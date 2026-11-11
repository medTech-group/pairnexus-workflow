"""#690: the profile check's `git` calls in `workflow doctor` (the base's
profile read, and `_code_warnings`' tracked files) run through the shared
runner since #689, and the tracked files' timeout is a seam,
`profile.CODE_FILES_TIMEOUT`.

#717: a Ctrl-C while doctor runs those calls stops it quietly (exit 130,
`workflow doctor: stopped`) and kills what that `git` started. The reproducer
of #690: a fake `git` on the PATH that, at one of those calls, starts a
`sleep`, writes its pid and waits; then a Ctrl-C, to doctor's pid or to its
whole process group. It runs on status's Ctrl-C harness
(`tests/test_status_local_gaps.py`), shared rather than copied."""

import pytest

from changelog_notes import KIT, entry, since_0110
from test_doctor import _prof
from test_status_local_gaps import _ctrl_c_at_git_call
from workflow import architecture
from workflow.guard import matches

# The profile check's `git` calls. Doctor's own calls log differently
# (`-c core.quotePath=false ls-files -z`, `rev-parse --verify -q`), so the
# profile check's are the first match.
PROFILE_GIT = ["check-ref-format refs/remotes/origin/main", "rev-parse --verify --quiet refs/remotes/origin/main^{commit}",
               "show refs/remotes/origin/main:.claude/workflow/profile.toml", "ls-files -z"]
# A profile that names code, so the check reads the tracked files too.
CODE = _prof('experience = "new"\nruleset = true\n', '[guard]\ncode_writers = "any"\ncode_paths = ["src/**"]\n')


# The SIGINT sent to doctor alone, and to its whole process group, as a
# terminal's Ctrl-C sends it.
@pytest.mark.parametrize("group", [False, True], ids=["pid", "group"])
@pytest.mark.parametrize("call", PROFILE_GIT)
def test_ctrl_c_during_the_profile_checks_git_calls_stops_quietly_with_nothing_left_running(tmp_path, call, group):
    _ctrl_c_at_git_call(tmp_path, call, command="doctor", last=False, group=group, profile=CODE)


# A slow `git` (a busy machine) at the tracked files' own timeout: the test's
# launcher sets `profile.CODE_FILES_TIMEOUT` far past its wait, as it does the
# profile's other `git` calls', so the Ctrl-C still finds the command running.
def test_a_slow_ls_files_in_the_profile_check_is_still_running_when_the_ctrl_c_comes(tmp_path):
    _ctrl_c_at_git_call(tmp_path, "ls-files -z", command="doctor", last=False, delay=21, profile=CODE)


def test_the_changelog_notes_the_profile_checks_git_calls_ctrl_c():
    notes = since_0110()
    assert "#690" in notes and "CODE_FILES_TIMEOUT" in notes


def test_the_changelog_notes_the_doctor_level_ctrl_c_test():
    note = entry("#717")
    assert "workflow doctor: stopped" in note and "process group" in note
    assert "- **For projects updating:**" in note
    # #690's note no longer says the test is still to come.
    assert "Still to come" not in entry("#690")


def test_the_changelog_note_helpers_are_listed_in_their_page():
    """The overview's "Reuse, not copies": `entry` moved into
    `tests/changelog_notes.py` is listed in a page, the small page named by
    its folder ("Code no page covers yet"), which covers the file by a literal
    path (#717)."""
    file = "tests/changelog_notes.py"
    covering = [pg for pg in architecture.pages(KIT) if any(matches(file, [g]) for g in pg.covers)]
    assert [pg.file for pg in covering] == ["docs/architecture/tests.md"], covering
    page = covering[0]
    assert file in page.covers, page.covers
    helpers = dict(page.helpers)
    assert {"entry", "since_0110"} <= helpers.keys(), page.helpers
    assert all(helpers[name] for name in ("entry", "since_0110")), page.helpers
