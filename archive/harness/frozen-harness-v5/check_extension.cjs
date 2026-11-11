const assert=require('node:assert/strict');
const {createJiti}=require('/home/cow/.local/opt/framework-ai/openrig-fleet/npm/node_modules/jiti');
const fromPi=require('node:module').createRequire('/home/cow/.local/opt/framework-ai/openrig-fleet/npm/node_modules/@earendil-works/pi-coding-agent/dist/core/extensions/loader.js');
const jiti=createJiti(__filename,{moduleCache:false,alias:{typebox:fromPi.resolve('typebox')}});
(async()=>{
 const factory=await jiti.import(process.argv[2],{default:true});
 function fixture(role='developer',phase='implementing'){
  const handlers={},tools={},calls=[];let active=[],aborts=0;
  const pi={registerTool:t=>tools[t.name]=t,on:(n,h)=>handlers[n]=h,setActiveTools:a=>active=a};
  const ctx={abort:()=>aborts++};let s={role,actual_role:role,phase,state:'active',assignment:'q1',project_kind:'programming-campaign',write_paths:null};
  factory(pi,async(op,p,lease)=>{calls.push({op,p,lease});if(op==='status')return {ok:true,result:s};if(op==='run')return {ok:true,result:{exit:7,timed_out:false,output:'line1\nline2',next:'repair'}};if(op==='read')return {ok:true,result:{text:'real\nnewline \\n literal'}};return {ok:true,result:{closed:true}};});
  return {handlers,tools,calls,ctx,get active(){return active},get aborts(){return aborts},s};
 }
 let f=fixture();let start=await f.handlers.before_agent_start({},f.ctx);assert(start.systemPrompt.includes('CURRENT_ASSIGNMENT q1'));assert(f.active.includes('append'));let plain=await f.tools.read.execute('r',{path:'x'},undefined,undefined,f.ctx);assert.equal(plain.content[0].text,'real\nnewline \\n literal');await f.handlers.agent_settled();assert(f.calls.some(c=>c.op==='turn_settled'&&c.lease==='q1'));assert(f.active.includes('finish_stage'));assert(!f.active.includes('delegate'));assert(!Object.values(f.tools).some(t=>/Unity/.test(t.description)));
 for(let i=0;i<3;i++){let r=await f.tools.run.execute('t',{command:'false'},undefined,undefined,f.ctx);assert.equal(r.isError,false);await f.handlers.tool_execution_end({isError:r.isError,toolName:'run'},f.ctx);}assert.equal(f.aborts,0);assert(!f.calls.some(x=>x.op==='halt'));
 let r=await f.tools.finish_stage.execute('t',{},undefined,undefined,f.ctx);await f.handlers.tool_execution_end({isError:r.isError,toolName:'finish_stage'},f.ctx);assert.equal(f.aborts,1);assert(!f.calls.some(x=>x.op==='halt'));assert(f.calls.filter(x=>x.op!=='status').every(x=>x.lease==='q1'));f.handlers.agent_end();
 f=fixture();await f.handlers.before_agent_start({},f.ctx);for(let i=0;i<3;i++)await f.handlers.tool_execution_end({isError:true,toolName:'write'},f.ctx);assert(f.calls.some(x=>x.op==='halt'));f.handlers.agent_end();
 f=fixture('lead','planning');await f.handlers.before_agent_start({},f.ctx);assert(f.active.includes('submit_plan'));assert(!f.active.includes('run'));r=await f.tools.submit_plan.execute('t',{steps:['one']},undefined,undefined,f.ctx);await f.handlers.tool_execution_end({isError:false,toolName:'submit_plan'},f.ctx);assert.equal(f.aborts,1);f.handlers.agent_end();
 f=fixture('lead','finalizing');await f.handlers.before_agent_start({},f.ctx);assert(f.active.includes('acceptance'));assert(!f.active.includes('write'));f.handlers.agent_end();
 f=fixture('developer','idle');await f.handlers.before_agent_start({},f.ctx);assert.equal(f.aborts,1);assert.equal(f.active.length,0);
 console.log('Extension protocol checks PASS: transport, command exits, closure termination, role scoping, fencing, invalid-operation budget, idle state');
})().catch(e=>{console.error(e);process.exitCode=1;});
