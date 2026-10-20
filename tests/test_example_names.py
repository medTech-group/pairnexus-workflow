"""The names test (#99, part of #37): examples are everyday ones, so a reader
sees their own project in them. pair-drop, PAIR's own project, is named only in
the README's "Where it came from"; patient data only among the sensitive-data
examples; the health examples the sweep removed, nowhere.

It reads what a project receives (`vendor.plan`), so new skills, docs and
templates are read as they land, plus the README and the quickstart, which
aren't vendored. It doesn't read `.github/`, `.claude/skills/release-gate/`
(neither ships), the tests, Matt Pocock's skills (`vendor.plan(KIT, None)`
leaves them out), or the history files `CHANGELOG.md`, `docs/spike.md` and
`docs/proposal.md`, which keep their names.
"""

import re
from pathlib import Path

from workflow import vendor

KIT = Path(__file__).resolve().parents[1]

# Read by name: neither ships to a project (the quickstart is in SKIP_DOCS).
BY_NAME = ["README.md", "docs/quickstart.md"]
# History, which keeps its names. vendor.plan leaves them out already; listed
# so that a change there can't bring them in.
HISTORY = {"CHANGELOG.md", "docs/spike.md", "docs/proposal.md"}

# Each rule: the words, and the only places they may appear. A place is
# (file, the section it sits in, how its line starts): the section is a
# heading the line sits under, at any depth ("" for anywhere in the file).
# A new place needs a deliberate change here, settled with the owner (#37).
RULES = {
    "pair-drop is named only in the README's \"Where it came from\"": (
        re.compile(r"pair[-_ ]?drop", re.I),
        [("README.md", "## Where it came from", "")],
    ),
    "patient data is only one sensitive-data example among others": (
        re.compile(r"\bpatients?\b", re.I),
        [
            ("README.md", "### Step 1. Ask Claude to set the repository up", "| Sensitive data |"),
            ("docs/profile.md", "## `[sensitive]`", "| `description` |"),
            ("templates/profile.md", "## Sensitive data", "- <!-- e.g."),
        ],
    ),
    "examples are everyday ones (a notes app, a shop, a booking page), never health ones": (
        re.compile(r"\b(?:clinic|medicine|refill)\w*", re.I),
        [],
    ),
}

_FENCE = re.compile(r"\s*(```|~~~)")
_HEADING = re.compile(r"(#{1,6}) \S")


def _read() -> dict[str, str]:
    files = {src.relative_to(KIT).as_posix() for src in vendor.plan(KIT, None).values()}
    files |= set(BY_NAME)
    texts = {}
    for rel in sorted(files - HISTORY):
        if rel.startswith((".github/", ".claude/skills/release-gate/", "tests/")):
            continue
        try:
            texts[rel] = (KIT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
    return texts


def _lines(text: str):
    """(line number, line, the headings it sits under), Markdown headings
    outside code fences only."""
    stack: list[tuple[int, str]] = []
    fenced = False
    for n, line in enumerate(text.splitlines(), 1):
        if _FENCE.match(line):
            fenced = not fenced
        elif not fenced and (m := _HEADING.match(line)):
            level = len(m.group(1))
            stack = [h for h in stack if h[0] < level] + [(level, line.rstrip())]
        yield n, line, {h for _, h in stack}


def _misplaced(texts: dict[str, str]) -> list[str]:
    found = []
    for rel, text in texts.items():
        for n, line, headings in _lines(text):
            for rule, (words, places) in RULES.items():
                for m in words.finditer(line):
                    if any(rel == f and (not s or s in headings) and line.lstrip().startswith(p)
                           for f, s, p in places):
                        continue
                    found.append(f"{rel}:{n}: \"{m.group()}\": {rule}")
    return found


def test_each_word_appears_only_in_its_allowed_places():
    found = _misplaced(_read())
    assert not found, (
        "A word appears outside its allowed places. Use an everyday example instead (a notes app, "
        "a shop, a booking page; CONTRIBUTING.md's \"Writing\"). A new place for one is a deliberate "
        "change to RULES in tests/test_example_names.py, settled with the owner:\n" + "\n".join(found)
    )


def test_it_reads_what_ships_plus_the_readme_and_the_quickstart():
    texts = _read()
    assert {"README.md", "docs/quickstart.md", "docs/profile.md", "templates/profile.md",
            "templates/profile.toml", "skills/start/SKILL.md", "docs/glossary.md"} <= set(texts)
    assert not any(rel.startswith((".github/", "tests/", ".claude/")) for rel in texts)
    assert not HISTORY & set(texts)


def test_each_allowed_place_exists_and_holds_its_word():
    texts = _read()
    for rule, (words, places) in RULES.items():
        for f, section, prefix in places:
            held = [line for _, line, headings in _lines(texts[f])
                    if (not section or section in headings) and line.lstrip().startswith(prefix)
                    and words.search(line)]
            assert held, f"{f}: no line under {section!r} starting {prefix!r} names the word for: {rule}"


def test_a_word_anywhere_else_fails_naming_the_file_and_the_rule():
    # A "#" line inside a code fence isn't a heading, so it doesn't end the section.
    readme = ("# Kit\n\n## Using it\n\nOur clinic app.\n\n## Where it came from\n\n```\n# not a heading\n```\n\n"
              "pair-drop's run.\n\n## Licence\n\npairdrop\n")
    profile = "## `[sensitive]`\n\n| `description` | patients' names |\n\n## Other\n\n| `description` | patients |\n"
    found = _misplaced({"README.md": readme, "docs/profile.md": profile, "docs/x.md": "From pair-drop.\n"})
    assert found == [
        'README.md:5: "clinic": examples are everyday ones (a notes app, a shop, a booking page), never health ones',
        'README.md:17: "pairdrop": pair-drop is named only in the README\'s "Where it came from"',
        'docs/profile.md:7: "patients": patient data is only one sensitive-data example among others',
        'docs/x.md:1: "pair-drop": pair-drop is named only in the README\'s "Where it came from"',
    ]


def test_the_readmes_sensitive_data_row_lists_patients_names_among_others():
    row = next(l for l in (KIT / "README.md").read_text().splitlines() if l.startswith("| Sensitive data |"))
    for example in ("patients' names", "phone numbers", "payment details", "children's names"):
        assert example in row, example


def test_the_other_two_sensitive_data_examples_list_patients_names_among_others():
    row = next(l for l in (KIT / "docs/profile.md").read_text().splitlines() if l.startswith("| `description` |"))
    example = next(l for l in (KIT / "templates/profile.md").read_text().splitlines() if l.startswith("- <!-- e.g."))
    for text in (row, example):
        for words in ("patients' names", "phone numbers", "payment details", "children's names"):
            assert words in text, (words, text)


def test_the_profile_templates_area_example_names_none_of_pair_drops_paths():
    t = (KIT / "templates/profile.toml").read_text()
    assert "backend/messages.py" not in t and "features/sharing" not in t
    areas = t.split("\n[areas]\n", 1)[1].split("\n[", 1)[0]
    assert re.search(r'^# \w+ = \["', areas, re.M), "the [areas] section keeps an example"


def test_the_readmes_walkthroughs_use_everyday_projects_never_the_starter():
    readme = (KIT / "README.md").read_text()
    for example in ("notes app", "a small shop", "booking page"):
        assert example in readme.lower(), example
    walkthroughs = readme.split("**What happens with your first message:**", 1)[1].split("### Keeping it up to date", 1)[0]
    assert "the starter" not in walkthroughs.lower()


def test_contributings_writing_section_names_the_rule_and_the_test():
    t = (KIT / "CONTRIBUTING.md").read_text()
    writing = t.split("**Writing.**", 1)[1].split("**The glossary.**", 1)[0]
    for words in ("everyday", "a notes app", "Where it came from", "pair-drop", "sensitive-data",
                  "tests/test_example_names.py"):
        assert words in writing, words
