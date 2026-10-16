"""`workflow merge-check`, through the CLI, fed recorded files (#80; #39's seam 1).

Each test starts from a pull request where every rule holds (`inputs`) and
breaks one thing. Review records come from the writer (`reviews.record`), so
the fixtures are what the panel really posts.
"""

import json
import re
import subprocess
from pathlib import Path

import pytest

from workflow import cli, merge, reviews

KIT = Path(__file__).resolve().parents[1]
HEAD = "a" * 40
EARLIER = "b" * 40
OUTSIDE = "c" * 40
FLAGS = ("pr", "files", "commits", "checks", "rulesets", "threads", "reviews", "comments", "permissions", "compare")


def run_(name, conclusion="success", status="completed", when="2026-10-16T10:00:00Z", sha=HEAD, slug="github-actions", rid=1):
    return {
        "id": rid,
        "name": name,
        "status": status,
        "conclusion": conclusion if status == "completed" else None,
        "head_sha": sha,
        "started_at": when,
        "completed_at": when if status == "completed" else None,
        "app": {"slug": slug},
    }


def ruleset(*checks, include=("~DEFAULT_BRANCH",), enforcement="active"):
    rules = [{"type": "deletion"}, {"type": "non_fast_forward"}, {"type": "pull_request"}]
    if checks:
        rules.append({"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": c} for c in checks]}})
    return {
        "id": 1,
        "name": "Protect main",
        "target": "branch",
        "enforcement": enforcement,
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": list(include), "exclude": []}},
        "rules": rules,
    }


def comment(body, author="owner", cid=100):
    return {"id": cid, "user": {"login": author}, "body": body, "created_at": "2026-10-16T09:00:00Z", "html_url": f"https://github.com/acme/demo/issues/12#issuecomment-{cid}"}


def rec(kind="round", rnd=1, commit=HEAD, clean=True, reviewers=None):
    who = reviewers or ("correctness" if kind == "pass" else "standards,spec,correctness")
    return reviews.record(kind=kind, round=rnd, commit=commit, reviewers=who, clean=clean)


def inputs():
    """A pull request where every rule holds."""
    return {
        "pr": {
            "number": 12,
            "head": {"sha": HEAD, "ref": "claude/build-1"},
            "base": {"ref": "main", "repo": {"default_branch": "main"}},
            "mergeable": True,
            "mergeable_state": "clean",
            "labels": [],
            "requested_reviewers": [],
        },
        "files": [{"filename": "src/app.py", "status": "modified"}],
        "commits": [{"sha": EARLIER}, {"sha": HEAD}],
        "checks": {"total_count": 1, "check_runs": [run_("tests")]},
        "rulesets": [ruleset("tests")],
        "threads": [],
        "reviews": [],
        "comments": [comment(rec())],
        "permissions": {"owner": "admin", "dev": "write", "keeper": "maintain", "stranger": "read"},
        "compare": {"status": "ahead", "ahead_by": 2, "behind_by": 0},
    }


PROFILE = """
[project]
name = "demo"
repo = "acme/demo"
base_branch = "main"
owner = "{owner}"
{ruleset}
[ci]
required_checks = {checks}
none = {none}
"""


class Project(type(Path())):
    """The project's root, with `write(...)` to rewrite its profile."""


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = Project(tmp_path / "project")
    (root / ".claude/workflow").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("WORKFLOW_EXPERIENCE", "developer")

    def write(owner="owner", checks=("tests",), none=False, ruleset=None):
        rs = "" if ruleset is None else f"ruleset = {str(ruleset).lower()}"
        (root / ".claude/workflow/profile.toml").write_text(
            PROFILE.format(owner=owner, checks=json.dumps(list(checks)), none=str(none).lower(), ruleset=rs)
        )

    write()
    root.write = write
    return root


def check(project, capsys, data, *extra, as_json=True, raw=None, leave_out=()):
    """Run merge-check on `data` (written as files); the parsed JSON (or the text) and the exit code."""
    d = project.parent / "in"
    d.mkdir(exist_ok=True)
    args = ["merge-check"]
    for name in FLAGS + ("preview",):
        if name in leave_out or (name == "preview" and "preview" not in data):
            continue
        path = d / f"{name}.json"
        path.write_text((raw or {}).get(name) or json.dumps(data[name]))
        args += [f"--{name}", str(path)]
    args += list(extra)
    if as_json:
        args.append("--json")
    code = cli.main(args)
    out = capsys.readouterr().out
    return (json.loads(out) if as_json else out), code


def ids(result):
    return [r["id"] for r in result["reasons"]]


def note_ids(result):
    return [n["id"] for n in result["notes"]]


# ---------- every rule holding ----------


def test_everything_holding_is_ready_and_exits_0(project, capsys):
    got, code = check(project, capsys, inputs())
    assert code == 0
    assert got["decision"] == "ready", got["reasons"]
    assert got["reasons"] == []
    assert got["head"] == HEAD
    assert got["checks"] == [{"name": "tests", "state": "passing", "required": True}]


def test_ready_in_text(project, capsys):
    out, code = check(project, capsys, inputs(), as_json=False)
    assert code == 0
    assert out.splitlines()[0].startswith("Ready")
    assert "tests: passing (required)" in out


# ---------- rule 1: checks ----------


def test_a_pending_check_is_not_yet(project, capsys):
    data = inputs()
    data["checks"]["check_runs"] = [run_("tests", status="in_progress")]
    got, _ = check(project, capsys, data)
    assert got["decision"] == "not_yet"
    assert ids(got) == ["checks_pending"]
    assert "tests" in got["reasons"][0]["message"]
    out, _ = check(project, capsys, data, as_json=False)
    assert out.startswith("Not yet") and "tests" in out


def test_a_failed_check_is_not_yet_with_fix_checks_naming_it(project, capsys):
    data = inputs()
    data["checks"]["check_runs"] = [run_("tests", "failure")]
    got, _ = check(project, capsys, data)
    assert got["decision"] == "not_yet"
    [r] = got["reasons"]
    assert r["id"] == "checks_failed" and r["action"] == "fix_checks" and "tests" in r["message"]
    assert r["implements"] == "flow §4.1"
    out, _ = check(project, capsys, data, as_json=False)
    assert out.startswith("Not yet") and "tests" in out


def test_a_check_absent_from_the_head_commit_is_pending_never_passed(project, capsys):
    data = inputs()
    data["checks"]["check_runs"] = [run_("tests", sha=EARLIER)]
    got, _ = check(project, capsys, data)
    assert got["decision"] == "not_yet"
    assert ids(got) == ["checks_pending"]
    assert got["checks"] == [{"name": "tests", "state": "missing", "required": True}]


def test_a_duplicate_counts_by_its_latest_result(project, capsys):
    data = inputs()
    data["checks"]["total_count"] = 2
    data["checks"]["check_runs"] = [run_("tests", "failure", when="2026-10-16T09:00:00Z", rid=1), run_("tests", when="2026-10-16T10:00:00Z", rid=2)]
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]
    data["checks"]["check_runs"].reverse()
    data["checks"]["check_runs"][0]["conclusion"] = "failure"
    data["checks"]["check_runs"][1]["conclusion"] = "success"
    data["checks"]["check_runs"][0]["completed_at"] = "2026-10-16T11:00:00Z"
    got, _ = check(project, capsys, data)
    assert ids(got) == ["checks_failed"]


def test_statuses_count_beside_check_runs(project, capsys):
    data = inputs()
    data["rulesets"] = [ruleset("tests", "ci/legacy")]
    status = {"sha": HEAD, "state": "pending", "total_count": 1, "statuses": [{"id": 5, "context": "ci/legacy", "state": "pending", "updated_at": "2026-10-16T10:00:00Z"}]}
    raw = {"checks": json.dumps(data["checks"]) + "\n" + json.dumps(status)}
    got, _ = check(project, capsys, data, raw=raw)
    assert ids(got) == ["checks_pending"]
    assert {"name": "ci/legacy", "state": "pending", "required": True} in got["checks"]


def test_required_checks_are_the_rulesets_and_the_profiles_together_with_a_note(project, capsys):
    project.write(checks=("tests", "lint"))
    data = inputs()
    data["rulesets"] = [ruleset("tests", "build")]
    data["checks"] = {"total_count": 2, "check_runs": [run_("tests", rid=1), run_("lint", rid=2)]}
    got, _ = check(project, capsys, data)
    assert got["decision"] == "not_yet"
    assert ids(got) == ["checks_pending"]
    assert "build" in got["reasons"][0]["message"]
    assert {c["name"] for c in got["checks"] if c["required"]} == {"tests", "lint", "build"}
    [n] = [n for n in got["notes"] if n["id"] == "lists_differ"]
    assert "build" in n["message"] and "lint" in n["message"] and "set-up" in n["message"]


def test_lists_that_agree_give_no_note(project, capsys):
    got, _ = check(project, capsys, inputs())
    assert "lists_differ" not in note_ids(got)


def test_a_ruleset_on_another_branch_or_not_active_requires_nothing(project, capsys):
    project.write(checks=())
    data = inputs()
    data["rulesets"] = [ruleset("build", include=("refs/heads/release",)), ruleset("deploy", enforcement="evaluate")]
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]


def test_a_ruleset_it_cant_tell_targets_the_base_is_not_yet(project, capsys):
    data = inputs()
    data["rulesets"] = [ruleset("build", include=("refs/heads/ma*",))]
    got, _ = check(project, capsys, data)
    assert got["decision"] == "not_yet"
    assert ids(got) == ["required_unknown"]


def test_with_neither_listing_checks_the_checks_that_ran_count_less_the_cloudflare_check(project, capsys):
    project.write(checks=())
    data = inputs()
    data["rulesets"] = [ruleset()]
    data["checks"] = {"total_count": 2, "check_runs": [run_("tests", rid=1), run_("Cloudflare Pages", "failure", slug="cloudflare-workers-and-pages", rid=2)]}
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]
    assert [c["name"] for c in got["checks"] if c["required"]] == ["tests"]
    data["checks"]["check_runs"][0]["conclusion"] = "failure"
    got, _ = check(project, capsys, data)
    assert ids(got) == ["checks_failed"]


def test_none_listed_and_none_ran_is_not_yet_no_checks(project, capsys):
    project.write(checks=())
    data = inputs()
    data["rulesets"] = []
    data["checks"] = {"total_count": 0, "check_runs": []}
    got, _ = check(project, capsys, data)
    assert got["decision"] == "not_yet"
    [r] = got["reasons"]
    assert r["id"] == "no_checks"
    assert "no checks have run on this commit" in r["wording"]["new"]["message"]
    assert "ci.none = true" in r["fix"]


def test_a_failed_check_that_isnt_required_is_a_note(project, capsys):
    data = inputs()
    data["checks"] = {"total_count": 2, "check_runs": [run_("tests", rid=1), run_("spelling", "failure", rid=2)]}
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]
    [n] = [n for n in got["notes"] if n["id"] == "failed_not_required"]
    assert "spelling" in n["message"]
    assert {"name": "spelling", "state": "failing", "required": False} in got["checks"]


# ---------- rule 2: conflict ----------


def test_a_conflict_is_not_yet_with_resolve_conflict(project, capsys):
    data = inputs()
    data["pr"].update(mergeable=False, mergeable_state="dirty")
    got, _ = check(project, capsys, data)
    [r] = got["reasons"]
    assert r["id"] == "conflict" and r["action"] == "resolve_conflict"
    out, _ = check(project, capsys, data, as_json=False)
    assert out.startswith("Not yet")


def test_mergeable_unknown_says_github_is_still_checking(project, capsys):
    data = inputs()
    data["pr"].update(mergeable=None, mergeable_state="unknown")
    got, _ = check(project, capsys, data)
    [r] = got["reasons"]
    assert r["id"] == "mergeable_unknown"
    assert "GitHub is still checking this change" in r["wording"]["new"]["message"]
    assert "minute" in r["fix"]


def test_gh_cli_shapes_are_read_too(project, capsys):
    data = inputs()
    data["pr"] = {"number": 12, "headRefOid": HEAD, "baseRefName": "main", "mergeable": "CONFLICTING", "mergeStateStatus": "DIRTY", "reviewRequests": []}
    data["files"] = {"files": [{"path": "src/app.py"}]}
    data["commits"] = {"commits": [{"oid": EARLIER}, {"oid": HEAD}]}
    data["reviews"] = {"reviews": []}
    data["comments"] = {"comments": [{"author": {"login": "owner"}, "body": rec(), "createdAt": "2026-10-16T09:00:00Z", "url": "https://github.com/acme/demo/pull/12#issuecomment-100"}]}
    data["rulesets"] = [ruleset("tests", include=("refs/heads/main",))]
    got, _ = check(project, capsys, data)
    assert ids(got) == ["conflict"]


# ---------- rule 3: up to date ----------


def test_behind_the_base_is_not_yet_with_update_branch(project, capsys):
    data = inputs()
    data["compare"] = {"status": "diverged", "ahead_by": 2, "behind_by": 3}
    got, _ = check(project, capsys, data)
    [r] = got["reasons"]
    assert r["id"] == "behind" and r["action"] == "update_branch" and r["implements"] == "flow §4.3"
    assert "main has moved on" in r["wording"]["new"]["message"]


# ---------- rule 4: reviews by people ----------


def thread(resolved, who="dev"):
    return {"isResolved": resolved, "comments": {"nodes": [{"author": {"login": who}, "body": "why?"}]}}


def test_an_unresolved_thread_is_not_yet_naming_who_asked(project, capsys):
    data = inputs()
    data["threads"] = [thread(False, "stranger"), thread(True)]
    got, _ = check(project, capsys, data)
    [r] = got["reasons"]
    assert r["id"] == "unresolved_threads" and "@stranger" in r["message"]


def test_threads_in_graphqls_own_shape(project, capsys):
    data = inputs()
    data["threads"] = {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [thread(False)]}}}}}
    got, _ = check(project, capsys, data)
    assert ids(got) == ["unresolved_threads"]


def review(state, who="dev", rid=1, when="2026-10-16T09:00:00Z"):
    return {"id": rid, "user": {"login": who}, "state": state, "submitted_at": when, "body": ""}


def test_outstanding_changes_requested_is_not_yet_naming_who(project, capsys):
    data = inputs()
    data["reviews"] = [review("CHANGES_REQUESTED")]
    got, _ = check(project, capsys, data)
    [r] = got["reasons"]
    assert r["id"] == "changes_requested" and "@dev" in r["message"]


def test_changes_requested_followed_by_that_reviewers_approval_doesnt_block(project, capsys):
    data = inputs()
    data["reviews"] = [review("CHANGES_REQUESTED", rid=1), review("COMMENTED", "keeper", rid=2), review("APPROVED", rid=3)]
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]
    data["reviews"] = [review("CHANGES_REQUESTED", rid=1), review("APPROVED", "keeper", rid=2), review("COMMENTED", rid=3)]
    got, _ = check(project, capsys, data)
    assert ids(got) == ["changes_requested"]


def test_changes_requested_followed_by_a_new_review_request_doesnt_block(project, capsys):
    data = inputs()
    data["reviews"] = [review("CHANGES_REQUESTED")]
    data["pr"]["requested_reviewers"] = [{"login": "dev"}]
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]


def test_a_plain_comment_never_blocks(project, capsys):
    data = inputs()
    data["comments"].append(comment("Looks odd to me, why this?", author="stranger", cid=101))
    data["reviews"] = [review("COMMENTED", "stranger")]
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]


def test_changes_requested_from_an_account_without_write_access_is_ignored(project, capsys):
    data = inputs()
    data["reviews"] = [review("CHANGES_REQUESTED", "stranger"), review("CHANGES_REQUESTED", "nobody-listed", rid=2)]
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]


# ---------- rule 5: the review panel ----------


def test_no_review_record_is_nobody_has_reviewed_this_change(project, capsys):
    data = inputs()
    data["comments"] = [comment("Thanks!")]
    got, _ = check(project, capsys, data)
    [r] = got["reasons"]
    assert r["id"] == "no_review" and r["action"] == "review" and r["implements"] == "flow §4.4"
    assert "nobody has reviewed this change" in r["wording"]["new"]["message"]


def test_a_not_clean_last_round_is_not_yet(project, capsys):
    data = inputs()
    data["comments"] = [comment(rec(rnd=1), cid=1), comment(rec(rnd=2, clean=False), cid=2)]
    got, _ = check(project, capsys, data)
    [r] = got["reasons"]
    assert r["id"] == "review_not_clean" and r["action"] == "review"


def test_a_clean_round_on_the_head_is_ready(project, capsys):
    data = inputs()
    data["comments"] = [comment(rec(rnd=1, clean=False), cid=1), comment(rec(rnd=2), cid=2)]
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]


def test_a_clean_round_on_an_earlier_commit_needs_a_later_clean_pass_on_the_head(project, capsys):
    data = inputs()
    data["comments"] = [comment(rec(commit=EARLIER), cid=1)]
    got, _ = check(project, capsys, data)
    [r] = got["reasons"]
    assert r["id"] == "review_stale" and r["action"] == "review"
    assert "the newest changes haven't been reviewed" in r["wording"]["new"]["message"]

    data["comments"].append(comment(rec("pass", commit=HEAD), cid=2))
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]

    data["comments"][1] = comment(rec("pass", commit=HEAD, clean=False), cid=2)
    got, _ = check(project, capsys, data)
    assert ids(got) == ["review_stale"]


def test_a_pass_before_the_round_doesnt_cover_it(project, capsys):
    data = inputs()
    data["comments"] = [comment(rec("pass", commit=HEAD), cid=1), comment(rec(rnd=2, commit=EARLIER), cid=2)]
    got, _ = check(project, capsys, data)
    assert ids(got) == ["review_stale"]


def test_a_record_naming_a_commit_outside_the_pr_is_ignored(project, capsys):
    data = inputs()
    data["comments"] = [comment(rec(commit=OUTSIDE))]
    got, _ = check(project, capsys, data)
    assert ids(got) == ["no_review"]
    data["comments"] = [comment(rec(commit=HEAD), cid=1), comment(rec(rnd=2, commit=OUTSIDE, clean=False), cid=2)]
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]


def test_a_record_from_an_account_without_write_access_is_ignored(project, capsys):
    data = inputs()
    data["comments"] = [comment(rec(), author="stranger")]
    got, _ = check(project, capsys, data)
    assert ids(got) == ["no_review"]
    data["comments"] = [comment(rec(), author="nobody-listed")]
    got, _ = check(project, capsys, data)
    assert ids(got) == ["no_review"]
    data["comments"] = [comment(rec(), author="dev")]
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]


def test_permissions_in_the_apis_own_shapes(project, capsys):
    data = inputs()
    data["comments"] = [comment(rec(), author="Keeper")]
    data["permissions"] = [{"permission": "write", "role_name": "maintain", "user": {"login": "keeper"}}]
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]
    data["permissions"] = [{"login": "keeper", "permissions": {"admin": False, "maintain": False, "push": False, "triage": True, "pull": True}}]
    got, _ = check(project, capsys, data)
    assert ids(got) == ["no_review"]


# ---------- rule 6: the suite's evidence (until #81) ----------


def test_ci_none_is_not_yet_until_the_evidence_is_read(project, capsys):
    project.write(checks=(), none=True)
    data = inputs()
    data["rulesets"] = []
    data["checks"] = {"total_count": 0, "check_runs": []}
    got, _ = check(project, capsys, data)
    [r] = got["reasons"]
    assert r["id"] == "evidence_missing" and r["implements"] == "flow §4.2"
    assert "the tests' results haven't been posted for this commit" in r["wording"]["new"]["message"]


# ---------- rule 7: previews ----------


def preview(state, commit=HEAD, url="https://pr-12.demo.pages.dev"):
    return {"state": state, "url": url, "commit": commit}


def test_a_failed_preview_is_not_yet(project, capsys):
    data = inputs()
    data["preview"] = preview("failed")
    got, _ = check(project, capsys, data)
    [r] = got["reasons"]
    assert r["id"] == "preview_failed" and "didn't build" in r["wording"]["new"]["message"]


@pytest.mark.parametrize("state, commit", [("building", HEAD), ("built", EARLIER)])
def test_a_building_preview_or_one_for_an_older_commit_is_still_building(project, capsys, state, commit):
    data = inputs()
    data["preview"] = preview(state, commit)
    got, _ = check(project, capsys, data)
    [r] = got["reasons"]
    assert r["id"] == "preview_building" and "still building" in r["wording"]["new"]["message"]


def test_a_built_preview_gives_its_link(project, capsys):
    data = inputs()
    data["preview"] = preview("built")
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]
    assert got["preview"] == {"state": "built", "url": "https://pr-12.demo.pages.dev"}
    out, _ = check(project, capsys, data, as_json=False)
    assert "https://pr-12.demo.pages.dev" in out


def test_no_previews_is_a_note_never_a_block(project, capsys):
    got, _ = check(project, capsys, inputs())
    assert got["decision"] == "ready"
    [n] = [n for n in got["notes"] if n["id"] == "no_previews"]
    assert "no try-it link for this project" in n["message"]
    data = inputs()
    data["preview"] = {"state": "none"}
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready" and "no_previews" in note_ids(got)


# ---------- kit and CI files ----------


def kit_change():
    data = inputs()
    data["files"] = [{"filename": "src/app.py"}, {"filename": ".github/workflows/ci.yml"}, {"filename": "docs/x.md", "previous_filename": ".claude/workflow/flow.md"}]
    return data


def test_kit_files_for_the_owner_are_ready_once_read(project, capsys):
    got, _ = check(project, capsys, kit_change(), "--asker", "Owner")
    assert got["decision"] == "owner_review"
    assert got["files"] == [".github/workflows/ci.yml", ".claude/workflow/flow.md"]
    out, _ = check(project, capsys, kit_change(), "--asker", "owner", as_json=False)
    assert out.startswith("Ready once you've read the changes to these files")
    assert ".github/workflows/ci.yml" in out


def test_kit_files_for_someone_else_need_the_owners_review(project, capsys):
    out, _ = check(project, capsys, kit_change(), "--asker", "dev", as_json=False)
    assert out.startswith("Needs the owner's review")
    got, _ = check(project, capsys, kit_change())
    assert got["decision"] == "owner_review" and got["owner"] is False


def test_an_admin_counts_as_the_owner_when_the_profile_names_none(project, capsys):
    project.write(owner="")
    out, _ = check(project, capsys, kit_change(), "--asker", "owner", as_json=False)
    assert out.startswith("Ready once you've read")
    out, _ = check(project, capsys, kit_change(), "--asker", "keeper", as_json=False)
    assert out.startswith("Needs the owner's review")


def test_kit_files_with_another_rule_failing_is_not_yet(project, capsys):
    data = kit_change()
    data["compare"]["behind_by"] = 1
    got, _ = check(project, capsys, data, "--asker", "owner")
    assert got["decision"] == "not_yet"
    assert "kit_files" in note_ids(got)


# ---------- wording, every reason, malformed input, the checkout ----------


def everything_wrong():
    data = inputs()
    data["checks"]["check_runs"] = [run_("tests", "failure")]
    data["pr"].update(mergeable=False, mergeable_state="dirty")
    data["compare"]["behind_by"] = 4
    data["threads"] = [thread(False)]
    data["reviews"] = [review("CHANGES_REQUESTED")]
    data["comments"] = []
    data["preview"] = preview("failed")
    return data


def test_every_reason_that_applies_is_listed(project, capsys):
    got, code = check(project, capsys, everything_wrong())
    assert code == 0
    assert set(ids(got)) == {"checks_failed", "conflict", "behind", "unresolved_threads", "changes_requested", "no_review", "preview_failed"}
    out, _ = check(project, capsys, everything_wrong(), as_json=False)
    assert len([line for line in out.splitlines() if line.startswith("- ")]) >= 7


def test_every_reason_is_worded_for_both_levels_with_the_same_decision(project, capsys, monkeypatch):
    seen = {}
    for level in ("new", "developer"):
        monkeypatch.setenv("WORKFLOW_EXPERIENCE", level)
        got, _ = check(project, capsys, everything_wrong())
        seen[level] = got
        assert got["experience"] == level
        for r in got["reasons"]:
            assert r["message"] == r["wording"][level]["message"] and r["fix"] == r["wording"][level]["fix"]
    assert seen["new"]["decision"] == seen["developer"]["decision"] == "not_yet"
    assert ids(seen["new"]) == ids(seen["developer"])
    for r in seen["new"]["reasons"]:
        assert r["wording"]["new"]["message"] != r["wording"]["developer"]["message"], r["id"]


def test_unknown_experience_is_worded_as_new(project, capsys, monkeypatch):
    monkeypatch.delenv("WORKFLOW_EXPERIENCE")
    got, _ = check(project, capsys, everything_wrong())
    assert got["experience"] == "new"


def test_every_reason_id_is_worded_at_both_levels_in_the_module():
    for rid, reason in merge.REASONS.items():
        assert set(reason.wording) == {"new", "developer"}, rid
        assert rid == "couldnt_read" or reason.rule in {r.id for r in merge.RULES}, rid
        for msg, fix in reason.wording.values():
            assert msg.startswith("Not yet") and fix, rid


@pytest.mark.parametrize("name", FLAGS)
def test_malformed_input_is_a_couldnt_read_reason_never_ready(project, capsys, name):
    got, code = check(project, capsys, inputs(), raw={name: "{not json"})
    assert code == 0
    assert got["decision"] == "not_yet"
    [r] = [r for r in got["reasons"] if r["id"] == "couldnt_read"]
    assert r["input"] == name and "couldn't read" in r["message"]


@pytest.mark.parametrize("name", FLAGS)
def test_input_in_the_wrong_shape_is_a_couldnt_read_reason(project, capsys, name):
    got, code = check(project, capsys, inputs(), raw={name: json.dumps({"surprise": [1, 2]}) if name != "pr" else "[1]"})
    assert code == 0
    assert got["decision"] == "not_yet"
    assert [r["input"] for r in got["reasons"] if r["id"] == "couldnt_read"] == [name]


@pytest.mark.parametrize("name", FLAGS)
def test_an_input_not_given_is_a_couldnt_read_reason(project, capsys, name):
    got, code = check(project, capsys, inputs(), leave_out=(name,))
    assert code == 0 and got["decision"] == "not_yet"
    assert [r["input"] for r in got["reasons"] if r["id"] == "couldnt_read"] == [name]


def test_a_missing_file_and_a_broken_profile_are_couldnt_read_too(project, capsys):
    got, code = check(project, capsys, inputs(), "--pr", str(project / "nope.json"))
    assert code == 0 and got["decision"] == "not_yet"
    assert [r["input"] for r in got["reasons"] if r["id"] == "couldnt_read"] == ["pr"]
    (project / ".claude/workflow/profile.toml").write_text("[project\n")
    got, code = check(project, capsys, inputs())
    assert code == 0 and got["decision"] == "not_yet"
    assert [r["input"] for r in got["reasons"] if r["id"] == "couldnt_read"] == ["profile"]


def test_a_head_that_isnt_a_full_sha_is_couldnt_read(project, capsys):
    data = inputs()
    data["pr"]["head"]["sha"] = "abc123"
    got, code = check(project, capsys, data)
    assert code == 0 and got["decision"] == "not_yet"
    assert [r["input"] for r in got["reasons"] if r["id"] == "couldnt_read"] == ["pr"]


def test_nothing_in_the_checkout_changes(project, capsys):
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "add", "-A"], cwd=project, check=True)
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "init"], cwd=project, check=True)
    before = sorted((p.relative_to(project).as_posix(), p.stat().st_mtime_ns) for p in project.rglob("*") if ".git" not in p.parts)
    check(project, capsys, everything_wrong())
    check(project, capsys, kit_change(), "--asker", "owner", as_json=False)
    after = sorted((p.relative_to(project).as_posix(), p.stat().st_mtime_ns) for p in project.rglob("*") if ".git" not in p.parts)
    assert before == after
    status = subprocess.run(["git", "status", "--porcelain", "--ignored"], cwd=project, capture_output=True, text=True, check=True).stdout
    assert status == ""


def test_the_command_is_listed_in_the_clis_usage(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "workflow merge-check" in capsys.readouterr().out


# ---------- flow §4 and the command's rules in step (#39's seam 3) ----------


def flow_items(path):
    text = path.read_text(encoding="utf-8")
    section = text.split("## 4. The merge rule", 1)[1].split("\n## ", 1)[0]
    return section, {f"flow §4.{n}" for n in re.findall(r"^(\d+)\. \*\*", section, re.M)}


def test_flow_4_and_the_commands_rules_are_in_step():
    section, items = flow_items(KIT / "docs/flow.md")
    assert items, "flow §4 has no numbered items"
    implemented = {r.implements for r in merge.RULES if r.implements.startswith("flow §4.")}
    assert implemented == items, (items - implemented, implemented - items)
    for r in merge.RULES:
        assert r.implements.startswith("flow §4.") or r.implements == "#30", r.id
    assert "`workflow merge-check`" in section and "one implementation" in section
