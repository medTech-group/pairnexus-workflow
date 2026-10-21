"""#89: the `release-gate` skill (#36). Seam 2: what a vendored copy and the plugin
contain. Seam 3: the skill's wording, read from its file as the kit-release tests
read skills. And the line the skill writes is the line the check reads: its
example reports, with a commit filled in, go through #88's script."""

from __future__ import annotations

import json
import re
import subprocess
import sys

from conftest import KIT

from workflow import vendor
from changelog_notes import since_0110

SKILL = KIT / ".claude/skills/release-gate/SKILL.md"
SCRIPT = KIT / ".github/scripts/release_gate.py"
SHA = "3f2a9c01b7de" + "4" * 28

# The checks, in their order. Later tickets insert theirs (#91 after the first,
# #92 after the last) without rewording these.
CHECKS = ["The update with CI green", "The guard's refusal", "The ruleset's refusal"]


def _text():
    return SKILL.read_text(encoding="utf-8")


def _flat(s):
    return re.sub(r"\s+", " ", s)


def _section(title):
    m = re.search(rf"^## [^\n]*{re.escape(title)}[^\n]*\n(.*?)(?=^## |\Z)", _text(), re.M | re.S)
    assert m, f"no section {title!r}"
    return m.group(1)


def _examples():
    """The report section's example reports, in order: the pass, then the fail."""
    return re.findall(r"^```markdown\n(.*?)^```", _section("The report"), re.M | re.S)


# ---------- what ships (seam 2) ----------

def test_the_skill_is_the_kit_repositorys_own_and_never_ships():
    assert SKILL.is_file()
    assert not (KIT / "skills/release-gate").exists()
    assert not any("release-gate" in dst for dst in vendor.plan(KIT, None))


def test_the_plugin_takes_only_skills():
    """The plugin's skills are `skills/`: its manifest names no other skill directory."""
    for name in ("plugin.json", "marketplace.json"):
        text = (KIT / ".claude-plugin" / name).read_text()
        assert "release-gate" not in text and ".claude/skills" not in text
    assert "skills" not in json.loads((KIT / ".claude-plugin/plugin.json").read_text())


def test_its_description_loads_it_on_the_ask():
    front = _text().split("---", 2)[1]
    assert "name: release-gate" in front
    assert "run the release gate on PR #N" in front
    assert "disable-model-invocation" not in front


# ---------- the skill's wording (seam 3) ----------

def test_the_candidate_is_the_prs_exact_commit_outside_the_working_tree():
    s = _flat(_section("The candidate"))
    assert "exact commit" in s and "full 40-character SHA" in s and "`VERSION` at it" in s
    assert "outside this session's working tree" in s and "checkout --detach" in s


def test_a_sandbox_branch_with_its_pull_request():
    s = _flat(_section("The sandbox branch"))
    assert "pairnexus-workflow-sandbox" in _text()
    assert '`access: "push"`' in s and "release-gate/$VERSION origin/main" in s
    assert "open the sandbox pull request" in s and "names the candidate commit" in s
    assert "links the release pull request" in s


def test_the_update_goes_through_the_candidates_update_workflow():
    s = _flat(_section("The sandbox branch"))
    assert "`$CAND/skills/update-workflow/SKILL.md`" in s
    assert "`vendor update --kit` pointing at the candidate's checkout" in s
    assert 'vendor update --kit "$CAND"' in s
    assert "pinned SHA" in s and "marketplace.json" in s


def test_a_run_on_a_newer_commit_starts_afresh_and_posts_a_new_report():
    assert "A run on a newer commit starts afresh" in _section("The sandbox branch")
    assert "close it" in _section("The sandbox branch")
    assert "A run on a newer commit posts a new report**; the old ones stay" in _section("The report")


def test_the_checks_run_in_order_as_one_numbered_list():
    """The numbered list is consecutive, and CI, the guard's refusal and the ruleset's
    refusal come in that order, wherever later tickets add theirs."""
    s = _section("The checks, in order")
    items = re.findall(r"^(\d+)\. \*\*([^*]+?)\.\*\*", s, re.M)
    assert [int(n) for n, _ in items] == list(range(1, len(items) + 1))
    names = [name for _, name in items]
    assert [n for n in names if n in CHECKS] == CHECKS


def test_each_check_says_what_passes_and_its_evidence():
    s = _flat(_section("The checks, in order"))
    assert "`ci.required_checks`" in s and "the CI run's link" in s
    assert "`create_session`" in s and "`run.ticket_environment`" in s and "`list_environments`" in s
    assert "release-gate/$VERSION" in s and "push it to main" in s
    assert "`main` is unchanged" in s and "before and after" in s and "transcript's link" in s
    assert "throwaway clone outside any checkout with the kit's hooks" in s
    assert "repository rule violation" in s and "the push's output" in s


def test_a_failed_check_stops_the_gate_and_closes_the_sandbox_pr():
    s = _flat(_section("The checks, in order"))
    assert "A failed check stops the gate" in s and "close the sandbox pull request" in s
    r = _flat(_section("The report"))
    assert "After a fail, it is closed" in r and "After a pass, the sandbox pull request stays open" in r


def test_the_report_has_its_table_version_marker_and_line_last():
    r = _flat(_section("The report"))
    assert "(check | result | evidence)" in r and "the Claude Code version" in r
    assert "`<!-- workflow:agent -->`" in r and "machine-readable line" in r
    assert "ordinary pull request comment" in r and "never a review comment" in r
    assert "read the pull request's head again" in r
    assert "`claude --version`" in _section("The candidate")
    for ex in _examples():
        rows = re.findall(r"^\| (The [^|]+?) \|", ex, re.M)
        assert [x for x in rows if x in CHECKS] == CHECKS
        assert "Claude Code version: " in ex and "<!-- workflow:agent -->" in ex
        assert re.search(r"release-gate: (pass|fail) <full sha>\n\Z", ex)


# ---------- the line the skill writes is the line the check reads ----------

def _check(tmp_path, report):
    data = {
        "pr": {"number": 7, "head": {"sha": SHA}, "body": "The 0.2.0 release.", "labels": [], "changed_files": 2},
        "files": [{"filename": "VERSION"}, {"filename": "CHANGELOG.md"}],
        "comments": [{"id": 1, "user": {"login": "maintainer"}, "body": report,
                      "created_at": "2026-10-21T10:00:00Z", "html_url": "https://github.com/o/r/pull/7#issuecomment-1"}],
        "permissions": {"maintainer": "admin"},
    }
    args = [sys.executable, "-I", str(SCRIPT)]
    for name, value in data.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
        args += [f"--{name}", str(tmp_path / f"{name}.json")]
    changelog = "# Changelog\n\n## 0.2.0\n\n- New.\n\n## 0.1.9\n\n- Old.\n"
    for name, text in (("changelog", changelog), ("changelog-base", changelog),
                       ("version-head", "0.2.0\n"), ("version-base", "0.1.9\n")):
        (tmp_path / name).write_text(text)
        args += [f"--{name}", str(tmp_path / name)]
    p = subprocess.run(args, capture_output=True, text=True)
    return p.returncode, p.stdout.strip()


def test_the_example_pass_reads_as_a_pass_for_its_commit(tmp_path):
    passed, _ = _examples()
    code, out = _check(tmp_path, passed.replace("<full sha>", SHA))
    assert code == 0 and out.startswith("pass: ") and SHA in out, out


def test_the_example_pass_for_another_commit_counts_for_nothing(tmp_path):
    passed, _ = _examples()
    code, out = _check(tmp_path, passed.replace("<full sha>", "b" * 40))
    assert code == 1 and out.startswith("fail: "), out


def test_the_example_fail_reads_as_a_fail(tmp_path):
    _, failed = _examples()
    code, out = _check(tmp_path, failed.replace("<full sha>", SHA))
    assert code == 1 and out.startswith("fail: ") and "failed for the head commit" in out, out


# ---------- docs ----------

def test_contributing_says_how_to_run_the_gate_and_that_claude_skills_never_ships():
    c = _flat((KIT / "CONTRIBUTING.md").read_text())
    assert "run the release gate on PR #N" in c and "about 30 minutes" in c
    assert "ticket environment" in c and "#89 says how" not in c
    assert "own `.claude/skills/` is for maintainers and never ships" in c


def test_spike_says_the_gate_re_proves_rows_4_and_5():
    s = _flat((KIT / "docs/spike.md").read_text())
    assert "re-proves rows 4 (the push) and 5 at every release" in s
    assert "changes only when a row's status does" in s


def test_the_changelog_note_and_no_version_bump():
    text = (KIT / "CHANGELOG.md").read_text()
    assert "(#89," in since_0110(text) and "`release-gate`" in since_0110(text)
    released = text.split("\n## ")[2].split()[0].lstrip("v")
    assert (KIT / "VERSION").read_text().strip() == released
