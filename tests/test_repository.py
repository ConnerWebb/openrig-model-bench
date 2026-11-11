import io,json,pathlib,tarfile,tempfile,unittest,hashlib,time,os
from benchmarks.run import definitions,suite_path,main
from tools.snapshot import scrub,snapshot
class FrozenSuite(unittest.TestCase):
 def test_hashes_and_track_families(self):
  tasks,cases=definitions();self.assertEqual(len(tasks),15)
  for prefix in ['py-','cpp-']:
   core=[k for k in tasks if k.startswith(prefix) and k not in ['py-team','py-normalizer','cpp-team']];self.assertEqual(len(core),6)
  self.assertEqual(cases.cases('py-csv',71),cases.cases('py-csv',71));self.assertNotEqual(cases.cases('py-csv',71),cases.cases('py-csv',72))
 def test_public_private_checks_are_distinct(self):
  tasks,cases=definitions()
  for id in tasks:self.assertGreater(len(cases.cases(id,1042,True)),len(cases.cases(id,71,False)),id)
 def test_materialization_does_not_include_reference_oracles(self):
  with tempfile.TemporaryDirectory() as tmp:
   d=pathlib.Path(tmp)/'work';main(['materialize','py-csv',str(d)]);self.assertTrue((d/'TASK.txt').exists());self.assertFalse((d/'catalog.py').exists());self.assertFalse((d/'cases.py').exists());self.assertNotIn('reference',json.dumps([p.name for p in d.iterdir()]))
 def test_original_h4_checker_is_byte_identical(self):
  root=pathlib.Path(__file__).resolve().parents[1];source=root/'archive/harness/frozen-harness-v4.2'
  for name in ['common.py','catalog.py','cases.py']:self.assertEqual((suite_path('h4')/name).read_bytes(),(source/name).read_bytes())
class PreviousRepairSuite(unittest.TestCase):
 def test_h5_checker_and_oracles_match_deployment_archive(self):
  root=pathlib.Path(__file__).resolve().parents[1]
  for name in ['common.py','catalog.py','cases.py']:self.assertEqual((suite_path('h5')/name).read_bytes(),(root/'archive/harness/frozen-harness-v5'/name).read_bytes())
  for name in ['catalog.py','cases.py']:self.assertEqual((suite_path('h5')/name).read_bytes(),(suite_path('h4')/name).read_bytes())
 def test_current_materialization_exposes_raw_public_input_and_driver_only(self):
  with tempfile.TemporaryDirectory() as tmp:
   d=pathlib.Path(tmp)/'candidate';main(['--suite','h5','materialize','py-csv',str(d)])
   tasks,cases=definitions('h5');self.assertEqual((d/'PUBLIC_DRIVER.py').read_text(),tasks['py-csv']['driver']);self.assertEqual((d/'public-inputs/case-00.csv').read_text(),cases.cases('py-csv',71,False)[0][0]['csv']);self.assertFalse((d/'cases.py').exists())
class CurrentSuite(unittest.TestCase):
 def test_h51_source_identity_and_historical_oracles(self):
  root=pathlib.Path(__file__).resolve().parents[1]
  for name in ['common.py','catalog.py','cases.py']:self.assertEqual((suite_path('h5.1')/name).read_bytes(),(root/'archive/harness/frozen-harness-v5.1'/name).read_bytes())
  for name in ['catalog.py','cases.py']:self.assertEqual((suite_path('h5.1')/name).read_bytes(),(suite_path('h4')/name).read_bytes())
class SnapshotSafety(unittest.TestCase):
 def test_credentials_scrubbed(self):
  token=('gho_'+'x'*40).encode();data,count=scrub(b'key='+token);self.assertNotIn(token,data);self.assertEqual(count,1)
 def test_completed_failed_interrupted_and_partial_evidence(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp);source=root/'source';repo=root/'repo';source.mkdir();repo.mkdir();(source/'runs').mkdir();(source/'transport').mkdir();status={'phase':'solo','pid':123};(source/'campaign-status.json').write_text(json.dumps(status));(source/'events.jsonl').write_text('{"kind":"test"}\n');(source/'memory-timeline.jsonl').write_text('{"used":1}\n')
   for label,ok,interrupted in [('pass',True,False),('failure',False,False),('interrupted',False,True)]:
    case=source/'runs'/label;project=case/'seats/dev/project';project.mkdir(parents=True);(project/'solution.py').write_text('print("saved")\n');(project/'program').write_bytes(b'\x7fELF\x00saved');agent=case/'transcripts/dev/agent';agent.mkdir(parents=True);(agent/'auth.json').write_text('{"secret":"must-not-upload"}');(project/'escape').symlink_to('/etc/passwd');(case/'result.json').write_text(json.dumps({'id':label,'phase':'solo','language':'python','complete':ok,'interrupted':interrupted,'finished':time.time()-120}))
   (source/'runs/active').mkdir();summary=snapshot(source,repo);self.assertEqual(summary['completed_case_records'],3);self.assertEqual(summary['in_progress_not_scored'],['active']);self.assertEqual(json.loads((source/'campaign-status.json').read_text()),status)
   record=next(r for r in json.loads((repo/'results/source/CASE-INDEX.json').read_text()) if r['directory']=='pass');bundle=repo/'results/source'/record['artifact']
   with tarfile.open(bundle) as archive:
    names=archive.getnames();self.assertTrue(any(n.endswith('/program') for n in names));self.assertFalse(any('auth.json' in n or n.endswith('/escape') for n in names));self.assertEqual(archive.extractfile('seats/dev/project/program').read(),b'\x7fELF\x00saved')
   old=hashlib.sha256(bundle.read_bytes()).hexdigest();snapshot(source,repo);self.assertEqual(hashlib.sha256(bundle.read_bytes()).hexdigest(),old)
   # The campaign can rename an interrupted attempt and reuse its canonical
   # directory. A new result must never point at the earlier artifact bundle.
   case=source/'runs/pass';result=json.loads((case/'result.json').read_text());result['attempts']=2;(case/'result.json').write_text(json.dumps(result));(case/'seats/dev/project/solution.py').write_text('print("new attempt")\n');snapshot(source,repo);new=next(r for r in json.loads((repo/'results/source/CASE-INDEX.json').read_text()) if r['directory']=='pass');self.assertNotEqual(record['artifact'],new['artifact']);self.assertTrue(bundle.exists())
   with tarfile.open(repo/'results/source'/new['artifact']) as archive:self.assertIn(b'new attempt',archive.extractfile('seats/dev/project/solution.py').read())
   with (source/'events.jsonl').open('a') as f:f.write('{"next":2}\n')
   snapshot(source,repo);index=json.loads((repo/'results/source/telemetry/events.jsonl/INDEX.json').read_text());self.assertEqual(index['offset'],(source/'events.jsonl').stat().st_size);self.assertEqual(len(index['chunks']),2)
   q=source/'qualification-growing';q.mkdir();(q/'first.json').write_text('{}');snapshot(source,repo);before=set((repo/'results/source/artifacts/evidence').glob('qualification-growing-*.tar.gz'));(q/'second.json').write_text('{"passed":true}');snapshot(source,repo);after=set((repo/'results/source/artifacts/evidence').glob('qualification-growing-*.tar.gz'));self.assertEqual(len(before),1);self.assertEqual(len(after),2)
if __name__=='__main__':unittest.main()
