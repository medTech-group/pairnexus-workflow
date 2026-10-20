"""The "release gate" check (#88, #36's seam 1): its decision, `.github/scripts/release_gate.py`,
run on recorded JSON as the release script's tests run it, asserting only on its output and exit
code; and its workflow, `.github/workflows/release-gate.yml`, read as `release.yml` is read."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
SCRIPT = KIT / ".github/scripts/release_gate.py"
WORKFLOW = KIT / ".github/workflows/release-gate.yml"

HEAD = "a" * 40
OLD = "b" * 40
MARK = "<!-- workflow:agent -->"
LINK = "https://github.com/o/r/pull/7#issuecomment-"

CHANGELOG = """# Changelog

## Unreleased

## 0.2.0

- New things.

## 0.1.9

- Old things.
"""


def _comment(body, login="maintainer", at="2026-10-20T10:00:00Z", n=1):
    return {"id": n, "user": {"login": login}, "body": body, "created_at": at, "html_url": f"{LINK}{n}"}


def _report(verdict, sha=HEAD, **kw):
    return _comment(f"| check | result |\n|---|---|\n| doctor | pass |\n\n{MARK}\nrelease-gate: {verdict} {sha}\n", **kw)


def _run(tmp_path, *, files=("VERSION", "CHANGELOG.md"), comments=(), permissions=None, labels=(),
         body="The 0.2.0 release.", changelog=CHANGELOG, head_version="0.2.0\n", base_version="0.1.9\n",
         omit=()):
    data = {
        "pr": {"number": 7, "head": {"sha": HEAD}, "body": body, "labels": [{"name": n} for n in labels],
               "html_url": "https://github.com/o/r/pull/7"},
        # As `gh api --paginate --slurp` gives them: a list of pages.
        "files": [[{"filename": f} for f in files]],
        "comments": [list(comments)],
        "permissions": {"maintainer": "admin", "helper": "write"} if permissions is None else permissions,
    }
    args = [sys.executable, "-I", str(SCRIPT)]
    for name, value in data.items():
        if name in omit:
            continue
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value))
        args += [f"--{name}", str(path)]
    for name, text in (("changelog", changelog), ("version-head", head_version), ("version-base", base_version)):
        if name in omit:
            continue
        path = tmp_path / name
        path.write_text(text)
        args += [f"--{name}", str(path)]
    p = subprocess.run(args, capture_output=True, text=True, cwd=tmp_path)
    return p.returncode, p.stdout.strip()


def _passes(result):
    code, out = result
    assert code == 0 and out.startswith("pass: "), result
    return out


def _fails(result):
    code, out = result
    assert code != 0 and out.startswith("fail: ") and len(out) > len("fail: ") + 10, result
    return out


# ---------- a pull request that doesn't change VERSION ----------

def test_a_pr_not_changing_version_passes_without_comments_or_permissions(tmp_path):
    out = _passes(_run(tmp_path, files=("README.md", "skills/start/SKILL.md"),
                       omit=("comments", "permissions", "changelog", "version-head", "version-base")))
    assert "VERSION" in out


def test_a_renamed_version_file_counts_as_changing_it(tmp_path):
    p = tmp_path / "files.json"
    p.write_text(json.dumps([{"filename": "OLD_VERSION", "previous_filename": "VERSION"}]))
    pr = tmp_path / "pr.json"
    pr.write_text(json.dumps({"number": 7, "head": {"sha": HEAD}, "body": "", "labels": []}))
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), "--pr", str(pr), "--files", str(p)],
                       capture_output=True, text=True)
    assert r.returncode != 0 and r.stdout.startswith("fail: ")


def test_a_release_pr_without_the_rest_of_its_inputs_fails_saying_which(tmp_path):
    out = _fails(_run(tmp_path, omit=("comments", "permissions")))
    assert "comments" in out


# ---------- the gate's report ----------

def test_a_pass_for_the_head_commit_passes(tmp_path):
    out = _passes(_run(tmp_path, comments=[_report("pass")]))
    assert HEAD in out


def test_no_report_fails_saying_so(tmp_path):
    out = _fails(_run(tmp_path, comments=[_comment("Looks good to me.")]))
    assert "no release gate report" in out


def test_a_pass_for_an_older_commit_fails_naming_it(tmp_path):
    out = _fails(_run(tmp_path, comments=[_report("pass", sha=OLD)]))
    assert OLD in out and HEAD in out


def test_a_later_fail_for_the_same_commit_wins(tmp_path):
    out = _fails(_run(tmp_path, comments=[
        _report("fail", n=2, at="2026-10-20T11:00:00Z"),
        _report("pass", n=1, at="2026-10-20T10:00:00Z"),
    ]))
    assert f"{LINK}2" in out


def test_a_later_pass_after_a_fail_passes(tmp_path):
    _passes(_run(tmp_path, comments=[
        _report("fail", n=1, at="2026-10-20T10:00:00Z"),
        _report("pass", n=2, at="2026-10-20T11:00:00Z"),
    ]))


def test_a_fail_links_its_comment(tmp_path):
    out = _fails(_run(tmp_path, comments=[_report("fail", n=5)]))
    assert f"{LINK}5" in out


def test_a_newer_report_for_another_commit_doesnt_hide_the_heads_pass(tmp_path):
    _passes(_run(tmp_path, comments=[
        _report("pass", n=1, at="2026-10-20T10:00:00Z"),
        _report("pass", sha=OLD, n=2, at="2026-10-20T11:00:00Z"),
    ]))


def test_a_pass_without_the_marker_is_ignored(tmp_path):
    c = _comment(f"release-gate: pass {HEAD}\n")
    out = _fails(_run(tmp_path, comments=[c]))
    assert "no release gate report" in out


def test_a_pass_from_read_or_triage_permission_is_ignored(tmp_path):
    for perm in ("read", "triage", "none"):
        out = _fails(_run(tmp_path, comments=[_report("pass", login="stranger")],
                          permissions={"stranger": perm}))
        assert "no release gate report" in out, perm


def test_a_pass_from_an_author_missing_from_the_permissions_is_ignored(tmp_path):
    out = _fails(_run(tmp_path, comments=[_report("pass", login="stranger")]))
    assert "no release gate report" in out


def test_write_maintain_and_admin_count_and_logins_ignore_case(tmp_path):
    for perm in ("write", "maintain", "admin"):
        _passes(_run(tmp_path, comments=[_report("pass", login="Helper")], permissions={"helper": perm}))


def test_an_unauthorised_fail_doesnt_undo_a_pass(tmp_path):
    _passes(_run(tmp_path, comments=[
        _report("pass", n=1, at="2026-10-20T10:00:00Z"),
        _report("fail", login="stranger", n=2, at="2026-10-20T11:00:00Z"),
    ], permissions={"maintainer": "admin", "stranger": "read"}))


def test_a_short_sha_or_a_malformed_line_isnt_a_gate_line(tmp_path):
    for line in (f"release-gate: pass {HEAD[:7]}", f"release-gate: pass {HEAD}0", f"release-gate: passed {HEAD}",
                 f"release-gate pass {HEAD}", f"release-gate: pass {'g' * 40}", f"see release-gate: pass {HEAD}"):
        out = _fails(_run(tmp_path, comments=[_comment(f"{MARK}\n{line}\n")]))
        assert "no release gate report" in out, line


# ---------- skipping the gate ----------

SKIP_BODY = "An urgent fix for the guard.\n\nGate skipped because the sandbox is down and the guard is broken.\n"
SKIP_LOG = CHANGELOG.replace("- New things.", "- New things.\n- Release gate skipped because the guard broke "
                                                "on Claude Code 3.1 and the sandbox was down.")


def test_a_skip_with_its_label_pr_line_and_changelog_line_passes(tmp_path):
    out = _passes(_run(tmp_path, labels=["release-gate-skipped"], body=SKIP_BODY, changelog=SKIP_LOG))
    assert "skip" in out


def test_a_skip_missing_its_label_fails_naming_it(tmp_path):
    out = _fails(_run(tmp_path, body=SKIP_BODY, changelog=SKIP_LOG))
    assert "release-gate-skipped" in out and "label" in out


def test_a_skip_missing_its_pr_line_fails_naming_it(tmp_path):
    out = _fails(_run(tmp_path, labels=["release-gate-skipped"], changelog=SKIP_LOG))
    assert "Gate skipped because" in out and "description" in out


def test_a_skip_missing_its_changelog_line_fails_naming_it(tmp_path):
    out = _fails(_run(tmp_path, labels=["release-gate-skipped"], body=SKIP_BODY))
    assert "Release gate skipped because" in out and "0.2.0" in out


def test_a_skip_line_in_another_versions_entry_doesnt_count(tmp_path):
    log = CHANGELOG.replace("## Unreleased\n", "## Unreleased\n\n- Release gate skipped because reasons.\n")
    out = _fails(_run(tmp_path, labels=["release-gate-skipped"], body=SKIP_BODY, changelog=log))
    assert "Release gate skipped because" in out


def test_a_skip_when_the_last_release_skipped_fails_saying_so(tmp_path):
    log = SKIP_LOG.replace("- Old things.", "- Old things.\n- Release gate skipped because of last week's outage.")
    out = _fails(_run(tmp_path, labels=["release-gate-skipped"], body=SKIP_BODY, changelog=log))
    assert "0.1.9" in out and "last release skipped" in out


def test_a_pass_for_the_head_commit_passes_whatever_the_skip_says(tmp_path):
    _passes(_run(tmp_path, labels=["release-gate-skipped"], comments=[_report("pass")]))


def test_every_fail_gives_its_reason(tmp_path):
    cases = [
        _run(tmp_path),
        _run(tmp_path, comments=[_report("pass", sha=OLD)]),
        _run(tmp_path, comments=[_report("fail")]),
        _run(tmp_path, labels=["release-gate-skipped"]),
        _run(tmp_path, omit=("permissions",)),
    ]
    reasons = {_fails(c) for c in cases}
    assert len(reasons) == len(cases)


def test_an_unreadable_input_fails_with_its_name(tmp_path):
    (tmp_path / "bad.json").write_text("{not json")
    pr = tmp_path / "pr.json"
    pr.write_text(json.dumps({"number": 7, "head": {"sha": HEAD}, "body": "", "labels": []}))
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), "--pr", str(pr), "--files", str(tmp_path / "bad.json")],
                       capture_output=True, text=True)
    assert r.returncode != 0 and r.stdout.startswith("fail: ") and "files" in r.stdout


# ---------- the workflow ----------

def _wf():
    return WORKFLOW.read_text()


def test_the_job_is_named_release_gate_and_runs_on_the_pull_request_events():
    wf = _wf()
    assert re.search(r"^\s+name: release gate$", wf, re.M)
    assert "pull_request:" in wf and "pull_request_target" not in wf
    assert "types: [opened, synchronize, reopened, edited, labeled, unlabeled]" in wf


def test_a_comment_reruns_the_latest_release_gate_run_for_the_head():
    wf = _wf()
    assert "issue_comment:" in wf and "types: [created, edited, deleted]" in wf
    assert "github.event.issue.pull_request" in wf
    assert "head_sha=" in wf and "/rerun" in wf and "event=pull_request" in wf


def test_least_permissions():
    wf = _wf()
    assert re.search(r"^permissions: \{\}$", wf, re.M)
    gate, rerun = wf.split("\n  rerun:\n")
    grants = lambda part: re.findall(r"^ {6}([a-z-]+): (read|write)$", part, re.M)  # noqa: E731
    assert grants(gate) and all(level == "read" for _, level in grants(gate))
    assert [g for g in grants(rerun) if g[1] == "write"] == [("actions", "write")]


def test_it_reads_the_pr_from_the_api_when_it_runs_and_runs_the_script():
    wf = _wf()
    for api in ("pulls/$PR", "pulls/$PR/files", "issues/$PR/comments", "collaborators/", "/permission",
                "contents/CHANGELOG.md", "contents/VERSION"):
        assert api in wf, api
    assert ".github/scripts/release_gate.py" in wf
    # Nothing about the pull request comes from the event's payload but its number.
    payload = re.findall(r"github\.event\.[a-z_.]+", wf)
    assert set(payload) <= {"github.event.pull_request.number", "github.event.issue.number",
                            "github.event.issue.pull_request"}, payload


def test_a_pr_not_changing_version_skips_the_comments_and_permissions():
    wf = _wf()
    # The step that reads comments and permissions runs only for a release PR.
    reads = wf.split("issues/$PR/comments")[0].rsplit("- name:", 1)[1]
    assert "if: steps." in reads
