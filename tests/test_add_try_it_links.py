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


def test_the_opening_choice_is_worded_by_experience_with_do_it_now_and_not_now():
    first = _sec("The opening choice")
    assert "*New to building*" in first and "*A developer*" in first
    assert "**Do it now** (recommended) and **Not now**" in first
    assert "same steps" in first
    # Handed over from check-setup, the person has just chosen, but still hears about Access.
    assert "skip this choice, but with sensitive data still say its Access sentence before screen 1" in first
    # With sensitive data, Access (and its possible payment method) is said up front.
    assert "Cloudflare Access, which may ask for a payment method" in first


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
        6: ["Wrangler lines", "no live site"],
        7: ["Cloudflare Access", "**Enable Access**"],
    }
    for n, words in names.items():
        for w in words:
            assert w in screens[n], (n, w)
    # The Wrangler lines screen 6 and the pull requests add, defined once.
    lines = _part()[_part().index("**The Wrangler lines**"):].split("\n\n", 1)[0]
    for w in ("`workers_dev = false`", "`preview_urls = true`", "`[previews]`", "missing a `previews` block",
              '`"workers_dev": false`', '`"preview_urls": true`', '`"previews": {}`'):
        assert w in lines, w


def test_the_part_runs_in_the_pages_order():
    part = _part()
    at = [part.index(h) for h in ("## What it needs", "## The opening choice", "## What's done already",
                                  "## Before step 2", "## The steps", "## The proof pull request",
                                  "## Its own try-it link", "## A fresh branch", "## Where try-it links end")]
    assert at == sorted(at)
    steps = _sec("The steps")
    assert steps.index("**Screen 5:") < steps.index("**Screen 7:")


def test_the_token_stays_in_cloudflare_and_no_detail_reaches_the_pull_request():
    assert "never ask for it" in _screens()[4]
    assert "No email address, token or other detail from Cloudflare's screens goes in it" in _sec("The proof pull request")


def test_each_screen_waits_for_done_and_a_step_already_done_shows_as_done():
    steps = _sec("The steps")
    assert '"Done"' in steps and '"Something\'s different"' in steps
    done = _sec("What's done already")
    assert "shown as done" in done and "**Continue**" in done
    # What can be read: Cloudflare's app on the repository, a built preview, the config.
    assert "`cloudflare-workers-and-pages`" in done
    assert "`built`" in done and "screens 1 to 5" in done
    assert "Wrangler config" in done and "screen 6" in done
    # A public link now doesn't skip "no live site": that still comes first.
    assert '"Before step 2" still comes first when the base branch\'s config needs it, then screen 5 again when Preview URLs were turned off for it, and screen 7' in done
    # The MCP tools read a pull request's check runs, never a commit's.
    assert "have no list of a commit's check runs" in done


def test_access_is_never_shown_as_done_and_a_public_link_is_said():
    done = _sec("What's done already")
    assert "Screen 7 is never shown as done" in done
    assert "An `access = true` already in the profile only changes its words" in done
    assert "that link is public right now" in done


def test_sensitive_data_is_read_from_the_profile_file_itself():
    need = _sec("What it needs")
    assert "from `.claude/workflow/profile.toml` itself (`WF profile check` doesn't print them)" in need
    assert "the template's secret-key patterns included" in need
    # A profile refused for Access goes to screen 7, then turns the links on as doctor's fix says.
    assert "previews.on is true but previews.access isn't" in need and profile.ACCESS_REFUSED.startswith("previews.on is true")
    assert "and `preview_urls = true` in the Wrangler config unless it says so already, as doctor's fix says" in need
    # Whether the section is there is read from the file: `profile check` prints the same without one.
    assert "whether the section is there at all, read from `profile.toml` itself" in need
    # `on = true` already: the Wrangler config is read itself, since doctor can't check a JSON one.
    assert "read the Wrangler config from the checkout (doctor's `previews.setup` line can't check a JSON one)" in need
    # Refused and no Access: the page's order, never `on = false` alone.
    assert "Preview URLs off in the dashboard first, then one pull request (from `workflow/no-previews`) setting `on = false`" in need
    assert "and setting `preview_urls = false` in the Wrangler config unless it says so already (a config with no `preview_urls` line doesn't say so: add the line" in need
    assert "`on = false` alone leaves the links public" in need
    assert "The owner merges it (a protected path), and the path ends with the \"No previews\" line" in need
    # On already, but links off: a stale `access = true` never turns them back on without screen 7.
    assert "With sensitive data and a `preview_urls` that isn't `true`" in need
    assert "ask screen 5 (Preview URLs on) and then screen 7 first, never turning them on from the profile's old `access = true`" in need
    assert "on **I can't turn it on** take the route below for a refused profile" in need
    # Asked before any Wrangler-lines pull request could turn the links on.
    assert need.index("and then screen 7 first") < need.index("When it lacks any of the Wrangler lines")
    # No Access: the record says so, and its own branch keeps a second run from opening another.
    assert "taking out any `access = true` (the owner has just said Access isn't on)" in need
    opened = need[need.index("**An open pull request of this path**"):].split("\n- ", 1)[0]
    assert "`workflow/no-previews`" in opened
    # An owner who has turned Access on since isn't stuck behind it.
    # It stays open until screen 7 confirms Access, after screen 5 turns Preview URLs back on.
    assert "for the third, screen 5 and then screen 7: only when screen 7's **Access is on** opens its `access = true` pull request, close the `workflow/no-previews` one" in opened
    assert "on **Not now** or **I can't turn it on**, leave it open" in opened
    # Beside a JSON config, Cloudflare reads the JSON one.
    assert "Cloudflare reads the JSON one" in need


# ---------- no live site, and the sensitive-data order ----------


def test_no_live_site_from_the_first_connect():
    need = _sec("Before step 2")
    assert "`workers_dev = false`" in need
    assert "`preview_urls = false`" in need and "sensitive" in need
    assert "before step 2" in need.lower() and "merge" in need
    # A config with routes or a custom domain already has a live site: said, never hidden.
    assert "`routes`" in need and "custom domain" in need
    # Read whether or not the repository is connected: a live site now is said plainly.
    assert "whether or not the repository is connected" in need
    assert "live on the internet now" in need and "public now" in need
    assert "placed and changed as the proof pull request's step 3 says" in need
    # The page's "do step 6 first, with those values": the Wrangler lines, `preview_urls = false` with sensitive data.
    assert 'the page\'s "do step 6 first, with those values", so the Wrangler lines, with `preview_urls = false` in place of `true`' in need
    # Connected and public: Preview URLs off first, since the small PR's branch builds a preview too.
    assert need.index("the person first turns **Preview URLs** off in the dashboard") < need.index("**The small pull request,**")
    assert "merging it deploys the base branch" in need
    assert "it keeps the app off the internet (and, with sensitive data, its preview links too)" in need
    assert "When they won't merge it now, stop there" in need
    # Preview URLs turned off for it: screen 5 is asked again, never left "done".
    assert "Screen 5 is then no longer done: it is asked again after the small pull request merges, just before screen 7" in need


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
    # Not now, with Preview URLs on and no Access: they go off again before the path stops.
    assert "**Not now** here, unlike other screens, first asks the person to turn **Preview URLs** off in the dashboard" in seven
    assert "whenever they may be on, whether screen 5 turned them on or they were on already" in seven
    assert "Preview URLs stay off until Access is on." in _sec("Where try-it links end")
    # As the page says: the small pull request sets it back when the config says otherwise.
    assert 'open the small pull request of "Before step 2" for it' in seven


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
    assert "never a second `[previews]` table" in pr


def test_a_section_there_already_is_changed_in_place_and_reads():
    # "Turn them on": the profile has `[previews]` with `on = false`.
    template, placed = _with_previews("[previews]\non = false\n")
    assert profile.parse(tomllib.loads(placed), KIT).previews.on is False
    turned = placed.replace("[previews]\non = false\n", _snippet())
    assert profile.parse(tomllib.loads(turned), KIT).previews.on is True
    # A second table, the mistake the skill rules out, doesn't read.
    with pytest.raises(tomllib.TOMLDecodeError):
        tomllib.loads(placed + "\n" + _snippet())


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
    assert "whichever of the Wrangler lines is missing" in pr
    assert "`workers_dev = true` becomes `false`, `preview_urls = false` becomes `true`" in pr
    assert "above its first line that starts with `[`" in pr and "at its end" in pr
    assert "Only the top-level settings count: a `workers_dev` under an `[env.…]` table is another environment's" in pr
    # A JSON config: doctor's line says it can't check it.
    assert "JSON config" in pr and "`cant_check`" in pr


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
    # The log is behind a Cloudflare sign-in: the person reads it out.
    assert "ask the person to open it" in states["failed"] and "paste its error line" in states["failed"]
    assert "screen 5" in states["none"] and "skipped" in states["none"]
    assert "push a new commit to the proof pull request's branch" in states["none"]


def test_an_old_build_command_gets_a_fresh_branch_not_a_retry():
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
    assert "built nothing to try" in end
    assert "no previews" in end.lower()
    assert "or the refused profile's `on = false` one" in end


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
