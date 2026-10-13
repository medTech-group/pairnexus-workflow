# Changelog

## 0.1.4

- **The guided start** (`skills/start`): you don't need to remember a command.
  - At the first message of an attended session, Claude asks "What are we working on?", with choices to click (`AskUserQuestion`).
  - The choices come from where the project stands: carry on a planned item, a map decision, a ready ticket or a PR waiting; something new or a change; a fix; sorting new issues; a brand-new project or large effort; an unattended run.
  - It splits a request into items, and proposes a path for each, always offering a spec as well: a quick ticket, finding the cause first, a spec, a map, or adding to an existing issue.
  - It proposes an order, and files each item as an issue (`<!-- workflow:item path=… -->`), so a plan outlives the session. What an item waits for becomes its tickets' `Blocked by`.
  - It offers each next step as a choice: after the interview, the spec, the tickets and each item. It recommends a fresh session after a spec, a build or a map, and commits the session's files before any stop.
  - "Carry on" picks up a PR waiting for you, work an earlier session claimed, a planned item (with its interview's decisions), a spec without tickets, a map decision or a ready ticket.
  - Sorting new issues follows `triage`, with flow §2's rule for a ticket made ready.
  - A clear first request (a question, "build #262", a command) skips the menu. `/start` brings it back any time. `project.guided_start = false` turns the first-message menu off.
- **`workflow status`**: where the project stands, for the guided start:
  - whether the kit is set up, and whether the project is brand new;
  - an unattended run, claimed work and open PRs;
  - planned items, maps, specs and ready tickets;
  - what waits on a person, and new issues to sort.
- **The flow comes into context for the planning commands on their own:** `/to-spec`, `/to-tickets`, `/wayfinder`, `/grill-with-docs`, `/triage`, `/implement` and `/implement-spec`.
- **`flow.md`:**
  - starting with the guided start, and handovers offered as choices;
  - a spec starts from `grill-with-docs` (or a map's decisions) in the same session;
  - the glossary and ADRs are committed with a pull request, and research notes stay on a `research/` branch (§2's new step and checklist line, §1 step 4);
  - a map's spec is linked from its Destination item, and the map is closed once every item has its spec and tickets;
  - an issue triaged to `ready-for-agent` gets a build ticket's `Blocked by`, `Area:` and acceptance criteria;
  - `implement` and `implement-spec` build with `build-ticket`;
  - the map gate is stated in §1, with who applies it.
- **The conductor's kick-off** lists ready tickets of a map whose Destination isn't fully specified, and recommends leaving them out: `workflow ready` doesn't know about maps.
- **`build-ticket`:** in an attended session that builds more than one thing, each ticket gets its own fresh branch, not named like `run.ticket_branch`.
- **For projects updating to 0.1.4:**
  - `update-workflow` also updates the "Workflow" section of the project's `CLAUDE.md`: a session starts with the guided start (the `start` skill: "What are we working on?", or `/start`);
  - nothing changes in the profile unless you want `guided_start = false`.
- **README:**
  - "Using it" opens with the guided start: where to run it, what the first message does, the paths, an example, the handovers, changing course and long sessions;
  - "Planning new work: what happens underneath" covers every step's command, `/wayfinder`, the side trips, and a table of every Matt Pocock skill in a project (who starts it, how it fits, where its files go, the plugin's prefix);
  - a brand-new project, step by step, with its first ticket built attended and its CI as an owner pull request.

## 0.1.3

From probing pair-drop's two cloud environments: both failed to start, because their setup script installed the project's dependencies from the repository's files, and an environment's setup script runs before the repository is there.

- **The project's own dependencies install at session start.** In cloud sessions (`CLAUDE_CODE_REMOTE=true`; a laptop's checkout is its owner's), the profile's `commands.setup` runs from the kit's SessionStart hook whenever the new `commands.setup_check` fails (it exits 0 once setup has run). A cloud session starts from a fresh clone, so this is every new session; a resumed one finds it in place. The session's context says "Project setup … ran" or "FAILED, exit N", never silence. `workflow repair` runs it too, and exits 1 when it fails. The hook's timeout is 600 s, with setup given up to 510 s of it.
- **The environments' setup script holds only machine tools** the cloud image lacks: the new `run.environment_setup`, empty for most projects whatever their stack (Python, Node.js, a frontend or none). The README's step 5 says what goes where, with examples, and that a script reading the repository's files stops every session in that environment.
- **Environments can be shared** by repositories whose setup scripts match, since they hold nothing of one project; a conductor that releases holds that project's secrets and gets its own.
- `setup-workflow` fills in `commands.setup_check` and `run.environment_setup`, and the PR body says "leave Setup script blank" when it is empty.

## 0.1.2

Documentation for owners, from setting up pair-drop with 0.1.1.

- **"Getting started" opens the README,** step by step with every click: GitHub access and plan (once); asking Claude to run `setup-workflow`, and what it asks; merging its PR; the ruleset; "Allow auto-merge"; the two Claude environments; checking it all; then using it (`/next`, an unattended run, changing and stopping one) and keeping it up to date.
- **Why the environment names must match,** and **both environments are per repo**, each with the project's setup script: the conductor runs the project's tests for its own fixes (`conductor_fixes`, on by default) and its release steps. `enforcement.md` no longer says they are "once per account".
- **The ruleset's bypass list is empty** (sessions act through the owner's account, so what the owner may bypass, they may too), **"Allow merge commits" stays on** and **"Require linear history" off** (sessions merge with a merge commit). A CI that skips paths is fixed in CI, by letting each required job report on every PR.
- **The conductor** treats a missing ticket environment as a blocking pre-flight problem, and never starts ticket sessions in another.
- **`setup-workflow`** writes the one-time steps into its PR body with this project's values (check names, environment names, setup script), so the owner can do them from the PR alone, and ends them with a check.
- **The `workflow kit` CI template** runs read-only (`permissions: contents: read`, `persist-credentials: false`).
- `flow.md` names the project's glossary (`GLOSSARY.md`, or its own name), not `CONTEXT.md`.

## 0.1.1

From the practice run on the sandbox repo (run 2026-10-12-words).

- **Agents' posts carry a marker.** Every comment, issue and PR body an agent posts goes out under the owner's account, so "the owner's comments are amendments" couldn't tell them apart. Every agent post now ends with `<!-- workflow:agent -->` (`scripts/workflow/posts.py`):
  - the guard refuses, in ticket and conductor sessions, a post that creates text without it (`gh issue|pr create|comment`, an edit or close with a body or comment, `gh api` to the issue, comment, PR and review endpoints with a `body` field or `--input`, the text-posting GraphQL mutations, and the GitHub MCP tools that post). It looks in the same texts as the sensitive-data check. Labels, assignees, state changes and merges aren't posts; attended sessions aren't asked;
  - `workflow comments --owner <login> --file comments.json [--since-id N]` lists the owner's own words: their comments without the marker;
  - the tracking and by-hand issue templates, the run report and the ticket briefing end posts with it.
- **The owner's answers in the conductor's chat** are recorded on the issue they concern, quoting the owner with `source: "chat <UTC time>"`; such an answer may close the owner task it completes, and a charter change is an amendment with the same source.
- **Readiness** notes a ticket whose body names one of the profile's protected paths ("names protected path <path> (<pattern>): check it isn't an owner task"), matched as the guard matches them (`issues.readiness(protected=…)`); the ticket stays ready, and the conductor lists noted tickets at kick-off for the owner to keep or exclude. The flow says such a change is an `owner-task`, and a ticket fixing a failing or flaky required check is `workflow:infra`.
- **A run waiting on the owner isn't done.** It keeps going, checking in every 60 minutes, only while in-scope tickets are blocked by open owner tasks or are `needs-human` tickets the conductor asked the owner about during the run (`asked_at` in the state); one "waiting on you" note per task or question; it stops at the end time or when nothing remains.
- **Pre-flight** also checks "Require branches to be up to date" (`strict_required_status_checks_policy`), raised as a safety gap when off. `enforcement.md` and `setup-workflow` now advise leaving "Require review from Code Owners" off while sessions act under the owner's account (an author can't approve their own PR), and on when agents have their own GitHub identity.
- **Sessions started are checked:** `get_session` confirms each new session's `permission_mode` (a mode it can read that differs: archived and reported; no field at all: noted once and carried on), and a claim is read back after the label is added (retried once, else the ticket is skipped that check-in).
- **Briefings copied exactly.** `workflow render` ends the briefing with `Briefing <sha256[:12]>`, prints it with `--print` (the default) and keeps a copy with `--out`; the conductor passes it verbatim and records the hash as the ticket's `briefing`. The session writes what it received to `.workflow/briefing.md`, runs `workflow briefing verify --file .workflow/briefing.md` (`Briefing <hash> intact`, `Briefing changed: expected <a>, got <b>` or `no Briefing line`; trailing whitespace ignored) and quotes that line in its first comment; anything but `intact` and the conductor stops the session and retries.
- **The tracking issue's charter section** sits between `<!-- workflow-charter:begin -->` and `<!-- workflow-charter:end -->`; `workflow charter splice --body body.md --charter charter.json --out body.md [--tickets …]` replaces just that section, and refuses a body without the markers.
- **Merging when auto-merge can't be armed:** in `auto-merge` mode, when GitHub refuses because the PR is already clean, whoever tried (the session, or the conductor) re-checks the merge rule and merges with a merge commit. The guard already allowed a ticket session's own merge (`gh pr merge`, `gh api -X PUT …/pulls/<n>/merge`, the MCP merge tool); tests now pin it. The conductor never merges a change to a protected path itself: it goes in `for_owner`.
- **The claim label:** one rule everywhere. The session always removes `workflow:in-progress` when its ticket ends (and `ready-for-agent` on `needs-human`); the conductor removes leftovers.
- **Waking the conductor.** At kick-off the conductor creates a poke-only routine bound to its own session (`wake_trigger` in the state, a required `wake_trigger` slot in the briefing; `null` and `none` if `create_trigger` fails); a ticket session fires it when its ticket ends ("#N merged in #PR", "#N needs-human" or "#N stopped"; `fire_trigger` is a deferred tool loaded with ToolSearch, tried once, never blocking the ticket), the conductor treats the wake as a check-in, and deletes the routine when the run stops.
- **Spike:** rows 8 and 9 verified, rows 4 and 11 partly, by the sandbox run; row 13 (the wake routine end to end, a child's `permission_mode`) not yet.
- **Ticket sessions use no GraphQL.** `gh api graphql` is refused in the ticket role, reads included: auto-merge (`enable_pr_auto_merge`), comments and reads go through the GitHub MCP tools or REST. Three review passes each found a new way for the shell to assemble a query the guard couldn't read (a `#` or quote in another field, `-ifquery=…`, a field name from a variable, brace expansion, `xargs`). The conductor keeps GraphQL, with the dangerous mutations still refused.
- **Ticket sessions also refuse** `gh` aimed at another repository (`-R other/repo`, `GH_REPO`, `GH_HOST`, gh's token variables), a `gh` or `git` command built from a shell function's or script's parameters (`f() { git push "$@"; }; f origin main`; text that mentions one goes in a quoted heredoc), git that runs a program the guard can't see (`rebase --exec`, `bisect run`, `submodule foreach`, `filter-branch`, `difftool`, `mergetool`, editor and diff-driver settings), git writing a protected path through `--output`, `format-patch -o`, `archive -o` or `bundle create`, `gh auth status --show-token`, and curl writes to GitHub with a flag's value joined to it (`-d@q.json`, `-Tfile`, `-K cfg`) or the host in capitals.
- **From the review of 0.1.1:**
  - `workflow comments` reads every shape the conductor fetches: a list, `--paginate --slurp` pages, arrays one after another, `gh issue view --json comments` and the MCP tool's (`author.login`, node ids, the number from the URL); ids compared as numbers; anything else a clear error. The conductor fetches with `gh api --paginate --slurp`.
  - Protected paths in readiness: not in fenced code (unless the prose before it asks for a change "to" or "in" it), not after "don't", "do not" or "never" in their clause, not a file their clause only reads (a clause ends at a sentence's end, a semicolon, a colon or a dash; when in doubt, noted), and a bare dot-name only when it is itself protected; `path#L20` anchors and blob/tree URLs into the repo are read.
  - The marker rule: `gh issue|pr reopen --comment` and commit comments are posts; `--input` JSON without a `body` or `comment`, GraphQL mutations whose arguments (lexed as GraphQL lexes them, with the operation's variable defaults; a fragment on the mutation counts as a post) carry no body, and `--delete-last` aren't; the conductor's GraphQL from `--input` (a file or stdin) is read from its JSON's `query`. `enforcement.md` says the marker is checked in the command's texts as a whole.
  - The evidence report ends with the marker.
  - The conductor: "a check-in is pending" defined (an enabled one-shot routine bound to it; the wake routine never counts), "A check-in is complete" kept apart from "Done"; the path back from a `needs-human` ticket once the owner answers, and how attempts count; `--only` takes every open `workflow:infra` ticket.

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
- **The final Correctness pass** after round 3 changed: a deploy script run with `.`; the default branch sent on stdin from a file or a pipe; a writing `find` from the project root checked against the protected files there by name; a pull request as a blocker, resolved once merged; the gate's reasons read as words; "doesn't" and "won't" read as negations. Two more passes on those fixes: a find from the root is read exactly (a plain `-name … -delete` or `-exec`, matched against every file there, directories holding protected paths and links to them included) or treated as a write into the whole tree; a symlinked root; `--input` from any spelling of stdin; an escaped `default_branch`; `-execdir` run where its match is; `-L` and `-follow`; `$PWD` and `$(pwd)` in paths; non-ASCII `-iname`; and writers run by `xargs`, whose targets are what the producer names exactly (plain `echo` or `printf '%s\n'` words, or a search checked as a tree; `find … -delete` is the way to delete what a find matches from the root), else unknown.
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
