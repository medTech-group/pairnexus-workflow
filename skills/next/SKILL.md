---
name: next
description: Find the next ready piece of work (a map decision, a spec to write, or a build ticket) and do it under the workflow's flow. Optional argument - "map", "spec", "build", or an issue number.
---

# Next

Pick one ready piece of work and do it, following the flow (`.claude/workflow/flow.md`, or the plugin's `docs/flow.md`). One piece per session.

Read the flow and the project's profile (`.claude/workflow/profile.toml`, `profile.md`) first. Use the GitHub MCP tools, or `gh api` where the session has it.

## 1. Find what is ready

**Build tickets:** run the readiness check rather than judging by eye:

```bash
python3 .claude/workflow/bin/workflow.py ready --fetch
```

Where `gh api` isn't available, fetch every issue (open and closed, `state=all`) and the open pull requests with the GitHub MCP tools, save them as JSON, and pass `--issues issues.json --prs prs.json`. It lists each `ready-for-agent` ticket as READY or why not:
- a blocker that is open, unknown, or closed as not planned;
- `needs-human` or `owner-task`;
- claimed (`workflow:in-progress`);
- an open PR closes it.

**Maps and specs:**
- A **map** is an issue labelled `wayfinder:map`. Its ready decisions are its open, unclaimed child tickets whose blockers are closed, in the order `get_sub_issues` returns them. A map's Notes may reorder its own frontier.
- A **clear map** has no open children and nothing under "Not yet specified". Its first Destination item with no spec linked is ready to spec.

## 2. Pick one

With an argument: `map`, `spec` or `build` picks from that group; a number picks that issue (say why if it isn't ready, and stop).

Without one, in this order:
1. A map decision that needs the owner.
2. A clear map's next spec.
3. The lowest-numbered ready build ticket.

Say which one and why in one line. Then claim it and follow the matching section of the flow.

## 3. Nothing ready

Say what is blocked and on what (an owner task, an open blocker, a PR in review), and stop.
