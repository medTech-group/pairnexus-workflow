# Security

The kit decides what Claude Code sessions may run, push, merge and post in the projects that use it, so a flaw in it can matter more than its size suggests. Thank you for reporting one.

## Reporting a vulnerability

**Please don't open a public issue.** Report it privately:

1. **GitHub:** this repository's **Security** tab → **Report a vulnerability** (private vulnerability reporting).
2. **Email**, if you can't use GitHub: info@med-technologies.com, with "pairnexus-workflow security" in the subject.

Say what you found, how to reproduce it (a hook event's JSON, a command, a profile), and what it lets a session do. We aim to acknowledge a report within 5 working days, best effort, and to agree a fix and a disclosure date with you. This is a small team's project, so there is no bounty.

## The support promise

The same in the [README](README.md#support) and [CONTRIBUTING.md](CONTRIBUTING.md):
- best effort, with no guaranteed response time for issues or pull requests;
- security reports acknowledged within 5 working days;
- a fix release when a Claude Code update breaks the guard or the hooks.

A Claude Code update that only stops the guard or a hook working goes in a public issue, with the template ["The guard or a hook stopped working after a Claude Code update"](https://github.com/medTech-group/pairnexus-workflow/issues/new?template=claude-code-break.md). One that lets a session past the guard is a security problem: report it here, privately.

## What's in scope

- **A way past the guard** (`scripts/workflow/guard.py`): a command, an edit or a GitHub post that a ticket or conductor session should be refused but isn't, such as a push to the base branch, a write to a protected path, a deploy command, a post without the agents' marker, or one matching the profile's sensitive patterns.
- **The other hooks failing open** where `docs/enforcement.md` says they fail closed.
- **The update path:** a way to get a project to vendor something other than a release of the kit, or to pass `vendor verify --strict` with files the lock doesn't record.
- **The kit's own release and CI workflows** (`.github/`).
- **Anything that leaks** a project's secrets or sensitive data through what the kit posts or logs.

## What isn't

- **Claude Code, claude.ai, GitHub, or Matt Pocock's skills.** Report those to their owners. A flaw in how the kit uses them is in scope.
- **The guard's documented limits.** It can't see a script a session writes and then runs, text piped into a shell, programs that make their own network calls, or deliberately obfuscated commands (`docs/enforcement.md` §4). The guard is a seatbelt for honest mistakes. The boundary is the GitHub ruleset and a ticket environment with no credentials, so a project relying on the guard alone isn't protected, by design.

## How releases reach projects

- **Vendored projects** take a release only through a pull request their owner reviews and merges.
- **Plugin users** follow this repository's `main` as it is. So only the maintainers merge here, every change goes through a pull request with CI, and a security fix goes out as a new release with a CHANGELOG entry saying what projects should do.
