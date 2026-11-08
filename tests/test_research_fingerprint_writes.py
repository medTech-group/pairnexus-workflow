"""#529: `workflow research fingerprint --saved F --fingerprints F` writes a key
source's saved copy and its fingerprint file from one fetch, both or neither
(spec #505). Seam 1, the `workflow` CLI fed files (with `--fetch` against a
local server); seam 2, the `study` skill's "Saving a key source" and its
examples, tied to what the command writes."""

import json
import os
import re
from datetime import date
from pathlib import Path

import pytest

from conftest import KIT
from test_research_notes import (  # noqa: F401  (fixtures: project, server)
    NOTE,
    PAGE,
    PARAS,
    SKILL,
    URL,
    _check,
    _cli,
    _closed_port,
    _env,
    _h,
    _note,
    _page,
    _shown,
    _snapshot,
    project,
    server,
)
from workflow import research

TOPIC = "docs/research/booking-ahead"
SAVED = f"{TOPIC}/sources/booking-help.md"
FPS = f"{TOPIC}/sources/booking-help.fingerprints"


def _write(project, link, saved, fps, *extra, given=None):
    given = given if given is not None else ["--page", PAGE]
    return _cli("fingerprint", link, *given, "--saved", saved, "--fingerprints", fps, *extra, cwd=project, env=_env(project))


def _want_saved(link: str) -> str:
    """The saved copy the skill shows, as the command writes it: today's
    `Accessed:` date (computed at the point of use), and paragraph 3, which
    the example's session left out by hand, as fetched."""
    lines = _shown(SAVED).replace(URL, link).splitlines()
    lines[1] = f"Accessed: {date.today().isoformat()}"
    lines[lines.index("[left out]")] = PARAS[2]
    return "\n".join(lines) + "\n"


def _want_fps(link: str) -> str:
    return _shown(FPS).replace(URL, link)


def _one_line(p):
    assert p.returncode == 1, (p.stdout, p.stderr)
    assert p.stdout == ""
    assert "Traceback" not in p.stderr
    lines = p.stderr.strip().splitlines()
    assert len(lines) == 1, p.stderr
    return lines[0]


# ---------- writing both files ----------


def test_fingerprint_writes_both_files_from_one_fetch_in_the_skills_layout(project, server):
    base, routes = server
    link = f"{base}/help/booking"
    routes["/help/booking"] = (200, "text/html", PAGE.read_bytes())
    topic = project / "docs/research/booking-new"  # neither the topic's folder nor `sources/` exists yet
    saved, fps = topic / "sources/booking-help.md", topic / "sources/booking-help.fingerprints"
    before = {x[0] for x in _snapshot(project)}
    p = _write(project, link, saved.relative_to(project), fps.relative_to(project), "--json", given=["--fetch"])
    assert p.returncode == 0, p.stderr
    assert fps.read_text(encoding="utf-8") == _want_fps(link)
    assert saved.read_text(encoding="utf-8") == _want_saved(link)
    out = json.loads(p.stdout)
    assert [x["hash"] for x in out["paragraphs"]] == [_h(t) for t in PARAS]
    assert out["saved"] == "docs/research/booking-new/sources/booking-help.md"
    assert out["fingerprints"] == "docs/research/booking-new/sources/booking-help.fingerprints"
    after = {x[0] for x in _snapshot(project)} - before
    assert after == {"docs/research/booking-new", "docs/research/booking-new/sources", *(f"docs/research/booking-new/sources/{n}" for n in ("booking-help.md", "booking-help.fingerprints"))}

    # the two files pass the source check as they are, from the note the skill shows
    note = _shown(f"{TOPIC}/note.md").replace(URL, link)
    (topic / "note.md").write_text(note, encoding="utf-8")
    c = _cli("check", "--note", topic / "note.md", "--fetch", "--json", env=_env(project))
    assert c.returncode == 0, c.stderr
    assert json.loads(c.stdout)["sources"][0]["result"] == "unchanged"


def test_fingerprint_says_what_it_wrote(project):
    p = _write(project, URL, "out/a.md", "out/a.fingerprints")
    assert p.returncode == 0, p.stderr
    assert "out/a.md" in p.stdout and "out/a.fingerprints" in p.stdout
    for i, t in enumerate(PARAS, 1):
        assert f"{i} {_h(t)}" in p.stdout


@pytest.mark.parametrize("fps_folder", ["new/sources", "new", "."], ids=["both-missing", "one-missing-shared-parent", "saved-missing"])
def test_fingerprint_makes_the_folders_it_writes_in(project, fps_folder):
    saved, fps = project / "new/sources/a.md", project / fps_folder / "a.fingerprints"
    p = _write(project, URL, saved, fps)
    assert p.returncode == 0, p.stderr
    assert fps.read_text(encoding="utf-8") == _want_fps(URL)
    assert saved.read_text(encoding="utf-8").startswith(f"Source: {URL}\nAccessed: ")


def test_fingerprint_replaces_files_already_there(project):
    """Saving a key source again writes the page as it is now."""
    saved, fps = project / SAVED, project / FPS
    p = _write(project, URL, saved, fps, given=["--page", _page(project, PARAS[:2])])
    assert p.returncode == 0, p.stderr
    assert fps.read_text(encoding="utf-8") == f"url: {URL}\n1 {_h(PARAS[0])}\n2 {_h(PARAS[1])}\n"
    assert saved.read_text(encoding="utf-8").endswith(f"\n\n{PARAS[0]}\n\n{PARAS[1]}\n")


def test_fingerprint_leaves_sensitive_patterns_out_of_the_saved_copy_not_the_hashes(project, tmp_path):
    paras = ["Your code is BOOKCODE-123456, keep it.", "Plain words."]
    p = _write(project, URL, "s/a.md", "s/a.fingerprints", given=["--page", _page(tmp_path, paras)])
    assert p.returncode == 0, p.stderr
    saved = (project / "s/a.md").read_text(encoding="utf-8")
    assert "BOOKCODE-123456" not in saved + p.stdout
    assert saved.endswith("\n\nYour code is [left out], keep it.\n\nPlain words.\n")
    assert (project / "s/a.fingerprints").read_text(encoding="utf-8") == f"url: {URL}\n1 {_h(paras[0])}\n2 {_h(paras[1])}\n"
    assert "left out 1 match" in p.stderr


def test_the_written_files_round_trip_through_the_layout_reader(project, tmp_path):
    """Whatever the page holds, the saved copy reads back with the same
    paragraphs, so `check` matches each to its hash."""
    paras = ["  Spaces\tand tabs  ", "Line\nbreaks\r\nand separators", "Source: not a header", "url: nor this", "[left out] is text too", "#  a heading?"]
    p = _write(project, URL, "s/a.md", "s/a.fingerprints", given=["--page", _page(tmp_path, paras)])
    assert p.returncode == 0, p.stderr
    url, hashes = research.read_fingerprints((project / "s/a.fingerprints").read_text(encoding="utf-8"), "f")
    src, saved = research.read_saved_copy((project / "s/a.md").read_text(encoding="utf-8"), "s")
    assert url == src == URL
    assert len(saved) == len(hashes) == len(paras)
    for text, h in zip(saved, hashes):
        assert research.LEFT_OUT in text or research.digest(text) == h


# ---------- both or neither ----------


def _files(root: Path):
    """Every file and link under root, with its bytes, inode and times: a file
    written, replaced or put back by a copy shows. Folders by name only, since
    making and removing one inside a folder changes that folder's time."""
    out = []
    for p in sorted(root.rglob("*")):
        st = p.lstat()
        rel = p.relative_to(root).as_posix()
        if p.is_symlink():
            out.append((rel, "link", os.readlink(p)))
        elif p.is_dir():
            out.append((rel, "folder"))
        else:
            out.append((rel, "file", st.st_ino, st.st_mtime_ns, st.st_mode, p.read_bytes()))
    return out


def _in_the_way(project, tmp_path, case: str, name: str) -> str:
    """A target that can't be written, as `case` says, under project/blocked/,
    as the person would type it."""
    blocked = project / "blocked"
    blocked.mkdir(exist_ok=True)
    if case == "a-folder-in-the-way":
        (blocked / name).mkdir()
        return str(blocked / name)
    if case == "a-file-in-the-way":
        (blocked / "a-file").write_text("x")
        return str(blocked / "a-file" / name)
    if case == "a-name-too-long":
        return str(blocked / "deeper" / ("x" * 300 + name))
    if case == "a-dangling-link":
        (blocked / name).symlink_to(tmp_path / "nowhere" / name)
        return str(blocked / name)
    if case == "a-link-to-a-file":
        (tmp_path / "elsewhere").write_text("x")
        (blocked / name).symlink_to(tmp_path / "elsewhere")
        return str(blocked / name)
    if case == "a-path-given-as-a-folder":
        return str(blocked / "deeper" / name) + "/"
    if case == "a-dot":
        return str(blocked / "deeper") + "/."
    raise AssertionError(case)


CASES = ["a-folder-in-the-way", "a-file-in-the-way", "a-name-too-long", "a-dangling-link", "a-link-to-a-file", "a-path-given-as-a-folder", "a-dot"]


@pytest.mark.parametrize("which", ["saved", "fingerprints"])
@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("other_there", [False, True], ids=["other-new", "other-there"])
def test_a_file_it_cant_write_leaves_both_as_they_were(project, tmp_path, case, which, other_there):
    bad = _in_the_way(project, tmp_path, case, "a.fingerprints" if which == "fingerprints" else "a.md")
    if other_there:  # re-saving a key source: the other file's old version is kept
        other = project / ("old/a.md" if which == "fingerprints" else "old/a.fingerprints")
        other.parent.mkdir()
        other.write_text("the old version\n")
    else:
        other = project / ("new/sources/a.md" if which == "fingerprints" else "new/sources/a.fingerprints")
    saved, fps = (str(other), bad) if which == "fingerprints" else (bad, str(other))
    before = _files(project)  # the project is tmp_path: where a link points is inside it
    line = _one_line(_write(project, URL, saved, fps))
    assert "can't write" in line and bad in line
    assert "neither file was written" in line
    assert _files(project) == before  # no file written or changed, no folder it made left behind


def _cant_write_list(text: str) -> list[str]:
    """The list of files it can't write, "(a folder in its way, …)", as items."""
    flat = re.sub(r"\s+", " ", text)
    start = flat.index("(a folder in its way")
    return flat[start + 1 : flat.index(")", start)].split(", ")


def test_a_symbolic_link_is_named_so_in_the_skill_the_changelog_and_the_message(project, tmp_path):
    """A "link" is the page's web address everywhere in the kit, so a path
    that is a symbolic link is called a symbolic link."""
    log = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    entry = log[log.index("(#529, split out of #506") :]
    for text in (_section(SKILL.read_text(encoding="utf-8")), entry[: entry.index("\n\n")]):
        items = _cant_write_list(text)
        assert "a symbolic link" in items and "a link" not in items, items
    for case in ("a-dangling-link", "a-link-to-a-file"):
        bad = _in_the_way(project, tmp_path, case, f"{case}.md")
        line = _one_line(_write(project, URL, bad, "new/a.fingerprints"))
        assert "it is a symbolic link" in line, line


def test_a_failure_writing_the_second_file_puts_the_first_back(project, tmp_path, monkeypatch):
    """Both files are in place before either replaces what was there; when
    putting the second in place fails, the first is put back as it was."""
    (project / "old").mkdir()
    first, second = project / "old/a.md", project / "new/deep/a.fingerprints"
    first.write_text("the old version\n")
    before = _files(project)
    real = os.replace
    calls = []

    def fake(src, dst):
        calls.append((Path(src), Path(dst)))
        if Path(dst) == second:
            raise OSError(5, "Input/output error", str(dst))
        return real(src, dst)

    monkeypatch.setattr(research.os, "replace", fake)
    with pytest.raises(research.WriteError) as e:
        research.write_files([(first, "new saved copy\n"), (second, "url: x\n1 " + "0" * 64 + "\n")])
    monkeypatch.undo()
    assert e.value.path == second and "Input/output error" in str(e.value)
    assert any(dst == first for _, dst in calls)  # the first had been put in place
    assert _files(project) == before  # and was put back, inode and all; no temporary file or folder left


def _failing_replace(monkeypatch, fail: set[int]):
    """os.replace in `research`, failing on the calls numbered in `fail`."""
    real = os.replace
    n = [0]

    def fake(src, dst):
        n[0] += 1
        if n[0] in fail:
            raise OSError(5, "Input/output error", str(dst))
        return real(src, dst)

    monkeypatch.setattr(research.os, "replace", fake)


@pytest.mark.parametrize(
    "there, fail, lost",
    [
        (["a.md"], {2, 3}, "a.md"),  # placing the new fingerprints fails, then putting the old saved copy back
        (["a.md", "a.fingerprints"], {2, 3}, "a.fingerprints"),
        (["a.md", "a.fingerprints"], {2, 4}, "a.md"),
    ],
    ids=["saved-there", "both-there-fingerprints-not-put-back", "both-there-saved-not-put-back"],
)
def test_an_old_file_that_cant_be_put_back_is_kept_and_named(project, monkeypatch, there, fail, lost):
    """When putting an old file back fails too, the old file moved aside is the
    only copy of it: it is kept, never removed, and the error names it."""
    folder = project / "old"
    folder.mkdir()
    for name in there:
        (folder / name).write_text(f"the old {name}\n")
    saved, fps = folder / "a.md", folder / "a.fingerprints"
    _failing_replace(monkeypatch, fail)
    with pytest.raises(research.WriteError) as e:
        research.write_files([(saved, "new\n"), (fps, "url: x\n")])
    monkeypatch.undo()
    assert e.value.path == fps
    assert any(p.read_text() == f"the old {lost}\n" for p in folder.iterdir())  # the old version is still on disk
    assert [p for p, _ in e.value.kept] == [folder / lost]
    kept = e.value.kept[0][1]
    assert kept.read_text() == f"the old {lost}\n"
    for name in there:  # each old file is still on disk, in place or kept aside
        if name != lost:
            assert (folder / name).read_text() == f"the old {name}\n"
    aside = [p for p in folder.iterdir() if p.name not in ("a.md", "a.fingerprints")]
    assert aside == [kept]  # no temporary file left, and only the old file named kept aside


def test_the_line_for_an_old_file_kept_names_it(project, monkeypatch, capsys):
    from workflow import cli

    folder = project / "old"
    folder.mkdir()
    (folder / "a.md").write_text("the old version\n")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    monkeypatch.chdir(project)
    _failing_replace(monkeypatch, {2, 3})
    code = cli.main(["research", "fingerprint", URL, "--page", str(PAGE), "--saved", "old/a.md", "--fingerprints", "old/a.fingerprints"])
    monkeypatch.undo()
    out, err = capsys.readouterr()
    assert code == 1 and out == ""
    [line] = err.strip().splitlines()
    kept = [p for p in folder.iterdir() if p.name != "a.md"]
    assert len(kept) == 1 and kept[0].read_text() == "the old version\n"
    assert "old/a.md" in line and kept[0].name in line
    assert "neither file was written" not in line


@pytest.mark.parametrize("when", ["writing", "placing"])
def test_any_other_exception_undoes_everything_and_is_raised_again(project, monkeypatch, when):
    """Not only an OSError: a text that can't be written in UTF-8, or an
    interrupt while the files are put in place, leaves both as they were."""
    (project / "old").mkdir()
    saved, fps = project / "old/a.md", project / "new/deep/a.fingerprints"
    saved.write_text("the old version\n")
    before = _files(project)
    if when == "writing":  # a lone surrogate
        files, raised = [(saved, "new\n"), (fps, "url: https://example.com/caf\udce9\n")], UnicodeEncodeError
    else:
        real = os.replace

        def fake(src, dst):
            if Path(dst) == fps:
                raise KeyboardInterrupt
            return real(src, dst)

        monkeypatch.setattr(research.os, "replace", fake)
        files, raised = [(saved, "new\n"), (fps, "url: x\n")], KeyboardInterrupt
    with pytest.raises(raised):
        research.write_files(files)
    monkeypatch.undo()
    assert _files(project) == before


def test_a_failure_writing_the_second_new_file_removes_the_first(project, monkeypatch):
    first, second = project / "n1/a.md", project / "n2/a.fingerprints"
    before = _files(project)
    real = os.replace
    monkeypatch.setattr(research.os, "replace", lambda s, d: (_ for _ in ()).throw(OSError(28, "No space left on device", str(d))) if Path(d) == second else real(s, d))
    with pytest.raises(research.WriteError) as e:
        research.write_files([(first, "a\n"), (second, "b\n")])
    monkeypatch.undo()
    assert e.value.path == second
    assert _files(project) == before


@pytest.mark.parametrize("fail", ["open", "makedirs"])
def test_a_failure_before_anything_is_in_place_leaves_nothing(project, monkeypatch, fail):
    first, second = project / "n1/x/a.md", project / "n2/y/a.fingerprints"
    before = _files(project)
    if fail == "open":
        real_open = open

        def fake_open(f, *a, **k):
            if isinstance(f, int):  # the second temporary file, by its descriptor
                fake_open.n += 1
                if fake_open.n == 2:
                    os.close(f)
                    raise OSError(28, "No space left on device")
            return real_open(f, *a, **k)

        fake_open.n = 0
        monkeypatch.setattr(research, "open", fake_open, raising=False)
    else:
        real_mkdir = os.mkdir

        def fake_mkdir(p, *a, **k):
            if Path(p).name == "y":
                raise OSError(13, "Permission denied", str(p))
            return real_mkdir(p, *a, **k)

        monkeypatch.setattr(research.os, "mkdir", fake_mkdir)
    with pytest.raises(research.WriteError):
        research.write_files([(first, "a\n"), (second, "b\n")])
    monkeypatch.undo()
    assert _files(project) == before


def test_a_written_file_keeps_the_mode_of_the_file_it_replaces(project):
    f = project / "old/a.md"
    f.parent.mkdir()
    f.write_text("x")
    f.chmod(0o640)
    research.write_files([(f, "new\n"), (project / "old/a.fingerprints", "fp\n")])
    assert f.read_text() == "new\n" and (f.stat().st_mode & 0o777) == 0o640
    umask = os.umask(0)
    os.umask(umask)
    assert ((project / "old/a.fingerprints").stat().st_mode & 0o777) == (0o666 & ~umask)


# ---------- refused before anything is fetched or written ----------


def _refused_early(project, *args):
    """Refused before it reads the page or fetches the link: the page is
    missing and the link's port is closed, so either would say "can't"."""
    link = f"http://127.0.0.1:{_closed_port()}/help/booking"
    before = _snapshot(project)
    p = _cli("fingerprint", link, *args, cwd=project, env=_env(project))
    assert "can't fetch" not in p.stderr and "can't read" not in p.stderr
    assert _snapshot(project) == before
    return p


@pytest.mark.parametrize("how", [["--fetch"], ["--page", "missing.html"]], ids=["fetch", "page"])
def test_a_link_holding_sensitive_data_is_refused_before_anything_is_fetched_or_written(project, how):
    link = f"http://127.0.0.1:{_closed_port()}/help?code=BOOKCODE-123456"
    before = _snapshot(project)
    p = _cli("fingerprint", link, *how, "--saved", "new/a.md", "--fingerprints", "new/a.fingerprints", cwd=project, env=_env(project))
    assert p.returncode == 1 and p.stdout == ""
    assert "sensitive data" in p.stderr and "can't" not in p.stderr
    assert "BOOKCODE-123456" not in p.stderr
    assert _snapshot(project) == before


@pytest.mark.parametrize("given", [["--saved", "new/a.md"], ["--fingerprints", "new/a.fingerprints"]], ids=["saved-only", "fingerprints-only"])
def test_one_file_without_the_other_is_refused(project, given):
    p = _refused_early(project, "--fetch", *given)
    assert p.returncode == 2 and p.stdout == ""
    assert "--saved" in p.stderr and "--fingerprints" in p.stderr


def test_a_fingerprint_file_not_named_fingerprints_is_refused(project):
    line = _one_line(_refused_early(project, "--fetch", "--saved", "new/a.md", "--fingerprints", "new/a.txt"))
    assert "new/a.txt" in line and ".fingerprints" in line


@pytest.mark.parametrize("saved", ["t/v/a.fingerprints", "t/v/A.FINGERPRINTS", "t/v/a.Fingerprints"])
def test_a_saved_copy_named_as_a_fingerprint_file_is_refused(project, saved):
    """`check` takes a file named `*.fingerprints` in the topic's folder for a
    fingerprint file, so a saved copy named so would fail it."""
    line = _one_line(_refused_early(project, "--fetch", "--saved", saved, "--fingerprints", "t/v/b.fingerprints"))
    assert saved in line and ".fingerprints" in line


def test_a_saved_copy_whose_name_only_holds_fingerprints_is_written(project):
    p = _write(project, URL, "t/v/a.fingerprints.md", "t/v/a.fingerprints")
    assert p.returncode == 0, p.stderr
    assert (project / "t/v/a.fingerprints.md").read_text(encoding="utf-8").startswith(f"Source: {URL}\n")


@pytest.mark.parametrize("fps", ["new/a.fingerprints", "new/../new/a.fingerprints", "./new/a.fingerprints"])
def test_both_options_naming_one_file_is_refused(project, fps):
    line = _one_line(_refused_early(project, "--fetch", "--saved", "new/a.fingerprints", "--fingerprints", fps))
    assert "same file" in line


def test_a_page_it_cant_fetch_writes_nothing(project, server):
    base, routes = server
    routes["/x"] = (200, "application/pdf", b"%PDF-1.4")
    before = _snapshot(project)
    p = _cli("fingerprint", f"{base}/x", "--fetch", "--saved", "new/a.md", "--fingerprints", "new/a.fingerprints", cwd=project, env=_env(project))
    assert p.returncode == 1 and "can't fetch" in p.stderr
    assert _snapshot(project) == before


def test_without_the_two_options_it_still_writes_nothing(project, tmp_path):
    before = _snapshot(project)
    p = _cli("fingerprint", URL, "--page", PAGE, "--json", cwd=project, env=_env(project))
    assert p.returncode == 0, p.stderr
    assert "saved" not in json.loads(p.stdout)
    assert _snapshot(project) == before


# ---------- seam 2: the study skill names the command ----------


def _section(text: str) -> str:
    start = text.index("**Saving a key source.**")
    return text[start : text.index("**The fingerprint file**", start)]


def test_the_study_skill_names_the_command_that_writes_both_files():
    section = _section(SKILL.read_text(encoding="utf-8"))
    cmd = re.search(r"```\n(WF research fingerprint [^\n]*)\n```", section)
    assert cmd, "the section shows the command in a fenced block"
    assert cmd.group(1) == f"WF research fingerprint <link> --fetch --saved {TOPIC.replace('booking-ahead', '<topic>')}/sources/<name>.md --fingerprints {TOPIC.replace('booking-ahead', '<topic>')}/sources/<name>.fingerprints"
    flat = re.sub(r"\s+", " ", section)
    assert "making their folders when missing" in flat
    assert "both or neither" in flat
    assert "personal details" in flat  # still left out by hand, after it writes
    assert "It writes nothing." not in flat


def test_the_skills_command_run_with_its_examples_paths_writes_its_examples(project, server):
    """The skill's command, with `<topic>` and `<name>` its example's, writes
    the saved copy and fingerprint file the skill shows."""
    base, routes = server
    link = f"{base}/help/booking"
    routes["/help/booking"] = (200, "text/html", PAGE.read_bytes())
    cmd = re.search(r"```\n(WF research fingerprint [^\n]*)\n```", _section(SKILL.read_text(encoding="utf-8"))).group(1)
    args = cmd.replace("<topic>", "booking-ahead").replace("<name>", "booking-help").split()[3:]
    args[args.index("<link>")] = link
    p = _cli("fingerprint", *args, cwd=project, env=_env(project))
    assert p.returncode == 0, p.stderr
    assert (project / FPS).read_text(encoding="utf-8") == _want_fps(link)
    assert (project / SAVED).read_text(encoding="utf-8") == _want_saved(link)
    # with paragraph 3 left out by hand, as the skill's example is, the source check passes
    saved = project / SAVED
    saved.write_text(saved.read_text(encoding="utf-8").replace(PARAS[2], "[left out]"), encoding="utf-8")
    (project / TOPIC / "note.md").write_text(_shown(f"{TOPIC}/note.md").replace(URL, link), encoding="utf-8")
    c = _check(project, extra=["--fetch"])
    assert c.returncode == 0, c.stderr
    assert json.loads(c.stdout)["sources"][0]["result"] == "unchanged"


def test_the_third_party_line_is_the_skills():
    third = next(l for l in _shown(SAVED).splitlines() if l.startswith("Third-party text:"))
    assert research.THIRD_PARTY == third


def test_the_changelog_notes_it_under_unreleased():
    log = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    unreleased = log[log.index("## Unreleased") : log.index("\n## ", log.index("## Unreleased") + 1)]
    assert "(#529, split out of #506, part of spec #505)" in unreleased
