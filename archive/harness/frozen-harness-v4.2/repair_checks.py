"""Regression and guard checks for the isolated h4 tool protocol."""
from common import *
import worker,io,contextlib,copy
from catalog import TASKS
Q=O/('harness-repair-checks-'+str(time.time_ns()));Q.mkdir();checks=[]
def record(name,ok,**extra):checks.append({'name':name,'passed':bool(ok),**extra})
root=Q/'seat/project';control=root.parent/'control';root.mkdir(parents=True);control.mkdir();identity='dev@h4-regression';qid='q-regression';job={'identity':identity,'project':str(root),'role':'developer','authority':'developer','assignment':qid,'phase':'implementing','state':'active','task':'py-csv','required_files':['solution.py','README.md'],'seed':42}
write_reference(TASKS['py-csv'],root);reference_tests(TASKS['py-csv'],root);(root/'TASK.txt').write_text('protected');atomic(control/'job.json',job)
row={'qitemId':qid,'destinationSession':identity,'state':'pending'};claims=[]
def native(*args,**kw):
 if args[:2]==('queue','show'):return copy.deepcopy(row)
 if args[:2]==('queue','claim'):claims.append(args[2]);row['state']='in-progress';return copy.deepcopy(row)
 if args[:2]==('queue','update'):row['state']='done';return copy.deepcopy(row)
 raise ValueError('Unexpected native operation')
worker.native=native;b=worker.Broker(root,identity)
first=b.dispatch('claim_task',{});second=b.dispatch('claim_task',{});record('claim_idempotent_once_native_claim',first['state']=='in-progress' and second['state']=='in-progress' and len(claims)==1)
row['destinationSession']='other';
try:b.dispatch('claim_task',{});record('wrong_owner_claim_denied',False)
except ValueError:record('wrong_owner_claim_denied',True)
row['destinationSession']=identity
for name,op,args in [('path_traversal','write',{'path':'../control/job.json','content':'{}'}),('protected_contract','write',{'path':'TASK.txt','content':'bad'}),('raw_native_mutation','rig_command',{'args':['queue','update',qid,'--state','done']}),('finish_without_receipt','finish_stage',{})]:
 try:b.dispatch(op,args);record(name,False)
 except Exception:record(name,True)
negative=b.dispatch('run',{'command':'python3 -c "raise SystemExit(7)"'});record('command_nonzero_returned_as_evidence',negative['exit']==7 and not negative['timed_out'])
# Exercise the CLI envelope, including assignment fencing, rather than only dispatch.
def invoke(op,params=None,lease=qid):
 oldin,oldargv=sys.stdin,sys.argv;oldidentity=os.environ.get('OPENRIG_SESSION_NAME');out=io.StringIO()
 try:
  sys.stdin=io.StringIO(json.dumps({'op':op,'params':params or {},'assignment':lease}));sys.argv=['worker.py',str(root)];os.environ['OPENRIG_SESSION_NAME']=identity
  with contextlib.redirect_stdout(out):worker.main()
 finally:
  sys.stdin=oldin;sys.argv=oldargv
  if oldidentity is None:os.environ.pop('OPENRIG_SESSION_NAME',None)
  else:os.environ['OPENRIG_SESSION_NAME']=oldidentity
 return json.loads(out.getvalue())
envelope=invoke('run',{'command':'false'});record('nonzero_command_envelope_is_not_tool_error',envelope['ok'] and envelope['result']['exit']==1)
before=(control/'job.json').read_bytes();stale=invoke('halt',{'reason':'late old timer'},lease='q-previous');record('late_old_stage_cannot_halt_new_assignment',not stale['ok'] and before==(control/'job.json').read_bytes())
valid=invoke('run_tests');record('fixed_and_saved_tests_positive',valid['ok'] and valid['result']['passed'])
b=worker.Broker(root,identity);closed=b.dispatch('finish_stage',{});again=b.dispatch('finish_stage',{});record('verified_closure_idempotent',closed['closed'] and again['already_closed'])
before=(control/'job.json').read_bytes();late=invoke('halt',{'reason':'late same-stage timer'});record('late_deadline_cannot_invalidate_closed_stage',late['ok'] and late['result']['already_closed'] and before==(control/'job.json').read_bytes())
(root/'README.md').write_text('changed after receipt')
try:b.dispatch('finish_stage',{});record('modified_closed_artifact_rejected',False)
except Exception:record('modified_closed_artifact_rejected',True)
row['state']='in-progress';atomic(control/'job.json',job)
for k in range(6):rep=invoke('run',{'command':'printf fixed-output'})
record('unchanged_repetition_bounded',rep['ok'] and rep['result']['stalled'] and rep['result']['unchanged_repetitions']==6)
(root/'README.md').write_text('progress resets repetition');rep=invoke('run',{'command':'printf fixed-output'});record('source_change_resets_repetition',rep['result']['unchanged_repetitions']==1)
pub={'passed':False,'hash':'x','mode':'normal','count':1,'rows':[{'case':0,'input':{'private-canary':123},'actual':{},'expected':{'x':1},'stderr':'' ,'passed':False}]};record('public_failure_has_input',feedback(pub)['failures'][0]['input']=={'private-canary':123});record('private_failure_hides_input_and_expected','input' not in feedback(pub,True)['failures'][0] and 'private-canary' not in json.dumps(feedback(pub,True)))
example=public_examples('cpp-csv')[0];record('decoded_csv_examples_remove_wire_escaping','api_input_csv' in example and example['api_input_csv'].startswith('category,amount'))
link=sandbox(root,['/bin/sh','-c','printf "int main(){}" > /tmp/t.cpp && clang++ /tmp/t.cpp -o /tmp/t && /tmp/t && test ! -e /etc/passwd && test ! -e /home/cow/.ssh']);record('default_linker_works_without_host_etc',link['exit']==0,evidence=link)
scoped=sandbox(root,['/bin/sh','-c','printf bad > solution.py']);record('readonly_execution_preserved',scoped['exit']!=0)
# Every original frozen task oracle must still accept its known-good source.
for id,task in TASKS.items():
 d=Q/'references'/id/'project';write_reference(task,d);r=run_checks(d,task,d.parent/'control',private=True);atomic(d.parent/'result.json',r);record('reference_'+id,r['passed'])
 # Relevant memory/concurrency guards are separate builds.
 if id in ['cpp-buffer','cpp-queue']:
  for mode in (['asan','tsan'] if id=='cpp-queue' else ['asan']):
   r=run_checks(d,task,d.parent/'control',private=True,mode=mode);atomic(d.parent/(mode+'.json'),r);record('reference_'+id+'_'+mode,r['passed'])
summary={'at':time.time(),'harness_revision':HARNESS_REVISION,'passed':all(x['passed'] for x in checks),'checks':checks};atomic(Q/'summary.json',summary);atomic(O/'repair-checks-latest.json',{'path':str(Q/'summary.json'),'passed':summary['passed']});print(json.dumps(summary,indent=2));sys.exit(0 if summary['passed'] else 1)
