import pathlib,json,sys,time
from common import *
from catalog import TASKS
Q=O/'qualification';Q.mkdir(exist_ok=True);rows=[]
for id,task in TASKS.items():
 root=Q/id/'project';control=root.parent/'control';write_reference(task,root)
 r=run_checks(root,task,control,seed=1701,private=True);atomic(Q/id/'reference.json',r);print(id,r['passed'],r.get('error',''),[{'case':x['case'],'actual':x['actual'],'expected':x['expected'],'stderr':x['stderr'][-500:]} for x in r.get('rows',[]) if not x['passed']][:2],flush=True);rows.append({'task':id,'passed':r['passed']})
 if task['language']=='cpp' and r['passed']:
  for mode in ['asan']+(['tsan'] if id=='cpp-queue' else []):
   s=run_checks(root,task,control,seed=1701,private=True,mode=mode,case_limit=3);atomic(Q/id/(mode+'.json'),s);print(id,mode,s['passed'],flush=True);rows.append({'task':id,'mode':mode,'passed':s['passed']})
atomic(Q/'summary.json',{'passed':all(x['passed'] for x in rows),'checks':rows});sys.exit(0 if all(x['passed'] for x in rows) else 1)
