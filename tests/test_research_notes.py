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


def test_fingerprint_writes_the_saved_copy_and_fingerprints_in_the_layout(project, tmp_path):
    saved, fps = project / "out/booking-help.md", project / "out/booking-help.fingerprints"
    saved.parent.mkdir()
    p = _cli("fingerprint", URL, "--page", PAGE, "--saved", saved, "--fingerprints", fps, env=_env(project))
    assert p.returncode == 0, p.stderr
    # the fingerprints are exactly the fixture's, which the skill shows
    assert fps.read_text(encoding="utf-8") == (NOTE / "sources/booking-help.fingerprints").read_text(encoding="utf-8")
    want = (NOTE / "sources/booking-help.md").read_text(encoding="utf-8").splitlines()
    got = saved.read_text(encoding="utf-8").splitlines()
    want[1] = f"Accessed: {date.today().isoformat()}"  # computed at the point of use
    want[8] = PARAS[2]  # the fixture's session left paragraph 3 out by hand
    assert got == want


def test_fingerprint_leaves_out_sensitive_patterns_but_hashes_the_page_as_fetched(project, tmp_path):
    paras = ["Your code is BOOKCODE-123456, keep it.", "Plain words."]
    page = _page(tmp_path, paras)
    saved = project / "saved.md"
    p = _cli("fingerprint", URL, "--page", page, "--saved", saved, "--json", env=_env(project))
    assert p.returncode == 0, p.stderr
    got = json.loads(p.stdout)["paragraphs"]
    assert got[0]["hash"] == _h(paras[0])
    assert "BOOKCODE-123456" not in p.stdout and "BOOKCODE-123456" not in saved.read_text()
    assert got[0]["text"] == "Your code is [left out], keep it."
    assert "[left out], keep it." in saved.read_text()


def test_fingerprint_fetches_the_page(project, server):
    base, routes = server
    routes["/help"] = (200, "text/html; charset=utf-8", PAGE.read_bytes())
    p = _cli("fingerprint", f"{base}/help", "--fetch", "--json", env=_env(project))
    assert p.returncode == 0, p.stderr
    assert [x["hash"] for x in json.loads(p.stdout)["paragraphs"]] == [_h(t) for t in PARAS]


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
    saved, fps = project / "s.md", project / "s.fingerprints"
    p = _cli("fingerprint", f"{base}/x", "--fetch", "--saved", saved, "--fingerprints", fps, env=_env(project))
    assert p.returncode == 1
    assert "can't" in p.stderr
    assert not saved.exists() and not fps.exists()


@pytest.mark.parametrize(
    "ctype,raw",
    [
        ("text/html; charset=undefined", b"<p>Caf\xc3\xa9</p>"),
        ("text/html; charset=idna", b"<p>Caf\xc3\xa9</p>"),
        ("text/html", b'<meta charset="undefined"><p>Caf\xc3\xa9</p>'),
        ("text/html", b'<meta charset="idna"><p>Caf\xc3\xa9</p>'),
    ],
    ids=["header-undefined", "header-idna", "meta-undefined", "meta-idna"],
)
def test_a_charset_it_cant_decode_with_is_read_as_utf8(ctype, raw):
    assert research.paragraphs(raw, ctype) == ["Caf\u00e9"]


def test_a_charset_it_can_decode_with_is_used():
    assert research.paragraphs(b"<p>Caf\xe9</p>", "text/html; charset=latin-1") == ["Caf\u00e9"]


def test_html_it_cant_parse_is_a_page_it_cant_read(monkeypatch):
    def broken(self, data):
        raise AssertionError("unknown status keyword")

    monkeypatch.setattr(research._Text, "feed", broken)
    with pytest.raises(research.PageError):
        research.page_paragraphs(b"<p>A</p>", "text/html")


def test_fingerprint_reads_a_page_whose_charset_it_cant_decode_with(project, tmp_path):
    page = tmp_path / "undefined.html"
    page.write_bytes(b'<meta charset="undefined"><p>Hi</p>')
    p = _cli("fingerprint", URL, "--page", page, "--json", env=_env(project))
    assert p.returncode == 0, p.stderr
    assert [x["text"] for x in json.loads(p.stdout)["paragraphs"]] == ["Hi"]


def test_check_reads_every_source_when_one_names_a_charset_it_cant_decode_with(project, server):
    base, routes = server
    other = _two_sources(project)
    folder = _note(project).parent
    for f in ("note.md", "sources/groups.md", "sources/groups.fingerprints"):
        (folder / f).write_text((folder / f).read_text().replace(other, f"{base}/groups"))
    routes["/groups"] = (200, "text/html; charset=idna", PAGE.read_bytes())
    p = _check(project, (URL, PAGE), extra=["--fetch"])
    assert p.returncode == 0, p.stderr
    assert [(s["url"], s["result"]) for s in json.loads(p.stdout)["sources"]] == [(URL, "unchanged"), (f"{base}/groups", "unchanged")]


def test_fingerprint_cant_fetch_an_unreachable_page(project):
    p = _cli("fingerprint", f"http://127.0.0.1:{_closed_port()}/x", "--fetch", env=_env(project))
    assert p.returncode == 1 and "can't fetch" in p.stderr


@pytest.mark.parametrize("link", ["file:///etc/passwd", "ftp://example.com/a", "example.com/a"])
def test_fingerprint_fetches_only_web_links(project, link):
    p = _cli("fingerprint", link, "--fetch", env=_env(project))
    assert p.returncode == 1 and "can't fetch" in p.stderr
    assert "root:" not in p.stdout


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
        ("note.md", "## Key sources\n\n", "## Key sources\n\n### Laws\n\n", "key-source line"),
        ("note.md", "- <https://example.com/help/booking>, saved as `sources/booking-help.md`, fingerprints in `sources/booking-help.fingerprints`\n", "", "- None"),
    ],
    ids=[
        "paragraph-deleted", "hash-missing", "path-escapes", "path-absolute", "bad-line", "no-section", "fp-link", "saved-link", "no-third-party-line", "bad-hash",
        "star-bullet", "indented", "numbered", "subheading", "empty-section",
    ],
)
def test_check_refuses_a_note_that_breaks_the_layout(project, path, old, new, said):
    _break(project, path, old, new)
    p = _check(project, (URL, PAGE))
    assert p.returncode == 1, p.stdout
    assert said in p.stderr
    assert p.stdout == ""


def test_check_a_note_with_no_key_sources(project):
    _break(project, "note.md", "- <https://example.com/help/booking>, saved as `sources/booking-help.md`, fingerprints in `sources/booking-help.fingerprints`", "- None")
    p = _check(project)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["sources"] == []


def test_check_reads_the_key_sources_up_to_the_next_section(project):
    with open(_note(project), "a", encoding="utf-8") as fh:
        fh.write("\n## Open questions\n\n* Do groups book further ahead?\n")
    p = _check(project, (URL, PAGE))
    assert p.returncode == 0, p.stderr
    assert [s["result"] for s in json.loads(p.stdout)["sources"]] == ["unchanged"]


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


def test_the_command_spends_no_tokens_and_writes_nothing_outside_the_files_given(project, tmp_path, server):
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
    saved, fps = project / "out.md", project / "out.fingerprints"
    p = _cli("fingerprint", URL, "--page", PAGE, "--saved", saved, "--fingerprints", fps, cwd=project, env=env)
    assert p.returncode == 0, p.stderr
    after = {x[0] for x in _snapshot(project)} - {x[0] for x in before}
    assert after == {"out.md", "out.fingerprints"}
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
