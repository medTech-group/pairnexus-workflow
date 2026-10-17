"""One support promise, worded the same everywhere, and the issue template for
a Claude Code update that breaks the guard or a hook (#97)."""

import re
from pathlib import Path
from changelog_notes import since_0110

KIT = Path(__file__).resolve().parents[1]

# The promise, in the words every file uses.
PROMISES = (
    "best effort, with no guaranteed response time for issues or pull requests",
    "security reports acknowledged within 5 working days",
    "a fix release when a Claude Code update breaks the guard or the hooks",
)

TEMPLATE = KIT / ".github" / "ISSUE_TEMPLATE" / "claude-code-break.md"


def _text(rel: str) -> str:
    return (KIT / rel).read_text(encoding="utf-8")


def _plain(text: str) -> str:
    """Lower case, with Markdown emphasis and runs of whitespace (line breaks
    included) made plain, so a promise reads the same wrapped or in a list."""
    return re.sub(r"\s+", " ", text.replace("*", "")).lower()


def _section(text: str, heading: str) -> str:
    """A section's text, from its heading to the next heading of its level or above."""
    level = len(heading) - len(heading.lstrip("#"))
    m = re.search(rf"^{re.escape(heading)}[ \t]*\n(.*?)(?=^#{{1,{level}}} |\Z)", text, re.M | re.S)
    assert m, f"no {heading!r}"
    return m.group(1)


def _anchors(text: str) -> list[str]:
    """GitHub's anchors for a README's headings (lower case, punctuation dropped,
    spaces to hyphens), one per heading, leaving out fenced code blocks."""
    text = re.sub(r"^```.*?^```", "", text, flags=re.M | re.S)
    titles = re.findall(r"^#{1,6} (.+?)[ \t]*$", text, re.M)
    return [re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-") for title in titles]


def _status_note(readme: str) -> list[str]:
    m = re.search(r"^> \[!NOTE\]\n((?:>.*\n)+)", readme, re.M)
    assert m, "the README has no status note"
    return m.group(1).splitlines()


def test_the_three_promises_read_the_same_everywhere():
    places = {
        "README.md's Support": _section(_text("README.md"), "### Support"),
        "SECURITY.md": _text("SECURITY.md"),
        "CONTRIBUTING.md": _text("CONTRIBUTING.md"),
    }
    for where, text in places.items():
        for promise in PROMISES:
            assert promise.lower() in _plain(text), f"{where} doesn't say: {promise}"


def test_contributing_gives_the_promise_at_its_opening():
    opening = _text("CONTRIBUTING.md").split("\n## ", 1)[0]
    for promise in PROMISES:
        assert promise.lower() in _plain(opening), promise


def test_support_section_says_how_to_report_each():
    support = _section(_text("README.md"), "### Support")
    how = support.split("How to report each:", 1)[1]
    assert "/pairnexus-workflow/issues)" in how
    assert "/issues/new?template=claude-code-break.md)" in how
    assert re.search(r"privately, as \[SECURITY\.md\]\(SECURITY\.md\)", how)


def test_support_section_is_in_the_contents():
    readme = _text("README.md")
    contents = readme.split("**Contents**", 1)[1].split("\n## ", 1)[0]
    assert "](#support)" in contents
    assert _anchors(readme).count("support") == 1


def test_status_note_gives_the_promise_in_one_line_linking_support():
    readme = _text("README.md")
    lines = [l for l in _status_note(readme) if "**Support:**" in l]
    assert len(lines) == 1
    line = lines[0]
    for promise in PROMISES:
        assert promise.lower() in _plain(line), promise
    assert "Maintained by PAIR (MedTech LLC)".lower() in _plain(line)
    links = re.findall(r"\]\(#([^)]+)\)", line)
    assert links == ["support"]


def test_security_keeps_its_5_working_day_acknowledgement():
    assert "acknowledge a report within 5 working days" in _plain(_text("SECURITY.md"))


def test_changelog_notes_are_under_unreleased():
    unreleased = since_0110(_text("CHANGELOG.md"))
    assert "#97" in unreleased
    assert "claude-code-break.md" in unreleased


def _template() -> tuple[dict[str, str], str]:
    """The issue template's front matter, and its body."""
    m = re.match(r"---\n(.*?)\n---\n(.*)", TEMPLATE.read_text(encoding="utf-8"), re.S)
    assert m, "no front matter"
    return dict(l.split(":", 1) for l in m.group(1).splitlines()), m.group(2)


def test_issue_template_asks_for_the_versions_and_labels_the_report():
    front, body = _template()
    assert "after a Claude Code update" in front["name"]
    assert re.findall(r"[\w-]+", front["labels"]) == ["claude-code-break"]
    for asked in ("`claude --version`", "`workflow version`", "Vendored or plugin", "What you ran", "What happened instead"):
        assert asked in body, asked


def test_issue_template_sends_a_guard_bypass_to_the_private_report_first():
    top = _template()[1].strip().split("\n\n", 1)[0]
    assert "past the guard" in top
    assert "security problem" in top
    assert "/security/advisories/new" in top
    assert "SECURITY.md" in top
    assert "never with this template" in top
