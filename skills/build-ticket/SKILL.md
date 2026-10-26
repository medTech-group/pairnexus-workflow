---
name: build-ticket
description: Build one ready ticket from claim to merge - tdd at the spec's seams, the review panel in rounds until clean, a pull request with its findings table, CI green, the local suite's evidence, and the merge under the merge rule. Use for "implement #N", "build #N", "build #N with a light review" ("quick build #N"), "build #N with the full panel", or a ticket session's briefing.
---

# Build a ticket

One ticket, start to finish. The flow's sections 3 to 5 are the rules; this skill is how to follow them. The flow is `.claude/workflow/flow.md` (vendored) or `docs/flow.md` beside `skills/` (plugin).

`WF` is the kit's CLI: `python3 .claude/workflow/bin/workflow.py` (vendored), or `python3 <this skill's directory>/../../scripts/workflow.py` (plugin).

**Every post carries the marker.** Everything you post on GitHub (comments, issues, the PR's body, reviews, edits of a body) goes out under the owner's account. End each body with this line, so the owner's own words can be told apart from agents':

```
<!-- workflow:agent -->
```

In a ticket session the guard refuses a post without it. Labels, assignees, state changes and merges need none.

## 0. Read first

- **The briefing,** if this is a ticket session. It says:
  - what runs alongside you, and what to stay out of;
  - which notes to read;
  - the owner's decisions since the run began;
  - the merge mode, and any waived check;
  - the wake routine's trigger id;
  - on its last line, `Briefing <hash>`.

  **Check your copy first.** With the Write tool, write the briefing (your first message, verbatim, from its first line to its `Briefing <hash>` line) to `.workflow/briefing.md`, which git ignores. Then run `WF briefing verify --file .workflow/briefing.md`. It prints one line: `Briefing <hash> intact`, `Briefing changed: expected <a>, got <b>`, or `no Briefing line`.

  **Your first write** is a comment on the ticket saying you've started, quoting that output line exactly ("Started. Briefing 3f2a9c01b7de intact"), so the conductor sees whether the briefing arrived intact. Carry on either way: if it didn't, the conductor stops this session and starts another.
- **The ticket,** its spec (the issue under "Parent") and every issue they link. Use `gh api` or the GitHub MCP tools.
- **The profile** (`.claude/workflow/profile.toml`, `profile.md`) and the rules it points to.
- **Its blockers.** If any isn't closed as completed, say so and stop: it isn't ready.

## 1. Claim it

Skip this if the briefing says the conductor has claimed it. Otherwise, before any other write:
- add the `workflow:in-progress` label, keeping the ticket's other labels (`issue_write` replaces the whole list);
- assign it to yourself in attended work, or to the owner in a run.

## 2. Build it

- **Branch:** work on the session's branch. A ticket session's is the profile's `run.ticket_branch` with the ticket's number. In an attended session that builds more than one thing, each ticket gets its own branch, fresh from `origin/<base>` and not named like `run.ticket_branch` (that would make it a ticket session), so no pull request carries another's work.
- **Tests first:** use `tdd` (Matt Pocock's) at the spec's seams. Write a failing test for each acceptance criterion, then the code. The seams the spec names are already agreed with the owner: they count as confirmed, so in a ticket session `tdd`'s "confirm with the user" step is satisfied and you never stop to ask. A seam the spec doesn't name is a decision the ticket leaves open (below).
- **Commands:** the profile's `commands.typecheck` and `commands.test_file` as you go. Run the full suite once the ticket is built.
- **Tests that don't fail by chance:** compute dates and times at the point of use, never at import. Never assert that a random id lacks some digit string.
- **Commit and push as you go,** with clear messages: push your branch after each commit, so the work is never only in this container and the conductor sees progress.
- **Stay within the flow's never-list** (§5). The guard hook stops most breaches: if it refuses something, the refusal is the answer, not a puzzle to get around.
- **Checks you can't run here:** for a check that needs a real device, account or service, build against the spec's fakes. Add its by-hand step as a checkbox under this ticket on the run's by-hand issue, or on the ticket in attended work. Never mark it done.
- **Decisions the ticket leaves open:** follow the briefing. By default, take the choice most consistent with the spec, ADRs and the project's rules, and record it for the PR body.

## 3. Review it

Follow the `review-panel` skill on the diff against the base branch:
- rounds until one comes back clean, at most the briefing's review rounds in a ticket session, else the profile's `run.review_rounds`;
- verify each finding, then fix it with a test or answer it with a reason;
- rerun the typecheck and the affected tests after each round;
- after the last round, any further commit gets a short Correctness pass, at most the briefing's pass cap, else the profile's `run.review_passes` (`review-panel` §5); past it, the owner decides (`passes_used_up`: in a run, `needs-human`, step 6.3).

**A light review,** when the person asks for one: "build #12 with a light review", or "quick build #12". "Light review" is its name; "quick build" is only understood. It is not the guided start's "quick ticket", which writes a build ticket on the spot. Follow `review-panel`'s light review (section 6), which gives its shape. A ticket session uses that shape when its briefing's review rounds are 1 (unless the ticket gets the small review, below), the Correctness-only rounds coming on top of the briefing's "at most 1". A light review is never chosen for the person, in attended or unattended work, and it never changes the merge rule.

**The small review,** on a ticket marked `Review: small` (a line in its body, written at planning; flow §2). In attended work it is always allowed; in a ticket session, when the briefing's "Small review" line says on (off: build the ticket like any other). A ticket marked small gets it in a 1-round run too; unmarked tickets keep the light review there. A build the person chose ("build #12 with a light review", "build #12 with the full panel") isn't the small review: the person's choice wins over the mark.
- Before reviewing, measure the diff: `WF review-record --measure --commit <sha>`, with `<sha>` your branch's head (in a run, with the briefing's `--small-max-lines` and `--small-max-files`, as its "Small review" line gives them; else the profile's `run.small_max_lines` and `run.small_max_files`). It prints whether the change is within the small threshold. If it can't measure (it exits non-zero), run the full panel. Measure again before opening the pull request, after the fixes.
- Within the threshold, follow `review-panel`'s small review (section 7): one round of Correctness, with the security review and the explorer where they apply, then Correctness passes under the pass cap, with no further rounds.
- Past it, run the full panel (the light review in a 1-round run), and the PR body says the diff overruled the mark. So does a later commit that takes it past the threshold, which `WF merge-check` reports as `past_small_threshold`: then run the one full-panel round it asks for, with the next round number and allowed past the round limit, and if it isn't clean, a Correctness pass (`review-panel` §7).

## 4. Open the pull request

To the base branch. Its body opens with **In plain words**, above everything else, so someone new to building can judge the change without reading code. Use exactly these headings, each on its own line with its text below it (the text here is only an example):

```markdown
## In plain words

**What changes for you**
The notes list now shows the newest note first.

**How to try it**
Open the notes list and add a note: it appears at the top.

**What could go wrong**
Easy to undo. Only the notes list's order changes.
```

- `**What changes for you**`: one to three sentences about what a user notices, not the code.
- `**How to try it**`: the first of these that fits:
  - the try-it link and two or three things to click, when a link exists;
  - else, when the project has preview links, where the link will appear ("A try-it link will appear as a comment on this pull request in a few minutes.");
  - else what to check another way (as in the example), or "Nothing to try: this change is behind the scenes".

  With the profile's `[previews] on = true`, the pull request opens with the second case (its link isn't built yet), and step 5 fills in the first once the preview is `built`. With previews off, use the last case: what to check another way, or "Nothing to try".
- `**What could go wrong**`: whether the change is easy or hard to undo, and what it could affect.

The section is the same for everyone, never worded by experience, so a pull request reads alike whoever wrote it and whoever reads it. Examples are everyday ones (a notes app, a shop, a booking page). If the `pr` skill is loaded too, its sections go below; the body still opens with `## In plain words`.

Below it, unchanged:
- `Closes #<n>`;
- what was built: routes, screens, tables, settings;
- how it was tested: the seams, the suites, what the explorer exercised;
- after a light review (asked for, or a briefing's review rounds at 1), the line "Light review: one round, no UI explorer", adding "plus N Correctness rounds for the fixes" when there were some, above the findings table (not on a ticket that got the small review);
- after the small review, the line "Small review: one round, Correctness", adding ", security" and ", explorer" when they ran, above the findings table. On a ticket marked small whose diff was past the threshold, say instead that the diff overruled the mark ("Marked `Review: small`, but the diff overruled the mark: 85 lines in 3 files outside tests, so the full panel ran"). With none of these lines, the full panel ran;
- the findings table: round, reviewer, finding, and what happened (fixed in which commit, or not a problem and why);
- the decisions taken, under "Decisions for the owner";
- the by-hand checks added.

Then post the review records so far: each round's and each Correctness pass's `record.md`, kept in its scratch directory (`review-panel`, "Post the review record"), oldest first. Later rounds and Correctness passes post theirs as they run. The records sit alongside the findings table; they don't replace it.

Lasting knowledge for later work (how a new module is meant to be used, a pitfall) goes in the repo's own docs, in this PR, before it merges.

Then subscribe to its activity. Schedule a check-in about every `run.check_in_minutes` (`send_later` in cloud sessions; `/loop` or a cron task locally), and end the turn with `WORKFLOW-STATUS: waiting`.

## 5. Get it green

- **The try-it link,** only with the profile's `[previews] on = true`: at each check-in until the pull request merges (CI can finish before the link is built), read the preview for the head: `WF preview --fetch <PR> --json` (or, without `gh`, `--comments F --checks F --sha <head>` with the pull request's issue comments and its head commit's check runs). Then edit the pull request's body (only its "How to try it", keeping the rest and the marker):
  - `built`: the link (`url`) and two or three things to try in it, as step 4's first case;
  - `failed`: say it plainly ("The try-it link didn't build for `<short sha>`."), with the fix: open the build's log from the check's details, find its message in "When a build fails" in `docs/previews.md` (`.claude/workflow/docs/previews.md` vendored, the kit's own as a plugin), and fix it when it's in this pull request's code (then push). When the fix is a Cloudflare setting (`docs/previews.md`'s steps 3 to 5) or the log can't be opened here, no push of yours fixes it: comment on the pull request and on the tracking issue with the step the owner redoes, then stop as "Still red after three fix attempts" says (`needs-human`);
  - `building` or `none`: leave it as it is, and read it again at the next check-in.
- **A required check is red:** find the cause (use `diagnosing-bugs` when it's unclear) and push a fix. "Flake" isn't a cause: a test that fails by chance gets fixed so it can't.
- **The base branch moved:** if auto-merge is armed, disarm it first (`disable_pr_auto_merge`, or `gh pr merge <n> --disable-auto`): GitHub would merge the new head, which `WF merge-check` hasn't said `ready` for. Then `git fetch origin <base> && git merge origin/<base>`, resolve any conflicts keeping both sides' intent, rerun the tests, and push. Never rebase or force-push.
- **A required check that never starts** because its workflow is path-filtered (the profile's `ci.path_filtered`): `WF merge-check` counts it as not started, so it never says `ready`, and in `auto-merge` mode GitHub would wait for it forever. Act on this only once every other required check has finished and the evidence is posted: `WF merge-check`'s only reason left is `checks_pending`, for checks that are all in `ci.path_filtered` and `missing` in its `checks[]`. Then comment that the PR needs the owner to merge and end `waiting`. Until then, step 6.3's `not_yet` applies.
- **A check the charter waives:** it counts as passed only when its log shows a killed marker (the profile's `ci.killed_markers`) rather than a test failure, and only with the evidence below.
- **Still red after three fix attempts:**
  1. label the ticket `needs-human`, and remove `workflow:in-progress` and `ready-for-agent` (keep its other labels);
  2. comment on it and on the tracking issue with exactly what fails and why;
  3. wake the conductor (step 6.7);
  4. end with `WORKFLOW-STATUS: needs-human`.

## 6. Post the evidence and merge

1. **Push everything,** and make sure the branch is level with the base branch.
2. **Run the evidence:** `WF evidence --base-ref origin/<base>`, after a `git fetch`.
   - It runs the suites in shards, resumes after a container restart, refuses a dirty tree, and runs the base branch's suites in a temporary worktree to compare counts.
   - With the profile's `commands.select_suites`, it runs only the suites the branch's changed files need, and says which it left out, or why it ran them all.
   - **When a required check was waived,** add `--all`: there the report is the proof, and `WF merge-check` counts only the full suite's.
   - Post its report on the PR.
3. **Run `WF merge-check`.** In attended work, skip this and step 4: say the PR is ready and leave it, since the owner merges. Point them at the `merge-check` skill ("is #N ready to merge?"), or `WF merge-check --fetch <n>`. In a run, right before each of these (merging, arming auto-merge, saying it's ready), run `WF merge-check --fetch <PR> --json --charter .workflow/tracking.md --review-rounds <N>`, with `<N>` the briefing's review rounds and the body of the tracking issue the briefing names saved there (`gh api repos/<repo>/issues/<tracking> --jq .body > .workflow/tracking.md`; git ignores `.workflow/`, so the evidence still sees a clean tree). Add `--review-passes <P> --small-max-lines <L> --small-max-files <F>`, with `<P>` the briefing's pass cap and `<L>` and `<F>` the briefing's small threshold (its lines and files), else the profile's `run.review_passes`, `run.small_max_lines` and `run.small_max_files`. It is the same command a person's `merge-check` runs, so a run and a person never disagree on "ready".
   - **The try-it link:** with the profile's `[previews] on = true`, read it first, each time: `WF preview --fetch <PR> --json > .workflow/preview.json`, and add `--preview .workflow/preview.json` (without `gh`, the reader takes files, as step 5 says). A reader that fails leaves the file empty, and the command says it couldn't read the preview: `not_yet`. With previews off, run no reader and pass no `--preview`: the note about the missing try-it link never blocks.
   - For a check the charter waives, add `--check-logs .workflow/check-logs` with its log in that directory, named by its check run's id on the head (a `waiver_not_taken` note names the file it wants).
   - Where `gh` can't read an input, a "couldn't read" reason names it: give it as a file (`--pr F`, `--checks F`, …) and run it again. Leave out `--asker`: it changes only the wording, never the decision.
   - It always exits 0, so read its JSON's `decision`. **`ready` is the only yes**:
     - `not_yet`: never merge or arm auto-merge, and if auto-merge is armed, disarm it (`disable_pr_auto_merge`, or `gh pr merge <n> --disable-auto`). Act on each of its `reasons[]` by its `action` and `fix`: a red check (§5), an open review thread, a review that wasn't clean (`review_not_clean`: fix the findings; its `next` says what follows: `round` is another round, `pass` is a Correctness pass on the head, since that was the last allowed round), a stale review (`review_stale`: a Correctness pass on the new commits), the pass cap reached (`passes_used_up`, `next: owner`: no further pass; it means `needs-human`: put the open findings in the PR body, then stop as §5's "Still red after three fix attempts" steps 1 to 4 say, with the cap as the reason), a branch behind the base (update it), a try-it link that didn't build (`preview_failed`: step 5's `failed`) or is still building (`preview_building`: wait), then run it again at the next check-in. A path-filtered check that never started is §5's.
     - `owner_review`: the change touches a protected path (the JSON's `files`). Never merge it or arm auto-merge: comment on the PR and on the tracking issue that the owner reviews and merges it ("#<n> changes a protected path (<files>): yours to review and merge"), and end with `WORKFLOW-STATUS: waiting`.
     - `ready`: merge by the briefing's mode (step 4), pinned to the head it checked (the JSON's `head`). With a try-it link (`preview.url`), first make sure "How to try it" gives it, as step 5 says: an edit of the body changes no commit, so the answer still holds.
4. **Merge** on `ready`. What you do depends on the briefing's mode:

   | Mode | What you do |
   |---|---|
   | `auto-merge` | First post your notes for the next tickets (step 6.5) on the tracking issue, then arm auto-merge with a merge commit, pinned to its `head`: `gh pr merge <n> --auto --merge --match-head-commit <sha>` (`enable_pr_auto_merge` can't pin the head: use it only when `gh` can't, then read the PR's head back and disarm if it isn't `<sha>`). Stay with it until GitHub has merged it. Before any push of yours while it is armed (a fix, the base merged in, an update of the branch), disarm it (`disable_pr_auto_merge`, or `gh pr merge <n> --disable-auto`). At each check-in, run step 3 again and act on it: on `not_yet`, as step 3 says (behind the base: disarm, update the branch with `gh api -X PUT repos/<repo>/pulls/<n>/update-branch`, and run it again next time); on `ready` with auto-merge not armed (whoever disarmed it), arm it again, pinned to the new `head`. End each such turn `waiting`. **If GitHub refuses to arm auto-merge because the PR is already mergeable** (clean: "Pull request is in clean status"), run the same `WF merge-check` again at that moment; on `ready`, merge it yourself with a merge commit pinned to its `head` (`gh pr merge <n> --merge --match-head-commit <sha>`, `gh api -X PUT repos/<repo>/pulls/<n>/merge -f merge_method=merge -f sha=<sha>`, or `merge_pull_request` with `merge_method: merge` and `expectedHeadSha`), and on anything else act on it as step 3 says |
   | `session` | Merge it yourself with a merge commit pinned to its `head`: `gh pr merge <n> --merge --match-head-commit <sha>`, `gh api -X PUT repos/<repo>/pulls/<n>/merge -f merge_method=merge -f sha=<sha>`, or `merge_pull_request` with `merge_method: merge` and `expectedHeadSha` |
   | `owner` | Say it's ready, and leave it |

   If your permission settings refuse the merge, don't work around it. Comment that it's green and ready, and end with `WORKFLOW-STATUS: waiting`.

   In a ticket session the guard lets you merge or arm only your own pull request: the pin must be your checkout's head (`git rev-parse HEAD` on your ticket branch), so after the branch was updated on GitHub (`update-branch`), `git pull` before you merge or arm. For `enable_pr_auto_merge`, the guard reads the pull request's head back instead.
5. **Once it has merged,** tell the tracking issue: "#<n> merged in #<PR>", then notes for the next tickets. Tag each note with its area and the tickets it's for ("For #201, area readings: …"): what you added that later tickets build on, decisions to know, and pitfalls.
6. **The claim label.** Whenever your ticket ends (merged, `needs-human`, or stopped), always remove `workflow:in-progress`; on `needs-human` also remove `ready-for-agent`. Keep the ticket's other labels. The conductor removes leftovers at its next check-in, but don't leave it to.
7. **Wake the conductor.** When the ticket ends, call `fire_trigger` with the briefing's wake routine id and exactly one of these lines: "#<n> merged in #<PR>", "#<n> needs-human" or "#<n> stopped". The conductor then checks in at once instead of at its next scheduled time. Skip this when the briefing's wake routine says `none`, or in attended work.
   - `fire_trigger` is a deferred tool (in a cloud session, `mcp__claude-code-remote__fire_trigger`; the server's part of the name can differ): load it first with ToolSearch, searching for `fire_trigger` rather than selecting an exact name.
   - If it isn't available, or the call errors, say so in the ticket's final note ("Couldn't wake the conductor: <why>") and carry on: try it once, never retry it in a loop. The conductor sees the ending at its next check-in anyway, so the wake never holds up the ticket or your `WORKFLOW-STATUS` line.

## 7. End each turn

End every turn with a status line. The checklist gate checks it in ticket sessions.

```
WORKFLOW-STATUS: done | waiting | needs-human | stopped
```

Use `waiting` when CI is running and a check-in is scheduled. With `done`, include the checklist below, each line marked `[x]`, or left `[ ]` with its reason in words ("because …", "not needed", "n/a", "skipped because …", or after a spaced dash: "- [ ] Docs — none changed"). The gate refuses an unchecked line without one.

- [ ] Blockers closed and the spec read
- [ ] Every acceptance criterion met, each with its test
- [ ] Typecheck and the full suite pass; evidence posted on the PR
- [ ] Review panel run in rounds until clean (or the limit, the rest raised); late commits had a Correctness pass
- [ ] Every finding fixed or answered with its reason
- [ ] PR opened with the findings table and decisions; by-hand checks filed
- [ ] Merged under the merge rule (or left for the owner), notes for the next tickets posted; the claim label removed and the conductor woken (in a run)
