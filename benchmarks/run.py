"""Portable operator entry point; never starts inference or changes services."""
import argparse,contextlib,hashlib,importlib.util,json,pathlib,shutil,sys,tempfile
ROOT=pathlib.Path(__file__).resolve().parent
def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def suite_path(version):
 if not version.replace('-','').replace('_','').replace('.','').isalnum():raise ValueError('Invalid suite name')
 path=ROOT/'suites'/version
 if not path.is_dir():raise ValueError('Unknown suite: '+version)
 manifest=json.loads((path/'MANIFEST.json').read_text())
 for name,digest in manifest['files'].items():
  if hashlib.sha256((path/name).read_bytes()).hexdigest()!=digest:raise ValueError('Frozen suite changed: '+name+'; create a new version instead')
 return path
def definitions(version='h5.4'):
 path=suite_path(version);return load(path/'catalog.py','benchmark_catalog').TASKS,load(path/'cases.py','benchmark_cases')
@contextlib.contextmanager
def grader(version,output,require_runtime=True):
 path=suite_path(version)
 if require_runtime and sys.platform!='linux':raise RuntimeError('Grading requires Linux, bubblewrap, systemd user services and the documented toolchains')
 for executable in ['bwrap','systemd-run']:
  if require_runtime and not shutil.which(executable):raise RuntimeError('Missing prerequisite: '+executable)
 with tempfile.TemporaryDirectory(prefix='openrig-grader-') as tmp:
  d=pathlib.Path(tmp)
  for name in ['common.py','catalog.py','cases.py']:shutil.copyfile(path/name,d/name)
  (d/'paths.json').write_text(json.dumps({'output':str(output),'isolation':str(d/'isolation')}))
  saved={name:sys.modules.get(name) for name in ['common','catalog','cases']};sys.path.insert(0,str(d))
  try:
   for name in saved:sys.modules.pop(name,None)
   yield load(d/'common.py','standalone_common')
  finally:
   sys.path.remove(str(d))
   for name,previous in saved.items():
    if previous is None:sys.modules.pop(name,None)
    else:sys.modules[name]=previous
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--suite',default='h5.4');sub=p.add_subparsers(dest='command',required=True);sub.add_parser('list');sub.add_parser('verify')
 m=sub.add_parser('materialize');m.add_argument('task');m.add_argument('destination',type=pathlib.Path)
 c=sub.add_parser('check');c.add_argument('task');c.add_argument('project',type=pathlib.Path);c.add_argument('--output',type=pathlib.Path,required=True);c.add_argument('--private',action='store_true');c.add_argument('--seed',type=int);c.add_argument('--mode',choices=['normal','asan','tsan'],default='normal')
 a=p.parse_args(argv);tasks,cases=definitions(a.suite)
 if a.command=='verify':print(json.dumps({'suite':a.suite,'verified':True,'tasks':len(tasks)}));return 0
 if a.command=='list':
  print(json.dumps([{'id':id,'language':t['language'],'contract':t['contract']} for id,t in tasks.items()],indent=2));return 0
 if a.task not in tasks:p.error('Unknown task: '+a.task)
 task=tasks[a.task]
 if a.command=='materialize':
  d=a.destination.resolve()
  if d.exists() and any(d.iterdir()):p.error('Destination must be new or empty; no existing work is overwritten')
  d.mkdir(parents=True,exist_ok=True)
  for name,content in task.get('starter',{}).items():f=d/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(content)
  (d/'TASK.txt').write_text(task['contract']+'\nPython standard library only; save unittest test*.py files. C++20; save standalone test*.cpp or a unittest wrapper compiling into a temporary directory. Add README.md. Private grading stays outside this workspace.\n')
  with grader(a.suite,d,require_runtime=False) as g:
   if hasattr(g,'publish_public'):g.publish_public(task,d)
   else:(d/'PUBLIC_CASES.json').write_text(json.dumps([{'driver_input':x,'expected':y} for x,y in cases.cases(a.task,71,False)],indent=2))
  print(d);return 0
 project=a.project.resolve();output=a.output.resolve()
 if not project.is_dir():p.error('Project directory does not exist')
 if output==project or output.is_relative_to(project):p.error('Grader output must be outside the candidate project')
 if a.mode!='normal' and task['language']!='cpp':p.error('Sanitizers are C++ checks')
 if (output/'result.json').exists():p.error('Result already exists; use a new output directory to preserve previous evidence')
 output.mkdir(parents=True,exist_ok=True);seed=a.seed if a.seed is not None else 1042 if a.private else 71
 with grader(a.suite,output) as g:
  report=g.run_checks(project,task,output/'control',seed=seed,private=a.private,mode=a.mode)
  report['authored_tests']=g.authored_tests(project);report['fixed_checks_passed']=report['passed'];report['passed']&=report['authored_tests']['passed'];report['readme_present']=(project/'README.md').is_file();report['passed']&=report['readme_present'];report.update(suite=a.suite,seed=seed,note='Functional grading only. Full guarded workflow also requires configured review/finalizer/native receipts and complete required-file checks. Run normal, ASan/UBSan and applicable TSan modes separately.')
  target=output/'result.json'
  if target.exists():p.error('Result already exists; use a new output directory to preserve previous evidence')
  g.atomic(target,report);print(json.dumps({'passed':report['passed'],'fixed_checks_passed':report['fixed_checks_passed'],'result':str(target)}));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
