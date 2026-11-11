"""Replay the actual failed Pi compaction input and its boundary cases."""
from common import *
from transport_policy import bounded_context,size
import copy
Q=O/('repairs/'+HARNESS_REVISION)/('compaction-checks-'+str(time.time_ns()));Q.mkdir(parents=True);checks=[];legacy=[]
def record(name,passed,**data):checks.append({'name':name,'passed':bool(passed),**data})
for p in (O/'transport').glob('*/metrics.json'):
 m=json.load(open(p))
 if m.get('prefix')=='solo-nemo-cpp-buffer-s42-h5.3/developer' and 'Pinned instructions' in m.get('error',''):legacy.append(p.parent)
assert legacy
unique={hashlib.sha256((p/'request.json').read_bytes()).hexdigest():p for p in legacy}
for h,folder in unique.items():
 body=json.load(open(folder/'request.json'));original=copy.deepcopy(body);bounded,policy=bounded_context(body);oldtext=body['messages'][1]['content'][0]['text'];newtext=bounded['messages'][1]['content'][0]['text'];tail=oldtext[oldtext.rfind('</conversation>'):]
 record('actual_summary_under_budget_'+h[:12],size({'messages':bounded['messages'],'tools':bounded.get('tools',[])})<=48000 and policy['kind']=='compaction-summary')
 record('preserve_system_and_format_'+h[:12],body==original and bounded['messages'][0]==body['messages'][0] and newtext.endswith(tail) and newtext.startswith(oldtext[:200]) and '[Older transcript omitted' in newtext)
 atomic(Q/('bounded-'+h[:12]+'.json'),bounded);atomic(Q/('policy-'+h[:12]+'.json'),policy)
body=json.load(open(legacy[0]/'request.json'));text=body['messages'][1]['content'][0]['text'];string_body=copy.deepcopy(body);string_body['messages'][1]['content']=text
bounded,policy=bounded_context(string_body);record('plain_string_summary_supported',policy['kind']=='compaction-summary' and isinstance(bounded['messages'][1]['content'],str))
utf=copy.deepcopy(body);utf['messages'][1]['content'][0]['text']='<conversation>'+'初期目標'*10000+'最新エラー'*10000+'</conversation>\nPreserve this exact summary format.';bounded,policy=bounded_context(utf);record('utf8_clipping_valid_and_within_bytes',size({'messages':bounded['messages'],'tools':bounded.get('tools',[])})<=48000 and bounded['messages'][1]['content'][0]['text'].endswith('Preserve this exact summary format.') and '\ufffd' not in bounded['messages'][1]['content'][0]['text'])
for name,change in [('tool_enabled',lambda b:b.update(tools=[{'type':'function','function':{'name':'write','parameters':{'type':'object','properties':{}}}}])),('ordinary_instruction',lambda b:b['messages'][0].update(content='You are a guarded programming agent.')),('not_conversation',lambda b:b['messages'][1]['content'][0].update(text='A'*200000))]:
 b=copy.deepcopy(body);change(b)
 try:bounded_context(b);ok=False
 except ValueError:ok=True
 record('never_rewrite_'+name,ok)
small={'messages':[{'role':'system','content':'You are a context summarization assistant.'},{'role':'user','content':'<conversation>small</conversation>\nformat'}]};b,p=bounded_context(small);record('small_request_unchanged',b==small and not p['applied'])
atomic(Q/'legacy-errors.json',{'count':len(legacy),'unique_requests':len(unique),'metrics_paths':[str(p.relative_to(O)) for p in legacy]})
summary={'at':time.time(),'passed':all(c['passed'] for c in checks),'checks':checks};atomic(Q/'summary.json',summary);atomic(O/('repairs/'+HARNESS_REVISION+'/compaction-checks-latest.json'),{'path':str(Q/'summary.json'),'passed':summary['passed']});print(json.dumps(summary,indent=2));sys.exit(0 if summary['passed'] else 1)
