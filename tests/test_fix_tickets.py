"""#373: filing the three kinds of ticket (spec #412, "Reviews from the
second", "The circuit breaker", "Runs"; ADR 0001's exceptions): tickets to fix
old bugs, tickets to fix late findings and split tickets, filed by the ticket
session as `build-ticket` says, each with an `Area:` line, acceptance criteria
from the finding, the bar where it has one, the agent marker and the machine
line `<!-- workflow:fix-ticket from=<n> kind=old|late|split -->`. Read as the
kit's other text contracts are (prior art: tests/test_build_review_rule.py)."""

import re

from changelog_notes import since_0110
from conftest import KIT

BUILD = "skills/build-ticket/SKILL.md"
PANEL = "skills/review-panel/SKILL.md"
HEADING = "### Filing tickets to fix findings, and split tickets"
MACHINE = re.compile(r"^<!-- workflow:fix-ticket from=(<n>|\d+) kind=(old\|late\|split|old|late|split) -->$")


def _read(rel: str) -> str:
    return (KIT / rel).read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _between(text: str, start: str, end: str) -> str:
    assert start in text, f"has {start!r}"
    return text.split(start, 1)[1].split(end, 1)[0]


def _filing_raw() -> str:
    """The filing subsection of `build-ticket`, up to the next heading."""
    return re.split(r"\n#{2,3} ", _between(_read(BUILD), HEADING + "\n", "\n## 4."), maxsplit=1)[0]


def _filing() -> str:
    return _flat(_filing_raw())


def _body_list() -> str:
    return _flat(_between(_read(BUILD), "## 4. Open the pull request", "\n## 5."))


def test_the_filing_is_a_part_of_build_tickets_review_step():
    review = _between(_read(BUILD), "## 3. Review it", "\n## 4.")
    assert HEADING in review
    # The light and small reviews' paragraphs stay above it, unchanged in place.
    assert review.index("**A light review,**") < review.index(HEADING)
    assert review.index("**The small review,**") < review.index(HEADING)


def test_review_panel_points_to_it():
    s3 = _flat(_between(_read(PANEL), "## 3. After each round", "\n## 4."))
    assert "the way `build-ticket` files tickets to fix findings" in s3
    assert "tickets to fix findings" in HEADING


def test_the_three_kinds():
    text = _filing()
    assert "Under the rule (`review-panel` §10)" in text
    assert "nothing piles up as `needs-triage`" in text
    assert (
        "**old:** a finding marked a ticket to fix it about code the change neither touches nor reaches, "
        "or a written rule broken outside the change's own lines;"
    ) in text
    assert "**late:** a finding marked a ticket to fix it from the second review on, about lines already reviewed;" in text
    assert "**split:** a part that `WF merge-check` says to split out (`mechanism_repeats` with `next: split`)." in text


def test_when_each_is_filed():
    text = _filing()
    # Old and late: after the review, before its record, with the issue back in the findings file.
    assert (
        "**When.** An old or late one: after each review, once its findings file is written and before its record, "
        "so the record names it: put the issue's number in the finding's entry as `issue`."
    ) in text
    assert "A finding you doubt is filed too, as the reviewer marked it: your doubt goes in the findings table, never in the ticket." in text
    # A split: before the fixer takes the part out, so a restart never loses it.
    assert (
        "A split one: as soon as `WF merge-check` says to split, before a fresh fixer takes the part out of the pull request, "
        "so a restart never loses the ticket; the next review's findings file gives it as a `split` outcome with its issue."
    ) in text


def test_it_looks_for_an_open_one_first():
    text = _filing()
    assert "**Look first** for an open issue for the same failure (the same defect in the same place, however it is worded)" in text
    assert "`gh api -X GET search/issues -f q='repo:<repo> is:issue is:open in:body \"workflow:fix-ticket\"'`" in text
    assert "When there is one, file nothing: its number is the finding's `issue`" in text
    # A split looks for its own earlier filing, so a restarted session never files it twice.
    assert "For a split, an open ticket whose machine line says `from=` this ticket and `kind=split` for the same part is that one." in text


def test_the_tickets_parts():
    text = _filing()
    assert "A ready build ticket, labelled `ready-for-agent`, never `needs-triage`" in text
    assert "`Area: <name>`: the profile's `[areas]` area whose paths hold the lines it is about; a split one keeps this ticket's area;" in text
    assert "`## Acceptance criteria`: from the finding" in text
    assert "a split one gets the criteria that need the part, moved from this ticket word for word" in text
    assert "`## Bar`: this ticket's bar, copied, when it has one and the new ticket is in its area (a split one always copies it); otherwise none;" in text


def test_blocked_by_names_this_ticket_only_for_its_own_lines():
    text = _filing()
    assert (
        "`## Blocked by`: this ticket (`#<n>`) when the new one is about this pull request's own lines, "
        "whose code isn't on the base branch yet: every split one, and a late one on the change's own lines. "
        "Otherwise \"None\": every old one, and a late one on lines the change only reaches."
    ) in text


def test_the_machine_line_and_the_marker_close_the_body():
    raw = _filing_raw()
    fence = raw.split("```\n", 2)[1]
    lines = [l.strip() for l in fence.strip().splitlines()]
    assert lines == ["<!-- workflow:fix-ticket from=<n> kind=old|late|split -->", "<!-- workflow:agent -->"]
    assert MACHINE.match(lines[0])
    text = _filing()
    assert "`from` is this ticket's number, not its pull request's, written as digits alone; `kind` is one of `old`, `late` or `split`." in text
    # The findings file's split flag comes from the same line, read on the ticket being built.
    assert "When this ticket has such a line saying `kind=split`, each of its findings files sets `split: true` (`review-panel` §4)." in text


def test_the_machine_line_matches_what_findings_py_reads():
    # findings.py's docstring names the line the split flag is copied from.
    doc = _read("scripts/workflow/findings.py")
    assert "`<!-- workflow:fix-ticket … kind=split -->`" in doc
    # A filled-in line from the template, as a session writes it.
    assert MACHINE.match("<!-- workflow:fix-ticket from=373 kind=late -->")
    assert not MACHINE.match("<!-- workflow:fix-ticket from=#373 kind=late -->")


def test_a_protected_path_is_an_owner_task():
    text = _filing()
    assert (
        "**A protected path** (the profile's `guard.protected_paths`): filed as an owner task instead, labelled `owner-task` "
        "in place of `ready-for-agent`, with the same machine line, so a run lists it for the owner (flow §2)."
    ) in text


def test_a_security_problem_on_main_names_only_its_area():
    text = _filing()
    assert "**A security or safety problem in code on the base branch** (`security: main`), whatever its mark:" in text
    assert "every public word names only its area" in text
    assert "the title (\"A security problem in <area>\")" in text
    assert "no reproducer, no file or line, no way to exploit it" in text
    assert "filed `ready-for-human`, never `ready-for-agent`, so nothing builds it unattended" in text
    assert "Its details (where, the reproducer, the fix) go to the owner privately, never on GitHub" in text
    assert "in attended work, in the session's chat" in text
    assert "in a run, in your own chat as soon as you have verified it, and again in your final message" in text
    # Only a ticket marked one is filed; a blocking one stays with its ticket.
    assert "A blocking one is never split out or filed in place of its fix." in text


def test_the_pull_request_body_names_moved_criteria_and_the_split_ticket():
    body = _body_list()
    assert (
        "after a split, under **Split out**, each part split out, in plain words, with its ticket and the acceptance "
        "criteria moved to it, quoted;"
    ) in body
    text = _filing()
    assert "In the findings table, such a finding's outcome is \"Filed #<n>\", or \"Already filed as #<n>\"" in text


def test_plain_words_in_what_a_person_reads():
    text = _filing()
    # "Mechanism" is the findings file's key, never what a person reads.
    assert "mechanism" not in text.replace("`mechanism", "")


def test_changelog_note():
    notes = since_0110()
    assert "(#373, part of spec #412)" in notes
    assert "`<!-- workflow:fix-ticket from=<n> kind=old|late|split -->`" in notes
    assert "Tests: `tests/test_fix_tickets.py`." in notes
