---
name: update-workflow
description: Update a project's vendored copy of the pairnexus workflow kit (and its Matt Pocock skills) to a newer release, keeping the project's own edits, through a reviewed pull request.
disable-model-invocation: true
---

# Update the vendored kit

This runs from a checkout of the new kit release (`KIT`), with `WF` as `python3 $KIT/scripts/workflow.py`.

**The kit's home** (`<kit repo>` below) is what `python3 .claude/workflow/bin/workflow.py version --repo` prints: the repository the project's copy came from, a fork's own. A copy older than 0.1.7 can't say: there it is the upstream, `medTech-group/pairnexus-workflow` (or your fork, if the project was set up from one). **Moving a project to a fork:** `<kit repo>` is the fork, whatever the project's copy prints; the update brings the fork's `KIT_REPO`, which the project follows from then on.

**The release, never `main` between releases.** The latest is what `python3 .claude/workflow/bin/workflow.py version --fresh` names. A project on a kit older than 0.1.5 has no `version` command: there, `git ls-remote --tags --refs https://github.com/<kit repo> 'v*' | sed 's#.*/v##' | sort -V | tail -1`. Clone that release outside the project, so nothing of it is committed by mistake:

```bash
KIT=$(mktemp -d)/pairnexus-workflow && git clone --depth 1 --branch v<version> https://github.com/<kit repo> "$KIT"
```

Then follow **this release's** copy of this skill, `$KIT/skills/update-workflow/SKILL.md`, not the project's older one.

1. **Where it stands.** In the project, run `python3 .claude/workflow/bin/workflow.py vendor verify`. It reports:
   - the kit's version;
   - files missing or changed since they were vendored;
   - whether the hooks are in place;
   - whether the plugin is also enabled.
2. **The new release.** Read `$KIT/CHANGELOG.md` from the current version up. Note anything that needs a profile change, and any "For projects updating" step (a change to the project's `CLAUDE.md`, say).
3. **Matt Pocock's skills.** Check them out at the SHA the new release pins, in `$KIT/.claude-plugin/marketplace.json`.
4. **The update.** On a branch in the project:

   ```bash
   WF vendor update --project <project> --mattpocock <that checkout>
   ```

   `--mattpocock` is required whenever the lock records Matt Pocock's skills. Without it they would be dropped, and the update refuses.

   For each file:
   - **unchanged in the project:** replaced with the kit's new version;
   - **changed in the project, unchanged in the kit:** the project's edit is kept, and listed under `kept`;
   - **changed in both:** the project's version is kept, the kit's is written beside it as `<file>.new`, and it is listed under `conflicts`;
   - **dropped by the kit but changed in the project:** kept, and recorded as orphaned.

   List the `kept` files in the PR body, so the owner sees which of the project's own edits carry on.
5. **Each conflict:**
   1. merge the two versions by hand, keeping the project's intent;
   2. run `WF vendor resolve <file>`, which records the merged file in the lock and deletes the `.new` file;
   3. explain the merge in the PR body.
6. **Check it.**
   - Run `WF profile check` and `WF vendor verify --strict`.
   - Make the changelog's profile changes, and its "For projects updating" steps.
   - **The weekly update check:** if `.github/workflows/workflow-kit-update.yml` is missing, copy it from `$KIT/templates/github/workflow-kit-update.yml`. It opens an issue when a newer release is out.
   - **The files set-up copied once,** which `vendor update` doesn't track: compare each with the new release's template and bring over what changed, keeping the project's own edits (the base branch name in `workflow-kit.yml`, for instance). Show each change in the PR body.
     - `.github/workflows/workflow-kit.yml` with `$KIT/templates/github/workflow-kit.yml`;
     - `.github/workflows/workflow-kit-update.yml` with `$KIT/templates/github/workflow-kit-update.yml`;
     - `docs/agents/issue-tracker.md` with `$KIT/templates/issue-tracker.md`;
     - `.github/ISSUE_TEMPLATE/build-ticket.md` and `owner-task.md` with `$KIT/templates/github/ISSUE_TEMPLATE/`.
7. **The project's experience default.** When `WF profile check` shows `"experience": null` (the profile has no `experience`), ask once, with `AskUserQuestion`: "How much do the people working on this project know, as its default?" Each person's own answer still wins over it. When they gave their own level earlier in this session, put that level first, "(Recommended)", and say this one is the project's default, not theirs again. The options:
   - *new to building*: "Explain the words and go one step at a time.";
   - *developer*: "Keep it short: git, pull requests and CI are familiar.";
   - *Leave it unset*: "The guided start asks each person instead."

   Write the answer in the profile's `[project]` table, on a line of its own: `experience = "new"` or `experience = "developer"`, in place of a commented `# experience = …` line if there is one. Run `WF profile check` again. It goes in the same pull request as the update, so it costs no pull request of its own. A skipped question or *Leave it unset* writes nothing: this update doesn't ask again, and each later update asks once while the profile has no `experience`. The level changes only how the kit words things and paces itself in a conversation: what it writes on GitHub (this PR's body included) is the same for every level, plain summary first.
8. **The PR,** titled "Update the workflow kit to <version>" (so the guided start sees it's open and doesn't offer a second). It gives the version change, the changelog's highlights, the experience default written (if any) and the conflicts resolved, and closes the open "Workflow kit update:" issue, if any (`Closes #<n>`). It touches protected paths, so it's the owner's to review and merge.
