"""#506: research notes (spec #505). Seam 1, `workflow research` fed files
(`fingerprint`, `check`, `notes`), with `--fetch` against a local server; seam
2, the fixtures tied to the layout the `study` skill's text shows."""

import hashlib
import http.server
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import threading
from datetime import date
from pathlib import Path

import pytest

from conftest import KIT
from workflow import research

CLI = KIT / "scripts/workflow.py"
FIX = KIT / "tests/fixtures/research"
NOTE = FIX / "booking-ahead"
PAGE = FIX / "pages/booking-help.html"
URL = "https://example.com/help/booking"
SKILL = KIT / "skills/study/SKILL.md"

PARAS = [
    "Booking a table",
    "You can book a table up to 30 days ahead. Bookings open at 9:00 each morning.",
    "Questions? Call the manager on 555-0100.",
    "Cancel up to 2 hours before your booking for a full refund.",
]


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cli(*args, cwd=None, env=None):
    e = {**os.environ, **(env or {})}
    return subprocess.run([sys.executable, "-B", str(CLI), "research", *map(str, args)], capture_output=True, text=True, cwd=cwd, env=e)


@pytest.fixture
def project(tmp_path):
    """A project with a profile (one sensitive pattern) and the fixture note."""
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname="d"\nrepo="a/d"\n[sensitive]\npatterns=[\'BOOKCODE-[0-9]{6}\']\n', encoding="utf-8"
    )
    shutil.copytree(NOTE, tmp_path / "docs/research/booking-ahead")
    return tmp_path


def _env(project):
    return {"CLAUDE_PROJECT_DIR": str(project)}


def _html(paras):
    body = "\n".join(f"<p>{p}</p>" for p in paras)
    return f"<!doctype html><html><head><title>t</title></head><body>{body}</body></html>"


def _page(tmp_path, paras, name="live.html"):
    p = tmp_path / name
    p.write_text(_html(paras), encoding="utf-8")
    return p


def _note(project):
    return project / "docs/research/booking-ahead/note.md"


# ---------- a local server for --fetch ----------


class _Pages(http.server.BaseHTTPRequestHandler):
    routes: dict = {}

    def do_GET(self):  # noqa: N802
        status, ctype, body = self.routes.get(self.path, (404, "text/plain", b"not here"))
        if status in (301, 302):
            self.send_response(status)
            self.send_header("Location", body.decode())
            self.end_headers()
            return
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    routes = {}
    handler = type("H", (_Pages,), {"routes": routes})
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", routes
    httpd.shutdown()
    httpd.server_close()


def _closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ---------- fingerprint ----------


def test_fingerprint_hashes_each_paragraph_of_the_page_as_fetched(project):
    p = _cli("fingerprint", URL, "--page", PAGE, "--json", env=_env(project))
    assert p.returncode == 0, p.stderr
    got = json.loads(p.stdout)
    assert got["url"] == URL
    assert [x["text"] for x in got["paragraphs"]] == PARAS  # the title, script, style and nav left out
    assert [x["hash"] for x in got["paragraphs"]] == [_h(t) for t in PARAS]
    assert [x["position"] for x in got["paragraphs"]] == [1, 2, 3, 4]


def test_fingerprint_prints_each_paragraphs_text_and_hash(project):
    p = _cli("fingerprint", URL, "--page", PAGE, env=_env(project))
    assert p.returncode == 0, p.stderr
    for i, t in enumerate(PARAS, 1):
        assert f"{i} {_h(t)}" in p.stdout
        assert t in p.stdout


def _files_from(out: dict, accessed: str) -> tuple[str, str]:
    """The fingerprint file and the saved copy, written from one
    `fingerprint --json` output as the study skill says: the header lines are
    the skill's example's, the `Accessed:` date today's."""
    head = _shown("docs/research/booking-ahead/sources/booking-help.md").splitlines()[:3]
    head = [l.replace("https://example.com/help/booking", out["url"]) for l in head]
    head[1] = f"Accessed: {accessed}"
    paras = out["paragraphs"]
    fps = f"url: {out['url']}\n" + "".join(f"{x['position']} {x['hash']}\n" for x in paras)
    saved = "\n".join(head) + "\n\n" + "\n\n".join(x["text"] for x in paras) + "\n"
    return fps, saved


def test_the_files_written_from_one_fingerprint_output_pass_the_check(project, server):
    text = SKILL.read_text(encoding="utf-8")
    assert "WF research fingerprint <link> --fetch --json" in text and "--saved" not in text
    base, routes = server
    link = f"{base}/help/booking"
    routes["/help/booking"] = (200, "text/html", PAGE.read_bytes())
    p = _cli("fingerprint", link, "--fetch", "--json", env=_env(project))
    assert p.returncode == 0, p.stderr
    fps, saved = _files_from(json.loads(p.stdout), date.today().isoformat())
    # the fingerprints are the fixture's, which the skill shows
    assert fps == (NOTE / "sources/booking-help.fingerprints").read_text(encoding="utf-8").replace(URL, link)
    folder = _note(project).parent
    (folder / "sources/booking-help.fingerprints").write_text(fps, encoding="utf-8")
    (folder / "sources/booking-help.md").write_text(saved, encoding="utf-8")
    _break(project, "note.md", URL, link)
    p = _check(project, extra=["--fetch"])
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["sources"][0]["result"] == "unchanged"


@pytest.mark.parametrize("option", ["--saved", "--fingerprints"])
def test_fingerprint_writes_nothing_and_takes_no_file_to_write(project, option):
    before = _snapshot(project)
    p = _cli("fingerprint", URL, "--page", PAGE, option, project / "out", env=_env(project))
    assert p.returncode == 2 and p.stdout == ""
    assert _snapshot(project) == before


def test_fingerprint_leaves_out_sensitive_patterns_but_hashes_the_page_as_fetched(project, tmp_path):
    paras = ["Your code is BOOKCODE-123456, keep it.", "Plain words."]
    page = _page(tmp_path, paras)
    p = _cli("fingerprint", URL, "--page", page, "--json", env=_env(project))
    assert p.returncode == 0, p.stderr
    got = json.loads(p.stdout)["paragraphs"]
    assert got[0]["hash"] == _h(paras[0])
    assert "BOOKCODE-123456" not in p.stdout
    assert got[0]["text"] == "Your code is [left out], keep it."


@pytest.mark.parametrize("how", ["page", "fetch"])
def test_fingerprint_sensitive_data(project, how):
    link = f"http://127.0.0.1:{_closed_port()}/help?code=BOOKCODE-123456"
    given = ["--page", project / "missing.html"] if how == "page" else ["--fetch"]  # refused before it reads or fetches
    before = _snapshot(project)
    p = _cli("fingerprint", link, *given, env=_env(project))
    assert p.returncode == 1 and p.stdout == ""
    assert "sensitive data" in p.stderr and "can't" not in p.stderr
    assert "BOOKCODE-123456" not in p.stdout + p.stderr and "127.0.0.1" not in p.stderr
    assert _snapshot(project) == before


def test_fingerprint_fetches_the_page(project, server):
    base, routes = server
    routes["/help"] = (200, "text/html; charset=utf-8", PAGE.read_bytes())
    p = _cli("fingerprint", f"{base}/help", "--fetch", "--json", env=_env(project))
    assert p.returncode == 0, p.stderr
    assert [x["hash"] for x in json.loads(p.stdout)["paragraphs"]] == [_h(t) for t in PARAS]


class _Seen(http.server.BaseHTTPRequestHandler):
    """Records every request it gets, of any method, and answers 404."""

    seen: list = []

    def parse_request(self):
        ok = super().parse_request()
        self.seen.append(self.requestline)
        return ok

    def do_GET(self):  # noqa: N802
        self.send_error(404)

    do_CONNECT = do_GET  # noqa: N815

    def log_message(self, *a):
        pass


@pytest.fixture
def seen():
    """A local server that records every request, the proxy for every link."""
    requests: list = []
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), type("S", (_Seen,), {"seen": requests}))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", requests
    httpd.shutdown()
    httpd.server_close()


@pytest.mark.parametrize("link", ["{base}/caf\u00e9", "https://fa\u00df.de/", "{base}/caf\udce9"], ids=["path", "host", "lone-surrogate"])
def test_page_fetching_refuses_a_link_outside_ascii_before_any_request(project, seen, monkeypatch, link):
    base, requests = seen
    link = link.format(base=base)

    def opened(self, *a, **k):
        raise AssertionError(f"a request was made for {link!r}")

    monkeypatch.setattr(research.urllib.request.OpenerDirector, "open", opened)
    with pytest.raises(research.PageError, match="outside ASCII"):
        research.fetch(link)
    proxy = {k: base for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY")}
    p = _cli("fingerprint", link, "--fetch", env={**_env(project), **proxy, "no_proxy": "", "NO_PROXY": ""})
    assert p.returncode == 1 and p.stdout == ""
    assert "can't fetch" in p.stderr and "outside ASCII" in p.stderr
    assert "Traceback" not in p.stderr
    assert requests == []


def test_fingerprint_fetches_a_link_with_its_escapes_left_alone(project, server):
    base, routes = server
    routes["/caf%C3%A9%20menu"] = (200, "text/html", b"<p>B</p>")
    p = _cli("fingerprint", f"{base}/caf%C3%A9%20menu", "--fetch", "--json", env=_env(project))
    assert p.returncode == 0, p.stderr
    assert [x["text"] for x in json.loads(p.stdout)["paragraphs"]] == ["B"]


def test_fingerprint_reads_a_plain_text_page_by_its_blank_lines(project, server):
    base, routes = server
    routes["/a.txt"] = (200, "text/plain", b"First  line\nstill first.\n\n\nSecond.\n")
    p = _cli("fingerprint", f"{base}/a.txt", "--fetch", "--json", env=_env(project))
    assert p.returncode == 0, p.stderr
    assert [x["text"] for x in json.loads(p.stdout)["paragraphs"]] == ["First line still first.", "Second."]


@pytest.mark.parametrize(
    "route",
    [(404, "text/html", b"gone"), (200, "application/pdf", b"%PDF-1.4"), (200, "text/html", b"<html><body><script>app()</script></body></html>")],
    ids=["not-found", "not-text", "no-text"],
)
def test_fingerprint_refuses_a_page_it_cant_read_and_writes_nothing(project, server, route):
    base, routes = server
    routes["/x"] = route
    before = _snapshot(project)
    p = _cli("fingerprint", f"{base}/x", "--fetch", env=_env(project))
    assert p.returncode == 1 and p.stdout == ""
    assert "can't" in p.stderr
    assert _snapshot(project) == before


@pytest.mark.parametrize(
    "html,want",
    [
        (b"<html><head><title>T</title><body><p>A</p>", ["A"]),  # `</head>` left out
        (b"<nav><nav>x</nav>y</nav><p>B</p>", ["B"]),  # a skipped element inside one of its kind
        (b"<p>a<br>b</p><table><tr><td>c</td><td>d</td></tr></table>", ["a b", "c d"]),
        (b"<nav/><p>C</p><div/>D", ["C", "D"]),  # `<x/>` opens nothing
    ],
    ids=["head-not-closed", "nested-skip", "spaces", "self-closing"],
)
def test_the_html_reader(html, want):
    assert research.paragraphs(html, "text/html") == want


@pytest.mark.parametrize(
    "html",
    [
        b"<head><noscript><img src=x></noscript><title>T</title></head><p>A</p>",
        b"<head><template><div>t</div></template><title>T</title></head><p>A</p>",
    ],
    ids=["noscript", "template"],
)
def test_the_head_is_skipped_until_its_end_or_the_body(html):
    assert research.paragraphs(html, "text/html") == ["A"]


_HTML5 = b"<!doctype html><html><head><title>T</title><p>First para.<p>Second para.</html>"


def test_a_page_that_leaves_out_both_the_heads_end_and_the_body_gives_its_paragraphs(project):
    # #526: the head that never ends at `</head>` or `<body>` ends at the first
    # tag (or text) that isn't head content, as HTML5 says.
    assert research.paragraphs(_HTML5, "text/html") == ["First para.", "Second para."]
    page = project / "html5.html"
    page.write_bytes(_HTML5)
    before = _snapshot(project)
    p = _cli("fingerprint", URL, "--page", page, "--json", env=_env(project))
    assert p.returncode == 0, p.stderr
    got = json.loads(p.stdout)["paragraphs"]
    assert [x["text"] for x in got] == ["First para.", "Second para."]
    assert [x["hash"] for x in got] == [_h("First para."), _h("Second para.")]
    assert _snapshot(project) == before  # it writes nothing


@pytest.mark.parametrize(
    "html,want",
    [
        # tags inside a head's <noscript> or <template> never end it
        (b"<head><noscript><img src=x></noscript><title>T</title><p>A</p>", ["A"]),
        (b"<head><noscript>&lt;img src=x&gt;</noscript><title>T</title><p>A</p>", ["A"]),
        (b"<head><template><p>Hidden</p></template><title>T</title><p>A</p>", ["A"]),
        (b"<head><template><template><p>x</p></template><p>y</p></template><title>T</title><p>A</p>", ["A"]),
        (b"<head><title>T<p>x</p></title><p>A</p>", ["A"]),  # a title's tags are its text
        (b"<head><noscript><noscript></noscript><title>T</title><p>A</p>", ["A"]),  # a noscript holds no noscript
        # head content, whitespace and comments keep it open
        (b"<html><head>\n <meta charset=utf-8><link rel=icon href=x><base href=/><style>p{}</style>"
         b"<script>a = '<p>no</p>'</script><noframes><p>no</p></noframes><!-- c --><meta/><head><html><p>A", ["A"]),
        # these two are head content with no end tag: what follows them is read
        (b"<head><title>T</title><basefont size=3><p>A", ["A"]),
        (b"<head><title>T</title><bgsound src=x><p>A", ["A"]),
        # anything else ends it, and is read
        (b"<head><title>T</title>Hello<p>A", ["Hello", "A"]),  # text
        (b"<head><title>T</title><h1>H</h1><p>A", ["H", "A"]),
        (b"<head><title>T</title><br/>Hello", ["Hello"]),  # a self-closed tag
        (b"<head><title>T</title><nav>N</nav><p>A", ["A"]),  # an element whose content is never text
        (b"<head><title>T</title></body><p>A", ["A"]),
        (b"<head><title>T</title></div><p>A", ["A"]),  # another end tag is ignored
    ],
    ids=[
        "noscript-tag", "noscript-text", "template", "nested-template", "title", "noscript-noscript",
        "head-content", "basefont", "bgsound", "text", "block", "self-closed", "skipped-element", "end-body", "end-other",
    ],
)
def test_a_head_that_isnt_closed_ends_at_the_first_tag_that_isnt_head_content(html, want):
    assert research.paragraphs(html, "text/html") == want


@pytest.mark.parametrize(
    "html,want",
    [
        (b'<!doctype html><html><head><meta charset="utf-8"><img src="pixel.gif" alt="">'
         b"<title>Booking help</title><p>Book 30 days ahead.", ["Book 30 days ahead."]),
        (b"<head><meta charset=utf-8>Hello<title>Page title</title><p>A", ["Hello", "A"]),
        (b"<head><custom-el></custom-el><title>T</title><p>A", ["A"]),
        (b"<head><div></div><noframes>NF</noframes><p>A", ["A"]),
        # their content is text: a tag in it opens nothing
        (b"<head><div></div><title>T<p>x</title><p>A", ["A"]),
        (b"<head><div></div><title>T<title>x</title><p>A", ["A"]),
        (b"<head><div></div><noframes>T<noframes>x</noframes><p>A", ["A"]),
    ],
    ids=["img", "text", "custom", "noframes", "title-tag", "title-title", "noframes-noframes"],
)
def test_after_a_head_that_isnt_closed_a_title_or_noframes_is_never_read(html, want):
    # As HTML5 says, a title or noframes after the head is still head content.
    assert research.paragraphs(html, "text/html") == want


@pytest.mark.parametrize(
    "html,want",
    [
        # what HTML5 would read as text, a closed head still leaves out (#526: unchanged)
        (b"<head><title>T</title><div>x</div></head><body><p>A</p>", ["A"]),
        (b"<head><title>T</title>Hello</head><p>A</p>", ["A"]),
        (b"<head><p>x</p><body><p>A</p>", ["A"]),
        (b"<head><noscript></head><body><p>A</p>", ["A"]),
        # a later head left open after the first one closed: as before
        (b"<head></head><p>A</p><head><p>B", ["A"]),
        (b"<p>A</p><head></head><p>B</p>", ["A", "B"]),
        (b"<head></head><title>T</title><p>A</p>", ["T", "A"]),  # a title after a closed head
    ],
    ids=["div", "text", "body", "noscript-open", "later-head-open", "text-before", "title-after"],
)
def test_a_closed_head_reads_as_before(html, want):
    assert research.paragraphs(html, "text/html") == want


def test_the_fixture_pages_fingerprints_are_unchanged():
    got = research.paragraphs(PAGE.read_bytes(), "text/html; charset=utf-8")
    fps = (NOTE / "sources/booking-help.fingerprints").read_text(encoding="utf-8").splitlines()[1:]
    assert [f"{i} {_h(t)}" for i, t in enumerate(got, 1)] == fps


_CAFE = b"<p>Caf\xc3\xa9</p>"


@pytest.mark.parametrize(
    "ctype,raw",
    [
        ("text/html", _CAFE),
        ("text/html; charset=utf-8", _CAFE),
        ("text/html; charset=UTF8", _CAFE),
        ("text/html; charset=us-ascii", _CAFE),
        ("text/html", b'<meta charset="utf-8">' + _CAFE),
        ("text/html", b'<meta charset="ascii">' + _CAFE),
        ("text/html", b"\xef\xbb\xbf" + _CAFE),
        ("text/plain; charset=utf-8", b"Caf\xc3\xa9"),
    ],
    ids=["no-charset", "header-utf-8", "header-utf8", "header-ascii", "meta-utf-8", "meta-ascii", "bom", "plain-text"],
)
def test_a_utf8_page_is_read(ctype, raw):
    assert research.paragraphs(raw, ctype) == ["Caf\u00e9"]


@pytest.mark.parametrize(
    "ctype,raw,charset",
    [
        ("text/html; charset=windows-1252", b"<p>Caf\xe9</p>", "windows-1252"),
        ("text/html", b'<meta charset="windows-1252"><p>Caf\xe9</p>', "windows-1252"),
        ("text/html; charset=latin-1", b"<p>Caf\xe9</p>", "latin-1"),
        ("text/html; charset=Shift_JIS", "<p>\u4e88\u7d04</p>".encode("shift_jis"), "Shift_JIS"),
        ("text/html; charset=TIS-620", "<p>\u0e01\u0e14</p>".encode("tis-620"), "TIS-620"),
        ("text/html", b'<meta charset="punycode"><p>Book up to 30 days ahead - call first.</p>', "punycode"),
        ("text/html; charset=punycode", b"<p>a-" + b"A" * 2_000_000 + b"</p>", "punycode"),  # refused before any decoding: never slow
        ("text/html; charset=unicode_escape", b"<p>C:\\new</p>", "unicode_escape"),
        ("text/html; charset=undefined", _CAFE, "undefined"),
        ("text/html", b'<meta charset="undefined">' + _CAFE, "undefined"),
        ("text/html; charset=idna", _CAFE, "idna"),
        ("text/html", b'<meta charset="idna">' + _CAFE, "idna"),
        ("text/plain; charset=windows-1252", b"Caf\xe9", "windows-1252"),
    ],
    ids=[
        "header-windows-1252", "meta-windows-1252", "latin-1", "shift-jis", "tis-620", "meta-punycode", "punycode-long",
        "unicode-escape", "header-undefined", "meta-undefined", "header-idna", "meta-idna", "plain-text",
    ],
)
def test_a_page_not_in_utf8_is_refused(ctype, raw, charset):
    with pytest.raises(research.PageError, match=f"it is in {re.escape(charset)}; only UTF-8 pages are read"):
        research.paragraphs(raw, ctype)


@pytest.mark.parametrize("ctype,raw", [("text/html", b"<p>Caf\xe9</p>"), ("text/plain", b"Caf\xe9")], ids=["html", "plain-text"])
def test_bytes_that_arent_valid_utf8_are_refused(ctype, raw):
    with pytest.raises(research.PageError, match="its bytes aren't valid UTF-8"):
        research.paragraphs(raw, ctype)


def test_html_it_cant_parse_is_a_page_it_cant_read(monkeypatch):
    def broken(self, data):
        raise AssertionError("unknown status keyword")

    monkeypatch.setattr(research._Text, "feed", broken)
    with pytest.raises(research.PageError):
        research.page_paragraphs(b"<p>A</p>", "text/html")


def test_fingerprint_refuses_a_page_not_in_utf8_and_writes_nothing(project, tmp_path):
    page = tmp_path / "menu.html"
    page.write_bytes(b'<meta charset="windows-1252"><p>Caf\xe9</p>')
    before = _snapshot(project)
    p = _cli("fingerprint", URL, "--page", page, env=_env(project))
    assert p.returncode == 1 and p.stdout == ""
    assert "can't read" in p.stderr and "it is in windows-1252; only UTF-8 pages are read" in p.stderr
    assert "Traceback" not in p.stderr
    assert _snapshot(project) == before


def test_check_cant_fetch_a_source_not_in_utf8_and_reads_the_others(project, server):
    base, routes = server
    other = _two_sources(project)
    folder = _note(project).parent
    for f in ("note.md", "sources/groups.md", "sources/groups.fingerprints"):
        (folder / f).write_text((folder / f).read_text().replace(other, f"{base}/groups"))
    routes["/groups"] = (200, "text/html; charset=idna", PAGE.read_bytes())
    p = _check(project, (URL, PAGE), extra=["--fetch"])
    assert p.returncode == 0, p.stderr
    got = json.loads(p.stdout)["sources"]
    assert [(s["url"], s["result"]) for s in got] == [(URL, "unchanged"), (f"{base}/groups", "cant_fetch")]
    assert "only UTF-8 pages are read" in got[1]["why"]


@pytest.mark.parametrize(
    "name,raw",
    [
        ("law.pdf", b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n"),
        ("logo.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"),
        ("page", b"<p>A page saved with no suffix.</p>"),
    ],
    ids=["pdf", "png", "no-suffix"],
)
def test_fingerprint_refuses_a_file_that_isnt_a_text_page_and_writes_nothing(project, tmp_path, name, raw):
    page = tmp_path / name
    page.write_bytes(raw)
    before = _snapshot(project)
    p = _cli("fingerprint", URL, "--page", page, env=_env(project))
    assert p.returncode == 1, p.stdout
    assert "isn't a text page" in p.stderr and p.stdout == ""
    assert _snapshot(project) == before


@pytest.mark.parametrize("name", ["help.txt", "help.md", "help.htm", "help.xhtml"])
def test_fingerprint_reads_a_file_named_as_a_text_page(project, tmp_path, name):
    page = tmp_path / name
    page.write_text("<p>First.</p>\n\n<p>Second.</p>\n" if "htm" in name else "First.\n\nSecond.\n", encoding="utf-8")
    p = _cli("fingerprint", URL, "--page", page, "--json", env=_env(project))
    assert p.returncode == 0, p.stderr
    assert [x["text"] for x in json.loads(p.stdout)["paragraphs"]] == ["First.", "Second."]


_UNTYPED = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n", b"<html><p>A</p></html>"]


@pytest.mark.parametrize("raw", _UNTYPED, ids=["pdf", "html"])
def test_fingerprint_refuses_a_page_that_names_no_content_type(project, server, raw):
    base, routes = server
    routes["/x"] = (200, "", raw)
    before = _snapshot(project)
    p = _cli("fingerprint", f"{base}/x", "--fetch", env=_env(project))
    assert p.returncode == 1 and p.stdout == ""
    assert "can't fetch" in p.stderr and "no content type" in p.stderr
    assert _snapshot(project) == before


@pytest.mark.parametrize("raw", _UNTYPED, ids=["pdf", "html"])
def test_check_cant_fetch_a_page_that_names_no_content_type(project, server, raw):
    base, routes = server
    routes["/help/booking"] = (200, "", raw)
    folder = _note(project).parent
    for f in ("note.md", "sources/booking-help.md", "sources/booking-help.fingerprints"):
        (folder / f).write_text((folder / f).read_text().replace(URL, f"{base}/help/booking"))
    p = _check(project, extra=["--fetch"])
    assert p.returncode == 0, p.stderr
    (src,) = json.loads(p.stdout)["sources"]
    assert src["result"] == "cant_fetch" and "no content type" in src["why"]


def test_check_cant_read_a_file_that_isnt_a_text_page(project, tmp_path):
    page = tmp_path / "help.pdf"
    page.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    p = _check(project, (URL, page))
    assert p.returncode == 0, p.stderr
    (src,) = json.loads(p.stdout)["sources"]
    assert src["result"] == "cant_fetch" and "isn't a text page" in src["why"]


def test_fingerprint_cant_fetch_an_unreachable_page(project):
    p = _cli("fingerprint", f"http://127.0.0.1:{_closed_port()}/x", "--fetch", env=_env(project))
    assert p.returncode == 1 and "can't fetch" in p.stderr


@pytest.mark.parametrize("link", ["file:///etc/passwd", "ftp://example.com/a", "example.com/a"])
def test_fingerprint_fetches_only_web_links(project, link):
    p = _cli("fingerprint", link, "--fetch", env=_env(project))
    assert p.returncode == 1 and "can't fetch" in p.stderr
    assert "root:" not in p.stdout


def test_fingerprint_follows_a_redirect(project, server):
    base, routes = server
    routes["/old"] = (302, "", b"/help")
    routes["/help"] = (200, "text/html", PAGE.read_bytes())
    p = _cli("fingerprint", f"{base}/old", "--fetch", "--json", env=_env(project))
    assert p.returncode == 0, p.stderr
    assert [x["hash"] for x in json.loads(p.stdout)["paragraphs"]] == [_h(t) for t in PARAS]


@pytest.mark.parametrize("target", [b"file:///etc/passwd", b"ftp://example.com/a"], ids=["file", "ftp"])
def test_fingerprint_follows_redirects_only_to_web_links(project, server, target):
    base, routes = server
    routes["/evil"] = (302, "", target)
    p = _cli("fingerprint", f"{base}/evil", "--fetch", env=_env(project))
    assert p.returncode == 1 and "can't fetch" in p.stderr
    assert "root:" not in p.stdout + p.stderr


def test_a_profile_it_cant_read_stops_the_command(project):
    (project / ".claude/workflow/profile.toml").write_text('[project]\nname="d"\nrepo="a/d"\n[sensitive]\npatterns=[\'(\']\n', encoding="utf-8")
    p = _cli("fingerprint", URL, "--page", PAGE, env=_env(project))
    assert p.returncode == 1 and p.stdout == ""
    assert "sensitive.patterns" in p.stderr


def test_fingerprint_needs_a_page_or_fetch(project):
    p = _cli("fingerprint", URL, env=_env(project))
    assert p.returncode == 2 and "--page" in p.stderr and "--fetch" in p.stderr


# ---------- check ----------


def _check(project, *pages, extra=(), json_out=True):
    args = ["check", "--note", _note(project)]
    for url, page in pages:
        args += ["--page", url, page]
    args += list(extra)
    if json_out:
        args.append("--json")
    return _cli(*args, env=_env(project))


def test_check_unchanged(project):
    p = _check(project, (URL, PAGE))
    assert p.returncode == 0, p.stderr
    got = json.loads(p.stdout)
    assert got["status"] == "current"
    (src,) = got["sources"]
    assert src["url"] == URL and src["result"] == "unchanged"
    assert src["new"] == [] and src["gone"] == []
    text = _check(project, (URL, PAGE), json_out=False)
    assert "unchanged" in text.stdout and "Questions?" not in text.stdout


def test_check_compares_as_a_set_so_moved_paragraphs_are_unchanged(project, tmp_path):
    page = _page(tmp_path, [PARAS[3], PARAS[0], PARAS[2], PARAS[1], PARAS[0]])
    src = json.loads(_check(project, (URL, page)).stdout)["sources"][0]
    assert src["result"] == "unchanged"


def test_check_reports_new_paragraphs_with_their_live_text_and_hash(project, tmp_path):
    new = "Groups of 8 or more call ahead."
    page = _page(tmp_path, PARAS[:2] + [new] + PARAS[2:])
    src = json.loads(_check(project, (URL, page)).stdout)["sources"][0]
    assert src["result"] == "changed"
    assert src["new"] == [{"position": 3, "hash": _h(new), "text": new}]
    assert src["gone"] == []


def test_check_reports_paragraphs_gone_by_position_with_the_saved_text_and_hash(project, tmp_path):
    page = _page(tmp_path, [PARAS[0], PARAS[3]])
    src = json.loads(_check(project, (URL, page)).stdout)["sources"][0]
    assert src["result"] == "changed" and src["new"] == []
    assert src["gone"] == [
        {"position": 2, "hash": _h(PARAS[1]), "saved_text": PARAS[1]},
        {"position": 3, "hash": _h(PARAS[2]), "saved_text": "[left out]"},  # the saved copy's text, never the page's
    ]


def test_check_a_changed_paragraph_is_new_and_gone(project, tmp_path):
    changed = "You can book a table up to 60 days ahead. Bookings open at 9:00 each morning."
    page = _page(tmp_path, [PARAS[0], changed, PARAS[2], PARAS[3]])
    p = _check(project, (URL, page))
    src = json.loads(p.stdout)["sources"][0]
    assert src["new"] == [{"position": 2, "hash": _h(changed), "text": changed}]
    assert src["gone"] == [{"position": 2, "hash": _h(PARAS[1]), "saved_text": PARAS[1]}]
    text = _check(project, (URL, page), json_out=False).stdout
    assert changed in text and _h(changed) in text and _h(PARAS[1]) in text and "changed" in text


def test_check_leaves_sensitive_patterns_out_of_live_text(project, tmp_path):
    page = _page(tmp_path, PARAS + ["Quote BOOKCODE-654321 when you call."])
    p = _check(project, (URL, page))
    assert "BOOKCODE-654321" not in p.stdout
    (new,) = json.loads(p.stdout)["sources"][0]["new"]
    assert new["text"] == "Quote [left out] when you call." and new["hash"] == _h("Quote BOOKCODE-654321 when you call.")


def _two_sources(project):
    """The fixture note with a second key source, copied from the first."""
    folder = _note(project).parent
    other = "https://example.com/help/groups"
    shutil.copy(folder / "sources/booking-help.md", folder / "sources/groups.md")
    shutil.copy(folder / "sources/booking-help.fingerprints", folder / "sources/groups.fingerprints")
    for f in ("sources/groups.md", "sources/groups.fingerprints"):
        (folder / f).write_text((folder / f).read_text().replace(URL, other))
    with open(folder / "note.md", "a", encoding="utf-8") as fh:
        fh.write(f"- <{other}>, saved as `sources/groups.md`, fingerprints in `sources/groups.fingerprints`\n")
    return other


def test_check_cant_fetch(project, server):
    base, routes = server
    other = _two_sources(project)
    folder = _note(project).parent
    for f in ("sources/groups.md", "sources/groups.fingerprints"):
        (folder / f).write_text((folder / f).read_text().replace(other, f"{base}/gone"))
    (folder / "note.md").write_text((folder / "note.md").read_text().replace(other, f"{base}/gone"))
    p = _check(project, (URL, PAGE), extra=["--fetch"])
    assert p.returncode == 0, p.stderr
    a, b = json.loads(p.stdout)["sources"]
    assert a["result"] == "unchanged"
    assert b["url"] == f"{base}/gone" and b["result"] == "cant_fetch" and "404" in b["why"]
    text = _check(project, (URL, PAGE), extra=["--fetch"], json_out=False).stdout
    assert "can't fetch" in text


def test_check_fetches_the_sources_not_given(project, server):
    base, routes = server
    routes["/help/booking"] = (200, "text/html", PAGE.read_bytes())
    folder = _note(project).parent
    for f in ("note.md", "sources/booking-help.md", "sources/booking-help.fingerprints"):
        (folder / f).write_text((folder / f).read_text().replace(URL, f"{base}/help/booking"))
    p = _check(project, extra=["--fetch"])
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["sources"][0]["result"] == "unchanged"


def test_check_needs_each_page_or_fetch(project):
    other = _two_sources(project)
    p = _check(project, (URL, PAGE))
    assert p.returncode == 2 and other in p.stderr and "--fetch" in p.stderr


def _break(project, path, old, new):
    f = _note(project).parent / path
    text = f.read_text()
    assert old in text
    f.write_text(text.replace(old, new))


@pytest.mark.parametrize(
    "path,old,new,said",
    [
        ("sources/booking-help.md", "[left out]\n\n", "", "paragraphs"),  # a paragraph deleted, not left out
        ("sources/booking-help.fingerprints", "\n4 4301a2050cf762c2ae5567611ac08bb487eaba2d7190b6eba3712bfe6cdb6ed0", "", "paragraphs"),
        ("note.md", "`sources/booking-help.md`", "`../../secrets.md`", "outside"),
        ("note.md", "`sources/booking-help.md`", "`/etc/passwd`", "outside"),
        ("note.md", ", saved as", " saved as", "key-source line"),
        ("note.md", "## Key sources", "## Sources", "## Key sources"),
        ("sources/booking-help.fingerprints", "url: https://example.com/help/booking", "url: https://example.com/other", "link"),
        ("sources/booking-help.md", "Source: https://example.com/help/booking", "Source: https://example.com/other", "link"),
        ("sources/booking-help.md", "Third-party text:", "Third party:", "Third-party text"),
        ("sources/booking-help.fingerprints", "2 d8aa", "2 zz", "fingerprint"),
        ("note.md", "- <https", "* <https", "key-source line"),
        ("note.md", "- <https", "  - <https", "key-source line"),
        ("note.md", "- <https", "1. <https", "key-source line"),
        ("note.md", "## Key sources\n\n", "## Key sources\n\n### Laws\n\n", "last section"),
        ("note.md", "- <https://example.com/help/booking>, saved as `sources/booking-help.md`, fingerprints in `sources/booking-help.fingerprints`\n", "", "- None"),
        ("sources/booking-help.md", "up to 30 days", "up to 90 days", "paragraph 2 doesn't match its fingerprint"),
        (
            "sources/booking-help.md",
            "\n\n".join([PARAS[0], PARAS[1], "[left out]", PARAS[3]]),
            "\n\n".join([PARAS[3], PARAS[1], "[left out]", PARAS[0]]),
            "paragraph 1 doesn't match its fingerprint",
        ),
    ],
    ids=[
        "paragraph-deleted", "hash-missing", "path-escapes", "path-absolute", "bad-line", "no-section", "fp-link", "saved-link", "no-third-party-line", "bad-hash",
        "star-bullet", "indented", "numbered", "subheading", "empty-section", "one-word-changed", "paragraphs-swapped",
    ],
)
def test_check_refuses_a_note_that_breaks_the_layout(project, path, old, new, said):
    _break(project, path, old, new)
    p = _check(project, (URL, PAGE))
    assert p.returncode == 1, p.stdout
    assert said in p.stderr
    assert p.stdout == ""


def test_check_accepts_a_saved_paragraph_with_words_left_out(project):
    _break(project, "sources/booking-help.md", "at 9:00 each", "at [left out] each")
    p = _check(project, (URL, PAGE))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["sources"][0]["result"] == "unchanged"


def test_check_a_note_with_no_key_sources(project):
    _break(project, "note.md", "- <https://example.com/help/booking>, saved as `sources/booking-help.md`, fingerprints in `sources/booking-help.fingerprints`", "- None")
    p = _check(project)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["sources"] == []


@pytest.mark.parametrize(
    "after",
    [
        "## Key sources\n\n- <https://example.com/help/groups>, saved as `sources/groups.md`, fingerprints in `sources/groups.fingerprints`\n",
        "## Notes\n\nGroups of 8 or more call ahead.\n",
    ],
    ids=["second-key-sources", "a-section-after"],
)
def test_check_refuses_a_note_whose_key_sources_arent_its_last_section_once(project, after):
    note = _note(project)
    n = len(note.read_text(encoding="utf-8").splitlines()) + 2
    with open(note, "a", encoding="utf-8") as fh:
        fh.write("\n" + after)
    p = _check(project, (URL, PAGE))
    assert p.returncode == 1 and p.stdout == ""
    assert f"line {n}" in p.stderr and after.splitlines()[0] in p.stderr
    assert "`## Key sources` must be the note's last section, once" in p.stderr


def test_check_says_when_the_note_is_superseded(project):
    _break(project, "note.md", "Status: current", "Status: superseded by docs/research/booking-rules/note.md")
    p = _check(project, (URL, PAGE), json_out=False)
    assert p.returncode == 0 and "superseded" in p.stdout


# ---------- notes ----------


def _add_note(project, topic, header):
    d = project / "docs/research" / topic
    d.mkdir(parents=True)
    (d / "note.md").write_text(header + "\n\n# " + topic + "\n\nWords.\n", encoding="utf-8")


def test_notes_lists_only_the_notes_marked_current(project):
    _add_note(project, "old-prices", "Status: superseded by docs/research/prices/note.md\nLast checked: 2026-01-02\nIssue: #7")
    _add_note(project, "prices", "Status: current\nLast checked: 2026-10-01\nIssue: #9")
    _add_note(project, "loose", "# A note merged before the header")
    _add_note(project, "typo", "Status: currant\nLast checked: 2026-10-01\nIssue: #9")
    p = _cli("notes", "--json", env=_env(project))
    assert p.returncode == 0, p.stderr
    got = json.loads(p.stdout)
    assert [n["path"] for n in got["current"]] == ["docs/research/booking-ahead/note.md", "docs/research/prices/note.md"]
    assert got["current"][0] == {"path": "docs/research/booking-ahead/note.md", "last_checked": "2026-11-07", "issue": 42, "title": "Booking ahead: how far people book"}
    assert sorted(n["path"] for n in got["not_listed"]) == ["docs/research/loose/note.md", "docs/research/old-prices/note.md", "docs/research/typo/note.md"]
    text = _cli("notes", env=_env(project))
    assert "docs/research/prices/note.md" in text.stdout and "old-prices" not in text.stdout and "loose" not in text.stdout
    assert "loose" in text.stderr and "typo" in text.stderr  # a header it can't read is named
    assert "old-prices" not in text.stderr  # superseded is ordinary


def test_notes_reads_a_folder_given(project, tmp_path):
    other = tmp_path / "elsewhere"
    shutil.copytree(NOTE, other / "booking-ahead")
    p = _cli("notes", "--dir", other, "--json", env=_env(project))
    assert [n["title"] for n in json.loads(p.stdout)["current"]] == ["Booking ahead: how far people book"]


def test_notes_with_no_research_folder(tmp_path):
    p = _cli("notes", "--json", env={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout) == {"current": [], "not_listed": []}


# ---------- no model tokens, nothing written ----------


def _snapshot(root: Path):
    return sorted((p.relative_to(root).as_posix(), p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else b"") for p in root.rglob("*"))


def test_the_command_spends_no_tokens_and_writes_nothing(project, tmp_path, server):
    base, routes = server
    routes["/help"] = (200, "text/html", PAGE.read_bytes())
    tools = tmp_path / "tools"
    tools.mkdir()
    called = tmp_path / "called"
    for name in ("claude", "gh", "curl"):  # a model, or a client that could reach one
        f = tools / name
        f.write_text(f"#!/bin/sh\necho {name} >> {called}\n")
        f.chmod(f.stat().st_mode | stat.S_IEXEC)
    env = {**_env(project), "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}", "ANTHROPIC_API_KEY": ""}
    page = _page(tmp_path, PARAS[:3])
    before = _snapshot(project)
    for args in (
        ["check", "--note", _note(project), "--page", URL, page],
        ["check", "--note", _note(project), "--page", URL, PAGE, "--json"],
        ["notes"],
        ["notes", "--json"],
        ["fingerprint", URL, "--page", PAGE],
        ["fingerprint", f"{base}/help", "--fetch", "--json"],
    ):
        p = _cli(*args, cwd=project, env=env)
        assert p.returncode == 0, (args, p.stderr)
    assert _snapshot(project) == before
    assert not called.exists()


# ---------- seam 2: the fixtures are the layout the skill shows ----------


def _shown(path: str) -> str:
    """The fenced block the `study` skill shows right after naming `path`."""
    text = SKILL.read_text(encoding="utf-8")
    m = re.search(r"`" + re.escape(path) + r"`[^\n]*:\n\n```[a-z]*\n(.*?)\n```", text, re.S)
    assert m, f"the study skill shows no example of {path}"
    return m.group(1) + "\n"


@pytest.mark.parametrize("name", ["note.md", "sources/booking-help.md", "sources/booking-help.fingerprints"])
def test_the_fixtures_are_copied_from_the_layout_the_study_skill_shows(name):
    assert (NOTE / name).read_text(encoding="utf-8") == _shown(f"docs/research/booking-ahead/{name}")


def test_the_study_skill_writes_down_the_header_the_mark_and_left_out_lines():
    text = re.sub(r"\s+", " ", SKILL.read_text(encoding="utf-8"))
    for line in ("`Status:`", "`Last checked:`", "`Issue:`", "`current`", "`superseded by <link>`"):
        assert line in text
    assert "the mark ` **(unconfirmed)**`" in text
    assert "a paragraph left out whole becomes one line, `[left out]`, in its place" in text
    assert "`Third-party text:`" in text and "not covered by the repository's licence" in text
    assert "`docs/research/<topic>/`" in text and "is always `note.md`" in text
    assert "WF research notes" in text and "WF research check" in text and "WF research fingerprint" in text


def test_the_saved_copy_has_one_name():
    """CONTRIBUTING.md's "the same name for the same thing everywhere": the
    skill, the README's row and the changelog's note all say "saved copy"."""
    readme = next(l for l in (KIT / "README.md").read_text(encoding="utf-8").splitlines() if l.startswith("| `skills/study`"))
    log = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    entry = log[log.index("**Research notes in the repository") :]
    entry = entry[: min(i for i in (entry.find("\n\n**", 1), entry.find("\n## ")) if i > 0)]
    for where, text in (("README.md", readme), ("CHANGELOG.md", entry), ("the study skill", SKILL.read_text(encoding="utf-8"))):
        assert "saved source" not in text.lower(), where
        assert "saved cop" in text, where


def test_the_shown_fingerprints_are_the_hashes_of_the_shown_page():
    shown = _shown("docs/research/booking-ahead/sources/booking-help.fingerprints").splitlines()
    assert shown[0] == f"url: {URL}"
    assert shown[1:] == [f"{i} {_h(t)}" for i, t in enumerate(PARAS, 1)]
