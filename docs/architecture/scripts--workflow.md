Covers: scripts/workflow/evidence.py
Covers: scripts/workflow/proc.py
Covers: scripts/workflow/research.py

Interface: `proc.run(argv, *, cwd=None, env=None, timeout, stderr=False) -> Done` and `proc.output(argv, *, cwd=None, timeout) -> str | None`.

# scripts/workflow

A small page: only the lines changes have written so far. The rest of the folder waits for the architecture pass.

## Helpers

- `_paths`: in `evidence.py`, names paths in a message: the first five, then "and N more"; in a report, each a code span on one line (`_code`: quoted as git quotes it when it holds a control character, a double quote or a backslash, and fenced past its backticks).
- `_dirty_store`: in `evidence.py`, the emptied `<sha>-dirty` store, where a run keeps what didn't run on the commit itself (a dirty tree with `--allow-dirty`, or a tree that changed mid-run), apart from the commit's evidence and never reused.
- `tree_state`: in `evidence.py`, a look at the whole checkout's tree, from its top even when the project is a folder in it, outside the project's `.workflow/`: each tracked or staged path's index entries and `lstat`, and the untracked files that aren't ignored (a checked-out submodule's HEAD and its own tracked and untracked paths in its place), and the `lstat` of each folder holding a tracked path. `tree_changes` gives the paths that differ between two looks; read-only git commands change neither.
- `proc.run`: runs one of the kit's own short commands with no shell and no input, in a session of its own, and kills its whole process group whenever the caller stops waiting (a timeout, a Ctrl-C), holding a Ctrl-C that comes while it starts; a Ctrl-C still reaches the caller as `KeyboardInterrupt`. Doctor's `_run`, `workflow status`'s `git` call, the profile's `_git` and the evidence run's tree look (`_git_out` in `evidence.py`) use it.
- `proc.output`: what a command printed, as UTF-8 with other bytes replaced, when it exited 0; else None.
- `ascii_link`: in `research.py`, the link in ASCII: the host encoded by UTS 46 non-transitional rules, the userinfo, path, query and fragment percent-encoded as UTF-8. `fetch` sends a link outside ASCII without its userinfo, as a browser does; a link in ASCII as written. `fetch` and `link_problem` both use it, so a link that can be saved is one that can be fetched.
- `unnameable`: in `research.py`, why no key-source line could name a link (a space, a line break, a control character, `<` or `>`), else None. `ascii_link` and `link_problem` both refuse such a link with it.

## Rules

- `evidence.py`: a run keeps a shard's result as the commit's only after checking, once the shard has ended, the working tree and then that HEAD hasn't moved. A moved head stops the run with nothing kept for that shard, so a later run on the commit runs it again (#671). A tracked or staged path changed since the last look (`tree_state`, inside submodules too, the repair's window included), or with `--allow-dirty` an untracked file that appeared or a file created or removed in a folder holding a tracked path (an ignored one too, even one gone again), makes the run a dirty one: it goes on, keeps that shard and every later one under `<sha>-dirty`, and its report carries the dirty marker. Untracked files that appear without `--allow-dirty` are left be (#704). The base branch's worktree, fresh from git, isn't checked at all (#703).

## Decisions

- Doctor's process-group kill (#684) moved into `proc.py` rather than being copied, so `workflow status` and the profile's `git` reads share it (#689).
- A host outside ASCII is encoded only where the standard library can be sure it encodes it as a browser does, and refused as can't fetch otherwise: the kit has no UTS 46 mapping table, and Python's own `idna` codec is IDNA 2003, which turns `faß.de` into `fass.de` (#532, [#560](https://github.com/medTech-group/pairnexus-workflow/pull/560)).
