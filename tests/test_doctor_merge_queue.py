"""#246: doctor suggests a merge queue where it fits, and checks the base's
workflows for `merge_group`. Seam 1 of #243: `workflow doctor --json` with
fixture files (`--repo`, `--rulesets`, `--org`, `--ci`, `--commits`, `--runs`,
`--now`) and the workflow files as they are on `origin/<base>` in a real git
checkout; and seam 6, the check-setup skill's text."""

import copy
import json
import re
import shutil
import subprocess

import pytest

from changelog_notes import since_0110
from conftest import KIT
from test_doctor import RULESET, SETTINGS, _bin, _prof, _project, _report
from test_doctor_github import _rs, _rule, _without

NOW = "2026-10-25T12:00:00Z"
CHECKS = '[ci]\nrequired_checks = ["tests"]\n'
PROFILE = _prof('experience = "new"\nruleset = true\n', CHECKS)
ORG = {**SETTINGS, "owner": {"login": "acme", "type": "Organization"}, "visibility": "public", "private": False}
PRIVATE = {**ORG, "visibility": "private", "private": True}
PERSONAL = {**SETTINGS, "owner": {"login": "someone", "type": "User"}, "visibility": "public", "private": False}
QUEUE_RULE = {"type": "merge_queue", "parameters": {"merge_method": "MERGE", "grouping_strategy": "ALLGREEN", "check_response_timeout_minutes": 60}}

CI_YML = """name: CI
on:
  pull_request:
  push:
    branches: [main]
  merge_group:
jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - run: true
"""
NO_MERGE_GROUP = CI_YML.replace("  merge_group:\n", "")
LABELER_YML = "name: Labeler\non:\n  pull_request:\njobs:\n  label:\n    runs-on: ubuntu-latest\n    steps:\n      - run: true\n"


def _queued(rs=None, strict=False):
    """The protecting ruleset with a merge-queue rule, "up to date" off unless `strict`."""
    rs = copy.deepcopy(rs or RULESET)
    rs["rules"].append(QUEUE_RULE)
    _rule(rs, "required_status_checks")["parameters"]["strict_required_status_checks_policy"] = strict
    return rs


def _check_run(name, sha, suite, app="github-actions", started="2026-10-24T10:00:00Z", completed="2026-10-24T10:12:00Z", id_=1):
    return {"id": id_, "name": name, "head_sha": sha, "status": "completed", "conclusion": "success", "started_at": started,
            "completed_at": completed, "app": {"slug": app}, "check_suite": {"id": suite}}


def _workflow_run(sha, suite, path=".github/workflows/ci.yml"):
    return {"id": suite * 10, "name": "CI", "head_sha": sha, "check_suite_id": suite, "path": path}


def _entry(sha, base, runs, workflow_runs):
    return {"sha": sha, "base": base, "check_runs": {"total_count": len(runs), "check_runs": runs},
            "workflow_runs": {"total_count": len(workflow_runs), "workflow_runs": workflow_runs}}


BASE_SHA, PR_SHA = "a" * 40, "b" * 40
# The required check `tests` from ci.yml on the base and a PR head; a labeller
# behind no required check on the PR head.
CI = [
    _entry(BASE_SHA, True, [_check_run("tests", BASE_SHA, 11)], [_workflow_run(BASE_SHA, 11)]),
    _entry(PR_SHA, False, [_check_run("tests", PR_SHA, 21, id_=2), _check_run("label", PR_SHA, 22, id_=3)],
           [_workflow_run(PR_SHA, 21), _workflow_run(PR_SHA, 22, ".github/workflows/labeler.yml")]),
]


def _commit(sha, date, parents=()):
    return {"sha": sha, "commit": {"committer": {"date": date}}, "parents": [{"sha": p} for p in parents]}


def _chain(n, last="2026-10-25T11:00:00Z", hours=6):
    """`n` first-parent commits on the base, newest first, `hours` apart,
    each a merge with a second parent off the chain."""
    from datetime import datetime, timedelta

    t = datetime.fromisoformat(last.replace("Z", "+00:00"))
    shas = [f"{k:040x}" for k in range(1, n + 2)]
    return [_commit(shas[k], (t - timedelta(hours=hours * k)).strftime("%Y-%m-%dT%H:%M:%SZ"), (shas[k + 1], "f" * 40)) for k in range(n)]


def _git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
                   cwd=root, check=True, capture_output=True)


def _checkout(tmp_path, base_files, worktree=None, profile=PROFILE):
    """A project whose `origin/main` holds `base_files` (path: text) under
    `.github/workflows/`, and whose working tree holds `worktree` instead
    when given (uncommitted)."""
    root = _project(tmp_path, profile=profile)
    _git(root, "init", "-q", "-b", "work")
    wf = root / ".github/workflows"
    wf.mkdir(parents=True, exist_ok=True)
    for name, text in base_files.items():
        (wf / name).write_text(text)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    for name, text in (worktree or {}).items():
        (wf / name).write_text(text)
    return root


def _path(tmp_path, gh=None):
    """The fake PATH, with the real `git` on it."""
    d = _bin(tmp_path, gh=gh)
    git = shutil.which("git")
    if not (d / "git").exists():
        (d / "git").symlink_to(git)
    return d


def _inputs(tmp_path, rulesets=(RULESET,), settings=ORG, org=None, ci=CI, commits=None, runs=(), now=NOW):
    d = tmp_path / "input"
    d.mkdir(exist_ok=True)
    args = []
    for flag, value in (("--rulesets", list(rulesets)), ("--repo", settings), ("--org", org), ("--ci", ci),
                        ("--commits", _chain(3) if commits is None else commits), ("--runs", list(runs))):
        if value is None:
            continue
        f = d / (flag[2:] + ".json")
        f.write_text(value if isinstance(value, str) else json.dumps(value))
        args += [flag, str(f)]
    return [*args, "--now", now] if now else args


def _doc(tmp_path, root, *args, env=None, gh=None, **kw):
    return _report(tmp_path, root, *_inputs(tmp_path, **kw), *args, path=_path(tmp_path, gh), env=env)


def _github(tmp_path, root, **kw):
    r = _doc(tmp_path, root, **kw)
    return {ln["id"]: ln for ln in r["lines"] if ln["group"] == "GitHub"}, r


@pytest.fixture
def project(tmp_path):
    return _checkout(tmp_path, {"ci.yml": CI_YML, "labeler.yml": LABELER_YML})


# ---------- the suggestion ----------


def test_the_suggestion_appears_for_a_public_organisation_repository_with_required_checks(tmp_path, project):
    lines, r = _github(tmp_path, project)
    q = lines["github.merge_queue"]
    assert (q["status"], q["offer"]) == ("note", "use_merge_queue"), q
    assert "merge queue" in q["message"] and "Use a merge queue" in q["fix"]
    assert r["merge_queue"]["available"] == "yes" and r["merge_queue"]["queue"] is False
    assert not [ln for ln in r["lines"] if ln["status"] == "gap"], r["lines"]


@pytest.mark.parametrize("level", ["new", "developer"])
def test_a_private_organisation_repository_whose_plan_cant_be_read_names_enterprise_cloud_and_says_check_first(tmp_path, project, level):
    lines, r = _github(tmp_path, project, settings=PRIVATE, org={"login": "acme"}, env={"WORKFLOW_EXPERIENCE": level})
    q = lines["github.merge_queue"]
    assert (q["status"], q["offer"]) == ("note", "use_merge_queue"), q
    assert "Enterprise Cloud" in q["message"]
    assert re.search(r"\bcheck\b", q["message"] + " " + q["fix"], re.I)
    assert r["merge_queue"]["available"] == "check_plan"


def test_an_unreadable_organisation_is_the_same_as_an_unreadable_plan(tmp_path, project):
    lines, r = _github(tmp_path, project, settings=PRIVATE, org='{"message": "Not Found"', )
    assert lines["github.merge_queue"]["offer"] == "use_merge_queue"
    assert r["merge_queue"]["available"] == "check_plan"


@pytest.mark.parametrize("settings, org", [
    ({**ORG, "visibility": "internal", "private": True}, None),
    (PRIVATE, {"login": "acme", "plan": {"name": "enterprise"}}),
], ids=["internal", "enterprise-cloud"])
def test_an_internal_or_enterprise_cloud_repository_gets_the_plain_suggestion(tmp_path, project, settings, org):
    lines, r = _github(tmp_path, project, settings=settings, org=org)
    q = lines["github.merge_queue"]
    assert q["offer"] == "use_merge_queue" and "Enterprise Cloud" not in q["message"]
    assert r["merge_queue"]["available"] == "yes"


@pytest.mark.parametrize("settings, org, rulesets, profile", [
    (PERSONAL, None, (RULESET,), PROFILE),
    (PRIVATE, {"login": "acme", "plan": {"name": "team"}}, (RULESET,), PROFILE),
    (ORG, None, (_without(_rs(), "required_status_checks"),), _prof('experience = "new"\nruleset = true\n')),
    (SETTINGS, None, (RULESET,), PROFILE),
], ids=["personal", "private-on-team", "no-required-checks", "owner-unknown"])
def test_no_suggestion_where_github_wont_give_a_queue_or_nothing_is_required(tmp_path, settings, org, rulesets, profile):
    root = _checkout(tmp_path, {"ci.yml": CI_YML}, profile=profile)
    lines, r = _github(tmp_path, root, settings=settings, org=org, rulesets=rulesets)
    assert "github.merge_queue" not in lines and "github.merge_group" not in lines, sorted(lines)
    assert not any(ln["offer"] == "use_merge_queue" for ln in r["lines"])


def test_no_suggestion_in_solo_mode(tmp_path):
    root = _checkout(tmp_path, {"ci.yml": CI_YML}, profile=_prof('experience = "new"\nruleset = false\n', CHECKS))
    lines, _ = _github(tmp_path, root)
    assert "github.merge_queue" not in lines


def test_with_the_queue_on_the_line_says_so_and_offers_nothing(tmp_path, project):
    lines, r = _github(tmp_path, project, rulesets=(_queued(),))
    q = lines["github.merge_queue"]
    assert (q["status"], q["offer"]) == ("fine", None), q
    assert r["merge_queue"]["queue"] is True


# ---------- the merge_group check ----------


def test_merge_group_on_every_workflow_behind_a_required_check_is_fine(tmp_path, project):
    lines, r = _github(tmp_path, project)
    mg = lines["github.merge_group"]
    assert mg["status"] == "fine", mg
    assert "ci.yml" in mg["message"]
    assert r["merge_queue"]["merge_group"]["clean"] is True


def test_only_workflows_behind_required_checks_are_read(tmp_path, project):
    # labeler.yml has no merge_group, but no required check comes from it.
    lines, r = _github(tmp_path, project)
    assert "labeler" not in lines["github.merge_group"]["message"]
    assert [w["path"] for w in r["merge_queue"]["merge_group"]["workflows"]] == [".github/workflows/ci.yml"]


def test_the_workflows_are_read_from_the_base_not_the_checkout(tmp_path):
    # The base lacks merge_group; the working tree has it: the base's counts.
    root = _checkout(tmp_path / "a", {"ci.yml": NO_MERGE_GROUP}, worktree={"ci.yml": CI_YML})
    lines, _ = _github(tmp_path / "a", root)
    assert lines["github.merge_group"]["status"] == "note", lines["github.merge_group"]
    # And the other way round.
    root = _checkout(tmp_path / "b", {"ci.yml": CI_YML}, worktree={"ci.yml": NO_MERGE_GROUP})
    lines, _ = _github(tmp_path / "b", root)
    assert lines["github.merge_group"]["status"] == "fine", lines["github.merge_group"]


def test_no_origin_base_is_cant_check_saying_to_fetch_it(tmp_path):
    root = _checkout(tmp_path, {"ci.yml": CI_YML})
    _git(root, "update-ref", "-d", "refs/remotes/origin/main")
    lines, _ = _github(tmp_path, root)
    mg = lines["github.merge_group"]
    assert mg["status"] == "cant_check" and "origin/main" in mg["message"], mg
    assert "git fetch origin main" in mg["fix"]


def test_a_missing_trigger_is_a_gap_only_with_the_queue_on(tmp_path):
    root = _checkout(tmp_path, {"ci.yml": NO_MERGE_GROUP})
    off, r = _github(tmp_path, root)
    assert off["github.merge_group"]["status"] == "note", off["github.merge_group"]
    assert "ci.yml" in off["github.merge_group"]["message"]
    assert r["merge_queue"]["merge_group"]["clean"] is False
    assert [w["state"] for w in r["merge_queue"]["merge_group"]["workflows"]] == ["missing"]
    on, _ = _github(tmp_path, root, rulesets=(_queued(),))
    assert on["github.merge_group"]["status"] == "gap", on["github.merge_group"]
    assert "merge_group" in on["github.merge_group"]["fix"]


@pytest.mark.parametrize("on_block", [
    "on: [push, pull_request]\n",
    "on:\n  - push\n  - pull_request\n",
    "on: push\n",
    "on:\n  push:\n    branches: [main]\n",
], ids=["inline-list", "block-list", "scalar", "push-only"])
def test_an_on_that_isnt_a_mapping_with_pull_request_is_cant_check(tmp_path, on_block):
    root = _checkout(tmp_path, {"ci.yml": "name: CI\n" + on_block + "jobs:\n  tests:\n    runs-on: x\n"})
    lines, r = _github(tmp_path, root)
    mg = lines["github.merge_group"]
    assert mg["status"] == "cant_check", mg
    assert "ci.yml" in mg["message"] and "pull_request" in mg["message"]
    assert [w["state"] for w in r["merge_queue"]["merge_group"]["workflows"]] == ["cant_check"]


@pytest.mark.parametrize("text", [
    "name: CI\non: {pull_request: {}, merge_group: {}}\njobs: {}\n",
    "name: CI\non:\n  pull_request: &pr\n  merge_group: *pr\njobs: {}\n",
    "name: CI\njobs: {}\n",
    "name: CI\non:\n\tpull_request:\n",
    "name: CI\non:\n  pull_request:\non:\n  merge_group:\n",
    "name: CI\non:\n  pull_request:\n  merge_group:\n    branches: [ma?n]\n",
], ids=["flow-mapping", "anchor", "no-on", "tab", "twice", "pattern"])
def test_an_on_block_it_cant_read_is_cant_check_never_fine(tmp_path, text):
    root = _checkout(tmp_path, {"ci.yml": text})
    lines, _ = _github(tmp_path, root)
    assert lines["github.merge_group"]["status"] == "cant_check", lines["github.merge_group"]


@pytest.mark.parametrize("merge_group, state", [
    ("  merge_group:\n    branches: [release]\n", "excluded"),
    ("  merge_group:\n    branches:\n      - release\n", "excluded"),
    ("  merge_group:\n    branches-ignore: [main]\n", "excluded"),
    ("  merge_group:\n    branches: [main, release]\n", "ready"),
    ("  merge_group:\n    branches:\n      - 'main'\n", "ready"),
    ("  merge_group:\n    types: [checks_requested]\n    branches: ['**']\n", "ready"),
    ("  merge_group: # the queue\n    types: [checks_requested]\n", "ready"),
], ids=["inline", "block", "ignore", "both", "quoted", "glob", "comment"])
def test_a_branches_filter_that_leaves_out_the_base_is_a_gap_with_the_queue_on(tmp_path, merge_group, state):
    text = "name: CI\non:\n  pull_request:\n" + merge_group + "jobs:\n  tests:\n    runs-on: x\n"
    root = _checkout(tmp_path, {"ci.yml": text})
    lines, r = _github(tmp_path, root, rulesets=(_queued(),))
    assert [w["state"] for w in r["merge_queue"]["merge_group"]["workflows"]] == [state]
    assert lines["github.merge_group"]["status"] == ("gap" if state == "excluded" else "fine"), lines["github.merge_group"]
    if state == "excluded":
        assert "main" in lines["github.merge_group"]["message"] and "branches" in lines["github.merge_group"]["message"]


def test_a_check_from_another_ci_service_is_cant_check_with_githubs_rule(tmp_path, project):
    ci = [_entry(BASE_SHA, True, [_check_run("tests", BASE_SHA, 31, app="circleci-checks")], [])]
    lines, r = _github(tmp_path, project, ci=ci)
    mg = lines["github.merge_group"]
    assert mg["status"] == "cant_check", mg
    assert "tests" in mg["message"] and "gh-readonly-queue/main" in mg["message"] + mg["fix"]
    assert [c["state"] for c in r["merge_queue"]["merge_group"]["checks"]] == ["other_ci"]


def test_a_required_check_with_no_run_seen_says_so_naming_it_never_another_ci_service(tmp_path):
    profile = _prof('experience = "new"\nruleset = true\n', '[ci]\nrequired_checks = ["tests", "lint"]\n')
    rs = _rs()
    _rule(rs, "required_status_checks")["parameters"]["required_status_checks"].append({"context": "lint"})
    root = _checkout(tmp_path, {"ci.yml": CI_YML}, profile=profile)
    lines, r = _github(tmp_path, root, rulesets=(rs,))
    mg = lines["github.merge_group"]
    assert mg["status"] == "cant_check", mg
    assert "no run seen" in mg["message"] and "`lint`" in mg["message"]
    assert "gh-readonly-queue" not in mg["message"]
    assert {c["name"]: c["state"] for c in r["merge_queue"]["merge_group"]["checks"]} == {"tests": "actions", "lint": "no_run"}


def test_ci_that_isnt_githubs_shape_is_cant_check(tmp_path, project):
    lines, _ = _github(tmp_path, project, ci=[{"sha": BASE_SHA}])
    assert lines["github.merge_group"]["status"] == "cant_check"


# ---------- github.up_to_date with the queue ----------


def test_the_queue_meets_up_to_date_and_its_fix_never_offers_it(tmp_path, project):
    lines, _ = _github(tmp_path, project, rulesets=(_queued(),))
    u = lines["github.up_to_date"]
    assert u["status"] == "fine", u
    assert "merge queue" in u["message"] and u["fix"] == "" and u["offer"] is None


def test_another_ruleset_keeping_up_to_date_on_is_reported(tmp_path, project):
    org_rs = _rs(id=202, name="Org rules", source_type="Organization", source="acme",
                 rules=[{"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": True,
                                                                          "required_status_checks": [{"context": "tests"}]}}])
    for level in ("new", "developer"):
        lines, _ = _github(tmp_path, project, rulesets=(_queued(), org_rs), env={"WORKFLOW_EXPERIENCE": level})
        u = lines["github.up_to_date"]
        assert u["status"] == "note", u
        assert "Org rules" in u["message"]
        assert "turn" in u["fix"].lower() and "off" in u["fix"].lower()


def test_a_merge_queue_rule_in_an_unsure_ruleset_is_cant_check(tmp_path, project):
    unsure = _queued(_rs(id=203, name="Queue", conditions={"ref_name": {"include": ["refs/heads/ma*"], "exclude": []}}))
    rs = _rs()
    _rule(rs, "required_status_checks")["parameters"]["strict_required_status_checks_policy"] = False
    lines, r = _github(tmp_path, project, rulesets=(rs, unsure))
    u = lines["github.up_to_date"]
    assert u["status"] == "cant_check", u
    assert "Queue" in u["message"]
    assert "github.merge_queue" not in lines and r["merge_queue"]["queue"] is None


# ---------- the signals ----------


def test_the_signals_are_reported_for_a_fixed_now(tmp_path, project):
    ci = [
        _entry("1" * 40, True, [_check_run("tests", "1" * 40, 41, completed="2026-10-24T10:30:00Z")], [_workflow_run("1" * 40, 41)]),
        _entry("2" * 40, True, [_check_run("tests", "2" * 40, 42, completed="2026-10-24T10:10:00Z"),
                                _check_run("lint", "2" * 40, 43, started="2026-10-24T10:01:00Z", completed="2026-10-24T10:12:00Z", id_=4)],
               [_workflow_run("2" * 40, 42), _workflow_run("2" * 40, 43)]),
        _entry("3" * 40, True, [_check_run("tests", "3" * 40, 44, completed="2026-10-24T10:12:00Z")], [_workflow_run("3" * 40, 44)]),
        _entry(PR_SHA, False, [_check_run("tests", PR_SHA, 45, completed="2026-10-24T12:00:00Z")], [_workflow_run(PR_SHA, 45)]),
    ]
    # 30 first-parent commits 6 hours apart from 11:00 on the 25th: 28 in the 7 days to NOW.
    lines, r = _github(tmp_path, project, ci=ci, commits=_chain(30), runs=[{"number": 7, "state": "open", "labels": [{"name": "workflow:run"}]}])
    s = r["merge_queue"]["signals"]
    assert s["now"] == NOW
    assert s["ci_minutes"] == {"longest": 30, "typical": 12, "commits": 3}
    assert (s["base_commits_7d"], s["base_commits_at_least"]) == (28, False)
    assert (s["runs_set_up"], s["run_in_progress"]) == (True, True)
    msg = lines["github.merge_queue"]["message"]
    assert "12 minutes" in msg and "30" in msg and "28 times" in msg
    # A later `now` counts fewer.
    _, later = _github(tmp_path, project, ci=ci, commits=_chain(30), now="2026-10-27T12:00:00Z")
    assert later["merge_queue"]["signals"]["base_commits_7d"] == 20


def test_commits_running_off_the_page_inside_the_window_are_counted_as_at_least(tmp_path, project):
    commits = _chain(10, hours=1)  # the 10th's first parent isn't listed, and is still inside the 7 days
    _, r = _github(tmp_path, project, commits=commits)
    s = r["merge_queue"]["signals"]
    assert (s["base_commits_7d"], s["base_commits_at_least"]) == (10, True)


def test_signals_that_cant_be_read_are_none_never_zero(tmp_path, project):
    _, r = _github(tmp_path, project, commits="nope")
    assert r["merge_queue"]["signals"]["base_commits_7d"] is None


def test_a_bad_now_is_refused(tmp_path, project):
    p = subprocess.run([shutil.which("python3"), "-B", str(project / ".claude/workflow/bin/workflow.py"), "doctor", "--json", "--now", "yesterday"],
                       cwd=project, capture_output=True, text=True)
    assert p.returncode == 2 and "--now" in p.stderr


# ---------- wording, and gh ----------


def test_each_new_line_has_both_wordings_with_the_same_status(tmp_path, project):
    for kw in ({}, {"settings": PRIVATE}, {"rulesets": (_queued(),)}):
        n, _ = _github(tmp_path, project, env={"WORKFLOW_EXPERIENCE": "new"}, **kw)
        d, _ = _github(tmp_path, project, env={"WORKFLOW_EXPERIENCE": "developer"}, **kw)
        for id_ in ("github.merge_queue", "github.merge_group", "github.up_to_date"):
            assert (n[id_]["status"], n[id_]["offer"]) == (d[id_]["status"], d[id_]["offer"]), id_
            assert n[id_]["message"] != d[id_]["message"], id_


def test_gh_reads_the_same_as_files_and_only_reads(tmp_path, project):
    import fake_gh
    from test_doctor import gh_routes

    routes = gh_routes(settings=PRIVATE)
    routes["orgs/acme"] = {"login": "acme", "plan": {"name": "enterprise"}}
    routes["repos/acme/demo/commits"] = _chain(3)
    routes["repos/acme/demo/pulls"] = fake_gh.pages([{"number": 5, "state": "open", "body": "", "head": {"sha": PR_SHA, "repo": {"full_name": "acme/demo"}}}])
    routes["repos/acme/demo/issues"] = []
    # The base's newest commit (the chain's first) ran the check; its older ones nothing.
    head, *older = [c["sha"] for c in _chain(3)]
    routes[f"repos/acme/demo/commits/{head}/check-runs"] = {"total_count": 1, "check_runs": [_check_run("tests", head, 11)]}
    for sha in older:
        routes[f"repos/acme/demo/commits/{sha}/check-runs"] = {"total_count": 0, "check_runs": []}
    routes["repos/acme/demo/actions/runs"] = {"total_count": 2, "workflow_runs": [_workflow_run(head, 11), _workflow_run(PR_SHA, 21)]}
    routes[f"repos/acme/demo/commits/{PR_SHA}/check-runs"] = {"total_count": 1, "check_runs": [_check_run("tests", PR_SHA, 21)]}
    path = _path(tmp_path, gh=routes)
    r = _report(tmp_path, project, "--now", NOW, path=path)
    lines = {ln["id"]: ln for ln in r["lines"]}
    assert lines["github.merge_queue"]["offer"] == "use_merge_queue" and r["merge_queue"]["available"] == "yes"
    assert lines["github.merge_group"]["status"] == "fine", lines["github.merge_group"]
    assert r["merge_queue"]["signals"]["base_commits_7d"] == 3
    gh = fake_gh.FakeGh(path)
    assert "orgs/acme" in [p.split("?")[0] for p in gh.paths()]
    for args in gh.calls():
        assert args[0] == "api" and not {"-X", "--method", "-f", "-F", "--field", "--raw-field", "--input"} & set(args), args


def test_without_the_new_inputs_a_repository_reads_as_before(tmp_path):
    # SETTINGS names no owner: no suggestion, no line, no extra read.
    import fake_gh

    root = _project(tmp_path, profile=PROFILE)
    path = _bin(tmp_path)
    r = _report(tmp_path, root, path=path)
    assert not [ln for ln in r["lines"] if ln["id"] in ("github.merge_queue", "github.merge_group")]
    assert r["merge_queue"] is None or r["merge_queue"]["available"] is None
    paths = [p.split("?")[0] for p in fake_gh.FakeGh(path).paths()]
    assert not [p for p in paths if p.startswith("orgs/") or "/actions/" in p or p.endswith("/commits")], paths


# ---------- the kit's text ----------


def _skill(name):
    return (KIT / f"skills/{name}/SKILL.md").read_text(encoding="utf-8")


def test_check_setup_gathers_the_new_inputs():
    text = _skill("check-setup")
    for flag in ("--org", "--ci", "--commits", "--now"):
        assert flag in text, flag
    assert "git fetch origin <base>" in text
    assert "actions/runs?head_sha=" in text and "orgs/<owner>" in text


def test_check_setup_recommends_the_queue_with_a_reason_never_as_a_gap():
    text = _skill("check-setup")
    offers = text[text.index("## 3. The offers"):]
    assert "`use_merge_queue`" in offers and "**Use a merge queue**" in offers
    assert "never a gap" in text
    assert "(Recommended)" in offers and "reason" in offers
    assert "Not now" in offers
    assert "in progress" in offers  # never offered while a run is in progress


def test_the_offer_is_doctors():
    from workflow import doctor

    assert doctor.OFFERS["use_merge_queue"] == "Use a merge queue"


def test_the_changelog_has_a_note_under_unreleased():
    notes = since_0110()
    assert "#246" in notes and "merge_group" in notes and "use_merge_queue" in notes
