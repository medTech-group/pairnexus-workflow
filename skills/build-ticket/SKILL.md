---
name: build-ticket
description: Build one ready ticket from claim to merge - tdd at the spec's seams, the review panel in rounds until clean, a pull request with its findings table, CI green, the local suite's evidence, and the merge under the merge rule. Use for "implement #N", "build #N", or a ticket session's briefing.
---

# Build a ticket

One ticket, start to finish. The flow (`.claude/workflow/flow.md`) sections 3 and 4 are the rules; this is how.

`WF` below means the kit's CLI: `python3 .claude/workflow/bin/workflow.py` (vendored), or `python3 <this skill's directory>/../../scripts/workflow.py` (plugin).

## 0. Read first

- The briefing, if this is a ticket session: what runs alongside you and what to stay out of, the notes to read, the owner's decisions since, the merge mode and any waived check.
- The ticket, its spec (under "Parent") and every issue they link. Use `gh api` or the GitHub MCP tools.
- The project's profile and the rules it points to.
- Its blockers. If any isn't closed as completed, say so and stop: it isn't ready.

## 1. Claim it

Before any other write: add the `workflow:in-progress` label (keep the ticket's other labels; the MCP `issue_write` replaces the whole list) and assign it. In an unattended run, assign the owner, as the conductor's briefing says.

## 2. Build it

- Work on the session's branch (a ticket session's is `run.ticket_branch` with the number).
- `tdd` (the Matt Pocock skill) at the spec's seams: a failing test first for each acceptance criterion, then the code.
- The profile's `commands.typecheck` and `commands.test_file` as you go; the full suite once it's built.
- New tests compute dates and times at the point of use, never at import, and never assert that random ids lack a digit string.
- Commit as you go, with clear messages.
- Never: skip or disable a test, push to the base branch, force-push, deploy, or change cloud settings, secrets, accounts, DNS or payments. The guard hook stops most of these; don't try another route.
- A check that needs a real device, account or service: build it against the spec's fakes, and add its by-hand step as a checkbox on the run's by-hand issue (or the ticket, in attended work). Never fake it as done.
- A decision the ticket leaves open: as the briefing says (decide-and-record by default: take the choice most consistent with the spec, ADRs and the project's rules, and record it for the PR body).

## 3. Review it

Follow the `review-panel` skill on the diff against the base branch. Rounds until one comes back clean, at most the profile's `run.review_rounds`. Each finding: check it against the code first (a reviewer can be wrong), fix the real ones with a test for each bug, record the rest with the reason. Rerun the typecheck and the affected tests after each round. After the last round, any further commit gets a short Correctness pass before merging.

## 4. Open the pull request

To the base branch. Its body:
- `Closes #<n>`;
- what was built (routes, screens, tables, settings);
- how it was tested (the seams, the suites, what the UI explorer exercised);
- the findings table: round, reviewer, finding, and what happened (fixed in which commit, or not a problem and why);
- the decisions taken, for the owner;
- by-hand checks added.

Subscribe to its activity. Schedule a check-in about every `run.check_in_minutes` (`send_later` in cloud sessions; `/loop` or a cron task locally) until it is merged or you stop.

## 5. Get it green

- Required checks red: find the cause (`diagnosing-bugs` when unclear) and push a fix. "Flake" is not a cause: a test failing by chance gets fixed so it can't.
- The base branch moved: merge it in (`resolving-merge-conflicts`), never rebase or force-push.
- A check named in the charter's `merge.waived_checks` counts as passed only when it was killed, not failed (the profile's `ci.killed_markers`), and only with the local evidence below.
- Still red after three fix attempts: label the ticket `needs-human`, comment on it and the tracking issue with exactly what fails and why, and stop.

## 6. Post the evidence and merge

1. Make sure the branch is level with the base branch and every commit is pushed.
2. Run `WF evidence --base-count <the base branch's passed count, from its last evidence or a run>` on the clean checkout. It runs the suites in shards, resumes after a container restart, and refuses a dirty tree. Post its report on the PR.
3. Merge when the merge rule holds (flow section 4):
   - `merge.mode` `auto-merge`: enable auto-merge on the PR (merge commit); GitHub merges when the ruleset's checks pass.
   - `session`: merge it yourself with a merge commit.
   - `owner`, or attended work: say it's ready, and leave it.
4. Comment on the tracking issue: "#<n> merged in #<PR>", then **notes for the next tickets**, each tagged with its area and the tickets it's for ("For #201: …"): what you added that later tickets build on, decisions to know, pitfalls. Lasting knowledge goes in the repo's own docs, in this PR.
5. Remove the `workflow:in-progress` label if the merge didn't close the ticket.

## 7. End each turn

With a status line, which the checklist gate checks in ticket sessions:

```
WORKFLOW-STATUS: done | waiting | needs-human | stopped
```

`waiting` when CI is running and a check-in is scheduled. `done` comes with the checklist:

- [ ] Blockers closed and the spec read
- [ ] Every acceptance criterion met, each with its test
- [ ] Typecheck and the full suite pass; evidence posted on the PR
- [ ] Review panel run in rounds until clean (or the limit, the rest raised); late commits had a Correctness pass
- [ ] Every finding fixed or answered with its reason
- [ ] PR opened with the findings table and decisions; by-hand checks filed
- [ ] Merged under the merge rule (or left for the owner), notes for the next tickets posted

Mark each `[x]`, or leave it `[ ]` with why.
