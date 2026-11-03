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
    t = _flatten(text)
    return "Before each round" in t or "checked before it's asked" in t


# --- the rule: one read, before the round ----------------------------------------


def test_each_round_waits_for_one_read_by_planning_checker():
    r = _rule()
    s = _sentence(r, "`planning-checker`")
    assert "one read" in s
    assert re.search(r"before (?:the round is asked|they see)", s), s
    # It reads the round's recommendations, under the flow's rule.
    assert "recommendation" in s
    assert 'flow, "Decision questions"' in r


def test_it_reads_against_the_code_the_adrs_earlier_answers_and_the_rules():
    s = _sentence(_rule(), "against")
    for what in ("code", "ADR", "answers", "project's rules"):
        assert what in s, what


def test_its_inputs_are_the_round_and_every_round_posted_so_far():
    r = _rule()
    s = _sentence(r, "/tmp/plan-check-")
    assert "/tmp/plan-check-<issue>-round-<n>/" in s
    assert '"Your inputs"' in s
    # The round as it's about to be asked, with its recommendations and evidence.
    assert "about to ask" in s and "evidence" in s
    # The answers so far: every round posted for the same spec or decision, and
    # for a map's Destination item the map decisions it draws on, as the end check takes them.
    assert "every round posted" in s
    assert "Destination item" in s and "map decisions" in s


def test_the_agent_knows_the_round_read():
    # The agent this rule fills a directory for: its `round` read, and what a
    # finding says before a round.
    text = AGENT.read_text(encoding="utf-8")
    assert "`round`" in text
    assert "**Before a round:**" in text
    assert "before a round: the recommendation it would change" in text


# --- each finding: changes the recommendation, or "Check: …" -----------------------


def test_each_finding_changes_the_recommendation_or_is_shown_as_check():
    r = _rule()
    s = _sentence(r, "Each finding")
    assert "changes the recommendation" in s
    assert '"Check: …"' in s
    # Which change it: a fix, or an ask that your own recommendation was wrong.
    assert "**fix**" in s and "**ask**" in s and "wrong" in s


def test_a_finding_that_leaves_no_basis_drops_the_recommendation():
    s = _sentence(_rule(), "basis")
    assert '"(Recommended)"' in s


def test_a_check_about_their_own_words_is_asked_on_its_own():
    s = _sentence(_rule(), "own words")
    assert '"Check: …"' in s and "on its own" in s


def test_then_the_round_is_asked_and_its_check_never_repeated():
    r = _rule()
    assert _sentences(r, "Then ask the round"), "the round is asked once its check is done"
    s = _sentence(r, "never repeated")
    # What the check changed, and a question asked again on its own, aren't read again.
    assert "isn't read again" in s or "aren't read again" in s
    assert "on its own" in s


def test_the_round_post_lists_the_check_s_findings():
    s = _sentence(_rule(), "round's post")
    assert "findings" in s
    # Each with what became of it, so the counts can tell how many changed a recommendation.
    assert "changed the recommendation" in s and '"Check: …"' in s
    assert '"nothing found"' in s


def test_a_check_s_own_rounds_get_none():
    s = _sentence(_rule(), "own rounds")
    assert "none" in s
    for own in ("end check", "breakdown check", "held-back ticket", "quick ticket"):
        assert own in s, own


# --- each of start's rounds points to it -----------------------------------------


def test_the_interview_s_rounds_are_checked_before_they_re_asked():
    assert _points_to_the_check(_spec_step(1))


def test_the_seams_round_is_checked_before_it_s_asked():
    seams = [b for b in re.split(r"\n\s*- ", _spec_step(2)) if "Ask the seams" in b]
    assert len(seams) == 1, "the Spec path's step 2 has one bullet asking the seams"
    assert _points_to_the_check(seams[0])


def test_a_map_decision_s_rounds_are_checked_before_they_re_asked():
    m = _path("\n**Map** (flow §1)", "\n**Add to an existing issue:**")
    step = m.split("\n4. ", 1)[1].split("\n5. ", 1)[0]
    assert _points_to_the_check(step)


def test_edits_after_publishing_are_checked_before_they_re_asked():
    edit = [b for b in re.split(r"\n\s*- ", _spec_step(2)) if b.startswith("**Edit the spec first**")]
    assert len(edit) == 1, "the Spec path offers **Edit the spec first** once"
    assert _points_to_the_check(edit[0])
    add = _path("\n**Add to an existing issue:**", "\n## 5.")
    assert _points_to_the_check(add.split("\n1. ", 1)[1].split("\n2. ", 1)[0])


def test_the_check_s_own_rounds_keep_no_check_of_their_own():
    # The end check's and the breakdown check's rounds still say they get none.
    step2 = _flatten(_spec_step(2))
    assert "no check of its own before it's asked" in step2
    step3 = _flatten(_spec_step(3))
    assert "no check of its own before it's asked" in step3
    assert "no check before it" in step3


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
