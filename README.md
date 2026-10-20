# pairnexus-workflow

**[New to building? Start here](docs/quickstart.md)**

A Claude Code kit for building software in your own project. You describe what you want; Claude plans it, builds it in small reviewed pieces and merges what passes.

You start with attended work: you're there, and Claude asks what to do next with choices to click, so you don't need to remember its commands. Start a session and say what you're working on ([Using it](#using-it)). Claude working while you're away (unattended runs, led by the conductor) is something you can add later ([Set up unattended runs](#set-up-unattended-runs)).

For developers, the flow in short: **plan → spec → build tickets → one session per ticket → review panel → merge**

> [!NOTE]
> **Status: beta.** One project has used it so far.
> - **Not yet tried for real:** some mechanisms of unattended runs ([docs/spike.md](docs/spike.md) lists what has and hasn't been).
> - **What it needs:** Claude Code (unattended runs need its cloud sessions), GitHub, and Python 3.11+.
> - **Support:** maintained by PAIR (MedTech LLC) for its own work and shared as it is: best effort, with no guaranteed response time for issues or pull requests; security reports acknowledged within 5 working days; and a fix release when a Claude Code update breaks the guard or the hooks ([Support](#support)).
> - **Taking part:** questions, bugs and ideas go in [issues](https://github.com/medTech-group/pairnexus-workflow/issues), and contributions are welcome ([CONTRIBUTING.md](CONTRIBUTING.md)). Report security problems privately ([SECURITY.md](SECURITY.md)).

**Contents**
- [Getting started](#getting-started): what you need, one request and one pull request to start, then two optional upgrades
- [Using it](#using-it): the guided start, [`/next`](#one-piece-at-a-time-next), [unattended runs](#unattended)
- [Planning new work](#planning-new-work-what-happens-underneath): the interview, specs, tickets, maps, and [every Matt Pocock skill](#every-matt-pocock-skill-in-a-project)
- [Keeping it up to date](#keeping-it-up-to-date) and [as a plugin](#as-a-plugin-on-your-own-computer)
- [When something goes wrong](#when-something-goes-wrong), [Good to know](#good-to-know) and [Support](#support)
- [What's in it](#whats-in-it), [Development](#development), [Forking the kit](#forking-the-kit), [Where it came from](#where-it-came-from)
- Reference: [the flow](docs/flow.md), [the run charter](docs/charter.md), [the profile](docs/profile.md), [enforcement](docs/enforcement.md), [install modes](docs/install.md), [what's verified](docs/spike.md)

## Getting started

Setting up a repository takes one request to Claude and one pull request to merge. You do it once per repository, and attended work starts as soon as it merges. A new project starts in **solo mode**: with no ruleset on GitHub yet, the kit's guard refuses changes straight to `main`. Two upgrades take it the rest of the way when you want them, each one request to Claude that guides you click by click: ["Protect `main`"](#protect-main) and ["Set up unattended runs"](#set-up-unattended-runs). Steps 3 to 5 below are the same clicks by hand, as their fallback. Moving to a later version of the kit is one request to Claude and a small pull request (see "Keeping it up to date").

### Before your first repository (once)

You need:

1. **Admin rights on the repository,** for "Protect `main`". Rulesets and the merge settings are under the repository's Settings, which only admins see. Without them, the upgrade hands you a ready message for the owner.
2. **Claude Code cloud sessions**, from the Claude desktop app (choose **Cloud** rather than **Local** when starting a session) or from claude.ai/code in a browser. Both start the same kind of session, on the same environments: an environment you create in one shows up in the other, and a session started in one can be followed in the other. Unattended runs and the set-up check need a cloud session. A local session can do the set-up itself, if the computer has Python 3.11 or later and `gh` signed in to GitHub.
3. **GitHub access for Claude.**
   - The Claude GitHub App is installed on the organisation, with access to the project's repository. This one (`medTech-group/pairnexus-workflow`) is public, so any session can clone it.
   - Your claude.ai account is connected to GitHub.
   - If a session can't reach a repository, it tells you which of these is missing.
4. **A paid GitHub plan** (Team or above) if the repository is private. Rulesets on private repositories need one. Without a ruleset, nothing outside the session stops a push straight to the base branch.
5. **Python 3.11 or later** as `python3`, wherever anyone opens the project in Claude Code (the cloud image has it). The kit's hooks run on it. With an older one, or none, the kit can't check anything: ticket and conductor sessions are refused every tool, and an attended session is told when it starts, and asked before a push or merge.

### Step 1. Ask Claude to set the repository up

1. Start a cloud session on the project's repository, in the Default environment:
   - **Desktop app:** start a new Code session, choose **Cloud**, pick the Default environment and the repository.
   - **Browser:** at claude.ai/code, pick the repository and the Default environment.
2. Send this message:

   > Set this repository up with the pairnexus workflow: clone https://github.com/medTech-group/pairnexus-workflow at its latest release's tag and follow `skills/setup-workflow/SKILL.md`.

   If Claude asks to add the kit's repository, or Matt Pocock's `mattpocock/skills`, to the session, allow it. That is how a cloud session gets to read them. Projects take released versions only, so set-up uses the latest release, not whatever is on the kit's `main`.

Claude first explores the repository: its tests, CI and check names, deploy scripts, any existing `.claude/` files, and whether a ruleset already protects the base branch. Then it asks only what attended work needs and it couldn't find out, with a recommended answer first:

| Question | What it means, and the usual answer |
|---|---|
| New to building, or a developer? | How much the people working here know, as the project's default. It changes only how the kit words things, never what it allows. Each person can still say their own. |
| Vendored or plugin? | **Vendored.** The kit is copied into the repository, so cloud sessions and, later, unattended runs get it. The plugin is for attended work on your own computer only ([As a plugin](#as-a-plugin-on-your-own-computer)). |
| Your GitHub login | The person whose words count as approval: you. |
| Sensitive data | What must never appear in an issue, comment or PR, such as phone numbers, payment details, children's names or patients' names. |
| Explorer | How reviewers try a change from outside: **browser** (a web app; Playwright), **api**, **cli**, or **none**. |
| Deploy commands | Asked only when it found deploy scripts: which commands deploy. Sessions are refused them, or an attended session asks you first. |

It may also ask about an older flow of the project's own. It asks nothing about areas, environment names, permission modes, merge approvals or releases: those wait for "Set up unattended runs".

Then Claude:
- **creates the workflow's labels** on the repository straight away (`ready-for-agent`, `workflow:run`, `workflow:stop` and others);
- **opens one pull request** containing:
  - the repository's settings: `.claude/workflow/profile.toml` and `profile.md`, with `ruleset = false` (solo mode), or `ruleset = true` when it read back a ruleset that already protects the base branch;
  - the kit's copy: its skills and Matt Pocock's in `.claude/skills/`, the reviewer agents in `.claude/agents/`, the CLI, docs and templates in `.claude/workflow/`, its hooks merged into `.claude/settings.json`, and `.claude/workflow/lock.json` recording the version and every file;
  - a `workflow kit` CI check (`.github/workflows/workflow-kit.yml`) and the weekly update check (`.github/workflows/workflow-kit-update.yml`);
  - CODEOWNERS, issue templates, the pull request template ("In plain words" at the top), `docs/agents/` (how agents use the issue tracker and labels), `.gitignore` entries, and a short section in `CLAUDE.md`.

In plugin mode there is no copy and no CI jobs: the PR holds the profile, the plugin in `.claude/settings.json`, and the rest of the list.

The PR body says **Merge this and start working**, and names "Protect `main`" and "Set up unattended runs" as optional next steps. There is no checklist of clicks to do first.

### Step 2. Merge the pull request

1. Wait for its CI to go green.
2. Read it.
3. Click **Merge pull request** (a merge commit), then **Confirm merge**.

It changes `.claude/` and `.github/`, so merging it is always yours, never an agent's. Once it has merged, start working: a session begins with the guided start. Claude offers "Protect `main`" once, with "Not now".

### Protect `main`

Ask Claude to protect `main`, or pick **Protect `main`** where the kit offers it. The `upgrade-setup` skill does it for you:

- **On your own computer, with `gh` signed in as the repository's admin:** after one confirmation, the kit makes the ruleset and the merge settings itself with `gh`. Claude Code asks you to approve the command that makes the ruleset; that is expected. You can tick the checks that already ran on `main`, to require them too.
- **In a cloud session, or without `gh`:** guided clicks, one screen at a time.

Either way it reads them back to confirm, and opens the pull request that leaves solo mode (`ruleset = true`, plus any checks you ticked). Checks are required once CI has run on `main`: tick them in the confirmation if they already ran, or later ask Claude to **require the checks** (or pick it in `check-setup`), which adds the ones you tick to the ruleset with "Require branches to be up to date" and lists them in the profile's `ci.required_checks` in a small pull request. Solo mode is how a project starts with no ruleset: the kit's guard is then all that keeps changes off `main`, so it refuses them. Until you merge that pull request, the guard stays in solo mode. If you're not the repository's admin, it gives you a ready message for the owner instead.

[Step 3](#step-3-protect-the-base-branch-with-a-ruleset) and [Step 4](#step-4-check-the-merge-settings) below are the same clicks by hand: they are its fallback, and what it guides you through when something can't be done for you.

### Set up unattended runs

When you want Claude to build tickets while you're away, ask Claude to **set up unattended runs**. Vendored mode only. The same `upgrade-setup` skill first offers "Protect `main`" if the project is still in solo mode; if you skip it, GitHub won't hold a merge for failing checks. Then it asks the questions only runs need: areas, environment names, ticket sessions' permission mode, merge approvals and releases. It shows you one screen for creating the two environments, with their names, `WORKFLOW_ROLE` values and setup script filled in. Last, it writes your answers to the profile in one pull request.

On merge approvals: unattended runs merge only if a pull request can merge with no human approval. If your team requires one, keep it in the ruleset: each run's conductor sees it and recommends stopping at "ready for review" (the charter's merge mode **owner**), since a PR a session opens is yours and you can't approve your own.

[Step 5](#step-5-create-the-two-claude-environments) below is the same clicks by hand: it is its fallback. The questions it asks are the ones Step 5 needs answers to.

### Step 3. Protect the base branch with a ruleset

The ruleset is what really stops anyone, a session included, from pushing straight to the base branch or merging before CI is green. The kit's own guard is a seatbelt; the ruleset is the wall.

On GitHub, open the repository's **Settings → Rules → Rulesets → New ruleset → New branch ruleset**, and fill it in:

- **Ruleset name:** anything, for example `main`.
- **Enforcement status:** **Active**. "Disabled" and "Evaluate" enforce nothing.
- **Bypass list:** **leave it empty.** Sessions act through your GitHub account, so anything you can bypass, a session could bypass too.
- **Target branches:** **Add target → Include default branch** (if the profile's `project.base_branch` isn't the default branch, add that branch by name instead).
- **Rules**, tick:
  - **Restrict deletions**.
  - **Block force pushes**.
  - **Require a pull request before merging**:
    - **Required approvals: 0**, so unattended runs can merge. If your team needs approvals, set them here; runs then stop at "ready for review" (see [Set up unattended runs](#set-up-unattended-runs)).
    - **Require review from Code Owners: leave it unticked.** Sessions post under your GitHub account, and GitHub never lets an author approve their own PR, so with it ticked those PRs could never merge.
  - **Require status checks to pass**:
    - Tick **Require branches to be up to date before merging**. Without it, two PRs that each passed against an older base can both merge and break it together.
    - **Add checks:** every name in the profile's `ci.required_checks`, `workflow kit` included in vendored mode. Type each name exactly; GitHub suggests names from recent runs.
- **Don't tick "Require linear history".** Sessions merge with a merge commit, which it forbids.
- Click **Create**.

### Step 4. Check the merge settings

Open the repository's **Settings → General** and scroll to **Pull Requests**:
- Tick **Allow auto-merge**.
- Keep **Allow merge commits** ticked. Sessions and the conductor always merge with a merge commit, so with it off every unattended merge fails.

### Step 5. Create the two Claude environments

An environment is the cloud machine a session runs on: its network access, environment variables, secrets and setup script. You pick one each time you start a session. **Skip this step in plugin mode**, and until you want unattended runs.

> [!IMPORTANT]
> **These two environments are for unattended runs only.** You start the conductor's sessions; the conductor starts the ticket sessions. **For planning, and for building a ticket with you there, use the Default environment** (or any environment without `WORKFLOW_ROLE`). See [Plan in one session, build in another](#plan-in-one-session-build-in-another).

To create one:
- **Desktop app:** in a new Code session, open the environment dropdown in the prompt box and select **Cloud**, then **Add cloud environment**. To change one later, hover over it in the same list and click its gear icon.
- **Browser:** at claude.ai/code, open the cloud environment menu (where you pick an environment when starting a session, or in a running session's title bar) and choose **Add environment**. To change one later, choose it there and click **Edit**.

Either way it's the same environment, so create each one once.

The names come from the profile's `run.ticket_environment` and `run.conductor_environment`, which set-up leaves empty. If you do this by hand, choose the two names first and put them in the profile by a pull request; "Set up unattended runs" does that for you.

**The ticket environment**, named exactly as in the profile's `run.ticket_environment` (for example `myproject-ticket`):
- **Environment variables:** only `WORKFLOW_ROLE=ticket`. Type it exactly: a value the kit doesn't know counts as `ticket` too, the strictest.
- **Secrets:** **none.** Leave **Network secrets** empty, and put no key or token in an environment variable: no cloud keys, no Auth0, Firebase or payment credentials, no deploy tokens. Tests use fakes, and a session can't misuse a key it doesn't have.
- **Network access:** the default is usually enough for package managers and container images. If a session later reports a blocked host, set Network access to **Limited** and add the host under **Allowed domains**, with **Allow package managers** left ticked. With the browser explorer, Playwright downloads Chromium: allow its host if the network is limited.
- **Setup script:** only the environments' setup script, the profile's `run.environment_setup` ("Set up unattended runs" works it out and shows it). **For most projects it is empty: leave the field blank.** See "What goes in the setup script" below.

**The conductor environment**, named exactly as in the profile's `run.conductor_environment` (for example `myproject-conductor`):
- **Environment variables:** `WORKFLOW_ROLE=conductor`.
- **Secrets:** none, unless you want runs to release. Then add only what the release steps need.
- **Setup script:** the same as the ticket environment's (often blank).

**What goes in the setup script.** Two different things get installed, at two different times:

| What | Example | Where it goes | When it runs |
|---|---|---|---|
| **Machine tools** the cloud image doesn't have | Flutter, the .NET SDK | The environment's **setup script** (the profile's `run.environment_setup`) | Once per environment, before Claude starts; the result is cached for later sessions |
| **The project's own dependencies** | `npm ci`, a Python virtualenv from `requirements.txt`, Playwright for the browser explorer | Nowhere you type: the profile's `commands.setup`, which the kit runs at the start of each cloud session when `commands.setup_check` says it's missing. It never runs without `setup_check` (`profile check` warns), and has about 8 minutes | Each new session, from the fresh clone |

The setup script runs before the repository is there, so it must never read the repository's files: one that does fails, and no session in that environment can start. The cloud image already has Python, Node.js, Java, Go, Rust, Ruby, PHP, Docker, PostgreSQL and Redis, so most projects need no setup script at all, whatever their stack:
- a Python API, or a Node.js app with or without a frontend: **blank**; the kit installs its packages;
- a project with no dependencies: **blank**, and `commands.setup` is empty too;
- a Flutter app: a script that downloads Flutter.

**Why the names must match.** The repository can't hold an environment's id, because ids belong to your Claude account. So the profile holds the names instead. At the start of a run, the conductor lists your environments, takes the one named `run.ticket_environment`, and starts every ticket session in it. If no environment has that name, the run stops before starting anything and says so. The name matters because of what that environment holds:
- **no credentials**;
- **`WORKFLOW_ROLE=ticket`**, which puts the guard in its strictest mode. A session can't change an environment variable from inside. Without it, the guard can only guess the role from the branch name, which a session can change.

**One repository per session.** The kit's hooks load from the repository's `.claude/settings.json` only when a cloud session has a single repository. Never add a second repository to a conductor or ticket session: it would run without the guard.

**What's per repository:**

| | One per repository? | Why |
|---|---|---|
| Ticket environment | **No**, if the setup scripts match | It holds no project files: only `WORKFLOW_ROLE=ticket` and the machine tools. Repositories whose setup script is the same (most often blank) can share one; name it in each profile. |
| Conductor environment | **No**, likewise | Unless runs release: then it holds that project's release secrets, and gets its own. |
| Ruleset | Yes | Each repository has its own check names. |
| Merge settings | Yes | Per-repository settings. |
| The kit | No | Built once, here. Each repository holds a pinned copy. |

### Step 6. Check it

Ask Claude to **check the set-up**, or run `workflow doctor` in your terminal (`python3 -B .claude/workflow/bin/workflow.py doctor`). Either gives one report of what's set up and what isn't, each line with its fix, the most serious first, and changes nothing.

Ask in a **cloud** session on the repository, since only cloud sessions can list your environments:

> Check the set-up.

Claude's `check-setup` skill gathers the rulesets and the merge settings through GitHub's API, the base branch's latest check runs and statuses and the open pull requests, the two environments, the `workflow:run` issues and its Claude Code version, runs `workflow doctor` with them, and shows you the report. For each upgrade the report names ("Protect `main`", "Restore protection", "Set up unattended runs", "Require these checks") it asks whether to do it now, with "Not now". In a local session, with `gh` signed in, it checks everything but the environments, and says those need a cloud session. The guided start offers it when its quick look finds a problem, and once a session in solo mode.

The kit's checklist (`.claude/workflow/docs/enforcement.md`, section 5) is what doctor checks, kept there as the reference for checking by hand:
- the ruleset, through GitHub's API: active, on the base branch, no bypass, deletions and force pushes blocked, required approvals, every required check present, "up to date" ticked, Code Owners off, linear history off;
- that auto-merge and merge commits are allowed;
- CODEOWNERS;
- that both environments exist, by name;
- `profile check` and `vendor verify`.

It can't see what an environment holds, so it asks you to confirm the ticket environment has no secrets.

At the start of every run the conductor runs `workflow doctor`, the same check, again. A missing ticket environment stops it. Any other gap it shows you, to fix first or to accept for that run.

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
> | **Build one ticket with you there** | the Default environment, as for planning | Type **`/next build`**. You merge its pull request: ask Claude "is #N ready to merge?" first, and choose "Merge it now" once it says "Ready" |
>
> - **Never start a session in the ticket environment yourself.** The conductor starts those, one per ticket.
> - **Never plan in the ticket or conductor environment.** Their `WORKFLOW_ROLE` tells the kit the session is part of an unattended run: it asks you nothing, follows a ticket session's or the conductor's rules, and the guided start never shows.
> - Planning and building can be days apart: everything waits on GitHub in between.

#### Start a session and say what you're working on

You don't need to remember any command. Start a session on the repository and say what you have in mind, or just "hi": Claude works out what to do, asks with choices to click when there's something to choose, and offers each next step the same way until the work is done. This is the kit's **guided start** (the `start` skill).

**Where:** a session on the repository, with you there:
- a local session;
- or a cloud session in the **Default environment** (any environment without `WORKFLOW_ROLE`), on a branch not named `claude/build-…`.

Not the ticket or conductor environment, and not a `claude/build-…` branch. There the session counts as part of an unattended run, and there is no menu:
- **in the ticket environment, or on a `claude/build-…` branch:** the guard holds it to a ticket session's rules, pushes go only to `claude/build-…` branches, and every turn has to end with a `WORKFLOW-STATUS` line;
- **in the conductor environment:** the conductor's rules. The guard denies what it would ask you about elsewhere, and allows the release steps the charter grants.

**What happens with your first message:**

| You type | Claude |
|---|---|
| Something clear: a question, "build #262", "rename the Save button to Done" | Does it. No menu. A code change goes on its own branch with a pull request for you to merge; if it turns out bigger than it looked, Claude offers a quick ticket instead. |
| Work to plan, one thing or several: "add booking reminders, and the booking page needs changing because testers found it confusing" | Splits it into items and proposes a path for each (below) |
| Anything vaguer: "hi", "let's work on the app", or `/start` | Looks at the project and asks "What are we working on?" |
| A command, such as `/next` or `/grill-me` | Runs that command, with no menu |

`/start` brings the menu back at any time (in plugin mode, `/pairnexus-workflow:start`). To turn the first-message menu off for a project, set `guided_start = false` in the profile's `[project]`; `/start` still works.

**Looking around.** First, Claude runs `workflow status`, which reads the project's issues and pull requests. Then it tells you, in a few lines, what matters:
- a pull request waiting for your merge;
- an unattended run in progress;
- items left from your last session;
- tickets ready to build;
- issues waiting on a person (owner tasks, `needs-human`, `needs-info`);
- new issues to sort: open issues labelled `needs-triage` or with no label at all (an issue opened with only GitHub's `bug` or `enhancement` label isn't counted: add `needs-triage` to it, or type `/triage`);
- a newer release of the kit;
- whether the project is brand new.

Then it asks **What are we working on?**, with up to four of these:
- **Update the workflow kit to 0.1.x (Recommended)**, first, when a newer release is out and no run is in progress ([Keeping it up to date](#keeping-it-up-to-date));
- **Check the set-up** (recommended, unless a kit update is), when its quick look finds a problem on your computer or in the kit's copy; or, not recommended, once a session in solo mode ([Step 6](#step-6-check-it));
- **Carry on:** the most pressing item: your PR, work an earlier session claimed but didn't finish (carry on from its branch, or **Release it**), a planned item, a spec with no tickets yet, a map decision, or a ready ticket;
- **Something new, or a change to what's there**;
- **Fix something that's broken**;
- **Sort the new issues**;
- **A brand-new project or a large effort** (recommended when the project has no code yet, unless a kit update or **Check the set-up** is);
- **Run the ready tickets unattended**: a run can't start from this session, so Claude tells you how to start one ([Unattended](#unattended)).

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

> I tested the booking page. Customers should get a reminder the day before their booking. And the page confuses people: they don't see which times are free.

Claude replies with two items and asks about each:

- *"Booking reminders: which way?"*
  - **Spec (Recommended):** "how long before, sent how, and for which bookings: decisions to make";
  - **Map**.
- *"Booking page doesn't show what's free: which way?"*
  - **Quick ticket (Recommended):** "the page has the free times already; it's how they're shown";
  - **Spec**.

Then *"Go with this plan? 1. Booking page (quick ticket) 2. Booking reminders (spec)"*. You click **Go**. It files #301 and #302, writes the booking page ticket, shows it to you, publishes it on your click, and asks **Build it now**, **Build it with a light review** (one review round, for a small change; never the recommendation), **Leave it ready for later** or **Next item**.

**At every handover, a choice:**

| After | You're offered |
|---|---|
| The interview | **Write the spec**, **There's more to discuss**, **Stop here** |
| The spec | **Split it into tickets**, **Edit the spec first**, **Stop here** |
| The tickets | **Build them in a fresh session**, **Run them unattended**, **Next item of the plan** (when it's light), **Stop here** |
| Charting a map | **Stop here: the first decision in a fresh session**, **Next item of the plan** (when it's light) |
| A light item (a quick ticket published, an edit to an issue) | **Next: <the next item>**, **Start it in a fresh session**, **Stop here** |
| Finding a bug's cause | **File the fix as a ticket and build it**, **It needs decisions: make it a spec**, **Stop here** (what was found goes on the issue) |
| A map decision, or a build | A recommendation to go on in a fresh session |

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

Building a ticket follows the kit's flow, the same as in a run except the merge:
1. it claims the ticket (`workflow:in-progress`);
2. builds it test-first at the spec's seams;
3. runs the review panel in rounds until one is clean (at most the profile's `run.review_rounds`; in a run, the charter's);
4. runs the full suite locally and posts the counts on the pull request (`workflow evidence`, which also counts the base branch's tests);
5. opens the pull request with its findings table, and watches CI, checking in every `run.check_in_minutes` while it waits;
6. ends each turn with a `WORKFLOW-STATUS` line and the flow's checklist.

You merge the pull request.

**What "ready" means.** `/next` and runs take a ticket only when all of these hold:
- it's open and labelled `ready-for-agent`;
- it isn't a spec: not labelled `spec`, its title doesn't start with "Spec:", and it has no sub-issues;
- it isn't labelled `needs-human`, `owner-task` or `ready-for-human`, and nobody has claimed it (`workflow:in-progress`);
- no open pull request closes it;
- every ticket it's blocked by is closed as completed (one closed as not planned still blocks, and so does one in another repository).

Infra tickets (`workflow:infra`) come first, then by number.

#### Unattended

In an unattended run, a **conductor** asks the owner a few questions once (the **run charter**). It then builds every ready ticket in parallel sessions, merges what passes, releases if allowed, and reports. Mid-run it waits on you only for your own tasks and for questions it asked you.

1. Start a cloud session on the repository (desktop app: **Cloud**; or claude.ai/code). Choose the **conductor environment**, and in the permission mode selector (beside the send button in the desktop app) choose **Auto**. A mode that asks before using tools would stall the run, and ticket sessions can't run in a more permissive mode than the conductor's.
2. Say:

   > Run the backlog unattended.

3. The conductor checks the set-up with `workflow doctor` (the ruleset, CODEOWNERS, the environments, the kit) and whether a newer kit is out, then asks you the charter's questions in one sitting: which tickets, until when, how many at once (2 by default), what it may merge and release, and the like ([docs/charter.md](docs/charter.md)).
4. It opens a **tracking issue** for the run (label `workflow:run`), with an issue for any by-hand checks linked from it, shows you the charter there, and waits for your one "go" (in the chat, or as a comment on the issue). If you don't go ahead, it closes both issues.
5. From then on it runs without you; you can close the browser:
   - it starts a ticket session for each ready ticket in the ticket environment, as many at once as you allowed and at most one per area;
   - it checks in every 20 minutes by default, and merges what passes;
   - at the end it writes a report on the tracking issue, and closes it.

**Watching it.** The tracking issue is the run's record:
- its **Now** line says what is running and what's next;
- the conductor comments as tickets merge, fail or need you;
- the ticket sessions show in your sessions list at claude.ai/code, tagged with the run.

Subscribe to the tracking issue to hear about it. The conductor's @mentions of you go out under your own account, so GitHub may not notify you of them.

**Changing it.** Comment on the tracking issue, for example "also #140", "stop releasing" or "extend to Monday 9am". Only your own comments count (the GitHub login you gave in step 1). It reads them at the next check-in and replies to confirm.

**Stopping it.** Add the label `workflow:stop` to the tracking issue, or say "stop the run" in the conductor's session. From its next check-in it interrupts the ticket sessions and waits for their branches to settle, which can take a few check-ins, then writes the report. **A stopped run releases nothing**, whatever the charter says; release by hand if you still want to.

**The end time** is a hard stop, not "start nothing new": the conductor stops the running sessions the same way, then releases if the charter says so.

**If the conductor's session ends** (closed, archived, or out of usage): start a new session in the conductor environment, in **Auto**, and say **"conductor resume #<tracking issue>"**. It rebuilds from the tracking issue, which holds the run's whole state.

**Usage.** Each ticket session runs the review panel for up to three rounds, and the conductor checks in until the end time, so a run's usage grows with its tickets. Cap it with the charter's sessions in all (40 by default), sessions at once, and the end time.

**Not yet proven in a real run** ([docs/spike.md](docs/spike.md)): a guard denial in a cloud session (row 4), a private repository's ruleset refusing a push (row 5), the conductor clearing a finished session's check-ins (row 11), a ticket session waking the conductor at once when it finishes (row 13; otherwise the next check-in sees it), and the final report's notification (row 17).

A run only builds tickets that are ready ([what that means](#one-piece-at-a-time-next)): planning is a conversation with you, so it never happens in a run. While a map still has Destination items without a spec, the conductor's kick-off lists that map's ready tickets and recommends leaving them out (see [the gate](#a-large-or-brand-new-effort-wayfinder)).

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

> /grill-with-docs In our notes app, people should get a reminder for a note they've given a date.

Claude interviews you in **rounds**:
- Each round asks every question that can be answered now: the ones that don't wait on another open answer. Each comes with Claude's recommended answer. Typed as a command, the questions are numbered and worded so that "yes" accepts the recommendation; the guided start asks them as choices to click, recommendation first.
- Answer the whole round in one message. For example:

  > Q1 yes. Q2 no: only notes they've starred. Q3 yes, but on the morning of the date, not the day before. Q4 I don't know, what do you suggest?

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
  - a written `## Blocked by` section, as well as GitHub's own links, so a blocker closed as "not planned" is still seen. The readiness check also reads a `Blocked by: #12, #14` line, "blocked by #8" in a sentence (so don't write it in passing), issue and PR links (an open PR blocks until it merges), `owner/repo#n`, and "None";
  - an `Area:` line with one word from the profile's `[areas]`, so an unattended run never runs two sessions on the same area at once. A ticket with no area can run beside anything;
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

> /wayfinder A small shop online: customers order from their phone, staff pack and post the orders.

1. Claude interviews you about the **destination**: what reaching the end looks like. It can be several items, each needing its own spec (for example "customers order from their phone" and "staff pack the orders").
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

   Both are protected paths: Claude shows you each change, and the pull request is yours to merge. (The guard stops only ticket sessions from changing them; in your own session, you are the check.) A build ticket can't make them, so this is never a ticket.
6. **Add the new check names to the ruleset** ([Step 3](#step-3-protect-the-base-branch-with-a-ruleset)).
7. **Only then run tickets unattended.**

#### Side trips while planning

- **`/prototype`**: throwaway code that answers one question.
  - A **logic** prototype: a single HTML file that pushes a state model through hard cases you can click through.
  - A **UI** prototype: several very different versions of one screen, switchable in the browser.

  When it has answered the question, the answer goes into the decisions, and the prototype is kept on a branch for reference.
- **`/research <question>`**: a background agent reads the primary sources (official docs, source code, specs) and leaves a Markdown file in the repository, citing each claim. You keep talking meanwhile; its findings feed the interview. It is kept on a `research/…` branch, linked from the issue it answers, and never merged.
- **`/to-questionnaire`**: when someone else holds the answer (an accountant, a supplier, legal). It asks you only who it's for and what you need back, then writes them a questionnaire to fill in, most important question first. It writes `to-questionnaire-<slug>.md` in the repository's root; you send it yourself. In a cloud session, ask Claude to print it before the session ends: the file is gone with the machine.
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

**Versions.** The kit is released as numbered versions (`0.1.5`): each is a tag (`v0.1.5`) and a GitHub release on [the Releases page](https://github.com/medTech-group/pairnexus-workflow/releases), with what changed. The kit's `release` workflow tags and publishes each version when it lands on `main`. A vendored project holds a pinned copy of one release, recorded in its `.claude/workflow/lock.json`, and moves to a newer one only through a pull request you merge. (In plugin mode, the session start says when a newer release is out, and `/plugin update pairnexus-workflow@pairnexus` updates it; the plugin follows `main`, not only releases.)

**You're told when a newer release is out, three ways:**

| Where | What you see | What to do |
|---|---|---|
| **A session you start** (the guided start) | **"Update the workflow kit to 0.1.5 (Recommended)"** as the first choice, or **"Carry on: the kit update PR #n"** once one is open | Click it. Claude opens the update pull request; you merge it |
| **An unattended run's kick-off** | **Update first** or **Run on 0.1.4** | Update first: the run ends, you update in a session of your own, then start the run again. A run never changes version midway, and its ticket sessions never update |
| **The weekly check** (a GitHub Action set-up adds, Mondays 04:17 UTC; vendored mode) | An issue, **"Workflow kit update: 0.1.4 → 0.1.5"**, labelled `owner-task`, linking every release since and the full difference; closed once you've updated | Start a session and choose the update, or say "Update the workflow kit". To skip that version, close the issue as not planned: it comes back for the next release |

**Nothing updates by itself.** The kit is what guards your sessions, so a new version always arrives as a pull request you read and merge, never swapped in by a session: a ticket session that could rewrite its own guard would defeat it, and the `workflow kit` CI check refuses a copy that wasn't recorded through an update. The weekly check opens an issue rather than the pull request, because a pull request opened by a GitHub Action's own token never runs your CI.

**To update by hand,** in a session on the repository (the Default environment), type `/update-workflow` (from kit 0.1.5 on), or say this, which works from any version:

> Update the workflow kit: clone it at the latest release's tag and follow its `skills/update-workflow/SKILL.md`.

Claude clones the kit at the latest release's tag into a temporary directory and follows that release's `skills/update-workflow/SKILL.md`. It opens a pull request that replaces the kit's copy, keeping any edits the project made on purpose, and does what that release's changelog asks of projects. Merge it like the set-up PR. The `workflow kit` CI check fails if anyone changes the copy without recording it, so the copy always matches a released version plus the project's recorded edits.

The update pull request lists each file the project had edited: kept as edited where the kit didn't change it, and merged by hand where both did. It also brings over changes to the files set-up copied once (the CI jobs, `docs/agents/issue-tracker.md`, the issue templates), and adds the pull request template once to a project set up before it.

To check by hand: `python3 -B .claude/workflow/bin/workflow.py version --fresh`. Each session start looks up the latest release (with `gh`, else GitHub's public API) at most every six hours; `WORKFLOW_UPDATE_CHECK=off` in an environment turns the lookup off.

### As a plugin, on your own computer

Everything above is the **vendored** mode, which every project that runs unattended needs. The kit also installs as a Claude Code plugin, for attended work on a laptop, in the desktop app or a terminal. Cloud sessions and unattended runs don't install it (unless an organisation Owner turns it on for every member: [docs/install.md](docs/install.md)), so pick one mode per project: never both. Your computer needs Python 3.11 or later as `python3`.

**Install it once on your computer.** The kit's repository is its own plugin marketplace, `pairnexus`. In Claude Code, type:

```
/plugin marketplace add medtech-group/pairnexus-workflow
/plugin install pairnexus-workflow@pairnexus
```

- This also installs Matt Pocock's skills (`mattpocock-skills@pairnexus`, pinned) and the kit's hooks: the guard, the status gate, the flow context and the session start.
- Don't also add Matt Pocock's own marketplace: two plugins named `mattpocock-skills` drop one's hooks.
- If Claude Code can't clone the repository, run `gh auth login && gh auth setup-git`, and set `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1` if you have no SSH key for GitHub.

**Set the project up** as in [Step 1](#step-1-ask-claude-to-set-the-repository-up), answering **plugin** to "Vendored or plugin?". It writes the profile and adds the plugin to the project's `.claude/settings.json`, so Claude Code suggests it to everyone who opens the project; each person still installs it once. There's no copy in `.claude/`, no `workflow kit` CI check and no weekly update check.

**The commands carry the plugin's name.** The kit's own:

| Type | What it does |
|---|---|
| `/pairnexus-workflow:start` | The guided start. It also comes up by itself at your first message, once the project has a profile |
| `/pairnexus-workflow:next` | The next ready piece of work: `map`, `spec`, `build` or an issue number after it |
| `/pairnexus-workflow:build-ticket` | Builds one ready ticket, from claim to merge |
| `/pairnexus-workflow:review-panel` | The review panel on a diff or pull request |
| `/pairnexus-workflow:run-report` | A run's report |
| `/pairnexus-workflow:merge-check` | "Is #12 ready to merge?": "Ready" or "Not yet" and why, the fixes as choices, then "Merge it now". Claude also uses it when you ask |
| `/pairnexus-workflow:upgrade-setup` | "Protect `main`": the ruleset and merge settings, read back, then the pull request that leaves solo mode |
| `/pairnexus-workflow:setup-workflow` | Sets a project up; Claude never starts it on its own |
| `/pairnexus-workflow:conductor` | An unattended run. It runs cloud sessions, which need the vendored mode |

Matt Pocock's take `mattpocock-skills:`, such as `/mattpocock-skills:to-spec`, `/mattpocock-skills:to-tickets`, `/mattpocock-skills:wayfinder` and `/mattpocock-skills:grill-with-docs`. [Every Matt Pocock skill in a project](#every-matt-pocock-skill-in-a-project) lists them all; add the prefix to each. Wherever this README says `/next` or `/to-spec`, type the prefixed name.

**Updating.** The session start says when a newer release is out. Type `/plugin update pairnexus-workflow@pairnexus` (not `/update-workflow`, which updates a vendored copy). The plugin follows `main`, not only releases.

[docs/install.md](docs/install.md) has the details, and how an organisation Owner can turn the plugin on for every member.

### When something goes wrong

| What you see | What it means, and what to do |
|---|---|
| **"[workflow guard, …] … is never allowed"** or an approval prompt for a push | The guard stopped something on its never-list (a push to the base branch, a force-push, a deploy command). In your own session, the prompt only comes in modes that ask (`default`, `acceptEdits`, `auto`, `plan`): approve only if you meant it. In a mode where nobody is asked (`bypassPermissions`, `dontAsk`, or one the kit doesn't know), it is refused instead and says "The kit would have asked you about this": switch the permission mode (Shift+Tab) to be asked, or run the command it gives in your own terminal. A ticket session never gets past it, and ends `needs-human` if its ticket needs it |
| **"the profile is invalid"** on every command | A ticket or conductor session fails closed. Fix `.claude/workflow/profile.toml` in a pull request from an attended session (`workflow.py profile check` says what's wrong), or restore it: `git checkout -- .claude/workflow` |
| **"The workflow's guard isn't working"** on a push or a merge | The guard couldn't decide (an error, an invalid profile, an unreadable event, or a `python3` that is old, missing or failing), so in your own session a push or a merge is asked, and refused in solo mode or where nobody is asked; everything else goes through unchecked. Run `python3 .claude/workflow/bin/workflow.py profile check`, check `python3 --version` (3.11 or newer), and report the error if neither shows it |
| **"Workflow kit: … Python 3.11"** at the start (it "needs Python 3.11", or "python3 could not run the workflow kit"), or every tool refused | `python3` is older than 3.11, missing, or failing. Check `python3 --version`, install 3.11 or later so `python3` runs it, and start a new session. On an old `python3`, `workflow doctor` gives a short report: `python3`'s version as a gap with its fix, and every other line as can't check until `python3` is 3.11 or newer |
| **A command blocked because the guard's hook timed out** ("blocking because onFailure is 'block'") | The guard took longer than its 30-second timeout (a command over a very large tree, or a slow laptop), so Claude Code blocked the tool rather than run it unchecked, in every kind of session. Claude says so and offers to split or simplify the command: run it in smaller pieces. The same block comes when the guard's hook can't start at all (`sh` missing, or the guard's command in `.claude/settings.json` edited): then every tool is blocked. Edit the settings by hand outside Claude Code, putting back the kit's guard entry (a kit update writes it again), and start a new session. This needs Claude Code v2.1.295 or later; an older version lets such a command run |
| **A hook error on every tool call** | Usually the kit's copy missing. Restore it with `git checkout -- .claude/workflow` |
| **"Project setup … FAILED"** at a cloud session's start | `commands.setup` failed or ran out of time (about 8 minutes). The session carries on without the dependencies: fix the command in the profile |
| **The `workflow kit` check fails** | The kit's copy doesn't match `.claude/workflow/lock.json`: someone changed it without an update. Undo the change, or update the kit properly (`/update-workflow`) |
| **A required check never reports**, so the PR can't merge | See "PRs that CI skips" below |
| **A run stalls** with PRs open | Is auto-merge allowed (Step 4)? Does the ruleset require an approval? Is the conductor's session still there? (If not: "conductor resume #<tracking issue>") |
| **`/next` says nothing is ready** | Check the ticket against [what ready means](#one-piece-at-a-time-next): most often a missing `ready-for-agent`, a blocker not closed as completed, or a claim left by an earlier session |

### Good to know

- **PRs that CI skips.** If the CI workflow skips some paths (`paths-ignore`, for docs-only changes say), a PR touching only those never gets its required checks, and with an empty bypass list it can't merge. Fix it in CI rather than in the ruleset: let each required job run on every PR and skip its own steps when nothing relevant changed, so the check still reports. Set-up notes such checks in the profile (`ci.path_filtered`), and a run hands those PRs to you.
- **Protected paths** (`.claude/`, `.github/workflows/`, CODEOWNERS, `.env` files): ticket sessions can't change them. Any PR that does is yours to review and merge, and a ticket that needs one is filed as an owner task. Adding your own in the profile's `guard.protected_paths` replaces the defaults, so keep them in the list.
- **The profile** (`.claude/workflow/profile.toml`) holds every setting: [docs/profile.md](docs/profile.md) explains each one. Change it in a pull request you merge.
- **Read more:**
  - [docs/flow.md](docs/flow.md): the flow sessions follow;
  - [docs/charter.md](docs/charter.md): the run charter;
  - [docs/enforcement.md](docs/enforcement.md): what stops a session, and why;
  - [docs/install.md](docs/install.md): vendored and plugin modes;
  - [docs/profile.md](docs/profile.md): the profile's settings and the environment variables;
  - [docs/protection.md](docs/protection.md): reading back whether the base branch is protected;
  - [docs/spike.md](docs/spike.md): what has been tried for real, and what hasn't.

### Support

PAIR (MedTech LLC) maintains the kit for its own work and shares it as it is. What it promises, in the same words here, in [SECURITY.md](SECURITY.md) and in [CONTRIBUTING.md](CONTRIBUTING.md):
- best effort, with no guaranteed response time for issues or pull requests;
- security reports acknowledged within 5 working days;
- a fix release when a Claude Code update breaks the guard or the hooks.

How to report each:
- **A question, a bug or an idea:** open an [issue](https://github.com/medTech-group/pairnexus-workflow/issues).
- **The guard or a hook stopped working after a Claude Code update:** open an issue with the template ["The guard or a hook stopped working after a Claude Code update"](https://github.com/medTech-group/pairnexus-workflow/issues/new?template=claude-code-break.md) (`.github/ISSUE_TEMPLATE/claude-code-break.md`). It asks for Claude Code's version, the kit's and how the kit is installed.
- **A security problem,** including a Claude Code update that lets a session past the guard: report it privately, as [SECURITY.md](SECURITY.md) says, never in a public issue.

## What's in it

| Part | What it does |
|---|---|
| `skills/setup-workflow` | Once per project: the solo set-up: the attended questions, the profile, labels, CODEOWNERS, vendoring, one pull request to merge and start working |
| `skills/start` | The guided start: "What are we working on?" with choices, a path per item, the plan filed as issues, a choice at each handover |
| `skills/next` | Find the next ready piece of work and do it under the flow |
| `skills/build-ticket` | One ticket from claim to merge |
| `skills/review-panel` | Standards, Spec, Correctness (with a security review for auth, upload, payment or API changes) and, when the profile has an explorer and the change touches a screen, endpoint or command, the explorer, in parallel rounds until clean |
| `skills/conductor` | The unattended run: charter, sessions, check-ins, merges, release, stop |
| `skills/run-report` | The end-of-run report for the owner |
| `skills/merge-check` | "Is #12 ready to merge?": the merge rule's answer in plain words, posting nothing, with the fixes as choices and "Merge it now" when it's ready |
| `skills/check-setup` | "Check the set-up": `workflow doctor`'s report, with what only a session can see (the rulesets, the environments) handed to it, and each upgrade it names offered with "Not now"; changes nothing |
| `skills/upgrade-setup` | The upgrades from solo mode: "Protect `main`", guided click by click, read back, then the pull request that leaves solo mode |
| `skills/update-workflow` | Update a project's vendored copy |
| `agents/` | The read-only Correctness reviewer and the UI explorer |
| `scripts/workflow.py`, `scripts/workflow/` | The CLI the skills and hooks run (Python 3.11+, standard library only): `profile`, `status` (with doctor's local gaps, no network call), `doctor` (what's set up and what isn't, each line with its fix; changes nothing), `protection`, `version`, `adopt`, `ready`, `charter`, `state`, `render`, `comments`, `merge-check`, `preview` (whether a pull request's try-it link is ready for its head commit), `briefing`, `evidence`, `repair`, `vendor`, `hook`. `python3 -B scripts/workflow.py --help` lists every flag |
| `hooks/hooks.json` | The plugin's hooks (a vendored project gets the same hooks in its `.claude/settings.json`): the guard (the never-list), the status gate, the flow context (`docs/profile.md`, "The flow context") and the guided start's first-message nudge, and at session start the environment repair, project setup and update notice |
| `docs/` | `flow.md`, `charter.md`, `enforcement.md`, `install.md`, `profile.md`, `protection.md`, `spike.md` (what's verified), `proposal.md` (the original design, historical) |
| `templates/` | The profile (`profile.toml`, `profile.md`), the ticket-session briefing, tracking and by-hand issues, `issue-tracker.md` (for `docs/agents/`), the issue templates, the pull request template, the `workflow kit` CI job and the weekly update check |
| `.claude-plugin/` | The plugin manifest and the `pairnexus` marketplace, which pins Matt Pocock's skills |
| `.github/` | The kit's own CI (the tests on Python 3.11 to 3.13, the hooks on a Python 3.9, and a check that the versions agree), the `release` workflow, and this repository's issue templates |
| `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` | How to report a vulnerability, how to contribute, and the code of conduct |
| `tests/` | The tests |
| `VERSION`, `CHANGELOG.md` | The version, and what changed in each, with the steps for projects updating |

Standards and Spec reviews, TDD, the planning interview, specs, tickets and maps come from [Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT), pinned in `.claude-plugin/marketplace.json` and copied into each project alongside the kit's own (they aren't in this repository). [Planning new work](#planning-new-work-what-happens-underneath) lists every one and how it fits.

## Development

```bash
python3 -m pytest tests -q          # Python 3.11+, pytest
```

Every hook and script is tested with JSON fixtures, including attempts to get past the guard.

Releases are semver: every change to shipped files bumps `VERSION`, `.claude-plugin/plugin.json` and adds a `CHANGELOG.md` entry, with a "For projects updating" list when a project must do something. **Shipped** means what `vendor.plan` copies into a project: `skills/`, `agents/`, `scripts/`, `templates/`, `docs/` (except `proposal.md`, `spike.md` and `quickstart.md`; `flow.md` goes to `.claude/workflow/flow.md`), `LICENSE`, and the hook set in `vendor.py`. README, CHANGELOG, `tests/` and `.github/` aren't. A shipped change merged without a bump reaches no vendored project until the next one, but plugin users get it at once: the plugin follows `main`.

CI checks that `VERSION`, `plugin.json` and the CHANGELOG agree; nothing checks that a change came with its bump. **Don't tag by hand:** the `release` workflow tags and publishes each version when its bump lands on `main` (`.github/scripts/release.py`). Projects pin a release, and update with `update-workflow`.

### Forking the kit

A fork can run its own releases, with its own projects following it rather than this repository. Change, in the fork:
- **The kit's home,** `KIT_REPO` in `scripts/workflow/updates.py`. That is the one place code reads it. The skills and the weekly update check read it through `workflow version --repo`, and projects set up from the fork follow it for updates.
- **The starter's home,** `STARTER_REPO` beside it, if the fork has its own starter template. `workflow version --starter` prints it, and the guided start's offer of the starter is to read it from there.
- **The marketplace and plugin names,** if you rename them:
  - `.claude-plugin/marketplace.json` (`name`, `owner`) and `.claude-plugin/plugin.json` (`name`, `author`);
  - the `pairnexus-workflow@pairnexus` key and the `pairnexus-workflow:` command prefix: `PLUGIN_UPDATE` in `updates.py`, `PLUGIN_KEY` in `vendor.py`, `scripts/workflow/context.py`, the skills `start`, `setup-workflow` and `review-panel`, `docs/flow.md`, `docs/install.md` and this README. `grep -rn "pairnexus-workflow[@:]" .` finds them.
- **The install commands** in `docs/install.md` and this README (the marketplace's `owner/repo`).
- **This repository's own pages:** the security advisory link in `.github/ISSUE_TEMPLATE/config.yml` and `.github/ISSUE_TEMPLATE/claude-code-break.md`, the issue-template link in `SECURITY.md`, and the contacts in `SECURITY.md`, `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`.
- **The rest:**
  - the `User-Agent` in `updates.py`;
  - the release title in `.github/scripts/release.py`;
  - the README's links;
  - the copyright line you add to `LICENSE`, keeping the original notice as MIT requires.

A test (`tests/test_kit_017.py`) counts where shipped files still name the upstream; it follows `KIT_REPO`, so it passes once the constant points at the fork.

Turn on GitHub Actions in the fork, bump the version and let the `release` workflow publish. Its first run also publishes a release for each version the fork inherited (at the upstream's tags); the newest, yours, is marked latest. A project already vendored from this repository keeps following it until it's updated from the fork: clone the fork's release and follow its `update-workflow` skill once.

## Where it came from

The kit packages what worked over the pair-drop weekend run of 9–12 Oct 2026, about 50 tickets, with fixes for what didn't. pair-drop is PAIR's own project, and is set up with the kit. [docs/spike.md](docs/spike.md) records what has been verified, and what hasn't, and [docs/proposal.md](docs/proposal.md) is PAIR's original proposal.

## Licence

MIT (MedTech LLC): see `LICENSE`, which a vendored copy carries as `.claude/workflow/LICENSE`. The repository is public. Contributions come in under the same licence ([CONTRIBUTING.md](CONTRIBUTING.md)); everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md). The Matt Pocock skills keep their own MIT licence and notice: `THIRD_PARTY-mattpocock-skills.txt` here, `.claude/skills/LICENSE-mattpocock-skills` in a project.
