"""`workflow protection`'s request builder (#66, seam 1 of #38): the requests
to protect the base branch, to require checks, and the checks that ran.

Driven through the command, fed recorded JSON files, as the read-back is
(tests/test_protection.py). The shapes are GitHub's (POST/PUT
repos/<repo>/rulesets, GET repos/<repo>, GET .../commits/<ref>/check-runs and
.../statuses), made up. The command builds and prints; it sends nothing.
"""

import copy
import json
import os
import subprocess
import sys

import pytest

from conftest import git
from test_hooks_cli import CLI

SETTINGS = {"full_name": "acme/demo", "default_branch": "main", "allow_merge_commit": False, "allow_auto_merge": False}

PR_PARAMS = {
    "required_approving_review_count": 0,
    "dismiss_stale_reviews_on_push": False,
    "require_code_owner_review": False,
    "require_last_push_approval": False,
    "required_review_thread_resolution": False,
}


@pytest.fixture
def inp(tmp_path_factory):
    """Where the JSON files go: outside the project, so a run's tree is only its own."""
    return tmp_path_factory.mktemp("input")


def cli(repo, *args, stdin=None):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo)}
    return subprocess.run([sys.executable, str(CLI), "protection", *args], cwd=repo, env=env, capture_output=True, text=True, input=stdin)


def put(inp, name, data):
    path = inp / name
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    return str(path)


def ok(p):
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def bad(p, *words):
    assert p.returncode == 2, (p.stdout, p.stderr)
    assert p.stdout == "" and "Traceback" not in p.stderr
    assert p.stderr.startswith("workflow protection: ")
    for w in words:
        assert w in p.stderr, p.stderr


def checks(*names):
    return [f"--check={n}" for n in names]


# ---------- protect ----------


def protect(repo, inp, *extra, settings=SETTINGS):
    return cli(repo, "--protect", "--repo", put(inp, "repo.json", settings), *extra)


def _expected_ruleset(include, names=()):
    rules = [{"type": "deletion"}, {"type": "non_fast_forward"}, {"type": "pull_request", "parameters": PR_PARAMS}]
    if names:
        rules.append({
            "type": "required_status_checks",
            "parameters": {"strict_required_status_checks_policy": True, "required_status_checks": [{"context": n} for n in names]},
        })
    return {
        "name": "Protect main (pairnexus-workflow)",
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": [include], "exclude": []}},
        "rules": rules,
    }


MERGE_REQUEST = {"method": "PATCH", "path": "repos/acme/demo", "body": {"allow_merge_commit": True, "allow_auto_merge": True}}


def test_protect_the_default_branch_targets_default_branch(repo, inp):
    out = ok(protect(repo, inp, "--json"))
    assert [(r["method"], r["path"]) for r in out["requests"]] == [("POST", "repos/acme/demo/rulesets"), ("PATCH", "repos/acme/demo")]
    assert out["requests"][0]["body"] == _expected_ruleset("~DEFAULT_BRANCH")
    assert {k: out["requests"][1][k] for k in ("method", "path", "body")} == MERGE_REQUEST


def test_protect_another_branch_names_it(repo, inp):
    out = ok(protect(repo, inp, "--base", "release", "--json"))
    body = out["requests"][0]["body"]
    want = _expected_ruleset("refs/heads/release")
    want["name"] = "Protect release (pairnexus-workflow)"
    assert body == want
    assert {k: out["requests"][1][k] for k in ("method", "path", "body")} == MERGE_REQUEST


def test_protect_takes_the_base_branch_from_the_profile(repo, inp):
    prof = repo / ".claude/workflow/profile.toml"
    prof.write_text(prof.read_text().replace('repo = "acme/demo"', 'repo = "acme/demo"\nbase_branch = "trunk"'))
    body = ok(protect(repo, inp, "--json"))["requests"][0]["body"]
    assert body["conditions"]["ref_name"]["include"] == ["refs/heads/trunk"]
    assert body["name"] == "Protect trunk (pairnexus-workflow)"


@pytest.mark.parametrize("base,include", [("main", "~DEFAULT_BRANCH"), ("release", "refs/heads/release")])
def test_protect_with_ticked_names_requires_them_up_to_date(repo, inp, base, include):
    out = ok(protect(repo, inp, "--base", base, *checks("tests (3.11)", "lint"), "--json"))
    body = out["requests"][0]["body"]
    want = _expected_ruleset(include, ["tests (3.11)", "lint"])
    want["name"] = f"Protect {base} (pairnexus-workflow)"
    assert body == want
    assert {k: out["requests"][1][k] for k in ("method", "path", "body")} == MERGE_REQUEST


def test_protect_without_names_has_no_checks_rule_and_no_linear_history(repo, inp):
    body = ok(protect(repo, inp, "--json"))["requests"][0]["body"]
    types = [r["type"] for r in body["rules"]]
    assert "required_status_checks" not in types and "required_linear_history" not in types


def test_protect_a_name_ticked_twice_is_required_once(repo, inp):
    body = ok(protect(repo, inp, *checks("tests", "tests"), "--json"))["requests"][0]["body"]
    assert body["rules"][-1]["parameters"]["required_status_checks"] == [{"context": "tests"}]


def test_protect_text_shows_each_request_and_says_nothing_was_sent(repo, inp):
    p = protect(repo, inp, "--check", "tests")
    assert p.returncode == 0, p.stderr
    assert "POST repos/acme/demo/rulesets" in p.stdout and "PATCH repos/acme/demo" in p.stdout
    assert "not sent" in p.stdout.lower()
    assert '"Protect main (pairnexus-workflow)"' in p.stdout and '"tests"' in p.stdout


def test_protect_needs_the_repository_settings(repo, inp):
    bad(cli(repo, "--protect"), "--repo")
    bad(protect(repo, inp, settings={"full_name": "acme/demo"}), "default_branch")
    bad(protect(repo, inp, settings={"default_branch": "main"}), "full_name")
    bad(protect(repo, inp, settings={"full_name": "acme/demo/x", "default_branch": "main"}), "full_name")
    bad(protect(repo, inp, settings=[]), "JSON object")
    bad(protect(repo, inp, settings="{not json"), "isn't JSON")


@pytest.mark.parametrize("name", ["", "  ", "a\nb", "tab\there"])
def test_a_bad_check_name_is_an_error(repo, inp, name):
    bad(protect(repo, inp, "--check", name), "check name")


def test_protect_refuses_a_bad_base(repo, inp):
    bad(protect(repo, inp, "--base", "ma in"), "branch name")


# ---------- the built rulesets read back as protected (#44) ----------


def readback(repo, inp, rulesets, base="main"):
    return ok(cli(repo, "--rulesets", put(inp, "rs.json", rulesets), "--repo", put(inp, "settings.json", SETTINGS), "--base", base, "--json"))


@pytest.mark.parametrize("base", ["main", "release"])
@pytest.mark.parametrize("names", [(), ("tests", "lint")])
def test_the_protect_ruleset_reads_back_as_protected(repo, inp, base, names):
    body = ok(protect(repo, inp, "--base", base, *checks(*names), "--json"))["requests"][0]["body"]
    out = readback(repo, inp, [body], base)
    assert out["protected"] is True and out["missing"] == []
    assert out["checks"]["required"] == list(names)
    assert (out["checks"]["note"] == "checks not required yet") == (not names)


def test_require_checks_applied_to_the_protect_ruleset_reads_back_with_checks(repo, inp):
    body = ok(protect(repo, inp, "--json"))["requests"][0]["body"]
    current = {"id": 7, "source_type": "Repository", "source": "acme/demo", **body}
    put_body = ok(require(repo, inp, current, "tests"))["requests"][0]["body"]
    out = readback(repo, inp, [put_body])
    assert out["protected"] is True and out["checks"]["required"] == ["tests"] and out["checks"]["note"] is None


# ---------- require checks ----------


def recorded_ruleset():
    """A ruleset as GET repos/<repo>/rulesets/<id> returns it, read-only fields and all."""
    return {
        "id": 42,
        "name": "Main rules",
        "target": "branch",
        "source_type": "Repository",
        "source": "acme/demo",
        "enforcement": "active",
        "node_id": "RRS_lACqUmVwb3NpdG9yec4",
        "created_at": "2026-09-01T10:00:00.000Z",
        "updated_at": "2026-09-02T10:00:00.000Z",
        "current_user_can_bypass": "never",
        "_links": {"self": {"href": "https://api.github.com/repos/acme/demo/rulesets/42"}, "html": {"href": "https://github.com/acme/demo/rules/42"}},
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH", "refs/heads/release"], "exclude": ["refs/heads/old"]}},
        "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}],
        "rules": [
            {"type": "deletion"},
            {"type": "required_signatures"},
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": False,
                    "do_not_enforce_on_create": True,
                    "required_status_checks": [{"context": "build", "integration_id": 15368}, {"context": "lint"}],
                },
            },
            {"type": "pull_request", "parameters": {**PR_PARAMS, "required_approving_review_count": 1}},
        ],
    }


READ_ONLY = ("id", "source", "source_type", "node_id", "created_at", "updated_at", "current_user_can_bypass", "_links")


def require(repo, inp, ruleset, *names, raw=None):
    return cli(repo, "--require-checks", put(inp, "ruleset.json", raw if raw is not None else ruleset), *checks(*names), "--json")


def test_require_checks_extends_and_leaves_everything_else(repo, inp):
    rs = recorded_ruleset()
    out = ok(require(repo, inp, rs, "tests (3.11)", "lint", "tests (3.12)"))
    [req] = out["requests"]
    assert req["method"] == "PUT" and req["path"] == "repos/acme/demo/rulesets/42"
    body = req["body"]
    assert not set(READ_ONLY) & set(body)
    assert set(body) == {"name", "target", "enforcement", "conditions", "bypass_actors", "rules"}
    for k in ("name", "target", "enforcement", "conditions", "bypass_actors"):
        assert body[k] == rs[k]
    want_rules = copy.deepcopy(rs["rules"])
    want_rules[2]["parameters"]["strict_required_status_checks_policy"] = True
    want_rules[2]["parameters"]["required_status_checks"] += [{"context": "tests (3.11)"}, {"context": "tests (3.12)"}]
    assert body["rules"] == want_rules


def test_require_checks_adds_a_checks_rule_when_there_is_none(repo, inp):
    rs = recorded_ruleset()
    rs["rules"] = [r for r in rs["rules"] if r["type"] != "required_status_checks"]
    body = ok(require(repo, inp, rs, "tests"))["requests"][0]["body"]
    assert body["rules"][:-1] == rs["rules"]
    assert body["rules"][-1] == {
        "type": "required_status_checks",
        "parameters": {"strict_required_status_checks_policy": True, "required_status_checks": [{"context": "tests"}]},
    }


def test_require_checks_already_required_names_change_only_up_to_date(repo, inp):
    rs = recorded_ruleset()
    body = ok(require(repo, inp, rs, "build"))["requests"][0]["body"]
    assert body["rules"][2]["parameters"]["required_status_checks"] == rs["rules"][2]["parameters"]["required_status_checks"]
    assert body["rules"][2]["parameters"]["strict_required_status_checks_policy"] is True


def test_require_checks_without_a_bypass_list_sends_none(repo, inp):
    rs = recorded_ruleset()
    del rs["bypass_actors"]  # not an admin: GitHub leaves it out, and an update without it keeps it
    body = ok(require(repo, inp, rs, "tests"))["requests"][0]["body"]
    assert "bypass_actors" not in body


def test_require_checks_text_shows_the_request(repo, inp):
    p = cli(repo, "--require-checks", put(inp, "ruleset.json", recorded_ruleset()), "--check", "tests")
    assert p.returncode == 0, p.stderr
    assert "PUT repos/acme/demo/rulesets/42" in p.stdout and "not sent" in p.stdout.lower()


def test_require_checks_needs_names(repo, inp):
    bad(require(repo, inp, recorded_ruleset()), "--check")


@pytest.mark.parametrize(
    "change,words",
    [
        (lambda rs: rs.pop("rules"), "in full"),
        (lambda rs: rs.pop("id"), "id"),
        (lambda rs: rs.update(id="42"), "id"),
        (lambda rs: rs.update(id=True), "id"),
        (lambda rs: rs.update(source_type="Organization", source="acme"), "organisation"),
        (lambda rs: rs.pop("source"), "source"),
        (lambda rs: rs.update(source="acme/demo/x"), "source"),
        (lambda rs: rs["rules"][2].update(parameters={"required_status_checks": "build"}), "required_status_checks"),
        (lambda rs: rs.update(enforcement=None), "enforcement"),
    ],
)
def test_require_checks_refuses_a_ruleset_that_isnt_whole(repo, inp, change, words):
    rs = recorded_ruleset()
    change(rs)
    bad(require(repo, inp, rs, "tests"), words)


@pytest.mark.parametrize("raw", ["[]", "{nope", '"ruleset"', json.dumps([recorded_ruleset()])])
def test_require_checks_refuses_what_isnt_one_ruleset(repo, inp, raw):
    bad(require(repo, inp, None, "tests", raw=raw))


# ---------- the checks that ran ----------


def run_(name, conclusion="success", status="completed", app="github-actions", started="2026-10-01T10:00:00Z", id=1):
    return {
        "id": id,
        "name": name,
        "status": status,
        "conclusion": conclusion if status == "completed" else None,
        "started_at": started,
        "completed_at": started if status == "completed" else None,
        "app": {"id": 9, "slug": app, "name": app},
    }


def status_(context, state="success", at="2026-10-01T10:00:00Z", id=1):
    return {"id": id, "context": context, "state": state, "created_at": at, "updated_at": at}


def ran(repo, inp, runs, statuses=None, rulesets=(), *extra):
    args = ["--checks-ran", put(inp, "runs.json", runs if not isinstance(runs, list) else {"total_count": len(runs), "check_runs": runs})]
    if statuses is not None:
        args += ["--statuses", put(inp, "statuses.json", statuses)]
    args += ["--rulesets", put(inp, "rulesets.json", list(rulesets)), "--repo", put(inp, "repo.json", SETTINGS)]
    return cli(repo, *args, *extra)


def _required(*names):
    return {
        "id": 1, "name": "r", "target": "branch", "enforcement": "active", "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [{"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": True, "required_status_checks": [{"context": n} for n in names]}}],
    }


def test_checks_that_ran_with_their_results(repo, inp):
    runs = [run_("tests (3.11)"), run_("lint", "failure", id=2), run_("e2e", status="in_progress", id=3), run_("docs", "skipped", id=4)]
    statuses = [status_("ci/circleci", "pending"), status_("deploy/preview", "error", id=2)]
    out = ok(ran(repo, inp, runs, statuses, (), "--json"))
    assert out["checks"] == [
        {"name": "ci/circleci", "result": "pending"},
        {"name": "deploy/preview", "result": "failing"},
        {"name": "docs", "result": "passing"},
        {"name": "e2e", "result": "pending"},
        {"name": "lint", "result": "failing"},
        {"name": "tests (3.11)", "result": "passing"},
    ]


def test_checks_already_required_are_left_out(repo, inp):
    out = ok(ran(repo, inp, [run_("tests"), run_("lint", id=2)], None, [_required("tests")], "--json"))
    assert out["checks"] == [{"name": "lint", "result": "passing"}]
    assert out["required"] == ["tests"]


def test_a_name_reported_twice_appears_once_with_its_latest_result(repo, inp):
    runs = [
        run_("tests", "failure", started="2026-10-01T10:00:00Z", id=1),
        run_("tests", "success", started="2026-10-01T11:00:00Z", id=2),  # a re-run
        run_("lint", "success", started="2026-10-01T12:00:00Z", id=3),
    ]
    statuses = [status_("lint", "failure", at="2026-10-01T13:00:00Z")]  # a status of the same name, later
    out = ok(ran(repo, inp, list(reversed(runs)), statuses, (), "--json"))
    assert out["checks"] == [{"name": "lint", "result": "failing"}, {"name": "tests", "result": "passing"}]


def test_statuses_newest_first_as_github_lists_them(repo, inp):
    statuses = [status_("ci", "success", at="2026-10-01T11:00:00Z", id=2), status_("ci", "pending", at="2026-10-01T10:00:00Z", id=1)]
    assert ok(ran(repo, inp, [], statuses, (), "--json"))["checks"] == [{"name": "ci", "result": "passing"}]


def test_a_combined_status_and_slurped_pages_are_read(repo, inp):
    pages = [{"total_count": 2, "check_runs": [run_("a")]}, {"total_count": 2, "check_runs": [run_("b", id=2)]}]
    combined = {"state": "success", "statuses": [status_("c")]}
    out = ok(ran(repo, inp, json.dumps(pages), combined, (), "--json"))
    assert [c["name"] for c in out["checks"]] == ["a", "b", "c"]
    out = ok(ran(repo, inp, [], [[status_("c")], [status_("d", id=2)]], (), "--json"))
    assert [c["name"] for c in out["checks"]] == ["c", "d"]


def test_a_commit_with_none_is_an_empty_list(repo, inp):
    out = ok(ran(repo, inp, [], [], (), "--json"))
    assert out["checks"] == []
    p = ran(repo, inp, [], None, ())
    assert p.returncode == 0 and p.stderr == "" and "no checks" in p.stdout.lower()


@pytest.mark.parametrize("conclusion", ["success", "failure"])
def test_the_cloudflare_check_is_never_offered(repo, inp, conclusion):
    runs = [run_("Workers Builds: notes-app", conclusion, app="cloudflare-workers-and-pages"), run_("tests", id=2)]
    out = ok(ran(repo, inp, runs, None, (), "--json"))
    assert out["checks"] == [{"name": "tests", "result": "passing"}]


def test_a_similar_name_from_another_app_is_listed(repo, inp):
    runs = [run_("Workers Builds: notes-app", app="some-other-ci")]
    assert ok(ran(repo, inp, runs, None, (), "--json"))["checks"] == [{"name": "Workers Builds: notes-app", "result": "passing"}]


def test_checks_that_ran_text(repo, inp):
    p = ran(repo, inp, [run_("tests"), run_("lint", "failure", id=2)], None, [_required("build")])
    assert p.returncode == 0, p.stderr
    assert '"tests": passing' in p.stdout and '"lint": failing' in p.stdout and '"build"' in p.stdout


@pytest.mark.parametrize(
    "runs",
    [
        "[1, 2]",
        json.dumps({"total_count": 1}),
        json.dumps({"check_runs": [{"status": "completed", "conclusion": "success"}]}),
        json.dumps({"check_runs": [{**run_("a"), "status": 3}]}),
        json.dumps({"check_runs": [{**run_("a"), "conclusion": None}]}),
        json.dumps({"check_runs": [{**run_("a"), "started_at": "yesterday"}]}),
        json.dumps({"check_runs": [{**run_("a"), "app": "github-actions"}]}),
        "{not json",
    ],
)
def test_malformed_check_runs_are_an_error(repo, inp, runs):
    bad(ran(repo, inp, runs, None, ()), "check runs")


@pytest.mark.parametrize(
    "statuses",
    [
        {"state": "success"},
        [{"state": "success"}],
        [{**status_("a"), "state": "great"}],
        [{**status_("a"), "created_at": 5}],
        "x",
    ],
)
def test_malformed_statuses_are_an_error(repo, inp, statuses):
    bad(ran(repo, inp, [], statuses, ()), "statuses")


def test_checks_ran_needs_the_rulesets(repo, inp):
    p = cli(repo, "--checks-ran", put(inp, "runs.json", {"check_runs": []}), "--repo", put(inp, "repo.json", SETTINGS))
    bad(p, "--rulesets")


def test_checks_ran_needs_the_settings(repo, inp):
    """Without them a ruleset on ~DEFAULT_BRANCH can't be counted, and its checks would be offered again."""
    p = cli(repo, "--checks-ran", put(inp, "runs.json", {"check_runs": [run_("tests")]}), "--rulesets", put(inp, "rs.json", [_required("tests")]), "--base", "main")
    bad(p, "--repo")


def test_checks_ran_refuses_a_ruleset_that_isnt_whole(repo, inp):
    bad(ran(repo, inp, [], None, [{"id": 1, "name": "summary only"}]), "in full")


# ---------- the options go together ----------


def test_the_modes_dont_mix(repo, inp):
    rs = put(inp, "rs.json", [])
    p = cli(repo, "--protect", "--require-checks", rs)
    assert p.returncode == 2
    bad(cli(repo, "--rulesets", rs, "--base", "main", "--check", "tests"), "--check")
    bad(cli(repo, "--rulesets", rs, "--base", "main", "--statuses", rs), "--statuses")
    bad(cli(repo, "--require-checks", rs, "--check", "a", "--rulesets", rs), "--rulesets")
    bad(cli(repo, "--require-checks", "-", "--check", "a", "--repo", "-"), "standard input")


def test_the_read_back_still_needs_its_rulesets(repo, inp):
    bad(cli(repo, "--base", "main"), "--rulesets")


def test_set_up_s_read_back_call_still_works(repo, inp):
    """#48: set-up runs `protection --rulesets … --repo … --base <base> --json`, with no profile."""
    (repo / ".claude/workflow/profile.toml").unlink()
    out = ok(cli(repo, "--rulesets", put(inp, "rs.json", []), "--repo", put(inp, "repo.json", SETTINGS), "--base", "main", "--json"))
    assert out["protected"] is False


# ---------- it writes nothing ----------


def test_it_writes_nothing(repo, inp):
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "start", "--allow-empty")
    before = git(repo, "status", "--porcelain", "--ignored")
    ok(protect(repo, inp, *checks("tests"), "--json"))
    ok(require(repo, inp, recorded_ruleset(), "tests"))
    ok(ran(repo, inp, [run_("tests")], [status_("ci")], (), "--json"))
    assert git(repo, "status", "--porcelain", "--ignored") == before
    assert sorted(p.name for p in inp.iterdir()) == sorted(["repo.json", "rulesets.json", "ruleset.json", "runs.json", "statuses.json"])


# ---------- review round 1 ----------


def test_a_status_state_that_isnt_text_is_an_error(repo, inp):
    bad(ran(repo, inp, [], [{"context": "ci", "state": []}], ()), "statuses")


def test_require_checks_refuses_a_required_check_without_a_context(repo, inp):
    for entry in ({"context": ["x"]}, {"context": 5}, {"integration_id": 1}):
        rs = recorded_ruleset()
        rs["rules"][2]["parameters"]["required_status_checks"] = [entry]
        bad(require(repo, inp, rs, "tests"), "context")


@pytest.mark.parametrize(
    "change,words",
    [
        (lambda rs: rs.update(name=5), "name"),
        (lambda rs: rs.update(target="push"), "branch ruleset"),
    ],
)
def test_require_checks_refuses_other_odd_rulesets(repo, inp, change, words):
    rs = recorded_ruleset()
    change(rs)
    bad(require(repo, inp, rs, "tests"), words)


def test_odd_characters_in_a_recorded_ruleset_are_escaped_in_the_text(repo, inp):
    rs = recorded_ruleset()
    rs["name"] = "bad\ud800 name\u2028line\x85"
    p = cli(repo, "--require-checks", put(inp, "ruleset.json", json.dumps(rs)), "--check", "tests")
    assert p.returncode == 0, p.stderr
    assert "\\ud800" in p.stdout and "\\u2028" in p.stdout and "\\u0085" in p.stdout
    assert "\u2028" not in p.stdout and "\x85" not in p.stdout


@pytest.mark.parametrize("raw", ['{"a": NaN}', '{"a": Infinity}', '{"a": -Infinity}'])
def test_nan_and_infinity_are_not_json(repo, inp, raw):
    rs = json.dumps(recorded_ruleset())[:-1] + ', "x": ' + raw[6:-1] + "}"
    bad(require(repo, inp, None, "tests", raw=rs), "isn't JSON")


def test_check_names_say_what_is_wrong_once(repo, inp):
    p = protect(repo, inp, "--check", "a\nb")
    bad(p, 'the check name "a\\nb" isn')
    bad(protect(repo, inp, "--check", " lint "), "spaces at either end")


def test_a_check_name_with_an_emoji_sequence_is_a_check_name(repo, inp):
    name = "\U0001F468\u200d\U0001F469 build"
    body = ok(protect(repo, inp, "--check", name, "--json"))["requests"][0]["body"]
    assert body["rules"][-1]["parameters"]["required_status_checks"] == [{"context": name}]


def test_a_check_name_that_isnt_text_is_refused(repo, inp):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo)}
    p = subprocess.run([sys.executable.encode(), str(CLI).encode(), b"protection", b"--protect", b"--repo", put(inp, "repo.json", SETTINGS).encode(), b"--check", b"ab\xff"], cwd=repo, env=env, capture_output=True, text=True)
    bad(p, "check name")


@pytest.mark.parametrize("full_name", ["../..", "acme/..", "./demo"])
def test_a_repository_name_that_climbs_out_is_refused(repo, inp, full_name):
    bad(protect(repo, inp, settings={**SETTINGS, "full_name": full_name}), "full_name")
    rs = recorded_ruleset()
    rs["source"] = full_name
    bad(require(repo, inp, rs, "tests"), "source")


@pytest.mark.parametrize(
    "settings,words",
    [
        ({**SETTINGS, "allow_merge_commit": "yes"}, "allow_merge_commit"),
        ({**SETTINGS, "default_branch": "ma in"}, "default_branch"),
        ({**SETTINGS, "default_branch": 5}, "default_branch"),
    ],
)
def test_protect_refuses_odd_settings(repo, inp, settings, words):
    bad(protect(repo, inp, settings=settings), words)


def test_one_page_of_many_is_not_the_whole_list(repo, inp):
    page = {"total_count": 45, "check_runs": [run_(f"c{i}", id=i) for i in range(30)]}
    bad(ran(repo, inp, json.dumps(page), None, ()), "30 of the commit's 45")
    rest = {"total_count": 45, "check_runs": [run_(f"c{i}", id=i) for i in range(30, 45)]}
    assert len(ok(ran(repo, inp, json.dumps([page, rest]), None, (), "--json"))["checks"]) == 45
    combined = {"state": "pending", "total_count": 3, "statuses": [status_("a")]}
    bad(ran(repo, inp, [], combined, ()), "1 of the commit's 3")


def test_a_report_with_no_time_counts_as_the_oldest(repo, inp):
    runs = [run_("tests", "failure", started=None, id=9), run_("tests", "success", id=1)]
    assert ok(ran(repo, inp, runs, None, (), "--json"))["checks"] == [{"name": "tests", "result": "passing"}]


def test_a_check_run_counts_from_when_it_finished(repo, inp):
    run = run_("tests", "failure", started="2026-10-01T10:00:00Z")
    run["completed_at"] = "2026-10-01T10:30:00Z"
    statuses = [status_("tests", "success", at="2026-10-01T10:15:00Z")]
    assert ok(ran(repo, inp, [run], statuses, (), "--json"))["checks"] == [{"name": "tests", "result": "failing"}]


# ---------- review round 2 ----------


@pytest.mark.parametrize("app", ["drop", None])
def test_a_check_run_without_its_app_is_an_error_so_the_cloudflare_check_cant_slip_through(repo, inp, app):
    r = run_("Workers Builds: notes-app")
    if app == "drop":
        del r["app"]
    else:
        r["app"] = None
    bad(ran(repo, inp, [r], None, ()), "app")


def test_a_number_too_large_for_a_float_is_not_json(repo, inp):
    rs = json.dumps(recorded_ruleset()).replace('"required_approving_review_count": 1', '"required_approving_review_count": 1e400')
    assert "1e400" in rs
    bad(require(repo, inp, None, "tests", raw=rs), "isn't JSON")


def test_pages_of_the_combined_status_are_read_and_must_be_whole(repo, inp):
    pages = [{"state": "success", "total_count": 2, "statuses": [status_("a")]}, {"state": "success", "total_count": 2, "statuses": [status_("b", id=2)]}]
    assert [c["name"] for c in ok(ran(repo, inp, [], pages, (), "--json"))["checks"]] == ["a", "b"]
    bad(ran(repo, inp, [], pages[:1], ()), "1 of the commit's 2")


@pytest.mark.parametrize("total", [True, "5", -1, 1.5])
def test_a_total_count_that_isnt_a_count_is_an_error(repo, inp, total):
    bad(ran(repo, inp, json.dumps({"total_count": total, "check_runs": [run_("a")]}), None, ()), "total_count")


def test_names_check_would_refuse_are_never_offered(repo, inp):
    runs = [run_("", id=1), run_("a\tb", id=2), run_("lint ", id=3), run_("lint", id=4)]
    assert ok(ran(repo, inp, runs, None, (), "--json"))["checks"] == [{"name": "lint", "result": "passing"}]


def test_at_the_same_time_the_higher_id_wins(repo, inp):
    statuses = [status_("ci", "success", id=8), status_("ci", "pending", id=7)]
    assert ok(ran(repo, inp, [], statuses, (), "--json"))["checks"] == [{"name": "ci", "result": "passing"}]
    statuses = [status_("ci", "pending", id=8), status_("ci", "success", id=7)]
    assert ok(ran(repo, inp, [], statuses, (), "--json"))["checks"] == [{"name": "ci", "result": "pending"}]


@pytest.mark.parametrize("params", [{}, {"strict_required_status_checks_policy": False}, None])
def test_require_checks_fills_a_checks_rule_with_no_list(repo, inp, params):
    rs = recorded_ruleset()
    rs["rules"][2] = {"type": "required_status_checks", "parameters": params}
    body = ok(require(repo, inp, rs, "tests"))["requests"][0]["body"]
    assert body["rules"][2] == {
        "type": "required_status_checks",
        "parameters": {"strict_required_status_checks_policy": True, "required_status_checks": [{"context": "tests"}]},
    }
