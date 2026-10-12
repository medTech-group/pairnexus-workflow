# Installing the kit

Two modes. Pick one per project: `setup-workflow` refuses both at once (the skills would be duplicated and the hooks would run twice).

| | Vendored (committed copy) | Plugin |
|---|---|---|
| Cloud sessions (claude.ai/code, unattended runs) | **Works**: the repo's `.claude/skills`, `.claude/agents` and the hooks in `.claude/settings.json` load | Not installed from the repo's settings |
| A laptop | Works | Works |
| Updates | `workflow vendor update` (or the `update-workflow` skill), reviewed in a PR | `/plugin update` |
| Skill names | `/next`, `/tdd` | `/pairnexus-workflow:next`, `/mattpocock-skills:tdd` |

Use **vendored** for any project that runs unattended. Use the plugin for attended work on projects that don't.

## Vendored

From a checkout of this repo and of `mattpocock/skills` at the commit this kit pins (`.claude-plugin/marketplace.json`):

```bash
git clone https://github.com/mattpocock/skills /tmp/mattpocock-skills
git -C /tmp/mattpocock-skills checkout <pinned sha>
python3 scripts/workflow.py vendor install --project /path/to/project --mattpocock /tmp/mattpocock-skills
```

Then commit `.claude/` on a branch and open a PR. `workflow vendor verify` (also run in the project's CI if you like) checks the copy against `.claude/workflow/lock.json`. `vendor update` replaces the files the project hasn't changed and writes `<file>.new` beside any it has, listed as conflicts. `--adopt` replaces earlier hand-vendored copies of the same files.

The hooks run `python3 .claude/workflow/bin/workflow.py`: the project needs Python 3.11+ wherever Claude Code runs. Repo hooks load in cloud sessions only when the session has a single repository.

## Plugin

The repo is private, so Claude Code clones it with your git credentials:

```bash
gh auth login && gh auth setup-git        # HTTPS through gh's credential helper
export CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1  # if you have no SSH key for GitHub
```

Then in Claude Code:

```
/plugin marketplace add medtech-group/pairnexus-workflow
/plugin install pairnexus-workflow@pairnexus
```

Installing it installs its dependency, `mattpocock-skills`, from the same marketplace, pinned. Don't also add Matt Pocock's own marketplace: two plugins named `mattpocock-skills` drop one's hooks.

## Every project, whichever mode

1. Run the `setup-workflow` skill: the profile, labels, issue templates, CODEOWNERS.
2. The owner does the one-time steps in `docs/enforcement.md`: the ruleset, the ticket sessions' environment.

## Org-wide (optional)

A claude.ai organisation Owner can enable the plugin for every member in server-managed settings (Organization settings → Claude Code → managed settings: `extraKnownMarketplaces` and `enabledPlugins`). Cloud sessions fetch these before installing plugins, so the plugin then works in cloud sessions too. It applies to every member's sessions, not one project.
