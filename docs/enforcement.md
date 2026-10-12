# Enforcement: what actually stops a session

Prompts and hooks are not a security boundary. A session can phrase a command a hook doesn't recognise, and a hook's own files live in the repo it is working on. So the kit relies on boundaries outside the session, and uses its hooks as defence in depth.

| Layer | Enforces | Set up by |
|---|---|---|
| **GitHub ruleset on the base branch** | No direct push, no force-push, no deletion; required status checks before merge | The owner, once per repo |
| **A cloud environment for ticket sessions** | No cloud, account, deploy or payment credentials; `WORKFLOW_ROLE=ticket` | The owner, once per account |
| **CODEOWNERS on protected paths** | The kit, hooks, CI config and secrets files need the owner's review | `setup-workflow` writes it; the ruleset requires code-owner review on those paths |
| **The guard hook** | The never-list, protected paths, skip markers, sensitive posts | The kit |
| **Instructions** | Everything else | The kit |

## 1. The ruleset (GitHub → the repo → Settings → Rules → Rulesets → New branch ruleset)

- **Target:** the default branch.
- **Rules:** Restrict deletions; Block force pushes; Require a pull request before merging (required approvals **0**, so unattended runs can merge; tick "Require review from Code Owners" so changes to CODEOWNERS paths need the owner); Require status checks to pass (add the profile's `ci.required_checks`, and "Require branches to be up to date").
- **Bypass list:** empty, or the owner alone.
- **Allow auto-merge:** Settings → General → Pull Requests → "Allow auto-merge", for `merge.mode: auto-merge`.

Rulesets and branch protection on **private** repositories need a paid GitHub plan for the organisation (Team or above). Without one, the guard hook and instructions are the only line, and the charter's pre-flight says so.

A charter waiver for a killed check can't override a ruleset's required check. Where a check is known to be killed by its runners, either fix the job first or leave it out of the ruleset's required checks for the run, and let the merge rule's local evidence stand in for it.

## 2. The ticket sessions' environment (claude.ai → Claude Code → Environments)

Create an environment for ticket sessions, separate from the one the conductor and the owner use:
- **No secrets**: no AWS keys, no Auth0, Firebase or payment credentials, no deploy tokens.
- **Environment variable:** `WORKFLOW_ROLE=ticket`.
- **Network:** what the builds and tests need (package registries, container images).
- **Setup script:** the project's `commands.setup`, if it's heavy.

The conductor passes this environment's id to `create_session`. The guard also recognises ticket sessions by their branch (`run.ticket_branch`) as a fallback.

## 3. CODEOWNERS

```
# The workflow kit and its enforcement: the owner reviews every change.
/.claude/                @owner-login
/.github/workflows/      @owner-login
/.github/CODEOWNERS      @owner-login
```

## 4. What the guard does and doesn't catch

It denies, in ticket sessions (asks, in attended ones):
- `git push` to the base branch in any form it can parse: `HEAD:main`, `refs/heads/main`, `git -C . push`, inside `sh -c`, `eval`, `$(…)`, backticks or a Python one-liner;
- force-push, `+refspec`, `--force-with-lease`, deletes, `--mirror`, `--all`;
- `gh api`/`curl` rewriting the base branch's ref, its protection or rulesets;
- the profile's deploy commands;
- writes to protected paths by Edit/Write, by shell (`rm`, `mv`, `cp`, `sed -i`, `tee`, redirects, `git checkout --`) or through GitHub's file tools;
- a new skip marker in a test file;
- a GitHub post (issue, comment, PR) matching the profile's sensitive patterns.

It can't see: a script file the session writes and then runs, network calls made by programs, obfuscated commands, or anything outside Claude Code's tools. That is why the ruleset and the credential-free environment come first.
