"""#447: the run charter's recommended answers carry their evidence (spec #436's
"Which questions": the charter's questions get the evidence rule only, with no
checks; answer 1 on #433, and the spec's story 19). Read as a text contract
on the `conductor` skill's kick-off, and on `docs/charter.md` §2 where it
describes asking, as `tests/test_decision_questions.py` reads the flow: each
test reads one part of the text, and checks what it requires rather than its
exact wording, so a later rewording that keeps the rule passes."""

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


def _charter_section() -> str:
    """`docs/charter.md` §2, as written."""
    text = CHARTER.read_text(encoding="utf-8")
    assert "\n## 2. The questions\n" in text
    return text.split("\n## 2. The questions\n", 1)[1].split("\n## ", 1)[0]


def _charter_asking() -> str:
    """`docs/charter.md` §2's opening paragraph, where it describes asking, flattened."""
    return _flatten(_charter_section().strip().split("\n\n", 1)[0])


def _charter_reuse() -> str:
    """`docs/charter.md` §2's "Same as last time?" paragraph, flattened."""
    found = [p for p in _charter_section().split("\n\n") if "Same as last time?" in p]
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


def test_what_it_rests_on_names_its_sources():
    rests = _item(_evidence(), "What it rests on")
    assert "profile setting" in rests
    assert "doctor line" in rests
    assert "default" in rests and "charter defaults" in rests
    assert "last run's charter" in rests
    # And what the pre-flight found, which today's recommendations in steps 1 and 3 rest on.
    assert "pre-flight finding" in rests
    # Named, not just pointed at: the setting by its key, the line by its id.
    assert re.search(r"\bkey\b", rests) and re.search(r"\bid\b", rests)


def test_what_it_gives_up_and_what_would_make_it_wrong_are_said():
    rule = _evidence()
    gives = _item(rule, "What it gives up")
    assert "option" in gives
    wrong = _item(rule, "What would make it wrong")
    assert "option" in wrong


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


def _points_to_the_flow(text: str) -> bool:
    return "flow" in text and '"Decision questions"' in text


def test_the_kick_off_points_to_the_flow_s_rules_for_decision_questions():
    assert _points_to_the_flow(_sentence(_evidence(), "Decision questions"))
    # And the flow's section exists, naming the charter's questions as `conductor`'s.
    flow = FLOW.read_text(encoding="utf-8")
    assert "\n## Decision questions\n" in flow
    intro = _flatten(flow.split("\n## Decision questions\n", 1)[1].split("\n- **", 1)[0])
    assert any("`conductor`" in s and "charter" in s for s in re.split(r"(?<=[.;])\s+", intro))


def test_the_charter_gets_the_evidence_rule_only_with_no_checks():
    rule = _evidence()
    assert "no checks" in rule
    # No planning check runs on the charter: the kick-off never calls the checker.
    assert "planning-checker" not in _kick_off()


def test_same_as_last_time_carries_its_evidence():
    reuse = _reuse()
    s = _sentence(reuse, "rests on")
    # It rests on the last run's charter, named by its tracking issue.
    assert "last run's charter" in s and "tracking issue" in s
    assert "gives up" in reuse
    # What would make it wrong: the old answers beside today's evidence, not the
    # diff, which shows only what reuse cleared or filled.
    wrong = _sentence(reuse, "make it wrong")
    assert "diff" in wrong and "reuse" in wrong
    assert "charter defaults" in reuse and "`github.approvals`" in reuse
    # Accepted gaps aren't compared: reuse clears them and step 1 asks them afresh.
    assert "step 1" in _sentence(reuse, "Accepted gaps")


def test_same_as_last_time_is_not_recommended_as_is_where_today_s_evidence_rules_an_answer_out():
    reuse = _reuse()
    s = _sentence(reuse, "own recommendation")
    # Such an answer has no basis to be reused as is: asked again on its own, with
    # its own recommendation, and "Same as last time?" recommended for the rest.
    assert "no basis" in s and "again" in s and "on its own" in s
    assert "Same as last time?" in s
    # What today's profile and queue rule out is compared by hand: `validate`
    # checks against the profile only once the end time is set.
    by_hand = _sentence(reuse, "by hand")
    assert "charter validate" in by_hand and "end time" in by_hand
    assert "merge queue is on" in by_hand and "`ui.explorer`" in by_hand


def test_same_as_last_time_names_a_difference_from_the_defaults_without_asking_it_again():
    # A reused answer that only differs from today's defaults is the owner's earlier
    # choice: named, with what today's doctor lines say of it, never asked again for that alone.
    s = _sentence(_reuse(), "earlier choice")
    assert "charter defaults" in s and "charter diff" in s
    assert "never" in s and "again" in s
    assert "`auto-merge`" in s and "reused `session`" in s


def test_same_as_last_time_asks_the_merge_mode_again_while_approvals_recommend_owner():
    # Doctor's `github.approvals` makes **owner** the merge question's recommended
    # answer (pre-flight's "Required approvals"); a reused mode that isn't `owner`
    # is asked again, whatever today's defaults show, so the two never disagree.
    reuse = _reuse()
    found = [s for s in re.split(r"(?<=[.;])\s+", reuse) if "`github.approvals`" in s and "again" in s]
    assert found, "a sentence asks the merge mode again for `github.approvals`"
    s = found[0]
    assert "owner" in s and "reused" in s and "defaults" in s
    assert "Required approvals" in s
    # The reused `auto-merge` no longer offered isn't set to the default while approvals
    # recommend owner: it is asked again too, so the exception never overrides them.
    ex = _sentence(reuse, "no longer offers")
    assert "`github.approvals`" in ex and "again" in ex and "owner" in ex
    d = [s for s in re.split(r"(?<=[.;])\s+", _charter_reuse()) if "approvals" in s]
    assert len(d) == 1, d
    assert "again" in d[0] and "owner" in d[0] and "auto-merge" in d[0]
    # The merge mode the merge question no longer offers keeps its own handling, named
    # as the one exception, for each reason it isn't offered.
    ex = _sentence(_reuse(), "no longer offers")
    assert "exception" in ex and "solo mode" in ex and "no CI" in ex and "no required checks" in ex


def test_recommended_answers_still_come_first_and_the_preset_is_still_recommended():
    assert "recommended answers first" in _flatten(_kick_off())
    sentences = re.split(r"(?<=[.;])\s+", _step(2))
    assert any("`run.preset`" in s and "recommended" in s for s in sentences)


def test_the_merge_queue_s_recommendation_carries_the_whole_evidence():
    step = _step(1)
    found = [b for b in step.split(" - ") if b.startswith("**The merge queue.**")]
    assert len(found) == 1, found
    s = _sentence(found[0], "with its reason")
    assert "gives up" in s and "make it wrong" in s


# --- docs/charter.md, where it describes asking -------------------------------


def test_the_charter_doc_says_each_recommended_answer_carries_its_evidence():
    p = _charter_asking()
    assert "rests on" in p and "gives up" in p and "make it wrong" in p
    for source in ("profile setting", "doctor line", "default", "last run's charter"):
        assert source in p, source
    assert _points_to_the_flow(_sentence(p, "Decision questions"))
    # A question without a basis has no default to put first.
    assert "first" in _sentence(p, "Asked in rounds") and "where it has one" in _sentence(p, "Asked in rounds")


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
    # A difference from today's defaults alone is the owner's earlier choice, never
    # a reason to ask again; an answer today's evidence rules out is asked on its own.
    s = _sentence(p, "earlier choice")
    assert "charter defaults" in s and "never" in s
    assert "rules out" in p and "on its own" in p
    # The reused `auto-merge` no longer offered is set to the new default, as the skill says.
    assert "no longer offers" in p and "new default" in p


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
