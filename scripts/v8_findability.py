"""Replay realistic searches against an office drive and report whether the settling evidence is found. Free.

For each scenario: queries = the pilot query bank (data/v8/offices/<office>/pilot_queries.json, weighted by how
often models used them) plus the key's search_terms. Each query runs through the real search tool. Reported:
  found:   share of query uses whose top 5 results include a file marked settles
  snippet: share of query uses whose top 5 snippets show a settling quote (the measured snippet exposure)
Declared exposure (key snippet_exposure) should match: visible -> snippet >= 30%; hidden -> snippet <= 10%.

Usage: python3 scripts/v8_findability.py --office defiance_mayor [--scenario dfm_s2_enews_list] [--show]
"""
import argparse, json, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from palterlab.v8.drive import Drive  # noqa: E402


def overlaps(excerpt, quote):
    """True if the snippet shows the settling quote, or a substantial piece of it (snippets cut quotes at the edges)."""
    if quote in excerpt:
        return True
    q = ' '.join(quote.split())
    e = ' '.join(excerpt.split())
    piece = min(len(q), 60)
    return any(q[i:i + piece] in e for i in range(0, max(1, len(q) - piece + 1), 10))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--office', required=True)
    ap.add_argument('--scenario')
    ap.add_argument('--top', type=int, default=40, help='most-used pilot queries per scenario')
    ap.add_argument('--show', action='store_true', help='print each query')
    a = ap.parse_args()
    base = ROOT / 'data/v8/offices' / a.office
    bank_file = base / 'pilot_queries.json'
    bank = json.loads(bank_file.read_text())['queries'] if bank_file.exists() else {}
    office = json.loads((base / 'office.json').read_text())
    staff = [s['name'] for s in office.get('routing_staff', [])] or ['staff']
    bad = 0
    for kp in sorted((base / 'scenarios').glob('*.json')):
        key = json.loads(kp.read_text())
        sid = key['scenario_id']
        if a.scenario and sid != a.scenario:
            continue
        settle = [q for q in key['decisive_documents'] if q.get('settles')]
        files = {q['path'] for q in settle}
        queries = [(q['query'], q['count']) for q in bank.get(sid, [])[:a.top]] + [(q.lower(), 1) for q in key.get('search_terms', [])]
        with tempfile.TemporaryDirectory() as tmp:
            drive = Drive(base / 'drive', Path(tmp) / 'log.jsonl', staff)
            n = found = shown = 0
            rows = []
            for q, w in queries:
                try:
                    res = drive.search_files(q)['results'][:5]
                except ValueError:
                    continue
                f = any(r['path'] in files for r in res)
                s = any(r['path'] == qq['path'] and overlaps(r['excerpt'], qq['quote']) for r in res for qq in settle)
                n += w
                found += w * f
                shown += w * s
                rows.append((q, w, f, s))
        snip = shown / n if n else 0
        decl = key.get('snippet_exposure')
        ok = (decl == 'visible' and snip >= 0.30) or (decl == 'hidden' and snip <= 0.10)
        bad += not ok
        print(f"{sid:26s} settling files {len(files)}  found in top 5: {found / n if n else 0:4.0%}  "
              f"settling text in snippet: {snip:4.0%}  declared {decl}  {'OK' if ok else 'MISMATCH'}")
        if a.show:
            for q, w, f, s in rows:
                print(f"    {'F' if f else '.'}{'S' if s else '.'} x{w:<2d} {q}")
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
