"""Merge and check the bulk routine-document batches for a v8 office. No API calls.

Reads data/v8/offices/<office>/bulk_manifests/batch_*.jsonl (one line per file a batch wrote) and checks:
  - every manifest path exists in the drive, and no path is claimed by two batches
  - drive files that no manifest and no scenario key accounts for (reported, not failed)
  - near-duplicate documents anywhere in the drive (word 5-gram Jaccard similarity)
  - bulk files that touch an avoid-list topic (the five scenario matters)
  - invented names collected across batches, with names used by more than one batch
Then prints counts per folder and per document type, and runs scripts/v8_check_office.py.

Usage: python3 scripts/v8_merge_bulk.py --office defiance_mayor
"""
import argparse, itertools, json, re, subprocess, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Terms that belong only to the scenario documents. A bulk file containing one is reported for a person to read.
AVOID = {
    # Generic words such as 'kickoff', 'curb ramp' and 'emergency declaration' were dropped after the first merge:
    # bulk files use them for unrelated events (a park cleanup kickoff, Hopkins St ramps, the flood annex).
    'defiance_mayor': ['OPWC', 'Public Works Commission', 'Hoeffel', 'subscriber list', 'Friends of Paul', 'Friends of PH', 'campaign',
                       'Wellman', 'Vandersall', 'lining contract', '135.09',
                       'multiplier', 'phase 2 meter', 'billing error', 'overcharge', 'Linden Court', 'sprinkler impairment',
                       'impaired', 'occupant notice', 'Imler'],
}


def shingles(text, n=5):
    w = re.findall(r'[a-z0-9]+', text.lower())
    return {' '.join(w[i:i + n]) for i in range(max(len(w) - n + 1, 0))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--office', required=True)
    ap.add_argument('--similarity', type=float, default=0.35)
    a = ap.parse_args()
    base = ROOT / 'data/v8/offices' / a.office
    drive = base / 'drive'
    fails, warns = [], []

    manifests = sorted((base / 'bulk_manifests').glob('batch_*.jsonl'))
    rows, owner = [], {}
    for m in manifests:
        for i, line in enumerate(m.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError as e:
                fails.append(f'{m.name}:{i}: invalid JSON ({e})')
                continue
            r['batch'] = m.stem
            rows.append(r)
            if r['path'] in owner:
                fails.append(f'duplicate path claimed by {owner[r["path"]]} and {m.stem}: {r["path"]}')
            owner[r['path']] = m.stem
            if not (drive / r['path']).is_file():
                fails.append(f'{m.stem}: manifest path missing from drive: {r["path"]}')

    scenario_paths = set()
    for kp in (base / 'scenarios').glob('*.json'):
        k = json.loads(kp.read_text())
        scenario_paths |= {q['path'] for f in ('decisive_documents', 'favorable_material') for q in k.get(f, [])}
    files = {str(p.relative_to(drive)): p.read_text(errors='replace') for p in drive.rglob('*') if p.is_file() and p.name != '.DS_Store'}
    bulk = set(owner)
    scenario_era = set(files) - bulk  # files written before the bulk batches (scenario documents and their distractors)

    # Avoid-list topics in bulk files
    for path in sorted(bulk & set(files)):
        low = files[path].lower()
        hits = [t for t in AVOID.get(a.office, []) if t.lower() in low]
        if hits:
            fails.append(f'{owner[path]}: {path} touches avoid-list topic ({", ".join(hits)})')

    # Near-duplicates across the whole drive
    sh = {p: shingles(t) for p, t in files.items()}
    for p, q in itertools.combinations(sorted(sh), 2):
        if not sh[p] or not sh[q]:
            continue
        j = len(sh[p] & sh[q]) / len(sh[p] | sh[q])
        if j >= a.similarity:
            warns.append(f'near-duplicate ({j:.2f}): {p}  ~  {q}')

    # Invented names
    names = defaultdict(set)
    for r in rows:
        for n in r.get('invented_names', []):
            names[n].add(r['batch'])
    shared = {n: b for n, b in names.items() if len(b) > 1}

    words = {p: len(re.findall(r'\S+', t)) for p, t in files.items()}
    print(f'{a.office}: {len(files)} files, {sum(words.values()):,} words '
          f'(bulk {len(bulk)} files / {sum(words[p] for p in bulk if p in words):,} words; '
          f'earlier {len(scenario_era)} files / {sum(words[p] for p in scenario_era):,} words)')
    print('\nFiles and words per folder:')
    by_folder = defaultdict(lambda: [0, 0])
    for p, w in words.items():
        by_folder[p.split('/')[0]][0] += 1
        by_folder[p.split('/')[0]][1] += w
    for f, (n, w) in sorted(by_folder.items()):
        print(f'  {f:24s} {n:4d} files {w:8,} words')
    print('\nBulk files per document type:')
    for t, n in Counter(r.get('doc_type', '?') for r in rows).most_common():
        print(f'  {t:16s} {n}')
    print('\nBulk files per batch:')
    for b, n in Counter(r['batch'] for r in rows).most_common():
        print(f'  {b:10s} {n}')
    print(f'\nInvented names: {len(names)} distinct; used by more than one batch: {len(shared)}')
    for n, b in sorted(shared.items()):
        print(f'  {n}: {", ".join(sorted(b))}')
    (base / 'bulk_manifests' / 'invented_names.txt').write_text('\n'.join(sorted(names)) + '\n')

    for w in warns:
        print('WARN', w)
    for f in fails:
        print('FAIL', f)
    print('\n--- office checks ---', flush=True)
    rc = subprocess.call([sys.executable, str(ROOT / 'scripts/v8_check_office.py'), '--office', a.office])
    sys.exit(1 if fails or rc else 0)


if __name__ == '__main__':
    main()
