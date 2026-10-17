"""#85: the conductor and ticket sessions merge on `workflow merge-check`.

The skills' and templates' wording is read as the kit-release tests read skills
(#39's seam 3); the briefing is rendered through the CLI, as
tests/test_charter_state_render.py renders it, and its seal still verifies.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"
CONDUCTOR = KIT / "skills/conductor/SKILL.md"
BUILD_TICKET = KIT / "skills/build-ticket/SKILL.md"
TEMPLATE = KIT / "templates/ticket-session-prompt.md"
CHARTER_DOC = KIT / "docs/charter.md"
CHANGELOG = KIT / "CHANGELOG.md"

COMMAND = re.compile(r"`WF merge-check --fetch <(?:PR|pr|n)> --json --charter [^`]+`")


def _read(p):
    return p.read_text(encoding="utf-8")


def _section(text, start, end):
    i = text.index(start)
    j = text.index(end, i + len(start))
    return text[i:j]


def _check_in_rows():
    """The conductor's check-in table and the paragraphs right under it."""
    return _section(_read(CONDUCTOR), "**4. Each ticket in flight.**", "**Stopping a stuck session safely:**")


def _row(rows, lead):
    line = next((ln for ln in rows.splitlines() if ln.startswith("| **" + lead)), None)
    assert line, lead
    return line


# ---------- the conductor ----------


def test_conductor_runs_merge_check_with_the_charter():
    rows = _check_in_rows()
    assert COMMAND.search(rows), "the conductor's merge rows run WF merge-check --fetch <PR> --json --charter …"
    # Files where gh can't read an input.
    assert "as a file" in rows or "with files" in rows


def test_conductor_ready_is_the_only_yes_in_every_mode():
    rows = _check_in_rows()
    assert "`ready` is the only yes" in rows
    session = _row(rows, "`session` mode")
    assert "`ready`" in session and "--match-head-commit" in session and "`sha`" in session
    assert "merge` grant" in session
    auto = _row(rows, "`auto-merge` mode")
    assert "`ready`" in auto and ("enable_pr_auto_merge" in auto or "--auto --merge" in auto)
    clean = _row(rows, "You tried to enable auto-merge and GitHub refused")
    assert "merge-check" in clean and "`ready`" in clean and "--match-head-commit" in clean
    owner = _row(rows, "`owner` mode")
    assert "`ready`" in owner and "ready for you to merge" in owner


def test_conductor_sends_owner_review_to_for_owner_with_the_files():
    rows = _check_in_rows()
    owner_review = _row(rows, "`owner_review`")
    assert "for_owner" in owner_review
    assert "#n changes a protected path (<files>): yours to review and merge (#PR)" in owner_review
    assert "`files`" in owner_review
    assert re.search(r"never (merge|arm)", owner_review, re.I)


def test_conductor_never_merges_on_not_yet():
    rows = _check_in_rows()
    not_yet = _row(rows, "`not_yet`")
    assert "never merge" in not_yet.lower()
    assert "reasons" in not_yet and "update_branch" in not_yet


def test_conductor_no_longer_restates_the_rule_or_lists_files():
    text = _read(CONDUCTOR)
    assert "reviews clean, the evidence comment is on the current head SHA" not in text
    assert "failed only by a killed marker" not in text
    assert "pulls/<n>/files" not in text
    assert "checks the branch is level before each merge" not in text
    assert "you check the branch is level with the base and update it first" not in text
    assert "merge rule met" not in text


def test_conductor_solo_kick_off_names_the_command():
    text = _read(CONDUCTOR)
    line = next(ln for ln in text.splitlines() if "This run is in solo mode" in ln)
    assert "`workflow merge-check`" in line


# ---------- build-ticket ----------


def _merge_step():
    return _section(_read(BUILD_TICKET), "## 6. Post the evidence and merge", "**Once it has merged,**")


def test_build_ticket_runs_merge_check_with_the_charter_before_merging():
    step = _merge_step()
    assert COMMAND.search(step)
    assert "tracking issue" in step and "the briefing names" in step
    assert "`ready`" in step and "only" in step
    assert "--match-head-commit" in step or "`sha`" in step
    clean = step[step.index("already mergeable"):]
    assert "merge-check" in clean.split("|")[0] and "`ready`" in clean.split("|")[0]


def test_build_ticket_handles_owner_review_and_attended_work():
    step = _merge_step()
    assert "`owner_review`" in step
    i = step.index("`owner_review`")
    assert "owner" in step[i:i + 300] and "waiting" in step[i:i + 300]
    assert "is #N ready to merge?" in step
    assert "`not_yet`" in step


# ---------- the briefing ----------


def _profile(tmp_path):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname="d"\nrepo="a/d"\nowner="o"\n'
        '[ci]\nrequired_checks=["CI", "Backend tests"]\n'
        '[[release.steps]]\nname="ship"\nrun="x"\n',
        encoding="utf-8",
    )


def _render(tmp_path, mode, waived):
    from workflow import charter

    _profile(tmp_path)
    c = charter.defaults(["ship"])
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    c["merge"] = {"mode": mode, "waived_checks": waived}
    files = {
        "charter.json": c,
        "ticket.json": {"number": 7, "title": "Readings tab"},
        "slots.json": {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "none", "wake_trigger": "trig_01abc"},
    }
    for name, value in files.items():
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    out = tmp_path / "briefing.md"
    p = subprocess.run(
        [sys.executable, str(CLI), "render", "--template", str(TEMPLATE), "--ticket", str(tmp_path / "ticket.json"),
         "--charter", str(tmp_path / "charter.json"), "--slots", str(tmp_path / "slots.json"), "--tracking", "232", "--out", str(out)],
        capture_output=True, text=True, cwd=tmp_path, env=env,
    )
    assert p.returncode == 0, p.stderr
    v = subprocess.run([sys.executable, str(CLI), "briefing", "verify", "--file", str(out)], capture_output=True, text=True, cwd=tmp_path, env=env)
    assert re.fullmatch(r"Briefing [0-9a-f]{12} intact\n?", v.stdout), v.stdout + v.stderr
    return _section(out.read_text(encoding="utf-8"), "### Merging", "### Rules")


def test_briefing_names_merge_check_and_the_charter(tmp_path):
    merging = _render(tmp_path, "session", ["Backend tests"])
    assert "merge-check --fetch <PR> --json --charter" in merging
    assert "#232" in merging and "body" in merging
    assert "`ready`" in merging
    assert "Merge mode: **session**" in merging and "Backend tests" in merging
    assert "--check-logs" in merging
    assert "evidence --base-ref origin/main" in merging


def test_briefing_keeps_auto_merge_and_no_waivers(tmp_path):
    merging = _render(tmp_path, "auto-merge", [])
    assert "Merge mode: **auto-merge**" in merging
    assert "every required check must be green" in merging
    assert "merge-check" in merging and "`ready`" in merging


# ---------- docs and changelog ----------


def test_charter_doc_names_the_command():
    text = _read(CHARTER_DOC)
    merging = _section(text, "**Merges are decided by `workflow merge-check`,**", "**Kill switch.**")
    assert "`workflow merge-check`" in merging and "--charter" in merging and "`ready`" in merging
    solo = next(ln for ln in text.splitlines() if ln.startswith("- **Solo mode:**"))
    assert "`workflow merge-check`" in solo


def test_changelog_notes_under_unreleased():
    text = _read(CHANGELOG)
    unreleased = _section(text, "## Unreleased", "\n## 0.")
    assert "merge-check" in unreleased and "#85" in unreleased
