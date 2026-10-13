---
name: start
description: The guided start - ask what we're working on with clickable choices, split a request into items, propose a path for each (a quick ticket, finding a bug's cause, a spec, a map), record the plan as issues, and offer every next step as a choice, so the person never has to remember a command. Use at the first message of an attended session, on /start, or when the person isn't sure what to do next.
---

# Start: what are we working on?

Guide the person from "what are we working on?" to work done, one choice at a time. They should never need to know a command or what comes after what: you know the flow, they make the decisions.

**Every question is a choice to click.** Use the `AskUserQuestion` tool:
- your recommended option first, its label ending "(Recommended)", with one line saying why;
- at most 4 options. "Other" is always there for their own words, so don't add a "something else" option;
- up to 4 questions in one call when they don't depend on each other.

Ask in plain text only when the answer can't be a choice ("Tell me what you have in mind").

`WF` is the kit's CLI: `python3 -B .claude/workflow/bin/workflow.py` (vendored), or `python3 -B <this skill's directory>/../../scripts/workflow.py` (plugin). The flow is `.claude/workflow/flow.md` (vendored) or `docs/flow.md` beside `skills/` (plugin). Read it once a path is chosen.

**Only in attended sessions.** In a ticket or conductor session (`WORKFLOW_ROLE`), there is no menu: those sessions work from a briefing or a charter.

## 0. Read the first message

The kit's hook brings this skill at a session's first message. Read that message before showing anything:

| The message | What to do |
|---|---|
| A clear request: a question, a named issue ("build #262"), a small change with an obvious place ("rename the Save button to Done") | Do it. No menu. |
| A description of work to plan, one thing or several ("add XYZ, and the export needs fixing") | Go to step 2 with their words. |
| Anything vaguer ("hi", "let's work on pair-drop"), or `/start` | Step 1. |
| The conversation was already under way (a resumed session) | Ignore the hook. Carry on. |

## 1. Look around, then ask

Run:

```bash
WF status --fetch
```

Where `gh api` isn't available, fetch the open issues (`state=all`, with labels, bodies and `sub_issues_summary`) and the open PRs with the GitHub MCP tools, save them as JSON, and pass `--issues issues.json --prs prs.json`.

It reports:
- whether the kit is set up here, and whether the project is brand new (no code of its own yet);
- an unattended run in progress (`workflow:run`), claimed work (`workflow:in-progress`) and open PRs;
- items planned at an earlier start and not begun;
- maps, open specs and ready build tickets;
- what waits on a person (owner tasks, `needs-human`, `needs-info`);
- new issues to sort (`needs-triage`, or no label at all).

Tell the person what matters in two to four lines, for example: "PR #297 is waiting for your merge. Two items from last time aren't started: #301 export as PDF (spec), #302 the Save button (quick ticket). One ticket is ready: #262." Leave out what doesn't matter.

**If the kit isn't set up here:**
- **A plugin session in a project without the kit:** ask "This project isn't set up for the workflow kit yet": **Set it up (Recommended)** or **Work without the kit for now**. Setting up follows the kit's `setup-workflow` skill. It is user-only, so read its `SKILL.md` and follow it.
- **No kit at all:** this skill isn't loaded. The kit's README, "Getting started", is where to begin.

**Then ask: "What are we working on?"** Pick at most four options from what status shows, the most useful first:

| Option | Offer it when | Its description |
|---|---|---|
| **Carry on: <the thing>** | An item from last time, a map decision, a clear map's next spec, a ready ticket, or a PR waiting for them (name the most pressing one) | What it is and what happens next |
| **Something new, or a change to what's there** | Always | "Tell me in your own words; several things at once is fine." |
| **Fix something that's broken** | Always, unless four better options fill the list | "Describe what goes wrong; I'll find the cause." |
| **Sort the new issues (N)** | Status lists issues to sort | "Go through them one by one: ready to build, needs more info, or won't do." |
| **A brand-new project or a large effort** | The project is brand new (then first and recommended), or the person mentioned something big | "Chart it as a map of decisions first." |
| **Run the ready tickets unattended (N)** | Tickets are ready and no run is in progress | "They're built in parallel sessions while you're away." |

Then:
- **New, or a change, or a fix:** ask in plain text, "Tell me what you have in mind: as much or as little as you like." Then step 2.
- **Carry on:** go straight to that item's next step (step 4), or to `/next`'s section for a map decision or a ticket (read `skills/next/SKILL.md` and follow it with that issue).
- **Sort the new issues:** step 5.
- **A brand-new project or a large effort:** step 2, with the path already chosen: a map.
- **Run unattended:** a run can't start from this session. It needs a new cloud session in the conductor environment (the profile's `run.conductor_environment`), in **Auto** permission mode. Tell them exactly that, and the words to type there: "Run the backlog unattended". If a map is open with Destination items still unspecified, say so first: its tickets shouldn't be built yet (step 4, "Map").

## 2. Split it into items, and propose a path for each

List each separate thing you heard as an **item**: one line each, in their words.

Before judging any item, look at what is there. Read the code it touches, and any open issue, spec or map about it, so you know whether it changes existing behaviour and how much. Use a subagent when the looking takes long.

**The paths.** Judge one per item:

| Path | When | What happens |
|---|---|---|
| **Quick ticket** | Small and clear, with nothing left to decide: a wording change, a small tweak, a bug whose cause is known | One build ticket, written now, then built |
| **Find the cause first** | Something is broken and nobody knows why | The `diagnosing-bugs` skill until a command fails on the bug; then a quick ticket, or a spec if the fix needs decisions |
| **Spec** | A feature, or a change with decisions to make: who sees what, what happens when, data that changes shape, more than one place in the code | The interview, the spec, then its build tickets |
| **Map** | Too big or too unclear for one sitting: several specs, unknowns that need research or a prototype, or a brand-new project | A map of decisions (`wayfinder`), one decision per session |
| **Add to an existing issue** | It changes something already planned and not yet built: an open spec or ticket | That issue is edited with them |
| **Answer it** | It's a question, not work | Answer it |

**Changes to existing features.** Judge from what they said and what the code does now. Something that behaves wrongly in one place is usually a quick ticket, or "find the cause first". A change to how a feature works for its users is usually a spec.

**Ask, one question per item**, up to four items per call:
- the question: "<the item, short>: which way?";
- the options:
  1. your recommended path, "(Recommended)", with why in one line ("one screen and one wording, nothing to decide");
  2. **Spec**, always, unless it's your recommendation: "Interview, spec, then tickets. Takes longer; nothing gets assumed.";
  3. then another path that fits, if one does.

**Then propose the order** and ask "Go with this plan?":
1. what other items depend on comes first;
2. then what hurts users now;
3. then the rest, in the order they gave.

Options: **Go (Recommended)**, **Change the order**, **Change an item's path**.

Show the plan above the question, numbered, each item with its path. Say that each item is filed as an issue so nothing is lost between sessions.

## 3. Record the plan

Once they say go, file each item as a GitHub issue, in the plan's order, with:
- a title in their words;
- a body with what they said, what you found in the code, and the path;
- this marker as its last line, so the next `/start` finds it:

  ```
  <!-- workflow:item path=<ticket|diagnose|spec|map> -->
  ```

These are the person's words in an attended session, so they get no `<!-- workflow:agent -->` line. No label: they aren't ready to build, and they aren't new reports to sort. Nothing sensitive goes in an issue: read the profile's `profile.md` first.

Two kinds of item are never filed:
- **Add to an existing issue:** comment on that issue with their words instead;
- **Answer it:** answer it now.

Name the issues you filed ("#301, #302, #303"), then start the first item.

## 4. Work through the plan, one item at a time

For each item, read the flow's section for its path and follow it, skipping nothing. At every step below, the next step is a question with options.

**Quick ticket** (flow §2, its ticket rules):
1. Write the ticket from the project's Build ticket template:
   - what to build;
   - acceptance criteria, each naming where it's tested;
   - `## Blocked by`;
   - an `Area:` line.

   Show it, and ask **Publish it (Recommended)** or **Change it**.
2. Publish by editing the item's issue into the ticket: replace its body, drop the marker, add `ready-for-agent`. The item's issue becomes the ticket.
3. Ask:
   - **Build it now (Recommended)**: follow `build-ticket`;
   - **Leave it ready for later**: `/next` or a run picks it up;
   - **Next item**.

**Find the cause first:**
1. Follow `diagnosing-bugs` until a command fails on the bug and you know why.
2. Say what you found in two lines, and ask:
   - **File the fix as a ticket and build it (Recommended)**: then "Quick ticket" above, on the same issue;
   - **It needs decisions: make it a spec**: then "Spec" below;
   - **Stop here**: comment on the item's issue with what you found.

**Spec** (flow §2), all in this session where it fits:
1. **The interview.** Load the `grilling` and `domain-modeling` skills with the Skill tool (that's all `grill-with-docs` does), and interview them about the item. Ask each round's questions as choices: one question per decision, with your recommended answer as the first option and real alternatives after it. Use plain text only for a question with no sensible options. Look facts up yourself, in the background; only decisions go to them. When nothing is left to ask, confirm your understanding in a few lines and ask:
   - **Write the spec (Recommended)**;
   - **There's more to discuss**;
   - **Stop here**: comment on the item's issue with the decisions so far, so the next session carries on from them.
2. **The spec.** `to-spec` is user-only: read its `SKILL.md` and follow it. Ask the seams as a choice: **These seams (Recommended)** with the seams listed above the question, **Fewer, higher seams**, or **Change them**. Publish it under flow §2 (labels `spec` and `ready-for-agent`, the decision behind each choice cited). Close the item's issue as completed, with "Planned as #<spec>". Ask:
   - **Split it into tickets (Recommended)**;
   - **Edit the spec first**;
   - **Stop here**: `/start` offers the tickets next time, from the open spec.
3. **The tickets.** `to-tickets` is user-only: read its `SKILL.md` and follow it, with flow §2's additions. Show the breakdown and ask:
   - **Publish these (Recommended)**;
   - **Change the sizes**;
   - **Change what blocks what**;
   - **Merge or split some**.

   Repeat until they publish.
4. **Commit what the session wrote,** under flow §2: the glossary, ADRs and research notes, on a branch, with a pull request for them to merge.
5. Ask:
   - **Build the first ticket now (Recommended)**;
   - **Run them unattended**: tell them how, as in step 1;
   - **Next item of the plan**;
   - **Stop here**.

**Map** (flow §1):
1. `wayfinder` is user-only: read its `SKILL.md` and chart the map.
2. Close the item's issue with "Charted as #<map>".
3. Ask:
   - **Take the first decision now (Recommended)**: one decision per session, so for a long one offer a fresh session instead;
   - **Stop here**: `/start` offers the map's next decision next time.
4. **The gate.** None of a map's build tickets is built until every item of its Destination has a spec and tickets. Only `/next` and this skill keep to it: `workflow ready` and an unattended run don't know about maps. So while a map has unspecified Destination items, don't offer to build or run its tickets. When a run is asked for, say which tickets to leave out at its kick-off.

**Add to an existing issue:**
1. Show the change to that issue, and ask **Make this change (Recommended)** or **Change it**.
2. Edit it on yes.
3. If it's a spec whose tickets are published, find the tickets the change touches, and change them the same way.
4. A ticket already built (closed, or with an open PR) isn't edited: the change becomes a new quick ticket.

## 5. Sorting new issues

Take them one at a time, oldest first. For each, say in two lines what it asks and what you found in the code, and ask:
- **Ready to build**: turn it into a build ticket, as in "Quick ticket" above, with the same template. A `/triage` brief without `Area:` and `## Blocked by` doesn't meet flow §2;
- **Needs a spec**: it joins the plan as an item;
- **Needs more information**: comment asking for it, label `needs-info`;
- **Won't do**: comment why, close as not planned.

Put your recommendation first.

## 6. Between items, and when the session gets long

After each item, ask:
- **Next: <the next item> (Recommended)**;
- **Start it in a fresh session**;
- **Stop here**.

**Recommend a fresh session** when this one is long: past about 150,000 tokens, or a map decision done. The plan is on GitHub, so a fresh session's first message (or `/start`) offers "Carry on: #302".

**Keep each item's steps in one session where you can:** the interview, the spec and the tickets. If the session gets long in the middle of an item:
1. finish the step you're on;
2. suggest they type `/compact` (only they can);
3. or carry on in a fresh session from what's on GitHub: the item's issue, or the published spec, with `to-tickets` for its tickets.

## 7. Changing course

They can change course at any point. Take it as said, and confirm in one line:
- **"That's enough, write it up":** the interview ends. What's left open goes into the spec's Further Notes, as open questions.
- **"Skip that one" / "drop it":** close its issue as not planned.
- **"Do that one first":** reorder.
- **A spec or ticket to change after it's published:**
  - edit it on GitHub, or ask you to;
  - removing `ready-for-agent` stops `/next` and runs picking it up;
  - closing it as not planned drops it.
- **A decision to undo:** reopen it.

**When `to-spec` or `to-tickets` says to run `/setup-matt-pocock-skills`:** don't. It means `docs/agents/` is missing. Usually the kit's set-up pull request isn't merged yet: ask them to merge it first.

## Rules

- **Decisions are theirs, facts are yours.** Never answer a decision for them; never ask them what you can look up.
- **Merging is theirs** in attended work (flow §4).
- **Where planning runs:** an attended session, local, or in the cloud's Default environment, on a branch not named like `run.ticket_branch`. In the ticket or conductor environment, or on a `claude/build-*` branch:
  - the guard treats the session as part of a run;
  - every turn must end with a status line;
  - pushes are limited to ticket branches.
