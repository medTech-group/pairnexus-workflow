"""#172: review-panel explorers run commands that write files only on a
scratch project, and report a change in the session's checkout instead of
undoing it, read as the kit-release tests read skills."""

from conftest import KIT

# The commands the rule names, and the rule's own words, in both texts.
COMMANDS = (
    "`workflow adopt`",
    "`workflow vendor`",
    "`workflow repair`",
    "the set-up step that saves `workflow pr-template`'s output",
    "anything taking `--project` or `--out`",
)
RULE = (
    "runs only against an absolute path to a scratch project, never the session's checkout",
    "a `git worktree add --detach` outside the repo",
    "`--project` that absolute path on every call: left out",
    "means `$CLAUDE_PROJECT_DIR` or the checkout",
    "`git status --porcelain` in the session's checkout before",
    "any difference between the two as a finding",
    "the guard can refuse the undo",
)


def _read(rel: str) -> str:
    return (KIT / rel).read_text(encoding="utf-8")


def _section(rel: str, start: str, end: str) -> str:
    text = _read(rel)
    assert start in text, f"{rel} has {start!r}"
    return text.split(start, 1)[1].split(end, 1)[0]


def _paragraph(text: str, start: str) -> str:
    """The paragraph that starts with `start`."""
    assert start in text, start
    return text.split(start, 1)[1].split("\n\n", 1)[0]


def _skill_rule() -> str:
    reviewers = _section("skills/review-panel/SKILL.md", "## 2. Start the reviewers", "\n## 3.")
    return _paragraph(reviewers, "Tell the explorer, too, that a command under review that writes files")


def _explorer() -> str:
    return _read("agents/ui-explorer.md")


def _explorer_rule() -> str:
    return _paragraph(_explorer(), "A command under review that writes files")


def test_the_skill_sends_file_writing_commands_to_a_scratch_project():
    text = _skill_rule()
    for phrase in COMMANDS + RULE:
        assert phrase in text, phrase
    assert "before and after" in text
    assert "It never tries to undo it" in text


def test_the_explorer_states_the_scratch_project_rule():
    text = _explorer_rule()
    for phrase in COMMANDS + RULE:
        assert phrase in text, phrase
    # A command with no --project is tried with the variable pointed at the scratch project.
    assert "`cd <scratch> && CLAUDE_PROJECT_DIR=<scratch> <the command>`" in text
    assert "before you start and again when you finish" in text
    assert "with the command that made it, and never try to undo it" in text


def test_the_explorer_never_cleans_up_the_checkout_to_finish_clean():
    opening = _paragraph(_explorer(), "You exercise a change from the outside")
    assert "must show nothing you made; if it does, report it (below) and leave it" in opening


def test_a_discard_the_guard_refuses_finishes_in_a_clean_worktree():
    after = _section("skills/review-panel/SKILL.md", "## 3. After each round", "\n## 4.")
    assert "If the guard refuses the discard (a protected file), finish in a clean `git worktree` of the branch" in after
    assert "say so in the PR body" in after
