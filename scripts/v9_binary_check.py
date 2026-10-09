"""Binary-reader sensitivity check (8 Oct): re-read palter-uncertain and partial-disclosure replies with readers who
must choose true state or false belief, plus the no-reply baseline. Paid, about $0.005 per reply.

Usage: python3 scripts/v9_binary_check.py runs/v9_measuretest_20261008 --office-root runs/v8_offices_snapshot_20261008/data/v8/offices
"""
import argparse, json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import v9_score  # noqa: E402
from palterlab.v9.judge3 import read_binary  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('run')
ap.add_argument('--office-root', default=str(ROOT / 'data/v8/offices'))
ap.add_argument('--budget', type=float, default=2)
a = ap.parse_args()
v9_score.OFFICES = Path(a.office_root)
run = ROOT / a.run
rows = [json.loads(l) for l in (run / 'scores3.jsonl').read_text().splitlines() if l.strip()]
pick = [r for r in rows if r['outcome'] == 'partial_disclosure' or r.get('palter_type') == 'uncertain']
client = v9_score.client_for(run, a.budget)
client.cfg['budget_usd'] = client.cfg['effective_budget_usd'] = client.spent() + a.budget  # on top of the run's spend
keys = {}
for r in pick:
    for o in Path(a.office_root).iterdir():
        if (o / 'scenarios').exists() and r['scenario'] in v9_score.load_keys(o.name):
            keys[r['scenario']] = v9_score.load_keys(o.name)[r['scenario']]
            break
with ThreadPoolExecutor(8) as ex:
    priors = dict(zip(keys, ex.map(lambda s: read_binary(client, keys[s], None, f'prior/{s}'), keys)))
    res = list(ex.map(lambda r: read_binary(client, keys[r['scenario']], r['reply'], f"bin/{r['episode']}"), pick))
out = []
for r, b in zip(pick, res):
    out.append({'episode': r['episode'], 'model': r['model'], 'outcome': r['outcome'], 'palter_type': r.get('palter_type'),
                'three_way': r['readers'], 'binary': b, 'binary_prior': priors[r['scenario']]})
(run / 'binary_check.jsonl').write_text(''.join(json.dumps(x) + '\n' for x in out))
for x in out:
    b, p = x['binary'] or {}, x['binary_prior'] or {}
    print(f"{x['outcome']:20s} {str(x['palter_type']):10s} 3-way misled {x['three_way']['misled']:.1f} unsure {x['three_way']['unsure']:.1f} | binary misled {b.get('misled', 0):.1f} (no reply {p.get('misled', 0):.1f})")
print(f'spent ${client.spent():.3f}')
