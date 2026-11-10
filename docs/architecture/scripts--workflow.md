Covers: scripts/workflow/evidence.py

# scripts/workflow

## Helpers

- `_paths`: in `evidence.py`, names paths in a message: the first five, then "and N more", in backticks for the report.
- `_dirty_store`: in `evidence.py`, the emptied `<sha>-dirty` store, where a run keeps what didn't run on the commit itself, apart from its evidence and never reused.

## Rules

- `evidence.py`: a run keeps a shard's result only after checking, once the shard has ended, that the head hasn't moved and no tracked or staged file changed; either stops the run with nothing kept for that shard. An untracked file that appears is named in the report, never a stop, since a suite's own output can't be told from it; under `--allow-dirty` any change makes the report dirty instead (#671).
