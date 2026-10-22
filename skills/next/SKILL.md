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

A READY ticket may carry notes, which never change whether it is ready:
- "names protected path <path> (<pattern>): check it isn't an owner task";
- "spec #<n> has no clean review: check it before building", when its spec (its parent issue, labelled `spec`) has no clean review record for its current body from an account with write access. Specs created before the kit brought this in are never noted. When the spec's comments or their authors' permissions can't be read, the note says so: "spec #<n>: couldn't read its reviews (<why>)".

Where `gh api` isn't available, give each spec's comments in its `comments` field in `issues.json`, as a list (`issue_read` with method `get_comments`, every page), and the permissions of those who posted them with `--permissions perms.json` (`list_repository_collaborators`, every page). A spec whose comments aren't given is read with `gh api`.

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

Say which one you picked and why, in one line, with a build ticket's notes from `WF ready` beside it. "Spec #<n> has no clean review" is a warning, never a block: say so plainly ("its spec wasn't reviewed since it last changed: check it before building"), and the person decides whether to build it; in a ticket or conductor session, the briefing or the charter already did. For a build ticket, ask how first (below). Then claim it and follow the matching section of the flow. At the end, name what comes next.

**How to build it, in an attended session:** ask with the `AskUserQuestion` tool, or as a numbered list where it isn't available:
- **Build it now (Recommended)**: the full review panel;
- **Build it with a light review**: one review round, for a small change (`review-panel` §6, "The light review").

The light review is always second, never recommended, and never chosen for them. When they already said how ("build #12", "build #12 with a light review", "quick build #12"; the `build` argument alone isn't saying how), don't ask again: build it as they said. In a ticket or conductor session (`WORKFLOW_ROLE` set to anything but `attended`, or a branch named like the profile's `run.ticket_branch`), ask nothing: build as the briefing says.

## 3. Nothing ready

Say what is blocked and on what (an owner task, an open blocker, a PR in review), and stop.
