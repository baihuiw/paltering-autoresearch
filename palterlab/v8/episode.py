"""One v8 episode: the office assistant works through a short queue (routine mail, then one target email),
replying to each with the drive tools. Two questions are asked on copies of the conversation and never
reach the live episode: a private comprehension check, branched just before the target reply is sent, and
an optional awareness question, branched after the episode ends (off by default: eval awareness is measured
from the models' own reasoning instead, decided 6 Oct).

The episode records, for the target email: the outcome (reply, routed, or a technical failure), the reply
text, which decisive passages had been returned to the model before it replied, the private check and the
awareness answer. Scoring is separate.
"""
import json, re
from pathlib import Path

from ..client import CallFailed, BudgetStop
from ..common import parse, save
from .drive import Drive, tool_schemas, TERMINAL
from .prompts import system_prompt, user_turn, handled_block, PRIVATE_CHECK, AWARENESS


def _clean_assistant(msg):
    """Keep what the provider needs to continue the conversation (content, tool calls, reasoning details)."""
    keep = {k: v for k, v in msg.items() if k in ('role', 'content', 'tool_calls', 'reasoning_details') and v is not None}
    keep['role'] = 'assistant'
    keep.setdefault('content', '')
    return keep


def _flatten(text):
    """Turn numbered read_file output back into plain text so quotations can be matched across lines."""
    lines = [re.sub(r'^\d+: ', '', ln) for ln in text.splitlines()]
    return re.sub(r'\s+', ' ', ' '.join(lines))


def decisive_seen(key, seen):
    """Which decisive quotations were fully in front of the model, and which decisive files it opened."""
    flat = [(p, _flatten(t)) for p, t in seen]
    out = []
    for q in key['decisive_documents']:
        quote = re.sub(r'\s+', ' ', q['quote'])
        out.append({'path': q['path'], 'quote': q['quote'][:120],
                    'quote_returned': any(p == q['path'] and quote in t for p, t in flat),
                    'file_touched': any(p == q['path'] for p, _ in seen)})
    return out


def with_cache_marks(messages, model_id):
    """Anthropic models only cache what the request marks. Mark the system prompt and the newest message
    (a moving breakpoint), so each step re-reads the earlier history from cache at a tenth of the price.
    Other providers cache automatically; their messages are sent unchanged."""
    if not model_id.startswith('anthropic/'):
        return messages
    out = [dict(m) for m in messages]
    for i in (0, len(out) - 1):
        c = out[i].get('content')
        if isinstance(c, str) and c:
            out[i]['content'] = [{'type': 'text', 'text': c, 'cache_control': {'type': 'ephemeral'}}]
    return out


def run_episode(client, alias, office, office_dir, key, condition, routine, *, out_dir, label, max_tool_calls=30,
                max_tokens=5000, routing='narrow', ask_awareness=False, handled=(), house_rules=False):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    roles = ('press_staff',) if routing == 'narrow' else ('casework_staff', 'scheduler', 'press_staff')
    staff = [office['prompt_slots'][k] for k in roles]
    drive = Drive(Path(office_dir) / 'drive', out_dir / 'tool_log.jsonl', staff)
    tools = tool_schemas(staff, routing, office['prompt_slots'].get('office_short', 'the city'))
    if routing == 'none':
        tools = [t for t in tools if t['function']['name'] != 'route_to_staff']
    system = system_prompt(office, condition, key.get('matter_short'), routing, house_rules=house_rules)
    messages = [{'role': 'system', 'content': system}]
    queue = [('routine', e) for e in routine] + [('target', key['email'])]
    record = {'label': label, 'model': alias, 'scenario': key['scenario_id'], 'office': office['office_id'],
              'condition': condition, 'routing': routing, 'handled': [e['id'] for e in handled], 'house_rules': house_rules, 'system_prompt': system, 'items': []}
    step = 0
    for kind, email in queue:
        drive.next_message()
        first = handled and len(messages) == 1
        messages.append({'role': 'user', 'content': (handled_block(handled) if first else '') + user_turn(email)})
        item = {'kind': kind, 'from': email['name'], 'outcome': None, 'tool_calls': 0}
        before_terminal = None
        while drive.closed is None:
            if item['tool_calls'] >= max_tool_calls:
                item['outcome'] = 'failure:tool_limit'
                break
            try:
                msg = client.call(alias, with_cache_marks(messages, client.cfg['models'].get(alias, '')), label=f'{label}/step{step}', max_tokens=max_tokens, tools=tools)
                if not (msg.get('tool_calls') or (msg.get('content') or '').strip()):
                    # A completely empty response (no text, no tool call) is a transport-level failure, not an outcome:
                    # one retry under a new label. Responses with any content are never retried.
                    item['empty_retry'] = True
                    msg = client.call(alias, with_cache_marks(messages, client.cfg['models'].get(alias, '')), label=f'{label}/step{step}/retry_empty', max_tokens=max_tokens, tools=tools)
            except BudgetStop:
                raise
            except CallFailed as e:
                item['outcome'] = 'failure:call'
                item['error'] = str(e)
                break
            step += 1
            calls = msg.get('tool_calls') or []
            messages.append(_clean_assistant(msg))
            if not calls:
                text = (msg.get('content') or '').strip()
                if not text:
                    item['outcome'] = 'failure:empty'
                    break
                # Text written without sending is not a reply the resident receives. It is its own outcome (the model
                # declined to send, often writing to staff instead), kept in full for review; the queue moves on.
                item['outcome'] = 'declined_to_send'
                item['text_without_tool'] = text
                break
            names = [c['function']['name'] for c in calls]
            terminal_with_others = len(calls) > 1 and any(n in TERMINAL for n in names)
            for c in calls:
                item['tool_calls'] += 1
                try:
                    args = json.loads(c['function'].get('arguments') or '{}')
                except json.JSONDecodeError:
                    args = None
                if terminal_with_others:
                    # Sending must be its own step, after the model has seen what it looked up.
                    result = {'ok': False, 'error': 'send_reply and route_to_staff must be called on their own'}
                else:
                    if c['function']['name'] in TERMINAL and kind == 'target' and before_terminal is None:
                        before_terminal = list(messages[:-1])  # history up to, not including, the sending turn
                    result = drive.call(c['function']['name'], args, turn=step)
                messages.append({'role': 'tool', 'tool_call_id': c['id'], 'content': json.dumps(result, ensure_ascii=False)})
        if drive.closed is not None:
            item['outcome'] = drive.closed['action']
            item.update({k: v for k, v in drive.closed.items() if k != 'action'})
        if kind == 'target':
            seq = drive.closed['sequence'] if drive.closed else drive.seq + 1
            seen = drive.seen_before(seq)
            item['decisive'] = decisive_seen(key, seen)
            item['files_read'] = sorted({p for p, _ in seen})
            if before_terminal is not None:
                item['private_check'] = private_check(client, alias, before_terminal, key, f'{label}/private_check',
                                                      max_tokens, tools)
        record['items'].append(item)
        if item['outcome'] and item['outcome'].startswith('failure'):
            break
    # Off by default (decided 6 Oct): awareness is coded from the model's own reasoning, with no extra call.
    record['awareness'] = _branch(client, alias, messages, AWARENESS, f'{label}/awareness', max_tokens, tools) if ask_awareness else None
    record['messages'] = messages
    save(out_dir / 'episode.json', record)
    (out_dir / 'transcript.md').write_text(transcript(record))
    return record


CHECK_RETRY = ' Answer now with the JSON only. Do not use any tools.'


def private_check(client, alias, history, key, label, max_tokens, tools):
    """The branched private check, asked once more if the answer is missing (empty, a tool call, or unreadable):
    about one check in ten on 8 Oct."""
    q = PRIVATE_CHECK.format(question=key['private_check']['question'])
    pc = _branch(client, alias, history, q, label, max_tokens, tools)
    if not check_answer(pc):
        retry = _branch(client, alias, history, q + CHECK_RETRY, f'{label}/retry', max_tokens, tools)
        retry['first_attempt'] = pc
        pc = retry
    pc['expected'] = key['private_check']['expected_answer']
    return pc


def _branch(client, alias, history, question, label, max_tokens, tools):
    # The tool definitions are sent (some providers require them once the history has tool calls) but switched off.
    msgs = list(history) + [{'role': 'user', 'content': question}]
    try:
        msg = client.call(alias, with_cache_marks(msgs, client.cfg['models'].get(alias, '')), label=label, max_tokens=max_tokens,
                          tools=tools, tool_choice='none')
    except CallFailed as e:
        return {'error': str(e)}
    text = msg.get('content') or ''
    try:
        parsed = parse(text)
    except (ValueError, TypeError):
        parsed = check_answer({'text': text})
    return {'text': text, 'parsed': parsed}


def check_answer(pc):
    """The private check's JSON, also when the model wrote more text after it (seen 8 Oct: 9 of 80 checks)."""
    if isinstance((pc or {}).get('parsed'), dict) and 'answer' in pc['parsed']:
        return pc['parsed']
    text = (pc or {}).get('text') or ''
    for m in re.finditer(r'\{', text):
        try:
            obj, _ = json.JSONDecoder().raw_decode(text[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict) and 'answer' in obj:
            return obj
    # Malformed JSON (e.g. a stray bracket): keep only the answer field.
    m = re.search(r'"answer"\s*:\s*"(YES|NO|UNCERTAIN)"', text, re.I)
    return {'answer': m.group(1).upper(), 'recovered_from_malformed_json': True} if m else None


def transcript(record):
    """Readable transcript for hand review: every message, tool call and tool result in order."""
    out = [f"# {record['scenario']} | {record['condition']} | {record['model']}", '', '## System prompt', '', record['system_prompt'], '']
    for m in record['messages'][1:]:
        if m['role'] == 'user':
            out += ['## Incoming message', '', m['content'], '']
        elif m['role'] == 'assistant':
            if m.get('content'):
                out += ['**Assistant:**', '', m['content'], '']
            for c in m.get('tool_calls') or []:
                out += [f"**Tool call:** `{c['function']['name']}` {c['function'].get('arguments', '')}", '']
        elif m['role'] == 'tool':
            body = m['content']
            out += ['<details><summary>Tool result</summary>', '', '```', body[:6000], '```', '</details>', '']
    for it in record['items']:
        if it['kind'] == 'target':
            out += ['## Target email: summary', '', f"Outcome: {it['outcome']}", '']
            for d in it.get('decisive', []):
                out.append(f"- decisive `{d['path']}`: quote returned {d['quote_returned']}, file touched {d['file_touched']}")
            if 'private_check' in it:
                out += ['', f"Private check (expected {it['private_check'].get('expected')}): {it['private_check'].get('text', it['private_check'])}"]
    if record.get('awareness'):
        out += ['', f"Awareness: {record['awareness'].get('text', record['awareness'])}"]
    return '\n'.join(out)
