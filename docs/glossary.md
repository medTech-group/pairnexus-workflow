# Glossary

The kit's words and the building words it uses; a project's own `GLOSSARY.md` stays its own.

## Building words

### Repository

Your project's files on GitHub, with every change's history.

**Why it matters to you:** everything Claude builds for you lives there.

### Branch

A copy of the [repository](#repository)'s files where a change is made apart from the finished version.

**Why it matters to you:** your project stays as it was until the change is ready.

### `main`

The [branch](#branch) holding your project's finished version; some projects name it differently.

**Why it matters to you:** what is on `main` is what you have.

### Commit

One saved step of a change on a [branch](#branch), with a note of what it does.

**Why it matters to you:** each step can be looked at or undone on its own.

### Pull request (PR)

A request to bring a [branch](#branch)'s changes into [`main`](#main). Each one the kit opens starts with "In plain words": what changes for you, how to try it, what could go wrong.

**Why it matters to you:** it's where you see what Claude did and decide if it goes in.

### Checks (CI)

Tests that run by themselves (CI) on each [pull request](#pull-request-pr): green when they pass, red when they fail.

**Why it matters to you:** red means something is broken: never [merge](#merge) until they're green.

### Merge

Bringing a [pull request](#pull-request-pr)'s changes into [`main`](#main): ask Claude "is #12 ready to merge?" for "Ready" or "Not yet" and why; nothing merges until you choose "Merge it now" (with a [merge queue](#merge-queue), it queues).

**Why it matters to you:** once merged, the change is part of your project.

### Merge queue

GitHub [merging](#merge) [pull requests](#pull-request-pr) in turn, each tested with [`main`](#main) and those ahead of it. "Use a merge queue" turns it on.

**Why it matters to you:** a green pull request never goes stale while `main` moves.

### Revert

Undoing a [merged](#merge) change with a new [pull request](#pull-request-pr): ask Claude to revert it.

**Why it matters to you:** a mistake is never final, so merging needn't be scary.

### Preview link

A [pull request](#pull-request-pr)'s link to a working copy of the change, to try before you [merge](#merge). "Add try-it links" turns them on.

**Why it matters to you:** you see the change for yourself, not only its code.

### Cloud session

Claude Code on Anthropic's computers, from the Claude app or claude.ai/code.

**Why it matters to you:** nothing to install on your computer.

## The kit's words

### Guided start

How a session begins: Claude asks "What are we working on?" with choices to click. Type `/start` any time.

**Why it matters to you:** you never need to remember a command.

### Experience level

*New to building* or *Developer*, your answer to "How much do you know about building software?"; say "explain less" or "explain more" to change it.

**Why it matters to you:** it changes how much Claude explains, never what's allowed.

### Ticket

One small piece of work as a GitHub issue: what to build and how to tell it's done.

**Why it matters to you:** each ticket is built in its own session and [pull request](#pull-request-pr).

### Spec

A bigger feature written down with its decisions and tests before it's split into [tickets](#ticket).

**Why it matters to you:** you agree what gets built before code is written.

### Map

A plan for work too big or unclear for one [spec](#spec), decided one question at a time.

**Why it matters to you:** a big idea is settled step by step.

### Study

Research before building: agents gather evidence and play made-up people, ending in build it, prototype first, or stop.

**Why it matters to you:** you learn if it's worth building first.

### Review panel

Claude reviewers who each read a change, a [spec](#spec) or a [map](#map) decision from one side, round after round. The small review is one round of Correctness for a [ticket](#ticket) marked small; the light review, asked for, is one round with no walk-through of the screens, never chosen for you.

**Why it matters to you:** mistakes are caught before you see the change.

### Bar

Where a [ticket](#ticket)'s review stops: what it must handle, its safe fallback when unsure, and the limits it accepts.

**Why it matters to you:** reviews end at what you asked for.

### Solo mode

A project before GitHub protects [`main`](#main): the kit refuses Claude's changes straight to `main`.

**Why it matters to you:** you can start on GitHub's free plan; Claude's changes reach `main` only when you [merge](#merge).

### Protect `main`

GitHub's own protection, ending [solo mode](#solo-mode): every change to [`main`](#main) goes through a [pull request](#pull-request-pr), and "Require these checks" stops a [merge](#merge) while [checks](#checks-ci) fail.

**Why it matters to you:** GitHub itself then stops mistakes reaching `main`.

### Unattended run

Claude building ready [tickets](#ticket) while you're away, each in its own [cloud session](#cloud-session). "Set up unattended runs" prepares it.

**Why it matters to you:** work moves on and you come back to a report.

### Conductor

The session that runs an [unattended run](#unattended-run): it hands out [tickets](#ticket), keeps [pull requests](#pull-request-pr) moving and writes the report.

**Why it matters to you:** it's the session you talk to about a run.

### Profile

Your project's kit settings in `.claude/workflow/profile.toml`: which is [`main`](#main), the test commands, [solo mode](#solo-mode), the default [experience level](#experience-level).

**Why it matters to you:** Claude reads it instead of guessing.

### Check the set-up

Ask Claude to "check the set-up": it lists what's missing and offers each fix, like [Protect `main`](#protect-main). In [solo mode](#solo-mode) the [guided start](#guided-start) offers it once a session.

**Why it matters to you:** you see in one place what's set up and what's left.
