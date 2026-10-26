"""`workflow merge-check` carries a review over a merge of the base (#261,
from #255's seams 1 and 5; #253's answers 4, 11 and 23).

Each round and pass record names two hashes of the pull request's own changes
at its commit (#258): `diff`, with their context lines, and `lines`, of the
changed lines alone. `merge-check` computes the head's from GitHub's per-file
data (`--files`: each file's `status`, `sha` and `patch`) and shows them as
`head_hashes`.
- **The carry-over:** when the head is a merge of the base (two or more
  parents, one outside the pull request's commits, read from `--commits`) and
  isn't the last counted review's commit, but its `diff` hash is that
  review's, that review covers the head, with its result, clean or not. No
  pass is needed.
- **The cap:** a pass doesn't count toward `--review-passes` when its commit
  is a merge of the base, the last counted review before it (by the pull
  request's history) was clean, and its `lines` hash is that review's. A pass
  that rechecks open findings always counts.
- A record without the hashes, or with `unknown`, covers only its own commit,
  and its passes count.
"""

import re
from pathlib import Path

from test_merge_check import EARLIER, HEAD, check, comment, ids, inputs, note_ids, project  # noqa: F401 (project is a fixture)
from test_review_record_hashes import checkout, git, recorded, rest_files  # noqa: F401 (checkout is a fixture)
from changelog_notes import since_0110
from workflow import merge, reviews

KIT = Path(__file__).resolve().parents[1]
MIDDLE = "e" * 40  # a commit of the PR between EARLIER and HEAD
BASE_TIP = "f" * 40  # the base branch's head, outside the PR
FORK_POINT = "9" * 40  # where the PR's branch left the base

# src/app.py's hunk as the reviews saw it, then as merges of the base left it.
REVIEWED = "@@ -4,7 +4,7 @@ def f():\n line 4\n line 5\n line 6\n-line 7\n+line seven\n line 8\n line 9\n line 10"
# The base added lines above the hunk: its numbers moved, its own changes didn't.
ELSEWHERE = "@@ -14,7 +14,7 @@ def f():\n line 4\n line 5\n line 6\n-line 7\n+line seven\n line 8\n line 9\n line 10"
# The base changed a line within 3 lines of the hunk: the context differs, the changed lines don't.
CONTEXT = "@@ -4,7 +4,7 @@ def f():\n line 4\n line five\n line 6\n-line 7\n+line seven\n line 8\n line 9\n line 10"
# A conflict resolved by changing the PR's own line.
RESOLVED = "@@ -4,7 +4,7 @@ def f():\n line 4\n line 5\n line 6\n-line 7\n+line SEVEN\n line 8\n line 9\n line 10"


def files(patch):
    return [{"filename": "src/app.py", "status": "modified", "additions": 1, "deletions": 1, "sha": "1" * 40, "patch": patch}]


def pr(patch, *commits, parents=True):
    """The pull request at HEAD with `src/app.py`'s `patch`, and `commits` as
    (sha, parents) in order; `parents=False` gives them without parents."""
    data = inputs()
    data["files"] = files(patch)
    data["commits"] = [{"sha": s, **({"parents": [{"sha": p} for p in ps]} if parents else {})} for s, ps in commits]
    data["pr"]["commits"] = len(commits)
    data["compare"]["commits"] = [{"sha": s} for s, _ in commits]
    data["compare"]["ahead_by"] = len(commits)
    return data


def merged_in(patch, **kw):
    """EARLIER, MIDDLE, then HEAD: a merge of the base (BASE_TIP) into MIDDLE."""
    return pr(patch, (EARLIER, [FORK_POINT]), (MIDDLE, [EARLIER]), (HEAD, [MIDDLE, BASE_TIP]), **kw)


def fixed(patch, **kw):
    """EARLIER, MIDDLE, then HEAD: a fix commit on MIDDLE, not a merge."""
    return pr(patch, (EARLIER, [FORK_POINT]), (MIDDLE, [EARLIER]), (HEAD, [MIDDLE]), **kw)


def hashes_of(project, capsys, patch):
    """`merge-check --json`'s head hashes for a pull request with this patch."""
    got, _ = check(project, capsys, pr(patch, (EARLIER, [FORK_POINT]), (HEAD, [EARLIER])))
    return got["head_hashes"]["diff"], got["head_hashes"]["lines"]


def hashed(kind="round", rnd=1, commit=EARLIER, clean=True, hashes=(None, None)):
    who = "correctness" if kind == "pass" else "standards,spec,correctness"
    return reviews.record(kind=kind, round=rnd, commit=commit, reviewers=who, clean=clean, diff=hashes[0], lines=hashes[1])


def records(*recs):
    return [comment(r, cid=i + 1) for i, r in enumerate(recs)]


def review_reasons(got):
    return [r for r in got["reasons"] if r["rule"] == "review_panel"]


# ---------- the head's hashes in --json ----------


def test_json_shows_the_heads_hashes(project, capsys):
    diff, lines = hashes_of(project, capsys, REVIEWED)
    assert re.fullmatch(r"[0-9a-f]{64}", diff) and re.fullmatch(r"[0-9a-f]{64}", lines) and diff != lines
    assert hashes_of(project, capsys, ELSEWHERE) == (diff, lines)
    assert hashes_of(project, capsys, CONTEXT)[0] != diff and hashes_of(project, capsys, CONTEXT)[1] == lines
    assert hashes_of(project, capsys, RESOLVED)[0] != diff and hashes_of(project, capsys, RESOLVED)[1] != lines


def test_a_file_with_changes_but_no_patch_makes_them_unknown(project, capsys):
    data = inputs()  # files with no patch and no blob SHA, as gh's list gives them
    got, _ = check(project, capsys, data)
    assert got["head_hashes"] == {"diff": "unknown", "lines": "unknown"}
    data["files"] = [{"filename": "big.sql", "status": "modified", "additions": 5000, "deletions": 0, "sha": "1" * 40}]
    got, _ = check(project, capsys, data)
    assert got["head_hashes"] == {"diff": "unknown", "lines": "unknown"}


def test_a_file_with_no_patch_and_no_counts_makes_them_unknown(project, capsys):
    data = inputs()
    for patch in ({}, {"patch": ""}):
        data["files"] = [{"filename": "src/app.py", "status": "modified", "sha": "1" * 40, **patch}]
        got, _ = check(project, capsys, data)
        assert got["head_hashes"] == {"diff": "unknown", "lines": "unknown"}


def test_files_that_cant_be_read_make_them_unknown(project, capsys):
    got, _ = check(project, capsys, inputs(), leave_out=("files",))
    assert got["head_hashes"] == {"diff": "unknown", "lines": "unknown"}


def test_a_patch_that_isnt_text_cant_be_read(project, capsys):
    data = inputs()
    data["files"] = [{"filename": "src/app.py", "status": "modified", "additions": 1, "deletions": 1, "sha": "1" * 40, "patch": 7}]
    got, _ = check(project, capsys, data)
    assert "couldnt_read" in ids(got) and got["head_hashes"] == {"diff": "unknown", "lines": "unknown"}


def test_text_the_hash_cant_encode_makes_them_unknown_never_a_traceback(project, capsys):
    surrogate = '[{"filename": "src/app.py", "status": "modified", "additions": 1, "deletions": 1, "sha": "' + "1" * 40 + '", "patch": "@@ -1 +1 @@\\n-a\\n+\\ud800"}]'
    for comments in ([], None):  # with and without a counted round
        data = inputs()
        if comments is not None:
            data["comments"] = comments
        got, code = check(project, capsys, data, raw={"files": surrogate})
        assert code == 0 and got["head_hashes"] == {"diff": "unknown", "lines": "unknown"}


# ---------- the carry-over ----------


def test_a_free_base_merge_with_the_same_diff_hash_is_ready_with_no_pass(project, capsys):
    reviewed = hashes_of(project, capsys, REVIEWED)
    data = merged_in(ELSEWHERE)
    data["comments"] = records(hashed(rnd=1, commit=MIDDLE, hashes=reviewed))
    got, _ = check(project, capsys, data, "--review-passes", "0")
    assert got["decision"] == "ready", got["reasons"]
    assert "review_carried" in note_ids(got)


def test_a_clean_pass_carries_over_too(project, capsys):
    reviewed = hashes_of(project, capsys, REVIEWED)
    data = merged_in(ELSEWHERE)
    data["comments"] = records(hashed(rnd=3, commit=EARLIER, clean=False), hashed("pass", rnd=3, commit=MIDDLE, hashes=reviewed))
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]


def test_after_a_pass_that_wasnt_clean_it_stays_not_clean(project, capsys):
    reviewed = hashes_of(project, capsys, REVIEWED)
    data = merged_in(ELSEWHERE)
    data["comments"] = records(hashed(rnd=1, commit=EARLIER, hashes=reviewed), hashed("pass", rnd=1, commit=MIDDLE, clean=False, hashes=reviewed))
    got, _ = check(project, capsys, data)
    assert ids(got) == ["pass_not_clean"]


def test_after_a_last_round_that_wasnt_clean_it_stays_not_clean(project, capsys):
    reviewed = hashes_of(project, capsys, REVIEWED)
    data = merged_in(ELSEWHERE)
    data["comments"] = records(hashed(rnd=3, commit=MIDDLE, clean=False, hashes=reviewed))
    got, _ = check(project, capsys, data)
    [r] = review_reasons(got)
    assert r["id"] == "review_not_clean" and r["next"] == "pass"
    assert "review_carried" in note_ids(got)


def test_a_late_record_for_an_older_commit_never_overrides_the_heads_own_pass(project, capsys):
    reviewed = hashes_of(project, capsys, REVIEWED)
    data = merged_in(ELSEWHERE)
    data["comments"] = records(hashed(rnd=1, commit=EARLIER, hashes=reviewed), hashed("pass", rnd=1, commit=HEAD, clean=False, hashes=reviewed),
                               hashed("pass", rnd=1, commit=MIDDLE, hashes=reviewed))
    got, _ = check(project, capsys, data, "--review-passes", "3")
    assert ids(got) == ["pass_not_clean"] and "review_carried" not in note_ids(got)


def test_a_commit_that_isnt_a_merge_of_the_base_never_carries_over(project, capsys):
    # A change of mode alone on a file with hunks keeps GitHub's per-file data, and so the hashes, as they were.
    reviewed = hashes_of(project, capsys, REVIEWED)
    data = fixed(REVIEWED)
    data["comments"] = records(hashed(rnd=1, commit=MIDDLE, hashes=reviewed))
    got, _ = check(project, capsys, data)
    assert ids(got) == ["review_stale"] and "review_carried" not in note_ids(got)


def test_only_the_last_counted_review_carries_over(project, capsys):
    reviewed = hashes_of(project, capsys, REVIEWED)
    data = merged_in(ELSEWHERE)
    # The round's hash matches the head's, but a later pass (on other changes) is the last review.
    data["comments"] = records(hashed(rnd=1, commit=EARLIER, hashes=reviewed), hashed("pass", rnd=1, commit=MIDDLE, hashes=hashes_of(project, capsys, RESOLVED)))
    got, _ = check(project, capsys, data)
    assert ids(got) == ["review_stale"]


# ---------- the cap ----------


def test_a_context_only_merge_after_a_clean_review_needs_a_pass_that_doesnt_count(project, capsys):
    reviewed, context = hashes_of(project, capsys, REVIEWED), hashes_of(project, capsys, CONTEXT)
    data = merged_in(CONTEXT)
    data["comments"] = records(hashed(rnd=1, commit=MIDDLE, hashes=reviewed))
    got, _ = check(project, capsys, data, "--review-passes", "1")
    assert ids(got) == ["review_stale"]  # a pass is needed
    # Its pass doesn't count: a fix after it still has the cap's one pass.
    data = pr(RESOLVED, (EARLIER, [FORK_POINT]), (MIDDLE, [EARLIER, BASE_TIP]), (HEAD, [MIDDLE]))
    data["comments"] = records(hashed(rnd=1, commit=EARLIER, hashes=reviewed), hashed("pass", rnd=1, commit=MIDDLE, hashes=context))
    got, _ = check(project, capsys, data, "--review-passes", "1")
    assert ids(got) == ["review_stale"]
    assert "free_passes" in note_ids(got)


def test_at_the_cap_a_pass_that_wouldnt_count_is_still_asked_for(project, capsys):
    reviewed = hashes_of(project, capsys, REVIEWED)
    data = merged_in(CONTEXT)
    data["comments"] = records(hashed(rnd=1, commit=MIDDLE, hashes=reviewed))
    got, _ = check(project, capsys, data, "--review-passes", "0")
    assert ids(got) == ["review_stale"]
    data = fixed(CONTEXT)  # the same hashes on a fix commit: its pass would count
    data["comments"] = records(hashed(rnd=1, commit=MIDDLE, hashes=reviewed))
    got, _ = check(project, capsys, data, "--review-passes", "0")
    assert ids(got) == ["passes_used_up"]


def test_after_a_review_that_wasnt_clean_its_pass_counts(project, capsys):
    reviewed, context = hashes_of(project, capsys, REVIEWED), hashes_of(project, capsys, CONTEXT)
    data = pr(RESOLVED, (EARLIER, [FORK_POINT]), (MIDDLE, [EARLIER, BASE_TIP]), (HEAD, [MIDDLE]))
    data["comments"] = records(hashed(rnd=3, commit=EARLIER, clean=False, hashes=reviewed), hashed("pass", rnd=3, commit=MIDDLE, hashes=context))
    got, _ = check(project, capsys, data, "--review-passes", "1")
    assert ids(got) == ["passes_used_up"]


def test_a_pass_that_rechecks_open_findings_counts_whatever_was_posted_between(project, capsys):
    # A late clean record for an older commit, posted between a pass on the head that wasn't clean and its recheck.
    reviewed = hashes_of(project, capsys, REVIEWED)
    data = merged_in(ELSEWHERE)
    late = [hashed(rnd=1, commit=EARLIER, hashes=reviewed), hashed("pass", rnd=1, commit=HEAD, clean=False, hashes=reviewed),
            hashed("pass", rnd=1, commit=MIDDLE, hashes=reviewed)]
    data["comments"] = records(*late)
    for cap in ("0", "1"):
        got, _ = check(project, capsys, data, "--review-passes", cap)
        assert ids(got) == ["passes_used_up"], cap
    data["comments"] = records(*late, hashed("pass", rnd=1, commit=HEAD, clean=False, hashes=reviewed))
    got, _ = check(project, capsys, data, "--review-passes", "2")
    assert ids(got) == ["passes_used_up"]


def test_a_late_record_for_an_older_commit_isnt_the_review_before_a_pass(project, capsys):
    # The open findings are on an earlier merge (MIDDLE); a clean record for EARLIER, posted after them, doesn't hide them.
    reviewed, context = hashes_of(project, capsys, REVIEWED), hashes_of(project, capsys, CONTEXT)
    data = pr(CONTEXT, (EARLIER, [FORK_POINT]), (MIDDLE, [EARLIER, BASE_TIP]), (HEAD, [MIDDLE, BASE_TIP]))
    late = [hashed(rnd=1, commit=EARLIER, hashes=reviewed), hashed("pass", rnd=1, commit=MIDDLE, clean=False, hashes=context),
            hashed("pass", rnd=1, commit=EARLIER, hashes=reviewed)]
    data["comments"] = records(*late)
    got, _ = check(project, capsys, data, "--review-passes", "1")
    assert ids(got) == ["passes_used_up"]
    data["comments"] = records(*late, hashed("pass", rnd=1, commit=HEAD, clean=False, hashes=context))
    got, _ = check(project, capsys, data, "--review-passes", "2")
    assert ids(got) == ["passes_used_up"]


def test_a_fix_commit_with_the_same_lines_hash_its_pass_counts(project, capsys):
    reviewed, context = hashes_of(project, capsys, REVIEWED), hashes_of(project, capsys, CONTEXT)
    data = fixed(RESOLVED)  # MIDDLE is a fix commit, not a merge
    data["comments"] = records(hashed(rnd=1, commit=EARLIER, hashes=reviewed), hashed("pass", rnd=1, commit=MIDDLE, hashes=context))
    got, _ = check(project, capsys, data, "--review-passes", "1")
    assert ids(got) == ["passes_used_up"]


def test_commits_given_without_parents_the_pass_after_a_base_merge_counts(project, capsys):
    reviewed, context = hashes_of(project, capsys, REVIEWED), hashes_of(project, capsys, CONTEXT)
    data = pr(RESOLVED, (EARLIER, [FORK_POINT]), (MIDDLE, [EARLIER, BASE_TIP]), (HEAD, [MIDDLE]), parents=False)
    data["comments"] = records(hashed(rnd=1, commit=EARLIER, hashes=reviewed), hashed("pass", rnd=1, commit=MIDDLE, hashes=context))
    got, _ = check(project, capsys, data, "--review-passes", "1")
    assert ids(got) == ["passes_used_up"]


def test_commits_in_graphqls_shape_tell_a_merge_of_the_base(project, capsys):
    reviewed, context = hashes_of(project, capsys, REVIEWED), hashes_of(project, capsys, CONTEXT)
    data = pr(RESOLVED, (EARLIER, [FORK_POINT]), (MIDDLE, [EARLIER, BASE_TIP]), (HEAD, [MIDDLE]))
    data["commits"] = {"data": {"repository": {"pullRequest": {"commits": {"nodes": [
        {"commit": {"oid": c["sha"], "parents": {"nodes": [{"oid": p["sha"]} for p in c["parents"]]}}} for c in data["commits"]
    ], "pageInfo": {"hasNextPage": False}}}}}}
    data["comments"] = records(hashed(rnd=1, commit=EARLIER, hashes=reviewed), hashed("pass", rnd=1, commit=MIDDLE, hashes=context))
    got, _ = check(project, capsys, data, "--review-passes", "1")
    assert ids(got) == ["review_stale"] and "free_passes" in note_ids(got)


def test_with_a_page_of_commits_left_out_every_pass_counts(project, capsys):
    # GitHub lists at most 250 commits: a parent on a page left out would read as outside the pull request.
    reviewed, context = hashes_of(project, capsys, REVIEWED), hashes_of(project, capsys, CONTEXT)
    data = pr(RESOLVED, (EARLIER, [FORK_POINT]), (MIDDLE, [EARLIER, BASE_TIP]), (HEAD, [MIDDLE]))
    data["commits"] = [{"sha": f"{i:040x}", "parents": [{"sha": f"{i - 1:040x}"}]} for i in range(1, 248)] + data["commits"]
    data["pr"]["commits"] = 300
    data["comments"] = records(hashed(rnd=1, commit=EARLIER, hashes=reviewed), hashed("pass", rnd=1, commit=MIDDLE, hashes=context))
    got, _ = check(project, capsys, data, "--review-passes", "1")
    assert ids(got) == ["passes_used_up"]
    data["pr"]["commits"] = 250
    got, _ = check(project, capsys, data, "--review-passes", "1")
    assert ids(got) == ["review_stale"]


def test_at_the_cap_the_answer_says_how_many_passes_counted(project, capsys):
    reviewed, context, resolved = (hashes_of(project, capsys, p) for p in (REVIEWED, CONTEXT, RESOLVED))
    data = pr(RESOLVED, (EARLIER, [FORK_POINT]), (MIDDLE, [EARLIER, BASE_TIP]), ("8" * 40, [MIDDLE]), (HEAD, ["8" * 40, BASE_TIP]))
    data["files"] = files(REVIEWED)
    data["comments"] = records(hashed(rnd=1, commit=EARLIER, hashes=reviewed), hashed("pass", rnd=1, commit=MIDDLE, hashes=context),
                               hashed("pass", rnd=1, commit="8" * 40, hashes=resolved))
    got, _ = check(project, capsys, data, "--review-passes", "1")
    [r] = review_reasons(got)
    assert r["id"] == "passes_used_up"
    assert "(1 allowed after round 1, 1 Correctness pass counted of 2 posted)" in r["wording"]["developer"]["message"]


def test_a_merge_of_two_of_the_prs_own_commits_isnt_a_merge_of_the_base(project, capsys):
    reviewed, context = hashes_of(project, capsys, REVIEWED), hashes_of(project, capsys, CONTEXT)
    data = pr(RESOLVED, (EARLIER, [FORK_POINT]), (MIDDLE, [FORK_POINT]), ("8" * 40, [EARLIER, MIDDLE]), (HEAD, ["8" * 40]))
    data["comments"] = records(hashed(rnd=1, commit=EARLIER, hashes=reviewed), hashed("pass", rnd=1, commit="8" * 40, hashes=context))
    got, _ = check(project, capsys, data, "--review-passes", "1")
    assert ids(got) == ["passes_used_up"]


def test_a_merge_whose_conflict_resolution_changed_a_line_needs_a_pass_and_it_counts(project, capsys):
    reviewed, resolved = hashes_of(project, capsys, REVIEWED), hashes_of(project, capsys, RESOLVED)
    data = merged_in(RESOLVED)
    data["comments"] = records(hashed(rnd=1, commit=MIDDLE, hashes=reviewed))
    got, _ = check(project, capsys, data, "--review-passes", "1")
    assert ids(got) == ["review_stale"]
    got, _ = check(project, capsys, data, "--review-passes", "0")
    assert ids(got) == ["passes_used_up"]
    data = pr(CONTEXT, (EARLIER, [FORK_POINT]), (MIDDLE, [EARLIER, BASE_TIP]), (HEAD, [MIDDLE]))
    data["comments"] = records(hashed(rnd=1, commit=EARLIER, hashes=reviewed), hashed("pass", rnd=1, commit=MIDDLE, hashes=resolved))
    got, _ = check(project, capsys, data, "--review-passes", "1")
    assert ids(got) == ["passes_used_up"]


# ---------- old records ----------


def test_an_old_record_without_the_fields_covers_only_its_own_commit(project, capsys):
    data = merged_in(ELSEWHERE)
    data["comments"] = records(hashed(rnd=1, commit=MIDDLE))
    got, _ = check(project, capsys, data)
    assert ids(got) == ["review_stale"]
    data = pr(RESOLVED, (EARLIER, [FORK_POINT]), (MIDDLE, [EARLIER, BASE_TIP]), (HEAD, [MIDDLE]))
    data["comments"] = records(hashed(rnd=1, commit=EARLIER), hashed("pass", rnd=1, commit=MIDDLE))
    got, _ = check(project, capsys, data, "--review-passes", "1")
    assert ids(got) == ["passes_used_up"]


def test_unknown_covers_only_its_own_commit(project, capsys):
    unknown = ("unknown", "unknown")
    data = merged_in(ELSEWHERE)
    data["comments"] = records(hashed(rnd=1, commit=MIDDLE, hashes=unknown))
    got, _ = check(project, capsys, data)
    assert ids(got) == ["review_stale"]
    data = pr(RESOLVED, (EARLIER, [FORK_POINT]), (MIDDLE, [EARLIER, BASE_TIP]), (HEAD, [MIDDLE]))
    data["comments"] = records(hashed(rnd=1, commit=EARLIER, hashes=unknown), hashed("pass", rnd=1, commit=MIDDLE, hashes=unknown))
    got, _ = check(project, capsys, data, "--review-passes", "1")
    assert ids(got) == ["passes_used_up"]


def test_an_unknown_record_never_carries_over_to_an_unknown_head(project, capsys):
    data = merged_in(ELSEWHERE)
    del data["files"][0]["patch"]
    data["comments"] = records(hashed(rnd=1, commit=MIDDLE, hashes=("unknown", "unknown")))
    got, _ = check(project, capsys, data)
    assert got["head_hashes"]["diff"] == "unknown" and ids(got) == ["review_stale"]


def test_a_head_whose_hashes_are_unknown_gets_no_carry_over(project, capsys):
    reviewed = hashes_of(project, capsys, REVIEWED)
    data = merged_in(ELSEWHERE)
    del data["files"][0]["patch"]
    data["comments"] = records(hashed(rnd=1, commit=MIDDLE, hashes=reviewed))
    got, _ = check(project, capsys, data)
    assert ids(got) == ["review_stale"]


# ---------- both sides hash alike ----------


def test_review_record_and_merge_check_hash_a_change_alike(checkout, capsys):
    """`review-record` on a repository whose `origin` is a local bare one, and
    `merge-check` on REST-shaped files built from it: a file with several
    hunks, a rename, a binary file, an empty file and a change of mode alone."""
    head = git(checkout, "rev-parse", "HEAD")
    as_recorded = recorded(capsys, head)
    rest = []
    for path, previous, status, sha, patch in rest_files(checkout):
        changed = (patch or "").split("\n")
        rest.append({
            "filename": path, "status": status, "sha": sha or git(checkout, "rev-parse", f"origin/main:{path}"),
            "additions": sum(ln.startswith("+") for ln in changed), "deletions": sum(ln.startswith("-") for ln in changed),
            **({"previous_filename": previous} if previous else {}), **({"patch": patch} if patch else {}),
        })
    assert {f["status"] for f in rest} >= {"modified", "renamed", "added", "changed", "removed"}
    data = inputs()
    data["files"] = rest
    data["pr"]["changed_files"] = len(rest)
    got, _ = check(checkout, capsys, data)
    assert (got["head_hashes"]["diff"], got["head_hashes"]["lines"]) == as_recorded


# ---------- the kit's text (seam 5) ----------


def _read(rel):
    return (KIT / rel).read_text(encoding="utf-8")


EXCEPTION = "a merge of the base that leaves the pull request's own changes identical"


def test_the_flow_says_the_new_rule_in_3_and_4():
    flow = _read("docs/flow.md")
    s3 = flow.split("## 3. Building", 1)[1].split("\n## ", 1)[0]
    step3 = next(ln for ln in s3.splitlines() if ln.startswith("3. **Review**"))
    assert EXCEPTION in step3 and "needs CI only" in step3
    assert "run a pass only when it asks for one" in step3
    item3 = next(ln for ln in flow.splitlines() if ln.startswith("3. **The branch is level"))
    assert "runs everything again" not in item3 and "item 4" in item3
    item4 = next(ln for ln in flow.splitlines() if ln.startswith("4. **The reviews are clean**"))
    assert EXCEPTION.capitalize() in item4 or EXCEPTION in item4
    assert "carries over" in item4 and "doesn't count toward" in item4


def test_review_panel_5_says_it():
    s5 = _read("skills/review-panel/SKILL.md").split("## 5. When to stop", 1)[1].split("\n## ", 1)[0]
    assert EXCEPTION in s5 and "needs CI only" in s5
    assert "run a pass only when it asks for one" in s5


def test_build_ticket_says_it_in_its_review_step_and_checklist():
    text = _read("skills/build-ticket/SKILL.md")
    step = text.split("## 3. Review it", 1)[1].split("\n## ", 1)[0]
    assert EXCEPTION in step and "needs CI only" in step
    assert "`WF merge-check --fetch <PR> --json`" in step and "review reasons only" in step
    assert "- [ ] Review panel run in rounds until clean (or the limit, the rest raised); late commits had a Correctness pass, except a merge of the base that `merge-check` carried a review over" in text


def test_the_merge_check_skill_names_the_files_and_commits_fields():
    skill = _read("skills/merge-check/SKILL.md")
    files = next(ln for ln in skill.splitlines() if ln.startswith("| `--files` |"))
    assert "`sha`" in files and "`patch`" in files
    commits = next(ln for ln in skill.splitlines() if ln.startswith("| `--commits` |"))
    assert "`parents`" in commits
    assert "`head_hashes`" in skill


def test_the_changelog_has_the_note():
    notes = since_0110(_read("CHANGELOG.md"))
    assert "#261" in notes and "`head_hashes`" in notes


# ---------- the wording from #261's last pass (#301) ----------


def test_the_panels_docstring_says_which_review_comes_before_a_pass():
    assert "the counted review before it (the latest by the PR's history) was clean" in " ".join(merge._panel.__doc__.split())


def test_the_merge_check_skills_commits_row_says_their_order():
    skill = _read("skills/merge-check/SKILL.md")
    commits = next(ln for ln in skill.splitlines() if ln.startswith("| `--commits` |"))
    assert "oldest first, as GitHub gives them" in commits


def test_flow_4_item_4_says_a_recheck_of_open_findings_always_counts():
    item4 = next(ln for ln in _read("docs/flow.md").splitlines() if ln.startswith("4. **The reviews are clean**"))
    assert "doesn't count toward the cap (a pass that rechecks open findings always counts)" in item4
