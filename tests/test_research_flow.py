"""#511: the flow and the README on research (spec #505): the order, research
notes in the repository, the overrides, fact notes, old notes, the note's
header and the research check rule (the decision questions and routing
choices a study adds are in `tests/test_decision_questions.py`). Read as text contracts on `docs/flow.md` and the README,
as `tests/test_decision_questions.py` reads the flow: each test reads one part
of the text and checks what it requires rather than its exact wording."""

import re

from changelog_notes import since_0110
from conftest import KIT
from workflow import context

FLOW = KIT / "docs/flow.md"
README = KIT / "README.md"


def _flatten(text: str) -> str:
    return " ".join(text.split())


def _text() -> str:
    return FLOW.read_text(encoding="utf-8")


def _section(heading: str) -> str:
    """A `## ` section of the flow, as written, from below its heading to the next."""
    text = _text()
    assert f"\n## {heading}\n" in text, f"the flow has a `## {heading}` section"
    return text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]


def _flow(n: int) -> str:
    text = _text()
    return text.split(f"\n## {n}. ", 1)[1].split("\n## ", 1)[0]


def _research() -> str:
    return _section("Research")


def _rule(name: str) -> str:
    """One `- **name` rule of the Research section, flattened, its sub-items included."""
    raw = _research()
    assert f"\n- **{name}" in raw, f"Research has a `- **{name}` rule"
    return _flatten(raw.split(f"\n- **{name}", 1)[1].split("\n- **", 1)[0])


def _step(n: int, section: int) -> str:
    raw = _flow(section)
    return _flatten(raw.split(f"\n{n}. ", 1)[1].split(f"\n{n + 1}. ", 1)[0].split("\n**Checklist:**", 1)[0])


def _checklist(n: int) -> str:
    return _flatten(_flow(n).split("**Checklist:**", 1)[1])


def _sentence(text: str, word: str) -> str:
    found = [s for s in re.split(r"(?<=[.;])\s+", text) if word in s]
    assert len(found) == 1, f"one sentence names {word!r}: {found}"
    return found[0]


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def _readme_line(start: str) -> str:
    """The README's list item (or numbered step) that starts with `start`, flattened."""
    text = _readme()
    assert start in text, start
    return _flatten(text.split(start, 1)[1].split("\n- ", 1)[0].split("\n5. ", 1)[0])


# --- where the section sits -------------------------------------------------


def test_research_comes_after_decision_questions_so_the_hook_still_carries_1_and_2():
    text = _text()
    assert text.index("\n## 2. ") < text.index("\n## Decision questions\n") < text.index("\n## Research\n") < text.index("\n## 3. ")
    # The hook's first flow context still carries §1 and §2 whole, and stops at "Decision questions".
    ctx = context.first_flow([FLOW])
    for heading in ("\n## 1. Planning", "\n## 2. A spec and its build tickets"):
        assert heading in ctx, heading


# --- the order ----------------------------------------------------------------


def test_the_order_is_the_intake_then_the_panel_then_the_verdict():
    s = _sentence(_rule("The order"), "runs from the intake")
    assert s.index("intake") < s.index("panel") < s.rindex("verdict")
    for verdict in ("build it", "prototype first", "stop"):
        assert verdict in s, verdict
    # The study ends at its verdict: grilling isn't part of it, and doesn't always follow.
    assert "grilling" not in s.casefold()


def test_grilling_follows_build_it_or_the_prototype_uncapped_and_stop_ends_the_work():
    # #511 round 1: a study whose verdict is stop goes on to no grilling.
    r = _rule("The order")
    s = _sentence(r, "Grilling")
    assert "build it" in s and "`prototype`" in s and "prototype first" in s
    assert "uncapped" in s
    # Grilling starts from what the study found.
    assert "findings" in s and "ranked questions" in s
    s = _sentence(r, "Stop")
    assert "no grilling" in s


def test_a_new_project_on_a_map_runs_the_intake_and_the_panel_before_charting():
    s = _sentence(_rule("The order"), "charting")
    assert "new project" in s and "map" in s
    assert "intake" in s and "panel" in s and "before" in s
    # The research issue is linked from the map's Notes, never one of its children.
    s = _sentence(_rule("The order"), "Notes")
    assert "research issue" in s and "linked" in s
    assert "`wayfinder:`" in _rule("The order")


def test_flow_1_and_2_point_to_the_order():
    s1 = _flatten(_flow(1).split("\n1. ", 1)[0])
    assert "before charting" in s1 and '"Research"' in s1
    step1 = _step(1, 2)
    study = step1.index("study")
    assert study < step1.index("`grill-with-docs`")
    assert '"Research"' in step1


# --- where research lives -----------------------------------------------------


def test_no_research_branch_is_left_in_flow_1_and_2():
    for n in (1, 2):
        s = _flatten(_flow(n))
        assert "`research/<name>`" not in s, n
        assert "never merged" not in s, n
        assert "on its branch" not in s and "on their branch" not in s, n


def test_flow_1_and_2_put_research_notes_in_docs_research_through_a_research_pull_request():
    for step, section in ((4, 1), (7, 2)):
        s = _step(step, section)
        assert "`docs/research/<topic>/`" in s, (step, section)
        assert "research pull request" in s, (step, section)
    assert "research notes still go in their research pull request" in _step(5, 1)
    for n in (1, 2):
        assert "research in its research pull request" in _checklist(n), n


def test_research_lives_in_docs_research_through_research_pull_requests():
    opening = _flatten(_research().split("\n- **", 1)[0])
    assert "`docs/research/<topic>/`" in opening
    assert "studies and fact notes alike" in opening
    assert "research pull request" in opening and "`claude/research-<topic>`" in opening
    # No new note goes on a research/ branch.
    assert "No new note goes on a `research/*` branch" in opening


# --- the overrides ------------------------------------------------------------


def test_the_flow_overrides_wayfinder_research_and_to_questionnaire_which_stay_unedited():
    r = _rule("The overrides")
    assert "unedited" in r
    s = _sentence(r, "`wayfinder`'s")
    assert "`research/<name>`" in s and "never merged" in s and "`docs/research/<topic>/`" in s
    s = _sentence(r, "`research` skill")
    assert "where the repo already keeps such notes" in s and "`docs/research/<topic>/`" in s
    s = _sentence(r, "`to-questionnaire`")
    assert "in the current directory" in s and "`docs/research/<topic>/`" in s
    assert "`grilling`" in r


# --- fact notes, old notes and the kit's own ----------------------------------


def test_background_subagents_write_in_their_own_worktrees_and_the_starting_session_opens_their_pull_requests():
    r = _rule("Fact notes")
    assert "own worktree" in r and "`claude/research-<topic>`" in r
    s = _sentence(r, "the session that started them")
    assert "opens" in s and "pull request" in s and "research check" in s


def test_a_fact_note_with_no_issue_gets_a_research_issue():
    s = _sentence(_rule("The note"), "no issue")
    assert "fact note" in s and "`research` issue" in s and "filed" in s


def test_old_notes_stay_until_used_and_are_then_brought_in():
    r = _rule("Old notes")
    assert "`research/*`" in r and "stay where they are" in r
    s = _sentence(r, "relies on")
    assert "offers to bring it in" in s
    for part in ("header", "saved sources", "fingerprints", "research check"):
        assert part in s, part


def test_the_kits_own_notes_go_in_docs_research_too():
    s = _sentence(_rule("Old notes"), "kit's own notes")
    assert "`docs/research/`" in s


# --- the note's header --------------------------------------------------------


def test_the_note_has_its_three_header_lines_and_agents_read_only_current_notes():
    r = _rule("The note")
    for line in ("`Status:`", "`Last checked:`", "`Issue:`"):
        assert line in r, line
    assert "`current`" in r and "superseded by" in r
    assert "information only" in r
    s = _sentence(r, "read only notes marked `current`")
    assert "Agents" in s and "`workflow research notes`" in s
    # The layout is the `study` skill's, as #506 shows it.
    assert "`study` skill" in r


# --- the research check rule --------------------------------------------------


def test_every_research_pull_request_gets_the_research_check_and_the_look_one_pass_each():
    r = _rule("The research check")
    assert "every research pull request" in r and "studies and fact notes alike" in r
    assert "one pass each" in r and "never in rounds" in r
    assert "`research-checker`" in r and "saved source" in r
    # The record first, then the claims: the record reader stops at the first code fence.
    s = _sentence(r, "--round 1")
    assert "`workflow review-record --kind research" in s
    assert s.index("record") < s.index("claims")
    assert "code fence" in r
    # The look reads the changed lines and the listed claims; an unchanged line is still wrong.
    s = _sentence(r, "--round 2")
    assert "look" in s
    assert "changed since" in r and "still wrong" in r
    assert "no further round" in r


def test_the_research_check_rule_points_to_4_item_4_rather_than_restating_it():
    r = _rule("The research check")
    assert "§4 item 4" in r and "**A pull request of research notes**" in r
    assert "one source" in r
    # The merge rule's own words stay in §4 alone.
    assert "counts its research check record as its clean review" not in r
    assert "**(unconfirmed)**" not in r
    item = _flatten(_flow(4))
    assert "**A pull request of research notes**" in item


# --- the README ---------------------------------------------------------------


def test_the_readme_s_map_decision_step_4_puts_research_notes_in_docs_research():
    line = _readme_line("4. commits any glossary or ADR change")
    assert "`docs/research/<topic>/`" in line and "research pull request" in line
    assert "research/…" not in line and "never merged" not in line


def test_the_readme_s_research_line_puts_notes_in_docs_research():
    line = _readme_line("- **`/research <question>`**")
    assert "`docs/research/<topic>/`" in line and "research pull request" in line
    assert "research/…" not in line and "never merged" not in line
    for part in ("`Status:`", "`Last checked:`", "`Issue:`", "`current`", "research check"):
        assert part in line, part


def test_the_readme_has_no_research_branch_left():
    text = _flatten(_readme())
    assert "`research/…` branch" not in text
    assert "research notes stay on their own" not in text


def test_the_readme_gives_the_order():
    text = _flatten(_readme())
    main = text.split("#### The main path, step by step", 1)[1].split("**1. `/grill-with-docs`", 1)[0]
    intake = main.index("intake")
    verdict = main.index("verdict", main.index("panel", intake))
    # The interview comes after the verdict, never between the panel and it.
    assert "interview" not in main[intake:verdict]
    after = main[verdict:]
    for part in ("build it", "prototype first", "stop", "interview", "uncapped"):
        assert part in after, part
    chart = text.split("**Chart the map**", 1)[1].split("**Work through it**", 1)[0]
    assert "new project" in chart and "intake" in chart and "panel" in chart and "before" in chart
    assert "Notes" in chart and "research issue" in chart


def test_the_readme_s_to_questionnaire_line_says_where_a_study_s_questionnaire_goes():
    line = _readme_line("- **`/to-questionnaire`**")
    assert "`docs/research/<topic>/`" in line


# --- the changelog ------------------------------------------------------------


def test_the_changelog_has_a_note_and_version_is_untouched():
    assert "(#511, part of spec #505)" in since_0110()
    log = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    start = log.index("## Unreleased\n")
    end = log.index("\n## ", start + 1)
    released = log[end + 4:].split("\n", 1)[0].strip()
    assert (KIT / "VERSION").read_text().strip() == released
