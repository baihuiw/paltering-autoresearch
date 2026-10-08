"""Checks across all v8 offices (BUILD_GUIDE section 11, merge step). Free: no API calls.

  - people and invented entities named in more than one office (officials, staff, council, entities, email senders)
  - near-identical target or routine emails across offices (word 5-gram Jaccard)
  - near-identical drive documents across offices
  - similar scenario topics across offices
  - counts per category: office type, state, severity, conduct type, question form, snippet exposure
Then runs scripts/v8_check_office.py on each office.

Usage: python3 scripts/v8_cross_office_check.py [--skip-office-checks]
"""
import argparse, itertools, json, re, subprocess, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OFFICES = ROOT / 'data/v8/offices'


def grams(text, n=5):
    w = re.findall(r"[a-z0-9']+", text.lower())
    return {hash(' '.join(w[i:i + n])) for i in range(max(0, len(w) - n + 1))}


def jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def names(o):
    out = {o['official']['full_name']}
    for v in o.get('staff', {}).values():
        if isinstance(v, dict) and v.get('name'):
            out.add(re.sub(r'^(Lt\.|Capt\.|Sgt\.|Dr\.)\s+', '', v['name']))
    for v in (o.get('fictional_council') or o.get('fictional_board') or {}).values():
        out.update(v if isinstance(v, list) else [v])
    out.update(o.get('invented_entities', {}).keys())
    return {n for n in out if isinstance(n, str) and len(n.split()) >= 2}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--skip-office-checks', action='store_true')
    a = ap.parse_args()
    offices = sorted(p.name for p in OFFICES.iterdir() if (p / 'office.json').exists())
    data, fails, warns = {}, [], []
    for oid in offices:
        base = OFFICES / oid
        o = json.loads((base / 'office.json').read_text())
        keys = [json.loads(p.read_text()) for p in sorted((base / 'scenarios').glob('*.json'))]
        rout = json.loads((base / 'routine_emails.json').read_text())['emails'] if (base / 'routine_emails.json').exists() else []
        docs = {str(p.relative_to(base / 'drive')): grams(p.read_text(errors='replace'))
                for p in (base / 'drive').rglob('*') if p.is_file() and p.name != '.DS_Store'}
        senders = {k['email']['name'] for k in keys} | {r['name'] for r in rout}
        data[oid] = dict(office=o, keys=keys, routine=rout, docs=docs, names=names(o), senders=senders)

    # people and entities
    owner = defaultdict(set)
    for oid, d in data.items():
        for n in d['names'] | d['senders']:
            owner[n].add(oid)
    surname = defaultdict(set)
    for oid, d in data.items():
        for n in d['names']:
            surname[n.split()[-1]].add(oid)
    for n, os_ in sorted(owner.items()):
        if len(os_) > 1:
            fails.append(f'name used in {len(os_)} offices: {n} ({", ".join(sorted(os_))})')
    for s, os_ in sorted(surname.items()):
        if len(os_) > 2:
            warns.append(f'surname "{s}" used in {len(os_)} offices ({", ".join(sorted(os_))})')

    # emails
    emails = [(oid, k['scenario_id'], grams(k['email']['body'], 4)) for oid, d in data.items() for k in d['keys']]
    emails += [(oid, r['id'], grams(r['body'], 4)) for oid, d in data.items() for r in d['routine']]
    for (o1, i1, g1), (o2, i2, g2) in itertools.combinations(emails, 2):
        if o1 != o2 and jac(g1, g2) > 0.25:
            warns.append(f'similar emails: {o1}/{i1} and {o2}/{i2} ({jac(g1, g2):.2f})')

    # drive documents
    for (o1, d1), (o2, d2) in itertools.combinations(data.items(), 2):
        for p1, g1 in d1['docs'].items():
            for p2, g2 in d2['docs'].items():
                if len(g1) > 50 and len(g2) > 50 and jac(g1, g2) > 0.3:
                    warns.append(f'near-duplicate documents: {o1}/{p1} and {o2}/{p2} ({jac(g1, g2):.2f})')

    # topics
    tops = [(oid, k['scenario_id'], set(re.findall(r'[a-z]{4,}', k['classification']['topic'].lower()))) for oid, d in data.items() for k in d['keys']]
    for (o1, s1, t1), (o2, s2, t2) in itertools.combinations(tops, 2):
        if o1 != o2 and t1 and t2 and len(t1 & t2) / len(t1 | t2) > 0.4:
            warns.append(f'similar topics: {s1} and {s2} ({", ".join(sorted(t1 & t2))})')

    # counts
    cnt = defaultdict(Counter)
    for oid, d in data.items():
        cnt['office type'][d['office']['office'].get('type')] += 1
        cnt['state'][d['office']['office'].get('state')] += 1
        for k in d['keys']:
            c = k['classification']
            cnt['severity'][c['severity']] += 1
            cnt['conduct type'][c['conduct_type']] += 1
            cnt['question form'][c['question_form']] += 1
            cnt['snippet exposure'][k.get('snippet_exposure')] += 1
    print(f'{len(offices)} offices, {sum(len(d["keys"]) for d in data.values())} scenarios, {sum(len(d["docs"]) for d in data.values())} drive files')
    for cat, c in cnt.items():
        print(f'  {cat}: ' + ', '.join(f'{k} {v}' for k, v in c.most_common()))
    for w in warns:
        print('WARN', w)
    for f in fails:
        print('FAIL', f)
    bad = bool(fails)
    if not a.skip_office_checks:
        for oid in offices:
            r = subprocess.run([sys.executable, str(ROOT / 'scripts/v8_check_office.py'), '--office', oid], capture_output=True, text=True)
            last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else 'no output'
            print(f'office check {oid}: {last}')
            bad |= r.returncode != 0
    print('OK' if not bad else 'FAILURES')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
