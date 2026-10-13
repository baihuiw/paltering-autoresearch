#!/usr/bin/env python3
"""Build a research post: post.html + post_data.json -> index.html, with fidelity checks.

Usage:
    python build.py post.html post_data.json --out site/index.html
    python build.py post.html post_data.json --out site/index.html --external-data   # big explorers
    python build.py post.html post_data.json --out site/index.html --draft           # errors become warnings

Placeholders resolved in post.html:
    {{stat:path.to.key|fmt}}  number from the data, formatted. fmt is one of:
                              int, num0..num3, pct0..pct2 (value is a 0-1 proportion),
                              pp0..pp2 (signed difference of proportions, "+17.5 points"), x1..x2 ("2.3x")
    {{text:path.to.key}}      string from the data, HTML-escaped
    {{meta:key}}              shorthand for {{text:meta.key}}
    {{quote:id}}              annotated transcript from data["quotes"][id]
    {{data}}                  the data file as JSON (keys starting with "_" are dropped)

Checks (errors stop the build unless --draft):
    - every placeholder resolves
    - every highlight string appears verbatim in its transcript
    - every transcript with a "source" appears verbatim in that source file
      (json, jsonl, csv, txt, optionally .gz); "[...]" or "[…]" marks trimmed text
Warnings (never stop the build):
    - numbers typed by hand in prose instead of coming from {{stat:...}}
    - transcripts with no source that are not marked "authored"
    - TODO / CITE style placeholders left in the text
    - missing <title> / meta description, images without alt text, prose length
"""
import argparse, csv, gzip, html, io, json, re, sys
from html.parser import HTMLParser
from pathlib import Path

ELISION = re.compile(r"\[(?:\.\.\.|…)\]")
PLACEHOLDER = re.compile(r"\{\{\s*(stat|text|meta|quote|data)\s*(?::\s*([^}|]+?))?\s*(?:\|\s*([a-z]+\d?))?\s*\}\}")


def get(data, path):
    cur = data
    for key in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(key)]
        else:
            cur = cur[key]
    return cur


def fmt(v, f):
    if f is None:
        f = "num1"
    if f == "int":
        return f"{round(v):,}"
    m = re.fullmatch(r"(pct|pp|num|x)(\d)", f)
    if not m:
        raise ValueError(f"unknown format '{f}'")
    kind, d = m.group(1), int(m.group(2))
    if kind == "pct":
        return f"{v * 100:.{d}f}%"
    if kind == "pp":
        sign = "+" if v > 0 else "\u2212" if v < 0 else ""
        return f"{sign}{abs(v) * 100:.{d}f} points"
    if kind == "x":
        return f"{v:.{d}f}\u00d7"
    return f"{v:,.{d}f}"


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


# ---------- source verification -------------------------------------------------
def strings_in(obj, out):
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            strings_in(v, out)
    elif isinstance(obj, list):
        for v in obj:
            strings_in(v, out)


_source_cache = {}


def load_source_strings(path):
    if path in _source_cache:
        return _source_cache[path]
    p = Path(path)
    raw = gzip.open(p, "rt", encoding="utf-8").read() if p.suffix == ".gz" else p.read_text(encoding="utf-8")
    name = p.name[:-3] if p.suffix == ".gz" else p.name
    out = []
    if name.endswith(".jsonl"):
        for line in raw.splitlines():
            if line.strip():
                strings_in(json.loads(line), out)
    elif name.endswith(".json"):
        strings_in(json.loads(raw), out)
    elif name.endswith(".csv"):
        for row in csv.reader(io.StringIO(raw)):
            out.extend(row)
    else:
        out.append(raw)
    blob = "\n".join(norm(s) for s in out)
    _source_cache[path] = blob
    return blob


def verify_quote(qid, q, base, errors, warnings):
    all_text = []
    for ci, col in enumerate(q.get("columns", [])):
        for ti, turn in enumerate(col.get("turns", [])):
            all_text.append(turn.get("text", ""))
            if col.get("authored") or turn.get("role") == "context":
                continue
            src = turn.get("source") or col.get("source") or q.get("source")
            if not src:
                warnings.append(f"quote '{qid}' column {ci} turn {ti}: no source file, so it cannot be checked verbatim. "
                                f"Add \"source\", or mark the column \"authored\": true if you wrote it.")
                continue
            src_path = (base / src).resolve()
            if not src_path.exists():
                errors.append(f"quote '{qid}': source file not found: {src}")
                continue
            blob = load_source_strings(str(src_path))
            for seg in ELISION.split(turn.get("text", "")):
                seg = norm(seg)
                if seg and seg not in blob:
                    errors.append(f"quote '{qid}' column {ci} turn {ti}: text not found verbatim in {src}: \"{seg[:90]}...\"")
    joined = "\n".join(all_text)
    for h in q.get("highlights", []):
        if h["text"] not in joined:
            errors.append(f"quote '{qid}': highlight is not an exact substring of the transcript: \"{h['text'][:90]}\"")


# ---------- transcript markup (mirrors renderTranscript in template.html) ------
def render_quote(q):
    notes, cols_html = [], []
    for col in q.get("columns", []):
        parts = [f'<div class="t-head"><span>{html.escape(col.get("heading", ""))}</span>']
        if col.get("tag"):
            parts.append(f'<span class="t-tag" data-tag="{html.escape(col.get("tag_kind", ""))}">{html.escape(col["tag"])}</span>')
        parts.append("</div>")
        if col.get("authored"):
            parts.append('<span class="t-authored">Written for the study, not a model output</span>')
        for turn in col.get("turns", []):
            h = html.escape(turn.get("text", ""), quote=False)
            for hl in q.get("highlights", []):
                e = html.escape(hl["text"], quote=False)
                if e in h:
                    n = ""
                    if hl.get("note"):
                        notes.append(hl["note"])
                        n = f"<sup>{len(notes)}</sup>"
                    cls = "key" if hl.get("kind") == "key" else ""
                    h = h.replace(e, f'<mark class="{cls}">{e}{n}</mark>', 1)
            h = "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in re.split(r"\n{2,}", h))
            role = html.escape(turn.get("role", "model"))
            who = html.escape(turn.get("label", turn.get("role", "")))
            parts.append(f'<div class="t-turn {role}"><span class="who">{who}</span><div>{h}</div></div>')
        cols_html.append('<div class="t-col">' + "".join(parts) + "</div>")
    pair = " pair" if len(cols_html) > 1 else ""
    out = f'<div class="transcript{pair}"><div class="transcript-cols">' + "".join(cols_html) + "</div>"
    if notes:
        out += '<ol class="t-notes">' + "".join(
            f"<li><b>{i + 1}</b><span>{html.escape(n, quote=False)}</span></li>" for i, n in enumerate(notes)) + "</ol>"
    return out + "</div>"


# ---------- prose lint ----------------------------------------------------------
class ProseLint(HTMLParser):
    PROSE = {"p", "li", "h1", "h2", "h3", "figcaption", "summary", "dd", "dt", "td"}
    SKIP = {"script", "style", "pre", "code", "sup"}
    VOID = {"meta", "link", "br", "img", "hr", "input", "source", "wbr"}
    NUM = re.compile(r"(?<![\w.\-])\d[\d,]*(?:\.\d+)?%?(?![\w\-]|\.\d)")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.bare, self.todos, self.words = [], [], [], 0
        self.has_title = self.has_desc = False
        self.img_no_alt = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("name") == "description" and a.get("content", "").strip():
            self.has_desc = True
        if tag == "img" and not a.get("alt"):
            self.img_no_alt += 1
        if tag in self.VOID:
            return
        cls = a.get("class") or ""
        exempt = (bool({"stat", "status", "byline"} & set(cls.split())) or "data-literal" in a or "data-from" in a
                  or "transcript" in cls or "t-notes" in cls or tag in self.SKIP)
        self.stack.append((tag, exempt))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        tags = [t for t, _ in self.stack]
        if "title" in tags and data.strip():
            self.has_title = True
        if any(ex for _, ex in self.stack) or not (set(tags) & self.PROSE):
            return
        self.words += len(data.split())
        for m in re.finditer(r"\[(TODO|CITE|STAT|EXAMPLE|N ?=|LINK)[^\]]*\]", data):
            self.todos.append(m.group(0))
        for m in self.NUM.finditer(data):
            tok = m.group(0)
            if re.fullmatch(r"(19|20)\d\d", tok):  # years
                continue
            ctx = data[max(0, m.start() - 30): m.end() + 20].strip()
            self.bare.append((tok, norm(ctx)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("post"), ap.add_argument("data")
    ap.add_argument("--out", default="index.html")
    ap.add_argument("--external-data", action="store_true", help="write data.json next to the page instead of embedding it")
    ap.add_argument("--draft", action="store_true", help="report errors but still write the page")
    ap.add_argument("--source-root", default=None, help="folder that quote 'source' paths are relative to (default: the data file's folder)")
    args = ap.parse_args()

    src = Path(args.post).read_text(encoding="utf-8")
    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    base = Path(args.source_root) if args.source_root else Path(args.data).resolve().parent
    errors, warnings = [], []

    for qid, q in (data.get("quotes") or {}).items():
        verify_quote(qid, q, base, errors, warnings)
    for coll in data.values():  # explorer rows share the quote shape
        if isinstance(coll, list):
            for i, row in enumerate(coll):
                if isinstance(row, dict) and "columns" in row:
                    verify_quote(f"{row.get('id', i)}", row, base, errors, [])

    public = {k: v for k, v in data.items() if not k.startswith("_")}

    def strip_private(o):
        if isinstance(o, dict):
            return {k: strip_private(v) for k, v in o.items() if k != "source"}
        if isinstance(o, list):
            return [strip_private(v) for v in o]
        return o
    public = strip_private(public)
    payload = json.dumps(public, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    def resolve(m):
        kind, arg, f = m.group(1), (m.group(2) or "").strip(), m.group(3)
        try:
            if kind == "data":
                return "{}" if args.external_data else payload
            if kind == "meta":
                return html.escape(str(get(data, "meta." + arg)), quote=True)
            if kind == "text":
                return f'<span data-from="{html.escape(arg)}">{html.escape(str(get(data, arg)), quote=False)}</span>' \
                    if not arg.startswith("meta.") else html.escape(str(get(data, arg)), quote=False)
            if kind == "stat":
                return f'<span class="stat" data-stat="{html.escape(arg)}">{fmt(get(data, arg), f)}</span>'
            if kind == "quote":
                return render_quote(get(data, "quotes." + arg))
        except (KeyError, IndexError, TypeError, ValueError) as e:
            errors.append(f"placeholder {m.group(0)} did not resolve: {e!r}")
            return m.group(0)
        return m.group(0)

    # placeholders inside HTML comments are documentation, so leave comments untouched
    pieces = re.split(r"(<!--.*?-->)", src, flags=re.S)
    out_html = "".join(p if p.startswith("<!--") else PLACEHOLDER.sub(resolve, p) for p in pieces)
    if args.external_data:
        out_html = out_html.replace('<script type="application/json" id="post-data">',
                                    '<script>window.RP_DATA_URL="data.json";</script>\n<script type="application/json" id="post-data">', 1)

    lint = ProseLint()
    lint.feed(re.sub(r"<!--.*?-->", "", out_html, flags=re.S))
    if not lint.has_title:
        warnings.append("missing <title>")
    if not lint.has_desc:
        warnings.append("missing meta description (used by link previews)")
    if lint.img_no_alt:
        warnings.append(f"{lint.img_no_alt} image(s) without alt text")
    for tok, ctx in lint.bare:
        warnings.append(f"number typed by hand: '{tok}' in \"...{ctx}...\". Use {{{{stat:...}}}}, or wrap in <span data-literal> if it is not a result.")
    for t in lint.todos:
        warnings.append(f"unfinished placeholder left in text: {t}")
    status = (data.get("meta") or {}).get("status", "")
    if status in ("preliminary", "in progress") and 'class="status"' not in out_html:
        warnings.append("meta.status is preliminary but the page has no .status banner")
    mode = (data.get("meta") or {}).get("mode", "rich")
    limit = 1100 if mode == "light" else 2200
    if lint.words > limit:
        warnings.append(f"prose is about {lint.words} words; {mode} posts read best under {limit}. Move detail into disclosures or the paper.")

    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    if errors and not args.draft:
        print(f"\nBuild stopped: {len(errors)} error(s). Fix them, or pass --draft to write the page anyway.")
        sys.exit(1)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(out_html, encoding="utf-8")
    if args.external_data:
        (out.parent / "data.json").write_text(payload.replace("<\\/", "</"), encoding="utf-8")
    kb = len(out_html.encode()) / 1024
    print(f"\nWrote {out} ({kb:,.0f} KB), about {lint.words} words of prose, {len(warnings)} warning(s), {len(errors)} error(s).")
    if kb > 3000 and not args.external_data:
        print("The page is over 3 MB. Consider --external-data, or trimming the explorer rows.")


if __name__ == "__main__":
    main()
