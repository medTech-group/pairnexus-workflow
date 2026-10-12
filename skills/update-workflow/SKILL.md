---
name: update-workflow
description: Update a project's vendored copy of the pairnexus workflow kit (and its Matt Pocock skills) to a newer release, keeping the project's own edits, through a reviewed pull request.
disable-model-invocation: true
---

# Update the vendored kit

1. **Check where it stands:** `python3 .claude/workflow/bin/workflow.py vendor verify`. It reports:
   - the kit version;
   - files missing or changed since they were vendored;
   - whether the hooks are in place;
   - whether the plugin is also enabled.
2. **Get the new release:** a checkout of `medtech-group/pairnexus-workflow` at the release tag. Read its `CHANGELOG.md` from the current version up, and note anything that needs a profile change.
3. **Get Matt Pocock's skills** at the SHA the new release pins (`.claude-plugin/marketplace.json`).
4. **On a branch,** from the new kit's checkout:

   ```bash
   python3 scripts/workflow.py vendor update --project <project> --mattpocock <mattpocock checkout>
   ```

   It replaces every file the project hasn't changed. For a file the project has changed, it keeps the project's version and writes the kit's beside it as `<file>.new`, listed under `conflicts`.
5. **Resolve each conflict:**
   1. merge the two by hand, keeping the project's intent;
   2. delete the `.new` file;
   3. explain the merge in the PR body.
6. **Check it:**
   - `workflow profile check`;
   - `workflow vendor verify`;
   - the kit's changelog items that need profile changes.
7. **Open a PR** with the version change, the changelog's highlights and the conflicts resolved. It touches protected paths, so it is the owner's to review and merge.
