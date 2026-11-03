---
name: build-ticket
description: Build one ready ticket from claim to merge - tdd at the spec's seams, the review panel in rounds until clean, a pull request with its findings table, CI green, the local suite's evidence, and the merge under the merge rule. Use for "implement #N", "build #N", "build #N with a light review" ("quick build #N"), "build #N with the full panel", or a ticket session's briefing. Never in a conductor session, which hands the ticket to a ticket session instead.
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

**Never in a conductor session.** With `WORKFLOW_ROLE=conductor`, stop here, before the claim or any other write: the conductor never builds a ticket. Follow the `conductor` skill's "A ticket named in chat" with it instead.

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
- verify each finding, then fix it with a test or answer it with a reason (under the rule, a finding marked a ticket to fix it is filed instead, except a security problem the change adds: "Filing tickets to fix findings, and split tickets", below);
- rerun the typecheck and the affected tests after each round;
- after the last round, any further commit gets a short Correctness pass, at most the briefing's pass cap, else the profile's `run.review_passes` (`review-panel` §5); past it, the owner decides (`passes_used_up`: in a run, `needs-human`, step 6.3). A pass cap of `until-clean` (#402) is none: fix each pass's findings and run another until one is clean, keeping the PR body's findings table current, since the run's end time can come first; `merge-check` never says `passes_used_up`, and the flag is `--review-passes until-clean`. The exception is a merge of the base that leaves the pull request's own changes identical, which needs CI only: after pushing a merge of the base, run step 6.3's `WF merge-check` (with `--fetch <PR>` and the briefing's flags) and run a pass only when it asks for one. In attended work, where the merge is the owner's, run `WF merge-check --fetch <PR> --json` after pushing a merge of the base, for its review reasons only.

**A light review,** when the person asks for one: "build #12 with a light review", or "quick build #12". "Light review" is its name; "quick build" is only understood. It is not the guided start's "quick ticket", which writes a build ticket on the spot. Follow `review-panel`'s light review (section 6), which gives its shape. A ticket session uses that shape when its briefing's review rounds are 1 (unless the ticket gets the small review, below), the Correctness-only rounds coming on top of the briefing's "at most 1". A light review is never chosen for the person, in attended or unattended work, and it never changes the merge rule.

**The small review,** on a ticket marked `Review: small` (a line in its body, written at planning; flow §2). In attended work it is always allowed; in a ticket session, when the briefing's "Small review" line says on (off: build the ticket like any other). A ticket marked small gets it in a 1-round run too; unmarked tickets keep the light review there. A build the person chose ("build #12 with a light review", "build #12 with the full panel") isn't the small review: the person's choice wins over the mark.
- Before reviewing, measure the diff: `WF review-record --measure --commit <sha>`, with `<sha>` your branch's head (in a run, with the briefing's `--small-max-lines` and `--small-max-files`, as its "Small review" line gives them; else the profile's `run.small_max_lines` and `run.small_max_files`). It prints whether the change is within the small threshold. If it can't measure (it exits non-zero), run the full panel. Measure again before opening the pull request, after the fixes.
- Within the threshold, follow `review-panel`'s small review (section 7): one round of Correctness, with the security review and the explorer where they apply, then Correctness passes under the pass cap, with no further rounds.
- Past it, run the full panel (the light review in a 1-round run), and the PR body says the diff overruled the mark. So does a later commit that takes it past the threshold, which `WF merge-check` reports as `past_small_threshold`: then run the one full-panel round it asks for, with the next round number and allowed past the round limit, and if it isn't clean, a Correctness pass (`review-panel` §7).

### Filing tickets to fix findings, and split tickets

Under the rule (`review-panel` §10), you file three kinds of ticket, so nothing piles up as `needs-triage`:
- **late:** a finding marked a ticket to fix it about this pull request's own lines, or about lines already reviewed (§10's "Lines already reviewed");
- **old:** any other finding marked a ticket to fix it: code the change neither touches nor reaches, or a written rule broken outside the change's own lines;
- **split:** a part that `WF merge-check` says to split out (`mechanism_repeats` with `next: split`).

**This ticket's own fix tickets** are the open issues whose machine line (below) says `from=` this ticket, posted by the account you post as (`gh api user --jq .login`), since only your own filing counts; those saying `kind=split` are its own split tickets. List every open issue with its author and its machine line, if it has one (the last, since a body may quote another above its own), rather than searching, since GitHub's search can miss an issue filed a minute ago:

```
gh api 'repos/<repo>/issues?state=open&per_page=100' --paginate --jq '.[] | select(.pull_request == null) | "#\(.number) \(.user.login) \([(.body // "") | scan("<!-- workflow:fix-ticket from=[0-9]+ kind=(?:old|late|split) -->")] | last // "-") \(.title)"'
```

**When.** An old or late one: after each review, once its findings file is written and before its record, so the record names it: put the issue's number in the finding's entry as `issue`. A finding you doubt is filed too, as the reviewer marked it: your doubt goes in the findings table, never in the ticket. A split one: as soon as `WF merge-check` says to split, before a fresh fixer takes the part out of the pull request, so a restart never loses the ticket; then add it to the pull request body's **Split out** (§4) at once. The next review's findings file gives a `split` outcome for each of this ticket's own split tickets that no record names yet, its `mechanism` copied from the ticket's `Part:` line, so a session restarted after the split still gives it, adds it to **Split out** if the body doesn't name it yet, and lists its moved criteria in `previous.md`.

**Look first.** When one of this ticket's own fix tickets is for the same failure (the same defect in the same place, however it is worded), or for a split the same part, file nothing: its number is the finding's `issue` (a security one: below). Any other open issue for the same failure is never reused, since a run may never build it: file the ticket, and name that issue in its `## What to build` ("may repeat #<n>").

**The ticket.** A ready build ticket, labelled `ready-for-agent`, with a title saying in plain words what is wrong ("The requeue drops a pull request queued twice"), and in its body:
- `Area: <name>`: the profile's `[areas]` area whose paths hold the lines it is about; when no area's paths hold them, or more than one does, and for every split one, this ticket's area;
- `## What to build`: the finding in plain words, naming this ticket and the review it came from ("found by round 2 of #<PR>, for #<n>"); a split one says why the part was split out, and gives the part's name exactly as `WF merge-check` gave it, on a line of its own: `Part: <name>`;
- `## Acceptance criteria`: from the finding: its reproducer's case as the test that should pass, and the fix's behaviour; a split one gets the criteria that need the part, moved from this ticket word for word, and the part working;
- `## Bar`: when this review's `bar.md` gives a bar (this ticket's, or its spec's) and the new ticket is in this ticket's area, that bar, copied (a split one always copies it); else, when the profile's `run.bar_areas` names the new ticket's area, the bar that area's tickets copy from `profile.md`; otherwise none;
- `## Blocked by`: this ticket (`#<n>`) when the new one is about this pull request's own lines, whose code isn't on the base branch yet: every split one, and a late one on the change's own lines. Otherwise "None": every old one, and a late one on lines the change only reaches.

Write "blocked by" only in `## Blocked by`: `workflow ready` reads it anywhere else on a line with an issue number as a blocker. In a copied finding or a moved criterion, write "waits on" instead, and say so in the pull request body. Its body ends with the machine line, then the agents' marker:

```
<!-- workflow:fix-ticket from=<n> kind=old|late|split -->
<!-- workflow:agent -->
```

`from` is this ticket's number, not its pull request's, written as digits alone; `kind` is one of `old`, `late` or `split`. In a run, the line is how the ticket joins the run. When this ticket was itself filed as a split ticket (its own machine line says `kind=split`), each of its findings files sets `split: true` (`review-panel` §4).

Two exceptions (ADR 0001), and a finding that is both takes both:
- **A protected path** (the profile's `guard.protected_paths`): filed as an owner task instead, labelled `owner-task` in place of `ready-for-agent`, with the same machine line.
- **A security or safety problem in code on the base branch** (`security: main`) marked a ticket to fix it:
  - every public word names only the finding's area: the title ("A security problem in <the finding's area>"), the body, the findings table: no reproducer, no file or line, no way to exploit it;
  - it is labelled `ready-for-human`, never `ready-for-agent`, so nothing builds it unattended, and its body says where the details are: "Details: given to the owner by the ticket session for #<n>";
  - its details (where, the reproducer, the fix) go to the owner privately, never on GitHub: in attended work, in the session's chat; in a run, in your own chat as soon as you have verified it, and again in your final message, which names the ticket;
  - it is a new ticket each time, unless you filed one for it yourself in this session, its details in your chat: then it is "Already filed as #<n>". Any other open one names only its area, so it can't be matched: tell the owner privately of any it may repeat.

A blocking `security: main` finding is never split out. In a run it holds this ticket for the owner:
- file its ticket to fix it as above (`ready-for-human`, only its area named, its details given privately), with `kind=old` and `## Blocked by` "None";
- add that ticket under this ticket's `## Blocked by`, replacing a "None" there and adding the section if there is none, keeping the rest of its body, so §0's blocker check (and `workflow ready`, once it is labelled ready again) stops any start before the owner closes that one;
- stop as §5's "Still red after three fix attempts" says (`needs-human`), the reason naming only its area and saying how it is released: "the owner fixes it on the base branch, merges the base into this ticket's branch and closes #<n> as completed (or, if it isn't a problem, takes #<n> out of this ticket's `## Blocked by`), then answers here".

What comes after the hold is the owner's. A later review that marks a `security: main` finding blocks holds the ticket again the same way, whatever it is: that costs the owner another look, never a merge with the problem in it. Marked a ticket to fix it, it is filed as the security bullet says. In attended work, a blocking one is fixed here instead, its details shown to the person and given privately to whoever fixes it.

A security problem the change adds (`security: change`) is the one finding never filed as marked: even when marked a ticket to fix it, it is fixed in this pull request, since it still blocks (`review-panel` §10), only its area named in public, and the findings table gives its mark. Marked blocks or note, it follows the usual rule.

In the findings table, a finding filed or found as above has the outcome "Filed #<n>", or "Already filed as #<n>".

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
- after a split, under **Split out**, each part split out, in plain words, with its ticket and the acceptance criteria moved to it, quoted;
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
- **The base branch moved:** if auto-merge is armed, disarm it first (`disable_pr_auto_merge`, or `gh pr merge <n> --disable-auto`): GitHub would merge the new head, which `WF merge-check` hasn't said `ready` for. Then `git fetch origin <base> && git merge origin/<base>`, resolve any conflicts keeping both sides' intent, rerun the tests, and push. Never rebase or force-push. With the merge queue on (`WF merge-check`'s `queue`), don't merge the base in because it moved: the queue tests the pull request on the latest base itself, and otherwise only the conductor merges the base in (step 6.4). Still merge it in to resolve a conflict (`WF merge-check`'s `resolve_conflict`), as above.
- **A required check that never starts** because its workflow is path-filtered (the profile's `ci.path_filtered`): `WF merge-check` counts it as not started, so it never says `ready`, and in `auto-merge` mode GitHub would wait for it forever. Act on this only once every other required check has finished and the evidence is posted: `WF merge-check`'s only reason left is `checks_pending`, for checks that are all in `ci.path_filtered` and `missing` in its `checks[]`. Then comment that the PR needs the owner to merge and end `waiting`. Until then, step 6.3's `not_yet` applies.
- **A check the charter waives:** it counts as passed only when its log shows a killed marker (the profile's `ci.killed_markers`) rather than a test failure, and only with the evidence below.
- **Still red after three fix attempts:**
  1. label the ticket `needs-human`, and remove `workflow:in-progress` and `ready-for-agent` (keep its other labels);
  2. comment on it and on the tracking issue with exactly what fails and why;
  3. wake the conductor (step 6.7);
  4. end with `WORKFLOW-STATUS: needs-human`.

## 6. Post the evidence and merge

1. **Push everything,** and make sure the branch is level with the base branch (with the merge queue on, the queue meets this).
2. **Run the evidence:** `WF evidence --base-ref origin/<base>`, after a `git fetch`.
   - It runs the suites in shards, resumes after a container restart, refuses a dirty tree, and runs the base branch's suites in a temporary worktree to compare counts.
   - With the profile's `commands.select_suites`, it runs only the suites the branch's changed files need, and says which it left out, or why it ran them all.
   - **When a required check was waived,** add `--all`: there the report is the proof, and `WF merge-check` counts only the full suite's.
   - Post its report on the PR.
3. **Run `WF merge-check`.** In attended work, skip this and step 4: say the PR is ready and leave it, since the owner merges. Point them at the `merge-check` skill ("is #N ready to merge?"), or `WF merge-check --fetch <n>`. In a run, right before each of these (merging, arming auto-merge, queueing, saying it's ready), run `WF merge-check --fetch <PR> --json --charter .workflow/tracking.md --review-rounds <N>`, with `<N>` the briefing's review rounds and the body of the tracking issue the briefing names saved there (`gh api repos/<repo>/issues/<tracking> --jq .body > .workflow/tracking.md`; git ignores `.workflow/`, so the evidence still sees a clean tree). Add `--review-passes <P> --small-max-lines <L> --small-max-files <F>`, with `<P>` the briefing's pass cap and `<L>` and `<F>` the briefing's small threshold (its lines and files), else the profile's `run.review_passes`, `run.small_max_lines` and `run.small_max_files`. It is the same command a person's `merge-check` runs, so a run and a person never disagree on "ready".
   - **The try-it link:** with the profile's `[previews] on = true`, read it first, each time: `WF preview --fetch <PR> --json > .workflow/preview.json`, and add `--preview .workflow/preview.json` (without `gh`, the reader takes files, as step 5 says). A reader that fails leaves the file empty, and the command says it couldn't read the preview: `not_yet`. With previews off, run no reader and pass no `--preview`: the note about the missing try-it link never blocks.
   - For a check the charter waives, add `--check-logs .workflow/check-logs` with its log in that directory, named by its check run's id on the head (a `waiver_not_taken` note names the file it wants).
   - Where `gh` can't read an input, a "couldn't read" reason names it: give it as a file (`--pr F`, `--checks F`, …) and run it again. Leave out `--asker`: it changes only the wording, never the decision.
   - **The merge queue.** Read whether the merge queue is on from the JSON's `queue` each time, never from the briefing, so a change made mid-run reaches you. With `queue: true`, `ready` means ready to queue: being behind the base is never a reason, and the rules are checked when it is queued (step 4). With a `queue_unsure` note (a merge-queue rule it can't judge, `queue` false), never merge directly or arm auto-merge, and disarm auto-merge if it is armed (`disable_pr_auto_merge`, or `gh pr merge <n> --disable-auto`), since GitHub could refuse the merge or queue it on its own: on `ready`, comment on the PR and on the tracking issue that it is ready for the owner to merge, and end with `WORKFLOW-STATUS: waiting`.
   - It always exits 0, so read its JSON's `decision`. **`ready` is the only yes**:
     - `not_yet`: never merge, arm auto-merge or queue, and if auto-merge is armed, disarm it (`disable_pr_auto_merge`, or `gh pr merge <n> --disable-auto`). Act on each of its `reasons[]` by its `action` and `fix`: a red check (§5), an open review thread, a review that wasn't clean (`review_not_clean`: fix the findings; its `next` says what follows: `round` is another round, `pass` is a Correctness pass on the head, since that was the last allowed round), a stale review (`review_stale`: a Correctness pass on the new commits), the pass cap reached (`passes_used_up`, `next: owner`: no further pass; it means `needs-human`: put the open findings in the PR body, then stop as §5's "Still red after three fix attempts" steps 1 to 4 say, with the cap as the reason), a branch behind the base (update it), a try-it link that didn't build (`preview_failed`: step 5's `failed`) or is still building (`preview_building`: wait), then run it again at the next check-in. A path-filtered check that never started is §5's.
     - `owner_review`: the change touches a protected path (the JSON's `files`). Never merge it, arm auto-merge or queue it: comment on the PR and on the tracking issue that the owner reviews and merges it ("#<n> changes a protected path (<files>): yours to review and merge"), and end with `WORKFLOW-STATUS: waiting`.
     - `ready`: merge by the briefing's mode (step 4), pinned to the head it checked (the JSON's `head`). With a try-it link (`preview.url`), first make sure "How to try it" gives it, as step 5 says: an edit of the body changes no commit, so the answer still holds.
4. **Merge** on `ready`. Without a merge queue (the JSON's `queue` is false, with no `queue_unsure` note: with one, step 3 says), what you do depends on the briefing's mode:

   | Mode | What you do |
   |---|---|
   | `auto-merge` | First post your notes for the next tickets (step 6.5) on the tracking issue, then arm auto-merge with a merge commit, pinned to its `head`: `gh pr merge <n> --auto --merge --match-head-commit <sha>` (`enable_pr_auto_merge` can't pin the head: use it only when `gh` can't, then read the PR's head back and disarm if it isn't `<sha>`). Stay with it until GitHub has merged it. Before any push of yours while it is armed (a fix, the base merged in, an update of the branch), disarm it (`disable_pr_auto_merge`, or `gh pr merge <n> --disable-auto`). At each check-in, run step 3 again and act on it: on `not_yet`, as step 3 says (behind the base: disarm, update the branch with `gh api -X PUT repos/<repo>/pulls/<n>/update-branch`, and run it again next time); on `ready` with auto-merge not armed (whoever disarmed it), arm it again, pinned to the new `head`. End each such turn `waiting`. **If GitHub refuses to arm auto-merge because the PR is already mergeable** (clean: "Pull request is in clean status"), run the same `WF merge-check` again at that moment; on `ready`, merge it yourself with a merge commit pinned to its `head` (`gh pr merge <n> --merge --match-head-commit <sha>`, `gh api -X PUT repos/<repo>/pulls/<n>/merge -f merge_method=merge -f sha=<sha>`, or `merge_pull_request` with `merge_method: merge` and `expectedHeadSha`), and on anything else act on it as step 3 says |
   | `session` | Merge it yourself with a merge commit pinned to its `head`: `gh pr merge <n> --merge --match-head-commit <sha>`, `gh api -X PUT repos/<repo>/pulls/<n>/merge -f merge_method=merge -f sha=<sha>`, or `merge_pull_request` with `merge_method: merge` and `expectedHeadSha` |
   | `owner` | Say it's ready, and leave it |

   **With the merge queue on** (the JSON's `queue` is true), nothing merges directly: add the pull request to the merge queue once per head, pinned to its `head`, your checkout's head: `gh api -i -X PUT repos/<repo>/pulls/<n>/merge-async -f merge_action=merge_queue -f sha=<sha>`, with the full SHA written out (`merge_queue` makes GitHub refuse rather than merge directly where no queue is required; never `--admin` or `bypass_rules`). When to queue it depends on the briefing's mode:
   - `session` mode: after your own final `WF merge-check` says `ready`;
   - `auto-merge` mode: as soon as `WF merge-check` says `ready`. Never arm GitHub's auto-merge with the queue on: if it is armed (the queue came on mid-run), disarm it first (`disable_pr_auto_merge`, or `gh pr merge <n> --disable-auto`);
   - `owner` mode: nothing is queued; say it's ready, and leave it.

   Before you first queue it, post your notes for the next tickets (step 6.5) on the tracking issue, once. Then read GitHub's answer (`-i` prints its status line): a **202** is accepted, not yet queued, so read its result with `gh api repos/<repo>/pulls/<n>/merge-async/<uuid>` (the `uuid` from its body) before saying it's in the queue: `enqueued` is in the queue; a **200** "already in a merge queue" is waiting there; for anything else (still `pending`, `failed`, a **409**, or a refusal), say GitHub's answer on the pull request. Never queue that head again: a head you queued only waits, whatever `WF merge-check` says of it later, and every re-queue is the conductor's, at its check-ins, which also queue a ready pull request you haven't.

   In `session` and `auto-merge` mode, stay with it until GitHub has merged it. At each check-in, run step 3 again and act on it, ending each such turn `waiting`. After the conductor merges the base in (once GitHub has taken the head out of the queue twice), `git pull`, run `WF merge-check` again, and run a Correctness pass only when it asks for one (a merge that leaves the pull request's own changes identical needs none); fix any red check (§5), and on `ready` queue the new head once, as above. A fix you push makes a new head too, which GitHub takes out of the queue: queue it once it is `ready`. If the conductor labels the ticket `needs-human` (dropped from the queue again after the base was merged in), stop: take steps 6.6 and 6.7 and end with `WORKFLOW-STATUS: needs-human`. The update-branch steps, the "behind" handling and the "already clean" fallback don't apply.

   If your permission settings refuse the merge, don't work around it. Comment that it's green and ready, and end with `WORKFLOW-STATUS: waiting`.

   In a ticket session the guard lets you merge, arm or queue only your own pull request: the pin must be your checkout's head (`git rev-parse HEAD` on your ticket branch), so after the branch was updated on GitHub (`update-branch`), `git pull` before you merge, arm or queue. For `enable_pr_auto_merge`, the guard reads the pull request's head back instead.
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
- [ ] Review panel run in rounds until clean (or the limit, the rest raised); late commits had a Correctness pass, except a merge of the base that `merge-check` carried a review over
- [ ] Every finding fixed or answered with its reason
- [ ] PR opened with the findings table and decisions; by-hand checks filed
- [ ] Merged under the merge rule (or left for the owner), notes for the next tickets posted; the claim label removed and the conductor woken (in a run)
