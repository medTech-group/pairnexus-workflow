"""#77: the quickstart, `docs/quickstart.md`, and the README's "New to building?
Start here", read as files (#35's seam 1)."""

import re

import pytest
from conftest import KIT
from test_glossary import MENTIONS, PARTS, _slug

from changelog_notes import since_0110
from workflow import vendor

QUICKSTART = KIT / "docs/quickstart.md"
README = KIT / "README.md"
LINK = re.compile(r"\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\(([^)\s]+)\)")


def _text() -> str:
    return QUICKSTART.read_text(encoding="utf-8")


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def _steps() -> list[str]:
    """The numbered steps' text, each from its number to the next step or heading."""
    return [m.group(2) for m in re.finditer(r"^(\d+)\. (.*?)(?=^\d+\. |^#|\Z)", _text(), re.M | re.S)]


def _anchors(text: str) -> set[str]:
    """GitHub's anchors for a file's headings, those in blockquotes included
    (the README's callout has one), leaving out fenced code blocks."""
    text = re.sub(r"^```.*?^```", "", text, flags=re.M | re.S)
    return {_slug(t) for t in re.findall(r"^(?:>[ \t]*)?#{1,6} (.+?)[ \t]*$", text, re.M)}


def _mention(anchor: str, text: str) -> re.Match | None:
    """The first use of a glossary word; `main` is matched by its case."""
    return re.search(MENTIONS[anchor], text, re.I if anchor != "main" else 0)


def _blockquotes(text: str) -> list[str]:
    """Each run of `>` lines, as plain words."""
    runs = re.findall(r"(?:^[ \t]*>.*\n?)+", text, re.M)
    return [" ".join(re.sub(r"^[ \t]*>[ \t]?", "", r, flags=re.M).split()) for r in runs]


def test_the_quickstart_has_at_most_ten_numbered_steps_in_order():
    numbers = [int(n) for n in re.findall(r"^(\d+)\. ", _text(), re.M)]
    assert 1 <= len(numbers) <= 10
    assert numbers == list(range(1, len(numbers) + 1))
    # Sub-steps are bullets, so a numbered line is always a step, and every
    # step is numbered the same way.
    assert not re.search(r"^[ \t]+\d+\. ", _text(), re.M)
    assert not re.search(r"^[ \t]*\d+\) ", _text(), re.M)


def test_it_opens_with_how_long_it_takes_and_what_you_will_have():
    intro = _text().split("\n1. ", 1)[0]
    assert "10 minutes" in intro
    assert "merged" in intro
    assert "nothing to install" in intro.lower()


def test_it_gives_the_clicks_for_the_desktop_app_and_the_browser():
    text = _text()
    assert "**Cloud**" in text
    assert "claude.ai/code" in text


def _plain_with_links(text: str) -> tuple[str, list[tuple[int, int, str]]]:
    """The text with each link reduced to its words, and where each link's
    words sit with its target."""
    plain, spans, at = [], [], 0
    for m in LINK.finditer(text):
        plain.append(text[at:m.start()])
        start = sum(len(p) for p in plain)
        plain.append(m.group(1))
        spans.append((start, start + len(m.group(1)), m.group(2)))
        at = m.end()
    plain.append(text[at:])
    return "".join(plain), spans


@pytest.mark.parametrize("anchor", [a for w in PARTS.values() for a in w.values()])
def test_each_glossary_word_links_to_its_entry_at_its_first_use(anchor):
    plain, spans = _plain_with_links(_text())
    m = _mention(anchor, plain)
    if not m:
        return
    target = f"glossary.md#{anchor}"
    linked = [t for s, e, t in spans if s <= m.start() < e]
    assert linked == [target], (
        f"the first use of {anchor!r} ({plain[max(0, m.start() - 30):m.end() + 10]!r}) "
        f"should link to {target}"
    )


def test_it_uses_the_glossary_words_a_first_change_meets():
    plain, _ = _plain_with_links(_text())
    for anchor in ("repository", "main", "pull-request-pr", "checks-ci", "merge", "revert",
                   "cloud-session", "guided-start", "solo-mode", "protect-main",
                   "unattended-run", "check-the-set-up"):
        assert _mention(anchor, plain), anchor


def test_every_link_and_anchor_resolves_to_a_file_or_heading_that_exists():
    text = _text()
    links = [t for _, t in LINK.findall(text)]
    assert links
    # A link this check can't read (a title, a reference) would go unchecked.
    assert text.count("](") == len(links) and "][" not in text
    for link in links:
        if link.startswith("https://"):
            continue
        assert not link.startswith("http://"), link
        path, _, anchor = link.partition("#")
        target = (QUICKSTART.parent / path).resolve() if path else QUICKSTART
        assert target.is_file(), f"{link}: no such file"
        assert KIT in target.parents, f"{link}: outside the kit"
        if anchor:
            assert anchor in _anchors(target.read_text(encoding="utf-8")), f"{link}: no such heading"


def test_it_links_the_readme_sections_it_names():
    links = {t for _, t in LINK.findall(_text())}
    assert "../README.md#protect-main" in links
    assert "../README.md#step-6-check-it" in links
    assert "../README.md#set-up-unattended-runs" in links


def test_its_facts_link_claudes_and_githubs_own_docs():
    # Steps 1, 2 and 4: the plans, the GitHub connection, the Default environment.
    steps = _steps()
    for n in (1, 2, 4):
        assert "](https://code.claude.com/docs/" in steps[n - 1], f"step {n}"
    # Step 2's GitHub App facts link GitHub's own docs.
    assert "](https://docs.github.com/" in steps[1]
    links = {t for _, t in LINK.findall(_text())}
    assert "https://github.com/apps/claude" in links or any(
        l.startswith("https://github.com/apps/claude/") for l in links)
    assert "https://github.com/new" in links


def _next_steps() -> list[str]:
    """The last step's bullets, each as its words, links reduced to their text."""
    bullets = [l for l in _steps()[-1].splitlines() if l.strip().startswith("- ")]
    return [_plain_with_links(l)[0] for l in bullets]


def test_the_next_steps_name_the_three_upgrades_each_optional():
    lines = _next_steps()
    for name in ("Protect `main`", "Check the set-up", "Set up unattended runs"):
        line = [l for l in lines if name.lower() in l.lower()]
        assert len(line) == 1, name
        assert "optional" in line[0].lower(), f"{name} isn't marked optional"


def test_the_protect_main_line_matches_the_readme():
    line = next(l for l in _next_steps() if "Protect `main`" in l)
    assert "with `gh` signed in" in line and "does it for you" in line
    assert "cloud session" in line and "guided clicks" in line
    assert "checks" in line and "once ci has run" in line.lower()
    readme = _readme().split("### Protect `main`", 1)[1].split("\n### ", 1)[0]
    assert "with `gh` signed in" in readme and "guided clicks" in readme.lower()
    assert "Checks are required once CI has run" in readme


def test_the_check_the_set_up_line_names_the_skill():
    line = next(l for l in _next_steps() if "check the set-up" in l.lower())
    assert "`check-setup`" in line


# The choices steps 6 and 7 tell the reader to pick, and the skill that shows each.
CHOICES = {
    "skills/setup-workflow/SKILL.md": ["Not now"],
    "skills/start/SKILL.md": [
        "A brand-new project or a large effort",
        "Something new, or a change to what's there",
        "Quick ticket",
    ],
}


@pytest.mark.parametrize("skill,label", [(k, l) for k, ls in CHOICES.items() for l in ls])
def test_the_choices_it_names_are_the_skills_own(skill, label):
    # A skill that renames a choice would send the reader to one that isn't there.
    assert f"**{label}**" in _text()
    assert f"**{label}**" in (KIT / skill).read_text(encoding="utf-8"), f"{skill} has no {label!r}"


def _readme_step1_message() -> str:
    step1 = _readme().split("### Step 1.", 1)[1].split("\n### ", 1)[0]
    quotes = _blockquotes(step1.split("Send this message", 1)[1])
    assert quotes, "the README's Step 1 has no message"
    return quotes[0]


def test_the_set_up_message_is_the_readmes_step_1_message_word_for_word():
    message = _readme_step1_message()
    assert message.startswith("Set this repository up with the pairnexus workflow")
    assert message in _blockquotes(_text())
    # In the step that sends it.
    step = next(s for s in _steps() if "set-up message" in s.lower())
    assert message in _blockquotes(step)


def test_the_readmes_first_line_after_the_title_links_the_quickstart():
    lines = [l for l in _readme().splitlines() if l.strip()]
    assert lines[0] == "# pairnexus-workflow"
    assert lines[1] == "**[New to building? Start here](docs/quickstart.md)**"


def test_a_vendored_copy_leaves_the_quickstart_out():
    assert "quickstart.md" in vendor.SKIP_DOCS
    files = vendor.plan(KIT, None)
    assert not any(p.endswith("quickstart.md") for p in files)
    assert ".claude/workflow/docs/glossary.md" in files


def test_contributing_says_the_quickstart_doesnt_ship():
    text = (KIT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    ships = text.split("**What ships.**", 1)[1].split("\n\n", 1)[0]
    assert "`docs/`, except `proposal.md`, `spike.md` and `quickstart.md`" in ships


def test_the_quickstart_names_no_project_of_ours():
    # #37's names test: everyday examples only.
    low = _text().lower()
    assert "patient" not in low
    assert "pair-drop" not in low


def test_the_changelog_has_a_note_for_it():
    notes = since_0110()
    assert "`docs/quickstart.md`" in notes
    assert "New to building? Start here" in notes
