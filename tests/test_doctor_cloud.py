"""#60: `workflow doctor`'s Cloud lines: the two environments the profile
names, whether a run has been made, and the note that nothing can read what an
environment holds. Seam 1 of #34: the CLI, with recorded environment JSON
(`--environments`, as `list_environments` returns it), recorded issue JSON
(`--runs`, as the GitHub API returns it) and a fake `gh` on the PATH."""

import json
import os
import subprocess
import sys

import pytest

import fake_gh
from changelog_notes import since_0110
from test_doctor import CLI, ENVIRONMENTS, _bin, _doctor, _each_at_once, _lines, _prof, _project, _report, _snapshot, _unchanged_after_doctor, gh_routes

NAMED = _prof("ruleset = true\n").replace('ticket_environment = "t"', 'ticket_environment = "workflow-ticket"').replace(
    'conductor_environment = "c"', 'conductor_environment = "workflow-conductor"')
RUN_ISSUE = {"number": 185, "title": "Run 2026-10-18", "state": "closed", "labels": [{"name": "workflow:run"}]}
OTHER_ISSUE = {"number": 12, "title": "Notes list order", "state": "open", "labels": [{"name": "ready-for-agent"}]}
NEW = {"WORKFLOW_EXPERIENCE": "new"}
DEV = {"WORKFLOW_EXPERIENCE": "developer"}


def _envs(*names, has_more=False):
    """The account's environments, as `list_environments` returns them."""
    return {"environments": [{"environment_id": f"env_0{k}", "name": n, "description": "", "state": "active", "kind": "anthropic_cloud",
                              "created_at": "2026-10-01T09:00:00Z"} for k, n in enumerate(names)], "has_more": has_more}


def _runs_file(tmp_path, issues):
    """A `--runs` file, outside the checkout."""
    d = tmp_path / "runs-input"
    d.mkdir(parents=True, exist_ok=True)
    (d / "runs.json").write_text(issues if isinstance(issues, str) else json.dumps(issues))
    return ["--runs", str(d / "runs.json")]


def _cloud(tmp_path, root, *args, envs=ENVIRONMENTS, **kw):
    """The report's Cloud lines by id."""
    r = _report(tmp_path, root, *args, environments=envs, **kw)
    return {ln["id"]: ln for ln in r["lines"] if ln["group"] == "Cloud"}


def _environments_line(tmp_path, root, *args, **kw):
    return _cloud(tmp_path, root, *args, **kw)["cloud.environments"]


def _no_gh(tmp_path):
    return _bin(tmp_path, gh=False)


def _gh_runs(tmp_path, issues, **kw):
    """A PATH whose fake `gh` answers for a protected repository and lists
    these `workflow:run` issues."""
    routes = gh_routes()
    routes["repos/acme/demo/issues"] = issues
    return _bin(tmp_path, gh=routes, **kw)


# Both found


def test_both_environments_found_is_fine(tmp_path):
    ln = _environments_line(tmp_path, _project(tmp_path))
    assert (ln["status"], ln["fix"], ln["offer"]) == ("fine", "", None), ln
    assert "`t`" in ln["message"] and "`c`" in ln["message"], ln


def test_both_found_by_their_real_names_in_text(tmp_path):
    root = _project(tmp_path, profile=NAMED)
    p = _doctor(tmp_path, root, environments=_envs("Default", "workflow-conductor", "workflow-ticket"))
    assert p.returncode == 0, p.stderr
    out = p.stdout.splitlines()
    assert "Cloud" in out, p.stdout
    cloud = out[out.index("Cloud") + 1:]
    cloud = cloud[: cloud.index("") if "" in cloud else len(cloud)]
    marked = [ln for ln in cloud if ln.startswith("  [")]
    # The note sorts before the fine line, as notes do.
    assert [m.split("]")[0] for m in marked] == ["  [note", "  [fine"], p.stdout
    assert "workflow-ticket" in " ".join(cloud), p.stdout


def test_both_found_never_reads_whether_a_run_was_made(tmp_path):
    path = _bin(tmp_path)
    _report(tmp_path, _project(tmp_path), path=path)
    assert not [p for p in fake_gh.FakeGh(path).paths() if "issues" in p]


# Neither found


def test_neither_found_with_no_run_made_is_a_note_offering_set_up_unattended_runs(tmp_path):
    root = _project(tmp_path)
    for env in (NEW, DEV):
        ln = _environments_line(tmp_path, root, *_runs_file(tmp_path, [OTHER_ISSUE]), envs=_envs("Default"), path=_no_gh(tmp_path), env=env)
        assert (ln["status"], ln["offer"]) == ("note", "set_up_unattended_runs"), ln
        assert "already made a run" not in ln["message"] and "gap" not in ln["message"], ln
        assert ln["fix"]


def test_neither_found_with_runs_unknown_is_the_same_note_with_the_already_made_a_run_wording(tmp_path):
    root = _project(tmp_path)
    ln = _environments_line(tmp_path, root, envs=_envs("Default"), path=_no_gh(tmp_path), env=NEW)
    assert (ln["status"], ln["offer"]) == ("note", "set_up_unattended_runs"), ln
    assert "If you've already made a run, this is a gap" in ln["message"], ln
    dev = _environments_line(tmp_path, root, envs=_envs("Default"), path=_no_gh(tmp_path), env=DEV)
    assert (dev["status"], dev["offer"]) == ("note", "set_up_unattended_runs"), dev
    assert "gap" in dev["message"] and "workflow:run" in dev["message"], dev


def test_runs_unknown_says_why(tmp_path):
    root = _project(tmp_path)
    signed_out = _bin(tmp_path)
    fake_gh.write(signed_out, gh_routes(), signed_in=False)
    ln = _environments_line(tmp_path, root, envs=_envs(), path=signed_out, env=DEV)
    assert ln["status"] == "note" and "signed in" in ln["message"], ln
    assert "--runs" in ln["fix"], ln
    ln = _environments_line(tmp_path, root, envs=_envs(), path=_no_gh(tmp_path), env=DEV)
    assert "no `gh`" in ln["message"] and "--runs" in ln["message"], ln


def test_an_empty_list_of_environments_is_neither_found(tmp_path):
    ln = _environments_line(tmp_path, _project(tmp_path), *_runs_file(tmp_path, []), envs=_envs())
    assert (ln["status"], ln["offer"]) == ("note", "set_up_unattended_runs"), ln


# One found, or a run made: gaps


@pytest.mark.parametrize("listed, missing, present", [(("t",), "c", "t"), (("c", "Default"), "t", "c")])
def test_one_found_is_a_gap_naming_the_other(tmp_path, listed, missing, present):
    root = _project(tmp_path)
    for env in (NEW, DEV):
        ln = _environments_line(tmp_path, root, envs=_envs(*listed), path=_no_gh(tmp_path), env=env)
        assert ln["status"] == "gap", ln
        assert f"`{missing}`" in ln["message"], ln
        assert f"`{present}`" in ln["message"], ln
        assert ln["offer"] == "set_up_unattended_runs"
        assert ln["fix"]


def test_one_found_doesnt_wait_on_whether_a_run_was_made(tmp_path):
    path = _bin(tmp_path)
    ln = _environments_line(tmp_path, _project(tmp_path), envs=_envs("t"), path=path)
    assert ln["status"] == "gap"
    assert not [p for p in fake_gh.FakeGh(path).paths() if "issues" in p]


def test_neither_found_once_a_run_has_been_made_is_a_gap_naming_both(tmp_path):
    root = _project(tmp_path)
    for env in (NEW, DEV):
        ln = _environments_line(tmp_path, root, *_runs_file(tmp_path, [OTHER_ISSUE, RUN_ISSUE]), envs=_envs("Default"), path=_no_gh(tmp_path), env=env)
        assert ln["status"] == "gap", ln
        assert "`t`" in ln["message"] and "`c`" in ln["message"], ln
        assert "#185" in ln["message"], ln


def test_a_run_made_is_read_with_gh_when_no_file_is_given(tmp_path):
    root = _project(tmp_path)
    path = _gh_runs(tmp_path, [RUN_ISSUE])
    ln = _environments_line(tmp_path, root, envs=_envs("Default"), path=path)
    assert ln["status"] == "gap" and "#185" in ln["message"], ln
    gh = fake_gh.FakeGh(path)
    asked = [p for p in gh.paths() if p.startswith("repos/acme/demo/issues")]
    assert asked and all("labels=workflow:run" in p and "state=all" in p for p in asked), asked
    for args in gh.calls():
        assert args[0] == "api", args
        assert not {"-X", "--method", "-f", "-F", "--field", "--raw-field", "--input"} & set(args), args


def test_no_run_read_with_gh_is_the_note(tmp_path):
    ln = _environments_line(tmp_path, _project(tmp_path), envs=_envs("Default"), path=_gh_runs(tmp_path, []))
    assert (ln["status"], ln["offer"]) == ("note", "set_up_unattended_runs") and "already made a run" not in ln["message"], ln


def test_the_runs_file_wins_over_gh(tmp_path):
    root = _project(tmp_path)
    ln = _environments_line(tmp_path, root, *_runs_file(tmp_path, []), envs=_envs(), path=_gh_runs(tmp_path, [RUN_ISSUE]))
    assert ln["status"] == "note", ln
    ln = _environments_line(tmp_path, root, *_runs_file(tmp_path, [RUN_ISSUE]), envs=_envs(), path=_gh_runs(tmp_path, []))
    assert ln["status"] == "gap", ln


@pytest.mark.parametrize("issues", [
    [[OTHER_ISSUE], [RUN_ISSUE]],  # pages, as `gh api --paginate --slurp` prints them
    {"issues": [RUN_ISSUE], "pageInfo": {"hasNextPage": False}},  # the GitHub MCP tools' list
    {"total_count": 1, "items": [RUN_ISSUE]},  # search's
    [{"number": 185, "title": "Run 2026-10-18"}],  # fetched by its label, without the labels
    [{**RUN_ISSUE, "labels": ["workflow:run"]}],  # labels as names
    [{**RUN_ISSUE, "labels": [{"name": "Workflow:Run"}]}],  # GitHub's labels are matched without case
])
def test_the_runs_file_takes_issues_as_the_github_api_returns_them(tmp_path, issues):
    ln = _environments_line(tmp_path, _project(tmp_path), *_runs_file(tmp_path, issues), envs=_envs(), path=_no_gh(tmp_path))
    assert ln["status"] == "gap", ln


def test_a_pull_request_labelled_workflow_run_isnt_a_run(tmp_path):
    pr = {**RUN_ISSUE, "pull_request": {"url": "https://api.github.com/repos/acme/demo/pulls/185"}}
    ln = _environments_line(tmp_path, _project(tmp_path), *_runs_file(tmp_path, [pr]), envs=_envs(), path=_no_gh(tmp_path))
    assert ln["status"] == "note" and "already made a run" not in ln["message"], ln


@pytest.mark.parametrize("text, why", [("{not json", "runs.json: it isn't valid JSON"), ('"runs"', "--runs: it isn't a list of issues"),
                                       ("[1, 2]", "--runs: an entry isn't an issue")])
def test_a_runs_file_that_cant_be_read_is_runs_unknown_saying_why(tmp_path, text, why):
    ln = _environments_line(tmp_path, _project(tmp_path), *_runs_file(tmp_path, text), envs=_envs(), path=_no_gh(tmp_path), env=DEV)
    assert ln["status"] == "note" and why in ln["message"], ln
    assert "--runs" in ln["message"]


# A typo is not found


def test_a_name_that_differs_only_by_a_typo_is_not_found(tmp_path):
    root = _project(tmp_path, profile=NAMED)
    ln = _environments_line(tmp_path, root, envs=_envs("workflow-tickt", "workflow-conductor"), path=_no_gh(tmp_path))
    assert ln["status"] == "gap", ln
    assert "`workflow-ticket`" in ln["message"] and "`workflow-tickt`" in ln["message"], ln


@pytest.mark.parametrize("listed", [("Workflow-Ticket", "workflow-conductor"), ("workflow-ticket ", "workflow-conductor")])
def test_a_name_that_differs_by_case_or_a_space_is_not_found(tmp_path, listed):
    ln = _environments_line(tmp_path, _project(tmp_path, profile=NAMED), envs=_envs(*listed), path=_no_gh(tmp_path))
    assert ln["status"] == "gap" and "`workflow-ticket`" in ln["message"], ln


def test_neither_found_with_typos_still_names_the_close_ones(tmp_path):
    root = _project(tmp_path, profile=NAMED)
    ln = _environments_line(tmp_path, root, *_runs_file(tmp_path, []), envs=_envs("workflow-tickt", "workflow-condutor"), path=_no_gh(tmp_path))
    assert ln["status"] == "note" and "`workflow-tickt`" in ln["message"] and "`workflow-condutor`" in ln["message"], ln


# No file, or one that can't be read


def test_no_environments_file_is_cant_check_saying_only_a_cloud_session_can(tmp_path):
    root = _project(tmp_path)
    for env in (NEW, DEV):
        ln = _environments_line(tmp_path, root, envs=None, env=env)
        assert (ln["status"], ln["offer"]) == ("cant_check", None), ln
        assert "cloud session" in ln["message"], ln
        assert "cloud session to check the set-up" in ln["fix"], ln


def test_no_environments_file_never_asks_gh(tmp_path):
    path = _bin(tmp_path)
    _environments_line(tmp_path, _project(tmp_path), envs=None, path=path)
    assert not [p for p in fake_gh.FakeGh(path).paths() if "issues" in p or "environment" in p]


def _env_file(tmp_path, text):
    d = tmp_path / "env-input"
    d.mkdir(parents=True, exist_ok=True)
    (d / "environments.json").write_text(text)
    return ["--environments", str(d / "environments.json")]


@pytest.mark.parametrize("text, why", [
    ("{nope", "valid JSON"),
    ('"workflow-ticket"', "list_environments"),
    ('{"environments": [{"environment_id": "env_1"}]}', "list_environments"),
    ('{"environments": "t"}', "list_environments"),
])
def test_an_environments_file_that_cant_be_read_is_cant_check_saying_why(tmp_path, text, why):
    ln = _environments_line(tmp_path, _project(tmp_path), *_env_file(tmp_path, text), envs=None, env=DEV)
    assert ln["status"] == "cant_check" and why in ln["message"], ln
    assert "--environments" in ln["fix"], ln


def test_a_missing_environments_file_is_cant_check(tmp_path):
    ln = _environments_line(tmp_path, _project(tmp_path), "--environments", str(tmp_path / "nowhere.json"), envs=None)
    assert ln["status"] == "cant_check" and "isn't there" in ln["message"], ln


def test_the_environments_as_a_bare_list_are_read_too(tmp_path):
    ln = _environments_line(tmp_path, _project(tmp_path), *_env_file(tmp_path, json.dumps(_envs("t", "c")["environments"])), envs=None)
    assert ln["status"] == "fine", ln


def test_a_list_with_more_to_come_cant_tell_a_missing_one(tmp_path):
    root = _project(tmp_path)
    ln = _environments_line(tmp_path, root, envs=_envs("t", has_more=True), path=_no_gh(tmp_path))
    assert ln["status"] == "cant_check" and "`c`" in ln["message"], ln
    assert _environments_line(tmp_path, root, envs=_envs("t", "c", has_more=True))["status"] == "fine"


def test_environments_from_standard_input(tmp_path):
    root = _project(tmp_path)
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), "HOME": str(tmp_path / "home"), "PATH": str(_no_gh(tmp_path))}
    env.pop("WORKFLOW_EXPERIENCE", None)
    p = subprocess.run([sys.executable, "-B", str(CLI), "doctor", "--json", "--environments", "-"], cwd=root, env=env,
                       input=json.dumps(_envs("t", "c")), capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert _lines(json.loads(p.stdout))["cloud.environments"]["status"] == "fine"


def test_only_one_file_can_be_standard_input(tmp_path):
    root = _project(tmp_path)
    for pair in (("--environments", "--runs"), ("--rulesets", "--environments"), ("--repo", "--runs")):
        p = _doctor(tmp_path, root, pair[0], "-", pair[1], "-", environments=None)
        assert p.returncode == 2 and "standard input" in p.stderr, (pair, p.stderr)


# The profile


def test_an_environment_the_profile_doesnt_name_is_a_gap_saying_so(tmp_path):
    profile = _prof("ruleset = true\n").replace('conductor_environment = "c"\n', "")
    ln = _environments_line(tmp_path, _project(tmp_path, profile=profile), envs=_envs("t", "c"), env=DEV)
    assert ln["status"] == "gap" and "run.conductor_environment" in ln["message"], ln


def test_neither_named_nor_listed_with_no_run_is_the_note(tmp_path):
    profile = _prof("ruleset = true\n").replace('ticket_environment = "t"\n', "").replace('conductor_environment = "c"\n', "")
    ln = _environments_line(tmp_path, _project(tmp_path, profile=profile), *_runs_file(tmp_path, []), envs=_envs("Default"))
    assert (ln["status"], ln["offer"]) == ("note", "set_up_unattended_runs"), ln


def test_no_profile_waits_on_it(tmp_path):
    lines = _cloud(tmp_path, _project(tmp_path, profile=None))
    assert lines["cloud.environments"]["status"] == "cant_check" and "profile" in lines["cloud.environments"]["message"]
    assert lines["cloud.contents"]["status"] == "note"


# The note: nothing can read what an environment holds


def _states(tmp_path, compiled=True):
    """Projects and inputs whose Cloud lines take every status between them."""
    yield _project(tmp_path / "a", compiled=compiled), [], ENVIRONMENTS, None
    yield _project(tmp_path / "b", compiled=compiled), _runs_file(tmp_path / "b", []), _envs("Default"), _no_gh(tmp_path / "b")
    yield _project(tmp_path / "c", compiled=compiled), [], _envs(), _no_gh(tmp_path / "c")
    yield _project(tmp_path / "d", compiled=compiled), [], _envs("t"), _no_gh(tmp_path / "d")
    yield _project(tmp_path / "e", compiled=compiled), _runs_file(tmp_path / "e", [RUN_ISSUE]), _envs(), _no_gh(tmp_path / "e")
    yield _project(tmp_path / "f", compiled=compiled), [], None, None
    yield _project(tmp_path / "g", profile=None, compiled=compiled), [], ENVIRONMENTS, None
    yield _project(tmp_path / "h", compiled=compiled), [], _envs("t", has_more=True), None
    yield _project(tmp_path / "i", profile=NAMED, compiled=compiled), _runs_file(tmp_path / "i", "[1]"), _envs("workflow-tickt"), _no_gh(tmp_path / "i")
    yield _project(tmp_path / "j", compiled=compiled), _env_file(tmp_path / "j", "{nope"), None, None


def test_the_note_that_nothing_can_read_what_an_environment_holds_is_always_there(tmp_path):
    calls = [(root, args, {"environments": envs, "path": path, "env": env})
             for root, args, envs, path in _states(tmp_path) for env in (NEW, DEV)]
    for r in _each_at_once(tmp_path, _report, calls):
        ln = _lines(r)["cloud.contents"]
        assert (ln["status"], ln["group"], ln["offer"]) == ("note", "Cloud", None), ln
        assert "WORKFLOW_ROLE=ticket" in ln["message"] + ln["fix"] and "WORKFLOW_ROLE=conductor" in ln["message"] + ln["fix"], ln
        assert "secret" in ln["message"] + ln["fix"], ln
        cloud = [x["id"] for x in r["lines"] if x["group"] == "Cloud"]
        assert sorted(cloud) == ["cloud.contents", "cloud.environments"], cloud


def test_the_note_names_the_profiles_environments(tmp_path):
    ln = _cloud(tmp_path, _project(tmp_path, profile=NAMED), envs=_envs("workflow-ticket", "workflow-conductor"))["cloud.contents"]
    assert "`workflow-ticket`" in ln["message"] and "`workflow-conductor`" in ln["message"], ln


# Wording, --strict, and changing nothing


def test_each_cloud_wording_for_new_and_developer_with_the_same_statuses(tmp_path):
    seen = set()
    calls = [(root, args, {"environments": envs, "path": path, "env": env})
             for root, args, envs, path in _states(tmp_path) for env in (NEW, DEV)]
    reports = iter(_each_at_once(tmp_path, _report, calls))
    for n, d in zip(reports, reports):
        n, d = _lines(n), _lines(d)
        for id_ in ("cloud.environments", "cloud.contents"):
            seen.add((id_, n[id_]["status"]))
            assert (n[id_]["status"], n[id_]["offer"]) == (d[id_]["status"], d[id_]["offer"]), id_
            assert n[id_]["message"] != d[id_]["message"], (id_, n[id_]["message"])
            if n[id_]["fix"] or d[id_]["fix"]:
                assert n[id_]["fix"] != d[id_]["fix"], (id_, n[id_]["fix"])
    for status in ("fine", "gap", "note", "cant_check"):
        assert ("cloud.environments", status) in seen, status
    assert ("cloud.contents", "note") in seen


def test_strict_passes_on_the_notes_and_fails_on_the_gaps_and_cant_check(tmp_path):
    root = _project(tmp_path)
    ok = _no_gh(tmp_path)
    fake_gh.write(ok, gh_routes())
    assert _doctor(tmp_path, root, "--strict", path=ok).returncode == 0  # both found, and the contents note
    assert _doctor(tmp_path, root, "--strict", *_runs_file(tmp_path, []), environments=_envs("Default"), path=ok).returncode == 0
    # Runs unknown: this `gh` reads the GitHub lines but has no answer for the issues.
    unknown = _environments_line(tmp_path, root, envs=_envs("Default"), path=ok)
    assert unknown["status"] == "note" and "If you've already made a run" in unknown["message"], unknown
    assert _doctor(tmp_path, root, "--strict", environments=_envs("Default"), path=ok).returncode == 0
    assert _doctor(tmp_path, root, "--strict", environments=_envs("t"), path=ok).returncode == 1
    assert _doctor(tmp_path, root, "--strict", *_runs_file(tmp_path, [RUN_ISSUE]), environments=_envs(), path=ok).returncode == 1
    assert _doctor(tmp_path, root, "--strict", environments=None, path=ok).returncode == 1


def test_the_cloud_gap_sorts_before_its_note(tmp_path):
    r = _report(tmp_path, _project(tmp_path), environments=_envs("t"), path=_no_gh(tmp_path))
    cloud = [(x["id"], x["status"]) for x in r["lines"] if x["group"] == "Cloud"]
    assert cloud == [("cloud.environments", "gap"), ("cloud.contents", "note")]


def test_nothing_in_the_checkout_changes_after_a_run(tmp_path):
    calls = []
    for root, args, envs, path in _states(tmp_path, compiled=False):  # so bytecode written would show
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        for extra in ((), ("--json",), ("--strict",)):
            calls.append((root, (*args, *extra), {"environments": envs, "path": path}))
            calls.append((root, extra, {"environments": _envs("Default")}))  # whether a run was made, through the fake gh
    _unchanged_after_doctor(tmp_path, calls)


# Docs


def test_the_changelog_has_a_note_under_unreleased():
    notes = since_0110()
    unreleased = notes[: notes.index("\n## 0.1.11\n")]
    assert "#60" in unreleased and "--environments" in unreleased and "--runs" in unreleased


def test_the_help_names_the_files():
    p = subprocess.run([sys.executable, "-B", str(CLI), "doctor", "--help"], capture_output=True, text=True)
    assert "--environments" in p.stdout and "--runs" in p.stdout


# Round 1 of the review


def test_one_environment_named_for_both_roles_is_a_gap(tmp_path):
    profile = _prof("ruleset = true\n").replace('conductor_environment = "c"', 'conductor_environment = "t"')
    root = _project(tmp_path, profile=profile)
    for env in (NEW, DEV):
        ln = _environments_line(tmp_path, root, envs=_envs("t"), env=env)
        assert (ln["status"], ln["offer"]) == ("gap", "set_up_unattended_runs"), ln
        assert "WORKFLOW_ROLE=ticket" in ln["message"] and "WORKFLOW_ROLE=conductor" in ln["message"], ln
    assert _environments_line(tmp_path, root, envs=None)["status"] == "gap"  # the profile alone says so


def test_an_incomplete_list_with_one_name_unset_cant_tell_the_other(tmp_path):
    profile = _prof("ruleset = true\n").replace('ticket_environment = "t"\n', "")
    ln = _environments_line(tmp_path, _project(tmp_path, profile=profile), *_runs_file(tmp_path, []), envs=_envs("Default", has_more=True))
    assert ln["status"] == "cant_check" and "`c`" in ln["message"], ln


@pytest.mark.parametrize("more", ["true", 1, None])
def test_has_more_that_isnt_true_or_false_is_the_wrong_shape(tmp_path, more):
    envs = {**_envs("t"), "has_more": more}
    ln = _environments_line(tmp_path, _project(tmp_path), envs=envs, path=_no_gh(tmp_path))
    if more is None:
        assert ln["status"] == "gap", ln  # null: as if absent
    else:
        assert ln["status"] == "cant_check" and "shape" in ln["message"], ln


def test_an_environment_that_isnt_active_isnt_found(tmp_path):
    envs = _envs("t", "c")
    envs["environments"][1]["state"] = "archived"
    root = _project(tmp_path)
    for env in (NEW, DEV):
        ln = _environments_line(tmp_path, root, envs=envs, path=_no_gh(tmp_path), env=env)
        assert ln["status"] == "gap" and "`c`" in ln["message"] and "`archived`" in ln["message"] and "active" in ln["message"], ln


def test_an_environment_listed_twice_counts_when_one_is_active(tmp_path):
    envs = _envs("t", "c", "c")
    envs["environments"][1]["state"] = "archived"
    assert _environments_line(tmp_path, _project(tmp_path), envs=envs)["status"] == "fine"


def test_names_are_shown_exactly(tmp_path):
    long_ = "x" * 45
    profile = NAMED.replace("workflow-ticket", long_ + "-ticket").replace("workflow-conductor", long_ + "-conductor")
    ln = _environments_line(tmp_path, _project(tmp_path, profile=profile), envs=_envs(long_ + "-ticket", long_ + "-conductorZ"), path=_no_gh(tmp_path))
    assert ln["status"] == "gap" and "-conductor`" in ln["message"] and "-conductorZ`" in ln["message"], ln
    root = _project(tmp_path / "s", profile=NAMED)
    ln = _environments_line(tmp_path / "s", root, envs=_envs("workflow-ticket ", "work`flow-conductor"), path=_no_gh(tmp_path / "s"))
    assert '`"workflow-ticket "`' in ln["message"] and "work\\u0060flow-conductor" in ln["message"], ln


def test_a_control_character_or_half_a_surrogate_pair_never_reaches_the_terminal(tmp_path):
    root = _project(tmp_path, profile=NAMED)
    envs = '{"environments": [{"name": "\\u001b[2Jworkflow-ticket"}, {"name": "workflow-conductor\\ud800"}]}'
    args = _env_file(tmp_path, envs)
    p = _doctor(tmp_path, root, *args, environments=None, path=_no_gh(tmp_path), env={**NEW, "PYTHONIOENCODING": "utf-8"})
    assert p.returncode == 0, p.stderr
    assert "\x1b" not in p.stdout and "\\u001b" in p.stdout and "\\ud800" in p.stdout, p.stdout


def test_an_empty_file_says_it_is_empty(tmp_path):
    ln = _environments_line(tmp_path, _project(tmp_path), *_env_file(tmp_path, ""), envs=None)
    assert ln["status"] == "cant_check" and "it is empty" in ln["message"], ln


def test_a_run_shown_twice_is_named_once(tmp_path):
    ln = _environments_line(tmp_path, _project(tmp_path), *_runs_file(tmp_path, [[RUN_ISSUE], [RUN_ISSUE]]), envs=_envs(), path=_no_gh(tmp_path))
    assert ln["message"].count("#185") == 1, ln


def test_a_run_without_a_number_is_worded_once(tmp_path):
    ln = _environments_line(tmp_path, _project(tmp_path), *_runs_file(tmp_path, [{"labels": ["workflow:run"]}]), envs=_envs(), path=_no_gh(tmp_path), env=DEV)
    assert ln["status"] == "gap" and ln["message"].count("labelled") == 1, ln


def test_the_runs_read_shares_githubs_time_budget(tmp_path):
    """A `gh` that never answers: the GitHub lines and the runs read wait
    60 seconds in all, not 60 and then 30 more."""
    import time

    path = _no_gh(tmp_path)
    (path / "gh").write_text("#!/bin/sh\nexec sleep 300\n")
    (path / "gh").chmod(0o755)
    start = time.monotonic()
    ln = _environments_line(tmp_path, _project(tmp_path), envs=_envs(), path=path)
    assert time.monotonic() - start < 80
    assert ln["status"] == "note" and "If you've already made a run" in ln["message"], ln


# Round 2 of the review


@pytest.mark.parametrize("text", ['{"message": "Not Found", "documentation_url": "https://docs.github.com/rest", "status": "404"}', "{}", "[{}]",
                                  '{"issues": "x"}'])
def test_an_answer_that_holds_no_issues_isnt_a_run(tmp_path, text):
    ln = _environments_line(tmp_path, _project(tmp_path), *_runs_file(tmp_path, text), envs=_envs(), path=_no_gh(tmp_path), env=DEV)
    assert ln["status"] == "note" and "an entry isn't an issue" in ln["message"], ln


def test_gh_answering_in_the_wrong_shape_says_how_to_tell(tmp_path):
    ln = _environments_line(tmp_path, _project(tmp_path), envs=_envs(), path=_gh_runs(tmp_path, "x"), env=DEV)
    assert ln["status"] == "note" and "it isn't a list of issues" in ln["message"], ln
    assert not ln["fix"].rstrip().endswith(":") and "--runs" in ln["fix"], ln


@pytest.mark.parametrize("hidden", ["\\u200b", "\\u00a0", "\\u202e", "\\u007f", "\\u009b"])
def test_a_character_that_cant_be_seen_is_shown_escaped(tmp_path, hidden):
    root = _project(tmp_path, profile=NAMED)
    args = _env_file(tmp_path, '{"environments": [{"name": "workflow-ticket%s"}, {"name": "workflow-conductor"}]}' % hidden)
    p = _doctor(tmp_path, root, *args, environments=None, path=_no_gh(tmp_path), env={**NEW, "PYTHONIOENCODING": "utf-8"})
    assert p.returncode == 0, p.stderr
    assert json.loads('"%s"' % hidden) not in p.stdout and hidden in p.stdout, p.stdout


def test_a_path_that_cant_be_printed_is_shown_escaped(tmp_path):
    root = _project(tmp_path)
    p = _doctor(tmp_path, root, "--environments", str(tmp_path / "a\x1bb.json"), environments=None, path=_no_gh(tmp_path))
    assert p.returncode == 0, p.stderr
    assert "\x1b" not in p.stdout and "\\u001b" in p.stdout, p.stdout


def test_a_github_value_that_cant_be_printed_is_shown_escaped(tmp_path):
    # A check name with an escape sequence, in the profile and missing from the ruleset.
    from test_doctor_github import _files

    profile = _prof("ruleset = true\n", '[ci]\nrequired_checks = ["tests\\u001b[2J"]\n')
    root = _project(tmp_path, profile=profile)
    p = _doctor(tmp_path, root, *_files(tmp_path), path=_no_gh(tmp_path))
    assert p.returncode == 0, p.stderr
    assert "\x1b" not in p.stdout and "tests\\u001b[2J" in p.stdout, p.stdout


def test_a_state_in_capitals_is_active(tmp_path):
    envs = _envs("t", "c")
    envs["environments"][0]["state"], envs["environments"][1]["state"] = "ACTIVE", "Active"
    assert _environments_line(tmp_path, _project(tmp_path), envs=envs)["status"] == "fine"


def test_an_inactive_environment_isnt_said_to_be_there(tmp_path):
    envs = _envs("t", "c")
    envs["environments"][0]["state"] = "archived"
    ln = _environments_line(tmp_path, _project(tmp_path), envs=envs, env=NEW)
    assert ln["status"] == "gap" and "only `c` is ready" in ln["message"] and "is listed but not active" in ln["message"], ln
    assert "is there" not in ln["message"], ln


def test_the_pages_of_list_environments_are_read_together(tmp_path):
    root = _project(tmp_path)
    pages = [_envs("t", has_more=True), _envs("c")]
    assert _environments_line(tmp_path, root, *_env_file(tmp_path, json.dumps(pages)), envs=None)["status"] == "fine"
    pages = [_envs("Default", has_more=True), _envs("t", has_more=True)]
    assert _environments_line(tmp_path, root, *_env_file(tmp_path, json.dumps(pages)), envs=None)["status"] == "cant_check"


def test_one_environment_for_both_roles_is_named_once_in_the_note(tmp_path):
    profile = _prof("ruleset = true\n").replace('conductor_environment = "c"', 'conductor_environment = "t"')
    root = _project(tmp_path, profile=profile)
    for env in (NEW, DEV):
        ln = _cloud(tmp_path, root, envs=None, env=env)["cloud.contents"]
        assert ln["message"].count("`t`") == 1 and ln["fix"].count("`t`") == 0, ln


def test_one_run_is_worded_as_one(tmp_path):
    ln = _environments_line(tmp_path, _project(tmp_path), *_runs_file(tmp_path, [RUN_ISSUE]), envs=_envs(), path=_no_gh(tmp_path), env=DEV)
    assert "An issue labelled workflow:run exists (#185)" in ln["message"], ln
    assert "to their exact names" in ln["fix"] and "guides both" in ln["fix"], ln


def test_neither_listed_in_an_incomplete_list_says_neither(tmp_path):
    ln = _environments_line(tmp_path, _project(tmp_path), envs=_envs("Default", has_more=True), env=DEV)
    assert "lists neither `t` nor `c`" in ln["message"], ln


def test_a_typo_with_no_run_made_says_to_correct_it(tmp_path):
    root = _project(tmp_path, profile=NAMED)
    ln = _environments_line(tmp_path, root, *_runs_file(tmp_path, []), envs=_envs("workflow-tickt", "workflow-condutor"), path=_no_gh(tmp_path))
    assert ln["status"] == "note" and "typo" in ln["fix"], ln


# Round 3 of the review


def test_an_incomplete_list_still_says_what_is_already_missing(tmp_path):
    profile = _prof("ruleset = true\n").replace('ticket_environment = "t"\n', "")
    root = _project(tmp_path, profile=profile)
    for env in (NEW, DEV):
        ln = _environments_line(tmp_path, root, envs=_envs("Default", has_more=True), env=env)
        assert ln["status"] == "cant_check" and "run.ticket_environment" in ln["message"], ln


@pytest.mark.parametrize("state", [0, {"value": "archived"}, ["active"]])
def test_a_state_that_isnt_text_is_the_wrong_shape(tmp_path, state):
    envs = _envs("t", "c")
    envs["environments"][1]["state"] = state
    ln = _environments_line(tmp_path, _project(tmp_path), envs=envs)
    assert ln["status"] == "cant_check" and "shape" in ln["message"], ln


def test_a_null_state_is_no_state(tmp_path):
    envs = _envs("t", "c")
    envs["environments"][1]["state"] = None
    assert _environments_line(tmp_path, _project(tmp_path), envs=envs)["status"] == "fine"


def test_one_run_listed_twice_is_worded_as_one(tmp_path):
    ln = _environments_line(tmp_path, _project(tmp_path), *_runs_file(tmp_path, [[RUN_ISSUE], [RUN_ISSUE]]), envs=_envs(), path=_no_gh(tmp_path), env=DEV)
    assert "An issue labelled workflow:run exists (#185)" in ln["message"], ln


def test_a_run_beside_an_entry_that_isnt_an_issue_still_counts(tmp_path):
    runs = [[RUN_ISSUE], {"message": "Bad credentials"}]
    ln = _environments_line(tmp_path, _project(tmp_path), *_runs_file(tmp_path, runs), envs=_envs(), path=_no_gh(tmp_path))
    assert ln["status"] == "gap" and "#185" in ln["message"], ln


def test_entries_that_happen_to_have_an_environments_key_arent_pages(tmp_path):
    entries = [{"name": "t", "environments": []}, {"name": "c", "environments": []}]
    ln = _environments_line(tmp_path, _project(tmp_path), *_env_file(tmp_path, json.dumps(entries)), envs=None)
    assert ln["status"] == "fine", ln


def test_two_long_names_alike_in_their_ends_are_both_named_in_the_note(tmp_path):
    # They differ only where a long name is cut, so both are shown alike.
    a, b = "a" * 40 + "x" * 10 + "z" * 40, "a" * 40 + "y" * 10 + "z" * 40
    profile = NAMED.replace("workflow-ticket", a).replace("workflow-conductor", b)
    ln = _cloud(tmp_path, _project(tmp_path, profile=profile), envs=None, env=DEV)["cloud.contents"]
    assert ln["fix"].count("`") == 4, ln  # each named once in the fix


@pytest.mark.parametrize("labels", [{"nodes": [{"name": "workflow:run"}]}, "workflow:run"])
def test_labels_that_arent_a_list_cant_be_read(tmp_path, labels):
    runs = [{"number": 51, "labels": labels}]
    ln = _environments_line(tmp_path, _project(tmp_path), *_runs_file(tmp_path, runs), envs=_envs(), path=_no_gh(tmp_path), env=DEV)
    assert ln["status"] == "note" and "an entry isn't an issue" in ln["message"], ln


def test_one_missing_has_a_fix_for_one(tmp_path):
    ln = _environments_line(tmp_path, _project(tmp_path), envs=_envs("t"), env=DEV)
    assert "guides it" in ln["fix"] and "guides both" not in ln["fix"], ln


def test_an_incomplete_list_names_an_inactive_one_as_already_missing(tmp_path):
    envs = _envs("t", has_more=True)
    envs["environments"][0]["state"] = "archived"
    root = _project(tmp_path)
    new = _environments_line(tmp_path, root, envs=envs, env=NEW)
    dev = _environments_line(tmp_path, root, envs=envs, env=DEV)
    for ln in (new, dev):
        assert ln["status"] == "cant_check" and "not active" in ln["message"] and "`c`" in ln["message"], ln
    assert "for the missing one" in new["fix"] and "Fix the other first" in dev["fix"], (new, dev)
