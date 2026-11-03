"""#446: spec #436's "Before each round" (answer 5 on #433) for the questions
`review-panel` §8's **Fixes** sends after a draft, read as a text contract on
§8, as `tests/test_planning_after_draft.py` reads it: each test reads one part
of the section (a bold paragraph, a sentence) and checks what it requires
rather than its exact wording, so a later rewording that keeps the rule passes.
The same check in `start` is `tests/test_before_each_round.py`'s (#445)."""

import re

from changelog_notes import since_0110
from conftest import KIT

SKILL = KIT / "skills/review-panel/SKILL.md"
START = KIT / "skills/start/SKILL.md"
AGENT = KIT / "agents/planning-checker.md"
NAME = "Before each question round:"


def _flatten(text: str) -> str:
    return " ".join(text.split())


def _planning_raw() -> str:
    """review-panel's planning review section, as written, up to the next heading."""
    text = SKILL.read_text(encoding="utf-8")
    assert ". The planning review\n" in text
    return text.split(". The planning review\n", 1)[1].split("\n## ", 1)[0]


def _para(name: str) -> str:
    """The §8 paragraph that opens with `**name`, up to the next bold paragraph, flattened."""
    raw = _planning_raw()
    assert raw.count(f"\n**{name}") == 1, f"§8 has one `**{name}` paragraph"
    return _flatten(raw.split(f"\n**{name}", 1)[1].split("\n\n**", 1)[0])


def _check() -> str:
    return _para(NAME)


def _sentences(text: str, word: str) -> list[str]:
    """The sentences of `text` that name `word`. §8 also breaks a sentence at a
    colon before a capital, a bold name or a quote, so this splits there too."""
    return [s for s in re.split(r"(?<=[.;:])\s+(?=[A-Z*\"(`])", text) if word.lower() in s.lower()]


def _sentence(text: str, word: str) -> str:
    found = _sentences(text, word)
    assert len(found) == 1, f"one sentence names {word!r}: {found}"
    return found[0]


def _points_to_the_check(text: str) -> bool:
    """The text says its question rounds are checked before they're asked, and doesn't say they aren't."""
    t = _flatten(text)
    found = [m.start() for m in re.finditer(r"checked before it's asked|waits for its check|\*\*Before each question round\*\*", t)]
    return bool(found) and not any(re.search(r"\b(isn't|not|never|no)\s+$", t[max(0, i - 12):i]) for i in found)


# --- the check: one read, before the question round ------------------------------


def test_each_question_round_waits_for_one_read_by_planning_checker():
    s = _sentence(_check(), "`planning-checker`")
    assert "one read" in s and "waits for its check" in s
    assert re.search(r"before (?:the owner sees it|it's asked)", s), s
    assert "recommendation" in s
    # Under the flow's rule, named as the other skills name it.
    assert 'flow, "Decision questions"' in s


def test_a_question_round_without_a_recommendation_is_read_too():
    s = _sentence(_check(), "`planning-checker`")
    assert re.search(r"with none|without one|no recommendation", s), s
    assert "options" in s


def test_it_comes_between_fixes_and_the_re_read():
    # Checked before it's asked, posted once answered, then re-read: in that order.
    raw = _planning_raw()
    fixes, check, reread = (raw.index(f"\n**{n}") for n in ("Fixes:", NAME, "The re-read:"))
    assert fixes < check < reread


def test_fixes_sends_each_question_round_to_its_check():
    fixes = _para("Fixes:")
    assert _points_to_the_check(_sentence(fixes, "**Before each question round**"))


def test_one_check_per_round_whether_start_or_this_section_asks_it():
    # start's "Before each round" already covers these questions (#445): the two
    # name the same check, and a round never gets two.
    s = _sentence(_check(), "`start`'s \"Before each round\"")
    assert "one read" in s
    assert re.search(r"never two|only once|not twice", s), s


def test_points_to_the_check_catches_a_reversed_rule():
    assert _points_to_the_check("Each question round waits for its check before it's asked.")
    assert not _points_to_the_check("A question round isn't checked before it's asked.")


# --- its inputs ------------------------------------------------------------------


def test_its_directory_is_the_round_read_s_as_start_and_the_agent_name_it():
    s = _sentence(_check(), "/tmp/plan-check-")
    assert "/tmp/plan-check-<issue>-round-<n>/" in s
    assert '"Your inputs"' in s
    # <issue> is where the question round will be posted, as start's rule says.
    assert "posted" in s
    assert "/tmp/plan-check-<issue>-round-<n>/" in START.read_text(encoding="utf-8")
    assert re.search(r"`<read>` is .*`round`", AGENT.read_text(encoding="utf-8"))


def test_its_inputs_are_the_question_round_and_every_post_so_far():
    s = _sentence(_check(), "as you're about to ask them")
    assert "recommendation" in s and "evidence" in s
    assert "`answers.md`" in s and "checks' own posts" in s


def test_its_inputs_carry_the_owner_s_words_tagged_and_the_rest_untagged():
    c = _check()
    s = _sentence(c, "word for word")
    assert "**the owner's own words**" in s
    assert "item's issue" in s and "edit after publishing" in s
    assert "map's own item's issue" in s
    rest = _sentence(c, "untagged")
    # A fix question's own inputs: what the planning round reviewed and the finding behind it.
    assert re.search(r"draft or diff", rest) and "finding behind" in rest
    assert "decision ticket" in rest and "Destination item" in rest
    assert "as published" in rest


def test_it_reads_against_the_code_the_adrs_earlier_answers_and_the_rules():
    s = _sentence(_check(), "against")
    for what in ("code", "ADR", "answers", "project's rules"):
        assert what in s, what


# --- each finding: changes the recommendation, or "Check: …" ------------------------


def test_each_finding_changes_the_recommendation_or_is_shown_as_check():
    s = _sentence(_check(), "Each finding")
    assert re.search(r"changes? the recommendation", s)
    assert '"Check: …"' in s
    assert "**fix**" in s and "**ask**" in s and "wrong" in s


def test_the_rest_of_the_finding_rules_are_start_s():
    # A finding about no question in the round, a recommendation left without a
    # basis, and a check about the owner's own words, as start's rule handles them.
    s = _sentence(_check(), "no question in the round")
    assert '"(Recommended)"' in s and "own words" in s
    assert "`start`'s rule" in s


def test_then_the_round_is_asked_and_its_check_never_repeated():
    c = _check()
    assert re.search(r"\bThen ask the question round\b", c)
    s = _sentence(c, "never repeated")
    assert "findings" in s and "on its own" in s
    # The re-read after it reads the answers' changes, not the round again.
    assert "re-read" in s


def test_a_check_that_fails_leaves_the_round_marked_not_checked():
    s = _sentence(_check(), "fails")
    assert "once more" in s
    assert re.search(r"wasn't checked|not checked", s) and "why" in s


def test_the_question_round_s_post_lists_the_check_s_findings():
    s = _sentence(_check(), "outside the round")
    assert "post" in s and "finding" in s
    assert "changed the recommendation" in s and '"Check: …"' in s
    assert '"nothing found"' in s and '"not checked"' in s


# --- an edit after publishing ------------------------------------------------------


def test_an_edit_s_question_rounds_are_checked_before_they_re_asked():
    edit = _para("An edit after publishing")
    assert _points_to_the_check(_sentence(edit, "**Before each question round**"))


# --- the changelog ---------------------------------------------------------------


def test_the_changelog_notes_it_and_version_is_untouched():
    notes = since_0110()
    head = "(#446, part of spec #436)."
    assert head in notes
    note = notes.split(head, 1)[1].split("\n\n**", 1)[0]
    for words in ("`planning-checker`", '"Check: …"', "**Fixes**", "never repeated"):
        assert words in note, words
    assert "tests/test_fix_questions_checked.py" in note
    log = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    start = log.index("## Unreleased\n")
    end = log.index("\n## ", start + 1)
    released = log[end + 4:].split("\n", 1)[0].strip()
    assert (KIT / "VERSION").read_text().strip() == released
