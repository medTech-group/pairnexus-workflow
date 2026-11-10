"""#639: doctor's `kit.architecture.missing` (spec #611, "Doctor" and
"Plugin-mode projects"; seam 2: doctor's lines from `Inputs`). A set-up
plugin-mode project whose `project.rules` doesn't list the architecture
overview gets a note offering "Write the architecture overview"
(`write_architecture_overview`); the old-Python short report gives the same
ids, by a mode of its own that reads `project.rules` as text.

One rule for a profile that can't be read (split out of #615's PR #635): the
full doctor can't load it, and the short report can't tell that it doesn't
load, so both read `project.rules` from its text the same way, with the short
report's reader. Listed there: no line from either. Not listed (or the text
can't be read at all): the line from both, `cant_check` in the full doctor."""

import os

import pytest

from changelog_notes import since_0110
from test_doctor_architecture import _inputs, _lines, _old_ids, _prof, _repo
from workflow import doctor

MISSING = "kit.architecture.missing"
IDS = ("kit.architecture.uncovered", "kit.architecture.unmatched", "kit.architecture.no_covers")
ARCH = (doctor.check_architecture_overview, doctor.check_architecture)
LISTS = 'rules = ["CLAUDE.md", "docs/architecture/README.md"]\n'
ARCH_FILES = {"src/a.py": "x\n", "docs/architecture/a.md": "Covers: src/**\n"}


def _arch(root, **kw):
    return _lines(root, checks=ARCH, **kw)


def _profile_file(root):
    return root / ".claude/workflow/profile.toml"


# ---------- the note and its offer ----------


def test_a_set_up_plugin_project_without_the_overview_in_its_rules_gets_the_note_and_offer(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n"}, vendored=False)
    got = _arch(root)
    assert set(got) == {MISSING}  # no folder: none of the other three
    ln = got[MISSING]
    assert ln.group == "The kit"
    assert ln.status == "note" and ln.offer == "write_architecture_overview"
    assert doctor.OFFERS["write_architecture_overview"] == "Write the architecture overview"
    assert "Write the architecture overview" in ln.fix.new and "Write the architecture overview" in ln.fix.developer
    assert "docs/architecture/README.md" in ln.message.new and "docs/architecture/README.md" in ln.message.developer
    assert ln.message.new != ln.message.developer and ln.fix.new != ln.fix.developer


@pytest.mark.parametrize("rules", [
    LISTS,
    'rules = ["./docs/architecture/README.md#cross-cutting-rules"]\n',
    "rules = [\n  \"CLAUDE.md\",\n  'docs/architecture/README.md',\n]\n",
])
def test_a_plugin_project_listing_the_overview_gets_no_line(tmp_path, rules):
    root = _repo(tmp_path, {"src/a.py": "x\n"}, prof=_prof(rules), vendored=False)
    assert MISSING not in _arch(root)


def test_a_vendored_project_never_gets_the_line(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n", "docs/architecture/a.md": "Covers: src/**\n"})
    assert MISSING not in _arch(root)


def test_a_vendored_project_whose_profile_cant_be_read_gets_no_line(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n"}, prof='[project]\nname = "x"\nbogus = [\n')
    assert MISSING not in _arch(root)


def test_a_plugin_project_not_set_up_gets_no_line(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n"}, vendored=False)
    _profile_file(root).unlink()
    assert MISSING not in _arch(root)
    assert _old_ids(root) == set()


def test_a_plugin_project_with_the_folder_gets_all_four(tmp_path):
    root = _repo(tmp_path, ARCH_FILES, vendored=False)
    assert set(_arch(root)) == {MISSING, *IDS}


def test_the_check_is_in_checks_and_local_checks_in_the_kit_group():
    check = doctor.check_architecture_overview
    assert check in doctor.CHECKS and check in doctor.LOCAL_CHECKS
    assert check.group == "The kit" and check.id == MISSING


def test_status_never_gets_it(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n"}, vendored=False)
    assert _arch(root, gaps_only=True) == {}


def test_the_text_report_offers_the_upgrade(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n"}, vendored=False)
    r = doctor.report(_inputs(root), [doctor.check_architecture_overview])
    assert "Write the architecture overview" in doctor.text(r)
    assert any(ln["offer"] == "write_architecture_overview" for ln in r.as_dict()["lines"])


# ---------- the short report gives the same ids ----------


@pytest.mark.parametrize("vendored", [True, False])
@pytest.mark.parametrize("folder", [True, False])
@pytest.mark.parametrize("rules", ["", LISTS, "rules = [\n  \"CLAUDE.md\",\n  'docs/architecture/README.md',\n]\n"])
def test_the_short_report_gives_the_same_ids_as_doctor(tmp_path, vendored, folder, rules):
    root = _repo(tmp_path, ARCH_FILES if folder else {"src/a.py": "x\n"}, prof=_prof(rules), vendored=vendored)
    full = set(_arch(root))
    assert _old_ids(root) == full
    assert (MISSING in full) == (not vendored and not rules)
    assert (set(IDS) <= full) == folder


@pytest.mark.parametrize("rules, listed", [
    ('rules = [\n  "CLAUDE.md",\n  # "docs/architecture/README.md",\n]\n', False),  # in a comment: not listed
    ("rules = [\"CLAUDE.md\"] # 'docs/architecture/README.md'\n", False),
    ('rules = ["docs/rules[v2].md", "docs/architecture/README.md"]\n', True),  # a `]` inside a string
    ("rules = ['docs/a]b.md', # a ] in a comment\n  \"docs/architecture/README.md\",\n]\n", True),
    ('rules = ["docs/a\\"]b.md", "docs/architecture/README.md"]\n', True),  # an escaped quote
    ('rules = ["CLAUDE.md"]\nother = ["docs/architecture/README.md"]\n', False),  # after the array's end
    ("rules = ['''docs/architecture/README.md''']\n", True),
    ('rules = ["docs/architecture/README\\u002emd"]\n', True),
])
def test_the_short_report_reads_the_rules_array_as_doctor_does(tmp_path, rules, listed):
    root = _repo(tmp_path, {"src/a.py": "x\n"}, prof=_prof(rules), vendored=False)
    full = set(_arch(root))
    assert (MISSING not in full) == listed
    assert _old_ids(root) == full


@pytest.mark.parametrize("profile, ids", [("listed", set()), ("none", set()), ("unlisted", {MISSING})])
def test_a_lock_that_cant_be_looked_at_gives_the_same_ids_from_both_reports(tmp_path, monkeypatch, profile, ids):
    # `Path.exists` raises PermissionError for a lock in a folder that can't
    # be searched, where `os.path.exists`, as the short report asks, says no
    # lock: plugin mode. Raised here whoever runs the test, root or not. So a
    # profile that doesn't list the overview gets the note from both.
    rules = 'rules = ["CLAUDE.md"]\n' if profile == "unlisted" else LISTS
    root = _repo(tmp_path, {"src/a.py": "x\n"}, prof=_prof(rules), vendored=False)
    if profile == "none":
        _profile_file(root).unlink()
    lock = root / ".claude/workflow/lock.json"
    exists = type(lock).exists

    def refused(self, *a, **kw):
        if self == lock:
            raise PermissionError(13, "Permission denied", str(self))
        return exists(self, *a, **kw)

    monkeypatch.setattr(type(lock), "exists", refused)
    full = _arch(root)
    assert _old_ids(root) == set(full) == ids
    if ids:
        assert full[MISSING].status == "note" and full[MISSING].offer == "write_architecture_overview"


def test_rules_are_read_in_the_project_table_only(tmp_path):
    # A `rules` key in another table (here an area named "rules") isn't project.rules.
    prof = _prof() + '[areas]\nrules = ["docs/architecture/README.md"]\n'
    root = _repo(tmp_path, {"src/a.py": "x\n"}, prof=prof, vendored=False)
    assert _old_ids(root) == set(_arch(root)) == {MISSING}


# ---------- a profile that can't be read: one rule for both reports ----------


def _broken(listed: bool) -> dict[str, bytes]:
    """Profiles the full doctor can't load, each listing the overview in
    `project.rules`'s text or not."""
    rules = LISTS if listed else 'rules = ["CLAUDE.md"]\n'
    return {
        # An unclosed array after the rules: TOML can't parse it.
        "doesnt_parse": (_prof(rules) + "[guard]\nprotected_paths = [\n").encode(),
        # TOML reads it, but the kit's profile check refuses it.
        "refused": _prof(rules).replace("ruleset = true", 'ruleset = "maybe"').encode(),
        # Not UTF-8: a byte that isn't, in a comment.
        "not_utf8": (_prof(rules) + "# caf").encode() + b"\xe9\n",
        # A byte-order mark before it: TOML refuses it, the short report leaves it out.
        "bom": b"\xef\xbb\xbf" + _prof(rules).encode(),
    }


@pytest.mark.parametrize("listed", [True, False], ids=["listed", "not_listed"])
@pytest.mark.parametrize("case", ["doesnt_parse", "refused", "not_utf8", "bom"])
def test_a_profile_that_cant_be_read_gives_the_same_ids_from_both_reports(tmp_path, case, listed):
    root = _repo(tmp_path, {"src/a.py": "x\n"}, vendored=False)
    _profile_file(root).write_bytes(_broken(listed)[case])
    assert _inputs(root).profile_error  # the full doctor can't load it
    full = _arch(root)
    assert _old_ids(root) == set(full)
    if listed:
        assert MISSING not in full
    else:
        ln = full[MISSING]
        assert ln.status == "cant_check" and ln.fix == doctor.PROFILE_FIRST and ln.offer is None


@pytest.mark.parametrize("listed", [True, False], ids=["listed", "not_listed"])
def test_a_profile_that_cant_be_read_gives_the_same_ids_with_the_folder(tmp_path, listed):
    root = _repo(tmp_path, ARCH_FILES, vendored=False)
    _profile_file(root).write_bytes(_broken(listed)["doesnt_parse"])
    full = set(_arch(root))
    assert _old_ids(root) == full
    assert full == (set(IDS) if listed else {MISSING, *IDS})


def test_an_unclosed_rules_array_listing_the_overview_doesnt_count(tmp_path):
    # TOML can't read it, and neither does the text reader: not listed.
    root = _repo(tmp_path, {"src/a.py": "x\n"}, prof=_prof('rules = ["docs/architecture/README.md"\n'), vendored=False)
    full = _arch(root)
    assert _old_ids(root) == set(full) == {MISSING}
    assert full[MISSING].status == "cant_check"


def test_a_profile_that_is_a_directory_gives_the_same_ids_from_both_reports(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n"}, vendored=False)
    path = _profile_file(root)
    path.unlink()
    path.mkdir()
    (path / "rules").write_text(LISTS)  # never read: it isn't the profile
    full = _arch(root)
    assert _old_ids(root) == set(full) == {MISSING}
    assert full[MISSING].status == "cant_check" and full[MISSING].fix == doctor.PROFILE_FIRST


def test_a_profile_that_is_a_pipe_is_never_opened_by_either_report(tmp_path):
    root = _repo(tmp_path, {"src/a.py": "x\n"}, vendored=False)
    path = _profile_file(root)
    path.unlink()
    os.mkfifo(path)  # opening it to read would block: neither report may
    full = _arch(root)
    assert _old_ids(root) == set(full) == {MISSING}
    assert full[MISSING].status == "cant_check"


# ---------- the changelog ----------


def test_the_changelog_has_a_note_under_unreleased():
    notes = since_0110()
    start = notes.index("(#639,")
    note = notes[start:notes.index("\n**", start)]
    for words in ("kit.architecture.missing", "write_architecture_overview", "Write the architecture overview", "plugin"):
        assert words in note, words
