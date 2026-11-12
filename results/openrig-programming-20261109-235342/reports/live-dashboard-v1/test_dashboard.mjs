import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {buildView,validState,scopesFor,METRICS,TASKS} from './chart_logic.mjs';
const data=JSON.parse(fs.readFileSync(new URL('./state/data.json',import.meta.url),'utf8'));
const code=fs.readFileSync(new URL('./dashboard.js',import.meta.url),'utf8')
 .replace(/^import .*;\n/gm,'').replaceAll('export ','').replace(/cycle\(\);\s*$/,'');
class Element{
 constructor(){this.value='';this.children=[];this.listeners={};}
 replaceChildren(){this.children=[];}append(...x){this.children.push(...x);}
 addEventListener(n,f){this.listeners[n]=f;}
}
const root=new Element(),lookup={};
for(const id of ['revision','scope','metric','title','snapshot','readout','note','failure-count','failures','status'])lookup['#perf-'+id]=new Element();
lookup['[data-viz-container]']=new Element();
root.querySelector=s=>{assert(s in lookup,s);return lookup[s];};
let mounts=0,chart,saves=0,broken=false;
const status={checked_at:Date.now()/1000,heartbeat_at:Date.now()/1000,active_jobs:['test-only'],result_identity:data.result_identity};
const sandbox={buildView,validState,scopesFor,METRICS,TASKS,console,AbortSignal,Date,
 document:{getElementById:()=>root,createElement:()=>new Element()},
 window:{addEventListener:()=>{}},localStorage:{getItem:()=>JSON.stringify({revision:'h5.4',scope:'all',metric:'success'}),setItem:()=>saves++},
 mountChart:(_,config)=>{mounts++;chart={config};return chart;},setTimeout:()=>1,clearTimeout:()=>{},
 fetch:async url=>{if(broken)throw Error('fixture offline');return {ok:true,json:async()=>url==='/status.json'?status:data};}};
vm.createContext(sandbox);new vm.Script(code).runInContext(sandbox);
await new vm.Script('refresh()').runInContext(sandbox);
assert.equal(mounts,1);assert.equal(saves,0);
assert.equal(lookup['#perf-revision'].value,'h5.4');assert.equal(lookup['#perf-scope'].value,'all');
const before=chart.config;
// A changed result identity drives another read; existing chart and selections survive.
status.result_identity='fixture-new-identity';
await new vm.Script('refresh()').runInContext(sandbox);
assert.equal(mounts,1);assert.equal(lookup['#perf-revision'].value,'h5.4');assert.equal(lookup['#perf-metric'].value,'success');
assert.equal(saves,0);
lookup['#perf-metric'].value='time';
root.listeners.change({target:lookup['#perf-metric']});
assert.equal(saves,1);assert.equal(chart.config.title,METRICS.time.label);
const lastGood=chart.config;broken=true;
await new vm.Script('refresh()').runInContext(sandbox);
assert.equal(chart.config,lastGood);assert(lookup['#perf-status'].textContent.includes('last good'));
broken=false;status.checked_at=Date.now()/1000-100;
await new vm.Script('refresh()').runInContext(sandbox);
assert(lookup['#perf-status'].textContent.includes('stale'));
const result={passed:true,checks:['automatic changed-result refresh','single mount','preserved filters','persistent user changes only','offline last-good retention','stale observer warning'],at:new Date().toISOString()};
fs.writeFileSync(new URL('./state/dashboard-checks.json',import.meta.url),JSON.stringify(result,null,2));
console.log(JSON.stringify(result));
