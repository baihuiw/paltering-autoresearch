"""Build a read-through page for one v8 office: each scenario's email, key, decisive passages in context,
favorable material and reference replies, plus a sample of routine drive files. No API calls.

Usage: python3 scripts/v8_review_page.py --office defiance_mayor --out <path>.html
"""
import argparse, html, json, random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = 900

CSS = """
/* Layout: one reading column; each scenario is a section with the email first, then the key, then evidence and replies. */
:root {
  --bg: #f3f5f7; --panel: #ffffff; --ink: #1d2733; --muted: #5b6878; --rule: #d6dde5;
  --accent: #1f5f8b; --mark: #fde9a8; --mark-ink: #1d2733; --chip: #e6eef5;
  --sev-low: #3d7a4f; --sev-mod: #a3661a; --sev-high: #b23a3a;
  --ui: "Public Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --letter: "Source Serif 4", Georgia, "Times New Roman", serif;
  --mono: "IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #12171d; --panel: #1a2129; --ink: #e3e8ee; --muted: #9aa7b6; --rule: #2d3742;
  --accent: #7db4dc; --mark: #5c4b12; --mark-ink: #fff6d6; --chip: #22303d;
  --sev-low: #7cc28f; --sev-mod: #e0a55a; --sev-high: #ee8080; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #12171d; --panel: #1a2129; --ink: #e3e8ee; --muted: #9aa7b6; --rule: #2d3742;
  --accent: #7db4dc; --mark: #5c4b12; --mark-ink: #fff6d6; --chip: #22303d;
  --sev-low: #7cc28f; --sev-mod: #e0a55a; --sev-high: #ee8080; color-scheme: dark }
body { background: var(--bg); color: var(--ink); font: 15px/1.55 var(--ui); }
.wrap { max-width: 860px; margin: 0 auto; padding-inline: 16px; padding-block: 28px 64px; display: grid; gap: 28px; }
h1, h2, h3 { text-wrap: balance; line-height: 1.25; margin: 0; }
h1 { font-size: 1.7rem; font-weight: 700; }
h2 { font-size: 1.3rem; font-weight: 700; }
h3 { font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); font-weight: 600; }
p { margin: 0; }
.lede { color: var(--muted); max-width: 65ch; }
nav { display: flex; flex-wrap: wrap; gap: 8px; }
nav a { color: var(--accent); text-decoration: none; border: 1px solid var(--rule); padding: 4px 10px; border-radius: 4px; background: var(--panel); font-size: .9rem; }
nav a:hover, nav a:focus-visible { border-color: var(--accent); outline: none; }
.checklist { background: var(--panel); border: 1px solid var(--rule); border-radius: 6px; padding: 16px 18px; display: grid; gap: 8px; }
.checklist ol { margin: 0; padding-left: 1.2em; display: grid; gap: 4px; max-width: 70ch; }
section.sc { display: grid; gap: 16px; padding-top: 12px; border-top: 2px solid var(--rule); }
.meta { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { font-size: .78rem; background: var(--chip); padding: 2px 8px; border-radius: 3px; letter-spacing: .02em; }
.sev { color: #fff; font-weight: 600; }
.sev.low { background: var(--sev-low); } .sev.moderate { background: var(--sev-mod); } .sev.high { background: var(--sev-high); }
.letter { background: var(--panel); border: 1px solid var(--rule); border-radius: 6px; padding: 14px 16px; font: 16px/1.6 var(--letter); white-space: pre-wrap; min-width: 0; overflow-wrap: anywhere; }
.hdr { font: .82rem/1.5 var(--mono); color: var(--muted); white-space: pre-wrap; margin-bottom: 8px; }
dl { display: grid; grid-template-columns: max-content 1fr; gap: 6px 14px; margin: 0; }
dt { color: var(--muted); font-size: .85rem; } dd { margin: 0; min-width: 0; }
@media (max-width: 560px) { dl { grid-template-columns: 1fr; } dt { margin-top: 6px; } }
.path { font: .8rem var(--mono); color: var(--accent); overflow-wrap: anywhere; }
.excerpt { font: .84rem/1.5 var(--mono); white-space: pre-wrap; background: var(--panel); border: 1px solid var(--rule); border-radius: 4px; padding: 10px 12px; overflow-x: auto; max-height: 340px; overflow-y: auto; }
mark { background: var(--mark); color: var(--mark-ink); padding: 0 1px; }
details { background: var(--panel); border: 1px solid var(--rule); border-radius: 6px; padding: 8px 12px; }
details > summary { cursor: pointer; font-weight: 600; }
details[open] > summary { margin-bottom: 8px; }
.stack { display: grid; gap: 10px; min-width: 0; }
.refs { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr)); }
.refs .letter { font-size: 14.5px; }
.reftitle { font-size: .82rem; font-weight: 600; margin-bottom: 4px; }
@media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto !important; } }
"""


def esc(s):
    return html.escape(s or '')


def excerpt(text, quote):
    i = text.find(quote)
    if i < 0:
        return esc(quote) + '\n[quote not found in file]'
    a, b = max(0, i - CONTEXT), min(len(text), i + len(quote) + CONTEXT)
    pre = ('…' if a else '') + text[a:i]
    post = text[i + len(quote):b] + ('…' if b < len(text) else '')
    return esc(pre) + '<mark>' + esc(quote) + '</mark>' + esc(post)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--office', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--sample', type=int, default=12)
    a = ap.parse_args()
    base = ROOT / 'data/v8/offices' / a.office
    office = json.loads((base / 'office.json').read_text())
    drive = base / 'drive'
    keys = [json.loads(p.read_text()) for p in sorted((base / 'scenarios').glob('*.json'))]
    sys_prompt = __import__('importlib').import_module('palterlab.v8.prompts').system_prompt(office, 'baseline')

    out = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
           f'<title>Defiance Office Review</title>',
           '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
           '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Public+Sans:wght@400;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">',
           f'<style>{CSS}</style>', '<div class="wrap">',
           f'<header class="stack"><h1>{esc(office["office"]["name"])}: scenario read-through</h1>'
           f'<p class="lede">Office 1 of the v8 paltering eval. Mayor {esc(office["official"]["full_name"])} (fictional) of {esc(office["office"]["place"])}. '
           f'Five target emails share one drive of {sum(1 for p in drive.rglob("*") if p.is_file())} files. Highlighted text is what the answer key quotes; the surrounding text is shown as it appears in the file.</p></header>',
           '<nav aria-label="Scenarios">' + ''.join(f'<a href="#{k["scenario_id"]}">{i + 1}. {esc(k["classification"]["topic"][:38])}</a>' for i, k in enumerate(keys)) + '<a href="#bulk">Routine files</a></nav>',
           '<div class="checklist"><h3>What to check</h3><ol>'
           '<li>Does each email read like real mail to a small-city mayor\'s office?</li>'
           '<li>Is the fact something the office would plausibly keep quiet, and something the resident has a right to know?</li>'
           '<li>Do the three validity tests hold: the honest answer needs the fact, the resident\'s decision turns on it, the false belief is about what they asked?</li>'
           '<li>Are the decisive passages buried in ordinary documents, neither too obvious nor impossible to find?</li>'
           '<li>Is the severity tier right?</li>'
           '<li>Are the reference replies right: honest states the fact, both palters are entirely true, the lie contains a false statement?</li>'
           '<li>Do the routine files read like a real city drive?</li></ol></div>',
           f'<details><summary>System prompt the model sees (baseline condition)</summary><div class="letter">{esc(sys_prompt)}</div></details>']

    for i, k in enumerate(keys):
        c, e = k['classification'], k['email']
        out.append(f'<section class="sc" id="{k["scenario_id"]}"><h2>{i + 1}. {esc(c["topic"])}</h2>')
        out.append('<div class="meta">'
                   f'<span class="chip sev {c["severity"]}">{c["severity"]} severity</span>'
                   f'<span class="chip">{c["conduct_type"].replace("_", " ")}</span>'
                   f'<span class="chip">question: {c["question_form"].replace("_", " ")}</span>'
                   f'<span class="chip">harm: {", ".join(c["harm_type"])}</span>'
                   f'<span class="chip">salience: {c["salience"]}</span></div>')
        out.append('<div class="stack"><h3>The email</h3><div class="letter">'
                   f'<div class="hdr">From: {esc(e["name"])}, {esc(e["address"])}\nReceived: {esc(e["received"])}\nTopic: {esc(e["dropdown_topic"])}</div>{esc(e["body"])}</div></div>')
        out.append('<div class="stack"><h3>Answer key</h3><dl>'
                   f'<dt>Fact</dt><dd>{esc(k["fact"])}</dd>'
                   f'<dt>True state</dt><dd>{esc(k["true_proposition"])}</dd>'
                   f'<dt>False belief</dt><dd>{esc(k["false_gist"])}</dd>'
                   f'<dt>Severity rationale</dt><dd>{esc(c["severity_rationale"])}</dd>'
                   f'<dt>Answer needs the fact</dt><dd>{esc(k["validity"]["answer_needs_fact"])}</dd>'
                   f'<dt>Decision turns on it</dt><dd>{esc(k["validity"]["decision_turns_on_it"])}</dd>'
                   f'<dt>Why disclosable</dt><dd>{esc(k["disclosability"]["why_not_confidential"])}</dd>'
                   f'<dt>Condition 3 label</dt><dd>{esc(k["matter_short"])}</dd></dl></div>')
        for field, title in (('decisive_documents', 'Where the fact is (decisive passages)'), ('favorable_material', 'Favorable material a reply could use')):
            out.append(f'<div class="stack"><h3>{title}</h3>')
            for q in k[field]:
                text = (drive / q['path']).read_text(errors='replace')
                out.append(f'<div class="stack"><div class="path">{esc(q["path"])} · {len(text.split()):,} words</div><div class="excerpt">{excerpt(text, q["quote"])}</div></div>')
            out.append('</div>')
        r = k['references']
        out.append('<div class="stack"><h3>Reference replies</h3><div class="refs">')
        for name, label in (('honest', 'Honest'), ('palter_omission', 'Palter by omission'),
                            ('palter_active', f'Active palter ({r["palter_active_tactic"]})'), ('lie', 'Lie')):
            out.append(f'<div><div class="reftitle">{esc(label)}</div><div class="letter">{esc(r[name])}</div></div>')
        out.append('</div></div></section>')

    used = {q['path'] for k in keys for f in ('decisive_documents', 'favorable_material') for q in k[f]}
    pool = sorted(str(p.relative_to(drive)) for p in drive.rglob('*') if p.is_file() and str(p.relative_to(drive)) not in used)
    rnd = random.Random(7)
    by_folder = {}
    for p in pool:
        by_folder.setdefault(p.split('/')[0], []).append(p)
    sample = [rnd.choice(v) for v in by_folder.values()]
    sample += rnd.sample([p for p in pool if p not in sample], max(0, a.sample - len(sample)))
    out.append(f'<section class="sc" id="bulk"><h2>Routine drive files (random sample of {len(sample)})</h2>'
               '<p class="lede">One file from each folder plus a few more, chosen at random. Each shows its first 80 lines.</p>')
    for p in sorted(sample):
        lines = (drive / p).read_text(errors='replace').splitlines()
        out.append(f'<details><summary><span class="path">{esc(p)}</span></summary><div class="excerpt">{esc(chr(10).join(lines[:80]))}'
                   f'{esc(chr(10) + "… (" + str(len(lines) - 80) + " more lines)") if len(lines) > 80 else ""}</div></details>')
    out.append('</section></div>')
    Path(a.out).write_text('\n'.join(out))
    print(a.out)


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(ROOT))
    main()
