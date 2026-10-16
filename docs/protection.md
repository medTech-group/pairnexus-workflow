# Reading back the base branch's protection, and the requests to protect it

`workflow protection` says whether the base branch is protected, from JSON that a session fetched from GitHub. It also builds the requests that protect the base branch and require its checks, and lists the checks that ran (#66; see [Building the requests](#building-the-requests)). It asks GitHub nothing, sends nothing and changes nothing: it reads the files it is given and prints a report or the requests.

The rule for "protected" lives here, and these call it rather than repeat it (solo mode, #32). The first does already; the others come with their tickets:
- the "Protect `main`" upgrade (`skills/upgrade-setup`), to read back the clicks;
- set-up, to choose `ruleset = true` or `false`;
- the conductor's pre-flight, to spot protection that was removed;
- `workflow doctor` (#34), whose `--rulesets` and `--repo` files will take this command's input format.

## Running it

```bash
workflow protection --rulesets rulesets.json [--repo repo.json] [--base main] [--json]
```

- `--rulesets`: the repository's rulesets as a JSON list, each one **in full**. The list endpoint (`GET repos/<repo>/rulesets`) gives only summaries, without their rules, so fetch each ruleset by its id (`GET repos/<repo>/rulesets/<id>`) and put them in one list. Pages from `gh api --paginate --slurp` are read as one list too.
- `--repo`: the repository's settings (`GET repos/<repo>`). With it, the report adds the merge settings, and a ruleset on `~DEFAULT_BRANCH` counts when the settings' `default_branch` is the base branch. Without it (or without `default_branch` in it), such a ruleset can't be counted, so give it whenever the rulesets use `~DEFAULT_BRANCH`, as the ones the kit guides you to make do.
- `--base`: the base branch (`main` or `refs/heads/main`). Without it, the profile's `project.base_branch`; with no profile, `--base` is needed. A name git refuses for a branch (a space, `*`, `~`, `..`, a `.lock` ending and the like) is an error.
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

A ruleset **targets** the base branch when it is a branch ruleset and its ref conditions include `refs/heads/<base>`, `~ALL`, or `~DEFAULT_BRANCH` when the base branch is the default branch, and none of its excludes matches the base branch. An include pattern such as `refs/heads/ma*` doesn't count: the report says it can't tell. Excludes are matched ignoring case. An exclude pattern GitHub reads differently from this command (one with `**`, `[^`, `[!`, `\`, `{` or `}`), or one that isn't a full ref name (`main` rather than `refs/heads/main`), counts as excluding the base branch.

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

## Building the requests

Three more forms of the same command print requests for a session to send, or the checks it can offer. They send nothing: the session sends each request itself (`gh api -X <method> <path> --input <body file>`, or the GitHub MCP tools), where the guard asks or refuses as it does for any ruleset change (#17, #33). Each takes `--json`, which gives the same for skills and `workflow doctor`; the text form is for a developer to read. Wrong input exits 2 with a plain message and prints nothing, as the read-back does: a request is never built from half the data. That includes JSON's `NaN` and `Infinity`, which no request may carry, and check names that are empty, have spaces at either end, or hold a line break or a control character. Text from the input is printed with line breaks and bytes that aren't text escaped, as the read-back prints it.

### Protect

```bash
workflow protection --protect --repo repo.json [--base main] [--check NAME ...] [--json]
```

From the repository's settings (`GET repos/<repo>`: its `full_name` and `default_branch`, both needed) and the base branch (`--base`, else the profile's), two requests:

1. `POST repos/<repo>/rulesets`, the ruleset:
   - named "Protect <base> (pairnexus-workflow)", enforcement `active`, an empty bypass list;
   - on the base branch: `~DEFAULT_BRANCH` when it is the repository's default branch, else `refs/heads/<base>`;
   - rules `deletion`, `non_fast_forward` and `pull_request` (0 approvals, Code Owners review off, the other review settings off);
   - with `--check` names (each ticked check, once), a `required_status_checks` rule requiring them with "up to date" (`strict_required_status_checks_policy`) on; without names, no such rule;
   - no linear-history rule.
2. `PATCH repos/<repo>` with `allow_merge_commit` and `allow_auto_merge` true.

This is the set `docs/enforcement.md` §1 and the guided clicks describe, and it reads back as protected (with "checks not required yet" when no names were given).

### Require checks

```bash
workflow protection --require-checks ruleset.json --check NAME [--check NAME ...] [--json]
```

From one ruleset in full (`GET repos/<repo>/rulesets/<id>`) and the names, `PUT repos/<repo>/rulesets/<id>`:
- its first `required_status_checks` rule gains each name it doesn't already require, after the ones it has; none is removed or reordered, and the rule's other parameters stay. A ruleset with no such rule gains one;
- "up to date" is turned on;
- every other rule, the conditions, the bypass list, the name and the enforcement are sent as they are. Only the fields GitHub accepts on an update are sent (`name`, `target`, `enforcement`, `bypass_actors`, `conditions`, `rules`): no `id`, `source`, `node_id`, `_links` or times. A ruleset read without admin access has no `bypass_actors`, and the request then leaves it out, which keeps it as it is.

The repository is the ruleset's own `source`. An organisation's ruleset is refused: the kit adds checks only to the repository's. So is a ruleset that isn't a branch ruleset, or one whose required checks lack a `context`.

### The checks that ran

```bash
workflow protection --checks-ran check-runs.json [--statuses statuses.json] --rulesets rulesets.json --repo repo.json [--base main] [--json]
```

From the base branch's latest commit's check runs (`GET repos/<repo>/commits/<sha>/check-runs`, or its pages from `--paginate --slurp`) and statuses (`GET repos/<repo>/commits/<sha>/statuses`, its pages, or the combined `.../status`), each check's name with its result:
- **passing:** a completed check run whose conclusion is `success`, `neutral` or `skipped`, or a `success` status;
- **failing:** any other conclusion, or a `failure` or `error` status;
- **pending:** a check run not completed yet, or a `pending` status.

A name reported more than once (a re-run, or a check run and a status of the same name) appears once, with its latest result: the check run that finished last (one still running counts from when it started), or the status updated last. A report with no time counts as the oldest; at the same time, the higher id wins. Those the rulesets already require are left out: `--rulesets`, `--repo` and `--base` are read as the read-back reads them, and their required checks come back under `required`. `--repo` is needed here, so that a ruleset on `~DEFAULT_BRANCH` counts and its checks aren't offered again. A commit with no checks gives an empty list, not an error.

Every page is needed: a file holding fewer check runs (or combined statuses) than its `total_count` is an error, since a list built from one page would leave checks out. Fetch with `gh api --paginate --slurp`, or `per_page=100`. The checks are listed by name.

**Never offered:** check runs from the `cloudflare-workers-and-pages` app (`Workers Builds: <worker>`, the try-it link's build, #41). The kit never makes the try-it link a required check (#18). A check of a similar name from another app is listed.

`--json` gives:

```json
{"checks": [{"name": "lint", "result": "failing"}, {"name": "tests (3.11)", "result": "passing"}], "required": ["build"]}
```

