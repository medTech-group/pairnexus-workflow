"""`workflow preview`, the preview reader (#113; #41's seam 1), through the CLI,
fed files as `workflow ready`'s file-fed tests are, and with `--fetch` a fake
`gh` on the PATH (`tests/fake_gh.py`).

The fixtures in `tests/fixtures/cloudflare/` are in the shape Cloudflare's
documentation gives the Workers Builds bot's comment and check runs (their
README says which pages, and what was assumed); the made-up cases build the
same shapes here.
"""

import json
from pathlib import Path

import pytest

import fake_gh
from test_merge_check import HEAD, inputs, project  # noqa: F401 (project is a fixture)
from workflow import cli

FIXTURES = Path(__file__).resolve().parent / "fixtures/cloudflare"
OLDER = "e" * 40
APP = "cloudflare-workers-and-pages"
BRANCH_URL = "https://notes-page-demo-notes.example-account.workers.dev"
INTRO = (
    '## Deploying with &nbsp;<a href="https://workers.dev"><img alt="Cloudflare Workers" src="https://workers.cloudflare.com/logo.svg" width="16"></a> &nbsp;Cloudflare Workers\n\n'
    "The latest updates on your project. Learn more about [integrating Git with Workers](https://developers.cloudflare.com/workers/ci-cd/builds/git-integration/).\n\n"
    "| Status | Name | Latest Commit | Preview URL | Updated (UTC) |\n| - | - | - | - | - |\n"
)
LINKS = f"[Commit Preview URL](https://0a1b2c3d-demo-notes.example-account.workers.dev)<br><br>[Branch Preview URL]({BRANCH_URL})"


def recorded(moment):
    d = FIXTURES
    return json.loads((d / f"{moment}.comments.json").read_text()), json.loads((d / f"{moment}.check-runs.json").read_text()), (d / f"{moment}.sha").read_text().strip()


def row(status="✅ Deployment successful!", sha=HEAD, links=LINKS, worker="demo-notes"):
    return f"| {status} <br>[View logs](https://dash.cloudflare.com/0/workers/services/view/{worker}/production/builds/1) | {worker} | [`{sha[:7]}`](https://github.com/acme/demo/commit/{sha}) | {links} | Oct 16 2026, 10:05 AM |\n"


def bot(*rows, cid=501, login="cloudflare-workers-and-pages[bot]", kind="Bot", updated="2026-10-16T10:05:00Z"):
    return {"id": cid, "user": {"login": login, "type": kind}, "body": INTRO + "".join(rows), "created_at": "2026-10-16T09:00:00Z", "updated_at": updated, "html_url": f"https://github.com/acme/demo/pull/12#issuecomment-{cid}"}


def person(body="Looks good to me.", cid=500):
    return {"id": cid, "user": {"login": "owner", "type": "User"}, "body": body, "created_at": "2026-10-16T08:00:00Z", "html_url": f"https://github.com/acme/demo/pull/12#issuecomment-{cid}"}


def cf_run(conclusion="success", status="completed", sha=HEAD, worker="demo-notes", slug=APP, rid=7001, when="2026-10-16T10:04:00Z", name=None):
    return {
        "id": rid,
        "name": name or f"Workers Builds: {worker}",
        "head_sha": sha,
        "status": status,
        "conclusion": conclusion if status == "completed" else None,
        "started_at": "2026-10-16T10:00:00Z",
        "completed_at": when if status == "completed" else None,
        "app": {"slug": slug},
    }


def checks(*runs):
    return {"total_count": len(runs), "check_runs": list(runs)}


def preview(tmp_path, capsys, comments=None, runs=None, sha=HEAD, *extra, as_json=True, raw=None):
    """`workflow preview` on the given data as files; `raw` ({flag: text}) as given."""
    d = tmp_path / "in"
    d.mkdir(exist_ok=True)
    args = ["preview"]
    for flag, value in (("comments", comments), ("checks", runs)):
        if value is not None:
            (d / f"{flag}.json").write_text(json.dumps(value))
            args += [f"--{flag}", str(d / f"{flag}.json")]
    for flag, text in (raw or {}).items():
        (d / flag).write_text(text)
        args += [f"--{flag}", str(d / flag)]
    if sha is not None:
        args += ["--sha", sha]
    args += list(extra) + (["--json"] if as_json else [])
    code = cli.main(args)
    out, err = capsys.readouterr()
    if as_json and code == 0:
        return json.loads(out), code, err
    return out, code, err


def answer(state, url=None, commit=HEAD):
    return {"state": state, "url": url, "commit": commit}


# ---------- the recorded shape ----------


def test_the_recorded_built_head_gives_its_branch_preview_url(tmp_path, capsys):
    comments, runs, sha = recorded("built")
    got, code, _ = preview(tmp_path, capsys, comments, runs, sha)
    assert code == 0
    assert got == answer("built", BRANCH_URL, sha)


def test_the_recorded_earlier_failed_row_is_failed(tmp_path, capsys):
    comments, runs, sha = recorded("failed")
    got, code, _ = preview(tmp_path, capsys, comments, runs, sha)
    assert code == 0
    assert got == answer("failed", None, sha)


def test_the_recorded_built_comment_for_an_earlier_head_is_building_for_a_new_push(tmp_path, capsys):
    comments, _, sha = recorded("built")
    got, _, _ = preview(tmp_path, capsys, comments, checks(cf_run(status="in_progress")), HEAD)
    assert got == answer("building", None, HEAD)


def test_the_recorded_shape_gives_json_merge_check_takes(project, tmp_path, capsys):
    comments, runs, sha = recorded("built")
    got, _, _ = preview(tmp_path, capsys, comments, runs, sha)
    data = inputs()
    data["pr"]["head"]["sha"] = sha
    data["commits"][-1]["sha"] = sha
    data["checks"]["check_runs"][0]["head_sha"] = sha
    data["compare"]["commits"][-1]["sha"] = sha
    data["compare"]["url"] = f"https://api.github.com/repos/acme/demo/compare/main...{sha}"
    from workflow import reviews

    data["comments"] = [{"id": 100, "user": {"login": "owner"}, "body": reviews.record(kind="round", round=1, commit=sha, reviewers="standards,spec,correctness", clean=True), "created_at": "2026-10-16T09:00:00Z"}]
    data["preview"] = got
    res = merge_check(tmp_path, capsys, data)
    assert res["decision"] == "ready", res["reasons"]
    assert res["preview"] == {"state": "built", "url": BRANCH_URL}


# ---------- made-up cases ----------


def test_a_failed_build(tmp_path, capsys):
    got, _, _ = preview(tmp_path, capsys, [bot(row("❌ Deployment failed", links=""))], checks(cf_run("failure")))
    assert got == answer("failed")


@pytest.mark.parametrize("conclusion", ["cancelled", "timed_out", "action_required"])
def test_a_build_that_didnt_finish_well_is_failed(tmp_path, capsys, conclusion):
    got, _, _ = preview(tmp_path, capsys, [bot(row("❌ Deployment failed", links=""))], checks(cf_run(conclusion)))
    assert got["state"] == "failed"


@pytest.mark.parametrize("status", ["queued", "in_progress"])
def test_a_build_in_progress(tmp_path, capsys, status):
    got, _, _ = preview(tmp_path, capsys, [bot(row(sha=OLDER))], checks(cf_run(status=status)))
    assert got == answer("building")


def test_a_preview_of_an_older_commit_is_building_never_built(tmp_path, capsys):
    # The head's build passed, but the bot's comment still shows the last commit's link.
    got, _, _ = preview(tmp_path, capsys, [bot(row(sha=OLDER))], checks(cf_run()))
    assert got == answer("building", None, OLDER)


def test_a_comment_for_an_older_commit_and_no_check_on_the_head_yet_is_building(tmp_path, capsys):
    got, _, _ = preview(tmp_path, capsys, [bot(row(sha=OLDER))], checks(cf_run(sha=OLDER)))
    assert got == answer("building", None, OLDER)


def test_no_bot_and_no_check_is_none(tmp_path, capsys):
    got, _, _ = preview(tmp_path, capsys, [person()], checks())
    assert got == answer("none", None, None)


def test_no_comments_at_all_and_other_checks_is_none(tmp_path, capsys):
    got, _, _ = preview(tmp_path, capsys, [], checks({**cf_run(), "name": "tests", "app": {"slug": "github-actions"}}))
    assert got == answer("none", None, None)


def test_a_comment_edited_after_the_check_is_read_as_it_stands(tmp_path, capsys):
    run = cf_run(when="2026-10-16T10:04:00Z")
    got, _, _ = preview(tmp_path, capsys, [bot(row(), updated="2026-10-16T10:30:00Z")], checks(run))
    assert got == answer("built", BRANCH_URL)
    # Edited again later to a failed row for the head: the URL no longer counts.
    got, _, _ = preview(tmp_path, capsys, [bot(row("❌ Deployment failed", links=""), updated="2026-10-16T10:40:00Z")], checks(run))
    assert got["state"] != "built" and got["url"] is None


@pytest.mark.parametrize("slug", ["cloudflare-workers-builds", "my-ci", "cloudflare-pages"])
def test_a_check_from_another_app_with_a_similar_name_is_ignored(tmp_path, capsys, slug):
    impostor = cf_run("failure", slug=slug, rid=7002, when="2026-10-16T10:09:00Z")
    got, _, _ = preview(tmp_path, capsys, [person()], checks(impostor))
    assert got == answer("none", None, None)
    got, _, _ = preview(tmp_path, capsys, [bot(row())], checks(cf_run(), impostor))
    assert got == answer("built", BRANCH_URL)


def test_another_check_from_cloudflares_app_isnt_the_workers_build(tmp_path, capsys):
    other = cf_run("failure", name="Cloudflare Pages", rid=7003)
    got, _, _ = preview(tmp_path, capsys, [bot(row())], checks(cf_run(), other))
    assert got == answer("built", BRANCH_URL)


def test_a_comment_from_someone_else_with_the_same_table_is_ignored(tmp_path, capsys):
    for c in (bot(row(), login="cloudflare-workers-and-pages-fan"), bot(row(), kind="User"), bot(row(), login="owner")):
        got, _, _ = preview(tmp_path, capsys, [c], checks())
        assert got == answer("none", None, None), c["user"]


def test_the_bots_login_without_bot_counts_as_gh_gives_it(tmp_path, capsys):
    c = bot(row())
    c.pop("user")
    c["author"] = {"login": "cloudflare-workers-and-pages"}
    got, _, _ = preview(tmp_path, capsys, [c], checks(cf_run()))
    assert got == answer("built", BRANCH_URL)


def test_a_rerun_counts_by_its_latest_result(tmp_path, capsys):
    first = cf_run("failure", rid=7001, when="2026-10-16T10:01:00Z")
    rerun = cf_run("success", rid=7005, when="2026-10-16T10:08:00Z")
    got, _, _ = preview(tmp_path, capsys, [bot(row())], checks(first, rerun))
    assert got == answer("built", BRANCH_URL)
    got, _, _ = preview(tmp_path, capsys, [bot(row())], checks(rerun, {**first, "id": 7009, "completed_at": "2026-10-16T10:20:00Z"}))
    assert got["state"] == "failed"


def test_the_newer_wording_preview_url_and_deployment_url(tmp_path, capsys):
    links = "[Preview URL](https://notes-page-demo-notes.example-account.workers.dev)<br>[Deployment URL](https://1a2b3c4d-demo-notes.example-account.workers.dev)"
    got, _, _ = preview(tmp_path, capsys, [bot(row(links=links))], checks(cf_run()))
    assert got == answer("built", BRANCH_URL)


def test_a_successful_row_without_a_preview_url_has_no_link(tmp_path, capsys):
    # The build ran no `wrangler preview`: there's nothing to try.
    got, _, _ = preview(tmp_path, capsys, [bot(row(links=""))], checks(cf_run()))
    assert got == answer("none", None, HEAD)


def test_a_link_that_isnt_a_web_address_doesnt_count(tmp_path, capsys):
    got, _, _ = preview(tmp_path, capsys, [bot(row(links="[Branch Preview URL](javascript:alert(1))"))], checks(cf_run()))
    assert got["url"] is None and got["state"] != "built"


def test_two_workers_need_both_built_and_give_the_first_link(tmp_path, capsys):
    api_links = "[Branch Preview URL](https://notes-page-demo-api.example-account.workers.dev)"
    rows = (row(worker="demo-notes"), row(worker="demo-api", links=api_links))
    got, _, _ = preview(tmp_path, capsys, [bot(*rows)], checks(cf_run(worker="demo-notes"), cf_run(worker="demo-api", rid=7010)))
    assert got == answer("built", "https://notes-page-demo-api.example-account.workers.dev")
    got, _, _ = preview(tmp_path, capsys, [bot(*rows)], checks(cf_run(worker="demo-notes"), cf_run("failure", worker="demo-api", rid=7010)))
    assert got["state"] == "failed"
    got, _, _ = preview(tmp_path, capsys, [bot(*rows)], checks(cf_run(worker="demo-notes"), cf_run(status="queued", worker="demo-api", rid=7010)))
    assert got["state"] == "building"


def test_a_check_run_for_another_commit_in_the_file_is_left_out(tmp_path, capsys):
    got, _, _ = preview(tmp_path, capsys, [bot(row())], checks(cf_run(), cf_run("failure", sha=OLDER, rid=7011, when="2026-10-16T11:00:00Z")))
    assert got == answer("built", BRANCH_URL)


def test_merge_checks_checks_file_with_statuses_too_is_read(tmp_path, capsys):
    combined = {"sha": HEAD, "state": "success", "total_count": 1, "statuses": [{"context": "ci/other", "state": "success", "url": f"https://api.github.com/repos/acme/demo/statuses/{HEAD}"}]}
    got, _, _ = preview(tmp_path, capsys, [bot(row())], [checks(cf_run()), combined])
    assert got == answer("built", BRANCH_URL)


def test_comments_as_pages_and_in_the_mcp_tools_shape_are_read(tmp_path, capsys):
    got, _, _ = preview(tmp_path, capsys, [[person()], [bot(row())]], [checks(cf_run())])
    assert got == answer("built", BRANCH_URL)
    got, _, _ = preview(tmp_path, capsys, {"comments": [bot(row())]}, checks(cf_run()))
    assert got == answer("built", BRANCH_URL)


def test_a_short_sha_is_matched_to_the_rows_commit(tmp_path, capsys):
    got, _, _ = preview(tmp_path, capsys, [bot(row())], checks(cf_run()), HEAD[:12])
    assert got == answer("built", BRANCH_URL, HEAD[:12])


# ---------- what can't be read ----------


def test_a_list_of_check_runs_shorter_than_its_total_is_refused(tmp_path, capsys):
    short = {"total_count": 3, "check_runs": [cf_run()]}
    out, code, err = preview(tmp_path, capsys, [bot(row())], short)
    assert code == 1 and "--checks" in err and "every page" in err


def test_a_bots_comment_without_a_table_it_knows_is_refused(tmp_path, capsys):
    c = bot()
    c["body"] = "## Deploying with Cloudflare Workers\n\nSomething new."
    out, code, err = preview(tmp_path, capsys, [c], checks(cf_run()))
    assert code == 1 and "--comments" in err and "table" in err


@pytest.mark.parametrize("bad", ["not json", '{"what": 1}', "[1, 2]"])
def test_a_checks_file_that_isnt_check_runs_is_refused(tmp_path, capsys, bad):
    out, code, err = preview(tmp_path, capsys, [], None, HEAD, raw={"checks": bad})
    assert code == 1 and "--checks" in err


def test_a_comments_file_that_isnt_comments_is_refused(tmp_path, capsys):
    out, code, err = preview(tmp_path, capsys, None, checks(), HEAD, raw={"comments": '{"what": 1}'})
    assert code == 1 and "--comments" in err


@pytest.mark.parametrize("sha", ["xyz", "abc12", "a" * 41, ""])
def test_a_sha_that_isnt_one_is_refused(tmp_path, capsys, sha):
    with pytest.raises(SystemExit) as e:
        preview(tmp_path, capsys, [], checks(), sha)
    assert e.value.code == 2 and "--sha" in capsys.readouterr().err


@pytest.mark.parametrize("leave_out", [("comments",), ("checks",), ("sha",), ("comments", "checks", "sha")])
def test_with_neither_a_file_nor_fetch_it_says_whats_missing(tmp_path, capsys, leave_out):
    comments = None if "comments" in leave_out else []
    runs = None if "checks" in leave_out else checks()
    sha = None if "sha" in leave_out else HEAD
    out, code, err = preview(tmp_path, capsys, comments, runs, sha)
    assert code == 2 and out == ""
    for name in leave_out:
        assert f"--{name}" in err
    assert "--fetch" in err


# ---------- the text ----------


@pytest.mark.parametrize(
    "comments, runs, said",
    [
        ([bot(row())], checks(cf_run()), f"ready: {BRANCH_URL}"),
        ([bot(row("❌ Deployment failed", links=""))], checks(cf_run("failure")), "didn't build"),
        ([bot(row(sha=OLDER))], checks(cf_run(status="in_progress")), "still building"),
        ([bot(row(sha=OLDER))], checks(cf_run()), "not the head"),
        ([], checks(), "No try-it link"),
    ],
)
def test_the_text_says_it_plainly(tmp_path, capsys, comments, runs, said):
    out, code, _ = preview(tmp_path, capsys, comments, runs, HEAD, as_json=False)
    assert code == 0 and said in out


def test_the_json_has_state_url_and_commit_only(tmp_path, capsys):
    got, _, _ = preview(tmp_path, capsys, [bot(row())], checks(cf_run()))
    assert set(got) == {"state", "url", "commit"}


# ---------- merge-check takes the JSON ----------


def merge_check(tmp_path, capsys, data):
    d = tmp_path / "mc"
    d.mkdir(exist_ok=True)
    args = ["merge-check"]
    for name, value in data.items():
        (d / f"{name}.json").write_text(json.dumps(value))
        args += [f"--{name}", str(d / f"{name}.json")]
    assert cli.main(args + ["--review-rounds", "3", "--json"]) == 0
    return json.loads(capsys.readouterr().out)


@pytest.mark.parametrize(
    "comments, runs, decision, reason",
    [
        ([bot(row())], checks(cf_run()), "ready", None),
        ([bot(row("❌ Deployment failed", links=""))], checks(cf_run("failure")), "not_yet", "preview_failed"),
        ([bot(row(sha=OLDER))], checks(cf_run(status="queued")), "not_yet", "preview_building"),
        ([bot(row(sha=OLDER))], checks(cf_run()), "not_yet", "preview_building"),
        ([], checks(), "ready", None),
    ],
)
def test_merge_check_takes_the_json(project, tmp_path, capsys, comments, runs, decision, reason):
    got, _, _ = preview(tmp_path, capsys, comments, runs)
    data = inputs()
    data["preview"] = got
    res = merge_check(tmp_path, capsys, data)
    assert res["decision"] == decision
    assert [r["id"] for r in res["reasons"] if r["id"].startswith("preview")] == ([reason] if reason else [])
    if got["state"] == "none":
        assert "no_previews" in [n["id"] for n in res["notes"]]


# ---------- --fetch ----------

R = "repos/acme/demo"


def routes(comments=None, runs=None, head=HEAD):
    return {
        f"{R}/pulls/12": {"number": 12, "head": {"sha": head}, "base": {"ref": "main"}},
        f"{R}/issues/12/comments": fake_gh.pages(*(comments if comments is not None else [[person()], [bot(row())]])),
        f"{R}/commits/{head}/check-runs": fake_gh.pages(*(runs if runs is not None else [checks(cf_run())])),
    }


def test_fetch_reads_the_three_inputs_with_gh(project, tmp_path, capsys, monkeypatch):
    gh = fake_gh.install(tmp_path, monkeypatch, routes())
    got, code, _ = preview(tmp_path, capsys, None, None, None, "--fetch", "12")
    assert code == 0 and got == answer("built", BRANCH_URL)
    asked = [p.split("?", 1)[0] for p in gh.paths()]
    assert set(asked) == {f"{R}/pulls/12", f"{R}/issues/12/comments", f"{R}/commits/{HEAD}/check-runs"}
    assert all("--paginate" in c for c in gh.calls() if "pulls/12" not in c[-1])


def test_fetch_reads_every_page(project, tmp_path, capsys, monkeypatch):
    many = [cf_run("success", rid=7100 + i, worker=f"w{i}") for i in range(3)]
    pages = [{"total_count": 3, "check_runs": many[:2]}, {"total_count": 3, "check_runs": many[2:]}]
    rows = [row(worker=f"w{i}") for i in range(3)]
    fake_gh.install(tmp_path, monkeypatch, routes([[bot(*rows)]], pages))
    got, code, _ = preview(tmp_path, capsys, None, None, None, "--fetch", "12")
    assert code == 0 and got["state"] == "built"


def test_fetch_with_a_gh_too_old_to_slurp(project, tmp_path, capsys, monkeypatch):
    fake_gh.install(tmp_path, monkeypatch, routes(), slurp=False)
    got, code, _ = preview(tmp_path, capsys, None, None, None, "--fetch", "12")
    assert code == 0 and got == answer("built", BRANCH_URL)


def test_a_comments_file_wins_over_fetchs_gh(project, tmp_path, capsys, monkeypatch):
    gh = fake_gh.install(tmp_path, monkeypatch, routes())
    got, code, _ = preview(tmp_path, capsys, [bot(row("❌ Deployment failed", links=""))], None, None, "--fetch", "12")
    assert code == 0 and got == answer("building", None, HEAD)
    assert f"{R}/issues/12/comments" not in gh.paths()


def test_a_checks_file_wins_over_fetchs_gh(project, tmp_path, capsys, monkeypatch):
    gh = fake_gh.install(tmp_path, monkeypatch, routes())
    got, code, _ = preview(tmp_path, capsys, None, checks(cf_run("failure")), None, "--fetch", "12")
    assert code == 0 and got == answer("failed", None, HEAD)
    assert f"{R}/commits/{HEAD}/check-runs" not in gh.paths()


def test_the_sha_given_wins_over_the_pull_requests_head(project, tmp_path, capsys, monkeypatch):
    r = {**routes(), f"{R}/commits/{OLDER}/check-runs": fake_gh.pages(checks(cf_run("failure", sha=OLDER)))}
    gh = fake_gh.install(tmp_path, monkeypatch, r)
    got, code, _ = preview(tmp_path, capsys, None, None, OLDER, "--fetch", "12")
    assert code == 0 and got == answer("failed", None, OLDER)
    assert f"{R}/pulls/12" not in gh.paths()


def test_with_every_input_as_a_file_gh_isnt_asked(project, tmp_path, capsys, monkeypatch):
    gh = fake_gh.install(tmp_path, monkeypatch, routes())
    got, code, _ = preview(tmp_path, capsys, [bot(row())], checks(cf_run()), HEAD, "--fetch", "12")
    assert code == 0 and got == answer("built", BRANCH_URL)
    assert gh.paths() == []


def test_fetch_without_gh_says_to_give_files(project, tmp_path, capsys, monkeypatch):
    fake_gh.without_gh(tmp_path, monkeypatch)
    out, code, err = preview(tmp_path, capsys, None, None, None, "--fetch", "12")
    assert code == 1 and out == ""
    assert "isn't installed" in err and "--comments" in err and "--sha" in err


def test_a_failed_call_names_its_input(project, tmp_path, capsys, monkeypatch):
    r = routes()
    r[f"{R}/commits/{HEAD}/check-runs"] = fake_gh.reply(exit=1, stderr="gh: Server Error (HTTP 502)")
    fake_gh.install(tmp_path, monkeypatch, r)
    out, code, err = preview(tmp_path, capsys, None, None, None, "--fetch", "12")
    assert code == 1 and "--checks" in err and "HTTP 502" in err


def test_fetch_without_a_profile_says_so(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "nowhere"))
    (tmp_path / "nowhere").mkdir()
    out, code, err = preview(tmp_path, capsys, None, None, None, "--fetch", "12")
    assert code == 2 and "profile" in err and "--comments" in err


def test_fetch_refuses_a_number_that_isnt_one(tmp_path, capsys):
    with pytest.raises(SystemExit):
        cli.main(["preview", "--fetch", "twelve"])
