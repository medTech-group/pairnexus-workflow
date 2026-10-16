# The profile

`.claude/workflow/profile.toml` is the project's settings: everything the kit's skills, hooks and scripts read instead of anything hard-coded. `setup-workflow` writes it; `workflow profile check` validates it (errors stop the hooks in ticket and conductor sessions; warnings don't). Prose that doesn't fit a setting (safety rules by reference, data classification, wording) goes in `profile.md` beside it.

It sits in `.claude/`, a protected path: ticket sessions can't change it, and a change is a pull request the owner merges. The commented template, with every key and examples for other test runners, is `templates/profile.toml` (in a project, `.claude/workflow/templates/profile.toml`). Unknown tables and keys are errors.

## `[project]`

| Key | What it is | Default |
|---|---|---|
| `name` | The project's name | (required) |
| `repo` | `owner/repo` of the GitHub issue tracker | (required) |
| `base_branch` | The branch pull requests target; the ruleset protects it | `main` |
| `owner` | The owner's GitHub login, without `@`: only their approval and comments count in runs | empty (a warning) |
| `rules` | Files (with an optional `#heading`) holding the project's own rules; reviewers read them | `[]` (the template has `["CLAUDE.md"]`) |
| `flow_addendum` | A project file read with the kit's flow | empty |
| `guided_start` | The first-message menu in attended sessions; `/start` works either way | `true` |
| `ruleset` | `true` or `false`. `false` is **solo mode**: no GitHub ruleset protects the base branch yet, so the kit's own guard is all that stops a change to it. `true` says a ruleset protects it. Write it as a plain `ruleset = true` or `ruleset = false` line, with nothing after it: a shell script reads it without a TOML parser. The template leaves it out; set-up writes it | absent: not set (as before) |
| `experience` | How much the people working here know, as the project's default: `"new"` (new to building) or `"developer"`. It names no person, and changes only wording and pacing, never what the guard refuses (see "Experience" below) | absent: the person is asked (set-up or the guided start asks, once those tickets land); until then, unknown |

Any other value of `ruleset` or `experience` is a `workflow profile check` error, so a typo never silently turns solo mode off. `workflow status` reports both: `Solo mode: yes`, `no` or `not set (as before)`, and `Experience:` with where it came from.

### Experience

Each person's experience is worked out by one function, `resolve_experience` in `scripts/workflow/profile.py`. `workflow status` reports what it finds. The guard's solo-mode tickets will call the same function, and skills will read the level from `status`. The first of these that holds a value wins:

1. `WORKFLOW_EXPERIENCE` in the environment: `new` or `developer`. Set it on a claude.ai environment to keep a cloud session's answer.
2. `.workflow/experience` in the project: one line, `new` or `developer`, written by a local session. `.workflow/` is untracked, so a person's level never lands in the repository's history.
3. The profile's `project.experience`.
4. Unknown. Wording then treats the person as new to building, since skipping the question counts as new.

In the environment and the file, case and spaces around the value don't matter (the profile takes only `"new"` or `"developer"`, exactly). An unrecognised value there is skipped, with a warning in `workflow status` that doesn't repeat the value; it never makes a hook fail.

## `[commands]`

| Key | What it is |
|---|---|
| `setup` | Installs the project's own dependencies (`npm ci`, a virtualenv). Run at the start of each **cloud** session when `setup_check` fails, with about 8 minutes to finish. **Never runs without `setup_check`** (a warning). |
| `setup_check` | Exits 0 when `setup` has run, e.g. `test -d node_modules` |
| `typecheck` | The typecheck, or empty |
| `test_file` | One test file, `{file}` replaced: sessions run it as they go |
| `[[commands.package]]` | Parts of a monorepo with their own `typecheck` and `test_file`: `name`, `path` (a glob of the files it covers), optional `cwd` |
| `[[commands.suite]]` | The full suite, one table per suite: `name`; `run` (`{files}` replaced by a shard's files); `files` (comma-separated globs from the project root, or empty to run once); `group` (files per shard); optional `cwd`; and the count regexes `passed`, `failed`, `skipped`, `errors`, optionally `total`. A shard that exits 0 with nothing counted fails. The template gives the regexes for pytest, jest, flutter, go (gotestsum) and Playwright. **It ships a pytest suite: replace it for any other runner.** |

`workflow evidence` runs the suites in shards, resumes by commit after a restart, and posts the counts on the pull request. The merge rule needs that evidence when a check is waived or the project has no CI.

## `[ci]`

| Key | What it is | Default |
|---|---|---|
| `required_checks` | The base branch's required checks, as their names show on a PR. Must equal the ruleset's (vendored mode adds `workflow kit`) | `[]` |
| `none` | No CI: the posted local suite is the merge gate, runs merge as `session`, and every run report says "add CI" | `false` |
| `path_filtered` | Required checks a workflow's `paths`/`paths-ignore` can skip; a run hands those PRs to the owner | `[]` |
| `killed_markers` | Log lines that mean a check was killed, not failed, for a waived check | `[]` (the template lists the runners' shutdown messages) |

## `[ui]`

| Key | What it is | Default |
|---|---|---|
| `explorer` | How the review panel's explorer tries a change from outside: `browser` (Playwright in Chromium: install it with `commands.setup`, and allow its download host if the network is limited), `api`, `cli` or `none` | `none` |
| `start` | Commands that start the stack and app for the explorer | `[]` |
| `sizes` | Browser viewports | `[]` (the template has a phone and a desktop size) |
| `notes` | Anything the explorer should know | empty |

## `[guard]`

| Key | What it is | Default |
|---|---|---|
| `protected_paths` | Paths ticket sessions may not change (the conductor only by a reviewed PR). **A list here replaces the defaults: keep them and add yours** (a warning when `.claude/**` or `.github/workflows/**` is missing) | `.claude/**`, `.github/workflows/**`, `.github/CODEOWNERS`, `CODEOWNERS`, `**/.env`, `**/.env.*` |
| `deploy_commands` | Commands only the owner, or the conductor under a release grant, may run. A script path matches however it's run; others by their first words. Attended sessions are asked first | `[]` |
| `test_paths` | Test files where a new skip or focus marker is refused in ticket sessions. A list here also replaces the defaults | common test file patterns |
| `allow_new_skips` | Allow new skip markers | `false` |

## `[sensitive]`

| Key | What it is |
|---|---|
| `description` | In words, what must never appear in an issue, comment, PR or notification (patients' names, phone numbers) |
| `patterns` | Regexes checked against every GitHub post, in every role; a match is refused. Anchor them so ordinary words don't match |

## `[areas]`

`<name> = [globs]`, one line per area: the parts of the project two sessions shouldn't change at once. A build ticket names one with an `Area: <name>` line (one word). A run starts at most one session per area; a ticket with no area can run beside anything, and an unknown name is its own area. The globs are hints for readers, not enforced.

## `[repair]`

`commands`: re-runnable environment repairs (start Docker, a database) run at session start, by `workflow repair`, and before each evidence shard. Each must be safe to run twice.

## `[release]`

`[[release.steps]]`: `name`, `run`, and optional `smoke` (a smoke test). A run releases only with the charter's grant (`release.when`: never, once at the end, or after each merge), from the base branch, logged on the tracking issue. A stopped run never releases.

## `[run]`

| Key | What it is | Default |
|---|---|---|
| `ticket_branch` | Ticket sessions' branches; a session on one counts as a ticket session even without `WORKFLOW_ROLE` | `claude/build-*` |
| `check_in_minutes` | The conductor's check-in cadence (a run's charter takes 5–240) | `20` |
| `max_parallel` | Ticket sessions at once (1–16) | `2` |
| `max_retries` | Retries per ticket before `needs-human` (0–5) | `1` |
| `review_rounds` | Review panel rounds at most (1–10) | `3` |
| `ticket_environment` | The claude.ai environment ticket sessions run in, by name: no credentials, `WORKFLOW_ROLE=ticket` | empty (a warning) |
| `conductor_environment` | The conductor's environment, by name: `WORKFLOW_ROLE=conductor` | empty (a warning) |
| `environment_setup` | The environments' setup script: machine tools the cloud image lacks only, never reading the repository. Usually empty | empty |
| `permission_mode` | Ticket sessions' mode: one that never prompts. `auto`; `bypassPermissions` in a sandbox; `dontAsk` or `acceptEdits` only with allow rules (`acceptEdits` still asks before shell commands). No more permissive than the conductor session's | `auto` |

The run's limits default from here; each run's charter can change them (`charter.md`).

## Environment variables

| Variable | Read by | What it does |
|---|---|---|
| `WORKFLOW_ROLE` | The hooks | `ticket`, `conductor` or `attended` (any case). Set it in the claude.ai environment, never in the profile. Any other value counts as `ticket`, the strictest |
| `WORKFLOW_EXPERIENCE` | `workflow status` | `new` or `developer`: this person's experience, ahead of `.workflow/experience` and `project.experience` (see "Experience" above). Any other value is skipped with a warning |
| `WORKFLOW_UPDATE_CHECK` | The session start | `off` (or `0`, `false`, `no`) stops the lookup of the latest kit release |
| `TMPDIR` | The hooks | Where the hooks keep their per-session markers and the latest-release cache (six hours) |
