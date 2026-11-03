"""#374: the rule for build reviewers (spec #412, "The rule", "Findings",
"Reviews from the second", "The bar"): one section of `review-panel`, copied
into each build review's scratch directory as `rule.md`, that every build
reviewer follows and planning reviews don't get. Read as the kit's other text
contracts are (prior art: tests/test_planning_review.py), plus the two
commands the section gives the session: the copy of the rule, and the pull
request's own changes since the last review, run for real."""

import re
import subprocess

import pytest

from changelog_notes import since_0110
from conftest import KIT, git
from workflow import findings

PANEL = "skills/review-panel/SKILL.md"
RULE_HEADING = "## 10. The rule for build reviewers"


def _read(rel: str) -> str:
    return (KIT / rel).read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _section(rel: str, start: str, end: str = "\n## ") -> str:
    text = _read(rel)
    assert start in text, f"{rel} has {start!r}"
    return text.split(start, 1)[1].split(end, 1)[0]


def _rule() -> str:
    return _flat(_section(PANEL, RULE_HEADING + "\n"))


def _inputs() -> str:
    return _section(PANEL, "## 1. Gather the inputs", "\n## 2.")


def _fence_after(text: str, words: str) -> str:
    """The first fenced block after `words` in `text`, its lines unindented."""
    after = text.split(words, 1)[1]
    block = after.split("```", 2)[1]
    lines = block.split("\n")[1:]  # the opening fence's own line
    return "\n".join(line.strip() for line in lines).strip()


# --- the section, and its copy as rule.md ------------------------------------


def test_the_rule_is_the_review_panels_last_section_so_its_copy_runs_to_the_end():
    text = _read(PANEL)
    headings = re.findall(r"^## .*$", text, re.M)
    assert headings[-1] == RULE_HEADING
    # The section says it is copied as rule.md and must stay last.
    rule = _rule()
    assert "copied, as it is, into each build review's scratch directory as `rule.md`" in rule
    assert "keep it the last section" in rule


def test_section_1_copies_exactly_the_rule_into_rule_md(tmp_path):
    inputs = _inputs()
    assert "`rule.md`" in inputs
    command = _fence_after(inputs, "`rule.md`")
    assert command.startswith("sed -n ")
    command = command.replace("<this skill's directory>", str(KIT / "skills/review-panel")).replace("<scratch>", str(tmp_path))
    subprocess.run(["bash", "-c", command], check=True)
    copied = (tmp_path / "rule.md").read_text(encoding="utf-8")
    text = _read(PANEL)
    assert copied == text[text.index(RULE_HEADING + "\n"):]


def test_every_build_reviewer_follows_it_and_planning_reviews_dont_get_it():
    rule = _rule()
    assert "Every build reviewer follows it: Standards, Spec, Correctness, the security review and the explorer" in rule
    assert "the light and small reviews included" in rule
    assert "Planning reviews (section 8) don't get it" in rule
    planning = _flat(_section(PANEL, ". The planning review\n"))
    assert "Planning reviews don't get section 10" in planning
    assert "no `rule.md`, `bar.md` or `since.patch`" in planning


def test_it_applies_to_records_written_with_findings_and_a_run_keeps_its_rule():
    rule = _rule()
    assert "**When it applies:** a build review whose record is written with `--findings` (section 4)" in rule
    # Until the switch, today's rule: no rule.md, and records with --clean or --not-clean.
    assert "build reviews keep today's rule: no `rule.md`, and records with `--clean` or `--not-clean`" in rule
    assert "A run keeps the rule it started with" in rule


# --- marks, severity, reproducers, the part ----------------------------------


def test_each_finding_carries_one_of_three_marks():
    rule = _rule()
    assert "Mark each finding" in rule
    for mark in ("**blocks:**", "**a ticket to fix it** (`ticket`):", "**note:**"):
        assert mark in rule, mark
    # A note: a preference, a gap the bar accepts, a moved criterion, no reproducer.
    note = rule.split("**note:**", 1)[1].split("**", 1)[0]
    for words in ("a preference no written rule backs", "a gap the bar accepts", "a finding on a moved criterion", "no reproducer"):
        assert words in note, words


def test_the_top_severity_is_critical_and_never_read_as_the_mark():
    rule = _rule()
    assert "Severity: critical, important or minor" in rule
    assert "\"Critical\" is the top severity; it never means blocks" in rule
    assert "A minor finding can block, and a critical one with no reproducer is a note" in rule
    # The old top severity is gone from the reviewer's own text.
    agent = _read("agents/correctness-reviewer.md")
    assert "**Severity:** critical, important or minor" in agent
    assert "blocker, important or minor" not in agent


def test_a_blocking_finding_needs_a_reproducer_by_what_it_is_about():
    rule = _rule()
    for words in (
        "code: an input, and the result it should give;",
        "skill or doc text: a concrete scenario, and the two lines that answer it differently;",
        "an unmet acceptance criterion or untested behaviour: the criterion or behaviour quoted, and the test that should exist;",
        "a breach of a written rule: the rule quoted, and the line that breaks it.",
        "No reproducer: the finding is a note, whatever its severity.",
    ):
        assert words in rule, words


def test_each_finding_names_its_part_reusing_earlier_names_exactly():
    rule = _rule()
    assert "Name the part of the change each finding is about" in rule
    assert "reuse its name exactly, character for character" in rule
    assert "`previous.md`" in rule
    # The record's limits on a name (#370), so a name is never refused.
    assert f"at most {findings.MAX_NAME} characters, one line, no backtick or `~~~`" in rule
    assert "whether the bar's fail-closed form covers the part" in rule


# --- what blocks, and where the hunt stops ----------------------------------


def test_what_blocks_is_adr_0001_as_adr_0002_changes_it():
    rule = _rule()
    assert "ADR 0001's rule, as ADR 0002 changes it" in rule
    for words in (
        "a defect in the change's own lines;",
        "something the change breaks elsewhere",
        "something the change makes reachable;",
        "an acceptance criterion not met;",
        "new behaviour without a test;",
        "a safety breach the change adds;",
        "a security problem the change adds;",
        "a breach of a written rule (`rules.md`) in the change's own lines.",
    ):
        assert words in rule, words


def test_reviewers_get_the_bar_and_a_gap_it_accepts_is_a_note():
    inputs = _flat(_inputs())
    assert "`bar.md`: the ticket's `## Bar`, or the bar its spec gives for its tickets, as written; \"None\" when neither gives one" in inputs
    rule = _rule()
    assert "**The bar:** a gap `bar.md` accepts as a limit is a note." in rule


def test_a_finding_on_a_criterion_moved_by_a_split_is_a_note():
    inputs = _flat(_inputs())
    assert "under \"Moved criteria\", each acceptance criterion moved by a split, quoted, with the ticket it moved to" in inputs
    rule = _rule()
    assert "**Moved criteria:** a criterion `previous.md` lists as moved by a split isn't unmet here: a finding on it is a note." in rule


# --- reviews from the second ---------------------------------------------------


def test_from_the_second_review_reviewers_get_the_changes_since_the_last_review_and_what_they_reach():
    inputs = _flat(_inputs())
    assert "`since.patch`, from the second review: the pull request's own changes since the last review, round or pass, with the base branch's changes left out" in inputs
    rule = _rule()
    assert "**From the second review,** a round or a pass, review `since.patch` and what it reaches" in rule
    assert "Read `diff.patch`, the whole change, for context" in rule
    assert "With no `since.patch`, the whole change is new to this review" in rule
    # Passes review the changes since the last review, round or pass.
    stop = _flat(_section(PANEL, "## 5. When to stop"))
    assert "a pass reviews the changes since the last review, round or pass (`since.patch`, section 1), not since the last round" in stop


def test_a_finding_on_lines_already_reviewed_is_a_ticket_unless_it_is_one_of_six_kinds():
    rule = _rule()
    lines = rule.split("**Lines already reviewed**", 1)[1].split("**", 1)[0]
    assert "a finding on lines unchanged since a review that covered them (in the change or in what it reached) is marked a ticket to fix it" in lines
    for words in (
        "a safety breach",
        "a security problem the change adds",
        "loses data",
        "leaves an acceptance criterion unmet",
        "leaves new behaviour untested",
        "something the change breaks elsewhere",
    ):
        assert words in lines, words
    assert "those still block, whichever review finds them" in lines


def test_previous_md_carries_the_parts_the_contests_and_what_was_done():
    inputs = _flat(_inputs())
    for words in (
        "with its findings numbered as in its record",
        "its part exactly as the reviewer wrote it",
        "under \"Contests to rule on\"",
        "the parts that took the bar's fail-closed form or were split out",
    ):
        assert words in inputs, words


def test_correctness_rules_on_contests_kept_or_overturned():
    rule = _rule()
    assert "The Correctness reviewer rules on each" in rule
    assert "**kept**" in rule and "**overturned**" in rule
    assert "Other reviewers don't rule" in rule
    assert "A kept finding is fixed, never contested again" in rule


def test_a_security_problem_shows_only_its_area():
    rule = _rule()
    assert "`security: change`" in rule and "`security: main`" in rule
    assert "never in a part's name: the public records show only the area" in rule


def test_the_report_lists_what_the_findings_file_needs():
    report = _rule().split("**How to report.**", 1)[1]
    for field in ("**Mark:**", "**Severity:**", "**Part:**", "**Where:**", "**Reproducer:**", "**Covered:**", "**Security:**", "**The fix:**"):
        assert field in report, field


# --- the session's side: §2's pointer, §3 and §4's records ------------------


def test_section_2_points_every_prompt_it_gives_to_rule_md():
    s2 = _flat(_section(PANEL, "## 2. Start the reviewers", "\n## 3."))
    assert "Follow the rule in <scratch>/rule.md: it says how to mark and report each finding." in s2
    pointer = s2.split("**Under the rule**", 1)[1]
    for who in ("`code-review`'s Standards and Spec reviewers", "the security review"):
        assert who in pointer, who
    assert "`correctness-reviewer` and `ui-explorer` read it themselves" in pointer


def test_section_3_writes_every_reported_finding_into_the_findings_file():
    s3 = _flat(_section(PANEL, "## 3. After each round", "\n## 4."))
    assert "under the rule (section 10), written with `--findings` (section 4)" in s3
    assert "every finding a reviewer reported goes in the findings file as reported, even one you judge not a problem" in s3
    assert "A mark is the reviewer's" in s3


def test_section_4_writes_rule_2_records_with_findings():
    s4 = _flat(_section(PANEL, "## 4. Post the review record", "\n## 5."))
    assert "WF review-record --kind round --round <n> --commit <sha> --reviewers standards,spec,correctness --findings /tmp/review-<ticket>-r<n>/findings.json > /tmp/review-<ticket>-r<n>/record.md" in s4
    assert "WF review-record --kind pass --round <last round> --commit <sha> --reviewers correctness --findings /tmp/review-<ticket>-pass<k>/findings.json > /tmp/review-<ticket>-pass<k>/record.md" in s4
    assert "`[]` when no reviewer reported anything" in s4
    # Every key the findings file takes is named, so the session can write it.
    for key in ("mark", "mechanism", "reproducer", "covered", "contested", "security", "area", "issue", "outcomes", "split"):
        assert f"`{key}`" in s4, key


def test_section_4s_example_findings_file_is_one_review_record_accepts():
    s4 = _section(PANEL, "## 4. Post the review record", "\n## 5.")
    example = _fence_after(s4, "For example:")
    loaded = findings.load(example)
    marks = [f.mark for f in loaded.findings]
    assert set(marks) == {"blocks", "ticket", "note"}
    assert not loaded.clean


def test_the_findings_table_gains_the_mark_and_the_part():
    table = _flat(_section(PANEL, "## 9. The findings table"))
    assert "| # | Round | Reviewer | Mark | Part | Finding | Outcome |" in table


# --- the reviewers' own text -------------------------------------------------


def test_correctness_reviewer_points_to_rule_md():
    agent = _flat(_read("agents/correctness-reviewer.md"))
    assert "**When the scratch directory holds `rule.md`, follow it.**" in agent
    assert "Where it and this file differ, `rule.md` wins." in agent
    for name in ("`bar.md`", "`since.patch`"):
        assert name in agent, name


def test_ui_explorer_points_to_rule_md():
    agent = _flat(_read("agents/ui-explorer.md"))
    assert "**When you're given a `rule.md`, follow it.**" in agent
    assert "your steps to reproduce, what you expected and what you saw are the reproducer" in agent


# --- since.patch, run for real ----------------------------------------------


def _since_command(scratch, last: str) -> str:
    command = _fence_after(_inputs(), "`since.patch`, from the second review")
    return command.replace("origin/<base>", "main").replace("<last>", last).replace("<scratch>", str(scratch))


@pytest.fixture
def pr(tmp_path, _no_user_git_config):
    """A pull request reviewed at `last`, then the base moved and was merged
    in, then one more change of its own."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    (root / "f.txt").write_text("".join(f"{c}\n" for c in "abcdefghij"))
    (root / "g.txt").write_text("x\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    git(root, "checkout", "-qb", "feat")
    (root / "f.txt").write_text((root / "f.txt").read_text().replace("b\n", "B-reviewed\n"))
    git(root, "commit", "-qam", "reviewed")
    last = git(root, "rev-parse", "HEAD").strip()
    return root, last


def _move_base(root, old: str, new: str):
    git(root, "checkout", "-q", "main")
    (root / "f.txt").write_text((root / "f.txt").read_text().replace(old, new))
    (root / "g.txt").write_text("y\n")
    git(root, "commit", "-qam", "base moved")
    git(root, "checkout", "-q", "feat")


def test_since_patch_leaves_out_the_base_and_what_was_reviewed(pr, tmp_path):
    root, last = pr
    _move_base(root, "i\n", "I-base\n")
    git(root, "merge", "-q", "--no-edit", "main")
    (root / "f.txt").write_text((root / "f.txt").read_text().replace("d\n", "D-new\n"))
    git(root, "commit", "-qam", "new")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    subprocess.run(["bash", "-c", _since_command(scratch, last)], cwd=root, check=True, capture_output=True)
    since = (scratch / "since.patch").read_text()
    assert "+D-new" in since and "-d" in since
    assert "I-base" not in since and "g.txt" not in since
    assert "+B-reviewed" not in since


def test_since_patch_without_a_base_merge_is_the_commits_since(pr, tmp_path):
    root, last = pr
    (root / "f.txt").write_text((root / "f.txt").read_text().replace("d\n", "D-new\n"))
    git(root, "commit", "-qam", "new")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    subprocess.run(["bash", "-c", _since_command(scratch, last)], cwd=root, check=True, capture_output=True)
    assert (scratch / "since.patch").read_text() == git(root, "diff", last, "HEAD")


def test_since_patch_is_not_written_when_the_reviewed_change_conflicts_with_the_base(pr, tmp_path):
    root, last = pr
    _move_base(root, "b\n", "B-base\n")
    merged = subprocess.run(["git", "merge", "-q", "--no-edit", "main"], cwd=root, capture_output=True, text=True)
    assert merged.returncode != 0
    (root / "f.txt").write_text((root / "f.txt").read_text().split("<<<<<<<")[0] + "B-both\n" + (root / "f.txt").read_text().split(">>>>>>> main\n")[1])
    git(root, "commit", "-qam", "merged")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    done = subprocess.run(["bash", "-c", _since_command(scratch, last)], cwd=root, capture_output=True)
    assert done.returncode != 0
    assert not (scratch / "since.patch").exists()
    # The text says what that means: the whole change is new to the review.
    assert "write no `since.patch`" in _flat(_inputs())


# --- the changelog -----------------------------------------------------------


def test_the_changelog_notes_it_under_unreleased():
    notes = since_0110()
    assert "#374" in notes
    note = notes.split("#374", 1)[0].rsplit("\n\n**", 1)[1] + notes.split("#374", 1)[1].split("\n\n**", 1)[0]
    for words in ("`rule.md`", "reproducer", "critical", "`since.patch`", "`bar.md`", "`--findings`"):
        assert words in note, words
