---
name: setup-workflow
description: Set a project up for the pairnexus workflow - interview the owner about the project (stack, tests, CI, UI, areas, sensitive data, releases), write the profile, vendor the kit for cloud sessions, write the Matt Pocock skills' per-repo docs, labels, issue templates and CODEOWNERS, and list the owner's one-time steps. Run once per project.
disable-model-invocation: true
---

# Set up the workflow in a project

This runs from a checkout of the kit (`medtech-group/pairnexus-workflow`), whether or not the project has the kit yet: read this file there and follow it. `KIT` is that checkout. `WF` is `python3 $KIT/scripts/workflow.py`.

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
| Merging | Can a PR merge with no human approval? Unattended runs need that. If the team's rules require an approval, runs end at "ready for review" (`merge.mode: owner`). |
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

**2. The kit.**
- Vendored mode:

  ```bash
  WF vendor install --project . --mattpocock <checkout of mattpocock/skills at the SHA in $KIT/.claude-plugin/marketplace.json>
  ```

  - If it reports files that aren't the kit's (an earlier hand-vendored copy), show the owner the list. Pass `--adopt` only for the ones that are copies of the kit's or Matt Pocock's skills.
  - The project's own skills of the same name get renamed first: move `.claude/skills/next` to `.claude/skills/next-<project>`.
  - If the kit is vendored already, use `WF vendor update` instead.
- Plugin mode: add the marketplace and plugin to `.claude/settings.json` (see `install.md`) and nothing else.

**3. The Matt Pocock skills' per-repo docs.** Read the vendored `.claude/skills/setup-matt-pocock-skills/SKILL.md` and follow its steps. It writes:
- `docs/agents/issue-tracker.md`, the triage labels and the domain-doc layout;
- the "Agent skills" block in `CLAUDE.md`.

`code-review`, `to-spec`, `to-tickets` and `wayfinder` need these. Without them they stop to ask, which stalls an unattended session. The domain docs keep the name the project uses: `CONTEXT.md` or `GLOSSARY.md`.

**4. The earlier flow.**
- Retire the old flow hook from `.claude/settings.json`, and the old flow doc.
- Or point `project.flow_addendum` at the doc, trimmed to what the kit's flow doesn't cover.

**5. `.github/CODEOWNERS`.** It covers `/.claude/`, `/.github/workflows/` and itself, with the owner's handle (`enforcement.md` §3).

**6. A CI job** that runs `python3 .claude/workflow/bin/workflow.py vendor verify --strict` (vendored mode). Its name goes in `ci.required_checks`.

**7. `.gitignore` gets `.workflow/`.** `vendor install` adds it; check it's there.

**8. A "Workflow" section in `CLAUDE.md`.** It points at `.claude/workflow/flow.md` and the profile, and replaces any older flow description. The project's own rules stay where they are.

**9. Labels,** created through the API (`gh api repos/<repo>/labels -f name=… -f color=…`) unless they already exist:
- `ready-for-agent`, `ready-for-human`, `needs-human`, `owner-task`, `needs-triage`, `needs-info`, `wontfix`, `spec`;
- `workflow:in-progress`, `workflow:run`, `workflow:stop`, `workflow:infra`;
- `wayfinder:map`, `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, `wayfinder:task`.

`ready-for-human` and `owner-task` both mean "a person does this". Readiness treats both as human blockers.

**10. Issue templates** in `.github/ISSUE_TEMPLATE/`:
- `build-ticket.md`: Parent, What to build, Acceptance criteria, `Area:`, `## Blocked by`, by-hand checks;
- `owner-task.md`: what the owner does, and what it unblocks.

Then commit, push the branch, and open the pull request. It touches protected paths, so it's the owner's to review and merge.

## 4. The owner's one-time steps

List them in the PR body as a checklist, from `enforcement.md`:

- [ ] **The base branch's ruleset,** set to **Active**:
  - no direct push, no force-push, no deletion;
  - required checks, including the vendor check, and "up to date" required;
  - code-owner review on the CODEOWNERS paths;
  - 0 required approvals for unattended merges.
- [ ] **"Allow auto-merge"** on, for `merge.mode: auto-merge`.
- [ ] **Two claude.ai environments,** named as in the profile:
  - ticket sessions: no credentials, `WORKFLOW_ROLE=ticket`, and the project's setup, including Playwright's browser when the explorer is `browser`;
  - the conductor: `WORKFLOW_ROLE=conductor`, and only the release credentials the owner chooses.
- [ ] **The organisation's GitHub plan,** if rulesets on private repos aren't available.

## Checklist

- [ ] Project explored; only open questions asked
- [ ] Profile written; `WF profile check` passes; `profile.md` points to the rules
- [ ] Kit vendored with its lock (or the plugin enabled), not both; earlier flow retired or made an addendum
- [ ] Matt Pocock's per-repo docs written
- [ ] CODEOWNERS, vendor CI check, `.gitignore`, CLAUDE.md section, labels, issue templates
- [ ] PR opened with the owner's one-time steps
