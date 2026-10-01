from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from palterlab.archive_study import DEFAULT,prepare,run_study,report
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','run','status','report']);p.add_argument('--run',type=Path,default=DEFAULT);p.add_argument('--calibration-only',action='store_true');a=p.parse_args()
 if a.command=='prepare':print(prepare(a.run))
 elif a.command=='run':run_study(a.run,a.calibration_only)
 else:print(json.dumps(report(a.run),indent=2))
