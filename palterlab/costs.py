from .common import ROOT,read,rates

def estimate(cfg):
 if cfg.get('workflow')=='staged':return staged_estimate(cfg)
 catalog=read(ROOT/'data/model_catalog.json')
 def cost(alias,inp,out):
  a,b=rates(cfg['models'][alias],catalog);return inp*a+out*b
 def lookup_cost(alias,high=False):
  return (cfg['verification_steps']+1 if high else 2)*cost(alias,6500 if high else 3000,700 if high else 200)
 def score_cost(high=False):
  coders=sum(cost(j,14000 if high else 8000,1800 if high else 1200) for j in cfg['judges'])
  beliefs=sum(cost(j,6500 if high else 3000,650 if high else 350)*8*cfg['reader_repeats'] for j in cfg['readers'])
  lookups=sum(4*lookup_cost(j,high) for j in cfg['readers'])
  return coders+beliefs+lookups
 def episode(alias,high=False):
  target=cost(alias,120000 if high else 40000,15000 if high else 6000)
  probe=cost(alias,40000 if high else 15000,1000 if high else 600)
  followups=max(0,cfg['office_turns']-1)*(lookup_cost(cfg['recipient'],high)+cost(cfg['recipient'],6500 if high else 3000,1200))
  return cfg['office_turns']*(target+probe+score_cost(high))+followups
 ns=len(cfg['search_cases']); nc=len(cfg['control_cases']); nh=len(cfg['heldout_cases']);k=cfg['top_k'];it=cfg['iterations']
 baseline_n=(ns+nc)*2*len(cfg['information_profiles'])*cfg['repeats'];search_n=it*cfg['repeats']
 # Upper planning count assumes selected conditions span all development cases; includes matching routine/contingent baselines.
 transfer_n=(k*(1+nh+nc)+2*(min(k,ns)+nh+nc))*len(cfg['information_profiles'])*cfg['transfer_repeats']
 fixed=it*(cost('attacker',15000,3000)+sum(cost(j,6500,1000) for j in cfg.get('validation_judges',cfg['judges'])))+k*(1+nh+nc)*len(cfg['information_profiles'])*sum(cost(j,6500,1000) for j in cfg.get('validation_judges',cfg['judges']))
 typical=fixed+sum((baseline_n+search_n)*episode(m) for m in cfg['search_models'])+sum(transfer_n*episode(m) for m in cfg['transfer_models'])
 heavy=fixed+sum((baseline_n+search_n)*episode(m,True) for m in cfg['search_models'])+sum(transfer_n*episode(m,True) for m in cfg['transfer_models'])
 return {'search_candidates':it,'baseline_episodes':baseline_n*len(cfg['search_models']),'search_episodes':search_n*len(cfg['search_models']),'transfer_and_baseline_episodes_up_to':transfer_n*len(cfg['transfer_models']),'typical_usd':round(typical,2),'heavy_context_usd':round(heavy,2),'with_25pct_contingency_usd':round(heavy*1.25,2),'hard_cap_usd':cfg['budget_usd'],'assumptions':{'target_total_input_tokens_per_reply':[40000,120000],'target_total_output_tokens_per_reply':[6000,15000],'belief_calls_per_reply':8*cfg['reader_repeats']*len(cfg['readers']),'lookup_trajectories_per_reply':4*len(cfg['readers']),'lookup_calls_per_trajectory':[2,cfg['verification_steps']+1],'comprehension_calls_per_reply':1,'verification_sampling':'Three final belief draws share one lookup trajectory per model/arm; trajectories are not independently replicated.','coder_calls_per_reply':len(cfg['judges']),'pricing':'Maximum listed rate over catalog overrides; no cache/batch/free-tier discounts; not a completion guarantee.','errors':'No automatic retries; all attempted calls count. Failed or invalid candidates can reduce realized spend.','learning':'Adaptive prompt/environment search, not gradient RL or fine-tuning; no GPU training cost.'},'models':{a:{'id':m,'input_per_million':rates(m,catalog)[0]*1e6,'output_per_million':rates(m,catalog)[1]*1e6} for a,m in cfg['models'].items()}}


def staged_estimate(cfg):
 catalog=read(ROOT/'data/model_catalog.json')
 def cost(a,i,o):
  p,q=rates(cfg['models'][a],catalog);return p*i+q*o
 def screen(a,high):
  return cost(a,160000 if high else 55000,16000 if high else 6600)+sum(cost(j,14000 if high else 8000,1800 if high else 1200) for j in cfg['judges'])
 def readers(high):
  if cfg.get('reader_evaluation_enabled',True) is False:return 0
  return sum(24*cost(j,6500 if high else 3000,650 if high else 350)+4*(4 if high else 2)*cost(j,6500 if high else 3000,700 if high else 200) for j in cfg['readers'])
 ns=len(cfg['search_cases'])+6;nc=len(cfg['control_cases']);nh=2;k=cfg['top_k'];it=cfg['iterations']
 baselines=(ns+nc)*4*len(cfg['search_models']);search=it*len(cfg['search_models'])
 confirm=(k*(1+nh+nc)+2*(min(k,ns)+nh+nc))*2*cfg['transfer_repeats']*len(cfg['transfer_models'])
 totals=[]
 for high in [False,True]:
  screening=((ns+nc)*4+it)*sum(screen(m,high) for m in cfg['search_models'])
  proposals=it*(cost('attacker',25000 if high else 15000,4000 if high else 3000)+sum(cost(j,10000 if high else 6500,1500 if high else 1000) for j in cfg.get('validation_judges',cfg['judges'])))
  # Full two-coder checks, source checks, reference calibration; one revision allowance at high end.
  author=10*((.4313 if high else .1541))
  validation=k*(1+nh+nc)*2*sum(cost(j,10000 if high else 6500,1500 if high else 1000) for j in cfg.get('validation_judges',cfg['judges']))
  confirmation=confirm*(sum(screen(m,high) for m in cfg['transfer_models'])/len(cfg['transfer_models'])+readers(high))
  audit=cfg['audit_replies']*readers(high)
  totals.append({'screening':screening,'proposals_and_validation':proposals,'new_dossiers':author,'transfer_validation':validation,'confirmation':confirmation,'audit':audit})
 return {'search_candidates':it,'new_scenarios':10,'new_development':6,'new_reserved':4,'reserved_used_now':2,'baseline_episodes':baselines,'search_episodes':search,'transfer_and_baseline_episodes_up_to':confirm,'saved_reply_audits':cfg['audit_replies'] if cfg.get('reader_evaluation_enabled',True) else 0,'typical_usd':round(sum(totals[0].values()),2),'heavy_context_usd':round(sum(totals[1].values()),2),'components':[ {k:round(v,3) for k,v in x.items()} for x in totals],'hard_cap_usd':190,'discovery_cap_usd':70,'assumptions':'Planning range, not measured or a completion guarantee. All authoring, API failures and pending reservations count. Current rates are frozen; no cache discounts assumed. The hard cap can stop the run early. Targets are not trained; this is adaptive condition search.'}
