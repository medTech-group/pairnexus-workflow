Covers: scripts/workflow/proc.py

Interface: `run(argv, *, cwd=None, env=None, timeout, stderr=False) -> Done` and `output(argv, *, cwd=None, timeout) -> str | None`.

# scripts/workflow

## Helpers

- `proc.run`: runs one of the kit's own short commands with no shell and no input, in a session of its own, and kills its whole process group whenever the caller stops waiting (a timeout, a Ctrl-C, or a SIGTERM or SIGHUP left to its default, which then ends the caller as before), holding any of these that comes while it starts; a Ctrl-C still reaches the caller as `KeyboardInterrupt`. Doctor's `_run`, `workflow status`'s `git` call and the profile's `_git` use it.
- `proc.output`: what a command printed, as UTF-8 with other bytes replaced, when it exited 0; else None.

## Decisions

- Doctor's process-group kill (#684) moved here rather than being copied, so `workflow status` and the profile's `git` reads share it (#689).
