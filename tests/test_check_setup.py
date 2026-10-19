"""#63: "Check the set-up", the `check-setup` skill, the guided start's offer of
it, and the docs (#34). Seam 4: the skills' and docs' wording, read from the
files as the kit-release tests do, and the skill shipping as the others do."""

import json
import re

from changelog_notes import since_0110
from conftest import KIT
from workflow import doctor, status, vendor

SKILL = KIT / "skills/check-setup/SKILL.md"
START = KIT / "skills/start/SKILL.md"
UPGRADE = KIT / "skills/upgrade-setup/SKILL.md"


def _text(path=SKILL):
    return path.read_text(encoding="utf-8")


def _head():
    return _text().split("---", 2)[1]


def _section(text, title, level="##"):
    """The text of the `<level> ...` section whose heading contains `title`, up
    to the next heading of that level or higher."""
    m = re.search(rf"^{level} [^\n]*{re.escape(title)}[^\n]*\n(.*?)(?=^#{{1,{len(level)}}} |\Z)", text, re.M | re.S)
    assert m, f"no section {title!r}"
    return m.group(1)


def _doctor_lines():
    """Every `WF doctor ...` command line the skill gives."""
    return re.findall(r"^WF doctor .*$", _text(), re.M)


# ---------- the skill: its name, and where it runs ----------


def test_the_skill_is_check_setup_and_claude_may_load_it():
    head = _head()
    assert re.search(r"^name: check-setup$", head, re.M)
    assert "disable-model-invocation" not in head
    assert re.search(r"^description: .*check the set-up", head, re.M | re.I)
    # Not `doctor`: Claude Code already has `/doctor`.
    assert not (KIT / "skills/doctor").exists()
    assert "`/doctor`" in _text()


def test_it_ships_vendored():
    files = vendor.plan(KIT, None)
    assert files[".claude/skills/check-setup/SKILL.md"] == SKILL


def test_it_ships_in_the_plugin():
    # The plugin is the repository root and ships every skills/<name>/SKILL.md.
    market = json.loads((KIT / ".claude-plugin/marketplace.json").read_text())
    kit = next(p for p in market["plugins"] if p["name"] == "pairnexus-workflow")
    assert kit["source"] == "./"
    assert "skills" not in json.loads((KIT / ".claude-plugin/plugin.json").read_text())
    assert SKILL.is_file()


def test_it_changes_nothing_itself():
    assert "**It changes nothing itself.**" in _text()


def test_it_never_runs_in_a_ticket_or_conductor_session():
    text = _text()
    assert "`WORKFLOW_ROLE`" in text
    assert "ticket" in text and "conductor" in text
    assert "pre-flight runs doctor itself" in text
    # A ticket session is known by its branch too, as the guided start and the guard know it.
    assert "`run.ticket_branch`" in text


# ---------- gathering, in a cloud session ----------


def test_a_cloud_session_gathers_every_file_doctor_takes():
    cloud = _section(_text(), "In a cloud session", "###")
    # The rulesets, each in full by its id, and the repository's settings.
    assert "rulesets" in cloud and "by its id" in cloud and "in full" in cloud
    assert "gh api repos/<repo>" in cloud
    assert "GitHub MCP tools" in cloud
    # The environments, every page.
    assert "`list_environments`" in cloud and "`has_more` is false" in cloud
    # The runs, open and closed.
    assert "workflow:run" in cloud and "state=all" in cloud
    # Claude Code's version.
    assert "claude --version" in cloud


def test_the_files_go_outside_the_checkout():
    cloud = _section(_text(), "In a cloud session", "###")
    assert "outside the checkout" in cloud
    assert "mktemp -d" in cloud


def test_the_cloud_command_hands_doctor_every_file():
    cmds = [c for c in _doctor_lines() if "--environments" in c]
    assert len(cmds) == 1, cmds
    cmd = cmds[0]
    for flag in ("--json", "--rulesets", "--repo", "--environments", "--runs", "--claude-version"):
        assert flag in cmd, flag


def test_a_file_it_could_not_gather_is_left_out_never_made_up():
    cloud = _section(_text(), "In a cloud session", "###")
    assert "leave its flag out" in cloud
    assert "never write a file you made up" in cloud.lower()


def test_a_paid_plan_refusal_is_left_to_doctors_own_read():
    # Doctor sees the refusal only on its own `gh` read, so no `[]` file is saved for it.
    cloud = _section(_text(), "In a cloud session", "###")
    assert "rulesets need a paid plan" in cloud
    assert "leave `--rulesets` out" in cloud and "save `[]`" not in cloud


def test_a_file_doctor_could_not_use_is_fetched_again_once():
    failed = _section(_text(), "When something goes wrong", "###")
    assert "Exit code 2" in failed and "more than one file" in failed
    assert "is a `cant_check` line" in failed and "Fetch such a file again once" in failed
    assert "look at each file yourself" in failed
    # A runs file doctor can't use leaves the Cloud line a note whose status isn't known.
    assert "**Runs that couldn't be read are the exception.**" in failed and "whether it is a note or a gap isn't known" in failed.lower()
    assert "counts as a line that couldn't be checked" in failed
    assert "only when neither environment is ready" in failed and "Only when its message says so" in failed
    show = _section(_text(), "Show the report")
    assert "no runs line that couldn't be read is the set-up fine" in show


def _doctor_inputs(tmp_path, **kw):
    from workflow.cli import _read_profile
    from workflow.profile import resolve_experience
    prof, error = _read_profile(KIT)
    assert prof and not error
    environ = kw.pop("environ", {"PATH": str(tmp_path / "no-bin")})  # no `gh`: nothing reaches GitHub
    return doctor.Inputs(root=KIT, kit_root=KIT, profile=prof, profile_error=None,
                         experience=resolve_experience(tmp_path, None, environ=environ), environ=environ, **kw)


def test_doctor_leaves_unread_runs_a_note_as_the_skill_says(tmp_path):
    # What the skill's exception rests on: neither environment found and the runs
    # unreadable give a note, not cant_check, saying the runs couldn't be read.
    envs = tmp_path / "environments.json"
    envs.write_text(json.dumps([{"environments": [{"name": "other", "state": "active"}], "has_more": False}]))
    i = _doctor_inputs(tmp_path, environments_file=envs, runs_file=tmp_path / "missing.json")
    ln, = [ln for ln in doctor.report(i, [doctor.check_environments]).lines if ln.id == "cloud.environments"]
    assert ln.status == "note" and "couldn't be read" in ln.message.new


def test_doctor_reports_workflow_experience_as_the_persons_setting(tmp_path):
    # Why the skill never sets WORKFLOW_EXPERIENCE for the run: kit.experience would name it.
    i = _doctor_inputs(tmp_path, environ={"PATH": str(tmp_path / "no-bin"), "WORKFLOW_EXPERIENCE": "developer"})
    ln, = doctor.report(i, [doctor.check_experience]).lines
    assert "WORKFLOW_EXPERIENCE" in ln.message.new + ln.message.developer


def test_without_a_profile_it_gathers_nothing():
    text = _text()
    assert "`profile_error`" in text and "gather nothing" in text and "`kit.profile`" in text


def test_the_flags_the_skill_gives_doctor_are_the_flags_it_takes():
    cli = (KIT / "scripts/workflow/cli.py").read_text(encoding="utf-8")
    m = re.search(r'^\s*s = sub\.add_parser\("doctor".*?^\s*s\.set_defaults\(fn=cmd_doctor\)', cli, re.M | re.S)
    assert m, "no doctor parser"
    usage = m.group(0)
    assert _doctor_lines(), "no doctor command line"
    for cmd in _doctor_lines():
        cmd = re.sub(r'"<[^"]*>"|<[^>]*>', "", cmd)  # placeholders such as "<what claude --version printed>"
        for flag in re.findall(r"--[a-z-]+", cmd):
            assert f'"{flag}"' in usage, flag


# ---------- a local session ----------


def test_a_local_session_runs_doctor_with_what_gh_gives():
    local = _section(_text(), "In a local session", "###")
    assert "`gh`" in local
    assert any("--environments" not in c and "--json" in c for c in _doctor_lines())


def test_a_local_session_says_the_environments_need_a_cloud_session():
    local = _section(_text(), "In a local session", "###")
    assert "only be checked from a cloud session" in local


def test_cloud_or_local_is_read_from_claude_code_remote():
    assert "`CLAUDE_CODE_REMOTE`" in _text()


def test_old_python_is_led_to_doctors_short_report():
    text = _text()
    assert "Python 3.11" in text and "short report" in text


# ---------- the report ----------


def test_the_report_is_shown_by_experience_most_serious_first():
    show = _section(_text(), "Show the report")
    assert "`wording`" in show
    assert "*new to building*" in show and "*developer*" in show
    assert "most serious first" in show
    # Doctor groups its lines; the skill shows them by status, keeping doctor's order within each.
    assert "keeping doctor's order within each status" in show
    # The session's own level changes only what Claude adds: setting the variable would change kit.experience.
    assert "Don't set `WORKFLOW_EXPERIENCE` for the run" in show
    for status in ("`gap`", "`cant_check`", "`note`", "`fine`"):
        assert status in show, status


def test_it_never_says_fine_for_a_line_doctor_could_not_check():
    show = _section(_text(), "Show the report")
    assert "Never say \"fine\"" in show
    assert "`cant_check`" in show and "how to check it" in show


def test_a_failed_doctor_run_is_never_a_clean_report():
    assert "never a clean report" in _text()


# ---------- the offers ----------


def test_each_offer_is_a_choice_with_not_now():
    offers = _section(_text(), "The offers")
    assert "`AskUserQuestion`" in offers
    assert "**Not now**" in offers
    assert "numbered list" in offers  # no tool: the same choices


def test_it_hands_doctors_offers_over_to_the_upgrade_skill():
    offers = _section(_text(), "The offers")
    for offer in ("protect_main", "restore_protection", "set_up_unattended_runs"):
        assert f"`{offer}`" in offers, offer
        assert offer in doctor.OFFERS, offer
        # The upgrade skill knows the offer by the same name.
        assert f"**`{offer}`**" in _text(UPGRADE), offer
    assert "`upgrade-setup`" in offers
    # The person has just chosen, so the upgrade doesn't ask its own opening choice again.
    assert offers.count("opening choice") == 3
    assert "Protect `main`" in offers and "Set up unattended runs" in offers


def test_only_a_gap_recommends_its_upgrade_and_never_after_a_paid_plan_refusal():
    offers = _section(_text(), "The offers")
    assert "recommended option only on a `gap` line" in offers
    assert "without \"(Recommended)\"" in offers
    assert "After a paid-plan refusal, `protect_main` and `restore_protection` aren't recommended either" in offers
    assert "a paid GitHub plan or a public repository" in offers


def test_an_offer_it_does_not_know_is_named_as_text():
    offers = _section(_text(), "The offers")
    assert "any other offer" in offers.lower()
    assert "as text" in offers


def test_the_line_ids_the_skill_names_are_doctors():
    src = (KIT / "scripts/workflow/doctor.py").read_text(encoding="utf-8")
    ids = set(re.findall(r"`((?:computer|kit|github|cloud|previews)\.[a-z0-9_.]+)`", _text()))
    assert ids, "no line ids named"
    for line_id in ids:
        assert f'"{line_id}"' in src or f"'{line_id}'" in src, line_id


# ---------- the guided start's offer ----------


def _look():
    return _section(_text(START), "1. Look around")


def test_start_offers_it_on_a_local_gap_from_status():
    look = _look()
    assert "**Check the set-up**" in look
    assert "`local_gap` is `true`" in look and "`Local gaps: N" in look
    # The gaps are named from the JSON's messages, worded for the person; the text line has only ids.
    assert "`local_gaps`' messages in `WF status --json`" in look
    assert "`check-setup`" in look
    # One recommended option only: a kit update stays first, and a brand-new project's map gives way.
    assert "then it is the recommended option and first" in look
    assert "this comes second, without \"(Recommended)\"" in look
    assert "unless a kit update or a local gap's **Check the set-up** is offered: then after them" in look


def test_start_offers_it_once_a_session_in_solo_mode():
    look = _look()
    assert "**In solo mode, once a session,**" in look
    assert "don't offer it again for solo mode" in look
    assert "Solo mode: yes" in look
    # The solo-mode line still never offers "Protect `main`" itself (#49).
    assert "Don't offer \"Protect `main`\" here" in look


def test_start_says_never_at_every_session_start():
    assert "never at every session start" in _text(START).lower()


def test_start_offers_set_up_not_check_the_set_up_before_the_kit_is_set_up():
    look = _look()
    assert "Read status's `set_up` first" in look
    assert "offer setting the kit up (below), not this" in look


def test_start_leads_an_old_python_to_doctors_short_report():
    look = _look()
    assert "Python 3.11" in look and "short report" in look


def test_status_json_has_the_fields_start_reads():
    # In-process: `tests/test_status_local_gaps.py` runs the command itself.
    st = status.Status(set_up=True, brand_new=False, own_files=1, local_gaps=[]).as_dict()
    for field in ("local_gap", "local_gaps", "set_up", "solo_mode", "profile_error"):
        assert field in st, field


def test_start_never_offers_it_in_ticket_or_conductor_sessions():
    # The guided start never shows there (its "Only in attended sessions").
    assert "**Only in attended sessions.**" in _text(START)


# ---------- the docs ----------


def test_enforcement_section_5_leads_with_check_the_set_up_and_keeps_the_checklist():
    text = _text(KIT / "docs/enforcement.md")
    sec = _section(text, "5. Checking the set-up")
    first = sec.strip().split("\n\n")[0]
    assert "check the set-up" in first.lower() and "`workflow doctor`" in first
    # The manual checklist is kept underneath, as the reference.
    assert "1. **The ruleset:**" in sec and "5. **The kit:**" in sec
    assert sec.index("check the set-up") < sec.index("1. **The ruleset:**")
    assert "reference" in sec


def test_readme_step_6_leads_with_check_the_set_up_and_keeps_the_checklist():
    text = _text(KIT / "README.md")
    sec = _section(text, "Step 6. Check it", "###")
    first = sec.strip().split("\n\n")[0]
    assert "check the set-up" in first.lower() and "`workflow doctor`" in first
    assert "`check-setup`" in sec
    assert "section 5" in sec and "reference" in sec
    assert "`skills/check-setup`" in text
    assert "with `gh` signed in" in sec
    # The guided start's list of options names it too.
    assert "- **Check the set-up** (recommended, unless a kit update is), when its quick look finds a problem" in text
    assert "(recommended when the project has no code yet, unless a kit update or **Check the set-up** is)" in text


def test_install_doc_points_at_check_the_set_up():
    assert "check the set-up" in _text(KIT / "docs/install.md").lower()


def test_changelog_notes_it_under_unreleased():
    # Read from "## Unreleased" down, so the note still counts once a release moves it.
    notes = since_0110()
    assert "(#63" in notes and "`check-setup`" in notes
