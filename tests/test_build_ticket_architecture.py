"""#617 (spec #611, answers 3, 8, 14 and 30 to 33): building reads the
architecture, and says where a structural line goes.

Seam 3, the kit's text: `build-ticket`'s two `workflow index reads` runs and
its `pages` run, its rule for where a structural line goes (answers 30 to 33's
rule for code no page covers among it); flow §3 item 1; and the changelog note
under `## Unreleased`. Flow §2 item 2's line on where a structural line goes,
with the first flow context's budget, is #646's; §2 item 7 and its checklist
(architecture lines on the planning branch, the tickets blocked by it) are #647's."""

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


def test_a_project_without_an_architecture_folder_reads_nothing(tmp_path, monkeypatch, capsys):
    # `reads` prints nothing there, but `pages` says there are no pages: the
    # step says what each prints, as the command does
    from conftest import git
    from workflow import cli

    s = _build_step()
    assert "With no `docs/architecture/` folder, `reads` prints nothing and `pages` says there are no pages: go on without." in s
    assert "they print nothing" not in s
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert cli.main(["index", "reads", "--base", "main"]) == 0
    assert capsys.readouterr().out == ""
    assert cli.main(["index", "pages"]) == 0
    assert capsys.readouterr().out == "No architecture pages in docs/architecture/.\n"


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


def test_flow_2_item_2_keeps_its_bar_bullet():
    # tests/test_start_carry_on.py reads this bullet word for word
    assert "- `## Bar`, required in a `run.bar_areas` area (\"The bar\")." in _between(
        _flow(), "2. Follow `to-tickets`", "\n3. Anything only the owner can do"
    )


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
    # the parts split out are named, and not described as built here
    assert "#646" in note and "#647" in note
    assert "9,450" not in note and "`## Blocked by`" not in note
