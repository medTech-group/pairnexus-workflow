"""#171: `workflow state put` and `state patch` check a charter change against
the profile on disk, with the same checks `workflow charter validate` runs
(#50's solo-mode and required-checks rules among them), through the CLI."""

import json
import os
import subprocess
import sys
from pathlib import Path

from workflow import charter, state

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"


def _cli(*args, env=None):
    e = {**os.environ, **(env or {})}
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, env=e)


def _profile(tmp_path, ruleset=None, checks=("CI",)):
    line = "" if ruleset is None else f"ruleset = {'true' if ruleset else 'false'}\n"
    text = (
        f'[project]\nname="d"\nrepo="a/d"\nowner="o"\n{line}'
        f"[ci]\nrequired_checks={json.dumps(list(checks))}\n"
        '[[release.steps]]\nname="ship"\nrun="x"\n'
    )
    (tmp_path / ".claude/workflow").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(text)
    return {"CLAUDE_PROJECT_DIR": str(tmp_path)}


def _charter(mode="session"):
    c = charter.defaults(["ship"])
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    c["merge"]["mode"] = mode
    c["approved"] = {"by": "o", "at": "2026-10-12T11:55:00Z", "source": "chat"}
    return c


def _body(tmp_path, c=None):
    b = tmp_path / "body.md"
    b.write_text(state.put("# Tracking\n", state.empty(c or _charter())))
    return b


def _patch(tmp_path, env, change, out=None):
    b, pf = tmp_path / "body.md", tmp_path / "patch.json"
    pf.write_text(json.dumps(change))
    extra = ["--out", str(out)] if out else []
    return _cli("state", "patch", "--body", str(b), "--patch", str(pf), *extra, env=env)


def _validate_message(tmp_path, env, c):
    """What `workflow charter validate` says about this charter, with this profile."""
    f = tmp_path / "check.json"
    f.write_text(json.dumps(c))
    p = _cli("charter", "validate", str(f), "--approved", env=env)
    assert p.returncode == 1
    return p.stderr.strip()


def _refused_unchanged(tmp_path, env, change):
    b = _body(tmp_path)
    before = b.read_text()
    out = tmp_path / "new.md"
    p = _patch(tmp_path, env, change, out=out)
    assert p.returncode == 1
    assert not out.exists() and p.stdout == ""
    assert b.read_text() == before
    return p


def test_auto_merge_in_solo_mode_is_refused_with_validates_message(tmp_path):
    env = _profile(tmp_path, ruleset=False)
    p = _refused_unchanged(tmp_path, env, {"charter": {"merge": {"mode": "auto-merge"}}})
    msg = _validate_message(tmp_path, env, _charter("auto-merge"))
    assert "solo mode" in msg
    assert msg in p.stderr


def test_auto_merge_with_no_required_checks_is_refused(tmp_path):
    env = _profile(tmp_path, ruleset=True, checks=())
    p = _refused_unchanged(tmp_path, env, {"charter": {"merge": {"mode": "auto-merge"}}})
    msg = _validate_message(tmp_path, env, _charter("auto-merge"))
    assert "no ci.required_checks" in msg
    assert msg in p.stderr


def test_removed_protection_recorded_in_the_charter_counts(tmp_path):
    env = _profile(tmp_path, ruleset=True)
    gap = "removed protection: the read-back found main unprotected"
    p = _refused_unchanged(tmp_path, env, {"charter": {"merge": {"mode": "auto-merge"}, "accepted_gaps": [gap]}})
    assert "removed protection" in p.stderr


def test_other_profile_checks_run_too(tmp_path):
    env = _profile(tmp_path, ruleset=True)
    p = _refused_unchanged(tmp_path, env, {"charter": {"release": {"steps": ["deploy prod"]}}})
    assert "'deploy prod' is not in the profile's [release] steps" in p.stderr


def test_a_valid_charter_patch_is_written(tmp_path):
    env = _profile(tmp_path, ruleset=True)
    _body(tmp_path)
    p = _patch(tmp_path, env, {"charter": {"merge": {"mode": "auto-merge"}}})
    assert p.returncode == 0, p.stderr
    assert state.get(p.stdout)["charter"]["merge"]["mode"] == "auto-merge"


def test_a_tickets_patch_is_written_as_before_even_when_the_charter_no_longer_fits(tmp_path):
    # The run started under a profile that allowed auto-merge; the profile has
    # since changed. A patch that doesn't touch the charter isn't checked.
    env = _profile(tmp_path, ruleset=False)
    _body(tmp_path, _charter("auto-merge"))
    p = _patch(tmp_path, env, {"tickets": {"7": {"status": "running"}}})
    assert p.returncode == 0, p.stderr
    assert state.get(p.stdout)["tickets"]["7"]["status"] == "running"
    # Setting a charter field to the value it already has isn't a change either.
    p = _patch(tmp_path, env, {"charter": {"merge": {"mode": "auto-merge"}}})
    assert p.returncode == 0, p.stderr


def test_put_checks_a_changed_charter(tmp_path):
    env = _profile(tmp_path, ruleset=False)
    b = _body(tmp_path)
    before = b.read_text()
    sf = tmp_path / "state.json"
    s = state.get(before)
    s["charter"]["merge"]["mode"] = "auto-merge"
    sf.write_text(json.dumps(s))
    p = _cli("state", "put", "--body", str(b), "--state", str(sf), env=env)
    assert p.returncode == 1 and "solo mode" in p.stderr and p.stdout == ""
    assert b.read_text() == before
    # The same charter, with only a ticket changed, is written.
    s = state.get(before)
    s["tickets"]["9"] = {"status": "queued"}
    sf.write_text(json.dumps(s))
    p = _cli("state", "put", "--body", str(b), "--state", str(sf), env=env)
    assert p.returncode == 0, p.stderr
    # A first put, into a body with no block, checks the charter it adds.
    b.write_text("# Tracking\n")
    s["charter"]["merge"]["mode"] = "auto-merge"
    sf.write_text(json.dumps(s))
    p = _cli("state", "put", "--body", str(b), "--state", str(sf), env=env)
    assert p.returncode == 1 and "solo mode" in p.stderr


def test_without_a_profile_a_charter_patch_is_written(tmp_path):
    _body(tmp_path)
    p = _patch(tmp_path, {"CLAUDE_PROJECT_DIR": str(tmp_path)}, {"charter": {"merge": {"mode": "auto-merge"}}})
    assert p.returncode == 0, p.stderr
