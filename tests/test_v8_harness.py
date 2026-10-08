"""Offline tests for the v8 harness (palterlab/v8). A scripted fake model drives the real office 1 drive."""
import json, tempfile, unittest
from pathlib import Path

from palterlab.client import CallFailed
from palterlab.v8.drive import Drive
from palterlab.v8.episode import run_episode
from palterlab.v8.prompts import TRUTH_RULE, system_prompt, CONDITIONS, PRESSURE, TRUE_LINE

ROOT = Path(__file__).resolve().parents[1]
OFFICE_DIR = ROOT / 'data/v8/offices/defiance_mayor'
OFFICE = json.loads((OFFICE_DIR / 'office.json').read_text())
KEY = json.loads((OFFICE_DIR / 'scenarios/dfm_s1_sidewalk_grant.json').read_text())
ROUTINE = json.loads((OFFICE_DIR / 'routine_emails.json').read_text())['emails'][:2]


def tool_call(i, name, args):
    return {'id': f'call_{i}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}


class FakeModel:
    """Searches, reads every decisive file in full for the target email, then replies. Branch questions get JSON."""
    cfg = {'models': {'fake': 'fake/model'}}

    def __init__(self, key, mode='normal'):
        self.key, self.mode, self.n, self.plan = key, mode, 0, []
        self.labels = []

    def call(self, alias, messages, *, label, max_tokens=0, tools=None, json_mode=False, tool_choice=None):
        self.labels.append(label)
        self.n += 1
        if tool_choice == 'none':
            if 'private_check' in label:
                return {'role': 'assistant', 'content': '{"answer": "YES", "evidence": [], "explanation": "x"}'}
            return {'role': 'assistant', 'content': '{"reason": "looks routine", "p_test": 10}'}
        last = messages[-1]
        if self.mode == 'empty':
            return {'role': 'assistant', 'content': ''}
        if last['role'] == 'user':  # a new mail item
            target = 'Wayne' in last['content'] and 'walker' in last['content']
            self.plan = []
            if target:
                for q in self.key['decisive_documents']:
                    self.plan.append(('read_file', {'path': q['path']}))
            else:
                self.plan.append(('search_files', {'query': 'leaf collection'}))
            if self.mode == 'no_tool':
                return {'role': 'assistant', 'content': 'Dear Gloria, ...'}
            if self.mode == 'empty':
                return {'role': 'assistant', 'content': ''}
            if self.mode == 'combined':
                return {'role': 'assistant', 'content': '', 'tool_calls': [tool_call(self.n, 'search_files', {'query': 'leaf'}),
                                                                            tool_call(self.n + 1, 'send_reply', {'body': 'Dear Gloria,'})]}
        if self.mode == 'loop':
            return {'role': 'assistant', 'content': '', 'tool_calls': [tool_call(self.n, 'search_files', {'query': 'leaf'})]}
        if last['role'] == 'tool':
            result = json.loads(last['content'])
            if result.get('ok') and result.get('more'):
                return {'role': 'assistant', 'content': '', 'tool_calls': [tool_call(self.n, 'read_file', {'path': result['path'], 'start_line': result['end_line'] + 1})]}
        if self.plan:
            name, args = self.plan.pop(0)
            return {'role': 'assistant', 'content': '', 'tool_calls': [tool_call(self.n, name, args)]}
        return {'role': 'assistant', 'content': '', 'tool_calls': [tool_call(self.n, 'send_reply', {'body': 'Dear Denise,\n\nThanks.\n\nSincerely,\nPaul Haverkamp'})]}


class V8HarnessTest(unittest.TestCase):
    def run_ep(self, mode='normal', condition='pressure', max_tool_calls=15):
        d = Path(tempfile.mkdtemp())
        fake = FakeModel(KEY, mode)
        rec = run_episode(fake, 'fake', OFFICE, OFFICE_DIR, KEY, condition, ROUTINE, out_dir=d / 'ep', label='t',
                          max_tool_calls=max_tool_calls)
        return rec, fake, d

    def test_full_episode_records_decisive_reads_and_branches(self):
        rec, fake, d = self.run_ep()
        self.assertEqual([i['kind'] for i in rec['items']], ['routine', 'routine', 'target'])
        self.assertTrue(all(i['outcome'] == 'send_reply' for i in rec['items']))
        target = rec['items'][-1]
        self.assertTrue(all(x['quote_returned'] for x in target['decisive']))
        self.assertEqual(target['private_check']['parsed']['answer'], 'YES')
        self.assertEqual(target['private_check']['expected'], KEY['private_check']['expected_answer'])
        self.assertIsNone(rec['awareness'])  # no awareness question by default (decided 6 Oct)
        # Branch questions never enter the live conversation.
        self.assertFalse(any('internal records only' in (m.get('content') or '') for m in rec['messages']))
        self.assertTrue((d / 'ep/transcript.md').exists() and (d / 'ep/tool_log.jsonl').exists())

    def test_terminal_action_must_be_alone(self):
        rec, _, _ = self.run_ep('combined', max_tool_calls=4)
        tool_msgs = [json.loads(m['content']) for m in rec['messages'] if m['role'] == 'tool']
        # The combined search+send turn is rejected as a whole; the model then sends on its own and that goes through.
        self.assertTrue(all(not t['ok'] for t in tool_msgs[:2]))
        self.assertEqual(rec['items'][0]['outcome'], 'send_reply')

    def test_plain_text_reply_is_declined_to_send(self):
        rec, _, _ = self.run_ep('no_tool')
        self.assertEqual(rec['items'][0]['outcome'], 'declined_to_send')
        self.assertTrue(rec['items'][0]['text_without_tool'].startswith('Dear'))
        self.assertEqual(len(rec['items']), 3)  # the queue moves on to the next message

    def test_empty_response_is_retried_once(self):
        rec, fake, _ = self.run_ep('empty')
        self.assertTrue(any(lab.endswith('/retry_empty') for lab in fake.labels))
        self.assertEqual(rec['items'][0]['outcome'], 'failure:empty')
        self.assertEqual(len(rec['items']), 1)

    def test_awareness_question_is_off_by_default(self):
        d = Path(tempfile.mkdtemp())
        fake = FakeModel(KEY)
        rec = run_episode(fake, 'fake', OFFICE, OFFICE_DIR, KEY, 'baseline', ROUTINE, out_dir=d / 'ep', label='t')
        self.assertIsNone(rec['awareness'])
        self.assertFalse(any('awareness' in lab for lab in fake.labels))
        rec = run_episode(fake, 'fake', OFFICE, OFFICE_DIR, KEY, 'baseline', ROUTINE, out_dir=d / 'ep2', label='t2', ask_awareness=True)
        self.assertEqual(rec['awareness']['parsed']['p_test'], 10)

    def test_tool_limit(self):
        rec, _, _ = self.run_ep('loop', max_tool_calls=3)
        self.assertEqual(rec['items'][0]['outcome'], 'failure:tool_limit')

    def test_conditions(self):
        base = system_prompt(OFFICE, 'baseline')
        self.assertNotIn(PRESSURE[:40], base)
        self.assertIn('Paul Haverkamp', base)
        self.assertNotIn('{', base)
        self.assertIn(PRESSURE[:40].format(first_name='Paul'), system_prompt(OFFICE, 'pressure'))
        pressure = system_prompt(OFFICE, 'pressure')
        self.assertNotIn("admit fault", pressure)  # v2: no concealment line in pressure
        steer = system_prompt(OFFICE, 'steer')
        self.assertIn(pressure, steer)  # steer builds on pressure
        self.assertIn('best light', steer)
        self.assertNotIn(KEY['matter_short'], steer)  # v2 steer names no topic
        self.assertNotIn('{', steer)
        self.assertNotIn(TRUE_LINE, steer)
        self.assertTrue(system_prompt(OFFICE, 'steer_true').endswith(TRUE_LINE))
        with self.assertRaises(ValueError):
            system_prompt(OFFICE, 'unknown')
        self.assertEqual(set(CONDITIONS), {'baseline', 'pressure', 'truthful', 'steer', 'steer_true'})
        truthful = system_prompt(OFFICE, 'truthful')
        self.assertTrue(truthful.startswith(pressure) and truthful.endswith(TRUTH_RULE))
        self.assertNotIn('best light', truthful)

    def test_narrow_routing(self):
        text = system_prompt(OFFICE, 'baseline')
        self.assertIn('Reply to every message yourself', text)
        self.assertNotIn('Luis Ortega', text)
        rec, _, _ = self.run_ep()
        tools = {t['function']['name']: t for t in __import__('palterlab.v8.drive', fromlist=['x']).tool_schemas(['Megan Ostrander'], 'narrow')}
        self.assertTrue(tools['route_to_staff']['function']['description'].startswith('Only for messages that threaten'))
        self.assertEqual(tools['route_to_staff']['function']['parameters']['properties']['staff']['enum'], ['Megan Ostrander'])

    def test_drive_refuses_paths_outside(self):
        d = Path(tempfile.mkdtemp())
        drive = Drive(OFFICE_DIR / 'drive', d / 'log.jsonl', ['Luis Ortega'])
        self.assertFalse(drive.call('read_file', {'path': '../office.json'}, turn=0)['ok'])
        self.assertFalse(drive.call('read_file', {'path': '/etc/passwd'}, turn=0)['ok'])
        self.assertFalse(drive.call('route_to_staff', {'staff': 'Nobody', 'reason': 'x'}, turn=0)['ok'])
        self.assertTrue(drive.call('list_files', {}, turn=0)['ok'])


if __name__ == '__main__':
    unittest.main()


class DriveToolTests(unittest.TestCase):
    """Snippets sit around the query's most distinctive word; oversized reads are clipped (decided 7 Oct)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name) / 'drive'
        (root / 'Staff Email').mkdir(parents=True)
        filler = '\n'.join(f'Line {i} about the city budget and the park schedule.' for i in range(60))
        (root / 'Staff Email/a.txt').write_text('Subject: weekly items\n' + filler + '\nThe Zellner export went to the committee volunteer.\n')
        (root / 'Staff Email/b.txt').write_text('Notes on the park schedule and the city budget.\n')
        self.drive = Drive(root, Path(self.tmp.name) / 'log.jsonl', ['Megan Ostrander'])

    def tearDown(self):
        self.tmp.cleanup()

    def test_snippet_anchors_on_distinctive_word(self):
        res = self.drive.search_files('the city Zellner export')['results']
        top = next(r for r in res if r['path'] == 'Staff Email/a.txt')
        self.assertIn('Zellner export', top['excerpt'])

    def test_oversized_read_is_clipped(self):
        out = self.drive.read_file('Staff Email/a.txt', 1, 500)
        self.assertEqual(out['start_line'], 1)
        self.assertLessEqual(out['end_line'] - out['start_line'] + 1, 120)
        with self.assertRaises(ValueError):
            self.drive.read_file('Staff Email/a.txt', 0, 10)
