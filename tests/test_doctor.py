"""#58: `workflow doctor`, its report, and the Your computer and The kit
groups. Seam 1 of #34: the CLI, with a temporary checkout and profile, and a
fake `python3` and `claude` on the PATH, a fake `gh` that answers for a
protected repository (the GitHub group's own tests are test_doctor_github.py),
and an environments file with both of the profile's (the Cloud group's are
test_doctor_cloud.py)."""

import functools
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import fake_gh
from changelog_notes import since_0110
from conftest import KIT, at_once, copy_kit_package
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


# GitHub's answers for a repository whose base branch is protected as the kit
# sets it up (GET repos/<repo>/rulesets/<id>, GET repos/<repo>), made up.
RULESET = {
    "id": 101,
    "name": "Protect main",
    "target": "branch",
    "source_type": "Repository",
    "source": "acme/demo",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "bypass_actors": [],
    "rules": [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {"type": "pull_request", "parameters": {"required_approving_review_count": 0, "dismiss_stale_reviews_on_push": False,
                                                "require_code_owner_review": False, "require_last_push_approval": False,
                                                "required_review_thread_resolution": False}},
        {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": True,
                                                          "required_status_checks": [{"context": "tests"}]}},
    ],
}
SETTINGS = {"full_name": "acme/demo", "default_branch": "main", "allow_merge_commit": True, "allow_auto_merge": True, "allow_squash_merge": True}
CODEOWNERS = "/.claude/ @someone\n/.github/workflows/ @someone\n"
# The account's environments as `list_environments` returns them, with both of
# the ones RUN names, made up.
ENVIRONMENTS = {
    "environments": [
        {"environment_id": "env_01ticket", "name": "t", "description": "", "state": "active", "kind": "anthropic_cloud", "created_at": "2026-10-01T09:00:00Z"},
        {"environment_id": "env_01conductor", "name": "c", "description": "", "state": "active", "kind": "anthropic_cloud", "created_at": "2026-10-01T09:01:00Z"},
        {"environment_id": "env_01default", "name": "Default", "description": "", "state": "active", "kind": "anthropic_cloud", "created_at": "2026-09-01T09:00:00Z"},
    ],
    "has_more": False,
}


def gh_routes(rulesets=(RULESET,), settings=SETTINGS, repo="acme/demo"):
    """The fake `gh`'s answers: the rulesets' summaries, each in full, and the
    repository's settings."""
    routes = {f"repos/{repo}/rulesets": fake_gh.pages([{k: rs[k] for k in ("id", "name") if k in rs} for rs in rulesets])}
    routes.update({f"repos/{repo}/rulesets/{rs['id']}": rs for rs in rulesets})
    if settings is not None:
        routes[f"repos/{repo}"] = settings
    return routes


def _bin(tmp_path, python="3.12.1", claude="2.1.300 (Claude Code)", gh=None):
    """A PATH with only a fake `python3`, `claude` and `gh` on it: None leaves
    `python3` or `claude` out; a string is what it prints; an int is its exit
    code, printing nothing. `gh` answers for a protected repository unless
    given its routes, or False to leave it out."""
    d = tmp_path / "bin"
    d.mkdir(parents=True, exist_ok=True)
    for name, out in (("python3", python), ("claude", claude)):
        if out is None:
            (d / name).unlink(missing_ok=True)
            continue
        _fake(d, name, f"exit {out}" if isinstance(out, int) else f"echo '{out}'")
    if gh is False:
        (d / "gh").unlink(missing_ok=True)
    else:
        fake_gh.write(d, gh_routes() if gh is None else gh)
    return d


def _project(tmp_path, profile=_prof('experience = "new"\nruleset = true\n'), vendored=True, settings=None, local=None, lock_files=None,
             codeowners=CODEOWNERS, compiled=True):
    root = tmp_path / "proj"
    (root / ".claude/workflow").mkdir(parents=True)
    if codeowners is not None:
        (root / ".github").mkdir()
        (root / ".github/CODEOWNERS").write_text(codeowners)
    if profile is not None:
        (root / ".claude/workflow/profile.toml").write_text(profile)
    if vendored:
        lock = {"kit_version": "0.1.11", "files": lock_files or {}, "mattpocock_skills": "vendored"}
        (root / ".claude/workflow/lock.json").write_text(json.dumps(lock))
        # The project's own copy of the CLI, with the files `vendor install`
        # puts there: the hooks are compared with the entries of the kit that
        # runs doctor. With `compiled`, its bytecode is there too (which
        # `vendor install` never copies), so a run doesn't compile it.
        bin_dir = root / ".claude/workflow/bin"
        bin_dir.mkdir()
        shutil.copy(CLI, bin_dir / "workflow.py")
        copy_kit_package(bin_dir / "workflow", compiled=compiled)
    if settings is None:
        settings = vendor.merge_hooks({}) if vendored else {}
    (root / ".claude/settings.json").write_text(json.dumps(settings, indent=2))
    if local is not None:
        (root / ".claude/settings.local.json").write_text(json.dumps(local))
    return root


def _doctor(tmp_path, root, *args, path=None, env=None, home=None, cli=None, environments=ENVIRONMENTS):
    """Doctor run from the project's own copy of the CLI when it has one,
    else from the kit's source (plugin mode, or `cli`). `environments` is
    given as `--environments`, outside the checkout, unless the arguments give
    their own or it is None."""
    if environments is not None and "--environments" not in args:
        d = tmp_path / "cloud-input"
        d.mkdir(parents=True, exist_ok=True)
        (d / "environments.json").write_text(json.dumps(environments))
        args = (*args, "--environments", str(d / "environments.json"))
    home = home or tmp_path / "home"
    home.mkdir(exist_ok=True)
    e = {k: v for k, v in os.environ.items() if k not in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "COLUMNS")}
    e.update({"CLAUDE_PROJECT_DIR": str(root), "HOME": str(home), "PATH": str(path or _bin(tmp_path)), **(env or {})})
    copy = root / ".claude/workflow/bin/workflow.py"
    cli = cli or (copy if copy.is_file() else CLI)
    return subprocess.run([sys.executable, "-B", str(cli), "doctor", *args], cwd=root, env=e, capture_output=True, text=True)


def _each_at_once(tmp_path, run, calls):
    """`run` (`_doctor` or `_report`) for each (root, args, keywords) in
    `calls`, at the same time (#193), the results in order. Each call is given
    a folder of its own outside every checkout as its `tmp_path`, so no two
    share an input file, a fake PATH or a home."""
    jobs, top = [], Path(tempfile.mkdtemp(prefix="at-once-", dir=tmp_path))
    for k, (root, args, kw) in enumerate(calls):
        work = top / str(k)
        work.mkdir()
        jobs.append(functools.partial(run, work, root, *args, **kw))
    return at_once(jobs)


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


def _entries(out):
    """The text report's lines, each with its wrapped continuation and fix
    joined into one string."""
    entries = []
    for ln in out.splitlines():
        if ln.startswith("  ["):
            entries.append(ln.strip())
        elif ln.startswith("    ") and entries:
            entries[-1] += " " + ln.strip()
    return entries


def _text_has(tmp_path, root, status_word, needle, *args, **kw):
    """The text report shows `needle` in a line marked with `status_word`."""
    p = _doctor(tmp_path, root, *args, **kw)
    assert p.returncode == 0, p.stderr
    assert any(e.startswith(status_word) and needle in e for e in _entries(p.stdout)), p.stdout


# The report's shape


def test_a_healthy_vendored_project_is_fine_throughout(tmp_path):
    root = _project(tmp_path)
    r = _report(tmp_path, root)
    for ln in r["lines"]:
        assert set(ln) == {"group", "id", "status", "message", "fix", "offer"}
        assert ln["status"] in STATUSES
        assert ln["group"] in ("Your computer", "The kit", "GitHub", "Cloud")
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


def test_a_python3_whose_version_cant_be_read_is_cant_check(tmp_path):
    root = _project(tmp_path)
    ln = _line(tmp_path, root, "computer.python3", path=_bin(tmp_path, python="not a version"))
    assert ln["status"] == "cant_check"
    assert "python3 --version" in ln["fix"]


def test_a_python3_that_doesnt_run_is_a_gap(tmp_path):
    """A stub or a broken shim: `command -v python3` finds it, so the hooks
    run it, it fails, and they take their fallback."""
    root = _project(tmp_path)
    ln = _line(tmp_path, root, "computer.python3", path=_bin(tmp_path, python=1))
    assert ln["status"] == "gap" and ln["fix"]


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
    lines = _lines(_report(tmp_path, root))
    assert lines["kit.settings"]["status"] == "gap" and ".claude/settings.json" in lines["kit.settings"]["message"]
    # Said once: the lines that need the file wait on it.
    assert lines["kit.hooks"]["status"] == "cant_check"
    assert lines["kit.vendor"]["status"] == "fine"  # the copy's files don't depend on it


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
    ln = _line(tmp_path, root, "kit.profile", env={"WORKFLOW_EXPERIENCE": "developer"})
    assert ln["status"] == "note" and "areas.web" in ln["message"]
    _text_has(tmp_path, root, "[note]", "areas.web", env={"WORKFLOW_EXPERIENCE": "developer"})
    # New to building: the count, and how to see the list.
    new = _line(tmp_path, root, "kit.profile")
    assert new["status"] == "note" and "profile check" in new["fix"]


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


def _every_status_project(tmp_path, compiled=True):
    """A project where the kit's and the computer's lines take every status."""
    settings = vendor.merge_hooks({"enabledPlugins": {vendor.PLUGIN_KEY: True}})
    settings["hooks"]["Stop"][0]["hooks"][0]["timeout"] = 99
    root = _project(
        tmp_path,
        profile=_prof("ruleset = false\n", '[areas]\nweb = ["web/**"]\n'),
        settings=settings,
        lock_files={".claude/skills/gone/SKILL.md": "0" * 64},
        compiled=compiled,
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


def _unchanged_after_doctor(tmp_path, calls):
    """Run doctor for each (root, args, keywords) in `calls` at once, and
    check that no checkout among them changed: every snapshot is taken before
    the first run."""
    roots = list(dict.fromkeys(root for root, _, _ in calls))
    before = {root: _snapshot(root) for root in roots}
    _each_at_once(tmp_path, _doctor, calls)
    for root in roots:
        assert _snapshot(root) == before[root], root


def test_nothing_in_the_checkout_changes_after_a_run(tmp_path):
    root, path = _every_status_project(tmp_path, compiled=False)  # so bytecode written would show
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    before = _snapshot(root)
    healthy = _bin(tmp_path / "ok")
    _each_at_once(tmp_path, _doctor, [(root, args, {"path": fake_path})
                                      for args in ((), ("--json",), ("--strict",), ("--json", "--strict", "--claude-version", "2.1.300"))
                                      for fake_path in (path, healthy)])
    assert _report(tmp_path, root, path=path)["counts"]["cant_check"] >= 1  # the every-status fakes still there
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


# Round 1 of the review: what broke or misled


def test_a_real_python3_on_the_path_is_read(tmp_path):
    """The fakes print a fixed string; this one runs doctor's own program."""
    path = _bin(tmp_path, python=None)
    (path / "python3").symlink_to(sys.executable)
    root = _project(tmp_path)
    ln = _line(tmp_path, root, "computer.python3", path=path)
    want = "%d.%d.%d" % tuple(sys.version_info[:3])
    assert ln["status"] == "fine" and want in ln["message"]


def test_a_notice_before_claudes_version_isnt_taken_for_it(tmp_path):
    root = _project(tmp_path)
    path = _bin(tmp_path, claude=None)
    _fake(path, "claude", "echo 'node v18.19.0 is deprecated'; echo '2.1.200 (Claude Code)'")
    ln = _line(tmp_path, root, "computer.claude_code", path=path)
    assert ln["status"] == "gap" and "2.1.200" in ln["message"]


def test_a_blank_claude_version_falls_back_to_the_command(tmp_path):
    root = _project(tmp_path)
    ln = _line(tmp_path, root, "computer.claude_code", "--claude-version", " ", path=_bin(tmp_path, claude="2.1.300 (Claude Code)"))
    assert ln["status"] == "fine" and "2.1.300" in ln["message"]


def test_an_odd_claude_version_is_shown_safely(tmp_path):
    root = _project(tmp_path)
    ln = _line(tmp_path, root, "computer.claude_code", "--claude-version", "a`b\nc" + "x" * 80, path=_bin(tmp_path, claude=None),
               env={"WORKFLOW_EXPERIENCE": "developer"})
    assert ln["status"] == "cant_check"
    assert "\n" not in ln["message"] and "a'b c" in ln["message"] and "…" in ln["message"]


@pytest.mark.parametrize("name", [".claude/settings.json", ".claude/workflow/lock.json", ".claude/workflow/profile.toml"])
@pytest.mark.parametrize("bad", ["utf16", "directory"])
def test_an_unreadable_file_is_a_line_never_a_traceback(tmp_path, name, bad):
    root = _project(tmp_path)
    f = root / name
    if bad == "utf16":
        f.write_bytes(f.read_text().encode("utf-16"))
    else:
        f.unlink()
        f.mkdir()
    for args in ((), ("--json",)):
        p = _doctor(tmp_path, root, *args)
        assert p.returncode == 0, p.stderr
        assert "Traceback" not in p.stderr
    r = _report(tmp_path, root)
    assert r["counts"]["gap"] >= 1
    want = {".claude/settings.json": "kit.settings", ".claude/workflow/lock.json": "kit.vendor", ".claude/workflow/profile.toml": "kit.profile"}[name]
    assert _lines(r)[want]["status"] == "gap"
    assert _doctor(tmp_path, root, "--strict").returncode == 1


def test_hooks_of_the_wrong_shape_are_a_gap(tmp_path):
    settings = vendor.merge_hooks({})
    settings["hooks"]["Notification"] = 5
    settings["hooks"]["Stop"] = [{"hooks": True}]
    root = _project(tmp_path, settings=settings)
    ln = _line(tmp_path, root, "kit.hooks")
    assert ln["status"] == "gap" and "status gate" in ln["message"]


def test_a_kit_hook_sharing_an_entry_with_the_projects_hook_is_named(tmp_path):
    settings = vendor.merge_hooks({})
    settings["hooks"]["Stop"][0]["hooks"].append({"type": "command", "command": "echo mine"})
    root = _project(tmp_path, settings=settings)
    ln = _line(tmp_path, root, "kit.hooks")
    assert ln["status"] == "gap" and "shares an entry" in ln["message"]


@pytest.mark.parametrize("where", ["project", "local", "user"])
def test_disable_all_hooks_is_a_gap(tmp_path, where):
    settings = vendor.merge_hooks({})
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    if where == "project":
        settings["disableAllHooks"] = True
    root = _project(tmp_path, settings=settings, local={"disableAllHooks": True} if where == "local" else None)
    if where == "user":
        (home / ".claude/settings.json").write_text(json.dumps({"disableAllHooks": True}))
    lines = _lines(_report(tmp_path, root, home=home))
    assert lines["kit.hooks_off"]["status"] == "gap"
    assert "disableAllHooks" in lines["kit.hooks_off"]["fix"]


def test_plugin_mode_with_unreadable_settings_says_so_not_install_it(tmp_path):
    root = _project(tmp_path, vendored=False)
    (root / ".claude/settings.json").write_text("[]")
    lines = _lines(_report(tmp_path, root))
    assert lines["kit.settings"]["status"] == "gap"
    assert lines["kit.plugin"]["status"] == "cant_check"
    assert "install" not in lines["kit.plugin"]["fix"]


def test_an_unreadable_user_settings_file_is_reported(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").write_text("{")
    root = _project(tmp_path)
    ln = _line(tmp_path, root, "kit.settings", home=home)
    assert ln["status"] == "gap" and "~/.claude/settings.json" in ln["message"]


def test_claude_config_dir_is_named_as_it_is(tmp_path):
    conf = tmp_path / "conf"
    conf.mkdir()
    (conf / "settings.json").write_text(json.dumps({"enabledPlugins": {vendor.PLUGIN_KEY: True}}))
    root = _project(tmp_path, vendored=False)
    ln = _line(tmp_path, root, "kit.plugin", env={"CLAUDE_CONFIG_DIR": str(conf), "WORKFLOW_EXPERIENCE": "developer"})
    assert ln["status"] == "fine" and str(conf / "settings.json") in ln["message"]


def test_another_kits_entries_cant_judge_a_vendored_copys_hooks(tmp_path):
    """Doctor from a different kit (a checkout of the kit, the plugin) can't
    tell a stale update from its own newer entries: it says so."""
    settings = vendor.merge_hooks({})
    settings["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] = 15
    root = _project(tmp_path, settings=settings)
    p = _doctor(tmp_path, root, "--json", cli=CLI)
    ln = _lines(json.loads(p.stdout))["kit.hooks"]
    assert ln["status"] == "cant_check"
    assert ".claude/workflow/bin/workflow.py doctor" in ln["fix"]
    # Matching entries are fine whichever kit compares them.
    root2 = _project(tmp_path / "two")
    assert _lines(json.loads(_doctor(tmp_path, root2, "--json", cli=CLI).stdout))["kit.hooks"]["status"] == "fine"


def test_matt_pocock_skills_not_vendored_is_a_note_and_declined_is_fine(tmp_path):
    root = _project(tmp_path)
    lock = json.loads((root / ".claude/workflow/lock.json").read_text())
    lock["mattpocock_skills"] = "not_vendored"
    (root / ".claude/workflow/lock.json").write_text(json.dumps(lock))
    ln = _line(tmp_path, root, "kit.vendor")
    assert ln["status"] == "note" and ln["fix"]
    lock["mattpocock_skills"] = "declined"
    (root / ".claude/workflow/lock.json").write_text(json.dumps(lock))
    assert _line(tmp_path, root, "kit.vendor")["status"] == "fine"


def test_text_shows_fine_and_cant_check_lines(tmp_path):
    root = _project(tmp_path)
    _text_has(tmp_path, root, "[fine]", "hooks")
    _text_has(tmp_path, root, "[fine]", "2.1.300")
    _text_has(tmp_path, root, "[can't check]", "Claude Code", path=_bin(tmp_path, claude=None))
    _text_has(tmp_path, root, "[gap]", "2.1.200", "--claude-version", "2.1.200")


def test_text_wraps_to_a_narrow_terminal(tmp_path):
    root, path = _every_status_project(tmp_path)
    p = _doctor(tmp_path, root, path=path, env={"COLUMNS": "40"})
    assert p.returncode == 0
    # Only a word longer than the width (a path, a command) may run over.
    for ln in p.stdout.splitlines():
        # Over the width only with a word that can't fit on any line of its own.
        assert len(ln) <= 40 or any(len(w) > 40 - 8 for w in ln.split()), ln


def test_a_notes_next_step_isnt_called_a_fix(tmp_path):
    root = _project(tmp_path, profile=_prof("ruleset = false\n"))
    p = _doctor(tmp_path, root)
    e = next(x for x in _entries(p.stdout) if x.startswith("[note]") and "Solo mode" in x)
    assert "Next:" in e and "Fix:" not in e


def _more_states(tmp_path):
    """Projects whose lines take the states `_every_status_project` doesn't."""
    yield _project(tmp_path / "a", vendored=False, settings={"enabledPlugins": {vendor.PLUGIN_KEY: True}}, profile=_prof("")), None
    yield _project(tmp_path / "b", vendored=False, profile=_prof('ruleset = "yes"\n')), _bin(tmp_path / "b", python="no", claude="2.1.100")
    yield _project(tmp_path / "e", vendored=False, profile=_prof("")), _bin(tmp_path / "e", python=1)
    root = _project(tmp_path / "c")
    (root / ".claude/settings.json").write_text("[]")
    yield root, None
    yield _project(tmp_path / "d", profile=None), _bin(tmp_path / "d", python=None)


def test_every_other_state_is_worded_both_ways_too(tmp_path):
    seen = set()
    for root, path in _more_states(tmp_path):
        n = _lines(_report(tmp_path, root, path=path, env={"WORKFLOW_EXPERIENCE": "new"}))
        d = _lines(_report(tmp_path, root, path=path, env={"WORKFLOW_EXPERIENCE": "developer"}))
        assert set(n) == set(d)
        for id_ in n:
            if id_ == "kit.experience":
                continue
            seen.add((id_, n[id_]["status"]))
            assert n[id_]["status"] == d[id_]["status"], id_
            assert n[id_]["message"] != d[id_]["message"], (id_, n[id_]["message"])
            if n[id_]["fix"] or d[id_]["fix"]:
                assert n[id_]["fix"] != d[id_]["fix"], id_
    for want in (("kit.plugin", "fine"), ("kit.plugin", "gap"), ("kit.ruleset", "note"), ("computer.python3", "cant_check"),
                 ("kit.settings", "gap"), ("kit.hooks", "cant_check"), ("kit.profile", "gap"), ("kit.ruleset", "cant_check"),
                 ("computer.python3", "gap"), ("computer.claude_code", "gap")):
        assert want in seen, want


def test_error_lines_leave_out_the_checkouts_path(tmp_path):
    root = _project(tmp_path, profile="[project\n")
    ln = _line(tmp_path, root, "kit.profile")
    assert ln["status"] == "gap" and str(root) not in ln["message"]


# Round 2 of the review


def test_a_broken_local_settings_file_is_one_gap(tmp_path):
    root = _project(tmp_path)
    (root / ".claude/settings.local.json").write_text("{bad")
    lines = _lines(_report(tmp_path, root))
    assert lines["kit.settings"]["status"] == "gap" and ".claude/settings.local.json" in lines["kit.settings"]["message"]
    assert lines["kit.vendor"]["status"] == "fine" and lines["kit.hooks"]["status"] == "fine"
    assert [ln["id"] for ln in _report(tmp_path, root)["lines"] if ln["status"] == "gap"] == ["kit.settings"]


@pytest.mark.parametrize("name, value", [(".claude/settings.json", ["x"]), (".claude/settings.local.json", "yes")])
def test_enabled_plugins_of_the_wrong_shape_is_a_settings_gap_in_plain_words(tmp_path, name, value):
    root = _project(tmp_path)
    data = json.loads((root / name).read_text()) if (root / name).exists() else {}
    data["enabledPlugins"] = value
    (root / name).write_text(json.dumps(data))
    r = _report(tmp_path, root)
    lines = _lines(r)
    assert lines["kit.settings"]["status"] == "gap" and "enabledPlugins" in lines["kit.settings"]["message"]
    assert not any("object has no attribute" in ln["message"] for ln in r["lines"])


@pytest.mark.parametrize("name", [".claude/settings.local.json", ".claude/workflow/profile.toml", ".claude/workflow/flow.md", ".claude/workflow/lock.json"])
def test_a_pipe_never_blocks_doctor(tmp_path, name):
    root = _project(tmp_path, lock_files={".claude/workflow/flow.md": "0" * 64})
    f = root / name
    f.unlink(missing_ok=True)
    os.mkfifo(f)
    p = subprocess.run([sys.executable, "-B", str(root / ".claude/workflow/bin/workflow.py"), "doctor", "--json"], cwd=root,
                       env={**os.environ, "CLAUDE_PROJECT_DIR": str(root), "HOME": str(tmp_path), "PATH": str(_bin(tmp_path))},
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["counts"]["gap"] >= 1


def test_a_copy_left_without_its_lock_isnt_told_to_install_the_plugin(tmp_path):
    root = _project(tmp_path)
    (root / ".claude/workflow/lock.json").unlink()
    lines = _lines(_report(tmp_path, root))
    assert lines["kit.vendor"]["status"] == "gap" and "lock.json" in lines["kit.vendor"]["fix"]
    assert "kit.plugin" not in lines or "install" not in lines["kit.plugin"]["fix"]
    # With the plugin on as well: both on.
    settings = json.loads((root / ".claude/settings.json").read_text())
    settings["enabledPlugins"] = {vendor.PLUGIN_KEY: True}
    (root / ".claude/settings.json").write_text(json.dumps(settings))
    assert _line(tmp_path, root, "kit.plugin")["status"] == "gap"


def test_a_copy_older_than_doctor_is_told_to_update_not_to_run_its_doctor(tmp_path):
    settings = vendor.merge_hooks({})
    settings["hooks"]["Stop"][0]["hooks"][0]["timeout"] = 99
    root = _project(tmp_path, settings=settings)
    cli = root / ".claude/workflow/bin/workflow/cli.py"
    cli.write_text(cli.read_text().replace('add_parser("doctor"', 'add_parser("not-yet"'))
    ln = _lines(json.loads(_doctor(tmp_path, root, "--json", cli=CLI).stdout))["kit.hooks"]
    assert ln["status"] == "cant_check" and "update" in ln["fix"] and "doctor`" not in ln["fix"]


def test_the_plugin_turned_off_locally_is_told_where(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {vendor.PLUGIN_KEY: True}}))
    root = _project(tmp_path, vendored=False, local={"enabledPlugins": {vendor.PLUGIN_KEY: False}})
    ln = _line(tmp_path, root, "kit.plugin", home=home)
    assert ln["status"] == "gap" and ".claude/settings.local.json" in ln["fix"] and "install" not in ln["fix"]


def test_disable_all_hooks_follows_the_most_specific_file_and_wants_true(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").write_text(json.dumps({"disableAllHooks": True}))
    root = _project(tmp_path, local={"disableAllHooks": False})
    assert "kit.hooks_off" not in _lines(_report(tmp_path, root, home=home))
    root2 = _project(tmp_path / "two", local={"disableAllHooks": "no"})
    assert "kit.hooks_off" not in _lines(_report(tmp_path, root2, home=tmp_path / "two" / "home"))


def test_a_pre_release_of_the_minimum_is_older_than_it(tmp_path):
    root = _project(tmp_path)
    assert _line(tmp_path, root, "computer.claude_code", "--claude-version", "2.1.295-beta.1")["status"] == "gap"
    assert _line(tmp_path, root, "computer.claude_code", "--claude-version", "2.1.296-beta.1")["status"] == "fine"


def test_a_project_folder_that_isnt_there_says_so(tmp_path):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path / "nowhere"), "HOME": str(tmp_path), "PATH": str(_bin(tmp_path))}
    p = subprocess.run([sys.executable, "-B", str(CLI), "doctor", "--json"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    lines = _lines(json.loads(p.stdout))
    assert lines["kit.profile"]["status"] == "gap" and "nowhere" in lines["kit.profile"]["message"]


def test_an_empty_folder_says_set_the_kit_up_first(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    r = _report(tmp_path, root)
    assert r["lines"][0]["id"] == "kit.profile"


# In-process: what the CLI can't reach without waiting ten seconds


def _inputs(tmp_path, **kw):
    from workflow import doctor
    from workflow.profile import Experience

    return doctor.Inputs(root=tmp_path, kit_root=KIT, profile=None, profile_error=None, experience=Experience(None, "unknown"), **kw)


def test_a_hung_command_is_stopped_with_what_it_started(tmp_path, monkeypatch):
    from workflow import doctor

    monkeypatch.setattr(doctor, "RUN_TIMEOUT", 1)
    path = _bin(tmp_path, python=None, claude=None)
    marker = tmp_path / "child.pid"
    _fake(path, "claude", f"{shutil.which('sleep')} 30 & echo $! > {marker}; wait")
    i = _inputs(tmp_path, environ={"PATH": str(path), "HOME": str(tmp_path)})
    ln = doctor.check_claude_code(i)[0]
    assert ln.status == "cant_check" and "timed out" in ln.message.developer
    child = int(marker.read_text())
    assert _gone(child), "the hung command's child is still running"


def _gone(pid, seconds=5.0):
    """The process has ended: no such pid, or a zombie nobody has reaped yet
    (a container's PID 1 may never reap orphans)."""
    import time

    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        try:
            if open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[0] == "Z":
                return True
        except (OSError, IndexError):
            pass
        time.sleep(0.1)
    return False


def test_a_check_that_raises_is_cant_check_without_the_checkouts_path(tmp_path, monkeypatch):
    from workflow import doctor

    def boom(i):
        raise PermissionError(f"[Errno 13] Permission denied: '{i.root}/secret/dir'")

    boom = doctor._check("The kit", "kit.boom")(boom)
    monkeypatch.setattr(doctor, "CHECKS", [boom])
    r = doctor.report(_inputs(tmp_path))
    (ln,) = r.lines
    assert (ln.id, ln.status) == ("kit.boom", "cant_check")
    assert str(tmp_path) not in ln.message.new and "secret/dir" in ln.message.new


# Round 3 of the review


def test_a_missing_project_folder_is_one_gap(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {vendor.PLUGIN_KEY: True}}))
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path / "nowhere"), "HOME": str(home), "PATH": str(_bin(tmp_path))}
    env.pop("WORKFLOW_EXPERIENCE", None)
    p = subprocess.run([sys.executable, "-B", str(CLI), "doctor", "--json"], cwd=tmp_path, env=env, capture_output=True, text=True)
    lines = _lines(json.loads(p.stdout))
    assert "kit.plugin" not in lines  # never "fine" for a folder that isn't there
    assert [i for i, ln in lines.items() if ln["status"] == "gap"] == ["kit.profile"]


def test_a_plugin_value_that_isnt_true_or_false_is_ignored(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {vendor.PLUGIN_KEY: True}}))
    root = _project(tmp_path, vendored=False, local={"enabledPlugins": {vendor.PLUGIN_KEY: "false"}})
    ln = _line(tmp_path, root, "kit.plugin", home=home, env={"WORKFLOW_EXPERIENCE": "developer"})
    assert ln["status"] == "fine" and "~/.claude/settings.json" in ln["message"]


def test_a_conflict_is_listed_once(tmp_path):
    root = _project(tmp_path, lock_files={".claude/skills/x/SKILL.md": "0" * 64})
    lock = json.loads((root / ".claude/workflow/lock.json").read_text())
    lock["conflicts"] = {".claude/skills/x/SKILL.md": "1" * 64}
    (root / ".claude/workflow/lock.json").write_text(json.dumps(lock))
    (root / ".claude/skills/x").mkdir(parents=True)
    (root / ".claude/skills/x/SKILL.md").write_text("mine")
    ln = _line(tmp_path, root, "kit.vendor")
    assert ln["status"] == "gap" and ln["message"].count(".claude/skills/x/SKILL.md") == 1 and "conflict" in ln["message"]


def test_odd_conflicts_in_the_lock_are_a_gap_not_a_kit_bug(tmp_path):
    root = _project(tmp_path)
    lock = json.loads((root / ".claude/workflow/lock.json").read_text())
    lock["conflicts"] = [1, "a"]
    (root / ".claude/workflow/lock.json").write_text(json.dumps(lock))
    ln = _line(tmp_path, root, "kit.vendor")
    assert ln["status"] == "gap" and "bug" not in ln["message"]


@pytest.mark.parametrize("dst", ["../outside.txt", "/etc/hostname"])
def test_a_lock_path_outside_the_project_is_named_not_read(tmp_path, dst):
    (tmp_path / "outside.txt").write_text("there")
    root = _project(tmp_path, lock_files={dst: "0" * 64})
    ln = _line(tmp_path, root, "kit.vendor")
    assert ln["status"] == "gap" and "outside the project" in ln["message"]


def test_a_symlinked_folder_in_the_copy_is_inside_the_project(tmp_path):
    shared = tmp_path / "shared/x"
    shared.mkdir(parents=True)
    (shared / "SKILL.md").write_text("kit's")
    import hashlib

    root = _project(tmp_path, lock_files={".claude/skills/x/SKILL.md": hashlib.sha256(b"kit's").hexdigest()})
    (root / ".claude/skills").symlink_to(tmp_path / "shared")
    assert _line(tmp_path, root, "kit.vendor")["status"] == "fine"


@pytest.mark.parametrize("slash", ["", "/"])
def test_another_kits_path_is_shown_from_home(tmp_path, slash):
    settings = vendor.merge_hooks({})
    settings["hooks"]["Stop"][0]["hooks"][0]["timeout"] = 99
    root = _project(tmp_path, settings=settings)
    home = tmp_path / "home"
    kit = home / "kit"
    shutil.copytree(KIT / "scripts", kit / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(KIT / "VERSION", kit / "VERSION")
    p = _doctor(tmp_path, root, "--json", cli=kit / "scripts/workflow.py", home=home,
                env={"WORKFLOW_EXPERIENCE": "developer", "HOME": str(home) + slash})
    msg = _lines(json.loads(p.stdout))["kit.hooks"]["message"]
    assert "~/kit" in msg and str(home) not in msg


def test_two_skipped_experience_values_are_spoken_of_as_two(tmp_path):
    root = _project(tmp_path)
    (root / ".workflow").mkdir()
    (root / ".workflow/experience").write_text("guru\n")
    ln = _line(tmp_path, root, "kit.experience", env={"WORKFLOW_EXPERIENCE": "expert"})
    assert "each should say" in ln["message"] and "remove them" in ln["fix"]


def test_claude_not_on_the_path_says_so(tmp_path):
    root = _project(tmp_path)
    ln = _line(tmp_path, root, "computer.claude_code", path=_bin(tmp_path, claude=None), env={"WORKFLOW_EXPERIENCE": "developer"})
    assert "isn't on the PATH" in ln["message"]


# The Correctness pass after round 3


def test_ctrl_c_stops_quietly_with_nothing_left_running(tmp_path):
    import signal
    import time

    root = _project(tmp_path)
    path = _bin(tmp_path, claude=None)
    marker = tmp_path / "child.pid"
    _fake(path, "claude", f"{shutil.which('sleep')} 30 & echo $! > {marker}; wait")
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), "HOME": str(tmp_path), "PATH": str(path)}
    p = subprocess.Popen([sys.executable, "-B", str(root / ".claude/workflow/bin/workflow.py"), "doctor"], cwd=root, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for _ in range(100):
        if marker.exists() and marker.read_text().strip():
            break
        time.sleep(0.1)
    p.send_signal(signal.SIGINT)
    out, err = p.communicate(timeout=20)
    assert p.returncode == 130 and "workflow doctor: stopped" in err and "Traceback" not in err
    assert _gone(int(marker.read_text()))


def test_a_missing_folder_under_home_is_shown_from_home(tmp_path):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path / "nowhere"), "HOME": str(tmp_path), "PATH": str(_bin(tmp_path))}
    p = subprocess.run([sys.executable, "-B", str(CLI), "doctor", "--json"], cwd=tmp_path, env=env, capture_output=True, text=True)
    msg = _lines(json.loads(p.stdout))["kit.profile"]["message"]
    assert "~/nowhere" in msg and str(tmp_path) not in msg
