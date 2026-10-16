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
    # The other paths' offer names.
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
    # The new person's one-line result keeps the checks note: experience never
    # changes what the person is told about safety.
    assert "Failing tests don't block a merge yet" in screens


def test_it_never_runs_in_a_ticket_session():
    assert "When `WORKFLOW_ROLE` is `ticket`, don't run it or offer it" in _text()


def test_an_unset_ruleset_follows_protect_main():
    assert "`ruleset` left out" in _section("When it's offered")


def test_a_ruleset_that_was_there_before_or_an_organisations_is_not_reoffered():
    first = _section("Read what is there")
    assert "`Organization`" in first and "message for the owner" in first
    back = _section("Read it back")
    assert "the ruleset this run created" in back
    assert "don't offer the click again" in back
    assert "Don't send the message of step 1 for it" in first
    assert "go back to step 1's not-an-admin path" in first
    assert "Don't hand over the message for the owner: the owner is the person." in first
    assert "with no retry, when the blocker is a ruleset this run didn't make" in _section("The end")


def test_screen_one_ends_with_create_when_screen_two_is_skipped():
    clicks = _section("The guided clicks")
    assert "When screen 2 is skipped (below), end this screen with: click **Create**." in clicks
    assert clicks.index("decide whether screen 2 applies") < clicks.index("**Screen 1")


# Admin first, and the message for the owner.


def test_it_checks_admin_first_and_hands_over_a_message_for_the_owner():
    text = _text()
    admin = _section("Admin first")
    assert "permissions" in admin and "admin" in admin
    assert "only an admin" in admin.lower()
    assert "message for the owner" in admin.lower()
    assert "never stops halfway" in admin.lower()
    # The owner runs the read-back too: only an admin sees a ruleset's bypass list.
    assert 'ask it to "protect main"' in admin
    assert "never guide them into step 3" in admin
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
    # Adding checks later is the third path, named in words: the skill ships
    # into projects, where a kit issue number means their issue.
    assert '"Require these checks"' in clicks
    assert not re.search(r"#\d", _text())


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
    for key in ("protected", "missing", "merge", "checks"):
        assert key in report and f"`{key}" in back, key
    assert protection.CHECKS_NOTE in back
    assert "**Any other exit:**" in back


# The flip PR, only after a protected read-back.


def test_the_pull_request_that_leaves_solo_mode_comes_only_after_a_protected_read_back():
    text = _text()
    flip = _section("Leave solo mode")
    assert "`ruleset = true`" in flip
    assert "**the pull request that leaves solo mode**" in flip
    assert "pull request" in flip
    assert "stays in solo mode until it merges" in flip
    assert "owner" in flip.lower()
    assert 'only once the read-back says `"protected": true`' in flip
    assert "already open" in flip
    assert "never merge it, or enable auto-merge on it, yourself" in flip
    assert text.index("## 4. Read it back") < text.index("## 5. Leave solo mode")


def test_the_line_the_skill_writes_takes_the_template_out_of_solo_mode():
    # The skill writes a plain `ruleset = true` line in [project], in place of the
    # template's commented one or a `ruleset = false` line.
    flip = _section("Leave solo mode")
    assert "`# ruleset = false`" in flip and "`ruleset = false`" in flip
    template = (KIT / "templates/profile.toml").read_text()
    assert "# ruleset = false" in template
    assert "after `base_branch` when neither is there" in flip
    no_line = template.replace("# ruleset = false\n", "")
    for before in (template, template.replace("# ruleset = false", "ruleset = false")):
        after = re.sub(r"^#? ?ruleset = false$", "ruleset = true", before, count=1, flags=re.M)
        assert parse(tomllib.loads(after), KIT).ruleset is True
        # Alone on its line, as the template asks, so a shell check can read it.
        assert re.search(r"^ruleset = true$", after, re.M)
    after = re.sub(r"^(base_branch = .*)$", r"\1\nruleset = true", no_line, count=1, flags=re.M)
    assert "ruleset = true" not in no_line and parse(tomllib.loads(after), KIT).ruleset is True


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


def test_the_readme_points_at_the_upgrade_with_the_clicks_as_its_fallback():
    readme = (KIT / "README.md").read_text()
    m = re.search(r"^### Protect `main`\n(.*?)(?=^### )", readme, re.M | re.S)
    assert m, "no Protect `main` section"
    section = m.group(1)
    assert "upgrade-setup" in section
    assert "Step 3" in section and "Step 4" in section and "fallback" in section
    assert readme.index("### Protect `main`") < readme.index("### Step 3.")
    assert "`skills/upgrade-setup`" in readme


# ---------- the automatic path with `gh` (#67, seam 4 of #38) ----------


def test_the_automatic_path_no_longer_comes_later():
    text = _text()
    assert "An automatic path with `gh` comes in a later release" not in text
    assert "the automatic path with `gh`, come in a later release" not in text
    where = _section("Where things are")
    assert "the kit makes the ruleset and the merge settings itself after one confirmation" in where


def test_the_automatic_paths_conditions_and_the_other_ways():
    which = _section("Which way")
    assert "Read all four before anything is tried" in which
    assert "(`CLAUDE_CODE_REMOTE` isn't `true`)" in which
    assert "`WORKFLOW_ROLE` isn't `conductor`" in which
    assert "`gh auth status --hostname github.com` exits 0" in which
    assert "step 1 read `permissions.admin` as `true` through `gh api`" in which
    # Cloud sessions always take the clicks, and never try the API.
    assert "always the guided clicks (step 3), never the API, even with `gh` there" in which
    # `gh` missing or signed out: the clicks, with how to sign in.
    assert "run `gh auth login` in your own terminal, and ask me again" in which
    # Not an admin: the ready message, before anything is tried.
    assert "step 1's message for the owner, before anything is tried" in which
    assert "On the person's own computer, try `gh api repos/<repo>` first" in _section("Admin first")
    # A claimed admin, or one not read through `gh api`, takes the clicks.
    assert "**Otherwise** (admin claimed with \"I'm an admin: go on\", or read without `gh api`): the guided clicks (step 3)." in which
    text = _text()
    assert text.index("## 1. Admin first") < text.index("## Which way") < text.index("## 2. Read what is there")


def test_the_automatic_path_only_where_no_ruleset_is_on_the_base_branch():
    auto = _section("The automatic path")
    assert auto.lstrip().startswith('Only when "Which way" chose it and step 2 found no ruleset on the base branch.')
    first = _section("Read what is there")
    # Rulesets that don't target the base branch don't count, read from `missing`.
    assert 'every `missing` line that names a ruleset says it "doesn\'t target" the base branch' in first
    # One already there that doesn't protect: the clicks beside it, never an edit.
    assert "by the clicks, on the automatic path too" in first
    assert "never edits an existing ruleset" in first
    # Already protected: nothing created; the merge settings only after a choice.
    assert "nothing is created, and no clicks for the ruleset" in first
    assert '"Turn on GitHub\'s merge settings: allow merge commits and auto-merge" with **Do it now** (recommended) and **Not now**' in first
    assert "send only the merge settings (its step 3.3)" in first


def test_one_confirmation_by_experience_with_the_checks_that_ran():
    screens = _section("The screens")
    assert "**On the automatic path, skip this opening choice:** the automatic path's step 2 is the only confirmation" in screens
    auto = _section("The automatic path")
    confirm = auto[auto.index("**2. One confirmation,**"):auto.index("**3. Then, in order:**")]
    assert "Protect your main branch: GitHub will then refuse changes that skip a pull request or a failing test" in confirm
    assert "**Do it now** (recommended) and **Not now**" in confirm
    assert "*A developer*: the ruleset's settings and the merge settings it will set" in confirm
    assert "**Not now** ends it: nothing is created." in confirm
    # The checks that ran, every page, for ticking.
    assert "--paginate --slurp" in auto and "WF protection --checks-ran" in auto
    assert "Passing ones are ticked by default." in auto
    assert "Names the profile's `ci.required_checks` lists" in auto and "are ticked by default too, when they ran" in auto
    assert "For `restore_protection`, offer only the names the profile already lists" in auto
    assert "naming each with its result" in confirm
    # AskUserQuestion takes four options to a question: every check still fits.
    assert "spread evenly so each question has two to four checks, up to four questions in a follow-up call; with more than sixteen, a numbered list" in confirm
    assert "With a single check, there is no **Choose which**" in confirm
    # Claude Code's prompt, said up front as expected.
    assert "Claude Code will ask you to approve the GitHub command that makes the ruleset. That is expected" in confirm


def test_a_refusal_naming_the_mode_is_answered_with_the_mode_switch():
    auto = _section("The automatic path")
    assert "**A refusal naming the permission mode**" in auto
    assert 'Answer "switch the permission mode and try again"' in auto
    assert "never retry the command in that mode" in auto
    assert "A refusal or a declined prompt sent nothing, so after a mode switch the person can ask again." in auto


def test_the_order_ruleset_merge_settings_read_back_pull_request_that_leaves_solo_mode():
    auto = _section("The automatic path")
    order = [
        "1. **The requests:** `WF protection --protect",
        "2. **The ruleset:** `gh api -X POST repos/<repo>/rulesets --input .workflow/ruleset-request.json`",
        "3. **The merge settings:** `gh api -X PATCH repos/<repo> --input .workflow/merge-request.json`",
        "4. **The read-back:** step 4",
        "5. **The pull request that leaves solo mode:** step 5",
    ]
    at = [auto.index(s) for s in order]
    assert at == sorted(at), order
    flip = _section("Leave solo mode")
    assert "the same pull request adds the ticked names it doesn't already list to `ci.required_checks`" in flip
    assert "never listing one twice" in flip
    assert "When it adds at least one new required check, it names them and carries this marker" in flip
    assert "never removing a name the profile already lists" in flip
    assert "<!-- workflow:required-checks -->" in flip


def test_a_failure_says_what_was_done_and_left_and_gives_the_clicks_for_the_rest():
    auto = _section("The automatic path")
    assert "**A failure at any step:** say what was done and what's left, read back (step 4), and give the clicks for the rest" in auto
    assert "Send the ruleset's `POST` once." in auto
    assert "never retry an edit to the ruleset in solo mode" in auto
    assert "Partial progress is only ever stricter" in auto
    assert "screen 3, then step 5 if the read-back says protected" in auto
    assert "the ruleset's request failed: nothing protects the base branch yet unless the read-back finds the new ruleset" in auto
    assert "the read-back finds something missing in the new ruleset: the clicks on its own page" in auto
    assert "<what was done>; <what's left>: the clicks for it are above." in _section("The end")


def test_the_readme_says_the_kit_makes_the_ruleset_with_the_clicks_as_the_fallback():
    readme = (KIT / "README.md").read_text()
    section = re.search(r"^### Protect `main`\n(.*?)(?=^### )", readme, re.M | re.S).group(1)
    assert section.startswith("\nAsk Claude to protect `main`")
    assert "**On your own computer, with `gh` signed in as the repository's admin:**" in section
    assert "the kit makes the ruleset and the merge settings itself with `gh`" in section
    assert "**In a cloud session, or without `gh`:** guided clicks" in section
    assert "they are its fallback" in section


def test_enforcement_doc_section_one_says_the_kit_makes_the_ruleset():
    doc = (KIT / "docs/enforcement.md").read_text()
    one = re.search(r"^## 1\.[^\n]*\n(.*?)(?=^## )", doc, re.M | re.S).group(1)
    assert "the kit makes this ruleset itself after one confirmation" in one
    assert 'named "Protect <base> (pairnexus-workflow)"' in one
    assert "The clicks stay the fallback whenever a step fails." in one
    # The name it gives is the one `workflow protection --protect` builds.
    body = protection.protect("main", {"full_name": "a/b", "default_branch": "main"})[0].body
    assert body["name"] == "Protect main (pairnexus-workflow)"


# ---------- "Require these checks", the third path (#68, seam 4 of #38) ----------


def _part(title):
    """The text of the `# ...` part (a top-level heading) whose heading contains `title`."""
    m = re.search(rf"^# [^\n]*{re.escape(title)}[^\n]*\n(.*?)(?=^# |\Z)", _text(), re.M | re.S)
    assert m, f"no part {title!r}"
    return m.group(1)


def test_the_third_path_is_named_with_its_offer():
    text = _text()
    assert "Require these checks" in _head()
    assert '**"Require these checks"**' in text
    assert "# Require these checks" in text
    assert text.index("# Protect `main`") < text.index("# Set up unattended runs") < text.index("# Require these checks")
    assert "The third path (offer `require_checks`)." in text
    offers = _section("When it's offered")
    assert "**`require_checks`**" in offers
    # Only through doctor's offer, or when asked; never anywhere else.
    assert "only through `workflow doctor`'s `require_checks` offer" in offers
    assert "`check-setup`" in offers and "the conductor's pre-flight" in offers
    assert "or when the person asks" in offers
    assert "Never anywhere else" in offers


def test_it_waits_in_solo_mode_naming_the_pull_request_that_leaves_it():
    part = _part("Require these checks")
    wait = _section("Solo mode waits")
    assert "`solo_mode` is `true`" in wait
    assert "the checks are added once the pull request that leaves solo mode has merged" in wait
    assert "point at it" in wait
    assert "if it has merged already, the local base branch is behind, so say to pull it and ask again" in wait
    assert "and stop" in wait
    assert part.index("## Solo mode waits") < part.index("## Which ruleset")


def test_the_ruleset_is_the_kits_own_else_the_one_protecting_the_base_branch():
    which = _section("Which ruleset")
    assert '"Protect <base> (pairnexus-workflow)"' in which
    assert "the one ruleset" in which and "protecting the base branch" in which
    assert "several" in which and "none is the kit's" in which and "the clicks naming them" in which
    # Not protected: the offer that fits the profile.
    assert "`restore_protection` when the profile says `ruleset = true`, `protect_main` when `solo_mode` is `null`" in which
    # Only what the read-back counts: a pattern target never reads back.
    assert "exactly as `workflow protection` reads a target" in which
    assert "its `target` is `branch` (a tag or push ruleset never counts)" in which
    assert "no `exclude` entry matches it" in which and "one not starting with `refs/`" in which
    # The patterns the read-back can't match, as protection.UNREAD_GLOB lists them.
    for glob in protection.UNREAD_GLOB:
        assert f"`{glob}`" in which, glob
    assert "isn't counted by the read-back, so checks added to it would never read back: leave it out" in which
    assert "https://github.com/organizations/<org>/settings/rules/<id>" in which
    # An organisation's ruleset is never the kit's to change.
    assert "organisation" in which


def test_the_screen_shows_results_ticks_passing_and_says_why_not_the_others():
    screen = _section("The checks screen")
    assert "WF protection --checks-ran" in screen
    # Reads work in a cloud session too; with no tool for them, it says so.
    assert "they use `gh api` wherever it is signed in, a cloud session too" in screen
    assert "say the checks that ran can't be read from here" in screen
    part = _part("Require these checks")
    assert part.index("## Which way, for the checks") < part.index("## The checks screen")
    assert "with its result" in screen
    assert "Passing ones are ticked by default" in screen
    assert "failing" in screen and "pending" in screen and "not ticked" in screen
    assert "a failing required check blocks every merge until it passes" in screen
    assert "hasn't finished" in screen
    # By experience.
    assert '"GitHub won\'t merge a change until these pass"' in screen
    assert '*A developer* gets the names, and that "Require branches to be up to date" goes on with them' in screen
    # The choices, and "Not now".
    assert "**Require the ticked ones** (recommended" in screen
    assert "**Choose which**" in screen and "**Not now**" in screen
    # A single failing check is never the recommended answer.
    assert "**Require it** (recommended only when it is passing)" in screen
    assert "**Not now** leaves everything as it is" in screen and "`workflow doctor` still says what's left" in screen
    # Already-required ones are left out; nothing left to add says so.
    assert "already required" in screen


def test_the_local_update_after_one_confirmation_with_the_expected_prompt():
    which = _section("Which way, for the checks")
    assert 'The same four conditions as "Which way"' in which
    local = _section("The update with `gh`")
    assert "Claude Code will ask you to approve the GitHub command that changes the ruleset. That is expected" in local
    order = [
        "`gh api repos/<repo>/rulesets/<id> > .workflow/ruleset.json`",
        "`WF protection --require-checks .workflow/ruleset.json",
        ".workflow/checks-request.json",
        "`gh api -X PUT repos/<repo>/rulesets/<id> --input .workflow/checks-request.json`",
    ]
    at = [local.index(s) for s in order]
    assert at == sorted(at), order
    assert "With the Write tool" in local
    # Never-ask modes: the mode switch, never a retry.
    assert 'Answer "switch the permission mode and try again"' in local
    assert "never retry the command in that mode" in local


def test_the_clicks_name_each_check_and_up_to_date_and_the_owner_gets_a_message():
    clicks = _section("The clicks for the checks")
    assert "one screen at a time" in clicks
    assert "https://github.com/<repo>/settings/rules/<id>" in clicks
    assert "**Require status checks to pass**" in clicks
    assert "**Require branches to be up to date before merging**" in clicks
    assert "**Add checks**" in clicks and "exactly" in clicks
    assert "**Save changes**" in clicks
    assert "message for the owner" in clicks
    # Nothing was read for a non-admin: no ids or names guessed.
    assert "but no ruleset id or check names" in clicks
    assert "https://github.com/organizations/<org>/settings/rules/<id>" in clicks


def test_it_reads_back_either_way_and_reoffers_the_click():
    back = _section("Read the checks back")
    assert "either way" in back.lower()
    assert "WF protection --rulesets .workflow/rulesets.json --repo .workflow/repo.json --json" in back
    assert "`checks.required`" in back
    assert "`strict_required_status_checks_policy`" in back
    assert "in plain words" in back and "offer the click again" in back


def test_the_profile_pull_request_with_its_marker_and_none_when_already_listed():
    pr = _section("The profile's pull request")
    assert "`ci.required_checks`" in pr
    assert "`ci.none = false`" in pr
    assert "<!-- workflow:required-checks -->" in pr
    assert "never removing" in pr
    assert "already lists every one of them, no pull request is opened, and say so" in pr
    # Every required name, so a check required by hand before reaches the profile too.
    assert "The names are the read-back's whole `checks.required`, not only the ones ticked now" in pr
    # An open one lacking names gets them, or says which are left.
    assert "if it lists every required name, point at it" in pr
    assert "add them to that branch in a new commit" in pr and "say which names it still lacks" in pr
    assert "open none beside it" in pr
    assert "merging it is the owner's" in pr
    assert "WF profile check" in pr


def test_a_failure_partway_says_what_was_done_and_whats_left_and_only_adds():
    part = _part("Require these checks")
    assert "**A failure partway:** say what was done and what's left" in part
    assert "the clicks for the rest" in part
    assert "Checks are only ever added, never removed" in part


def test_the_protect_path_no_longer_says_adding_checks_comes_later():
    clicks = _section("The guided clicks")
    assert "Adding them later comes in a later release" not in clicks
    assert '"Require these checks"' in clicks


def test_the_readme_and_enforcement_say_checks_are_required_once_ci_has_run():
    readme = (KIT / "README.md").read_text()
    section = re.search(r"^### Protect `main`\n(.*?)(?=^### )", readme, re.M | re.S).group(1)
    assert "once CI has run" in section and "`check-setup`" in section
    doc = (KIT / "docs/enforcement.md").read_text()
    one = re.search(r"^## 1\.[^\n]*\n(.*?)(?=^## )", doc, re.M | re.S).group(1)
    assert "the kit adds the required checks once CI has run" in one
    assert '"up to date"' in one
