"""#47: the "Protect `main`" upgrade, the first path of the `upgrade-setup`
skill (solo mode, #32). Seam 4: the skill's wording, read from its file as the
kit-release tests do, and the skill shipping as the other skills do."""

import json
import re
import tomllib

from conftest import KIT
from workflow import protection, vendor
from workflow.profile import parse

SKILL = KIT / "skills/upgrade-setup/SKILL.md"


def _text():
    return SKILL.read_text(encoding="utf-8")


def _head():
    return _text().split("---", 2)[1]


def _section(title):
    """The text of the `## ...` section whose heading contains `title`."""
    text = _text()
    m = re.search(rf"^## [^\n]*{re.escape(title)}[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert m, f"no section {title!r}"
    return m.group(1)


# The skill exists, Claude may load it, and it names the path and its offers.


def test_the_skill_is_one_claude_may_load():
    head = _head()
    assert re.search(r"^name: upgrade-setup$", head, re.M)
    assert "disable-model-invocation" not in head
    assert re.search(r"^description: .*Protect `main`", head, re.M)


def test_it_names_protect_main_and_its_offers():
    text = _text()
    assert "Protect `main`" in text
    for offer in ("`protect_main`", "`restore_protection`"):
        assert offer in text, offer
    # Where it's offered, and never as a nag.
    offers = _section("When it's offered")
    for place in ("asks", "refusal", "unattended run", "workflow doctor"):
        assert place in offers, place
    assert "never as a nag" in offers.lower()
    # The second path is the next ticket's; its offer name is reserved.
    assert "`set_up_unattended_runs`" in text


# Both screens by experience, the same steps.


def test_it_has_a_screen_for_each_experience_and_the_same_steps():
    screens = _section("The screens")
    assert "`WF status --json`" in screens and "wording_level" in screens
    assert "Protect your main branch: GitHub will then refuse changes that skip a pull request or a failing test" in screens
    assert "**Do it now**" in screens and "**Not now**" in screens
    assert "one-line result" in screens
    assert "developer" in screens.lower() and "ruleset's settings" in screens
    assert "same steps" in screens


# Admin first, and the message for the owner.


def test_it_checks_admin_first_and_hands_over_a_message_for_the_owner():
    text = _text()
    admin = _section("Admin first")
    assert "permissions" in admin and "admin" in admin
    assert "only an admin" in admin.lower()
    assert "message for the owner" in admin.lower()
    assert "never stops halfway" in admin.lower()
    # It is the first thing checked: before reading rulesets and before any click.
    assert text.index("## 1. Admin first") < text.index("## 2. Read what is there") < text.index("## 3. The guided clicks")


# Existing rulesets read back first, never edited.


def test_it_reads_existing_rulesets_back_before_any_click_and_never_edits_one():
    first = _section("Read what is there")
    assert "`WF protection" in first
    assert "already protected" in first.lower() and "the pull request that leaves solo mode" in first
    assert "never edits an existing ruleset" in first


# The guided clicks: ruleset, required checks, merge settings, each linked.


def test_it_lists_the_rulesets_settings_checks_and_merge_settings_with_their_pages():
    clicks = _section("The guided clicks")
    for setting in (
        "Active",
        "default branch",
        "Bypass list",
        "Restrict deletions",
        "Block force pushes",
        "Require a pull request before merging",
        "Required approvals: 0",
        "Code Owners",
        "Require linear history",
        "Allow merge commits",
        "Allow auto-merge",
    ):
        assert setting in clicks, setting
    assert "checks not required yet" in clicks
    assert "ci.required_checks" in clicks
    assert "one screen at a time" in clicks.lower()
    # A link to each exact settings page.
    assert "https://github.com/<repo>/settings/rules/new?target=branch" in clicks
    assert "`https://github.com/<repo>/settings`" in clicks
    # The automatic path and adding checks later are #38's.
    assert "#38" in clicks


# The read-back runs `workflow protection` and offers the click again.


def test_the_read_back_runs_workflow_protection_and_reoffers_the_click():
    back = _section("Read it back")
    assert "WF protection --rulesets" in back and "--repo" in back and "--json" in back
    assert "**Exit 2:**" in back and "**Exit 0:**" in back
    assert "never read it as protected" in back
    assert "`missing`" in back and "offer the click again" in back
    # Each ruleset in full, by its id.
    assert "rulesets/<id>" in _text()


def test_the_read_back_command_names_what_the_skill_relays():
    # The JSON keys the skill reads are the ones `workflow protection --json` gives.
    back = _section("Read it back")
    report = protection.check([], "main", {"allow_merge_commit": True, "allow_auto_merge": True}).as_dict()
    for key in ("protected", "missing", "merge"):
        assert key in report and f"`{key}`" in back, key


# The flip PR, only after a protected read-back.


def test_the_flip_pr_comes_only_after_a_protected_read_back():
    text = _text()
    flip = _section("Leave solo mode")
    assert "`ruleset = true`" in flip
    assert "**the pull request that leaves solo mode**" in flip
    assert "pull request" in flip
    assert "stays in solo mode until it merges" in flip
    assert "owner" in flip.lower()
    assert '"protected": true' in flip or "`protected` is `true`" in flip
    assert text.index("## 4. Read it back") < text.index("## 5. Leave solo mode")


def test_the_flip_the_skill_describes_takes_the_template_out_of_solo_mode():
    # The skill writes a plain `ruleset = true` line in [project], in place of the
    # template's commented one or a `ruleset = false` line.
    flip = _section("Leave solo mode")
    assert "`# ruleset = false`" in flip and "`ruleset = false`" in flip
    template = (KIT / "templates/profile.toml").read_text()
    assert "# ruleset = false" in template
    for before in (template, template.replace("# ruleset = false", "ruleset = false")):
        after = re.sub(r"^#? ?ruleset = false$", "ruleset = true", before, count=1, flags=re.M)
        assert parse(tomllib.loads(after), KIT).ruleset is True


# It ships, vendored and as the plugin, as the other skills do.


def test_it_ships_vendored():
    files = vendor.plan(KIT, None)
    assert files[".claude/skills/upgrade-setup/SKILL.md"] == SKILL


def test_it_ships_in_the_plugin():
    # The plugin is the repository root, and its skills are skills/ (no list in
    # the manifest), so every skill directory with a SKILL.md ships.
    market = json.loads((KIT / ".claude-plugin/marketplace.json").read_text())
    kit = next(p for p in market["plugins"] if p["name"] == "pairnexus-workflow")
    assert kit["source"] == "./"
    assert "skills" not in json.loads((KIT / ".claude-plugin/plugin.json").read_text())
    assert SKILL.parent.parent == KIT / "skills"


def test_the_readme_points_at_the_upgrade_with_the_clicks_as_its_fallback():
    readme = (KIT / "README.md").read_text()
    m = re.search(r"^### Protect `main`\n(.*?)(?=^### )", readme, re.M | re.S)
    assert m, "no Protect `main` section"
    section = m.group(1)
    assert "upgrade-setup" in section
    assert "Step 3" in section and "Step 4" in section and "fallback" in section
    assert readme.index("### Protect `main`") < readme.index("### Step 3.")
    assert "`skills/upgrade-setup`" in readme
