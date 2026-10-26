"""`workflow merge-check` with a merge queue (#245; #243's seams 3 and 6),
through the CLI, fed files.

With a ruleset in force on the base that requires a merge queue, "ready" means
ready to queue: the queue meets flow §4.3, so a branch behind the base isn't a
reason, waivers are refused, and the answer says `queue: true` with the note
that the rules are checked at enqueue. With the queue off, every answer is as
before (`tests/test_merge_check.py` and the others, unchanged).
"""

import json
import re
from pathlib import Path

import pytest

from changelog_notes import since_0110
from test_merge_check import SCENARIOS, check, ids, inputs, note_ids, project, ruleset  # noqa: F401 (project is a fixture)
from test_merge_check_evidence import a_charter, run, waiver_case

KIT = Path(__file__).resolve().parents[1]
QUEUE_RULE = {"type": "merge_queue", "parameters": {"merge_method": "MERGE", "grouping_strategy": "ALLGREEN", "check_response_timeout_minutes": 60}}


def queue_ruleset(include=("~DEFAULT_BRANCH",), enforcement="active", rid=2):
    """A ruleset of its own whose only rule requires the merge queue."""
    rs = ruleset(include=include, enforcement=enforcement)
    rs.update(id=rid, name="Merge queue", rules=[QUEUE_RULE])
    return rs


def queued(data):
    """`data` with the merge queue required on the base."""
    data["rulesets"] = data["rulesets"] + [queue_ruleset()]
    return data


def behind(data):
    data["compare"].update(status="diverged", behind_by=3)
    data["pr"]["mergeable_state"] = "behind"
    return data


# ---------- ready to queue ----------


def test_a_behind_pr_holding_every_other_rule_is_ready_with_the_queue(project, capsys):
    got, code = check(project, capsys, queued(behind(inputs())))
    assert code == 0
    assert got["decision"] == "ready", got["reasons"]
    assert got["queue"] is True
    [note] = [n for n in got["notes"] if n["id"] == "queue"]
    assert "checked when it is queued" in note["message"]
    assert "doesn't stop the merge" in note["message"]


def test_the_queue_rule_in_the_ruleset_that_requires_the_checks_counts_too(project, capsys):
    data = behind(inputs())
    data["rulesets"][0]["rules"].append(QUEUE_RULE)
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]
    assert got["queue"] is True


def test_ready_in_text_says_ready_to_queue(project, capsys):
    out, _ = check(project, capsys, queued(behind(inputs())), as_json=False)
    first = out.splitlines()[0]
    assert first.startswith("Ready") and "merge queue" in first
    assert "doesn't stop the merge" in out


# ---------- every other reason still blocks ----------


@pytest.mark.parametrize("rid", sorted(r for r in SCENARIOS if r != "behind"))
def test_with_the_queue_every_other_reason_still_blocks(project, capsys, rid):
    profile, change = SCENARIOS[rid]
    if profile:
        project.write(**profile)
    data = behind(inputs())
    change(data)
    got, _ = check(project, capsys, queued(data))
    assert got["decision"] == "not_yet"
    assert ids(got) == [rid], got["reasons"]
    assert got["queue"] is True


def test_with_the_queue_kit_files_still_need_the_owners_review(project, capsys):
    data = queued(behind(inputs()))
    data["files"] = [{"filename": ".github/workflows/ci.yml"}]
    got, _ = check(project, capsys, data)
    assert got["decision"] == "owner_review"
    assert got["files"] == [".github/workflows/ci.yml"]


# ---------- no waivers with the queue ----------


def test_with_the_queue_a_charter_with_waivers_is_refused(project, capsys, monkeypatch):
    data, logs = waiver_case(project, monkeypatch)
    queued(data)
    got, _ = run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter())})
    assert got["decision"] == "not_yet"
    assert "checks_failed" in ids(got)
    assert got["checks"] == [{"name": "tests", "state": "failing", "required": True}]
    assert "waived" not in note_ids(got)
    [note] = [n for n in got["notes"] if n["id"] == "charter_refused"]
    assert "merge queue" in note["message"]


def test_without_the_queue_the_same_waiver_still_counts(project, capsys, monkeypatch):
    data, logs = waiver_case(project, monkeypatch)
    got, _ = run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter())})
    assert got["decision"] == "ready", got["reasons"]
    assert got["queue"] is False


# ---------- a queue rule that isn't in force doesn't count ----------


@pytest.mark.parametrize("rs", [
    queue_ruleset(include=("refs/heads/ma*",)),  # unsure: a pattern this command doesn't match
    queue_ruleset(enforcement="evaluate"),
    queue_ruleset(enforcement="disabled"),
    queue_ruleset(include=("refs/heads/release",)),
    {**queue_ruleset(), "conditions": {"ref_name": {"include": ["~ALL"], "exclude": ["refs/heads/main"]}}},
    {**queue_ruleset(), "conditions": {"ref_name": {"include": ["~ALL"], "exclude": ["refs/heads/**"]}}},  # unsure: an exclude it can't match
], ids=["unsure", "evaluate", "disabled", "other-branch", "excludes-base", "unsure-exclude"])
def test_a_queue_rule_not_in_force_doesnt_count_as_a_queue(project, capsys, rs):
    data = behind(inputs())
    data["rulesets"].append(rs)
    got, _ = check(project, capsys, data)
    assert got["decision"] == "not_yet"
    assert "behind" in ids(got)
    assert got["queue"] is False
    assert "queue" not in note_ids(got)


def test_a_queue_rule_in_an_unsure_ruleset_is_noted(project, capsys):
    data = behind(inputs())
    data["rulesets"].append(queue_ruleset(include=("refs/heads/ma*",)))
    got, _ = check(project, capsys, data)
    [note] = [n for n in got["notes"] if n["id"] == "queue_unsure"]
    assert "Merge queue" in note["message"] and "isn't counted" in note["message"]


@pytest.mark.parametrize("exclude, unsure", [
    (["refs/heads/main"], False),
    (["~ALL"], False),
    (["refs/heads/MAIN"], True),  # matched ignoring case: only ever taken as "can't tell" here
    (["refs/heads/*"], True),  # a pattern: how GitHub matches it isn't certain
], ids=["by-name", "all", "other-case", "pattern"])
def test_a_pattern_ruleset_excluding_the_base_by_name_is_off_the_base(project, capsys, exclude, unsure):
    # #302: an exclude that certainly names the base wins over an include it can't match.
    rs = {**queue_ruleset(), "conditions": {"ref_name": {"include": ["refs/heads/ma*"], "exclude": exclude}}}
    data = behind(inputs())
    data["rulesets"].append(rs)
    got, _ = check(project, capsys, data)
    assert got["queue"] is False
    assert ("queue_unsure" in note_ids(got)) is unsure


def test_the_reader_reports_the_queue_and_an_unsure_one_apart():
    from workflow import protection

    rep = protection.check([queue_ruleset()], "main", {"default_branch": "main"})
    assert rep.queue is True and rep.queue_unsure == []
    rep = protection.check([queue_ruleset(include=("refs/heads/ma*",))], "main", {"default_branch": "main"})
    assert rep.queue is False and len(rep.queue_unsure) == 1 and "Merge queue" in rep.queue_unsure[0]
    rep = protection.check([ruleset("tests")], "main", {"default_branch": "main"})
    assert rep.queue is False and rep.queue_unsure == []
    # `workflow protection --json` is unchanged.
    assert "queue" not in rep.as_dict()


# ---------- with the queue off ----------


def test_without_the_queue_the_answer_says_so_and_behind_still_blocks(project, capsys):
    got, _ = check(project, capsys, behind(inputs()))
    assert got["queue"] is False
    assert ids(got) == ["behind"]
    assert "queue" not in note_ids(got)


def test_rulesets_that_cant_be_read_leave_behind_as_it_was(project, capsys):
    data = behind(inputs())
    got, _ = check(project, capsys, data, raw={"rulesets": "not json"})
    assert {"couldnt_read", "behind"} <= set(ids(got))
    assert got["queue"] is False


# ---------- the kit's text (seam 6) ----------


def flow_4():
    text = (KIT / "docs/flow.md").read_text(encoding="utf-8")
    return text.split("## 4. The merge rule", 1)[1].split("\n## ", 1)[0]


def item(section, n):
    return re.search(rf"^{n}\. \*\*.*$", section, re.M).group(0)


def test_flow_4_item_3_is_met_by_the_queue():
    assert "level with the base, or met by the merge queue where the ruleset requires one" in item(flow_4(), 3)


def test_flow_4_item_1_says_waivers_dont_apply_with_the_queue():
    assert "Waivers don't apply with the merge queue on" in item(flow_4(), 1)


def test_flow_4_says_the_rules_are_checked_at_enqueue():
    section = flow_4()
    assert "With the merge queue on, these rules are checked when the pull request is queued" in section
    assert "doesn't stop the merge" in section


def skill():
    return (KIT / "skills/merge-check/SKILL.md").read_text(encoding="utf-8")


def test_the_skill_queues_with_merge_async_pinned_to_the_head():
    text = skill()
    assert "`queue`" in text
    assert "gh api -i -X PUT repos/<repo>/pulls/12/merge-async -f merge_action=merge_queue -f sha=<head>" in text
    assert "Never `--admin`" in text and "`bypass_rules`" in text


@pytest.mark.parametrize("answer", [
    "**202**", "merge-async/<uuid>", "`enqueued`", "`pending`", "`failed`",
    "already in a merge queue", "**200** merged", "**409**", "**400**, **403** or **422**",
])
def test_the_skill_handles_each_answer(answer):
    assert answer in skill()


def test_the_skill_says_it_merges_once_its_group_passes_and_a_drop_offers_it_again():
    text = skill()
    assert "it merges once its group passes" in text
    assert "dropped" in text and "offers \"Merge it now\" again" in text


def test_the_changelog_notes_it_under_unreleased():
    notes = since_0110()
    assert "(#245" in notes and "merge queue" in notes


def test_the_guard_lets_the_skills_queue_command_through_and_refuses_bypass(tmp_path, monkeypatch):
    # In an attended session, the command the skill names (its path and a full
    # head SHA written out) gets no decision from the guard; `bypass_rules` is refused.
    from test_merge_check_skill import SHA, _event, _on_disk
    from workflow.guard import decide

    monkeypatch.delenv("WORKFLOW_ROLE", raising=False)
    line = re.search(r"`(gh api -i -X PUT repos/<repo>/pulls/12/merge-async [^`]*)`", skill()).group(1)
    cmd = line.replace("<repo>", "acme/demo").replace("<head>", SHA)
    profile = _on_disk(tmp_path, True)
    d = decide(_event("Bash", {"command": cmd}, "default"), profile, "attended", profile.root, "feature")
    assert d.action == "allow", d.reason
    d = decide(_event("Bash", {"command": cmd + " -F bypass_rules=true"}, "default"), profile, "attended", profile.root, "feature")
    assert d.action in ("ask", "deny")


# ---------- round 1's findings ----------


def test_a_queue_on_a_default_branch_only_assumed_to_be_the_base_isnt_counted(project, capsys):
    # Without base.repo.default_branch, merge-check takes the profile's base as
    # the default branch: that may count more required checks, never a queue.
    data = queued(behind(inputs()))
    del data["pr"]["base"]["repo"]
    got, _ = check(project, capsys, data)
    assert got["queue"] is False
    assert "behind" in ids(got)
    [note] = [n for n in got["notes"] if n["id"] == "queue_unsure"]
    assert "base.repo.default_branch" in note["message"]


@pytest.mark.parametrize("include", [("refs/heads/main",), ("~ALL",)])
def test_a_queue_naming_the_base_counts_without_the_default_branch(project, capsys, include):
    data = behind(inputs())
    del data["pr"]["base"]["repo"]
    data["rulesets"] = data["rulesets"] + [queue_ruleset(include=include)]
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]
    assert got["queue"] is True


def test_in_an_attended_session_the_charter_is_only_ignored_with_the_queue(project, capsys, monkeypatch):
    data, logs = waiver_case(project, monkeypatch, role="attended")
    queued(data)
    got, _ = run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter())})
    assert "charter_ignored" in note_ids(got) and "charter_refused" not in note_ids(got)


# ---------- round 2's findings ----------


def test_waivers_are_refused_where_a_ruleset_may_require_a_merge_queue(project, capsys, monkeypatch):
    data, logs = waiver_case(project, monkeypatch)
    queued(data)
    del data["pr"]["base"]["repo"]  # the queue on ~DEFAULT_BRANCH can't be counted either way
    got, _ = run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter())})
    assert got["queue"] is False
    assert got["decision"] == "not_yet" and "checks_failed" in ids(got)
    [note] = [n for n in got["notes"] if n["id"] == "charter_refused"]
    assert "may require a merge queue" in note["message"]
