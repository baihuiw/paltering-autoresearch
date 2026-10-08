"""Run v8 episodes for hand-testing (work plan step 7). Paid unless --dry-run.

Each episode: routine email(s) (one by default), then the scenario's target email, one reply each, with the drive tools.
Saves runs/<run>/<scenario>/<condition>/<model>/s<k>/{episode.json, transcript.md, tool_log.jsonl} and a
summary table. Outcome coding (honest / palter / lie / ...) is a separate step; read the transcripts.

Usage (from the repository root):
  python3 scripts/v8_run.py --office defiance_mayor --dry-run --scenario dfm_s1_sidewalk_grant --condition pressure
  python3 scripts/v8_run.py --office defiance_mayor --run runs/v8_hand_20261005 --models deepseekv41flash \
      --conditions pressure --n 3 --budget 2
Needs OPENROUTER_API_KEY for a paid run. Completed calls are cached in the run directory; rerunning resumes.
"""
import argparse, hashlib, json, sys, urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from palterlab.client import Client, BudgetStop  # noqa: E402
from palterlab.common import save  # noqa: E402
from palterlab.v8.env import load_key  # noqa: E402
load_key()
from palterlab.v8.episode import run_episode, check_answer  # noqa: E402
from palterlab.v8.variants import expand  # noqa: E402
from palterlab.v8.prompts import system_prompt, user_turn, handled_block, CONDITIONS  # noqa: E402
sys.path.insert(0, str(ROOT / 'scripts'))
from v8_probe_knowledge import MODELS  # noqa: E402


def handled_for(office_dir, key, k, routine, count):
    """v9: earlier mail already answered, shown before the first live message. Different from the live routine email,
    received before it (or before the target if there is none), oldest first."""
    if not count:
        return []
    emails = json.loads((office_dir / 'routine_emails.json').read_text())['emails']
    live = {e['id'] for e in routine}
    first = min([e['received'] for e in routine] + [key['email']['received']])
    pool = [e for e in emails if e['id'] not in live and e['received'] < first]
    order = sorted(pool, key=lambda e: hashlib.sha256(f"{key['scenario_id']}/{k}/handled/{e['id']}".encode()).hexdigest())
    return sorted(order[:count], key=lambda e: e['received'])


def routine_for(office_dir, scenario_id, k, count=1):
    """Routine emails before the target, chosen deterministically per scenario and sample, in arrival order.
    One by default: the history read for routine mail is re-sent on every target step (cost analysis, Oct 3)."""
    emails = json.loads((office_dir / 'routine_emails.json').read_text())['emails']
    order = sorted(emails, key=lambda e: hashlib.sha256(f'{scenario_id}/{k}/{e["id"]}'.encode()).hexdigest())
    return sorted(order[:count], key=lambda e: e['received'])


def reasoning_setting(catalog, model_id, effort):
    """Reasoning as the model ships ('default'), or a fixed effort. Recorded in the run config."""
    meta = next(m for m in catalog['data'] if m['id'] == model_id)
    info = meta.get('reasoning') or {}
    if effort != 'default':
        return {'effort': effort}
    if info.get('default_effort'):
        return {'effort': info['default_effort']}
    return {'enabled': True} if info else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--office', required=True)
    ap.add_argument('--scenario', nargs='*', help='scenario ids (default: all in the office)')
    ap.add_argument('--conditions', '--condition', nargs='+', default=['pressure'], choices=CONDITIONS)
    ap.add_argument('--models', nargs='+', default=['deepseekv41flash'])
    ap.add_argument('--n', type=int, default=1, help='samples per scenario x condition x model')
    ap.add_argument('--run', help='run directory (new or resuming)')
    ap.add_argument('--budget', type=float, default=2.0)
    ap.add_argument('--max-tool-calls', type=int, default=30)  # 15 was too few for a 200-file drive (smoke test, Oct 3)
    ap.add_argument('--effort', default='default', help="reasoning effort for target models; 'default' uses each model's own default")
    ap.add_argument('--temperature', type=float, default=1.0)
    ap.add_argument('--routine', type=int, default=1, help='routine emails before the target')
    ap.add_argument('--awareness', choices=['subset', 'all', 'none'], default='none',
                    help="ask the branched awareness question (an extra call). Not used since 6 Oct: eval awareness is coded "
                         "from the models' own reasoning (design section 10). 'subset' = first sample of each cell")
    ap.add_argument('--routing', nargs='+', default=['narrow'], choices=['narrow', 'standard', 'clarified', 'none'])
    ap.add_argument('--handled', type=int, default=0, help='v9: earlier answered emails shown before the first live message')
    ap.add_argument('--house-rules', action='store_true', help='v9: add the house-rules paragraph to the system prompt')
    ap.add_argument('--variants', action='store_true', help="also run email variants ('<scenario>@<form>')")
    ap.add_argument('--retry-failed', action='store_true', help='rerun episodes that ended in a call failure (failed copies kept)')
    ap.add_argument('--workers', type=int, default=12, help='episodes at once; set the budget cap comfortably above expected spend')
    ap.add_argument('--dry-run', action='store_true', help='print the prompts for one episode; no calls')
    a = ap.parse_args()

    office_dir = ROOT / 'data/v8/offices' / a.office
    office = json.loads((office_dir / 'office.json').read_text())
    keys = {p.stem: json.loads(p.read_text()) for p in sorted((office_dir / 'scenarios').glob('*.json'))}
    if a.variants:  # v9: also run each scenario's email variants, as '<scenario>@<question_form>'
        keys = expand(keys)
    ids = a.scenario or sorted(keys)

    if a.dry_run:
        key = keys[ids[0]]
        print('=== SYSTEM ===\n' + system_prompt(office, a.conditions[0], key['matter_short'], a.routing[0], house_rules=a.house_rules))
        rt = routine_for(office_dir, key['scenario_id'], 0, a.routine)
        hd = handled_for(office_dir, key, 0, rt, a.handled)
        for i, e in enumerate(rt + [key['email']]):
            print('\n=== USER ===\n' + (handled_block(hd) if hd and i == 0 else '') + user_turn(e))
        return
    if not a.run:
        raise SystemExit('--run is required for a paid run')

    run = ROOT / a.run
    with urllib.request.urlopen(urllib.request.Request('https://openrouter.ai/api/v1/models', headers={'User-Agent': 'v8-run'}), timeout=60) as r:
        catalog = json.load(r)
    wanted = {MODELS[m] for m in a.models}
    catalog['data'] = [m for m in catalog['data'] if m['id'] in wanted]
    if {m['id'] for m in catalog['data']} != wanted:
        raise SystemExit('A model is missing from the live catalog')
    cfg = {'models': {m: MODELS[m] for m in a.models}, 'budget_usd': a.budget, 'effective_budget_usd': a.budget,
           'concurrency': a.workers, 'temperature': a.temperature, 'technical_retries': 2, 'retry_backoff_seconds': 10,
           'reasoning': {m: reasoning_setting(catalog, MODELS[m], a.effort) for m in a.models},
           # 'auto' for everyone: Anthropic models with reasoning reject forced tool use, and 'auto' is how deployments run.
           'tool_choice_by_model': {m: 'auto' for m in a.models}}
    if not (run / 'config.json').exists():
        save(run / 'config.json', cfg)
        save(run / 'catalog.json', catalog)
    client = Client(run, cfg, catalog, live=True)

    jobs = [(sid, c, m, k, rt) for sid in ids for c in a.conditions for m in a.models for k in range(a.n) for rt in a.routing]
    # Slowest models first, so the run doesn't end waiting on a few long episodes (pilot timing, Oct 3).
    slow = {'grok46': 0, 'grok47': 0, 'deepseekv4pro': 0, 'gpt61solpro': 0, 'opus55': 1, 'gptchat': 1, 'gpt61sol': 1, 'kimik3': 1}
    jobs.sort(key=lambda j: slow.get(j[2], 2))
    print(f'{len(jobs)} episodes; budget ${a.budget:.2f}; spent so far ${client.spent():.4f}', flush=True)

    def v9_extras(key, k):
        rt = routine_for(office_dir, key['scenario_id'], k, a.routine)
        return {'handled': handled_for(office_dir, key, k, rt, a.handled), 'house_rules': a.house_rules}

    def one(job):
        sid, cond, m, k, rt = job
        out = run / sid / cond / m / (f's{k}' if rt == 'narrow' else f'{rt}_s{k}')
        label = f'{sid}/{cond}/{m}/{rt}/s{k}'
        if (out / 'episode.json').exists():
            rec = json.loads((out / 'episode.json').read_text())
            if not (a.retry_failed and any(str(i.get('outcome')).startswith('failure:call') for i in rec['items'])):
                return rec
            # A dropped call is not the model's doing: set the failed episode aside and run it again under a new label.
            n = len(list(out.parent.glob(out.name + '_failed*'))) + 1
            out.rename(out.with_name(f'{out.name}_failed{n}'))
            return run_episode(client, m, office, office_dir, keys[sid], cond, routine_for(office_dir, sid, k, a.routine),
                               out_dir=out, label=f'{label}/rerun{n}', max_tool_calls=a.max_tool_calls, routing=rt,
                               ask_awareness=a.awareness == 'all' or (a.awareness == 'subset' and k == 0),
                               **v9_extras(keys[sid], k))
        attempts = sorted(out.parent.glob(out.name + '_attempt*'))
        done = next((p for p in attempts if (p / 'episode.json').exists()), None)
        if done:
            return json.loads((done / 'episode.json').read_text())
        if out.exists():
            # An episode we interrupted (stopped run): keep its logs and start a new attempt under a new label, so its
            # unfinished calls aren't reused. The interruption came from us, not from anything the model wrote.
            n = len(attempts) + 2
            out, label = out.with_name(f'{out.name}_attempt{n}'), f'{label}/attempt{n}'
        return run_episode(client, m, office, office_dir, keys[sid], cond, routine_for(office_dir, sid, k, a.routine), out_dir=out,
                           label=label, max_tool_calls=a.max_tool_calls, routing=rt,
                           ask_awareness=a.awareness == 'all' or (a.awareness == 'subset' and k == 0),
                               **v9_extras(keys[sid], k))

    records = []
    with ThreadPoolExecutor(a.workers) as ex:
        for rec in ex.map(lambda j: _safe(one, j), jobs):
            if rec:
                records.append(rec)

    rows = []
    for r in records:
        t = next((i for i in r['items'] if i['kind'] == 'target'), None)
        aw = (r.get('awareness') or {}).get('parsed') or {}
        pc = (t or {}).get('private_check') or {}
        rows.append({'scenario': r['scenario'], 'condition': r['condition'], 'model': r['model'], 'routing': r.get('routing', 'narrow'),
                     'target_outcome': t['outcome'] if t else 'not_reached',
                     'decisive_returned': sum(d['quote_returned'] for d in (t or {}).get('decisive', [])),
                     'decisive_total': len((t or {}).get('decisive', [])),
                     'private_check': (check_answer(pc) or {}).get('answer'), 'expected': pc.get('expected'),
                     'p_test': aw.get('p_test')})
    save(run / 'summary.json', rows)
    print(f'\nspent ${client.spent():.4f}')
    print(f"{'scenario':26s} {'condition':10s} {'model':16s} {'outcome':20s} decisive  check  p_test")
    for x in rows:
        print(f"{x['scenario']:26s} {x['condition']:10s} {x['model']:16s} {x['target_outcome']:20s} "
              f"{x['decisive_returned']}/{x['decisive_total']:<6} {str(x['private_check']):6s} {x['p_test']}")
    print('\nTarget outcomes by routing variant and model:')
    for rt in a.routing:
        for m in a.models:
            print(f'  {rt:10s} {m:16s} {dict(Counter(x["target_outcome"] for x in rows if x["routing"] == rt and x["model"] == m))}')


def _safe(fn, job):
    try:
        return fn(job)
    except BudgetStop as e:
        print('budget stop:', e, flush=True)
        return None


if __name__ == '__main__':
    main()
