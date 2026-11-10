"""The architecture overview's and example page's templates (#612, spec #611
seam 3): the standing rules, the rules for code no page covers, and the page
form, as the kit's text."""

import re
from pathlib import Path

from changelog_notes import since_0110
from workflow import architecture

KIT = Path(__file__).resolve().parents[1]
OVERVIEW = (KIT / "templates/architecture-overview.md").read_text()
PAGE = (KIT / "templates/architecture-page.md").read_text()


def _section(text, heading):
    m = re.search(rf"^{re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    assert m, heading
    return m.group(1)


def _flat(text):
    return " ".join(text.split())


def test_the_overview_has_its_headings():
    for h in ("## Standing rules", "## Cross-cutting rules", "## Writing a page"):
        assert re.search(rf"^{re.escape(h)}$", OVERVIEW, re.M), h


def test_the_overview_names_no_kit_issue_numbers():
    assert not re.search(r"#\d", OVERVIEW)


def test_the_overview_never_points_to_the_example_page():
    assert "architecture-page" not in OVERVIEW


def test_pages_are_added_as_code_is_built():
    assert "Pages are added as code is built" in OVERVIEW


def test_structural_lines_go_in_the_same_pull_request():
    s = _flat(_section(OVERVIEW, "## Standing rules"))
    assert "A change that makes a structural decision writes its line in the same pull request, in the page it belongs to." in s
    assert "A cross-cutting rule goes in this overview" in s
    for part in ("what a page owns", "its interface", "its own rules", "its helpers", "its decisions", "the cross-cutting rules"):
        assert part in s, part


def test_lines_in_this_folder_are_never_on_a_stay_out_list_and_no_more():
    s = _flat(_section(OVERVIEW, "## Standing rules"))
    assert "Lines in this folder are always the change's own: they are never another area's files and never on a run's stay-out list." in s
    assert "whatever else it is told to stay out of" not in s


def test_the_rules_block():
    assert "a change that breaks one is blocked" in _flat(OVERVIEW)


def test_a_new_module_adds_its_full_page():
    s = _flat(_section(OVERVIEW, "## Standing rules"))
    assert "A change that adds a new module adds its page in the same pull request." in s
    assert "A new module is a new folder of code that no page covers and that held no code before." in s
    assert "A new file in an existing folder that no page covers is old code: it is left to the architecture pass" in s
    assert "its `Covers:` spans the folder" in s and "what the module owns and gives its interface" in s
    assert "the outermost new folder gets the page" in s


def test_code_is_as_doctor_counts_it():
    s = _flat(OVERVIEW)
    assert "what the kit's doctor counts: the profile's `guard.code_paths` when they are set, else every tracked file outside `docs/` and the protected paths" in s
    assert "files at the repository's root, the documents in the profile's `project.rules` and the profile's `guard.test_paths` aren't code" in s


def test_the_reuse_rule_and_its_exceptions():
    s = _flat(_section(OVERVIEW, "## Standing rules"))
    assert "A change doesn't add a copy of logic that already exists: it uses the shared helper, or moves the logic into one, used in its own code, and lists it in its page." in s
    assert "Copies already in the code are left to the architecture pass." in s
    assert "When moving the logic would touch another area's files during a run, or a protected path, the copy doesn't block. A ticket to merge the copies is always filed: an owner task when the move would touch a protected path." in s


def test_code_no_page_covers_goes_in_a_small_page():
    s = _flat(_section(OVERVIEW, "## Standing rules"))
    assert "A structural line about a file no page covers, an old file or a new one, outside a new module's folder, goes in a small page" in s
    assert "its folders joined with `--`, with a dot at the start of the name dropped: `src/orders/check.py` → `src--orders.md`, `.tools/lint/check.py` → `tools--lint.md`" in s
    assert "A file at the repository's root** has its line in `_root.md`" in s
    assert "A top-level folder named `_root` would share that page: a rare clash" in s
    assert "each `*`, `?` and `[` in it in brackets (`[*]`, `[?]`, `[[]`)" in s
    assert "The page is created if it doesn't exist, and added to if it does: two changes touching one folder write to the same page." in s
    assert "A small page needs only its `Covers:` lines and the changes' lines until the architecture pass. The rest of the folder stays noted by doctor" in s
    assert "A helper moved into a new folder goes on that folder's page." in s
    assert "A new module (above) gets a full page instead." in s


def test_writing_a_page_gives_the_form():
    s = OVERVIEW.split("\n## Writing a page\n", 1)[1]  # the last section; its example holds `## ` headings
    flat = _flat(s)
    assert "A page is a Markdown file directly in this folder, other than this `README.md`." in flat
    assert "Files in subfolders, and files that aren't `.md` (other than another spelling of `README.md`, such as `README.MD`, which is a page), are neither pages nor read." in flat
    assert "one glob on each line, never two on one line" in flat
    assert "A page with no `Covers:` line covers nothing yet" in flat
    assert "**`Interface:`** is one line" in flat
    assert "written ``- `name`: what it's for``" in flat
    assert "**`## Rules`** holds the page's own written rules." in flat
    assert "each decision is one line, linking the ADR or pull request that made it" in flat
    assert "no size limit" in flat and "no diagram is required" in flat
    example = re.search(r"```markdown\n(.*?)```", s, re.S).group(1)
    page = architecture.parse("docs/architecture/orders.md", example)
    assert page.covers == ["src/orders/**", "src/shared/money.py"]
    assert page.interface and page.helpers == [("check_input", "validates an order's fields, with the shared error messages.")]
    assert "## Rules" in example


def test_the_example_page_reads_as_a_page():
    page = architecture.parse("docs/architecture/notes.md", PAGE)
    assert page.covers == ["src/notes/**", "src/shared/text.py"]
    assert page.interface.startswith("`NotesStore`")
    assert [n for n, _ in page.helpers] == ["clean_body", "preview"]
    assert all(w for _, w in page.helpers)
    assert "\n## Rules\n" in PAGE


def test_the_changelog_notes_say_the_overview_is_never_a_page():
    note = _flat(since_0110().split("(#612,", 1)[1].split("\n\n**", 1)[0])
    assert "A page is a `.md` file directly in `docs/architecture/` other than the overview (#631), or another spelling of `README.md`, such as `README.MD`; files in subfolders and other files are ignored." in note
    assert "For now `README.md` is also read as a page" not in note
    assert "with no `Covers:` line, one that covers nothing yet" not in note
    note = _flat(since_0110().split("(#631,", 1)[1].split("\n\n**", 1)[0])
    assert "The overview is the file the folder lists as exactly `docs/architecture/README.md`" in note
    assert "every other `.md` file directly in the folder is a page" in note
    assert "`index pages` never lists the overview" in note
    assert "`index reads` prints it once, first, never under `--json`'s `\"pages\"`" in note
    assert "A case variant (`Readme.md`, `readme.md`) with no `README.md` beside it is a page, listed once" in note
    assert "So is one whose extension's case differs too (`README.MD`)" in note
