---
name: check-setup
description: Check the set-up - gather what only a Claude session can see (the rulesets and repository settings through the GitHub tools, the base branch's latest check runs and statuses, the open pull requests, the base's recent commits and their CI, the cloud environments, the workflow:run issues, Claude Code's version), hand it to `workflow doctor --json` as files, show the report worded by the person's experience with the most serious first, and offer each upgrade it names as a choice with "Not now". Changes nothing itself. Use when the person asks to "check the set-up" (or "check the workflow set-up", "is my project set up properly?"), or picks it where the guided start offers it.
---

# Check the set-up

One report of what's set up and what isn't, each line with its fix: `workflow doctor`'s, with what only a Claude session can see handed to it as files. This skill is named `check-setup`, not `doctor`, because Claude Code already has `/doctor`.

**It changes nothing itself.** It reads, runs doctor (which never changes anything either), shows the report and offers the upgrades the report names. An upgrade the person picks is the `upgrade-setup` skill's to make, with its own confirmations.

## Where things are

**The CLI.** `WF` is:
- `python3 -B .claude/workflow/bin/workflow.py` (vendored);
- or `python3 -B <this skill's directory>/../../scripts/workflow.py` (plugin).

**The repository** (`<repo>`, `owner/name`) is the profile's `project.repo`. Write it out in full in every command: no shell variables in a `gh api` route. With no profile to read it from (`WF status --json` says `set_up` false, or `profile_error` true), gather nothing: run `WF doctor --json` as it is. Its `kit.profile` line comes first and says what to fix.

**Cloud or local.** A cloud session has `CLAUDE_CODE_REMOTE` set to `true`. Anything else is a local session.

**Only in attended sessions.** In a ticket or conductor session (`WORKFLOW_ROLE` set to anything but `attended`, or a branch named like the profile's `run.ticket_branch`) don't run it: there's nobody to answer its offers, and the conductor's pre-flight runs doctor itself. That reading holds with `code_writers` absent or `"any"` (`WF status --json`'s `code_writers` is `null` or `"any"`). Under `code_writers = "ticket"`, a session that would be a ticket session only by its branch, or by a `WORKFLOW_ROLE` that isn't a role, is a planning session, an attended one: run it there.

## 1. Gather, then run doctor

### In a cloud session

Only a cloud session can list the account's environments, so this is where the report is complete. Make a new directory outside the checkout for the files, with `mktemp -d`, and write its path out in full in each command after (below, `<dir>`). Nothing goes into the checkout.

Gather:
- **The rulesets, each in full:** list them with `gh api --paginate 'repos/<repo>/rulesets?includes_parents=true&per_page=100'`, then fetch each one by its id (`gh api repos/<repo>/rulesets/<id>`), and save the full rulesets (not the list's summaries) as one JSON list in `<dir>/rulesets.json`. When GitHub refuses the list because rulesets need a paid plan (a private repository on GitHub Free: "Upgrade to GitHub Pro or make this repository public"), leave `--rulesets` out instead of saving a file: doctor then reads the list with `gh` itself, sees the refusal, and words its ruleset line and fix for it (a paid plan, or a public repository). A file can't carry that refusal.
- **The repository's settings:** `gh api repos/<repo> > <dir>/repo.json`.
- **The environments:** `list_environments`, every page until `has_more` is false, saved as one JSON list of its pages in `<dir>/environments.json`.
- **The runs:** the issues labelled `workflow:run`, open and closed: `gh api 'repos/<repo>/issues?labels=workflow:run&state=all&per_page=100' > <dir>/run-issues.json`, or the GitHub MCP tools (`list_issues` with that label, every state). One page is enough: doctor only asks whether a run has been made.
- **The checks that ran on the base branch** (the profile's `project.base_branch`, `<base>` below, percent-encoded in a route except for its `/`, as doctor does), for doctor's "Require these checks" offer: its latest commit's check runs and statuses, every page, in one file.
  1. `gh api --paginate --slurp 'repos/<repo>/commits/<base>/status?per_page=100' > <dir>/status.json`. It is a list of pages, and the first page's `sha` is the commit: `python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))[0]["sha"])' <dir>/status.json`. Write it out in full in the next command (`<sha>`), so both reads are of the same commit even if `<base>` moves in between.
  2. `gh api --paginate --slurp 'repos/<repo>/commits/<sha>/check-runs?per_page=100' > <dir>/check-runs.json`.
  3. Put the two side by side in one JSON list, as doctor's `--checks` takes them:

     ```bash
     python3 -c 'import json, sys; json.dump([json.load(open(f)) for f in sys.argv[1:]], sys.stdout)' <dir>/check-runs.json <dir>/status.json > <dir>/checks.json
     ```

  The GitHub MCP tools have no list of a commit's check runs, so without `gh api` here, leave `--checks` out.

  **Look at `checks.json` before you pass it: a wrong one is silent.** Doctor then makes no offer, and no line says why. Check that:
  - it holds GitHub's own pages, never an error body (`{"message": …}`, alone or inside a page list);
  - each check run keeps its `app` with its `slug` (without it doctor can't tell the try-it link's check apart, and reads nothing);
  - the check runs across the pages, and the statuses across theirs, each add up to their `total_count` (fewer read as unreadable);
  - the status's `sha` is the commit the check runs were fetched for (each run's `head_sha`).

  Each command above must exit 0: a failed `gh api` still writes GitHub's error body into its file, and a failed command still leaves the file its redirect made. If one fails, or `checks.json` fails one of these checks, run the steps again once from step 1; if that fails too, leave `--checks` out.
- **The open pull requests,** for doctor's note on a pull request that adds GitHub's required checks to the profile: `gh api --paginate --slurp 'repos/<repo>/pulls?state=open&per_page=100' > <dir>/prs.json`, or the GitHub MCP tools' `list_pull_requests` with `state` open, every page, with every field (no `fields` subset), saved as one JSON list of its pages. Each pull request is in full, with its `body` and its `head.repo`: a marked pull request counts only when it comes from this repository, and one without `head.repo` counts by its body alone. Never a minimal or summarised list.
- **Claude Code's version:** `claude --version`, as it prints it.
- **For the merge queue** (doctor's suggestion, `github.merge_queue`, and its `merge_group` check; doctor reads these only where they matter):
  - `git fetch origin <base>` first: doctor reads the workflow files with `git` as they are on `origin/<base>`, never the checkout's.
  - **The organisation,** when `repo.json`'s `owner.type` is `Organization`: `gh api orgs/<owner> > <dir>/org.json` (GET `orgs/<owner>`). Its `plan` shows only to the organisation's owners; without it, doctor's suggestion for a private repository says to check the plan first.
  - **The base's commits:** `gh api 'repos/<repo>/commits?sha=<base>&per_page=100' > <dir>/commits.json`, one page, for how often `<base>` moved in the last 7 days.
  - **The CI** of the base's last 5 commits (the newest in `commits.json`, then each one's first parent) and of up to 5 open pull requests' heads (`head.sha` in `prs.json`). For each `<sha>`:
    - `gh api 'repos/<repo>/commits/<sha>/check-runs?per_page=100' > <dir>/runs-<sha>.json`;
    - `gh api 'repos/<repo>/actions/runs?head_sha=<sha>&per_page=100' > <dir>/flows-<sha>.json`, for the workflow file behind each check run.

    Then put them together as doctor's `--ci` takes them, naming each commit `base:<sha>` or `pr:<sha>`:

    ```bash
    python3 -c 'import json, sys; d = sys.argv[1]; json.dump([{"sha": s, "base": k == "base", "check_runs": json.load(open(f"{d}/runs-{s}.json")), "workflow_runs": json.load(open(f"{d}/flows-{s}.json"))} for k, s in (a.split(":") for a in sys.argv[2:])], sys.stdout)' <dir> base:<sha> pr:<sha> > <dir>/ci.json
    ```

  Each read is one page, never `--paginate`. Without `gh api` here, leave `--org`, `--commits` and `--ci` out: doctor reads them with `gh` itself where it can. Doctor counts the 7 days to now; `--now <time>` (as `2026-10-25T12:00:00Z`) is only for another end.

Use `gh api` where it works in this session; else the GitHub MCP tools, where one returns GitHub's own JSON for it. Doctor reads GitHub's JSON as it is, so a file you can't fill with GitHub's own answer (no tool here gives it, or the fetch failed twice) is not written: leave its flag out. Doctor then reads it with `gh` itself where it can, else says that line can't be checked, with how to check it (the runs are the exception: see "When something goes wrong"). Never write a file you made up or pieced together from summaries. A failed `gh api` saves GitHub's error body (`{"message": "Not Found", …}`) into the file: fetch it again once, and leave the flag out if it fails again.

Then run doctor once, with every file you have:

```bash
WF doctor --json --rulesets <dir>/rulesets.json --repo <dir>/repo.json --environments <dir>/environments.json --runs <dir>/run-issues.json --checks <dir>/checks.json --prs <dir>/prs.json --org <dir>/org.json --commits <dir>/commits.json --ci <dir>/ci.json --claude-version "<what claude --version printed>"
```

Without `--checks`, doctor reads the checks with `gh` itself, where it can. When it can't, it makes no "Require these checks" offer and no line says so. Doctor makes the offer only when the report's `github.ruleset` line is `fine` (the base branch protected, not in solo mode). So when all of these hold:
- you left `--checks` out;
- `github.ruleset` is `fine`;
- `github.required_checks` has no `offer`;

say once beside the report:

> Which checks have run on `<base>` couldn't be read from this session, so if some aren't required yet, "Require these checks" can't be offered here. To see them, ask Claude to check the set-up again where GitHub's command-line tool (`gh`) is signed in.

Otherwise say nothing about it.

### In a local session

Doctor reads the rulesets, the repository's settings, the base branch's latest check runs and statuses, and the open pull requests with `gh` itself, where `gh` is installed and signed in, and Claude Code's version with `claude --version`. The merge queue's inputs too (the organisation, the base's commits and their CI); it reads the workflow files from `origin/<base>`, so run `git fetch origin <base>` first. Then run it as it is:

```bash
WF doctor --json
```

Without `gh` signed in, its GitHub lines say they can't be checked from here and how to check them. The environments can only be checked from a cloud session: say so beside the report, once ("To check the two cloud environments, ask a cloud session on this repository to check the set-up."). That line is `cant_check` here, never fine.

### When something goes wrong

- **Exit code 2:** the command was wrong (a flag doctor doesn't take, or `-` given for more than one file). Fix it and run it again.
- **A file doctor couldn't use** is not an exit code: it is a `cant_check` line, which names a missing or empty file, or says its answer isn't in the shape GitHub gives. `--checks` is the exception: doctor says nothing about a checks file it couldn't use, and the line it feeds can read `fine` without it. That is why you look at `checks.json` before running doctor. Doctor doesn't always see GitHub's error body for what it is (in `--repo`, `{"message": …}` reads as settings only an admin can see), so look at each file yourself before running doctor, as above. Fetch such a file again once and run doctor again; whatever its lines say after that is the report.
- **Runs that couldn't be read are the exception.** Doctor reads the runs only when neither environment is ready. Then, when the runs file can't be used, or was left out and doctor's own `gh` read failed, `cloud.environments` is a `note` (unattended runs not set up yet) whose message says whether a run has been made couldn't be read. Only when its message says so, fetch the runs file again once, where a tool here gives it, and run doctor again. If the message still says so, that line counts as a line that couldn't be checked, everywhere below: show it with the `cant_check` lines, count it with them in the opening line, and the set-up isn't fine while it is there. Whether it is a note or a gap isn't known.
- **An old `python3`** (older than Python 3.11) still gets doctor's JSON, as its short report: `python3`'s version as a gap with its fix (`computer.python3`), and every other line `cant_check` until `python3` is 3.11 or newer. Show it like any report: the fix to `python3` comes first, and nothing else is fine yet.
- **Anything else** (a traceback, another exit code): run it again once. If it still fails, say the set-up couldn't be checked, with the error's last line. That is never a clean report.

## 2. Show the report

Doctor's JSON has `wording` (`new` or `developer`, the person's level as the kit resolves it), `counts`, and `lines`, each with a `group`, an `id`, a `status`, a `message`, a `fix` and an `offer`. The messages and fixes are already worded for the person: show them as they are, and word what you add around them for `wording`:
- *new to building*: plain sentences, one line per problem with its fix, no ids, no jargon;
- *developer*: short; the line's `id` beside each problem.

When this session's level differs from `wording` (the person said "explain less" or "explain more" and it couldn't be recorded), word what you add for this session's level, and keep doctor's messages and fixes as they are. Don't set `WORKFLOW_EXPERIENCE` for the run: doctor would report it as the person's own setting, and its `kit.experience` line would change.

Doctor's `lines` come grouped (Your computer, The kit, GitHub, …), the group with the most serious line first. Show them by status instead, the most serious first, keeping doctor's order within each status (so removed protection, which doctor lists first, still comes first):
1. **`gap`** lines first: each with its message and its fix.
2. **`cant_check`** lines next: each with its message and how to check it (its fix).
3. **`note`** lines: a state chosen on purpose (solo mode, unattended runs not set up yet, checks not required yet), with its fix when it has one. A note is never a problem.
4. **`fine`** lines last, counted in one line by group ("Fine: 13 lines, in Your computer, The kit and GitHub"), unless the person asks to see them.

Open with one line from `counts`: "2 problems to fix, 1 line I couldn't check, 3 notes." **Never say "fine"** (or "all set", "everything is in order") about the set-up while any line is `cant_check`: say what was checked is fine and name what couldn't be checked. Only with no `gap`, no `cant_check` and no runs line that couldn't be read is the set-up fine.

**The note naming the open profile pull request.** When GitHub requires checks the profile doesn't list and an open pull request adds them, `github.profile_checks` is a `note` naming that pull request. Show it as doctor words it, its message and its fix, with the other notes, never as something to fix now: the profile catches up when that pull request merges. It carries no offer. Without such a pull request the same line is a `gap`, shown as any gap.

**The merge-queue suggestion.** `github.merge_queue`'s note is a suggestion, never a gap: show it with the notes, never among the problems, worded as section 3 says. `github.merge_group` beside it is the state of the workflows for that upgrade: a `note` while the queue is off (what it couldn't check among them, so `--strict` still passes), and a `gap` or `cant_check` only once the queue is on.

Show the `cloud.contents` note with the others, never summarised away: nothing can read what an environment holds, so the person confirms the ticket environment has no secrets. In a local session, add once the line that the environments need a cloud session.

## 3. The offers

Each line with an `offer` is an upgrade one tap away. Offer each one the report names as a choice with `AskUserQuestion`, once, after the report: the question names the line's problem in a few words, and the options are the upgrade and **Not now**. The upgrade is the recommended option only on a `gap` line: a `note` is a state chosen on purpose (solo mode, unattended runs not set up yet), so its upgrade is offered without "(Recommended)". After a paid-plan refusal, `protect_main` and `restore_protection` aren't recommended either: when the ruleset line says rulesets need a paid plan, say beside the choice that the upgrade needs a paid GitHub plan or a public repository. Up to 4 questions in one call; an offer two lines share is asked once. Without the tool (a headless session), ask the same choices as a numbered list.

| `offer` | The choice | On yes |
|---|---|---|
| `protect_main` | **Protect `main`** (the profile's base branch by name) | Load the `upgrade-setup` skill with the Skill tool, for "Protect `main`" (its offer `protect_main`), skipping its opening choice: the person has just chosen |
| `restore_protection` | **Restore protection** | Load `upgrade-setup` for "Protect `main`" with the offer `restore_protection`: the same path, without the pull request that leaves solo mode, and without its opening choice |
| `set_up_unattended_runs` | **Set up unattended runs** | Load `upgrade-setup` for "Set up unattended runs" (its offer `set_up_unattended_runs`), skipping its opening choice |
| `require_checks` | **Require these checks** | Load `upgrade-setup` for "Require these checks" (its offer `require_checks`), from its start: it has nothing to skip, and the person ticks the checks to require on its checks screen |
| `add_try_it_links` | **Add try-it links** (on the Previews line) | Load `upgrade-setup` for "Add try-it links" (its offer `add_try_it_links`), skipping its opening choice |
| `use_merge_queue` | **Use a merge queue** (on the `github.merge_queue` line) | Load `upgrade-setup` for "Use a merge queue" (its offer `use_merge_queue`), from its start |

**The merge queue: a recommendation with its reason.** `use_merge_queue` is the one note whose upgrade may be recommended. Read doctor's JSON `merge_queue`: its `available` and its `signals` (`ci_minutes.typical`, `base_commits_7d`, `runs_set_up`, `run_in_progress`). A signal that is `null` couldn't be read, and never counts towards it.
- **Recommend it** (the upgrade first, with "(Recommended)") when CI typically takes 10 minutes or more on `<base>` and either `<base>` moved 10 or more times in the 7 days or unattended runs are set up. Each merge then sends every other open pull request back through that CI, and the queue saves those runs.
- **Otherwise** offer it without "(Recommended)".
- **Never recommend it** when `available` is `check_plan`: say beside the choice that a private repository has the queue only on GitHub Enterprise Cloud, and to check the organisation's plan first.
- **Give the reason** beside the choice, in one sentence from the signals, either way. For example: "CI takes about 30 minutes and `main` moved 25 times this week, so each merge sends the other pull requests back through CI." Or: "CI takes about 3 minutes, so updating a pull request costs little; the queue can wait."
- **While a run is in progress** (`run_in_progress` true, or `null`: it can't be told), don't offer it: name it as text ("Doctor also suggests a merge queue: once the run has ended, ask Claude to \"Use a merge queue\"."). A run's merging mustn't change under it.

**Protecting comes first.** When the report offers `protect_main` or `restore_protection` as well as `require_checks`, ask the protecting one first, and on yes to both, finish "Protect `main`" before starting "Require these checks": checks are only added to a protected base branch. Today's doctor offers `require_checks` only once the base branch is protected, so it never offers both in one report; the order holds for any report that does.

**Not now** ends that offer for now: nothing is changed, and the next check still names it.

**Who writes code.** Doctor's `kit.code_writers` line carries no `offer`. While it is a `note` whose fix names "Choose who writes code" (`guard.code_writers` unanswered), offer **Choose who writes code** as a choice with **Not now**, among the others and in the same way, without "(Recommended)" (a note). On yes, load `upgrade-setup` for "Choose who writes code", from its "Where it stands": its question comes next, so ask no other first. In plugin mode, which has no kit update to ask it, this is where it is asked. Once answered, the line's fix no longer names it, and it isn't offered.

**Any other offer** doctor names that isn't in the table (a later kit adds them) is named as text, not offered as a choice: "Doctor also suggests `<offer>`: <the line's fix>." Start only the upgrades in the table.

A line without an offer has only its fix: say it, and do it only if the person asks, as a separate request.

After the offers (or when there are none), the check is done. When the person fixes something, offer to check the set-up again.
