"""`workflow research`: research notes in `docs/research/<topic>/` (spec #505).

The folder's one fixed layout is in the `study` skill's text, which the tests'
fixtures are copied from:

- `note.md`, the note: three header lines (`Status:`, `Last checked:`,
  `Issue:`), then a blank line; its key sources one line each under
  `## Key sources`, its last section, once: `- <link>, saved as `path`,
  fingerprints in `path``;
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
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

LEFT_OUT = "[left out]"
NOTE_FILE = "note.md"
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


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self._now: list[str] = []
        self._skip: list[str] = []

    def _end_paragraph(self):
        text = _flat("".join(self._now))
        if text:
            self.paragraphs.append(text)
        self._now = []

    def handle_starttag(self, tag, attrs):
        if tag == "body" and self._skip[:1] == ["head"]:
            self._skip = []  # `</head>` may be left out: the head ends at `<body>`. With neither, there is no text
        if self._skip:
            if tag == self._skip[-1] and tag not in _VOID:
                self._skip.append(tag)
            return
        if tag in _SKIP:
            if tag not in _VOID:
                self._skip.append(tag)
            return
        if tag in _BLOCK:
            self._end_paragraph()
        elif tag in _SPACE:
            self._now.append(" ")

    def handle_startendtag(self, tag, attrs):  # <x/>: opens nothing
        if self._skip or tag in _SKIP:
            return
        if tag in _BLOCK:
            self._end_paragraph()
        elif tag in _SPACE:
            self._now.append(" ")

    def handle_endtag(self, tag):
        if self._skip:
            if tag == self._skip[-1]:
                self._skip.pop()
            return
        if tag in _BLOCK:
            self._end_paragraph()
        elif tag in _SPACE:
            self._now.append(" ")

    def handle_data(self, data):
        if not self._skip:
            self._now.append(data)

    def close(self):
        super().close()
        self._end_paragraph()


def _kind(content_type: str) -> str:
    """"html" or "text" by the content type. Raises PageError for anything
    else (a PDF, an image), and for no content type at all."""
    ctype = content_type.split(";", 1)[0].strip().lower()
    if ctype in ("text/html", "application/xhtml+xml"):
        return "html"
    if ctype.startswith("text/"):
        return "text"
    if not ctype:
        raise PageError("it names no content type, so it can't be told from a PDF or an image")
    raise PageError(f"it isn't a text page ({ctype})")


# The text encodings a web page can use (the WHATWG Encoding Standard's, and
# latin-1, ascii and utf-16 as pages name them), by Python's codec names.
# Anything else, a codec such as punycode or unicode_escape among them, is read as UTF-8.
_WEB_CHARSETS = {
    "utf-8", "utf-16", "utf-16-be", "utf-16-le", "ascii", "cp866", "koi8-r", "koi8-u", "mac-roman", "mac-cyrillic",
    "cp874", "cp1250", "cp1251", "cp1252", "cp1253", "cp1254", "cp1255", "cp1256", "cp1257", "cp1258",
    "gbk", "gb2312", "gb18030", "big5", "euc_jp", "iso2022_jp", "shift_jis", "euc_kr",
    *(f"iso8859-{n}" for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16)),
}


def _charset(content_type: str, raw: bytes, kind: str) -> str:
    m = re.search(r"charset=[\"']?([A-Za-z0-9_.:-]+)", content_type, re.I)
    if not m and kind == "html":
        m = re.search(rb"<meta[^>]+charset=[\"']?([A-Za-z0-9_.:-]+)", raw[:4096], re.I)
        name = m.group(1).decode("ascii") if m else "utf-8"
    else:
        name = m.group(1) if m else "utf-8"
    try:
        codec = codecs.lookup(name).name
    except (LookupError, UnicodeError, ValueError):
        return "utf-8"
    return codec if codec in _WEB_CHARSETS else "utf-8"


def paragraphs(raw: bytes, content_type: str) -> list[str]:
    """The page's text, as paragraphs: HTML by its block elements (scripts,
    styles, the head and navigation left out), plain text by its blank lines.
    Whitespace inside a paragraph is one space; empty paragraphs are dropped.
    A charset it can't decode with, or one that isn't a web page's text
    encoding, is read as UTF-8; HTML it can't parse, or
    a page with no content type, raises PageError."""
    kind = _kind(content_type)
    try:
        text = raw.decode(_charset(content_type, raw, kind), errors="replace")
    except (LookupError, UnicodeError, ValueError):
        text = raw.decode("utf-8", errors="replace")
    text = text.lstrip("﻿")
    if kind == "html":
        p = _Text()
        try:
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


_ASCII = "".join(map(chr, range(128)))


def _ascii_link(url: str) -> str:
    """The link as the request sends it: letters outside ASCII in its path,
    query and fragment percent-encoded as UTF-8, its host IDNA-encoded. An
    ASCII link, existing escapes included, is sent as written."""
    if url.isascii():
        return url
    parts = urllib.parse.urlsplit(url)
    netloc = parts.netloc
    if not netloc.isascii():
        user, at, hostport = netloc.rpartition("@")
        host, colon, port = hostport.partition(":")
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            raise PageError("its host name can't be written in ASCII (IDNA)") from None
        netloc = urllib.parse.quote(user, safe=_ASCII) + at + host + colon + port
    path, query, fragment = (urllib.parse.quote(x, safe=_ASCII) for x in (parts.path, parts.query, parts.fragment))
    return urllib.parse.urlunsplit((parts.scheme, netloc, path, query, fragment))


def fetch(url: str, timeout: float = FETCH_TIMEOUT, limit: int = FETCH_LIMIT) -> tuple[bytes, str]:
    """The page at a web link: its bytes and content type. Only http and https,
    redirects included; raises PageError with the reason it can't."""
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
    req = urllib.request.Request(_ascii_link(url), headers={"User-Agent": USER_AGENT, "Accept": "text/html, text/plain;q=0.9, */*;q=0.1"})
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
    try:
        start = lines.index("## Key sources")
    except ValueError:
        raise LayoutError(f"{path}: it has no `## Key sources` section (write `- None` under it when there are none)") from None
    sources: list[KeySource] = []
    none = False
    for n, line in enumerate(lines[start + 1:], start + 2):
        if line.startswith("#"):
            raise LayoutError(f"{path}: `## Key sources` must be the note's last section, once, but line {n} is a heading after it: {line[:200]}")
        if not line.strip():
            continue
        if line == "- None":
            none = True
            continue
        m = _KEY_SOURCE.fullmatch(line)
        if not m:
            raise LayoutError(
                f"{path}: a line under `## Key sources` is neither a key-source line, `- <link>, saved as `<path>`, fingerprints in `<path>``, nor `- None`: {line[:200]}"
            )
        sources.append(KeySource(m["url"], _inside(path.parent, m["saved"], "saved copy", m["url"]), _inside(path.parent, m["fps"], "fingerprints", m["url"])))
    if none and sources:
        raise LayoutError(f"{path}: `## Key sources` says `- None` and lists sources")
    if not none and not sources:
        raise LayoutError(f"{path}: `## Key sources` lists nothing (write `- None` under it when there are none)")
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
