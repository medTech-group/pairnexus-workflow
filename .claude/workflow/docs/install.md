# Installing the kit

Two modes. Pick one per project: `workflow vendor install` and `vendor verify` refuse a project whose `.claude/settings.json` or `settings.local.json` also enables the plugin (the skills would be duplicated and the hooks would run twice).

| | Vendored (committed copy) | Plugin |
|---|---|---|
| Cloud sessions (claude.ai/code, unattended runs) | **Works**: the repo's `.claude/skills`, `.claude/agents` and the hooks in `.claude/settings.json` load | Not installed from the repo's settings (only when enabled org-wide, below) |
| A laptop | Works | Works |
| Updates | The `update-workflow` skill: a PR the owner merges | `/plugin update pairnexus-workflow@pairnexus` |
| Python 3.11+ | Wherever Claude Code runs | Wherever Claude Code runs |
| `workflow kit` CI check, weekly update check | Yes | No |
| Skill names | `/next`, `/tdd` | `/pairnexus-workflow:next`, `/mattpocock-skills:tdd` |

Use **vendored** for any project that runs unattended. Use the plugin for attended work on projects that don't. The one-mode check reads the project's `settings.json` and `settings.local.json`; if the plugin is enabled in your user settings or org-wide, don't also vendor it.

## Vendored

Run the `setup-workflow` skill from a checkout of this repo at its latest release's tag: open Claude Code in the project and ask it to follow `<kit checkout>/skills/setup-workflow/SKILL.md`. It writes the profile and vendors the kit in the same pull request. Underneath, the vendoring is:

```bash
git clone https://github.com/mattpocock/skills /tmp/mattpocock-skills
git -C /tmp/mattpocock-skills checkout <the sha pinned in .claude-plugin/marketplace.json>
python3 <kit>/scripts/workflow.py vendor install --project /path/to/project --mattpocock /tmp/mattpocock-skills
```

- `vendor verify` checks the copy against `.claude/workflow/lock.json`; setup adds it to the project's CI as a required check (`--strict`).
- `vendor update` (run by the `update-workflow` skill, with `--kit <the new release's checkout>`) replaces the files the project hasn't changed; keeps the project's edit where the kit didn't change the file (listed as `kept`); and where both changed it, keeps the project's and writes the kit's beside it as `<file>.new`, listed as a conflict. `vendor resolve <file>` records a hand-merged one.
- `--adopt` replaces files that already exist and aren't the kit's (an earlier hand-vendored copy); it lists every one. Rename the project's own skills of the same name first.
- Install checks every file before writing any, so a refused install changes nothing.

The hooks run `python3 .claude/workflow/bin/workflow.py`: the project needs Python 3.11+ wherever Claude Code runs (with an older `python3`, or none, the kit can't check anything, so ticket and conductor sessions are refused every tool and an attended session is told at its start). Repo hooks load in cloud sessions only when the session has a single repository: don't add a second repository to a conductor or ticket session.

## Plugin

The repo is public; if Claude Code can't clone it, give git your credentials:

```bash
gh auth login && gh auth setup-git        # HTTPS through gh's credential helper
export CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1  # if you have no SSH key for GitHub
```

Then in Claude Code (from a fork, the fork's `owner/repo` in place of the one below):

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

The plugin's commands carry its name: `/pairnexus-workflow:start`, `/pairnexus-workflow:next`, `/mattpocock-skills:to-spec`. The guided start comes up by itself at the first message only in a project with a profile; before set-up, type `/pairnexus-workflow:start` or `/pairnexus-workflow:setup-workflow`. The plugin follows the kit's `main`, not only its releases.

## Every project, whichever mode

The kit's README ("Getting started", https://github.com/medTech-group/pairnexus-workflow#getting-started) walks through it step by step, with every click. In short:

1. Run the `setup-workflow` skill: the profile, Matt Pocock's per-repo docs, labels, issue templates, CODEOWNERS; in vendored mode also the kit's copy, the `workflow kit` CI job and the weekly update check.
2. The owner merges its pull request, then does the one-time steps (`docs/enforcement.md`): the ruleset (active), "Allow auto-merge", and, for unattended runs (vendored mode only), the two environments, named as in the profile.
3. Check it (`docs/enforcement.md` §5).

The profile's settings: `docs/profile.md`.

## Org-wide (optional)

A claude.ai organisation Owner can enable the plugin for every member in server-managed settings (Organization settings → Claude Code → managed settings: `extraKnownMarketplaces` and `enabledPlugins`). Cloud sessions fetch these before installing plugins, so the plugin then works in cloud sessions too. It applies to every member's sessions, not one project.
