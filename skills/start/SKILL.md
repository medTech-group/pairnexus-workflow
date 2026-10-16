---
name: start
description: The guided start - ask what we're working on with clickable choices, split a request into items, propose a path for each (a quick ticket, finding a bug's cause, a spec, a map), record the plan as issues, and offer every next step as a choice, so the person never has to remember a command. Use at the first message of an attended session, on /start, or when the person isn't sure what to do next, and when they say "explain less" or "explain more".
---

# Start: what are we working on?

Guide the person from "what are we working on?" to work done, one choice at a time. They should never need to know a command or what comes after what: you know the flow, they make the decisions.

## Choices

**Every question is a choice to click.** Use the `AskUserQuestion` tool:
- **Options:** 2 to 4. Your recommended option comes first, its label ending "(Recommended)", with one line saying why. "Other" is always added for their own words, so never add a "something else" option.
- **Questions:** up to 4 in one call, when they don't depend on each other. More than 4 means several calls.
- **No tool:** where `AskUserQuestion` isn't available (a headless `-p` session), ask the same choices as a numbered list.

Ask in plain text only when the answer can't be a choice ("Tell me what you have in mind").

## Where things are

**The CLI.** `WF` is:
- `python3 -B .claude/workflow/bin/workflow.py` (vendored);
- or `python3 -B <this skill's directory>/../../scripts/workflow.py` (plugin).

**The flow.** `.claude/workflow/flow.md` (vendored), or `docs/flow.md` beside `skills/` (plugin). Read it once a path is chosen.

**Skills Claude may load itself** (`grilling`, `domain-modeling`, `diagnosing-bugs`, `research`, and the kit's `next` and `build-ticket`): load them with the Skill tool.

**User-only skills** (`to-spec`, `to-tickets`, `wayfinder`, `triage`) can't be loaded with the Skill tool: read their `SKILL.md` and follow it.
- Vendored, it is at `.claude/skills/<name>/SKILL.md`.
- In plugin mode, find it with `find ~/.claude/plugins -path '*/<name>/SKILL.md'`.
- Links inside a `SKILL.md` are relative to its own directory.

**Only in attended sessions.** In a ticket or conductor session (`WORKFLOW_ROLE`) there is no menu: those sessions work from a briefing or a charter.

## Before anything: how much they know

The kit words things and paces itself for each person's experience: *new to building* or *developer*. It changes nothing else.

**Is it known?** At a session's first message (not a resumed one), run `WF status --json` before reading the message. Ask only when its `experience.source` is `"unknown"`: no `WORKFLOW_EXPERIENCE`, no local file and no project default. Otherwise word things for its `experience.wording_level` and go on to step 0.

**Never in a ticket or conductor session** (`WORKFLOW_ROLE` set to anything but `attended`, or a branch named like the profile's `run.ticket_branch`): they never ask, whatever status says, and word things for its `wording_level`. **Nor when the kit isn't set up here** (status's `set_up` is false): set-up asks the experience question, so it would come twice.

**Ask it** as the very first question of the session, before step 0's work or any other question, with `AskUserQuestion`: "How much do you know about building software?" (header "Experience"). It describes the person, so no option is recommended:
- *New to building*: "Explain the words and go one step at a time."
- *Developer*: "Keep it short: git, pull requests and CI are familiar."

Then go on to step 0, with their first message. With the profile's `guided_start = false`, this question comes only with `/start`.

**Skipping counts as new.** If they skip it, dismiss it or answer with something else (their request, say), record `new`, and take what they wrote as their first message.

**Record the answer:**
- Write it to `.workflow/experience` in the project: one line, `new` or `developer`. That is the file `workflow status` reads as the local file. Never stage or commit it.
- **Check first** that the file stays out of the repository: `git check-ignore -q .workflow/experience` must succeed, and nothing that isn't a plain file may sit at that path (a link, say). If either check fails, don't write it: keep the level in this conversation for this session.
- **A cloud session** (`CLAUDE_CODE_REMOTE` is `true`) starts from a fresh clone, so the file lasts for this session only. **Say once**, in one line, how to keep it: "To be asked only once, add `WORKFLOW_EXPERIENCE=<level>` to this cloud environment's variables on claude.ai."

**"Explain less" or "explain more",** at any point in the session, changes the level: "explain less" to `developer`, "explain more" to `new`. It is recorded the same way, and confirmed in one line ("Got it: I'll keep it short."). When `experience.source` is `"environment"`, the file can't override it: keep the new level for this session, and say once that `WORKFLOW_EXPERIENCE` (on the cloud environment, or in their shell) changes it for good. Then carry on where you were: don't restart the guided start.

**Tell yourself the new level** whenever you record one, answer or change alike, in one line: "From now on: <level>." With *developer* (the first question's answer, or "explain less"), stop explaining the glossary's words for the rest of the session. After "explain more", read the glossary again (`.claude/workflow/docs/glossary.md` vendored, or `docs/glossary.md` beside `skills/` in the plugin), if it is there, and from then on explain each of its words in the glossary's wording, in one or two sentences, the first time you use it in this session, and never again in this session. Never explain them in what you write on GitHub (pull request descriptions, comments, reports).

## 0. Read the first message

The kit's hook brings this skill at a session's first message. Read that message before showing anything:

| The message | What to do |
|---|---|
| One clear request: a question, a named issue ("build #262"), one small change with an obvious place ("rename the Save button to Done") | Do it. No menu. A change to the code goes on a branch of its own with a pull request for them to merge (only pull requests reach the base branch); if it turns out bigger than it looked, offer a quick ticket instead. |
| **More than one thing**, even if one of them is small ("add XYZ, and the greeting is wrong") | Step 1's look around, without the question, then step 2 with their words. Never start on one of them before the plan is agreed. |
| One piece of work to plan: a feature, a change to how something works, something broken with no known cause | The same: step 1's look around, then step 2 |
| Anything vaguer ("hi", "let's work on the app"), or `/start` | Step 1 |
| The conversation was already under way (a resumed session) | Ignore the hook and carry on |

## 1. Look around, then ask

Run:

```bash
WF status --fetch
```

Where `gh api` isn't available, fetch the issues (`state=all`, with labels, bodies and `sub_issues_summary`) and the open PRs with the GitHub MCP tools. Save them as JSON and pass `--issues issues.json --prs prs.json`.

It reports:
- whether the kit is set up, and whether the project is brand new (no code of its own);
- the kit's version here, and whether a newer release is out (`Kit version:`; the session's start says so too);
- an unattended run (`workflow:run`), claimed work (`workflow:in-progress`) and open PRs;
- items planned at an earlier start and not begun;
- maps, open specs (and parent issues) and ready build tickets;
- what waits on a person (owner tasks, `needs-human`, `needs-info`);
- new issues to sort (`needs-triage`, or no label).

Tell the person what matters in two to four lines, for example: "PR #297 is waiting for your merge. Two items from last time aren't started: #301 refill reminders (spec), #302 the Save button (quick ticket). One ticket is ready: #262." Leave out what doesn't matter.

**In solo mode** (status says `Solo mode: yes`), one of those lines says so, with what it means for them: "This project is in solo mode: nothing on GitHub protects `<base branch>` yet, so the kit refuses any change straight to it, and all work goes through pull requests." Name the profile's base branch. Don't offer "Protect `main`" here: it is offered when they ask, and in a refusal.

**If the kit isn't set up here** (only possible with the plugin, since otherwise this skill isn't there), ask "This project isn't set up for the workflow kit yet". The options:
- **Set it up (Recommended):** follow the kit's `setup-workflow` skill. It is user-only, so read its `SKILL.md`.
- **Work without the kit for now.**

**Then ask: "What are we working on?"** Pick two to four options from what status shows, the most useful first:

| Option | Offer it when | Its description |
|---|---|---|
| **Update the workflow kit to <version> (Recommended)** | A newer kit release is out, no run is in progress, and no update pull request is open (status's `kit_update_pr`; else offer "Carry on: the kit update PR #n"). It comes first, before a brand-new project's map | "A pull request for you to merge, with what's new; then we carry on." |
| **Carry on: <the thing>** | Something is under way (the table below): name the most pressing one | What it is and what happens next |
| **Something new, or a change to what's there** | Always | "Tell me in your own words; several things at once is fine." |
| **Fix something that's broken** | Unless four better options fill the list | "Describe what goes wrong; I'll find the cause." |
| **Sort the new issues (N)** | Status lists issues to sort | "One by one: ready to build, needs more info, or won't do." |
| **A brand-new project or a large effort** | The project is brand new (then first and recommended), or they mentioned something big | "Chart it as a map of decisions first." |
| **Run the ready tickets unattended (N)** | Tickets are ready and no run is in progress | "Built in parallel sessions while you're away." |

**Carrying on.** What "Carry on" does depends on what is under way:

| Under way | What to do |
|---|---|
| A PR waiting for them | Give its link, what it does and its checks. Ask **Review it with me (Recommended)**, **I'll merge it myself** or **Later**. |
| Work claimed (`workflow:in-progress`), no run in progress | An earlier session stopped part-way. Read the issue's comments and look for its branch (an open PR that closes it, or a branch naming its number). Ask **Carry on from there (Recommended)**, then follow `build-ticket` on that branch, or **Release it**, which removes the label so `/next` can take it. |
| A planned item | Read its body and comments. A `path=spec` item may have an interview's decisions in a comment: carry on the interview from them, or go to the spec if nothing is left open. Then step 4 for its path. |
| An open spec with no tickets | `to-tickets` for it (step 4, "Spec", step 3) |
| A map decision, a clear map's next spec, or a ready ticket | Load `next` with the Skill tool, with that issue |

**What the other options lead to:**
- **Update the workflow kit:** in plugin mode (no `.claude/workflow/lock.json`), tell them to type `/plugin update pairnexus-workflow@pairnexus`. Vendored: read the project's `.claude/skills/update-workflow/SKILL.md` (user-only, so read it) for where the kit lives and how to clone the new release outside the project, then read **that release's** `$KIT/skills/update-workflow/SKILL.md` and follow it. It ends with a pull request for them to merge. Then ask "What are we working on?" again, without this option. With a run in progress, don't offer it: a run stays on the version it started with.
- **New, a change, or a fix:** ask in plain text, "Tell me what you have in mind: as much or as little as you like." Then step 2.
- **Sort the new issues:** step 5.
- **A brand-new project or a large effort:** step 2, with the path already chosen: a map.
- **Run unattended:** a run can't start from this session.
  1. It needs a new cloud session in the conductor environment (the profile's `run.conductor_environment`), in **Auto** permission mode, with the words "Run the backlog unattended". Tell them exactly that.
  2. If a map is open with Destination items still unspecified, say so first: the conductor will recommend leaving its tickets out (flow §1, "The gate").

## 2. Split it into items, and propose a path for each

List each separate thing you heard as an **item**: one line each, in their words.

**Look before judging.** Read the code each item touches, and any open issue, spec or map about it. Then you know whether it already exists, whether it changes existing behaviour, and how much. Use a subagent when the looking takes long. If something they asked for already exists, say where, and ask whether they meant a change to it.

**The paths.** Judge one per item:

| Path | When | What happens |
|---|---|---|
| **Quick ticket** | Small and clear, with nothing left to decide: a wording change, a small tweak, a bug whose cause is known | One build ticket, written now, then built |
| **Find the cause first** | Something is broken and nobody knows why | `diagnosing-bugs` until a command fails on the bug; then a quick ticket, or a spec if the fix needs decisions |
| **Spec** | A feature, or a change with decisions to make: who sees what, what happens when, data that changes shape, more than one place in the code | The interview, the spec, then its build tickets |
| **Map** | Too big or too unclear for one sitting: several specs, unknowns that need research or a prototype, or a brand-new project | A map of decisions (`wayfinder`), one decision per session |
| **Add to an existing issue** | It changes something already planned and not yet built: an open spec or ticket | That issue is edited with them |
| **Answer it** | It's a question, not work | Answer it; no question about its path |

**Changes to existing features.** Judge from what they said and what the code does now:
- something that behaves wrongly in one place is usually a quick ticket, or "find the cause first";
- a change to how a feature works for its users is usually a spec.

**Ask, one question per item** (not for "Answer it"):
- the question: "<the item, short>: which way?";
- the options, at least two:
  1. your recommended path, "(Recommended)", with why in one line ("one screen and one wording, nothing to decide");
  2. **Spec**: "Interview, spec, then tickets. Takes longer; nothing gets assumed." When Spec is the recommendation, give instead the next most likely path, with its risk named ("Quick ticket: faster, but I'd be deciding X for you");
  3. any other path that fits.

**Then propose the order** and ask "Go with this plan?":
1. what other items depend on comes first;
2. then what hurts users now;
3. then the rest, in the order they gave.

Show the plan above the question, numbered, each item with its path and what it waits for ("after #301"). Say that each item is filed as an issue, so nothing is lost between sessions. The options: **Go (Recommended)**, **Change the order**, **Change an item's path**.

## 3. Record the plan

Once they say go, file each item as a GitHub issue, in the plan's order, with:
- a title in their words;
- a body with what they said, what you found in the code, the path, and what it waits for ("After #301: it builds on the export");
- this marker as its last line, so the next `/start` finds it:

  ```
  <!-- workflow:item path=<ticket|diagnose|spec|map> -->
  ```

These are the person's words in an attended session, so they get no `<!-- workflow:agent -->` line. They get no label either: they aren't ready to build, and they aren't new reports to sort. Nothing sensitive goes in an issue: read the profile's `profile.md` first.

Two kinds of item are never filed:
- **Add to an existing issue:** comment on that issue with their words;
- **Answer it:** answer it now.

Name the issues you filed ("#301, #302, #303"). Then start the first item.

**What an item waits for becomes a blocker.** Write it into the `## Blocked by` of the ticket it becomes (or of each of its spec's tickets), so `/next` and a run never build it first.

## 4. Work through the plan, one item at a time

For each item, read the flow's section for its path and follow it, skipping nothing. At every step below, the next step is a question with options.

**Branches.** In an attended session, each ticket is built on its own branch, made fresh from `origin/<base>`:
- not named like the profile's `run.ticket_branch` (`claude/build-*`), or the session turns into a ticket session; use, for example, `claude/<ticket number>-<slug>`;
- the session's files (glossary, ADRs) get their own branch and pull request too, so no pull request carries another's work.

**Before any "Stop here":** commit what this session wrote (flow §2's "Commit what the session wrote"), so nothing is left only in this machine.

**Quick ticket** (flow §2, its ticket rules):
1. Write the ticket from the project's Build ticket template:
   - what to build;
   - acceptance criteria, each naming where it's tested;
   - `## Blocked by`, with what the item waits for;
   - an `Area:` line.

   Show it, and ask **Publish it (Recommended)** or **Change it**.
2. Publish by editing the item's issue into the ticket: replace its body, drop the marker, and add `ready-for-agent`. The item's issue becomes the ticket.
3. Ask:
   - **Build it now (Recommended)**: load `build-ticket` with the Skill tool, on a fresh branch;
   - **Leave it ready for later**: `/next` or a run picks it up;
   - **Next item**.

**Find the cause first:**
1. Follow `diagnosing-bugs` until a command fails on the bug and you know why.
2. Say what you found in two lines, and ask:
   - **File the fix as a ticket and build it (Recommended)**: then "Quick ticket" above, on the same issue, with the failing command in its acceptance criteria;
   - **It needs decisions: make it a spec**: then "Spec" below;
   - **Stop here**: comment on the item's issue with what you found.

**Spec** (flow §2), all in one session where it fits:
1. **The interview.** Load the `grilling` and `domain-modeling` skills with the Skill tool (that's all `grill-with-docs` does), and interview them about the item. Ask each round's questions as choices:
   - one question per decision;
   - your recommended answer as the first option, with real alternatives after it;
   - plain text only for a question with no sensible options.

   Look facts up yourself, in the background; only decisions go to them.

   When nothing is left to ask, confirm your understanding in a few lines and ask:
   - **Write the spec (Recommended)**;
   - **There's more to discuss**;
   - **Stop here**: comment on the item's issue with the decisions so far, so the next session carries on from them.
2. **The spec.** Read `to-spec`'s `SKILL.md` and follow it.
   - Ask the seams as a choice, with the seams listed above the question: **These seams (Recommended)**, **Fewer, higher seams** or **Change them**.
   - Publish it under flow §2: labels `spec` and `ready-for-agent`, the decision behind each choice cited, and, for a map's Destination item, linked from the map.
   - Close the item's issue as completed, with "Planned as #<spec>".

   Ask:
   - **Split it into tickets (Recommended)**;
   - **Edit the spec first**;
   - **Stop here**: `/start` offers the tickets next time, from the open spec.
3. **The tickets.** Read `to-tickets`' `SKILL.md` and follow it, with flow §2's additions. Show the breakdown and ask:
   - **Publish these (Recommended)**;
   - **Change the sizes**;
   - **Change what blocks what**;
   - **Merge or split some**.

   Repeat until they publish.
4. **Commit what the session wrote,** as flow §2 says.
5. **Build in a fresh session.** A spec's interview and tickets fill most of a session, and the flow builds one ticket per session. Ask:
   - **Build them in a fresh session (Recommended)**: there, the first message (or `/next build`) takes the first ticket;
   - **Run them unattended**: tell them how, as in step 1;
   - **Next item of the plan**: only when it is light (a quick ticket to publish, an edit to an issue); else a fresh session for that too;
   - **Stop here**.

**Map** (flow §1):
1. Read `wayfinder`'s `SKILL.md` and chart the map. Charting is one session's work: it settles no decision itself.
2. Close the item's issue with "Charted as #<map>".
3. Ask:
   - **Stop here: the first decision in a fresh session (Recommended)**: there, the first message offers it, or `/next map`;
   - **Next item of the plan**: only when it is light.
4. **The gate** (flow §1). None of a map's build tickets is built until every item of its Destination has a spec and tickets. `next`, this skill and the conductor's kick-off keep to it; `workflow ready` doesn't know about maps. So while a map has unspecified Destination items, don't offer to build its tickets.

**Add to an existing issue:**
1. Show the change to that issue, and ask **Make this change (Recommended)** or **Change it**.
2. Edit it on yes.
3. If it's a spec whose tickets are published, find the tickets the change touches, and change them the same way.
4. A ticket already built (closed, or with an open PR) isn't edited: the change becomes a new quick ticket.

## 5. Sorting new issues

Take them one at a time, oldest first, following `triage`'s steps for each. Read its `SKILL.md`:
- its disclaimer on every comment it posts;
- the check whether it is already built, or ruled out before (`.out-of-scope/`);
- reproducing a bug before anything else.

Say in two lines what it asks and what you found, then ask, your recommendation first:
- **Ready to build**: it becomes a build ticket as in "Quick ticket" above, with the same template (flow §2 says a triaged ticket gets `Area:`, `## Blocked by` and acceptance criteria);
- **Needs a spec**: it joins the plan: append the item marker with `path=spec`;
- **Needs more information**: comment asking for it, label `needs-info`;
- **Won't do**: comment why, label `wontfix`, close as not planned.

Each outcome removes `needs-triage`.

## 6. Between items, and when the session gets long

**After a light item** (a quick ticket published, an edit to an issue, a diagnosis filed), ask:
- **Next: <the next item> (Recommended)**;
- **Start it in a fresh session**;
- **Stop here**.

**After a heavy item** (a spec with its tickets, a build, a map), recommend a fresh session for the next one. The flow keeps one spec, one ticket or one map decision to a session.

**A fresh session is easy:** the plan is on GitHub, so a fresh session's first message (or `/start`) offers "Carry on: #302". Recommend one too when this session is long: past about 150,000 tokens.

**When the session gets long in the middle of an item:**
1. finish the step you're on;
2. suggest they type `/compact` (only they can);
3. or carry on in a fresh session from what's on GitHub: the item's issue with its decisions, or the published spec, with `to-tickets` for its tickets.

## 7. Changing course

They can change course at any point. Take it as said, and confirm in one line:
- **"That's enough, write it up":** the interview ends. What's left open goes into the spec's Further Notes, as open questions.
- **"Skip that one" / "drop it":** close its issue as not planned.
- **"Do that one first":** reorder, and change the blockers to match.
- **A spec or ticket to change after it's published:**
  - edit it on GitHub, or ask you to;
  - removing `ready-for-agent` stops `/next` and runs picking it up;
  - closing it as not planned drops it.
- **A decision to undo:** reopen it.

**When `to-spec` or `to-tickets` says to run `/setup-matt-pocock-skills`:** don't. It means `docs/agents/` is missing, usually because the kit's set-up pull request isn't merged yet. Ask them to merge it first.

## Rules

- **Decisions are theirs, facts are yours.** Never answer a decision for them; never ask them what you can look up.
- **Merging is theirs** in attended work (flow §4).
- **The level changes wording and pacing in this conversation only,** never what the kit allows. What you write on GitHub (issues, comments, PR descriptions, run reports) is the same for every level, plain summary first.
- **Where this runs:** a local session, or a cloud session in the Default environment, on a branch not named like `run.ticket_branch`. Elsewhere the session is part of a run, and the guided start never shows:
  - in the ticket environment (`WORKFLOW_ROLE=ticket`), or on a `claude/build-*` branch: the guard holds it to a ticket session's rules, pushes go only to ticket branches, and every turn must end with a status line;
  - in the conductor environment (`WORKFLOW_ROLE=conductor`): the conductor's rules, with no status line.
