---
name: upgrade-setup
description: Move a project from solo mode to the full set-up, one upgrade at a time. "Protect `main`" makes a ruleset and the merge settings on the base branch with `gh` after one confirmation on the owner's own computer, or guides the person click by click to them everywhere else, reads them back with `workflow protection`, and opens the pull request that leaves solo mode. "Require these checks", once CI has run on the base branch, adds the ticked checks that ran to the ruleset protecting it (with "up to date" on) and to the profile's `ci.required_checks`. "Set up unattended runs" asks the questions only runs need, guides the two cloud environments, and writes the answers to the profile in one pull request. "Add try-it links" takes the owner through Cloudflare one screen at a time, then opens a pull request that turns previews on in the profile and reports its own try-it link once it has built. Use when the person asks to protect main, to require the checks, to set up unattended runs or to add try-it links, or picks one where the kit offers it.
---

# Upgrade the set-up

A project set up in solo mode (`project.ruleset = false`) works attended from the start, with the kit's guard refusing what touches the base branch. This skill takes it the rest of the way, one upgrade at a time, each one offered and never pushed:

- **"Protect `main`"**: a ruleset on the base branch and the merge settings, then a pull request that sets `ruleset = true`. The first part of this file.
- **"Set up unattended runs"**: the questions only runs need, the two cloud environments, and a pull request that writes the answers to the profile. The second part.
- **"Require these checks"**: once CI has run on the base branch, the checks that ran, ticked, added to the ruleset protecting it and listed in the profile's `ci.required_checks`, so failing tests stop merges and the two agree. The third part.
- **"Add try-it links"**: a try-it link on each pull request, from Cloudflare, with no live site: the steps in Cloudflare one screen at a time, then a pull request that turns previews on and shows its own link working. The fourth part, last.

"Where things are" and "When it's offered" are shared by all four.

Below, `main` stands for the profile's `project.base_branch`: use its real name in everything you show.

## Where things are

**The CLI.** `WF` is:
- `python3 -B .claude/workflow/bin/workflow.py` (vendored);
- or `python3 -B <this skill's directory>/../../scripts/workflow.py` (plugin).

**The repository** (`<repo>`, `owner/name`) is the profile's `project.repo`; the base branch is `project.base_branch`.

**GitHub.** Read with `gh api` where it is signed in, or the GitHub MCP tools in a cloud session. On the person's own computer, with `gh` signed in as the repository's admin, the kit makes the ruleset and the merge settings itself after one confirmation ("The automatic path"), and adds required checks to the ruleset the same way ("The update with `gh`"). Everywhere else nothing here writes a ruleset or a setting: the person clicks, and this skill reads back. The GitHub MCP tools never write them.

The read-back needs GitHub's own JSON: the repository (`GET repos/<repo>`, with `permissions`, `default_branch` and the merge settings) and each ruleset by its id. Use a tool that returns those responses as they are, `gh api` where it is signed in. When no tool here gives them, treat the rulesets as unreadable ("Protect `main`", step 2).

**Choices** use the `AskUserQuestion` tool, the recommended option first; without it (a headless session), the same choices as a numbered list.

**Only in attended sessions.** When `WORKFLOW_ROLE` is `ticket`, don't run it or offer it: there's nobody to click. For "Protect `main`", say in the ticket's report that the base branch isn't protected, and carry on. The conductor runs it only at its kick-off, with the owner there, and never runs "Require these checks": its kick-off sends the owner to an attended session for that (the `conductor` skill). It never runs "Add try-it links" either.

## When it's offered

Offered, never as a nag, at these moments only (`require_checks` and `add_try_it_links` have their own, narrower rules, below). Each comes with "Not now", and "Not now" ends it for that moment:
- when the person asks ("protect main", "set up the ruleset", "set up unattended runs", "require the checks");
- right after the set-up pull request merges, "Protect `main`" once (set-up's own offer), and both in its body as optional next steps;
- in the guard's solo-mode refusal, once it offers "Protect `main`";
- before an unattended run in solo mode, once the conductor's pre-flight offers it;
- by `workflow doctor`, once it exists, when it finds the base branch unprotected.

The offers have names, which `workflow doctor` and the other skills use:
- **`protect_main`**: the project is in solo mode (`ruleset = false`), or set up before solo mode existed (`ruleset` left out, `solo_mode` `null`). The path ends with the pull request that leaves solo mode.
- **`restore_protection`**: the profile says `ruleset = true` but the read-back says the base branch isn't protected (the protection was removed or weakened). The same path, without the pull request that leaves solo mode: the profile is already right.
- **`require_checks`**: CI has run on the base branch and some checks that ran aren't required yet (`WF protection --checks-ran … --json` gives a non-empty `checks`). The third path, "Require these checks". Unlike the others it is offered only through `workflow doctor`'s `require_checks` offer (which `check-setup` and the conductor's pre-flight show), or when the person asks ("require the checks", "make failing tests block merges"). Never anywhere else: not after set-up, not in the guard's refusals.
- **`set_up_unattended_runs`**: the person wants Claude to work while nobody is watching, and the profile names no environments yet (`run.ticket_environment` empty). The second path, "Set up unattended runs".
- **`add_try_it_links`**: the project has a Wrangler config and no `[previews]` section in the profile. The fourth path, "Add try-it links". Like `require_checks` it has its own, narrower rule: offered only from the quickstart's next steps, from `workflow doctor`'s `add_try_it_links` offer (which `check-setup` shows), and when the person asks ("add try-it links", "set up previews"). Never at session start, never as a nag, and never to a project whose `[previews]` section turned them off: doctor makes no offer there.

# Protect `main`

## The screens

Read the person's level and the mode first: `WF status --json` gives `experience.wording_level` (`new` or `developer`; `new` when unknown) and `solo_mode`. The level changes only the words. Both levels get the same steps, the same clicks and the same read-back, and end with the same protection.

**New to building** gets one plain screen, as a choice:

> Protect your main branch: GitHub will then refuse changes that skip a pull request or a failing test.

with **Do it now** (recommended) and **Not now**. Each later step is one short screen in the same plain words, and the end is a one-line result ("`main` is protected." or "`main` isn't protected yet: <the first thing missing>"). When no checks are required yet, the result says so too, since the plain screen promised it: "`main` is protected. Failing tests don't block a merge yet: that comes once CI has run."

**A developer** gets the ruleset's settings listed (from step 3), with the same **Do it now** and **Not now**, and the read-back's report as it is at the end.

**On the automatic path, skip this opening choice:** the automatic path's step 2 is the only confirmation, asked once step 1, "Which way" and step 2 have settled it, and the kit's requests take the place of the clicks ("The automatic path"). Elsewhere, show it first, as above.

## 1. Admin first

Before anything else, read the repository's permissions: `GET repos/<repo>` (`gh api repos/<repo>`, or the GitHub MCP tools), and look at `permissions.admin`. On the person's own computer, try `gh api repos/<repo>` first, so the automatic path can use the answer ("Which way"); the MCP tools only when `gh` isn't there or isn't signed in. Keep that JSON: the read-back uses it as `--repo`.

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
- **Not protected, with rulesets there:** show what is missing. This path never edits an existing ruleset, and never guides a change to one: changing a ruleset that was there before is left to a later release (only "Require these checks" adds checks to one, once the base branch is protected). It guides a new ruleset beside them, by the clicks, on the automatic path too: the kit makes a ruleset itself only where none targets the base branch yet (below). Note which rulesets were there before this run: step 4 needs to know.
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
- **The checks that ran,** when there are any, in the same call as a second question: **Require the ticked ones** (recommended, naming each with its result, so a failing one is seen: a failing required check blocks every merge until it passes), **Choose which** (then multiSelect questions listing every check with its result, spread evenly so each question has two to four checks, up to four questions in a follow-up call; with more than sixteen, a numbered list to pick from), and **None for now**. With a single check, there is no **Choose which**: the choice is **Require it** (recommended, when it is ticked by default) and **None for now**. When none ran, say "checks not required yet" instead.
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
- the merge settings failed: the ruleset stands; screen 3, then step 5 if the read-back says protected (the merge settings don't change the verdict);
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

**Screen 2: the required checks.** Only when CI has already run on the base branch and the profile lists its checks (`ci.required_checks`): check that each name appears in the base branch's latest check runs (`GET repos/<repo>/commits/<base>/check-runs?per_page=100`, every page). If they all do, add to the same ruleset before creating it: **Require status checks to pass**, **Require branches to be up to date before merging**, and **Add checks** with each name exactly. Otherwise skip this screen and report "checks not required yet": the ruleset protects the base branch without them, and they are added once CI has run and their names are known, by "Require these checks" (the third part of this file).

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

# Require these checks

The third path (offer `require_checks`). Once CI has run on the base branch, the checks that ran are shown for ticking, then required by the ruleset protecting the base branch, with "Require branches to be up to date" on, and listed in the profile's `ci.required_checks`, so failing tests stop merges and the ruleset and the profile agree. Offered only as "When it's offered" says, each time with **Not now**. Checks are only ever added, never removed: nothing here takes a required check out of a ruleset or a name out of the profile.

The level changes only the words, as in "The screens": read `WF status --json` for `experience.wording_level` and `solo_mode`.

## Solo mode waits

When `solo_mode` is `true` (`ruleset = false`), nothing is changed and no ruleset is read. Say the checks are added once the pull request that leaves solo mode has merged: point at it if one is open (from `workflow/protect-main`, or any open pull request changing `ruleset` in the profile); if it has merged already, the local base branch is behind, so say to pull it and ask again; otherwise say "Protect `main`" opens it, and that its confirmation already offers the checks that ran, so a project with CI is protected and its checks required in one go, and stop.

`false`, or `null` (set up before solo mode existed): go on.

## Which ruleset, and is it protected

1. **Admin first,** exactly as "Protect `main`" step 1 does, keeping the JSON in `.workflow/repo.json`. Not an admin: the message for the owner ("The clicks for the checks" says what it holds), before anything else is tried. Can't tell: the same two choices.
2. **The rulesets, read back:** fetch each in full and run `WF protection` on them, as "Read it back" (step 4) does.
   - `protected` is `false`, or the rulesets can't be read: no checks are added to an unprotected branch. Say what is missing in plain words and offer "Protect `main`" first, then stop: `restore_protection` when the profile says `ruleset = true`, `protect_main` when `solo_mode` is `null` (its pull request sets `ruleset = true`). Its confirmation offers the checks that ran too.
   - `protected` is `true`: go on.
3. **The ruleset to change:** among the fetched rulesets, the ones protecting the base branch are those the read-back counted, exactly as `workflow protection` reads a target:
   - its `target` is `branch` (a tag or push ruleset never counts);
   - its enforcement is active;
   - `conditions.ref_name.include` names `~ALL`, `refs/heads/<base>`, or `~DEFAULT_BRANCH` when the base branch is the default;
   - no `exclude` entry matches it: an entry naming it (as the include names above do) or a pattern matching it, ignoring case, one holding `**`, `[^`, `[!`, `\`, `{` or `}`, and one not starting with `refs/` all count as excluding it.

   A ruleset whose include is any other pattern (`refs/heads/ma*`) isn't counted by the read-back, so checks added to it would never read back: leave it out.
   - The kit's own, named "Protect <base> (pairnexus-workflow)", when one of those is it.
   - Else the one ruleset protecting the base branch, when there is exactly one.
   - When there are several and none is the kit's: the clicks naming them, each with its page, for the person to pick the one to add the checks to. The kit doesn't guess.
   - An organisation's ruleset (`source_type` `Organization`) is the organisation owner's: `WF protection --require-checks` refuses it. Say whose it is, and give the clicks with its page in the organisation's settings (`https://github.com/organizations/<org>/settings/rules/<id>`), for the organisation owner.

## Which way, for the checks

The same four conditions as "Which way", read the same way. All four, and a repository's own ruleset chosen in "Which ruleset": the update with `gh`. A cloud session, `gh` missing or signed out, or an admin claimed with "I'm an admin: go on": the clicks. A conductor session never gets here ("Only in attended sessions"). Not an admin: the message for the owner.

## The checks screen

Fetch the base branch's latest commit's check runs and statuses, every page, with the commands of the automatic path's step 1. These are reads: they use `gh api` wherever it is signed in, a cloud session too (only the update is kept to the person's own computer); without it, a tool that returns GitHub's JSON as it is, `app.slug` and `total_count` included, into the same files. When no tool here gives them, say the checks that ran can't be read from here, and to ask again where `gh` is signed in, and stop. Then `WF protection --checks-ran .workflow/check-runs.json --statuses .workflow/status.json --rulesets .workflow/rulesets.json --repo .workflow/repo.json --base <base> --json`. Its `checks` are the ones to offer, each with its result; those already required (its `required`) and the Cloudflare check are left out by the command. Exit 2 or any other failure: fetch again once; if it still fails, say so and why, and stop. When `checks` is empty, say so ("every check that ran on `main` is already required", or "CI hasn't run on `main` yet") and stop.

Show each check with its result:
- **Passing ones are ticked by default.**
- **Failing and pending ones are not ticked,** and say why: failing, "a failing required check blocks every merge until it passes"; pending, "it hasn't finished, so its result isn't known yet".

By experience, the words only:
- *New to building* gets one plain sentence above the list: "GitHub won't merge a change until these pass".
- *A developer* gets the names, and that "Require branches to be up to date" goes on with them (a branch behind `main` must be updated before it merges).

The choices, with `AskUserQuestion` as the automatic path's checks question has them: **Require the ticked ones** (recommended, naming each with its result), **Choose which** (multiSelect questions, two to four checks each, in a follow-up call; past sixteen, a numbered list), and **Not now**. With a single check: **Require it** (recommended only when it is passing) and **Not now**; a failing or pending one gets **Not now** first. With none ticked by default, no **Require the ticked ones**. On the update with `gh`, the same screen says Claude Code's prompt is expected (below).

**Not now** leaves everything as it is: nothing is sent, and `workflow doctor` still says what's left.

## The update with `gh`

One confirmation: the checks screen is it. On the same screen: "Claude Code will ask you to approve the GitHub command that changes the ruleset. That is expected: it is how the kit's guard lets you see it first." Then, in order:

1. **The ruleset, in full:** `gh api repos/<repo>/rulesets/<id> > .workflow/ruleset.json`, the ruleset chosen above.
2. **The request:** `WF protection --require-checks .workflow/ruleset.json --check NAME ... --json > .workflow/checks.json`, one `--check` for each ticked name. It gives one `PUT` with the ruleset's rules, the names added and "up to date" on, and sends nothing. With the Write tool, put its `body` in `.workflow/checks-request.json`, checking its `method` is `PUT` and its `path` is `repos/<repo>/rulesets/<id>`. Exit 2 or any other failure: nothing was sent; say so, and give the clicks.
3. **The update:** `gh api -X PUT repos/<repo>/rulesets/<id> --input .workflow/checks-request.json`. The guard asks; Claude Code's prompt is the person's approval. Send it once.
4. **The read-back,** below.
5. **The profile's pull request,** below.

**A refusal naming the permission mode** (nobody is asked in `bypassPermissions` or `dontAsk`): nothing was sent. Answer "switch the permission mode and try again" (Shift+Tab, or the mode selector), and never retry the command in that mode. A solo-mode refusal: the profile went back to solo mode, so "Solo mode waits". Any other refusal, or the person declining the prompt: nothing was sent; say so, and offer the clicks.

**A failure partway:** say what was done and what's left, read back, and give the clicks for the rest: the request failed to build or send, the clicks for all of it; the update went through but the read-back finds a name or "up to date" missing, the clicks for those on the ruleset's page; the update went through but the profile's pull request couldn't be opened, the ruleset stands, so say so and give the profile change to make by hand.

## The clicks for the checks

For everyone the update with `gh` isn't for, one screen at a time, each with the link and the exact names to type. After each, wait for "Done" (or "Something's different", then help with what they see).

**Screen 1: open the ruleset.** `https://github.com/<repo>/settings/rules/<id>` (**Settings → Rules → Rulesets →** the ruleset's name). With several and none the kit's, list each with its link and say to open the one that protects `main`. An organisation's ruleset: `https://github.com/organizations/<org>/settings/rules/<id>`, for its owner.

**Screen 2: the checks.** Tick **Require status checks to pass**, and under it **Require branches to be up to date before merging**. Then **Add checks**, and type each name exactly, one at a time: the ticked names, each in a code span. Leave any checks already listed. Click **Save changes**.

A non-admin gets "Protect `main`" step 1's ready message for the owner, in a code block, with these steps instead: what it's for in one line; the easy way, a Claude session on the repository asked to "require the checks", which shows the checks that ran; or by hand these two screens, with the repository's name filled in but no ruleset id or check names (nothing was read for a non-admin, and a name that never ran must not be typed), then the same request to Claude for the read-back and the profile's pull request.

## Read the checks back

Either way, the update with `gh` or the clicks: fetch the rulesets again, each in full, and the repository, as step 4 does, then run `WF protection --rulesets .workflow/rulesets.json --repo .workflow/repo.json --json`, with the same exit-code rules.
- Every ticked name is in `checks.required`, and a ruleset protecting the base branch that requires them (the one they were added to) has `strict_required_status_checks_policy` `true` in its `required_status_checks` rule's parameters: say so in one line (new to building), or show the report (developer).
- Anything missing (a name, "up to date", or the base branch no longer protected): show each in plain words, and offer the click again, as a choice with **Not now**. Then read it back again.

## The profile's pull request

Once the read-back has the names required. The names are the read-back's whole `checks.required`, not only the ones ticked now, so a check required by hand before this run reaches the profile too and the two agree.

First look for one already open (carrying `<!-- workflow:required-checks -->`, or from `workflow/required-checks`): if it lists every required name, point at it rather than opening another. If it lacks some and is the kit's `workflow/required-checks` branch, add them to that branch in a new commit, as step 2 below, and say which. Any other open one (the pull request that leaves solo mode carries the marker too): say which names it still lacks, and open none beside it, since two pull requests changing `ci.required_checks` would conflict; once it merges, asking again adds the rest.

When the profile's `ci.required_checks` already lists every one of them, no pull request is opened, and say so ("the profile already lists them", as a starter project's does from the start). Otherwise:

1. A branch from the base branch, such as `workflow/required-checks`.
2. In `.claude/workflow/profile.toml`'s `[ci]` table, add the required names the profile doesn't list to `ci.required_checks`, after the names already there, never removing one and never listing one twice; and set `ci.none = false` when it was `true`. Change nothing else.
3. `WF profile check` passes.
4. Push the branch and open the pull request. Its body: the names now required, the read-back's report, and this marker on a line of its own, so `workflow doctor` can name the pull request while it's open:

   ```
   <!-- workflow:required-checks -->
   ```

The profile is a protected path: merging it is the owner's. Never merge it, or enable auto-merge on it, yourself.

## Where the checks end

Say where it stands in one line:
- "<names> are required on `main`, and the profile's pull request is #<n>: merge it when you're ready." (or "…; the profile already lists them.");
- "Nothing was changed." after **Not now**;
- "The checks wait for the pull request that leaves solo mode." in solo mode;
- "<what was done>; <what's left>: the clicks for it are above." after a failure;
- "Nothing was changed: switch the permission mode and try again." after a refusal naming the mode;
- or, not an admin, "The message for the owner is above."

# Add try-it links

The fourth path (offer `add_try_it_links`). It takes a project whose app runs on Cloudflare Workers to one where each pull request gets a try-it link: a working copy of the change, to try before merging it. It follows the steps of the kit's page on try-it links, one screen at a time (screen N is the page's step N), then opens a pull request that turns previews on in the profile and reads that pull request's own link to show it working. Connecting Cloudflare this way puts no live site on the internet.

**The page** is `.claude/workflow/docs/previews.md` (vendored) or the kit's `docs/previews.md` (plugin), "Add try-it links to your pull requests". Its steps (`#the-steps`) are the steps here, and its table of build-log messages (`#when-a-build-fails`) has the fix for each. Link it from the screens, so the person can read ahead.

**It never signs in to Cloudflare,** connects anything or changes a Cloudflare setting: the person clicks in Cloudflare's dashboard and says "Done", and this path writes only the pull requests. What Cloudflare holds can't be read from here, except what its app reports on the repository (its check and its bot's comment on a pull request), which `WF preview` reads. Its build logs are behind a Cloudflare sign-in too: the person reads them.

**The Wrangler lines** are the three settings step 6 of the page gives: `workers_dev = false` (the Worker's own public address off, so no live site), `preview_urls = true` (the preview links on: each deploy of the base branch sets **Preview URLs** from this line, whatever the dashboard says) and a `[previews]` block (even empty: without it Cloudflare's preview build fails with "missing a `previews` block"). In a `wrangler.json` or `wrangler.jsonc` they are `"workers_dev": false`, `"preview_urls": true` and `"previews": {}`.

**The conductor never runs it,** and neither does a ticket session ("Only in attended sessions"): there is nobody to click.

## What it needs

Read these first, before any screen:

- **A Wrangler config** at the project's root: `wrangler.toml`, `wrangler.json` or `wrangler.jsonc`, the file that tells Cloudflare how to run the app on Cloudflare Workers. Without one, say plainly that try-it links need an app that runs on Cloudflare Workers, and this project has none yet, then stop: nothing is changed. With a `wrangler.toml` and a JSON one beside it, Cloudflare reads the JSON one: every change below goes there, and say so.
- **Sensitive data:** read `[sensitive]` `patterns` from `.claude/workflow/profile.toml` itself (`WF profile check` doesn't print them). The project has sensitive data when they aren't empty, the template's secret-key patterns included, so most projects do: say so when it comes up, since it means screen 7.
- **The profile's `[previews]`:** whether the section is there at all, read from `profile.toml` itself, and its `on` and `access` through `WF profile check`, which prints them the same with or without a section:
  - `on = true` already: say try-it links are on, and read the Wrangler config from the checkout (doctor's `previews.setup` line can't check a JSON one). With sensitive data and a `preview_urls` that isn't `true`, the links may have been turned off for want of Access: ask screen 5 (Preview URLs on) and then screen 7 first, never turning them on from the profile's old `access = true`, and on **I can't turn it on** take the route below for a refused profile. When it lacks any of the Wrangler lines, open a pull request adding only the missing Wrangler lines (as the proof pull request's step 3 does); the person merges it, since merging it deploys the base branch. Then read its link as "Its own try-it link" does. Otherwise offer to read an open pull request's link, and stop: there are no steps left.
  - A `[previews]` section that doesn't say `on = true`: they were turned off on purpose (doctor makes no offer there, so the person asked). Say so, and ask once, with **Turn them on** and **Not now**, before going on.
  - `WF profile check` refuses the profile because `on = true` lacks `access = true` (its error starts "previews.on is true but previews.access isn't"): go straight to screen 7. On **Access is on**, a pull request sets `access = true`, and `preview_urls = true` in the Wrangler config when it says otherwise, as doctor's fix says; then "Its own try-it link" for it. On **I can't turn it on**, as screen 7's says: Preview URLs off in the dashboard first, then one pull request (from `workflow/no-previews`) setting `on = false`, taking out any `access = true` (the owner has just said Access isn't on), and setting `preview_urls = false` in the Wrangler config when it says otherwise, since `on = false` alone leaves the links public. The owner merges it (a protected path), and the path ends with the "No previews" line, naming it.
- **An open pull request of this path** (from `workflow/try-it-links`, `workflow/no-live-site` or `workflow/no-previews`, or any open pull request changing `[previews]` in the profile or the Wrangler lines in the config): point at it rather than opening another, and pick up where it is: "Its own try-it link" for the first, "Before step 2" for the second, the "No previews" line for the third.
- **The level:** `WF status --json` gives `experience.wording_level` (`new` or `developer`; `new` when unknown). It changes only the words: both levels get the same steps, the same pull request and the same link.

## The opening choice

One choice:

- *New to building*: "Add try-it links: each pull request then gets a link that opens a working copy of the change, so you can try it before you merge it. It takes a free Cloudflare account and a few minutes of clicks, which I guide one at a time." With sensitive data, add: "Your project has sensitive data, so the links go behind Cloudflare Access, which may ask for a payment method." Then **Do it now** (recommended) and **Not now**.
- *A developer*: the seven steps, a line each (Access among them with sensitive data), and what the pull request changes (the profile's `[previews]` section, and whichever Wrangler lines are missing), with the same **Do it now** (recommended) and **Not now**.

Both get the same steps. **Not now** ends it: nothing is changed. When `check-setup` hands the offer over, the person has just chosen: skip this choice, but with sensitive data still say its Access sentence before screen 1, since doctor's note doesn't.

## What's done already

Before screen 1, read what can be read, so a step already done is shown as done, with **Continue**, instead of its clicks:

- **Connected:** Cloudflare's app (`cloudflare-workers-and-pages`) already reports on this repository: a check run named "Workers Builds: …" from it on the base branch's latest commit (`gh api --paginate --slurp 'repos/<repo>/commits/<base>/check-runs?per_page=100' > .workflow/check-runs.json`, as the automatic path reads them) or on an open pull request's head, or its bot's comment on an open pull request. The GitHub MCP tools read a pull request's head check runs and its comments, but have no list of a commit's check runs. Then screens 1 and 2 are done.
- **Built:** an open pull request's link reads `built` (`WF preview`, as "Its own try-it link" reads it). Then screens 1 to 5 are done: the Build command, the token and Preview URLs work. With sensitive data and no Access confirmed yet, that link is public right now: say so plainly. "Before step 2" still comes first when the base branch's config needs it, then screen 5 again when Preview URLs were turned off for it, and screen 7.
- **The Wrangler config,** read from the checkout: which of the Wrangler lines it has already, for screen 6.

A step shown as done gets one line ("Screen 2, connecting the repository: done, since Cloudflare already reports on it.") with **Continue**, and "Something's different" for a person who knows otherwise. A step that can't be read from here gets its screen, and a person who did it already says "Done". Screen 7 is never shown as done: with sensitive data it is always asked, since only the owner's answer today counts. An `access = true` already in the profile only changes its words ("You said before that Access guards the links: is it still on?").

## Before step 2: no live site first

The page's "Before step 2". Connecting the repository makes Cloudflare deploy the base branch at once, and each deploy sets the Worker's public address and its preview links from the base branch's Wrangler config. So the config on the base branch must say `workers_dev = false`, and, for a project with sensitive data, `preview_urls = false` until screen 7 is confirmed. Read it before screen 2, whether or not the repository is connected:

- When it says so, go on.
- When it doesn't, and the repository isn't connected yet: a small pull request first, before screen 2. When it is connected already: say plainly that the app's own address is live on the internet now (`workers_dev` isn't `false`), or that its preview links are public now (sensitive data and `preview_urls` isn't `false`), and the same small pull request comes first, before any other screen. With sensitive data, the person first turns **Preview URLs** off in the dashboard (screen 5's setting), since pushing the small pull request's branch builds one more preview, public while they are on. Screen 5 is then no longer done: it is asked again after the small pull request merges, just before screen 7.
- **The small pull request,** fresh from the base branch (such as `workflow/no-live-site`): the page's "do step 6 first, with those values", so the Wrangler lines, with `preview_urls = false` in place of `true` for a project with sensitive data, placed and changed as the proof pull request's step 3 says. Say what it does in plain words: it keeps the app off the internet (and, with sensitive data, its preview links too). The person merges it (merging it deploys the base branch): wait for "Merged", then read the base branch's config again. When they won't merge it now, stop there, with its line in "Where try-it links end".
- A config with `routes` or a custom domain already has a live site: say so plainly, and that connecting deploys the base branch to it. Offer **Go on** and **Not now**. This path never removes a route.

## The steps

One screen at a time, with `AskUserQuestion`, in the page's order (`#the-steps`), each with the link it needs, worded for the person's level: *new to building*, plain sentences and the page's step to read; *a developer*, the setting's name and where it is. After each, wait for "Done" (or "Something's different", then help with what they see). A step already done is shown as done (above). Each screen has **Not now** too: it stops the path where it is, and asking again later reads what's done and picks it up there.

With sensitive data, screen 7 comes straight after screen 5, before any pull request is pushed: until Access is on, each preview is public. Without sensitive data, screen 7 is left out.

**Screen 1: a Cloudflare account.** Sign up at `https://dash.cloudflare.com/sign-up`. The free plan is enough.

**Screen 2: connect the repository through Cloudflare's GitHub app.** In Cloudflare, **Workers & Pages**: create an application, and import a repository from GitHub. When GitHub asks where to install Cloudflare's app, choose **Only select repositories** and pick this repository alone, so Cloudflare sees nothing else.

**Screen 3: an empty Build command.** In the Worker's **Settings**, under **Build**, clear the **Build command** box in the build settings for **Production** and for **Previews Base**, and save both. A new project puts `npx wrangler deploy` there, which makes each preview try to deploy the live site instead, and fail. Each branch copies "Previews Base" when it is first built ("A fresh branch", below).

**Screen 4: a new build token.** Where the build settings ask for an API token, choose **Create new token**. An old or reused token fails with "Configured API token unavailable". The token stays in Cloudflare: never ask for it, and if the person pastes it here, say to delete that token and make a new one.

**Screen 5: Preview URLs on.** They are off by default: in the Worker's **Settings**, under **Domains & Routes**, enable **Preview URLs**. While they are off, builds run but no link arrives.

**Screen 6: the Wrangler config, and no live site.** Nothing to click: the kit adds the Wrangler lines that are missing in the proof pull request, reading the config. Say which it will add or change, and why each (from "The Wrangler lines", above). Then **Continue**.

**Screen 7: Cloudflare Access, for sensitive data.** A preview link is public: anyone with it can open it. In the Worker's **Domains & Routes**, the **Preview URLs** row says "Anyone with this URL can visit", beside an **Enable Access** link: click it, and allow only the people who should see previews, such as the owner's own email address. Cloudflare may ask for a payment method, even on its free plan. Then, on the same screen and in plain words for both levels: "The kit can't check Access itself: it relies on your word, which the pull request records as `access = true` in the profile." The choices are **Access is on**, **I can't turn it on** and **Not now**:
- **Access is on** is the owner's confirmation: go on to the proof pull request, with `access = true`. Only their answer counts: never assume it from a screen they didn't confirm.
- **I can't turn it on:** this project gets no previews: the path stops, and opens no proof pull request. What keeps the links off: turn **Preview URLs** off in the dashboard (screen 5) first, since Cloudflare makes a public link for each branch while they are on; then the Wrangler config keeps `preview_urls = false`. When it doesn't say so, open the small pull request of "Before step 2" for it, as the page says.

## The proof pull request

Once the steps are done (and, with sensitive data, screen 7 confirmed): one pull request that turns previews on and carries the Wrangler lines still missing.

1. A branch fresh from the base branch, such as `workflow/try-it-links`, made only now, after screen 3: a branch copies "Previews Base" when it is first built, so one made earlier could keep the old Build command.
2. In `.claude/workflow/profile.toml`, a `[previews]` table, in place of the template's commented `# [previews]` lines (the comment line above them stays), or at the end of the file when they aren't there:

   ```toml
   [previews]
   provider = "cloudflare"
   on = true
   access = true
   ```

   The `access = true` line only when screen 7 was confirmed; without sensitive data, leave it out. When the profile has a `[previews]` section already, change its lines in place: never a second `[previews]` table. Change nothing else in the profile.
3. In the Wrangler config, whichever of the Wrangler lines is missing, a line saying otherwise changed rather than a second one added (`workers_dev = true` becomes `false`, `preview_urls = false` becomes `true`), placed as the page's step 6 says: the two settings near the top, above its first line that starts with `[`, and `[previews]` at its end, since a setting below a line in square brackets belongs to that block. Only the top-level settings count: a `workers_dev` under an `[env.…]` table is another environment's. In a JSON config, say that doctor's `previews.setup` line is `cant_check` once this merges, since doctor reads only a `wrangler.toml`. Change nothing else.
4. `WF profile check` passes. It refuses `on = true` without `access = true` in a profile with `[sensitive]` patterns, so a project with sensitive data never gets here without screen 7.
5. Push the branch and open the pull request. Its body: what it turns on, which steps were done (and which were done already), and, with sensitive data, that the owner confirmed Cloudflare Access guards the preview links, which the kit can't check. No email address, token or other detail from Cloudflare's screens goes in it.

The profile is a protected path, so merging it is the owner's. Never merge it, or enable auto-merge on it, yourself. Its own link works before it merges; once it merges, every session knows previews are on.

## Its own try-it link

Read the proof pull request's own preview with the kit's reader: `WF preview --fetch <n> --json` where `gh api` is signed in, or else `WF preview --comments F --checks F --sha <head> --json`, given the pull request's issue comments, its head commit's check runs and its head SHA, each as GitHub's JSON (the GitHub MCP tools give a pull request's comments and its head's check runs). First say that the first build can take about four minutes to start. The reader prints its `state`, `url` and `commit`:

- **`built`**: report the link, its `url`: "#<n>'s try-it link: <url>. Open it to try this pull request's copy of your app." Then "Where try-it links end".
- **`building`**: still building, or not started yet. Wait a minute or two and read it again, for up to about ten minutes; then say it is still building, and offer **Check again** and **Not now**.
- **`failed`**: the build's log is behind a Cloudflare sign-in, so ask the person to open it (**View logs** in Cloudflare's comment on the pull request, or the check's **Details**) and say or paste its error line. Then say the failure in plain words with its fix, from the page's **When a build fails** (`#when-a-build-fails`). A Build command that isn't empty is "A fresh branch", below. A fix in the code goes on the proof pull request's branch.
- **`none`**: with no `commit`, Cloudflare hasn't reported on the pull request yet: read it again as for `building`, and after about ten minutes say the repository may not be connected (screen 2). With a `commit`, Cloudflare built nothing to try for it: its build was skipped, or Preview URLs are off (screen 5). That build is done, so once Preview URLs are on, push a new commit to the proof pull request's branch (a comment line in the Wrangler config will do) and read it again.
- **Exit 1 or 2** (an input couldn't be read, or is missing): say what the reader printed, and read it again once. When the check runs or comments still can't be read from here, say so, and ask the person to look at the pull request on GitHub for Cloudflare's comment and its **Branch Preview URL**.

## A fresh branch

The page's trap: "Previews Base" is copied when a branch is first built, and the branch keeps its copy. So when a preview still runs the old Build command after screen 3 (its log says the name in the Wrangler config "must match the name of your Worker", though the names match), push a fresh branch rather than retry: a retried build, or a new commit on the same branch, runs the old command again. First check screen 3 is done (the box empty on **Previews Base**). Then make a new branch from the proof pull request's head (such as `workflow/try-it-links-2`), push it, open a new pull request from it with the same body, and close the old one with a comment naming the new one. Read the new pull request's link as above.

## Where try-it links end

Say where it stands in one line:
- "Try-it links work: #<n>'s is <url>. Merge #<n> when you're ready, and every pull request gets one.";
- "#<n> is open, and its try-it link is still building: ask me to check it again.";
- "#<n>'s try-it link didn't build: <the fix>.";
- "#<n> built nothing to try: turn Preview URLs on (screen 5), and I'll push a new commit to build it again.";
- "No previews: this project has sensitive data, and Cloudflare Access isn't on." (adding "#<n> keeps the preview links off: merge it when you're ready." when the small pull request of "Before step 2", or the refused profile's `on = false` one, was opened);
- "Merge #<n> first: it keeps your app off the internet. Then ask me to add try-it links again." after the small pull request of "Before step 2";
- "Nothing was changed." after **Not now** at the opening choice, or "Stopped before screen <n>: ask me to add try-it links again to go on." after **Not now** later;
- "Try-it links need an app that runs on Cloudflare Workers: this project has no Wrangler config."
