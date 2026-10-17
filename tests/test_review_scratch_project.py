"""#172: review-panel explorers run commands that write files only on a
scratch project, and report a change in the real checkout instead of undoing
it, read as the kit-release tests read skills."""

from conftest import KIT


def _read(rel: str) -> str:
    return (KIT / rel).read_text(encoding="utf-8")


def _section(rel: str, start: str, end: str) -> str:
    text = _read(rel)
    assert start in text, f"{rel} has {start!r}"
    return text.split(start, 1)[1].split(end, 1)[0]


def _start_reviewers() -> str:
    return _section("skills/review-panel/SKILL.md", "## 2. Start the reviewers", "\n## 3.")


def _explorer() -> str:
    return _read("agents/ui-explorer.md")


def test_the_skill_sends_file_writing_commands_to_a_scratch_project():
    text = _start_reviewers()
    # The commands it covers, by name.
    for name in ("`workflow adopt`", "`workflow pr-template`", "set-up and upgrade", "`--project`"):
        assert name in text, name
    assert "only against an absolute path to a scratch project" in text
    assert "a fresh temporary directory or a `git worktree`" in text
    assert "never the session's checkout" in text


def test_the_skill_has_the_explorer_report_changes_in_the_real_checkout():
    text = _start_reviewers()
    assert "`git status --porcelain`" in text
    assert "report any change it shows in the real checkout as a finding, and never try to undo it" in text


def test_the_explorer_states_the_scratch_project_rule():
    text = _explorer()
    for name in ("`workflow adopt`", "`workflow pr-template`", "set-up and upgrade", "`--project`"):
        assert name in text, name
    assert "only against an absolute path to a scratch project" in text
    assert "a fresh temporary directory or a `git worktree`" in text
    assert "never the session's checkout" in text


def test_the_explorer_reports_a_changed_checkout_instead_of_undoing_it():
    text = _explorer()
    assert "`git status --porcelain`" in text
    assert "report it as a finding" in text
    assert "never try to undo it" in text
    # Checked before it starts and again when it finishes.
    assert "before you start and again when you finish" in text
