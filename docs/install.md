# Installing the kit

Two modes. Pick one per project: `setup-workflow` refuses both at once (the skills would be duplicated and the hooks would run twice).

| | Vendored (committed copy) | Plugin |
|---|---|---|
| Cloud sessions (claude.ai/code, unattended runs) | **Works**: the repo's `.claude/skills`, `.claude/agents` and the hooks in `.claude/settings.json` load | Not installed from the repo's settings |
| A laptop | Works | Works |
| Updates | `workflow vendor update` (or the `update-workflow` skill), reviewed in a PR | `/plugin update` |
| Skill names | `/next`, `/tdd` | `/pairnexus-workflow:next`, `/mattpocock-skills:tdd` |

Use **vendored** for any project that runs unattended. Use the plugin for attended work on projects that don't. The one-mode check reads the project's `settings.json` and `settings.local.json`; if the plugin is enabled in your user settings or org-wide, don't also vendor it.

## Vendored

Run the `setup-workflow` skill from a checkout of this repo: open Claude Code in the project and ask it to follow `<kit checkout>/skills/setup-workflow/SKILL.md`. It writes the profile and vendors the kit in the same pull request. Underneath, the vendoring is:

```bash
git clone https://github.com/mattpocock/skills /tmp/mattpocock-skills
git -C /tmp/mattpocock-skills checkout <the sha pinned in .claude-plugin/marketplace.json>
python3 <kit>/scripts/workflow.py vendor install --project /path/to/project --mattpocock /tmp/mattpocock-skills
```

- `vendor verify` checks the copy against `.claude/workflow/lock.json`; setup adds it to the project's CI as a required check (`--strict`).
- `vendor update` replaces the files the project hasn't changed and writes `<file>.new` beside any it has, listed as conflicts; `vendor resolve <file>` records a hand-merged one.
- `--adopt` replaces files that already exist and aren't the kit's (an earlier hand-vendored copy); it lists every one. Rename the project's own skills of the same name first.
- Install checks every file before writing any, so a refused install changes nothing.

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

To suggest it to everyone working on a project, put this in the project's `.claude/settings.json` (each person still installs it once; cloud sessions don't):

```json
{
  "extraKnownMarketplaces": {"pairnexus": {"source": {"source": "github", "repo": "medtech-group/pairnexus-workflow"}}},
  "enabledPlugins": {"pairnexus-workflow@pairnexus": true}
}
```

Installing it installs its dependency, `mattpocock-skills`, from the same marketplace, pinned. Don't also add Matt Pocock's own marketplace: two plugins named `mattpocock-skills` drop one's hooks.

## Every project, whichever mode

1. Run the `setup-workflow` skill: the profile, the kit, Matt Pocock's per-repo docs, labels, issue templates, CODEOWNERS.
2. The owner does the one-time steps in `docs/enforcement.md`: the ruleset (active), the two environments.

## Org-wide (optional)

A claude.ai organisation Owner can enable the plugin for every member in server-managed settings (Organization settings → Claude Code → managed settings: `extraKnownMarketplaces` and `enabledPlugins`). Cloud sessions fetch these before installing plugins, so the plugin then works in cloud sessions too. It applies to every member's sessions, not one project.
