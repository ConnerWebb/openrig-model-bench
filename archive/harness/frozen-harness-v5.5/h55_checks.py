"""Exact heading-checkpoint regression and sensor-failure resource guard."""
from common import *
from transport_policy import bounded_context,size
import copy,errno,types,threading
from unittest.mock import patch
Q=O/'repairs/h5.5'/('heading-checks-'+str(time.time_ns()));Q.mkdir(parents=True);checks=[]
def record(name,passed,**data):checks.append({'name':name,'passed':bool(passed),**data})
legacy=[]
for p in (O/'transport').glob('*/metrics.json'):
 m=json.load(p.open())
 if m.get('prefix')=='solo-coder30-cpp-csv-s42-h5.4/developer' and 'Pinned instructions' in m.get('error',''):legacy.append(p.parent)
assert legacy,'Need the real archived failure'
unique={hashlib.sha256((p/'request.json').read_bytes()).hexdigest():p for p in legacy}
for h,folder in unique.items():
 body=json.load((folder/'request.json').open());original=copy.deepcopy(body);out,policy=bounded_context(body);old=body['messages'][1]['content'][0]['text'];new=out['messages'][1]['content'][0]['text'];tail=old[old.rfind('\n\n# Instructions\n'):]
 record('actual_heading_request_bounded_'+h[:12],size({'messages':out['messages'],'tools':out.get('tools',[])})<=48000 and policy.get('summary_envelope')=='heading-checkpoint')
 record('system_and_entire_format_unchanged_'+h[:12],body==original and body['messages'][0]==out['messages'][0] and new.startswith('# Conversation\n') and new.endswith(tail) and '[Older transcript omitted' in new)
 atomic(Q/('bounded-'+h[:12]+'.json'),out);atomic(Q/('policy-'+h[:12]+'.json'),policy)
 body['messages'][1]['content']=old;out,policy=bounded_context(body);record('heading_plain_string_supported',isinstance(out['messages'][1]['content'],str) and out['messages'][1]['content'].endswith(tail))
 utf=copy.deepcopy(body);utf['messages'][1]['content']='# Conversation\n'+'初期目標'*16000+'最新エラー'*16000+tail;out,policy=bounded_context(utf);record('heading_utf8_safe',size({'messages':out['messages'],'tools':[]})<=48000 and '\ufffd' not in out['messages'][1]['content'] and out['messages'][1]['content'].endswith(tail))
 for name,mutate in [('tools',lambda b:b.update(tools=[{'type':'function','function':{'name':'write','parameters':{'type':'object','properties':{}}}}])),('ordinary_assignment',lambda b:b['messages'][0].update(content='You are a guarded programming agent.')),('wrong_format',lambda b:b['messages'][1].update(content=old[:-50])),('missing_boundary',lambda b:b['messages'][1].update(content=old.replace('\n\n# Instructions\n','\n\n# Data\n')))]:
  b=copy.deepcopy(body);mutate(b)
  try:bounded_context(b);ok=False
  except ValueError:ok=True
  record('never_clip_'+name,ok)

# Run the actual monitor loop through a continuously failing optional sensor
# and a sustained low-memory window. No real services or signals are touched.
import main
from thermal_policy import temperatures
class EndLoop(BaseException):pass
ticks=[0];events=[];commands=[];stop=threading.Event();T=Q/'monitor';T.mkdir()
def sleep(_):
 ticks[0]+=1
 if ticks[0]>=3:raise EndLoop()
def sensors():
 def read(p):
  if p=='wifi':raise OSError(errno.ELOOP,'Wi-Fi sensor ELOOP')
  return '42000'
 return temperatures(['wifi','good'],read)
clock=types.SimpleNamespace(time=time.time,monotonic=lambda:[0,10,21][ticks[0]],sleep=sleep)
with patch.object(main,'O',T),patch.object(main,'snapshot',lambda:{'at':time.time(),'available':15*2**30}),patch.object(main,'time',clock),patch.object(main,'temperatures',sensors),patch.object(main,'STOP',stop),patch.object(main,'ACTIVE',{}),patch.object(main,'event',lambda kind,**kw:events.append({'kind':kind,**kw})),patch.object(main,'subprocess',types.SimpleNamespace(run=lambda args,**kw:commands.append(args))):
 try:main.monitor()
 except EndLoop:pass
 samples=[json.loads(x) for x in (T/'memory-timeline.jsonl').read_text().splitlines()]
 record('thermal_errors_do_not_disable_resource_guard',stop.is_set() and [x['kind'] for x in events]==['resource_guard'] and commands==[['systemctl','--user','stop',main.INFER_UNIT]])
 record('all_samples_and_sensor_errors_preserved',len(samples)==3 and all(x['temperatures']=={'good':42000} and x['temperature_errors']['wifi']['errno']==errno.ELOOP for x in samples) and json.load((T/'heartbeat.json').open())['available']==15*2**30)
summary={'at':time.time(),'passed':all(c['passed'] for c in checks),'checks':checks,'archived_failures':len(legacy),'unique_requests':len(unique)};atomic(Q/'summary.json',summary);atomic(O/'repairs/h5.5/heading-checks-latest.json',{'path':str(Q/'summary.json'),'passed':summary['passed']});print(json.dumps(summary,indent=2));sys.exit(0 if summary['passed'] else 1)
