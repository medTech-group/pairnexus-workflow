"""`workflow protection`: whether the base branch is protected, read back from
the rulesets (and the repository's settings) as JSON files a session hands it.

Fed recorded JSON, as `status --issues` is (#44, seam 3 of #32). The shapes
are GitHub's (GET repos/<repo>/rulesets/<id>, GET repos/<repo>), made up.
"""

import copy
import json
import os
import subprocess
import sys

import pytest

from conftest import git
from test_hooks_cli import CLI


def _ruleset(**over):
    rs = {
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
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": 0,
                    "dismiss_stale_reviews_on_push": False,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_review_thread_resolution": False,
                },
            },
        ],
    }
    rs.update(over)
    return rs


def _checks_rule(*names):
    return {
        "type": "required_status_checks",
        "parameters": {"strict_required_status_checks_policy": False, "required_status_checks": [{"context": n} for n in names]},
    }


@pytest.fixture
def inp(tmp_path_factory):
    """Where the JSON files go: outside the project, so a run's tree is only its own."""
    return tmp_path_factory.mktemp("input")


SETTINGS = {"full_name": "acme/demo", "default_branch": "main", "allow_merge_commit": True, "allow_auto_merge": True, "allow_squash_merge": True}


NO_SETTINGS = None


def run(repo, inp, rulesets, *extra, settings=SETTINGS, raw=None):
    """The command on these rulesets, with the settings file unless `settings=NO_SETTINGS`."""
    path = inp / "rulesets.json"
    path.write_text(raw if raw is not None else json.dumps(rulesets))
    args = [sys.executable, str(CLI), "protection", "--rulesets", str(path), *extra]
    if settings is not None:
        (inp / "repo.json").write_text(settings if isinstance(settings, str) else json.dumps(settings))
        args += ["--repo", str(inp / "repo.json")]
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo)}
    return subprocess.run(args, cwd=repo, env=env, capture_output=True, text=True)


def verdict(repo, inp, rulesets, **kw):
    p = run(repo, inp, rulesets, "--json", **kw)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


# ---------- protected ----------


@pytest.mark.parametrize("ref", ["~DEFAULT_BRANCH", "refs/heads/main"])
def test_a_complete_active_ruleset_reads_as_protected(repo, inp, ref):
    rs = _ruleset(conditions={"ref_name": {"include": [ref], "exclude": []}}, rules=_ruleset()["rules"] + [_checks_rule("tests")])
    out = verdict(repo, inp, [rs])
    assert out["protected"] is True
    assert out["missing"] == []
    assert out["base_branch"] == "main"
    assert out["checks"]["required"] == ["tests"] and out["checks"]["note"] is None
    p = run(repo, inp, [rs])
    assert p.returncode == 0 and p.stdout.splitlines()[0] == "main is protected."


def test_the_rules_may_come_from_two_rulesets(repo, inp):
    a = _ruleset(id=1, name="No force", rules=[{"type": "deletion"}, {"type": "non_fast_forward"}])
    b = _ruleset(id=2, name="PRs", rules=[_ruleset()["rules"][2]])
    assert verdict(repo, inp, [a, b])["protected"] is True


def test_pages_from_gh_slurp_are_read_as_one_list(repo, inp):
    assert verdict(repo, inp, [[_ruleset()], []])["protected"] is True


def test_base_branch_option_overrides_the_profile(repo, inp):
    rs = _ruleset(conditions={"ref_name": {"include": ["refs/heads/trunk"], "exclude": []}})
    assert verdict(repo, inp, [rs])["protected"] is False
    p = run(repo, inp, [rs], "--base", "trunk", "--json")
    out = json.loads(p.stdout)
    assert out["protected"] is True and out["base_branch"] == "trunk"


# ---------- checks not required yet ----------


def test_no_required_checks_says_checks_not_required_yet_and_is_still_protected(repo, inp):
    out = verdict(repo, inp, [_ruleset()])
    assert out["protected"] is True
    assert out["checks"]["required"] == []
    assert out["checks"]["note"] == "checks not required yet"
    p = run(repo, inp, [_ruleset()])
    assert p.stdout.splitlines()[0] == "main is protected." and "checks not required yet" in p.stdout.lower()


def test_an_empty_required_checks_list_is_not_required_checks(repo, inp):
    rs = _ruleset(rules=_ruleset()["rules"] + [_checks_rule()])
    assert verdict(repo, inp, [rs])["checks"]["note"] == "checks not required yet"


# ---------- each missing protection ----------


def _missing(repo, inp, rulesets, **kw):
    out = verdict(repo, inp, rulesets, **kw)
    assert out["protected"] is False
    p = run(repo, inp, rulesets, **kw)
    assert p.returncode == 0, p.stderr
    assert p.stdout.splitlines()[0] == "main is not protected:"
    for line in out["missing"]:
        assert f"- {line}" in p.stdout.splitlines(), (line, p.stdout)
    return out["missing"]


@pytest.mark.parametrize(
    "enforcement, words",
    [("disabled", "not active"), ("evaluate", "evaluate only")],
)
def test_a_ruleset_not_active_is_not_protection(repo, inp, enforcement, words):
    missing = _missing(repo, inp, [_ruleset(enforcement=enforcement)])
    assert any("Protect main" in m and words in m for m in missing), missing
    assert any("deletions allowed" in m for m in missing)
    assert any("force pushes allowed" in m for m in missing)
    assert any("pull requests not required" in m for m in missing)


def test_a_ruleset_on_another_branch_is_not_protection(repo, inp):
    rs = _ruleset(conditions={"ref_name": {"include": ["refs/heads/develop"], "exclude": []}})
    missing = _missing(repo, inp, [rs])
    assert any("Protect main" in m and "doesn't target main" in m for m in missing), missing


def test_an_exclude_of_the_base_branch_wins(repo, inp):
    rs = _ruleset(conditions={"ref_name": {"include": ["~ALL"], "exclude": ["refs/heads/ma*"]}})
    missing = _missing(repo, inp, [rs])
    assert any("doesn't target main" in m for m in missing), missing


def test_all_branches_targets_the_base_branch(repo, inp):
    rs = _ruleset(conditions={"ref_name": {"include": ["~ALL"], "exclude": []}})
    assert verdict(repo, inp, [rs])["protected"] is True


def test_default_branch_does_not_target_a_base_branch_that_is_not_the_default(repo, inp):
    settings = {**SETTINGS, "default_branch": "develop"}
    missing = _missing(repo, inp, [_ruleset()], settings=settings)
    assert any("doesn't target main" in m for m in missing), missing


def test_a_tag_ruleset_is_not_branch_protection(repo, inp):
    missing = _missing(repo, inp, [_ruleset(target="tag")])
    assert any("doesn't target main" in m for m in missing), missing


def test_a_bypass_list_is_not_protection(repo, inp):
    rs = _ruleset(bypass_actors=[{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}])
    missing = _missing(repo, inp, [rs])
    assert missing == [m for m in missing if "bypass list" in m] and len(missing) == 1, missing


def test_a_bypass_list_that_cannot_be_read_is_not_protection(repo, inp):
    rs = _ruleset()
    del rs["bypass_actors"]
    missing = _missing(repo, inp, [rs])
    assert any("bypass list" in m and "can't be read" in m for m in missing), missing


@pytest.mark.parametrize(
    "rule, words",
    [("deletion", "deletions allowed"), ("non_fast_forward", "force pushes allowed"), ("pull_request", "pull requests not required")],
)
def test_each_missing_rule_is_its_own_line(repo, inp, rule, words):
    rs = _ruleset(rules=[r for r in _ruleset()["rules"] if r["type"] != rule])
    missing = _missing(repo, inp, [rs])
    assert len(missing) == 1 and words in missing[0], missing


def test_several_missing_protections_each_get_a_line(repo, inp):
    rs = _ruleset(bypass_actors=[{"actor_id": 1, "actor_type": "OrganizationAdmin", "bypass_mode": "always"}], rules=[{"type": "deletion"}])
    missing = _missing(repo, inp, [rs])
    assert len(missing) == 3, missing
    assert any("bypass list" in m for m in missing)
    assert any("force pushes allowed" in m for m in missing)
    assert any("pull requests not required" in m for m in missing)


def test_no_rulesets_reads_as_not_protected(repo, inp):
    missing = _missing(repo, inp, [])
    assert len(missing) == 1 and "no rulesets" in missing[0]


# ---------- malformed input ----------


@pytest.mark.parametrize(
    "raw",
    [
        "not json {",
        "",
        json.dumps({"rulesets": []}),
        json.dumps("protected"),
        json.dumps([1, 2]),
        json.dumps([{"id": 1, "name": "Protect main", "enforcement": "active"}]),  # a list summary: no rules
        json.dumps([{**_ruleset(), "rules": {"type": "deletion"}}]),
        json.dumps([{**_ruleset(), "rules": [{"kind": "deletion"}]}]),
        json.dumps([{**_ruleset(), "enforcement": 1}]),
        json.dumps([{k: v for k, v in _ruleset().items() if k != "target"}]),
        json.dumps([[_ruleset()], _ruleset()]),
        json.dumps([{**_ruleset(), "rules": [{"type": "required_status_checks", "parameters": ["tests"]}]}]),
        json.dumps([{**_ruleset(), "rules": [_checks_rule("tests") | {"parameters": {"required_status_checks": "tests"}}]}]),
        json.dumps([{**_ruleset(), "bypass_actors": "none"}]),
        json.dumps([{**_ruleset(), "conditions": {"ref_name": {"include": "~DEFAULT_BRANCH"}}}]),
    ],
)
def test_malformed_rulesets_are_an_error_never_protected(repo, inp, raw):
    for extra in ((), ("--json",)):
        p = run(repo, inp, None, *extra, raw=raw)
        assert p.returncode != 0
        assert p.stdout == ""
        assert p.stderr.startswith("workflow protection: "), p.stderr
        assert "Traceback" not in p.stderr


@pytest.mark.parametrize("settings", ["{nope", json.dumps([SETTINGS]), json.dumps({**SETTINGS, "allow_merge_commit": "yes"})])
def test_malformed_settings_are_an_error(repo, inp, settings):
    p = run(repo, inp, [_ruleset()], "--json", settings=settings)
    assert p.returncode != 0 and p.stdout == ""
    assert p.stderr.startswith("workflow protection: ") and "Traceback" not in p.stderr


def test_deeply_nested_json_is_a_plain_error(repo, inp):
    p = run(repo, inp, None, raw="[" * 100000 + "]" * 100000)
    assert p.returncode == 2 and p.stdout == ""
    assert p.stderr.startswith("workflow protection: ") and "Traceback" not in p.stderr


@pytest.mark.parametrize("raw", ['[{"id": ' + "1" * 5000 + "}]", '[{"name": "\\ud800"}]', "\udcff".encode("utf-8", "surrogateescape").decode("latin-1")])
def test_odd_numbers_and_characters_are_a_plain_error(repo, inp, raw):
    p = run(repo, inp, None, raw=raw)
    assert p.returncode == 2 and p.stdout == "" and "Traceback" not in p.stderr


def test_a_lone_surrogate_in_a_name_is_printed_escaped(repo, inp):
    p = run(repo, inp, None, raw=json.dumps([_ruleset(name="\ud800", enforcement="disabled")]))
    assert p.returncode == 0, p.stderr
    assert '"\\ud800"' in p.stdout


def test_an_include_pattern_cannot_be_told(repo, inp):
    rs = _ruleset(conditions={"ref_name": {"include": ["refs/heads/*"], "exclude": []}})
    missing = _missing(repo, inp, [rs])
    assert any("can't tell" in m and '"refs/heads/*"' in m for m in missing), missing


def test_a_disabled_ruleset_on_another_branch_says_it_targets_another_branch(repo, inp):
    rs = _ruleset(name="Protect develop", enforcement="disabled", conditions={"ref_name": {"include": ["refs/heads/develop"], "exclude": []}})
    missing = _missing(repo, inp, [rs, _ruleset(id=2, rules=[{"type": "deletion"}])])
    assert 'ruleset "Protect develop" doesn\'t target main' in missing, missing


def test_the_reason_reads_as_a_sentence_when_settings_lack_the_default_branch(repo, inp):
    settings = {k: v for k, v in SETTINGS.items() if k != "default_branch"}
    missing = _missing(repo, inp, [_ruleset()], settings=settings)
    assert any("has no default_branch, so it can't tell whether that is main" in m for m in missing), missing


def test_excludes_match_without_folding_too(repo, inp):
    rs = _ruleset(conditions={"ref_name": {"include": ["refs/heads/\u00df"], "exclude": ["refs/heads/?"]}})
    p = run(repo, inp, [rs], "--base", "\u00df", "--json")
    assert json.loads(p.stdout)["protected"] is False


def test_a_missing_file_is_a_plain_error(repo, inp):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo)}
    p = subprocess.run([sys.executable, str(CLI), "protection", "--rulesets", str(inp / "nope.json")], cwd=repo, env=env, capture_output=True, text=True)
    assert p.returncode != 0 and "Traceback" not in p.stderr and "nope.json" in p.stderr


# ---------- merge settings ----------


def test_merge_settings_are_reported(repo, inp):
    out = verdict(repo, inp, [_ruleset()], settings=SETTINGS)
    assert out["merge"] == {"merge_commits": True, "auto_merge": True, "missing": []}
    p = run(repo, inp, [_ruleset()], settings=SETTINGS)
    assert "merge commits allowed" in p.stdout and "auto-merge allowed" in p.stdout


@pytest.mark.parametrize(
    "over, words",
    [
        ({"allow_merge_commit": False}, "merge commits not allowed"),
        ({"allow_auto_merge": False}, "auto-merge not allowed"),
    ],
)
def test_each_missing_merge_setting_in_plain_words(repo, inp, over, words):
    out = verdict(repo, inp, [_ruleset()], settings={**SETTINGS, **over})
    assert out["protected"] is True  # merge settings are reported beside the verdict
    assert len(out["merge"]["missing"]) == 1 and words in out["merge"]["missing"][0]
    p = run(repo, inp, [_ruleset()], settings={**SETTINGS, **over})
    assert words in p.stdout


def test_a_merge_setting_not_in_the_file_is_unknown_not_allowed(repo, inp):
    settings = {k: v for k, v in SETTINGS.items() if k != "allow_auto_merge"}
    out = verdict(repo, inp, [_ruleset()], settings=settings)
    assert out["merge"]["auto_merge"] is None
    assert any("auto-merge" in m and "can't be read" in m for m in out["merge"]["missing"])


def test_without_the_settings_file_merge_settings_are_not_reported(repo, inp):
    rs = _ruleset(conditions={"ref_name": {"include": ["refs/heads/main"], "exclude": []}})
    out = verdict(repo, inp, [rs], settings=NO_SETTINGS)
    assert out["merge"] is None and out["protected"] is True
    assert "merge commits" not in run(repo, inp, [rs], settings=NO_SETTINGS).stdout.lower()


@pytest.mark.parametrize("settings", [NO_SETTINGS, {k: v for k, v in SETTINGS.items() if k != "default_branch"}])
def test_default_branch_unknown_is_not_protected(repo, inp, settings):
    missing = _missing(repo, inp, [_ruleset()], settings=settings)
    why = "--repo" if settings is NO_SETTINGS else "no default_branch"
    assert any("default branch" in m and why in m for m in missing), missing
    p = run(repo, inp, [_ruleset()], "--base", "develop", "--json", settings=settings)
    assert json.loads(p.stdout)["protected"] is False


def test_null_settings_are_an_error_not_no_settings(repo, inp):
    p = run(repo, inp, [_ruleset()], "--json", settings="null")
    assert p.returncode == 2 and p.stdout == "" and "JSON object" in p.stderr


def test_merge_settings_line_says_each_state(repo, inp):
    settings = {k: v for k, v in SETTINGS.items() if k != "allow_auto_merge"} | {"allow_merge_commit": False}
    p = run(repo, inp, [_ruleset()], settings=settings)
    assert "Merge settings: merge commits not allowed, auto-merge unknown." in p.stdout.splitlines()


# ---------- --json carries the same ----------


def test_json_and_text_carry_the_same_report(repo, inp):
    rs = _ruleset(enforcement="evaluate", rules=[{"type": "deletion"}])
    settings = {**SETTINGS, "allow_auto_merge": False}
    out = verdict(repo, inp, [rs], settings=settings)
    assert set(out) >= {"base_branch", "protected", "missing", "checks", "merge"}
    text = run(repo, inp, [rs], settings=settings).stdout
    for line in out["missing"] + out["merge"]["missing"]:
        assert line in text
    assert out["checks"]["note"] in text.lower()


# ---------- writes nothing ----------


def test_it_writes_nothing(repo, inp):
    before = git(repo, "status", "--porcelain", "--ignored")
    files = sorted(p.relative_to(repo) for p in repo.rglob("*") if ".git" not in p.parts)
    for rulesets in ([_ruleset()], [], [_ruleset(enforcement="disabled")]):
        run(repo, inp, rulesets, settings=SETTINGS)
        run(repo, inp, rulesets, "--json", settings=SETTINGS)
    run(repo, inp, None, raw="not json")
    assert git(repo, "status", "--porcelain", "--ignored") == before
    assert sorted(p.relative_to(repo) for p in repo.rglob("*") if ".git" not in p.parts) == files


def test_it_needs_no_profile_given_the_base_branch(tmp_path):
    (tmp_path / "rulesets.json").write_text(json.dumps([_ruleset(conditions={"ref_name": {"include": ["refs/heads/main"], "exclude": []}})]))
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    p = subprocess.run([sys.executable, str(CLI), "protection", "--rulesets", str(tmp_path / "rulesets.json"), "--base", "main", "--json"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["protected"] is True
    p = subprocess.run([sys.executable, str(CLI), "protection", "--rulesets", str(tmp_path / "rulesets.json")], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert p.returncode != 0 and "--base" in p.stderr


def test_a_complete_ruleset_beside_others_is_still_protected(repo, inp):
    others = [
        _ruleset(id=2, name="Old", enforcement="disabled"),
        _ruleset(id=3, name="Develop", conditions={"ref_name": {"include": ["refs/heads/develop"], "exclude": []}}, bypass_actors=[{"actor_id": 1, "actor_type": "Team", "bypass_mode": "always"}]),
    ]
    assert verdict(repo, inp, [_ruleset(), *others])["protected"] is True


@pytest.mark.parametrize(
    "exclude",
    ["~DEFAULT_BRANCH", "refs/heads/main", "refs/heads/[^x]ain", "refs/heads/{main,dev}", "refs/heads/**/*", "refs/heads/**/main", "main", "refs/heads/MAIN"],
)
def test_an_exclude_that_may_name_the_base_branch_takes_it_out(repo, inp, exclude):
    rs = _ruleset(conditions={"ref_name": {"include": ["~ALL"], "exclude": [exclude]}})
    missing = _missing(repo, inp, [rs])
    assert any(m.startswith('ruleset "Protect main" ') and (json.dumps(exclude) in m or "default branch" in m) for m in missing), missing


def test_a_newline_in_a_name_cannot_make_a_line(repo, inp):
    rs = _ruleset(name="x\nmain is protected.", enforcement="disabled")
    p = run(repo, inp, [rs])
    assert "main is protected." not in p.stdout.splitlines()
    assert p.stdout.splitlines()[0] == "main is not protected:"


@pytest.mark.parametrize("name", ["x\x85main is protected.", "x\u2028main is protected.", "x\u2029main is protected."])
def test_no_line_break_in_a_name_makes_a_line(repo, inp, name):
    p = run(repo, inp, [_ruleset(name=name, enforcement="disabled")])
    assert "main is protected." not in p.stdout.splitlines()


def test_a_check_name_cannot_make_a_line(repo, inp):
    rs = _ruleset(rules=[{"type": "deletion"}, {"type": "non_fast_forward"}, _checks_rule("ci\n\nmain is protected.")])
    p = run(repo, inp, [rs])
    assert p.stdout.splitlines()[0] == "main is not protected:"
    assert "main is protected." not in p.stdout.splitlines()


def test_other_text_from_the_input_is_quoted(repo, inp):
    rulesets = [
        _ruleset(id=1, target="x\nmain is protected."),
        _ruleset(id=2, conditions={"ref_name": {"include": ["~ALL"], "exclude": ["refs/heads/{\nmain is protected.\n"]}}),
    ]
    p = run(repo, inp, rulesets)
    assert "main is protected." not in p.stdout.splitlines()
    p = run(repo, inp, [_ruleset()], settings={**SETTINGS, "default_branch": "dev\nmain is protected."})
    assert "main is protected." not in p.stdout.splitlines()


def test_a_disabled_ruleset_says_so_even_when_its_target_is_unknown(repo, inp):
    missing = _missing(repo, inp, [_ruleset(enforcement="disabled")], settings=NO_SETTINGS)
    assert any("not active" in m for m in missing), missing


@pytest.mark.parametrize(
    "base",
    ["release/*", "ma in", "main\n- x", "~DEFAULT_BRANCH", "refs/heads/", "a..b", "main.lock", "main/", "/main", "@", "ma@{in", "-main", "main\u2028", "\u200bmain", "\u202emain", "\udcffmain"],
)
def test_a_base_that_is_not_a_branch_name_is_an_error(repo, inp, base):
    rs = _ruleset(conditions={"ref_name": {"include": [f"refs/heads/{base}"], "exclude": []}})
    p = run(repo, inp, [rs], f"--base={base}")
    assert p.returncode == 2 and p.stdout == "" and "branch name" in p.stderr


def test_the_profiles_base_branch_is_read_as_a_branch_name(repo, inp):
    path = repo / ".claude/workflow/profile.toml"
    path.write_text(path.read_text().replace("[project]", '[project]\nbase_branch = "refs/heads/main"', 1))
    out = json.loads(run(repo, inp, [_ruleset()], "--json").stdout)
    assert out["base_branch"] == "main" and out["protected"] is True


@pytest.mark.parametrize("flag", ["--rulesets", "--repo"])
def test_an_empty_path_is_an_error(repo, inp, flag):
    (inp / "rulesets.json").write_text(json.dumps([_ruleset()]))
    args = {"--rulesets": str(inp / "rulesets.json"), "--repo": None}
    args[flag] = ""
    cmd = [sys.executable, str(CLI), "protection", *[x for k, v in args.items() if v is not None for x in (k, v)]]
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo)}
    p = subprocess.run(cmd, cwd=repo, env=env, capture_output=True, text=True)
    assert p.returncode == 2 and p.stdout == "" and "no path" in p.stderr


def test_closed_standard_input_is_a_plain_error(repo, inp):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo)}
    p = subprocess.run(
        ["sh", "-c", f'"{sys.executable}" "{CLI}" protection --rulesets - --base main <&-'],
        cwd=repo, env=env, capture_output=True, text=True,
    )
    assert p.returncode == 2 and "Traceback" not in p.stderr and "closed" in p.stderr


def test_rulesets_from_standard_input(repo, inp):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo)}
    (inp / "repo.json").write_text(json.dumps(SETTINGS))
    p = subprocess.run([sys.executable, str(CLI), "protection", "--rulesets", "-", "--repo", str(inp / "repo.json"), "--json"], cwd=repo, env=env, input=json.dumps([_ruleset()]), capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["protected"] is True
    p = subprocess.run([sys.executable, str(CLI), "protection", "--rulesets", "-", "--repo", "-"], cwd=repo, env=env, input="[]", capture_output=True, text=True)
    assert p.returncode == 2 and "standard input" in p.stderr


def test_base_option_takes_a_full_ref_and_refuses_an_empty_one(repo, inp):
    assert json.loads(run(repo, inp, [_ruleset()], "--base", "refs/heads/main", "--json").stdout)["base_branch"] == "main"
    p = run(repo, inp, [_ruleset()], "--base", " ")
    assert p.returncode == 2 and "--base" in p.stderr


def test_a_broken_profile_is_a_plain_error(repo, inp):
    (repo / ".claude/workflow/profile.toml").write_text("[project\n")
    p = run(repo, inp, [_ruleset()])
    assert p.returncode == 2 and p.stderr.startswith("workflow protection: ") and "--base" in p.stderr
    assert run(repo, inp, [_ruleset()], "--base", "main").returncode == 0


def test_a_byte_order_mark_is_read(repo, inp):
    p = run(repo, inp, None, "--json", raw="\ufeff" + json.dumps([_ruleset()]))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["protected"] is True


def test_the_input_is_not_changed(repo, inp):
    rs = [_ruleset()]
    keep = copy.deepcopy(rs)
    run(repo, inp, rs)
    assert json.loads((inp / "rulesets.json").read_text()) == keep
