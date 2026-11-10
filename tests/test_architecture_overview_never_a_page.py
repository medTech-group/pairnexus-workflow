"""The overview is never a page (#631, split from #612; spec #611 seam 1):
`workflow index pages` never lists `docs/architecture/README.md`, `reads`
prints it once, as the overview, and a case variant of its name is either the
overview or a page, never both and never neither, on case-sensitive and
case-insensitive file systems alike. Through `cli.main`, on a scratch git
repository; a case-insensitive file system is stood in for by `Path` answering
for any spelling of a name the folder lists."""

import json
import os
from pathlib import Path

import pytest
from conftest import git

from workflow import cli

ARCH = "docs/architecture"
OVERVIEW = f"{ARCH}/README.md"


def _write(root, rel, text=""):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _repo(tmp_path, files):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@e")
    git(tmp_path, "config", "user.name", "t")
    _write(tmp_path, "README.md", "x\n")
    for rel, text in files.items():
        _write(tmp_path, rel, text)
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "x")
    git(tmp_path, "checkout", "-qb", "work")
    _write(tmp_path, "src/a.py")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "change")
    return tmp_path


def _run(monkeypatch, capsys, root, *args):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    code = cli.main(["index", *args])
    out = capsys.readouterr()
    assert code == 0, out.err
    return out.out


def _case_insensitive(monkeypatch):
    """Make `Path` answer as a case-insensitive file system does: a name that
    isn't there under its own spelling is the entry its folder lists under
    another spelling, when there is one. The folder's listing keeps each
    entry's own spelling, as such a file system's does."""
    real = {name: getattr(Path, name) for name in ("is_file", "exists", "stat", "read_text", "open")}

    def found(p):
        if os.path.lexists(p):
            return p
        try:
            for e in os.listdir(os.path.dirname(p) or "."):
                if e.casefold() == p.name.casefold():
                    return p.with_name(e)
        except OSError:
            pass
        return p

    def wrap(name):
        def f(self, *a, **k):
            return real[name](found(self), *a, **k)
        return f

    for name in real:
        monkeypatch.setattr(Path, name, wrap(name))


FILE_SYSTEMS = ["case-sensitive", "case-insensitive"]


def _on(fs, monkeypatch):
    if fs == "case-insensitive":
        _case_insensitive(monkeypatch)


# ---------- README.md never a page ----------


@pytest.mark.parametrize("fs", FILE_SYSTEMS)
@pytest.mark.parametrize("readme", ["x\n", "Covers: src/**\n\nInterface: not a page\n"])
def test_pages_never_lists_the_overview(tmp_path, monkeypatch, capsys, fs, readme):
    root = _repo(tmp_path, {OVERVIEW: readme, f"{ARCH}/orders.md": "Covers: src/**\n"})
    _on(fs, monkeypatch)
    got = json.loads(_run(monkeypatch, capsys, root, "pages", "--json"))
    assert [pg["file"] for pg in got["pages"]] == [f"{ARCH}/orders.md"]
    text = _run(monkeypatch, capsys, root, "pages")
    assert "README" not in text
    assert text.startswith(f"{ARCH}/orders.md\n")


@pytest.mark.parametrize("fs", FILE_SYSTEMS)
@pytest.mark.parametrize("readme", ["x\n", "Covers: src/**\n"])
def test_reads_prints_the_overview_once_as_the_overview(tmp_path, monkeypatch, capsys, fs, readme):
    root = _repo(tmp_path, {OVERVIEW: readme, f"{ARCH}/orders.md": "Covers: src/**\n"})
    _on(fs, monkeypatch)
    out = _run(monkeypatch, capsys, root, "reads", "--base", "main")
    assert out.splitlines() == [OVERVIEW, f"{ARCH}/orders.md"]
    got = json.loads(_run(monkeypatch, capsys, root, "reads", "--base", "main", "--json"))
    assert got == {
        "documents": [OVERVIEW, f"{ARCH}/orders.md"],
        "pages": [{"file": f"{ARCH}/orders.md", "matched_by": ["src/**"]}],
    }


@pytest.mark.parametrize("fs", FILE_SYSTEMS)
def test_the_overview_alone_is_printed_once_and_no_page(tmp_path, monkeypatch, capsys, fs):
    root = _repo(tmp_path, {OVERVIEW: "x\n"})
    _on(fs, monkeypatch)
    got = json.loads(_run(monkeypatch, capsys, root, "reads", "--base", "main", "--json"))
    assert got == {"documents": [OVERVIEW], "pages": []}
    assert json.loads(_run(monkeypatch, capsys, root, "pages", "--json")) == {"pages": []}


# ---------- a case variant: the overview or a page, never both, never neither ----------


@pytest.mark.parametrize("fs", FILE_SYSTEMS)
@pytest.mark.parametrize("name", ["Readme.md", "readme.md"])
@pytest.mark.parametrize("text", ["x\n", "Covers: src/**\n"])
def test_a_case_variant_is_the_overview_or_a_page_never_both_never_neither(tmp_path, monkeypatch, capsys, fs, name, text):
    root = _repo(tmp_path, {f"{ARCH}/{name}": text, f"{ARCH}/orders.md": "Covers: src/**\n"})
    _on(fs, monkeypatch)
    if fs == "case-insensitive":
        assert (root / OVERVIEW).is_file()  # the stand-in answers for the other spelling
    variant = f"{ARCH}/{name}"
    spellings = {variant, OVERVIEW}

    reads = json.loads(_run(monkeypatch, capsys, root, "reads", "--base", "main", "--json"))
    listed = [pg["file"] for pg in json.loads(_run(monkeypatch, capsys, root, "pages", "--json"))["pages"]]
    printed = _run(monkeypatch, capsys, root, "reads", "--base", "main").splitlines()

    as_document = [d for d in reads["documents"] if d in spellings]
    as_page = [f for f in listed if f in spellings]
    reads_pages = [pg["file"] for pg in reads["pages"] if pg["file"] in spellings]
    as_overview = [d for d in as_document if d not in reads_pages]

    assert len(as_document) == 1, reads  # printed once
    assert [line for line in printed if line in spellings] == as_document
    assert len(as_page) + len(as_overview) == 1, (listed, reads)  # never both, never neither
    if as_page:  # a page: under its own name, given out by reads as a page too
        assert as_page == [variant] and reads_pages == [variant]
    else:  # the overview: printed first, and never among reads' pages
        assert reads["documents"][0] in spellings and not reads_pages
    assert listed.count(f"{ARCH}/orders.md") == 1
