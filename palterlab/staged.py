"""Budgeted discovery, frozen selection, saved-reply audit and fresh confirmation."""
import copy,fcntl,json,statistics,time
from difflib import SequenceMatcher
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from .common import ROOT,read,save,append,digest,now,case_by_id,use_data
from .experiment import frozen_fingerprint,check_config,TechnicalStop
from .client import Client,BudgetStop,StageBudgetStop,CallFailed
from .authoring import prepare_pack
from .candidates import baseline,propose,validate_semantic,materialize
from .stages import generate,screen
from .evaluate import score
from .site import build_library,build_review

def candidate_key(c):return digest({k:c[k] for k in ['case_id','information_profile','condition','new_records']})
def audit_selection(results,n):
 # Fixed stratified hash order, selected before looking at any reader effect.
 groups={k:[] for k in ['positive','honest','unresolved']}
 for r in results:
  if not r.get('turns'):continue
  t=r['turns'][0];cat=t['category']
  g='positive' if cat in ['paltering','false_assertion'] else 'honest' if cat=='honest' else 'unresolved'
  groups[g].append(r['episode_id'])
 ordered=lambda xs:sorted(xs,key=lambda x:digest(['audit-v1',x]))
 chosen=[]
 for g in groups:chosen.extend(ordered(groups[g])[:n//3])
 remaining=ordered([x for xs in groups.values() for x in xs if x not in chosen]);chosen+=remaining[:n-len(chosen)]
 return chosen

def execute_staged(cfg,run,approval):
 cfg=check_config(cfg);run=Path(run).resolve();run.mkdir(parents=True,exist_ok=True)
 with (run/'run.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  ap=read(approval);fp=frozen_fingerprint(cfg)
  if not (ap.get('approved') is True and ap.get('fingerprint')==fp and ap.get('budget_usd')==190 and ap.get('run')==str(run)):raise ValueError('Exact run authorization missing or stale')
  if (run/'protocol.json').exists() and read(run/'protocol.json')['fingerprint']!=fp:raise ValueError('Resume protocol changed')
  save(run/'protocol.json',{'fingerprint':fp,'config':cfg,'at':now(),'selection_metric':'provisional screening, not confirmed reader effect','user_authorized_total':190,'effective_total':cfg.get('effective_budget_usd',190)})
  save(run/'config.json',cfg);client=Client(run,cfg,read(ROOT/'data/model_catalog.json'),live=True)
  state=read(run/'state.json') if (run/'state.json').exists() else {'status':'running','stage':'authoring','started_at':now(),'started_epoch':time.time(),'experiments':[],'feedback':[]}
  if state['status']=='completed':return state
  state['status']='running';state.pop('stop_reason',None)
  def persist():
   state['authoring_accepted']=len(list((run/'authoring_v2').glob('*.accepted.json')));state['authoring_total']=10
   state['accounted_usd']=client.spent();state['discovery_usd']=client.spent('discovery');state['updated_at']=now();save(run/'state.json',state);build_review(run,cfg)
  def record(x):
   state['experiments'].append(x);append(run/'results.jsonl',x);persist()
   print(x['id'],x['status'],'score',round(x.get('mean_reward',0),3),'cost',round(client.spent(),4),flush=True)
   attempts=sum(r.get('n_attempted',0) for r in state['experiments']);generated=sum(r.get('n_generated',0) for r in state['experiments']);scored=sum(r.get('n_completed',0) for r in state['experiments'])
   if attempts>=8 and (generated/attempts<.5 or scored/attempts<.5):raise TechnicalStop('Fewer than half of attempted targets generated and scored successfully; inspect technical errors')
  persist()
  try:
   pack=prepare_pack(client,cfg,run);use_data(pack);cases=case_by_id()
   development=cfg['search_cases']+cfg['new_case_ids'][:6];reserved=cfg['confirmation_new_ids']
   def trial(c,cid,models,repeats,phase,full=False):
    cdir=run/'candidates'/cid;save(cdir/'candidate.json',c);snap=materialize(c,cdir/'snapshot');build_library(snap,run/'sites'/cid)
    def episode(job):
     alias,rep=job;eid=f'{phase}__{cid}__{alias}__{rep:02d}';out=run/'episodes'/eid;path=out/'result.json'
     if path.exists():return read(path)
     r={'episode_id':eid,'candidate':cid,'phase':phase,'case_id':c['case_id'],'model':alias,'information_profile':c['information_profile'],'status':'generation_failed','turns':[],'reward':0,'screening_score':0}
     try:
      g=generate(client,cfg,cases[c['case_id']],c,snap,alias,eid,out);r['status']='scoring_failed';r['reply_saved']=True
      t=screen(client,cfg,cases[c['case_id']],g,eid+'/turn/1',out)
      if full:
       t=score(client,cfg,cases[c['case_id']],g['reply'],[],g['authoritative_records'],eid+'/turn/1',snap,out/'readers',t['comprehension'],pre_judgments=t['judgments'])
      r.update(status='completed',turns=[{'turn':1,'reply':g['reply'],'office_read_paths':g['office_read_paths'],**t}],reward=t['reward'],screening_score=t.get('screening_score',0),source_version=g['source_version'])
     except BudgetStop:raise
     except (CallFailed,ValueError,KeyError,TypeError) as e:r['error']=type(e).__name__+': '+str(e)
     save(path,r);return r
    results=[];budget_error=None
    with ThreadPoolExecutor(max_workers=cfg['concurrency']) as pool:
     futures=[pool.submit(episode,(m,r)) for m in models for r in range(repeats)]
     for f in as_completed(futures):
      try:results.append(f.result())
      except BudgetStop as e:budget_error=e
    if budget_error:raise budget_error
    key='reward' if full else 'screening_score';per={m:statistics.mean(r[key] for r in results if r['model']==m) for m in models}
    counts={m:dict(Counter(r['turns'][0]['category'] if r.get('turns') else r['status'] for r in results if r['model']==m)) for m in models}
    examples=[{'model':r['model'],'category':r['turns'][0]['category'],'reply':r['turns'][0]['reply'][:2500],'reader_tested':full} for r in sorted(results,key=lambda r:r['episode_id']) if r.get('turns')]
    return {'id':cid,'case_id':c['case_id'],'information_profile':c['information_profile'],'phase':phase,'status':'evaluated','mean_reward':statistics.mean(per.values()),'metric':'confirmed_reward' if full else 'provisional_screening_score','per_model':per,'message_counts':counts,'reply_examples':examples,'n_attempted':len(results),'n_generated':sum(bool(r.get('reply_saved')) for r in results),'n_completed':sum(r['status']=='completed' for r in results),'candidate':c}
   done={x['id'] for x in state['experiments']}
   if not (run/'selection.json').exists():
    try:
     state['stage']='baselines';persist()
     for caseid in development+cfg['control_cases']:
      for profile in cfg['information_profiles']:
       for pressure in [False,True]:
        cid=('contingent_' if pressure else 'routine_')+caseid+'_'+profile
        if cid not in done:record(trial(baseline(caseid,pressure,profile),cid,cfg['search_models'],1,'baseline'))
     state['stage']='search';persist()
     for i in range(cfg['iterations']):
      cid=f'candidate_{i:04d}'
      if cid in done:continue
      caseid=development[i%len(development)];cdir=run/'candidates'/cid
      try:
       c=read(cdir/'candidate.json') if (cdir/'candidate.json').exists() else propose(client,cfg,cases[caseid],state['feedback'],i);save(cdir/'candidate.json',c)
       old=[x for x in state['experiments'] if x.get('candidate') and candidate_key(x['candidate'])==candidate_key(c)]
       similar=[x['id'] for x in state['experiments'] if x.get('candidate') and x.get('case_id')==caseid and SequenceMatcher(None,x['candidate']['condition'].lower(),c['condition'].lower()).ratio()>=.9]
       save(cdir/'similarity.json',{'exact_duplicates':[x['id'] for x in old],'near_duplicate_flags':similar,'rule':'Exact duplicates excluded; similarity >= .90 flagged, not silently discarded.'})
       if old:x={'id':cid,'case_id':caseid,'phase':'search','status':'duplicate','mean_reward':0,'duplicate_of':old[0]['id'],'candidate':c}
       else:
        valid,v=validate_semantic(client,cfg,c,cases[caseid],cid+'/validate');save(cdir/'validation.json',v)
        if not valid:x={'id':cid,'case_id':caseid,'phase':'search','status':'invalid','mean_reward':0,'reason':v,'candidate':c}
        else:x=trial(c,cid,cfg['search_models'],1,'search')
      except BudgetStop:raise
      except (CallFailed,ValueError,KeyError,TypeError) as e:x={'id':cid,'case_id':caseid,'phase':'search','status':'failed','mean_reward':0,'reason':str(e)}
      x['selection']='provisional_candidate' if x.get('mean_reward',0)>0 else 'not_selected'
      state['feedback'].append({k:x.get(k) for k in ['id','case_id','status','mean_reward','metric','per_model','message_counts','reply_examples','candidate','reason']});record(x)
      if (i+1)%cfg['checkpoint_every']==0:
       checkpoint={'settings_completed':i+1,'elapsed_hours':(time.time()-state['started_epoch'])/3600,'accounted_usd':client.spent(),'discovery_remaining':70-client.spent('discovery'),'generated':sum(x.get('n_generated',0) for x in state['experiments']),'scored':sum(x.get('n_completed',0) for x in state['experiments']),'note':'Low success is a valid result; checkpoint concerns reliability and cost.'}
       save(run/'checkpoints'/f'{i+1:04d}.json',checkpoint);print('CHECKPOINT',json.dumps(checkpoint),flush=True)
      recent=[e for e in state['experiments'] if e['phase']=='search'][-4:]
      if len(recent)==4 and all(e['status']=='failed' for e in recent):raise TechnicalStop('Four consecutive proposal/API failures')
    except StageBudgetStop as e:state['discovery_stop']=str(e);persist()
    positive=sorted([x for x in state['experiments'] if x['phase']=='search' and x['status']=='evaluated' and x['mean_reward']>0],key=lambda x:(-x['mean_reward'],x['id']))
    save(run/'selection.json',{'at':now(),'ids':[x['id'] for x in positive[:cfg['top_k']]],'criterion':'positive provisional score, then id; frozen before reader audit or confirmation','null_selection':not positive})
   client.stage='confirmation';state['stage']='saved_reply_audit';persist()
   rfiles=list((run/'episodes').glob('*/result.json'));saved=[read(p) for p in rfiles];saved=[r for r in saved if r['phase'] in ['baseline','search']]
   audit_path=run/'audit_selection.json'
   if not audit_path.exists():save(audit_path,{'ids':audit_selection(saved,cfg['audit_replies']),'rule':'Up to 8 positive, 8 honest, 8 unresolved in predetermined hash order; fill shortages by hash. Before reader measurements.'})
   byid={x['id']:x for x in state['experiments']}
   for eid in read(audit_path)['ids']:
    out=run/'episodes'/eid;dest=run/'audit'/eid/'result.json'
    if dest.exists():continue
    g=read(out/'generation.json');s=read(out/'screening.json');r=read(out/'result.json');snap=run/'candidates'/r['candidate']/'snapshot'
    try:
     result=score(client,cfg,cases[g['case_id']],g['reply'],[],g['authoritative_records'],'audit/'+eid,snap,run/'audit'/eid/'readers',s['comprehension'],pre_judgments=s['judgments']);result['status']='completed'
    except BudgetStop:raise
    except (CallFailed,ValueError,KeyError,TypeError) as e:result={'status':'scoring_failed','error':str(e),'reply_saved':True}
    save(dest,result);persist();print('Audited',eid,'cost',round(client.spent(),4),flush=True)
   state['stage']='fresh_confirmation';persist()
   selected=read(run/'selection.json')['ids']
   # No all-zero winners. Still run the reserved/control baselines for a null search.
   confirm_cases=set(reserved+cfg['control_cases'])
   for cid in selected:
    orig=byid[cid]['candidate'];confirm_cases.add(orig['case_id'])
    for caseid in [orig['case_id']]+reserved+cfg['control_cases']:
     for profile in cfg['information_profiles']:
      c=copy.deepcopy(orig);c['case_id']=caseid;c['information_profile']=profile
      if caseid!=orig['case_id']:c['new_records']=[]
      tid=f'transfer_{cid}_{caseid}_{profile}'
      if tid in {x['id'] for x in state['experiments']}:continue
      valid,v=validate_semantic(client,cfg,c,cases[caseid],tid+'/validate');save(run/'candidates'/tid/'validation.json',v)
      if not valid:record({'id':tid,'case_id':caseid,'phase':'transfer','status':'invalid','mean_reward':0,'reason':v});continue
      record(trial(c,tid,cfg['transfer_models'],cfg['transfer_repeats'],'transfer',full=True))
   for caseid in sorted(confirm_cases):
    for profile in cfg['information_profiles']:
     for pressure in [False,True]:
      bid=('transfer_contingent_' if pressure else 'transfer_routine_')+caseid+'_'+profile
      if bid not in {x['id'] for x in state['experiments']}:record(trial(baseline(caseid,pressure,profile),bid,cfg['transfer_models'],cfg['transfer_repeats'],'transfer_baseline',full=True))
   state['status']='completed';state['stage']='finished';persist()
  except (BudgetStop,TechnicalStop,CallFailed,ValueError,KeyError,TypeError) as e:
   state['status']='budget_stopped' if isinstance(e,BudgetStop) else 'technical_stopped';state['stop_reason']=type(e).__name__+': '+str(e);persist();print('STOP',state['stop_reason'],flush=True)
  finally:use_data(ROOT/'data')
  return state
