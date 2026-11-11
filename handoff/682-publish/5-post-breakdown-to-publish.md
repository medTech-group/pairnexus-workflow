## Breakdown to publish

The breakdown as it will be published, after the breakdown check, its re-read and their rounds (answers 76–88). Blockers are named by title here and swapped for issue numbers as each is published. No owner tasks, no edits to existing issues, and no ticket held back: nothing is left open. There is no architecture pull request. After the reads, each ticket gained its `## Structural lines` (flow §2 item 2), which moves nothing between tickets.

### `workflow graph cites` for an issue, an ADR and a note: passages, open issues, counts and `--json`

Area: doctor

#### Parent

#682

#### What to build

The command `workflow graph cites <id>... [--json]` (spec #682, "The command's form", "Where it looks", "What it gives back"), in its own module `scripts/workflow/graph.py` (never the vendored copy, which the kit's update pull request adds), for the ids `#n`, `ADR:NNNN` and a note's path. It reads the base branch's tracked text files at `origin/<base>` after fetching it, and the bodies of open issues and open pull requests, and prints, counts first, each citing passage as `file:line` and its sentence grouped by file, and each open issue citing it with its sentence, `kind` and `claimed`. GitHub's inputs come from files (`--issues F --prs F`, `--comments F --permissions F`) or `--fetch`, read by page. No model tokens; it writes nothing but the git history it fetches, to `.git`. Answer ids, `built_by`, `--record` and `owner-tasks` are later tickets.

#### Acceptance criteria

- [ ] Each citation form of `#n`, ADRs ("ADR 0001", "ADR-0001", `adr/` paths) and research note paths is found; several ids in one run (seam 1)
- [ ] The citing sentence and where it ends, as the spec's "What it gives back" says: `."`, `.)`, `.**`, `!`, `?`, a blank line, a heading, a list item and a table row each end one; "e.g.", "i.e." and "ans." don't; a sentence over several lines is given at the citation's line (seam 1)
- [ ] Left out: the vendored kit (`lock.json`'s `files`, `orphaned` and the `<file>.new` its `conflicts` name), research notes' saved copies and fingerprint files, and a style file's `#` followed by 3, 6 or 8 hex digits (seam 1)
- [ ] An issue's citation inside its own `## Replaces` isn't listed, a citation elsewhere in that body is; `## Replaces` is read as the spec says (one id per list line, backticks allowed, ending at the next heading), never from a fenced block or a `>` quote (seam 1)
- [ ] Open issues and open pull requests citing it, each with `kind` (`pull_request`, `spec`, `decision`, `run`, `ticket`, `other`, in the spec's order; a run's tracking issue and the by-hand issue its state names as `run`) and `claimed` (`workflow:in-progress`; a decision ticket's assignee; an open issue an open pull request closes, never a `pull_request` entry by that clause) (seam 1)
- [ ] A run whose state can't be read: the command goes on and names that run in its output (seam 1)
- [ ] A sentence matching a `[sensitive].patterns` entry written "[left out: sensitive]", keeping its `file:line`, in every output (seam 1)
- [ ] Counts first (`passages`, `files`, `issues`); `counts.files` counts distinct passage files; `--json` gives the spec's list of objects for every id asked (seam 1)
- [ ] GitHub from files and from `--fetch` through `tests/fake_gh.py`, read by page (`page=N`) (seam 1)
- [ ] A changelog note under `## Unreleased`
- [ ] The full suite passes

#### Structural lines

`docs/architecture/scripts--workflow.md`, the small page for `scripts/workflow/` (the overview's "Code no page covers yet"): this ticket adds its `Covers: scripts/workflow/graph.py` line, with the module's structural lines.

#### By-hand checks

None

#### Blocked by

None

### Answer ids: tying a bare answer to its spec, round posts, joins, maps and `changed_by`

Area: doctor

#### Parent

#682

#### What to build

`workflow graph cites #n:answer:N` (spec #682, "Tying a bare answer to its spec", "For answer numbers and confirmed replacement lines", "Decision tickets", the map's id): the citation forms "answer N", "answers N…" (every number in a list or range) and "ans. N"; the tie of each bare answer (a named `#n` in the naming forms, an issue body's own spec for a sentence with no `#n`, else "spec unsure"); answer numbers and confirmed lines read from round posts; the "Planned as" and map-body joins; decision tickets; a map's id; and the confirmed lines that changed the answer in `changed_by`. `spec_unsure` marks and `counts.spec_unsure`.

#### Acceptance criteria

- [ ] "answer N", "answers 6, 14, 16 and 18", "answers 1–6" and "ans. N" read as every number they name (seam 1)
- [ ] A named `#n` in each naming form (a list after "on", "#n's answer N", "#n, answer N", the space-only forms "#n answer N", "#n ans. N", "spec #n ans. N"); a named ticket or other issue "spec unsure"; several named `#n` tied to each that holds the number or has no round posts read (seam 1)
- [ ] Which named `#n` ties: a spec, an item issue joined by "Planned as", an open, unjoined item issue (to itself) and a decision ticket; a named ticket or other issue never does (seam 1)
- [ ] In an issue's body, a "see #n" paragraph or list item, or a heading, above a sentence with a bare answer leaves that answer tied, being a sentence of its own (seam 1)
- [ ] In an issue's body: a sentence with no `#n` tied to the body's own spec (a spec's body; a ticket's parent spec; a decision ticket's or an open, unjoined item issue's own body to itself; a quick ticket with no parent spec, and any other body, "spec unsure"); a sentence with a named `#n` tied by it alone, even when it doesn't hold the number; a sentence with only unnamed `#n` "spec unsure"; a bare answer in a file with no named `#n` "spec unsure" (seam 1)
- [ ] Round posts: an answer line `**N. ` or a table row whose first cell is `**N.**`, from the post's own lines only (never a fenced block or `>` line), with write access and the agents' marker required, an unnumbered post ignored; on spec issues, item issues, decision tickets, and a map's comments naming a Destination item (seam 1)
- [ ] The numbers check: a tie to a spec, decision ticket or open, unjoined item issue whose round posts were read and hold no such number is "spec unsure"; kept when none were read (seam 1)
- [ ] The "Planned as" join (write access) and the map-body join for open and closed maps, with a `Blocked by:` on the item's line and "(spec #n)" linking it, and their skips (no item matched, two matched, no linked spec) (seam 1)
- [ ] A map's `#n` named without its item's spec, alone and beside another `#n` that ties, "spec unsure"; named with its item's spec, tied to it; another answer in the same sentence named by its own `#n` still tied (seam 1)
- [ ] `cites #<map>:answer:N` lists only the "spec unsure" citations, with no numbers check and nothing in `changed_by`, its output saying so and to ask by the Destination item's spec once the map links it (`--json` leaving that line out) (seam 1)
- [ ] A sentence holding several citations of the asked answer, one tied and one "spec unsure" (with or without a bracket after a bare answer), listed once, tied (seam 1)
- [ ] `#682:answer:44` in an open pull request's prose listed on a run for `#682`, not on one for `#682:answer:44` (seam 1)
- [ ] `changed_by`: the confirmed lines that replace, narrow or widen the asked answer, its "answer N on #M" form included, a decision ticket's own confirmed lines among them (seam 1)
- [ ] `spec_unsure` on passages and issues, and `counts.spec_unsure` (seam 1)
- [ ] A changelog note under `## Unreleased`
- [ ] The full suite passes

#### Structural lines

`docs/architecture/scripts--workflow.md`, the page that covers `scripts/workflow/graph.py` (its `Covers:` line comes with the first command ticket).

#### By-hand checks

None

#### Blocked by

- `workflow graph cites` for an issue, an ADR and a note: passages, open issues, counts and `--json`

### `built_by`: the pull requests that built on a decision, the ones that replace it, and their files

Area: doctor

#### Parent

#682

#### What to build

`built_by` (spec #682, "For the ticket built on a decision", "To tie a ticket to its pull request", "The building pull request's files", "The history fetch", `replaces`): closed tickets whose body cites the decision, or whose own `## Replaces` names the asked id, tied to their merged pull request by its closing keywords or `run.ticket_branch` in a merge commit, with the files of the pull request's merge or squash commit on the base branch, fetching the history from a shallow clone. The `replaces` and `spec_unsure` marks, as answers 70, 71 and 73 have them.

#### Acceptance criteria

- [ ] The ticket built on a decision: a merged pull request's closing keywords ("Fixed #n" among them) and `run.ticket_branch` in a merge commit; its pull request's files from its merge commit or squash commit (seam 1)
- [ ] A closed ticket whose only citation of `#682` is inside its own `## Replaces` line `#682:answer:44` not listed in `built_by` on a run for `#682`, nor marked `replaces` (the ids don't match whole) (seam 1)
- [ ] A closed owner task, decision ticket or item issue citing the decision not read for `built_by`; a closed ticket with no merged pull request found not listed (seam 1)
- [ ] A closed ticket whose citation is "spec unsure" listed with its pull request marked `spec_unsure` (seam 1)
- [ ] A merged ticket whose own `## Replaces` names the asked id listed marked `replaces`: found by its `## Replaces` alone, listed once when its body cites the id too, not `spec_unsure`; one naming another spec's answer of the same number unmarked; one naming the joined item issue's answer (`#679:answer:3`) marked on a run for the spec's id; `ADR:7` matching `ADR:0007`; a ticket for the rest closed as not planned not listed (seam 1)
- [ ] A merged ticket found by `## Replaces` `#<map>:answer:N` alone marked `replaces` and `spec_unsure` on a run for that map's id and for a spec a Destination item of that map links, not listed for a spec no item links; found on the same run also by a certain tie or a whole-id line, its one entry `replaces` and not `spec_unsure` (answer 73) (seam 1)
- [ ] "replaces it" beside that pull request in the text output (seam 1)
- [ ] `counts.built_by` counting every entry, marked ones included; `counts.spec_unsure` counting `built_by` entries marked `spec_unsure` (seam 1)
- [ ] The history fetch in a shallow clone (`git fetch --unshallow origin <base>`), and a failed fetch reported in the text output, and on stderr with `--json` (seam 1)
- [ ] A changelog note under `## Unreleased`
- [ ] The full suite passes

#### Structural lines

`docs/architecture/scripts--workflow.md`, the page that covers `scripts/workflow/graph.py` (its `Covers:` line comes with the first command ticket).

#### By-hand checks

None

#### Blocked by

- Answer ids: tying a bare answer to its spec, round posts, joins, maps and `changed_by`

### `--record` and `graph owner-tasks`: the marked record and the closed owner tasks still to run

Area: doctor

#### Parent

#682

#### What to build

`workflow graph cites <id>... --record [--on N] [--around F] [--counts-only]` and `workflow graph owner-tasks [--json]` (spec #682, "The record", "Closed owner tasks", `--record` in "The command's form"): the marked comment's body for each id's record issue, `<!-- workflow:graph ids=<the ids> -->` with the agents' marker; the round-post form with `--around F`; the switch to counts and files past the limit, and, still past it, the file list cut to fit with its "and N more" line (answer 74); and the closed owner tasks still to run, dated by the kit update that brought the command.

#### Acceptance criteria

- [ ] The record's body for each id's record issue (an answer's spec, a decision ticket's or an open, unjoined item issue's own issue, a map's issue for a map's answer id, a note's `Issue:` header), each headed by that issue's number; ids sharing a record issue share one body (seam 1)
- [ ] `--on N` for an ADR id and for a note with no `Issue:` header, and with several ids; `--record` refusing an ADR id, or such a note, without it (seam 1)
- [ ] `--around F`: `F`'s text with the list added (seam 1)
- [ ] Past the limit (counted as `review-record` counts it), `--record` and `--around` switch to counts and files themselves, keeping each `built_by` pull request with its files and its marks, "replaces it" and a failed fetch's line among them; `--counts-only` asks for that form (seam 1)
- [ ] Still past the limit as counts and files (the limit `review-record` uses), cut to fit: every id's counts, the fixed lines (a failed fetch, a map id's "ask by the spec", a run whose state can't be read) and every `built_by` pull request's number and marks kept; every id's passage files dropped (the later ids' first) before any pull request's files (the later ids' first) (answer 77); one line "and N more files and M more pull request files: run `workflow graph cites <ids>` for the full list"; the marker kept. `--around` refused with the size and the limit, and `--record` printing a marked body of every id's counts, the fixed lines and "too large to list: run `workflow graph cites <ids>`" (answer 84), only when the text plus everything the cut keeps (counts, fixed lines, `built_by` numbers and marks, open issues, `changed_by`, the "and N more" line, the marker and each record issue's heading) is still past it (answers 74, 76 and 84) (seam 1)
- [ ] A sentence matching a `[sensitive].patterns` entry written "[left out: sensitive]" in `--record`'s and `--around`'s bodies, so the guard doesn't refuse the record; `F`'s own text and file paths not filtered (answers 83 and 86) (seam 1)
- [ ] The record posted even with 0 passages; a map's id's record headed by the map's issue and saying so (seam 1)
- [ ] `graph owner-tasks`: `owner-task` issues closed after the first first-parent commit whose `lock.json` `files` lists `graph.py` (committer date in UTC, with a non-UTC offset and an owner task closed within that offset), with no record that counts: write access required, a record counting wherever it is posted (a round post on another issue among them); a plugin project, with no lock file, gets none; `--json` gives `[{"number", "title", "closed_at"}]` (seam 1)
- [ ] A changelog note under `## Unreleased`
- [ ] The full suite passes

#### Structural lines

`docs/architecture/scripts--workflow.md`, the page that covers `scripts/workflow/graph.py` (its `Covers:` line comes with the first command ticket).

#### By-hand checks

None

#### Blocked by

- `built_by`: the pull requests that built on a decision, the ones that replace it, and their files

### The planning session runs the graph: flow §1, §2, "Decision questions" and "Each round", and `start`

Area: start

#### Parent

#682

#### What to build

The planning session's rules (spec #682, "Who runs it and what they do", "Where the rules go"), in `docs/flow.md` and `skills/start`: a planning session runs `workflow graph cites` whenever an answer, ADR or note it makes reverses or narrows an earlier decision or a built reading, and at a confirmed replacement line or an ADR that changes another (only a note marked superseded is T6's, answers 79 and 85); posts the list in that round (its post being the record), except when `--around` is refused (answers 74 and 78); edits, notes and files a ticket for the rest as the spec says; `## Replaces` among a build ticket's parts; the breakdown check gets the list as notes; "Each round" gains the answer line's form, the map comment's form and the agents' marker.

#### Acceptance criteria

- [ ] Flow §1 (a map decision can reverse a decision), §2 (item 2's `## Replaces`, its ids in the command's own form, one per list line; the run when a round reverses a decision) and "Decision questions" (the replacement line runs it; the breakdown check gets the list, a listed passage no ticket covers a note in its post, never an **ask**) (seam 2)
- [ ] Advice only: nothing the list holds blocks a merge, a publish or a build (seam 2)
- [ ] The planning session's edits and notes: unclaimed tickets edited; claimed issues of any kind, open pull requests, claimed decision tickets, an open issue an open pull request closes, and a run's tracking and by-hand issues noted, never edited, each note naming the decision only and ending with the agents' marker; a spec's body changed as an edit after publishing unless claimed; other unclaimed non-ticket issues and unclaimed decision tickets edited directly, said in the round's post; a map's Destination line text kept (seam 2)
- [ ] The ticket for the rest: passages by `file:line` alone, never the sentence, always with `## Replaces` holding the ids in the command's own form, one per list line; inside a spec's breakdown one of its build tickets, everywhere else a quick ticket whose body names each answer with its spec; in a breakdown it names that way each answer of a spec other than its parent and any answer in a sentence holding a `#n`; `start`'s three "becomes a new ticket" places saying they don't apply to the list's notes (seam 2)
- [ ] `start`'s Quick ticket path: the item's issue of a ticket for the rest names the decision's ids, each answer as "#n's answer N", links the round post that reversed it (or the new note, the new ADR or the decision ticket's resolution comment), quotes nothing, every passage under `## Decided for you` as its `file:line` before **Publish it** (seam 2)
- [ ] Where a session posts a record: the round's post when a round carries the list, else `--record`'s body on the record issue, an ADR's included (a note's is T6's); when `--around` is refused, the round posted without the list and `--record`'s body as its own comment (answer 74) (seam 2)
- [ ] The ticket for the rest's `file:line` list (and a quick ticket's `## Decided for you`) cut by the session to `review-record`'s limit, dropping the last N passages in the command's `--json` order, with one line "and N more passages", its session getting the full list at claim (answers 75 and 87); the breakdown check given the list from the command's `--json`, never a record's body (answer 74) (seam 2)
- [ ] "Each round" in `start` and the flow: the answer line `**N. ` (or a table's first cell `**N.**`), a map comment's first heading holding the Destination item's title, and the agents' marker on every round's post (seam 2)
- [ ] A changelog note under `## Unreleased`
- [ ] The full suite passes

#### Structural lines

None: it changes skills, agents or docs, which aren't code (`guard.code_paths`).

#### By-hand checks

None

#### Blocked by

- `--record` and `graph owner-tasks`: the marked record and the closed owner tasks still to run

### Marking a research note superseded runs the graph: the flow's "Research" and `study`

Area: docs
Review: small

#### Parent

#682

#### What to build

The flow's "Research" section and the `study` skill (spec #682, "Where the rules go", "Research"): marking a note superseded runs `workflow graph cites` on the note's path, and its record goes on the issue the note's `Issue:` header names, or with none, with `--on N` on the issue where the session posts its rounds.

#### Acceptance criteria

- [ ] The flow's "Research" and `study` say that marking a note superseded runs the command on its path, and where its record goes: the issue its `Issue:` header names, or `--on N` for a note with none (answer 79: the superseded mark's rule is this ticket's alone; a new note that reverses a decision is T5's, answer 85) (seam 2)
- [ ] A changelog note under `## Unreleased`
- [ ] The full suite passes

#### Structural lines

None: it changes skills, agents or docs, which aren't code (`guard.code_paths`).

#### By-hand checks

None

#### Blocked by

- `--record` and `graph owner-tasks`: the marked record and the closed owner tasks still to run

### The breakdown check gets the list: `planning-checker`'s inputs and "How to report"

Area: review
Review: small

#### Parent

#682

#### What to build

The `planning-checker` agent (spec #682, "Where the rules go", "The `planning-checker` agent"): its breakdown-check inputs gain the list a reversing round carried, and its "How to report" gains the list's notes beside its four kinds of finding: a listed passage no ticket covers is a note, never an **ask**, so it holds no ticket back.

#### Acceptance criteria

- [ ] `agents/planning-checker.md`'s breakdown-check inputs include the list (the command's `--json`, never a record's body, answer 74), and "How to report" gives a listed passage no ticket covers as a note, never an **ask** (seam 2)
- [ ] A ticket for the rest's "and N more passages" line covers exactly the last N passages in the command's `--json` order, so those aren't noted as uncovered and any other unlisted passage is (answers 75 and 87) (seam 2)
- [ ] A changelog note under `## Unreleased`
- [ ] The full suite passes

#### Structural lines

None: it changes skills, agents or docs, which aren't code (`guard.code_paths`).

#### By-hand checks

None

#### Blocked by

- `built_by`: the pull requests that built on a decision, the ones that replace it, and their files

### `/next` runs the graph for closed owner tasks, and reads the passages before building

Area: start

#### Parent

#682

#### What to build

`skills/next` (spec #682, "The conductor's check-in and `/next`"): for each owner task `graph owner-tasks` lists, post the record (`--record`'s body on the owner task's issue); a ticket it starts whose body cites such a task reads its passages, from the command's `--json`, never the record's body (answer 74), before building. Only records from accounts with write access count; a plugin project gets no automatic run.

#### Acceptance criteria

- [ ] `next` runs `graph owner-tasks`, posts each record, and has a ticket whose body cites such a task read the passages before building (seam 2)
- [ ] `next` says a plugin project gets no automatic run (seam 2)
- [ ] A changelog note under `## Unreleased`
- [ ] The full suite passes

#### Structural lines

None: it changes skills, agents or docs, which aren't code (`guard.code_paths`).

#### By-hand checks

None

#### Blocked by

- `--record` and `graph owner-tasks`: the marked record and the closed owner tasks still to run

### `build-ticket` runs the graph at claim on `## Replaces`

Area: build
Review: small

#### Parent

#682

#### What to build

`skills/build-ticket` (spec #682, "`build-ticket`"): at claim, on the ids in its ticket's `## Replaces`, run `workflow graph cites` and read the passages and the building pull requests' files before building.

#### Acceptance criteria

- [ ] `build-ticket` at claim runs the command on its ticket's `## Replaces` ids and reads the passages and `built_by` files before building (seam 2)
- [ ] A changelog note under `## Unreleased`
- [ ] The full suite passes

#### Structural lines

None: it changes skills, agents or docs, which aren't code (`guard.code_paths`).

#### By-hand checks

None

#### Blocked by

- `built_by`: the pull requests that built on a decision, the ones that replace it, and their files

### The conductor's check-in runs the graph for closed owner tasks, and the briefing carries the passages

Area: conductor

#### Parent

#682

#### What to build

`skills/conductor` (spec #682, "The conductor's check-in and `/next`"): at each check-in, for each owner task `graph owner-tasks` lists, post the record on its issue; a ticket the conductor starts whose body cites such a task gets the passages in its briefing's read-first list. Only records from accounts with write access count.

#### Acceptance criteria

- [ ] The conductor's check-in runs `graph owner-tasks` and posts each record (seam 2)
- [ ] A ticket started whose body cites such a task gets the listed passages in its briefing's read-first list, taken from the command's `--json`, never the record's body (answer 74) (seam 2)
- [ ] A changelog note under `## Unreleased`
- [ ] The full suite passes

#### Structural lines

None: it changes skills, agents or docs, which aren't code (`guard.code_paths`).

#### By-hand checks

None

#### Blocked by

- `--record` and `graph owner-tasks`: the marked record and the closed owner tasks still to run
- #273 (it changes the run's briefing, where this adds the passages)

<!-- workflow:agent -->

---
_Generated by [Claude Code](https://claude.ai/code)_
