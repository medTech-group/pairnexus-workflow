# Glossary

The kit's words, and the building words it uses. A project's own `GLOSSARY.md` stays its own.

## Building words

### Repository

Your project's files on GitHub, with the history of every change.

**Why it matters to you:** everything Claude builds for you lives there.

### Branch

A separate copy of the [repository](#repository)'s files, where a change is made apart from the finished version.

**Why it matters to you:** your project stays as it was until the change is ready.

### `main`

The [branch](#branch) that holds the finished version of your project. Some projects give it another name.

**Why it matters to you:** what is on `main` is what you have.

### Commit

One saved step of a change on a [branch](#branch), with a note of what it does.

**Why it matters to you:** each step can be looked at, or undone, on its own.

### Pull request (PR)

A request to bring a [branch](#branch)'s changes into [`main`](#main), laid out to read.

**Why it matters to you:** it is where you see what Claude did and decide if it goes in.

### Checks (CI)

Tests that run by themselves on each [pull request](#pull-request-pr), green when they pass and red when they fail. CI (continuous integration) runs them.

**Why it matters to you:** red means something is broken, so never [merge](#merge) until they are green.

### Merge

Bringing a [pull request](#pull-request-pr)'s changes into [`main`](#main) with GitHub's green button.

**Why it matters to you:** once merged, the change is part of your project.

### Revert

Undoing a [merged](#merge) change with a new [pull request](#pull-request-pr) that takes it back out: ask Claude to revert it.

**Why it matters to you:** a mistake is never final, so merging needn't be scary.

### Preview link

A link on a [pull request](#pull-request-pr) that opens a working copy of the change, such as your shop, to try before you [merge](#merge) it.

**Why it matters to you:** you see the change for yourself, not only its code.

### Cloud session

Claude Code running on Anthropic's computers, from the Claude app or claude.ai/code. Its environment sets what it starts with: the [repository](#repository), the websites it may reach, any secrets.

**Why it matters to you:** there is nothing to install on your computer.

## The kit's words

### Guided start

How a session begins: Claude asks "What are we working on?" with choices to click. Type `/start` for it at any time.

**Why it matters to you:** you never need to remember a command.

### Experience level

Your answer to "How much do you know about building software?": *New to building* or *Developer*. Say "explain less" or "explain more" to change it; the [profile](#profile) can set a default (`experience`).

**Why it matters to you:** it changes how much Claude explains, never what is allowed.

### Ticket

One small piece of work, as a GitHub issue: what to build, and how to tell it's done.

**Why it matters to you:** each ticket is built in its own session and [pull request](#pull-request-pr).

### Spec

A bigger feature written down, with its decisions and tests, before it is split into [tickets](#ticket).

**Why it matters to you:** you agree what gets built before any code is written.

### Map

A plan for work too big or too unclear for one [spec](#spec), decided one question at a time.

**Why it matters to you:** a big idea gets settled step by step, not all at once.

### Review panel

Claude reviewers who each read a change from one side (does it work, does it follow the rules) before its [pull request](#pull-request-pr) opens. Each round leaves a record on it.

**Why it matters to you:** mistakes are caught before you see the change.

### Solo mode

How a project starts while GitHub doesn't protect [`main`](#main) yet: the [profile](#profile) says `ruleset = false`, and the kit refuses Claude's pushes to `main`, and its changes to `main` on GitHub, so Claude's changes go through a [pull request](#pull-request-pr).

**Why it matters to you:** you can start on GitHub's free plan, and Claude's changes still reach `main` only when you [merge](#merge).

### Protect `main`

GitHub's own protection, ending [solo mode](#solo-mode): a ruleset (GitHub's rules for a [branch](#branch)) sends every change to [`main`](#main) through a [pull request](#pull-request-pr), and "Require these checks", once CI has run, stops a [merge](#merge) while [checks](#checks-ci) fail. On your own computer, with `gh` and admin rights, Claude does it; in a [cloud session](#cloud-session) it guides your clicks.

**Why it matters to you:** GitHub itself then stops a mistake reaching `main`.

### Unattended run

Claude building ready [tickets](#ticket) while you're away, each in its own [cloud session](#cloud-session). "Set up unattended runs" prepares it: a few questions, two cloud environments, and one [pull request](#pull-request-pr) for you to [merge](#merge).

**Why it matters to you:** work moves on while you're away, and you come back to a report.

### Conductor

The Claude session that runs an [unattended run](#unattended-run): it hands out each [ticket](#ticket), keeps the [pull requests](#pull-request-pr) moving, and writes the report.

**Why it matters to you:** it is the session you talk to about a run.

### Profile

The kit's settings for your project, in `.claude/workflow/profile.toml`: which is [`main`](#main), how to run the tests, [solo mode](#solo-mode) (`ruleset`) and the default [experience level](#experience-level) (`experience`).

**Why it matters to you:** Claude reads it instead of guessing.

### Check the set-up

Ask Claude to "check the set-up": the `check-setup` skill runs `workflow doctor`, lists what's missing, and offers each fix, such as [Protect `main`](#protect-main), with "Not now". It changes nothing itself; in [solo mode](#solo-mode) the [guided start](#guided-start) offers it once a session.

**Why it matters to you:** you see in one place what is set up and what's left.
