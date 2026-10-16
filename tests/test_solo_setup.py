"""#48: the solo set-up, and the "Set up unattended runs" upgrade (solo mode,
#32). Seam 4: the skills' wording, read from their files as the kit-release
tests do, plus the lines set-up writes, parsed as the profile parses them."""

import re
import tomllib

from conftest import KIT
from workflow.profile import parse

SETUP = KIT / "skills/setup-workflow/SKILL.md"
UPGRADE = KIT / "skills/upgrade-setup/SKILL.md"


def _section(path, title, level="##"):
    """The text of the `<level> ...` section whose heading contains `title`."""
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"^{level} [^\n]*{re.escape(title)}[^\n]*\n(.*?)(?=^{level} |\Z)", text, re.M | re.S)
    assert m, f"no section {title!r} in {path.name}"
    return m.group(1)


def _asked_topics():
    """The first column of set-up's question table."""
    ask = _section(SETUP, "Ask")
    rows = [l for l in ask.splitlines() if l.startswith("|") and not l.startswith("|---")]
    return [r.split("|")[1].strip() for r in rows[1:]]


# Set-up asks only what attended work needs.


def test_setup_asks_only_what_attended_work_needs():
    assert _asked_topics() == ["Experience", "Mode", "Owner", "Sensitive data", "Explorer", "Deploy commands", "Earlier flow"]
    ask = _section(SETUP, "Ask")
    # The experience default's two levels, as the profile names them.
    assert "*new to building*" in ask and "*developer*" in ask
    # Deploy commands only when exploring found deploy scripts.
    row = next(l for l in ask.splitlines() if l.startswith("| Deploy commands"))
    assert "Only when exploring found deploy scripts" in row
    # Everything else takes the template's default.
    assert "Everything else takes the template's default" in ask


def test_setup_no_longer_asks_the_run_only_questions():
    for topic in ("Areas", "Environments", "Merging", "Releases", "Permission mode", "Repair"):
        assert topic not in _asked_topics(), topic
    ask = _section(SETUP, "Ask")
    # They are asked by the second upgrade, never nowhere.
    assert "areas, environment names, ticket sessions' permission mode, merge approvals and releases" in ask
    assert '"Set up unattended runs"' in ask
    head = SETUP.read_text().split("---", 2)[1]
    for word in ("areas", "releases", "one-time steps"):
        assert word not in head, word


def test_setup_writes_ruleset_from_the_read_back_as_a_plain_line():
    write = _section(SETUP, "Write, on a branch")
    assert "`WF protection --rulesets" in write and "--repo" in write
    # The base branch given, never read from whichever profile the command finds.
    assert "--base <the base branch>" in write and "Always give `--base`" in write
    # A ruleset fetched as a summary is fetched again before solo mode is chosen.
    assert "fetch each in full by its id again, once" in write
    assert '`"protected": true`' in write
    assert "`ruleset = true`" in write and "`ruleset = false`" in write
    # An unknown counts as unprotected: unreadable rulesets, a failed command,
    # a bypass list it can't see.
    assert "can't be read" in write and "an unknown counts as unprotected" in write
    assert "**Exit 2**" in write
    # A plain line, where the template has its commented one.
    assert "in place of the template's `# ruleset = false`" in write
    assert "on a line of its own" in write
    # The experience from the answer.
    assert '`experience = "new"`' in write and '`experience = "developer"`' in write
    # A skipped answer writes nothing: left out, the level is unknown.
    assert "When the question was skipped, leave the template's commented line as it is" in write


def test_the_lines_setup_writes_parse_as_the_profile_reads_them():
    template = (KIT / "templates/profile.toml").read_text()
    for ruleset in ("true", "false"):
        for level in ("new", "developer"):
            after = template.replace("# ruleset = false", f"ruleset = {ruleset}", 1)
            after = after.replace('# experience = "new"', f'experience = "{level}"', 1)
            p = parse(tomllib.loads(after), KIT)
            assert p.ruleset is (ruleset == "true") and p.experience == level
            # Alone on its line, so the shell wrapper reads it without TOML.
            assert re.search(rf"^ruleset = {ruleset}$", after, re.M)


def test_profile_checks_environment_warnings_are_expected_not_asked():
    write = _section(SETUP, "Write, on a branch")
    assert "those are expected until \"Set up unattended runs\" names them" in write
    assert "don't ask for the names" in write


def test_the_read_back_files_are_never_committed_in_either_mode():
    write = _section(SETUP, "Write, on a branch")
    assert "In plugin mode, add them yourself" in write
    assert "nothing under `.workflow/`" in write


def test_setup_writes_everything_else_as_today():
    write = _section(SETUP, "Write, on a branch")
    for item in ("CODEOWNERS", "workflow-kit.yml", "workflow-kit-update.yml", "setup-matt-pocock-skills",
                 "CLAUDE.md", "Labels", "ISSUE_TEMPLATE", "vendor install"):
        assert item in write, item


# Its PR body, and the offer after the merge.


def test_the_pr_body_says_merge_and_start_working_with_the_upgrades_as_optional_next_steps():
    text = SETUP.read_text()
    body = _section(SETUP, "The pull request")
    assert "Merge this and start working" in body
    assert "optional next steps" in body
    assert '"Protect `main`"' in body and '"Set up unattended runs"' in body
    # Today's one-time-steps checklist is gone.
    assert "one-time steps" not in text
    assert "**The base branch's ruleset,**" not in text
    assert "- [ ] **" not in text


def test_setup_offers_protect_main_once_after_the_merge():
    after = _section(SETUP, "After the merge")
    assert "offer \"Protect `main`\" once" in after and "**Not now**" in after
    assert "don't offer it again in this session" in after
    # The upgrade runs on the merged base branch, without asking twice.
    assert "git merge --ff-only origin/<base>" in after
    assert "skip its opening choice" in after
    # The skill's path in both modes: the plugin may not be installed yet.
    assert "`$KIT/skills/upgrade-setup/SKILL.md` in plugin mode" in after
    assert "`protect_main`" in after and "upgrade-setup" in after
    # Not offered when set-up found the base branch protected already.
    assert "`ruleset = true`" in after


# "Set up unattended runs", the upgrade skill's second path.


def test_upgrade_setup_has_the_unattended_runs_path():
    text = UPGRADE.read_text()
    assert re.search(r"^# Set up unattended runs$", text, re.M)
    assert "`set_up_unattended_runs`" in _section(UPGRADE, "When it's offered")
    # No longer "a later release".
    assert "It comes in a later release; until then" not in text
    head = text.split("---", 2)[1]
    assert "Set up unattended runs" in head


def _runs(title):
    """A `##` section inside the "Set up unattended runs" part of the skill."""
    text = UPGRADE.read_text()
    part = text[text.index("\n# Set up unattended runs\n"):]
    m = re.search(rf"^## [^\n]*{re.escape(title)}[^\n]*\n(.*?)(?=^## |\Z)", part, re.M | re.S)
    assert m, f"no section {title!r} under Set up unattended runs"
    return m.group(1)


def test_in_solo_mode_it_offers_protect_main_first_with_the_warning_when_skipped():
    first = _runs("Protect `main` first")
    assert "`solo_mode`" in first and "**Not now**" in first
    assert "GitHub won't hold a merge for failing checks" in first
    # Whatever the first path's end, this path goes on, with the warning if needed.
    assert "come back here, whatever its end" in first
    # A "Not now" earlier in the session isn't asked again.
    assert "already went through \"Protect `main`\" in this session, whatever their answer or its end" in first
    assert "If `main` still isn't protected when you come back, show the warning" in first
    text = UPGRADE.read_text()
    assert text.index("## 1. Protect `main` first") < text.index("## 2. The questions only runs need")


def test_it_asks_the_run_only_questions():
    qs = _runs("The questions only runs need")
    for topic in ("Areas", "Environment names", "Permission mode", "Merge approvals", "Releases"):
        assert f"| {topic} |" in qs, topic
    for key in ("[areas]", "run.ticket_environment", "run.conductor_environment", "run.permission_mode",
                "[[release.steps]]", "guard.deploy_commands"):
        assert key in qs, key


def test_it_shows_the_guided_environments_screen():
    env = _runs("The two environments")
    for item in ("WORKFLOW_ROLE=ticket", "WORKFLOW_ROLE=conductor", "no secrets", "run.environment_setup",
                 "run.ticket_environment", "run.conductor_environment", "leave Setup script blank"):
        assert item in env, item
    assert "No API creates them" in env


def test_it_writes_the_answers_in_one_profile_pull_request():
    pr = _runs("One pull request")
    assert "one pull request" in pr.lower()
    assert "`WF profile check`" in pr
    assert "pre-flight" in pr
    assert "never merge it" in pr
    assert "when `main` still isn't protected" in _runs("Where it ends")


def test_the_readme_leads_with_the_solo_setup_and_keeps_the_fallback_steps():
    readme = (KIT / "README.md").read_text()
    start = readme.index("## Getting started")
    step1 = readme.index("### Step 1.")
    intro = readme[start:step1]
    assert "solo mode" in intro
    # Step 1's table no longer lists the run-only questions.
    s1 = readme[step1:readme.index("### Step 2.")]
    for gone in ("| Areas |", "| Environment names |", "| Permission mode |", "| Can a PR merge with no human approval? |"):
        assert gone not in s1, gone
    assert "Merge this and start working" in s1 or "merge it and start working" in s1
    m = re.search(r"^### Set up unattended runs\n(.*?)(?=^### )", readme, re.M | re.S)
    assert m, "no Set up unattended runs section"
    assert "upgrade-setup" in m.group(1) and "Step 5" in m.group(1) and "fallback" in m.group(1)
    assert readme.index("### Set up unattended runs") < readme.index("### Step 5.")
    # Steps 3 to 5 stay, after the upgrades, as their fallback.
    for step in ("### Step 3.", "### Step 4.", "### Step 5."):
        assert readme.index("### Protect `main`") < readme.index(step), step


def test_install_md_matches_the_solo_setup():
    install = (KIT / "docs/install.md").read_text()
    every = install[install.index("## Every project, whichever mode"):]
    assert "one-time steps" not in every
    assert "solo mode" in every and '"Protect `main`"' in every and '"Set up unattended runs"' in every


def test_the_changelog_notes_say_existing_projects_dont_change():
    log = (KIT / "CHANGELOG.md").read_text()
    unreleased = log[log.index("## Unreleased"):log.index("\n## ", log.index("## Unreleased") + 1)]
    m = re.search(r"\*\*The solo set-up[^\n]*\(#48[^\n]*\n(.*?)(?=\n\*\*|\Z)", unreleased, re.S)
    assert m, "no #48 entry under ## Unreleased"
    assert "**For projects updating:**" in m.group(1) and "set up already" in m.group(1)
