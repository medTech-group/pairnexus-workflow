# A clean review resolves everything the change touches or reaches; old bugs outside it get a ticket to fix them

A build review round or pass is clean when it leaves no blocking finding open, not when it finds nothing. A round or pass that reports a blocking finding is not clean, even once the finding is fixed: the next round or pass checks the fix.

A finding blocks, whatever its severity, when it is:

- a defect in the change's own lines;
- anything the change breaks elsewhere;
- anything the change makes reachable (a new button calling an old broken function);
- an acceptance criterion not met;
- new behaviour without a test;
- a safety breach the change adds;
- a breach of a written rule in the project's rules documents, in the change's own lines.

A real defect in code the change neither touches nor reaches is filed before the merge as a ticket to fix it: a ready build ticket, never `needs-triage`. A run builds it next in its own small pull request. In attended work, spec #362's reading is that the session names these tickets and offers to build the first. Spec #362 also reads answer 26's "only a preference … is dropped" as meaning that a written-rule breach outside the change's lines gets a ticket too. A reviewer's preference that no written rule backs is noted and dropped.

There are two exceptions. A ticket to fix a problem in a protected path is filed as an owner task instead. A security or safety problem in code already on `main` names only its area in public, its details go to the owner privately, and a ticket to fix one is always filed `ready-for-human`, so nothing builds it unattended. In a run it is held for the owner: a blocking one stops its ticket at `needs-human`, and a ticket to fix one isn't added to the run.

We decided this because reviews weren't converging. Of 261 review rounds on the 90 merged ticket pull requests before this, 15 were clean, and #340 and #349 reached their pass caps (#360). The owner wants nothing broken to carry past a merge and no pile of issues to sort. So the clean review stays the merge gate for the change and everything it reaches, and only problems outside what the change reaches move out of the pull request, into tickets that are built rather than triaged. Whether this alone makes reviews converge is untested: the records don't say what each finding was about, and a run under this rule is the check.

## Considered Options

- **Every finding blocks** (the rule before this): reviews didn't converge, and the pass cap handed changes to the owner unmerged.
- **Only the change's own lines block, the rest filed as `needs-triage` follow-ups:** rejected. A regression the change causes in a caller it didn't touch, or an old broken function its new button calls, would merge, and the owner would sort a growing pile of issues.
- **Only critical- or important-severity findings block:** rejected, because a minor defect the change reaches would merge.
- **The ticket session classifies findings:** rejected, because the builder would judge its own work. The reviewer marks each finding. The session may contest a mark with a written reason, and the next reviewer rules. A blocking finding the session answers "not a problem" also waits for the next reviewer.

## Consequences

- Reviewers review the change and what it reaches, not unrelated code.
- The rule applies to build reviews only. Planning reviews (a spec's draft, a map decision's or a spec session's ADRs and glossary, and, in phase 2, a breakdown's review) still count every finding. Extending the rule to them is out of scope here; it is filed as #363.
- It arrives with a project's kit update, with no setting. Until spec #362's phase-1 tickets reach a project in its kit update (this repository included), every finding still blocks. A run in progress keeps the rule it started with. An attended pull request open across the update follows the new rule from its next round or pass.
