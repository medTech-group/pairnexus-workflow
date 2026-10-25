"""#248: the charter and the run's state with a merge queue (#243's seam 4),
through the CLI as the other charter tests do. With the queue on, a waiver is
refused at `charter validate` and at `state init`; the run's state records the
queue's state at kick-off and reports a change; `workflow state drop` decides
each answer to an enqueue and records it on the ticket."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from workflow import charter, state

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"
CHARTER_DOC = KIT / "docs/charter.md"

HEAD_A = "a" * 40
HEAD_B = "b" * 40
HEAD_C = "c" * 40


def _cli(*args, env=None):
    e = {**os.environ, **(env or {})}
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, env=e)


def _profile(tmp_path, checks=("CI", "Lint")):
    text = (
        '[project]\nname="d"\nrepo="a/d"\nowner="o"\nruleset = true\n'
        f"[ci]\nrequired_checks={json.dumps(list(checks))}\n"
        '[[release.steps]]\nname="ship"\nrun="x"\n'
    )
    (tmp_path / ".claude/workflow").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(text)
    return {"CLAUDE_PROJECT_DIR": str(tmp_path)}


def _charter_file(tmp_path, mode="session", waived=(), approved=False):
    c = charter.defaults(["ship"])
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    c["merge"] = {"mode": mode, "waived_checks": list(waived)}
    if approved:
        c["approved"] = {"by": "o", "at": "2026-01-01T00:00:00Z", "source": "chat"}
    f = tmp_path / "c.json"
    f.write_text(json.dumps(c))
    return f


def _init(tmp_path, env, *extra, waived=()):
    f = _charter_file(tmp_path, waived=waived, approved=True)
    return _cli("state", "init", "--charter", str(f), "--run-id", "r", "--read-through", "0", *extra, env=env)


# ---------- waivers with the queue on ----------


def test_validate_refuses_a_waiver_with_the_queue_on(tmp_path):
    env = _profile(tmp_path)
    f = _charter_file(tmp_path, waived=["CI"])
    p = _cli("charter", "validate", str(f), "--queue", "on", env=env)
    assert p.returncode == 1
    assert "merge.waived_checks" in p.stderr and "merge queue" in p.stderr


@pytest.mark.parametrize("queue", [["--queue", "off"], []])
def test_validate_is_unchanged_with_the_queue_off_or_not_given(tmp_path, queue):
    env = _profile(tmp_path)
    p = _cli("charter", "validate", str(_charter_file(tmp_path, waived=["CI"])), *queue, env=env)
    assert p.returncode == 0, p.stderr
    # A waiver outside the required checks is still refused, as before.
    p = _cli("charter", "validate", str(_charter_file(tmp_path, waived=["Nope"])), *queue, env=env)
    assert p.returncode == 1 and "not one of the profile's ci.required_checks" in p.stderr


def test_validate_with_the_queue_on_and_no_waivers_is_fine_in_every_mode(tmp_path):
    env = _profile(tmp_path)
    for mode in sorted(charter.MERGE_MODES):
        p = _cli("charter", "validate", str(_charter_file(tmp_path, mode=mode)), "--queue", "on", env=env)
        assert p.returncode == 0, (mode, p.stderr)


def test_the_merge_modes_keep_their_names():
    assert charter.MERGE_MODES == {"auto-merge", "session", "owner"}


def test_validate_refuses_a_waiver_with_the_queue_on_without_a_profile(tmp_path):
    f = _charter_file(tmp_path, waived=["CI"])
    p = _cli("charter", "validate", str(f), "--queue", "on", env={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert p.returncode == 1 and "merge queue" in p.stderr


def test_the_rule_is_one_function():
    c = charter.defaults(["ship"])
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    c["merge"] = {"mode": "session", "waived_checks": ["CI"]}
    assert any("merge queue" in x for x in charter.validate(c, queue=True))
    assert charter.validate(c, queue=False) == charter.validate(c) == []


def test_state_init_refuses_a_waiver_with_the_queue_on(tmp_path):
    env = _profile(tmp_path)
    p = _init(tmp_path, env, "--queue", "on", waived=["CI"])
    assert p.returncode == 1 and "merge.waived_checks" in p.stderr and "merge queue" in p.stderr


@pytest.mark.parametrize("queue", [["--queue", "off"], []])
def test_state_init_is_unchanged_with_the_queue_off_or_not_given(tmp_path, queue):
    env = _profile(tmp_path)
    p = _init(tmp_path, env, *queue, waived=["CI"])
    assert p.returncode == 0, p.stderr


def test_questions_say_no_waivers_with_the_queue_on(tmp_path):
    env = _profile(tmp_path)
    merge = lambda out: next(q for q in json.loads(out) if q["key"] == "merge")  # noqa: E731
    on = merge(_cli("charter", "questions", "--queue", "on", env=env).stdout)
    assert "No waivers" in on["note"] and "merge queue" in on["note"]
    assert on["options"] == ["auto-merge", "session", "owner"]
    assert "waived" not in on["ask"]
    off = merge(_cli("charter", "questions", env=env).stdout)
    assert "note" not in off and "waived" in off["ask"]


# ---------- the queue's state at kick-off, and a change ----------


@pytest.mark.parametrize("given,recorded", [("on", True), ("off", False), (None, None)])
def test_state_init_records_the_queue_seen_at_kick_off(tmp_path, given, recorded):
    env = _profile(tmp_path)
    p = _init(tmp_path, env, *(["--queue", given] if given else []))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["merge_queue"] is recorded


def _body(tmp_path, s):
    f = tmp_path / "body.md"
    f.write_text(state.put("The run.", s))
    return f


def _started(tmp_path, env, queue="off"):
    p = _init(tmp_path, env, "--queue", queue)
    assert p.returncode == 0, p.stderr
    s = json.loads(p.stdout)
    s["tickets"] = {"12": {"status": "in-review", "pr": 40}}
    return _body(tmp_path, s)


def _queue(body, out, value, env):
    return _cli("state", "queue", "--body", str(body), "--queue", value, "--out", str(out), env=env)


def test_a_different_queue_state_is_reported_as_a_change_once(tmp_path):
    env = _profile(tmp_path)
    body = _started(tmp_path, env, "off")
    out = tmp_path / "new.md"
    p = _queue(body, out, "off", env)
    assert p.returncode == 0, p.stderr
    assert p.stdout.split(":")[0] == "unchanged"
    p = _queue(body, out, "on", env)
    assert p.returncode == 0, p.stderr
    assert p.stdout.split(":")[0] == "changed"
    assert "on" in p.stdout and "off" in p.stdout
    assert state.get(out.read_text())["merge_queue"] is True
    # Recorded, so the next check-in doesn't report it again; turned off again, it is a change.
    p = _queue(out, out, "on", env)
    assert p.stdout.split(":")[0] == "unchanged"
    p = _queue(out, out, "off", env)
    assert p.stdout.split(":")[0] == "changed"
    assert state.get(out.read_text())["merge_queue"] is False


def test_a_change_to_on_says_the_charters_waivers_stop(tmp_path):
    env = _profile(tmp_path)
    p = _init(tmp_path, env, "--queue", "off", waived=["CI"])
    assert p.returncode == 0, p.stderr
    body = _body(tmp_path, json.loads(p.stdout))
    out = tmp_path / "new.md"
    p = _queue(body, out, "on", env)
    assert p.stdout.startswith("changed:") and "waived checks no longer apply" in p.stdout
    p = _queue(out, out, "off", env)
    assert p.stdout.startswith("changed:") and "waived checks apply again" in p.stdout


def test_a_first_sighting_of_the_queue_on_says_the_charters_waivers_dont_apply(tmp_path):
    env = _profile(tmp_path)
    p = _init(tmp_path, env, waived=["CI"])
    assert p.returncode == 0, p.stderr
    body = _body(tmp_path, json.loads(p.stdout))
    out = tmp_path / "new.md"
    p = _queue(body, out, "on", env)
    assert p.stdout.startswith("recorded:") and "waived checks no longer apply" in p.stdout
    p = _queue(body, out, "off", env)
    assert p.stdout.startswith("recorded:") and "waived" not in p.stdout


def test_no_waivers_no_waiver_words(tmp_path):
    env = _profile(tmp_path)
    body = _started(tmp_path, env, "off")
    out = tmp_path / "new.md"
    for value in ("on", "off"):
        p = _queue(body if value == "on" else out, out, value, env)
        assert p.stdout.startswith("changed:") and "waived" not in p.stdout


def test_a_queue_state_with_none_recorded_is_recorded_not_a_change(tmp_path):
    env = _profile(tmp_path)
    s = state.empty(None)
    s["tickets"] = {}
    body = _body(tmp_path, s)
    out = tmp_path / "new.md"
    p = _queue(body, out, "on", env)
    assert p.returncode == 0, p.stderr
    assert p.stdout.split(":")[0] == "recorded"
    assert state.get(out.read_text())["merge_queue"] is True


def test_the_recorded_queue_state_must_be_true_false_or_null():
    s = state.empty(None)
    s["merge_queue"] = "on"
    assert any("merge_queue" in x for x in state.validate(s))


# ---------- state drop ----------


class Run:
    """A tracking issue's body on disk, and `state drop` against it."""

    def __init__(self, tmp_path):
        self.env = _profile(tmp_path)
        self.body = _started(tmp_path, self.env, "on")

    def drop(self, answer, head=HEAD_A, ticket="12"):
        p = _cli(
            "state", "drop", "--body", str(self.body), "--ticket", ticket, "--head", head,
            "--answer", answer, "--out", str(self.body), env=self.env,
        )
        assert p.returncode == 0, p.stderr
        return p.stdout.strip()

    def ticket(self, n="12"):
        return state.get(self.body.read_text())["tickets"][n]


@pytest.fixture
def run(tmp_path):
    return Run(tmp_path)


def test_a_heads_first_accepted_enqueue_is_in_queue(run):
    assert run.drop("202-enqueued") == "in_queue"
    t = run.ticket()
    assert t["queue_heads"] == {HEAD_A: 0}
    assert t["queue_result"] == "in_queue"


def test_still_waiting_is_waiting_and_never_a_drop(run):
    assert run.drop("200-waiting") == "waiting"
    assert run.drop("200-waiting") == "waiting"
    assert run.ticket()["queue_heads"] == {HEAD_A: 0}
    # Seen in the queue through "already in a merge queue": a later accepted enqueue is its first drop.
    assert run.drop("202-enqueued") == "requeued"


def test_the_first_drop_on_a_head_is_requeued_and_the_second_merge_base(run):
    assert run.drop("202-enqueued") == "in_queue"
    assert run.drop("200-waiting") == "waiting"
    assert run.drop("202-enqueued") == "requeued"
    assert run.ticket()["queue_heads"] == {HEAD_A: 1}
    assert run.ticket().get("base_merged") in (None, False)
    assert run.drop("202-enqueued") == "merge_base"
    t = run.ticket()
    assert t["queue_heads"] == {HEAD_A: 2}
    assert t["base_merged"] is True
    assert t["queue_result"] == "merge_base"


def test_a_first_drop_on_a_new_head_before_any_base_merge_is_requeued(run):
    assert run.drop("202-enqueued") == "in_queue"
    assert run.drop("202-enqueued") == "requeued"
    # A fix pushed: a new head starts its own count.
    assert run.drop("202-enqueued", HEAD_B) == "in_queue"
    assert run.drop("202-enqueued", HEAD_B) == "requeued"
    assert run.ticket()["queue_heads"] == {HEAD_A: 1, HEAD_B: 1}


def test_after_merge_base_a_new_heads_first_enqueue_is_in_queue_and_its_drop_needs_human(run):
    for want in ("in_queue", "requeued", "merge_base"):
        assert run.drop("202-enqueued") == want
    # The base merged in makes a new head.
    assert run.drop("202-enqueued", HEAD_B) == "in_queue"
    assert run.drop("200-waiting", HEAD_B) == "waiting"
    assert run.drop("202-enqueued", HEAD_B) == "needs_human"
    assert run.ticket()["queue_result"] == "needs_human"


def test_any_drop_once_the_base_was_merged_in_needs_human_whatever_the_head(run):
    for want in ("in_queue", "requeued", "merge_base"):
        assert run.drop("202-enqueued") == want
    # The same head again (the base merge never happened), or a third head after a fix.
    assert run.drop("202-enqueued") == "needs_human"
    assert run.drop("202-enqueued", HEAD_C) == "in_queue"
    assert run.drop("202-enqueued", HEAD_C) == "needs_human"


@pytest.mark.parametrize("answer", ["202-pending", "409", "refused", "failed"])
def test_answers_that_are_tried_again_are_retry_and_never_drops(run, answer):
    assert run.drop(answer) == "retry"
    # Not in the queue yet: the next accepted enqueue is the head's first.
    assert run.drop("202-enqueued") == "in_queue"
    assert run.drop(answer) == "retry"
    assert run.ticket()["queue_heads"] == {HEAD_A: 0}
    assert run.drop("202-enqueued") == "requeued"


def test_a_third_failed_on_a_head_needs_human(run):
    assert run.drop("failed") == "retry"
    assert run.drop("failed") == "retry"
    assert run.drop("failed", HEAD_B) == "retry"  # counted per head
    assert run.ticket()["queue_failed"] == {HEAD_A: 2, HEAD_B: 1}
    assert run.drop("failed") == "needs_human"
    assert run.ticket()["queue_failed"] == {HEAD_A: 3, HEAD_B: 1}


def test_merged_is_merged(run):
    assert run.drop("202-enqueued") == "in_queue"
    assert run.drop("200-merged") == "merged"
    assert run.ticket()["queue_result"] == "merged"


def test_drop_keeps_the_rest_of_the_ticket_and_the_body(run):
    run.drop("202-enqueued")
    text = run.body.read_text()
    assert text.startswith("The run.")
    t = run.ticket()
    assert t["status"] == "in-review" and t["pr"] == 40


def test_drop_heads_are_read_in_lower_case(run):
    assert run.drop("202-enqueued", "A" * 40) == "in_queue"
    assert run.drop("202-enqueued", "a" * 40) == "requeued"


@pytest.mark.parametrize(
    "args,words",
    [
        (["--ticket", "99", "--head", HEAD_A, "--answer", "200-waiting"], "#99"),
        (["--ticket", "12", "--head", "abc123", "--answer", "200-waiting"], "head"),
        (["--ticket", "12", "--head", HEAD_A, "--answer", "201"], "invalid choice"),
        (["--ticket", "12", "--head", HEAD_A], "--answer"),
        (["--ticket", "12", "--answer", "200-waiting"], "--head"),
        (["--ticket", "0", "--head", HEAD_A, "--answer", "200-waiting"], "#0"),
    ],
)
def test_drop_refuses_what_it_cant_decide(run, args, words):
    out = run.body.with_name("other.md")
    p = _cli("state", "drop", "--body", str(run.body), *args, "--out", str(out), env=run.env)
    assert p.returncode != 0
    assert words in p.stderr
    assert not out.exists()


@pytest.mark.parametrize(
    "fields",
    [{"queue_result": []}, {"queue_heads": {HEAD_A: "1"}}, {"queue_heads": "x"}, {"queue_failed": {HEAD_A: "1"}}],
)
def test_drop_refuses_a_hand_edited_state_it_cant_read(run, fields):
    s = state.get(run.body.read_text())
    s["tickets"]["12"].update(fields)
    block = json.dumps(s)
    text = run.body.read_text()
    start, end = text.index("```json\n") + len("```json\n"), text.index("\n```\n")
    run.body.write_text(text[:start] + block + text[end:])
    out = run.body.with_name("other.md")
    p = _cli("state", "drop", "--body", str(run.body), "--ticket", "12", "--head", HEAD_A, "--answer", "202-enqueued", "--out", str(out), env=run.env)
    assert p.returncode == 1, p.stderr
    assert "Traceback" not in p.stderr and "tickets[12]." in p.stderr
    assert not out.exists()


def test_drop_refuses_a_body_without_state(run):
    run.body.write_text("Just words.")
    out = run.body.with_name("other.md")
    p = _cli("state", "drop", "--body", str(run.body), "--ticket", "12", "--head", HEAD_A, "--answer", "200-waiting", "--out", str(out), env=run.env)
    assert p.returncode == 1 and "no state block" in p.stderr
    assert not out.exists()


@pytest.mark.parametrize("out", [[], ["--out", ""]])
def test_drop_needs_out(run, out):
    p = _cli("state", "drop", "--body", str(run.body), "--ticket", "12", "--head", HEAD_A, "--answer", "200-waiting", *out, env=run.env)
    assert p.returncode == 2 and "--out" in p.stderr


def test_the_queue_fields_are_validated():
    s = state.empty(None)
    s["tickets"] = {
        "1": {"status": "in-review", "queue_heads": {"zz": -1}, "queue_failed": [], "base_merged": "yes", "queue_result": "maybe"}
    }
    problems = "\n".join(state.validate(s))
    for f in ("queue_heads", "queue_failed", "base_merged", "queue_result"):
        assert f"tickets[1].{f}" in problems


def test_the_drop_rule_is_one_function():
    t = {"status": "in-review"}
    assert state.drop(t, HEAD_A, "202-enqueued") == "in_queue"
    assert state.drop(t, HEAD_A, "202-enqueued") == "requeued"
    assert t["queue_heads"] == {HEAD_A: 1}


# ---------- the docs ----------


def test_the_charter_doc_covers_the_queue():
    doc = CHARTER_DOC.read_text()
    assert "merge queue" in doc
    assert "--queue" in doc
    assert "workflow state drop" in doc
    for word in ("in_queue", "waiting", "merged", "retry", "requeued", "merge_base", "needs_human"):
        assert f"`{word}`" in doc, word
    assert "No waivers" in doc or "no waivers" in doc


def test_the_changelog_says_so_under_unreleased():
    text = (KIT / "CHANGELOG.md").read_text()
    unreleased = text.split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    assert "state drop" in unreleased
