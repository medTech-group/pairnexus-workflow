"""#64: the conductor's pre-flight runs `workflow doctor` (#34). Seam 4: the
skill's wording and the docs, read from the files as the kit-release tests do."""

import re
from pathlib import Path

from workflow import doctor

KIT = Path(__file__).resolve().parents[1]
CONDUCTOR = KIT / "skills/conductor/SKILL.md"


def _conductor():
    return CONDUCTOR.read_text(encoding="utf-8")


def _section(text, start, end):
    m = re.search(start + r".*?(?=" + end + ")", text, re.M | re.S)
    assert m, f"no section {start!r}"
    return m.group(0)


def _preflight():
    return _section(_conductor(), r"^### 1\. Pre-flight", r"^### 2\.")


def _kickoff():
    return _section(_conductor(), r"^### 2\. The kick-off", r"^## ")


def _doctor_block():
    return _section(_preflight(), r"^\*\*The set-up: `WF doctor`\*\*", r"^\*\*The ticket sessions' environment\*\*")


# ---------- doctor runs with the files the pre-flight gathers ----------


def test_preflight_runs_doctor_json_with_every_file():
    block = _doctor_block()
    m = re.search(r"^WF doctor --json .*$", block, re.M)
    assert m, "no doctor command line"
    cmd = m.group(0)
    for flag in ("--rulesets", "--repo", "--environments", "--runs", "--claude-version"):
        assert flag in cmd, flag


def test_each_file_says_where_it_comes_from():
    block = _doctor_block()
    # The rulesets in full, each by its id, not the list's summaries.
    assert "gh api --paginate 'repos/<repo>/rulesets?" in block and "by its id" in block
    assert "gh api repos/<repo> > .workflow/repo.json" in block
    # A private repository on GitHub Free: the list is refused, and no ruleset is saved.
    assert "rulesets need a paid plan" in block and "save `[]`" in block
    assert "keep it for the kick-off" in block
    assert "`list_environments`" in block and "has_more" in block
    assert "workflow:run" in block and "state=all" in block
    assert "claude --version" in block


def test_a_paid_plan_refusal_is_said_in_the_kickoff_and_going_ahead_recommended():
    # Doctor can't see the refusal in `[]`, so the conductor says it and doesn't steer to Protect.
    kick = _kickoff()
    refusal = _section(kick, r"^\s*- \*\*A paid-plan refusal\*\*", r"\n")
    assert "need a paid GitHub plan (Team or above)" in refusal
    assert "beside the solo-mode gap" in refusal and "`github.ruleset`'s gap" in refusal
    assert "**Go ahead** for the solo-mode gap" in refusal and "**Go ahead without it** for the ruleset's gap" in refusal
    assert "**Protect `main`** (recommended, except after a paid-plan refusal" in kick


def test_the_flags_doctor_is_given_are_the_flags_it_takes():
    cli = (KIT / "scripts/workflow/cli.py").read_text(encoding="utf-8")
    # Doctor's own parser only: other subcommands take --repo and --runs too.
    usage = _section(cli, r'^\s*s = sub\.add_parser\("doctor"', r"^\s*s\.set_defaults\(fn=cmd_doctor\)")
    cmd = re.search(r"^WF doctor --json .*$", _doctor_block(), re.M).group(0)
    cmd = re.sub(r'"<[^"]*>"', "", cmd)  # a placeholder such as "<what claude --version printed>"
    for flag in re.findall(r"--[a-z-]+", cmd):
        assert f'"{flag}"' in usage, flag


def test_doctors_gaps_and_cant_checks_become_the_kickoffs_safety_gaps():
    block = _doctor_block()
    assert "`gap`" in block and "`cant_check`" in block and "safety gap" in block
    kick = _kickoff()
    assert "Fix it first / Go ahead without it" in kick and "`accepted_gaps`" in kick
    fix_first = _section(kick, r"^\s*- \*\*Fix it first:\*\*", r"\n")
    assert "run doctor again" in fix_first and "neither a `gap` nor `cant_check`" in fix_first
    for status in doctor.STATUSES:
        assert f"`{status}`" in block, status


def test_the_safety_gaps_cover_what_the_ticket_names():
    block = _doctor_block()
    for line_id in ("github.ruleset", "github.required_checks", "github.up_to_date", "github.code_owner_review",
                    "github.codeowners", "kit.profile"):
        assert f"`{line_id}`" in block, line_id
    assert "`ruleset = true` mismatch" in block


def test_the_line_ids_the_skill_names_are_doctors():
    src = (KIT / "scripts/workflow/doctor.py").read_text(encoding="utf-8")
    named = set(re.findall(r"`((?:computer|kit|github|cloud)\.[a-z_.*]+)`", _conductor()))
    assert named
    for line_id in named:
        if line_id.endswith(".*"):
            assert f'"{line_id[:-1]}' in src, line_id
        else:
            assert f'"{line_id}"' in src, line_id


def test_the_offers_the_skill_reads_are_doctors():
    block = _doctor_block()
    for offer in ("protect_main", "restore_protection"):
        assert offer in doctor.OFFERS and f"`{offer}`" in block, offer


def test_approvals_above_zero_still_recommend_owner():
    block = _doctor_block()
    assert "`github.approvals`" in block
    assert "**owner** the recommended answer" in block


# ---------- what the pre-flight no longer does itself ----------


def test_preflight_no_longer_lists_the_ruleset_codeowners_or_required_checks_steps():
    pre = _preflight()
    assert "It must be `enforcement: active`" not in pre
    assert "The required checks must equal the profile's `ci.required_checks`" not in pre
    assert "CODEOWNERS covers `.claude/` and `.github/workflows/`" not in pre
    assert "`WF profile check`: no errors" not in pre
    assert "WF protection" not in pre
    assert "WF status --json" not in pre
    assert "required_approving_review_count" not in pre


# ---------- solo mode and removed protection, from doctor's lines (#50) ----------


def test_solo_mode_and_removed_protection_are_read_from_doctors_lines():
    block = _doctor_block()
    solo = _section(block, r"^- \*\*Solo mode\*\*", r"^- \*\*|\Z")
    assert "`kit.ruleset`" in solo and "solo-mode note" in solo and "`protect_main`" in solo
    assert "`github.ruleset`" in solo and "`restore_protection`" in solo and "mismatch line" in solo
    assert "ruleset = false" in solo and "ruleset = true" in solo
    assert "one place that decides" in solo


def test_a_cant_check_ruleset_with_ruleset_true_counts_as_removed_protection():
    solo = _section(_doctor_block(), r"^- \*\*Solo mode\*\*", r"^- \*\*|\Z")
    also = _section(solo, r"^\s*With `ruleset = true`, each of these counts as removed protection too:", r"^\s*With `ruleset` left out")
    assert "`cant_check`" in also and "no `github.ruleset` line" in also and "never gave its JSON" in also
    assert "can't be confirmed from this session, not that it was removed" in also
    # Without doctor's JSON, the profile itself says which kind of solo mode.
    assert "`project.ruleset` says which: `false` is chosen solo mode, `true` removed protection" in also


def test_a_file_that_couldnt_be_read_is_fetched_again_before_the_report_is_read():
    block = _doctor_block()
    redo = _section(block, r"Before reading the report, redo any fetch that went wrong, once:", r"^Fetch each such file again")
    assert "error body" in redo and "missing or empty" in redo and "fix says to fetch it again" in redo
    assert "Fetch each such file again and run doctor again. Whatever its lines say after that is the report" in block
    assert "run it again once, and if it still fails" in block


def test_a_gap_still_open_after_fix_it_first_asks_go_ahead_or_dont_start():
    fix_first = _section(_kickoff(), r"^\s*- \*\*Fix it first:\*\*", r"\n")
    assert "**Go ahead without it**" in fix_first and "**Don't start the run**" in fix_first


def test_the_findings_show_this_sessions_own_problems_too():
    findings = _section(_kickoff(), r"^1\. \*\*The findings\.\*\*", r"\n")
    assert "this session's own" in findings and "doctor's safety gaps" in findings


def test_approvals_that_cant_be_read_recommend_owner_too():
    assert "A `github.approvals` line that is `cant_check` makes **owner** the recommended answer too" in _doctor_block()


def test_auto_merge_gives_way_in_solo_mode():
    solo = _section(_doctor_block(), r"^- \*\*Solo mode\*\*", r"^- \*\*|\Z")
    assert "`github.auto_merge`" in solo and "give way to one safety gap" in solo


def test_the_kickoff_still_offers_protecting_restoring_or_going_ahead():
    kick = _kickoff()
    assert "`protect_main`" in kick and "`restore_protection`" in kick
    assert "**Go ahead**" in kick
    assert "doctor" in kick


# ---------- what stays the conductor's own ----------


def test_the_session_only_checks_are_still_listed():
    pre = _preflight()
    for phrase in ("echo $WORKFLOW_ROLE", "`get_session`", "`run.permission_mode`", "`WF version --fresh`",
                   "`WF ready --fetch`", "names protected path", "Leftovers", "The base branch's CI is green",
                   "**The last run**"):
        assert phrase in pre, phrase


def test_a_missing_ticket_environment_still_stops_the_run_whatever_doctor_says():
    pre = _preflight()
    env = _section(pre, r"^\*\*The ticket sessions' environment\*\*", r"^\*\*The work\*\*")
    assert "`list_environments`" in env and "keep its id" in env
    # Only an active one counts, as doctor counts it.
    assert "the active one named `run.ticket_environment`" in env and "isn't active counts as none" in env
    assert "Two active ones of that name are a blocking problem too" in env
    assert "whatever doctor's `cloud.environments` line says" in env
    assert "before the kick-off's questions" in env
    assert "blocking problem" in env


# ---------- the docs and the changelog ----------


def test_enforcement_doc_says_the_conductor_runs_doctor():
    text = (KIT / "docs/enforcement.md").read_text(encoding="utf-8")
    sec = _section(text, r"^## 5\. Checking the set-up", r"^## |\Z")
    assert "The conductor repeats items 1, 3 and 4" not in sec
    assert re.search(r"conductor runs `workflow doctor", sec)


def test_readme_step_6_says_the_conductor_runs_doctor():
    text = (KIT / "README.md").read_text(encoding="utf-8")
    sec = _section(text, r"^### Step 6\. Check it", r"^### ")
    assert "The conductor checks the ruleset, CODEOWNERS and the ticket environment again" not in sec
    assert re.search(r"conductor runs `workflow doctor`", sec)
    assert "A missing ticket environment stops it" in sec


def test_changelog_notes_the_change_under_unreleased():
    text = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    unreleased = _section(text, r"^## Unreleased", r"^## \d")
    assert "(#64" in unreleased
