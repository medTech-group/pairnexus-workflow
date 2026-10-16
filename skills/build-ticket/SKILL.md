---
name: build-ticket
description: Build one ready ticket from claim to merge - tdd at the spec's seams, the review panel in rounds until clean, a pull request with its findings table, CI green, the local suite's evidence, and the merge under the merge rule. Use for "implement #N", "build #N", or a ticket session's briefing.
---

# Build a ticket

One ticket, start to finish. The flow's sections 3 to 5 are the rules; this skill is how to follow them. The flow is `.claude/workflow/flow.md` (vendored) or `docs/flow.md` beside `skills/` (plugin).

`WF` is the kit's CLI: `python3 .claude/workflow/bin/workflow.py` (vendored), or `python3 <this skill's directory>/../../scripts/workflow.py` (plugin).

**Every post carries the marker.** Everything you post on GitHub (comments, issues, the PR's body, reviews, edits of a body) goes out under the owner's account. End each body with this line, so the owner's own words can be told apart from agents':

```
<!-- workflow:agent -->
```

In a ticket session the guard refuses a post without it. Labels, assignees, state changes and merges need none.

## 0. Read first

- **The briefing,** if this is a ticket session. It says:
  - what runs alongside you, and what to stay out of;
  - which notes to read;
  - the owner's decisions since the run began;
  - the merge mode, and any waived check;
  - the wake routine's trigger id;
  - on its last line, `Briefing <hash>`.

  **Check your copy first.** With the Write tool, write the briefing (your first message, verbatim, from its first line to its `Briefing <hash>` line) to `.workflow/briefing.md`, which git ignores. Then run `WF briefing verify --file .workflow/briefing.md`. It prints one line: `Briefing <hash> intact`, `Briefing changed: expected <a>, got <b>`, or `no Briefing line`.

  **Your first write** is a comment on the ticket saying you've started, quoting that output line exactly ("Started. Briefing 3f2a9c01b7de intact"), so the conductor sees whether the briefing arrived intact. Carry on either way: if it didn't, the conductor stops this session and starts another.
- **The ticket,** its spec (the issue under "Parent") and every issue they link. Use `gh api` or the GitHub MCP tools.
- **The profile** (`.claude/workflow/profile.toml`, `profile.md`) and the rules it points to.
- **Its blockers.** If any isn't closed as completed, say so and stop: it isn't ready.

## 1. Claim it

Skip this if the briefing says the conductor has claimed it. Otherwise, before any other write:
- add the `workflow:in-progress` label, keeping the ticket's other labels (`issue_write` replaces the whole list);
- assign it to yourself in attended work, or to the owner in a run.

## 2. Build it

- **Branch:** work on the session's branch. A ticket session's is the profile's `run.ticket_branch` with the ticket's number. In an attended session that builds more than one thing, each ticket gets its own branch, fresh from `origin/<base>` and not named like `run.ticket_branch` (that would make it a ticket session), so no pull request carries another's work.
- **Tests first:** use `tdd` (Matt Pocock's) at the spec's seams. Write a failing test for each acceptance criterion, then the code. The seams the spec names are already agreed with the owner: they count as confirmed, so in a ticket session `tdd`'s "confirm with the user" step is satisfied and you never stop to ask. A seam the spec doesn't name is a decision the ticket leaves open (below).
- **Commands:** the profile's `commands.typecheck` and `commands.test_file` as you go. Run the full suite once the ticket is built.
- **Tests that don't fail by chance:** compute dates and times at the point of use, never at import. Never assert that a random id lacks some digit string.
- **Commit and push as you go,** with clear messages: push your branch after each commit, so the work is never only in this container and the conductor sees progress.
- **Stay within the flow's never-list** (§5). The guard hook stops most breaches: if it refuses something, the refusal is the answer, not a puzzle to get around.
- **Checks you can't run here:** for a check that needs a real device, account or service, build against the spec's fakes. Add its by-hand step as a checkbox under this ticket on the run's by-hand issue, or on the ticket in attended work. Never mark it done.
- **Decisions the ticket leaves open:** follow the briefing. By default, take the choice most consistent with the spec, ADRs and the project's rules, and record it for the PR body.

## 3. Review it

Follow the `review-panel` skill on the diff against the base branch:
- rounds until one comes back clean, at most the profile's `run.review_rounds`;
- verify each finding, then fix it with a test or answer it with a reason;
- rerun the typecheck and the affected tests after each round;
- after the last round, any further commit gets a short Correctness pass.

## 4. Open the pull request

To the base branch. Its body:
- `Closes #<n>`;
- what was built: routes, screens, tables, settings;
- how it was tested: the seams, the suites, what the explorer exercised;
- the findings table: round, reviewer, finding, and what happened (fixed in which commit, or not a problem and why);
- the decisions taken, under "Decisions for the owner";
- the by-hand checks added.

Then post the review records of the rounds so far: each round's `record.md`, kept in its scratch directory (`review-panel`, "Review records"), oldest first. Later rounds and Correctness passes post theirs as they run. The records sit alongside the findings table; they don't replace it.

Lasting knowledge for later work (how a new module is meant to be used, a pitfall) goes in the repo's own docs, in this PR, before it merges.

Then subscribe to its activity. Schedule a check-in about every `run.check_in_minutes` (`send_later` in cloud sessions; `/loop` or a cron task locally), and end the turn with `WORKFLOW-STATUS: waiting`.

## 5. Get it green

- **A required check is red:** find the cause (use `diagnosing-bugs` when it's unclear) and push a fix. "Flake" isn't a cause: a test that fails by chance gets fixed so it can't.
- **The base branch moved:** `git fetch origin <base> && git merge origin/<base>`, resolve any conflicts keeping both sides' intent, rerun the tests, and push. Never rebase or force-push.
- **A required check that never starts** because its workflow is path-filtered (the profile's `ci.path_filtered`): in `session` mode it counts as passed once the evidence is posted; in `auto-merge` mode GitHub waits for it, so comment that the PR needs the owner to merge and end `waiting`.
- **A check the charter waives:** it counts as passed only when its log shows a killed marker (the profile's `ci.killed_markers`) rather than a test failure, and only with the evidence below.
- **Still red after three fix attempts:**
  1. label the ticket `needs-human`, and remove `workflow:in-progress` and `ready-for-agent` (keep its other labels);
  2. comment on it and on the tracking issue with exactly what fails and why;
  3. wake the conductor (step 6.6);
  4. end with `WORKFLOW-STATUS: needs-human`.

## 6. Post the evidence and merge

1. **Push everything,** and make sure the branch is level with the base branch.
2. **Run the evidence:** `WF evidence --base-ref origin/<base>`, after a `git fetch`.
   - It runs the suites in shards, resumes after a container restart, refuses a dirty tree, and runs the base branch's suites in a temporary worktree to compare counts.
   - Post its report on the PR.
3. **Merge** when the merge rule holds (flow §4). What you do depends on the briefing's mode:

   | Mode | What you do |
   |---|---|
   | `auto-merge` | First post your notes for the next tickets (step 4) on the tracking issue, then enable auto-merge with a merge commit (`enable_pr_auto_merge`, or `gh pr merge <n> --auto --merge`). Stay with it: at each check-in, if the PR is behind the base (`mergeable_state` behind), update it (`gh api -X PUT repos/<repo>/pulls/<n>/update-branch`) and end the turn `waiting`, until GitHub has merged it. **If GitHub refuses to enable auto-merge because the PR is already mergeable** (clean: "Pull request is in clean status"), check the merge rule (flow §4) again at that moment, on the current head; if it holds, merge it yourself with a merge commit (`merge_pull_request` with `merge_method: merge`, or `gh api -X PUT repos/<repo>/pulls/<n>/merge -f merge_method=merge`) |
   | `session` | Merge it yourself with a merge commit |
   | `owner`, or attended work | Say it's ready, and leave it |

   If your permission settings refuse the merge, don't work around it. Comment that it's green and ready, and end with `WORKFLOW-STATUS: waiting`.
4. **Once it has merged,** tell the tracking issue: "#<n> merged in #<PR>", then notes for the next tickets. Tag each note with its area and the tickets it's for ("For #201, area readings: …"): what you added that later tickets build on, decisions to know, and pitfalls.
5. **The claim label.** Whenever your ticket ends (merged, `needs-human`, or stopped), always remove `workflow:in-progress`; on `needs-human` also remove `ready-for-agent`. Keep the ticket's other labels. The conductor removes leftovers at its next check-in, but don't leave it to.
6. **Wake the conductor.** When the ticket ends, call `fire_trigger` with the briefing's wake routine id and exactly one of these lines: "#<n> merged in #<PR>", "#<n> needs-human" or "#<n> stopped". The conductor then checks in at once instead of at its next scheduled time. Skip this when the briefing's wake routine says `none`, or in attended work.
   - `fire_trigger` is a deferred tool (in a cloud session, `mcp__claude-code-remote__fire_trigger`; the server's part of the name can differ): load it first with ToolSearch, searching for `fire_trigger` rather than selecting an exact name.
   - If it isn't available, or the call errors, say so in the ticket's final note ("Couldn't wake the conductor: <why>") and carry on: try it once, never retry it in a loop. The conductor sees the ending at its next check-in anyway, so the wake never holds up the ticket or your `WORKFLOW-STATUS` line.

## 7. End each turn

End every turn with a status line. The checklist gate checks it in ticket sessions.

```
WORKFLOW-STATUS: done | waiting | needs-human | stopped
```

Use `waiting` when CI is running and a check-in is scheduled. With `done`, include the checklist below, each line marked `[x]`, or left `[ ]` with its reason in words ("because …", "not needed", "n/a", "skipped because …", or after a spaced dash: "- [ ] Docs — none changed"). The gate refuses an unchecked line without one.

- [ ] Blockers closed and the spec read
- [ ] Every acceptance criterion met, each with its test
- [ ] Typecheck and the full suite pass; evidence posted on the PR
- [ ] Review panel run in rounds until clean (or the limit, the rest raised); late commits had a Correctness pass
- [ ] Every finding fixed or answered with its reason
- [ ] PR opened with the findings table and decisions; by-hand checks filed
- [ ] Merged under the merge rule (or left for the owner), notes for the next tickets posted; the claim label removed and the conductor woken (in a run)
