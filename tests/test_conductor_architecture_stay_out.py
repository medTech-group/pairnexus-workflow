"""#613 (spec #611, answer 18 on #603): the conductor never puts
`docs/architecture/` on a ticket's stay-out list.

Seam 3, the kit's text: the conductor's `alongside` row, and the changelog
note under `## Unreleased`."""

import re

from changelog_notes import since_0110
from conftest import KIT


def _flat(text):
    return re.sub(r"\s+", " ", text)


def _alongside_row():
    text = (KIT / "skills/conductor/SKILL.md").read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("| `alongside` |")]
    assert len(rows) == 1, rows
    return rows[0]


def test_the_alongside_row_still_says_what_a_ticket_stays_out_of():
    row = _alongside_row()
    assert "The tickets running now and their areas" in row
    assert "what this one stays out of" in row


def test_the_alongside_row_never_puts_the_architecture_on_a_stay_out_list():
    row = _flat(_alongside_row())
    assert "`docs/architecture/` is never on that stay-out list" in row
    # Even where another ticket's area globs match it (a `docs/*.md` area, with
    # `*` crossing `/`, matches every page): its lines are the change's own.
    assert "even when another ticket's area matches it" in row
    assert "always the change's own" in row


def test_the_changelog_says_so_under_unreleased():
    unreleased = _flat(since_0110().split("\n## 0.1.22\n", 1)[0])
    assert "(#613, part of spec #611)" in unreleased
    note = unreleased.split("(#613, part of spec #611)", 1)[1].split("**For projects updating:**", 1)[0]
    assert "`alongside`" in note
    assert "`docs/architecture/`" in note
    assert "stay-out list" in note
