import {mountChart} from 'https://persistent.oaistatic.com/plugins/visualize/charts/1.2.3/element.js';
import {buildView,validState,scopesFor,METRICS,TASKS} from './chart_logic.mjs';

const root=document.getElementById('openrig-performance-live');
const el=id=>root.querySelector('#perf-'+id);
const revision=el('revision'),scope=el('scope'),metric=el('metric');
const storageKey='openrig-performance-live-v1';
let data,chart,identity,state;
try{state=JSON.parse(localStorage.getItem(storageKey));}catch{}

function options(select,values){
  select.replaceChildren();
  for(const [value,label] of values){const o=document.createElement('option');o.value=value;o.textContent=label;select.append(o);}
  select.disabled=false;
}
function render(){
  const v=buildView(data,state);state=v.state;
  revision.value=state.revision;scope.value=state.scope;metric.value=state.metric;
  if(chart)chart.config=v.config;
  else chart=mountChart(root.querySelector('[data-viz-container]'),v.config);
  el('title').textContent=v.config.title;
  el('readout').textContent=v.readout;
  el('note').textContent=v.scoped+' · '+v.note;
  el('snapshot').textContent=`Results updated ${data.captured_label} · ${data.cases.length} finished solo trials across ${data.revisions.length} separate revisions`;
  el('failure-count').textContent=`Failed trials (${v.failures.length})`;
  const list=el('failures');list.replaceChildren();
  for(const failure of v.failures){
    const li=document.createElement('li'),label=document.createElement('div'),detail=document.createElement('div');
    label.textContent=failure.label;detail.className='text-muted';detail.textContent=failure.detail;
    li.append(label,detail);list.append(li);
  }
  if(!v.failures.length){const li=document.createElement('li');li.textContent='No failed completed trials in this selection.';list.append(li);}
}
export function applyData(incoming){
  // Validate before replacing the last good chart; retain all three selections.
  if(incoming.schema!==1||!Array.isArray(incoming.cases)||!incoming.revisions.includes(incoming.active_revision))throw Error('Unsupported result snapshot');
  const next=validState(incoming,state);
  buildView(incoming,next);
  data=incoming;state=next;identity=incoming.result_identity;
  options(revision,data.revisions.map(v=>[v,v==='legacy'?'Legacy · revision unavailable':v+(v===data.active_revision?' · current':'')]));
  options(scope,scopesFor(data).map(v=>[v,v==='shared'?'Matched two-task screen':v==='all'?'All finished solo tasks':TASKS[v]||v]));
  options(metric,Object.entries(METRICS).map(([v,m])=>[v,m.label]));
  render();
}
root.addEventListener('change',e=>{
  if(!data||![revision,scope,metric].includes(e.target))return;
  state={revision:revision.value,scope:scope.value,metric:metric.value};render();
  try{localStorage.setItem(storageKey,JSON.stringify(state));}catch{}
});
async function getJSON(url){
  const response=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(6000)});
  if(!response.ok)throw Error('Read failed: '+response.status);
  return response.json();
}
export async function refresh(){
  try{
    const status=await getJSON('/status.json');
    if(!data||status.result_identity!==identity)applyData(await getJSON('/data.json'));
    const now=Date.now()/1000;
    if(status.error)throw Error(status.error);
    if(now-status.checked_at>45)throw Error('Result observer is stale');
    const staleHeartbeat=now-status.heartbeat_at>120;
    el('status').className=staleHeartbeat?'text-small text-destructive':'text-small';
    const jobs=(status.active_jobs||[]).join(', ')||status.current||status.phase;
    el('status').textContent=`${staleHeartbeat?'Campaign heartbeat is stale':'Checking for results every 15 seconds'} · Current: ${jobs} · Last checked ${new Date(status.checked_at*1000).toLocaleTimeString()}`;
  }catch(error){
    el('status').className='text-small text-destructive';
    el('status').textContent='Updates unavailable; showing last good results. '+error.message;
  }
}
let stopped=false,timer;
async function cycle(){await refresh();if(!stopped)timer=setTimeout(cycle,15000);}
window.addEventListener('pagehide',()=>{stopped=true;clearTimeout(timer);});
window.addEventListener('pageshow',e=>{if(e.persisted){stopped=false;cycle();}});
cycle();
