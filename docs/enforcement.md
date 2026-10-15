# Enforcement: what actually stops a session

Prompts and hooks are not a security boundary. A session can phrase a command a hook doesn't recognise, and a hook's own files live in the repo it is working on. So the kit relies on boundaries outside the session, and uses its hooks as defence in depth.

| Layer | Enforces | Set up by |
|---|---|---|
| **GitHub ruleset on the base branch** | No direct push, no force-push, no deletion; required status checks before merge | The owner, once per repo |
| **Cloud environments per role** | Ticket sessions: no cloud, account, deploy or payment credentials, `WORKFLOW_ROLE=ticket`. The conductor: `WORKFLOW_ROLE=conductor` and only the release credentials the owner chooses | The owner; shared by repos whose environment setup scripts match, often blank (§2) |
| **CODEOWNERS on protected paths** | Changes to the kit and its hooks (`.claude/`), CI config (`.github/workflows/`) and CODEOWNERS itself ask for the owner's review | `setup-workflow` writes it; the ruleset can require that review only when agents have their own GitHub identity (§1) |
| **The guard hook** | The never-list, protected paths, skip markers, sensitive posts, the agents' marker on posts | The kit |
| **Instructions** | Everything else | The kit |

## 1. The ruleset (GitHub → the repo → Settings → Rules → Rulesets → New branch ruleset)

- **Target:** the profile's `project.base_branch`, normally the default branch ("Include default branch"); if they differ, target the base branch by name.
- **Rules:** Restrict deletions; Block force pushes; Require a pull request before merging (required approvals **0**, so unattended runs can merge: with more, the conductor recommends `merge.mode: owner` and runs stop at "ready for review"; "Require review from Code Owners": see below); Require status checks to pass (add the profile's `ci.required_checks`, and tick "Require branches to be up to date", which the API calls `strict_required_status_checks_policy`).
- **Bypass list:** empty. Sessions act through the owner's GitHub account, so whatever the owner may bypass, a session may too.
- **Merge settings:** keep "Allow merge commits" on and "Require linear history" off: sessions and the conductor merge with a merge commit.
- **Enforcement status: Active.** A ruleset left "Disabled" or "Evaluate" enforces nothing.
- **Allow auto-merge:** Settings → General → Pull Requests → "Allow auto-merge", for runs whose charter says `merge.mode: auto-merge`. The merge mode is chosen per run, in the charter (`charter.md` §2), not in the profile.

**"Require review from Code Owners": leave it off while sessions act under the owner's GitHub account** (the usual setup: the GitHub connector and `gh` both use the owner's token). Every PR a session opens is then the owner's own, and GitHub never lets an author approve their own PR, so a PR touching a CODEOWNERS path could never merge. With it off, CODEOWNERS still requests the owner's review on those PRs, and the protected paths stay protected by the guard, by the ticket environment having no credentials, and by such PRs going to the owner (a ticket that changes one is an owner task, never a build ticket).

Turn it on when agents use their own GitHub identity (a bot account or a GitHub App): then the owner is a different person from the PR's author, and their approval is what merges a change to a protected path.

"Require branches to be up to date" matters more than it looks: without it, two PRs that are each green against an older base can both merge and break the base together. If the owner leaves it off, the conductor's pre-flight raises it as a safety gap, and the conductor (or session) checks the branch is level with the base before each merge (flow §4.3).

Rulesets and branch protection on **private** repositories need a paid GitHub plan for the organisation (Team or above). Without one, the guard hook and instructions are the only line, and the charter's pre-flight says so.

A charter waiver for a killed check can't override a ruleset's required check. Where a check is known to be killed by its runners, either fix the job first, or leave it out of the ruleset's required checks for the run (the conductor's pre-flight then shows the difference from `ci.required_checks` as a gap for the owner to accept) and use `merge.mode: session`, where the session reads that check's log for a killed marker and posts the local evidence before merging. Never combine a waiver with GitHub auto-merge: it can't tell killed from failed.

## 2. The environments (claude.ai/code → the environment menu → add, or Edit)

Two environments, named in the profile (`run.ticket_environment`, `run.conductor_environment`). The kit's README has the clicks: https://github.com/medTech-group/pairnexus-workflow#step-5-create-the-two-claude-environments.

**The names must match exactly.** An environment's id belongs to the owner's Claude account, so the repo records names instead. The conductor lists the account's environments, takes the one named `run.ticket_environment`, and starts every ticket session in it. With no environment of that name it stops in pre-flight and starts nothing. A ticket session in the wrong environment would have whatever credentials that environment holds, and no `WORKFLOW_ROLE`.

**Setup script: machine tools only.** An environment's setup script runs before the repository is there and is cached for later sessions, so it holds only machine-level tools the cloud image lacks (the profile's `run.environment_setup`; usually nothing). A script that reads the repository's files fails, and then no session in that environment starts. The project's own dependencies are `commands.setup`, which the kit's SessionStart hook runs in each cloud session, from the fresh clone, whenever `commands.setup_check` fails, and reports in the session's context ("Project setup … FAILED" when it does). So an environment holds nothing of one project, and repos whose setup scripts match can share a pair; a conductor that releases holds that project's release secrets, and gets its own.

**Ticket sessions**
- **No secrets**: no AWS keys, no Auth0, Firebase or payment credentials, no deploy tokens.
- **Environment variable:** `WORKFLOW_ROLE=ticket`.
- **Network:** what the builds and tests need (package registries, container images).
- **Setup script:** the profile's `run.environment_setup`, usually blank.

**The conductor**
- **Environment variable:** `WORKFLOW_ROLE=conductor`, so the guard denies (rather than asks a person) and allows the release steps.
- **Setup script:** the same as the ticket sessions'. The conductor's own fixes run the project's tests, and the kit installs the project's dependencies at session start as for a ticket session.
- **Secrets:** only what the charter's release steps need, if the owner wants releases unattended.

The conductor checks its own `WORKFLOW_ROLE` in pre-flight, and passes the ticket environment's id and the profile's `run.permission_mode` (`auto` recommended; a mode that prompts would stall an unattended session) to `create_session`.

The guard also recognises ticket sessions by their branch (`run.ticket_branch`) when `WORKFLOW_ROLE` isn't set. That fallback is a convenience, not a boundary: a session can change its branch (the guard refuses switching away from the pattern, but only the environment variable can't be changed from inside).

## 3. CODEOWNERS

```
# The workflow kit and its enforcement: the owner reviews every change.
/.claude/                @owner-login
/.github/workflows/      @owner-login
/.github/CODEOWNERS      @owner-login
```

## 4. What the guard does and doesn't catch

It reads each command the way a shell would, well enough to catch a well-meaning session's mistakes and the obvious tricks:
- operators and subshells wherever they sit (`;(`, `&&(`, `$(…)`, backticks, `<(…)`, function bodies);
- heredocs (scanned when they feed a shell, or when their delimiter can't be read);
- the shell's working directory, from the hook event and through `cd`/`pushd`;
- wrappers (`sudo`, `env`, `timeout`, `xargs`, `script -c` …), and a `git` or `gh` anywhere in a command's words;
- file-descriptor redirects (`2>&1` is a redirect, not an argument).

**In ticket sessions, by allow-list:**
- `git push` may update only the session's own ticket branch: no tags, no other branches, and a bare push only when the upstream has the same name;
- `gh` may run only the PR, issue, run and read subcommands a ticket needs, in the profile's repository alone (`-R`/`--repo` or a pull request or issue URL naming another, or `GH_REPO`, `GH_HOST` and gh's token variables set, are refused), never with a function's or script's parameters (`"$@"`, `$1`; text that mentions one goes in a quoted heredoc, `-m "$(cat <<'EOF' … EOF)"`, or a file with `-F`/`--body-file`), and never printing the token (`gh auth status --show-token`);
- `gh api` writes may touch only issues, comments, labels and pull requests of the profile's repo, and never GitHub's GraphQL API (auto-merge, comments and reads go through the GitHub MCP tools or REST: the shell can assemble a GraphQL query in more ways than the guard can follow); merging its own PR (`gh pr merge`, `gh api -X PUT repos/<repo>/pulls/<n>/merge`, the GitHub MCP merge tool) is allowed, since the ruleset still decides what may merge into the base branch;
- git that runs a program the guard can't see is refused (`rebase --exec`, `bisect run`, `submodule foreach`, `filter-branch`, `difftool`, `mergetool`, editor and diff-driver settings or variables other than a no-op `GIT_EDITOR=true`), and `git diff|log --output`, `format-patch -o`, `archive -o` and `bundle create` count as writes (under `git -C` too);
- `git config` may not set aliases, push settings, `core.*` hooks, editors, ssh commands, credentials or includes; `GIT_CONFIG*`/`GIT_SSH*`/`GIT_DIR` assignments and `--config-env` are refused.

**In every role** it denies (asks, in attended sessions):
- pushes to the base branch in any form it can parse (refspecs, `HEAD`, `@`, abbreviated options, `send-pack`, `git-push`), force-pushes, deletes, `--mirror`, `--all`;
- `gh pr merge --admin`;
- rewriting, renaming or merging into the base branch, its protection, its rulesets or the default branch through the API.

In attended sessions the guard doesn't stop changes to protected paths: the person sees them in the pull request, which is theirs to merge.

**In ticket sessions it also denies:**
- the profile's deploy commands, however they're run (directly, through a shell, piped, `env -C`, `find -exec`);
- writes to protected paths, `.git/config` and `.git/hooks/**`, by Edit/Write, by the shell's writers (redirects, `cp`/`mv`/`install`/`rsync`/`ln` destinations, `rm`, `sed -i`, `perl -pi`, `dd`, `tee`, `mkdir`, `curl -o`, `wget -O`, `find -delete` and `find -exec` over a tree holding one (a plain `find DIR -name GLOB … -delete` or `-exec … {} +` that the guard can read exactly is checked by name against the files there, directories holding protected paths and links to them included; anything else is a write into the whole tree), commands run by `xargs` (their targets are what the producer names exactly, else they can't be seen), a tree checked on disk for a protected path a pattern matches anywhere (`**/.env`, up to 50,000 entries), `git rm`/`mv`/`checkout`/`restore`, archives and patches that touch them, deleting a parent directory, globs and brace lists that expand to them, symlinks resolved), or through GitHub's file tools;
- a new skip or focus marker in a test file (`conftest.py` included);
- switching to a branch outside the pattern when the role comes only from the branch name.

A GitHub post (MCP or `gh`, including heredoc bodies and `--body-file`/`--input` files) matching the profile's sensitive patterns is refused in every role.

In ticket and conductor sessions, a post that creates text (an issue, PR, comment or review, or a new body for one, through `gh issue|pr create|comment|edit|close|reopen`, `gh api` to issues, pull requests, reviews and commit comments with a `body` field, or with `--input` JSON that carries a `body` or `comment` or can't be read, the conductor's GraphQL mutations that post, or the GitHub MCP tools that do) is refused unless it carries `<!-- workflow:agent -->`: the marker that tells agents' posts from the owner's own words (`charter.md` §4). A GraphQL query sent with `--input` (a file or stdin) is read from its JSON's `query`, and a mutation that may carry a body (`updateIssue`, `updatePullRequest` …) counts only when its arguments, or the variables they take, hold one; a `body` in what it asks back doesn't count. Labels, assignees, state changes (`--input` JSON such as `{"state": "closed"}` that can be read), `gh issue|pr comment --delete-last` and merges aren't posts. Attended sessions aren't asked.

The marker is looked for in the command's texts as a whole (the command, its heredocs, its body and `--input` files, what it reads with `cat` or `<`), not in each post separately: a command that posts twice passes when either text carries it. It is a seatbelt against forgetting the marker, not proof that each post is an agent's. A conductor's GraphQL post assembled by the shell (a field name from a variable, brace expansion, `xargs`) can get past it; the conductor is trusted not to hide its posts, and ticket sessions use no GraphQL at all.

**When something is wrong it fails closed** in ticket and conductor sessions (`WORKFLOW_ROLE` set, or set to a value it doesn't recognise, which counts as ticket):
- an invalid or missing profile;
- a malformed hook event;
- an error in the guard itself;
- the kit's CLI missing from the checkout. Then everything is refused except `git checkout -- .claude/workflow` or `git restore .claude/workflow`, which restore it;
- `python3` older than 3.11, or none on the PATH (since 0.1.8). Every tool is refused until the session runs on Python 3.11 or later.

In attended sessions the hooks report the error and stay out of the way. With an old `python3` the guard still asks before a `git push` or `gh pr merge`, and the session start says what is wrong; with no `python3` at all, only the session start says so.

**It can't see** a script file the session writes and then runs, text piped into a shell, network calls made by programs (an interpreter's `subprocess.run(['git', …])`, `wget`, `fetch`), or deliberately obfuscated commands. It is a seatbelt for honest mistakes, not a wall against an adversary. That is why the ruleset and the credential-free environment come first.

**A lesson from building this kit:** a review agent testing the guard ran its own test cases by accident. Its heredoc's delimiter appeared inside a case, so the shell ran the rest as commands. One of them pushed to the kit repo's `main`, which had no active ruleset at the time. Reviewers and explorers that try dangerous commands work only in throwaway copies, never in the real checkout, and the ruleset is what makes such an accident harmless.

## 5. Checking the set-up

What an owner, or a cloud session asked to "check the workflow set-up", looks at after the set-up pull request merges. Only a cloud session can list the account's environments. Report each item as fine or as a gap with its fix; change nothing.

1. **The ruleset:** `gh api repos/<repo>/rulesets`, then `gh api repos/<repo>/rulesets/<id>` for each:
   - `enforcement` is `active`, and `conditions.ref_name.include` covers the base branch (`~DEFAULT_BRANCH` or `refs/heads/<base>`);
   - `bypass_actors` is empty;
   - its rules include `deletion` and `non_fast_forward`;
   - `pull_request`: `required_approving_review_count` 0 (more is a choice, with the consequence in §1) and `require_code_owner_review` false;
   - `required_status_checks`: every name in the profile's `ci.required_checks` (vendored mode includes `workflow kit`), and `strict_required_status_checks_policy` true;
   - no `required_linear_history` rule.
2. **The merge settings:** `gh api repos/<repo>`: `allow_auto_merge` and `allow_merge_commit` are true.
3. **CODEOWNERS** (§3) covers `/.claude/` and `/.github/workflows/`.
4. **The environments** (§2): `list_environments` shows both names in the profile's `run.ticket_environment` and `run.conductor_environment`. Nothing can read what an environment holds, so ask the owner to confirm the ticket environment has no secrets and `WORKFLOW_ROLE=ticket`, and the conductor's `WORKFLOW_ROLE=conductor`.
5. **The kit:** `python3 -B .claude/workflow/bin/workflow.py profile check` (no errors; read the warnings) and `vendor verify --strict`.

The conductor repeats items 1, 3 and 4 in every run's pre-flight.
