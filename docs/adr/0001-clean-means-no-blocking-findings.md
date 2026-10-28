# A clean review means no blocking findings; the rest become follow-up issues

A build review round or pass is clean when it leaves no blocking finding open, not when it finds nothing. A finding blocks when it is a defect in lines the pull request adds or changes, an acceptance criterion not met, new behaviour without a test, a breach of the safety rules, or a breach of a written rule in the project's rules documents on the pull request's own lines, whatever its severity. Any other real finding (a defect in code the pull request doesn't touch, an improvement beyond the ticket) is filed as a `needs-triage` issue, named in the review record, and doesn't block: `merge-check` checks only that each named issue exists. A reviewer's preference that no written rule backs is noted and dropped.

We decided this because a panel that counts every finding rarely converges on a hard ticket. In run #355, every ticket needed all three rounds, and two reached their pass caps, each pass finding a new edge case in code it hadn't changed (#360). The clean review stays the merge gate, so no defect a change introduces carries downstream. What changes is that older problems and improvements are tracked as issues instead of holding the change. A reader seeing a known defect merge alongside a clean review should look for its follow-up issue, not assume the review missed it.

## Considered Options

- **Every finding blocks** (the rule before this): reviews didn't converge, and the pass cap handed working changes to the owner unmerged.
- **Only blocker- or important-severity findings block:** rejected, because a minor defect in the change's own lines would merge.
- **The ticket session classifies findings:** rejected, because the builder would judge its own work. The reviewer marks each finding; the session may contest a mark, and the next reviewer rules. A blocking finding the session answers "not a problem" also waits for the next reviewer.

## Consequences

- A review record names its follow-up issues, and a record written before this rule reads as naming none.
- The rule applies to build reviews only. Planning reviews (a spec's draft, a map decision's ADRs and glossary) still count every finding.
- It arrives with a project's kit update, with no setting. A run in progress keeps the rule it started with.
