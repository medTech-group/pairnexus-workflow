# pairnexus-workflow

A Claude Code kit for building software from a spec, attended or unattended:

**plan → spec → build tickets → one session per ticket → review panel → merge**

For unattended runs, a **conductor** asks the owner a few questions once (the **run charter**). It then builds every ready ticket in parallel sessions, merges what passes, releases if allowed, and reports, without waiting on anyone mid-run.

It packages what worked over the pair-drop weekend run of 9–12 Oct 2026 (about 50 tickets), with fixes for what didn't. pair-drop itself is set up with it (medTech-group/pair-drop#292).

## Getting started

Setting up a repository takes one Claude session and about ten minutes of your own clicks on GitHub and claude.ai. You do it once per repository. Moving to a later version of the kit is one request to Claude and a small pull request (see "Keeping it up to date").

### Before your first repository (once)

You need:

1. **Admin rights on the repository.** Rulesets and the merge settings are under the repository's Settings, which only admins see.
2. **Claude Code cloud sessions**, from the Claude desktop app (choose **Cloud** rather than **Local** when starting a session) or from claude.ai/code in a browser. Both start the same kind of session, on the same environments: an environment you create in one shows up in the other, and a session started in one can be followed in the other. Unattended runs and the set-up check need a cloud session. A local session can do the set-up itself, if the computer has Python 3.11 or later and `gh` signed in to GitHub.
3. **GitHub access for Claude.**
   - The Claude GitHub App is installed on the organisation, with access to the project's repository and to this one (`medTech-group/pairnexus-workflow`, which is private).
   - Your claude.ai account is connected to GitHub.
   - If a session can't reach a repository, it tells you which of these is missing.
4. **A paid GitHub plan** (Team or above) if the repository is private. Rulesets on private repositories need one. Without a ruleset, nothing outside the session stops a push straight to the base branch.

### Step 1. Ask Claude to set the repository up

1. Start a cloud session on the project's repository, in the Default environment:
   - **Desktop app:** start a new Code session, choose **Cloud**, pick the Default environment and the repository.
   - **Browser:** at claude.ai/code, pick the repository and the Default environment.
2. Send this message:

   > Set this repository up with the pairnexus workflow: clone https://github.com/medTech-group/pairnexus-workflow and follow `skills/setup-workflow/SKILL.md`.

   If Claude asks to add the kit's repository to the session, allow it. That is how a cloud session gets to read it.

Claude first explores the repository: its tests, CI and check names, deploy scripts, and any existing `.claude/` files. Then it asks only what it couldn't find out, with a recommended answer first. The questions you are most likely to get:

| Question | What it means, and the usual answer |
|---|---|
| Vendored or plugin? | **Vendored.** The kit is copied into the repository, so cloud sessions and unattended runs get it. |
| Your GitHub login | The person whose words count as approval in runs: you. |
| Can a PR merge with no human approval? | **Yes**, so unattended runs can merge. If your team requires an approval, runs stop at "ready for review". |
| Areas | The parts of the project two sessions shouldn't change at once, such as "backend", "phone app" or "infra". |
| Explorer | How reviewers try a change from outside: **browser** (a web app; Playwright), **api**, **cli**, or **none**. |
| Sensitive data | What must never appear in an issue, comment or PR, such as patients' names or phone numbers. |
| Deploys and releases | Which commands deploy. Ticket sessions are refused them, an attended session asks you first, and a run deploys only if you allow it when it starts. |
| Environment names | Two names, for example `myproject-ticket` and `myproject-conductor`. In step 5 you create environments with exactly these names. |
| Permission mode | How ticket sessions run: **auto**, so an unattended session never stops to ask. |

It may also ask about a project without CI, a monorepo, what a fresh container needs started (Docker, a database), and an older flow of the project's own.

Then Claude:
- **creates the workflow's labels** on the repository straight away (`ready-for-agent`, `workflow:run`, `workflow:stop` and others);
- **opens one pull request** containing:
  - the repository's settings: `.claude/workflow/profile.toml` and `profile.md`;
  - the kit's copy in `.claude/`, with its hooks;
  - a `workflow kit` CI check;
  - CODEOWNERS, issue templates, `docs/agents/` (how agents use the issue tracker and labels), `.gitignore` entries, and a short section in `CLAUDE.md`.

The PR body lists your one-time steps, filled in with this repository's check names, environment names and setup scripts. The steps below are the same ones, with every click.

### Step 2. Merge the pull request

1. Wait for its CI to go green.
2. Read it.
3. Click **Merge pull request** (a merge commit), then **Confirm merge**.

It changes `.claude/` and `.github/`, so merging it is always yours, never an agent's.

### Step 3. Protect the base branch with a ruleset

The ruleset is what really stops anyone, a session included, from pushing straight to the base branch or merging before CI is green. The kit's own guard is a seatbelt; the ruleset is the wall.

On GitHub, open the repository's **Settings → Rules → Rulesets → New ruleset → New branch ruleset**, and fill it in:

- **Ruleset name:** anything, for example `main`.
- **Enforcement status:** **Active**. "Disabled" and "Evaluate" enforce nothing.
- **Bypass list:** **leave it empty.** Sessions act through your GitHub account, so anything you can bypass, a session could bypass too.
- **Target branches:** **Add target → Include default branch**.
- **Rules**, tick:
  - **Restrict deletions**.
  - **Block force pushes**.
  - **Require a pull request before merging**:
    - **Required approvals: 0**, so unattended runs can merge.
    - **Require review from Code Owners: leave it unticked.** Sessions post under your GitHub account, and GitHub never lets an author approve their own PR, so with it ticked those PRs could never merge.
  - **Require status checks to pass**:
    - Tick **Require branches to be up to date before merging**. Without it, two PRs that each passed against an older base can both merge and break it together.
    - **Add checks:** every name in the PR body's list, `workflow kit` included. This is the profile's `ci.required_checks`. Type each name exactly; GitHub suggests names from recent runs.
- **Don't tick "Require linear history".** Sessions merge with a merge commit, which it forbids.
- Click **Create**.

### Step 4. Check the merge settings

Open the repository's **Settings → General** and scroll to **Pull Requests**:
- Tick **Allow auto-merge**.
- Keep **Allow merge commits** ticked. Sessions and the conductor always merge with a merge commit, so with it off every unattended merge fails.

### Step 5. Create the two Claude environments

An environment is the cloud machine a session runs on: its network access, environment variables, secrets and setup script. You pick one each time you start a session.

To create one:
- **Desktop app:** in a new Code session, open the environment dropdown in the prompt box and select **Cloud**, then **Add cloud environment**. To change one later, hover over it in the same list and click its gear icon.
- **Browser:** at claude.ai/code, open the cloud environment menu (where you pick an environment when starting a session, or in a running session's title bar) and choose **Add environment**. To change one later, choose it there and click **Edit**.

Either way it's the same environment, so create each one once.

**The ticket environment**, named exactly as in the profile's `run.ticket_environment` (for example `myproject-ticket`):
- **Environment variables:** only `WORKFLOW_ROLE=ticket`.
- **Secrets:** **none.** Leave **Network secrets** empty, and put no key or token in an environment variable: no cloud keys, no Auth0, Firebase or payment credentials, no deploy tokens. Tests use fakes, and a session can't misuse a key it doesn't have.
- **Network access:** the default is usually enough for package managers and container images. If a session later reports a blocked host, set Network access to **Limited** and add the host under **Allowed domains**, with **Allow package managers** left ticked.
- **Setup script:** paste the ticket environment's setup script from the PR body. It installs the project's dependencies, and Playwright's browser when the explorer is `browser`.

**The conductor environment**, named exactly as in the profile's `run.conductor_environment` (for example `myproject-conductor`):
- **Environment variables:** `WORKFLOW_ROLE=conductor`.
- **Secrets:** none, unless you want runs to release. Then add only what the release steps need.
- **Setup script:** the same as the ticket environment's. The conductor may fix a broken test or CI itself, and runs the project's tests before it opens that PR; it needs the project's dependencies for that, and for any release.

**Why the names must match.** The repository can't hold an environment's id, because ids belong to your Claude account. So the profile holds the names instead. At the start of a run, the conductor lists your environments, takes the one named `run.ticket_environment`, and starts every ticket session in it. If no environment has that name, the run stops before starting anything and says so. The name matters because of what that environment holds:
- **no credentials**;
- **`WORKFLOW_ROLE=ticket`**, which puts the guard in its strictest mode. A session can't change an environment variable from inside. Without it, the guard can only guess the role from the branch name, which a session can change.

**What's per repository:**

| | One per repository? | Why |
|---|---|---|
| Ticket environment | **Yes** | Its setup script installs that project's dependencies. |
| Conductor environment | **Usually yes** | It needs the project's dependencies (and its release secrets, if runs release). Only if you turn off the conductor's own fixes and releases in every run can repositories share one. |
| Ruleset | Yes | Each repository has its own check names. |
| Merge settings | Yes | Per-repository settings. |
| The kit | No | Built once, here. Each repository holds a pinned copy. |

### Step 6. Check it

In a **cloud** session on the repository (only cloud sessions can list your environments), ask:

> Check the workflow set-up: the ruleset, the merge settings and the two environments.

Claude checks:
- the ruleset, through GitHub's API: active, on the default branch, no bypass, deletions and force pushes blocked, every required check present, "up to date" ticked, Code Owners off, linear history off;
- that auto-merge and merge commits are allowed;
- that both environments exist, by name.

It can't see what an environment holds, so it asks you to confirm the ticket environment has no secrets.

The conductor checks the ruleset, CODEOWNERS and the ticket environment again at the start of every run. A missing ticket environment stops it. Any other gap it shows you, to fix first or to accept for that run.

### Using it

**Tickets.** Work lives in GitHub issues.
- A build ticket is an issue labelled `ready-for-agent`, written from the **Build ticket** template that set-up added. It has an `Area:`, what to build, acceptance criteria with where each is tested, and what blocks it.
- For larger work, ask Claude to write a spec with you ("write a spec for <feature>"). It publishes the spec, then splits it into build tickets. A very large effort can start as a map of decisions instead; `/next map` and `/next spec` then work through it.

**One piece at a time, with you there.**
1. In a session on the repository, type `/next`.
2. It picks the next ready piece of work and does it under the flow: claim, tests first, build, review panel, pull request, CI.
3. You merge the pull request.

To pick the work yourself, use `/next build`, or `/next 123` for a particular issue.

**Unattended.**
1. Start a cloud session on the repository (desktop app: **Cloud**; or claude.ai/code). Choose the **conductor environment**, and in the permission mode selector (beside the send button in the desktop app) choose **Auto**. A mode that asks before using tools would stall the run, and ticket sessions can't run in a more permissive mode than the conductor's.
2. Say:

   > Run the backlog unattended.

3. The conductor checks the set-up, then asks you the charter's questions in one sitting: which tickets, until when, how many at once (2 by default), what it may merge, and the like.
4. It shows you the plan and waits for your one "go".
5. It opens a **tracking issue** for the run (label `workflow:run`), with an issue for any by-hand checks linked from it.
6. From then on it runs without you; you can close the browser:
   - it starts a ticket session for each ready ticket in the ticket environment, as many at once as you allowed and at most one per area;
   - it checks in every 20 minutes by default, and merges what passes;
   - at the end it writes a report on the tracking issue.

While it runs:
- **To change the run,** comment on the tracking issue, for example "also #140" or "extend to Monday 9am". Only your own comments count (the GitHub login you gave in step 1). It reads them at the next check-in and replies to confirm.
- **To stop it,** add the label `workflow:stop` to the tracking issue: at its next check-in it stops the ticket sessions and writes the report. Or say "stop the run" in the conductor's session.

### Keeping it up to date

When the kit releases a new version, ask Claude in a session on the repository:

> Update the workflow kit: clone https://github.com/medTech-group/pairnexus-workflow and follow `skills/update-workflow/SKILL.md`.

It opens a pull request that replaces the kit's copy, keeping any edits the project made on purpose. Merge it like the set-up PR. The `workflow kit` CI check fails if anyone changes the copy without recording it, so the copy always matches a released version plus the project's recorded edits.

### Good to know

- **PRs that CI skips.** If the CI workflow skips some paths (`paths-ignore`, for docs-only changes say), a PR touching only those never gets its required checks, and with an empty bypass list it can't merge. Fix it in CI rather than in the ruleset: let each required job run on every PR and skip its own steps when nothing relevant changed, so the check still reports. Set-up notes such checks in the profile (`ci.path_filtered`), and a run hands those PRs to you.
- **Protected paths** (`.claude/`, `.github/workflows/`, CODEOWNERS, secrets files): ticket sessions can't change them. Any PR that does is yours to review and merge, and a ticket that needs one is filed as an owner task.
- **Read more:**
  - [docs/flow.md](docs/flow.md): the flow sessions follow;
  - [docs/charter.md](docs/charter.md): the run charter;
  - [docs/enforcement.md](docs/enforcement.md): what stops a session, and why;
  - [docs/install.md](docs/install.md): vendored and plugin modes.

## What's in it

| Part | What it does |
|---|---|
| `skills/setup-workflow` | Once per project: the interview, the profile, labels, CODEOWNERS, vendoring, the owner's one-time steps |
| `skills/next` | Find the next ready piece of work and do it under the flow |
| `skills/build-ticket` | One ticket from claim to merge |
| `skills/review-panel` | Standards, Spec, Correctness (with security) and a UI explorer, in parallel rounds until clean |
| `skills/conductor` | The unattended run: charter, sessions, check-ins, merges, release, stop |
| `skills/run-report` | The end-of-run report for the owner |
| `skills/update-workflow` | Update a project's vendored copy |
| `agents/` | The read-only Correctness reviewer and the UI explorer |
| `scripts/workflow.py` | The CLI the skills and hooks run: `profile`, `ready`, `charter`, `state`, `render`, `comments`, `evidence`, `repair`, `vendor`, `hook` |
| `hooks/` | Guard (the never-list), checklist gate, flow context, environment repair |
| `docs/` | `flow.md`, `charter.md`, `enforcement.md`, `install.md`, `spike.md` (what's verified), `proposal.md` (the design) |
| `templates/` | Profile, ticket-session briefing, tracking and by-hand issues, the `workflow kit` CI job |

Standards and Spec reviews, TDD, specs, tickets and maps come from [Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT), pinned in `.claude-plugin/marketplace.json` and installed alongside.

## Development

```bash
python3 -m pytest tests -q          # Python 3.11+, pytest
```

Every hook and script is tested with JSON fixtures, including attempts to get past the guard.

Releases are semver: `VERSION`, `.claude-plugin/plugin.json`, a `CHANGELOG.md` entry and a `v<version>` tag. Projects pin a release, and update with `update-workflow`.

## Licence

MIT (MedTech LLC): see `LICENSE`. The repository itself is private. The Matt Pocock skills keep their own MIT licence and notice: `THIRD_PARTY-mattpocock-skills.txt`.
