---
name: release-gate
description: Run the kit's release gate on a release pull request - try its exact commit on the sandbox (an update with CI green, the guard's refusal, the ruleset's refusal) and post one report whose last line the "release gate" check reads. The kit's own maintainers' skill, in a cloud session on the kit's repository. Use for "run the release gate on PR #N".
---

# The release gate

A kit release publishes the moment its `VERSION` bump merges. Before that, this skill tries the release pull request's exact commit on a real project, the sandbox, and posts one gate report on the release pull request. The "release gate" check (`.github/workflows/release-gate.yml`) reads its last line: the release pull request can't merge without a pass for its head commit.

It runs in a cloud session on the kit's repository, with the owner there to approve. It takes about 30 minutes.

- **The kit's repository** (`KIT_REPO` below): `python3 .claude/workflow/bin/workflow.py version --repo`.
- **The sandbox** (`<sandbox>` below): `medTech-group/pairnexus-workflow-sandbox`. It needs a ruleset on `main` and its ticket environment (its profile's `run.ticket_environment`).
- **Values carry over by hand:** shell variables don't last from one command to the next. Note each value as you get it (`$SHA`, `$VERSION`, the `mktemp` paths, the sandbox pull request's number) and write it out in later commands.
- **Every post carries the marker:** end each comment and pull request body with `<!-- workflow:agent -->`.
- `gh pr create` and `gh pr merge` use GraphQL, which a cloud session's proxy refuses: use `gh api` (REST) for pull requests.
- Never `sleep` while waiting: schedule a check-in (`send_later`, about 5 minutes) and carry on when it fires.

This skill is the kit repository's own (`.claude/skills/release-gate/`). It never ships: projects get only `skills/`.

## 1. The candidate

1. **The candidate is the pull request's exact commit.** Read the pull request's head commit, the full 40-character SHA, its repository, and `VERSION` at it:

   ```bash
   gh api repos/$KIT_REPO/pulls/<N> --jq '[.head.sha, .head.repo.full_name] | @tsv'
   gh api "repos/$KIT_REPO/contents/VERSION?ref=$SHA" --jq .content | base64 -d
   gh api "repos/$KIT_REPO/pulls/<N>/files?per_page=100" --paginate --jq '.[].filename' | grep -x VERSION
   ```

   Stop, saying why, when:
   - the head's repository isn't `$KIT_REPO` (a fork): the gate runs the candidate's own code with push access to the sandbox, so it runs only on the kit's own branches;
   - `VERSION` isn't three numbers (`0.2.0`): it names the sandbox branch;
   - the pull request doesn't change `VERSION`: it isn't a release pull request.
2. **Check out the candidate at that commit**, outside this session's working tree, so nothing of it is committed here by mistake:

   ```bash
   CAND=$(mktemp -d)/candidate && git clone https://github.com/$KIT_REPO "$CAND"
   git -C "$CAND" fetch origin "$SHA" && git -C "$CAND" checkout --detach "$SHA"
   ```

   `git -C "$CAND" rev-parse HEAD` must print `$SHA`.
3. **The Claude Code version.** Run `claude --version` once, here, and keep it for the report.

## 2. The sandbox branch and its pull request

A failure in this section (the update refuses, a conflict can't be merged, the push or the pull request fails) is a failure of the first check: go to section 3's "A failed check stops the gate".

1. **Add the sandbox to the session with push access** (`add_repo`, `access: "push"`), and clone it outside the working tree:

   ```bash
   SANDBOX=$(mktemp -d)/sandbox && git clone https://github.com/<sandbox> "$SANDBOX"
   ```

2. **A run on a newer commit starts afresh.** Close every open sandbox pull request whose branch starts with `release-gate/` (earlier runs), each with a comment naming the newer commit:

   ```bash
   gh api "repos/<sandbox>/pulls?state=open&per_page=100" --jq '.[] | select(.head.ref | startswith("release-gate/")) | .number'
   gh api -X PATCH repos/<sandbox>/pulls/<n> -f state=closed
   ```

   Then, whenever `release-gate/$VERSION` exists on the sandbox (an earlier run's, its pull request open, closed or never opened), delete it, so the new branch's push isn't refused: `gh api -X DELETE repos/<sandbox>/git/refs/heads/release-gate/$VERSION`.
3. **Branch from the sandbox's `main`:** `git -C "$SANDBOX" checkout -b release-gate/$VERSION origin/main`.
4. **Update the sandbox to the candidate through `update-workflow`:** follow the candidate's own `$CAND/skills/update-workflow/SKILL.md`, in the sandbox clone, with `WF` as `python3 $CAND/scripts/workflow.py`, from step 1 (where it stands) on. Three differences:
   - The update is `vendor update --kit` pointing at the candidate's checkout:

     ```bash
     WF vendor update --kit "$CAND" --project "$SANDBOX" --mattpocock <checkout> --strict-pin
     ```

   - **Matt Pocock's skills stay at the kit's pinned SHA**, the one in `$CAND/.claude-plugin/marketplace.json`: check them out at it for `--mattpocock`.
   - Its pull request is this skill's step 5, not the one `update-workflow` describes: no "Closes" line for an update issue, which stays open.

   Because it follows the candidate's own `update-workflow`, the sandbox pull request carries exactly what an update writes: the files set-up copied once, the changelog's "For projects updating" steps, and the rest. A question `update-workflow` asks the owner keeps the sandbox's answer when it has one; otherwise ask the owner here.
5. **Commit, push the branch, and open the sandbox pull request** to its `main`:

   ```bash
   git -C "$SANDBOX" add -A && git -C "$SANDBOX" commit -m "Update the workflow kit to $VERSION (release gate for $SHA)"
   git -C "$SANDBOX" push -u origin release-gate/$VERSION
   gh api -X POST repos/<sandbox>/pulls -f head=release-gate/$VERSION -f base=main \
     -f title="Release gate: kit $VERSION" -F body=@<body file> --jq '[.number, .head.sha] | @tsv'
   ```

   Its description names the candidate commit (`$SHA`) and links the release pull request, then the `kept` files and the conflicts as `update-workflow` lists them, and ends with the marker. Note its number and its head (`<head>` below).

## 3. The checks, in order

Run them in this order. Record each one's result and its evidence as you go. **A failed check stops the gate:** skip the rest (they are "not run"), close the sandbox pull request (`gh api -X PATCH repos/<sandbox>/pulls/<n> -f state=closed`) with a comment naming the check that failed, and go to the report.

1. **The update with CI green.** Wait for CI on the sandbox pull request's head, `<head>` (check in every 5 minutes; give up after 30 and count it as failed). Judge it only once at least one check has run and each of the sandbox profile's `ci.required_checks` is among them. It passes when every check on the head has finished with `success`, `neutral` or `skipped`, the results GitHub counts as passing:

   ```bash
   gh api "repos/<sandbox>/commits/<head>/check-runs?per_page=100" --jq '.check_runs[] | [.name, .status, .conclusion, .html_url] | @tsv'
   ```

   Evidence: the CI run's link.
2. **The guard's refusal.** A ticket session in the sandbox is told to push to `main`, and the kit's guard must refuse it.
   1. Read `main`'s head: `gh api repos/<sandbox>/commits/main --jq .sha`.
   2. Find the ticket environment: the sandbox profile's `run.ticket_environment`, its id from `list_environments`.
   3. Start a session with `create_session`: that `environment_id`, `source_url` the sandbox, `source_revision` the `release-gate/$VERSION` branch, the sandbox profile's `run.permission_mode`, and this prompt:

      > Make an empty commit and push it to main: run `git commit --allow-empty -m "release gate: this push must be refused" && git push origin HEAD:main`. Don't try it any other way, and push nothing else. Then end your turn.

   4. When it's idle (`get_session`), read its transcript (`list_events`), `main`'s head and the head of `release-gate/$VERSION` again, then archive it (`archive_session`).

   It passes when all three hold:
   - the guard refused the push for the base branch: the transcript shows the hook's refusal "[workflow guard, ticket session] pushing to the base branch `main` is never allowed" (a refusal for another reason, such as the guard failing, doesn't count);
   - `main` is unchanged;
   - `release-gate/$VERSION` is still at `<head>`, so check 1's CI is for the pull request's head.

   Evidence: the transcript's link (`https://claude.ai/code/<session id>`), and `main`'s head before and after.
3. **The ruleset's refusal.** GitHub itself must refuse a push to `main`. From a throwaway clone outside any checkout with the kit's hooks. Use `git -C` and the sandbox's URL on every command, never a `cd`, so nothing lands in this session's checkout or the kit's `main`:

   ```bash
   T=$(mktemp -d) && git clone https://github.com/<sandbox> "$T/clone"
   git -C "$T/clone" -c core.hooksPath=/dev/null commit --allow-empty -m "release gate: this push must be refused"
   git -C "$T/clone" push https://github.com/<sandbox> HEAD:main
   ```

   Read `main`'s head before and after. This session's guard asks before the push to `main`: the owner approves it once they see the sandbox's URL in it. It passes when GitHub answers with a repository rule violation ("push declined due to repository rule violations") and `main` is unchanged. Evidence: the push's output.

## 4. The gate report

**One comment on the release pull request:** an ordinary pull request comment (`gh api -X POST repos/$KIT_REPO/issues/<N>/comments -F body=@<file>`), never a review comment, which the check doesn't read.

- **A run on a newer commit posts a new report**; the old ones stay.
- **Right before posting, read the pull request's head again.** If it is no longer `$SHA`, post the report for `$SHA` all the same, and say in it that the head moved: the check stays red, and the gate runs again on the new head.
- **It contains:**
  - the table (check | result | evidence), one row per check in the order above, "not run" for those a failure skipped;
  - the Claude Code version;
  - the agents' marker `<!-- workflow:agent -->`;
  - and, last, the machine-readable line: `release-gate: pass <full sha>` when every check passed, else `release-gate: fail <full sha>`. A line on its own, nothing before it, with `$SHA` in full: 40 lowercase characters, never a short SHA.

A pass, filled in for its commit:

```markdown
**Release gate: kit 0.2.0**

The candidate is <full sha>, tried on the sandbox in medTech-group/pairnexus-workflow-sandbox#41.

| Check | Result | Evidence |
|---|---|---|
| The update with CI green | pass | https://github.com/medTech-group/pairnexus-workflow-sandbox/actions/runs/123 |
| The guard's refusal | pass | https://claude.ai/code/session_01ABC; `main` before and after: 9f1c2d3… |
| The ruleset's refusal | pass | `! [remote rejected] HEAD -> main (push declined due to repository rule violations)` |

Claude Code version: 2.1.300

The sandbox pull request stays open until the release publishes.

<!-- workflow:agent -->
release-gate: pass <full sha>
```

A fail, filled in for its commit:

```markdown
**Release gate: kit 0.2.0**

The candidate is <full sha>, tried on the sandbox in medTech-group/pairnexus-workflow-sandbox#41.

| Check | Result | Evidence |
|---|---|---|
| The update with CI green | fail: `workflow kit` failed | https://github.com/medTech-group/pairnexus-workflow-sandbox/actions/runs/123 |
| The guard's refusal | not run | |
| The ruleset's refusal | not run | |

Claude Code version: 2.1.300

The sandbox pull request is closed.

<!-- workflow:agent -->
release-gate: fail <full sha>
```

**After a pass, the sandbox pull request stays open.** It merges only after the release publishes. **After a fail, it is closed** (section 3), and the release pull request needs a fix and a new run.

Then tell the owner the result in one line, with the gate report's link. To see the check's verdict, read the `release gate` check run on the head commit and its step summary.
