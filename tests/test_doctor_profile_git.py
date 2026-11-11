"""#690: a Ctrl-C while `workflow doctor` runs the profile check's own `git`
calls stops it quietly (exit 130, `workflow doctor: stopped`), and kills what
that `git` started. The reproducer of #684's round 1: a fake `git` on the
PATH that, at one of those calls, starts a `sleep`, writes its pid and waits;
then a Ctrl-C. The calls are the base's profile read (`check-ref-format`,
`rev-parse`, `show`) and, for a profile that names code, `_code_warnings`'
tracked files (`ls-files -z`)."""

import pytest

from changelog_notes import since_0110
from test_doctor import _bin, _ctrl_c, _gone, _prof
from test_status_local_gaps import _counting_git, _env, _git_project

# The profile check's `git` calls, in the order doctor makes them.
PROFILE_GIT = ["check-ref-format refs/remotes/origin/main", "rev-parse --verify --quiet refs/remotes/origin/main^{commit}",
               "show refs/remotes/origin/main:.claude/workflow/profile.toml", "ls-files -z"]
# A profile that names code, so the check reads the tracked files too.
CODE = _prof('experience = "new"\nruleset = true\n', '[guard]\ncode_writers = "any"\ncode_paths = ["src/**"]\n')


def _doctor_calls(tmp_path, root, path):
    """The `git` calls a whole doctor run makes, in order, with the real `git` behind the fake."""
    import subprocess
    import sys

    log, _ = _counting_git(path, tmp_path)
    cli = root / ".claude/workflow/bin/workflow.py"
    p = subprocess.run([sys.executable, "-B", str(cli), "doctor", "--json"], cwd=root, env=_env(tmp_path, root, path),
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return log.read_text().splitlines()


def _ctrl_c_at_profile_git_call(tmp_path, call, delay=0, group=False):
    root = _git_project(tmp_path, profile=CODE)
    path = _bin(tmp_path, gh=False)
    calls = _doctor_calls(tmp_path, root, path)
    assert call in calls, calls
    # The profile check's own call: the first with these arguments.
    _, marker = _counting_git(path, tmp_path, hang_at=calls.index(call) + 1, delay=delay)
    code, err = _ctrl_c(root / ".claude/workflow/bin/workflow.py", ["doctor"], root, _env(tmp_path, root, path), marker,
                        group=group)
    assert code == 130 and "workflow doctor: stopped" in err and "Traceback" not in err, err
    assert _gone(int(marker.read_text())), "what the profile check's git started is still running"


# The SIGINT sent to doctor alone, and to its whole process group, as a
# terminal's Ctrl-C sends it.
@pytest.mark.parametrize("group", [False, True], ids=["pid", "group"])
@pytest.mark.parametrize("call", PROFILE_GIT)
def test_ctrl_c_during_the_profile_checks_git_calls_stops_quietly_with_nothing_left_running(tmp_path, call, group):
    _ctrl_c_at_profile_git_call(tmp_path, call, group=group)


# A slow `git` (a busy machine) at the tracked files' own timeout: the test's
# launcher sets it far past its wait, as it does the profile's other `git`
# calls', so the Ctrl-C still finds the command running.
def test_a_slow_ls_files_in_the_profile_check_is_still_running_when_the_ctrl_c_comes(tmp_path):
    _ctrl_c_at_profile_git_call(tmp_path, "ls-files -z", delay=21)


def test_the_changelog_notes_the_profile_checks_git_calls_ctrl_c():
    notes = since_0110()
    assert "#690" in notes and "CODE_FILES_TIMEOUT" in notes
