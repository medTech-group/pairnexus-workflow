---
name: check-setup
description: Check the set-up - gather what only a Claude session can see (the rulesets and repository settings through the GitHub tools, the cloud environments, the workflow:run issues, Claude Code's version), hand it to `workflow doctor --json` as files, show the report worded by the person's experience with the most serious first, and offer each upgrade it names as a choice with "Not now". Changes nothing itself. Use when the person asks to "check the set-up" (or "check the workflow set-up", "is my project set up properly?"), or picks it where the guided start offers it.
---

# Check the set-up

One report of what's set up and what isn't, each line with its fix: `workflow doctor`'s, with what only a Claude session can see handed to it as files. This skill is named `check-setup`, not `doctor`, because Claude Code already has `/doctor`.

**It changes nothing itself.** It reads, runs doctor (which never changes anything either), shows the report and offers the upgrades the report names. An upgrade the person picks is the `upgrade-setup` skill's to make, with its own confirmations.

## Where things are

**The CLI.** `WF` is:
- `python3 -B .claude/workflow/bin/workflow.py` (vendored);
- or `python3 -B <this skill's directory>/../../scripts/workflow.py` (plugin).

**The repository** (`<repo>`, `owner/name`) is the profile's `project.repo`. Write it out in full in every command: no shell variables in a `gh api` route.

**Cloud or local.** A cloud session has `CLAUDE_CODE_REMOTE` set to `true`. Anything else is a local session.

**Only in attended sessions.** In a ticket or conductor session (`WORKFLOW_ROLE` set to anything but `attended`) don't run it: there's nobody to answer its offers, and the conductor's pre-flight runs doctor itself.

## 1. Gather, then run doctor

### In a cloud session

Only a cloud session can list the account's environments, so this is where the report is complete. Make a new directory outside the checkout for the files, with `mktemp -d`, and write its path out in full in each command after (below, `<dir>`). Nothing goes into the checkout.

Gather:
- **The rulesets, each in full:** list them with `gh api --paginate 'repos/<repo>/rulesets?includes_parents=true&per_page=100'`, then fetch each one by its id (`gh api repos/<repo>/rulesets/<id>`), and save the full rulesets (not the list's summaries) as one JSON list in `<dir>/rulesets.json`. When GitHub refuses the list because rulesets need a paid plan (a private repository on GitHub Free: "Upgrade to GitHub Pro or make this repository public"), save `[]` and say so beside the report: no ruleset can protect the base branch on that plan.
- **The repository's settings:** `gh api repos/<repo> > <dir>/repo.json`.
- **The environments:** `list_environments`, every page until `has_more` is false, saved as one JSON list of its pages in `<dir>/environments.json`.
- **The runs:** the issues labelled `workflow:run`, open and closed: `gh api 'repos/<repo>/issues?labels=workflow:run&state=all&per_page=100' > <dir>/run-issues.json`, or the GitHub MCP tools (`list_issues` with that label, every state), all pages in one JSON list.
- **Claude Code's version:** `claude --version`, as it prints it.

Use `gh api` where it works in this session; else the GitHub MCP tools, where one returns GitHub's own JSON for it. Doctor reads GitHub's JSON as it is, so a file you can't fill with GitHub's own answer (no tool here gives it, or the fetch failed twice) is not written: leave its flag out, and doctor says that line can't be checked, with how to check it. Never write a file you made up or pieced together from summaries. A failed `gh api` saves GitHub's error body (`{"message": "Not Found", …}`) into the file: fetch it again once, and leave the flag out if it fails again.

Then run doctor once, with every file you have:

```bash
WF doctor --json --rulesets <dir>/rulesets.json --repo <dir>/repo.json --environments <dir>/environments.json --runs <dir>/run-issues.json --claude-version "<what claude --version printed>"
```

### In a local session

Doctor reads the rulesets, the repository's settings and the runs with `gh` itself, where `gh` is installed and signed in, and Claude Code's version with `claude --version`. So run it as it is:

```bash
WF doctor --json
```

Without `gh` signed in, its GitHub lines say they can't be checked from here and how to check them. The environments can only be checked from a cloud session: say so beside the report, once ("To check the two cloud environments, ask a cloud session on this repository to check the set-up."). That line is `cant_check` here, never fine.

### When doctor doesn't give its JSON

- **Exit code 2:** the command was wrong (a flag, a file it can't read). Fix it and run it again.
- **An old `python3`** (older than Python 3.11) still gets doctor's JSON, as its short report: `python3`'s version as a gap with its fix (`computer.python3`), and every other line `cant_check` until `python3` is 3.11 or newer. Show it like any report: the fix to `python3` comes first, and nothing else is fine yet. If the kit stops instead with "workflow needs Python 3.11", run `WF doctor` without `--json` for the same short report as text.
- **Anything else** (a traceback, another exit code): run it again once. If it still fails, say the set-up couldn't be checked, with the error's last line. That is never a clean report.

## 2. Show the report

Doctor's JSON has `wording` (`new` or `developer`, the person's level as the kit resolves it), `counts`, and `lines`, each with a `group`, an `id`, a `status`, a `message`, a `fix` and an `offer`. The messages and fixes are already worded for the person: show them as they are, and word what you add around them for `wording`:
- *new to building*: plain sentences, one line per problem with its fix, no ids, no jargon;
- *developer*: short; the line's `id` beside each problem.

Doctor's `lines` are already in order, the most serious first: keep that order.
1. **`gap`** lines first: each with its message and its fix.
2. **`cant_check`** lines next: each with its message and how to check it (its fix).
3. **`note`** lines: a state chosen on purpose (solo mode, unattended runs not set up yet, checks not required yet), with its fix when it has one. A note is never a problem.
4. **`fine`** lines last, counted in one line by group ("Fine: 13 lines, in Your computer, The kit and GitHub"), unless the person asks to see them.

Open with one line from `counts`: "2 problems to fix, 1 line I couldn't check, 3 notes." **Never say "fine"** (or "all set", "everything is in order") about the set-up while any line is `cant_check`: say what was checked is fine and name what couldn't be checked. Only with no `gap` and no `cant_check` is the set-up fine.

Beside the report, say once: what an environment holds can't be read by anything (`cloud.contents`), so the person confirms the ticket environment has no secrets. In a local session, the line that the environments need a cloud session.

## 3. The offers

Each line with an `offer` is an upgrade one tap away. Offer each one the report names as a choice with `AskUserQuestion`, once, after the report: the question names the line's problem in a few words, and the options are the upgrade (recommended) and **Not now**. Up to 4 questions in one call; an offer two lines share is asked once. Without the tool (a headless session), ask the same choices as a numbered list.

| `offer` | The choice | On yes |
|---|---|---|
| `protect_main` | **Protect `main`** (the profile's base branch by name) | Load the `upgrade-setup` skill with the Skill tool, for "Protect `main`" (its offer `protect_main`) |
| `restore_protection` | **Restore protection** | Load `upgrade-setup` for "Protect `main`" with the offer `restore_protection`: the same path, without the pull request that leaves solo mode |
| `set_up_unattended_runs` | **Set up unattended runs** | Load `upgrade-setup` for "Set up unattended runs" (its offer `set_up_unattended_runs`) |

**Not now** ends that offer for now: nothing is changed, and the next check still names it.

**Any other offer** doctor names that isn't in the table (a later kit adds them) is named as text, not offered as a choice: "Doctor also suggests `<offer>`: <the line's fix>." Never start an upgrade this skill doesn't know.

A line without an offer has only its fix: say it, and do it only if the person asks, as a separate request.

After the offers (or when there are none), the check is done. When the person fixes something, offer to check the set-up again.
