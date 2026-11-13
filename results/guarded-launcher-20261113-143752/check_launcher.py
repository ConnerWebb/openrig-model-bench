import importlib.util,pathlib,tempfile,json,sys
P=pathlib.Path
spec=importlib.util.spec_from_file_location('launcher',(P(__file__).parent/'fleet_programming.py' if (P(__file__).parent/'fleet_programming.py').exists() else P(__file__).parent/'launcher.py'));l=importlib.util.module_from_spec(spec);spec.loader.exec_module(l)
checks=[]
with tempfile.TemporaryDirectory() as d:
 root=P(d);(root/'safe.py').write_text('x=1');(root/'.env').write_text('secret');(root/'.git').mkdir();(root/'.git/key').write_text('secret')
 assert list(l.inventory(root))==['safe.py'];checks.append('credential/hidden-file exclusion')
 (root/'link').symlink_to('/etc/passwd')
 try:l.inventory(root)
 except ValueError:checks.append('symlink rejection')
 else:raise AssertionError('symlink accepted')
job=P('/home/cow/.local/state/openrig-fleet/v2/programming/jobs/20261113-143110-40aded');sys.path.insert(0,str(job/'runtime-source'));import common as c
with tempfile.TemporaryDirectory() as d:
 root=P(d);(root/'calc.py').write_text('def add(a,b):return a-b\n')
 r=c.run_suite(root,{'id':'general'},root/'unused');assert not r['passed'];assert c.feedback(r)['checks']['normal']['failures'];checks.append('broken code rejected with actual feedback')
 (root/'calc.py').write_text('def add(a,b):return a+b\n');assert c.run_suite(root,{'id':'general'},root/'unused')['passed'];checks.append('correct code accepted by frozen checks')
 (root/'calc.py').write_text('import os;os._exit(0)\n');assert not c.run_suite(root,{'id':'general'},root/'unused')['passed'];checks.append('early zero exit cannot masquerade as completed verification')
print(json.dumps({'passed':True,'checks':checks},indent=2))
