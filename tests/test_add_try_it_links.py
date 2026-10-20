"""#116: "Add try-it links", the fourth path of the `upgrade-setup` skill (#41,
user stories 8 to 14 and 24). The skill's wording, read from its file as the
kit-release tests read skills and as #47's and #68's tests read
`upgrade-setup`; the profile it writes, parsed as the kit parses it; and the
skills and docs that hand the offer over to it."""

import re
import tomllib

import pytest

from changelog_notes import since_0110
from conftest import KIT
from workflow import doctor, profile, vendor

SKILL = KIT / "skills/upgrade-setup/SKILL.md"
CHECK = KIT / "skills/check-setup/SKILL.md"
PAGE = KIT / "docs/previews.md"
NAME = "Add try-it links"


def _text(path=SKILL):
    return path.read_text(encoding="utf-8")


def _part():
    """The skill's `# Add try-it links` part, to the end of the file."""
    m = re.search(r"^# Add try-it links\n(.*)", _text(), re.M | re.S)
    assert m, "no part # Add try-it links"
    return m.group(1)


def _sec(title):
    """The `## ...` section of the part whose heading contains `title`."""
    m = re.search(rf"^## [^\n]*{re.escape(title)}[^\n]*\n(.*?)(?=^## |\Z)", _part(), re.M | re.S)
    assert m, f"no section {title!r}"
    return m.group(1)


def _offered():
    m = re.search(r"^## When it's offered\n(.*?)(?=^#{1,2} )", _text(), re.M | re.S)
    return m.group(1)


def _screens():
    """The numbered screens of "The steps": {number: text}."""
    steps = _sec("The steps")
    found = re.findall(r"^(\*\*Screen (\d).*?)(?=^\*\*Screen \d|\Z)", steps, re.M | re.S)
    return {int(n): body for body, n in found}


# ---------- the path, its offer, and where it's offered ----------


def test_the_fourth_path_is_named_with_its_offer():
    text = _text()
    head = text.split("---", 2)[1]
    assert f'"{NAME}"' in head
    assert f'**"{NAME}"**' in text.split("\n## ", 1)[0]  # the opening list of upgrades
    # The fourth part, after the other three.
    assert text.index("# Require these checks") < text.index(f"\n# {NAME}\n")
    assert f"The fourth path (offer `add_try_it_links`)." in _part()
    assert doctor.OFFERS["add_try_it_links"] == NAME
    assert "shared by all four" in text


def test_it_is_offered_only_from_the_quickstart_doctor_and_when_asked():
    offers = _offered()
    assert "**`add_try_it_links`**" in offers
    entry = offers[offers.index("**`add_try_it_links`**"):].split("\n- **`", 1)[0]
    assert "only from the quickstart's next steps" in entry
    assert "`workflow doctor`'s `add_try_it_links` offer" in entry and "`check-setup`" in entry
    assert "when the person asks" in entry
    assert "Never at session start" in entry and "never as a nag" in entry
    # Doctor offers it only for a Wrangler config with no [previews] section.
    assert "no `[previews]` section" in entry


def test_a_ticket_or_conductor_session_never_runs_it():
    part = _part()
    assert "When `WORKFLOW_ROLE` is `ticket`, don't run it or offer it" in _text()
    assert "The conductor never runs it" in part


def test_it_never_changes_cloudflare_itself_the_person_clicks():
    part = _part()
    assert "never signs in to Cloudflare" in part
    assert "the person clicks" in part
    assert "can't be read from here" in part


# ---------- before the steps ----------


def test_it_needs_a_wrangler_config_and_stops_without_one():
    need = _sec("What it needs")
    for name in ("`wrangler.toml`", "`wrangler.json`", "`wrangler.jsonc`"):
        assert name in need, name
    assert "Cloudflare Workers" in need and "stop" in need


def test_it_reads_the_profile_and_points_at_an_open_pull_request():
    need = _sec("What it needs")
    assert "`[sensitive]`" in need and "`patterns`" in need
    assert "`on = true` already" in need
    assert "`workflow/try-it-links`" in need and "point at it rather than opening another" in need
    assert "`experience.wording_level`" in need


# ---------- one screen at a time, by experience ----------


def test_the_first_screen_is_worded_by_experience_with_do_it_now_and_not_now():
    first = _sec("The first screen")
    assert "*New to building*" in first and "*A developer*" in first
    assert "**Do it now** (recommended) and **Not now**" in first
    assert "same steps" in first
    assert "`AskUserQuestion`" in first
    # Handed over from check-setup, the person has just chosen.
    assert "skip this screen" in first


def test_the_steps_are_the_pages_seven_one_screen_at_a_time():
    steps = _sec("The steps")
    assert "one screen at a time" in steps.lower() and "`AskUserQuestion`" in steps
    assert "`#the-steps`" in steps
    screens = _screens()
    assert sorted(screens) == list(range(1, 8)), sorted(screens)
    # Each screen names its part of the page, in the page's order.
    names = {
        1: ["Cloudflare account", "dash.cloudflare.com/sign-up"],
        2: ["**Only select repositories**", "this repository alone"],
        3: ["**Build command**", "**Production**", "**Previews Base**", "empty"],
        4: ["**Create new token**", "Configured API token unavailable"],
        5: ["**Preview URLs**", "off by default"],
        6: ["`[previews]`", "`workers_dev = false`", "`preview_urls = true`", "no live site"],
        7: ["Cloudflare Access", "**Enable Access**"],
    }
    for n, words in names.items():
        for w in words:
            assert w in screens[n], (n, w)


def test_each_screen_waits_for_done_and_a_step_already_done_shows_as_done():
    steps = _sec("The steps")
    assert '"Done"' in steps and '"Something\'s different"' in steps
    done = _sec("What's done already")
    assert "shown as done" in done and "**Continue**" in done
    # What can be read: Cloudflare's app on the repository, a built preview, the config.
    assert "`cloudflare-workers-and-pages`" in done
    assert "`built`" in done and "steps 1 to 5" in done
    assert "Wrangler config" in done and "step 6" in done


# ---------- no live site, and the sensitive-data order ----------


def test_no_live_site_from_the_first_connect():
    need = _sec("Before step 2")
    assert "`workers_dev = false`" in need
    assert "`preview_urls = false`" in need and "sensitive" in need
    assert "before step 2" in need.lower() and "merge" in need
    # A config with routes or a custom domain already has a live site: said, never hidden.
    assert "`routes`" in need and "custom domain" in need


def test_a_sensitive_project_gets_access_straight_after_step_5_before_any_pull_request():
    steps = _sec("The steps")
    assert "straight after screen 5, before any pull request is pushed" in steps
    assert "without sensitive data, screen 7 is left out" in steps.lower()


def test_access_is_the_owners_word_and_the_kit_says_it_cant_check_it():
    seven = _screens()[7]
    assert "The kit can't check Access itself" in seven
    assert "relies on your word" in seven
    assert "`access = true`" in seven
    assert "**Access is on**" in seven and "**I can't turn it on**" in seven
    # Without Access: it stops, with no previews, and the steps that keep the links off.
    assert "no previews" in seven and "stops" in seven
    assert "**Preview URLs** off" in seven and "`preview_urls = false`" in seven


# ---------- the proof pull request ----------


def _snippet():
    pr = _sec("The proof pull request")
    blocks = re.findall(r"```toml\n(.*?)```", pr, re.S)
    assert len(blocks) == 1, blocks
    return blocks[0]


def test_the_proof_pull_request_sets_previews_on_with_cloudflare():
    got = tomllib.loads(_snippet())["previews"]
    assert got == {"provider": "cloudflare", "on": True, "access": True}
    pr = _sec("The proof pull request")
    assert "`access = true` line only when screen 7 was confirmed" in pr
    assert "`WF profile check` passes" in pr
    assert "fresh from the base branch" in pr and "`workflow/try-it-links`" in pr


def _with_previews(snippet):
    template = (KIT / "templates/profile.toml").read_text(encoding="utf-8")
    commented = re.search(r"^# \[previews\]\n(?:# .*\n)+", template, re.M)
    assert commented, "the template's commented [previews] lines"
    return template, template[:commented.start()] + snippet + template[commented.end():]


def test_the_section_it_writes_turns_the_templates_previews_on():
    pr = _sec("The proof pull request")
    assert "in place of the template's commented `# [previews]` lines" in pr
    assert "at the end of the file" in pr
    template, placed = _with_previews(_snippet())
    for text in (placed, template + "\n" + _snippet()):
        got = profile.parse(tomllib.loads(text), KIT).previews
        assert got.on is True and got.access is True and got.provider == "cloudflare" and got.section is True


def test_without_access_a_sensitive_profile_is_refused_so_the_kit_writes_no_on():
    # The template has [sensitive] patterns: `on = true` with no `access = true`
    # is what `profile check` refuses, as the skill says.
    _, placed = _with_previews(_snippet().replace("access = true\n", ""))
    with pytest.raises(profile.ProfileError, match=re.escape(profile.ACCESS_REFUSED)):
        profile.parse(tomllib.loads(placed), KIT)
    assert "refuses" in _sec("The proof pull request")


def test_the_proof_pull_request_carries_the_wrangler_changes_step_6_needs():
    pr = _sec("The proof pull request")
    assert "whichever of" in pr and "is missing" in pr
    assert "`workers_dev = false`" in pr and "`preview_urls = true`" in pr and "`[previews]`" in pr
    assert "above its first line that starts with `[`" in pr and "at its end" in pr
    # A JSON config gets the JSON spellings, and doctor's line says it can't check it.
    assert '`"previews": {}`' in pr and "`cant_check`" in pr


def test_merging_the_proof_pull_request_is_the_owners():
    pr = _sec("The proof pull request")
    assert "protected path" in pr
    assert "merging it is the owner's" in pr
    assert "Never merge it, or enable auto-merge on it, yourself" in pr


# ---------- its own try-it link ----------


def test_it_reads_its_own_preview_with_workflow_preview_and_reports_the_link_once_built():
    link = _sec("Its own try-it link")
    assert "`WF preview --fetch <n> --json`" in link
    assert "`WF preview --comments F --checks F --sha <head> --json`" in link
    assert "about four minutes" in link
    states = {s: link[link.index(f"- **`{s}`**"):].split("\n- **", 1)[0] for s in ("built", "building", "failed", "none")}
    assert "`url`" in states["built"] and "report" in states["built"]
    assert "read it again" in states["building"]
    assert "**When a build fails**" in states["failed"] and "`#when-a-build-fails`" in states["failed"]
    assert "step 5" in states["none"]


def test_trap_3_pushes_a_fresh_branch_rather_than_retry():
    trap = _sec("A fresh branch")
    assert "Previews Base" in trap
    assert "copied when a branch is first built" in trap
    assert "rather than retry" in trap
    assert "new branch" in trap and "new pull request" in trap
    # The failure the page names for it.
    assert "must match the name of your Worker" in trap


def test_it_ends_with_one_line_for_each_outcome():
    end = _sec("Where try-it links end")
    assert "Not now" in end and "Nothing was changed." in end
    assert "Merge #<n> when you're ready" in end
    assert "no previews" in end.lower()


# ---------- check-setup hands the offer over ----------


def _check_offers():
    text = _text(CHECK)
    return text[text.index("## 3. The offers"):]


def test_check_setup_hands_add_try_it_links_to_the_upgrade_with_not_now():
    offers = _check_offers()
    [row] = [ln for ln in offers.splitlines() if ln.startswith("| `add_try_it_links`")]
    assert f"**{NAME}**" in row
    assert "`upgrade-setup`" in row and f'"{NAME}"' in row and "`add_try_it_links`" in row
    assert "**Not now**" in offers
    # No longer named as text until the upgrade exists.
    assert "until `upgrade-setup` has that upgrade" not in offers


# ---------- the docs ----------


def test_doctors_offer_note_says_to_ask_claude_for_the_upgrade():
    src = _text(KIT / "scripts/workflow/doctor.py")
    note = src[src.index("def check_previews"):src.index('offer="add_try_it_links"')]
    assert "ADD_TRY_IT_LINKS" in note
    assert doctor.ADD_TRY_IT_LINKS == NAME


def test_enforcement_section_5_says_check_setup_offers_it():
    doc = _text(KIT / "docs/enforcement.md")
    five = re.search(r"^## 5\.[^\n]*\n(.*?)(?=^## |\Z)", doc, re.M | re.S).group(1)
    assert "Until `upgrade-setup` has that upgrade" not in five
    assert f"`check-setup` offers it, and `upgrade-setup`'s \"{NAME}\" makes it" in five


def test_readme_step_6_and_install_name_the_upgrade():
    readme = _text(KIT / "README.md")
    six = re.search(r"^### Step 6\. Check it\n(.*?)(?=^### )", readme, re.M | re.S).group(1)
    assert f'"{NAME}"' in six
    install = _text(KIT / "docs/install.md")
    assert f'"{NAME}"' in install


def test_the_quickstart_and_the_page_say_to_ask_claude():
    quick = _text(KIT / "docs/quickstart.md")
    [bullet] = [l for l in quick.splitlines() if l.strip().startswith(f"- **{NAME}**")]
    assert "Ask Claude to add try-it links" in bullet
    intro = _text(PAGE).split("\n## ", 1)[0]
    assert "Ask Claude to add try-it links" in intro
    assert "to come" not in _text(PAGE)


def test_it_ships_beside_the_page_it_follows():
    files = vendor.plan(KIT, None)
    assert files[".claude/skills/upgrade-setup/SKILL.md"] == SKILL
    assert files[".claude/workflow/docs/previews.md"] == PAGE
    part = _part()
    assert "`.claude/workflow/docs/previews.md`" in part and "the kit's `docs/previews.md`" in part


def test_changelog_notes_116_under_unreleased():
    notes = since_0110()
    entry = notes[re.search(r"^\*\*.*\(#116[,)]", notes, re.M).start():]
    entry = entry[:entry.index("\n**", 1)]
    assert f'"{NAME}"' in entry and "`add_try_it_links`" in entry and "`check-setup`" in entry
