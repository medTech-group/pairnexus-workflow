---
name: upgrade-setup
description: Move a project from solo mode to the full set-up, one upgrade at a time. "Protect `main`" makes a ruleset and the merge settings on the base branch with `gh` after one confirmation on the owner's own computer, or guides the person click by click to them everywhere else, reads them back with `workflow protection`, and opens the pull request that leaves solo mode. "Set up unattended runs" asks the questions only runs need, guides the two cloud environments, and writes the answers to the profile in one pull request. Use when the person asks to protect main or to set up unattended runs, or picks either where the kit offers it.
---

# Upgrade the set-up

A project set up in solo mode (`project.ruleset = false`) works attended from the start, with the kit's guard refusing what touches the base branch. This skill takes it the rest of the way, one upgrade at a time, each one offered and never pushed:

- **"Protect `main`"**: a ruleset on the base branch and the merge settings, then a pull request that sets `ruleset = true`. The first part of this file.
- **"Set up unattended runs"**: the questions only runs need, the two cloud environments, and a pull request that writes the answers to the profile. The second part, after it.

"Where things are" and "When it's offered" are shared by both.

Below, `main` stands for the profile's `project.base_branch`: use its real name in everything you show.

## Where things are

**The CLI.** `WF` is:
- `python3 -B .claude/workflow/bin/workflow.py` (vendored);
- or `python3 -B <this skill's directory>/../../scripts/workflow.py` (plugin).

**The repository** (`<repo>`, `owner/name`) is the profile's `project.repo`; the base branch is `project.base_branch`.

**GitHub.** Read with `gh api` where it is signed in, or the GitHub MCP tools in a cloud session. On the person's own computer, with `gh` signed in as the repository's admin, the kit makes the ruleset and the merge settings itself after one confirmation ("The automatic path"). Everywhere else nothing here writes a ruleset or a setting: the person clicks, and this skill reads back. The GitHub MCP tools never write them.

The read-back needs GitHub's own JSON: the repository (`GET repos/<repo>`, with `permissions`, `default_branch` and the merge settings) and each ruleset by its id. Use a tool that returns those responses as they are, `gh api` where it is signed in. When no tool here gives them, treat the rulesets as unreadable ("Protect `main`", step 2).

**Choices** use the `AskUserQuestion` tool, the recommended option first; without it (a headless session), the same choices as a numbered list.

**Only in attended sessions.** When `WORKFLOW_ROLE` is `ticket`, don't run it or offer it: there's nobody to click. Say in the ticket's report that the base branch isn't protected, and carry on. The conductor runs it only at its kick-off, with the owner there.

## When it's offered

Offered, never as a nag, at these moments only. Each comes with "Not now", and "Not now" ends it for that moment:
- when the person asks ("protect main", "set up the ruleset", "set up unattended runs");
- right after the set-up pull request merges, "Protect `main`" once (set-up's own offer), and both in its body as optional next steps;
- in the guard's solo-mode refusal, once it offers "Protect `main`";
- before an unattended run in solo mode, once the conductor's pre-flight offers it;
- by `workflow doctor`, once it exists, when it finds the base branch unprotected.

The offers have names, which `workflow doctor` and the other skills use:
- **`protect_main`**: the project is in solo mode (`ruleset = false`), or set up before solo mode existed (`ruleset` left out, `solo_mode` `null`). The path ends with the pull request that leaves solo mode.
- **`restore_protection`**: the profile says `ruleset = true` but the read-back says the base branch isn't protected (the protection was removed or weakened). The same path, without the pull request that leaves solo mode: the profile is already right.
- **`set_up_unattended_runs`**: the person wants Claude to work while nobody is watching, and the profile names no environments yet (`run.ticket_environment` empty). The second path, "Set up unattended runs".

# Protect `main`

## The screens

Read the person's level and the mode first: `WF status --json` gives `experience.wording_level` (`new` or `developer`; `new` when unknown) and `solo_mode`. The level changes only the words. Both levels get the same steps, the same clicks and the same read-back, and end with the same protection.

**New to building** gets one plain screen, as a choice:

> Protect your main branch: GitHub will then refuse changes that skip a pull request or a failing test.

with **Do it now** (recommended) and **Not now**. Each later step is one short screen in the same plain words, and the end is a one-line result ("`main` is protected." or "`main` isn't protected yet: <the first thing missing>"). When no checks are required yet, the result says so too, since the plain screen promised it: "`main` is protected. Failing tests don't block a merge yet: that comes once CI has run."

**A developer** gets the ruleset's settings listed (from step 3), with the same **Do it now** and **Not now**, and the read-back's report as it is at the end.

**On the automatic path, skip this opening choice:** the automatic path's step 2 is the only confirmation, asked once step 1, "Which way" and step 2 have settled it, and the kit's requests take the place of the clicks ("The automatic path"). Elsewhere, show it first, as above.

## 1. Admin first

Before anything else, read the repository's permissions: `GET repos/<repo>` (`gh api repos/<repo>`, or the GitHub MCP tools), and look at `permissions.admin`. Keep that JSON: the read-back uses it as `--repo`.

- **An admin** (`true`): go on to step 2.
- **Not an admin** (`false`): say plainly that only an admin can do this, since rulesets and the merge settings are under the repository's Settings, which only admins see. Then hand over a ready message for the owner (here, whoever is the repository's admin), in a code block they can copy:
  - what it's for, in one line;
  - the easy way: open a Claude session on the repository and ask it to "protect main", which guides them, reads it back and opens the pull request that leaves solo mode;
  - or by hand: the links and the clicks of step 3, filled in with the repository's name and base branch, then the same request to Claude for the read-back and the pull request.

  The read-back is the owner's too: GitHub shows a ruleset's bypass list only to its admins, so a read-back by someone else never comes back protected. That is the end of this run of the skill: it never stops halfway, with a ruleset half made or a pull request waiting on clicks nobody can make. If the person asks again later, still not an admin, give the message again; never guide them into step 3.
- **Can't tell** (no `permissions` in the answer, or the request failed): say so, and offer both: "I'm an admin: go on" and "Give me the message for the owner".

## Which way

Once step 1 has an answer, decide whether the kit makes the protection itself or guides the clicks. Read all four before anything is tried:

- **Local:** the session runs on the person's own computer (`CLAUDE_CODE_REMOTE` isn't `true`).
- **Attended:** `WORKFLOW_ROLE` isn't `conductor`. The guard refuses a conductor session's ruleset request, so a conductor's kick-off takes the clicks.
- **`gh` signed in:** `gh auth status --hostname github.com` exits 0 (the host alone, so a problem with another account doesn't count). A missing `gh` (command not found) or a non-zero exit counts as signed out.
- **Admin:** step 1 read `permissions.admin` as `true` through `gh api`. "Can't tell", followed by "I'm an admin: go on", isn't enough.

Then:
- **All four:** the automatic path, after step 2's read-back.
- **A cloud session** (`CLAUDE_CODE_REMOTE` is `true`): always the guided clicks (step 3), never the API, even with `gh` there. The automatic path is for the person's own computer only.
- **A conductor session:** the guided clicks.
- **`gh` missing or signed out:** the guided clicks, with one line on the other way, for the person who would rather: "Or install the GitHub CLI (`gh`), run `gh auth login` in your own terminal, and ask me again: I'll then make it for you after one confirmation."
- **Not an admin:** step 1's message for the owner, before anything is tried. Never the automatic path, and never the clicks.
- **Otherwise** (admin claimed with "I'm an admin: go on", or read without `gh api`): the guided clicks (step 3).

## 2. Read what is there

Before guiding any click, fetch the rulesets and read them back with `WF protection`, exactly as step 4 does. Some repositories already have one.

- **Already protected** (`protected` is `true`): nothing is created, and no clicks for the ruleset. If the merge settings are missing, set only those first, since they are part of this upgrade too. Where "Which way" chose the automatic path, ask first, as a choice: "Turn on GitHub's merge settings: allow merge commits and auto-merge" with **Do it now** (recommended) and **Not now**; on **Do it now**, build the requests (the automatic path's step 3.1, with no `--check`) and send only the merge settings (its step 3.3). Otherwise step 3's screen 3. Then, for `protect_main`, go straight to the pull request that leaves solo mode (step 5); for `restore_protection`, say it is protected again and stop.
- **Not protected, with rulesets there:** show what is missing. This skill never edits an existing ruleset, and never guides a change to one: changing a ruleset that was there before is left to a later release. It guides a new ruleset beside them, by the clicks, on the automatic path too: the kit makes a ruleset itself only where none targets the base branch yet (below). Note which rulesets were there before this run: step 4 needs to know.
  - When an existing one stops the verdict whatever is added (its bypass list, say), say which ruleset and what in it, and that it is its admin's to change. Don't guide a new ruleset that can't help.
  - An organisation's ruleset (`source_type` `Organization`) is the organisation owner's, even for a repository admin: say which one and what in it (its bypass list, or that its bypass list can't be read from here), and that the organisation owner changes it or reads it back. Don't send the message of step 1 for it: running this skill again as a repository admin gives the same answer.
  - A repository's own ruleset whose bypass list "can't be read":
    - when step 1 couldn't tell and the person chose "I'm an admin: go on", they aren't its admin after all: go back to step 1's not-an-admin path and hand over the message for the owner;
    - when step 1 read `permissions.admin` as `true`, the GitHub access this session uses can't see bypass lists (a token without admin rights): say so, and that the read-back needs access with admin rights, such as `gh` signed in as the person. Don't hand over the message for the owner: the owner is the person. Nothing in the ruleset needs a click, so stop here, and read it back again once the session has that access.
- **No rulesets,** or only ones that don't target the base branch (every `missing` line that names a ruleset says it "doesn't target" the base branch; the other lines are the rules still missing): the automatic path when "Which way" chose it, otherwise step 3.
- **Can't read the rulesets** (no access from here): say so. Guide the clicks anyway, but without a read-back there is no pull request that leaves solo mode: an unknown counts as unprotected.

## The automatic path

Only when "Which way" chose it and step 2 found no ruleset on the base branch. Existing rulesets were read back first (step 2), and none is ever edited: the kit only creates one beside them.

**1. The checks that already ran.** Fetch the base branch's latest commit's check runs and statuses, every page, then hand them to `WF protection` with the rulesets of step 2:

- `gh api --paginate --slurp 'repos/<repo>/commits/<base>/check-runs?per_page=100' > .workflow/check-runs.json`;
- `gh api --paginate --slurp 'repos/<repo>/commits/<base>/status?per_page=100' > .workflow/status.json`;
- `WF protection --checks-ran .workflow/check-runs.json --statuses .workflow/status.json --rulesets .workflow/rulesets.json --repo .workflow/repo.json --base <base> --json`.

Its `checks` are the ones to offer, each with its `result` (`passing`, `failing` or `pending`). Passing ones are ticked by default. Names the profile's `ci.required_checks` lists (a starter project's lists its checks from the start) are ticked by default too, when they ran. For `restore_protection`, offer only the names the profile already lists: its pull request is not opened, so no new name could reach the profile. Exit 2 (an input is wrong, often a page missing) or any other failure: fetch again once; if it still fails, offer no checks and say "checks not required yet", and why. A `gh` that answers "unknown flag: --slurp" is older than the kit needs: say to update `gh`.

**2. One confirmation,** worded by experience as "The screens" are, and asked once with `AskUserQuestion`:

- *New to building*: "Protect your main branch: GitHub will then refuse changes that skip a pull request or a failing test", with **Do it now** (recommended) and **Not now**.
- *A developer*: the ruleset's settings and the merge settings it will set, from the requests below (`WF protection --protect …` without `--json` prints them, given a `--check` for each name ticked by default), with the same **Do it now** and **Not now**. Say the checks rule follows the ticks.
- **The checks that ran,** when there are any, in the same call as a second question: **Require the ticked ones** (recommended, naming each with its result, so a failing one is seen: a failing required check blocks every merge until it passes), **Choose which** (then one multiSelect question listing every check with its result), and **None for now**. When none ran, say "checks not required yet" instead.
- Then, on the same screen: "Claude Code will ask you to approve the GitHub command that makes the ruleset. That is expected: it is how the kit's guard lets you see it first."

**Not now** ends it: nothing is created. Without `AskUserQuestion`, the same choices as a numbered list.

**3. Then, in order:**

1. **The requests:** `WF protection --protect --repo .workflow/repo.json --base <base> [--check NAME ...] --json > .workflow/protect.json`, one `--check` for each ticked name. It gives the ruleset `POST`, then the merge-settings `PATCH`, and sends nothing. With the Write tool, put the first request's `body` in `.workflow/ruleset-request.json` and the second's in `.workflow/merge-request.json`, checking each `method` and `path` against the commands below. Exit 2 or any other failure: nothing was sent; say so and give the clicks (step 3).
2. **The ruleset:** `gh api -X POST repos/<repo>/rulesets --input .workflow/ruleset-request.json`. The guard asks; Claude Code's prompt is the person's approval. Note the new ruleset's `id` from the answer: step 4 counts it as the ruleset this run created.
3. **The merge settings:** `gh api -X PATCH repos/<repo> --input .workflow/merge-request.json` (allow merge commits and auto-merge; not asked).
4. **The read-back:** step 4, with the new ruleset fetched in full among the others.
5. **The pull request that leaves solo mode:** step 5, once the base branch reads as protected, with the ticked names.

**A refusal naming the permission mode** (the guard says nobody is asked in `bypassPermissions` or `dontAsk`): nothing was sent. Answer "switch the permission mode and try again" (Shift+Tab, or the mode selector), and never retry the command in that mode. Any other refusal, or the person declining Claude Code's prompt: nothing was sent; say so, and offer the clicks (step 3).

**A failure at any step:** say what was done and what's left, read back (step 4), and give the clicks for the rest:
- the ruleset's request failed: nothing protects the base branch yet unless the read-back finds the new ruleset; step 3's screens for what is missing;
- the merge settings failed: the ruleset stands; screen 3;
- the read-back finds something missing in the new ruleset: the clicks on its own page, as step 4 says.

Send the ruleset's `POST` once. After a failure, read back and give the clicks: never send the `POST` a second time once it was sent, and never retry an edit to the ruleset in solo mode, since a second ruleset, or one changed by the kit, is not this path's. A refusal or a declined prompt sent nothing, so after a mode switch the person can ask again. Partial progress is only ever stricter: a ruleset without the merge settings protects more than nothing, and the guard stays in solo mode until the pull request that leaves it merges.

## 3. The guided clicks

For everyone the automatic path isn't for: one screen at a time, each with a link to the exact settings page, in every kind of session. Before showing screen 1, decide whether screen 2 applies (its test is below), so screen 1 knows whether it ends with **Create**. After each screen, wait for "Done" (or "Something's different", then help with what they see).

**Screen 1: the ruleset.** Open `https://github.com/<repo>/settings/rules/new?target=branch` (**Settings → Rules → Rulesets → New ruleset → New branch ruleset**) and fill it in:
- **Ruleset name:** anything, for example `main`.
- **Enforcement status:** **Active**. "Disabled" and "Evaluate" enforce nothing.
- **Bypass list:** leave it empty. Sessions act through the person's GitHub account, so anything they can bypass, a session could too.
- **Target branches:** **Add target → Include default branch**. If the base branch isn't the default branch, add it by name instead.
- **Rules**, tick:
  - **Restrict deletions**;
  - **Block force pushes**;
  - **Require a pull request before merging**, with **Required approvals: 0** and **Require review from Code Owners** left unticked (GitHub never lets an author approve their own pull request, and sessions post as the person).
- Leave **Require linear history** unticked: the kit merges with a merge commit, which it forbids.
- When screen 2 is skipped (below), end this screen with: click **Create**.

**Screen 2: the required checks.** Only when CI has already run on the base branch and the profile lists its checks (`ci.required_checks`): check that each name appears in the base branch's latest check runs (`GET repos/<repo>/commits/<base>/check-runs?per_page=100`, every page). If they all do, add to the same ruleset before creating it: **Require status checks to pass**, **Require branches to be up to date before merging**, and **Add checks** with each name exactly. Otherwise skip this screen and report "checks not required yet": the ruleset protects the base branch without them, and they are added once CI has run and their names are known. Adding them later comes in a later release; leave the ruleset as it is for that.

Then click **Create**, at the end of whichever of screens 1 and 2 is the last.

**Screen 3: the merge settings.** Open `https://github.com/<repo>/settings` (**Settings → General**) and scroll to **Pull Requests**:
- keep **Allow merge commits** ticked: sessions and the conductor always merge with a merge commit;
- tick **Allow auto-merge**.

## 4. Read it back

Fetch, then hand the files to `WF protection`. Write them under `.workflow/`, which git ignores:

1. The rulesets, **each in full**: list the ids with `GET repos/<repo>/rulesets?includes_parents=true` (every page), then fetch each one by its id with `GET repos/<repo>/rulesets/<id>`, through the repository even for an organisation's ruleset. Put them in one JSON list in `.workflow/rulesets.json`. The list endpoint alone gives summaries without their rules, which the command refuses.
2. The repository's settings: `GET repos/<repo>` again, to read the merge settings as they are now, in `.workflow/repo.json`.
3. Run `WF protection --rulesets .workflow/rulesets.json --repo .workflow/repo.json --json`. Always give `--repo`: without it, a ruleset on the default branch can't be counted.

Check the exit code before reading the output:
- **Exit 2:** an input is wrong (the message is on standard error, and nothing is printed). Fetch again, usually a ruleset that wasn't fetched in full; never read it as protected.
- **Any other exit:** the command failed. Show its error, and count the base branch as not protected.
- **Exit 0:** read the JSON.
  - `protected` is `true`: the base branch is protected. Say so in one line (new to building), or show the report (developer).
  - `protected` is `false`: show each line of `missing` in plain words, and offer the click again, as a choice with "Not now":
    - in the ruleset this run created, the fix is on that ruleset's own page (`https://github.com/<repo>/settings/rules/<id>`): it is the person's, made a minute ago, so correcting it is part of the same clicks, not an edit of an existing ruleset;
    - a merge setting: screen 3 again;
    - in a ruleset that was there before, or an organisation's: don't offer the click again. Say whose it is, as step 2 does.

    Then read it back again.
  - `merge`: its `missing` lines are the merge settings that are off or unknown. Offer screen 3 again for them. They don't change the verdict.
  - `checks.note` is "checks not required yet" when no checks are required: report it as that, not as a failure.

The read-back doesn't check approvals or Code Owners yet. Look at the `pull_request` rule's `parameters` in the fetched rulesets yourself: if `required_approving_review_count` is above 0 or `require_code_owner_review` is `true`, say that unattended runs will then stop at "ready for review". It doesn't stop the pull request that leaves solo mode.

## 5. Leave solo mode

Only for `protect_main`, and only once the read-back says `"protected": true`. First look for one already open (from `workflow/protect-main`, or any open pull request changing `ruleset` in the profile): if there is one, point at it rather than opening another. Then open **the pull request that leaves solo mode**: a small one that sets `ruleset = true`.

1. A branch from the base branch, such as `workflow/protect-main`.
2. In `.claude/workflow/profile.toml`'s `[project]` table, a plain `ruleset = true` line on its own: in place of a `ruleset = false` line, or of the template's commented `# ruleset = false`, or after `base_branch` when neither is there.
   - When names were ticked on the automatic path, the same pull request adds the ticked names it doesn't already list to `ci.required_checks`, after the names already there, never removing a name the profile already lists and never listing one twice.
   - Change nothing else.
3. `WF profile check` passes, and `WF status --json` gives `solo_mode: false` on the branch.
4. Push the branch and open the pull request. Its body: what the read-back found (the report, "checks not required yet" if so), and that merging it takes the project out of solo mode. When it adds at least one new required check, it names them and carries this marker on a line of its own, so `workflow doctor` can name the pull request while it's open:

   ```
   <!-- workflow:required-checks -->
   ```

Tell the person: the guard stays in solo mode until it merges, so until then the kit is only stricter, never looser. Merging it is the owner's: never merge it, or enable auto-merge on it, yourself.

## The end

Say where it stands in one line, adding the checks line from "The screens" when no checks are required yet:
- "`main` is protected, and the pull request that leaves solo mode is #<n>: merge it when you're ready.";
- "`main` is protected again." (`restore_protection`);
- "`main` isn't protected yet: <what's missing>." with the choice to try that screen again;
- on the automatic path after a failure, "<what was done>; <what's left>: the clicks for it are above.";
- after a refusal naming the permission mode, "Nothing was changed: switch the permission mode and try again.";
- "`main` isn't protected yet: <ruleset> is <the organisation owner's, or its admin's> to change." with no retry, when the blocker is a ruleset this run didn't make;
- "`main` isn't protected yet: this session can't read <ruleset>'s bypass list. Read it back with `gh` signed in as you." with no retry, when the access here lacks admin rights;
- or, not an admin, "The message for the owner is above."

# Set up unattended runs

The second path (offer `set_up_unattended_runs`). It takes a project that works attended to one where the conductor can build ready tickets in cloud sessions while nobody is watching: it asks the questions only runs need, which set-up leaves out, guides the two cloud environments, and writes the answers to the profile in one pull request.

**The vendored kit only.** Cloud sessions don't install the plugin from a project's settings, so unattended runs need the vendored kit. In plugin mode (no `.claude/workflow/lock.json`), say so plainly, and that moving to vendored mode is the kit's `setup-workflow` skill run again in vendored mode; then stop.

**By experience.** *New to building* first gets one plain screen, as a choice: "Set up unattended runs: Claude can then build ready tickets in its own cloud sessions while you're away, and merge what passes." with **Do it now** (recommended) and **Not now**; each later step is one short screen in the same plain words. A developer gets the list of what it writes (step 4) instead. Both get the same steps.

## 1. Protect `main` first

Read `WF status --json` and look at `solo_mode`.

- **`true`** (solo mode, `ruleset = false`): if the person already went through "Protect `main`" in this session, whatever their answer or its end (**Not now**, the message for the owner, a pull request not yet merged), don't ask again: point at that pull request if there is one, show the warning below if `main` still isn't protected (a protected read-back with that pull request waiting needs none), and go on to step 2. Otherwise offer "Protect `main`" first, as a choice with **Protect `main` first** (recommended) and **Not now**.
  - **Protect `main` first:** follow the first part of this file (`protect_main`) from "The screens", reading the level as it says, but skipping its opening choice (the person has just chosen), then come back here, whatever its end: a message for the owner or a "no retry" end stops that path, not this one. Its pull request and this path's are separate. If `main` still isn't protected when you come back, show the warning below, as for **Not now**, and go on.
  - **Not now:** show the warning, in plain words, and go on to step 2:

    > Without a ruleset on `main`, GitHub won't hold a merge for failing checks: the kit's own "never merge while CI is red" check is the only one. A run in solo mode never uses GitHub's auto-merge, and the conductor's pre-flight shows this gap before each run, to fix or to accept.
- **`false`** (protected) **or `null`** (set up before solo mode existed): go on to step 2.

## 2. The questions only runs need

Use `AskUserQuestion`, the recommended answer first. Read the profile first: where it already has a value, offer it as the default. Ask only what exploring the repository and the profile doesn't settle:

| Topic | What to ask | Where it goes |
|---|---|---|
| Areas | The parts of the project two sessions shouldn't touch at once: features, layers or packages, each with the globs of its files. The conductor runs at most one session per area. | `[areas]` |
| Environment names | The names of the two claude.ai environments, one for ticket sessions and one for the conductor, such as `<project>-ticket` and `<project>-conductor`. Repositories whose setup scripts match can share them. | `run.ticket_environment`, `run.conductor_environment` |
| Permission mode | The mode ticket sessions run in: `auto` (recommended), so an unattended session never stops to ask; `bypassPermissions` only in a sandbox; `dontAsk` or `acceptEdits` only with allow rules for the commands sessions run. No more permissive than the conductor session's own. | `run.permission_mode` |
| Merge approvals | Can a pull request merge with no human approval? Unattended runs need that to merge. It isn't a profile setting: it is the ruleset's **Required approvals**. If the team requires an approval, keep it; each run's conductor sees it and recommends the merge mode **owner**, so runs end at "ready for review". The merge mode is chosen per run in the charter, not in the profile. | nowhere (the ruleset) |
| Releases | Which commands deploy, and what runs after merges, each step with its smoke test. A run deploys only under a release grant in its charter. | `guard.deploy_commands`, `[[release.steps]]` |
| Repair | Only when exploring found services the tests need (Docker, a database): what a fresh or restarted container needs started. Each command must be safe to run twice. | `[repair]` `commands` |

Then work out the environments' setup script from the repository, without asking: only machine tools the cloud image lacks (it has Python, Node.js, Java, Go, Rust, Ruby, PHP, Docker, PostgreSQL and Redis), never reading the repository's files, exiting 0, in about five minutes. It is empty for most projects; downloading Flutter for a Flutter app is the usual exception. It goes in `run.environment_setup`. The project's own dependencies are `commands.setup`, which set-up wrote already.

## 3. The two environments

One guided screen, filled in with this project's values. No API creates them: the person makes both on claude.ai, and this session can't see what they hold.

- **Where:** in the desktop app, a new Code session's environment dropdown → **Cloud** → **Add cloud environment**; in a browser, claude.ai/code's cloud environment menu → **Add environment**. Either way it is the same environment, so make each one once.
- **The ticket environment,** named exactly `<run.ticket_environment>`:
  - **Environment variables:** only `WORKFLOW_ROLE=ticket`;
  - **Secrets:** no secrets. Leave **Network secrets** empty, and put no key or token in a variable: tests use fakes, and a session can't misuse a key it doesn't have;
  - **Network access:** the default, unless a session later reports a blocked host;
  - **Setup script:** `run.environment_setup` exactly as it is to be pasted, or "leave Setup script blank" when it is empty.
- **The conductor environment,** named exactly `<run.conductor_environment>`:
  - **Environment variables:** `WORKFLOW_ROLE=conductor`;
  - **Secrets:** no secrets, unless runs release: then only what the release steps need;
  - **Setup script:** the same as the ticket environment's.
- **Why the names must match:** the conductor finds the ticket environment by its name and starts every ticket session in it; with no environment of that name, a run stops before starting anything.

Wait for "Done" (or "Something's different", then help with what they see). Then ask the person to confirm the ticket environment has no secrets.

## 4. One pull request

All the answers go in one pull request. First look for one already open (from `workflow/unattended-runs`, or any open pull request changing these settings): if there is one, point at it rather than opening another.

1. A branch from the base branch, such as `workflow/unattended-runs`.
2. In `.claude/workflow/profile.toml`, the answers: `[areas]`, `run.ticket_environment`, `run.conductor_environment`, `run.permission_mode`, `run.environment_setup`, `guard.deploy_commands`, `[[release.steps]]` and `[repair]`. Change nothing else; `ruleset` is the first path's.
3. `WF profile check` passes.
4. Push the branch and open the pull request. Its body: the answers, the two environments as the person made them, and that the conductor's pre-flight confirms the environments by name at the start of every run.

It changes `.claude/`, so merging it is the owner's: never merge it, or enable auto-merge on it, yourself.

## 5. Where it ends

Say where it stands in one line:
- "Unattended runs are set up once #<n> merges: then start a session in the conductor environment and ask it to run the backlog unattended.";
- when `main` still isn't protected (after "Not now" to "Protect `main`", or after that path), add: "`main` isn't protected: GitHub won't hold a merge for failing checks.";
- in plugin mode, "Unattended runs need the vendored kit."
