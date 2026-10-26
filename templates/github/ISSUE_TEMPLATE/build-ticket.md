---
name: Build ticket
about: One buildable slice of a spec, for a session to build
labels: ["ready-for-agent"]
---

Area: <one of the profile's [areas]>
<!-- Add a line reading `Review: small` here only when you expect the change to stay within the small threshold (the profile's run.small_max_lines changed lines in run.small_max_files files, outside tests) and to add no endpoint, table, screen or setting: the ticket can then get the small review (one round of Correctness while its diff stays within the threshold). Without the line it gets the usual review; deleting the line later opts the ticket out. -->

## Parent

#<spec>

## What to build

<the slice, end to end>

## Acceptance criteria

- [ ] <criterion> (seam: <where it's tested>)

## By-hand checks

<what needs a real device, account or service, or "None">

## Blocked by

None
