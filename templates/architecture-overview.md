# Architecture

This folder is the project's architecture, written down. This file, the overview, holds only the rules every page shares; the pages beside it each describe one piece of the code. It is one of the project's rule documents, so every session and reviewer reads it. A change also reads the pages that cover the files it touches, and the pages list: every page's interface and helpers.

Pages are added as code is built: a folder of code with no page yet isn't a mistake, only code nobody has described so far. A later pass writes the pages for code that existed before this folder did.

The rules below are written rules: a change that breaks one is blocked, like a change that breaks any other rule document.

## Standing rules

### Structural lines go in the same pull request

A change that makes a structural decision writes its line in the same pull request, in the page it belongs to. A cross-cutting rule goes in this overview, under "Cross-cutting rules". Structural means:
- what a page owns;
- its interface;
- its own rules;
- its helpers;
- its decisions;
- the cross-cutting rules.

Lines in this folder are always the change's own: they are never another area's files and never on a run's stay-out list.

### A new module adds its page

A change that adds a new module adds its page in the same pull request. A new module is a new folder of code that no page covers and that held no code before. A new file in an existing folder that no page covers is old code: it is left to the architecture pass, not to this rule.

The new module's page is a full page: its `Covers:` spans the folder (`Covers: src/payments/**`), and it says what the module owns and gives its interface. When a change adds folders inside new folders, the outermost new folder gets the page.

"Code" here is what the kit's doctor counts: the profile's `guard.code_paths` when they are set, else every tracked file outside `docs/` and the protected paths. Either way, files at the repository's root, the documents in the profile's `project.rules` and the profile's `guard.test_paths` aren't code for this rule.

### Reuse, not copies

A change doesn't add a copy of logic that already exists: it uses the shared helper, or moves the logic into one, used in its own code, and lists it in its page.

- Copies already in the code are left to the architecture pass.
- When moving the logic would touch another area's files during a run, or a protected path, the copy doesn't block. A ticket to merge the copies is always filed: an owner task when the move would touch a protected path.

### Code no page covers yet

A structural line about a file no page covers, an old file or a new one, outside a new module's folder, goes in a small page:
- **Its name** is the file's folder path, its folders joined with `--`, with a dot at the start of the name dropped: `src/orders/check.py` → `src--orders.md`, `.tools/lint/check.py` → `tools--lint.md`.
- **A file at the repository's root** has its line in `_root.md`. A top-level folder named `_root` would share that page: a rare clash, accepted, like any other two folder paths that give one name.
- **Its `Covers:`** gets a line for that file, written as a literal path: each `*`, `?` and `[` in it in brackets (`[*]`, `[?]`, `[[]`), since a `Covers:` line is a glob. `app/[id]/page.py` is written `Covers: app/[[]id]/page.py`.
- The page is created if it doesn't exist, and added to if it does: two changes touching one folder write to the same page.
- A small page needs only its `Covers:` lines and the changes' lines until the architecture pass. The rest of the folder stays noted by doctor as code no page covers.
- A helper moved into a new folder goes on that folder's page.

A new module (above) gets a full page instead.

## Cross-cutting rules

None written yet.

## Writing a page

A page is a Markdown file directly in this folder, other than this `README.md`. Files in subfolders, and files that aren't `.md`, are neither pages nor read. There is no size limit and no diagram is required. Its form:

```markdown
Covers: src/orders/**
Covers: src/shared/money.py

Interface: `place(order) -> Receipt`; nothing else is imported from outside the folder.

# Orders

Owns placing and checking orders, and the order's states.

## Helpers

- `check_input`: validates an order's fields, with the shared error messages.

## Rules

- Orders never call billing directly; they raise an event.

## Decisions

- Orders keep their own copy of prices, so a price change never changes a placed order ([ADR 0003](../adr/0003-order-prices.md)).
```

- **`Covers:`** lines come first, at the top of the page: one glob on each line, never two on one line. They match a path as the guard's protected paths do: `*` also crosses `/`, and `**` matches every file under a folder. Pages may overlap: a rule for a group of pages lives in one page whose `Covers:` spans the group. A page with no `Covers:` line covers nothing yet: every change reads it until it has one.
- **`Interface:`** is one line: how the rest of the code uses this piece. A page without one is listed as having no interface given.
- **`## Helpers`** lists the shared helpers the page owns, one list item each, written ``- `name`: what it's for``.
- **`## Rules`** holds the page's own written rules. They bind every change to the files the page covers.
- **What it owns** and **its decisions** are free text under headings: each decision is one line, linking the ADR or pull request that made it.
