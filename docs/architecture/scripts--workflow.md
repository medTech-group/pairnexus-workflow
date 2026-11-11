Covers: scripts/workflow/evidence.py
Covers: scripts/workflow/proc.py
Covers: scripts/workflow/research.py

Interface: `proc.run(argv, *, cwd=None, env=None, timeout, stderr=False) -> Done` and `proc.output(argv, *, cwd=None, timeout) -> str | None`.

# scripts/workflow

A small page: only the lines changes have written so far. The rest of the folder waits for the architecture pass.

## Helpers

- `_paths`: in `evidence.py`, names paths in a message: the first five, then "and N more".
- `_dirty_store`: in `evidence.py`, the emptied `<sha>-dirty` store, where a run with `--allow-dirty` on a dirty tree keeps its results, apart from the commit's evidence and never reused.
- `proc.run`: runs one of the kit's own short commands with no shell and no input, in a session of its own, and kills its whole process group whenever the caller stops waiting (a timeout, a Ctrl-C), holding a Ctrl-C that comes while it starts; a Ctrl-C still reaches the caller as `KeyboardInterrupt`. Doctor's `_run`, `workflow status`'s `git` call and the profile's `_git` use it.
- `proc.output`: what a command printed, as UTF-8 with other bytes replaced, when it exited 0; else None.
- `ascii_link`: in `research.py`, the link in ASCII: the host encoded by UTS 46 non-transitional rules, the userinfo, path, query and fragment percent-encoded as UTF-8. `fetch` sends a link outside ASCII without its userinfo, as a browser does; a link in ASCII as written. `fetch` and `link_problem` both use it, so a link that can be saved is one that can be fetched.
- `unnameable`: in `research.py`, why no key-source line could name a link (a space, a line break, a control character, `<` or `>`), else None. `ascii_link` and `link_problem` both refuse such a link with it.

## Rules

- `evidence.py`: a run keeps a shard's result as the commit's only after checking, once the shard has ended, that HEAD hasn't moved. A moved head stops the run with nothing kept for that shard, so a later run on the commit runs it again. The checkout's working tree is checked only at its start, and the base branch's worktree, fresh from git, not at all (#671).

## Decisions

- Doctor's process-group kill (#684) moved into `proc.py` rather than being copied, so `workflow status` and the profile's `git` reads share it (#689).
- A host outside ASCII is encoded only where the standard library can be sure it encodes it as a browser does, and refused as can't fetch otherwise: the kit has no UTS 46 mapping table, and Python's own `idna` codec is IDNA 2003, which turns `faß.de` into `fass.de` (#532, [#560](https://github.com/medTech-group/pairnexus-workflow/pull/560)).
