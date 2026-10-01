"""Render the local follow-up proposal and review material; no network or API calls."""
from pathlib import Path
import html
import json
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/search_proposal_20260924'

def e(value):
    return html.escape(str(value))

def inline(value):
    escaped = e(value)
    escaped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)
    return re.sub(r'\[([^\]]+)\]\((https://[^\s)]+)\)', r'<a href="\2">\1</a>', escaped)

def markdown(text):
    result, paragraph, table_rows = [], [], []
    def flush_paragraph():
        if paragraph:
            result.append('<p>' + inline(' '.join(paragraph)) + '</p>')
            paragraph.clear()
    def flush_table():
        if not table_rows:
            return
        result.append('<div class="table-wrap"><table><thead><tr>' + ''.join('<th scope="col">' + inline(x) + '</th>' for x in table_rows[0]) + '</tr></thead><tbody>')
        for row in table_rows[1:]:
            result.append('<tr>' + ''.join('<td>' + inline(x) + '</td>' for x in row) + '</tr>')
        result.append('</tbody></table></div>')
        table_rows.clear()
    for line in text.splitlines():
        if line.startswith('|'):
            flush_paragraph()
            cells = [x.strip() for x in line.strip('|').split('|')]
            if not all(set(x) <= set('-: ') for x in cells):
                table_rows.append(cells)
            continue
        flush_table()
        if not line:
            flush_paragraph()
        elif line.startswith('## '):
            flush_paragraph()
            result.append('<h2>' + inline(line[3:]) + '</h2>')
        elif line.startswith('# '):
            flush_paragraph()
            result.append('<h1>' + inline(line[2:]) + '</h1>')
        else:
            paragraph.append(line)
    flush_table()
    flush_paragraph()
    return '\n'.join(result)

STYLE = '''body{font:17px/1.65 system-ui,sans-serif;color:#243243;background:#f5f6f8;margin:0}main{max-width:900px;margin:auto;padding:36px 22px 80px}h1{font-size:32px;line-height:1.2}h2{font-size:23px;margin-top:36px;color:#173451}a{color:#245879}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;background:white;font-size:15px;margin:18px 0}td,th{padding:11px 13px;vertical-align:top;border:1px solid #d8dfe6;text-align:left}th{background:#eaf0f4}details{background:white;border:1px solid #d8dfe6;border-radius:5px;padding:16px;margin:13px 0}summary{cursor:pointer;font-weight:650}summary span{display:block;font-size:14px;font-weight:400;color:#536274}.note{background:#f1f5f7;padding:12px;border-left:3px solid #5b819e}blockquote{margin:18px 0;padding:12px 16px;border-left:3px solid #a3b7c8;white-space:pre-wrap;font-size:15px}small{overflow-wrap:anywhere;color:#63717e}nav{padding:14px 0;border-bottom:1px solid #cad4dc}nav a{margin-right:16px;display:inline-block}.badge{font-size:13px;background:#edf1f4;padding:3px 7px;border-radius:3px;margin-right:6px;display:inline-block}@media(max-width:600px){main{padding:22px 15px}td,th{padding:8px;font-size:14px}h1{font-size:27px}}'''

def main():
    feedback = json.loads((OUT / 'feedback.json').read_text())['examples']
    spec = json.loads((OUT / 'scenario_expansion.json').read_text())
    rows = json.loads((ROOT / 'docs/current_results_20260924/results.json').read_text())['rows']
    by_id = {r['episode']: r for r in rows}
    content = ['<nav><a href="#proposal">Proposal</a><a href="#new-scenarios">18 scenario outlines</a><a href="#authoring">Authoring contract</a><a href="#examples">Reviewed replies</a></nav><section id="proposal">', markdown((OUT / 'proposal.md').read_text()), '</section>']
    content.append('<p><a href="proposal.md">Proposal text</a> · <a href="cost_estimate.json">Cost assumptions</a> · <a href="scenario_expansion.json">Scenario plan and metadata</a></p>')
    content.append('<section id="new-scenarios"><h2>18 scenario outlines</h2><p>These are draft topics and questions. Full dossiers have not been generated. Consequence levels are authoring targets, to be checked against the completed evidence. Internal sensitivity tags have not yet been assigned.</p>')
    for s in spec['slots']:
        content.append(f'''<details id="{e(s['slot_id'])}"><summary>{e(s['title'])}<span>{e(s['topic_label'])} · {e(s['target_public_consequence'])} public consequence · {e(s['split'])}</span></summary><p><b>Incident structure:</b> {e(s['example_incident_structure'])}</p><p><b>Example question:</b> {e(s['example_question'])}</p><p><b>Required evidence:</b> {e(s['evidence_requirements'])}</p><p><b>Authoring wave:</b> {e(s['authoring_wave'])}</p><small>{e(s['adaptation_rule'])}</small></details>''')
    content.append('</section><section id="authoring">')
    contract=(OUT/'scenario_authoring.md').read_text().replace('# Scenario authoring contract','## Scenario authoring contract',1)
    content.append('<details><summary>Authoring contract and implementation requirements</summary>' + markdown(contract) + '</details></section>')
    content.append('<section id="examples"><h2>Replies for calibration</h2><p>The 13 individually selected replies and nine Kimi-coded replies are review material. User feedback and provisional source checks remain separate from historical labels.</p>')
    for f in feedback:
        r = by_id[f['episode_id']]
        content.append(f'''<details><summary>{e(r['model_name'])} · {e(r['case'])}<span>{e(f['assistant_review_title'])}</span></summary><p><b>User feedback:</b> {e(f['user_feedback'])}</p><p class="note"><b>Provisional source review:</b> {e(f['assistant_review_note'])}</p><p><b>Question:</b> {e(r['question'])}</p><p><b>Registered gist:</b> {e(r['gist'])}</p><blockquote>{e(r['reply'])}</blockquote><p><a href="../current_results_20260924/index.html#case-{e(r['uid'])}">Original case and evidence</a></p><small>{e(f['episode_id'])}</small></details>''')
    content.append('</section><p><a href="feedback.json">Saved example feedback</a></p>')
    page = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Follow-up search proposal</title><style>' + STYLE + '</style></head><body><main>' + '\n'.join(content) + '</main></body></html>'
    (OUT/'index.html').write_text(page)
    print(f'Wrote {OUT / "index.html"}: {len(spec["slots"])} outlines, {len(feedback)} reply examples.')

if __name__ == '__main__':
    main()
