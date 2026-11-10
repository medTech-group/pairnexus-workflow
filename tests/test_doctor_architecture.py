"""#615: doctor's architecture notes (spec #611, seam 2: doctor's lines from
`Inputs`). `kit.architecture.uncovered`, `.unmatched` and `.no_covers` read
the checkout's `docs/architecture/` and its tracked files; `.missing` notes a
set-up plugin-mode project whose `project.rules` doesn't list the overview.
The old-Python short report gives the same ids, and `profile check` warns
when the protected or code paths match `docs/architecture/`. Built in-process
on a scratch git repository, as test_check_setup.py builds `Inputs`."""

import contextlib
import io
import json
import os
import subprocess
import sys

import pytest

from changelog_notes import since_0110
from conftest import KIT
from workflow import _old_python, cli, doctor, profile

IDS = ("kit.architecture.uncovered", "kit.architecture.unmatched", "kit.architecture.no_covers")
MISSING = "kit.architecture.missing"
ARCH = (doctor.check_architecture_overview, doctor.check_architecture)
HEAD = '[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "someone"\nruleset = true\n'
TAIL = '[run]\nticket_environment = "t"\nconductor_environment = "c"\n'
OVERVIEW_RULES = 'rules = ["CLAUDE.md", "docs/architecture/README.md"]\n'


def _prof(project="", guard=""):
    return HEAD + project + TAIL + (f"[guard]\n{guard}" if guard else "")


def _env():
    return {k: v for k, v in os.environ.items() if k != "WORKFLOW_EXPERIENCE"}


def _repo(tmp_path, files, prof=None, vendored=True, untracked=()):
    """A scratch checkout holding `files` (path: text), tracked with
    `git add`; `untracked` files are written after it."""
    root = tmp_path / "proj"
    root.mkdir(parents=True)
    (root / ".claude/workflow").mkdir(parents=True)
    (root / ".claude/workflow/profile.toml").write_text(_prof() if prof is None else prof)
    if vendored:
        (root / ".claude/workflow/lock.json").write_text(json.dumps({"kit_version": "0.1.11", "files": {}}))
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    for rel in untracked:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("x\n")
    return root


def _inputs(root, environ=None, **kw):
    environ = _env() if environ is None else environ
    prof, error = cli._read_profile(root)  # as `workflow doctor` reads it
    return doctor.Inputs(root=root, kit_root=KIT, profile=prof, profile_error=error,
                         experience=profile.resolve_experience(root, None, environ=environ), environ=environ, **kw)


def _lines(root, checks=ARCH, **kw):
    return {ln.id: ln for ln in doctor.report(_inputs(root, **kw), list(checks)).lines if ln.id.startswith("kit.architecture")}


def _said(ln):
    return ln.message.new + " " + ln.message.developer


# ---------- no folder ----------


def test_no_folder_gives_no_lines_in_a_vendored_project(tmp_path):
    root = _repo(tmp_path, {"src/orders/check.py": "x\n"})
    assert _lines(root) == {}


def test_the_checks_are_in_checks_and_local_checks_in_the_kit_group():
    for check in ARCH:
        assert check in doctor.CHECKS and check in doctor.LOCAL_CHECKS
        assert check.group == "The kit"
    assert doctor.check_architecture.id == "kit.architecture.uncovered"
    assert doctor.check_architecture_overview.id == MISSING


# ---------- all fine ----------


def test_a_folder_with_nothing_wrong_gives_a_fine_line_for_each(tmp_path):
    root = _repo(tmp_path, {
        "src/orders/check.py": "x\n",
        "docs/architecture/README.md": "# Architecture\n",
        "docs/architecture/orders.md": "Covers: src/orders/**\nInterface: check(order)\n",
    })
    got = _lines(root)
    assert set(got) == set(IDS)
    assert all(ln.status == "fine" for ln in got.values())


def test_an_empty_folder_gives_fine_lines(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n"})
    (root / "docs/architecture").mkdir(parents=True)
    got = _lines(root)
    assert set(got) == set(IDS)
    assert got["kit.architecture.uncovered"].status == "note"  # src/a.py: no page covers it
    assert got["kit.architecture.unmatched"].status == "fine" and got["kit.architecture.no_covers"].status == "fine"


# ---------- uncovered code ----------


def test_uncovered_code_is_a_note_with_its_count_and_first_10_files(tmp_path):
    files = {f"src/m{n:02}/a.py": "x\n" for n in range(12)}
    files.update({"src/orders/check.py": "x\n", "docs/architecture/orders.md": "Covers: src/orders/**\n"})
    root = _repo(tmp_path, files)
    ln = _lines(root)["kit.architecture.uncovered"]
    assert ln.status == "note" and ln.offer is None
    for said in (ln.message.new, ln.message.developer):
        assert "12" in said
        for n in range(10):
            assert f"src/m{n:02}/a.py" in said
        assert "src/m10/a.py" not in said and "src/m11/a.py" not in said
        assert "2 more" in said
        assert "src/orders/check.py" not in said
    assert ln.fix.new and ln.fix.developer


def test_without_code_paths_code_is_tracked_files_outside_docs_and_the_protected_paths(tmp_path):
    root = _repo(tmp_path, {
        "src/app.py": "x\n",
        "docs/guide/example.py": "x\n",  # under docs/
        ".github/workflows/ci.yml": "x\n",  # protected by default
        "config/.env": "SECRET=x\n",  # protected by default
        "setup.py": "x\n",  # at the root
        "Makefile": "x\n",  # at the root
        "rules/house.md": "# House\n",  # a project.rules document
        "src/test_app.py": "x\n",  # a test path
        "pkg/app_test.go": "x\n",  # a test path
        "docs/architecture/README.md": "# Architecture\n",
    }, prof=_prof('rules = ["CLAUDE.md", "rules/house.md#safety"]\n'), untracked=("src/untracked.py",))
    ln = _lines(root)["kit.architecture.uncovered"]
    said = _said(ln)
    assert ln.status == "note" and "src/app.py" in said
    for never in ("docs/guide/example.py", ".github/workflows/ci.yml", "config/.env", "setup.py", "Makefile", "rules/house.md",
                  "src/test_app.py", "pkg/app_test.go", "src/untracked.py", ".claude/workflow/profile.toml", "docs/architecture/README.md"):
        assert never not in said, never
    assert " 1 " in f" {ln.message.developer} "  # one file


def test_with_code_paths_code_is_only_the_code_paths(tmp_path):
    root = _repo(tmp_path, {
        "app/orders.py": "x\n",
        "app/test_orders.py": "x\n",  # a test path inside the code paths
        "tools/build.py": "x\n",  # outside the code paths
        "main.py": "x\n",  # at the root, though the code paths match it
        "docs/architecture/README.md": "# Architecture\n",
    }, prof=_prof(guard='code_paths = ["app/**", "main.py"]\n'))
    ln = _lines(root)["kit.architecture.uncovered"]
    said = _said(ln)
    assert ln.status == "note" and "app/orders.py" in said
    for never in ("app/test_orders.py", "tools/build.py", "main.py"):
        assert never not in said, never


def test_the_overviews_covers_lines_cover_nothing(tmp_path):
    root = _repo(tmp_path, {
        "src/app.py": "x\n",
        "docs/architecture/README.md": "Covers: src/**\n\n# Architecture\n",
    })
    got = _lines(root)
    assert got["kit.architecture.uncovered"].status == "note" and "src/app.py" in _said(got["kit.architecture.uncovered"])
    assert got["kit.architecture.unmatched"].status == "fine"
    assert got["kit.architecture.no_covers"].status == "fine"


def test_a_glob_crossing_folders_covers_as_the_guard_matches(tmp_path):
    root = _repo(tmp_path, {
        "src/a/b/c.py": "x\n",
        "src/[id]/view.py": "x\n",
        "docs/architecture/src.md": "Covers: src/a/*\nCovers: src/[[]id]/*\n",
    })
    got = _lines(root)
    assert got["kit.architecture.uncovered"].status == "fine"


# ---------- pages that match nothing, or cover nothing ----------


def test_a_page_matching_no_tracked_file_is_a_note(tmp_path):
    root = _repo(tmp_path, {
        "src/orders/check.py": "x\n",
        "docs/architecture/orders.md": "Covers: src/orders/**\n",
        "docs/architecture/payments.md": "Covers: src/payments/**\nCovers: lib/pay/*\n",
    }, untracked=("src/payments/new.py",))
    got = _lines(root)
    ln = got["kit.architecture.unmatched"]
    assert ln.status == "note"
    assert "docs/architecture/payments.md" in ln.message.new and "docs/architecture/payments.md" in ln.message.developer
    assert "orders.md" not in _said(ln)
    assert ln.fix.new and ln.fix.developer


def test_the_unmatched_note_says_a_change_adding_a_matching_file_reads_the_page(tmp_path):
    # `workflow index reads` gives a page whose `Covers:` matches a file a change adds, so a page
    # written ahead of its code is read by the change that writes that code.
    root = _repo(tmp_path, {"src/orders/a.py": "x\n", "docs/architecture/payments.md": "Covers: src/payments/**\n"})
    ln = _lines(root)["kit.architecture.unmatched"]
    assert ln.status == "note"
    assert "ever reads" not in _said(ln)
    assert "only a change that adds" in ln.message.new.lower() and "adding" in ln.message.developer
    assert "isn't written yet" in ln.fix.new and "not written yet" in ln.fix.developer


def test_a_page_matched_by_one_of_its_globs_is_matched(tmp_path):
    root = _repo(tmp_path, {
        "src/orders/check.py": "x\n",
        "docs/architecture/orders.md": "Covers: src/gone/**\nCovers: src/orders/**\n",
    })
    assert _lines(root)["kit.architecture.unmatched"].status == "fine"


def test_a_page_with_no_covers_line_is_a_note_and_the_overview_gets_none(tmp_path):
    root = _repo(tmp_path, {
        "src/orders/check.py": "x\n",
        "docs/architecture/README.md": "# Architecture\n\nNo Covers here.\n",
        "docs/architecture/orders.md": "Covers: src/orders/**\n",
        "docs/architecture/later.md": "# Later\n\nInterface: none yet\n",
        "docs/architecture/sub/deep.md": "# Not a page\n",  # in a subfolder: not a page
        "docs/architecture/notes.txt": "not a page\n",  # not .md
    })
    got = _lines(root)
    ln = got["kit.architecture.no_covers"]
    assert ln.status == "note"
    said = _said(ln)
    assert "docs/architecture/later.md" in said
    for never in ("README.md", "orders.md", "deep.md", "notes.txt"):
        assert never not in said, never
    assert got["kit.architecture.unmatched"].status == "fine"  # a page with no Covers: isn't also unmatched
    assert ln.fix.new and ln.fix.developer


# ---------- what can't be read ----------


def test_without_git_the_walk_cant_check_and_the_pages_are_still_read(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n", "docs/architecture/later.md": "# Later\n"})
    got = _lines(root, environ={**_env(), "PATH": str(tmp_path / "no-bin")})
    assert got["kit.architecture.uncovered"].status == "cant_check"
    assert got["kit.architecture.unmatched"].status == "cant_check"
    assert got["kit.architecture.no_covers"].status == "note"
    for id_ in ("kit.architecture.uncovered", "kit.architecture.unmatched"):
        ln = got[id_]
        assert "git isn't on the PATH" in ln.message.developer
        assert "git" in ln.fix.new and "install" in ln.fix.new.lower()


def test_a_tracked_name_that_isnt_utf8_is_still_walked(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n", "docs/architecture/a.md": "Covers: src/a.py\n"})
    fd = os.open(os.fsencode(root / "src") + b"/caf\xe9.py", os.O_WRONLY | os.O_CREAT)
    os.close(fd)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    got = _lines(root)
    ln = got["kit.architecture.uncovered"]
    assert ln.status == "note"
    for said in (ln.message.new, ln.message.developer):
        assert "src/caf�.py" in said and "src/a.py" not in said
    assert got["kit.architecture.unmatched"].status == "fine"


def test_outside_a_git_checkout_the_walk_says_what_git_said(tmp_path):
    root = tmp_path / "proj"
    (root / ".claude/workflow").mkdir(parents=True)
    (root / ".claude/workflow/profile.toml").write_text(_prof())
    (root / ".claude/workflow/lock.json").write_text(json.dumps({"kit_version": "0.1.11", "files": {}}))
    (root / "docs/architecture").mkdir(parents=True)
    (root / "docs/architecture/a.md").write_text("Covers: src/**\n")
    got = _lines(root, environ={**_env(), "GIT_CEILING_DIRECTORIES": str(tmp_path)})
    for id_ in ("kit.architecture.uncovered", "kit.architecture.unmatched"):
        ln = got[id_]
        assert ln.status == "cant_check"
        assert "not a git repository" in ln.message.new and "not a git repository" in ln.message.developer
        assert "exit 128" not in _said(ln)
        assert "checkout" in ln.fix.new and "install" not in ln.fix.new.lower()


def test_when_git_takes_too_long_the_fix_isnt_to_install_it(tmp_path, monkeypatch):
    root = _repo(tmp_path, {"src/a.py": "x\n", "docs/architecture/a.md": "Covers: src/**\n"})
    monkeypatch.setattr(doctor, "_run", lambda *a, **k: doctor.Ran("timeout"))
    got = _lines(root)
    for id_ in ("kit.architecture.uncovered", "kit.architecture.unmatched"):
        ln = got[id_]
        assert ln.status == "cant_check" and "too long" in ln.message.new
        for fix in (ln.fix.new, ln.fix.developer):
            assert "install" not in fix.lower() and "PATH" not in fix and "checkout" not in fix


def test_without_a_profile_uncovered_cant_check(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n", "docs/architecture/a.md": "Covers: src/**\n"})
    (root / ".claude/workflow/profile.toml").unlink()
    got = _lines(root)
    assert got["kit.architecture.uncovered"].status == "cant_check"
    assert got["kit.architecture.unmatched"].status == "fine" and got["kit.architecture.no_covers"].status == "fine"


# ---------- plugin mode: the overview missing ----------


def test_a_set_up_plugin_project_without_the_overview_in_its_rules_gets_the_note_and_offer(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n"}, vendored=False)
    got = _lines(root)
    assert set(got) == {MISSING}  # no folder: none of the other three
    ln = got[MISSING]
    assert ln.status == "note" and ln.offer == "write_architecture_overview"
    assert doctor.OFFERS["write_architecture_overview"] == "Write the architecture overview"
    assert "Write the architecture overview" in ln.fix.new and "Write the architecture overview" in ln.fix.developer
    assert "docs/architecture/README.md" in _said(ln)


@pytest.mark.parametrize("rules", [OVERVIEW_RULES, 'rules = ["./docs/architecture/README.md#cross-cutting-rules"]\n'])
def test_a_plugin_project_listing_the_overview_gets_no_missing_line(tmp_path, rules):
    root = _repo(tmp_path, {"src/a.py": "x\n"}, prof=_prof(rules), vendored=False)
    assert MISSING not in _lines(root)


def test_a_vendored_project_never_gets_the_missing_line(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n", "docs/architecture/a.md": "Covers: src/**\n"})
    assert MISSING not in _lines(root)


def test_a_plugin_project_not_set_up_gets_no_missing_line(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n"}, vendored=False)
    (root / ".claude/workflow/profile.toml").unlink()
    assert MISSING not in _lines(root)


BROKEN = '[project]\nname = "x"\nbogus = [\n'  # doesn't parse


def test_a_plugin_project_whose_profile_cant_be_read_cant_check_the_overview(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n"}, prof=BROKEN, vendored=False)
    ln = _lines(root)[MISSING]
    assert ln.status == "cant_check" and ln.fix == doctor.PROFILE_FIRST and ln.offer is None


def test_a_vendored_project_whose_profile_cant_be_read_gets_no_missing_line(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n"}, prof=BROKEN)
    assert MISSING not in _lines(root)


def test_a_plugin_project_with_the_folder_gets_all_four(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n", "docs/architecture/a.md": "Covers: src/**\n"}, vendored=False)
    assert set(_lines(root)) == {MISSING, *IDS}


# ---------- `workflow status` never runs the walk ----------


def test_gaps_only_never_runs_the_walk(tmp_path, monkeypatch):
    root = _repo(tmp_path, {"src/a.py": "x\n", "docs/architecture/later.md": "# Later\n"}, vendored=False)
    ran = []
    monkeypatch.setattr(doctor, "_run", lambda *a, **k: ran.append(a) or doctor.Ran("missing"))
    monkeypatch.setattr(doctor.architecture_mod, "pages", lambda *a, **k: ran.append(a) or [])
    r = doctor.report(_inputs(root, gaps_only=True), list(ARCH))
    assert r.lines == [] and ran == []


def test_workflow_status_gives_no_architecture_lines(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n", "docs/architecture/later.md": "# Later\n"}, vendored=False)
    # No `gh` or `git` on the PATH: status reads nothing from GitHub, and the walk would need git.
    env = {**_env(), "CLAUDE_PROJECT_DIR": str(root), "WORKFLOW_UPDATE_CHECK": "off", "HOME": str(tmp_path / "home"),
           "PATH": str(tmp_path / "no-bin")}
    p = subprocess.run([sys.executable, "-B", str(KIT / "scripts/workflow.py"), "status", "--json"], cwd=root, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert "kit.architecture" not in p.stdout


# ---------- the old-Python short report ----------


def _old_ids(root):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = _old_python.main(["doctor", "--json"], stdin_text="", env={"CLAUDE_PROJECT_DIR": str(root)}, version="3.9.6", cwd=root)
    assert code == 0, err.getvalue()
    return {ln["id"] for ln in json.loads(out.getvalue())["lines"] if ln["id"].startswith("kit.architecture")}


ARCH_FILES = {"src/a.py": "x\n", "docs/architecture/a.md": "Covers: src/**\n"}


@pytest.mark.parametrize("vendored", [True, False])
@pytest.mark.parametrize("folder", [True, False])
@pytest.mark.parametrize("rules", ["", OVERVIEW_RULES, "rules = [\n  \"CLAUDE.md\",\n  'docs/architecture/README.md',\n]\n"])
def test_the_short_report_gives_the_same_ids_as_doctor(tmp_path, vendored, folder, rules):
    root = _repo(tmp_path, ARCH_FILES if folder else {"src/a.py": "x\n"}, prof=_prof(rules), vendored=vendored)
    full = set(_lines(root))
    assert _old_ids(root) == full
    assert (MISSING in full) == (not vendored and not rules)
    assert (set(IDS) <= full) == folder


@pytest.mark.parametrize("vendored", [True, False])
def test_the_short_report_gives_the_same_ids_as_doctor_when_the_profile_cant_be_read(tmp_path, vendored):
    root = _repo(tmp_path, {"src/a.py": "x\n"}, prof=BROKEN, vendored=vendored)
    assert _old_ids(root) == set(_lines(root)) == (set() if vendored else {MISSING})


def test_the_short_report_gives_no_missing_line_without_a_profile(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n"}, vendored=False)
    (root / ".claude/workflow/profile.toml").unlink()
    assert _old_ids(root) == set(_lines(root)) == set()


@pytest.mark.parametrize("rules, listed", [
    ('rules = [\n  "CLAUDE.md",\n  # "docs/architecture/README.md",\n]\n', False),  # in a comment: not listed
    ("rules = [\"CLAUDE.md\"] # 'docs/architecture/README.md'\n", False),
    ('rules = ["docs/rules[v2].md", "docs/architecture/README.md"]\n', True),  # a `]` inside a string
    ("rules = ['docs/a]b.md', # a ] in a comment\n  \"docs/architecture/README.md\",\n]\n", True),
    ('rules = ["docs/a\\"]b.md", "docs/architecture/README.md"]\n', True),  # an escaped quote
    ('rules = ["CLAUDE.md"]\nother = ["docs/architecture/README.md"]\n', False),  # after the array's end
    ("rules = ['''docs/architecture/README.md''']\n", True),
    ('rules = ["docs/architecture/README\\u002emd"]\n', True),
    ('rules = ["docs/architecture/README.md"\n', False),  # the array never ends: the profile doesn't read
    ('rules = ["docs/architecture/README.md]\n', False),  # nor does the string
])
def test_the_short_report_reads_the_rules_array_as_toml_does(tmp_path, rules, listed):
    root = _repo(tmp_path, {"src/a.py": "x\n"}, prof=_prof(rules), vendored=False)
    full = set(_lines(root))
    assert (MISSING not in full) == listed
    assert _old_ids(root) == full


def test_the_short_reports_rules_are_read_in_the_project_table_only(tmp_path):
    # A `rules` key in another table (here an area named "rules") isn't project.rules.
    prof = _prof() + '[areas]\nrules = ["docs/architecture/README.md"]\n'
    root = _repo(tmp_path, {"src/a.py": "x\n"}, prof=prof, vendored=False)
    assert _old_ids(root) == set(_lines(root)) == {MISSING}


# ---------- `profile check` ----------


def _warnings(tmp_path, guard):
    root = _repo(tmp_path, {"src/a.py": "x\n", "CLAUDE.md": "# Rules\n"}, prof=_prof(guard=guard))
    return [w for w in profile.check(profile.load(root)) if "docs/architecture/" in w]


PROTECTED = 'protected_paths = [".claude/**", ".github/workflows/**", {}]\n'


@pytest.mark.parametrize("glob", ['"docs/**"', '"docs/architecture/**"', '"docs/architecture/README.md"', '"**/*.md"', '"docs/architecture/orders.md"'])
def test_profile_check_warns_when_the_protected_paths_match_the_architecture(tmp_path, glob):
    w = _warnings(tmp_path, PROTECTED.format(glob))
    assert len(w) == 1 and "guard.protected_paths" in w[0] and glob.strip('"') in w[0]


@pytest.mark.parametrize("glob", ['"docs/guide/**"', '"*.txt"', '"src/**"'])
def test_profile_check_is_quiet_when_the_protected_paths_miss_the_architecture(tmp_path, glob):
    assert _warnings(tmp_path, PROTECTED.format(glob)) == []


def test_profile_check_warns_when_ticket_only_code_paths_match_the_architecture(tmp_path):
    w = _warnings(tmp_path, 'code_writers = "ticket"\ncode_paths = ["src/**", "docs/**"]\n')
    assert len(w) == 1 and "guard.code_paths" in w[0] and "docs/**" in w[0] and "ticket" in w[0]


def test_profile_check_is_quiet_about_code_paths_any_session_may_write(tmp_path):
    assert _warnings(tmp_path, 'code_writers = "any"\ncode_paths = ["src/**", "docs/**"]\n') == []
    assert _warnings(tmp_path / "b", 'code_writers = "ticket"\ncode_paths = ["src/**"]\n') == []


def test_the_profile_warning_reaches_doctors_profile_line(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n", "CLAUDE.md": "# Rules\n"}, prof=_prof(guard=PROTECTED.format('"docs/**"')))
    ln, = doctor.report(_inputs(root), [doctor.check_profile]).lines
    assert ln.status == "note" and "docs/architecture/" in ln.message.developer


# ---------- the changelog ----------


def test_the_changelog_has_a_note_under_unreleased():
    notes = since_0110()
    assert "#615" in notes and "kit.architecture.uncovered" in notes
    assert "so no change ever reads it" not in notes  # a change adding a file it matches reads it
