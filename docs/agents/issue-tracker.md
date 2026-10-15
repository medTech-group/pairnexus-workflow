# Issue tracker: GitHub (medTech-group/pairnexus-workflow)

Issues and specs for this repo live as GitHub issues in `medTech-group/pairnexus-workflow`.

Claude Code cloud sessions have **no `gh` issue or pr subcommands to rely on**; use the GitHub MCP tools (`mcp__github__*`, loaded with ToolSearch if deferred), or `gh api` (REST) where the session has it. On a laptop with the GitHub CLI, the `gh` forms in parentheses work too.

## Conventions

- **Create an issue**: `issue_write` with `method: "create"`, `title`, `body`, `labels`; or `gh api repos/medTech-group/pairnexus-workflow/issues -f title=… -f body=… -f "labels[]=…"`. (`gh issue create`)
- **Read an issue**: `issue_read` with `method: "get"`, then `method: "get_comments"`; or `gh api repos/medTech-group/pairnexus-workflow/issues/<n>` and `…/comments`. (`gh issue view <n> --comments`)
- **List issues**: `list_issues` with `state`, `labels`; `search_issues` for text; or `gh api "repos/medTech-group/pairnexus-workflow/issues?state=open&labels=…"`. (`gh issue list`)
- **Comment**: `add_issue_comment`; or `gh api repos/medTech-group/pairnexus-workflow/issues/<n>/comments -f body=…`. (`gh issue comment`)
- **Labels**: `issue_write` `method: "update"` with the **full** new `labels` list (it replaces), so read the current labels first; or `gh api repos/medTech-group/pairnexus-workflow/issues/<n>/labels -f "labels[]=…"` to add. (`gh issue edit --add-label`)
- **Close**: comment with the reason, then `issue_write` `method: "update"`, `state: "closed"`, `state_reason: "completed" | "not_planned" | "duplicate"`. (`gh issue close --comment`)
- **Sub-issues**: `sub_issue_write` `method: "add"` with the child's numeric id (not its `#number`).
- **Blocking**: write a `## Blocked by` section in the body (issue refs, or "None"), even when GitHub's own dependencies are also set.

## Sensitive data

Never put the project's sensitive data (see `.claude/workflow/profile.md`) in an issue, comment or PR. Refer to records by id.

## Agents' posts

An agent's issues, comments and PR bodies go out under the owner's GitHub account. In a ticket or conductor session, end every body with `<!-- workflow:agent -->`, so the owner's own words can be told apart; the workflow guard refuses a post without it there. A ticket whose change is to a protected path (the profile's `guard.protected_paths`) is an `owner-task`, never a build ticket.

## Pull requests as a triage surface

**PRs as a request surface: no.**

## When a skill says "publish to the issue tracker"

Create a GitHub issue as above.

## When a skill says "fetch the relevant ticket"

Read the issue and its comments as above.
