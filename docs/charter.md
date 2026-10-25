# The run charter

Before an unattended run starts anything, the conductor asks the owner a short set of questions, shows the plan back, and needs one "go". That charter is the run's only source of authority: what it may merge, release and change, what it sets aside, when it stops. It is recorded on the tracking issue, so nothing is inferred later and nothing the charter answers is asked again mid-run. The run waits on the owner only for open owner tasks and for questions it asked about `needs-human` tickets (§4).

## 1. Pre-flight (no questions)

The conductor first works out what it can by itself, so it only asks about real choices:

- **Readiness:** `workflow ready --fetch` (or with `--issues`/`--prs` from the GitHub MCP tools): ready tickets, blocked ones and why, owner tasks in the way, and a suggested order with areas. Its notes on tickets that name a protected path, or whose spec has no clean review, never block: the owner keeps or excludes those tickets at kick-off.
- **Safety:** the conductor runs with `WORKFLOW_ROLE=conductor` and a permission mode that doesn't prompt (where `get_session` doesn't show the mode, it asks the owner); the ticket sessions' environment exists, by name, and the owner confirms it holds no cloud, account or deploy credentials (nothing can read an environment's contents); and the set-up as `workflow doctor` reports it (`docs/enforcement.md` §5): the base branch's ruleset is active, blocks force pushes and deletion, requires the checks and requires branches to be up to date; CODEOWNERS covers the protected paths; the profile passes `profile check`. Each of doctor's gaps, and each line it can't check, is shown first, with its fix. The owner may still go ahead; the charter records each gap they accept in `accepted_gaps`.
- **Solo mode:** the profile says `ruleset = false`, or `ruleset = true` while the base branch reads back as unprotected (removed protection), as `workflow doctor` says in its lines (its read-back is `workflow protection`'s, `docs/protection.md`). Either way it is a safety gap, stated plainly: nothing on GitHub stops a mistake reaching `main`, and the kit's "never merge while CI is red" check is the only one: `workflow merge-check`, which every merge in the run goes through (§4). The kick-off offers "Protect `main`" (or, for removed protection, restoring it), through the `upgrade-setup` skill, or "Go ahead". Accepted, it goes in `accepted_gaps`, and the run report repeats it. The ticket sessions' environment is still required. With `ruleset` left out, nothing changes.
- **Required approvals:** when the ruleset requires approving reviews, no PR a session opens can merge without a person (sessions post as the owner, and GitHub never lets an author approve their own PR), so the merge question recommends `owner`.
- **Leftovers:** open PRs and claimed tickets from an earlier run; the base branch's CI is green.
- **Capacity:** any usage warning a session has reported (the conductor can't read the account's usage directly). Usage grows with `max_sessions`: each ticket session runs the review panel for up to the run's review rounds (§4). In the kick-off this line stays as it is, with the run's estimate beside it (§2).
- **Last run:** the previous tracking issue's charter (label `workflow:run`), to offer "same as last time".

## 2. The questions

Asked in rounds of up to four with `AskUserQuestion` (three rounds for a first run), each with its recommended default first. `workflow charter questions` prints them; `workflow charter defaults` gives defaults that fit the project's profile: the run's size from its `run.preset`, the check-in interval from its `[run]`, release "never" when it has no release steps, and merge `session` when it has no CI or no required checks, or in solo mode.

**A run's size: Light, Normal or Thorough.** The limits question offers three presets first, the profile's `run.preset` recommended (Normal when it has none). Each bundles the levers the kit controls; choosing one sets the charter's `preset`, `limits` (but `ends_at` and `check_in_minutes`) and `review`:

| | Light | Normal | Thorough |
|---|---|---|---|
| `limits.max_parallel` | 1 | the profile's `run.max_parallel` | 3 |
| `limits.max_sessions` | 10 | 40 | 60 |
| `limits.max_retries` | 0 | the profile's `run.max_retries` | 1 |
| `review.rounds` | 1 | the profile's `run.review_rounds` | 3, or the profile's if more |
| `review.explorer` | off | on if the profile has one | on if the profile has one |

- "Has one" means the profile's `ui.explorer` isn't `none`. With `none`, `review.explorer` is always off, and the one page says "no UI explorer (the project has none)".
- The end time and the check-in interval aren't part of a preset: the end time is always asked, and the check-in interval stays the profile's.
- Any single number can still be changed afterwards. The charter keeps its `preset`, and the one page says what changed by comparing the charter with the preset's numbers: "**Normal**, changed: 3 sessions at once".
- The numbers live in one place, `scripts/workflow/presets.py`: `charter questions` gives each preset's under the limits question's `presets`, with `options` (the recommended one first) and `recommended`. The merge question is separate, so solo mode's rule (no `auto-merge`) stands whatever the preset.
- `run.preset` is only the recommended answer: attended builds never read it.

**The estimate.** With the presets, the kick-off shows roughly what the run will use, in sessions and hours, never money (the kit can't read the account's usage or prices), and runs it again on every change of preset or number, so the figure approved is the one for the charter approved:

```
workflow charter estimate charter.json --tickets 7 --runs runs.json --security 13,143 [--now ISO] [--json]
```

- **Input:** the charter (unapproved is fine, and the end time may not be given yet); the number of tickets in the plan, or the plan as `--tickets "13:messages,143:-"` (without it, the charter's `plan`); optionally `--runs`, past runs' `workflow:run` issues as JSON, as the GitHub API returns them, fetched by the session as `workflow ready --issues` takes issues; and `--security`, the planned tickets the review panel would give a security review (an auth, upload, payment or API change).
- **Sessions:** tickets × (1 + `max_retries`), the worst case. With two or more past runs, tickets × their average sessions per ticket (the sum of `attempts` over the tickets they started), never below one per ticket nor above the tries the charter allows (1 + `max_retries`).
- **Hours:** ceil(sessions ÷ `max_parallel`) waves × one hour, or, with two or more past runs, × their average wall time per merged ticket (`started_at`, its latest session's start, to `merged_at`). Rounded to the hour, as "roughly".
- **Past runs** are the five most recent closed `workflow:run` issues with at least one merged ticket, read from their run state (`workflow state get`). Fewer than two means the defaults. An open one (the run in progress) isn't a past run, nor is one with no run state (a kick-off abandoned before the go); a body whose run state can't be read is skipped with a note, never a crash. The GitHub MCP tools' wrapped lists (`{"issues": […]}`) and `gh api --paginate --slurp`'s pages are read as one list.
- **Warnings,** in words, never blocking:
  - the end time stops the run before its tickets are done ("The end time stops it after about 5 of 7 tickets");
  - `max_sessions` is below the tickets' first tries plus retries ("10 sessions in all covers 7 tickets with 3 retries");
  - the run's review (`presets.review_of`) is lighter than the project's default (the profile's rounds and explorer) while `--security` names a ticket.
- **Output:** one plain line, "About 14 ticket sessions over roughly 7 hours (7 tickets, up to 1 retry each), plus the conductor's check-ins", its basis ("assuming about an hour a session", or "from your last 3 runs: …"), and the warnings. Runs skipped are notes on stderr. `--json` gives `sessions`, `hours`, `basis`, `runs_used` (0 with the defaults) and `warnings`, plus `line`, `tickets` and `notes`.
- **On the one page:** `charter markdown` and `charter splice` take that JSON as `--estimate estimate.json` and add "**Estimate:** …" with its basis (and its warnings under it) beside the size and review, so the tracking issue records what the owner expected. The conductor keeps the approved estimate in the run state as `estimate`, splices with it after each amendment, and runs it again for an amendment that changes the limits, the review or the plan.

**Solo mode never uses GitHub auto-merge.** Nothing on GitHub reliably requires checks there, so auto-merge could merge a PR at once, without waiting for checks. In solo mode `charter defaults` picks `session`, `charter questions` leaves `auto-merge` out of the merge question's `options` and says why in its `note` (as it does with no CI or no required checks), and `charter validate` and `state init` refuse a charter with `auto-merge`.

For removed protection the profile still says `ruleset = true`, so the conductor passes `--unprotected` (the read-back's verdict) to `defaults`, `questions` and `validate`. Once the owner accepts the gap, its `accepted_gaps` line starts `removed protection: `, and the charter carries the verdict itself: every later check refuses `auto-merge`, amendments included. The rule is one function, `charter.solo_reason`.

**With a merge queue, no waivers.** Where the base's ruleset requires a merge queue (#243), every merge goes through the queue, and only a direct merge could take a waiver. The merge modes keep their names (§5 says what each means with the queue). The conductor passes the queue's state as it reads it from the ruleset at that moment (at kick-off, and again for an amendment's `validate`), `--queue on` or `--queue off`, to `charter questions`, `charter validate` and `state init`. A merge-queue rule in a ruleset the kit can't judge counts as `on` here, as `merge-check` counts it for waivers. With it on, the merge question no longer asks about waivers and its `note` says "No waivers", and `validate` and `state init` refuse a charter with `merge.waived_checks`. With it off, or not given, nothing changes. `workflow merge-check` refuses waivers too whenever the queue is on, so a run whose queue is turned on mid-run stops applying them from then on.

The accepted gap's line is fixed, so the run report can find it (`charter.SOLO_GAP`, with the base branch's name):

```
solo mode: nothing on GitHub stops a mistake reaching main; the kit's "never merge while CI is red" check is the only one
```

| Key | Question | Recommended default |
|---|---|---|
| `scope` | Which tickets? Any to exclude? Also tickets unblocked during the run? | Every ready ticket; yes |
| `limits` | How big a run: Light, Normal or Thorough (sets `limits` and `review`)? When does the run end? Check-in cadence? | The profile's `run.preset` (Normal: the profile's `run.max_parallel` at once, 40 in all, its `run.max_retries` then `needs-human`, its rounds and explorer); the owner's end time; 20 minutes |
| `merge` | Merge automatically when a ticket passes the merge rule? Which checks may be waived when killed (not failed)? | GitHub auto-merge (`session` with no CI, no required checks or in solo mode; `owner` when the ruleset requires approvals); none waived. A waiver needs mode `session`, and the check taken out of the ruleset's required checks for the run, which pre-flight then shows as a gap to accept |
| `release` | Deploy and build after merges? Never, each merge, or once at the end? Which of the profile's release steps? | Once at the end, the first release step, with its smoke test; never when the profile has none |
| `outward` | Any change outside the repo (cloud, secrets, accounts, DNS, payments)? Which, exactly? | None: listed as owner tasks |
| `conductor_fixes` | May the conductor open its own PRs for test, CI or deploy-script problems? | Yes, each reviewed and logged |
| `open_decisions` | A product decision the ticket leaves open: decide-and-record, or set the ticket aside? | Decide-and-record in the PR |
| `stop_run_on` | Anything that stops the whole run rather than being set aside? | Nothing |
| `notify` | Failures and the final report: the tracking issue only, or also a mention (and a phone notification where the session can send one)? | Issue for failures; push for the final report |

When a previous charter exists, start from `workflow charter reuse old.json` (it keeps `preset` and `review`; approval, amendments, accepted gaps, plan and end time cleared, and a ticket list that was the old plan reset to every ready ticket) and ask: "Same as last time?", showing the tickets ready now and `workflow charter diff`. Ask again only what the owner wants changed, and always the end time.

"push" means: the conductor @mentions the owner (`project.owner` in the profile) in the comment, and also sends a phone notification where the session has a tool for it. The mention alone may not reach the owner: the comment goes out under the owner's own account, and GitHub doesn't notify anyone of their own comments. To be told, watch the tracking issue (Subscribe) or check it; spike.md row 17.

## 3. The charter shown back

`workflow charter markdown charter.json --tickets "13:messages,143:-"` renders the one page: the plan (tickets in order with their areas), what it will and won't do, what goes on the owner's lists, the limits and the end time, the size (the preset and what changed from it) and the review, the estimate (with `--estimate`, §2), accepted gaps, and the kill switch. The owner replies "go". The conductor:

1. sets `approved` to `{by, at, source}`: `by` is the profile's `project.owner`; `source` is the URL of the owner's comment on the tracking issue, or the owner's words quoted with the time when the go came in chat;
2. checks it: `workflow charter validate charter.json --approved` (also against the profile's release steps);
3. puts it in the tracking issue's state block (`workflow state put`) and the rendered page in the issue body's charter section, between `<!-- workflow-charter:begin -->` and `<!-- workflow-charter:end -->` (`workflow charter splice`).

## 4. During the run

- **The ticket sessions' review comes from the charter.** Each ticket session's briefing (`workflow render`, from `templates/ticket-session-prompt.md`) takes its review rounds and UI explorer from the approved charter, through `presets.review_of`: its `review`; without one, its `preset`'s numbers; and for a charter written before presets, the profile's `run.review_rounds` and `ui.explorer`, as before. With `review.explorer` false the briefing's explorer is `none`; with it true, the profile's `ui.explorer`. Rounds of 1 brief as "1 (the light review)" and the explorer as `none`, so the session takes the light review's shape (`review-panel` §6), which runs no explorer. The skills a session follows take the briefing's rounds and explorer over the profile's.
- **A charter change is checked when it is written.** `workflow state patch` and `workflow state put` run `charter validate --approved`'s checks against the profile on disk whenever the charter in the state changes, refuse the write listing the same problems and leave the state unchanged. A change that drops the `removed protection:` line from the state's current charter is refused too (a `put` over a block that isn't JSON has none to compare with): the charter carries that verdict until the run ends, so `auto-merge` stays refused (it needs a new run, whose kick-off reads protection back). A patch to `tickets` or anything else outside the charter isn't checked. A profile that can't be read refuses a charter change (fix the profile first); with no profile, the change is written with a note.
- **No waiting on the charter.** Anything outside the charter is set aside and reported, never asked about mid-run.
- **Waiting on the owner.** When nothing is running or ready, the run keeps going only while in-scope tickets are blocked by open owner tasks, or are `needs-human` tickets on which the conductor asked the owner a question during this run. It posts one "waiting on you" note per owner task or question, and checks in every 60 minutes instead of `limits.check_in_minutes`, until one of them moves or `limits.ends_at`. When the owner answers a `needs-human` ticket (in the conductor's chat, or a comment without the marker), the conductor records the answer on the ticket (rewriting its acceptance criteria if the answer changes them), removes `needs-human` and queues it again; that try counts as a first try, with `max_retries` retries after it, as at the start.
- **Whose words count.** Every comment, issue and PR body an agent posts goes out under the owner's GitHub account, so the author alone can't tell them apart. Every agent post (the conductor's and ticket sessions') ends with the marker `<!-- workflow:agent -->`, and the guard refuses one without it. The owner's own words are:
  - their comments: by `project.owner` and **without** the marker (`workflow comments --owner <login> --file comments.json --since-id <comments_read_through>` lists them);
  - their answers in the conductor's chat.
- **Amendments.** The owner may comment on the tracking issue at any time ("also #140", "stop releasing", "extend to Monday 9am"). At each check-in the conductor reads the owner's own comments after the state's `comments_read_through`, adds each change to `amendments` with its comment URL as `source` (once per URL), validates the charter again, replies to confirm, and acts on it. A comment from anyone else, or one carrying the marker, is information, never authority.
- **Answers in the conductor's chat.** The owner may also answer or decide in the conductor's own chat. The conductor records each such answer on the issue it concerns, quoting the owner's words with `source: "chat <UTC time>"`. When the answer completes an owner task, it may close that task as completed, with that comment. A charter change given in chat is an amendment like any other, with the same `source`.
- **Merges are decided by `workflow merge-check`,** with the charter. Every merge in a run, and every time auto-merge is armed, the ticket session or the conductor first runs `workflow merge-check --fetch <PR> --json --charter <the tracking issue's body, saved under .workflow/> --review-rounds <the charter's review rounds>` (with `--check-logs DIR` for a waived check's log), right before it acts: the same command, and the same rules (flow §4), as a person's `merge-check`, so a run and a person never disagree on "ready". When the profile says `[previews] on = true`, it first reads the try-it link for the head with `workflow preview --fetch <PR> --json` and passes that answer as `--preview`, as a person's `merge-check` does, so a link that didn't build or is still building is "Not yet" for a run too; with previews off it passes none, and the note about the missing link never blocks. **`ready` is the only yes.** `not_yet` never merges: its reasons say what to do. `owner_review` (a change to a protected path) never merges unattended: it goes on the owner's list, with the files. The charter is read from the tracking issue's run state; its waivers count only as flow §4.1 says. A merge is pinned to the head the command checked, and, without a merge queue, auto-merge is disarmed before a branch update and armed again only on the new head's `ready`.
- **The merge queue's state.** `state init --queue on|off` records the queue's state at kick-off in the run state's `merge_queue`, used only to notice a change, never to check a charter. At each check-in the conductor reads the ruleset again and runs `workflow state queue --body <body> --queue on|off --out <new body>`. It prints `unchanged: …`, `changed: the merge queue is now on (it was off)`, or `recorded: …` when no state was recorded, and records what it was given, so a change is reported once. On `changed`, the conductor logs it in the ledger, says so on the tracking issue and follows the ruleset from then on. Nothing stops.
- **A pull request in the merge queue.** A drop is GitHub taking a pull request out of the queue without merging it. With the queue on, the conductor gives each answer to queueing a ticket's pull request (`PUT pulls/<n>/merge-async` with `merge_action: merge_queue`, pinned to the head) to `workflow state drop --body <body> --ticket <n> --head <full sha> --answer <answer> --out <new body>`, where the answer is `202-enqueued` (accepted, and read back as in the queue), `202-pending` (accepted, still pending), `200-waiting` ("already in a merge queue"), `200-merged`, `409`, `failed` or `refused` (400, 403 or 422). It prints what to do, and records it on the ticket, so it is run once per answer, on the body last written to the tracking issue:
  - `in_queue`: the head's first accepted enqueue; a head is in the queue from the first answer that shows it there, this or `200-waiting`;
  - `waiting`: still waiting in the queue, never a drop;
  - `merged`: done;
  - `retry`: `202-pending`, `409`, `refused` or `failed`, tried again at the next check-in, never a drop;
  - `requeued`: a later `202-enqueued` of a head already in the queue means it was dropped, and the first drop on that head is simply queued again;
  - `merge_base`: the second drop on the same head; the conductor merges the base in, pinned;
  - `needs_human`: any drop once the base was merged in, whatever the head, or a third `failed` on one head.

  The ticket keeps the heads seen in the queue with their drops (`queue_heads`), the `failed` answers per head (`queue_failed`), whether the base was merged in (`base_merged`) and the last decision (`queue_result`). A new head's first `202-enqueued` is never a drop. `base_merged` is set when `merge_base` is printed, so if merging the base in then fails, the next drop is `needs_human`: a person is brought in rather than the base tried again. `state drop` leaves the ticket's `status` alone: on `needs_human` the conductor takes the usual `needs-human` steps.
- **Merging when auto-merge can't be armed.** Without a merge queue, in `merge.mode: auto-merge`, GitHub refuses to enable auto-merge on a PR that is already mergeable (clean). Whoever tried (the ticket session, or the conductor) then runs `workflow merge-check` again at that moment, and on `ready` merges with a merge commit, pinned to the head it checked. The charter's `auto-merge` grant covers that merge. The conductor never merges a change to a protected path itself: `merge-check` answers `owner_review`, and that PR goes on the owner's list.
- **Kill switch.** The `workflow:stop` label on the tracking issue (or "stop the run" in the conductor's chat): from the next check-in the conductor interrupts the running sessions, waits until each branch stops moving (up to 3 check-ins) and archives them, records `stopped`, and writes the final report. **A stop releases nothing**, whatever `release.when` says: the report says the owner can release by hand.
- **The end time** is a hard stop, not "start nothing new": at `limits.ends_at` the conductor stops running sessions the same way, then releases if `release.when` is `end`.

## 5. The schema

```json
{
  "version": 1,
  "scope":   {"tickets": "all-ready", "exclude": [143], "follow_unblocked": true},
  "limits":  {"ends_at": "2026-10-13T03:30:00Z", "max_parallel": 2, "max_sessions": 40, "max_retries": 1, "check_in_minutes": 20},
  "preset":  "normal",
  "review":  {"rounds": 3, "explorer": true},
  "merge":   {"mode": "session", "waived_checks": ["Backend tests (seam 1)"]},
  "release": {"when": "end", "steps": ["deploy poc"], "smoke_test": true},
  "plan":    [146, 147, 148],
  "outward": {"allowed": ["set Parameter Store timer-secret on poc"]},
  "conductor_fixes": true,
  "open_decisions": "decide-and-record",
  "stop_run_on": [],
  "notify":  {"failures": "issue", "final_report": "push"},
  "accepted_gaps": ["no ruleset on main yet"],
  "approved": {"by": "owner-login", "at": "2026-10-11T10:00:00Z", "source": "https://github.com/…/issues/232#issuecomment-…"},
  "amendments": [{"at": "…", "by": "owner-login", "change": "also build #140 and #146", "source": "…"}]
}
```

`preset`: `light`, `normal` or `thorough`, the one chosen. `review`: `rounds`, the review panel's rounds at most, and `explorer`, whether the UI explorer runs. A charter written before presets has neither: it stays valid and reads as Normal, the profile's `run.review_rounds` and UI explorer, as before. A `preset` without `review` reviews as its preset's numbers. `presets.review_of` gives the review a charter means.

`merge.mode`: `auto-merge` (GitHub merges once the ruleset's checks pass; no waivers), `session` (the ticket session, or the conductor, merges under the merge rule), `owner` (nothing merges unattended). With the merge queue on, the modes keep their names and no check is waived: in `auto-merge` GitHub's auto-merge is never armed, and whoever first sees `merge-check` say `ready`, the ticket session or a conductor check-in, adds the pull request to the queue, pinned to the head; in `session` the ticket session adds it, pinned, after its own final `merge-check` says `ready`; in `owner` nothing is queued unattended. `release.when`: `never`, `end`, `each-merge`. Validation (`workflow charter validate`) also requires:
- `ends_at` in the future and after the approval;
- `max_parallel` 1–16, `max_sessions` 1–500 and no fewer than `max_parallel`, `max_retries` 0–5, `check_in_minutes` 5–240;
- `preset` one of `light`, `normal`, `thorough` when given; `review.rounds` 1–10 and `review.explorer` true or false when `review` is given;
- `review.explorer` false when the profile's `ui.explorer` is `none`;
- no keys it doesn't know;
- no waived checks with the merge queue on (`--queue on`);
- waived checks among the profile's required checks, and no `auto-merge` when the profile has no CI or no required checks, or in solo mode (`--unprotected`, or a `removed protection: ` gap, for removed protection);
- release steps among the profile's;
- `approved.by` and each amendment's `by` to be the profile's `project.owner`.
