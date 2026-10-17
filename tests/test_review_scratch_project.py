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
    "anything taking `--project` or `--out`, and any other command that writes files, `workflow evidence` among them",
)
RULE = (
    "runs only against an absolute path to a scratch project, never the session's checkout",
    "a fresh temporary directory, or a `git clone` of the checkout into one with its `origin` removed",
    "shares the session's `.git`",
    "`--project` the scratch project's absolute path on every call",
    "`$CLAUDE_PROJECT_DIR` or the nearest checkout",
    "left out (or empty, for `vendor`)",
    "`git status --porcelain --ignored --untracked-files=all` in the session's checkout (and in the clean copy too, when",
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
    assert "It never tries to undo a change" in text
    assert "how to run a command that has no `--project`" in text


def test_the_explorer_states_the_scratch_project_rule():
    text = _explorer_rule()
    for phrase in COMMANDS + RULE:
        assert phrase in text, phrase
    # A command with no --project is tried with the variable pointed at the scratch project.
    assert "`cd <scratch> && CLAUDE_PROJECT_DIR=<scratch> <the command>`" in text
    assert "before you start and again when you finish" in text
    assert "Call the CLI with `python3 -B` (so it writes no bytecode) by its absolute path in the session's checkout (or in the clean copy, when the review panel gives you one)" in text
    assert "delete it when you finish" in text
    assert "`git -C <scratch> remote remove origin`" in text
    assert "with literal absolute paths" in text
    assert "each into a file in your temporary directory, and `diff` the two" in text
    assert "with the command that made it, and never try to undo it" in text


def test_the_explorer_never_cleans_up_the_checkout_to_finish_clean():
    opening = _paragraph(_explorer(), "You exercise a change from the outside")
    assert "must show nothing you made; if it does, report it (below) and leave it" in opening


def test_a_discard_the_guard_refuses_finishes_in_a_clean_copy():
    after = _section("skills/review-panel/SKILL.md", "## 3. After each round", "\n## 4.")
    assert "If the guard refuses the discard (a protected file), finish in a clean copy, and say so in the PR body" in after
    # A worktree of the branch itself is refused while the checkout holds it.
    assert "`git worktree add --detach <a directory outside the repo> HEAD`" in after
    assert "`git push origin HEAD:<branch>`" in after
    assert "Do everything after it there: later fixes, the tests, `commit.txt`, the diff and the next rounds" in after
    assert "the explorer runs the CLI from it, and checks both it and the session's checkout" in after
