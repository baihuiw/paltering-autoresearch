"""Resume only unattempted cells under fidelity-checked manual adaptations."""
from pathlib import Path
import argparse,collections,fcntl,importlib.util,json,os,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from palterlab.common import read,save,now,use_data
from palterlab.client import BudgetStop
spec=importlib.util.spec_from_file_location('followup_v4',ROOT/'scripts/followup_v4.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
RUN=ROOT/'runs/followup_v3_20260924'

def inspect(run):
 cfg,plan=runner.verify(run)
 for manifest in ['portable_freeze.json','reserved_freeze.json']:
  assert all(runner.sha(run/p)==h for p,h in read(run/manifest)['files'].items()),manifest
 outcomes=[read(run/'authoring'/s['slot_id']/'outcome.json') for s in read(run/'scenario_plan.json')['slots']]
 assert len(outcomes)==18
 dev=runner.ANCHORS+[x['case_id'] for x in outcomes if x['status']=='accepted' and x['slot']['split']!='reserved']
 reserved=[x['case_id'] for x in outcomes if x['status']=='accepted' and x['slot']['split']=='reserved']
 rows=[read(p) for p in (run/'episodes').glob('*/result.json')]
 remaining_upper=len(dev)*32+len(reserved)*48-sum(x['phase'] in ['discovery','transfer'] for x in rows)
 assert len(rows)+remaining_upper<=plan['max_target_attempts']
 return cfg,plan,dev,reserved,{'existing_attempts':len(rows),'remaining_upper_bound_before_semantic_checks':remaining_upper,'development_cases':dev,'reserved_cases':reserved,'cap_usd':cfg['budget_usd'],'accounted_usd':runner.spent(run)}

def main():
 p=argparse.ArgumentParser();p.add_argument('--dry-run',action='store_true');a=p.parse_args()
 with (RUN/'run.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  cfg,plan,dev,reserved,counts=inspect(RUN)
  print(json.dumps(counts,indent=2),flush=True)
  if a.dry_run:return
  use_data(RUN/'pack');clients=runner.clients(RUN,cfg);study=runner.Study(RUN,cfg,clients)
  selected=['seed_'+f+'_private' for f in runner.FAMILIES]
  runner.update(RUN,status='running',stage='manual_adaptation_transfer',pid=os.getpid(),active_amendment='003_manual_portable_transfer',transfer_provenance='Assistant-authored faithful adaptations independently checked by Qwen and Kimi; exact-parent replies unchanged.')
  try:
   # Existing result files, including failures, are skipped by Study.batch.
   # All authoring is complete and frozen. No new author call or exact-parent repeat.
   study.discover_fixed(dev,selected)
   study.transfer(selected)
   runner.verify(RUN)
   runner.update(RUN,status='completed' if not study.blocked else 'completed_with_unattempted_transport_slots',stage='finished',selected_settings=runner.FAMILIES,blocked_models=study.blocked)
   save(RUN/'completion_audit.json',{'at':now(),'historical_results_unchanged':True,'pre_amendment_replies_unchanged':True,'cost_usd':runner.spent(RUN),'cap_respected':runner.spent(RUN)<=100,'score_version':runner.VERSION,'reader_calls':0,'selected_settings':runner.FAMILIES,'routine_or_contingent_controls':0,'manual_transfer_amendment':'003_manual_portable_transfer','needs_final_slot_accounting':True})
  except BudgetStop as exc:runner.update(RUN,status='budget_stopped',error=str(exc));raise
  except Exception as exc:runner.update(RUN,status='technical_stopped',error=type(exc).__name__+': '+str(exc));raise
  finally:runner.report(RUN);use_data(ROOT/'data')
if __name__=='__main__':main()
