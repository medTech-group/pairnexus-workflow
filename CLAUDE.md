# pairnexus-workflow

This repository is the pairnexus workflow kit itself, and it is built with the kit.

## Workflow

Work here follows the kit's flow: `.claude/workflow/flow.md` (plan → spec → build tickets → one session per ticket → review panel → merge), with this project's profile in `.claude/workflow/profile.toml` and `profile.md`. Read both before acting.

- A session starts with the guided start: the `start` skill asks "What are we working on?" (or type `/start`). `/next` finds a ready ticket and builds it.
- Build tickets are the sub-issues of the specs #32 to #42. Each has an `Area:` line and a `## Blocked by` section; the planning is on the closed map #13.
- **Two copies of the kit.** Edit the source (`scripts/`, `skills/`, `agents/`, `templates/`, `docs/`). The vendored release in `.claude/` is what sessions run under, and is changed only by the kit's update pull request.
- The release rules are in `CONTRIBUTING.md`: build tickets add changelog notes under `## Unreleased` and never bump `VERSION`.

## Agent skills

### Issue tracker

Issues and specs are GitHub issues in `medTech-group/pairnexus-workflow`, used through the GitHub MCP tools or `gh api`. See `docs/agents/issue-tracker.md`.

### Triage labels

The default five: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context, with the kit's glossary in `docs/glossary.md` rather than a root `GLOSSARY.md`. See `docs/agents/domain.md`.
