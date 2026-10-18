"""#59: `workflow doctor`'s GitHub lines: the ruleset, the merge settings and
CODEOWNERS, checked against the profile. Seam 1 of #34: the CLI, with recorded
ruleset and repository JSON given as `--rulesets`/`--repo` files or answered by
a fake `gh` on the PATH (as the `--fetch` tests fake it)."""

import copy
import json
import subprocess

import pytest

from changelog_notes import since_0110
from test_doctor import (
    CODEOWNERS,
    RULESET,
    SETTINGS,
    _bin,
    _doctor,
    _entries,
    _lines,
    _prof,
    _project,
    _report,
    _snapshot,
    gh_routes,
)

CHECKS = '[ci]\nrequired_checks = ["tests"]\n'
SOLO = _prof("ruleset = false\n")
# Every line of the group, as a fully protected repository reads.
GITHUB_IDS = ("github.ruleset", "github.required_checks", "github.up_to_date", "github.approvals", "github.code_owner_review",
              "github.linear_history", "github.merge_commits", "github.auto_merge", "github.codeowners")
# The lines that need GitHub's answers (CODEOWNERS is read from the checkout).
NEEDS_GITHUB = tuple(i for i in GITHUB_IDS if i != "github.codeowners")


def _rs(**over):
    rs = copy.deepcopy(RULESET)
    rs.update(over)
    return rs


def _rule(rs, type_):
    return next(r for r in rs["rules"] if r["type"] == type_)


def _without(rs, type_):
    rs["rules"] = [r for r in rs["rules"] if r["type"] != type_]
    return rs


def _files(tmp_path, rulesets=(RULESET,), settings=SETTINGS):
    """`--rulesets` and `--repo` files, outside the checkout."""
    d = tmp_path / "input"
    d.mkdir(exist_ok=True)
    args = []
    if rulesets is not None:
        (d / "rulesets.json").write_text(rulesets if isinstance(rulesets, str) else json.dumps(list(rulesets)))
        args += ["--rulesets", str(d / "rulesets.json")]
    if settings is not None:
        (d / "repo.json").write_text(settings if isinstance(settings, str) else json.dumps(settings))
        args += ["--repo", str(d / "repo.json")]
    return args


def _github(tmp_path, root, rulesets=(RULESET,), settings=SETTINGS, *args, **kw):
    """The report's GitHub lines by id, from files."""
    r = _report(tmp_path, root, *_files(tmp_path, rulesets, settings), *args, **kw)
    return {ln["id"]: ln for ln in r["lines"] if ln["group"] == "GitHub"}


def _protected(tmp_path, profile=_prof('experience = "new"\nruleset = true\n', CHECKS), **kw):
    return _project(tmp_path, profile=profile, **kw)


# A fully protected repository


def test_a_fully_protected_repository_reads_fine_on_every_line_in_json(tmp_path):
    root = _protected(tmp_path)
    lines = _github(tmp_path, root)
    assert set(lines) == set(GITHUB_IDS), sorted(lines)
    for id_ in GITHUB_IDS:
        assert lines[id_]["status"] == "fine", lines[id_]
        assert lines[id_]["fix"] == "" and lines[id_]["offer"] is None


def test_a_fully_protected_repository_reads_fine_on_every_line_in_text(tmp_path):
    root = _protected(tmp_path)
    p = _doctor(tmp_path, root, *_files(tmp_path))
    assert p.returncode == 0, p.stderr
    out = p.stdout.splitlines()
    assert "GitHub" in out
    github = out[out.index("GitHub") + 1:]
    github = github[: github.index("") if "" in github else len(github)]
    marked = [ln for ln in github if ln.startswith("  [")]
    assert len(marked) == len(GITHUB_IDS) and all(ln.startswith("  [fine]") for ln in marked), p.stdout
    assert _doctor(tmp_path, root, *_files(tmp_path), "--strict").returncode == 0


def test_the_fake_gh_answers_the_same_as_files(tmp_path):
    root = _protected(tmp_path)
    path = _bin(tmp_path)
    r = _report(tmp_path, root, path=path)
    lines = {ln["id"]: ln for ln in r["lines"] if ln["group"] == "GitHub"}
    assert {i: ln["status"] for i, ln in lines.items()} == {i: "fine" for i in GITHUB_IDS}


def test_gh_is_asked_for_each_ruleset_in_full_and_the_settings_and_only_reads(tmp_path):
    import fake_gh

    root = _protected(tmp_path)
    path = _bin(tmp_path)
    _report(tmp_path, root, path=path)
    gh = fake_gh.FakeGh(path)
    paths = [p.split("?")[0] for p in gh.paths()]
    assert "repos/acme/demo/rulesets" in paths and "repos/acme/demo/rulesets/101" in paths and "repos/acme/demo" in paths
    for args in gh.calls():
        assert args[0] == "api", args
        assert not {"-X", "--method", "-f", "-F", "--field", "--raw-field", "--input"} & set(args), args


# Removed protection: the mismatch, first


def test_ruleset_true_with_the_base_branch_unprotected_is_a_gap_offering_restore_protection_listed_first(tmp_path):
    root = _protected(tmp_path)
    r = _report(tmp_path, root, *_files(tmp_path, rulesets=[]))
    first = r["lines"][0]
    assert (first["id"], first["status"], first["offer"]) == ("github.ruleset", "gap", "restore_protection"), first
    assert "main" in first["message"]


def test_the_mismatch_comes_before_every_other_gap_even_another_groups(tmp_path):
    # Your computer has a gap too (no python3), and comes earlier in GROUPS.
    root = _protected(tmp_path)
    path = _bin(tmp_path, python=None)
    r = _report(tmp_path, root, *_files(tmp_path, rulesets=[]), path=path)
    assert r["lines"][0]["id"] == "github.ruleset" and r["lines"][0]["offer"] == "restore_protection"
    assert any(ln["id"] == "computer.python3" and ln["status"] == "gap" for ln in r["lines"])
    p = _doctor(tmp_path, root, *_files(tmp_path, rulesets=[]), path=path)
    out = p.stdout.splitlines()
    assert out[2] == "GitHub", p.stdout  # after the counts and a blank line
    first = _entries(p.stdout)[0]
    assert first.startswith("[gap]") and "doesn't any more" in first, first
    assert out.index("      Claude can offer: Restore protection") < out.index("Your computer")


def test_removed_protection_is_never_trusted_whatever_else_reads_fine(tmp_path):
    root = _protected(tmp_path)
    lines = _github(tmp_path, root, rulesets=[_rs(enforcement="disabled")])
    assert lines["github.ruleset"]["status"] == "gap" and lines["github.ruleset"]["offer"] == "restore_protection"


# Each missing protection, its own gap


@pytest.mark.parametrize(
    "ruleset, id_, words",
    [
        (_rs(enforcement="disabled"), "github.protection.active", "turned off"),
        (_rs(enforcement="evaluate"), "github.protection.active", "only reports"),
        (_rs(conditions={"ref_name": {"include": ["refs/heads/release"], "exclude": []}}), "github.protection.base", "doesn't cover `main`"),
        (_rs(bypass_actors=[{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}]), "github.protection.bypass", "skip"),
        (_without(_rs(), "deletion"), "github.protection.deletions", "deleted"),
        (_without(_rs(), "non_fast_forward"), "github.protection.force_pushes", "force push"),
        (_without(_rs(), "pull_request"), "github.protection.pull_requests", "pull request"),
    ],
)
def test_each_missing_protection_is_its_own_gap_in_plain_words(tmp_path, ruleset, id_, words):
    root = _protected(tmp_path)
    lines = _github(tmp_path, root, rulesets=[ruleset])
    assert lines[id_]["status"] == "gap", lines
    assert words in lines[id_]["message"], lines[id_]["message"]
    assert lines[id_]["fix"]
    assert lines["github.ruleset"]["status"] == "gap"


def test_a_bypass_list_that_cant_be_read_is_a_gap_too(tmp_path):
    rs = _rs()
    del rs["bypass_actors"]
    root = _protected(tmp_path)
    ln = _github(tmp_path, root, rulesets=[rs], env={"WORKFLOW_EXPERIENCE": "developer"})["github.protection.bypass"]
    assert ln["status"] == "gap" and "admin" in ln["message"]


def test_the_developer_wording_carries_the_read_backs_own_words(tmp_path):
    root = _protected(tmp_path)
    ln = _github(tmp_path, root, rulesets=[_without(_rs(), "deletion")], env={"WORKFLOW_EXPERIENCE": "developer"})
    assert "no active ruleset on main restricts deletions" in ln["github.protection.deletions"]["message"]


def test_no_ruleset_with_ruleset_absent_is_a_gap_offering_protect_main(tmp_path):
    root = _project(tmp_path, profile=_prof(""))
    ln = _github(tmp_path, root, rulesets=[])["github.ruleset"]
    assert (ln["status"], ln["offer"]) == ("gap", "protect_main")


# Solo mode


def test_solo_mode_no_ruleset_is_a_note_offering_protect_main(tmp_path):
    root = _project(tmp_path, profile=SOLO)
    lines = _github(tmp_path, root, rulesets=[], settings={**SETTINGS, "allow_auto_merge": False})
    assert (lines["github.ruleset"]["status"], lines["github.ruleset"]["offer"]) == ("note", "protect_main")
    assert lines["github.auto_merge"]["status"] == "note"
    assert not any(ln["status"] in ("gap", "cant_check") for ln in lines.values()), lines
    files = _files(tmp_path, rulesets=[], settings={**SETTINGS, "allow_auto_merge": False})
    assert _doctor(tmp_path, root, *files, "--strict").returncode == 0


def test_auto_merge_off_is_a_gap_outside_solo_mode(tmp_path):
    root = _protected(tmp_path)
    ln = _github(tmp_path, root, settings={**SETTINGS, "allow_auto_merge": False})["github.auto_merge"]
    assert ln["status"] == "gap"


# Required checks


def test_checks_not_required_yet_is_a_note_while_the_profile_lists_none(tmp_path):
    root = _project(tmp_path)
    ln = _github(tmp_path, root, rulesets=[_without(_rs(), "required_status_checks")])["github.required_checks"]
    assert ln["status"] == "note" and "checks not required yet" in ln["message"].lower()


def test_checks_the_profile_lists_that_the_ruleset_doesnt_require_are_a_gap_naming_them(tmp_path):
    root = _project(tmp_path, profile=_prof('ruleset = true\n', '[ci]\nrequired_checks = ["tests", "lint"]\n'))
    ln = _github(tmp_path, root)["github.required_checks"]
    assert ln["status"] == "gap" and "lint" in ln["message"] and "`tests`" not in ln["message"]


def test_a_check_the_ruleset_requires_but_the_profile_doesnt_list_isnt_a_line_here(tmp_path):
    root = _protected(tmp_path)
    rs = _rs()
    _rule(rs, "required_status_checks")["parameters"]["required_status_checks"].append({"context": "extra"})
    ln = _github(tmp_path, root, rulesets=[rs])["github.required_checks"]
    assert ln["status"] == "fine" and "extra" not in ln["message"]


# The other ruleset lines


def test_up_to_date_off_is_a_gap(tmp_path):
    rs = _rs()
    _rule(rs, "required_status_checks")["parameters"]["strict_required_status_checks_policy"] = False
    ln = _github(tmp_path, _protected(tmp_path), rulesets=[rs])["github.up_to_date"]
    assert ln["status"] == "gap" and "up to date" in ln["message"]


def test_code_owners_review_on_is_a_gap(tmp_path):
    rs = _rs()
    _rule(rs, "pull_request")["parameters"]["require_code_owner_review"] = True
    ln = _github(tmp_path, _protected(tmp_path), rulesets=[rs])["github.code_owner_review"]
    assert ln["status"] == "gap"


def test_a_linear_history_rule_is_a_gap(tmp_path):
    rs = _rs()
    rs["rules"].append({"type": "required_linear_history"})
    ln = _github(tmp_path, _protected(tmp_path), rulesets=[rs])["github.linear_history"]
    assert ln["status"] == "gap"


def test_required_approvals_above_0_are_a_note_naming_ready_for_review(tmp_path):
    rs = _rs()
    _rule(rs, "pull_request")["parameters"]["required_approving_review_count"] = 1
    root = _protected(tmp_path)
    ln = _github(tmp_path, root, rulesets=[rs])["github.approvals"]
    assert ln["status"] == "note" and "ready for review" in ln["message"]
    assert _doctor(tmp_path, root, *_files(tmp_path, rulesets=[rs]), "--strict").returncode == 0


def test_a_ruleset_on_another_branch_doesnt_count_for_the_other_lines(tmp_path):
    other = _rs(id=102, name="Release", conditions={"ref_name": {"include": ["refs/heads/release"], "exclude": []}})
    other["rules"].append({"type": "required_linear_history"})
    lines = _github(tmp_path, _protected(tmp_path), rulesets=[RULESET, other])
    assert lines["github.linear_history"]["status"] == "fine"
    assert lines["github.ruleset"]["status"] == "fine"


# Merge settings


def test_merge_commits_off_is_a_gap(tmp_path):
    ln = _github(tmp_path, _protected(tmp_path), settings={**SETTINGS, "allow_merge_commit": False})["github.merge_commits"]
    assert ln["status"] == "gap"


def test_a_merge_setting_that_cant_be_read_is_cant_check(tmp_path):
    settings = {k: v for k, v in SETTINGS.items() if k != "allow_auto_merge"}
    ln = _github(tmp_path, _protected(tmp_path), settings=settings)["github.auto_merge"]
    assert ln["status"] == "cant_check"


# CODEOWNERS


def test_codeowners_missing_altogether_is_a_gap(tmp_path):
    ln = _github(tmp_path, _protected(tmp_path, codeowners=None))["github.codeowners"]
    assert ln["status"] == "gap"


@pytest.mark.parametrize("text, missing", [
    ("/.claude/ @someone\n", "/.github/workflows/"),
    ("/.github/workflows/ @someone\n", "/.claude/"),
    ("/.claude/ @someone\n/.github/workflows/ @someone\n/.claude/\n", "/.claude/"),  # the last match has no owner
    ("/.claude/*.json @someone\n/.github/workflows/ @someone\n", "/.claude/"),  # only some of its files
])
def test_codeowners_missing_either_path_is_a_gap_naming_it(tmp_path, text, missing):
    ln = _github(tmp_path, _protected(tmp_path, codeowners=text))["github.codeowners"]
    assert ln["status"] == "gap" and missing in ln["message"], ln


@pytest.mark.parametrize("where, text", [
    (".github/CODEOWNERS", "* @someone\n"),
    ("CODEOWNERS", "/.claude/** @someone\n.github/workflows/ @a @b\n"),
    ("docs/CODEOWNERS", "# owners\n.claude/ someone@example.com\n/.github/ @someone\n"),
])
def test_codeowners_in_any_place_github_reads_covering_both_is_fine(tmp_path, where, text):
    root = _protected(tmp_path, codeowners=None)
    (root / where).parent.mkdir(parents=True, exist_ok=True)
    (root / where).write_text(text)
    assert _github(tmp_path, root)["github.codeowners"]["status"] == "fine"


def test_codeowners_is_read_from_the_first_place_github_looks(tmp_path):
    # .github/CODEOWNERS wins, so a full root CODEOWNERS doesn't make up for it.
    root = _protected(tmp_path, codeowners="/.claude/ @someone\n")
    (root / "CODEOWNERS").write_text(CODEOWNERS)
    ln = _github(tmp_path, root)["github.codeowners"]
    assert ln["status"] == "gap" and "/.github/workflows/" in ln["message"]


def test_a_codeowners_that_isnt_a_file_is_a_gap_never_a_hang(tmp_path):
    import os

    root = _protected(tmp_path, codeowners=None)
    (root / ".github").mkdir()
    os.mkfifo(root / ".github/CODEOWNERS")
    ln = _github(tmp_path, root)["github.codeowners"]
    assert ln["status"] == "gap"


# A file wins; without one, gh; without gh, can't check


def test_a_file_wins_over_gh(tmp_path):
    import fake_gh

    root = _protected(tmp_path)
    path = _bin(tmp_path, gh=gh_routes(rulesets=[]))  # gh would say unprotected
    lines = _github(tmp_path, root, path=path)
    assert lines["github.ruleset"]["status"] == "fine"
    assert not any("rulesets" in p or p.split("?")[0] == "repos/acme/demo" for p in fake_gh.FakeGh(path).paths())


def test_one_file_given_and_the_other_read_with_gh(tmp_path):
    import fake_gh

    root = _protected(tmp_path)
    path = _bin(tmp_path, gh=gh_routes(settings={**SETTINGS, "allow_merge_commit": False}))
    r = _report(tmp_path, root, *_files(tmp_path, settings=None), path=path)
    lines = {ln["id"]: ln for ln in r["lines"]}
    assert lines["github.ruleset"]["status"] == "fine" and lines["github.merge_commits"]["status"] == "gap"
    paths = [p.split("?")[0] for p in fake_gh.FakeGh(path).paths()]
    assert "repos/acme/demo" in paths and not any("rulesets" in p for p in paths)


@pytest.mark.parametrize("gh, words", [(False, "isn't installed"), ("signed_out", "sign")])
def test_without_gh_or_signed_out_each_line_needing_github_is_cant_check(tmp_path, gh, words):
    import fake_gh

    root = _protected(tmp_path)
    path = _bin(tmp_path, gh=False)
    if gh == "signed_out":
        fake_gh.write(path, gh_routes(), signed_in=False)
    r = _report(tmp_path, root, path=path)
    lines = {ln["id"]: ln for ln in r["lines"] if ln["group"] == "GitHub"}
    for id_ in NEEDS_GITHUB:
        if id_ == "github.required_checks":
            continue  # it lists checks, so it needs GitHub too: below
        assert lines[id_]["status"] == "cant_check", lines[id_]
        assert "sign in with `gh`" in lines[id_]["fix"].lower() or "gh auth login" in lines[id_]["fix"], lines[id_]["fix"]
        assert "cloud session" in lines[id_]["fix"]
    assert lines["github.required_checks"]["status"] == "cant_check"
    assert words in lines["github.ruleset"]["message"], lines["github.ruleset"]["message"]
    assert lines["github.codeowners"]["status"] == "fine"  # read from the checkout
    assert _doctor(tmp_path, root, "--strict", path=path).returncode == 1


def test_without_gh_checks_not_required_yet_is_still_a_note(tmp_path):
    root = _project(tmp_path)
    lines = _lines(_report(tmp_path, root, path=_bin(tmp_path, gh=False)))
    assert lines["github.required_checks"]["status"] == "note"


def test_gh_failing_says_why_in_the_developer_wording(tmp_path):
    import fake_gh

    root = _protected(tmp_path)
    routes = gh_routes()
    routes["repos/acme/demo/rulesets"] = fake_gh.reply(exit=1, stderr="gh: Resource not accessible by integration (HTTP 403)")
    lines = _lines(_report(tmp_path, root, path=_bin(tmp_path, gh=routes), env={"WORKFLOW_EXPERIENCE": "developer"}))
    assert lines["github.ruleset"]["status"] == "cant_check" and "HTTP 403" in lines["github.ruleset"]["message"]
    assert lines["github.merge_commits"]["status"] == "fine"  # the settings still read


@pytest.mark.parametrize("rulesets, settings, id_, words", [
    ("{not json", SETTINGS, "github.ruleset", "isn't valid JSON"),
    ('{"a": 1}', SETTINGS, "github.ruleset", "list"),
    ([{"id": 1, "name": "summary only"}], SETTINGS, "github.ruleset", "in full"),
    ([RULESET], "[]", "github.merge_commits", "object"),
])
def test_a_file_that_isnt_what_github_returns_is_cant_check_saying_so(tmp_path, rulesets, settings, id_, words):
    root = _protected(tmp_path)
    ln = _github(tmp_path, root, rulesets, settings, env={"WORKFLOW_EXPERIENCE": "developer"})[id_]
    assert ln["status"] == "cant_check" and words in ln["message"], ln


def test_a_rulesets_file_that_is_missing_is_cant_check_naming_it(tmp_path):
    root = _protected(tmp_path)
    r = _report(tmp_path, root, "--rulesets", str(tmp_path / "nowhere.json"), path=_bin(tmp_path, gh=False))
    ln = _lines(r)["github.ruleset"]
    assert ln["status"] == "cant_check" and "nowhere.json" in ln["message"]


def test_no_profile_makes_the_github_lines_wait_on_it(tmp_path):
    root = _project(tmp_path, profile=None)
    lines = _lines(_report(tmp_path, root))
    assert lines["github.ruleset"]["status"] == "cant_check"
    assert "profile" in lines["github.ruleset"]["fix"]
    assert lines["github.codeowners"]["status"] == "fine"


# Wording, and changing nothing


def _states(tmp_path):
    """Projects and inputs whose GitHub lines take every status between them."""
    rs = _rs(bypass_actors=[{"actor_id": 5}], enforcement="active")
    rs = _without(rs, "deletion")
    rs = _without(rs, "non_fast_forward")
    rs = _without(rs, "pull_request")
    rs["rules"].append({"type": "required_linear_history"})
    rs["rules"].append({"type": "pull_request", "parameters": {"required_approving_review_count": 2, "require_code_owner_review": True}})
    _rule(rs, "required_status_checks")["parameters"]["strict_required_status_checks_policy"] = False
    off = _rs(id=102, name="Off", enforcement="disabled")
    elsewhere = _rs(id=103, name="Elsewhere", conditions={"ref_name": {"include": ["refs/heads/x"], "exclude": []}})
    yield _protected(tmp_path / "a", profile=_prof("ruleset = true\n", '[ci]\nrequired_checks = ["tests", "lint"]\n'), codeowners="/.claude/ @a\n"), \
        _files(tmp_path / "a", rulesets=[rs, off, elsewhere], settings={**SETTINGS, "allow_merge_commit": False, "allow_auto_merge": False}), None
    yield _project(tmp_path / "b", profile=SOLO, codeowners=None), _files(tmp_path / "b", rulesets=[], settings={**SETTINGS, "allow_auto_merge": False}), None
    yield _project(tmp_path / "c", profile=_prof("")), _files(tmp_path / "c", rulesets=[], settings={"full_name": "acme/demo", "default_branch": "main"}), None
    yield _protected(tmp_path / "d"), [], _bin(tmp_path / "d", gh=False)
    yield _project(tmp_path / "e"), _files(tmp_path / "e"), None
    yield _project(tmp_path / "f", profile=SOLO), _files(tmp_path / "f"), None
    yield _project(tmp_path / "g", profile=None), [], None
    yield _protected(tmp_path / "h"), _files(tmp_path / "h", rulesets=[_without(_rs(), "required_status_checks")]), None
    yield _protected(tmp_path / "i"), _files(tmp_path / "i"), None
    yield _protected(tmp_path / "j"), _files(tmp_path / "j", rulesets=[_without(_rs(), "pull_request")]), None


def test_each_github_wording_for_new_and_developer_with_the_same_statuses(tmp_path):
    seen = set()
    for root, args, path in _states(tmp_path):
        n = _lines(_report(tmp_path, root, *args, path=path, env={"WORKFLOW_EXPERIENCE": "new"}))
        d = _lines(_report(tmp_path, root, *args, path=path, env={"WORKFLOW_EXPERIENCE": "developer"}))
        assert set(n) == set(d)
        for id_ in n:
            if not id_.startswith("github."):
                continue
            seen.add((id_, n[id_]["status"]))
            assert (n[id_]["status"], n[id_]["offer"]) == (d[id_]["status"], d[id_]["offer"]), id_
            assert n[id_]["message"] != d[id_]["message"], (id_, n[id_]["message"])
            if n[id_]["fix"] or d[id_]["fix"]:
                assert n[id_]["fix"] != d[id_]["fix"], (id_, n[id_]["fix"])
    for id_ in GITHUB_IDS:
        assert (id_, "fine") in seen, id_
    for want in [("github.ruleset", s) for s in ("gap", "note", "cant_check", "fine")] + [
        ("github.protection.active", "gap"), ("github.protection.base", "gap"), ("github.protection.bypass", "gap"),
        ("github.protection.deletions", "gap"), ("github.protection.force_pushes", "gap"), ("github.protection.pull_requests", "gap"),
        ("github.required_checks", "gap"), ("github.required_checks", "note"), ("github.required_checks", "cant_check"),
        ("github.up_to_date", "gap"), ("github.up_to_date", "note"), ("github.approvals", "note"), ("github.code_owner_review", "gap"),
        ("github.linear_history", "gap"), ("github.merge_commits", "gap"), ("github.merge_commits", "cant_check"),
        ("github.auto_merge", "gap"), ("github.auto_merge", "note"), ("github.auto_merge", "cant_check"),
        ("github.codeowners", "gap"),
    ]:
        assert want in seen, want


def test_nothing_in_the_checkout_changes_after_a_run(tmp_path):
    for root, args, path in _states(tmp_path):
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        before = _snapshot(root)
        for extra in ((), ("--json",), ("--strict",)):
            _doctor(tmp_path, root, *args, *extra, path=path)
            _doctor(tmp_path, root, *extra)  # through the fake gh
        assert _snapshot(root) == before, root


# Docs


def test_the_changelog_has_a_note_under_unreleased():
    notes = since_0110()
    assert "#59" in notes and "restore_protection" in notes


def test_the_help_names_the_files():
    from test_doctor import CLI
    import sys

    p = subprocess.run([sys.executable, "-B", str(CLI), "doctor", "--help"], capture_output=True, text=True)
    assert "--rulesets" in p.stdout and "--repo" in p.stdout
