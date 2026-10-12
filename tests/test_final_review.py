"""The final correctness pass after review round 3, each finding pinned.

Every command here is data passed to `decide`; none is run.
"""

import json

import pytest
from conftest import BASE_PROFILE

from workflow import gate
from workflow.guard import decide
from workflow.issues import blockers_of, readiness
from workflow.profile import parse


def act(profile, root, cmd, role="ticket", branch="claude/build-1"):
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}}
    return decide(ev, profile, role, root, branch, role_from_env=True).action


@pytest.fixture
def deploy_profile(tmp_path):
    data = json.loads(json.dumps(BASE_PROFILE))
    data["guard"]["deploy_commands"] = ["scripts/deploy.sh"]
    return parse(data, tmp_path)


# ---------- 1. a deploy script run with `.` ----------


@pytest.mark.parametrize("cmd", [". scripts/deploy.sh poc", "cd scripts && . ./deploy.sh", "source scripts/deploy.sh"])
def test_dot_runs_a_deploy_script(cmd, deploy_profile, tmp_path):
    (tmp_path / "scripts").mkdir()
    assert act(deploy_profile, tmp_path, cmd) == "deny", cmd
    assert act(deploy_profile, tmp_path, cmd, role="attended", branch="main") == "ask", cmd


def test_dot_running_another_script_is_fine(deploy_profile, tmp_path):
    assert act(deploy_profile, tmp_path, ". .venv/bin/activate") == "allow"


# ---------- 2. the default branch through `--input -` from a file or a pipe ----------


def test_default_branch_on_stdin_from_a_file_or_pipe(profile, tmp_path):
    (tmp_path / "db.json").write_text('{"default_branch": "dev"}')
    (tmp_path / "desc.json").write_text('{"description": "x"}')
    for cmd in ("gh api -X PATCH repos/acme/demo --input - < db.json", "cat db.json | gh api -X PATCH repos/acme/demo --input -"):
        assert act(profile, tmp_path, cmd, role="conductor", branch="main") == "deny", cmd
        assert act(profile, tmp_path, cmd, role="attended", branch="main") == "ask", cmd
    assert act(profile, tmp_path, "gh api -X PATCH repos/acme/demo --input - < desc.json", role="conductor", branch="main") == "allow"


# ---------- 3. a writing find from the root or above ----------


def test_find_from_the_root_is_checked_against_the_files_there(profile, tmp_path):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("on: push\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.pyc").write_text("")
    for cmd in (
        "find . -delete",
        "find . -name '*.yml' -delete",
        "find . -iname '*.YML' -delete",
        "find . -name '*.yml' -exec sed -i s/a/b/ {} +",
        "find . -path './.github/*' -delete",
        "find . -name '*.pyc' -o -name '*.yml' -delete",
        "find .. -name '*.pyc' -delete",
        "find / -name ci.yml -delete",
    ):
        assert act(profile, tmp_path, cmd) == "deny", cmd
    for cmd in ("find . -name '*.pyc' -delete", "find . -type d -name __pycache__ -exec rm -rf {} +", "find src -delete"):
        assert act(profile, tmp_path, cmd) == "allow", cmd


# ---------- 4. a pull request as a blocker ----------


def _issue(n, state="open", labels=("ready-for-agent",), body="", reason=None, **extra):
    return {"number": n, "state": state, "state_reason": reason, "labels": [{"name": l} for l in labels], "body": body, "title": f"t{n}", **extra}


def test_a_pr_blocker_resolves_once_merged():
    body = "Blocked by: https://github.com/acme/demo/pull/8"
    assert blockers_of(body, "acme/demo") == [8]
    merged = _issue(8, state="closed", labels=(), pull_request={"merged_at": "2026-10-12T00:00:00Z"})
    unmerged = _issue(8, state="closed", labels=(), pull_request={"merged_at": None})
    still_open = _issue(8, labels=(), pull_request={"merged_at": None})
    for pr, reasons in ((merged, []), (unmerged, ["blocker PR #8 closed without merging"]), (still_open, ["blocked by open PR #8"])):
        (v,) = readiness([_issue(10, body=body), pr], [], repo="acme/demo")
        assert v.reasons == reasons
    (v,) = readiness([_issue(10, body=body)], [], repo="acme/demo")
    assert not v.ready and "unknown" in v.reasons[0]


# ---------- 10. the gate's reasons ----------


def test_gate_reasons_are_words(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    done = "- [x] a\n- [x] b\n- [ ] {}\nWORKFLOW-STATUS: done"
    for ok in ("Docs — none changed", "Merged: not yet, because the owner merges", "Docs: none", "Browser check skipped because no UI"):
        assert gate.verdict(done.format(ok)) is None, ok
    for bare in ("Handle the cannot connect case", "Update the Why section", "Docs—x", "Merged under the merge rule (or left for the owner), notes posted", "PR opened with the owner's one-time steps"):
        v = gate.verdict(done.format(bare))
        assert v and gate.NEEDS_REASON in v, bare


# ---------- 11. contractions as negations ----------


def test_contracted_negations_are_not_blockers():
    for text in ("This doesn't get blocked by #4 any more.", "It won't be blocked by #4.", "We aren't blocked by #4."):
        assert blockers_of(text, "acme/demo") == [], text
    assert blockers_of("This is blocked by #4 for now.", "acme/demo") == [4]


# ---------- the pass on the fixes above ----------


def _project(root):
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "ci.yml").write_text("on: push\n")
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / ".env").write_text("X=1\n")
    (root / "src" / "a.pyc").write_text("")


def test_a_matched_directory_holding_protected_paths(profile, tmp_path):
    _project(tmp_path)
    for cmd in (
        "find . -name .github -exec rm -rf {} +",
        "find . -name '.git*' -exec rm -rf {} +",
        "find . -name pkg -exec rm -rf {} +",
        "find . -name '\\.env' -delete",
        "find . -name '[^x]env' -delete",
    ):
        assert act(profile, tmp_path, cmd) == "deny", cmd
    assert act(profile, tmp_path, "find . -name '*.pyc' -delete") == "allow"


def test_a_symlinked_root_is_walked_as_its_target(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    _project(real)
    link = tmp_path / "link"
    link.symlink_to(real)
    prof = parse(json.loads(json.dumps(BASE_PROFILE)), link)
    assert act(prof, link, "find . -name ci.yml -delete") == "deny"
    assert act(prof, link, "find . -name '*.pyc' -delete") == "allow"


def test_dependency_directories_are_walked_and_a_big_tree_says_so(profile, tmp_path, monkeypatch):
    from workflow import guard

    _project(tmp_path)
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / ".env").write_text("X=1\n")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / ".env").write_text("X=1\n")
    for cmd in ("find . -name build -exec rm -rf {} +", "find . -name node_modules -exec rm -rf {} +"):
        assert act(profile, tmp_path, cmd) == "deny", cmd
    assert act(profile, tmp_path, "find . -name '*.pyc' -delete") == "allow"
    monkeypatch.setattr(guard, "_WALK_LIMIT", 5)
    d = decide({"tool_name": "Bash", "tool_input": {"command": "find . -name '*.pyc' -delete"}}, profile, "ticket", tmp_path, "claude/build-1")
    assert d.action == "deny" and "too big" in d.reason


@pytest.mark.parametrize(
    "cmd",
    [
        "find . -name config -exec rm -f {} \\; -prune -o -name zzz -print",
        "find . -name hooks -exec rm -rf {} + -prune -o -name zzz -print",
        "find . \\( -name config -prune -o -name zzz \\) -exec rm -f {} +",
        "find . -delete -name zzz",
        "find . -exec rm -f {} \\; -name zzz",
        "find . -true -delete -name zzz",
        "find . -name '[[:alpha:]]onfig' -delete",
        "find . -name '*[[:punct:]]sample' -delete",
        "find -name config -delete",
        "find -- . -name config -delete",
        "find . -name lnk -exec cp x {} \\;",
    ],
)
def test_find_expressions_the_guard_cant_read_exactly(cmd, profile, tmp_path):
    (tmp_path / ".git" / "hooks").mkdir(parents=True)
    (tmp_path / ".git" / "config").write_text("[core]\n")
    (tmp_path / ".git" / "hooks" / "pre-commit.sample").write_text("")
    (tmp_path / "lnk").symlink_to(tmp_path / ".git" / "config")
    assert act(profile, tmp_path, cmd) == "deny", cmd


def test_a_pruned_find_from_the_root(profile, tmp_path):
    _project(tmp_path)
    assert act(profile, tmp_path, "find . -name node_modules -prune -o -name '*.pyc' -delete") == "allow"
    assert act(profile, tmp_path, "find . -name node_modules -prune -o -name '*.yml' -delete") == "deny"
    assert act(profile, tmp_path, "find . -name node_modules -prune -o -name '*.pyc' -o -name '*.yml' -delete") == "deny"


def test_default_branch_through_dev_stdin_and_escaped_keys(profile, tmp_path):
    (tmp_path / "db.json").write_text('{"default_branch": "dev"}')
    (tmp_path / "esc.json").write_text('{"default\\u005fbranch": "dev"}')
    for cmd in (
        "gh api -X PATCH repos/acme/demo --input /dev/stdin < db.json",
        "gh api -X PATCH repos/acme/demo --input esc.json",
        "gh api -X PATCH repos/acme/demo --input - < esc.json",
        "gh api -X PATCH repos/acme/demo --input /proc/thread-self/fd/0 < db.json",
    ):
        assert act(profile, tmp_path, cmd, role="conductor", branch="main") == "deny", cmd


# ---------- the fourth pass ----------


@pytest.mark.parametrize(
    "cmd",
    [
        "find . -name '*.pyc' -execdir rm -rf ../.github \\;",
        "find . -name '*.pyc' -execdir sh -c 'rm -rf ../.github' \\;",
        "find . -iname 'confİg' -delete",
        "find $PWD -delete",
        'find "$PWD" -name \'*.yml\' -delete',
        "rm -rf $PWD/.github",
        "rm -rf ${PWD}/.github",
        "find -L src -name '*.yml' -delete",
        "find src -follow -name '*.yml' -delete",
        "echo .github/workflows/ci.yml | xargs rm",
        "printf '%s\\n' .github/workflows/ci.yml | xargs -I{} rm {}",
        "jq -r .files list.json | xargs rm",
    ],
)
def test_fourth_pass_bypasses(cmd, profile, tmp_path):
    _project(tmp_path)
    assert act(profile, tmp_path, cmd) == "deny", cmd


def test_fourth_pass_ordinary_work(profile, tmp_path):
    _project(tmp_path)
    for cmd in (
        "find . -name '*.pyc' -execdir rm -f {} +",
        "find . -iname '*.PYC' -delete",
        "rm -rf $PWD/src/a.pyc",
        "echo src/a.pyc | xargs rm",
    ):
        assert act(profile, tmp_path, cmd) == "allow", cmd


def test_stdin_spellings_normalised(profile, tmp_path):
    (tmp_path / "db.json").write_text('{"default_branch": "dev"}')
    for f in ("/dev/./stdin", "//dev/stdin", "/proc/self/fd/../fd/0", "/proc/$$/fd/0"):
        cmd = f"gh api -X PATCH repos/acme/demo --input {f} < db.json"
        assert act(profile, tmp_path, cmd, role="conductor", branch="main") == "deny", cmd


# ---------- the fifth pass ----------


@pytest.mark.parametrize(
    "cmd",
    [
        "find src -name main.py -execdir cp {} .env \\;",
        "find src -name main.py -execdir mv {} ../.github/x \\;",
        "find . -name '*.yml' | xargs rm",
        "echo .github/workflows/ci.yml | xargs -I% rm %",
        "echo .github/workflows/ci.yml | xargs rm src/a.pyc",
        "echo '.git\\hub/workflows/ci.yml' | xargs rm",
        "printf '.git%sub/workflows/ci.yml\\n' h | xargs rm",
        "cat < evil.txt | xargs rm",
        "git ls-files '*.yml' | xargs rm",
        "(cd .github && echo workflows/ci.yml) | xargs rm",
        "xargs rm < evil.txt",
        "xargs -a evil.txt rm",
        "rm -rf $(pwd -P)/.github",
        "rm -rf $( pwd )/.github",
        "rm -rf ${PWD%/}/.github",
    ],
)
def test_fifth_pass_bypasses(cmd, profile, tmp_path):
    _project(tmp_path)
    assert act(profile, tmp_path, cmd) == "deny", cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "echo src/a.pyc | xargs rm",
        "printf '%s\\n' src/a.pyc | xargs rm",
        "find . -name '*.pyc' -execdir rm -f {} +",
        "yes | rm -i src/a.pyc",
        "pytest | tee out.log",
    ],
)
def test_fifth_pass_ordinary_work(cmd, profile, tmp_path):
    _project(tmp_path)
    assert act(profile, tmp_path, cmd) == "allow", cmd


# ---------- the sixth pass ----------


def test_find_piped_to_xargs_from_the_root_points_to_delete(profile, tmp_path):
    _project(tmp_path)
    for cmd in ("find . -name '*.pyc' -print0 | xargs -0 rm -f", "find . -type d -name __pycache__ | xargs rm -rf"):
        d = decide({"tool_name": "Bash", "tool_input": {"command": cmd}}, profile, "ticket", tmp_path, "claude/build-1")
        assert d.action == "deny" and "-delete" in d.reason, cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "echo .github/workflows/ci.yml | env -S 'xargs rm'",
        "echo .github/workflows/ci.yml | env --split-string='xargs rm'",
        "find . -name .github -prune -o -name '*.pyc' | xargs rm -rf",
        "find -L . -name .gitconfig | xargs rm",
        "find $PWD -name x | xargs rm -rf",
        "echo 'x .github/workflows/ci.yml' | xargs rm",
        "find src -name main.py -execdir env -C ../.github rm -rf {} \\;",
        "find src -name main.py -execdir cp {} .env \\;",
    ],
)
def test_sixth_pass_bypasses(cmd, profile, tmp_path):
    _project(tmp_path)
    assert act(profile, tmp_path, cmd) == "deny", cmd


def test_sixth_pass_no_exception_with_deploy_commands(deploy_profile, tmp_path):
    for cmd in ("find . -name '*.sh' -execdir bash {} \\;", "find . -name x -execdir python3 {} \\;"):
        assert act(deploy_profile, tmp_path, cmd) in ("allow", "deny"), cmd


def test_sixth_pass_ordinary_work(profile, tmp_path):
    _project(tmp_path)
    for cmd in ("find . -name '*.pyc' -execdir rm -f {} +", "find . -name '*.pyc' -delete", "find src -name '*.orig' -delete"):
        assert act(profile, tmp_path, cmd) == "allow", cmd


def test_a_find_matching_the_roots_own_name(profile, tmp_path):
    _project(tmp_path)
    assert act(profile, tmp_path, f"find $PWD -name {tmp_path.name} -exec rm -rf {{}} +", ) == "deny"
    assert act(profile, tmp_path, "find . -name '*' -delete") == "deny"


# ---------- the seventh pass ----------


def test_a_searched_tree_holding_a_protected_file_anywhere(profile, tmp_path):
    _project(tmp_path)  # src/pkg/.env, which `**/.env` reaches
    for cmd in (
        "rm -rf src",
        "git ls-files 'src/*' | xargs rm",
        "find src -name '*.orig' | xargs rm",
        "git ls-files ':/.github/workflows/*' | xargs rm",
        "git ls-files ':!src/*' | xargs rm",
        "git ls-files ':(top).github/*' | xargs rm",
        "find src -name pkg -exec rm -rf {} +",
    ):
        assert act(profile, tmp_path, cmd) == "deny", cmd


def test_searches_of_trees_without_protected_files(profile, tmp_path):
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "ci.yml").write_text("on: push\n")
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "a.pyc").write_text("")
    for cmd in (
        "rm -rf src/pkg",
        "git ls-files 'src/*.pyc' | xargs rm",
        "find src -name '*.pyc' -print0 | xargs -0 rm -f",
        "find src -name '*.py' -execdir sed -i s/a/b/ {} +",
        "find src -name '*.sh' -execdir chmod +x {} +",
        "find . -name 'src*' -delete",
        "echo src/pkg/a.pyc | xargs touch -a",
    ):
        assert act(profile, tmp_path, cmd) == "allow", cmd
    assert act(profile, tmp_path, f"find . -name '{tmp_path.name[:4]}*' -delete") == "allow"  # `.` isn't tested by name
    assert act(profile, tmp_path, "find src -name a.pyc -execdir sudo --chdir=../.github rm -rf {} +") == "deny"
    assert act(profile, tmp_path, "find src -name a.pyc -execdir sudo -D../.github rm -rf {} +") == "deny"


# ---------- the eighth pass ----------


@pytest.mark.parametrize(
    "cmd",
    [
        "find . -type d -name lib -execdir cp /tmp/payload/.env {} \\;",
        "find . -type d -name lib -execdir tar -xf p.tar -C {} \\;",
        "find . -type d -name lib -execdir rsync -a /tmp/payload/ {} \\;",
        "find . -name a.py -execdir cp {} ROOT/.github/workflows/ \\;",
        "find . -name a.py -execdir ln -s {} ROOT/.claude/ \\;",
        "echo hi > .github/workflows/__find_execdir_match__",
        "cp evil.yml .github/workflows/{}",
        "mkdir -p x && rm -rf x/../.github",
        "git ls-files ':/.github/workflows/*' | xargs rm",
        "git ls-files ':(exclude)src' | xargs rm",
    ],
)
def test_eighth_pass_bypasses(cmd, profile, tmp_path):
    _project(tmp_path)
    (tmp_path / "lib").mkdir()
    assert act(profile, tmp_path, cmd.replace("ROOT", str(tmp_path))) == "deny", cmd


def test_eighth_pass_ordinary_work(profile, tmp_path):
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "ci.yml").write_text("on: push\n")
    (tmp_path / "src").mkdir()
    for cmd in (
        "find src -name '*.py' -execdir sed -i s/a/b/ {} +",
        "find src -name '*.sh' -execdir chmod +x {} +",
        "find . -name '*.pyc' -execdir rm -f {} +",
    ):
        assert act(profile, tmp_path, cmd) == "allow", cmd


# ---------- the ninth pass ----------


def test_ninth_pass_bypasses(profile, tmp_path):
    _project(tmp_path)
    (tmp_path / "x").write_text(str(tmp_path / ".github" / "workflows" / "ci.yml"))
    for cmd in (
        "cd src && git ls-files ':/.github' | xargs rm",
        "cd src && git ls-files -z ':(top).github/workflows' | xargs -0 rm -f",
        "git ls-files ':(icase)Src' | xargs rm",
        "git grep -l foo -- ':(top)src' | xargs sed -i s/a/b/",
        "find src -name a.py -execdir sed -i s/a/b/ {} $(cat x) \\;",
        "find src -name a.py -execdir sed -i s/a/b/ {} `cat x` \\;",
    ):
        assert act(profile, tmp_path, cmd) == "deny", cmd


def test_a_tree_between_the_old_and_new_walk_limits(profile, tmp_path, monkeypatch):
    from workflow import guard

    assert guard._TREE_WALK_LIMIT >= 50_000


def test_magic_pathspecs_from_a_subdirectory(profile, tmp_path):
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "ci.yml").write_text("on: push\n")
    (tmp_path / "src").mkdir()
    for cmd in (
        "cd src && git ls-files ':/.github' | xargs rm",
        "cd src && git ls-files ':(top).github' | xargs rm -f",
        "cd src && git grep -l on -- ':/' | xargs sed -i s/a/b/",
        "cd src && git ls-files ':(top,glob)**/*.yml' | xargs rm",
    ):
        assert act(profile, tmp_path, cmd) == "deny", cmd
