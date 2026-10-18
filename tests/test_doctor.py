"""#58: `workflow doctor`, its report, and the Your computer and The kit
groups. Seam 1 of #34: the CLI, with a temporary checkout and profile, and a
fake `python3` and `claude` on the PATH."""

import json
import os
import subprocess
import sys

import pytest

from changelog_notes import since_0110
from conftest import KIT
from workflow import vendor

CLI = KIT / "scripts/workflow.py"
PROFILE_HEAD = '[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "someone"\n'
RUN = '[run]\nticket_environment = "t"\nconductor_environment = "c"\n'


def _prof(project="ruleset = true\n", tail=""):
    """A profile `profile check` has no warning about, with `project` lines
    in [project] and `tail` (more tables) after it."""
    return PROFILE_HEAD + project + RUN + tail
STATUSES = {"fine", "gap", "note", "cant_check"}


def _fake(bin_dir, name, body):
    p = bin_dir / name
    p.write_text("#!/bin/sh\n" + body + "\n")
    p.chmod(0o755)


def _bin(tmp_path, python="3.12.1", claude="2.1.300 (Claude Code)"):
    """A PATH with only a fake `python3` and `claude` on it: None leaves one
    out; a string is what it prints; an int is its exit code, printing nothing."""
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    for name, out in (("python3", python), ("claude", claude)):
        if out is None:
            continue
        _fake(d, name, f"exit {out}" if isinstance(out, int) else f"echo '{out}'")
    return d


def _project(tmp_path, profile=_prof('experience = "new"\nruleset = true\n'), vendored=True, settings=None, local=None, lock_files=None):
    root = tmp_path / "proj"
    (root / ".claude/workflow").mkdir(parents=True)
    if profile is not None:
        (root / ".claude/workflow/profile.toml").write_text(profile)
    if vendored:
        lock = {"kit_version": "0.1.11", "files": lock_files or {}, "mattpocock_skills": "vendored"}
        (root / ".claude/workflow/lock.json").write_text(json.dumps(lock))
    if settings is None:
        settings = vendor.merge_hooks({}) if vendored else {}
    (root / ".claude/settings.json").write_text(json.dumps(settings, indent=2))
    if local is not None:
        (root / ".claude/settings.local.json").write_text(json.dumps(local))
    return root


def _doctor(tmp_path, root, *args, path=None, env=None, home=None):
    home = home or tmp_path / "home"
    home.mkdir(exist_ok=True)
    e = {k: v for k, v in os.environ.items() if k not in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR")}
    e.update({"CLAUDE_PROJECT_DIR": str(root), "HOME": str(home), "PATH": str(path or _bin(tmp_path)), **(env or {})})
    return subprocess.run([sys.executable, "-B", str(CLI), "doctor", *args], cwd=root, env=e, capture_output=True, text=True)


def _report(tmp_path, root, *args, **kw):
    p = _doctor(tmp_path, root, "--json", *args, **kw)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def _lines(report):
    return {ln["id"]: ln for ln in report["lines"]}


def _line(tmp_path, root, id_, *args, **kw):
    lines = _lines(_report(tmp_path, root, *args, **kw))
    assert id_ in lines, sorted(lines)
    return lines[id_]


def _text_has(tmp_path, root, status_word, needle, *args, **kw):
    """The text report shows `needle` on a line marked with `status_word`."""
    p = _doctor(tmp_path, root, *args, **kw)
    assert p.returncode == 0, p.stderr
    assert any(status_word in ln and needle in ln for ln in p.stdout.splitlines()), p.stdout


# The report's shape


def test_a_healthy_vendored_project_is_fine_throughout(tmp_path):
    root = _project(tmp_path)
    r = _report(tmp_path, root)
    for ln in r["lines"]:
        assert set(ln) == {"group", "id", "status", "message", "fix", "offer"}
        assert ln["status"] in STATUSES
        assert ln["group"] in ("Your computer", "The kit")
        assert ln["message"]
    lines = _lines(r)
    for id_ in ("computer.python3", "computer.claude_code", "kit.hooks", "kit.profile", "kit.vendor", "kit.ruleset"):
        assert lines[id_]["status"] == "fine", lines[id_]
        assert lines[id_]["fix"] == ""
    assert "kit.plugin" not in lines  # vendored, plugin off: nothing to say
    assert r["counts"]["gap"] == 0 and r["counts"]["cant_check"] == 0


def test_text_output_groups_the_lines(tmp_path):
    root = _project(tmp_path)
    p = _doctor(tmp_path, root)
    assert p.returncode == 0, p.stderr
    out = p.stdout.splitlines()
    assert "Your computer" in out and "The kit" in out
    assert out.index("Your computer") < out.index("The kit")


def test_the_most_serious_line_comes_first_in_text(tmp_path):
    # The kit has a gap (no profile) and Your computer is all fine: the kit
    # group comes first, its gap at its top.
    root = _project(tmp_path, profile=None)
    p = _doctor(tmp_path, root)
    out = [ln for ln in p.stdout.splitlines() if ln.strip()]
    marked = [ln for ln in out if ln.lstrip().startswith("[")]
    assert marked[0].lstrip().startswith("[gap]"), p.stdout
    assert out.index("The kit") < out.index("Your computer")
    # And the JSON has the same order.
    r = _report(tmp_path, root)
    assert r["lines"][0]["status"] == "gap"
    order = {"gap": 0, "cant_check": 1, "note": 2, "fine": 3}
    kit = [order[ln["status"]] for ln in r["lines"] if ln["group"] == "The kit"]
    assert kit == sorted(kit)


def test_cant_check_comes_before_notes_and_fine(tmp_path):
    root = _project(tmp_path, profile=_prof("ruleset = false\n"))
    r = _report(tmp_path, root, path=_bin(tmp_path, claude=None))
    statuses = [ln["status"] for ln in r["lines"] if ln["group"] == "Your computer"]
    assert statuses[0] == "cant_check"
    kit = [ln["status"] for ln in r["lines"] if ln["group"] == "The kit"]
    assert kit.index("note") < kit.index("fine")
    # No gap anywhere, so the group with a can't-check line leads.
    assert r["lines"][0]["group"] == "Your computer"


# Exit codes


def test_exit_0_always_even_with_gaps(tmp_path):
    root = _project(tmp_path, profile=None)
    assert _doctor(tmp_path, root).returncode == 0
    assert _doctor(tmp_path, root, "--json").returncode == 0


def test_strict_fails_on_a_gap(tmp_path):
    root = _project(tmp_path, profile=None)
    p = _doctor(tmp_path, root, "--strict")
    assert p.returncode != 0
    assert _doctor(tmp_path, root, "--strict", "--json").returncode != 0


def test_strict_fails_on_cant_check(tmp_path):
    root = _project(tmp_path)
    p = _doctor(tmp_path, root, "--strict", path=_bin(tmp_path, claude=None))
    assert p.returncode != 0


def test_strict_passes_on_notes_alone(tmp_path):
    root = _project(tmp_path, profile=_prof("ruleset = false\n"))
    r = _report(tmp_path, root)
    assert r["counts"]["note"] >= 1 and r["counts"]["gap"] == 0 and r["counts"]["cant_check"] == 0
    assert _doctor(tmp_path, root, "--strict").returncode == 0


# Your computer: python3


def test_python3_on_the_path_311_or_newer_is_fine(tmp_path):
    root = _project(tmp_path)
    ln = _line(tmp_path, root, "computer.python3", path=_bin(tmp_path, python="3.11.0"))
    assert ln["status"] == "fine" and "3.11.0" in ln["message"]


def test_an_old_python3_on_the_path_is_a_gap_though_doctor_runs_on_a_newer_one(tmp_path):
    assert sys.version_info >= (3, 11)
    root = _project(tmp_path)
    ln = _line(tmp_path, root, "computer.python3", path=_bin(tmp_path, python="3.9.6"))
    assert ln["status"] == "gap"
    assert "3.9.6" in ln["message"] and "3.11" in ln["message"]
    assert ln["fix"]
    _text_has(tmp_path, root, "[gap]", "3.9.6", path=_bin(tmp_path, python="3.9.6"))


def test_no_python3_on_the_path_is_a_gap(tmp_path):
    root = _project(tmp_path)
    ln = _line(tmp_path, root, "computer.python3", path=_bin(tmp_path, python=None))
    assert ln["status"] == "gap" and ln["fix"]


@pytest.mark.parametrize("python", [1, "not a version"])
def test_a_python3_whose_version_cant_be_read_is_cant_check(tmp_path, python):
    root = _project(tmp_path)
    ln = _line(tmp_path, root, "computer.python3", path=_bin(tmp_path, python=python))
    assert ln["status"] == "cant_check"
    assert "python3 --version" in ln["fix"]


# Your computer: Claude Code


def test_claude_code_version_read_from_claude_version(tmp_path):
    root = _project(tmp_path)
    ln = _line(tmp_path, root, "computer.claude_code", path=_bin(tmp_path, claude="2.1.295 (Claude Code)"))
    assert ln["status"] == "fine" and "2.1.295" in ln["message"]


def test_claude_code_version_given_wins_over_the_command(tmp_path):
    root = _project(tmp_path)
    ln = _line(tmp_path, root, "computer.claude_code", "--claude-version", "2.1.200", path=_bin(tmp_path, claude="2.1.300 (Claude Code)"))
    assert ln["status"] == "gap" and "2.1.200" in ln["message"]
    ln = _line(tmp_path, root, "computer.claude_code", "--claude-version", "2.1.400 (Claude Code)", path=_bin(tmp_path, claude="2.1.100"))
    assert ln["status"] == "fine" and "2.1.400" in ln["message"]


def test_claude_code_older_than_2_1_295_is_a_gap_saying_the_guard_wont_block(tmp_path):
    root = _project(tmp_path)
    ln = _line(tmp_path, root, "computer.claude_code", path=_bin(tmp_path, claude="2.1.294 (Claude Code)"))
    assert ln["status"] == "gap"
    assert "2.1.294" in ln["message"] and "2.1.295" in ln["message"]
    assert "claude update" in ln["fix"]
    dev = _line(tmp_path, root, "computer.claude_code", path=_bin(tmp_path, claude="2.1.294"), env={"WORKFLOW_EXPERIENCE": "developer"})
    assert "onFailure" in dev["message"]


@pytest.mark.parametrize("claude", [None, 1, "something else"])
def test_claude_code_version_unknown_is_cant_check(tmp_path, claude):
    root = _project(tmp_path)
    ln = _line(tmp_path, root, "computer.claude_code", path=_bin(tmp_path, claude=claude))
    assert ln["status"] == "cant_check"
    assert "claude --version" in ln["fix"]


def test_an_unreadable_claude_version_given_is_cant_check(tmp_path):
    root = _project(tmp_path)
    ln = _line(tmp_path, root, "computer.claude_code", "--claude-version", "latest", path=_bin(tmp_path, claude=None))
    assert ln["status"] == "cant_check"


# The kit: hooks, plugin, both on


def test_vendored_hooks_hand_edited_are_a_gap(tmp_path):
    settings = vendor.merge_hooks({})
    settings["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] = 15
    del settings["hooks"]["PreToolUse"][0]["hooks"][0]["onFailure"]
    root = _project(tmp_path, settings=settings)
    ln = _line(tmp_path, root, "kit.hooks")
    assert ln["status"] == "gap" and ln["fix"]
    assert "guard" in ln["message"]


def test_a_missing_kit_hook_is_a_gap(tmp_path):
    settings = vendor.merge_hooks({})
    del settings["hooks"]["SessionStart"]
    root = _project(tmp_path, settings=settings)
    ln = _line(tmp_path, root, "kit.hooks")
    assert ln["status"] == "gap" and "session start" in ln["message"]


def test_a_stale_extra_kit_hook_is_a_gap(tmp_path):
    settings = vendor.merge_hooks({})
    settings["hooks"]["PostToolUse"] = [{"hooks": [{"type": "command", "command": f'python3 "$CLAUDE_PROJECT_DIR/{vendor.HOOK_TAG}" hook old'}]}]
    root = _project(tmp_path, settings=settings)
    assert _line(tmp_path, root, "kit.hooks")["status"] == "gap"


def test_the_projects_own_hooks_beside_the_kits_are_fine(tmp_path):
    own = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo mine"}]}]}}
    root = _project(tmp_path, settings=vendor.merge_hooks(own))
    assert _line(tmp_path, root, "kit.hooks")["status"] == "fine"


def test_unreadable_settings_are_a_gap(tmp_path):
    root = _project(tmp_path)
    (root / ".claude/settings.json").write_text("{not json")
    assert _line(tmp_path, root, "kit.hooks")["status"] == "gap"


def test_plugin_mode_enabled_in_the_projects_settings_is_fine(tmp_path):
    root = _project(tmp_path, vendored=False, settings={"enabledPlugins": {vendor.PLUGIN_KEY: True}})
    lines = _lines(_report(tmp_path, root))
    assert lines["kit.plugin"]["status"] == "fine"
    assert "kit.hooks" not in lines and "kit.vendor" not in lines  # vendored only


def test_plugin_mode_enabled_in_the_users_settings_is_fine(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {vendor.PLUGIN_KEY: True}}))
    root = _project(tmp_path, vendored=False)
    assert _line(tmp_path, root, "kit.plugin", home=home)["status"] == "fine"


def test_plugin_mode_not_enabled_is_a_gap(tmp_path):
    root = _project(tmp_path, vendored=False)
    ln = _line(tmp_path, root, "kit.plugin")
    assert ln["status"] == "gap" and ln["fix"]
    # Turned off for this project, though on for the user: still a gap.
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {vendor.PLUGIN_KEY: True}}))
    (root / ".claude/settings.local.json").write_text(json.dumps({"enabledPlugins": {vendor.PLUGIN_KEY: False}}))
    assert _line(tmp_path, root, "kit.plugin", home=home)["status"] == "gap"


def test_both_on_is_a_gap_naming_which_to_turn_off(tmp_path):
    settings = vendor.merge_hooks({"enabledPlugins": {vendor.PLUGIN_KEY: True}})
    root = _project(tmp_path, settings=settings)
    lines = _lines(_report(tmp_path, root))
    ln = lines["kit.plugin"]
    assert ln["status"] == "gap"
    assert "plugin" in ln["fix"] and ".claude/settings.json" in ln["fix"]
    assert lines["kit.hooks"]["status"] == "fine"
    _text_has(tmp_path, root, "[gap]", "plugin")


def test_both_on_through_the_users_settings_names_the_local_file(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {vendor.PLUGIN_KEY: True}}))
    root = _project(tmp_path)
    ln = _line(tmp_path, root, "kit.plugin", home=home)
    assert ln["status"] == "gap" and ".claude/settings.local.json" in ln["fix"]


# The kit: profile check and vendor verify


def test_no_profile_is_a_gap(tmp_path):
    root = _project(tmp_path, profile=None)
    lines = _lines(_report(tmp_path, root))
    assert lines["kit.profile"]["status"] == "gap"
    assert lines["kit.ruleset"]["status"] == "cant_check"


def test_profile_check_errors_are_gaps(tmp_path):
    root = _project(tmp_path, profile=_prof('ruleset = "yes"\n'))
    ln = _line(tmp_path, root, "kit.profile")
    assert ln["status"] == "gap" and "project.ruleset" in ln["message"]
    _text_has(tmp_path, root, "[gap]", "project.ruleset")


def test_profile_check_warnings_are_notes(tmp_path):
    root = _project(tmp_path, profile=_prof(tail='[areas]\nweb = ["web/**"]\n'))
    ln = _line(tmp_path, root, "kit.profile")
    assert ln["status"] == "note" and "areas.web" in ln["message"]
    _text_has(tmp_path, root, "[note]", "areas.web")


def test_a_clean_profile_is_fine(tmp_path):
    root = _project(tmp_path, profile=_prof())
    assert _line(tmp_path, root, "kit.profile")["status"] == "fine"


def test_vendor_verify_failing_is_a_gap(tmp_path):
    root = _project(tmp_path, lock_files={".claude/skills/gone/SKILL.md": "0" * 64})
    ln = _line(tmp_path, root, "kit.vendor")
    assert ln["status"] == "gap" and ".claude/skills/gone/SKILL.md" in ln["message"] and ln["fix"]


def test_a_vendored_file_changed_by_hand_is_a_gap(tmp_path):
    root = _project(tmp_path, lock_files={".claude/skills/x/SKILL.md": "0" * 64})
    (root / ".claude/skills/x").mkdir(parents=True)
    (root / ".claude/skills/x/SKILL.md").write_text("edited")
    ln = _line(tmp_path, root, "kit.vendor")
    assert ln["status"] == "gap" and ".claude/skills/x/SKILL.md" in ln["message"]


def test_an_unreadable_lock_is_a_gap(tmp_path):
    root = _project(tmp_path)
    (root / ".claude/workflow/lock.json").write_text("{nope")
    assert _line(tmp_path, root, "kit.vendor")["status"] == "gap"


# The kit: experience and ruleset


@pytest.mark.parametrize(
    "setup, env, level, source",
    [
        ("env", {"WORKFLOW_EXPERIENCE": "developer"}, "developer", "environment"),
        ("file", {}, "developer", "local file"),
        ("profile", {}, "developer", "profile"),
        ("none", {}, None, "unknown"),
    ],
)
def test_experience_is_reported_with_its_source(tmp_path, setup, env, level, source):
    exp = 'experience = "developer"\n' if setup == "profile" else 'experience = "new"\n' if setup != "none" else ""
    root = _project(tmp_path, profile=_prof(exp + "ruleset = true\n"))
    if setup == "file":
        (root / ".workflow").mkdir()
        (root / ".workflow/experience").write_text("developer\n")
    r = _report(tmp_path, root, env=env)
    ln = _lines(r)["kit.experience"]
    assert r["experience"] == {"level": level, "source": source, "default": {"profile": "developer", "none": None}.get(setup, "new")}
    if level:
        assert ln["status"] == "fine"
        assert level in ln["message"] or "developer" in ln["message"]
    else:
        assert ln["status"] == "note" and ln["fix"]
    # The source shows in the message.
    words = {"environment": "WORKFLOW_EXPERIENCE", "local file": ".workflow/experience", "profile": "project.experience"}
    if source in words:
        assert words[source] in ln["message"]


def test_an_ignored_experience_value_is_a_note(tmp_path):
    root = _project(tmp_path, profile=_prof('experience = "new"\nruleset = true\n'))
    ln = _line(tmp_path, root, "kit.experience", env={"WORKFLOW_EXPERIENCE": "expert"})
    assert ln["status"] == "note" and "WORKFLOW_EXPERIENCE" in ln["message"]


def test_ruleset_true_is_fine(tmp_path):
    root = _project(tmp_path)
    ln = _line(tmp_path, root, "kit.ruleset")
    assert ln["status"] == "fine" and ln["offer"] is None


def test_ruleset_false_is_a_note_offering_protect_main(tmp_path):
    root = _project(tmp_path, profile=_prof("ruleset = false\n"))
    ln = _line(tmp_path, root, "kit.ruleset")
    assert ln["status"] == "note" and ln["offer"] == "protect_main"
    _text_has(tmp_path, root, "[note]", "main")


def test_no_ruleset_is_not_set_as_before_a_note(tmp_path):
    root = _project(tmp_path, profile=_prof(""))
    ln = _line(tmp_path, root, "kit.ruleset")
    assert ln["status"] == "note" and "not set (as before)" in ln["message"]


# Wording by experience


def _every_status_project(tmp_path):
    """A project where the kit's and the computer's lines take every status."""
    settings = vendor.merge_hooks({"enabledPlugins": {vendor.PLUGIN_KEY: True}})
    settings["hooks"]["Stop"][0]["hooks"][0]["timeout"] = 99
    root = _project(
        tmp_path,
        profile=_prof("ruleset = false\n", '[areas]\nweb = ["web/**"]\n'),
        settings=settings,
        lock_files={".claude/skills/gone/SKILL.md": "0" * 64},
    )
    return root, _bin(tmp_path, python="3.9.6", claude=None)


def test_each_message_and_fix_differs_by_experience_while_every_status_is_the_same(tmp_path):
    root, path = _every_status_project(tmp_path)
    new = _report(tmp_path, root, path=path, env={"WORKFLOW_EXPERIENCE": "new"})
    dev = _report(tmp_path, root, path=path, env={"WORKFLOW_EXPERIENCE": "developer"})
    assert {ln["status"] for ln in new["lines"]} >= {"gap", "note", "cant_check"}
    n, d = _lines(new), _lines(dev)
    assert set(n) == set(d)
    for id_ in n:
        if id_ == "kit.experience":
            continue  # it reports the level itself
        assert n[id_]["status"] == d[id_]["status"], id_
        assert n[id_]["offer"] == d[id_]["offer"], id_
        assert n[id_]["message"] != d[id_]["message"], id_
        if n[id_]["fix"] or d[id_]["fix"]:
            assert n[id_]["fix"] != d[id_]["fix"], id_


def test_fine_lines_are_worded_by_experience_too(tmp_path):
    root = _project(tmp_path)
    n = _lines(_report(tmp_path, root, env={"WORKFLOW_EXPERIENCE": "new"}))
    d = _lines(_report(tmp_path, root, env={"WORKFLOW_EXPERIENCE": "developer"}))
    for id_ in ("computer.python3", "computer.claude_code", "kit.hooks", "kit.vendor", "kit.ruleset"):
        assert n[id_]["status"] == d[id_]["status"] == "fine"
        assert n[id_]["message"] != d[id_]["message"], id_


def test_unknown_experience_reads_as_new(tmp_path):
    root, path = _every_status_project(tmp_path)
    unknown = _report(tmp_path, root, path=path)
    new = _report(tmp_path, root, path=path, env={"WORKFLOW_EXPERIENCE": "new"})
    u, n = _lines(unknown), _lines(new)
    for id_ in u:
        if id_ == "kit.experience":
            continue
        assert (u[id_]["status"], u[id_]["message"], u[id_]["fix"]) == (n[id_]["status"], n[id_]["message"], n[id_]["fix"]), id_


# It never changes anything


def _snapshot(root):
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            p = os.path.join(dirpath, name)
            st = os.lstat(p)
            out[p] = (st.st_mode, st.st_size, st.st_mtime_ns, open(p, "rb").read() if os.path.isfile(p) else None)
    return out


def test_nothing_in_the_checkout_changes_after_a_run(tmp_path):
    root, path = _every_status_project(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    before = _snapshot(root)
    for args in ((), ("--json",), ("--strict",), ("--json", "--strict", "--claude-version", "2.1.300")):
        _doctor(tmp_path, root, *args, path=path)
        _doctor(tmp_path, root, *args)
    assert _snapshot(root) == before


# Docs


def test_the_readme_command_list_names_doctor():
    readme = (KIT / "README.md").read_text()
    row = next(ln for ln in readme.splitlines() if ln.startswith("| `scripts/workflow.py`"))
    assert "`doctor`" in row


def test_install_md_names_doctor_for_plugin_mode():
    text = (KIT / "docs/install.md").read_text()
    plugin = text[text.index("## Plugin"):text.index("## Every project")]
    assert "workflow doctor" in plugin


def test_the_changelog_has_a_note_under_unreleased():
    notes = since_0110()
    unreleased = notes[: notes.index("\n## 0.1.11\n")]
    assert "workflow doctor" in unreleased and "#58" in unreleased


def test_the_cli_docstring_lists_doctor():
    p = subprocess.run([sys.executable, "-B", str(CLI), "--help"], capture_output=True, text=True)
    assert "workflow doctor" in p.stdout
