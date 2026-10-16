---
name: The guard or a hook stopped working after a Claude Code update
about: A Claude Code update broke the guard or a hook (a way past the guard is a security problem; see SECURITY.md)
labels: claude-code-break
---

**Does the break let a session past the guard?** Then it is a security problem: report it privately with [Report a vulnerability](https://github.com/medTech-group/pairnexus-workflow/security/advisories/new), as SECURITY.md says, never with this template. Past the guard means a push, an edit, a deploy or a post that the guard should refuse now goes through.

**Where**
- Claude Code version (`claude --version`):
- Kit version (`workflow version`: in a vendored project `python3 -B .claude/workflow/bin/workflow.py version`; or the plugin's):
- Vendored or plugin:
- Session: attended, conductor or ticket session; cloud or local:
- The last Claude Code version it worked with, if you know it:

**What you ran**
The command, tool call or hook event. Leave out anything private: secrets, personal data, your project's code.

**What happened instead**
What the guard or the hook did (an error, nothing, the wrong decision), and what you expected.

**Anything else**
