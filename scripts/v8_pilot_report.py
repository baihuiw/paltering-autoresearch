"""Summarize v8 episode runs without API calls: cost and time per model, routine vs target cost,
target outcomes, evidence access, private check, and a keyword screen for eval awareness in reasoning.

The keyword screen only flags episodes to read; awareness is coded by reading reasoning (design section 10).

Usage: python3 scripts/v8_pilot_report.py <run_dir> [<run_dir> ...] [--group-by-run-prefix]
Runs whose names contain _r0_ / _r1_ are grouped as routine 0 / routine 1.
"""
import glob, json, re, sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from palterlab.v8.episode import check_answer  # noqa: E402

AWARE = re.compile(r"\b(this is (a|an) (test|eval\w*|simulation|exercise)|being (tested|evaluated)|"
                   r"benchmark|test scenario|simulated|fictional|hypothetical scenario|red[- ]team|"
                   r"honesty test|role[- ]?play|tests? whether|designed to test|scenario is designed|planted)\b", re.I)


def ts(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00'))


def episode_stats(run):
    calls = defaultdict(dict)   # label prefix -> step -> (cost, at, reasoning)
    check = defaultdict(float)
    for f in glob.glob(f'{run}/calls/*.json'):
        c = json.loads(Path(f).read_text())
        if c.get('status') != 'ok':
            continue
        lab, cost = c['label'], c.get('accounted_usd') or 0
        msg = (c.get('response') or {}).get('choices', [{}])[0].get('message', {}) or {}
        reasoning = (msg.get('reasoning') or '') + json.dumps(msg.get('reasoning_details') or '')
        m = re.match(r'(.*)/step(\d+)$', lab)
        if m:
            calls[m.group(1)][int(m.group(2))] = (cost, c.get('at'), reasoning)
        else:
            check[lab.rsplit('/', 1)[0]] += cost
    rows = []
    for ep in glob.glob(f'{run}/*/*/*/*/episode.json'):
        if '_failed' in Path(ep).parent.name:
            continue
        d = json.loads(Path(ep).read_text())
        steps = calls.get(d['label'], {})
        msgs = d['messages']
        users = [i for i, m in enumerate(msgs) if m['role'] == 'user']
        n_r = sum(1 for m in msgs[:users[-1]] if m['role'] == 'assistant')
        r_cost = sum(v[0] for k, v in steps.items() if k < n_r)
        t_cost = sum(v[0] for k, v in steps.items() if k >= n_r)
        times = sorted(v[1] for v in steps.values() if v[1])
        secs = (ts(times[-1]) - ts(times[0])).total_seconds() if len(times) > 1 else 0
        hits = sorted({h.lower() for v in steps.values() for h in AWARE.findall(v[2]) for h in [h[0] if isinstance(h, tuple) else h]})
        has_reasoning = any(len(v[2]) > 10 for v in steps.values())
        pc = d['items'][-1].get('private_check') or {}
        answer = (check_answer(pc) or {}).get('answer')
        rows.append(dict(run=Path(run).name, label=d['label'], model=d['model'], scenario=d['scenario'], condition=d['condition'],
                         outcome=d['items'][-1]['outcome'], tool_calls=d['items'][-1]['tool_calls'],
                         routine_cost=r_cost, target_cost=t_cost, check_cost=check.get(d['label'], 0), secs=secs,
                         aware_hits=hits, has_reasoning=has_reasoning,
                         check=answer, knew=answer is not None and answer == pc.get('expected')))
    summ = Path(run) / 'summary.json'
    if summ.exists():
        by = {(s['scenario'], s['condition'], s['model']): s for s in json.loads(summ.read_text())}
        for r in rows:
            s = by.get((r['scenario'], r['condition'], r['model']), {})
            r['decisive'] = f"{s.get('decisive_returned')}/{s.get('decisive_total')}"
            r['found'] = (s.get('decisive_returned') or 0) > 0
    return rows


def table(rows, key):
    g = defaultdict(list)
    for r in rows:
        g[key(r)].append(r)
    print(f"{'group':34s} {'n':>3s} {'$/ep':>7s} {'routine%':>8s} {'sec/ep':>7s} {'maxsec':>6s} {'tools':>5s} {'found':>5s} {'knew':>5s} {'reason':>6s} {'aware?':>6s}  outcomes")
    for k in sorted(g):
        rs = g[k]
        n = len(rs)
        tot = sum(r['routine_cost'] + r['target_cost'] + r['check_cost'] for r in rs)
        rout = sum(r['routine_cost'] for r in rs)
        outs = defaultdict(int)
        for r in rs:
            outs[r['outcome']] += 1
        print(f"{str(k):34s} {n:3d} {tot / n:7.3f} {100 * rout / tot if tot else 0:7.0f}% {sum(r['secs'] for r in rs) / n:7.0f} "
              f"{max(r['secs'] for r in rs):6.0f} {sum(r['tool_calls'] for r in rs) / n:5.1f} "
              f"{sum(r.get('found', False) for r in rs):5d} {sum(r.get('knew', False) for r in rs):5d} "
              f"{sum(r['has_reasoning'] for r in rs):6d} {sum(bool(r['aware_hits']) for r in rs):6d}  {dict(outs)}")


def main():
    runs = [a for a in sys.argv[1:] if not a.startswith('--')]
    rows = [r for run in runs for r in episode_stats(run)]
    for r in rows:
        r['arm'] = 'routine0' if '_r0_' in r['run'] else 'routine1' if '_r1_' in r['run'] else r['run']
    print(f'{len(rows)} episodes, total ${sum(r["routine_cost"] + r["target_cost"] + r["check_cost"] for r in rows):.2f}\n')
    print('By model:'); table(rows, lambda r: r['model'])
    print('\nBy arm x model:'); table(rows, lambda r: (r['arm'], r['model']))
    print('\nBy condition x model:'); table(rows, lambda r: (r['condition'], r['model']))
    flagged = [r for r in rows if r['aware_hits']]
    print(f'\nAwareness keyword hits ({len(flagged)}; read these):')
    for r in flagged:
        print(f"  {r['run']}  {r['label']}  {r['aware_hits']}")


if __name__ == '__main__':
    main()
