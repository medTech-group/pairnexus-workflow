"""#601: `workflow doctor`'s own paged reads of GitHub (`_gh` with `paginate`:
the rulesets, the base commit's status and check runs, the open pull requests)
in a Claude Code cloud session, whose proxy refuses GitHub's next-page links
(they name the repository by number). On that refusal alone, doctor reads the
pages one at a time with `page=N` on the `repos/<owner>/<repo>/` path, as
#568's `fetch.by_page` does, within its own time budget (`GH_BUDGET`); any
other failure is reported as before, and the refusal is never worded as the
person's account not being allowed to read it."""

import shutil
import time

import fake_gh
from conftest import KIT
from test_doctor import RULESET, _bin, _fake, _prof, _project, _report
from test_doctor_github import CHECKS, _rs
from test_doctor_require_checks import MARKER, SHA, _combined, _pr, _requiring, _routes, _run, _runs, _status

PROTECTED = _prof('experience = "new"\nruleset = true\n', CHECKS)
FULL = 100  # doctor asks for 100 to a page: a page this full has a next one
ACCOUNT = "may not be allowed"  # the 403 branch's words for an account that can't read it
LACKS = "token lacks access"


def _lines(report):
    return {ln["id"]: ln for ln in report["lines"]}


def _paged(paths, route):
    """The `page=N` read of `route` (no `--paginate`), in order."""
    out = []
    for p in paths:
        base, _, query = p.partition("?")
        if base == route:
            out += [kv.partition("=")[2] for kv in query.split("&") if kv.startswith("page=")]
    return out


def _paginated(gh, route):
    return [args for args in gh.calls() if "--paginate" in args and any(a.split("?")[0] == route for a in args)]


# Every page, read one at a time on the proxy's refusal


def test_the_rulesets_past_the_first_page_are_read_one_page_at_a_time(tmp_path):
    other = [_rs(id=1000 + k, name=f"Release {k}", conditions={"ref_name": {"include": [f"refs/heads/release-{k}"], "exclude": []}}) for k in range(FULL)]
    routes = _routes([*other, RULESET])
    routes["repos/acme/demo/rulesets"] = fake_gh.pages([{"id": rs["id"]} for rs in other], [{"id": RULESET["id"]}], numeric_refused=True)
    path = _bin(tmp_path, gh=routes)
    lines = _lines(_report(tmp_path, _project(tmp_path, profile=PROTECTED), path=path))
    assert lines["github.ruleset"]["status"] == "fine", lines["github.ruleset"]  # only the second page's ruleset is on main
    gh = fake_gh.FakeGh(path)
    assert _paginated(gh, "repos/acme/demo/rulesets"), gh.calls()  # --paginate first, as before
    assert _paged(gh.paths(), "repos/acme/demo/rulesets") == ["1", "2"], gh.paths()
    assert "repos/acme/demo/rulesets/101" in gh.paths()
    for p in gh.paths():
        if _paged([p], "repos/acme/demo/rulesets"):
            assert p.startswith("repos/acme/demo/rulesets?") and "includes_parents=true" in p and "per_page=100" in p, p


def test_the_status_and_check_runs_past_the_first_page_are_read_one_page_at_a_time(tmp_path):
    routes = _routes([_requiring("tests")], runs=_runs(_run("tests")))
    statuses = [_status("tests", n=k) for k in range(FULL)]
    routes["repos/acme/demo/commits/main/status"] = fake_gh.pages(_combined(*statuses), _combined(_status("from-status-page-2", n=500)), numeric_refused=True)
    runs = [_run("tests", n=k) for k in range(FULL)]
    routes[f"repos/acme/demo/commits/{SHA}/check-runs"] = fake_gh.pages(_runs(*runs), _runs(_run("from-runs-page-2", n=600)), numeric_refused=True)
    path = _bin(tmp_path, gh=routes)
    ln = _lines(_report(tmp_path, _project(tmp_path, profile=PROTECTED), path=path))["github.required_checks"]
    assert "`from-runs-page-2`" in ln["message"] and "`from-status-page-2`" in ln["message"], ln
    paths = fake_gh.FakeGh(path).paths()
    assert _paged(paths, "repos/acme/demo/commits/main/status") == ["1", "2"], paths
    assert _paged(paths, f"repos/acme/demo/commits/{SHA}/check-runs") == ["1", "2"], paths


def test_the_open_pull_requests_past_the_first_page_are_read_one_page_at_a_time(tmp_path):
    routes = _routes([_requiring("tests", "lint")])
    routes["repos/acme/demo/pulls"] = fake_gh.pages([_pr(k + 1) for k in range(FULL)], [_pr(212, MARKER)], numeric_refused=True)
    path = _bin(tmp_path, gh=routes)
    ln = _lines(_report(tmp_path, _project(tmp_path, profile=PROTECTED), path=path))["github.profile_checks"]
    assert ln["status"] == "note" and "#212" in ln["message"], ln
    paths = fake_gh.FakeGh(path).paths()
    pages = [p for p in paths if _paged([p], "repos/acme/demo/pulls")]
    assert _paged(paths, "repos/acme/demo/pulls") == ["1", "2"] and all("state=open" in p and "per_page=100" in p for p in pages), paths


def test_the_page_reads_keep_within_doctors_budget_for_githubs_reads(tmp_path, monkeypatch):
    from workflow import doctor
    from workflow.profile import Experience, load

    monkeypatch.setattr(doctor, "GH_BUDGET", 1)
    root = _project(tmp_path, profile=PROTECTED)
    routes = _routes([RULESET])
    routes["repos/acme/demo/rulesets"] = fake_gh.pages([{"id": 101}] * FULL, [{"id": 101}], numeric_refused=True)
    path = _bin(tmp_path, gh=routes)
    (path / "gh").rename(path / "gh-real")
    # Every read answers at once but the page reads, which hang.
    _fake(path, "gh", f'case "$*" in *"&page="*) exec {shutil.which("sleep")} 30;; esac\nexec "{path}/gh-real" "$@"')
    i = doctor.Inputs(root=root, kit_root=KIT, profile=load(root), profile_error=None, experience=Experience(None, "unknown"),
                      environ={"PATH": str(path), "HOME": str(tmp_path)})
    start = time.monotonic()
    lines = {ln.id: ln for ln in doctor.report(i).lines}
    assert time.monotonic() - start < 10
    ln = lines["github.ruleset"]
    assert ln.status == "cant_check", ln
    assert "1 s" in ln.message.developer or "took over 1 s" in ln.message.developer, ln.message.developer
    assert ACCOUNT not in ln.fix.new and LACKS not in ln.fix.developer, ln.fix


def test_more_pages_than_fetch_reads_is_a_cant_check_line_in_both_wordings(tmp_path, monkeypatch):
    from workflow import doctor, fetch
    from workflow.profile import Experience, load

    monkeypatch.setattr(fetch, "MAX_PAGES", 2)
    root = _project(tmp_path, profile=PROTECTED)
    routes = _routes([RULESET])
    full = [{"id": 101}] * FULL
    routes["repos/acme/demo/rulesets"] = fake_gh.pages(full, full, full, numeric_refused=True)
    path = _bin(tmp_path, gh=routes)
    i = doctor.Inputs(root=root, kit_root=KIT, profile=load(root), profile_error=None, experience=Experience(None, "unknown"),
                      environ={"PATH": str(path), "HOME": str(tmp_path)})
    ln = {ln.id: ln for ln in doctor.report(i).lines}["github.ruleset"]  # no traceback
    assert ln.status == "cant_check", ln
    assert "GitHub's answer has more than 2 pages" in ln.message.new, ln.message
    assert "`gh api repos/acme/demo/rulesets` has more than 2 pages" in ln.message.developer, ln.message
    assert "Ask Claude to check the set-up, which gives doctor GitHub's answers as files." in ln.fix.new, ln.fix
    assert f"Give {doctor.GIVE_FILES}." in ln.fix.developer and "--rulesets" in ln.fix.developer, ln.fix
    assert ACCOUNT not in ln.fix.new and LACKS not in ln.fix.developer, ln.fix
    assert _paged(fake_gh.FakeGh(path).paths(), "repos/acme/demo/rulesets") == ["1", "2"], fake_gh.FakeGh(path).paths()


# Any other failure stays as it was


def test_another_403_on_a_paged_read_is_reported_as_before_with_no_page_reads(tmp_path):
    routes = _routes([RULESET])
    routes["repos/acme/demo/rulesets"] = fake_gh.reply(exit=1, stderr="gh: Resource not accessible by integration (HTTP 403)")
    path = _bin(tmp_path, gh=routes)
    ln = _lines(_report(tmp_path, _project(tmp_path, profile=PROTECTED), path=path))["github.ruleset"]
    assert ln["status"] == "cant_check" and ACCOUNT in ln["fix"], ln
    assert _paged(fake_gh.FakeGh(path).paths(), "repos/acme/demo/rulesets") == [], fake_gh.FakeGh(path).paths()


def test_the_refusals_words_in_a_page_on_stdout_dont_start_the_page_reads(tmp_path):
    routes = _routes([RULESET])
    quoted = '[{"id": 101, "name": "' + fake_gh.NUMERIC_REFUSED.replace('"', "'") + '"}]\n'
    routes["repos/acme/demo/rulesets"] = fake_gh.reply(stdout=quoted, exit=1, stderr="gh: Server Error (HTTP 502)")
    path = _bin(tmp_path, gh=routes)
    ln = _lines(_report(tmp_path, _project(tmp_path, profile=PROTECTED), path=path))["github.ruleset"]
    assert ln["status"] == "cant_check" and "502" in ln["message"], ln
    assert _paged(fake_gh.FakeGh(path).paths(), "repos/acme/demo/rulesets") == [], fake_gh.FakeGh(path).paths()


def test_a_page_read_that_fails_is_reported_as_that_failure(tmp_path):
    routes = _routes([_requiring("tests", "lint")])
    routes["repos/acme/demo/pulls"] = fake_gh.reply(exit=1, stderr="gh: Server Error (HTTP 502)")
    # Only --paginate is refused by the proxy; the page reads then fail on their own.
    path = _bin(tmp_path, gh=routes)
    (path / "gh").rename(path / "gh-real")
    refusal = fake_gh.NUMERIC_REFUSED.replace("'", "")
    _fake(path, "gh", f'for a in "$@"; do [ "$a" = --paginate ] && case "$*" in *pulls*) echo \'{refusal}\' >&2; exit 1;; esac; done\nexec "{path}/gh-real" "$@"')
    ln = _lines(_report(tmp_path, _project(tmp_path, profile=PROTECTED), path=path))["github.profile_checks"]
    assert ln["status"] == "cant_check" and "502" in ln["message"], ln
    assert ACCOUNT not in ln["fix"], ln
    assert _paged(fake_gh.FakeGh(path).paths(), "repos/acme/demo/pulls") == ["1"], fake_gh.FakeGh(path).paths()


# The 403 branch's words for the proxy's refusal


def test_the_proxys_refusal_on_a_read_that_isnt_paged_isnt_blamed_on_the_account(tmp_path):
    routes = _routes([RULESET])
    routes["repos/acme/demo/rulesets/101"] = fake_gh.reply(exit=1, stderr=fake_gh.NUMERIC_REFUSED)
    path = _bin(tmp_path, gh=routes)
    for experience in ("new", "developer"):
        ln = _lines(_report(tmp_path, _project(tmp_path / experience, profile=_prof(f'experience = "{experience}"\nruleset = true\n', CHECKS)), path=path))["github.ruleset"]
        assert ln["status"] == "cant_check", ln
        assert ACCOUNT not in ln["fix"] and LACKS not in ln["fix"], ln
        assert "proxy" in ln["message"] + ln["fix"], ln
