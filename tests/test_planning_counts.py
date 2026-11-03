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
    s = _sub("before each round")
    assert "findings" in s
    assert "changed a recommendation" in s or "changed the recommendation" in s
    # Counted from the round posts' first outcome only (#445's three outcomes),
    # so a "Check: …" or a fix made outside the round never counts as a change.
    assert "\"changed the recommendation\"" in s and "only" in s
    # A round whose read failed is named, so it never reads as a clean one.
    assert "\"not checked\"" in s


def test_it_counts_the_ask_and_fix_findings_of_the_end_check_the_re_reads_and_the_breakdown_check():
    s = _sub("ask")
    for read in ("end check", "re-read", "breakdown check"):
        assert read in s, read
    assert "**ask**" in s and "**fix**" in s
    # The breakdown check's own re-read is counted too, not folded away.
    assert re.search(r"breakdown check'?s? (and|with) its re-read|breakdown re-read", s), s


def test_it_counts_the_answers_replaced_after_the_end_check():
    s = _sub("replaced")
    # Read from the confirmed lines, the record of a replacement, from the end
    # check's own round on: its post holds the lines its round confirmed.
    assert "confirmed" in s
    assert "end check's round on" in s and "\"End check\" post included" in s
    # A later edit's comment counts its own lines, not the spec's again.
    assert "only the lines its own rounds posted" in _sentence(s, "later edit")


def test_it_counts_the_questions_sent_after_the_draft():
    s = _sub("after the draft")
    assert "questions" in s and "**Fixes**" in s


def test_it_counts_each_planning_rounds_findings_by_reviewer():
    s = _sub("planning round")
    assert "by reviewer" in s and "§8" in s


def test_a_step_that_did_not_run_is_never_a_zero():
    s = _sentence(_rule(), "didn't run")
    assert "says so" in s
    assert re.search(r"\b0\b[^.]*found nothing", s), "a 0 is kept for a read that found nothing"


def test_counts_come_from_the_posts_and_an_unknown_count_is_never_guessed():
    rule = _rule()
    s = _sentence(rule, "posts on GitHub")
    assert "round posts" in s and "confirmed" in s
    for head in ('"End check"', '"Re-read"', '"Breakdown check"', '"Breakdown re-read"'):
        assert head in s, head
    # What no post says is counted as it ran: §8's re-reads post no headed comment.
    s = _sentence(rule, "as you ran it")
    assert "re-reads after the draft" in s and "planning rounds" in s
    s = _sentence(rule, "\"not known\"")
    assert "never a guess" in s


# --- where and when it is posted ------------------------------------------------


def test_a_spec_posts_it_on_its_issue_once_its_tickets_are_published():
    s = _sub("a spec", _where_raw())
    assert "its issue" in s or "the spec's issue" in s
    assert "tickets are published" in s
    # After the session's ADR or glossary pull request's planning review
    # (flow §2 step 7), which comes after the tickets, so its rounds count.
    first = _sentences(s, "tickets are published")[0]
    assert "pull request" in first and "planning review" in first
    for part in ("interview", "end check", "breakdown check", "pull request's rounds"):
        assert part in first, part


def test_an_edit_before_the_tickets_counts_in_the_specs_comment():
    s = _sub("a spec", _where_raw())
    assert re.search(r"edit made before (its|the) tickets", s), s


def test_a_spec_session_that_stops_before_its_tickets_posts_what_it_counted():
    where = _sub("a spec", _where_raw())
    s = _sentence(where, "Planning counts so far")
    assert "however it ends" in s and "no post says" in s
    # The session that posts the counts adds every such comment up.
    assert "adds up every such comment" in where
    # One that dies after publishing is picked up by the next that carries on.
    s = _sentence(where, '"Breakdown published"')
    assert "carries on" in s and "posts it" in s


def test_a_later_edit_to_a_published_spec_adds_its_own():
    s = _sub("a later edit", _where_raw())
    assert "its own" in s and "spec's issue" in s
    assert "once its tickets are published" in s


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


def test_the_spec_path_posts_it_once_the_tickets_are_published_and_its_pull_request_reviewed():
    step = _flatten(_spec_step(4))
    assert step.startswith("**Commit what the session wrote,**")
    s = _sentence(step, NAME)
    assert "planning review" in s and "tickets are published" in s
    assert "spec's issue" in s or "on its issue" in s
    assert _points_to_the_counts(s)
    # Not posted from the breakdown's publish steps, before the pull request's rounds.
    assert NAME not in _spec_step(3)


def test_the_spec_paths_stop_after_publishing_posts_what_it_counted_so_far():
    step = _flatten(_spec_step(2))
    stop = step.split("**Stop here**", 1)[1].split(" - **", 1)[0]
    assert "\"Planning counts so far\"" in stop


def test_the_quick_ticket_posts_it_once_published():
    quick = _path("**Quick ticket** (flow §2", "**Find the cause first:**")
    step2 = _flatten(quick.split("\n2. ", 1)[1].split("\n3. ", 1)[0])
    assert "`ready-for-agent`" in step2
    assert _points_to_the_counts(step2)
    # After it's published, not before.
    assert step2.index("`ready-for-agent`") < step2.index(NAME)


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
    # Before its tickets are published, an edit counts in the spec's own comment.
    assert "tickets are published and changed" in _sentence(later, NAME)


def test_a_fresh_session_for_the_tickets_posts_what_it_counted_first():
    long = _flatten(_path("**When the session gets long in the middle of an item:**", "\n## 7."))
    assert "\"Planning counts so far\"" in _sentence(long, "to-tickets")


def test_next_points_to_starts_rule():
    rules = _block(NEXT.read_text(encoding="utf-8")).split("\n- **")[1:]
    found = [r for r in rules if NAME in r]
    assert len(found) == 1, found
    s = _flatten(found[0])
    assert "`start`" in s and _points_to_the_counts(s)


# --- docs -----------------------------------------------------------------------


def test_the_changelog_has_a_note_and_version_is_untouched():
    notes = since_0110()
    assert "(#448, part of spec #436)" in notes
    assert "tests/test_planning_counts.py" in notes
    log = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    start = log.index("## Unreleased\n")
    end = log.index("\n## ", start + 1)
    released = log[end + 4:].split("\n", 1)[0].strip()
    assert (KIT / "VERSION").read_text().strip() == released
