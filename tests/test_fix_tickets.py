"""#373: filing the three kinds of ticket (spec #412, "Reviews from the
second", "The circuit breaker", "Runs"; ADR 0001's exceptions): tickets to fix
old bugs, tickets to fix late findings and split tickets, filed by the ticket
session as `build-ticket` says, each with an `Area:` line, acceptance criteria
from the finding, the bar where it has one, the agents' marker and the machine
line `<!-- workflow:fix-ticket from=<n> kind=old|late|split -->`. Read as the
kit's other text contracts are (prior art: tests/test_build_review_rule.py)."""

import json
import re
import shutil
import subprocess

import pytest

from changelog_notes import since_0110
from conftest import KIT, git
from workflow import issues
from workflow.guard import decide
from workflow.profile import load

BUILD = "skills/build-ticket/SKILL.md"
PANEL = "skills/review-panel/SKILL.md"
HEADING = "### Filing tickets to fix findings, and split tickets"


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


def _listing() -> str:
    """The command that lists the open issues, from the filing subsection."""
    return _filing_raw().split("rather than searching", 1)[1].split("```\n", 2)[1].strip()


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
    assert (
        "(under the rule, a finding marked a ticket to fix it is filed instead, except a security problem the change adds: "
        "\"Filing tickets to fix findings, and split tickets\", below)"
    ) in review
    # review-panel §3 names the same exception, so the two never answer differently.
    assert (
        "The one exception is a security problem the change adds (`security: change`) marked a ticket to fix it: "
        "it is never filed, but fixed in the pull request, since it still blocks (section 10)."
    ) in s3


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
        "so a restart never loses the ticket; then add it to the pull request body's **Split out** (§4) at once."
    ) in text
    # A session restarted after the split still gives the outcome, with the part's exact name, and the body's entry.
    assert (
        "The next review's findings file gives a `split` outcome for each of this ticket's own split tickets that no record "
        "names yet, its `mechanism` copied from the ticket's `Part:` line, so a session restarted after the split still gives "
        "it, adds it to **Split out** if the body doesn't name it yet, and lists its moved criteria in `previous.md`."
    ) in text


def test_it_looks_for_an_open_one_first():
    text = _filing()
    # Only this ticket's own fix tickets are reused: one from another ticket, or a person's issue, may never be built.
    # Only the session's own filing counts: `author_association` doesn't show write access.
    assert (
        "**This ticket's own fix tickets** are the open issues whose machine line (below) says `from=` this ticket, "
        "posted by the account you post as (`gh api user --jq .login`), since only your own filing counts; "
        "those saying `kind=split` are its own split tickets."
    ) in text
    assert "author_association" not in text
    assert (
        "**Look first.** When one of this ticket's own fix tickets is for the same failure (the same defect in the same place, "
        "however it is worded), or for a split the same part, file nothing: its number is the finding's `issue` (a security one: below)."
    ) in text
    assert (
        "Any other open issue for the same failure is never reused, since a run may never build it: file the ticket, "
        "and name that issue in its `## What to build` (\"may repeat #<n>\")."
    ) in text
    # Listed, not searched: the search index lags behind an issue just filed.
    assert (
        "List every open issue with its author and its machine line, if it has one (the last, since a body may quote another "
        "above its own), rather than searching, since GitHub's search can miss an issue filed a minute ago:"
    ) in text
    assert "search/issues" not in text
    assert _listing().startswith("gh api 'repos/<repo>/issues?state=open&per_page=100' --paginate --jq '")


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq isn't installed")
def test_the_listing_prints_each_issues_machine_line(tmp_path):
    jq = _listing().split("--jq '", 1)[1].rsplit("'", 1)[0]
    issues = [
        {"number": 5, "title": "A bug a person wrote", "user": {"login": "someone"}, "body": "labels broken"},
        {"number": 6, "title": "The preview reader", "user": {"login": "owner"},
         "body": "x\n<!-- workflow:fix-ticket from=373 kind=split -->\n<!-- workflow:agent -->"},
        {"number": 7, "title": "a pull request", "pull_request": {}, "user": {"login": "owner"},
         "body": "<!-- workflow:fix-ticket from=1 kind=old -->"},
        {"number": 8, "title": "No body", "user": {"login": "owner"}, "body": None},
        {"number": 9, "title": "Quotes the form", "user": {"login": "owner"},
         "body": "`<!-- workflow:fix-ticket from=<n> kind=old|late|split -->`"},
        # A finding quoting another ticket's line above its own: its own, the last, is the one listed.
        {"number": 10, "title": "Quotes a real line", "user": {"login": "owner"},
         "body": "#380's `<!-- workflow:fix-ticket from=12 kind=old -->` names its PR\n"
                 "<!-- workflow:fix-ticket from=373 kind=late -->\n<!-- workflow:agent -->"},
    ]
    (tmp_path / "page.json").write_text(json.dumps(issues))
    out = subprocess.run(["jq", "-r", jq, str(tmp_path / "page.json")], capture_output=True, text=True, check=True).stdout
    assert out.splitlines() == [
        "#5 someone - A bug a person wrote",
        "#6 owner <!-- workflow:fix-ticket from=373 kind=split --> The preview reader",
        "#8 owner - No body",
        "#9 owner - Quotes the form",
        "#10 owner <!-- workflow:fix-ticket from=373 kind=late --> Quotes a real line",
    ]


def test_the_guard_lets_the_listing_through_in_a_ticket_session(repo):
    branch = "claude/build-87"
    git(repo, "checkout", "-qb", branch)
    cmd = _listing().replace("<repo>", "acme/demo")
    d = decide({"tool_name": "Bash", "tool_input": {"command": cmd}}, load(repo), "ticket", repo, branch)
    assert d.action == "allow", d.reason


def test_the_tickets_parts():
    text = _filing()
    assert "A ready build ticket, labelled `ready-for-agent`, with a title" in text
    assert (
        "`Area: <name>`: the profile's `[areas]` area whose paths hold the lines it is about; when no area's paths hold them, "
        "or more than one does, and for every split one, this ticket's area;"
    ) in text
    assert "naming this ticket and the review it came from (\"found by round 2 of #<PR>, for #<n>\")" in text
    assert "gives the part's name exactly as `WF merge-check` gave it, on a line of its own: `Part: <name>`;" in text
    assert "`## Acceptance criteria`: from the finding" in text
    assert "a split one gets the criteria that need the part, moved from this ticket word for word" in text
    assert (
        "`## Bar`: when this review's `bar.md` gives a bar (this ticket's, or its spec's) and the new ticket is in this "
        "ticket's area, that bar, copied (a split one always copies it); else, when the profile's `run.bar_areas` names the "
        "new ticket's area, the bar that area's tickets copy from `profile.md`; otherwise none;"
    ) in text
    # `workflow ready` reads "blocked by #8" anywhere in a body as a blocker.
    assert (
        "Write \"blocked by\" only in `## Blocked by`: `workflow ready` reads it anywhere else on a line with an issue number "
        "as a blocker. In a copied finding or a moved criterion, write \"waits on\" instead, and say so in the pull request body."
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
    text = _filing()
    assert "`from` is this ticket's number, not its pull request's, written as digits alone; `kind` is one of `old`, `late` or `split`." in text
    # The findings file's split flag comes from the same line, read on the ticket being built.
    assert "When this ticket was itself filed as a split ticket (its own machine line says `kind=split`), each of its findings files sets `split: true` (`review-panel` §4)." in text


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
    assert "**A security or safety problem in code on the base branch** (`security: main`) marked a ticket to fix it:" in text
    assert "every public word names only the finding's area: the title (\"A security problem in <the finding's area>\"), the body, the findings table" in text
    assert "no reproducer, no file or line, no way to exploit it" in text
    assert "it is labelled `ready-for-human`, never `ready-for-agent`, so nothing builds it unattended" in text
    assert "its body says where the details are: \"Details: given to the owner by the ticket session for #<n>\"" in text
    assert "its details (where, the reproducer, the fix) go to the owner privately, never on GitHub" in text
    assert "in attended work, in the session's chat" in text
    assert "in a run, in your own chat as soon as you have verified it, and again in your final message, which names the ticket" in text
    assert (
        "it is a new ticket each time, unless you filed one for it yourself in this session, its details in your chat: "
        "then it is \"Already filed as #<n>\". Any other open one names only its area, so it can't be matched: "
        "tell the owner privately of any it may repeat."
    ) in text


def test_a_blocking_security_problem_on_main_holds_a_run_for_the_owner():
    text = _filing()
    assert "A blocking `security: main` finding is never split out." in text
    # ADR 0001: in a run it stops its ticket at needs-human; never fixed unattended in public.
    assert "In a run it holds this ticket for the owner, until the owner has fixed it on the base branch:" in text
    assert (
        "file its ticket to fix it as above (`ready-for-human`, only its area named, its details given privately), "
        "with `kind=old` and `## Blocked by` \"None\";"
    ) in text
    # The hold is released by the fix on the base branch, not by a later session finding it again.
    assert (
        "add that ticket under this ticket's `## Blocked by`, replacing a \"None\" there and adding the section if there is none, "
        "keeping the rest of its body, so §0's blocker check (and `workflow ready`, once it is labelled ready again) "
        "stops any start before the owner closes that one;"
    ) in text
    assert (
        "stop as §5's \"Still red after three fix attempts\" says (`needs-human`), the reason naming only its area and saying "
        "how it is released: \"the owner fixes it on the base branch, closes #<n>, then answers here\"."
    ) in text
    # The signal to merge the base in first sits where every session reads it: §0's blocker check.
    zero = _flat(_between(_read(BUILD), "## 0. Read first", "\n## 1."))
    assert (
        "When one is a ticket filed from this ticket for a security problem on the base branch (labelled `ready-for-human`, "
        "its machine line saying `from=` this ticket), now closed as completed, merge the base branch in before anything else, "
        "as §5's \"The base branch moved\" says, with the merge queue on too, so the reviewers read the owner's fix"
    ) in zero
    assert "§0 has the session that picks it up again merge the base branch in first, so its reviewers read the fix." in text
    assert "In attended work it is fixed here, its details shown to the person and given privately to whoever fixes it." in text
    assert "full review" not in text
    assert "**The base branch moved:**" in _read(BUILD)
    assert "**Still red after three fix attempts:**" in _read(BUILD)


@pytest.mark.parametrize(
    "section, held",
    [
        ("## Blocked by\n\nNone\n", []),  # why the step replaces a "None": a section opening with it reads as no blockers
        ("## Blocked by\n\nNone\n- #500\n", []),
        ("## Blocked by\n\n- #500\n", [500]),
        ("## Blocked by\n\n- #372\n- #500\n", [372, 500]),
    ],
)
def test_the_hold_reads_as_a_blocker_only_with_none_replaced(section, held):
    body = f"Area: build\n\n## What to build\n\nx\n\n{section}\n<!-- workflow:agent -->\n"
    assert [b for b in issues.blockers_of(body)] == held


def test_a_security_problem_the_change_adds_is_never_filed():
    text = _filing()
    # It blocks whichever review finds it (review-panel §10), so a mistaken ticket mark never lets it merge.
    assert (
        "A security problem the change adds (`security: change`) is the one finding never filed as marked: even when marked "
        "a ticket to fix it, it is fixed in this pull request, since it still blocks (`review-panel` §10), only its area "
        "named in public, and the findings table gives its mark. Marked blocks or note, it follows the usual rule."
    ) in text
    # Only the ticket mark is overridden: a note (a gap the bar accepts) or a contest keeps its usual rule.
    assert "whatever its mark" not in _flat(_between(_read(PANEL), "## 3. After each round", "\n## 4."))


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
    note = _flat(notes.split("**Filing the three kinds of ticket", 1)[1].split("\n**", 1)[0])
    # The note says what the skill says on the points a reader acts on.
    assert "those filed under the account it posts as" in note
    assert "is a new ticket unless this session already filed one for it" in note
    assert "never filed, even when marked a ticket to fix it" in note
    assert "its ticket to fix it is filed (`kind=old`) and named under the held ticket's `## Blocked by`, replacing a \"None\"" in note
    assert "(#373, part of spec #412)" in notes
    assert "`<!-- workflow:fix-ticket from=<n> kind=old|late|split -->`" in notes
    assert "Tests: `tests/test_fix_tickets.py`." in notes
