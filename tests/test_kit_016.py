"""Kit 0.1.6: the docs audit's fixes."""

import json
import re
from pathlib import Path

from workflow.profile import check, parse

KIT = Path(__file__).resolve().parents[1]


def _text(rel: str) -> str:
    return (KIT / rel).read_text(encoding="utf-8")


def test_profile_check_warns_setup_without_check(tmp_path):
    prof = parse({"project": {"name": "d", "repo": "a/d"}, "commands": {"setup": "npm ci"}}, tmp_path)
    assert any(x.startswith("commands.setup is set but commands.setup_check is empty") for x in check(prof))
    prof = parse({"project": {"name": "d", "repo": "a/d"}, "commands": {"setup": "npm ci", "setup_check": "test -d node_modules"}}, tmp_path)
    assert not any(x.startswith("commands.setup is set") for x in check(prof))


def test_profile_check_warns_protected_paths_replacing_defaults(tmp_path):
    prof = parse({"project": {"name": "d", "repo": "a/d"}, "guard": {"protected_paths": ["infra/**"]}}, tmp_path)
    w = check(prof)
    assert any("guard.protected_paths leaves out '.claude/**'" in x for x in w)
    assert any("guard.protected_paths leaves out '.github/workflows/**'" in x for x in w)
    prof = parse({"project": {"name": "d", "repo": "a/d"}}, tmp_path)
    assert not any(x.startswith("guard.protected_paths") for x in check(prof))


def test_vendored_copy_carries_the_kits_licence():
    from workflow import vendor
    files = vendor.plan(KIT, None)
    assert files[".claude/workflow/LICENSE"] == KIT / "LICENSE"


def test_readme_names_no_skill_the_pin_dropped():
    assert "resolving-merge-conflicts" not in _text("README.md")
