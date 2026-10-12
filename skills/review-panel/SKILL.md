---
name: review-panel
description: Review a diff or pull request with independent agents in parallel - Standards, Spec, Correctness (with a security review where it applies) and, for UI, API or CLI changes, an explorer that uses the change from outside. Use on any branch or PR, inside build-ticket or alone.
---

# The review panel

Independent reviewers read the change fresh, each in its own context and in parallel. They report; they change no code. You verify each finding and fix the real ones.

## 1. Gather the inputs, outside the repo

Make a scratch directory outside the repo, for example `/tmp/review-<ticket>-r<round>/`. Write into it:

- `diff.patch`: `git diff <base>...HEAD`. The base is the profile's `project.base_branch`, as `origin/<base>` after a `git fetch`.
- `ticket.md`: the ticket's body and comments, its spec (the issue under "Parent") and the issues they link.
- `rules.md`: the project's rules, copied from each document in the profile's `project.rules` (safety rules, wording), plus `profile.md`'s sensitive-data and secrets sections.
- `previous.md`, from round 2: the earlier findings and what was done about each.

The reviewers read these files. The Correctness reviewer can't run git or reach GitHub.

## 2. Start the reviewers (one message, all at once)

**Standards and Spec.** Load Matt Pocock's `code-review` skill with the Skill tool (`code-review`, or `mattpocock-skills:code-review` as a plugin). Build its two sub-agent prompts as its own steps say, with the base above as the fixed point and `ticket.md` as the spec, so it never needs to ask. Start both with the Agent tool.

**Correctness.** The `correctness-reviewer` agent (`pairnexus-workflow:correctness-reviewer` as a plugin). Give it:
- the scratch directory's path;
- the list of changed files, to read in full in the repo;
- the round number.

For an auth, upload, payment or API change, also run the `security-review` skill on the branch.

**Explorer.** The `ui-explorer` agent, when the profile's `ui.explorer` isn't `none` and the change touches a screen, an endpoint or a command. Give it:
- the profile's `[ui]` settings;
- `ticket.md`;
- the screens, endpoints or commands the change touches;
- the scratch directory for its own files.

Tell the Correctness reviewer and the explorer to try risky commands (pushes, `gh` writes, guard experiments) only in a throwaway copy whose `origin` is a local bare repository, and to write test inputs with file tools rather than shell heredocs.

Give each reviewer the round number. From round 2, give each `previous.md`, so it checks the fixes and doesn't repeat itself.

## 3. After each round

1. Check each finding against the code. A reviewer can be wrong.
2. Fix every real one, with a test for each bug.
3. Record each that isn't a problem, with the reason.
4. Run `git status`: it must show nothing a reviewer made. Discard anything stray and say so.
5. Rerun the typecheck and the affected tests.

## 4. When to stop

Repeat on the new diff until a round finds nothing to fix, at most the profile's `run.review_rounds`.

- Anything still open after the last round goes to the owner in the PR body, never silently.
- Any commit after the last round gets a Correctness pass on just those commits before merging.

## 5. The findings table (for the PR body)

| # | Round | Reviewer | Finding | Outcome |
|---|---|---|---|---|
| 1 | 1 | Correctness | A not-planned blocker reads as done | Fixed in abc1234, test `test_blockers_not_planned` |
| 2 | 1 | Spec | No `Area:` on the new tickets | Not a problem: the spec makes areas optional for one-off tickets |
