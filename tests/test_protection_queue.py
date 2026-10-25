"""`workflow protection --merge-queue`: the ruleset writer's merge-queue rule
(#247, seam 2 of #243), and "Require these checks" leaving "up to date" alone
once the rule is there.

Driven through the command, fed recorded JSON files, as the other request
builders are (tests/test_protection_requests.py). The doctor file is the shape
`workflow doctor --json` gives (#246): its `merge_queue.merge_group` verdict
and `merge_queue.signals.ci_minutes.longest`. The command builds and prints;
it sends nothing.
"""

import copy
import json

import pytest

from test_protection_requests import READ_ONLY, bad, checks, cli, inp, ok, put, recorded_ruleset  # noqa: F401 (inp is a fixture)

SETTINGS = {
    "merge_method": "MERGE",
    "grouping_strategy": "ALLGREEN",
    "max_entries_to_build": 5,
    "max_entries_to_merge": 5,
    "min_entries_to_merge": 1,
    "min_entries_to_merge_wait_minutes": 0,
}


def doctor(clean=True, longest=None, status=None, workflows=None):
    """`workflow doctor --json`, cut to what the writer reads."""
    flows = workflows if workflows is not None else [{"path": ".github/workflows/ci.yml", "state": "ready" if clean else "missing", "why": None}]
    return {
        "lines": [],
        "merge_queue": {
            "queue": False,
            "available": "yes",
            "merge_group": {"status": status or ("fine" if clean else "note"), "clean": clean, "workflows": flows, "checks": []},
            "signals": {"ci_minutes": {"longest": longest, "typical": longest, "commits": 3 if longest is not None else 0}},
        },
    }


def queue(repo, inp, ruleset, report, *extra, raw=None):
    rs = put(inp, "ruleset.json", raw if raw is not None else ruleset)
    return cli(repo, "--merge-queue", rs, "--doctor", put(inp, "doctor.json", report), *extra, "--json")


def body_of(p):
    [req] = ok(p)["requests"]
    return req


def queue_rule(body):
    [rule] = [r for r in body["rules"] if r["type"] == "merge_queue"]
    return rule["parameters"]


def checks_params(body):
    [rule] = [r for r in body["rules"] if r["type"] == "required_status_checks"]
    return rule["parameters"]


# ---------- the body ----------


def test_the_body_has_the_queue_rule_with_each_setting_up_to_date_off_and_the_checks_kept(repo, inp):
    rs = recorded_ruleset()
    rs["rules"][2]["parameters"]["strict_required_status_checks_policy"] = True
    req = body_of(queue(repo, inp, rs, doctor(longest=25)))
    assert req["method"] == "PUT" and req["path"] == "repos/acme/demo/rulesets/42"
    body = req["body"]
    assert not set(READ_ONLY) & set(body)
    assert queue_rule(body) == {**SETTINGS, "check_response_timeout_minutes": 60}
    params = checks_params(body)
    assert params["strict_required_status_checks_policy"] is False
    assert params["required_status_checks"] == rs["rules"][2]["parameters"]["required_status_checks"]
    assert params["do_not_enforce_on_create"] is True
    # Everything else is the ruleset as it was, the queue rule added last.
    want = copy.deepcopy(rs["rules"])
    want[2]["parameters"]["strict_required_status_checks_policy"] = False
    assert body["rules"][:-1] == want and body["rules"][-1]["type"] == "merge_queue"
    for k in ("name", "target", "enforcement", "conditions", "bypass_actors"):
        assert body[k] == rs[k]


@pytest.mark.parametrize(
    "longest,minutes",
    [
        (None, 60),  # no history: GitHub's default
        (0, 60),
        (10, 60),  # never below the no-history default
        (30, 60),
        (31, 62),  # twice the longest run: room to spare
        (45, 90),
        (179, 358),
        (180, 360),
        (181, 360),  # GitHub's cap
        (900, 360),
    ],
)
def test_the_timeout_is_above_the_longest_run_with_room_to_spare_and_capped_at_360(repo, inp, longest, minutes):
    body = body_of(queue(repo, inp, recorded_ruleset(), doctor(longest=longest)))["body"]
    assert queue_rule(body)["check_response_timeout_minutes"] == minutes


@pytest.mark.parametrize("given", ["1", "45", "360"])
def test_the_owner_s_timeout_wins(repo, inp, given):
    body = body_of(queue(repo, inp, recorded_ruleset(), doctor(longest=200), "--timeout", given))["body"]
    assert queue_rule(body)["check_response_timeout_minutes"] == int(given)


@pytest.mark.parametrize("given", ["0", "361", "-5", "1.5", "an hour", ""])
def test_a_timeout_outside_github_s_range_is_refused(repo, inp, given):
    bad(queue(repo, inp, recorded_ruleset(), doctor(), "--timeout", given), "timeout")


def test_a_queue_rule_already_there_is_replaced_not_doubled(repo, inp):
    rs = recorded_ruleset()
    rs["rules"].insert(1, {"type": "merge_queue", "parameters": {**SETTINGS, "merge_method": "SQUASH", "check_response_timeout_minutes": 15}})
    body = body_of(queue(repo, inp, rs, doctor(longest=40)))["body"]
    assert [r["type"] for r in body["rules"]] == [r["type"] for r in rs["rules"]]
    assert queue_rule(body) == {**SETTINGS, "check_response_timeout_minutes": 80}


def test_the_text_shows_the_settings_and_says_nothing_was_sent(repo, inp):
    p = cli(repo, "--merge-queue", put(inp, "ruleset.json", recorded_ruleset()), "--doctor", put(inp, "doctor.json", doctor()))
    assert p.returncode == 0, p.stderr
    assert "PUT repos/acme/demo/rulesets/42" in p.stdout and "not sent" in p.stdout.lower()
    assert '"check_response_timeout_minutes": 60' in p.stdout and '"strict_required_status_checks_policy": false' in p.stdout


def test_the_input_is_not_changed(repo, inp):
    rs = recorded_ruleset()
    path = put(inp, "ruleset.json", rs)
    before = open(path).read()
    p = cli(repo, "--merge-queue", path, "--doctor", put(inp, "doctor.json", doctor()), "--json")
    assert p.returncode == 0, p.stderr
    assert open(path).read() == before


# ---------- refused without a clean merge_group verdict ----------


@pytest.mark.parametrize(
    "report,words",
    [
        (doctor(clean=False), "merge_group"),
        (doctor(clean=False, status="gap"), "merge_group"),
        (doctor(clean=False, status="cant_check", workflows=[]), "merge_group"),
        ({**doctor(), "merge_queue": {**doctor()["merge_queue"], "merge_group": None}}, "merge_group"),
        ({**doctor(), "merge_queue": None}, "merge_queue"),
        ({"lines": []}, "merge_queue"),
        ({**doctor(), "merge_queue": {**doctor()["merge_queue"], "merge_group": {**doctor()["merge_queue"]["merge_group"], "clean": "yes"}}}, "merge_group"),
        ([], "doctor"),
    ],
)
def test_it_is_refused_without_a_clean_merge_group_verdict(repo, inp, report, words):
    bad(queue(repo, inp, recorded_ruleset(), report), words)


def test_the_refusal_names_the_workflows_still_missing_the_trigger(repo, inp):
    flows = [
        {"path": ".github/workflows/ci.yml", "state": "missing", "why": None},
        {"path": ".github/workflows/lint.yml", "state": "ready", "why": None},
    ]
    p = queue(repo, inp, recorded_ruleset(), doctor(clean=False, workflows=flows))
    bad(p, "ci.yml")
    assert "lint.yml" not in p.stderr


def test_it_needs_the_doctor_file(repo, inp):
    p = cli(repo, "--merge-queue", put(inp, "ruleset.json", recorded_ruleset()), "--json")
    bad(p, "--doctor")


@pytest.mark.parametrize("longest", ["30", -1, True, 1.5])
def test_a_longest_run_that_isnt_whole_minutes_is_refused(repo, inp, longest):
    report = doctor()
    report["merge_queue"]["signals"]["ci_minutes"]["longest"] = longest
    bad(queue(repo, inp, recorded_ruleset(), report), "longest")


def test_unreadable_signals_count_as_no_history(repo, inp):
    report = doctor()
    report["merge_queue"]["signals"] = None
    body = body_of(queue(repo, inp, recorded_ruleset(), report))["body"]
    assert queue_rule(body)["check_response_timeout_minutes"] == 60


# ---------- the ruleset it goes in ----------


def test_a_ruleset_without_required_checks_is_refused(repo, inp):
    rs = recorded_ruleset()
    rs["rules"] = [r for r in rs["rules"] if r["type"] != "required_status_checks"]
    bad(queue(repo, inp, rs, doctor()), "Require these checks")


@pytest.mark.parametrize(
    "change,words",
    [
        (lambda rs: rs.pop("rules"), "in full"),
        (lambda rs: rs.pop("id"), "id"),
        (lambda rs: rs.update(source_type="Organization", source="acme"), "organisation"),
        (lambda rs: rs.pop("source"), "source"),
        (lambda rs: rs.update(target="tag"), "branch"),
    ],
)
def test_it_refuses_a_ruleset_require_checks_would_refuse(repo, inp, change, words):
    rs = recorded_ruleset()
    change(rs)
    bad(queue(repo, inp, rs, doctor()), words)


def test_the_modes_dont_mix(repo, inp):
    rs, report = put(inp, "ruleset.json", recorded_ruleset()), put(inp, "doctor.json", doctor())
    bad(cli(repo, "--merge-queue", rs, "--doctor", report, "--check", "tests"), "--check")
    bad(cli(repo, "--merge-queue", rs, "--doctor", report, "--rulesets", rs), "--merge-queue")
    bad(cli(repo, "--require-checks", rs, "--check", "tests", "--doctor", report), "--doctor")
    bad(cli(repo, "--require-checks", rs, "--check", "tests", "--timeout", "60"), "--timeout")


# ---------- "Require these checks" with the queue there ----------


def require(repo, inp, ruleset, *names):
    return cli(repo, "--require-checks", put(inp, "ruleset.json", ruleset), *checks(*names), "--json")


def with_queue(rs, strict):
    rs["rules"][2]["parameters"]["strict_required_status_checks_policy"] = strict
    rs["rules"].append({"type": "merge_queue", "parameters": {**SETTINGS, "check_response_timeout_minutes": 60}})
    return rs


@pytest.mark.parametrize("strict", [False, True])
def test_require_checks_leaves_up_to_date_as_it_is_with_the_queue_rule(repo, inp, strict):
    rs = with_queue(recorded_ruleset(), strict)
    body = body_of(require(repo, inp, rs, "tests"))["body"]
    params = checks_params(body)
    assert params["strict_required_status_checks_policy"] is strict
    assert params["required_status_checks"][-1] == {"context": "tests"}
    assert body["rules"][-1] == rs["rules"][-1]


def test_require_checks_adds_a_checks_rule_with_up_to_date_off_beside_the_queue(repo, inp):
    rs = with_queue(recorded_ruleset(), False)
    rs["rules"] = [r for r in rs["rules"] if r["type"] != "required_status_checks"]
    body = body_of(require(repo, inp, rs, "tests"))["body"]
    assert checks_params(body) == {"strict_required_status_checks_policy": False, "required_status_checks": [{"context": "tests"}]}


def test_require_checks_after_the_queue_writer_keeps_up_to_date_off(repo, inp):
    queued = body_of(queue(repo, inp, recorded_ruleset(), doctor()))["body"]
    current = {"id": 42, "source_type": "Repository", "source": "acme/demo", **queued}
    body = body_of(require(repo, inp, current, "e2e"))["body"]
    assert checks_params(body)["strict_required_status_checks_policy"] is False
    assert queue_rule(body) == queue_rule(queued)


def test_require_checks_without_the_queue_still_turns_up_to_date_on(repo, inp):
    body = body_of(require(repo, inp, recorded_ruleset(), "tests"))["body"]
    assert checks_params(body)["strict_required_status_checks_policy"] is True


def test_the_queued_ruleset_reads_back_as_protected_with_the_queue(repo, inp):
    rs = recorded_ruleset()
    queued = body_of(queue(repo, inp, rs, doctor()))["body"]
    current = {**{k: rs[k] for k in ("id", "source_type", "source")}, **queued}
    settings = {"full_name": "acme/demo", "default_branch": "main", "allow_merge_commit": True, "allow_auto_merge": True}
    p = cli(repo, "--rulesets", put(inp, "rulesets.json", [current]), "--repo", put(inp, "repo.json", settings), "--json")
    out = ok(p)
    assert out["checks"]["required"] == ["build", "lint"]


def test_the_doctor_file_can_come_from_standard_input(repo, inp):
    p = cli(repo, "--merge-queue", put(inp, "ruleset.json", recorded_ruleset()), "--doctor", "-", "--json", stdin=json.dumps(doctor()))
    assert queue_rule(body_of(p)["body"])["check_response_timeout_minutes"] == 60
