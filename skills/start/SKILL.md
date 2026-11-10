---
name: start
description: The guided start - ask what we're working on with clickable choices, split a request into items, propose a path for each (a quick ticket, finding a bug's cause, a spec, a map), record the plan as issues, and offer every next step as a choice, so the person never has to remember a command. Use at the first message of an attended session, on /start, or when the person isn't sure what to do next, and when they say "explain less" or "explain more".
---

# Start: what are we working on?

Guide the person from "what are we working on?" to work done, one choice at a time. They should never need to know a command or what comes after what: you know the flow, they make the decisions.

## Choices

**Every question is a choice to click.** Use the `AskUserQuestion` tool:
- **Options:** 2 to 4. When you recommend one, it comes first, its label ending "(Recommended)", with one line saying why (on a decision question, its evidence: below). "Other" is always added for their own words, so never add a "something else" option.
- **Building a ticket:** **Build it with a light review** is always the second choice, after the full build: never first, never "(Recommended)", never chosen for them. So on a ticket marked `Review: small`, after **Build it now (Recommended)** (the small review) and before **Build it with the full panel**.
- **Questions:** up to 4 in one call, when they don't depend on each other. More than 4 means several calls.
- **No tool:** where `AskUserQuestion` isn't available (a headless `-p` session), ask the same choices as a numbered list.

Ask in plain text only when the answer can't be a choice ("Tell me what you have in mind").

**Decision questions** are the ones whose answer is posted as theirs. They follow the flow's rules (flow, "Decision questions"). They are the interview's rounds and the seams (step 4, "Spec"), a map decision's rounds (step 4, "Map"), the questions a planning review's **Fixes** sends once a draft exists (step 4, "Spec" and "Map"), the questions of **Edit the spec first** and of **Add to an existing issue** on a spec, and the breakdown check's rounds (step 4, "Spec", step 3). Routing choices (which step comes next, such as **Write the spec** or **Build it now**) keep their one line of why.
- **Evidence:** a recommended option's description says what it rests on (the file, issue, ADR or earlier answer you checked), what it gives up, and what would make it wrong. Where there's no basis to prefer one option, none is "(Recommended)": lay the options out, each with what it gives up. Evidence that cites a research note runs the source check on it first (the flow's "Research", **The source check**).
- **"Yes to all"** (or any reply that accepts every recommendation at once) answers only the questions that have a recommendation. Ask each question without one again, on its own. A finding about their own words (an answer they typed or picked, not a recommendation they accepted) is asked on its own, never in a round they could answer with "yes to all".
- **Before each round,** `planning-checker` reads it, one read, before they see it (flow, "Decision questions", **The checks**): its recommendations, or with none, its options and what each gives up. A check's own rounds get no check before them: the end check's round, the breakdown check's rounds, settling a held-back ticket, and a quick ticket's **ask** round.
  - **Its inputs.** Fill `/tmp/plan-check-<issue>-round-<n>/` (`<issue>` being where the round will be posted) as the agent's "Your inputs" says. Put in the round's questions as you're about to ask them, each with its recommendation and evidence, and every post so far for the same spec or decision, the checks' own posts included, as `review-panel` §8's `answers.md` takes them (for a map's Destination item, the answers on the map decisions it draws on too). Add what they asked for that raised the round, word for word, tagged **the owner's own words**: their words in the item's issue (for a map's Destination item or a map decision, in the map's own item's issue), or the change they asked for in an edit after publishing. Add the rest as it is written, untagged: the item's issue, the map's Destination item or the decision ticket. For a question a planning review's fix raises, also add the draft or diff it reviewed and the finding behind the question. Once the spec is published, add its body as published. The checker reads them against the code, the ADRs, the earlier answers and the project's rules.
  - **Each finding** either changes the recommendation (a **fix**, or an **ask** showing your own recommendation was wrong) or is shown beside its question as "Check: …", in plain words with its example. A finding about no question in the round (an earlier answer's evidence, say) has its fix made and listed in the round's post when it's a **fix**, and joins the round as a question of its own, with its "Check: …", when it's an **ask**. A change that leaves no basis to prefer an option drops its "(Recommended)", as **Evidence** says. A question with a "Check: …" about their own words is asked on its own, as "Yes to all" says: straight after the rest of the round, as part of it, and posted with it once all its questions are answered.
  - **Then ask the round,** as its check left it. Its check is never repeated: the one read covers what you changed from its findings and each question asked on its own after the round. If the read fails, try it once more, and if it fails again, ask the round and say in its post that it wasn't checked, and why.
- **Each round** is posted as soon as it's answered, not only at **Stop here**, so a later session carries on from it. The interview's and the seams' rounds go on the item's issue (for a map's Destination item, a comment on the map naming it, and with neither, file an item's issue first). A map decision's rounds go on its decision ticket. An edit after publishing goes on the spec's issue, and so do the breakdown check's rounds. A question a planning review's fix raises goes with the current rounds: the item's issue (or the map) before the spec is published, the spec's issue after, and the decision ticket for a map decision. The post carries each question, your recommendation with its evidence, the checks' findings (when a check ran), and their reply quoted word for word. For the check before the round, the post lists each finding with whether it changed the recommendation, was shown as "Check: …" or was a fix made outside the round, or says "nothing found" (or "not checked", with why, when the read failed). Each reply is tagged **accepted recommendation** or **the owner's own words**. Their own words are any reply but a recommendation they accepted: an option picked over it or where none was recommended, or words they typed. It numbers the answers on from the last one posted for the same spec or decision, wherever that was (the item's issue, then the spec's issue), so a later line can name one. Earlier posts without numbers count in the order they were posted. A replacement or narrowing they confirmed is a plain line of its own ("answer 34 replaces 7: confirmed"), naming the issue of an answer posted elsewhere ("answer 3 on #301"). Sensitive data (`profile.md`) is left out of the post, and marked as left out.
- **Planning counts.** Each piece of planning ends with one comment headed "Planning counts", so they can see whether the checks catch things early. A step that didn't run says so ("no breakdown check: a quick ticket has none"), so a 0 always means a read that found nothing. Count from the posts on GitHub where they say it, wherever they were posted for this spec or decision (the item's issue, closed as "Planned as #<spec>", the map's comments naming its Destination item, the decision ticket and the spec's issue): the round posts, the posts headed "End check", "Re-read", "Breakdown check" and "Breakdown re-read", and the confirmed lines. Count the rest as you ran it: a quick ticket's checks, which post nothing, the re-reads after the draft, and the planning rounds. A part an earlier session ran and didn't post reads "not known", with why, never a guess. The comment gives each of these as a number:
  - **The checks before each round:** their findings, and how many changed a recommendation, counted from the round posts' "changed the recommendation" only, with any round "not checked" named.
  - **The findings of each read,** **ask** and **fix** apart: the end check, each re-read (the end check's, and each one after the draft), and the breakdown check and its re-read, each read on its own line.
  - **The answers replaced after the end check:** the confirmed replacement and narrowing lines from the end check's round on, those in its "End check" post included. A later edit's comment counts only the lines its own rounds posted.
  - **The questions sent after the draft:** those a planning review's **Fixes** sent, and an edit's own questions.
  - **The findings of each planning round** (`review-panel` §8: the draft's, and those of the session's ADR or glossary pull request), by reviewer ("round 1: Spec 4, Correctness 2").
- **Where the planning counts go:**
  - **A spec:** on the spec's issue once its tickets are published and the session's ADR or glossary pull request, if it has one, has had its planning review (step 4, "Spec", step 4). It counts the interview, the end check, the planning review of the draft, any edit made while the spec owes it, the breakdown check and that pull request's rounds. A session that worked on the spec after it was published can end while the spec owes its "Planning counts" (below), however it ends: **Stop here**, the tickets left to a fresh session, or after an edit, there or after later items of the plan. Its last step is then to post on the spec's issue what it counted that no post says, headed "Planning counts so far", after "Commit what the session wrote" and that pull request's planning review. The session that posts the counts adds up every such comment. A spec owes its "Planning counts" until a comment headed exactly "Planning counts" follows its first "Breakdown published" comment (settling a held-back ticket can post another) ("Planning counts so far" isn't one): before that first "Breakdown published", and after it until that comment, the case "Carrying on" (§1) finishes. The exception is a spec whose tickets were published with neither a "Breakdown to publish" post nor a "Breakdown published" comment (one from before these counts): it owes none.
  - **A later edit** to a published spec, made when the spec owes no "Planning counts" of its own (above): its own comment on the spec's issue, once the edit is saved and the tickets it touches are changed, counting that edit's rounds, re-reads, questions and planning rounds.
  - **A quick ticket:** on the ticket once it is published (step 4, "Quick ticket", step 2), counting its end check and its one re-read, the routes through **File the fix as a ticket and build it** and §5's **Ready to build** included.
  - **A map decision:** on its decision ticket when it's recorded, before it's closed (step 4, "Map").

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

**Tell yourself the new level** whenever you record one, answer or change alike, in one line: "From now on: <level>." With *developer* (the first question's answer, or "explain less"), stop explaining the glossary's words for the rest of the session. After "explain more", read the glossary again (`.claude/workflow/docs/glossary.md` vendored, or `docs/glossary.md` beside `skills/` in the plugin), if it is there, and from then on explain each of its words in the glossary's wording, in one or two sentences, the first time you use it in this session, and never again in this session. A word you used without explaining it (while at *developer*) still counts as unexplained. Never explain them in what you write on GitHub (pull request descriptions, comments, reports).

## 0. Read the first message

The kit's hook brings this skill at a session's first message. Read that message before showing anything:

| The message | What to do |
|---|---|
| One clear request: a question, a named issue ("build #262"), one small change with an obvious place ("rename the Save button to Done") | Do it. No menu. A change to the code goes on a branch of its own with a pull request for them to merge (only pull requests reach the base branch); if it turns out bigger than it looked, offer a quick ticket instead. |
| **More than one thing**, even if one of them is small ("add XYZ, and the greeting is wrong") | Step 1's look around, without the question, then step 2 with their words. Never start on one of them before the plan is agreed. |
| One piece of work to plan: a feature, a change to how something works, something broken with no known cause | The same: step 1's look around, then step 2 |
| Anything vaguer ("hi", "let's work on the app"), or `/start` | Step 1 |
| The conversation was already under way (a resumed session) | Follow the hook's reminder (below) instead of this table: carry on with what was agreed, and plan any new work first |

**Later messages.** At each later message of an attended session, the hook adds a one-line reminder: new work that isn't part of the plan or ticket already agreed in this session is split into items with a path for each and the plan agreed first (step 2); a question, a named issue or one small change with an obvious place may go ahead (on its own branch, with a pull request); replies to your own questions carry on. Never in a ticket or conductor session, with `guided_start = false`, at a slash command, or when the message already brings the flow's context.

## 1. Look around, then ask

Run:

```bash
WF status --fetch
```

Where `gh api` isn't available, fetch the issues (`state=all`, with labels, bodies, `created_at`, `comments` and `sub_issues_summary`) and the open PRs with the GitHub MCP tools. Save them as JSON and pass `--issues issues.json --prs prs.json`.

It reports:
- whether the kit is set up, and whether the project is brand new (no code of its own);
- the kit's version here, and whether a newer release is out (`Kit version:`; the session's start says so too);
- an unattended run (`workflow:run`), claimed work (`workflow:in-progress`) and open PRs;
- tickets carried on (`workflow:carry-on`, its `carry_on`): handed on by an earlier session with their review not yet clean, and adopted by no run;
- research under way ("Research under way", its `research`): open issues labelled `research`, a study or a note to fix, never new issues to sort;
- items held by an open owner task under their issue's `## Blocked by` (its `held`, with the task): "Held items", below;
- items planned at an earlier start and not begun;
- maps, open specs (and parent issues) and ready build tickets;
- what waits on a person (owner tasks, `needs-human`, `needs-info`);
- new issues to sort (`needs-triage`, or no label).

Tell the person what matters in two to four lines, for example: "PR #297 is waiting for your merge. Two items from last time aren't started: #301 the booking page (quick ticket), #302 booking reminders (spec). One ticket is ready: #262." Leave out what doesn't matter.

**A ready ticket's note.** Before you name a ready ticket in those lines or offer it ("Carry on", or a ready ticket in "What are we working on?"), read their notes, in one call for all of them: `WF ready --fetch --only <n>` (`<n>` the ticket numbers, comma-separated; or with `--issues`/`--prs` files, as `next` says). Show a note beside the ticket, in its line and in the option's description: "spec #<n> has no clean review: check it before building" means its spec wasn't reviewed since it last changed, and "couldn't read its reviews" that it couldn't be told. Either is a warning, never a block: offer the ticket as usual, and the person decides.

**In solo mode** (status says `Solo mode: yes`), one of those lines says so, with what it means for them: "This project is in solo mode: nothing on GitHub protects `<base branch>` yet, so the kit refuses any change straight to it, and all work goes through pull requests." Name the profile's base branch. Don't offer "Protect `main`" here: it is offered when they ask, and in a refusal.

**"Check the set-up"** (the `check-setup` skill) is offered only at these moments, never at every session start:
- **On a local gap.** Read status's `set_up` first: when it is false, the gap is the missing profile, so offer setting the kit up (below), not this. Otherwise, when status reports a local gap (the line `Local gaps: N (…)`; in `--json`, `local_gap` is `true`, with the lines in `local_gaps`), one of your lines names the gaps in a few words, from `local_gaps`' messages in `WF status --json` (the run at the session's first message has them; else run it), which are already worded for the person: the text line gives only their ids. Then offer **Check the set-up** in "What are we working on?".
- **In solo mode, once a session,** beside the solo-mode line above: offer **Check the set-up** in "What are we working on?". Once it has been offered in this session, whatever they picked, don't offer it again for solo mode.
- **On an old `python3`.** When `WF status` stops with "workflow needs Python 3.11", that is not "no gap": `status` can't run on an older `python3`. Say `python3` is older than the kit needs, and offer **Check the set-up**: doctor still runs there, with its short report and the fix.

Only the local look counts here: `status` makes no network call for it, and the guided start never runs `workflow doctor` itself. Never in a ticket or conductor session (above, "Only in attended sessions").

**If the kit isn't set up here** (only possible with the plugin, since otherwise this skill isn't there), ask "This project isn't set up for the workflow kit yet". The options:
- **Set it up (Recommended):** follow the kit's `setup-workflow` skill. It is user-only, so read its `SKILL.md`.
- **Work without the kit for now.**

**Then ask: "What are we working on?"** Pick two to four options from what status shows, the most useful first:

| Option | Offer it when | Its description |
|---|---|---|
| **Carry on: #<n>, handed on (Recommended)** | Status lists a ticket under `carry_on`: one option for each, as room allows, lowest number first. It comes first ("One recommendation", below) | "Its review wasn't clean when its session stopped; we carry it on from the hand-off." |
| **Update the workflow kit to <version> (Recommended)** | A newer kit release is out, no run is in progress, and no update pull request is open (status's `kit_update_pr`; else offer "Carry on: the kit update PR #n"). It comes first, before a brand-new project's map | "A pull request for you to merge, with what's new; then we carry on." |
| **Carry on: <the thing>** | Something is under way (the table below): name the most pressing one, never a held item but to settle a held-back ticket ("Held items", below); a ticket under status's `carry_on` has its own option (above) | What it is and what happens next |
| **Check the set-up** | Status reports a local gap, or `python3` is too old for it: then it is the recommended option and first, ahead of a brand-new project's map; when a kit update is offered, the update stays first and recommended, and this comes second, without "(Recommended)". Or once a session in solo mode, as above, not recommended | "What's set up and what isn't, each with its fix; it changes nothing." |
| **Check whether #N is ready to merge** | Status lists an open PR: one for each it lists, as room allows, leaving out one already offered as "Carry on" or the pull request of a ticket offered under `carry_on` | "Ready, or not yet and why; nothing merges until you choose." |
| **Something new, or a change to what's there** | Always | "Tell me in your own words; several things at once is fine." |
| **Fix something that's broken** | Unless four better options fill the list | "Describe what goes wrong; I'll find the cause." |
| **Sort the new issues (N)** | Status lists issues to sort | "One by one: ready to build, needs more info, or won't do." |
| **A brand-new project or a large effort** | The project is brand new (then first and recommended, unless a kit update or a local gap's **Check the set-up** is offered: then after them, without "(Recommended)"), or they mentioned something big | "Chart it as a map of decisions first." |
| **Run the ready tickets unattended (N)** | Tickets are ready and no run is in progress | "Built in parallel sessions while you're away." |

**One recommendation.** With a ticket under `carry_on`, its **Carry on** (the lowest number's) comes first and is the only "(Recommended)" option, whatever the rows above say: the rest keep their order after it, without "(Recommended)".

**Held items.** An item whose issue's `## Blocked by` names an open owner task (`owner-task` or `ready-for-human`) rests on the owner's answer: status lists it under `held` (status's `held`, naming the task), not in its own section. One already waiting on a person (labelled `needs-info`, `needs-human`, `owner-task` or `ready-for-human`) stays under status's `waiting` instead, unless it is a spec, a parent issue or a planned item, and the same rule holds for it; an issue naming itself is never held by itself. Say it waits on that task, and never offer it ("Carry on", a ready ticket or a spec's next step) or start it while the task is open. The one exception is a build ticket held back by the breakdown check (its row under "Carrying on", below): settling its open findings is planning, not building, and doesn't rest on the task's answer, so offer to settle it. It stays held, and isn't built, until the task closes. Once the task closes, status lists it in its own section again. A map's Destination item has no issue: it is held by a `Blocked by: #<n>` line beside it in the map's body, which status doesn't read. Read the map's body for it, and skip that item as a clear map's next spec while #<n> is open (a study of it already under way still carries on to its verdict).

**Carrying on.** What "Carry on" does depends on what is under way. Three rows need more than status's lines: read the bodies of the build tickets `WF status --json` lists as waiting, held or to sort (its text shows only eight of each) for a `## Breakdown check` section, and each open spec's comments for a "Breakdown to publish" post with no "Breakdown published" comment after it, and for a first "Breakdown published" comment with no comment headed exactly "Planning counts" after it.

| Under way | What to do |
|---|---|
| A PR waiting for them | Give its link, what it does and its checks. Ask **Check whether it's ready to merge (Recommended)**, which loads `merge-check` for it, **Review it with me**, **I'll merge it myself** or **Later**. |
| A carry-on ticket (`workflow:carry-on`: under status's `carry_on`, or claimed with it) | An earlier session handed it on with its review not yet clean (a run's end time, or attended work's stop after 10 reviews), leaving a hand-off comment on its pull request. Ask **Carry on (Recommended)** or **Later**, which leaves it as it is. On **Carry on**, load `build-ticket` for it ("carry on #<n>"): its claim (§1) takes `workflow:carry-on` off before any other write and puts `ready-for-agent` back, so no run adopts it as well, then it goes on from §3's "Carrying on after a hand-off" on its pull request's branch: it reads the hand-off (`WF merge-check --fetch <PR> --json`'s `hand_off.url`) and carries the review on from there, reviewing any later commits too. It is not a retry, and attended work's count of 10 reviews starts again. On a branch named like `run.ticket_branch` (a run's), the session works under a ticket session's rules there (Rules, below). With no open pull request, `build-ticket`'s carry-on path doesn't apply: say so, make that claim yourself (`workflow:in-progress` on, `workflow:carry-on` off and `ready-for-agent` back, in one write), and carry on as for claimed work. A ticket also labelled `workflow:in-progress` is listed as claimed, and `build-ticket` §1 stops on it. With a run in progress, it is the run's: leave it to its run. With none, offer only **Release it** (the row below): it is then a carry-on ticket again. |
| Work claimed (`workflow:in-progress`), no run in progress | An earlier session stopped part-way. Read the issue's comments and look for its branch (an open PR that closes it, or a branch naming its number). Ask **Carry on from there (Recommended)**, then follow `build-ticket` on that branch, or **Release it**, which removes the label so `/next` can take it. One also labelled `workflow:carry-on` is the carry-on row's (above), not this row's. |
| A research issue (status's `research`) | A study under way, or an issue a session filed about a note: a claim it found wrong, or a key source that changed or can't be fetched (the flow's "Research", **The source check** and **Fixing a wrong note**). The `study` skill's section 5 is the one rule for a research issue: follow it, not this row, where they meet. Read the issue's body and comments, then ask **Carry on (Recommended)** or **Later**. On **Carry on**, it continues the study from the last record posted on the issue, with the `study` skill (load it with the Skill tool); or, for an issue about a note, it runs the source check on the note and asks the owner's choice (go on, fix the note or re-run the study, a routing line on the issue), unless an "Owner chose" line on it from an account with write access already chose and the check reports the same paragraphs (**Choosing once**). A research pull request that fixes the note or re-runs the study, with its research check, closes the issue (`Closes #<n>`). No note changes (the owner chose to go on, or the claim was right): close the issue with that routing line. |
| An item whose issue links an open research issue (a "Study under way: #<n>" comment on it, or for a map's Destination item a comment on the map naming it, the `study` skill's section 5), or a map's open decisions or a clear map's Destination items while its Notes link an open research issue (a new project's study) | Look for that comment on each planned item and open spec you'd offer, and on a clear map for each Destination item with no spec linked, and on a map for an open research issue linked from its Notes (its decisions and a clear map's next spec, `next` §1). The item is offered as that study's **Carry on** (the row above, for #<n>), never started afresh on its own path or offered a second study. Once an item's own research issue closes, its verdict, on the research issue, says what follows (the `study` skill's section 11). On **Build it**, the item carries on as its own row says. On **Prototype first**, the item waits until its prototype is done. For a Destination item, the prototype is the `wayfinder:prototype` ticket linking the verdict, which `next` charts with no blockers when the map has none, never one charted before the verdict (`next` §1, "A clear map"), offered as the map's decision (the row that loads `next`, below), and the item's spec comes only once it has closed. For a planned item, offer **Carry on: the prototype for #<item> (Recommended)** or **Later**, which loads the `prototype` skill with the study's findings and its ranked questions. **Carry on** ends by posting a comment on the item's issue that gives the prototype's branch and the answer it settled, even where that skill's "Capture it when done" left them elsewhere (a commit, another issue). Nothing is folded into the real code before the spec: that skill's "Fold any validated decision into the real code" doesn't apply here, so the prototype stays on its throwaway branch and its answer goes to the item's interview (the `study` skill's section 11, and the flow's order: a spec, then build tickets). The prototype is done once a comment on the item's issue, posted after the verdict, gives the prototype's branch and the answer it settled (that skill's "Capture it when done"); then the planned item carries on as its own row says. On **Stop**, the item has already moved out, linking the verdict: a Destination item to the map's Out of scope, a planned item closed as not planned (the `study` skill's sections 5 and 11; one still there is moved or closed now), so it isn't offered. A map's decisions and Destination items held for a study its Notes link go by the verdict row below once it closes. |
| A planned item | Read its body and comments. One linking an open research issue, or a closed one whose verdict still holds it (the row above), is the row above's, not this row's. A `path=spec` item may have an interview's rounds posted in its comments ("Decision questions", above): read every one, with its tags, its evidence, the checks' findings and any confirmed replacement line, which says which answer stands. Then carry on the interview from them, numbering on from the last answer posted, or go to the spec if nothing is left to ask. Once a post headed "End check" is there, the interview is over: carry on from it as the end check says (step 4, "Spec"). Then step 4 for its path. |
| An open spec whose "Breakdown to publish" post has no "Breakdown published" comment after it | Its publishing stopped part-way: carry on as step 4, "Spec", step 3 says |
| An open spec with no tickets | Read the rounds posted on the spec's issue first (an edit after publishing, and the breakdown check, post there), then `to-tickets` for it (step 4, "Spec", step 3, which says how to carry on a breakdown check) |
| An open spec whose first "Breakdown published" comment has no comment headed exactly "Planning counts" after it ("Planning counts so far" isn't one) | Its counts were never posted: finish step 4, "Spec", step 4 where it stopped (its pull request's planning review), then post them as "Decision questions" says, adding up every "Planning counts so far" on it |
| A build ticket held back by the breakdown check (a `## Breakdown check` section, held back as step 4, "Spec", step 3 says) | Settle it as that step's "Settling a held-back ticket" says |
| A map whose Notes link a research issue that has closed (a new project's study, its verdict on the issue) | The verdict says which of its decisions is offered (`next` §1, "A map"; the `study` skill's section 11 says what each verdict means): on **Build it**, as on any map (the row below); on **Prototype first**, only the prototype, until it closes: the `wayfinder:prototype` ticket linking the verdict, which `next` charts with no blockers when the map has none, never one charted before the verdict; on **Stop**, none, nor its next spec: offer **Carry on: close map #<n>** (its study stopped it), which loads `next` with the map, and `next` closes the map as not planned with its open decision tickets, linking the verdict. |
| A map decision, a clear map's next spec, or a ready ticket | Load `next` with the Skill tool, with that issue |

**What the other options lead to:**
- **Update the workflow kit:** in plugin mode (no `.claude/workflow/lock.json`), tell them to type `/plugin update pairnexus-workflow@pairnexus`. Vendored: read the project's `.claude/skills/update-workflow/SKILL.md` (user-only, so read it) for where the kit lives and how to clone the new release outside the project, then read **that release's** `$KIT/skills/update-workflow/SKILL.md` and follow it. It ends with a pull request for them to merge. Then ask "What are we working on?" again, without this option. With a run in progress, don't offer it: a run stays on the version it started with.
- **Check the set-up:** load `check-setup` with the Skill tool. It shows the report and offers the upgrades it names, each with "Not now". Then ask "What are we working on?" again, without this option.
- **Check whether #N is ready to merge:** load `merge-check` with the Skill tool, for that PR. Only when they pick it: never run the check on its own.
- **New, a change, or a fix:** ask in plain text, "Tell me what you have in mind: as much or as little as you like." Then step 2.
- **Sort the new issues:** step 5.
- **A brand-new project or a large effort:** step 2, with the path already chosen: a map.
- **Run unattended:** a run can't start from this session.
  1. It needs a new cloud session in the conductor environment (the profile's `run.conductor_environment`), in **Auto** permission mode, with the words "Run the backlog unattended". Tell them exactly that.
  2. If a map is open with Destination items still unspecified, say so first: the conductor will recommend leaving its tickets out (flow §1, "The gate"). A Destination item with a `Blocked by:` line in the map's body is left out of that, whether its task is open or closed.

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
   - an `Area:` line;
   - where its structural lines go, by the overview's rules: the code's page (a cross-cutting rule: the overview), a new module's full page, or for a file no page covers, a small page named by its folder path (`src--orders.md`, `_root.md`);
   - `## Bar`, as flow §2 says ("The bar"): a ticket may carry one, and one whose area is in the profile's `run.bar_areas` must;
   - a `Review: small` line, only when you expect the change to stay within the small threshold (the profile's `run.small_max_lines` changed lines in `run.small_max_files` files, outside tests) and to add no endpoint, table, screen or setting (flow §2). Removing the line opts the ticket out.

   **The end check,** before **Publish it** (flow, "Decision questions", **The checks**). Give `planning-checker` the drafted ticket and the item's issue, for one read of the decisions you made for them that the item's issue doesn't make. With no item's issue (a quick ticket offered in step 0, or the new one **Add to an existing issue** makes), file one first, as step 3, "Record the plan", does, with what they asked in their words. Fill its scratch directory, `/tmp/plan-check-<issue>-end-<n>/` (`<issue>` being the item's issue), as the agent's "Your inputs" says. It is one of the flow's checks, not the planning review: one read and one re-read in all, and none of it is posted as their answers, since a quick ticket posts none.
   - **Its ask findings** are asked first, before **Publish it** is shown: one short round of choices, each with your recommendation and its evidence where there's a basis for one, and **Leave them open** among its options. "Yes to all" answers only the questions with a recommendation: ask each other one again on its own. A finding about their own words (the item's issue, or what they typed in a reply) is asked on its own, never in a round they could answer with "yes to all". Change the draft to their answers, and take out of `## Decided for you` any decision an answer settles: it is theirs now. A finding they leave open goes into `## Decided for you`, marked open.
   - **Its fix findings** you make in the draft yourself, and list them above **Publish it**, where they can object.
   - **Decided for you:** each decision the check lists under "Decided for you" goes into the ticket's body under `## Decided for you`, in plain words, with its evidence: what it rests on, what it gives up and what would make it wrong. These are decisions you made for them, not tagged as their answers or as an accepted recommendation. With none, the heading says "None". An issue the ticket waits for goes in `## Blocked by` as `#n`, since readiness reads only issue numbers there. An open question about what it waits for stays here, marked open, and doesn't hold the ticket back: once its **ask** round is answered or left open, nothing a check found stops the publish (flow, "Decision questions"). Elsewhere in the section, name another issue as "see #n", never "blocked by #n": `workflow ready` reads "blocked by" with an issue anywhere in the body as a blocker. Sensitive data (`profile.md`) is left out of the section, and marked as left out.
   - **One re-read in all,** of only what changed since the end check (what their answers to its **ask** findings and any **Change it** changed, and the fixes), against the rest of what it read. It runs on the draft as it stands when **Publish it** is last shown: the first time they pick **Publish it** on a draft that changed since the check (beyond writing its `## Decided for you`), run it before publishing. Fill `/tmp/plan-check-<issue>-reread-<n>/` as "Your inputs" says, with their replies word for word, each reply to an **ask** tagged as the agent's inputs say. Its findings are never asked: make its **fix** findings, and its **ask** findings go into `## Decided for you`, marked open. Its own "Decided for you" list updates the section for what changed, except a decision their replies settle, which stays out. Publish straight away only when it found nothing and left the section as it was. Otherwise show the draft once more, with its fixes and the section's new items above **Publish it**. With nothing changed, there's no re-read.
   - **After the re-read,** a **Change it** gets no further read: make it, add each decision it makes for them to `## Decided for you`, marked open (no read has seen it), and show the draft again.

   Show it, with the decisions made for them (each with its evidence, the open ones marked open) and the check's fixes above **Publish it (Recommended)**. Then ask **Publish it (Recommended)** or **Change it**.
2. Publish by editing the item's issue into the ticket: replace its body (its `## Decided for you` included), drop the marker, and add `ready-for-agent`. The item's issue becomes the ticket. Then post its "Planning counts" on it ("Decision questions", above).
3. Ask:
   - **Build it now (Recommended)**: load `build-ticket` with the Skill tool, on a fresh branch;
   - **Build it with a light review**: the same, asking `build-ticket` for a light review (`review-panel` §6, "The light review"): one review round, for a low-risk change;
   - **Leave it ready for later**: `/next` or a run picks it up;
   - **Next item**.

   **On a ticket marked `Review: small`**, ask instead (`AskUserQuestion` takes four choices, so with it leave out **Next item**: they can still say it under "Other"):
   - **Build it now (Recommended)**: load `build-ticket` with the Skill tool, on a fresh branch: the small review, one round of Correctness with the security review and the explorer where they apply (`review-panel` §7, "The small review"), or the full panel if the diff grows past the small threshold;
   - **Build it with a light review**: as above;
   - **Build it with the full panel**: the same, asking `build-ticket` for the full panel, as for an unmarked ticket;
   - **Leave it ready for later**: `/next` or a run picks it up;
   - **Next item**.

**Find the cause first:**
1. Follow `diagnosing-bugs` until a command fails on the bug and you know why.
2. Say what you found in two lines, and ask:
   - **File the fix as a ticket and build it (Recommended)**: then "Quick ticket" above, on the same issue, with the failing command in its acceptance criteria, and its end check and `## Decided for you` as there;
   - **It needs decisions: make it a spec**: then "Spec" below;
   - **Stop here**: comment on the item's issue with what you found.

**Offering a study** (the `study` skill), before a Spec item's interview and before a Map item's charting. A study researches the people and the problem first. A Quick ticket, Find the cause first, Add to an existing issue and Answer it never get one.
1. **Whether to offer it:**
   - **A brand-new project** (no code of its own) with no stakes record yet (`WF research stakes --fetch` lists none): its first item offered one is always recommended a study, ahead of the bullets below and even where a current note covers it, and that is the project's one study; a fix, wording or an internal change is never that item. From the first stakes record on (the study run or skipped), every later item takes the bullets below as in any project, its map's Destination items after the next bullet's wait where the map's Notes link a study's research issue: an internal change is skipped with nothing asked or posted, work a current note covers gets one stakes line naming the note, and any other feature is judged.
   - **A map whose Notes link a study's research issue** (a new project's): its Destination items wait for that study's verdict, whatever stakes records there are, ahead of the bullets below: none goes on to its interview until then, and then only as the verdict says, never on **Stop** (`next` §1, "A clear map").
   - **Fixes, wording and internal changes:** skipped, with nothing asked or posted.
   - **Work a current note already covers** (`WF research notes` lists the current notes): skipped with no question, but with one stakes line naming the note, posted as the stakes record (step 3).
   - **Any other feature:** judge its stakes and say why. Recommend a study when it involves new people or a new need that no current note covers; when it is high-stakes, by your judgement (safety, money, privacy and the law are things you must consider, not a list that decides); when it is hard to undo (stored data, pricing, a public promise, a legal commitment); or when it is a bet (they say "not sure" to whether users want it). Otherwise recommend a skip.
   - **An item already offered one** gets no second offer, in this session or a later one: one that already has a stakes record that counts (the `study` skill's sections 2 and 3, "Which comments count"), on its issue, or for a map's Destination item where the `study` skill's section 5 puts its records, was skipped, so go straight on to the interview or the charting, carrying on from its rounds; one that already links a study (a "Study under way: #<n>" comment) carries that study on.
2. **Before judging,** read the earlier judgements, for similar work, and judge alike: `WF research stakes --fetch`. Then the study's size: `WF research estimate --fetch` ("about 11 agents, roughly 1.2M tokens", or "not learned yet" before any full study), shown as it prints it, never as money; nothing caps a study. Where `--fetch` can't read them, give the inputs as files, `--comments F --permissions F`, as the `study` skill's section 3 says.
3. **Ask** "<the item, short>: study it first?", the stakes and your why above the question, the size in the study's option. Your recommendation comes first:
   - **Run a study**: the intake, the panel, then the verdict, before the interview (for a new project, the intake and the panel before charting's first step);
   - **Skip it**: straight to the interview or the charting. Ask their reason in one line, unless they already gave it.

   It is a routing choice, recorded in one line with the reason and their choice: the stakes record (the `study` skill's section 2), on the item's issue when the study is skipped, and on the research issue when it runs. For a map's Destination item, follow the `study` skill's section 5 for where it goes.
4. **On Run a study,** load `study` with the Skill tool and follow it from its section 4: the research issue first (its section 5), then the intake. The interview waits for its verdict, as its section 4 says; a new project's charting starts once its intake and panel have run.

**Spec** (flow §2), all in one session where it fits:
1. **The interview.** It comes after **Offering a study** (above). Load the `grilling` and `domain-modeling` skills with the Skill tool (that's all `grill-with-docs` does), and interview them about the item. Its questions are decision questions ("Decision questions", above). Ask each round's questions as choices:
   - one question per decision;
   - your recommended answer as the first option, with its evidence, and real alternatives after it; with no basis to prefer one, no recommendation;
   - plain text only for a question with no sensible options.

   Whenever a round is asked in a message instead (as `grilling` lays one out), each question takes the flow's labelled parts (flow, "Decision questions", **Asked in a message**): the question, ➡️ **Recommended:** with its evidence (or "Recommended: none" and why), and **Alternatives:**, never the recommendation as the question's first sentence or a bold paragraph; a choice keeps its recommended first option, "(Recommended)", as above.

   Look facts up yourself, in the background; only decisions go to them. Each round is checked before it's asked ("Before each round", above), and posted as soon as it's answered, tagged, before the next round is asked: on the item's issue, or for a map's Destination item in a comment on the map naming it ("Decision questions", above).

   When nothing is left to ask, confirm your understanding in a few lines and ask:
   - **Write the spec (Recommended)**;
   - **There's more to discuss**;
   - **Stop here**: post their answers so far on the item's issue, each question with the answer quoted word for word, tagged, in the same form as each round. Every answered round is already posted, so this posts only a round not yet there. For a map's Destination item, they go in a comment on the map naming it. The next session carries on from them.
2. **The spec.** Read `to-spec`'s `SKILL.md` and follow it.
   - Ask the seams as a choice, with the seams listed above the question: **These seams (Recommended)**, with its evidence (what each seam rests on in the code, what it leaves untested, and what would make it wrong), **Fewer, higher seams** or **Change them**. It is checked before it's asked ("Before each round", above).
   - Post their answers, the seams among them, on the item's issue (or, for a map's Destination item, a comment on the map naming it). The interview's rounds are already there, so this is the seams' round. Post it as soon as it's answered, tagged, each question with the answer quoted word for word (flow §2).
   - **The end check,** once the seams' round is posted and before you write the draft (flow, "Decision questions", **The checks**). Give `planning-checker` all the answers together, for one read: every round posted for this spec, and for a map's Destination item the answers on the map decisions it draws on too, as `review-panel` §8's `answers.md` takes them. Fill its scratch directory, `/tmp/plan-check-<issue>-end-<n>/`, as the agent's "Your inputs" says. It is one of the flow's checks, not the planning review: one read, one re-read, and no spec record. Every post it leads to goes where the rounds are (for a map's Destination item, a comment on the map naming it), headed "End check" or "Re-read", one for each read, even one that found nothing ("nothing found"). A session that carries on reads them first: with an "End check" post there, it never runs the end check or asks its questions again, and runs the re-read only if no "Re-read" post follows. What was left open there is what's left (below), never a question for the interview.
     - **Its ask findings** come back to them as one short round, asked as decision questions ("Decision questions", above): each with your recommendation and its evidence where there's a basis for one, and **Leave them open** among its options. A finding about their own words is asked on its own, as "Yes to all" says, and posted with this round once all its questions are answered. This round gets no check of its own before it's asked, since its re-read reads what it changed. Post it as each round is, with the fixes listed in it. A replacement they confirm is its plain line.
     - **Its fix findings** you make yourself, and list them where they can object: in that round's post. With no round (nothing to ask), list them in a comment straight after the read.
     - **Then one re-read** of only what changed since the end check (that round's answers and the fixes), against the rest of what the end check read, and stop. Fill `/tmp/plan-check-<issue>-reread-<n>/` and tell it the read it follows, what that round changed and the fixes, as "Your inputs" says. With nothing changed, there's nothing to re-read. Its findings are never asked: make its **fix** findings, and its **ask** findings are what's left. List both in a comment straight after it.
     - **What's left** (a question left open or unanswered, and a re-read's **ask** findings) goes into the spec's Further Notes as open questions, before it's published. A finding answered **Leave them open** goes into Further Notes with the rest. It's never only in the session's closing choices.
   - Review the draft before publishing it: `review-panel`'s planning review (§8), until a round is clean. A fix that would change what a decision means is a question for them first, asked as a decision question ("Decision questions", above), checked before it's asked ("Before each round", above) and posted where the interview's rounds are, as soon as it's answered; anything still open after the last round is named in the handover.
   - Publish the reviewed text as is, under flow §2: labels `spec` and `ready-for-agent`, the decision behind each choice cited, and, for a map's Destination item, linked from the map. Check the published body's hash against the reviewed file (`review-panel` §8), then post each round's spec record on it, oldest first.
   - Close the item's issue as completed, with "Planned as #<spec>".

   Ask:
   - **Split it into tickets (Recommended)**;
   - **Edit the spec first**: the edited body gets another planning round and its spec record (`review-panel` §8) before the tickets, and the questions the edit raises are decision questions ("Decision questions", above), each round checked before it's asked ("Before each round", above) and posted on the spec's issue as soon as it's answered, tagged;
   - **Stop here**: `/start` offers the tickets next time, from the open spec. Last, after "Commit what the session wrote" (step 4, "Spec", step 4) and its pull request's planning review, post what you counted that no post says on the spec's issue, headed "Planning counts so far" ("Decision questions", above).
3. **The tickets.** Read `to-tickets`' `SKILL.md` and follow it, with flow §2's additions. Show the breakdown with a link to the spec it's read against: each build ticket with its full body drafted (its criteria, `## Blocked by`, and `## Bar` where it has one: a ticket whose area is in the profile's `run.bar_areas` must, flow §2), the owner tasks, and the edits to existing issues, each as the edit itself. An edit is only to an open issue that isn't claimed (`workflow:in-progress`) or built (closed, or with an open PR): a change to one that is becomes a new build ticket, as **Add to an existing issue** says. An edit to a spec gets its planning round and spec record, as **Add to an existing issue** says too. Then ask:
   - **Agree these (Recommended)**;
   - **Change the sizes**;
   - **Change what blocks what**;
   - **Merge or split some**.

   Repeat until they agree.

   **The breakdown check,** after **Agree these** and before anything is published (flow, "Decision questions", **The breakdown check**). Give `planning-checker` the breakdown as agreed, for one read against the spec. Fill its scratch directory, `/tmp/plan-check-<spec>-breakdown-<n>/` (`<spec>` being the spec's issue), as the agent's "Your inputs" says: the spec, the drafted tickets in full, the owner tasks and the edits to existing issues, with every round posted for the spec (for a map's Destination item, the answers on the map decisions it draws on too). It reads:
   - every decision and acceptance criterion of the spec in exactly one build ticket, owner task or edit to an existing issue;
   - criteria every ticket carries (the changelog note, the full suite) and decisions that build nothing (out of scope, or something left unchanged) are left out;
   - each ticket's `## Blocked by` against what it builds on;
   - each ticket's `## Bar` against the spec's, where the spec gives one.

   It is one of the flow's checks, not the planning review: one read, one re-read, and no spec record. Every post it leads to goes on the spec's issue, headed "Breakdown check" or "Breakdown re-read", one for each read, even one that found nothing ("nothing found"): the post of the round that follows the read, or with no round, the read's own comment straight after it. Each carries the breakdown that read checked, in full, so a session that carries on starts from it.
   - **Ask or fix:** here only wording is a **fix**. Anything that moves a criterion or a decision between tickets, owner tasks and edits, or changes a `## Blocked by`, is an **ask**, whatever the checker marked it. You make the **fix** findings yourself, and list them in that read's post (above).
   - **Its ask findings** come back to them as one short round before anything is published, asked as decision questions ("Decision questions", above), each with **Leave them open** among its options. This round gets no check of its own before it's asked. Post it on the spec's issue as each round is. Then redraft the breakdown as the answers say.
   - **Then one re-read** of only what changed (that round's answers, the redraft and the fixes), against the rest of the breakdown and the spec. Fill `/tmp/plan-check-<spec>-reread-<n>/` as "Your inputs" says, with the spec and the redrafted breakdown in full, and tell it the read it follows (the breakdown check), what that round changed and the fixes. With nothing changed, there's nothing to re-read. Unlike the end check's re-read, its **ask** findings are asked, as one more short round before anything is published, with no read after it, each with **Leave them open** among its options. Each of its questions shows, for each option, the `## Blocked by` each ticket it affects would end up with. Post it on the spec's issue as each round is.
   - **Show the redrafted breakdown** once more before you publish it, whenever a round or a fix changed it since **Agree these**.
   - **A finding left open** keeps the build tickets it affects out of `ready-for-agent`: the new ones, and the existing ones labelled `ready-for-agent` and not claimed or built. A finding about an edit to anything else (a spec, say) holds back the build tickets that edit affects. Label them `needs-info` instead, so status lists them as waiting on a person (even while their `## Blocked by` names an open owner task) rather than as new issues to sort. Write the finding into their bodies under `## Breakdown check`, opening with "Held back by spec #<spec>'s breakdown check: settled through `/start`, not by triage", then a line for each open finding starting "Open:", with the question and what each answer would change. In that section, name another issue as "see #n", never "blocked by #n": `workflow ready` reads "blocked by" with an issue anywhere in the body as a blocker. An issue a ticket waits for goes in its `## Blocked by` as `#n`. "Settling a held-back ticket" (below) settles them later.
   - **Then publish.** Each new ticket's `## Blocked by` names the architecture pull request (flow §2 item 7) while it is unmerged, whichever session opened it, so none is ready before it merges. First post the breakdown as it will be published on the spec's issue, headed "Breakdown to publish", in full: each build ticket's body (its blockers named by title, swapped for issue numbers as you publish), each owner task, each edit as the edit itself, and each existing ticket held back with its `## Breakdown check` section. Then, in this order:
     1. Hold back the existing tickets: the section and `needs-info` in place of `ready-for-agent`, in one edit where you can.
     2. If the session's architecture lines are in no pull request yet, open the architecture pull request as a draft. Publish the new build tickets, blockers first, as `to-tickets` does: each `ready-for-agent` but the ones held back. File each owner task labelled `owner-task`.
     3. Make the edits to existing issues, with the new tickets' numbers, keeping a held ticket's section. An edit whose issue was claimed or built since isn't made: list it in a comment on the spec's issue, as what's left.
     4. Comment "Breakdown published" on the spec's issue.

     A check that leaves nothing to ask publishes with no further click.
   - **What's left** (a finding left open or unanswered), with each read's fixes, is listed in that read's post on the spec's issue (above). It names the tickets a finding holds back, and is never only in the session's closing choices.
   - **A session that carries on** reads the posts on the spec's issue first. With a "Breakdown to publish" post and no "Breakdown published" comment after it, the breakdown was final: publish from it exactly as posted, in the order above, with no further read, skipping what's done (a ticket whose title an issue already has, open or closed, under the spec or naming it under `## Parent`; a hold whose section and `needs-info` are both there; an edit already in its issue's body). Without one, but with a "Breakdown check" post, start from the breakdown in the last read's post, redrafted as its round's answers and its listed fixes say (they stand), show it and ask **Agree these**. Agreed as it stands, run only the reads that have no post yet: the re-read of what the "Breakdown check" post's round and fixes changed, with no "Breakdown re-read" post after it. Changed at **Agree these**, the earlier reads don't carry over: run the breakdown check on that draft.
   - **Settling a held-back ticket.** A ticket is held back when it has an "Open:" line under `## Breakdown check`, or is labelled `needs-info` or `needs-triage` with that section and no "Open:" line left (a settle that stopped before its label changed). A ticket labelled `needs-human`, or with no label, isn't: someone took it out of `ready-for-agent` on purpose. Read the rounds on the spec's issue, then ask every finding still open (its "Open:" lines), in this ticket and in any other the same answers touch, as one round shaped as the re-read's round above. It is the breakdown check's last round, carried on, with no check before it and no read after it. Post it on the spec's issue as soon as it's answered, tagged. Edit the tickets the answers affect as they say (their criteria and `## Blocked by`); a new ticket or owner task an answer makes is published as "Then publish" says, before the blockers that name it are written. Replace each settled "Open:" line with "Settled: answer <n>". On a ticket with no "Open:" line left, swap `needs-info` or `needs-triage` for `ready-for-agent`. A ticket claimed or built since isn't edited: that part becomes a new quick ticket. A finding left open again changes nothing.
4. **Commit what the session wrote,** as flow §2 says. Once the tickets are published and its pull request, if it has one, has had its planning review, post the spec's "Planning counts" on its issue ("Decision questions", above).
5. **Build in a fresh session.** A spec's interview and tickets fill most of a session, and the flow builds one ticket per session. Ask:
   - **Build them in a fresh session (Recommended)**: there, the first message (or `/next build`) takes the first ticket;
   - **Run them unattended**: tell them how, as in step 1;
   - **Next item of the plan**: only when it is light (a quick ticket to publish, an edit to an issue); else a fresh session for that too;
   - **Stop here**.

**Map** (flow §1):
1. **Offering a study** (above) first: for a new project, the intake and the panel run before charting's first step. Then read `wayfinder`'s `SKILL.md` and chart the map. Charting is one session's work: it settles no decision itself.
   When a study's owner task came before the map (a new project's study, "Ask a professional"), charting writes a `Blocked by: #<n>` line beside each Destination item that rests on its answer, in the map's body (the flow's "Research", **A finding that needs a professional**, which overrides `wayfinder` here).
2. Close the item's issue with "Charted as #<map>".
3. Ask:
   - **Stop here: the first decision in a fresh session (Recommended)**: there, the first message offers it, or `/next map`. For a map whose Notes link an open research issue (a new project's study), it is **Stop here: the study's Carry on in a fresh session (Recommended)** instead: there, the first message offers that study's **Carry on**, since none of the map's decisions is ready before its verdict (`next` §1, "A map");
   - **Next item of the plan**: only when it is light.
4. **Each decision,** in its own session (flow §1): its rounds asked as decision questions ("Decision questions", above), each recommendation with its evidence, each round checked before it's asked ("Before each round", above), and each round posted on its ticket as soon as it's answered, tagged, each question with the answer quoted word for word. After the last round, before the ADR or glossary is written (or the decision recorded, when it changes neither), the end check, run as the Spec path's step 2 runs it, with every post on the decision ticket. A decision with no rounds has none. What's left after it goes into the decision's resolution comment. Then the ADR and glossary written on a branch and given `review-panel`'s planning review (§8) until clean (a question a fix raises is a decision question too, checked before it's asked as "Before each round", above, says), before the ticket is closed and the pull request offered with its review records. When it's recorded, before it's closed, post its "Planning counts" on the decision ticket ("Decision questions", above).
5. **The gate** (flow §1). None of a map's build tickets is built until every item of its Destination has a spec and tickets. `next`, this skill and the conductor's kick-off keep to it; `workflow ready` doesn't know about maps. So while a map has unspecified Destination items, don't offer to build its tickets. A Destination item with a `Blocked by:` line in the map's body is left out of the gate, whether its task is open or closed, and the line stays: the map's other tickets can be offered, and once its task closes, only that item's own tickets wait for its spec and tickets (the flow's "Research", **A finding that needs a professional**).

**Add to an existing issue:**
1. On a spec, ask the questions the change raises first: they are decision questions ("Decision questions", above), each round checked before it's asked ("Before each round", above) and posted on the spec's issue as soon as it's answered, tagged. Then show the change to that issue, and ask **Make this change (Recommended)** or **Change it**.
2. Edit it on yes.
3. If it's a spec, its edited body gets another planning round and its spec record (`review-panel` §8). If its tickets are published, find the tickets the change touches, and change them the same way. While the spec owes its own "Planning counts" ("Decision questions", above), the edit counts in that comment, and the session that made it posts "Planning counts so far" as its last step if the spec still owes them when it ends, here or after later items. Otherwise, post the edit's own "Planning counts" on the spec's issue.
4. A ticket already built (closed, or with an open PR) isn't edited: the change becomes a new quick ticket.

## 5. Sorting new issues

Take them one at a time, oldest first, following `triage`'s steps for each. Read its `SKILL.md`:
- its disclaimer on every comment it posts;
- the check whether it is already built, or ruled out before (`.out-of-scope/`);
- reproducing a bug before anything else.

A build ticket held back by the breakdown check (step 4, "Spec", step 3, "Settling a held-back ticket") isn't sorted here: put back `needs-info` in place of `needs-triage` (`triage` swaps it on any reply), and "Carry on" (§1) settles it.

Say in two lines what it asks and what you found. Unless what you found already rules out a build ticket (it is built already, it was ruled out before, or a bug didn't reproduce: then leave that option out), before its options draft the build ticket it would become, as "Quick ticket" step 1 writes it, and run that step's end check, with the issue you're sorting as the item's issue (here and in that path's step 2). Show the decisions it lists (**Decided for you**, each with its evidence), its fixes and its **ask** findings above the options. Then ask, your recommendation first:
- **Ready to build**: it becomes that build ticket as in "Quick ticket" above, with the same template and its `Review: small` line only where the quick ticket says (flow §2 item 6: a triaged ticket gets item 2's parts, the bar among them). The check you ran is the one **Publish it** shows, so it isn't run again: ask its **ask** findings now, then go on from showing the draft, with its one re-read as step 1 says;
- **Needs a spec**: it joins the plan: append the item marker with `path=spec`;
- **Needs more information**: comment asking for it, label `needs-info`;
- **Won't do**: comment why, label `wontfix`, close as not planned.

With another outcome, the draft isn't published. With **Needs more information**, its **ask** findings are among what the comment asks, sensitive data (`profile.md`) left out and marked as left out. Each outcome removes `needs-triage`. `triage` run on its own, which applies `ready-for-agent` when the maintainer says so, isn't covered: only this step drafts and checks the ticket.

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
3. or carry on in a fresh session from what's on GitHub: the item's issue with its decisions, or the published spec, with `to-tickets` for its tickets (posting "Planning counts so far" on it as this session's last step, "Decision questions" above).

## 7. Changing course

They can change course at any point. Take it as said, and confirm in one line:
- **"That's enough, write it up":** the interview ends, but the end check still runs before the spec is written (step 4, "Spec"), and its round offers **Leave them open** on each question. What's left open, and each finding left open, goes into the spec's Further Notes, as open questions (in a map decision, its resolution comment, step 4, "Map").
- **"Skip that one" / "drop it":** close its issue as not planned.
- **"Do that one first":** reorder, and change the blockers to match.
- **A spec or ticket to change after it's published:**
  - edit it on GitHub, or ask you to; a spec you edit gets another planning round and its spec record (`review-panel` §8), and the questions the edit raises are asked as "Decision questions" (above) say, the edit counted in a "Planning counts" comment as "Where the planning counts go" (above) says;
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
