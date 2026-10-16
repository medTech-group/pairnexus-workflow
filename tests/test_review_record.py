"""Review records (#79): `workflow review-record` writes one, `reviews.read` reads them back."""

import json

import pytest

from conftest import KIT
from workflow import cli, reviews

SHA = "3f2a9c0b7de14a2c9e8f5d6b1a0c3e2f4d5b6a7c"
OTHER = "0123456789abcdef0123456789abcdef01234567"


def run(capsys, *args):
    code = cli.main(["review-record", *args])
    out, err = capsys.readouterr()
    return code, out, err


def body(capsys, *args):
    code, out, err = run(capsys, *args)
    assert code == 0, err
    return out


# The writer, through the CLI --------------------------------------------------


def test_a_round_prints_the_human_line_the_record_line_and_the_marker(capsys):
    out = body(capsys, "--kind", "round", "--round", "2", "--commit", SHA, "--reviewers", "standards,spec,correctness", "--clean")
    assert out.splitlines() == [
        "Review round 2 on `3f2a9c0`: clean. Reviewers: Standards, Spec, Correctness.",
        f"<!-- workflow:review kind=round round=2 commit={SHA} reviewers=standards,spec,correctness result=clean -->",
        "<!-- workflow:agent -->",
    ]


def test_a_not_clean_round_is_written_too(capsys):
    out = body(capsys, "--kind", "round", "--round", "1", "--commit", SHA, "--reviewers", "standards,spec,correctness,explorer", "--not-clean")
    assert out.splitlines()[0] == "Review round 1 on `3f2a9c0`: not clean. Reviewers: Standards, Spec, Correctness, Explorer."
    assert "result=not-clean" in out.splitlines()[1]


def test_a_pass_names_the_round_it_follows(capsys):
    out = body(capsys, "--kind", "pass", "--round", "3", "--commit", SHA, "--reviewers", "correctness", "--clean")
    assert out.splitlines() == [
        "Correctness pass after round 3 on `3f2a9c0`: clean. Reviewers: Correctness.",
        f"<!-- workflow:review kind=pass round=3 commit={SHA} reviewers=correctness result=clean -->",
        "<!-- workflow:agent -->",
    ]


def test_reviewers_are_read_in_any_case_and_order_and_written_in_the_panels_order(capsys):
    out = body(capsys, "--kind", "round", "--round", "1", "--commit", SHA.upper(), "--reviewers", "Explorer, security,SPEC,standards,correctness", "--clean")
    assert f"commit={SHA} reviewers=standards,spec,correctness,security,explorer " in out


@pytest.mark.parametrize(
    "args, says",
    [
        (["--commit", SHA[:7]], "full 40-character"),
        (["--commit", "g" * 40], "full 40-character"),
        (["--commit", SHA + "a"], "full 40-character"),
        (["--commit", ""], "full 40-character"),
        (["--reviewers", "standards,linter"], "unknown reviewer `linter`"),
        (["--reviewers", ""], "give --reviewers"),
        (["--reviewers", "standards,,spec"], "--reviewers has an empty name"),
        (["--reviewers", "standards,spec,"], "--reviewers has an empty name"),
        (["--round", "0"], "a whole number from 1"),
        (["--round", "9" * 5000], "a whole number from 1"),
        (["--round", "1234567"], "a whole number from 1"),
        (["--round", "two"], "a whole number from 1"),
        (["--kind", "light"], "--kind is `round` or `pass`"),
    ],
)
def test_each_malformed_input_is_refused_in_plain_words(capsys, args, says):
    full = {"--kind": "round", "--round": "1", "--commit": SHA, "--reviewers": "standards,spec,correctness"}
    full.update(dict(zip(args[::2], args[1::2])))
    flat = [x for kv in full.items() for x in kv]
    code, out, err = run(capsys, *flat, "--clean")
    assert code != 0 and out == ""
    assert says in err and err.startswith("workflow review-record: ")
    assert "Traceback" not in err


@pytest.mark.parametrize("missing", ["--kind", "--round", "--commit", "--reviewers"])
def test_a_missing_field_is_refused(capsys, missing):
    full = {"--kind": "round", "--round": "1", "--commit": SHA, "--reviewers": "correctness"}
    del full[missing]
    flat = [x for kv in full.items() for x in kv]
    code, out, err = run(capsys, *flat, "--clean")
    assert code != 0 and out == ""
    assert f"give {missing}" in err


def test_no_result_is_refused(capsys):
    code, out, err = run(capsys, "--kind", "round", "--round", "1", "--commit", SHA, "--reviewers", "correctness")
    assert code != 0 and out == ""
    assert "give --clean or --not-clean" in err


def test_both_results_are_refused(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["review-record", "--kind", "round", "--round", "1", "--commit", SHA, "--reviewers", "correctness", "--clean", "--not-clean"])
    assert e.value.code != 0


@pytest.mark.parametrize("who", ["standards", "correctness,security", "spec,correctness"])
def test_a_pass_with_reviewers_other_than_correctness_is_refused(capsys, who):
    code, out, err = run(capsys, "--kind", "pass", "--round", "2", "--commit", SHA, "--reviewers", who, "--clean")
    assert code != 0 and out == ""
    assert "a pass is reviewed by correctness alone" in err


def test_the_command_is_listed_with_a_help_line(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "review-record" in capsys.readouterr().out


# The reader ---------------------------------------------------------------


def written(capsys, *args):
    return body(capsys, "--commit", SHA, *args)


def test_records_written_by_the_command_read_back_field_for_field(capsys):
    text = written(capsys, "--kind", "round", "--round", "2", "--reviewers", "spec,standards,correctness,security", "--not-clean")
    assert reviews.records_in(text) == [
        reviews.Record(kind="round", round=2, commit=SHA, reviewers=("standards", "spec", "correctness", "security"), result="not-clean")
    ]
    text = written(capsys, "--kind", "pass", "--round", "2", "--reviewers", "correctness", "--clean")
    (r,) = reviews.records_in(text)
    assert (r.kind, r.round, r.commit, r.reviewers, r.result, r.clean) == ("pass", 2, SHA, ("correctness",), "clean", True)


def test_the_writer_and_the_reader_agree_on_every_reviewer():
    for who in reviews.REVIEWERS:
        text = reviews.record(kind="round", round=1, commit=SHA, reviewers=[who], clean=True)
        assert reviews.records_in(text)[0].reviewers == (who,)


def test_a_comment_without_a_record_yields_none():
    assert reviews.records_in("Looks good to me.") == []
    assert reviews.records_in("") == []
    assert reviews.records_in(None) == []
    assert reviews.records_in(123) == []


def test_the_command_reads_names_in_any_case_and_a_padded_sha(capsys):
    out = body(capsys, "--kind", " ROUND ", "--round", " 1 ", "--commit", f"  {SHA}\n", "--reviewers", "Spec", "--clean")
    assert f"kind=round round=1 commit={SHA} reviewers=spec result=clean" in out


def test_the_python_writer_takes_only_true_or_false_as_the_result():
    with pytest.raises(reviews.RecordError, match="give --clean or --not-clean"):
        reviews.record(kind="round", round=1, commit=SHA, reviewers="spec", clean="false")


def test_a_record_line_quoted_inside_other_text_is_not_a_record(capsys):
    line = written(capsys, "--kind", "round", "--round", "3", "--reviewers", "spec", "--clean").splitlines()[1]
    assert reviews.records_in(f"The record `{line}` was wrong.") == []
    assert reviews.records_in(f"Before: {line}") == []
    assert len(reviews.records_in(f"  {line}  \r\n")) == 1


@pytest.mark.parametrize(
    "line",
    [
        f"<!-- workflow:review kind=round round=2 commit={SHA[:7]} reviewers=spec result=clean -->",
        f"<!-- workflow:review kind=round round=2 commit={SHA} reviewers=spec,linter result=clean -->",
        f"<!-- workflow:review kind=round round=2 commit={SHA} reviewers=spec result=maybe -->",
        f"<!-- workflow:review kind=round round=2 commit={SHA} reviewers=spec -->",
        f"<!-- workflow:review kind=round round=x commit={SHA} reviewers=spec result=clean -->",
        f"<!-- workflow:review kind=round round=0 commit={SHA} reviewers=spec result=clean -->",
        f"<!-- workflow:review kind=round round={'9' * 5000} commit={SHA} reviewers=spec result=clean -->",
        f"<!-- workflow:review kind=round round=01 commit={SHA} reviewers=spec result=clean -->",
        f"<!-- workflow:review kind=round round=1 commit={SHA.upper()} reviewers=spec result=clean -->",
        f"<!-- workflow:review kind=ROUND round=1 commit={SHA} reviewers=spec result=clean -->",
        f"<!-- workflow:review kind=round round=1 commit={SHA} reviewers=spec,standards result=clean -->",
        f"<!-- workflow:review kind=round round=1 commit={SHA} reviewers=spec,spec result=clean -->",
        f"<!-- workflow:review kind=round round=1 commit={SHA} reviewers=spec, result=clean -->",
        f"<!-- workflow:review kind=light round=1 commit={SHA} reviewers=spec result=clean -->",
        f"<!-- workflow:review kind=pass round=1 commit={SHA} reviewers=spec result=clean -->",
        f"<!-- workflow:review kind=round round=1 round=2 commit={SHA} reviewers=spec result=clean -->",
        f"<!-- workflow:review kind=round round=1 commit={SHA} reviewers=spec result=clean extra=1 -->",
        f"<!-- workflow:review kind=round round=1 commit={SHA} reviewers= result=clean -->",
        f"<!-- workflow:review kind=round round=1 commit={SHA} reviewers=spec result=clean",
        "<!-- workflow:review -->",
    ],
)
def test_a_malformed_record_line_yields_no_record_and_never_raises(line):
    assert reviews.records_in(f"Review round 2.\n{line}\n<!-- workflow:agent -->") == []


def test_two_records_in_one_comment_are_both_read(capsys):
    a = written(capsys, "--kind", "round", "--round", "1", "--reviewers", "correctness", "--not-clean")
    b = body(capsys, "--kind", "pass", "--round", "1", "--commit", OTHER, "--reviewers", "correctness", "--clean")
    got = reviews.records_in(a + "\n" + b)
    assert [(r.kind, r.commit, r.result) for r in got] == [("round", SHA, "not-clean"), ("pass", OTHER, "clean")]


def test_a_good_record_beside_a_malformed_one_is_still_read(capsys):
    good = written(capsys, "--kind", "round", "--round", "1", "--reviewers", "spec", "--clean")
    bad = f"<!-- workflow:review kind=round round=1 commit=abc reviewers=spec result=clean -->"
    assert len(reviews.records_in(bad + "\n" + good)) == 1


def test_read_takes_a_prs_comments_and_keeps_who_posted_each_and_when(capsys):
    a = written(capsys, "--kind", "round", "--round", "1", "--reviewers", "standards,spec,correctness", "--not-clean")
    b = written(capsys, "--kind", "round", "--round", "2", "--reviewers", "standards,spec,correctness", "--clean")
    comments = [
        {"id": 11, "user": {"login": "notes-app-owner"}, "created_at": "2026-10-16T10:00:00Z", "html_url": "https://x/pull/5#issuecomment-11", "body": a},
        {"id": 12, "user": {"login": "a-shopper"}, "created_at": "2026-10-16T10:05:00Z", "body": "When does this ship?"},
        {"id": 13, "user": {"login": "notes-app-owner"}, "created_at": "2026-10-16T10:10:00Z", "body": b},
        {"id": 14, "user": {"login": "notes-app-owner"}, "created_at": "2026-10-16T10:11:00Z", "body": None},
    ]
    got = reviews.read(comments)
    assert [(r.round, r.result, r.author, r.comment_id, r.created_at) for r in got] == [
        (1, "not-clean", "notes-app-owner", 11, "2026-10-16T10:00:00Z"),
        (2, "clean", "notes-app-owner", 13, "2026-10-16T10:10:00Z"),
    ]


def test_read_takes_the_shapes_the_comments_command_takes(capsys):
    a = written(capsys, "--kind", "round", "--round", "1", "--reviewers", "correctness", "--clean")
    mcp = {"comments": [{"id": "IC_kwX", "author": {"login": "owner"}, "createdAt": "t", "url": "https://x/pull/5#issuecomment-21", "body": a}]}
    (r,) = reviews.read(mcp)
    assert (r.author, r.comment_id, r.created_at) == ("owner", 21, "t")
    (r,) = reviews.read(json.loads(json.dumps([[mcp["comments"][0]]])))
    assert r.round == 1


# The skills and the docs ----------------------------------------------------


def _text(path):
    return (KIT / path).read_text(encoding="utf-8")


def test_the_review_panel_posts_a_record_after_every_round_with_the_command_commit_and_result():
    text = _text("skills/review-panel/SKILL.md")
    assert "WF review-record --kind round --round <n> --commit <sha>" in text
    assert "--kind pass --round <last round> --commit <sha> --reviewers correctness" in text
    assert "--clean" in text and "--not-clean" in text
    assert "git rev-parse HEAD" in text
    assert "after every round, whatever it found" in text
    assert "after each later Correctness pass" in text
    assert "`--clean`, or `--not-clean` when it found something to fix" in text
    assert "mkdir -p /tmp/review-<ticket>-pass<k>" in text
    assert "-F body=@/tmp/review-<ticket>-r<n>/record.md" in text
    assert "only when the command exited 0" in text
    assert "attended and unattended sessions alike" in text
    assert "record.md" in text


def test_the_review_panel_says_how_to_run_the_command_vendored_and_as_a_plugin():
    text = _text("skills/review-panel/SKILL.md")
    assert "python3 .claude/workflow/bin/workflow.py" in text
    assert "scripts/workflow.py" in text


def test_build_ticket_posts_the_records_kept_before_the_pull_request_and_keeps_its_table():
    text = _text("skills/build-ticket/SKILL.md")
    assert "the findings table" in text
    assert "review records" in text and "record.md" in text
    assert "each round's and each Correctness pass's `record.md`" in text


def test_the_flow_says_each_round_and_pass_posts_its_record():
    text = _text("docs/flow.md")
    assert "review record" in text and "`workflow review-record`" in text


def test_the_changelog_notes_it_under_unreleased():
    text = _text("CHANGELOG.md")
    unreleased = text.split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    assert "#79" in unreleased and "review-record" in unreleased
