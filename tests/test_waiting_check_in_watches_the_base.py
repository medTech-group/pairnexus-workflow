"""#664: a waiting ticket session notices its pull request now conflicts with
the base. Every waiting check-in, whatever the session waits on, runs
`WF merge-check` on the head while the pull request is open, and on `conflict`
merges the base in at once. A head it queued is watched by one rule under one
name, "a queued head in conflict" (#685): it only waits until `WF merge-check`
gives it a `conflict`. The stay for the evidence report is left to §6 step 5
(#686). `build-ticket` is read as
a text contract (seam 2), and the briefing's **Check-ins** line is rendered
through the CLI, as `tests/test_evidence_never_holds_the_merge.py` renders
briefings, the **Merging** lines too."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from changelog_notes import since_0110
from workflow import charter

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"
TEMPLATE = KIT / "templates/ticket-session-prompt.md"
BUILD_TICKET = KIT / "skills/build-ticket/SKILL.md"
SLOTS = {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "none", "wake_trigger": "trig_01abc"}
HEADING = "**Every waiting check-in watches the base.**"
NAME = "a queued head in conflict"
PINNED = (
    "Never queue that head again: a head you queued only waits, whatever `WF merge-check` says of it later, "
    "and every re-queue is the conductor's"
)


def _flat(text):
    return re.sub(r"\s+", " ", text)


def _section(text, start, end):
    assert start in text, start
    i = text.index(start)
    return text[i:text.index(end, i + len(start))]


def _paragraph():
    four = _section(BUILD_TICKET.read_text(), "## 4. Open the pull request", "## 5. Get it green")
    assert HEADING in four, "build-ticket §4 has no waiting check-in paragraph"
    i = four.index(HEADING)
    end = four.find("\n\n", i)
    return _flat(four[i:end if end != -1 else len(four)])


# ---------- build-ticket (seam 2) ----------


def test_it_follows_the_check_in_it_describes():
    four = _section(BUILD_TICKET.read_text(), "## 4. Open the pull request", "## 5. Get it green")
    subscribe = four.index("Then subscribe to its activity.")
    assert subscribe < four.index(HEADING)


def test_every_waiting_check_in_runs_merge_check_whatever_it_waits_on():
    p = _paragraph()
    assert "Whatever you wait on (CI, the evidence run or a review agent)" in p
    assert "each check-in, while the pull request is open, runs" in p
    # the watch has no exception of its own for a queued head (#685)
    assert "isn't one you queued" not in p
    assert "runs `WF merge-check --fetch <PR> --json` on the head (in a run, with step 6.3's flags)" in p
    assert "not only once what you wait on is done" in p


def test_on_conflict_it_merges_the_base_in_at_once_never_a_rebase():
    p = _paragraph()
    assert "On a `conflict` reason (its action `resolve_conflict`), merge the base in at once" in p
    assert "disarm auto-merge first if it is armed" in p
    assert "`git fetch origin <base> && git merge origin/<base>`" in p
    assert "never a rebase or force-push" in p


def test_a_changelog_conflict_keeps_both_sides():
    p = _paragraph()
    assert "in a `CHANGELOG.md` conflict, keep both sides: every note from each" in p


def test_it_pushes_and_acts_on_the_next_merge_check():
    p = _paragraph()
    assert "push, and act on the next `WF merge-check`" in p
    assert "a Correctness pass only when it asks for one (§3)" in p


def test_an_evidence_run_still_going_holds_nothing():
    p = _paragraph()
    assert "An evidence run still going holds this merge no more than any other (§6 step 2)" in p


def _six():
    return _section(BUILD_TICKET.read_text(), "## 6. Post the evidence and merge", "## 7. End each turn")


def _queued_head_rule():
    six = _six()
    lead = "**" + NAME[0].upper() + NAME[1:] + "**"
    assert lead in six, "build-ticket §6 step 4 has no paragraph for a queued head in conflict"
    i = six.index(lead)
    return _flat(six[i:six.index("\n\n", i)])


def test_the_watch_and_section_6_step_4_name_one_rule_for_a_queued_head():
    # #685: one rule under one name, in §4 and in §6 step 4; never "in the
    # merge queue", a state the session can't read
    p = _paragraph()
    assert f"A head you queued is watched the same way, as **{NAME}** (§6 step 4)" in p
    assert "only waits until `WF merge-check` gives it a `conflict`" in p
    assert "merge queue" not in p
    rule = _queued_head_rule()
    assert "merge queue" in rule  # it says why: GitHub takes a conflict out of the queue
    for text in (_paragraph(), _flat(_six())):
        assert text.lower().count(NAME) == 1, text


def test_the_rule_comes_after_section_6s_pinned_sentence_which_stays_word_for_word():
    six = _flat(_six())
    assert PINNED in six
    assert six.index(PINNED) < six.index("**A queued head in conflict**")


def test_the_condition_is_merge_checks_conflict_never_the_queue_state():
    rule = _queued_head_rule()
    assert (
        "when `WF merge-check` gives a head you queued a `conflict` reason (its action `resolve_conflict`), "
        "at any check-in, merge the base in at once, as §4's \"Every waiting check-in watches the base\" says"
    ) in rule
    assert "GitHub takes a pull request that conflicts with the base out of the merge queue" in rule
    assert "Read only `WF merge-check`'s answer for this, never whether the head is still in the queue: its JSON doesn't say" in rule


def test_a_queued_head_without_a_conflict_only_waits_and_re_queues_stay_the_conductors():
    rule = _queued_head_rule()
    assert "With no `conflict`, a head you queued only waits, as above" in rule
    assert "Merging the base in is never a re-queue of that head" in rule
    assert "re-queue" in _flat(_six()) and "every re-queue is the conductor's" in _flat(_six())


def test_the_merge_makes_a_new_head_queued_once_on_ready():
    rule = _queued_head_rule()
    assert "The merge makes a new head: on `ready`, queue it once, as for a fix you push." in rule


def test_the_evidence_to_come_never_holds_a_queued_head_in_conflict():
    # the notes posted before queueing carry "Evidence for <sha> to come": that
    # never holds the base merge for a queued head in conflict. The rule says
    # nothing of when step 5's stay begins (#686's), so it never narrows the
    # stay to a pull request that has merged: one left to the owner stays too
    rule = _queued_head_rule()
    assert "not while you stay" not in rule
    assert (
        "Your evidence run still going never holds this merge, nor does the \"Evidence for `<sha>` to come\" line "
        "in the notes you posted before queueing."
    ) in rule
    assert "begins once" not in rule


def test_the_watch_leaves_the_evidence_stay_to_section_6_step_5():
    # the watch makes no rule of its own for the stay (#686's): it points at
    # §6 step 5's "Then stay", whose text is as it was
    p = _paragraph()
    assert "This watch doesn't apply while you stay for your evidence report: §6 step 5's \"Then stay\" says what the stay does." in p
    assert "wins over" not in p
    six = _section(BUILD_TICKET.read_text(), "## 6. Post the evidence and merge", "## 7. End each turn")
    stay = _flat(_section(six, "**Then stay**", "6. **The claim label.**"))
    assert "Leave your checkout as it is (no pull, no edit: the run stops if your head moves)" in stay
    assert stay.rstrip().endswith("Then end `done`.")
    assert "watches the base" not in stay


def test_the_base_moved_bullet_still_resolves_a_conflict_with_the_queue_on():
    five = _section(BUILD_TICKET.read_text(), "## 5. Get it green", "## 6. Post the evidence and merge")
    assert "Still merge it in to resolve a conflict (`WF merge-check`'s `resolve_conflict`), as above." in five


# ---------- the briefing's Check-ins line, rendered (seam 2) ----------


def _project(tmp_path):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "owner-login"\nbase_branch = "trunk"\n\n'
        '[ci]\nrequired_checks = ["unit"]\n'
    )
    (tmp_path / "ticket.json").write_text(json.dumps({"number": 7, "title": "Readings tab"}))
    (tmp_path / "slots.json").write_text(json.dumps(SLOTS))


def _cli(tmp_path, *args):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, cwd=tmp_path, env=env)


def _briefing(tmp_path, mode=None):
    c = charter.defaults()
    if mode:
        c["merge"] = {"mode": mode, "waived_checks": []}
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    c["limits"]["check_in_minutes"] = 20
    c["approved"] = {"by": "owner", "at": "2026-10-12T11:55:00Z", "source": "chat"}
    (tmp_path / "charter.json").write_text(json.dumps(c))
    p = _cli(
        tmp_path, "render", "--template", str(TEMPLATE), "--ticket", "ticket.json", "--charter", "charter.json",
        "--slots", "slots.json", "--tracking", "11", "--out", "briefing.md",
    )
    assert p.returncode == 0, p.stderr
    v = _cli(tmp_path, "briefing", "verify", "--file", "briefing.md")
    assert v.returncode == 0 and v.stdout.endswith(" intact\n"), v.stdout
    return (tmp_path / "briefing.md").read_text()


def _check_ins(tmp_path):
    lines = [l for l in _briefing(tmp_path).splitlines() if l.startswith("- **Check-ins:**")]
    assert len(lines) == 1, lines
    return lines[0]


def test_the_rendered_check_ins_line_watches_the_base(tmp_path):
    _project(tmp_path)
    line = _check_ins(tmp_path)
    # the line as it was, kept
    assert "subscribe to the PR's activity and schedule a check-in with `send_later` about every 20 minutes." in line
    assert "End that turn with `WORKFLOW-STATUS: waiting`." in line
    # and the new sentence, with the profile's base branch filled in
    assert (
        "Whatever you wait on (CI, the evidence or a review agent), each check-in, while the PR is "
        "open, runs `merge-check` (the command under **Merging**) on the head; on "
        "`conflict`, "
    ) in line
    assert (
        " in at once (never a rebase or force-push), keeping both sides of a `CHANGELOG.md` "
        "conflict, then push and act on the next `merge-check`."
    ) in line
    # a head you queued is watched too, under the rule's one name (#685); the evidence stay is step 5's
    assert (
        "A head you queued is watched the same way, as a queued head in conflict (**Merging**), even with your "
        "evidence still to come; the stay for the evidence report follows `build-ticket` §6 step 5 instead."
    ) in line
    assert "isn't one you queued" not in line
    assert "merge queue" not in line
    # a local base branch can be stale from the clone: fetch and merge the remote's
    assert "`conflict`, fetch and merge `origin/trunk` in at once (never a rebase or force-push)" in line
    assert "merge `trunk` in" not in line
    assert "{{" not in line


@pytest.mark.parametrize("mode", ["owner", "session"])
def test_the_rendered_check_ins_line_keeps_the_evidence_stay_whole_as_section_4_does(tmp_path, mode):
    # a PR left to the owner stays open while the session stays for its
    # evidence report: the line hands every stay to §6 step 5, as §4 does,
    # never only one whose PR has merged
    _project(tmp_path)
    lines = [l for l in _briefing(tmp_path, mode).splitlines() if l.startswith("- **Check-ins:**")]
    assert len(lines) == 1, lines
    line = lines[0]
    assert line.endswith("the stay for the evidence report follows `build-ticket` §6 step 5 instead.")
    assert "once the PR has merged" not in line
    assert "This watch doesn't apply while you stay for your evidence report:" in _paragraph()


@pytest.mark.parametrize("mode", ["auto-merge", "session"])
def test_the_rendered_merge_queue_line_gives_the_same_rule_under_the_same_name(tmp_path, mode):
    _project(tmp_path)
    lines = [l for l in _briefing(tmp_path, mode).splitlines() if l.startswith("- **The merge queue:**")]
    assert len(lines) == 1, lines
    line = lines[0]
    # #664's criterion kept: a queued head only waits, re-queues are the conductor's
    assert "A head you queued only waits. The one exception is a queued head in conflict:" in line
    assert "every re-queue is the conductor's" in line
    assert (
        "when `merge-check` gives a head you queued a `conflict` reason, GitHub has taken it out of the queue, "
        "so merge the base in at once, as **Check-ins** says; read only `merge-check`'s answer, not whether the "
        "head is still queued. Its new head you queue once on `ready`."
    ) in line
    # #297's pin: the bullet never says "never queue"
    assert "never queue" not in line
    assert line.lower().count("a queued head in conflict") == 1


def test_changelog_notes_664():
    notes = since_0110()
    assert "(#664" in notes
    assert "waiting check-in" in notes


def test_changelog_notes_685_without_bumping_version():
    notes = since_0110()
    assert "(#685" in notes
    assert "a queued head in conflict" in notes.lower()
    # build tickets never bump VERSION (CONTRIBUTING.md): it stays the latest released heading
    log = (KIT / "CHANGELOG.md").read_text()
    released = re.findall(r"^## (\d+\.\d+\.\d+)$", log, re.M)
    assert (KIT / "VERSION").read_text().strip() == released[0]
