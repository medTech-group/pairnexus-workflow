---
name: update-workflow
description: Update a project's vendored copy of the pairnexus workflow kit (and its Matt Pocock skills) to a newer release, keeping the project's own edits, through a reviewed pull request.
disable-model-invocation: true
---

# Update the vendored kit

This runs from a checkout of the new kit release (`KIT`), with `WF` as `python3 $KIT/scripts/workflow.py`.

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
   - **changed in the project:** kept, with the kit's version written beside it as `<file>.new` and listed under `conflicts`;
   - **dropped by the kit but changed in the project:** kept, and recorded as orphaned.
5. **Each conflict:**
   1. merge the two versions by hand, keeping the project's intent;
   2. run `WF vendor resolve <file>`, which records the merged file in the lock and deletes the `.new` file;
   3. explain the merge in the PR body.
6. **Check it.**
   - Run `WF profile check` and `WF vendor verify --strict`.
   - Make the changelog's profile changes, and its "For projects updating" steps.
7. **The PR.** It gives the version change, the changelog's highlights and the conflicts resolved. It touches protected paths, so it's the owner's to review and merge.
