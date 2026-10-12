# Spike: what has been verified, and what hasn't

The kit relies on Claude Code and GitHub behaving as their docs say. This file records what has actually been tried, so nothing rests on an assumption by accident. Update it whenever one of these is checked again.

| # | Assumption | Status | How it was checked |
|---|---|---|---|
| 1 | Repo hooks in `.claude/settings.json` run in a headless session and the guard's `deny` stops the tool | **Verified** 12 Oct 2026 | `claude -p` (2.1.296) in a copy of pair-drop with the kit vendored and `WORKFLOW_ROLE=ticket`, asked to `git push origin main` with `--allowedTools "Bash(git push:*)"`: the guard denied it and the remote got no `main` |
| 2 | The Stop gate makes a ticket session add its status line | **Verified** 12 Oct 2026 | Same session: it ended its turn without one, was asked, and added `WORKFLOW-STATUS` |
| 3 | In an attended session the guard's `ask` reaches the person (and blocks in `-p`) | **Verified** 12 Oct 2026 | Same copy without `WORKFLOW_ROLE`: the push was held for approval |
| 4 | Repo hooks run in a claude.ai/code cloud session (single repo) and block a ticket session's push to `main` and `mcp__github__merge_pull_request` misuse | Not yet | The sandbox e2e: a ticket session in `pairnexus-workflow-sandbox` |
| 5 | A ruleset on a private repo is enforced on medtech-group's plan | Partly | `pairnexus-workflow` has a ruleset; it was still `disabled` on 12 Oct. Check once it's active: a direct push to `main` is refused |
| 6 | The plugin's `dependencies: ["mattpocock-skills"]` installs Matt Pocock's skills from this marketplace | Not yet | `/plugin marketplace add medtech-group/pairnexus-workflow`, install, then check `/mattpocock-skills:tdd` exists |
| 7 | A cloud session's setup script can install the plugin from the private repo | Not yet, and not needed | Vendored mode is what cloud sessions use |
| 8 | `create_session` with `permission_mode` and `environment_id` starts a ticket session that runs unattended without prompts | Not yet | The sandbox e2e |
| 9 | `send_later` check-ins keep a conductor alive across hours, and summaries don't lose the run (state from the issue) | Partly | The pair-drop weekend run (9–12 Oct) used `send_later` every 20 minutes for three days; state then lived in a scratchpad, now in the issue |
| 10 | Claude Code's built-in `gh api --paginate` returns one merged array | **Verified** 12 Oct 2026 | `ready --fetch` against pair-drop (the review); `--slurp` with a fallback either way |
