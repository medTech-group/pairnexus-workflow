"""#82: "In plain words" at the top of every pull request `build-ticket` opens,
read as the kit-release tests read skills (#39's seam 3)."""

import re

from conftest import KIT

HEADINGS = ["## In plain words", "**What changes for you**", "**How to try it**", "**What could go wrong**"]


def _read(rel: str) -> str:
    return (KIT / rel).read_text(encoding="utf-8")


def _pr_step() -> str:
    """build-ticket's step 4, where the PR body is described."""
    text = _read("skills/build-ticket/SKILL.md")
    return text.split("## 4. Open the pull request", 1)[1].split("\n## 5.", 1)[0]


def _template() -> str:
    """The fenced block in step 4 that shows the section's exact headings."""
    blocks = re.findall(r"```markdown\n(.*?)```", _pr_step(), re.S)
    assert len(blocks) == 1, "step 4 shows the section's headings in one ```markdown block"
    return blocks[0]


def test_the_pr_body_opens_with_in_plain_words_and_its_three_parts_in_order():
    block = _template()
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    # Each heading on a line of its own, in the order #83's template copies.
    assert [line for line in lines if line in HEADINGS] == HEADINGS
    assert lines[0] == "## In plain words"


def test_in_plain_words_comes_above_everything_the_body_had_before():
    step = _pr_step()
    assert "Its body opens with **In plain words**, above everything else" in step
    first = step.index("## In plain words")
    for later in ("`Closes #<n>`", "what was built", "how it was tested", "the findings table", '"Decisions for the owner"', "the by-hand checks"):
        assert later in step, later
        assert first < step.index(later), f"{later!r} comes before In plain words"
    # The list below it is the one the body had before, introduced as unchanged.
    assert "Below it, unchanged:\n- `Closes #<n>`;" in step


def test_each_part_says_what_goes_in_it():
    step = _pr_step()
    assert "one to three sentences about what a user notices, not the code" in step
    assert "easy or hard to undo" in step
    assert "what it could affect" in step


def test_how_to_try_it_names_its_three_cases():
    step = _pr_step()
    how = step.split("- `**How to try it**`:", 1)[1].split("\n- `**What could go wrong**`:", 1)[0]
    assert "the try-it link" in how and "two or three things to click" in how
    assert "where the link will appear" in how
    assert "another way" in how
    assert '"Nothing to try: this change is behind the scenes"' in how
    # The cases are tried in that order.
    assert how.index("the try-it link") < how.index("where the link will appear") < how.index("another way")
    # No project has preview links yet, so the note points at the last case, never "will appear".
    note = how.split("so for now", 1)[1]
    assert "another way" in note and '"Nothing to try"' in note
    assert "will appear" not in note


def test_the_guidance_names_each_part_by_its_exact_heading():
    # The bullets quote the headings as written, so no other form (a colon inside the bold) is copied.
    step = _pr_step()
    for heading in HEADINGS[1:]:
        assert f"- `{heading}`:" in step, heading
    assert "**What changes for you:**" not in step


def test_the_example_is_marked_as_an_example():
    step = _pr_step()
    assert "(the text here is only an example)" in step
    # A change a user sees is tried another way, not "Nothing to try".
    assert "Nothing to try" not in _template()


def test_the_section_is_the_same_for_everyone():
    step = _pr_step()
    assert "same for everyone" in step
    assert "never worded by experience" in step


def test_the_examples_are_everyday_ones():
    low = _pr_step().lower()
    assert "notes" in low
    assert "patient" not in low and "pair-drop" not in low


def test_flow_section_3_lists_in_plain_words_first_in_the_pr_body():
    flow = _read("docs/flow.md")
    section = flow.split("## 3. Building", 1)[1].split("\n## 4.", 1)[0]
    step = next(line for line in section.splitlines() if line.startswith("4. **Pull request**"))
    body = step.split(":", 1)[1]
    assert body.lstrip().startswith('"In plain words"'), step
    assert body.index('"In plain words"') < body.index("`Closes #<n>`")


def test_the_glossarys_pull_request_entry_mentions_in_plain_words():
    text = _read("docs/glossary.md")
    entry = text.split("### Pull request (PR)", 1)[1].split("\n### ", 1)[0]
    assert '"In plain words"' in entry
    for part in ("what changes for you", "how to try it", "what could go wrong"):
        assert part in entry, part


def test_build_ticket_puts_the_pr_skills_sections_below_it():
    assert "If the `pr` skill is loaded too, its sections go below; the body still opens with `## In plain words`." in _pr_step()


def test_the_vendored_pr_skill_is_left_as_it_is():
    # Matt Pocock's `pr` skill stays as vendored (#30): the section lives in build-ticket.
    assert "In plain words" not in _read(".claude/skills/pr/SKILL.md")


def test_the_changelog_notes_it_under_unreleased():
    text = _read("CHANGELOG.md")
    unreleased = text.split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    assert "(#82" in unreleased
    assert "In plain words" in unreleased
