---
name: review-panel
description: Review a diff or pull request with independent agents in parallel - Standards, Spec, Correctness (with a security review where it applies) and, for UI changes, an explorer that runs the app and uses every input. Use on any branch or PR, inside build-ticket or alone.
---

# The review panel

Independent reviewers, each reading the diff and the ticket fresh in its own context, in parallel. Reviewers change no code: they report. You verify and fix.

## Inputs

- **The diff:** `git diff <base>...HEAD` (the profile's `project.base_branch`), and the changed files in full where needed.
- **The ticket and its spec** (the issue, its parent, what it links).
- **The project's rules:** what `profile.md` points to (safety rules, data classification, wording), and `CLAUDE.md`.

## The reviewers (one message, all at once)

1. **Standards** and **Spec**: the two sub-agents of the `code-review` skill (Matt Pocock's). Standards checks the repo's documented coding rules; Spec checks the diff against what the ticket and spec asked, criterion by criterion.
2. **Correctness**: the `correctness-reviewer` agent, with the diff, the ticket and the rules' locations. It hunts wrong behaviour, unhandled edge cases, missing or weak tests, race conditions, and every safety rule in the project's rules. For an auth, upload, payment or API change, also run the `security-review` skill on the branch.
3. **UI explorer**, when the change adds or changes a screen (the profile's `ui.explorer` is `browser`), or exercises an API or CLI the change adds (`api`, `cli`): the `ui-explorer` agent, with the start commands, sizes and notes from the profile's `[ui]` and the screens or endpoints the ticket touches.

Give each the round number and, from round 2, the previous findings and what was done about them, so it checks the fixes and doesn't repeat itself.

## After each round

- Check each finding against the code. A reviewer can be wrong.
- Fix every real one, with a test for each bug.
- Record each that isn't a problem, with the reason.
- `git status` must be clean of anything a reviewer wrote (they shouldn't write; if one did, discard it and say so).
- Rerun the typecheck and the affected tests.

Repeat on the new diff until a round finds nothing to fix, at most the profile's `run.review_rounds`. Anything still open after the last round goes to the owner in the PR body, not silently. Any commit after the last round gets a Correctness pass on just those commits before merging.

## The findings table (for the PR body)

| # | Round | Reviewer | Finding | Outcome |
|---|---|---|---|---|
| 1 | 1 | Correctness | `ready` treats a not-planned blocker as done | Fixed in abc1234, test `test_blockers_not_planned` |
| 2 | 1 | Spec | No `Area:` on the new tickets | Not a problem: the spec says areas are optional for one-off tickets |
