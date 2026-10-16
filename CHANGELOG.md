# Changelog

## Unreleased

**The pull request template set-up installs: "In plain words" for every pull request** (#83, part of judging a PR without reading code, #39).

- **The template,** `templates/github/pull_request_template.md`, has `build-ticket`'s headings (#82): `## In plain words`, then `**What changes for you**`, `**How to try it**` and `**What could go wrong**`, each with a one-line prompt under it in an HTML comment, so an unedited pull request shows only the headings. A test reads the headings from both files, so the two can't drift.
- **`workflow pr-template [--existing FILE]`** prints the file to write and changes nothing. With no `--existing`, it prints the kit's template. With one, it prints the headings above the project's template, whose content is kept whole, in its own line endings. A file that already starts with `## In plain words` (after any blank lines and HTML comments) comes back unchanged, with a note, so running it twice adds nothing. An empty file gets the kit's template; one that isn't UTF-8 text, or an empty `--existing`, is refused in words (exit 1). A `.github/PULL_REQUEST_TEMPLATE/` folder is left alone: GitHub picks those through a query string, so the command exits 3 and says to add the headings by hand.
- **`setup-workflow`** gains step 11, beside the issue templates. It prints the template to `.workflow/pr-template.md` and moves it to `.github/pull_request_template.md`, or back over the project's own template, only when the command exits 0. The set-up pull request says it was added, or what was added at the top of the existing one.
- **`update-workflow`** adds it once to a project set up before this: in the first update to this release or a later one, shown in the update PR. One that has the headings already is left as it is, and later updates leave the file to the owner. It isn't a protected path, so the owner changes it freely. The starter (#40) is to take the file from `workflow pr-template` when it is built.
- Docs: `docs/install.md`'s list of what set-up writes, and the README's. Tests: `tests/test_pr_template.py`.
- **For projects updating:** the update adds `.github/pull_request_template.md`, or the "In plain words" headings at the top of yours; a folder of templates gets them by hand.

**"In plain words" at the top of every pull request `build-ticket` opens** (#82, part of judging a PR without reading code, #39).

- **`build-ticket`'s PR body** (step 4) now opens with `## In plain words`, then `**What changes for you**` (one to three sentences about what a user notices), `**How to try it**` (the try-it link and things to click; else where the link will appear, when the project has preview links; else what to check another way, or "Nothing to try: this change is behind the scenes"; for now always the last, as the kit doesn't read preview links yet) and `**What could go wrong**` (easy or hard to undo, and what it could affect). Each heading is on its own line, its text below it. The section is the same for everyone, never worded by experience, and when the `pr` skill is loaded too its sections go below. Below it the body is unchanged: `Closes #<n>`, what was built, how it was tested, the findings table, "Decisions for the owner" and the by-hand checks.
- Docs: `docs/flow.md` §3's pull-request step names "In plain words" first; `docs/glossary.md`'s "pull request" entry says each one the kit opens starts with it (a few words trimmed elsewhere to keep the file under 6,000 characters; no entry lost). Tests: `tests/test_in_plain_words.py`.
- **For projects updating:** nothing to do; pull requests `build-ticket` opens after the next kit update start with the section.

**Review records: each review round leaves one on the pull request** (#79, part of judging a PR without reading code, #39).

- **`workflow review-record`** prints the comment a round or a later Correctness pass posts: a line for people ("Review round 2 on `3f2a9c0`: clean. Reviewers: Standards, Spec, Correctness."), one machine-readable line (`<!-- workflow:review kind=round round=2 commit=<full sha> reviewers=standards,spec,correctness result=clean -->`) and the agents' marker. Flags: `--kind round|pass`, `--round`, `--commit` (the full SHA), `--reviewers` (from `standards`, `spec`, `correctness`, `security`, `explorer`; a `pass` is `correctness` alone), `--clean` or `--not-clean`. A missing field, a short or non-hex SHA, an unknown reviewer or a pass with other reviewers is refused in plain words, with a non-zero exit.
- **The reader** sits in the same module (`scripts/workflow/reviews.py`: `records_in(text)` for one comment, `read(comments)` for a pull request's comments, with who posted each), so the writer and whatever reads records (a `workflow merge-check` is planned) apply the same rules. Only a record line of its own counts, at the start of the line and before any code fence (```` ``` ```` or `~~~`) in the comment: one quoted in a sentence, a list, a quote or a code block, or a malformed one, is skipped, never a crash. When in doubt the reader leaves a line out; the writer's comment has no fence. For `workflow comments` too: a comment id past 20 digits reads as no number, and JSON with a number past Python's digit limit or nested too deeply is refused in words, not with a traceback.
- **The `review-panel` skill** posts a record after every round, whatever it found, and after each later Correctness pass, in attended and unattended sessions alike. `build-ticket` posts the records of the rounds run before its pull request opened, once it does; its findings table stays in the PR body.
- Docs: `docs/flow.md` §3; the glossary's "Review panel". Tests: `tests/test_review_record.py`.
- **For projects updating:** nothing to do.

**"Require these checks": failing tests stop merges once CI has run** (#68, part of the automated GitHub set-up, #38).

- **A third path in the `upgrade-setup` skill,** offer name `require_checks`, offered only through `workflow doctor`'s offer (which `check-setup` and the conductor's pre-flight show) or when you ask. It shows the checks that ran on the base branch's latest commit with their results (already-required ones left out), passing ones ticked by default and failing or pending ones not, saying why; *new to building* gets one plain sentence, a developer the names and "up to date". **Not now** changes nothing.
- **On your own computer, with `gh` signed in as the repository's admin,** it adds the ticked checks to the ruleset protecting the base branch (the kit's own, else the only one) with `workflow protection --require-checks`'s `PUT` sent by `gh api`, after one confirmation that says Claude Code's prompt is expected. Everywhere else, and when several rulesets protect the branch and none is the kit's: the clicks, one screen at a time, with the exact names and "Require branches to be up to date". Not an admin: a ready message for the owner. Either way it reads back with `workflow protection`.
- **Then the profile:** a small pull request adding every name the ruleset now requires to `ci.required_checks` (and `ci.none = false` when it was set), with `<!-- workflow:required-checks -->` in its body; none when the profile already lists them. Checks are only ever added, never removed. In solo mode it waits for the pull request that leaves solo mode.
- **The guard is unchanged.** Its existing decisions on the `PUT`: asked in an attended session with `ruleset = true` or no `ruleset` setting; refused in solo mode, in `bypassPermissions` and `dontAsk` (naming the mode), and in ticket and conductor sessions; the reads allowed.
- Docs: the README's "Protect `main`", `docs/enforcement.md` §1. Tests: `tests/test_protect_main_gh.py` (the guard), `tests/test_upgrade_setup.py` (the wording).
- **For projects updating:** nothing to do.

**The guard sees `Monitor` and `PowerShell`** (#55, part of guard robustness, #33).

- **The guard's matcher adds `Monitor` and `PowerShell`**, in a vendored project's settings and in the plugin's hooks file. Before, neither reached the guard, even in a ticket session.
- **`Monitor`:** its `command` is checked exactly as a Bash command, in every role (a ticket session's `gh run watch` still passes; a push or a deploy through it is refused or asked as through Bash). A WebSocket watch (`ws`, no command) is allowed.
- **`PowerShell`:** the guard can't read it and never parses it. Ticket and conductor sessions are refused it ("the guard can't read PowerShell; use Bash"). In an attended session, a push or a merge in its text (matched in any case, as PowerShell runs it, a backtick line continuation joined) is asked, and refused in solo mode or where nobody is asked; anything else is left alone. The can't-decide fallbacks (`fallback.py`, `fallback.sh`) read a `Monitor` or `PowerShell` command as they read a Bash one.
- Where nobody is asked, the refusal gives the `Monitor` or `PowerShell` command itself to run by hand, never when it holds text matching a sensitive pattern. The hand command now also masks a token assigned with spaces around `=` (PowerShell's `$env:GH_TOKEN = '…'`, or `= '…'`), keeping the spacing as written; `VAR= cmd` keeps its command. A solo-mode refusal of a Bash or `Monitor` command or a GitHub MCP tool whose input matches a sensitive pattern no longer repeats it, neither in the hand command nor in what the kit saw.
- Docs: `docs/enforcement.md` §4 lists the tools the guard sees, and records the release-gate step for item 10 (#36): compare Claude Code's tools reference with that list. Tests: `tests/test_guard_monitor_powershell.py`; `tests/test_vendor_evidence.py`'s matcher assertion now includes the two tools.
- **For projects updating:** nothing to do; the next kit update writes the new matcher into `.claude/settings.json`.

**"Protect `main`" is automatic on your own computer, with `gh`** (#67, part of the automated GitHub set-up, #38).

- **The `upgrade-setup` skill makes the ruleset and the merge settings itself** when the session is local, `gh` is signed in, and the repository reads you as its admin: after one confirmation, worded by experience, it sends `workflow protection --protect`'s ruleset `POST` and merge-settings `PATCH` with `gh api`, reads them back with `workflow protection`, and opens the pull request that leaves solo mode. Claude Code asks you to approve the ruleset command, and the skill says so up front.
- **The checks that already ran** on the base branch's latest commit (`workflow protection --checks-ran`) are offered on the same screen, passing ones and those the profile lists ticked by default. Ticked names go in the ruleset and, in the same pull request, into `ci.required_checks` (never removing one), with the marker `<!-- workflow:required-checks -->` in its body.
- **Everyone else gets the guided clicks:** cloud sessions always, `gh` missing or signed out (with how to sign in), and a ruleset already on the base branch that doesn't protect it, which is read back first and never edited. Not an admin: the ready message for the owner, before anything is tried.
- **Refusals and failures:** a refusal naming a permission mode where nobody is asked is answered with "switch the permission mode and try again", never a retry. A failed step says what was done and what's left, reads back, and gives the clicks for the rest; the ruleset's request is never sent twice.
- **The guard is unchanged.** Its existing decisions on the exact commands the skill runs: the `POST` asked when someone is asked, refused in `bypassPermissions`, `dontAsk` and ticket and conductor sessions; the `PATCH` and the reads allowed, in solo mode and out.
- Docs: the README's "Protect `main`", `docs/enforcement.md` §1. Tests: `tests/test_protect_main_gh.py` (the guard), `tests/test_upgrade_setup.py` (the wording).
- **For projects updating:** nothing to do.

**No `python3`, and the plugin: the hook commands get the same fallback** (#56, part of guard robustness, #33).

- **Without a working `python3`** (missing, a stub, a shim with no version, a non-zero exit), an attended session's guard hook command still applies #53's rule: a push or a merge is asked, and refused in solo mode or in a permission mode where nobody is asked; everything else is left alone. It reads the event's raw text in the new `scripts/workflow/fallback.sh` (POSIX `sh` and `awk`, matched word by word): only a Bash command or a GitHub MCP tool's name, never a file's content. The reason says the guard isn't working and to check `python3 --version` (3.11 or newer).
- **An attended session's guard hook command always exits 0.** Before, a failing `python3`'s exit code was passed on. Ticket and conductor sessions are still refused every tool; the restore commands still pass with the kit missing.
- **The plugin's hooks file** (`hooks/hooks.json`) is now written from `vendor.plugin_hooks()`: the same commands as a vendored project's, rooted at `${CLAUDE_PLUGIN_ROOT}`, with the `python3` check, the old-Python fallback and this one. The plugin is for attended work, so without Python it never refuses every tool (an old `python3` still reads the session's role, as the CLI does), and it asks about a push or a merge in a project with no profile too, as an old `python3` has since 0.1.8. If `fallback.sh` itself is missing (a partial copy of the kit), every tool is asked, with a reason saying the kit is broken. Its session-start hook says what is wrong when `python3` is missing or failing (an old one already did).
- Docs: `docs/install.md`, `docs/enforcement.md`'s "When something is wrong", the README. Tests: `tests/test_guard_no_python.py`; `tests/test_kit_018.py`'s failing-`python3` case now expects exit 0 in an attended session.
- **For projects updating:** nothing to do; the next kit update writes the new hook commands into `.claude/settings.json`.

**When the guard can't decide: pushes and merges wait for the person** (#53, part of guard robustness, #33).

- **The can't-decide fallback.** In an attended session, when the guard raises or runs out of time, the profile is invalid, the hook's event can't be read, or `python3` is older than 3.11, a push or a merge is asked, and refused in solo mode (`ruleset = false`) or in a permission mode where nobody is asked; everything else is left alone. Before, the CLI's errors exited 1 and let every tool through.
- **One definition of a push or a merge** (`git … push`, `gh … pr … merge`, the GitHub MCP tools that push, write files or merge), in the new `scripts/workflow/fallback.py` (Python 3.7 syntax, the standard library and `modes` only), used by the CLI's error paths and the old-Python fallback alike. Solo mode is read from the profile's first plain `ruleset = …` line, so an invalid profile still counts; an unreadable event is read for its tool, command and mode.
- **The reason** says the guard isn't working, why (the error, the profile's error, the Python version) and how to fix it; where nobody is asked it adds how to be asked and to do it by hand, without repeating the command, since nothing could check it for sensitive data.
- **`hook guard` always exits 0 in an attended session**, printing the fallback's decision or nothing (an invalid profile is still reported on stderr). Ticket and conductor sessions, a missing profile, and the other hooks are unchanged.
- Docs: `docs/enforcement.md`'s "When something is wrong", `SECURITY.md`'s scope (a hook failing open where `docs/enforcement.md` says it asks or refuses, in any role), a README row. Tests: `tests/test_guard_cant_decide.py`.
- **For projects updating:** nothing to do.

**Modes that never ask: the guard refuses what it would have asked** (#52, part of guard robustness, #33).

- **The guard reads `permission_mode`** from each tool call. In an attended session, in `bypassPermissions`, `dontAsk` or a mode the kit doesn't know, every ask the guard makes becomes a refusal, solo mode's remaining asks included; in `default`, `acceptEdits`, `auto`, `plan` or with no mode sent, asks stay asks.
- **The refusal** keeps the ask's reason and adds the mode, how to switch it (Shift+Tab, or the mode selector) to be asked, and how to do it by hand (the command for your own terminal, or on GitHub for a GitHub MCP tool). An unknown mode is named.
- **The guard's modes are listed** in `scripts/workflow/modes.py`, in Python 3.7 syntax with no imports, ready for the old-Python fallback (which reads it since #53).
- Denies, allows, and ticket and conductor sessions are unchanged in every mode. Docs: `docs/enforcement.md`'s mode table, the README's "When something goes wrong" row. Tests: `tests/test_guard_modes.py`.
- **For projects updating:** nothing to do. A person who works in `bypassPermissions` now sees the guard's asks refused, with the command to run by hand.

**Solo mode: the guard refuses GitHub-side changes to the base branch** (#46, part of solo mode, #32).

- **In solo mode** (`ruleset = false`), an attended session is refused, never asked: `gh pr merge --admin`, changing the default branch, renaming the base branch, writing its protection, updating or deleting its ref, merging or writing files into it through the API, and a ruleset's `PUT`, `PATCH` or `DELETE`, through `gh api`, `curl`, GraphQL or the GitHub MCP tools. They are read as gh and curl send them (every URL, every value a field may take, decoded paths), and a path, method, body or alias the guard can't read counts as the base branch. Calls to another repository are unchanged.
- **Creating a ruleset is still asked**, since it is how a project leaves solo mode (a `curl` that creates one is now asked in solo mode too). The repository's merge settings are unchanged.
- **The refusal** carries #45's wording; for an MCP tool, the hand command is the `gh` command that does the same.
- Docs: `docs/enforcement.md`'s solo-mode section. Tests: `tests/test_guard_solo_github.py`.
- **For projects updating:** nothing to do. With `ruleset = true` or no setting, and in ticket and conductor sessions, nothing changes.

**Explanations stop, restart, and run during set-up** (#75, part of the quickstart and the glossary, #35).

- **The guided start (`start`):** *developer* (the first question's answer) or "explain less" stops explaining the glossary's words for the rest of the session. "Explain more" reads the glossary again (`.claude/workflow/docs/glossary.md` vendored, the plugin's `docs/glossary.md` otherwise) and explains each word from then on.
- **Set-up (`setup-workflow`):** asks the experience question first, on its own. After a *new to building* answer (or a skipped question), it follows the same rule from `docs/glossary.md` in its clone of the kit, and keeps explanations out of the set-up pull request (its body, files and commit messages). A *developer* answer gets none.
- **The same rule everywhere:** both skills word it as the context hook (#74) does: each word in the glossary's wording, the first time it's used in the session, never again, and never in what is written on GitHub. `tests/test_glossary_explaining.py` pins the key phrases in all three.
- **For projects updating:** nothing to do.

**The context hook explains the glossary's words to someone new to building** (#74, part of the quickstart and the glossary, #35).

- **At the first prompt of an attended session** whose experience is `new` or unknown (from `WORKFLOW_EXPERIENCE`, `.workflow/experience` or `project.experience`, through `resolve_experience`), `workflow hook context` adds the glossary and the rule: explain each of its words in the glossary's wording, in one or two sentences, the first time it's used in the session, never again, and never in what is written on GitHub.
- **Beside, never instead:** after the guided start's nudge, or with the flow when the first prompt is a flow request. Its own `glossary` marker keeps it to once a session, whether or not the guided start is on or the first prompt was a command.
- **Under Claude Code's 10,000-character limit:** the glossary goes in whole on its own or beside the nudge. Beside the whole flow (or for a glossary too long to fit) it adds only the rule and the glossary's path, to read at once, ahead of the flow, so it is within the 2,000 characters Claude sees of a longer string. A failure in this part never costs the flow or the nudge.
- **Where:** `.claude/workflow/docs/glossary.md` when vendored, the plugin's `docs/glossary.md` otherwise. A vendored copy without the glossary (or with an empty or unreadable one) adds nothing until its next kit update.
- **Never** for a developer, in a ticket or conductor session, after the first prompt, or in a project with no profile. The level changes only what is said, never what is checked, refused or merged.
- Docs: `docs/profile.md` ("Experience"). Tests: `tests/test_glossary_context.py`; the guided start's hook tests now run as a developer, and `run_hook` clears `WORKFLOW_EXPERIENCE` as it does `WORKFLOW_ROLE`.
- **For projects updating:** nothing to do.

**The glossary: `docs/glossary.md`** (#73, part of the quickstart and the glossary, #35).

- **One page of plain words** for someone new to building, read by people and by Claude alike, in two parts: "Building words" (repository, branch, `main`, commit, pull request, checks, merge, revert, preview link, cloud session) and "The kit's words" (guided start, experience level, ticket, spec, map, review panel, solo mode, "Protect `main`", unattended run, conductor, profile, "Check the set-up"). Each entry is one or two sentences, then "Why it matters to you:", and links any other glossary word it uses.
- **Its headings are stable anchors** for the quickstart to link to, and the file stays under 6,000 characters, so #35's context hook can add it whole to a session.
- **Vendored** into `.claude/workflow/docs/glossary.md` with the kit's other docs. The guided start's "explain more" now names where to read it.
- `CONTRIBUTING.md` says a new kit term goes into the glossary in the same pull request, and that `domain-modeling` treats it as the kit's glossary. Tests: `tests/test_glossary.py`.
- **For projects updating:** nothing to do. A project's own `GLOSSARY.md` stays its own.

**`workflow protection` builds the requests: protect, require checks, the checks that ran** (#66, part of automated GitHub set-up, #38).

- **`--protect --repo F`** prints the two requests that protect the base branch: the ruleset to create ("Protect <base> (pairnexus-workflow)", active, an empty bypass list, on `~DEFAULT_BRANCH` when the base branch is the default or `refs/heads/<base>`; `deletion`, `non_fast_forward`, `pull_request` with 0 approvals; `required_status_checks` with "up to date" on only when `--check` names are given), and the merge settings (`allow_merge_commit`, `allow_auto_merge`).
- **`--require-checks F --check NAME`** prints the update that adds the names to a ruleset's required checks with "up to date" on, removing nothing and sending only the fields GitHub accepts on an update.
- **`--checks-ran F [--statuses F] --rulesets F --repo F`** lists the checks that ran on a commit, each passing, failing or pending, the latest result of each name, less those already required; the try-it link's Cloudflare check is never offered, and a file holding one page of several is an error.
- It sends nothing: a session sends each request. `--json` for skills and `workflow doctor`. The read-back is unchanged, except that it now refuses JSON's `NaN` and `Infinity` as not JSON. Docs: `docs/protection.md`. Tests: `tests/test_protection_requests.py`.
- **For projects updating:** nothing to do.

**Unattended runs in solo mode: the charter and the conductor's warning** (#50, part of solo mode, #32).

- **The charter in solo mode** (`ruleset = false`): `workflow charter defaults` picks `session` merging, `charter questions` leaves `auto-merge` out of the merge question's new `options` and says why in its `note` (as it now does with no CI or no required checks), and `charter validate` and `state init` refuse `auto-merge`. GitHub auto-merge could merge at once there, since nothing on GitHub reliably requires checks.
- **Removed protection** (`ruleset = true` while `workflow protection` reads the base branch back as unprotected) counts as solo mode too: the conductor passes the new `--unprotected` to `charter defaults`, `questions` and `validate`. Once accepted, the gap's `removed protection: ` line in `accepted_gaps` carries that verdict to every later check, amendments and `state init` included. The rule is one function, `charter.solo_reason`, and the gap's line is `charter.SOLO_GAP`.
- **The conductor's pre-flight** reads the ruleset back with `workflow protection` and, in either case, states the gap plainly: nothing on GitHub stops a mistake reaching `main`, and the kit's "never merge while CI is red" check is the only one. It offers "Protect `main`" (or restoring it) through `upgrade-setup`, or "Go ahead", which goes in `accepted_gaps`. The ticket environment is still required; when the profile names none, the pre-flight now offers "Set up unattended runs" beside the README's Step 5. Projects with `ruleset` left out keep today's ruleset checks.
- **The run report** repeats a solo-mode run's gap under its summary.
- Docs: `docs/charter.md`. Tests: `tests/test_charter_solo.py`.
- **For projects updating:** nothing to do. With `ruleset` left out, nothing changes; with `ruleset = true`, the conductor also reads the protection back before each run.

**Experience in the guided start and kit updates** (#49, part of solo mode, #32).

- **The guided start** (`start`) asks how much the person knows, *new to building* or *developer*, as the session's very first question, only when `workflow status` finds no level. Skipping counts as new.
- **The answer** goes in the untracked `.workflow/experience`, the file `status` reads, only after checking that git ignores it and that nothing but a plain file is there. A cloud session's file lasts for that session, so the guided start says once how to keep it with `WORKFLOW_EXPERIENCE` on the environment. Where the kit isn't set up yet, set-up asks instead, so the question never comes twice. The first-message hook's nudge now says to ask the level first.
- **"Explain less" or "explain more"** changes the level the same way, and the guided start tells Claude the new level when it records one (#35's glossary explanations stop or start on it).
- **In solo mode,** the guided start's look around says so in one line, with what it means, naming the base branch. It doesn't offer "Protect `main`" there, so the offer never nags.
- **Ticket and conductor sessions** are never asked. The level changes wording and pacing only; what the kit writes on GitHub is the same for every level, plain summary first.
- **Kit updates** (`update-workflow`) ask the project's default once when the profile has no `experience`, and write it in the update pull request; while it stays unset, each later update asks once again. `setup-workflow` now says the guided start asks each person whose level is unknown.
- Tests: `tests/test_experience_start.py`.
- **For projects updating:** the update asks the project's experience default once if the profile has none; "Leave it unset" changes nothing.

**Solo mode and experience in the profile, reported by `workflow status`** (#43, the first part of solo mode, #32).

- **`project.ruleset`:** `true` or `false`; `false` is solo mode. Left out, nothing changes. The profile template shows it as a plain `ruleset = …` line, commented out until set-up writes it.
- **`project.experience`:** `"new"` or `"developer"`, the project's default. Left out, the person's own answer counts, else unknown (set-up and the guided start will ask).
- **`workflow profile check`** refuses any other value of either, naming the setting, so a typo never silently turns solo mode off.
- **Experience resolution:** one function, `resolve_experience`, which `status` uses now and the guard's solo-mode tickets will call. `WORKFLOW_EXPERIENCE` wins, then the untracked `.workflow/experience` file, then `project.experience`, else unknown (worded as new to building). An unrecognised value is skipped with a warning that doesn't repeat it; it never raises.
- **`workflow status`** reports `Solo mode:` (yes, no, or not set) and `Experience:` with its source and any warning, in text and in `--json` (`solo_mode`, `experience`).
- Docs: `docs/profile.md` and the template describe both settings. Tests: `tests/test_solo_mode_profile.py`.
- **For projects updating:** nothing to do. Without the two settings, the kit behaves as before.

**Solo mode: the guard refuses git pushes that touch the base branch** (#45, part of solo mode, #32).

- **In solo mode** (`ruleset = false`), an attended session's push to the base branch is refused, never asked: a push to it (a bare push whose upstream it is, or a push from it, included), a force-push or deletion of it, `--mirror`, `--all`, `--prune` with no branch named, and the settings that make every push a mirror or send a bare push to it (set in the command, or already on disk for a bare push).
- **A push whose destination the guard can't tell** (a variable, `@` with no known branch, a glob, a brace list, a detached HEAD, another directory or repository, a git alias that pushes) counts as the base branch in solo mode, and the refusal says to push the branch by name.
- **Force-pushing or deleting a named feature branch is still asked:** the force and delete options are read with their destinations in solo mode. An ask earlier in a command never hides a refusal later in it.
- **The refusal's reason** says why in plain words, explains what `main` is to someone new to building (or of unknown experience), gives the command to run in their own terminal, and tells Claude to offer "Protect `main`" with "Not now". It is built by `guard.solo_refusal`, for the other solo-mode refusals to reuse.
- **When the guard runs out of time** in solo mode, the command is refused, as in ticket sessions.
- **Unchanged:** ticket and conductor sessions, and projects with `ruleset = true` or no setting.
- Docs: `docs/enforcement.md` §4. Tests: `tests/test_guard_solo.py`.
- **For projects updating:** nothing to do. Solo mode only applies once the profile says `ruleset = false`.

**A guard test no longer fails when `WORKFLOW_ROLE` is set** (#132). `test_hook_takes_the_project_roots_branch_when_the_cwd_has_none` clears the variable for its in-process assertions too, not only for the hook it runs, so the local suite passes in ticket sessions and the conductor's. No assertion changed.

**The guard's linear-time tests no longer fail on a busy machine** (#146). Six tests in `tests/test_kit_011_final.py` held a call to a limit in seconds: the seal, GraphQL lexing, `protected_named`, mutation words, a bundled `-R` and many words. Each now times the same call at size n/8 and at size n, in the process's own CPU time, best of five with the garbage collector off (a run past 2 s of CPU, already a regression, ends the repeats early). It fails when the larger size takes 24 times as long or more: linear work takes about 8 times, quadratic about 64. Time other processes take isn't counted, so the tests passed 40 runs in a row beside two busy processes per CPU, with ratios from 4.4 to 8.8 (wall-clock ratios reached 26 there, since a busy machine cuts a long run more often than a short one). Each test still fails when its call is made quadratic, and the bundled `-R` test fails against the 0.1.0 version of the `-R` regex. The two guard tests also check that both sizes reach the same decision, so the path timed is the one meant. No test was removed or skipped.

**`workflow protection` reads back whether the base branch is protected** (#44, part of solo mode, #32). A session hands it the rulesets, each in full, and the repository's settings, as JSON files ([docs/protection.md](docs/protection.md)).

- It says whether the base branch is protected, and lists each missing protection on its own line, in plain words.
- It says "checks not required yet" when no status checks are required, and reports the merge settings.
- `--json` gives the same for skills.
- It asks GitHub nothing and writes nothing. A wrong input is an error, never "protected".
- Anything it can't tell reads as not protected, with a line saying why: a ruleset on `~DEFAULT_BRANCH` without the settings that name the default branch, say.
- The "Protect `main`" upgrade uses it (#47); set-up, the conductor's pre-flight and `workflow doctor` will.

**"Protect `main`": the `upgrade-setup` skill's first path** (#47, part of solo mode, #32). It takes a project from solo mode to a protected base branch, guided click by click. Claude loads it itself when the person asks; it ships vendored and in the plugin.

- **Offered, never as a nag:** when the person asks, and, once their tickets land, in the guard's solo-mode refusal, before an unattended run in solo mode, and by `workflow doctor`. The offers are `protect_main` (solo mode) and `restore_protection` (the profile says protected, GitHub doesn't).
- **By experience:** someone new to building gets one plain screen with "Do it now" and "Not now", and a one-line result; a developer gets the ruleset's settings. The steps are the same.
- **Admin first:** a person who isn't the repository's admin is told so plainly and handed a ready message for the owner, with the links and the clicks.
- **Rulesets read first:** an already protected base branch goes straight to the pull request. It never edits an existing ruleset.
- **The guided clicks:** the ruleset, its required checks when CI has run on the base branch (otherwise "checks not required yet"), and the merge settings, each with a link to its settings page.
- **Read-back** with `workflow protection`; anything missing is shown in plain words, with the click offered again.
- **The pull request that leaves solo mode:** only after a protected read-back, it sets `ruleset = true`. The guard stays in solo mode until the owner merges it.
- Docs: the README's new "Protect `main`" section, with Steps 3 and 4 as its fallback. Tests: `tests/test_upgrade_setup.py`.
- **For projects updating:** nothing to do.

**The solo set-up, and "Set up unattended runs"** (#48, part of solo mode, #32). `setup-workflow` becomes the short set-up for every new project, and the questions only runs need move to the `upgrade-setup` skill's second path in the same change, so every question still has a place.

- **Set-up asks only what attended work needs:** the project's experience default, sensitive data, the explorer, the mode, the owner and an earlier flow, and deploy commands only when it found deploy scripts. Everything else takes the template's default or what exploring found. It asks nothing about areas, environment names, permission modes, merge approvals or releases.
- **It writes `ruleset`** as a plain line: `true` only when the rulesets can be read and `workflow protection` says the base branch is protected, otherwise `false` (solo mode): an unknown counts as unprotected. It writes `experience` from the answer.
- **Its pull request** says "Merge this and start working", with "Protect `main`" and "Set up unattended runs" as optional next steps. The one-time-steps checklist is gone. After the merge, the set-up session offers "Protect `main`" once, with "Not now".
- **"Set up unattended runs"** (offer `set_up_unattended_runs`): in solo mode it offers "Protect `main`" first, with a plain warning when skipped (GitHub won't hold a merge for failing checks); it asks areas, environment names, ticket sessions' permission mode, merge approvals, releases and repair; it shows one guided screen for the two environments (names, `WORKFLOW_ROLE`, no secrets, the setup script); and it writes the answers to the profile in one pull request. Vendored mode only.
- Docs: the README's "Getting started" leads with the solo set-up, with Steps 3 to 5 kept as the upgrades' click-by-click fallback; `docs/install.md` matches. Tests: `tests/test_solo_setup.py`.
- **For projects updating:** nothing changes for projects set up already. The new set-up applies to new projects; "Set up unattended runs" is there when wanted.

## 0.1.10

**The guard reads editing scripts as their tools do, and fails closed when it runs out of time.** In a ticket session the guard refuses a new test-skip or focus marker that an editing script (`sed`, `perl`, `awk`, `vim`, `ed`) or a patch adds. The correctness reviews of 0.1.9 found older ways, all in 0.1.8 already, that a script could add one unseen, and ways to make the guard slow enough to outlast the hook's timeout, which in 0.1.8 doesn't block. Reported and fixed privately, under `SECURITY.md`.

- **A sed script on standard input** (`-f -`, `-f /dev/stdin`) is read from the heredoc, the `<` file or the `cat` piped in, and a `-f` file the guard can't read (not written yet, a device, a directory) is refused: both were read as empty. `/dev/null` reads as empty.
- **stdin is read as bash gives it:** only fd 0's heredocs, here-strings and `<` files are stdin; more than one of them, stdin from another descriptor (`<&3`) or beside another descriptor's input (`3<f`), is refused for an editing command or a patch. A `cat` piped in gets the last of its own inputs and joins files with nothing between them; what anything else pipes in (a group's output too, `( cat f ) 2>/dev/null |`) can't be seen. A sed script is taken from stdin once. A `/dev/` or `/proc/` path other than `/dev/null` isn't read. Text another command pipes into `ed`, or into vim in ex mode, is refused.
- **vim given stdin** (a heredoc, `<` or a pipe) runs it, so it edits its files: in ex mode (`-e`, `-es`, `-Nes` …) stdin is read as commands, otherwise as keys typed, `:` commands among them, which count as added. So a heredoc of keys that removes a marker is refused too; `-c` or ex mode reads it exactly.
- **sed scripts are read by sed's grammar:** an address (`/re/`, `\%re%`) is read only where a command starts, so text that `a`, `i` and `c` write always counts as added, slashes and `s` commands in it included; an `s` inside an address starts no command; and a command followed by more than sed accepts ends the reading, so the rest counts as added.
- **vim's and ed's `s` ends at the end of its line,** as they read it (the closing delimiter can be left out). The lines `a`, `i` and `c` add count as added, and the keys of `normal` and `execute` are read for markers they run into (`normal Oit.only(`).
- **perl and awk:** a string (`"…"`, `q(…)`, a heredoc) is text the code writes, and a regex (`/re/` where a value is expected, `m{…}`, `qr`) only finds. So an `s` command or a regex inside a string is no longer read as one. perl's bracketed `s` takes the replacement's own delimiters, as perl reads it (`s{…}{…}`, `s{…}/…/`, `s(…) […]`), and a quote-like operator takes its delimiter after a space or as any punctuation (`s /a/b/`, `s,a,b,`, `qq,…,`). A hash key `{s}`, or a comment before the delimiter, counts as added; an `s` after a binary operator (`1-s/…/`, `/x/&&s/…/`, `"a" %s/…/`) is still one, and only a method (`->s`), a file test (`-s $f`) or a sigil after a bareword (`my %s`) makes it a name. awk is read as awk: it has no such operators.
- **What a command finds is read as a regex:** a backslash and a letter (`\s`, `\b`) is a class or an anchor, never that letter. What it puts is read as before.
- **A patch's lines are read as the file's text,** without unescaping, so a removed line holding `it\.only\(` doesn't net away an added `it.only(`.
- **Limits on what the guard reads.** Past these, a ticket session's command is refused rather than read in part:
  - an in-place edit's scripts, `-f` files included, are read once per command, however many files it edits, up to 1 MB together (a vim script sourced with `-S` isn't read, as before: it's among the documented limits);
  - patches up to 4 MB together, where a patch past 1 MB was cut off before (given through a `cat` too);
  - a test file a Write replaces, up to 4 MB.
- **A branch name that isn't UTF-8** is read, and matched against `run.ticket_branch`, instead of making the hooks fail.
- **A time budget:** the guard's hook stops 12 seconds after the kit's CLI starts loading, under its 15-second timeout, and refuses the tool in ticket and conductor sessions. Reading the session's role from the branch counts within it, and a role not read in time counts as ticket. In an attended session it reports the error, as for any guard error. It needs `SIGALRM`, so it doesn't apply on Windows.
- **Decisions:**
  - fuzzed against GNU sed 4.9, perl (bracketed `s` with either form of replacement included) and vim's ex mode, running random scripts on a test file: none that they accepted added a marker the guard missed (copies of lines already in the file aside, which the guard has never counted). Against 0.1.9, the new reading refuses scripts that 0.1.9 allowed, and allows some it refused: those were valid scripts 0.1.9 misread, such as `it.only(` at the start of a sed command, which is sed's `i` inserting `t.only(`, or a vim `s` that leaves out its closing delimiter;
  - a sed `#` comment isn't read for markers, and a sed address with its own delimiter (`\%re%d`) is now read as one;
  - perl's bracketed `s{…}{…}` is now read as perl reads it, so `s{foo}{bar}g; s/xit\(/it(/g`, a removal that 0.1.9 refused, is allowed (its 0.1.9 test moved to `tests/test_kit_0110.py`).
- Tests cover each way in, a big `-f` script across 30 test files, the caps and the time budget (`tests/test_kit_0110.py`).
- **For projects updating to 0.1.10:** nothing to do beyond the update.

## 0.1.9

**The guard's script and skip-marker patterns run in linear time.** In a ticket session the guard counts the test-skip markers an editing script (`sed`, `perl`) or an edit adds, and refuses new ones. Two of its patterns could take far longer than the text they read:
- the patterns for an `s` command and an address (`/x/d`) could read a backslash two ways, and backtracked exponentially on a script with many escapes and no closing delimiter: about 3 seconds at 24 escapes, four times longer with every 2 more;
- the `pytest.mark.xfail(… run=False` marker was quadratic on text holding many `xfail(`.

Either could run past the guard hook's timeout, and in 0.1.8 a hook that runs past its timeout doesn't block the command.

- **An editing script is read as `sed` reads it.** A backslash always starts an escape, so `\/` never ends an `s` command or an address, and each pattern runs in linear time. The slow inputs now return in milliseconds.
- **A command's flags** (`g`, perl's `s`) start no new command, though they're still read for markers.
- **A regex class like `\s*`** is no longer taken for an `s` command (an `s` straight after a backslash starts none). So `/^\s*$/d; s/it\.only(/it(/` is read as cleanup plus a removal.
- **An `s` command the guard can't read,** one that never closes, ends the netting. From there on, every skip marker in the script counts as added, and no address is dropped. perl's bracketed `s{…}{…}` is read as an `s` command delimited by `{`, so a pair of them nets as before, while a single one before a removal ends the netting.
- **The xfail marker** stops at the next `xfail(`, so it stays linear with no length limit. It counts each `xfail(… run=False` on its own, where 0.1.8 could count two as one.
- **Decisions:**
  - well-formed `sed` and `perl` scripts are read as before, except that these are now refused:
    - a single perl `s{…}{…}` before a removal;
    - a `\s*` followed by `s` commands with `*` in them (`/\s*a/d; s/x/it.only(/; s/b*/c/; s/d*/e/`), which 0.1.8 read as one command, netting the marker away;
    - a script that inserts a marker after a stray `\s`, which 0.1.8 netted as a removal;
  - on malformed scripts the guard follows `sed`'s reading. Fuzzed against 0.1.8 over 900,000 random scripts (regex classes like `\s*` included), that refused about 25,600 that 0.1.8 allowed, and allowed 249 that it refused. The ones examined were scripts where 0.1.8 found a marker only by misreading the script, not text the file would hold: a marker run into a following `\s` (which `sed` writes as `skips`), `xfail(` joined to a `run=False` past a `)` the script writes, or a marker read across a mismatched address.
- CodeQL flagged the 0.1.8 patterns. Tests cover the slow inputs, an escaped delimiter, flags, regex classes, long xfail arguments, and scripts that never close.
- **For projects updating to 0.1.9:** nothing to do beyond the update.

## 0.1.8

**The hooks fail closed without Python 3.11** (#22). The kit needs Python 3.11 or later as `python3`. With an older one, the entry point exited 1, which Claude Code treats as a hook error and then runs the tool anyway, so every hook failed open, the guard included. With no `python3` at all, the hook command exited 127, which fails open the same way. Cloud sessions have Python 3.11+, so unattended runs weren't affected; a local session on macOS's own `python3` (3.9) was.

- **An older `python3`:** the entry point hands hooks to `scripts/workflow/_old_python.py`, which needs nothing newer than Python 3.7 and never exits non-zero:
  - a ticket or conductor session is refused every tool, saying which Python it found and what it needs. The role comes from `WORKFLOW_ROLE` (anything but `attended`), or with it unset and the kit set up, from a branch matching the profile's `run.ticket_branch` (read from a plain `ticket_branch = "…"` line);
  - an attended session is asked before a push or a merge (`git push`, `gh pr merge`, the GitHub MCP tools that push or merge), and otherwise left alone;
  - the session start says what is wrong and how to fix it.
- **`python3` missing or failing** (vendored projects; a macOS stub without the developer tools, a pyenv shim with no version): the hook command no longer passes on a failed run. It refuses every tool to a ticket or conductor session, read the same way, and the session start says so. An attended session's guard passes the error on as before. Plugin mode, which is attended only, still needs a working `python3` to run its hooks at all.
- `WORKFLOW_ROLE` with a space inside (`atten ded`) is no longer read as `attended` by the hook command when the kit can't run: it counts as ticket, as the CLI reads it.
- A hook event nested too deeply to parse now counts as malformed (the guard refuses it in a ticket or conductor session) instead of failing the hook.
- The kit's CI also installs Python 3.9 and runs the entry point and the vendored hook command on it, and checks the fallback parses as Python 3.7.
- **Docs:** `docs/enforcement.md` §4 lists the old or missing Python among what fails closed. The README's set-up step and "When something goes wrong", and `docs/install.md`, say what happens.
- **For projects updating to 0.1.8:**
  - The update rewrites the kit's hook commands in `.claude/settings.json` (they now check for `python3`), alongside the copy. Review that part of its pull request too.
  - Nothing else to do.

## 0.1.7

Getting the kit ready for outside users and forks.

- **The kit's home in one place.**
  - `KIT_REPO` in `scripts/workflow/updates.py` is the one place code names the kit's GitHub repository.
  - `workflow version --repo` prints it without asking the network, and `workflow version --json` gives it as `kit_repo`.
  - The skills read it from there:
    - `update-workflow` clones the release from the project's own kit home, and falls back to the upstream for copies older than 0.1.7;
    - `setup-workflow` fills the plugin settings snippet with it;
    - `start` hands updating to `update-workflow`, so the clone command lives in one place.
  - The weekly update check (`templates/github/workflow-kit-update.yml`) reads it at run time from the project's copy, and falls back to the upstream, instead of a fixed value.
  - So a fork's projects hear about, and update to, the fork's releases. The README's new "Forking the kit" lists what a fork changes.
  - A test keeps new hard-coded copies of the name out of the files projects receive.
- **Taking part:**
  - `SECURITY.md`: private vulnerability reporting, and what is in scope;
  - `CONTRIBUTING.md`;
  - `CODE_OF_CONDUCT.md`: the Contributor Covenant 2.1;
  - issue templates for this repository.
  - The README has a status note near the top: beta, what it needs, best-effort support.
- An example in the start skill no longer names PAIR's project.
- **For projects updating to 0.1.7:**
  - The update brings the weekly check's new `workflow-kit-update.yml`, since the files set-up copied once are compared with the release's templates. Bring over its change, keeping your own edits (to the schedule, say): the two `KIT` lines in its script replace the fixed `KIT:` value.
  - Nothing else to do.

## 0.1.6

A full audit of the README and docs against what the kit does, with the fixes it called for.

- **Stopping a run releases nothing.** The `workflow:stop` label (or "stop the run" in the conductor's chat) no longer runs an `end` release: a stop means something may be wrong. The ledger and the report say the release was skipped, and the owner can release by hand. The end time, a wind-down and a finished run still release as the charter says. The stop reason is recorded (`owner`, `ends_at`, `wind-down`, `done`).
- **Required approvals.** The conductor's pre-flight reads the ruleset's `required_approving_review_count`. Above 0, no PR a session opens can merge (sessions post as the owner, who can't approve their own PR), so the kick-off says so and recommends the merge mode `owner`.
- **The conductor:**
  - **Resuming in a new session** ("conductor resume #<n>") creates a new wake routine, deletes the old one, and deletes any routine still bound to the old session;
  - **an abandoned kick-off** closes its tracking and by-hand issues as not planned, so `workflow status` doesn't see a run in progress;
  - pre-flight no longer claims to read the account's usage, which it can't.
- **The wake routine's tool.** Ticket sessions find `fire_trigger` with a ToolSearch for the word, not an exact name: in cloud sessions it is `mcp__claude-code-remote__fire_trigger`, not `mcp__Claude_Code_Remote__fire_trigger`.
- **Set-up uses the latest release,** cloned at its tag, never `main` between releases.
- **`update-workflow`:**
  - lists the project's own edits it kept (`vendor update` now prints `kept` in full, not as a count);
  - brings over changes to the files set-up copied once: `workflow-kit.yml`, `workflow-kit-update.yml`, `docs/agents/issue-tracker.md` and the issue templates.
- **`workflow profile check` warns:**
  - when `commands.setup` is set without `commands.setup_check` (the session start never runs it then);
  - when `guard.protected_paths` leaves out `.claude/**` or `.github/workflows/**` (a list there replaces the defaults).
- **The kit's LICENSE** goes into a vendored copy, as `.claude/workflow/LICENSE`.
- **The guided start:**
  - says what "do it" means for a single small change (a branch and a pull request);
  - tells the ticket environment's rules from the conductor's.
- **Docs:**
  - **`docs/profile.md` (new):** every profile setting, its default and what reads it, and the environment variables (`WORKFLOW_ROLE`, `WORKFLOW_UPDATE_CHECK`, `TMPDIR`).
  - **`docs/enforcement.md` §5 (new):** checking the set-up, item by item (README Step 6 follows it).
  - **`docs/charter.md`:**
    - the stop and the end time;
    - required approvals;
    - waivers and the ruleset;
    - what reuse clears;
    - every validation rule;
    - a mention from the owner's own account may not notify (spike.md row 17).
  - **`docs/install.md`:**
    - what refuses both modes;
    - `vendor update`'s three cases;
    - what plugin mode has and hasn't.
  - **`docs/flow.md`:**
    - the `owner` merge mode;
    - when the explorer and the security review run;
    - the handovers;
    - "Anything else" points to `start`, not `ask-matt`.
  - **`docs/proposal.md`** is marked historical.
  - **The profile template:**
    - a `protected_paths` or `test_paths` list replaces the defaults;
    - `setup` needs `setup_check`;
    - `acceptEdits` still asks before shell commands.
- **README:**
  - **Navigation:** a table of contents, and "When something goes wrong" (new).
  - **Set-up:**
    - Python 3.11+ for everyone;
    - the full contents of the set-up PR;
    - plugin-mode differences;
    - the base branch;
    - one repository per session;
    - the browser explorer's Playwright;
    - `WORKFLOW_ROLE` values.
  - **Daily work:**
    - what "ready" means;
    - the accepted blocker forms and areas;
    - building with you there (evidence, check-ins, status lines);
    - the guided start's full choices;
    - which issues count as unsorted.
  - **Runs:** the real kick-off order, watching, stopping, the end time, resuming, usage, and what isn't yet proven.
  - **Updating:** the weekly issue's contents and skipping a version; `/update-workflow` only from 0.1.5 on.
  - **Reference:** a complete "What's in it"; what counts as shipped.
  - **Fixes:** `/resolving-merge-conflicts` was removed from the table (the pinned Matt Pocock skills don't have it), and attended sessions aren't guarded on protected paths.
- **For projects updating to 0.1.6:**
  - From 0.1.4 or earlier, update by saying "Update the workflow kit: clone it at the latest release's tag and follow its `skills/update-workflow/SKILL.md`" rather than `/update-workflow`: older copies of that skill don't clone a release tag.
  - If the profile sets `commands.setup` without `commands.setup_check` (projects set up before 0.1.3), add a check, e.g. `test -d node_modules`: without it, cloud sessions never install the project's dependencies.
  - `profile check` may now warn about `guard.protected_paths`: put the six defaults back in the list.

## 0.1.5

- **Releases.** Each version is a GitHub release with its tag (`v0.1.5`), its notes this changelog's entry. The kit's own `release` workflow publishes it on every push to main, and only from main (`.github/scripts/release.py`):
  - a version is done once it has a release, not merely a tag, and a tag without one gets its release;
  - every version is tried, and a failure fails the run at the end;
  - its first run publishes 0.1.0 to 0.1.4 at the last commit of each;
  - every change to shipped files bumps VERSION, and no one tags by hand.

  Vendored projects take releases only: `update-workflow` clones a release's tag outside the project and follows that release's copy of itself, never `main` between releases.
- **The update check.**
  - `workflow version` gives the kit's version here and the latest release. It reads the latest with `gh api`, else GitHub's public API, and remembers it for six hours (a failed lookup for an hour). A cache or lock it can't read means "don't know". It never updates anything itself.
  - **The session start says when a newer release is out.** It asks first, in at most 8 seconds, so setup keeps the hook's time.
    - Attended sessions are offered the update: `update-workflow` vendored, `/plugin update pairnexus-workflow@pairnexus` as a plugin.
    - Conductor sessions are told to raise it only at a run's kick-off.
    - Ticket sessions are told nothing: they stay on their run's version.
  - **The guided start** offers **"Update the workflow kit to <version>"** first, before anything else, when a newer release is out (not during a run). When an update pull request is already open, it offers **"Carry on: the kit update PR #n"** instead (`workflow status` finds it by its title, "Update the workflow kit to …").
  - **The conductor's kick-off** asks **Update first** or **Run on <this version>**. A run never updates mid-run.
  - **The weekly update check** (`templates/github/workflow-kit-update.yml`, a project's `.github/workflows/workflow-kit-update.yml`):
    - an issue, "Workflow kit update: 0.1.4 → 0.1.5", labelled `owner-task` (created if missing), linking every release since and the full difference;
    - closed once the project catches up;
    - not asked again for a version whose issue was closed as not planned;
    - a warning, not a failure, when the lock has no version.

    It opens an issue, not a pull request: a pull request opened by a workflow's token runs no CI, so a session makes the update pull request instead.
  - `WORKFLOW_UPDATE_CHECK=off` turns the lookup off.
- **For projects updating to 0.1.5:**
  - `update-workflow` adds `.github/workflows/workflow-kit-update.yml` (a protected path, so it's in the owner's update pull request);
  - from 0.1.4, which has no `version` command, find the latest release with `git ls-remote --tags` (the skill says how).
- **README:**
  - "Keeping it up to date" covers releases, the check and the weekly issue;
  - the kit's repository is public.

## 0.1.4

- **The guided start** (`skills/start`): you don't need to remember a command.
  - At the first message of an attended session, Claude asks "What are we working on?", with choices to click (`AskUserQuestion`).
  - The choices come from where the project stands: carry on a planned item, a map decision, a ready ticket or a PR waiting; something new or a change; a fix; sorting new issues; a brand-new project or large effort; an unattended run.
  - It splits a request into items, and proposes a path for each, always offering a spec as well: a quick ticket, finding the cause first, a spec, a map, or adding to an existing issue.
  - It proposes an order, and files each item as an issue (`<!-- workflow:item path=… -->`), so a plan outlives the session. What an item waits for becomes its tickets' `Blocked by`.
  - It offers each next step as a choice: after the interview, the spec, the tickets and each item. It recommends a fresh session after a spec, a build or a map, and commits the session's files before any stop.
  - "Carry on" picks up a PR waiting for you, work an earlier session claimed, a planned item (with its interview's decisions), a spec without tickets, a map decision or a ready ticket.
  - Sorting new issues follows `triage`, with flow §2's rule for a ticket made ready.
  - A clear first request (a question, "build #262", a command) skips the menu. `/start` brings it back any time. `project.guided_start = false` turns the first-message menu off.
- **`workflow status`**: where the project stands, for the guided start:
  - whether the kit is set up, and whether the project is brand new;
  - an unattended run, claimed work and open PRs;
  - planned items, maps, specs and ready tickets;
  - what waits on a person, and new issues to sort.
- **The flow comes into context for the planning commands on their own:** `/to-spec`, `/to-tickets`, `/wayfinder`, `/grill-with-docs`, `/triage`, `/implement` and `/implement-spec`.
- **`flow.md`:**
  - starting with the guided start, and handovers offered as choices;
  - a spec starts from `grill-with-docs` (or a map's decisions) in the same session;
  - the glossary and ADRs are committed with a pull request, and research notes stay on a `research/` branch (§2's new step and checklist line, §1 step 4);
  - a map's spec is linked from its Destination item, and the map is closed once every item has its spec and tickets;
  - an issue triaged to `ready-for-agent` gets a build ticket's `Blocked by`, `Area:` and acceptance criteria;
  - `implement` and `implement-spec` build with `build-ticket`;
  - the map gate is stated in §1, with who applies it.
- **The conductor's kick-off** lists ready tickets of a map whose Destination isn't fully specified, and recommends leaving them out: `workflow ready` doesn't know about maps.
- **`build-ticket`:** in an attended session that builds more than one thing, each ticket gets its own fresh branch, not named like `run.ticket_branch`.
- **For projects updating to 0.1.4:**
  - `update-workflow` also updates the "Workflow" section of the project's `CLAUDE.md`: a session starts with the guided start (the `start` skill: "What are we working on?", or `/start`);
  - nothing changes in the profile unless you want `guided_start = false`.
- **README:**
  - "Using it" opens with the guided start: where to run it, what the first message does, the paths, an example, the handovers, changing course and long sessions;
  - "Planning new work: what happens underneath" covers every step's command, `/wayfinder`, the side trips, and a table of every Matt Pocock skill in a project (who starts it, how it fits, where its files go, the plugin's prefix);
  - a brand-new project, step by step, with its first ticket built attended and its CI as an owner pull request.

## 0.1.3

From probing pair-drop's two cloud environments: both failed to start, because their setup script installed the project's dependencies from the repository's files, and an environment's setup script runs before the repository is there.

- **The project's own dependencies install at session start.** In cloud sessions (`CLAUDE_CODE_REMOTE=true`; a laptop's checkout is its owner's), the profile's `commands.setup` runs from the kit's SessionStart hook whenever the new `commands.setup_check` fails (it exits 0 once setup has run). A cloud session starts from a fresh clone, so this is every new session; a resumed one finds it in place. The session's context says "Project setup … ran" or "FAILED, exit N", never silence. `workflow repair` runs it too, and exits 1 when it fails. The hook's timeout is 600 s, with setup given up to 510 s of it.
- **The environments' setup script holds only machine tools** the cloud image lacks: the new `run.environment_setup`, empty for most projects whatever their stack (Python, Node.js, a frontend or none). The README's step 5 says what goes where, with examples, and that a script reading the repository's files stops every session in that environment.
- **Environments can be shared** by repositories whose setup scripts match, since they hold nothing of one project; a conductor that releases holds that project's secrets and gets its own.
- `setup-workflow` fills in `commands.setup_check` and `run.environment_setup`, and the PR body says "leave Setup script blank" when it is empty.

## 0.1.2

Documentation for owners, from setting up pair-drop with 0.1.1.

- **"Getting started" opens the README,** step by step with every click: GitHub access and plan (once); asking Claude to run `setup-workflow`, and what it asks; merging its PR; the ruleset; "Allow auto-merge"; the two Claude environments; checking it all; then using it (`/next`, an unattended run, changing and stopping one) and keeping it up to date.
- **Why the environment names must match,** and **both environments are per repo**, each with the project's setup script: the conductor runs the project's tests for its own fixes (`conductor_fixes`, on by default) and its release steps. `enforcement.md` no longer says they are "once per account".
- **The ruleset's bypass list is empty** (sessions act through the owner's account, so what the owner may bypass, they may too), **"Allow merge commits" stays on** and **"Require linear history" off** (sessions merge with a merge commit). A CI that skips paths is fixed in CI, by letting each required job report on every PR.
- **The conductor** treats a missing ticket environment as a blocking pre-flight problem, and never starts ticket sessions in another.
- **`setup-workflow`** writes the one-time steps into its PR body with this project's values (check names, environment names, setup script), so the owner can do them from the PR alone, and ends them with a check.
- **The `workflow kit` CI template** runs read-only (`permissions: contents: read`, `persist-credentials: false`).
- `flow.md` names the project's glossary (`GLOSSARY.md`, or its own name), not `CONTEXT.md`.

## 0.1.1

From the practice run on the sandbox repo (run 2026-10-12-words).

- **Agents' posts carry a marker.** Every comment, issue and PR body an agent posts goes out under the owner's account, so "the owner's comments are amendments" couldn't tell them apart. Every agent post now ends with `<!-- workflow:agent -->` (`scripts/workflow/posts.py`):
  - the guard refuses, in ticket and conductor sessions, a post that creates text without it (`gh issue|pr create|comment`, an edit or close with a body or comment, `gh api` to the issue, comment, PR and review endpoints with a `body` field or `--input`, the text-posting GraphQL mutations, and the GitHub MCP tools that post). It looks in the same texts as the sensitive-data check. Labels, assignees, state changes and merges aren't posts; attended sessions aren't asked;
  - `workflow comments --owner <login> --file comments.json [--since-id N]` lists the owner's own words: their comments without the marker;
  - the tracking and by-hand issue templates, the run report and the ticket briefing end posts with it.
- **The owner's answers in the conductor's chat** are recorded on the issue they concern, quoting the owner with `source: "chat <UTC time>"`; such an answer may close the owner task it completes, and a charter change is an amendment with the same source.
- **Readiness** notes a ticket whose body names one of the profile's protected paths ("names protected path <path> (<pattern>): check it isn't an owner task"), matched as the guard matches them (`issues.readiness(protected=…)`); the ticket stays ready, and the conductor lists noted tickets at kick-off for the owner to keep or exclude. The flow says such a change is an `owner-task`, and a ticket fixing a failing or flaky required check is `workflow:infra`.
- **A run waiting on the owner isn't done.** It keeps going, checking in every 60 minutes, only while in-scope tickets are blocked by open owner tasks or are `needs-human` tickets the conductor asked the owner about during the run (`asked_at` in the state); one "waiting on you" note per task or question; it stops at the end time or when nothing remains.
- **Pre-flight** also checks "Require branches to be up to date" (`strict_required_status_checks_policy`), raised as a safety gap when off. `enforcement.md` and `setup-workflow` now advise leaving "Require review from Code Owners" off while sessions act under the owner's account (an author can't approve their own PR), and on when agents have their own GitHub identity.
- **Sessions started are checked:** `get_session` confirms each new session's `permission_mode` (a mode it can read that differs: archived and reported; no field at all: noted once and carried on), and a claim is read back after the label is added (retried once, else the ticket is skipped that check-in).
- **Briefings copied exactly.** `workflow render` ends the briefing with `Briefing <sha256[:12]>`, prints it with `--print` (the default) and keeps a copy with `--out`; the conductor passes it verbatim and records the hash as the ticket's `briefing`. The session writes what it received to `.workflow/briefing.md`, runs `workflow briefing verify --file .workflow/briefing.md` (`Briefing <hash> intact`, `Briefing changed: expected <a>, got <b>` or `no Briefing line`; trailing whitespace ignored) and quotes that line in its first comment; anything but `intact` and the conductor stops the session and retries.
- **The tracking issue's charter section** sits between `<!-- workflow-charter:begin -->` and `<!-- workflow-charter:end -->`; `workflow charter splice --body body.md --charter charter.json --out body.md [--tickets …]` replaces just that section, and refuses a body without the markers.
- **Merging when auto-merge can't be armed:** in `auto-merge` mode, when GitHub refuses because the PR is already clean, whoever tried (the session, or the conductor) re-checks the merge rule and merges with a merge commit. The guard already allowed a ticket session's own merge (`gh pr merge`, `gh api -X PUT …/pulls/<n>/merge`, the MCP merge tool); tests now pin it. The conductor never merges a change to a protected path itself: it goes in `for_owner`.
- **The claim label:** one rule everywhere. The session always removes `workflow:in-progress` when its ticket ends (and `ready-for-agent` on `needs-human`); the conductor removes leftovers.
- **Waking the conductor.** At kick-off the conductor creates a poke-only routine bound to its own session (`wake_trigger` in the state, a required `wake_trigger` slot in the briefing; `null` and `none` if `create_trigger` fails); a ticket session fires it when its ticket ends ("#N merged in #PR", "#N needs-human" or "#N stopped"; `fire_trigger` is a deferred tool loaded with ToolSearch, tried once, never blocking the ticket), the conductor treats the wake as a check-in, and deletes the routine when the run stops.
- **Spike:** rows 8 and 9 verified, rows 4 and 11 partly, by the sandbox run; row 13 (the wake routine end to end, a child's `permission_mode`) not yet.
- **Ticket sessions use no GraphQL.** `gh api graphql` is refused in the ticket role, reads included: auto-merge (`enable_pr_auto_merge`), comments and reads go through the GitHub MCP tools or REST. Three review passes each found a new way for the shell to assemble a query the guard couldn't read (a `#` or quote in another field, `-ifquery=…`, a field name from a variable, brace expansion, `xargs`). The conductor keeps GraphQL, with the dangerous mutations still refused.
- **Ticket sessions also refuse** `gh` aimed at another repository (`-R other/repo`, `GH_REPO`, `GH_HOST`, gh's token variables), a `gh` or `git` command built from a shell function's or script's parameters (`f() { git push "$@"; }; f origin main`; text that mentions one goes in a quoted heredoc), git that runs a program the guard can't see (`rebase --exec`, `bisect run`, `submodule foreach`, `filter-branch`, `difftool`, `mergetool`, editor and diff-driver settings), git writing a protected path through `--output`, `format-patch -o`, `archive -o` or `bundle create`, `gh auth status --show-token`, and curl writes to GitHub with a flag's value joined to it (`-d@q.json`, `-Tfile`, `-K cfg`) or the host in capitals.
- **From the review of 0.1.1:**
  - `workflow comments` reads every shape the conductor fetches: a list, `--paginate --slurp` pages, arrays one after another, `gh issue view --json comments` and the MCP tool's (`author.login`, node ids, the number from the URL); ids compared as numbers; anything else a clear error. The conductor fetches with `gh api --paginate --slurp`.
  - Protected paths in readiness: not in fenced code (unless the prose before it asks for a change "to" or "in" it), not after "don't", "do not" or "never" in their clause, not a file their clause only reads (a clause ends at a sentence's end, a semicolon, a colon or a dash; when in doubt, noted), and a bare dot-name only when it is itself protected; `path#L20` anchors and blob/tree URLs into the repo are read.
  - The marker rule: `gh issue|pr reopen --comment` and commit comments are posts; `--input` JSON without a `body` or `comment`, GraphQL mutations whose arguments (lexed as GraphQL lexes them, with the operation's variable defaults; a fragment on the mutation counts as a post) carry no body, and `--delete-last` aren't; the conductor's GraphQL from `--input` (a file or stdin) is read from its JSON's `query`. `enforcement.md` says the marker is checked in the command's texts as a whole.
  - The evidence report ends with the marker.
  - The conductor: "a check-in is pending" defined (an enabled one-shot routine bound to it; the wake routine never counts), "A check-in is complete" kept apart from "Done"; the path back from a `needs-human` ticket once the owner answers, and how attempts count; `--only` takes every open `workflow:infra` ticket.

## 0.1.0

First version, from the pair-drop weekend run of 9–12 Oct 2026 and two independent reviews of its proposal.

- **The flow** (`docs/flow.md`): plan (optional maps), spec, build tickets with areas, building, the merge rule, unattended runs.
- **The run charter** (`docs/charter.md`, `workflow charter`): the kick-off questions, the one "go", amendments by the owner's comments, the `workflow:stop` kill switch.
- **The conductor** (`skills/conductor`):
  - pre-flight, check-ins and safe stopping;
  - retries, then `needs-human`;
  - lanes by `Area:`, conductor-ops and the ledger, release under a grant, and the final report.
- **build-ticket** and **review-panel**: rounds until clean, with a Correctness pass for any commit after the last round; the findings table; local evidence for the merge rule.
- **The CLI** (`scripts/workflow.py`):
  - readiness (blockers closed as completed, claims by label, owner tasks);
  - the state block with its size limit;
  - briefings rendered with required slots (a briefing with a gap is refused);
  - sharded, resumable evidence by head SHA, compared with the base branch's test count;
  - vendoring with a lockfile (local edits kept, one mode per project).
- **The hooks:**
  - the guard: base-branch pushes, force-pushes, deploys, protected paths, new skip markers and sensitive posts, across Bash, Edit/Write and GitHub's MCP tools;
  - the checklist gate (`WORKFLOW-STATUS`, one nudge per turn, never while already continuing, a safety cap per session);
  - flow context;
  - environment repair.
- **Review round 1** (three independent reviewers, about 100 findings) changed:
  - the guard to allow-lists for ticket sessions (pushes only to ticket branches, GitHub API writes only to issues, comments, labels and PRs), closing every bypass the review found;
  - the guard to fail closed in ticket and conductor sessions;
  - readiness to leave specs and parents out, read more blocker and closing forms, honour native dependencies, and parse areas;
  - vendoring to check everything before writing, keep local edits through `resolve` and orphans, and never drop Matt Pocock's skills;
  - evidence to prove the commit (untracked files, the base branch's count from a worktree, causes in the report);
  - the charter to check limits, waivers and the profile, with `accepted_gaps` and `reuse`;
  - the conductor's own environment (`WORKFLOW_ROLE=conductor`) and an explicit permission mode for ticket sessions.
- **Review round 2** changed:
  - the guard's parsing (quotes, redirects, subshells, heredocs, the working directory) and its allow-lists for ticket sessions;
  - the conductor's mechanics: claims, check-ins, retries, stopping across several check-ins, and archiving;
  - evidence to run the base branch in a worktree, and to report rather than fail when the base has no usable count;
  - vendoring's keep and resolve.
- **Review round 3** (no blockers) changed:
  - the guard: remote mirror and push-default keys, `find` start paths, sensitive text read through `cat`, stdin and pipes, GraphQL queries from variables, deploys run through interpreters, branch switches when the role comes from the branch, the default branch, more in-place writers, patches from heredocs, skip markers counted net of what is removed, and the global git config protected in ticket and conductor sessions;
  - the charter: malformed charters never raise, amendments are checked against the owner, `charter pin-plan`, and `reuse` clears the old plan;
  - `state init` runs the profile check; readiness reads `/pull/` blockers and "blocked by" mid-sentence;
  - the gate: an unchecked line's reason must say why, and its cap is counted per day;
  - the conductor and build-ticket skills: PRs waiting on the owner, auto-merge, path-filtered checks, and merging the base in rather than rebasing.
- **The final Correctness pass** after round 3 changed: a deploy script run with `.`; the default branch sent on stdin from a file or a pipe; a writing `find` from the project root checked against the protected files there by name; a pull request as a blocker, resolved once merged; the gate's reasons read as words; "doesn't" and "won't" read as negations. Two more passes on those fixes: a find from the root is read exactly (a plain `-name … -delete` or `-exec`, matched against every file there, directories holding protected paths and links to them included) or treated as a write into the whole tree; a symlinked root; `--input` from any spelling of stdin; an escaped `default_branch`; `-execdir` run where its match is; `-L` and `-follow`; `$PWD` and `$(pwd)` in paths; non-ASCII `-iname`; and writers run by `xargs`, whose targets are what the producer names exactly (plain `echo` or `printf '%s\n'` words, or a search checked as a tree; `find … -delete` is the way to delete what a find matches from the root), else unknown.
- **Deviations from the proposal, recorded:**
  - the profile is TOML (stdlib `tomllib`), not YAML;
  - `vendor update` writes `<file>.new` for conflicts and `vendor resolve` records a hand merge, rather than an automatic three-way merge;
  - the UI explorer drives Playwright through Bash rather than an MCP server;
  - the run's state lives in the tracking issue's body (refusing corrupt bodies, re-read before each write) rather than on a state branch;
  - the checklist gate nudges once per turn with a safety cap of 40 a day per session, not "at most 2 a session", since ticket sessions end many turns waiting on CI;
  - a team that requires human approval uses `merge.mode: owner` (ready PRs wait for the owner) rather than auto-merge after approval;
  - the charter has no budget field: usage is watched through the account's limits, reported in pre-flight;
  - the marketplace lists the kit at `./`, so a project pins a release by the tag it vendors from, not through the marketplace;
  - tickets start infra first, then by number (the plan's order isn't kept).
- **Enforcement** (`docs/enforcement.md`): the ruleset, the credential-free ticket environment and CODEOWNERS come first; the hooks are defence in depth.
