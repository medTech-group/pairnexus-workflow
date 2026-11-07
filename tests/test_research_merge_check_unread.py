"""The research-records note, and what `merge-check` says when a pull
request's files can't be read (#538, split out of #509, spec #505).

Seam 1: the `workflow` CLI fed files, as `tests/test_research_merge_check.py`.

- With every file read and one outside `docs/research/`, a note says the
  pull request's research records were left out, and why.
- When the files can't be read (a page left out, no list at all), or the list
  is empty, no note claims files outside `docs/research/`; and when no file it
  could read is outside that folder, which rule applies can't be told, so the
  review panel's advice for a pull request with no review (`no_review`) isn't
  given beside the "couldn't read" reason.
- Every other review reason of the panel's still shows beside it: the pass cap
  (`passes_used_up`), and `review_passes` as `until-clean` under a `rule=2`
  record.
- It is never `ready` while the files can't be read.
"""

import json

import pytest

from test_merge_check import EARLIER, HEAD, ids, note_ids, project  # noqa: F401 (project is a fixture)
from test_merge_check_evidence import run
from test_research_merge_check import judged, note, pr, record
from workflow import findings, reviews

APP = {"filename": "src/app.py", "status": "modified", "additions": 1, "deletions": 1, "sha": "3" * 40, "patch": "@@ -1 +1 @@\n-a\n+b"}
NOTE_LEFT_OUT = "research_records_ignored"


def round_(commit=HEAD, clean=True):
    return reviews.record(kind="round", round=1, commit=commit, reviewers="standards,spec,correctness", clean=clean)


def pass_(commit=HEAD, clean=False):
    return reviews.record(kind="pass", round=1, commit=commit, reviewers="correctness", clean=clean)


def rule2_round(commit=HEAD):
    """A `rule=2` round with one blocking finding (#426)."""
    f = findings.load(json.dumps({"findings": [{"mark": "blocks", "mechanism": "the requeue order", "reproducer": "a PR dropped twice is requeued once"}], "outcomes": [], "split": False}))
    return reviews.record(kind="round", round=1, commit=commit, reviewers="standards,spec,correctness", clean=None, findings=f)


def partial(data, want=3):
    """GitHub's list of files left some out: the pull request says it changes `want`."""
    data["pr"]["changed_files"] = want
    return data


def unlisted(data):
    """No list of files at all."""
    del data["files"]
    return data


def files_reason(got):
    [r] = [r for r in got["reasons"] if r["id"] == "couldnt_read"]
    assert r["input"] == "files", r
    return r


# ---------- the note: research records left out, and why ----------


@pytest.mark.parametrize("files", [note() + [APP], [APP]], ids=["notes-and-code", "code"])
def test_a_pull_request_with_a_file_outside_the_research_folder_says_its_research_records_were_left_out(project, capsys, files):
    got = judged(project, capsys, pr(files, record(1, files), record(2, files)))
    assert ids(got) == ["no_review"]
    [n] = [n for n in got["notes"] if n["id"] == NOTE_LEFT_OUT]
    assert "2 research records" in n["message"] and "outside `docs/research/`" in n["message"], n


def test_with_no_research_records_nothing_is_said_of_them(project, capsys):
    got = judged(project, capsys, pr([APP], round_()))
    assert got["decision"] == "ready", got["reasons"]
    assert NOTE_LEFT_OUT not in note_ids(got)


def test_a_pull_request_of_research_notes_gets_no_such_note(project, capsys):
    got = judged(project, capsys, pr(note(), record(1, note())))
    assert got["decision"] == "ready", got["reasons"]
    assert NOTE_LEFT_OUT not in note_ids(got)


# ---------- files it can't read, or none ----------


@pytest.mark.parametrize("unread", [partial, unlisted], ids=["a-page-left-out", "no-list"])
def test_research_notes_whose_files_it_cant_read_get_no_note_and_no_panel_advice(project, capsys, unread):
    got = judged(project, capsys, unread(pr(note(), record(1, note()))))
    assert ids(got) == ["couldnt_read"], got["reasons"]
    files_reason(got)
    assert NOTE_LEFT_OUT not in note_ids(got)
    assert got["decision"] == "not_yet"


def test_an_empty_list_with_files_left_out_gets_no_note_and_no_panel_advice(project, capsys):
    got = judged(project, capsys, partial(pr([], record(1, note()))))
    assert ids(got) == ["couldnt_read"], got["reasons"]
    assert NOTE_LEFT_OUT not in note_ids(got)


def test_an_empty_list_says_nothing_of_files_outside_the_research_folder_and_gets_the_panels_rule(project, capsys):
    got = judged(project, capsys, pr([], record(1, note())))
    assert ids(got) == ["no_review"], got["reasons"]
    assert NOTE_LEFT_OUT not in note_ids(got)


def test_a_file_it_could_read_outside_the_research_folder_still_gets_the_panels_advice(project, capsys):
    got = judged(project, capsys, partial(pr([APP], record(1, [APP]))))
    assert ids(got) == ["couldnt_read", "no_review"], got["reasons"]
    files_reason(got)
    assert NOTE_LEFT_OUT not in note_ids(got)


@pytest.mark.parametrize("files", [[APP], note()[:1]], ids=["code", "a-note"])
def test_files_it_cant_read_still_show_the_pass_cap(project, capsys, files):
    """One round at --review-rounds 1, two passes that weren't clean at
    --review-passes 2, and `changed_files` 3 while the list gives 1."""
    data = partial(pr(files, round_(EARLIER), pass_(EARLIER), pass_(HEAD)))
    got, code = run(project, capsys, data, "--review-rounds", "1", "--review-passes", "2")
    assert code == 0
    assert ids(got) == ["couldnt_read", "passes_used_up"], got["reasons"]
    files_reason(got)
    assert got["review_passes"] == 2


@pytest.mark.parametrize("files", [[APP], note()[:1]], ids=["code", "a-note"])
def test_files_it_cant_read_still_show_until_clean_under_a_rule_2_record(project, capsys, files):
    data = partial(pr(files, rule2_round()))
    got, code = run(project, capsys, data, "--review-rounds", "3", "--review-passes", "2")
    assert code == 0
    assert got["review_passes"] == "until-clean", got
    assert ids(got) == ["couldnt_read", "review_not_clean"], got["reasons"]


@pytest.mark.parametrize("files", [[APP], note(), note()[:1]], ids=["code", "notes", "a-note"])
@pytest.mark.parametrize("unread", [partial, unlisted], ids=["a-page-left-out", "no-list"])
def test_never_ready_while_the_files_cant_read(project, capsys, files, unread):
    got = judged(project, capsys, unread(pr(files, round_(), record(1, files))))
    files_reason(got)
    assert got["decision"] == "not_yet"
    assert NOTE_LEFT_OUT not in note_ids(got)
