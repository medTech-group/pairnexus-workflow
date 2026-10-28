---
name: run-report
description: Write the final report of an unattended run (or a progress report mid-run) - what merged, what was set aside and why, what's live, the outward changes to confirm or undo, the decisions for the owner, the by-hand checks and the follow-ups. Used by the conductor at the end of a run, or alone.
---

# The run report

One comment on the tracking issue, written for the owner to act on. Build it only from the record, never from memory.

`WF` is the kit's CLI: `python3 .claude/workflow/bin/workflow.py` (vendored), or `python3 <this skill's directory>/../../scripts/workflow.py` (plugin).

## Gather the record

- **The state:** save the tracking issue's body to `body.md`, then run `WF state get --body body.md`. Each ticket has its status, attempts, `started_at`, `merged_at` and PR. The state also holds the ledger and `for_owner`.
- **Each merged PR's body:** its "Decisions for the owner", any findings left open, and the number of review rounds.
- **Each merged PR's timeline**, every page (`gh api --paginate --slurp 'repos/<repo>/issues/<PR>/timeline?per_page=100'`, or one `?page=N` at a time where `--paginate` is refused): one with an `added_to_merge_queue` event went through the merge queue, whoever queued it. For those, when it was last added to the queue, and its reviews and review threads.
- **The by-hand issue:** its open checkboxes.
- **The tracking issue's comments:** each ticket session's notes and failures.

## Its sections

1. **Summary.** One line:
   - how many tickets merged, how many were set aside, how many weren't started;
   - why the run ended: done, the end time, a limit, or the stop label.

   **A solo-mode run** repeats its gap right under the summary. It is one whose charter's `accepted_gaps` has a line starting `solo mode:` or `removed protection:`, whatever its case or spacing (the charter's own check reads `removed protection:` the same way). Use these words, with the base branch's name in place of `main` where it isn't `main`:

   > This run was in solo mode: nothing on GitHub stops a mistake reaching `main`, and the kit's "never merge while CI is red" check is the only one.

   Then one line on closing it before the next run, in an attended session with the `upgrade-setup` skill:
   - `solo mode:`: "Protect `main`";
   - `removed protection:`: first say the profile says `main` is protected but the conductor's read-back didn't find it protected (the protection was removed, or couldn't be confirmed without admin access), then "Restore protection".
2. **Merged.** A table of ticket, title, PR, review rounds, wall time (from `started_at` to `merged_at`) and attempts.
3. **Set aside.** Each `needs-human` or set-aside ticket, with exactly what it needs and from whom. A run wound down because a session wasn't a ticket session (the state's `wind_down`) says so first, with the environment's fix: `WORKFLOW_ROLE=ticket` in the ticket environment's variables (`docs/enforcement.md` §2), before the next run.
4. **What's live.** Each release step in the ledger: what ran, from which commit, and the smoke test's result. A release skipped because the owner stopped the run says so, and that the owner can release by hand.
5. **Changes outside the repo.** The ledger, as a list for the owner to **confirm or undo**. Each line gives the change, when it happened, and the charter line or owner comment that allowed it.
6. **For you:**
   - the decisions sessions took that the owner should confirm, each with its PR;
   - `for_owner`;
   - each PR that merged with a request made after it was queued: changes requested, or an open review thread, from after it was last added to the queue. The queue doesn't stop for one (flow §4), so flag it with the request's link, and offer a revert: a pull request reverting its merge commit (`git revert -m 1 <merge commit>`), for the owner to decide. The conductor makes it only once the owner allows it, recorded in the ledger first (the `conductor` skill's "Reverting a merged change"), and pushes it in a command of its own, never chained with the revert;
   - the owner tasks still open;
   - the by-hand issue's open checkboxes, counted, with a link.
7. **Follow-ups.** What the reviews found that wasn't this run's to fix, each with a suggested ticket.
8. **The project's health:**
   - CI duration on the base branch, now and at the start;
   - flaky tests seen;
   - "add CI" when the profile says `ci.none`.

Keep it scannable: tables and short lines, issue and PR references, no transcripts.

End the report with the agents' marker as its last line, as every agent post does (the guard refuses a conductor's post without it):

```
<!-- workflow:agent -->
```

## Afterwards

1. Post the report as a comment on the tracking issue.
2. When the charter's `notify.final_report` is `push`:
   - @mention the owner (`profile.project.owner`) in the comment;
   - also send a short notification with the issue's link, if the session has a notification tool (`PushNotification`).
3. Close the tracking issue as completed, unless a set-aside ticket still points to it.
