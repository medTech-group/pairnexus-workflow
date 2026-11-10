"""#663: with no required check waived and the profile not `ci.none`, the
evidence never holds the merge. `build-ticket` §6 is read as a text contract
(seam 2), and the briefing's **Merging** lines are rendered through the CLI with
a charter that waives no check, one that waives one, and a `ci.none` profile, as
`tests/test_briefing_review.py` renders briefings."""

import json
import os
import subprocess
import sys
from pathlib import Path

from changelog_notes import since_0110
from workflow import charter

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"
TEMPLATE = KIT / "templates/ticket-session-prompt.md"
BUILD_TICKET = KIT / "skills/build-ticket/SKILL.md"
SLOTS = {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "none", "wake_trigger": "trig_01abc"}
EVIDENCE = "python3 .claude/workflow/bin/workflow.py evidence --base-ref origin/main"


def _section(text, start, end):
    assert start in text, start
    i = text.index(start)
    return text[i:text.index(end, i + len(start))]


def _six():
    return _section(BUILD_TICKET.read_text(), "## 6. Post the evidence and merge", "## 7. End each turn")


def _step(n):
    six = _six()
    return _section(six, f"\n{n}. **", f"\n{n + 1}. **")


# ---------- build-ticket §6 (seam 2) ----------


def test_the_evidence_never_holds_the_merge_without_a_waiver_or_ci_none():
    two = _step(2)
    assert "**Otherwise the evidence never holds the merge:**" in two
    otherwise = two[two.index("**Otherwise the evidence never holds the merge:**"):]
    # started once the review is clean, as a tracked background task, never `&`
    assert "Once the review is clean" in otherwise
    assert "tracked background task" in otherwise and "never `&` inside a shell call" in otherwise
    # merge-check and the merge go on without waiting for it
    assert "without waiting for it" in otherwise
    assert "run `WF merge-check`" in otherwise
    assert "queue it, merge it or arm auto-merge" in otherwise
    # the report is posted when it ends, naming its head, even after the merge
    assert "When it ends, post its report on the PR, naming the head it covers" in otherwise
    assert "even if the PR has merged by then" in otherwise


def test_a_waiver_or_ci_none_keeps_the_report_first():
    two = _step(2)
    required = _section(two, "**When the report is required**", "**Otherwise the evidence never holds the merge:**")
    assert "a required check the charter waives, or the profile's `ci.none`" in required
    assert "comes first" in required and "`--all`" in required
    assert "post its report on the PR, then go on to step 3" in required
    assert "`WF merge-check` counts it" in required


def test_merge_check_and_the_queue_never_wait_on_an_evidence_run_that_isnt_required():
    three = _step(3)
    assert "never waits on an evidence run that isn't required (step 2)" in three
    four = _step(4)
    queue = _section(four, "**With the merge queue on**", "\n\n   Before you first queue it")
    assert "In `session` and `auto-merge` mode alike, an evidence run still going is no reason to wait, unless the report is required (step 2)" in queue


def test_the_report_is_posted_before_the_ticket_ends():
    five = _step(5)
    assert "post the evidence's report first" in five
    # the checklist's line still holds
    assert "- [ ] Typecheck and the full suite pass; evidence posted on the PR" in BUILD_TICKET.read_text()


# ---------- the briefing, rendered (seam 2) ----------


def _project(tmp_path, ci_none=False):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    ci = "[ci]\nnone = true\n" if ci_none else '[ci]\nrequired_checks = ["unit"]\n'
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        f'[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "owner-login"\n\n{ci}'
    )
    (tmp_path / "ticket.json").write_text(json.dumps({"number": 7, "title": "Readings tab"}))
    (tmp_path / "slots.json").write_text(json.dumps(SLOTS))


def _cli(tmp_path, *args):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, cwd=tmp_path, env=env)


def _merging(tmp_path, mode="auto-merge", waived=()):
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    c["approved"] = {"by": "owner", "at": "2026-10-12T11:55:00Z", "source": "chat"}
    c["merge"] = {"mode": mode, "waived_checks": list(waived)}
    (tmp_path / "charter.json").write_text(json.dumps(c))
    p = _cli(
        tmp_path, "render", "--template", str(TEMPLATE), "--ticket", "ticket.json", "--charter", "charter.json",
        "--slots", "slots.json", "--tracking", "11", "--out", "briefing.md",
    )
    assert p.returncode == 0, p.stderr
    v = _cli(tmp_path, "briefing", "verify", "--file", "briefing.md")
    assert v.returncode == 0 and v.stdout.endswith(" intact\n"), v.stdout
    text = (tmp_path / "briefing.md").read_text()
    return _section(text, "### Merging", "### Rules")


def _bullets(merging):
    return [l for l in merging.splitlines() if l.startswith("- ")]


def test_no_waived_check_briefs_the_evidence_as_never_holding_the_merge(tmp_path):
    _project(tmp_path)
    merging = _merging(tmp_path)
    first = _bullets(merging)[0]
    assert first.startswith("- **The evidence never holds the merge:**"), first
    assert f"`{EVIDENCE}`" in first and "--all" not in first
    assert "tracked background task" in first and "never with `&` inside a shell call" in first
    assert "without waiting for it" in first
    assert "post its report on the PR, naming the head it covers, even if the PR has merged by then" in first
    # nothing reads as "post the evidence" before merge-check
    assert "Post the evidence from" not in merging


def test_a_waived_check_briefs_the_report_first(tmp_path):
    _project(tmp_path)
    merging = _merging(tmp_path, mode="session", waived=["unit"])
    first = _bullets(merging)[0]
    assert first.startswith("- **The evidence comes first:** the charter waives unit"), first
    assert f"`{EVIDENCE} --all`" in first
    assert "post its report on the PR before the `merge-check` below" in first
    assert "never holds the merge" not in merging


def test_ci_none_briefs_the_report_first(tmp_path):
    _project(tmp_path, ci_none=True)
    merging = _merging(tmp_path)
    first = _bullets(merging)[0]
    assert first.startswith("- **The evidence comes first:** the profile says `ci.none`"), first
    assert f"`{EVIDENCE} --all`" in first
    assert "never holds the merge" not in merging


def test_changelog_notes_663_without_bumping_version():
    notes = since_0110()
    assert "(#663" in notes
    assert "never holds the merge" in notes
