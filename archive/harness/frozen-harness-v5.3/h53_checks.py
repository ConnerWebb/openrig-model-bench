"""Regression checks for observed Qwen batches and per-mode sanitizer feedback."""
from common import *
from transport_policy import xml_tools
from proxy import convert,encoded
from catalog import TASKS
import copy
Q=O/('repairs/'+HARNESS_REVISION)/('targeted-checks-'+str(time.time_ns()));Q.mkdir(parents=True);checks=[]
def record(name,passed,**extra):checks.append({'name':name,'passed':bool(passed),**extra})
# Replay actual archived inputs, not an invented approximation of the model.
legacy=[]
for p in (O/'transport').glob('*/metrics.json'):
 row=json.load(open(p))
 if row.get('prefix')=='solo-coder30-cpp-buffer-s42-h5.2/developer':legacy.append(p.parent)
assert len(legacy)==3
for folder in legacy:
 body=json.load(open(folder/'request.json'));messages=[]
 for line in (folder/'response.jsonl').read_text().splitlines():
  if line.startswith('data:'):
   try:messages.append(json.loads(line[5:]))
   except ValueError:pass
 result=convert(messages,body);calls=(result or [{}])[0].get('choices',[{}])[0].get('delta',{}).get('tool_calls',[])
 record('actual_qwen_batch_'+folder.name,[c['function']['name'] for c in calls]==['get_task','claim_task','ls','read','read'] and len({c['id'] for c in calls})==5 and [c['index'] for c in calls]==list(range(5)))
 atomic(Q/(folder.name+'-converted.json'),result)
body=json.load(open(legacy[0]/'request.json'));tools=body['tools'];text=''.join(m.get('choices',[{}])[0].get('delta',{}).get('content','') or '' for m in messages if m.get('choices'))
first='<function=get_task></function></tool_call>';second='<function=claim_task></function></tool_call>'
for name,raw in [('prose','I will do this: '+text),('truncated_tail',text[:-4]),('unknown_second',first+'<function=delete_host></function></tool_call>'),('bad_parameter',first+'<function=read><parameter=path>file</parameter><parameter=bad>yes</parameter></function></tool_call>'),('missing_required',first+'<function=read></function></tool_call>'),('over_budget',first*9)]:record('reject_entire_batch_'+name,xml_tools(raw,tools) is None)
record('allow_wrapped_and_missing_opening_in_same_batch',len(xml_tools('<tool_call>'+first+second,tools))==2)
for name,finish,done in [('length','length',True),('no_done','stop',False)]:
 # convert validates finish; DONE gating is covered at the socket layer.
 m=[{'choices':[{'delta':{'content':first+second},'finish_reason':finish}]}]
 if name=='length':record('never_normalize_output_capped_batch',convert(m,body) is None)
# Reproduce the real faulty Qwen3.5 artifact read-only with public inputs.
oldroot=O/'runs/solo-q35-cpp-buffer-s42-h5.2/seats/developer/project';before=digest(oldroot)
r=run_suite(oldroot,TASKS['cpp-buffer'],Q/'actual-old-build',seed=71,private=False);atomic(Q/'old-artifact-public-suite.json',r);f=feedback(r);atomic(Q/'old-artifact-public-feedback.json',f)
record('actual_artifact_normal_passes_asan_fails',r['checks']['normal']['passed'] and not r['checks']['asan']['passed'] and not r['passed'])
record('public_asan_feedback_contains_actual_failed_cases',f['failed_modes']==['asan'] and f['checks']['asan']['failures'] and f['checks']['normal']['passed'])
record('mode_result_not_overwritten_by_aggregate',r['checks']['normal']['passed'] and digest(oldroot)==before)
private=feedback(r,private=True);atomic(Q/'old-artifact-redacted-feedback.json',private)
record('private_mode_feedback_hides_inputs_and_expected',all('input' not in failure and failure['expected']=='independent contract check failed' for c in private['checks'].values() for failure in c['failures']) and private['failed_modes']==['asan'])
root=Q/'reference/project';write_reference(TASKS['cpp-buffer'],root);good=run_suite(root,TASKS['cpp-buffer'],Q/'reference/control',seed=71,private=False);atomic(Q/'reference-suite.json',good)
record('known_correct_buffer_passes_all_modes',good['passed'] and set(good['checks'])=={'normal','asan'})
# Directly exercise aggregate mode/error selection including TSan without executing a race.
import common
real=common.run_checks;calls=[]
def stub(root,task,control,**kw):
 mode=kw['mode'];calls.append(mode)
 return {'passed':mode!='tsan','hash':digest(root),'count':1,'mode':mode,'rows':[{'case':0,'passed':mode!='tsan','input':'hidden-marker','expected':{'x':1},'actual':{},'stderr':'ThreadSanitizer: simulated race' if mode=='tsan' else '', 'exit':66 if mode=='tsan' else 0}]}
common.run_checks=stub
try:
 q=run_suite(root,TASKS['cpp-queue'],Q/'tsan-probe',private=True);out=feedback(q,True)
 record('tsan_failure_mode_and_diagnostic_preserved',calls==['normal','asan','tsan'] and out['failed_modes']==['tsan'] and 'ThreadSanitizer' in out['checks']['tsan']['failures'][0]['stderr'] and 'hidden-marker' not in json.dumps(out))
 common.run_checks=lambda root,task,control,**kw:{'passed':False,'hash':digest(root),'count':0,'mode':kw['mode'],'compile':{'exit':1,'stderr':'compile failure'}}
 q=run_suite(root,TASKS['cpp-queue'],Q/'compile-probe');out=feedback(q)
 record('compile_failure_and_skipped_modes_explicit',out['failed_modes']==['normal'] and set(out['not_run'])=={'asan','tsan'} and out['checks']['normal']['compile']['stderr']=='compile failure')
finally:common.run_checks=real
summary={'at':time.time(),'harness_revision':HARNESS_REVISION,'passed':all(c['passed'] for c in checks),'checks':checks};atomic(Q/'summary.json',summary);atomic(O/('repairs/'+HARNESS_REVISION+'/targeted-checks-latest.json'),{'path':str(Q/'summary.json'),'passed':summary['passed']});print(json.dumps(summary,indent=2));sys.exit(0 if summary['passed'] else 1)
