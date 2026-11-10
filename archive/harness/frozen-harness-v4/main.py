"""Persistent finite campaign. Own services only; atomic case results and resumable checkpoints."""
from orchestrator import *
from parallel import direct_batch,capture_runtime
from report import report
from preserve import checkpoint
import random,fcntl
QUALIFIED=[]
def status(phase,**extra):
 atomic(O/'campaign-status.json',{'phase':phase,'at':time.time(),'pid':os.getpid(),'harness_revision':HARNESS_REVISION,**extra});event('phase',phase=phase,**extra);report();print(phase,json.dumps(extra),flush=True)
def own_memory_reset():
 if STOP.is_set():
  subprocess.run(['systemctl','--user','stop',INFER_UNIT],capture_output=True);time.sleep(3);STOP.clear();set_profile()
def execute(id,task,models,seed=42,topology=1,variant=0,phase='solo'):
 if not id.endswith('-'+HARNESS_REVISION):id+='-'+HARNESS_REVISION
 folder=O/'runs'/id
 if (folder/'result.json').exists():
  prior=json.load(open(folder/'result.json'))
  if not prior.get('interrupted'):return prior
 # An interrupted case is preserved and rerun as a distinct, labelled attempt, never overwritten.
 if folder.exists() and (folder/'manifest.json').exists():
  old=json.load(open(folder/'manifest.json'))
  try:native('down',old['rig'],'--yes','--json',timeout=120)
  except Exception:pass
  archived=folder.with_name(id+'-interrupted-'+str(int(time.time())));folder.rename(archived);event('interrupted_case_preserved',id=id,path=str(archived))
 own_memory_reset();healthy_wait();status(phase,current=id);r=Case(id,task,models,seed,topology,variant,phase).run();r['resource_limited']=STOP.is_set();atomic(folder/'result.json',r);report();return r

def monitor():
 low=None;last=0;counter=0;oom_previous=0
 with (O/'memory-timeline.jsonl').open('a') as f:
  while True:
   try:
    s=snapshot();s['active_jobs']=list(ACTIVE);s['memory_pressure']=pathlib.Path('/proc/pressure/memory').read_text();s['temperatures']={str(p):p.read_text().strip() for p in pathlib.Path('/sys/class/hwmon').glob('hwmon*/temp*_input')};f.write(json.dumps(s)+'\n');f.flush();atomic(O/'heartbeat.json',{'at':time.time(),'pid':os.getpid(),'active_jobs':list(ACTIVE),'available':s['available']});counter+=1
    if counter%5==0:
     try:
      cg=subprocess.check_output(['systemctl','--user','show',INFER_UNIT,'-p','ControlGroup','--value'],text=True).strip();events=pathlib.Path('/sys/fs/cgroup'+cg)/'memory.events';
      if not cg:raise ValueError('No active private inference cgroup')
      counts=dict(line.split() for line in events.read_text().splitlines());oom=int(counts.get('oom_kill',0));s['inference_oom_kills']=oom
      if oom>oom_previous and not STOP.is_set():STOP.set();event('resource_guard',reason='Private inference cgroup OOM; not a coding-quality failure',count=oom);subprocess.run(['systemctl','--user','stop',INFER_UNIT],capture_output=True)
      oom_previous=oom
     except Exception:pass
     try:atomic(O/'currently-loaded.json',api('/api/ps',timeout=3))
     except Exception:pass
    if s['available']<16*2**30:
     low=low or time.monotonic()
     if time.monotonic()-low>20 and not STOP.is_set():event('resource_guard',reason='MemAvailable below16GiB for20s',sample=s);STOP.set();subprocess.run(['systemctl','--user','stop',INFER_UNIT],capture_output=True)
    else:low=None
   except Exception as e:event('monitor_error',error=str(e))
   time.sleep(1)

def qualifier():
 assert json.load(open(O/'repair-checks-latest.json'))['passed'],'Repair regression checks failed'
 assert json.load(open(O/'guard-checks-latest.json'))['passed'],'Revised guard checks failed'
 for f in ['qualification/summary.json','qualification-final/summary.json','guard-qualification/summary.json']:
  assert json.load(open(O/f))['passed'],f
 # Changes to shared integration cases and coverage are qualified again in the frozen harness.
 q=O/('frozen-qualification-'+HARNESS_REVISION);q.mkdir(exist_ok=True);checks=[]
 for id,t in TASKS.items():
  root=q/id/'project';write_reference(t,root);r=run_checks(root,t,root.parent/'control',private=True);atomic(q/(id+'.json'),r);checks.append({'id':id,'passed':r['passed']})
  if not r['passed']:raise RuntimeError('Frozen reference failed: '+id)
 atomic(q/'summary.json',{'passed':True,'checks':checks})
 import replay
 replay_result=replay.run()
 if not replay_result['complete']:event('baseline_replay_failure_preserved',result=replay_result)
 for lang,task in [('python','py-csv'),('cpp','cpp-buffer')]:
  r=execute('qualification-'+lang+'-frozen',task,{'lead':'next','developer':'next','reviewer':'next'},topology=3,phase='qualification')
  if not r['complete']:raise RuntimeError('Native guarded baseline failed for '+lang+'; preserve and diagnose before ranking')
 archive_db('baseline-'+HARNESS_REVISION);checkpoint('baseline-'+HARNESS_REVISION)

def qualify_topologies():
 # Each workflow is retried under the revision before scored team comparisons.
 for task in ['py-team','cpp-team']:
  for n in [1,2,4,5,6]:
   revision='-v2' if n>=5 else ''
   r=execute(f'qualification-{task}-n{n}'+revision,task,{'lead':'next','developer':'next','reviewer':'next'},topology=n,phase='qualification')
   atomic(O/('topology-qualification-'+HARNESS_REVISION)/f'{task}-{n}.json',r)
 archive_db('qualification-complete');checkpoint('qualification')

def eligible_models():
 good=[]
 for key in MODELS:
  own_memory_reset();healthy_wait();status('compatibility',current=key);r=compatibility(key)
  if r['qualified'] and key!='tiny':good.append(key)
 atomic(O/'qualified-models.json',good);return good

def solos(good):
 tasks=[id for id in TASKS if id not in ['py-team','py-normalizer','cpp-team']]
 for key in good:
  order=tasks[:];random.Random(1729+list(MODELS).index(key)).shuffle(order)
  for seed in [42,43,44]:
   for task in order:execute(f'solo-{key}-{task}-s{seed}',task,{'developer':key},seed,1,phase='solo')
  archive_db('after-solo-'+key);checkpoint('solo-'+key)
  execute('drift-control-'+key,'py-csv',{'developer':'next'},42,1,phase='drift-control')
  for task in ['py-queue','cpp-buffer']:planner_probe(key,task)
  for task in ['py-refactor','cpp-binary']:
   for goodpatch in [True,False]:role_probe(key,task,goodpatch)

def repair_reruns():
 # Fresh projects, not patched answers. IDs are the same scored matrix cells
 # with the new revision suffix, so the normal schedule never double-counts.
 cells=[('py-queue',42),('cpp-queue',42),('cpp-csv',42),('cpp-stats',42),('py-refactor',42),('py-archive',42),('py-queue',43)]
 for task,seed in cells:execute(f'solo-next-{task}-s{seed}',task,{'developer':'next'},seed,1,phase='solo')
 archive_db('repair-reruns-'+HARNESS_REVISION);checkpoint('repair-reruns-'+HARNESS_REVISION)

def triples(good):
 sets={'A':('next','next','next'),'B':('q35','next','devstral'),'C':('q27q4','next','glm'),'D':('nemo','q27q4','devstral'),'E':('q122','next','glm'),'F':('gpt120','next','devstral'),'G':('q9','coder30','glm'),'H':('gpt20','coder30','devstral'),'I':('glm','next','q35'),'J':('next','coder30','gpt20'),'K':('devstral','next','q27q4')}
 for label,keys in sets.items():
  if not all(k in good for k in keys):atomic(O/'ineligible-cells'/('team-'+label+'.json'),{'models':keys,'reason':'A required model did not qualify for structured OpenRig tools'});continue
  models=dict(zip(['lead','developer','reviewer'],keys))
  for task in ['py-http','py-refactor','cpp-queue','cpp-binary']:
   for seed in [42,43,44]:execute(f'team-{label}-{task}-s{seed}',task,models,seed,3,100,phase='teams')
  archive_db('after-team-'+label);checkpoint('team-'+label)

def ranking(good,lang):
 rows=report();candidates=[]
 for key in good:
  items=[x for x in rows if x['phase']=='solo' and x['language']==lang and x['models']['developer']==key]
  if items:candidates.append((sum(x['complete'] for x in items)/len(items),sum(x['complete'] for x in items)*3600/max(.001,sum(x['seconds'] for x in items)),key))
 return [x[2] for x in sorted(candidates,reverse=True)] or ['next']
def model_sets(good,lang):
 ranked=ranking(good,lang);dev=ranked[0];reviews=[]
 for key in good:
  prefix='py-' if lang=='python' else 'cpp-'
  probes=[json.load(open(f)) for f in (O/'role-probes').glob('probe-'+key+'-'+prefix+'*/result.json')];valid=[r for r in probes if r.get('state')=='complete'];reviews.append((sum(r.get('correct_decision',False) for r in valid)/max(1,len(probes)),len(valid),key))
 reviewer=max(reviews)[2] if reviews else 'next';rows=report();teams=[r for r in rows if r['phase']=='teams' and r['language']==lang];planners=[]
 for key in good:
  entries=[r for r in teams if r['models']['lead']==key]
  if entries:planners.append((sum(r['complete'] for r in entries)/len(entries),sum(r['complete'] for r in entries)/max(1,sum(r['seconds'] for r in entries)),key))
 lead=max(planners)[2] if planners else 'next';return {'uniform':{'lead':dev,'developer':dev,'reviewer':dev},'mixed':{'lead':lead,'developer':dev,'reviewer':reviewer}}
def topologies(good):
 chosen={}
 for lang,task in [('python','py-team'),('cpp','cpp-team')]:
  chosen[lang]=model_sets(good,lang)
  for label,models in chosen[lang].items():
   for n in [1,2,3,4,5,6]:
    qualification=O/('topology-qualification-'+HARNESS_REVISION)/f'{task}-{n}.json'
    reference=json.load(open(O/('frozen-qualification-'+HARNESS_REVISION)/(task+'.json')))
    if not reference.get('passed'):raise RuntimeError('Integration reference no longer qualifies: '+task)
    if n!=3 and (not qualification.exists() or not json.load(open(qualification)).get('complete')):atomic(O/'topology-warnings'/f'{lang}-{label}-{n}.json',{'reason':'Coder-Next workflow trial did not complete; reference fixture passes. This exploratory topology is still attempted with the selected models; report its reliability separately.'})
    for variant in [0,1]:
     for seed in [42,43,44]:execute(f'topology-{lang}-{label}-n{n}-v{variant}-s{seed}',task,models,seed,n,variant,phase='topology')
 expanded={'four':{'lead':'q35','developer':'next','tester':'glm','reviewer':'devstral'},'five':{'lead':'q35','developer':'next','developer2':'coder30','tester':'glm','reviewer':'devstral'},'six':{'lead':'q35','developer':'next','developer2':'coder30','tester':'q9','reviewer':'devstral','integrator':'glm'}}
 for label,models in expanded.items():
  n=len(models)
  if not all(k in good for k in models.values()):atomic(O/'ineligible-cells'/('expanded-'+label+'.json'),{'models':models,'reason':'A model lacks OpenRig tool qualification'});continue
  for task in ['py-team','cpp-team']:
   for seed in [42,43,44]:execute(f'expanded-{label}-{task}-s{seed}',task,models,seed,n,1,phase='topology')
 atomic(O/'selected-model-sets.json',chosen);archive_db('topologies-complete');checkpoint('topologies');return chosen

def parallel_work(good,chosen):
 # The direct layer characterizes queueing/prefill/concurrency independently from orchestration.
 candidates=['next','glm']+[ranking(good,l)[0] for l in ['python','cpp']];candidates=list(dict.fromkeys(k for k in candidates if k in good))[:4]
 for key in candidates:
  for slots in [1,2,3,4]:
   for ctx in [8192,16384,32768]:
    own_memory_reset();set_profile(slots,1,ctx)
    for seed in [42,43,44]:
     if STOP.is_set():break
     healthy_wait();status('parallel-inference',model=key,slots=slots,context=ctx);direct_batch(key,slots,ctx,seed)
    capture_runtime(f'{key}-{slots}-{ctx}')
    if STOP.is_set():break
 for key in candidates:
  ds=[json.load(open(f)) for f in (O/'parallel-inference').glob(f'api-{key}-p*-c32768-*/result.json')];one=[r for r in ds if r['slots_requested']==1];four=[r for r in ds if r['slots_requested']==4];qualified=one and four and all(r.get('accepted',0)>=3 and r.get('memory_after',{}).get('available',0)>=24*2**30 for r in four) and max(r['aggregate_tokens_per_second'] for r in four)>=1.2*max(r['aggregate_tokens_per_second'] for r in one)
  if not qualified:atomic(O/'ineligible-cells'/('six-slots-'+key+'.json'),{'reason':'Four-slot throughput or memory qualification did not justify six slots'});continue
  for slots in [1,2,3,4,6]:
   own_memory_reset();set_profile(slots,1,32768)
   for seed in [42,43,44]:
    if STOP.is_set():break
    healthy_wait();direct_batch(key,slots,32768,seed,requests=6)
   capture_runtime(f'saturated-six-{key}-{slots}')
 # Test unique-model counts separately from agent counts; the 5/6-model tiers are explicit 8K memory diagnostics.
 allkeys=['q9','coder30','devstral','glm','gpt20','gemma']
 for count in [2,3,4,5,6]:
  mix=allkeys[:count];ctx=32768 if count<=4 else 8192
  for resident in sorted(set([1,count])):
   own_memory_reset();set_profile(1,resident,ctx)
   for seed in [42,43,44]:
    if STOP.is_set():break
    healthy_wait();status('mixed-model-residency',models=mix,max_loaded=resident,context=ctx);direct_batch('mixed',1,ctx,seed,requests=count,mix=mix)
   capture_runtime(f'mixed-{count}-resident{resident}-ctx{ctx}')
 # Actual simultaneous complete guarded OpenRig jobs, with fixed project/agent work.
 pools={'same-model':{'lead':'next','developer':'next','reviewer':'next'},'small-mixed':{'lead':'q9','developer':'coder30','reviewer':'glm'},'review-pair':{'lead':'devstral','developer':'glm','reviewer':'devstral'}}
 for label,models in pools.items():
  if not all(k in good for k in models.values()):continue
  for slots in [1,2,3,4]:
   for resident in sorted(set([1,len(set(models.values()))])):
    own_memory_reset();set_profile(slots,resident,32768)
    for count in [1,2,3]:
     for seed in [42,43,44]:
      id=f'jobs-{label}-p{slots}-m{resident}-j{count}-s{seed}';d=O/'parallel-jobs'/id;d.mkdir(parents=True,exist_ok=True)
      if (d/'result.json').exists():continue
      healthy_wait();status('parallel-jobs',current=id);begin=time.time()
      with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:results=list(pool.map(lambda i:execute(id+'-'+str(i),'py-csv' if i%2==0 else 'cpp-buffer',models,seed,3,i+300,phase='parallel-jobs'),range(count)))
      elapsed=time.time()-begin;atomic(d/'result.json',{'id':id,'models':models,'slots':slots,'max_loaded_models':resident,'concurrent_jobs':count,'seconds':elapsed,'accepted':sum(r['complete'] for r in results),'accepted_tasks_per_hour':sum(r['complete'] for r in results)*3600/max(elapsed,.001),'per_language':{lang:{'accepted':sum(r['complete'] for r in results if r['language']==lang),'attempts':sum(r['language']==lang for r in results)} for lang in ['python','cpp']},'case_ids':[r['id'] for r in results],'resource_limited':STOP.is_set()})
     capture_runtime(id)
     if STOP.is_set():break
    if STOP.is_set():break
 archive_db('parallel-complete');checkpoint('parallel')

def soak(good):
 batches=[json.load(open(f)) for f in (O/'parallel-jobs').glob('*/result.json')];stable=[b for b in batches if b['accepted']==b['concurrent_jobs'] and not b.get('resource_limited')];stable.sort(key=lambda b:b['accepted_tasks_per_hour'],reverse=True);profiles=[]
 for b in stable:
  key=(str(b['models']),b['slots'],b['max_loaded_models'],b['concurrent_jobs'])
  if key not in [p[0] for p in profiles]:profiles.append((key,b))
  if len(profiles)==3:break
 if not profiles:profiles=[(('fallback',1,1,1),{'models':{'lead':'next','developer':'next','reviewer':'next'},'slots':1,'max_loaded_models':1,'concurrent_jobs':1})]
 plan=json.load(open(O/'soak-plan.json')) if (O/'soak-plan.json').exists() else {'start':time.time(),'minimum_window_hours':6,'profiles':[p[1] for p in profiles]};atomic(O/'soak-plan.json',plan);stop_at=plan['start']+6*3600;completed=[int(f.stem.split('-')[-1]) for f in (O/'soak').glob('batch-*.json')];index=max(completed,default=-1)+1
 while time.time()<stop_at:
  _,p=profiles[index%len(profiles)];own_memory_reset();set_profile(p['slots'],p['max_loaded_models'],32768);seed=[42,43,44][index%3];n=p['concurrent_jobs'];batchstart=time.time();status('soak',batch=index)
  with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:results=list(pool.map(lambda i:execute(f'soak-{index}-{i}','py-queue' if (index+i)%2==0 else 'cpp-queue',p['models'],seed,3,index+500,phase='soak'),range(n)))
  atomic(O/'soak'/f'batch-{index}.json',{'seconds':time.time()-batchstart,'cases':[r['id'] for r in results],'accepted':sum(r['complete'] for r in results)});index+=1
  if not (O/'recovery-test.json').exists():
   atomic(O/'recovery-test.json',{'state':'checkpointed-before-controlled-runner-restart','pid_before':os.getpid(),'at':time.time(),'last_completed_batch':index-1});event('controlled_runner_restart',checkpoint_batch=index-1);os._exit(99)
 archive_db('soak-complete');checkpoint('soak')

def main():
 if (O/'COMPLETED.json').exists():print('Campaign already complete; no tests repeated.',flush=True);return
 lock=open(O/'campaign.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);init_services();threading.Thread(target=monitor,daemon=True).start();
 if (O/'recovery-test.json').exists():
  recovery=json.load(open(O/'recovery-test.json'))
  if recovery['state']=='checkpointed-before-controlled-runner-restart':
   recovery.update(state='resumed-from-preserved-checkpoint',pid_after=os.getpid(),resumed_at=time.time(),passed=os.getpid()!=recovery['pid_before']);atomic(O/'recovery-test.json',recovery)
 atomic(O/'models.json',model_config('bootstrap',[('next',42)]));status('qualification')
 try:
  qualification_marker=O/('qualification-done-'+HARNESS_REVISION+'.json')
  if not qualification_marker.exists():qualifier();atomic(qualification_marker,{'passed':True,'at':time.time(),'harness_revision':HARNESS_REVISION})
  good=eligible_models();assert 'next' in good,'Baseline unavailable';status('repair-reruns');repair_reruns()
  topology_marker=O/('topology-checks-done-'+HARNESS_REVISION+'.json')
  if not topology_marker.exists():qualify_topologies();atomic(topology_marker,{'at':time.time(),'done':True})
  status('solo',models=good);solos(good);status('teams');set_profile();triples(good);status('topology');chosen=topologies(good);status('parallel');parallel_work(good,chosen);status('soak');soak(good);status('complete');report(final=True);archive_db('final');atomic(O/'COMPLETED.json',{'at':time.time(),'harness_revision':HARNESS_REVISION,'phases':['python-and-cpp-solo','role-probes','three-seat-combinations','one-through-six-agent-topologies','distinct-model-counts','parallel-inference','concurrent-guarded-jobs','six-hour-soak'],'report':str(O/'RESULTS.txt')});checkpoint('final');event('campaign_complete');subprocess.run(['systemctl','--user','disable',P['unit']+'.service'],capture_output=True)
 except Exception as e:
  atomic(O/'ATTENTION.json',{'at':time.time(),'error':str(e),'traceback':traceback.format_exc(),'note':'Results preserved. No production changes or automatic promotion.'});status('needs_attention',error=str(e));raise SystemExit(78)
 finally:
  subprocess.run(['systemctl','--user','stop',INFER_UNIT],capture_output=True)
  try:native('daemon','stop',timeout=90)
  except Exception:pass
def request_stop(signum,frame):
 STOP.set();event('operator_stop',signal=signum);raise SystemExit(128+signum)
if __name__=='__main__':
 signal.signal(signal.SIGTERM,request_stop);signal.signal(signal.SIGINT,request_stop);main()
