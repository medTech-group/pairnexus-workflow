"""Vendoring: resolving by taking the kit's version, keeping a local edit, verify,
Matt Pocock's skills, other flow hooks, .gitignore and stale files on --adopt."""

import json
import subprocess
import sys
from pathlib import Path

from test_vendor_evidence import kit, mattpocock, proj  # noqa: F401  (fixtures)

from workflow import vendor

CLI = Path(__file__).resolve().parents[1] / "scripts/workflow.py"
FLOW = ".claude/workflow/flow.md"


def _cli(*args):
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True)


# ---------- 5. a conflict resolved by taking the kit's version ----------


def test_taking_the_kits_version_updates_cleanly_next_time(mattpocock, kit, proj):
    vendor.install(kit, proj, mattpocock)
    flow, new = proj / FLOW, proj / (FLOW + ".new")
    flow.write_text("local edit")
    (kit / "docs/flow.md").write_text("kit v2")
    assert vendor.install(kit, proj, mattpocock, update=True)["conflicts"] == [FLOW]
    flow.write_text(new.read_text())  # take the kit's version as it is
    vendor.resolve(proj, FLOW)
    (kit / "docs/flow.md").write_text("kit v3")
    r = vendor.install(kit, proj, mattpocock, update=True)
    assert not r["conflicts"] and FLOW in r["written"] and flow.read_text() == "kit v3" and not new.exists()
    v = vendor.verify(proj)
    assert not v["changed"] and not v["conflicts"]


def test_a_dropped_file_resolved_to_the_kits_version_is_removed(mattpocock, kit, proj):
    vendor.install(kit, proj, mattpocock)
    doc = ".claude/workflow/docs/charter.md"
    (proj / doc).write_text("local")
    (kit / "docs/charter.md").write_text("kit v2")
    vendor.install(kit, proj, mattpocock, update=True)
    (proj / doc).write_text("kit v2")
    vendor.resolve(proj, doc)
    (kit / "docs/charter.md").unlink()
    r = vendor.install(kit, proj, mattpocock, update=True)
    assert r["removed"] == [doc] and not (proj / doc).exists()


# ---------- 6. keeping a deliberate local edit ----------


def test_keep_records_a_local_edit_until_the_kit_changes_the_file(mattpocock, kit, proj):
    vendor.install(kit, proj, mattpocock)
    (proj / FLOW).write_text("our own flow notes")
    p = _cli("vendor", "verify", "--strict", "--project", str(proj))
    assert p.returncode == 1 and "changed since vendored" in p.stderr and FLOW in p.stderr

    p = _cli("vendor", "resolve", "--keep", FLOW, "--project", str(proj))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout) == {"kept": FLOW}
    assert vendor.read_lock(proj)["kept"][FLOW]
    p = _cli("vendor", "verify", "--strict", "--project", str(proj))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["kept"] == [FLOW]

    # The kit didn't change it: still kept, still passing.
    r = vendor.install(kit, proj, mattpocock, update=True)
    assert FLOW in r["kept"] and not r["conflicts"]
    assert _cli("vendor", "verify", "--strict", "--project", str(proj)).returncode == 0

    # The kit changes it: a conflict, and the keep is gone.
    (kit / "docs/flow.md").write_text("kit v2")
    r = vendor.install(kit, proj, mattpocock, update=True)
    assert r["conflicts"] == [FLOW] and (proj / FLOW).read_text() == "our own flow notes"
    assert FLOW not in (vendor.read_lock(proj).get("kept") or {})


def test_keep_refuses_a_conflict_and_an_unedited_file(mattpocock, kit, proj):
    import pytest

    vendor.install(kit, proj, mattpocock)
    with pytest.raises(vendor.VendorError, match="no local edit to keep"):
        vendor.resolve(proj, FLOW, keep=True)
    (proj / FLOW).write_text("mine")
    (kit / "docs/flow.md").write_text("kit v2")
    vendor.install(kit, proj, mattpocock, update=True)
    with pytest.raises(vendor.VendorError, match="has a conflict"):
        vendor.resolve(proj, FLOW, keep=True)


# ---------- 7. verify fails on conflicts; resolve takes --project anywhere ----------


def test_verify_fails_on_unresolved_conflicts_and_lists_them(mattpocock, kit, proj):
    vendor.install(kit, proj, mattpocock)
    cli_file = ".claude/workflow/bin/workflow/gate.py"
    (proj / cli_file).write_text("# patched locally\n")
    (kit / "scripts/workflow/gate.py").write_text("# the kit's new gate\n")
    assert vendor.install(kit, proj, mattpocock, update=True)["conflicts"] == [cli_file]
    p = _cli("vendor", "verify", "--project", str(proj))
    assert p.returncode == 1 and "unresolved conflicts" in p.stderr and cli_file in p.stderr
    assert json.loads(p.stdout)["conflicts"] == [cli_file]
    (proj / cli_file).write_text("# the kit's new gate\n")
    # --project before the path.
    p = _cli("vendor", "resolve", "--project", str(proj), cli_file)
    assert p.returncode == 0, p.stderr
    assert _cli("vendor", "verify", "--project", str(proj)).returncode == 0


# ---------- 8. Matt Pocock's skills ----------


def test_install_without_mattpocock_warns_and_strict_verify_fails(kit, proj):
    r = vendor.install(kit, proj, None)
    assert any("the Matt Pocock skills (tdd, code-review, to-spec, …) aren't vendored; build-ticket and review-panel need them" in w for w in r["warnings"])
    assert vendor.read_lock(proj)["mattpocock_skills"] == "not_vendored"
    assert _cli("vendor", "verify", "--project", str(proj)).returncode == 0
    p = _cli("vendor", "verify", "--strict", "--project", str(proj))
    assert p.returncode == 1 and "aren't vendored" in p.stderr


def test_no_mattpocock_is_deliberate(kit, proj, tmp_path):
    p = _cli("vendor", "install", "--kit", str(kit), "--project", str(proj), "--no-mattpocock")
    assert p.returncode == 0, p.stderr
    assert "Matt Pocock" not in p.stderr
    assert vendor.read_lock(proj)["mattpocock_skills"] == "declined"
    assert _cli("vendor", "verify", "--strict", "--project", str(proj)).returncode == 0
    r = vendor.install(kit, proj, None, update=True)  # the choice carries over
    assert not any("Matt Pocock" in w for w in r["warnings"])
    assert vendor.read_lock(proj)["mattpocock_skills"] == "declined"


def test_mattpocock_and_no_mattpocock_together_are_refused(mattpocock, kit, proj):
    import pytest

    with pytest.raises(vendor.VendorError, match="not both"):
        vendor.install(kit, proj, mattpocock, no_mattpocock=True)


# ---------- 9. another UserPromptSubmit hook ----------


def test_install_names_an_existing_prompt_hook(mattpocock, kit, proj):
    settings = {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": ".claude/hooks/flow-context.sh"}]}]}}
    (proj / ".claude/settings.json").write_text(json.dumps(settings))
    r = vendor.install(kit, proj, mattpocock)
    w = [x for x in r["warnings"] if "UserPromptSubmit" in x]
    assert len(w) == 1 and ".claude/hooks/flow-context.sh" in w[0] and "twice" in w[0]
    # The kit's own context hook isn't reported on the next update.
    (proj / ".claude/settings.json").write_text(json.dumps({}))
    vendor.install(kit, proj, mattpocock, update=True)
    r = vendor.install(kit, proj, mattpocock, update=True)
    assert not [x for x in r["warnings"] if "UserPromptSubmit" in x]


# ---------- 10. .gitignore ----------


def test_gitignore_gets_pycache(mattpocock, kit, proj):
    r = vendor.install(kit, proj, mattpocock)
    assert r["gitignore_added"] == [".workflow/", "__pycache__/"]
    assert (proj / ".gitignore").read_text() == ".workflow/\n__pycache__/\n"


# ---------- 11. stale files on --adopt ----------


def test_adopt_reports_stale_files_without_deleting_them(mattpocock, kit, proj):
    (proj / ".claude/skills/next").mkdir(parents=True)
    (proj / ".claude/skills/next/SKILL.md").write_text("an older copy")
    (proj / ".claude/skills/next/CONTEXT-FORMAT.md").write_text("left from the earlier copy")
    (proj / ".claude/skills/mine").mkdir(parents=True)
    (proj / ".claude/skills/mine/SKILL.md").write_text("the project's own skill")
    (proj / ".claude/workflow/docs").mkdir(parents=True)
    (proj / ".claude/workflow/docs/old.md").write_text("old")
    r = vendor.install(kit, proj, mattpocock, adopt=True)
    assert r["stale"] == [".claude/skills/next/CONTEXT-FORMAT.md", ".claude/workflow/docs/old.md"]
    assert (proj / ".claude/skills/next/CONTEXT-FORMAT.md").exists()
    p = _cli("vendor", "update", "--kit", str(kit), "--mattpocock", str(mattpocock), "--project", str(proj), "--adopt")
    assert p.returncode == 0 and json.loads(p.stdout)["stale"] == r["stale"]
