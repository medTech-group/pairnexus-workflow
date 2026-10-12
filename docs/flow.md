# The flow: plan → spec → build tickets → code

Every session that plans, writes a spec or builds a ticket follows this file. Each kind of session ends by reporting its checklist, every line marked done or saying why not, so a skipped step shows.

The project's specifics live in its profile: `.claude/workflow/profile.toml` (commands, required checks, protected paths, areas, release steps) and `profile.md` (the safety rules by reference, sensitive data, secrets, wording). Read both before acting. Where this file says "the project's rules", it means what `profile.md` points to.

**Skills.** Skills named here are in `.claude/skills/<name>/` (vendored) or under the plugins (`pairnexus-workflow:<name>`, `mattpocock-skills:<name>`). A skill marked user-only can't be loaded with the Skill tool: read its `SKILL.md` and follow it as written.

**Starting.** Name the work ("implement #146", "work the doctor map"), or use `next`: it finds what is ready and does one piece under this file.

## 1. Planning (optional): a map, one decision per session

A large effort can start as a **map**: an issue labelled `wayfinder:map` whose child tickets are the decisions to make with the owner (grilling, research, prototypes, tasks). Follow the `wayfinder` skill. Small efforts skip this and start at a spec.

1. **Claim** the ticket (the `workflow:in-progress` label and an assignee) before any other write.
2. Resolve it with the owner. A human-in-the-loop decision is the owner's answer, asked in rounds; never answer for them.
3. Record it: a resolution comment, close it, the map's "Decisions so far", unblocked tickets updated, new tickets created and wired.
4. Commit `CONTEXT.md`, ADRs and research to a branch and offer a pull request.

**Checklist:** claimed first; every decision the owner's; recorded and closed; map updated; dependents updated; changes committed with a PR offered; next ticket named.

## 2. A spec and its build tickets: one spec per session

1. Follow `to-spec`: agree the test seams with the owner, then publish the spec (`ready-for-agent`), citing the decision behind each choice.
2. Follow `to-tickets`: agree the breakdown, then publish build tickets. Each build ticket has:
   - `## Blocked by` (issue refs, or "None");
   - an `Area: <name>` line from the profile's `[areas]`, so the conductor never runs two sessions on one area;
   - acceptance criteria naming their seams;
   - the by-hand checks it will need (a real device, account or service), if any.
3. Anything only the owner can do (create an account, a key, a domain) is its own issue labelled `owner-task`, and blocks what needs it.

**Checklist:** every input decision used or ruled out with a reason; seams agreed; spec published; tickets agreed, published, wired, each with an area; owner tasks filed.

## 3. Building: one ticket per session

Follow the `build-ticket` skill. In short:

1. **Claim** it; read the ticket, its spec, the project's rules and the notes the briefing points to.
2. **Build** it: `tdd` at the spec's seams; the typecheck and single test files as you go; the full suite at the end.
3. **Review** with the `review-panel` skill: Standards, Spec, Correctness (with a security review for auth, upload or API changes) and, for a UI change, the explorer, in parallel. Verify each finding, fix the real ones with a test, answer the rest with a reason. Repeat until a round is clean, at most the profile's `run.review_rounds`; a short Correctness pass then covers any commit made after the last round.
4. **Pull request** to the base branch: `Closes #<n>`, what was built, how it was tested, the findings table, the decisions taken.
5. **Green and merge** under the merge rule (below), or leave it for the owner in attended work.

**Checklist:** blockers closed and spec read; each acceptance criterion met with its test; typecheck and full suite pass; review rounds until clean; every finding fixed or answered; PR opened with the findings table; merged under the rule (or left for the owner); notes for the next tickets posted.

## 4. The merge rule

A pull request merges only when all of these hold on its current head:

1. **Every required check is green** (`ci.required_checks`). A check the run's charter waives counts only if it was **killed, not failed** (the profile's `ci.killed_markers`: exit 143, runner shutdown, cancelled, never started). A real test failure always blocks.
2. **The full suite passed locally on that exact commit**, posted on the PR by `workflow evidence`: the command, SHA, counts, duration, and no fewer tests than the base branch. Required when a check is waived; recommended always.
3. **The branch is level with the base branch.** Whoever merges second merges the base in and runs everything again.
4. **The reviews are clean**, and any commit after the last round had its Correctness pass.

Merging is the owner's in attended work. In an unattended run it follows the charter's `merge.mode`: GitHub auto-merge behind the ruleset (preferred), or the session merges with a merge commit.

## 5. Unattended runs

Follow the `conductor` skill. The conductor never builds tickets itself: it asks the owner the kick-off questions once (the **run charter**, `docs/charter.md`), then hands each ready ticket to its own session, checks in, merges what passes, and reports. What it may do outside the repo is exactly what the charter grants, logged in the run's ledger.

**Each ticket session** follows "Building" with these differences:
- it never deploys, changes cloud settings, secrets, accounts, DNS or payments, pushes to the base branch, force-pushes, or skips or disables a test (the guard hook and the GitHub ruleset back this up);
- a check that needs a real device, account or service is built against the spec's fakes and added to the run's by-hand issue as a checkbox, never faked as done;
- a decision the ticket leaves open is taken as the charter says (`open_decisions`) and recorded in the PR;
- if CI is still red after three fix attempts, or the ticket can't be built as written, it labels the ticket `needs-human`, says exactly why on the ticket and the tracking issue, and stops;
- it ends every turn with `WORKFLOW-STATUS: done | waiting | needs-human | stopped` (`waiting` while CI runs with a check-in scheduled); `done` includes the checklist.

## Anything else

Use `ask-matt`, the router over the engineering skills.
