# Contributing

Thank you for helping. This kit started inside one team (PAIR, MedTech LLC) and is shared as it is: issues and pull requests are welcome, and it is maintained on a best-effort basis.

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
- `docs/`, except `proposal.md` and `spike.md`;
- `LICENSE`;
- the hook set.

Plugin users get the whole repository at `main`.

A change to shipped files also:
- bumps `VERSION` and `.claude-plugin/plugin.json`;
- adds a `CHANGELOG.md` entry, with a "For projects updating" list when a project must do something.

**Don't tag by hand:** the `release` workflow publishes each version when its bump lands on `main`. README, CHANGELOG-only, `tests/` and `.github/` changes need no bump.

**The kit's home.** Shipped files don't name this repository outright: they read `workflow version --repo` (`KIT_REPO` in `scripts/workflow/updates.py`), so forks work. A test lists the few places that still do.

**Writing.** The skills, docs and README are read by people and by Claude:
- plain words and short sentences;
- the same name for the same thing everywhere;
- say what happens, not what might.

Keep a skill's instructions where they act, not in a separate essay.

**The glossary.** `docs/glossary.md` holds the kit's words for someone new to building, and ships to projects:
- a new kit term a person meets goes into `docs/glossary.md` in the same pull request: a heading, one or two sentences, then "Why it matters to you:";
- the whole file stays under 6,000 characters, because the context hook adds it whole at a new-to-building session's first prompt (#35), within Claude Code's 10,000-character cap;
- a session using `domain-modeling` on the kit treats `docs/glossary.md` as the kit's glossary (`docs/agents/domain.md`), not a root `GLOSSARY.md`.

## Pull requests

- One change per pull request, with what it does and why, and how you tested it.
- CI must be green. A maintainer reviews and merges it. Only the maintainers merge, because plugin users follow `main` directly.
- By contributing, you agree that your contribution is licensed under this repository's [MIT licence](LICENSE). No separate agreement or sign-off is needed.

## Conduct

Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md).
