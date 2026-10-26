# Changelog

## Unreleased

**The conductor never builds a ticket named to it: "build #12" becomes a run for #12** (#308).

- **The context hook:** in a conductor session (`WORKFLOW_ROLE=conductor`, with or without a profile), a message that names a ticket right after a build verb ("build #12", "building tickets 12 and 13", "fix bug #12", "Let's work on 12", "pick up #12", "build spec #32"), names it before "build", "built" or "implement" ("#12 please build it"), or is `/next`, `/build-ticket` or `/implement-spec` brings a line first, beside the flow: if the message asks for a ticket to be built, the conductor makes no branch, code or pull request of its own for it, never loads `next` or `build-ticket` for it, and follows the `conductor` skill instead. A message that names no ticket ("why did the build fail?", "fix the CI", "fix 2 typos", "build 2.0") brings nothing: a bare number counts after "ticket" or "issue", or at the end of its clause ("build 12 please"). Only `WORKFLOW_ROLE` makes a conductor session, so the hook reads no branch for it, and every repeat in its pattern is bounded, so a long pasted prompt stays quick. Attended and ticket sessions get nothing new.
- **`conductor`'s "A ticket named in chat":** with no run in progress, a run scoped to that ticket (`scope.tickets` `[<n>]`, `follow_unblocked` false), through the usual pre-flight and kick-off; during the run this session conducts, the amendment "also #<n>" (added to `plan`, to `scope.tickets` when it is a list, and out of `scope.exclude`); during a run another session conducts, nothing written, and the owner told to comment "also #<n>" on its tracking issue or to say "conductor resume". A kick-off under way takes it into its draft plan; a ticket already in the run, or a run stopping or out of sessions, is said as it is. A named spec stands for its open build tickets. `/next` with no ticket offers a run of the ready tickets. Claiming the ticket for its ticket session stays the conductor's, as before. Its description names these phrases.
- **`next`** opens with "Never in a conductor session" and no longer treats a conductor session like a ticket session ("build as the briefing says"). **`build-ticket`** stops before the claim in a conductor session, and its description says so. Flow §5 says what a ticket named to the conductor becomes.
- Tests: `tests/test_conductor_never_builds.py`; `tests/test_light_review_offers.py`'s pinned line moves to the new wording.
- **For projects updating:** nothing to do. A conductor session that was asked to build a ticket now starts a run for it instead.

**`review-record --measure` counts with the same pinned `git diff` as the hashes** (#298, from #258).

- **`small.local_changes`** (what `--measure` counts) now diffs with the pins `own_changes` gives the hashes, which move to `small.py` (`DIFF` and `pinned_diff`) so both use one: renames within git's default limit, a submodule never left out, git's default size for a binary file, no external diff or textconv, Myers, and the attributes of the commit itself (git 2.40 and later), never a global, the system's or the working tree's file. So `diff.renameLimit=1`, `diff.ignoreSubmodules=all`, `core.bigFileThreshold`, `core.attributesFile` or an uncommitted `.gitattributes` with `-diff` no longer change `--measure`'s counts, which now agree with what `merge-check` measures from GitHub.
- **Replaced objects** (`git replace`), which GitHub never reads, no longer change the counts or the hashes: `review-record`'s git reads the objects as committed (`GIT_NO_REPLACE_OBJECTS` and `core.useReplaceRefs=false`), so a replaced blob changes no count and a grafted commit doesn't move the merge base. For both, a diff driver's `binary` setting in the configuration, `.git/info/attributes` and git's deprecated `.git/info/grafts` still count.
- Tests: `tests/test_measure_pinned.py`.
- **For projects updating:** nothing to do. Counts for ordinary changes are unchanged; a checkout whose configuration changed them now counts as GitHub does.

**Runs queue instead of updating: the conductor's check-ins, `build-ticket` and the ticket-session prompt with a merge queue** (#249, part of #243; answers 7, 12, 14, 17 and 18 on #241). With the queue off, nothing changes, except where a ruleset has a merge-queue rule the kit can't judge (below).

- **`build-ticket` and the ticket-session prompt:** a session reads whether the merge queue is on from `merge-check`'s `queue` each time, never from its briefing. With it on, it queues its pull request once per head through `merge-async`, pinned to its checkout's head: in `session` mode after its own final `merge-check` says `ready`, in `auto-merge` mode as soon as it does, never arming GitHub's auto-merge. It stays with the pull request until GitHub merges it; after the conductor merges the base in, it runs `merge-check` again and a Correctness pass only when it asks for one. The update-branch steps, the "behind" handling and the "already clean" fallback don't apply, but a conflict is still resolved by merging the base in. A head already queued only waits.
- **The conductor's check-ins:** a new "The merge queue on" row queues every open, `ready` pull request in `auto-merge` or `session` mode (never `owner`), gives each answer to `workflow state drop` and does what it prints: `merge_base` merges the base in with `update-branch` pinned by `expected_head_sha`, `needs_human` takes the usual `needs-human` steps ("dropped from the merge queue again after the base was merged in", or GitHub's message after three `failed` answers). The "behind", "`session` mode", "`auto-merge` mode" and "already clean" rows say they apply without a queue. The stuck row counts a pull request in the queue as waiting on CI when this check-in's `state drop` for its head printed `in_queue`, `waiting` or `requeued`. An amendment is validated with the queue on only when it adds a waived check. An owner's answer that sends a ticket back to `queued` clears its merge-queue fields, so the drop rule starts afresh.
- **A mid-run change of the queue's state** ("The merge queue's state", after the check-in rows): `workflow state queue` at each check-in; a failed ruleset read is never a change; on `changed`, the conductor logs it in the ledger, says so on the tracking issue, follows the ruleset from then on, and stops applying the charter's waivers when the queue comes on. A merge-queue rule the kit can't judge (`queue_unsure`) counts as on for the state, and its pull request is never merged directly nor armed: the owner merges it.
- **The kick-off** passes the queue's state (`--queue on|off`) to `charter questions`, `charter validate` (an amendment's only when it adds a waived check; `docs/charter.md` says so too) and `state init`, and recommends the queue or not by `check-setup`'s rule, with its reason, pointing to an attended session's "Use a merge queue". It never changes the ruleset itself, and never offers the upgrade while a run is in progress.
- **The run report** reads each merged pull request's timeline for `added_to_merge_queue`, and flags one that merged with a request made after it was queued (changes requested, an open review thread) and offers a revert.
- **Flow §4's merge-mode paragraph** says what each mode means with the queue, and scopes "keeps the branch up to date" and "already mergeable (clean)" to "up to date".
- Tests: `tests/test_queue_runs.py`.
- **For projects updating:** nothing to do. A run reads the queue from the ruleset; without one, it runs as before. One change without a queue: where a ruleset has a merge-queue rule the kit can't judge (`queue_unsure`), a run's ready pull requests now go to the owner to merge instead of being merged or armed.

**`merge-check` carries a review over a merge of the base that leaves the pull request's own changes identical** (#261, from #255; answers 4, 11, 23 and 24 on #253). `merge-check`'s side of the free base merge, after the record side (#258).

- **The head's hashes.** `merge-check` reads each file's blob `sha` and `patch` as well as its status and counts (`--fetch` already gets them from GitHub's REST list), and hashes the pull request's own changes at its head with #258's definition (`own_changes.of_files`). `--json` shows them as `"head_hashes": {"diff": …, "lines": …}`, each `unknown` where they can't be computed: a file with changes but no patch (too large for GitHub to show, or `--files` from gh's or GraphQL's list), files it can't read, or text the hash can't encode (a lone surrogate in a hand-given file). A file whose `patch` isn't text makes `--files` unreadable.
- **The carry-over.** When the head is a merge of the base (as below) and isn't the last counted review's commit (round or pass) but its `diff` hash is that review's, that review covers the head, with its result, clean or not, and no pass is needed; a note (`review_carried`) says so.
- **The pass cap.** A pass doesn't count toward `--review-passes` when its commit is a merge of the base (a commit of the pull request with two or more parents, at least one of them outside its commits, read from `--commits`' `parents`; GraphQL's `parents.nodes` too), the last counted review before it was clean (the latest by the pull request's history, so a record posted late for an older commit isn't it), its `lines` hash is that review's, and no record on its commit since the last round wasn't clean (a pass that rechecks open findings always counts); a note (`free_passes`) says how many didn't count. Commits without parents, or a list with a page left out, make every pass count. At the cap, a head that is such a merge, after a clean review with the same `lines` hash, still gets the pass it needs rather than `passes_used_up`, since that pass wouldn't count; and `passes_used_up` says how many passes counted of those posted when some didn't ("1 Correctness pass counted of 2 posted"). `docs/profile.md`'s `review_passes` and the `merge-check` skill say the same.
- **Old records:** a record without the hashes, or with `unknown`, covers only its own commit, and its passes count, as before.
- **"Every commit after the last round gets a Correctness pass"** now has its exception wherever it is said (flow §3 step 3, flow §4 items 3 and 4, `review-panel` §5, `build-ticket`'s review step and its checklist line): a merge of the base that leaves the pull request's own changes identical needs CI only. A session runs `merge-check` after pushing a merge of the base (in a run, with the briefing's flags) and runs a pass only when it asks for one; in attended work, `build-ticket` runs `WF merge-check --fetch <PR> --json` then for its review reasons only. A review never carries over when a counted record since the last round names the head itself. The `merge-check` skill's `--files` and `--commits` rows name the new fields, and its answer names `head_hashes`.
- Tests: `tests/test_merge_check_carry_over.py`, with one test that hashes a change both ways (`review-record` on a temporary repository and `merge-check` on REST-shaped files from it); `tests/test_review_record_hashes.py`'s REST list moves to a helper they share, and `tests/test_light_review.py`'s pinned checklist line moves to the new one.
- **For projects updating:** nothing to do. A pull request reviewed with the vendored kit's older records keeps today's answer; `--files` and `--commits` given by hand need `sha`, `patch` and `parents` for the carry-over and the free pass, and without them the answer is today's. The mapping of git's statuses to GitHub's is checked by hand once on the sandbox (#286).

**Building with the small review: `Review: small` on tickets, the three build choices, and the glossary** (#260, from #255; answers 1, 2, 7, 12, 15, 18 and 22 on #253).

- **`review-panel` §7, "The small review":** one round, with Correctness, the security review where it applies, and the explorer only where it would run in any round. No Standards and no Spec reviewer. Its record is an ordinary round record (`--round 1 --reviewers correctness`, adding `security` and `explorer` when they ran). Fixes after it are Correctness passes under the pass cap, with no further rounds. Past the small threshold, the ticket gets the full panel instead (the light review in a 1-round run). The findings table moves to §9, so the planning review keeps §8.
- **`build-ticket`** reads `Review: small` on the ticket. The small review is allowed in attended work always, and in a run when the briefing's "Small review" line says on, a 1-round run included (unmarked tickets keep the light review there). Before reviewing, it measures the diff with `review-record --measure` (with the briefing's threshold in a run). Past the threshold, it runs the full panel and the PR body says the diff overruled the mark. The PR body's line above the findings table reads "Small review: one round, Correctness", with ", security" and ", explorer" when they ran. A light review or the full panel the person asked for wins over the mark.
- **`start` and `next`,** on a ticket marked small, offer **Build it now (Recommended)** (the small review), **Build it with a light review**, then **Build it with the full panel**, before "Leave it ready for later" and "Next item". On an unmarked ticket the choices are as before.
- **Planning writes the mark:** flow §2's ticket rules, the guided start's quick ticket and its sorting ("Ready to build"), and the build-ticket issue template's comment (`templates/github/ISSUE_TEMPLATE/build-ticket.md`) write or ask for `Review: small` only when the change should stay within the threshold and add no endpoint, table, screen or setting. Removing the line opts the ticket out. Flow §3 names the small review.
- **The glossary's "Review panel"** names both: the small review (one round of Correctness for a ticket marked small) and the light review (asked for, with no walk-through of the screens). The light review is no longer called "for small changes" anywhere, so "small" means only the mark and the small review; what the light review does is unchanged.
- Tests: `tests/test_small_review_build.py`; the pinned wording in `tests/test_light_review.py` ("writes a build ticket on the spot") and `tests/test_light_review_offers.py` (the glossary's "the light review, asked for") moves to the new wording.
- **For projects updating:** nothing to do. Tickets written before this change carry no mark, so they are built as before. The update brings the issue template's new comment (when to add a `Review: small` line; the template writes no mark itself) into `.github/ISSUE_TEMPLATE/build-ticket.md`, as `update-workflow` does for the files set-up copied once.

**Review records name the hashes of the pull request's own changes: `diff=` and `lines=`** (#258, from #255; answers 4, 11, 13, 23 and 24 on #253). The record side of a free base merge; `merge-check`'s carry-over is #261.

- **`workflow review-record`** computes them for `--kind round` and `--kind pass` from `--commit`, never the working head: the diff from the merge base of `origin/<base>` to that commit, the base fetched first (`--base B`, else the profile's `project.base_branch`; if the fetch fails, the `origin/<base>` already here, with a note). A commit not in the repository, no repository, no `origin/<base>` or an unreadable profile without `--base` gives `unknown` for both, with a note on standard error: it never refuses, and standard output stays exactly the record.
- **The record's fields:** `diff=<64 hex> lines=<64 hex>`, each `unknown` when it can't be computed, between the reviewers and the result, on round and pass records only, never on spec records. The reader takes records with or without them.
- **The definition,** in one place (`scripts/workflow/own_changes.py`'s `of_files`, taking each file's path(s), status, blob SHA and patch as GitHub's REST list gives them, for #261 to reuse): per file in path order, its path(s) and GitHub's status, then for `diff` each hunk's context, added and removed lines (each `@@` line replaced by a fixed separator, `\ No newline at end of file` and `\r` kept), and for `lines` only the added and removed lines with their marks. A file with no hunks adds its blob SHA (none when removed); one with changed lines but no patch makes both `unknown`. Locally `git diff` is pinned whatever the configuration or the environment says (no external diff or textconv, Myers, 3 lines of context, renames within git's default limit and never copies, UTF-8 paths, a submodule as its `Subproject commit` lines and never left out, git's default size for a binary file, and the attributes of the commit itself on git 2.40 and later, never a global or the system's file); a diff driver's `binary` setting in the configuration and `.git/info/attributes` still count. A type change, which git shows as a removal and an addition, is one `changed` file with both hunks.
- **`review-panel`** says to add `--base <branch>` where the pull request's base isn't the profile's, and its reviewers' diff takes the same base. `--base` given twice is refused, as the other flags are.
- **The fetch never waits for git's own credential prompt:** `review-record`'s git runs with `GIT_TERMINAL_PROMPT=0` and no standard input, so a fetch that needs credentials fails at once and falls back as above (`--measure` too). An ssh passphrase prompt is ssh's own and isn't stopped.
- **`--base ""`** is no longer read as the profile's base: on a record it gives `unknown` for both hashes with the note "isn't a branch's name", and `--measure` refuses it.
- Tests: `tests/test_review_record_hashes.py`; the exact record lines from made-up commits in `tests/test_review_record.py` now end `diff=unknown lines=unknown`.
- **For projects updating:** a kit older than this change drops records with the new fields, so its `merge-check` reads such a pull request as unreviewed: update every checkout that runs `merge-check` together.

**Runs and the small review: the charter's `review.small`, pass cap and small threshold, the presets, and the briefing** (#259, from #255; answers 3, 5, 8, 15, 17 and 21 on #253).

- **The charter's `review`** takes four more keys, each optional and refused out of range: `small` (true or false), `passes` (0 to 10), `small_max_lines` (1 to 1000) and `small_max_files` (1 to 50). A missing `small` reads as off, with or without a `review` object, so a charter approved before this change behaves as approved; a missing `passes` or threshold value reads as the profile's (`presets.review_of`).
- **The presets** set `small`: Light and Normal on, Thorough off. The pass cap and the threshold are the profile's in every preset, so a charter written from a preset carries `small` and leaves them out.
- **`workflow charter reuse`** fills a missing `small` from the old charter's preset (Normal's without one), writing out the review it read as when it had none (with a note on standard error when no profile could be read, since that review is then the profile's defaults), so `charter diff` shows the change at the kick-off.
- **The limits question** names the small review and the pass cap, and each preset's `words` gives them ("small review on (at most 60 lines in 4 files outside tests); at most 2 Correctness passes"). **The one page** (`charter markdown`, `charter splice`) gains "**Small review:**" and "**Pass cap:**" lines, and names a small review that differs from the preset's (an old charter's, read as off, included), a changed pass cap or threshold beside it ("**Normal**, changed: the small review off, 5 passes"). The small review's line names the UI explorer only where the run has one.
- **The ticket-session briefing** (`templates/ticket-session-prompt.md`, `workflow render`) gains "**Small review:**" (on or off, with the threshold and the `review-record --measure` command to measure against it) and "**Pass cap:**" lines, and its `merge-check` command carries `--review-passes`, `--small-max-lines` and `--small-max-files` with the charter's values.
- **`build-ticket`**'s step 3 `merge-check` adds `--small-max-lines <L> --small-max-files <F>` from the briefing, beside `--review-rounds` and `--review-passes`; **`conductor`**'s "PR open, not merged" row, and "A ticket at the cap" that runs it, pass the same three flags with the charter's values, and its kick-off says what `reuse` fills in. The `merge-check` skill no longer says briefings carry none. `docs/charter.md` names the new keys, what an old charter reads as, and the presets' `small`.
- Tests: `tests/test_charter_small_review.py`; `tests/test_charter_presets.py`'s pinned preset and `review_of` values gain the new keys, and its one page for a review without `small` names the small review off; `tests/test_merge_check_passes.py`'s pinned "A ticket at the cap" names the flags.
- **For projects updating:** nothing to do. A run approved before this change keeps the small review off; a new run's kick-off from it shows the small review turned on by its preset (off for Thorough). The briefing's `merge-check` line needs a vendored kit with `--review-passes` and the threshold flags, which this release has.

**`merge-check` judges the small review by the diff: the small threshold, `past_small_threshold`, and `review-record --measure`** (#257, from #255; answers 1, 5, 6, 9, 14, 16, 19 and 20 on #253).

- **The settings.** `run.small_max_lines` (default 60, from 1 to 1000) and `run.small_max_files` (default 4, from 1 to 50) in the profile, refused outside those (`templates/profile.toml`, `docs/profile.md`). "Within the threshold" means at most both.
- **What counts.** Only files outside tests: a test file is a path matching one of the profile's suites' `files` globs, matched as path patterns (`*` stays within a folder, `**` crosses folders), and a rename is a test only when both its paths match. With no suite globs, every file counts. Lines are each counted file's additions plus deletions; a rename is one file.
- **`workflow merge-check`** reads each file's status, additions and deletions (`--fetch` already gets them from GitHub's REST list), and takes `--small-max-lines N` and `--small-max-files N`, defaulting to the profile's; `--json` gives them as `small_max_lines` and `small_max_files`, and the measured diff as `small`. When the pull request has a counted round and none of them ran `spec`, the diff must be within the threshold: past it, the new reason `past_small_threshold` replaces every other review reason, with action `review` and `next: full_round`, a round allowed past the round limit. Within it, a round that isn't clean counts as the last allowed one (`next: pass`), and so does that full-panel round. A light review's round 1 runs `spec`, so its later rounds are judged as before. With no counted round the answer stays `no_review`, and the counts aren't needed; where they are and a file has none, or a file on a test path has no status (gh's and GraphQL's lists may name none, so a rename into tests can't be told), it says it couldn't read `--files`.
- **`workflow review-record --measure --commit <sha> [--base B] [--small-max-lines N --small-max-files N]`** writes no record: it fetches `origin/<base>` (the profile's base by default; if the fetch fails, the one already there, with a note on standard error), and prints only the commit's counted lines and files against their merge base, and whether they are within the threshold, counted as `merge-check` counts them (renames found, binary files at 0 lines).
- **The skill and the flow.** The `merge-check` skill's "Review it now" runs the full panel for `past_small_threshold` (the light review's shape for a 1-round run's pull request), never a Correctness-only round; its `--files` row names the fields, and it tells a person checking a run's pull request to pass the charter's threshold. Flow §4's item 4 names the condition.
- Tests: `tests/test_small_review.py`, and `past_small_threshold`'s scenario in `tests/test_merge_check.py`.
- **For projects updating:** nothing to do. A pull request reviewed only by rounds without Spec (Correctness alone) now needs its diff within the threshold, and `--files` given by hand needs each file's `additions` and `deletions`, and `status` (with `previous_filename` for a rename), as GitHub's REST list gives them.

**The conductor marks a ticket for another look when `past_small_threshold` comes beside an unreadable profile** (#295, from #257's finding 30 on #289).

- **Marked too.** Step 2's "A ticket at the cap" now marks a `needs-human` ticket in the run's state (`cap_unknown_at`) when its `merge-check` gives `past_small_threshold` beside a "couldn't read" reason for the profile, as it already did for `passes_used_up`. The test globs come from the profile, so with it unreadable `merge-check` counts test files as well (the conductor gives the threshold itself as flags), and a pull request at its pass cap could read `past_small_threshold` instead and go unmarked. Without that "couldn't read" reason, `past_small_threshold` marks nothing. Step 2's look again is unchanged, as is when the mark goes; it still never keeps the run going on its own.
- Tests: `tests/test_merge_check_passes.py`, including one of `merge-check` itself, run with the conductor's flags: a small review at the cap, whose code alone is past the default threshold but within the flag's and whose diff is mostly tests, reads `passes_used_up` with the profile, and `past_small_threshold` without it.
- **For projects updating:** nothing to do.

**The conductor at the pass cap with its own profile unreadable: the ticket is looked at again, and a crashed session is retried** (#283, from #281's last Correctness pass).

- **Looked at again.** When `merge-check` says `passes_used_up` beside a "couldn't read" reason for the profile, whether the ticket is at the cap can't be told, so it takes the usual "Labelled `needs-human`" row. Before, nothing looked again once the profile read, unless the owner had been asked. Now a ticket labelled `needs-human` at `passes_used_up` with the profile unreadable is marked in the run's state (`cap_unknown_at`, a new optional ticket field `workflow state` accepts), and step 2 begins by running the definition again on each marked ticket, before "Stop now" and "Done" (and "Stop the run" does before its report); once the profile reads, the ticket takes the steps for a ticket at the cap, or stays with the row it took. The mark goes when the ticket is queued again or its pull request is no longer open, and it never keeps the run going on its own. A stuck ticket out of tries, labelled `needs-human` by the conductor, and the "Labelled `needs-human`" row go through the definition too.
- **A crashed session is retried.** The pass-cap row's stuck-session clause (label it `needs-human` instead of a retry) now applies only to a ticket at the cap, as step 2 defines it; with the profile unreadable, the stuck row's retry applies.
- Tests: `tests/test_merge_check_passes.py`.
- **For projects updating:** nothing to do.

**The conductor at the pass cap: one definition of "a ticket at the cap", and "couldn't read" never hides it** (#281, from #256's last Correctness pass).

- **One definition.** Step 2 gains "A ticket at the cap": `merge-check`, run as the "PR open, not merged" row runs it, says `passes_used_up` with no "couldn't read" reason for the profile. Beside any other "couldn't read" reason (an unreadable try-it link, say) the cap still counts, since `merge-check` keeps judging the review when an input can't be read; before, the run then waited on the owner until its end time. A "couldn't read" reason for the profile is the exception: the profile holds the cap itself, so `merge-check` then judges against the default of 2. A ticket with no open pull request is never at the cap, and with the profile unreadable whether one is can't be told, so it isn't taken as the cap: it keeps waiting, and an answer requeues it as usual.
- **One set of steps,** each taken only where it isn't done already: its labels stay (`needs-human`, never claimed again), `asked_at` is cleared, its `for_owner` line becomes "#n reached its pass cap (#PR): see its review records and PR body", the ticket gets the "One more pass" note, and the change is named on the tracking issue at once (for an answer in chat between check-ins, in a comment of its own).
- **Every path uses it:** step 2's "Waiting on the owner", "Asking about a `needs-human` ticket" (which now takes the steps rather than only not asking), the "When the owner answers" exception and the pass-cap row (whose ticket, labelled by its session at the cap, takes the steps instead of the "Labelled `needs-human`" row's question and line) point to it, so the answers path now updates `for_owner` too and keeps the profile's exception.
- Tests: `tests/test_merge_check_passes.py`, including two of `merge-check` itself: the cap beside an unreadable try-it link, and beside an unreadable profile.
- **For projects updating:** nothing to do.

**The pass cap: at most `run.review_passes` Correctness passes after the last round, then the owner decides** (#256, from #255; answers 3, 10 and 21 on #253).

- **The problem.** Review rounds were capped, but the Correctness passes after the last round weren't: every later commit needed a clean pass, and a review that kept finding something new looped until the session stopped.
- **The setting.** `run.review_passes` in the profile: default 2, a whole number from 0 to 10, refused outside it, as `run.review_rounds` is (`templates/profile.toml`, `docs/profile.md`).
- **`workflow merge-check --review-passes N`** (0 to 10), beside `--review-rounds`, defaulting to the profile's; `--json` gives it as `review_passes`. Every counted pass record after the last counted round counts, on any commit of the pull request, repeated ones on one commit included. Where a pass is what comes next (`review_not_clean` with `next: pass`, `pass_not_clean` or `review_stale`) and the cap is reached, the new reason `passes_used_up` replaces them, with action `review` and `next: owner`: the pull request waits on the owner. With `--review-passes 0`, any change after the last round stops there at once. A round that isn't clean below the round limit still asks for another round, and a clean pass on the head is still ready.
- **The skills and the flow.** The `merge-check` skill offers "One more pass" with `passes_used_up`, beyond the cap since the person chose it, and tells a person checking a run's pull request to pass `--review-passes`. `review-panel` §5 stops passes at the cap. `build-ticket` passes `--review-passes` (the briefing's pass cap, else the profile's) and takes `passes_used_up` as `needs-human`, with the open findings in the PR body; so does the conductor's row for a pull request that isn't ready. The conductor never asks the owner about a ticket at the cap, clears `asked_at` on one asked about before its pull request reached the cap (checked each check-in in step 2, before the run counts as waiting on the owner), and an answer that comes anyway doesn't requeue it and clears its `asked_at`, judged by the merge rule's `merge-check` (with `--charter` and `--review-rounds`). The ticket-session briefing's "Stopping" list and flow §5 name the cap; flow §3 names it, and §4's item 4 names it within the item.
- Tests: `tests/test_merge_check_passes.py`, and `passes_used_up`'s scenario in `tests/test_merge_check.py`; `tests/test_merge_check_rounds.py`'s "the latest pass on the head decides" now allows 3 passes, so it still checks what it did below the cap.
- **For projects updating:** nothing to do. With no `run.review_passes`, the cap is 2: a pull request whose head already has 2 passes after its last round, and needs another, now waits on the owner. So does one whose branch was brought up to date after its passes reached the cap, until a merge of the base that leaves the PR's own changes alone needs no pass (#261).

**The "Use a merge queue" upgrade: `merge_group` in the workflows first, then the ruleset's merge-queue rule with "up to date" off** (#247, part of #243).

- **The ruleset writer.** `workflow protection --merge-queue ruleset.json --doctor doctor.json [--timeout MINUTES]` prints the `PUT` that adds a `merge_queue` rule to the ruleset: merge method `MERGE`, grouping `ALLGREEN`, at most 5 entries built and 5 merged at once, a minimum of 1 and no wait, and a check timeout of twice the base's longest recent CI run (doctor's `merge_queue.signals.ci_minutes.longest`), at least 60 minutes (60 with no history) and at most 360, or the owner's `--timeout` (above that run, at most 360; only 360 when it ran 359 or more). The same change turns "up to date" off and keeps the required checks. It refuses unless doctor's `merge_group` verdict is clean, naming the workflows and checks not ready, and refuses a ruleset that requires no checks or isn't active. It sends nothing.
- **`--require-checks`** leaves "up to date" as it is when the ruleset has a merge-queue rule (a new checks rule beside the queue gets it off), and doctor's `require_checks` fix says so when the ruleset holding the checks has the queue. `docs/enforcement.md` asks for "up to date" only where there is no queue.
- **The `upgrade-setup` skill's "Use a merge queue"** (`use_merge_queue`, offered by doctor through `check-setup`, or when asked), in an attended session and never while a run is in progress: first a pull request adding `merge_group:` beside `pull_request:` in each workflow doctor's check names, which the owner merges; then, once the check is clean on the base, the settings shown to the owner and chosen there, the ruleset change with `gh` after one confirmation on the owner's computer or click by click, and the read-back through doctor. "Require these checks" and its read-back no longer turn "up to date" on, or give its click, beside the queue.
- **The kit's CI template** (`templates/github/workflow-kit.yml`) runs on `merge_group` too.
- **Docs:** `docs/protection.md` gains "The merge queue" (its availability, the settings, "up to date" off, and a note for path-filtered CI: diff the merge group's `base_sha..head_sha`); the glossary gains "Merge queue", and its "Merge" entry says "Merge it now" joins the queue there, other entries trimmed to stay under 6,000 characters.
- Tests: `tests/test_protection_queue.py`, `tests/test_upgrade_merge_queue.py`.
- **For projects updating:** the kit's update brings `merge_group:` into `.github/workflows/workflow-kit.yml` (it does nothing without a queue). Nothing else changes until the owner takes "Use a merge queue".

**Doctor and check-setup suggest a merge queue where it fits, and check the base's workflows for `merge_group`** (#246, part of #243).

- **New inputs.** `workflow doctor` takes `--org` (GET `orgs/<owner>`, for a private repository's plan), `--commits` (the base's commits, one page), `--ci` (the check runs of the base's last commits and of recent pull requests' heads, each with GET `actions/runs?head_sha=<sha>` for the workflow behind it) and `--now`. Without the files it reads them with `gh` (GETs, one page each), and only where a line needs them. It reads the workflow files with `git` as they are on `origin/<base>`, never the checkout's.
- **The suggestion** (`github.merge_queue`): a note offering "Use a merge queue" (`use_merge_queue`), never a gap, where the base is protected with required checks and the queue is off, for a public or internal organisation repository, or a private one on GitHub Enterprise Cloud. For a private one whose plan can't be read, it says the queue needs Enterprise Cloud and to check first. A personal repository, a private one on another plan, or one with nothing required gets no line. With the queue on, the line says so.
- **The `merge_group` check** (`github.merge_group`), over only the workflows behind the required checks, found through their check runs and workflow runs. Each `on:` is read line by line with no YAML library: one it can't read, or one that isn't a mapping with `pull_request:`, is `cant_check`; so is a required check from another CI service (a check run from another app, or a commit status on the base, with GitHub's rule that it must run on pushes to `gh-readonly-queue/<base>`), and one with no run seen, named. A missing trigger, or a `branches` filter leaving out the base, is a gap. All of that holds with the queue on; with it off, the line is a note (its JSON keeps each state for the upgrade), so a queue nobody chose never fails `--strict`.
- **`github.up_to_date`** counts the merge queue as meeting it, and its fix never offers "up to date" then. A ruleset still keeping "up to date" on beside the queue is a note naming it; a merge-queue rule in an `unsure` ruleset is `cant_check` (on `github.merge_queue` when "up to date" is on anyway).
- **The signals,** in the suggestion's words and in `--json`'s new `merge_queue` (with the queue's state, its availability and the `merge_group` check's workflows and checks): CI's typical and longest time on the base (the longest run of a required check, on commits whose required checks have finished), the commits that reached it in the 7 days to `--now` (by first parents), and whether unattended runs are set up or one is in progress (`null` when it can't be told).
- **The `check-setup` skill** gathers the new inputs, shows the suggestion with the notes, and offers "Use a merge queue" with "Not now": recommended, with its reason, when CI takes 10 minutes or more and the base moved 10 or more times in the week or runs are set up; never while a run is in progress. The conductor's pre-flight fetches `origin/<base>` for it.
- Tests: `tests/test_doctor_merge_queue.py`.
- **For projects updating:** nothing to do. An organisation's repository with required checks gets the suggestion and the `merge_group` note; neither fails `--strict` while the queue is off. Otherwise the report is as before.

**The charter and the run's state with a merge queue: no waivers, and `workflow state drop` decides what to do with each answer to queueing a pull request** (#248, part of #243).

- **No waivers with the queue on.** `charter validate`, `charter questions` and `state init` take the queue's state as read, `--queue on` or `--queue off`. With it on, `validate` and `state init` refuse a charter with `merge.waived_checks` (every merge goes through the queue, and only a direct merge could take a waiver), and the merge question no longer asks about waivers: its note says "No waivers". With it off, or not given, nothing changes. The merge modes keep their names; `docs/charter.md` §5 says what each means with the queue.
- **The queue's state at kick-off** is recorded in the run state's `merge_queue` by `state init --queue`. `workflow state queue --body F --queue on|off --out F` prints `unchanged`, `changed` (with the old and new state) or `recorded` (when none was), and records what it was given, so a change is reported once. Over a charter with waivers, it adds that they no longer apply when the queue is on (at `changed` or `recorded`), and that they apply again when it changes to off.
- **`workflow state drop --body F --ticket N --head SHA --answer A --out F`** takes GitHub's answer to queueing a ticket's pull request: `202-enqueued`, `202-pending`, `200-waiting`, `200-merged`, `409`, `failed` or `refused`. It prints what to do: `in_queue`, `waiting`, `merged`, `retry`, `requeued`, `merge_base` or `needs_human`.
- **The rule.** A head's first `202-enqueued` is `in_queue`, and "already in a merge queue" is `waiting`. A later `202-enqueued` of a head in the queue means GitHub dropped it: the first drop on a head is `requeued`, a second `merge_base`, and any drop once the base was merged in `needs_human`, whatever the head. The other answers are `retry`, but a third `failed` on one head is `needs_human`.
- **On the ticket** it records the heads seen in the queue with their drops (`queue_heads`), the `failed` answers per head (`queue_failed`), whether the base was merged in (`base_merged`) and the last decision (`queue_result`).
- `docs/charter.md` says so. Tests: `tests/test_charter_queue.py`.
- **For projects updating:** nothing to do. Without `--queue on`, every charter and state command answers as before.

**`workflow merge-check` with a merge queue: "ready" means ready to queue, and the `merge-check` skill's "Merge it now" adds the pull request to the queue** (#245, part of #243).

- **The queue reader.** `protection.check` says whether a ruleset in force on the base (active, and one it can tell targets the base) has a `merge_queue` rule. A merge-queue rule in a ruleset it can't judge (`unsure`) is listed apart, for doctor to show, and never counts as a queue; so is one on `~DEFAULT_BRANCH` when the default branch is only taken to be the base (the pull request didn't give it). `workflow protection --json` is unchanged.
- **`workflow merge-check` with the queue on:** the queue meets flow §4.3 (up to date), so a branch behind the base is no reason and there is no `update_branch` action; a charter's waivers are refused (a `charter_refused` note), since every merge goes through the queue, and also where a ruleset may require one (an unsure merge-queue rule); the answer carries `queue: true` and a `queue` note that the rules are checked when it is queued and that a request made after that (changes requested, a new review thread) doesn't stop the merge. Its text says "Ready to queue". Every other rule is unchanged. A merge-queue rule in an `unsure` ruleset gets a `queue_unsure` note.
- **With the queue off,** every answer is as before, with `queue: false`.
- **The `merge-check` skill:** with `queue: true`, "Merge it now" checks again on the same head, then queues it with `gh api -i -X PUT repos/<repo>/pulls/<n>/merge-async -f merge_action=merge_queue -f sha=<head>` (#244's route; `-i` prints the status line), never `--admin` or `bypass_rules`. It says what GitHub answered: a 202 read through `merge-async/<uuid>` (`enqueued`: it merges once its group passes; `pending`: ask again shortly; `failed`: GitHub's message), 200 "already in a merge queue", 200 merged, 409 (another request pending), and 400, 403 or 422 (GitHub's message). A dropped pull request, asked about again, is offered "Merge it now" again.
- **Flow §4:** item 3 reads "level with the base, or met by the merge queue where the ruleset requires one"; item 1 says waivers don't apply with the merge queue on; the merging paragraph says that with the queue the rules are checked when the pull request is queued.
- Tests: `tests/test_merge_check_queue.py`.
- **For projects updating:** nothing to do. Without a merge-queue rule on the base, nothing changes.

**The guard lets a session add its pull request to a merge queue through `merge-async`, pinned, and never merge directly** (#244, part of #243).

- **The route.** `gh api -X PUT repos/<repo>/pulls/<n>/merge-async -f merge_action=merge_queue -f sha=<sha>` is the one way the kit queues a pull request. Ticket sessions may now call it (it joins their API allow-list), pinned like their merges: `sha` must be the ticket branch's head, written out in full. Conductor and attended sessions need a `sha` that is a full commit sha, or one the shell fills in.
- **In every role** (asked in attended sessions, refused where nobody is asked): `bypass_rules` in any form (`-f`, `-F` on any `gh api` write, an `--input` body or a heredoc on stdin), any `merge_action` but `merge_queue` (none means `default`, which merges directly when no queue is required), an `--input` body or `@file` field, a query string or `#` on the path, a field name that isn't plain, words `xargs`, `eval`, `sh -c` or an unquoted expansion add, and a quoted expansion that may be a flag of its own (`"$E"`). The path is read by its last part, however it is spelled (a full URL, `%`-escapes, `//`, `repos/$REPO/…`). An attended session's `curl` to `merge-async` is asked unless it sends one JSON body that queues it with a `sha` and no `bypass_rules`.
- **Today's rules are unchanged:** merges, auto-merge and update-branch. `docs/enforcement.md`'s merge pins and its every-role list gain the route.
- Tests: `tests/test_guard_merge_async.py`.
- **For projects updating:** nothing to do.

## 0.1.15

**A spec published from a Claude Code cloud session can get its spec records.** One fix, #250: the spec's hash leaves out the footer those sessions' GitHub tools add to every issue body. Its own note is below.

- **For projects updating to 0.1.15:** nothing to do, unless a spec record was made from a `spec.md` that itself ended with that footer: that spec reads as unreviewed until it is reviewed again.

**A spec published from a Claude Code cloud session can get its spec records: the body's hash leaves out the footer those sessions add** (#250, found publishing #243; #233's records, #235's read-back check).

- **The problem.** In a Claude Code cloud session, every write of an issue body, through the GitHub MCP tools or `gh api`, ends with a blank line, `---` and `_Generated by [Claude Code](https://claude.ai/code)_`, and editing the body back appends it again. So the planning review's read-back check (`review-panel` §8) never matched the reviewed `spec.md`, no spec record was posted, and `workflow ready` noted every such spec's tickets as unreviewed.
- **The fix.** A spec's body hash (`reviews.plain_body`, used by `workflow review-record --body` and by `reviews.spec_reviewed`) leaves out exactly that footer at the very end of the body, after the whitespace there, once or repeated. The read-back check then matches whether or not `spec.md` carries the footer. Any other difference still changes the hash and blocks the records: another footer, `---` straight after the text (a heading, not a rule), text after it, or any edit beside it. A body that is nothing but the footer is refused as empty, and the refusal says so.
- **`review-panel` §8** says so: the footer needn't be in `spec.md`, any other difference counts, and each line of the check must print a `body=` line (two refusals are no match).
- Tests: `tests/test_spec_review_record.py`, `tests/test_planning_review.py`, `tests/test_ready_spec_note.py`.
- **For projects updating:** nothing to do, unless a spec record was made from a `spec.md` that itself ended with that footer: it names the old hash, so that spec reads as unreviewed until it is reviewed again.

## 0.1.14

**Planning is reviewed before it's offered or published, and `workflow ready` notes a ticket whose spec has no clean review.** Spec #232's three tickets: spec review records keyed to the spec's text (#233), the planning review in the flow, the review panel and the guided start (#235), and `workflow ready`'s note, shown by `next`, `start` and the conductor's kick-off (#234). Each change's own note is below.

- **For projects updating to 0.1.14:** nothing to do. `SPEC_REVIEW_SINCE` is this release's date, 2026-10-23, so specs created before it are never noted as unreviewed and updating adds no notes.

**`workflow ready` notes a ticket whose spec has no clean review, and `next`, `start` and the conductor's kick-off show it** (#234, part of #232).

- **The note.** A ready ticket whose parent spec (its sub-issue link, or the first ref on the first line under its `## Parent` heading, when it is in this repository; the spec labelled `spec`) has no clean spec record (#233) for its current body from an account with write access gets "spec #<n> has no clean review: check it before building". It's a warning, never a block: the ticket stays ready, as with the protected-path note. A not-clean record, a clean one for an older body, or one from an account without write access leaves the note.
- **Old specs aren't noted:** specs created before `SPEC_REVIEW_SINCE` (in `scripts/workflow/issues.py`, this release's date) never are, so updating the kit adds no notes. A spec whose creation date can't be read counts as new, so the MCP route's issues file gives each issue's `created_at` (`next` and `start` list it). **The release that brings this in sets `SPEC_REVIEW_SINCE` to its own date.**
- **Where the comments come from:** a spec's `comments` in the `--issues` file when it carries them as a list (the MCP route), else `gh api`, only for the parent specs of the ready tickets shown, once each (a spec with no comments isn't fetched). The authors' permissions come from `--permissions F` (new, any shape `merge-check --permissions` takes) or `gh api`, as `merge-check` reads them, each login once. Once `gh` is missing or times out, it isn't called again in that run. When either can't be read, or the parent isn't in the issue list at all, the note says so: "spec #<n>: couldn't read its reviews (<why>)".
- **The skills:** `next` and `start` show the note beside a ticket when they offer it; the conductor's kick-off lists those tickets beside the protected-path ones, for the owner to keep or exclude by spec (excluding a spec excludes all its open tickets, blocked ones too); a ticket of an unreviewed spec noted later in the run is named in that check-in's comment. `docs/charter.md`'s readiness line says so.
- Tests: `tests/test_ready_spec_note.py`.
- **For projects updating:** nothing to do.

**Spec review records: `workflow review-record --body F` keys a spec's review to its body's SHA-256** (#233, part of #232).

- **The writer.** `workflow review-record --kind spec --round N --body spec.md --reviewers spec,correctness --clean` (or `--not-clean`; `--body` alone means `--kind spec`) prints the record a spec's review round posts on the spec's issue: "Spec review round 1 on body `9c1e4b2`: clean. Reviewers: Spec, Correctness.", then a machine line naming the body's SHA-256 in a field of its own (`body=<64 hex>`, in place of `commit=`), so a commit-keyed record and a spec record are never confused. The body is read from the file the session publishes, its line endings made `\n` (GitHub gives a body back with `\r\n`), and a byte order mark at its start and the whitespace at its very end left out, so an edit after the review makes the spec read as unreviewed again.
- **Refused in words:** a body file that's missing, can't be read, isn't UTF-8 text or is empty (nothing but whitespace or a byte order mark); `--commit` and `--body` together; a round or pass with `--body`, or a mistyped `--kind`, before the file is read; a spec record without one; reviewers other than `spec` and `correctness`.
- **The reader.** `reviews.read` and `records_in` return spec records with their hash (`body`) and author; a line whose hash isn't 64 hex characters is skipped. `reviews.spec_reviewed(records, body)` says whether the latest spec record for that body's hash is clean.
- **Round and pass records are unchanged,** and `workflow merge-check` reads only those: a spec record on a pull request is no review of its code.
- Tests: `tests/test_spec_review_record.py`. The review panel's text comes with the planning-review ticket (#235), and `workflow ready`'s note with #234.
- **For projects updating:** nothing to do.

**Planning is reviewed before it's offered or published: the planning review of a map decision's ADRs, a spec's draft and a spec session's ADRs** (#235, part of #232).

- **The flow.** §1: after a decision is resolved, the owner's answers are posted on the decision ticket, each question with the answer quoted word for word (sensitive data left out and marked as left out); the ADR and glossary are written on a branch and reviewed until clean; only then is the ticket closed, the map updated and the pull request offered with its review records, an order that replaces `wayfinder`'s own. §2: once the seams are agreed, the answers (the seams among them) go on the item's issue or the map's Destination item (otherwise the spec's first comment); the spec's draft is reviewed before it's published and published as is, with its spec records on the spec issue; and a spec session's ADR or glossary pull request is reviewed before it's offered. Both checklists gain "answers posted verbatim; reviewed until clean, records posted". §4: the owner's hand merge of a planning pull request relies on the review made before it was offered; no check enforces it.
- **The review panel** gains "The planning review" (§8): Correctness, briefed for a document (facts against the code, contradictions with other ADRs, the project's safety rules), and a Spec reviewer with its own brief that reads the record against the owner's answers word for word. No Standards reviewer, no explorer; both run every round, up to the profile's `run.review_rounds`, and a spec whose last round wasn't clean is published fixed, its handover saying it reads as unreviewed. The session fixes wording, facts and omissions; a fix that would change what a decision means is put to the owner first. A pull request posts round records on its commit once it is open, a spec posts spec records keyed to its body (`workflow review-record --kind spec --body`), and the published body is read back and its full hash checked before the records go on it, so a footer added on the way is caught. An edit after publishing (in the guided start, "Edit the spec first" or "Add to an existing issue") gets another planning round before tickets are written from it; a Destination item's spec is checked against the map decisions it draws on too.
- **The guided start's** Spec and Map steps post the answers word for word and review before publishing or offering; the glossary's "Review panel" says specs and map decisions are reviewed too; the README's interview, `/to-spec` and "Work through it" tell the new order.
- Tests: `tests/test_planning_review.py`.
- **For projects updating:** nothing to do. The vendored flow and skills change with the update's pull request.

## 0.1.13

**Attended sessions plan new work before they code.** Spec #221's two tickets: the guided start's first-message text names its three exceptions exactly, every later message of an attended session gets a one-line reminder to plan new work first, and a message that only mentions the conductor gets the guided start instead of the flow. Each change's own note is below.

- **For projects updating to 0.1.13:** nothing to do. `guided_start = false` in the profile turns the reminder off along with the guided start.

**Attended sessions plan new work before they code: a narrower first-message text, and a reminder at every later message** (#222, part of #221).

- **The first message.** The guided start's text from the context hook now names the `start` skill's three exceptions exactly: act straight away only on a question, a named issue, or one small change with an obvious place (on its own branch, with a pull request). Any other request for work (a feature, a change, a fix whose cause isn't known, or more than one thing) is split into items and the plan agreed first. It no longer says to "just do" one clear thing.
- **Every later message** of an attended session gets a one-line reminder: new work that isn't part of the plan or ticket already agreed in the session is split into items and agreed first; a question, a named issue or one small change may go ahead, and replies to Claude's own questions carry on. Not in ticket or conductor sessions, with `guided_start = false`, at a slash command, or when the message already brings the flow's context.
- **A resumed session** (the first-message marker lost after a restart) follows the reminder, which comes below the first-message text, instead of ignoring it.
- Docs: the `start` skill's step 0, the README's "What happens with your first message", the flow's "Starting", and `guided_start` in `docs/profile.md` and in the profile template's comment. Tests: `tests/test_plan_first.py`.
- **For projects updating:** nothing to do. `guided_start = false` turns the reminder off with the menu.

**Mentioning the conductor brings the guided start, not the flow** (#223, part of #221).

- **A message that only mentions the conductor** ("why did the conductor stop?", "the conductor skipped #12", "Conductor run on Friday never woke up") no longer brings the flow's text from the context hook: as a first message it gets the guided start, and later the reminder, like any other message. Nor do "can ticket sessions run unattended?" and "run the tests unattended".
- **Asking still brings the flow:** working on a named map ("work the doctor map"), asking to start, restart, run, resume or stop a run or the conductor ("stop the run", "restart the conductor", or a line that is only "conductor resume", "OK conductor, stop" or "conductor resume #45"), the `/conductor` command, and the conductor's own wake ("conductor: wake (a ticket session finished)"). "Run the backlog unattended", the conductor skill's own example, now brings it too: it never did before.
- Tests: `tests/test_conductor_mention.py`.
- **For projects updating:** nothing to do.

## 0.1.12

**`workflow doctor` and "Check the set-up", try-it links, "Require these checks", the quickstart, and the release gate.** Everything merged since 0.1.11: the build tickets of specs #33 to #38 and #41, and the infra fixes they found. Each change's own note is below.

- **For projects updating to 0.1.12:**
  - the update rewrites the guard's hook entry in `.claude/settings.json` (`onFailure`, the timeout, the matcher), keeping the project's own hooks: use Claude Code v2.1.295 or later (see #57);
  - nothing else: every other change below needs nothing from an updating project.

**The release gate compares Claude Code's tools with the tools the guard sees** (#92, part of #36).

- **A new check, "The tools comparison",** after the ruleset's refusal: the `release-gate` skill reads Claude Code's tools reference (https://code.claude.com/docs/en/tools-reference) and the list of tools the guard sees in the candidate's `docs/enforcement.md`, and notes every tool on the reference that isn't on the list.
- **A missing tool that runs a command or a program** (as `Bash`, `Monitor` and `PowerShell` do) fails the gate, naming it: the fix is a guard change and a fix release. Any other missing tool is a note below the report's table, never a fail. A reference that can't be read fails the gate as "couldn't check".
- **The list is the guard's:** a test reads the list in `docs/enforcement.md` and the guard's matcher, in a vendored project's settings and in the plugin's hooks file, and fails when one names a tool the other doesn't.
- Docs: `docs/enforcement.md` says the gate runs this step; `CONTRIBUTING.md`'s list of what the gate checks. Tests: `tests/test_release_gate_skill.py`. Running it for real is owner task #94.
- **For projects updating:** nothing to do. The skill is the kit repository's own and never ships.

**The release gate runs `workflow doctor --strict` on the sandbox** (#91, part of #36).

- **A new second check, "The set-up check",** after the update with CI green and before the guard's refusal: the `release-gate` skill gathers the sandbox's rulesets, repository settings, environments, `workflow:run` issues, the base branch's checks and the open pull requests by following the candidate's own `check-setup`, writes them to files outside the checkout, and runs the candidate's `workflow doctor --strict` on the sandbox branch with them and the Claude Code version the report records (read once, never a second `claude --version`).
- **It passes on exit 0;** notes never fail it, except the one saying whether a run has been made couldn't be read, which `check-setup` counts as unchecked. Any other exit fails the gate like the other checks, with doctor's text output quoted below the report's table; exit 2, a wrong command, is fixed and run again first. A gate run on a Claude Code older than doctor asks for fails here.
- Docs: `CONTRIBUTING.md`'s list of what the gate checks. Tests: `tests/test_release_gate_skill.py`. Running it for real is owner task #94.
- **For projects updating:** nothing to do. The skill is the kit repository's own and never ships.

**"Finish the release gate": the sandbox pull request updated from the release tag, then merged** (#90, part of #36).

- **Asked "finish the release gate"** once the release has published, for the version or the release pull request #N, the `release-gate` skill's new section 5 checks the GitHub release `v<version>` exists, then finds the gate's sandbox pull request from `release-gate/<version>`. Without the release, or when that pull request is missing, merged already, or closed (by a failed gate or a later version's gate run), it says so and stops.
- **The update from the tag,** as the candidate was applied: the tag's checkout as `vendor update --kit`, Matt Pocock's skills at the pinned SHA when the branch's lock records them. Only the lock's `kit_sha` and `kit_version` may change. Any other file stops it loudly, naming the files on the sandbox pull request, which stays open, with nothing pushed and the sandbox's `main` untouched.
- **Then** the sandbox pull request's description says it holds release `v<version>`, keeping its earlier lists, its CI goes green, and it merges with a merge commit pinned to its head once the pull request shows the pushed commit. `docs/spike.md` isn't touched.
- **Finish a version before gating the next:** a gate run closes every open `release-gate/` sandbox pull request, an unfinished pass among them.
- Docs: `CONTRIBUTING.md`'s release section ends with finishing the gate. Tests: `tests/test_release_gate_skill.py`. Doing it for real is owner task #94.
- **For projects updating:** nothing to do. The skill is the kit repository's own and never ships.

**The `release-gate` skill: a release tried on the sandbox before it publishes** (#89, part of #36).

- **Asked "run the release gate on PR #N"** in a cloud session on the kit's repository, the skill reads the release pull request's exact commit and its `VERSION`, checks it out outside the working tree, and updates the sandbox to it on a `release-gate/<version>` branch, through the candidate's own `update-workflow` with `vendor update --kit` pointing at the candidate (Matt Pocock's skills at the kit's pinned SHA). It opens the sandbox pull request, naming the candidate commit and the release pull request. It runs only on the kit's own branches, never a fork's, since it runs the candidate's code with push access to the sandbox.
- **The checks, in order:** the update with CI green; a ticket session in the sandbox's ticket environment told to push to `main`, refused by the guard with `main` unchanged; a push to `main` from a throwaway clone, refused by GitHub's ruleset. A failed check stops the gate and closes the sandbox pull request; a pass leaves it open until the release publishes.
- **The report:** one new comment on the release pull request per run, with the table (check, result, evidence), the Claude Code version, the agents' marker and, last, `release-gate: pass <sha>` or `release-gate: fail <sha>`, which the "release gate" check (#88) reads.
- **It never ships:** it lives in the kit repository's own `.claude/skills/release-gate/`, not `skills/`, so neither a vendored copy nor the plugin has it. Docs: `CONTRIBUTING.md` says how to run the gate and that the repository's own `.claude/skills/` never ships; `docs/spike.md` says the gate re-proves rows 4 and 5 at every release. Tests: `tests/test_release_gate_skill.py`, including the skill's example reports read by #88's script. Running it for real is owner task #94.
- **For projects updating:** nothing to do.

**The "release gate" check** (#88, part of #36).

- **A check named "release gate" on every pull request** of the kit's repository (`.github/workflows/release-gate.yml`). A pull request that doesn't change `VERSION` passes at once, without reading comments or permissions. A release pull request passes only when the newest gate line for its head commit, `release-gate: pass <sha>` with the full SHA, comes from a comment carrying the agents' marker by an account with write, maintain or admin permission; a later `release-gate: fail <sha>` for the same commit wins. Or when the skip is allowed: the `release-gate-skipped` label, a "Gate skipped because …" line in the description and a "Release gate skipped because …" line in the new version's CHANGELOG entry, never twice in a row (read from the base branch's CHANGELOG, which the pull request can't edit).
- **The decision** is `.github/scripts/release_gate.py`, beside `release.py`, standard library only: fed JSON and text files, it prints `pass: …` or `fail: …` with the reason. It has its own reading of write access, not merge-check's, so it never imports the kit it judges. The workflow runs the base branch's copy of it and never checks out the pull request's code; the workflow file itself runs as the pull request has it.
- **The workflow** reads the pull request, its files, comments, labels and description, each marked comment's author's permission, the CHANGELOG and `VERSION` (at the head and at the base) from the API when it runs, never from the event's payload. A read that fails, other than a file that isn't there, fails the check; an author whose permission can't be read is left out. A comment on a pull request re-runs its latest `release gate` run for the head commit, one at a time per pull request. Read access for the job; `actions: write` only for the re-run.
- Docs: `CONTRIBUTING.md`'s release section describes the check and how to skip it. Tests: `tests/test_release_gate.py`. Making it a required check is owner task #93.
- **For projects updating:** nothing to do. The check runs only on the kit's own repository.

**"Add try-it links": `upgrade-setup`'s fourth path** (#116, part of #41).

- **The path** (offer `add_try_it_links`) takes the owner through `docs/previews.md`'s seven steps in Cloudflare one screen at a time, worded by experience, with a step already done (a repository Cloudflare already reports on, a link that already built, the Wrangler lines already there) shown as done with "Continue". With `[sensitive]` patterns, Cloudflare Access comes straight after Preview URLs, confirmed by the owner, and the path says plainly that the kit can't check it; without Access it stops, with no previews. The base branch's Wrangler config must keep the app off the internet (`workers_dev = false`, and `preview_urls = false` with sensitive data until Access is confirmed), in a small pull request of its own when it doesn't: before connecting, or first of all when the repository is connected already, saying plainly what is public now.
- **The proof pull request,** from a fresh branch, sets `[previews]` (`provider = "cloudflare"`, `on = true`, `access = true` only as confirmed) with the Wrangler lines step 6 needs, reads its own preview with `workflow preview`, and reports the link once it's `built`, or the failure with its fix from "When a build fails". A preview still running the old Build command gets a fresh branch rather than a retry. The profile is a protected path, so merging it is the owner's.
- **Offered** only from the quickstart's next steps, doctor's `add_try_it_links` offer and when asked. **`check-setup`** now hands the offer to the path, with "Not now", instead of naming it as text. Doctor's Previews notes (the offer, and a section turned off beside a Wrangler config) say to ask Claude to "Add try-it links".
- Docs: `docs/previews.md` and `docs/profile.md` no longer call the upgrade "to come"; the quickstart's bullet and the page say to ask Claude; `docs/enforcement.md` §5, the README's Step 6 and `docs/install.md` name it. Tests: `tests/test_add_try_it_links.py`.
- **For projects updating:** nothing to do. With a Wrangler config, ask Claude to "Add try-it links" when you want them.

**Every consumer reads the same try-it link: `merge-check`, the conductor and "How to try it", behind `[previews] on`** (#117, part of #41).

- **The gate:** only with the profile's `[previews] on = true` does anything run the preview reader. Otherwise nothing reads it, and `merge-check`'s note about the missing try-it link never blocks and names `docs/previews.md`, as before.
- **The `merge-check` skill** reads the link for the pull request's head with `workflow preview --fetch <n> --json` (or from files, without `gh`) into a file outside the checkout, and passes it as `merge-check --preview F`. It passes that file even when the reader fails: the file is then empty and the answer is "Not yet" (it couldn't read the preview), so a link that can't be read never reads as "Ready". A link that didn't build offers "Ask Claude to fix it", with "When a build fails" in `docs/previews.md`.
- **`workflow merge-check --fetch` reads the link itself** with previews on when no `--preview` is given, through the same reader, so a check run by hand gives the same answer as the skill and a run. A link it can't read is "Not yet" (it couldn't read the preview).
- **The conductor's merge row and `build-ticket` §6** read it before each `merge-check` (`.workflow/run/preview-<PR>.json`, one file per pull request, and `.workflow/preview.json`), and a ticket session's briefing says so: with `[previews] on = true`, read the profile each time.
- **`build-ticket`'s "How to try it":** with previews on, the pull request opens saying where the link will appear; at each check-in until it merges, the session reads the preview and, once it's `built`, edits "How to try it" to give the link and two or three things to try (and makes sure it does before merging on `ready`). A `failed` one is said plainly ("The try-it link didn't build for …") with its fix, from "When a build fails" in `docs/previews.md`; when the fix is a Cloudflare setting, no push fixes it, so the session names the owner's step and stops as `needs-human`.
- **`workflow merge-check`'s answers:** a `failed` preview's fix now points to "When a build fails" in `docs/previews.md`; a `building` one says a try-it link can take about four minutes to start building. The `none` note reads by case: previews off, as before; previews on but no preview read, how to read it (`workflow preview`); no report from Cloudflare yet (no comment or check), that its build may not have started or Cloudflare isn't connected; Cloudflare built nothing for the head, that. The last two are notes of their own (`preview_none`), so only previews off or unread is `no_previews`; a profile that can't be read (its own reason) gets neither. With previews on, a `none` for another commit is a stale answer, so it counts as still building.
- Docs: `docs/charter.md`'s merge section says runs pass the preview when previews are on; `docs/previews.md`'s "What to expect" says the merge check says "Not yet" while the link builds or after it fails. Tests: `tests/test_every_consumer_reads_the_preview.py`.
- **For projects updating:** nothing to do. With previews off, nothing changes.

**Everyday examples, and the names test** (#99, part of #37).

- **The README's walkthroughs** use everyday projects: the guided start's table row and example (a booking page and its reminders), the interview (`/grill-with-docs`, a notes app's dated notes), the map (`/wayfinder`, a small shop online) and `/to-questionnaire`'s who-it's-for (an accountant, a supplier, legal). The guided start skill's example matches: "#301 the booking page (quick ticket), #302 booking reminders (spec)".
- **Sensitive data:** patients' names stay as one example among phone numbers, payment details and children's names, in the README's set-up table, `docs/profile.md`'s `[sensitive]` row and `templates/profile.md`'s example.
- **`templates/profile.toml`'s area example** names a notes app's paths (`notes = ["server/notes.py", "app/lib/notes/**"]`).
- **The names test** (`tests/test_example_names.py`) reads every file a project receives (`vendor.plan`), plus the README and `docs/quickstart.md`, and allows pair-drop only in the README's "Where it came from", patient data only in those three sensitive-data examples, and the removed health examples nowhere. pair-drop and patient are matched in any case and inside identifiers (`patient_id`, `isPatient`, `FHIRPatient`), not inside other words ("impatient"); the health words anywhere. A failure names the file, line and rule. `CONTRIBUTING.md`'s "Writing" says so.
- **For projects updating:** nothing to do.

**`workflow doctor`'s Previews group, and the `add_try_it_links` offer** (#115, part of #41).

- **The Previews group,** read from the checkout, worded by experience like every line: with the profile's `[previews] on = true`, `previews.setup` is a gap when the Wrangler config (`wrangler.toml` at the project's root, read as TOML) has no `[previews]` block, or there's no Wrangler config there at all; its fix links `docs/previews.md` (step 6: by its path from the project's root when the kit is in the checkout, as in a vendored project, and by the kit's full path otherwise) and names the "missing a `previews` block" failure Cloudflare shows. With the block, it's fine. A `wrangler.json` or `wrangler.jsonc` is "can't check", with a fix naming the `"previews"` key to look for; a `wrangler.toml` that isn't TOML is too.
- **With `[sensitive]` patterns and `on = true`,** `previews.access` is a gap when `access` isn't true (beside `kit.profile`'s, when that is the mistake `profile check` refuses the profile for), linking the page's step 7; with `access = true` it's fine, and says the kit can't check Access itself and relies on the owner's word.
- **The offer:** a Wrangler config with no `[previews]` section is a note carrying a new offer, `add_try_it_links` ("Add try-it links"), so `doctor --strict` passes there. A section that doesn't turn them on is a note with no offer: they're off on purpose, so it's never a nag. With neither a Wrangler config nor a section, there's no Previews line.
- **The profile loader** records whether the profile has a `[previews]` section (`Profile.previews.section`), so previews never set up and previews turned off read apart.
- **Old Python's short report** names the Previews line ("can't check") only in a project with a Wrangler config or a `[previews]` section (read as text), roughly as the full report does.
- Docs: `docs/enforcement.md` §5, `skills/check-setup/SKILL.md`. Tests: `tests/test_doctor_previews.py`.
- **For projects updating:** nothing to do. Doctor changes nothing.

**"Add try-it links to your pull requests": `docs/previews.md`, and the quickstart's fourth next step** (#114, part of #41).

- **The page:** how to get a try-it link (a preview link) on every pull request from Cloudflare Workers Builds, with no live site, in plain words with each glossary word linked at its first use. Merging the no-live-site setting comes before connecting, since connecting deploys `main` at once. Seven numbered steps: a Cloudflare account; connecting only this repository through Cloudflare's GitHub app; an empty Build command on Production and on "Previews Base", naming the trap (a branch built before the fix keeps the old command, so push a fresh branch rather than retry); a new build token; preview URLs on, since they're off by default; the Wrangler config's `[previews]` block with `workers_dev = false` and `preview_urls = true`; and, for a project with sensitive data, Cloudflare Access, confirmed by the owner, since the kit can't check it; until Access is on (or if it can't be), `preview_urls = false` keeps the links off, since each deploy of `main` sets them from the Wrangler config. Then "When a build fails" (each build-log message with its fix) and "What to expect" (a comment and a check, about four minutes to start, made-up data only).
- **The D1 step** isn't there yet: `docs/spike.md` doesn't record the starter's D1 trial (#104), so #104's record pull request adds it.
- **The quickstart's next steps** gain a fourth, marked optional: "Add try-it links", linking the page. **The glossary's "preview link" entry** says "Add try-it links" turns them on; three entries lose a few words, so the file stays under 6,000 characters. `docs/profile.md`'s `[previews]` section links the page.
- **`workflow merge-check`'s "no try-it link" note** now ends by naming the page where it is: `.claude/workflow/docs/previews.md` in a vendored project, the kit's `docs/previews.md` otherwise (it named `docs/previews.md` everywhere, which only became visible now the page exists). With `[previews] on = true` it leaves the pointer out, since there is nothing to add.
- **Vendored:** the page ships in `.claude/workflow/docs/`, so it links only the docs that ship beside it. Tests: `tests/test_previews_doc.py`.
- **For projects updating:** nothing to do.

**The README opens on your own project, and PAIR's story moves to "Where it came from"** (#98, part of #37).

- **The opening,** after "New to building? Start here": what the kit does for your project in plain words (you describe what you want; Claude plans it, builds it in small reviewed pieces and merges what passes), attended work first and unattended runs as something you can add later, then the flow in short, for developers. The status note follows as it was.
- **The conductor's paragraph** moved to the top of "Unattended", opening "In an unattended run" where it said "For unattended runs".
- **"Where it came from":** a new section before "Licence", listed in Contents: the pair-drop weekend run of 9–12 Oct 2026, about 50 tickets. It is the only place in the README that names pair-drop; the Flutter line in Step 5 no longer points at pair-drop's own set-up doc.
- **History marked as background:** `docs/spike.md` opens with a note that it is the kit's record of what has been verified, PAIR's own runs and the demo repository's included; `docs/proposal.md`'s note says it is PAIR's original proposal.
- Tests: `tests/test_readme_opening.py`.
- **For projects updating:** nothing to do. None of these files ships.

**The conductor's pre-flight hands doctor the base branch's checks and offers "Require these checks" at kick-off** (#71, part of #38).

- **Two more files in `.workflow/`:**
  - `checks.json`: the base branch's latest commit's check runs and statuses, every page, side by side in one JSON list, for `--checks`. The conductor looks at the file before passing it, since doctor is silent about a wrong one, fetches it again once if it's wrong, and else leaves the flag out.
  - `prs.json`: the open pull requests, in full with `head.repo`, for `--prs` (from the MCP tools only when they give `head.repo`).
- **The offer:** `github.required_checks` offering `require_checks` (a note or a gap) is asked "Require these checks first" or "Go ahead without them", in place of "Fix it first / Go ahead without it". The conductor never changes the ruleset itself, so "Require these checks first" names the checks that ran, says to ask Claude to "require the checks" in an attended session (`upgrade-setup`), and ends the kick-off there, before anything is created. "Go ahead without them" puts a gap in `accepted_gaps`; a note needs no record. Two more gaps end the kick-off the same way on "Fix it first", for an attended session: a `github.required_checks` gap without the offer whose fix asks for "Require these checks" (its checks haven't run, or couldn't be read) while the base branch is protected, and `github.profile_checks`' gap (the profile's pull request is opened there, never in the kick-off). When the checks file was left out, the kick-off says once, as a note, that the checks that ran couldn't be read from the session. `upgrade-setup` now says the same: a conductor session never runs "Require these checks".
- **The note naming the open profile pull request** (`github.profile_checks`) stays a note: the run goes ahead, and the conductor never merges that pull request (the profile is a protected path, so it's the owner's). Unless the profile says `ruleset = false`, open pull requests that can't be read leave that line `cant_check`, a safety gap.
- Docs: `skills/conductor/SKILL.md`, `skills/upgrade-setup/SKILL.md`, `docs/enforcement.md` §5. Tests: `tests/test_conductor_doctor.py`, which also runs the pre-flight's own commands into doctor.
- **For projects updating:** nothing to do.

**"Check the set-up" hands doctor the base branch's checks and offers "Require these checks"** (#70, part of #38).

- **Two more files, in a cloud session:**
  - `--checks`: the base branch's latest commit's check runs and statuses, every page, read with `gh api`. The skill's own one-line command puts them side by side in one JSON list. The skill looks at the file before passing it, since doctor is silent about a wrong one. Without `gh api` it leaves the flag out: the GitHub MCP tools list no commit's check runs.
  - `--prs`: the open pull requests, in full with `head.repo` (`gh api`, or `list_pull_requests` with every field).
  - The skill says once that the checks that ran couldn't be read from this session, and to check the set-up again where `gh` is signed in. It says so only when the flag is left out, `github.ruleset` is fine and `github.required_checks` has no offer.
  - In a local session doctor reads both with `gh`, as before.
- **The offer:** `require_checks` is a choice with "Not now", handing over to `upgrade-setup`'s "Require these checks", whose checks screen asks which checks to require. When `protect_main` or `restore_protection` is offered too, protecting comes first.
- **The note naming the open profile pull request** (`github.profile_checks`) is shown as doctor words it, never as something to fix now. The skill still changes nothing itself, and never says "fine" while a line couldn't be checked.
- Docs: `docs/enforcement.md` §5 and the README's "Step 6. Check it". Tests: `tests/test_check_setup.py`.
- **For projects updating:** nothing to do. The update brings the skill's new steps.

**The evidence runs only the suites a pull request's files need** (`commands.select_suites`; asked for by medTech-group/pair-drop#485).

- **The setting:** `commands.select_suites`, a command the project writes. It reads the pull request's changed paths on stdin, one a line (`git diff --name-only --no-renames <base>...HEAD`, so a rename is both its paths), and prints the suites they need, one a line, or `none` when none is needed. No suite may then be named `none`.
- **It runs as the base branch has it:** in a temporary worktree of the base (without `commands.setup`), so a branch never changes the rules it's judged by, nor anything they import.
- **What runs:** `workflow evidence --base-ref origin/<base_branch>` runs those suites, and any suite one of whose test files (its `files`) was added, changed or deleted. It runs them on the branch and on the base worktree, so the counts compare the same suites. With none needed, nothing runs and the report passes, comparing nothing.
- **Every suite runs, as before,** when:
  - the setting is unset, or the profile says `ci.none` (the report is then the only proof);
  - the base ref isn't `origin/<base_branch>` as fetched (a ref inside the branch would list only part of its changes);
  - the changed files can't be listed (no merge base, a path that isn't UTF-8 or holds a line break) or none changed;
  - a change is under `.github/workflows/` or `.claude/workflow/`, or to a file the command names;
  - the command exits non-zero, takes over 2 minutes, prints nothing (a crashed pipeline can exit 0) or names a suite the profile hasn't.

  The report then says why. `--all` runs every suite whatever the setting says. `--suite` and `--base-count` make no selection.
- **The report:** the suites run and those not needed, with the command. Its first line reads `**Local suites its files need on `<sha>`**: passed` whenever a suite didn't run, with `--suite` too.
- **`workflow merge-check`:** where it needs the evidence (`ci.none`, or a waived check), only a full-suite report counts. A scoped one is a note, like a dirty one. `build-ticket` runs the evidence with `--all` when a check was waived.
- Docs: `docs/profile.md`, `templates/profile.toml`, `docs/flow.md` §4, `skills/build-ticket/SKILL.md` step 6. Tests: `tests/test_evidence_select.py`, `tests/test_merge_check_evidence.py`.
- **For projects updating:** nothing to do. To use it, set `commands.select_suites` in the profile (a pull request the owner merges).

**`workflow doctor` offers "Require these checks", and names the open profile pull request** (#69, part of #38).

- **Two new files, each winning over `gh`:** `--checks`, the base branch's latest commit's check runs and statuses in one file (GET `repos/<repo>/commits/<ref>/check-runs` and `.../status`, or `.../statuses`, every page, side by side): the checks that ran, read as `workflow protection --checks-ran` reads them from its two files; and `--prs`, the open pull requests, as `workflow ready --prs` takes them. Without them doctor reads both with `gh api` (GETs only, within the GitHub lines' 60 seconds), and only when a line needs them. Either can be `-`, but only one of doctor's files can be standard input.
- **The `require_checks` offer** ("Require these checks", beside `protect_main`, `restore_protection` and `set_up_unattended_runs`) is made on `github.required_checks` when checks ran on the base branch that the ruleset doesn't require, naming each with its result: on the "checks not required yet" note, on the gap naming checks the profile lists that the ruleset doesn't require, and, when the profile and the ruleset agree, on a note naming the check that ran and neither lists (one added to CI later). The try-it link's `Workers Builds: <worker>` check is never counted. It is never made in solo mode, nor while the base branch isn't protected (`protect_main` or `restore_protection` come first), nor when the check runs can't be read: the line is then as before.
- **A check the ruleset requires that the profile doesn't list** is a new line, `github.profile_checks`, given only then: a note naming the open pull request that carries `<!-- workflow:required-checks -->` (the profile catches up when it merges), a gap naming the checks with none open (add them to `ci.required_checks` in a pull request, since the merge rule and the conductor read the profile), or "can't check" when the pull requests can't be read. A pull request from another repository (a fork's) isn't counted, where its shape says so (GitHub's pulls list's `head.repo`, or `gh pr list`'s `isCrossRepository`). In solo mode the line is a note either way, and so are profile-listed checks the ruleset doesn't require, even with a ruleset on the base branch: "Require these checks" waits for the pull request that leaves solo mode. On an old `python3`, doctor takes the two files too.
- Docs: `docs/enforcement.md` §5. Tests: `tests/test_doctor_require_checks.py`.
- **For projects updating:** nothing to do. `check-setup` (#70) and the conductor's pre-flight (#71) hand doctor the two files.

**The quickstart: `docs/quickstart.md`, and "New to building? Start here" at the top of the README** (#77, part of #35).

- **One page, ten steps, about 10 minutes** from nothing to a first merged change, in a cloud session with nothing to install. The steps: what you need, connecting Claude to GitHub, a repository of your own, a cloud session in the Default environment, the README's Step 1 set-up message (copied word for word), merging the set-up pull request, a new session and one small change, its pull request and checks, merging it (and how to undo it), then the next steps, each optional: "Protect `main`", "Check the set-up" and "Set up unattended runs".
- **The clicks** are given for the desktop app's **Cloud** option and for claude.ai/code, and the plan, GitHub and environment facts link to Claude's and GitHub's own docs. A brand-new project's first choice in the guided start is a map, so step 7 says to pick "Something new, or a change to what's there" and then **Quick ticket**; step 6 says "Not now" to set-up's "Protect `main`" offer. The choices it names are checked against the skills that show them.
- **Every glossary word** links to its entry in `docs/glossary.md` at its first use on the page. #41 adds try-it links to the next steps when it writes `docs/previews.md`.
- **The README's** first line after the title is "New to building? Start here", linking the quickstart. Its Development section's list of what ships names the quickstart too.
- **Not vendored:** the quickstart is for the kit's readers, so `vendor.plan` leaves it out (`SKIP_DOCS`), and `CONTRIBUTING.md`'s "What ships" says so. Tests: `tests/test_quickstart.py`.
- **For projects updating:** nothing to do. Only `vendor.py`'s list of skipped docs changes.

**"Check the set-up": the `check-setup` skill, and the guided start's offer of it** (#63, part of #34).

- **The skill** (`skills/check-setup`, a kit skill Claude may load itself; not `doctor`, which Claude Code already has as `/doctor`) runs `workflow doctor --json` and shows its report, worded by the person's experience, the most serious first. It changes nothing itself.
  - **In a cloud session** it gathers what only a session can see into a directory outside the checkout: the rulesets, each fetched in full; the repository's settings; `list_environments`, every page; the `workflow:run` issues, open and closed; and `claude --version`. It hands them to doctor as `--rulesets`, `--repo`, `--environments`, `--runs` and `--claude-version`. A file it can't fill with GitHub's own answer is left out: doctor reads it with `gh` where it can, else says that line can't be checked. Runs it couldn't read (doctor's note) count as a line that couldn't be checked.
  - **In a local session** it runs doctor with what `gh` gives, and says the environments can only be checked from a cloud session.
  - **It never says "fine"** while a line can't be checked, and an old `python3` gets doctor's short report.
  - **The offers:** each offer the report names is a choice with "Not now": `protect_main` and `restore_protection` hand over to `upgrade-setup`'s "Protect `main`", `set_up_unattended_runs` to its "Set up unattended runs". Any other offer is named as text.
- **The guided start** (`start`) offers "Check the set-up" when `workflow status` reports a local gap (after reading `set_up`: before set-up it offers setting the kit up instead), on an old `python3`, and once a session in solo mode. Never at every session start, and never in ticket or conductor sessions.
- Docs: `docs/enforcement.md` §5 and the README's "Step 6. Check it" lead with "check the set-up" or `workflow doctor`, the manual checklist kept underneath as the reference; the README's parts table; `docs/install.md`. Tests: `tests/test_check_setup.py`.
- **For projects updating:** nothing to do. The update brings the new skill.

**The slowest tests run faster, so CI stays inside its time limit** (#193). The kit's own tests only: nothing that ships changes.

- **A fresh copy of the CLI** in a test's project (`tests/test_doctor.py`'s `_project`, `tests/test_guard_no_python.py`'s `_kit_at`) now has its bytecode beside it, compiled once per test run (`copy_kit_package` in `tests/conftest.py`). Under `-B`, a copy with no bytecode compiled every module on every run, about half of each run's time. The bytecode is checked against each file's source hash, so a test that changes a copied file still runs that file's new source (`tests/test_test_helpers.py`).
- **Copies with no bytecode, where it matters:** `compiled=False` gives the copy as before. Doctor's "nothing in the checkout changes" tests (#58, #59, #60) use it, so bytecode written by a run would still show, and so does `test_doctor_on_a_real_python_3_9`, which checks that no `__pycache__` is written.
- **Tests that run the CLI many times** now make those runs 2 to 8 at a time, one per CPU (`at_once` in `tests/conftest.py`). `_each_at_once` in `tests/test_doctor.py` gives each doctor run a folder of its own for its input files, fake `PATH` and home. Every run is still made, and its result checked as before. The tests:
  - doctor's "nothing in the checkout changes" tests;
  - doctor's wording tests: the GitHub lines, the Cloud lines and the kit's other states;
  - the Cloud contents note test;
  - the installed guard's attended cases (#57);
  - the guard's attended push and merge without a working `python3` (#56).
- **For projects updating:** nothing to do.

**The conductor's pre-flight runs `workflow doctor`** (#64, part of #34).

- **One check of the set-up:** the pre-flight gathers the files doctor takes into `.workflow/` (the rulesets, each fetched in full; the repository's settings; `list_environments`' pages; the `workflow:run` issues, open and closed; this session's `claude --version`) and runs `workflow doctor --json` with them, so a run checks exactly what the owner would check by hand.
- **Doctor's gaps, and its lines it can't check, are the kick-off's safety gaps,** each with its fix, asked "Fix it first / Go ahead without it" as before; an accepted one goes in `accepted_gaps` in doctor's words, its line's id in front. "Fix it first" follows the line's fix (the `upgrade-setup` offer it names, if any) and runs doctor again. Notes are shown as they are; `github.approvals` above 0 still makes **owner** the recommended merge answer.
- **Replaced, not kept beside doctor:** the pre-flight's own steps for the ruleset, the required checks and "up to date", Code Owners review, required approvals, CODEOWNERS and `profile check`, and its `workflow status --json` / `workflow protection` read-back for solo mode.
- **Solo mode and removed protection** (#50) are read from doctor's lines: `kit.ruleset`'s solo-mode note (`ruleset = false`), or `github.ruleset`'s mismatch line offering `restore_protection` (`ruleset = true`, the base branch unprotected). With `ruleset = true`, three more cases count as removed protection, worded as unconfirmed: a `github.ruleset` line still `cant_check`, no such line, and a doctor run that never gave its JSON (then the profile's `project.ruleset` decides). A gathered file that holds an error, or that a line says can't be read, is fetched again once before the report is read. In solo mode, doctor's ruleset lines and `github.auto_merge` give way to the one solo-mode gap. The kick-off's "Protect `main`" / "Restore protection" / "Go ahead" is unchanged, but when GitHub refuses the rulesets list because rulesets need a paid plan (a private repository on GitHub Free), the conductor saves no ruleset, says why, and recommends going ahead, since protecting `main` can't work on that plan.
- **Still the conductor's own:** `WORKFLOW_ROLE`, the permission mode against the profile's, `version --fresh`, `ready --fetch` and the protected-path notes, leftovers, the base branch's CI and the last run (now read from the same `workflow:run` issues). A missing ticket environment still stops the run before the kick-off's questions, whatever doctor's Cloud line says, and the conductor still keeps its id from `list_environments`; one of that name that isn't active counts as missing, as doctor counts it, and two active ones stop the run too. A gap still open after "Fix it first" asks "Go ahead without it" or "Don't start the run"; a `github.approvals` line that can't be checked also recommends **owner**.
- Docs: `skills/conductor/SKILL.md`, `docs/enforcement.md` §5, the README (Step 6, "Run the backlog unattended"), `docs/charter.md`, `docs/protection.md`. Tests: `tests/test_conductor_doctor.py`; two of `tests/test_charter_solo.py`'s pre-flight tests now read the doctor wording.
- **For projects updating:** nothing to do.

**`workflow status` reports doctor's local gaps, with no network calls** (#62, part of #34).

- **The checks** are doctor's own local ones, run as doctor runs them:
  - `python3` on the PATH;
  - the hooks, with Claude Code's settings and the plugin;
  - `profile check`'s errors. Its warnings are notes, and their globs can be slow, so `status` skips them;
  - `vendor verify`;
  - the `ruleset` setting.
- **No network:** the checks read only this computer and the checkout. Without `--fetch`, `status` still runs no `gh`. `--fetch` reads issues, pull requests and the latest release as before. It never runs doctor's GitHub or Cloud checks.
- **Not set up:** a project with no profile has the gap `kit.profile`, as in doctor, beside `Kit: NOT set up here`.
- **Text:** one line after the experience lines. It is `Local gaps: none`, or names each gap by doctor's id, the most serious first: `Local gaps: 2 (computer.python3, kit.hooks): ...`.
- **`--json`:** `local_gaps`, the gap lines in doctor's shape (group, id, status, message, fix, offer, worded by the person's experience), and `local_gap`, `true` or `false`. A note or a line doctor can't check isn't a gap. Solo mode (`ruleset = false`) and no `ruleset` setting are notes, which `Solo mode:` already reports.
- **A profile with an error** no longer stops `status`. It says `Kit: set up, but its profile has an error (kit.profile)` and `Solo mode: unknown`, and the gap `kit.profile` says what's wrong. In `--json`, `profile_error` is `true` and `set_up` stays `true`. `--fetch` then reads no issues and says why.
- **Ctrl-C** while `status` runs `python3` stops it quietly (exit 130).
- Everything else in `status`'s text and JSON is unchanged. Tests: `tests/test_status_local_gaps.py`.
- **For projects updating:** nothing to do.

**`workflow doctor` on an old `python3`: a short report** (#61, part of #34).

- **On a `python3` older than 3.11** (macOS's own is 3.9), `workflow doctor` gives a short report from the kit's old-Python path (Python 3.7 syntax, the standard library only) instead of saying what it needs and exiting 1. `python3`'s version (the Python running it) is a gap with its fix; every other line the full doctor gives when nothing is wrong (Claude Code's version, the kit, GitHub, Cloud) is `can't check` "until `python3` is 3.11 or newer", with the full doctor's ids and groups (`kit.hooks` and `kit.vendor` in a vendored project, `kit.plugin` in plugin mode), so a skill reading `--json` sees the same lines.
- **`--json`** gives the full doctor's shape (`experience`, `wording`, `counts`, `strict_ok`, `lines`, each line's group, id, status, message, fix and offer). It exits 0, and 1 with `--strict`. It takes the full doctor's flags as the full doctor parses them (`argparse`, so a refused argument exits 2, as in the full doctor); the files and the version a session hands in (`--rulesets`, `--repo`, `--environments`, `--runs`, `--claude-version`) are taken and not read. It never raises: a report that fails still gives the `python3` gap, and output that can't be written (a closed pipe) still exits as `--strict` says.
- **Wording** follows `WORKFLOW_EXPERIENCE`, else `.workflow/experience`, read as the full doctor reads them; the profile's default needs `tomllib`, so it isn't read there, and unknown reads as new to building; the JSON's `experience.default` is always `null` there.
- A test on the supported Python compares its lines with the full doctor's on the same checkout, and every line id `doctor.py` names, so a line added later is added to the short report too (`_DOCTOR_LINES` in `scripts/workflow/_old_python.py`), or listed as one said only when something is wrong.
- Docs: `docs/enforcement.md` ("When something is wrong"), the README's "When something goes wrong". Tests: `tests/test_doctor_old_python.py`, on a real Python 3.9 in CI.
- **For projects updating:** nothing to do.

**`workflow doctor`: the Cloud lines (the two environments)** (#60, part of #34).

- **The environments** the profile names (`run.ticket_environment`, `run.conductor_environment`) come from `--environments FILE`: the account's environments as `list_environments` returns them (`{"environments": [...], "has_more": false}`, the list alone, or a list of its pages), or `-` for standard input. Only a cloud session can list them, so there is no other source. With no file the line is `can't check`, saying only a cloud session can check them ("ask a cloud session to check the set-up").
- **The line:**
  - both found by their exact names, and active, is fine;
  - one found and not the other is a gap naming the missing one;
  - neither found is a note offering `set_up_unattended_runs` while no run has been made, and a gap naming both once one has;
  - when doctor can't tell whether a run has been made, it is the same note, saying "if you've already made a run, this is a gap" and why it couldn't tell;
  - one environment named for both roles is a gap, since ticket sessions and the conductor each need their own.
- **What counts as found:** a name that differs at all (a letter, its case, a space) isn't found, and a listed name close to it is named as a likely typo. An environment whose `state` isn't `active` (in any case) isn't found either, and a `state` that isn't text is the wrong shape. An empty name in the profile is missing (and `profile check` warns about it). Names are shown exactly: one with a space at either end, a backtick or a character that can't be printed is shown as a JSON string.
- **What it can't tell:** a list that says `has_more` can't tell whether a name it doesn't hold is there, so the line is `can't check`. A file that can't be read, or isn't in `list_environments`' shape, is `can't check` saying why.
- **Whether a run has been made:** an issue labelled `workflow:run`, open or closed (pull requests don't count). It is read only when neither environment is found. It comes from `--runs FILE`, read as `charter estimate --runs` reads it (a list of issues, the GitHub MCP tools' `{"issues": [...]}` or search's `{"items": [...]}`, or pages of any of them; an issue without labels counts, since it was fetched by its label), or `-`. An issue is an object with a number or labels, whose labels, if given, are a list. When no entry is a run and one isn't an issue, such as GitHub's error saved as the file, the runs can't be read. Without the file it is read with `gh api`: one GET, within the GitHub lines' 60 seconds for all of GitHub's reads, with the same reasons when it can't be read.
- **Always followed by a note:** nothing can read what an environment holds, so confirm by hand that the ticket environment has no secrets and `WORKFLOW_ROLE=ticket`, and the conductor's `WORKFLOW_ROLE=conductor`. Notes never fail `--strict`; the gaps and `can't check` do.
- **Elsewhere in doctor:** only one of `--rulesets`, `--repo`, `--environments` and `--runs` can be standard input. An empty file now says it is empty, and a character that can't be printed, in a value or a file's path shown in a report, is escaped.
- Docs: `docs/enforcement.md` §5, `docs/install.md` ("Check it"). Tests: `tests/test_doctor_cloud.py`; the other doctor tests now give both environments by default.
- **For projects updating:** nothing to do. In a local session the Cloud line says only a cloud session can check the environments.

**`workflow doctor`: the GitHub lines (the ruleset, the merge settings and CODEOWNERS)** (#59, part of #34).

- **Where GitHub's answers come from:** `--rulesets FILE` (each ruleset in full, as `workflow protection` takes them) and `--repo FILE` (the repository's settings), either of them `-` for standard input (read as UTF-8; never waited on at a terminal), read as `workflow protection` reads them (`NaN` refused). A file given wins; without one, doctor reads them with `gh api` (GETs only, 30 seconds a call and 60 for all of them), as `status --fetch` does. With neither, each line that needs them is `can't check`, saying why and how to check it: `gh` not installed or not signed in (sign in with `gh`, or ask a cloud session to check the set-up), a repository GitHub doesn't know (`project.repo`), a refusal (HTTP 403: an admin's `gh`), no connection (the network or proxy), a rate limit, GitHub's own error or no answer (run it again), or a file that can't be read. `--strict` then exits 1. `gh`'s messages are shown with the home directory as `~`.
- **Protection** is `workflow protection`'s read-back (#44), called as it is. The profile's `ruleset = true` with the base branch unprotected is a gap offering `restore_protection`, listed before every other line of the report: removed protection is never trusted. Each missing protection is its own gap in plain words (a ruleset turned off or only evaluating, no ruleset on the base branch, a bypass list, deletions or force pushes allowed, pull requests not required); a ruleset for other branches (or one with a pattern) isn't blamed while another one covers the base branch. What the read-back can't see is never removed protection: when the base branch would read protected with bypass lists only an admin can read taken as empty, the ruleset line alone is `can't check` (a note in solo mode); without the default branch (the settings missing, or without `default_branch`), the rulesets are read with it as the base branch and as another, and when the two readings differ every ruleset line is `can't check`, saying what to give, unless neither reading puts a ruleset in force on the base branch (then the other lines read as with none); when neither protects it, the ruleset line still says so (removed protection, first, under `ruleset = true`; in solo mode a note only when neither reading has a ruleset there). Settings whose merge settings can't be read still give their default branch. In solo mode (`ruleset = false`) no ruleset on the base branch is a note offering `protect_main`, and so are the checks the profile lists; a ruleset there with holes is a gap like any other. With `ruleset` absent, an unprotected base branch is a gap offering `protect_main`. GitHub's answer that rulesets need a paid plan (a private repository on GitHub Free) reads as no ruleset, and the line says so.
- **Required checks:** "checks not required yet" is a note while `ci.required_checks` is empty; the names it lists that no active ruleset on the base branch requires are a gap naming them (a note in solo mode with no ruleset there).
- **The other ruleset lines,** read from the active rulesets on the base branch (none there: no lines, since the ruleset line says so): "Require branches to be up to date" off is a gap (a note while the profile lists no checks and none are required, since it comes with them); required approvals above 0 a note saying unattended runs will stop at "ready for review", and a count that can't be read `can't check`; "Require review from Code Owners" on, while sessions post as the owner, a gap; a linear-history rule a gap.
- **Merge settings:** merge commits off is a gap; auto-merge off a gap, or a note in solo mode; a setting GitHub shows only to admins is `can't check`.
- **CODEOWNERS,** read from the checkout (so checked without `gh` too) where GitHub looks first (`.github/`, the root, `docs/`), must name an owner (`@login`, `@org/team` or an email address) for every file under `/.claude/` and `/.github/workflows/`, as GitHub matches its patterns (`/.claude/*` takes only the files directly there, and a later rule naming nobody takes files back); missing either, or missing altogether, is a gap.
- `workflow protection`'s report also keeps, for doctor, the kind of each missing protection and the rulesets it counted; its verdict, text and `--json` are unchanged.
- Docs: `docs/enforcement.md` §5, `docs/protection.md`, `docs/install.md` ("Check it"). Tests: `tests/test_doctor_github.py`.
- **For projects updating:** nothing to do. Doctor only reads: run it with `gh` signed in to see the GitHub lines.

**`workflow doctor`: one report of what's set up and what isn't, with the Your computer and The kit lines** (#58, part of #34).

- **`workflow doctor`** prints one line per check, grouped (Your computer, The kit, and GitHub with #59; Cloud comes with #60), the most serious first. Each line is `fine`, a `gap`, a `note` (a state chosen on purpose) or `can't check` with how to check it, with a one-sentence fix, and sometimes an upgrade Claude can offer (`protect_main`). `--json` gives every line's group, id, status, message, fix and offer, for skills. It exits 0 always; with `--strict`, 1 when any line is a gap or can't be checked (notes never fail it). It never changes anything, in vendored or plugin mode alike.
- **Wording by experience:** every message and fix has a *new to building* and a *developer* wording, chosen as `workflow status` resolves the experience (unknown reads as new). What is checked, and each line's status, never depend on it.
- **Your computer:** `python3` on the PATH, the one the hooks run (run as they run it), is 3.11 or newer, and one that's missing or doesn't run is a gap; Claude Code is 2.1.295 or newer (`--claude-version`, else `claude --version`; a pre-release of 2.1.295 is older), since an older one lets a command run when the guard's hook fails or times out. A version it can't read is `can't check`.
- **The kit:**
  - a vendored project's hooks in `.claude/settings.json` are the entries of the kit version that runs doctor (a hand edit or a stale update is a gap). Run from another kit, such as a checkout of the kit, a difference is `can't check`, with the project's own copy's command to run instead;
  - in plugin mode the plugin is enabled (the user's settings, the project's, or its local file, the most specific winning); both on is a gap naming the file that turns the plugin off;
  - Claude Code's settings files that can't be read are one gap (the lines that need them wait on it), and so is `disableAllHooks: true` where the most specific file sets it;
  - a vendored copy or the kit's hooks left without `.claude/workflow/lock.json` is a gap saying so, not a project to install the plugin in;
  - `profile check`'s errors are gaps and its warnings notes;
  - `vendor verify`'s file check (vendored only), read as doctor reads files: missing files, files changed by hand (which `vendor verify` itself counts only with `--strict`) and unsettled conflicts are gaps; Matt Pocock's skills not vendored, and not declined either, is a note;
  - the experience with its source, and `project.ruleset`: `false` is a note offering "Protect `main`", absent is "not set (as before)", a note.
- **Never a traceback, never stuck:** a file it can't read (not UTF-8, a directory, a pipe, the wrong JSON) is a line saying so, and a check that fails unexpectedly is `can't check`. A `python3` or `claude` that hangs is stopped after 10 seconds, with its process group. The text wraps to the terminal's width (at most 100 columns).
- Docs: the README's command list, `docs/install.md` (plugin mode, and "Check it"). Tests: `tests/test_doctor.py`.
- **For projects updating:** nothing to do.

**The guard's hook blocks on failure: `onFailure: "block"` and a 30-second timeout** (#57, part of guard robustness, #33).

- **The guard's PreToolUse entry,** in a vendored project's settings and in the plugin's hooks file (`hooks/hooks.json`), carries `"onFailure": "block"`: a guard hook that times out, can't start or prints output Claude Code can't read blocks the tool in every role, attended sessions included, instead of letting it run. Claude Code discards a timed-out hook's output, so a timeout blocks even where the guard would have allowed the command. It needs Claude Code v2.1.295 or later; an older version ignores the field and keeps the hooks (checked on 2.1.294, #54). An attended session's guard command always exits 0 (#56), so only a real failure blocks.
- **Its timeout goes from 15 to 30 seconds,** so an ordinary command on a large tree or a slow laptop isn't blocked for being slow. The guard's own time budget goes from 12 to 25 seconds with it, so it still refuses with its own reason (or takes the can't-decide fallback in an attended session) before the timeout cuts it off.
- **The Stop gate, the prompt hook and the session-start hook keep the default (`continue`)** and their timeouts: blocking a Stop on failure would loop, and blocking a prompt would lose it.
- **When a timeout blocks a command,** Claude says so and offers to split or simplify it: set-up's "Workflow" section in `CLAUDE.md` says so in a line, and `update-workflow` adds the line to a project's section that lacks it.
- Docs: `docs/enforcement.md`'s "When something is wrong" and the oldest Claude Code these protections need (v2.1.295); the README's "When something goes wrong". Tests: `tests/test_guard_on_failure.py`.
- **For projects updating:** the update rewrites the guard's hook entry in `.claude/settings.json` (`onFailure`, the timeout, the matcher), keeping the project's own hooks, and the update's pull request says so, so the owner reviews it like any other change. Use Claude Code v2.1.295 or later for the timeout and can't-start protection.

## 0.1.11

**Solo mode, a guard that fails closed, `workflow merge-check`, light reviews and presets, and the preview reader.** Everything built by the unattended runs 2026-10-16-weekend (#130) and 2026-10-17-followup (#174): the build tickets of specs #32, #33, #35, #37 to #39, #41 and #42 that could start, and the infra fixes they found. Each change's own note is below.

- **For projects updating to 0.1.11:**
  - a profile with `run.review_rounds = 1` now gets the light review shape in a run (see #121 below);
  - the update adds `.github/pull_request_template.md`, or the "In plain words" headings at the top of yours (see #83);
  - the update writes the new hook matcher and hook commands into `.claude/settings.json` (see #55 and #56);
  - the update asks the project's experience default once if the profile has none (see #49);
  - a run under way keeps its vendored skills until the update (see #85);
  - nothing else: every other change below needs nothing from an updating project.

**`workflow preview`: a pull request's try-it link and its state, from one command** (#113, part of #41).

- **`workflow preview --comments F --checks F --sha SHA`**, or **`--fetch <PR>`** to read the same three through `gh api` (REST routes only, every page; a file given wins), answers `state` (`built`, `building`, `failed` or `none`), `url` and `commit`, in plain words or with `--json`. The JSON is what `workflow merge-check --preview F` takes. It changes nothing and posts nothing; a missing input exits 2 naming it, one it can't read exits 1 saying why.
- **The rules:** Cloudflare's `Workers Builds: <worker>` checks on the head commit decide the state. Only checks from the `cloudflare-workers-and-pages` app count, and a re-run counts by its latest result. A skipped build has no preview: `none`.
- **The link** comes from the Cloudflare bot's comment, read as it stands: the Branch Preview URL (or the Preview URL beside a Deployment URL) of the head commit's row, only when that row says the deployment succeeded. A row that says it failed is `failed`. With several Workers, each built on the head needs its own row to say so; one with no check on the head (build watch paths) counts neither way. A re-run still going is `building`, whatever the comment said of the last. A link for an older commit is `building`, never `built`. No bot comment and no check is `none`.
- **A format it doesn't know is refused,** not read as "no preview": a bot comment without the table, a row without a commit, a Preview URL cell with no link it can tell is the branch's. A comment counts as the bot's only when GitHub says it's a bot.
- **Not gated here:** whether a project reads previews (`[previews] on`) is for its callers (#117). Tests: `tests/test_preview.py`, with fixtures in `tests/fixtures/cloudflare/` in the shape Cloudflare's documentation gives the bot's comment and check runs; checking against a real recording is a by-hand check (#173). The README's command list and `docs/install.md` name it.

**A ticket session merges only its own pull request** (#87, found by #36).

- **The guard** refuses a ticket session's merge unless it is pinned to the head commit of the session's checked-out ticket branch, in the field GitHub checks: `gh pr merge <n> --match-head-commit <sha>` (with `--auto` too), the REST merge's `-f sha=<sha>`, or `merge_pull_request`'s `expectedHeadSha`. The refusal names the fix: pin it to `git rev-parse HEAD`, and `git pull` first if the pull request's head was updated on GitHub. Every pin given must match. A REST merge with an `--input` body is refused, and so is a merge, or any ticket-session `gh api` call (a read included), with a word the shell expands into other words outside quotes (a variable, substitution, glob, brace list or leading tilde, or a quoted array) or fed by `xargs`: the guard's lexer now marks such words, so quoted text is fine. Before, any pull request could be merged once its required checks were green, another ticket's included, before its own review rounds.
- **`enable_pr_auto_merge` and `PUT pulls/<n>/ccr/auto_merge`** take no pin GitHub is known to check, so the guard reads the pull request's head with `gh api` and allows the arm only when it is the session's ticket branch, in this repository, at its local head; when it can't be read, the arm is refused, naming the pinned `gh pr merge --auto` and the conductor. Ticket sessions may now use the `ccr/auto_merge` route, which cloud sessions need, since `gh pr merge --auto` goes through GraphQL there. Disarming needs no pin.
- Conductor and attended sessions are unchanged. The merge steps in `build-ticket`, `merge-check` and `conductor` already pin to the head `merge-check` checked. `docs/enforcement.md` §4 says how a session's own pull request is told. Tests: `tests/test_guard_own_merge.py`.
- **For projects updating:** nothing to do.

**`merge-check`: a clean Correctness pass after the last allowed review round lifts that round's findings** (#170, decided for run 2026-10-16-weekend's open question; part of #39).

- **`workflow merge-check`** follows flow §3 and §4.4: a review round that wasn't clean still answers `review_not_clean` (run another round) unless it was the last allowed one (its number at least the allowed rounds); then a later clean Correctness pass on the head lifts it, a not-clean one answers `pass_not_clean`, and with none it answers `review_not_clean` saying to fix the findings and run a Correctness pass on the head. No fourth round is ever asked for. Before, a last round with findings blocked for good, even after a clean pass on the head: #76's PR #177 had to be merged by hand.
- **`--review-rounds N`** (1 to 10) gives the allowed rounds; without it, the profile's `run.review_rounds` (3 by default, and 3 when the profile can't be read). Any other value is refused with a plain message. The answer's JSON says which number it used (`review_rounds`), and a review reason with a counted round carries its `round` and `reviewers`, and on `review_not_clean` its `next` (`round` or `pass`), so a caller needn't read the wording.
- **build-ticket and the conductor** pass the briefing's (the charter's) review rounds to `merge-check`; the `merge-check` skill's "Review it now" runs a Correctness pass for `next: pass` (on a fork's branch too, once the author has pushed fixes), and it checks a light review's PR with `--review-rounds 1`. `docs/flow.md` §4.4 and `docs/charter.md` say so. Tests: `tests/test_merge_check_rounds.py`, with PR #177's own records.
- **For projects updating:** nothing to do.

**The flow the context hook adds stays under Claude Code's 10,000-character limit** (#76).

- **The first flow request of a session** (`workflow hook context`) now gets a short, fixed instruction first: follow the flow, and read it now, all of it, before acting, at its paths (the flow and any `flow_addendum`). Then come the flow's sections from its start, each whole, as far as they fit in 8,500 characters, with room left for the glossary's rule (#74); the instruction names only the section where they stop, so it stays short however much is left out. A flow file that can't be read now leaves only the instruction, where the hook used to fail. Before, the whole flow went in (12,000 characters and more), over Claude Code's limit for a hook's added context, so Claude may have seen only its first 2,000 characters while being told to "follow the flow below".
- The reminder at later flow requests says to read the flow again unless all of it is still in context. `docs/profile.md` describes the flow context. Tests: `tests/test_flow_context_limit.py`, with the kit's own flow, long addenda, many sections and a huge heading; #74's `test_beside_the_whole_flow_as_the_rule_and_its_path` now checks the whole stays under the limit. Whether Claude Code truncates is still to confirm by hand (#173).
- **For projects updating:** nothing to do.

**The review panel's explorer runs commands that write files only on a scratch project** (#172, found by #106).

- **`review-panel` and the `ui-explorer` agent:** a command under review that writes files (`workflow adopt`, `workflow vendor`, `workflow repair`, the set-up step that saves `workflow pr-template`'s output, anything taking `--project` or `--out`, and any other command that writes files, `workflow evidence` among them) runs only against an absolute path to a scratch project, never the session's checkout: a fresh temporary directory, or a `git clone` of the checkout into one with its `origin` removed, never a `git worktree`, which shares the session's `.git`. The explorer calls the CLI with `python3 -B` by its absolute path in the session's checkout, or in the clean copy (below) when it has one, and gives `--project` the scratch project's path on every call, since a left-out `--project` (or an empty one, for `vendor`) means `$CLAUDE_PROJECT_DIR` or the nearest checkout; it tries a command without one as `cd <scratch> && CLAUDE_PROJECT_DIR=<scratch> …`. It runs `git status --porcelain --ignored --untracked-files=all` in the session's checkout before and after and reports any difference as a finding instead of undoing it, since the guard can refuse the undo of a protected file.
- **If the guard refuses a discard** after a round (a protected file), the session finishes in a clean copy (`git worktree add --detach … HEAD`, pushed with `git push origin HEAD:<branch>`), does the rest of the review there (the reviewers get its path; the explorer runs the CLI from it and checks both with `git status`), and says so in the PR body.
- Tests read both texts (`tests/test_review_scratch_project.py`).
- **For projects updating:** nothing to do.

**`workflow state patch` and `state put` check a charter change against the profile** (#171, found by #50).

- **`state patch` and `state put`** run the checks `workflow charter validate --approved` runs against the profile on disk whenever the charter in the state changes: auto-merge in solo mode or with no `ci.required_checks` (#50), release steps, waived checks, the explorer and the owner. A change that fails is refused, listing the same problems, and the state is left unchanged, so a mid-run patch can't set `merge.mode = "auto-merge"` where the kick-off couldn't. A change that drops a `removed protection:` line from the current charter's `accepted_gaps` is refused too (a `put` over a block that isn't JSON has no current charter), so the charter keeps that verdict, and auto-merge stays refused, until the run ends: auto-merge needs a new run, whose kick-off reads protection back. The conductor's amendment step never drops it. Before, only the conductor's amendment step caught any of this, by running `charter validate` first.
- A patch that doesn't change the charter (`tickets`, `status`, …) is written as before, unchecked. With no profile a charter change is written with a note; a profile that can't be read (not TOML, not UTF-8, not a file) refuses it. The conductor skill's amendment step and `docs/charter.md` §4 say so. Tests: `tests/test_state_charter_profile.py`.
- **For projects updating:** nothing to do.

**An estimate before a run, in sessions and hours** (#123, part of a session budget and a light review, #42).

- **`workflow charter estimate charter.json --tickets N`** says roughly what a run will use, never in money: "About 14 ticket sessions over roughly 7 hours (7 tickets, up to 1 retry each), plus the conductor's check-ins". With no past runs it is the worst case (every retry used) at an hour a session; given `--runs` (past `workflow:run` issues, as the GitHub API returns them) with two or more that merged something, it uses the five most recent runs' sessions per ticket (never above the retries the charter allows) and wall time per merged ticket. The approved estimate is kept in the run state as `estimate`, for later splices. A body whose run state can't be read is skipped with a note.
- **Warnings,** never blocking: the end time stops the run early, `max_sessions` is below the tickets' tries and retries, or the review is lighter than the project's default while `--security` names a ticket the review panel would give a security review. `--json` gives `sessions`, `hours`, `basis`, `runs_used` and `warnings`.
- **The one page:** `charter markdown` and `charter splice` take `--estimate estimate.json` and add "**Estimate:** …" with its basis, so the tracking issue records what the owner expected.
- **The conductor's kick-off** offers the presets first, shows the estimate with them and runs it again on every change; the pre-flight's capacity line is unchanged, with the estimate beside it. `docs/charter.md` §2 describes it.
- **For projects updating:** nothing to do.

**`merge-check --fetch` works in a cloud session** (#165, a follow-up to #81 found by #85).

- **Review threads:** when GraphQL is refused (a Claude Code cloud session's proxy refuses it), `--fetch` reads the session route `pulls/<n>/ccr/review_threads`, every page, and gives it to `merge-check` in GraphQL's shape. That route is a bare list with no count, so it counts as whole only when every review comment of the pull request (`pulls/<n>/comments`, every page, as many as the PR's `review_comments`) sits in one of its threads; otherwise the threads stay "couldn't read".
- **Permissions:** when the session's proxy refuses `collaborators/<login>/permission` ("not permitted through this proxy"), the token's own login (`gh api user`) gets the token's own permission on the repository (`repos/<repo>`'s `permissions`). Anyone else counts as without write access, since nothing the session can read shows theirs (`author_association` doesn't). A reviewer whose change request still stands, as `merge-check` reads the reviews, isn't dropped that way: permissions then stay "couldn't read", naming them.
- GraphQL and the collaborator route are still tried first, a file given still wins, and any other failure (GitHub's own 403s included) is "couldn't read" as before. The `merge-check` skill says so. Tests: `tests/test_merge_check_cloud.py`.
- **Fixed:** reviewers in a `--reviews` file in GraphQL's shape now have their permissions fetched too. Before, they were left out, so their change request counted as from someone without write access.
- **For projects updating:** nothing to do.

**A run's size in one choice: Light, Normal or Thorough** (#119, part of a session budget and a light review, #42).

- **The presets** bundle the levers the kit controls: sessions at once, sessions in all, retries per ticket, review rounds and the UI explorer. Light is 1, 10, 0, one round and no explorer; Normal is the profile's own numbers (40 sessions in all); Thorough is 3, 60, 1, at least 3 rounds (more when the profile has more) and the explorer where the project has one. The end time is always asked; the check-in interval stays the profile's.
- **The charter** gains `preset` (`light`, `normal` or `thorough`) and a `review` section (`rounds` 1–10, `explorer` true or false; unknown keys refused). The check against the profile refuses `review.explorer = true` when `ui.explorer` is `none`.
- **`charter questions`** offers the presets first under the limits question (`options`, the profile's `run.preset` first and `recommended`, each preset's numbers in `presets`); **`charter defaults`** starts from `run.preset`. Solo mode's merge rule (#50) stands beside them.
- **The one page** (`charter markdown`, `charter splice`) says the size and the review: "**Normal**, changed: 3 sessions at once", and "no UI explorer (the project has none)" where so. `charter reuse` keeps `preset` and `review`; `charter diff` shows changes to both.
- **The profile:** `run.preset`, `normal` when absent; anything else fails `profile check`. It is only the charter's recommended answer: attended builds never read it.
- The numbers live in one place, `scripts/workflow/presets.py`. Docs: `docs/charter.md` §2 and §5, `docs/profile.md`. Tests: `tests/test_charter_presets.py`.
- **For projects updating:** nothing to do. A charter written before this, with no `preset` or `review`, stays valid and reads as Normal (the profile's review rounds and UI explorer), so a run in progress keeps working. Ticket sessions take their rounds and explorer from the charter (#120, below).

**Ticket sessions take review rounds and the UI explorer from the approved charter** (#120, part of a session budget and a light review, #42).

- **The briefing** (`workflow render`) now reads the review from the charter, through `presets.review_of`: the charter's `review`, else its preset's numbers, else the profile's `run.review_rounds` and `ui.explorer` for a charter written before presets. Its review line names the explorer too: "UI explorer: browser", or `none` when `review.explorer` is false.
- **Rounds of 1** brief as "at most 1 (the light review)" and the explorer as `none`, so the light-review rule (the briefing's review rounds at 1) applies without a line that contradicts it. The one page says so too: a one-round review with `review.explorer` on reads "no UI explorer (one round is the light review)", so the owner approves what the sessions do.
- **The skills say so:** `review-panel` and `build-ticket` take the rounds and explorer from the briefing in a ticket session, else from the profile; `docs/flow.md` §3 and the conductor's capacity line too.
- Docs: `docs/charter.md` §1 and §4, `docs/flow.md` §3. Tests: `tests/test_briefing_review.py`.
- **For projects updating:** nothing to do. A charter with no `preset` or `review` briefs exactly the profile's rounds and explorer, as before; the briefing gains the explorer on its review line.

**The light review, offered second: "Build it with a light review", and "Review it now" as a light review** (#122, part of a session budget and a light review, #42).

- **`next` and the guided start** offer "Build it with a light review" wherever they offer to build a ticket, as the second choice after the full build: never first, never "(Recommended)", never chosen for the person. `next` asks before claiming, only in an attended session, and not when the person already said how ("build #12", "build #12 with a light review", "quick build #12"); a ticket session asks nothing.
- **The `merge-check` skill's "Review it now"** now runs the light review (`review-panel` §6) instead of the full panel when nothing has been reviewed yet, and the choice says so. After a round with findings: the fixes, then another round (Correctness-only after a light review's Correctness-only round, by its record, else the full panel, never lighter); after a pass with findings, the fixes and another pass; after newer changes, a Correctness pass on the head. On a fork, only the reviews that need no push are offered.
- **The glossary's "Review panel" entry** says what a light review is: one round with no walk-through of the screens, for small changes, never chosen for you. Other entries are trimmed a little to keep it under 6,000 characters. The README's guided-start example lists the new choice.
- Tests: `tests/test_light_review_offers.py`.
- **For projects updating:** nothing to do.

**The conductor and ticket sessions merge on `workflow merge-check`** (#85, part of judging a PR without reading code, #39).

- **One command decides every merge in a run.** Right before merging or arming auto-merge, the conductor's check-in and `build-ticket` §6 run `WF merge-check --fetch <PR> --json --charter <file>`. The file is the tracking issue's body (its run state holds the charter), saved under `.workflow/` so the evidence still sees a clean tree. A waived check's log goes under `--check-logs`; an input `gh` can't read is given as a file. It is the same command a person's `merge-check` runs, so a run and a person never disagree on "ready".
- **`ready` is the only yes.** In `session` mode the merge is a merge commit pinned to the head it checked (`gh pr merge <n> --merge --match-head-commit <sha>`, the REST merge with `sha`, or `merge_pull_request` with `expectedHeadSha`). In `auto-merge` mode auto-merge is armed only on `ready`, pinned the same way (`gh pr merge --auto … --match-head-commit`); it is disarmed before any push to the PR (a fix, the base merged in, a branch update) and on a later `not_yet`, and armed again only on the new head's `ready`; when GitHub refuses because the PR is already clean, the command runs again and merges on `ready`. In `owner` mode `ready` marks it "ready for you to merge". `not_yet` never merges: its reasons say what to do (update a branch that's behind; a red check or a review is the ticket session's).
- **Protected paths:** `owner_review` goes to `for_owner` as "#n changes a protected path (<files>): yours to review and merge (#PR)", with merge-check's `files`, and is never merged or armed unattended; a ticket session comments that the owner merges it and ends `waiting`. The conductor no longer lists a PR's files itself, nor restates the merge rule's conditions, nor checks the branch is level before each merge for the accepted "up to date" gap (rule 3 checks it).
- **A path-filtered required check that never started** now goes to the owner once it is the only reason left (every other required check finished, the evidence posted), and counts as settled for the run's end: `merge-check` counts it as not started, so it is never `ready` (it used to count as passed in `session` mode).
- **The ticket briefing's merge line** (`templates/ticket-session-prompt.md`) names `workflow merge-check` and the charter, with the merge mode and waived checks still shown. Attended work still says the PR is ready and leaves it, pointing at "is #N ready to merge?".
- **Solo mode's kick-off** now says the kit's "never merge while CI is red" check is `workflow merge-check`. The `accepted_gaps` line is unchanged.
- Docs: `docs/charter.md` says merges are decided by `workflow merge-check` with the charter; `docs/enforcement.md`'s "up to date" gap points at it. Tests: `tests/test_run_merges_on_merge_check.py`.
- **For projects updating:** nothing to do. A run already under way keeps its vendored skills until the kit's update pull request.

**The light review: "build #12 with a light review"** (#121, part of a session budget and a light review, #42).

- **Asked for** as "build #12 with a light review", or "quick build #12" ("light review" is the name; "quick build" is only understood, and isn't the guided start's "quick ticket"). It is never chosen for the person, in attended or unattended work.
- **The shape** (`review-panel` §6): round 1 runs the full panel (Standards, Spec, Correctness, and the security review where it applies) without the UI explorer; if it isn't clean, the fixes get Correctness-only rounds until one is clean, at most 2 more. Each posts its review record unchanged: round 1 as `--kind round` without `explorer`, each Correctness-only round as `--kind round --reviewers correctness`. Anything still open goes to the owner in the PR body.
- **In a run,** when the briefing's review rounds are 1, ticket sessions use the same shape: one round means one full-panel round.
- **The PR body** (`build-ticket`) says "Light review: one round, no UI explorer", adding "plus N Correctness rounds for the fixes" when there were some, above the findings table.
- **The merge rule is unchanged:** CI green, the review record, and the owner's review of kit and CI files all stand. `review-panel`'s findings table is now §7.
- Docs: `docs/flow.md` §3. Tests: `tests/test_light_review.py`.
- **For projects updating:** a profile with `run.review_rounds = 1` now gets the light shape in a run: round 1 without the UI explorer, then up to 2 Correctness-only rounds for its fixes. To keep the explorer in a run's ticket sessions, give the run 2 review rounds or more (the charter's `review.rounds` since #120; `run.review_rounds` for a charter without one).

**The `merge-check` skill: "is #12 ready to merge?", and "Merge it now"** (#84, part of judging a PR without reading code, #39).

- **Asked** "is #12 ready to merge?", "can I merge this?" or "is my change ready?", Claude gathers the pull request's details (`workflow merge-check --fetch` where `gh api` works, else the GitHub MCP tools into files outside the checkout), with the asker's login, runs `workflow merge-check --json`, and answers in the chat, worded for the person's experience, the most important reason first. It posts nothing on GitHub.
- **"Not yet"** gives each reason and what to do, with the fixes as choices: "Review it now" (the review panel), "Bring it up to date" (merge the base in, never a rebase or force-push), "Resolve the conflict" and "Ask Claude to fix it", plus "Not now". A reviewer's question is theirs to answer on GitHub; nothing is resolved for them.
- **"Ready"** gives the try-it link and the things to try first, then "Merge it now" and "Not now". Choosing it checks again, and merges only when the answer is still `ready` on the same head commit, with a merge commit pinned to it (`gh pr merge <n> --merge --match-head-commit <sha>`, or `merge_pull_request` with `merge_method: merge` and `expectedHeadSha`); never `--admin`, a squash, a rebase or auto-merge. A refused merge is reported with its reason, never worked around. For *new to building*: "To undo it, ask Claude to revert #12."
- **The owner's kit and CI files:** the owner gets "Ready once you've read the changes to these files" and "I've read them" before "Merge it now"; anyone else gets "Needs the owner's review". Never in a ticket or conductor session, where merging stays the charter's.
- **`workflow merge-check --fetch` also fetches the asker's permission** (`--asker`), so with no `project.owner` an admin who hasn't commented or reviewed still counts as the owner.
- **The guided start** offers "Check whether #N is ready to merge" for each open pull request it lists. The glossary's "Merge" entry says to ask (other entries are trimmed a little to keep it under 6,000 characters), and the README's "Build one ticket with you there" says to ask before you merge.
- Tests: `tests/test_merge_check_skill.py`, with the guard's decision on the skill's exact merge commands through `decide()` with `ruleset = true`, `ruleset = false` (solo mode) and no setting, in four permission modes: a plain pinned merge gets no decision, `--admin` never is allowed.
- **For projects updating:** nothing to do. The skill comes with the kit's update.

**`workflow merge-check`: the suite's evidence, the run's waivers, and fetching with `gh`** (#81, part of judging a PR without reading code, #39).

- **The suite's evidence** (flow §4.2): where the profile says `ci.none`, or a waiver was used on the head, `workflow evidence`'s report for the head must be on the pull request. It counts when the latest comment from an account with write access whose first line is the report's headline (``**Local full suite on `<sha>`**: passed``, a short SHA of 7 or more counting) says passed for the head, not on a dirty tree. Missing, `FAILED`, for another commit, on a dirty tree or from another account: "Not yet: the tests' results haven't been posted for this commit", with the fix `workflow evidence --base-ref origin/<base>`. Elsewhere a missing report isn't a reason. The headline is written and read by one pair of functions, `evidence.headline` and `evidence.read_headline`.
- **The run's waivers** (flow §4.1): `--charter F` (the approved charter as JSON, the tracking issue as GitHub returns it, or its body, whose run state holds the charter) and `--check-logs DIR` (one file per check, named by its latest check run's id on the head, `<id>`, `<id>.log` or `<id>.txt`; the id is its job's, as `gh run view --log-failed --job <id>` takes it, so a log kept from an earlier run is never read for this one). A required check the charter's `merge.waived_checks` names counts as passed (state `waived`) only when it failed or was cancelled with one of the profile's `ci.killed_markers` in its log and no sign of a real failure there (a failed or errored count, by the profile's suites' regexes or pytest's, an exit code no marker names, or a test reported failed as the runner went); using one makes the evidence required. A charter that isn't approved, valid against the profile, approved by the profile's `project.owner` (a profile naming none takes no waivers) and in `merge.mode` session waives nothing, with a note saying why. Waivers are taken only where `WORKFLOW_ROLE` says ticket or conductor: in an attended session, with no `WORKFLOW_ROLE` (the guard's branch fallback) or with one it doesn't know, `--charter` is ignored, with a note.
- **`--fetch N`** reads every input not given as a file through `gh api`, every page: the pull request, its files, commits, the head's check runs and combined status, the rulesets each in full, the review threads through GraphQL, the reviews, the comments and their authors' permissions (an author GitHub doesn't know has none), and the comparison with the base. A file given wins. Without `gh`, or when a call fails (gh not signed in, say), each input says it couldn't be fetched and to give it as a file; a `--pr` file of another pull request than N, or one that doesn't say its number, is refused; a gh too old for `--slurp` has its pages read one after another. It still exits 0 and is never `ready` with an input missing. The fetcher is `scripts/workflow/fetch.py`.
- Docs: `docs/flow.md` §4.1 and §4.2 say the command applies them. Tests: `tests/test_merge_check_evidence.py`, with a fake `gh` on the PATH in `tests/fake_gh.py` for other commands' tests to reuse (doctor's, #59).
- **For projects updating:** nothing to do.

**`[previews]` in the profile: whether pull requests get try-it links** (#112, part of a preview deploy per PR, #41).

- **Three keys:** `provider` (only `"cloudflare"`, the default), `on` and `access` (the owner's word that Cloudflare Access guards the preview URLs), `on` and `access` both `false` by default. A profile without the section has no previews, so every project behaves as before.
- **Refused by `profile check`** (exit 1, in words): an unknown key in `[previews]`, named; a provider other than `"cloudflare"`; `on` or `access` that isn't true or false (the message shows the value given); and `on = true` without `access = true` in a profile with `[sensitive]` patterns, since a sensitive project's previews must sit behind Access or not be made.
- **Read by the CLI's loader** as `Profile.previews` (`provider`, `on`, `access`), and printed by `workflow profile check` under `previews`, for the preview reader and `merge-check` to come.
- **Written by "Add try-it links"** (#41, to come) through its own pull request: set-up never writes it, and the starter ships only a commented-out example in `templates/profile.toml`. Docs: `docs/profile.md`'s new `[previews]` table. Tests: `tests/test_previews_profile.py`.
- **For projects updating:** nothing to do.

**"Make this project yours": `workflow adopt` rewrites a copy of the starter's names** (#106, part of one starter template, #40).

- **`workflow adopt --owner LOGIN --repo OWNER/NAME --name NAME [--project DIR]`,** run in a checkout, rewrites only these: the profile's `project.owner`, `project.name` and `project.repo` (an `owner` line the profile left out goes in under `repo`); in CODEOWNERS (`.github/`, the root or `docs/`, the first GitHub would read) the profile's old owner becomes the new one on every line, a whole login in any case, never `@old/team` or a longer login; `wrangler.toml`'s top-level `name` and `package.json`'s top-level `name`, both the name in lower case with dashes (accents dropped and letters like `ß` spelled out, other letters outside ASCII left out, at most 63 characters, a Worker's limit); and the README's title, its first `# ` line outside a code fence. It prints each file it changed and what; a second run changes nothing and says "Already yours: nothing to change."
- **Line by line, never re-serialized:** comments, order, formatting and line endings stay as they are, and each rewritten file is read back (TOML, JSON, the profile's own rules) before anything is written. A missing file is skipped with a note, never created.
- **Refused in words, with nothing written** (exit 1): a `--repo` that isn't `owner/name` (or ends in `.git`), an `--owner` that isn't a login (a leading `@` is dropped), a name that makes an empty Worker name or holds control characters or line breaks, an empty `--project`, no profile, a file that is, or is under, a symbolic link, or a line it can't rewrite in place (a multi-line string, say). A write that fails is reported in words; the profile is written last, so running it again finishes the job.
- **The starter's home in one place:** `STARTER_REPO = "medTech-group/pairnexus-starter-web"` beside `KIT_REPO` in `scripts/workflow/updates.py`, and `workflow version --starter` prints it with no network call, so a fork can point at its own starter.
- Docs: the README's command list and "Forking the kit"; `docs/install.md`'s new "A copy of the starter". Tests: `tests/test_adopt.py`, on a temporary checkout shaped like the starter.
- **For projects updating:** nothing to do.

**One support promise, and an issue template for a Claude Code update that breaks the guard or a hook** (#97, part of open-source readiness, #37).

- **The promise,** in the same words in the README's new "Support" section, its status note, `SECURITY.md` and `CONTRIBUTING.md`:
  - best effort, with no guaranteed response time for issues or pull requests;
  - security reports acknowledged within 5 working days;
  - a fix release when a Claude Code update breaks the guard or the hooks.
- **A new issue template, "The guard or a hook stopped working after a Claude Code update"** (`.github/ISSUE_TEMPLATE/claude-code-break.md`). It asks for `claude --version`, `workflow version`, vendored or plugin, what was run and what happened instead, and applies the `claude-code-break` label once the owner creates it. A break that lets a session past the guard is reported privately instead, with **Report a vulnerability** (`SECURITY.md`).
- Docs: the README's "Support", `SECURITY.md` and `CONTRIBUTING.md`. Tests check that the promise reads the same in each file, and what the template asks for (`tests/test_support_promise.py`).
- **For projects updating:** nothing to do. None of these files ship.

**`workflow merge-check`: whether a pull request may merge, as one command** (#80, part of judging a PR without reading code, #39).

- **It reads JSON files and nothing else:** `--pr`, `--files`, `--commits`, `--checks` (the head commit's check runs and statuses, one after another in one file), `--rulesets`, `--threads`, `--reviews`, `--comments`, `--permissions`, `--compare`, an optional `--preview` (`state` built/building/failed/none, `url`, `commit`), and `--asker`. It answers `ready`, `not_yet` or `owner_review`, with every reason that applies. Each reason has an id, wording for *new to building* and for *developer* (unknown counts as new), a fix and an optional action (`review`, `update_branch`, `resolve_conflict`, `fix_checks`). Notes never change the answer. Output is text, or `--json` with each check's name and state. It changes nothing, posts nothing, and always exits 0. Anything it can't read, or wasn't given, is a "couldn't read …" reason, never `ready`.
- **The rules,** each naming the flow §4 item or #30 condition it implements, in `scripts/workflow/merge.py`:
  - required checks: the rulesets' and `ci.required_checks` together, with a note when the two lists differ. A check missing from the head commit counts as pending. A check reported twice counts by its latest result. With neither list naming any, every check that ran counts except the try-it link's. None ran, without `ci.none`: "no checks have run on this commit";
  - GitHub can merge it: open, not a draft, no conflict ("GitHub is still checking" while it's unknown); not behind the base;
  - no unresolved review thread, and no "changes requested" left standing (one followed by that reviewer's approval, or a new review request, doesn't block);
  - a clean review round on the head, or on an earlier commit of the PR with a later clean Correctness pass on the head; a later not-clean pass on the head blocks;
  - under `ci.none`, "the tests' results haven't been posted" until #81 reads the evidence;
  - a preview that failed or is still building blocks; no previews is a note.
  
  Records and reviews are read oldest first by their times. A list shorter than GitHub says (the PR's `changed_files`, `comments` and `commits`, or GraphQL's `totalCount` and `pageInfo`) is "couldn't read …: fetch every page". So is a check, status or base comparison that doesn't name the head commit (a comparison must also start from the base branch). GitHub lists at most 250 commits, which is allowed for; a change of more than 3,000 files can't be read. Every input it can't read is named in the same run.

  A change to protected paths, with everything else holding, is `owner_review`: "Ready once you've read the changes to these files" for `project.owner` (or an admin when the profile names no owner), and "Needs the owner's review" for anyone else. Review records and "changes requested" count only from accounts with `write`, `maintain` or `admin`.
- **Reused, not repeated:** `reviews.read` for the records, the guard's `matches` for protected paths, and `protection.check` for the rulesets' checks. `protection.Report` gains `unsure`: active rulesets it can't tell target the base. Merge-check answers "Not yet" for those. `protection.latest` is the checks-that-ran reader `checks_ran` now shares, with the try-it link's check marked rather than dropped.
- Docs: `docs/flow.md` §4 names the command as the rule's one implementation; a test keeps §4's items and the command's rules in step. Tests: `tests/test_merge_check.py`.
- **For projects updating:** nothing to do.

**The pull request template set-up installs: "In plain words" for every pull request** (#83, part of judging a PR without reading code, #39).

- **The template,** `templates/github/pull_request_template.md`, has `build-ticket`'s headings (#82): `## In plain words`, then `**What changes for you**`, `**How to try it**` and `**What could go wrong**`, each with a one-line prompt under it in an HTML comment, so an unedited pull request shows only the headings. A test reads the headings from both files, so the two can't drift.
- **`workflow pr-template [--existing FILE]`** prints the file to write and changes nothing. With no `--existing`, it prints the kit's template. With one, it prints the headings above the project's template, whose content is kept whole, in its own line endings. A file that already starts with `## In plain words` (after any blank lines and HTML comments) comes back unchanged, with a note, so running it twice adds nothing. An empty file gets the kit's template; one that isn't UTF-8 text, or an empty `--existing`, is refused in words (exit 1). A `.github/PULL_REQUEST_TEMPLATE/` folder is left alone: GitHub picks those through a query string, so the command exits 3 and says to add the headings by hand.
- **`setup-workflow`** gains step 11, beside the issue templates. It prints the template to `.workflow/pr-template.md` and moves it to `.github/pull_request_template.md`, or back over the project's own template, only when the command exits 0. The set-up pull request says it was added, or what was added at the top of the existing one.
- **`update-workflow`** adds it once to a project set up before this: in the first update to this release or a later one, shown in the update PR. One that has the headings already is left as it is, and later updates leave the file to the owner. It isn't a protected path, so the owner changes it freely. The starter (#40) is to take the file from `workflow pr-template` when it is built.
- Docs: `docs/install.md`'s list of what set-up writes, and the README's. Tests: `tests/test_pr_template.py`.
- **For projects updating:** the update adds `.github/pull_request_template.md`, or the "In plain words" headings at the top of yours; a folder of templates gets them by hand.

**"In plain words" at the top of every pull request `build-ticket` opens** (#82, part of judging a PR without reading code, #39).

- **`build-ticket`'s PR body** (step 4) now opens with `## In plain words`, then `**What changes for you**` (one to three sentences about what a user notices), `**How to try it**` (the try-it link and things to click; else where the link will appear, when the project has preview links; else what to check another way, or "Nothing to try: this change is behind the scenes"; for now always the last, as the kit doesn't read preview links yet) and `**What could go wrong**` (easy or hard to undo, and what it could affect). Each heading is on its own line, its text below it. The section is the same for everyone, never worded by experience, and when the `pr` skill is loaded too its sections go below. Below it the body is unchanged: `Closes #<n>`, what was built, how it was tested, the findings table, "Decisions for the owner" and the by-hand checks.
- Docs: `docs/flow.md` §3's pull-request step names "In plain words" first; `docs/glossary.md`'s "pull request" entry says each one the kit opens starts with it (a few words trimmed elsewhere to keep the file under 6,000 characters; no entry lost). Tests: `tests/test_in_plain_words.py`.
- **For projects updating:** nothing to do; pull requests `build-ticket` opens after the next kit update start with the section.

**Review records: each review round leaves one on the pull request** (#79, part of judging a PR without reading code, #39).

- **`workflow review-record`** prints the comment a round or a later Correctness pass posts: a line for people ("Review round 2 on `3f2a9c0`: clean. Reviewers: Standards, Spec, Correctness."), one machine-readable line (`<!-- workflow:review kind=round round=2 commit=<full sha> reviewers=standards,spec,correctness result=clean -->`) and the agents' marker. Flags: `--kind round|pass`, `--round`, `--commit` (the full SHA), `--reviewers` (from `standards`, `spec`, `correctness`, `security`, `explorer`; a `pass` is `correctness` alone), `--clean` or `--not-clean`. A missing field, a short or non-hex SHA, an unknown reviewer or a pass with other reviewers is refused in plain words, with a non-zero exit.
- **The reader** sits in the same module (`scripts/workflow/reviews.py`: `records_in(text)` for one comment, `read(comments)` for a pull request's comments, with who posted each), so the writer and whatever reads records (a `workflow merge-check` is planned) apply the same rules. Only a record line of its own counts, at the start of the line and before any code fence (```` ``` ```` or `~~~`) in the comment: one quoted in a sentence, a list, a quote or a code block, or a malformed one, is skipped, never a crash. When in doubt the reader leaves a line out; the writer's comment has no fence. For `workflow comments` too: a comment id past 20 digits reads as no number, and JSON with a number past Python's digit limit or nested too deeply is refused in words, not with a traceback.
- **The `review-panel` skill** posts a record after every round, whatever it found, and after each later Correctness pass, in attended and unattended sessions alike. `build-ticket` posts the records of the rounds run before its pull request opened, once it does; its findings table stays in the PR body.
- Docs: `docs/flow.md` §3; the glossary's "Review panel". Tests: `tests/test_review_record.py`.
- **For projects updating:** nothing to do.

**"Require these checks": failing tests stop merges once CI has run** (#68, part of the automated GitHub set-up, #38).

- **A third path in the `upgrade-setup` skill,** offer name `require_checks`, offered only through `workflow doctor`'s offer (which `check-setup` and the conductor's pre-flight show) or when you ask. It shows the checks that ran on the base branch's latest commit with their results (already-required ones left out), passing ones ticked by default and failing or pending ones not, saying why; *new to building* gets one plain sentence, a developer the names and "up to date". **Not now** changes nothing.
- **On your own computer, with `gh` signed in as the repository's admin,** it adds the ticked checks to the ruleset protecting the base branch (the kit's own, else the only one) with `workflow protection --require-checks`'s `PUT` sent by `gh api`, after one confirmation that says Claude Code's prompt is expected. Everywhere else, and when several rulesets protect the branch and none is the kit's: the clicks, one screen at a time, with the exact names and "Require branches to be up to date". Not an admin: a ready message for the owner. Either way it reads back with `workflow protection`.
- **Then the profile:** a small pull request adding every name the ruleset now requires to `ci.required_checks` (and `ci.none = false` when it was set), with `<!-- workflow:required-checks -->` in its body; none when the profile already lists them. Checks are only ever added, never removed. In solo mode it waits for the pull request that leaves solo mode.
- **The guard is unchanged.** Its existing decisions on the `PUT`: asked in an attended session with `ruleset = true` or no `ruleset` setting; refused in solo mode, in `bypassPermissions` and `dontAsk` (naming the mode), and in ticket and conductor sessions; the reads allowed.
- Docs: the README's "Protect `main`", `docs/enforcement.md` §1. Tests: `tests/test_protect_main_gh.py` (the guard), `tests/test_upgrade_setup.py` (the wording).
- **For projects updating:** nothing to do.

**The guard sees `Monitor` and `PowerShell`** (#55, part of guard robustness, #33).

- **The guard's matcher adds `Monitor` and `PowerShell`**, in a vendored project's settings and in the plugin's hooks file. Before, neither reached the guard, even in a ticket session.
- **`Monitor`:** its `command` is checked exactly as a Bash command, in every role (a ticket session's `gh run watch` still passes; a push or a deploy through it is refused or asked as through Bash). A WebSocket watch (`ws`, no command) is allowed.
- **`PowerShell`:** the guard can't read it and never parses it. Ticket and conductor sessions are refused it ("the guard can't read PowerShell; use Bash"). In an attended session, a push or a merge in its text (matched in any case, as PowerShell runs it, a backtick line continuation joined) is asked, and refused in solo mode or where nobody is asked; anything else is left alone. The can't-decide fallbacks (`fallback.py`, `fallback.sh`) read a `Monitor` or `PowerShell` command as they read a Bash one.
- Where nobody is asked, the refusal gives the `Monitor` or `PowerShell` command itself to run by hand, never when it holds text matching a sensitive pattern. The hand command now also masks a token assigned with spaces around `=` (PowerShell's `$env:GH_TOKEN = '…'`, or `= '…'`), keeping the spacing as written; `VAR= cmd` keeps its command. A solo-mode refusal of a Bash or `Monitor` command or a GitHub MCP tool whose input matches a sensitive pattern no longer repeats it, neither in the hand command nor in what the kit saw.
- Docs: `docs/enforcement.md` §4 lists the tools the guard sees, and records the release-gate step for item 10 (#36): compare Claude Code's tools reference with that list. Tests: `tests/test_guard_monitor_powershell.py`; `tests/test_vendor_evidence.py`'s matcher assertion now includes the two tools.
- **For projects updating:** nothing to do; the next kit update writes the new matcher into `.claude/settings.json`.

**"Protect `main`" is automatic on your own computer, with `gh`** (#67, part of the automated GitHub set-up, #38).

- **The `upgrade-setup` skill makes the ruleset and the merge settings itself** when the session is local, `gh` is signed in, and the repository reads you as its admin: after one confirmation, worded by experience, it sends `workflow protection --protect`'s ruleset `POST` and merge-settings `PATCH` with `gh api`, reads them back with `workflow protection`, and opens the pull request that leaves solo mode. Claude Code asks you to approve the ruleset command, and the skill says so up front.
- **The checks that already ran** on the base branch's latest commit (`workflow protection --checks-ran`) are offered on the same screen, passing ones and those the profile lists ticked by default. Ticked names go in the ruleset and, in the same pull request, into `ci.required_checks` (never removing one), with the marker `<!-- workflow:required-checks -->` in its body.
- **Everyone else gets the guided clicks:** cloud sessions always, `gh` missing or signed out (with how to sign in), and a ruleset already on the base branch that doesn't protect it, which is read back first and never edited. Not an admin: the ready message for the owner, before anything is tried.
- **Refusals and failures:** a refusal naming a permission mode where nobody is asked is answered with "switch the permission mode and try again", never a retry. A failed step says what was done and what's left, reads back, and gives the clicks for the rest; the ruleset's request is never sent twice.
- **The guard is unchanged.** Its existing decisions on the exact commands the skill runs: the `POST` asked when someone is asked, refused in `bypassPermissions`, `dontAsk` and ticket and conductor sessions; the `PATCH` and the reads allowed, in solo mode and out.
- Docs: the README's "Protect `main`", `docs/enforcement.md` §1. Tests: `tests/test_protect_main_gh.py` (the guard), `tests/test_upgrade_setup.py` (the wording).
- **For projects updating:** nothing to do.

**No `python3`, and the plugin: the hook commands get the same fallback** (#56, part of guard robustness, #33).

- **Without a working `python3`** (missing, a stub, a shim with no version, a non-zero exit), an attended session's guard hook command still applies #53's rule: a push or a merge is asked, and refused in solo mode or in a permission mode where nobody is asked; everything else is left alone. It reads the event's raw text in the new `scripts/workflow/fallback.sh` (POSIX `sh` and `awk`, matched word by word): only a Bash command or a GitHub MCP tool's name, never a file's content. The reason says the guard isn't working and to check `python3 --version` (3.11 or newer).
- **An attended session's guard hook command always exits 0.** Before, a failing `python3`'s exit code was passed on. Ticket and conductor sessions are still refused every tool; the restore commands still pass with the kit missing.
- **The plugin's hooks file** (`hooks/hooks.json`) is now written from `vendor.plugin_hooks()`: the same commands as a vendored project's, rooted at `${CLAUDE_PLUGIN_ROOT}`, with the `python3` check, the old-Python fallback and this one. The plugin is for attended work, so without Python it never refuses every tool (an old `python3` still reads the session's role, as the CLI does), and it asks about a push or a merge in a project with no profile too, as an old `python3` has since 0.1.8. If `fallback.sh` itself is missing (a partial copy of the kit), every tool is asked, with a reason saying the kit is broken. Its session-start hook says what is wrong when `python3` is missing or failing (an old one already did).
- Docs: `docs/install.md`, `docs/enforcement.md`'s "When something is wrong", the README. Tests: `tests/test_guard_no_python.py`; `tests/test_kit_018.py`'s failing-`python3` case now expects exit 0 in an attended session.
- **For projects updating:** nothing to do; the next kit update writes the new hook commands into `.claude/settings.json`.

**When the guard can't decide: pushes and merges wait for the person** (#53, part of guard robustness, #33).

- **The can't-decide fallback.** In an attended session, when the guard raises or runs out of time, the profile is invalid, the hook's event can't be read, or `python3` is older than 3.11, a push or a merge is asked, and refused in solo mode (`ruleset = false`) or in a permission mode where nobody is asked; everything else is left alone. Before, the CLI's errors exited 1 and let every tool through.
- **One definition of a push or a merge** (`git … push`, `gh … pr … merge`, the GitHub MCP tools that push, write files or merge), in the new `scripts/workflow/fallback.py` (Python 3.7 syntax, the standard library and `modes` only), used by the CLI's error paths and the old-Python fallback alike. Solo mode is read from the profile's first plain `ruleset = …` line, so an invalid profile still counts; an unreadable event is read for its tool, command and mode.
- **The reason** says the guard isn't working, why (the error, the profile's error, the Python version) and how to fix it; where nobody is asked it adds how to be asked and to do it by hand, without repeating the command, since nothing could check it for sensitive data.
- **`hook guard` always exits 0 in an attended session**, printing the fallback's decision or nothing (an invalid profile is still reported on stderr). Ticket and conductor sessions, a missing profile, and the other hooks are unchanged.
- Docs: `docs/enforcement.md`'s "When something is wrong", `SECURITY.md`'s scope (a hook failing open where `docs/enforcement.md` says it asks or refuses, in any role), a README row. Tests: `tests/test_guard_cant_decide.py`.
- **For projects updating:** nothing to do.

**Modes that never ask: the guard refuses what it would have asked** (#52, part of guard robustness, #33).

- **The guard reads `permission_mode`** from each tool call. In an attended session, in `bypassPermissions`, `dontAsk` or a mode the kit doesn't know, every ask the guard makes becomes a refusal, solo mode's remaining asks included; in `default`, `acceptEdits`, `auto`, `plan` or with no mode sent, asks stay asks.
- **The refusal** keeps the ask's reason and adds the mode, how to switch it (Shift+Tab, or the mode selector) to be asked, and how to do it by hand (the command for your own terminal, or on GitHub for a GitHub MCP tool). An unknown mode is named.
- **The guard's modes are listed** in `scripts/workflow/modes.py`, in Python 3.7 syntax with no imports, ready for the old-Python fallback (which reads it since #53).
- Denies, allows, and ticket and conductor sessions are unchanged in every mode. Docs: `docs/enforcement.md`'s mode table, the README's "When something goes wrong" row. Tests: `tests/test_guard_modes.py`.
- **For projects updating:** nothing to do. A person who works in `bypassPermissions` now sees the guard's asks refused, with the command to run by hand.

**Solo mode: the guard refuses GitHub-side changes to the base branch** (#46, part of solo mode, #32).

- **In solo mode** (`ruleset = false`), an attended session is refused, never asked: `gh pr merge --admin`, changing the default branch, renaming the base branch, writing its protection, updating or deleting its ref, merging or writing files into it through the API, and a ruleset's `PUT`, `PATCH` or `DELETE`, through `gh api`, `curl`, GraphQL or the GitHub MCP tools. They are read as gh and curl send them (every URL, every value a field may take, decoded paths), and a path, method, body or alias the guard can't read counts as the base branch. Calls to another repository are unchanged.
- **Creating a ruleset is still asked**, since it is how a project leaves solo mode (a `curl` that creates one is now asked in solo mode too). The repository's merge settings are unchanged.
- **The refusal** carries #45's wording; for an MCP tool, the hand command is the `gh` command that does the same.
- Docs: `docs/enforcement.md`'s solo-mode section. Tests: `tests/test_guard_solo_github.py`.
- **For projects updating:** nothing to do. With `ruleset = true` or no setting, and in ticket and conductor sessions, nothing changes.

**Explanations stop, restart, and run during set-up** (#75, part of the quickstart and the glossary, #35).

- **The guided start (`start`):** *developer* (the first question's answer) or "explain less" stops explaining the glossary's words for the rest of the session. "Explain more" reads the glossary again (`.claude/workflow/docs/glossary.md` vendored, the plugin's `docs/glossary.md` otherwise) and explains each word from then on.
- **Set-up (`setup-workflow`):** asks the experience question first, on its own. After a *new to building* answer (or a skipped question), it follows the same rule from `docs/glossary.md` in its clone of the kit, and keeps explanations out of the set-up pull request (its body, files and commit messages). A *developer* answer gets none.
- **The same rule everywhere:** both skills word it as the context hook (#74) does: each word in the glossary's wording, the first time it's used in the session, never again, and never in what is written on GitHub. `tests/test_glossary_explaining.py` pins the key phrases in all three.
- **For projects updating:** nothing to do.

**The context hook explains the glossary's words to someone new to building** (#74, part of the quickstart and the glossary, #35).

- **At the first prompt of an attended session** whose experience is `new` or unknown (from `WORKFLOW_EXPERIENCE`, `.workflow/experience` or `project.experience`, through `resolve_experience`), `workflow hook context` adds the glossary and the rule: explain each of its words in the glossary's wording, in one or two sentences, the first time it's used in the session, never again, and never in what is written on GitHub.
- **Beside, never instead:** after the guided start's nudge, or with the flow when the first prompt is a flow request. Its own `glossary` marker keeps it to once a session, whether or not the guided start is on or the first prompt was a command.
- **Under Claude Code's 10,000-character limit:** the glossary goes in whole on its own or beside the nudge. Beside the whole flow (or for a glossary too long to fit) it adds only the rule and the glossary's path, to read at once, ahead of the flow, so it is within the 2,000 characters Claude sees of a longer string. A failure in this part never costs the flow or the nudge.
- **Where:** `.claude/workflow/docs/glossary.md` when vendored, the plugin's `docs/glossary.md` otherwise. A vendored copy without the glossary (or with an empty or unreadable one) adds nothing until its next kit update.
- **Never** for a developer, in a ticket or conductor session, after the first prompt, or in a project with no profile. The level changes only what is said, never what is checked, refused or merged.
- Docs: `docs/profile.md` ("Experience"). Tests: `tests/test_glossary_context.py`; the guided start's hook tests now run as a developer, and `run_hook` clears `WORKFLOW_EXPERIENCE` as it does `WORKFLOW_ROLE`.
- **For projects updating:** nothing to do.

**The glossary: `docs/glossary.md`** (#73, part of the quickstart and the glossary, #35).

- **One page of plain words** for someone new to building, read by people and by Claude alike, in two parts: "Building words" (repository, branch, `main`, commit, pull request, checks, merge, revert, preview link, cloud session) and "The kit's words" (guided start, experience level, ticket, spec, map, review panel, solo mode, "Protect `main`", unattended run, conductor, profile, "Check the set-up"). Each entry is one or two sentences, then "Why it matters to you:", and links any other glossary word it uses.
- **Its headings are stable anchors** for the quickstart to link to, and the file stays under 6,000 characters, so #35's context hook can add it whole to a session.
- **Vendored** into `.claude/workflow/docs/glossary.md` with the kit's other docs. The guided start's "explain more" now names where to read it.
- `CONTRIBUTING.md` says a new kit term goes into the glossary in the same pull request, and that `domain-modeling` treats it as the kit's glossary. Tests: `tests/test_glossary.py`.
- **For projects updating:** nothing to do. A project's own `GLOSSARY.md` stays its own.

**`workflow protection` builds the requests: protect, require checks, the checks that ran** (#66, part of automated GitHub set-up, #38).

- **`--protect --repo F`** prints the two requests that protect the base branch: the ruleset to create ("Protect <base> (pairnexus-workflow)", active, an empty bypass list, on `~DEFAULT_BRANCH` when the base branch is the default or `refs/heads/<base>`; `deletion`, `non_fast_forward`, `pull_request` with 0 approvals; `required_status_checks` with "up to date" on only when `--check` names are given), and the merge settings (`allow_merge_commit`, `allow_auto_merge`).
- **`--require-checks F --check NAME`** prints the update that adds the names to a ruleset's required checks with "up to date" on, removing nothing and sending only the fields GitHub accepts on an update.
- **`--checks-ran F [--statuses F] --rulesets F --repo F`** lists the checks that ran on a commit, each passing, failing or pending, the latest result of each name, less those already required; the try-it link's Cloudflare check is never offered, and a file holding one page of several is an error.
- It sends nothing: a session sends each request. `--json` for skills and `workflow doctor`. The read-back is unchanged, except that it now refuses JSON's `NaN` and `Infinity` as not JSON. Docs: `docs/protection.md`. Tests: `tests/test_protection_requests.py`.
- **For projects updating:** nothing to do.

**Unattended runs in solo mode: the charter and the conductor's warning** (#50, part of solo mode, #32).

- **The charter in solo mode** (`ruleset = false`): `workflow charter defaults` picks `session` merging, `charter questions` leaves `auto-merge` out of the merge question's new `options` and says why in its `note` (as it now does with no CI or no required checks), and `charter validate` and `state init` refuse `auto-merge`. GitHub auto-merge could merge at once there, since nothing on GitHub reliably requires checks.
- **Removed protection** (`ruleset = true` while `workflow protection` reads the base branch back as unprotected) counts as solo mode too: the conductor passes the new `--unprotected` to `charter defaults`, `questions` and `validate`. Once accepted, the gap's `removed protection: ` line in `accepted_gaps` carries that verdict to every later check, amendments and `state init` included. The rule is one function, `charter.solo_reason`, and the gap's line is `charter.SOLO_GAP`.
- **The conductor's pre-flight** reads the ruleset back with `workflow protection` and, in either case, states the gap plainly: nothing on GitHub stops a mistake reaching `main`, and the kit's "never merge while CI is red" check is the only one. It offers "Protect `main`" (or restoring it) through `upgrade-setup`, or "Go ahead", which goes in `accepted_gaps`. The ticket environment is still required; when the profile names none, the pre-flight now offers "Set up unattended runs" beside the README's Step 5. Projects with `ruleset` left out keep today's ruleset checks.
- **The run report** repeats a solo-mode run's gap under its summary.
- Docs: `docs/charter.md`. Tests: `tests/test_charter_solo.py`.
- **For projects updating:** nothing to do. With `ruleset` left out, nothing changes; with `ruleset = true`, the conductor also reads the protection back before each run.

**Experience in the guided start and kit updates** (#49, part of solo mode, #32).

- **The guided start** (`start`) asks how much the person knows, *new to building* or *developer*, as the session's very first question, only when `workflow status` finds no level. Skipping counts as new.
- **The answer** goes in the untracked `.workflow/experience`, the file `status` reads, only after checking that git ignores it and that nothing but a plain file is there. A cloud session's file lasts for that session, so the guided start says once how to keep it with `WORKFLOW_EXPERIENCE` on the environment. Where the kit isn't set up yet, set-up asks instead, so the question never comes twice. The first-message hook's nudge now says to ask the level first.
- **"Explain less" or "explain more"** changes the level the same way, and the guided start tells Claude the new level when it records one (#35's glossary explanations stop or start on it).
- **In solo mode,** the guided start's look around says so in one line, with what it means, naming the base branch. It doesn't offer "Protect `main`" there, so the offer never nags.
- **Ticket and conductor sessions** are never asked. The level changes wording and pacing only; what the kit writes on GitHub is the same for every level, plain summary first.
- **Kit updates** (`update-workflow`) ask the project's default once when the profile has no `experience`, and write it in the update pull request; while it stays unset, each later update asks once again. `setup-workflow` now says the guided start asks each person whose level is unknown.
- Tests: `tests/test_experience_start.py`.
- **For projects updating:** the update asks the project's experience default once if the profile has none; "Leave it unset" changes nothing.

**Solo mode and experience in the profile, reported by `workflow status`** (#43, the first part of solo mode, #32).

- **`project.ruleset`:** `true` or `false`; `false` is solo mode. Left out, nothing changes. The profile template shows it as a plain `ruleset = …` line, commented out until set-up writes it.
- **`project.experience`:** `"new"` or `"developer"`, the project's default. Left out, the person's own answer counts, else unknown (set-up and the guided start will ask).
- **`workflow profile check`** refuses any other value of either, naming the setting, so a typo never silently turns solo mode off.
- **Experience resolution:** one function, `resolve_experience`, which `status` uses now and the guard's solo-mode tickets will call. `WORKFLOW_EXPERIENCE` wins, then the untracked `.workflow/experience` file, then `project.experience`, else unknown (worded as new to building). An unrecognised value is skipped with a warning that doesn't repeat it; it never raises.
- **`workflow status`** reports `Solo mode:` (yes, no, or not set) and `Experience:` with its source and any warning, in text and in `--json` (`solo_mode`, `experience`).
- Docs: `docs/profile.md` and the template describe both settings. Tests: `tests/test_solo_mode_profile.py`.
- **For projects updating:** nothing to do. Without the two settings, the kit behaves as before.

**Solo mode: the guard refuses git pushes that touch the base branch** (#45, part of solo mode, #32).

- **In solo mode** (`ruleset = false`), an attended session's push to the base branch is refused, never asked: a push to it (a bare push whose upstream it is, or a push from it, included), a force-push or deletion of it, `--mirror`, `--all`, `--prune` with no branch named, and the settings that make every push a mirror or send a bare push to it (set in the command, or already on disk for a bare push).
- **A push whose destination the guard can't tell** (a variable, `@` with no known branch, a glob, a brace list, a detached HEAD, another directory or repository, a git alias that pushes) counts as the base branch in solo mode, and the refusal says to push the branch by name.
- **Force-pushing or deleting a named feature branch is still asked:** the force and delete options are read with their destinations in solo mode. An ask earlier in a command never hides a refusal later in it.
- **The refusal's reason** says why in plain words, explains what `main` is to someone new to building (or of unknown experience), gives the command to run in their own terminal, and tells Claude to offer "Protect `main`" with "Not now". It is built by `guard.solo_refusal`, for the other solo-mode refusals to reuse.
- **When the guard runs out of time** in solo mode, the command is refused, as in ticket sessions.
- **Unchanged:** ticket and conductor sessions, and projects with `ruleset = true` or no setting.
- Docs: `docs/enforcement.md` §4. Tests: `tests/test_guard_solo.py`.
- **For projects updating:** nothing to do. Solo mode only applies once the profile says `ruleset = false`.

**A guard test no longer fails when `WORKFLOW_ROLE` is set** (#132). `test_hook_takes_the_project_roots_branch_when_the_cwd_has_none` clears the variable for its in-process assertions too, not only for the hook it runs, so the local suite passes in ticket sessions and the conductor's. No assertion changed.

**The guard's linear-time tests no longer fail on a busy machine** (#146). Six tests in `tests/test_kit_011_final.py` held a call to a limit in seconds: the seal, GraphQL lexing, `protected_named`, mutation words, a bundled `-R` and many words. Each now times the same call at size n/8 and at size n, in the process's own CPU time, best of five with the garbage collector off (a run past 2 s of CPU, already a regression, ends the repeats early). It fails when the larger size takes 24 times as long or more: linear work takes about 8 times, quadratic about 64. Time other processes take isn't counted, so the tests passed 40 runs in a row beside two busy processes per CPU, with ratios from 4.4 to 8.8 (wall-clock ratios reached 26 there, since a busy machine cuts a long run more often than a short one). Each test still fails when its call is made quadratic, and the bundled `-R` test fails against the 0.1.0 version of the `-R` regex. The two guard tests also check that both sizes reach the same decision, so the path timed is the one meant. No test was removed or skipped.

**`workflow protection` reads back whether the base branch is protected** (#44, part of solo mode, #32). A session hands it the rulesets, each in full, and the repository's settings, as JSON files ([docs/protection.md](docs/protection.md)).

- It says whether the base branch is protected, and lists each missing protection on its own line, in plain words.
- It says "checks not required yet" when no status checks are required, and reports the merge settings.
- `--json` gives the same for skills.
- It asks GitHub nothing and writes nothing. A wrong input is an error, never "protected".
- Anything it can't tell reads as not protected, with a line saying why: a ruleset on `~DEFAULT_BRANCH` without the settings that name the default branch, say.
- The "Protect `main`" upgrade uses it (#47); set-up, the conductor's pre-flight and `workflow doctor` will.

**"Protect `main`": the `upgrade-setup` skill's first path** (#47, part of solo mode, #32). It takes a project from solo mode to a protected base branch, guided click by click. Claude loads it itself when the person asks; it ships vendored and in the plugin.

- **Offered, never as a nag:** when the person asks, and, once their tickets land, in the guard's solo-mode refusal, before an unattended run in solo mode, and by `workflow doctor`. The offers are `protect_main` (solo mode) and `restore_protection` (the profile says protected, GitHub doesn't).
- **By experience:** someone new to building gets one plain screen with "Do it now" and "Not now", and a one-line result; a developer gets the ruleset's settings. The steps are the same.
- **Admin first:** a person who isn't the repository's admin is told so plainly and handed a ready message for the owner, with the links and the clicks.
- **Rulesets read first:** an already protected base branch goes straight to the pull request. It never edits an existing ruleset.
- **The guided clicks:** the ruleset, its required checks when CI has run on the base branch (otherwise "checks not required yet"), and the merge settings, each with a link to its settings page.
- **Read-back** with `workflow protection`; anything missing is shown in plain words, with the click offered again.
- **The pull request that leaves solo mode:** only after a protected read-back, it sets `ruleset = true`. The guard stays in solo mode until the owner merges it.
- Docs: the README's new "Protect `main`" section, with Steps 3 and 4 as its fallback. Tests: `tests/test_upgrade_setup.py`.
- **For projects updating:** nothing to do.

**The solo set-up, and "Set up unattended runs"** (#48, part of solo mode, #32). `setup-workflow` becomes the short set-up for every new project, and the questions only runs need move to the `upgrade-setup` skill's second path in the same change, so every question still has a place.

- **Set-up asks only what attended work needs:** the project's experience default, sensitive data, the explorer, the mode, the owner and an earlier flow, and deploy commands only when it found deploy scripts. Everything else takes the template's default or what exploring found. It asks nothing about areas, environment names, permission modes, merge approvals or releases.
- **It writes `ruleset`** as a plain line: `true` only when the rulesets can be read and `workflow protection` says the base branch is protected, otherwise `false` (solo mode): an unknown counts as unprotected. It writes `experience` from the answer.
- **Its pull request** says "Merge this and start working", with "Protect `main`" and "Set up unattended runs" as optional next steps. The one-time-steps checklist is gone. After the merge, the set-up session offers "Protect `main`" once, with "Not now".
- **"Set up unattended runs"** (offer `set_up_unattended_runs`): in solo mode it offers "Protect `main`" first, with a plain warning when skipped (GitHub won't hold a merge for failing checks); it asks areas, environment names, ticket sessions' permission mode, merge approvals, releases and repair; it shows one guided screen for the two environments (names, `WORKFLOW_ROLE`, no secrets, the setup script); and it writes the answers to the profile in one pull request. Vendored mode only.
- Docs: the README's "Getting started" leads with the solo set-up, with Steps 3 to 5 kept as the upgrades' click-by-click fallback; `docs/install.md` matches. Tests: `tests/test_solo_setup.py`.
- **For projects updating:** nothing changes for projects set up already. The new set-up applies to new projects; "Set up unattended runs" is there when wanted.

## 0.1.10

**The guard reads editing scripts as their tools do, and fails closed when it runs out of time.** In a ticket session the guard refuses a new test-skip or focus marker that an editing script (`sed`, `perl`, `awk`, `vim`, `ed`) or a patch adds. The correctness reviews of 0.1.9 found older ways, all in 0.1.8 already, that a script could add one unseen, and ways to make the guard slow enough to outlast the hook's timeout, which in 0.1.8 doesn't block. Reported and fixed privately, under `SECURITY.md`.

- **A sed script on standard input** (`-f -`, `-f /dev/stdin`) is read from the heredoc, the `<` file or the `cat` piped in, and a `-f` file the guard can't read (not written yet, a device, a directory) is refused: both were read as empty. `/dev/null` reads as empty.
- **stdin is read as bash gives it:** only fd 0's heredocs, here-strings and `<` files are stdin; more than one of them, stdin from another descriptor (`<&3`) or beside another descriptor's input (`3<f`), is refused for an editing command or a patch. A `cat` piped in gets the last of its own inputs and joins files with nothing between them; what anything else pipes in (a group's output too, `( cat f ) 2>/dev/null |`) can't be seen. A sed script is taken from stdin once. A `/dev/` or `/proc/` path other than `/dev/null` isn't read. Text another command pipes into `ed`, or into vim in ex mode, is refused.
- **vim given stdin** (a heredoc, `<` or a pipe) runs it, so it edits its files: in ex mode (`-e`, `-es`, `-Nes` …) stdin is read as commands, otherwise as keys typed, `:` commands among them, which count as added. So a heredoc of keys that removes a marker is refused too; `-c` or ex mode reads it exactly.
- **sed scripts are read by sed's grammar:** an address (`/re/`, `\%re%`) is read only where a command starts, so text that `a`, `i` and `c` write always counts as added, slashes and `s` commands in it included; an `s` inside an address starts no command; and a command followed by more than sed accepts ends the reading, so the rest counts as added.
- **vim's and ed's `s` ends at the end of its line,** as they read it (the closing delimiter can be left out). The lines `a`, `i` and `c` add count as added, and the keys of `normal` and `execute` are read for markers they run into (`normal Oit.only(`).
- **perl and awk:** a string (`"…"`, `q(…)`, a heredoc) is text the code writes, and a regex (`/re/` where a value is expected, `m{…}`, `qr`) only finds. So an `s` command or a regex inside a string is no longer read as one. perl's bracketed `s` takes the replacement's own delimiters, as perl reads it (`s{…}{…}`, `s{…}/…/`, `s(…) […]`), and a quote-like operator takes its delimiter after a space or as any punctuation (`s /a/b/`, `s,a,b,`, `qq,…,`). A hash key `{s}`, or a comment before the delimiter, counts as added; an `s` after a binary operator (`1-s/…/`, `/x/&&s/…/`, `"a" %s/…/`) is still one, and only a method (`->s`), a file test (`-s $f`) or a sigil after a bareword (`my %s`) makes it a name. awk is read as awk: it has no such operators.
- **What a command finds is read as a regex:** a backslash and a letter (`\s`, `\b`) is a class or an anchor, never that letter. What it puts is read as before.
- **A patch's lines are read as the file's text,** without unescaping, so a removed line holding `it\.only\(` doesn't net away an added `it.only(`.
- **Limits on what the guard reads.** Past these, a ticket session's command is refused rather than read in part:
  - an in-place edit's scripts, `-f` files included, are read once per command, however many files it edits, up to 1 MB together (a vim script sourced with `-S` isn't read, as before: it's among the documented limits);
  - patches up to 4 MB together, where a patch past 1 MB was cut off before (given through a `cat` too);
  - a test file a Write replaces, up to 4 MB.
- **A branch name that isn't UTF-8** is read, and matched against `run.ticket_branch`, instead of making the hooks fail.
- **A time budget:** the guard's hook stops 12 seconds after the kit's CLI starts loading, under its 15-second timeout, and refuses the tool in ticket and conductor sessions. Reading the session's role from the branch counts within it, and a role not read in time counts as ticket. In an attended session it reports the error, as for any guard error. It needs `SIGALRM`, so it doesn't apply on Windows.
- **Decisions:**
  - fuzzed against GNU sed 4.9, perl (bracketed `s` with either form of replacement included) and vim's ex mode, running random scripts on a test file: none that they accepted added a marker the guard missed (copies of lines already in the file aside, which the guard has never counted). Against 0.1.9, the new reading refuses scripts that 0.1.9 allowed, and allows some it refused: those were valid scripts 0.1.9 misread, such as `it.only(` at the start of a sed command, which is sed's `i` inserting `t.only(`, or a vim `s` that leaves out its closing delimiter;
  - a sed `#` comment isn't read for markers, and a sed address with its own delimiter (`\%re%d`) is now read as one;
  - perl's bracketed `s{…}{…}` is now read as perl reads it, so `s{foo}{bar}g; s/xit\(/it(/g`, a removal that 0.1.9 refused, is allowed (its 0.1.9 test moved to `tests/test_kit_0110.py`).
- Tests cover each way in, a big `-f` script across 30 test files, the caps and the time budget (`tests/test_kit_0110.py`).
- **For projects updating to 0.1.10:** nothing to do beyond the update.

## 0.1.9

**The guard's script and skip-marker patterns run in linear time.** In a ticket session the guard counts the test-skip markers an editing script (`sed`, `perl`) or an edit adds, and refuses new ones. Two of its patterns could take far longer than the text they read:
- the patterns for an `s` command and an address (`/x/d`) could read a backslash two ways, and backtracked exponentially on a script with many escapes and no closing delimiter: about 3 seconds at 24 escapes, four times longer with every 2 more;
- the `pytest.mark.xfail(… run=False` marker was quadratic on text holding many `xfail(`.

Either could run past the guard hook's timeout, and in 0.1.8 a hook that runs past its timeout doesn't block the command.

- **An editing script is read as `sed` reads it.** A backslash always starts an escape, so `\/` never ends an `s` command or an address, and each pattern runs in linear time. The slow inputs now return in milliseconds.
- **A command's flags** (`g`, perl's `s`) start no new command, though they're still read for markers.
- **A regex class like `\s*`** is no longer taken for an `s` command (an `s` straight after a backslash starts none). So `/^\s*$/d; s/it\.only(/it(/` is read as cleanup plus a removal.
- **An `s` command the guard can't read,** one that never closes, ends the netting. From there on, every skip marker in the script counts as added, and no address is dropped. perl's bracketed `s{…}{…}` is read as an `s` command delimited by `{`, so a pair of them nets as before, while a single one before a removal ends the netting.
- **The xfail marker** stops at the next `xfail(`, so it stays linear with no length limit. It counts each `xfail(… run=False` on its own, where 0.1.8 could count two as one.
- **Decisions:**
  - well-formed `sed` and `perl` scripts are read as before, except that these are now refused:
    - a single perl `s{…}{…}` before a removal;
    - a `\s*` followed by `s` commands with `*` in them (`/\s*a/d; s/x/it.only(/; s/b*/c/; s/d*/e/`), which 0.1.8 read as one command, netting the marker away;
    - a script that inserts a marker after a stray `\s`, which 0.1.8 netted as a removal;
  - on malformed scripts the guard follows `sed`'s reading. Fuzzed against 0.1.8 over 900,000 random scripts (regex classes like `\s*` included), that refused about 25,600 that 0.1.8 allowed, and allowed 249 that it refused. The ones examined were scripts where 0.1.8 found a marker only by misreading the script, not text the file would hold: a marker run into a following `\s` (which `sed` writes as `skips`), `xfail(` joined to a `run=False` past a `)` the script writes, or a marker read across a mismatched address.
- CodeQL flagged the 0.1.8 patterns. Tests cover the slow inputs, an escaped delimiter, flags, regex classes, long xfail arguments, and scripts that never close.
- **For projects updating to 0.1.9:** nothing to do beyond the update.

## 0.1.8

**The hooks fail closed without Python 3.11** (#22). The kit needs Python 3.11 or later as `python3`. With an older one, the entry point exited 1, which Claude Code treats as a hook error and then runs the tool anyway, so every hook failed open, the guard included. With no `python3` at all, the hook command exited 127, which fails open the same way. Cloud sessions have Python 3.11+, so unattended runs weren't affected; a local session on macOS's own `python3` (3.9) was.

- **An older `python3`:** the entry point hands hooks to `scripts/workflow/_old_python.py`, which needs nothing newer than Python 3.7 and never exits non-zero:
  - a ticket or conductor session is refused every tool, saying which Python it found and what it needs. The role comes from `WORKFLOW_ROLE` (anything but `attended`), or with it unset and the kit set up, from a branch matching the profile's `run.ticket_branch` (read from a plain `ticket_branch = "…"` line);
  - an attended session is asked before a push or a merge (`git push`, `gh pr merge`, the GitHub MCP tools that push or merge), and otherwise left alone;
  - the session start says what is wrong and how to fix it.
- **`python3` missing or failing** (vendored projects; a macOS stub without the developer tools, a pyenv shim with no version): the hook command no longer passes on a failed run. It refuses every tool to a ticket or conductor session, read the same way, and the session start says so. An attended session's guard passes the error on as before. Plugin mode, which is attended only, still needs a working `python3` to run its hooks at all.
- `WORKFLOW_ROLE` with a space inside (`atten ded`) is no longer read as `attended` by the hook command when the kit can't run: it counts as ticket, as the CLI reads it.
- A hook event nested too deeply to parse now counts as malformed (the guard refuses it in a ticket or conductor session) instead of failing the hook.
- The kit's CI also installs Python 3.9 and runs the entry point and the vendored hook command on it, and checks the fallback parses as Python 3.7.
- **Docs:** `docs/enforcement.md` §4 lists the old or missing Python among what fails closed. The README's set-up step and "When something goes wrong", and `docs/install.md`, say what happens.
- **For projects updating to 0.1.8:**
  - The update rewrites the kit's hook commands in `.claude/settings.json` (they now check for `python3`), alongside the copy. Review that part of its pull request too.
  - Nothing else to do.

## 0.1.7

Getting the kit ready for outside users and forks.

- **The kit's home in one place.**
  - `KIT_REPO` in `scripts/workflow/updates.py` is the one place code names the kit's GitHub repository.
  - `workflow version --repo` prints it without asking the network, and `workflow version --json` gives it as `kit_repo`.
  - The skills read it from there:
    - `update-workflow` clones the release from the project's own kit home, and falls back to the upstream for copies older than 0.1.7;
    - `setup-workflow` fills the plugin settings snippet with it;
    - `start` hands updating to `update-workflow`, so the clone command lives in one place.
  - The weekly update check (`templates/github/workflow-kit-update.yml`) reads it at run time from the project's copy, and falls back to the upstream, instead of a fixed value.
  - So a fork's projects hear about, and update to, the fork's releases. The README's new "Forking the kit" lists what a fork changes.
  - A test keeps new hard-coded copies of the name out of the files projects receive.
- **Taking part:**
  - `SECURITY.md`: private vulnerability reporting, and what is in scope;
  - `CONTRIBUTING.md`;
  - `CODE_OF_CONDUCT.md`: the Contributor Covenant 2.1;
  - issue templates for this repository.
  - The README has a status note near the top: beta, what it needs, best-effort support.
- An example in the start skill no longer names PAIR's project.
- **For projects updating to 0.1.7:**
  - The update brings the weekly check's new `workflow-kit-update.yml`, since the files set-up copied once are compared with the release's templates. Bring over its change, keeping your own edits (to the schedule, say): the two `KIT` lines in its script replace the fixed `KIT:` value.
  - Nothing else to do.

## 0.1.6

A full audit of the README and docs against what the kit does, with the fixes it called for.

- **Stopping a run releases nothing.** The `workflow:stop` label (or "stop the run" in the conductor's chat) no longer runs an `end` release: a stop means something may be wrong. The ledger and the report say the release was skipped, and the owner can release by hand. The end time, a wind-down and a finished run still release as the charter says. The stop reason is recorded (`owner`, `ends_at`, `wind-down`, `done`).
- **Required approvals.** The conductor's pre-flight reads the ruleset's `required_approving_review_count`. Above 0, no PR a session opens can merge (sessions post as the owner, who can't approve their own PR), so the kick-off says so and recommends the merge mode `owner`.
- **The conductor:**
  - **Resuming in a new session** ("conductor resume #<n>") creates a new wake routine, deletes the old one, and deletes any routine still bound to the old session;
  - **an abandoned kick-off** closes its tracking and by-hand issues as not planned, so `workflow status` doesn't see a run in progress;
  - pre-flight no longer claims to read the account's usage, which it can't.
- **The wake routine's tool.** Ticket sessions find `fire_trigger` with a ToolSearch for the word, not an exact name: in cloud sessions it is `mcp__claude-code-remote__fire_trigger`, not `mcp__Claude_Code_Remote__fire_trigger`.
- **Set-up uses the latest release,** cloned at its tag, never `main` between releases.
- **`update-workflow`:**
  - lists the project's own edits it kept (`vendor update` now prints `kept` in full, not as a count);
  - brings over changes to the files set-up copied once: `workflow-kit.yml`, `workflow-kit-update.yml`, `docs/agents/issue-tracker.md` and the issue templates.
- **`workflow profile check` warns:**
  - when `commands.setup` is set without `commands.setup_check` (the session start never runs it then);
  - when `guard.protected_paths` leaves out `.claude/**` or `.github/workflows/**` (a list there replaces the defaults).
- **The kit's LICENSE** goes into a vendored copy, as `.claude/workflow/LICENSE`.
- **The guided start:**
  - says what "do it" means for a single small change (a branch and a pull request);
  - tells the ticket environment's rules from the conductor's.
- **Docs:**
  - **`docs/profile.md` (new):** every profile setting, its default and what reads it, and the environment variables (`WORKFLOW_ROLE`, `WORKFLOW_UPDATE_CHECK`, `TMPDIR`).
  - **`docs/enforcement.md` §5 (new):** checking the set-up, item by item (README Step 6 follows it).
  - **`docs/charter.md`:**
    - the stop and the end time;
    - required approvals;
    - waivers and the ruleset;
    - what reuse clears;
    - every validation rule;
    - a mention from the owner's own account may not notify (spike.md row 17).
  - **`docs/install.md`:**
    - what refuses both modes;
    - `vendor update`'s three cases;
    - what plugin mode has and hasn't.
  - **`docs/flow.md`:**
    - the `owner` merge mode;
    - when the explorer and the security review run;
    - the handovers;
    - "Anything else" points to `start`, not `ask-matt`.
  - **`docs/proposal.md`** is marked historical.
  - **The profile template:**
    - a `protected_paths` or `test_paths` list replaces the defaults;
    - `setup` needs `setup_check`;
    - `acceptEdits` still asks before shell commands.
- **README:**
  - **Navigation:** a table of contents, and "When something goes wrong" (new).
  - **Set-up:**
    - Python 3.11+ for everyone;
    - the full contents of the set-up PR;
    - plugin-mode differences;
    - the base branch;
    - one repository per session;
    - the browser explorer's Playwright;
    - `WORKFLOW_ROLE` values.
  - **Daily work:**
    - what "ready" means;
    - the accepted blocker forms and areas;
    - building with you there (evidence, check-ins, status lines);
    - the guided start's full choices;
    - which issues count as unsorted.
  - **Runs:** the real kick-off order, watching, stopping, the end time, resuming, usage, and what isn't yet proven.
  - **Updating:** the weekly issue's contents and skipping a version; `/update-workflow` only from 0.1.5 on.
  - **Reference:** a complete "What's in it"; what counts as shipped.
  - **Fixes:** `/resolving-merge-conflicts` was removed from the table (the pinned Matt Pocock skills don't have it), and attended sessions aren't guarded on protected paths.
- **For projects updating to 0.1.6:**
  - From 0.1.4 or earlier, update by saying "Update the workflow kit: clone it at the latest release's tag and follow its `skills/update-workflow/SKILL.md`" rather than `/update-workflow`: older copies of that skill don't clone a release tag.
  - If the profile sets `commands.setup` without `commands.setup_check` (projects set up before 0.1.3), add a check, e.g. `test -d node_modules`: without it, cloud sessions never install the project's dependencies.
  - `profile check` may now warn about `guard.protected_paths`: put the six defaults back in the list.

## 0.1.5

- **Releases.** Each version is a GitHub release with its tag (`v0.1.5`), its notes this changelog's entry. The kit's own `release` workflow publishes it on every push to main, and only from main (`.github/scripts/release.py`):
  - a version is done once it has a release, not merely a tag, and a tag without one gets its release;
  - every version is tried, and a failure fails the run at the end;
  - its first run publishes 0.1.0 to 0.1.4 at the last commit of each;
  - every change to shipped files bumps VERSION, and no one tags by hand.

  Vendored projects take releases only: `update-workflow` clones a release's tag outside the project and follows that release's copy of itself, never `main` between releases.
- **The update check.**
  - `workflow version` gives the kit's version here and the latest release. It reads the latest with `gh api`, else GitHub's public API, and remembers it for six hours (a failed lookup for an hour). A cache or lock it can't read means "don't know". It never updates anything itself.
  - **The session start says when a newer release is out.** It asks first, in at most 8 seconds, so setup keeps the hook's time.
    - Attended sessions are offered the update: `update-workflow` vendored, `/plugin update pairnexus-workflow@pairnexus` as a plugin.
    - Conductor sessions are told to raise it only at a run's kick-off.
    - Ticket sessions are told nothing: they stay on their run's version.
  - **The guided start** offers **"Update the workflow kit to <version>"** first, before anything else, when a newer release is out (not during a run). When an update pull request is already open, it offers **"Carry on: the kit update PR #n"** instead (`workflow status` finds it by its title, "Update the workflow kit to …").
  - **The conductor's kick-off** asks **Update first** or **Run on <this version>**. A run never updates mid-run.
  - **The weekly update check** (`templates/github/workflow-kit-update.yml`, a project's `.github/workflows/workflow-kit-update.yml`):
    - an issue, "Workflow kit update: 0.1.4 → 0.1.5", labelled `owner-task` (created if missing), linking every release since and the full difference;
    - closed once the project catches up;
    - not asked again for a version whose issue was closed as not planned;
    - a warning, not a failure, when the lock has no version.

    It opens an issue, not a pull request: a pull request opened by a workflow's token runs no CI, so a session makes the update pull request instead.
  - `WORKFLOW_UPDATE_CHECK=off` turns the lookup off.
- **For projects updating to 0.1.5:**
  - `update-workflow` adds `.github/workflows/workflow-kit-update.yml` (a protected path, so it's in the owner's update pull request);
  - from 0.1.4, which has no `version` command, find the latest release with `git ls-remote --tags` (the skill says how).
- **README:**
  - "Keeping it up to date" covers releases, the check and the weekly issue;
  - the kit's repository is public.

## 0.1.4

- **The guided start** (`skills/start`): you don't need to remember a command.
  - At the first message of an attended session, Claude asks "What are we working on?", with choices to click (`AskUserQuestion`).
  - The choices come from where the project stands: carry on a planned item, a map decision, a ready ticket or a PR waiting; something new or a change; a fix; sorting new issues; a brand-new project or large effort; an unattended run.
  - It splits a request into items, and proposes a path for each, always offering a spec as well: a quick ticket, finding the cause first, a spec, a map, or adding to an existing issue.
  - It proposes an order, and files each item as an issue (`<!-- workflow:item path=… -->`), so a plan outlives the session. What an item waits for becomes its tickets' `Blocked by`.
  - It offers each next step as a choice: after the interview, the spec, the tickets and each item. It recommends a fresh session after a spec, a build or a map, and commits the session's files before any stop.
  - "Carry on" picks up a PR waiting for you, work an earlier session claimed, a planned item (with its interview's decisions), a spec without tickets, a map decision or a ready ticket.
  - Sorting new issues follows `triage`, with flow §2's rule for a ticket made ready.
  - A clear first request (a question, "build #262", a command) skips the menu. `/start` brings it back any time. `project.guided_start = false` turns the first-message menu off.
- **`workflow status`**: where the project stands, for the guided start:
  - whether the kit is set up, and whether the project is brand new;
  - an unattended run, claimed work and open PRs;
  - planned items, maps, specs and ready tickets;
  - what waits on a person, and new issues to sort.
- **The flow comes into context for the planning commands on their own:** `/to-spec`, `/to-tickets`, `/wayfinder`, `/grill-with-docs`, `/triage`, `/implement` and `/implement-spec`.
- **`flow.md`:**
  - starting with the guided start, and handovers offered as choices;
  - a spec starts from `grill-with-docs` (or a map's decisions) in the same session;
  - the glossary and ADRs are committed with a pull request, and research notes stay on a `research/` branch (§2's new step and checklist line, §1 step 4);
  - a map's spec is linked from its Destination item, and the map is closed once every item has its spec and tickets;
  - an issue triaged to `ready-for-agent` gets a build ticket's `Blocked by`, `Area:` and acceptance criteria;
  - `implement` and `implement-spec` build with `build-ticket`;
  - the map gate is stated in §1, with who applies it.
- **The conductor's kick-off** lists ready tickets of a map whose Destination isn't fully specified, and recommends leaving them out: `workflow ready` doesn't know about maps.
- **`build-ticket`:** in an attended session that builds more than one thing, each ticket gets its own fresh branch, not named like `run.ticket_branch`.
- **For projects updating to 0.1.4:**
  - `update-workflow` also updates the "Workflow" section of the project's `CLAUDE.md`: a session starts with the guided start (the `start` skill: "What are we working on?", or `/start`);
  - nothing changes in the profile unless you want `guided_start = false`.
- **README:**
  - "Using it" opens with the guided start: where to run it, what the first message does, the paths, an example, the handovers, changing course and long sessions;
  - "Planning new work: what happens underneath" covers every step's command, `/wayfinder`, the side trips, and a table of every Matt Pocock skill in a project (who starts it, how it fits, where its files go, the plugin's prefix);
  - a brand-new project, step by step, with its first ticket built attended and its CI as an owner pull request.

## 0.1.3

From probing pair-drop's two cloud environments: both failed to start, because their setup script installed the project's dependencies from the repository's files, and an environment's setup script runs before the repository is there.

- **The project's own dependencies install at session start.** In cloud sessions (`CLAUDE_CODE_REMOTE=true`; a laptop's checkout is its owner's), the profile's `commands.setup` runs from the kit's SessionStart hook whenever the new `commands.setup_check` fails (it exits 0 once setup has run). A cloud session starts from a fresh clone, so this is every new session; a resumed one finds it in place. The session's context says "Project setup … ran" or "FAILED, exit N", never silence. `workflow repair` runs it too, and exits 1 when it fails. The hook's timeout is 600 s, with setup given up to 510 s of it.
- **The environments' setup script holds only machine tools** the cloud image lacks: the new `run.environment_setup`, empty for most projects whatever their stack (Python, Node.js, a frontend or none). The README's step 5 says what goes where, with examples, and that a script reading the repository's files stops every session in that environment.
- **Environments can be shared** by repositories whose setup scripts match, since they hold nothing of one project; a conductor that releases holds that project's secrets and gets its own.
- `setup-workflow` fills in `commands.setup_check` and `run.environment_setup`, and the PR body says "leave Setup script blank" when it is empty.

## 0.1.2

Documentation for owners, from setting up pair-drop with 0.1.1.

- **"Getting started" opens the README,** step by step with every click: GitHub access and plan (once); asking Claude to run `setup-workflow`, and what it asks; merging its PR; the ruleset; "Allow auto-merge"; the two Claude environments; checking it all; then using it (`/next`, an unattended run, changing and stopping one) and keeping it up to date.
- **Why the environment names must match,** and **both environments are per repo**, each with the project's setup script: the conductor runs the project's tests for its own fixes (`conductor_fixes`, on by default) and its release steps. `enforcement.md` no longer says they are "once per account".
- **The ruleset's bypass list is empty** (sessions act through the owner's account, so what the owner may bypass, they may too), **"Allow merge commits" stays on** and **"Require linear history" off** (sessions merge with a merge commit). A CI that skips paths is fixed in CI, by letting each required job report on every PR.
- **The conductor** treats a missing ticket environment as a blocking pre-flight problem, and never starts ticket sessions in another.
- **`setup-workflow`** writes the one-time steps into its PR body with this project's values (check names, environment names, setup script), so the owner can do them from the PR alone, and ends them with a check.
- **The `workflow kit` CI template** runs read-only (`permissions: contents: read`, `persist-credentials: false`).
- `flow.md` names the project's glossary (`GLOSSARY.md`, or its own name), not `CONTEXT.md`.

## 0.1.1

From the practice run on the sandbox repo (run 2026-10-12-words).

- **Agents' posts carry a marker.** Every comment, issue and PR body an agent posts goes out under the owner's account, so "the owner's comments are amendments" couldn't tell them apart. Every agent post now ends with `<!-- workflow:agent -->` (`scripts/workflow/posts.py`):
  - the guard refuses, in ticket and conductor sessions, a post that creates text without it (`gh issue|pr create|comment`, an edit or close with a body or comment, `gh api` to the issue, comment, PR and review endpoints with a `body` field or `--input`, the text-posting GraphQL mutations, and the GitHub MCP tools that post). It looks in the same texts as the sensitive-data check. Labels, assignees, state changes and merges aren't posts; attended sessions aren't asked;
  - `workflow comments --owner <login> --file comments.json [--since-id N]` lists the owner's own words: their comments without the marker;
  - the tracking and by-hand issue templates, the run report and the ticket briefing end posts with it.
- **The owner's answers in the conductor's chat** are recorded on the issue they concern, quoting the owner with `source: "chat <UTC time>"`; such an answer may close the owner task it completes, and a charter change is an amendment with the same source.
- **Readiness** notes a ticket whose body names one of the profile's protected paths ("names protected path <path> (<pattern>): check it isn't an owner task"), matched as the guard matches them (`issues.readiness(protected=…)`); the ticket stays ready, and the conductor lists noted tickets at kick-off for the owner to keep or exclude. The flow says such a change is an `owner-task`, and a ticket fixing a failing or flaky required check is `workflow:infra`.
- **A run waiting on the owner isn't done.** It keeps going, checking in every 60 minutes, only while in-scope tickets are blocked by open owner tasks or are `needs-human` tickets the conductor asked the owner about during the run (`asked_at` in the state); one "waiting on you" note per task or question; it stops at the end time or when nothing remains.
- **Pre-flight** also checks "Require branches to be up to date" (`strict_required_status_checks_policy`), raised as a safety gap when off. `enforcement.md` and `setup-workflow` now advise leaving "Require review from Code Owners" off while sessions act under the owner's account (an author can't approve their own PR), and on when agents have their own GitHub identity.
- **Sessions started are checked:** `get_session` confirms each new session's `permission_mode` (a mode it can read that differs: archived and reported; no field at all: noted once and carried on), and a claim is read back after the label is added (retried once, else the ticket is skipped that check-in).
- **Briefings copied exactly.** `workflow render` ends the briefing with `Briefing <sha256[:12]>`, prints it with `--print` (the default) and keeps a copy with `--out`; the conductor passes it verbatim and records the hash as the ticket's `briefing`. The session writes what it received to `.workflow/briefing.md`, runs `workflow briefing verify --file .workflow/briefing.md` (`Briefing <hash> intact`, `Briefing changed: expected <a>, got <b>` or `no Briefing line`; trailing whitespace ignored) and quotes that line in its first comment; anything but `intact` and the conductor stops the session and retries.
- **The tracking issue's charter section** sits between `<!-- workflow-charter:begin -->` and `<!-- workflow-charter:end -->`; `workflow charter splice --body body.md --charter charter.json --out body.md [--tickets …]` replaces just that section, and refuses a body without the markers.
- **Merging when auto-merge can't be armed:** in `auto-merge` mode, when GitHub refuses because the PR is already clean, whoever tried (the session, or the conductor) re-checks the merge rule and merges with a merge commit. The guard already allowed a ticket session's own merge (`gh pr merge`, `gh api -X PUT …/pulls/<n>/merge`, the MCP merge tool); tests now pin it. The conductor never merges a change to a protected path itself: it goes in `for_owner`.
- **The claim label:** one rule everywhere. The session always removes `workflow:in-progress` when its ticket ends (and `ready-for-agent` on `needs-human`); the conductor removes leftovers.
- **Waking the conductor.** At kick-off the conductor creates a poke-only routine bound to its own session (`wake_trigger` in the state, a required `wake_trigger` slot in the briefing; `null` and `none` if `create_trigger` fails); a ticket session fires it when its ticket ends ("#N merged in #PR", "#N needs-human" or "#N stopped"; `fire_trigger` is a deferred tool loaded with ToolSearch, tried once, never blocking the ticket), the conductor treats the wake as a check-in, and deletes the routine when the run stops.
- **Spike:** rows 8 and 9 verified, rows 4 and 11 partly, by the sandbox run; row 13 (the wake routine end to end, a child's `permission_mode`) not yet.
- **Ticket sessions use no GraphQL.** `gh api graphql` is refused in the ticket role, reads included: auto-merge (`enable_pr_auto_merge`), comments and reads go through the GitHub MCP tools or REST. Three review passes each found a new way for the shell to assemble a query the guard couldn't read (a `#` or quote in another field, `-ifquery=…`, a field name from a variable, brace expansion, `xargs`). The conductor keeps GraphQL, with the dangerous mutations still refused.
- **Ticket sessions also refuse** `gh` aimed at another repository (`-R other/repo`, `GH_REPO`, `GH_HOST`, gh's token variables), a `gh` or `git` command built from a shell function's or script's parameters (`f() { git push "$@"; }; f origin main`; text that mentions one goes in a quoted heredoc), git that runs a program the guard can't see (`rebase --exec`, `bisect run`, `submodule foreach`, `filter-branch`, `difftool`, `mergetool`, editor and diff-driver settings), git writing a protected path through `--output`, `format-patch -o`, `archive -o` or `bundle create`, `gh auth status --show-token`, and curl writes to GitHub with a flag's value joined to it (`-d@q.json`, `-Tfile`, `-K cfg`) or the host in capitals.
- **From the review of 0.1.1:**
  - `workflow comments` reads every shape the conductor fetches: a list, `--paginate --slurp` pages, arrays one after another, `gh issue view --json comments` and the MCP tool's (`author.login`, node ids, the number from the URL); ids compared as numbers; anything else a clear error. The conductor fetches with `gh api --paginate --slurp`.
  - Protected paths in readiness: not in fenced code (unless the prose before it asks for a change "to" or "in" it), not after "don't", "do not" or "never" in their clause, not a file their clause only reads (a clause ends at a sentence's end, a semicolon, a colon or a dash; when in doubt, noted), and a bare dot-name only when it is itself protected; `path#L20` anchors and blob/tree URLs into the repo are read.
  - The marker rule: `gh issue|pr reopen --comment` and commit comments are posts; `--input` JSON without a `body` or `comment`, GraphQL mutations whose arguments (lexed as GraphQL lexes them, with the operation's variable defaults; a fragment on the mutation counts as a post) carry no body, and `--delete-last` aren't; the conductor's GraphQL from `--input` (a file or stdin) is read from its JSON's `query`. `enforcement.md` says the marker is checked in the command's texts as a whole.
  - The evidence report ends with the marker.
  - The conductor: "a check-in is pending" defined (an enabled one-shot routine bound to it; the wake routine never counts), "A check-in is complete" kept apart from "Done"; the path back from a `needs-human` ticket once the owner answers, and how attempts count; `--only` takes every open `workflow:infra` ticket.

## 0.1.0

First version, from the pair-drop weekend run of 9–12 Oct 2026 and two independent reviews of its proposal.

- **The flow** (`docs/flow.md`): plan (optional maps), spec, build tickets with areas, building, the merge rule, unattended runs.
- **The run charter** (`docs/charter.md`, `workflow charter`): the kick-off questions, the one "go", amendments by the owner's comments, the `workflow:stop` kill switch.
- **The conductor** (`skills/conductor`):
  - pre-flight, check-ins and safe stopping;
  - retries, then `needs-human`;
  - lanes by `Area:`, conductor-ops and the ledger, release under a grant, and the final report.
- **build-ticket** and **review-panel**: rounds until clean, with a Correctness pass for any commit after the last round; the findings table; local evidence for the merge rule.
- **The CLI** (`scripts/workflow.py`):
  - readiness (blockers closed as completed, claims by label, owner tasks);
  - the state block with its size limit;
  - briefings rendered with required slots (a briefing with a gap is refused);
  - sharded, resumable evidence by head SHA, compared with the base branch's test count;
  - vendoring with a lockfile (local edits kept, one mode per project).
- **The hooks:**
  - the guard: base-branch pushes, force-pushes, deploys, protected paths, new skip markers and sensitive posts, across Bash, Edit/Write and GitHub's MCP tools;
  - the checklist gate (`WORKFLOW-STATUS`, one nudge per turn, never while already continuing, a safety cap per session);
  - flow context;
  - environment repair.
- **Review round 1** (three independent reviewers, about 100 findings) changed:
  - the guard to allow-lists for ticket sessions (pushes only to ticket branches, GitHub API writes only to issues, comments, labels and PRs), closing every bypass the review found;
  - the guard to fail closed in ticket and conductor sessions;
  - readiness to leave specs and parents out, read more blocker and closing forms, honour native dependencies, and parse areas;
  - vendoring to check everything before writing, keep local edits through `resolve` and orphans, and never drop Matt Pocock's skills;
  - evidence to prove the commit (untracked files, the base branch's count from a worktree, causes in the report);
  - the charter to check limits, waivers and the profile, with `accepted_gaps` and `reuse`;
  - the conductor's own environment (`WORKFLOW_ROLE=conductor`) and an explicit permission mode for ticket sessions.
- **Review round 2** changed:
  - the guard's parsing (quotes, redirects, subshells, heredocs, the working directory) and its allow-lists for ticket sessions;
  - the conductor's mechanics: claims, check-ins, retries, stopping across several check-ins, and archiving;
  - evidence to run the base branch in a worktree, and to report rather than fail when the base has no usable count;
  - vendoring's keep and resolve.
- **Review round 3** (no blockers) changed:
  - the guard: remote mirror and push-default keys, `find` start paths, sensitive text read through `cat`, stdin and pipes, GraphQL queries from variables, deploys run through interpreters, branch switches when the role comes from the branch, the default branch, more in-place writers, patches from heredocs, skip markers counted net of what is removed, and the global git config protected in ticket and conductor sessions;
  - the charter: malformed charters never raise, amendments are checked against the owner, `charter pin-plan`, and `reuse` clears the old plan;
  - `state init` runs the profile check; readiness reads `/pull/` blockers and "blocked by" mid-sentence;
  - the gate: an unchecked line's reason must say why, and its cap is counted per day;
  - the conductor and build-ticket skills: PRs waiting on the owner, auto-merge, path-filtered checks, and merging the base in rather than rebasing.
- **The final Correctness pass** after round 3 changed: a deploy script run with `.`; the default branch sent on stdin from a file or a pipe; a writing `find` from the project root checked against the protected files there by name; a pull request as a blocker, resolved once merged; the gate's reasons read as words; "doesn't" and "won't" read as negations. Two more passes on those fixes: a find from the root is read exactly (a plain `-name … -delete` or `-exec`, matched against every file there, directories holding protected paths and links to them included) or treated as a write into the whole tree; a symlinked root; `--input` from any spelling of stdin; an escaped `default_branch`; `-execdir` run where its match is; `-L` and `-follow`; `$PWD` and `$(pwd)` in paths; non-ASCII `-iname`; and writers run by `xargs`, whose targets are what the producer names exactly (plain `echo` or `printf '%s\n'` words, or a search checked as a tree; `find … -delete` is the way to delete what a find matches from the root), else unknown.
- **Deviations from the proposal, recorded:**
  - the profile is TOML (stdlib `tomllib`), not YAML;
  - `vendor update` writes `<file>.new` for conflicts and `vendor resolve` records a hand merge, rather than an automatic three-way merge;
  - the UI explorer drives Playwright through Bash rather than an MCP server;
  - the run's state lives in the tracking issue's body (refusing corrupt bodies, re-read before each write) rather than on a state branch;
  - the checklist gate nudges once per turn with a safety cap of 40 a day per session, not "at most 2 a session", since ticket sessions end many turns waiting on CI;
  - a team that requires human approval uses `merge.mode: owner` (ready PRs wait for the owner) rather than auto-merge after approval;
  - the charter has no budget field: usage is watched through the account's limits, reported in pre-flight;
  - the marketplace lists the kit at `./`, so a project pins a release by the tag it vendors from, not through the marketplace;
  - tickets start infra first, then by number (the plan's order isn't kept).
- **Enforcement** (`docs/enforcement.md`): the ruleset, the credential-free ticket environment and CODEOWNERS come first; the hooks are defence in depth.
