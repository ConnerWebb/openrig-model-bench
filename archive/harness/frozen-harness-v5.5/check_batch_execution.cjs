const assert=require('node:assert/strict');
const {createJiti}=require('/home/cow/.local/opt/framework-ai/openrig-fleet/npm/node_modules/jiti');
const fromPi=require('node:module').createRequire('/home/cow/.local/opt/framework-ai/openrig-fleet/npm/node_modules/@earendil-works/pi-coding-agent/dist/core/extensions/loader.js');
const jiti=createJiti(__filename,{moduleCache:false,alias:{typebox:fromPi.resolve('typebox')}});
(async()=>{
 const factory=await jiti.import(process.argv[2],{default:true});
 const {Agent}=await import('/home/cow/.local/opt/framework-ai/openrig-fleet/npm/node_modules/@earendil-works/pi-agent-core/dist/agent.js');
 const {createAssistantMessageEventStream}=await import('/home/cow/.local/opt/framework-ai/openrig-fleet/npm/node_modules/@earendil-works/pi-ai/dist/utils/event-stream.js');
 const {wrapToolDefinition}=await import('/home/cow/.local/opt/framework-ai/openrig-fleet/npm/node_modules/@earendil-works/pi-coding-agent/dist/core/tools/tool-definition-wrapper.js');
 const tools={},handlers={},observed=[];let active=[],agent,source='';const ctx={abort:()=>agent?.abort()};
 const pi={registerTool:t=>tools[t.name]=t,on:(n,h)=>handlers[n]=h,setActiveTools:x=>active=x};
 factory(pi,async(op,p,lease)=>{
  if(op==='status')return {ok:true,result:{role:'developer',actual_role:'developer',phase:'implementing',state:'active',assignment:'q1',project_kind:'programming-campaign',write_paths:null}};
  assert.equal(lease,'q1');observed.push(op);
  if(op==='write'){await new Promise(r=>setTimeout(r,40));source=p.content;return {ok:true,result:{saved:p.path}};}
  if(op==='append'){assert.equal(source,'A','append must await preceding write');source+=p.content;return {ok:true,result:{saved:p.path}};}
  if(op==='run_tests'){assert.equal(source,'AB','tests must see all earlier writes');return {ok:true,result:{passed:true,fixed_public_passed:true,count:1,hash:'h',next_action:'finish_stage'}};}
  return {ok:true,result:{closed:true}};
 });
 assert(Object.values(tools).every(t=>t.executionMode==='sequential'));
 const model={id:'fixture',name:'fixture',api:'openai-completions',provider:'fixture',input:['text'],reasoning:false,cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:32768,maxTokens:4096};
 const input=[['write',{path:'file',content:'A'}],['append',{path:'file',content:'B'}],['run_tests',{}],['finish_stage',{}],['write',{path:'file',content:'AFTER_CLOSURE'}]];
 let turns=0;
 agent=new Agent({initialState:{model,systemPrompt:'fixture'},streamFn:()=>{
  assert.equal(turns++,0,'closure must not trigger another model turn');
  const msg={role:'assistant',api:model.api,provider:model.provider,model:model.id,timestamp:Date.now(),content:input.map(([name,args],i)=>({type:'toolCall',id:'c'+i,name,arguments:args})),stopReason:'toolUse',usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}};
  const s=createAssistantMessageEventStream();s.push({type:'start',partial:msg});s.push({type:'done',reason:'toolUse',message:msg});return s;
 }});
 await handlers.before_agent_start({},ctx);agent.state.tools=active.map(n=>wrapToolDefinition(tools[n],()=>ctx));
 agent.subscribe(async e=>{if(e.type==='tool_execution_end')await handlers.tool_execution_end(e,ctx);});
 await agent.prompt('run fixture');handlers.agent_end();
 assert.deepEqual(observed,['write','append','run_tests','finish_stage']);assert.equal(source,'AB');
 console.log('PASS: installed Pi agent executes registered batch in wire order and stops after guarded closure');
})().catch(e=>{console.error(e);process.exitCode=1;});
