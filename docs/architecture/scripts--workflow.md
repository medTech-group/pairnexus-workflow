Covers: scripts/workflow/evidence.py

# scripts/workflow

## Helpers

- `_paths`: in `evidence.py`, names paths in a message: the first five, then "and N more".
- `_dirty_store`: in `evidence.py`, the emptied `<sha>-dirty` store, where a run with `--allow-dirty` on a dirty tree keeps its results, apart from the commit's evidence and never reused.

## Rules

- `evidence.py`: a run keeps a shard's result as the commit's only after checking, once the shard has ended, that HEAD hasn't moved. A moved head stops the run with nothing kept for that shard, so a later run on the commit runs it again. The checkout's working tree is checked only at its start, and the base branch's worktree, fresh from git, not at all (#671).
