---
name: setup-workflow
description: Set a project up for the pairnexus workflow in solo mode - explore it, ask only what attended work needs (experience, sensitive data, the explorer, the mode, the owner), read the rulesets back, write the profile, vendor the kit for cloud sessions, write the Matt Pocock skills' per-repo docs, labels, issue templates and CODEOWNERS, and open one pull request to merge and start working. Run once per project.
disable-model-invocation: true
---

# Set up the workflow in a project

This runs from a checkout of the kit, whether or not the project has the kit yet, and in either mode: read this file there and follow it. The kit's home (`<kit repo>`) is the repository you were pointed at: the upstream, `medTech-group/pairnexus-workflow`, or your fork. `KIT` is that checkout, **at the latest release's tag, never `main` between releases**: the version is `git ls-remote --tags --refs https://github.com/<kit repo> 'v*' | sed 's#.*/v##' | sort -V | tail -1`, then `git clone --depth 1 --branch v<version> https://github.com/<kit repo>`, outside the project. Once it is cloned, `WF version --repo` prints the home that release names; projects set up from it follow that home for updates. If you were given a checkout of `main` (`git -C $KIT describe --tags --exact-match` fails), clone the release that way and follow its copy of this file instead. `WF` is `python3 -B $KIT/scripts/workflow.py`. Matt Pocock's skills: `git clone https://github.com/mattpocock/skills` and check out the SHA in `$KIT/.claude-plugin/marketplace.json`.

Explore first, ask only what you can't find, show what you'll write, and write it on a branch with a pull request. The base branch is the owner's; this is a PR like any other.

## 1. Explore

**The repo**
- `git remote -v` gives the repo; also note the default branch.
- `CLAUDE.md` and `AGENTS.md`.
- The domain docs: `CONTEXT.md` or `GLOSSARY.md`, and `docs/adr/`.

**How it builds and tests**
- Package files, a Makefile, the CI workflows (`.github/workflows/`) and the test directories.
- Note each suite's command, where it runs, and how its files can be split into shards.
- Note the CI check names on a recent PR (`gh api repos/<repo>/commits/<sha>/check-runs --jq '.check_runs[].name'`), and any `paths-ignore` or `paths` filters on required checks.

**What it is and how it ships**
- Its interface: a web app, a mobile app, an API, a CLI, or none. Note how it starts locally.
- Deploy scripts, infrastructure tools, secrets files. Deploy commands are asked about only when there are some.

**Whether the base branch is protected already**
- Read the rulesets back as the `upgrade-setup` skill's "Read it back" does (`$KIT/skills/upgrade-setup/SKILL.md`): the repository (`GET repos/<repo>`) in `.workflow/repo.json`, and each ruleset in full, by its id, in one JSON list in `.workflow/rulesets.json`. Ask nothing; the profile (step 3, item 1) writes `ruleset` from it. Never commit these files: `.workflow/` is git-ignored once step 3's `.gitignore` entry (item 7) is there.

**What's there already**
- `.claude/skills`, including an earlier hand-vendored copy of these skills or of Matt Pocock's.
- The hooks in `.claude/settings.json` and `settings.local.json`, especially an earlier flow hook.
- The plugin in any `enabledPlugins`.
- `docs/agents/*`, issue labels (`gh api repos/<repo>/labels --paginate`), and issue templates.

## 2. Ask

Use `AskUserQuestion`, recommended answers first. Set-up asks only what attended work needs, and only what exploring didn't settle:

| Topic | What to ask |
|---|---|
| Experience | How much the people working here know, as the project's default: *new to building* or *developer*. It changes only how the kit words things and paces itself, never what it allows. Skipping it leaves the project's default unset, so each person's own answer counts: the guided start asks each person whose level is unknown, at their first session. Until someone gives one, word things as for *new to building*. |
| Mode | Vendored (works in cloud sessions, and needed for unattended runs later) or the plugin (attended only). One mode per project; if the plugin is enabled org-wide, vendoring would duplicate it, so say so. |
| Owner | The GitHub login of the person whose words are approval. |
| Sensitive data | What counts here, and which patterns would catch it in a post. |
| Explorer | Browser, API, CLI or none. |
| Deploy commands | Only when exploring found deploy scripts or infrastructure tools: which commands deploy (`guard.deploy_commands`), so sessions are refused them or asked first. With none found, don't ask. |
| Earlier flow | If the project has its own flow doc or flow hook: keep it as an addendum (`project.flow_addendum`) or retire it. Two flows injected on every prompt contradict each other. |

**Explaining the glossary's words.** Ask the experience question first, on its own, so its answer is known before the other questions use any of these words. After a *new to building* answer, or a skipped question (worded as *new to building*), follow the glossary's rule for the rest of set-up; a *developer* answer gets none. Read `$KIT/docs/glossary.md`, the glossary in your clone of the kit, if it is there. Explain each of its words in the glossary's wording, in one or two sentences, the first time you use it in this session, and never again in this session. A word you used without explaining it (before the answer, while exploring) still counts as unexplained. Never explain them in what you write on GitHub (pull request descriptions, comments, reports): the set-up pull request's body included, and the files and commit messages it carries. What set-up writes on GitHub reads the same for every level. Sessions after set-up get the same rule from the context hook.

Everything else takes the template's default, or what exploring found: the commands and suites, the CI check names (`ci.required_checks`), no CI (`ci.none = true`, so the local full suite is the gate) and a monorepo's per-package commands and path-filtered checks. Ask nothing about areas, environment names, ticket sessions' permission mode, merge approvals and releases: they matter only for unattended runs, and the upgrade "Set up unattended runs" (the `upgrade-setup` skill) asks them when the person wants runs. If the person brings one up now, say so, and offer that upgrade once the set-up pull request has merged.

## 3. Write, on a branch

**1. The profile.**
- Write `.claude/workflow/profile.toml` from `$KIT/templates/profile.toml`, filled in.
- Write `.claude/workflow/profile.md` from `$KIT/templates/profile.md`. It points to the rules by reference (anchors in `CLAUDE.md`), and covers sensitive data, secrets and environment quirks.
- **`ruleset`,** as a plain line on a line of its own, in place of the template's `# ruleset = false` (the key at the start, nothing after the value: a shell script reads it without TOML):
  - `ruleset = true` only when the rulesets could be read and `WF protection --rulesets .workflow/rulesets.json --repo .workflow/repo.json --base <the base branch> --json`, run in the project, exits 0 with `"protected": true`. Always give `--base`, the base branch exploring found: without it the command reads the base branch from whichever profile it finds, the kit's own included;
  - otherwise `ruleset = false`, which is solo mode. That includes rulesets that can't be read from here, **Exit 2** (an input it refuses, usually a ruleset fetched as a summary: fetch each in full by its id again, once, and write `false` only if it still exits 2), any other failure, and a bypass list it can't see (only a ruleset's admins can): an unknown counts as unprotected.
- **`experience`,** from the answer, in place of the template's `# experience = "new"`: `experience = "new"` (*new to building*) or `experience = "developer"`. When the question was skipped, leave the template's commented line as it is: left out, the level is unknown (worded as *new to building*).
- The run-only settings (`[areas]`, `[release]`, `run.ticket_environment`, `run.conductor_environment`, `run.permission_mode`, `run.environment_setup`) keep the template's defaults until "Set up unattended runs".
- Run `WF profile check` with `CLAUDE_PROJECT_DIR` set to the project, and fix what it reports, except its two warnings that `run.ticket_environment` and `run.conductor_environment` are empty: those are expected until "Set up unattended runs" names them. Leave them, and don't ask for the names.
- **Setup:** `commands.setup` installs the project's own dependencies from its files (`npm ci`, a virtualenv from `requirements.txt`), and `commands.setup_check` exits 0 once that has run (`test -d node_modules`, `test -x .venv/bin/python`). The kit runs setup at each session start when the check fails, since a cloud session starts from a fresh clone. Both empty when there is nothing to install. The environments' setup script (`run.environment_setup`) is left to "Set up unattended runs".

**2. The kit.**
- Vendored mode:

  ```bash
  WF vendor install --project . --mattpocock <checkout of mattpocock/skills at the SHA in $KIT/.claude-plugin/marketplace.json>
  ```

  - If it reports files that aren't the kit's (an earlier hand-vendored copy), show the owner the list.
  - The project's own skills of the same name get renamed first: move `.claude/skills/next` to `.claude/skills/next-<project>` and change its frontmatter `name:` to match, then update anything that sends people to the old name (CLAUDE.md, docs).
  - Then `--adopt` replaces the rest (copies of the kit's or Matt Pocock's skills). It lists each file it replaced, and the `stale` files the old copy had that the kit doesn't ship: delete those the owner agrees are obsolete.
  - A vendored file the project deliberately changes afterwards (for example Matt Pocock's skills saying `GLOSSARY.md` where the project uses `CONTEXT.md`): edit it, then `WF vendor resolve --keep <path>`, so `verify --strict` stays green.
  - If the kit is vendored already, use `WF vendor update` instead.
- Plugin mode: add to the project's `.claude/settings.json`, and nothing else (`<kit repo>` is `WF version --repo`; a fork that renamed its marketplace or plugin uses its own names, from `$KIT/.claude-plugin/`):

  ```json
  {
    "extraKnownMarketplaces": {"pairnexus": {"source": {"source": "github", "repo": "<kit repo>"}}},
    "enabledPlugins": {"pairnexus-workflow@pairnexus": true}
  }
  ```

  Each person then installs it once (`docs/install.md`). Plugin mode is for attended work only: cloud sessions don't install it.

**3. The Matt Pocock skills' per-repo docs.** Read Matt Pocock's `setup-matt-pocock-skills/SKILL.md` (vendored, or in his checkout) and follow its steps, with one change: write `docs/agents/issue-tracker.md` from `$KIT/templates/issue-tracker.md` (OWNER/REPO filled in), not from his GitHub template, which uses `gh issue …` subcommands that cloud sessions don't have. It also writes the triage labels doc, the domain-doc layout and the "Agent skills" block in `CLAUDE.md`.

`code-review`, `to-spec`, `to-tickets` and `wayfinder` need these. Without them they stop to ask, which stalls an unattended session. The domain docs keep the name the project uses (`CONTEXT.md` or `GLOSSARY.md`): where his skills name the other one, edit them and `vendor resolve --keep`.

**4. The earlier flow.**
- Retire the old flow hook from `.claude/settings.json`, and the old flow doc.
- Or point `project.flow_addendum` at the doc, trimmed to what the kit's flow doesn't cover.

**5. `.github/CODEOWNERS`.** It covers `/.claude/`, `/.github/workflows/` and itself, with the owner's handle (`enforcement.md` §3). It requests the owner's review on those paths; the ruleset that "Protect `main`" guides leaves "Require review from Code Owners" off while sessions act under the owner's GitHub account, since GitHub never lets an author approve their own pull request.

**6. A CI job,** in vendored mode: copy `$KIT/templates/github/workflow-kit.yml` to `.github/workflows/workflow-kit.yml`, replacing `BASE_BRANCH` with the base branch. Its check, `workflow kit`, goes in `ci.required_checks`. Also copy `$KIT/templates/github/workflow-kit-update.yml` to `.github/workflows/workflow-kit-update.yml`: the weekly check that opens an issue when a newer kit release is out (not a required check).

**7. `.gitignore` gets `.workflow/` and `__pycache__/`.** `vendor install` adds them in vendored mode; check they're there. In plugin mode, add them yourself. Either way, before committing, check that nothing under `.workflow/` (the read-back's files) is staged.

**8. A "Workflow" section in `CLAUDE.md`.** It points at `.claude/workflow/flow.md` and the profile, says a session starts with the guided start (the `start` skill: "What are we working on?", or `/start`), and replaces any older flow description. The project's own rules stay where they are.

**9. Labels,** created through the API (`gh api repos/<repo>/labels -f name=… -f color=…`) unless they already exist:
- `ready-for-agent`, `ready-for-human`, `needs-human`, `owner-task`, `needs-triage`, `needs-info`, `wontfix`, `spec`;
- `workflow:in-progress`, `workflow:run`, `workflow:stop`, `workflow:infra`;
- `wayfinder:map`, `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, `wayfinder:task`.

`ready-for-human` and `owner-task` both mean "a person does this". Readiness treats both as human blockers.

**10. Issue templates:** copy `$KIT/templates/github/ISSUE_TEMPLATE/build-ticket.md` and `owner-task.md` to `.github/ISSUE_TEMPLATE/`, keeping any the project has.

Then commit, push the branch, and open the pull request. It touches protected paths, so it's the owner's to review and merge.

## 4. The pull request

Its body is short. It opens with **Merge this and start working**: once it merges, attended work starts (a session begins with the guided start, or `/start`). Then:
- what it adds, in a few lines;
- whether the project starts in solo mode: with `ruleset = false`, one plain line that the kit's guard refuses changes straight to the base branch (by its real name) until it is protected, and why (no ruleset was read back, or the rulesets couldn't be read from here); with `ruleset = true`, that the base branch is protected already;
- two optional next steps, each one request to Claude, none needed to start:
  - **"Protect `main`"**: a ruleset and the merge settings, guided click by click, then a small pull request that leaves solo mode. Left out when `ruleset = true`;
  - **"Set up unattended runs"**: the two cloud environments and the questions only runs need, so Claude can work while nobody is watching. Vendored mode only.

It carries no checklist of clicks: the upgrades guide those when the person wants them, and the kit's README keeps them as the fallback.

## 5. After the merge

When the person says the pull request has merged (or you see it merged), first check out the base branch and bring it up to date with the merge (`git fetch origin <base> && git checkout <base> && git merge --ff-only origin/<base>`), so the profile and the kit are there. If the fast-forward fails (the local base branch has its own commits), say so and stop there: never reset or rebase it. Then offer "Protect `main`" once, as a choice (`AskUserQuestion`) with **Do it now** (recommended) and **Not now**. It is the `upgrade-setup` skill's `protect_main` offer: on **Do it now**, follow that skill from its "The screens", reading the level as it says, but skip its opening choice (the person has just chosen): `.claude/skills/upgrade-setup/SKILL.md` in vendored mode, or `$KIT/skills/upgrade-setup/SKILL.md` in plugin mode (the person may not have installed the plugin yet). **Not now** ends it: don't offer it again in this session. Don't offer it when set-up wrote `ruleset = true`: the base branch is protected already. Don't offer "Set up unattended runs" here unless the person asked for it, or brought up its questions during set-up; the PR body names it.

## Checklist

- [ ] Project explored, the rulesets read back; only the attended questions asked
- [ ] Profile written with `ruleset` and `experience`; `WF profile check` passes; `profile.md` points to the rules
- [ ] Kit vendored with its lock, or the plugin enabled, only one of the two; earlier flow retired or made an addendum
- [ ] Matt Pocock's per-repo docs written
- [ ] CODEOWNERS, vendor CI check, `.gitignore`, CLAUDE.md section, labels, issue templates
- [ ] PR opened: "Merge this and start working", with the two upgrades as optional next steps
- [ ] After the merge, "Protect `main`" offered once (unless already protected)
