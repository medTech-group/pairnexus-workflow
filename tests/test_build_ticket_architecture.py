"""#617 (spec #611, answers 3, 8, 10, 14, 21 and 30 to 33): building reads the
architecture, and the flow says where a structural line goes.

Seam 3, the kit's text: `build-ticket`'s two `workflow index reads` runs and
its `pages` run, its rule for where a structural line goes (answers 30 to 33's
rule for code no page covers among it); flow §2 items 2 and 7, §2's checklist
and §3 item 1; and the changelog note under `## Unreleased`."""

import re

from changelog_notes import since_0110
from conftest import KIT


def _flat(text):
    return re.sub(r"\s+", " ", text)


def _read(rel):
    return (KIT / rel).read_text(encoding="utf-8")


def _between(text, start, end):
    assert start in text, start
    rest = text.split(start, 1)[1]
    assert end in rest, end
    return rest.split(end, 1)[0]


def _build_step():
    return _flat(_between(_read("skills/build-ticket/SKILL.md"), "## 2. Build it", "## 3. Review it"))


def _review_step():
    return _flat(_between(_read("skills/build-ticket/SKILL.md"), "## 3. Review it", "### The rule for build reviewers"))


def _lasting():
    pr = _between(_read("skills/build-ticket/SKILL.md"), "## 4. Open the pull request", "## 5. Get it green")
    return _flat(pr.split("Lasting knowledge for later work", 1)[1].split("\nThen subscribe to its activity", 1)[0])


def _flow():
    return _read("docs/flow.md")


def _flow_2_item_2():
    return _flat(_between(_flow(), "2. Follow `to-tickets`", "\n3. Anything only the owner can do"))


def _flow_2_item_7():
    return _flat(_between(_flow(), "7. **Commit what the session wrote:**", "**Checklist:**"))


def _flow_2_checklist():
    s2 = _between(_flow(), "## 2. A spec and its build tickets", "## Decision questions")
    return _flat(s2.split("**Checklist:**", 1)[1])


def _flow_3_item_1():
    s3 = _between(_flow(), "## 3. Building: one ticket per session", "\n2. **Build** it")
    return _flat(s3.split("1. **Claim** it", 1)[1])


# --- build-ticket: the reads and the pages list ------------------------------


def test_the_build_step_reads_the_architecture_before_building():
    s = _build_step()
    assert "`WF index reads --base origin/<base> --paths <the files you expect to change>`" in s
    assert "`WF index pages`" in s
    # before the tests and the code, and what is read is named
    assert s.index("`WF index reads --base origin/<base>") < s.index("**Tests first:**")
    assert "before building" in s
    assert "the overview" in s and "the pages list" in s


def test_the_review_step_runs_reads_again_on_the_real_diff():
    s = _review_step()
    assert "`WF index reads --base origin/<base>`" in s
    assert "Before the first review" in s
    # reads counts only committed changes: the diff is committed first, and
    # an uncommitted file is given with --paths
    assert "only committed changes" in s
    assert "`--paths`" in s
    # it comes before the panel runs
    assert s.index("`WF index reads --base origin/<base>`") < s.index("Follow the `review-panel` skill")


def test_a_project_without_an_architecture_folder_reads_nothing():
    s = _build_step()
    assert "With no `docs/architecture/` folder they print nothing" in s


# --- build-ticket: where a structural line goes -------------------------------


def test_the_lasting_knowledge_step_keeps_its_old_words():
    s = _lasting()
    assert "(how a new module is meant to be used, a pitfall) goes in the repo's own docs, in this PR, before it merges" in s


def test_a_structural_line_goes_in_its_page_or_the_overview():
    s = _lasting()
    assert "A structural line" in s
    for part in ("what a page owns", "its interface", "its own rules", "its helpers", "its decisions"):
        assert part in s, part
    assert "the architecture page it belongs to" in s
    assert "a cross-cutting rule in the overview (`docs/architecture/README.md`)" in s
    assert "in this PR" in s


def test_a_new_module_adds_its_full_page_covering_the_outermost_new_folder():
    s = _lasting()
    assert "A new module" in s
    assert "a new folder of code that no page covers and that held no code before" in s
    assert "its full page" in s
    assert "the outermost new folder" in s
    assert "what it owns and its interface" in s
    assert "\"code\" as doctor counts it" in s


def test_a_file_no_page_covers_gets_the_small_page_named_by_its_folder_path():
    s = _lasting()
    assert "A file no page covers" in s
    assert "joined with `--`" in s
    assert "a dot at the start of the name dropped" in s
    assert "`src/orders/check.py` → `docs/architecture/src--orders.md`" in s
    assert "`_root.md`" in s and "the repository's root" in s
    assert "created if it doesn't exist" in s
    assert "a `Covers:` line for that file" in s
    assert "literal path" in s
    assert "`[*]`, `[?]`, `[[]`" in s


def test_the_build_skill_points_at_the_overview_for_the_rest():
    # the overview's standing rules are the full text; the skill names them
    assert "The overview's standing rules say the same in full" in _lasting()


# --- the flow ----------------------------------------------------------------


def test_flow_2_item_2_says_where_a_structural_line_goes():
    s = _flow_2_item_2()
    assert "where its structural lines go: its page, or the overview for a cross-cutting rule" in s
    # answers 26, 29 and 31: a new module's full page
    assert "a new folder of code, its full page" in s
    # answers 30, 32 and 33: the small page, `--`, no leading dot, `_root.md`
    assert "a file no page covers, a `Covers:` line in the page named by its folder path" in s
    assert "`.a/b/c.py`: `a--b.md`" in s
    assert "`_root.md`" in s


def test_flow_2_still_reaches_a_planning_session_whole_beside_the_glossary_rule():
    # The first flow context carries §1 and §2 whole (tests/test_start_carry_on.py,
    # tests/test_planning_review.py); the budget that makes room for this ticket's
    # lines still leaves the glossary's rule room for a long path in front of it.
    from workflow import context

    rule = context.GLOSSARY_RULE.format(where="/" + "g" * 150) + " It isn't included here: read it now."
    assert context.FLOW_BUDGET + 2 + len(rule) < context.CONTEXT_LIMIT
    assert "\n## 2. A spec and its build tickets" in context.first_flow([KIT / "docs/flow.md"])
    assert "9,250 characters" in _read("docs/profile.md")


def test_flow_2_item_2_keeps_its_bar_bullet():
    # tests/test_start_carry_on.py reads this bullet word for word
    assert "- `## Bar`, required in a `run.bar_areas` area (\"The bar\")." in _between(
        _flow(), "2. Follow `to-tickets`", "\n3. Anything only the owner can do"
    )


def test_flow_2_item_7_commits_architecture_lines_on_the_planning_branch():
    s = _flow_2_item_7()
    # answers 10 and 21: on the planning branch, with the glossary and ADRs,
    # and the spec's tickets wait for that pull request
    assert s.startswith(" the domain glossary, ADRs and architecture lines, on their own branch, with a pull request")
    assert "(with architecture lines, under the spec's tickets' `## Blocked by`)" in s
    # the planning review still comes first (tests/test_planning_review.py)
    assert "before the pull request is offered" in s


def test_flow_2_checklist_names_the_architecture_lines():
    c = _flow_2_checklist()
    assert "glossary, ADRs and architecture lines committed with a PR offered" in c


def test_flow_3_item_1_reads_the_architecture():
    s = _flow_3_item_1()
    assert "the architecture documents `workflow index reads` prints" in s
    assert "the pages list (`workflow index pages`)" in s
    assert "the notes the briefing points to" in s


# --- the changelog -----------------------------------------------------------


def test_the_changelog_says_so_under_unreleased():
    unreleased = _flat(since_0110().split("\n## 0.1.22\n", 1)[0])
    assert "(#617, part of spec #611)" in unreleased
    note = unreleased.split("(#617, part of spec #611)", 1)[1].split("**For projects updating:**", 1)[0]
    assert "`workflow index reads --base origin/<base>" in note
    assert "`workflow index pages`" in note
    assert "`build-ticket`" in note
    assert "`_root.md`" in note
    assert "`## Blocked by`" in note
