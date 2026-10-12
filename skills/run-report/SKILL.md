---
name: run-report
description: Write the final report of an unattended run (or a progress report mid-run) - what merged, what was set aside and why, what's live, the outward changes to confirm or undo, the decisions for the owner, the by-hand checks and the follow-ups. Used by the conductor at the end of a run, or alone.
---

# The run report

One comment on the tracking issue, written for the owner to act on. It reads only from the record, never from memory:
- the state block (`workflow state get`);
- each merged PR's body: its decisions, findings left open, by-hand checks;
- the by-hand issue;
- the ledger;
- the comments tagged "For the owner".

## Its sections

1. **Summary.** One line: how many tickets merged, set aside, and not started, and why the run ended (done, end time, limit, the stop label).

2. **Merged.** A table: ticket, title, PR, and review rounds. Add wall time and retries when known.

3. **Set aside.** Each `needs-human` or set-aside ticket, with exactly what it needs and from whom.

4. **What's live.** Each release step the ledger records: what ran, from which commit, and its smoke test's result.

5. **Changes outside the repo.** The ledger as a list to **confirm or undo**. Each line is the change, when, and the charter line or owner comment that allowed it.

6. **For you.**
   - The decisions sessions took that the owner should confirm, each with its PR.
   - The owner tasks still open.
   - The by-hand issue's open checkboxes, counted, with a link.

7. **Follow-ups.** What the reviews found that wasn't this run's to fix, each with a suggested ticket.

8. **Per-ticket numbers**, when the state has them: wall time, review rounds, CI minutes, retries. Also the CI duration trend.

Keep it scannable: tables and short lines, issue and PR references, no transcripts.

## Afterwards

Post it as a comment on the tracking issue. When the charter's `notify.final_report` is `push`, also send the owner a short notification (`PushNotification`, when available) with the issue link. Then close the tracking issue as completed, unless a set-aside ticket still names it.
