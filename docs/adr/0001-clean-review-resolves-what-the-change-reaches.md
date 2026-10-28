# A clean review resolves everything the change touches or reaches; old bugs outside it become fix tickets

A build review round or pass is clean when it leaves no blocking finding open, not when it finds nothing. A finding blocks, whatever its severity, when it is in the change's own lines, anything the change breaks elsewhere, anything the change makes reachable (a new button calling an old broken function), an acceptance criterion not met, new behaviour without a test, a safety breach the change adds, or a breach of a written rule in the project's rules documents in the change's own lines. A real defect in code the change neither touches nor reaches is filed at once as a ready build ticket (a fix ticket, never `needs-triage`) and built next in its own pull request; a security or safety one names only the area in public. A reviewer's preference that no written rule backs is noted and dropped.

We decided this because a panel that counts every finding rarely converges. Of 84 review rounds on 29 merged ticket pull requests before this, 8 were clean, and in run #355 two tickets reached their pass caps, each pass finding something new in code the change hadn't touched (#360). The owner wants nothing broken to carry past a merge and no pile of issues to sort. So the clean review stays the merge gate for the change and everything it reaches, and only unrelated old bugs move out of the pull request, into tickets that are built rather than triaged.

## Considered Options

- **Every finding blocks** (the rule before this): reviews didn't converge, and the pass cap handed working changes to the owner unmerged.
- **Only the change's own lines block, the rest filed as `needs-triage` follow-ups:** rejected. A regression the change causes in a caller it didn't touch, or an old broken function its new button calls, would merge, and the owner would sort a growing pile of issues.
- **Only critical- or important-severity findings block:** rejected, because a minor defect the change reaches would merge.
- **The ticket session classifies findings:** rejected, because the builder would judge its own work. The reviewer marks each finding; the session may contest a mark, and the next reviewer rules. A blocking finding the session answers "not a problem" also waits for the next reviewer.

## Consequences

- Reviewers review the change and what it reaches, not unrelated code.
- The rule applies to build reviews only. Planning reviews (a spec's draft, a map decision's ADRs and glossary) still count every finding.
- It arrives with a project's kit update, with no setting. A run in progress keeps the rule it started with.
