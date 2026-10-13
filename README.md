# pairnexus-workflow

A Claude Code kit for building software from a spec, attended or unattended:

**plan → spec → build tickets → one session per ticket → review panel → merge**

You don't need to remember its commands: start a session and say what you're working on, and Claude asks what to do next with choices to click ([Using it](#using-it)).

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

> [!IMPORTANT]
> **These two environments are for unattended runs only.** You start the conductor's sessions; the conductor starts the ticket sessions. **For planning, and for building a ticket with you there, use the Default environment** (or any environment without `WORKFLOW_ROLE`). See [Plan in one session, build in another](#plan-in-one-session-build-in-another).

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

### Using it

> [!IMPORTANT]
> #### Plan in one session, build in another
>
> **Which environment you start a session in decides what it does.** Pick the right one every time:
>
> | You want to | Start a session in | Then |
> |---|---|---|
> | **Plan:** tell Claude what you found, settle decisions, write specs and tickets | **the Default environment** (any environment **without `WORKFLOW_ROLE`**), or a local session | Say what you have in mind. Claude asks with choices and publishes the specs and tickets on GitHub |
> | **Build the tickets unattended** | **the conductor environment** (for example `myproject-conductor`), permission mode **Auto** | Say **"Run the backlog unattended"**. It asks its questions once, then starts every ticket session itself |
> | **Build one ticket with you there** | the Default environment, as for planning | Type **`/next build`**. You merge its pull request |
>
> - **Never start a session in the ticket environment yourself.** The conductor starts those, one per ticket.
> - **Never plan in the ticket or conductor environment.** Their `WORKFLOW_ROLE` tells the kit the session is part of an unattended run: it asks you nothing, follows a ticket session's or the conductor's rules, and the guided start never shows.
> - Planning and building can be days apart: everything waits on GitHub in between.

#### Start a session and say what you're working on

You don't need to remember any command. Start a session on the repository and say what you have in mind, or just "hi": Claude works out what to do, asks with choices to click when there's something to choose, and offers each next step the same way until the work is done. This is the kit's **guided start** (the `start` skill).

**Where:** a session on the repository, with you there:
- a local session;
- or a cloud session in the **Default environment** (any environment without `WORKFLOW_ROLE`), on a branch not named `claude/build-…`.

Not the ticket or conductor environment, and not a `claude/build-…` branch. There the session counts as part of an unattended run:
- the guard holds it to a ticket session's rules;
- pushes go only to `claude/build-…` branches;
- every turn has to end with a `WORKFLOW-STATUS` line;
- and there is no menu.

**What happens with your first message:**

| You type | Claude |
|---|---|
| Something clear: a question, "build #262", "rename the Save button to Done" | Does it. No menu. |
| Work to plan, one thing or several: "add refill reminders, and the reminders screen needs changing because testers found it confusing" | Splits it into items and proposes a path for each (below) |
| Anything vaguer: "hi", "let's work on pair-drop", or `/start` | Looks at the project and asks "What are we working on?" |
| A command, such as `/next` or `/grill-me` | Runs that command, with no menu |

`/start` brings the menu back at any time (in plugin mode, `/pairnexus-workflow:start`). To turn the first-message menu off for a project, set `guided_start = false` in the profile's `[project]`; `/start` still works.

**Looking around.** First, Claude runs `workflow status`, which reads the project's issues and pull requests. Then it tells you, in a few lines, what matters:
- a pull request waiting for your merge;
- an unattended run in progress;
- items left from your last session;
- tickets ready to build;
- new issues nobody has sorted;
- whether the project is brand new.

Then it asks **What are we working on?**, with up to four of these:
- **Carry on:** the most pressing item: a planned item, a map decision, a ready ticket or your PR;
- **Something new, or a change to what's there**;
- **Fix something that's broken**;
- **Sort the new issues**;
- **A brand-new project or a large effort** (recommended when the project has no code yet);
- **Run the ready tickets unattended**.

"Other" is always there, for your own words.

**Splitting a request into items.** Say several things at once, as you would to a colleague. Claude lists each as an item, looks at the code each one touches, and proposes a path for it:

| Path | For | What happens |
|---|---|---|
| **Quick ticket** | Small and clear, nothing to decide: a wording, a small tweak, a bug whose cause is known | One build ticket, written and built |
| **Find the cause first** | Something broken, nobody knows why | Claude reproduces it until a command fails on the bug, then a quick ticket (or a spec, if the fix needs decisions) |
| **Spec** | A feature, or a change with decisions in it | The interview, the spec, then its build tickets |
| **Map** | Too big or too unclear for one sitting, or a brand-new project | A map of decisions, one per session |
| **Add to an existing issue** | It changes something planned but not yet built | That spec or ticket is edited with you |

Each item is a question: Claude's recommended path first, with why, and **Spec** always offered as well. A spec takes longer, but nothing is assumed. Then it proposes an order:
1. what the others depend on;
2. then what hurts users now;
3. then the rest, in the order you gave.

You can say **Go**, **Change the order** or **Change an item's path**.

When you say go, each item is filed as a GitHub issue in your words, ending with a hidden marker (`<!-- workflow:item path=spec -->`). Nothing is lost if the session ends: the next session's first message offers "Carry on: #302".

**An example.** You type:

> I tested the app. Patients should get a reminder to refill a medicine before it runs out. And the reminders screen confuses people: they don't see which medicines are due.

Claude replies with two items and asks about each:

- *"Refill reminders: which way?"*
  - **Spec (Recommended):** "how many days ahead, worked out from what, and for which medicines: decisions to make";
  - **Map**.
- *"Reminders screen doesn't show what's due: which way?"*
  - **Quick ticket (Recommended):** "the screen has the medicines already; it's how they're shown";
  - **Spec**.

Then *"Go with this plan? 1. Reminders screen (quick ticket) 2. Refill reminders (spec)"*. You click **Go**. It files #301 and #302, writes the reminders ticket, shows it to you, publishes it on your click, and asks **Build it now**, **Leave it ready for later** or **Next item**.

**At every handover, a choice:**

| After | You're offered |
|---|---|
| The interview | **Write the spec**, **There's more to discuss**, **Stop here** |
| The spec | **Split it into tickets**, **Edit the spec first**, **Stop here** |
| The tickets | **Build them in a fresh session**, **Run them unattended**, **Next item of the plan** (when it's light), **Stop here** |
| Charting a map | **Stop here: the first decision in a fresh session**, **Next item of the plan** (when it's light) |
| A light item (a quick ticket published, an edit to an issue) | **Next: <the next item>**, **Start it in a fresh session**, **Stop here** |

"Stop here" leaves everything on GitHub, so the next session picks it up.

**Changing course.** Say so in your own words at any point:
- **"That's enough, write it up"** ends an interview. Anything still open goes into the spec as an open question.
- **"Drop that one"** closes its issue as not planned.
- **"Do that one first"** reorders the plan.
- **A spec or ticket already published:**
  - edit it on GitHub, or ask Claude to;
  - remove its `ready-for-agent` label to stop `/next` and runs taking it;
  - close it as not planned to drop it.
- **A map decision to redo:** reopen it.

**Long sessions.** A session's context holds about 150,000 tokens comfortably. Keep one item's interview, spec and tickets in one session where you can. When it gets long, Claude recommends carrying on in a fresh session, since everything is on GitHub. In the middle of an item, finish the step you're on, then type `/compact`, or start fresh with `/to-tickets #<spec>`.

How long each takes, roughly:
- a quick ticket: minutes;
- an interview: several rounds of questions;
- a map: one session per decision, so many sessions over days.

#### One piece at a time: `/next`

`/next` skips the menu and does the next ready piece of work under the flow:
- with no argument, a map decision first, then a clear map's next spec, then a build ticket;
- `/next build` for the next build ticket;
- `/next map` or `/next spec`;
- `/next 123` for a particular issue.

Building a ticket follows the kit's flow: claim, tests first, the review panel in rounds, a pull request with its findings, CI. You merge the pull request.

#### Unattended

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

A run only builds tickets that are ready: planning is a conversation with you, so it never happens in a run. While a map still has Destination items without a spec, the conductor's kick-off lists that map's ready tickets and recommends leaving them out (see [the gate](#a-large-or-brand-new-effort-wayfinder)).

### Planning new work: what happens underneath

The guided start runs these for you. This section is for when you want to know what each step does, or to type a step's command yourself.

Planning uses [Matt Pocock's skills](https://github.com/mattpocock/skills). In vendored mode, set-up copies them into the project's `.claude/skills/` beside the kit's own. In plugin mode they come with the plugin, and their commands are prefixed, such as `/mattpocock-skills:to-spec`.

**Most of them are commands you type.** `/grill-with-docs`, `/to-spec`, `/to-tickets`, `/wayfinder` and the others marked "You type" below never start by themselves when Claude judges them useful. Two things start them:
- you typing the command;
- the guided start, which reads their instructions and follows them for you.

**The project's own rules apply.** The project's `CLAUDE.md` tells Claude to follow the kit's flow. Typing `/to-spec`, `/to-tickets`, `/wayfinder`, `/grill-with-docs`, `/triage`, `/implement` or `/implement-spec` also brings the flow into the conversation, which adds the kit's rules to what these commands publish.

#### Which command, if you type them yourself

| Your situation | Start with |
|---|---|
| A feature or change you can describe in one sitting | `/grill-with-docs`, then `/to-spec`, then `/to-tickets` ([the main path](#the-main-path-step-by-step)) |
| A brand-new project, or a feature too big or too foggy for one session | `/wayfinder` ([a large effort](#a-large-or-brand-new-effort-wayfinder)) |
| A question only running code can answer: does this state model hold up, what should this screen look like | `/prototype`, as a side trip during the interview |
| Facts that live in documentation or a third party's API | `/research` |
| The answer is in someone else's head | `/to-questionnaire` |
| Bug reports and requests that arrive raw, from other people | `/triage`, or the guided start's "Sort the new issues" |
| Something is broken and you don't know why | `/diagnosing-bugs` |
| Not sure which | `/start` |

#### The main path, step by step

Keep steps 1 to 3 in **one session** where you can, so the spec and the tickets are written from everything said in the interview (see "Long sessions" above for when it gets long).

**1. `/grill-with-docs`: the interview.** Type the command and the idea in a sentence or two:

> /grill-with-docs Patients should get a reminder to refill a medicine before it runs out.

Claude interviews you in **rounds**:
- Each round asks every question that can be answered now: the ones that don't wait on another open answer. Each comes with Claude's recommended answer. Typed as a command, the questions are numbered and worded so that "yes" accepts the recommendation; the guided start asks them as choices to click, recommendation first.
- Answer the whole round in one message. For example:

  > Q1 yes. Q2 no: only medicines they take every day. Q3 yes, but 5 days ahead, not 3. Q4 I don't know, what do you suggest?

- Your answers open the next round. It goes on until no decision is left unasked; then Claude checks you agree it has understood, and does nothing more until you say so.
- **Facts are Claude's job, decisions are yours.** Anything it can find out (how the code works now, what a library allows) it looks up itself, often in the background, rather than asking you.
- **It keeps the project's language straight.** When a word you use clashes with the project's glossary (`GLOSSARY.md`, or whatever name the project uses), it asks which you mean, and adds terms to the glossary as they're settled. When a decision is hard to reverse, surprising, and a real trade-off, it offers to record it as a short ADR in `docs/adr/`.
- **Those files are only in the session's working tree.** Before the session ends, or you stop, Claude commits them to a branch of their own and opens a pull request for you to merge; the flow's checklist has the step. A cloud session's files are gone when it ends.

`/grill-me` is the same interview, but it writes nothing down. Use it to think something through away from a repository (a plan, a pitch); in a project, use `/grill-with-docs`.

**2. `/to-spec`: the spec.** Type `/to-spec` in the same session. It doesn't interview you again: it writes up what the interview settled. The one thing it asks is to confirm the seams.
- It reads the code, then proposes **where the tests will plug in** (the "seams": as few as possible, as high up as possible, existing ones first). Ticket sessions later build test-first at exactly those seams.
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
- `/next build` builds the next one with you there, or `/next 123` a particular one;
- or start an unattended run, which builds them all ([Unattended](#unattended)).

Before building, you can edit any spec or ticket on GitHub like any issue.

**Use `/next` or a run, not `/implement` or `/implement-spec`.** Matt Pocock's own builders are in the project too, but they work differently:
- `/implement` commits to the current branch, with no pull request or review panel;
- `/implement-spec` runs parallel builders onto one branch.

If you type either, the flow tells Claude to build with the kit's `build-ticket` instead, one ticket at a time.

**Sorting incoming issues with `/triage`.** It sorts raw reports into `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human` or `wontfix`. Under the kit's flow, an issue it makes `ready-for-agent` must first get the build ticket's `## Blocked by`, `Area:` and acceptance criteria. Its own agent brief has none of them, and the readiness check doesn't refuse a ticket without an area. The guided start's "Sort the new issues" does this for you.

#### A large or brand-new effort: `/wayfinder`

When the work is too big for one session, or too unclear to spec yet, chart it first as a **map**: one GitHub issue (label `wayfinder:map`) whose child issues are the **decisions** to make on the way.

**Chart the map** (one session):

> /wayfinder A clinic queue app: patients join from their phone, staff call them in.

1. Claude interviews you about the **destination**: what reaching the end looks like. It can be several items, each needing its own spec (for example "patients join the queue" and "staff call them in").
2. A second, wider round finds the open questions across the whole effort and the first steps that can be taken now. If it finds nothing unclear, no map is needed: it stops and asks how you want to go on (usually straight to a spec).
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

**Work through it**, **one decision per session** (research questions excepted). Use `/next map`, or `/wayfinder <map link>`, or the guided start's "Carry on". Claude:
1. takes the first decision whose blockers are settled, and claims it (the `workflow:in-progress` label, and assigned to you), so no other session takes it;
2. settles it as its kind says: an interview with you, a prototype you react to, research, or a task;
3. writes the answer as a comment, closes the issue, and adds one line to the map's "Decisions so far";
4. opens new decision issues as answers make them clear, moving each from "Not yet specified" as it does;
5. commits any glossary or ADR change to a branch and offers you a pull request; research notes stay on their own `research/…` branch, linked from the decision, never merged.

Several decisions that don't block each other can be worked in parallel sessions.

**From map to tickets.** When the map has no open decisions and nothing left under "Not yet specified", it's clear:
- `/next spec` takes its first Destination item without a spec, one per session. It writes that spec from the map's decisions, then its tickets (steps 2 and 3 above, with the same seam check and ticket review with you).
- **The gate:** none of a map's build tickets should be built until every Destination item of that map has its spec and its tickets, so building never starts on half a plan.
  - `/next` and the guided start keep to it.
  - `workflow ready` doesn't know about maps, so a run would build them. At a run's kick-off the conductor lists such tickets and recommends leaving them out.
  - Or simply start the run once every Destination item has its tickets.

**A brand-new project.** In this order:
1. **Create the GitHub repository,** with a README. If the Claude GitHub App has access only to selected repositories, add this one ([Before your first repository](#before-your-first-repository-once), item 3).
2. **Set it up with the kit** ([Step 1](#step-1-ask-claude-to-set-the-repository-up) to Step 6).
   - With no code yet, set-up records no test commands.
   - Unless the repository has CI, it sets `ci.none = true`. Its only required check is then `workflow kit`, the kit's own job, which checks the kit's copy, not your code.
   - For areas, answer with the parts you expect (directories still to come are fine) or none; you can add them to the profile later.
3. **Plan.** Start a session: the guided start sees a brand-new project and recommends a map (or a spec, for something small).
4. **Build the first ticket with you there:** the project's skeleton, its test runner and a first test. Use `/next build`, and merge it yourself. It can't be unattended:
   - with `ci.none`, the merge rule needs the full suite's result posted from the session (`workflow evidence`);
   - until the profile names a suite, there is none to run.

   So expect this one ticket's session to say it found no suite or typecheck in the profile and couldn't post the suite's evidence. It runs the new tests directly instead, and you merge on what it shows you.
5. **One owner pull request** for the test set-up. In an attended session, ask Claude to:
   - add the suite, typecheck and setup commands to `.claude/workflow/profile.toml`;
   - add a CI workflow in `.github/workflows/` that runs them;
   - set `ci.none = false`, and add the new check names to `ci.required_checks`.

   Both are protected paths: Claude asks you before each change, and the pull request is yours to merge. A build ticket can't make them, so this is never a ticket.
6. **Add the new check names to the ruleset** ([Step 3](#step-3-protect-the-base-branch-with-a-ruleset)).
7. **Only then run tickets unattended.**

#### Side trips while planning

- **`/prototype`**: throwaway code that answers one question.
  - A **logic** prototype: a single HTML file that pushes a state model through hard cases you can click through.
  - A **UI** prototype: several very different versions of one screen, switchable in the browser.

  When it has answered the question, the answer goes into the decisions, and the prototype is kept on a branch for reference.
- **`/research <question>`**: a background agent reads the primary sources (official docs, source code, specs) and leaves a Markdown file in the repository, citing each claim. You keep talking meanwhile; its findings feed the interview. It is kept on a `research/…` branch, linked from the issue it answers, and never merged.
- **`/to-questionnaire`**: when someone else holds the answer (a clinician, a vendor, legal). It asks you only who it's for and what you need back, then writes them a questionnaire to fill in, most important question first. It writes `to-questionnaire-<slug>.md` in the repository's root; you send it yourself. In a cloud session, ask Claude to print it before the session ends: the file is gone with the machine.
- **`/wait-what`**: Claude's last message didn't make sense. It says it again, plainly, with the context you were missing.
- **`/handoff`**: writes the conversation so far to a file another session can pick up.
  - It saves to the machine's temporary directory, not the repository.
  - On your own computer, a local session can read it.
  - A fresh cloud session can't: it runs on another machine. In the cloud, ask Claude to print the handoff and paste it into the new session, or to commit it to a branch.
  - With the guided start you rarely need it: the plan, specs and decisions are on GitHub.

#### Every Matt Pocock skill in a project

"You type" means a slash command Claude never starts on its own judgement; the guided start may still follow its instructions for you when you choose that step. "Claude, when needed" means Claude also uses it by itself when the work calls for it, and you can still type it. In plugin mode, type them with the plugin's prefix, such as `/mattpocock-skills:to-spec`.

| Skill | Who starts it | What it's for | With the kit |
|---|---|---|---|
| `/ask-matt` | You type | Which skill fits your situation | `/start` covers most of it |
| `/grill-with-docs` | You type | The interview, writing the glossary and ADRs as it goes | Step 1 of planning |
| `/grill-me` | You type | The same interview, writing nothing | Away from a repository |
| `/grilling` | Claude, when needed | The interview itself, which the two above, `/wayfinder`, `/triage` and `/improve-codebase-architecture` run | |
| `/domain-modeling` | Claude, when needed | Keeps the glossary and ADRs; challenges fuzzy or clashing words | Runs inside `/grill-with-docs` |
| `/to-spec` | You type | The interview written up as a spec issue | Labelled `spec` and `ready-for-agent` |
| `/to-tickets` | You type | A plan or spec split into build tickets | With the kit's Area, Blocked by and owner tasks |
| `/wayfinder` | You type | A map of decisions for a large or foggy effort | `/next map` and `/next spec` work it |
| `/to-questionnaire` | You type | Questions for someone else to answer, as a file in the repository's root | |
| `/prototype` | Claude, when needed | Throwaway code that answers a design question | |
| `/research` | Claude, when needed | A background agent reads primary sources, writes a cited note | |
| `/triage` | You type | Sorts raw bug reports and requests into `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human` or `wontfix`, with a brief for the agent | A ticket it readies gets `Area:` and `## Blocked by` first |
| `/diagnosing-bugs` | Claude, when needed | Hard bugs: gets a command that fails on this bug before theorising, then fixes it with a test | The guided start's "Find the cause first" |
| `/tdd` | Claude, when needed | Builds test-first, one red-to-green step at a time | Every ticket session uses it |
| `/code-review` | Claude, when needed | Standards and Spec reviews of a change | Part of the review panel |
| `/implement` | You type | Builds one ticket, committing to the current branch | Not recommended: use `/next build` |
| `/implement-spec` | You type | Builds a whole spec on one branch with parallel agents | Not recommended: use an unattended run |
| `/pr` | Claude, when needed | Writes a pull request's description | |
| `/resolving-merge-conflicts` | Claude, when needed | Works through a merge or rebase conflict | |
| `/codebase-design` | Claude, when needed | The words for designing a module: depth, interface, seam | |
| `/improve-codebase-architecture` | You type | Finds places the code could be simpler for agents to work in, then interviews you about the one you pick | Its HTML report goes to the machine's temporary directory and opens in a browser, so run it in a local session; its outcome is a new item to plan |
| `/retro` | You type | Looks back at a session and suggests changes to the setup, not the code | |
| `/handoff` | You type | The conversation written to a file for another session | Saved to the temporary directory: see [Side trips](#side-trips-while-planning) |
| `/wait-what` | You type | Re-explains a message that didn't land | |
| `/teach` | You type | Learn a concept over several sessions, in a folder | It writes its lessons in the current directory, so run it outside the project |
| `/wizard` | Claude, when needed | A script that walks a person through steps only they can do (a dashboard, credentials) | Handy for owner tasks |
| `/writing-for-agents` | Claude, when needed | How to write skills and `CLAUDE.md` | |
| `/setup-matt-pocock-skills` | You type | Configures the issue tracker, labels and glossary location | **Don't run it**: the kit's set-up already did this. If `/to-spec` or `/to-tickets` tells you to run it, `docs/agents/` is missing: usually the set-up pull request isn't merged yet |

### Keeping it up to date

**Versions.** The kit is released as numbered versions (`0.1.5`): each is a tag (`v0.1.5`) and a GitHub release on [the Releases page](https://github.com/medTech-group/pairnexus-workflow/releases), with what changed. The kit's `release` workflow tags and publishes each version when it lands on `main`. A project holds a pinned copy of one release, recorded in its `.claude/workflow/lock.json`, and moves to a newer one only through a pull request you merge.

**You're told when a newer release is out, three ways:**

| Where | What you see | What to do |
|---|---|---|
| **A session you start** (the guided start) | **"Update the workflow kit to 0.1.5 (Recommended)"** as the first choice | Click it. Claude opens the update pull request; you merge it |
| **An unattended run's kick-off** | **Update first** or **Run on 0.1.4** | Update first: the run ends, you update in a session of your own, then start the run again. A run never changes version midway, and its ticket sessions never update |
| **The weekly check** (a GitHub Action set-up adds) | An issue, **"Workflow kit update: 0.1.4 → 0.1.5"**, with the release's notes; closed once you've updated | Start a session and choose the update, or say "Update the workflow kit" |

**Nothing updates by itself.** The kit is what guards your sessions, so a new version always arrives as a pull request you read and merge, never swapped in by a session: a ticket session that could rewrite its own guard would defeat it, and the `workflow kit` CI check refuses a copy that wasn't recorded through an update. The weekly check opens an issue rather than the pull request, because a pull request opened by a GitHub Action's own token never runs your CI.

**To update by hand,** in a session on the repository (the Default environment):

> Update the workflow kit.

Claude clones the kit at the latest release's tag and follows `skills/update-workflow/SKILL.md`. It opens a pull request that replaces the kit's copy, keeping any edits the project made on purpose, and does what that release's changelog asks of projects. Merge it like the set-up PR. The `workflow kit` CI check fails if anyone changes the copy without recording it, so the copy always matches a released version plus the project's recorded edits.

To check by hand: `python3 -B .claude/workflow/bin/workflow.py version --fresh`.

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
| `skills/start` | The guided start: "What are we working on?" with choices, a path per item, the plan filed as issues, a choice at each handover |
| `skills/next` | Find the next ready piece of work and do it under the flow |
| `skills/build-ticket` | One ticket from claim to merge |
| `skills/review-panel` | Standards, Spec, Correctness (with security) and a UI explorer, in parallel rounds until clean |
| `skills/conductor` | The unattended run: charter, sessions, check-ins, merges, release, stop |
| `skills/run-report` | The end-of-run report for the owner |
| `skills/update-workflow` | Update a project's vendored copy |
| `agents/` | The read-only Correctness reviewer and the UI explorer |
| `scripts/workflow.py` | The CLI the skills and hooks run: `profile`, `status`, `version`, `ready`, `charter`, `state`, `render`, `comments`, `evidence`, `repair`, `vendor`, `hook` |
| `hooks/` | Guard (the never-list), checklist gate, flow context and the guided start's first-message nudge, environment repair and project setup |
| `docs/` | `flow.md`, `charter.md`, `enforcement.md`, `install.md`, `spike.md` (what's verified), `proposal.md` (the design) |
| `templates/` | Profile, ticket-session briefing, tracking and by-hand issues, the `workflow kit` CI job and the weekly update check |

Standards and Spec reviews, TDD, the planning interview, specs, tickets and maps come from [Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT), pinned in `.claude-plugin/marketplace.json` and copied into each project alongside the kit's own (they aren't in this repository). [Planning new work](#planning-new-work-what-happens-underneath) lists every one and how it fits.

## Development

```bash
python3 -m pytest tests -q          # Python 3.11+, pytest
```

Every hook and script is tested with JSON fixtures, including attempts to get past the guard.

Releases are semver: `VERSION`, `.claude-plugin/plugin.json`, a `CHANGELOG.md` entry and a `v<version>` tag. Projects pin a release, and update with `update-workflow`.

## Licence

MIT (MedTech LLC): see `LICENSE`. The repository itself is private. The Matt Pocock skills keep their own MIT licence and notice: `THIRD_PARTY-mattpocock-skills.txt`.
