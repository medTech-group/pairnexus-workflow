"""#112: the profile's `[previews]` section (`provider`, `on`, `access`), as
`profile check` judges it and the profile loader reads it (#41's seam 2)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import KIT
from test_hooks_cli import CLI
from workflow import profile as profile_mod

PROFILE_HEAD = '[project]\nname = "demo"\nrepo = "acme/demo"\n'
SENSITIVE = '\n[sensitive]\ndescription = "patients"\npatterns = ["patient_id"]\n'


def _write_profile(root, extra=""):
    (root / ".claude/workflow").mkdir(parents=True, exist_ok=True)
    (root / ".claude/workflow/profile.toml").write_text(PROFILE_HEAD + extra)


def _check(root):
    e = {k: v for k, v in os.environ.items() if k != "WORKFLOW_EXPERIENCE"}
    e["CLAUDE_PROJECT_DIR"] = str(root)
    return subprocess.run([sys.executable, str(CLI), "profile", "check"], cwd=root, env=e, capture_output=True, text=True)


def _previews_toml(on="true", access="true", provider='"cloudflare"'):
    return f'\n[previews]\nprovider = {provider}\non = {on}\naccess = {access}\n'


# accepted, and readable


@pytest.mark.parametrize("on, access", [("true", "true"), ("true", "false"), ("false", "false"), ("false", "true")])
def test_a_previews_section_passes_and_the_loader_reads_it(tmp_path, on, access):
    _write_profile(tmp_path, _previews_toml(on, access))
    p = _check(tmp_path)
    assert p.returncode == 0, p.stderr
    want = {"provider": "cloudflare", "on": on == "true", "access": access == "true"}
    assert json.loads(p.stdout)["previews"] == want
    prof = profile_mod.load(tmp_path)
    assert (prof.previews.provider, prof.previews.on, prof.previews.access) == tuple(want.values())


def test_no_previews_section_passes_and_reads_as_previews_off(tmp_path):
    _write_profile(tmp_path)
    p = _check(tmp_path)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["previews"]["on"] is False
    prof = profile_mod.load(tmp_path)
    assert prof.previews.on is False and prof.previews.access is False


def test_an_empty_previews_section_reads_as_previews_off(tmp_path):
    _write_profile(tmp_path, "\n[previews]\n")
    p = _check(tmp_path)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["previews"] == {"provider": "cloudflare", "on": False, "access": False}


def test_a_section_without_provider_reads_as_cloudflare(tmp_path):
    _write_profile(tmp_path, "\n[previews]\non = true\naccess = true\n")
    p = _check(tmp_path)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["previews"]["provider"] == "cloudflare"


# refused


@pytest.mark.parametrize("typo", ["enabled", "On", "acess", "url"])
def test_an_unknown_key_fails_naming_it(tmp_path, typo):
    _write_profile(tmp_path, _previews_toml() + f"{typo} = true\n")
    p = _check(tmp_path)
    assert p.returncode == 1
    assert "[previews]" in p.stderr and repr(typo) in p.stderr


@pytest.mark.parametrize("provider", ['"vercel"', '"Cloudflare"', '""', "true", '["cloudflare"]'])
def test_a_provider_other_than_cloudflare_fails(tmp_path, provider):
    _write_profile(tmp_path, _previews_toml(provider=provider))
    p = _check(tmp_path)
    assert p.returncode == 1
    assert "previews.provider" in p.stderr and '"cloudflare"' in p.stderr


@pytest.mark.parametrize("key", ["on", "access"])
@pytest.mark.parametrize("value, shown", [('"true"', "'true'"), ("1", "1"), ('"yes"', "'yes'"), ("[]", "[]")])
def test_on_and_access_must_be_true_or_false(tmp_path, key, value, shown):
    _write_profile(tmp_path, f"\n[previews]\n{key} = {value}\n")
    p = _check(tmp_path)
    assert p.returncode == 1
    assert f"previews.{key}" in p.stderr and "true or false" in p.stderr
    assert f"not {shown}" in p.stderr


def test_a_long_bad_provider_is_cut_short(tmp_path):
    _write_profile(tmp_path, _previews_toml(provider=f'"{"x" * 5000}"'))
    p = _check(tmp_path)
    assert p.returncode == 1 and "previews.provider" in p.stderr and len(p.stderr) < 300


# sensitive projects: Access, or no previews


@pytest.mark.parametrize("access", ["false", None])
def test_on_without_access_fails_in_a_sensitive_profile(tmp_path, access):
    section = "\n[previews]\non = true\n" + (f"access = {access}\n" if access else "")
    _write_profile(tmp_path, SENSITIVE + section)
    p = _check(tmp_path)
    assert p.returncode == 1
    assert "previews" in p.stderr and "Access" in p.stderr and "sensitive" in p.stderr


def test_on_without_access_passes_in_a_profile_without_sensitive_patterns(tmp_path):
    _write_profile(tmp_path, '\n[sensitive]\ndescription = "nothing"\npatterns = []\n' + _previews_toml(access="false"))
    p = _check(tmp_path)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["previews"]["on"] is True


@pytest.mark.parametrize("on, access", [("true", "true"), ("false", "false")])
def test_a_sensitive_profile_passes_with_access_or_previews_off(tmp_path, on, access):
    _write_profile(tmp_path, SENSITIVE + _previews_toml(on, access))
    p = _check(tmp_path)
    assert p.returncode == 0, p.stderr


# what ships


def test_the_starter_ships_no_previews_section_but_a_commented_example():
    text = (KIT / "templates/profile.toml").read_text()
    assert not any(line.strip() == "[previews]" for line in text.splitlines())
    assert "# [previews]" in text


def test_the_commented_example_passes_when_uncommented(tmp_path):
    text = (KIT / "templates/profile.toml").read_text().splitlines()
    start = text.index("# [previews]")
    block = []
    for line in text[start:]:
        if not line.startswith("#"):
            break
        block.append(line[1:].lstrip())
    example = "\n".join(l for l in block if "=" in l or l.startswith("["))
    _write_profile(tmp_path, "\n" + example + "\n")
    p = _check(tmp_path)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["previews"]["provider"] == "cloudflare"


def test_profile_md_documents_the_three_keys():
    text = (KIT / "docs/profile.md").read_text()
    assert "[previews]" in text
    start = text.index("## `[previews]`")
    end = text.find("\n## ", start + 1)
    section = text[start:end if end != -1 else len(text)]
    for key in ("`provider`", "`on`", "`access`"):
        assert key in section, key
