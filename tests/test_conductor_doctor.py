"""#64: the conductor's pre-flight runs `workflow doctor` (#34), and #71: it
hands doctor the base branch's checks and the open pull requests, and offers
"Require these checks" at kick-off. Seam 4: the skill's wording and the docs,
read from the files as the kit-release tests do; and the skill's own commands
for the checks file, run into doctor."""

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

from changelog_notes import since_0110
from test_doctor import _project, _report
from test_doctor_github import _files
from test_doctor_require_checks import MARKER, PROTECTED, SHA, _combined, _pr, _requiring, _run, _status
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
    # With `ruleset` left out, "Require these checks" needs a ruleset as well.
    assert "`github.required_checks`'s" in refusal
    assert "**Go ahead** for the solo-mode gap" in refusal and "**Go ahead without it** for the ruleset's gaps" in refusal
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
    assert "(#64" in since_0110()


# ---------- #71: the check runs, the open pull requests and "Require these checks" ----------


def _checks_bullet():
    return _section(_doctor_block(), r"^- \*\*The checks that ran on the base branch\*\*", r"^- \*\*The open pull requests")


def _prs_bullet():
    return _section(_doctor_block(), r"^- \*\*The open pull requests", r"^- \*\*This session's Claude Code version")


def _require_checks_bullet():
    return _section(_kickoff(), r"^ {3}- \*\*The `require_checks` offer\*\*", r"^ {3}- \*\*(?!The `require_checks`)|^ {3}Also:|^\d\. ")


def test_preflight_gathers_the_base_branchs_check_runs_and_statuses_into_one_file():
    checks = _checks_bullet()
    # The latest commit's statuses first, every page: their `sha` is the commit the check runs are read for.
    assert "gh api --paginate --slurp 'repos/<repo>/commits/<base>/status?per_page=100' > .workflow/status.json" in checks
    assert "gh api --paginate --slurp 'repos/<repo>/commits/<sha>/check-runs?per_page=100' > .workflow/check-runs.json" in checks
    # Side by side in one JSON list, as doctor's --checks takes them.
    assert "one JSON list" in checks and "> .workflow/checks.json" in checks
    # A wrong checks file is silent, so the conductor looks at it first.
    assert "a wrong one is silent" in checks
    assert "`app`" in checks and "`slug`" in checks and "`total_count`" in checks
    assert "error body" in checks and "`head_sha`" in checks


def test_without_the_checks_the_offer_cant_be_made_and_the_kickoff_says_so():
    checks = _checks_bullet()
    assert "leave `--checks` out" in checks
    kick = _require_checks_bullet()
    assert "couldn't be read from this session" in kick and "a note, not a safety gap" in kick


def test_preflight_gathers_the_open_pull_requests_in_full():
    prs = _prs_bullet()
    assert "gh api --paginate --slurp 'repos/<repo>/pulls?state=open&per_page=100' > .workflow/prs.json" in prs
    assert "`head.repo`" in prs and "in full" in prs
    # Pull requests that can't be read leave the profile's line unchecked: a safety gap like any other.
    # Left out, doctor reads them with `gh` itself; with `ruleset` left out it is `cant_check` too.
    assert "`github.profile_checks`" in prs and "`cant_check`" in prs
    assert "Unless the profile says `ruleset = false`" in prs and "doctor's own `gh` read fails" in prs
    # The MCP tools' pull requests count only with `head.repo`: a fork's marked one is never the repository's own.
    assert "no `head.repo.full_name`, leave `--prs` out" in prs


def test_doctor_is_given_the_checks_and_the_pull_requests():
    cmd = re.search(r"^WF doctor --json .*$", _doctor_block(), re.M).group(0)
    assert "--checks .workflow/checks.json" in cmd and "--prs .workflow/prs.json" in cmd


def test_the_redo_rule_covers_the_two_new_files():
    redo = _section(_doctor_block(), r"Before reading the report, redo any fetch that went wrong, once:", r"^Fetch each such file again")
    assert "`checks.json`" in redo and "`prs.json`" in redo
    # The checks file has its own one redo: once left out, it isn't fetched a third time.
    assert "once you've left `--checks` out, don't fetch it again" in redo


def test_the_kickoff_offers_require_these_checks_first_or_go_ahead_without_them():
    kick = _require_checks_bullet()
    assert "`require_checks`" in kick and "`github.required_checks`" in kick
    assert "require_checks" in doctor.OFFERS
    assert "**Require these checks first**" in kick and "**Go ahead without them**" in kick
    # Done in an attended session, where Claude is asked to "require the checks" (#68); the kick-off stops there.
    assert "names the checks that ran" in kick
    assert '"require the checks"' in kick and "attended session" in kick
    assert "end here" in kick and "nothing has been created yet" in kick


def test_going_ahead_records_a_gap_but_not_a_note():
    kick = _require_checks_bullet()
    assert "`accepted_gaps`" in kick and "`github.required_checks: <message>`" in kick
    assert "a note needs no record" in kick
    # It replaces the gap's usual question: "Fix it first" can't work from a conductor session.
    assert "in place of **Fix it first / Go ahead without it**" in kick


def test_a_required_checks_gap_without_the_offer_is_also_sent_to_an_attended_session():
    # The checks it names haven't run (or couldn't be read): its fix still asks for "Require these checks".
    kick = _require_checks_bullet()
    rest = _section(kick, r"Two more gaps are fixed in an attended session", r"\n\n")
    assert "**Fix it first** ends here the same way" in rest and "**Fix it first / Go ahead without it** as usual" in rest
    no_offer = _section(rest, r"- a `github.required_checks` gap with no `offer`", r"\n")
    assert "while `github.ruleset` is `fine`" in no_offer and '"require the checks" in an attended session once they have run' in no_offer
    # While the base branch isn't protected, protecting it comes first (it adds the listed checks).
    assert "the ruleset's own gap comes first" in no_offer and "paid-plan refusal" in no_offer
    assert "`github.ruleset`'s gap with `ruleset` left out" in no_offer
    # Without protection, this gap can't be fixed in the kick-off: going ahead is recommended.
    assert "While that gap is accepted or still open, this gap's **Fix it first** can't work, so recommend **Go ahead without it**" in no_offer
    fix_first = _section(_kickoff(), r"^\s*- \*\*Fix it first:\*\*", r"\n")
    assert 'except "Require these checks", below' in fix_first


def test_the_profile_checks_gap_is_fixed_in_an_attended_session_too():
    rest = _section(_require_checks_bullet(), r"Two more gaps are fixed in an attended session", r"\n\n")
    gap = _section(rest, r"- `github.profile_checks`' gap", r"\n|\Z")
    assert "in an attended session" in gap and "`ci.required_checks`" in gap
    assert "`workflow/required-checks`" in gap and f"`{MARKER}`" in gap


def test_upgrade_setup_agrees_that_the_conductor_never_requires_the_checks():
    text = (KIT / "skills/upgrade-setup/SKILL.md").read_text(encoding="utf-8")
    assert 'never runs "Require these checks": its kick-off sends the owner to an attended session' in text
    which = _section(text, r"^## Which way, for the checks", r"^## ")
    assert "A cloud session, a conductor session," not in which
    assert "A conductor session never gets here" in which


def test_the_note_when_the_checks_couldnt_be_read_is_given_in_words():
    kick = _require_checks_bullet()
    assert "> Which checks have run on `<base>` couldn't be read from this session, so if some aren't required yet" in kick


def test_the_conductor_never_changes_the_ruleset_or_merges_the_profile_pull_request():
    text = _conductor()
    assert "The conductor never changes the ruleset itself" in text
    assert "never merges the profile's pull request" in text


def test_the_open_profile_pull_requests_note_stays_a_note():
    block = _doctor_block()
    note = _section(block, r"^- \*\*The open profile pull request\.\*\*", r"^- \*\*|^\*\*")
    assert "`github.profile_checks`" in note and "`note`" in note
    assert "never a safety gap" in note and "the run goes ahead" in note
    assert "never merges the profile's pull request" in note and "protected path" in note
    # Its gap's fix, the profile's pull request, is made in an attended session, never in the kick-off.
    assert "never in the kick-off" in note and f"`{MARKER}`" in note


def test_changelog_notes_71_under_unreleased():
    assert "(#71, part of #38)" in since_0110()


def test_the_skills_own_commands_make_files_doctor_reads(tmp_path):
    """The pre-flight's one-liners, run as written on `gh api --paginate --slurp`'s
    pages, give doctor a --checks it reads (the offer); a slurped pulls page with
    `head.repo`, as the skill's `gh api` saves it, gives the profile's note."""
    work = tmp_path / ".workflow"
    work.mkdir()
    (work / "status.json").write_text(json.dumps([_combined(_status("deploy/preview"))]))
    (work / "check-runs.json").write_text(json.dumps([
        {"total_count": 2, "check_runs": [_run("tests")]}, {"total_count": 2, "check_runs": [_run("lint", n=2)]}]))
    own = {"ref": "add-checks", "repo": {"full_name": "acme/demo"}}
    (work / "prs.json").write_text(json.dumps([[{**_pr(12, f"Requires `build`.\n\n{MARKER}\n"), "head": own}]]))
    one_liners = re.findall(r"python3 -c '[^']*' \.workflow/[^`\n]*", _checks_bullet())
    assert len(one_liners) == 2, one_liners
    first, merge = (c.replace("python3", shlex.quote(sys.executable), 1) for c in one_liners)
    got = subprocess.run(first, shell=True, cwd=tmp_path, capture_output=True, text=True, check=True).stdout.strip()
    assert got == SHA
    subprocess.run(merge, shell=True, cwd=tmp_path, check=True)
    root = _project(tmp_path / "p", profile=PROTECTED)
    args = _files(tmp_path / "p", [_requiring("tests", "build")]) + ["--checks", str(work / "checks.json"), "--prs", str(work / "prs.json")]
    lines = {ln["id"]: ln for ln in _report(tmp_path / "p", root, *args)["lines"]}
    offer = lines["github.required_checks"]
    assert (offer["status"], offer["offer"]) == ("note", "require_checks"), offer
    assert "`lint`" in offer["message"] and "`deploy/preview`" in offer["message"], offer
    note = lines["github.profile_checks"]
    assert note["status"] == "note" and "#12" in note["message"], note


def test_enforcement_doc_says_the_conductor_hands_doctor_the_checks_and_asks_require_these_checks():
    text = (KIT / "docs/enforcement.md").read_text(encoding="utf-8")
    run = _section(text, r"^In every run's pre-flight the conductor runs `workflow doctor --json`", r"\n")
    assert "(`--checks`)" in run and "(`--prs`)" in run
    assert '"Require these checks first"' in run and '"Go ahead without them"' in run
    assert "the conductor never changes the ruleset itself" in run
