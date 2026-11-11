"""Experimental OpenRig broker. Only native own-seat work and isolated files/tools."""
import json,pathlib,os,sys,time,fcntl,hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from common import *
from catalog import TASKS
class Broker:
 def __init__(self,root,identity):
  self.root=pathlib.Path(root).resolve();self.control=self.root.parent/'control';self.file=self.control/'job.json';self.job=json.load(open(self.file));self.identity=identity
  if self.job['identity']!=identity or pathlib.Path(self.job['project']).resolve()!=self.root:raise ValueError('Unrecognized seat/project identity')
  self.role=self.job['role'];self.authority=self.job['authority']
 def save(self):atomic(self.file,self.job)
 def h(self):return digest(self.root)
 def log(self,op,**data):
  with (self.control/'tools.jsonl').open('a') as f:f.write(json.dumps({'at':time.time(),'role':self.role,'op':op,**data})+'\n')
 def owner(self):
  q=self.job.get('assignment')
  if not q:raise ValueError('No stage assigned')
  row=native('queue','show',q,'--full','--json')
  if row.get('destinationSession')!=self.identity or row['state'] in ['done','failed','canceled']:raise ValueError('Assignment is not active and owned by this seat')
  return q
 def path(self,value,write=False):
  p=pathlib.PurePath(value)
  if p.is_absolute():
   if p==pathlib.PurePath('/work'):p=pathlib.PurePath('.')
   elif str(p).startswith('/work/'):p=p.relative_to('/work')
   elif p.is_relative_to(self.root):p=p.relative_to(self.root)
   else:raise ValueError('Only paths inside /work are allowed')
  if '..' in p.parts or any(v.startswith('.') for v in p.parts):raise ValueError('Hidden/traversal paths denied')
  f=self.root/p
  if write and (not p.parts or f.is_dir()):raise ValueError('A file path is required')
  if not f.resolve().is_relative_to(self.root):raise ValueError('Path leaves project')
  if any((self.root/pathlib.Path(*p.parts[:i+1])).is_symlink() for i in range(len(p.parts))):raise ValueError('Symlinks denied')
  if write:
   self.owner()
   if self.authority!='developer' or str(p) in ['TASK.txt','PUBLIC_CASES.json','PUBLIC_DRIVER.py','PUBLIC_DRIVER.cpp','rig.yaml','RESULT.md'] or p.parts[0]=='public-inputs':raise ValueError('Role/path is read-only')
   allowed=self.job.get('write_paths')
   if allowed is not None and not any(str(p)==v or (v.endswith('/') and str(p).startswith(v)) for v in allowed):raise ValueError('Path not assigned to this seat')
  return f
 def close(self,resolution):
  q=self.owner();r=native('queue','update',q,'--state','done','--closure-reason','no-follow-on','--resolution',resolution,'--note','Guarded exact-source stage hash='+self.h(),'--json');self.job['closed']={'qid':q,'resolution':resolution,'hash':self.h(),'at':time.time()};self.job['phase']='idle';self.save();return r
 def tested(self):
  r=self.job.get('tests',{})
  if not r.get('passed') or r.get('hash')!=self.h() or r.get('qid')!=self.job.get('assignment'):raise ValueError('Fresh passing fixed public checks required for this exact artifact and assignment')
 def required(self):
  for name in self.job.get('required_files',[]):
   f=self.root/name
   if not f.is_file() or not f.stat().st_size or f.is_symlink():raise ValueError('Missing required file '+name)
 def dispatch(self,op,p):
  if op=='status':return {'role':self.authority,'actual_role':self.role,'project_kind':'programming-campaign','coordination':'staged','phase':self.job['phase'],'state':self.job['state'],'hash':self.h(),'assignment':self.job.get('assignment'),'write_paths':self.job.get('write_paths'),'harness_revision':HARNESS_REVISION,'workflow_reference':self.job.get('workflow_reference',False),'identity':self.identity,'test_framework':'stdlib unittest.TestCase/test_*; pytest unavailable; C++ standalone *test*.cpp or unittest wrapper'}
  if op in ['get_task','claim_task']:
   if not self.job.get('assignment'):return {'assignment':None}
   q=self.owner();row=native('queue','show',q,'--full','--json')
   if op=='get_task' or row['state'] in ['in-progress','claimed']:return row
   return native('queue','claim',q,'--json')
  if op in ['finish_stage','submit_plan','finish_task']:
   closed=self.job.get('closed',{})
   if closed.get('qid')==self.job.get('assignment') and closed.get('hash')==self.h():
    row=native('queue','show',self.job['assignment'],'--full','--json')
    expected=(op=='finish_stage' and closed.get('resolution') in ['Implementation ready','REVIEW_APPROVED','REVIEW_REJECTED']) or (op=='submit_plan' and closed.get('resolution')=='PLAN_READY') or (op=='finish_task' and self.job.get('state')=='complete')
    if row['state']=='done' and expected:return {'closed':True,'already_closed':True,'resolution':closed['resolution'],'hash':closed['hash'],'complete':self.job.get('state')=='complete'}
  if op=='read':
   f=self.path(p['path']);offset=max(0,int(p.get('offset',1))-1);n=min(250,max(1,int(p.get('limit',120))));return {'text':'\n'.join(f.read_text().splitlines()[offset:offset+n])[:40000]}
  if op=='ls':return [{'name':f.name,'directory':f.is_dir()} for f in sorted(self.path(p.get('path','')).iterdir()) if not f.name.startswith('.')][:200]
  if op in ['write','edit','append']:
   f=self.path(p['path'],True);s=p['content'] if op=='write' else (f.read_text() if f.exists() else '')
   if op=='append':s+=p['content']
   if op=='edit':
    old=p['oldText']
    if not old or s.count(old)!=1:raise ValueError('Exact edit anchor must occur once')
    s=s.replace(old,p['newText'],1)
   if len(s.encode())>100000:raise ValueError('File operation exceeds limit')
   f.parent.mkdir(parents=True,exist_ok=True);fd,name=tempfile.mkstemp(prefix=f.name+'.write-',dir=f.parent)
   with os.fdopen(fd,'w') as stream:stream.write(s)
   os.replace(name,f);return {'saved':p['path']}
  if op=='run':
   self.owner()
   if len(p['command'])>10000:raise ValueError('Command exceeds limit')
   result=sandbox(self.root,['/bin/sh','-c',p['command']],writable=self.authority=='developer' and self.job.get('write_paths') is None,timeout=90)
   out=(result['stdout']+result['stderr'])[-40000:];key=hashlib.sha256(json.dumps([p['command'],self.h(),result['exit'],out]).encode()).hexdigest();last=self.job.get('last_command',{});count=last.get('count',0)+1 if last.get('key')==key else 1;self.job['last_command']={'key':key,'count':count};self.save()
   return {'exit':result['exit'],'output':out,'timed_out':result.get('timed_out',False),'seconds':result['seconds'],'unchanged_repetitions':count,'stalled':count>=6,'next':'Command exit codes are test evidence, not tool transport errors. Fix the implementation or your authored test; use run_tests for fixed public checks and exact-source receipts. Repeating an identical command without changing the artifact is not progress.' if result['exit'] or count>=3 else 'Use run_tests then finish_stage when ready.'}
  if op=='run_tests':
   q=self.owner();before=self.h();task=TASKS[self.job['task']];r=run_checks(self.root,task,self.control,seed=71,private=False);fixed_passed=r['passed'];own=authored_tests(self.root) if self.job.get('authored_tests_required',True) else {'passed':True,'note':'Frozen reviewer probe'};r['authored_tests']=own;r['passed']=r['passed'] and own['passed'] and before==self.h();self.job['tests']={'passed':r['passed'],'hash':self.h(),'qid':q,'count':r.get('count',0)};self.save();atomic(self.control/('public-'+str(time.time_ns())+'.json'),r);out=feedback(r);out['fixed_public_passed']=fixed_passed;out['authored_tests']=own;out['missing_required_files']=[n for n in self.job.get('required_files',[]) if not (self.root/n).is_file() or not (self.root/n).stat().st_size];out['next_action']=('save_required_files_then_rerun_tests' if out['missing_required_files'] else 'finish_stage' if self.authority=='developer' else 'review_decision' if self.authority=='reviewer' else 'acceptance') if r['passed'] else 'repair_code_or_authored_tests_then_run_tests';return out
  if op=='turn_settled':
   if self.job['state']=='active' and self.job['phase']!='idle':self.job['turn_settled_at']=time.time();self.save()
   return {'recorded':True}
  if op=='submit_plan':
   self.owner()
   if self.authority!='lead' or self.job['phase']!='planning' or not 1<=len(p.get('steps',[]))<=12:raise ValueError('Planning seat only; 1–12 concrete steps')
   self.job['plan']=p['steps'];self.save();self.close('PLAN_READY');return {'plan_submitted':True}
  if op=='review_decision':
   self.owner()
   if self.authority!='reviewer':raise ValueError('Independent reviewer only')
   if p['approved']:
    if p.get('issues'):raise ValueError('Approval must not contain issues')
    self.required();self.tested()
   self.job['review']={'approved':p['approved'],'issues':p.get('issues',[]),'hash':self.h(),'qid':self.job['assignment']};self.save();return self.job['review']
  if op=='finish_stage':
   self.owner()
   if self.authority=='developer':self.required();self.tested();resolution='Implementation ready'
   elif self.authority=='reviewer':
    r=self.job.get('review',{})
    if r.get('qid')!=self.job['assignment'] or r.get('hash')!=self.h():raise ValueError('Record exact-source review_decision first')
    resolution='REVIEW_APPROVED' if r['approved'] else 'REVIEW_REJECTED'
   else:raise ValueError('Planner uses submit_plan; finalizer uses finish_task')
   self.close(resolution);return {'closed':True,'resolution':resolution,'hash':self.h()}
  if op=='acceptance':
   self.owner()
   if self.authority!='lead' or self.job['phase']!='finalizing':raise ValueError('Finalizer only')
   r=run_checks(self.root,TASKS[self.job['task']],self.control,seed=self.job['seed'],private=True);atomic(self.control/'final-independent.json',r);self.job['acceptance']={'passed':r['passed'],'hash':r['hash']};self.save();return feedback(r,private=True)
  if op=='finish_task':
   self.owner();self.required();self.tested();h=self.h()
   if self.authority!='lead' or self.job['phase']!='finalizing' or self.job.get('review_hash')!=h or not self.job.get('review_approved'):raise ValueError('Exact-source independently approved finalization required')
   a=self.job.get('acceptance',{})
   if not a.get('passed') or a.get('hash')!=h:raise ValueError('Fresh independent acceptance required')
   self.job['state']='complete';self.job['completed_hash']=h;self.save();self.close('PASS: independently validated exact-artifact completion');return {'complete':True,'hash':h}
  if op=='rig_command':
   a=p.get('args',[])
   if a and a[0]=='whoami':return native('whoami','--json')
   if a[:2]==['queue','show'] and len(a)>2 and a[2]==self.job.get('assignment'):return native('queue','show',a[2],'--full','--json')
   raise ValueError('Only own task inspection allowed; use structured stage tools')
  if op=='halt':
   closed=self.job.get('closed',{})
   if closed.get('qid')==self.job.get('assignment') and closed.get('hash')==self.h():
    row=native('queue','show',self.job['assignment'],'--full','--json')
    if row['state']=='done':return {'stopped':False,'already_closed':True,'note':'A late deadline cannot invalidate verified closure'}
   q=self.job.get('assignment');self.job['state']='failed';self.job['failure']=p.get('reason','turn budget');self.save()
   try:self.close('STAGE_FAILED: '+self.job['failure'])
   except Exception:pass
   return {'stopped':True}
  raise ValueError('Controller owns delegation and lifecycle; operation unavailable')
def main():
 root=pathlib.Path(sys.argv[1]);control=root.parent/'control'
 with (control/'lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);b=Broker(root,os.environ.get('OPENRIG_SESSION_NAME',''));request=json.load(sys.stdin);op=request['op']
  try:
   if op!='status' and request.get('assignment')!=b.job.get('assignment'):raise ValueError('Stale assignment: this tool call belongs to a previous stage')
   r=b.dispatch(op,request.get('params',{}));b.log(op,ok=True,assignment=b.job.get('assignment'));print(json.dumps({'ok':True,'result':r}))
  except Exception as e:b.log(op,ok=False,error=str(e));print(json.dumps({'ok':False,'error':str(e)[:3000]}))
if __name__=='__main__':main()
