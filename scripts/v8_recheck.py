"""Re-ask missing private checks in finished v8 episodes (paid, about $0.01 each).

A check is missing when the model returned nothing, called a tool despite tools being off, or wrote no readable
answer (about one in ten on 8 Oct). The history up to the sending turn is rebuilt from the saved messages and the
check is asked again with the retry wording; the episode file keeps the first attempt.

Usage: python3 scripts/v8_recheck.py <run_dir> [<run_dir> ...] [--budget 1]
Then rerun scripts/v8_run.py on the run (no new episodes) to refresh summary.json, or read episodes directly.
"""
import argparse, glob, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from palterlab.client import Client  # noqa: E402
from palterlab.common import save  # noqa: E402
from palterlab.v8.env import load_key  # noqa: E402
from palterlab.v8.episode import check_answer, private_check  # noqa: E402
from palterlab.v8.drive import tool_schemas, TERMINAL  # noqa: E402

load_key()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('runs', nargs='+')
    ap.add_argument('--budget', type=float, default=1.0)
    a = ap.parse_args()
    for run in map(Path, a.runs):
        cfg = json.loads((run / 'config.json').read_text())
        client = Client(run, cfg, json.loads((run / 'catalog.json').read_text()), live=True)
        cfg['budget_usd'] = cfg['effective_budget_usd'] = client.spent() + a.budget  # --budget is on top of the run's spend
        fixed = 0
        for ep in sorted(glob.glob(f'{run}/*/*/*/*/episode.json')):
            d = json.loads(Path(ep).read_text())
            t = d['items'][-1]
            if t['kind'] != 'target' or not t.get('private_check') or check_answer(t['private_check']):
                continue
            office_dir = ROOT / 'data/v8/offices' / d['office']
            office = json.loads((office_dir / 'office.json').read_text())
            key = json.loads((office_dir / 'scenarios' / f"{d['scenario']}.json").read_text())
            msgs = d['messages']
            last_user = max(i for i, m in enumerate(msgs) if m['role'] == 'user')
            send = next(i for i in range(last_user, len(msgs)) if msgs[i]['role'] == 'assistant'
                        and any(c['function']['name'] in TERMINAL for c in msgs[i].get('tool_calls') or []))
            roles = ('press_staff',) if d.get('routing', 'narrow') == 'narrow' else ('casework_staff', 'scheduler', 'press_staff')
            tools = tool_schemas([office['prompt_slots'][k] for k in roles], d.get('routing', 'narrow'),
                                 office['prompt_slots'].get('office_short', 'the city'))
            pc = private_check(client, d['model'], msgs[:send], key, f"{d['label']}/private_check/recheck", 5000, tools)
            pc['first_attempt_in_episode'] = t['private_check']
            t['private_check'] = pc
            save(Path(ep), d)
            fixed += bool(check_answer(pc))
            print(f"{d['label']}: {(check_answer(pc) or {}).get('answer')}")
        print(f'{run.name}: {fixed} recovered')


if __name__ == '__main__':
    main()
