# pairnexus-workflow

A Claude Code kit for building software from a spec, attended or unattended:

**plan → spec → build tickets → one session per ticket → review panel → merge**

…and, for unattended runs, a **conductor** that asks the owner a few questions once (the **run charter**), then builds every ready ticket in parallel sessions, merges what passes, releases if allowed, and reports, without waiting on anyone mid-run.

It packages what worked over the pair-drop weekend run of 9–12 Oct 2026 (about 50 tickets), with the fixes for what didn't.

## What's in it

| Part | What it does |
|---|---|
| `skills/setup-workflow` | Once per project: the interview, the profile, labels, CODEOWNERS, vendoring, the owner's one-time steps |
| `skills/next` | Find the next ready piece of work and do it under the flow |
| `skills/build-ticket` | One ticket from claim to merge |
| `skills/review-panel` | Standards, Spec, Correctness (with security) and a UI explorer, in parallel rounds until clean |
| `skills/conductor` | The unattended run: charter, sessions, check-ins, merges, release, stop |
| `skills/run-report` | The end-of-run report for the owner |
| `skills/update-workflow` | Update a project's vendored copy |
| `agents/` | The read-only Correctness reviewer and the UI explorer |
| `scripts/workflow.py` | The CLI the skills and hooks run: `ready`, `charter`, `state`, `render`, `evidence`, `repair`, `vendor`, `hook` |
| `hooks/` | Guard (the never-list), checklist gate, flow context, environment repair |
| `docs/` | `flow.md`, `charter.md`, `enforcement.md`, `install.md` |
| `templates/` | Profile, ticket-session briefing, tracking and by-hand issues |

Standards and Spec reviews, TDD, specs, tickets and maps come from [Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT), pinned in `.claude-plugin/marketplace.json` and installed alongside.

## Getting started

1. Install it: [docs/install.md](docs/install.md). Use **vendored** mode for any project that runs unattended.
2. In the project, run the `setup-workflow` skill.
3. The owner's one-time steps: [docs/enforcement.md](docs/enforcement.md). These are the base branch's ruleset and a credential-free cloud environment for ticket sessions.
4. Work ticket by ticket with `/next`, or start an unattended run with the `conductor` skill.

## Development

```bash
python3 -m pytest tests -q          # Python 3.11+, pytest
```

Every hook and script is tested with JSON fixtures, including attempts to get past the guard.

Releases are semver: `VERSION`, `.claude-plugin/plugin.json`, a `CHANGELOG.md` entry and a `v<version>` tag. Projects pin a release, and update with `update-workflow`.

## Licence

Private to medtech-group: see `LICENSE`. The Matt Pocock skills keep their MIT licence: `THIRD_PARTY-mattpocock-skills.txt`.
