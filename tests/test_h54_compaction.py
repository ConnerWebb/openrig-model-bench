import pathlib,unittest,copy
from benchmarks.run import load,suite_path
ROOT=pathlib.Path(__file__).resolve().parents[1];P=load(ROOT/'archive/harness/frozen-harness-v5.4/transport_policy.py','h54_transport_policy')
class H54Compaction(unittest.TestCase):
 def test_source_and_oracles_preserved(self):
  for n in ['common.py','catalog.py','cases.py']:self.assertEqual((suite_path('h5.4')/n).read_bytes(),(ROOT/'archive/harness/frozen-harness-v5.4'/n).read_bytes())
  for n in ['catalog.py','cases.py']:self.assertEqual((suite_path('h5.4')/n).read_bytes(),(suite_path('h4')/n).read_bytes())
 def test_only_summary_transcript_is_budgeted(self):
  b={'messages':[{'role':'system','content':'You are a context summarization assistant.'},{'role':'user','content':[{'type':'text','text':'<conversation>'+'初期 goal\n'*10000+'recent error\n'*10000+'</conversation>EXACT FORMAT'}]}]};old=copy.deepcopy(b);limited,policy=P.bounded_context(b)
  self.assertEqual(b,old);self.assertEqual(limited['messages'][0],b['messages'][0]);self.assertTrue(limited['messages'][1]['content'][0]['text'].endswith('</conversation>EXACT FORMAT'));self.assertLessEqual(P.size({'messages':limited['messages'],'tools':[]}),48000);self.assertEqual(policy['kind'],'compaction-summary')
  b['tools']=[{'type':'function','function':{'name':'write','parameters':{'type':'object','properties':{}}}}]
  with self.assertRaises(ValueError):P.bounded_context(b)
