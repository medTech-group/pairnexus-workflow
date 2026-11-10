Covers: src/notes/**
Covers: src/shared/text.py

Interface: `NotesStore` (`add(note)`, `list(newest_first=True)`, `remove(id)`), imported from `src/notes/store.py`; nothing else in the folder is used from outside it.

# Notes

Owns the notes: adding, listing and removing them, how they are stored, and the shared text helpers every screen uses on a note's body.

## Helpers

- `clean_body`: trims a note's body and folds its line endings to `\n`; every screen that saves text uses it.
- `preview`: the first line of a body, cut to 80 characters with an ellipsis.

## Rules

- Screens never read the notes' table directly: they go through `NotesStore`.
- A note's body is cleaned with `clean_body` before it is saved, wherever it comes from.

## Decisions

- Notes are listed newest first by default ([ADR 0002](../adr/0002-notes-newest-first.md)).
- Removing a note keeps it for 30 days before it is deleted (pull request 57).

<!-- An example page, in the kit's own templates only: set-up never copies it into a project. The form is in the overview's "Writing a page" section (templates/architecture-overview.md). -->
