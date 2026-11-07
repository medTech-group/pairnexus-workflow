---
name: study
description: Research notes in the repository - the fixed layout of a topic's folder in `docs/research/<topic>/` (the note, its `Status:`, `Last checked:` and `Issue:` header, its key sources, their saved copies and fingerprints), the "[left out]" lines, and the unconfirmed mark. Use when writing, updating, reading or checking a research note, or when a decision relies on one.
---

# Research notes

All research, studies and fact notes alike, lives in `docs/research/<topic>/`: one note per topic, updated in place (git keeps the old versions), with the sources it rests on saved beside it. This section is the folder's one fixed layout. `workflow research` reads it, and the kit's tests copy their fixtures from the examples below, so write it exactly as shown.

`WF` is the kit's CLI: `python3 .claude/workflow/bin/workflow.py` (vendored), or `python3 <this skill's directory>/../../scripts/workflow.py` (plugin).

## 1. The folder's layout

```
docs/research/<topic>/
  note.md                      the note
  sources/<name>.md            a saved copy of a key source
  sources/<name>.fingerprints  its fingerprints
```

`<topic>` and `<name>` are short, lower-case and hyphenated (`booking-ahead`, `booking-help`). Anything else a study keeps (persona briefs, transcripts, a questionnaire) sits in the same folder, beside these.

**The note** is always `note.md`. It starts with three header lines, in this order, then a blank line:
- `Status:` is `current`, or `superseded by <link>` (the note that replaces it). Read only notes marked `current`: `WF research notes` lists them, and names on standard error any `note.md` whose header it can't read.
- `Last checked:` is the date its claims were last read against their sources, as `YYYY-MM-DD`. It is for information only: nothing decides by it.
- `Issue:` is `#<n>`, the `research` issue that tracks it.

**The key sources** are the sources its findings rest on. They alone get fingerprints. The note lists them under a `## Key sources` heading, one line each: the link in angle brackets, then its saved copy and its fingerprints, as paths inside the topic's folder. That section is the note's last, and the note has it once. A note with no key sources says so with one line, `- None`.

An example note, `docs/research/booking-ahead/note.md`:

```markdown
Status: current
Last checked: 2026-11-07
Issue: #42

# Booking ahead: how far people book

People can book a table up to 30 days ahead, and bookings open at 9:00 each morning ([the booking help page](sources/booking-help.md), paragraph 2).

Cancelling at least 2 hours before a booking gives a full refund (paragraph 4).

## Key sources

- <https://example.com/help/booking>, saved as `sources/booking-help.md`, fingerprints in `sources/booking-help.fingerprints`
```

**Saving a key source.** Fetch the page once:

```
WF research fingerprint <link> --fetch --json
```

It prints the page's paragraphs, each with its position, the SHA-256 of its text as fetched, and its text. It writes nothing. Write both files from that one output, in the layout shown below, so the saved copy is the same text the hashes come from: the fingerprint file from each paragraph's position and hash, and the saved copy from each paragraph's text, under its three header lines. `WF research check` refuses a saved copy and fingerprint file that don't match. It reads HTML and plain-text pages in UTF-8 only; a page it can't read as text, one in another charset or whose bytes aren't valid UTF-8, one whose server names no content type, or one with no text in it (built by JavaScript), it refuses.

**The fingerprint file** holds no text: its first line is `url: <link>`, then one line per paragraph of the page as fetched, its position and the SHA-256 of its text, before anything is left out. Write it from `WF research fingerprint`'s output only; never change a hash by hand. An example, `docs/research/booking-ahead/sources/booking-help.fingerprints`:

```text
url: https://example.com/help/booking
1 af954abf60383cf5f14b6650a28a656e95e1b95908360244d4d1db93eab7bc7c
2 d8aa1758d7945863cdb141fcb4514dd9bd017d138febb5abd9dcf856615f6fa8
3 addcb8b3951b029a33f806cd78d89275ff20c11fe67a6ab7ddcc98ec70826569
4 4301a2050cf762c2ae5567611ac08bb487eaba2d7190b6eba3712bfe6cdb6ed0
```

**The saved copy** starts with three lines, then a blank line, then the page's paragraphs, one per position, separated by blank lines:
- `Source:` the link;
- `Accessed:` the date it was fetched, as `YYYY-MM-DD`;
- `Third-party text:` the line saying it is someone else's text, quoted for checking, and not covered by the repository's licence.

**Leaving out.** A saved copy leaves out personal details and secrets (`profile.md`'s rule), each marked as left out: inside a paragraph, the words become `[left out]`; a paragraph left out whole becomes one line, `[left out]`, in its place. Never delete a paragraph or merge two: the saved copy keeps the same number of paragraphs as its fingerprints, so positions match the hashes. `WF research fingerprint` already leaves out whatever matches the profile's `[sensitive].patterns`, since a commit is never checked against them; personal details are yours to leave out, by reading every paragraph. An example, `docs/research/booking-ahead/sources/booking-help.md`, whose paragraph 3 (a phone number) is left out whole:

```markdown
Source: https://example.com/help/booking
Accessed: 2026-11-07
Third-party text: someone else's words, quoted to check this note's claims. Not covered by this repository's licence.

Booking a table

You can book a table up to 30 days ahead. Bookings open at 9:00 each morning.

[left out]

Cancel up to 2 hours before your booking for a full refund.
```

**The source check.** `WF research check --note docs/research/<topic>/note.md --fetch` fetches each key source again and compares its paragraphs' hashes with the fingerprints, as a set, so paragraphs that only moved count as unchanged. For each source it says one of:
- **unchanged:** nothing to read;
- **changed:** each new paragraph's live text, its position on the live page and its hash, and each paragraph gone, by its position in the saved copy, with the saved copy's text there and its hash. Read only those;
- **can't fetch,** and why.

It refuses a note whose layout breaks the rules above (a key-source line it can't read, a path outside the topic's folder, links that don't agree, or a saved copy whose paragraphs don't match its fingerprints), naming what to fix. It spends no model tokens, and writes nothing.

**The mark.** A claim still wrong after the look at a fix gets the mark ` **(unconfirmed)**`, exactly that text, with its leading space, added at the end of the line that holds the claim. For example:

```markdown
Cancelling at least 2 hours before a booking gives a full refund (paragraph 4). **(unconfirmed)**
```
