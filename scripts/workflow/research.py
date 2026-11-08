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
  unread; so is a file or folder there that can't be read.
  The rest of the note is prose, never read for key sources;
- a saved copy: `Source:`, `Accessed:` and `Third-party text:` lines, a blank
  line, then the page's paragraphs, one per position, separated by blank lines
  (a paragraph left out whole is one `[left out]` line in its place);
- a fingerprint file: `url: <link>`, then `<position> <sha256>` per paragraph
  of the page as fetched, before anything is left out. Hashes only, no text.

`fingerprint` reads a page (a file, or with `--fetch` the web), splits its text
into paragraphs and hashes each, and with `--saved` and `--fingerprints` writes
the saved copy and the fingerprint file from that one read, both or neither
(`write_files`); `check` compares a note's key sources against their
fingerprints as a set; `notes` lists the notes marked `current`. None of it
calls a model, and nothing else is written.
"""

from __future__ import annotations

import codecs
import functools
import hashlib
import http.client
import os
import re
import secrets
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
THIRD_PARTY = "Third-party text: someone else's words, quoted to check this note's claims. Not covered by this repository's licence."
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


class WriteError(Exception):
    """A file `write_files` can't write: `path` as given, and why. `kept`
    lists each (path, its old file) that couldn't be put back: the old file
    is kept aside under that name, never removed; its old file is None for a
    new file that couldn't be removed, which is left written."""

    def __init__(self, path, why: str, kept: list | None = None):
        super().__init__(f"{path} ({why})")
        self.path = path
        self.why = why
        self.kept = kept or []


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


def _media_type(content_type: str) -> str:
    return content_type.split(";", 1)[0].strip().lower()


def _kind(content_type: str, raw: bytes) -> str:
    """"html" or "text" by the content type; with none named, by the bytes,
    only where they are clearly an HTML or plain-text page (`_untyped_kind`).
    Raises PageError for anything else (a PDF, an image)."""
    ctype = _media_type(content_type)
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
_UNTYPED = "it names no content type, and its bytes aren't clearly a text page"
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
    why = _UNTYPED
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


# ---------- a page's charset: the WHATWG Encoding Standard ----------

# The Encoding Standard's encodings and their labels (https://encoding.spec.whatwg.org/,
# its encodings.json), as it lists them. A label it doesn't list is refused, and a
# page is decoded only in one of these: tests/test_research_charsets.py ties this
# table to the standard's own file, and each single-byte table to its index.
_STANDARD = {
    "UTF-8": "unicode-1-1-utf-8 unicode11utf8 unicode20utf8 utf-8 utf8 x-unicode20utf8",
    "IBM866": "866 cp866 csibm866 ibm866",
    "ISO-8859-2": "csisolatin2 iso-8859-2 iso-ir-101 iso8859-2 iso88592 iso_8859-2 iso_8859-2:1987 l2 latin2",
    "ISO-8859-3": "csisolatin3 iso-8859-3 iso-ir-109 iso8859-3 iso88593 iso_8859-3 iso_8859-3:1988 l3 latin3",
    "ISO-8859-4": "csisolatin4 iso-8859-4 iso-ir-110 iso8859-4 iso88594 iso_8859-4 iso_8859-4:1988 l4 latin4",
    "ISO-8859-5": "csisolatincyrillic cyrillic iso-8859-5 iso-ir-144 iso8859-5 iso88595 iso_8859-5 iso_8859-5:1988",
    "ISO-8859-6": "arabic asmo-708 csiso88596e csiso88596i csisolatinarabic ecma-114 iso-8859-6 iso-8859-6-e iso-8859-6-i"
    " iso-ir-127 iso8859-6 iso88596 iso_8859-6 iso_8859-6:1987",
    "ISO-8859-7": "csisolatingreek ecma-118 elot_928 greek greek8 iso-8859-7 iso-ir-126 iso8859-7 iso88597 iso_8859-7"
    " iso_8859-7:1987 sun_eu_greek",
    "ISO-8859-8": "csiso88598e csisolatinhebrew hebrew iso-8859-8 iso-8859-8-e iso-ir-138 iso8859-8 iso88598 iso_8859-8"
    " iso_8859-8:1988 visual",
    "ISO-8859-8-I": "csiso88598i iso-8859-8-i logical",
    "ISO-8859-10": "csisolatin6 iso-8859-10 iso-ir-157 iso8859-10 iso885910 l6 latin6",
    "ISO-8859-13": "iso-8859-13 iso8859-13 iso885913",
    "ISO-8859-14": "iso-8859-14 iso8859-14 iso885914",
    "ISO-8859-15": "csisolatin9 iso-8859-15 iso8859-15 iso885915 iso_8859-15 l9",
    "ISO-8859-16": "iso-8859-16",
    "KOI8-R": "cskoi8r koi koi8 koi8-r koi8_r",
    "KOI8-U": "koi8-ru koi8-u",
    "macintosh": "csmacintosh mac macintosh x-mac-roman",
    "windows-874": "dos-874 iso-8859-11 iso8859-11 iso885911 tis-620 windows-874",
    "windows-1250": "cp1250 windows-1250 x-cp1250",
    "windows-1251": "cp1251 windows-1251 x-cp1251",
    "windows-1252": "ansi_x3.4-1968 ascii cp1252 cp819 csisolatin1 ibm819 iso-8859-1 iso-ir-100 iso8859-1 iso88591"
    " iso_8859-1 iso_8859-1:1987 l1 latin1 us-ascii windows-1252 x-cp1252",
    "windows-1253": "cp1253 windows-1253 x-cp1253",
    "windows-1254": "cp1254 csisolatin5 iso-8859-9 iso-ir-148 iso8859-9 iso88599 iso_8859-9 iso_8859-9:1989 l5 latin5"
    " windows-1254 x-cp1254",
    "windows-1255": "cp1255 windows-1255 x-cp1255",
    "windows-1256": "cp1256 windows-1256 x-cp1256",
    "windows-1257": "cp1257 windows-1257 x-cp1257",
    "windows-1258": "cp1258 windows-1258 x-cp1258",
    "x-mac-cyrillic": "x-mac-cyrillic x-mac-ukrainian",
    "GBK": "chinese csgb2312 csiso58gb231280 gb2312 gb_2312 gb_2312-80 gbk iso-ir-58 x-gbk",
    "gb18030": "gb18030",
    "Big5": "big5 big5-hkscs cn-big5 csbig5 x-x-big5",
    "EUC-JP": "cseucpkdfmtjapanese euc-jp x-euc-jp",
    "ISO-2022-JP": "csiso2022jp iso-2022-jp",
    "Shift_JIS": "csshiftjis ms932 ms_kanji shift-jis shift_jis sjis windows-31j x-sjis",
    "EUC-KR": "cseuckr csksc56011987 euc-kr iso-ir-149 korean ks_c_5601-1987 ks_c_5601-1989 ksc5601 ksc_5601 windows-949",
    "replacement": "csiso2022kr hz-gb-2312 iso-2022-cn iso-2022-cn-ext iso-2022-kr replacement",
    "UTF-16BE": "unicodefffe utf-16be",
    "UTF-16LE": "csunicode iso-10646-ucs-2 ucs-2 unicode unicodefeff utf-16 utf-16le",
    "x-user-defined": "x-user-defined",
}
ENCODING_LABELS = {label: name for name, labels in _STANDARD.items() for label in labels.split()}

# The standard's multi-byte encodings a Python codec decodes as the standard does,
# each with that codec: Shift_JIS is Windows' (cp932) and EUC-KR is Windows' (cp949),
# as the standard's indexes are. The others are decoded by the standard's own
# decoders (`MULTI_BYTE_DECODERS`). No other codec decodes a page.
MULTI_BYTE_CODECS = {
    "UTF-8": "utf-8",
    "Shift_JIS": "cp932",
    "EUC-KR": "cp949",
    "UTF-16BE": "utf-16-be",
    "UTF-16LE": "utf-16-le",
}
# cp932 reads the bytes 0xA0 and 0xFD to 0xFF alone as U+F8F0 to U+F8F3, and nothing
# else as these; the standard's Shift_JIS decoder refuses those bytes, so they are refused.
_SHIFT_JIS_UNDEFINED = re.compile("[\uf8f0-\uf8f3]")

# The standard's single-byte encodings, each decoded by a table of its index: the
# Python codec named gives each byte's character, a byte 0x80 to 0x9F it leaves
# undefined is that code point (the standard's C1 controls), and _INDEX_FIXES are
# where the codec and the index differ. A byte the index leaves undefined is refused.
_SINGLE_BYTE = {
    "IBM866": "cp866",
    **{f"ISO-8859-{n}": f"iso8859_{n}" for n in (2, 3, 4, 5, 6, 7, 8, 10, 13, 14, 15, 16)},
    "ISO-8859-8-I": "iso8859_8",
    "KOI8-R": "koi8_r",
    "KOI8-U": "koi8_u",
    "macintosh": "mac_roman",
    "windows-874": "cp874",
    **{f"windows-{n}": f"cp{n}" for n in range(1250, 1259)},
    "x-mac-cyrillic": "mac_cyrillic",
}
_INDEX_FIXES = {"KOI8-U": {0xAE: 0x045E, 0xBE: 0x040E}, "windows-1255": {0xCA: 0x05BA}}
_UNDEFINED = "\ufffe"  # what codecs.charmap_decode reads as a byte with no character
_BOMS = ((b"\xef\xbb\xbf", "UTF-8"), (b"\xfe\xff", "UTF-16BE"), (b"\xff\xfe", "UTF-16LE"))
_HEADER_CHARSET = re.compile(r";[ \t]*charset=[\"']?([A-Za-z0-9_.:-]+)", re.I | re.A)  # a parameter's, not `x-charset=`'s
_PRESCAN = 4096  # an HTML page's first bytes, searched for its <meta> charset
_ASCII_SPACE = b"\t\n\x0c\r "
_SHOWN_LABEL = 40  # characters of a label a refusal shows


def encoding_named(label: str) -> str | None:
    """The standard's encoding for a label, as its "get an encoding" says: ASCII
    white space around it ignored, ASCII letters in either case; None for a
    label it doesn't list, a label outside ASCII among them."""
    label = label.strip("\t\n\f\r ")
    return ENCODING_LABELS.get(label.lower()) if label.isascii() else None


@functools.lru_cache(maxsize=None)
def _table(name: str) -> str:
    """A single-byte encoding's 256 characters, as `codecs.charmap_decode` takes them."""
    if name == "x-user-defined":
        return "".join(chr(b) for b in range(0x80)) + "".join(chr(0xF780 + b) for b in range(0x80))
    codec, fixes = _SINGLE_BYTE[name], _INDEX_FIXES.get(name, {})
    chars = []
    for b in range(0x100):
        try:
            c = chr(fixes[b]) if b in fixes else bytes([b]).decode(codec)
        except UnicodeDecodeError:
            c = chr(b) if 0x80 <= b <= 0x9F else _UNDEFINED
        chars.append(c)
    return "".join(chars)


def decode(raw: bytes, name: str) -> str:
    """Bytes as text in the standard's encoding `name`, strictly: bytes the
    encoding doesn't define raise PageError, never become U+FFFD, so two
    different texts never read as one."""
    try:
        if name in MULTI_BYTE_DECODERS:
            text = MULTI_BYTE_DECODERS[name](raw)
            if text is None:
                raise UnicodeDecodeError(name, raw, 0, len(raw), "undefined")
            return text
        if name in MULTI_BYTE_CODECS:
            text = raw.decode(MULTI_BYTE_CODECS[name], errors="strict")
            if name == "Shift_JIS" and _SHIFT_JIS_UNDEFINED.search(text):
                raise UnicodeDecodeError(name, raw, 0, len(raw), "undefined")
            return text
        return codecs.charmap_decode(raw, "strict", _table(name))[0]
    except UnicodeDecodeError:
        raise PageError(f"its bytes aren't valid {name}") from None


# ---------- the standard's own multi-byte decoders ----------

# The standard's multi-byte indexes, pointer to character, each built from one Python
# codec (`INDEX_CODECS`): each pointer's bytes as that codec reads them, then the
# fixes where it and the standard's index differ. tests/test_research_charsets.py
# ties each built index to the standard's own file.
# Index jis0208 is read through Shift_JIS's bytes, and index jis0212 through EUC-JP's.
INDEX_CODECS = {"gb18030": "gb18030", "big5": "big5hkscs", "jis0208": "cp932", "jis0212": "euc_jp"}
_GB18030_FIXES = {  # GB18030-2022's changes, and 0xA3 0xA0 as U+3000, as the standard's index has them
    6555: 0x3000, 7182: 0xFE10, 7183: 0xFE12, 7184: 0xFE11, 7185: 0xFE13, 7186: 0xFE14, 7187: 0xFE15,
    7188: 0xFE16, 7201: 0xFE17, 7202: 0xFE18, 7208: 0xFE19, 7533: 0x1E3F, 23775: 0x9FB4, 23783: 0x9FB5,
    23788: 0x9FB6, 23789: 0x9FB7, 23795: 0x9FB8, 23812: 0x9FB9, 23829: 0x9FBA, 23845: 0x9FBB,
}
_BIG5_FIXES = {  # HKSCS-2008's characters, and the codes the standard's index maps differently
    1000: 0x3875, 1001: 0x21D53, 1002: 0x2369E, 1003: 0x26021, 1004: 0x3EEC, 1005: 0x258DE, 1006: 0x3AF5,
    1007: 0x7AFC, 1008: 0x9F97, 1009: 0x24161, 1010: 0x2890D, 1011: 0x231EA, 1012: 0x20A8A, 1013: 0x2325E,
    1014: 0x430A, 1015: 0x8484, 1016: 0x9F96, 1017: 0x942F, 1018: 0x4930, 1019: 0x8613, 1020: 0x5896,
    1021: 0x974A, 1022: 0x9218, 1023: 0x79D0, 1024: 0x7A32, 1025: 0x6660, 1026: 0x6A29, 1027: 0x889D,
    1028: 0x744C, 1029: 0x7BC5, 1030: 0x6782, 1031: 0x7A2C, 1032: 0x524F, 1033: 0x9046, 1034: 0x34E6,
    1035: 0x73C4, 1036: 0x25DB9, 1037: 0x74C6, 1038: 0x9FC7, 1039: 0x57B3, 1040: 0x492F, 1041: 0x544C,
    1042: 0x4131, 1043: 0x2368E, 1044: 0x5818, 1045: 0x7A72, 1046: 0x27B65, 1047: 0x8B8F, 1048: 0x46AE,
    1049: 0x26E88, 1050: 0x4181, 1051: 0x25D99, 1052: 0x7BAE, 1053: 0x224BC, 1054: 0x9FC8, 1055: 0x224C1,
    1056: 0x224C9, 1057: 0x224CC, 1058: 0x9FC9, 1059: 0x8504, 1060: 0x235BB, 1061: 0x40B4, 1062: 0x9FCA,
    1063: 0x44E1, 1064: 0x2ADFF, 1065: 0x62C1, 1066: 0x706E, 1067: 0x9FCB, 2082: 0x7BB8, 2088: 0x7C06,
    2103: 0x7CCE, 2114: 0x7DD2, 2123: 0x7E1D, 2148: 0x8005, 2151: 0x8028, 2221: 0x83C1, 2239: 0x84A8,
    2244: 0x840F, 2303: 0x89A6, 2304: 0x89A9, 2354: 0x8D77, 2400: 0x90FD, 2413: 0x92B9, 2477: 0x975C,
    2498: 0x97FF, 2605: 0x9F16, 2673: 0x8503, 2746: 0x5159, 2747: 0x515B, 2748: 0x515D, 2749: 0x515E,
    2771: 0x936E, 2780: 0x7479, 2990: 0x6D67, 3087: 0x799B, 3259: 0x9097, 3301: 0x975D, 3436: 0x701E,
    3451: 0x5B28, 4136: 0x7201, 4138: 0x77D7, 4141: 0x7E87, 4182: 0x99D6, 4206: 0x91D4, 4220: 0x60DE,
    4230: 0x6FB6, 4241: 0x8F36, 4258: 0x4FBB, 4273: 0x71DF, 4279: 0x9104, 4282: 0x9DF0, 4294: 0x83CF,
    4329: 0x5C10, 4330: 0x79E3, 4349: 0x5A67, 4419: 0x8F0B, 4422: 0x7B51, 4494: 0x62D0, 4624: 0x6062,
    4694: 0x75F9, 4708: 0x6C4A, 4742: 0x9B2E, 4748: 0x9F17, 4815: 0x50ED, 4828: 0x5F0C, 4902: 0x880F,
    4922: 0x62CE, 4982: 0x7468, 4992: 0x7162, 4997: 0x7250, 5029: 0x2027, 5038: 0xFE51, 5120: 0x00AF,
    5153: 0xFF5E, 5168: 0x2295, 5169: 0x2299, 5182: 0x2215, 5183: 0xFE68, 5185: 0xFFE5, 5187: 0xFFE0,
    5188: 0xFFE1, 5432: 0x2400, 5433: 0x2401, 5434: 0x2402, 5435: 0x2403, 5436: 0x2404, 5437: 0x2405,
    5438: 0x2406, 5439: 0x2407, 5440: 0x2408, 5441: 0x2409, 5442: 0x240A, 5443: 0x240B, 5444: 0x240C,
    5445: 0x240D, 5446: 0x240E, 5447: 0x240F, 5448: 0x2410, 5449: 0x2411, 5450: 0x2412, 5451: 0x2413,
    5452: 0x2414, 5453: 0x2415, 5454: 0x2416, 5455: 0x2417, 5456: 0x2418, 5457: 0x2419, 5458: 0x241A,
    5459: 0x241B, 5460: 0x241C, 5461: 0x241D, 5462: 0x241E, 5463: 0x241F, 5464: 0x2421, 5465: 0x20AC,
    10942: 0x5EF4, 10946: 0x65E0, 10948: 0x7676, 10950: 0x96B6, 10957: 0x3003, 10958: 0x4EDD, 19028: 0x5029,
    19035: 0x507D, 19088: 0x5305, 19096: 0x5344, 19112: 0x537F, 19162: 0x5605, 19240: 0x5A77, 19299: 0x5E75,
    19305: 0x5ED0, 19326: 0x5F58, 19355: 0x60A4, 19398: 0x6490, 19439: 0x6674, 19454: 0x675E, 19553: 0x6C9C,
    19554: 0x6E1D, 19557: 0x6E2F, 19611: 0x716E, 19643: 0x732A, 19672: 0x745C, 19697: 0x74E9, 19748: 0x7809,
}
_JIS0212_FIXES = {116: 0xFF5E}
# Big5's pointers whose character is two code points, as the standard's decoder gives them
_BIG5_TWO = {1133: "\u00ca\u0304", 1135: "\u00ca\u030c", 1164: "\u00ea\u0304", 1166: "\u00ea\u030c"}
_NOT_ASCII = re.compile(rb"[\x80-\xff]")


def _gb18030_pointers():
    for lead in range(0x81, 0xFF):
        for byte in (*range(0x40, 0x7F), *range(0x80, 0xFF)):
            yield (lead - 0x81) * 190 + byte - (0x40 if byte < 0x7F else 0x41), bytes((lead, byte))


def _big5_pointers():
    for lead in range(0x81, 0xFF):
        for byte in (*range(0x40, 0x7F), *range(0xA1, 0xFF)):
            yield (lead - 0x81) * 157 + byte - (0x40 if byte < 0x7F else 0x62), bytes((lead, byte))


def _jis0208_pointers():
    for lead in (*range(0x81, 0xA0), *range(0xE0, 0xFD)):
        for byte in (*range(0x40, 0x7F), *range(0x80, 0xFD)):
            pointer = (lead - (0x81 if lead < 0xA0 else 0xC1)) * 188 + byte - (0x40 if byte < 0x7F else 0x41)
            if not 8836 <= pointer <= 10715:  # Shift_JIS's private use area, not in the index
                yield pointer, bytes((lead, byte))


def _jis0212_pointers():
    for lead in range(0xA1, 0xFF):
        for byte in range(0xA1, 0xFF):
            yield (lead - 0xA1) * 94 + byte - 0xA1, bytes((0x8F, lead, byte))


_INDEXES = {
    "gb18030": (_gb18030_pointers, _GB18030_FIXES),
    "big5": (_big5_pointers, _BIG5_FIXES),
    "jis0208": (_jis0208_pointers, {}),
    "jis0212": (_jis0212_pointers, _JIS0212_FIXES),
}


@functools.lru_cache(maxsize=None)
def multi_byte_index(name: str) -> dict[int, str]:
    """The standard's index `name`, pointer to character: each pointer's bytes
    as `INDEX_CODECS[name]` reads them as one character, then the fixes."""
    pointers, fixes = _INDEXES[name]
    index = {}
    for pointer, raw in pointers():
        try:
            c = raw.decode(INDEX_CODECS[name])
        except UnicodeDecodeError:
            continue
        if len(c) == 1:
            index[pointer] = c
    index.update((pointer, chr(cp)) for pointer, cp in fixes.items())
    return index


def _stateless(raw: bytes, char) -> str | None:
    """Bytes in one of the standard's stateless multi-byte encodings: ASCII bytes
    as themselves, each other character as `char(raw, i)` reads it (it and the
    position after it); None for bytes the encoding doesn't define."""
    out, i, n = [], 0, len(raw)
    while i < n:
        if raw[i] < 0x80:
            m = _NOT_ASCII.search(raw, i)
            j = m.start() if m else n
            out.append(raw[i:j].decode("ascii"))
            i = j
            continue
        got = char(raw, i)
        if got is None:
            return None
        out.append(got[0])
        i = got[1]
    return "".join(out)


def _gb18030_char(raw: bytes, i: int) -> tuple[str, int] | None:
    """The standard's gb18030 decoder, at a byte that isn't ASCII."""
    b = raw[i]
    if b == 0x80:
        return "\u20ac", i + 1
    if b == 0xFF or i + 1 >= len(raw):
        return None
    byte = raw[i + 1]
    if 0x30 <= byte <= 0x39:  # four bytes
        if i + 3 >= len(raw) or not 0x81 <= raw[i + 2] <= 0xFE or not 0x30 <= raw[i + 3] <= 0x39:
            return None
        pointer = (b - 0x81) * 12600 + (byte - 0x30) * 1260 + (raw[i + 2] - 0x81) * 10 + raw[i + 3] - 0x30
        if 39419 < pointer < 189000 or pointer > 1237575:
            return None
        if pointer == 7457:
            return "\ue7c7", i + 4
        try:  # the gb18030 codec reads the rest as the standard's index gb18030 ranges does
            return raw[i : i + 4].decode("gb18030"), i + 4
        except UnicodeDecodeError:
            return None
    if not (0x40 <= byte <= 0x7E or 0x80 <= byte <= 0xFE):
        return None
    c = multi_byte_index("gb18030").get((b - 0x81) * 190 + byte - (0x40 if byte < 0x7F else 0x41))
    return None if c is None else (c, i + 2)


def _gb18030(raw: bytes) -> str | None:
    return _stateless(raw, _gb18030_char)


def _big5_char(raw: bytes, i: int) -> tuple[str, int] | None:
    """The standard's Big5 decoder, at a byte that isn't ASCII."""
    b = raw[i]
    if not 0x81 <= b <= 0xFE or i + 1 >= len(raw):
        return None
    byte = raw[i + 1]
    if not (0x40 <= byte <= 0x7E or 0xA1 <= byte <= 0xFE):
        return None
    pointer = (b - 0x81) * 157 + byte - (0x40 if byte < 0x7F else 0x62)
    c = _BIG5_TWO.get(pointer) or multi_byte_index("big5").get(pointer)
    return None if c is None else (c, i + 2)


def _big5(raw: bytes) -> str | None:
    return _stateless(raw, _big5_char)


def _euc_jp_char(raw: bytes, i: int) -> tuple[str, int] | None:
    """The standard's EUC-JP decoder, at a byte that isn't ASCII."""
    b = raw[i]
    if i + 1 >= len(raw):
        return None
    byte = raw[i + 1]
    if b == 0x8E:  # halfwidth katakana
        return (chr(0xFF61 - 0xA1 + byte), i + 2) if 0xA1 <= byte <= 0xDF else None
    index, size = "jis0208", 2
    if b == 0x8F:
        if not 0xA1 <= byte <= 0xFE or i + 2 >= len(raw):
            return None
        b, byte, index, size = byte, raw[i + 2], "jis0212", 3
    if not (0xA1 <= b <= 0xFE and 0xA1 <= byte <= 0xFE):
        return None
    c = multi_byte_index(index).get((b - 0xA1) * 94 + byte - 0xA1)
    return None if c is None else (c, i + size)


def _euc_jp(raw: bytes) -> str | None:
    return _stateless(raw, _euc_jp_char)


_ISO_2022_JP_ESCAPES = {b"(B": "ASCII", b"(J": "Roman", b"(I": "katakana", b"$@": "jis0208", b"$B": "jis0208"}
_ROMAN = {0x5C: "\u00a5", 0x7E: "\u203e"}


def _iso_2022_jp(raw: bytes) -> str | None:
    """The standard's ISO-2022-JP decoder: its escapes switch between ASCII, Roman,
    halfwidth katakana and index jis0208's two bytes; an escape right after
    another, SO or SI, or a byte the state doesn't define is an error (None)."""
    out, i, n = [], 0, len(raw)
    state, escaped = "ASCII", False
    while i < n:
        b = raw[i]
        if b == 0x1B:
            state = _ISO_2022_JP_ESCAPES.get(raw[i + 1 : i + 3])
            if state is None or escaped:
                return None
            escaped, i = True, i + 3
            continue
        escaped = False
        if state == "jis0208":
            byte = raw[i + 1] if i + 1 < n else 0
            c = multi_byte_index("jis0208").get((b - 0x21) * 94 + byte - 0x21) if 0x21 <= b <= 0x7E and 0x21 <= byte <= 0x7E else None
            if c is None:
                return None
            out.append(c)
            i += 2
            continue
        if state == "katakana":
            if not 0x21 <= b <= 0x5F:
                return None
            out.append(chr(0xFF61 - 0x21 + b))
        elif b > 0x7F or b in (0x0E, 0x0F):
            return None
        else:
            out.append(_ROMAN.get(b, chr(b)) if state == "Roman" else chr(b))
        i += 1
    return "".join(out)


# The standard's multi-byte encodings decoded by its own decoders: GBK's decoder is
# gb18030's, and Big5's index covers HKSCS.
MULTI_BYTE_DECODERS = {
    "GBK": _gb18030,
    "gb18030": _gb18030,
    "Big5": _big5,
    "EUC-JP": _euc_jp,
    "ISO-2022-JP": _iso_2022_jp,
}


def _cut(label: str) -> str:
    return label if len(label) <= _SHOWN_LABEL else label[:_SHOWN_LABEL] + "…"


def _attribute(low: bytes, i: int) -> tuple[bytes | None, bytes, int]:
    """HTML's prescan's "get an attribute", from `low[i]` (`low` being the window
    with ASCII letters lowercased): the attribute's name, None when there is none
    (at a `>`, or at the window's end, where the position is the window's length),
    its value, and the position after it."""
    n = len(low)
    while i < n and low[i] in b"\t\n\x0c\r /":
        i += 1
    if i >= n or low[i] == 0x3E:  # ">"
        return None, b"", i
    start, i = i, i + 1  # a name's first byte may be "="
    while i < n and low[i] not in b"\t\n\x0c\r />=":
        i += 1
    name = low[start:i]
    while i < n and low[i] in _ASCII_SPACE:
        i += 1
    if i >= n:
        return None, b"", n
    if low[i] != 0x3D:  # no "=": no value
        return name, b"", i
    i += 1
    while i < n and low[i] in _ASCII_SPACE:
        i += 1
    if i >= n:
        return None, b"", n
    if low[i] in b"\"'":
        end = low.find(low[i : i + 1], i + 1)
        return (None, b"", n) if end < 0 else (name, low[i + 1 : end], end + 1)
    if low[i] == 0x3E:
        return name, b"", i
    start = i
    while i < n and low[i] not in b"\t\n\x0c\r >":
        i += 1
    return (None, b"", n) if i >= n else (name, low[start:i], i)


def _content_charset(s: bytes) -> bytes | None:
    """The label a `<meta>`'s lowercased `content` names after "charset=", as HTML's
    "extracting a character encoding from a meta element" finds it; None for none."""
    i = 0
    while True:
        i = s.find(b"charset", i)
        if i < 0:
            return None
        i += 7
        while i < len(s) and s[i] in _ASCII_SPACE:
            i += 1
        if i >= len(s) or s[i] != 0x3D:  # "charset" with no "=": look further on
            continue
        i += 1
        while i < len(s) and s[i] in _ASCII_SPACE:
            i += 1
        if i >= len(s):
            return None
        if s[i] in b"\"'":
            end = s.find(s[i : i + 1], i + 1)
            return None if end < 0 else s[i + 1 : end]
        end = i
        while end < len(s) and s[end] not in b"\t\n\x0c\r ;":
            end += 1
        return s[i:end]


def _meta(low: bytes, i: int) -> tuple[bytes | None, int]:
    """A `<meta>`'s attributes from `low[i]`, as HTML's prescan reads them: the label
    its `charset` names, or its `content` names beside `http-equiv="content-type"`,
    None when it names none, and the position after its attributes."""
    seen, pragma, need_pragma, label = set(), False, None, None
    while True:
        name, value, i = _attribute(low, i)
        if name is None:
            break
        if name in seen:
            continue
        seen.add(name)
        if name == b"http-equiv":
            pragma = pragma or value == b"content-type"
        elif name == b"content" and label is None:
            found = _content_charset(value)
            if found is not None:
                label, need_pragma = found, True
        elif name == b"charset":
            label, need_pragma = value, False
    if need_pragma is None or (need_pragma and not pragma):
        return None, i
    return label, i


def _meta_charset(raw: bytes) -> str | None:
    """The label an HTML page's `<meta>` names in its first 4096 bytes, as HTML's
    prescan finds it, with a script's text skipped too: never in a comment, a script
    or another tag's attribute, and from a `content` only beside
    `http-equiv="content-type"`. A `<meta>` whose label the standard doesn't list
    (an empty one among them) is passed over, as the prescan does, and the search
    goes on. The first `<meta>` with a listed label wins; None for none."""
    low = raw[:_PRESCAN].lower()
    n, i = len(low), 0
    while i < n:
        if low.startswith(b"<!--", i):
            i = low.find(b"-->", i + 2)  # its dashes may be the "<!--"'s own
            if i < 0:
                return None
            i += 2
        elif low.startswith(b"<meta", i) and i + 5 < n and low[i + 5] in b"\t\n\x0c\r /":
            label, i = _meta(low, i + 5)
            if label is not None and encoding_named(label := label.decode("ascii", "replace")) is not None:
                return label
        elif low.startswith(b"<", i) and low[i + 1 : i + 2].isalpha() or low.startswith(b"</", i) and low[i + 2 : i + 3].isalpha():
            start = i + 1
            while i < n and low[i] not in b"\t\n\x0c\r >":
                i += 1
            tag = low[start:i]
            name = b""
            while name is not None:
                name, _, i = _attribute(low, i)
            if tag == b"script" and i < n:
                i = low.find(b"</script", i)
                if i < 0:
                    return None
                continue
        elif low.startswith((b"<!", b"</", b"<?"), i):
            i = low.find(b">", i + 1)
            if i < 0:
                return None
        i += 1
    return None


def _encoding(content_type: str, raw: bytes, kind: str) -> tuple[str, int]:
    """The standard's encoding the page is read in, and how many bytes of byte
    order mark to skip: a byte order mark first, as the standard's decode does;
    else the charset the header names; else, for HTML, the one its `<meta>`
    names in its first 4096 bytes, where UTF-16 means UTF-8 and x-user-defined
    windows-1252, as HTML says; else UTF-8. Raises PageError for a header's label
    the standard doesn't list (a `<meta>`'s is passed over: `_meta_charset`), or a
    label it reads as a single replacement character."""
    for bom, name in _BOMS:
        if raw.startswith(bom):
            return name, len(bom)
    m = _HEADER_CHARSET.search(content_type)
    meta = None
    if not m and kind == "html":
        meta = _meta_charset(raw)
    if not m and meta is None:
        return "UTF-8", 0
    label = m.group(1) if m else meta
    name = encoding_named(label)
    if name is None:
        raise PageError(f"it names a charset the Encoding Standard doesn't list ({_cut(label)})")
    if name == "replacement":
        raise PageError(f"it is in {_cut(label)}, which the Encoding Standard reads as one replacement character")
    if meta is not None and name in ("UTF-16BE", "UTF-16LE"):
        return "UTF-8", 0
    if meta is not None and name == "x-user-defined":
        return "windows-1252", 0
    return name, 0


def paragraphs(raw: bytes, content_type: str) -> list[str]:
    """The page's text, as paragraphs: HTML by its block elements (scripts,
    styles, the head and navigation left out), plain text by its blank lines.
    Whitespace inside a paragraph is one space; empty paragraphs are dropped.
    A page is read in the charset it names (`_encoding`), else UTF-8; a page
    with no content type only when it reads the same as in UTF-8. A header's label
    the Encoding Standard doesn't list, bytes the charset doesn't define, HTML it
    can't parse, or a page with no content type whose bytes aren't clearly
    HTML or plain text raises PageError."""
    kind = _kind(content_type, raw)
    name, skip = _encoding(content_type, raw, kind)
    if name != "UTF-8" and not _media_type(content_type):  # #527 read it as UTF-8 (`_untyped_kind`): it must read the same
        try:
            same = decode(raw, name) == raw.decode("utf-8")
        except PageError:
            same = False
        if not same:
            raise PageError(f"{_UNTYPED}: they read differently in {name}, the charset it names, than in UTF-8")
    text = decode(raw[skip:], name)
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
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError as e:  # a bracketed host that isn't an IP address, say (#530)
        raise PageError(f"it isn't a well-formed link ({e})") from None
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


# ---------- writing a key source's two files ----------


def fingerprints_text(url: str, paras: list[str]) -> str:
    """The fingerprint file: `url: <link>`, then `<position> <sha256>` per
    paragraph of the page as fetched."""
    return "".join([f"url: {url}\n"] + [f"{i} {digest(t)}\n" for i, t in enumerate(paras, 1)])


def saved_copy_text(url: str, accessed: str, paras: list[str]) -> str:
    """The saved copy: its three header lines, a blank line, then the
    paragraphs given (sensitive patterns already left out), one per position."""
    return f"Source: {url}\nAccessed: {accessed}\n{THIRD_PARTY}\n\n" + "\n\n".join(paras) + "\n"


def link_problem(url: str) -> str | None:
    """Why a link can't go in a key source's two files, else None: each holds
    it on a line of its own, and a key-source line names it as `<link>`. So
    ASCII only, no whitespace, control character, `<` or `>`, and http or
    https with a host. Checked before anything is read, fetched or written."""
    if not url.isascii():
        return "it holds characters outside ASCII; cite the link percent-encoded"
    if any(c <= " " or c in "<>\x7f" for c in url):
        return "it holds a space, a line break, a control character, `<` or `>`"
    try:
        parts = urllib.parse.urlsplit(url)
        ok = parts.scheme in ("http", "https") and bool(parts.hostname)
    except ValueError:
        ok = False
    return None if ok else "it isn't an http or https link with a host"


def target_problem(saved: str, fps: str) -> tuple[str, str] | None:
    """(the path as given, why) when the two paths can't be written whatever
    the page holds, else None: checked before anything is fetched."""
    for option, given in (("--saved", saved), ("--fingerprints", fps)):
        # a key-source line names each path between backticks, on one line, in UTF-8 text: a surrogate (Cs),
        # as a byte that isn't UTF-8 in the command line gives, can't be written there; named by its option, never echoed
        if any(c == "`" or unicodedata.category(c) in ("Cc", "Cs") for c in given):
            return (
                f"the file given to {option}",
                "its path holds a backtick, a control character (a line break among them) or a byte that isn't UTF-8, which no key-source line can name",
            )
    for given in (saved, fps):
        if os.path.basename(given) in ("", ".", ".."):
            return given, "it names a folder, not a file"
    if not fps.endswith(FINGERPRINTS):
        return fps, f"a fingerprint file's name ends with `{FINGERPRINTS}`"
    if os.path.realpath(saved) == os.path.realpath(fps):
        return fps, "--saved and --fingerprints name the same file"
    if saved.casefold().endswith(FINGERPRINTS):  # `check` would take it for a fingerprint file no key-source line names
        return saved, f"a saved copy's name doesn't end with `{FINGERPRINTS}`, a fingerprint file's"
    return None


def _kind_of(st: os.stat_result) -> str | None:
    """Why an existing path can't be replaced by a file, or None for a file."""
    if stat.S_ISREG(st.st_mode):
        return None
    if stat.S_ISDIR(st.st_mode):
        return "it is a folder"
    if stat.S_ISLNK(st.st_mode):
        return "it is a symbolic link, which the file would be written through or replace"
    return "it isn't a file"


def write_files(files: list[tuple[Path, str]]) -> None:
    """Write each (path, text), both or neither: the folders made, each text
    written to a new file beside its path, and only then each put in place,
    an existing file moved aside first. On any failure, or any exception (an
    interrupt too, raised again once undone), everything is undone:
    each file put back as it was (the same file, renamed back), each new file
    and temporary file removed, and each folder made removed. An old file
    that can't be put back is kept aside, never removed, and named in the
    error's `kept`, as is a new file that can't be removed. Raises WriteError
    naming the path that failed."""
    made: list[Path] = []  # folders made, in order
    temps: list[Path] = []  # new files beside each path, not yet in place
    placed: list[tuple[Path, Path | None]] = []  # (path, the old file moved aside, or None), recorded before the move
    now = None
    try:
        modes: list[int | None] = []
        for now, _ in files:
            missing = []
            p = Path(now).parent
            while not os.path.lexists(p) and p != p.parent:
                missing.append(p)
                p = p.parent
            for d in reversed(missing):
                os.mkdir(d)
                made.append(d)
        for now, _ in files:
            try:
                st = os.lstat(now)
            except FileNotFoundError:
                modes.append(None)
                continue
            why = _kind_of(st)
            if why:
                raise WriteError(now, why)
            modes.append(stat.S_IMODE(st.st_mode))
        for (now, text), mode in zip(files, modes):
            tmp = Path(now).parent / f".workflow-{secrets.token_hex(6)}.tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
            temps.append(tmp)
            with open(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            if mode is not None:
                os.chmod(tmp, mode)
        for (now, _), tmp, mode in zip(files, list(temps), modes):
            old = None
            if mode is not None:
                old = Path(now).parent / f".workflow-{secrets.token_hex(6)}.old"
            placed.append((Path(now), old))
            if old is not None:
                os.rename(now, old)
            os.replace(tmp, now)
            temps.remove(tmp)
    except BaseException as e:  # anything, an interrupt too: undone, then raised again
        kept: list[tuple[Path, Path | None]] = []  # (path, its old file, the only copy, kept; or None: a new file not removed)
        for path, old in reversed(placed):  # each put back as it was
            try:
                if old is None:
                    if os.path.lexists(path):  # there was nothing here: it is the new file
                        os.unlink(path)
                elif os.path.lexists(old):  # else never moved aside: the old file is still in place
                    os.replace(old, path)
            except OSError:
                kept.append((path, old))
        for f in temps:  # never an old file: each is put back, kept or never moved
            try:
                os.unlink(f)
            except OSError:
                pass
        for d in reversed(made):
            try:
                os.rmdir(d)
            except OSError:
                pass
        if isinstance(e, WriteError):
            e.kept = kept
            raise
        if not isinstance(e, OSError):
            raise
        raise WriteError(now, e.strerror or str(e), kept) from None
    for _, old in placed:
        if old is not None:
            try:
                os.unlink(old)
            except OSError:
                pass


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

    def unread(e: OSError):  # a folder that can't be listed can't be ruled out: refused
        raise LayoutError(
            f"{path}: {e.filename} is a folder in the topic's folder that can't be read ({e.strerror or e}), so a fingerprint file in it can't be "
            "ruled out, and its source wouldn't be read: make it readable, or move it out of the topic's folder"
        )

    for folder, folders, files in os.walk(path.parent, onerror=unread):
        folders.sort()
        for name in sorted(files):
            f = Path(folder) / name
            try:
                resolved = f.resolve()
            except (OSError, RuntimeError):  # a symlink loop, before Python 3.13: never a listed file, so it is read below and refused
                resolved = None
            if resolved not in listed and _is_fingerprint_file(f, path):
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
