---
name: review-panel
description: Review a diff or pull request with independent agents in parallel - Standards, Spec, Correctness (with a security review where it applies) and, for UI, API or CLI changes, an explorer that uses the change from outside. Use on any branch or PR, inside build-ticket or alone.
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

Give each reviewer the round number. From round 2, give each `previous.md`, so it checks the fixes and doesn't repeat itself.

## 3. After each round

1. Check each finding against the code. A reviewer can be wrong.
2. Fix every real one, with a test for each bug.
3. Record each that isn't a problem, with the reason.
4. Run `git status`: it must show nothing a reviewer made. Discard anything stray and say so.
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
