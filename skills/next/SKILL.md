---
name: next
description: Find the next ready piece of work (a map decision, a spec to write, or a build ticket) and do it under the workflow's flow. Optional argument - "map", "spec", "build", or an issue number.
---

# Next

Pick one ready piece of work and do it, following the flow (`.claude/workflow/flow.md` vendored, or `docs/flow.md` beside `skills/` as a plugin). One piece per session.

**Never in a conductor session.** In a conductor session (`WORKFLOW_ROLE=conductor`), never build: follow the `conductor` skill's "A ticket named in chat" with the ticket, or, with none named, offer a run of the ready tickets as its "Start a run" says. The conductor hands each ticket to a ticket session; it never builds one itself.

Read the flow and the project's profile (`.claude/workflow/profile.toml`, `profile.md`) first. Use the GitHub MCP tools, or `gh api` where the session has it. `WF` is the kit's CLI: `python3 .claude/workflow/bin/workflow.py`, or `python3 <this skill's directory>/../../scripts/workflow.py` as a plugin.

## 1. Find what is ready

**Build tickets:** run the readiness check rather than judging by eye.

```bash
WF ready --fetch
```

Where `gh api` isn't available, fetch the issues and PRs with the GitHub MCP tools, save them as JSON, and pass them with `--issues issues.json --prs prs.json`:
- every issue, open and closed (`state=all`), with its labels, body, `created_at`, `comments`, `state_reason`, `sub_issues_summary` and `issue_dependencies_summary`;
- the open pull requests.

It lists each `ready-for-agent` build ticket as READY, or gives why not:
- a blocker that's open, unknown, in another repository, or closed as not planned;
- a GitHub issue dependency;
- `needs-human`, `ready-for-human` or `owner-task`;
- claimed (`workflow:in-progress`);
- an open PR closes it.

It leaves out specs (the `spec` label, a "Spec:" title, or an issue with sub-issues) and maps.

A READY ticket may carry notes, which never change whether it is ready:
- "names protected path <path> (<pattern>): check it isn't an owner task";
- "area <area> is in run.bar_areas, but the ticket has no ## Bar heading: …", when its area is one of the profile's `run.bar_areas` and its body has no `## Bar` (#428): check whether it needs one;
- "spec #<n> has no clean review: check it before building", when its spec (its parent issue, labelled `spec`) has no clean review record for its current body from an account with write access. Specs created before the kit brought this in are never noted. When the spec's comments or their authors' permissions can't be read, the note says so: "spec #<n>: couldn't read its reviews (<why>)".

Where `gh api` isn't available, give each spec's comments in its `comments` field in `issues.json`, as a list (`issue_read` with method `get_comments`, every page), and the permissions of those who posted them with `--permissions perms.json`, in any shape `merge-check --permissions` takes (`list_repository_collaborators`, every page, or each author's `collaborators/<login>/permission`). A spec whose comments aren't given as a list (a count of 0 is none) is read with `gh api`, and a spec without `created_at` counts as new.

**Maps and specs:**
- **A map** is an issue labelled `wayfinder:map`. Its ready decisions are its open, unclaimed child tickets whose blockers are closed, in the order `issue_read` with method `get_sub_issues` returns them. A map's Notes may reorder its own frontier.
- **A clear map** has no open children and nothing under "Not yet specified". Its first Destination item with no spec linked is ready to spec, skipping one whose study is under way: a "Study under way: #<n>" comment on the map naming it, with #<n> open (the `study` skill's section 5). That item is offered as that study's **Carry on** (`start`'s "Carrying on"), never started afresh, and is ready to spec again once #<n> closes. None is ready while the map's Notes link an open research issue (a new project's study, §2's **Offering a study**): that study is offered as its **Carry on** instead. Once it closes, its verdict, on the research issue, says what follows: on **Build it**, they are ready to spec; on **Prototype first**, the prototype comes first, as the map's decision (a `wayfinder:prototype` ticket linking the verdict: chart it if the map has none), so the map isn't clear until it closes; on **Stop**, none is ever ready: move each to the map's Out of scope, linking the verdict, as the `study` skill's section 5 does for a Destination item.
- **The gate:** a map's build tickets wait until every Destination item of that map has its spec and its tickets.

**Held items.** An item whose issue's `## Blocked by` names an open owner task (`owner-task` or `ready-for-human`) rests on the owner's answer: `WF status --fetch` lists it under `held` (or `--json`'s `held`), naming the task. Skip it while the task is open, whether it is a build ticket (`WF ready` already says "blocked by owner task #<n>"), a spec or a planned item. Picked by number, say it's held on that task, and stop.

## 2. Pick one

**With an argument:** `map`, `spec` or `build` picks from that group. A number picks that issue; if it isn't ready, say why and stop.

**Without one,** in this order:
1. A map decision that needs the owner.
2. A clear map's next spec.
3. The first ready build ticket: `workflow:infra` first, then the lowest number.

Ready research tickets start at once in background subagents (the `research` skill), alongside whatever you pick.

Say which one you picked and why, in one line, with a build ticket's notes from `WF ready` beside it. "Spec #<n> has no clean review" is a warning, never a block: say so plainly ("its spec wasn't reviewed since it last changed: check it before building"), and the person decides whether to build it; in a ticket session, the briefing already did. For a build ticket, ask how first (below). Then claim it and follow the matching section of the flow. At the end, name what comes next.

**Offering a study** (the `study` skill), for a clear map's next spec, before its interview, as `start`'s **Offering a study** says (read its `SKILL.md`, `.claude/skills/start/SKILL.md` vendored or `../start/SKILL.md` as a plugin, for how the choice is asked):
- **A brand-new project** (no code of its own) with no stakes record yet (`WF research stakes --fetch` lists none): its first item offered one is always recommended a study, ahead of **Whether** below and even where a current note covers it, and that is the project's one study; a fix, wording or an internal change is never that item. From the first stakes record on (the study run or skipped), every later item takes **Whether** as in any project, its map's Destination items once its verdict is in (or it was skipped): an internal change is skipped with nothing asked or posted, and work a current note covers gets one stakes line naming the note.
- **A map whose Notes link a study's research issue** (a new project's): its Destination items wait for that study's verdict, whatever stakes records there are, ahead of **Whether** below: none is ready to spec until then, and then only as the verdict says, never on **Stop** (§1, "A clear map").
- **Whether:** fixes, wording and internal changes are skipped, with nothing asked or posted. Work a current note already covers (`WF research notes`) is skipped with no question, but with one stakes line naming the note. Any other feature: judge its stakes and say why, recommending a study for new people or a new need, for work that is high-stakes (safety, money, privacy and the law are things you must consider, not a list that decides), hard to undo, or a bet. An item already offered one gets no second offer: one that already has a stakes record that counts (the `study` skill's sections 2 and 3, "Which comments count"; for a Destination item, where the `study` skill's section 5 puts its records) was skipped, so go straight on to its interview, carrying on from its rounds; one already linking a study ("Study under way: #<n>") carries that study on.
- **Before judging,** read earlier judgements with `WF research stakes --fetch`, and show the size from `WF research estimate --fetch`, never as money; nothing caps a study. Where `--fetch` can't read them, give `--comments F --permissions F`.
- **They choose** **Run a study** or **Skip it**, with their reason: the stakes record (the `study` skill's section 2), on the item's issue when skipped, on the research issue when it runs. A Destination item's goes where the `study` skill's section 5 says.
- **On Run a study,** load `study` with the Skill tool and follow it; the interview waits for its verdict.

**Decision questions** are the ones whose answer is posted as the owner's. They follow the flow's rules (flow, "Decision questions"). Here they are a map decision's rounds, a spec's interview and its seams, and the questions a planning review's **Fixes** sends once a draft exists. Ask them as `start` does: read its `SKILL.md` (`.claude/skills/start/SKILL.md` vendored, or `../start/SKILL.md` from this skill's directory as a plugin), its "Choices" with their "Decision questions", for the evidence each recommendation carries, "yes to all", the check before each round, and what each round's post carries and leaves out, with its tags and confirmed replacement lines. Routing choices, such as "How to build it" below, keep their one line of why.
- **Each round** is posted as soon as it's answered, where the flow posts the owner's answers: the decision ticket, the item's issue, or a comment on the map naming its Destination item. A question a planning review's fix raises goes with the current rounds: the decision ticket for a map decision, and for a spec the item's issue or the map before the spec is published, and the spec's issue after.
- **Before asking anything,** read the rounds already posted for this spec or decision (on a map, the comments naming its Destination item). Then carry on from them, and number on from the last answer posted for it. Once an "End check" post is there, its rounds are over (the interview's, the seams' or a map decision's), though a planning review's fix questions still come: go on as `start`'s end check says.
- **After the last round,** before the spec, or a map decision's ADR or glossary, is written (or the decision recorded, when it changes neither), run the end check as `start`'s step 4 says ("Spec" and "Map").
- **A spec's tickets** are agreed with **Agree these**, then read against the spec by the breakdown check before any is published, as `start`'s step 4 says ("Spec", step 3).
- **Planning counts:** each piece of planning ends with a "Planning counts" comment, posted when and where `start`'s "Decision questions" says.

**How to build it, in an attended session:** ask with the `AskUserQuestion` tool, or as a numbered list where it isn't available:
- **Build it now (Recommended)**: the full review panel;
- **Build it with a light review**: one review round, for a low-risk change (`review-panel` §6, "The light review").

**On a ticket marked `Review: small`** (a line in its body), ask instead:
- **Build it now (Recommended)**: the small review, one round of Correctness with the security review and the explorer where they apply (`review-panel` §7, "The small review"); the full panel if the diff grows past the small threshold;
- **Build it with a light review**: as above;
- **Build it with the full panel**: every reviewer, as for an unmarked ticket.

The light review is always second, never recommended, and never chosen for them. When they already said how ("build #12", "build #12 with a light review", "build #12 with the full panel", "quick build #12"; the `build` argument alone isn't saying how), don't ask again: build it as they said. In a ticket session (`WORKFLOW_ROLE` set to anything but `attended` or `conductor`, or a branch named like the profile's `run.ticket_branch`), ask nothing: build as the briefing says.

## 3. Nothing ready

Say what is blocked and on what (an owner task, an open blocker, a PR in review), and stop.
