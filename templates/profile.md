# Workflow profile: <project> (prose)

What every session and reviewer reads beside `profile.toml`. Point to the project's own rules; don't copy them here, so nothing drifts.

## The project's rules

- Safety rules: `CLAUDE.md#safety-constraints` <!-- the anchors reviewers check every diff against -->
- Wording rules: <!-- e.g. a style guide, banned terms -->
- Architecture decisions: `docs/adr/`

## Sensitive data

What counts as sensitive here, and where it must never appear (issues, comments, PR bodies, logs, notifications, screenshots kept in the repo):

- <!-- e.g. Patient data: names, dates of birth, record contents. Refer to records by id only. -->

The guard checks outward GitHub posts against `[sensitive].patterns` in `profile.toml`. Patterns catch only what they describe; this list is the rule.

## Secrets

- Never print, commit or post a secret. Config files that hold keys are the owner's to add.
- Writing a secret anywhere (a parameter store, a CI secret) is outside a ticket session's reach; for the conductor it needs a charter grant and goes in the ledger.

## Anything else sessions should know

<!-- Environment quirks, slow suites, flaky areas, where the by-hand checks usually are. -->
