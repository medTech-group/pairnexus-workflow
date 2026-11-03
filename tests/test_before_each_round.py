"""#445: spec #436's "Before each round" (answer 5 on #433), read as a text
contract on the shipped `start` (its "Decision questions" rules, and each place
it asks a round: the Spec step's interview and seams, the Map step's decisions,
and the edits after publishing) and `next`, as `tests/test_end_check.py` reads
the end check: each test reads one part of the text (a rule, a step, a sentence)
and checks what it requires rather than its exact wording, so a later rewording
that keeps the rule passes."""

import re

from changelog_notes import since_0110
from conftest import KIT

START = KIT / "skills/start/SKILL.md"
NEXT = KIT / "skills/next/SKILL.md"
AGENT = KIT / "agents/planning-checker.md"


def _flatten(text: str) -> str:
    return " ".join(text.split())


def _between(text: str, start: str, end: str) -> str:
    assert start in text, f"has {start!r}"
    return text.split(start, 1)[1].split(end, 1)[0]


def _start() -> str:
    return START.read_text(encoding="utf-8")


def _sentences(text: str, word: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.;])\s+", text) if word in s]


def _sentence(text: str, word: str) -> str:
    """The one sentence of `text` that names `word`."""
    found = _sentences(text, word)
    assert len(found) == 1, f"one sentence names {word!r}: {found}"
    return found[0]


def _block(text: str) -> str:
    """A skill's `**Decision questions**` paragraph and its rules, as written."""
    assert "\n**Decision questions**" in text, "the skill has a **Decision questions** paragraph"
    return text.split("\n**Decision questions**", 1)[1].split("\n\n", 1)[0]


def _rule() -> str:
    """`start`'s "Before each round" rule, among its decision-question rules, flattened."""
    raw = _block(_between(_start(), "\n## Choices\n", "\n## "))
    found = [r for r in raw.split("\n- **")[1:] if r.lower().startswith("before each round")]
    assert len(found) == 1, "start's Decision questions have one **Before each round** rule"
    return _flatten(found[0])


def _path(start: str, end: str) -> str:
    """One of `start`'s step 4 paths, from its opening to `end`, as written."""
    return _between(_start(), start, end)


def _spec_step(n: int) -> str:
    spec = _path("\n**Spec** (flow §2)", "\n**Map**")
    assert f"\n{n}. " in spec, f"the Spec path has a step {n}"
    return spec.split(f"\n{n}. ", 1)[1].split(f"\n{n + 1}. ", 1)[0]


def _points_to_the_check(text: str) -> bool:
    """The text says its rounds are checked before they're asked, and doesn't say they aren't."""
    t = _flatten(text)
    found = [m.start() for m in re.finditer(r"checked before it's asked|\"Before each round\"", t)]
    return bool(found) and not any(re.search(r"\b(isn't|not|never|no)\s+$", t[max(0, i - 12):i]) for i in found)


def _each_round() -> str:
    """`start`'s "Each round" rule, flattened."""
    raw = _block(_between(_start(), "\n## Choices\n", "\n## "))
    found = [r for r in raw.split("\n- **")[1:] if r.startswith("Each round**")]
    assert len(found) == 1, "start's Decision questions have one **Each round** rule"
    return _flatten(found[0])


# --- the rule: one read, before the round ----------------------------------------


def test_each_round_waits_for_one_read_by_planning_checker():
    r = _rule()
    s = _sentence(r, "`planning-checker`")
    assert "one read" in s
    assert re.search(r"before (?:the round is asked|they see)", s), s
    # It reads the round's recommendations, under the flow's rule.
    assert "recommendation" in s
    assert 'flow, "Decision questions"' in s


def test_a_round_without_a_recommendation_is_read_too():
    # Its options and what each gives up: "not checked" never reads as "clean".
    s = _sentence(_rule(), "`planning-checker`")
    assert re.search(r"with none|without one|no recommendation", s), s
    assert "options" in s


def test_it_reads_against_the_code_the_adrs_earlier_answers_and_the_rules():
    s = _sentence(_rule(), "against")
    for what in ("code", "ADR", "answers", "project's rules"):
        assert what in s, what


def test_its_inputs_are_the_round_and_every_round_posted_so_far():
    r = _rule()
    assert "/tmp/plan-check-<issue>-round-<n>/" in _sentence(r, "/tmp/plan-check-")
    assert '"Your inputs"' in _sentence(r, "/tmp/plan-check-")
    s = _sentence(r, "every post so far")
    # The round as it's about to be asked, with its recommendations and evidence.
    assert re.search(r"about to (?:ask|be asked)", s) and "evidence" in s
    # The answers so far with the checks' own posts (their fixes), as §8's
    # answers.md takes them, and for a map's Destination item the map decisions
    # it draws on, as the end check takes them.
    assert "checks' own posts" in s and "`answers.md`" in s
    assert "Destination item" in s and "map decisions" in s


def test_its_inputs_carry_the_words_that_raised_the_round():
    # A recommendation that contradicts the item's issue or the edit asked for is
    # caught before the round, not left open by a last read.
    r = _rule()
    s = _sentence(r, "raised the round")
    assert "word for word" in s and "**the owner's own words**" in s
    # Only what they asked for is tagged as theirs: their words in the item's
    # issue, or the change asked for in an edit after publishing.
    assert "item's issue" in s and "edit after publishing" in s
    # For a map's Destination item or a map decision, the map's own item's issue,
    # never the Destination line the session wrote on the map.
    assert "map's own item's issue" in s and "Destination item" in s and "map decision" in s
    assert "line on the map" not in s
    # The rest (text the session wrote) goes in untagged, never as their words.
    rest = _sentence(r, "untagged")
    assert "decision ticket" in rest and "Destination item" in rest
    # A fix question's draft and finding, and the published spec, for any round after publishing.
    assert "draft" in _sentence(r, "fix raises") and "finding" in _sentence(r, "fix raises")
    assert "as published" in _sentence(r, "Once the spec is published")


def test_the_agent_knows_the_round_read_and_its_inputs():
    # The directory's `<read>` is `round` in the agent too, and the agent expects
    # the round's questions and the words that raised it.
    text = AGENT.read_text(encoding="utf-8")
    assert re.search(r"`<read>` is .*`round`", text)
    inputs = _flatten(_between(text, "## Your inputs", "\n## "))
    s = _sentence(inputs, "Before a round")
    assert "raised the round" in s and "own words" in s
    # The same inputs as start's rule, so the two never disagree.
    tagged = _sentence(inputs, "That is their words")
    assert "map's own item's issue" in tagged and "map decision" in tagged and "edit after publishing" in tagged
    rest = _sentence(inputs, "untagged")
    for part in ("decision ticket", "Destination item", "draft", "finding", "as published"):
        assert part in rest, part
    reads = _flatten(_between(text, "## The reads", "\n## "))
    s = _sentence(reads, "**Before a round:**")
    assert "raised the round" in s and "options" in s


# --- each finding: changes the recommendation, or "Check: …" -----------------------


def test_each_finding_changes_the_recommendation_or_is_shown_as_check():
    s = _sentence(_rule(), "Each finding")
    assert re.search(r"changes? the recommendation", s)
    assert '"Check: …"' in s
    # Which change it: a fix, or an ask that your own recommendation was wrong.
    assert "**fix**" in s and "**ask**" in s and "wrong" in s


def test_a_finding_about_no_question_in_the_round_has_a_place():
    s = _sentence(_rule(), "no question in the round")
    assert "**fix**" in s and "round's post" in s
    assert "**ask**" in s and "question of its own" in s


def test_a_finding_that_leaves_no_basis_drops_the_recommendation():
    s = _sentence(_rule(), "basis")
    assert '"(Recommended)"' in s
    assert re.search(r"\b(drops?|removes?|takes? out)\b", s), s
    # Under the Evidence rule, not a copy of it.
    assert "**Evidence**" in s


def test_a_check_about_their_own_words_is_asked_on_its_own_as_part_of_the_round():
    s = _sentence(_rule(), "their own words")
    assert '"Check: …"' in s and "on its own" in s and '"Yes to all"' in s
    # Part of the round: asked after it, posted with it, not a new round with its own check.
    assert "part of it" in s and "posted with it" in s


def test_then_the_round_is_asked_and_its_check_never_repeated():
    r = _rule()
    assert re.search(r"\bThen ask the round\b|\bthe round is then asked\b", r, re.I)
    # One read covers what the check changed and each question asked on its own after it.
    s = _sentence(r, "never repeated")
    assert "findings" in s and "on its own" in s


def test_a_check_that_fails_leaves_the_round_marked_not_checked():
    s = _sentence(_rule(), "fails")
    assert "once more" in s and "ask the round" in s
    assert re.search(r"wasn't checked|not checked", s) and "why" in s
    post = _sentence(_each_round(), "check before the round")
    assert '"not checked"' in post


def test_the_round_post_lists_the_check_s_findings():
    # Where the post's contents live: the Each round rule.
    s = _sentence(_each_round(), "check before the round")
    assert "finding" in s
    # Each with what became of it, so the counts can tell how many changed a recommendation.
    assert "changed the recommendation" in s and '"Check: …"' in s
    # A fix outside the round is its own outcome, never counted as a changed recommendation.
    assert "outside the round" in s
    assert '"nothing found"' in s


def test_a_check_s_own_rounds_get_none():
    s = _sentence(_rule(), "own rounds")
    assert re.search(r"\bno check\b|\bnone\b", s)
    for own in ("end check", "breakdown check", "held-back ticket", "quick ticket"):
        assert own in s, own
    # Only those: none of the rounds the check covers is listed with them.
    for checked in ("interview", "seams", "map decision", "**Edit the spec first**", "**Fixes**", "existing issue"):
        assert checked not in s, checked


def test_points_to_the_check_catches_a_reversed_rule():
    assert _points_to_the_check("Each round is checked before it's asked.")
    assert not _points_to_the_check("The seams' round isn't checked before it's asked.")


# --- each of start's rounds points to it -----------------------------------------


def test_the_interview_s_rounds_are_checked_before_they_re_asked():
    assert _points_to_the_check(_spec_step(1))


def test_the_seams_round_is_checked_before_it_s_asked():
    seams = [b for b in re.split(r"\n\s*- ", _spec_step(2)) if "Ask the seams" in b]
    assert len(seams) == 1, "the Spec path's step 2 has one bullet asking the seams"
    assert _points_to_the_check(seams[0])


def test_a_map_decision_s_rounds_are_checked_before_they_re_asked():
    m = _path("\n**Map** (flow §1)", "\n**Add to an existing issue:**")
    step = _flatten(m.split("\n4. ", 1)[1].split("\n5. ", 1)[0])
    # The decision's own rounds, not the fix questions' pointer later in the step.
    assert _points_to_the_check(_sentence(step, "**Each decision,**"))


def test_edits_after_publishing_are_checked_before_they_re_asked():
    edit = [b for b in re.split(r"\n\s*- ", _spec_step(2)) if b.startswith("**Edit the spec first**")]
    assert len(edit) == 1, "the Spec path offers **Edit the spec first** once"
    assert _points_to_the_check(edit[0])
    add = _path("\n**Add to an existing issue:**", "\n## 5.")
    assert _points_to_the_check(add.split("\n1. ", 1)[1].split("\n2. ", 1)[0])


def test_a_planning_review_s_fix_questions_are_checked_before_they_re_asked():
    review = [b for b in re.split(r"\n\s*- ", _spec_step(2)) if b.startswith("Review the draft")]
    assert len(review) == 1, "the Spec path's step 2 has one bullet reviewing the draft"
    assert _points_to_the_check(review[0])


def test_a_map_decision_s_fix_questions_are_checked_before_they_re_asked():
    m = _flatten(_path("\n**Map** (flow §1)", "\n**Add to an existing issue:**"))
    s = _sentence(m, "a fix raises")
    assert _points_to_the_check(s)


# --- next ----------------------------------------------------------------------


def test_next_takes_the_check_before_each_round_from_start():
    text = NEXT.read_text(encoding="utf-8")
    s = _sentence(_flatten(_block(text).split("\n- **", 1)[0]), "Choices")
    assert "check before each round" in s


# --- changelog -----------------------------------------------------------------


def test_the_changelog_has_a_note_and_version_is_untouched():
    assert "(#445, part of spec #436)" in since_0110()
    log = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    start = log.index("## Unreleased\n")
    end = log.index("\n## ", start + 1)
    released = log[end + 4:].split("\n", 1)[0].strip()
    assert (KIT / "VERSION").read_text().strip() == released
