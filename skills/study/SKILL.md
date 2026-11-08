---
name: study
description: Run a study, from the intake to the verdict - the research issue, the intake, the panel (an evidence gatherer, a question writer, 5 to 8 personas, a synthesizer and a validator), the ranked questions, the note in its research pull request, the research check and the look, and the verdict (build it, prototype first, or stop); and research notes in the repository - the fixed layout of a topic's folder in `docs/research/<topic>/` (the note, its `Status:`, `Last checked:` and `Issue:` header, its key sources, their saved copies and fingerprints), the "[left out]" lines, the unconfirmed mark, the stakes record and the token record, and a study's size from past ones. Use when running a study, when writing, updating, reading or checking a research note, when a decision relies on one, or when judging a feature's stakes, offering a study or ending one.
---

# Studies and research notes

All research, studies and fact notes alike, lives in `docs/research/<topic>/`: one note per topic, updated in place (git keeps the old versions), with the sources it rests on saved beside it. Section 1 is the folder's one fixed layout, and sections 2 and 3 the two records' fixed shapes. Sections 4 to 13 run a study, from the intake to the verdict. `workflow research` reads it, and the kit's tests copy their fixtures from the examples below, so write it exactly as shown.

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

**The key sources** are the sources its findings rest on. They alone get fingerprints. The note lists them under a `## Key sources` heading, one line each: the link in angle brackets, then its saved copy and its fingerprints, as paths inside the topic's folder. The note has that section once, outside any code fence. It runs to the next `# ` or `## ` heading, or to the note's end, so other sections may follow it. It holds only those lines, with blank lines between them if you like. Every fingerprint file is named `<name>.fingerprints`, and each one in the topic's folder, in any folder inside it, has its key-source line in that section: a note with a fingerprint file the section doesn't name is refused, naming the file, since a key source written anywhere else wouldn't be read. A file there whose first line is a `url:` line is a fingerprint file too, whatever its name, and a file or folder there that can't be read is refused, naming it, since it can't be ruled out. The rest of the note is prose, and nothing in it is read for key sources. A note with no key sources says so with one line, `- None`, and its folder holds no fingerprint files.

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

**Saving a key source.** Write its saved copy and its fingerprint file from one fetch:

```
WF research fingerprint <link> --fetch --saved docs/research/<topic>/sources/<name>.md --fingerprints docs/research/<topic>/sources/<name>.fingerprints
```

It writes both files from that one fetch, in the layout shown below, making their folders when missing: the fingerprint file from each paragraph's hash, and the saved copy from each paragraph's text, under its three header lines, `Accessed:` today's date. So the saved copy is the same text the hashes come from. It writes both or neither: when either file can't be written (a folder in its way, a name too long, a symbolic link, a path that names a folder), it says which in one line and changes neither, leaving no folder it made behind. When a file can't then be put back as it was, or a new file can't be removed, the line names it instead, and where its old version is kept. The fingerprint file's name ends with `.fingerprints`, the saved copy's doesn't, neither path holds a backtick, a control character (a line break among them) or a byte that isn't UTF-8, and the two paths name different files; it checks both, and refuses a link holding the profile's `[sensitive].patterns`, before it fetches anything. It also prints the paragraphs, each with its position, hash and text (`--json` for JSON). Then read every paragraph of the saved copy and leave out personal details by hand ("Leaving out", below), and add its key-source line to the note: `WF research check` refuses a fingerprint file in the topic's folder that no key-source line names.

A link holding characters outside ASCII it refuses: cite it percent-encoded. It also refuses, before reading anything, a link no key-source line could name: one holding a space, a line break, a control character, `<` or `>`, or one that isn't http or https with a host. It reads HTML and plain-text pages in the charset they name, as the WHATWG Encoding Standard maps its labels, else in UTF-8. A page starting with a byte order mark it reads in the mark's UTF-8 or UTF-16, whatever its header or `<meta>` names. The header's label is its first `charset` parameter: a `charset=`, in either case, right after a `;` and any spaces or tabs, whose value starts, after any opening quote, with an ASCII letter, a digit or one of `_.:-`, read up to the first character that isn't one; a header with none names no charset. Only an HTML page whose header names no charset is read by its `<meta>`, as HTML's own search finds one in its first 4096 bytes: a `<meta>` naming a label the standard doesn't list is passed over, and the search goes on; one naming UTF-16 is read as UTF-8, and x-user-defined as windows-1252, as HTML says. A page it can't read as text, one with no byte order mark whose header names a charset the standard doesn't list, or whose header or `<meta>` names a label the standard reads as one replacement character (`iso-2022-kr`), one whose bytes aren't valid in its charset, one whose server names no content type and whose bytes aren't clearly an HTML page (starting with `<!doctype html>` or `<html>`) or plain text, or read differently in the charset they name than in UTF-8, or one with no text in it (built by JavaScript), it refuses, and writes nothing.

**The fingerprint file** holds no text: its first line is `url: <link>`, then one line per paragraph of the page as fetched, its position and the SHA-256 of its text, before anything is left out. `WF research fingerprint` writes it; never change a hash by hand. An example, `docs/research/booking-ahead/sources/booking-help.fingerprints`:

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

It refuses a note whose layout breaks the rules above (a key-source line it can't read, a fingerprint file in the topic's folder that no key-source line names, a file or folder there it can't read, `## Key sources` twice or inside a code fence, a path outside the topic's folder, links that don't agree, or a saved copy whose paragraphs don't match its fingerprints), naming what to fix. It spends no model tokens, and writes nothing.

**The mark.** A claim still wrong after the look at a fix gets the mark ` **(unconfirmed)**`, exactly that text, with its leading space, added at the end of the line that holds the claim. For example:

```markdown
Cancelling at least 2 hours before a booking gives a full refund (paragraph 4). **(unconfirmed)**
```

## 2. The stakes record

When a feature's stakes are judged, the judgement is recorded in one comment: one readable line starting `Stakes: `, a blank line, then the stakes marker and the agents' marker, each on a line of its own. It goes on the item's issue when the study is skipped, and on the research issue when it runs. Before judging, read the earlier judgements, for similar work: `WF research stakes --fetch` lists every stakes record, one per line, in the order given (as GitHub gives them, oldest first), each with its issue's number, the comment's date and the issue's title.

An example, a comment on issue #42:

```markdown
Stakes: touches payments. Recommended: study. Owner chose: skip, because the deposit is the fixed fee we already take.

<!-- workflow:stakes -->
<!-- workflow:agent -->
```

The stakes line is one line. `WF research stakes` lists it and the issue's title with control characters and the profile's sensitive patterns left out, and a line or title past 1,000 characters cut. Write the marker exactly as shown, and nothing else in the comment: a comment with a second stakes line or a second marker, a token record, or either line inside a code fence isn't read.

## 3. The token record

When a study ends, add up each sub-agent's reported token total and post the total on the research issue, in one comment: one readable line saying that the main session's own share isn't counted, a blank line, then the token marker and the agents' marker, each on a line of its own. The marker says whether it was a full study (`study=full`) or a second study (`study=second`: "research it ourselves" for a finding that needs a professional), how many sub-agents ran (`agents=`) and their total (`total=`), each count in digits alone, with no leading zero. Write it exactly as shown, and nothing else in the comment: a comment with a second token marker, a stakes record, or the marker inside a code fence isn't read.

An example, a comment on research issue #43:

```markdown
Tokens: 1,180,000 across 11 agents, each sub-agent's reported total added up. The main session's own share isn't counted.

<!-- workflow:tokens study=full agents=11 total=1180000 -->
<!-- workflow:agent -->
```

A second study's, on its own research issue, #44:

```markdown
Tokens: 240,000 across 4 agents, each sub-agent's reported total added up. The main session's own share isn't counted.

<!-- workflow:tokens study=second agents=4 total=240000 -->
<!-- workflow:agent -->
```

**The size shown.** When a study is offered, show its size from `WF research estimate --fetch`: how many agents it will run and a rough token count ("about 11 agents, roughly 1.2M tokens"). It averages the past full studies' token records, one per research issue (the last one given), never a second study's; give `--agents N` when you know how many agents this one will run. Before there are any, it counts the panel at its largest, 12 agents, at the per-agent figure, 80,000 tokens per agent, and says it isn't learned yet. That figure is approximate: a trial run of the panel's agents set it, and the sandbox study's per-agent average replaces it. Nothing caps a study, and its size is never shown as money.

**Which comments count.** For both records, only comments carrying the agents' marker, posted by an account with write access, count, as hand-off comments do. Others with a stakes or token marker are left out, and standard error says how many. `--fetch` reads the issues, their comments and those accounts' permissions with `gh`; without it, give them as files: `--comments F --permissions F` (any shape `WF merge-check` takes them in), and `--issues F` for the titles. Both commands spend no model tokens, and write nothing.

## 4. A study, from the intake to the verdict

A study researches the people and the problem before grilling: who has it, what they use today, what shows the need, what would make it not worth building, and how we'd know it worked. Whether to run one is the owner's choice, a routing choice recorded in the stakes record (section 2), offered with the study's size (section 3). Once the owner chooses to run it, it goes in this order, as the flow's "Research" section gives it:

1. the research issue (section 5);
2. the intake (section 6);
3. the panel (section 7) and its ranked questions (section 8);
4. the note, in a research pull request of its own (section 9);
5. the research check and the look (section 10);
6. the verdict (section 11), then closing (section 12), with the token record (section 3).

Grilling, still uncapped, comes after the verdict, never before it, and starts from the study's findings and its ranked questions. For a new project on a map, the intake and the panel run before charting's first step, and the research issue is linked from the map's Notes, never made one of the map's children (map tickets carry only `wayfinder:` labels). Every file and post of a study follows the sensitive-data rule (section 13).

## 5. The research issue

**Filed before the intake,** as soon as the owner chooses to run the study: a GitHub issue labelled `research`, titled with the study's question ("Research: should the booking page take a deposit?"). It tracks the question, the discussion (the intake's rounds and the routing lines) and the verdict. The stakes record for a study that runs goes on it (section 2). Link it from the item's issue at once, in a comment there ("Study under way: #43"). A skipped study has no research issue and no intake.

**The label.** Before filing the first research issue in a project, look for the `research` label (`gh api repos/<repo>/labels/research`). When it's missing (a project set up before set-up created it), create it first (`gh api repos/<repo>/labels -f name=research -f description="Tracks research notes: a study's, a fact note's, or a note found wrong"`), then file the issue. When it's there, leave it as it is.

**A map's Destination item** has no issue of its own. Every record that would go on the item's issue goes in a comment on the map naming the item, as the item's rounds do: the stakes line (section 2), the research issue's link and the routing lines (the flow's "Decision questions"). The verdict's **Stop** moves the item to the map's Out of scope, with the verdict linked, in place of closing an issue. This is the one rule for a Destination item: offering a study, a finding that needs a professional and the source check all follow it.

## 6. The intake

The intake frames the study: who it's for, what problem, what success looks like, and any hard limits. It has no question cap: it ends once the study is framed, never at a count of questions.

- Its questions are decision questions (the flow's "Decision questions"): each with its recommendation and evidence, checked before each round by `planning-checker`, and posted on the research issue as soon as it's answered, each answer quoted word for word and tagged. Of the checks, it gets only the one before each round: no end check or re-read.
- A question the intake doesn't ask goes to the panel (into the gatherer's or the question writer's brief) or to grilling, and the intake's last post lists each with where it went. None is dropped.

## 7. The panel

The panel does the study's research. Every member is a fresh agent, started with the Agent tool, and each sees only what its role needs:

| Role | How many | Agent | What it sees |
|---|---|---|---|
| Evidence gatherer | one | general-purpose, with the web | the intake's framing |
| Question writer | one | general-purpose | the intake's framing |
| Persona | 5 to 8 | `research-persona`, with no tools | its own brief and the questions, nothing else |
| Synthesizer | one | general-purpose | the gatherer's findings, the briefs, the questions and every persona's answers |
| Validator | one | `research-checker`, read-only | the findings, the briefs, the answers, the saved copies, and what the owner brought in |

- **The evidence gatherer** collects real public evidence about the people and the problem. It saves each source it cites in the topic's folder: a key source with its fingerprints, as "Saving a key source" says (section 1); any other cited source as a saved copy in the same layout, with no fingerprint file. It marks the key sources its findings rest on, which alone get fingerprints. It then writes a brief for each persona, citing the evidence: a made-up person, what they do today, and what people like them have said or done.
- **The question writer** writes open, neutral questions: none answered by yes or no, none assuming the product is wanted, none leading to an answer. It covers what the intake left to the panel.
- **The personas,** 5 to 8 `research-persona` agents. One is a skeptic, one is an edge case, and one would never use the product (the non-user); the brief names each role. Each gets only its own brief and the questions, in its prompt: never another persona's brief or answers, the study's hopes or a recommendation. Start them together, so none waits on another's answers. The skeptic also lists the questions nobody asked.
- **The synthesizer** reports the themes, the disagreements, the surprises and the questions nobody asked (the skeptic's and its own). Every persona agreeing is a warning, not confirmation: it says so, and asks why (briefs too alike, a leading question).
- **The validator,** a `research-checker`, labels each finding with one of three labels, reading the saved copies:
  - *simulated*: it rests only on the personas' answers or the panel's reasoning;
  - *observed (public source)*: a saved copy says it, named with its paragraph;
  - *observed (real person)*: a real person said or did it. A finding gets it only when the owner brings it in (an answer from someone they asked, their own sales figures), since the kit gathers no real people's answers itself.

Keep the persona briefs and each persona's answers (its transcript) in the topic's folder, beside the note (`briefs/<n>.md`, `transcripts/<n>.md`). Note each sub-agent's reported token total as it finishes, for the token record (section 3).

## 8. The ranked questions

The study lists every question a real person or a real test would most change, most important first: the findings labelled *simulated* that the verdict or the build would rest on, the disagreements, and the questions nobody asked. There is no cap on how many. All of them go in the note, under `## Ranked questions`, and all are carried into grilling (and into the prototype, on **Prototype first**), so the real-world checks start with the first.

## 9. The note

The session writes the note from the panel's work, in `docs/research/<topic>/note.md`, in the layout of section 1: its header (`Status: current`, `Last checked:` today, `Issue:` the research issue), the findings, each with its label and its source, the synthesizer's themes, disagreements and surprises, the ranked questions (section 8) and the key sources. It goes on a branch named `claude/research-<topic>`, in a research pull request of its own holding only files under `docs/research/` (the flow's "Research"), whose body names the research issue.

**A finding that needs a professional** (the law, a regulation, a safety rule): the owner's professional choice for it is made before the research check, so its open mark, questionnaire or link is in what the check reads. Only what rests on the professional's answer waits for it; the verdict and grilling go ahead.

## 10. The research check and the look

As the flow's "Research" section says, every research pull request gets the research check and, when it isn't clean, the look, one pass each, never rounds until clean:

1. **The research check:** one fresh `research-checker` reads each claim of the note against its source's saved copy, facts only. It posts nothing, so the session posts one comment on the pull request: first the research record, `WF review-record --kind research --round 1 --commit <sha> --reviewers research --clean` (or `--not-clean`), naming the commit it read, then the claims it found wrong, listed. The record comes first, since the record reader stops at the first code fence and a claim may quote one.
2. **The look,** short for the look at a fix, only when the research check wasn't clean: fix the claims it listed, then a fresh `research-checker` reads the lines changed since the research check and each listed claim. A listed claim whose line didn't change counts as still wrong. Post its comment the same way, with `--round 2`.
3. **The mark:** a claim the look finds still wrong gets the mark (section 1) at the end of its line, and there is no further round. After the look, only marks may change.

How these records count at merge is flow §4 item 4's.

## 11. The verdict

Once the research pull request is ready to merge (after the look, where one was needed), ask the verdict: one decision question on the research issue, posted word for word and tagged (the flow's "Decision questions"). It has three options, and each says what it leads to:

- **Build it:** the item goes on to its spec or its map, and grilling starts from the findings and the ranked questions.
- **Prototype first:** the `prototype` skill comes next, then grilling, with the findings and the ranked questions carried into both.
- **Stop:** the item's issue is closed as not planned, linking the verdict (a map's Destination item moves to the map's Out of scope instead: section 5). Nothing is built, and stopping is a valid, recorded outcome.

The verdict is recorded on the research issue only, never in the note, so the note doesn't change after its records.

## 12. Closing

The research issue closes at the verdict, once the token record (section 3) is posted on it.

- A finding waiting on a professional keeps its own owner task, open.
- A finding left open stays marked "open" in the note, and goes into the spec's open questions if a spec follows.
- No other issues are filed.

## 13. Sensitive data

Notes, persona briefs, transcripts and saved copies follow `profile.md`'s rule, and so do the research issue's posts:
- names and personal details are left out, and marked as left out (`[left out]`), and sources are cited by link;
- personas are made up: no real person's name or details, even in a brief citing a real source;
- saved copies also leave out anything matching the profile's `[sensitive].patterns`, marked as left out, since a commit is never checked against them (`WF research fingerprint` does this; personal details are yours to leave out, section 1).
