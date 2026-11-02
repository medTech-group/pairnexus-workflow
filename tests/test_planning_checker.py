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


def _frontmatter() -> dict:
    text = _text()
    assert text.startswith("---\n"), "the agent opens with its frontmatter"
    head = text.split("---\n", 2)[1]
    return dict(line.split(": ", 1) for line in head.strip().splitlines())


def _body() -> str:
    return " ".join(_text().split("---\n", 2)[2].split())


def _section(name: str) -> str:
    """One `## ` section of the body, flattened."""
    text = _text().split("---\n", 2)[2]
    assert f"\n## {name}\n" in text, f"the agent has a `## {name}` section"
    return " ".join(text.split(f"\n## {name}\n", 1)[1].split("\n## ", 1)[0].split())


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
    reads = _section("The reads")
    for read in ("Before a round", "The end check", "A re-read", "The breakdown check"):
        assert read in reads, read
    # A re-read reads only what changed, against the rest, and doesn't report the rest again.
    reread = reads.split("A re-read", 1)[1]
    assert "only what" in reread and "changed" in reread
    # A quick ticket's end check reads the draft against the item's issue (spec #436, "Quick tickets").
    assert "quick ticket" in reads and "item's issue" in reads and "decided for" in reads.lower()


# --- its inputs ---------------------------------------------------------------


def test_it_reads_the_scratch_directory_the_session_fills():
    inputs = _section("Your inputs")
    assert "/tmp/plan-check-<issue>-<read>-<n>/" in inputs
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
    assert "four kinds" in kinds
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


def test_the_breakdown_check_reads_landing_blockers_and_bars():
    reads = _section("The reads")
    bd = reads.split("The breakdown check", 1)[1]
    assert "exactly one" in bd
    for where in ("build ticket", "owner task", "edit to an existing issue"):
        assert where in bd, where
    assert "`## Blocked by`" in bd and "`## Bar`" in bd and "where the spec gives one" in bd
    # Criteria every ticket carries, and decisions that build nothing, are left out.
    assert "every ticket carries" in bd and "build nothing" in bd


def test_each_finding_is_marked_ask_or_fix():
    marks = _section("Ask or fix")
    assert "**ask**" in marks and "**fix**" in marks
    ask = marks.split("**ask**", 1)[1].split("**fix**", 1)[0]
    assert "changes what an answer means" in ask
    fix = marks.split("**fix**", 1)[1]
    assert "wording" in fix and "fact" in fix and "omission" in fix
    assert "changes no answer's meaning" in fix or "doesn't change what any answer means" in fix


def test_a_finding_about_the_owners_own_words_is_always_ask():
    marks = _section("Ask or fix")
    assert re.search(r"owner's own words[^.]*always \*\*ask\*\*", marks), marks


def test_in_the_breakdown_check_only_wording_is_a_fix():
    marks = _section("Ask or fix")
    bd = marks.split("breakdown check", 1)[1]
    assert "only wording" in bd
    assert "`## Blocked by`" in bd and "**ask**" in bd


def test_it_says_how_to_report_and_when_it_found_nothing():
    report = _section("How to report")
    for part in ("ask", "fix", "example", "kind"):
        assert part in report.lower(), part
    assert "found nothing" in report


# --- sensitive data -------------------------------------------------------------


def test_sensitive_data_is_left_out_of_its_inputs_and_its_findings():
    body = _body()
    assert "Sensitive data" in body and "`profile.md`" in body
    assert "left out" in body and "marked as left out" in body
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
    unreleased = notes.split("\n## ", 2)[0] if notes.count("\n## ") else notes
    assert "planning-checker" in unreleased and "#438" in unreleased
