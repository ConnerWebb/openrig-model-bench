"""Private fleet tool broker. No daemon, host shell, or model-supplied identity."""
from pathlib import Path
import contextlib,fcntl,hashlib,json,os,resource,subprocess,sys,tempfile,time
CLI='/home/cow/Documents/Codex/2026-11-05/referenced-chatgpt-conversation-this-is-an/outputs/openrig-programming-20261109-235342/isolation/rig'
PROTECTED={'TASK.txt','AGENTS.md','rig.yaml','agents','RESULT.md'}
FILE_CODE=r'''
import json,os,sys,pathlib
r=json.loads(sys.argv[1]);root=pathlib.Path('/work');p=root/r.get('path','.')
if not p.resolve().is_relative_to(root):raise ValueError('Path leaves project')
if r['op']=='ls':print(json.dumps([{'name':x.name,'directory':x.is_dir()} for x in sorted(p.iterdir())][:200]))
elif r['op']=='read':
 s=p.read_text();a=max(0,int(r.get('offset',1))-1);b=min(500,int(r.get('limit',200)));print('\n'.join(s.splitlines()[a:a+b])[:50000])
elif r['op']=='write':
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.fleet-tmp');tmp.write_text(r['content']);os.replace(tmp,p);print('Saved '+r['path'])
elif r['op']=='edit':
 s=p.read_text();old=r['oldText'];assert old and s.count(old)==1,'oldText must occur exactly once';s=s.replace(old,r['newText'],1);tmp=p.with_name(p.name+'.fleet-tmp');tmp.write_text(s);os.replace(tmp,p);print('Edited '+r['path'])
'''
class Broker:
 def __init__(self,project,identity,rig=None):
  self.root=Path(project).resolve();self.control=self.root.parent/'control';self.file=self.control/'job.json';self.identity=identity;self.rig_impl=rig
  self.job=json.loads(self.file.read_text());assert self.root==Path(self.job['project']).resolve()
  self.role=next((k for k,v in self.job['seats'].items() if v==identity),None)
  if not self.role:raise ValueError('Unknown fleet seat; no authority granted')
 def save(self):
  p=self.file.with_suffix('.tmp');p.write_text(json.dumps(self.job,indent=2)+'\n');p.chmod(0o600);os.replace(p,self.file)
 def event(self,op,detail):
  with (self.control/'events.jsonl').open('a') as f:f.write(json.dumps({'at':time.time(),'role':self.role,'op':op,'detail':detail})+'\n')
 def rig(self,args):
  if self.rig_impl:return self.rig_impl(args)
  r=subprocess.run([CLI,*args],capture_output=True,text=True,timeout=25)
  if r.returncode:raise ValueError((r.stderr+r.stdout)[-2500:])
  try:return json.loads(r.stdout)
  except ValueError:return {'message':r.stdout[-16000:]}
 def unity_module(self):
  import importlib.util
  spec=importlib.util.spec_from_file_location('unity_project',Path(__file__).with_name('unity_project.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
 def coding_module(self):
  import importlib.util
  spec=importlib.util.spec_from_file_location('unity_coding',Path(__file__).with_name('unity_coding.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
 def digest(self):
  if self.job.get('project_kind')=='unity-coding':return self.coding_module().u.digest(self.root)
  if self.job.get('project_kind')=='unity-validation':
   module=self.unity_module();h=hashlib.sha256(module.digest(self.root).encode());report=self.root/'FLEET-ONBOARDING.md'
   if report.is_symlink():raise ValueError('Report symlinks are forbidden')
   if report.exists():h.update(report.read_bytes())
   return h.hexdigest()
  h=hashlib.sha256()
  for p in sorted(self.root.rglob('*')):
   rel=p.relative_to(self.root)
   if any(x.startswith('.') or x=='__pycache__' for x in rel.parts) or rel.parts[0] in PROTECTED or p.suffix=='.pyc':continue
   if p.is_symlink():raise ValueError('Project symlinks are not supported')
   if p.is_file():
    if p.stat().st_size>2**24:raise ValueError('Project file exceeds 16 MiB')
    h.update(str(rel).encode()+b'\0'+p.read_bytes())
  return h.hexdigest()
 def path(self,value,write=False):
  p=Path(value)
  if p.is_absolute():
   p=p.relative_to('/work') if self.job.get('project_kind')=='unity-coding' and p.is_relative_to('/work') else p.relative_to(self.root)
  if '..' in p.parts:raise ValueError('Path leaves project')
  if write and self.job.get('project_kind')=='unity-coding':
   if str(p)=='FLEET-CODING.md':raise ValueError('FLEET-CODING.md is coordinator-generated from actual test evidence. Run run_tests, then finish_stage; do not create it or search for agent folders.')
   module=self.coding_module();manifest=json.loads((self.control/'coding.json').read_text())
   if not module.editable(str(p),manifest):raise ValueError('Denied path '+str(p)+'. Approved writable paths: '+', '.join(manifest['write_paths'])+'. Create the required verification document at its exact listed path using write/edit. Only FLEET-CODING.md is coordinator-generated. Shell commands are read-only.')
  if write and self.job.get('project_kind')=='unity-validation' and str(p)!='FLEET-ONBOARDING.md':raise ValueError('Unity validation permits only FLEET-ONBOARDING.md edits; game code is read-only')
  if write and (self.role!='developer' or any(x.startswith('.') for x in p.parts) or (p.parts and p.parts[0] in PROTECTED)):raise ValueError('Only developer may edit implementation files; control files are protected')
  return str(p)
 def sandbox(self,argv,writable=False,checks=None):
  def cap():
   resource.setrlimit(resource.RLIMIT_AS,(2*2**30,2*2**30));resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_FSIZE,(16*2**20,16*2**20))
  coding=self.job.get('project_kind')=='unity-coding'
  unity=self.job.get('project_kind')=='unity-validation'
  report=self.root/'FLEET-ONBOARDING.md'
  if unity and writable and not report.exists():report.touch()
  cmd=['/usr/bin/bwrap','--unshare-all','--new-session','--die-with-parent','--clearenv','--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/work','--bind' if writable and not unity else '--ro-bind',str(self.root),'/work']
  if coding:cmd+=['--dir',str(self.root.parent),'--symlink','/work',str(self.root)]
  if unity or coding:
   # Generated caches and runtime configuration may contain private identifiers.
   for name in ['Library','Temp','Logs','Obj','obj','UserSettings','.pi']:
    if (self.root/name).is_dir():cmd+=['--tmpfs','/work/'+name]
   if writable and not coding:cmd+=['--bind',str(report),'/work/FLEET-ONBOARDING.md']
  for name in PROTECTED|{'.pi','.agents','.git','.codex','.claude','.openrig'}:
   p=self.root/name
   if p.exists() and not ((unity or coding) and name=='.pi'):cmd+=['--ro-bind',str(p),'/work/'+name]
  if checks:cmd+=['--ro-bind',str(checks),'/checks']
  cmd+=['--chdir','/work','--setenv','HOME','/tmp','--setenv','PATH','/usr/bin:/bin','--setenv','LC_ALL','C.UTF-8','--setenv','PYTHONDONTWRITEBYTECODE','1',*argv]
  with tempfile.TemporaryFile(dir=self.control) as f:
   try:
    r=subprocess.run(cmd,stdout=f,stderr=f,timeout=35,preexec_fn=cap);code=r.returncode
   except subprocess.TimeoutExpired:code=124
   f.seek(0,2);size=f.tell();f.seek(max(0,size-60000));output=f.read().decode(errors='replace')
  return {'exit':code,'output':output,'truncated':size>60000}
 def owner(self,qid):
  r=self.rig(['queue','show',qid,'--full','--json'])
  if r.get('destinationSession')!=self.identity:raise ValueError('Cannot mutate another seat task or the lead parent')
  allowed=[self.job.get('parent')] if self.role=='lead' else self.job.get('children',{}).get(self.role,[])
  if qid not in allowed:raise ValueError('Task is not assigned to this project/role')
  return r
 def current(self):
  if self.role=='lead':return self.job.get('parent')
  for qid in reversed(self.job.get('children',{}).get(self.role,[])):
   if self.rig(['queue','show',qid,'--full','--json']).get('state') not in ['done','failed','canceled']:return qid
  raise ValueError('No active stage assigned; wait for delegation')
 def coding_report(self,complete=False):
  if self.job.get('project_kind')!='unity-coding':return
  rows={role:{k:r.get(k) for k in ['passed','count','hash','source_hash','reused_evidence']} for role,r in self.job.get('tests',{}).items()}
  record={'state':'verified complete' if complete else 'developer tests verified; independent review/completion still required','tests':rows,'review':self.job.get('review'),'acceptance':self.job.get('acceptance'),'artifact_hash':self.digest(),'manual_gameplay':'not run','standalone_player_build':'not run'}
  path=self.root/'FLEET-CODING.md'
  if path.is_symlink():raise ValueError('Generated report cannot be a symlink')
  path.write_text('# Unity coding verification\n\nCoordinator-generated from actual evidence. Reused exact-source test evidence is labeled.\n\n'+json.dumps(record,indent=2)+'\n\nCode executes only in the isolated headless runner. The original project and defaults are preserved.\n')
 def required(self):
  missing=[n for n in self.job['required_files'] if not (self.root/n).is_file() or not (self.root/n).stat().st_size]
  if missing:raise ValueError('Missing deliverables: '+', '.join(missing))
 def tested(self,role):
  r=self.job.get('tests',{}).get(role,{})
  if self.job.get('project_kind')=='unity-coding':
   module=self.coding_module()
   if r.get('harness')!=module.harness_hash() or r.get('policy')!=module.policy_hash(self.control):raise ValueError('Unity evidence needs the current runner and policy')
  if not r.get('passed') or r.get('hash')!=self.digest() or (role!='lead' and r.get('task')!=self.job['children'].get(role,[None])[-1]):raise ValueError('Current implementation needs passing saved tests for '+role)
  return r
 def gate(self):
  self.required();h=self.digest();self.tested('developer');self.tested('reviewer');self.tested('lead')
  if self.job.get('coordination')=='staged' and self.job['tests']['lead'].get('task')!=self.job.get('parent'):raise ValueError('Finalizer needs tests for its own current assignment')
  if self.job.get('project_kind')=='unity-coding' or self.job.get('coordination')=='staged':
   for role,prefix in [('developer','Implementation ready'),('reviewer','REVIEW_APPROVED')]:
    ids=self.job['children'].get(role,[]);closed=self.job.get('closed_stages',{}).get(role,{})
    if not ids or closed.get('closed')!=ids[-1] or closed.get('hash')!=h or not closed.get('outcome','').startswith(prefix):raise ValueError(role+' stage needs successful verified closure; a stopped/denied stage is not completion')
  developer=self.job['children'].get('developer',[])
  if not developer or self.rig(['queue','show',developer[-1],'--full','--json']).get('state')!='done':raise ValueError('Developer stage has not closed')
  r=self.job.get('review',{})
  if not r.get('approved') or r.get('issues') or r.get('hash')!=h:raise ValueError('Independent reviewer approval for this exact implementation is required')
  a=self.job.get('acceptance',{})
  if not a.get('passed') or not a.get('configured_checks') or a.get('hash')!=h:raise ValueError('Independent acceptance checks for current implementation are required')
  reviewer=self.job['children'].get('reviewer',[])
  if not reviewer or r.get('task')!=reviewer[-1] or self.rig(['queue','show',reviewer[-1],'--full','--json']).get('state')!='done':raise ValueError('Reviewer stage has not closed')
  return h
 def checked_inputs(self):
  for rel,expected in self.job.get('input_hashes',{}).items():
   source=self.root/rel
   if source.is_symlink() or not source.resolve().is_relative_to(self.root) or hashlib.sha256(source.read_bytes()).hexdigest()!=expected:raise ValueError('Protected research input changed; a new job and review are required')
 def dispatch(self,op,p):
  a=p.get('args',[]) if op=='rig_command' else []
  readonly=op in ['status','read','ls','get_task','project_info'] or (op=='rig_command' and (a[:1] in [['whoami'],['ps']] or a[:2] in [['queue','show'],['queue','list']]))
  if not readonly and op!='halt':self.checked_inputs()
  if not readonly and op!='halt' and hashlib.sha256((self.root/'TASK.txt').read_bytes()).hexdigest()!=self.job['task_sha256']:raise ValueError('Task changed; a new job and review are required')
  if op=='finish_task' and self.job.get('state')=='complete':
   if self.role!='lead':raise ValueError('Only lead can finish overall task')
   if self.job.get('completed_hash')!=self.digest():raise ValueError('Completed artifact changed; new validation is required')
   return {'already_complete':True,'hash':self.job['completed_hash']}
  if self.job.get('state') in ['complete','needs_attention'] and not readonly and op!='halt':raise ValueError('Job is closed or needs operator attention; no further mutations')
  if time.time()-self.job['created']>self.job.get('timeout',900) and not readonly and op!='halt':raise ValueError('Project time budget exhausted; operator attention required')
  if self.job.get('coordination')=='staged' and self.role=='lead':
   if op=='delegate':raise ValueError('The local controller assigns stages; planner/finalizer must not delegate')
   if op in ['run_tests','acceptance','finish_task'] and self.job.get('phase')!='finalizing':raise ValueError('This operation is only for the finalization phase')
  if op=='submit_plan':
   if self.role!='lead' or self.job.get('coordination')!='staged' or self.job.get('phase')!='planning':raise ValueError('Only the assigned planning stage can submit a plan')
   qid=self.current();self.owner(qid);steps=p.get('steps',[])
   if not 1<=len(steps)<=12 or any(not isinstance(s,str) or not s.strip() or len(s)>800 for s in steps):raise ValueError('Provide 1–12 short plan steps')
   self.rig(['queue','update',qid,'--state','done','--closure-reason','no-follow-on','--resolution','PLAN_READY','--note','Plan submitted for controller-owned handoff','--json'])
   self.job['plan']={'task':qid,'steps':steps,'hash':self.digest()};self.job['plan_submitted']=True;self.save();return {'plan_submitted':True,'next':'Planning task closed. End your turn; the controller assigns implementation.'}
  if op in ['get_task','claim_task']:
   try:qid=self.current()
   except ValueError:return {'assignment':None,'next':'Wait for a stage assignment'}
   if not qid:return {'assignment':None,'next':'Wait for an assigned parent task'}
   self.owner(qid)
   if op=='claim_task':return self.rig(['queue','claim',qid,'--json'])
   return self.rig(['queue','show',qid,'--full','--json'])
  if op=='status':return {'role':self.role,'project_kind':self.job.get('project_kind','python'),'coordination':self.job.get('coordination'),'phase':self.job.get('phase'),'state':self.job.get('state'),'parent':self.job.get('parent'),'children':self.job.get('children'),'tests':self.job.get('tests'),'review':self.job.get('review'),'hash':self.digest()}
  if op in ['read','ls','write','edit']:
   if op in ['write','edit']:self.owner(self.current())
   p={**p,'op':op,'path':self.path(p.get('path','.'),op in ['write','edit'])}
   if self.job.get('project_kind')=='unity-coding':
    if op=='read':p['limit']=min(120,max(1,int(p.get('limit',80))))
    target=self.root/p['path']
    if op=='write' and target.is_file() and target.stat().st_size>12000:raise ValueError('Existing file is large: use edit with one exact small anchor, not write of the whole file. Preserve unrelated content and avoid context overflow.')
   if any(len(str(p.get(k,'')))>60000 for k in ['content','oldText','newText']):raise ValueError('File operation too large')
   code=FILE_CODE
   if self.job.get('project_kind')=='unity-validation' and op in ['write','edit']:
    code=code.replace("tmp=p.with_name(p.name+'.fleet-tmp');tmp.write_text(r['content']);os.replace(tmp,p)","p.write_text(r['content'])").replace("tmp=p.with_name(p.name+'.fleet-tmp');tmp.write_text(s);os.replace(tmp,p)","p.write_text(s)")
   r=self.sandbox(['/usr/bin/python3','-c',code,json.dumps(p)],op in ['write','edit']);self.event(op,{'path':p['path'],'exit':r['exit']});return r
  if op=='run':
   if self.role=='developer':self.owner(self.current())
   if len(p['command'])>8000:raise ValueError('Command too long')
   r=self.sandbox(['/bin/sh','-c',p['command']],self.role=='developer' and self.job.get('project_kind') not in ['unity-validation','unity-coding'])
   if self.job.get('project_kind')=='unity-coding' and 'FLEET-CODING' in p['command']:r['output']='REPORT: FLEET-CODING.md is coordinator-generated from passing test evidence. Use run_tests then finish_stage; do not create it or search hidden folders. Shell commands remain read-only.\n'+r['output']
   self.event(op,{'command':p['command'],'exit':r['exit']});return r
  if op=='project_info' and self.job.get('project_kind')=='unity-coding':
   result=self.coding_module().info(self.root,self.control);result['report_path']='FLEET-CODING.md (coordinator-generated after verified finish_stage; do not write it)'
   evidence=result.get('tests') or {}
   if not evidence.get('passed'):
    import xml.etree.ElementTree as ET
    for suite in evidence.get('suites',[]):
     if not suite.get('xml'):continue
     tree=ET.parse(self.control/suite['xml']).getroot()
     suite['failures']=[{'test':t.get('fullname'),'message':(t.findtext('failure/message') or t.findtext('reason/message') or 'No message')[:2000]} for t in tree.iter('test-case') if t.get('result')!='Passed'][:12]
     fixed=[t for t in tree.iter('test-case') if t.get('fullname','').startswith('FleetSandbox.')]
     suite['operator_checks']={'passed':sum(t.get('result')=='Passed' for t in fixed),'failed':sum(t.get('result')!='Passed' for t in fixed)}
   return result
  if op=='project_info':
   if self.job.get('project_kind')!='unity-validation':raise ValueError('Not a Unity validation project')
   return self.unity_module().info(self.root,self.control)
  if op=='run_tests' and self.job.get('project_kind')=='unity-coding':
   qid=self.current();self.owner(qid);before=self.digest();r=self.coding_module().run_tests(self.root,self.control);h=self.digest()
   receipt={**r,'source_hash':r['hash'],'hash':h,'task':qid,'passed':r['passed'] and before==h};self.job.setdefault('tests',{})[self.role]=receipt;self.save();return receipt
  if op=='run_tests' and self.job.get('project_kind')=='unity-validation':
   qid=self.current();self.owner(qid);before=self.digest();r=self.unity_module().run_tests(self.root,self.control);h=self.digest()
   receipt={**r,'source_hash':r['hash'],'hash':h,'task':qid,'passed':r['passed'] and before==h};self.job.setdefault('tests',{})[self.role]=receipt;self.save();return receipt
  if op=='run_tests':
   qid=self.current();self.owner(qid);before=self.digest();r=self.sandbox(['/usr/bin/python3','-I','-m','unittest','discover','-s','/work','-p','test*.py','-v']);h=self.digest()
   import re
   n=re.search(r'Ran (\d+) tests?',r['output']);passed=r['exit']==0 and bool(n and int(n[1])>0) and before==h
   receipt={**r,'task':qid,'passed':passed,'hash':h,'count':int(n[1]) if n else 0};self.job.setdefault('tests',{})[self.role]=receipt;self.save();return receipt
  if op=='delegate':
   if self.role!='lead':raise ValueError('Only lead delegates stages')
   parent=self.job.get('parent');self.owner(parent);target=p['role']
   if target not in ['developer','reviewer']:raise ValueError('Unknown role')
   if len(self.job['children'].get(target,[]))>=3:raise ValueError('Two-repair limit reached; needs attention')
   if target=='reviewer':
    if self.job.get('project_kind')=='unity-coding':
     ids=self.job['children'].get('developer',[]);closed=self.job.get('closed_stages',{}).get('developer',{})
     if not ids or closed.get('closed')!=ids[-1] or closed.get('hash')!=self.digest() or not closed.get('outcome','').startswith('Implementation ready'):raise ValueError('Developer stage needs successful verified closure before review')
    self.required();self.tested('developer')
    dev=self.job['children'].get('developer',[])
    if not dev or self.rig(['queue','show',dev[-1],'--full','--json']).get('state')!='done':raise ValueError('Wait for developer closure before review')
   existing=self.job['children'].get(target,[])
   if existing and self.rig(['queue','show',existing[-1],'--full','--json']).get('state') not in ['done','failed','canceled']:return {'assigned':existing[-1],'role':target,'already_active':True,'next':'End your turn and wait'}
   instructions=p['instructions']
   if self.job.get('project_kind')=='unity-coding':instructions+='\nOperator workflow: FLEET-CODING.md is generated automatically by verified finish_stage; never create it or search hidden folders. Use small read ranges and edit for existing large files, especially STATUS.md. Inspect only relevant code/spec/docs, call run_tests, update accurate verification docs, revalidate after edits, then finish_stage. Reused exact-source evidence is valid and labeled. Do not reread the full archive or repeat status checks.'
   body=instructions+'\n\nRead TASK.txt for exact requirements. Work only as '+target+'. Use run_tests and finish_stage; do not close the lead parent.'
   item=self.rig(['queue','create','--destination',self.job['seats'][target],'--summary',target+' stage','--body',body,'--json']);qid=item['qitemId'];self.job['children'].setdefault(target,[]).append(qid);self.save()
   self.rig(['queue','block',parent,'--on',qid,'--continuation','Child closed: inspect result, then review/repair or finish task','--json']);return {'assigned':qid,'role':target,'parent_parked':True,'next':'End your turn; native child closure wakes you.'}
  if op=='review_decision':
   if self.role!='reviewer':raise ValueError('Only reviewer records a decision')
   qid=self.current();self.owner(qid)
   if p['approved'] and p.get('issues'):raise ValueError('Approval cannot contain unresolved issues')
   if p['approved']:self.required();self.tested('reviewer')
   self.job['review']={'task':qid,'approved':bool(p['approved']),'issues':p.get('issues',[]),'hash':self.digest()};self.save();return self.job['review']
  if op=='finish_stage':
   if self.role=='lead':raise ValueError('Lead uses finish_task after review and acceptance')
   try:qid=self.current()
   except ValueError:
    done=self.job.get('closed_stages',{}).get(self.role,{})
    if done.get('hash')==self.digest():return {'already_closed':True,**done}
    raise
   self.owner(qid)
   if self.role=='developer':
    if self.job.get('project_kind')=='unity-coding':self.tested('developer');self.coding_report()
    self.required();self.tested('developer');note='Implementation ready; saved tests passed, hash='+self.digest()
   else:
    review=self.job.get('review',{})
    if review.get('hash')!=self.digest():raise ValueError('Record review_decision first')
    note=('REVIEW_APPROVED' if review['approved'] else 'REVIEW_CHANGES_REQUIRED')+' '+json.dumps(review.get('issues',[]))
   r=self.rig(['queue','update',qid,'--state','done','--closure-reason','no-follow-on','--resolution',note,'--note',note,'--json']);self.job.setdefault('closed_stages',{})[self.role]={'closed':qid,'outcome':note,'hash':self.digest()};self.save();self.event(op,{'id':qid,'note':note});return {'closed':qid,'outcome':note}
  if op=='acceptance' and self.job.get('project_kind')=='unity-coding':
   if self.role!='lead':raise ValueError('Lead runs acceptance')
   self.required();self.tested('lead');module=self.coding_module();module.validate(self.root,self.control);r=module.run_tests(self.root,self.control)
   checks={'isolated_Unity_suites':r['passed'],'NUnit_checks_and_baseline_coverage':all(s.get('coverage',False) for s in r['suites']),'no_push_remote':not module.u.git(self.root,'remote').strip(),'source_matches_tested_revision':r['hash']==module.execution_hash(self.root)}
   self.job['acceptance']={'hash':self.digest(),'passed':all(checks.values()),'configured_checks':len(checks),'checks':checks};self.save();return self.job['acceptance']
  if op=='acceptance' and self.job.get('project_kind')=='unity-validation':
   if self.role!='lead':raise ValueError('Lead runs acceptance')
   self.required();self.tested('lead');module=self.unity_module();module.validate(self.root,self.control);r=module.run_tests(self.root,self.control)
   report=(self.root/'FLEET-ONBOARDING.md').read_text();checks=[r['passed'],all(str(s['count']) in report and s['suite'] in report for s in r['suites']),len(report)>500,not module.git(self.root,'remote').strip(),'fleet-project' in report and '```powershell' not in report.lower()]
   self.job['acceptance']={'hash':self.digest(),'passed':all(checks),'configured_checks':len(checks),'checks':dict(zip(['actual_suites_passed','report_counts_match_XML','report_present','no_remote','Linux_workflow_use_project_info_operator_workflow_not_Windows_PowerShell'],checks)),'operator_workflow':module.info(self.root,self.control)['operator_workflow']};self.save();return self.job['acceptance']
  if op=='acceptance':
   if self.role!='lead':raise ValueError('Lead runs fixed acceptance after review')
   self.required();h=self.digest();checks=self.control/'acceptance';runs=[]
   for script in self.job.get('acceptance_scripts',[]):
    code="import runpy,sys;sys.path.insert(0,'/work');sys.argv=['/checks/"+script+"'];runpy.run_path(sys.argv[0],run_name='__main__')"
    runs.append(self.sandbox(['/usr/bin/python3','-c',code],checks=checks))
   passed=bool(runs) and all(x['exit']==0 for x in runs) and h==self.digest()
   self.job['acceptance']={'hash':h,'passed':passed,'runs':runs,'configured_checks':len(runs)};self.save()
   if not passed and self.job.get('coordination')=='staged':
    qid=self.current();self.owner(qid);self.rig(['queue','update',qid,'--state','done','--closure-reason','denied','--resolution','FINAL_CHECK_FAILED: controller repair required','--json']);self.job['phase']='repair_pending';self.job['acceptance']['return_to_controller']=True;self.save()
   return self.job['acceptance']
  if op=='finish_task':
   if self.role!='lead':raise ValueError('Only lead can finish overall task')
   h=self.gate();self.coding_report(complete=True);parent=self.job['parent'];self.owner(parent)
   verified={'hash':h,'review':self.job['review'],'tests':{k:{x:v.get(x) for x in ['passed','count','hash']} for k,v in self.job['tests'].items()},'independent_acceptance_passed':self.job['acceptance']['passed'],'independent_checks_configured':self.job['acceptance']['configured_checks']}
   (self.root/'RESULT.md').write_text('# Verified fleet result\n\n'+json.dumps(verified,indent=2)+'\n\n## Agent notes\n'+p.get('summary','')+'\n')
   self.rig(['queue','update',parent,'--state','done','--closure-reason','no-follow-on','--resolution','PASS: exact-artifact review, saved tests and configured acceptance passed','--note','Verified completion hash='+h,'--json']);self.job['state']='complete';self.job['completed_hash']=h;self.save();return verified
  if op=='rig_command':
   a=p['args']
   if not a:raise ValueError('Missing command')
   if a[0]=='whoami':return self.rig(['whoami','--json'])
   if a[0]=='ps':return self.rig(['ps','--nodes','--rig',self.job['rig'],'--json'])
   if a[:2]==['queue','show'] and len(a)>=3:
    known=[self.job.get('parent')]+sum(self.job['children'].values(),[])
    if a[2] not in known:raise ValueError('Task outside this project')
    return self.rig(['queue','show',a[2],'--full','--json'])
   if a[:2]==['queue','list']:return self.rig(['queue','list','--destination',self.identity,'--json'])
   if a[:2]==['queue','claim'] and len(a)>=3:self.owner(a[2]);return self.rig(['queue','claim',a[2],'--json'])
   if a[:2] in [['queue','update'],['queue','block']]:
    self.owner(a[2]);raise ValueError('Use finish_stage/finish_task/delegate; raw task mutation is gated')
   if a[0]=='send' and len(a)==3 and a[1] in self.job['seats'].values():return self.rig(a)
   raise ValueError('Use structured stage tools; raw lifecycle or cross-project actions are unavailable')
  if op=='halt':
   self.job.setdefault('alerts',[]).append({'role':self.role,'reason':p['reason'],'at':time.time()})
   if self.job.get('state')=='complete':self.save();return {'stopped':True,'completed_job_preserved':True}
   if self.role=='lead' and self.job.get('coordination')=='staged' and self.job.get('phase') not in ['planning','finalizing']:
    self.save();return {'stopped':True,'completed_planning_stage_preserved':True}
   if self.role=='lead':
    self.job['state']='needs_attention';self.save()
    try:self.rig(['queue','update',self.job['parent'],'--state','failed','--resolution',p['reason'],'--note','Operator attention required','--json'])
    except Exception:pass
   else:
    self.save()
    try:
     qid=self.current();self.owner(qid);self.rig(['queue','update',qid,'--state','done','--closure-reason','denied','--resolution','STAGE_FAILED: '+p['reason'],'--note','Bounded stage failure: lead may repair','--json'])
    except Exception:pass
   return {'stopped':True,'reason':p['reason']}
  raise ValueError('Unknown operation')

def main():
 request=json.load(sys.stdin);project=Path(sys.argv[1]).resolve();control=project.parent/'control';identity=os.environ.get('OPENRIG_SESSION_NAME','')
 with (control/'lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  broker=Broker(project,identity)
  try:
   result=broker.dispatch(request['op'],request.get('params',{}));print(json.dumps({'ok':not isinstance(result,dict) or result.get('exit',0)==0,'result':result}))
  except Exception as e:
   broker.event('denied',{'op':request.get('op'),'reason':str(e)[:1000]});print(json.dumps({'ok':False,'error':str(e)[:2500]}))
if __name__=='__main__':main()
