# Enforcement: what actually stops a session

Prompts and hooks are not a security boundary. A session can phrase a command a hook doesn't recognise, and a hook's own files live in the repo it is working on. So the kit relies on boundaries outside the session, and uses its hooks as defence in depth.

| Layer | Enforces | Set up by |
|---|---|---|
| **GitHub ruleset on the base branch** | No direct push, no force-push, no deletion; required status checks before merge | The owner, once per repo |
| **Cloud environments per role** | Ticket sessions: no cloud, account, deploy or payment credentials, `WORKFLOW_ROLE=ticket`. The conductor: `WORKFLOW_ROLE=conductor` and only the release credentials the owner chooses | The owner, once per account |
| **CODEOWNERS on protected paths** | The kit, hooks, CI config and secrets files need the owner's review | `setup-workflow` writes it; the ruleset requires code-owner review on those paths |
| **The guard hook** | The never-list, protected paths, skip markers, sensitive posts | The kit |
| **Instructions** | Everything else | The kit |

## 1. The ruleset (GitHub → the repo → Settings → Rules → Rulesets → New branch ruleset)

- **Target:** the default branch.
- **Rules:** Restrict deletions; Block force pushes; Require a pull request before merging (required approvals **0**, so unattended runs can merge; tick "Require review from Code Owners" so changes to CODEOWNERS paths need the owner); Require status checks to pass (add the profile's `ci.required_checks`, and "Require branches to be up to date").
- **Bypass list:** empty, or the owner alone.
- **Enforcement status: Active.** A ruleset left "Disabled" or "Evaluate" enforces nothing.
- **Allow auto-merge:** Settings → General → Pull Requests → "Allow auto-merge", for `merge.mode: auto-merge`.

Rulesets and branch protection on **private** repositories need a paid GitHub plan for the organisation (Team or above). Without one, the guard hook and instructions are the only line, and the charter's pre-flight says so.

A charter waiver for a killed check can't override a ruleset's required check. Where a check is known to be killed by its runners, either fix the job first, or leave it out of the ruleset's required checks for the run and use `merge.mode: session`, where the session reads that check's log for a killed marker and posts the local evidence before merging. Never combine a waiver with GitHub auto-merge: it can't tell killed from failed.

## 2. The environments (claude.ai → Claude Code → Environments)

Two environments, named in the profile (`run.ticket_environment`, `run.conductor_environment`):

**Ticket sessions**
- **No secrets**: no AWS keys, no Auth0, Firebase or payment credentials, no deploy tokens.
- **Environment variable:** `WORKFLOW_ROLE=ticket`.
- **Network:** what the builds and tests need (package registries, container images).
- **Setup script:** the project's `commands.setup`, and Playwright's Chromium when the profile's explorer is `browser`.

**The conductor**
- **Environment variable:** `WORKFLOW_ROLE=conductor`, so the guard denies (rather than asks a person) and allows the release steps.
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
- `gh` may run only the PR, issue, run and read subcommands a ticket needs;
- `gh api` writes may touch only issues, comments, labels and pull requests of the profile's repo, and GraphQL only `enablePullRequestAutoMerge` and `addComment`;
- `git config` may not set aliases, push settings, `core.*` hooks, editors, ssh commands, credentials or includes; `GIT_CONFIG*`/`GIT_SSH*`/`GIT_DIR` assignments and `--config-env` are refused.

**In every role** it denies (asks, in attended sessions):
- pushes to the base branch in any form it can parse (refspecs, `HEAD`, `@`, abbreviated options, `send-pack`, `git-push`), force-pushes, deletes, `--mirror`, `--all`;
- `gh pr merge --admin`;
- rewriting, renaming or merging into the base branch, its protection, its rulesets or the default branch through the API.

**In ticket sessions it also denies:**
- the profile's deploy commands, however they're run (directly, through a shell, piped, `env -C`, `find -exec`);
- writes to protected paths, `.git/config` and `.git/hooks/**`, by Edit/Write, by the shell's writers (redirects, `cp`/`mv`/`install`/`rsync`/`ln` destinations, `rm`, `sed -i`, `perl -pi`, `dd`, `tee`, `mkdir`, `curl -o`, `wget -O`, `find -delete`, `git rm`/`mv`/`checkout`/`restore`, archives and patches that touch them, deleting a parent directory, globs and brace lists that expand to them, symlinks resolved), or through GitHub's file tools;
- a new skip or focus marker in a test file (`conftest.py` included);
- switching to a branch outside the pattern when the role comes only from the branch name.

A GitHub post (MCP or `gh`, including heredoc bodies and `--body-file`/`--input` files) matching the profile's sensitive patterns is refused in every role.

**When something is wrong it fails closed** in ticket and conductor sessions (`WORKFLOW_ROLE` set, or set to a value it doesn't recognise, which counts as ticket):
- an invalid or missing profile;
- a malformed hook event;
- an error in the guard itself;
- the kit's CLI missing from the checkout. Then everything is refused except `git checkout -- .claude/workflow` or `git restore .claude/workflow`, which restore it.

In attended sessions the hooks report the error and stay out of the way.

**It can't see** a script file the session writes and then runs, network calls made by programs, or deliberately obfuscated commands. It is a seatbelt for honest mistakes, not a wall against an adversary. That is why the ruleset and the credential-free environment come first.

**A lesson from building this kit:** a review agent testing the guard ran its own test cases by accident. Its heredoc's delimiter appeared inside a case, so the shell ran the rest as commands. One of them pushed to the kit repo's `main`, which had no active ruleset at the time. Reviewers and explorers that try dangerous commands work only in throwaway copies, never in the real checkout, and the ruleset is what makes such an accident harmless.
