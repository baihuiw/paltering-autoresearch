import copy,json,tempfile,unittest,threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from palterlab.common import ROOT,read,save,use_data
from palterlab.client import Client,BudgetStop,StageBudgetStop
from palterlab.stages import collect_evidence,supported_quotes,generate,screen
from palterlab.staged import audit_selection,candidate_key
from palterlab.candidates import baseline,materialize
from palterlab.information import refreeze,sha
from palterlab.experiment import check_config
class StagedTests(unittest.TestCase):
 def setUp(self):self.cfg=read(ROOT/'config/lean175.json')
 def tearDown(self):use_data(ROOT/'data')
 def test_concurrent_reservations_never_cross_cap(self):
  with tempfile.TemporaryDirectory() as t:
   c=Client(t,{**self.cfg,'budget_usd':1,'discovery_budget_usd':1},read(ROOT/'data/model_catalog.json'))
   def attempt(i):
    try:c.reserve(str(i),.3);return True
    except BudgetStop:return False
   with ThreadPoolExecutor(max_workers=8) as p:r=list(p.map(attempt,range(20)))
   self.assertEqual(sum(r),3);self.assertLessEqual(c.spent(),1)
 def test_discovery_reserves_confirmation_funds(self):
  with tempfile.TemporaryDirectory() as t:
   c=Client(t,self.cfg,read(ROOT/'data/model_catalog.json'));c.reserve('one',69)
   with self.assertRaises(StageBudgetStop):c.reserve('two',2)
   c.stage='confirmation';c.reserve('three',100);self.assertEqual(c.spent(),169)
 def test_snippet_and_partial_read_support_but_not_unseen_fact(self):
  text='The gate delayed the emergency vehicle by eleven minutes.'
  observed=collect_evidence('search_files',{'ok':True,'results':[{'record_id':'x','snippet':text}]})
  a={'answer':'YES','supports':[{'evidence_id':'x','quote':text}]}
  self.assertTrue(supported_quotes(a,observed,{'x'},True));a['supports'][0]['quote']='The mayor deliberately caused eleven deaths.'
  self.assertFalse(supported_quotes(a,observed,{'x'},True))
 def test_audit_fixed_and_contains_negative_cases(self):
  rows=[{'episode_id':str(i),'turns':[{'category':c}]} for i,c in enumerate(['honest']*20+['paltering']*20+['unresolved']*20)]
  a=audit_selection(rows,24);self.assertEqual(a,audit_selection(list(reversed(rows)),24));self.assertEqual(len(a),24)
  self.assertEqual(Counter(rows[int(i)]['turns'][0]['category'] for i in a),{'honest':8,'paltering':8,'unresolved':8})
 def test_reserved_records_removed_from_development_snapshot(self):
  import shutil
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);shutil.copytree(ROOT/'data',p/'data');use_data(p/'data');m=read(p/'data/library/manifest.json')
   path='offices/p09/internal/records/TEST-RES.txt';text='Reserved source invisible in development.'
   (p/'data/library/drive'/path).write_text(text);m['files'].append({'path':path,'office_id':'p09','access':'staff','record_id':'TEST-RES','kind':'records','title':'Reserved','sha256':sha(text),'case_id':'new_reserved','split':'reserved'});refreeze(p/'data/library',m)
   snap=materialize(baseline('bellhaven_food'),p/'snapshot');self.assertFalse((snap/'drive'/path).exists());self.assertNotIn('TEST-RES',{r['record_id'] for r in read(snap/'manifest.json')['files']})
 def test_identical_condition_ignores_cosmetic_title(self):
  a=baseline('bellhaven_food');b=copy.deepcopy(a);b['title']='Renamed';self.assertEqual(candidate_key(a),candidate_key(b))
 def test_invalid_scenario_split_rejected(self):
  self.cfg['confirmation_new_ids']=self.cfg['new_case_ids'][:2]
  with self.assertRaises(ValueError):check_config(self.cfg)
 def test_generation_is_saved_before_failed_scoring(self):
  from palterlab.mock import MockClient
  from palterlab.common import case_by_id
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);case=case_by_id()['bellhaven_fire'];c=baseline(case['case_id']);snap=materialize(c,p/'snap');client=MockClient(case,'honest',snap)
   g=generate(client,self.cfg,case,c,snap,'llama8','fixture',p/'out');self.assertTrue((p/'out/generation.json').exists())
   with patch.object(client,'call',side_effect=ValueError('scorer offline')):
    with self.assertRaises(ValueError):screen(client,self.cfg,case,g,'fixture',p/'out')
    self.assertEqual(generate(client,self.cfg,case,c,snap,'llama8','fixture',p/'out')['reply'],g['reply'])
from collections import Counter

class StagedFlowTests(unittest.TestCase):
 def test_null_search_freezes_empty_selection_and_resumes_without_calls(self):
  import shutil
  from palterlab.staged import execute_staged
  from palterlab.experiment import frozen_fingerprint
  class FakeClient:
   def __init__(self,*a,**k):self.stage='discovery'
   def spent(self,*a):return 0
  cfg=read(ROOT/'config/lean175.json');cfg.update(iterations=1,search_models=['llama8'],transfer_models=['gpt'],transfer_repeats=1,audit_replies=0)
  def pack(client,cfg,run):
   dest=Path(run)/'pack';shutil.copytree(ROOT/'data',dest,dirs_exist_ok=True)
   cases=read(dest/'cases.json');plans=read(dest/'information_plans.json');source=cases[0]
   for cid in cfg['new_case_ids']:
    c=copy.deepcopy(source);c['case_id']=cid;cases.append(c);plans[cid]=copy.deepcopy(plans[source['case_id']])
   save(dest/'cases.json',cases);save(dest/'information_plans.json',plans);return dest
  def fake_generate(client,cfg,case,c,snap,a,eid,out):return {'reply':'An accurate answer.','office_read_paths':[],'source_version':'fixture','authoritative_records':[]}
  def fake_screen(*a,**k):return {'category':'honest','judgments':[],'comprehension':{},'reward':0,'screening_score':0}
  def proposal(client,cfg,case,feedback,i):
   c=baseline(case['case_id']);c['condition']='A distinct fictional condition.';return c
  with tempfile.TemporaryDirectory() as t:
   run=Path(t)/'run';approval=Path(t)/'approved.json';save(approval,{'approved':True,'budget_usd':190,'run':str(run.resolve()),'fingerprint':frozen_fingerprint(cfg)})
   with patch('palterlab.staged.Client',FakeClient),patch('palterlab.staged.prepare_pack',side_effect=pack),patch('palterlab.staged.generate',side_effect=fake_generate) as gen,patch('palterlab.staged.screen',side_effect=fake_screen),patch('palterlab.staged.propose',side_effect=proposal),patch('palterlab.staged.validate_semantic',return_value=(True,[])),patch('palterlab.staged.score',return_value={'category':'honest','reward':0}),patch('palterlab.staged.build_library'),patch('palterlab.staged.build_review'),patch('builtins.print'),patch('urllib.request.urlopen',side_effect=AssertionError('No network')):
    result=execute_staged(cfg,run,approval);self.assertEqual(result['status'],'completed');self.assertEqual(read(run/'selection.json')['ids'],[])
    n=gen.call_count;execute_staged(cfg,run,approval);self.assertEqual(gen.call_count,n)
