---
name: review-panel
description: Review a diff or pull request with independent agents in parallel - Standards, Spec, Correctness (with a security review where it applies) and, for UI, API or CLI changes, an explorer that uses the change from outside. Also the planning review of a map decision's or a spec session's ADRs and glossary, or a spec's draft, before it's offered or published. Use on any branch or PR, inside build-ticket or alone.
---

# The review panel

Independent reviewers read the change fresh, each in its own context and in parallel. They report; they change no code. You verify each finding and fix the real ones.

`WF` is the kit's CLI: `python3 .claude/workflow/bin/workflow.py` (vendored), or `python3 <this skill's directory>/../../scripts/workflow.py` (plugin).

## 1. Gather the inputs, outside the repo

Make a scratch directory outside the repo, for example `/tmp/review-<ticket>-r<round>/`. Write into it:

- `commit.txt`: `git rev-parse HEAD`, the commit this round covers.
- `diff.patch`: `git diff <base>...HEAD`. The base is the profile's `project.base_branch`, as `origin/<base>` after a `git fetch`.
- `ticket.md`: the ticket's body and comments, its spec (the issue under "Parent") and the issues they link.
- `rules.md`: the project's rules, copied from each document in the profile's `project.rules` (safety rules, wording), plus `profile.md`'s sensitive-data and secrets sections.
- `previous.md`, from round 2: the earlier findings and what was done about each.

The reviewers read these files. The Correctness reviewer can't run git or reach GitHub.

## 2. Start the reviewers (one message, all at once)

**Standards and Spec.** Load Matt Pocock's `code-review` skill with the Skill tool (`code-review`, or `mattpocock-skills:code-review` as a plugin). Build its two sub-agent prompts as its own steps say, with the base above as the fixed point and `ticket.md` as the spec, so it never needs to ask. Start both with the Agent tool.

**Correctness.** The `correctness-reviewer` agent (`pairnexus-workflow:correctness-reviewer` as a plugin). Give it:
- the scratch directory's path;
- the list of changed files, to read in full in the repo;
- the round number.

For an auth, upload, payment or API change, also run the `security-review` skill on the branch.

**Explorer.** The `ui-explorer` agent, when the explorer isn't `none` (the briefing's UI explorer in a ticket session, else the profile's `ui.explorer`) and the change touches a screen, an endpoint or a command. Give it:
- the profile's `[ui]` settings;
- `ticket.md`;
- the screens, endpoints or commands the change touches;
- the scratch directory for its own files.

Tell the Correctness reviewer and the explorer to try risky commands (pushes, `gh` writes, guard experiments) only in a throwaway copy whose `origin` is a local bare repository, and to write test inputs with file tools rather than shell heredocs.

Tell the explorer, too, that a command under review that writes files (`workflow adopt`, `workflow vendor`, `workflow repair`, the set-up step that saves `workflow pr-template`'s output, anything taking `--project` or `--out`, and any other command that writes files, `workflow evidence` among them) runs only against an absolute path to a scratch project, never the session's checkout: a fresh temporary directory, or a `git clone` of the checkout into one with its `origin` removed, never a `git worktree`, which shares the session's `.git`. It gives `--project` the scratch project's absolute path on every call: left out (or empty, for `vendor`), the flag means `$CLAUDE_PROJECT_DIR` or the nearest checkout. It runs `git status --porcelain --ignored --untracked-files=all` in the session's checkout (and in the clean copy too, when it has one) before and after, and reports any difference between the two as a finding. It never tries to undo a change: the guard can refuse the undo, and you decide what to discard (section 3). Its own text says how to run a command that has no `--project`.

Give each reviewer the round number. From round 2, give each `previous.md`, so it checks the fixes and doesn't repeat itself.

## 3. After each round

1. Check each finding against the code. A reviewer can be wrong.
2. Fix every real one, with a test for each bug.
3. Record each that isn't a problem, with the reason.
4. Run `git status`: it must show nothing a reviewer made. Discard anything stray and say so. If the guard refuses the discard (a protected file), finish in a clean copy, and say so in the PR body: `git worktree add --detach <a directory outside the repo> HEAD`, commit there, and push with `git push origin HEAD:<branch>`. Do everything after it there: later fixes, the tests, `commit.txt`, the diff and the next rounds. Give the reviewers the clean copy's absolute path as the repo: the explorer runs the CLI from it, and checks both it and the session's checkout with `git status`.
5. Rerun the typecheck and the affected tests.
6. Post the round's review record (section 4).

## 4. Post the review record

Post a record on the pull request after every round, whatever it found, and after each later Correctness pass, in attended and unattended sessions alike. A record says which commit was reviewed, by whom, and whether anything was left to fix, so a merge never has to guess.

- **A round:** with the commit from `commit.txt` (the branch's head when the round ran, from `git rev-parse HEAD`), the reviewers that ran (from `standards`, `spec`, `correctness`, `security`, `explorer`), and `--clean` when the round found nothing to fix, else `--not-clean`:

  ```
  WF review-record --kind round --round <n> --commit <sha> --reviewers standards,spec,correctness --clean > /tmp/review-<ticket>-r<n>/record.md
  ```
- **A later Correctness pass:** the round it follows, the commit from its own `commit.txt` (section 5), only `correctness`, and `--clean`, or `--not-clean` when it found something to fix:

  ```
  WF review-record --kind pass --round <last round> --commit <sha> --reviewers correctness --clean > /tmp/review-<ticket>-pass<k>/record.md
  ```

Keep `record.md` only when the command exited 0. If it refuses, delete the empty `record.md`, fix what it names and run it again: never write a record by hand.

Post `record.md` as it is, as a comment on the pull request: `gh api repos/<repo>/issues/<pr>/comments -F body=@/tmp/review-<ticket>-r<n>/record.md` (the pass's path for a pass), or the GitHub MCP tools with its text. It already ends with the agents' marker; add nothing.

No pull request yet (the first rounds of `build-ticket` run before it opens)? Keep each `record.md` in its scratch directory and post them, oldest first, as soon as the pull request is open.

## 5. When to stop

Repeat on the new diff until a round finds nothing to fix, at most the briefing's review rounds in a ticket session, else the profile's `run.review_rounds`. For a light review, or when the briefing's review rounds are 1, follow the light review (section 6) instead.

- Anything still open after the last round goes to the owner in the PR body, never silently.
- Any commit after the last round gets a Correctness pass on just those commits before merging. Before it starts, `mkdir -p /tmp/review-<ticket>-pass<k>` (its scratch directory, `k` counting the passes from 1) and write `git rev-parse HEAD` to `commit.txt` there: the commit it covers, never one made after. Then post its record (section 4).

## 6. The light review

A shorter review for a small, low-risk ticket, asked for as "build #12 with a light review" (`build-ticket`, "Review it"). It keeps every reviewer but the explorer, and it never changes the merge rule (flow §4): CI green, the review record, the owner's review of kit and CI files and the rest of it all stand.

- **Round 1** runs the full panel (Standards, Spec, Correctness, and the security review where it applies) but no UI explorer. Its record:

  ```
  WF review-record --kind round --round 1 --commit <sha> --reviewers standards,spec,correctness --clean > /tmp/review-<ticket>-r1/record.md
  ```

  (`standards,spec,correctness,security` when the security review ran; `--not-clean` when it found something to fix.)
- **If round 1 isn't clean,** fix its findings as in section 3, then run Correctness-only rounds until one is clean, at most 2 more. Each is a round of its own, with its own scratch directory, `commit.txt` and `previous.md`, and posts its record as a round, never as a pass:

  ```
  WF review-record --kind round --round <n> --commit <sha> --reviewers correctness --clean > /tmp/review-<ticket>-r<n>/record.md
  ```

  (`--not-clean` when it found something to fix.) The 2 is fixed, whatever `run.review_rounds` says: with the briefing's review rounds at 1, these rounds come on top of its "at most 1".
- **Post each record** as section 4 says. A later commit after the last round still gets its Correctness pass (section 5).
- **Anything still open** after them goes to the owner in the PR body, never silently.

**In a run:** when the briefing's review rounds are 1, ticket sessions use this same shape, so one round means one full-panel round, without the explorer, in attended and unattended work alike. There the owner chose it, by giving the run one review round; it is never chosen for the person.

## 7. The findings table (for the PR body)

| # | Round | Reviewer | Finding | Outcome |
|---|---|---|---|---|
| 1 | 1 | Correctness | A not-planned blocker reads as done | Fixed in abc1234, test `test_blockers_not_planned` |
| 2 | 1 | Spec | No `Area:` on the new tickets | Not a problem: the spec makes areas optional for one-off tickets |

## 8. The planning review

Planning is reviewed before it's offered or published (flow §1 and §2): a map decision's pull request (its ADRs and glossary), a spec's draft, and a spec session's ADR or glossary pull request. Build tickets aren't. Sections 1 to 5 hold, with these differences.

**The inputs,** in a scratch directory named by the decision ticket or the item's issue (`/tmp/review-<issue>-r<n>/`; a spec has no number of its own until it's published):
- the diff as `diff.patch`, or the spec's draft as `spec.md`: the whole body exactly as it will be published, any footer or marker included;
- the owner's answers as posted, as `answers.md`: each question with the answer quoted word for word, copied from the decision ticket, the item's issue or the map's Destination item (or, for a spec with neither, the comment about to be posted), never the session's summary. Sensitive data (`profile.md`) is left out of them and marked as left out, never posted;
- the ADRs and glossary, all of them, not only the changed ones;
- the decision ticket and its map, or the item's issue, as `ticket.md`;
- the project's rules, as `rules.md`.

**The reviewers,** both every round, in one message:
- **Correctness:** the `correctness-reviewer` agent, briefed for a document: check its facts against the code, look for contradictions with other ADRs and the glossary, and apply the project's safety rules (a name or other sensitive data where it shouldn't be, a screen given to the wrong reader).
- **Spec:** a general-purpose agent with its own brief, since `code-review`'s Spec axis compares code to a ticket: read the ADRs and glossary, or the spec's draft, against `answers.md`, word for word, and report anything the owner said that is dropped, reworded into a different meaning, or stated as settled where the owner left it open, and anything recorded as the owner's that they didn't say.

No Standards reviewer and no explorer: there is no code to hold to the standards and nothing to use.

**Rounds:** both reviewers run every round, until a round is clean, up to the profile's `run.review_rounds`. Planning runs in attended sessions, never in a ticket session, so no briefing's rounds apply, and the light review doesn't either. Anything still open after the last round goes to the owner: in the pull request's body, or, for a spec, in the handover. A spec whose last round wasn't clean is fixed and published all the same, and the handover says it reads as unreviewed (`workflow ready` notes its tickets) until a clean round on its current body is posted.

**Fixes:** the session fixes wording, facts and omissions itself. A fix that would change what a decision means is put to the owner as a question first, and their answer is posted word for word like the others before the next round.

**Records:** after every round, whatever it found (section 4's rules on refusals hold):
- a decision's or a spec session's pull request gets a round record on its commit. The pull request is offered only after the review, so keep each `record.md` and post them, oldest first, once it is open (section 4):

  ```
  WF review-record --kind round --round <n> --commit <sha> --reviewers spec,correctness --clean > /tmp/review-<issue>-r<n>/record.md
  ```
- a spec gets a spec record keyed to its body, the SHA-256 of `spec.md` in place of a commit, posted on the spec issue once it is published, oldest first:

  ```
  WF review-record --kind spec --round <n> --body /tmp/review-<issue>-r<n>/spec.md --reviewers spec,correctness --clean > /tmp/review-<issue>-r<n>/record.md
  ```

  Publish the last round's `spec.md` as is (after a last round that wasn't clean, the fixed file, as **Rounds** says). Then check nothing changed on the way: read the published body back into a file and run the command on it and on the file you published, keeping neither output. The short hashes they name must match. If they don't (a footer, a tool's edit), edit the body back to the file's text, and if it changes again, say so in the handover.

(`--not-clean` when the round found something to fix.)
