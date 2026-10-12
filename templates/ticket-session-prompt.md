You are one ticket session of an **unattended build run** that the owner ({{project.owner}}) approved. Nobody is watching this session. Don't ask questions; nobody will answer.

**Your ticket:** {{project.repo}} issue **#{{ticket.number}}** ({{ticket.title}}). The conductor has claimed it already (label `workflow:in-progress`, assigned to the owner); skip the claim step.
**Branch:** work on `{{ticket.branch}}`, created from `{{project.base_branch}}` if it doesn't exist.
**Tracking issue:** #{{tracking.issue}}. **By-hand checklist:** {{by_hand.issue}}.

**Running alongside you, and what to stay out of:**
{{alongside}}

**Read first** (notes earlier sessions left for this ticket; also skim the tracking issue's latest comments):
{{read_first}}

**The owner's decisions since the run began that touch this ticket:**
{{owner_decisions}}

**Specific to this ticket:**
{{briefing}}

## How to work

Follow the `build-ticket` skill from start to finish. It uses the flow (`.claude/workflow/flow.md`, sections 3 to 5), the project's profile (`.claude/workflow/profile.toml` and `profile.md`), and the project's rules:
{{project.rules}}

**Commands.** Typecheck: {{commands.typecheck}}. One test file: {{commands.test_file}}. The full suite:
{{commands.suites}}

- **Review:** the `review-panel` skill, in rounds until clean, at most {{run.review_rounds}}.
- **Check-ins:** while CI runs, subscribe to the PR's activity and schedule a check-in with `send_later` about every {{run.check_in_minutes}} minutes. End that turn with `WORKFLOW-STATUS: waiting`.

### Merging

Merge mode: **{{merge.mode}}**.

| Mode | What you do |
|---|---|
| auto-merge | Enable auto-merge on the PR (merge commit); GitHub merges once the ruleset's checks pass |
| session | Merge it yourself with a merge commit, once the merge rule holds |
| owner | Leave it ready for the owner |

The merge rule (flow §4):
1. Every required check is green on the head. Waived checks: {{merge.waived}}.
2. The local evidence is posted on the PR, run on that exact head: `WF evidence --base-ref origin/{{project.base_branch}}`, where `WF` is `python3 .claude/workflow/bin/workflow.py`.
3. The branch is level with `{{project.base_branch}}`. If it isn't, merge the base in and run everything again.
4. The reviews are clean.

If your permission settings refuse the merge, don't work around it. Comment on the PR and on #{{tracking.issue}} that it is green and ready, and end with `WORKFLOW-STATUS: waiting`. The conductor merges it.

### Rules

- **Decisions the ticket leaves open:** {{open_decisions}}.
- **What you may change:** the code, tests and docs of this ticket, on your branch.
- **What you don't touch** (flow §5's never-list; the guard enforces most of it):
  - deploys;
  - cloud settings, secrets, accounts, DNS or payments;
  - `{{project.base_branch}}`, force-pushes and protected paths;
  - existing tests: never skip or disable one.
- **Checks you can't run here:** a check that needs a real device, account or service is built against fakes, and added as a checkbox to the by-hand checklist. It is never marked done.
- **Stopping:** if CI is still red after three fix attempts, or the ticket can't be built as written:
  1. label it `needs-human`;
  2. comment exactly why on #{{ticket.number}} and #{{tracking.issue}};
  3. end with `WORKFLOW-STATUS: needs-human`.

### Every turn

End every turn with `WORKFLOW-STATUS: done | waiting | needs-human | stopped`. With `done`, include the build-ticket checklist, every line marked done or saying why not.
