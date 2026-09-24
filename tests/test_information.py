import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from palterlab.common import ROOT,read,case_by_id
from palterlab.candidates import baseline,materialize,validate_shape
from palterlab.information import RecipientLibraryTools,metadata,public_packet
from palterlab.library import OfficeLibraryTools
from palterlab.evaluate import reader_effect
from palterlab.subject import run_episode,comprehension_check
from palterlab.mock import MockClient
from palterlab.site import build_library
from palterlab.prompts import KNOWLEDGE

class InformationTests(unittest.TestCase):
 def setUp(self):self.cfg=read(ROOT/'config/smoke.json')
 def adapter(self,snap,root,caseid):return RecipientLibraryTools(snap,case_id=caseid,episode_id='test',actor_id='resident',log_path=root/'recipient.jsonl')
 def test_all_six_pairs_preserve_evidence_and_enforce_access(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)
   for caseid in case_by_id():
    snaps={profile:materialize(baseline(caseid,information_profile=profile),root/caseid/profile) for profile in ['private','shared']}
    self.assertEqual(public_packet(snaps['private']),public_packet(snaps['shared']))
    infos={p:metadata(s) for p,s in snaps.items()}
    self.assertEqual(infos['private']['extract_body_sha256'],infos['shared']['extract_body_sha256'])
    manifests={p:{r['record_id']:r for r in read(s/'manifest.json')['files']} for p,s in snaps.items()}
    for rid in manifests['private']:
     if rid!=infos['private']['extract_id']:self.assertEqual(manifests['private'][rid],manifests['shared'][rid])
    for profile,snap in snaps.items():
     info=infos[profile];reader=self.adapter(snap,root/'logs'/caseid/profile,caseid)
     office=OfficeLibraryTools(snap,audience='staff',office_id='p09',episode_id='test',actor_id='office',log_path=root/'logs'/caseid/profile/'office.jsonl')
     self.assertTrue(office.dispatch('read_file',{'path':info['extract_path']},turn=1)['ok'])
     self.assertEqual(reader.dispatch('read_file',{'path':info['extract_path']},turn=1)['ok'],profile=='shared')
     for rid in info['source_ids']:
      r=manifests[profile][rid]
      self.assertEqual(r['access'],'staff');self.assertFalse(reader.dispatch('read_file',{'path':r['path']},turn=1)['ok'])
      self.assertTrue(office.dispatch('read_file',{'path':r['path']},turn=1)['ok'])
     if profile=='private':
      paths={r['path'] for r in reader.dispatch('list_files',{'folder':''},turn=1)['files']}
      self.assertNotIn(info['extract_path'],paths)
      matches=reader.dispatch('search_files',{'query':info['extract_id']},turn=1)['results']
      self.assertNotIn(info['extract_id'],{r['record_id'] for r in matches})
 def test_owner_grant_does_not_publish_private_record(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);snap=materialize(baseline('bellhaven_pet',information_profile='shared'),root/'snapshot');info=metadata(snap)
   public=OfficeLibraryTools(snap,audience='public',office_id='p09',episode_id='test',actor_id='anyone',log_path=root/'public.jsonl')
   self.assertFalse(public.dispatch('read_file',{'path':info['extract_path']},turn=1)['ok'])
   with self.assertRaises(ValueError):self.adapter(snap,root,'bellhaven_fire')
   build_library(snap,root/'site')
   self.assertNotIn('EXTRACT-PET',(root/'site/public/index.html').read_text())
   self.assertIn('EXTRACT-PET',(root/'site/recipient/index.html').read_text())
 def test_false_reference_can_be_corrected_after_lookup(self):
  def panel(values):return [{'model':m,'arm':a,'assessment':{'answer':'YES' if v>50 else 'NO' if v<50 else 'UNCERTAIN','probability_true':v}} for m in self.cfg['readers'] for a,v in values.items() for _ in range(3)]
  pre=panel({'before':50,'honest':98,'false':2,'actual':10})
  post=panel({'before':98,'honest':98,'false':98,'actual':10})
  self.assertTrue(reader_effect(post,self.cfg,True,calibration_panel=pre)[0])
  corrected=panel({'before':98,'honest':98,'false':98,'actual':98})
  self.assertFalse(reader_effect(corrected,self.cfg,True,calibration_panel=pre)[0])
 def test_comprehension_requires_received_support(self):
  class C:
   def call(self,*a,**k):return {'content':json.dumps({'answer':'YES','evidence_ids':['not-read']})}
  case={'proposition':'A fact','answer':True}
  check=comprehension_check(C(),case,'model',[],{'read'}, {'not-read'},'test')
  self.assertTrue(check['correct']);self.assertFalse(check['supported_correct'])
 def test_probe_does_not_enter_office_or_verification_history(self):
  case=case_by_id()['bellhaven_fire'];cfg=copy.deepcopy(self.cfg);cfg['office_turns']=2
  with tempfile.TemporaryDirectory() as t,patch('urllib.request.urlopen',side_effect=AssertionError('Network forbidden')):
   root=Path(t);c=baseline(case['case_id']);snap=materialize(c,root/'snapshot');outer=self
   class Spy(MockClient):
    def call(self,alias,messages,*,label,**kwargs):
     if '/office/' in label or '/lookup/' in label:
      outer.assertNotIn(KNOWLEDGE,json.dumps(messages))
      outer.assertNotIn('probability_true',json.dumps(messages))
     if label.endswith('/message'):return {'content':json.dumps({'done':False,'message':'What happened at the gate?'})}
     return super().call(alias,messages,label=label,**kwargs)
   result=run_episode(Spy(case,'paltering',snap),cfg,case,c,snap,'llama8','fixture',root/'episode')
   self.assertEqual(len(result['turns']),2);self.assertTrue(result['turns'][0]['comprehension']['supported_correct'])
   self.assertEqual(len(result['turns'][0]['recipient_lookups']),8)
 def test_wrong_comprehension_does_not_erase_message_label(self):
  case=case_by_id()['bellhaven_fire']
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);c=baseline(case['case_id']);snap=materialize(c,root/'snapshot')
   class Unaware(MockClient):
    def call(self,alias,messages,*,label,**kwargs):
     if '/comprehension' in label:return {'content':json.dumps({'answer':'UNCERTAIN','evidence_ids':[]})}
     return super().call(alias,messages,label=label,**kwargs)
   r=run_episode(Unaware(case,'paltering',snap),self.cfg,case,c,snap,'llama8','test',root/'episode')
   self.assertEqual(r['turns'][0]['category'],'paltering');self.assertTrue(r['turns'][0]['confirmed_reader_shift']);self.assertEqual(r['reward'],0)
 def test_generator_cannot_invent_access_mode(self):
  c=baseline('bellhaven_fire');c['information_profile']='all_offices_bug'
  with self.assertRaises(ValueError):validate_shape(c,'bellhaven_fire','contextual')

if __name__=='__main__':unittest.main()
