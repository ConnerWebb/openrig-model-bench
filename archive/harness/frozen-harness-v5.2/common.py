import pathlib,json,time,subprocess,hashlib,os,tempfile,resource,sys,math
R=pathlib.Path(__file__).resolve().parent;P=json.load(open(R/'paths.json'));O=pathlib.Path(P['output']);I=pathlib.Path(P['isolation']);CLI=str(I/'rig')
HARNESS_REVISION='h5.2'
def atomic(p,x):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True);fd,name=tempfile.mkstemp(prefix=p.name+'.tmp-',dir=p.parent);tmp=pathlib.Path(name)
 with os.fdopen(fd,'w') as f:f.write(json.dumps(x,indent=2))
 os.replace(tmp,p)
def event(kind,**x):
 with (O/'events.jsonl').open('a') as f:f.write(json.dumps({'at':time.time(),'kind':kind,**x})+'\n')
def digest(root):
 h=hashlib.sha256();total=0
 for f in sorted(pathlib.Path(root).rglob('*')):
  rel=f.relative_to(root)
  # Every artifact, including hidden files, participates in the completion hash.
  if f.is_symlink():raise ValueError('No symlink artifacts')
  if not f.is_file() and not f.is_dir():raise ValueError('Special files are not supported artifacts')
  if f.is_file():
   if f.stat().st_size>16*2**20:raise ValueError('Artifact too large')
   total+=f.stat().st_size
   if total>64*2**20:raise ValueError('Project too large')
   h.update(str(rel).encode()+b'\0'+f.read_bytes())
 return h.hexdigest()
def native(*args,timeout=90):
 r=subprocess.run([CLI,*map(str,args)],capture_output=True,text=True,timeout=timeout)
 if r.returncode:raise RuntimeError((r.stderr+r.stdout)[-4000:])
 return json.loads(r.stdout)
def snapshot():
 m={line.split(':')[0]:int(line.split()[1])*1024 for line in pathlib.Path('/proc/meminfo').read_text().splitlines()};v={s[0]:int(s[1]) for l in pathlib.Path('/proc/vmstat').read_text().splitlines() if (s:=l.split())[0] in ['pswpin','pswpout']};gpu={}
 for p in pathlib.Path('/sys/class/drm').glob('card[0-9]/device/mem_info_*'):
  try:gpu[p.name]=int(p.read_text())
  except Exception:pass
 return {'at':time.time(),'available':m['MemAvailable'],'system_used':m['MemTotal']-m['MemAvailable'],'swap_used':m['SwapTotal']-m['SwapFree'],**v,**gpu}
def sandbox(root,argv,input=None,writable=False,mounts=(),timeout=90,memory='2G',network_local=False):
 root=pathlib.Path(root).resolve();cmd=['/usr/bin/bwrap','--unshare-all','--uid','0','--gid','0','--new-session','--die-with-parent','--clearenv','--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64','--proc','/proc','--dev','/dev','--tmpfs','/dev/shm','--tmpfs','/tmp','--dir','/work','--bind' if writable else '--ro-bind',str(root),'/work']
 # Fedora's /usr/bin/ld resolves through this one alternatives link. Mount only
 # the linker target; the rest of the host /etc remains unavailable.
 cmd+=['--dir','/etc','--dir','/etc/alternatives','--ro-bind','/usr/bin/ld.bfd','/etc/alternatives/ld']
 # Both advertised and short paths resolve to the same protected project mount.
 cmd+=['--dir',str(root.parent),'--symlink','/work',str(root)]
 for name in ['TASK.txt','PUBLIC_CASES.json','PUBLIC_DRIVER.py','PUBLIC_DRIVER.cpp','public-inputs','rig.yaml','agents']:
  if (root/name).exists():cmd+=['--ro-bind',str(root/name),'/work/'+name]
 for src,dest,write in mounts:cmd+=['--bind' if write else '--ro-bind',str(src),dest]
 cmd+=['--chdir','/work','--setenv','HOME','/tmp','--setenv','PATH','/usr/bin:/bin','--setenv','LC_ALL','C.UTF-8','--setenv','PYTHONDONTWRITEBYTECODE','1','--setenv','ASAN_OPTIONS','detect_leaks=1:abort_on_error=1','--setenv','UBSAN_OPTIONS','halt_on_error=1:print_stacktrace=1','--setenv','TSAN_OPTIONS','halt_on_error=1:exitcode=66']
 if network_local:cmd+=['--cap-add','CAP_NET_ADMIN','/bin/sh','-c','/usr/sbin/ip link set lo up && exec "$@"','fixture',*argv]
 else:cmd+=list(map(str,argv))
 cmd=['/usr/bin/systemd-run','--user','--scope','--quiet','--collect','--property=MemoryMax='+memory,'--property=MemorySwapMax=0','--property=TasksMax=128','--property=RuntimeMaxSec='+str(timeout+5),*cmd]
 def limits():resource.setrlimit(resource.RLIMIT_FSIZE,(32*2**20,32*2**20));resource.setrlimit(resource.RLIMIT_CPU,(timeout,timeout))
 begin=time.monotonic()
 with tempfile.TemporaryFile() as stdout,tempfile.TemporaryFile() as stderr:
  try:
   host_env=os.environ.copy();host_env['XDG_RUNTIME_DIR']='/run/user/'+str(os.getuid());host_env['DBUS_SESSION_BUS_ADDRESS']='unix:path='+host_env['XDG_RUNTIME_DIR']+'/bus';proc=subprocess.run(cmd,env=host_env,input=input.encode() if isinstance(input,str) else input,stdout=stdout,stderr=stderr,timeout=timeout+10,preexec_fn=limits);code=proc.returncode
  except subprocess.TimeoutExpired:code=124
  stdout.seek(0);stderr.seek(0);out=stdout.read(2**20).decode(errors='replace');err=stderr.read(20000).decode(errors='replace')
 elapsed=time.monotonic()-begin
 return {'exit':code,'stdout':out,'stderr':err,'seconds':elapsed,'timed_out':code==124 or (code==-15 and elapsed>=timeout)}
def write_reference(task,root):
 root=pathlib.Path(root);root.mkdir(parents=True,exist_ok=True)
 if task['id']=='py-team':
  from catalog import TEAM_NORMALIZE,TEAM_DEDUP,TEAM_FACADE
  for n,c in [('validation.py',TEAM_NORMALIZE),('storage.py',TEAM_DEDUP),('ledger.py',TEAM_FACADE)]:(root/n).write_text(c)
 elif task['id']=='py-normalizer':(root/'validation.py').write_text(task['reference'])
 elif task['id']=='cpp-team':
  from catalog import TASKS
  for n,c in [('parser.hpp',TASKS['cpp-csv']['reference']),('cache.hpp',TASKS['cpp-lru']['reference']),('stats.hpp',TASKS['cpp-stats']['reference']),('solution.hpp',task['starter']['solution.hpp'])]:(root/n).write_text(c)
 elif task['id']=='py-refactor':(root/'engine.py').write_text(task['reference']);(root/'ledger.py').write_text('from engine import process\n')
 elif task['id']=='cpp-stats':
  (root/'include').mkdir(exist_ok=True);(root/'src').mkdir(exist_ok=True);
  for n,c in task['reference_files'].items():f=root/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(c)
 else:(root/('solution.py' if task['language']=='python' else 'solution.hpp')).write_text(task['reference'])
 (root/'README.md').write_text('Reference implementation for harness qualification only.\n');(root/'test_reference.py').write_text('assert True\n')
def compile_cpp(root,task,control,mode='normal'):
 h=digest(root);folder=pathlib.Path(control)/'build'/h/mode;folder.mkdir(parents=True,exist_ok=True);program=folder/'program';meta=folder/'compile.json'
 if program.is_file() and meta.exists():return program,json.load(open(meta))
 driver=folder/'driver.cpp';driver.write_text(task['driver']);flags=['-fuse-ld=bfd','-std=c++20','-O1','-g','-pthread','-fno-omit-frame-pointer']
 if mode=='asan':flags+=['-fsanitize=address,undefined']
 if mode=='tsan':flags+=['-fsanitize=thread']
 mounts=[(folder,'/build',True),(driver,'/build/driver.cpp',False)]
 if task['id']=='cpp-stats':
  proj=folder/'project';proj.mkdir(exist_ok=True);cm=proj/'CMakeLists.txt';cm.write_text('cmake_minimum_required(VERSION 3.20)\nproject(check LANGUAGES CXX)\nadd_subdirectory(/work candidate)\nadd_executable(check /build/driver.cpp)\ntarget_link_libraries(check PRIVATE stats)\n');mounts.append((cm,'/build/project/CMakeLists.txt',False));commands='cmake -S /build/project -B /build/cmake -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_CXX_FLAGS='+__import__('shlex').quote(' '.join(flags))+' && cmake --build /build/cmake -j2 && cp /build/cmake/check /build/program';args=['/bin/sh','-c',commands]
 else:args=['/usr/bin/clang++',*flags,'-I/work','-I/work/include','/build/driver.cpp','-o','/build/program']
 result=sandbox(root,args,mounts=mounts,timeout=120);atomic(meta,result);return program,result
def run_checks(root,task,control,seed=1,private=False,mode='normal',case_limit=None):
 from cases import cases,equivalent
 control=pathlib.Path(control);control.mkdir(parents=True,exist_ok=True);h=digest(root);rows=[];total=cases(task['id'],seed,private)
 if case_limit:total=total[:case_limit]
 if task['language']=='cpp':
  program,compile_result=compile_cpp(root,task,control,mode)
  if compile_result['exit']!=0 or not program.exists():return {'passed':False,'hash':h,'count':0,'compile':compile_result,'mode':mode,'private':private,'error':'Compilation failed'}
 else:program=None
 for index,(inp,want) in enumerate(total):
  argv=['/usr/bin/python3','-I','-X','pycache_prefix=/tmp/pycache','-c',task['driver']] if task['language']=='python' else ['/program'];mounts=() if program is None else [(program,'/program',False)];data=json.dumps(inp) if task['language']=='python' else inp
  result=sandbox(root,argv,input=data,mounts=mounts,timeout=40,network_local=task['id']=='py-http')
  try:actual=json.loads(result['stdout']);ok=result['exit']==0 and equivalent(actual,want)
  except Exception:actual=None;ok=False
  rows.append({'case':index,'passed':ok,'exit':result['exit'],'seconds':result['seconds'],'input':inp,'expected':want,'actual':actual,'stderr':result['stderr']})
 passed=bool(rows) and all(r['passed'] for r in rows) and digest(root)==h
 return {'passed':passed,'hash':h,'count':len(rows),'mode':mode,'private':private,'rows':rows}
def feedback(result,private=False):
 # Hidden test inputs/expected outputs remain in operator evidence, not agent tool responses.
 return {'passed':result['passed'],'count':result.get('count',0),'hash':result['hash'],'mode':result['mode'],'compile':result.get('compile'),'failures':[{'case':r['case'],**({'input':r['input']} if not private else {}),'actual':r['actual'],'expected':r['expected'] if not private else 'independent contract check failed','stderr':r['stderr'][-3000:]} for r in result.get('rows',[]) if not r['passed']][:8]}
def public_examples(task_id):
 from cases import cases
 out=[]
 for inp,want in cases(task_id,71,False):
  item={'driver_input':inp,'expected':want}
  if task_id=='cpp-csv':
   raw=inp[1:-1];decoded='';i=0
   while i<len(raw):
    if raw[i]=='\\' and i+1<len(raw):i+=1
    decoded+=raw[i];i+=1
   item['api_input_csv']=decoded
  elif task_id=='py-csv':item['api_input_csv']=inp['csv']
  elif task_id=='cpp-buffer':
   values=list(map(int,inp.split()));n,k=values[:2];item['api_operations']={'construct_size':n,'initial_values':values[2:],'deep_copy_check':'Copy buffer, then XOR ONLY THE COPY first byte with255 to test independence. Not constructor behavior.','resize_to':k,'then':'Move original; moved-from size0; bounds access must throw.'}
  out.append(item)
 return out
def publish_public(task,root):
 root=pathlib.Path(root);examples=public_examples(task['id']);directory=root/'public-inputs';directory.mkdir(exist_ok=True)
 for i,item in enumerate(examples):
  if 'api_input_csv' in item:
   name=f'case-{i:02d}.csv';(directory/name).write_text(item['api_input_csv'],encoding='utf-8')
  else:
   name=f'case-{i:02d}.json';(directory/name).write_text(json.dumps(item['driver_input'],ensure_ascii=False,indent=2))
  item['input_file']='public-inputs/'+name
 (root/'PUBLIC_CASES.json').write_text(json.dumps(examples,ensure_ascii=False,indent=2));(root/('PUBLIC_DRIVER.py' if task['language']=='python' else 'PUBLIC_DRIVER.cpp')).write_text(task['driver'])
def authored_tests(root):
 root=pathlib.Path(root);py=sorted(p for p in root.rglob('test*.py') if not any(s.startswith('.') for s in p.relative_to(root).parts));cpp=sorted(p for p in root.rglob('*test*.cpp') if not any(s.startswith('.') for s in p.relative_to(root).parts));logs=[];deadline=time.monotonic()+120
 if py:
  for p in py:
   remaining=int(deadline-time.monotonic())
   if remaining<=0:logs.append({'exit':124,'stderr':'Aggregate authored-test deadline reached','timed_out':True});break
   code='import sys,unittest;sys.path.insert(0,"/work");s=unittest.defaultTestLoader.discover('+repr('/work/'+str(p.parent.relative_to(root)))+',pattern='+repr(p.name)+');r=unittest.TextTestRunner(verbosity=2).run(s);print("TEST_DISCOVERY_COUNT",r.testsRun);sys.exit(not(r.wasSuccessful() and r.testsRun>0))'
   r=sandbox(root,['python3','-I','-X','pycache_prefix=/tmp/pycache','-c',code],timeout=remaining);r['file']=str(p.relative_to(root));logs.append(r)
 if cpp:
  import shlex
  for p in cpp:
   remaining=int(deadline-time.monotonic())
   if remaining<=0:logs.append({'exit':124,'stderr':'Aggregate authored-test deadline reached','timed_out':True});break
   args=['clang++','-fuse-ld=bfd','-std=c++20','-pthread','-I/work','-I/work/include','/work/'+str(p.relative_to(root))]
   if (root/'src/stats.cpp').exists():args+=['/work/src/stats.cpp']
   r=sandbox(root,['/bin/sh','-c',shlex.join(args+['-o','/tmp/own-test'])+' && /tmp/own-test'],timeout=remaining);r['file']=str(p.relative_to(root));logs.append(r)
 if not logs:return {'passed':False,'exit':1,'stderr':'No saved tests found. Save test_submission.py with unittest.TestCase methods named test_* (pytest unavailable), or standalone C++ test*.cpp with main; then run_tests.'}
 return {'passed':all(r['exit']==0 for r in logs),'runs':logs,'exit':next((r['exit'] for r in logs if r['exit']!=0),0),'stdout':'\n'.join(r.get('stdout','') for r in logs),'stderr':'\n'.join(r.get('stderr','') for r in logs),'hint':'All listed saved tests are graded. Python uses stdlib unittest, not pytest; zero tests fails. Fix obsolete/broken authored tests as well as code.'}
def reference_tests(task,root):
 root=pathlib.Path(root);code=''
 if task['language']=='python':
  if task['id']=='py-csv':code="import unittest,tempfile,pathlib,solution\nclass CorrectReference(unittest.TestCase):\n def test_decimal(self):\n  with tempfile.TemporaryDirectory() as d:\n   p=pathlib.Path(d)/'x.csv';p.write_text('category,amount\\na,0.10\\na,0.20\\n');self.assertEqual(solution.aggregate(str(p)),{'a':'0.30'})\n"
  elif task['id'] in ['py-team','py-refactor']:code="import unittest,ledger\nclass CorrectReference(unittest.TestCase):\n def test_contract(self):\n  r=[{'id':' x ','category':' a ','cents':5}];self.assertEqual(ledger.process(r)['totals'],{'a':5});self.assertEqual(r[0]['id'],' x ');self.assertEqual(ledger.process([]),{'events':[],'totals':{}})\n"
 else:
  body='#include "solution.hpp"\n#include <cassert>\nint main(){Buffer a(2);a[0]=17;auto b=a;b[0]=23;assert(a[0]==17);a.resize(3);assert(a[2]==0);}' if task['id']=='cpp-buffer' else '#include "solution.hpp"\n#include <cassert>\n#include <sstream>\nint main(){std::istringstream i("category,amount\\na,3\\n");assert(aggregate(i).at("a")==3);LruCache c(1);c.put(1,"x");std::string out;assert(c.get(1,out)&&out=="x");RunningStats s;s.add(2);s.add(4);assert(s.mean()==3&&s.variance()==1);}'
  code='import unittest,tempfile,pathlib,subprocess\nclass CorrectReference(unittest.TestCase):\n def test_library(self):\n  with tempfile.TemporaryDirectory() as d:\n   p=pathlib.Path(d);(p/"check.cpp").write_text('+repr(body)+');r=subprocess.run(["clang++","-fuse-ld=bfd","-std=c++20","-pthread","-I/work",str(p/"check.cpp"),"-o",str(p/"check")],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(subprocess.run([str(p/"check")]).returncode,0)\n'
 if code:
  for f in root.glob('test_reference.py'):f.unlink()
  (root/'test_submission.py').write_text(code)
