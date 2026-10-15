# Workflow profile: pairnexus-workflow (prose)

What every session and reviewer reads beside `profile.toml`. Point to the project's own rules; don't copy them here, so nothing drifts.

## The project's rules

The list of rule documents is `project.rules` in `profile.toml`: `CLAUDE.md` and `CONTRIBUTING.md`. `CONTRIBUTING.md`'s "Writing" section and its release rules matter most: plain words, the same name for the same thing everywhere, and a `VERSION` bump only in a release pull request (build tickets put their changelog notes under `## Unreleased`).

## Sensitive data

The kit handles no personal data of its own. What must never appear in an issue, comment, PR body, log or test fixture:

- secrets of any kind (tokens, keys), including in recorded GitHub data used as fixtures;
- real people's data: examples are made up and everyday (a notes app, a shop, a booking page), never patient data or pair-drop's (#37's names test).

The guard checks outward GitHub posts against `[sensitive].patterns` in `profile.toml`. Patterns catch only what they describe; this list is the rule.

## Secrets

- Never print, commit or post a secret. Config files that hold keys are the owner's to add.
- Writing a secret anywhere (a parameter store, a CI secret) is outside a ticket session's reach; for the conductor it needs a charter grant and goes in the ledger.

## Anything else sessions should know

- **Two copies of the kit.** The source is `scripts/`, `skills/`, `agents/`, `templates/` and `docs/`. The copy sessions run under is the vendored release in `.claude/` (protected): change the source, never the copy. The copy moves to a new release only through the kit's update pull request.
- **Releases.** Merging a `VERSION` bump publishes a release (`.github/workflows/release.yml`), so `VERSION`, `.claude-plugin/` and `.github/scripts/` are protected paths. A release PR is the owner's.
- **The kit-only skill** `.claude/skills/release-gate/` (#89) sits under the protected `.claude/`, so tickets that change it are reviewed and merged by the owner.
- **Tests:** `python3 -m pytest tests -q`. `tests/test_kit_018.py` needs an old Python 3.9 for its fail-closed checks: CI sets `OLD_PYTHON`; locally those cases are skipped without one.
- **By-hand checks** usually run on the sandbox, `medTech-group/pairnexus-workflow-sandbox`.
