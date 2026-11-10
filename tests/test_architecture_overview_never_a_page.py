"""The overview is never a page (#631, split from #612; spec #611 seam 1):
`workflow index pages` never lists `docs/architecture/README.md`, `reads`
prints it once, as the overview, and a case variant of its name is either the
overview or a page, never both and never neither, on case-sensitive and
case-insensitive file systems alike. Through `cli.main`, on a scratch git
repository; a case-insensitive file system is stood in for by `Path` answering
for any spelling of a name the folder lists.

The one rule that decides it (#632): the overview is the entry the folder lists
as exactly `README.md`, and every other `.md` file directly in it is a page,
with `README.md` and `readme.md` side by side, and with a lone `Readme.md`
where `Path.is_file` answers for `README.md` too. Those tests hold on either
kind of host: a case-sensitive file system is stood in for too, by `Path`
answering only for the spelling the folder lists."""

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
@pytest.mark.parametrize("name", ["Readme.md", "readme.md", "README.MD", "readme.MD"])
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


@pytest.mark.parametrize("fs", FILE_SYSTEMS)
@pytest.mark.parametrize("name", ["orders.MD", "README.txt", "README.md.bak"])
def test_only_the_overview_s_name_is_a_page_with_another_extension_case(tmp_path, monkeypatch, capsys, fs, name):
    """A name that casefolds to `readme.md` is a page whatever its extension's
    case; any other file whose extension isn't exactly `.md` is still none."""
    root = _repo(tmp_path, {f"{ARCH}/{name}": "Covers: src/**\n", f"{ARCH}/notes.md": "Covers: src/**\n"})
    _on(fs, monkeypatch)
    listed = [pg["file"] for pg in json.loads(_run(monkeypatch, capsys, root, "pages", "--json"))["pages"]]
    assert listed == [f"{ARCH}/notes.md"]
    reads = json.loads(_run(monkeypatch, capsys, root, "reads", "--base", "main", "--json"))
    assert reads["documents"] == [f"{ARCH}/notes.md"]


# ---------- one rule for the overview and the pages (#632) ----------
#
# The overview is the entry the folder lists as exactly `README.md`; every
# other `.md` file directly in the folder is a page. Moved from #612 word for
# word: "The overview is never a page: never matched, listed or noted."


def _is_file_ignores_case(monkeypatch):
    """Only `Path.is_file` answers as a case-insensitive file system does: true
    for a name the folder lists under another spelling. The trap #632 closes:
    `(d / "README.md").is_file()` is then true beside a lone `Readme.md`."""
    real = Path.is_file

    def is_file(self):
        if real(self):
            return True
        try:
            return any(e.casefold() == self.name.casefold() and real(self.with_name(e)) for e in os.listdir(self.parent))
        except OSError:
            return False

    monkeypatch.setattr(Path, "is_file", is_file)


def _case_sensitive(monkeypatch, stored=None):
    """Make `Path` answer as a case-sensitive file system does, whatever the
    host's: a name its folder lists only under another spelling isn't there.
    `stored` maps a path to a file kept elsewhere: its folder lists that path
    too, and the path, under its own spelling, is that file. So `readme.md`
    stands beside `README.md`, which a case-insensitive host can't hold."""
    stored = stored or {}
    real = {name: getattr(Path, name) for name in ("iterdir", "is_file", "exists", "stat", "read_text", "open")}

    def elsewhere(p):  # listed, but only under another spelling
        try:
            names = os.listdir(p.parent)
        except OSError:
            return False
        return p.name not in names and any(e.casefold() == p.name.casefold() for e in names)

    def wrap(name):
        def f(self, *a, **k):
            if self in stored:
                return real[name](stored[self], *a, **k)
            if elsewhere(self):
                if name in ("is_file", "exists"):
                    return False
                raise FileNotFoundError(2, "No such file or directory", str(self))
            return real[name](self, *a, **k)
        return f

    def iterdir(self):
        yield from real["iterdir"](self)
        yield from (p for p in stored if p.parent == self)

    for name in real:
        monkeypatch.setattr(Path, name, iterdir if name == "iterdir" else wrap(name))


def test_with_readme_and_a_lower_case_one_readme_is_the_overview_and_the_other_a_page(tmp_path, tmp_path_factory, monkeypatch, capsys):
    """On a case-sensitive file system, stood in for so it holds on any host,
    `README.md` and `readme.md` side by side: `README.md` is the overview
    (printed first, once, never matched or listed) and `readme.md` a page
    (listed once, matched by its globs)."""
    root = _repo(tmp_path, {OVERVIEW: "Covers: src/**\n\n# Architecture\n"})
    lower = f"{ARCH}/readme.md"
    page = tmp_path_factory.mktemp("stored") / "readme.md"
    page.write_text("Covers: src/**\n\nInterface: a page\n")
    _case_sensitive(monkeypatch, {root / lower: page})
    names = sorted(p.name for p in (root / ARCH).iterdir())
    assert names == ["README.md", "readme.md"], names  # the stand-in holds both
    assert (root / OVERVIEW).read_text().endswith("# Architecture\n")
    assert (root / lower).read_text().endswith("Interface: a page\n")

    listed = json.loads(_run(monkeypatch, capsys, root, "pages", "--json"))["pages"]
    assert [pg["file"] for pg in listed] == [lower]
    assert listed[0]["interface"] == "a page"
    text = _run(monkeypatch, capsys, root, "pages")
    assert OVERVIEW not in text and text.count(lower) == 1

    assert _run(monkeypatch, capsys, root, "reads", "--base", "main").splitlines() == [OVERVIEW, lower]
    got = json.loads(_run(monkeypatch, capsys, root, "reads", "--base", "main", "--json"))
    assert got == {"documents": [OVERVIEW, lower], "pages": [{"file": lower, "matched_by": ["src/**"]}]}


@pytest.mark.parametrize("fs", ["case-sensitive", "is_file ignores case", "case-insensitive"])
@pytest.mark.parametrize("text", ["x\n", "Covers: src/**\n"])
def test_a_lone_capitalised_readme_is_printed_exactly_once(tmp_path, monkeypatch, capsys, fs, text):
    """Only `Readme.md`: `reads` prints it exactly once, as a page, on a
    case-sensitive file system and on a case-insensitive one (`Path.is_file`
    patched to ignore case, alone or with the rest of `Path`)."""
    root = _repo(tmp_path, {f"{ARCH}/Readme.md": text})
    if fs == "case-sensitive":
        _case_sensitive(monkeypatch)
    elif fs == "is_file ignores case":
        _is_file_ignores_case(monkeypatch)
    else:
        _case_insensitive(monkeypatch)
    assert (root / OVERVIEW).is_file() == (fs != "case-sensitive")  # each stand-in, on any host
    variant = f"{ARCH}/Readme.md"

    printed = _run(monkeypatch, capsys, root, "reads", "--base", "main").splitlines()
    assert printed == [variant]
    got = json.loads(_run(monkeypatch, capsys, root, "reads", "--base", "main", "--json"))
    assert got == {"documents": [variant], "pages": [{"file": variant, "matched_by": ["src/**"] if "Covers" in text else []}]}
    listed = json.loads(_run(monkeypatch, capsys, root, "pages", "--json"))["pages"]
    assert [pg["file"] for pg in listed] == [variant]
