#!/usr/bin/python3
"""Guarded general Python/C++ task launcher; originals are never edited."""
import argparse,fcntl,hashlib,json,os,pathlib,shutil,subprocess,sys,time,uuid,threading,signal,re
P=pathlib.Path
BASE=P('/home/cow/.local/opt/framework-ai/openrig-fleet')
STATE=P('/home/cow/.local/state/openrig-fleet/v2/programming')
TEMPLATE=BASE/'v2/general-coding/template'
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix('.pending');q.write_text(json.dumps(v,indent=2));q.replace(p)
def inventory(root):
 out={}
 for p in sorted(root.rglob('*')):
  if any(n.startswith('.') or n in ['__pycache__','node_modules','build'] for n in p.relative_to(root).parts):continue
  if p.is_symlink():raise ValueError('Symlinks are not supported: '+str(p))
  if p.is_file():
   if p.stat().st_size>16*2**20:raise ValueError('File too large: '+str(p))
   out[str(p.relative_to(root))]=hashlib.sha256(p.read_bytes()).hexdigest()
 if sum((root/n).stat().st_size for n in out)>64*2**20:raise ValueError('Choose a project/subproject with at most64MiB of source')
 return out
PATCH='''
# General project task support: immutable operator checks outside agent workspace.
_original_suite=run_suite
_original_public=publish_public
_original_authored=authored_tests
def run_suite(root,task,control,seed=1,private=False):
 if task['id']!='general':return _original_suite(root,task,control,seed,private)
 before=digest(root); script=O/'trusted'/('acceptance.py' if private else 'public.py')
 marker='CHECK_COMPLETED_'+str(time.time_ns());code='import sys,runpy;sys.path.insert(0,"/work");runpy.run_path("/checks/check.py",run_name="__main__");print('+repr(marker)+')'
 r=sandbox(root,['python3','-I','-c',code],mounts=[(script,'/checks/check.py',False)],timeout=120)
 check={'passed':r['exit']==0 and marker in r['stdout'].splitlines() and before==digest(root),'count':1,'hash':before,'mode':'normal','compile':None,'failures':[] if r['exit']==0 else [{'case':'operator-check','exit':r['exit'],'stderr':r['stderr'],'actual':r['stdout'],'expected':'trusted check exit0'}]}
 check['rows']=[{'case':'operator-check','passed':check['passed'],'input':'trusted operator verification','exit':r['exit'],'stderr':r['stderr'],'actual':r['stdout'],'expected':'successful check and completion marker'}]
 return {'passed':check['passed'],'count':1,'hash':before,'checks':{'normal':check},'failed_modes':[] if check['passed'] else ['normal'],'not_run':{},'source_changed':before!=digest(root),'mode':'verification-suite','private':private}
def publish_public(task,root):
 if task['id']!='general':return _original_public(task,root)
 root=pathlib.Path(root);(root/'PUBLIC_CASES.json').write_text('{"verification":"Immutable operator check outside workspace. Add your own tests; do not search /checks."}');(root/'PUBLIC_DRIVER.py').write_text('# Use run_tests for the immutable operator check.\\n')
def authored_tests(root):
 # Existing authored-test execution is retained; CMake projects may use a Python test wrapper.
 if json.load(open(O/'task.json')).get('project_tests_only'):return {'passed':True,'note':'The frozen operator checker defines project test execution; no separate test auto-discovery is claimed.'}
 return _original_authored(root)
'''
def prepare(args):
 if args.project_tests_only and not args.check_file:raise ValueError('--project-tests-only requires --check-file')
 source=P(args.project).expanduser().resolve();task=P(args.task_file).expanduser().resolve().read_text()
 if not source.is_dir() or not task.strip():raise ValueError('Project directory and nonempty task file required')
 if any((source/n).exists() for n in ['Assets','ProjectSettings','Packages/manifest.json']):raise ValueError('Unity projects use their unchanged Unity launcher')
 if source==P.home() or source==P('/') or source.is_relative_to(STATE) or STATE.is_relative_to(source):raise ValueError('Choose a specific independent project')
 before=inventory(source);ident=time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6];job=STATE/'jobs'/ident;job.mkdir(parents=True)
 snap=job/'input';snap.mkdir()
 for name in before:
  dst=snap/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/name,dst)
 trusted=job/'trusted';trusted.mkdir()
 if args.check_file:check=P(args.check_file).expanduser().resolve().read_text()
 elif args.language=='python':
  tests={n:(source/n).read_text() for n in before if P(n).name.startswith('test') and n.endswith('.py')}
  if not tests:raise ValueError('Provide --check-file, or a Python project with existing unittest tests')
  check='import pathlib,tempfile,sys,unittest\nwith tempfile.TemporaryDirectory() as d:\n p=pathlib.Path(d)\n'
  for n,s in tests.items():check+=' f=p/'+repr(n)+';f.parent.mkdir(parents=True,exist_ok=True);f.write_text('+repr(s)+')\n'
  check+=' sys.path.insert(0,"/work");suite=unittest.defaultTestLoader.discover(d);r=unittest.TextTestRunner(verbosity=2).run(suite);assert r.testsRun>0 and r.wasSuccessful()\n'
 else:raise ValueError('C++ tasks require --check-file: a Python verification script that compiles/tests the project')
 (trusted/'public.py').write_text(check);(trusted/'acceptance.py').write_text(P(args.acceptance_file).read_text() if args.acceptance_file else check)
 profile=json.load(open(json.load(open('/home/cow/.local/state/openrig-fleet/v2/programming-defaults.json'))[args.language]));assert profile['model']=='framework-qwen122'
 runtime=job/'runtime-source';shutil.copytree(TEMPLATE/'runtime-source',runtime,ignore=shutil.ignore_patterns('__pycache__'))
 old='/home/cow/Documents/Codex/2026-11-05/referenced-chatgpt-conversation-this-is-an/outputs/qwen122-candidate-20261113-131635';new=str(job)
 for f in runtime.iterdir():
  if f.is_file() and f.suffix in ['.py','.ts','.cjs']:
   text=f.read_text().replace(old,new)
   if f.name=='extension.ts':text=text.replace('Read PUBLIC_DRIVER.py/cpp for exact wire format, and load public-inputs files directly rather than retyping escaped CSV or driver headers. Implement the declared API, not the grading wire protocol.','Read TASK.txt and implement the project task. run_tests executes the frozen operator check.')
   f.write_text(text)
 with (runtime/'common.py').open('a') as f:f.write(PATCH)
 with (runtime/'catalog.py').open('a') as f:f.write('\nTASKS["general"]='+repr({'id':'general','language':args.language,'contract':task,'starter':{},'driver':'','reference':''})+'\n')
 i=job/'isolation'
 for n in ['home','config','data','state','instance','models','runtime/bin']:(i/n).mkdir(parents=True)
 subprocess.run(['cp','-a','--reflink=always',str(TEMPLATE/'isolation/models')+'/.',str(i/'models')],check=True)
 for n in ['npm','node-v22.23.4-linux-x64']:(i/'runtime'/n).symlink_to(BASE/n,target_is_directory=True)
 for src,dst in [(TEMPLATE/'isolation/rig',i/'rig'),(TEMPLATE/'isolation/runtime/bin/pi',i/'runtime/bin/pi')]:dst.write_text(src.read_text().replace(old,new));dst.chmod(0o700)
 paths=json.load(open(TEMPLATE/'paths.json'));paths.update(output=str(job),isolation=str(i),runtime=str(i/'runtime'),backup=str(job/'checkpoints'),stamp=ident,unit='fleet-programming-'+ident);save(runtime/'paths.json',paths)
 save(job/'task.json',{'id':ident,'source':str(source),'language':args.language,'task':task,'profile':profile,'source_before':before,'trusted_check_sha256':hashlib.sha256(check.encode()).hexdigest(),'acceptance_note':'Separate operator acceptance' if args.acceptance_file else 'Same frozen operator check rerun independently; not hidden coverage','state':'queued','project_tests_only':args.project_tests_only})
 launcher=P(__file__).resolve();subprocess.run(['systemd-run','--user','--unit',paths['unit'],'--property=MemoryMax=8G','--property=TasksMax=1024','--property=Nice=5','--setenv=XDG_RUNTIME_DIR=/run/user/1000','--setenv=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus','/usr/bin/python3','-B',str(launcher),'_run',ident],check=True)
 print('Task started: '+ident+'\nStatus: fleet-programming status '+ident+'\nWorkspace: '+str(job/'runs/work-h5.5/seats/developer/project'))
def run(ident):
 job=STATE/'jobs'/ident;meta=json.load(open(job/'task.json'));lock=(STATE/'runtime.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX)
 sys.path.insert(0,str(job/'runtime-source'));import main as m
 signal.signal(signal.SIGTERM,m.request_stop);signal.signal(signal.SIGINT,m.request_stop)
 try:
  meta['state']='waiting_for_resources';save(job/'task.json',meta);m.healthy_wait();meta['state']='running';save(job/'task.json',meta);m.init_services();threading.Thread(target=m.monitor,daemon=True).start()
  # Create the approved per-model alias in this task's isolated model registry.
  m.api('/api/create',{'model':'framework-qwen122','from':'qwen3.5:122b','parameters':{'num_ctx':32768,'num_predict':4096,'temperature':.2,'top_p':.95,'top_k':40},'stream':False});m.MODELS['q122']='framework-qwen122'
  import orchestrator;orchestrator.MODELS['q122']='framework-qwen122'
  m.atomic(job/'models.json',m.model_config('bootstrap',[('q122',42)]))
  class ProjectCase(m.Case):
   def add_seat(self,*a,**kw):
    kw['files']=['README.md'];return super().add_seat(*a,**kw)
  c=ProjectCase('work-h5.5','general',{'developer':'q122'},42,1,0,'general-coding',seed_project=job/'input');r=c.run()
  unchanged=inventory(P(meta['source']))==meta['source_before'];r['source_original_unchanged']=unchanged
  if r.get('complete'):
   audit=c.audit(c.seats['developer']['root'],'operator-final');r['complete']=r['complete'] and audit['passed'] and unchanged
  save(job/'RESULT.json',r);meta['state']='complete' if r.get('complete') else 'needs_attention';meta['result']=str(job/'RESULT.json');save(job/'task.json',meta)
 except BaseException as exc:
  meta.update(state='needs_attention',error=str(exc));save(job/'task.json',meta);raise
 finally:
  subprocess.run(['systemctl','--user','stop',m.INFER_UNIT],capture_output=True)
  try:m.native('daemon','stop',timeout=90)
  except Exception:pass
  lock.close()
def main():
 p=argparse.ArgumentParser(description='Guarded Python/C++ coding in a disposable copy; no automatic merge or Unity changes');s=p.add_subparsers(dest='action',required=True)
 q=s.add_parser('new');q.add_argument('--language',choices=['python','cpp'],required=True);q.add_argument('--project',required=True);q.add_argument('--task-file',required=True);q.add_argument('--check-file');q.add_argument('--acceptance-file');q.add_argument('--project-tests-only',action='store_true',help='Use the frozen --check-file for the entire project test/build policy instead of additional unittest/standalone-test auto-discovery')
 for a in ['status','result','_run']:q=s.add_parser(a);q.add_argument('id')
 a=p.parse_args();STATE.mkdir(parents=True,exist_ok=True)
 if a.action=='new':prepare(a)
 elif a.action=='_run':
  if not re.fullmatch(r'[0-9]{8}-[0-9]{6}-[a-f0-9]{6}',a.id):raise ValueError('Invalid task ID')
  run(a.id)
 else:
  if not re.fullmatch(r'[0-9]{8}-[0-9]{6}-[a-f0-9]{6}',a.id):raise ValueError('Invalid task ID')
  job=STATE/'jobs'/a.id;meta=json.loads((job/'task.json').read_text());result=json.loads((job/'RESULT.json').read_text()) if (job/'RESULT.json').exists() else {}
  print(json.dumps({'id':a.id,'state':meta['state'],'language':meta['language'],'workspace':str(job/'runs/work-h5.5/seats/developer/project'),'passed':result.get('complete'),'original_unchanged':result.get('source_original_unchanged'),'error':meta.get('error') or result.get('failure'),'result_file':str(job/'RESULT.json') if result else None},indent=2))
if __name__=='__main__':
 try:main()
 except Exception as exc:print('Task launcher: '+str(exc),file=sys.stderr);sys.exit(1)
