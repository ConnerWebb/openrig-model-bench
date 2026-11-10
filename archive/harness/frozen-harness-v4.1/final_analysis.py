"""Post-completion analysis. Never starts inference or changes model settings."""
import json,pathlib,statistics,collections,math,shutil,time
R=pathlib.Path(__file__).resolve().parent
P=json.load(open(R/'paths.json'));O=pathlib.Path(P['output'])
def read(p):return json.load(open(p))
def median(values):return statistics.median(values) if values else None
def p95(values):
 if not values:return None
 values=sorted(values);x=.95*(len(values)-1);lo=int(x);hi=min(lo+1,len(values)-1);return values[lo]+(x-lo)*(values[hi]-values[lo])
def interval(k,n):
 if not n:return [0,1]
 z=1.96;p=k/n;a=1+z*z/n;b=(p+z*z/(2*n))/a;c=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/a
 return [max(0,b-c),min(1,b+c)]
def run():
 if not (O/'COMPLETED.json').exists():return
 all_rows=[read(p) for p in (O/'runs').glob('*/result.json')]
 revision=read(O/'active-harness-revision.json')['revision'] if (O/'active-harness-revision.json').exists() else None
 rows=[r for r in all_rows if not r.get('interrupted') and r['phase']!='qualification' and (revision is None or r.get('harness_revision')==revision)]
 direct=[]
 for p in (O/'parallel-inference').glob('*/result.json'):
  d=read(p);req=p.parent/'0/request.json'
  if req.exists():d['_started']=req.stat().st_mtime;d['_finished']=d['_started']+d['seconds']
  direct.append(d)
 byid={r['id']:r for r in rows};measure={k:{'ttft':[],'tokens':0,'request_seconds':[],'incomplete_requests':0,'samples':0} for k in byid}
 with (O/'events.jsonl').open() as f:
  for line in f:
   try:e=json.loads(line)
   except Exception:continue
   if e.get('kind')!='inference_request':continue
   id=e.get('prefix','').split('/')[0]
   if id not in measure:continue
   m=measure[id];ttft=e.get('first_content_seconds');sec=e.get('seconds')
   if ttft is not None:m['ttft'].append(ttft)
   if sec is not None:m['request_seconds'].append(sec)
   m['tokens']+=(e.get('usage') or {}).get('completion_tokens',0);m['incomplete_requests']+=not e.get('complete',False)
 boundaries=[]
 for r in rows:boundaries.extend([(r['started'],1,r['id']),(r['finished'],0,r['id'])])
 for d in direct:
  if '_started' in d:
   measure[d['id']]={'samples':0};boundaries.extend([(d['_started'],1,d['id']),(d['_finished'],0,d['id'])])
 boundaries.sort();i=0;active=set()
 with (O/'memory-timeline.jsonl').open() as f:
  for line in f:
   try:s=json.loads(line)
   except Exception:continue
   while i<len(boundaries) and boundaries[i][0]<=s['at']:
    _,add,id=boundaries[i];active.add(id) if add else active.discard(id);i+=1
   for id in active:
    m=measure[id];m['samples']+=1
    for key in ['system_used','swap_used','mem_info_vram_used','mem_info_gtt_used']:
     if key in s:m['peak_'+key]=max(m.get('peak_'+key,0),s[key])
    for key in ['pswpin','pswpout']:
     if key in s:m.setdefault(key+'_first',s[key]);m[key+'_last']=s[key]
 for id,m in measure.items():
  m['median_request_ttft_seconds']=median(m.pop('ttft',[]));m['median_request_latency_seconds']=median(m.pop('request_seconds',[]))
  for key in ['pswpin','pswpout']:m[key+'_pages']=max(0,m.pop(key+'_last',0)-m.pop(key+'_first',0))
 groups=collections.defaultdict(list)
 for r in rows:
  if r['phase'] not in ['solo','teams','topology','parallel-jobs','soak']:continue
  groups[(r['phase'],r['language'],json.dumps(r['models'],sort_keys=True),r['topology'])].append(r)
 summary=[]
 for (phase,lang,models,agents),items in groups.items():
  k=sum(bool(r['complete']) for r in items);n=len(items);ms=[measure[r['id']] for r in items];secs=sum(r['seconds'] for r in items)
  row={'phase':phase,'language':lang,'models':json.loads(models),'agents':agents,'accepted':k,'attempted':n,'first_attempt_accepted':sum(r['complete'] and r.get('attempts')==1 for r in items),'pass_rate':k/n,'descriptive_95pct_wilson_interval':interval(k,n),'median_task_seconds':median([r['seconds'] for r in items]),'p95_task_seconds':p95([r['seconds'] for r in items]),'accepted_per_sum_job_hour':k*3600/max(secs,.001),'resource_limited':sum(bool(r.get('resource_limited')) for r in items),'timeout_jobs':sum('deadline' in r.get('failure','').lower() or 'timeout' in r.get('failure','').lower() for r in items),'incomplete_requests':sum(m['incomplete_requests'] for m in ms),'median_of_case_request_ttft_seconds':median([m['median_request_ttft_seconds'] for m in ms if m['median_request_ttft_seconds'] is not None])}
  for key in ['system_used','swap_used','mem_info_vram_used','mem_info_gtt_used']:row['peak_'+key]=max((m.get('peak_'+key,0) for m in ms),default=0)
  summary.append(row)
 batches=[read(p) for p in (O/'parallel-jobs').glob('*/result.json')];bg=collections.defaultdict(list)
 for b in batches:bg[(json.dumps(b['models'],sort_keys=True),b['slots'],b['max_loaded_models'],b['concurrent_jobs'])].append(b)
 parallel=[]
 for (models,slots,resident,jobs),items in bg.items():
  accepted=sum(b['accepted'] for b in items);seconds=sum(b['seconds'] for b in items);parallel.append({'models':json.loads(models),'slots':slots,'resident':resident,'jobs':jobs,'repetitions':len(items),'accepted':accepted,'attempted':sum(b['concurrent_jobs'] for b in items),'accepted_per_machine_hour':accepted*3600/max(seconds,.001),'resource_limited_batches':sum(bool(b.get('resource_limited')) for b in items)})
 compatibility={p.parent.name:read(p) for p in (O/'compatibility').glob('*/result.json')}
 dg=collections.defaultdict(list)
 for d in direct:dg[(tuple(d['models']),d['slots_requested'],d['context_limit'],d['profile']['resident'],len(d['requests']))].append(d)
 inference=[]
 for (models,slots,ctx,resident,clients),items in dg.items():
  requests=[r for d in items for r in d['requests']];mem=[measure.get(d['id'],{}) for d in items];r={'models':models,'slots_requested':slots,'context':ctx,'max_loaded_models':resident,'clients':clients,'repetitions':len(items),'accepted':sum(d['accepted'] for d in items),'attempted':len(requests),'median_aggregate_tokens_per_second':median([d['aggregate_tokens_per_second'] for d in items]),'accepted_per_batch_wall_hour':sum(d['accepted'] for d in items)*3600/max(.001,sum(d['seconds'] for d in items)),'median_request_latency_seconds':median([x['inference_seconds'] for x in requests if 'inference_seconds' in x]),'p95_request_latency_seconds':p95([x['inference_seconds'] for x in requests if 'inference_seconds' in x]),'median_ttft_seconds':median([x['ttft_seconds'] for x in requests if x.get('ttft_seconds') is not None]),'failed_requests':sum(bool(x.get('error')) for x in requests),'resource_limited_batches':sum(bool(d.get('resource_limited')) for d in items)}
  for key in ['system_used','swap_used','mem_info_vram_used','mem_info_gtt_used']:r['peak_'+key]=max((m.get('peak_'+key,0) for m in mem),default=0)
  inference.append(r)
 data={'at':time.time(),'groups':summary,'case_measurements':measure,'parallel_guarded_batches':parallel,'direct_inference_profiles':inference,'compatibility':compatibility,'limits':['Repeated task families; Wilson intervals describe these attempts and are not independent-domain generalization claims.','Memory is sampled whole-system/shared-GPU consumption, not exclusive process attribution. VRAM and GTT are reported separately and must not be added as independent physical memory. Direct-batch windows use request-file timestamps and batch duration, to the precision of one-second sampling.','Time to first token is measured per tool-round HTTP request; task latency includes the complete workflow.','Overlapping job durations are not machine throughput. Parallel batch throughput uses actual batch wall time.','No production model or configuration is automatically changed.']}
 data['harness_revision']=revision;data['historical_results_preserved_separately']=len(all_rows)-len(rows)
 target=O/'FINAL-COMPARISON.json';target.write_text(json.dumps(data,indent=2));lines=['FINISHED PYTHON / C++ MODEL COMPARISON','','Final data: '+str(target),'']
 for lang in ['python','cpp']:
  lines += [lang.upper(),'Phase | models | agents | accepted | task seconds median | accepted/sum-job-hour | median request TTFT seconds | resource-limited']
  selected=sorted([x for x in summary if x['language']==lang],key=lambda x:(x['phase'],-x['pass_rate'],-x['accepted_per_sum_job_hour']))
  for r in selected:lines.append(f"{r['phase']} | {json.dumps(r['models'],sort_keys=True)} | {r['agents']} | {r['accepted']}/{r['attempted']} | {r['median_task_seconds']:.1f} | {r['accepted_per_sum_job_hour']:.2f} | {r['median_of_case_request_ttft_seconds']} | {r['resource_limited']}")
  solo=[r for r in selected if r['phase']=='solo']
  if solo:lines.append('Best observed individual candidate, ranking correctness then throughput: '+json.dumps(solo[0]['models']))
  lines.append('')
 lines += ['GUARDED PARALLEL PROCESSING — actual machine hours']
 for r in sorted(parallel,key=lambda x:-x['accepted_per_machine_hour']):lines.append(json.dumps(r,sort_keys=True))
 stable=[r for r in parallel if r['accepted']==r['attempted'] and not r['resource_limited_batches'] and r['repetitions']>=3]
 if stable:lines.append('Best observed fully accepted repeated parallel profile (experimental recommendation only): '+json.dumps(max(stable,key=lambda x:x['accepted_per_machine_hour']),sort_keys=True))
 else:lines.append('No fully accepted repeated parallel profile qualified for a reliability recommendation.')
 lines+=['','DIRECT API INFERENCE — separate from guarded agent scoring']+[json.dumps(r,sort_keys=True) for r in inference]
 lines += ['','Compatibility exclusions: '+', '.join(k for k,v in compatibility.items() if not v['qualified']),'','Effective GPU runner slot/context evidence: runtime-evidence/. Requested slot counts are not proof of actual parallel execution.','']+data['limits']
 (O/'FINAL-COMPARISON.txt').write_text('\n'.join(lines)+'\n');backup=pathlib.Path(P['backup'])/('final-analysis-'+str(time.time_ns()));backup.mkdir();shutil.copy2(target,backup/target.name);shutil.copy2(O/'FINAL-COMPARISON.txt',backup/'FINAL-COMPARISON.txt')
if __name__=='__main__':run()
