import json
from pathlib import Path

import pytest
from conftest import git

from workflow import evidence, vendor
from workflow.profile import parse

KIT = Path(__file__).resolve().parents[1]


@pytest.fixture
def mattpocock(tmp_path):
    mp = tmp_path / "mp"
    (mp / ".claude-plugin").mkdir(parents=True)
    (mp / "skills/engineering/tdd").mkdir(parents=True)
    (mp / "skills/engineering/tdd/SKILL.md").write_text("---\nname: tdd\n---\nTDD")
    (mp / "skills/engineering/next").mkdir(parents=True)
    (mp / "skills/engineering/next/SKILL.md").write_text("upstream next")
    (mp / ".claude-plugin/plugin.json").write_text(json.dumps({"name": "mattpocock-skills", "skills": ["./skills/engineering/tdd", "./skills/engineering/next"]}))
    (mp / "LICENSE").write_text("MIT")
    return mp


def test_install_verify_update(tmp_path, mattpocock):
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude/settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "mine.sh"}]}]}}))
    r = vendor.install(KIT, proj, mattpocock)
    assert not r["conflicts"]
    assert (proj / ".claude/skills/tdd/SKILL.md").read_text().endswith("TDD")
    assert "upstream" not in (proj / ".claude/skills/next/SKILL.md").read_text()  # the kit's own wins
    assert (proj / ".claude/workflow/bin/workflow.py").exists()
    assert (proj / ".claude/workflow/flow.md").exists()
    assert (proj / ".claude/skills/LICENSE-mattpocock-skills").read_text() == "MIT"
    s = json.loads((proj / ".claude/settings.json").read_text())
    assert any(h["command"] == "mine.sh" for e in s["hooks"]["PreToolUse"] for h in e["hooks"])
    assert sum(vendor.HOOK_TAG in h["command"] for e in s["hooks"]["PreToolUse"] for h in e["hooks"]) == 1
    v = vendor.verify(proj)
    assert v["hooks_ok"] and not v["missing"] and not v["changed"]

    with pytest.raises(vendor.VendorError, match="already vendored"):
        vendor.install(KIT, proj, mattpocock)

    # A local edit is kept on update; the kit's version lands beside it.
    flow = proj / ".claude/workflow/flow.md"
    flow.write_text("local edit")
    assert vendor.verify(proj)["changed"] == [".claude/workflow/flow.md"]
    r = vendor.install(KIT, proj, mattpocock, update=True)
    assert r["conflicts"] == [".claude/workflow/flow.md"]
    assert flow.read_text() == "local edit"
    assert (proj / ".claude/workflow/flow.md.new").exists()
    s = json.loads((proj / ".claude/settings.json").read_text())
    assert sum(vendor.HOOK_TAG in h["command"] for e in s["hooks"]["PreToolUse"] for h in e["hooks"]) == 1


def test_one_mode_per_project(tmp_path, mattpocock):
    proj = tmp_path / "p"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {vendor.PLUGIN_KEY: True}}))
    with pytest.raises(vendor.VendorError, match="one mode"):
        vendor.install(KIT, proj, mattpocock)


def test_existing_files_need_adopt(tmp_path, mattpocock):
    proj = tmp_path / "p"
    (proj / ".claude/skills/tdd").mkdir(parents=True)
    (proj / ".claude/skills/tdd/SKILL.md").write_text("hand-vendored, older")
    with pytest.raises(vendor.VendorError, match="--adopt"):
        vendor.install(KIT, proj, mattpocock)
    r = vendor.install(KIT, proj, mattpocock, adopt=True)
    assert ".claude/skills/tdd/SKILL.md" in r["adopted"]


def _suite_repo(tmp_path, results):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@e")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "tests").mkdir()
    for i, r in enumerate(results):
        (tmp_path / f"tests/test_{i}.txt").write_text(r)
    (tmp_path / "run_tests.py").write_text(
        "import sys\np=f=0\nfor a in sys.argv[1:]:\n    r=open(a).read().strip()\n    p+=r=='pass'; f+=r=='fail'\n"
        "print(f'{p} passed' + (f', {f} failed' if f else ''))\nsys.exit(1 if f else 0)\n"
    )
    (tmp_path / ".gitignore").write_text(".workflow/\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "x")
    prof = parse(
        {"project": {"name": "d", "repo": "a/d"}, "commands": {"suite": [{"name": "unit", "run": "python3 run_tests.py {files}", "files": "tests/test_*.txt", "group": 2}]}},
        tmp_path,
    )
    return prof


def test_evidence_shards_resume_and_report(tmp_path):
    prof = _suite_repo(tmp_path, ["pass", "pass", "pass"])
    sha, res = evidence.collect(prof, tmp_path)
    assert len(res) == 2 and sum(r.passed for r in res) == 3
    ok, md = evidence.report(sha, prof, res, base_count=3)
    assert ok and sha in md and "3 passed" in md
    # Resume: finished shards aren't run again.
    (tmp_path / "tests/test_0.txt").write_text("fail")  # dirty tree
    with pytest.raises(evidence.EvidenceError, match="uncommitted"):
        evidence.collect(prof, tmp_path)
    git(tmp_path, "checkout", "--", ".")
    sha2, res2 = evidence.collect(prof, tmp_path)
    assert sha2 == sha and [r.seconds for r in res2] == [r.seconds for r in res]
    ok, md = evidence.report(sha, prof, res2, base_count=5)
    assert not ok and "Fewer tests than the base branch" in md


def test_evidence_failure(tmp_path):
    prof = _suite_repo(tmp_path, ["pass", "fail"])
    sha, res = evidence.collect(prof, tmp_path)
    ok, md = evidence.report(sha, prof, res)
    assert not ok and "FAILED" in md and "1 failed" in md
