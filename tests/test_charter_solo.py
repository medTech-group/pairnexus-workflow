"""#50: unattended runs in solo mode (#32). Seam 2: the charter's `defaults`,
`questions` and its check against the profile, through the CLI as the existing
charter tests do. Seam 4: the conductor's pre-flight and the run report's
wording, read from the skill files as the kit-release tests do."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from workflow import charter

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"
CONDUCTOR = KIT / "skills/conductor/SKILL.md"
RUN_REPORT = KIT / "skills/run-report/SKILL.md"
CHARTER_DOC = KIT / "docs/charter.md"

# The decided words of the gap (#32).
GAP_WORDS = "nothing on GitHub stops a mistake reaching `main`"
ONLY_CHECK = "the kit's \"never merge while CI is red\" check is the only one"


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


def _charter_file(tmp_path, mode):
    c = charter.defaults(["ship"])
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    c["merge"]["mode"] = mode
    f = tmp_path / "c.json"
    f.write_text(json.dumps(c))
    return f


def _merge_q(out):
    return next(q for q in json.loads(out) if q["key"] == "merge")


# ---------- the one rule ----------


def test_solo_mode_is_ruleset_false_or_removed_protection():
    assert charter.solo_mode(False) and "project.ruleset is false" in charter.solo_mode(False)
    assert charter.solo_mode(False, protected=True)  # the profile still says solo until its flip PR merges
    removed = charter.solo_mode(True, protected=False)
    assert removed and "isn't protected" in removed
    assert charter.solo_mode(True) is None and charter.solo_mode(True, protected=True) is None
    # Left out: as before, whatever the read-back says.
    assert charter.solo_mode(None) is None and charter.solo_mode(None, protected=False) is None


# ---------- charter defaults ----------


@pytest.mark.parametrize("ruleset,mode", [(False, "session"), (True, "auto-merge"), (None, "auto-merge")])
def test_defaults_pick_session_merging_in_solo_mode(tmp_path, ruleset, mode):
    env = _profile(tmp_path, ruleset)
    p = _cli("charter", "defaults", env=env)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["merge"]["mode"] == mode


def test_defaults_with_removed_protection(tmp_path):
    env = _profile(tmp_path, True)
    p = _cli("charter", "defaults", "--unprotected", env=env)
    assert json.loads(p.stdout)["merge"]["mode"] == "session"
    # Left out, --unprotected changes nothing: as before.
    env = _profile(tmp_path, None)
    assert json.loads(_cli("charter", "defaults", "--unprotected", env=env).stdout)["merge"]["mode"] == "auto-merge"


# ---------- charter questions ----------


def test_questions_dont_offer_auto_merge_in_solo_mode_and_say_why(tmp_path):
    env = _profile(tmp_path, False)
    q = _merge_q(_cli("charter", "questions", env=env).stdout)
    assert "auto-merge" not in q["options"] and set(q["options"]) == {"session", "owner"}
    assert q["default"]["mode"] == "session"
    assert "solo mode" in q["note"].lower() and "auto-merge" in q["note"]
    assert "merge at once" in q["note"] and "required checks" in q["note"]


def test_questions_with_removed_protection(tmp_path):
    env = _profile(tmp_path, True)
    q = _merge_q(_cli("charter", "questions", "--unprotected", env=env).stdout)
    assert "auto-merge" not in q["options"] and "isn't protected" in q["note"]


@pytest.mark.parametrize("ruleset", [True, None])
def test_questions_offer_every_mode_outside_solo_mode(tmp_path, ruleset):
    env = _profile(tmp_path, ruleset)
    q = _merge_q(_cli("charter", "questions", env=env).stdout)
    assert set(q["options"]) == {"auto-merge", "session", "owner"}
    assert "note" not in q
    # Without a profile, too.
    q = _merge_q(_cli("charter", "questions", env={"CLAUDE_PROJECT_DIR": str(tmp_path / "none")}).stdout)
    assert set(q["options"]) == {"auto-merge", "session", "owner"}


# ---------- the check against the profile ----------


def test_check_flags_auto_merge_in_solo_mode(tmp_path):
    env = _profile(tmp_path, False)
    p = _cli("charter", "validate", str(_charter_file(tmp_path, "auto-merge")), env=env)
    assert p.returncode == 1
    assert "merge.mode auto-merge" in p.stderr and "solo mode" in p.stderr and "use session" in p.stderr
    assert _cli("charter", "validate", str(_charter_file(tmp_path, "session")), env=env).returncode == 0


@pytest.mark.parametrize("ruleset", [True, None])
def test_check_doesnt_flag_auto_merge_with_true_or_no_setting(tmp_path, ruleset):
    env = _profile(tmp_path, ruleset)
    p = _cli("charter", "validate", str(_charter_file(tmp_path, "auto-merge")), env=env)
    assert p.returncode == 0, p.stderr


def test_check_flags_auto_merge_with_removed_protection(tmp_path):
    env = _profile(tmp_path, True)
    f = _charter_file(tmp_path, "auto-merge")
    p = _cli("charter", "validate", str(f), "--unprotected", env=env)
    assert p.returncode == 1 and "isn't protected" in p.stderr and "use session" in p.stderr


def test_check_against_profile_names_one_reason():
    c = charter.defaults(["ship"])
    c["merge"]["mode"] = "auto-merge"
    p = charter.check_against_profile(c, ["ship"], [], ruleset=False)
    assert len(p) == 1 and "solo mode" in p[0]  # not also "no ci.required_checks"
    assert charter.check_against_profile(c, ["ship"], ["CI"], ruleset=True) == []
    assert charter.check_against_profile(c, ["ship"], ["CI"]) == []


# ---------- the conductor's pre-flight (seam 4) ----------


def _conductor():
    return CONDUCTOR.read_text(encoding="utf-8")


def _preflight():
    text = _conductor()
    m = re.search(r"^### 1\. Pre-flight.*?(?=^### 2\.)", text, re.M | re.S)
    assert m, "no pre-flight section"
    return m.group(0)


def _kickoff():
    text = _conductor()
    m = re.search(r"^### 2\. The kick-off.*?(?=^## )", text, re.M | re.S)
    assert m, "no kick-off section"
    return m.group(0)


def test_preflight_treats_both_cases_as_solo_mode():
    pre = _preflight()
    assert "ruleset = false" in pre
    assert "ruleset = true" in pre and "WF protection" in pre and "--repo" in pre and "--json" in pre
    assert '"protected": false' in pre
    assert "solo mode" in pre.lower()


def test_preflight_states_the_gap_in_the_decided_words():
    text = _preflight() + _kickoff()
    assert GAP_WORDS in text and ONLY_CHECK in text


def test_preflight_offers_protecting_or_restoring_or_going_ahead():
    text = _preflight() + _kickoff()
    assert "Protect `main`" in text and "`protect_main`" in text
    assert "`restore_protection`" in text
    assert "Go ahead" in text
    assert "upgrade-setup" in text


def test_acceptance_goes_in_accepted_gaps_and_auto_merge_is_never_offered():
    text = _preflight() + _kickoff()
    assert "accepted_gaps" in text
    assert "--unprotected" in text
    assert re.search(r"never (offers|uses|offer|use) (GitHub )?`?auto-merge", text)


def test_the_ticket_environment_is_still_required_and_the_upgrade_offered():
    pre = _preflight()
    assert "still required in solo mode" in pre
    assert "`set_up_unattended_runs`" in pre and "Set up unattended runs" in pre
    assert "step-5-create-the-two-claude-environments" in pre


# ---------- the run report (seam 4) ----------


def test_run_report_repeats_a_solo_mode_runs_gap():
    text = RUN_REPORT.read_text(encoding="utf-8")
    assert "accepted_gaps" in text and "solo mode" in text.lower()
    assert GAP_WORDS in text and ONLY_CHECK in text
    assert "Protect `main`" in text


# ---------- the docs ----------


def test_charter_doc_covers_solo_modes_merge_default_and_the_gap():
    text = CHARTER_DOC.read_text(encoding="utf-8")
    assert "solo mode" in text.lower()
    assert GAP_WORDS in text and ONLY_CHECK in text
    assert "--unprotected" in text
