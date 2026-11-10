"""#618: set-up and the kit's update write the architecture overview and list it
in `project.rules`, moving an existing `docs/architecture/README.md` aside once;
`upgrade-setup` gains "Write the architecture overview" and `check-setup` offers
it (spec #611, seam 3: the kit's text; answers 9 and 20 on #603)."""

import re

from conftest import KIT
from workflow import doctor

SETUP = KIT / "skills/setup-workflow/SKILL.md"
UPDATE = KIT / "skills/update-workflow/SKILL.md"
UPGRADE = KIT / "skills/upgrade-setup/SKILL.md"
CHECK = KIT / "skills/check-setup/SKILL.md"
INSTALL = KIT / "docs/install.md"
TEMPLATE = KIT / "templates/architecture-overview.md"
NAME = "Write the architecture overview"
OFFER = "write_architecture_overview"
OVERVIEW = "`docs/architecture/README.md`"
CHAINED = "never chained with the commit (`git commit … && git push`)"


def _text(path):
    return path.read_text(encoding="utf-8")


def _flat(text):
    return " ".join(text.split())


def _section(text, title, level="##"):
    m = re.search(rf"^{level} [^\n]*{re.escape(title)}[^\n]*\n(.*?)(?=^#{{1,{len(level)}}} |\Z)", text, re.M | re.S)
    assert m, f"no section {title!r}"
    return m.group(1)


def _item(text, opening):
    """The list item that opens with `opening`, with its nested lines."""
    i = text.index(opening)
    rest = text[i:]
    m = re.search(r"\n(?=- \*\*|\*\*\d+\.|\d+\. \*\*|#)", rest[1:])
    return rest if not m else rest[: m.start() + 1]


def _setup_item():
    profile_step = _text(SETUP).split("**1. The profile.**", 1)[1].split("**2. The kit.**", 1)[0]
    return _item(profile_step, "- **The architecture overview,**")


def _update_step(title):
    m = re.search(rf"^\d+\. \*\*{re.escape(title)}[^\n]*\n?(.*?)(?=^\d+\. \*\*|\Z)", _text(UPDATE), re.M | re.S)
    assert m, f"no step {title!r}"
    return m.group(0)


def _part():
    m = re.search(rf"^# {re.escape(NAME)}\n(.*?)(?=^# |\Z)", _text(UPGRADE), re.M | re.S)
    assert m, f"no part {NAME!r}"
    return m.group(1)


def _moves_once(text):
    """The move the spec settles (answer 20): once, before writing, never over an
    `earlier-overview.md`, only while `project.rules` doesn't list the overview."""
    t = _flat(text)
    assert "`docs/architecture/earlier-overview.md`" in t
    assert "only when `project.rules` doesn't list it yet" in t
    assert "never overwritten" in t and "`earlier-overview-2.md`" in t and "next free name" in t
    assert "Other files in `docs/architecture/` stay as they are" in t
    # Listed means an entry naming the overview, as doctor reads it.
    assert "a `#heading` after it and a leading `./` ignored" in t


# ---------- set-up ----------


def test_set_up_writes_the_overview_from_the_template_and_lists_it():
    item = _flat(_setup_item())
    assert f"{OVERVIEW}" in item and "`$KIT/templates/architecture-overview.md`" in item
    assert 'adds `"docs/architecture/README.md"` to `project.rules`' in item
    assert TEMPLATE.exists()


def test_set_up_moves_an_existing_readme_aside_first():
    _moves_once(_setup_item())
    item = _flat(_setup_item())
    assert item.index("earlier-overview.md") < item.index("Then write")


def test_set_up_writes_the_overview_before_profile_check_runs():
    text = _text(SETUP)
    profile_step = text.split("**1. The profile.**", 1)[1].split("**2. The kit.**", 1)[0]
    assert profile_step.index("- **The architecture overview,**") < profile_step.index("- Run `WF profile check`")


def test_set_ups_pull_request_and_checklist_name_the_overview():
    text = _text(SETUP)
    pr = _section(text, "4. The pull request")
    assert "the architecture overview" in pr and "`earlier-overview" in pr
    checklist = _section(text, "Checklist")
    assert any("architecture overview" in ln for ln in checklist.splitlines() if ln.startswith("- [ ]"))


# ---------- update ----------


def test_update_writes_and_lists_the_overview_in_the_update_that_brings_it_in():
    step = _flat(_update_step("The architecture overview"))
    assert "in the update that brings it in" in step.lower()
    assert '"For projects updating"' in step
    assert "`$KIT/templates/architecture-overview.md`" in step
    assert 'adds `"docs/architecture/README.md"` to `project.rules`' in step


def test_update_moves_an_existing_readme_aside_once():
    _moves_once(_update_step("The architecture overview"))


def test_later_updates_leave_the_overview_alone():
    step = _flat(_update_step("The architecture overview"))
    assert "Later updates leave it alone" in step
    assert "never compare it with the template" in step
    # Not among the files set-up copied once, which each update compares.
    copied = _flat(_update_step("Check it"))
    assert "architecture-overview" not in copied


def test_the_overview_comes_before_who_writes_code_and_is_in_the_pr():
    text = _text(UPDATE)
    assert text.index("**The architecture overview.**") < text.index("**Who writes code.**")
    assert "architecture overview" in _update_step("The PR")


# ---------- upgrade-setup ----------


def test_upgrade_setup_has_the_part_seventh_and_last():
    text = _text(UPGRADE)
    head = text.split("---", 2)[1]
    assert f'"{NAME}"' in head
    intro = text.split("\n## ", 1)[0]
    assert f'**"{NAME}"**' in intro and "The seventh part, last." in intro
    assert "shared by all seven" in intro
    assert text.index("\n# Choose who writes code\n") < text.index(f"\n# {NAME}\n")
    assert doctor.OFFERS[OFFER] == NAME


def test_upgrade_setup_names_the_offer_and_when_it_is_offered():
    offered = _section(_text(UPGRADE), "When it's offered")
    entry = _item(offered, f"- **`{OFFER}`**")
    assert "`kit.architecture.missing`" in entry and "`check-setup`" in entry
    assert "plugin" in entry
    assert "never in a ticket or conductor session" in entry.lower()
    assert f'Nor "{NAME}".' in _text(UPGRADE)


def test_the_part_does_what_set_up_does():
    part = _flat(_part())
    assert "The seventh path." in part
    assert OVERVIEW in part and 'adds `"docs/architecture/README.md"` to `project.rules`' in part
    # The template, wherever the kit is.
    assert "`.claude/workflow/templates/architecture-overview.md`" in part
    assert "`<this skill's directory>/../../templates/architecture-overview.md`" in part
    _moves_once(_part())


def test_the_part_stops_when_the_base_already_lists_it_or_a_pull_request_is_open():
    stands = _flat(_section(_part(), "1. Where it stands"))
    assert "git show origin/<base>:.claude/workflow/profile.toml" in stands
    assert "lists the overview already" in stands and "stop" in stands
    assert "an open pull request" in stands


def test_the_part_opens_one_pull_request_for_the_owner():
    pr = _section(_part(), "One pull request")
    assert re.search(r'^\d+\. Commit, then push the branch in a command of its own \("Pushing"\)', pr, re.M)
    assert "`WF profile check`" in pr
    assert "the owner's" in pr and "never merge it" in pr
    assert "Pushing" in _text(UPGRADE) and CHAINED in _text(UPGRADE)


# ---------- check-setup ----------


def test_check_setup_offers_it_from_doctors_note():
    offers = _section(_text(CHECK), "3. The offers")
    rows = [ln for ln in offers.splitlines() if ln.startswith(f"| `{OFFER}` |")]
    assert len(rows) == 1, rows
    row = rows[0]
    assert f"**{NAME}**" in row and "`kit.architecture.missing`" in row
    assert "`upgrade-setup`" in row and f"its offer `{OFFER}`" in row and "from its start" in row


def test_install_names_the_upgrade_for_plugin_projects():
    step = [ln for ln in _text(INSTALL).splitlines() if ln.startswith("3. When wanted, optional upgrades")]
    assert len(step) == 1
    assert f'"{NAME}"' in step[0] and "plugin" in step[0]
