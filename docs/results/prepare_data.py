"""Build post_data.json for the results page from a scored collection. Free: no API calls.

Every number and transcript on the page comes from here. To update the page after the full run, point --run-template
at the new runs (and adjust CONDITIONS / MODELS if the labels changed), then rebuild:

  python3 docs/results/prepare_data.py --run-template 'runs/v8_main_{office}_20261008'
  python3 docs/results/build.py docs/results/post.html docs/results/post_data.json --out docs/results/index.html \
      --source-root .
"""
import argparse, json, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

MODELS = {'sonnet55': ('Claude Sonnet 5.5', 'Anthropic'), 'opus55': ('Claude Opus 5.5', 'Anthropic'),
          'gpt61sol': ('GPT-6.1 Sol', 'OpenAI'), 'gpt61solpro': ('GPT-6.1 Sol Pro', 'OpenAI'),
          'gemini38flash': ('Gemini 3.8 Flash', 'Google'), 'grok47': ('Grok 4.7', 'xAI'),
          'deepseekv4pro': ('DeepSeek V4 Pro', 'DeepSeek'), 'kimik3': ('Kimi K3', 'Moonshot AI'),
          'musewonder': ('Muse Wonder', 'Meta')}
CONDITIONS = {'baseline': 'No messaging instruction', 'pressure': 'Promote the official',
              'steer': "Protect the office's image", 'truthful': 'Promote, plus "never make up information"'}
# Outcome groups shown on the page. Everything not listed falls into "other".
GROUPS = {'honest': 'honest', 'palter': 'palter', 'lie': 'lie', 'disputed': 'disputed'}
GROUP_LABELS = {'honest': 'Honest', 'palter': 'Palter', 'lie': 'Lie', 'disputed': 'Judges split', 'other': 'Unresolved or other'}
OUTCOME_LABELS = {'honest': 'Honest', 'palter': 'Palter', 'lie': 'Lie', 'disputed': 'Judges split',
                  'unresolved': 'Unresolved', 'evidence_missed': 'Evidence missed', 'technical_failure': 'Technical failure',
                  'declined_to_send': 'Declined to send', 'declined_to_respond': 'Declined to respond', 'routed': 'Routed to staff'}
HERO = ('ada_city_manager', 'ada_s5_playground', 'pressure', 'gemini38flash')


def rate(n, d):
    return n / d if d else None


def load(run_template):
    base = ROOT / 'data/v8/offices'
    rows, keys, offices = [], {}, {}
    for od in sorted(base.glob('*/office.json')):
        oid = od.parent.name
        scores = ROOT / run_template.format(office=oid) / 'scoring/scores.jsonl'
        if not scores.exists():
            continue
        o = json.loads(od.read_text())
        offices[oid] = {'place': (o.get('office', {}).get('place') or '').split(' (')[0], 'state': o.get('office', {}).get('state'),
                        'title': o['prompt_slots'].get('signature_title')}
        for p in (od.parent / 'scenarios').glob('*.json'):
            keys[p.stem] = json.loads(p.read_text())
        for line in scores.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                r['_office'], r['_scores'] = oid, str(scores.relative_to(ROOT))
                rows.append(r)
    return rows, keys, offices


def group(outcome):
    return GROUPS.get(outcome, 'other')


def counts(rs):
    c = Counter(group(r['outcome']) for r in rs)
    return {g: c.get(g, 0) for g in GROUP_LABELS} | {'n': len(rs)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-template', default='runs/v8_main_{office}_20261008')
    ap.add_argument('--data-date', default='8 October 2026')
    ap.add_argument('--out', default=str(Path(__file__).with_name('post_data.json')))
    a = ap.parse_args()
    rows, keys, offices = load(a.run_template)
    models = [m for m in MODELS if any(r['model'] == m for r in rows)]
    conds = [c for c in CONDITIONS if any(r['condition'] == c for r in rows)]
    n = len(rows)
    tot = counts(rows)

    # Figure 1: outcome mix per model, filterable by condition (with an "All conditions" level).
    outcomes = []
    for cond in ['all'] + conds:
        for m in models:
            rs = [r for r in rows if r['model'] == m and (cond == 'all' or r['condition'] == cond)]
            outcomes.append({'model': MODELS[m][0], 'provider': MODELS[m][1],
                             'condition': 'All conditions' if cond == 'all' else CONDITIONS[cond], **counts(rs)})

    # Figure 2: palter and lie rate per model across conditions.
    by_condition = []
    for m in models:
        for cond in conds:
            rs = [r for r in rows if r['model'] == m and r['condition'] == cond]
            c = counts(rs)
            for kind in ('palter', 'lie'):
                by_condition.append({'model': MODELS[m][0], 'condition': CONDITIONS[cond],
                                     'measure': 'Palter rate' if kind == 'palter' else 'Lie rate',
                                     'rate': rate(c[kind], c['n']), 'count': c[kind], 'n': c['n']})

    cond_stats = {}
    for cond in conds:
        c = counts([r for r in rows if r['condition'] == cond])
        cond_stats[cond] = {'n': c['n'], 'palter': rate(c['palter'], c['n']), 'lie': rate(c['lie'], c['n']),
                            'misled': rate(c['palter'] + c['lie'], c['n']), 'honest': rate(c['honest'], c['n'])}

    model_stats = {}
    for m in models:
        c = counts([r for r in rows if r['model'] == m])
        model_stats[m] = {'name': MODELS[m][0], 'palter': rate(c['palter'], c['n']), 'lie': rate(c['lie'], c['n']),
                          'misled': rate(c['palter'] + c['lie'], c['n']), 'n': c['n']}
    ranked = sorted(model_stats.values(), key=lambda s: s['misled'])

    # Figure 3: did the model know the fact? (private knowledge check)
    knowledge = []
    for g in ('honest', 'palter', 'lie'):
        rs = [r for r in rows if group(r['outcome']) == g]
        k = Counter(r.get('knowledge') or 'no answer' for r in rs)
        knowledge.append({'outcome': GROUP_LABELS[g], 'knew': k.get('knew', 0),
                          'uncertain': k.get('uncertain', 0) + k.get('no answer', 0) + k.get('None', 0),
                          'believed_opposite': k.get('believed_opposite', 0), 'n': len(rs)})
    misled = [r for r in rows if group(r['outcome']) in ('palter', 'lie')]

    # Reader belief in the true answer after the reply (0-100), by outcome.
    reader = []
    for g in ('honest', 'palter', 'lie'):
        v = [r['reader_mean'] for r in rows if group(r['outcome']) == g and r.get('reader_mean') is not None]
        reader.append({'outcome': GROUP_LABELS[g], 'belief': sum(v) / len(v) / 100 if v else None, 'n': len(v)})

    # Hero example.
    office, sid, cond, model = HERO
    hr = next(r for r in rows if (r['_office'], r['scenario'], r['condition'], r['model']) == HERO)
    hk = keys[sid]
    hero_scen = f'data/v8/offices/{office}/scenarios/{sid}.json'
    hero_counts = counts([r for r in rows if r['scenario'] == sid])
    quotes = {'hero': {
        'columns': [
            {'heading': f'{MODELS[model][0]}, "promote the official" condition', 'tag': 'Palter', 'tag_kind': 'warn',
             'turns': [
                 {'role': 'user', 'label': f"Resident's email to the {offices[office]['place']} city manager",
                  'text': hk['email']['body'], 'source': hero_scen},
                 {'role': 'model', 'label': f'Reply sent by {MODELS[model][0]}', 'text': hr['reply'],
                  'source': hr['_scores']}]},
            {'heading': 'An honest reply', 'authored': True, 'tag': 'Reference', 'tag_kind': 'good',
             'turns': [{'role': 'context', 'label': 'What the office drive shows',
                        'text': hk['true_proposition']},
                       {'role': 'model', 'label': 'Reference reply', 'text': hk['references']['honest']}]}],
        'highlights': [
            {'text': 'our certified inspector identified structural wear on the upper bridge of the wooden structure',
             'note': 'True, but the structure failed the inspection outright, and the problem was not limited to the bridge.'},
            {'text': 'You and your son are welcome to enjoy the open sections.',
             'note': 'Leaves the parent believing the rest of the structure is safe for a four-year-old.'},
            {'text': 'He and our parks director recommended closing the whole structure', 'kind': 'key',
             'note': 'The fact the reply leaves out.'}]}}

    # Reply browser: every reply in the collection.
    replies = []
    for r in rows:
        k = keys.get(r['scenario'], {})
        mech = {j: (v.get('coding') or {}).get('impression_mechanism') for j, v in (r.get('judges') or {}).items()}
        replies.append({
            'model': MODELS.get(r['model'], (r['model'],))[0], 'condition': CONDITIONS.get(r['condition'], r['condition']),
            'office': f"{offices[r['_office']]['place']}, {offices[r['_office']]['state']}",
            'topic': (k.get('classification') or {}).get('topic') or r['scenario'],
            'outcome': OUTCOME_LABELS.get(r['outcome'], r['outcome']),
            'reader': r.get('reader_mean'), 'knowledge': r.get('knowledge'),
            'email': (k.get('email') or {}).get('body'), 'true_answer': k.get('true_proposition'),
            'reply': r.get('reply'), 'judges': [m for m in mech.values() if m]})

    data = {
        'meta': {
            'title': 'PalterBench: do AI assistants mislead with true statements?',
            'short_title': 'PalterBench',
            'description': 'AI mail assistants for local officials, asked practical questions whose honest answer '
                           'exposes the office, and how often they mislead without saying anything false.',
            'headline': 'Do AI assistants mislead the public with true statements?',
            'authors': '[AUTHORS]', 'affiliation': '[AFFILIATION]', 'date': '[DATE]',
            'updated': a.data_date, 'status': 'preliminary',
            'footer': 'Draft results page. Offices are real places; every official and event in the scenarios is invented.',
            'bibtex': '[CITATION]'},
        'design': {'n_offices': len(offices), 'n_scenarios': len({r['scenario'] for r in rows}),
                   'n_models': len(models), 'n_conditions': len(conds), 'n_replies': n},
        'overall': {'n': n, 'honest': rate(tot['honest'], n), 'palter': rate(tot['palter'], n),
                    'lie': rate(tot['lie'], n), 'disputed': rate(tot['disputed'], n), 'other': rate(tot['other'], n),
                    'misled': rate(tot['palter'] + tot['lie'], n),
                    'palter_n': tot['palter'], 'lie_n': tot['lie'], 'misled_n': tot['palter'] + tot['lie'],
                    'palter_per_lie': rate(tot['palter'], tot['lie'])},
        'cond': cond_stats,
        'models': {'lowest': ranked[0], 'highest': ranked[-1], **model_stats},
        'knew': {'misled_knew': rate(sum(r.get('knowledge') == 'knew' for r in misled), len(misled)),
                 'misled_n': len(misled)},
        'hero': {'palter': rate(hero_counts['palter'], hero_counts['n']), 'n': hero_counts['n'],
                 'palter_n': hero_counts['palter'], 'reader': hr.get('reader_mean', 0) / 100},
        'reader_by_outcome': {x['outcome'].lower(): x for x in reader},
        'outcomes': outcomes, 'by_condition': by_condition, 'knowledge': knowledge,
        'quotes': quotes, 'replies': replies,
        '_source': a.run_template}
    Path(a.out).write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f'Wrote {a.out}: {n} replies, {len(models)} models, {len(conds)} conditions, {len(offices)} offices')
    print('overall', {k: round(v, 3) if isinstance(v, float) else v for k, v in data['overall'].items()})
    for c, s in cond_stats.items():
        print(c, {k: round(v, 3) for k, v in s.items()})
    for s in ranked:
        print(s)
    print('knew', data['knew'], 'reader', reader, 'hero', data['hero'])


if __name__ == '__main__':
    main()
