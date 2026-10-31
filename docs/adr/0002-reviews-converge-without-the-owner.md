# Reviews converge without the owner: a finding needs a reproducer, fixes narrow first, and a mechanism that keeps failing is made to fail closed or split out

A build review's loop never waits for a person, in a run or in attended work. It ends in one of four ways: a clean review, a mechanism replaced by its fail-closed form, a mechanism split into a ticket the run builds next, or the run's end time (and the next run takes the ticket up from its hand-off). Four rules make that converge:

- **A blocking finding needs a reproducer:** for code, an input and the result it should give; for skill or doc text, a scenario and the two lines that answer it differently; for an unmet criterion or untested behaviour, the criterion quoted and the test that should exist. Without one, the finding is a note.
- **Fixes narrow first,** made by a fresh fixer agent each round: removing a case, refusing more or deleting text comes before adding an exception, and a fix that adds one tests both sides of it.
- **From round 2, reviewers look at what changed since the last review and what it reaches.** A finding on lines unchanged since a review that covered them becomes a ticket to fix it, built next, unless it is a safety breach or loses data. This changes ADR 0001 for those lines only: there, every finding in the change's own lines blocks, whichever round finds it.
- **When the same mechanism blocks in two reviews in a row,** `merge-check` says so from the review records, and the session replaces it with the fail-closed form its ticket's bar names, or splits it out, its acceptance criterion moving with it. A mechanism is split once.

We decided this because the owner wants runs to be unattended, and the caps and stops before it ended a review that didn't settle with the owner (#402's `until-clean` moved that to the run's end time). Of 116 findings from round 3 or a pass on nine slow ticket pull requests, about 46% were defects in an earlier fix and 21% edge cases of edge cases; the long tails each began where a fix added an exception (#359's requeue, #401's "a repository made earlier in the same command"), and ended only when a person split the mechanism out or a simpler, stricter rule replaced it. Fresh full re-reviews found more in round 3 than round 2 on 4 of the 9. The rules turn those two endings into steps the loop takes itself.

## Considered Options

- **More passes, no change to the loop** (`until-clean` alone): a review that doesn't settle runs to the end time and still ends with the owner.
- **Ask the owner at milestones** (#362's notices and soft budget): a run can't wait for an answer.
- **Every finding in the change's own lines blocks, whatever round finds it** (ADR 0001): each fresh full re-review finds a different set, so late rounds keep reopening reviewed lines.
- **Only critical findings block late:** rejected, as in ADR 0001; a minor defect a fix introduces still blocks, because it is in what changed since the last review.

## Consequences

- Guard and conductor tickets must carry a `## Bar`: what they must handle, their fail-closed behaviour, and their accepted limits. Reviewers stop their hunt there.
- A pull request can merge with a mechanism split out; its criterion is then the new ticket's, never silently dropped.
- Security problems and protected paths still go to the owner, as ADR 0001 says.
- Planning reviews are unchanged (#363).
