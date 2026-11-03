"""`workflow ready --first` (#372, spec #412 "Runs"): the given tickets start
right after `workflow:infra` tickets, in the order given, ahead of the rest."""

import json

import pytest

from workflow import cli
from workflow.issues import parse_number_list, parse_numbers, readiness, startable

INFRA = ("ready-for-agent", "workflow:infra")


def issue(n, labels=("ready-for-agent",), body="", state="open", reason=None):
    return {"number": n, "state": state, "state_reason": reason, "labels": [{"name": l} for l in labels], "body": body, "title": f"t{n}"}


# ---------- startable ----------


def test_given_tickets_come_right_after_infra_in_the_order_given():
    vs = readiness([issue(10), issue(11), issue(12, labels=INFRA), issue(13), issue(14)], [])
    assert [v.number for v in startable(vs, [], 5, first=[14, 11])] == [12, 14, 11, 10, 13]


def test_without_first_the_order_is_as_today():
    vs = readiness([issue(10), issue(11), issue(12, labels=INFRA), issue(13)], [])
    assert [v.number for v in startable(vs, [], 5)] == [12, 10, 11, 13]
    assert [v.number for v in startable(vs, [], 5, first=[])] == [12, 10, 11, 13]


def test_given_tickets_take_the_slots_ahead_of_the_rest():
    vs = readiness([issue(10), issue(11), issue(12, labels=INFRA), issue(13)], [])
    assert [v.number for v in startable(vs, [], 2, first=[13])] == [12, 13]


def test_a_given_ticket_that_isnt_ready_is_left_out():
    vs = readiness([issue(10), issue(11, body="## Blocked by\n\n#10\n"), issue(12)], [])
    assert [v.number for v in startable(vs, [], 5, first=[11, 99, 12])] == [12, 10]


def test_a_given_ticket_takes_its_area_first():
    vs = readiness([issue(10, body="Area: a"), issue(11, body="Area: a"), issue(12)], [])
    assert [v.number for v in startable(vs, [], 5, first=[11])] == [11, 12]
    assert [v.number for v in startable(vs, ["a"], 5, first=[11])] == [12]


def test_an_infra_ticket_given_too_stays_among_the_infra_tickets():
    vs = readiness([issue(10), issue(11, labels=INFRA), issue(12, labels=INFRA), issue(13)], [])
    assert [v.number for v in startable(vs, [], 5, first=[13, 12])] == [11, 12, 13, 10]


def test_a_long_part_is_refused_by_the_kit_not_by_python():
    import sys

    if hasattr(sys, "set_int_max_str_digits"):
        old = sys.get_int_max_str_digits()
        sys.set_int_max_str_digits(0)  # no limit: the refusal must not rest on Python's
        try:
            with pytest.raises(ValueError, match="not a ticket number: '1{20}…'"):
                parse_number_list("5, " + "1" * 5000)
        finally:
            sys.set_int_max_str_digits(old)
    assert parse_number_list("0" * 4300 + "7") == [7]  # leading zeros don't count
    with pytest.raises(ValueError, match="not a ticket number: 'x{20}…'"):
        parse_number_list("x" * 100)
    with pytest.raises(ValueError, match="not a ticket number: '12x'$"):
        parse_number_list("12x")


def test_parse_number_list_keeps_the_order_given():
    assert parse_number_list("14, #11,14 ,, 3") == [14, 11, 3]
    assert parse_number_list(None) == []
    with pytest.raises(ValueError, match="x1"):
        parse_number_list("12, x1")


@pytest.mark.parametrize("odd", ["\uff17", "\u0663", "\u00b2", "1" * 5000])
def test_only_plain_digits_are_ticket_numbers(odd):
    for parse in (parse_number_list, parse_numbers):
        with pytest.raises(ValueError, match="not a ticket number"):
            parse(f"5, {odd}")


# ---------- the `ready` command ----------


@pytest.fixture
def ready_files(tmp_path, monkeypatch):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname = "demo"\nrepo = "acme/demo"\n[areas]\nmessages = ["src/messages/**"]\nreadings = ["src/readings/**"]\n'
    )
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    issues = [
        issue(1, body="Area: messages"),
        issue(2, body="Area: readings"),
        issue(3, labels=INFRA),
        issue(4),
        issue(5, body="## Blocked by\n\n#1\n"),
        issue(6),
    ]
    (tmp_path / "issues.json").write_text(json.dumps(issues))
    (tmp_path / "prs.json").write_text("[]")
    return ["ready", "--issues", str(tmp_path / "issues.json"), "--prs", str(tmp_path / "prs.json")]


def _start_now(capsys):
    return json.loads(capsys.readouterr().out)["start_now"]


def test_ready_cli_first(ready_files, capsys):
    assert cli.main([*ready_files, "--json", "--slots", "6", "--first", "6,#2"]) == 0
    assert _start_now(capsys) == [3, 6, 2, 1, 4]


def test_ready_cli_without_first_is_as_today(ready_files, capsys):
    assert cli.main([*ready_files, "--json", "--slots", "6"]) == 0
    assert _start_now(capsys) == [3, 1, 2, 4, 6]


def test_ready_cli_first_leaves_out_a_ticket_that_isnt_ready(ready_files, capsys):
    assert cli.main([*ready_files, "--json", "--slots", "2", "--first", "5,4"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["start_now"] == [3, 4]
    assert [v["number"] for v in out["not_ready"]] == [5]


def test_ready_cli_first_with_only_and_running_area(ready_files, capsys):
    assert cli.main([*ready_files, "--json", "--slots", "6", "--only", "1,2,4", "--first", "4,2,6", "--running-area", "messages"]) == 0
    assert _start_now(capsys) == [4, 2]


def test_ready_cli_first_in_text(ready_files, capsys):
    assert cli.main([*ready_files, "--slots", "3", "--first", "4"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "start now: #3, #4, #1"


def test_ready_cli_first_empty_is_as_today(ready_files, capsys):
    assert cli.main([*ready_files, "--json", "--slots", "6", "--first", ""]) == 0
    assert _start_now(capsys) == [3, 1, 2, 4, 6]


def test_ready_cli_first_bad_number_is_a_clean_error(ready_files, capsys):
    assert cli.main([*ready_files, "--first", "4, abc"]) == 2
    err = capsys.readouterr().err
    assert "abc" in err and "Traceback" not in err
    for flag in ("--first", "--exclude", "--only", "--override"):
        for odd in ("\u00b2", "\u0663", "1" * 5000):
            assert cli.main([*ready_files, flag, f"4, {odd}"]) == 2
            err = capsys.readouterr().err
            assert "not a ticket number" in err and "invalid literal" not in err and "Exceeds" not in err
