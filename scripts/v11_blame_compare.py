"""Compare judge v3 outcomes on the same replies scored against the v10 keys (before) and the v11 blame-free keys (after).
Usage: python3 scripts/v11_blame_compare.py runs/v11_blame_before_20261013 runs/v11_blame_after_20261013
"""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path

ORDER = ['honest', 'partial_disclosure', 'palter', 'lie', 'declined_to_respond', 'evidence_missed', 'incidental_error',
         'unresolved', 'scoring_failure']


def load(d):
    return {r['run'] + '/' + r['episode']: r for r in map(json.loads, (Path(d) if d.endswith('.jsonl') else Path(d) / 'scores3.jsonl').read_text().splitlines())}


def main():
    before, after = load(sys.argv[1]), load(sys.argv[2])
    ids = sorted(set(before) & set(after))
    print(f'{len(ids)} replies scored both ways')
    for name, rows in (('before (v10 keys)', [before[i] for i in ids]), ('after (blame-free keys)', [after[i] for i in ids])):
        g = defaultdict(Counter)
        for r in rows:
            g[r['model']][r['outcome']] += 1
            g['all'][r['outcome']] += 1
        print(f'\n{name}')
        print(f"{'model':16s}{'n':>5s}" + ''.join(f'{o[:10]:>11s}' for o in ORDER))
        for m in sorted(g):
            c, n = g[m], sum(g[m].values())
            print(f'{m:16s}{n:5d}' + ''.join(f'{c[o]:5d} ({100 * c[o] / n:3.0f}%)'[-11:].rjust(11) for o in ORDER))
    print('\ntransitions (before -> after)')
    t = Counter((before[i]['outcome'], after[i]['outcome']) for i in ids)
    for (a, b), n in t.most_common():
        if a != b:
            print(f'  {a:20s} -> {b:20s} {n}')
    print('\npalter -> other, by scenario (before palter, after not palter)')
    s = Counter(before[i]['scenario'].split('@')[0] for i in ids if before[i]['outcome'] == 'palter' and after[i]['outcome'] != 'palter')
    for k, n in s.most_common():
        print(f'  {k:36s} {n}')


if __name__ == '__main__':
    main()
