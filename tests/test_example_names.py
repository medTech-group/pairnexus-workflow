"""The names test (#99, part of #37): examples are everyday ones, so a reader
sees their own project in them. pair-drop, PAIR's own project, is named only in
the README's "Where it came from"; patient data only among the sensitive-data
examples; the removed health examples, nowhere.

It reads what a project receives (`vendor.plan`), so new skills, docs and
templates are read as they land, plus the README and the quickstart, which
aren't vendored. It doesn't read `.github/`, `.claude/skills/release-gate/`
(neither ships), the tests, Matt Pocock's skills (`vendor.plan(KIT, None)`
leaves them out), or the history files `CHANGELOG.md`, `docs/spike.md` and
`docs/proposal.md`, which keep their names.
"""

import re
import sys
from typing import NamedTuple

import pytest

from changelog_notes import since_0110
from conftest import KIT
from workflow import vendor

# Read by name: neither ships to a project (the quickstart is in SKIP_DOCS).
BY_NAME = ["README.md", "docs/quickstart.md"]
# Never read: history keeps its names, and the rest never ships. vendor.plan
# leaves them all out; were it to ship one, test_it_reads_… fails, so the change
# is seen and this list decided again.
NOT_READ = ("CHANGELOG.md", "docs/spike.md", "docs/proposal.md", ".github/", ".claude/skills/release-gate/", "tests/")
# Shipped files that aren't text, and so aren't read (compared in lower case).
BINARY = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".ttf", ".woff", ".woff2", ".ds_store")

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


def _name(first: str, rest: str) -> re.Pattern:
    """A name in any case, also inside identifiers (`patient_id`, `isPatient`,
    `FHIRPatient`), but not inside other words ("impatient", "repair drops").
    Run together in capitals, a name can't be told from a word (`MYPATIENT`,
    `IMPATIENT`), so neither is matched."""
    upper = first.upper()
    return re.compile(rf"(?:(?<![A-Za-z])(?i:{first})|(?<=[a-z]){upper}|(?<=[A-Z]){upper}(?=[a-z]))(?i:{rest})\w*")


PAIR_DROP = "pair-drop is named only in the README's \"Where it came from\""
PATIENT = "patient data is only one sensitive-data example among others"
HEALTH = "examples are everyday ones (a notes app, a shop, a booking page), never health examples"

# Each rule: the words, and the only places they may appear. pair-drop and
# patient are matched as names (`_name`); the health words anywhere, even
# inside other words ("polyclinic", `refill_rate`).
# A new place needs a deliberate change here, settled with the owner (#37).
RULES = {
    PAIR_DROP: (
        _name("p", "air[-_ ‐‑–]?drop"),
        [Place("README.md", "## Where it came from", "")],
    ),
    PATIENT: (
        _name("p", "atient"),
        [
            Place("README.md", "### Step 1. Ask Claude to set the repository up", "| Sensitive data |"),
            Place("docs/profile.md", "## `[sensitive]`", "| `description` |"),
            Place("templates/profile.md", "## Sensitive data", "- <!-- e.g."),
        ],
    ),
    HEALTH: (
        re.compile(r"(?:clinic|medicine|refill)\w*", re.I),
        [],
    ),
}

_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")
_HEADING = re.compile(r" {0,3}(#{1,6}) \S")
_SETEXT = re.compile(r" {0,3}(=+|-+)\s*$")
# A line that can't be a setext heading's text: a list item (at any depth), a
# quote, a table row, or HTML (a `---` under an HTML comment is a rule).
_NOT_SETEXT = re.compile(r"\s*(?:(?:[-*+]|\d{1,9}[.)])(?:\s|$)|[>|<])")


def _text(rel: str) -> str:
    try:
        return (KIT / rel).read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        pytest.fail(f"{rel} isn't utf-8 text ({e}): add its suffix to BINARY if it is binary")


def _texts() -> dict[str, str]:
    """What the test reads: relative path -> text."""
    files = {src.relative_to(KIT).as_posix() for src in vendor.plan(KIT, None).values()}
    return {rel: _text(rel) for rel in sorted(files | set(BY_NAME))
            if not rel.startswith(NOT_READ) and not rel.lower().endswith(BINARY)}


def _lines(text: str):
    """(line number, line, the headings it sits under), counting ATX and setext
    headings outside code fences."""
    lines = text.splitlines()
    stack: list[tuple[int, str]] = []
    fence = ""  # the open fence; it closes on the same character, at least as long
    for i, line in enumerate(lines):
        heading = None
        if f := _FENCE.match(line):
            if not fence:
                # a backtick fence's info string has no backtick: "```x` and `y`" is text
                if not (f.group(1)[0] == "`" and "`" in line[f.end():]):
                    fence = f.group(1)
            elif f.group(1)[0] == fence[0] and len(f.group(1)) >= len(fence) and not line[f.end():].strip():
                fence = ""
        elif fence:
            pass
        elif m := _HEADING.match(line):
            heading = len(m.group(1)), line.strip()
        elif (line.strip() and not _NOT_SETEXT.match(line)
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
    return next(l for l in _text(rel).splitlines() if l.lstrip().startswith(starts))


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
    assert set(texts) == {rel for rel in shipped | set(BY_NAME) if not rel.lower().endswith(BINARY)}
    assert {"README.md", "docs/quickstart.md", "docs/glossary.md", "skills/start/SKILL.md"} <= set(texts)


def test_each_allowed_place_exists_and_holds_its_word():
    texts = _texts()
    for rule, (words, places) in RULES.items():
        for p in places:
            assert any(p.holds(p.file, line, headings) and words.search(line)
                       for _, line, headings in _lines(texts[p.file])), f"{p} no longer names its word: {rule}"


def test_a_word_anywhere_else_fails_naming_the_file_and_the_rule():
    # A "#" line inside a code fence isn't a heading, so it doesn't end the
    # section; a setext heading does, and so does an indented one. A fence
    # closes only on its own character, at least as long, with nothing after.
    readme = (
        "# Kit\n\n## Using it\n\nOur Clinicians' app, with autoRefill.\n\n"
        "## Where it came from\n\n````\n```\n# not a heading\n````\n\npair-drop's run, PairDrop.\n\n"
        "Licence\n-------\n\npair_drop, usePairDrop\n\n```\nrefill\n```\n\nImpatient? The repair drops nothing.\n\n"
        "## Where it came from\n\n  ## Thanks\n\npairdrop\n\n"
        "## Where it came from\n\n~~~\n```\n## Not a heading\n~~~\n\n```python\n```js\n## Nor this\n```  \n\npair-drop\n\n"
        "```x` is text, so this is a heading:\n\n## Licence\n\npair-drop\n\n"
        "## Where it came from\n\n*Licence*\n---\n\npair-drop\n\n"
        "## Where it came from\n\n- a list item\n---\n\n+ x\n---\n\n1. x\n---\n\n> x\n---\n\n| a |\n---\n\n"
        "    - nested\n---\n\n<!-- note -->\n---\n\npair-drop\n"
    )
    profile = ("## `[sensitive]`\n\n| `description` | patients' names |\n\n## Other\n\n"
               "| `description` | Patients |\n\npatient_id, isPatient, FHIRPatient, MYPATIENT\n")
    found = _misplaced({"README.md": readme, "docs/profile.md": profile, "docs/x.md": "From pair‑drop.\n"})
    assert found == [
        f'README.md:5: "Clinicians": {HEALTH}',
        f'README.md:5: "Refill": {HEALTH}',
        f'README.md:19: "pair_drop": {PAIR_DROP}',
        f'README.md:19: "PairDrop": {PAIR_DROP}',
        f'README.md:22: "refill": {HEALTH}',
        f'README.md:31: "pairdrop": {PAIR_DROP}',
        f'README.md:51: "pair-drop": {PAIR_DROP}',
        f'README.md:58: "pair-drop": {PAIR_DROP}',
        f'docs/profile.md:7: "Patients": {PATIENT}',
        f'docs/profile.md:9: "patient_id": {PATIENT}',
        f'docs/profile.md:9: "Patient": {PATIENT}',
        f'docs/profile.md:9: "Patient": {PATIENT}',
        f'docs/x.md:1: "pair‑drop": {PAIR_DROP}',
    ]


def test_a_shipped_file_that_isnt_utf8_fails_naming_itself(tmp_path, monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], "KIT", tmp_path)
    (tmp_path / "logo.bin").write_bytes(b"\x89PNG\xff")
    with pytest.raises(pytest.fail.Exception, match="logo.bin isn't utf-8 text"):
        _text("logo.bin")


def test_the_three_sensitive_data_examples_list_patients_names_among_others():
    _, places = RULES[PATIENT]
    assert len(places) == 3
    for p in places:
        text = _line(p.file, p.starts)
        for example in SENSITIVE_EXAMPLES:
            assert example in text, (example, text)


def test_the_profile_templates_area_example_names_none_of_pair_drops_paths():
    t = _text("templates/profile.toml")
    assert "backend/messages.py" not in t and "features/sharing" not in t
    areas = t.split("\n[areas]\n", 1)[1].split("\n[", 1)[0]
    assert re.search(r'^# \w+ = \["', areas, re.M), "the [areas] section keeps an example"


def test_the_walkthroughs_use_everyday_projects_never_the_starter():
    # "the starter" (#40's starter template) doesn't exist yet: examples say "a notes app".
    readme = _text("README.md")
    for project in ("notes app", "a small shop", "booking page"):
        assert project in readme.lower(), project
    walkthroughs = readme.split("**What happens with your first message:**", 1)[1].split("### Keeping it up to date", 1)[0]
    start_example = _line("skills/start/SKILL.md", "Tell the person what matters")
    for text in (walkthroughs, start_example):
        assert "the starter" not in text.lower()
    assert "booking" in start_example


def test_contributings_writing_section_names_the_rule_and_the_test():
    writing = _text("CONTRIBUTING.md").split("**Writing.**", 1)[1].split("**The glossary.**", 1)[0]
    for words in ("everyday examples", "a notes app", "Where it came from", "pair-drop", "sensitive-data",
                  "tests/test_example_names.py"):
        assert words in writing, words


def test_the_changelog_notes_it_without_a_version_bump():
    assert "(#99, part of #37)" in since_0110()
    released = re.search(r"^## (\d+\.\d+\.\d+)", _text("CHANGELOG.md"), re.M).group(1)
    assert _text("VERSION").strip() == released
