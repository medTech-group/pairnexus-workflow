"""The findings file and new-rule review records (#370, spec #412 "Records and
clean"): `workflow review-record --findings F` writes a `rule=2` record whose
result is worked out from the findings' marks, and `reviews.records_in` reads
it back only whole."""

import json
import sys

import pytest

from conftest import KIT
from workflow import cli, findings as findings_mod, reviews
from changelog_notes import since_0110

SHA = "3f2a9c0b7de14a2c9e8f5d6b1a0c3e2f4d5b6a7c"
MARKER = "<!-- workflow:agent -->"
# What the hashes of a round's own changes add to its line (` diff=<64 hex> lines=<64 hex>`).
HASHES_ROOM = len(" diff= lines=") + 2 * 64
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


@pytest.mark.parametrize("name", ["a ~ b", "~~", "x~~ ~y", "fence ``` no"])
def test_a_mechanism_with_tildes_reads_back_and_three_backticks_are_refused(capsys, tmp_path, name):
    if "`" in name:
        assert "has a backtick" in refused(capsys, tmp_path, [{"mark": "note", "mechanism": name}])
        return
    out = written(capsys, tmp_path, {"findings": [{"mark": "ticket", "mechanism": name, "issue": 3}],
                                     "outcomes": [{"outcome": "split", "mechanism": name, "issue": 4}]})
    assert "~" not in "".join(l for l in out.splitlines() if l.startswith("<!-- workflow:"))
    (r,) = reviews.records_in(out)
    assert r.findings[0].mechanism == r.outcomes[0].mechanism == name


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


def test_a_spec_refusal_says_to_leave_out_findings_and_a_round_with_a_body_says_so(capsys, tmp_path):
    err = refused(capsys, tmp_path, [], "--kind", "spec", "--round", "2", "--reviewers", "spec,correctness", "--clean")
    assert "leave it out" in err and "give --clean" not in err
    spec = tmp_path / "spec.md"
    spec.write_text("# A spec\n")
    err = refused(capsys, tmp_path, [], "--kind", "round", "--round", "2", "--body", str(spec), "--reviewers", "spec")
    assert "a round or a pass names a commit" in err


def test_the_other_flags_are_checked_before_the_file_is_read(capsys, tmp_path):
    code, out, err = run(capsys, "--kind", "round", "--round", "2", "--reviewers", "spec", "--findings", str(tmp_path / "missing.json"))
    assert code == 2 and "give --commit" in err


def test_a_record_past_githubs_comment_limit_is_refused(capsys, tmp_path):
    many = [{"mark": "note", "mechanism": f"part {i} " + "é" * 60} for i in range(200)]
    err = refused(capsys, tmp_path, many)
    assert f"past the {reviews.RECORD_LIMIT} a comment holds with a cloud session's footer" in err


def _units(text):
    return len(text.encode("utf-16-le")) // 2


def _sized(total, filler="f" * 80, **hashes):
    """Findings whose record comes to exactly `total` UTF-16 units: parts
    named `filler`, then parts of 80 `f` to come within 200 to 470 units of
    it, then one part named with `a` (2 units each, its text and its line) and
    `é` (7: one in its text, six encoded), which closes any such gap."""
    def text(found):
        return reviews.record(kind="round", round=1, commit=SHA, reviewers="correctness", clean=None, findings=found, **hashes)

    def found(big, small, a, e):
        names = [filler] * big + ["f" * 80] * small + ["a" * a + "é" * e]
        return findings_mod.checked([findings_mod.Finding(mark="note", mechanism=n) for n in names], (), False)

    def most(size, under):
        n = 0
        while size(n + 1) <= under:
            n += 1
        return n

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(reviews, "RECORD_LIMIT", 10**9)  # measured with the limit lifted
        big = most(lambda n: _units(text(found(n, 0, 1, 0))), total - 3000)
        small = most(lambda n: _units(text(found(big, n, 1, 0))), total - 200)
        gap = total - _units(text(found(big, small, 1, 0)))
    e = next(e for e in range(80) if (gap - 7 * e) % 2 == 0 and 0 <= (gap - 7 * e) // 2 < 80 - e)
    return found(big, small, 1 + (gap - 7 * e) // 2, e), text


def test_the_room_for_the_hashes_is_what_they_add():
    assert reviews._HASHES_ROOM == HASHES_ROOM


@pytest.mark.parametrize("hashes", [{"diff": "a" * 64, "lines": "b" * 64}, {}])
@pytest.mark.parametrize("filler", ["f" * 80, "😀" * 80], ids=["ascii", "emoji"])
def test_the_size_limit_holds_on_both_sides_of_it_hashed_or_not(hashes, filler):
    room = 0 if hashes else HASHES_ROOM
    f, text = _sized(reviews.RECORD_LIMIT - room, filler, **hashes)
    assert _units(text(f)) == reviews.RECORD_LIMIT - room
    f, text = _sized(reviews.RECORD_LIMIT - room + 1, filler, **hashes)
    with pytest.raises(reviews.RecordError, match=f"would come to {reviews.RECORD_LIMIT + 1} characters with its hashes, counted as GitHub counts them \\(UTF-16 units\\), past the {reviews.RECORD_LIMIT}"):
        text(f)


def test_the_size_limit_counts_utf16_units_not_code_points():
    # 55 parts of 80 emoji: under the limit in code points, over it in UTF-16 units.
    f = findings_mod.checked([findings_mod.Finding(mark="note", mechanism="😀" * 80) for _ in range(55)], (), False)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(reviews, "RECORD_LIMIT", 10**9)
        text = reviews.record(kind="round", round=1, commit=SHA, reviewers="correctness", clean=None, findings=f, diff="a" * 64, lines="b" * 64)
    assert len(text) < reviews.RECORD_LIMIT < _units(text)
    with pytest.raises(reviews.RecordError, match="past the"):
        reviews.record(kind="round", round=1, commit=SHA, reviewers="correctness", clean=None, findings=f, diff="a" * 64, lines="b" * 64)


def test_a_record_with_room_for_its_hashes_is_read_back_whole_once_hashed():
    f, text = _sized(reviews.RECORD_LIMIT - HASHES_ROOM)
    hashed = reviews.record(kind="round", round=1, commit=SHA, reviewers="correctness", clean=None, findings=f, diff="a" * 64, lines="b" * 64)
    assert _units(hashed) == reviews.RECORD_LIMIT
    assert _units(hashed + reviews._CLOUD_FOOTER) == reviews.COMMENT_LIMIT
    assert len(reviews.records_in(hashed + reviews._CLOUD_FOOTER)[0].findings) == len(f.findings)


def test_a_refusal_shows_the_findings_path_plainly_and_a_long_ones_end(capsys, tmp_path):
    code, out, err = run(capsys, *ROUND, "--findings", "/no/such/findings.json")
    assert "--findings names no file: `/no/such/findings.json`" in err
    long = str(tmp_path / ("d" * 90) / "findings.json")
    code, out, err = run(capsys, *ROUND, "--findings", long)
    assert err.rstrip().endswith("/findings.json`") and "…" in err


@pytest.mark.parametrize("depth", [50, sys.getrecursionlimit() * 2])
def test_a_deeply_nested_value_is_refused_in_words(capsys, tmp_path, depth):
    err = refused(capsys, tmp_path, '{"findings": [], "split": ' + "[" * depth + "]" * depth + "}")
    assert "Traceback" not in err
    # Deep past the recursion limit, the JSON reader of one Python refuses it
    # and another reads it: either way, words.
    assert "not a list" in err if depth == 50 else ("not a list" in err or "isn't JSON" in err)


@pytest.mark.parametrize("number", ["1e400", "-1e400"])
def test_a_number_too_large_to_hold_is_refused_as_written(capsys, tmp_path, number):
    err = refused(capsys, tmp_path, '{"findings": [], "split": ' + number + "}")
    assert f"`{number}` is too large a number" in err and "Infinity" not in err


def test_a_backtick_in_the_findings_path_is_escaped(capsys, tmp_path):
    code, out, err = run(capsys, *ROUND, "--findings", "/no/a`b.json")
    assert "--findings names no file: `/no/a\\`b.json`" in err


def test_a_file_starting_with_a_byte_order_mark_is_read(capsys, tmp_path):
    out = written(capsys, tmp_path, b"\xef\xbb\xbf[]")
    assert "rule=2 findings=0 outcomes=0 split=no result=clean" in out


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
        ('{"findings": [], "findings": []}', "`\"findings\"` twice"),
        ("3", "a list of findings, or an object"),
        ('"x"', "a list of findings, or an object"),
        ({"outcomes": []}, "give `findings`"),
        ({"findings": {}}, "`findings` is a list"),
        ({"findings": [], "extra": 1}, "unknown key `\"extra\"`"),
        ({"findings": [], "a`b": 1}, "unknown key `\"a\\`b\"`"),
        ({"findings": [], "outcomes": {}}, "`outcomes` is a list"),
        ({"findings": [], "split": "yes"}, "`split` is true or false"),
        ([1], "finding 1 is an object"),
        ([{"mechanism": "a"}], "finding 1: give `mark`"),
        ([{"mark": "blocking", "mechanism": "a"}], "finding 1: `mark` is `blocks`, `ticket` (a ticket to fix it) or `note`"),
        ([{"mark": "note"}], "finding 1: give `mechanism`"),
        ([{"mark": "note", "mechanism": "  "}], "finding 1: `mechanism` is empty"),
        ([{"mark": "note", "mechanism": 3}], "finding 1: `mechanism` is text"),
        ([{"mark": "note", "mechanism": "a`b"}], "finding 1: `mechanism` has a backtick"),
        ([{"mark": "note", "mechanism": "a\nb"}], "finding 1: `mechanism` has a control or invisible character"),
        ([{"mark": "note", "mechanism": "a\u202eb"}], "finding 1: `mechanism` has a control or invisible character"),
        ([{"mark": "note", "mechanism": "the ~~~ fence rule"}], "finding 1: `mechanism` has `~~~`, which reads as a code fence"),
        ([{"mark": "note", "mechanism": "a", "security": "main", "area": "x ~~~"}], "finding 1: `area` has `~~~`"),
        ({"findings": [], "outcomes": [{"outcome": "fail-closed", "mechanism": "~~~"}]}, "outcome 1: `mechanism` has `~~~`"),
        ({"findings": [], "split": "true"}, "`split` is true or false (in JSON, without quotes), not `\"true\"`"),
        ({"findings": [], "split": None}, "not `null`"),
        ({"findings": [], "split": [[1]]}, "not a list"),
        ({"findings": [], "outcomes": [{"outcome": "contested", "finding": {"a": 1}, "ruling": "kept"}]}, "not an object"),
        ('{"findings": [], "split": NaN}', "`NaN` is no JSON value"),
        ('[{"mark": "ticket", "mechanism": "a", "issue": Infinity}]', "`Infinity` is no JSON value"),
        ({"findings": [], "outcomes": [{"outcome": "contested", "finding": "2", "ruling": "kept"}]}, "from 1 to 999, not `\"2\"`"),
        ({"findings": [], "outcomes": [{"outcome": "split", "mechanism": "a", "issue": True}]}, "as 415 or \"#415\", not `true`"),
        ([{"mark": "note", "mechanism": "x" * 81}], "finding 1: `mechanism` is longer than 80 characters"),
        ([{"mark": "note", "mechanism": "a", "colour": "red"}], "finding 1: unknown key `\"colour\"`"),
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
        ({"findings": [], "outcomes": [{"outcome": "fixed"}]}, "outcome 1: `outcome` is `contested`, `fail-closed` or `split`, not `\"fixed\"`"),
        ({"findings": [], "outcomes": [{"outcome": "contested", "ruling": "overturned"}]}, "outcome 1: give `finding`"),
        ({"findings": [], "outcomes": [{"outcome": "contested", "finding": 0, "ruling": "kept"}]}, "outcome 1: `finding` is the number"),
        ({"findings": [], "outcomes": [{"outcome": "contested", "finding": 1}]}, "outcome 1: give `ruling`"),
        ({"findings": [], "outcomes": [{"outcome": "contested", "finding": 1, "ruling": "upheld"}]}, "outcome 1: `ruling` is `kept` or `overturned`, not `\"upheld\"`"),
        ({"findings": [], "outcomes": [{"outcome": "contested", "finding": 1, "ruling": "overturned", "mechanism": "a"}]}, "outcome 1: unknown key `\"mechanism\"`"),
        ({"findings": [], "outcomes": [{"outcome": "fail-closed"}]}, "outcome 1: give `mechanism`"),
        ({"findings": [], "outcomes": [{"outcome": "fail-closed", "mechanism": "a", "issue": 3}]}, "outcome 1: unknown key `\"issue\"`"),
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


@pytest.mark.parametrize(
    "bad",
    [
        {"security": "token sent in redirect"},
        {"mark": "token sent in redirect"},
        {"covered": "token sent in redirect"},
        {"contested": "token sent in redirect"},
        {"issue": "token sent in redirect"},
        {"area": "token sent in redirect `"},
        {"mechanism": "token sent in redirect" * 5},
        {"mechanism": "token sent in redirect `"},
        {"reproducer": ["token sent in redirect"]},
    ],
)
def test_a_refusal_never_quotes_a_findings_values(capsys, tmp_path, bad):
    finding = {"mark": "blocks", "mechanism": "m", "reproducer": "r", "security": "change", "area": "auth", **bad}
    err = refused(capsys, tmp_path, [finding])
    assert "token" not in err and "finding 1" in err


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
        pytest.param(lambda ls: [ls[0].replace("findings=5 outcomes=4", "findings=4 outcomes=0"), *ls[1:6]], id="a finding line past the count"),
        pytest.param(lambda ls: [ls[0].replace("outcomes=4", "outcomes=3"), *ls[1:]], id="an outcome line past the count"),
        pytest.param(lambda ls: [ls[0], "```", *ls[1:]], id="a fence among its lines"),
    ],
)
def test_a_rule_2_record_is_read_only_whole(capsys, tmp_path, change):
    assert _mangled(capsys, tmp_path, change) == []


def test_a_finding_or_outcome_line_alone_is_no_record(capsys, tmp_path):
    lines = _machine(written(capsys, tmp_path, FULL))
    assert reviews.records_in("\n".join(lines[1:])) == []


def test_a_whole_record_is_read_from_its_own_comment_beside_a_broken_one(capsys, tmp_path):
    good = written(capsys, tmp_path, FULL)
    broken = "\n".join(_machine(good)[:-3])
    got = reviews.read([{"id": 1, "body": broken}, {"id": 2, "body": good}])
    assert [(r.comment_id, r.rule, len(r.findings)) for r in got] == [(2, 2, 5)]
    # In one comment, the broken record's lines are lines the good one doesn't
    # account for: neither counts.
    assert reviews.records_in(broken + "\n" + good) == []


@pytest.mark.parametrize(
    "where",
    [
        pytest.param(lambda t, x: t.replace(MARKER, MARKER + "\n" + x), id="after the marker"),
        pytest.param(lambda t, x: t.replace("\n" + MARKER, "\n\n" + x + "\n" + MARKER), id="after a blank line"),
        pytest.param(lambda t, x: t.replace(MARKER, " " + x + "\n" + MARKER), id="indented"),
        pytest.param(lambda t, x: t.replace(MARKER, x.upper() + "\n" + MARKER), id="upper-cased"),
        pytest.param(lambda t, x: t.replace(MARKER, x.replace("<!-- ", "<!--") + "\n" + MARKER), id="no space"),
        pytest.param(lambda t, x: x + "\n" + t, id="above it"),
        pytest.param(lambda t, x: t + "\n```\n" + x, id="after a fence"),
        pytest.param(lambda t, x: t.replace(MARKER, x.replace("finding n=2 mark=blocks mechanism=x covered=no contested=no security=no issue=none", "outcome n=1 kind=fail-closed mechanism=x") + "\n" + MARKER), id="an outcome line"),
    ],
)
def test_a_finding_or_outcome_line_anywhere_else_in_the_comment_leaves_the_record_unread(capsys, tmp_path, where):
    text = written(capsys, tmp_path, [{"mark": "note", "mechanism": "a"}])
    assert len(reviews.records_in(text)) == 1
    extra = "<!-- workflow:finding n=2 mark=blocks mechanism=x covered=no contested=no security=no issue=none -->"
    assert reviews.records_in(where(text, extra)) == []


def test_two_whole_records_in_one_comment_are_both_read(capsys, tmp_path):
    a = written(capsys, tmp_path, FULL)
    b = written(capsys, tmp_path, [{"mark": "note", "mechanism": "b"}], "--kind", "pass", "--round", "3", "--commit", SHA, "--reviewers", "correctness")
    got = reviews.records_in(a + "\n" + b)
    assert [(r.kind, r.rule, len(r.findings), len(r.outcomes)) for r in got] == [("round", 2, 5, 4), ("pass", 2, 1, 0)]


def test_a_comment_of_review_like_lines_is_read_one_line_past_each(monkeypatch):
    calls = []
    real = findings_mod._parse_finding
    monkeypatch.setattr(findings_mod, "_parse_finding", lambda line, n: calls.append(n) or real(line, n))
    line = f"<!-- workflow:review kind=round round=1 commit={SHA} reviewers=spec rule=2 findings=999 outcomes=0 split=no result=clean -->"
    assert reviews.records_in("\n".join([line] * 3000)) == []
    # Each review line reads at most the one under it, and stops there (one
    # with fewer than 999 lines under it reads none), never 999 for each.
    assert len(calls) == 3000 - 999


def test_old_records_beside_stray_finding_lines_read_as_before(capsys):
    cli.main(["review-record", *ROUND, "--clean"])
    out, _ = capsys.readouterr()
    extra = "<!-- workflow:finding n=1 mark=blocks mechanism=x covered=no contested=no security=no issue=none -->"
    (r,) = reviews.records_in(out + extra)
    assert (r.rule, r.result) == (None, "clean")


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
        f"<!-- workflow:review kind=round round=1 commit={SHA} reviewers=spec rule=2 findings=1 outcomes=0 split=no result=clean -->\n"
        "<!-- workflow:finding n=1 mark=note mechanism=\ud800 covered=no contested=no security=no issue=none -->",
        f"<!-- workflow:review kind=round round=1 commit={SHA} reviewers=spec rule=2 findings=0 outcomes=1 split=no result=clean -->\n"
        "<!-- workflow:outcome n=1 kind=fail-closed mechanism=\u00e9 -->",
    ]:
        assert reviews.records_in(text) == []


# Docs -------------------------------------------------------------------------


def test_the_changelog_notes_it_under_unreleased():
    unreleased = since_0110()
    assert "#370" in unreleased and "--findings" in unreleased and "rule=2" in unreleased
