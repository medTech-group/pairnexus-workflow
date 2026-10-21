---
name: release-gate
description: Run the kit's release gate on a release pull request - try its exact commit on the sandbox (an update with CI green, the guard's refusal, the ruleset's refusal) and post one report whose last line the "release gate" check reads; once the release has published, finish it (the sandbox pull request updated from the release tag, then merged). The kit's own maintainers' skill, in a cloud session on the kit's repository. Use for "run the release gate on PR #N" and "finish the release gate".
---

# The release gate

A kit release publishes the moment its `VERSION` bump merges. Before that, this skill tries the release pull request's exact commit on a real project, the sandbox, and posts one gate report on the release pull request. The "release gate" check (`.github/workflows/release-gate.yml`) reads its last line: the release pull request can't merge without a pass for its head commit.

It runs in a cloud session on the kit's repository, with the owner there to approve. It takes about 30 minutes.

The owner asks for it twice: "run the release gate on PR #N" before the release (sections 1 to 4), and "finish the release gate" once the release has published (section 5).

- **The kit's repository** (`KIT_REPO` below): `python3 .claude/workflow/bin/workflow.py version --repo`.
- **The sandbox** (`<sandbox>` below): `medTech-group/pairnexus-workflow-sandbox`. It needs a ruleset on `main` and its ticket environment (its profile's `run.ticket_environment`).
- **Values carry over by hand:** shell variables don't last from one command to the next. Note each value as you get it (`$SHA`, `$VERSION`, the `mktemp` paths, the sandbox pull request's number) and write it out in later commands.
- **Every post carries the marker** `<!-- workflow:agent -->`: at the end of each comment and pull request body, and in the gate report just before its last line, the gate line.
- `gh pr create` and `gh pr merge` use GraphQL, which a cloud session's proxy refuses: use `gh api` (REST) for pull requests.
- Never `sleep` while waiting: schedule a check-in (`send_later`, about 5 minutes) and carry on when it fires.

This skill is the kit repository's own (`.claude/skills/release-gate/`). It never ships: projects get only `skills/`.

## 1. The candidate

1. **The candidate is the pull request's exact commit.** Read the pull request's head commit, the full 40-character SHA, its repository, and `VERSION` at it:

   ```bash
   gh api repos/$KIT_REPO/pulls/<N> --jq '[.head.sha, .head.repo.full_name] | @tsv'
   gh api "repos/$KIT_REPO/contents/VERSION?ref=$SHA" --jq .content | base64 -d
   gh api "repos/$KIT_REPO/pulls/<N>/files?per_page=100" --paginate --jq '.[] | .filename, .previous_filename // empty' | grep -x VERSION
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
   gh api -X POST repos/<sandbox>/issues/<earlier PR>/comments -F body=@<comment file>
   gh api -X PATCH repos/<sandbox>/pulls/<earlier PR> -f state=closed
   ```

   `<earlier PR>` is each number the first command prints.

   Then, whenever `release-gate/$VERSION` exists on the sandbox (an earlier run's, its pull request open, closed or never opened), delete it, so the new branch's push isn't refused: `gh api -X DELETE repos/<sandbox>/git/refs/heads/release-gate/$VERSION`.
3. **Branch from the sandbox's `main`:** `git -C "$SANDBOX" checkout -b release-gate/$VERSION origin/main`.
4. **Update the sandbox to the candidate through `update-workflow`:** follow the candidate's own `$CAND/skills/update-workflow/SKILL.md`, in the sandbox clone, with `KIT` as `$CAND` (so its changelog, templates and pinned SHA are the candidate's, never this session's checkout) and `WF` as `python3 $CAND/scripts/workflow.py`, from step 1 (where it stands) on. Four differences:
   - **Every one of its commands runs on the sandbox:** prefix each with `CLAUDE_PROJECT_DIR="$SANDBOX"` and give `--project "$SANDBOX"` where the command takes it (`vendor verify`, `vendor resolve`); every file it names (`CLAUDE.md`, `.github/…`, the profile) is the one under `$SANDBOX`. Without them, a command finds this session's checkout, the kit's own, and reports on it. Step 1's check is `CLAUDE_PROJECT_DIR="$SANDBOX" python3 "$SANDBOX/.claude/workflow/bin/workflow.py" vendor verify --project "$SANDBOX"`.
   - **The update is `vendor update --kit` pointing at the candidate's checkout:**

     ```bash
     WF vendor update --kit "$CAND" --project "$SANDBOX" --mattpocock <checkout> --strict-pin
     ```

   - **Matt Pocock's skills stay at the kit's pinned SHA**, the one in `$CAND/.claude-plugin/marketplace.json`: check them out at it for `--mattpocock`.
   - **Its pull request is this skill's step 5,** not the one `update-workflow` describes: no "Closes" line for an update issue, which stays open.

   Because it follows the candidate's own `update-workflow`, the sandbox pull request carries exactly what an update writes: the files set-up copied once, the changelog's "For projects updating" steps, and the rest. A question `update-workflow` asks the owner keeps the sandbox's answer when it has one; otherwise ask the owner here.
5. **Commit, push the branch, and open the sandbox pull request** to its `main`:

   ```bash
   git -C "$SANDBOX" add -A && git -C "$SANDBOX" commit -m "Update the workflow kit to $VERSION (release gate for $SHA)"
   git -C "$SANDBOX" push -u origin release-gate/$VERSION
   gh api -X POST repos/<sandbox>/pulls -f head=release-gate/$VERSION -f base=main \
     -f title="Release gate: kit $VERSION" -F body=@<body file> --jq '[.number, .head.sha] | @tsv'
   ```

   Its description names the candidate commit (`$SHA`) and links the release pull request, then the `kept` files and the conflicts as `update-workflow` lists them, and ends with the marker. Note its number (`<sandbox PR>` below) and its head (`<head>`).

## 3. The checks, in order

Run them in this order. Record each one's result and its evidence as you go. **A failed check stops the gate:** skip the rest (they are "not run"), close the sandbox pull request with a comment naming the check that failed (`gh api -X POST repos/<sandbox>/issues/<sandbox PR>/comments -F body=@<comment file>`, then `gh api -X PATCH repos/<sandbox>/pulls/<sandbox PR> -f state=closed`), and go to the report.

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

   Read `main`'s head before and after. This session's guard asks before the push to `main`: the owner approves it after checking that the URL in it is the sandbox's. It passes when GitHub answers with a repository rule violation ("push declined due to repository rule violations") and `main` is unchanged. Evidence: the push's output.

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

**After a pass, the sandbox pull request stays open.** It merges only after the release publishes, when the gate is finished (section 5). **After a fail, it is closed** (section 3), and the release pull request needs a fix and a new run.

Then tell the owner the result in one line, with the gate report's link. To see the check's verdict, read the `release gate` check run on the head commit and its step summary.

## 5. Finishing the gate

Asked "finish the release gate" once the release has published, for the version or for the release pull request #N. Given neither, ask the owner which version. A pass left the sandbox pull request open (section 4). Finishing updates its branch from the release tag, so the sandbox records the released version rather than the candidate's commit. Then it merges it.

- It touches the sandbox's `main` only through that pull request's merge.
- It never touches `docs/spike.md`, which changes only when a row's status does.
- Its values carry over by hand, as the gate's do: `$VERSION`, `$SANDBOX`, `$REL`, `<sandbox PR>`, `<candidate>`, `<head>`.
- Finish a version before running the gate for the next one: a gate run closes every open `release-gate/` sandbox pull request (section 2, step 2), an unfinished pass among them.

Run these steps in order. A step that stops the finish says why to the owner. A stop never merges and never touches the sandbox's `main`; before step 5 it pushes nothing.

1. **The release exists.** Asked for the release pull request #N, read its merge commit and `VERSION` at it. A pull request that hasn't merged has no release: stop, saying so.

   ```bash
   gh api repos/$KIT_REPO/pulls/<N> --jq '[.merged, .merge_commit_sha] | @tsv'
   gh api "repos/$KIT_REPO/contents/VERSION?ref=<merge sha>" --jq .content | base64 -d
   ```

   Stop, saying why, when `VERSION` isn't three numbers (`0.2.0`), as in section 1. Then read the release `v$VERSION`, a GitHub release, not merely a tag:

   ```bash
   gh api repos/$KIT_REPO/releases/tags/v$VERSION --jq .html_url
   ```

   If the release isn't there (a 404), say the release `v$VERSION` hasn't published yet and stop: finish once it has.
2. **The sandbox pull request.** Add the sandbox to the session with push access (`add_repo`, `access: "push"`). Find the gate's pull request from its branch, `release-gate/$VERSION`, newest first:

   ```bash
   gh api "repos/<sandbox>/pulls?state=all&head=medTech-group:release-gate/$VERSION&per_page=100" --jq '.[] | [.number, .state, .merged_at, .head.sha] | @tsv'
   ```

   Take the first line. Stop, saying why, when:
   - there's none: no gate opened one for `$VERSION`, so there is nothing to finish;
   - it is closed and merged (`merged_at` set): the gate is finished already;
   - it is closed and not merged: a failed gate closed it (section 3), or a later version's gate run did (its closing comment names the newer commit). Say which, from its last comment. The sandbox stays as it is.

   Note its number (`<sandbox PR>`) and its current head. Asked for the release pull request #N, its gate report's second line names the sandbox pull request too ("tried on the sandbox in …#<n>"): if the two differ, ask the owner which one.
3. **The update from the tag.** As the candidate was applied (section 2, step 4), with the release tag's checkout as the kit. Clone the sandbox's branch and the tag outside the working tree:

   ```bash
   SANDBOX=$(mktemp -d)/sandbox && git clone --branch release-gate/$VERSION https://github.com/<sandbox> "$SANDBOX"
   REL=$(mktemp -d)/release && git clone https://github.com/$KIT_REPO "$REL"
   git -C "$REL" checkout --detach "v$VERSION"
   git -C "$SANDBOX" show HEAD:.claude/workflow/lock.json | jq -r '[.kit_sha, .mattpocock_sha] | @tsv'
   ```

   `git -C "$SANDBOX" rev-parse HEAD` must print that current head; else someone pushed to the branch since step 2: stop, saying so. The lock's `kit_sha` is the candidate commit the gate tried (`<candidate>`): keep it for step 5. When it is already the tag's commit (`git -C "$REL" rev-parse HEAD`), an earlier finish pushed and then stopped: take the candidate from the pull request's description instead.

   Matt Pocock's skills follow the branch's lock, as `update-workflow` does. When it records a `mattpocock_sha`, check them out at the release's pinned SHA, the one in `$REL/.claude-plugin/marketplace.json`, and run:

   ```bash
   CLAUDE_PROJECT_DIR="$SANDBOX" python3 "$REL/scripts/workflow.py" vendor update --kit "$REL" --project "$SANDBOX" --mattpocock <checkout> --strict-pin
   ```

   When it records none, run the same without `--mattpocock <checkout> --strict-pin`.

   Only `vendor update`, not the rest of `update-workflow`: the branch already holds what the candidate's `update-workflow` wrote, and the release is the candidate merged. An update that refuses stops the finish here. A conflict it writes is a changed file, which step 4 stops on.
4. **Files unchanged apart from the lock's source and version.** The update may change only the lock's `kit_sha` (its source, now the tag's commit) and `kit_version`. Check both:

   ```bash
   git -C "$SANDBOX" status --porcelain
   diff <(git -C "$SANDBOX" show HEAD:.claude/workflow/lock.json | jq -S 'del(.kit_sha, .kit_version)') \
        <(jq -S 'del(.kit_sha, .kit_version)' "$SANDBOX/.claude/workflow/lock.json")
   ```

   The first must list `.claude/workflow/lock.json` alone, or nothing. The second must print nothing.

   Otherwise **stop loudly**, and name every file that differs: each file the first lists other than the lock, and the lock when the second prints anything. Name them to the owner, and in a comment on the sandbox pull request (`gh api -X POST repos/<sandbox>/issues/<sandbox PR>/comments -F body=@<comment file>`). Push nothing, leave the sandbox pull request open, and never touch the sandbox's `main`. The release differs from what the gate tried, and what follows is the owner's call.
5. **The description names the release.** Commit and push the branch (a plain push: it builds on the pull request's head). Skip both when step 4's first command listed nothing: `<head>` is then step 2's current head.

   ```bash
   git -C "$SANDBOX" add -A && git -C "$SANDBOX" commit -m "Update the workflow kit to release v$VERSION"
   git -C "$SANDBOX" push origin release-gate/$VERSION
   ```

   Then `git -C "$SANDBOX" rev-parse HEAD` prints `<head>`, the pushed commit. Then rewrite the sandbox pull request's title and description:

   ```bash
   gh api repos/<sandbox>/pulls/<sandbox PR> --jq .body
   gh api -X PATCH repos/<sandbox>/pulls/<sandbox PR> -f title="Kit release v$VERSION" -F body=@<body file>
   ```

   The new description opens by saying it holds release `v$VERSION`, with the release's link, and names the candidate commit the gate passed (`<candidate>`). Below that, it keeps the earlier description's `kept` files and conflicts. It ends with the marker.

   Then read the pull request's head until it is `<head>`: GitHub updates it shortly after a push. If it isn't, check again at a check-in; after 10 minutes, stop, saying the pull request's head isn't `<head>`.

   ```bash
   gh api repos/<sandbox>/pulls/<sandbox PR> --jq .head.sha
   ```

6. **CI green.** Wait for CI on `<head>` and judge it as section 3's first check. If it fails, or isn't green after 30 minutes, stop: say what failed, with the CI run's link, and leave the sandbox pull request open.
7. **A merge commit.** Merge it with a merge commit, pinned to `<head>`:

   ```bash
   gh api -X PUT repos/<sandbox>/pulls/<sandbox PR>/merge -f merge_method=merge -f sha=<head>
   ```

   If the sandbox's ruleset refuses it, tell the owner why and leave it: never bypass the ruleset.

Then tell the owner in one line that the sandbox's `main` holds release `v$VERSION`, with the sandbox pull request's link.
