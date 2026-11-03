---
name: review-panel
description: Review a diff or pull request with independent agents in parallel - Standards, Spec, Correctness (with a security review where it applies) and, for UI, API or CLI changes, an explorer that uses the change from outside. Also the planning review of a map decision's or a spec session's ADRs and glossary, or a spec's draft, before it's offered or published. Use on any branch or PR, inside build-ticket or alone.
---

# The review panel

Independent reviewers read the change fresh, each in its own context and in parallel. They report; they change no code. You verify each finding and fix the real ones (under the rule for build reviewers, a fresh fixer makes the fixes: section 3).

`WF` is the kit's CLI: `python3 .claude/workflow/bin/workflow.py` (vendored), or `python3 <this skill's directory>/../../scripts/workflow.py` (plugin).

## 1. Gather the inputs, outside the repo

Make a scratch directory outside the repo, for example `/tmp/review-<ticket>-r<round>/`. Write into it:

- `commit.txt`: `git rev-parse HEAD`, the commit this round covers.
- `diff.patch`: `git diff <base>...HEAD`. The base is the pull request's base branch (the profile's `project.base_branch` unless it targets another), as `origin/<base>` after a `git fetch`.
- `ticket.md`: the ticket's body and comments, its spec (the issue under "Parent") and the issues they link.
- `rules.md`: the project's rules, copied from each document in the profile's `project.rules` (safety rules, wording), plus `profile.md`'s sensitive-data and secrets sections.
- `previous.md`, from round 2: the earlier findings and what was done about each.

**Under the rule for build reviewers** (section 10), add these, `<scratch>` being this review's scratch directory:

- `rule.md`: section 10, copied as it is, with:

  ```
  sed -n '/^## 10\. The rule for build reviewers$/,$p' <this skill's directory>/SKILL.md > <scratch>/rule.md && test -s <scratch>/rule.md
  ```

  If it fails, stop and find out why: never start the reviewers with an empty or missing `rule.md`.
- `bar.md`: the ticket's `## Bar`, or the bar its spec gives for its tickets, as written; "None" when neither gives one.
- `previous.md`, from the second review (round or pass), in place of the one above:
  - each earlier review (its kind, number and commit) with its findings numbered as in its record, each with its mark, its part exactly as the reviewer wrote it, its severity and what was done: fixed in which commit with which test, a ticket to fix it filed as which issue, contested with the written reason, or ruled kept or overturned;
  - under "Contests to rule on", the last review's contested findings, each with its number, its reason, and what it needs to be re-entered if kept: its reproducer, its part, and its `security` and area if it has them;
  - the parts that took the bar's fail-closed form or were split out;
  - under "Moved criteria", each acceptance criterion moved by a split, quoted, with the ticket it moved to;
  - under "Failures", each failure step 5 of section 3 found after the last fixer, with the command that shows it and its output.
- `since.patch`, from the second review: the pull request's own changes since the last review, round or pass, with the base branch's changes left out. `<last>` is the commit the last review covered. Before the pull request opens, it is in that review's `commit.txt`. After, it is the `commit=` of the latest review record that `merge-check` counts: one posted from an account with write access. After a `git fetch`:

  ```
  old=$(git merge-base origin/<base> <last>)
  new=$(git merge-base origin/<base> HEAD)
  tree=$(git merge-tree --write-tree --merge-base="$old" "$new" <last>) && git diff "$tree" HEAD > <scratch>/since.patch
  ```

  It replays the reviewed change onto the base the head is on, and compares that with the head. If it fails (the reviewed change conflicts with the base merged in since, the commit can't be found, or git is older than 2.40), write no `since.patch`: with none, the reviewers treat the whole change as new.

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

**Under the rule** (section 10), every reviewer follows `rule.md`. Open each prompt you write with this line, `<scratch>` filled in: the two prompts for `code-review`'s Standards and Spec reviewers, and the security review's (run it in an agent of its own, told to use the `security-review` skill on the branch):

```
Follow the rule in <scratch>/rule.md: it says how to mark and report each finding.
```

`correctness-reviewer` and `ui-explorer` read it themselves: give each the scratch directory (the explorer as well as its own files' directory), and they follow its `rule.md`.

## 3. After each round

1. Check each finding against the code. A reviewer can be wrong.
2. Fix every real one, with a test for each bug. Under the rule (section 10), a fresh fixer makes them instead, in the order **The fixer** (below) gives, and a finding marked a ticket to fix it or a note isn't fixed here (the paragraph after these steps).
3. Record each that isn't a problem, with the reason. Under the rule, a blocking finding's reason is the fixer's (**The fix rule**).
4. Run `git status`: it must show nothing a reviewer made. Discard anything stray and say so. If the guard refuses the discard (a protected file), finish in a clean copy, and say so in the PR body: `git worktree add --detach <a directory outside the repo> HEAD`, commit there, and push with `git push origin HEAD:<branch>`. Do everything after it there: later fixes, the tests, `commit.txt`, the diff and the next rounds. Give the reviewers the clean copy's absolute path as the repo: the explorer runs the CLI from it, and checks both it and the session's checkout with `git status`.
5. Rerun the typecheck and the affected tests. Under the rule, you fix nothing yourself: a failure goes in the findings table and under "Failures" in the next review's `previous.md`, whose Correctness reviewer reports it as a finding (section 10), so that review's fixer gets it.
6. Post the round's review record (section 4).

A record under the rule (section 10), written with `--findings` (section 4), comes from the reviewers' reports: every finding a reviewer reported goes in the findings file as reported, even one you judge not a problem. Such a finding marked blocks is contested only when the fixer contests it (**The fix rule**), never by you: its reason, the fixer's, goes in the findings table and in the next review's `previous.md`, under "Contests to rule on", and the next review rules on it. One marked a ticket to fix it is never dropped: it is filed as the reviewer marked it, the way `build-ticket` files tickets to fix findings, and your doubt goes in the findings table. The one exception is a security problem the change adds (`security: change`) marked a ticket to fix it: it is never filed, but fixed in the pull request, since it still blocks (section 10). A note is answered with its reason in the findings table. Neither is ruled on. A finding flagged kept after a contest is never contested again: it is fixed. One entry for each finding each reviewer reported. A mark is the reviewer's: copy it, its part, its reproducer and its flags as written, and never change one.

**The fixer.** Under the rule (section 10), each review's fixes, round 1's included, go to a fresh `fixer` agent (`pairnexus-workflow:fixer` as a plugin), never one kept from an earlier review, and you make none yourself: you build the change, start the reviewers and the fixers, post the records and keep short summaries. A finding you doubt goes to the fixer all the same: it checks it, and your doubt goes only in the findings table. The order, after each review:
1. the findings file written, and its tickets filed (`build-ticket`);
2. step 4;
3. the record posted (step 6), and, once the pull request is open, `WF merge-check` run on the head, since it says `mechanism_repeats` only while the head is the latest record's commit;
4. the fixer, when there is anything to fix, with `part.md` from that answer, a split's ticket filed first (`build-ticket`);
5. step 5, on the head it pushed.

A finding the fixer reports refused by the guard is the owner's, since only they can lift the guard's never-list: never work around it, and stop as `build-ticket` §5's "Still red after three fix attempts" says, the refusal as the reason, naming only a security finding's area. A refused finding never waits for a later review, which could pass over it.

Give it the repository's path (the clean copy's, after a step 4 that made one), the branch's name, and a scratch directory of its own, `/tmp/fix-<ticket>-<review>/` (`<review>` being `r<n>` or `pass<k>`, as the review's own), holding only these, and nothing of this session's history (no `previous.md`, no summaries):
- `ticket.md`, `bar.md` and `rules.md`, copied from the review's scratch directory;
- `findings.md`: the findings to fix, numbered as in the review's findings file. Each comes with its part, where it is, its reproducer, the reviewer's one-line fix, and its `security` and area; one kept after a contest comes with the ruling and its reason. They are the review's findings marked blocks, and any security problem the change adds (`security: change`) marked a ticket to fix it. An overturned one isn't given to it: it counts for nothing. A blocking security or safety problem in code on the base branch (`security: main`) goes in only in attended work: in a run it holds the ticket for the owner (`build-ticket`), and the fixer never sees it;
- `moved.md`: the criteria moved by a split, quoted, each with its ticket, or "None";
- `head.txt`: `git rev-parse HEAD`, the head it starts from;
- `part.md`, when `merge-check` says to give a part the safe fallback or split it out: each such part's name exactly as the records give it, and which for each.

If auto-merge is armed, disarm it first: the fixer pushes. Its report gives each finding's outcome: the commit and the test for each fixed one (they go in the findings table), the reason for each contested one, the part for each taken with its part, and the guard's refusal for each refused.

**The fix rule.** The `fixer` agent follows it, and gives it in full. For each finding it is given:
- Check it against the code first: a reviewer can be wrong.
- A defect: its reproducer as a failing test first, then the fix that makes it pass. A missing test (an acceptance criterion unmet, or behaviour untested): the test is the fix.
- Narrow first: prefer a fix that removes a case, refuses more or deletes text over one that adds; a defect it can't fix in place, it fixes by refusing the case it fails on. A fix that adds an exception, a state or a rule tests both sides of it in the same commit.
- Change nothing a finding doesn't need, never build a moved criterion, and never put back a part split out.
- Then the typecheck and the affected tests, a commit for each finding, a push, and each finding's outcome reported.
- "Not a problem": the finding is contested with a written reason, never fixed silently or dropped; its reason is the contest's, in the findings table and under "Contests to rule on". A finding kept after a contest is fixed, never contested again; one overturned counts for nothing. Every finding ends fixed, contested, taken with its part (a part in `part.md`, replaced or taken out) or refused by the guard. A security finding is never taken with its part, and a security problem the change adds marked a ticket to fix it is fixed, never contested: it still blocks (when its reproducer already gives the right result, the test is the fix). The fixer never changes a mark.
- A security problem the change adds: its test's name, its row in the findings table and its commit message name only its area, and so does every other word the fixer writes in the repository.

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
- **Under the rule** (section 10), a round's or a pass's record is written from its findings file, `findings.json` in its scratch directory, with `--findings` in place of `--clean` or `--not-clean`: its result is worked out from the marks, not clean when any finding is marked `blocks`.

  ```
  WF review-record --kind round --round <n> --commit <sha> --reviewers standards,spec,correctness --findings /tmp/review-<ticket>-r<n>/findings.json > /tmp/review-<ticket>-r<n>/record.md
  WF review-record --kind pass --round <last round> --commit <sha> --reviewers correctness --findings /tmp/review-<ticket>-pass<k>/findings.json > /tmp/review-<ticket>-pass<k>/record.md
  ```

  The file is a JSON object, always, so no outcome or split flag is ever lost: `findings`, the list, empty when no reviewer reported anything; `outcomes`; and `split`. Each finding (section 3) gives its `mark` (`blocks`, `ticket` or `note`), its part as `mechanism`, its `reproducer` (needed for `blocks`, and never shown in the record), `covered` (the bar's fail-closed form covers it), `contested` (a finding of the last review kept after a contest, re-entered here), `security` (`change` or `main`) with its `area`, and `issue` once its ticket is filed. `outcomes` gives what became of the last review's findings after its record was posted (each contest's ruling, a part that took the bar's fail-closed form, a part split out to a ticket), and `split` is true when the ticket was itself made by a split. For example:

  ```
  {
    "findings": [
      {"mark": "blocks", "mechanism": "the requeue order", "reproducer": "a dropped PR requeued twice: queued once", "covered": true},
      {"mark": "ticket", "mechanism": "label sync", "issue": 415},
      {"mark": "note", "mechanism": "wording"}
    ],
    "outcomes": [
      {"outcome": "contested", "finding": 2, "ruling": "overturned"},
      {"outcome": "fail-closed", "mechanism": "the merge gate"},
      {"outcome": "split", "mechanism": "the preview reader", "issue": 416}
    ],
    "split": false
  }
  ```

A round's or a pass's record also names two hashes of the pull request's own changes at that commit, `diff=` (with their context lines) and `lines=` (the changed lines alone), which the command computes from the diff against the merge base of `origin/<base>`, fetched first. When the pull request's base branch isn't the profile's `project.base_branch`, add `--base <branch>` to the command. A hash it can't compute reads `unknown`, and it says why on standard error: the record still counts, and `record.md` holds only the record.

Keep `record.md` only when the command exited 0. If it refuses, delete the empty `record.md`, fix what it names and run it again: never write a record by hand.

Post `record.md` as it is, as a comment on the pull request: `gh api repos/<repo>/issues/<pr>/comments -F body=@/tmp/review-<ticket>-r<n>/record.md` (the pass's path for a pass), or the GitHub MCP tools with its text. It already ends with the agents' marker; add nothing.

No pull request yet (the first rounds of `build-ticket` run before it opens)? Keep each `record.md` in its scratch directory and post them, oldest first, as soon as the pull request is open.

## 5. When to stop

Repeat on the new diff until a round finds nothing to fix, at most the briefing's review rounds in a ticket session, else the profile's `run.review_rounds` (a ticket that gets the small review has its one round: section 7). For a light review, or when the briefing's review rounds are 1, follow the light review (section 6) instead, unless the ticket gets the small review (section 7).

- Anything still open after the last round goes to the owner in the PR body, never silently.
- Any commit after the last round gets a Correctness pass on just those commits before merging, except a merge of the base that leaves the pull request's own changes identical, which needs CI only: after pushing a merge of the base, run `workflow merge-check` (`--fetch <PR> --json`, in a ticket session with the briefing's flags) and run a pass only when it asks for one. Before a pass starts, `mkdir -p /tmp/review-<ticket>-pass<k>` (its scratch directory, `k` counting the passes from 1) and write `git rev-parse HEAD` to `commit.txt` there: the commit it covers, never one made after. Then post its record (section 4). Under the rule (section 10), a pass reviews the changes since the last review, round or pass (`since.patch`, section 1), not since the last round.
- **Passes stop at the pass cap:** at most the briefing's pass cap in a ticket session, else the profile's `run.review_passes`, counting every pass after the last round, each record once, on any commit, except a pass on a merge of the base after a clean review that left the pull request's changed lines as they were, which `merge-check` asks for even at the cap (a pass that rechecks open findings always counts). When one more pass would be needed past it, `workflow merge-check` says `passes_used_up`: run no further pass. What's still open goes to the owner in the PR body, and the owner decides (in attended work they can choose "One more pass").
- **The pass cap `until-clean`** (a briefing's or the profile's, #402) is no cap: after the last round, fix each pass's findings and run another, until one is clean. `merge-check` never says `passes_used_up`. Keep the PR body's findings table current after each pass: in a run, the end time can come first, and the conductor then sets the ticket aside with its open findings there.

## 6. The light review

A shorter review for a low-risk change, asked for as "build #12 with a light review" (`build-ticket`, "Review it"). It keeps every reviewer but the explorer, and it never changes the merge rule (flow §4): CI green, the review record, the owner's review of kit and CI files and the rest of it all stand.

- **Round 1** runs the full panel (Standards, Spec, Correctness, and the security review where it applies) but no UI explorer. Its record:

  ```
  WF review-record --kind round --round 1 --commit <sha> --reviewers standards,spec,correctness --clean > /tmp/review-<ticket>-r1/record.md
  ```

  (`standards,spec,correctness,security` when the security review ran; `--not-clean` when it found something to fix; under the rule, `--findings` in place of `--clean` or `--not-clean`, as section 4 says.)
- **If round 1 isn't clean,** fix its findings as in section 3, then run Correctness-only rounds until one is clean, at most 2 more. Each is a round of its own, with its own scratch directory, `commit.txt` and `previous.md`, and posts its record as a round, never as a pass:

  ```
  WF review-record --kind round --round <n> --commit <sha> --reviewers correctness --clean > /tmp/review-<ticket>-r<n>/record.md
  ```

  (`--not-clean` when it found something to fix; under the rule, `--findings`, as section 4 says.) The 2 is fixed, whatever `run.review_rounds` says: with the briefing's review rounds at 1, these rounds come on top of its "at most 1".
- **Post each record** as section 4 says. A later commit after the last round still gets its Correctness pass (section 5).
- **Anything still open** after them goes to the owner in the PR body, never silently.

**In a run:** when the briefing's review rounds are 1, ticket sessions use this same shape, except on a ticket that gets the small review (section 7), so one round means one full-panel round, without the explorer, in attended and unattended work alike. There the owner chose it, by giving the run one review round; it is never chosen for the person.

## 7. The small review

The review of a ticket marked `Review: small` while its diff stays within the small threshold: at most the briefing's small threshold in a ticket session, else the profile's `run.small_max_lines` changed lines in `run.small_max_files` files, both outside tests (`build-ticket`, "Review it", measures it first). Planning writes the mark (flow §2). Like the light review, it never changes the merge rule (flow §4): `workflow merge-check` holds a review with no Spec round to the threshold.

- **One round.** Its reviewers, started as section 2 says:
  - Correctness;
  - the security review, where it applies (section 2);
  - the explorer, only where it would run in any round: the explorer isn't `none` and the change touches a screen, an endpoint or a command.

  No Standards and no Spec reviewer. The inputs are section 1's.
- **Its record** is an ordinary round record, as section 4 says, with the reviewers that ran:

  ```
  WF review-record --kind round --round 1 --commit <sha> --reviewers correctness --clean > /tmp/review-<ticket>-r1/record.md
  ```

  (`correctness,security`, `correctness,explorer` or `correctness,security,explorer` when those ran; `--not-clean` when it found something to fix; under the rule, `--findings` in place of `--clean` or `--not-clean`, as section 4 says.)
- **Fixes after it** are covered by Correctness passes (section 5), under the pass cap. There are no further rounds: when the round isn't clean, fix its findings as in section 3, and a clean pass on the head lifts them.
- **Past the small threshold,** measured before reviewing or as `merge-check`'s `past_small_threshold`, the ticket doesn't get the small review: run the full panel (section 5), or the light review (section 6) in a 1-round run. The pull request's body says the diff overruled the mark. After a small round already ran, that is one full-panel round (the light review's round 1 in a 1-round run, without the explorer) with the next round number, allowed past the round limit; if it isn't clean, fix its findings and run a Correctness pass, with no further round.
- **Anything still open** after the pass cap (or, with `until-clean`, at the run's end time) goes to the owner in the PR body, never silently.

## 8. The planning review

Planning is reviewed before it's offered or published (flow §1 and §2): a map decision's pull request (its ADRs and glossary), a spec's draft, and a spec session's ADR or glossary pull request. Build tickets aren't. Sections 1 to 5 hold, with these differences. Planning reviews don't get section 10, the rule for build reviewers: no `rule.md`, `bar.md` or `since.patch`, and their records keep `--clean` or `--not-clean`.

**The inputs,** in a fresh scratch directory for each kind of review, so a spec's review and the same session's pull request never share one: `/tmp/review-<issue>-spec-r<n>/` for a spec's draft, `/tmp/review-<issue>-pr-r<n>/` for a pull request. `<issue>` is the decision ticket, the item's issue, or the map's number for its Destination item (a spec has no number of its own until it's published), else a short name for the work:
- the diff as `diff.patch`, or the spec's draft as `spec.md`: the whole body exactly as it will be published, any footer or marker included (a Claude Code cloud session's own footer needn't be: the hash leaves it out, **Records**);
- the owner's answers as posted, as `answers.md`: each question round's post copied as posted, its tags, evidence and the checks' findings included (**Fixes**), never the session's summary, with every confirmed replacement line and every comment a check posts (its fixes and what it leaves), even one that lists no fixes. They come from the decision ticket, the item's issue or the map's Destination item (a comment on the map naming it). A map's Destination item's spec takes, as well, the answers posted on the map decisions it draws on. Once the spec is published, a review (an edit's, or a spec session's pull request's) takes all of these as well as everything of these kinds posted on the spec's issue: every question round (each edit's so far, this one included, a pull request's, and the breakdown check's, which settle what each ticket builds, not the spec's words), confirmed line and check's comment (below), so a dropped earlier answer is still caught. The whole file is in the order the comments were posted, oldest first, each with its date and where it was posted. Sensitive data (`profile.md`) is left out of them and marked as left out, never posted;
- the ADRs and glossary, all of them, not only the changed ones;
- the decision ticket and its map, or the item's issue, as `ticket.md`;
- the project's rules, as `rules.md`.

**The reviewers,** both every round, in one message:
- **Correctness:** the `correctness-reviewer` agent, briefed for a document: check its facts against the code, look for contradictions with other ADRs and the glossary, and apply the project's safety rules (a name or other sensitive data where it shouldn't be, a screen given to the wrong reader).
- **Spec:** a general-purpose agent with its own brief, since `code-review`'s Spec axis compares code to a ticket: read the ADRs and glossary, or the spec's draft, against `answers.md`, word for word, and report anything the owner said that is dropped, reworded into a different meaning, or stated as settled where the owner left it open, and anything recorded as the owner's that they didn't say. An answer tagged **accepted recommendation** counts as the owner's, in the words of the recommendation they accepted. Its brief also says that each post's evidence and the checks' findings aren't the owner's words: never report them as dropped, or as the owner's. A confirmed replacement line ("answer 34 replaces 7: confirmed") settles which answer stands, and so does a fix listed in a question round's post, or in a check's comment, with no objection from the owner after it. A conflict such a comment lists as left open is settled by neither, nor by later words, until the owner answers it in a later question round or a confirmed line: until then, report a draft that states it as settled. The breakdown check's rounds settle what each ticket builds: never report them as dropped from the spec. Only where none of these applies, and the owner's later words plainly change an earlier answer, the later words stand; where it's unclear whether they do, report it, so it goes to the owner (**Fixes**).

No Standards reviewer and no explorer: there is no code to hold to the standards and nothing to use.

**Rounds:** both reviewers run every round, until a round is clean, up to the profile's `run.review_rounds`. Planning runs in attended sessions, never in a ticket session, so no briefing's rounds apply, and the light review doesn't either. Anything still open after the last round goes to the owner: in the pull request's body, or, for a spec, in the handover. A spec whose last round wasn't clean is fixed and published all the same, and the handover says it reads as unreviewed (`workflow ready` notes its tickets) until a clean round on its current body is posted.

**Fixes:** the session fixes wording, facts and omissions itself. A fix that would change what a decision means is put to the owner as a question first. These questions are decision questions, under every rule of the flow's section (flow, "Decision questions"). Among those rules, each recommendation carries its evidence, and "yes to all" answers only the questions with a recommendation. Each question round waits for its check before it's asked (**Before each question round**, below). Each question round is posted as soon as it's answered, with each question, its recommendation and evidence, the checks' findings, and the owner's reply quoted word for word, tagged **accepted recommendation** or **the owner's own words**. A replacement or narrowing the owner confirmed is posted as a plain line ("answer 34 replaces 7: confirmed"). A question round goes where the answers are posted (the decision ticket, the item's issue or the map's Destination item), or, once the spec is published, on the spec's issue: an edit's question rounds, and those of a spec session's pull request.

**Before each question round:** each question round **Fixes** sends waits for its check, one read by `planning-checker` of its recommendations (with none, its options and what each gives up), before the owner sees it (flow, "Decision questions", **The checks**). It is the check `start`'s "Before each round" gives every round of decision questions but a check's own, so whether `start` or this section asks the question round, it gets this one read, never two. Fill `/tmp/plan-check-<issue>-round-<n>/` (`<issue>` being where the question round will be posted) as the agent's "Your inputs" says, with the inputs `start`'s rule lists. Put in the question round's questions as you're about to ask them, each with its recommendation and evidence, and every post of the kinds `answers.md` takes, as posted so far, the checks' own posts included and any question round posted since this planning round's `answers.md` was built. Add what the owner asked for that raised the round, word for word, tagged **the owner's own words**: their words in the item's issue (for a map decision or a map's Destination item, the map's own item's issue), or the change they asked for in an edit after publishing. Add the rest as it is written, untagged: the item's issue, the map's Destination item or the decision ticket, and once the spec is published, its body as published. For a question a planning round's fix raises, also add the draft or diff that round reviewed and the finding behind the question. The checker reads them against the code, the ADRs, the earlier answers and the project's rules. Each finding either changes the recommendation (a **fix**, or an **ask** showing your own recommendation was wrong) or is shown beside its question as "Check: …", in plain words with its example. A finding about no question in the round, a change that leaves no basis for a "(Recommended)", and a "Check: …" about the owner's own words are handled as `start`'s rule says. Then ask the question round as its check left it. Its check is never repeated: the one read covers what you changed from its findings and each question asked on its own after the round, and the re-read (below) reads what the answers changed, not the round again. If the read fails, try it once more, and if it fails again, ask the question round all the same and say in its post that it wasn't checked, and why. Its post lists the check's findings, each with whether it changed the recommendation, was shown as "Check: …" or was a fix made outside the round, or says "nothing found" (or "not checked", with why).

**The re-read:** after each question round, `planning-checker` reads, once, what that question round changed, against all the earlier answers, and stops. It runs before the next planning round, or, after the last planning round, before the spec is published or the pull request offered (for an edit after publishing, before its body is saved and any tickets are written or changed from it). It isn't a planning round (no record), and nothing reads its result again. Fill its scratch directory, `/tmp/plan-check-<issue>-reread-<n>/` (`<n>` counting re-reads on that issue), as the agent says, with every answer `answers.md` takes, wherever it was posted, and telling it which read it follows (this planning round, or the edit), what that question round changed, and the fixes listed in its post. Make its **fix** findings. Keep its **ask** findings as left open: they are never asked. List the fixes made, with what it leaves (those findings, and the question round's questions left open or unanswered), in a comment on the issue the question round was posted on (on a map, naming its Destination item, as the round's post does), straight after the read, since no round follows a re-read (flow, "Decision questions", **Each read's fixes**). What's left also goes where the flow says (flow, "Decision questions", **What's left**): for a spec, into its Further Notes as open questions before it's published, or, once it's published, that comment on the spec's issue lists them; for a map decision, its resolution comment.

**Records:** after every round, whatever it found (section 4's rules on refusals hold):
- a decision's or a spec session's pull request gets a round record on its commit, kept until the pull request opens (section 4, "No pull request yet"):

  ```
  WF review-record --kind round --round <n> --commit <sha> --reviewers spec,correctness --clean > /tmp/review-<issue>-pr-r<n>/record.md
  ```
- a spec gets a spec record keyed to its body, the SHA-256 of `spec.md` in place of a commit, posted on the spec's issue once it is published, oldest first:

  ```
  WF review-record --kind spec --round <n> --body /tmp/review-<issue>-spec-r<n>/spec.md --reviewers spec,correctness --clean > /tmp/review-<issue>-spec-r<n>/record.md
  ```

  (`--not-clean`, for either record, when the round found something to fix.)

  Publish the last round's `spec.md` as is. After a last round that wasn't clean (**Rounds**), make the fixes in that same `spec.md`, once its `record.md` is written, and publish that. A question round sent after that round gets its re-read first (**The re-read**), and its fixes go into that same `spec.md`, with what it leaves as open questions in Further Notes on a first publish, before the body is published (for an edit, saved). Before posting the records, check nothing changed on the way. Make its directory (`mkdir -p /tmp/review-<issue>-spec-check`) and save the published body as GitHub returns it, never retyped (`gh api repos/<repo>/issues/<spec> --jq .body > /tmp/review-<issue>-spec-check/published.md`, or the GitHub MCP tools' `body` written to that file as is). Then print the full hash of each file, never writing a `record.md`: `review-record` reads them as a spec record does (line endings made `\n`, a cloud session's footer left out), which a plain `sha256sum` wouldn't:

  ```
  WF review-record --kind spec --round 1 --body /tmp/review-<issue>-spec-check/published.md --reviewers spec --clean | grep -o 'body=[0-9a-f]*'
  WF review-record --kind spec --round 1 --body /tmp/review-<issue>-spec-r<n>/spec.md --reviewers spec --clean | grep -o 'body=[0-9a-f]*'
  ```

  The two must match. A Claude Code cloud session's GitHub tools, `gh api` among them, add their footer to every body they write, editing it back included: a blank line, `---`, then `_Generated by [Claude Code](https://claude.ai/code)_`. The hash leaves out exactly that footer at the very end (repeated, too), so it never makes the two differ, and needn't be in `spec.md`. Any other difference counts. Each line must print a `body=` line: one that prints nothing was refused (its message is on stderr), and two empty lines are no match. If they don't match (another footer, a tool's edit), edit the body back to the file's text and check again; if it still differs, post no records and say so in the handover. Nothing waits to go on the spec's issue before the records: each question round was posted as soon as it was answered (**Fixes**), a spec with nowhere else to post having filed an item's issue first (flow §2).

**An edit after publishing** (the guided start's "Edit the spec first", a later change to the spec) makes it read as unreviewed: the edited body gets another planning round, its own spec record, before any tickets are written from it. Its questions are decision questions too. Each of its question rounds waits for its check before it's asked (`start`'s "Before each round"). Post each of its question rounds on the spec's issue as soon as it's answered, in the tagged form **Fixes** gives, the owner's request for the change among them, quoted word for word and tagged **the owner's own words**, any sensitive data (`profile.md`) left out and marked as left out, so the Spec reviewer reads them with the rest. Each question round then gets its re-read (**The re-read**) before the planning round, and what it leaves goes in the re-read's comment on the spec's issue.

## 9. The findings table (for the PR body)

| # | Round | Reviewer | Finding | Outcome |
|---|---|---|---|---|
| 1 | 1 | Correctness | A not-planned blocker reads as done | Fixed in abc1234, test `test_blockers_not_planned` |
| 2 | 1 | Spec | No `Area:` on the new tickets | Not a problem: the spec makes areas optional for one-off tickets |

Under the rule (section 10), the table gains the mark and the part after the reviewer. A security finding's row names only its area, in every column: its part, its finding and its outcome, the test's name included.

| # | Round | Reviewer | Mark | Part | Finding | Outcome |
|---|---|---|---|---|---|---|
| 1 | 1 | Correctness | blocks | the blocker check | A not-planned blocker reads as done | Fixed in abc1234, test `test_blockers_not_planned` |
| 2 | 1 | Standards | note | wording | "Sync" where the glossary says "update" | Noted |

## 10. The rule for build reviewers

This section is copied, as it is, into each build review's scratch directory as `rule.md` (section 1), so keep it the last section. Every build reviewer follows it: Standards, Spec, Correctness, the security review and the explorer, in rounds and passes, the light and small reviews included. Planning reviews (section 8) don't get it.

**When it applies:** once `build-ticket` says build reviews follow it; in a run, only when the briefing has a "Findings:" line, since a run keeps the rule it started with. Until then, build reviews keep today's rule: no `rule.md`, and records with `--clean` or `--not-clean`. Under the rule, every build review's record is written with `--findings` (section 4).

**Your inputs,** in the scratch directory beside `diff.patch`, `ticket.md` and `rules.md`:
- `bar.md`: the ticket's bar: what it must handle, what it does when it can't be sure (its fail-closed form), and the limits it accepts; "None" when it has none.
- `previous.md`, from the second review: the earlier reviews' findings, each with its number in its review's record, its mark, its part and what was done; the contests for you to rule on; the parts that took the fail-closed form or were split out; and the criteria moved by a split.
- `since.patch`, from the second review: the pull request's own changes since the last review, with the base branch's changes left out.

**Marks.** Mark each finding:
- **blocks:** it holds the merge until it is fixed. It needs a reproducer (below); without one, mark it a note.
- **a ticket to fix it** (`ticket`): a real defect that goes to a ticket of its own, built next, not in this pull request: one in code the change neither touches nor reaches, a breach of a written rule outside the change's own lines, or, from the second review, a finding that would otherwise block, on lines already reviewed, that isn't one of the kinds that still block (below).
- **note:** a preference no written rule backs, a gap the bar accepts, a finding on a moved criterion, or a finding that would block but has no reproducer. Noted in the findings table; it neither blocks nor gets a ticket.

The mark isn't the severity. Severity: critical, important or minor. "Critical" is the top severity; it never means blocks. A minor finding can block, and a critical one with no reproducer is a note.

**Reproducers.** A finding marked blocks gives one, by what it is about:
- code: an input, and the result it should give;
- skill or doc text: a concrete scenario, and the two lines that answer it differently;
- an unmet acceptance criterion or untested behaviour: the criterion or behaviour quoted, and the test that should exist;
- a breach of a written rule: the rule quoted, and the line that breaks it.

No reproducer: the finding is a note, whatever its severity.

**The part.** Name the part of the change each finding is about: a short name, at most 80 characters, one line, no backtick or `~~~`, such as "the requeue order". When `previous.md` names the same part, reuse its name exactly, character for character; give a new name only to a part no earlier review named. Say, too, whether the bar's fail-closed form covers the part: the part could do what `bar.md` says the change does when it can't be sure.

**What blocks.** A finding with a reproducer blocks when it is:
- a defect in the change's own lines;
- something the change breaks elsewhere (a regression in code it reaches);
- something the change makes reachable;
- an acceptance criterion not met;
- new behaviour without a test;
- a safety breach the change adds;
- a security problem the change adds;
- a breach of a written rule (`rules.md`) in the change's own lines.

Where the hunt stops:
- **The bar:** a gap `bar.md` accepts as a limit is a note.
- **Moved criteria:** a criterion `previous.md` lists as moved by a split isn't unmet here: a finding on it is a note.
- **Lines already reviewed** (from the second review): a finding that would otherwise block, on lines unchanged since a review that covered them (in the change or in what it reached), is marked a ticket to fix it, unless it is a safety breach, a security problem the change adds, loses data, leaves an acceptance criterion unmet, leaves new behaviour untested, or is something the change breaks elsewhere: those still block, whichever review finds them.

**From the second review,** a round or a pass, review `since.patch` and what it reaches: the code it calls and the code that calls it, read in full in the repo. Read `diff.patch`, the whole change, for context. Everything in `since.patch` follows the rule as in a first review, and so do the lines it reaches that no earlier review covered. Check each fix `previous.md` lists, and, as the Correctness reviewer, report each failure it lists under "Failures" as a finding, marked as any other, the failing command and its output as the reproducer. With no `since.patch`, the whole change is new to this review. An empty one still asks for a look: check the change's lines in `diff.patch` against the base, for something it breaks.

**Security.** A security problem the change adds: mark it as any other finding, with `security: change` and its area, a word or two such as "sign-in". A security or safety problem in code already on the base branch: `security: main`, with its area. Give its details (where, the reproducer) in your report, never in a part's name: the public records show only the area.

**Contests.** `previous.md` lists, under "Contests to rule on", the last review's findings marked blocks that were contested, each with its written reason. Only a finding marked blocks is contested. The Correctness reviewer rules on each: **kept** (the finding stands: re-enter it as a finding of this review, marked blocks even on lines already reviewed, flagged kept (`contested` in the findings file), with its reproducer, its part, and its `security` and area as before) or **overturned** (it counts for nothing: leave it out). Other reviewers don't rule. A kept finding is fixed, never contested again. Never change a mark yourself to settle a contest: rule on it.

**How to report.** For each finding:
- **Mark:** blocks, ticket or note;
- **Severity:** critical, important or minor;
- **Part:** its name;
- **Where:** file and line, or the criterion or rule;
- **Reproducer:** for a finding marked blocks (above);
- **Covered:** yes when the bar's fail-closed form covers the part, else no;
- **Security:** none, change or main, with its area;
- **Kept:** yes for a finding re-entered after its contest was kept, else no;
- **The fix:** one line.

Then, from the Correctness reviewer, each contest's ruling: its number in `previous.md`, kept or overturned, and why. Say plainly when you found nothing.
