"""The small review judged by the diff (#257, #255's seams 1, 2, 4 and 5).

When a pull request has at least one counted round and none of them ran
`spec`, `workflow merge-check` holds its diff to the small threshold: at most
`run.small_max_lines` changed lines (default 60) in at most
`run.small_max_files` files (default 4), outside tests. Past it,
`past_small_threshold` replaces every other review reason. Within it, a round
that isn't clean is treated as the last allowed one. `workflow review-record
--measure` counts a commit's change the same way, from git.
"""

import os
import subprocess
from pathlib import Path

import pytest

from test_merge_check import EARLIER, HEAD, check, comment, ids, inputs, project, rec  # noqa: F401 (project is a fixture)
from changelog_notes import since_0110
from workflow import cli
from workflow import profile as profile_mod

KIT = Path(__file__).resolve().parents[1]
SUITE = '\n[[commands.suite]]\nname = "unit"\nrun = "pytest {{files}}"\nfiles = "{globs}"\n'


def suites(project, globs="tests/**/test_*.py"):
    path = project / ".claude/workflow/profile.toml"
    path.write_text(path.read_text() + SUITE.format(globs=globs))


def run_table(project, **values):
    path = project / ".claude/workflow/profile.toml"
    path.write_text(path.read_text() + "\n[run]\n" + "".join(f"{k} = {v}\n" for k, v in values.items()))


def changed(path, adds, dels=0, status="modified", previous=None):
    f = {"filename": path, "status": status, "additions": adds, "deletions": dels}
    if previous:
        f["previous_filename"] = previous
    return f


def small(rnd=1, commit=HEAD, clean=True):
    """A small review's round: Correctness, with no Spec."""
    return rec(rnd=rnd, commit=commit, clean=clean, reviewers="correctness")


def with_files(*files, recs=None):
    data = inputs()
    data["files"] = list(files)
    data["pr"]["changed_files"] = len(files)
    data["comments"] = [comment(r, cid=i + 1) for i, r in enumerate([small()] if recs is None else recs)]
    return data


def review_reasons(got):
    return [r for r in got["reasons"] if r["rule"] == "review_panel"]


def past(got):
    assert ids(got) == ["past_small_threshold"], got["reasons"]
    [r] = got["reasons"]
    assert r["action"] == "review" and r["next"] == "full_round"
    return r


# ---------- merge-check: the threshold ----------


def test_a_round_with_no_spec_on_a_diff_within_the_threshold_is_ready(project, capsys):
    got, _ = check(project, capsys, with_files(changed("src/app.py", 10, 5)))
    assert got["decision"] == "ready", got["reasons"]
    assert got["small"] == {"lines": 15, "files": 1, "max_lines": 60, "max_files": 4, "within": True}


def test_exactly_60_lines_in_4_files_is_ready(project, capsys):
    files = [changed("src/a.py", 20), changed("src/b.py", 10, 10), changed("src/c.py", 0, 10), changed("src/d.py", 5, 5)]
    got, _ = check(project, capsys, with_files(*files))
    assert got["decision"] == "ready", got["reasons"]


def test_one_line_past_gives_past_small_threshold_alone(project, capsys):
    files = [changed("src/a.py", 21), changed("src/b.py", 10, 10), changed("src/c.py", 0, 10), changed("src/d.py", 5, 5)]
    r = past(check(project, capsys, with_files(*files))[0])
    assert "61 changed lines in 4 files" in r["wording"]["developer"]["message"]
    assert "full panel" in r["wording"]["developer"]["fix"] and "Correctness-only" in r["wording"]["developer"]["fix"]


def test_one_file_past_gives_past_small_threshold_alone(project, capsys):
    files = [changed(f"src/{n}.py", 1) for n in "abcde"]
    r = past(check(project, capsys, with_files(*files))[0])
    assert "5 changed lines in 5 files" in r["wording"]["developer"]["message"]


def test_past_the_threshold_replaces_every_other_review_reason(project, capsys):
    big = changed("src/a.py", 100)
    # A small round that isn't clean, with no pass: today's review_not_clean.
    past(check(project, capsys, with_files(big, recs=[small(clean=False)]))[0])
    # A clean round on an earlier commit: today's review_stale.
    past(check(project, capsys, with_files(big, recs=[small(commit=EARLIER)]))[0])
    # Passes at the cap: today's passes_used_up.
    recs = [small(commit=EARLIER, clean=False), rec("pass", commit=EARLIER, clean=False), rec("pass", clean=False)]
    past(check(project, capsys, with_files(big, recs=recs))[0])


# ---------- merge-check: what counts ----------


def test_test_files_are_left_out_of_both_counts(project, capsys):
    suites(project)
    files = [changed("src/app.py", 10), changed("tests/test_app.py", 500), changed("tests/unit/test_more.py", 80),
             changed("tests/test_a.py", 1), changed("tests/test_b.py", 1)]
    got, _ = check(project, capsys, with_files(*files))
    assert got["decision"] == "ready", got["reasons"]
    assert got["small"]["lines"] == 10 and got["small"]["files"] == 1


def test_a_star_stays_within_a_folder_and_fixtures_outside_the_globs_count(project, capsys):
    suites(project, "tests/test_*.py")
    files = [changed("tests/unit/test_more.py", 50), changed("tests/fixtures/data.json", 20)]
    r = past(check(project, capsys, with_files(*files))[0])
    assert "70 changed lines in 2 files" in r["wording"]["developer"]["message"]


def test_a_rename_between_a_test_and_a_non_test_path_counts(project, capsys):
    suites(project)
    for previous, path in (("tests/test_old.py", "src/helpers.py"), ("src/helpers.py", "tests/test_old.py")):
        got, _ = check(project, capsys, with_files(changed(path, 70, status="renamed", previous=previous)))
        past(got)
    got, _ = check(project, capsys, with_files(changed("tests/test_new.py", 70, status="renamed", previous="tests/test_old.py")))
    assert got["decision"] == "ready", got["reasons"]


def test_a_rename_whose_old_path_isnt_given_counts(project, capsys):
    # gh's and GraphQL's lists name only the new path: it may have come from outside tests.
    suites(project)
    data = with_files()
    data["files"] = {"files": [{"path": "tests/test_old.py", "additions": 70, "deletions": 0, "changeType": "RENAMED"}]}
    past(check(project, capsys, data)[0])


def test_a_rename_counts_as_one_file(project, capsys):
    files = [changed(f"src/{n}.py", 1, status="renamed", previous=f"old/{n}.py") for n in "abcd"]
    got, _ = check(project, capsys, with_files(*files))
    assert got["decision"] == "ready", got["reasons"]
    assert got["small"]["files"] == 4


def test_a_project_with_no_suite_globs_counts_every_file(project, capsys):
    past(check(project, capsys, with_files(changed("src/app.py", 10), changed("tests/test_app.py", 60)))[0])


def test_the_counts_from_gh_pr_views_json_are_read_too(project, capsys):
    data = with_files()
    data["files"] = {"files": [{"path": "src/app.py", "additions": 70, "deletions": 0}]}
    past(check(project, capsys, data)[0])


# ---------- merge-check: where the threshold comes from ----------


def test_the_flags_override_the_profiles(project, capsys):
    run_table(project, small_max_lines=100, small_max_files=10)
    data = with_files(changed("src/a.py", 80), *[changed(f"src/{n}.py", 1) for n in "bcdef"])
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]
    assert (got["small_max_lines"], got["small_max_files"]) == (100, 10)
    got, _ = check(project, capsys, data, "--small-max-lines", "80")
    past(got)
    assert got["small_max_lines"] == 80
    got, _ = check(project, capsys, data, "--small-max-files", "5")
    past(got)
    got, _ = check(project, capsys, data, "--small-max-lines", "1000", "--small-max-files", "50")
    assert got["decision"] == "ready", got["reasons"]


def test_without_flags_or_profile_values_the_defaults_are_60_and_4(project, capsys):
    got, _ = check(project, capsys, with_files(changed("src/a.py", 1)))
    assert (got["small_max_lines"], got["small_max_files"]) == (60, 4)


@pytest.mark.parametrize("flag, value", [("--small-max-lines", "0"), ("--small-max-lines", "1001"), ("--small-max-lines", "x"),
                                         ("--small-max-files", "0"), ("--small-max-files", "51"), ("--small-max-files", "-1")])
def test_the_flags_refuse_values_outside_their_bounds(project, capsys, flag, value):
    with pytest.raises(SystemExit) as e:
        cli.main(["merge-check", flag, value, "--json"])
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert flag in err and ("1 to 1000" if "lines" in flag else "1 to 50") in err


# ---------- merge-check: whose review it applies to ----------


def test_a_planning_round_over_the_threshold_is_ready(project, capsys):
    data = with_files(changed("docs/adr/0007.md", 300), recs=[rec(reviewers="spec,correctness")])
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]
    assert got["small"] is None


def test_a_full_panel_round_over_the_threshold_is_ready(project, capsys):
    got, _ = check(project, capsys, with_files(changed("src/app.py", 300), recs=[rec()]))
    assert got["decision"] == "ready", got["reasons"]


def test_a_small_round_that_isnt_clean_with_3_rounds_allowed_asks_for_a_pass(project, capsys):
    data = with_files(changed("src/app.py", 10), recs=[small(clean=False)])
    got, _ = check(project, capsys, data)
    [r] = review_reasons(got)
    assert r["id"] == "review_not_clean" and r["next"] == "pass" and got["review_rounds"] == 3
    data = with_files(changed("src/app.py", 10), recs=[small(commit=EARLIER, clean=False), rec("pass")])
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]


def test_a_light_reviews_round_2_that_isnt_clean_within_the_threshold_still_asks_for_a_round(project, capsys):
    data = with_files(changed("src/app.py", 10), recs=[rec(rnd=1, commit=EARLIER, clean=False), small(rnd=2, clean=False)])
    got, _ = check(project, capsys, data)
    [r] = review_reasons(got)
    assert r["id"] == "review_not_clean" and r["next"] == "round"


def test_a_full_panel_round_past_the_limit_that_isnt_clean_asks_for_a_pass(project, capsys):
    big = changed("src/app.py", 100)
    data = with_files(big, recs=[small(commit=EARLIER), rec(rnd=2, clean=False)])
    got, _ = check(project, capsys, data)
    [r] = review_reasons(got)
    assert r["id"] == "review_not_clean" and r["next"] == "pass" and r["round"] == 2
    data = with_files(big, recs=[small(commit=EARLIER), rec(rnd=2, commit=EARLIER, clean=False), rec("pass", rnd=2)])
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]


def test_passes_after_the_full_panel_round_past_the_limit_count_afresh(project, capsys):
    big = changed("src/app.py", 100)
    recs = [small(commit=EARLIER, clean=False), rec("pass", commit=EARLIER, clean=False), rec("pass", commit=EARLIER, clean=False),
            rec(rnd=2, commit=EARLIER, clean=False), rec("pass", rnd=2, clean=False)]
    got, _ = check(project, capsys, with_files(big, recs=recs))
    assert ids(got) == ["pass_not_clean"], got["reasons"]


# ---------- merge-check: the line counts, needed only where the condition applies ----------


def test_no_counted_round_stays_no_review_with_files_that_have_no_counts(project, capsys):
    data = with_files({"filename": "src/app.py", "status": "modified"}, recs=[])
    got, _ = check(project, capsys, data)
    assert ids(got) == ["no_review"]
    assert got["small"] is None


def test_files_without_counts_where_the_condition_applies_cant_be_read(project, capsys):
    data = with_files({"filename": "src/app.py", "status": "modified"})
    got, _ = check(project, capsys, data)
    assert ids(got) == ["couldnt_read"]
    [r] = got["reasons"]
    assert r["input"] == "files"
    assert "additions and deletions" in r["wording"]["developer"]["message"]
    assert got["small"] is None


def test_files_without_counts_still_give_the_round_its_one_review_reason(project, capsys):
    data = with_files({"filename": "src/app.py", "status": "modified"}, recs=[small(clean=False)])
    got, _ = check(project, capsys, data)
    [r] = review_reasons(got)
    assert r["id"] == "review_not_clean" and r["reviewers"] == ["correctness"]
    assert [x["input"] for x in got["reasons"] if x["id"] == "couldnt_read"] == ["files"]


def test_a_test_file_without_counts_isnt_needed(project, capsys):
    suites(project)
    data = with_files(changed("src/app.py", 3), {"filename": "tests/test_app.py", "status": "modified"})
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]


def test_counts_that_arent_whole_numbers_cant_be_read_where_the_condition_applies(project, capsys):
    got, _ = check(project, capsys, with_files(changed("src/app.py", "ten")))
    assert [x["input"] for x in got["reasons"] if x["id"] == "couldnt_read"] == ["files"]
    assert "whole numbers" in got["reasons"][0]["wording"]["developer"]["message"]
    # Elsewhere they aren't needed, so they never block.
    for recs in ([], [rec()]):
        got, _ = check(project, capsys, with_files(changed("src/app.py", "ten"), recs=recs))
        assert "couldnt_read" not in ids(got), got["reasons"]


# ---------- review-record --measure (seam 2) ----------


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


PROFILE = '[project]\nname = "demo"\nrepo = "acme/demo"\nbase_branch = "main"\n' + SUITE.format(globs="tests/**/test_*.py")
DOC = "".join(f"Line {i} of the notes.\n" for i in range(1, 21))


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """A checkout whose `origin` is a local bare repository, with a branch whose
    change, as GitHub would list its files, is `REST_FILES`."""
    origin, root = tmp_path / "origin.git", tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(root))
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "checkout", "-q", "-b", "main")
    (root / ".claude/workflow").mkdir(parents=True)
    (root / ".claude/workflow/profile.toml").write_text(PROFILE)
    (root / "src").mkdir()
    (root / "src/app.py").write_text("a = 1\nb = 2\nc = 3\n")
    (root / "docs").mkdir()
    (root / "docs/old.md").write_text(DOC)
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    git(root, "push", "-q", "origin", "main")
    git(root, "checkout", "-q", "-b", "claude/build-1")
    (root / "src/app.py").write_text("a = 1\nb = 20\nc = 3\nd = 4\ne = 5\n")  # +3 -1
    (root / "src/new.py").write_text("".join(f"x{i} = {i}\n" for i in range(5)))  # +5
    git(root, "mv", "docs/old.md", "docs/new.md")
    (root / "docs/new.md").write_text(DOC.replace("Line 7 of", "Line seven of"))  # +1 -1
    (root / "assets").mkdir()
    (root / "assets/logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00binary")  # 0 lines
    (root / "tests").mkdir()
    (root / "tests/test_app.py").write_text("".join(f"def test_{i}():\n    pass\n" for i in range(20)))  # a test: left out
    git(root, "add", ".")
    git(root, "commit", "-qm", "change")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.chdir(root)
    return root


REST_FILES = [
    changed("assets/logo.png", 0, 0, status="added"),
    changed("docs/new.md", 1, 1, status="renamed", previous="docs/old.md"),
    changed("src/app.py", 3, 1),
    changed("src/new.py", 5, 0, status="added"),
    changed("tests/test_app.py", 40, 0, status="added"),
]


def measure(capsys, *extra):
    """`review-record --measure` on the checkout's head, with the checkout as the
    project (a test may have pointed CLAUDE_PROJECT_DIR at merge-check's)."""
    os.environ["CLAUDE_PROJECT_DIR"] = str(Path.cwd())  # restored by the fixtures' monkeypatch
    code = cli.main(["review-record", "--measure", "--commit", git(Path.cwd(), "rev-parse", "HEAD"), *extra])
    out, err = capsys.readouterr()
    return code, out, err


def test_measure_writes_no_record_and_counts_as_merge_check_does(checkout, capsys, project):
    code, out, err = measure(capsys)
    assert code == 0, err
    assert out == "11 lines in 4 files outside tests: within the small threshold (at most 60 lines in at most 4 files)\n"
    assert "workflow:review" not in out
    # merge-check, on the same change as GitHub lists it, in a project with the same suite globs.
    os.environ["CLAUDE_PROJECT_DIR"] = str(project)
    suites(project)
    got, _ = check(project, capsys, with_files(*REST_FILES))
    assert got["small"] == {"lines": 11, "files": 4, "max_lines": 60, "max_files": 4, "within": True}


@pytest.mark.parametrize("flags, within", [(("--small-max-lines", "10"), False), (("--small-max-files", "3"), False),
                                           (("--small-max-lines", "11", "--small-max-files", "4"), True)])
def test_measure_and_merge_check_agree_with_the_threshold_flags(checkout, capsys, project, flags, within):
    code, out, err = measure(capsys, *flags)
    assert code == 0, err
    assert out.startswith("11 lines in 4 files outside tests: " + ("within" if within else "past"))
    os.environ["CLAUDE_PROJECT_DIR"] = str(project)
    suites(project)
    got, _ = check(project, capsys, with_files(*REST_FILES), *flags)
    assert (got["small"]["lines"], got["small"]["files"], got["small"]["within"]) == (11, 4, within)


def test_measure_takes_the_profiles_threshold(checkout, capsys):
    path = checkout / ".claude/workflow/profile.toml"
    path.write_text(path.read_text() + "\n[run]\nsmall_max_lines = 10\n")
    code, out, _ = measure(capsys)
    assert code == 0 and out.startswith("11 lines in 4 files outside tests: past the small threshold (at most 10 lines")


def test_measure_counts_against_the_merge_base_not_the_bases_tip(checkout, capsys):
    # The base moves on after the branch was made: its change isn't the branch's.
    base = checkout.parent / "base"
    git(checkout.parent, "clone", "-q", "-b", "main", str(checkout.parent / "origin.git"), str(base))
    (base / "src/other.py").write_text("".join(f"y{i} = {i}\n" for i in range(100)))
    git(base, "add", ".")
    git(base, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "elsewhere")
    git(base, "push", "-q", "origin", "main")
    code, out, _ = measure(capsys)
    assert code == 0 and out.startswith("11 lines in 4 files")
    # It fetched origin/main first.
    assert git(checkout, "rev-parse", "origin/main") == git(base, "rev-parse", "HEAD")


def test_measure_takes_the_base_as_an_option(checkout, capsys):
    # `release` holds the branch's change already, so against it nothing counts.
    git(checkout, "push", "-q", "origin", "HEAD:release")
    git(checkout, "update-ref", "-d", "refs/remotes/origin/release")  # so only a fetch brings it back
    code, out, err = measure(capsys, "--base", "release")
    assert code == 0, err
    assert out.startswith("0 lines in 0 files outside tests: within")
    assert git(checkout, "rev-parse", "origin/release") == git(checkout, "rev-parse", "HEAD")


def test_a_failed_fetch_uses_the_origin_base_already_here_with_a_note(checkout, capsys):
    git(checkout, "fetch", "-q", "origin")
    git(checkout, "remote", "set-url", "origin", str(checkout.parent / "gone.git"))
    code, out, err = measure(capsys)
    assert code == 0
    assert out.startswith("11 lines in 4 files") and out.count("\n") == 1
    assert "couldn't fetch origin/main" in err and "already here" in err


def test_with_no_origin_base_it_says_it_cant_measure(checkout, capsys):
    git(checkout, "remote", "set-url", "origin", str(checkout.parent / "gone.git"))
    git(checkout, "update-ref", "-d", "refs/remotes/origin/main")
    code, out, err = measure(capsys)
    assert code == 1 and out == ""
    assert "can't measure" in err and "no origin/main" in err


def test_a_commit_not_in_the_repository_cant_be_measured(checkout, capsys):
    code = cli.main(["review-record", "--measure", "--commit", "d" * 40])
    out, err = capsys.readouterr()
    assert code == 1 and out == ""
    assert "isn't in this repository" in err


@pytest.mark.parametrize("extra", [("--reviewers", "correctness"), ("--clean",), ("--kind", "round"), ("--round", "1")])
def test_measure_takes_no_record_flags(checkout, capsys, extra):
    code, out, err = measure(capsys, *extra)
    assert code == 2 and out == ""
    assert "--measure writes no record" in err


def test_the_threshold_flags_go_with_measure_only(checkout, capsys):
    code = cli.main(["review-record", "--kind", "round", "--round", "1", "--commit", HEAD, "--reviewers", "correctness", "--clean", "--small-max-lines", "10"])
    out, err = capsys.readouterr()
    assert code == 2 and out == ""
    assert "only with --measure" in err


def test_measure_needs_a_full_commit(checkout, capsys):
    code = cli.main(["review-record", "--measure", "--commit", "HEAD"])
    out, err = capsys.readouterr()
    assert code == 2 and out == "" and "--commit" in err


# ---------- profile.load: run.small_max_lines and run.small_max_files (seam 4) ----------


def _load(tmp_path, run=""):
    root = tmp_path / "p"
    (root / ".claude/workflow").mkdir(parents=True)
    (root / ".claude/workflow/profile.toml").write_text('[project]\nname = "demo"\nrepo = "acme/demo"\n' + (f"\n[run]\n{run}\n" if run else ""))
    return profile_mod.load(root)


def test_the_profile_defaults_are_60_and_4(tmp_path):
    p = _load(tmp_path)
    assert (p.small_max_lines, p.small_max_files) == (60, 4)


@pytest.mark.parametrize("key, n", [("small_max_lines", 1), ("small_max_lines", 1000), ("small_max_files", 1), ("small_max_files", 50)])
def test_the_profile_takes_values_within_the_bounds(tmp_path, key, n):
    assert getattr(_load(tmp_path, f"{key} = {n}"), key) == n


@pytest.mark.parametrize("key, value, bounds", [
    ("small_max_lines", "0", "from 1 to 1000"), ("small_max_lines", "1001", "from 1 to 1000"), ("small_max_lines", '"60"', "from 1 to 1000"),
    ("small_max_files", "0", "from 1 to 50"), ("small_max_files", "51", "from 1 to 50"), ("small_max_files", "2.5", "from 1 to 50"),
    ("small_max_files", "true", "from 1 to 50"),
])
def test_the_profile_refuses_values_outside_the_bounds(tmp_path, key, value, bounds):
    with pytest.raises(profile_mod.ProfileError) as e:
        _load(tmp_path, f"{key} = {value}")
    assert f"run.{key}" in str(e.value) and bounds in str(e.value)


def test_the_template_and_the_profile_doc_name_them():
    template = (KIT / "templates/profile.toml").read_text()
    assert "\nsmall_max_lines = 60" in template and "\nsmall_max_files = 4" in template
    doc = (KIT / "docs/profile.md").read_text().splitlines()
    lines = next(ln for ln in doc if ln.startswith("| `small_max_lines` |"))
    files = next(ln for ln in doc if ln.startswith("| `small_max_files` |"))
    assert "(1–1000)" in lines and "`60`" in lines
    assert "(1–50)" in files and "`4`" in files


# ---------- the kit's text (seam 5) ----------


def _read(rel):
    return (KIT / rel).read_text(encoding="utf-8")


def _item_4():
    flow = _read("docs/flow.md")
    section = flow.split("## 4. The merge rule", 1)[1].split("\n## ", 1)[0]
    return next(ln for ln in section.splitlines() if ln.startswith("4. **The reviews are clean**"))


def test_flow_4_item_4_names_the_condition():
    item = _item_4()
    assert "A review in which no counted round ran Spec (the small review) counts only while the diff is within the small threshold" in item
    assert "`run.small_max_lines` and `run.small_max_files`" in item and "outside tests" in item
    assert "past it, a full-panel round is needed, allowed past the round limit" in item


def test_the_merge_check_skill_matches_flow_4():
    skill = _read("skills/merge-check/SKILL.md")
    row = next(ln for ln in skill.splitlines() if ln.startswith('| `review` | **"Review it now"** |'))
    assert ("When no counted round ran Spec and the diff is past the small threshold (`past_small_threshold`), the full panel (§5), "
            "or the light review's shape (§6) for a pull request a 1-round run built, never a Correctness-only round; "
            "it is allowed past the round limit.") in row
    # The same condition as flow §4's item 4.
    assert "no counted round ran Spec" in _item_4()
    files = next(ln for ln in skill.splitlines() if ln.startswith("| `--files` |"))
    assert "`filename`" in files and "`previous_filename`" in files and "`status`" in files
    assert "`additions` and `deletions`" in files
    assert "--small-max-lines" in skill and "--small-max-files" in skill
    assert "on `past_small_threshold` its `next` is `full_round`" in skill
    assert "- `small`: the diff's counted lines and files against the small threshold" in skill


def test_the_changelog_has_the_note():
    notes = since_0110()
    assert "(#257" in notes and "`past_small_threshold`" in notes and "review-record --measure" in notes


def test_a_path_that_isnt_utf8_is_measured_not_a_traceback(checkout, capsys):
    (Path(os.fsdecode(bytes(checkout) + b"/caf\xe9.txt"))).write_text("one\ntwo\n")
    git(checkout, "add", ".")
    git(checkout, "commit", "-qm", "latin-1 name")
    code, out, err = measure(capsys)
    assert code == 0, err
    assert out.startswith("13 lines in 5 files outside tests")


def test_measure_counts_with_myers_whatever_the_configuration(checkout, capsys):
    git(checkout, "config", "diff.algorithm", "histogram")
    git(checkout, "config", "diff.external", "false")
    code, out, err = measure(capsys)
    assert code == 0, err
    assert out.startswith("11 lines in 4 files")
