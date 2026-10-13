---
name: setup-workflow
description: Set a project up for the pairnexus workflow - interview the owner about the project (stack, tests, CI, UI, areas, sensitive data, releases), write the profile, vendor the kit for cloud sessions, write the Matt Pocock skills' per-repo docs, labels, issue templates and CODEOWNERS, and list the owner's one-time steps. Run once per project.
disable-model-invocation: true
---

# Set up the workflow in a project

This runs from a checkout of the kit (`medtech-group/pairnexus-workflow`), whether or not the project has the kit yet, and in either mode: read this file there and follow it. `KIT` is that checkout, **at the latest release's tag, never `main` between releases**: the version is `git ls-remote --tags --refs https://github.com/medTech-group/pairnexus-workflow 'v*' | sed 's#.*/v##' | sort -V | tail -1`, then `git clone --depth 1 --branch v<version> https://github.com/medTech-group/pairnexus-workflow`, outside the project. If you were given a checkout of `main` (`git -C $KIT describe --tags --exact-match` fails), clone the release that way and follow its copy of this file instead. `WF` is `python3 -B $KIT/scripts/workflow.py`. Matt Pocock's skills: `git clone https://github.com/mattpocock/skills` and check out the SHA in `$KIT/.claude-plugin/marketplace.json`.

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
- Deploy scripts, infrastructure tools, secrets files.

**What's there already**
- `.claude/skills`, including an earlier hand-vendored copy of these skills or of Matt Pocock's.
- The hooks in `.claude/settings.json` and `settings.local.json`, especially an earlier flow hook.
- The plugin in any `enabledPlugins`.
- `docs/agents/*`, issue labels (`gh api repos/<repo>/labels --paginate`), and issue templates.

## 2. Ask

Use `AskUserQuestion`, recommended answers first. Ask only what exploring didn't settle:

| Topic | What to ask |
|---|---|
| Mode | Vendored (works in cloud sessions; recommended for unattended runs) or the plugin (attended only). One mode per project; if the plugin is enabled org-wide, vendoring would duplicate it, so say so. |
| Owner | The GitHub login of the person whose words are approval in runs. |
| Merging | Can a PR merge with no human approval? Unattended runs need that. If the team's rules require an approval, say that each run's conductor sees it in the ruleset and recommends the merge mode **owner**, so runs end at "ready for review". The merge mode is chosen per run in the charter, not in the profile: there is no `[merge]` table. |
| No CI | Then the local full suite is the gate (`ci.none = true`), and every run report says "add CI". |
| Monorepo | Commands per package, and which required checks are path-filtered, so they may never run on a PR (`ci.path_filtered`). |
| Explorer | Browser, API, CLI or none. |
| Areas | The parts of the project two sessions shouldn't touch at once: features, layers or packages. |
| Sensitive data | What counts here, and which patterns would catch it in a post. |
| Releases | Which commands deploy, and what runs after merges, each step with its smoke test. |
| Repair | What a fresh or restarted container needs: start Docker or a database, free disk. |
| Environments | The names of the two claude.ai environments, one for the conductor and one for ticket sessions, and the permission mode ticket sessions run in (`auto` recommended). |
| Earlier flow | If the project has its own flow doc or flow hook: keep it as an addendum (`project.flow_addendum`) or retire it. Two flows injected on every prompt contradict each other. |

## 3. Write, on a branch

**1. The profile.**
- Write `.claude/workflow/profile.toml` from `$KIT/templates/profile.toml`, filled in.
- Write `.claude/workflow/profile.md` from `$KIT/templates/profile.md`. It points to the rules by reference (anchors in `CLAUDE.md`), and covers sensitive data, secrets and environment quirks.
- Run `WF profile check` with `CLAUDE_PROJECT_DIR` set to the project, and fix what it reports.
- **Setup, in two parts** (`templates/profile.toml` explains both):
  - `commands.setup` installs the project's own dependencies from its files (`npm ci`, a virtualenv from `requirements.txt`), and `commands.setup_check` exits 0 once that has run (`test -d node_modules`, `test -x .venv/bin/python`). The kit runs setup at each session start when the check fails, since a cloud session starts from a fresh clone. Both empty when there is nothing to install.
  - `run.environment_setup` is the environments' setup script: only machine tools the cloud image lacks (it has Python, Node.js, Java, Go, Rust, Ruby, PHP, Docker, PostgreSQL and Redis), never reading the repository's files, exiting 0, under about five minutes. Empty for most projects; e.g. downloading Flutter for a Flutter app.

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
- Plugin mode: add to the project's `.claude/settings.json`, and nothing else:

  ```json
  {
    "extraKnownMarketplaces": {"pairnexus": {"source": {"source": "github", "repo": "medtech-group/pairnexus-workflow"}}},
    "enabledPlugins": {"pairnexus-workflow@pairnexus": true}
  }
  ```

  Each person then installs it once (`docs/install.md`). Plugin mode is for attended work only: cloud sessions don't install it.

**3. The Matt Pocock skills' per-repo docs.** Read Matt Pocock's `setup-matt-pocock-skills/SKILL.md` (vendored, or in his checkout) and follow its steps, with one change: write `docs/agents/issue-tracker.md` from `$KIT/templates/issue-tracker.md` (OWNER/REPO filled in), not from his GitHub template, which uses `gh issue …` subcommands that cloud sessions don't have. It also writes the triage labels doc, the domain-doc layout and the "Agent skills" block in `CLAUDE.md`.

`code-review`, `to-spec`, `to-tickets` and `wayfinder` need these. Without them they stop to ask, which stalls an unattended session. The domain docs keep the name the project uses (`CONTEXT.md` or `GLOSSARY.md`): where his skills name the other one, edit them and `vendor resolve --keep`.

**4. The earlier flow.**
- Retire the old flow hook from `.claude/settings.json`, and the old flow doc.
- Or point `project.flow_addendum` at the doc, trimmed to what the kit's flow doesn't cover.

**5. `.github/CODEOWNERS`.** It covers `/.claude/`, `/.github/workflows/` and itself, with the owner's handle (`enforcement.md` §3). It requests the owner's review on those paths; whether the ruleset also requires it depends on whose GitHub account the sessions use (§4 below).

**6. A CI job,** in vendored mode: copy `$KIT/templates/github/workflow-kit.yml` to `.github/workflows/workflow-kit.yml`, replacing `BASE_BRANCH` with the base branch. Its check, `workflow kit`, goes in `ci.required_checks`. Also copy `$KIT/templates/github/workflow-kit-update.yml` to `.github/workflows/workflow-kit-update.yml`: the weekly check that opens an issue when a newer kit release is out (not a required check).

**7. `.gitignore` gets `.workflow/` and `__pycache__/`.** `vendor install` adds them; check they're there.

**8. A "Workflow" section in `CLAUDE.md`.** It points at `.claude/workflow/flow.md` and the profile, says a session starts with the guided start (the `start` skill: "What are we working on?", or `/start`), and replaces any older flow description. The project's own rules stay where they are.

**9. Labels,** created through the API (`gh api repos/<repo>/labels -f name=… -f color=…`) unless they already exist:
- `ready-for-agent`, `ready-for-human`, `needs-human`, `owner-task`, `needs-triage`, `needs-info`, `wontfix`, `spec`;
- `workflow:in-progress`, `workflow:run`, `workflow:stop`, `workflow:infra`;
- `wayfinder:map`, `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, `wayfinder:task`.

`ready-for-human` and `owner-task` both mean "a person does this". Readiness treats both as human blockers.

**10. Issue templates:** copy `$KIT/templates/github/ISSUE_TEMPLATE/build-ticket.md` and `owner-task.md` to `.github/ISSUE_TEMPLATE/`, keeping any the project has.

Then commit, push the branch, and open the pull request. It touches protected paths, so it's the owner's to review and merge.

## 4. The owner's one-time steps

List them in the PR body as a checklist, with the clicks of `$KIT/README.md` ("Getting started", steps 2 to 6) filled in with this project's values: the required check names one per line, both environment names, and the environments' setup script exactly as it is pasted: the profile's `run.environment_setup`, or "leave Setup script blank" when it is empty, as it is for most projects. The owner should be able to do every step from the PR body alone. The checklist, from `enforcement.md`:

- [ ] **The organisation's GitHub plan,** if rulesets on private repos aren't available: first, since the ruleset needs it.
- [ ] **The base branch's ruleset,** set to **Active**:
  - no direct push, no force-push, no deletion;
  - required checks, including the vendor check, and "Require branches to be up to date" ticked;
  - "Require review from Code Owners" **off** while sessions act under the owner's GitHub account (the usual setup): GitHub never lets an author approve their own PR, so a PR touching a CODEOWNERS path would never merge. CODEOWNERS still requests the owner's review, and the protected paths stay protected by the guard, the credential-free ticket environment, and those changes going to the owner as owner tasks. Turn it **on** only when agents use their own GitHub identity (a bot account or a GitHub App);
  - 0 required approvals for unattended merges;
  - an empty bypass list (sessions act through the owner's account), and "Require linear history" off.
- [ ] **"Allow auto-merge"** on, for runs whose charter says `merge.mode: auto-merge`, and **"Allow merge commits"** on: sessions merge with a merge commit.
- [ ] **Two claude.ai environments,** named exactly as in the profile (the conductor finds the ticket environment by name):
  - ticket sessions: no credentials, `WORKFLOW_ROLE=ticket`, and the setup script (usually blank);
  - the conductor: `WORKFLOW_ROLE=conductor`, the same setup script, and only the release credentials the owner chooses.
- [ ] **Check it:** ask a cloud session to check the ruleset, the merge settings and the two environments (the kit's README, step 6).

## Checklist

- [ ] Project explored; only open questions asked
- [ ] Profile written; `WF profile check` passes; `profile.md` points to the rules
- [ ] Kit vendored with its lock, or the plugin enabled, only one of the two; earlier flow retired or made an addendum
- [ ] Matt Pocock's per-repo docs written
- [ ] CODEOWNERS, vendor CI check, `.gitignore`, CLAUDE.md section, labels, issue templates
- [ ] PR opened with the owner's one-time steps
