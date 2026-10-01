import json,tempfile,unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch
from scripts import repeat_fixed as r

class RepeatTests(unittest.TestCase):
 def test_exact_balanced_fresh_schedule(self):
  jobs=r.jobs(r.MODELS,10,240924)
  self.assertEqual(len(jobs),480);self.assertEqual(len({j['episode_id'] for j in jobs}),480)
  self.assertEqual(set(Counter((j['model'],j['arm'],j['information_profile']) for j in jobs).values()),{10})
  self.assertEqual(jobs,r.jobs(r.MODELS,10,240924))
  self.assertTrue(all(j['episode_id'].startswith('repeat__') for j in jobs))
  for model in r.MODELS:
   for block in range(10):self.assertEqual(len({(j['arm'],j['information_profile']) for j in jobs if j['model']==model and j['block']==block}),8)
 def test_wilson_zero_is_not_proof_of_zero_rate(self):
  low,high=r.wilson(0,10);self.assertEqual(low,0);self.assertGreater(high,.25)
 def test_run_preserves_failures_and_resume_only_unattempted(self):
  class FakeClient:
   def __init__(self,*a,**kw):self.stage='confirmation'
   def spent(self,*a):return 0
  count=[0]
  def gen(client,cfg,case,c,snap,alias,eid,out):
   count[0]+=1
   if count[0]<=3:raise r.CallFailed('HTTP Error 429: Too Many Requests')
   return {'reply':'Yes, the office received and acknowledged the prior warning.','office_read_paths':[],'source_version':'fixture'}
  def screen(*a):return {'category':'honest','screening_score':0,'reward':0,'reader_tested':False,'judgments':[],'comprehension':{}}
  with tempfile.TemporaryDirectory() as td:
   run=Path(td)/'run';r.prepare(run,['gpt']);original=r.sha(run/'plan.json')
   with patch.object(r,'Client',FakeClient),patch.object(r,'generate',side_effect=gen),patch.object(r,'screen',side_effect=screen),patch('urllib.request.urlopen',side_effect=AssertionError('No network')),patch('builtins.print'):
    s=r.run_study(run);self.assertEqual(s['status'],'technical_stopped');self.assertEqual(s['attempted'],3)
    first={p:r.sha(p) for p in (run/'episodes').glob('*/result.json')}
    s=r.run_study(run);self.assertEqual(s['status'],'completed');self.assertEqual(s['attempted'],80);self.assertEqual(s['completed'],77)
    self.assertEqual(count[0],80)
    self.assertTrue(all(r.sha(p)==h for p,h in first.items()));self.assertEqual(r.sha(run/'plan.json'),original)
    r.run_study(run);self.assertEqual(count[0],80)
   blinded=[json.loads(x) for x in (run/'review/review_sheet.jsonl').read_text().splitlines()]
   self.assertEqual(len(blinded),77)
   self.assertTrue(all(not {'model','arm','candidate','episode_id'} & set(x) for x in blinded))
 def test_existing_reservations_enforce_batch_cap(self):
  from palterlab.client import Client,BudgetStop
  with tempfile.TemporaryDirectory() as td:
   cfg=r.read(r.PARENT/'config.json');cfg.update(budget_usd=20,effective_budget_usd=20)
   client=Client(Path(td),cfg,r.read(r.ROOT/'data/model_catalog.json'));client.stage='confirmation';client.reserve('existing',19.99)
   with self.assertRaises(BudgetStop):client.reserve('next',.02)
if __name__=='__main__':unittest.main()
