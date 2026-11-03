"""#448: spec #436's "Counts" (answer 9 on #433), read as a text contract on the
shipped `start` (its "Decision questions" rules, and each place a piece of
planning ends: a spec's tickets published, a later edit to a published spec, a
quick ticket published, a map decision recorded) and `next`, as
`tests/test_end_check.py` reads the end check: each test reads one part of the
text (a rule, a step, a sentence) and checks what it requires rather than its
exact wording, so a later rewording that keeps the rule passes. The counts are
posted by the session, not computed by a command (the spec's "Not tested")."""

import re

from changelog_notes import since_0110
from conftest import KIT

START = KIT / "skills/start/SKILL.md"
NEXT = KIT / "skills/next/SKILL.md"
NAME = '"Planning counts"'


def _flatten(text: str) -> str:
    return " ".join(text.split())


def _between(text: str, start: str, end: str) -> str:
    assert start in text, f"has {start!r}"
    return text.split(start, 1)[1].split(end, 1)[0]


def _start() -> str:
    return START.read_text(encoding="utf-8")


def _sentences(text: str, word: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.;:])\s+(?=[A-Z*\"`(])", text) if word in s]


def _sentence(text: str, word: str) -> str:
    """The one sentence of `text` that names `word`."""
    found = _sentences(text, word)
    assert len(found) == 1, f"one sentence names {word!r}: {found}"
    return found[0]


def _block(text: str) -> str:
    """A skill's `**Decision questions**` paragraph and its rules, as written."""
    assert "\n**Decision questions**" in text, "the skill has a **Decision questions** paragraph"
    return text.split("\n**Decision questions**", 1)[1].split("\n\n", 1)[0]


def _top(lead: str) -> str:
    """The one decision-question rule of `start` opening with `lead`, as written."""
    raw = _block(_between(_start(), "\n## Choices\n", "\n## "))
    found = [r for r in raw.split("\n- **")[1:] if r.lower().startswith(lead)]
    assert len(found) == 1, f"start's Decision questions have one rule opening {lead!r}"
    return found[0]


def _rule_raw() -> str:
    """`start`'s "Planning counts" rule: what the comment counts, and how."""
    return _top("planning counts")


def _where_raw() -> str:
    """`start`'s rule on where the counts' comment goes, and when."""
    return _top("where the planning counts go")


def _rule() -> str:
    return _flatten(_rule_raw())


def _sub(word: str, raw: str | None = None) -> str:
    """The one sub-bullet of the rule (or of `raw`) whose opening names `word`, flattened."""
    subs = re.split(r"\n\s+- ", _rule_raw() if raw is None else raw)[1:]
    found = [s for s in subs if word.lower() in re.sub(r"\*", "", s)[:40].lower()]
    assert len(found) == 1, f"the rule has one sub-bullet opening with {word!r}: {found}"
    return _flatten(found[0])


def _path(start: str, end: str) -> str:
    return _between(_start(), start, end)


def _spec_step(n: int) -> str:
    spec = _path("\n**Spec** (flow §2)", "\n**Map**")
    assert f"\n{n}. " in spec, f"the Spec path has a step {n}"
    return spec.split(f"\n{n}. ", 1)[1].split(f"\n{n + 1}. ", 1)[0]


def _points_to_the_counts(text: str) -> bool:
    """The text names the counts' comment, and doesn't say it isn't posted."""
    t = _flatten(text)
    found = [m.start() for m in re.finditer(r"\"Planning counts", t)]
    return bool(found) and not any(re.search(r"\b(isn't|not|never|no)\s+(\w+\s+){0,2}$", t[max(0, i - 24):i]) for i in found)


# --- what the comment counts ---------------------------------------------------


def test_the_rule_names_the_comment():
    rule = _rule()
    assert NAME in rule, "the comment is headed \"Planning counts\""


def test_it_counts_the_before_round_checks_findings_and_how_many_changed_a_recommendation():
    s = _sub("before-round")
    assert "findings" in s
    assert "changed a recommendation" in s or "changed the recommendation" in s
    # Counted from the round posts' first outcome only (#445's three outcomes),
    # so a "Check: …" or a fix made outside the round never counts as a change.
    assert "\"changed the recommendation\"" in s and "only" in s


def test_it_counts_the_ask_and_fix_findings_of_the_end_check_the_re_reads_and_the_breakdown_check():
    s = _sub("ask")
    for read in ("end check", "re-read", "breakdown check"):
        assert read in s, read
    assert "**ask**" in s and "**fix**" in s
    # The breakdown check's own re-read is counted too, not folded away.
    assert re.search(r"breakdown check'?s? (and|with) its re-read|breakdown re-read", s), s


def test_it_counts_the_answers_replaced_after_the_end_check():
    s = _sub("replaced")
    assert "after the end check" in s or "after its \"End check\" post" in s
    # Read from the confirmed lines, the record of a replacement.
    assert "confirmed" in s


def test_it_counts_the_questions_sent_after_the_draft():
    s = _sub("after the draft")
    assert "questions" in s and "**Fixes**" in s


def test_it_counts_each_planning_rounds_findings_by_reviewer():
    s = _sub("planning round")
    assert "by reviewer" in s and "§8" in s


def test_a_step_that_did_not_run_is_never_a_zero():
    s = _sentence(_rule(), "didn't run")
    assert "says so" in s
    assert "0" in s, "a 0 is kept for a read that found nothing"


def test_counts_come_from_the_posts_and_an_unknown_count_is_never_guessed():
    rule = _rule()
    s = _sentence(rule, "posts on GitHub")
    assert "round posts" in s and "headed" in s and "confirmed" in s
    s = _sentence(rule, "\"not known\"")
    assert "never a guess" in s


# --- where and when it is posted ------------------------------------------------


def test_a_spec_posts_it_on_its_issue_once_its_tickets_are_published():
    s = _sub("a spec", _where_raw())
    assert "its issue" in s or "the spec's issue" in s
    assert "tickets are published" in s


def test_an_edit_before_the_tickets_counts_in_the_specs_comment():
    s = _sub("a spec", _where_raw())
    assert re.search(r"edit made before (its|the) tickets", s), s


def test_a_spec_session_that_stops_before_its_tickets_posts_what_it_counted():
    s = _sentence(_sub("a spec", _where_raw()), "so far")
    assert "stops" in s and "Planning counts so far" in s


def test_a_later_edit_to_a_published_spec_adds_its_own():
    s = _sub("a later edit", _where_raw())
    assert "its own" in s and "spec's issue" in s
    assert "published" in s


def test_a_quick_ticket_posts_it_on_the_ticket():
    s = _sub("a quick ticket", _where_raw())
    assert "on the ticket" in s and "published" in s
    assert "end check" in s and "re-read" in s
    # Each of the guided start's routes to a quick ticket ends there.
    assert "**File the fix as a ticket**" in s and "**Ready to build**" in s


def test_a_map_decision_posts_it_on_its_decision_ticket():
    s = _sub("a map decision", _where_raw())
    assert "decision ticket" in s
    assert "before it's closed" in s or "before closing it" in s


# --- each place planning ends points to the rule --------------------------------


def test_the_spec_path_posts_it_once_the_tickets_are_published():
    step = _spec_step(3)
    publish = step.split("**Then publish.**", 1)[1].split("\n   - **", 1)[0]
    done = _flatten(publish.split("\n     4. ", 1)[1])
    assert '"Breakdown published"' in done
    assert done.index('"Breakdown published"') < done.index(NAME)
    assert _points_to_the_counts(done)


def test_the_spec_paths_stop_after_publishing_posts_what_it_counted_so_far():
    step = _flatten(_spec_step(2))
    stop = step.split("**Stop here**", 1)[1].split(" - **", 1)[0]
    assert "\"Planning counts so far\"" in stop


def test_the_quick_ticket_posts_it_once_published():
    quick = _path("**Quick ticket** (flow §2", "**Find the cause first:**")
    step2 = _flatten(quick.split("\n2. ", 1)[1].split("\n3. ", 1)[0])
    assert "`ready-for-agent`" in step2
    assert _points_to_the_counts(step2)


def test_the_map_decision_posts_it_before_its_ticket_is_closed():
    m = _path("\n**Map** (flow §1)", "\n**Add to an existing issue:**")
    step4 = _flatten(m.split("\n4. ", 1)[1].split("\n5. ", 1)[0])
    s = _sentence(step4, NAME)
    assert "decision ticket" in s and _points_to_the_counts(s)


def test_an_edit_after_publishing_posts_its_own():
    add = _flatten(_path("\n**Add to an existing issue:**", "\n## 5."))
    s = _sentence(add, NAME)
    assert re.search(r"\bown\b", s) and "spec's issue" in s and _points_to_the_counts(s)
    later = _flatten(_path("**A spec or ticket to change after it's published:**", "\n- **A decision to undo"))
    assert _points_to_the_counts(later)


def test_next_points_to_starts_rule():
    block = _flatten(_block(NEXT.read_text(encoding="utf-8")))
    s = _sentence(block, NAME)
    assert "`start`" in s and _points_to_the_counts(s)


# --- docs -----------------------------------------------------------------------


def test_the_changelog_notes_the_counts():
    notes = since_0110()
    assert "#448" in notes
    note = notes.split("(#448", 1)[0].rsplit("\n\n", 1)[-1] + notes.split("(#448", 1)[1].split("\n\n**", 1)[0]
    assert NAME in note or "Planning counts" in note
    assert "tests/test_planning_counts.py" in note
