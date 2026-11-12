export const METRICS = {
  work: {label:'Accepted tasks per hour of recorded work', axis:'Accepted tasks / hour', decimals:2,
    note:'Accepted tasks divided by summed recorded trial time. Failed trials and retries consume time. This is solo workflow performance, including inference, tools and tests.'},
  time: {label:'Recorded time per task',axis:'Median minutes / task',decimals:2,
    note:'Median recorded trial duration, including failed outcomes and retries. Short failed trials are not successful completions.'},
  success: {label:'Validated completion rate',axis:'Accepted / completed trials',percent:true,
    note:'Independent acceptance plus required saved tests and guarded closure. Running, interrupted and qualification trials are excluded.'},
  attempts: {label:'Attempts per task',axis:'Mean attempts / task',decimals:2,
    note:'Initial attempt plus bounded retries. Unknown historical attempt counts appear as gaps.'},
  ttft: {label:'First delivery latency',axis:'Median seconds / HTTP round',decimals:2,
    note:'Time to first delivered stream event in completed HTTP rounds. Older runs without measured delivery timestamps appear as gaps.'},
  tokens: {label:'Measured request token rate',axis:'Completion tokens / request-second',decimals:2,
    note:'Completion tokens divided by elapsed time of complete measured HTTP rounds, including prefill and delivery overhead. This is not decode-only speed or task success.'}
};
export const TASKS={
 'py-csv':'Python · CSV aggregation','cpp-buffer':'C++ · Buffer ownership',
 'py-http':'Python · HTTP pagination','py-queue':'Python · Durable queue',
 'py-archive':'Python · Archive extraction','py-refactor':'Python · Refactoring',
 'py-expression':'Python · Expression parser','cpp-queue':'C++ · Blocking queue',
 'cpp-csv':'C++ · CSV parser','cpp-stats':'C++ · Running statistics',
 'cpp-binary':'C++ · Binary encoding','cpp-lru':'C++ · LRU cache'
};
export function median(values){
 if(!values.length)return null;
 const a=[...values].sort((x,y)=>x-y), i=Math.floor(a.length/2);
 return a.length%2?a[i]:(a[i-1]+a[i])/2;
}
export function scopesFor(data){return ['shared','all',...new Set(data.cases.map(r=>r.task))];}
export function validState(data,state){
 return {revision:data.revisions.includes(state?.revision)?state.revision:data.active_revision,
  scope:scopesFor(data).includes(state?.scope)?state.scope:'shared',
  metric:Object.hasOwn(METRICS,state?.metric)?state.metric:'work'};
}
export function filterCases(data,state){
 return data.cases.filter(r=>r.revision===state.revision && (state.scope==='all' ||
  (state.scope==='shared' ? r.seed===42 && r.variant===0 && ['py-csv','cpp-buffer'].includes(r.task) : r.task===state.scope)));
}
function measure(rows,metric){
 if(!rows.length)return null;
 if(metric==='success')return rows.filter(r=>r.passed).length/rows.length;
 if(metric==='time')return median(rows.map(r=>r.seconds/60));
 if(metric==='work')return rows.filter(r=>r.passed).length*3600/rows.reduce((s,r)=>s+r.seconds,0);
 if(metric==='attempts'){
  const a=rows.map(r=>r.attempts).filter(x=>Number.isFinite(x));
  return a.length?a.reduce((x,y)=>x+y,0)/a.length:null;
 }
 if(metric==='ttft')return median(rows.flatMap(r=>r.ttft));
 const secs=rows.reduce((s,r)=>s+r.request_seconds,0);
 return secs>0?rows.reduce((s,r)=>s+r.tokens,0)/secs:null;
}
function reason(row){
 const a=[];
 if(row.resource_limited)a.push('resource limit');
 if(row.context_rejections)a.push(`${row.context_rejections} context-limit rejections`);
 if(row.last_public_modes.normal===false)a.push('last fixed checks failed');
 if(row.last_public_modes.asan===false || row.last_public_modes.tsan===false)a.push('last sanitizer check failed');
 if(row.last_saved_tests===false)a.push('last saved tests failed');
 if(row.last_private_passed===false)a.push('independent acceptance failed');
 if(/deadline|timeout/i.test(row.reason))a.push('deadline');
 else if(/verified closure/i.test(row.reason))a.push('unverified closure');
 else if(/tool|invalid/i.test(row.reason))a.push('tool-use limit');
 else a.push('retry budget / workflow');
 return a.join(' · ');
}
export function buildView(data,input){
 const state=validState(data,input), selected=filterCases(data,state), metric=METRICS[state.metric];
 const models=data.model_order.filter(k=>data.labels[k]);
 const aggregate=k=>['python','cpp'].map(l=>selected.filter(r=>r.model===k && r.language===l));
 const rows=models.map(k=>{
  const [py,cpp]=aggregate(k);
  const counts=state.scope==='shared'?'':` · Py ${py.filter(r=>r.passed).length}/${py.length}, C++ ${cpp.filter(r=>r.passed).length}/${cpp.length}`;
  return [data.labels[k]+counts, measure(py,state.metric), measure(cpp,state.metric)];
 });
 const observations=Object.fromEntries(['python','cpp'].map(l=>{
  const a=selected.filter(r=>r.language===l);
  return [l,{passed:a.filter(r=>r.passed).length,total:a.length}];
 }));
 const scoped=state.scope==='shared'?'Shared two-task screen · seed 42':state.scope==='all'?'All finished solo tasks':TASKS[state.scope]||state.scope;
 const presentFields=['Python','C++'].filter((_,i)=>rows.some(r=>r[i+1]!==null));
 // Keep axes comparable between revision choices for this same scope/metric.
 let maximum=1;
 for(const rev of data.revisions){
  const same=filterCases(data,{...state,revision:rev});
  for(const k of models)for(const l of ['python','cpp']){
   const v=measure(same.filter(r=>r.model===k && r.language===l),state.metric);
   if(v!==null)maximum=Math.max(maximum,v);
  }
 }
 const domain=state.metric==='success'?[0,1]:[0,maximum*1.08];
 const config={id:'openrig-performance-bars',title:metric.label,showHeader:false,
  description:`${state.revision} · ${scoped}`,height:608,
  summary:`Python ${observations.python.passed}/${observations.python.total} and C++ ${observations.cpp.passed}/${observations.cpp.total} accepted. Harness revisions are shown separately.`,
  spec:{type:'horizontalBar',y:'Model',x:presentFields.length?presentFields:['Python','C++'],xLabel:metric.axis,showValues:true,showLegend:true,sortOrder:'original',xDomain:domain,
   colors:{Python:'var(--chart-1)','C++':'var(--chart-2)'},
   valueFormat:metric.percent?{style:'percent',maximumFractionDigits:1}:{style:'decimal',maximumFractionDigits:metric.decimals}},
  columns:['Model','Python','C++'],rows:rows.some(r=>r[1]!==null||r[2]!==null)?rows:[]};
 const covered=new Set(selected.map(r=>r.model)).size;
 return {state,config,observations,scoped,covered,
  readout:`Python ${observations.python.passed}/${observations.python.total} accepted · C++ ${observations.cpp.passed}/${observations.cpp.total} accepted · ${covered}/${models.length} model configurations`,
  note:metric.note+(state.scope==='shared'?' Each model has at most one trial per language in this screen.':' Coverage varies by model; sample counts are included in model labels.'),
  failures:selected.filter(r=>!r.passed).map(r=>({label:`${data.labels[r.model]} · ${TASKS[r.task]||r.task} · seed ${r.seed} · ${(r.seconds/60).toFixed(2)} min`,detail:reason(r)}))};
}
