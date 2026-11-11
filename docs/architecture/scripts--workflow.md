Covers: scripts/workflow/evidence.py

# scripts/workflow

## Helpers

- `_paths`: in `evidence.py`, names paths in a message: the first five, then "and N more".
- `_dirty_store`: in `evidence.py`, the emptied `<sha>-dirty` store, where a run keeps what didn't run on the commit itself (a dirty tree with `--allow-dirty`, or a tree that changed mid-run), apart from the commit's evidence and never reused.
- `tree_state`: in `evidence.py`, a look at the checkout's tree outside `.workflow/`: each tracked or staged path's index entries and `lstat` (a checked-out submodule's HEAD and its own tracked paths in its place), and the untracked files that aren't ignored. `tree_changes` gives the paths that differ between two looks; read-only git commands change neither.

## Rules

- `evidence.py`: a run keeps a shard's result as the commit's only after checking, once the shard has ended, the working tree and then that HEAD hasn't moved. A moved head stops the run with nothing kept for that shard, so a later run on the commit runs it again (#671). A tracked or staged path changed since the last look (`tree_state`, inside submodules too, the repair's window included), or with `--allow-dirty` an untracked file that appeared, makes the run a dirty one: it goes on, keeps that shard and every later one under `<sha>-dirty`, and its report carries the dirty marker. Untracked files that appear without `--allow-dirty` are left be (#704). The base branch's worktree, fresh from git, isn't checked at all (#703).
