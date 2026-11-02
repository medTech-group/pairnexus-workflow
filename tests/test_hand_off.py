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
from workflow import cli, findings, gate, handoff, merge, reviews

LINE = f"<!-- workflow:hand-off head={HEAD} round=3 passes=2 -->"


def record_of(found, rnd=3, kind="pass", commit=EARLIER):
    """The last review's record, as `workflow review-record --findings` writes it."""
    f = findings.load(json.dumps(found))
    who = "correctness" if kind == "pass" else "standards,spec,correctness"
    return reviews.record(kind=kind, round=rnd, commit=commit, reviewers=who, clean=None, findings=f)


BLOCKS = [{"mark": "blocks", "mechanism": "the requeue order", "reproducer": "a PR dropped twice is requeued once"}]


def written(tmp_path, capsys, *args, record=None):
    """`workflow hand-off`'s output, errors and exit code, with `record` as its --record file."""
    argv = ["hand-off", *args]
    if record is not None:
        path = tmp_path / "record.md"
        path.write_text(record)
        argv += ["--record", str(path)]
    code = cli.main(argv)
    out = capsys.readouterr()
    return out.out, out.err, code


def hand_off_comment(head=HEAD, rnd=3, passes=2, record=None, **kw):
    if record is None and rnd:
        record = handoff.last_record(record_of([], rnd=rnd, kind="pass" if passes else "round"))
    return handoff.comment(head=head, round=rnd, passes=passes, record=record, **kw)


def from_record(found, **kw):
    return hand_off_comment(record=handoff.last_record(record_of(found)), **kw)


# ---------- the comment ----------


def test_the_comment_has_a_plain_heading_the_head_the_reviews_and_the_machine_line_with_the_marker():
    text = hand_off_comment()
    lines = text.splitlines()
    assert lines[0].startswith("## ") and "`" not in lines[0]
    assert f"`{HEAD[:7]}`" in text
    assert "3 review rounds and 2 Correctness passes" in text
    assert lines[-2:] == [LINE, "<!-- workflow:agent -->"]
    assert "Open blocking findings: none." in text and "Tickets filed: none." in text


def test_open_blocking_findings_come_from_the_record_a_security_one_by_its_area_only():
    text = from_record([
        *BLOCKS,
        {"mark": "blocks", "mechanism": "token check", "reproducer": "SECRET-DETAIL an expired token passes", "security": "change", "area": "sign-in"},
        {"mark": "note", "mechanism": "wording"},
        {"mark": "ticket", "mechanism": "label sync", "issue": 415},
    ])
    assert "- the part `the requeue order`." in text
    assert "- a security problem the change adds, in `sign-in`." in text
    assert "SECRET-DETAIL" not in text and "token check" not in text and "expired" not in text
    assert "a PR dropped twice" not in text  # a record carries no reproducer
    assert "wording" not in text  # a note isn't open
    assert "Tickets filed: #415." in text  # a ticket to fix it is a ticket filed


def test_a_finding_kept_after_a_contest_says_so():
    text = from_record({"findings": [{**BLOCKS[0], "contested": True}], "outcomes": [{"outcome": "contested", "finding": 1, "ruling": "kept"}]})
    assert "- the part `the requeue order`, kept after a contest." in text


def test_a_blocking_findings_own_ticket_is_a_ticket_filed():
    text = from_record([{"mark": "blocks", "mechanism": "m", "reproducer": "r", "security": "main", "area": "sign-in", "issue": 420}])
    assert "in `sign-in`, #420." in text and "Tickets filed: #420." in text


def test_tickets_filed_join_the_records_tickets_and_splits_once_each_in_number_order():
    text = from_record({
        "findings": [{"mark": "ticket", "mechanism": "label sync", "issue": 415}],
        "outcomes": [{"outcome": "split", "mechanism": "the preview reader", "issue": 416}],
    }, tickets=(417, 415))
    assert "Tickets filed: #415, #416, #417." in text


def test_the_part_is_named_as_the_records_own_list_names_it():
    f = findings.load(json.dumps([{"mark": "blocks", "mechanism": "m", "reproducer": "r", "covered": True, "issue": 9}])).findings[0]
    assert f.text() == f"- Blocks: {f.part()}." and f.part() == "the part `m`, which the safe fallback covers, #9"


def test_the_cli_writes_the_comment_from_the_record(tmp_path, capsys):
    rec_text = record_of(BLOCKS)
    out, err, code = written(tmp_path, capsys, "--commit", HEAD, "--round", "3", "--passes", "2", "--tickets", "#417,418", record=rec_text)
    assert code == 0 and not err
    assert out == hand_off_comment(record=handoff.last_record(rec_text), tickets=(417, 418))
    assert handoff.in_text(out).head == HEAD
    # A record GitHub gives back, with `\r\n` and a cloud session's footer, reads the same.
    crlf = (rec_text + "\n---\n_Generated by [Claude Code](https://claude.ai/code)_\n").replace("\n", "\r\n")
    assert written(tmp_path, capsys, "--commit", HEAD, "--round", "3", "--passes", "2", "--tickets", "#417,418", record=crlf)[0] == out


def test_the_last_record_in_the_file_counts():
    two = record_of([], rnd=3, kind="round") + record_of(BLOCKS)
    assert handoff.last_record(two).findings[0].mechanism == "the requeue order"


@pytest.mark.parametrize("args, record, says", [
    (("--round", "3", "--passes", "2"), None, "--commit"),
    (("--commit", HEAD[:7], "--round", "3", "--passes", "2"), None, "40-character"),
    (("--commit", HEAD, "--passes", "2"), None, "--round"),
    (("--commit", HEAD, "--round", "x", "--passes", "2"), None, "--round"),
    (("--commit", HEAD, "--round", "3"), None, "--passes"),
    (("--commit", HEAD, "--round", "3", "--passes", "-1"), None, "--passes"),
    (("--commit", HEAD, "--round", "0", "--passes", "1"), None, "a pass follows a round"),
    (("--commit", HEAD, "--round", "3", "--passes", "2", "--tickets", "x"), None, "--tickets"),
    (("--commit", HEAD, "--round", "3", "--passes", "2", "--tickets", "##415"), None, "--tickets"),
    (("--commit", HEAD, "--commit", HEAD, "--round", "3", "--passes", "2"), None, "once"),
    # The open findings are named from the first round on, and never before.
    (("--commit", HEAD, "--round", "3", "--passes", "2"), None, "give --record"),
    (("--commit", HEAD, "--round", "0", "--passes", "0"), "BLOCKS", "--round 0"),
    (("--commit", HEAD, "--round", "2", "--passes", "2"), "BLOCKS", "round 3's"),
    (("--commit", HEAD, "--round", "3", "--passes", "2"), "Not a record.", "holds no review record"),
    (("--commit", HEAD, "--round", "3", "--passes", "2"), "OLD", "rule=2"),
    (("--commit", HEAD, "--round", "3", "--passes", "0"), "BLOCKS", "--passes 0"),  # a pass's record, with no pass
])
def test_the_cli_refuses_a_malformed_flag(tmp_path, capsys, args, record, says):
    text = {"BLOCKS": record_of(BLOCKS), "OLD": reviews.record(kind="pass", round=3, commit=HEAD, reviewers="correctness", clean=False)}.get(record, record)
    out, err, code = written(tmp_path, capsys, *args, record=text)
    assert code == 2 and not out and says in err, err


def test_a_rounds_own_record_goes_with_passes_after_an_earlier_round():
    # A small review's round 1 and its passes, then a full round 2: round 2's record, with the passes so far.
    record = handoff.last_record(record_of(BLOCKS, rnd=2, kind="round"))
    assert "Open blocking findings:" in handoff.comment(head=HEAD, round=2, passes=3, record=record)


def test_the_cli_refuses_a_record_it_cant_read(tmp_path, capsys):
    argv = ["hand-off", "--commit", HEAD, "--round", "1", "--passes", "0", "--record"]
    assert cli.main([*argv, str(tmp_path / "missing.md")]) == 2
    (tmp_path / "latin1.md").write_bytes("caf\xe9".encode("latin-1"))
    assert cli.main([*argv, str(tmp_path / "latin1.md")]) == 2
    assert "UTF-8" in capsys.readouterr().err


def test_a_comment_past_githubs_limit_is_refused():
    with pytest.raises(handoff.HandOffError, match="UTF-16"):
        hand_off_comment(tickets=tuple(range(1_000_000, 1_008_000)))


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
    assert "hand_off" in note_ids(got) and "hand_offs_ignored" not in note_ids(got)
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


def test_a_rule_2_record_after_it_clears_it_whatever_its_result(project, capsys):
    for found in ([], BLOCKS):
        data = with_comments((rec(rnd=3, clean=False), "owner"), (hand_off_comment(), "owner"), (record_of(found, commit=HEAD), "owner"))
        got, _ = check(project, capsys, data)
        assert got["hand_off"] is None, found


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


def test_a_record_posted_after_it_for_an_older_commit_doesnt_clear_it(project, capsys):
    # A record posted late for a commit before the hand-off's head is no review since.
    data = with_comments((rec(rnd=3, clean=False), "owner"), (hand_off_comment(), "owner"), (rec(kind="pass", rnd=3, commit=EARLIER, clean=True), "owner"))
    got, _ = check(project, capsys, data)
    assert got["hand_off"]["comment_id"] == 2


def test_a_record_for_a_later_commit_clears_a_hand_off_of_an_earlier_one(project, capsys):
    data = with_comments((rec(commit=EARLIER, clean=False), "owner"), (hand_off_comment(head=EARLIER, rnd=1, passes=0), "owner"),
                         (rec(rnd=2, clean=True), "owner"))
    got, _ = check(project, capsys, data)
    assert got["hand_off"] is None


def test_follows_means_posted_later_by_time_not_by_the_inputs_order(project, capsys):
    data = with_comments((rec(clean=False), "owner"), (rec(rnd=2, clean=True), "owner"), (hand_off_comment(rnd=1, passes=0), "owner"))
    # The record is listed before the hand-off but was posted after it.
    data["comments"][0]["created_at"] = "2026-10-16T08:00:00Z"
    data["comments"][2]["created_at"] = "2026-10-16T08:30:00Z"
    got, _ = check(project, capsys, data)
    assert got["hand_off"] is None
    data["comments"][1]["created_at"] = "2026-10-16T08:10:00Z"  # now posted before it
    got, _ = check(project, capsys, data)
    assert got["hand_off"]["comment_id"] == 3


def long_pr(*bodies_and_authors):
    """A pull request of 300 commits, of which GitHub lists the oldest 250: its head isn't among them."""
    data = with_comments(*bodies_and_authors)
    data["pr"]["commits"] = 300
    data["commits"] = [{"sha": EARLIER}] + [{"sha": f"{i:040x}"} for i in range(1, 250)]
    return data


def test_a_hand_off_of_a_head_the_commit_list_leaves_out_is_cleared_only_by_a_record_of_it(project, capsys):
    data = long_pr((rec(rnd=3, clean=False), "owner"), (hand_off_comment(), "owner"), (rec(kind="pass", rnd=3, commit=EARLIER, clean=True), "owner"))
    got, _ = check(project, capsys, data)
    assert got["hand_off"]["comment_id"] == 2
    data = long_pr((rec(rnd=3, clean=False), "owner"), (hand_off_comment(), "owner"), (rec(kind="pass", rnd=3, clean=True), "owner"))
    got, _ = check(project, capsys, data)
    assert got["hand_off"] is None


def test_a_hand_off_of_a_commit_past_the_listed_250_that_is_no_longer_the_head_is_left_out_saying_so(project, capsys):
    data = long_pr((rec(rnd=3, clean=False), "owner"), (hand_off_comment(head=OUTSIDE), "owner"))
    got, _ = check(project, capsys, data)
    assert got["hand_off"] is None
    [n] = [x for x in got["notes"] if x["id"] == "hand_offs_ignored"]
    assert "past the 250 GitHub lists" in n["message"]


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
    assert "Carry on in a fresh session" in out and "Handed off" not in out and HEAD[:7] in out


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
    assert "handed-off" in gate.verdict("All done.")  # its request names every status it accepts
    assert gate.verdict("```\nWORKFLOW-STATUS: handed-off\n```\n")
    assert gate.verdict("WORKFLOW-STATUS: handed-offish")
    assert gate.verdict("WORKFLOW-STATUS: handed")


# ---------- the changelog ----------


def test_the_changelog_says_so():
    notes = since_0110()
    assert "#371" in notes and "workflow hand-off" in notes and "hand_off" in notes and "handed-off" in notes
