"""Research records and `merge-check` for research pull requests (#509, spec #505).

Seam 1: the `workflow` CLI fed files, as `tests/test_merge_check.py` and
`tests/test_review_record.py` run it. A pull request whose files are all under
`docs/research/` is judged on its latest counted research record and on what
changed since it in its own changes; any other gets the review panel's rule,
and its research records don't count.

Seam 2: text contracts. The mark the fixtures use is copied from the `study`
skill's text (`tests/fixtures/research/marked-line.md`) and tied to it here,
as `tests/test_research_notes.py` ties the note's fixtures; flow §4 item 4
carries the rule.

The note is the `study` skill's example (`tests/fixtures/research/booking-ahead/`),
added by the pull request, as GitHub's list of its files gives it.
"""

import json
import re
from pathlib import Path

import pytest

import fake_gh
from test_merge_check import EARLIER, HEAD, comment, ids, inputs, note_ids, project, run_  # noqa: F401 (project is a fixture)
from test_merge_check_evidence import REPO, routes, run
from test_review_record_hashes import checkout, commit_all, git  # noqa: F401 (checkout is a fixture)
from workflow import cli, merge, own_changes, research_pr, reviews

KIT = Path(__file__).resolve().parents[1]
FIX = KIT / "tests/fixtures/research"
SKILL = KIT / "skills/study/SKILL.md"
MIDDLE = "e" * 40  # a commit between EARLIER and HEAD
BASE_TIP = "f" * 40  # the base branch's head, outside the pull request
FORK = "9" * 40  # where the pull request's branch left the base

NOTE_PATH = "docs/research/booking-ahead/note.md"
SAVED_PATH = "docs/research/booking-ahead/sources/booking-help.md"
NOTE = (FIX / "booking-ahead/note.md").read_text(encoding="utf-8")
SAVED = (FIX / "booking-ahead/sources/booking-help.md").read_text(encoding="utf-8")
MARKED = (FIX / "marked-line.md").read_text(encoding="utf-8").rstrip("\n")
CLAIM = MARKED.removesuffix(research_pr.MARK)


# ---------- the pull request, as GitHub gives its files ----------


def added(path, text):
    lines = text.splitlines()
    return {"filename": path, "status": "added", "additions": len(lines), "deletions": 0, "sha": format(abs(hash(text)), "040x")[:40],
            "patch": f"@@ -0,0 +1,{len(lines)} @@\n" + "\n".join("+" + line for line in lines)}


def note(text=NOTE):
    """The pull request's files: the note (with `text`) and its saved copy, both added."""
    return [added(NOTE_PATH, text), added(SAVED_PATH, SAVED)]


def marked(text=NOTE):
    """The note with the claim's line marked, as the fixture copied from the skill shows it."""
    assert CLAIM in text.splitlines()
    return "\n".join(MARKED if line == CLAIM else line for line in text.splitlines()) + "\n"


def changed(text=NOTE):
    """The note with a claim changed: more than a mark."""
    return text.replace("30 days ahead", "60 days ahead")


def hashes(files):
    return own_changes.of_files(merge._changes_of(files, "files"))


def record(rnd, files, commit=HEAD, clean=True, hashed=True):
    """A research record (#509) for `commit`, whose own changes are `files`."""
    h = hashes(files)
    extra = {"diff": h.diff, "lines": h.lines} if hashed else {}
    return reviews.record(kind="research", round=rnd, commit=commit, reviewers="research", clean=clean, **extra)


def pr(files, *bodies, commits=((EARLIER, (FORK,)), (HEAD, (EARLIER,))), authors=None):
    """The pull request at HEAD with `files`, its comments `bodies` (each by
    the owner, or by `authors[i]`), and `commits` as (sha, parents)."""
    data = inputs()
    data["files"] = files
    data["pr"]["changed_files"] = len(files)
    data["commits"] = [{"sha": s, "parents": [{"sha": p} for p in ps]} for s, ps in commits]
    data["pr"]["commits"] = len(commits)
    data["compare"]["commits"] = [{"sha": s} for s, _ in commits]
    data["compare"]["ahead_by"] = len(commits)
    data["comments"] = [comment(b, author=(authors or {}).get(i, "owner"), cid=i + 1) for i, b in enumerate(bodies)]
    data["pr"]["comments"] = len(bodies)
    return data


def compared(files, commit):
    """GitHub's comparison of the base with `commit`: what `--recorded` takes."""
    return {"url": f"https://api.github.com/repos/acme/demo/compare/main...{commit}", "status": "ahead", "ahead_by": 1, "behind_by": 0, "files": files}


def judged(project, capsys, data, recorded=None):
    if recorded is not None:
        data = {**data, "recorded": recorded}
    got, code = run(project, capsys, data)
    assert code == 0
    return got


def review_reasons(got):
    return [r for r in got["reasons"] if r["rule"] == "review_panel"]


# ---------- review-record --kind research (seam 1, as tests/test_review_record.py) ----------


@pytest.fixture
def no_project(tmp_path, monkeypatch):
    """No profile and no git here: the hashes are `unknown`."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))


def recorded_cli(capsys, *args):
    code = cli.main(["review-record", *args])
    out, err = capsys.readouterr()
    return code, out, err


@pytest.mark.parametrize("rnd, name", [("1", "Research check"), ("2", "The look at a fix")])
@pytest.mark.parametrize("flag, result", [("--clean", "clean"), ("--not-clean", "not-clean")])
def test_review_record_writes_a_research_record_clean_and_not_clean(no_project, capsys, rnd, name, flag, result):
    sha = "3f2a9c0b7de14a2c9e8f5d6b1a0c3e2f4d5b6a7c"
    code, out, err = recorded_cli(capsys, "--kind", "research", "--round", rnd, "--commit", sha, "--reviewers", "research", flag)
    assert code == 0, err
    assert out.splitlines() == [
        f"{name} on `3f2a9c0`: {result.replace('-', ' ')}. Reviewer: Research.",
        f"<!-- workflow:review kind=research round={rnd} commit={sha} reviewers=research diff=unknown lines=unknown result={result} -->",
        "<!-- workflow:agent -->",
    ]
    [r] = reviews.records_in(out)
    assert (r.kind, r.round, r.commit, r.reviewers, r.result) == ("research", int(rnd), sha, ("research",), result)


def test_a_research_record_carries_the_hashes_of_its_commits_own_changes(checkout, capsys):
    (checkout / "docs/research/booking-ahead").mkdir(parents=True)
    (checkout / NOTE_PATH).write_text(NOTE)
    sha = commit_all(checkout, "the note")
    code, out, err = recorded_cli(capsys, "--kind", "research", "--round", "1", "--commit", sha, "--reviewers", "research", "--not-clean")
    assert code == 0, err
    [r] = reviews.records_in(out)
    want = own_changes.local(checkout, sha, "main", lambda _: None, "test")
    assert (r.diff, r.lines) == (want.diff, want.lines) and re.fullmatch(r"[0-9a-f]{64}", r.diff)
    for kind, reviewers in (("round", "standards,spec,correctness"), ("research", "research")):
        code, out, _ = recorded_cli(capsys, "--kind", kind, "--round", "1", "--commit", sha, "--reviewers", reviewers, "--clean")
        assert code == 0
        assert reviews.records_in(out)[0].diff == want.diff  # the same hashes as a round's


@pytest.mark.parametrize("args, says", [
    (["--reviewers", "correctness"], "one reviewer is `research`, not `correctness`"),
    (["--reviewers", "research,spec"], "one reviewer is `research`, not `spec`"),
    (["--reviewers", ""], "give --reviewers"),
    (["--round", "3"], "round is 1 (the research check) or 2 (the look at a fix)"),
    (["--round", "0"], "a whole number from 1"),
    (["--commit", "abc1234"], "full 40-character"),
])
def test_review_record_refuses_a_research_record_with_another_reviewer_or_round(no_project, capsys, args, says):
    base = {"--kind": "research", "--round": "1", "--commit": "a" * 40, "--reviewers": "research"}
    base.update(dict(zip(args[::2], args[1::2])))
    code, out, err = recorded_cli(capsys, *[x for kv in base.items() for x in kv], "--clean")
    assert code == 2 and out == "" and says in err, err


def test_research_is_no_reviewer_of_a_round_or_pass_and_takes_no_findings_or_body(no_project, capsys, tmp_path):
    for kind in ("round", "pass"):
        code, _, err = recorded_cli(capsys, "--kind", kind, "--round", "1", "--commit", "a" * 40, "--reviewers", "research", "--clean")
        assert code == 2 and "give --kind research" in err
    found = tmp_path / "findings.json"
    found.write_text('{"findings": []}')
    code, _, err = recorded_cli(capsys, "--kind", "research", "--round", "1", "--commit", "a" * 40, "--reviewers", "research", "--findings", str(found))
    assert code == 2 and "not a research record" in err
    body = tmp_path / "spec.md"
    body.write_text("A spec.\n")
    code, _, err = recorded_cli(capsys, "--kind", "research", "--round", "1", "--body", str(body), "--reviewers", "research", "--clean")
    assert code == 2 and "a research record names a commit" in err


def test_the_reader_reads_no_research_record_with_rule_2_fields():
    line = f"<!-- workflow:review kind=research round=1 commit={'a' * 40} reviewers=research rule=2 findings=0 outcomes=0 split=no result=clean -->"
    assert reviews.records_in(line + "\n<!-- workflow:agent -->\n") == []


def test_a_hand_off_never_takes_a_research_record_for_the_last_review():
    from workflow import handoff

    with pytest.raises(handoff.HandOffError, match="holds no review record"):
        handoff.last_record(record(1, note()))


# ---------- merge-check on a pull request of research notes (seam 1) ----------


def test_no_record_is_not_yet_it_needs_its_research_check(project, capsys):
    got = judged(project, capsys, pr(note()))
    assert got["decision"] == "not_yet"
    [r] = got["reasons"]
    assert (r["id"], r["next"], r["implements"], r["action"]) == ("research_none", "research_check", "flow §4.4", "review")


def test_the_research_check_clean_with_no_change_since_is_ready(project, capsys):
    got = judged(project, capsys, pr(note(), record(1, note())))
    assert got["decision"] == "ready", got["reasons"]
    assert "research_judged" in note_ids(got)


def test_the_research_check_not_clean_needs_the_look(project, capsys):
    got = judged(project, capsys, pr(note(), record(1, note(), clean=False)))
    [r] = got["reasons"]
    assert (r["id"], r["next"], r["round"], r["reviewers"]) == ("research_needs_look", "look", 1, ["research"])
    assert "wasn't clean" in r["wording"]["developer"]["message"]


@pytest.mark.parametrize("since", [marked, changed])
def test_any_change_since_the_research_check_needs_the_look_even_marks(project, capsys, since):
    for clean in (True, False):
        got = judged(project, capsys, pr(note(since()), record(1, note(), commit=EARLIER, clean=clean)))
        [r] = got["reasons"]
        assert r["id"] == "research_needs_look" and r["next"] == "look"
        if clean:
            assert "aren't the ones it read" in r["wording"]["developer"]["message"]


def test_the_research_check_on_an_earlier_commit_with_the_same_changes_is_ready(project, capsys):
    # A change taken out again: the head's own changes are the record's.
    got = judged(project, capsys, pr(note(), record(1, note(), commit=EARLIER)))
    assert got["decision"] == "ready", got["reasons"]


def test_a_research_record_without_hashes_covers_only_its_own_commit(project, capsys):
    assert judged(project, capsys, pr(note(), record(1, note(), hashed=False)))["decision"] == "ready"
    got = judged(project, capsys, pr(note(), record(1, note(), commit=EARLIER, hashed=False)))
    assert ids(got) == ["research_needs_look"]


@pytest.mark.parametrize("clean", [True, False])
def test_the_look_with_no_change_since(project, capsys, clean):
    got = judged(project, capsys, pr(note(), record(1, note(), commit=EARLIER, clean=False), record(2, note(), clean=clean)))
    if clean:
        assert got["decision"] == "ready", got["reasons"]
    else:
        [r] = got["reasons"]
        assert (r["id"], r["next"], r["round"]) == ("research_needs_marks", "mark", 2)
        assert research_pr.MARK in r["wording"]["new"]["fix"]


@pytest.mark.parametrize("clean", [True, False])
def test_the_look_then_marks_only_is_ready(project, capsys, clean):
    at_look = note()
    data = pr(note(marked()), record(2, at_look, commit=EARLIER, clean=clean))
    got = judged(project, capsys, data, compared(at_look, EARLIER))
    assert got["decision"] == "ready", got["reasons"]
    [n] = [n for n in got["notes"] if n["id"] == "research_judged"]
    assert "1 mark added since" in n["message"]


@pytest.mark.parametrize("clean", [True, False])
@pytest.mark.parametrize("since", [lambda: changed(), lambda: changed(marked())])
def test_the_look_then_more_than_marks_is_not_ready(project, capsys, clean, since):
    at_look = note()
    got = judged(project, capsys, pr(note(since()), record(2, at_look, commit=EARLIER, clean=clean)), compared(at_look, EARLIER))
    [r] = got["reasons"]
    assert (r["id"], r["next"]) == ("research_more_than_marks", "take_out")
    assert f"`{NOTE_PATH}`" in r["wording"]["developer"]["message"]


def test_a_new_file_after_the_look_is_more_than_marks(project, capsys):
    at_look = note()
    files = at_look + [added("docs/research/booking-ahead/questions.md", "One more thing.\n")]
    got = judged(project, capsys, pr(files, record(2, at_look, commit=EARLIER, clean=False)), compared(at_look, EARLIER))
    assert ids(got) == ["research_more_than_marks"]


def test_a_mark_taken_off_after_the_look_is_more_than_marks(project, capsys):
    at_look = note(marked())
    got = judged(project, capsys, pr(note(), record(2, at_look, commit=EARLIER)), compared(at_look, EARLIER))
    assert ids(got) == ["research_more_than_marks"]


def test_a_change_taken_out_again_after_the_look_is_ready(project, capsys):
    # EARLIER: the look; MIDDLE: a change; HEAD: the change taken out. The own changes are the look's again.
    commits = ((EARLIER, (FORK,)), (MIDDLE, (EARLIER,)), (HEAD, (MIDDLE,)))
    got = judged(project, capsys, pr(note(), record(2, note(), commit=EARLIER, clean=True), commits=commits))
    assert got["decision"] == "ready", got["reasons"]
    # And the same with the marks the look asked for left in: only marks are left since.
    got = judged(project, capsys, pr(note(marked()), record(2, note(), commit=EARLIER, clean=False), commits=commits), compared(note(), EARLIER))
    assert got["decision"] == "ready", got["reasons"]


def test_a_merge_of_the_base_before_the_marks_leaves_the_record_as_it_was(project, capsys):
    commits = ((EARLIER, (FORK,)), (HEAD, (EARLIER, BASE_TIP)))
    for rnd in (1, 2):
        got = judged(project, capsys, pr(note(), record(rnd, note(), commit=EARLIER), commits=commits))
        assert got["decision"] == "ready", got["reasons"]
    got = judged(project, capsys, pr(note(), record(2, note(), commit=EARLIER, clean=False), commits=commits))
    assert ids(got) == ["research_needs_marks"]  # the merge added no mark


def test_a_merge_of_the_base_after_the_marks_is_still_marks_only(project, capsys):
    commits = ((EARLIER, (FORK,)), (MIDDLE, (EARLIER,)), (HEAD, (MIDDLE, BASE_TIP)))
    got = judged(project, capsys, pr(note(marked()), record(2, note(), commit=EARLIER, clean=False), commits=commits), compared(note(), EARLIER))
    assert got["decision"] == "ready", got["reasons"]


def test_a_mark_on_a_line_the_pull_request_otherwise_leaves_alone_counts():
    """A note updated in place: the claim's line is one the pull request didn't change, so its patch shows it
    removed and added back marked."""
    from workflow.small import Change

    ctx = " Line 1.\n Line 2.\n Line 3.\n"
    was = Change(NOTE_PATH, None, "modified", 1, 1, "1" * 40, "@@ -1,6 +1,6 @@\n Status: current\n-Last checked: 2026-10-01\n+Last checked: 2026-11-07\n Issue: #42\n" + ctx.rstrip("\n"))
    far = f"@@ -20,7 +20,7 @@\n a\n b\n c\n-{CLAIM}\n+{MARKED}\n d\n e\n f"
    now = Change(NOTE_PATH, None, "modified", 2, 2, "2" * 40, was.patch + "\n" + far)
    assert research_pr.since([was], [now]) == research_pr.Since("marks", 1)
    # A line moved instead: more than marks.
    moved = Change(NOTE_PATH, None, "modified", 2, 2, "2" * 40, was.patch + "\n" + f"@@ -20,7 +20,7 @@\n a\n b\n-c\n-{CLAIM}\n+{MARKED}\n+c\n d\n e\n f")
    assert research_pr.since([was], [moved]).kind == "more"


def _c(status, patch=None, sha="1" * 40, path=NOTE_PATH, previous=None):
    from workflow.small import Change

    return Change(path, previous, status, 0, 0, sha, patch)


def test_a_file_with_no_patch_is_the_same_only_by_its_blob_or_removed():
    since = research_pr.since
    assert since([_c("added", sha="a" * 40)], [_c("added", sha="b" * 40)]).kind == "more"
    assert since([_c("added", sha="a" * 40)], [_c("added", sha="a" * 40)]) == research_pr.Since("none")
    assert since([_c("removed", sha=None)], [_c("removed", sha=None)]) == research_pr.Since("none")


def test_a_status_that_differs_is_more_than_marks():
    patch = "@@ -1 +1 @@\n-a\n+b"
    got = research_pr.since([_c("modified", patch)], [_c("renamed", patch, previous="docs/research/old.md")])
    assert got.kind == "more" and got.files == (NOTE_PATH,)
    assert research_pr.since([_c("modified", patch)], [_c("renamed", patch)]).kind == "more"


@pytest.mark.parametrize("bad", [
    "@@ -1,3 +1,2 @@\n a\n-b\n+c",  # the header's counts and its lines don't agree
    "@@ -1 +1 @@\n-a\n+b\n*c",  # a line starting with another character
    "@@ -1 +1 @@\n-a\n+b\n@@ nothing @@",  # a header it can't read
    "-a\n+b",  # no hunk first
])
def test_a_patch_it_cant_read_is_more_than_marks(bad):
    good = "@@ -1 +1 @@\n-a\n+b"
    assert research_pr.since([_c("modified", good)], [_c("modified", good)]) == research_pr.Since("none")
    assert research_pr.since([_c("modified", good)], [_c("modified", bad)]).kind == "more"
    assert research_pr.since([_c("modified", bad)], [_c("modified", good)]).kind == "more"


def test_a_mark_on_a_last_line_with_no_newline_counts():
    end = "\n\\ No newline at end of file"
    was = _c("modified", "@@ -1,2 +1,2 @@\n a\n-b" + end + f"\n+{CLAIM}" + end)
    now = _c("modified", "@@ -1,2 +1,2 @@\n a\n-b" + end + f"\n+{MARKED}" + end)
    assert research_pr.since([was], [now]) == research_pr.Since("marks", 1)
    # The newline added with the mark: more than marks.
    now = _c("modified", "@@ -1,2 +1,2 @@\n a\n-b" + end + f"\n+{MARKED}")
    assert research_pr.since([was], [now]).kind == "more"


def test_a_pure_deletion_the_same_on_both_sides_is_no_change():
    gone = _c("modified", "@@ -3,2 +2,0 @@\n-x\n-y")
    assert research_pr.since([gone], [gone]) == research_pr.Since("none")
    # One line more deleted at the head: more than marks.
    assert research_pr.since([gone], [_c("modified", "@@ -3,3 +2,0 @@\n-x\n-y\n-z")]).kind == "more"


def test_the_look_without_its_commits_changes_cant_be_judged(project, capsys):
    at_look = note()
    data = pr(note(marked()), record(2, at_look, commit=EARLIER, clean=False))
    got = judged(project, capsys, data)
    [r] = [r for r in got["reasons"] if r["id"] == "couldnt_read"]
    assert r["input"] == "recorded" and EARLIER in r["wording"]["developer"]["message"]
    # Another commit's changes don't hash as the record says.
    got = judged(project, capsys, data, compared(note(changed()), EARLIER))
    [r] = [r for r in got["reasons"] if r["id"] == "couldnt_read"]
    assert r["input"] == "recorded" and "don't hash as the research record" in r["wording"]["developer"]["message"]
    assert got["decision"] == "not_yet"
    # Its files alone, as a list, read too.
    assert judged(project, capsys, data, at_look)["decision"] == "ready"


def test_a_comparison_of_300_files_may_leave_some_out_so_it_isnt_read(project, capsys):
    data = pr(note(marked()), record(2, note(), commit=EARLIER, clean=False))
    many = note() + [added(f"docs/research/more/{i}.md", f"Line {i}.\n") for i in range(merge.MAX_COMPARED_FILES - 2)]
    assert len(many) == 300
    got = judged(project, capsys, data, compared(many, EARLIER))
    [r] = [r for r in got["reasons"] if r["id"] == "couldnt_read"]
    assert r["input"] == "recorded" and "at most 300 files" in r["wording"]["developer"]["message"]
    assert got["decision"] == "not_yet"
    # One fewer is read, and judged by its hashes.
    got = judged(project, capsys, data, compared(many[:-1], EARLIER))
    [r] = [r for r in got["reasons"] if r["id"] == "couldnt_read"]
    assert "don't hash as the research record" in r["wording"]["developer"]["message"]


def test_the_look_with_no_hashes_on_another_commit_cant_tell_what_changed(project, capsys):
    got = judged(project, capsys, pr(note(marked()), record(2, note(), commit=EARLIER, clean=False, hashed=False)))
    [r] = got["reasons"]
    assert r["id"] == "research_more_than_marks" and "names no hashes" in r["wording"]["developer"]["message"]


def test_the_latest_record_is_latest_by_the_pull_requests_history_then_by_posting(project, capsys):
    # The look on the head, then a research check for an older commit posted late: the look decides.
    got = judged(project, capsys, pr(note(), record(2, note()), record(1, note(), commit=EARLIER, clean=False)))
    assert got["decision"] == "ready", got["reasons"]
    # Two records on the head: the one posted last decides.
    got = judged(project, capsys, pr(note(), record(1, note()), record(1, note(), clean=False)))
    assert ids(got) == ["research_needs_look"]


def test_a_record_whose_claims_quote_a_code_fence_counts_when_it_comes_first(project, capsys):
    claims = "Claims found wrong:\n- paragraph 2 says 60 days:\n\n```text\nYou can book a table up to 60 days ahead.\n```\n"
    first = record(1, note()) + "\n" + claims
    assert judged(project, capsys, pr(note(), first))["decision"] == "ready"
    after = claims + "\n" + record(1, note())
    assert ids(judged(project, capsys, pr(note(), after))) == ["research_none"]


def test_records_from_accounts_without_write_access_dont_count(project, capsys):
    data = pr(note(), record(1, note()), authors={0: "stranger"})
    got = judged(project, capsys, data)
    assert ids(got) == ["research_none"] and "records_ignored" in note_ids(got)
    data = pr(note(), record(1, note()), record(2, note(), clean=False), authors={1: "stranger"})
    assert judged(project, capsys, data)["decision"] == "ready"  # the stranger's look doesn't count


def test_a_record_naming_a_commit_outside_the_pull_request_doesnt_count(project, capsys):
    got = judged(project, capsys, pr(note(), record(1, note(), commit="c" * 40)))
    assert ids(got) == ["research_none"] and "records_ignored" in note_ids(got)


def test_review_rounds_dont_count_on_a_pull_request_of_research_notes(project, capsys):
    rnd = reviews.record(kind="round", round=1, commit=HEAD, reviewers="standards,spec,correctness", clean=True)
    got = judged(project, capsys, pr(note(), rnd))
    assert ids(got) == ["research_none"] and "panel_records_ignored" in note_ids(got)


def _behind(d):
    d["compare"]["behind_by"] = 2


def _failed(d):
    d["checks"]["check_runs"] = [run_("tests", "failure")]


def _draft(d):
    d["pr"]["draft"] = True


def _conflict(d):
    d["pr"]["mergeable"] = False


def _thread(d):
    d["threads"] = {"totalCount": 1, "nodes": [{"isResolved": False, "comments": {"nodes": [{"author": {"login": "dev"}}]}}]}


def _changes_requested(d):
    d["reviews"] = [{"user": {"login": "dev"}, "state": "CHANGES_REQUESTED", "submitted_at": "2026-10-16T10:00:00Z"}]


@pytest.mark.parametrize("change, rid", [
    (_failed, "checks_failed"), (_behind, "behind"), (_draft, "draft"), (_conflict, "conflict"),
    (_thread, "unresolved_threads"), (_changes_requested, "changes_requested"),
])
def test_items_1_to_3_and_30s_conditions_still_apply(project, capsys, change, rid):
    data = pr(note(), record(1, note()))
    change(data)
    assert ids(judged(project, capsys, data)) == [rid]


def test_the_evidence_is_still_required_where_the_profile_says(project, capsys):
    project.write(checks=(), none=True)
    data = pr(note(), record(1, note()))
    data["rulesets"], data["checks"] = [], {"total_count": 0, "check_runs": []}
    assert ids(judged(project, capsys, data)) == ["evidence_missing"]


@pytest.mark.parametrize("other", [
    {"filename": "src/app.py", "status": "modified", "additions": 1, "deletions": 1, "sha": "3" * 40, "patch": "@@ -1 +1 @@\n-a\n+b"},
    {"filename": "docs/researchers.md", "status": "added", "additions": 1, "deletions": 0, "sha": "3" * 40, "patch": "@@ -0,0 +1 @@\n+x"},
    {"filename": "docs/research/booking-ahead/notes.md", "previous_filename": "docs/notes.md", "status": "renamed", "additions": 0, "deletions": 0, "sha": "3" * 40},
])
def test_a_pull_request_with_any_other_file_gets_the_normal_rule_and_its_research_records_dont_count(project, capsys, other):
    files = note() + [other]
    got = judged(project, capsys, pr(files, record(1, files)))
    assert ids(got) == ["no_review"] and "research_records_ignored" in note_ids(got)
    rnd = reviews.record(kind="round", round=1, commit=HEAD, reviewers="standards,spec,correctness", clean=True)
    got = judged(project, capsys, pr(files, record(1, files, clean=False), rnd))
    assert got["decision"] == "ready", got["reasons"]


def test_files_it_cant_read_give_only_their_own_reason(project, capsys):
    """Whether the pull request is one of research notes can't be told, so
    neither rule's advice is given, and nothing is said about where its files are."""
    data = pr(note(), record(1, note()))
    data["pr"]["changed_files"] = 5  # GitHub's list left 3 out
    got = judged(project, capsys, data)
    assert ids(got) == ["couldnt_read"]
    assert got["reasons"][0]["input"] == "files"
    assert "research_records_ignored" not in note_ids(got)
    assert got["decision"] == "not_yet"


def test_a_pull_request_with_no_files_says_nothing_of_files_outside_the_research_folder(project, capsys):
    got = judged(project, capsys, pr([], record(1, note())))
    assert "research_records_ignored" not in note_ids(got)
    assert got["decision"] == "not_yet"


@pytest.mark.parametrize("path, research", [
    ("docs/research/booking-ahead/note.md", True),
    ("docs/research/x", True),
    ("docs/research/", False),
    ("docs/research/../flow.md", False),
    ("docs/research//note.md", False),
    ("docs/researchers/note.md", False),
    ("./docs/research/note.md", False),
])
def test_what_counts_as_a_research_note(path, research):
    assert research_pr.is_research([path]) is research
    assert research_pr.is_research([]) is False


# ---------- --fetch fetches the record's commit's changes only when needed ----------


def _fetch_routes(data):
    r = routes(data)
    r[f"{REPO}/compare/main...{EARLIER}"] = compared(note(), EARLIER)
    return r


def test_fetch_reads_the_looks_commits_changes_when_marks_follow_it(project, capsys, tmp_path, monkeypatch):
    data = pr(note(marked()), record(2, note(), commit=EARLIER, clean=False))
    gh = fake_gh.install(tmp_path, monkeypatch, _fetch_routes(data))
    got, code = run(project, capsys, {}, "--fetch", "12")
    assert code == 0 and got["decision"] == "ready", got["reasons"]
    assert f"{REPO}/compare/main...{EARLIER}" in [p.split("?")[0] for p in gh.paths()]


@pytest.mark.parametrize("data", [
    pr(note(), record(1, note(), commit=EARLIER)),  # a research check: any change needs the look
    pr(note(), record(2, note())),  # the look on the head
    pr(note() + [{"filename": "src/app.py", "status": "added", "additions": 0, "deletions": 0, "sha": "3" * 40}], record(2, note(), commit=EARLIER)),
])
def test_fetch_reads_nothing_more_when_its_not_needed(project, capsys, tmp_path, monkeypatch, data):
    gh = fake_gh.install(tmp_path, monkeypatch, _fetch_routes(data))
    run(project, capsys, {}, "--fetch", "12")
    assert f"{REPO}/compare/main...{EARLIER}" not in [p.split("?")[0] for p in gh.paths()]


def test_fetch_that_fails_says_so_never_ready(project, capsys, tmp_path, monkeypatch):
    data = pr(note(marked()), record(2, note(), commit=EARLIER, clean=False))
    r = routes(data)  # no route for the comparison: GitHub's 404
    fake_gh.install(tmp_path, monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    [x] = [x for x in got["reasons"] if x["id"] == "couldnt_read"]
    assert x["input"] == "recorded" and "HTTP 404" in x["wording"]["developer"]["message"]
    assert got["decision"] == "not_yet"


# ---------- seam 2: the text ----------


def test_the_marks_fixture_is_copied_from_the_study_skill():
    """The fixture is the example line the skill shows under "The mark", and
    `merge-check`'s mark is the one the skill writes down."""
    text = SKILL.read_text(encoding="utf-8")
    m = re.search(r"\*\*The mark\.\*\*[^\n]*:\n\n```markdown\n(.*?)\n```", text, re.S)
    assert m, "the study skill shows no example of the mark"
    assert (FIX / "marked-line.md").read_text(encoding="utf-8") == m.group(1) + "\n"
    assert f"the mark `{research_pr.MARK}`" in re.sub(r"\s+", " ", text)
    assert MARKED.endswith(research_pr.MARK) and CLAIM in NOTE.splitlines()


def _item_4():
    flow = (KIT / "docs/flow.md").read_text(encoding="utf-8")
    section = flow[flow.index("## 4. The merge rule"):flow.index("## 5.")]
    item = section[section.index("4. **The reviews are clean**"):section.index("This section is the merge rule's one source")]
    return re.sub(r"\s+", " ", item)


def test_flow_4_item_4_carries_the_research_rule():
    item = _item_4()
    # F6's text.
    assert "a pull request whose files are all research notes counts its research check record as its clean review; items 1 to 3 still apply" in item
    assert "`docs/research/`" in item
    # The look, the mark, and only marks after the look.
    assert "the look at a fix" in item and "`workflow review-record --kind research`" in item
    assert f"The mark is `{research_pr.MARK}`, added at the end of the line" in item
    assert "Only marks after the look" in item
    assert "research records count nowhere else" in item


def test_the_merge_check_skill_says_research_none_carries_only_its_next(project, capsys):
    """The skill's "Read the answer" says which research reasons carry a
    round: all but `research_none`, which has no record to count."""
    text = re.sub(r"\s+", " ", (KIT / "skills/merge-check/SKILL.md").read_text(encoding="utf-8"))
    assert "each with its `next`, and all but `research_none` (no research record yet) with its `round`" in text
    assert "the research ones, each with its `round`" not in text
    [r] = judged(project, capsys, pr(note()))["reasons"]
    assert r["id"] == "research_none" and "round" not in r and "reviewers" not in r
    [r] = judged(project, capsys, pr(note(), record(1, note(), clean=False)))["reasons"]
    assert (r["round"], r["reviewers"]) == (1, ["research"])


def test_merge_checks_research_rule_names_that_item():
    [rule] = [r for r in merge.RULES if r.judge is merge._panel]
    assert rule.implements == "flow §4.4"
    for rid in ("research_none", "research_needs_look", "research_needs_marks", "research_more_than_marks"):
        assert merge.REASONS[rid].rule == rule.id


# ---------- end to end: the record from git, merge-check from GitHub's files ----------


def _github(root, commit):
    """The pull request's own changes at `commit`, as GitHub's list of files gives them."""
    out = []
    for c in own_changes.local_files(root, commit, "origin/main"):
        plus = sum(1 for line in (c.patch or "").splitlines() if line.startswith("+"))
        minus = sum(1 for line in (c.patch or "").splitlines() if line.startswith("-"))
        out.append({"filename": c.path, **({"previous_filename": c.previous} if c.previous else {}), "status": c.status,
                    "additions": plus, "deletions": minus, "sha": c.sha, **({"patch": c.patch.rstrip("\n")} if c.patch else {})})
    return out


@pytest.fixture
def notes_branch(tmp_path, monkeypatch, _no_user_git_config):
    """A checkout whose `origin` is a local bare repository, on a branch that
    updates a note already on main (in place) and adds its saved copy."""
    origin, root = tmp_path / "origin.git", tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(root))
    git(root, "checkout", "-q", "-b", "main")
    (root / ".claude/workflow").mkdir(parents=True)
    (root / ".claude/workflow/profile.toml").write_text('[project]\nname = "demo"\nrepo = "acme/demo"\nbase_branch = "main"\n')
    (root / "docs/research/booking-ahead/sources").mkdir(parents=True)
    (root / NOTE_PATH).write_text(NOTE.replace("2026-11-07", "2026-10-01"))
    commit_all(root, "base")
    git(root, "push", "-q", "origin", "main")
    git(root, "checkout", "-q", "-b", "claude/research-booking-ahead")
    (root / NOTE_PATH).write_text(NOTE)
    (root / SAVED_PATH).write_text(SAVED)
    commit_all(root, "the note, checked again")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.chdir(root)
    return root


@pytest.mark.parametrize("mark, want", [(True, "ready"), (False, "research_needs_marks")])
def test_end_to_end_the_look_from_git_then_the_mark(notes_branch, project, capsys, monkeypatch, mark, want):
    root = notes_branch
    look = git(root, "rev-parse", "HEAD")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))  # the record is written in the checkout
    code, body, err = recorded_cli(capsys, "--kind", "research", "--round", "2", "--commit", look, "--reviewers", "research", "--not-clean")
    assert code == 0, err
    assert reviews.records_in(body)[0].diff == hashes(_github(root, look)).diff  # git's hash is GitHub's
    if mark:
        (root / NOTE_PATH).write_text(marked())  # the claim's line is one this branch left as it was on main
    else:
        (root / NOTE_PATH).write_text(NOTE + "\n")  # some other change: no mark
        want = "research_more_than_marks"
    head = commit_all(root, "after the look")
    files, at_look = _github(root, head), _github(root, look)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    data = pr(files, body, commits=((look, (FORK,)), (head, (look,))))
    data["pr"]["head"]["sha"] = head
    data["checks"]["check_runs"] = [run_("tests", sha=head)]
    data["compare"]["url"] = f"https://api.github.com/repos/acme/demo/compare/main...{head}"
    got = judged(project, capsys, data, compared(at_look, look))
    if want == "ready":
        assert got["decision"] == "ready", got["reasons"]
    else:
        [r] = got["reasons"]
        assert r["id"] == want and "case" not in r and f"`{NOTE_PATH}`" in r["wording"]["developer"]["message"]
