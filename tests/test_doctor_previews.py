"""#115: `workflow doctor`'s Previews group (#41's doctor lines) and the
`add_try_it_links` offer. Seam 1 of #34, as #58's tests use it: the CLI, with
a temporary checkout, its profile and its Wrangler config, and the fake
`python3`, `claude` and `gh` of test_doctor.py."""

import json
import re
import shutil

from changelog_notes import since_0110
from conftest import KIT
from test_doctor import HEALTHY, _doctor, _each_at_once, _entries, _lines, _project, _report, _unchanged_after_doctor
from test_doctor_old_python import _old_report
from workflow import doctor, profile, vendor

NEW = {"WORKFLOW_EXPERIENCE": "new"}
DEV = {"WORKFLOW_EXPERIENCE": "developer"}
PAGE = KIT / "docs/previews.md"
SENSITIVE = '[sensitive]\ndescription = "phone numbers"\npatterns = ["\\\\b\\\\d{3}-\\\\d{3}-\\\\d{4}\\\\b"]\n'
ON = HEALTHY + "[previews]\non = true\n"
OFF = HEALTHY + "[previews]\non = false\n"
# A notes app's Wrangler config, with the block and without it.
WITH_BLOCK = 'name = "notes"\nmain = "src/index.ts"\nworkers_dev = false\npreview_urls = true\n\n[previews]\n'
NO_BLOCK = 'name = "notes"\nmain = "src/index.ts"\nworkers_dev = false\n'
JSONC = '// the notes app\n{\n  "name": "notes",\n  "workers_dev": false,\n  "previews": {}\n}\n'


def _with(tmp_path, name, profile=HEALTHY, files=None, vendored=True, page=True):
    """A checkout under tmp_path/name with `profile` and `files` (name:
    text) at its root. With `page`, a vendored one has the page where `vendor
    install` puts it."""
    root = _project(tmp_path / name, profile=profile, vendored=vendored)
    for rel, text in (files or {}).items():
        (root / rel).write_text(text)
    if vendored and page:
        (root / ".claude/workflow/docs").mkdir(parents=True)
        shutil.copy(PAGE, root / ".claude/workflow/docs/previews.md")
    return root


def _previews(report):
    return {ln["id"]: ln for ln in report["lines"] if ln["group"] == "Previews"}


def _reports(tmp_path, calls):
    """`--json` reports for each (root, args, env) at once."""
    return _each_at_once(tmp_path, _report, [(root, args, {"env": env}) for root, args, env in calls])


def _both(tmp_path, root, *args):
    """The report in both wordings."""
    return _reports(tmp_path, [(root, args, NEW), (root, args, DEV)])


# ---------- with `[previews] on = true`: the `[previews]` block ----------


def test_on_with_no_previews_block_in_wrangler_toml_is_a_gap_and_with_it_fine(tmp_path):
    without = _with(tmp_path, "without", ON, {"wrangler.toml": NO_BLOCK})
    with_ = _with(tmp_path, "with", ON, {"wrangler.toml": WITH_BLOCK})
    new, dev, ok_new, ok_dev = _reports(tmp_path, [(without, (), NEW), (without, (), DEV), (with_, (), NEW), (with_, (), DEV)])
    for r in (new, dev):
        line = _previews(r)["previews.setup"]
        assert line["status"] == "gap", line
        assert "`[previews]`" in line["message"] and "wrangler.toml" in line["message"]
        # The fix names the page and the failure Cloudflare shows without the block.
        assert "`.claude/workflow/docs/previews.md`" in line["fix"] and "step 6" in line["fix"]
        assert "missing a `previews` block" in line["fix"]
        assert line["offer"] is None
        assert r["strict_ok"] is False
    for key in ("message", "fix"):  # worded by experience
        assert _previews(new)["previews.setup"][key] != _previews(dev)["previews.setup"][key]
    for r in (ok_new, ok_dev):
        line = _previews(r)["previews.setup"]
        assert line["status"] == "fine", line
        assert line["fix"] == "" and line["offer"] is None
        assert r["strict_ok"] is True, r["lines"]


def test_on_with_no_previews_block_is_a_gap_in_the_text_report_too(tmp_path):
    without = _with(tmp_path, "without", ON, {"wrangler.toml": NO_BLOCK})
    with_ = _with(tmp_path, "with", ON, {"wrangler.toml": WITH_BLOCK})
    gap, fine = _each_at_once(tmp_path, _doctor, [(without, (), {"env": NEW}), (with_, ("--strict",), {"env": NEW})])
    assert gap.returncode == 0, gap.stderr
    out = gap.stdout.splitlines()
    assert "Previews" in out
    assert any(e.startswith("[gap]") and "`[previews]`" in e and "Fix:" in e and "docs/previews.md" in e for e in _entries(gap.stdout)), gap.stdout
    assert fine.returncode == 0, fine.stdout
    assert any(e.startswith("[fine]") and "`[previews]`" in e for e in _entries(fine.stdout)), fine.stdout


def test_on_with_no_wrangler_config_at_all_is_a_gap(tmp_path):
    root = _with(tmp_path, "none", ON)
    for r in _both(tmp_path, root):
        line = _previews(r)["previews.setup"]
        assert line["status"] == "gap", line
        assert "wrangler.toml" in line["message"] and "root" in line["message"]
        assert "wrangler.json or wrangler.jsonc" in line["message"] or "(`wrangler.toml`)" in line["message"]
        assert "docs/previews.md" in line["fix"] and "missing a `previews` block" in line["fix"]


def test_a_previews_key_that_isnt_a_block_is_a_gap(tmp_path):
    root = _with(tmp_path, "key", ON, {"wrangler.toml": 'name = "notes"\npreviews = true\n'})
    line = _previews(_report(tmp_path, root))["previews.setup"]
    assert line["status"] == "gap", line


def test_a_wrangler_toml_that_isnt_toml_or_isnt_a_file_cant_be_checked(tmp_path):
    bad = _with(tmp_path, "bad", ON, {"wrangler.toml": 'name = "notes\n[previews\n'})
    folder = _with(tmp_path, "folder", ON)
    (folder / "wrangler.toml").mkdir()
    dangling = _with(tmp_path, "dangling", ON)
    (dangling / "wrangler.toml").symlink_to(dangling / "nowhere.toml")
    calls = [(root, (), env) for root in (bad, folder, dangling) for env in (NEW, DEV)]
    for (root, _, env), r in zip(calls, _reports(tmp_path, calls)):
        line = _previews(r)["previews.setup"]
        assert line["status"] == "cant_check", (root, line)
        assert "wrangler.toml" in line["message"] and line["fix"]
        # Only a file that isn't TOML is told to read as TOML.
        assert ("TOML" in line["fix"]) == (root == bad), (root, line)
        if env == NEW:
            assert "line " not in line["message"]  # the parser's detail is the developer's


# ---------- `wrangler.json` and `wrangler.jsonc` ----------


def test_wrangler_json_or_jsonc_cant_be_checked_with_a_fix_naming_the_key(tmp_path):
    json_root = _with(tmp_path, "json", ON, {"wrangler.json": json.dumps({"name": "notes", "previews": {}})})
    jsonc_root = _with(tmp_path, "jsonc", ON, {"wrangler.jsonc": JSONC})
    # Beside a wrangler.toml, Wrangler reads the JSON one first, so the TOML one can't settle it.
    both = _with(tmp_path, "both", ON, {"wrangler.toml": WITH_BLOCK, "wrangler.json": "{}"})
    calls = [(root, (), env) for root in (json_root, jsonc_root, both) for env in (NEW, DEV)]
    reports = _reports(tmp_path, calls)
    for (root, _, env), r in zip(calls, reports):
        line = _previews(r)["previews.setup"]
        assert line["status"] == "cant_check", (root, line)
        name = "wrangler.jsonc" if root == jsonc_root else "wrangler.json"
        assert name in line["message"], line
        assert '"previews"' in line["fix"] and "docs/previews.md" in line["fix"], line


# ---------- `[sensitive]` patterns: `access` ----------


def test_sensitive_patterns_with_on_and_access_not_true_is_a_gap(tmp_path):
    no_access = _with(tmp_path, "no-access", HEALTHY + SENSITIVE + "[previews]\non = true\n", {"wrangler.toml": WITH_BLOCK})
    access_false = _with(tmp_path, "access-false", HEALTHY + SENSITIVE + "[previews]\non = true\naccess = false\n", {"wrangler.toml": WITH_BLOCK})
    calls = [(root, (), env) for root in (no_access, access_false) for env in (NEW, DEV)]
    for r in _reports(tmp_path, calls):
        line = _previews(r)["previews.access"]
        assert line["status"] == "gap", line
        assert "Access" in line["message"] and "`access = true`" in line["message"] + line["fix"]
        assert "docs/previews.md" in line["fix"] and "step 7" in line["fix"]
        # Without Access, the profile alone changes nothing on Cloudflare: the links go off there too.
        assert "`preview_urls = false`" in line["fix"] and "Preview URLs off" in line["fix"]
        # With Access, the links go on in the Wrangler config too (step 7).
        assert "`preview_urls = true`" in line["fix"]
        # `profile check` refuses that profile too, and says so on its own line.
        assert _lines(r)["kit.profile"]["status"] == "gap"


def test_a_profile_refused_for_access_with_no_wrangler_config_still_says_so(tmp_path):
    root = _with(tmp_path, "no-config", HEALTHY + SENSITIVE + "[previews]\non = true\n")
    p = _previews(_report(tmp_path, root))
    assert p["previews.access"]["status"] == "gap", p
    assert "previews.setup" not in p  # nothing to wait on the profile for: no Wrangler config


def test_a_profile_refused_for_another_reason_first_shows_no_access_gap(tmp_path):
    # `profile check` names the first mistake it finds; the Access line repeats only that refusal.
    root = _with(tmp_path, "other", HEALTHY + '[ui]\nexplorer = "nope"\n' + SENSITIVE + "[previews]\non = true\n", {"wrangler.toml": WITH_BLOCK})
    r = _report(tmp_path, root)
    assert "ui.explorer" in _lines(r)["kit.profile"]["message"]
    assert "previews.access" not in _previews(r)
    assert _previews(r)["previews.setup"]["status"] == "cant_check"


def test_sensitive_patterns_with_on_and_access_true_relies_on_the_owners_word(tmp_path):
    root = _with(tmp_path, "access", HEALTHY + SENSITIVE + "[previews]\non = true\naccess = true\n", {"wrangler.toml": WITH_BLOCK})
    for r in _both(tmp_path, root):
        p = _previews(r)
        assert p["previews.setup"]["status"] == "fine", p
        assert p["previews.access"]["status"] == "fine", p
        assert "can't check" in p["previews.access"]["message"]
        assert r["strict_ok"] is True, r["lines"]


def test_sensitive_patterns_without_previews_on_say_nothing_about_access(tmp_path):
    off = _with(tmp_path, "off", HEALTHY + SENSITIVE + "[previews]\non = false\n", {"wrangler.toml": NO_BLOCK})
    none = _with(tmp_path, "none", HEALTHY + SENSITIVE, {"wrangler.toml": NO_BLOCK})
    for r in _reports(tmp_path, [(off, (), NEW), (none, (), NEW)]):
        assert "previews.access" not in _previews(r), r["lines"]


# ---------- a Wrangler config, no `[previews]` section: the offer ----------


def test_a_wrangler_config_with_no_previews_section_is_a_note_offering_add_try_it_links(tmp_path):
    toml_root = _with(tmp_path, "toml", HEALTHY, {"wrangler.toml": NO_BLOCK})
    jsonc_root = _with(tmp_path, "jsonc", HEALTHY, {"wrangler.jsonc": JSONC})
    calls = [(root, ("--strict",), env) for root in (toml_root, jsonc_root) for env in (NEW, DEV)]
    results = _each_at_once(tmp_path, _doctor, [(root, ("--json", *args), {"env": env}) for root, args, env in calls])
    for p in results:
        assert p.returncode == 0, p.stdout  # --strict passes: a note never fails it
        r = json.loads(p.stdout)
        line = _previews(r)["previews.setup"]
        assert line["status"] == "note", line
        assert line["offer"] == "add_try_it_links"
        assert "docs/previews.md" in line["fix"]
        assert '"Add try-it links"' in line["fix"]  # the upgrade that takes them through it (#116)
        assert r["strict_ok"] is True


def test_the_offer_shows_in_the_text_report(tmp_path):
    root = _with(tmp_path, "toml", HEALTHY, {"wrangler.toml": NO_BLOCK})
    p = _doctor(tmp_path, root, "--strict", env=NEW)
    assert p.returncode == 0, p.stdout
    assert any(e.startswith("[note]") and "Next:" in e and "Claude can offer: Add try-it links" in e for e in _entries(p.stdout)), p.stdout


def test_previews_turned_off_in_the_profile_is_a_note_with_no_offer(tmp_path):
    # Turned off on purpose (a sensitive project without Access, say): never a nag.
    off = _with(tmp_path, "off", OFF, {"wrangler.toml": NO_BLOCK})
    empty = _with(tmp_path, "empty", HEALTHY + "[previews]\n")
    calls = [(root, ("--strict",), env) for root in (off, empty) for env in (NEW, DEV)]
    for (root, _, _), r in zip(calls, _reports(tmp_path, calls)):
        line = _previews(r)["previews.setup"]
        assert line["status"] == "note", line
        assert "`on = true`" in line["message"] and "`on = false`" not in line["message"]
        assert line["offer"] is None
        assert "docs/previews.md" in line["fix"]
        # The upgrade (#116) is named only where it can run: beside a Wrangler config.
        assert ('"Add try-it links"' in line["fix"]) == (root == off), (root, line["fix"])
        assert r["strict_ok"] is True


def test_the_profile_tells_previews_never_set_up_from_turned_off(tmp_path):
    def previews(text):
        (tmp_path / ".claude/workflow").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".claude/workflow/profile.toml").write_text(text)
        return profile.load(tmp_path).previews

    assert previews(HEALTHY).section is False
    assert previews(HEALTHY + "[previews]\n").section is True
    assert previews(OFF).section is True and previews(OFF).on is False


def test_the_offer_is_the_add_try_it_links_upgrade():
    assert doctor.OFFERS["add_try_it_links"] == "Add try-it links"


# ---------- nothing to say ----------


def test_no_wrangler_config_and_no_section_shows_no_previews_line(tmp_path):
    root = _with(tmp_path, "plain", HEALTHY)
    j, p = _each_at_once(tmp_path, _doctor, [(root, ("--json",), {"env": NEW}), (root, (), {"env": NEW})])
    assert _previews(json.loads(j.stdout)) == {}
    assert "Previews" not in p.stdout.splitlines()


def test_a_wrangler_config_in_a_project_not_set_up_waits_on_the_set_up(tmp_path):
    root = _with(tmp_path, "unset", None, {"wrangler.toml": NO_BLOCK})
    line = _previews(_report(tmp_path, root))["previews.setup"]
    assert line["status"] == "cant_check" and line["offer"] is None, line


# ---------- the page the fixes link ----------


def test_the_fixes_link_the_page_and_the_link_resolves(tmp_path):
    vendored = _with(tmp_path, "vendored", ON, {"wrangler.toml": NO_BLOCK})
    plugin = _with(tmp_path, "plugin", ON, {"wrangler.toml": NO_BLOCK}, vendored=False)
    v_new, v_dev, p_new, p_dev = _reports(tmp_path, [(vendored, (), NEW), (vendored, (), DEV), (plugin, (), NEW), (plugin, (), DEV)])
    # Vendored: the page's path from the project's root, where `vendor install` puts it.
    files = vendor.plan(KIT, None)
    for r in (v_new, v_dev):
        fix = _previews(r)["previews.setup"]["fix"]
        rel = re.search(r"`([^`]*previews\.md)`", fix).group(1)
        assert rel == ".claude/workflow/docs/previews.md"
        assert files[rel] == PAGE and (vendored / rel).is_file()
    # The plugin: the kit's own page, by its full path.
    for r in (p_new, p_dev):
        fix = _previews(r)["previews.setup"]["fix"]
        assert f"the kit's `docs/previews.md` (`{PAGE}`)" in fix
        assert PAGE.is_file()
    # The step and the section the fixes send the reader to are on the page.
    text = PAGE.read_text(encoding="utf-8")
    assert "\n6. **The Wrangler config: a `[previews]` block" in text and "\n7. **For a project with sensitive data**" in text
    assert "\n## When a build fails\n" in text and "missing a `previews` block" in text


# ---------- doctor changes nothing ----------


def test_nothing_in_the_checkout_changes(tmp_path):
    roots = [_with(tmp_path, "a", ON, {"wrangler.toml": NO_BLOCK}), _with(tmp_path, "b", HEALTHY, {"wrangler.jsonc": JSONC}),
             _with(tmp_path, "c", HEALTHY + SENSITIVE + "[previews]\non = true\n", {"wrangler.toml": WITH_BLOCK})]
    _unchanged_after_doctor(tmp_path, [(root, ("--json",), {}) for root in roots])


# ---------- old Python's short report ----------


def test_old_pythons_short_report_names_the_previews_line_only_with_a_wrangler_config_or_a_section(tmp_path):
    with_config = _with(tmp_path, "with", HEALTHY, {"wrangler.toml": NO_BLOCK}, page=False)
    jsonc = _with(tmp_path, "jsonc", HEALTHY, {"wrangler.jsonc": JSONC}, page=False)
    section = _with(tmp_path, "section", ON, page=False)
    inline = _with(tmp_path, "inline", "previews = { on = false }\n" + HEALTHY, page=False)  # above the first table
    dangling = _with(tmp_path, "dangling", HEALTHY, page=False)
    (dangling / "wrangler.toml").symlink_to(dangling / "nowhere.toml")
    quoted = _with(tmp_path, "quoted", HEALTHY + "['previews']\non = false\n", page=False)
    plain = _with(tmp_path, "plain", HEALTHY, page=False)
    # An area named `previews` is a key of [areas], not a section (as in the kit's own profile).
    area = _with(tmp_path, "area", HEALTHY + "[areas]\npreviews = []\n", page=False)
    for root in (with_config, jsonc, section, inline, dangling, quoted):
        line = {ln["id"]: ln for ln in _old_report(root)["lines"]}["previews.setup"]
        assert line["group"] == "Previews" and line["status"] == "cant_check", line
    for root in (plain, area):
        assert "previews.setup" not in {ln["id"] for ln in _old_report(root)["lines"]}, root


# ---------- docs ----------


def _section(text, title):
    start = text.index(f"\n## {title}")
    end = text.find("\n## ", start + 1)
    return text[start:end if end != -1 else None]


def test_enforcement_section_5_names_the_previews_group_and_the_offer():
    sec = _section((KIT / "docs/enforcement.md").read_text(encoding="utf-8"), "5. Checking the set-up")
    assert "Previews" in sec and "\"Add try-it links\"" in sec and "`add_try_it_links`" in sec
    assert "`wrangler.toml`" in sec and "`[previews]`" in sec


def test_check_setup_hands_the_offer_to_the_upgrade_now_that_it_has_it():
    # #116 gave `upgrade-setup` the upgrade, so the offer is a row, no longer text.
    text = (KIT / "skills/check-setup/SKILL.md").read_text(encoding="utf-8")
    offers = text[text.index("## 3. The offers"):]
    assert "| `add_try_it_links` |" in offers and "#116" not in offers
    assert "add_try_it_links" in doctor.OFFERS


def test_changelog_notes_115_under_unreleased():
    notes = since_0110()
    entry = notes[re.search(r"^\*\*.*\(#115[,)]", notes, re.M).start():]
    entry = entry[:entry.index("\n**", 1)]
    assert "Previews" in entry and "`add_try_it_links`" in entry and "`docs/enforcement.md`" in entry
