# Reading back the base branch's protection

`workflow protection` says whether the base branch is protected, from JSON that a session fetched from GitHub. It asks GitHub nothing and changes nothing: it reads the files it is given and prints a report.

The rule for "protected" lives here. These will call it rather than repeat it (solo mode, #32); none does yet:
- the "Protect `main`" upgrade, to read back the clicks;
- set-up, to choose `ruleset = true` or `false`;
- the conductor's pre-flight, to spot protection that was removed;
- `workflow doctor` (#34), whose `--rulesets` and `--repo` files will take this command's input format.

## Running it

```bash
workflow protection --rulesets rulesets.json [--repo repo.json] [--base main] [--json]
```

- `--rulesets`: the repository's rulesets as a JSON list, each one **in full**. The list endpoint (`GET repos/<repo>/rulesets`) gives only summaries, without their rules, so fetch each ruleset by its id (`GET repos/<repo>/rulesets/<id>`) and put them in one list. Pages from `gh api --paginate --slurp` are read as one list too.
- `--repo`: the repository's settings (`GET repos/<repo>`). With it, the report adds the merge settings, and a ruleset on `~DEFAULT_BRANCH` counts when the settings' `default_branch` is the base branch. Without it (or without `default_branch` in it), such a ruleset can't be counted, so give it whenever the rulesets use `~DEFAULT_BRANCH`, as the ones the kit guides you to make do.
- `--base`: the base branch (`main` or `refs/heads/main`). Without it, the profile's `project.base_branch`; with no profile, `--base` is needed. A name no branch can have (a space, `*`, `~` and the like) is an error.
- `--json`: the same report for skills.
- `-` for a file reads it from standard input (for one of the two files only).

With `gh`:

```bash
set -eo pipefail
gh api --paginate "repos/<repo>/rulesets?includes_parents=true" --jq '.[].id' \
  | while read id; do gh api "repos/<repo>/rulesets/$id" || exit 1; done | jq -s . > rulesets.json
gh api repos/<repo> > repo.json
```

With the GitHub MCP tools, fetch the same and write the files. Fetch organisation rulesets through the repository too (`repos/<repo>/rulesets/<id>`), not `orgs/<org>/rulesets`: the repository's list holds only those that apply to it, and this command doesn't read a ruleset's repository conditions.

It exits 0 with a report, protected or not. When an input is wrong (not JSON, not the shape GitHub returns, a ruleset that isn't in full) it exits 2 with a plain message on standard error and prints nothing on standard output, `--json` or not. A wrong input is never read as protected.

## What counts as protected

The base branch is protected when the active rulesets that target it, taken together:
- restrict deletions (a `deletion` rule);
- block force pushes (a `non_fast_forward` rule);
- require a pull request (a `pull_request` rule);
- and none of them has a bypass list.

A ruleset **targets** the base branch when it is a branch ruleset and its ref conditions include `refs/heads/<base>`, `~ALL`, or `~DEFAULT_BRANCH` when the base branch is the default branch, and none of its excludes matches the base branch. An include pattern such as `refs/heads/ma*` doesn't count. Excludes are matched ignoring case. An exclude pattern GitHub reads differently from this command (one with `**`, `[^`, `[!`, `\`, `{` or `}`), or one that isn't a full ref name (`main` rather than `refs/heads/main`), counts as excluding the base branch.

Each thing missing is its own line, in plain words:
- no rulesets;
- a ruleset not active (disabled), or evaluate only (it reports but doesn't block);
- a ruleset that doesn't target the base branch, or can't be told to (`~DEFAULT_BRANCH` without the settings); these, and rulesets not active, are listed only when the branch isn't protected;
- a bypass list, or a bypass list that can't be read (GitHub shows it only to admins);
- deletions allowed, force pushes allowed, pull requests not required.

Text from the input (ruleset names, check names, patterns) is printed as JSON strings, with line breaks escaped, so it can't make a line of its own.

**Checks:** when no active ruleset on the base branch requires status checks, the report says "checks not required yet". The branch can still read as protected: the checks are added once CI has run and their names are known.

**Merge settings** (with `--repo`): merge commits (`allow_merge_commit`) and auto-merge (`allow_auto_merge`), each allowed, not allowed or unknown (not in the file). Each one that is off or unknown is also its own line. They are reported beside the verdict, not part of it.

## The report

```
main is protected.
Checks not required yet: no active ruleset on main requires status checks.
Merge settings: merge commits allowed, auto-merge allowed.
```

```
main is not protected:
- ruleset "Protect main" is evaluate only: it reports but doesn't block
- deletions allowed: no active ruleset on main restricts deletions
- force pushes allowed: no active ruleset on main blocks force pushes
- pull requests not required: no active ruleset on main requires a pull request
Checks not required yet: no active ruleset on main requires status checks.
```

`--json` gives:

```json
{
  "base_branch": "main",
  "protected": false,
  "missing": ["..."],
  "checks": {"required": [], "note": "checks not required yet"},
  "merge": {"merge_commits": true, "auto_merge": false, "missing": ["auto-merge not allowed: turn on allow_auto_merge"]}
}
```

`checks.note` is `null` when checks are required, and `merge` is `null` without `--repo`. A merge setting not in the file is `null`.
