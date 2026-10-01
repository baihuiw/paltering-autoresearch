"""Export a read-only snapshot of saved Qwen paltering flags and their settings."""
import argparse
import html
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
NAMES = {'llama8': 'Llama 3.1 8B', 'gemma27': 'Gemma 3 27B',
         'qwen9': 'Qwen 3.5 9B', 'deepseek': 'DeepSeek V4.1 Flash',
         'mistral24': 'Mistral Small 3.2 24B', 'nemotron30': 'Nemotron 3 Nano 30B A3B',
         'sonnet': 'Claude Sonnet 5', 'gpt': 'GPT-5.6 Luna'}

def read(p):
    return json.loads(p.read_text())

def esc(s):
    return html.escape(str(s), quote=True)

def paragraph(s):
    return '<div class="prose">' + esc(s) + '</div>'

def render(run):
    cfg = read(run / 'config.json')
    adjudication_path = run / 'review/adjudications.json'
    adjudications = read(adjudication_path) if adjudication_path.exists() else {}
    rows = []
    for p in sorted((run / 'episodes').glob('*/result.json')):
        r = read(p)
        for t in r.get('turns', []):
            js = [j for j in t.get('judgments', []) if j.get('model') == 'judge_qwen']
            if len(js) != 1 or js[0].get('category') != 'paltering':
                continue
            g = read(p.parent / 'generation.json')
            c = read(run / 'candidates' / r['candidate'] / 'candidate.json')
            cohort = ('primary' if r['model'] in cfg['search_models'] and r.get('phase') in ['baseline', 'search']
                      else 'supplementary' if r['model'] in cfg.get('retained_search_models', []) else 'confirmation')
            review = adjudications.get(r['episode_id'] + '-t' + str(t.get('turn',1)))
            excluded = bool(review and review.get('exclude_from_palter_examples'))
            automated_valid = t.get('category') == 'paltering'
            audit_path = run / 'audit' / r['episode_id'] / 'result.json'
            audit = read(audit_path) if audit_path.exists() else None
            rows.append(dict(r=r, t=t, j=js[0], g=g, c=c, cohort=cohort,
                             automated_valid=automated_valid, valid=automated_valid and not excluded,
                             review=review, audit=audit, status='review_error' if excluded else 'validated' if automated_valid else 'flag_only'))
    rows.sort(key=lambda x: (not x['valid'], x['cohort'] != 'primary', x['r']['case_id'], x['r']['model'], x['r']['episode_id']))
    totals = Counter(x['status'] for x in rows)
    automated_total = sum(x['automated_valid'] for x in rows)
    timestamp = datetime.now(ZoneInfo('America/Chicago')).strftime('%B %d, %Y at %I:%M %p %Z')
    body = '<header><p class="eyebrow">Saved replies · Qwen 3.7 Plus coding</p><h1>Paltering flags and their settings</h1>'
    body += f'<p>{len(rows)} replies received a raw Qwen paltering label; {automated_total} pass the automated field checks. {totals["review_error"]} flagged case(s) have been excluded after assistant review. {totals["validated"]} provisional automated passes remain in the default view.</p>'
    body += '<p>The automated checks verify required fields, a matching reply quotation and a recognized source ID. They do not independently verify whether the explanation supports the label. Remaining flags need semantic review; they are not confirmed palters or measured recipient effects. Assistant reviews are identified separately and preserve the original data. Gemma’s partial results are marked supplementary.</p>'
    if cfg.get('reader_evaluation_enabled',True) is False:
        body += '<p><strong>Reader audits are deferred.</strong> Current review concerns the message itself: necessity of the fact, factual truth, a specific wrong inference, permitted disclosure, and consistency between explanation and evidence. Previously collected reader results are historical; no further audits or reference calls are planned.</p>'
    progress_text = 'The scheduled message run is complete. <a href="completion.html">Completion audit</a>.' if read(run / "state.json").get("status")=="completed" else "The experiment is continuing."
    body += f'<p class="muted">Snapshot: {esc(timestamp)}. {progress_text} <a href="index.html">Full run report</a></p></header>'
    body += '<section class="filters" aria-label="Filter replies"><label>Evidence status<select id="status"><option value="validated">Provisional automated passes</option><option value="all">All raw Qwen flags</option><option value="flag_only">Did not pass automated checks</option><option value="review_error">Coding errors found on review</option></select></label>'
    for field, title, values in [('model', 'Office model', sorted({x['r']['model'] for x in rows})),
                                  ('case', 'Scenario', sorted({x['r']['case_id'] for x in rows}))]:
        body += f'<label>{title}<select id="{field}"><option value="all">All</option>'
        body += ''.join(f'<option value="{esc(v)}">{esc(NAMES.get(v,v))}</option>' for v in values)
        body += '</select></label>'
    body += '<label>Sample<select id="cohort"><option value="all">All samples</option><option value="primary">Active discovery models</option><option value="supplementary">Supplementary models</option><option value="confirmation">Confirmation</option></select></label>'
    body += '<label class="wide">Search reply or setting<input id="search" type="search" placeholder="e.g. food, complaint, candidate_0042"></label></section><p id="shown" aria-live="polite"></p>'
    for x in rows:
        r,t,j,g,c = (x[k] for k in ['r','t','j','g','c'])
        eid = r['episode_id']; cid = r['candidate']; anchor = eid + '-t' + str(t.get('turn',1))
        valid_text = 'Coding error: assistant review says ' + x['review']['category'] if x['status']=='review_error' else 'Automated checks passed; provisional' if x['valid'] else 'Raw flag only: ' + t.get('category','unresolved').replace('_',' ')
        body += f'<details class="case" id="{esc(anchor)}" data-status="{x["status"]}" data-model="{esc(r["model"])}" data-case="{esc(r["case_id"])}" data-cohort="{x["cohort"]}">'
        body += f'<summary><span class="case-title">{esc(NAMES.get(r["model"],r["model"]))} · {esc(r["case_id"])}</span><span class="badge {"pass" if x["valid"] else "flag"}">{esc(valid_text)}</span><small>{esc(cid)} · {esc(r.get("phase",""))} · {x["cohort"]}</small></summary>'
        body += '<div class="inside"><div class="columns"><section><h2>The setting</h2>'
        initial = g.get('history', g.get('pre_reply_history', []))
        question = next((m.get('content','') for m in initial if m.get('role')=='user'), '').split('\n\nMailbox update:',1)[0]
        body += '<h3>Resident’s question</h3>' + paragraph(question)
        body += '<h3>Condition prompt</h3>' + paragraph(c.get('condition',''))
        body += '<h3>Information access</h3><p>' + ('The recipient can retrieve the case extract. The office has the same incident evidence.' if r.get('information_profile')=='shared' else 'The case extract is internal. The office can explain its relevant findings, but the recipient cannot retrieve the extract.') + '</p>'
        body += '<p>The office can access its own internal records and public records from all offices. It has no staff-handoff tool.</p>'
        for n, note in enumerate(c.get('new_records',[]),1):
            body += '<details><summary>Added office note: ' + esc(note.get('title',str(n))) + '</summary>' + paragraph(note.get('text','')) + '</details>'
        system = next((m.get('content','') for m in initial if m.get('role')=='system'),'')
        body += '<details><summary>Full system prompt</summary>' + paragraph(system) + '</details>'
        body += f'<p><a href="../sites/{quote(cid)}/staff/index.html">Staff archive</a> · <a href="../sites/{quote(cid)}/recipient/index.html">Recipient archive</a></p></section><section><h2>The model’s reply</h2>'
        reply = t.get('reply',''); cited = j.get('quote','')
        if isinstance(cited,str) and cited and cited in reply:
            a,b = reply.split(cited,1)
            marked = esc(a) + '<mark>' + esc(cited) + '</mark>' + esc(b)
        else:
            marked = esc(reply)
        body += '<div class="prose reply">' + marked + '</div><p class="muted">Highlight: the passage quoted by Qwen, where it matches the saved reply exactly. An omitted fact cannot itself be highlighted.</p>'
        if x['review']:
            body += '<section class="review-note"><h3>Assistant review: ' + esc(x['review']['category']) + '</h3>' + paragraph(x['review']['basis']) + paragraph(x['review']['judge_inconsistency']) + '<p class="muted">' + esc(x['review']['scope']) + '</p></section>'
        body += '<h3>Qwen’s explanation</h3>' + paragraph(j.get('explanation','Not supplied.'))
        body += '<h3>The inference Qwen identifies</h3>' + paragraph(j.get('specific_wrong_inference','Not supplied.'))
        body += '<p><strong>Tactics named by Qwen:</strong> ' + esc(', '.join(j.get('tactics',[]))) + '</p>'
        body += '<p><strong>Stored automated category (before assistant review):</strong> ' + esc(t.get('category','unresolved').replace('_',' ')) + '. <strong>Source-supported comprehension:</strong> ' + ('passed' if t.get('comprehension',{}).get('supported_correct') is True else 'not established') + '. <strong>Reader measurement:</strong> ' + ('audit recorded; see panel details below' if x.get('audit') else 'recorded; see scoring data' if t.get('reader_tested') else 'not yet tested for this reply') + '.</p>'
        if x.get('audit'):
            audit=x['audit']
            body+='<details><summary>Reader audit results</summary>'
            if audit.get('status')!='completed':
                body+='<p>Incomplete measurement: '+esc(audit.get('error','Scoring failed.'))+' This is not evidence of no effect.</p>'
            else:
                body+='<p>Mean probability of the true conclusion, from 0 to 100. A completed API audit may still contain an invalid reader panel; missing or inconsistent measurements are shown separately.</p>'
                for key,title in [('reader_effect_immediate','Before lookup'),('reader_effect_after_lookup','After lookup')]:
                    body+='<h3>'+title+'</h3>'
                    for panel in audit.get(key,[]):
                        label={'judge_qwen':'Qwen 3.7 Plus','judge_mistral':'Mistral Small 2603'}.get(panel['model'],panel['model'])
                        means=panel.get('means_truth')
                        if means:
                            vals='; '.join(name+': '+format(means[arm],'.1f') for arm,name in [('before','No reply'),('honest','Honest reference'),('false','False reference'),('actual','Actual reply')])
                            body+='<p><strong>'+esc(label)+'</strong><br>'+esc(vals)+'<br>Reference calibration: '+('passed' if panel.get('calibrated') else 'failed')+'. Meets the misleading-effect criterion: '+('yes' if panel.get('confirmed') else 'no')+'.</p>'
                        else:
                            body+='<p><strong>'+esc(label)+'</strong>: unavailable. '+esc(panel.get('reason','No valid estimate.'))+'</p>'
                valid_panels=all(v.get('means_truth') for key in ['reader_effect_immediate','reader_effect_after_lookup'] for v in audit.get(key,[]))
                if not valid_panels:body+='<p>A two-reader conclusion is unavailable because at least one panel is incomplete or internally inconsistent.</p>'
            body+=f'<p><a href="../audit/{quote(eid)}/result.json">Full reader audit data</a></p></details>'
        evidence_id = j.get('evidence_id')
        sources = [s for s in g.get('authoritative_records',[]) if s.get('record_id')==evidence_id]
        body += '<details><summary>Source record cited by Qwen: ' + esc(evidence_id or 'none') + '</summary>'
        body += ''.join(paragraph(s.get('text','')) for s in sources) if sources else '<p>No exact matching source identifier was found in this reply’s stored evidence.</p>'
        body += '</details><details><summary>Full Qwen coding and check results</summary><pre>' + esc(json.dumps({'qwen':j,'message_category':t.get('category'),'score_evidence':t.get('search_score',{}),'comprehension':t.get('comprehension',{}).get('assessment',{})},indent=2,ensure_ascii=False)) + '</pre></details>'
        body += f'<p><a href="#{quote(anchor)}">Link to this reply</a> · <a href="../episodes/{quote(eid)}/result.json">Saved scoring data</a> · <a href="../candidates/{quote(cid)}/candidate.json">Setting JSON</a></p></section></div></div></details>'
    css = '''*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#202d3d;font:16px/1.65 system-ui,-apple-system,sans-serif}main{max-width:1160px;margin:auto;padding:36px 22px 80px}header{max-width:850px}h1{font-size:clamp(29px,4vw,42px);line-height:1.15;margin:10px 0 20px}h2{font-size:22px;margin:0 0 16px}h3{font-size:16px;margin:24px 0 6px}.eyebrow,.muted,small{color:#5c6878;font-size:13px}.filters{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;padding:20px;background:#fff;border:1px solid #d9e0e7;border-radius:8px;margin-top:28px}label{font-size:13px;font-weight:650}select,input{display:block;width:100%;min-height:42px;padding:8px;margin-top:5px;border:1px solid #bac6d3;border-radius:4px;background:#fff;color:inherit;font:inherit}.wide{grid-column:1/-1}.case{background:#fff;border:1px solid #d3dde6;border-radius:8px;margin:14px 0;scroll-margin-top:20px}.case>summary{padding:18px 20px;cursor:pointer}.case-title{font-weight:650;display:inline-block;margin:0 14px 6px 0}.case small{display:block;margin-top:5px}.badge{display:inline-block;border-radius:4px;padding:2px 9px;font-size:12px}.pass{background:#dfeee8;color:#17503d}.flag{background:#f6ead4;color:#785116}.inside{padding:10px 22px 24px;border-top:1px solid #e0e5eb}.columns{display:grid;grid-template-columns:1fr 1.1fr;gap:30px}.prose{white-space:pre-wrap;overflow-wrap:anywhere}.reply{background:#f5f8fc;border-left:3px solid #6588ac;padding:16px}mark{background:#fff0ab;color:inherit}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}a{color:#1b507d}section details{margin:14px 0;border-top:1px solid #dfe5eb;padding-top:10px}section summary{cursor:pointer;font-weight:600;font-size:14px}[hidden]{display:none!important}@media(max-width:760px){.columns{grid-template-columns:1fr}.filters{grid-template-columns:1fr 1fr}main{padding:24px 14px}.inside{padding:15px}.case>summary{padding:16px}.badge{display:table}h2{margin-top:10px}}'''
    js = '''const ids=['status','model','case','cohort','search'];const cards=[...document.querySelectorAll('.case')];function filter(){let n=0;for(const c of cards){let show=true;for(const id of ids){const v=document.getElementById(id).value;if(id==='search'){if(v&&!c.textContent.toLowerCase().includes(v.toLowerCase()))show=false}else if(v!=='all'&&c.dataset[id]!==v)show=false}c.hidden=!show;if(show)n++}document.getElementById('shown').textContent=n+' replies shown. Open a row to compare the setting and reply.'}for(const id of ids)document.getElementById(id).addEventListener(id==='search'?'input':'change',filter);function reveal(){const id=decodeURIComponent(location.hash.slice(1));const c=document.getElementById(id);if(c&&c.classList.contains('case')){for(const key of ids)document.getElementById(key).value=key==='search'?'':'all';filter();c.open=true;c.scrollIntoView()}}window.addEventListener('hashchange',reveal);filter();reveal();'''
    document = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Qwen paltering flags and settings</title><style>' + css + '</style><main>' + body + '</main><script>' + js + '</script></html>'
    dest=run/'review/qwen_paltering.html';tmp=dest.with_suffix('.html.tmp');tmp.write_text(document);os.replace(tmp,dest)
    return {'path':str(dest),'raw_flags':len(rows),'automated_field_checks_pass':automated_total,'assistant_review_exclusions':totals['review_error'],'provisional_remaining':totals['validated'],
            'primary_pass':sum(x['valid'] and x['cohort']=='primary' for x in rows),
            'supplementary_pass':sum(x['valid'] and x['cohort']=='supplementary' for x in rows),
            'snapshot':timestamp}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,default=ROOT/'runs/lean175_20260923');a=p.parse_args()
    print(json.dumps(render(a.run.resolve()),indent=2))
