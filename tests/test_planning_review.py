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
    # A decision that writes nothing has nothing to review, and says so.
    assert (
        "A decision that changes no ADR or glossary skips this step and step 4's commit "
        "(research notes still go on their branch), and its checklist says so" in s1
    )
    assert "A research or task decision posts what the owner said, if anything" in s1


def test_flow_1_checklist_carries_the_answers_and_the_review():
    c = _flatten(_checklist(1))
    assert "answers posted verbatim; reviewed until clean, records posted" in c
    # Reviewed before it's recorded and the PR offered.
    assert c.index("reviewed until clean") < c.index("recorded and closed")


# --- flow §2: a spec and a spec session's ADRs ------------------------------


def test_flow_2_says_where_the_answers_are_posted():
    s2 = _flatten(_flow(2))
    assert "each question with the answer quoted word for word" in s2
    assert "on the item's issue or the map's Destination item (a comment on the map naming it), when there is one" in s2
    assert "Otherwise they are the spec's first comment once it is published, before its records" in s2
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
    assert "on the spec's issue" in s2
    assert "the map's Destination item (a comment on the map naming it)" in s2
    assert "an edit after the review makes the spec read as unreviewed" in s2


def test_flow_2_reviews_a_spec_sessions_adr_pull_request_before_offering_it():
    step7 = _flatten(_flow(2).split("7. **Commit what the session wrote:**", 1)[1].split("**Checklist:**", 1)[0])
    assert "planning review" in step7
    assert "before the pull request is offered" in step7
    assert "its review records on its commit" in step7


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
    # A Destination item's spec is held to the map decisions it is written from.
    assert "A map's Destination item's spec takes, as well, the answers posted on the map decisions it draws on" in p
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
    assert "on the spec's issue" in p
    assert "keyed to its body" in p
    # The pull request is offered after the review: records wait for it (section 4).
    assert 'kept until the pull request opens (section 4, "No pull request yet")' in p
    # The published body is read back before the records are posted.
    assert "Before posting the records, check nothing changed on the way" in p
    assert "never writing a `record.md`" in p
    assert "if it still differs, post no records and say so in the handover" in p
    assert "When the answers are the spec's first comment (flow §2), post them before the records" in p
    # The body is fetched, never retyped; the fixes after an unclean last round stay in the file the check reads.
    assert "never retyped (`gh api repos/<repo>/issues/<spec> --jq .body > /tmp/review-<issue>-spec-check/published.md`" in p
    assert "make the fixes in that same `spec.md`, once its `record.md` is written, and publish that" in p
    # An edit after publishing is reviewed again before tickets.
    assert "the edited body gets another planning round, its own spec record, before any tickets are written from it" in p
    # The owner's words for the edit are posted first, and are the Spec reviewer's input.
    assert "First post the owner's words for the change on the spec's issue, each request or answer quoted word for word" in p
    assert "an edit after publishing takes the owner's words for the change, posted on the spec's issue" in p
    # The read-back check's directory is made before the body is saved there.
    assert p.index("mkdir -p /tmp/review-<issue>-spec-check") < p.index("> /tmp/review-<issue>-spec-check/published.md")


def test_the_planning_reviews_scratch_directories_never_mix_a_spec_and_a_pull_request():
    p = _planning()
    assert "`/tmp/review-<issue>-spec-r<n>/` for a spec's draft, `/tmp/review-<issue>-pr-r<n>/` for a pull request" in p
    commands = _commands_of_planning()
    assert "/tmp/review-<issue>-pr-r<n>/record.md" in commands[0]
    assert "/tmp/review-<issue>-spec-r<n>/spec.md" in commands[1] and "/tmp/review-<issue>-spec-r<n>/record.md" in commands[1]
    assert "record.md" not in commands[2]  # the read-back check writes no record


def _commands_of_planning() -> list[str]:
    section = _section("skills/review-panel/SKILL.md", ". The planning review\n", "\n## ")
    return [c.strip() for c in re.findall(r"```\n(.*?)```", section, re.S)]


def _run_review_record(command: str, capsys, paths: dict[str, str]) -> str:
    """One `WF review-record` line, its redirect or pipe left off, through `cli.main`."""
    words = shlex.split(re.split(r" [>|] ", command, maxsplit=1)[0])
    assert words[:2] == ["WF", "review-record"]
    args = [paths.get(w, next((v for k, v in paths.items() if w.endswith(k)), w)) for w in words[2:]]
    assert cli.main(["review-record", *args]) == 0, command
    out, err = capsys.readouterr()
    assert not err
    return out


def test_the_planning_reviews_commands_run(tmp_path, capsys):
    """Each fenced command in the planning review, run through `cli.main` as written."""
    commands = _commands_of_planning()
    assert len(commands) == 3
    spec = tmp_path / "spec.md"
    spec.write_text("## Problem Statement\n\nNotes are lost.\n\n<!-- workflow:agent -->\n", encoding="utf-8")
    paths = {"<n>": "1", "<sha>": "a" * 40, "/spec.md": str(spec)}
    kinds = []
    for command in commands[:2]:
        out = _run_review_record(command, capsys, paths)
        (record,) = reviews.read([{"id": 1, "user": {"login": "owner"}, "body": out}])
        kinds.append(record.kind)
        assert record.reviewers == ("spec", "correctness") and record.clean
    assert kinds == ["round", "spec"]


def test_the_read_back_check_matches_githubs_copy_and_catches_a_footer(tmp_path, capsys):
    """The check's two lines print the full hash; GitHub's \\r\\n copy matches, a footer doesn't."""
    check = _commands_of_planning()[2].splitlines()
    assert len(check) == 2 and all("| grep -o 'body=[0-9a-f]*'" in line for line in check)
    text = "## Problem Statement\n\nNotes are lost.\n\n<!-- workflow:agent -->\n"
    spec = tmp_path / "spec.md"
    spec.write_text(text, encoding="utf-8")

    def hashes(published: str) -> list[str]:
        back = tmp_path / "published.md"
        back.write_bytes(published.encode("utf-8"))
        paths = {"<n>": "1", "/published.md": str(back), "/spec.md": str(spec)}
        return [re.search(r"body=[0-9a-f]{64}", _run_review_record(line, capsys, paths)).group() for line in check]

    as_github_returns_it = text.replace("\n", "\r\n").rstrip("\r\n")
    first, second = hashes(as_github_returns_it)
    assert first == second
    first, second = hashes(text + "\n---\n_Generated by a tool_\n")
    assert first != second


# --- the guided start's Spec and Map steps ----------------------------------


def test_the_guided_starts_spec_step_names_the_answers_and_the_review():
    spec = _start_step("Spec")
    assert "word for word" in spec
    assert "planning review" in spec
    # The seams are agreed, the answers posted, the draft reviewed, then published.
    order = ["**These seams (Recommended)**", "Post their answers, the seams among them", "planning review", "Publish the reviewed text as is"]
    assert [spec.index(o) for o in order] == sorted(spec.index(o) for o in order)
    # An edit after publishing is reviewed again before the tickets.
    assert "**Edit the spec first**: the edited body gets another planning round and its spec record (`review-panel` §8) before the tickets" in spec
    # The published body is checked before the records go on it.
    assert spec.index("Publish the reviewed text as is") < spec.index("Check the published body's hash") < spec.index("then post each round's spec record")
    # Adding to a published spec reviews it again too.
    step = _flatten(_section("skills/start/SKILL.md", "\n**Add to an existing issue:**\n", "\n## "))
    assert "If it's a spec, its edited body gets another planning round and its spec record (`review-panel` §8)" in step
    # Before the tickets are changed to match.
    assert step.index("another planning round") < step.index("change them the same way")
    # A change mid-session (step 7) too.
    course = _flatten(_section("skills/start/SKILL.md", "\n## 7. Changing course", "\n## "))
    assert "a spec you edit gets another planning round and its spec record (`review-panel` §8)" in course
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
    assert "An edited spec reads as unreviewed until it has another planning round" in text


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
