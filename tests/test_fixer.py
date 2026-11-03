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
    """From `opening` to the next bold-headed paragraph (`**…**` after a full stop or a colon), flattened."""
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
    assert "Read no other `/tmp/review-*` or `/tmp/fix-*` directory" in inputs
    assert "`previous.md`" not in inputs
    # The head is given; nothing stops it there (round 3: a stop with no outcome had no answer).
    assert "`head.txt`: the branch's head the findings are about" in inputs
    assert "If `git rev-parse HEAD` isn't `head.txt`" not in inputs


def test_section_3_gives_it_the_same_inputs_in_a_directory_of_its_own():
    fixer = _the_fixer()
    assert "`/tmp/fix-<ticket>-<review>/`" in fixer
    for name in ("`ticket.md`", "`bar.md`", "`rules.md`", "`findings.md`", "`moved.md`", "`head.txt`"):
        assert name in fixer, name
    assert "nothing of this session's history (no `previous.md`, no summaries)" in fixer
    listed = fixer.split("holding only these", 1)[1]
    assert "- `previous.md`" not in listed and "- `diff.patch`" not in listed
    # An overturned finding counts for nothing: it isn't given to the fixer.
    assert "An overturned one isn't given to it: it counts for nothing" in fixer


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
    "the affected tests",
)


def test_the_agent_states_the_fix_rule():
    rule = _section("The fix rule")
    for words in RULE_WORDS:
        assert words in rule, words
    assert rule.index("failing test first") < rule.index("prefer a fix that removes a case")
    for step in ("commit", "push", "report"):
        assert step in rule.split("the affected tests", 1)[1], step


def test_section_3_states_the_same_fix_rule():
    rule = _fix_rule()
    for words in RULE_WORDS:
        assert words in rule, words
    assert "`fixer` agent follows it, and gives it in full" in rule
    assert "It is `review-panel` §3's fix rule, given here in full" in _section("The fix rule")


def test_the_agent_and_section_3_order_the_checks_before_the_commit():
    for rule in (_section("The fix rule"), _fix_rule()):
        tests = rule.index("the affected tests")
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


def test_it_never_posts_merges_or_edits_the_records():
    body = _body()
    assert "never post on GitHub" in body
    assert "never merge" in body
    assert "never edit `findings.json` or `record.md`" in body


def test_it_reports_each_findings_outcome_by_its_number():
    report = _section("How to report")
    for outcome in ("**fixed:**", "**contested:**", "**taken with its part:**"):
        assert outcome in report, outcome
    # No third way out: a finding left "not fixed" would turn into a ticket at the next review
    # (§10's lines already reviewed), and the defect would merge.
    assert "not fixed" not in report
    assert "Every finding ends fixed, contested, taken with its part (below) or refused by the guard, nothing else" in _section("The fix rule")
    assert "Every finding ends fixed, contested, taken with its part (a part in `part.md`, replaced or taken out) or refused by the guard" in _fix_rule()
    assert "**refused:**" in report
    assert "fixes by refusing the case it fails on" in _fix_rule()
    assert "you fix by refusing the case it fails on" in _section("The fix rule")
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


# --- round 1's findings ------------------------------------------------------


def test_the_record_and_merge_check_come_before_the_fixer():
    # merge-check says `mechanism_repeats` only while the head is the latest record's commit:
    # a fixer that pushed first would leave it never firing, and `part.md` never given.
    fixer = _the_fixer()
    order = fixer.split("The order, after each review:", 1)[1]
    findings_file, step4, record, merge_check, the_fixer, step5 = (
        order.index("the findings file written"),
        order.index("step 4;"),
        order.index("the record posted (step 6)"),
        order.index("`WF merge-check` run on the head"),
        order.index("the fixer, when there is anything to fix, with `part.md` from that answer"),
        order.index("step 5, on the head it pushed"),
    )
    assert findings_file < step4 < record < merge_check < the_fixer < step5
    assert "only while the head is the latest record's commit" in order


def test_a_security_problem_the_change_adds_marked_a_ticket_reaches_the_fixer():
    s3 = _the_fixer()
    findings = s3.split("`findings.md`:", 1)[1]
    assert "any security problem the change adds (`security: change`) marked a ticket to fix it" in findings
    inputs = _section("Your inputs").split("`findings.md`", 1)[1]
    assert "any security problem the change adds (`security: change`) marked a ticket to fix it, which you fix as if marked blocks" in inputs


def test_a_security_problem_on_main_never_reaches_a_runs_fixer():
    s3 = _the_fixer()
    assert "A blocking security or safety problem in code on the base branch (`security: main`) goes in only in attended work: in a run it holds the ticket for the owner (`build-ticket`), and the fixer never sees it" in s3
    assert "which it does only in attended work" in _section("The fix rule")


def test_a_security_problems_area_is_all_any_word_in_the_repository_names():
    rule = _section("The fix rule")
    assert "the test's docstring and comments, code comments" in rule
    assert "so does every other word the fixer writes in the repository" in _fix_rule()


def test_it_pushes_head_to_the_branch_so_a_clean_copy_pushes_too():
    rule = _section("The fix rule")
    assert "always as `git push origin HEAD:<branch>`" in rule
    assert "Commit only the files you changed" in rule


def test_it_fixes_only_what_its_fixes_broke_and_reports_the_rest():
    rule = _section("The fix rule")
    assert "Fix what your fixes broke; report any other failure, changing nothing for it" in rule
    assert "skip it when the profile has none" in rule
    assert "the typecheck and the affected tests" in _fix_rule()


def test_the_session_contests_nothing_itself():
    s3 = _s3()
    assert "contested only when the fixer contests it (**The fix rule**), never by you" in s3
    assert "your doubt goes only in the findings table" in _the_fixer()


def test_part_md_can_name_several_parts():
    assert "each such part's name exactly as the records give it, and which for each" in _the_fixer()
    assert "for each such part, its name" in _section("A part to replace or take out")


def test_a_failure_after_the_fixer_goes_to_the_next_review_never_to_the_session():
    s3 = _s3()
    # Not a second fixer in the same review: it would have no finding number, and a failure
    # the first fixer rightly left alone would start fixer after fixer.
    assert "Under the rule, you fix nothing yourself: a failure goes in the findings table and under \"Failures\" in the next review's `previous.md`, whose Correctness reviewer reports it as a finding (section 10), so that review's fixer gets it." in s3
    assert "a failure goes to a fresh fixer" not in s3
    # It reaches that review: §1 lists it, and §10 (rule.md) has the reviewers report it, marked as any
    # other, so a failure on the base branch becomes a ticket and one the change causes blocks.
    text = (KIT / PANEL).read_text(encoding="utf-8")
    inputs = _flat(text.split("## 1. Gather the inputs", 1)[1].split("\n## 2.", 1)[0])
    assert "under \"Failures\", each failure step 5 of section 3 found after the last fixer, with the command that shows it and its output" in inputs
    rule = _flat(text.split("## 10. The rule for build reviewers", 1)[1])
    # One reviewer reports it, so it is never three entries with different marks.
    assert "as the Correctness reviewer, report each failure it lists under \"Failures\" as a finding, marked as any other, the failing command and its output as the reproducer" in rule


def test_the_older_steps_hand_the_fixes_and_reasons_to_the_fixer():
    s3 = _s3()
    assert "Under the rule, a blocking finding's reason is the fixer's (**The fix rule**)." in s3
    opening = (KIT / PANEL).read_text(encoding="utf-8").split("## 1.", 1)[0]
    assert "under the rule for build reviewers, a fresh fixer makes the fixes: section 3" in _flat(opening)


# --- round 2's findings ------------------------------------------------------


def test_a_splits_ticket_is_filed_before_the_fixer_takes_the_part_out():
    order = _the_fixer().split("The order, after each review:", 1)[1]
    assert "with `part.md` from that answer, a split's ticket filed first (`build-ticket`)" in order


def test_a_security_finding_is_never_taken_with_its_part():
    part = _section("A part to replace or take out")
    assert "A security finding never is: fix it or contest it as usual first; if its part is then taken out, its test goes with the part, and your report says so." in part
    assert "A security finding is never taken with its part" in _fix_rule()


def test_a_security_problem_the_change_adds_marked_a_ticket_is_never_contested():
    # review-panel §10 lets only a finding marked blocks be contested.
    for text in (_section("The fix rule"), _fix_rule()):
        assert "a security problem the change adds marked a ticket to fix it is fixed, never contested: it still blocks" in text.lower()
        # One whose reproducer already passes isn't fixed silently: the test is the fix.
        assert "already gives the right result, the test is the fix" in text


def test_a_refusal_of_the_guard_is_an_outcome_the_session_acts_on():
    inputs = _section("Your inputs")
    assert "the refusal is the answer, never a puzzle to get around" in inputs
    # The project's rule for a hook that timed out: split or simplify it.
    assert "a command whose hook timed out, split or simplify once" in inputs
    assert "refused again, or anything else it refuses, leave that finding **refused** (How to report) and go on to the next" in inputs
    assert "commits already made are pushed all the same" in _section("The fix rule")
    fixer = _the_fixer()
    # A refused finding is never left for a later review: §10's lines-already-reviewed rule would make it
    # a ticket, or no reviewer report it again, and the defect would merge (pass 1).
    assert "A finding the fixer reports refused by the guard is the owner's" in fixer
    assert "stop as `build-ticket` §5's \"Still red after three fix attempts\" says, the refusal as the reason, naming only a security finding's area" in fixer
    assert "A refused finding never waits for a later review" in fixer
    assert "head moved" not in fixer
