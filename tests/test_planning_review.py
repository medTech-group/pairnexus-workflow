"""#235: the planning review in the kit's text (spec #232's seam 3, decisions on
#230): flow §1, §2 and §4, the review panel's planning section, the guided
start's Spec and Map steps, and the glossary, read as the kit-release tests read
skills."""

import re
import shlex

from changelog_notes import since_0110
from conftest import KIT
from workflow import cli, context, reviews


def _read(rel: str) -> str:
    return (KIT / rel).read_text(encoding="utf-8")


def _section(rel: str, start: str, end: str) -> str:
    text = _read(rel)
    assert start in text, f"{rel} has {start!r}"
    return text.split(start, 1)[1].split(end, 1)[0]


def _flatten(text: str) -> str:
    return " ".join(text.split())


def _flow(n: int) -> str:
    return _section("docs/flow.md", f"\n## {n}. ", "\n## ")


def _checklist(n: int) -> str:
    return _flow(n).split("**Checklist:**", 1)[1]


def _planning() -> str:
    """review-panel's planning review section, up to the next heading."""
    return _flatten(_section("skills/review-panel/SKILL.md", ". The planning review\n", "\n## "))


def _start_step(name: str) -> str:
    """The guided start's step 4 path, from its bold name to the next path."""
    step = _section("skills/start/SKILL.md", "## 4. Work through the plan", "\n## 5.")
    return _flatten(step.split(f"\n**{name}** (flow §", 1)[1].split("\n**", 1)[0])


# --- flow §1: a map decision ------------------------------------------------


def test_flow_1_posts_the_answers_word_for_word_on_the_decision_ticket():
    s1 = _flatten(_flow(1))
    assert "on the decision ticket" in s1
    assert "each question with the answer quoted word for word" in s1
    assert "never a summary" in s1
    # Word for word, but never sensitive data.
    assert "any sensitive data (`profile.md`) left out and marked as left out" in s1


def test_flow_1_reviews_the_adr_and_glossary_before_recording_and_offering():
    s1 = _flatten(_flow(1))
    answers = s1.index("each question with the answer quoted word for word")
    branch = s1.index("ADRs and the domain glossary")
    review = s1.index("planning review")
    then = s1.index("**Only then**")
    assert answers < branch < review < then
    # What waits for the review: the resolution, closing, the map and the PR.
    after = s1[then:]
    for words in ("a resolution comment", "close the ticket", "the map's \"Decisions so far\"", "Offer the pull request"):
        assert words in after, words
    assert "with its review records" in after
    assert "`review-panel`" in s1 and "until a round is clean" in s1
    # `wayfinder` records and closes straight away: the flow's order wins.
    assert "This order replaces `wayfinder`'s" in after


def test_flow_1_puts_a_fix_that_changes_a_decision_to_the_owner():
    s1 = _flatten(_flow(1))
    assert "A fix that would change what a decision means goes to the owner as a question first" in s1


def test_flow_1_checklist_carries_the_answers_and_the_review():
    c = _flatten(_checklist(1))
    assert "answers posted verbatim; reviewed until clean, records posted" in c
    # Reviewed before it's recorded and the PR offered.
    assert c.index("reviewed until clean") < c.index("recorded and closed")


# --- flow §2: a spec and a spec session's ADRs ------------------------------


def test_flow_2_says_where_the_answers_are_posted():
    s2 = _flatten(_flow(2))
    assert "each question with the answer quoted word for word" in s2
    assert "on the item's issue or the map's Destination item, when there is one" in s2
    assert "otherwise as the spec's first comment once it is published" in s2
    # Posted once the seams are agreed, so the seam answer is among them.
    assert s2.index("agree the test seams") < s2.index("**Post the owner's answers**")
    assert "the seams among them" in s2


def test_flow_2_reviews_the_spec_draft_before_publishing_it():
    s2 = _flatten(_flow(2))
    answers = s2.index("**Post the owner's answers**")
    review = s2.index("review the spec's draft")
    publish = s2.index("publish the reviewed text as is")
    assert answers < review < publish
    assert "then publish the spec" not in s2  # publishing is never named before the review
    assert "`workflow review-record --kind spec --body`" in s2
    assert "on the spec issue" in s2
    assert "an edit after the review makes the spec read as unreviewed" in s2


def test_flow_2_reviews_a_spec_sessions_adr_pull_request_before_offering_it():
    step7 = _flatten(_flow(2).split("7. **Commit what the session wrote:**", 1)[1].split("**Checklist:**", 1)[0])
    assert "planning review" in step7
    assert "before the pull request is offered" in step7
    assert "its round records on its commit" in step7


def test_flow_2_checklist_carries_the_answers_and_the_review():
    c = _flatten(_checklist(2))
    assert "answers posted verbatim; reviewed until clean, records posted" in c
    assert c.index("reviewed until clean") < c.index("spec published")


# --- flow §4: the hand merge ------------------------------------------------


def test_flow_4_says_a_hand_merge_of_planning_relies_on_the_earlier_review():
    s4 = _flatten(_flow(4))
    assert (
        "A planning pull request (a map decision's or a spec session's ADRs and glossary) that the owner merges "
        "by hand relies on the review made before it was offered (§1, §2): no check enforces it." in s4
    )
    # The next sentence is about merging, not the planning pull request.
    assert "no check enforces it. In an unattended run, merging follows the charter's `merge.mode`" in s4


def test_the_first_flow_context_still_carries_sections_1_and_2():
    # The context hook adds the flow's sections that fit; a planning session needs both.
    first = context.first_flow([KIT / "docs/flow.md"])
    for heading in ("\n## 1. Planning", "\n## 2. A spec and its build tickets"):
        assert heading in first, heading


# --- the review panel's planning section ------------------------------------


def test_the_review_panel_has_a_planning_section_and_says_so_up_front():
    text = _read("skills/review-panel/SKILL.md")
    head = text.split("\n---\n", 1)[0]
    assert "planning" in head  # the description, so the skill loads for it
    assert re.search(r"^## \d+\. The planning review$", text, re.M)


def test_the_planning_review_names_its_inputs():
    p = _planning()
    for words in (
        "the diff as `diff.patch`, or the spec's draft as `spec.md`",
        "the whole body exactly as it will be published, any footer or marker included",
        "the owner's answers as posted",
        "the ADRs and glossary",
        "the decision ticket and its map, or the item's issue",
        "the project's rules",
    ):
        assert words in p, words
    assert "never the session's summary" in p
    assert "Sensitive data (`profile.md`) is left out of them and marked as left out, never posted" in p


def test_the_planning_review_has_two_reviewers_and_no_standards_or_explorer():
    p = _planning()
    assert "**Correctness:** the `correctness-reviewer` agent" in p and "**Spec:** a general-purpose agent" in p
    assert "No Standards reviewer and no explorer" in p
    # Correctness, briefed for a document.
    assert "facts against the code" in p
    assert "contradictions with other ADRs" in p
    assert "the project's safety rules" in p
    # Spec, with its own brief against the answers.
    assert "its own brief" in p
    assert "word for word" in p
    for words in ("dropped", "reworded into a different meaning", "stated as settled where the owner left it open"):
        assert words in p, words


def test_the_planning_review_runs_both_every_round_up_to_the_profiles_rounds():
    p = _planning()
    assert "both reviewers run every round" in p
    # Up to the profile's rounds, never "at most" them: test_briefing_review keeps ticket sessions on the briefing's.
    assert "up to the profile's `run.review_rounds`" in p
    assert "never in a ticket session, so no briefing's rounds apply" in p
    assert "Anything still open after the last round goes to the owner" in p
    # A spec whose last round wasn't clean has a defined outcome.
    assert "A spec whose last round wasn't clean is fixed and published all the same" in p
    assert "until a clean round on its current body is posted" in p


def test_the_planning_review_puts_a_fix_that_changes_a_decision_to_the_owner():
    p = _planning()
    assert "fixes wording, facts and omissions" in p
    assert "A fix that would change what a decision means is put to the owner as a question first" in p


def test_the_planning_review_posts_both_record_kinds():
    p = _planning()
    assert "--kind round --round <n> --commit <sha> --reviewers spec,correctness" in p
    assert "--kind spec --round <n> --body" in p
    assert "on the spec issue" in p
    assert "keyed to its body" in p
    # The pull request is offered after the review: records wait for it (section 4).
    assert "keep each `record.md` and post them, oldest first, once it is open (section 4)" in p
    # The published body is read back: a footer or an edit would break the match.
    assert "read the published body back into a file" in p
    assert "The short hashes they name must match" in p


def test_the_planning_reviews_commands_run(tmp_path, capsys):
    """Each fenced command in the planning review, run through `cli.main` as written."""
    section = _section("skills/review-panel/SKILL.md", ". The planning review\n", "\n## ")
    commands = [c.strip() for c in re.findall(r"```\n(.*?)```", section, re.S)]
    assert len(commands) == 2
    spec = tmp_path / "spec.md"
    spec.write_text("## Problem Statement\n\nNotes are lost.\n", encoding="utf-8")
    sha = "a" * 40
    kinds = []
    for command in commands:
        words = shlex.split(command.split(" > ", 1)[0])
        assert words[:2] == ["WF", "review-record"]
        args = [
            {"<n>": "1", "<sha>": sha}.get(w, str(spec) if w.endswith("/spec.md") else w)
            for w in words[2:]
        ]
        assert cli.main(["review-record", *args]) == 0, command
        out, err = capsys.readouterr()
        assert not err
        (record,) = reviews.read([{"id": 1, "user": {"login": "owner"}, "body": out}])
        kinds.append(record.kind)
        assert record.reviewers == ("spec", "correctness") and record.clean
    assert kinds == ["round", "spec"]


# --- the guided start's Spec and Map steps ----------------------------------


def test_the_guided_starts_spec_step_names_the_answers_and_the_review():
    spec = _start_step("Spec")
    assert "word for word" in spec
    assert "planning review" in spec
    # The seams are agreed, the answers posted, the draft reviewed, then published.
    order = ["**These seams (Recommended)**", "Post their answers, the seams among them", "planning review", "Publish the reviewed text as is"]
    assert [spec.index(o) for o in order] == sorted(spec.index(o) for o in order)
    # Stopping mid-interview posts the answers so far, word for word.
    assert "**Stop here**: post their answers so far on the item's issue, each question with the answer quoted word for word" in spec


def test_the_guided_starts_map_step_names_the_answers_and_the_review():
    m = _start_step("Map")
    assert "word for word" in m
    assert "planning review" in m
    assert "before the ticket is closed and the pull request offered" in m


# --- the glossary and the changelog -----------------------------------------


def test_the_glossary_says_planning_is_reviewed_too():
    entry = _section("docs/glossary.md", "### Review panel\n", "\n### ")
    what = entry.split("**Why it matters", 1)[0]
    # Planning: a spec and a map's decisions.
    assert "a change, a [spec](#spec) or a [map](#map) decision" in what


def test_the_readme_tells_the_new_order():
    text = _flatten(_read("README.md"))
    assert "posts your answers on the decision's issue, each question with your answer quoted word for word" in text
    assert "only then writes the resolution as a comment, closes the issue" in text
    assert "has the spec's draft reviewed against them" in text
    assert "writes the answer as a comment, closes the issue" not in text


def test_the_changelog_notes_the_planning_review():
    notes = since_0110()
    head = "(#235, part of #232)."
    assert head in notes
    note = notes.split(head, 1)[1].split("\n\n**", 1)[0]
    headline = notes.split(head, 1)[0].rsplit("\n\n", 1)[1]
    assert "planning review" in headline
    for words in ("word for word", "spec records", "`run.review_rounds`", "no check enforces it", '"Review panel"'):
        assert words in note, words
    assert "tests/test_planning_review.py" in note
