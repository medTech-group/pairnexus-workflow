"""#373: filing the three kinds of ticket (spec #412, "Reviews from the
second", "The circuit breaker", "Runs"; ADR 0001's exceptions): tickets to fix
old bugs, tickets to fix late findings and split tickets, filed by the ticket
session as `build-ticket` says, each with an `Area:` line, acceptance criteria
from the finding, the bar where it has one, the agents' marker and the machine
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
    # build-ticket's older line on findings sends a ticket mark here.
    review = _flat(_between(_read(BUILD), "## 3. Review it", HEADING))
    assert "(under the rule, a finding marked a ticket to fix it is filed instead: \"Filing tickets to fix findings, and split tickets\", below)" in review


def test_the_three_kinds():
    text = _filing()
    assert "Under the rule (`review-panel` §10)" in text
    assert "nothing piles up as `needs-triage`" in text
    assert (
        "**late:** a finding marked a ticket to fix it about this pull request's own lines, "
        "or about lines already reviewed (§10's \"Lines already reviewed\");"
    ) in text
    # Every other ticket mark is old, so each has a kind.
    assert (
        "**old:** any other finding marked a ticket to fix it: code the change neither touches nor reaches, "
        "or a written rule broken outside the change's own lines;"
    ) in text
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
        "so a restart never loses the ticket. Then add it to the pull request body's **Split out** (§4) at once."
    ) in text
    # A session restarted after the split still gives the outcome, from the open split tickets.
    assert (
        "The next review's findings file gives it as a `split` outcome with its issue: every open ticket whose machine line "
        "says `from=` this ticket and `kind=split` that no record names yet, so a session restarted after the split still "
        "gives it, and `previous.md` lists its moved criteria."
    ) in text


def test_it_looks_for_an_open_one_first():
    text = _filing()
    assert "**Look first** for an open fix ticket for the same failure (the same defect in the same place, however it is worded)" in text
    # Listed, not searched: the search index lags behind an issue just filed.
    assert "first among the tickets this session has filed (its findings files' `issue`), then among the open issues carrying a machine line, listed rather than searched" in text
    assert "search/issues" not in text
    listing = _filing_raw().split("listed rather than searched", 1)[1].split("```\n", 2)[1].strip()
    assert listing.startswith("gh api 'repos/<repo>/issues?state=open&per_page=100' --paginate ")
    assert 'contains("<!-- workflow:fix-ticket ")' in listing
    assert "When one is that failure, file nothing: its number is the finding's `issue`" in text
    # An issue no run would build is never reused.
    assert "An open issue for the same failure without a machine line (one a person wrote, say) is never reused, since no run builds it: file the ticket, and name that issue in its `## What to build`." in text
    # A split looks for its own earlier filing, so a restarted session never files it twice.
    assert "For a split, an open ticket whose machine line says `from=` this ticket and `kind=split` for the same part is that one." in text


def test_the_tickets_parts():
    text = _filing()
    assert "A ready build ticket, labelled `ready-for-agent`, with a title" in text
    assert (
        "`Area: <name>`: the profile's `[areas]` area whose paths hold the lines it is about; when no area's paths hold them, "
        "or more than one does, and for every split one, this ticket's area;"
    ) in text
    assert "naming this ticket and the review it came from (\"found by round 2 of #<PR>, for #<n>\")" in text
    assert "`## Acceptance criteria`: from the finding" in text
    assert "a split one gets the criteria that need the part, moved from this ticket word for word" in text
    assert (
        "`## Bar`: the bar this review's `bar.md` gives (this ticket's, or its spec's), copied, when the new ticket is in this "
        "ticket's area (a split one always copies it); else, when the profile's `run.bar_areas` names the new ticket's area, "
        "the bar that area's tickets copy from `profile.md`; otherwise none;"
    ) in text


def test_blocked_by_names_this_ticket_only_for_its_own_lines():
    text = _filing()
    assert (
        "`## Blocked by`: this ticket (`#<n>`) when the new one is about this pull request's own lines, "
        "whose code isn't on the base branch yet: every split one, and a late one on the change's own lines. "
        "Otherwise \"None\": every old one, and a late one on lines the change only reaches."
    ) in text


def test_the_machine_line_and_the_marker_close_the_body():
    raw = _filing_raw()
    fence = raw.split("Its body ends with the machine line", 1)[1].split("```\n", 2)[1]
    lines = [line.strip() for line in fence.strip().splitlines()]
    assert lines == ["<!-- workflow:fix-ticket from=<n> kind=old|late|split -->", "<!-- workflow:agent -->"]
    assert MACHINE.match(lines[0])
    text = _filing()
    assert "`from` is this ticket's number, not its pull request's, written as digits alone; `kind` is one of `old`, `late` or `split`." in text
    # The findings file's split flag comes from the same line, read on the ticket being built.
    assert "When this ticket has such a line saying `kind=split`, each of its findings files sets `split: true` (`review-panel` §4)." in text


def test_findings_py_names_the_same_line():
    # findings.py's docstring names the line the split flag is copied from, in the same form.
    doc = _flat(_read("scripts/workflow/findings.py"))
    assert "`<!-- workflow:fix-ticket … kind=split -->`" in doc


def test_a_protected_path_is_an_owner_task():
    text = _filing()
    assert (
        "**A protected path** (the profile's `guard.protected_paths`): filed as an owner task instead, labelled `owner-task` "
        "in place of `ready-for-agent`, with the same machine line."
    ) in text
    # A security finding on a protected path follows both bullets.
    assert "Two exceptions (ADR 0001), and a finding that is both takes both:" in text


def test_a_security_problem_on_main_names_only_its_area():
    text = _filing()
    # Any security finding, the change's or the base branch's, so a mistaken ticket mark leaks nothing.
    assert "**A security finding** (`security: change` or `main`) marked a ticket to fix it:" in text
    assert "every public word names only the finding's area: the title (\"A security problem in <the finding's area>\"), the body, the findings table" in text
    assert "no reproducer, no file or line, no way to exploit it" in text
    assert "it is labelled `ready-for-human`, never `ready-for-agent`, so nothing builds it unattended" in text
    assert "its body says where the details are: \"Details: given to the owner by the ticket session for #<n>\"" in text
    assert "its details (where, the reproducer, the fix) go to the owner privately, never on GitHub" in text
    assert "in attended work, in the session's chat" in text
    assert "in a run, in your own chat as soon as you have verified it, and again in your final message, which names the ticket" in text
    assert "it is always a new ticket: an open one names only its area, so it can't be matched. Tell the owner privately of any open one it may repeat." in text
    # Only a ticket marked one is filed; a blocking one is fixed in the pull request.
    assert "A blocking security finding is fixed in this pull request: never split out, and never filed in place of its fix." in text


def test_the_pull_request_body_names_moved_criteria_and_the_split_ticket():
    body = _body_list()
    assert (
        "after a split, under **Split out**, each part split out, in plain words, with its ticket and the acceptance "
        "criteria moved to it, quoted;"
    ) in body
    text = _filing()
    assert "In the findings table, a finding filed or found as above has the outcome \"Filed #<n>\", or \"Already filed as #<n>\"." in text


def test_plain_words_in_what_a_person_reads():
    text = _filing()
    # "Mechanism" is the findings file's key, never what a person reads.
    assert "mechanism" not in text.replace("`mechanism", "")


def test_changelog_note():
    notes = since_0110()
    assert "(#373, part of spec #412)" in notes
    assert "`<!-- workflow:fix-ticket from=<n> kind=old|late|split -->`" in notes
    assert "Tests: `tests/test_fix_tickets.py`." in notes
