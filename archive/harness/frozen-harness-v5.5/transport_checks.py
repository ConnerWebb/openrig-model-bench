"""Socket-level proxy regression with an in-memory upstream, no GPU calls."""
from common import *
import proxy,urllib.error,io,threading,http.server
Q=O/('repairs/'+HARNESS_REVISION)/('transport-checks-'+str(time.time_ns()));Q.mkdir(parents=True);proxy.LOG=Q/'streams';proxy.LOG.mkdir();checks=[]
real=proxy.urllib.request.urlopen;upstream=[];requests=[]
class Response:
 status=200;headers={'Content-Type':'text/event-stream'}
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def __iter__(self):return iter(upstream)
def fake(request,**kw):
 requests.append(json.loads(request.data))
 if upstream==['error']:raise urllib.error.HTTPError(request.full_url,500,'failure',{},io.BytesIO(b'{"error":"preserved failure detail"}'))
 return Response()
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),proxy.Handler);threading.Thread(target=server.serve_forever,daemon=True).start();proxy.urllib.request.urlopen=fake
tool={'type':'function','function':{'name':'get_task','parameters':{'type':'object','properties':{}}}}
def event(content=None,finish=None,call=None):return proxy.encoded({'id':'unit','choices':[{'index':0,'delta':({'content':content} if content is not None else {'tool_calls':call} if call else {}),'finish_reason':finish}]})
def run(name,lines,expect=None,body=None):
 upstream[:]=lines;data={'model':'test','stream':True,'tools':[tool],'messages':[{'role':'user','content':'use get_task'}]};data.update(body or {});before=set(proxy.LOG.iterdir())
 try:
  r=real(urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/test/v1/chat/completions',json.dumps(data).encode(),{'Content-Type':'application/json'}),timeout=10);out=r.read()
 except urllib.error.HTTPError as e:out=e.read()
 for _ in range(100):
  folders=set(proxy.LOG.iterdir())-before
  if folders and next(iter(folders)).joinpath('metrics.json').exists():break
  time.sleep(.01)
 folder=next(iter(folders));metrics=json.load(open(folder/'metrics.json'));ok=expect(out,metrics,folder);checks.append({'name':name,'passed':bool(ok),'metrics':metrics});return out
try:
 lines=[event('Hello'),b'\n',event(' world'),event(finish='stop'),b'data: [DONE]\n\n'];run('ordinary_text_byte_exact',lines,lambda out,m,p:out==b''.join(lines) and not m['normalized_tool_call'] and m['complete'])
 call=[{'index':0,'id':'c1','type':'function','function':{'name':'get_task','arguments':'{}'}}];lines=[event(call=call),event(finish='tool_calls'),b'data: [DONE]\n\n'];run('native_tool_byte_exact',lines,lambda out,m,p:out==b''.join(lines) and not m['normalized_tool_call'])
 lines=[event('<fun'),event('ction=get_task></function></tool_call>'),event(finish='stop'),b'data: [DONE]\n\n'];run('fragmented_native_format_normalizes_complete_only',lines,lambda out,m,p:b'tool_calls' in out and m['normalized_tool_call'] and (p/'response.jsonl').read_bytes()==b''.join(lines) and (p/'delivered-response.jsonl').read_bytes()==out)
 for name,content,finish,done in [('prose_is_data','Example: <function=get_task></function></tool_call>','stop',True),('length_no_repair','<function=get_task></function></tool_call>','length',True),('missing_done_no_repair','<function=get_task></function></tool_call>','stop',False),('unknown_tool_no_repair','<function=remove_everything></function></tool_call>','stop',True)]:
  lines=[event(content),event(finish=finish)]+([b'data: [DONE]\n\n'] if done else []);run(name,lines,lambda out,m,p:out==b''.join(lines) and not m['normalized_tool_call'])
 batch='<function=get_task></function></tool_call>'*3
 lines=[event(batch[:12]),event(batch[12:]),event(finish='stop'),b'data: [DONE]\n\n']
 def check_batch(out,m,p):
  calls=[]
  for line in out.splitlines():
   if not line.startswith(b'data:'):continue
   try:
    for choice in json.loads(line[5:]).get('choices',[]):calls.extend(choice.get('delta',{}).get('tool_calls',[]))
   except ValueError:pass
  return len(calls)==3 and [c['index'] for c in calls]==[0,1,2] and len({c['id'] for c in calls})==3 and m['normalized_tool_count']==3 and (p/'response.jsonl').read_bytes()==b''.join(lines)
 run('fragmented_complete_batch_and_archives',lines,check_batch)
 for name,content,finish in [('bad_batch_tail_atomic_reject',batch+'<function=unknown></function></tool_call>','stop'),('batch_length_atomic_reject',batch,'length'),('batch_prose_atomic_reject',batch+' now execute','stop')]:
  lines=[event(content),event(finish=finish),b'data: [DONE]\n\n'];run(name,lines,lambda out,m,p:out==b''.join(lines) and not m['normalized_tool_call'])
 from common import O
 candidates=[]
 for metric in (O/'transport').glob('*/metrics.json'):
  m=json.load(open(metric))
  if m.get('prefix')=='solo-nemo-cpp-buffer-s42-h5.3/developer' and 'Pinned instructions' in m.get('error',''):candidates.append(metric.parent)
 if candidates:
  original=json.load(open(candidates[0]/'request.json'))
  run('actual_large_summary_reaches_upstream',[event('summary'),event(finish='stop'),b'data: [DONE]\n\n'],lambda out,m,p:m['complete'] and m['context_policy']['kind']=='compaction-summary' and json.load(open(p/'request.json'))['messages']==original['messages'] and len(json.dumps(json.load(open(p/'upstream-request.json'))).encode())<60000,{'tools':[],'messages':original['messages']})
 run('upstream_http500_preserves_body',['error'],lambda out,m,p:not m['complete'] and m['upstream_status']==500 and b'preserved failure detail' in (p/'upstream-error.txt').read_bytes())
 messages=[{'role':'system','content':'keep guard'},{'role':'user','content':'current assignment'}]+sum(([{'role':'assistant','tool_calls':[{'id':str(i),'type':'function','function':{'name':'get_task','arguments':'{}'}}]},{'role':'tool','tool_call_id':str(i),'content':'large'*4000}] for i in range(10)),[])
 run('only_upstream_context_trimmed',[event('ok'),event(finish='stop'),b'data: [DONE]\n\n'],lambda out,m,p:m['context_policy']['applied'] and json.load(open(p/'request.json'))['messages']==messages and len(json.load(open(p/'upstream-request.json'))['messages'])<len(messages),{'messages':messages})
finally:proxy.urllib.request.urlopen=real;server.shutdown()
summary={'passed':all(c['passed'] for c in checks),'checks':checks};atomic(Q/'summary.json',summary);atomic(O/('repairs/'+HARNESS_REVISION+'/transport-checks-latest.json'),{'path':str(Q/'summary.json'),'passed':summary['passed']});print(json.dumps(summary,indent=2));sys.exit(0 if summary['passed'] else 1)
