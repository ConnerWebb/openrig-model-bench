"""Regression evidence for observed h4 failures; no production endpoints."""
from common import *
from transport_policy import xml_tool,bounded_context,size
from proxy import convert
import worker,orchestrator,copy
from catalog import TASKS
Q=O/('repairs/'+HARNESS_REVISION)/('checks-'+str(time.time_ns()));Q.mkdir(parents=True);checks=[]
def record(name,passed,**evidence):checks.append({'name':name,'passed':bool(passed),**evidence})
tools=[{'type':'function','function':{'name':'get_task','parameters':{'type':'object','properties':{}}}},{'type':'function','function':{'name':'write','parameters':{'type':'object','properties':{'path':{'type':'string'},'content':{'type':'string'}},'required':['path','content']}}},{'type':'function','function':{'name':'review_decision','parameters':{'type':'object','properties':{'approved':{'type':'boolean'},'issues':{'type':'array','items':{'type':'string'}}},'required':['approved','issues']}}}]
xml='<function=get_task>\n</function>\n</tool_call>'
record('complete_known_zero_argument_native_call',xml_tool(xml,tools)=={'name':'get_task','arguments':{}})
source='print("a\\nb")\nprint("尾")'
call=xml_tool('<tool_call>\n<function=write>\n<parameter=path>solution.py</parameter>\n<parameter=content>\n'+source+'\n</parameter>\n</function>\n</tool_call>',tools)
record('source_newlines_escapes_and_unicode_preserved',call and call['arguments']=={'path':'solution.py','content':source})
record('typed_array_and_boolean',xml_tool('<function=review_decision><parameter=approved>false</parameter><parameter=issues>["bad"]</parameter></function></tool_call>',tools)['arguments']=={'approved':False,'issues':['bad']})
for name,text in [('prose','Use this '+xml),('unknown',xml.replace('get_task','sudo')),('partial',xml[:-5]),('second_call',xml+xml),('missing_required','<function=write></function></tool_call>'),('unknown_parameter','<function=get_task><parameter=x>1</parameter></function></tool_call>'),('wrong_type','<function=review_decision><parameter=approved>"false"</parameter><parameter=issues>[]</parameter></function></tool_call>'),('duplicate','<function=write><parameter=path>x</parameter><parameter=path>x</parameter><parameter=content>x</parameter></function></tool_call>')]:record('reject_'+name,xml_tool(text,tools) is None)
msgs=[{'choices':[{'delta':{'content':xml},'finish_reason':None}]},{'choices':[{'delta':{},'finish_reason':'stop'}],'usage':{'prompt_tokens':7,'completion_tokens':12}}]
converted=convert(msgs,{'tools':tools});record('normalization_preserves_usage_and_tool_finish',converted and converted[-1]['usage']['completion_tokens']==12 and converted[1]['choices'][0]['finish_reason']=='tool_calls')
length=copy.deepcopy(msgs);length[-1]['choices'][0]['finish_reason']='length';record('never_execute_length_truncated_call',convert(length,{'tools':tools}) is None)
native=copy.deepcopy(msgs);native[0]['choices'][0]['delta']['tool_calls']=[{'function':{'name':'get_task'}}];record('never_duplicate_native_calls',convert(native,{'tools':tools}) is None)
body={'tools':tools,'messages':[{'role':'system','content':'guarded instructions'},{'role':'user','content':'latest assignment'}]}
for n in range(30):body['messages'] += [{'role':'assistant','tool_calls':[{'id':str(n),'type':'function','function':{'name':'write','arguments':json.dumps({'path':'solution.py','content':'x'*8000})}}]},{'role':'tool','tool_call_id':str(n),'content':'result'*1500}]
original=copy.deepcopy(body);limited,policy=bounded_context(body,12000);record('bounded_history_preserves_original_and_instructions',body==original and size({'messages':limited['messages'],'tools':tools})<=12000 and limited['messages'][:2]==body['messages'][:2] and policy['applied'])
known=set();paired=True
for m in limited['messages']:
 if m['role']=='assistant':known.update(c['id'] for c in m.get('tool_calls',[]))
 if m['role']=='tool' and m['tool_call_id'] not in known:paired=False
record('tool_results_keep_matching_call',paired)
root=Q/'seat/project';control=root.parent/'control';root.mkdir(parents=True);control.mkdir();task=TASKS['py-csv'];write_reference(task,root);reference_tests(task,root);publish_public(task,root)
identity='dev@h5-regression';job={'identity':identity,'project':str(root),'role':'developer','authority':'developer','assignment':'q1','phase':'implementing','state':'active','task':'py-csv','required_files':['solution.py','README.md'],'seed':42};atomic(control/'job.json',job)
worker.native=lambda *a,**k:{'destinationSession':identity,'state':'in-progress','qitemId':'q1'};b=worker.Broker(root,identity)
record('host_path_alias_broker_plaintext',b.dispatch('read',{'path':str(root/'PUBLIC_DRIVER.py')})['text']==task['driver'].rstrip('\n'))
b.dispatch('append',{'path':str(root/'extra.py'),'content':'first\n'});b.dispatch('append',{'path':'/work/extra.py','content':'second\n'});record('guarded_append', (root/'extra.py').read_text()=='first\nsecond\n')
for name in ['PUBLIC_DRIVER.py','PUBLIC_CASES.json','public-inputs/case-00.csv']:
 try:b.dispatch('append',{'path':name,'content':'corrupt'});ok=False
 except ValueError:ok=True
 record('protected_append_'+name,ok)
import shlex
cmd='test "$(pwd)" = /work && cd '+shlex.quote(str(root))+' && printf safe > alias-test.txt && test "$(cat /work/alias-test.txt)" = safe && test ! -e /home/cow/.ssh'
r=sandbox(root,['sh','-c',cmd],writable=True);record('advertised_path_is_same_isolated_writable_project',r['exit']==0,evidence=r)
r=sandbox(root,['sh','-c','printf corrupt > '+shlex.quote(str(root/'PUBLIC_DRIVER.py'))],writable=True);record('alias_cannot_bypass_readonly_contract',r['exit']!=0)
for folder in ['tests','other']:
 d=root/folder;d.mkdir();(d/'test_duplicate.py').write_text('import unittest\nclass Duplicate(unittest.TestCase):\n def test_one(self):self.assertTrue(True)\n')
a=authored_tests(root);record('duplicate_python_test_basenames_each_run',a['passed'] and len(a['runs'])==3,evidence=a)
(root/'test_empty.py').write_text('assert True\n');a=authored_tests(root);record('zero_test_files_fail_with_nonzero_exit',not a['passed'] and a['exit']!=0)
(root/'test_empty.py').unlink();(root/'test_fail.cpp').write_text('int main(){return 7;}');a=authored_tests(root);record('cpp_test_also_runs_when_python_exists',not a['passed'] and a['exit']==7)
c=object.__new__(orchestrator.Case);c.deadline=time.time()+100;c.seats={'developer':{'root':root,'control':control}};c.job=lambda role:{**job,'state':'failed','failure':'first failed before closure'}
r=c.wait('developer',1);record('terminal_stage_race_returns_retry_feedback',r.get('_stage_failure')=='first failed before closure')
c.job=lambda role:{**job,'turn_settled_at':time.time()-3};r=c.wait('developer',1);record('unclosed_turn_is_retryable_without_twenty_minute_wait',bool(r.get('_stage_failure')))
# Exercise actual Case.run repair control flow with failed owned stages, no model or daemon.
c=orchestrator.Case('h5-budget-regression-'+str(time.time_ns()),'py-csv',{'developer':'next'},phase='harness-regression');old=c.dir;c.dir=Q/'retry-case';c.dir.mkdir();old.rmdir();c.seats={'developer':{'root':root,'control':control,'identity':identity}};c.compose=lambda:None;c.launch=lambda:None;c.ordinary_develop=lambda *a:False
oldnative=orchestrator.native;orchestrator.native=lambda *a,**k:{}
try:r=c.run()
finally:orchestrator.native=oldnative
record('three_attempt_budget_survives_failed_stages',r['attempts']==3 and len(r['stage_attempts'])==3 and not r['complete'])
for name in ['catalog.py','cases.py']:
 record('unchanged_oracle_'+name,(R/name).read_bytes()==(O/'frozen-harness-v4.2'/name).read_bytes())
large={'passed':False,'fixed_public_passed':True,'authored_tests':{'passed':False,'exit':153,'runs':[{'file':'test_driver.cpp','exit':153,'stdout':'字'*500000,'stderr':''}]},'next_action':'repair_code_or_authored_tests_then_run_tests'}
projected=worker.bounded_reply(large)
record('oversize_unicode_log_preserves_verdict_within_wire_budget',len(json.dumps(projected,ensure_ascii=False).encode())<=100000 and projected['passed'] is False and projected['fixed_public_passed'] is True and projected['authored_tests']['exit']==153 and large['authored_tests']['runs'][0]['stdout']=='字'*500000)
record('normal_replies_are_byte_semantically_unchanged',worker.bounded_reply({'passed':False,'authored_tests':{'exit':7,'stderr':'normal'}})=={'passed':False,'authored_tests':{'exit':7,'stderr':'normal'}})
large_array=worker.bounded_reply({'passed':False,'failures':[{'actual':[{'value':'x'*50000} for _ in range(20)]} for _ in range(20)]})
record('large_nested_failed_values_fit_wire_budget',large_array['passed'] is False and len(json.dumps(large_array,ensure_ascii=False).encode())<=100000)
import io,contextlib
old_dispatch=worker.Broker.dispatch;oldin,oldargv=sys.stdin,sys.argv;oldidentity=os.environ.get('OPENRIG_SESSION_NAME');capture=io.StringIO()
try:
 worker.Broker.dispatch=lambda self,op,p:large if op=='run_tests' else old_dispatch(self,op,p)
 sys.stdin=io.StringIO(json.dumps({'op':'run_tests','params':{},'assignment':'q1'}));sys.argv=['worker.py',str(root)];os.environ['OPENRIG_SESSION_NAME']=identity
 with contextlib.redirect_stdout(capture):worker.main()
 envelope=json.loads(capture.getvalue());evidence_files=list(control.glob('oversize-tool-run_tests-*.json'))
 record('oversize_real_cli_is_test_evidence_not_tool_error',envelope['ok'] and envelope['result']['passed'] is False and len(capture.getvalue().encode())<120000 and evidence_files and json.load(open(evidence_files[-1]))==large)
finally:
 worker.Broker.dispatch=old_dispatch;sys.stdin,sys.argv=oldin,oldargv
 if oldidentity is None:os.environ.pop('OPENRIG_SESSION_NAME',None)
 else:os.environ['OPENRIG_SESSION_NAME']=oldidentity
summary={'at':time.time(),'harness_revision':HARNESS_REVISION,'passed':all(x['passed'] for x in checks),'checks':checks};atomic(Q/'summary.json',summary);atomic(O/('repairs/'+HARNESS_REVISION+'/checks-latest.json'),{'path':str(Q/'summary.json'),'passed':summary['passed']});print(json.dumps(summary,indent=2));sys.exit(0 if summary['passed'] else 1)
