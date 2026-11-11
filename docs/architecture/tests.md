Covers: tests/changelog_notes.py

# tests

A small page: only the lines changes have written so far. The rest of the folder waits for the architecture pass.

## Helpers

- `since_0110`: in `changelog_notes.py`, the changelog's notes from `## Unreleased` down to `## 0.1.10`, so a test finds a ticket's note before and after a release moves it under its version.
- `entry`: in `changelog_notes.py`, one ticket's note in those notes: from the heading ending `(#<ticket>).` down to the next note's heading. Status's and doctor's Ctrl-C tests read their notes with it (#717).
- `released`: in `changelog_notes.py`, the latest released version: the heading after `## Unreleased`, without a leading `v`, for a test that checks `VERSION` wasn't bumped (#736).
