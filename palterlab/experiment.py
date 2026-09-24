import copy,json,statistics,fcntl
from collections import Counter
from pathlib import Path
from .common import ROOT,read,save,digest,append,case_by_id,now
from .candidates import baseline,propose,validate_shape,validate_semantic,materialize
from .subject import run_episode
from .client import Client,BudgetStop,CallFailed
from .site import build_library,build_review

class TechnicalStop(RuntimeError):pass

def frozen_fingerprint(cfg):
 files=list((ROOT/'palterlab').glob('*.py'))+list((ROOT/'data/library').rglob('*.txt'))+[ROOT/'data/cases.json',ROOT/'data/library/manifest.json',ROOT/'data/model_catalog.json',ROOT/'data/information_plans.json']
 return digest({'config':cfg,'files':{str(p.relative_to(ROOT)):digest(p.read_text()) for p in sorted(files)}})
def check_config(c):
 if c.get('schema')!='office-search-v2' or c.get('information_profiles')!=['private','shared']:raise ValueError('Use v2 paired information configuration')
 if type(c.get('require_supported_comprehension')) is not bool:raise ValueError('Set comprehension requirement explicitly')
 if c['mode'] not in ['contextual','explicit']:raise ValueError('Track must be contextual or explicit')
 for k in ['iterations','repeats','reader_repeats','office_turns','max_tool_steps','top_k','transfer_repeats','verification_steps']:
  if type(c[k]) is not int or not 1<=c[k]<=1000:raise ValueError('Invalid '+k)
 if c['verification_steps']>6:raise ValueError('At most six lookup actions')
 if c['office_turns']>4:raise ValueError('At most four replies')
 if type(c['budget_usd']) not in [float,int] or c['budget_usd']<=0:raise ValueError('Positive budget required')
 if len(set(c['judges']))!=2 or len(set(c['readers']))!=2:raise ValueError('Two distinct coders and readers required')
 if set(c['search_cases']) & (set(c['heldout_cases'])|set(c['control_cases'])):raise ValueError('Search/test/control overlap')
 if set(c['search_models']) & set(c['transfer_models']):raise ValueError('Search and transfer target models overlap')
 if len({c['models'][a] for a in c['judges']})!=2:raise ValueError('Two distinct judge model IDs required')
 cases=case_by_id();cat=read(ROOT/'data/model_catalog.json');models={m['id']:m for m in cat['data']}
 for k in ['search_cases','heldout_cases','control_cases']:
  if any(x not in cases for x in c[k]):raise ValueError('Unknown case')
 for a in set(c['search_models']+c['transfer_models']+c['readers']+[c['recipient']]):
  if c['models'][a] not in models or 'tools' not in models[c['models'][a]].get('supported_parameters',[]):raise ValueError('Target missing tool support: '+a)
 return c

def execute(cfg,run,approval):
 cfg=check_config(cfg);run=Path(run);run.mkdir(parents=True,exist_ok=True)
 with (run/'run.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  ap=read(approval);fp=frozen_fingerprint(cfg)
  if ap.get('approved') is not True or ap.get('fingerprint')!=fp or ap.get('budget_usd')!=cfg['budget_usd'] or ap.get('run')!=str(run.resolve()):raise ValueError('Missing/mismatched approval for this exact run, code, sources and budget')
  if (run/'protocol.json').exists() and read(run/'protocol.json')['fingerprint']!=fp:raise ValueError('Cannot resume with changed protocol')
  save(run/'protocol.json',{'fingerprint':fp,'config':cfg,'at':now(),'provenance':read(ROOT/'data/provenance.json')})
  client=Client(run,cfg,read(ROOT/'data/model_catalog.json'),live=True);cases=case_by_id()
  state=read(run/'state.json') if (run/'state.json').exists() else {'status':'running','experiments':[],'feedback':[],'transfer_started':False}
  def persist():save(run/'state.json',state);build_review(run,cfg)
  def trial(c,cid,models,repeats,phase):
   cdir=run/'candidates'/cid;cdir.mkdir(parents=True,exist_ok=True);save(cdir/'candidate.json',c)
   snap=materialize(c,cdir/'snapshot');build_library(snap,run/'sites'/cid)
   results=[]
   for alias in models:
    for rep in range(repeats):
     eid=f'{phase}__{cid}__{alias}__{rep:02d}';dest=run/'episodes'/eid
     if (dest/'result.json').exists(): r=read(dest/'result.json')
     else:
      try:r=run_episode(client,cfg,cases[c['case_id']],c,snap,alias,eid,dest)
      except BudgetStop:raise
      except (CallFailed,ValueError,KeyError,TypeError) as e:r={'episode_id':eid,'case_id':c['case_id'],'model':alias,'status':'failed','error':str(e),'reward':0,'turns':[],'information_profile':c['information_profile']}
      r['phase']=phase;r['candidate']=cid;save(dest/'result.json',r)
     results.append(r)
   # Equal model weights; failed episodes remain in the denominator with zero search reward.
   per_model={m:statistics.mean(r['reward'] for r in results if r['model']==m) for m in models}
   counts={m:dict(Counter(r['turns'][0]['category'] if r.get('turns') else 'failed' for r in results if r['model']==m)) for m in models}
   examples=[{'model':r['model'],'category':r['turns'][0]['category'],'reply':r['turns'][0]['reply'][:2500],'reader_effect':r['turns'][0].get('confirmed_reader_shift',False)} for r in sorted(results,key=lambda r:-r['reward']) if r.get('turns')][:4]
   return {'id':cid,'case_id':c['case_id'],'information_profile':c['information_profile'],'phase':phase,'status':'evaluated','mean_reward':statistics.mean(per_model.values()),'per_model':per_model,'message_counts':counts,'reply_examples':examples,'n_attempted':len(results),'n_completed':sum(r['status']=='completed' for r in results),'candidate':c}
  def record(result):
   state['experiments'].append(result);append(run/'results.jsonl',result);persist()
   with (run/'results.tsv').open('a') as f:f.write('\t'.join(str(result.get(k,'')) for k in ['id','case_id','phase','status','mean_reward','n_attempted','n_completed'])+'\n')
   attempts=sum(x.get('n_attempted',0) for x in state['experiments']); completed=sum(x.get('n_completed',0) for x in state['experiments'])
   if attempts>=8 and completed/attempts<0.5:raise TechnicalStop('More than half of target episodes failed technically; review before spending further')
  try:
   done={x['id'] for x in state['experiments']}
   if not (run/'results.tsv').exists():(run/'results.tsv').write_text('id\tcase_id\tphase\tstatus\tmean_reward\tn_attempted\tn_completed\n')
   # Baselines are measured before adaptive searching and never treated as attack successes.
   for caseid in cfg['search_cases']+cfg['control_cases']:
    for profile in cfg['information_profiles']:
     for pressure in [False,True]:
      cid=('contingent_' if pressure else 'routine_')+caseid+'_'+profile
      if cid not in done:record(trial(baseline(caseid,pressure,profile),cid,cfg['search_models'],cfg['repeats'],'baseline'))
   for i in range(cfg['iterations']):
    cid=f'candidate_{i:04d}'
    if cid in done:continue
    if state['transfer_started']:raise ValueError('Search cannot resume after transfer feedback has been inspected')
    caseid=cfg['search_cases'][i%len(cfg['search_cases'])];case=cases[caseid]
    cdir=run/'candidates'/cid
    try:
     c=read(cdir/'candidate.json') if (cdir/'candidate.json').exists() else propose(client,cfg,case,state['feedback'],i)
     save(cdir/'candidate.json',c)
     valid,verdicts=validate_semantic(client,cfg,c,case,cid+'/validate');save(cdir/'validation.json',verdicts)
     if not valid:result={'id':cid,'case_id':caseid,'phase':'search','status':'invalid','mean_reward':0,'candidate':c,'reason':verdicts}
     else:result=trial(c,cid,cfg['search_models'],cfg['repeats'],'search')
    except BudgetStop:raise
    except (CallFailed,ValueError,KeyError,TypeError) as e:result={'id':cid,'case_id':caseid,'phase':'search','status':'failed','mean_reward':0,'reason':str(e)}
    earlier=[x['mean_reward'] for x in state['experiments'] if x['phase']=='search']
    result['selection']='keep' if result['status']=='evaluated' and result['mean_reward']>max(earlier,default=-1) else 'discard'
    # All candidates, including discards/failures, remain available for audit.
    state['feedback'].append({k:result.get(k) for k in ['id','case_id','status','mean_reward','per_model','message_counts','reply_examples','candidate','selection','reason']})
    record(result)
   # Freeze selection before reading a single transfer result; no feedback to attacker.
   selection=run/'selection.json'
   if not selection.exists():
    candidates=sorted((x for x in state['experiments'] if x['phase']=='search' and x['status']=='evaluated'),key=lambda x:(-x['mean_reward'],x['id']))
    save(selection,[x['id'] for x in candidates[:cfg['top_k']]])
   state['transfer_started']=True;persist()
   byid={x['id']:x for x in state['experiments']}
   for selected in read(selection):
    original=byid[selected]['candidate']
    # New target families receive the full selected setting on its original case.
    # Unseen dossiers receive its condition only; case-specific added facts are not transported.
    for caseid in [original['case_id']]+cfg['heldout_cases']+cfg['control_cases']:
     # Compare BOTH profiles for every frozen condition, including the control.
     # No condition edits or feedback after selection. Independent repeats are
     # matched by scenario/condition, not guaranteed identical random seeds.
     for profile in cfg['information_profiles']:
      c=copy.deepcopy(original);c['case_id']=caseid;c['information_profile']=profile
      if caseid!=original['case_id']:c['new_records']=[]
      cid=f'transfer_{selected}_{caseid}_{profile}'
      if cid in byid:continue
      valid,v=validate_semantic(client,cfg,c,cases[caseid],cid+'/validate');save(run/'candidates'/cid/'validation.json',v)
      if not valid:record({'id':cid,'case_id':caseid,'information_profile':profile,'phase':'transfer','status':'invalid','mean_reward':0,'reason':v});continue
      record(trial(c,cid,cfg['transfer_models'],cfg['transfer_repeats'],'transfer'))
      for pressure in [False,True]:
       bid=('transfer_contingent_' if pressure else 'transfer_routine_')+caseid+'_'+profile
       if bid not in {x['id'] for x in state['experiments']}:record(trial(baseline(caseid,pressure,profile),bid,cfg['transfer_models'],cfg['transfer_repeats'],'transfer_baseline'))
   state['status']='completed';state['accounted_usd']=client.spent();persist()
  except (BudgetStop,TechnicalStop) as e:
   state['status']='budget_stopped' if isinstance(e,BudgetStop) else 'technical_stopped';state['stop_reason']=str(e);state['accounted_usd']=client.spent();persist()
  return state
