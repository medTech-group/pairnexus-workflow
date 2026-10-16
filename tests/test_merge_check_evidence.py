"""`workflow merge-check`: the suite's evidence, the run's waivers, and fetching
with `gh` (#81; #39's seam 1), through the CLI, fed recorded files and a fake
`gh` on the PATH (`tests/fake_gh.py`).

The pull request where every rule holds is `test_merge_check.inputs()`; each
test breaks or adds one thing.
"""

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import fake_gh
from test_merge_check import EARLIER, HEAD, comment, ids, inputs, note_ids, project, review, run_  # noqa: F401 (project is a fixture)
from workflow import charter as charter_mod
from workflow import cli, evidence, merge, state
from workflow.profile import parse

MARKERS = ["exit code 143", "The operation was canceled"]
FIX = "Run `workflow evidence --base-ref origin/main` and post the report."


def markers(project, markers=MARKERS):
    """The profile's ci.killed_markers ([ci] is the profile's last table)."""
    path = project / ".claude/workflow/profile.toml"
    path.write_text(path.read_text() + f"killed_markers = {json.dumps(markers)}\n")


def report(sha=HEAD, ok=True, dirty=False):
    """The report `workflow evidence` writes, from its own writer."""
    prof = parse({"project": {"name": "demo", "repo": "acme/demo", "rules": ["CLAUDE.md"]},
                  "commands": {"suite": [{"name": "unit", "run": "python3 -m pytest {files} -q", "files": "tests/test_*.py"}]}}, Path("."))
    shard = evidence.ShardResult("unit", 0, ["tests/test_a.py"], 0 if ok else 1, 10, 0 if ok else 1, 0, 0, 1.0, "10 passed in 0.1s")
    _, md = evidence.report(sha, prof, [shard], 10, dirty=["notes.txt"] if dirty else None)
    return md


def with_report(data, body=None, author="owner", cid=200):
    data["comments"].append(comment(body if body is not None else report(), author=author, cid=cid))
    data["pr"]["comments"] = len(data["comments"])
    return data


def run(project, capsys, data, *extra, files=None, as_json=True):
    """merge-check on `data` as files, plus `files` ({flag: text}) as given."""
    d = project.parent / "in"
    d.mkdir(exist_ok=True)
    args = ["merge-check"]
    for name, value in data.items():
        (d / f"{name}.json").write_text(json.dumps(value))
        args += [f"--{name}", str(d / f"{name}.json")]
    for flag, text in (files or {}).items():
        (d / flag).write_text(text)
        args += [f"--{flag}", str(d / flag)]
    args += list(extra) + (["--json"] if as_json else [])
    code = cli.main(args)
    out = capsys.readouterr().out
    return (json.loads(out) if as_json else out), code


def ci_none(project):
    project.write(checks=(), none=True)
    data = inputs()
    data["rulesets"] = []
    data["checks"] = {"total_count": 0, "check_runs": []}
    return data


# ---------- rule 6: the suite's evidence ----------


def test_the_headline_is_the_one_evidence_writes_and_reads_back():
    first = report().splitlines()[0]
    assert first == f"**Local full suite on `{HEAD}`**: passed"
    assert evidence.read_headline(first) == (HEAD, True, False)
    assert evidence.read_headline(report(ok=False).splitlines()[0]) == (HEAD, False, False)
    assert evidence.read_headline(report(dirty=True).splitlines()[0]) == (HEAD, True, True)
    assert evidence.read_headline("Local full suite on HEAD: passed") is None


def test_under_ci_none_a_passing_report_for_the_head_is_ready(project, capsys):
    got, code = run(project, capsys, with_report(ci_none(project)))
    assert code == 0
    assert got["decision"] == "ready", got["reasons"]


def test_a_short_sha_matching_the_head_counts(project, capsys):
    got, _ = run(project, capsys, with_report(ci_none(project), report(sha=HEAD[:7])))
    assert got["decision"] == "ready", got["reasons"]


@pytest.mark.parametrize("case", ["none", "failed", "earlier", "dirty", "no write access", "not the first line", "too short"])
def test_a_missing_or_unusable_report_is_not_yet_with_the_fix(project, capsys, monkeypatch, case):
    monkeypatch.setenv("WORKFLOW_EXPERIENCE", "developer")
    data = ci_none(project)
    if case == "failed":
        with_report(data, report(ok=False))
    elif case == "earlier":
        with_report(data, report(sha=EARLIER))
    elif case == "dirty":
        with_report(data, report(dirty=True))
    elif case == "no write access":
        with_report(data, author="stranger")
    elif case == "not the first line":
        with_report(data, "Here's the evidence:\n" + report())
    elif case == "too short":
        with_report(data, report(sha=HEAD[:6]))
    got, code = run(project, capsys, data)
    assert code == 0 and got["decision"] == "not_yet"
    assert ids(got) == ["evidence_missing"]
    [r] = got["reasons"]
    assert r["implements"] == "flow §4.2"
    assert r["wording"]["new"]["message"] == "Not yet: the tests' results haven't been posted for this commit."
    assert r["fix"] == FIX
    # A report read but not counted is a note; a line that isn't a report's headline isn't one.
    assert ("evidence_ignored" in note_ids(got)) == (case in ("failed", "earlier", "dirty", "no write access"))


def test_the_latest_report_for_the_head_decides(project, capsys):
    data = with_report(with_report(ci_none(project), cid=200), report(ok=False), cid=201)
    got, _ = run(project, capsys, data)
    assert ids(got) == ["evidence_missing"]
    data = with_report(with_report(ci_none(project), report(ok=False), cid=200), cid=201)
    got, _ = run(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]


def test_without_ci_none_or_a_waiver_a_missing_report_isnt_a_reason(project, capsys):
    got, _ = run(project, capsys, inputs())
    assert got["decision"] == "ready", got["reasons"]
    data = inputs()
    data["comments"].append(comment(report(ok=False), cid=200))
    data["pr"]["comments"] = 2
    got, _ = run(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]


# ---------- waivers in rule 1 ----------


def a_charter(waived=("tests",), mode="session", approved_by="owner"):
    now = datetime.now(timezone.utc)
    c = charter_mod.defaults()
    c["limits"]["ends_at"] = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    c["merge"] = {"mode": mode, "waived_checks": list(waived)}
    if approved_by:
        c["approved"] = {"by": approved_by, "at": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "the owner said go in chat"}
    return c


def waiver_case(project, monkeypatch, conclusion="failure", log="Error: Process completed with exit code 143.", role="conductor", evidence=True, log_name="1"):
    markers(project)
    monkeypatch.setenv("WORKFLOW_ROLE", role)
    data = inputs()
    data["checks"]["check_runs"] = [run_("tests", conclusion)]
    if evidence:
        with_report(data)
    logs = project.parent / "logs"
    logs.mkdir(exist_ok=True)
    if log is not None:
        # As `gh run view --log-failed` prints it: job, step, Actions' timestamp, the line.
        (logs / log_name).write_text("".join(f"tests\tRun tests\t2026-10-16T10:00:0{i}.1234567Z {line}\n" for i, line in enumerate(log.split("\n"))))
    return data, logs


def test_a_waived_check_killed_not_failed_counts(project, capsys, monkeypatch):
    data, logs = waiver_case(project, monkeypatch)
    got, code = run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter())})
    assert code == 0
    assert got["decision"] == "ready", got["reasons"]
    assert got["checks"] == [{"name": "tests", "state": "waived", "required": True}]
    assert "waived" in note_ids(got)


def test_a_killed_pytest_run_with_only_passing_progress_counts(project, capsys, monkeypatch):
    log = "tests/test_a.py ......ss..   [ 40%]\n.....xX...   [ 80%]\ntests/test_b.py ..\nError: Process completed with exit code 143."
    data, logs = waiver_case(project, monkeypatch, log=log)
    got, _ = run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter())})
    assert got["decision"] == "ready", got["reasons"]


def test_a_cancelled_waived_check_with_a_marker_counts(project, capsys, monkeypatch):
    data, logs = waiver_case(project, monkeypatch, conclusion="cancelled", log="##[error]The operation was canceled.")
    got, _ = run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter())})
    assert got["decision"] == "ready", got["reasons"]


def test_a_log_file_ending_in_log_counts_too(project, capsys, monkeypatch):
    data, logs = waiver_case(project, monkeypatch, log_name="1.log")
    got, _ = run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter())})
    assert got["decision"] == "ready", got["reasons"]


@pytest.mark.parametrize("log_name", ["tests", "2.log", "tests.1.log"])
def test_a_log_not_named_by_the_heads_run_isnt_read(project, capsys, monkeypatch, log_name):
    # A log kept from an earlier, killed run (another id) never waives this run's failure.
    data, logs = waiver_case(project, monkeypatch, log_name=log_name)
    got, _ = run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter())})
    assert ids(got) == ["checks_failed"]
    [n] = [n for n in got["notes"] if n["id"] == "waiver_not_taken"]
    assert "no log was given for its run on the head" in n["message"]


@pytest.mark.parametrize("log", [
    "FAILED tests/test_a.py::test_x - AssertionError\n1 failed, 3 passed in 0.2s\nError: Process completed with exit code 143.",
    "Error: Process completed with exit code 1.\nError: Process completed with exit code 143.",
    "Error: Process completed with exit code 143.\n2 errors in 0.1s",
    "tests/test_a.py::test_x FAILED\nError: Process completed with exit code 143.",
    "FAILED tests/test_a.py::test_x - AssertionError\nError: Process completed with exit code 143.",
    "--- FAIL: TestX (0.00s)\nError: Process completed with exit code 143.",
    "  ✕ adds two numbers (3 ms)\nError: Process completed with exit code 143.",
    "ERROR tests/test_a.py::test_x - ImportError\nError: Process completed with exit code 143.",
    "tests/test_a.py ..F..                                                    [ 40%]\nError: Process completed with exit code 143.",
    "tests/test_a.py::test_x[a b] FAILED\nError: Process completed with exit code 143.",
    "\x1b[31mtests/test_a.py ..E\x1b[0m [ 40%]\nError: Process completed with exit code 143.",
    "..F.......                                                               [ 40%]\nError: Process completed with exit code 143.",
    "..........F\nError: Process completed with exit code 143.",
    "[gw0] [ 50%] FAILED tests/test_a.py::test_x\nError: Process completed with exit code 143.",
    "FAIL src/sum.test.js\nError: Process completed with exit code 143.",
])
def test_a_killed_marker_beside_a_real_failure_blocks(project, capsys, monkeypatch, log):
    data, logs = waiver_case(project, monkeypatch, log=log)
    got, _ = run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter())})
    assert ids(got) == ["checks_failed"]
    assert "waiver_not_taken" in note_ids(got)


def test_a_pending_waived_check_stays_pending(project, capsys, monkeypatch):
    data, logs = waiver_case(project, monkeypatch)
    data["checks"]["check_runs"] = [run_("tests", status="in_progress")]
    got, _ = run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter())})
    assert ids(got) == ["checks_pending"]


def test_no_waiver_when_the_profile_names_no_owner(project, capsys, monkeypatch):
    data, logs = waiver_case(project, monkeypatch)
    path = project / ".claude/workflow/profile.toml"
    path.write_text(path.read_text().replace('owner = "owner"\n', ""))
    got, _ = run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter(approved_by="anyone"))})
    assert ids(got) == ["checks_failed"]
    [n] = [n for n in got["notes"] if n["id"] == "charter_refused"]
    assert "names no `project.owner`" in n["message"]


def test_a_used_waiver_makes_the_evidence_required(project, capsys, monkeypatch):
    data, logs = waiver_case(project, monkeypatch, evidence=False)
    got, _ = run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter())})
    assert ids(got) == ["evidence_missing"]
    assert "`tests` was waived" in got["reasons"][0]["wording"]["developer"]["message"]


def test_a_waived_check_that_really_failed_blocks(project, capsys, monkeypatch):
    data, logs = waiver_case(project, monkeypatch, log="FAILED tests/test_a.py::test_x - AssertionError")
    got, _ = run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter())})
    assert ids(got) == ["checks_failed"]
    assert "waiver_not_taken" in note_ids(got)


def test_a_waived_check_without_its_log_blocks(project, capsys, monkeypatch):
    data, logs = waiver_case(project, monkeypatch, log=None)
    got, _ = run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter())})
    assert ids(got) == ["checks_failed"]
    got, _ = run(project, capsys, data, files={"charter": json.dumps(a_charter())})
    assert ids(got) == ["checks_failed"]
    assert "waiver_not_taken" in note_ids(got)


def test_an_unwaived_check_with_a_killed_marker_blocks(project, capsys, monkeypatch):
    project.write(checks=("tests", "lint"))
    data, logs = waiver_case(project, monkeypatch)
    data["rulesets"][0]["rules"][-1]["parameters"]["required_status_checks"].append({"context": "lint"})
    data["checks"] = {"total_count": 2, "check_runs": [run_("tests", "failure", rid=1), run_("lint", rid=2)]}
    got, _ = run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter(waived=("lint",)))})
    assert ids(got) == ["checks_failed"]


def test_no_waiver_without_a_charter(project, capsys, monkeypatch):
    data, logs = waiver_case(project, monkeypatch)
    got, _ = run(project, capsys, data, "--check-logs", str(logs))
    assert ids(got) == ["checks_failed"]


@pytest.mark.parametrize("bad, words", [
    ({"approved_by": None}, "not been approved"),
    ({"approved_by": "someone-else"}, "only the owner approves a run"),
    ({"mode": "auto-merge"}, "auto-merge"),
    ({"mode": "owner"}, "merge.mode session"),
    ("not a charter at all", "no charter"),
])
def test_no_waiver_from_an_unapproved_or_unusable_charter(project, capsys, monkeypatch, bad, words):
    data, logs = waiver_case(project, monkeypatch)
    text = bad if isinstance(bad, str) else json.dumps(a_charter(**bad))  # its times taken now, not at import
    got, code = run(project, capsys, data, "--check-logs", str(logs), files={"charter": text})
    assert code == 0
    assert ids(got) == ["checks_failed"]
    [n] = [n for n in got["notes"] if n["id"] == "charter_refused"]
    assert n["message"].startswith("The charter wasn't used, so no check is waived:")
    assert words in n["message"]


def test_the_charter_from_the_tracking_issues_body(project, capsys, monkeypatch):
    data, logs = waiver_case(project, monkeypatch)
    s = state.empty(a_charter())
    s["run_id"] = "run-1"
    body = state.put("# Unattended run\n\nThe run's tracking issue.", s)
    got, _ = run(project, capsys, data, "--check-logs", str(logs), files={"charter": body})
    assert got["decision"] == "ready", got["reasons"]
    issue = json.dumps({"number": 130, "title": "Unattended run", "body": body})
    got, _ = run(project, capsys, data, "--check-logs", str(logs), files={"charter": issue})
    assert got["decision"] == "ready", got["reasons"]


def test_never_a_waiver_in_an_attended_session(project, capsys, monkeypatch):
    data, logs = waiver_case(project, monkeypatch, role="attended")
    got, code = run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter())})
    assert code == 0
    assert ids(got) == ["checks_failed"]
    [n] = [n for n in got["notes"] if n["id"] == "charter_ignored"]
    assert n["message"] == "The charter (--charter) is ignored in an attended session: nobody waives a check by hand."


@pytest.mark.parametrize("role, branch", [(None, "main"), (None, "claude/build-81"), ("atended", "main"), ("", "claude/build-81")])
def test_no_waiver_unless_workflow_role_says_ticket_or_conductor(project, capsys, monkeypatch, role, branch):
    # The guard reads a ticket branch, or a role it doesn't know, as ticket (its strictest);
    # for waivers that would be the loosest, so only WORKFLOW_ROLE's own word counts.
    data, logs = waiver_case(project, monkeypatch)
    if role is None:
        monkeypatch.delenv("WORKFLOW_ROLE")
    else:
        monkeypatch.setenv("WORKFLOW_ROLE", role)
    subprocess.run(["git", "init", "-q", "-b", branch], cwd=project, check=True)
    got, code = run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter())})
    assert code == 0
    assert ids(got) == ["checks_failed"]
    [n] = [n for n in got["notes"] if n["id"] == "charter_ignored"]
    assert n["message"] == "The charter (--charter) is ignored unless `WORKFLOW_ROLE` says this is a ticket or conductor session: nobody waives a check by hand."


def test_a_ticket_session_takes_the_waiver(project, capsys, monkeypatch):
    data, logs = waiver_case(project, monkeypatch, role="ticket")
    got, _ = run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter())})
    assert got["decision"] == "ready", got["reasons"]


# ---------- fetching with gh ----------

REPO = "repos/acme/demo"


def routes(data=None):
    """The fake gh's answers for PR 12, as GitHub gives them: every page."""
    data = data or with_report(inputs())
    thread_page = {"data": {"repository": {"pullRequest": {"reviewThreads": {"totalCount": 0, "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}}}}}
    return {
        f"{REPO}/pulls/12": data["pr"],
        f"{REPO}/pulls/12/files": fake_gh.pages(data["files"]),
        f"{REPO}/pulls/12/commits": fake_gh.pages(data["commits"]),
        f"{REPO}/commits/{HEAD}/check-runs": fake_gh.pages(data["checks"]),
        f"{REPO}/commits/{HEAD}/status": fake_gh.pages({"sha": HEAD, "state": "success", "total_count": 0, "statuses": []}),
        f"{REPO}/rulesets": fake_gh.pages([{"id": 1, "name": "Protect main"}]),
        f"{REPO}/rulesets/1": data["rulesets"][0],
        "graphql": fake_gh.pages(thread_page),
        f"{REPO}/pulls/12/reviews": fake_gh.pages(data["reviews"]),
        f"{REPO}/issues/12/comments": fake_gh.pages(data["comments"][:1], data["comments"][1:]),
        f"{REPO}/collaborators/owner/permission": {"permission": "admin", "role_name": "admin", "user": {"login": "owner"}},
        f"{REPO}/compare/main...{HEAD}": data["compare"],
    }


def test_fetch_reads_every_input_through_gh(project, capsys, tmp_path, monkeypatch):
    gh = fake_gh.install(tmp_path, monkeypatch, routes())
    got, code = run(project, capsys, {}, "--fetch", "12")
    assert code == 0
    assert got["decision"] == "ready", got["reasons"]
    asked = [p.split("?")[0] for p in gh.paths()]
    for route in routes():
        assert route in asked, route
    [threads] = [c for c in gh.calls() if "graphql" in c]
    assert {"owner=acme", "name=demo"} <= set(threads) and threads[threads.index("number=12") - 1] == "-F"
    # Every list is fetched whole: each call that can page does.
    for args in gh.calls():
        path = next(a for a in args[1:] if not a.startswith("-"))
        if path.split("?")[0] in (f"{REPO}/pulls/12", f"{REPO}/rulesets/1", f"{REPO}/compare/main...{HEAD}") or "/collaborators/" in path:
            continue
        assert "--paginate" in args and "--slurp" in args, args


def test_fetch_with_a_gh_too_old_to_slurp_reads_the_pages_one_after_another(project, capsys, tmp_path, monkeypatch):
    fake_gh.install(tmp_path, monkeypatch, routes(), slurp=False)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert got["decision"] == "ready", got["reasons"]


def test_a_file_given_wins_over_gh(project, capsys, tmp_path, monkeypatch):
    gh = fake_gh.install(tmp_path, monkeypatch, routes())
    pr = with_report(inputs())["pr"]
    pr.update(mergeable=False, mergeable_state="dirty")
    got, _ = run(project, capsys, {"pr": pr}, "--fetch", "12")
    assert ids(got) == ["conflict"]
    assert f"{REPO}/pulls/12" not in [p.split("?")[0] for p in gh.paths()]


def test_fetched_pages_left_out_are_couldnt_read(project, capsys, tmp_path, monkeypatch):
    r = routes()
    page = {"data": {"repository": {"pullRequest": {"reviewThreads": {"totalCount": 101, "pageInfo": {"hasNextPage": True, "endCursor": "x"}, "nodes": []}}}}}
    r["graphql"] = fake_gh.pages(page)
    fake_gh.install(tmp_path, monkeypatch, r)
    got, code = run(project, capsys, {}, "--fetch", "12")
    assert code == 0 and got["decision"] == "not_yet"
    assert [x["input"] for x in got["reasons"] if x["id"] == "couldnt_read"] == ["threads"]


def test_review_authors_permissions_are_fetched_too(project, capsys, tmp_path, monkeypatch):
    data = with_report(inputs())
    data["reviews"] = [review("CHANGES_REQUESTED", who="dev")]
    r = routes(data)
    r[f"{REPO}/collaborators/dev/permission"] = {"permission": "write", "role_name": "write", "user": {"login": "dev"}}
    gh = fake_gh.install(tmp_path, monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert ids(got) == ["changes_requested"]
    assert f"{REPO}/collaborators/dev/permission" in gh.paths()


def test_a_pr_file_of_another_pull_request_is_couldnt_read(project, capsys, tmp_path, monkeypatch):
    fake_gh.install(tmp_path, monkeypatch, routes())
    pr = with_report(inputs())["pr"]
    pr["number"] = 13
    got, code = run(project, capsys, {"pr": pr}, "--fetch", "12")
    assert code == 0 and got["decision"] == "not_yet"
    [x] = [x for x in got["reasons"] if x["id"] == "couldnt_read"]
    assert x["input"] == "pr" and "it is #13, not #12 (--fetch)" in x["wording"]["developer"]["message"]
    del pr["number"]
    got, _ = run(project, capsys, {"pr": pr}, "--fetch", "12")
    [x] = [x for x in got["reasons"] if x["id"] == "couldnt_read"]
    assert x["input"] == "pr" and "it doesn't say its number, not #12 (--fetch)" in x["wording"]["developer"]["message"]


def test_output_from_gh_that_isnt_json_is_couldnt_read(project, capsys, tmp_path, monkeypatch):
    r = routes()
    r[f"{REPO}/pulls/12/files"] = fake_gh.reply(stdout="<html>oops</html>")
    fake_gh.install(tmp_path, monkeypatch, r, slurp=False)
    got, code = run(project, capsys, {}, "--fetch", "12")
    assert code == 0
    [x] = [x for x in got["reasons"] if x["id"] == "couldnt_read"]
    assert x["input"] == "files" and "isn't JSON" in x["wording"]["developer"]["message"]


def test_a_listed_ruleset_without_an_id_is_couldnt_read(project, capsys, tmp_path, monkeypatch):
    r = routes()
    r[f"{REPO}/rulesets"] = fake_gh.pages([{"name": "Protect main"}])
    fake_gh.install(tmp_path, monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert [x["input"] for x in got["reasons"] if x["id"] == "couldnt_read"] == ["rulesets"]


@pytest.mark.parametrize("bad", ["0", "-3", "abc"])
def test_fetch_needs_a_pull_requests_number(project, capsys, bad):
    with pytest.raises(SystemExit):
        cli.main(["merge-check", "--fetch", bad])
    assert "isn't a pull request's number" in capsys.readouterr().err


def test_an_author_github_doesnt_know_has_no_permission(project, capsys, tmp_path, monkeypatch):
    data = inputs()
    data["comments"] = [comment(data["comments"][0]["body"], author="ghost")]
    fake_gh.install(tmp_path, monkeypatch, routes(data))
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert ids(got) == ["no_review"]


def test_a_permission_gh_cant_fetch_is_couldnt_read(project, capsys, tmp_path, monkeypatch):
    r = routes()
    r[f"{REPO}/collaborators/owner/permission"] = fake_gh.reply(exit=1, stderr="gh: Server Error (HTTP 502)")
    fake_gh.install(tmp_path, monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    [x] = [x for x in got["reasons"] if x["id"] == "couldnt_read"]
    assert x["input"] == "permissions" and "HTTP 502" in x["wording"]["developer"]["message"]


def test_without_gh_each_input_says_how_to_give_it_as_a_file(project, capsys, tmp_path, monkeypatch):
    fake_gh.without_gh(tmp_path, monkeypatch)
    monkeypatch.setenv("WORKFLOW_EXPERIENCE", "developer")
    got, code = run(project, capsys, {}, "--fetch", "12")
    assert code == 0 and got["decision"] == "not_yet"
    named = [x["input"] for x in got["reasons"] if x["id"] == "couldnt_read"]
    assert named == [n for n in merge.INPUTS if n != "preview"]
    pr = next(x for x in got["reasons"] if x.get("input") == "pr")
    assert pr["message"] == "Not yet: couldn't read the pull request (--pr): gh (the GitHub CLI) isn't installed here, so it couldn't be fetched: give --pr as a file."
    assert pr["fix"] == "Give --pr as GitHub returns it, every page, then run merge-check again."


def test_gh_not_signed_in_is_couldnt_read_never_ready(project, capsys, tmp_path, monkeypatch):
    fake_gh.install(tmp_path, monkeypatch, routes(), signed_in=False)
    got, code = run(project, capsys, {}, "--fetch", "12")
    assert code == 0 and got["decision"] == "not_yet"
    pr = next(x for x in got["reasons"] if x.get("input") == "pr")
    assert pr["wording"]["developer"]["message"].endswith("gh auth login, so it couldn't be fetched: give --pr as a file.")


def test_without_fetch_or_files_each_input_is_named(project, capsys, tmp_path, monkeypatch):
    gh = fake_gh.install(tmp_path, monkeypatch, routes())
    got, code = run(project, capsys, {})
    assert code == 0 and got["decision"] == "not_yet"
    assert gh.calls() == []
    assert [x["input"] for x in got["reasons"] if x["id"] == "couldnt_read"] == [n for n in merge.INPUTS if n != "preview"]


def test_nothing_in_the_checkout_changes_after_a_fetch_or_a_waiver(project, capsys, tmp_path, monkeypatch):
    data, logs = waiver_case(project, monkeypatch)
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "add", "-A"], cwd=project, check=True)
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "init"], cwd=project, check=True)
    before = sorted((p.relative_to(project).as_posix(), p.stat().st_mtime_ns) for p in project.rglob("*") if ".git" not in p.parts)
    fake_gh.install(tmp_path, monkeypatch, routes())
    run(project, capsys, {}, "--fetch", "12")
    run(project, capsys, data, "--check-logs", str(logs), files={"charter": json.dumps(a_charter())}, as_json=False)
    after = sorted((p.relative_to(project).as_posix(), p.stat().st_mtime_ns) for p in project.rglob("*") if ".git" not in p.parts)
    assert before == after
    status = subprocess.run(["git", "status", "--porcelain", "--ignored"], cwd=project, capture_output=True, text=True, check=True).stdout
    assert status == ""
