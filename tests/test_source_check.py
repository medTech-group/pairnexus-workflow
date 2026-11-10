"""#517: the source check when a decision relies on a note (spec #505, answers
10, 16, 17, 20, 23 and 28 to 33, fixes F14 to F16). Read as text contracts
(seam 2) on the flow, the `start`, `build-ticket` and `conductor` skills and the
briefing rendered from `templates/ticket-session-prompt.md`, as
`tests/test_professional_finding.py` reads them: each test reads one part of
the text and checks what it requires, not its exact wording.

The flow holds the rule ("Research", **The source check** and **Fixing a wrong
note**), never §1 or §2: the hook's first flow context carries those two whole,
with almost no room left."""

import json
import os
import re
import subprocess
import sys

import pytest

from changelog_notes import since_0110
from conftest import KIT
from workflow import charter, context, reviews

FLOW = KIT / "docs/flow.md"
CLI = KIT / "scripts/workflow.py"
TEMPLATE = KIT / "templates/ticket-session-prompt.md"
SLOTS = {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "none", "wake_trigger": "trig_01abc"}
HASH = re.compile(r"\b[0-9a-f]{64}\b")
OWNER_MARKER = "<!-- workflow:owner-chose -->"


def _flat(text: str) -> str:
    return " ".join(text.split())


def _read(rel: str) -> str:
    return (KIT / rel).read_text(encoding="utf-8")


def _flow_section(heading: str) -> str:
    text = FLOW.read_text(encoding="utf-8")
    assert f"\n## {heading}" in text, heading
    return text.split(f"\n## {heading}", 1)[1].split("\n## ", 1)[0]


def _rule(name: str) -> str:
    """One top-level rule of the flow's "Research" section, its sub-items and examples included (raw)."""
    raw = _flow_section("Research\n")
    lead = f"\n- **{name}"
    assert lead in raw, f"Research has a rule named {name!r}"
    return raw.split(lead, 1)[1].split("\n- **", 1)[0]


def _source_check() -> str:
    return _flat(_rule("The source check"))


def _part(rule: str, bold: str) -> str:
    """One bold-led part of a flattened rule: from `**bold` to the next list item's bold lead-in."""
    assert f"**{bold}" in rule, bold
    rest = rule.split(f"**{bold}", 1)[1]
    return re.split(r" (?:-|\d+\.) \*\*", rest, maxsplit=1)[0]


def _owner_chose_example(text: str) -> str:
    """The fenced example holding the "Owner chose" marker."""
    blocks = re.findall(r"```markdown\n(.*?)\n *```", text, flags=re.S)
    found = [b for b in blocks if OWNER_MARKER in b]
    assert len(found) == 1, "one fenced example of the Owner chose line"
    return "\n".join(l.strip() for l in found[0].splitlines())


def _conductor_owner_answers() -> str:
    text = _read("skills/conductor/SKILL.md")
    lead = "**When the owner answers** a `needs-human` ticket"
    assert lead in text
    return text.split(lead, 1)[1].split("\n**3. The owner's words.**", 1)[0]


# The flow: when it runs, and its three answers.


def test_it_runs_whenever_a_decision_relies_on_a_note_cited_or_followed():
    rule = _source_check()
    assert "relies on a note" in rule
    assert "evidence cites" in rule, "a recommendation's evidence citing the note"
    assert "follows it" in rule, "the build of a session building a ticket following the note"
    assert "research check" in rule and "--fetch" in rule, "it runs `workflow research check` first"


def test_unchanged_spends_nothing():
    part = _part(_source_check(), "Unchanged")
    assert "no model tokens" in part


def test_changed_reads_only_the_changed_paragraphs_and_recommends_one_of_three_recorded_in_one_line():
    part = _part(_source_check(), "Changed")
    assert "only" in part and "paragraphs" in part
    for option in ("go on", "fix the note", "re-run"):
        assert option in part, option
    assert "routing choice" in part and "one line" in part


def test_cant_fetch_is_one_line_for_a_small_decision_and_asked_for_a_high_stakes_one():
    part = _part(_source_check(), "Can't fetch")
    assert "small decision" in part and "one line" in part
    assert "high-stakes" in part and "asked" in part
    assert "that decision" in part, "whether it's high-stakes is judged for that decision"


# A session building a ticket.


def test_an_attended_build_goes_on_with_the_current_note_after_fix_or_re_run():
    part = _part(_source_check(), "Attended")
    assert "owner chooses" in part or "owner is asked" in part
    assert "current note" in part and "pull request" in part
    assert "fix the note" in part and "re-run" in part


def test_an_unattended_build_notes_small_ones_and_follows_open_decisions_for_high_stakes_ones():
    part = _part(_source_check(), "Unattended")
    assert "doesn't touch the decision" in part and "small decision" in part and "goes on" in part
    assert "open_decisions" in part
    assert "decide-and-record" in part and "safest choice" in part
    assert "set aside" in part and "needs-human" in part
    assert "briefing" in part, "the briefing's line for research-source decisions"


def test_what_it_goes_on_with():
    part = _part(_source_check(), "What it goes on with")
    assert "current note" in part and "quoted" in part
    assert "safer of the note and the live text" in part
    assert "fix" in part and "re-run" in part


def test_after_the_owner_chose_decide_and_record_still_rests_on_the_safer_of_the_two():
    # #505's second open question, as Choosing once answers it: a matching "Owner chose" line
    # settles the choice, never what the build rests on under decide-and-record. What it goes
    # on with says the same, so the two parts give one answer.
    part = _part(_source_check(), "What it goes on with")
    after = part.split("after the owner chose", 1)[1]
    assert "current note" in after
    assert "decide-and-record" in after and "safer of the two" in after
    assert "as Choosing once says" in after
    choosing = _part(_source_check(), "Choosing once")
    assert "Under decide-and-record, a matching line settles the choice, and the build still rests on the safer" in choosing


def test_its_lines_go_in_the_pull_request_and_on_the_build_ticket_and_a_stop_names_the_hashes():
    part = _part(_source_check(), "Its lines")
    assert "pull request" in part and "build ticket" in part
    assert "needs-human" in part
    for named in ("note", "link", "hashes"):
        assert named in part, named


def test_quoting_a_source_leaves_out_personal_details_and_sensitive_patterns():
    part = _part(_source_check(), "Quoting a source")
    assert "personal details" in part and "[sensitive].patterns" in part
    for where in ("pull request", "build ticket", "research issue"):
        assert where in part, where


# Choosing once: the "Owner chose" line.


def test_the_owner_chose_line_has_one_fixed_shape_and_a_marker_of_its_own():
    part = _part(_source_check(), "Choosing once")
    assert "conductor" in part and "build ticket" in part and "research issue" in part
    assert "same paragraphs" in part and "new choice" in part
    assert "never counts as the owner's" in part
    assert "planning session" in part
    example = _owner_chose_example(_rule("The source check"))
    lines = [l for l in example.splitlines() if l.strip()]
    assert lines[0].startswith("Owner chose: ")
    for field in ("Note: ", "Source: ", "New: ", "Gone: "):
        assert field in lines[0], field
    assert len(HASH.findall(lines[0])) >= 2, "the changed paragraphs' hashes, new and gone"
    assert lines[1:] == [OWNER_MARKER, "<!-- workflow:agent -->"]


def test_routing_lines_and_the_stakes_line_never_carry_the_owner_chose_marker():
    part = _part(_source_check(), "Choosing once")
    assert "only a line with" in part.lower() and "marker" in part
    assert "routing line" in part and "never" in part
    study = _read("skills/study/SKILL.md")
    assert OWNER_MARKER not in study, "the stakes record and the token record have markers of their own"


def test_the_owner_s_choice_counts_as_choosing_once_says():
    part = _part(_source_check(), "Choosing once")
    assert "the agents' marker" in part
    assert "posted by an account with write access" in part and "as hand-off comments do" in part
    start = next(l for l in _read("skills/start/SKILL.md").splitlines()
                 if l.startswith("| A research issue (status's `research`)"))
    build = _flat(_read("skills/build-ticket/SKILL.md").split("\n## 2. Build it", 1)[1].split("\n## 3.", 1)[0])
    wrong = _flat(_rule("Fixing a wrong note"))
    for where, text in (("start", start), ("build-ticket", build), ("Fixing a wrong note", wrong)):
        assert "from an account with write access" in text, where
        assert "Choosing once" in text, where


def test_owner_s_choice_1():
    part = _part(_source_check(), "Quoting a source")
    assert "<!--" in part and "markers" in part and "left out" in part


def test_owner_s_choice_2():
    part = _part(_source_check(), "Choosing once")
    assert "nothing else" in part and "code fence" in part
    conductor = _flat(_conductor_owner_answers())
    assert "nothing else in the comment" in conductor


def test_owner_s_choice_3():
    # A cloud session's GitHub tools add their footer after every body they post, the
    # conductor's "Owner chose" comment among them (`reviews._CLOUD_FOOTER`). That one
    # footer, once and at the very end, is the only thing besides the fixed shape a
    # comment may hold and still count; anything else still means it doesn't.
    footer = reviews._CLOUD_FOOTER.strip().split("\n")
    assert footer[0] == "---"
    shown = f"a blank line, `{footer[0]}`, then `{footer[1]}`"
    choosing = _part(_source_check(), "Choosing once")
    conductor = _flat(_conductor_owner_answers())
    for where, text in (("Choosing once", choosing), ("conductor", conductor)):
        assert "cloud session's footer" in text and shown in text, where
        assert "once, at the very end" in text, where
        assert "nothing else" in text, where
    assert "each once and on a line of its own, never inside a code fence" in choosing
    assert "nothing else before it" in choosing
    assert "nothing else in the comment" in conductor


def test_the_two_open_questions_take_the_safest_choice():
    part = _part(_source_check(), "Choosing once")
    # #505's first open question: an unfetchable source has no hashes, so an answer about it doesn't carry over.
    assert "can't be fetched" in part and "doesn't count for a later session" in part
    # #505's second: under decide-and-record, a matching line doesn't lift "the safer of the two".
    assert "decide-and-record" in part and "safer of the note and the live text" in part


# Research issues, fixing a wrong note, a Destination item.


def test_a_research_issue_is_filed_only_when_a_note_needs_work_or_no_owner_was_there():
    part = _part(_source_check(), "A research issue")
    assert "fix" in part and "re-run" in part
    assert "no owner was there" in part
    assert "comments on" in part or "commented on" in part, "an open one for the same note and source"
    assert "same note and source" in part
    assert "attended" in part and "files nothing" in part


def test_a_research_issue_closes_through_start_s_carry_on_row():
    part = _part(_source_check(), "A research issue")
    assert "Carry on" in part and "start" in part
    assert "Closes #<n>" in part
    assert "routing line" in part, "closed with its routing line when no note changes"


def test_a_destination_item_s_routing_lines_go_where_the_study_skill_s_section_5_says():
    rule = _source_check()
    assert "Destination item" in rule and "section 5" in rule


def test_fixing_a_wrong_note():
    rule = _flat(_rule("Fixing a wrong note"))
    assert "research pull request" in rule and "research check" in rule
    assert "can't open a second pull request" in rule
    assert "`research`" in rule and "wrong claim" in rule and "evidence" in rule
    assert "mentions it" in rule or "mentioned in" in rule
    assert "unless the owner already chose" in rule


def test_the_hook_still_carries_1_and_2_whole_and_the_source_check_isn_t_in_them():
    for heading in ("1. ", "2. "):
        assert "source check" not in _flow_section(heading).lower(), heading
    ctx = context.first_flow([FLOW])
    assert len(ctx) <= context.FLOW_BUDGET
    for heading in ("## 1. Planning", "## 2. A spec"):
        assert heading in ctx, heading


# The Owner chose line, shown in the conductor too.


def test_the_conductor_posts_the_owner_chose_line_on_the_build_ticket_and_the_open_research_issue():
    text = _conductor_owner_answers()
    flat = _flat(text)
    assert "Owner chose" in flat
    assert "build ticket" in flat and "open research issue" in flat
    assert _owner_chose_example(text) == _owner_chose_example(_rule("The source check")), "one fixed shape"


def test_the_conductor_posts_none_for_a_source_that_can_t_be_fetched():
    flat = _flat(_conductor_owner_answers())
    assert "can't be fetched" in flat and "no hashes" in flat


# The briefing (render.py and the template).


def _project(tmp_path):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "owner-login"\n'
    )
    (tmp_path / "ticket.json").write_text(json.dumps({"number": 7, "title": "Readings tab"}))
    (tmp_path / "slots.json").write_text(json.dumps(SLOTS))


def _brief(tmp_path, open_decisions):
    _project(tmp_path)
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    c["approved"] = {"by": "owner", "at": "2026-10-12T11:55:00Z", "source": "chat"}
    c["open_decisions"] = open_decisions
    (tmp_path / "charter.json").write_text(json.dumps(c))
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    p = subprocess.run(
        [sys.executable, str(CLI), "render", "--template", str(TEMPLATE), "--ticket", "ticket.json",
         "--charter", "charter.json", "--slots", "slots.json", "--tracking", "11", "--out", "briefing.md"],
        capture_output=True, text=True, cwd=tmp_path, env=env,
    )
    assert p.returncode == 0, p.stderr
    return (tmp_path / "briefing.md").read_text()


def _research_line(text):
    found = [l for l in text.splitlines() if l.startswith("- **A decision resting on a research note")]
    assert len(found) == 1, "one line for research-source decisions"
    return found[0]


def test_the_briefing_under_decide_and_record_takes_the_safest_choice_for_research_source_decisions(tmp_path):
    line = _research_line(_brief(tmp_path, "decide-and-record"))
    assert "safest choice" in line
    assert "safer of the note and the live text" in line
    assert "record it in the PR body" in line
    assert "The source check" in line, "it points to the flow's rule"


def test_the_briefing_under_set_aside_stops_at_needs_human_with_the_hashes(tmp_path):
    line = _research_line(_brief(tmp_path, "set-aside"))
    assert "safest" not in line
    assert "needs-human" in line and "hashes" in line


def test_the_briefing_under_set_aside_follows_a_matching_owner_chose_line_instead_of_stopping_again(tmp_path):
    # #586: after the owner answered a stopped ticket, the conductor's "Owner chose" line is on it, and
    # a later session that sees the same paragraphs follows it (the flow's **Choosing once**) rather
    # than stopping at needs-human again; only without a matching line does it stop.
    line = _research_line(_brief(tmp_path, "set-aside"))
    high = line.split("for a high-stakes one,", 1)[1]
    assert '"Owner chose" line on the ticket' in high and "matches" in high
    assert "Choosing once" in high, "it points to the flow's rule for a matching line"
    follow, stop = high.index("follow "), high.index("needs-human")
    assert follow < stop and "without one" in high[follow:stop], "it stops only without a matching line"
    assert "and stop" in high[stop:]


def test_the_briefing_under_decide_and_record_lets_a_matching_owner_chose_line_settle_the_choice(tmp_path):
    # #586: the same exception in the decide-and-record clause: a matching line settles the choice,
    # and the build still rests on the safer of the note and the live text (**Choosing once**).
    line = _research_line(_brief(tmp_path, "decide-and-record"))
    high = line.split("for a high-stakes one,", 1)[1]
    assert '"Owner chose" line on the ticket' in high and "matches" in high
    assert "Choosing once" in high
    owner = high.index("Owner chose")
    assert owner < high.index("safer of the note and the live text"), "the owner's choice also rests on the safer of the two"
    assert "record it in the PR body" in high, "recorded either way"


def test_the_changelog_notes_the_owner_chose_exception_in_the_briefing():
    assert "(#586" in since_0110()


@pytest.mark.parametrize("open_decisions", ["decide-and-record", "set-aside"])
def test_the_briefing_notes_a_small_decision_in_the_pr_body_and_on_the_build_ticket(tmp_path, open_decisions):
    # The flow's **Its lines**: the can't-fetch line and the routing line go in the pull request
    # and on the build ticket, under either charter.
    line = _research_line(_brief(tmp_path, open_decisions))
    assert "a small decision, or a change that doesn't touch the decision, is noted in the PR body and on the build ticket" in line


def test_the_general_open_decisions_line_is_unchanged(tmp_path):
    text = _brief(tmp_path, "decide-and-record")
    assert "- **Decisions the ticket leaves open:** take the choice most consistent with the spec" in text


# build-ticket and start.


def test_build_ticket_runs_the_source_check_and_points_to_the_flow():
    text = _flat(_read("skills/build-ticket/SKILL.md").split("\n## 2. Build it", 1)[1].split("\n## 3.", 1)[0])
    assert "research note" in text and "The source check" in text
    assert "pull request" in text and "build ticket" in text
    assert "Fixing a wrong note" in text


def test_start_s_evidence_runs_the_source_check_when_it_cites_a_note():
    text = _read("skills/start/SKILL.md")
    evidence = next(l for l in text.splitlines() if l.startswith("- **Evidence:**"))
    assert "source check" in evidence and "note" in evidence


def test_start_s_carry_on_row_takes_a_source_check_issue_and_honours_the_owner_s_line():
    text = _read("skills/start/SKILL.md")
    row = next(l for l in text.splitlines() if l.startswith("| A research issue (status's `research`)"))
    assert "source check" in row
    assert "Owner chose" in row
    assert "routing line" in row and "close" in row


def test_the_changelog_has_a_note_and_version_is_untouched():
    assert "(#517, part of spec #505)" in since_0110()
