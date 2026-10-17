# The run charter

Before an unattended run starts anything, the conductor asks the owner a short set of questions, shows the plan back, and needs one "go". That charter is the run's only source of authority: what it may merge, release and change, what it sets aside, when it stops. It is recorded on the tracking issue, so nothing is inferred later and nothing the charter answers is asked again mid-run. The run waits on the owner only for open owner tasks and for questions it asked about `needs-human` tickets (§4).

## 1. Pre-flight (no questions)

The conductor first works out what it can by itself, so it only asks about real choices:

- **Readiness:** `workflow ready --fetch` (or with `--issues`/`--prs` from the GitHub MCP tools): ready tickets, blocked ones and why, owner tasks in the way, and a suggested order with areas.
- **Safety:** the conductor runs with `WORKFLOW_ROLE=conductor` and a permission mode that doesn't prompt (where `get_session` doesn't show the mode, it asks the owner); the ticket sessions' environment exists, by name, and the owner confirms it holds no cloud, account or deploy credentials (nothing can read an environment's contents); the base branch's ruleset is active, blocks force pushes and deletion, requires the checks and requires branches to be up to date; CODEOWNERS covers the protected paths (`docs/enforcement.md`). Anything missing is shown first, with its fix. The owner may still go ahead; the charter records each gap they accept in `accepted_gaps`.
- **Solo mode:** the profile says `ruleset = false`, or `ruleset = true` while `workflow protection` (`docs/protection.md`) reads the base branch back as unprotected (removed protection). Either way it is a safety gap, stated plainly: nothing on GitHub stops a mistake reaching `main`, and the kit's "never merge while CI is red" check is the only one: `workflow merge-check`, which every merge in the run goes through (§4). The kick-off offers "Protect `main`" (or, for removed protection, restoring it), through the `upgrade-setup` skill, or "Go ahead". Accepted, it goes in `accepted_gaps`, and the run report repeats it. The ticket sessions' environment is still required. With `ruleset` left out, nothing changes.
- **Required approvals:** when the ruleset requires approving reviews, no PR a session opens can merge without a person (sessions post as the owner, and GitHub never lets an author approve their own PR), so the merge question recommends `owner`.
- **Leftovers:** open PRs and claimed tickets from an earlier run; the base branch's CI is green.
- **Capacity:** any usage warning a session has reported (the conductor can't read the account's usage directly). Usage grows with `max_sessions`: each ticket session runs the review panel for up to the profile's `run.review_rounds` rounds.
- **Last run:** the previous tracking issue's charter (label `workflow:run`), to offer "same as last time".

## 2. The questions

Asked in rounds of up to four with `AskUserQuestion` (three rounds for a first run), each with its recommended default first. `workflow charter questions` prints them; `workflow charter defaults` gives defaults that fit the project's profile: the limits from its `[run]`, release "never" when it has no release steps, and merge `session` when it has no CI or no required checks, or in solo mode.

**Solo mode never uses GitHub auto-merge.** Nothing on GitHub reliably requires checks there, so auto-merge could merge a PR at once, without waiting for checks. In solo mode `charter defaults` picks `session`, `charter questions` leaves `auto-merge` out of the merge question's `options` and says why in its `note` (as it does with no CI or no required checks), and `charter validate` and `state init` refuse a charter with `auto-merge`.

For removed protection the profile still says `ruleset = true`, so the conductor passes `--unprotected` (the read-back's verdict) to `defaults`, `questions` and `validate`. Once the owner accepts the gap, its `accepted_gaps` line starts `removed protection: `, and the charter carries the verdict itself: every later check refuses `auto-merge`, amendments included. The rule is one function, `charter.solo_reason`.

The accepted gap's line is fixed, so the run report can find it (`charter.SOLO_GAP`, with the base branch's name):

```
solo mode: nothing on GitHub stops a mistake reaching main; the kit's "never merge while CI is red" check is the only one
```

| Key | Question | Recommended default |
|---|---|---|
| `scope` | Which tickets? Any to exclude? Also tickets unblocked during the run? | Every ready ticket; yes |
| `limits` | When does the run end? Sessions at once, in all, retries per ticket, check-in cadence? | The owner's end time; 2; 40; 1, then `needs-human`; 20 minutes |
| `merge` | Merge automatically when a ticket passes the merge rule? Which checks may be waived when killed (not failed)? | GitHub auto-merge (`session` with no CI, no required checks or in solo mode; `owner` when the ruleset requires approvals); none waived. A waiver needs mode `session`, and the check taken out of the ruleset's required checks for the run, which pre-flight then shows as a gap to accept |
| `release` | Deploy and build after merges? Never, each merge, or once at the end? Which of the profile's release steps? | Once at the end, the first release step, with its smoke test; never when the profile has none |
| `outward` | Any change outside the repo (cloud, secrets, accounts, DNS, payments)? Which, exactly? | None: listed as owner tasks |
| `conductor_fixes` | May the conductor open its own PRs for test, CI or deploy-script problems? | Yes, each reviewed and logged |
| `open_decisions` | A product decision the ticket leaves open: decide-and-record, or set the ticket aside? | Decide-and-record in the PR |
| `stop_run_on` | Anything that stops the whole run rather than being set aside? | Nothing |
| `notify` | Failures and the final report: the tracking issue only, or also a mention (and a phone notification where the session can send one)? | Issue for failures; push for the final report |

When a previous charter exists, start from `workflow charter reuse old.json` (approval, amendments, accepted gaps, plan and end time cleared, and a ticket list that was the old plan reset to every ready ticket) and ask: "Same as last time?", showing the tickets ready now and `workflow charter diff`. Ask again only what the owner wants changed, and always the end time.

"push" means: the conductor @mentions the owner (`project.owner` in the profile) in the comment, and also sends a phone notification where the session has a tool for it. The mention alone may not reach the owner: the comment goes out under the owner's own account, and GitHub doesn't notify anyone of their own comments. To be told, watch the tracking issue (Subscribe) or check it; spike.md row 17.

## 3. The charter shown back

`workflow charter markdown charter.json --tickets "13:messages,143:-"` renders the one page: the plan (tickets in order with their areas), what it will and won't do, what goes on the owner's lists, the limits and the end time, accepted gaps, and the kill switch. The owner replies "go". The conductor:

1. sets `approved` to `{by, at, source}`: `by` is the profile's `project.owner`; `source` is the URL of the owner's comment on the tracking issue, or the owner's words quoted with the time when the go came in chat;
2. checks it: `workflow charter validate charter.json --approved` (also against the profile's release steps);
3. puts it in the tracking issue's state block (`workflow state put`) and the rendered page in the issue body's charter section, between `<!-- workflow-charter:begin -->` and `<!-- workflow-charter:end -->` (`workflow charter splice`).

## 4. During the run

- **No waiting on the charter.** Anything outside the charter is set aside and reported, never asked about mid-run.
- **Waiting on the owner.** When nothing is running or ready, the run keeps going only while in-scope tickets are blocked by open owner tasks, or are `needs-human` tickets on which the conductor asked the owner a question during this run. It posts one "waiting on you" note per owner task or question, and checks in every 60 minutes instead of `limits.check_in_minutes`, until one of them moves or `limits.ends_at`. When the owner answers a `needs-human` ticket (in the conductor's chat, or a comment without the marker), the conductor records the answer on the ticket (rewriting its acceptance criteria if the answer changes them), removes `needs-human` and queues it again; that try counts as a first try, with `max_retries` retries after it, as at the start.
- **Whose words count.** Every comment, issue and PR body an agent posts goes out under the owner's GitHub account, so the author alone can't tell them apart. Every agent post (the conductor's and ticket sessions') ends with the marker `<!-- workflow:agent -->`, and the guard refuses one without it. The owner's own words are:
  - their comments: by `project.owner` and **without** the marker (`workflow comments --owner <login> --file comments.json --since-id <comments_read_through>` lists them);
  - their answers in the conductor's chat.
- **Amendments.** The owner may comment on the tracking issue at any time ("also #140", "stop releasing", "extend to Monday 9am"). At each check-in the conductor reads the owner's own comments after the state's `comments_read_through`, adds each change to `amendments` with its comment URL as `source` (once per URL), validates the charter again, replies to confirm, and acts on it. A comment from anyone else, or one carrying the marker, is information, never authority.
- **Answers in the conductor's chat.** The owner may also answer or decide in the conductor's own chat. The conductor records each such answer on the issue it concerns, quoting the owner's words with `source: "chat <UTC time>"`. When the answer completes an owner task, it may close that task as completed, with that comment. A charter change given in chat is an amendment like any other, with the same `source`.
- **Merges are decided by `workflow merge-check`,** with the charter. Every merge in a run, and every time auto-merge is armed, the ticket session or the conductor first runs `workflow merge-check --fetch <PR> --json --charter <the tracking issue's body, saved under .workflow/>` (with `--check-logs DIR` for a waived check's log), right before it acts: the same command, and the same rules (flow §4), as a person's `merge-check`, so a run and a person never disagree on "ready". **`ready` is the only yes.** `not_yet` never merges: its reasons say what to do. `owner_review` (a change to a protected path) never merges unattended: it goes on the owner's list, with the files. The charter is read from the tracking issue's run state; its waivers count only as flow §4.1 says. A merge is pinned to the head the command checked, and auto-merge is disarmed before a branch update and armed again only on the new head's `ready`.
- **Merging when auto-merge can't be armed.** In `merge.mode: auto-merge`, GitHub refuses to enable auto-merge on a PR that is already mergeable (clean). Whoever tried (the ticket session, or the conductor) then runs `workflow merge-check` again at that moment, and on `ready` merges with a merge commit, pinned to the head it checked. The charter's `auto-merge` grant covers that merge. The conductor never merges a change to a protected path itself: `merge-check` answers `owner_review`, and that PR goes on the owner's list.
- **Kill switch.** The `workflow:stop` label on the tracking issue (or "stop the run" in the conductor's chat): from the next check-in the conductor interrupts the running sessions, waits until each branch stops moving (up to 3 check-ins) and archives them, records `stopped`, and writes the final report. **A stop releases nothing**, whatever `release.when` says: the report says the owner can release by hand.
- **The end time** is a hard stop, not "start nothing new": at `limits.ends_at` the conductor stops running sessions the same way, then releases if `release.when` is `end`.

## 5. The schema

```json
{
  "version": 1,
  "scope":   {"tickets": "all-ready", "exclude": [143], "follow_unblocked": true},
  "limits":  {"ends_at": "2026-10-13T03:30:00Z", "max_parallel": 2, "max_sessions": 40, "max_retries": 1, "check_in_minutes": 20},
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

`merge.mode`: `auto-merge` (GitHub merges once the ruleset's checks pass; no waivers), `session` (the ticket session, or the conductor, merges under the merge rule), `owner` (nothing merges unattended). `release.when`: `never`, `end`, `each-merge`. Validation (`workflow charter validate`) also requires:
- `ends_at` in the future and after the approval;
- `max_parallel` 1–16, `max_sessions` 1–500 and no fewer than `max_parallel`, `max_retries` 0–5, `check_in_minutes` 5–240;
- no keys it doesn't know;
- waived checks among the profile's required checks, and no `auto-merge` when the profile has no CI or no required checks, or in solo mode (`--unprotected`, or a `removed protection: ` gap, for removed protection);
- release steps among the profile's;
- `approved.by` and each amendment's `by` to be the profile's `project.owner`.
