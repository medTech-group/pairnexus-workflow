"""#447: the run charter's recommended answers carry their evidence (spec #436's
"Which questions": the charter's questions get the evidence rule only, with no
checks; answer 19 on #433). Read as a text contract on the `conductor` skill's
kick-off, and on `docs/charter.md` §2 where it describes asking, as
`tests/test_decision_questions.py` reads the flow: each test reads one part of
the text, and checks what it requires rather than its exact wording, so a later
rewording that keeps the rule passes."""

import re

from changelog_notes import since_0110
from conftest import KIT

CONDUCTOR = KIT / "skills/conductor/SKILL.md"
CHARTER = KIT / "docs/charter.md"
FLOW = KIT / "docs/flow.md"


def _flatten(text: str) -> str:
    return " ".join(text.split())


def _kick_off() -> str:
    """The conductor's "### 2. The kick-off", as written."""
    text = CONDUCTOR.read_text(encoding="utf-8")
    assert "\n### 2. The kick-off\n" in text
    return text.split("\n### 2. The kick-off\n", 1)[1].split("\n## ", 1)[0].split("\n### ", 1)[0]


def _evidence() -> str:
    """The kick-off's evidence rule: its `**Each recommended answer` paragraph
    and the bullets under it, up to the kick-off's numbered steps, flattened."""
    raw = _kick_off()
    assert "\n**Each recommended answer" in raw, "the kick-off has an `**Each recommended answer` rule"
    return _flatten(raw.split("\n**Each recommended answer", 1)[1].split("\n1. ", 1)[0])


def _item(text: str, name: str) -> str:
    """One `- **name` bullet of a flattened rule."""
    assert f"- **{name}" in text, f"the rule has a `- **{name}` bullet"
    return text.split(f"- **{name}", 1)[1].split(" - **", 1)[0]


def _step(n: int) -> str:
    """Step n of the kick-off's numbered list, flattened."""
    raw = _kick_off()
    assert f"\n{n}. " in raw
    return _flatten(raw.split(f"\n{n}. ", 1)[1].split(f"\n{n + 1}. ", 1)[0].split("\nThen:\n", 1)[0])


def _reuse() -> str:
    """Step 2's "Same as last time?" bullet, flattened."""
    step = _step(2)
    assert "Same as last time?" in step
    found = [b for b in step.split(" - ") if "Same as last time?" in b]
    assert len(found) == 1, found
    return found[0]


def _charter_asking() -> str:
    """`docs/charter.md` §2's opening paragraph, where it describes asking, flattened."""
    text = CHARTER.read_text(encoding="utf-8")
    assert "\n## 2. The questions\n" in text
    section = text.split("\n## 2. The questions\n", 1)[1].split("\n## ", 1)[0]
    return _flatten(section.strip().split("\n\n", 1)[0])


def _charter_reuse() -> str:
    """`docs/charter.md` §2's "Same as last time?" paragraph, flattened."""
    text = CHARTER.read_text(encoding="utf-8")
    section = text.split("\n## 2. The questions\n", 1)[1].split("\n## ", 1)[0]
    found = [p for p in section.split("\n\n") if "Same as last time?" in p]
    assert len(found) == 1, found
    return _flatten(found[0])


def _sentence(text: str, word: str) -> str:
    found = [s for s in re.split(r"(?<=[.;])\s+", text) if word in s]
    assert len(found) == 1, f"one sentence names {word!r}: {found}"
    return found[0]


# --- the rule in the conductor's kick-off -----------------------------------


def test_the_kick_off_says_each_recommended_answer_carries_its_evidence():
    rule = _evidence()
    # It names the three parts, each its own bullet.
    for part in ("What it rests on", "What it gives up", "What would make it wrong"):
        assert f"- **{part}" in rule, part


def test_what_it_rests_on_names_the_four_sources():
    rests = _item(_evidence(), "What it rests on")
    assert "profile setting" in rests
    assert "doctor line" in rests
    assert "default" in rests and "`WF charter defaults`" in rests
    assert "last run's charter" in rests
    # Named, not just pointed at: the setting by its key, the line by its id.
    assert "key" in rests and "id" in rests


def test_what_it_gives_up_and_what_would_make_it_wrong_are_said():
    rule = _evidence()
    gives = _item(rule, "What it gives up")
    assert "other option" in gives
    wrong = _item(rule, "What would make it wrong")
    assert "another option" in wrong or "other option" in wrong


def test_the_rule_covers_every_kick_off_question_that_recommends_one():
    s = _sentence(_evidence(), "every kick-off question")
    # Step 1's findings, step 2's charter questions and step 3's plan, by step.
    for step in ("step 1", "step 2", "step 3"):
        assert step in s, step
    assert "Same as last time?" in s


def test_a_question_with_no_basis_has_no_recommended_answer():
    none = _item(_evidence(), "No basis, no recommendation")
    # Fail closed: a default whose basis can't be named isn't recommended.
    assert "can't name" in none
    assert "no recommended answer" in none or "none marked" in none
    assert "(Recommended)" in none
    # The end time is the owner's: never recommended.
    assert "end time" in none


def test_the_kick_off_points_to_the_flow_s_rules_for_decision_questions():
    rule = _evidence()
    assert 'flow, "Decision questions"' in rule
    # And the flow's section exists, naming the charter's questions as `conductor`'s.
    flow = FLOW.read_text(encoding="utf-8")
    assert "\n## Decision questions\n" in flow
    intro = _flatten(flow.split("\n## Decision questions\n", 1)[1].split("\n- **", 1)[0])
    assert "`conductor`" in _sentence(intro, "charter")


def test_the_charter_gets_the_evidence_rule_only_with_no_checks():
    rule = _evidence()
    assert "no checks" in rule
    # No planning check runs on the charter: the conductor never calls the checker.
    assert "planning-checker" not in CONDUCTOR.read_text(encoding="utf-8")


def test_same_as_last_time_carries_its_evidence():
    reuse = _reuse()
    s = _sentence(reuse, "rests on")
    # It rests on the last run's charter, named by its tracking issue.
    assert "last run's charter" in s and "tracking issue" in s
    assert "gives up" in reuse
    # What would make it wrong: what changed since, as the diff, doctor and the profile show it.
    wrong = _sentence(reuse, "wrong")
    assert "charter diff" in wrong
    assert "doctor" in wrong and "profile" in wrong


def test_the_existing_recommendations_keep_their_place():
    # The defaults don't change (accepted limits): recommended answers still come first.
    assert "recommended answers first" in _flatten(_kick_off())
    assert "marked recommended (`recommended`)" in _step(2)


# --- docs/charter.md, where it describes asking -------------------------------


def test_the_charter_doc_says_each_recommended_answer_carries_its_evidence():
    p = _charter_asking()
    assert "rests on" in p and "gives up" in p and "make it wrong" in p
    for source in ("profile setting", "doctor line", "default", "last run's charter"):
        assert source in p, source
    assert 'flow, "Decision questions"' in p


def test_the_charter_doc_has_no_recommendation_without_a_basis_and_no_checks():
    p = _charter_asking()
    s = _sentence(p, "no recommended answer")
    assert "basis" in s or "can't name" in s
    assert "end time" in p
    # Evidence only: nothing checks it.
    assert "Nothing checks" in p or "no checks" in p


def test_the_charter_doc_s_same_as_last_time_carries_its_evidence():
    p = _charter_reuse()
    assert "rests on" in p and "last run's charter" in p
    assert "gives up" in p and "wrong" in p


# --- the changelog ----------------------------------------------------------


def test_the_changelog_has_a_note_and_version_is_untouched():
    # Read as the other notes are, so a release that moves them under its heading still passes.
    assert "(#447, part of spec #436)" in since_0110()
    log = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    start = log.index("## Unreleased\n")
    end = log.index("\n## ", start + 1)
    # No version bump: VERSION is still the last release's.
    released = log[end + 4:].split("\n", 1)[0].strip()
    assert (KIT / "VERSION").read_text().strip() == released
