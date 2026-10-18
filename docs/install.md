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

The hooks run `python3 .claude/workflow/bin/workflow.py`: the project needs Python 3.11+ wherever Claude Code runs (with an older `python3`, or none, or one that fails, the kit can't check anything: ticket and conductor sessions are refused every tool; in an attended session pushes and merges are still asked, and refused in solo mode or in a permission mode where nobody is asked, and the session is told at its start). Repo hooks load in cloud sessions only when the session has a single repository: don't add a second repository to a conductor or ticket session.

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

Plugin mode fails the same way as vendored: its hooks run the same commands as a vendored project's, from the plugin's directory. With an older `python3`, or none, or one that fails, pushes and merges are still asked (refused in solo mode or in a permission mode where nobody is asked), not only told at the session's start. The session's start also says what is wrong. The plugin is for attended work, so without a `python3` that runs, it never refuses every tool. An older `python3` still reads the session's role as the kit does everywhere: a ticket or conductor session (`WORKFLOW_ROLE`, or a branch matching the profile's `run.ticket_branch`) is refused every tool. Use vendored mode for those. Installed for a user, the plugin's hooks run in every project; without a `python3` that runs, a push or a merge is asked there too, profile or not (refused in solo mode or where nobody is asked), as an old `python3` has done since 0.1.8.

**Checking the set-up.** `workflow doctor` runs the same in plugin mode, with the same report, from the plugin's directory: `python3 -B <the plugin's directory>/scripts/workflow.py doctor`. Its "The kit" lines check that the plugin is enabled (in your own settings or the project's), and say so as a gap when a vendored copy is on in the same project too, naming which to turn off. It changes nothing; `--json` gives the same lines for skills, and `--strict` exits non-zero on a gap or a line it couldn't check.

## Every project, whichever mode

The kit's README ("Getting started", https://github.com/medTech-group/pairnexus-workflow#getting-started) walks through it step by step, with every click. In short:

1. Run the `setup-workflow` skill, the solo set-up: it asks only what attended work needs, and writes the profile (with `ruleset = false`, solo mode, unless it reads back a ruleset that already protects the base branch), Matt Pocock's per-repo docs, labels, issue templates, the pull request template ("In plain words" at the top, from `workflow pr-template`), CODEOWNERS; in vendored mode also the kit's copy, the `workflow kit` CI job and the weekly update check.
2. The owner merges its pull request and starts working. In solo mode the kit's guard refuses changes straight to the base branch.
3. When wanted, two optional upgrades, each one request to Claude (the `upgrade-setup` skill): "Protect `main`" (the ruleset and "Allow auto-merge", read back, then a small pull request that leaves solo mode) and "Set up unattended runs" (vendored mode only: the questions only runs need, the two environments named as in the profile, and one profile pull request). The README's Steps 3 to 5 are their clicks by hand.
4. Check it: `workflow doctor` reports your computer's `python3` and Claude Code, the kit's hooks, profile and copy, on GitHub the ruleset, the merge settings and CODEOWNERS (read with `gh`, signed in), and the two cloud environments (from `--environments`, which only a cloud session can list), each line with its fix (`docs/enforcement.md` §5 has the rest of the checklist).

The profile's settings: `docs/profile.md`.

**Reading a pull request's try-it link.** Where Cloudflare Workers Builds builds a preview of each pull request, `workflow preview` says whether the link is ready for the head commit: `built` with its URL, `building`, `failed`, or `none`. It changes nothing and posts nothing:

```bash
python3 -B .claude/workflow/bin/workflow.py preview --fetch 12 --json
python3 -B .claude/workflow/bin/workflow.py preview --comments comments.json --checks check-runs.json --sha <head SHA> --json
```

`--fetch` reads the pull request's comments, its head commit's check runs and its head through `gh api`; a file given wins. The JSON (`state`, `url`, `commit`) is what `workflow merge-check --preview F` takes. The state comes from the `Workers Builds: <worker>` check on the head commit, and the link from the Cloudflare bot's comment, only when its row for the head commit says the deployment succeeded; a link for an older commit is `building`.

## A copy of the starter

A project made from the starter template (`workflow version --starter` names it) arrives with the kit set up, so it needs no set-up pull request. Its first session opens one small "Make this project yours" pull request instead, made with:

```bash
python3 -B .claude/workflow/bin/workflow.py adopt --owner LOGIN --repo OWNER/NAME --name "My notes"
```

It rewrites only the template's names, line by line, keeping comments and formatting: the profile's `project.owner`, `project.name` and `project.repo`; the old owner in CODEOWNERS, on every line; `wrangler.toml`'s top-level `name` and `package.json`'s `name` (the name in lower case with dashes, `my-notes`); and the README's title. It prints what it changed. A file that isn't there is skipped with a note, never created. A second run changes nothing and says the project is already yours. A `--repo` that isn't `owner/name`, or a name with no ASCII letters or digits (accents are dropped: `Café` gives `cafe`), is refused with nothing written.

## Org-wide (optional)

A claude.ai organisation Owner can enable the plugin for every member in server-managed settings (Organization settings → Claude Code → managed settings: `extraKnownMarketplaces` and `enabledPlugins`). Cloud sessions fetch these before installing plugins, so the plugin then works in cloud sessions too. It applies to every member's sessions, not one project.
