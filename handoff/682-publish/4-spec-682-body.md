Planned from #679 (answers 1–24 there), with answers 25–88 on this issue, which settle the open questions it was published with, each earlier re-read's after them, what the planning rounds on the edited body sent, what the checks before each edit round raised, and a rule the body held that no answer said (answer 40). Answers 64–66 split the ticket for the rest's lifecycle out to the follow-up item #714, leaving this slice the command, the record and who runs it, and moved the three questions then open, and answers 44–46, 49–51, 53–56, 58 and 60, to #714 as recommendations, not settled answers (answer 66); answers 67–69 settle the two the re-read after them left, so none of those is open; planning round 24 left one, which answer 70 settles, and answer 71 settles what planning round 25 sent; the re-reads after answers 70 and 71 left one each, and planning round 27 one, which answers 72–74 settle, with answer 75 settling what the check before that round raised; the re-read after answers 72–75 left three, which answers 76–78 settle in the breakdown check's round, with answers 79–83 settling where the breakdown puts what that check found, and answers 84–88 what its re-read found, so none is open. The second slice, the files parallel tickets will touch, is #680.

## Problem Statement

A project's decisions change after work has rested on them. An answer reverses an earlier one, an owner task closes with its result, an ADR changes another, or a research note is superseded. Today nothing finds what rests on the old decision:
- the passages in code, tests and docs that state or use it;
- the open tickets and specs that cite it;
- the files the ticket built on it changed.

A session either lists them by hand, or misses them, and the stale text is found later, one review at a time. In a project using the kit:
- an answer reversed a reading a ticket had just built, and the replacing ticket's author listed about a dozen places by hand, missing one test file the build then had to change;
- prose citing a closed owner task kept saying "until it checks";
- the spec's body lagged its own answers.

In the kit itself, #80 built a merge rule that contradicted flow §4, and run 174 set a ticket aside because of it.

The links are already in the text. Across the kit and two projects, about 1,100 files cite issues by number. Spec answers, ADRs and research notes are cited by id too: one project cites its ADRs about 500 times, and the kit cites its research notes by path. Nothing reads them as links.

## Solution

A command, `workflow graph`, answers "what rests on this decision?" It is built fresh each time from git, the issues and the text, with no model and no stored graph, and it lists:
- every passage citing the decision, as its sentence;
- the open issues citing it;
- the pull requests that built on it, with their files.

It is advice: the session decides what to change, and nothing blocks (answer 5). The flow has it run:
- by a planning session that reverses or narrows a decision;
- at the recorded signals;
- by the conductor and `/next` for owner tasks closed since the kit update that brought it;
- by a ticket session whose ticket replaces a reading.

The list is kept as one marked comment, as the kit keeps its other records.

A backtest replayed it on a project's reversed answer:
- citations of the old decision and of the ticket built on it found 5 of the 7 places on the hand-made list;
- with that ticket's pull request's files, it found all 7, and all 8 files the replacing build changed, with 3 extra.

For a closed owner task, 13 files and 144 lines cited it, the 3 stale passages among them, so it lists sentences, not whole files (answer 7). The prototype is a throwaway branch, `claude/prototype-project-graph-backtest`, in the private sandbox repository.

## User Stories

1. As a planning session that reverses an earlier answer, I want every passage that cites the old answer listed, so that I can change them in the same plan instead of leaving stale text.
2. As a planning session, I want the open tickets whose bodies cite the old answer listed, so that I can edit the unclaimed ones before they are built on the old reading (answer 9).
3. As a planning session, I want a claimed ticket that cites the old answer named, so that I note it on that ticket rather than edit a ticket someone is building (answer 9).
4. As a planning session, I want the files changed by the pull request of a ticket built on the old reading, so that I find the places that use the decision without citing it (answer 6).
5. As a planning session, I want each passage as its citing sentence with `file:line`, grouped by file, so that I read sentences, not whole files or 4,000-character lines (answer 7).
6. As a planning session, I want the counts first, so that I see the size of the change before reading it (answer 7).
7. As a planning session, I want the list in `--json` too, so that I can work through it in steps (answer 7).
8. As a planning session, I want a bare "answer 7" tied to its spec by the `#n` its sentence names, so that a citation of another spec's answer 7 isn't listed as this one's (answers 21, 28 and 32–35).
9. As a planning session, I want a bare answer whose spec it can't tell listed once as "spec unsure", so that nothing is silently left out (answers 12 and 21).
10. As a planning session, I want a bare answer in an issue's body, in a sentence with no `#n`, tied to that body's own spec, so that a ticket's or spec's own citations resolve without guessing (answer 31).
11. As a planning session in a cloud session, I want the command to fetch the history it needs from a shallow clone, so that the building pull request's files and the kit update's date are found there (answers 15, 16 and 31).
12. As a planning session, I want answer numbers and confirmed replacement lines read from round posts on spec issues, item issues and decision tickets, and on a map's issue where they name a Destination item, so that the command knows which specs have an answer 7 and which answers were replaced (answers 12, 18 and 38).
13. As a planning session, I want "answers 6, 14, 16 and 18" and "answers 1–6" read as every number they name, so that a list or range isn't read as its first number only (the end check's fix to answer 11).
14. As a planning session, I want ADRs cited as "ADR 0001", "ADR-0001" or by their `adr/` path all found, so that each project's form counts (answers 2 and 11).
15. As a planning session, I want research notes found by their path, so that a superseded note's dependents are listed (answer 2).
16. As a planning session, I want the vendored kit's files left out, so that the kit's own `#n` and example answers aren't listed as my project's passages (answer 13 and the end check's fix).
17. As a planning session, I want the round's post that carries the list to be its marked record, wherever the round is posted, so that one post does both, even before the spec exists (answers 8, 9 and 19).
18. As a planning session, I want a spec's own body, when it cites the old answer, changed by me as an edit after publishing, unless it is claimed, with its planning round and spec record, so that a ticket never edits a published spec (answer 23, as narrowed by answers 40 and 42).
19. As a planning session, I want one ticket filed for the rest, listing each passage in files by its `file:line` (cut to fit an issue body with an "and N more passages" line, answer 75) and carrying `## Replaces`, so that the stale passages are fixed, its session reading their sentences at claim (answers 9, 23, 64 and 75).
20. As a planning session writing a ticket that replaces a reading, I want to name the ids it replaces in a `## Replaces` section, so that its ticket session can find what rests on them (answer 9).
21. As a planning session, I want the breakdown check to get the list, so that it can see which listed passages the breakdown covers (answer 9).
22. As a planning session, I want the command run when I write a confirmed replacement line, mark a note superseded, or write an ADR that changes another, so that the recorded signals aren't missed (answer 4).
23. As the conductor, I want the owner tasks closed since the kit update that brought the command, with no record yet that counts, listed for me, so that I run it once for each and never backfill old ones (answers 4, 8 and 16).
24. As the conductor, I want to post each such list as a marked comment on the owner task's issue, so that a later check-in knows it has been run (answer 8).
25. As the conductor, I want a ticket I start whose body cites such a decision to get the listed passages in its briefing, so that its session builds on the current reading (answer 9).
26. As `/next`, I want to do the same as the conductor for owner tasks closed since, so that attended work catches them too (answers 4 and 9).
27. As the conductor or `/next`, I want only marked comments from accounts with write access to count as "already run", so that anyone else's comment can't hide a closed owner task (answer 24).
28. As a ticket session whose ticket has a `## Replaces` section, I want `build-ticket` to run the command on those ids at claim, so that I read what rests on the reading I replace before building (answer 9).
29. As a session recording a list for a note or an ADR, I want it posted on the issue the note's `Issue:` header names, or for an ADR on the issue where the session that changed it posts its rounds, so that a decision with no issue of its own still gets a record (answer 17).
30. As a session, I want a post that would pass GitHub's 65,536-character limit to carry the list as counts and files only, and, still past it, those lists cut to fit with an "and N more" line, so that the record still posts, and past even what the cut keeps, a body of counts and fixed lines saying the list is too large to list (answer 8, #679's re-read's fix 1, and answers 74, 76 and 84).
31. As the owner of a project that uses the kit as a plugin, I want no automatic run for closed owner tasks there, since it has no `lock.json` to date the update, while the command and planning sessions still run on demand (answer 22).
32. As a project owner, I want the command never to block a merge, a publish or a build, so that a long list of still-correct citations can't stop work (answer 5).
33. As a project owner, I want the command to spend no model tokens and change nothing but the git history it fetches, so that running it is always safe and cheap (#679).
34. As a session in any project, I want the command's GitHub inputs taken from files or with `--fetch`, as the kit's other commands take them, so that it runs where `gh api` can't (answer 14).

## Implementation Decisions

- **The name.** The project graph. The glossary's **Map** stays the wayfinder map, and the project graph gets no glossary entry in this slice (answers 1 and 10).
- **The decisions it reads** (answer 2):
  - issues (`#n`: owner tasks, specs, tickets);
  - a spec's numbered answers;
  - ADRs;
  - research notes.

  Glossary terms are not read in this slice.
- **The citation forms** (answer 11 and the end check's fix), built in only, with no profile setting:
  - `#n`;
  - "answer N", "answers N…" (every number in a list or range), "ans. N";
  - "ADR 0001", "ADR-0001", and paths under `adr/`;
  - research note paths.
- **The vendored kit is left out** (answer 13 and the end check's fix): the paths in `.claude/workflow/lock.json`'s `files` and `orphaned`, and the `<file>.new` its `conflicts` name, in the kit as in any project.
- **Where it looks** (answer 3, as widened by answers 12, 16, 18, 20, 38, 41 and 70 and narrowed by answer 13):
  - **For passages:**
    - the base branch's tracked text files, read at `origin/<base>` after fetching it, as `review-record --base` does;
    - the bodies of open issues, open pull requests among them (read from `--prs`, as `status` takes them; answer 41).

    It leaves out the vendored kit, research notes' saved copies and fingerprint files (third-party text), and in style files (`.css`, `.scss`) a `#` followed by 3, 6 or 8 hex digits (a colour, not an issue). An issue's citation inside its own `## Replaces` section isn't listed, so its `## Replaces` alone doesn't list it; a citation elsewhere in its body, such as the ticket for the rest's own prose naming an answer (answer 68), is listed like any other.
  - **For the ticket built on a decision:** the bodies of closed tickets (closed issues the list would give `kind: ticket`), only to find those whose body cites the decision (answer 3), a citation inside the closed ticket's own `## Replaces` left out here too, and those whose own `## Replaces` names the asked id and whose merged pull request is found (below), which are listed as replacing it (answer 70, widening answer 3). For an owner task, these are the closed tickets whose body cites it, and those whose own `## Replaces` names it and whose merged pull request is found, marked `replaces`.
  - **To tie a ticket to its pull request:**
    - a merged pull request whose body closes #n, by GitHub's closing keywords ("Closes", "Fixes", "Resolves" and their other forms), read as `issues.closed_by_open_prs` reads an open one's;
    - the profile's `run.ticket_branch` (`*` as the ticket's number, default `claude/build-*`) named in a merge commit (answer 20 and #679's re-read's fix 3).
  - **For answer numbers and confirmed replacement lines** (answers 12, 18 and 38):
    - **Which posts:** round posts on spec issues, item issues and decision tickets (answer 38), and on a map's issue, open or closed, where they name a Destination item (answer 18).
      - **An item's issue and its spec** are joined by the item's closing "Planned as #<spec>" comment (answer 41), counted only from an account with write access.
      - **A Destination item and its spec** are joined by the map's body. An item is a list line in the body's Destination section that links `#<spec>` (its link to an issue of kind `spec`; a `Blocked by: #<n>` on the same line isn't it), and its title is that line's text before its first `#n` and before any `Blocked by:`, with the list marker, surrounding whitespace, and trailing punctuation, brackets and the word "spec" dropped ("- Booking ahead (spec #700)" has the title "Booking ahead"). A comment names an item when its first heading holds the title word for word.
      - **Skipped:** a comment matching no item, or two, and an item with no linked spec.
      - **The form is new:** `start`'s and the flow's "Each round" gain it (below).
    - **What counts as a round post:** a comment from an account with write access, carrying the agents' marker and numbered answers. An answer is a line starting `**N. ` (bold, number, full stop), or a table row whose first cell is `**N.**`. `start`'s and the flow's "Each round" gain this form, and that a round's post carries the agents' marker, which an attended session's posts needn't otherwise carry (below). A post with no such line isn't read. Unlike `start`'s numbering, older posts unnumbered or without the agents' marker aren't counted, so citations of them come out "spec unsure".
    - **How they are read:** only from the post's own lines, never from a quoted list (a fenced block or a `>` line), so a quoted example isn't read as a real one (#679's re-read's fix 2).
    - **What the numbers are for:**
      - to map a named item issue to its spec;
      - to check a tie: a citation tied to a spec whose round posts were read and hold no answer with that number is "spec unsure". A spec with no round posts read keeps the tie. A tie to a decision ticket is checked the same way, against that ticket's own round posts, and kept when none were read (answer 38). A tie to an open, unjoined item issue is checked the same way, against its own round posts. A map's `#n` never ties by itself: a citation naming it (the map's `#n` next to that answer, in a naming form) is "spec unsure" whatever other `#n` that citation names, unless it also names that map's Destination item's spec. When it does, the several-`#n` rule applies to the `#n` it names other than the map (answers 26, 35 and 43). This goes by citation, not by sentence: another answer in the same sentence, named by its own `#n`, still ties.
    - **Decision tickets:** a decision ticket is an issue carrying a `wayfinder:<type>` label other than `wayfinder:map` (the `wayfinder` skill), never a ticket under answer 9. A citation of a decision ticket's answer is found only when its sentence names that ticket's `#n`, or, in a sentence with no `#n`, in that ticket's own body (answers 31 and 37). Its own round posts, on its own issue, are read as a spec's are, for its answer numbers and its confirmed lines, which show in `changed_by` (answer 38).
  - **For which owner tasks still need a run:** closed `owner-task` issues and their marked comments (answer 16), and the marked records whose ids name them on any other issue whose comments it reads (a round post carrying the list, answer 19), since a record counts wherever it is posted.
  - **To tell a run's by-hand issue:** the bodies of `workflow:run` tracking issues, open and closed, for their state's `by_hand_issue` (answer 41).

  No other comments are read: only round posts, "Planned as" comments and marked records.
- **Tying a bare answer to its spec** (answers 21, 28, 31–37 and 43). There is no history tie: answer 31 replaces answer 29 and narrows answers 2, 12, 25 and 28.
  1. **A named `#n`** (answers 28, 32 and 33). A `#n` names an answer only in these forms, with the answer next to the `#n`:
     - "answer N on #n", where each `#n` of a list after "on" is named ("answers 17 and 23 on #603 and #611");
     - "#n's answer N";
     - "#n, answer N";
     - "#n answer N", "#n ans. N" and "spec #n ans. N", with a space only;
     - their plural and "ans." variants.

     It ties only when `#n` is a spec, an item issue joined by "Planned as", an open issue carrying the `workflow:item` marker not yet joined by "Planned as" (it ties to itself, answer 36), or a decision ticket. A map's `#n` never ties by itself (answer 35). With several named `#n`, it is tied to each named one that holds that number or has no round posts read, and with none of them, it is "spec unsure". A citation that also names a map is the exception: it is "spec unsure" unless it names that map's Destination item's spec (answer 43). A `#n` in any other form, or a named ticket or other issue, is unnamed and never ties (answers 25 and 34).
  2. **In an issue's body, for a sentence with no `#n` at all,** the body's own spec (answer 31):
     - a spec's body ties it to that spec;
     - a ticket's body ties it to its parent (`issues.parent_of`) when that parent's `kind` is `spec`; a ticket with no such parent (a quick ticket) makes it "spec unsure";
     - a decision ticket's body, or an open, unjoined item issue's, ties it to that issue (answers 36 and 37);
     - any other body makes it "spec unsure".
  3. **Everything else** is listed once as "spec unsure": a bare answer in a file with no named `#n`, and a body sentence whose `#n` are all unnamed (answer 31). It is still listed for a run on that answer, only marked unsure.

  **Several citations of the asked answer in one sentence** (answer 65, replacing answer 61). A sentence holding more than one citation of the asked answer, one tied and one "spec unsure" among them ("Answer 44 settled it, as #682's answer 44 says", or a bare answer followed by a bracket naming it), is one passage, listed once, tied if any of them ties.

- **The building pull request's files** (answers 6 and 15, as widened by answer 70) come from git: the pull request's merge commit ("Merge pull request #N") or squash commit ("(#N)") on the base branch. Code-symbol links are not followed. A closed ticket whose citation is "spec unsure" doesn't count as built on the decision, but its pull request is still listed in `built_by`, marked `spec_unsure`, so nothing is silently left out (as answers 12 and 31 list unsure citations). A closed ticket whose own `## Replaces` names the asked id, and whose merged pull request is found as above (by its closing keywords or `run.ticket_branch`), is listed in `built_by` once, marked `replaces`, whether or not its body cites the id elsewhere, and not `spec_unsure`, since its `## Replaces` names the whole id; so a later run on a replaced id shows which files already carry the new reading (answer 70). A ticket for the rest closed with no merged pull request found (closed as not planned, say) isn't listed, since nothing of it landed, and neither is any other closed ticket citing the decision with no merged pull request found: a `built_by` entry needs its pull request. A `## Replaces` naming a map's answer id (`#<map>:answer:N`) marks its ticket both `replaces` and `spec_unsure`, on a run for that map's id and on a run for `#<spec>:answer:N` where a Destination item of that map links `<spec>` in the map's body (answer 18's join), since a map's id doesn't say which item's answer N it is (answers 26, 35 and 71). Where, on a run for `#<spec>:answer:N`, the same ticket is also found by a certain tie (a tied body citation) or a `## Replaces` line naming `#<spec>:answer:N` whole, a certain tie wins: its one entry keeps `replaces` and isn't `spec_unsure` (answer 73, narrowing answer 71).
- **The history fetch:** the command fetches the base branch's history when the clone is shallow (`git fetch --unshallow origin <base>`), for the building pull request's files (answer 15) and the kit update's date (answer 16). This is the one thing it writes, to `.git` only. If the fetch fails, the run says so in its output: in the text output and in `--record`'s bodies, their counts-and-files form included, so a record posted after a failed fetch says why a building pull request, or its files, may be missing. With `--json`, the line goes to stderr, and the list keeps its form.
- **What it gives back** (answer 7, as widened by answer 70):
  - counts first;
  - each citing passage as `file:line` and its sentence, grouped by file. A sentence ends at `.`, `!` or `?`, with any closing quote, bracket, emphasis marker (`**`, `_`) or backtick after it, followed by a space or a line end, except the full stop of "ans.", "e.g." and "i.e."; and at the end of a heading, a list item or a table row, and at a blank line. So hard-wrapped prose stays one sentence, "spec #n ans. N" stays in one, and a heading, or a line set apart as its own paragraph or list item (a "see #n" line), is a sentence of its own. A sentence that runs over several lines is given at the citation's line. A sentence matching one of the profile's `[sensitive].patterns` is written "[left out: sensitive]", keeping its `file:line`, in every output, as `research fingerprint --saved` leaves out matches, here by whole sentence, so the guard doesn't refuse the record for a sentence; file paths and `--around`'s own text aren't filtered;
  - each open issue citing it, with the sentence;
  - each pull request that built on it, with its files, and the pull request of each closed ticket whose own `## Replaces` names it, with its files, marked "replaces it" (answer 70);
  - the confirmed lines that replace, narrow or widen the asked answer, its "answer N on #M" form included.

  There is no cap. `--json` gives the same for every id asked, as a list of objects: `[{"decision", "counts": {"passages", "files", "issues", "built_by", "spec_unsure"}, "passages": [{"file", "line", "sentence", "spec_unsure"}], "issues": [{"number", "kind", "claimed", "sentence", "spec_unsure"}], "built_by": [{"pr", "ticket", "files", "spec_unsure", "replaces"}], "changed_by": [{"answer", "verb", "issue"}]}]`.
  - `kind` is one of `ticket`, `spec`, `decision`, `pull_request`, `run`, `other` (answers 37 and 40), decided in this order:
    1. a pull request is `pull_request`;
    2. the `spec` label, or a "Spec:" title, is `spec`;
    3. a `wayfinder:<type>` label other than `wayfinder:map` is `decision`;
    4. a run's tracking issue (the `workflow:run` label), or the by-hand issue a `workflow:run` issue's state names (`by_hand_issue`, read as `workflow state get --body` reads it, from open and closed runs), is `run` (answer 40);
    5. `ticket` is an issue `issues.is_build_ticket` counts that has no `owner-task`, `ready-for-human` or `research` label and no `workflow:item` marker;
    6. anything else (an owner task, a map, a research issue, an item issue) is `other`.

    A run whose state can't be read, or isn't written yet, doesn't stop the command: it goes on, names that run in its output, where a failed history fetch's line shows, and says that run's by-hand issue isn't told apart.
  - `claimed` is true when the issue carries `workflow:in-progress`, or, for a decision ticket, has an assignee (the `wayfinder` skill's claim), or when it is an open issue of any kind that an open pull request closes, as `issues.closed_by_open_prs` reads it from `--prs` (GitHub's closing keywords in the pull request's body, drafts included; answer 42 and its re-read's fix 1). A `pull_request` entry is never claimed by this last clause.
  - `verb` is one of `replaces`, `narrows`, `widens`.
  - `replaces` is true on a `built_by` entry whose ticket's own `## Replaces` names the asked id, compared as the whole id, and false on every other (answer 70). Before the comparison, in a `#n:answer:N` id a joined item issue's `#n` is read as its spec's, in the asked id and in `## Replaces` alike, as rule 1 of the tie reads it, so `#679:answer:3` and `#682:answer:3` match (a bare `#679` stays `#679`); a map's `#<map>:answer:N` in `## Replaces` also matches `#<spec>:answer:N` for a spec a Destination item of that map links, marked `spec_unsure` too (answer 71), unless, on a run for `#<spec>:answer:N`, the same ticket is also found by a certain tie or a `## Replaces` line naming `#<spec>:answer:N` whole, when it isn't `spec_unsure` (answer 73); backticks and a leading `./` are dropped, and an `ADR:` id is compared by its number, so `ADR:7` matches `ADR:0007`. The text output and `--record`'s bodies, their counts-and-files form included, say "replaces it" beside that pull request.
  - `counts.built_by` counts every `built_by` entry, those marked `replaces` or `spec_unsure` included, and `counts.spec_unsure` counts every passage, issue and `built_by` entry marked `spec_unsure`, a map's `replaces` entry marked `spec_unsure` among them. `counts.files` counts the distinct files holding a listed passage; a `built_by` pull request's files aren't counted there.

  `graph owner-tasks --json` gives `[{"number", "title", "closed_at"}]`.
- **The command's form:**
  - `workflow graph cites <id>... [--json] [--record] [--counts-only]` takes one or more ids:
    - `#n`;
    - `#n:answer:N`;
    - `ADR:NNNN`;
    - a note's path.

    A map's id can't be tied (answer 39): `cites #<map>:answer:N` lists only the "spec unsure" citations of that number (a closed ticket's among them, its pull request in `built_by` marked `spec_unsure`), and the `built_by` entries a `## Replaces` naming that map's id marks `replaces` and `spec_unsure` (answer 71), with no numbers check and nothing in `changed_by`. Its output says so, and says to ask by the Destination item's spec once the map links it: in the text output and in `--record`'s bodies, their counts-and-files form included. `--json` leaves that line out.

    `--record` prints a marked comment's body for each id's record issue, one after another, each headed by that issue's number. An `ADR:NNNN` id's record issue is given with `--on N`, and `--record` refuses an ADR id without it, and a note's path whose note has no `Issue:` header (an old note, flow "Research") unless `--on N` is given. `--on N` gives the record issue of every id with none of its own (an ADR, a note with no `Issue:` header), other ids keeping theirs, and ids sharing a record issue share one body. `--record --around F` prints a round post instead: `F`'s text with the list added. Either switches to counts and files only by itself past the comment limit (the counts-and-files form drops the sentences, and keeps each `built_by` pull request with its files and its marks), counted as `review-record` counts it (UTF-16 units, room kept for a cloud session's footer). `--counts-only` asks for counts and files only. Still past the limit as counts and files, the lists are cut to fit (answer 74, under "The record"); past even what the cut keeps, `--record` prints counts and fixed lines only and `--around` is refused (answers 76 and 84).
  - `workflow graph owner-tasks [--json]` lists the closed owner tasks still to run, from the same inputs.
  - GitHub's inputs come from files (`--issues F --prs F` as `status` takes them, `--comments F --permissions F` as `research stakes` takes them) or with `--fetch`, read by page (`page=N` on `repos/<owner>/<repo>/` paths, #568). It spends no model tokens.
  - The command's code is its own module, `scripts/workflow/graph.py`, vendored as `.claude/workflow/bin/workflow/graph.py`, so the lock records when a project got it.
- **The record** (answers 8, 17, 19 and 24, as narrowed by answer 74). The record is a marked comment: `<!-- workflow:graph ids=<the ids> -->` with `<!-- workflow:agent -->`. It counts for its ids wherever it is posted, so a planning round that carries an owner task's list (answer 19) counts for that task. It is posted even when nothing cites the decision (0 passages), so the task isn't listed again. A duplicate from the conductor and `/next` running at once is harmless. Where it goes:
  - **When a planning round carries the list,** that round's post is the record, wherever the round is posted (answer 19).
  - **Otherwise,** the session posts `--record`'s body:
    - on the decision's issue (for an answer, its spec's issue; for a decision ticket's or an open, unjoined item issue's answer, that issue; for a map's answer id, the map's issue);
    - for a note, on the issue its `Issue:` header names, or with none, the issue given with `--on N`: the issue where the session that marked it superseded posts its rounds, as for an ADR;
    - for an ADR, on the issue where the session that changed it posts its rounds.

  The whole post's length is what counts: the command's `--record` and `--record --around F` switch to counts and files only themselves past GitHub's 65,536 characters (answer 8 and #679's re-read's fix 1). If the counts-and-files form is still past the limit (the one `review-record` uses: GitHub's 65,536, less a cloud session's footer), its lists are cut to fit (answer 74, narrowing answers 8 and 19). The cut keeps every id's counts, the fixed lines (a failed history fetch, a map id's "ask by the spec", a run whose state can't be read), every `built_by` pull request's number and marks ("replaces it" among them), the open issues' entries and `changed_by`; it drops every id's passage files (the later ids' first) before any `built_by` pull request's files (the later ids' first) (answer 77, narrowing answer 74), and ends with one line "and N more files and M more pull request files: run `workflow graph cites <ids>` for the full list", N counting passage files and M the pull requests' files. The cut body keeps its marker and counts as the record. When the text plus everything the cut keeps (every id's counts, the fixed lines, every `built_by` pull request's number and marks, the open issues' entries and `changed_by`, the "and N more" line, the marker and each record issue's heading) is still past the limit, `--record` prints a marked body holding every id's counts, the fixed lines and one line "too large to list: run `workflow graph cites <ids>`", so a record still counts (answer 84, narrowing answer 76); `--around` is refused with the size and the limit (answer 76, narrowing answer 74), as `workflow handoff` does past its record limit, and prints no body, and the session then posts its round without the list and `--record`'s body as its own comment on the record issue (answer 74). No one reads a record's list back: the briefing's passages and the breakdown check's list come from the command's own output (`--json`), never from a record's body (answer 74). A record counts only from an account with write access (answer 24).
- **Closed owner tasks** (answers 4, 8, 16 and 22): `graph owner-tasks` lists `owner-task` issues closed after the kit update that brought the command, with no record that counts.
  - **The kit update:** the first first-parent commit on the base branch whose `.claude/workflow/lock.json` `files` lists `.claude/workflow/bin/workflow/graph.py`, fetched if the clone is shallow.
  - **The comparison:** that commit's committer date against the issue's `closed_at`, both in UTC.
  - **A plugin project,** which has no lock file, gets none: on demand only.
- **Who runs it and what they do** (answers 4, 9 and 23):
  - **A planning session runs it** whenever an answer, ADR or note it makes reverses or narrows an earlier decision or a built reading, and at a confirmed replacement line, a note marked superseded or an ADR that changes another. It:
    - posts the list in that round, except when `--around` is refused: then the round goes without it and `--record`'s body as its own comment (answer 74, narrowing answer 9, answer 78);
    - edits open, unclaimed tickets whose body cites the decision;
    - notes claimed ones, as a comment on each claimed ticket naming the decision, also listed in the record;
    - notes an open pull request, or a claimed decision ticket, whose body cites it, the same way, never editing its body: its own session decides (answer 30);
    - changes a spec's body, unless the spec is claimed, as an edit after publishing, with its planning round and spec record (answer 23, as narrowed by answers 27, 30, 40 and 42);
    - edits unclaimed owner tasks, maps, research issues and item issues, and open, unclaimed decision tickets, directly, saying in the round's post what it changed (answer 27, as widened by answer 37 and narrowed by answers 40 and 42; answer 37 as widened by answer 40 and narrowed by answer 42);
    - notes, never edits, any claimed issue of any kind, an open issue that an open pull request closes among them (answer 42), and a run's tracking issue and its by-hand issue (`kind: run`), as answer 30 does for a pull request (answer 40). The conductor is the tracking issue's only writer, and ticket sessions add their checkboxes to the by-hand issue. A map's body keeps each Destination line's text before its link unchanged, so the item's earlier rounds still name it (answer 18's join);
    - ends every note (the comment naming the decision, on a claimed issue, a pull request or a run's two issues) with `<!-- workflow:agent -->`, so a conductor's check-in never reads a note on its tracking issue as the owner's words;
    - files a ticket for the rest: the passages in files, each listed as its `file:line` alone, never its sentence, so no bare answer is copied into a ticket's body where it would tie to the wrong spec (answer 31's rule 2); its session reads the sentences when `build-ticket` runs the command at claim on its `## Replaces` (answer 9). That ticket always carries `## Replaces` with the decision's ids. Past an issue body's limit (the one `review-record` uses: 65,536, less a cloud session's footer, counted in UTF-16 units), the session cuts its `file:line` list (and a quick ticket's `## Decided for you`) to fit, dropping the last N passages in the command's `--json` order and ending with one line "and N more passages" (answer 87), its session getting the full list when `build-ticket` runs the command at claim (answer 75, narrowing answer 64). Every noted issue, a claimed build ticket and one an open pull request closes included, gets the note only, and the note names the decision only, never the ticket for the rest (answers 30, 40, 42, 64 and 69). Inside a spec's breakdown, the ticket for the rest is one of that breakdown's build tickets: drafted with the others, read by the breakdown check and published with them. Everywhere else it is a quick ticket, written and published by `start`'s Quick ticket path (its item's issue first, the end check, `## Decided for you`), with no parent spec, so its body names each answer with its spec ("#n's answer N"). Inside a breakdown, it names that way each answer of a spec other than its parent, and any answer in a sentence that holds a `#n`, since a bare answer in a ticket's body ties to its parent spec only in a sentence with no `#n` (answer 47, as narrowed by answer 64 and widened by answer 68). That item's issue names the decision's ids, each answer as "#n's answer N" (or the note's path, or `ADR:NNNN`), and links the round post that reversed it, or with none (a note marked superseded, or an ADR from a map decision with no rounds), the new note, the new ADR or the decision ticket's resolution comment; it quotes nothing, so every passage shows under `## Decided for you` as its `file:line`, before **Publish it** (answer 64). Whether the ticket for the rest also carries a noted build ticket's change and waits on it, and what happens when that ticket closes, is the follow-up item #714 (answer 66). This bullet rests on answers 9 and 23, as narrowed by answers 47 and 64, and on answer 64 as narrowed by answers 68, 69 and 75;
    - writes `## Replaces` on a ticket that replaces a reading: the ids it replaces, in the command's own form (`#n`, `#n:answer:N`, `ADR:NNNN`, a note's path), one id per list line, backticks allowed, the section ending at the next heading, read only from the body's own lines, never from a fenced block or a `>` quote (as round posts are read), as `build-ticket` runs the command on them, so a run compares each with the asked id whole and a bare answer of another spec never matches (answer 70's check).

    The breakdown check gets the list, from the command's own output (`--json`), never from a record's body (answer 74). A ticket for the rest's "and N more passages" line covers exactly the last N passages in the command's `--json` order (answers 75 and 87), so any other passage it doesn't list is named. A listed passage no ticket covers is a note in its post, never an **ask**, so it never holds a ticket back (answer 5).
  - **The conductor's check-in and `/next`:** for each owner task `graph owner-tasks` lists, they post the record. A ticket they start whose body cites it gets the passages, from the command's own output (`--json`), never from the record's body (answer 74):
    - the conductor in the briefing's read-first list;
    - `/next` by reading them before building.
  - **`build-ticket`:** at claim, on the ids in its ticket's `## Replaces`, reading the passages and the building pull requests' files before building.
- **Where the rules go:**
  - **`docs/flow.md`:**
    - §1 (a map decision can reverse a decision);
    - §2 (item 2's list of a build ticket's parts gains `## Replaces`, its ids in the command's own form (`#n`, `#n:answer:N`, `ADR:NNNN`, a note's path), one per list line, and the run when a round reverses a decision);
    - "Decision questions" (the replacement line runs it, and the breakdown check gets the list as notes).
  - **Research:** the flow's "Research" section and the `study` skill (marking a note superseded runs the command).
  - **"Each round":** `start`'s and the flow's gain the answer line's form (`**N. `, or a table's first cell `**N.**`), a map comment's form (its first heading holds the Destination item's title), and that every round's post carries the agents' marker.
  - **The source skills** `start`, `next`, `conductor` and `build-ticket`. In `start`, the three places that say a change to a claimed or built issue (in **Add to an existing issue**, a built one) becomes a new ticket (Spec step 3's breakdown paragraph, its edit rule; **Settling a held-back ticket**, a bullet inside the same step; and **Add to an existing issue** step 4) say that this doesn't apply to the list's notes, where the note is all, and which kind of ticket the ticket for the rest is, as answer 47 has it (inside a spec's breakdown, one of its build tickets; everywhere else, a quick ticket whose body names each answer with its spec): today Spec step 3's breakdown paragraph is the first, the other two the second. Where the ticket for the rest is filed, `start` says its passages are listed by `file:line` alone, with `## Replaces` holding the ids in the command's own form (`#n`, `#n:answer:N`, `ADR:NNNN`, a note's path), one per list line, and that in a breakdown it names as "#n's answer N" each answer of a spec other than its parent, and any answer in a sentence that holds a `#n` (answer 68). `start`'s Quick ticket path says what the item's issue of a ticket for the rest holds: the decision's ids, each answer named "#n's answer N", and a link to the round post that reversed it or, with none, to the new note, the new ADR or the decision ticket's resolution comment, quoting nothing (answer 64).
  - **The `planning-checker` agent:** its breakdown-check inputs, and its "How to report", which gains the list's notes beside its four kinds of finding.
  - **Left unedited:** the vendored `to-tickets` and `wayfinder`.

## Testing Decisions

Seams (answer 14):

1. **The command,** through `cli.main` on a scratch git repository, with GitHub from files or `--fetch` through `tests/fake_gh.py`. Only what it prints is tested, text and `--json`. Prior art: `tests/test_architecture_index.py` (spec #611's seam 1), merge-check's `--fetch` tests, doctor's fake-gh tests, `tests/test_fetch_by_page.py` (`page=N`), and a shallow clone in `tests/test_review_record_hashes.py`. It covers:
   - each citation form, lists and ranges included;
   - the citing sentence, and where it ends: in an issue's body, a "see #n" paragraph or list item, or a heading, above a sentence with a bare answer leaves that answer tied; a sentence ending in `."`, `.)`, `.**`, `!` or `?`, and at a blank line; "e.g." and "i.e." not ending one; "#n ans. N" and "spec #n ans. N" stay one sentence and tie; a table row is a sentence of its own; a sentence over several lines is given at the citation's line;
   - the vendored kit left out;
   - a citation inside a ticket's own `## Replaces` left out, for passages and for the ticket built on a decision (`#682` within `#682:answer:44` on a run for `#682`), except that a closed ticket's `## Replaces` naming the asked id whole marks it `replaces` (answer 70), and a citation elsewhere in that body still listed;
   - the tie of a bare answer: a named `#n` in each naming form (a list after "on", the space-only forms), a named ticket "spec unsure", an unjoined item issue tying to itself, an issue body's spec for a sentence with no `#n`, a body sentence with only unnamed `#n` "spec unsure", a bare answer in a file with no named `#n` listed as "spec unsure";
   - a map's `#n` named without its item's spec, alone and beside another `#n` that ties ("spec unsure"), and named with its item's spec (tied to it), with another answer in the same sentence, named by its own `#n`, still tied;
   - a decision ticket named, and a decision ticket's and an unjoined item issue's own body tying to themselves, with `kind: decision` in `--json`;
   - a decision ticket claimed by an assignee alone, as `claimed`;
   - an open issue that an open pull request closes, a ticket and an issue of another kind, as `claimed`;
   - the history fetch in a shallow clone, and a failed fetch reported;
   - answer numbers read only from a round post's own lines, in the `**N. ` and table forms, with an unnumbered post ignored, and write access and the agents' marker required;
   - the "Planned as" join, the map-body join for open and closed maps, and their skips;
   - in an issue's body, a sentence with a named `#n` tied by that `#n` alone, never by the body's own spec, even when the named `#n` doesn't hold that number;
   - each `kind`: a pull request, a spec, a decision ticket, a build ticket, a run's tracking issue and its by-hand issue as `run`, and an owner task, an item issue and a research issue as `other`;
   - a decision ticket's own round posts: a tie to one whose posts hold no such number "spec unsure", a tie kept when none were read, and its confirmed lines in `changed_by`, and the same check for an open, unjoined item issue's tie;
   - a map's id: only "spec unsure" citations listed (a closed ticket's among them, its pull request in `built_by` marked `spec_unsure`), and a merged ticket whose `## Replaces` names the map's id marked `replaces` and `spec_unsure`, the text output and the record's body saying so, and the record headed by the map's issue;
   - the record of a decision ticket's, and of an open, unjoined item issue's, answer headed by that issue;
   - a run whose state can't be read: the command goes on and names the run;
   - a quick ticket with no parent spec making a body citation "spec unsure";
   - a closed ticket's pull request listed in `built_by` marked unsure;
   - a merged ticket whose own `## Replaces` names the asked id listed in `built_by` marked `replaces`: found by its `## Replaces` alone, listed once when its body cites the id too, not `spec_unsure`, the mark in the text output and the record's counts-and-files form, a ticket whose `## Replaces` names another spec's answer of the same number left unmarked, one naming the joined item issue's answer (`#679:answer:3`) marked on a run for the spec's id, `ADR:7` matching `ADR:0007`, a ticket for the rest closed as not planned not listed, and `counts.built_by` counting the marked entry (answer 70);
   - a merged ticket found by its `## Replaces` line `#<map>:answer:N` alone (no other tie on that run) marked `replaces` and `spec_unsure` on a run for a spec a Destination item of that map links, counted in `counts.spec_unsure`, and not listed on a run for a spec no item of that map links (answer 71); the same ticket also found by a tied body citation, or by a whole-id `## Replaces` line for the spec's id, listed once, `replaces` and not `spec_unsure` (answer 73);
   - several named `#n`;
   - a sentence holding several citations of the asked answer, one tied and one "spec unsure" (with or without a bracket after a bare answer), listed once as one passage, tied (answer 65);
   - `--on` for an ADR id;
   - a sensitive sentence left out;
   - saved copies, fingerprint files and style-file colours left out;
   - a record counting for its ids wherever it is posted, `graph owner-tasks` leaving out an owner task whose list a round post on another issue carried;
   - `#682:answer:44` in an open pull request's prose listed on a run for `#682`, not on one for `#682:answer:44`;
   - a closed owner task, decision ticket or item issue citing the decision not read for `built_by`;
   - `counts.files` counting distinct passage files, not `built_by` pull requests' files;
   - the map-body join with a `Blocked by:` on the item's line and with "(spec #n)" linking it;
   - `--on N` with several ids, ids sharing a record issue sharing one body;
   - open issues and open pull requests citing it;
   - the ticket built on a decision (a merged pull request's closing keywords, "Fixed #n" among them, and `run.ticket_branch` in a merge commit), and its pull request's files;
   - the confirmed lines that changed the answer;
   - several ids in one run;
   - the record's body, `--around`, the switch to counts and files past the limit, and `--counts-only`;
   - `graph owner-tasks`: write access, the lock file's date (a commit whose committer date carries a non-UTC offset, and an owner task closed within that offset of the kit update), and a plugin project;
   - a counts-and-files record still past the limit cut to fit: every id's counts, the fixed lines and every `built_by` pull request's number and marks kept, every id's passage files dropped (the later ids' first) before any pull request's files (the later ids' first), the "and N more files and M more pull request files" line, the marker kept; and, when the text plus everything the cut keeps (the "and N more" line, the marker and each record issue's heading among it) is past it, `--around` refused with the size and the limit and `--record` printing the counts, the fixed lines and the "too large to list" line, marked (answers 74, 76, 77 and 84);
   - `--record` for a note with no `Issue:` header refused without `--on N`;
   - a `## Replaces` heading inside a fenced block or a `>` quote not read as the body's own;
   - `--fetch` by page.
2. **The skills', the agent's and the flow's text,** read as text contracts on the shipped `start`, `next`, `conductor`, `build-ticket`, `study`, `agents/planning-checker.md` and `docs/flow.md`, as `tests/test_end_check.py` and `tests/test_breakdown_check.py` do. Each test reads one part and checks what it requires, not its wording. It covers:
   - who runs the command and when;
   - advice only, including the breakdown check's notes;
   - the planning session's edits, notes and ticket for the rest: open pull requests, claimed issues of any kind, and a run's tracking and by-hand issues noted, each note ending with the agents' marker; other non-ticket issues and unclaimed decision tickets edited directly;
   - the ticket for the rest carrying its `## Replaces`, each passage listed by its `file:line` alone, never its sentence, cut to fit an issue body (`review-record`'s limit) with an "and N more passages" line (answer 75), and the note alone for every noted issue, a claimed build ticket and one an open pull request closes included, the note naming the decision only, never the ticket for the rest, with `start`'s three "becomes a new ticket" places saying they don't apply to the list's notes;
   - the ticket for the rest as one of the breakdown's build tickets inside a spec's breakdown (`start`'s Spec step 3's breakdown paragraph), and as a quick ticket everywhere else (the other two places), its body naming each answer with its spec ("#n's answer N"); in a breakdown, it names that way each answer of a spec other than its parent, and any answer in a sentence that holds a `#n`;
   - in `start`'s Quick ticket path, the item's issue of a ticket for the rest naming the decision's ids, each answer as "#n's answer N", and linking the round post that reversed it, or with none the new note, the new ADR or the decision ticket's resolution comment, quoting nothing, with every passage under `## Decided for you` as its `file:line`, before **Publish it**;
   - `## Replaces`, its ids in the command's own form, one per list line, in flow §2 and `start`;
   - where a session posts a record, a note's and an ADR's among them, and, when `--around` is refused, the round posted without the list and `--record`'s body as its own comment (answer 74);
   - the conductor's briefing and the breakdown check taking the list from the command's `--json`, never from a record's body (answer 74);
   - marking a note superseded, in the flow's "Research" and `study`;
   - the answer line's and the map comment's forms, and the agents' marker, in "Each round";
   - the conductor's and `/next`'s records and briefings;
   - `build-ticket` at claim.

A good test checks what the command prints or what a rule requires, never how the command finds it. Left untested: whether a session acts on the list, and the real GitHub API.

## Out of Scope

- The files parallel tickets will touch: #680, the next slice.
- Glossary terms as decisions (answer 2).
- Reviewers getting the list (answer 9).
- A profile setting for a project's own citation forms (answer 11).
- Links through code symbols (answer 6).
- A glossary entry for the project graph (answer 10).
- Blocking anything (answer 5).
- A noted build ticket's change carried in the ticket for the rest, what happens when that ticket closes, a ticket for the rest left empty or edited by hand, and claimed tickets that list it as a blocker: the follow-up item #714 (answer 66).

## Further Notes

- The backtest has two replayable cases. A wrong call shows as a list too long or too short, and the command's output makes that visible.
- The backtest's citation count also took citations of the building ticket's `#n`. This spec doesn't list those: it lists that ticket's pull request's files.
- **Work in flight** when this spec was written:
  - **Spec #268** (`CLAUDE.md` as a short index), whose tickets #269–#276 aren't built:
    - #273 changes the run's briefing, where this spec adds the passages. #273 is itself held, waiting for an edit to #268, so the conductor's briefing part is its own ticket, blocked by #273, and the other skill rules don't wait for it.
    - #271 and #272 extend `workflow index` in `cli.py`, beside `workflow graph`.
    - #275 adds a glossary entry to a glossary at 6,430 of its 6,500-character cap. That doesn't change answer 10.
    - #268's own rules for the flow's §2 and `build-ticket`'s lasting-knowledge step change the same files as this spec's flow and skill tickets, in other parts.
  - **#672 (PR #677)** changes `build-ticket`, `conductor`, the ticket-session template and the run's state, the files this spec's skill tickets change, in other sections. Those tickets waited for #672 to merge; PR #677 has merged since.

  Of these, only #273 goes into a ticket's `## Blocked by` (the conductor's briefing ticket): the others change other parts of the same files (#275 a file this spec doesn't change; #672 has merged) (answer 81).
- Pull requests rebased in, with no `#N` in their commits, aren't tied by answer 15's git rule. Their "Closes #n" still ties their ticket (answer 20).

- **The open questions are settled:** the end check's re-read on #679 left three open, and the owner answered them on this issue after publishing. Answer 25 settled the unnamed `#n`, answer 26 a map's several items' rounds, and answer 27 the other open issues. Answers 28 and 30 settled what their round's check found: the naming forms, and open pull requests and claimed decision tickets. Answer 29's history tie was replaced by answer 31.

- **The re-read's eight questions are settled too:** the re-read after answers 25–30 left eight open, and the owner settled them with answers 31–37. Answer 31 simplified the tie, which settles questions 5 and 7. Answers 32–37 settle the rest.
- **The command's own id form in prose:** `#n:answer:N` isn't one of answer 11's citation forms, so outside `## Replaces` it is read only as a `#n` citation: an open pull request's body saying "replaces `#682:answer:44`" is listed on a run for `#682`, not on one for `#682:answer:44`. Reading it as an answer citation would widen answer 11, which no answer does.
- **"answers N" in other wording:** "answers N" also matches ordinary wording such as "the route answers 503" in a project using the kit. Such a match is treated like any bare answer (in a file, "spec unsure"; in an issue's body with no `#n`, tied to that body's spec), and is listed only on a run for that number, so it is harmless.
- **What the simple tie gives up:** in a project using the kit, about 470 of 797 lines citing "ans. N" have no `#n`. They come out "spec unsure", still listed for a run on that answer (answer 31).
- **Not covered by the automatic run:** a closed `ready-for-human` owner task (`graph owner-tasks` reads the `owner-task` label, as answer 16 says), and the answers of an item whose rounds were posted on its issue before it was published as a quick ticket: publishing drops the `workflow:item` marker, so a named "#q answer N" is "spec unsure" (answer 34).
- **A map's own id:** `cites #<map>:answer:N` lists only "spec unsure" citations, with no numbers check and nothing in `changed_by`. Until the map links the Destination item's spec, a reversed answer of that item gets no more than that; once it does, the answer is asked by the spec's id (answer 39), and a merged ticket whose `## Replaces` names the map's id is still marked there, `spec_unsure` too (answer 71), unless, on that run for the spec's id, a certain tie or a `## Replaces` line naming `#<spec>:answer:N` whole also finds it (answer 73).
- **The open questions after answers 31–37 are settled:** the re-read after answers 31–37 left two questions and a list of lines never confirmed, and the owner settled them with answers 38–41. Answer 38 settled a decision ticket's own rounds, and answer 39 a map's id. Answer 40 settled a rule the body held that no answer said (claimed issues and a run's two issues; the round's check added `kind: run`), and answer 41 what that check found (the three reads beyond answer 3). The lines were confirmed in that round's post. The re-read after them left one question, an open issue that an open pull request closes, and answer 42 settled it.
- **Answers 43 and 44:** planning round 9 on the edited body sent one question, a map named beside another `#n`, and answer 43 settled it. Answer 44 settled the question the re-read after answer 42 left open, a noted issue and `start`'s "becomes a new ticket" (answer 44 is replaced by answer 64), and that re-read's two lines were confirmed in the same round's post.
- **Answers 45–63, and the split (answers 64–66):** answers 45–63 grew the ticket for the rest into a lifecycle (a noted build ticket's change carried in it and blocking it, its closes, the owner editing it by hand, claimed tickets' blockers, and how listed text is written in it), and 21 planning rounds didn't come clean, mostly on it. Edit round 12 split it out: answer 64 keeps the plain form here (passages by `file:line` alone, the note only for every noted issue) and replaces answers 44, 48, 52, 57, 59, 62 and 63; answer 65 replaces answer 61; answer 47 (the ticket for the rest's kind) stays here, as narrowed by answer 64; answer 66 moves answers 44 (replaced here), 45, 46, 49–51, 53–56, 58 and 60, and the three questions then left open (two by the re-read after answers 60–63, one by planning round 21), to the follow-up item #714 as its starting point, as recommendations, not settled answers. Its eleven lines were confirmed in that round's post.
- **Answers 67–69:** the re-read after answers 64–66 left two questions open, and planning round 22 found that holding the ticket they touch would settle them through **Settling a held-back ticket**, the path the old question 3 (now in #714) found faulty. The owner settled them in edit round 13: answer 67 settles them now, answer 68 keeps answer 47's naming rule for the ticket for the rest's own prose and brings back the breakdown case, and answer 69 has the note name the decision only, never the ticket for the rest. Their three lines were confirmed in that round's post.
- **Answer 70:** planning round 24, the last round in its session, left one question, a merged replacing ticket in `built_by`, and the owner settled it in edit round 14: a closed ticket whose own `## Replaces` names the asked id is found by that section and listed in `built_by` marked `replaces`, not `spec_unsure` (answer 71 narrows that for a map's id). Its line, "answer 70 widens 3", was confirmed in that round's post.
- **Answer 71:** planning round 25 on the edited body sent one question, how answer 70's mark treats a map's answer id in `## Replaces`, and the owner settled it in edit round 15: both marks, `replaces` and `spec_unsure`, on a run for the map's id and on a run for the spec a Destination item of that map links. Its three lines ("answer 71 widens 39", "answer 71 widens 70", "answer 71 narrows 70") were confirmed in that round's post.

- **Answers 72–75:** the three open questions (one left by each of the re-reads after answers 70 and 71, and one by planning round 27) were settled in edit round 16: answer 72 confirmed "answer 70 widens 6" and "answer 70 widens 7"; answer 73 has a certain tie win over a map-id match on the same run (narrowing answer 71); answer 74 cuts a record still past the limit as counts and files to fit, rather than refusing it (narrowing answers 8 and 19); and answer 75, which the check before that round raised, cuts the ticket for the rest's `file:line` list the same way past an issue body's limit (narrowing answer 64). Their six lines were confirmed in that round's post. The re-read after them left three questions open ("Open questions").

- **Answers 76–83:** the breakdown check's round. Its first finding held tickets for the three questions the re-read after answers 72–75 left, so they were asked there: answer 76 refuses `--record` or `--around` only when the text plus everything the cut keeps is past the limit, and answer 77 cuts kind first, every id's passage files before any pull request's files (both narrowing answer 74); answer 78 confirmed "answer 74 narrows 9". Answers 79–83 placed what the check found in the breakdown (answer 81: only #273 blocks a ticket, among the work in flight). The round's lines were confirmed in its post.

- **Answers 84–88:** the breakdown re-read's round. Answer 84 has `--record` never refused: past even what the cut keeps, it prints a marked body of counts, the fixed lines and "too large to list", so a closed owner task still gets a record (narrowing answer 76, which stays for `--around`). Answer 87 has the session cut a ticket for the rest's last N passages in `--json` order, so the breakdown check knows which the line covers. Answers 85, 86 and 88 placed rules and blockers in the breakdown. The round's line was confirmed in its post.
**Open questions.** None.
