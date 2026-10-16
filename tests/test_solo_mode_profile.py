"""#43: solo mode (`project.ruleset`) and experience (`project.experience`) in
the profile, the shared experience resolution, and `workflow status`."""

import json
import os
import subprocess
import sys

import pytest

from conftest import KIT
from test_hooks_cli import CLI
from workflow import profile as profile_mod

PROFILE_HEAD = '[project]\nname = "demo"\nrepo = "acme/demo"\n'


def _write_profile(root, extra=""):
    (root / ".claude/workflow").mkdir(parents=True, exist_ok=True)
    (root / ".claude/workflow/profile.toml").write_text(PROFILE_HEAD + extra)


def _cli(root, *args, env=None):
    e = {k: v for k, v in os.environ.items() if k != "WORKFLOW_EXPERIENCE"}
    e.update({"CLAUDE_PROJECT_DIR": str(root), **(env or {})})
    return subprocess.run([sys.executable, str(CLI), *args], cwd=root, env=e, capture_output=True, text=True)


# profile check: ruleset


@pytest.mark.parametrize("line, want", [("ruleset = true\n", True), ("ruleset = false\n", False), ("", None)])
def test_profile_check_accepts_each_ruleset_value(tmp_path, line, want):
    _write_profile(tmp_path, line)
    p = _cli(tmp_path, "profile", "check")
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["ruleset"] is want


@pytest.mark.parametrize("line", ['ruleset = "false"\n', "ruleset = 0\n", 'ruleset = "yes"\n', "ruleset = []\n"])
def test_profile_check_refuses_any_other_ruleset(tmp_path, line):
    _write_profile(tmp_path, line)
    p = _cli(tmp_path, "profile", "check")
    assert p.returncode == 1
    assert "project.ruleset" in p.stderr and "true or false" in p.stderr


# profile check: experience


@pytest.mark.parametrize("line, want", [('experience = "new"\n', "new"), ('experience = "developer"\n', "developer"), ("", None)])
def test_profile_check_accepts_each_experience_value(tmp_path, line, want):
    _write_profile(tmp_path, line)
    p = _cli(tmp_path, "profile", "check")
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["experience"] == want


@pytest.mark.parametrize("line", ['experience = "expert"\n', 'experience = "New"\n', 'experience = ""\n', "experience = true\n"])
def test_profile_check_refuses_any_other_experience(tmp_path, line):
    # (A long value is cut short in the message: see the next test.)
    _write_profile(tmp_path, line)
    p = _cli(tmp_path, "profile", "check")
    assert p.returncode == 1
    assert "project.experience" in p.stderr and '"new" or "developer"' in p.stderr


def test_profile_check_cuts_a_long_bad_value_short(tmp_path):
    _write_profile(tmp_path, f'experience = "{"x" * 5000}"\n')
    p = _cli(tmp_path, "profile", "check")
    assert p.returncode == 1 and "project.experience" in p.stderr and len(p.stderr) < 300


# status: solo mode


@pytest.mark.parametrize(
    "line, text, value",
    [("ruleset = false\n", "Solo mode: yes", True), ("ruleset = true\n", "Solo mode: no", False), ("", "Solo mode: not set (as before)", None)],
)
def test_status_reports_solo_mode(repo, line, text, value):
    _write_profile(repo, line)
    p = _cli(repo, "status")
    assert p.returncode == 0, p.stderr
    assert text in p.stdout.splitlines()
    p = _cli(repo, "status", "--json")
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["solo_mode"] is value


def test_status_without_a_profile_reports_solo_mode_not_set(tmp_path):
    p = _cli(tmp_path, "status", "--json")
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert out["solo_mode"] is None and out["experience"]["source"] == "unknown"


# status: experience and its source


def _experience(root, env=None):
    p = _cli(root, "status", "--json", env=env)
    assert p.returncode == 0, p.stderr
    t = _cli(root, "status", env=env)
    assert t.returncode == 0, t.stderr
    return json.loads(p.stdout)["experience"], t.stdout


def _local(root, text):
    (root / ".workflow").mkdir(exist_ok=True)
    (root / ".workflow/experience").write_text(text)


def test_status_experience_from_the_environment_wins_over_file_and_profile(repo):
    _write_profile(repo, 'experience = "new"\n')
    _local(repo, "new\n")
    exp, text = _experience(repo, {"WORKFLOW_EXPERIENCE": "developer"})
    assert (exp["level"], exp["source"], exp["warnings"]) == ("developer", "environment", [])
    assert "Experience: developer (from the environment, WORKFLOW_EXPERIENCE)" in text


def test_status_experience_from_the_local_file_wins_over_the_profile(repo):
    _write_profile(repo, 'experience = "new"\n')
    _local(repo, "developer\n")
    exp, text = _experience(repo)
    assert (exp["level"], exp["source"]) == ("developer", "local file")
    assert "Experience: developer (from the local file, .workflow/experience)" in text


def test_status_experience_from_the_profile(repo):
    _write_profile(repo, 'experience = "developer"\n')
    exp, text = _experience(repo)
    assert (exp["level"], exp["source"]) == ("developer", "profile")
    assert "Experience: developer (from the profile, project.experience)" in text


def test_status_experience_unknown_counts_as_new(repo):
    exp, text = _experience(repo)
    assert (exp["level"], exp["source"], exp["wording_level"]) == (None, "unknown", "new")
    assert "Experience: unknown (worded as new to building)" in text


def test_status_skips_an_unrecognised_environment_value_with_a_warning(repo):
    _local(repo, "developer\n")
    exp, text = _experience(repo, {"WORKFLOW_EXPERIENCE": "expert"})
    assert (exp["level"], exp["source"]) == ("developer", "local file")
    assert len(exp["warnings"]) == 1 and "WORKFLOW_EXPERIENCE" in exp["warnings"][0]
    assert "expert" not in exp["warnings"][0]  # a value is never repeated
    assert "warning: " + exp["warnings"][0] in text


def test_status_skips_an_unrecognised_local_file_with_a_warning(repo):
    _write_profile(repo, 'experience = "developer"\n')
    _local(repo, "guru\n")
    exp, text = _experience(repo)
    assert (exp["level"], exp["source"]) == ("developer", "profile")
    assert len(exp["warnings"]) == 1 and ".workflow/experience" in exp["warnings"][0]
    assert "guru" not in exp["warnings"][0]
    assert "warning: " + exp["warnings"][0] in text


def test_status_skips_both_bad_values_to_unknown(repo):
    _local(repo, "")
    exp, _ = _experience(repo, {"WORKFLOW_EXPERIENCE": "lots"})
    assert (exp["level"], exp["source"], exp["wording_level"]) == (None, "unknown", "new")
    assert len(exp["warnings"]) == 2


# the shared resolution function, as the guard will call it


def test_resolution_reads_a_value_with_spaces_and_case_around_it(tmp_path):
    _local(tmp_path, "  Developer  \n")
    exp = profile_mod.resolve_experience(tmp_path, environ={})
    assert (exp.level, exp.source) == ("developer", "local file")
    exp = profile_mod.resolve_experience(tmp_path, environ={"WORKFLOW_EXPERIENCE": " NEW "})
    assert (exp.level, exp.source) == ("new", "environment")


def test_resolution_takes_the_profile_value_it_is_given(tmp_path):
    exp = profile_mod.resolve_experience(tmp_path, "developer", environ={})
    assert (exp.level, exp.source, exp.wording_level) == ("developer", "profile", "developer")


def test_an_empty_environment_value_is_as_if_unset(tmp_path):
    exp = profile_mod.resolve_experience(tmp_path, "new", environ={"WORKFLOW_EXPERIENCE": ""})
    assert (exp.level, exp.source, exp.warnings) == ("new", "profile", [])


@pytest.mark.parametrize(
    "setup, warned",
    [
        (lambda root: (root / ".workflow").mkdir(), 0),  # no file
        (lambda root: (root / ".workflow/experience").mkdir(parents=True), 1),  # a directory: a mistake
        (lambda root: (root / ".workflow").write_text("a file, not a directory"), 0),
        (lambda root: _local_bytes(root, b"\xff\xfe\x00bad"), 1),  # not UTF-8
        (lambda root: _local_bytes(root, b"developer\nnew\n"), 1),  # more than one line
        (lambda root: _local_bytes(root, b"x" * 100_000), 1),  # far too long
        (lambda root: _local_bytes(root, b"   \n"), 1),  # empty
    ],
)
def test_resolution_never_raises_on_a_bad_local_file(tmp_path, setup, warned):
    setup(tmp_path)
    exp = profile_mod.resolve_experience(tmp_path, "developer", environ={})
    assert (exp.level, exp.source) == ("developer", "profile")
    assert len(exp.warnings) == warned


def test_a_byte_order_mark_is_read_past(tmp_path):
    _local_bytes(tmp_path, "\ufeffdeveloper\r\n".encode())
    exp = profile_mod.resolve_experience(tmp_path, environ={})
    assert (exp.level, exp.source, exp.warnings) == ("developer", "local file", [])


def test_a_skipped_file_s_text_is_never_shown(tmp_path):
    # The path may be a symlink to anything, a secret among them.
    secret = tmp_path / "secret.txt"
    secret.write_text("API_KEY=made-up-value\n")
    (tmp_path / ".workflow").mkdir()
    (tmp_path / ".workflow/experience").symlink_to(secret)
    exp = profile_mod.resolve_experience(tmp_path, environ={"WORKFLOW_EXPERIENCE": "TOKEN=also-made-up"})
    assert exp.source == "unknown" and len(exp.warnings) == 2
    assert not any("made-up" in w or "API_KEY" in w or "TOKEN" in w for w in exp.warnings)


def _local_bytes(root, data):
    (root / ".workflow").mkdir(exist_ok=True)
    (root / ".workflow/experience").write_bytes(data)


@pytest.mark.parametrize("bad", [None, 3, "guru", ["new"], {"a": 1}])
def test_resolution_never_raises_on_a_bad_profile_value(tmp_path, bad):
    exp = profile_mod.resolve_experience(tmp_path, bad, environ={})
    assert exp.source == "unknown" and exp.wording_level == "new"


def test_resolution_never_raises_without_a_root():
    exp = profile_mod.resolve_experience(None, None, environ={"WORKFLOW_EXPERIENCE": "developer"})
    assert (exp.level, exp.source) == ("developer", "environment")
    exp = profile_mod.resolve_experience(None, None, environ={})
    assert exp.source == "unknown"


def test_resolution_reads_the_real_environment_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKFLOW_EXPERIENCE", "developer")
    assert profile_mod.resolve_experience(tmp_path).source == "environment"


def test_the_local_file_is_not_tracked():
    # The person's level never lands in the repository's history.
    ignored = (KIT / ".gitignore").read_text().split()
    assert ".workflow/" in ignored


# docs


def test_the_template_and_the_profile_doc_describe_both_settings():
    template = (KIT / "templates/profile.toml").read_text()
    doc = (KIT / "docs/profile.md").read_text()
    # A plain line #33's shell wrapper can read without TOML.
    assert any(line in ("# ruleset = false", "# ruleset = true") for line in template.splitlines())
    assert "experience" in template
    for word in ("`ruleset`", "`experience`", "solo mode", "WORKFLOW_EXPERIENCE", ".workflow/experience", "profile check"):
        assert word in doc, word


def test_the_template_still_parses():
    import tomllib

    data = tomllib.loads((KIT / "templates/profile.toml").read_text())
    p = profile_mod.parse(data, KIT)
    # Left out until set-up writes it, so a project set up before set-up
    # reads its rulesets doesn't land in solo mode with main protected.
    assert p.ruleset is None and p.experience == ""
