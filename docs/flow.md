# The flow: plan → spec → build tickets → code

Every session that plans, writes a spec or builds a ticket follows this file. Each kind of session ends by reporting its checklist, every line marked done or saying why not, so a skipped step shows.

The project's specifics live in its profile: `.claude/workflow/profile.toml` (commands, required checks, protected paths, areas, release steps, and `project.rules`, the list of the project's rule documents) and `profile.md` (sensitive data, secrets, environment notes). Read both before acting. Where this file says "the project's rules", it means the documents in `project.rules`.

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
   Label the spec `spec` as well, so readiness never mistakes it for a build ticket.
2. Follow `to-tickets`: agree the breakdown, then publish build tickets (`ready-for-agent`). Each build ticket has:
   - `## Blocked by` (issue refs, or "None"), written out even when the tickets are also linked with GitHub's own dependencies, so a blocker closed as not planned is seen;
   - an `Area: <name>` line from the profile's `[areas]`, so the conductor never runs two sessions on one area;
   - acceptance criteria naming their seams;
   - the by-hand checks it will need (a real device, account or service), if any.
3. Anything only the owner can do (create an account, a key, a domain) is its own issue labelled `owner-task` (or `ready-for-human`), and blocks what needs it.
4. **A change to a protected path** (the profile's `guard.protected_paths`: the kit, CI config, CODEOWNERS, secrets files) is an owner task too, labelled `owner-task`, never a build ticket: a ticket session can't change those paths. `workflow ready` notes a ticket whose body names one ("names protected path … : check it isn't an owner task"), leaving it ready; the conductor lists such tickets at kick-off for the owner to keep or exclude. Paths in fenced code, or after "don't", "do not" or "never" on their line, aren't noted.
5. **A ticket that fixes a failing or flaky required check** is infra: label it `workflow:infra` as well, so it starts before other tickets. (If its fix is to CI config itself, it is an owner task, as above.)

**Checklist:** every input decision used or ruled out with a reason; seams agreed; spec published; tickets agreed, published, wired, each with an area; owner tasks filed (protected-path changes among them); check fixes labelled `workflow:infra`.

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

1. **Every required check is green** (`ci.required_checks`). A check the run's charter waives counts only if its log shows it was **killed, not failed** (the profile's `ci.killed_markers`: exit 143, runner shutdown, cancelled, never started). A real test failure always blocks. Waivers need `merge.mode: session`, since GitHub's auto-merge can't tell killed from failed.
2. **The full suite passed locally on that exact commit**, posted on the PR by `workflow evidence --base-ref origin/<base>`: the command, SHA, counts, duration, and no fewer tests than the base branch. Required when a check is waived or the profile says `ci.none`; recommended always. When the base branch's own suite doesn't pass, the report says the count wasn't compared; the PR may still merge, and the conductor opens an infra ticket for the base.
3. **The branch is level with the base branch.** Whoever merges second merges the base in and runs everything again.
4. **The reviews are clean**, and any commit after the last round had its Correctness pass.

This section is the merge rule's one source; skills and briefings point here rather than restate it.

Merging is the owner's in attended work. In an unattended run it follows the charter's `merge.mode`: GitHub auto-merge behind the ruleset (the session or the conductor keeps the branch up to date until it merges), or the session merges with a merge commit. In `auto-merge` mode, when GitHub refuses to enable auto-merge because the PR is already mergeable (clean), whoever tried (the session, or the conductor) checks this rule again at that moment and, if it holds, merges with a merge commit. The conductor never merges a change to a protected path itself: it goes to the owner.

## 5. Unattended runs

Follow the `conductor` skill. The conductor never builds tickets itself: it asks the owner the kick-off questions once (the **run charter**, `charter.md` in the kit's docs), then hands each ready ticket to its own session, checks in, keeps PRs moving to merge, and reports. What it may do outside the repo is exactly what the charter grants, logged in the run's ledger.

**The never-list.** A ticket session changes only its ticket's code, tests and docs, on its own branch. The owner keeps these to themselves, and the guard hook and the GitHub ruleset back it up:
- deploys and releases;
- cloud settings, secrets, accounts, DNS and payments;
- the base branch (only pull requests reach it), and history (no force-pushes);
- protected paths: the kit, CI config, CODEOWNERS, secrets files;
- the test suite's reach: no test is skipped, disabled or focused away.

**Posts.** Every comment, issue and PR body an agent posts (the conductor's and every ticket session's) goes out under the owner's GitHub account. Each ends with `<!-- workflow:agent -->`, so the owner's own words can be told apart from agents' (`charter.md` §4); the guard refuses a post without it in ticket and conductor sessions.

**Each ticket session** follows "Building" with these differences:
- it stays within the never-list above;
- it first writes its briefing to `.workflow/briefing.md` and checks it with `workflow briefing verify --file .workflow/briefing.md`; its first comment on the ticket quotes the line that prints (`Briefing <hash> intact`), so the conductor sees the briefing arrived intact;
- a check that needs a real device, account or service is built against the spec's fakes and added to the run's by-hand issue as a checkbox, never faked as done;
- a decision the ticket leaves open is taken as the charter says (`open_decisions`) and recorded in the PR;
- if CI is still red after three fix attempts, or the ticket can't be built as written, it labels the ticket `needs-human`, says exactly why on the ticket and the tracking issue, and stops;
- **the claim label:** when its ticket ends (merged, `needs-human` or stopped) the session always removes `workflow:in-progress`, and on `needs-human` also `ready-for-agent`; the conductor removes leftovers at its next check-in;
- when its ticket ends it fires the conductor's wake routine named in its briefing, with "#<n> merged in #<PR>", "#<n> needs-human" or "#<n> stopped"; if that fails, it says so in its final note and carries on;
- it ends every turn with `WORKFLOW-STATUS: done | waiting | needs-human | stopped` (`waiting` while CI runs with a check-in scheduled); `done` includes the checklist.

## Anything else

Use `ask-matt`, the router over the engineering skills.
