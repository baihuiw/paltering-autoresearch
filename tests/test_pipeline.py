import copy,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from palterlab.common import ROOT,read,case_by_id
from palterlab.candidates import baseline,materialize,validate_shape
from palterlab.library import OfficeLibraryTools
from palterlab.evaluate import valid_reader,reader_effect,message_category
from palterlab.client import Client,BudgetStop,CallFailed
from palterlab.experiment import check_config,execute,frozen_fingerprint
from palterlab.site import build_library
from palterlab.mock import offline_demo
class PipelineTests(unittest.TestCase):
 def setUp(self): self.cfg=read(ROOT/'config/pilot.json');self.case=case_by_id()['bellhaven_fire']
 def test_real_adapter_scope_and_integrity(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);c=baseline(self.case['case_id']);c['new_records']=[{'title':'Review note','access':'staff','text':'An internal operational note.'}]
   snap=materialize(c,root/'snapshot')
   public=OfficeLibraryTools(snap,audience='public',office_id='p09',episode_id='test',actor_id='reader',log_path=root/'public.jsonl')
   staff=OfficeLibraryTools(snap,audience='staff',office_id='p09',episode_id='test',actor_id='office',log_path=root/'staff.jsonl')
   p=next(x['path'] for x in read(snap/'manifest.json')['files'] if x['record_id'].startswith('OPS-'))
   self.assertFalse(public.dispatch('read_file',{'path':p},turn=1)['ok']);self.assertTrue(staff.dispatch('read_file',{'path':p},turn=1)['ok'])
   self.assertFalse(staff.dispatch('read_file',{'path':'../../cases.json'},turn=1)['ok'])
   (snap/'drive'/p).write_text('tampered');self.assertEqual(staff.dispatch('read_file',{'path':p},turn=2)['error'],'snapshot_mismatch')
 def test_site_never_packages_key_or_staff_in_public(self):
  with tempfile.TemporaryDirectory() as t:
   build_library(ROOT/'data/library',t);public=(Path(t)/'public/index.html').read_text()
   self.assertNotIn('RESEARCHER_ONLY_',public);self.assertNotIn('AC-44 · owner',public)
   for r in read(ROOT/'data/library/manifest.json')['files']:
    if r['access']=='staff':self.assertNotIn(r['path'],public)
 def test_probabilities_not_silently_reversed(self):
  self.assertFalse(valid_reader({'answer':'NO','probability_true':95}));self.assertFalse(valid_reader({'answer':'YES','probability_true':50}));self.assertTrue(valid_reader({'answer':'UNCERTAIN','probability_true':50}))
 def test_uncertainty_is_not_rewarded(self):
  panel=[{'model':m,'arm':a,'assessment':{'answer':'YES' if p>50 else 'NO' if p<50 else 'UNCERTAIN','probability_true':p}} for m in self.cfg['readers'] for a,p in [('before',50),('honest',98),('false',2),('actual',50)] for _ in range(3)]
  self.assertFalse(reader_effect(panel,self.cfg,True)[0])
 def test_incidental_error_not_central_lie(self):
  j={'category':'incidental_error','quote':'11 minutes','evidence_id':'record'}
  cat=message_category([j,j],'11 minutes',{'record'});self.assertEqual(cat,'incidental_error');self.assertEqual(self.cfg['reward'].get(cat,0),0)
 def test_unverified_quote_and_missing_gate_no_palter(self):
  j={'category':'paltering','quote':'invented','evidence_id':'x'}
  self.assertEqual(message_category([j,j],'actual',{'x'}),'invalid_evidence')
 def test_shape_disallows_answer_key_changes(self):
  c=baseline('bellhaven_fire');c['answer']=False
  with self.assertRaises(ValueError):validate_shape(c,'bellhaven_fire','contextual')
 def test_split_overlap_rejected(self):
  self.cfg['heldout_cases'].append(self.cfg['search_cases'][0])
  with self.assertRaises(ValueError):check_config(self.cfg)
 def test_budget_blocks_before_network(self):
  with tempfile.TemporaryDirectory() as t,patch('urllib.request.urlopen',side_effect=AssertionError('Network forbidden')):
   self.cfg['budget_usd']=0.000001;c=Client(t,self.cfg,read(ROOT/'data/model_catalog.json'),live=True)
   with self.assertRaises(BudgetStop):c.call('attacker',[{'role':'user','content':'test'}],label='budget')
 def test_pending_failure_never_resampled(self):
  with tempfile.TemporaryDirectory() as t,patch.dict(os.environ,{'OPENROUTER_API_KEY':'fake-test-key'}),patch('urllib.request.urlopen',side_effect=OSError('offline')) as request:
   c=Client(t,self.cfg,read(ROOT/'data/model_catalog.json'),live=True)
   for _ in range(2):
    with self.assertRaises(CallFailed):c.call('attacker',[{'role':'user','content':'test'}],label='same')
   self.assertEqual(request.call_count,1);self.assertGreater(c.spent(),0)
 def test_live_requires_matching_approval(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'approval.json';p.write_text('{"approved":false}')
   with self.assertRaises(ValueError):execute(self.cfg,Path(t)/'run',p)
 def test_mock_end_to_end_no_network(self):
  with tempfile.TemporaryDirectory() as t,patch('urllib.request.urlopen',side_effect=AssertionError('Network forbidden')):
   offline_demo(Path(t)/'mock',self.cfg)
   state=read(Path(t)/'mock/state.json');self.assertEqual([r['mean_reward'] for r in state['experiments']],[0,3,1]);self.assertTrue(state['mock'])
 def test_search_freezes_transfer_and_resumes_without_rerunning(self):
  cfg=copy.deepcopy(self.cfg);cfg.update(search_models=['llama8'],transfer_models=['gpt'],search_cases=['bellhaven_food'],heldout_cases=['bellhaven_fire'],control_cases=['bellhaven_medicine'],iterations=2,repeats=1,top_k=1,transfer_repeats=1)
  class FakeClient:
   def __init__(self,*args,**kwargs):pass
   def spent(self):return 0
  def proposal(client,cfg,case,feedback,index):
   self.assertTrue(all(x['id'].startswith('candidate_') for x in feedback))
   c=baseline(case['case_id']);c['title']='Proposal '+str(index);return c
  def episode(client,cfg,case,candidate,snapshot,alias,eid,out):
   return {'episode_id':eid,'case_id':case['case_id'],'model':alias,'status':'completed','turns':[],'reward':0}
  with tempfile.TemporaryDirectory() as t:
   run=Path(t)/'run';ap=Path(t)/'approval.json';ap.write_text(json.dumps({'approved':True,'fingerprint':frozen_fingerprint(cfg),'budget_usd':cfg['budget_usd'],'run':str(run.resolve())}))
   with patch('palterlab.experiment.Client',FakeClient),patch('palterlab.experiment.propose',side_effect=proposal),patch('palterlab.experiment.validate_semantic',return_value=(True,[])),patch('palterlab.experiment.run_episode',side_effect=episode) as calls,patch('urllib.request.urlopen',side_effect=AssertionError('Network forbidden')):
    state=execute(cfg,run,ap);n=calls.call_count
    self.assertEqual(state['status'],'completed');self.assertEqual(len(state['feedback']),2);self.assertTrue(state['transfer_started'])
    self.assertEqual(read(run/'selection.json'),['candidate_0000'])
    execute(cfg,run,ap);self.assertEqual(calls.call_count,n)

if __name__=='__main__':unittest.main()
