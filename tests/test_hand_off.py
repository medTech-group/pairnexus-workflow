"""The hand-off comment and the handed-off status (#371, spec #412; from #362).

A session that hands its ticket to a fresh one (restarted or stopped, a run's
end time, attended work's stop after 10 reviews) posts a hand-off comment on
the pull request (`workflow hand-off`): a plain heading, the head it covers,
the open blocking findings (a security finding by its area only), the tickets
filed, the reviews so far, and the machine line
`<!-- workflow:hand-off head=<sha> round=<n> passes=<n> -->` with the agents'
marker. `workflow merge-check --json` reports the latest trusted one as
`hand_off` until a counted review record follows it, and the Stop gate accepts
`WORKFLOW-STATUS: handed-off` without the checklist.
"""

import json

import pytest

from test_merge_check import EARLIER, HEAD, OUTSIDE, check, comment, inputs, note_ids, project, rec  # noqa: F401 (project is a fixture)
from changelog_notes import since_0110
from workflow import cli, findings, gate, handoff, merge

LINE = f"<!-- workflow:hand-off head={HEAD} round=3 passes=2 -->"


def written(tmp_path, capsys, *args, found=None):
    """`workflow hand-off`'s output and exit code, with `found` as its findings file."""
    argv = ["hand-off", *args]
    if found is not None:
        path = tmp_path / "findings.json"
        path.write_text(json.dumps(found))
        argv += ["--findings", str(path)]
    code = cli.main(argv)
    out = capsys.readouterr()
    return out.out, out.err, code


def hand_off_comment(head=HEAD, rnd=3, passes=2, **kw):
    return handoff.comment(head=head, round=rnd, passes=passes, **kw)


# ---------- the comment ----------


def test_the_comment_has_a_plain_heading_the_head_the_reviews_and_the_machine_line_with_the_marker():
    text = hand_off_comment()
    lines = text.splitlines()
    assert lines[0].startswith("## ") and "`" not in lines[0]
    assert f"`{HEAD[:7]}`" in text
    assert "3 review rounds and 2 Correctness passes" in text
    assert lines[-2:] == [LINE, "<!-- workflow:agent -->"]
    assert "Open blocking findings: none." in text and "Tickets filed: none." in text


def test_open_blocking_findings_are_listed_a_security_one_by_its_area_only():
    found = findings.load(json.dumps([
        {"mark": "blocks", "mechanism": "the requeue order", "reproducer": "a PR dropped twice is requeued once"},
        {"mark": "blocks", "mechanism": "token check", "reproducer": "SECRET-DETAIL an expired token passes", "security": "change", "area": "sign-in"},
        {"mark": "note", "mechanism": "wording"},
        {"mark": "ticket", "mechanism": "label sync", "issue": 415},
    ]))
    text = hand_off_comment(found=found)
    assert "the part `the requeue order`" in text
    assert "a security problem the change adds, in `sign-in`" in text
    assert "SECRET-DETAIL" not in text and "token check" not in text and "expired" not in text
    assert "a PR dropped twice" not in text  # no reproducer is written
    assert "wording" not in text  # a note isn't open
    assert "Tickets filed: #415." in text  # a ticket to fix it is a ticket filed


def test_tickets_filed_join_the_findings_tickets_and_splits_once_each_in_order():
    found = findings.load(json.dumps({
        "findings": [{"mark": "ticket", "mechanism": "label sync", "issue": 415}],
        "outcomes": [{"outcome": "split", "mechanism": "the preview reader", "issue": 416}],
    }))
    text = hand_off_comment(found=found, tickets=(417, 415))
    assert "Tickets filed: #415, #416, #417." in text


def test_the_cli_writes_the_comment(tmp_path, capsys):
    out, err, code = written(tmp_path, capsys, "--commit", HEAD, "--round", "3", "--passes", "2", "--tickets", "#417,418",
                             found=[{"mark": "blocks", "mechanism": "the requeue order", "reproducer": "x"}])
    assert code == 0 and not err
    assert out == hand_off_comment(found=findings.load(json.dumps([{"mark": "blocks", "mechanism": "the requeue order", "reproducer": "x"}])), tickets=(417, 418))
    assert handoff.in_text(out).head == HEAD


@pytest.mark.parametrize("args, says", [
    (("--round", "3", "--passes", "2"), "--commit"),
    (("--commit", HEAD[:7], "--round", "3", "--passes", "2"), "40-character"),
    (("--commit", HEAD, "--passes", "2"), "--round"),
    (("--commit", HEAD, "--round", "x", "--passes", "2"), "--round"),
    (("--commit", HEAD, "--round", "3"), "--passes"),
    (("--commit", HEAD, "--round", "3", "--passes", "-1"), "--passes"),
    (("--commit", HEAD, "--round", "0", "--passes", "1"), "a pass follows a round"),
    (("--commit", HEAD, "--round", "3", "--passes", "2", "--tickets", "x"), "--tickets"),
    (("--commit", HEAD, "--commit", HEAD, "--round", "3", "--passes", "2"), "once"),
])
def test_the_cli_refuses_a_malformed_flag(tmp_path, capsys, args, says):
    out, err, code = written(tmp_path, capsys, *args)
    assert code == 2 and not out and says in err


def test_the_cli_refuses_a_malformed_findings_file(tmp_path, capsys):
    out, err, code = written(tmp_path, capsys, "--commit", HEAD, "--round", "1", "--passes", "0", found=[{"mark": "blocks", "mechanism": "x"}])
    assert code == 2 and not out and "reproducer" in err


def test_no_review_yet_is_allowed():
    assert "no review yet" in hand_off_comment(rnd=0, passes=0)


# ---------- the reader ----------


def test_the_reader_takes_what_the_writer_writes():
    h = handoff.in_text(hand_off_comment())
    assert (h.head, h.round, h.passes) == (HEAD, 3, 2)


@pytest.mark.parametrize("text", [
    LINE + "\n",  # no agents' marker
    f"Quoted: {LINE}\n<!-- workflow:agent -->\n",  # not a line of its own
    f"```\n{LINE}\n```\n<!-- workflow:agent -->\n",  # in a code block
    LINE + "\n" + LINE + "\n<!-- workflow:agent -->\n",  # two in one comment
    LINE.replace("round=3", "round=03") + "\n<!-- workflow:agent -->\n",  # not as the writer writes it
    LINE.replace(HEAD, HEAD.upper()) + "\n<!-- workflow:agent -->\n",
    LINE.replace("passes=2", "passes=2 extra=1") + "\n<!-- workflow:agent -->\n",
    LINE + "\n<!-- workflow:hand-off head=nonsense -->\n<!-- workflow:agent -->\n",  # beside a malformed one
    LINE + "\n" + rec(),  # beside a review record: the writer never writes both
])
def test_the_reader_leaves_out_anything_but_a_whole_comment_as_written(text):
    assert handoff.in_text(text) is None


def test_the_reader_never_raises():
    for value in (None, 3, [], {"body": 1}, "", "<!-- workflow:hand-off -->"):
        assert handoff.in_text(value) is None


# ---------- merge-check's hand_off ----------


def with_comments(*bodies_and_authors):
    data = inputs()
    data["comments"] = [comment(b, author=a, cid=i + 1) for i, (b, a) in enumerate(bodies_and_authors)]
    data["pr"]["comments"] = len(data["comments"])
    return data


def test_no_hand_off_is_null(project, capsys):
    got, _ = check(project, capsys, inputs())
    assert got["hand_off"] is None
    assert "hand_off" not in note_ids(got)


def test_the_latest_trusted_hand_off_is_reported(project, capsys):
    data = with_comments((rec(clean=False), "owner"), (hand_off_comment(head=EARLIER, rnd=1, passes=0), "dev"), (hand_off_comment(), "owner"))
    got, code = check(project, capsys, data)
    assert code == 0
    h = got["hand_off"]
    assert {k: h[k] for k in ("head", "round", "passes", "comment_id", "author", "on_head")} == {
        "head": HEAD, "round": 3, "passes": 2, "comment_id": 3, "author": "owner", "on_head": True}
    assert h["url"].endswith("#issuecomment-3")
    assert "hand_off" in note_ids(got)
    # It reports, and never decides: the review's own reasons stand.
    assert got["decision"] == "not_yet" and "review_not_clean" in [r["id"] for r in got["reasons"]]


def test_on_head_is_false_once_the_head_has_moved_past_the_hand_off(project, capsys):
    data = with_comments((rec(commit=EARLIER, clean=False), "owner"), (hand_off_comment(head=EARLIER, rnd=1, passes=0), "owner"))
    got, _ = check(project, capsys, data)
    assert got["hand_off"]["head"] == EARLIER and got["hand_off"]["on_head"] is False


def test_a_counted_record_after_it_clears_it(project, capsys):
    data = with_comments((rec(clean=False), "owner"), (hand_off_comment(rnd=1, passes=0), "owner"), (rec(rnd=2, clean=True), "dev"))
    got, _ = check(project, capsys, data)
    assert got["hand_off"] is None and got["decision"] == "ready"
    assert "hand_off" not in note_ids(got)


def test_a_counted_pass_after_it_clears_it_too(project, capsys):
    data = with_comments((rec(rnd=3, clean=False), "owner"), (hand_off_comment(), "owner"), (rec(kind="pass", rnd=3, clean=False), "keeper"))
    got, _ = check(project, capsys, data)
    assert got["hand_off"] is None


@pytest.mark.parametrize("after", [
    (rec(kind="pass", clean=True), "stranger"),  # an account without write access: not counted
    (rec(kind="pass", commit=OUTSIDE, clean=True), "owner"),  # a commit outside the pull request: not counted
    ("Looks good to me.", "owner"),  # a plain comment
])
def test_a_record_that_isnt_counted_doesnt_clear_it(project, capsys, after):
    data = with_comments((rec(clean=False), "owner"), (hand_off_comment(), "owner"), after)
    got, _ = check(project, capsys, data)
    assert got["hand_off"] is not None and got["hand_off"]["comment_id"] == 2


def test_a_record_before_it_doesnt_clear_it(project, capsys):
    data = with_comments((rec(clean=False), "owner"), (rec(kind="pass", clean=False), "owner"), (hand_off_comment(), "owner"))
    got, _ = check(project, capsys, data)
    assert got["hand_off"]["comment_id"] == 3


@pytest.mark.parametrize("bad", [
    (hand_off_comment(), "stranger"),  # an account without write access
    (hand_off_comment(head=OUTSIDE), "owner"),  # a head outside the pull request
])
def test_an_untrusted_hand_off_is_left_out_with_a_note(project, capsys, bad):
    data = with_comments((rec(clean=False), "owner"), bad)
    got, _ = check(project, capsys, data)
    assert got["hand_off"] is None and "hand_offs_ignored" in note_ids(got)


def test_an_untrusted_later_hand_off_leaves_the_trusted_one_reported(project, capsys):
    data = with_comments((rec(clean=False), "owner"), (hand_off_comment(rnd=1, passes=0), "owner"), (hand_off_comment(), "stranger"))
    got, _ = check(project, capsys, data)
    assert got["hand_off"]["comment_id"] == 2 and got["hand_off"]["round"] == 1


def test_the_text_answer_names_the_hand_off(project, capsys):
    data = with_comments((rec(clean=False), "owner"), (hand_off_comment(), "owner"))
    out, _ = check(project, capsys, data, as_json=False)
    assert "Handed off" in out and HEAD[:7] in out


def test_unreadable_comments_give_no_hand_off(project, capsys):
    data = inputs()
    got, _ = check(project, capsys, data, raw={"comments": "not json"})
    assert got["hand_off"] is None and got["decision"] == "not_yet"


def test_the_result_carries_hand_off_in_its_dict():
    res = merge.Result("ready", 12, HEAD, "developer", False)
    assert res.as_dict()["hand_off"] is None


# ---------- the Stop gate ----------


def test_the_gate_accepts_handed_off_without_the_checklist(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    msg = "Handed off in #432: a fresh session carries the review on.\nWORKFLOW-STATUS: handed-off"
    assert gate.verdict(msg) is None
    assert gate.decide({"session_id": "h-1", "last_assistant_message": msg}) is None
    assert gate.verdict("**WORKFLOW-STATUS:** Handed-Off") is None


def test_the_gate_still_asks_for_a_status_and_reads_no_status_from_a_fence(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    assert gate.verdict("```\nWORKFLOW-STATUS: handed-off\n```\n")
    assert gate.verdict("WORKFLOW-STATUS: handed-offish")
    assert gate.verdict("WORKFLOW-STATUS: handed")


# ---------- the changelog ----------


def test_the_changelog_says_so():
    notes = since_0110()
    assert "#371" in notes and "workflow hand-off" in notes and "hand_off" in notes and "handed-off" in notes
