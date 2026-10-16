---
name: upgrade-setup
description: Move a project from solo mode to the full set-up, one upgrade at a time. Its first path, "Protect `main`", guides the person click by click to a ruleset and the merge settings on the base branch, reads them back with `workflow protection`, and opens the pull request that leaves solo mode. Use when the person asks to protect main, or picks "Protect `main`" where the kit offers it.
---

# Upgrade the set-up

A project set up in solo mode (`project.ruleset = false`) works attended from the start, with the kit's guard refusing what touches the base branch. This skill takes it the rest of the way, one upgrade at a time, each one offered and never pushed:

- **"Protect `main`"**: a ruleset on the base branch and the merge settings, then a pull request that sets `ruleset = true`. This file is that path.
- **"Set up unattended runs"** (offer `set_up_unattended_runs`): the two cloud environments and the questions only runs need. It comes in a later release; until then, say it isn't here yet and point at the README's Step 5.

Below, `main` stands for the profile's `project.base_branch`: use its real name in everything you show.

## Where things are

**The CLI.** `WF` is:
- `python3 -B .claude/workflow/bin/workflow.py` (vendored);
- or `python3 -B <this skill's directory>/../../scripts/workflow.py` (plugin).

**The repository** (`<repo>`, `owner/name`) is the profile's `project.repo`; the base branch is `project.base_branch`.

**GitHub.** Read with `gh api` where it is signed in, or the GitHub MCP tools in a cloud session. Neither path writes a ruleset or a setting here: the person clicks, and this skill reads back. An automatic path with `gh` comes in a later release (below).

The read-back needs GitHub's own JSON: the repository (`GET repos/<repo>`, with `permissions`, `default_branch` and the merge settings) and each ruleset by its id. Use a tool that returns those responses as they are, `gh api` where it is signed in. When no tool here gives them, treat the rulesets as unreadable (step 2).

**Choices** use the `AskUserQuestion` tool, the recommended option first; without it (a headless session), the same choices as a numbered list.

**Only in attended sessions.** When `WORKFLOW_ROLE` is `ticket`, don't run it or offer it: there's nobody to click. Say in the ticket's report that the base branch isn't protected, and carry on. The conductor runs it only at its kick-off, with the owner there.

## When it's offered

Offered, never as a nag, at these moments only. Each comes with "Not now", and "Not now" ends it for that moment:
- when the person asks ("protect main", "set up the ruleset");
- in the guard's solo-mode refusal, once it offers "Protect `main`";
- before an unattended run in solo mode, once the conductor's pre-flight offers it;
- by `workflow doctor`, once it exists, when it finds the base branch unprotected.

The offers have names, which `workflow doctor` and the other skills use:
- **`protect_main`**: the project is in solo mode (`ruleset = false`), or set up before solo mode existed (`ruleset` left out, `solo_mode` `null`). The path ends with the pull request that leaves solo mode.
- **`restore_protection`**: the profile says `ruleset = true` but the read-back says the base branch isn't protected (the protection was removed or weakened). The same path, without the pull request that leaves solo mode: the profile is already right.

## The screens

Read the person's level and the mode first: `WF status --json` gives `experience.wording_level` (`new` or `developer`; `new` when unknown) and `solo_mode`. The level changes only the words. Both levels get the same steps, the same clicks and the same read-back, and end with the same protection.

**New to building** gets one plain screen, as a choice:

> Protect your main branch: GitHub will then refuse changes that skip a pull request or a failing test.

with **Do it now** (recommended) and **Not now**. Each later step is one short screen in the same plain words, and the end is a one-line result ("`main` is protected." or "`main` isn't protected yet: <the first thing missing>"). When no checks are required yet, the result says so too, since the plain screen promised it: "`main` is protected. Failing tests don't block a merge yet: that comes once CI has run."

**A developer** gets the ruleset's settings listed (from step 3), with the same **Do it now** and **Not now**, and the read-back's report as it is at the end.

## 1. Admin first

Before anything else, read the repository's permissions: `GET repos/<repo>` (`gh api repos/<repo>`, or the GitHub MCP tools), and look at `permissions.admin`. Keep that JSON: the read-back uses it as `--repo`.

- **An admin** (`true`): go on to step 2.
- **Not an admin** (`false`): say plainly that only an admin can do this, since rulesets and the merge settings are under the repository's Settings, which only admins see. Then hand over a ready message for the owner, in a code block they can copy:
  - what it's for, in one line;
  - the links and the clicks of step 3, filled in with the repository's name and base branch;
  - "Tell me once it's done, and I'll read it back."

  That is the end of this run of the skill: it never stops halfway, with a ruleset half made or a pull request waiting on clicks nobody can make. When the person says the owner has done it, start again at step 2.
- **Can't tell** (no `permissions` in the answer, or the request failed): say so, and offer both: "I'm an admin: go on" and "Give me the message for the owner".

## 2. Read what is there

Before guiding any click, fetch the rulesets and read them back with `WF protection`, exactly as step 4 does. A repository may already have one.

- **Already protected** (`protected` is `true`): no clicks for the ruleset. If the merge settings are missing, guide only those first (step 3's screen 3), since they are part of this upgrade too. Then, for `protect_main`, go straight to the pull request that leaves solo mode (step 5); for `restore_protection`, say it is protected again and stop.
- **Not protected, with rulesets there:** show what is missing. This skill never edits an existing ruleset, and never guides a change to one: changing a ruleset that was there before is left to a later release. It guides a new ruleset beside them. Note which rulesets were there before this run: step 4 needs to know.
  - When an existing one stops the verdict whatever is added (its bypass list, or a bypass list that can't be read), say which ruleset and what in it, and that it is its admin's to change. Don't guide a new ruleset that can't help.
  - An organisation's ruleset (`source_type` `Organization`) is the organisation owner's, even for a repository admin: hand over the message for the owner (step 1), naming that ruleset and what in it.
- **No rulesets:** go on to step 3.
- **Can't read the rulesets** (no access from here): say so. Guide the clicks anyway, but without a read-back there is no pull request that leaves solo mode: an unknown counts as unprotected.

## 3. The guided clicks

One screen at a time, each with a link to the exact settings page, in every kind of session. After each screen, wait for "Done" (or "Something's different", then help with what they see).

**Screen 1: the ruleset.** Open `https://github.com/<repo>/settings/rules/new?target=branch` (**Settings → Rules → Rulesets → New ruleset → New branch ruleset**) and fill it in:
- **Ruleset name:** anything, for example `main`.
- **Enforcement status:** **Active**. "Disabled" and "Evaluate" enforce nothing.
- **Bypass list:** leave it empty. Sessions act through the person's GitHub account, so anything they can bypass, a session could too.
- **Target branches:** **Add target → Include default branch** (the default branch). If the base branch isn't the default branch, add it by name instead.
- **Rules**, tick:
  - **Restrict deletions**;
  - **Block force pushes**;
  - **Require a pull request before merging**, with **Required approvals: 0** and **Require review from Code Owners** left unticked (GitHub never lets an author approve their own pull request, and sessions post as the person).
- Leave **Require linear history** unticked: the kit merges with a merge commit, which it forbids.

**Screen 2: the required checks.** Only when CI has already run on the base branch and the profile lists its checks (`ci.required_checks`): check that each name appears in the base branch's latest check runs (`GET repos/<repo>/commits/<base>/check-runs?per_page=100`, every page). If they all do, add to the same ruleset before creating it: **Require status checks to pass**, **Require branches to be up to date before merging**, and **Add checks** with each name exactly. Otherwise skip this screen and report "checks not required yet": the ruleset protects the base branch without them, and they are added once CI has run and their names are known. Adding them later, and the automatic path with `gh`, come in a later release; leave the ruleset as it is for that.

Then click **Create**.

**Screen 3: the merge settings.** Open `https://github.com/<repo>/settings` (**Settings → General**) and scroll to **Pull Requests**:
- keep **Allow merge commits** ticked: sessions and the conductor always merge with a merge commit;
- tick **Allow auto-merge**.

## 4. Read it back

Fetch, then hand the files to `WF protection`. Write them under `.workflow/`, which git ignores:

1. The rulesets, **each in full**: list the ids with `GET repos/<repo>/rulesets?includes_parents=true` (every page), then fetch each one by its id with `GET repos/<repo>/rulesets/<id>`, through the repository even for an organisation's ruleset. Put them in one JSON list in `.workflow/rulesets.json`. The list endpoint alone gives summaries without their rules, which the command refuses.
2. The repository's settings: `GET repos/<repo>` again (the merge settings may have changed), in `.workflow/repo.json`.
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
2. In `.claude/workflow/profile.toml`'s `[project]` table, a plain `ruleset = true` line on its own: in place of a `ruleset = false` line, or of the template's commented `# ruleset = false`, or after `base_branch` when neither is there. Change nothing else.
3. `WF profile check` passes, and `WF status --json` gives `solo_mode: false` on the branch.
4. Push the branch and open the pull request. Its body: what the read-back found (the report, "checks not required yet" if so), and that merging it takes the project out of solo mode.

Tell the person: the guard stays in solo mode until it merges, so until then the kit is only stricter, never looser. Merging it is the owner's: never merge it, or enable auto-merge on it, yourself.

## The end

Say where it stands in one line:
- "`main` is protected, and the pull request that leaves solo mode is #<n>: merge it when you're ready.";
- "`main` is protected again." (`restore_protection`);
- "`main` isn't protected yet: <what's missing>." with the choice to try that screen again;
- or, not an admin, "The message for the owner is above."
