"""Controller-owned generic stages. No model-written receipts or row closure."""
import pathlib,json,time,subprocess,hashlib,fcntl,uuid,importlib.util
class Controller:
 def __init__(self,project,cli,worker):
  self.root=pathlib.Path(project);self.control=self.root.parent/'control';self.cli=cli
  spec=importlib.util.spec_from_file_location('isolated_broker',worker);self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
 def read(self):return json.loads((self.control/'job.json').read_text())
 def update(self,change):
  with (self.control/'lock').open('a') as f:
   fcntl.flock(f,fcntl.LOCK_EX);j=self.read();change(j);p=self.control/'controller.tmp';p.write_text(json.dumps(j,indent=2));p.replace(self.control/'job.json');return j
 def event(self,event,**data):
  with (self.control/'controller-events.jsonl').open('a') as f:f.write(json.dumps({'time':time.time(),'event':event,**data})+'\n')
 def native(self,*args):
  r=subprocess.run([self.cli,*args],capture_output=True,text=True,timeout=45)
  if r.returncode:raise RuntimeError((r.stderr+r.stdout)[-3000:])
  return json.loads(r.stdout)
 def broker(self):return self.module.Broker(self.root,self.read()['seats']['lead'])
 def wait(self,predicate,seconds=360):
  end=time.monotonic()+seconds
  while time.monotonic()<end:
   j=self.read()
   if j['state']=='needs_attention':raise RuntimeError('Guard requested operator attention')
   if time.time()-j['created']>j['timeout']:raise RuntimeError('Overall budget exhausted')
   value=predicate(j)
   if value:return value
   time.sleep(2)
  raise RuntimeError('Stage deadline exceeded; no interruption or completion')
 def idle(self,role):
  def check(j):
   r=self.native('ps','--nodes','--rig',j['rig'],'--json');entries=r if isinstance(r,list) else r.get('entries',[])
   seats=[x for x in entries if x.get('canonicalSessionName')==j['seats'][role]]
   return len(seats)==1 and seats[0].get('agentActivity',{}).get('state')=='idle'
  self.wait(check,90)
 def assign(self,role,body,phase):
  self.idle(role);qid='qitem-'+time.strftime('%Y%m%d%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:16]
  def register(j):
   j['phase']=phase
   if role=='lead':j['parent']=qid;j.setdefault('lead_assignments',[]).append(qid)
   else:j['children'][role].append(qid)
  # Register retry ID before native create/wake, eliminating the startup race.
  self.update(register)
  item=self.native('queue','create','--id',qid,'--source','installer@external','--destination',self.read()['seats'][role],'--summary','Guarded '+phase+' stage','--body',body,'--json');assert item['qitemId']==qid
  self.event('assigned',role=role,phase=phase,qid=qid);return qid
 def closed(self,role,qid):
  def check(j):
   row=self.native('queue','show',qid,'--json')
   return row if row['state'] in ('done','failed','canceled') else False
  row=self.wait(check);self.idle(role);j=self.read();closed=j.get('closed_stages',{}).get(role,{})
  prefix='Implementation ready' if role=='developer' else 'REVIEW_'
  return row['state']=='done' and str(row.get('resolution','')).startswith(prefix) and closed.get('closed')==qid and closed.get('hash')==self.broker().digest() and closed.get('outcome','').startswith(prefix)
 def audit(self,label):
  b=self.broker();b.checked_inputs();h=b.digest();runs=[]
  for script in self.read()['acceptance_scripts']:
   code="import sys,runpy;sys.path.insert(0,'/work');runpy.run_path('/checks/"+script+"',run_name='__main__')";r=b.sandbox(['/usr/bin/python3','-c',code],checks=self.control/'acceptance');runs.append({'script':script,**r})
  result={'hash':h,'passed':bool(runs) and all(r['exit']==0 for r in runs) and h==b.digest(),'runs':runs}
  (self.control/('audit-'+label+'.json')).write_text(json.dumps(result,indent=2));self.event('independent_audit',label=label,passed=result['passed'],hash=h)
  return result
 @staticmethod
 def issues(audit):return ['Independent acceptance failed:\n'+r['output'][-10000:] for r in audit['runs'] if r['exit']!=0]
 def run(self):
  with (self.control/'controller.lock').open('a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
   first=self.audit('preserved-failure');issues=self.issues(first)
   # Approved task is authoritative; no model-planning stage can block repair.
   self.event('controller_plan',origin='operator task plus deterministic failed checks')
   for attempt in range(3):
    self.event('developer_required',attempt=attempt,issues=issues)
    plan='Read TASK.txt; repair the public API and preserve exact evidence; test malformed input and regenerate the saved output.';qid=self.assign('developer','DEVELOPER ONLY. Get/claim this stage. Read TASK.txt. Fixed acceptance files are outside the project and intentionally unreadable; do not search for checks or /checks. Use the supplied failures and full task contract. Work only in this disposable copy. Fix unmet requirements and preserve already-correct behavior; implement the complete contract, not just listed test cases. Preserve evidence. Saved unit tests run read-only: CLI tests must use a temporary directory. Use write/edit or isolated developer shell to save required output. Run_tests then finish_stage. End your turn.\nPLAN:\n'+plan+'\nREPAIR REQUIREMENTS:\n'+'\n'.join(issues),'implementing')
    if not self.closed('developer',qid):issues=['Developer did not produce a verified closed implementation.'];continue
    qid=self.assign('reviewer','INDEPENDENT REVIEWER ONLY. Get/claim this stage. Read TASK.txt and inspect actual public API validation, saved output equality, URL authority checks, HTML/.md shared quotation budget and source handling. Run_tests, record concrete review_decision and finish_stage. No edits or delegation. End your turn.','reviewing')
    if not self.closed('reviewer',qid):issues=['Reviewer stage lacked valid closed receipt.'];continue
    review=self.read().get('review',{})
    if not review.get('approved') or review.get('issues') or review.get('task')!=qid or review.get('hash')!=self.broker().digest():issues=review.get('issues') or ['Reviewer rejected implementation.'];self.event('repair_required',cause='review',attempt=attempt);continue
    audit=self.audit('attempt-'+str(attempt))
    if not audit['passed']:issues=self.issues(audit);self.event('repair_required',cause='acceptance',attempt=attempt);continue
    finalid=self.assign('lead','FINALIZER ONLY. Get/claim this finalization assignment. Developer and independent reviewer closed successfully; controller acceptance passed. Call run_tests, acceptance, then finish_task only after all pass. Never edit, use shell or delegate. Failed acceptance returns to the controller. End after completion.','finalizing')
    state=self.wait(lambda j:j if j['state']=='complete' or j.get('phase')=='repair_pending' else False)
    self.idle('lead')
    if state['state']=='complete':
     row=self.native('queue','show',finalid,'--json');assert row['state']=='done' and str(row.get('resolution','')).startswith('PASS:');self.event('verified_complete',qid=finalid,hash=state['completed_hash']);return
    issues=['Finalizer acceptance failed; repair before fresh review.']+self.issues(state['acceptance']);self.event('repair_required',cause='finalizer_acceptance',attempt=attempt)
   raise RuntimeError('Two-repair limit reached; no completion claimed')

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('project');args=parser.parse_args()
 c=Controller(args.project,'/home/cow/Documents/Codex/2026-11-05/referenced-chatgpt-conversation-this-is-an/outputs/openrig-programming-20261109-235342/isolation/rig',str(pathlib.Path(__file__).with_name('worker.py')))
 try:c.run()
 except Exception as e:
  c.update(lambda j:j.update(state='needs_attention',controller_error=str(e)))
  raise SystemExit(str(e))
