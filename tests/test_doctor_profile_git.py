"""#690: the profile check's `git` calls in `workflow doctor` (the base's
profile read, and `_code_warnings`' tracked files) run through the shared
runner since #689, and the tracked files' timeout is a seam,
`profile.CODE_FILES_TIMEOUT`. The doctor-level Ctrl-C test at those calls is
#717's."""

from changelog_notes import since_0110


def test_the_changelog_notes_the_profile_checks_git_calls_ctrl_c():
    notes = since_0110()
    assert "#690" in notes and "CODE_FILES_TIMEOUT" in notes
