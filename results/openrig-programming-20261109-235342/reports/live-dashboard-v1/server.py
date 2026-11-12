"""Independent read-only campaign observer. No inference or service-control code."""
import argparse
import collections
import datetime
import hashlib
import http.server
import json
import os
from pathlib import Path
import threading
import time
import urllib.parse
import zoneinfo

HERE = Path(__file__).resolve().parent
DEFAULT_CAMPAIGN = HERE.parents[2]
LABELS = {'next':'Qwen3-Coder-Next 80B','coder30':'Qwen3-Coder 30B','nemo':'Nemotron 3 Nano 30B','q35':'Qwen3.5 35B','devstral':'Devstral Small 2','glm':'GLM 4.7 Flash','q27q4':'Qwen 27B Q4','q9':'Qwen3.5 9B','q27q8':'Qwen 27B Q8','q122':'Qwen3.5 122B','gpt120':'GPT-OSS 120B','gpt20':'GPT-OSS 20B'}
ORDER = ['next','coder30','nemo','q35','devstral','glm','q27q4','q9','q27q8','q122','gpt120','gpt20']

def read_json(path):
    return json.loads(path.read_bytes())

def atomic(path, value):
    tmp = path.with_name(path.name + '.pending')
    tmp.write_text(json.dumps(value, ensure_ascii=False, separators=(',',':')))
    os.replace(tmp, path)

def collect(campaign, now=None):
    now = time.time() if now is None else now
    rows, hashes, byid, excluded = [], {}, collections.defaultdict(list), collections.Counter()
    for path in sorted((campaign/'runs').glob('*/result.json')):
        raw = path.read_bytes()
        r = json.loads(raw)
        if r.get('interrupted'):
            excluded['interrupted'] += 1
            continue
        if r.get('phase') != 'solo':
            excluded[r.get('phase','other')] += 1
            continue
        # h5.5 writes the result before cleanup, then adds resource_limited in
        # execute.finally. Do not count that intermediate result as finalized.
        if (not r.get('finished') or r['finished'] > now or path.stat().st_mtime > now-2
                or (r.get('harness_revision') == 'h5.5' and 'resource_limited' not in r)):
            excluded['not_final_at_capture'] += 1
            continue
        if set(r['models']) != {'developer'} or r['topology'] != 1:
            raise ValueError('Unexpected solo task contract: '+path.parent.name)
        row = dict(id=r['id'], directory=path.parent.name, revision=r.get('harness_revision') or 'legacy',
                   model=r['models']['developer'], language=r['language'], task=r['task'], seed=r['seed'],
                   variant=r.get('variant',0), passed=bool(r['complete']), seconds=r['seconds'], attempts=r.get('attempts'),
                   resource_limited=r.get('resource_limited'), started=r['started'], finished=r['finished'],
                   reason=str(r.get('last_stage_feedback') or r.get('failure') or '')[:420],
                   tokens=0, request_seconds=0.0, ttft=[], measured_requests=0, http_errors=0, context_rejections=0)
        public = sorted(path.parent.glob('seats/*/control/public-*.json'))
        q = read_json(public[-1]) if public else {}
        row['last_public_modes'] = {k:v.get('passed') for k,v in q.get('checks',{}).items()}
        row['last_saved_tests'] = q.get('authored_tests',{}).get('passed')
        private = sorted(path.parent.glob('attempt-*-suite.json'))
        row['private_acceptance_recorded'] = bool(private)
        if private:
            row['last_private_passed'] = read_json(private[-1]).get('passed')
        rows.append(row)
        byid[r['id']].append(row)
        hashes[str(path.relative_to(campaign))] = hashlib.sha256(raw).hexdigest()
    # Read only the event log length captured at open; never follow the writer.
    with (campaign/'events.jsonl').open('rb') as stream:
        size = os.fstat(stream.fileno()).st_size
        for line in stream.read(size).splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get('kind') != 'inference_request':
                continue
            for row in byid.get(e.get('prefix','').split('/')[0], []):
                if not row['started'] <= e.get('at',0) <= row['finished']:
                    continue
                if e.get('error'):
                    row['http_errors'] += 1
                if 'Pinned instructions' in e.get('error',''):
                    row['context_rejections'] += 1
                if not e.get('complete'):
                    continue
                value = e.get('first_delivered_seconds')
                if isinstance(value,(int,float)) and value >= 0:
                    row['ttft'].append(round(value,6))
                tokens, seconds = (e.get('usage') or {}).get('completion_tokens'), e.get('seconds')
                if isinstance(tokens,(int,float)) and tokens >= 0 and isinstance(seconds,(int,float)) and seconds > 0:
                    row['tokens'] += tokens
                    row['request_seconds'] += seconds
                    row['measured_requests'] += 1
    for row in rows:
        row['seconds'] = round(row['seconds'],6)
        row['request_seconds'] = round(row['request_seconds'],6)
        del row['started'], row['finished']
    revisions = sorted({r['revision'] for r in rows}, key=lambda r:tuple(int(x) for x in r[1:].split('.')) if r.startswith('h') else (0,), reverse=True)
    local = datetime.datetime.fromtimestamp(now,zoneinfo.ZoneInfo('America/Chicago'))
    data = dict(schema=1, captured_at=now, captured_label=local.strftime('%b %d, %Y · %I:%M:%S %p %Z'),
                active_revision=read_json(campaign/'active-harness-revision.json')['revision'],
                revisions=revisions, model_order=ORDER, labels=LABELS, excluded=dict(excluded), cases=rows,
                snapshot_policy='Finalized solo trials only. Interrupted and qualification trials excluded. Revisions never pooled. Token rates include prefill/overhead; missing evidence is unknown.')
    return data, hashes

class Observer:
    def __init__(self, campaign, state):
        self.campaign, self.state = campaign, state
        state.mkdir(parents=True,exist_ok=True)
        self.signature = None

    def scan(self):
        signature = tuple((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in sorted((self.campaign/'runs').glob('*/result.json')))
        revision = (self.campaign/'active-harness-revision.json').read_bytes()
        changed = (signature,revision) != self.signature
        status = dict(checked_at=time.time(),error=None)
        try:
            if changed or not (self.state/'data.json').exists():
                data, hashes = collect(self.campaign)
                identity = hashlib.sha256(json.dumps([hashes,data['active_revision']],sort_keys=True).encode()).hexdigest()
                previous = read_json(self.state/'data.json') if (self.state/'data.json').exists() else None
                if not previous or previous.get('result_identity') != identity:
                    data['result_identity'] = identity
                    destination = self.state/'snapshots'/str(time.time_ns())
                    destination.mkdir(parents=True)
                    atomic(destination/'data.json',data)
                    atomic(destination/'source-result-sha256.json',hashes)
                    atomic(self.state/'data.json',data)
                # Leave the signature pending while a fresh/incomplete result is
                # present, so its finality delay is rechecked without a new write.
                if not data['excluded'].get('not_final_at_capture'):
                    self.signature = (signature,revision)
            heartbeat = read_json(self.campaign/'heartbeat.json')
            campaign_status = read_json(self.campaign/'campaign-status.json')
            data = read_json(self.state/'data.json')
            status.update(campaign_pid=heartbeat['pid'],heartbeat_at=heartbeat['at'],
                          active_jobs=heartbeat.get('active_jobs',[]),phase=campaign_status.get('phase'),
                          current=campaign_status.get('current'),revision=data['active_revision'],
                          captured_at=data['captured_at'],captured_label=data['captured_label'],
                          result_identity=data['result_identity'],finished_solo_trials=len(data['cases']))
        except Exception as exc:
            status['error'] = type(exc).__name__+': '+str(exc)
        atomic(self.state/'status.json',status)
        return status

    def run(self):
        while True:
            try:
                self.scan()
            except Exception as exc:
                print('Observer retry:',repr(exc),flush=True)
            time.sleep(10)

def handler(state, port):
    files = {'/':'index.html','/dashboard.js':'dashboard.js','/chart_logic.mjs':'chart_logic.mjs',
             '/visualize.css':'visualize.css','/theme.css':'theme.css'}
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            allowed = {'127.0.0.1:'+str(port),'localhost:'+str(port)}
            if self.headers.get('Host') not in allowed:
                self.send_error(403)
                return
            origin = self.headers.get('Origin')
            if origin and origin not in {'http://'+x for x in allowed}:
                self.send_error(403)
                return
            route = urllib.parse.urlsplit(self.path).path
            if route in ('/data.json','/status.json'):
                path = state/route[1:]
            elif route in files:
                path = HERE/files[route]
            else:
                self.send_error(404)
                return
            if not path.is_file():
                self.send_error(503,'Waiting for first successful read')
                return
            raw = path.read_bytes()
            self.send_response(200)
            kind = {'html':'text/html','css':'text/css','js':'text/javascript','mjs':'text/javascript','json':'application/json'}[path.suffix[1:]]
            self.send_header('Content-Type',kind+'; charset=utf-8')
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' https://persistent.oaistatic.com/plugins/visualize/charts/; style-src 'self' 'unsafe-inline' https://persistent.oaistatic.com/plugins/visualize/charts/; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError,ConnectionResetError):
                pass
        def log_message(self,*args):
            pass
    return Handler

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--campaign',type=Path,default=DEFAULT_CAMPAIGN)
    parser.add_argument('--state',type=Path,default=HERE/'state')
    parser.add_argument('--port',type=int,default=18765)
    args = parser.parse_args()
    observer = Observer(args.campaign,args.state)
    observer.scan()
    threading.Thread(target=observer.run,daemon=True).start()
    http.server.ThreadingHTTPServer(('127.0.0.1',args.port),handler(args.state,args.port)).serve_forever()
