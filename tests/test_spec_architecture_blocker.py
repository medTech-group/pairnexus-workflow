"""#647 (spec #611, answers 10 and 21, user story 22): a spec's tickets wait
for its architecture pull request from the moment they are published.

Seam 3, the kit's text: flow §2 item 2's `## Blocked by` part, item 7 (the
architecture lines committed on the planning branch, with the glossary and ADRs,
its pull request opened as a draft before the tickets are published) and §2's
checklist; `start`'s "Then publish", which a spec session publishes by; and the
changelog note. And the part working: `workflow ready` never lists a ticket
naming that pull request in its `## Blocked by` before it merges. §3 item 1 is
#617's (`tests/test_build_ticket_architecture.py`); §2 reaching a planning
session whole in the hook's first flow context is pinned by
`tests/test_flow_structural_lines.py` and `tests/test_start_carry_on.py`."""

import re

from changelog_notes import since_0110
from conftest import KIT
from workflow.issues import readiness


def _flat(text):
    return re.sub(r"\s+", " ", text)


def _read(rel):
    return (KIT / rel).read_text(encoding="utf-8")


def _section_2():
    flow = _read("docs/flow.md")
    return flow.split("## 2. A spec and its build tickets", 1)[1].split("\n## Decision questions", 1)[0]


def _item(n, nxt):
    s2 = _section_2()
    return _flat(s2.split(f"\n{n}. ", 1)[1].split(f"\n{nxt}", 1)[0])


# --- flow §2 -----------------------------------------------------------------


def test_item_2_s_blocked_by_part_names_the_architecture_pull_request():
    blocked_by = _item(2, "3. ").split("- `## Blocked by`", 1)[1].split("\n- ", 1)[0]
    assert "the architecture pull request (item 7)" in _flat(blocked_by.split(" - ", 1)[0])


def test_item_7_commits_the_architecture_lines_with_the_glossary_and_adrs():
    item = _item(7, "**Checklist:**")
    assert "the domain glossary, ADRs and architecture lines, on their own branch" in item


def test_item_7_opens_the_pull_request_before_the_tickets_are_published():
    item = _item(7, "**Checklist:**")
    # opened as a draft before item 2 publishes, so the tickets name it from the start
    assert "With architecture lines, open it as a draft before item 2 publishes" in item
    # and named by every ticket published while it is unmerged, by this session
    # or a later one (a spec session that stopped before its tickets, say)
    assert "until it merges, every session's tickets name it in `## Blocked by`" in item
    # the planning review still comes before it is offered (marked ready)
    assert "planning review as §1 does before the pull request is offered" in item
    assert item.index("as a draft before item 2 publishes") < item.index("planning review")


def test_the_checklist_has_a_line_for_it():
    checklist = _flat(_section_2().split("**Checklist:**", 1)[1])
    assert "glossary, ADRs and architecture lines committed with a PR offered" in checklist
    # what happens, by item 2's and item 7's name for it: the tickets are
    # published naming it, never held back from publishing until it merges
    assert "the architecture pull request in each ticket's `## Blocked by`" in checklist
    assert "from publishing" not in checklist and "architecture PR" not in checklist


# --- start's publish, which a spec session follows ---------------------------


def _publish():
    start = _flat(_read("skills/start/SKILL.md"))
    return start.split("**Then publish.**", 1)[1].split("4. Comment \"Breakdown published\"", 1)[0]


def test_start_names_the_architecture_pull_request_whichever_session_opened_it():
    publish = _publish()
    names = (
        "Each new ticket's `## Blocked by` names the architecture pull request (flow §2 item 7) "
        "while it is unmerged, whichever session opened it, so none is ready before it merges."
    )
    # a session publishing tickets for a spec whose lines an earlier session
    # wrote and offered ("Stop here") names that pull request too
    assert names in publish
    # in the post of what will be published, which a session carrying on
    # publishes from as is
    assert publish.index(names) < publish.index("Breakdown to publish")
    # a held-back ticket's settle publishes its new tickets the same way
    start = _flat(_read("skills/start/SKILL.md"))
    settle = start.split("**Settling a held-back ticket.**", 1)[1].split(" 4. **Commit what the session wrote,**", 1)[0]
    assert 'is published as "Then publish" says' in settle


def test_start_opens_the_draft_only_for_lines_in_no_pull_request_yet():
    publish = _publish()
    opens = "If the session's architecture lines are in no pull request yet, open the architecture pull request as a draft."
    assert opens in publish
    # a session carrying on, or one publishing after an earlier session opened
    # it, never opens a second one; the first opens it before any ticket
    assert publish.count("as a draft") == 1
    assert publish.index(opens) < publish.index("Publish the new build tickets")


def test_start_s_publish_order_has_one_first_step():
    publish = _publish()
    # the post comes first; the draft opens in the numbered steps after it
    assert "before anything else" not in publish
    assert publish.index("First post") < publish.index("Then, in this order:") < publish.index("as a draft")


def test_start_calls_it_the_architecture_pull_request():
    # the same name as flow §2 item 2 and the checklist
    publish = _publish()
    assert "the session's pull request" not in publish
    assert "the architecture pull request" in publish


# --- the part working --------------------------------------------------------


def _issue(n, state="open", labels=("ready-for-agent",), body="", **extra):
    return {"number": n, "state": state, "state_reason": None, "labels": [{"name": l} for l in labels], "body": body, "title": f"t{n}", **extra}


def test_ready_never_lists_a_ticket_before_its_architecture_pull_request_merges():
    ticket = _issue(21, body="Area: orders\n\n## What to build\n\nx\n\n## Blocked by\n\n- #20\n")
    draft = _issue(20, labels=(), pull_request={"merged_at": None}, draft=True)
    merged = _issue(20, state="closed", labels=(), pull_request={"merged_at": "2026-11-10T00:00:00Z"})
    (v,) = readiness([ticket, draft], [], repo="acme/demo")
    assert not v.ready and v.reasons == ["blocked by open PR #20"]
    (v,) = readiness([ticket, merged], [], repo="acme/demo")
    assert v.ready


# --- the changelog -----------------------------------------------------------


def test_the_changelog_says_so_under_unreleased():
    unreleased = _flat(since_0110().split("\n## 0.1.22\n", 1)[0])
    assert "(#647, part of spec #611" in unreleased
    note = unreleased.split("(#647, part of spec #611", 1)[1].split("**For projects updating:**", 1)[0]
    assert "`## Blocked by`" in note
    assert "draft" in note
    assert "`start`" in note
