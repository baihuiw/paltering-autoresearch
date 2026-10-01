import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('kimi_review',ROOT/'scripts/kimi_review.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
from palterlab.client import Client,BudgetStop
class KimiReviewTests(unittest.TestCase):
 def test_blinding_whitelist(self):
  c={'question':'Q','proposition':'P','answer':True,'required_disclosures':['fact'],'disclosure_constraints':'none','model':'hidden','condition':'hidden'}
  g={'reply':'R','authoritative_records':[{'record_id':'A','text':'Fact','path':'hidden','access':'hidden'}],'operational_context':'hidden','model':'hidden','pre_reply_history':'hidden'}
  p=m.payload(c,g);self.assertNotIn('hidden',json.dumps(p));self.assertEqual(p['authoritative_records'],[{'record_id':'A','text':'Fact'}])
 def test_unsupported_quote_does_not_pass(self):
  j={'category':'paltering','quote':'absent','evidence_id':'A','material_to_question':True,'necessary_fact_withheld_or_distorted':True,'privacy_justified':False,'specific_wrong_inference':'P','no_false_assertions':True}
  x={'reply':'Other text','authoritative_records':[{'record_id':'A','text':'Fact'}]};self.assertEqual(m.code_result(j,x)['category'],'invalid_evidence')
 def test_budget_includes_pending(self):
  with tempfile.TemporaryDirectory() as d:
   c=Client(d,{'models':{'kimi':'m'},'budget_usd':20},{});c.reserve('one',19.99)
   with self.assertRaises(BudgetStop):c.reserve('two',.02)
   self.assertEqual(c.spent(),19.99)
 def test_resume_skips_existing_results(self):
  from palterlab.common import save
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);save(r/'state.json',{'status':'running'});save(r/'results/old.json',{'review_id':'old','status':'failed'});original=(r/'results/old.json').read_bytes()
   with patch.object(m,'verify',return_value=({'jobs':[{'review_id':'old'}]},{})),patch.object(m,'Client') as client,patch.object(m,'read',side_effect=lambda p: {} if Path(p).name=='billing_catalog.json' else json.loads(Path(p).read_text())),patch.object(m,'refresh'):
    client.return_value.spent.return_value=0.;m.run_study(r)
    client.return_value.call.assert_not_called()
   self.assertEqual((r/'results/old.json').read_bytes(),original)
if __name__=='__main__':unittest.main()
