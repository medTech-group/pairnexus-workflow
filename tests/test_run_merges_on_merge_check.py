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

from workflow import charter
from changelog_notes import since_0110

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"
CONDUCTOR = KIT / "skills/conductor/SKILL.md"
BUILD_TICKET = KIT / "skills/build-ticket/SKILL.md"
TEMPLATE = KIT / "templates/ticket-session-prompt.md"
CHARTER_DOC = KIT / "docs/charter.md"
CHANGELOG = KIT / "CHANGELOG.md"

COMMAND = re.compile(r"`WF merge-check --fetch <(?:PR|pr|n)> --json --charter \.workflow/[^`]+`")
# Each way of merging pins the head merge-check checked.
# When a path-filtered check that never started goes to the owner.
PATH_FILTERED_WHEN = (
    "only once every other required check has finished and the evidence is posted: `WF merge-check`'s only reason left is "
    "`checks_pending`, for checks that are all in `ci.path_filtered` and `missing` in its `checks[]`"
)
DISARM = "`disable_pr_auto_merge`, or `gh pr merge <n> --disable-auto`"
PINS = ("--match-head-commit <sha>", "-f sha=<sha>", "`expectedHeadSha`")


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
    assert "give it as a file (`--pr F`, `--checks F`, …)" in rows
    # Scratch files stay where git ignores them, so the evidence sees a clean tree.
    assert "> .workflow/run/tracking.md" in rows and "--check-logs .workflow/run/check-logs" in rows


def test_conductor_ready_is_the_only_yes_in_every_mode():
    rows = _check_in_rows()
    assert "`ready` is the only yes" in rows
    session = _row(rows, "`session` mode")
    assert all(pin in session for pin in PINS), session
    assert "merge` grant" in session
    auto = _row(rows, "`auto-merge` mode")
    assert "`gh pr merge <n> --auto --merge --match-head-commit <sha>`" in auto
    assert "Never arm it on anything but `ready`" in auto
    clean = _row(rows, "You tried to enable auto-merge and GitHub refused")
    assert "merge-check" in clean and "On `ready`, merge it yourself as the `session` row does, pinned to its `head`" in clean
    behind = _row(rows, "PR open, behind the base")
    assert "disarm it first" in behind and "`WF merge-check` gives a `behind` reason" in behind and "Arm it again only on the new head's `ready`" in behind
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
    assert not_yet.split("|")[2].strip().startswith("Never merge it or arm auto-merge, and if auto-merge is armed on it, disarm it")
    assert "update_branch" in not_yet and "A reason with no `action`" in not_yet
    assert "The path-filtered row below wins over this one once its condition holds." in not_yet
    path_filtered = _row(rows, "A required check never started")
    assert "never says `ready`" in path_filtered and "settled for \"Done\"" in path_filtered
    assert PATH_FILTERED_WHEN in path_filtered and "until then, the `not_yet` row applies" in path_filtered


def test_conductor_no_longer_restates_the_rule_or_lists_files():
    text = _read(CONDUCTOR)
    assert "reviews clean, the evidence comment is on the current head SHA" not in text
    assert "failed only by a killed marker" not in text
    assert "pulls/<n>/files" not in text
    assert "checks the branch is level before each merge" not in text
    assert "you check the branch is level with the base and update it first" not in text
    assert "merge rule met" not in text
    assert "In `session` mode it counts as passed" not in text
    assert "Don't list the files yourself" not in text
    enforcement = _read(KIT / "docs/enforcement.md")
    assert "checks the branch is level with the base before each merge" not in enforcement
    assert "`workflow merge-check`" in enforcement


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
    assert "the tracking issue the briefing names saved there (`gh api repos/<repo>/issues/<tracking> --jq .body > .workflow/tracking.md`" in step
    assert "--check-logs .workflow/check-logs" in step
    assert "**`ready` is the only yes**" in step
    assert "- `not_yet`: never merge or arm auto-merge, and if auto-merge is armed, disarm it (" + DISARM + ")" in step
    assert "`review_stale`: a Correctness pass on the new commits" in step
    assert "right before each of these (merging, arming auto-merge, saying it's ready), run `WF merge-check --fetch <PR> --json" in step
    session = next(ln for ln in step.splitlines() if ln.startswith("   | `session` |"))
    assert all(pin in session for pin in PINS), session
    auto = next(ln for ln in step.splitlines() if ln.startswith("   | `auto-merge` |"))
    assert "--auto --merge --match-head-commit <sha>" in auto
    assert "Before any push of yours while it is armed (a fix, the base merged in, an update of the branch), disarm it (" + DISARM + ")" in auto
    assert "on `ready` with auto-merge not armed (whoever disarmed it), arm it again, pinned to the new `head`" in auto
    clean = auto[auto.index("already mergeable"):]
    assert "run the same `WF merge-check` again at that moment; on `ready`" in clean
    assert all(pin in clean for pin in PINS)
    # The renumbered cross-references land where they mean.
    assert "notes for the next tickets (step 6.5)" in auto and "5. **Once it has merged,**" in _read(BUILD_TICKET)
    assert "wake the conductor (step 6.7)" in _read(BUILD_TICKET) and "7. **Wake the conductor.**" in _read(BUILD_TICKET)
    assert "a red check (§5)" in step
    assert "in `session` mode it counts as passed once the evidence is posted" not in _read(BUILD_TICKET)
    green = _section(_read(BUILD_TICKET), "## 5. Get it green", "## 6.")
    assert PATH_FILTERED_WHEN in green and "Until then, step 6.3's `not_yet` applies." in green
    assert "- **The base branch moved:** if auto-merge is armed, disarm it first (" + DISARM + ")" in green


def test_build_ticket_handles_owner_review_and_attended_work():
    step = _merge_step()
    owner_review = next(ln for ln in step.splitlines() if ln.strip().startswith("- `owner_review`:"))
    assert "Never merge it or arm auto-merge: comment on the PR and on the tracking issue that the owner reviews and merges it" in owner_review
    assert "end with `WORKFLOW-STATUS: waiting`" in owner_review
    assert "is #N ready to merge?" in step
    attended = step[step.index("3. **Run `WF merge-check`.**"):].split("\n")[0]
    assert "In attended work, skip this and step 4: say the PR is ready and leave it" in attended


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
    assert "merge-check --fetch <PR> --json --charter .workflow/tracking.md" in merging
    assert "the body of the tracking issue #232 saved to `.workflow/tracking.md`" in merging
    assert "`ready` is the only yes. On `not_yet`, never merge or arm auto-merge (disarm it if it's armed)" in merging
    assert "merge it yourself with a merge commit pinned to the head it checked" in merging
    assert "On `ready`, act by the merge mode: `session` merges with a merge commit pinned to the head it checked; `auto-merge` arms auto-merge pinned to it; `owner` says it's ready and leaves it." in merging
    assert "In `auto-merge` mode, disarm auto-merge before any push while it's armed." in merging
    assert "Right before each of these (merging, arming auto-merge, saying it's ready), run `workflow merge-check`" in merging
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
    assert "`workflow merge-check`" in merging and "--charter" in merging and "**`ready` is the only yes.**" in merging
    assert "flow §4.1" in merging
    solo = next(ln for ln in text.splitlines() if ln.startswith("- **Solo mode:**"))
    assert "`workflow merge-check`" in solo


def test_changelog_notes_under_unreleased():
    text = _read(CHANGELOG)
    unreleased = since_0110(text)
    assert "merge-check" in unreleased and "#85" in unreleased
