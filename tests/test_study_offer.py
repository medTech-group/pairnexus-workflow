"""#515: offering a study (spec #505, "When a study is offered").
Seam 2: the shipped text, read as text contracts, as `tests/test_end_check.py`
and `tests/test_study_skill.py` read it. `start` and `next` each offer a study:
by the stakes for a feature, never for fixes, wording or internal changes, and
with one stakes line for work a current note covers;
they post the stakes record, read earlier judgements, show the size and load
`study`."""

import re

import pytest
from conftest import KIT
from changelog_notes import since_0110

START = KIT / "skills/start/SKILL.md"
NEXT = KIT / "skills/next/SKILL.md"
STUDY = KIT / "skills/study/SKILL.md"


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _block(path, label: str) -> str:
    """The paragraph (with its list) that opens with the bold `label`, down to
    the next bold-labelled paragraph or heading, flattened."""
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"^\*\*{re.escape(label)}\*\*.*?(?=^\*\*[A-Z][^*]*\*\*|^#|\Z)", text, re.M | re.S)
    assert m, f"{path.relative_to(KIT)} has no **{label}** paragraph"
    return _flat(m.group(0))


def _start() -> str:
    return _block(START, "Offering a study")


def _next() -> str:
    return _block(NEXT, "Offering a study")


OFFERS = pytest.mark.parametrize("offer", [_start, _next], ids=["start", "next"])


# --- when it is offered -------------------------------------------------------


@OFFERS
def test_a_feature_is_judged_on_its_stakes_and_the_why_is_said(offer):
    text = offer()
    assert "judge" in text and "stakes" in text
    assert "say why" in text or "says why" in text
    for reason in ("new people or a new need", "high-stakes", "hard to undo", "a bet"):
        assert reason in text, reason


@OFFERS
def test_high_stakes_is_the_model_s_judgement_not_a_list(offer):
    text = offer()
    assert "safety, money, privacy and the law" in text
    assert "not a list that decides" in text


@OFFERS
def test_fixes_wording_and_internal_changes_are_skipped_silently(offer):
    text = offer()
    assert "fixes, wording and internal changes" in text.lower()
    assert "nothing asked or posted" in text


@OFFERS
def test_work_a_current_note_covers_gets_one_stakes_line_naming_the_note(offer):
    text = offer()
    assert "current note" in text
    assert "WF research notes" in text
    assert "one stakes line naming the note" in text
    assert "no question" in text


@OFFERS
def test_the_owner_chooses_run_or_skip(offer):
    text = offer()
    assert "Run a study" in text and "Skip it" in text
    assert "their reason" in text


# --- the record, the earlier judgements and the size ---------------------------


@OFFERS
def test_the_stakes_record_goes_on_the_item_s_issue_or_the_research_issue(offer):
    text = offer()
    assert "stakes record" in text
    assert "item's issue" in text and "research issue" in text
    assert "`study` skill's section 2" in text


@OFFERS
def test_a_destination_item_points_to_the_study_skill_s_section_5_rather_than_restating_it(offer):
    text = offer()
    assert "Destination item" in text
    assert "`study` skill's section 5" in text
    # #512's note: section 5 is the one rule; the offer doesn't restate where the record goes.
    assert "comment on the map naming" not in text


@OFFERS
def test_earlier_judgements_are_read_with_research_stakes_before_judging(offer):
    text = offer()
    assert "WF research stakes --fetch" in text
    assert text.index("WF research stakes") < text.index("Run a study")


@OFFERS
def test_the_size_comes_from_research_estimate_never_money_and_uncapped(offer):
    text = offer()
    assert "WF research estimate --fetch" in text
    assert "never as money" in text
    assert "nothing caps" in text


@OFFERS
def test_inputs_as_files_where_fetch_can_t_read_them(offer):
    text = offer()
    assert "`--comments F --permissions F`" in text


@OFFERS
def test_a_study_that_runs_loads_the_study_skill(offer):
    text = offer()
    assert "load `study` with the Skill tool" in text


@OFFERS
def test_an_item_that_already_links_a_study_is_offered_no_second_one(offer):
    text = offer()
    assert "Study under way: #<n>" in text
    assert "no second" in text


@OFFERS
def test_an_item_already_judged_is_offered_no_second_study(offer):
    # A skip's stakes record stays the item's one judgement: carrying the item on in a
    # later session posts no second record. A Destination item's record is where the
    # `study` skill's section 5 puts it.
    text = offer()
    rules = [s for s in re.split(r"(?<=[.:])\s+(?=[A-Z*-])", text) if "already has a stakes record" in s]
    assert rules, "no rule for an item that already has a stakes record"
    rule = rules[0]
    assert "no second offer" in rule
    assert "Destination item" in rule and "`study` skill's section 5" in rule
    assert "skipped" in rule or "Skip it" in rule


@OFFERS
def test_issue_comments_only_stakes_records_that_count_end_the_offer(offer):
    # Issue comments: start and next say the same, by the `study` skill's rule.
    text = offer()
    rules = [s for s in re.split(r"(?<=[.:])\s+(?=[A-Z*-])", text) if "already has a stakes record" in s]
    assert rules, "no rule for an item that already has a stakes record"
    rule = rules[0]
    assert "already has a stakes record that counts" in rule
    assert '"Which comments count"' in rule
    assert "`study` skill's sections 2 and 3" in rule
    assert "a comment with the stakes marker" not in text


def test_the_study_skill_still_has_the_sections_the_offer_points_to():
    text = STUDY.read_text(encoding="utf-8")
    assert re.search(r"^## 2\. The stakes record$", text, re.M)
    assert re.search(r"^## 3\. The token record$", text, re.M)
    sec5 = _flat(re.search(r"^## 5\. The research issue$.*?(?=^## )", text, re.M | re.S).group(0))
    assert "A map's Destination item" in sec5 and "This is the one rule for a Destination item" in sec5
    assert "Study under way: #43" in sec5


# --- where the offer sits in each skill ----------------------------------------


def test_start_offers_it_before_the_interview_and_before_charting():
    text = _flat(START.read_text(encoding="utf-8"))
    offer = text.index("**Offering a study**")
    assert offer < text.index("**Spec** (flow §2)") < text.index("**Map** (flow §1)")
    spec_step = text[text.index("**Spec** (flow §2)"):text.index("2. **The spec.**")]
    assert "**Offering a study**" in spec_step
    map_step = text[text.index("**Map** (flow §1)"):text.index("2. Close the item's issue")]
    assert "**Offering a study**" in map_step
    assert "before charting's first step" in map_step


def test_start_s_interview_keeps_its_heading_and_comes_after_the_offer():
    # Other tests find the interview by its heading, `1. **The interview.**`.
    spec = START.read_text(encoding="utf-8").split("\n**Spec** (flow §2)", 1)[1]
    assert "\n1. **The interview.**" in spec
    step = spec.split("\n1. **The interview.**", 1)[1].split("\n2. **The spec.**", 1)[0]
    assert "**Offering a study** (above)" in step


def test_a_new_project_s_charting_waits_for_the_intake_and_the_panel_not_the_verdict():
    # As the flow's order: the intake and the panel run before charting's first step.
    text = _start()
    option = re.search(r"\*\*Run a study\*\*: (.*?);", text).group(1)
    aside = re.search(r"\(for a new project, ([^)]*)\)", option)
    assert aside, option
    assert "the intake and the panel before charting's first step" in aside.group(1)
    assert "charting starts once its intake and panel have run" in text


def test_next_offers_it_before_a_clear_map_s_next_spec():
    text = _next()
    assert "clear map's next spec" in text
    assert "before its interview" in text


def test_next_points_to_start_for_how_the_choice_is_asked():
    assert "`start`'s **Offering a study**" in _next()


def test_quick_tickets_and_finding_a_cause_get_no_offer():
    text = _start()
    assert "Quick ticket" in text and "Find the cause first" in text


# --- a new project (#580, split out of #515) -------------------------------------
# One study, on its first item offered one; every later item, a Destination item of
# its map included, takes the offer's other bullets, so the current-note and the
# internal-change skips still give their one answer.


def _new_project(offer) -> str:
    """The new-project rule: the sentences of the offer that name a brand-new project."""
    text = offer()
    m = re.search(r"\*\*A brand-new project\*\*.*?(?=- \*\*[A-Z]|\Z)", text)
    assert m, "the offer has no **A brand-new project** bullet"
    return m.group(0)


@OFFERS
def test_a_brand_new_project_is_always_recommended_one_study(offer):
    rule = _new_project(offer)
    assert "(no code of its own)" in rule
    assert "always recommended a study" in rule
    assert "the project's one study" in rule


@OFFERS
def test_a_new_project_s_one_study_is_its_first_item_offered_one(offer):
    # Round 2's note: a new project whose first item is a quick ticket. A quick ticket
    # is never offered one, so the study goes to the first item that is.
    rule = _new_project(offer)
    assert "first item offered one" in rule
    assert "a fix, wording or an internal change is never that item" in rule


@OFFERS
def test_a_later_session_tells_the_study_was_offered_by_its_stakes_record(offer):
    # Round 2's note: how a later session tells the study has already run (or was skipped).
    rule = _new_project(offer)
    assert "no stakes record yet" in rule
    assert "`WF research stakes --fetch` lists none" in rule
    assert "From the first stakes record on" in rule


@OFFERS
def test_a_new_project_s_later_items_take_the_other_bullets_with_one_answer(offer):
    # The two cases of #580: a later Destination item a current note covers, and one
    # that is an internal change. Each gets exactly the other bullets' answer.
    rule = _new_project(offer)
    later = rule[rule.index("From the first stakes record on"):]
    assert "every later item takes" in later
    assert "as in any project" in later
    assert "an internal change is skipped with nothing asked or posted" in later
    assert "work a current note covers gets one stakes line naming the note" in later
    # Round 1's fix ("judged as a feature") judged an internal change too.
    assert "judged as a feature" not in offer()
    assert "always" not in later


@OFFERS
def test_the_new_project_rule_states_its_precedence_over_the_current_note_skip(offer):
    # The first item only: "always" wins over the current-note skip there, and says so,
    # so the two bullets never both fit one item with different answers.
    rule = _new_project(offer)
    first = rule[:rule.index("From the first stakes record on")]
    assert "even where a current note covers it" in first


def _bullets(offer) -> list:
    """The offer's bullets, each from its `- **` to the next one."""
    return re.findall(r"- \*\*.*?(?=- \*\*|\Z)", offer())


def _wait(offer) -> str:
    """The bullet that holds a map's Destination items for its study's verdict."""
    waits = [b for b in _bullets(offer) if "wait for that study's verdict" in b]
    assert len(waits) == 1, "the offer has no single bullet for the wait"
    return waits[0]


@OFFERS
def test_a_new_project_s_destination_items_wait_for_its_study_s_verdict(offer):
    # Round 2's note: a Destination item picked before the new project's verdict.
    # #583's round 1 (findings 4 and 8): a study that runs posts its stakes record on its
    # research issue as soon as it is filed, before charting, so a wait under "no stakes
    # record yet" never applies. The wait is a bullet of its own, keyed to the map's Notes.
    wait = _wait(offer)
    assert wait.startswith("- **A map whose Notes link")
    assert "Destination items" in wait
    assert "whatever stakes records there are" in wait
    assert "stakes record yet" not in wait and "lists none" not in wait
    assert "wait for" not in _new_project(offer)


@OFFERS
def test_a_new_project_s_later_items_leave_its_destination_items_to_the_wait(offer):
    # #583's round 1, finding 4: "from the first stakes record on, every later item, its map's
    # Destination items included, takes the bullets as in any project" let them go on while
    # the study ran. They go on as in any project only once its verdict is in.
    rule = _new_project(offer)
    later = rule[rule.index("From the first stakes record on"):]
    assert "its map's Destination items included" not in later
    assert "its map's Destination items once its verdict is in (or it was skipped)" in later
    text = offer()
    assert text.index(_wait(offer)) < text.lower().index("fixes, wording and internal changes")


def _clear_map() -> str:
    """`next` §1's rule for a clear map's next spec."""
    lines = [ln for ln in NEXT.read_text(encoding="utf-8").splitlines() if ln.startswith("- **A clear map**")]
    assert len(lines) == 1, "next §1 has no single **A clear map** rule"
    return lines[0]


def test_next_s_clear_map_rule_holds_the_destination_items_for_the_verdict():
    # #583's round 1, finding 9: `next` §1 picked a clear map's first Destination item with no
    # spec, skipping only one named by a "Study under way" comment, so §2 announced it before
    # the offer's wait was reached. The wait is in the readiness rule itself.
    clear = _clear_map()
    wait = clear[clear.index("None is ready while"):]
    assert "the map's Notes link an open research issue" in wait
    assert "that study is offered as its **Carry on**" in wait


@OFFERS
def test_the_offer_s_wait_points_to_next_s_clear_map_rule(offer):
    # A Destination item has no issue number of its own, so "picked by number" fits none.
    wait = _wait(offer)
    assert '`next` §1, "A clear map"' in wait or '§1, "A clear map"' in wait
    assert "picked by number" not in wait


def test_start_s_carry_on_row_offers_the_study_for_a_clear_map_whose_notes_link_it():
    # Finding 9: `start`'s rows offered "Carry on: the clear map's next spec", which `next` then
    # refused. The study's own row takes the map's Destination items while its issue is open.
    text = START.read_text(encoding="utf-8")
    row = next(ln for ln in text.splitlines() if ln.startswith("| An item whose issue links an open research issue"))
    assert "a clear map's Destination items while its Notes link an open research issue" in row
    assert "that study's **Carry on**" in row


@OFFERS
def test_the_new_project_rule_comes_first_in_whether(offer):
    text = offer()
    rule = text.index("**A brand-new project**")
    assert rule < text.lower().index("fixes, wording and internal changes")
    assert rule < text.index("current note already covers")


def test_the_flow_s_research_section_holds_the_new_project_rule():
    flow = _flat((KIT / "docs/flow.md").read_text(encoding="utf-8"))
    research = flow[flow.index("## Research"):flow.index("## The bar")]
    assert "A brand-new project" in research
    assert "always recommended one study" in research
    assert "`start`'s **Offering a study**" in research


def test_the_readme_says_a_new_project_is_recommended_a_study():
    # Round 3's note (row 34 of #579): the README said a study "comes first".
    text = _flat((KIT / "README.md").read_text(encoding="utf-8"))
    assert "For a new project, a study comes first" not in text
    assert "a study is always recommended first" in text


# --- the changelog ---------------------------------------------------------------


def test_the_changelog_has_a_note_and_version_is_untouched():
    assert "(#515, part of spec #505)" in since_0110()
    assert "(#580, part of spec #505)" in since_0110()
    log = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    start = log.index("## Unreleased\n")
    end = log.index("\n## ", start + 1)
    released = log[end + 4:].split("\n", 1)[0].strip()
    assert (KIT / "VERSION").read_text().strip() == released
