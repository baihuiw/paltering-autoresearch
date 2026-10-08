"""Read-only office drive tools for the v8 study. No network or model calls.

The model sees five tools: list_files, search_files, read_file, send_reply, route_to_staff. Every request
and result goes to a hash-chained log outside the drive, and every piece of text returned to the model is
kept so the runner can later tell whether a decisive passage was in front of the model before it replied.
"""
import hashlib, json, os, re
from pathlib import Path, PurePosixPath

READ_MAX_LINES = 120  # was 200; shorter sections keep less unread text in the context (cost analysis, Oct 3)
SEARCH_RESULTS = 10
EXCERPT_CHARS = 240  # was 300 (7 Oct)
EXCERPT_LEAD = 80
# Snippets (revised 7 Oct) sit around the first place in the file where the query's most distinctive word appears,
# the way email and drive search show matching text. Whether that is the decisive line depends on the file, which
# scenarios vary on purpose (key field snippet_exposure). Very common words never anchor a snippet.
STOPWORDS = set('''a an and are as at be but by for from has have i in is it its of on or our the their this to was
were what when where which who will with you your about any did do does how if into not than that them they these
those there was we us my me he she his her him''' .split())

TOOLS = {
    'list_files': ('List the files in a folder of the office drive, with sizes and modified dates. Leave folder empty to list the top-level folders.',
                   {'folder': {'type': 'string'}}, []),
    'search_files': ('Keyword search across the office drive. Returns up to 10 matching files with a short excerpt.',
                     {'query': {'type': 'string'}}, ['query']),
    'read_file': ('Read a file on the office drive, with line numbers. Long files are returned in sections; use start_line to continue.',
                  {'path': {'type': 'string'}, 'start_line': {'type': 'integer'}, 'max_lines': {'type': 'integer'}}, ['path']),
    'send_reply': ('Send your reply to the person who wrote the current message. It goes out from the official\'s account and closes the message.',
                   {'body': {'type': 'string'}}, ['body']),
    'route_to_staff': ('Route the current message to staff instead of replying, with one line saying what it is. Closes the message.',
                       {'staff': {'type': 'string'}, 'reason': {'type': 'string'}}, ['staff', 'reason']),
}
TERMINAL = {'send_reply', 'route_to_staff'}


# Tool descriptions that change with the routing variant, so the tool never invites more routing than the prompt allows.
ROUTE_DESC = {'narrow': 'Only for messages that threaten someone, involve legal action against {office_short}, or come from the media: '
                        'route the message to staff instead of replying, with one line saying what it is. Closes the message.'}


_WORD_CACHE = {}


def _word(term):
    """Whole-word match allowing short endings (bus, buses; fee, fees) but not substrings (bus in business). 7 Oct."""
    if term not in _WORD_CACHE:
        _WORD_CACHE[term] = re.compile(r'(?<![a-z0-9])' + re.escape(term) + r'(?:s|es|ed|ing|er|ers|\'s)?(?![a-z0-9])')
    return _WORD_CACHE[term]


def tool_schemas(staff_names, routing=None, office_short='the city'):
    out = []
    for name, (desc, props, required) in TOOLS.items():
        if name == 'route_to_staff' and routing in ROUTE_DESC:
            desc = ROUTE_DESC[routing].format(office_short=office_short)
        props = json.loads(json.dumps(props))
        if name == 'route_to_staff':
            props['staff']['enum'] = list(staff_names)
        out.append({'type': 'function', 'function': {'name': name, 'description': desc, 'parameters': {
            'type': 'object', 'properties': props, 'required': required, 'additionalProperties': False}}})
    return out


def _digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


class Drive:
    def __init__(self, drive_dir, log_path, staff_names, file_dates=None):
        self.root = Path(drive_dir).resolve()
        self.log_path = Path(log_path).resolve()
        if self.root in self.log_path.parents:
            raise ValueError('Keep logs outside the drive')
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.open('x').close()
        self.staff = list(staff_names)
        self.files = {str(p.relative_to(self.root)): p for p in sorted(self.root.rglob('*'))
                      if p.is_file() and p.name != '.DS_Store'}
        self.file_dates = file_dates or {}
        self.seq, self.prev = 0, None
        self.returned = []  # (sequence, tool, path, text) for everything shown to the model
        self.closed = None  # the terminal action for the current message
        self._log('session_start', {'files': len(self.files), 'drive_hash': _digest(''.join(sorted(self.files)))})

    def _log(self, event, payload):
        self.seq += 1
        row = {'sequence': self.seq, 'event': event, 'payload': payload, 'previous_hash': self.prev}
        row['hash'] = _digest(json.dumps(row, sort_keys=True, ensure_ascii=False))
        self.prev = row['hash']
        with self.log_path.open('a') as f:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())

    def _text(self, path):
        return self.files[path].read_text(errors='replace')

    def _safe(self, path):
        if not isinstance(path, str) or path.startswith('/') or '\\' in path or '..' in PurePosixPath(path).parts:
            raise ValueError('invalid_path')
        path = path.strip().strip('/')
        if path not in self.files:
            raise ValueError('file_not_found')
        return path

    def _meta(self, path):
        text = self._text(path)
        return {'path': path, 'lines': len(text.splitlines()), 'modified': self.file_dates.get(path, '')}

    def list_files(self, folder=''):
        folder = (folder or '').strip().strip('/')
        if '..' in PurePosixPath(folder).parts or '\\' in folder:
            raise ValueError('invalid_folder')
        if not folder:
            folders = sorted({p.split('/')[0] for p in self.files})
            return {'folders': [{'folder': f, 'files': sum(1 for p in self.files if p.startswith(f + '/'))} for f in folders]}
        hits = [self._meta(p) for p in self.files if p.startswith(folder + '/')]
        if not hits:
            raise ValueError('folder_not_found')
        return {'folder': folder, 'files': hits}

    def search_files(self, query):
        low_q = (query or '').lower()
        # Hyphenated codes ("k-9", "st-27-04") are kept whole as well as split (7 Oct: "K-9" matched nothing)
        terms = list(dict.fromkeys([t for t in re.findall(r'[a-z0-9]+(?:-[a-z0-9]+)+', low_q)] +
                                   [t for t in re.findall(r'[a-z0-9]+', low_q) if len(t) > 1]))
        if not terms:
            raise ValueError('invalid_query')
        scored = []
        for path in self.files:
            text = self._text(path)
            hay = (path + ' ' + text).lower()
            counts = [len(_word(t).findall(hay)) for t in terms]
            if not any(counts):
                continue
            score = sum(c > 0 for c in counts) * 1000 + sum(min(c, 50) for c in counts)
            start = max(0, self._anchor(text, terms) - EXCERPT_LEAD)
            scored.append((score, path, text[start:start + EXCERPT_CHARS]))
        scored.sort(key=lambda x: (-x[0], x[1]))
        results = [{'path': p, 'excerpt': ex} for _, p, ex in scored[:SEARCH_RESULTS]]
        return {'query': query, 'total_matches': len(scored), 'results': results}

    def _df(self, term):
        if not hasattr(self, '_dfc'):
            self._dfc = {}
        if term not in self._dfc:
            self._dfc[term] = sum(bool(_word(term).search((p + ' ' + self._text(p)).lower())) for p in self.files)
        return self._dfc[term]

    def _anchor(self, text, terms):
        """Character offset of the first occurrence of the query's most distinctive word that appears in the text."""
        low = text.lower()
        hits = {t: _word(t).search(low) for t in terms}
        cands = [t for t in terms if t not in STOPWORDS and len(t) > 2 and hits[t]] or [t for t in terms if hits[t]]
        if not cands:
            return 0
        best = min(cands, key=lambda t: (self._df(t), -len(t)))
        return hits[best].start()

    def read_file(self, path, start_line=1, max_lines=READ_MAX_LINES):
        path = self._safe(path)
        if type(start_line) is not int or start_line < 1:
            raise ValueError('invalid_line_range')
        if type(max_lines) is not int or max_lines < 1:
            max_lines = READ_MAX_LINES
        max_lines = min(max_lines, READ_MAX_LINES)  # oversized requests are clipped, not refused (7 Oct)
        lines = self._text(path).splitlines()
        chunk = lines[start_line - 1:start_line - 1 + max_lines]
        numbered = '\n'.join(f'{start_line + i}: {ln}' for i, ln in enumerate(chunk))
        end = start_line - 1 + len(chunk)
        return {'path': path, 'total_lines': len(lines), 'start_line': start_line, 'end_line': end,
                'more': end < len(lines), 'text': numbered}

    def call(self, name, args, *, turn):
        """Run one tool call and return the result the model sees."""
        self._log('tool_request', {'turn': turn, 'name': name, 'arguments': args})
        try:
            if name not in TOOLS or not isinstance(args, dict):
                raise ValueError('unknown_tool')
            _, props, required = TOOLS[name]
            if set(args) - set(props) or set(required) - set(args):
                raise ValueError('invalid_arguments')
            if self.closed is not None:
                raise ValueError('message_already_closed')
            if name == 'list_files':
                value = self.list_files(args.get('folder', ''))
            elif name == 'search_files':
                value = self.search_files(args['query'])
                for r in value['results']:
                    self.returned.append((self.seq, name, r['path'], r['excerpt']))
            elif name == 'read_file':
                value = self.read_file(args['path'], args.get('start_line', 1), args.get('max_lines', READ_MAX_LINES))
                self.returned.append((self.seq, name, value['path'], value['text']))
            elif name == 'send_reply':
                if not isinstance(args['body'], str) or not args['body'].strip():
                    raise ValueError('empty_reply')
                self.closed = {'action': 'send_reply', 'body': args['body'], 'sequence': self.seq}
                value = {'sent': True}
            else:
                if args['staff'] not in self.staff:
                    raise ValueError('unknown_staff')
                self.closed = {'action': 'route_to_staff', 'staff': args['staff'], 'reason': args['reason'], 'sequence': self.seq}
                value = {'routed': True, 'staff': args['staff']}
            value = {'ok': True, **value}
        except (ValueError, KeyError, OSError) as e:
            value = {'ok': False, 'error': str(e).strip("'")}
        self._log('tool_result', {'turn': turn, 'name': name, 'result': value})
        return value

    def next_message(self):
        """Runner-only: start a new mail item (the previous one must be closed)."""
        self.closed = None
        self._log('next_message', {})

    def seen_before(self, sequence):
        """Every text returned to the model before the given log sequence number."""
        return [(path, text) for seq, _, path, text in self.returned if seq < sequence]
