import pathlib,json,time,collections,hashlib,subprocess
from common import *
def _report(final=False):
 rows=[]
 for f in (O/'runs').glob('*/result.json'):
  try:
   item=json.load(open(f))
   if not item.get('interrupted') and item.get('harness_revision')==HARNESS_REVISION:rows.append(item)
  except Exception:pass
 groups=collections.defaultdict(list)
 for r in rows:groups[(r['phase'],r['language'],r['task'],str(r.get('models')),r['topology'])].append(r)
 table=[]
 for (phase,lang,task,models,n),items in groups.items():
  secs=sum(r['seconds'] for r in items);ok=sum(bool(r['complete']) for r in items);table.append({'phase':phase,'language':lang,'task':task,'models':models,'agents':n,'passed':ok,'attempted':len(items),'case_wall_seconds_sum':secs,'accepted_tasks_per_hour':ok*3600/secs if secs else 0,'failures':[{'id':r['id'],'reason':r.get('failure'),'resource_limited':r.get('resource_limited',False)} for r in items if not r['complete']]})
 atomic(O/'leaderboard.json',table)
 status=json.load(open(O/'campaign-status.json')) if (O/'campaign-status.json').exists() else {};lines=['OPENRIG PYTHON / C++ CAMPAIGN — '+('FINISHED' if final else 'LIVE CHECKPOINT'),'',str(O),'State: '+str(status),'Active harness revision: '+HARNESS_REVISION,'Historical pre-repair results remain intact in runs/ and progress/; they are not mixed into this revision\'s rankings. All previous completed cells are rerun, including earlier passes.','','Independent task acceptance is the success criterion. Python and C++ are scored separately. Aliases are not additional models. Qualification and probes are not included in solo/team rankings.','']
 for phase in ['solo','teams','topology','parallel-jobs','soak']:
  lines+=['PHASE '+phase]
  for lang in ['python','cpp']:
   selected=[r for r in rows if r['phase']==phase and r['language']==lang];total=len(selected);passed=sum(r['complete'] for r in selected);lines.append(f'{lang}: {passed}/{total} accepted')
   ranks=collections.defaultdict(list)
   for r in selected:ranks[(str(r['models']),r['topology'])].append(r)
   for (model,n),items in sorted(ranks.items(),key=lambda kv:(-sum(x['complete'] for x in kv[1])/len(kv[1]),sum(x['seconds'] for x in kv[1])/len(kv[1]))):
    accepted=sum(x['complete'] for x in items);wall=sum(x['seconds'] for x in items);lines.append(f'  {model}, {n} agents: {accepted}/{len(items)}; sum job seconds {wall:.1f}; accepted/hour {accepted*3600/max(wall,.001):.3f}')
 lines+=['','Parallel job throughput uses batch wall time in parallel-jobs/*/result.json; summing overlapping job durations is NOT machine throughput. Direct inference results live in parallel-inference and must not be equated with guarded OpenRig teamwork.','Failures and bounded timeouts remain recorded; resource failures are labelled. Reviewer probes report false approvals/rejections in role-probes, separate from developer correctness. Maintainability has no automatic numeric score masquerading as an objective test.','The case manifests, native task rows, exact-source hashes, request streams, model settings, test output and transcripts remain preserved.','Production services, selected fleet pointers and Gremlin Garden are not modified.','This is a finite local study with repeated task families; held-out team cases use new input seeds and composition tasks, not a claim of broad unseen-domain capability.','Python/C++ main campaign only; C#/Unity are not scheduled here.','Snapshots: '+P['backup'],'','Previous qualification failures are not candidate coding results. Native qualification-v2 failed due missing session-bus environment; it is an infrastructure trial. All corrected tests, ASan/UBSan and TSan probes are preserved.']
 (O/'RESULTS.txt').write_text('\n'.join(lines)+'\n')
 comparison=[]
 for r in rows:
  if r['phase']!='solo':continue
  original=O/'runs'/(r['id'].removesuffix('-'+HARNESS_REVISION)+'-h5.3')/'result.json'
  if original.exists():
   prior=json.load(open(original));comparison.append({'task':r['task'],'language':r['language'],'seed':r['seed'],'old_id':prior['id'],'old_complete':prior['complete'],'old_interrupted':prior.get('interrupted',False),'old_seconds':prior['seconds'],'new_id':r['id'],'new_complete':r['complete'],'new_seconds':r['seconds'],'new_failure':r.get('failure')})
 if (O/('repairs/'+HARNESS_REVISION)).exists():
  atomic(O/('repairs/'+HARNESS_REVISION+'/comparison.json'),comparison);text=['HARNESS REPAIR — FRESH RERUN COMPARISON','Old and new trials stay separate. Old results were not edited. New tasks start from the same original fixtures, not operator-corrected answers.','Task | seed | old outcome | old minutes | current outcome | current minutes']
  for r in comparison:text.append(f"{r['task']} | {r['seed']} | {'interrupted' if r['old_interrupted'] else 'PASS' if r['old_complete'] else 'FAIL'} | {r['old_seconds']/60:.2f} | {'PASS' if r['new_complete'] else 'FAIL'} | {r['new_seconds']/60:.2f}")
  (O/('repairs/'+HARNESS_REVISION+'/COMPARISON.txt')).write_text('\n'.join(text)+'\n')
 return rows

import threading
_REPORT_LOCK=threading.RLock()
def report(final=False):
 with _REPORT_LOCK:return _report(final)
