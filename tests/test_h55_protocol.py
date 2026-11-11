import pathlib,unittest,copy
from benchmarks.run import load,suite_path
ROOT=pathlib.Path(__file__).resolve().parents[1]
P=load(ROOT/'archive/harness/frozen-harness-v5.5/transport_policy.py','h55_transport_policy')
class H55Protocol(unittest.TestCase):
 def test_pinned_suite_matches_original_contracts(self):
  for n in ['common.py','catalog.py','cases.py']:self.assertEqual((suite_path('h5.5')/n).read_bytes(),(ROOT/'archive/harness/frozen-harness-v5.5'/n).read_bytes())
  for n in ['catalog.py','cases.py']:self.assertEqual((suite_path('h5.5')/n).read_bytes(),(suite_path('h4')/n).read_bytes())
 def test_heading_checkpoint_preserves_format_and_rejects_assignment_clipping(self):
  tail='\n\n# Instructions\nThe messages above are earlier context from an ongoing conversation.\n## Original Request\nExact A\n## Progress So Far\nExact B\n## Context Needed to Continue\nExact C\nOnly summarize information explicitly present above. Do not infer or recreate later messages.'
  body={'messages':[{'role':'system','content':'You are a context summarization assistant.'},{'role':'user','content':'# Conversation\n'+'earlier 初期\n'*15000+'recent errors\n'*10000+tail}]};before=copy.deepcopy(body);out,policy=P.bounded_context(body)
  self.assertEqual(body,before);self.assertEqual(out['messages'][0],body['messages'][0]);self.assertTrue(out['messages'][1]['content'].endswith(tail));self.assertLessEqual(P.size({'messages':out['messages'],'tools':[]}),48000);self.assertEqual(policy['summary_envelope'],'heading-checkpoint')
  body['messages'][0]['content']='You are a guarded coding agent.'
  with self.assertRaises(ValueError):P.bounded_context(body)
  body=copy.deepcopy(before);body['tools']=[{'type':'function','function':{'name':'write','parameters':{'type':'object','properties':{}}}}]
  with self.assertRaises(ValueError):P.bounded_context(body)
