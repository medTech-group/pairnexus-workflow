import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import git

from workflow import evidence, vendor
from workflow.profile import ProfileError, parse

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"


def _git_repo(path: Path) -> Path:
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", "t@e")
    git(path, "config", "user.name", "t")
    git(path, "add", ".")
    git(path, "commit", "-qm", "x")
    return path


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
    return _git_repo(mp)


@pytest.fixture
def kit(tmp_path, mattpocock):
    """A copy of the kit the test may change, pinned at the fixture's mattpocock SHA."""
    k = tmp_path / "kit"
    for d in ("skills", "agents", "scripts", "docs", "templates", ".claude-plugin"):
        shutil.copytree(KIT / d, k / d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy(KIT / "VERSION", k / "VERSION")
    mf = k / ".claude-plugin/marketplace.json"
    data = json.loads(mf.read_text())
    for p in data["plugins"]:
        if p["name"] == "mattpocock-skills":
            p["source"]["sha"] = git(mattpocock, "rev-parse", "HEAD").strip()
    mf.write_text(json.dumps(data))
    return k


@pytest.fixture
def proj(tmp_path):
    p = tmp_path / "proj"
    (p / ".claude").mkdir(parents=True)
    return p


def _kit_hooks(s):
    return [h for ev in s["hooks"].values() for e in ev for h in e["hooks"] if vendor.HOOK_TAG in h["command"]]


def test_install_verify_update(tmp_path, mattpocock, kit, proj):
    (proj / ".claude/settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "mine.sh"}]}]}}))
    r = vendor.install(kit, proj, mattpocock)
    assert not r["conflicts"] and not r["warnings"]
    assert (proj / ".claude/skills/tdd/SKILL.md").read_text().endswith("TDD")
    assert "upstream" not in (proj / ".claude/skills/next/SKILL.md").read_text()  # the kit's own wins
    assert (proj / ".claude/workflow/bin/workflow.py").exists()
    assert (proj / ".claude/workflow/flow.md").exists()
    assert not (proj / ".claude/workflow/docs/proposal.md").exists()
    assert (proj / ".claude/skills/LICENSE-mattpocock-skills").read_text() == "MIT"
    s = json.loads((proj / ".claude/settings.json").read_text())
    assert any(h["command"] == "mine.sh" for e in s["hooks"]["PreToolUse"] for h in e["hooks"])
    assert sum(vendor.HOOK_TAG in h["command"] for e in s["hooks"]["PreToolUse"] for h in e["hooks"]) == 1
    v = vendor.verify(proj)
    assert v["hooks_ok"] and not v["missing"] and not v["changed"]

    with pytest.raises(vendor.VendorError, match="already vendored"):
        vendor.install(kit, proj, mattpocock)

    r = vendor.install(kit, proj, mattpocock, update=True)
    assert not r["written"] and not r["conflicts"]
    s = json.loads((proj / ".claude/settings.json").read_text())
    assert sum(vendor.HOOK_TAG in h["command"] for e in s["hooks"]["PreToolUse"] for h in e["hooks"]) == 1


def test_no_false_conflict_then_conflict_then_resolve(mattpocock, kit, proj):
    vendor.install(kit, proj, mattpocock)
    flow = proj / ".claude/workflow/flow.md"
    new = proj / ".claude/workflow/flow.md.new"
    flow.write_text("local edit")
    assert vendor.verify(proj)["changed"] == [".claude/workflow/flow.md"]

    # The kit didn't change flow.md: the project's edit stays, silently.
    r = vendor.install(kit, proj, mattpocock, update=True)
    assert r["conflicts"] == [] and ".claude/workflow/flow.md" in r["kept"]
    assert flow.read_text() == "local edit" and not new.exists()

    # The kit changes it too: a conflict, with the kit's version beside it.
    (kit / "docs/flow.md").write_text("kit v2")
    r = vendor.install(kit, proj, mattpocock, update=True)
    assert r["conflicts"] == [".claude/workflow/flow.md"]
    assert flow.read_text() == "local edit" and new.read_text() == "kit v2"
    assert vendor.verify(proj)["conflicts"] == [".claude/workflow/flow.md"]

    # Merged by hand and resolved: no .new, verify clean, and the same kit leaves the merge alone.
    flow.write_text("local edit + kit v2")
    assert vendor.resolve(proj, ".claude/workflow/flow.md") == {"resolved": ".claude/workflow/flow.md"}
    assert not new.exists()
    v = vendor.verify(proj)
    assert not v["changed"] and not v["conflicts"]
    r = vendor.install(kit, proj, mattpocock, update=True)
    assert not r["conflicts"] and flow.read_text() == "local edit + kit v2" and not new.exists()

    # A later kit change conflicts again rather than overwriting the merge.
    (kit / "docs/flow.md").write_text("kit v3")
    r = vendor.install(kit, proj, mattpocock, update=True)
    assert r["conflicts"] == [".claude/workflow/flow.md"] and flow.read_text() == "local edit + kit v2"

    with pytest.raises(vendor.VendorError, match="no conflict"):
        vendor.resolve(proj, ".claude/workflow/bin/workflow.py")


def test_unchanged_project_file_takes_the_kit_update(mattpocock, kit, proj):
    vendor.install(kit, proj, mattpocock)
    (kit / "docs/flow.md").write_text("kit v2")
    r = vendor.install(kit, proj, mattpocock, update=True)
    assert ".claude/workflow/flow.md" in r["written"]
    assert (proj / ".claude/workflow/flow.md").read_text() == "kit v2"


def test_orphans_are_kept_and_recognised_later(mattpocock, kit, proj):
    vendor.install(kit, proj, mattpocock)
    edited = proj / ".claude/workflow/docs/charter.md"
    plain = proj / ".claude/workflow/docs/install.md"
    original = (kit / "docs/charter.md").read_text()
    edited.write_text("the project's notes")
    (kit / "docs/charter.md").unlink()
    (kit / "docs/install.md").unlink()

    r = vendor.install(kit, proj, mattpocock, update=True)
    assert r["orphaned"] == [".claude/workflow/docs/charter.md"]
    assert r["removed"] == [".claude/workflow/docs/install.md"]  # unedited: removed
    assert edited.read_text() == "the project's notes" and not plain.exists()
    lock = vendor.read_lock(proj)
    assert ".claude/workflow/docs/charter.md" in lock["orphaned"]

    # The kit ships it again, unchanged: the project's file is the kit's, edited; nothing to merge.
    (kit / "docs/charter.md").write_text(original)
    r = vendor.install(kit, proj, mattpocock, update=True)
    assert ".claude/workflow/docs/charter.md" in r["kept"] and not r["conflicts"]
    assert ".claude/workflow/docs/charter.md" not in vendor.read_lock(proj)["orphaned"]

    # Dropped and shipped again changed: a conflict, never "isn't the kit's".
    (kit / "docs/charter.md").unlink()
    vendor.install(kit, proj, mattpocock, update=True)
    (kit / "docs/charter.md").write_text("changed in the kit")
    r = vendor.install(kit, proj, mattpocock, update=True)
    assert r["conflicts"] == [".claude/workflow/docs/charter.md"]
    assert edited.read_text() == "the project's notes"


def test_clashes_are_all_listed_and_nothing_is_written(mattpocock, kit, proj):
    (proj / ".claude/skills/tdd").mkdir(parents=True)
    (proj / ".claude/skills/tdd/SKILL.md").write_text("the project's own tdd")
    (proj / ".claude/skills/tdd/notes.md").write_text("x")
    (proj / ".claude/agents").mkdir()
    (proj / ".claude/agents/correctness-reviewer.md").write_text("mine")
    (proj / ".claude/skills/next").mkdir()
    (proj / ".claude/skills/next/SKILL.md").write_text("mine too")
    with pytest.raises(vendor.VendorError) as e:
        vendor.install(kit, proj, mattpocock)
    msg = str(e.value)
    assert "a skill of the same name already exists in .claude/skills/tdd/: rename the project's skill directory, or pass --adopt to replace it" in msg
    assert ".claude/skills/next/" in msg and ".claude/agents/correctness-reviewer.md already exists" in msg
    assert msg.count("a skill of the same name") == 2  # grouped per skill directory
    assert not (proj / vendor.LOCK).exists() and not (proj / vendor.SETTINGS).exists()
    assert not (proj / ".claude/workflow").exists() and not (proj / ".gitignore").exists()


def test_adopt_names_what_it_replaces(mattpocock, kit, proj):
    (proj / ".claude/skills/tdd").mkdir(parents=True)
    (proj / ".claude/skills/tdd/SKILL.md").write_text("hand-vendored, older")
    r = vendor.install(kit, proj, mattpocock, adopt=True)
    assert r["adopted"] == [".claude/skills/tdd/SKILL.md"]
    assert ".claude/skills/tdd/SKILL.md" not in r["written"]


def test_cli_prints_paths_in_full(mattpocock, kit, proj):
    (proj / ".claude/skills/tdd").mkdir(parents=True)
    (proj / ".claude/skills/tdd/SKILL.md").write_text("hand-vendored, older")
    args = [sys.executable, str(CLI), "vendor", "install", "--kit", str(kit), "--mattpocock", str(mattpocock), "--project", str(proj), "--adopt"]
    p = subprocess.run(args, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert out["adopted"] == [".claude/skills/tdd/SKILL.md"] and isinstance(out["written"], int)
    (kit / "docs/flow.md").write_text("kit v2")
    (proj / ".claude/workflow/flow.md").write_text("mine")
    (kit / "docs/install.md").unlink()
    args[3] = "update"
    out = json.loads(subprocess.run(args[:-1], capture_output=True, text=True).stdout)
    assert out["conflicts"] == [".claude/workflow/flow.md"] and out["removed"] == [".claude/workflow/docs/install.md"]
    p = subprocess.run([sys.executable, str(CLI), "vendor", "resolve", ".claude/workflow/flow.md", "--project", str(proj)], capture_output=True, text=True)
    assert p.returncode == 0 and not (proj / ".claude/workflow/flow.md.new").exists()


def test_update_keeps_mattpocock_skills_and_checks_the_pin(tmp_path, mattpocock, kit, proj):
    vendor.install(kit, proj, mattpocock)
    with pytest.raises(vendor.VendorError, match="pass --mattpocock <checkout at SHA>"):
        vendor.install(kit, proj, None, update=True)
    assert (proj / ".claude/skills/tdd/SKILL.md").exists()

    (mattpocock / "README.md").write_text("newer")
    git(mattpocock, "add", ".")
    git(mattpocock, "commit", "-qm", "newer")
    r = vendor.install(kit, proj, mattpocock, update=True)
    assert r["warnings"] and "pins" in r["warnings"][0]
    with pytest.raises(vendor.VendorError, match="--strict-pin"):
        vendor.install(kit, proj, mattpocock, update=True, strict_pin=True)
    assert vendor.pinned_mattpocock_sha(KIT)  # the real kit pins one


def test_one_mode_per_project(mattpocock, kit, proj):
    (proj / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {vendor.PLUGIN_KEY: True}}))
    with pytest.raises(vendor.VendorError, match="one mode"):
        vendor.install(kit, proj, mattpocock)
    (proj / ".claude/settings.json").write_text("{}")
    (proj / ".claude/settings.local.json").write_text(json.dumps({"enabledPlugins": {vendor.PLUGIN_KEY: True}}))
    with pytest.raises(vendor.VendorError, match="settings.local.json enables"):
        vendor.install(kit, proj, mattpocock)


def test_merge_hooks_keeps_the_projects_hooks_in_shared_entries():
    kit_cmd = vendor.hook_command("guard")
    settings = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "mine.sh"}, {"type": "command", "command": kit_cmd}]},
                {"matcher": "Edit", "hooks": [{"type": "command", "command": 'python3 "$CLAUDE_PROJECT_DIR/.claude/workflow/bin/workflow.py" hook guard'}]},
            ],
            "Stop": [{"hooks": [{"type": "command", "command": "stop.sh"}]}],
        },
        "permissions": {"allow": ["Bash(ls)"]},
    }
    out = vendor.merge_hooks(settings)
    pre = out["hooks"]["PreToolUse"]
    assert pre[0] == {"matcher": "Bash", "hooks": [{"type": "command", "command": "mine.sh"}]}
    assert all(e.get("matcher") != "Edit" for e in pre)  # emptied: dropped
    assert pre[-1]["matcher"] == "Bash|Edit|Write|MultiEdit|NotebookEdit|mcp__.*[Gg]it[Hh]ub.*"
    assert len(_kit_hooks(out)) == 4 and out["permissions"] == settings["permissions"]
    assert vendor.merge_hooks(out) == out  # idempotent: the tag still finds the kit's hooks


@pytest.mark.parametrize(
    "bad",
    [
        [],
        {"hooks": []},
        {"hooks": {"Stop": {"hooks": []}}},
        {"hooks": {"Stop": [{"command": "x"}]}},
        {"hooks": {"Stop": ["x"]}},
        {"hooks": {"Stop": [{"hooks": ["x"]}]}},
    ],
)
def test_merge_hooks_validates_shapes(bad):
    with pytest.raises(vendor.VendorError):
        vendor.merge_hooks(bad)


def test_hook_command_survives_a_missing_cli(tmp_path):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    p = subprocess.run(["bash", "-c", vendor.hook_command("guard")], input="{}", capture_output=True, text=True, env=env)
    assert p.returncode == 0
    assert vendor.HOOK_TAG in vendor.hook_command("guard")


def test_containment_and_symlinks(tmp_path, mattpocock, kit, proj):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SKILL.md").write_text("escaped")
    mf = mattpocock / ".claude-plugin/plugin.json"
    mf.write_text(json.dumps({"skills": ["../outside"]}))
    with pytest.raises(vendor.VendorError, match="outside the checkout"):
        vendor.plan(kit, mattpocock)
    mf.write_text(json.dumps({"skills": ["./skills/engineering/tdd"]}))

    (kit / "skills/next/linked.md").symlink_to(outside / "SKILL.md")
    (kit / "skills/next/linked-dir").symlink_to(outside)
    r = vendor.install(kit, proj, mattpocock)
    assert not (proj / ".claude/skills/next/linked.md").exists()
    assert not (proj / ".claude/skills/next/linked-dir").exists()
    assert any(s.endswith("linked.md") for s in r["symlinks_skipped"])
    assert any(s.endswith("linked-dir") for s in r["symlinks_skipped"])


def test_not_a_kit_is_a_clean_error(tmp_path, proj):
    p = subprocess.run([sys.executable, str(CLI), "vendor", "install", "--kit", str(tmp_path), "--project", str(proj)], capture_output=True, text=True)
    assert p.returncode == 1 and "doesn't look like the kit" in p.stderr and "Traceback" not in p.stderr


def test_gitignore_gets_workflow_dir_once(mattpocock, kit, proj):
    (proj / ".gitignore").write_text("node_modules/")
    vendor.install(kit, proj, mattpocock)
    vendor.install(kit, proj, mattpocock, update=True)
    assert (proj / ".gitignore").read_text() == "node_modules/\n.workflow/\n"


# ---------- evidence ----------

RUNNER = (
    "import os, sys\n"
    "p=f=0\n"
    "for a in sys.argv[1:]:\n"
    "    r=open(a).read().strip()\n"
    "    p+=r=='pass'; f+=r=='fail'\n"
    "if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.workflow', 'break')):\n"
    "    print('ConnectionError: docker daemon refused'); f+=1\n"
    "print(f'{p} passed' + (f', {f} failed' if f else ''))\n"
    "sys.exit(1 if f else 0)\n"
)


def _suite_repo(tmp_path, results, **suite):
    (tmp_path / "tests").mkdir()
    for i, r in enumerate(results):
        (tmp_path / f"tests/test_{i}.txt").write_text(r)
    (tmp_path / "run_tests.py").write_text(RUNNER)
    (tmp_path / ".gitignore").write_text(".workflow/\n")
    _git_repo(tmp_path)
    s = {"name": "unit", "run": "python3 run_tests.py {files}", "files": "tests/test_*.txt", "group": 2, **suite}
    return _profile(tmp_path, s)


def _profile(root, *suites, repair=None):
    data = {"project": {"name": "d", "repo": "a/d"}, "commands": {"suite": list(suites)}}
    if repair:
        data["repair"] = {"commands": repair}
    return parse(data, root)


def test_evidence_shards_resume_and_report(tmp_path):
    prof = _suite_repo(tmp_path, ["pass", "pass", "pass"])
    sha, res = evidence.collect(prof, tmp_path)
    assert len(res) == 2 and sum(r.passed for r in res) == 3
    assert (tmp_path / f".workflow/evidence/{sha}/unit-000.log").read_text().startswith("$ python3 run_tests.py")
    ok, md = evidence.report(sha, prof, res, base_count=3)
    assert ok and sha in md and "3 passed" in md
    assert "  1 passed" in md  # the suite's short tail, even on success
    # Resume: finished shards aren't run again.
    (tmp_path / "tests/test_0.txt").write_text("fail")  # dirty tree
    with pytest.raises(evidence.EvidenceError, match="uncommitted"):
        evidence.collect(prof, tmp_path)
    git(tmp_path, "checkout", "--", ".")
    sha2, res2 = evidence.collect(prof, tmp_path)
    assert sha2 == sha and [r.seconds for r in res2] == [r.seconds for r in res]
    ok, md = evidence.report(sha, prof, res2, base_count=5)
    assert not ok and "Fewer tests than the base branch" in md and "A test was removed or skipped" in md

    # The cache key includes the command: a changed run re-runs.
    prof2 = _profile(tmp_path, {"name": "unit", "run": "python3 run_tests.py {files} ", "files": "tests/test_*.txt", "group": 2})
    _, res3 = evidence.collect(prof2, tmp_path)
    assert all(r.run == prof2.suites[0].run for r in res3)


def test_evidence_failure_shows_the_cause(tmp_path):
    prof = _suite_repo(tmp_path, ["pass", "fail"])
    (tmp_path / ".workflow").mkdir()
    (tmp_path / ".workflow/break").write_text("")
    sha, res = evidence.collect(prof, tmp_path)
    ok, md = evidence.report(sha, prof, res)
    assert not ok and "FAILED" in md and "2 failed" in md  # the failing test, and the broken environment
    assert "Likely cause:" in md and "ConnectionError: docker daemon refused" in md
    assert "Full output: `.workflow/evidence/" in md
    assert "No base-branch count given: this doesn't show whether tests were removed." in md


def test_retry_records_the_earlier_failure(tmp_path):
    prof = _suite_repo(tmp_path, ["pass"])
    (tmp_path / ".workflow").mkdir()
    (tmp_path / ".workflow/break").write_text("")
    sha, res = evidence.collect(prof, tmp_path)
    assert not res[0].ok
    (tmp_path / ".workflow/break").unlink()
    sha, res = evidence.collect(prof, tmp_path)
    assert res[0].ok and len(res[0].previous_failures) == 1
    saved = json.loads((tmp_path / f".workflow/evidence/{sha}/unit-000.json").read_text())
    assert saved["previous_failures"][0]["exit"] == 1
    ok, md = evidence.report(sha, prof, res)
    assert ok and "passed on retry after 1 failure" in md


def test_a_suite_that_runs_nothing_fails(tmp_path):
    (tmp_path / "x").write_text("")
    _git_repo(tmp_path)
    prof = _profile(tmp_path, {"name": "empty", "run": "echo 'no tests ran'"})
    sha, res = evidence.collect(prof, tmp_path)
    assert res[0].exit == 0 and not res[0].ok
    ok, md = evidence.report(sha, prof, res)
    assert not ok and "no test counts found in the output; check the suite's regexes" in md


def test_counts_read_stdout_first_then_stderr():
    s = parse({"project": {"name": "d", "repo": "a/d"}, "commands": {"suite": [{"name": "u", "run": "x"}]}}, Path(".")).suites[0]
    # The concatenation's tail would be stderr's noise; stdout's own last lines hold the totals.
    out = "3 passed\n"
    err = "\n".join(f"warning {i}" for i in range(10))
    assert evidence.counts(s, out, err)["passed"] == 3
    # jest prints its totals to stderr.
    assert evidence.counts(s, "console.log noise\n", "Tests: 1 failed, 4 passed")["passed"] == 4
    assert evidence.counts(s, "", "")["passed"] == 0


def test_untracked_files_need_allow_dirty(tmp_path):
    prof = _suite_repo(tmp_path, ["pass"])
    (tmp_path / "tests/test_9.txt").write_text("pass")  # untracked, not ignored: changes the result
    with pytest.raises(evidence.EvidenceError, match="untracked"):
        evidence.collect(prof, tmp_path)
    dirty = evidence.dirty_paths(tmp_path)
    sha, res = evidence.collect(prof, tmp_path, allow_dirty=True)
    assert sum(r.passed for r in res) == 2
    assert (tmp_path / f".workflow/evidence/{sha}-dirty").is_dir()
    assert not (tmp_path / f".workflow/evidence/{sha}").exists()  # never reused as the commit's proof
    ok, md = evidence.report(sha, prof, res, dirty=dirty)
    assert "NOT A PROOF OF THE COMMIT" in md and "not a proof of the commit" in md.lower()


def test_repair_runs_once_and_again_after_a_failed_shard(tmp_path):
    prof = _suite_repo(tmp_path, ["pass", "pass", "pass"], group=1)
    prof.repair = ["echo r >> .workflow/repairs"]
    (tmp_path / ".workflow").mkdir(exist_ok=True)
    evidence.collect(prof, tmp_path)
    assert (tmp_path / ".workflow/repairs").read_text().count("r") == 1
    (tmp_path / ".workflow/break").write_text("")
    evidence.collect(prof, tmp_path, fresh=True)
    # once at the start, then before shards 2 and 3 since each one before failed
    assert (tmp_path / ".workflow/repairs").read_text().count("r") == 1 + 3


def test_fewer_tests_with_errors_points_at_the_environment(tmp_path):
    prof = _suite_repo(tmp_path, ["pass"])
    r = evidence.ShardResult("unit", 0, [], 1, 1, 0, 0, 2, 1.0, "")
    ok, md = evidence.report("abc", prof, [r], base_count=5)
    assert not ok
    assert "Fewer tests passed than on the base branch, and some errored: the environment may be failing (see the errors above)" in md
    assert "A test was removed" not in md


def test_suite_cwd_gets_files_relative_to_it(tmp_path):
    (tmp_path / "app/tests").mkdir(parents=True)
    (tmp_path / "app/tests/test_a.txt").write_text("pass")
    (tmp_path / "app/run_tests.py").write_text(RUNNER)
    (tmp_path / ".gitignore").write_text(".workflow/\n")
    _git_repo(tmp_path)
    prof = _profile(tmp_path, {"name": "app", "run": "python3 run_tests.py {files}", "files": "app/tests/test_*.txt", "cwd": "app"})
    assert evidence.shards(prof.suites[0], tmp_path) == [["tests/test_a.txt"]]
    sha, res = evidence.collect(prof, tmp_path)
    assert res[0].ok and res[0].passed == 1


def test_files_without_placeholder_is_an_error(tmp_path):
    with pytest.raises(ProfileError, match=r"no \{files\}"):
        _profile(tmp_path, {"name": "u", "run": "pytest -q", "files": "tests/*.py"})
    with pytest.raises(ProfileError, match="cwd"):
        _profile(tmp_path, {"name": "u", "run": "pytest {files}", "files": "t/*.py", "cwd": "../elsewhere"})


def test_base_ref_runs_the_base_in_a_worktree(tmp_path):
    prof = _suite_repo(tmp_path, ["pass", "pass"])
    git(tmp_path, "branch", "base")
    git(tmp_path, "checkout", "-qb", "feature")
    (tmp_path / "tests/test_1.txt").unlink()
    git(tmp_path, "commit", "-qam", "drop a test")
    count, base_sha, base_ok = evidence.base_count_from_ref(prof, tmp_path, "base")
    assert count == 2 and base_ok and base_sha == git(tmp_path, "rev-parse", "base").strip()
    assert not (tmp_path / f".workflow/base-{base_sha}").exists()
    assert len(git(tmp_path, "worktree", "list").splitlines()) == 1
    sha, res = evidence.collect(prof, tmp_path)
    ok, md = evidence.report(sha, prof, res, count, base_label="`base`")
    assert not ok and "1 passed here, 2 on base" in md and md.startswith(f"**Local full suite on `{sha}`**: FAILED")
    with pytest.raises(evidence.EvidenceError, match="not a commit"):
        evidence.base_count_from_ref(prof, tmp_path, "nope")
