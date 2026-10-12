---
name: next
description: Find the next ready piece of work (a map decision, a spec to write, or a build ticket) and do it under the workflow's flow. Optional argument - "map", "spec", "build", or an issue number.
---

# Next

Pick one ready piece of work and do it, following the flow (`.claude/workflow/flow.md` vendored, or `docs/flow.md` beside `skills/` as a plugin). One piece per session.

Read the flow and the project's profile (`.claude/workflow/profile.toml`, `profile.md`) first. Use the GitHub MCP tools, or `gh api` where the session has it. `WF` is the kit's CLI: `python3 .claude/workflow/bin/workflow.py`, or `python3 <this skill's directory>/../../scripts/workflow.py` as a plugin.

## 1. Find what is ready

**Build tickets:** run the readiness check rather than judging by eye.

```bash
WF ready --fetch
```

Where `gh api` isn't available, fetch the issues and PRs with the GitHub MCP tools, save them as JSON, and pass them with `--issues issues.json --prs prs.json`:
- every issue, open and closed (`state=all`), with its labels, body, `state_reason`, `sub_issues_summary` and `issue_dependencies_summary`;
- the open pull requests.

It lists each `ready-for-agent` build ticket as READY, or gives why not:
- a blocker that's open, unknown, in another repository, or closed as not planned;
- a GitHub issue dependency;
- `needs-human`, `ready-for-human` or `owner-task`;
- claimed (`workflow:in-progress`);
- an open PR closes it.

It leaves out specs (the `spec` label, a "Spec:" title, or an issue with sub-issues) and maps.

**Maps and specs:**
- **A map** is an issue labelled `wayfinder:map`. Its ready decisions are its open, unclaimed child tickets whose blockers are closed, in the order `issue_read` with method `get_sub_issues` returns them. A map's Notes may reorder its own frontier.
- **A clear map** has no open children and nothing under "Not yet specified". Its first Destination item with no spec linked is ready to spec.
- **The gate:** a map's build tickets wait until every Destination item of that map has its spec and its tickets.

## 2. Pick one

**With an argument:** `map`, `spec` or `build` picks from that group. A number picks that issue; if it isn't ready, say why and stop.

**Without one,** in this order:
1. A map decision that needs the owner.
2. A clear map's next spec.
3. The first ready build ticket: `workflow:infra` first, then the lowest number.

Ready research tickets start at once in background subagents (the `research` skill), alongside whatever you pick.

Say which one you picked and why, in one line. Then claim it and follow the matching section of the flow. At the end, name what comes next.

## 3. Nothing ready

Say what is blocked and on what (an owner task, an open blocker, a PR in review), and stop.
