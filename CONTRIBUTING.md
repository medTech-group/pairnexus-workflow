# Contributing

Thank you for helping. This kit started inside one team (PAIR, MedTech LLC) and is shared as it is: issues and pull requests are welcome. What it promises, the same as in the [README](README.md#support) and [SECURITY.md](SECURITY.md):
- best effort, with no guaranteed response time for issues or pull requests;
- security reports acknowledged within 5 working days;
- a fix release when a Claude Code update breaks the guard or the hooks.

## Before you start

- **Bugs and small fixes:** open a pull request, or an issue if you're not sure it's a bug.
- **Anything bigger** (a new skill, a change to how runs, the guard or the update path behave): open an issue first, so we can agree the approach before you spend the time.
- **Security problems:** never in public; see [SECURITY.md](SECURITY.md).

## Working on it

You need Python 3.11 or later and `pytest`:

```bash
python3 -m pytest tests -q
```

Every hook and script is tested with JSON fixtures, including attempts to get past the guard. A change to behaviour comes with a test that fails without it. CI runs the suite on Python 3.11, 3.12 and 3.13.

**What ships.** Projects receive what `vendor.plan` (`scripts/workflow/vendor.py`) copies:
- `skills/`, `agents/`, `scripts/` and `templates/`;
- `docs/`, except `proposal.md`, `spike.md` and `quickstart.md` (the quickstart is for the kit's readers, not a project's sessions);
- `LICENSE`;
- the hook set.

Plugin users get the whole repository at `main`, and the plugin's skills are `skills/`.

The repository's own `.claude/skills/` is for maintainers and never ships: it holds the vendored release this repository runs under, and the kit-only `release-gate` skill.

A change to shipped files also:
- bumps `VERSION` and `.claude-plugin/plugin.json`;
- adds a `CHANGELOG.md` entry, with a "For projects updating" list when a project must do something.

**Don't tag by hand:** the `release` workflow publishes each version when its bump lands on `main`. README, CHANGELOG-only, `tests/` and `.github/` changes need no bump.

**The release gate.** Every pull request gets a "release gate" check (`.github/workflows/release-gate.yml`, its decision in `.github/scripts/release_gate.py`):
- a pull request that doesn't change `VERSION` passes at once;
- a release pull request (one that changes `VERSION`) needs a gate report that says pass for its exact head commit: a maintainer runs the gate (below), and the gate report it posts on the pull request ends with `release-gate: pass <sha>`, the full 40-character SHA. Only a gate report carrying the agents' marker, from an account with write, maintain or admin permission, counts, and a later `release-gate: fail <sha>` for the same commit wins. Any later push means running the gate again;
- a comment added, edited or deleted re-runs the check, so nobody needs an empty push. GitHub doesn't re-run a run more than 30 days old: then push, or change a label.

**Running the gate.** In a cloud session on the kit's repository, ask "run the release gate on PR #N". The `release-gate` skill (`.claude/skills/release-gate/`) tries the pull request's exact commit on the sandbox, `medTech-group/pairnexus-workflow-sandbox`: an update to it on a `release-gate/<version>` branch with CI green, then a ticket session's push to `main` refused by the guard, then a push refused by the ruleset. It posts the gate report on the pull request. It takes about 30 minutes and needs the sandbox, its ruleset and its ticket environment, with the owner there to approve.

**Skipping the gate for an urgent fix** needs all three:
- the `release-gate-skipped` label;
- a "Gate skipped because …" line in the pull request's description;
- a "Release gate skipped because …" line in the new version's CHANGELOG entry. That entry becomes the release notes, so write the reason for project owners, in plain words: they read it to decide when to update.

Never twice in a row: the check refuses a skip when the previous version's entry, in the base branch's CHANGELOG, skipped too.

A change to the check's own workflow or script is reviewed as CI config. The check runs the base branch's copy of the script, so a change to the script takes effect once it has merged; a change to the workflow takes effect on its own pull request. To move the script, merge a copy at its new path first, then point the workflow at it in a second pull request.

**Finishing the gate,** after the release publishes. A pass leaves the sandbox pull request open. Once the release has published, ask "finish the release gate" in a cloud session on the kit's repository: the skill updates the sandbox pull request's branch from the release tag, stops naming the files if anything but the lock's source and version changed, says in the description that it holds the release, and merges it with a merge commit once its CI is green. The sandbox's `main` then holds the released version, ready for the next gate.

**The kit's home.** Shipped files don't name this repository outright: they read `workflow version --repo` (`KIT_REPO` in `scripts/workflow/updates.py`), so forks work. A test lists the few places that still do.

**Writing.** The skills, docs and README are read by people and by Claude:
- plain words and short sentences;
- the same name for the same thing everywhere;
- say what happens, not what might;
- everyday examples, so readers see their own project: a notes app, a shop, a booking page.

**Names in their places.** pair-drop, PAIR's own project, is named only in the README's "Where it came from"; patient data appears only as one sensitive-data example among others (phone numbers, payment details, children's names). The names test, `tests/test_example_names.py`, lists the allowed places and reads every file a project receives, plus the README and the quickstart; a new place is a deliberate change to that list. History (`CHANGELOG.md`, `docs/spike.md`, `docs/proposal.md`) keeps its names.

Keep a skill's instructions where they act, not in a separate essay.

**The glossary.** `docs/glossary.md` holds the kit's words for someone new to building, and ships to projects:
- a new kit term a person meets goes into `docs/glossary.md` in the same pull request: a heading, one or two sentences, then "Why it matters to you:";
- the whole file stays under 6,000 characters, because #35's context hook will add it whole at a new-to-building session's first prompt, within Claude Code's 10,000-character cap;
- a session using `domain-modeling` on the kit treats `docs/glossary.md` as the kit's glossary (`docs/agents/domain.md`), not a root `GLOSSARY.md`.

## Pull requests

- One change per pull request, with what it does and why, and how you tested it.
- CI must be green. A maintainer reviews and merges it. Only the maintainers merge, because plugin users follow `main` directly.
- By contributing, you agree that your contribution is licensed under this repository's [MIT licence](LICENSE). No separate agreement or sign-off is needed.

## Conduct

Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md).
