"""`workflow research`: research notes in `docs/research/<topic>/` (spec #505).

The folder's one fixed layout is in the `study` skill's text, which the tests'
fixtures are copied from:

- `note.md`, the note: three header lines (`Status:`, `Last checked:`,
  `Issue:`), then a blank line; its key sources one line each under
  `## Key sources`, once, outside any code fence: `- <link>, saved as `path`,
  fingerprints in `path``. The section runs to the next `# ` or `## `
  heading, or the note's end. Every fingerprint file anywhere in the topic's
  folder (named `*.fingerprints`, or, whatever its name, a file whose first
  line is a `url:` line) must be named by a key-source line there, so a key
  source written anywhere else is refused, naming its file, and none goes
  unread; so is a file there that can't be read.
  The rest of the note is prose, never read for key sources;
- a saved copy: `Source:`, `Accessed:` and `Third-party text:` lines, a blank
  line, then the page's paragraphs, one per position, separated by blank lines
  (a paragraph left out whole is one `[left out]` line in its place);
- a fingerprint file: `url: <link>`, then `<position> <sha256>` per paragraph
  of the page as fetched, before anything is left out. Hashes only, no text.

`fingerprint` reads a page (a file, or with `--fetch` the web), splits its text
into paragraphs and hashes each; `check` compares a note's key sources against
their fingerprints as a set; `notes` lists the notes marked `current`. None of
it calls a model, and none of it writes anything: the session writes the saved
copy and the fingerprint file from `fingerprint`'s output.
"""

from __future__ import annotations

import codecs
import hashlib
import http.client
import os
import re
import ssl
import stat
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

LEFT_OUT = "[left out]"
NOTE_FILE = "note.md"
FINGERPRINTS = ".fingerprints"  # a fingerprint file's name ends with it
FIRST_BYTES = 512  # read of each other file in a topic's folder, to tell whether it's a fingerprint file
FETCH_LIMIT = 10 * 1024 * 1024  # bytes
FETCH_TIMEOUT = 30  # seconds
USER_AGENT = "pairnexus-workflow-research/1"

_HASH = re.compile(r"[0-9a-f]{64}")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_KEY_SOURCE = re.compile(r"- <(?P<url>[^<>\s]+)>, saved as `(?P<saved>[^`]+)`, fingerprints in `(?P<fps>[^`]+)`")
_WS = re.compile(r"\s+")


class PageError(Exception):
    """A page that can't be fetched or read as text; the reason is its message."""


class LayoutError(Exception):
    """A note, saved copy or fingerprint file that breaks the fixed layout."""


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _flat(text: str) -> str:
    return _WS.sub(" ", text).strip()


def leave_out(text: str, patterns: list[str]) -> tuple[str, int]:
    """The text with every match of the profile's `[sensitive].patterns` left out."""
    n = 0
    for p in patterns:
        text, k = re.subn(p, LEFT_OUT, text)
        n += k
    return text, n


# ---------- reading a page ----------


# Elements whose content is never the page's text.
_SKIP = {"script", "style", "noscript", "template", "svg", "math", "head", "nav", "iframe", "object", "canvas", "select"}
# Elements that start and end a paragraph.
_BLOCK = {
    "address", "article", "aside", "blockquote", "body", "caption", "dd", "details", "dialog", "div", "dl", "dt",
    "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hgroup",
    "hr", "html", "li", "main", "ol", "p", "pre", "section", "summary", "table", "tbody", "tfoot", "thead", "tr", "ul",
}
_SPACE = {"br", "td", "th", "img", "input", "wbr"}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
# A head that `</head>` or `<body>` never ends ends, as HTML5 says, at the
# first tag or text that isn't head content (#526). Inside these, nothing ends
# it: a template's content, and the raw text of the others (a title's tags,
# and a noscript's, as a browser running scripts reads them).
_HEAD_CONTENT = {"base", "basefont", "bgsound", "link", "meta", "noframes", "noscript", "script", "style", "template", "title"}
_HEAD_RAW = {"noframes", "noscript", "script", "style", "title"}
_HTML_SPACE = " \t\n\f\r"


class _Text(HTMLParser):
    """The page's paragraphs. A head ends at `</head>` or `<body>`; with
    `open_head`, one that neither ends also ends at the first tag or text that
    isn't head content. `head_left_open` says the page's first head never
    ended."""

    def __init__(self, open_head: bool = False):
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self._now: list[str] = []
        self._skip: list[str] = []
        self._open_head = open_head
        self._head = ""  # "open" once the first head starts, "ended" once it ends
        self.head_left_open = False

    def close(self):
        super().close()
        self._end_paragraph()
        self.head_left_open = self._head == "open"

    def _end_paragraph(self):
        text = _flat("".join(self._now))
        if text:
            self.paragraphs.append(text)
        self._now = []

    def _end_head(self):
        self._skip = []
        if self._head == "open":
            self._head = "ended"

    def _in_head(self) -> bool:
        """Directly in a head no `</head>` or `<body>` has ended yet, with `open_head`."""
        return self._open_head and self._skip == ["head"]

    def handle_starttag(self, tag, attrs):
        if self._open_head and self._skip[:1] == ["head"]:
            if len(self._skip) > 1 and self._skip[1] in _HEAD_RAW:
                return  # raw text: nothing in it is a tag
            if self._in_head():
                if tag in ("head", "html"):
                    return
                if tag in _HEAD_CONTENT:
                    if tag in _HEAD_RAW or tag == "template":  # the others have no end tag
                        self._skip.append(tag)
                    return
                self._end_head()  # anything else ends the head, and is read
        if tag == "body" and self._skip[:1] == ["head"]:
            self._end_head()  # `</head>` may be left out: the head ends at `<body>`
        if tag == "head" and not self._skip and not self._head:
            self._head = "open"
        if self._open_head and self._skip[:1] in (["title"], ["noframes"]):
            return  # raw text: nothing in it is a tag
        if self._skip:
            if tag == self._skip[-1] and tag not in _VOID:
                self._skip.append(tag)
            return
        if tag in _SKIP or (self._open_head and tag in ("title", "noframes")):  # head content wherever it is, as HTML5 says
            if tag not in _VOID:
                self._skip.append(tag)
            return
        if tag in _BLOCK:
            self._end_paragraph()
        elif tag in _SPACE:
            self._now.append(" ")

    def handle_startendtag(self, tag, attrs):  # <x/>: opens nothing
        if self._in_head() and tag not in _HEAD_CONTENT and tag not in ("head", "html"):
            self._end_head()
        if self._skip or tag in _SKIP:
            return
        if tag in _BLOCK:
            self._end_paragraph()
        elif tag in _SPACE:
            self._now.append(" ")

    def handle_endtag(self, tag):
        if self._in_head() and tag in ("body", "html", "br"):
            self._end_head()  # these end the head, and are read; any other end tag in it is ignored
        if self._skip:
            if tag == self._skip[-1]:
                self._skip.pop()
                if not self._skip and tag == "head":
                    self._end_head()
            return
        if tag in _BLOCK:
            self._end_paragraph()
        elif tag in _SPACE:
            self._now.append(" ")

    def handle_data(self, data):
        if self._in_head() and data.strip(_HTML_SPACE):
            self._end_head()  # text that isn't white space ends the head, and is read
        if not self._skip:
            self._now.append(data)


def _kind(content_type: str, raw: bytes) -> str:
    """"html" or "text" by the content type; with none named, by the bytes,
    only where they are clearly an HTML or plain-text page (`_untyped_kind`).
    Raises PageError for anything else (a PDF, an image)."""
    ctype = content_type.split(";", 1)[0].strip().lower()
    if ctype in ("text/html", "application/xhtml+xml"):
        return "html"
    if ctype.startswith("text/"):
        return "text"
    if not ctype:
        return _untyped_kind(raw)
    raise PageError(f"it isn't a text page ({ctype})")


# Formats whose first bytes can be printable ASCII: refused even then.
_NOT_TEXT_STARTS = (b"%PDF-", b"%!PS", b"GIF87a", b"GIF89a", b"RIFF", b"\x89PNG", b"\xff\xd8\xff")
# C0 and C1 control characters, but for tab, line feed, form feed and carriage return.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f-\x9f]")
_SPACES = re.compile(r"\s*")
_XML_DECLARATION = re.compile(r"<\?xml\b[^>]*\?>", re.I)
_HTML_TAG = re.compile(r"<(?:!doctype\s+html|html)[\s>]", re.I)


def _starts_as_html(text: str) -> bool:
    """Whether the text starts with `<!doctype html>` or `<html>`, after an
    XML declaration (XHTML), comments and whitespace."""
    i = _SPACES.match(text).end()
    m = _XML_DECLARATION.match(text, i)
    if m:
        i = _SPACES.match(text, m.end()).end()
    while text.startswith("<!--", i):
        end = text.find("-->", i + 4)
        if end < 0:
            return False
        i = _SPACES.match(text, end + 3).end()
    return _HTML_TAG.match(text, i) is not None


def _untyped_kind(raw: bytes) -> str:
    """A page that names no content type: "html" when its bytes start as an
    HTML page, "text" when they are plain text. Fails closed: bytes that
    start like a PDF or an image (or hold `%PDF-` in their first 1024 bytes,
    where PDF readers look for it), hold a control character (a NUL among
    them), aren't valid UTF-8, or start with markup that isn't HTML (an SVG,
    say) or a character that isn't shown (`_shown`) raise PageError."""
    why = "it names no content type, and its bytes aren't clearly a text page"
    i = 0
    while raw.startswith(b"\xef\xbb\xbf", i):  # every leading BOM, as `paragraphs` strips them
        i += 3
    body = raw[i:]
    if any(body.lstrip().startswith(sig) for sig in _NOT_TEXT_STARTS) or b"%PDF-" in body[:1024]:
        raise PageError(f"{why}: they start like a PDF or an image")
    try:
        text = body.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise PageError(f"{why}: they aren't valid UTF-8") from None
    if _CONTROL.search(text):
        raise PageError(f"{why}: they hold a control character")
    if _starts_as_html(text):
        return "html"
    j = _SPACES.match(text).end()
    first = text[j : j + 1]
    if first == "<":
        raise PageError(f"{why}: they start with markup that isn't HTML")
    if first and not _shown(first):  # it hides what follows
        raise PageError(f"{why}: they start with a character that isn't shown")
    return "text"


# Letters and symbols that show as blank, though printable.
_BLANK = frozenset("ᅟᅠㅤﾠ⠀\U0001d159")


def _shown(c: str) -> bool:
    """Whether a page's first character is shown on its own: printable (so not a
    format, private-use or unassigned character), not a mark, and not blank."""
    return c.isprintable() and not unicodedata.category(c).startswith("M") and c not in _BLANK


def _charset(content_type: str, raw: bytes, kind: str) -> str | None:
    """The charset the page names: the header's, else an HTML page's `<meta>`, else none."""
    m = re.search(r"charset=[\"']?([A-Za-z0-9_.:-]+)", content_type, re.I)
    if m:
        return m.group(1)
    if kind == "html":
        m = re.search(rb"<meta[^>]+charset=[\"']?([A-Za-z0-9_.:-]+)", raw[:4096], re.I)
        if m:
            return m.group(1).decode("ascii")
    return None


def _is_utf8(name: str) -> bool:
    try:
        return codecs.lookup(name).name in ("utf-8", "ascii")
    except (LookupError, UnicodeError, ValueError):
        return False


def paragraphs(raw: bytes, content_type: str) -> list[str]:
    """The page's text, as paragraphs: HTML by its block elements (scripts,
    styles, the head and navigation left out), plain text by its blank lines.
    Whitespace inside a paragraph is one space; empty paragraphs are dropped.
    Only UTF-8 pages are read: a page naming another charset, bytes that
    aren't valid UTF-8, HTML it can't parse, or a page with no content type
    whose bytes aren't clearly HTML or plain text raises PageError."""
    kind = _kind(content_type, raw)
    name = _charset(content_type, raw, kind)
    if name is not None and not _is_utf8(name):
        raise PageError(f"it is in {name}; only UTF-8 pages are read")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise PageError("its bytes aren't valid UTF-8") from None
    text = text.lstrip("\ufeff")
    if kind == "html":
        try:
            p = _Text()
            p.feed(text)
            p.close()
            if p.head_left_open:  # read again, ending the head as HTML5 does; a closed head reads as before
                p = _Text(open_head=True)
                p.feed(text)
                p.close()
        except Exception as e:  # html.parser's own errors on odd markup
            raise PageError(f"its HTML can't be read ({type(e).__name__})") from None
        return p.paragraphs
    return [t for t in (_flat(c) for c in re.split(r"\n[ \t\r\f\v]*\n", text.replace("\r\n", "\n").replace("\r", "\n"))) if t]


def read_page(path: Path) -> tuple[bytes, str]:
    """A page saved as a file: its bytes, and a content type by its name.
    Raises PageError for a name that isn't an HTML or plain-text page's."""
    suffix = Path(path).suffix.lower()
    ctype = "text/html" if suffix in (".html", ".htm", ".xhtml") else "text/plain" if suffix in (".txt", ".md") else ""
    if not ctype:
        what = f"a `{suffix}` file" if suffix else "a file with no suffix"
        raise PageError(f"it isn't a text page ({what}): give the page as .html, .htm, .xhtml, .txt or .md")
    return Path(path).read_bytes(), ctype


def fetch(url: str, timeout: float = FETCH_TIMEOUT, limit: int = FETCH_LIMIT) -> tuple[bytes, str]:
    """The page at a web link: its bytes and content type. Only http and https,
    redirects included, and only a link written in ASCII; raises PageError
    with the reason it can't."""
    if not url.isascii():
        raise PageError("it holds characters outside ASCII; cite the link percent-encoded")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise PageError("it isn't an http or https link")
    opener = urllib.request.OpenerDirector()
    for h in (
        urllib.request.ProxyHandler(),
        urllib.request.HTTPHandler(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        urllib.request.HTTPRedirectHandler(),
        urllib.request.HTTPDefaultErrorHandler(),
        urllib.request.HTTPErrorProcessor(),
    ):
        opener.add_handler(h)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html, text/plain;q=0.9, */*;q=0.1"})
    try:
        with opener.open(req, timeout=timeout) as r:
            raw = r.read(limit + 1)
            ctype = r.headers.get("Content-Type", "") or ""
    except urllib.error.HTTPError as e:
        raise PageError(f"HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise PageError(str(e.reason)) from None
    except (OSError, ValueError, http.client.HTTPException) as e:
        raise PageError(f"{type(e).__name__}: {e}") from None
    if len(raw) > limit:
        raise PageError(f"it is over {limit // (1024 * 1024)} MB")
    return raw, ctype


def page_paragraphs(raw: bytes, ctype: str) -> list[str]:
    """`paragraphs`, refusing a page with no text (built by JavaScript, say),
    whose fingerprints could never show a change."""
    paras = paragraphs(raw, ctype)
    if not paras:
        raise PageError("there is no text on it (a page built by JavaScript?)")
    return paras


# ---------- reading the layout ----------


def _lines(text: str) -> list[str]:
    return text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n").split("\n")


def read_fingerprints(text: str, name: str) -> tuple[str, list[str]]:
    lines = [l.rstrip() for l in _lines(text)]
    while lines and not lines[-1]:
        lines.pop()
    if not lines or not lines[0].startswith("url: "):
        raise LayoutError(f"{name}: the first line isn't `url: <link>`")
    hashes = []
    for i, line in enumerate(lines[1:], 1):
        pos, _, h = line.partition(" ")
        if pos != str(i) or not _HASH.fullmatch(h):
            raise LayoutError(f"{name}: line {i + 1} isn't `{i} <sha256>`, a fingerprint for paragraph {i}")
        hashes.append(h)
    if not hashes:
        raise LayoutError(f"{name}: it holds no fingerprints")
    return lines[0][5:].strip(), hashes


def read_saved_copy(text: str, name: str) -> tuple[str, list[str]]:
    lines = _lines(text)
    want = ("Source: ", "Accessed: ", "Third-party text:")
    for i, start in enumerate(want):
        if len(lines) <= i or not lines[i].startswith(start):
            raise LayoutError(f"{name}: line {i + 1} isn't the `{start.strip()}` line")
    if len(lines) < 4 or lines[3].strip():
        raise LayoutError(f"{name}: line 4 isn't blank")
    body = "\n".join(lines[4:])
    paras = [t for t in (_flat(c) for c in re.split(r"\n[ \t]*\n", body)) if t]
    return lines[0][len("Source: "):].strip(), paras


@dataclass
class Header:
    status: str
    last_checked: str
    issue: int
    title: str = ""


def read_header(text: str) -> Header:
    """The note's three header lines, or LayoutError saying what's wrong."""
    lines = [l.rstrip() for l in _lines(text)]
    for i, start in enumerate(("Status: ", "Last checked: ", "Issue: ")):
        if len(lines) <= i or not lines[i].startswith(start):
            raise LayoutError(f"line {i + 1} isn't the `{start.strip()}` line")
    status, checked, issue = (lines[i].split(": ", 1)[1].strip() for i in range(3))
    if status != "current" and not (status.startswith("superseded by ") and status[len("superseded by "):].strip()):
        raise LayoutError(f"`Status: {status}` is neither `current` nor `superseded by <link>`")
    if not _DATE.fullmatch(checked):
        raise LayoutError(f"`Last checked: {checked}` isn't a date (YYYY-MM-DD)")
    if not re.fullmatch(r"#[1-9][0-9]*", issue):
        raise LayoutError(f"`Issue: {issue}` isn't `#<n>`")
    title = next((l[2:].strip() for l in lines[3:] if l.startswith("# ")), "")
    return Header(status, checked, int(issue[1:]), title)


@dataclass
class KeySource:
    url: str
    saved: Path
    fingerprints: Path
    hashes: list[str] = field(default_factory=list)
    saved_paragraphs: list[str] = field(default_factory=list)


def _inside(folder: Path, rel: str, what: str, url: str) -> Path:
    p = Path(rel)
    target = (folder / p).resolve()
    if p.is_absolute() or not target.is_relative_to(folder.resolve()):
        raise LayoutError(f"{url}: its {what} `{rel}` is outside the topic's folder")
    return target


def _heading_level(line: str) -> int:
    """1 to 6 for an ATX heading written at the line's start (`## Notes`), else 0."""
    level = len(line) - len(line.lstrip("#"))
    return level if 1 <= level <= 6 and (len(line) == level or line[level] in " \t") else 0


def _names_key_sources(line: str) -> bool:
    """Whether the line is a heading named "Key sources" in any form a reader
    could take for one: at any level, in any case, indented, in a quote."""
    s = line.strip()
    while s.startswith(">"):
        s = s[1:].strip()
    level = len(s) - len(s.lstrip("#"))
    if not level or (len(s) > level and s[level] not in " \t"):
        return False
    return " ".join(s[level:].strip().rstrip("#").split()).casefold() == "key sources"


def _fence(line: str) -> tuple[str, int, str] | None:
    """(its character, its length, what follows) for a code fence's line
    (three or more backticks or tildes, indented at most 3 spaces), else None."""
    s = line.lstrip(" ")
    if len(line) - len(s) > 3 or s[:1] not in ("`", "~"):
        return None
    length = len(s) - len(s.lstrip(s[0]))
    rest = s[length:]
    if length < 3 or (s[0] == "`" and "`" in rest):
        return None
    return s[0], length, rest.strip()


def _key_sources_section(lines: list[str], path: Path) -> tuple[int, int]:
    """(the `## Key sources` heading's index, the index where its section
    ends: the next `# ` or `## ` heading, or the note's end). Fails closed:
    a note whose key sources can't all be read is refused, naming the line,
    rather than read in part."""
    heads: list[tuple[int, int | None]] = []  # (index, the opening fence's index when inside one)
    fence: tuple[str, int, int] | None = None
    for i, line in enumerate(lines):
        if _names_key_sources(line):
            heads.append((i, fence[2] if fence else None))
        f = _fence(line)
        if fence is None:
            if f:
                fence = (f[0], f[1], i)
        elif f and f[0] == fence[0] and f[1] >= fence[1] and not f[2]:
            fence = None
    if not heads:
        raise LayoutError(f"{path}: it has no `## Key sources` section (write `- None` under it when there are none)")
    for i, opened in heads:
        if opened is not None:
            raise LayoutError(
                f"{path}: line {i + 1} names `## Key sources` inside a code fence (opened on line {opened + 1}): the section must be outside any fence, once: {lines[i][:200]}"
            )
    if len(heads) > 1:
        raise LayoutError(
            f"{path}: the note has `## Key sources` more than once (lines {', '.join(str(i + 1) for i, _ in heads)}), so line {heads[1][0] + 1} would go unread: "
            f"list every key source under one heading: {lines[heads[1][0]][:200]}"
        )
    start = heads[0][0]
    if lines[start] != "## Key sources":
        raise LayoutError(f"{path}: line {start + 1} names the key sources but isn't the heading `## Key sources`, written at the line's start: {lines[start][:200]}")
    end = next((j for j in range(start + 1, len(lines)) if 1 <= _heading_level(lines[j]) <= 2), len(lines))
    return start, end


def _is_fingerprint_file(f: Path, path: Path) -> bool:
    """Whether `f` is a fingerprint file: named `*.fingerprints`, or, whatever
    its name, a file whose first line is a `url:` line (only its first bytes
    are read). A file that can't be read can't be ruled out: refused."""
    if f.name.endswith(FINGERPRINTS):
        return True
    try:
        if not stat.S_ISREG(os.stat(f).st_mode):
            return False
        with open(f, "rb") as fh:
            first = fh.read(FIRST_BYTES)
    except OSError as e:
        raise LayoutError(
            f"{path}: {f} is a file in the topic's folder that can't be read ({e.strerror or e}), so it can't be ruled out as a fingerprint file "
            "whose source wouldn't be read: make it readable, or move it out of the topic's folder"
        ) from None
    return first.decode("utf-8", "replace").lstrip("\ufeff \t\r\n")[:4].casefold() == "url:"


def _every_fingerprint_file_listed(path: Path, sources: list[KeySource]) -> None:
    """A key source has a fingerprint file in the topic's folder (the folder
    holding the note), so a key source written anywhere but under
    `## Key sources`, in any form, leaves its file unnamed there: refused,
    naming the file. The note's prose is never read for key sources."""
    listed = {s.fingerprints for s in sources}  # already resolved by `_inside`
    for folder, folders, files in os.walk(path.parent):
        folders.sort()
        for name in sorted(files):
            f = Path(folder) / name
            if f.resolve() not in listed and _is_fingerprint_file(f, path):
                raise LayoutError(
                    f"{path}: {f} is a fingerprint file in the topic's folder, but no key-source line under `## Key sources` names it, "
                    f"so its source wouldn't be read (a file whose first line is a `url:` line is one, whatever its name): "
                    f"give it its key-source line there (its name ending with `{FINGERPRINTS}`), or delete the file"
                )


def read_note(path: Path) -> tuple[Header, list[KeySource]]:
    """The note's header and its key sources, each with its fingerprints and
    saved copy read and checked against the layout: each saved paragraph
    with nothing left out has its fingerprint's hash. Raises LayoutError."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise LayoutError(f"{path}: can't be read ({getattr(e, 'strerror', None) or e})") from None
    try:
        header = read_header(text)
    except LayoutError as e:
        raise LayoutError(f"{path}: {e}") from None
    lines = [l.rstrip() for l in _lines(text)]
    start, end = _key_sources_section(lines, path)
    sources: list[KeySource] = []
    none = False
    for n, line in enumerate(lines[start + 1 : end], start + 2):
        if not line.strip():
            continue
        if line == "- None":
            none = True
            continue
        if _heading_level(line):
            raise LayoutError(f"{path}: `## Key sources` holds key-source lines only, but line {n} is a heading inside it: {line[:200]}")
        m = _KEY_SOURCE.fullmatch(line)
        if not m:
            raise LayoutError(
                f"{path}: line {n}, under `## Key sources`, is neither a key-source line, `- <link>, saved as `<path>`, fingerprints in `<path>``, nor `- None`: {line[:200]}"
            )
        if not m["fps"].endswith(FINGERPRINTS):
            raise LayoutError(f"{path}: line {n} names its fingerprints `{m['fps']}`, but a fingerprint file's name ends with `{FINGERPRINTS}`: {line[:200]}")
        sources.append(KeySource(m["url"], _inside(path.parent, m["saved"], "saved copy", m["url"]), _inside(path.parent, m["fps"], "fingerprints", m["url"])))
    if none and sources:
        raise LayoutError(f"{path}: `## Key sources` says `- None` and lists sources")
    if not none and not sources:
        raise LayoutError(f"{path}: `## Key sources` lists nothing (write `- None` under it when there are none)")
    _every_fingerprint_file_listed(path, sources)
    for s in sources:
        for f in (s.saved, s.fingerprints):
            if not f.is_file():
                raise LayoutError(f"{s.url}: {f} doesn't exist")
        try:
            fp_url, s.hashes = read_fingerprints(s.fingerprints.read_text(encoding="utf-8"), str(s.fingerprints))
            saved_url, s.saved_paragraphs = read_saved_copy(s.saved.read_text(encoding="utf-8"), str(s.saved))
        except (OSError, UnicodeDecodeError) as e:
            raise LayoutError(f"{s.url}: its files can't be read ({e})") from None
        if fp_url != s.url or saved_url != s.url:
            raise LayoutError(f"{s.url}: the note's link, the saved copy's `Source:` ({saved_url}) and the fingerprints' `url:` ({fp_url}) don't agree")
        if len(s.saved_paragraphs) != len(s.hashes):
            raise LayoutError(
                f"{s.url}: the saved copy has {len(s.saved_paragraphs)} paragraphs and its fingerprints {len(s.hashes)}, so positions don't match "
                f"(a paragraph left out whole stays as one `{LEFT_OUT}` line)"
            )
        for i, (text, h) in enumerate(zip(s.saved_paragraphs, s.hashes), 1):
            if LEFT_OUT not in text and digest(text) != h:
                raise LayoutError(
                    f"{s.url}: the saved copy's paragraph {i} doesn't match its fingerprint, so it isn't the text the hash comes from "
                    f"(write both files from one `workflow research fingerprint` output; only `{LEFT_OUT}` may change a paragraph)"
                )
    return header, sources


# ---------- the source check ----------


def compare(source: KeySource, live: list[str], patterns: list[str]) -> dict:
    """The key source against the live page's paragraphs, as sets of hashes:
    each new paragraph's live text (sensitive patterns left out), position and
    hash; each paragraph gone, by its position in the saved copy, with the saved
    copy's text there and its hash."""
    saved = set(source.hashes)
    live_hashes = [digest(t) for t in live]
    now = set(live_hashes)
    new = [{"position": i, "hash": h, "text": leave_out(t, patterns)[0]} for i, (t, h) in enumerate(zip(live, live_hashes), 1) if h not in saved]
    gone = [
        {"position": i, "hash": h, "saved_text": leave_out(source.saved_paragraphs[i - 1], patterns)[0]}
        for i, h in enumerate(source.hashes, 1)
        if h not in now
    ]
    return {"result": "changed" if new or gone else "unchanged", "new": new, "gone": gone}


# ---------- current notes ----------


def notes(root: Path) -> tuple[list[dict], list[dict]]:
    """(the notes marked `current`, the rest with why): every `<topic>/note.md`
    under `root`. `broken` marks a note whose header can't be read."""
    current: list[dict] = []
    not_listed: list[dict] = []
    if not root.is_dir():
        return current, not_listed
    for path in sorted(root.glob(f"*/{NOTE_FILE}")):
        try:
            h = read_header(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as e:
            not_listed.append({"path": path, "why": f"it can't be read ({getattr(e, 'strerror', None) or e})", "broken": True})
            continue
        except LayoutError as e:
            not_listed.append({"path": path, "why": str(e), "broken": True})
            continue
        if h.status == "current":
            current.append({"path": path, "last_checked": h.last_checked, "issue": h.issue, "title": h.title})
        else:
            not_listed.append({"path": path, "why": f"Status: {h.status}", "broken": False})
    return current, not_listed
