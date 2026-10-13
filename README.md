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

The PR body lists your one-time steps, filled in with this repository's check names, environment names and the environments' setup script (blank for most projects). The steps below are the same ones, with every click.

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
- **Setup script:** only what the PR body gives as the environments' setup script (the profile's `run.environment_setup`). **For most projects it is empty: leave the field blank.** See "What goes in the setup script" below.

**The conductor environment**, named exactly as in the profile's `run.conductor_environment` (for example `myproject-conductor`):
- **Environment variables:** `WORKFLOW_ROLE=conductor`.
- **Secrets:** none, unless you want runs to release. Then add only what the release steps need.
- **Setup script:** the same as the ticket environment's (often blank).

**What goes in the setup script.** Two different things get installed, at two different times:

| What | Example | Where it goes | When it runs |
|---|---|---|---|
| **Machine tools** the cloud image doesn't have | Flutter, the .NET SDK | The environment's **setup script** (the profile's `run.environment_setup`) | Once per environment, before Claude starts; the result is cached for later sessions |
| **The project's own dependencies** | `npm ci`, a Python virtualenv from `requirements.txt` | Nowhere you type: the profile's `commands.setup`, which the kit runs at the start of each cloud session when `commands.setup_check` says it's missing | Each new session, from the fresh clone |

The setup script runs before the repository is there, so it must never read the repository's files: one that does fails, and no session in that environment can start. The cloud image already has Python, Node.js, Java, Go, Rust, Ruby, PHP, Docker, PostgreSQL and Redis, so most projects need no setup script at all, whatever their stack:
- a Python API, or a Node.js app with or without a frontend: **blank**; the kit installs its packages;
- a project with no dependencies: **blank**, and `commands.setup` is empty too;
- a Flutter app: a script that downloads Flutter (pair-drop's is in its `docs/operations/workflow-setup.md`).

**Why the names must match.** The repository can't hold an environment's id, because ids belong to your Claude account. So the profile holds the names instead. At the start of a run, the conductor lists your environments, takes the one named `run.ticket_environment`, and starts every ticket session in it. If no environment has that name, the run stops before starting anything and says so. The name matters because of what that environment holds:
- **no credentials**;
- **`WORKFLOW_ROLE=ticket`**, which puts the guard in its strictest mode. A session can't change an environment variable from inside. Without it, the guard can only guess the role from the branch name, which a session can change.

**What's per repository:**

| | One per repository? | Why |
|---|---|---|
| Ticket environment | **No**, if the setup scripts match | It holds no project files: only `WORKFLOW_ROLE=ticket` and the machine tools. Repositories whose setup script is the same (most often blank) can share one; name it in each profile. |
| Conductor environment | **No**, likewise | Unless runs release: then it holds that project's release secrets, and gets its own. |
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

### Planning new work: from an idea to build tickets

The kit builds tickets. Turning an idea into those tickets (interviewing you, writing the spec, splitting it up) is done with [Matt Pocock's skills](https://github.com/mattpocock/skills), which set-up copies into every project's `.claude/skills/` beside the kit's own.

**Most of them are commands you type.** `/grill-with-docs`, `/to-spec`, `/to-tickets`, `/wayfinder` and the others marked "you type" below are set so Claude never starts them by itself. That's why they don't show up among the things Claude offers to do. Type the command at the start of your message.

**Where to run them:** in a session on the project's repository, with you there. That can be a local session, or a cloud session in your everyday environment. Not the ticket or conductor environment: their `WORKFLOW_ROLE` tells the guard the session is part of an unattended run. Planning is a conversation with you, so it never happens in an unattended run: the conductor only builds tickets that are already ready.

**The project's own rules apply.** The project's `CLAUDE.md` tells Claude to follow the kit's flow, and typing `/to-spec`, `/to-tickets`, `/wayfinder`, `/grill-with-docs`, `/triage`, `/implement` or `/implement-spec` also brings the flow into the conversation. That adds the kit's rules to what these commands publish (below).

#### Which way in

| Your situation | Start with |
|---|---|
| A feature or change you can describe in one sitting | `/grill-with-docs`, then `/to-spec`, then `/to-tickets` ([the main path](#the-main-path-step-by-step)) |
| A brand-new project, or a feature too big or too foggy for one session | `/wayfinder` ([a large effort](#a-large-or-brand-new-effort-wayfinder)) |
| A question only running code can answer: does this state model hold up, what should this screen look like | `/prototype`, as a side trip during the interview |
| Facts that live in documentation or a third party's API | `/research` |
| The answer is in someone else's head | `/to-questionnaire` |
| Bug reports and requests that arrive raw, from other people | `/triage` |
| Something is broken and you don't know why | `/diagnosing-bugs` |
| Not sure which | `/ask-matt` |

#### The main path, step by step

Keep steps 1 to 3 in **one session**, without `/clear` or `/compact` in between, so the spec and the tickets are written from everything said in the interview. If the conversation gets very long before the tickets are out, finish the step you're on and ask Claude how best to carry on.

**1. `/grill-with-docs`: the interview.** Type the command and the idea in a sentence or two:

> /grill-with-docs Patients should be able to export all their records as one PDF to give a new doctor.

Claude interviews you in **rounds**:
- Each round asks every question that can be answered now: the ones that don't wait on another open answer. They're numbered, and each comes with Claude's recommended answer, worded so that "yes" accepts it.
- Answer the whole round in one message. For example:

  > Q1 yes. Q2 no: only Documents, not Readings. Q3 yes, but in Hindi too. Q4 I don't know, what do you suggest?

- Your answers open the next round. It goes on until no decision is left unasked; then Claude checks you agree it has understood, and does nothing more until you say so.
- **Facts are Claude's job, decisions are yours.** Anything it can find out (how the code works now, what a library allows) it looks up itself, often in the background, rather than asking you.
- **It keeps the project's language straight.** When a word you use clashes with the project's glossary (`GLOSSARY.md`, or whatever name the project uses) it asks which you mean. It adds terms to the glossary as they're settled, and records a decision that would be hard to reverse as a short ADR in `docs/adr/`. Those files are written in the session; commit them with the spec's pull request, or ask Claude to.

`/grill-me` is the same interview, but it writes nothing down. Use it to think something through away from a repository (a plan, a pitch); in a project, use `/grill-with-docs`.

**2. `/to-spec`: the spec.** Type `/to-spec` in the same session. It asks you nothing new: it writes up what the interview settled.
- It reads the code, then proposes **where the tests will plug in** (the "seams": as few as possible, as high up as possible, existing ones first) and **asks you to confirm them**. Ticket sessions later build test-first at exactly those seams.
- It publishes the spec as a GitHub issue, with these sections:
  - Problem Statement;
  - Solution;
  - User Stories (a long, numbered list);
  - Implementation Decisions;
  - Testing Decisions;
  - Out of Scope;
  - Further Notes.
- Under the kit's flow, it labels the spec `ready-for-agent` and `spec`, so the readiness check never takes the spec itself for a build ticket, and it cites the decision behind each choice.

**3. `/to-tickets`: the build tickets.** Type `/to-tickets`, or `/to-tickets #<spec number>` in a new session.
- It splits the spec into **thin end-to-end slices**: each works through every layer it touches (data, API, screen, tests) and can be checked on its own, rather than one layer at a time. Any tidying the code needs first comes first.
- It shows you the list (each ticket's title, what blocks it, and what it delivers) and asks whether the size is right, whether the blocking is right, and whether any should be merged or split. It changes the list until you approve it.
- It publishes them in order, blockers first, each linked to what blocks it.
- **The kit's flow adds to each build ticket:**
  - a written `## Blocked by` section, as well as GitHub's own links, so a blocker closed as "not planned" is still seen;
  - an `Area:` line from the profile, so an unattended run never runs two sessions on the same area at once;
  - acceptance criteria that name where each is tested;
  - the checks only a person can do (a real phone, a real account), if any.
- **Things only you can do** (create an account, a key, a domain) become their own issues labelled `owner-task`, blocking the tickets that need them. So does any change to a protected path (the kit, CI config, CODEOWNERS): a ticket session can't make those.
- A ticket that fixes a failing or flaky required check is also labelled `workflow:infra`, so it's built first.

**4. Build.** The tickets are now `ready-for-agent`:
- `/next` builds the next one with you there, or `/next 123` a particular one;
- or start an unattended run, which builds them all ([Using it](#using-it)).

Before building, you can edit any spec or ticket on GitHub like any issue.

Matt Pocock's own builders, `/implement` (one ticket) and `/implement-spec` (a whole spec on one branch), are in the project too. Under the kit's flow, typing either builds the kit's way, one ticket at a time with `build-ticket`: the review panel, the pull request with its findings, CI and the merge rule. So `/next` is the simpler way to start.

#### A large or brand-new effort: `/wayfinder`

When the work is too big for one session, or too unclear to spec yet, chart it first as a **map**: one GitHub issue (label `wayfinder:map`) whose child issues are the **decisions** to make on the way. Nothing is built while the map is open.

**Chart the map** (one session):

> /wayfinder A clinic queue app: patients join from their phone, staff call them in.

1. Claude interviews you about the **destination**: what reaching the end looks like (usually a spec ready to build).
2. A second, wider round finds the open questions across the whole effort and the first steps that can be taken now.
3. It creates the map issue with these sections:
   - **Destination**;
   - **Notes**;
   - **Decisions so far** (empty to start);
   - **Not yet specified**: what's visible but not yet sharp enough to ask;
   - **Out of scope**.
4. It creates a child issue for each question it can already state, wired with what blocks what. Each is labelled with its kind:
   - `wayfinder:grilling`: a conversation with you; the default;
   - `wayfinder:research`: reading documentation or an API, done by Claude alone;
   - `wayfinder:prototype`: a rough, throwaway thing to react to;
   - `wayfinder:task`: something that has to be done before a decision can be made, like signing up for a service to try its API.
5. It starts the research questions straight away in the background, and stops: charting resolves nothing itself.

**Work through it**, **one decision per session** (research questions excepted):

> /next map

or `/wayfinder <map link>`. Claude:
1. takes the first decision whose blockers are settled, and assigns it to you so no other session takes it;
2. settles it as its kind says: an interview with you, a prototype you react to, research, or a task;
3. writes the answer as a comment, closes the issue, and adds one line to the map's "Decisions so far";
4. opens new decision issues as answers make them clear, moving each from "Not yet specified" as it does.

Several decisions that don't block each other can be worked in parallel sessions.

**From map to tickets.** When the map has no open decisions and nothing left under "Not yet specified", it's clear:
- `/next spec` picks its first Destination item without a spec, and writes that spec from the map's decisions, then its tickets (steps 2 and 3 above, with the same seam check and ticket review with you).
- **The kit's gate:** none of a map's build tickets is built until every Destination item of that map has its spec and its tickets, so building never starts on half a plan.

**A brand-new project.** Create the GitHub repository (a README is enough) and set it up with the kit first ([Step 1](#step-1-ask-claude-to-set-the-repository-up)), so the skills, labels and issue templates are there. With no code yet, set-up records no test commands and no CI. The first build tickets create them; then ask Claude to add them to `.claude/workflow/profile.toml` (a protected path, so that pull request is yours to merge). Then start with `/wayfinder`, or `/grill-with-docs` if the first piece is small.

#### Side trips while planning

- **`/prototype`**: throwaway code that answers one question.
  - A **logic** prototype: a single HTML file that pushes a state model through hard cases you can click through.
  - A **UI** prototype: several very different versions of one screen, switchable in the browser.

  When it has answered the question, the answer goes into the decisions, and the prototype is kept on a branch for reference. To run one apart from the interview, the usual way is: `/handoff` to write the context to a file, prototype in a fresh session, then `/handoff` back what you learned.
- **`/research <question>`**: a background agent reads the primary sources (official docs, source code, specs) and leaves a Markdown file in the repository, citing each claim. You keep talking meanwhile; its findings feed the interview.
- **`/to-questionnaire`**: when someone else holds the answer (a clinician, a vendor, legal). It asks you only who it's for and what you need back, then writes them a questionnaire to fill in, most important question first.
- **`/wait-what`**: Claude's last message didn't make sense. It says it again, plainly, with the context you were missing.
- **`/handoff`**: writes the conversation so far to a file a fresh session (or a colleague) can pick up.

#### Every Matt Pocock skill in a project

"You type" means a slash command Claude never starts on its own. "Claude, when needed" means Claude also uses it by itself when the work calls for it, and you can still type it.

| Skill | Who starts it | What it's for | With the kit |
|---|---|---|---|
| `/ask-matt` | You type | Which skill fits your situation | |
| `/grill-with-docs` | You type | The interview, writing the glossary and ADRs as it goes | Step 1 of planning |
| `/grill-me` | You type | The same interview, writing nothing | Away from a repository |
| `/grilling` | Claude, when needed | The interview itself, which the two above and `/wayfinder` and `/triage` run | |
| `/domain-modeling` | Claude, when needed | Keeps the glossary and ADRs; challenges fuzzy or clashing words | Runs inside `/grill-with-docs` |
| `/to-spec` | You type | The interview written up as a spec issue | Labelled `spec` and `ready-for-agent` |
| `/to-tickets` | You type | A plan or spec split into build tickets | With the kit's Area, Blocked by and owner tasks |
| `/wayfinder` | You type | A map of decisions for a large or foggy effort | `/next map` and `/next spec` work it |
| `/to-questionnaire` | You type | Questions for someone else to answer | |
| `/prototype` | Claude, when needed | Throwaway code that answers a design question | |
| `/research` | Claude, when needed | A background agent reads primary sources, writes a cited note | |
| `/triage` | You type | Sorts raw bug reports and requests into `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human` or `wontfix`, with a brief for the agent | Not for tickets `/to-tickets` made: they're ready already |
| `/diagnosing-bugs` | Claude, when needed | Hard bugs: gets a command that fails on this bug before theorising, then fixes it with a test | |
| `/tdd` | Claude, when needed | Builds test-first, one red-to-green step at a time | Every ticket session uses it |
| `/code-review` | Claude, when needed | Standards and Spec reviews of a change | Part of the review panel |
| `/implement` | You type | Builds one ticket | Built the kit's way (`build-ticket`); `/next` is simpler |
| `/implement-spec` | You type | Builds a whole spec on one branch with parallel agents | Built the kit's way, one ticket at a time; or use an unattended run |
| `/pr` | Claude, when needed | Writes a pull request's description | |
| `/resolving-merge-conflicts` | Claude, when needed | Works through a merge or rebase conflict | |
| `/codebase-design` | Claude, when needed | The words for designing a module: depth, interface, seam | |
| `/improve-codebase-architecture` | You type | Finds places the code could be simpler for agents to work in, as an HTML report, then interviews you about the one you pick | Its outcome is a new idea for step 1 |
| `/retro` | You type | Looks back at a session and suggests changes to the setup, not the code | |
| `/handoff` | You type | The conversation written to a file for another session | |
| `/wait-what` | You type | Re-explains a message that didn't land | |
| `/teach` | You type | Learn a concept over several sessions, in a folder | |
| `/wizard` | Claude, when needed | A script that walks a person through steps only they can do (a dashboard, credentials) | Handy for owner tasks |
| `/writing-for-agents` | Claude, when needed | How to write skills and `CLAUDE.md` | |
| `/setup-matt-pocock-skills` | You type | Configures the issue tracker, labels and glossary location | **Don't run it**: the kit's set-up already did this |

### Using it

**Tickets.** Work lives in GitHub issues.
- A build ticket is an issue labelled `ready-for-agent`, written from the **Build ticket** template that set-up added. It has an `Area:`, what to build, acceptance criteria with where each is tested, and what blocks it.
- For new work, plan it with Claude first: `/grill-with-docs`, `/to-spec`, `/to-tickets`, or `/wayfinder` for a large effort. See [Planning new work](#planning-new-work-from-an-idea-to-build-tickets).

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

Standards and Spec reviews, TDD, the planning interview, specs, tickets and maps come from [Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT), pinned in `.claude-plugin/marketplace.json` and copied into each project alongside the kit's own (they aren't in this repository). [Planning new work](#planning-new-work-from-an-idea-to-build-tickets) lists every one and how it fits.

## Development

```bash
python3 -m pytest tests -q          # Python 3.11+, pytest
```

Every hook and script is tested with JSON fixtures, including attempts to get past the guard.

Releases are semver: `VERSION`, `.claude-plugin/plugin.json`, a `CHANGELOG.md` entry and a `v<version>` tag. Projects pin a release, and update with `update-workflow`.

## Licence

MIT (MedTech LLC): see `LICENSE`. The repository itself is private. The Matt Pocock skills keep their own MIT licence and notice: `THIRD_PARTY-mattpocock-skills.txt`.
