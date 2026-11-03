"""#429: the fixer agent, `agents/fixer.md`, and `review-panel` §3's fix rule
(spec #412, "The fixer"; ADR 0002's "Fixes narrow first"). Read as the kit's
other text contracts are (prior art: tests/test_planning_review.py,
tests/test_planning_checker.py): a later rewording that keeps the rule passes.
And `vendor.plan` ships the agent, as it ships the others."""

import re

from changelog_notes import since_0110
from conftest import KIT

from workflow import vendor

AGENT = KIT / "agents/fixer.md"
PANEL = "skills/review-panel/SKILL.md"


def _flat(text: str) -> str:
    return " ".join(text.split())


def _parts() -> tuple[str, str]:
    """(the frontmatter, the body) of the agent."""
    text = AGENT.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "the agent opens with its frontmatter"
    _, head, body = text.split("---\n", 2)
    return head, body


def _frontmatter() -> dict:
    return dict(line.split(": ", 1) for line in _parts()[0].strip().splitlines())


def _body() -> str:
    return _flat(_parts()[1])


def _section(name: str) -> str:
    """One `## ` section of the agent's body, flattened."""
    body = _parts()[1]
    assert f"\n## {name}\n" in body, f"the agent has a `## {name}` section"
    return _flat(body.split(f"\n## {name}\n", 1)[1].split("\n## ", 1)[0])


def _s3() -> str:
    text = (KIT / PANEL).read_text(encoding="utf-8")
    return _flat(text.split("## 3. After each round", 1)[1].split("\n## 4.", 1)[0])


def _paragraph(text: str, opening: str) -> str:
    """From `opening` to the next bold-headed paragraph (`**…**` after a full stop), flattened."""
    assert opening in text, opening
    after = text.split(opening, 1)[1]
    return opening + re.split(r"(?<=[.:]) \*\*[A-Z]", after, maxsplit=1)[0]


def _fix_rule() -> str:
    return _paragraph(_s3(), "**The fix rule.**")


def _the_fixer() -> str:
    return _paragraph(_s3(), "**The fixer.**")


# --- who it is ----------------------------------------------------------------


def test_it_is_a_named_agent_with_edit_and_shell_tools():
    fm = _frontmatter()
    assert fm["name"] == "fixer"
    tools = {t.strip() for t in fm["tools"].split(",")}
    assert {"Read", "Edit", "Write", "Bash"} <= tools
    assert "Agent" not in tools, "a fixer starts no agents of its own"
    assert "review-panel" in fm["description"] and "fresh" in fm["description"]


def test_vendor_ships_it_beside_the_reviewers():
    plan = vendor.plan(KIT, None)
    assert ".claude/agents/fixer.md" in plan
    assert ".claude/agents/correctness-reviewer.md" in plan


def test_it_gets_only_what_the_spec_names_and_nothing_of_the_sessions_history():
    inputs = _section("Your inputs")
    for name in ("`ticket.md`", "`bar.md`", "`rules.md`", "`findings.md`", "`moved.md`", "`head.txt`"):
        assert name in inputs, name
    # The open blocking findings, with their reproducers and any ruling on them.
    findings = inputs.split("`findings.md`", 1)[1]
    for words in ("marked blocks", "reproducer", "kept after a contest"):
        assert words in findings, words
    assert "Nothing of the session's history" in inputs
    # It checks it starts on the head it was given: anything else, it stops.
    assert "If `git rev-parse HEAD` isn't `head.txt`, stop" in inputs


def test_section_3_gives_it_the_same_inputs_in_a_directory_of_its_own():
    fixer = _the_fixer()
    assert "`/tmp/fix-<ticket>-<review>/`" in fixer
    for name in ("`ticket.md`", "`bar.md`", "`rules.md`", "`findings.md`", "`moved.md`", "`head.txt`"):
        assert name in fixer, name
    assert "nothing of this session's history" in fixer
    # An overturned finding counts for nothing: it isn't given to the fixer.
    assert "an overturned one isn't given to it" in fixer


# --- the fix rule, in both places --------------------------------------------


RULE_WORDS = (
    # a defect: the reproducer as a failing test first, then the fix
    "its reproducer as a failing test first, then the fix that makes it pass",
    # a missing test: the test is the fix
    "the test is the fix",
    # narrowing first
    "prefer a fix that removes a case, refuses more or deletes text",
    # an added exception, state or rule: both sides, one commit
    "adds an exception, a state or a rule tests both sides of it in the same commit",
    # then the checks, the commit, the push and the report
    "the typecheck and the affected tests",
)


def test_the_agent_states_the_fix_rule():
    rule = _section("The fix rule")
    for words in RULE_WORDS:
        assert words in rule, words
    assert rule.index("failing test first") < rule.index("prefer a fix that removes a case")
    for step in ("commit", "push", "report"):
        assert step in rule.split("the typecheck and the affected tests", 1)[1], step


def test_section_3_states_the_same_fix_rule():
    rule = _fix_rule()
    for words in RULE_WORDS:
        assert words in rule, words
    assert "`fixer` agent follows it" in rule


def test_the_agent_and_section_3_order_the_checks_before_the_commit():
    for rule in (_section("The fix rule"), _fix_rule()):
        tests = rule.index("the typecheck and the affected tests")
        assert tests < rule.index("commit", tests) < rule.index("push", tests)


def test_each_finding_is_checked_before_it_is_fixed():
    assert "Check it against the code first: a reviewer can be wrong" in _section("The fix rule")
    assert "Check it against the code first: a reviewer can be wrong" in _fix_rule()


# --- contests and marks -------------------------------------------------------


CONTEST_WORDS = (
    "is contested with a written reason, never fixed silently or dropped",
    "A finding kept after a contest is fixed, never contested again",
)


def test_the_agent_contests_with_a_reason_fixes_a_kept_one_and_never_changes_a_mark():
    rule = _section("The fix rule")
    for words in CONTEST_WORDS:
        assert words in rule, words
    assert "\"not a problem\"" in rule.lower()
    assert "You never change a mark" in rule


def test_section_3_says_the_same_of_contests_and_marks():
    rule = _fix_rule()
    for words in CONTEST_WORDS:
        assert words in rule, words
    assert "never changes a mark" in rule
    # The fixer's reason is the contest's reason: it goes where §3 already sends a contest's.
    assert "its reason is the contest's" in rule
    # The session's own doubt goes to the fixer too, never held back.
    assert "A finding you doubt goes to the fixer all the same" in _the_fixer()


def test_the_older_paragraph_still_holds_every_reported_finding():
    # #374's paragraph stands beside the fixer: every finding goes in the findings file as reported.
    s3 = _s3()
    assert "every finding a reviewer reported goes in the findings file as reported" in s3
    assert "Such a finding marked blocks is contested" in s3


# --- security -----------------------------------------------------------------


def test_a_security_problem_names_only_its_area_in_its_test_table_and_commit():
    rule = _section("The fix rule")
    s3 = _fix_rule()
    for text in (rule, s3):
        assert "security problem the change adds" in text
        assert "its test's name, its row in the findings table and its commit message name only its area" in text
    # The details stay out of every public word, the fixer's report being the session's alone.
    assert "Its details stay in your report, which only the session reads" in rule


# --- a fresh fixer for each review -------------------------------------------


def test_section_3_sends_each_reviews_fixes_to_a_fresh_fixer():
    fixer = _the_fixer()
    assert "Under the rule (section 10)" in fixer
    assert "each review's fixes, round 1's included, go to a fresh `fixer` agent" in fixer
    assert "never one kept from an earlier review" in fixer
    # The numbered steps say so too, so the two never answer differently.
    s3 = _s3()
    steps = s3.split("1. Check each finding", 1)[1].split("A record under the rule", 1)[0]
    assert "a fresh fixer makes them instead" in steps


def test_it_never_posts_merges_or_starts_a_review():
    body = _body()
    assert "never post on GitHub" in body
    assert "never merge" in body
    assert "never edit `findings.json` or `record.md`" in body


def test_it_reports_each_findings_outcome_by_its_number():
    report = _section("How to report")
    for outcome in ("**fixed:**", "**contested:**", "**not fixed:**"):
        assert outcome in report, outcome
    assert "its number in `findings.md`" in report
    assert "the head you pushed" in report


def test_it_never_builds_a_moved_criterion_or_puts_back_a_split_part():
    rule = _section("The fix rule")
    assert "Never build a criterion `moved.md` lists, and never put back a part split out" in rule


def test_a_part_to_replace_or_take_out_comes_as_part_md():
    # merge-check's `fail_closed` and `split` say "a fresh fixer" does them.
    part = _section("A part to replace or take out")
    assert "`part.md`" in part
    assert "the safe fallback" in part.lower() and "`bar.md`" in part
    assert "take it out" in part
    assert "`part.md`" in _the_fixer()


# --- the changelog -----------------------------------------------------------


def test_the_changelog_notes_it_under_unreleased():
    notes = since_0110()
    assert "#429" in notes
    note = notes.split("#429", 1)[0].rsplit("\n\n**", 1)[1] + notes.split("#429", 1)[1].split("\n\n**", 1)[0]
    for words in ("`fixer`", "`agents/fixer.md`", "§3", "failing test", "fresh"):
        assert words in note, words
