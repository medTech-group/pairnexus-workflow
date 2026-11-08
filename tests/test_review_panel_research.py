"""#513: the research check and the look in `review-panel` (spec #505, "The
research check"). Seam 2: the shipped text, read as text contracts, as
`tests/test_research_flow.py` reads the flow: each test reads one part of the
skill's section and checks what it requires rather than its exact wording.

The section points to the flow's "Research" rule (#511) and to flow §4 item 4
(#509) rather than restating them (answer 45), and to the `research-checker`
agent's own text for how a note's claims are read (#571 owns that file)."""

import re

from changelog_notes import since_0110
from conftest import KIT

PANEL = KIT / "skills/review-panel/SKILL.md"
HEADING = "## The research check and the look"


def _flat(text: str) -> str:
    return " ".join(text.split())


def _text() -> str:
    return PANEL.read_text(encoding="utf-8")


def _raw() -> str:
    """The section as written, from below its heading to the next `## `."""
    text = _text()
    assert f"\n{HEADING}\n" in text, f"review-panel has a `{HEADING}` section"
    return text.split(f"\n{HEADING}\n", 1)[1].split("\n## ", 1)[0]


def _section() -> str:
    return _flat(_raw())


def _part(name: str) -> str:
    """One `**name` paragraph or list item of the section, flattened, up to the next bold lead-in."""
    raw = _raw()
    assert f"**{name}" in raw, f"the section has a `**{name}` part"
    after = raw.split(f"**{name}", 1)[1]
    return _flat(re.split(r"\n(?:\d+\. |- )?\*\*", after, maxsplit=1)[0])


def _sentence(text: str, word: str) -> str:
    found = [s for s in re.split(r"(?<=[.;:])\s+", text) if word in s]
    assert found, f"a sentence names {word!r}"
    return found[0]


def _fence_after(text: str, words: str) -> str:
    after = text.split(words, 1)[1]
    return after.split("```", 2)[1]


# --- where it sits --------------------------------------------------------------


def test_the_section_sits_before_the_rule_for_build_reviewers_which_stays_last():
    # §10 is copied from its heading to the end as `rule.md`: the research
    # section must never end up in a build reviewer's rule.
    text = _text()
    assert text.index(f"\n{HEADING}\n") < text.index("\n## 10. The rule for build reviewers\n")
    assert text.index("\n## 8. The planning review\n") < text.index(f"\n{HEADING}\n")
    rule = text.split("\n## 10. The rule for build reviewers\n", 1)[1]
    assert "## " not in rule.replace("### ", ""), "§10 stays the last section"
    assert "research-checker" not in rule


def test_the_skill_s_description_names_the_research_check():
    head = _text().split("---", 2)[1]
    description = head.split("description:", 1)[1].split("\n", 1)[0]
    assert "research check" in description and "research pull request" in description


def test_the_section_is_for_research_pull_requests_and_not_a_build_review():
    s = _section()
    assert "research pull request" in s and "`docs/research/`" in s
    # One pass each, never rounds until clean, with none of the build panel's reviewers.
    assert "one pass each" in s and "never rounds until clean" in s
    for word in ("Standards", "Spec", "Correctness"):
        assert word in _sentence(s, "Standards"), word
    assert "section 10" in s or "§10" in s


# --- pointers, not restatements ---------------------------------------------------


def test_it_points_to_the_flow_s_research_rule_and_4_item_4_rather_than_restating_them():
    s = _section()
    assert "the flow's \"Research\" section" in s and "research check rule" in s
    assert "§4 item 4" in s and "**A pull request of research notes**" in s
    # The merge rule's own words stay in §4 alone (#511's one source).
    assert "counts its research check record as its clean review" not in s
    assert "**(unconfirmed)**" not in s


def test_it_points_to_the_agent_s_text_for_how_claims_are_read():
    s = _section()
    assert "`agents/research-checker.md`" in s or "the agent's file" in s
    s = _sentence(s, "how it reads")
    assert "research-checker" in s or "agent" in s
    # The validator's labels are the agent's, never restated here (#571 owns them).
    for label in ("observed (public source)", "observed (real person)", "*simulated*"):
        assert label not in _section(), label


# --- the research check -----------------------------------------------------------


def test_one_research_checker_one_pass_reading_the_saved_copies():
    part = _part("The research check")
    assert "one `research-checker`" in part and "one pass" in part
    assert "saved copies" in part and "never a live page" in part
    assert "`pairnexus-workflow:research-checker`" in part
    assert "commit.txt" in part


def test_the_session_posts_one_comment_the_record_first_then_the_listed_claims():
    raw = _raw()
    part = _part("The comment")
    assert "one comment" in part
    assert part.index("record") < part.index("claims")
    assert "code fence" in part
    fence = _flat(_fence_after(raw, "**The comment"))
    assert "WF review-record --kind research --round 1 --commit <sha> --reviewers research" in fence
    assert "--clean" in fence or "--not-clean" in fence
    # The guard refuses posting a file the same command writes.
    assert "next command" in part or "second command" in part
    assert "<!-- workflow:agent -->" in part
    assert "section 4" in part


# --- the look ---------------------------------------------------------------------


def test_the_look_reads_the_changed_lines_and_the_listed_claims():
    part = _part("The look")
    assert "fresh `research-checker`" in part
    assert "`research_needs_look`" in part
    assert "changed.patch" in part and "claims.md" in part
    assert "`since.patch`" in part and "section 1" in part
    assert "--round 2" in part


def test_a_listed_claim_whose_line_didn_t_change_counts_as_still_wrong():
    part = _part("The look")
    s = _sentence(part, "didn't change")
    assert "still wrong" in s
    assert "not clean" in part


def test_a_context_line_of_changed_patch_never_counts_as_a_changed_line():
    # `changed.patch` comes from `git diff`, with 3 context lines around each
    # change: a listed claim on a context line didn't change, so it is still wrong.
    part = _part("The look")
    assert "no line of `changed.patch` holds it" not in part
    s = _sentence(part, "added (`+`)")
    assert "removed (`-`)" in s and "changed.patch" in s
    s = _sentence(part, "context line")
    assert "doesn't count" in s or "don't count" in s


def test_the_look_s_comment_lists_every_claim_still_wrong_not_only_the_checker_s():
    # A listed claim whose line didn't change is still wrong even when the
    # checker calls it fine: the comment lists it too, as the mark step marks it.
    part = _part("The look")
    s = _sentence(part, "every claim still wrong")
    assert "comment" in s
    after = part.split("every claim still wrong", 1)[1]
    assert "the checker reported" in after and "didn't change" in after


def test_no_changed_patch_means_no_look_and_no_look_record():
    # Section 1's fallback (no `since.patch`: the whole change is new) has no
    # meaning for the look's checker, which gets no `diff.patch`: with no
    # `changed.patch`, a look would read nothing and come out clean.
    part = _part("The look")
    s = _sentence(part, "run no look")
    assert "changed.patch" in s and "no look record" in s
    assert "whole change as new" not in part
    # With one written, the look runs as before.
    assert "give a fresh `research-checker`" in part and "`changed.patch`: the lines changed" in part


def test_the_mark_goes_on_after_the_look_and_never_before():
    part = _part("The mark")
    assert "after the look" in part
    assert "never before" in part or "not before" in part
    assert "no further round" in part or "no third" in part
    assert "only marks" in part
    assert "§4 item 4" in part


def test_records_count_at_merge_by_4_item_4_and_merge_check_reads_them():
    s = _section()
    assert "`research_none`" in s and "`research_needs_look`" in s and "`research_needs_marks`" in s


# --- the changelog ----------------------------------------------------------------


def test_the_changelog_notes_it_and_version_is_untouched():
    notes = since_0110()
    head = next((l for l in notes.splitlines() if "(#513, part of spec #505)" in l), None)
    assert head, "a changelog note for #513 under ## Unreleased"
    assert notes.index("## Unreleased") < notes.index(head)
    log = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    released = re.findall(r"^## (\d+\.\d+\.\d+)$", log, re.M)
    assert (KIT / "VERSION").read_text(encoding="utf-8").strip() == released[0]
