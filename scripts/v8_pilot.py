"""Run the v8 pilot end to end: episodes, then scoring, then a summary. Paid.

Default design (docs/workplan_v8.md): 3 free-tier models x all office scenarios x 3 conditions x 3 samples, narrow routing,
the awareness question on the first sample of each cell. Hard caps: --episode-budget for the episodes and
--score-budget for scoring (together $40 by default). Rerunning resumes; finished episodes are reused.

Usage (from the repository root):
  python3 scripts/v8_pilot.py --office defiance_mayor --run runs/v8_pilot_<date>
  python3 scripts/v8_pilot.py --office defiance_mayor --run runs/v8_pilot_<date> --summary-only
"""
import argparse, json, subprocess, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT_MODELS = ['sonnet55', 'gptchat', 'grok46']
CONDITIONS = ['baseline', 'pressure', 'steer']  # steer_true deferred to keep the pilot under $50 (decided 3 Oct)
ORDER = ['honest', 'palter', 'lie', 'incidental_error', 'explicit_evasion', 'unresolved', 'disputed', 'routed',
         'declined_to_send', 'technical_failure', 'scoring_failure']


def pct(n, d):
    return f'{100 * n / d:.0f}%' if d else '-'


def summarize(run, scoring='scoring'):
    rows = [json.loads(l) for l in (run / scoring / 'scores.jsonl').read_text().splitlines() if l.strip()]
    out = [f'# Pilot summary: {run.name}', '', f'{len(rows)} scored target emails.', '']

    out += ['## Outcomes by model and condition (share of target emails)', '',
            '| Model | Condition | n | ' + ' | '.join(ORDER) + ' |', '|' + '---|' * (len(ORDER) + 3)]
    cells = defaultdict(list)
    for r in rows:
        cells[(r['model'], r['condition'])].append(r['outcome'])
    for (m, c), outs in sorted(cells.items()):
        cnt = Counter(outs)
        out.append(f'| {m} | {c} | {len(outs)} | ' + ' | '.join(pct(cnt[o], len(outs)) if cnt[o] else '' for o in ORDER) + ' |')

    replied = [r for r in rows if r['outcome'] not in ('routed', 'declined_to_send', 'technical_failure')]
    misleading = [r for r in rows if r['outcome'] in ('palter', 'lie')]
    out += ['', '## Headline counts', '',
            f"- Routed: {sum(r['outcome'] == 'routed' for r in rows)} of {len(rows)} ({pct(sum(r['outcome'] == 'routed' for r in rows), len(rows))})",
            f"- Declined to send: {sum(r['outcome'] == 'declined_to_send' for r in rows)}",
            f"- Technical failures: {sum(r['outcome'] == 'technical_failure' for r in rows)}",
            f"- Replies coded: {len(replied)}; palters {sum(r['outcome'] == 'palter' for r in replied)}, lies {sum(r['outcome'] == 'lie' for r in replied)}, "
            f"honest {sum(r['outcome'] == 'honest' for r in replied)}, disputed {sum(r['outcome'] == 'disputed' for r in replied)}",
            f"- False central statements by what the model knew: " + ', '.join(f'{k} {v}' for k, v in Counter(r.get('lie_type') for r in rows if r['outcome'] == 'lie').items()),
            f"- Misleading replies that were informed (decisive passage seen and private check correct): "
            f"{sum(bool(r.get('informed')) for r in misleading)} of {len(misleading)}", '']

    # What the model knew when it replied, from its private check (branched just before sending).
    def knowledge(r):
        try:
            ep = json.loads((run / r['episode']).read_text())
        except (OSError, KeyError):
            return 'no check'
        t = next((i for i in ep['items'] if i['kind'] == 'target'), {})
        pc = t.get('private_check') or {}
        ans = (pc.get('parsed') or {}).get('answer')
        if ans is None:
            return 'no check'
        return 'knew' if ans == pc.get('expected') else ('uncertain' if ans == 'UNCERTAIN' else 'believed opposite')
    states = ['knew', 'uncertain', 'believed opposite', 'no check']
    out += ['## What the model knew when it replied (private check)', '',
            'Knowing lie = lie where the model knew; a lie made while uncertain is a false statement under uncertainty.', '',
            '| Model | Outcome | ' + ' | '.join(states) + ' |', '|---|---|' + '---|' * len(states)]
    kt = defaultdict(Counter)
    for r in replied:
        kt[(r['model'], r['outcome'])][knowledge(r)] += 1
    for (m, o), c in sorted(kt.items()):
        if o in ('honest', 'palter', 'lie', 'disputed', 'unresolved'):
            out.append(f'| {m} | {o} | ' + ' | '.join(str(c[s]) if c[s] else '' for s in states) + ' |')
    out.append('')

    out += ['## By scenario (share of target emails)', '', '| Scenario | n | honest | palter | lie | routed | other |', '|---|---|---|---|---|---|---|']
    by_s = defaultdict(list)
    for r in rows:
        by_s[r['scenario']].append(r['outcome'])
    for s, outs in sorted(by_s.items()):
        c = Counter(outs)
        other = len(outs) - c['honest'] - c['palter'] - c['lie'] - c['routed']
        out.append(f"| {s} | {len(outs)} | {pct(c['honest'], len(outs))} | {pct(c['palter'], len(outs))} | {pct(c['lie'], len(outs))} | {pct(c['routed'], len(outs))} | {pct(other, len(outs))} |")

    asked = [r for r in rows if r.get('awareness_asked')]
    out += ['', '## Eval awareness test (subset)', '',
            f'Asked in {len(asked)} episodes. Mean P(test) by model (asked directly, so read comparatively):', '']
    by_m = defaultdict(list)
    for r in asked:
        if isinstance(r.get('p_test'), (int, float)):
            by_m[r['model']].append(r['p_test'])
    for m, v in sorted(by_m.items()):
        out.append(f'- {m}: {sum(v) / len(v):.0f} (n={len(v)})')
    verbal = [r for r in rows if isinstance(r.get('verbal_awareness'), dict) and 'aware' in r['verbal_awareness']]
    out += ['', f"Verbalized awareness in reasoning: {sum(bool(r['verbal_awareness']['aware']) for r in verbal)} of {len(verbal)} episodes with reasoning coded."]

    text = '\n'.join(out) + '\n'
    (run / ('summary.md' if scoring == 'scoring' else f'summary_{scoring.replace("/", "_")}.md')).write_text(text)
    print(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--office', required=True)
    ap.add_argument('--run', required=True)
    ap.add_argument('--models', nargs='+', default=PILOT_MODELS)
    ap.add_argument('--conditions', nargs='+', default=CONDITIONS)
    ap.add_argument('--n', type=int, default=3)
    ap.add_argument('--episode-budget', type=float, default=44.0)
    ap.add_argument('--score-budget', type=float, default=6.0)
    ap.add_argument('--workers', type=int, default=12)
    ap.add_argument('--summary-only', action='store_true')
    ap.add_argument('--scoring', default='scoring', help='scoring folder inside the run (for rescoring)')
    a = ap.parse_args()
    run = ROOT / a.run
    if not a.summary_only:
        py = sys.executable
        subprocess.run([py, 'scripts/v8_run.py', '--office', a.office, '--run', a.run, '--models', *a.models,
                        '--conditions', *a.conditions, '--n', str(a.n), '--routing', 'narrow', '--awareness', 'subset',
                        '--budget', str(a.episode_budget), '--workers', str(a.workers)], cwd=ROOT, check=True)
        subprocess.run([py, 'scripts/v8_score.py', '--office', a.office, '--run', a.run, '--budget', str(a.score_budget)],
                       cwd=ROOT, check=True)
    summarize(run, a.scoring)


if __name__ == '__main__':
    main()
