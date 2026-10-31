# Reviews converge without the owner: a finding needs a reproducer, fixes narrow first, and a part that keeps failing is made to fail closed or split out

A build review's loop never stops to ask anyone, in a run or in attended work. It ends with a clean review; in a run, at the run's end time, after which a later run takes the ticket up from its hand-off on its own; in attended work, after 10 reviews that weren't clean in one session, with a status line and the hand-off left for the person to carry on. Security problems in code already on `main`, and protected paths, still go to the owner, as ADR 0001 says. Five rules make it converge:

- **A blocking finding needs a reproducer:** for code, an input and the result it should give; for skill or doc text, a concrete scenario and the two lines that answer it differently; for an unmet criterion or untested behaviour, the criterion or behaviour quoted and the test that should exist; for a breach of a written rule, the rule quoted and the line that breaks it. Without one, the finding is a note.
- **Fixes narrow first,** made by a fresh fixer agent for each review (round or pass), round 1 included: a defect's fix starts with a failing test from its reproducer (for a missing test, the test is the fix); a fix that removes a case, refuses more or deletes text is preferred; a fix that adds an exception, a state or a new rule tests both sides of its new boundary in the same commit.
- **From the second review (round or pass), reviewers look at the pull request's own changes since the last review and what they reach.** A finding on lines unchanged since a review that covered them becomes a ticket to fix it (built next in a run; named and offered after the merge in attended work), unless it is a safety breach, loses data, leaves an acceptance criterion unmet, leaves new behaviour untested, or is something the change breaks: those still block, whichever review finds them.
- **When the same part blocks in two reviews in a row,** counted from the review records across fixers and sessions (parts named by the reviewer, a name reused when it is the same part, a contested finding counted once, security findings never counted), `merge-check` says what comes next and the session does it: the fail-closed form its ticket's bar names, when the reviewer marks the part as one that form covers and it hasn't taken it yet; else, once per part, a split: the part is taken out of the pull request, which merges without it, into a ticket built next, any acceptance criterion that needs it moving with it, counted as moved, not unmet. A split-off ticket's own repeats take its fail-closed form, or go on to the end. The pull request body says which and why. Either way the next review checks the result.
- **Clean is worked out from the findings' marks** in the review records: a review that reports a blocking finding isn't clean, even once it is fixed, as ADR 0001 says. Records without marks are judged by today's rule: their own clean or not-clean result.

This changes ADR 0001 in four places: what blocks needs a reproducer; on lines already reviewed, only the kinds of finding named above block; a criterion moved by a split isn't unmet; and a run keeps the rule it started with, the next run using the new one, with no question asked.

We decided this because the owner wants runs to be unattended, and the caps and stops before it ended a review that didn't settle with the owner (#402's `until-clean` moved that to the run's end time). Of 116 findings from round 3 or a pass on nine slow ticket pull requests, about 46% were defects in an earlier fix and 21% edge cases of edge cases; the long tails began where a fix added a rule or exception, and in #359 and #401 ended when the part was split out (#361) or a simpler rule replaced it. Fresh full re-reviews often found more in round 3 than in round 2. The rules turn those endings into steps the loop takes itself.

## Considered Options

- **More passes, no change to the loop** (`until-clean` alone): a review that doesn't settle runs to the end time and still ends with the owner.
- **Ask the owner at milestones** (#362's notices and soft budget): a run can't wait for an answer.
- **Every finding in the change or what it reaches blocks, whichever review finds it** (ADR 0001): each fresh full re-review finds a different set, so late reviews keep reopening reviewed lines.
- **Only critical findings block late:** rejected, as in ADR 0001; a minor defect a fix introduces still blocks, because it is in what changed since the last review.

## Consequences

- A ticket may carry a `## Bar`: what it must handle, what it does when it can't be sure (its fail-closed form), and its accepted limits. A profile lists the areas whose tickets need one; this repository's are the guard and, until #411 moves the run states into code, the conductor. Reviewers stop their hunt there: a gap the bar accepts is a note.
- A ticket still not clean at a run's end time is carried on by a later run, not set aside for the owner, except one held for a security problem in code on `main` or a protected path.
- The light and small reviews keep their shapes and carry on with Correctness passes until clean.
- Spec #362's phase 1 owner stops are replaced; its marks, tickets to fix old bugs and hand-off are kept.
- Planning reviews keep counting every finding (#363).
