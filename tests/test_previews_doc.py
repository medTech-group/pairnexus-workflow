"""#114: `docs/previews.md`, "Add try-it links to your pull requests", read as a
file (#41's seam 3), with the quickstart's next step and the glossary's
"preview link" entry that point to it."""

import re
import tomllib

import pytest
from conftest import KIT
from test_glossary import PARTS, _slug
from test_quickstart import LINK, _anchors, _mention, _next_steps, _plain_with_links

from changelog_notes import since_0110
from workflow import vendor

PAGE = KIT / "docs/previews.md"
TITLE = "# Add try-it links to your pull requests"
# The headings #115 (doctor), #116 (the upgrade) and #117 (the preview's
# readers) link to, with GitHub's anchors. Renaming one breaks their links.
HEADINGS = {
    "The steps": "the-steps",
    "When a build fails": "when-a-build-fails",
    "What to expect": "what-to-expect",
}


def _text() -> str:
    return PAGE.read_text(encoding="utf-8")


def _body() -> str:
    """The page below its title: the title is the page's name, and its words
    are linked where the text first uses them."""
    first, _, rest = _text().partition("\n")
    assert first == TITLE
    return rest


def _section(heading: str) -> str:
    return _text().split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]


def _steps() -> list[str]:
    """The numbered steps, each from its number to the next step or heading."""
    return [m.group(2) for m in re.finditer(r"^(\d+)\. (.*?)(?=^\d+\. |^#|\Z)", _section("The steps"), re.M | re.S)]


def _words(text: str) -> str:
    """The text as one line, links reduced to their words."""
    return " ".join(_plain_with_links(text)[0].split())


def test_the_page_is_titled_add_try_it_links_to_your_pull_requests():
    assert _text().startswith(TITLE + "\n")


def test_the_headings_later_tickets_link_are_there_with_their_anchors():
    headings = re.findall(r"^## (.+?)[ \t]*$", _text(), re.M)
    for heading, anchor in HEADINGS.items():
        assert heading in headings, heading
        assert _slug(heading) == anchor


def test_the_steps_are_seven_numbered_in_order():
    numbers = [int(n) for n in re.findall(r"^(\d+)\. ", _section("The steps"), re.M)]
    assert numbers == list(range(1, 8))
    # The rest of the page has no numbered steps, so a step can't hide there.
    assert len(re.findall(r"^\d+\. ", _text(), re.M)) == 7


def test_step_1_is_a_cloudflare_account():
    assert "Cloudflare account" in _words(_steps()[0])


def test_step_2_connects_only_this_repository_through_cloudflares_github_app():
    step = _words(_steps()[1])
    assert "GitHub app" in step
    assert "**Only select repositories**" in _steps()[1]


def test_step_3_empties_the_build_command_on_production_and_previews_base_and_names_the_trap():
    step = _words(_steps()[2])
    assert step.startswith("**An empty Build command") and "clear the **Build command** box" in _steps()[2]
    assert "**Production**" in _steps()[2] and "**Previews Base**" in _steps()[2]
    # The trap: Previews Base is a template a branch copies when it's first
    # built, so a branch built before the fix keeps the old command.
    assert "template" in step
    assert "first built" in step
    assert "fresh branch" in step and "retry" in step


def test_step_4_is_a_new_build_token():
    step = _steps()[3]
    assert "new build token" in _words(step)
    assert "**Create new token**" in step


def test_step_5_turns_preview_urls_on_which_are_off_by_default():
    step = _words(_steps()[4])
    assert "Preview URLs" in step and "off by default" in step
    # Cloudflare's own words while they're off, so the reader recognises them.
    assert "they will not create Preview URLs until you enable them" in step


def test_step_6_gives_the_previews_block_and_no_live_site():
    step = _steps()[5]
    assert "`[previews]`" in step
    assert "`workers_dev = false`" in step and "`preview_urls = true`" in step
    assert "no live site" in _words(step).lower()


def test_step_6s_wrangler_config_reads_as_toml_with_no_live_site():
    [block] = re.findall(r"```toml\n(.*?)```", _steps()[5], re.S)
    config = tomllib.loads(re.sub(r"^ {3}", "", block, flags=re.M))
    assert config["workers_dev"] is False
    assert config["preview_urls"] is True
    assert config["previews"] == {}


def test_step_7_is_cloudflare_access_for_sensitive_data_confirmed_by_the_owner():
    step = _words(_steps()[6])
    assert "Cloudflare Access" in step and "sensitive data" in step
    # #37's rule for examples: phone numbers or payment details.
    assert "phone numbers" in step and "payment details" in step
    # The kit can't check Access itself, and relies on the owner's word.
    assert "can't check Access itself" in step
    assert "`access = true`" in step
    assert "Without Access" in step and "no previews" in step


@pytest.mark.parametrize("says,fix", [
    ("must match the name of your Worker", "Step 3"),
    ("missing a `previews` block", "Step 6"),
    ("Configured API token unavailable", "Step 4"),
])
def test_each_build_log_failure_has_its_fix_beside_it(says, fix):
    rows = [r for r in _section("When a build fails").splitlines() if r.startswith("|") and says in r]
    assert len(rows) == 1, says
    assert fix in rows[0]


def test_what_to_expect_says_where_the_link_arrives_how_long_and_made_up_data_only():
    part = _words(_section("What to expect"))
    assert "comment" in part and "check" in part
    assert "four minutes" in part
    assert "made-up data" in part
    assert "public" in part


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
        target = (PAGE.parent / path).resolve() if path else PAGE
        assert target.is_file(), f"{link}: no such file"
        if anchor:
            assert anchor in _anchors(target.read_text(encoding="utf-8")), f"{link}: no such heading"


def test_its_relative_links_stay_among_the_docs_a_project_receives():
    # The page ships, so a link outside `docs/` or to a doc that doesn't ship
    # would be dead in a project's `.claude/workflow/docs/`.
    for _, link in LINK.findall(_text()):
        path = link.partition("#")[0]
        if link.startswith("https://") or not path:
            continue
        assert "/" not in path, f"{link}: link only to docs beside it"
        assert path not in vendor.SKIP_DOCS, f"{link}: {path} doesn't ship"


@pytest.mark.parametrize("anchor", [a for w in PARTS.values() for a in w.values()])
def test_each_glossary_word_links_to_its_entry_at_its_first_use(anchor):
    plain, spans = _plain_with_links(_body())
    m = _mention(anchor, plain)
    if not m:
        return
    target = f"glossary.md#{anchor}"
    linked = [t for s, e, t in spans if s <= m.start() < e]
    assert linked == [target], (
        f"the first use of {anchor!r} ({plain[max(0, m.start() - 30):m.end() + 10]!r}) "
        f"should link to {target}"
    )


def test_it_uses_the_glossary_words_a_reader_meets():
    plain, _ = _plain_with_links(_body())
    for anchor in ("pull-request-pr", "preview-link", "merge", "repository", "branch", "main", "checks-ci", "profile"):
        assert _mention(anchor, plain), anchor


def test_the_page_names_no_project_of_ours():
    # #37's names test: everyday examples only.
    low = _text().lower()
    assert "patient" not in low
    assert "pair-drop" not in low


def test_a_vendored_copy_carries_the_page():
    files = vendor.plan(KIT, None)
    assert files[".claude/workflow/docs/previews.md"] == PAGE


def test_vendoring_writes_the_page_into_a_project(tmp_path):
    vendor.install(KIT, tmp_path, None, no_mattpocock=True)
    assert (tmp_path / ".claude/workflow/docs/previews.md").read_text(encoding="utf-8") == _text()


def test_the_quickstarts_next_steps_offer_add_try_it_links_as_optional():
    [line] = [l for l in _next_steps() if "Add try-it links" in l]
    assert "optional" in line.lower()
    raw = (KIT / "docs/quickstart.md").read_text(encoding="utf-8")
    [bullet] = [l for l in raw.splitlines() if l.strip().startswith("- ") and "Add try-it links" in l]
    assert "](previews.md)" in bullet


def test_the_glossarys_preview_link_entry_names_add_try_it_links():
    text = (KIT / "docs/glossary.md").read_text(encoding="utf-8")
    entry = text.split("\n### Preview link\n", 1)[1].split("\n### ", 1)[0]
    assert '"Add try-it links"' in entry
    assert len(text) < 6000


def test_the_profile_doc_links_the_page_from_its_previews_section():
    text = (KIT / "docs/profile.md").read_text(encoding="utf-8")
    section = text.split("\n## `[previews]`\n", 1)[1].split("\n## ", 1)[0]
    assert "](previews.md)" in section


def test_the_changelog_has_a_note_for_it():
    notes = since_0110()
    assert "`docs/previews.md`" in notes
    assert "Add try-it links to your pull requests" in notes
