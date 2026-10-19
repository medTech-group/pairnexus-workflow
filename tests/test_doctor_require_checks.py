"""#69: `workflow doctor`'s GitHub group reads the base branch's check runs
(`--checks`) and the open pull requests (`--prs`): the `require_checks` offer,
and a check the ruleset requires that the profile doesn't list. Seam 3 of #38
(doctor's offer): the CLI, with recorded rulesets, settings, check runs,
statuses and pull requests given as files or answered by a fake `gh` on the
PATH, as #59's tests use."""

import json
import subprocess
import sys

import fake_gh
from changelog_notes import since_0110
from test_doctor import CLI, RULESET, SETTINGS, _bin, _doctor, _each_at_once, _entries, _lines, _prof, _project, _report, _unchanged_after_doctor, gh_routes
from test_doctor_github import CHECKS, SOLO, _files, _rs, _rule, _without

SHA = "a" * 40
MARKER = "<!-- workflow:required-checks -->"
TWO = '[ci]\nrequired_checks = ["tests", "lint"]\n'
PROTECTED = _prof('experience = "new"\nruleset = true\n', CHECKS)


def _run(name, conclusion="success", app="github-actions", n=1, status="completed"):
    return {"id": n, "name": name, "head_sha": SHA, "status": status, "conclusion": conclusion if status == "completed" else None,
            "started_at": "2026-10-18T09:00:00Z", "completed_at": "2026-10-18T09:05:00Z" if status == "completed" else None,
            "app": {"slug": app}}


def _runs(*runs):
    """GET repos/<repo>/commits/<ref>/check-runs, one page."""
    return {"total_count": len(runs), "check_runs": list(runs)}


def _combined(*statuses):
    """GET repos/<repo>/commits/<ref>/status, one page."""
    return {"state": "success", "sha": SHA, "total_count": len(statuses), "statuses": list(statuses)}


def _status(context, state="success", n=50):
    return {"id": n, "context": context, "state": state, "updated_at": "2026-10-18T09:06:00Z"}


def _pr(number, body="", state="open"):
    return {"number": number, "state": state, "title": f"Change {number}", "body": body}


def _requiring(*names):
    """The protected ruleset, requiring `names`."""
    rs = _rs()
    _rule(rs, "required_status_checks")["parameters"]["required_status_checks"] = [{"context": n} for n in names]
    return rs


def _given(tmp_path, checks=None, prs=None, rulesets=(RULESET,), settings=SETTINGS):
    """--rulesets and --repo, and --checks and --prs when given, as files."""
    args = _files(tmp_path, rulesets, settings)
    d = tmp_path / "input"
    for flag, value in (("--checks", checks), ("--prs", prs)):
        if value is not None:
            f = d / f"{flag[2:]}.json"
            f.write_text(value if isinstance(value, str) else json.dumps(value))
            args += [flag, str(f)]
    return args


def _github(report):
    return {ln["id"]: ln for ln in report["lines"] if ln["group"] == "GitHub"}


def _routes(rulesets=(RULESET,), runs=None, statuses=None, prs=None):
    """The fake `gh`'s answers, with the base branch's checks and the open pull requests."""
    routes = gh_routes(rulesets)
    if runs is not None:
        routes["repos/acme/demo/commits/main/status"] = fake_gh.pages(statuses or _combined())
        routes[f"repos/acme/demo/commits/{SHA}/check-runs"] = fake_gh.pages(runs)
    if prs is not None:
        routes["repos/acme/demo/pulls"] = fake_gh.pages(prs)
    return routes


# The offer, where it goes


def test_the_offer_is_made_on_each_of_its_three_lines_in_json(tmp_path):
    ran = [_runs(_run("tests"), _run("lint", "failure", n=2))]
    calls = [
        # "Checks not required yet": the profile lists none, the ruleset requires none.
        (_project(tmp_path / "a"), _given(tmp_path / "a", ran, rulesets=[_without(_rs(), "required_status_checks")]), {}),
        # The gap naming a check the profile lists that the ruleset doesn't require.
        (_project(tmp_path / "b", profile=_prof("ruleset = true\n", TWO)), _given(tmp_path / "b", ran), {}),
        # The rest agree, but a check ran that neither lists.
        (_project(tmp_path / "c", profile=PROTECTED), _given(tmp_path / "c", ran), {}),
    ]
    a, b, c = (_github(r)["github.required_checks"] for r in _each_at_once(tmp_path, _report, calls))
    assert (a["status"], a["offer"]) == ("note", "require_checks"), a
    assert "checks not required yet" in a["message"].lower() and "`tests`" in a["message"] and "`lint`" in a["message"], a
    assert (b["status"], b["offer"]) == ("gap", "require_checks"), b
    assert "`lint`" in b["message"], b
    assert (c["status"], c["offer"]) == ("note", "require_checks"), c
    assert "`lint`" in c["message"] and "Require these checks" in c["fix"], c


def test_the_offer_shows_in_text(tmp_path):
    root = _project(tmp_path, profile=PROTECTED)
    p = _doctor(tmp_path, root, *_given(tmp_path, [_runs(_run("tests"), _run("lint", n=2))]))
    assert p.returncode == 0, p.stderr
    assert any(e.startswith("[note]") and "`lint`" in e and "Claude can offer: Require these checks" in e for e in _entries(p.stdout)), p.stdout


def test_statuses_count_as_checks_that_ran(tmp_path):
    root = _project(tmp_path, profile=PROTECTED)
    checks = [_runs(_run("tests")), _combined(_status("ci/legacy", "pending"))]
    ln = _github(_report(tmp_path, root, *_given(tmp_path, checks)))["github.required_checks"]
    assert (ln["status"], ln["offer"]) == ("note", "require_checks") and "`ci/legacy`" in ln["message"], ln


# Where it isn't made


def test_the_offer_isnt_made_in_solo_mode_unprotected_all_required_or_for_the_cloudflare_check(tmp_path):
    ran = [_runs(_run("tests"), _run("lint", n=2))]
    cloudflare = [_runs(_run("tests"), _run("Workers Builds: demo", app="cloudflare-workers-and-pages", n=2))]
    calls = [
        # Solo mode, with GitHub protecting `main` anyway, and with no ruleset.
        (_project(tmp_path / "a", profile=_prof("ruleset = false\n", CHECKS)), _given(tmp_path / "a", ran), {}),
        (_project(tmp_path / "b", profile=_prof("ruleset = false\n", CHECKS)), _given(tmp_path / "b", ran, rulesets=[]), {}),
        # The base branch unprotected: "Restore protection" or "Protect `main`" comes first.
        (_project(tmp_path / "c", profile=PROTECTED), _given(tmp_path / "c", ran, rulesets=[]), {}),
        (_project(tmp_path / "d", profile=_prof("", CHECKS)), _given(tmp_path / "d", ran, rulesets=[_without(_rs(), "deletion")]), {}),
        # Every check that ran is required.
        (_project(tmp_path / "e", profile=PROTECTED), _given(tmp_path / "e", [_runs(_run("tests"))]), {}),
        # The only check not required is the try-it link's.
        (_project(tmp_path / "f", profile=PROTECTED), _given(tmp_path / "f", cloudflare), {}),
    ]
    reports = _each_at_once(tmp_path, _report, calls)
    for k, r in enumerate(reports):
        assert not any(ln["offer"] == "require_checks" for ln in r["lines"]), (k, r["lines"])
    e, f = _github(reports[4])["github.required_checks"], _github(reports[5])["github.required_checks"]
    assert e["status"] == f["status"] == "fine", (e, f)
    assert "Workers Builds" not in f["message"]


def test_solo_mode_with_a_ruleset_that_doesnt_require_a_listed_check_is_a_note_never_a_gap(tmp_path):
    # "Protect `main`" made the ruleset before CI ran; the pull request leaving solo mode is still open.
    ran = [_runs(_run("tests"), _run("lint", n=2))]
    profile = _prof("ruleset = false\n", TWO)
    calls = [(_project(tmp_path / k, profile=profile), _given(tmp_path / k, ran, rulesets=rulesets), {})
             for k, rulesets in (("a", [RULESET]), ("b", [_without(_rs(), "deletion")]))]
    for r in _each_at_once(tmp_path, _report, calls):
        ln = _github(r)["github.required_checks"]
        assert (ln["status"], ln["offer"]) == ("note", None) and "`lint`" in ln["message"] and "solo mode" in ln["message"].lower(), ln
        assert "Protect `main`" in ln["fix"], ln
    root = _project(tmp_path / "s", profile=profile)
    assert _doctor(tmp_path / "s", root, *_given(tmp_path / "s", ran), "--strict").returncode == 0


def test_solo_mode_with_checks_listed_and_no_ruleset_is_a_note_and_passes_strict(tmp_path):
    root = _project(tmp_path, profile=_prof("ruleset = false\n", CHECKS))
    args = _given(tmp_path, [_runs(_run("tests"))], rulesets=[], settings={**SETTINGS, "allow_auto_merge": False})
    ln = _github(_report(tmp_path, root, *args))["github.required_checks"]
    assert (ln["status"], ln["offer"]) == ("note", None) and "`tests`" in ln["message"], ln
    assert _doctor(tmp_path, root, *args, "--strict").returncode == 0


# A check the ruleset requires that the profile doesn't list


def test_a_check_the_ruleset_requires_but_the_profile_doesnt_list(tmp_path):
    rulesets = [_requiring("tests", "lint")]
    marked = [_pr(7, "Lists the checks.\n"), _pr(12, f"Requires `lint`.\n\n{MARKER}\n")]
    calls = [
        (_project(tmp_path / "a", profile=PROTECTED), _given(tmp_path / "a", prs=marked, rulesets=rulesets), {}),
        (_project(tmp_path / "b", profile=PROTECTED), _given(tmp_path / "b", prs=[_pr(7), _pr(9, MARKER, state="closed")], rulesets=rulesets), {}),
        (_project(tmp_path / "c", profile=PROTECTED), _given(tmp_path / "c", rulesets=rulesets), {"path": _bin(tmp_path / "c", gh=False)}),
        (_project(tmp_path / "d", profile=PROTECTED), _given(tmp_path / "d", prs='{"not": "pull requests"}', rulesets=rulesets), {}),
    ]
    a, b, c, d = (_github(r) for r in _each_at_once(tmp_path, _report, calls))
    note, gap, unread, bad = (x["github.profile_checks"] for x in (a, b, c, d))
    assert "`tests`" not in note["message"] and "pull request #12 adds" in note["message"], note
    assert note["status"] == "note" and "#12" in note["message"] and "#7" not in note["message"] and "`lint`" in note["message"], note
    assert gap["status"] == "gap" and "`lint`" in gap["message"] and "`tests`" not in gap["message"], gap
    assert "ci.required_checks" in gap["fix"] and "pull request" in gap["fix"], gap
    assert unread["status"] == "cant_check" and "`lint`" in unread["message"] and "gh" in unread["fix"], unread
    assert bad["status"] == "cant_check" and "--prs" in bad["message"], bad
    for x in (a, b, c, d):
        assert x["github.required_checks"]["status"] == "fine", x["github.required_checks"]


def test_in_solo_mode_it_is_a_note_for_the_pull_request_leaving_it(tmp_path):
    root = _project(tmp_path, profile=_prof("ruleset = false\n", CHECKS))
    args = _given(tmp_path, rulesets=[_requiring("tests", "lint")])
    ln = _github(_report(tmp_path, root, *args, path=_bin(tmp_path, gh=False)))["github.profile_checks"]
    assert ln["status"] == "note" and "`lint`" in ln["message"] and "Protect `main`" in ln["fix"], ln
    assert _doctor(tmp_path, root, *args, "--strict", path=_bin(tmp_path, gh=False)).returncode == 0


def test_only_this_repositorys_open_pull_requests_count_each_once(tmp_path):
    def head(repo):
        return {"ref": "x", "repo": None if repo is None else {"full_name": repo}}

    rulesets = [_requiring("tests", "lint")]
    cases = {
        "fork": [{**_pr(30, MARKER), "head": head("stranger/demo")}],
        "deleted": [{**_pr(31, MARKER), "head": head(None)}],
        "own": [{**_pr(32, MARKER), "head": head("Acme/Demo")}],
        "twice": [[_pr(33, MARKER)], [_pr(33, MARKER)]],  # pages that overlap
        "bad": [_pr(-3, MARKER)],
    }
    calls = [(_project(tmp_path / k, profile=PROTECTED), _given(tmp_path / k, prs=prs, rulesets=rulesets), {}) for k, prs in cases.items()]
    fork, deleted, own, twice, bad = (_github(r)["github.profile_checks"] for r in _each_at_once(tmp_path, _report, calls))
    assert fork["status"] == deleted["status"] == "gap", (fork, deleted)
    assert own["status"] == "note" and "#32" in own["message"], own
    assert twice["status"] == "note" and "pull request #33 adds" in twice["message"], twice
    assert bad["status"] == "cant_check" and "workflow ready --prs" in bad["fix"], bad


def test_in_solo_mode_an_open_marked_pull_request_is_named(tmp_path):
    root = _project(tmp_path, profile=_prof("ruleset = false\n", CHECKS))
    args = _given(tmp_path, prs=[_pr(40, MARKER)], rulesets=[_requiring("tests", "lint")])
    ln = _github(_report(tmp_path, root, *args))["github.profile_checks"]
    assert ln["status"] == "note" and "#40" in ln["message"], ln


def test_with_the_profile_listing_none_while_github_requires_some_it_doesnt_say_not_required(tmp_path):
    root = _project(tmp_path)
    lines = _github(_report(tmp_path, root, *_given(tmp_path, prs=[])))
    ln = lines["github.required_checks"]
    assert ln["status"] == "note" and "not required yet" not in ln["message"].lower() and "GitHub requires some" in ln["message"], ln
    assert lines["github.profile_checks"]["status"] == "gap" and "`tests`" in lines["github.profile_checks"]["message"]


def test_with_the_profile_listing_every_required_check_there_is_no_such_line(tmp_path):
    lines = _github(_report(tmp_path, _project(tmp_path, profile=PROTECTED), *_given(tmp_path, prs=[])))
    assert "github.profile_checks" not in lines and lines["github.required_checks"]["status"] == "fine"


def test_strict_passes_on_the_open_profile_pull_requests_note_alone(tmp_path):
    root = _project(tmp_path, profile=PROTECTED)
    args = _given(tmp_path, [_runs(_run("tests"), _run("lint", n=2))], [_pr(12, MARKER)], rulesets=[_requiring("tests", "lint")])
    r = _report(tmp_path, root, *args)
    assert _github(r)["github.profile_checks"]["status"] == "note"
    assert _doctor(tmp_path, root, *args, "--strict").returncode == 0, r["lines"]


# Files, and `gh`


def test_gh_is_read_for_the_checks_and_the_pull_requests_only_with_gets(tmp_path):
    root = _project(tmp_path, profile=PROTECTED)
    path = _bin(tmp_path, gh=_routes([_requiring("tests", "lint")], runs=_runs(_run("tests"), _run("docs", n=3)), prs=[_pr(12, MARKER)]))
    lines = _github(_report(tmp_path, root, path=path))
    assert (lines["github.required_checks"]["status"], lines["github.required_checks"]["offer"]) == ("note", "require_checks")
    assert "`docs`" in lines["github.required_checks"]["message"]
    assert lines["github.profile_checks"]["status"] == "note" and "#12" in lines["github.profile_checks"]["message"]
    gh = fake_gh.FakeGh(path)
    paths = [p.split("?")[0] for p in gh.paths()]
    assert {"repos/acme/demo/commits/main/status", f"repos/acme/demo/commits/{SHA}/check-runs", "repos/acme/demo/pulls"} <= set(paths), paths
    for args in gh.calls():
        assert args[0] == "api" and not {"-X", "--method", "-f", "-F", "--field", "--raw-field", "--input"} & set(args), args


def test_gh_answering_the_status_but_not_the_check_runs_makes_no_offer(tmp_path):
    routes = _routes([RULESET], runs=_runs(_run("tests"), _run("lint", n=2)))
    routes[f"repos/acme/demo/commits/{SHA}/check-runs"] = fake_gh.reply(exit=1, stderr="gh: Server Error (HTTP 502)")
    nosha = _routes([RULESET], runs=_runs(_run("lint", n=2)))
    nosha["repos/acme/demo/commits/main/status"] = fake_gh.pages({"state": "pending", "statuses": [], "total_count": 0})
    calls = [(_project(tmp_path / k, profile=PROTECTED), (), {"path": _bin(tmp_path / k, gh=r)}) for k, r in (("a", routes), ("b", nosha))]
    for r in _each_at_once(tmp_path, _report, calls):
        ln = _github(r)["github.required_checks"]
        assert (ln["status"], ln["offer"]) == ("fine", None), ln


def test_a_file_wins_over_gh(tmp_path):
    root = _project(tmp_path, profile=PROTECTED)
    path = _bin(tmp_path, gh=_routes([_requiring("tests", "lint")], runs=_runs(_run("tests"), _run("from-gh", n=3)), prs=[_pr(12, MARKER)]))
    args = ["--checks", str(tmp_path / "checks.json"), "--prs", str(tmp_path / "prs.json")]
    (tmp_path / "checks.json").write_text(json.dumps([_runs(_run("tests"), _run("from-file", n=4))]))
    (tmp_path / "prs.json").write_text(json.dumps([_pr(20)]))
    lines = _github(_report(tmp_path, root, *args, path=path))
    assert "`from-file`" in lines["github.required_checks"]["message"] and "from-gh" not in lines["github.required_checks"]["message"]
    assert lines["github.profile_checks"]["status"] == "gap"
    paths = [p.split("?")[0] for p in fake_gh.FakeGh(path).paths()]
    assert not any("/commits/" in p or p.endswith("/pulls") for p in paths), paths


def test_without_a_file_or_gh_no_offer_and_59s_lines_are_unchanged(tmp_path):
    calls = []
    for k, (profile, rulesets) in enumerate([(PROTECTED, [RULESET]), (_prof("ruleset = true\n", TWO), [RULESET]),
                                              (_prof('ruleset = true\n'), [_without(_rs(), "required_status_checks")])]):
        root = _project(tmp_path / str(k), profile=profile)
        files = _files(tmp_path / str(k), rulesets)
        unreadable = [*files, "--checks", str(tmp_path / "missing.json")]
        calls += [(root, files, {"path": _bin(tmp_path / f"{k}-none", gh=False)}), (root, unreadable, {"path": _bin(tmp_path / f"{k}-none", gh=False)}),
                  (root, files, {"path": _bin(tmp_path / f"{k}-404")})]  # the fake gh has no checks: GitHub's 404
    reports = iter(_each_at_once(tmp_path, _report, calls))
    # #59's lines: fine, the gap naming `lint`, and "checks not required yet".
    expected = [("fine", "GitHub requires the checks the kit's profile lists to pass before a pull request merges (`tests`)."),
                ("gap", "GitHub doesn't require this check the kit's profile lists to pass before a pull request merges: `lint`."),
                ("note", "Checks not required yet: the kit's profile lists no checks that must pass before a pull request merges into `main`.")]
    for (status, message), none, unreadable, missing in zip(expected, reports, reports, reports):
        want = _github(none)["github.required_checks"]
        assert (want["status"], want["message"], want["offer"]) == (status, message, None), want
        assert _github(unreadable)["github.required_checks"] == want == _github(missing)["github.required_checks"]


def test_a_checks_file_of_pages_and_plain_statuses_reads(tmp_path):
    # The check runs' pages (`gh api --paginate --slurp`) and GET .../statuses' list, side by side.
    root = _project(tmp_path, profile=PROTECTED)
    pages = [{"total_count": 2, "check_runs": [_run("tests")]}, {"total_count": 2, "check_runs": [_run("lint", n=2)]}]
    checks = [pages, [_status("deploy/preview", "failure"), _status("deploy/preview", n=51)]]
    ln = _github(_report(tmp_path, root, *_given(tmp_path, checks)))["github.required_checks"]
    assert ln["offer"] == "require_checks" and "`lint` (passing)" in ln["message"] and "`deploy/preview` (passing)" in ln["message"], ln


def test_only_one_file_can_be_standard_input(tmp_path):
    root = _project(tmp_path, profile=PROTECTED)
    p = _doctor(tmp_path, root, "--checks", "-", "--prs", "-")
    assert p.returncode == 2 and "only one of" in p.stderr and "--checks" in p.stderr and "--prs" in p.stderr, p.stderr


def test_an_old_python_takes_the_new_files_too(tmp_path, monkeypatch):
    from test_doctor_old_python import _old, _old_report

    monkeypatch.setenv("COLUMNS", "100")
    root = _project(tmp_path)
    given = tmp_path / "given.json"
    given.write_text("[]")
    assert _old_report(root, "--checks", str(given), "--prs", str(given)) == _old_report(root)
    code, out, err = _old(root, "--checks", "-", "--prs", "-")
    assert code == 2 and out == "" and "--checks" in err and "--prs" in err, err


# Wording, and changing nothing


def _states(tmp_path, compiled=True):
    """Projects and inputs giving each new line, and the offer on each of its lines."""
    ran = [_runs(_run("tests"), _run("lint", n=2))]
    two = [_requiring("tests", "lint")]
    yield _project(tmp_path / "a", compiled=compiled), _given(tmp_path / "a", ran, rulesets=[_without(_rs(), "required_status_checks")])
    yield _project(tmp_path / "b", profile=_prof("ruleset = true\n", '[ci]\nrequired_checks = ["tests", "docs"]\n'), compiled=compiled), _given(tmp_path / "b", ran)
    yield _project(tmp_path / "c", profile=PROTECTED, compiled=compiled), _given(tmp_path / "c", ran)
    yield _project(tmp_path / "d", profile=PROTECTED, compiled=compiled), _given(tmp_path / "d", ran, [_pr(12, MARKER)], rulesets=two)
    yield _project(tmp_path / "e", profile=PROTECTED, compiled=compiled), _given(tmp_path / "e", ran, [], rulesets=two)
    yield _project(tmp_path / "f", profile=PROTECTED, compiled=compiled), _given(tmp_path / "f", ran, "[", rulesets=two)
    yield _project(tmp_path / "g", profile=_prof("ruleset = false\n", CHECKS), compiled=compiled), _given(tmp_path / "g", ran, rulesets=two)
    yield _project(tmp_path / "h", profile=_prof("ruleset = false\n", TWO), compiled=compiled), _given(tmp_path / "h", ran)
    yield _project(tmp_path / "i", compiled=compiled), _given(tmp_path / "i", ran, [])


def test_each_new_wording_for_new_and_developer_with_the_same_statuses(tmp_path):
    calls = [(root, args, {"env": {"WORKFLOW_EXPERIENCE": experience}}) for root, args in _states(tmp_path) for experience in ("new", "developer")]
    reports = iter(_each_at_once(tmp_path, _report, calls))
    seen = set()
    for n, d in zip(reports, reports):
        n, d = _lines(n), _lines(d)
        assert set(n) == set(d)
        for id_ in ("github.required_checks", "github.profile_checks"):
            if id_ not in n:
                continue
            seen.add((id_, n[id_]["status"], n[id_]["offer"]))
            assert (n[id_]["status"], n[id_]["offer"]) == (d[id_]["status"], d[id_]["offer"]), id_
            assert n[id_]["message"] != d[id_]["message"], (id_, n[id_]["message"])
            if n[id_]["fix"] or d[id_]["fix"]:
                assert n[id_]["fix"] != d[id_]["fix"], (id_, n[id_]["fix"])
    assert {("github.required_checks", "note", "require_checks"), ("github.required_checks", "gap", "require_checks"),
            ("github.profile_checks", "note", None), ("github.profile_checks", "gap", None), ("github.profile_checks", "cant_check", None)} <= seen, seen


def test_nothing_in_the_checkout_changes_after_a_run(tmp_path):
    calls = []
    for root, args in _states(tmp_path, compiled=False):  # so bytecode written would show
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        calls += [(root, (*args, *extra), {}) for extra in ((), ("--json", "--strict"))]
    calls.append((root, (), {"path": _bin(tmp_path / "gh", gh=_routes([_requiring("tests", "lint")], runs=_runs(_run("x")), prs=[]))}))
    _unchanged_after_doctor(tmp_path, calls)


# Docs


def test_the_help_names_the_new_files():
    p = subprocess.run([sys.executable, "-B", str(CLI), "doctor", "--help"], capture_output=True, text=True)
    assert "--checks" in p.stdout and "--prs" in p.stdout


def test_the_changelog_has_a_note_under_unreleased():
    notes = since_0110()
    assert "#69" in notes and "require_checks" in notes and "--checks" in notes and "--prs" in notes
