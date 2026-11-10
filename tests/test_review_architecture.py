"""#616: the review panel reads the architecture (spec #611, "The review
panel"; answers 24 and 25 on #611). Seam 3, the kit's text: the panel's
inputs (the pages `workflow index reads` prints, the overview once through
`rules.md`, `pages.md`, and `run.md` in a run), section 10's written rules and
its `ticket` case for a copy the reuse rule lets through, `docs/architecture/`
never another area's, the Standards, Spec and security prompts' added lines,
the Correctness agent's inputs and rule check, section 8's list, and ADR
0001's consequence line. #645 adds section 8's inputs (`pages.md` and the read
pages) and the pages its Correctness brief reads in the repo: those a new or
changed page's `Covers:` overlaps, and every page when the overview changes.
Prior art: tests/test_planning_review.py and tests/test_build_review_rule.py."""

import re

from conftest import KIT

PANEL = "skills/review-panel/SKILL.md"
AGENT = "agents/correctness-reviewer.md"
ADR = "docs/adr/0001-clean-review-resolves-what-the-change-reaches.md"
RULE_HEADING = "## 10. The rule for build reviewers"


def _read(rel: str) -> str:
    return (KIT / rel).read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _section(rel: str, start: str, end: str = "\n## ") -> str:
    text = _read(rel)
    assert start in text, f"{rel} has {start!r}"
    return text.split(start, 1)[1].split(end, 1)[0]


def _inputs() -> str:
    return _flat(_section(PANEL, "## 1. Gather the inputs", "\n## 2."))


def _reviewers() -> str:
    return _flat(_section(PANEL, "## 2. Start the reviewers", "\n## 3."))


def _planning() -> str:
    return _flat(_section(PANEL, "## 8. The planning review", "\n## The research check"))


def _rule() -> str:
    return _flat(_section(PANEL, RULE_HEADING + "\n"))


# --- the panel's inputs (section 1) -------------------------------------------


def test_every_reviewer_gets_the_pages_reads_prints_keeping_their_paths():
    inputs = _inputs()
    # The pages `reads` prints for the change, with the review's base.
    assert "`WF index reads --base origin/<base>`" in inputs
    assert "copied beside `rules.md`, each at its path in the project" in inputs
    # A page that covers nothing yet is printed by `reads` too, so it is copied with the rest.
    assert "a page with no `Covers:` line among them" in inputs
    # It can't tell which files changed: never start the reviewers without its pages.
    assert "never start the reviewers without the pages it names" in inputs


def test_the_overview_reaches_the_reviewers_once_through_rules_md():
    inputs = _inputs()
    assert "The overview (`docs/architecture/README.md`, printed first) reaches them once, through `rules.md`" in inputs
    # Left out of the copy when `project.rules` lists it, so it is never given twice.
    assert "leave it out of the copy when `project.rules` lists it" in inputs
    # The copy command leaves the overview out.
    text = _section(PANEL, "## 1. Gather the inputs", "\n## 2.")
    assert "grep -vxF docs/architecture/README.md" in text


def _copy_command(label: str) -> str:
    text = _section(PANEL, "## 1. Gather the inputs", "\n## 2.")
    assert label in text, f"the copy command is written in full after {label!r}"
    return text.split(label, 1)[1].split("```", 2)[1].strip()


def _run_copy(command: str, tmp_path) -> "Path":
    import subprocess

    project = tmp_path / "project"
    scratch = tmp_path / "scratch"
    (project / "docs" / "architecture").mkdir(parents=True)
    scratch.mkdir()
    (project / "docs" / "architecture" / "README.md").write_text("# Architecture\n", encoding="utf-8")
    (project / "docs" / "architecture" / "orders.md").write_text("Covers: src/orders/**\n", encoding="utf-8")
    printed = "printf 'docs/architecture/README.md\\ndocs/architecture/orders.md\\n'"
    assert "WF index reads --base origin/<base>" in command
    command = command.replace("WF index reads --base origin/<base>", printed).replace("<scratch>", str(scratch))
    run = subprocess.run(["bash", "-c", command], cwd=project, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    return scratch


def test_the_copy_command_is_written_in_full_for_both_cases(tmp_path):
    # Dropping `grep -vxF …` from the one written command by hand leaves a
    # pipeline that runs reads.txt as a command, or a syntax error: both forms
    # are written out, and each copies what it should.
    text = _section(PANEL, "## 1. Gather the inputs", "\n## 2.")
    assert "(Without `grep -vxF" not in text

    listed = _run_copy(_copy_command("when `project.rules` lists the overview:"), tmp_path / "listed")
    assert (listed / "docs" / "architecture" / "orders.md").is_file()
    assert not (listed / "docs" / "architecture" / "README.md").exists()

    unlisted = _run_copy(_copy_command("When it doesn't:"), tmp_path / "unlisted")
    assert (unlisted / "docs" / "architecture" / "orders.md").is_file()
    assert (unlisted / "docs" / "architecture" / "README.md").is_file()


def test_every_reviewer_gets_pages_md():
    inputs = _inputs()
    assert "`pages.md`: `WF index pages`'s output" in inputs
    assert "every page's file, `Covers:`, interface and helpers" in inputs


def test_run_md_in_a_run_names_the_area_alongside_and_protected_paths():
    inputs = _inputs()
    assert "`run.md`, in a ticket session:" in inputs
    for words in (
        "the ticket's area, from its `Area:` line, with that area's globs from the profile's `[areas]`",
        "the briefing's \"Running alongside you\" section, as written",
        "the profile's `guard.protected_paths`",
    ):
        assert words in inputs, words
    # Answer 24: run.md says it too.
    assert "`docs/architecture/` is never another area's files: lines there are always the change's own" in inputs


def test_the_scratch_directory_names_the_architecture_documents_given():
    inputs = _inputs()
    assert "the architecture documents given" in inputs


def _clause(text: str, start: str) -> str:
    """The words from `start` to the end of its sentence."""
    assert start in text, start
    return text.split(start, 1)[1].split(". ", 1)[0]


def test_the_architecture_documents_given_are_the_overview_and_the_pages_everywhere():
    # One name, one set (CONTRIBUTING.md, Writing): the overview and the pages
    # copied under docs/architecture/, as the Correctness agent and ADR 0001
    # say; pages.md and run.md are inputs beside them, never part of them.
    inputs = _inputs()
    assert "The overview in `rules.md` and the pages copied under `docs/architecture/` are the architecture documents given" in inputs
    assert "`pages.md` are the architecture documents given" not in inputs

    rule = _section(PANEL, RULE_HEADING + "\n")
    given = _flat(rule.split("- the architecture documents given:", 1)[1].split("\n- ", 1)[0])
    assert "pages.md" not in given and "run.md" not in given
    assert "\n- `pages.md`" in rule

    text = _section(PANEL, "## 2. Start the reviewers", "\n## 3.")
    standards = _flat(text.split("Standards:", 1)[1].split("```", 2)[1])
    other = _flat(text.split("Spec and security:", 1)[1].split("```", 2)[1])
    for clause in (
        _clause(standards, "The architecture documents given are in <scratch>:"),
        _clause(other, "Check the change against the architecture documents given in <scratch>:"),
    ):
        assert "the overview in rules.md" in clause and "the pages copied under docs/architecture/" in clause
        assert "pages.md" not in clause and "run.md" not in clause
    assert "pages.md" in standards and "pages.md" in other

    agent = _flat(_section(AGENT, "## Your inputs", "\n## What to look for"))
    assert "pages.md" not in _clause(agent, "the architecture documents given:").split(";", 1)[0]


# --- section 10: the written rules, the ticket case, never another area's ----


def test_rule_reads_the_architecture_documents_as_written_rules():
    rule = _rule()
    # Its inputs name them.
    for words in ("the pages copied under `docs/architecture/`", "`pages.md`", "`run.md`"):
        assert words in rule, words
    # A breach in the change's own lines blocks, and outside them is a ticket to fix it.
    assert "a breach of a written rule (`rules.md` or an architecture document given) in the change's own lines." in rule
    assert "a breach of a written rule (`rules.md` or an architecture document given) outside the change's own lines" in rule


def test_rule_marks_a_copy_the_reuse_rule_lets_through_a_ticket():
    rule = _rule()
    ticket = _section(PANEL, RULE_HEADING + "\n").split("- **a ticket to fix it** (`ticket`):", 1)[1].split("\n- **note:**", 1)[0]
    ticket = _flat(ticket)
    assert "a copy of existing logic the reuse rule lets through" in ticket
    assert "moving the logic into one shared helper would touch another area's files during a run, or a protected path" in ticket
    # Which areas and paths: run.md in a run, else the profile.
    assert "`run.md` names them in a run" in ticket


def test_rule_lets_a_copy_through_outside_a_run_only_for_a_protected_path():
    # The reuse rule's area case holds only during a run: outside one, a copy
    # whose move would touch another area's files still blocks, and only a
    # protected path makes it a ticket.
    ticket = _section(PANEL, RULE_HEADING + "\n").split("- **a ticket to fix it** (`ticket`):", 1)[1].split("\n- **note:**", 1)[0]
    ticket = _flat(ticket)
    assert "outside a run, only a protected path counts, from the profile's `guard.protected_paths`" in ticket
    assert "[areas]" not in ticket


def test_rule_says_docs_architecture_is_never_another_areas_files():
    rule = _rule()
    assert "`docs/architecture/` is never another area's files: lines there are always the change's own" in rule


def test_rule_still_names_no_adr_and_no_kit_issue():
    # rule.md reaches projects: no kit ADR and no kit issue numbers.
    rule = _rule()
    assert "ADR" not in rule
    assert not re.search(r"#\d", rule)


# --- section 2: the prompts' added lines --------------------------------------


def test_standards_prompt_searches_the_codebase_and_checks_the_architecture():
    reviewers = _reviewers()
    assert "**The architecture.**" in reviewers
    text = _section(PANEL, "## 2. Start the reviewers", "\n## 3.")
    standards = text.split("Standards:", 1)[1].split("```", 2)[1]
    standards = _flat(standards)
    assert "For each new function, check or constant in the change, search the codebase for existing logic that does the same" in standards
    assert "Check the change against the architecture documents" in standards


def test_spec_and_security_prompts_check_the_architecture():
    text = _section(PANEL, "## 2. Start the reviewers", "\n## 3.")
    other = _flat(text.split("Spec and security:", 1)[1].split("```", 2)[1])
    assert "Check the change against the architecture documents" in other
    reviewers = _reviewers()
    # The security review gets a prompt of its own, so it gets the line.
    assert "run it in an agent of its own, told to use the `security-review` skill on the branch" in reviewers


# --- the Correctness agent ----------------------------------------------------


def test_correctness_agent_names_the_architecture_inputs():
    inputs = _flat(_section(AGENT, "## Your inputs", "\n## What to look for"))
    for words in (
        "the architecture documents given",
        "`docs/architecture/`",
        "`pages.md`",
        "`run.md`",
    ):
        assert words in inputs, words


def test_correctness_agents_rule_check_reads_the_architecture_with_rules_md():
    look = _flat(_section(AGENT, "## What to look for, in order", "\n## How to report"))
    assert "each one in `rules.md` and in the architecture documents given" in look


# --- section 8 ----------------------------------------------------------------


def test_planning_review_covers_a_spec_sessions_architecture_lines():
    planning = _planning()
    assert "a spec session's pull request of ADRs, glossary or architecture lines" in planning
    assert "Build tickets aren't." in planning


def _planning_text() -> str:
    return _section(PANEL, "## 8. The planning review", "\n## The research check")


def _planning_inputs() -> str:
    return _flat(_planning_text().split("**The inputs,**", 1)[1].split("**The reviewers,**", 1)[0])


def _planning_brief(name: str, end: str) -> str:
    reviewers = _flat(_planning_text().split("**The reviewers,**", 1)[1])
    return reviewers.split(f"- **{name}:**", 1)[1].split(end, 1)[0]


def test_planning_review_gets_pages_md_and_the_read_pages():
    # #645, seam 3: section 8's inputs gain pages.md and, for a pull request,
    # the pages `reads` prints, copied as section 1 copies them.
    inputs = _planning_inputs()
    assert "`pages.md`, as in section 1" in inputs
    assert "for a pull request, the pages `WF index reads --base origin/<base>` prints, copied as in section 1" in inputs
    # The overview reaches them once, as in section 1.
    assert "the overview reaching them through `rules.md` when `project.rules` lists it" in inputs
    # So a new page that contradicts an existing one is caught.
    assert "so a new page that contradicts an existing one is caught" in inputs


def test_planning_correctness_looks_for_contradictions_with_the_architecture():
    brief = _planning_brief("Correctness", "- **Spec:**")
    assert "contradictions with other ADRs, the glossary and the architecture documents given" in brief


def test_planning_correctness_reads_the_pages_a_new_or_changed_page_overlaps():
    # `reads` matches changed files against `Covers:`, and a planning pull
    # request changes only files under docs/: a new page covering
    # src/orders/refund.py never brings orders.md (src/orders/**) with it.
    brief = _planning_brief("Correctness", "- **Spec:**")
    assert "`reads` finds pages only by the files a change touches" in brief
    assert (
        "for each page the pull request adds or changes, every page `pages.md` lists "
        "whose `Covers:` could match a file that page's `Covers:` could match"
    ) in brief
    assert "read in the repo" in brief


def test_planning_correctness_reads_every_page_when_the_overview_changes():
    # The overview has no `Covers:`: a cross-cutting rule added to it that
    # contradicts orders.md overlaps nothing, so every page is read.
    brief = _planning_brief("Correctness", "- **Spec:**")
    assert (
        "when the pull request adds or changes the overview (`docs/architecture/README.md`), "
        "every page `pages.md` lists"
    ) in brief


def test_planning_correctness_reads_every_page_for_a_page_that_covers_nothing_yet():
    # A new or changed page with no `Covers:` line overlaps nothing either.
    brief = _planning_brief("Correctness", "- **Spec:**")
    assert "the same, every page `pages.md` lists, for a page it adds or changes that has no `Covers:` line" in brief


def test_planning_spec_brief_reads_the_architecture_lines_against_the_answers():
    # A spec session's architecture lines are the rules its spec decides
    # (answers 10 and 21): the Spec reviewer reads them against answers.md too.
    brief = _planning_brief("Spec", "No Standards reviewer")
    assert "read the ADRs, glossary and architecture lines, or the spec's draft, against `answers.md`" in brief


# --- ADR 0001 -----------------------------------------------------------------


def test_adr_0001_counts_the_architecture_documents_as_written_rules():
    consequences = _flat(_section(ADR, "## Consequences\n", "\n## "))
    assert "The architecture documents a build review is given" in consequences
    assert "count as written rules in the project's rules documents" in consequences
    assert "The planning review also covers a spec session's architecture lines" in consequences


def test_adr_0001_lists_architecture_lines_among_the_planning_reviews():
    consequences = _flat(_section(ADR, "## Consequences\n", "\n## "))
    assert "Planning reviews (a spec's draft, a map decision's or a spec session's ADRs, glossary and architecture lines)" in consequences
