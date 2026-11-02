"""#438: the planning checker, `agents/planning-checker.md` (spec #436's "The
checker", answers 4, 12 and 22 on #433), read as a text contract as
`tests/test_planning_review.py` reads the skills: a later rewording that keeps
the rule passes. And `vendor.plan` ships it, as `tests/test_glossary.py` checks
the glossary."""

import re

from changelog_notes import since_0110
from conftest import KIT

from workflow import vendor

AGENT = KIT / "agents/planning-checker.md"


def _text() -> str:
    return AGENT.read_text(encoding="utf-8")


def _parts() -> tuple[str, str]:
    """(the frontmatter, the body)."""
    text = _text()
    assert text.startswith("---\n"), "the agent opens with its frontmatter"
    _, head, body = text.split("---\n", 2)
    return head, body


def _frontmatter() -> dict:
    return dict(line.split(": ", 1) for line in _parts()[0].strip().splitlines())


def _flatten(text: str) -> str:
    return " ".join(text.split())


def _body() -> str:
    return _flatten(_parts()[1])


def _raw_section(name: str) -> str:
    """One `## ` section of the body, as written."""
    body = _parts()[1]
    assert f"\n## {name}\n" in body, f"the agent has a `## {name}` section"
    return body.split(f"\n## {name}\n", 1)[1].split("\n## ", 1)[0]


def _section(name: str) -> str:
    """One `## ` section of the body, flattened."""
    return _flatten(_raw_section(name))


def _mark(name: str) -> str:
    """The `- **ask**` or `- **fix**` bullet of "Ask or fix", flattened."""
    return _bullet("Ask or fix", f"{name}**")


def _bullet(section: str, name: str) -> str:
    """One `- **name**` bullet of a section, flattened."""
    raw = _raw_section(section)
    assert f"\n- **{name}" in raw, f"`## {section}` has a bullet `{name}`"
    return _flatten(re.split(r"\n- |\n\n", raw.split(f"\n- **{name}", 1)[1], maxsplit=1)[0])


# --- who it is ----------------------------------------------------------------


def test_it_is_a_named_read_only_agent():
    fm = _frontmatter()
    assert fm["name"] == "planning-checker"
    assert {t.strip() for t in fm["tools"].split(",")} == {"Read", "Grep", "Glob"}
    body = _body()
    assert "you never edit" in body.lower() or "never edits" in body.lower()
    # No GitHub: the session fetches what it reads, and the session posts.
    assert "no GitHub" in body or "never post" in body.lower()


def test_its_description_says_which_reads_use_it():
    desc = _frontmatter()["description"]
    for read in ("before each round", "end check", "re-read", "breakdown check"):
        assert read in desc, read


def test_it_names_the_four_reads():
    bullets = re.findall(r"^- \*\*([^*]+)\*\*", _raw_section("The reads"), re.M)
    assert bullets == ["Before a round:", "The end check:", "A re-read:", "The breakdown check:"]
    # The scratch directory's `<read>` names the same four.
    assert "`round`, `end`, `reread` or `breakdown`" in _section("Your inputs")
    # A re-read reads only what changed, against the rest, and doesn't report the rest again.
    reread = _bullet("The reads", "A re-read")
    assert "only what changed since the read it follows, against all the rest" in reread
    # What changed includes the fixes the session made after that read (answer 22's "Wrong if").
    assert "the fixes the session made after that read" in reread
    assert "Report only findings that involve what changed" in reread
    # The breakdown check's round is re-read too (answer 24), with the breakdown's rules.
    assert "the breakdown check's round" in reread
    assert "A re-read of the breakdown check, or of a quick ticket, reads as that read does" in reread
    # A quick ticket's end check reads the draft against the item's issue (spec #436, "Quick tickets").
    end = _bullet("The reads", "The end check")
    assert "quick ticket" in end and "against the item's issue" in end and "Decided for you" in end


# --- its inputs ---------------------------------------------------------------


def test_it_reads_the_scratch_directory_the_session_fills():
    inputs = _section("Your inputs")
    assert "/tmp/plan-check-<issue>-<read>-<n>/" in inputs
    # `<issue>` is wherever the answers are posted (flow §1 and §2), the map for its Destination item.
    issue = inputs.split("`<issue>`", 1)[1].split("`<read>`", 1)[0]
    for where in ("the decision ticket", "the item's issue", "the spec's issue", "the map, for its Destination item"):
        assert where in issue, where
    # The fixes each post lists are read with the answers, so the checker knows what they settled.
    assert "the fixes each post lists" in inputs
    assert "the session fills" in inputs or "the session filled" in inputs
    for given in ("as posted", "the ADRs", "the glossary", "the project's rules", "the profile"):
        assert given in inputs, given
    # The issues the evidence cites, fetched as files: it has no GitHub of its own.
    assert re.search(r"issues the evidence cites[^.]*as files", inputs)
    # The repository files the evidence cites, in place.
    assert re.search(r"repository files the evidence cites[^.]*in place", inputs)


def test_the_breakdown_check_also_reads_the_spec_tickets_owner_tasks_and_edits():
    inputs = _section("Your inputs")
    breakdown = inputs.split("breakdown check", 1)[1]
    for given in ("the spec", "drafted tickets", "owner tasks", "edits to existing issues"):
        assert given in breakdown, given


# --- what it reports ----------------------------------------------------------


def test_it_reports_four_kinds_of_finding():
    kinds = _section("What to look for")
    assert re.search(r"four kinds of finding, and only these", kinds, re.I), kinds
    for kind in ("Conflicts between answers", "Combinations that break", "Gaps", "Wrong facts"):
        assert kind in kinds, kind
    assert "build ticket would have to guess" in kinds


def test_each_finding_needs_a_concrete_example_and_a_preference_isnt_one():
    kinds = _section("What to look for")
    assert "concrete example" in kinds
    # Either the session's steps and where they go wrong, or a quoted line with its file or issue.
    assert "steps" in kinds and "where they go wrong" in kinds
    assert "quoted line" in kinds and "file or issue" in kinds
    # Without one, or a preference: not reported.
    assert re.search(r"without (one|an example)[^.]*preference[^.]*(isn't|is not|aren't|not) reported", kinds), kinds
    # It doesn't re-argue a decision for its own sake, the owner's own words included.
    assert "re-argue" in kinds
    assert "owner's own words included" in kinds


def test_a_listed_fix_settles_like_a_confirmed_line():
    # Spec #436, "Records": a fix listed in a post, with no objection, stands the same way.
    kinds = _section("What to look for")
    conflicts = kinds.split("**Conflicts between answers:**", 1)[1].split("2. ", 1)[0]
    assert "confirmed replacement line settles it" in conflicts
    assert "a fix a post lists that the owner didn't object to" in conflicts
    facts = kinds.split("**Wrong facts:**", 1)[1]
    assert "A fact a listed fix already corrected isn't one" in facts


def test_the_breakdown_checks_findings_are_the_four_kinds():
    bd = _bullet("The reads", "The breakdown check")
    assert "lands in no ticket is a gap" in bd
    assert "one that lands in two, or a `## Bar` that doesn't fit the spec's, is a conflict" in bd
    assert "a `## Blocked by` that doesn't match what a ticket builds on is a combination that breaks" in bd


def test_the_breakdown_check_reads_landing_blockers_and_bars():
    bd = _bullet("The reads", "The breakdown check")
    assert "exactly one" in bd
    for where in ("build ticket", "owner task", "edit to an existing issue"):
        assert where in bd, where
    assert "`## Blocked by`" in bd and "`## Bar`" in bd and "where the spec gives one" in bd
    # Criteria every ticket carries, and decisions that build nothing, are left out.
    assert "every ticket carries" in bd and "build nothing" in bd


def test_each_finding_is_marked_ask_or_fix():
    ask = _mark("ask")
    assert "changes what an answer means" in ask
    fix = _mark("fix")
    assert "wording" in fix and "fact" in fix and "omission" in fix
    assert "changes no answer's meaning" in fix or "doesn't change what any answer means" in fix


def test_a_finding_about_the_owners_own_words_is_always_ask():
    marks = _section("Ask or fix")
    assert re.search(r"owner's own words[^.]*always \*\*ask\*\*", marks), marks


def test_on_a_quick_ticket_the_persons_own_words_are_always_ask():
    # Answer 4 ("an answer they typed, not one they accepted"), and spec #436's
    # "Its ask findings are asked first" on a quick ticket.
    marks = _section("Ask or fix")
    quick = marks.split("On a quick ticket", 1)[1].split("In the breakdown check", 1)[0]
    for part in ("the item's issue", "own words", "is **ask**"):
        assert part in quick, part
    # What they typed: a Change it, and a reply to an ask unless it accepted the recommendation.
    assert re.search(r"\*\*Change it\*\*[^)]*\*\*ask\*\*[^)]*\b(?:isn't|not|never|unless|except)\b[^)]*accepted", quick), quick
    assert not re.search(r"accepted or not|even an accepted", quick), quick


def test_a_quick_tickets_reread_gets_the_persons_replies_word_for_word():
    inputs = _section("Your inputs")
    quick = inputs.split("For a quick ticket's end check", 1)[1]
    for part in ("the person's replies", "**Change it**", "reply to an **ask**", "word for word", "tagged", "accepted recommendation", "own words"):
        assert part in quick, part


def test_a_reread_after_the_draft_follows_the_round_that_sent_its_questions():
    inputs = _section("Your inputs")
    assert "A re-read after the draft follows the planning review's round or the edit after publishing" in inputs
    assert "its fixes are the ones listed in that round's post" in inputs


def test_in_the_breakdown_check_only_wording_is_a_fix():
    marks = _section("Ask or fix")
    bd = marks.split("In the breakdown check", 1)[1]
    assert re.match(r", and its re-read, only wording is a \*\*fix\*\*", bd), bd[:80]
    assert "moves a criterion or a decision between tickets" in bd
    assert "changes a `## Blocked by`, is an **ask**" in bd


def test_an_ask_after_a_last_read_is_left_open_not_asked():
    # Spec #436: "A last read's findings ... are never asked: ... its ask findings are what's left."
    ask = _mark("ask")
    assert re.search(r"nothing is asked after the read \(a last re-read\), keeps it as left open", ask), ask
    # Answer 24: the breakdown check's re-read is the exception, its asks asked before publishing.
    assert re.search(r"breakdown check's re-read is the exception: its \*\*ask\*\* findings are asked", ask), ask
    assert "before the tickets are published" in ask


def test_it_says_how_to_report_and_when_it_found_nothing():
    report = _section("How to report")
    for part in ("**Kind:** one of the four", "**Mark:** ask or fix", "**About:**", "**Example:**"):
        assert part in report, part
    assert "found nothing" in report


def test_a_quick_tickets_decided_for_you_list_has_its_own_place_in_the_report():
    report = _section("How to report")
    assert "separate list" in report and '"Decided for you"' in report
    assert "with its evidence" in report
    assert "aren't findings" in report


# --- sensitive data -------------------------------------------------------------


def test_sensitive_data_is_left_out_of_its_inputs_and_its_findings():
    inputs = _section("Your inputs")
    assert re.search(r"\*\*Sensitive data\*\* \(`profile\.md`[^)]*\) is left out of your inputs and marked as left out", inputs), inputs
    # Met all the same: never quoted; named only when it is in the scratch directory.
    assert "never quote it. If it is in the scratch directory, name the file" in inputs
    report = _section("How to report")
    # Its findings follow the same rule: never quoted, marked as left out.
    assert "sensitive" in report.lower() and "left out" in report


# --- shipped ----------------------------------------------------------------------


def test_a_vendored_copy_carries_the_planning_checker():
    files = vendor.plan(KIT, None)
    assert files[".claude/agents/planning-checker.md"] == AGENT


def test_vendoring_writes_the_planning_checker_into_a_project(tmp_path):
    vendor.install(KIT, tmp_path, None, no_mattpocock=True)
    assert (tmp_path / ".claude/agents/planning-checker.md").read_text(encoding="utf-8") == _text()


def test_the_changelog_names_the_planning_checker():
    notes = since_0110()
    assert "`planning-checker`" in notes and "(#438, part of spec #436)" in notes
