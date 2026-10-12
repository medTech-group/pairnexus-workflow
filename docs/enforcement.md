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

In ticket sessions it works by **allow-list** where a deny-list can't keep up:
- `git push` may only update branches matching `run.ticket_branch` (any form it can parse: refspecs, `HEAD`, `@`, `-C`, `cd`, inside `sh -c`, `eval`, `$(…)`, backticks, shell keywords, wrappers, line continuations);
- GitHub API writes may only touch issues, comments, labels and pull requests; GraphQL mutations aren't allowed; `curl` writes to GitHub aren't allowed;
- `git config` may not set aliases or push settings.

In every role it denies (asks, in attended sessions): pushes to the base branch, force-pushes, deletes, `--mirror`, `--all`, `gh pr merge --admin`, and rewriting the base branch's ref, protection or rulesets (REST or GraphQL), merging into it through the merges API, or writing it through the contents API.

In ticket sessions it also denies: the profile's deploy commands (by the command run, not by mentions); writes to protected paths by Edit/Write, by the shell's common writers (redirects, `cp`/`mv`/`install`/`rsync` destinations, `rm`, `sed -i`, `perl -pi`, `dd of=`, `tee`, `mkdir`, `git rm`/`mv`/`checkout`, deleting a parent directory, after a `cd`) or through GitHub's file tools; a new skip or focus marker in a test file; and switching to a branch outside the pattern when the role comes only from the branch name. A GitHub post (MCP or `gh`) matching the profile's sensitive patterns is refused in every role.

If the guard itself fails, or the profile is invalid, it refuses in ticket and conductor sessions (`WORKFLOW_ROLE` set) and reports the error in attended ones. If the kit's CLI is missing from the checkout, the hooks do nothing rather than block every tool.

It can't see: a script file the session writes and then runs, network calls made by programs, obfuscated commands, or anything outside Claude Code's tools. That is why the ruleset and the credential-free environment come first.
