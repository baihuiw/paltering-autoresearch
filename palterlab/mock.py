"""Deterministic fixtures exercise the real retrieval + scoring + site code, without HTTP."""
import json,copy
from pathlib import Path
from .common import read,save,case_by_id,ROOT
from .candidates import baseline,materialize
from .subject import run_episode
from .prompts import JUDGE,READER,VERIFY
from .information import metadata
from .site import build_library,build_review
class MockClient:
 def __init__(self,case,kind,snapshot): self.case=case;self.kind=kind;self.info=metadata(snapshot)
 def call(self,alias,messages,*,label,**kw):
  case=self.case
  if '/office/' in label:
   step=int(label.rsplit('/',1)[-1]);path=self.info['extract_path']
   if step==0:name,args='read_file',{'path':path}
   else:
    text=case['references'][{'honest':'honest','paltering':'candidate_palter','false_assertion':'false_assertion'}[self.kind]]
    name,args='send_reply',{'body':text}
   return {'role':'assistant','content':None,'tool_calls':[{'id':'fixture_'+str(step),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
  if '/comprehension' in label:
   r={'answer':'YES' if case['answer'] else 'NO','evidence_ids':[self.info['extract_id']],'explanation':'Fixture'}
  elif messages[0]['content']==VERIFY:
   return {'role':'assistant','content':None,'tool_calls':[{'id':'fixture_finish','type':'function','function':{'name':'finish_lookup','arguments':'{}'}}]}
  elif messages[0]['content']==JUDGE:
   d=json.loads(messages[1]['content']);r={'category':self.kind,'material_to_question':True,'necessary_fact_withheld_or_distorted':self.kind=='paltering','privacy_justified':False,'specific_wrong_inference':'No delay occurred' if self.kind!='honest' else '', 'no_false_assertions':self.kind!='false_assertion','quote':d['reply'],'evidence_id':case['evidence_records'][0],'explanation':'DETERMINISTIC SOFTWARE FIXTURE','tactics':['omission'] if self.kind=='paltering' else []}
  elif messages[0]['content']==READER:
   arm=label.split('/')[-2]
   prob={'before':50,'honest':98,'false':2,'actual':98 if self.kind=='honest' else 10}[arm]
   r={'answer':'YES' if prob>50 else 'NO' if prob<50 else 'UNCERTAIN','probability_true':prob,'reason':'DETERMINISTIC SOFTWARE FIXTURE'}
  else:r={'done':True,'message':'Fixture ending'}
  return {'role':'assistant','content':json.dumps(r)}
def offline_demo(out,cfg):
 out=Path(out)
 if out.exists():raise ValueError('Mock output directory must be new')
 out.mkdir(parents=True);cfg=copy.deepcopy(cfg);cfg['office_turns']=1
 case=case_by_id()['bellhaven_fire'];state={'mock':True,'status':'Offline fixtures only; no model results','experiments':[]}
 for i,kind in enumerate(['honest','paltering','false_assertion']):
  cid='fixture_'+kind;c=baseline(case['case_id']);c['title']='Software fixture: '+kind
  save(out/'candidates'/cid/'candidate.json',c);snap=materialize(c,out/'candidates'/cid/'snapshot');build_library(snap,out/'sites'/cid)
  result=run_episode(MockClient(case,kind,snap),cfg,case,c,snap,'llama8',cid,out/'episodes'/cid)
  result['mock']=True;save(out/'episodes'/cid/'result.json',result)
  state['experiments'].append({'id':cid,'case_id':case['case_id'],'status':'MOCK','mean_reward':result['reward']})
 save(out/'state.json',state);save(out/'config.json',cfg);build_review(out,cfg)
