"""#486: a decision question asked in a message is laid out in labelled parts
(the question, a "Recommended" part with its evidence, and the alternatives), so
a recommendation can't be mistaken for a decision already made (the owner's
feedback and answers L1 and L2 on #485's round 2). Read as a text contract on
`docs/flow.md`'s "Decision questions" and `start`'s interview step, as
`tests/test_decision_questions.py` and `tests/test_planning_review.py` read the
kit's text: each test checks what the rule requires, not its exact wording."""

import re

from changelog_notes import since_0110
from conftest import KIT


def _read(rel: str) -> str:
    return (KIT / rel).read_text(encoding="utf-8")


def _flatten(text: str) -> str:
    return " ".join(text.split())


def _block() -> str:
    text = _read("docs/flow.md")
    assert "\n## Decision questions\n" in text
    return text.split("\n## Decision questions\n", 1)[1].split("\n## ", 1)[0]


def _raw_rule(name: str) -> str:
    raw = _block()
    assert f"\n- **{name}" in raw, f"the flow's Decision questions has a `- **{name}` rule"
    return raw.split(f"\n- **{name}", 1)[1].split("\n- **", 1)[0]


def _rule(name: str) -> str:
    """One rule's prose, flattened, without its quoted example."""
    lines = _raw_rule(name).splitlines()
    return _flatten("\n".join(line for line in lines if not line.strip().startswith(">")))


def _sentence(text: str, word: str) -> str:
    found = [s for s in re.split(r"(?<=[.;])\s+", text) if word in s]
    assert len(found) == 1, f"one sentence names {word!r}: {found}"
    return found[0]


def _interview() -> str:
    """`start`'s Spec step 1, the interview, flattened."""
    text = _read("skills/start/SKILL.md")
    spec = text.split("\n**Spec** (flow §2)", 1)[1]
    return _flatten(spec.split("\n1. **The interview.**", 1)[1].split("\n2. **The spec.**", 1)[0])


# --- the flow's rule -----------------------------------------------------------


def test_the_flow_has_its_own_rule_for_a_question_asked_in_a_message():
    r = _rule("Asked in a message")
    # For a round asked in a message, as `grilling` lays one out, kept whole and unedited.
    assert "`grilling`" in r and "unedited" in r
    for part in ('"❓"', '"➡️"', "frontier"):
        assert part in r, part
    # Why: so a recommendation can't read as a decision already made.
    assert "decision already made" in r


def test_each_question_has_the_question_a_labelled_recommended_part_and_the_alternatives():
    r = _rule("Asked in a message")
    s = _sentence(r, "labelled parts")
    assert "the question" in s and "as a question" in s
    assert "➡️ **Recommended:**" in s
    assert "**Alternatives:**" in s and "one line each" in s


def test_the_recommended_part_carries_its_evidence_or_says_none_and_why():
    s = _sentence(_rule("Asked in a message"), "➡️ **Recommended:**")
    # The answer, then its evidence, as the Evidence rule names it.
    for label in ("*Rests on:*", "*Gives up:*", "*Wrong if:*"):
        assert label in s, label
    # No basis to prefer one: "Recommended: none", with why.
    assert '"➡️ Recommended: none"' in s and "with why" in s and "no basis" in s


def test_never_the_recommendation_as_the_first_sentence_or_a_bold_paragraph():
    s = _sentence(_rule("Asked in a message"), "Never")
    assert "first sentence" in s
    assert "bold paragraph of its own" in s


def test_a_posted_round_keeps_the_parts_as_columns_or_labels():
    s = _sentence(_rule("Asked in a message"), "posted")
    assert "same parts" in s
    assert '"Recommended"' in s and '"Alternatives"' in s and "columns" in s
    assert "same labels" in s


def test_choices_and_the_charter_s_questions_are_unchanged():
    s = _sentence(_rule("Asked in a message"), "`AskUserQuestion`")
    assert "unchanged" in s
    assert "first" in s and '"(Recommended)"' in s and "description" in s
    assert "charter" in s and "`conductor`" in s


def test_the_rule_shows_an_example_in_its_parts():
    lines = [line.strip() for line in _raw_rule("Asked in a message").splitlines() if line.strip().startswith(">")]
    example = "\n".join(lines)
    assert "❓" in example and "?" in example
    assert "➡️ **Recommended:**" in example
    assert "*Rests on:*" in example and "*Gives up:*" in example and "*Wrong if:*" in example
    assert "**Alternatives:**" in example
    # The recommendation isn't in the question's line.
    question = next(line for line in lines if "❓" in line)
    assert "Recommended" not in question


def test_the_evidence_rule_still_drops_recommended_without_a_basis():
    # The new rule sits beside the existing ones, which stay.
    s = _sentence(_rule("Evidence"), "(Recommended)")
    assert 'no "(Recommended)"' in s


# --- start's interview step ----------------------------------------------------


def test_start_s_interview_points_to_the_rule_whenever_a_round_is_asked_in_a_message():
    step = _interview()
    s = _sentence(step, "in a message")
    assert "**Asked in a message**" in s and '"Decision questions"' in s
    assert "flow" in s
    assert "➡️ **Recommended:**" in s and "**Alternatives:**" in s


def test_start_keeps_the_recommended_first_option_for_choices():
    step = _interview()
    assert "your recommended answer as the first option, with its evidence" in step
    # And the options rule for every choice stays.
    options = _flatten(_read("skills/start/SKILL.md")).split("- **Options:**", 1)[1].split("- **", 1)[0]
    assert 'it comes first, its label ending "(Recommended)"' in options


# --- the changelog -------------------------------------------------------------


def test_the_changelog_has_a_note_and_version_is_untouched():
    assert "(#486)" in since_0110()
    log = _read("CHANGELOG.md")
    start = log.index("## Unreleased\n")
    end = log.index("\n## ", start + 1)
    released = log[end + 4:].split("\n", 1)[0].strip()
    assert _read("VERSION").strip() == released
