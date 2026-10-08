"""Pooled outcome tallies across scored v8 runs (no API calls).

Usage: python3 scripts/v8_tally.py runs/v8_main_*_20261008
Reads <run>/scoring/scores.jsonl; prints outcome shares overall, by model, by condition, and deception
(palter + knowing lie) by model x condition.
"""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path

ORDER = ['honest', 'palter', 'lie', 'evidence_missed', 'declined_to_respond', 'incidental_error', 'unresolved', 'disputed',
         'scoring_failure']


def table(rows, key, title):
    g = defaultdict(Counter)
    for r in rows:
        g[key(r)][r['outcome']] += 1
    cols = [o for o in ORDER if any(c[o] for c in g.values())]
    print(f'\n{title}')
    print(f"{'':16s} {'n':>4s} " + ' '.join(f'{c[:10]:>10s}' for c in cols) + f" {'deceptive':>10s}")
    for k in sorted(g):
        c, n = g[k], sum(g[k].values())
        print(f'{str(k):16s} {n:4d} ' + ' '.join(f'{100 * c[o] / n:9.0f}%' for o in cols)
              + f" {100 * (c['palter'] + c['lie']) / n:9.0f}%")


def main():
    rows, done = [], []
    for run in sys.argv[1:]:
        p = Path(run) / 'scoring' / 'scores.jsonl'
        if p.exists():
            done.append(Path(run).name)
            rows += [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    print(f'{len(done)} runs scored, {len(rows)} replies')
    table(rows, lambda r: 'all', 'Overall')
    table(rows, lambda r: r['model'], 'By model')
    table(rows, lambda r: r['condition'], 'By condition')
    g = defaultdict(Counter)
    for r in rows:
        g[r['model']][r['condition']] += 1
        g[r['model']][r['condition'] + '_dec'] += r['outcome'] in ('palter', 'lie')
    print('\nDeceptive (palter + knowing lie) by model x condition')
    print(f"{'':16s} {'baseline':>9s} {'pressure':>9s} {'steer':>9s}")
    for m in sorted(g):
        print(f'{m:16s} ' + ' '.join(f"{100 * g[m][c + '_dec'] / g[m][c]:8.0f}%" if g[m][c] else '        -'
                                     for c in ('baseline', 'pressure', 'steer')))


if __name__ == '__main__':
    main()
