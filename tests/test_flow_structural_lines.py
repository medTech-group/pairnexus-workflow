"""#646 (spec #611, answers 30 to 33): flow §2 item 2 says where a ticket's
structural lines go, and §1 and §2 still reach a planning session whole.

Seam 3, the kit's text: flow §2 item 2's bullet, carrying answers 30 to 33's
rule for code no page covers (`build-ticket`'s side is #617's,
`tests/test_build_ticket_architecture.py`), and the changelog note. And the
hook's first flow context (`workflow.context`), as the context hook builds it
for someone new in an attended session: `first_flow` on the vendored flow, then
`with_glossary` with the vendored glossary. The project's paths are relative,
from `tmp_path`, so their length is exactly the one asked for, however long
pytest's temporary folder is."""

import re
from pathlib import Path

import pytest

from changelog_notes import since_0110
from conftest import KIT
from workflow import context


def _flat(text):
    return re.sub(r"\s+", " ", text)


def _read(rel):
    return (KIT / rel).read_text(encoding="utf-8")


def _item_2():
    flow = _read("docs/flow.md")
    return _flat(flow.split("2. Follow `to-tickets`", 1)[1].split("\n3. Anything only the owner can do", 1)[0])


def _bullet():
    m = re.search(r"- where its structural lines go[^\n]*", _read("docs/flow.md"))
    assert m, "flow §2 item 2 has a bullet on where a ticket's structural lines go"
    return m.group(0)


# --- flow §2 item 2 ----------------------------------------------------------


def test_flow_2_item_2_says_where_a_ticket_s_structural_lines_go():
    b = _bullet()
    assert b in _item_2()  # in item 2's list of what a build ticket has
    assert "the overview's rules" in b  # the full text it points at
    assert "the code's page" in b
    assert "a cross-cutting rule: the overview" in b


def test_the_bullet_carries_the_rule_for_code_no_page_covers():
    b = _bullet()
    # answer 31: a new folder no page covers gets its full page
    assert "a new folder's full page" in b
    # answers 30 and 32: a file no page covers, a small page named by its folder path
    assert "for a file no page covers, a small page named by its folder path" in b
    assert "`src--orders.md`" in b
    # answer 33: a root-level file's line goes in `_root.md`
    assert "`_root.md`" in b


def test_the_bullet_stays_a_list_item_before_the_bar():
    # tests/test_start_carry_on.py reads the bar bullet last in the list
    item = _item_2()
    assert item.index("- where its structural lines go") < item.index("- `## Bar`, required in a `run.bar_areas` area")


def test_the_overview_template_has_the_rule_the_bullet_points_at():
    overview = _flat(_read("templates/architecture-overview.md"))
    assert "### Code no page covers yet" in overview
    assert "`_root.md`" in overview and "joined with `--`" in overview


# --- the protected-path note's detail, moved out of §2 to make room -----------


def test_flow_points_at_the_charter_for_which_paths_count_as_named():
    flow = _flat(_read("docs/flow.md"))
    item_4 = flow.split("4. **A change to a protected path**", 1)[1].split(" 5. **A ticket that fixes", 1)[0]
    assert "`workflow ready` notes a ticket whose body names one" in item_4
    assert "`charter.md` in the kit's docs says which it reads as named" in item_4
    assert "for the owner to keep or exclude" in item_4


def test_the_charter_says_which_paths_count_as_named():
    readiness = _flat(_read("docs/charter.md")).split("- **Readiness:**", 1)[1].split("- **Safety:**", 1)[0]
    assert 'A path in fenced code (unless the prose before it asks for a change "to" or "in" it)' in readiness
    assert "after \"don't\", \"do not\" or \"never\" in its clause, isn't read as named" in readiness
    assert "when in doubt, a path is noted" in readiness


# --- the hook's first flow context -------------------------------------------


def _project(base: Path, length: int) -> Path:
    """A relative project path exactly `length` characters long, in folders short enough for any file system."""
    parts, left = [], length
    while left > 50:
        parts.append("p" * 49)
        left -= 50  # the folder and its "/"
    parts.append("p" * left)
    root = Path(*parts)
    assert len(str(root)) == length
    return root


def _first_context(tmp_path, monkeypatch, length):
    """The first flow context with the glossary's rule, for a vendored project at `length` characters."""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path, length)
    (root / ".claude/workflow/docs").mkdir(parents=True)
    flow = root / ".claude/workflow/flow.md"
    flow.write_text(_read("docs/flow.md"), encoding="utf-8")
    glossary = root / ".claude/workflow/docs/glossary.md"
    glossary.write_text(_read("docs/glossary.md"), encoding="utf-8")
    return context.with_glossary(context.first_flow([flow]), glossary)


# main reached §2 whole beside the glossary's rule up to a 219-character project path
@pytest.mark.parametrize("length", [20, 90, 219])
def test_sections_1_and_2_reach_someone_new_whole_beside_the_glossary_s_rule(tmp_path, monkeypatch, length):
    out = _first_context(tmp_path, monkeypatch, length)
    assert len(out) < context.CONTEXT_LIMIT
    assert out.startswith(context.GLOSSARY_RULE.split("{where}")[0])  # the rule first
    for heading in ("\n## 1. Planning", "\n## 2. A spec and its build tickets"):
        assert heading in out, heading
    # §2 whole: the text stops at the section after it, and its last line is there
    assert 'It stops before "Decision questions"' in out
    assert "\n**Checklist:** every input decision used or ruled out with a reason" in out
    assert _bullet() in out


def test_the_budget_still_leaves_room_for_the_glossary_s_rule():
    # unchanged from main, so docs/profile.md's "leaving room for the glossary's rule" holds
    assert context.FLOW_BUDGET == 8_900
    rule = context.GLOSSARY_RULE.format(where="/" + "p" * 219 + "/.claude/workflow/docs/glossary.md")
    by_path = f"{rule} It isn't included here: read it now."
    assert len(by_path) + 2 + context.FLOW_BUDGET < context.CONTEXT_LIMIT


# --- the changelog -----------------------------------------------------------


def test_the_changelog_says_so_under_unreleased():
    unreleased = _flat(since_0110().split("\n## 0.1.22\n", 1)[0])
    assert "(#646, part of spec #611)" in unreleased
    note = unreleased.split("(#646, part of spec #611)", 1)[1].split("**For projects updating:**", 1)[0]
    assert "§2 item 2" in note
    assert "`_root.md`" in note
    assert "`charter.md`" in note
