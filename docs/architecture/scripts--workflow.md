Covers: scripts/workflow/evidence.py

# scripts/workflow

## Helpers

- `_paths`: in `evidence.py`, names paths in a message: the first five, then "and N more", in backticks for the report.
- `_dirty_store`: in `evidence.py`, the emptied `<sha>-dirty` store, where a run keeps what didn't run on the commit itself, apart from its evidence and never reused.

## Rules

- `evidence.py`: a run keeps a shard's result as the commit's only after checking, once the shard has ended, the working tree and then the head. A moved head stops the run with nothing kept for that shard. Any change to the tree since the last check (each tracked or staged file's index entry and stat, and the untracked files) keeps what runs from that shard on apart, under `<sha>-dirty`, never reused: a tracked or staged change, or under `--allow-dirty` any change, makes the report dirty, naming the paths; an untracked file that appears is named in the report, never a stop, since a suite's own output can't be told from it. What changes while the `[repair]` commands run is checked the same way. The base branch's worktree, fresh from git, is checked only for a moved head (#671).
