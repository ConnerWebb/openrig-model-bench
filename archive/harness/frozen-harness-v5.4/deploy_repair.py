"""Deploy this revision to the stopped, private campaign only."""
from common import *
from preserve import check
import shutil
D=O/('repairs/'+HARNESS_REVISION);F=O/'frozen-harness-v5.4';old=O/'frozen-harness-v5.3';assert HARNESS_REVISION=='h5.4';assert not F.exists()
assert subprocess.check_output(['systemctl','--user','show',P['unit']+'.service','-p','MainPID','--value'],text=True).strip()=='0','Private campaign must already be stopped'
for name in ['repair-checks-latest.json','guard-checks-latest.json','repairs/'+HARNESS_REVISION+'/checks-latest.json','repairs/'+HARNESS_REVISION+'/transport-checks-latest.json','repairs/'+HARNESS_REVISION+'/targeted-checks-latest.json','repairs/'+HARNESS_REVISION+'/compaction-checks-latest.json']:
 row=json.load(open(O/name));assert row['passed'],name
 summary=json.load(open(row['path']));assert all(x['passed'] for x in summary['checks'])
 if name=='guard-checks-latest.json':assert 'guard-qualification-h5.4-' in row['path']
 if name=='repair-checks-latest.json':assert summary['harness_revision']==HARNESS_REVISION
 if '/' not in name:shutil.copy2(O/name,D/name)
assert check('before-h54-deploy')['matches_before']
atomic(D/'old-result-sha256.json',{str(p.relative_to(O)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (O/'runs').glob('*/result.json')})
unit=pathlib.Path('/home/cow/.config/systemd/user')/(P['unit']+'.service');wrapper=I/'runtime/bin/pi';assert str(old) in unit.read_text() and str(old) in wrapper.read_text()
shutil.copy2(unit,D/'previous-campaign.service');shutil.copy2(wrapper,D/'previous-pi-wrapper');shutil.copy2(O/'active-harness-revision.json',D/'previous-active-harness-revision.json')
F.mkdir()
for p in R.iterdir():
 if p.is_file() and (p.suffix in ['.py','.ts','.cjs'] or p.name=='paths.json'):(F/p.name).write_text(p.read_text().replace(str(R),str(F)))
shutil.copytree(old/'replay-profile',F/'replay-profile',ignore=shutil.ignore_patterns('__pycache__'))
for p in (F/'replay-profile').rglob('*'):
 if p.is_file():p.write_text(p.read_text().replace(str(old),str(F)))
atomic(O/'frozen-harness-v5.4-sha256.json',{str(p.relative_to(F)):hashlib.sha256(p.read_bytes()).hexdigest() for p in F.rglob('*') if p.is_file()})
wrapper.write_text(wrapper.read_text().replace(str(old),str(F)));unit.write_text(unit.read_text().replace(str(old),str(F)))
atomic(O/'active-harness-revision.json',{'revision':HARNESS_REVISION,'path':str(F),'at':time.time(),'previous':str(old),'production_changes':False,'reason':'Recognize tool-free Pi compaction envelopes and budget only their transcript while preserving summary instructions, full raw history and ordinary assignment/tool policies. Prior tool/ASan repairs retained.'})
subprocess.run(['systemctl','--user','daemon-reload'],check=True);subprocess.run(['systemctl','--user','reset-failed',P['unit']+'.service'],capture_output=True);subprocess.run(['systemctl','--user','start',P['unit']+'.service'],check=True)
print('Started',HARNESS_REVISION,'production unchanged',check('after-h54-start')['matches_before'])
