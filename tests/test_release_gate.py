"""The "release gate" check (#88, #36's seam 1): its decision, `.github/scripts/release_gate.py`,
run as a command on recorded JSON, asserting only on its output and exit code; and its workflow,
`.github/workflows/release-gate.yml`, read as `release.yml` is read."""

from __future__ import annotations

import json
import re
import subprocess
import sys

from conftest import KIT

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
         body="The 0.2.0 release.", changelog=CHANGELOG, changelog_base=None, head_version="0.2.0\n",
         base_version="0.1.9\n", changed_files=None, omit=()):
    data = {
        "pr": {"number": 7, "head": {"sha": HEAD}, "body": body, "labels": [{"name": n} for n in labels],
               "html_url": "https://github.com/o/r/pull/7",
               "changed_files": len(files) if changed_files is None else changed_files},
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
    texts = (("changelog", changelog), ("changelog-base", changelog if changelog_base is None else changelog_base),
             ("version-head", head_version), ("version-base", base_version))
    for name, text in texts:
        if name in omit:
            continue
        path = tmp_path / name
        path.write_bytes(text.encode())
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
                       omit=("comments", "permissions", "changelog", "changelog-base", "version-head", "version-base")))
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
    assert "no gate report" in out


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
    assert "no gate report" in out


def test_a_pass_from_read_or_triage_permission_is_ignored(tmp_path):
    for perm in ("read", "triage", "none"):
        out = _fails(_run(tmp_path, comments=[_report("pass", login="stranger")],
                          permissions={"stranger": perm}))
        assert "no gate report" in out, perm


def test_a_pass_from_an_author_missing_from_the_permissions_is_ignored(tmp_path):
    out = _fails(_run(tmp_path, comments=[_report("pass", login="stranger")]))
    assert "no gate report" in out


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
        assert "no gate report" in out, line


def test_a_gate_line_with_windows_line_ends_counts(tmp_path):
    crlf = _comment(f"{MARK}\r\nrelease-gate: fail {HEAD}\r\n", n=2, at="2026-10-20T11:00:00Z")
    out = _fails(_run(tmp_path, comments=[_report("pass", n=1), crlf]))
    assert f"{LINK}2" in out


def test_comments_posted_at_the_same_time_go_by_id(tmp_path):
    _fails(_run(tmp_path, comments=[_report("fail", n=9), _report("pass", n=3)]))


def test_a_pr_whose_files_couldnt_all_be_read_fails(tmp_path):
    out = _fails(_run(tmp_path, files=("README.md",), changed_files=3001, omit=("comments", "permissions")))
    assert "1 of 3001" in out


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


def test_bold_skip_lines_count(tmp_path):
    body = "**Gate skipped because** the sandbox is down.\n"
    log = CHANGELOG.replace("- New things.", "- New things.\n- **Release gate skipped because** the guard broke.")
    _passes(_run(tmp_path, labels=["release-gate-skipped"], body=body, changelog=log))


def test_the_last_releases_skip_is_read_from_the_base_not_the_head(tmp_path):
    base = CHANGELOG.replace("- Old things.", "- Old things.\n- Release gate skipped because of last week's outage.")
    out = _fails(_run(tmp_path, labels=["release-gate-skipped"], body=SKIP_BODY, changelog=SKIP_LOG,
                      changelog_base=base))
    assert "last release skipped" in out


def test_a_skip_when_the_base_has_no_entry_for_its_version_fails(tmp_path):
    out = _fails(_run(tmp_path, labels=["release-gate-skipped"], body=SKIP_BODY, changelog=SKIP_LOG,
                      changelog_base="# Changelog\n"))
    assert "no 0.1.9 entry" in out


def test_the_first_release_may_skip(tmp_path):
    _passes(_run(tmp_path, labels=["release-gate-skipped"], body=SKIP_BODY, changelog=SKIP_LOG,
                 changelog_base="", base_version=""))


def test_a_failed_skip_keeps_the_reports_reason(tmp_path):
    out = _fails(_run(tmp_path, labels=["release-gate-skipped"], comments=[_report("fail", n=4)]))
    assert f"{LINK}4" in out and "the skip is missing" in out


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
    cases.append(_run(tmp_path, labels=["release-gate-skipped"], body=SKIP_BODY, changelog=SKIP_LOG,
                      changelog_base=SKIP_LOG.replace("- Old things.", "- Old things.\n- Release gate skipped because x.")))
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
    assert "\n  gate:\n    name: release gate\n" in wf
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
                "contents/$1?ref=$2", 'raw CHANGELOG.md "$HEAD"', 'raw VERSION "$HEAD"'):
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


def test_the_script_that_judges_comes_from_the_base_branch_not_the_pr():
    wf = _wf()
    assert "actions/checkout" not in wf  # the PR's code is never checked out
    assert 'raw .github/scripts/release_gate.py "$base"' in wf
    assert 'python3 -I "$DATA/release_gate.py"' in wf


def test_only_a_missing_file_reads_as_empty():
    wf = _wf()
    assert 'grep -q "HTTP 404"' in wf and "return 1" in wf and "|| :" not in wf
    assert 'raw CHANGELOG.md "$BASE"' in wf and 'raw VERSION "$BASE"' in wf


def test_reruns_for_one_pr_go_one_at_a_time():
    rerun = _wf().split("\n  rerun:\n")[1]
    assert "concurrency:" in rerun and "github.event.issue.number" in rerun
    timeout = int(re.search(r"timeout-minutes: (\d+)", rerun).group(1))
    waits = re.search(r"seq (\d+)\).*?sleep (\d+)", rerun, re.S)
    assert int(waits.group(1)) * int(waits.group(2)) < timeout * 60
