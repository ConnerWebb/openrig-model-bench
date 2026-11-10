from orchestrator import *
def run():
 prior=O/'baseline-replay/result.json'
 if prior.exists():return json.load(open(prior))
 path=R/'replay-profile';path.mkdir(exist_ok=True)
 for name in ['worker.py','controller.py','extension.ts']:
  s=(BASE/'v2/generic-staged'/name).read_text().replace('/home/cow/.local/bin/rig-fleet',CLI).replace(str(BASE/'v2/generic-staged/worker.py'),str(path/'worker.py'));(path/name).write_text(s)
 parent=O/'baseline-replay';parent.mkdir(exist_ok=True);root=parent/'project';control=parent/'control';root.mkdir(exist_ok=True);(control/'acceptance').mkdir(parents=True,exist_ok=True);old=pathlib.Path('/home/cow/.local/state/openrig-fleet/v2/jobs/fleet-v2-baseline-20261108-203205');name='bench-replay-'+P['stamp'];models={}
 for f in ['TASK.txt','AGENTS.md']:shutil.copy2(old/'project'/f,root/f)
 shutil.copytree(old/'project/agents',root/'agents',dirs_exist_ok=True)
 for f in ['acceptance.py','acceptance_extra.py']:shutil.copy2(old/'control/acceptance'/f,control/'acceptance'/f)
 text=(old/'project/rig.yaml').read_text().replace('fleet-v2-baseline-20261108-203205',name);a=alias('next',42,replay=True);text=text.replace('ollama/lab-coder-next','ollama/'+a);(root/'rig.yaml').write_text(text);seats={role:'team-'+role+'@'+name for role in ['lead','developer','reviewer']}
 j={'rig':name,'project':str(root),'created':time.time(),'timeout':2400,'state':'active','coordination':'staged','phase':'prepared','parent':None,'children':{'developer':[],'reviewer':[]},'seats':seats,'required_files':['expenses.py','test_expenses.py','README.md'],'acceptance_scripts':['acceptance.py','acceptance_extra.py'],'input_hashes':{'TASK.txt':hashlib.sha256((root/'TASK.txt').read_bytes()).hexdigest()},'task_sha256':hashlib.sha256((root/'TASK.txt').read_bytes()).hexdigest()};atomic(control/'job.json',j)
 for role,identity in seats.items():
  agent=I/'instance/state/pi'/identity/'agent';agent.mkdir(parents=True,exist_ok=True);cfg=model_config('baseline-replay/'+role,[('next',42)]);cfg['providers']['ollama']['models'][0].update(id=a,name=a,samplingParams={'temperature':1.,'top_p':.95});atomic(agent/'models.json',cfg)
 s=importlib.util.spec_from_file_location('replay_controller',path/'controller.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
 class Trial(m.Controller):
  def assign(self,role,body,phase):
   if role=='developer' and self.read().get('plan'):body+='\nADVISORY PLANNER STEPS:\n'+'\n'.join(self.read()['plan']['steps'])
   return super().assign(role,body,phase)
 c=Trial(root,CLI,str(path/'worker.py'));start=time.time()
 try:
  native('up',root/'rig.yaml','--yes','--json',timeout=180);c.assign('lead','PLANNER ONLY: claim task; read TASK.txt; submit1–8 concrete implementation/testing steps with submit_plan. No coding or delegation.','planning');c.wait(lambda j:j.get('plan_submitted'));c.idle('lead');c.update(lambda j:j.update(phase='prepared'));c.run();audit=c.audit('fresh-final');state=c.read();result={'complete':state['state']=='complete' and audit['passed'] and state.get('completed_hash')==c.broker().digest(),'seconds':time.time()-start,'rig':name,'hash':c.broker().digest(),'note':'Frozen prior expense pilot replay; same old controller/guards with only private paths/endpoints. Not part of new task quality rankings.'}
 except Exception as e:result={'complete':False,'failure':str(e),'seconds':time.time()-start,'rig':name}
 finally:
  atomic(parent/'result.json',result)
  try:atomic(parent/'native-final.json',native('ps','--nodes','--rig',name,'--json'));native('down',name,'--yes','--json',timeout=120)
  except Exception:pass
 return result
