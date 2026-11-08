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


# --- the changelog ---------------------------------------------------------------


def test_the_changelog_has_a_note_and_version_is_untouched():
    assert "(#515, part of spec #505)" in since_0110()
    log = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    start = log.index("## Unreleased\n")
    end = log.index("\n## ", start + 1)
    released = log[end + 4:].split("\n", 1)[0].strip()
    assert (KIT / "VERSION").read_text().strip() == released
