# Changelog

## 0.1.0 (unreleased)

First version, from the pair-drop weekend run of 9–12 Oct 2026 and two independent reviews of its proposal.

- **The flow** (`docs/flow.md`): plan (optional maps), spec, build tickets with areas, building, the merge rule, unattended runs.
- **The run charter** (`docs/charter.md`, `workflow charter`): the kick-off questions, the one "go", amendments by the owner's comments, the `workflow:stop` kill switch.
- **The conductor** (`skills/conductor`):
  - pre-flight, check-ins and safe stopping;
  - retries, then `needs-human`;
  - lanes by `Area:`, conductor-ops and the ledger, release under a grant, and the final report.
- **build-ticket** and **review-panel**: rounds until clean, with a Correctness pass for any commit after the last round; the findings table; local evidence for the merge rule.
- **The CLI** (`scripts/workflow.py`):
  - readiness (blockers closed as completed, claims by label, owner tasks);
  - the state block with its size limit;
  - briefings rendered with required slots (a briefing with a gap is refused);
  - sharded, resumable evidence by head SHA, compared with the base branch's test count;
  - vendoring with a lockfile (local edits kept, one mode per project).
- **The hooks:**
  - the guard: base-branch pushes, force-pushes, deploys, protected paths, new skip markers and sensitive posts, across Bash, Edit/Write and GitHub's MCP tools;
  - the checklist gate (`WORKFLOW-STATUS`, one nudge per turn, never while already continuing, a safety cap per session);
  - flow context;
  - environment repair.
- **Review round 1** (three independent reviewers, about 100 findings) changed:
  - the guard to allow-lists for ticket sessions (pushes only to ticket branches, GitHub API writes only to issues, comments, labels and PRs), closing every bypass the review found;
  - the guard to fail closed in ticket and conductor sessions;
  - readiness to leave specs and parents out, read more blocker and closing forms, honour native dependencies, and parse areas;
  - vendoring to check everything before writing, keep local edits through `resolve` and orphans, and never drop Matt Pocock's skills;
  - evidence to prove the commit (untracked files, the base branch's count from a worktree, causes in the report);
  - the charter to check limits, waivers and the profile, with `accepted_gaps` and `reuse`;
  - the conductor's own environment (`WORKFLOW_ROLE=conductor`) and an explicit permission mode for ticket sessions.
- **Review round 2** changed:
  - the guard's parsing (quotes, redirects, subshells, heredocs, the working directory) and its allow-lists for ticket sessions;
  - the conductor's mechanics: claims, check-ins, retries, stopping across several check-ins, and archiving;
  - evidence to run the base branch in a worktree, and to report rather than fail when the base has no usable count;
  - vendoring's keep and resolve.
- **Review round 3** (no blockers) changed:
  - the guard: remote mirror and push-default keys, `find` start paths, sensitive text read through `cat`, stdin and pipes, GraphQL queries from variables, deploys run through interpreters, branch switches when the role comes from the branch, the default branch, more in-place writers, patches from heredocs, skip markers counted net of what is removed, and the global git config protected in ticket and conductor sessions;
  - the charter: malformed charters never raise, amendments are checked against the owner, `charter pin-plan`, and `reuse` clears the old plan;
  - `state init` runs the profile check; readiness reads `/pull/` blockers and "blocked by" mid-sentence;
  - the gate: an unchecked line's reason must say why, and its cap is counted per day;
  - the conductor and build-ticket skills: PRs waiting on the owner, auto-merge, path-filtered checks, and merging the base in rather than rebasing.
- **The final Correctness pass** after round 3 changed: a deploy script run with `.`; the default branch sent on stdin from a file or a pipe; a writing `find` from the project root checked against the protected files there by name; a pull request as a blocker, resolved once merged; the gate's reasons read as words; "doesn't" and "won't" read as negations. A second pass on those fixes: a matched directory holding protected paths, a symlinked root, dependency directories left unwalked, `-prune -o`, `--input /dev/stdin` and an escaped `default_branch`.
- **Deviations from the proposal, recorded:**
  - the profile is TOML (stdlib `tomllib`), not YAML;
  - `vendor update` writes `<file>.new` for conflicts and `vendor resolve` records a hand merge, rather than an automatic three-way merge;
  - the UI explorer drives Playwright through Bash rather than an MCP server;
  - the run's state lives in the tracking issue's body (refusing corrupt bodies, re-read before each write) rather than on a state branch;
  - the checklist gate nudges once per turn with a safety cap of 40 a day per session, not "at most 2 a session", since ticket sessions end many turns waiting on CI;
  - a team that requires human approval uses `merge.mode: owner` (ready PRs wait for the owner) rather than auto-merge after approval;
  - the charter has no budget field: usage is watched through the account's limits, reported in pre-flight;
  - the marketplace lists the kit at `./`, so a project pins a release by the tag it vendors from, not through the marketplace;
  - tickets start infra first, then by number (the plan's order isn't kept).
- **Enforcement** (`docs/enforcement.md`): the ruleset, the credential-free ticket environment and CODEOWNERS come first; the hooks are defence in depth.
