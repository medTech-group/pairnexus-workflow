Covers: scripts/workflow/evidence.py
Covers: scripts/workflow/research.py

# scripts/workflow

A small page: only the lines changes have written so far. The rest of the folder waits for the architecture pass.

## Helpers

- `_paths`: in `evidence.py`, names paths in a message: the first five, then "and N more".
- `_dirty_store`: in `evidence.py`, the emptied `<sha>-dirty` store, where a run with `--allow-dirty` on a dirty tree keeps its results, apart from the commit's evidence and never reused.
- `ascii_link`: in `research.py`, the link in ASCII: the host encoded by UTS 46 non-transitional rules, the userinfo, path, query and fragment percent-encoded as UTF-8. `fetch` sends a link outside ASCII without its userinfo, as a browser does; a link in ASCII as written. `fetch` and `link_problem` both use it, so a link that can be saved is one that can be fetched.
- `unnameable`: in `research.py`, why no key-source line could name a link (a space, a line break, a control character, `<` or `>`), else None. `ascii_link` and `link_problem` both refuse such a link with it.

## Rules

- `evidence.py`: a run keeps a shard's result as the commit's only after checking, once the shard has ended, that HEAD hasn't moved. A moved head stops the run with nothing kept for that shard, so a later run on the commit runs it again. The checkout's working tree is checked only at its start, and the base branch's worktree, fresh from git, not at all (#671).

## Decisions

- A host outside ASCII is encoded only where the standard library can be sure it encodes it as a browser does, and refused as can't fetch otherwise: the kit has no UTS 46 mapping table, and Python's own `idna` codec is IDNA 2003, which turns `faß.de` into `fass.de` (#532, [#560](https://github.com/medTech-group/pairnexus-workflow/pull/560)).
