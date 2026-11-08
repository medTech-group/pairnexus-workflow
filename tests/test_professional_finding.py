"""#516: a finding that needs a professional, and the gate (spec #505, answers
7, 15, 16, 27, 40, 41 and 43, fixes F8 and F9). Read as text contracts
(seam 2) on the flow, the `study`, `start`, `next` and `conductor` skills and
the README, as `tests/test_research_flow.py` reads the flow: each test reads
one part of the text and checks what it requires, not its exact wording.

The flow holds the rule ("Research", **A finding that needs a professional**);
§1's gate points to it, since the hook's first flow context carries §1 and §2
whole and has no room for more. The two tests that only check the gate's
heading (`tests/test_kit_014_start.py`, `tests/test_kit_014.py`) stay as they
are: the gate's rule for a held Destination item is tested here."""

import re

import pytest

from changelog_notes import since_0110
from conftest import KIT
from workflow import context

FLOW = KIT / "docs/flow.md"


def _flat(text: str) -> str:
    return " ".join(text.split())


def _read(rel: str) -> str:
    return (KIT / rel).read_text(encoding="utf-8")


def _flow() -> str:
    return FLOW.read_text(encoding="utf-8")


def _flow_section(heading: str) -> str:
    text = _flow()
    assert f"\n## {heading}" in text, heading
    return text.split(f"\n## {heading}", 1)[1].split("\n## ", 1)[0]


def _professional() -> str:
    """The Research section's `- **A finding that needs a professional**` rule, its sub-items included, flattened."""
    raw = _flow_section("Research\n")
    name = "\n- **A finding that needs a professional"
    assert name in raw, "Research has a rule for a finding that needs a professional"
    return _flat(raw.split(name, 1)[1].split("\n- **", 1)[0])


def _part(rule: str, bold: str) -> str:
    """One bold-led part of a flattened rule: from `**bold` to the next list item's bold lead-in."""
    assert f"**{bold}" in rule, bold
    rest = rule.split(f"**{bold}", 1)[1]
    return re.split(r" (?:-|\d+\.) \*\*", rest, maxsplit=1)[0]


def _gate_1() -> str:
    para = next(p for p in _flow_section("1. ").split("\n\n") if p.startswith("**The gate.**"))
    return _flat(para)


# --- the routing choice -----------------------------------------------------


def test_the_professional_choice_has_three_options_and_is_one_recorded_routing_line():
    rule = _professional()
    for option in ("Research it ourselves", "Ask a professional", "Leave it open"):
        assert f"**{option}" in rule, option
    # A routing choice, recorded in one line with the reason and the owner's choice ("Decision questions" item 2).
    assert "routing choice" in rule and '"Decision questions"' in rule
    assert "each time" in rule


def test_the_professional_choice_is_made_before_the_research_check():
    rule = _professional()
    before = rule[rule.index("before the"):][:200]
    assert "research check" in before
    # So the open mark, the questionnaire or the link is in what the check reads.
    assert "questionnaire" in rule and "open" in rule


def test_the_study_asks_it_before_the_research_check_and_points_to_the_flow():
    study = _flat(_read("skills/study/SKILL.md"))
    para = study[study.index("**A finding that needs a professional**"):].split("## 10.", 1)[0]
    assert "before the research check" in para
    assert "routing" in para and '"Decision questions"' in para
    assert "A finding that needs a professional" in para and 'flow\'s "Research"' in para
    for option in ("Research it ourselves", "Ask a professional", "Leave it open"):
        assert option in para, option


# --- the second study ---------------------------------------------------------


def test_a_second_study_is_its_own_note_topic_pull_request_and_research_issue():
    part = _part(_professional(), "Research it ourselves")
    assert "second study" in part
    assert "own note" in part and "topic" in part
    assert "research pull request" in part and "research issue" in part
    # Filed when the owner chooses it, with no intake and no verdict.
    assert "no intake" in part and "no verdict" in part
    # Fresh agents, primary texts, each conclusion quoting its clause, a skeptic, and its label.
    assert "primary" in part and "clause" in part and "skeptic" in part
    assert '"researched, not confirmed by a professional"' in part


def test_the_main_note_links_to_it_and_a_later_research_pull_request_updates_the_mark_and_closes_its_issue():
    part = _part(_professional(), "Research it ourselves")
    assert "main note links to it" in part and "marks the finding open" in part
    later = part[part.index("Once the second note merges"):]
    assert "research pull request" in later and "updates the main note's mark" in later
    assert "Closes #<n>" in later


def test_a_second_study_s_token_record_carries_the_second_study_marker():
    part = _part(_professional(), "Research it ourselves")
    assert "study=second" in part and "token record" in part
    # The study skill posts it, and closes the second study's issue at the mark's update, not at a verdict.
    closing = _flat(_read("skills/study/SKILL.md").split("## 12. Closing", 1)[1].split("\n## ", 1)[0])
    assert "second study" in closing and "study=second" in closing
    assert "Closes #<n>" in closing and "no verdict" in closing



def test_a_second_study_s_research_issue_gets_no_study_under_way_link_on_the_item():
    # `next` and `start` hold an item whose "Study under way: #<n>" link names an open research issue;
    # the second study's issue stays open past the main verdict, so a link to it would hold the item's
    # spec when the verdict and grilling go ahead.
    study = _flat(_read("skills/study/SKILL.md"))
    para = study[study.index("**A finding that needs a professional**"):].split("## 10.", 1)[0]
    ours = para[para.index("**Research it ourselves:**"):].split("- **Ask a professional:**", 1)[0]
    assert '"Study under way"' in ours, "says what the second study's research issue isn't linked by"
    link = ours[ours.index('"Study under way"') - 40:ours.index('"Study under way"') + 120]
    assert "no " in link and "main note" in link


# --- the questionnaire and what waits ----------------------------------------------


def test_the_questionnaire_is_saved_in_the_topic_s_folder_with_an_owner_task_linking_it():
    part = _part(_professional(), "Ask a professional")
    assert "`to-questionnaire`" in part and "`docs/research/<topic>/`" in part
    assert "owner task" in part and "`owner-task`" in part and "links it" in part


def test_leaving_it_open_lists_it_on_the_research_issue_and_marks_it_open_in_the_note():
    part = _part(_professional(), "Leave it open")
    assert "research issue" in part and "open in the note" in part


def test_only_what_rests_on_the_answer_waits():
    part = _part(_professional(), "What waits")
    assert "only what rests on" in part
    assert "verdict and grilling go ahead" in part


# --- holding back ---------------------------------------------------------------------


def test_the_owner_task_goes_under_blocked_by_on_the_item_the_spec_and_the_tickets():
    part = _part(_professional(), "Holding back")
    assert "`## Blocked by`" in part
    for what in ("item's issue", "spec", "build tickets"):
        assert what in part, what


def test_a_destination_item_gets_a_blocked_by_line_in_the_map_s_body_and_who_writes_it():
    part = _part(_professional(), "Holding back")
    assert "Destination item" in part and "`Blocked by: #<n>`" in part and "map's body" in part
    # The session that files the owner task writes it; charting, when the task comes before the map.
    assert "session that files the owner task" in part
    assert "charting" in part and "before the map" in part and "`wayfinder`" in part
    # Its records go where the study skill's section 5 says.
    assert "`study` skill's section 5" in part


@pytest.mark.parametrize("rel", ["skills/next/SKILL.md", "skills/start/SKILL.md"])
def test_next_and_start_skip_a_held_destination_item_while_its_task_is_open(rel):
    rule = _flat(next(ln for ln in _read(rel).splitlines() if ln.startswith("**Held items.**")))
    # The line beside it in the map's body, which `status` doesn't read.
    assert "Destination item" in rule and "`Blocked by: #<n>`" in rule and "map's body" in rule
    tail = rule[rule.index("Destination item"):]
    assert "skip" in tail.casefold() and "while" in tail and "open" in tail


def test_charting_writes_the_line_when_the_task_comes_before_the_map():
    # start's Map path charts the map; a new project's study can file the owner task before it.
    start = _read("skills/start/SKILL.md")
    step1 = _flat(start.split("**Map** (flow §1):", 1)[1].split("\n2. ", 1)[0])
    assert "`Blocked by: #<n>`" in step1 and "Destination item" in step1 and "owner task" in step1


# --- the gate ---------------------------------------------------------------------


def _says_the_held_item_rule(text: str):
    """The gate's rule for a held Destination item: one with a `Blocked by:` line is left out of
    the gate whether its task is open or closed."""
    assert "`Blocked by:`" in text, "names the Destination item's `Blocked by:` line"
    assert "left out" in text, "leaves the held item out of the gate"
    assert "open or closed" in text, "whether its task is open or closed"


def test_the_flow_s_rule_leaves_a_held_destination_item_out_of_the_gate_whether_its_task_is_open_or_closed():
    gate = _part(_professional(), "The gate")
    _says_the_held_item_rule(gate)
    # The line stays; the map's other build tickets can be built while the item is held.
    assert "the line stays" in gate
    assert "other build tickets" in gate
    # Once its task closes, only the held item's own tickets wait for its spec and tickets.
    closes = gate[gate.index("closes"):]
    assert "only" in closes and "own tickets" in closes


def test_flow_1_s_gate_points_to_the_rule_and_the_hook_still_carries_1_and_2_whole():
    gate = _gate_1()
    assert "held" in gate and '"Research"' in gate
    ctx = context.first_flow([FLOW])
    for heading in ("\n## 1. Planning", "\n## 2. A spec and its build tickets"):
        assert heading in ctx, heading
    assert gate.split(" ", 2)[2][:60] in _flat(ctx)


def _start_map_step_5() -> str:
    start = _read("skills/start/SKILL.md")
    return _flat(start.split("**Map** (flow §1):", 1)[1].split("\n5. ", 1)[1].split("\n\n", 1)[0])


def _start_run_unattended() -> str:
    start = _read("skills/start/SKILL.md")
    run = start.split("- **Run unattended:**", 1)[1].split("\n\n", 1)[0]
    return _flat(run.split("\n  2. ", 1)[1])


def _next_gate() -> str:
    return _flat(next(ln for ln in _read("skills/next/SKILL.md").splitlines() if ln.startswith("- **The gate:**")))


def _conductor_kick_off() -> str:
    return _flat(next(ln for ln in _read("skills/conductor/SKILL.md").splitlines()
                      if ln.strip().startswith("- **Maps not yet fully specified.**")))


def _readme_kick_off() -> str:
    return _flat(next(ln for ln in _read("README.md").splitlines() if ln.startswith("A run only builds tickets that are ready")))


def _readme_gate() -> str:
    readme = _read("README.md")
    return _flat(readme.split("- **The gate:** none of a map's build tickets", 1)[1].split("\n\n", 1)[0])


@pytest.mark.parametrize("where", [_next_gate, _start_map_step_5, _start_run_unattended, _conductor_kick_off,
                                   _readme_kick_off, _readme_gate],
                         ids=["next", "start's Map step 5", "start's Run unattended", "the conductor's kick-off",
                              "the README's kick-off line", "the README's gate bullets"])
def test_every_account_of_the_gate_leaves_a_held_destination_item_out(where):
    _says_the_held_item_rule(where())


@pytest.mark.parametrize("where", [_next_gate, _start_map_step_5, _conductor_kick_off, _readme_gate],
                         ids=["next", "start's Map step 5", "the conductor's kick-off", "the README's gate bullets"])
def test_the_fuller_accounts_hold_only_the_held_item_s_own_tickets_once_its_task_closes(where):
    text = where()
    assert "closes" in text, "says what waits once the held item's task closes"
    closes = text[text.index("closes"):]
    assert "only" in closes and "own tickets" in closes


def test_the_conductor_s_kick_off_lists_a_held_item_s_own_tickets_for_excluding_once_its_task_closes():
    # `WF ready` holds the item's tickets only while their `## Blocked by` task is open: once it closes,
    # the kick-off must list them itself, or a run builds them before the item has its spec and tickets.
    kick = _conductor_kick_off()
    assert "lists none of its tickets" not in kick
    assert "closes" in kick, "says what the kick-off lists once the held item's task closes"
    closes = kick[kick.index("closes"):]
    assert "own tickets" in closes and "sub-issues of its spec" in closes and "exclud" in closes


# --- the changelog -----------------------------------------------------------------


def test_the_changelog_has_a_note_and_version_is_untouched():
    assert "(#516, part of spec #505)" in since_0110()
    log = _read("CHANGELOG.md")
    start = log.index("## Unreleased\n")
    end = log.index("\n## ", start + 1)
    released = log[end + 4:].split("\n", 1)[0].strip()
    assert _read("VERSION").strip() == released
