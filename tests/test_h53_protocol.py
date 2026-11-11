import pathlib,unittest
from benchmarks.run import load,suite_path
ROOT=pathlib.Path(__file__).resolve().parents[1]
POLICY=load(ROOT/'archive/harness/frozen-harness-v5.3/transport_policy.py','h53_transport_policy')
class H53Protocol(unittest.TestCase):
 def test_current_suite_matches_archive_and_original_contracts(self):
  for name in ['common.py','catalog.py','cases.py']:self.assertEqual((suite_path('h5.3')/name).read_bytes(),(ROOT/'archive/harness/frozen-harness-v5.3'/name).read_bytes())
  for name in ['catalog.py','cases.py']:self.assertEqual((suite_path('h5.3')/name).read_bytes(),(suite_path('h4')/name).read_bytes())
 def test_batch_order_and_all_or_nothing(self):
  tools=[{'type':'function','function':{'name':n,'parameters':{'type':'object','properties':{}}}} for n in ['get_task','claim_task']]
  a='<function=get_task></function></tool_call>';b='<function=claim_task></function></tool_call>'
  self.assertEqual([c['name'] for c in POLICY.xml_tools(a+b,tools)],['get_task','claim_task'])
  for bad in [a+b[:-3],a+'<function=unknown></function></tool_call>','Example '+a,a*9]:self.assertIsNone(POLICY.xml_tools(bad,tools))
