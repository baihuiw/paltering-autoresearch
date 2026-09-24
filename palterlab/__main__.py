import argparse,json,functools,http.server
from pathlib import Path
from .common import ROOT,read,save,digest,now,case_by_id
from .experiment import execute,check_config,frozen_fingerprint
from .costs import estimate
from .candidates import baseline,materialize
from .site import build_library,build_review

def main():
 p=argparse.ArgumentParser(description='Closed-library scenario search. All commands except run are offline.')
 p.add_argument('command',choices=['prepare','estimate','authorize','run','mock','report','serve'])
 p.add_argument('--config',default=str(ROOT/'config/pilot.json'));p.add_argument('--out',default=str(ROOT/'runs/pilot'))
 p.add_argument('--approval',default=str(ROOT/'.approvals/pilot.json'));p.add_argument('--port',type=int,default=59603)
 a=p.parse_args();cfg=check_config(read(a.config));out=Path(a.out).resolve()
 if a.command=='estimate':print(json.dumps(estimate(cfg),indent=2));return
 if a.command=='authorize':
  save(a.approval,{'approved':True,'at':now(),'fingerprint':frozen_fingerprint(cfg),'budget_usd':cfg['budget_usd'],'run':str(out),'note':'Create only after the project owner approves this scope and cap.'});print('Authorization recorded for',out);return
 if a.command=='run':
  print(json.dumps(execute(cfg,out,a.approval),indent=2));return
 if a.command=='serve':
  # This serves the researcher review directory. Participants only use bound library tools.
  handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(out))
  print(f'Researcher preview: http://127.0.0.1:{a.port}/review/index.html',flush=True)
  http.server.ThreadingHTTPServer(('127.0.0.1',a.port),handler).serve_forever();return
 if a.command=='report':print(build_review(out,cfg));return
 if a.command=='mock':
  from .mock import offline_demo
  offline_demo(out,cfg);print(build_review(out,cfg));return
 out.mkdir(parents=True,exist_ok=True)
 if (out/'state.json').exists():raise SystemExit('Output exists; choose a fresh directory. Preparation never overwrites a run.')
 save(out/'state.json',{'status':'Prepared; awaiting approval','experiments':[],'mock':False})
 save(out/'estimate.json',estimate(cfg));save(out/'config.json',cfg)
 for profile in cfg['information_profiles']:
  c=baseline(cfg['search_cases'][0],information_profile=profile);cid='routine_preview_'+profile;save(out/'candidates'/cid/'candidate.json',c)
  snap=materialize(c,out/'candidates'/cid/'snapshot');build_library(snap,out/'sites'/cid)
 print(build_review(out,cfg))
if __name__=='__main__':main()
