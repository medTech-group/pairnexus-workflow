# Proposal (v2): pairnexus-workflow

> [!NOTE]
> **Historical design record, kept as written.** The kit has moved on since (the profile is `profile.toml`, the run's state lives in the tracking issue's body, the conductor runs only in the cloud, and more). Where this differs from `flow.md`, `charter.md`, `enforcement.md`, `profile.md` or the skills, they win.

A reusable kit for the plan → spec → tickets → build → review → merge workflow, attended or unattended, in any repo.

**Owner decisions so far:**
- **Repo:** new and private, `medtech-group/pairnexus-workflow`.
- **Tracker:** GitHub Issues only in v1.
- **Scope:** the full kit, with pair-drop moved onto it as the first user.
- **Dependency:** the Matt Pocock skills.

**v2** follows two independent reviews: one of the workflow against the weekend run's evidence (40 findings), and one of every mechanism against Claude Code's documentation. The changes from v1 are listed at the end.

---

## 1. The two facts that shape the design

**1. Cloud sessions don't install plugins, but they do load what's committed in the repo.**
- Unattended runs happen in claude.ai/code cloud sessions.
- There, repo `.claude/skills/`, `.claude/agents/` and the hooks in `.claude/settings.json` load. Hooks load only in single-repo sessions.
- Plugins declared in the repo are not installed.

So the kit's **primary form is a copy committed into each project**, which `setup-workflow` generates, version-stamps and keeps in step. The plugin is how it's distributed, and how it's used on a laptop.

**2. Prompts and hooks are not a security boundary. GitHub and the environment are.**
- The weekend's "never" list held only because sessions obeyed it.
- The ticket sessions ran in an environment that could deploy and change accounts.
- A Bash hook misses GitHub MCP tools, `gh api`, `git -C . push`, and edits made through Edit/Write.

So enforcement is layered, real boundary first:

| Layer | What it enforces | Strength |
|---|---|---|
| **GitHub rulesets on the base branch** | No direct push or force-push; required checks before merge | Hard |
| **A separate cloud environment for ticket sessions** | No cloud, account or deploy credentials; a `WORKFLOW_ROLE=ticket` variable | Hard |
| **CODEOWNERS on protected paths** | Hooks, CI config, test config, the kit's own files need the owner's review | Hard, if reviews are required |
| **Guard hook** (PreToolUse on Bash, `mcp__github__*`, Edit/Write) | Pushes to base, force-push, deploy commands, edits to protected paths, skipped tests, posting sensitive data | Defence in depth |
| **Instructions** | Everything else | Soft |

---

## 2. Keep (what made the run work)

1. **The flow:** an optional map, then spec, then build tickets with `Blocked by`, then code. `/next` also works with plain `ready-for-agent` tickets and no maps.
2. **One ticket per session**, starting fresh from the base branch, with a full self-contained briefing.
3. **Building:** claim, then `tdd` at the spec's seams, typecheck and single test files as it goes, and the full suite at the end.
4. **The review panel.** Four reviewers run in parallel; each finding is checked, then fixed with a test or answered with a reason. The panel repeats until a round is clean, up to 3 rounds. Then a short Correctness pass reviews any commit made after the last round, which was missing in the weekend run.
5. **The PR body:** `Closes #n`, what was built, how it was tested, a findings table, and the decisions taken.
6. **The merge rule** (§6), with waivers granted explicitly by the owner.
7. **The conductor:**
   - at most N sessions at once, with lanes and check-ins;
   - a failed session is retried once, then the ticket goes to `needs-human`;
   - a final report at the end.
8. **The tracking issue and the by-hand checklist issue.** A check that needs a real device, account or service is built against fakes and listed in the checklist; it is never faked as done.
9. **Notes for the next ticket,** now targeted (§7).
10. **Decisions the spec doesn't settle:** take the safest consistent choice and record it in the PR for the owner.
11. **The stop rule:** if CI is still red after 3 fixes, or the ticket can't be built as written, label it `needs-human`, say why, and stop.

## 3. Roles and authority

**Roles:**
- **Owner:** grants authority, decides, does owner tasks.
- **Conductor:** orchestrates.
- **Ticket session:** builds one ticket.
- **Reviewer:** read-only.
- **Conductor-ops:** the conductor's own code and operations. The weekend conductor opened 4 PRs, deployed, wrote secrets and built apps; v1 pretended it didn't.

**Authority is granted by the owner and recorded, never inferred:**
- Grants cover merges, a waiver of a named CI check, deploys, account changes, scope and run length.
- The owner posts each grant as a comment on the tracking issue, or the conductor quotes the owner's chat message with its time. The state records the grant's URL or quote.
- Grants for a waiver or a deploy expire with the run.

**Merges:**
- Where possible, by **GitHub auto-merge behind the ruleset**.
- Otherwise by the ticket session or the conductor, under a recorded merge grant.
- A review agent is a quality step, never a way to get permission. The weekend's "review before merging" was shaped to get past the permission classifier; v2 doesn't do that.

**Conductor-ops** (a PR of its own, a deploy, a release, writing a secret, changing an account): each action needs a recorded grant and goes in the **outward-changes ledger**. `run-report` turns the ledger into a confirm-or-revert list for the owner.

**Owner tasks:** issues labelled `owner-task`. Readiness treats them as a human blocker, so the conductor never starts one and reports them instead.

## 4. Run limits, the kill switch and cleanup

- **Per-run limits in the state:** an end time, max concurrent sessions, max total sessions, max retries per ticket, and an optional budget note. The conductor stops when a limit is reached.
- **Kill switch:** a `workflow:stop` label on the tracking issue. The conductor checks it at every check-in; when set, it interrupts and archives the running sessions and stops.
- **Stopping a session safely:**
  - `interrupt_session` then `archive_session`, then a check that its branch has stopped moving. The weekend's #225 session was told to stop and pushed anyway.
  - A retry's briefing names the branch, PR and head SHA the first attempt left.
- **Cleanup at the end:**
  - delete the conductor's and the children's pending scheduled check-ins;
  - unsubscribe from PRs;
  - archive finished sessions;
  - post the final report.

## 5. Readiness, state and prompts are scripts, not judgment

These ship as small tested scripts in the kit (`workflow ready|render|state|evidence`):

- **`ready`:** a ticket is ready when it is open, has `ready-for-agent`, its blockers are closed as completed (not `not_planned`), it has no open PR closing it, and it isn't `needs-human`, `owner-task`, claimed or excluded.
  - **Claim** is the `workflow:in-progress` label plus an assignee. v1's "unassigned" rule contradicted the claim, and broke in teams where people self-assign.
- **`state`:** a small JSON block in the tracking issue body, schema-checked, with the conductor as its only writer. The narrative goes in comments. Large data (the dependency graph, the ledger) goes in a state file on a `workflow-state` branch, using its SHA for compare-and-swap. The issue body's 65,536-character limit and lack of compare-and-swap are why.
- **`render`:** builds a ticket session's briefing from the template, the profile, the run state and the conductor's curated slots. It refuses to send if any `{{…}}` is left (the "SEE_BELOW" incident) or any required slot is empty. Required slots:
  - `alongside`: what is running in parallel and what to stay out of;
  - `read_first`: the exact notes and comments to read;
  - `owner_decisions`: what the owner decided since the last ticket;
  - `briefing`: anything specific to this ticket.
- **`evidence`:** posts the local full-suite proof (§6).

## 6. The merge rule

**By default every required check is green.**

**A waiver:**
- is per run and per named check;
- is granted by the owner, recorded, and expires with the run;
- covers only a check that was **killed, not failed**: exit 143, runner shutdown, cancelled, or never started. A real test failure always blocks.

**Local evidence**, posted by `workflow evidence`:
- the command, head SHA, test count, duration and log tail;
- the count must not be lower than the base branch's, which also catches skipped tests.

**Level with base:**
- the branch must be level with the base branch when it merges;
- whoever merges second merges base in and reruns.

**Teams that require human approval:** the rule then becomes auto-merge after that approval. Otherwise the project is attended-only.

## 7. Notes, lanes and preemption

**Notes for the next ticket:**
- each is tagged with its area and target tickets ("For #201");
- `render` puts the exact comment links in `read_first`;
- lasting knowledge moves into the repo's own docs in the same PR, so the tracking issue doesn't become 2,000 lines that every session reads. #232 reached 71 comments.

**Lanes:**
- tickets carry an `Area:` field, set when the ticket is written;
- the profile lists the areas, with optional path globs;
- the conductor runs at most one session per area unless the run state records an override, as the weekend did with "#151 Copilot beside a phone-only ticket".

**Preemption:** an infra ticket the conductor opens (CI time, a flake) takes the next free slot. A rule can pause a ticket session for it, as with #260.

## 8. The project profile

**`profile.yaml`** (schema-checked at setup; read by the hooks and scripts):
- base branch;
- commands: setup, typecheck, single test, full suite as shards plus a resumable runner;
- the UI or API stack and how to start each app at given sizes;
- required checks;
- the never-list (deploy commands, protected paths);
- areas;
- environment repair;
- **release steps:** deploy, smoke test, app builds, each gated on an owner grant;
- check-in cadence;
- run defaults.

**`profile.md`** (prose):
- the safety rules **by reference**: the anchors in CLAUDE.md or other docs, never a copy that drifts;
- the data classification (what counts as sensitive, which outputs must never contain it);
- the secrets policy;
- wording rules.

**A portability interview** in `setup-workflow` covers:

| Situation | What the kit does |
|---|---|
| No UI | The UI explorer becomes an API or CLI explorer, or is skipped |
| No CI | The local full suite is the gate, with a standing "add CI" warning |
| Monorepo | Commands per package; required checks that are path-filtered and never ran are handled |
| Solo or team | Merge grants vs required human reviews |
| No issues yet | Start at "write a spec" or "import a backlog" |

## 9. Sensitive data and secrets

**Sensitive data:**
- The profile classifies what is sensitive; for pair-drop, PHI.
- The guard scans outward MCP posts (issues, comments, PR bodies) against it.
- UI-explorer screenshots stay local.
- Tracking notes name ids, never people.

**Secrets:**
- never printed, never committed;
- config files that hold keys are owner-only steps;
- writing a secret is conductor-ops (a grant and the ledger);
- `.env` and key files are protected paths.

## 10. Hooks

| Hook | Event | Behaviour |
|---|---|---|
| `guard` | PreToolUse: Bash, `mcp__github__*`, Edit/Write | Blocks the never-list, protected paths, skipped tests and sensitive posts. In attended sessions it warns rather than blocks (configurable). Defence in depth only |
| `checklist-gate` | Stop | Ticket sessions only. Reads `last_assistant_message` and `stop_hook_active`. Allows stopping when the checklist is present, or a check-in is scheduled, or a `waiting`/`needs-human` marker is set. At most 2 blocks a session; the platform also caps it at 8 |
| `env-repair` | SessionStart, plus a re-runnable `workflow repair` command | The profile's repair steps. A container restart mid-session doesn't fire SessionStart, so the suite runner calls `repair` itself and keeps its shard results on disk by head SHA |
| `flow-context` | UserPromptSubmit | Injects the flow only on a flow verb plus an issue reference, or on `/next`, not on any `#n` |

**Session role:** `WORKFLOW_ROLE` set by the ticket sessions' own cloud environment, with branch `claude/build-*` as a fallback. A file in the repo isn't used, because the session can edit it.

## 11. Agents (reviewers)

- **Standards and Spec:** one source, `code-review`'s two sub-agents, not duplicates.
- **Correctness:** `tools: Read, Grep, Glob`, with no Bash, so it is truly read-only. It may run the tests through a separate read-only command if the profile allows.
- **UI explorer:**
  - Bash for the stack, plus Playwright from the kit's `.mcp.json`; agent frontmatter can't declare MCP servers;
  - after it runs, `git status` must be clean.
- No `hooks`, `mcpServers` or `permissionMode` in agent frontmatter. Plugin agents ignore them.

## 12. Distribution, the Matt Pocock skills, versions

**The marketplace** (`pairnexus`, in the private repo):
- it lists `pairnexus-workflow`, and `mattpocock-skills` from `github: mattpocock/skills` **pinned by `sha`**;
- `pairnexus-workflow` declares the dependency `mattpocock-skills`, so installing ours installs his;
- install only one copy of the Matt Pocock skills; two plugins with that name drop one's hooks.

**On a laptop:**
- `gh auth login && gh auth setup-git`;
- `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1` when there is no SSH key, since the repo is private;
- then `/plugin marketplace add medtech-group/pairnexus-workflow` and install.

**In cloud sessions:**
- **The vendored copy:** `setup-workflow` writes the kit's skills, agents, hooks (into `.claude/settings.json`, using `$CLAUDE_PROJECT_DIR`) and scripts, plus the Matt Pocock skills, into the project's `.claude/`.
- **The lockfile** (`.claude/workflow/lock.json`) records the kit version, the Matt Pocock SHA and each file's hash.
- **`/update-workflow`** does a three-way merge that keeps local edits.
- **A CI check** verifies the copy against the lockfile.
- **One mode per project:** the vendored copy, or the plugin. Setup refuses both, which would give duplicate skills and hooks firing twice.

**Versions:**
- semver, a CHANGELOG and git tags;
- projects pin a version;
- the marketplace pins to a tag.

**Scheduling:**
- Cloud conductor: `send_later` (Claude Code Remote).
- Local conductor: `/loop`, CronCreate, or ScheduleWakeup (the session must stay open; jitter and 7-day expiry apply).
- Skills that a loop or schedule runs are **not** marked `disable-model-invocation`.

## 13. Skills

| Skill | Purpose |
|---|---|
| `setup-workflow` | The interview, profile, labels, issue templates, rulesets checklist, CODEOWNERS, the vendored copy and lockfile, the cloud-environment checklist |
| `next` | Find ready work (maps optional) and do it under the flow |
| `build-ticket` | One ticket, claim to merge, under the rules above |
| `review-panel` | The reviewers on any diff or PR; usable alone |
| `conductor` | Start, run, resume and stop a run; limits, the kill switch, lanes, preemption, retries, conductor-ops, cleanup |
| `run-report` | From the state, each PR's decisions, the by-hand checklist, the ledger, follow-ups and per-ticket metrics (wall time, review rounds, CI minutes, retries) |
| `update-workflow` | Refresh the vendored copy |

## 14. Testing the kit, and the build plan

**Spike first** (riskiest assumptions, a day at most), with results recorded before any build:
1. In a cloud session, can a setup script install the plugin from the private repo? Is the private repo cloneable from cloud? Do plugin hooks fire without `/reload-plugins`?
2. Do repo hooks in `.claude/settings.json` block `mcp__github__merge_pull_request` and `git -C . push origin main` in a cloud ticket session?
3. Do rulesets work on medtech-group's private repos on its GitHub plan?
4. Does the `mattpocock-skills` dependency resolve from our marketplace?
5. Does the Stop gate behave while a session waits on CI?

**The kit's own tests:**
- hook unit tests on JSON fixtures, including bypass attempts;
- script tests for `ready`, `render`, `state` and `evidence`;
- CI on the kit repo.

**The sandbox e2e:** a private sandbox repo with 6 toy tickets:
- a chain;
- two in parallel;
- one with a flaky test;
- one that is impossible and must end `needs-human`;
- one that edits a protected path;
- one that needs an owner task.

The conductor runs them unattended before each release.

**Build order:**
1. The spike.
2. Spec and tickets in the new repo.
3. Scripts and hooks, with their tests.
4. Skills and agents.
5. `setup-workflow` and the vendoring.
6. The sandbox e2e.
7. pair-drop migrates in a PR, reviewed.

---

## What changed from v1

1. The vendored copy is primary for cloud; v1 assumed plugins load there, and they don't.
2. Enforcement is now GitHub rulesets, a separate credential-free ticket environment, CODEOWNERS and hooks; v1 relied on a Bash-only hook.
3. Merge authority comes from the owner and is recorded; v1 had a review agent stand in as permission.
4. Run limits, a kill switch, safe stopping and cleanup are new.
5. Conductor-ops, an outward-changes ledger, release steps and owner tasks are new.
6. Readiness, state, prompt rendering and evidence are tested scripts, with required briefing slots.
7. The CI waiver is per run, explicit and expiring; local evidence is checked against the base branch's test count.
8. Notes are targeted, lanes come from an `Area:` field, and infra tickets can preempt.
9. The profile is split into yaml and md, safety rules are referenced not copied, and a portability interview is added.
10. Sensitive-data and secrets policies are added.
11. The Stop gate is safe while waiting, and environment repair survives container restarts.
12. Reviewers are truly read-only, the Standards and Spec reviewers are not duplicated, and a post-final-round pass is added.
13. The Matt Pocock skills are pinned by SHA in our marketplace; the kit has a lockfile, versions and one-mode-per-project.
14. A spike comes first, then a 6-ticket sandbox e2e replaces v1's one-ticket dry run.

---

## v3 addition: the run charter (owner-approved 12 Oct)

Before an unattended run starts, the conductor:

1. **Runs pre-flight checks** with no questions: readiness, the safety setup, leftovers from an earlier run, and capacity.
2. **Asks the kick-off questions once:** scope, limits, merging and CI waivers, release, changes outside the repo, the conductor's own fix PRs, open product decisions, what stops the run, and how to reach the owner. Each question has a recommended default.
3. **Shows the charter back** and gets one "go", recorded with its source on the tracking issue.

During the run:
- **Nothing waits on the owner.** Anything outside the charter is set aside and reported.
- **The owner can amend the charter** by commenting on the tracking issue.
- **The `workflow:stop` label is the kill switch.**

**Later runs:** these ask "Same as last time?" and show only what changed. Details are in `docs/charter.md` in the kit.
