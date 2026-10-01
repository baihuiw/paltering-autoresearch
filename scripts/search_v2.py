#!/usr/bin/env python3
"""Search v2 commands: prepare | seed | step | report | smoke.

prepare records the owner's approval, the cap and the code hashes; every paid command verifies them,
takes the run's exclusive lock and stops at the cap. The API key must come from the environment.
"""
import argparse, fcntl, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from palterlab.search_v2 import Search, prepare, QualityStop
from palterlab.client import BudgetStop
from palterlab.common import save

SUMMARY = ('archive', 'map', 'operator_stats', 'sessions', 'reasoning', 'cost_by_stage', 'cost_total', 'usage_rows_unmatched')

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('prepare')
    a.add_argument('--config', required=True); a.add_argument('--out', required=True); a.add_argument('--instruction', required=True)
    for name in ('seed', 'step', 'report', 'smoke'):
        b = sub.add_parser(name)
        b.add_argument('--run', required=True)
        if name == 'seed':
            b.add_argument('--n', type=int)
        if name == 'step':
            b.add_argument('--operator'); b.add_argument('--parent'); b.add_argument('--n', type=int, default=1); b.add_argument('--batch', type=int, default=1)
    args = p.parse_args()
    if args.cmd == 'prepare':
        print(prepare(args.config, args.out, args.instruction))
        return
    run = Path(args.run)
    if args.cmd == 'report':
        rep = Search(run).report(); save(run / 'report.json', rep)
        print(json.dumps({k: rep[k] for k in SUMMARY}, indent=1))
        return
    with (run / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        s = Search(run)
        try:
            if args.cmd == 'seed':
                s.seed(s.cfg['seed_slots'][:args.n] if args.n else s.cfg['seed_slots'])
            elif args.cmd == 'step':
                if args.operator or args.parent:
                    for _ in range(args.n):
                        s.step(args.operator, args.parent)
                else:
                    s.run_steps(args.n, args.batch)
            else:
                s.seed(s.cfg['seed_slots'])
                for op in s.cfg.get('smoke_operators', []):
                    try:
                        s.step(op)
                    except ValueError as e:
                        print('step skipped:', e, flush=True)
        except (BudgetStop, QualityStop) as e:
            print('STOPPED:', type(e).__name__, e, flush=True)
        finally:
            rep = s.report(); save(run / 'report.json', rep)
            print(json.dumps({k: rep[k] for k in SUMMARY}, indent=1))

if __name__ == '__main__':
    main()
