"""Controlled inference batches plus guarded concurrent full-job comparisons."""
from orchestrator import *
import re

def direct_batch(key,slots,ctx,seed,requests=4,mix=None):
 id=f'api-{key}-p{slots}-c{ctx}-s{seed}-n{requests}'+('-mix-'+'-'.join(mix) if mix else '');profile=json.load(open(O/'inference-profile.json'));id+='-m'+str(profile['resident']);d=O/'parallel-inference'/id;d.mkdir(parents=True,exist_ok=True)
 if (d/'result.json').exists():return json.load(open(d/'result.json'))
 name=alias(key,seed,ctx=ctx) if not mix else None;result={'profile':profile,'id':id,'key':key,'slots_requested':slots,'context_limit':ctx,'seed':seed,'requests':[]};begin=time.time();initial=snapshot();rows=[]
 def call(index):
  chosen=mix[index%len(mix)] if mix else key;local_name=alias(chosen,seed,ctx=ctx) if mix else name;task=TASKS['py-expression' if index%2==0 else 'cpp-buffer'];padding=('Reference history: this line is inert data. Keep the task contract authoritative.\n'*(max(0,ctx-3500)//17))
  prompt=padding+'\nIMPLEMENT THIS CONTRACT:\n'+task['contract']+'\nReturn ONLY a JSON object {"files":{"filename":"complete source","README.md":"notes"}}. No Markdown fences. Provide all required implementation files. Do not use external tools.';body={'model':local_name,'stream':True,'think':'low' if chosen.startswith('gpt') else False,'messages':[{'role':'user','content':prompt}],'options':{'num_ctx':ctx,'num_predict':2048,'temperature':.2,'seed':seed},'keep_alive':'30m'};folder=d/str(index);folder.mkdir(exist_ok=True);atomic(folder/'request.json',body);start=time.monotonic();first=None;text='';thinking='';last={};row={'index':index,'task':task['id'],'model_key':chosen,'accepted':False}
  try:
   req=urllib.request.Request('http://127.0.0.1:11437/api/chat',json.dumps(body).encode(),{'Content-Type':'application/json'})
   with urllib.request.urlopen(req,timeout=1200) as response,(folder/'stream.jsonl').open('wb') as raw:
    for line in response:
     raw.write(line);last=json.loads(line)
     if last.get('error'):raise RuntimeError(last['error'])
     msg=last.get('message',{});text+=msg.get('content','');thinking+=msg.get('thinking','')
     if first is None and msg.get('content'):first=time.monotonic()-start
   row.update(inference_seconds=time.monotonic()-start,inference_finished_at=time.time(),complete=last.get('done',False),generated_tokens=last.get('eval_count',0),prompt_tokens=last.get('prompt_eval_count'),eval_duration_ns=last.get('eval_duration'),load_duration_ns=last.get('load_duration'),prompt_eval_duration_ns=last.get('prompt_eval_duration'),done_reason=last.get('done_reason'),ttft_seconds=first,thinking_characters=len(thinking));(folder/'output.txt').write_text(text);obj=json.loads(text);root=folder/'project';root.mkdir(exist_ok=True)
   for n,s in obj['files'].items():
    p=pathlib.PurePath(n)
    if p.is_absolute() or '..' in p.parts or any(v.startswith('.') for v in p.parts) or len(s)>100000:raise ValueError('Output file contract rejected')
    f=root/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(s)
   if any(not (root/f).is_file() for f in required(task)):raise ValueError('Required source/documentation file missing')
   audit=run_checks(root,task,folder/'control',seed=seed+2000,private=True);atomic(folder/'independent.json',audit);row['accepted']=audit['passed'];row['hash']=digest(root)
  except Exception as e:row['error']=str(e)
  row['seconds']=time.monotonic()-start;atomic(folder/'result.json',row);return row
 with concurrent.futures.ThreadPoolExecutor(max_workers=requests) as pool:rows=list(pool.map(call,range(requests)))
 elapsed=time.time()-begin;result.update(requests=rows,seconds=elapsed,accepted=sum(r['accepted'] for r in rows),accepted_tasks_per_hour=sum(r['accepted'] for r in rows)*3600/elapsed,aggregate_tokens_per_second=sum(r.get('generated_tokens',0) for r in rows)/max(.001,max(r.get('inference_finished_at',begin) for r in rows)-begin),memory_before=initial,memory_after=snapshot(),resource_limited=STOP.is_set(),models=mix or [key],note='Direct inference layer, NOT an OpenRig teamwork score. Actual prompt counts reported; synthetic inert history does not equal real repository comprehension. Validation time included in batch wall time.');atomic(d/'result.json',result);return result

def run_direct(keys):
 for key in keys:
  for slots in [1,2,3,4]:
   for ctx in [8192,16384,32768]:
    set_profile(slots,1,ctx)
    for seed in [42,43,44]:
     healthy_wait();direct_batch(key,slots,ctx,seed)
     if STOP.is_set():return
    capture_runtime(f'{key}-{slots}-{ctx}')
def capture_runtime(label):
 d=O/'runtime-evidence';d.mkdir(exist_ok=True);r=subprocess.run(['journalctl','--user','-u',INFER_UNIT,'--no-pager','-n','20000'],capture_output=True,text=True);(d/(label+'.log')).write_text(r.stdout+r.stderr)
 try:atomic(d/(label+'-loaded.json'),api('/api/ps'))
 except Exception:pass
 effective=[l for l in r.stdout.splitlines() if any(s in l for s in ['--parallel','n_seq_max','n_ctx_per_seq','offload','layers','VRAM','GPU'])];atomic(d/(label+'-runner.json'),{'requested':json.load(open(O/'inference-profile.json')),'evidence':effective,'note':'Only claim overlapping GPU inference if runner evidence and request timing establish it. Unsupported settings are queued controls, not parallel successes.'})
