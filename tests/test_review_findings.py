"""The findings file and new-rule review records (#370, spec #412 "Records and
clean"): `workflow review-record --findings F` writes a `rule=2` record whose
result is worked out from the findings' marks, and `reviews.records_in` reads
it back only whole."""

import json

import pytest

from conftest import KIT
from workflow import cli, findings as findings_mod, reviews
from changelog_notes import since_0110

SHA = "3f2a9c0b7de14a2c9e8f5d6b1a0c3e2f4d5b6a7c"
ROUND = ["--kind", "round", "--round", "2", "--commit", SHA, "--reviewers", "standards,spec,correctness"]

FULL = {
    "findings": [
        {"mark": "blocks", "mechanism": "the requeue order", "reproducer": "a dropped PR requeued twice: queued once", "covered": True},
        {"mark": "ticket", "mechanism": "label sync", "issue": 415},
        {"mark": "note", "mechanism": "wording"},
        {"mark": "blocks", "mechanism": "token printed in the log", "reproducer": "run X: the log shows Y", "security": "change", "area": "auth"},
        {"mark": "blocks", "mechanism": "the requeue order", "reproducer": "requeue after a fix: queued twice", "contested": True},
    ],
    "outcomes": [
        {"outcome": "contested", "finding": 2, "ruling": "kept"},
        {"outcome": "contested", "finding": 3, "ruling": "overturned"},
        {"outcome": "fail-closed", "mechanism": "the merge gate"},
        {"outcome": "split", "mechanism": "the preview reader", "issue": 416},
    ],
    "split": True,
}


@pytest.fixture(autouse=True)
def _no_project(tmp_path, monkeypatch):
    """No profile and no git here: the hashes of a round's own changes are
    `unknown` without running git in the kit's own checkout."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))


def run(capsys, *args):
    code = cli.main(["review-record", *args])
    out, err = capsys.readouterr()
    return code, out, err


def file_of(tmp_path, content, name="findings.json"):
    p = tmp_path / name
    if isinstance(content, bytes):
        p.write_bytes(content)
    elif isinstance(content, str):
        p.write_text(content)
    else:
        p.write_text(json.dumps(content))
    return str(p)


def written(capsys, tmp_path, content, *args):
    code, out, err = run(capsys, *(args or ROUND), "--findings", file_of(tmp_path, content))
    assert code == 0, err
    return out


def refused(capsys, tmp_path, content, *args):
    code, out, err = run(capsys, *(args or ROUND), "--findings", file_of(tmp_path, content))
    assert code == 2 and out == "", (code, out, err)
    return err


# The writer -------------------------------------------------------------------


@pytest.mark.parametrize("content", [[], {"findings": []}, {"findings": [], "outcomes": [], "split": False}])
def test_an_empty_list_is_a_clean_rule_2_record(capsys, tmp_path, content):
    out = written(capsys, tmp_path, content)
    assert out.splitlines() == [
        "Review round 2 on `3f2a9c0`: clean. Reviewers: Standards, Spec, Correctness.",
        "",
        f"<!-- workflow:review kind=round round=2 commit={SHA} reviewers=standards,spec,correctness diff=unknown lines=unknown rule=2 findings=0 outcomes=0 split=no result=clean -->",
        "<!-- workflow:agent -->",
    ]


def test_each_finding_its_flags_the_outcomes_and_the_split_flag_are_written(capsys, tmp_path):
    out = written(capsys, tmp_path, FULL)
    assert out.splitlines() == [
        "Review round 2 on `3f2a9c0`: not clean. Reviewers: Standards, Spec, Correctness.",
        "",
        "Findings:",
        "- Blocks: the part `the requeue order`, which the safe fallback covers.",
        "- A ticket to fix it: the part `label sync`, #415.",
        "- Note: the part `wording`.",
        "- Blocks: a security problem the change adds, in `auth`.",
        "- Blocks, kept after a contest: the part `the requeue order`.",
        "",
        "From the last review:",
        "- Finding 2's contest: kept.",
        "- Finding 3's contest: overturned.",
        "- The part `the merge gate` took the safe fallback.",
        "- The part `the preview reader` was split out to #416.",
        "",
        "This ticket was made by a split.",
        "",
        f"<!-- workflow:review kind=round round=2 commit={SHA} reviewers=standards,spec,correctness diff=unknown lines=unknown rule=2 findings=5 outcomes=4 split=yes result=not-clean -->",
        "<!-- workflow:finding n=1 mark=blocks mechanism=the%20requeue%20order covered=yes contested=no security=no issue=none -->",
        "<!-- workflow:finding n=2 mark=ticket mechanism=label%20sync covered=no contested=no security=no issue=415 -->",
        "<!-- workflow:finding n=3 mark=note mechanism=wording covered=no contested=no security=no issue=none -->",
        "<!-- workflow:finding n=4 mark=blocks mechanism=auth covered=no contested=no security=change issue=none -->",
        "<!-- workflow:finding n=5 mark=blocks mechanism=the%20requeue%20order covered=no contested=yes security=no issue=none -->",
        "<!-- workflow:outcome n=1 kind=contested finding=2 ruling=kept -->",
        "<!-- workflow:outcome n=2 kind=contested finding=3 ruling=overturned -->",
        "<!-- workflow:outcome n=3 kind=fail-closed mechanism=the%20merge%20gate -->",
        "<!-- workflow:outcome n=4 kind=split mechanism=the%20preview%20reader issue=416 -->",
        "<!-- workflow:agent -->",
    ]


def test_a_security_findings_mechanism_and_reproducer_show_only_its_area(capsys, tmp_path):
    content = {"findings": [
        {"mark": "blocks", "mechanism": "session token in the redirect", "reproducer": "GET /login?next=evil: the token goes along", "security": "change", "area": "sign-in"},
        {"mark": "ticket", "mechanism": "old cookie flags", "reproducer": "cookie lacks Secure", "security": "main", "area": "cookies", "issue": 420},
    ]}
    out = written(capsys, tmp_path, content)
    for secret in ("session token", "redirect", "evil", "old cookie", "Secure"):
        assert secret not in out
    assert "- Blocks: a security problem the change adds, in `sign-in`." in out
    assert "- A ticket to fix it: a security or safety problem in code on the base branch, in `cookies`, #420." in out
    assert "mark=blocks mechanism=sign-in covered=no contested=no security=change issue=none" in out
    assert "mark=ticket mechanism=cookies covered=no contested=no security=main issue=420" in out


def test_notes_and_tickets_alone_leave_the_review_clean(capsys, tmp_path):
    out = written(capsys, tmp_path, [{"mark": "note", "mechanism": "a"}, {"mark": "ticket", "mechanism": "b", "issue": "#9"}])
    assert out.splitlines()[0].endswith(": clean. Reviewers: Standards, Spec, Correctness.")
    assert "rule=2 findings=2 outcomes=0 split=no result=clean -->" in out
    assert "issue=9 -->" in out


def test_a_blocking_finding_makes_the_review_not_clean(capsys, tmp_path):
    out = written(capsys, tmp_path, [{"mark": "blocks", "mechanism": "a", "reproducer": "x gives y"}])
    assert "result=not-clean" in out and ": not clean." in out


def test_a_pass_takes_a_findings_file_too(capsys, tmp_path):
    out = written(capsys, tmp_path, [], "--kind", "pass", "--round", "3", "--commit", SHA, "--reviewers", "correctness")
    assert out.splitlines()[0] == "Correctness pass after round 3 on `3f2a9c0`: clean. Reviewers: Correctness."
    assert f"kind=pass round=3 commit={SHA} reviewers=correctness diff=unknown lines=unknown rule=2 " in out


def test_a_mechanism_is_written_exactly_and_never_breaks_the_comment(capsys, tmp_path):
    name = "the --> end & 100% <odd> part"
    out = written(capsys, tmp_path, [{"mark": "note", "mechanism": f"  {name} "}])
    line = next(l for l in out.splitlines() if l.startswith("<!-- workflow:finding"))
    assert line.count("-->") == 1 and "<odd>" not in line
    (r,) = reviews.records_in(out)
    assert r.findings[0].mechanism == name


# Refusals ---------------------------------------------------------------------


@pytest.mark.parametrize("flag", ["--clean", "--not-clean"])
def test_a_result_flag_is_refused_with_findings(capsys, tmp_path, flag):
    err = refused(capsys, tmp_path, [], *ROUND, flag)
    assert "--findings" in err and "works the result out" in err


def test_a_spec_review_is_refused_with_findings(capsys, tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("# A spec\n")
    err = refused(capsys, tmp_path, [], "--kind", "spec", "--round", "1", "--body", str(spec), "--reviewers", "spec")
    assert "--findings" in err and "spec" in err
    err = refused(capsys, tmp_path, [], "--round", "1", "--body", str(spec), "--reviewers", "spec")
    assert "--findings" in err and "spec" in err
    err = refused(capsys, tmp_path, [], "--kind", "spec", "--round", "1", "--commit", SHA, "--reviewers", "spec")
    assert "--findings" in err and "spec" in err


def test_measure_is_refused_with_findings(capsys, tmp_path):
    err = refused(capsys, tmp_path, [], "--measure", "--commit", SHA)
    assert "--findings" in err


def test_findings_given_twice_is_refused(capsys, tmp_path):
    f = file_of(tmp_path, [])
    code, out, err = run(capsys, *ROUND, "--findings", f, "--findings", f)
    assert code == 2 and "give --findings once" in err


def test_a_missing_file_or_a_folder_is_refused(capsys, tmp_path):
    code, out, err = run(capsys, *ROUND, "--findings", str(tmp_path / "nope.json"))
    assert code == 2 and "--findings names no file" in err
    code, out, err = run(capsys, *ROUND, "--findings", str(tmp_path))
    assert code == 2 and "isn't a file" in err
    code, out, err = run(capsys, *ROUND, "--findings", "")
    assert code == 2 and "give --findings a file" in err


@pytest.mark.parametrize(
    "content, says",
    [
        (b"\xff\xfe[]", "isn't UTF-8 text"),
        ("", "is empty"),
        ("  \n", "is empty"),
        ("[", "isn't JSON"),
        ('{"findings": [], "findings": []}', "`findings` twice"),
        ("3", "a list of findings, or an object"),
        ('"x"', "a list of findings, or an object"),
        ({"outcomes": []}, "give `findings`"),
        ({"findings": {}}, "`findings` is a list"),
        ({"findings": [], "extra": 1}, "unknown key `extra`"),
        ({"findings": [], "outcomes": {}}, "`outcomes` is a list"),
        ({"findings": [], "split": "yes"}, "`split` is true or false"),
        ([1], "finding 1 is an object"),
        ([{"mechanism": "a"}], "finding 1: give `mark`"),
        ([{"mark": "blocking", "mechanism": "a"}], "finding 1: `mark` is `blocks`, `ticket` (a ticket to fix it) or `note`, not `blocking`"),
        ([{"mark": "note"}], "finding 1: give `mechanism`"),
        ([{"mark": "note", "mechanism": "  "}], "finding 1: `mechanism` is empty"),
        ([{"mark": "note", "mechanism": 3}], "finding 1: `mechanism` is text"),
        ([{"mark": "note", "mechanism": "a`b"}], "finding 1: `mechanism` has a backtick"),
        ([{"mark": "note", "mechanism": "a\nb"}], "finding 1: `mechanism` has a control character"),
        ([{"mark": "note", "mechanism": "x" * 81}], "finding 1: `mechanism` is longer than 80 characters"),
        ([{"mark": "note", "mechanism": "a", "colour": "red"}], "finding 1: unknown key `colour`"),
        ([{"mark": "note", "mechanism": "a"}, {"mark": "blocks", "mechanism": "b"}], "finding 2 is marked blocks but has no `reproducer`"),
        ([{"mark": "blocks", "mechanism": "b", "reproducer": " "}], "finding 1 is marked blocks but has no `reproducer`"),
        ([{"mark": "note", "mechanism": "a", "reproducer": 5}], "finding 1: `reproducer` is text"),
        ([{"mark": "note", "mechanism": "a", "covered": "yes"}], "finding 1: `covered` is true or false"),
        ([{"mark": "note", "mechanism": "a", "contested": 1}], "finding 1: `contested` is true or false"),
        ([{"mark": "note", "mechanism": "a", "contested": True}], "finding 1 is contested (kept after a contest), so it is marked blocks"),
        ([{"mark": "note", "mechanism": "a", "security": "yes", "area": "x"}], "finding 1: `security` is `change` (a security problem the change adds) or `main`"),
        ([{"mark": "note", "mechanism": "a", "security": "change"}], "finding 1 is a security finding: give its `area`"),
        ([{"mark": "note", "mechanism": "a", "area": "auth"}], "finding 1: `area` goes only with `security`"),
        ([{"mark": "note", "mechanism": "a", "security": "change", "area": "a`b"}], "finding 1: `area` has a backtick"),
        ([{"mark": "note", "mechanism": "a", "issue": 0}], "finding 1: `issue` is an issue's number"),
        ([{"mark": "note", "mechanism": "a", "issue": True}], "finding 1: `issue` is an issue's number"),
        ([{"mark": "note", "mechanism": "a", "issue": "#x"}], "finding 1: `issue` is an issue's number"),
        ([{"mark": "note", "mechanism": "a", "issue": 123456789}], "finding 1: `issue` is an issue's number"),
        ({"findings": [], "outcomes": [3]}, "outcome 1 is an object"),
        ({"findings": [], "outcomes": [{"finding": 1}]}, "outcome 1: give `outcome`"),
        ({"findings": [], "outcomes": [{"outcome": "fixed"}]}, "outcome 1: `outcome` is `contested`, `fail-closed` or `split`, not `fixed`"),
        ({"findings": [], "outcomes": [{"outcome": "contested", "ruling": "overturned"}]}, "outcome 1: give `finding`"),
        ({"findings": [], "outcomes": [{"outcome": "contested", "finding": 0, "ruling": "kept"}]}, "outcome 1: `finding` is the number"),
        ({"findings": [], "outcomes": [{"outcome": "contested", "finding": 1}]}, "outcome 1: give `ruling`"),
        ({"findings": [], "outcomes": [{"outcome": "contested", "finding": 1, "ruling": "upheld"}]}, "outcome 1: `ruling` is `kept` or `overturned`, not `upheld`"),
        ({"findings": [], "outcomes": [{"outcome": "contested", "finding": 1, "ruling": "overturned", "mechanism": "a"}]}, "outcome 1: unknown key `mechanism`"),
        ({"findings": [], "outcomes": [{"outcome": "fail-closed"}]}, "outcome 1: give `mechanism`"),
        ({"findings": [], "outcomes": [{"outcome": "fail-closed", "mechanism": "a", "issue": 3}]}, "outcome 1: unknown key `issue`"),
        ({"findings": [], "outcomes": [{"outcome": "split", "mechanism": "a"}]}, "outcome 1: give `issue`"),
        ({"findings": [], "outcomes": [{"outcome": "contested", "finding": 1, "ruling": "overturned"}] * 2}, "outcome 2: finding 1's contest is already ruled"),
        ({"findings": [], "outcomes": [{"outcome": "split", "mechanism": "a", "issue": 4}, {"outcome": "split", "mechanism": "a", "issue": 5}]}, "outcome 2: the part `a` is already split"),
        ({"findings": [], "outcomes": [{"outcome": "contested", "finding": 1, "ruling": "kept"}]}, "1 contest kept but 0 findings flagged contested"),
        ([{"mark": "blocks", "mechanism": "a", "reproducer": "x", "contested": True}], "0 contests kept but 1 finding flagged contested"),
    ],
)
def test_a_malformed_file_is_refused_naming_what_is_wrong(capsys, tmp_path, content, says):
    err = refused(capsys, tmp_path, content)
    assert says in err, err


def test_a_refusal_never_echoes_a_secret_reproducer(capsys, tmp_path):
    err = refused(capsys, tmp_path, [{"mark": "blocks", "mechanism": "a", "reproducer": "hunter2-token", "security": "change", "area": "auth", "bad": 1}])
    assert "hunter2" not in err


def test_the_help_lists_findings(capsys):
    with pytest.raises(SystemExit):
        cli.main(["review-record", "--help"])
    assert "--findings" in capsys.readouterr().out


# The python writer ------------------------------------------------------------


def test_the_python_writer_refuses_a_result_with_findings_and_a_spec():
    f = findings_mod.load("[]")
    with pytest.raises(reviews.RecordError, match="works the result out"):
        reviews.record(kind="round", round=1, commit=SHA, reviewers="spec", clean=True, findings=f)
    with pytest.raises(reviews.RecordError, match="spec"):
        reviews.record(kind="spec", round=1, body="# spec", reviewers="spec", clean=None, findings=f)
    assert "result=clean" in reviews.record(kind="round", round=1, commit=SHA, reviewers="spec", clean=None, findings=f)


# The reader -------------------------------------------------------------------


def test_a_rule_2_record_reads_back_field_for_field(capsys, tmp_path):
    (r,) = reviews.records_in(written(capsys, tmp_path, FULL))
    assert (r.kind, r.round, r.commit, r.rule, r.result, r.clean, r.from_split) == ("round", 2, SHA, 2, "not-clean", False, True)
    F, O = findings_mod.Finding, findings_mod.Outcome
    assert r.findings == (
        F(mark="blocks", mechanism="the requeue order", covered=True),
        F(mark="ticket", mechanism="label sync", issue=415),
        F(mark="note", mechanism="wording"),
        F(mark="blocks", mechanism="auth", security="change"),
        F(mark="blocks", mechanism="the requeue order", contested=True),
    )
    assert r.outcomes == (
        O(kind="contested", finding=2, ruling="kept"),
        O(kind="contested", finding=3, ruling="overturned"),
        O(kind="fail-closed", mechanism="the merge gate"),
        O(kind="split", mechanism="the preview reader", issue=416),
    )


def test_an_empty_rule_2_record_reads_back_clean(capsys, tmp_path):
    (r,) = reviews.records_in(written(capsys, tmp_path, []))
    assert (r.rule, r.result, r.findings, r.outcomes, r.from_split) == (2, "clean", (), (), False)


def test_records_without_rule_2_read_exactly_as_before(capsys):
    code = cli.main(["review-record", *ROUND, "--not-clean"])
    out, _ = capsys.readouterr()
    assert code == 0
    (r,) = reviews.records_in(out)
    assert r == reviews.Record(kind="round", round=2, commit=SHA, reviewers=("standards", "spec", "correctness"), result="not-clean",
                               diff="unknown", lines="unknown")
    assert (r.rule, r.findings, r.outcomes, r.from_split) == (None, (), (), False)
    assert "rule=" not in out and "workflow:finding" not in out


def _machine(out):
    return [l for l in out.splitlines() if l.startswith("<!-- workflow:")]


def _mangled(capsys, tmp_path, change):
    lines = _machine(written(capsys, tmp_path, FULL))
    return reviews.records_in("\n".join(change(lines)))


@pytest.mark.parametrize(
    "change",
    [
        pytest.param(lambda ls: ls[:3] + ls[4:], id="a finding line missing"),
        pytest.param(lambda ls: ls[:-2] + ls[-1:], id="an outcome line missing"),
        pytest.param(lambda ls: ls[:2] + ["text between"] + ls[2:], id="text between its lines"),
        pytest.param(lambda ls: ls[:2] + [""] + ls[2:], id="a blank line between its lines"),
        pytest.param(lambda ls: [ls[0], ls[2], ls[1], *ls[3:]], id="findings out of order"),
        pytest.param(lambda ls: [ls[0].replace("findings=5", "findings=4"), *ls[1:]], id="a count that disagrees"),
        pytest.param(lambda ls: [ls[0].replace("result=not-clean", "result=clean"), *ls[1:]], id="a result the marks don't give"),
        pytest.param(lambda ls: [ls[0].replace("split=yes", "split=maybe"), *ls[1:]], id="a split flag that isn't yes or no"),
        pytest.param(lambda ls: [ls[0].replace("rule=2", "rule=3"), *ls[1:]], id="another rule"),
        pytest.param(lambda ls: [*ls[:1], ls[1].replace("mark=blocks", "mark=Blocks"), *ls[2:]], id="a mark not as written"),
        pytest.param(lambda ls: [*ls[:1], ls[1].replace("the%20requeue", "the requeue"), *ls[2:]], id="a mechanism not encoded"),
        pytest.param(lambda ls: [*ls[:1], ls[1].replace("%20", "%2x"), *ls[2:]], id="a broken encoding"),
        pytest.param(lambda ls: [*ls[:1], ls[1].replace("issue=none", "issue=0"), *ls[2:]], id="an issue zero"),
        pytest.param(lambda ls: [*ls[:4], ls[4].replace("mechanism=auth", "mechanism="), *ls[5:]], id="an empty mechanism"),
        pytest.param(lambda ls: [*ls[:5], ls[5].replace("contested=yes", "contested=no"), *ls[6:]], id="kept contests that don't add up"),
        pytest.param(lambda ls: ["```", *ls], id="after a fence"),
        pytest.param(lambda ls: [ls[0], "```", *ls[1:]], id="a fence among its lines"),
    ],
)
def test_a_rule_2_record_is_read_only_whole(capsys, tmp_path, change):
    assert _mangled(capsys, tmp_path, change) == []


def test_a_finding_or_outcome_line_alone_is_no_record(capsys, tmp_path):
    lines = _machine(written(capsys, tmp_path, FULL))
    assert reviews.records_in("\n".join(lines[1:])) == []


def test_a_whole_record_beside_a_broken_one_is_still_read(capsys, tmp_path):
    good = written(capsys, tmp_path, FULL)
    broken = "\n".join(_machine(good)[:-3])
    got = reviews.records_in(broken + "\n" + good)
    assert len(got) == 1 and got[0].rule == 2 and len(got[0].findings) == 5


def test_read_keeps_who_posted_a_rule_2_record(capsys, tmp_path):
    text = written(capsys, tmp_path, [])
    (r,) = reviews.read([{"id": 5, "user": {"login": "owner"}, "created_at": "t", "body": text.replace("\n", "\r\n")}])
    assert (r.rule, r.author, r.comment_id) == (2, "owner", 5)


def test_the_reader_never_raises_on_odd_lines():
    for text in [
        f"<!-- workflow:review kind=round round=1 commit={SHA} reviewers=spec rule=2 findings=99999 outcomes=0 split=no result=clean -->",
        f"<!-- workflow:review kind=round round=1 commit={SHA} reviewers=spec rule=2 findings=1 outcomes=0 split=no result=clean -->",
        "<!-- workflow:finding n=1 mark=note mechanism=%ZZ covered=no contested=no security=no issue=none -->",
        "<!-- workflow:outcome n=1 kind=split mechanism=a issue=99999999999999999999999 -->",
    ]:
        assert reviews.records_in(text) == []


# Docs -------------------------------------------------------------------------


def test_the_changelog_notes_it_under_unreleased():
    unreleased = since_0110()
    assert "#370" in unreleased and "--findings" in unreleased and "rule=2" in unreleased
