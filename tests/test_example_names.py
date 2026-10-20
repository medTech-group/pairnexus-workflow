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
from typing import NamedTuple

from changelog_notes import since_0110
from conftest import KIT
from workflow import vendor

# Read by name: neither ships to a project (the quickstart is in SKIP_DOCS).
BY_NAME = ["README.md", "docs/quickstart.md"]
# Never read: history keeps its names, and the rest never ships. vendor.plan
# leaves them all out already; listed so that a change there can't bring one in.
NOT_READ = ("CHANGELOG.md", "docs/spike.md", "docs/proposal.md", ".github/", ".claude/skills/release-gate/", "tests/")
# Shipped files that aren't text, and so aren't read.
BINARY = (".png", ".jpg", ".gif", ".ico", ".pdf", ".zip")

SENSITIVE_EXAMPLES = ("patients' names", "phone numbers", "payment details", "children's names")


class Place(NamedTuple):
    """Where a word may appear: a file, a heading its line sits under (at any
    depth; "" for anywhere in the file), and how the line starts."""
    file: str
    section: str
    starts: str

    def holds(self, rel: str, line: str, headings: set[str]) -> bool:
        return (rel == self.file and (not self.section or self.section in headings)
                and line.lstrip().startswith(self.starts))


# Each rule: the words, and the only places they may appear. Words are matched
# in any case and inside identifiers (`patient_id`, `autoRefill`), but not
# inside other words ("impatient", "repair drops").
# A new place needs a deliberate change here, settled with the owner (#37).
RULES = {
    "pair-drop is named only in the README's \"Where it came from\"": (
        re.compile(r"(?<![a-z])pair[-_ ‐‑–]?drop", re.I),
        [Place("README.md", "## Where it came from", "")],
    ),
    "patient data is only one sensitive-data example among others": (
        re.compile(r"(?<![a-z])patient\w*", re.I),
        [
            Place("README.md", "### Step 1. Ask Claude to set the repository up", "| Sensitive data |"),
            Place("docs/profile.md", "## `[sensitive]`", "| `description` |"),
            Place("templates/profile.md", "## Sensitive data", "- <!-- e.g."),
        ],
    ),
    "examples are everyday ones (a notes app, a shop, a booking page), never health examples": (
        re.compile(r"(?:clinic|medicine|refill)\w*", re.I),
        [],
    ),
}

_FENCE = re.compile(r"\s*(```|~~~)")
_HEADING = re.compile(r"(#{1,6}) \S")
_SETEXT = re.compile(r"(=+|-+)\s*$")


def _texts() -> dict[str, str]:
    """What the test reads: relative path -> text."""
    files = {src.relative_to(KIT).as_posix() for src in vendor.plan(KIT, None).values()}
    texts = {}
    for rel in sorted(files | set(BY_NAME)):
        if rel.startswith(NOT_READ) or rel.endswith(BINARY):
            continue
        texts[rel] = (KIT / rel).read_text(encoding="utf-8")  # a text file that won't decode fails loudly
    return texts


def _lines(text: str):
    """(line number, line, the headings it sits under), counting ATX and setext
    headings outside code fences."""
    lines = text.splitlines()
    stack: list[tuple[int, str]] = []
    fenced = False
    for i, line in enumerate(lines):
        heading = None
        if _FENCE.match(line):
            fenced = not fenced
        elif not fenced and (m := _HEADING.match(line)):
            heading = len(m.group(1)), line.rstrip()
        elif (not fenced and line.strip() and not line.startswith(("|", " ", "\t"))
              and i + 1 < len(lines) and (u := _SETEXT.match(lines[i + 1]))):
            level = 1 if u.group(1)[0] == "=" else 2
            heading = level, f"{'#' * level} {line.strip()}"
        if heading:
            stack = [h for h in stack if h[0] < heading[0]] + [heading]
        yield i + 1, line, {h for _, h in stack}


def _misplaced(texts: dict[str, str]) -> list[str]:
    found = []
    for rel, text in texts.items():
        for n, line, headings in _lines(text):
            for rule, (words, places) in RULES.items():
                for m in words.finditer(line):
                    if not any(p.holds(rel, line, headings) for p in places):
                        found.append(f"{rel}:{n}: \"{m.group()}\": {rule}")
    return found


def _line(rel: str, starts: str) -> str:
    return next(l for l in (KIT / rel).read_text(encoding="utf-8").splitlines() if l.startswith(starts))


def test_each_word_appears_only_in_its_allowed_places():
    found = _misplaced(_texts())
    assert not found, (
        "A word appears outside its allowed places. Use an everyday example instead (a notes app, "
        "a shop, a booking page; CONTRIBUTING.md's \"Writing\"). A new place for one is a deliberate "
        "change to RULES in tests/test_example_names.py, settled with the owner:\n" + "\n".join(found)
    )


def test_it_reads_what_ships_plus_the_readme_and_the_quickstart():
    texts = _texts()
    shipped = {src.relative_to(KIT).as_posix() for src in vendor.plan(KIT, None).values()}
    assert set(texts) == {rel for rel in shipped | set(BY_NAME) if not rel.endswith(BINARY)}
    assert {"README.md", "docs/quickstart.md", "docs/glossary.md", "skills/start/SKILL.md"} <= set(texts)


def test_each_allowed_place_exists_and_holds_its_word():
    texts = _texts()
    for rule, (words, places) in RULES.items():
        for p in places:
            assert any(p.holds(p.file, line, headings) and words.search(line)
                       for _, line, headings in _lines(texts[p.file])), f"{p} no longer names its word: {rule}"


def test_a_word_anywhere_else_fails_naming_the_file_and_the_rule():
    # A "#" line inside a code fence isn't a heading, so it doesn't end the
    # section; a setext heading does.
    readme = (
        "# Kit\n\n## Using it\n\nOur Clinicians' app, with autoRefill.\n\n"
        "## Where it came from\n\n```\n# not a heading\n```\n\npair-drop's run, PairDrop.\n\n"
        "Licence\n-------\n\npair_drop\n\n```\nrefill\n```\n\nImpatient? The repair drops nothing.\n"
    )
    profile = ("## `[sensitive]`\n\n| `description` | patients' names |\n\n## Other\n\n"
               "| `description` | Patients |\n\npatient_id\n")
    found = _misplaced({"README.md": readme, "docs/profile.md": profile, "docs/x.md": "From pair‑drop.\n"})
    health = "examples are everyday ones (a notes app, a shop, a booking page), never health examples"
    pair_drop = "pair-drop is named only in the README's \"Where it came from\""
    patient = "patient data is only one sensitive-data example among others"
    assert found == [
        f'README.md:5: "Clinicians": {health}',
        f'README.md:5: "Refill": {health}',
        f'README.md:18: "pair_drop": {pair_drop}',
        f'README.md:21: "refill": {health}',
        f'docs/profile.md:7: "Patients": {patient}',
        f'docs/profile.md:9: "patient_id": {patient}',
        f'docs/x.md:1: "pair‑drop": {pair_drop}',
    ]


def test_the_three_sensitive_data_examples_list_patients_names_among_others():
    for text in (_line("README.md", "| Sensitive data |"), _line("docs/profile.md", "| `description` |"),
                 _line("templates/profile.md", "- <!-- e.g.")):
        for example in SENSITIVE_EXAMPLES:
            assert example in text, (example, text)


def test_the_profile_templates_area_example_names_none_of_pair_drops_paths():
    t = (KIT / "templates/profile.toml").read_text(encoding="utf-8")
    assert "backend/messages.py" not in t and "features/sharing" not in t
    areas = t.split("\n[areas]\n", 1)[1].split("\n[", 1)[0]
    assert re.search(r'^# \w+ = \["', areas, re.M), "the [areas] section keeps an example"


def test_the_walkthroughs_use_everyday_projects_never_the_starter():
    # "the starter" (#40's starter template) doesn't exist yet: examples say "a notes app".
    readme = (KIT / "README.md").read_text(encoding="utf-8")
    for project in ("notes app", "a small shop", "booking page"):
        assert project in readme.lower(), project
    walkthroughs = readme.split("**What happens with your first message:**", 1)[1].split("### Keeping it up to date", 1)[0]
    start_example = _line("skills/start/SKILL.md", "Tell the person what matters")
    for text in (walkthroughs, start_example):
        assert "the starter" not in text.lower()
    assert "booking" in start_example


def test_contributings_writing_section_names_the_rule_and_the_test():
    t = (KIT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    writing = t.split("**Writing.**", 1)[1].split("**The glossary.**", 1)[0]
    for words in ("everyday examples", "a notes app", "Where it came from", "pair-drop", "sensitive-data",
                  "tests/test_example_names.py"):
        assert words in writing, words


def test_the_changelog_notes_it_without_a_version_bump():
    assert "(#99, part of #37)" in since_0110()
    released = re.search(r"^## (\d+\.\d+\.\d+)", (KIT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M).group(1)
    assert (KIT / "VERSION").read_text(encoding="utf-8").strip() == released
