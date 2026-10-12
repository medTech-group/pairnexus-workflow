---
name: setup-workflow
description: Set a project up for the pairnexus workflow - interview the owner about the project (stack, tests, CI, UI, areas, sensitive data, releases), write the profile, create the labels and issue templates, write CODEOWNERS, vendor the kit for cloud sessions, and list the owner's one-time steps. Run once per project.
disable-model-invocation: true
---

# Set up the workflow in a project

Explore first, ask only what you can't find, show what you'll write, and write it on a branch with a pull request. Never push to the base branch.

## 1. Explore

- `git remote -v` (the repo), the default branch, `CLAUDE.md`/`AGENTS.md`, `CONTEXT.md`, `docs/adr/`.
- How to set up, typecheck and test: package files, Makefile, CI workflows (`.github/workflows/`), test directories. Note each suite's command and how its files can be split into shards.
- The CI check names on a recent PR (`gh api repos/<repo>/commits/<sha>/check-runs`).
- A UI? (a web app, a mobile app, an API, a CLI, none) and how it starts locally.
- Deploy scripts, infrastructure tools, secrets files.
- What already exists: `.claude/skills`, `.claude/settings.json` hooks, an earlier hand-vendored copy of these skills, the plugin in `enabledPlugins`.

## 2. Ask (`AskUserQuestion`, recommended answers first)

Only what exploring didn't settle. The portability questions:

- **Mode:** vendored (works in cloud sessions; recommended for unattended runs) or the plugin (attended only). One mode per project.
- **Merging:** can a PR merge with no human approval (unattended runs need that), or do the team's rules require one? If so, unattended runs end at "ready for review".
- **No CI?** Then the local full suite is the gate, and the report keeps saying "add CI".
- **Monorepo?** Commands per package, and which required checks are path-filtered (they may never run on a PR).
- **The UI explorer:** browser, API, CLI or none.
- **Areas:** the parts of the project two sessions shouldn't touch at once (features, layers, packages).
- **Sensitive data:** what counts here, and which patterns would catch it in a post.
- **Deploy commands and release steps:** which commands deploy, and what runs after merges (each step with its smoke test).
- **Environment repair:** what a fresh or restarted container needs (start Docker or a database, free disk).

## 3. Write (on a branch)

1. `.claude/workflow/profile.toml`, from `templates/profile.toml`, filled in. Check it: `workflow profile check`.
2. `.claude/workflow/profile.md`, from `templates/profile.md`: the rules by reference (anchors in `CLAUDE.md`), sensitive data, secrets.
3. **Vendored mode:** `python3 <kit>/scripts/workflow.py vendor install --project . --mattpocock <checkout of mattpocock/skills at the pinned sha>`. Use `--adopt` if an earlier hand-vendored copy is there. This writes the skills, agents, CLI, flow, templates, lock and hooks.
   - **Plugin mode:** add the marketplace and plugin to the project's `.claude/settings.json` (`docs/install.md`) and nothing else.
4. `.github/CODEOWNERS` covering `.claude/`, `.github/workflows/` and itself (`docs/enforcement.md`), with the owner's handle.
5. `.gitignore`: `.workflow/` (the evidence runner's results).
6. `CLAUDE.md`: a short "Workflow" section pointing at `.claude/workflow/flow.md` and the profile, replacing any older flow description. Keep the project's own rules where they are.
7. Labels, created through the API:
   - `ready-for-agent`, `needs-human`, `owner-task`, `needs-triage`, `needs-info`, `wontfix`;
   - `workflow:in-progress`, `workflow:run`, `workflow:stop`;
   - `wayfinder:map`, `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, `wayfinder:task`.

Commit, push the branch, and open the pull request. It touches protected paths, so it is the owner's to review and merge.

## 4. The owner's one-time steps

List them in the PR body as a checklist, from `docs/enforcement.md`:

- [ ] The base branch's ruleset:
  - no direct push, no force-push, no deletion;
  - required checks, and "up to date" required;
  - code-owner review on the CODEOWNERS paths;
  - 0 required approvals for unattended merges.
- [ ] "Allow auto-merge" turned on, for `merge.mode: auto-merge`.
- [ ] A claude.ai environment for ticket sessions: no credentials, and `WORKFLOW_ROLE=ticket`.
- [ ] If GitHub says rulesets aren't available on the plan: the organisation's plan.

## Checklist

- [ ] Project explored; only open questions asked
- [ ] Profile written and `workflow profile check` passes; `profile.md` points to the rules
- [ ] Kit vendored with its lock (or the plugin enabled), not both
- [ ] CODEOWNERS, `.gitignore`, CLAUDE.md section
- [ ] Labels created
- [ ] PR opened with the owner's one-time steps
