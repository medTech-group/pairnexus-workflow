"""#390 (spec #338, split from #341): under `code_writers = "ticket"`, a
session that doesn't write code is refused a `git push` to `project.repo`,
from any directory, when the commits it would send (those on no tracking
ref of a remote that fetches from `project.repo`) carry a code path, judged
as #389 reads one. A remote is `project.repo` when its push URL, with `.git`
and a trailing `/` stripped and compared in any case, ends in it with a `/`
or `:` just before it; a push given a URL is judged by that URL. A push
whose commits or remote can't be read is asked, and refused in the
conductor. Pushes to other repositories decide as today.

Through `workflow hook guard`, run as Claude Code runs it, in temporary git
repositories cloned from a bare remote (`…/acme/demo.git`). The commands are
data given to the hook; only the set-up runs."""

import pytest

from changelog_notes import since_0110
from conftest import KIT, git
from test_guard_code_commits import CODE, NOT_TICKET, _change, _clone, _on, hook
from workflow import cli
from workflow import guard as guard_mod

pytestmark = pytest.mark.usefixtures("_no_user_git_config")


@pytest.fixture
def proj(tmp_path):
    return _clone(tmp_path)


def _commit(root, path, text="changed\n", msg="x"):
    _change(root, path, text)
    git(root, "add", path)
    git(root, "commit", "-qm", msg)


def _code_commit(root):
    _commit(root, CODE)


def _docs_commit(root):
    _commit(root, "docs/guide.md")


def _other_remote(tmp_path, name="other"):
    """A bare repository that isn't `project.repo`."""
    bare = tmp_path / f"{name}-remote" / "acme" / "elsewhere.git"
    bare.parent.mkdir(parents=True)
    git(tmp_path, "init", "-q", "--bare", str(bare))
    return bare


# ---------- which commits ----------


PUSHES = [
    "git push origin feature",
    "git push origin HEAD",
    "git push -u origin feature",
    "git push origin HEAD:refs/heads/feature",
    "git push origin feature:feature-2",
    "git push",
    "git push origin",
    "git push --set-upstream origin feature",
    "git push origin $(git branch --show-current)",
    "git -C . push origin feature",
    "cd docs && git push origin feature",
    "env git push origin feature",
    "git push --repo=origin",
    "git push origin tag v1",
    "git push origin --tags",
]


@pytest.mark.parametrize("command", PUSHES)
@pytest.mark.parametrize("who", list(NOT_TICKET))
def test_a_push_carrying_a_code_path_is_refused(tmp_path, monkeypatch, capsys, command, who):
    role, branch = NOT_TICKET[who]
    root = _clone(tmp_path)
    _on(root, branch)
    _code_commit(root)
    if branch != "feature":
        git(root, "branch", "-q", "-f", "feature")
    git(root, "tag", "v1")
    git(root, "config", f"branch.{branch}.remote", "origin")
    for mode in (None, "default", "bypassPermissions", "dontAsk"):
        d, why = hook(monkeypatch, capsys, root, command, role, mode)
        assert d == "deny", (who, mode, command, d, why)
        assert "push" in why and "code path `src/app.py` (src/**)" in why, why


def test_the_refusal_names_the_commit_the_path_and_what_to_do_instead(proj, monkeypatch, capsys):
    _code_commit(proj)
    sha = git(proj, "rev-parse", "--short", "HEAD").strip()
    d, why = hook(monkeypatch, capsys, proj, "git push origin feature")
    assert d == "deny" and why.startswith("[workflow guard, attended session]"), why
    assert f"commit {sha}" in why and "carries the code path `src/app.py` (src/**)" in why, why
    assert "acme/demo" in why and "**Run it unattended**" in why and "guard.code_writers" in why, why
    d, why = hook(monkeypatch, capsys, proj, "git push origin feature", "conductor")
    assert d == "deny" and "the conductor writes no code" in why and "`workflow:infra`" in why, why


@pytest.mark.parametrize("who", list(NOT_TICKET))
def test_a_push_of_docs_only_commits_goes_through(tmp_path, monkeypatch, capsys, who):
    role, branch = NOT_TICKET[who]
    root = _clone(tmp_path)
    _on(root, branch)
    _docs_commit(root)
    _commit(root, "README.md", "# demo\n")
    for command in (f"git push origin {branch}", "git push origin HEAD", f"git push -u origin {branch}"):
        d, why = hook(monkeypatch, capsys, root, command, role)
        assert d == "allow", (who, command, why)


def test_commits_already_on_the_remote_dont_count(proj, monkeypatch, capsys):
    """A code commit pushed earlier (by a ticket session, say) is on the
    remote's tracking refs: only what the push would send counts."""
    _code_commit(proj)
    git(proj, "push", "-q", "origin", "feature")
    _docs_commit(proj)
    assert hook(monkeypatch, capsys, proj, "git push origin feature")[0] == "allow"
    # The base's code, merged by a fast-forward, is on the remote already.
    git(proj, "checkout", "-q", "-b", "other", "origin/main")
    assert hook(monkeypatch, capsys, proj, "git push origin other")[0] == "allow"


def test_code_under_a_docs_commit_still_counts(proj, monkeypatch, capsys):
    _code_commit(proj)
    _docs_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, "git push origin feature")
    assert d == "deny" and "src/app.py" in why, why


def test_a_removed_or_renamed_code_file_counts(proj, monkeypatch, capsys):
    git(proj, "mv", CODE, "docs/app.py")
    git(proj, "commit", "-qm", "move")
    d, why = hook(monkeypatch, capsys, proj, "git push origin feature")
    assert d == "deny" and "src/app.py" in why, why


def test_a_protected_path_inside_a_code_path_isnt_code(proj, monkeypatch, capsys):
    _commit(proj, "src/protected/keep.py")
    assert hook(monkeypatch, capsys, proj, "git push origin feature")[0] == "allow"


def test_a_merge_commit_is_judged_as_any_commit(proj, monkeypatch, capsys):
    """Until #391 narrows it: a merge's change against its first parent counts."""
    git(proj, "checkout", "-q", "-b", "side")
    _code_commit(proj)
    git(proj, "checkout", "-q", "feature")
    git(proj, "merge", "-q", "--no-ff", "--no-edit", "side")
    git(proj, "branch", "-q", "-D", "side")
    d, why = hook(monkeypatch, capsys, proj, "git push origin feature")
    assert d == "deny" and "src/app.py" in why, why


def test_only_the_named_branch_counts(proj, monkeypatch, capsys):
    git(proj, "checkout", "-q", "-b", "code")
    _code_commit(proj)
    git(proj, "checkout", "-q", "feature")
    _docs_commit(proj)
    assert hook(monkeypatch, capsys, proj, "git push origin feature")[0] == "allow"
    assert hook(monkeypatch, capsys, proj, "git push origin code")[0] == "deny"
    assert hook(monkeypatch, capsys, proj, "git push origin code:feature")[0] == "deny"
    assert hook(monkeypatch, capsys, proj, "git push origin feature code")[0] == "deny"
    assert hook(monkeypatch, capsys, proj, "git push origin {feature,code}")[0] == "deny"


def test_a_dry_run_or_a_deletion_sends_nothing(proj, monkeypatch, capsys):
    _code_commit(proj)
    for command in ("git push --dry-run origin feature", "git push -n origin feature"):
        assert hook(monkeypatch, capsys, proj, command) == ("allow", ""), command
    # A deletion sends no commit: decided as today (asked, outside the workflow's rules).
    for command in ("git push origin :feature", "git push --delete origin feature", "git push -d origin feature"):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "ask" and "code path" not in why and "can't tell" not in why, (command, why)


def test_matching_push_settings_count_every_branch(proj, monkeypatch, capsys):
    """With `push.default = matching`, a bare push sends every branch the remote has."""
    git(proj, "checkout", "-q", "-b", "code")
    _code_commit(proj)
    git(proj, "checkout", "-q", "feature")
    _docs_commit(proj)
    assert hook(monkeypatch, capsys, proj, "git push origin")[0] == "allow"
    git(proj, "config", "push.default", "matching")
    assert hook(monkeypatch, capsys, proj, "git push origin")[0] == "deny"


def test_a_push_from_another_clone_is_judged(proj, tmp_path, monkeypatch, capsys):
    """Code committed in a clone the commit rule leaves alone is caught when pushed."""
    other = tmp_path / "elsewhere"
    git(tmp_path, "clone", "-q", str(tmp_path / "proj-remote/acme/demo.git"), str(other))
    git(other, "config", "user.email", "t@example.com")
    git(other, "config", "user.name", "t")
    git(other, "checkout", "-q", "-b", "x")
    _code_commit(other)
    for command in (f"cd {other} && git push origin x", f"git -C {other} push origin x"):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "deny" and "src/app.py" in why, (command, why)
    _docs_commit(other)
    git(other, "push", "-q", "origin", "x")
    _commit(other, "docs/guide.md", "more\n")
    assert hook(monkeypatch, capsys, proj, f"git -C {other} push origin x")[0] == "allow"


def test_a_code_push_is_refused_even_after_an_ask(proj, monkeypatch, capsys):
    _code_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, "git push origin HEAD:main; git push origin feature")
    assert d == "deny" and "code path" in why, why


def test_an_options_value_is_not_the_repository(proj, monkeypatch, capsys):
    """git takes the next word as these options' value."""
    _code_commit(proj)
    for command in (
        "git push --recurse-submodules check origin feature",
        "git push --recurse-submodules on-demand origin feature",
        "git push -o ci.skip origin feature",
        "git push --push-option x origin feature",
        "git push --repo origin",
        "git push --no-recurse-submodules origin feature",
    ):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "deny" and "src/app.py" in why, (command, d, why)


def test_patterns_send_every_ref_they_match(proj, tmp_path, monkeypatch, capsys):
    """Code fetched from another clone, or stashed, is sent by a pattern."""
    other = tmp_path / "elsewhere"
    git(tmp_path, "clone", "-q", str(tmp_path / "proj-remote/acme/demo.git"), str(other))
    git(other, "config", "user.email", "t@example.com")
    git(other, "config", "user.name", "t")
    _code_commit(other)
    git(proj, "remote", "add", "other", str(other))
    git(proj, "fetch", "-q", "other")
    _docs_commit(proj)
    assert hook(monkeypatch, capsys, proj, "git push origin feature")[0] == "allow"
    for command in (
        "git push origin 'refs/remotes/other/*:refs/heads/*'",
        "git push origin --mirror",
        "git push --mirror origin",
    ):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "deny" and "src/app.py" in why, (command, d, why)
    # A remote's push setting sends the same.
    git(proj, "config", "remote.origin.push", "refs/remotes/other/*:refs/heads/*")
    d, why = hook(monkeypatch, capsys, proj, "git push origin")
    assert d == "deny" and "src/app.py" in why, why


def test_stashed_code_sent_by_a_pattern(proj, monkeypatch, capsys):
    _change(proj, CODE)
    git(proj, "stash", "-q")
    d, why = hook(monkeypatch, capsys, proj, "git push origin 'refs/sta*:refs/heads/sta*'")
    assert d == "deny" and "src/app.py" in why, why


def test_a_negative_refspec_is_a_push_the_guard_cant_tell_about(proj, monkeypatch, capsys):
    """It doesn't read what a negative refspec leaves out, so it neither
    refuses for a commit that may not be sent nor lets one through."""
    _code_commit(proj)
    git(proj, "checkout", "-q", "-b", "docsonly", "origin/main")
    _docs_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, "git push origin 'refs/heads/*:refs/heads/*' '^refs/heads/feature'")
    assert d == "ask" and "negative refspec" in why, why
    assert hook(monkeypatch, capsys, proj, "git push origin 'refs/heads/*:refs/heads/*' '^refs/heads/feature'", "conductor")[0] == "deny"


@pytest.mark.parametrize("value", ["true", "yes", "on", "1"])
def test_a_mirror_setting_sends_every_ref(proj, monkeypatch, capsys, value):
    git(proj, "checkout", "-q", "-b", "code")
    _code_commit(proj)
    git(proj, "checkout", "-q", "feature")
    git(proj, "config", "remote.origin.mirror", value)
    d, why = hook(monkeypatch, capsys, proj, "git push origin")
    assert d == "deny" and "src/app.py" in why, (value, why)


@pytest.mark.parametrize("name", ["docs", "src", "tests"])
def test_a_branch_named_like_a_folder(proj, monkeypatch, capsys, name):
    git(proj, "checkout", "-q", "-b", name)
    _docs_commit(proj)
    assert hook(monkeypatch, capsys, proj, f"git push origin {name}") == ("allow", "")
    assert hook(monkeypatch, capsys, proj, f"git push -u origin {name}", "conductor") == ("allow", "")
    _code_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, f"git push origin {name}")
    assert d == "deny" and "src/app.py" in why, why


def test_a_file_name_like_the_guards_own_marker_is_still_read(proj, monkeypatch, capsys):
    _commit(proj, "src/\x01ab.py")
    d, why = hook(monkeypatch, capsys, proj, "git push origin feature")
    assert d == "deny" and "src/" in why, why


def test_a_repository_made_in_the_same_command(proj, monkeypatch, capsys):
    (proj / "tmpx").mkdir()
    d, why = hook(monkeypatch, capsys, proj, "gh repo clone me/fork tmpx && git -C tmpx push git@github.com:acme/demo.git HEAD:refs/heads/x")
    assert d == "ask" and "can't tell" in why and "makes a repository" in why, why


def test_ordinary_parts_beside_a_push_leave_it_judged(proj, monkeypatch, capsys):
    _docs_commit(proj)
    for command in (
        "git fetch && git push origin feature",
        "git fetch origin main && git push origin feature",
        "git gc && git push origin feature",
        "git status && git push -u origin HEAD",
        "git push origin feature && git push origin HEAD:refs/heads/feature-2",
        "git config user.email me@example.com && git push origin feature",
        "git push origin $(git branch --show-current)",
    ):
        assert hook(monkeypatch, capsys, proj, command) == ("allow", ""), command


def test_long_words_dont_slow_the_push_rule(proj, monkeypatch, capsys):
    import time

    for command in ("git push origin '{" + "." * 100_000 + "'", "git push origin " + "{a,b}" * 30, "git push origin " + "{" * 3000 + "x"):
        t = time.monotonic()
        d, why = hook(monkeypatch, capsys, proj, command)
        assert time.monotonic() - t < 5, command[:40]
        assert d == "ask" and "guard isn't working" not in why, (command[:40], why[:200])


def test_a_bare_push_goes_where_git_sends_it(proj, tmp_path, monkeypatch, capsys):
    other = _other_remote(tmp_path)
    git(proj, "remote", "add", "o", str(other))
    _code_commit(proj)
    assert hook(monkeypatch, capsys, proj, "git push")[0] == "deny"
    git(proj, "config", "remote.pushDefault", "o")
    assert hook(monkeypatch, capsys, proj, "git push") == ("allow", "")
    git(proj, "config", "branch.feature.pushRemote", "origin")
    assert hook(monkeypatch, capsys, proj, "git push")[0] == "deny"
    git(proj, "config", "branch.feature.pushRemote", "o")
    assert hook(monkeypatch, capsys, proj, "git push") == ("allow", "")


def test_a_docs_only_bare_push(proj, monkeypatch, capsys):
    _docs_commit(proj)
    assert hook(monkeypatch, capsys, proj, "git push") == ("allow", "")
    assert hook(monkeypatch, capsys, proj, "git push", "conductor") == ("allow", "")


def test_the_shells_branch_in_another_repository(proj, tmp_path, monkeypatch, capsys):
    other = tmp_path / "elsewhere"
    git(tmp_path, "clone", "-q", str(tmp_path / "proj-remote/acme/demo.git"), str(other))
    _docs_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, f"git -C {other} push origin $(git branch --show-current)")
    assert d == "ask" and "the shell's branch" in why, why
    # The same repository, from a folder of it: HEAD.
    assert hook(monkeypatch, capsys, proj, "git -C docs push origin $(git branch --show-current)") == ("allow", "")


def test_a_bare_push_beside_another_push(proj, monkeypatch, capsys):
    git(proj, "tag", "vdocs")
    _docs_commit(proj)
    git(proj, "config", "branch.feature.remote", "origin")
    for command in ("git push && git push --tags", "git push origin feature && git push"):
        assert hook(monkeypatch, capsys, proj, command) == ("allow", ""), command
    # `-u` sets the branch's remote, which a bare push after it reads.
    d, why = hook(monkeypatch, capsys, proj, "git push -u origin HEAD; git push")
    assert d == "ask" and "can't tell" in why, why
    git(proj, "remote", "add", "self", ".")
    git(proj, "config", "branch.feature.pushRemote", "self")
    d, why = hook(monkeypatch, capsys, proj, "git push && git push origin feature")
    assert d == "ask" and "can't tell" in why, why


def test_a_remote_named_like_a_url(proj, monkeypatch, capsys):
    """git looks a word up as a remote before reading it as a URL."""
    git(proj, "config", "remote.https://github.com/acme/sandbox.url", "git@github.com:acme/demo.git")
    _code_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, "git push https://github.com/acme/sandbox feature")
    assert d == "deny" and "src/app.py" in why, why


@pytest.mark.parametrize("command", ["git push . HEAD:wip", "git push -u . HEAD:wip", "git push .. feature", "git push '' feature"])
def test_a_push_into_a_path_that_isnt_project_repo_decides_as_today(proj, monkeypatch, capsys, command):
    (proj / ".git/branches").mkdir(exist_ok=True)
    _docs_commit(proj)
    for role in (None, "conductor"):
        d, why = hook(monkeypatch, capsys, proj, command, role)
        with monkeypatch.context() as m:
            m.setattr(guard_mod, "_push_code", lambda *a, **k: (None, None))
            today = hook(monkeypatch, capsys, proj, command, role)
        assert (d, why) == today, (command, role, why)


def test_no_tags_cancels_tags(proj, monkeypatch, capsys):
    git(proj, "tag", "vdocs")
    git(proj, "push", "-q", "origin", "feature")
    _code_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, "git push --tags --no-tags origin")
    assert d == "deny" and "src/app.py" in why, why


@pytest.mark.parametrize(
    "command",
    [
        "git config --remove-section branch.feature && git push",
        "git config remove-section branch.feature && git push",
        "git config --rename-section branch.feature branch.old && git push",
    ],
)
def test_a_config_section_dropped_before_a_bare_push(proj, tmp_path, monkeypatch, capsys, command):
    other = _other_remote(tmp_path)
    git(proj, "remote", "add", "side", str(other))
    git(proj, "config", "branch.feature.pushRemote", "side")
    _code_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, command)
    assert d == "ask" and "can't tell" in why, (command, why)


def test_a_switch_before_a_bare_push_that_seems_to_go_elsewhere(proj, tmp_path, monkeypatch, capsys):
    other = _other_remote(tmp_path)
    git(proj, "remote", "add", "side", str(other))
    git(proj, "config", "branch.feature.pushRemote", "side")
    git(proj, "checkout", "-q", "-b", "codeb")
    _code_commit(proj)
    git(proj, "checkout", "-q", "feature")
    d, why = hook(monkeypatch, capsys, proj, "git switch codeb && git push")
    assert d == "ask" and "can't tell" in why, why


@pytest.mark.parametrize(
    "command",
    [
        "git config --local remote.origin.url && git push origin feature",
        "git config --global push.default; git push origin feature",
        "git config --show-origin remote.origin.url && git push origin feature",
        "git config -z remote.origin.url && git push origin feature",
        "git -c push.autoSetupRemote=true push origin feature",
        "git config push.autoSetupRemote true && git push origin feature",
        "git branch --contains HEAD && git push origin feature",
        "git branch --merged main && git push origin feature",
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=user.name GIT_CONFIG_VALUE_0=x git push https://github.com/acme/sandbox feature",
    ],
)
def test_reads_and_other_settings_beside_a_push(proj, monkeypatch, capsys, command):
    """Decided as without the push rule (some are asked or refused by today's own rules)."""
    _docs_commit(proj)
    for role in (None, "conductor"):
        d, why = hook(monkeypatch, capsys, proj, command, role)
        with monkeypatch.context() as m:
            m.setattr(guard_mod, "_push_code", lambda *a, **k: (None, None))
            today = hook(monkeypatch, capsys, proj, command, role)
        assert (d, why) == today, (command, role, why)


def test_a_tag_on_a_tree_is_a_push_the_guard_cant_tell_about(proj, monkeypatch, capsys):
    _change(proj, CODE)
    git(proj, "add", CODE)
    tree = git(proj, "write-tree").strip()
    git(proj, "reset", "-q")
    git(proj, "tag", "treetag", tree)
    for command in ("git push origin treetag", "git push origin --tags"):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "ask" and "isn't a commit" in why, (command, why)


def test_the_push_rules_own_time_limit(proj, monkeypatch, capsys):
    monkeypatch.setattr(guard_mod, "_PUSH_RULE_SECONDS", -1)
    d, why = hook(monkeypatch, capsys, proj, "git push origin feature")
    assert d == "ask" and "too many to read in time" in why, why


@pytest.mark.parametrize(
    "command",
    [
        "GIT_DIR={cb} git push side codeb",
        "HOME={tmp} git push side codeb",
        "GIT_CONFIG_GLOBAL={tmp}/gc git push side codeb",
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=$K GIT_CONFIG_VALUE_0=x git push side codeb",
        "git -c \"$K=x\" push side codeb",
        "printf x >> .git/config && git push side codeb",
        "git config --remove branch.feature && git push",
        "git config --unset-al branch.feature.pushremote && git push",
        "git config --rename-section foo.x remote.side && git push side codeb",
        "git push -u origin feature && git push",
        "git tag --sort=refname vcode codeb && git push origin --tags",
        "git branch --format=x wip codeb && git push origin --all",
        "git fetch --refmap=+refs/heads/*:refs/heads/* side codeb && git push origin codeb",
        "git push --set-up origin feature && git push",
        "printf x >> ~/.gitconfig && git push side codeb",
        "printf x >> .git/config && git push https://github.com/acme/sandbox codeb",
        "git -c 'remote.x:y.url=git@github.com:acme/demo.git' push x:y codeb",
        "git config remote.x:y.url git@github.com:acme/demo.git && git push x:y codeb",
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=remote.x:y.url GIT_CONFIG_VALUE_0=git@github.com:acme/demo.git git push x:y codeb",
    ],
)
def test_what_changes_where_a_push_by_a_remotes_name_goes(proj, tmp_path, monkeypatch, capsys, command):
    """A push by a remote's name, or with none named, that seems to go
    elsewhere: whatever changes the config or repository git reads makes it
    one the guard can't tell about."""
    other = _other_remote(tmp_path)
    git(proj, "remote", "add", "side", str(other))
    git(proj, "config", "branch.feature.pushRemote", "side")
    git(proj, "checkout", "-q", "-b", "codeb")
    _code_commit(proj)
    git(proj, "checkout", "-q", "feature")
    command = command.format(cb=tmp_path / "cb.git", tmp=tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    d, why = hook(monkeypatch, capsys, proj, command)
    assert d == "ask" and "can't tell" in why, (command, d, why)
    assert hook(monkeypatch, capsys, proj, command, "conductor")[0] == "deny", command


def test_the_shells_branch_in_another_worktree(proj, tmp_path, monkeypatch, capsys):
    """Worktrees share a git directory but each has its own HEAD."""
    git(proj, "checkout", "-q", "-b", "codeb")
    _code_commit(proj)
    wt = proj / ".claude/worktrees/w"
    git(proj, "worktree", "add", "-q", "-b", "docsb", str(wt), "origin/main")
    d, why = hook(monkeypatch, capsys, proj, "git -C .claude/worktrees/w push origin $(git branch --show-current)")
    assert d == "ask" and "the shell's branch" in why, why


def test_a_nested_tag_on_a_tree(proj, monkeypatch, capsys):
    _change(proj, CODE)
    git(proj, "add", CODE)
    tree = git(proj, "write-tree").strip()
    git(proj, "reset", "-q")
    git(proj, "tag", "sub/tt", tree)
    d, why = hook(monkeypatch, capsys, proj, "git push origin 'refs/tags/*:refs/tags/*'")
    assert d == "ask" and "isn't a commit" in why, why


def test_a_branch_named_like_a_tag_keeps_its_push_remote(proj, tmp_path, monkeypatch, capsys):
    other = _other_remote(tmp_path)
    git(proj, "remote", "add", "fork", str(other))
    git(proj, "config", "remote.pushDefault", "fork")
    git(proj, "config", "branch.feature.pushRemote", "origin")
    git(proj, "tag", "feature", "origin/main")
    _code_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, "git push")
    assert d == "deny" and "src/app.py" in why, why


@pytest.mark.parametrize("command", ["git send-pack", "git http-push"])
def test_send_pack_with_no_repository(proj, monkeypatch, capsys, command):
    d, why = hook(monkeypatch, capsys, proj, command)
    assert "isn't working" not in why, why


@pytest.mark.parametrize(
    "command",
    [
        "git config --type bool push.default && git push origin feature",
        "git config -f x.cfg remote.origin.url && git push origin feature",
        "git tag -l 'v*' && git push origin feature",
    ],
)
def test_config_and_tag_reads_with_options_beside_a_push(proj, monkeypatch, capsys, command):
    _docs_commit(proj)
    assert hook(monkeypatch, capsys, proj, command) == ("allow", ""), command


def test_a_code_push_beside_a_named_dot_git_or_an_upstream_is_still_refused(proj, monkeypatch, capsys):
    git(proj, "checkout", "-q", "-b", "codeb")
    _code_commit(proj)
    for command in ("git push origin codeb && echo see .git/remotes", "git push -u origin feature && git push origin codeb"):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "deny" and "src/app.py" in why, (command, why)


@pytest.mark.parametrize(
    "command",
    [
        "git -c http.extraHeader=\"Authorization: Bearer $TOKEN\" push https://github.com/acme/sandbox feature",
        "git branch --format '%(refname:short)' && git push origin feature",
        "git branch --sort committerdate && git push origin feature",
        "git config get --show-names --all --regexp '^remote\\.' && git push https://github.com/acme/sandbox x",
        "git push -u origin feature && git push origin HEAD:refs/heads/feature-2",
        "git branch --sort -committerdate && git push origin feature",
        "git remote prune origin && git push https://github.com/acme/sandbox x",
        "git remote update && git push origin feature",
        "git --config-env=http.extraHeader=AUTH push https://github.com/acme/sandbox x",
    ],
)
def test_more_ordinary_parts_beside_a_push_decide_as_without_the_rule(proj, monkeypatch, capsys, command):
    _docs_commit(proj)
    for role in (None, "conductor"):
        d, why = hook(monkeypatch, capsys, proj, command, role)
        with monkeypatch.context() as m:
            m.setattr(guard_mod, "_push_code", lambda *a, **k: (None, None))
            today = hook(monkeypatch, capsys, proj, command, role)
        assert (d, why) == today, (command, role, why)


@pytest.mark.parametrize(
    "command",
    [
        "git -c push.default=matching push git@github.com:acme/demo.git",
        "git config push.default matching && git push git@github.com:acme/demo.git",
        "GIT_CONFIG_PARAMETERS=\"'push.default'='matching'\" git push git@github.com:acme/demo.git",
        "GIT_DIR={cb} git push git@github.com:acme/demo.git feature",
        "GIT_CONFIG_PARAMETERS=\"'url.git@github.com:acme/demo.git.pushInsteadOf=https://github.com/acme/sandbox'\" git push https://github.com/acme/sandbox codeb",
        "GIT_CONFIG_PARAMETERS=\"'http.x'='$T'\" git push https://github.com/acme/sandbox codeb",
        "git remote set-url --push x:y git@github.com:acme/demo.git && git push x:y codeb",
        "GIT_CONFIG_PARAMETERS=\"'http.x=a\\' 'url.git@github.com:acme/demo.git.pushInsteadOf=https://github.com/acme/sandbox'\" git push https://github.com/acme/sandbox codeb",
        "GIT_CONFIG_PARAMETERS=\"'http.x'='a'\\''b' 'url.git@github.com:acme/demo.git.pushInsteadOf'='https://github.com/acme/sandbox'\" git push https://github.com/acme/sandbox codeb",
        "GIT_CONFIG_PARAMETERS=\"not git's format\" git push https://github.com/acme/sandbox codeb",
    ],
)
def test_what_changes_what_a_url_push_sends(proj, tmp_path, monkeypatch, capsys, command):
    """A push given a URL: with no refs, `push.default` says what it sends;
    a remote of that name is looked up first; GIT_CONFIG_PARAMETERS is read
    as git reads it, after the shell."""
    git(proj, "config", "remote.x:y.url", str(_other_remote(tmp_path)))
    git(proj, "checkout", "-q", "-b", "codeb")
    _code_commit(proj)
    git(proj, "checkout", "-q", "main")
    git(proj, "merge", "-q", "--ff-only", "codeb")
    git(proj, "checkout", "-q", "feature")
    d, why = hook(monkeypatch, capsys, proj, command.format(cb=tmp_path / "cb.git"))
    assert d == "ask" and "can't tell" in why, (command, d, why)


@pytest.mark.parametrize(
    "command",
    [
        "git -c push.default=matching push git@github.com:acme/demo.git codeb",
        "HOME=/tmp git push git@github.com:acme/demo.git codeb",
        "GIT_CONFIG_PARAMETERS=\"'push.default'='matching'\" git push git@github.com:acme/demo.git codeb",
        "git config push.default matching && git push git@github.com:acme/demo.git codeb",
    ],
)
def test_a_url_push_naming_its_refs_is_judged_beside_settings(proj, monkeypatch, capsys, command):
    """Given project.repo's URL and what it sends, settings don't change it: judged, so a code push is refused."""
    git(proj, "checkout", "-q", "-b", "codeb")
    _code_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, command)
    assert d == "deny" and "src/app.py" in why, (command, why)


def test_a_long_config_parameters_value_doesnt_slow_the_rule(proj, monkeypatch, capsys):
    import time

    t = time.monotonic()
    value = "'" + "x'\\''" * 20_000 + "x'='y'"  # one long valid key, read to its end
    assert guard_mod._config_params_keys(value) == ["x'" * 20_000 + "x"]
    t = time.monotonic()
    d, why = hook(monkeypatch, capsys, proj, f"GIT_CONFIG_PARAMETERS=\"{value}\" git push https://github.com/acme/sandbox x")
    assert time.monotonic() - t < 5 and d == "allow", why[:200]


def test_config_parameters_are_read_as_git_reads_them():
    keys = guard_mod._config_params_keys
    assert keys("'http.x'='y'") == ["http.x"]
    assert keys("'http.x=y'") == ["http.x"]
    assert keys("'core.bare'=") == ["core.bare"]  # git's own spelling of a key set to true
    assert keys("'http.x=a\\' 'url.a.pushinsteadof=b'") == ["http.x", "url.a.pushinsteadof"]
    assert keys("'http.x'='a'\\''b' 'url.y.pushinsteadof'='z'") == ["http.x", "url.y.pushinsteadof"]
    assert keys("'http.x'='remote.y'") == ["http.x"]
    assert keys("not quoted") is None and keys("'unterminated") is None


@pytest.mark.parametrize(
    "command",
    [
        "V=https://github.com/acme/sandbox git --config-env=u{r,r}l.git@github.com:acme/demo.git.pushInsteadOf=V push https://github.com/acme/sandbox codeb",
        "env GIT_CONFIG_PARAMETERS=\\'u{r,r}l.git@github.com:acme/demo.git.pushInsteadOf=https://github.com/acme/sandbox\\' git push https://github.com/acme/sandbox codeb",
        "env GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=u{r,r}l.x.pushInsteadOf GIT_CONFIG_VALUE_0=y git push https://github.com/acme/sandbox codeb",
    ],
)
def test_a_config_key_the_shell_spells_counts(proj, monkeypatch, capsys, command):
    git(proj, "checkout", "-q", "-b", "codeb")
    _code_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, command)
    assert d == "ask" and "can't tell" in why, (command, d, why)


@pytest.mark.parametrize(
    "command",
    [
        "export GIT_CONFIG_KEY_0=remot; export GIT_CONFIG_KEY_0+=e.side.pushurl GIT_CONFIG_COUNT=1 GIT_CONFIG_VALUE_0=git@github.com:acme/demo.git; git push side codeb",
        "read -r GIT_CONFIG_KEY_0 <<< remote.side.pushurl; export GIT_CONFIG_KEY_0 GIT_CONFIG_COUNT=1 GIT_CONFIG_VALUE_0=git@github.com:acme/demo.git; git push side codeb",
        "GIT_CONFIG_VALUE_0=git@github.com:acme/demo.git git push side codeb",
        "GIT_CONFIG_COUNT=1 git push side codeb",
        "GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=user.name GIT_CONFIG_VALUE_0=x GIT_CONFIG_VALUE_1=git@github.com:acme/demo.git git push side codeb",
        "GIT_CONFIG_KEY_0=user.name GIT_CONFIG_VALUE_0=x GIT_CONFIG_VALUE_1=git@github.com:acme/demo.git git push side codeb",
        "GIT_CONFIG_COUNT=² GIT_CONFIG_KEY_0=user.name GIT_CONFIG_VALUE_0=x git push side codeb",
        "GIT_CONFIG_COUNT=" + "0" * 5000 + "1 GIT_CONFIG_KEY_0=user.name GIT_CONFIG_VALUE_0=x git push side codeb",
        "git config [r]emote.side.pushurl git@github.com:acme/demo.git && git push side codeb",
        "git -c [r]emote.side.pushurl=git@github.com:acme/demo.git push side codeb",
    ],
)
def test_config_variables_the_guard_cant_read_whole(proj, tmp_path, monkeypatch, capsys, command):
    git(proj, "remote", "add", "side", str(_other_remote(tmp_path)))
    git(proj, "checkout", "-q", "-b", "codeb")
    _code_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, command)
    assert d == "ask" and "can't tell" in why, (command, d, why)


@pytest.mark.parametrize(
    "command",
    [
        "git push me@backup.example:~/proj.git main",
        "GIT_CONFIG_PARAMETERS=\"'http.extraheader'='Accept: */*'\" git push https://github.com/acme/sandbox x",
        "git -c 'http.https://*.corp.example.proxy=http://p' push https://github.com/acme/sandbox x",
        'cd "$X" && git push ./elsewhere.git main',
        'cd "$X" && git push ../elsewhere.git main',
    ],
)
def test_more_pushes_elsewhere_decide_as_today(proj, monkeypatch, capsys, command):
    _code_commit(proj)
    for role in (None, "conductor"):
        d, why = hook(monkeypatch, capsys, proj, command, role)
        with monkeypatch.context() as m:
            m.setattr(guard_mod, "_push_code", lambda *a, **k: (None, None))
            today = hook(monkeypatch, capsys, proj, command, role)
        assert (d, why) == today, (command, role, why)


def test_a_code_push_beside_a_glob_in_a_setting_is_refused(proj, monkeypatch, capsys):
    git(proj, "checkout", "-q", "-b", "codeb")
    _code_commit(proj)
    for command in (
        "git -c 'http.https://*.corp.example.proxy=http://p' push origin codeb",
        "GIT_CONFIG_PARAMETERS=\"'http.extraheader'='Accept: */*'\" git push https://github.com/acme/demo codeb",
    ):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "deny" and "src/app.py" in why, (command, why)


def test_a_config_variable_named_in_text_changes_nothing(proj, monkeypatch, capsys):
    """Only a variable the command sets counts, not one a message names."""
    git(proj, "checkout", "-q", "-b", "codeb")
    _code_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, 'echo "see GIT_CONFIG_COUNT" && git push origin codeb')
    assert d == "deny" and "src/app.py" in why, why
    command = 'echo "docs: GIT_CONFIG_KEY_<n>" && git push https://github.com/acme/sandbox x'
    assert hook(monkeypatch, capsys, proj, command) == ("allow", "")


def test_settings_variables_are_judged_by_their_keys(proj, monkeypatch, capsys):
    git(proj, "checkout", "-q", "-b", "codeb")
    _code_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, "GIT_CONFIG_PARAMETERS=\"'core.x'='y'\" git push origin codeb")
    assert d == "deny" and "src/app.py" in why, why
    d, why = hook(monkeypatch, capsys, proj, "GIT_CONFIG_PARAMETERS=\"'branch.codeb.pushRemote'='origin'\" git push")
    assert d == "ask" and "can't tell" in why, why


@pytest.mark.parametrize(
    "command",
    [
        "git config push.default current && git push {bak} main",
        'cd "$X" && git push {bak} main',
        "GIT_CONFIG_PARAMETERS=\"'core.bare'=\" git push https://github.com/acme/sandbox x",
    ],
)
def test_a_push_to_a_path_elsewhere_decides_as_today(proj, tmp_path, monkeypatch, capsys, command):
    command = command.format(bak=_other_remote(tmp_path))
    _code_commit(proj)
    for role in (None, "conductor"):
        d, why = hook(monkeypatch, capsys, proj, command, role)
        with monkeypatch.context() as m:
            m.setattr(guard_mod, "_push_code", lambda *a, **k: (None, None))
            today = hook(monkeypatch, capsys, proj, command, role)
        assert (d, why) == today, (command, role, why)


@pytest.mark.parametrize("word", ["~a\x00b", "~\udc80"])
def test_a_path_the_guard_cant_place_beside_a_push(proj, monkeypatch, capsys, word):
    """Asked as a push it can't tell about, never as the guard breaking."""
    _docs_commit(proj)
    for command in (f"git push '{word}' main && git push origin feature", f"git clone x '{word}' && git push origin feature"):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert "isn't working" not in why, why


def test_a_tag_made_beside_a_push_of_tags(proj, monkeypatch, capsys):
    """`--column` takes no next word: `vcode` is the tag git makes."""
    _code_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, "git tag --column vcode && git push origin --tags")
    assert d == "ask" and "can't tell" in why, why


def test_a_code_push_beside_another_remote_added(proj, monkeypatch, capsys):
    _code_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, "git remote add fork https://github.com/me/fork && git push git@github.com:acme/demo.git feature")
    assert d == "deny" and "src/app.py" in why, why


def test_a_long_option_cluster_doesnt_slow_the_rule(proj, monkeypatch, capsys):
    import time

    t = time.monotonic()
    hook(monkeypatch, capsys, proj, "git push -" + "u" * 200_000 + "! origin x && git push origin feature")
    assert time.monotonic() - t < 5


def test_follow_tags_sends_no_commit_the_push_doesnt(proj, monkeypatch, capsys):
    """Only annotated tags on commits the push already sends: a tag on
    another branch's code doesn't count."""
    git(proj, "checkout", "-q", "-b", "code")
    _code_commit(proj)
    git(proj, "tag", "-a", "-m", "t", "vcode")
    git(proj, "checkout", "-q", "feature")
    _docs_commit(proj)
    assert hook(monkeypatch, capsys, proj, "git push --follow-tags origin feature") == ("allow", "")
    assert hook(monkeypatch, capsys, proj, "git push --tags origin feature")[0] == "deny"


def test_tags_alone_send_only_tags(proj, monkeypatch, capsys):
    git(proj, "tag", "vdocs")
    _code_commit(proj)
    for command in ("git push --tags", "git push origin --tags"):
        assert hook(monkeypatch, capsys, proj, command) == ("allow", ""), command
    git(proj, "tag", "vcode")
    assert hook(monkeypatch, capsys, proj, "git push --tags")[0] == "deny"


def test_a_remote_with_a_slash_in_its_name(proj, monkeypatch, capsys):
    git(proj, "remote", "add", "up/stream", "git@github.com:acme/demo.git")
    _code_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, "git push up/stream feature")
    assert d == "deny" and "src/app.py" in why, why


def test_a_remote_nested_in_another_remotes_name_isnt_on_project_repo(proj, tmp_path, monkeypatch, capsys):
    """`origin/fork`'s tracking refs sit under `refs/remotes/origin/`, but it
    fetches from the fork."""
    fork = tmp_path / "fork"
    git(tmp_path, "clone", "-q", str(tmp_path / "proj-remote/acme/demo.git"), str(fork))
    git(fork, "config", "user.email", "t@example.com")
    git(fork, "config", "user.name", "t")
    _code_commit(fork)
    # Written as config: a newer git's `remote add` refuses a name nested in another remote's, but reads one written so.
    git(proj, "config", "remote.origin/fork.url", str(fork))
    git(proj, "config", "remote.origin/fork.fetch", "+refs/heads/*:refs/remotes/origin/fork/*")
    git(proj, "fetch", "-q", str(fork), "+refs/heads/main:refs/remotes/origin/fork/main")
    d, why = hook(monkeypatch, capsys, proj, "git push origin origin/fork/main:refs/heads/fromfork")
    assert d == "deny" and "src/app.py" in why, why


def test_a_remote_from_gits_old_remote_files(proj, monkeypatch, capsys):
    _code_commit(proj)
    (proj / ".git/branches").mkdir(exist_ok=True)
    (proj / ".git/branches/oldbr").write_text("git@github.com:acme/demo.git\n")
    d, why = hook(monkeypatch, capsys, proj, "git push oldbr feature")
    assert d == "ask" and "`.git/remotes` or `.git/branches`" in why, why


def test_a_push_into_another_repository_on_this_machine_doesnt_count(proj, tmp_path, monkeypatch, capsys):
    """Only a push into the repository being judged moves its refs."""
    other = _other_remote(tmp_path)
    git(proj, "remote", "add", "self", ".")
    _docs_commit(proj)
    assert hook(monkeypatch, capsys, proj, f"git push {other} HEAD:refs/heads/x && git push origin feature") == ("allow", "")
    d, why = hook(monkeypatch, capsys, proj, "git push self HEAD:refs/heads/y && git push origin feature")
    assert d == "ask" and "can't tell" in why, why


def test_replacement_objects_dont_hide_what_is_sent(proj, monkeypatch, capsys):
    _code_commit(proj)
    code = git(proj, "rev-parse", "HEAD").strip()
    git(proj, "checkout", "-q", "-b", "d", "origin/main")
    _docs_commit(proj)
    git(proj, "replace", code, git(proj, "rev-parse", "HEAD").strip())
    git(proj, "checkout", "-q", "feature")
    d, why = hook(monkeypatch, capsys, proj, "git push origin feature")
    assert d == "deny" and "src/app.py" in why, why


def test_a_read_that_takes_too_long_is_asked(proj, monkeypatch, capsys):
    _code_commit(proj)
    monkeypatch.setattr(guard_mod, "_GIT_READ_SECONDS", 0)
    d, why = hook(monkeypatch, capsys, proj, "git push origin feature")
    assert d == "ask" and "took too long" in why, why


def test_many_pushes_in_one_command_stay_within_time(proj, monkeypatch, capsys):
    import time

    _docs_commit(proj)
    t = time.monotonic()
    d, why = hook(monkeypatch, capsys, proj, " && ".join(["git push origin feature"] * 300))
    assert time.monotonic() - t < 15 and d == "allow", why[:300]


def test_a_config_value_isnt_a_key(proj, monkeypatch, capsys):
    _docs_commit(proj)
    for command in (
        "git config user.email remote.ops@acme.example && git push origin feature",
        "git config branch.feature.description hi && git push origin feature",
    ):
        assert hook(monkeypatch, capsys, proj, command) == ("allow", ""), command
    d, why = hook(monkeypatch, capsys, proj, "git config --file x.cfg remote.x.url y && git push origin feature")
    assert d == "ask" and "can't tell" in why, why


@pytest.mark.parametrize("command", ["git send-pack {url} feature", "git http-push {url} feature", "git-send-pack {url} feature"])
def test_send_pack_and_http_push_are_judged(proj, tmp_path, monkeypatch, capsys, command):
    url = str(tmp_path / "proj-remote/acme/demo.git")
    _code_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, command.format(url=url))
    assert d == "deny" and "src/app.py" in why, why
    assert hook(monkeypatch, capsys, proj, command.format(url="https://github.com/acme/sandbox")) == ("allow", "")


@pytest.mark.parametrize(
    "command",
    [
        "rm -f {.claude/settings.json," + "{}" * 65 + "}",
        "rm -f {.claude/settings.json,x}" + "{a,b}" * 30,
        "rm -f x" + "{a,b}" * 1001,
    ],
)
def test_a_brace_list_too_long_to_expand_is_a_target_the_guard_cant_place(proj, monkeypatch, capsys, command):
    """A ticket session's write whose brace list names more paths than the
    guard expands is refused, never checked by part of its list (#390's
    change to `_braces`, which stops expanding past its limit)."""
    import time

    _on(proj, "claude/build-1")
    t = time.monotonic()
    d, why = hook(monkeypatch, capsys, proj, command, "ticket")
    assert time.monotonic() - t < 5
    assert d == "deny" and ("brace lists than the guard expands" in why) == command.startswith("rm -f x"), why
    assert "brace lists than the guard expands" in why or "protected path" in why, why


def test_the_first_64_paths_of_a_brace_list_are_still_checked(proj, monkeypatch, capsys):
    _on(proj, "claude/build-1")
    command = "tee {" + ",".join(f"a{i}" for i in range(63)) + ",.claude/workflow/profile.toml} < /dev/null"
    d, why = hook(monkeypatch, capsys, proj, command, "ticket")
    assert d == "deny" and "protected path" in why, why


@pytest.mark.parametrize("role", ["ticket", "conductor"])
@pytest.mark.parametrize("code_writers", ["ticket", "any", None])
def test_a_brace_list_the_guard_expands_decides_as_today(tmp_path, monkeypatch, capsys, role, code_writers):
    """One list of 70 docs paths, or 30 lists: as on main (the first 64 paths checked)."""
    root = _clone(tmp_path, code_writers)
    _on(root, "claude/build-1")
    for command in ("touch docs/{" + ",".join(f"a{i}" for i in range(70)) + "}.md", "mkdir -p docs/x" + "{a,b}" * 30):
        assert hook(monkeypatch, capsys, root, command, role) == ("allow", ""), (command[:40], role, code_writers)


# ---------- which remote is project.repo ----------


@pytest.mark.parametrize(
    "url",
    [
        "git@github.com:acme/demo.git",
        "git@github.com:acme/demo",
        "https://github.com/acme/demo.git",
        "https://github.com/acme/demo/",
        "https://github.com/acme/demo.git/",
        "ssh://git@github.com/Acme/Demo.GIT",
    ],
)
def test_a_remote_naming_project_repo_is_judged(proj, monkeypatch, capsys, url):
    git(proj, "remote", "add", "gh", url)
    _code_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, "git push gh feature")
    assert d == "deny" and "src/app.py" in why, (url, why)
    # Given as a URL rather than a remote's name.
    d, why = hook(monkeypatch, capsys, proj, f"git push {url} feature")
    assert d == "deny" and "src/app.py" in why, (url, why)


@pytest.mark.parametrize(
    "url",
    [
        "github.com/notacme/demo",
        "https://github.com/notacme/demo.git",
        "git@github.com:acme/demo-site.git",
        "https://github.com/acme/demos",
        "https://github.com/acme/demo/other",
    ],
)
def test_a_remote_naming_another_repository_decides_as_today(proj, monkeypatch, capsys, url):
    git(proj, "remote", "add", "gh", url)
    _code_commit(proj)
    assert hook(monkeypatch, capsys, proj, "git push gh feature") == ("allow", ""), url
    assert hook(monkeypatch, capsys, proj, f"git push {url} feature") == ("allow", ""), url


def test_the_push_url_is_the_one_judged(proj, tmp_path, monkeypatch, capsys):
    other = _other_remote(tmp_path)
    _code_commit(proj)
    git(proj, "remote", "add", "o", str(other))
    assert hook(monkeypatch, capsys, proj, "git push o feature")[0] == "allow"
    git(proj, "remote", "set-url", "--push", "o", "git@github.com:acme/demo.git")
    assert hook(monkeypatch, capsys, proj, "git push o feature")[0] == "deny"
    # And the other way: origin pushing elsewhere decides as today.
    git(proj, "remote", "set-url", "--push", "origin", str(other))
    assert hook(monkeypatch, capsys, proj, "git push origin feature")[0] == "allow"


def test_one_of_several_push_urls_naming_project_repo(proj, tmp_path, monkeypatch, capsys):
    other = _other_remote(tmp_path)
    git(proj, "remote", "add", "o", str(other))
    git(proj, "remote", "set-url", "--add", "--push", "o", str(other))
    git(proj, "remote", "set-url", "--add", "--push", "o", "https://github.com/acme/demo")
    _code_commit(proj)
    assert hook(monkeypatch, capsys, proj, "git push o feature")[0] == "deny"


def test_a_remote_through_insteadof_keeps_its_tracking_refs(proj, tmp_path, monkeypatch, capsys):
    """Its URL is read as git fetches from it, so the base's code on its
    tracking refs isn't sent again."""
    bare = str(tmp_path / "proj-remote/acme/demo.git")
    git(proj, "config", f"url.{bare}.insteadOf", "gh:")
    git(proj, "remote", "set-url", "origin", "gh:")
    _docs_commit(proj)
    assert hook(monkeypatch, capsys, proj, "git push origin feature") == ("allow", "")


def test_a_repo_written_with_git_is_still_project_repo(tmp_path, monkeypatch, capsys):
    root = _clone(tmp_path)
    profile = root / ".claude/workflow/profile.toml"
    profile.write_text(profile.read_text().replace('repo = "acme/demo"', 'repo = "acme/demo.git"'))
    _code_commit(root)
    d, why = hook(monkeypatch, capsys, root, "git push origin feature")
    assert d == "deny" and "src/app.py" in why, why


def test_pushes_elsewhere_beside_other_settings_decide_as_today(proj, tmp_path, monkeypatch, capsys):
    other = _other_remote(tmp_path)
    git(proj, "remote", "add", "sandbox", str(other))
    _code_commit(proj)
    for command in (
        "git config user.email bot@example.com && git push https://github.com/acme/sandbox feature",
        "git config user.email bot@example.com && git push sandbox feature",
        "HOME=/tmp git push https://github.com/acme/sandbox feature",
        "git config branch.feature.description hi && git push sandbox feature",
        'cd "$X" && git push https://github.com/acme/sandbox HEAD:refs/heads/x',
    ):
        assert hook(monkeypatch, capsys, proj, command) == ("allow", ""), command


def test_a_push_to_another_repository_by_remote_or_url_decides_as_today(proj, tmp_path, monkeypatch, capsys):
    """The release gate pushes to its sandbox by URL."""
    other = _other_remote(tmp_path)
    git(proj, "remote", "add", "sandbox", str(other))
    _code_commit(proj)
    for command in ("git push sandbox feature", f"git push {other} feature", "git push https://github.com/acme/sandbox.git HEAD:refs/heads/x"):
        assert hook(monkeypatch, capsys, proj, command) == ("allow", ""), command
    # The conductor's push elsewhere is as today too.
    assert hook(monkeypatch, capsys, proj, "git push sandbox feature", "conductor") == ("allow", "")


def test_a_remote_fetching_from_project_repo_has_its_tracking_refs_counted(proj, monkeypatch, capsys):
    """Pushing by URL, the commits on a tracking ref of a remote that fetches
    from `project.repo` are on it already."""
    _code_commit(proj)
    git(proj, "push", "-q", "origin", "feature")
    _docs_commit(proj)
    assert hook(monkeypatch, capsys, proj, "git push git@github.com:acme/demo.git feature")[0] == "allow"


# ---------- can't tell ----------


def test_a_push_whose_commits_cant_be_read_is_asked(proj, monkeypatch, capsys):
    _code_commit(proj)
    d, why = hook(monkeypatch, capsys, proj, "git push origin nosuchbranch")
    assert d == "ask" and "can't tell" in why and "nosuchbranch" in why and "`git log" in why, why
    d, why = hook(monkeypatch, capsys, proj, "git push origin nosuchbranch", "conductor")
    assert d == "deny" and "can't tell" in why and "the conductor" in why, why
    for mode in ("bypassPermissions", "dontAsk"):
        d, why = hook(monkeypatch, capsys, proj, "git push origin nosuchbranch", mode=mode)
        assert d == "deny" and "can't tell" in why, (mode, why)


@pytest.mark.parametrize(
    "command",
    [
        'cd "$X" && git push origin feature',
        "git -C /nonexistent/place push origin feature",
        "git push origin $BRANCH",
        "git push origin `git rev-parse HEAD`",
        "git push origin feature{1..2}",
        "git push --stdin origin",
        "GIT_DIR=.git git push origin feature",
        "git -c remote.origin.pushurl=elsewhere push origin feature",
        "git -c url.x.insteadOf=y push origin feature",
        "git switch -c new && git push origin new",
        "git checkout feature && git push origin HEAD",
        "git reset --hard HEAD~1; git push origin feature",
        "git update-ref refs/heads/feature HEAD && git push origin feature",
        "echo feature | xargs git push origin",
        "git push . HEAD:feature && git push origin feature",
        "git fetch . +HEAD:feature && git push origin feature",
        "/usr/lib/git-core/git-update-ref refs/heads/feature HEAD && git push origin feature",
        "export GIT_DIR=/tmp/elsewhere.git; git push origin HEAD:refs/heads/x",
        "declare -x GIT_CONFIG_GLOBAL=/tmp/gc; git push origin feature",
        "git config remote.origin.pushurl /tmp/x && git push origin feature",
        "git push origin 'heads/*:refs/heads/*'",
        "for d in docs; do git -C $d push origin feature; done",
        "git push -o x . HEAD:feature && git push origin feature",
        "git push --receive-pack x . HEAD:feature && git push origin feature",
        "gh pr checkout 12 && git push origin HEAD:refs/heads/x",
        "git push {origin,} feature",
        "git push $R feature",
        "git push ${R:-origin} feature",
        "git push $(echo origin) feature",
        "git push `echo origin` feature",
        "GIT_CONFIG_PARAMETERS=\"'url.x.pushinsteadof'='y'\" git push https://github.com/acme/sandbox feature",
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=url.x.pushInsteadOf GIT_CONFIG_VALUE_0=y git push https://github.com/acme/sandbox feature",
        "git config branch.feature.pushRemote origin && git push sandbox feature",
    ],
)
def test_more_pushes_the_guard_cant_read(proj, monkeypatch, capsys, command):
    d, why = hook(monkeypatch, capsys, proj, command)
    assert d == "ask" and "can't tell" in why, (command, d, why)
    # In the conductor, refused: by this rule, or first by another that refuses it outright.
    assert hook(monkeypatch, capsys, proj, command, "conductor")[0] == "deny", command


def test_a_config_git_cant_read_is_asked(proj, monkeypatch, capsys):
    _code_commit(proj)
    (proj / ".git/config").write_text((proj / ".git/config").read_text() + "\n[remote \"broken\"\n")
    d, why = hook(monkeypatch, capsys, proj, "git push broken feature")
    assert d == "ask" and "can't tell" in why and "`git " in why, why
    assert hook(monkeypatch, capsys, proj, "git push broken feature", "conductor")[0] == "deny"


def test_a_remote_whose_url_cant_be_read_is_asked(proj, monkeypatch, capsys):
    """A remote git lists but whose URL `git remote get-url` can't give (git
    failing on that one read)."""
    _code_commit(proj)
    git(proj, "remote", "add", "legacy", "https://github.com/acme/demo")
    real = guard_mod._git_read

    def failing(d, glob, *args, **kw):
        if args[:2] == ("remote", "get-url"):
            return None, "`git remote get-url` failed (simulated)"
        return real(d, glob, *args, **kw)

    monkeypatch.setattr(guard_mod, "_git_read", failing)
    d, why = hook(monkeypatch, capsys, proj, "git push legacy feature")
    assert d == "ask" and "couldn't read the URL of the remote `legacy`" in why, why
    assert hook(monkeypatch, capsys, proj, "git push legacy feature", "conductor")[0] == "deny"


def test_a_url_to_another_repository_from_a_directory_the_guard_cant_follow(proj, monkeypatch, capsys):
    """Its commits can't be read, but its destination can: as today."""
    command = 'cd "$X" && git push https://github.com/acme/sandbox.git HEAD:refs/heads/x'
    assert hook(monkeypatch, capsys, proj, command) == ("allow", "")


def test_a_push_the_guard_cant_read_joins_another_ask(proj, monkeypatch, capsys):
    d, why = hook(monkeypatch, capsys, proj, "git push origin nosuchbranch; git push origin HEAD:main")
    assert d == "ask" and "base branch" in why and "nosuchbranch" in why, why


def test_a_push_when_the_guard_cant_decide_is_still_asked(proj, monkeypatch, capsys):
    _code_commit(proj)

    def boom(*a, **k):
        raise RuntimeError("guard-broke-here")

    monkeypatch.setattr(cli.guard_mod, "decide", boom)
    _on(proj, "claude/build-1")  # a branch-only ticket session is asked as an attended one
    assert hook(monkeypatch, capsys, proj, "git push origin claude/build-1")[0] == "ask"
    _on(proj, "feature")
    for role in (None, "tikcet"):
        d, why = hook(monkeypatch, capsys, proj, "git push origin feature", role)
        assert d == "ask", (role, why)
    d, why = hook(monkeypatch, capsys, proj, "git push origin feature", mode="dontAsk")
    assert d == "deny", why
    _docs_commit(proj)
    assert hook(monkeypatch, capsys, proj, "git push origin feature")[0] == "ask"


# ---------- a ticket session, "any" and unanswered ----------


def test_a_ticket_session_pushes_code_as_today(proj, monkeypatch, capsys):
    _on(proj, "claude/build-1")
    _code_commit(proj)
    assert hook(monkeypatch, capsys, proj, "git push origin claude/build-1", "ticket") == ("allow", "")
    assert hook(monkeypatch, capsys, proj, "git push origin nosuchbranch:claude/build-1", "ticket") == ("allow", "")


@pytest.mark.parametrize("code_writers", ["any", None])
def test_any_and_unanswered_decide_as_today(tmp_path, monkeypatch, capsys, code_writers):
    root = _clone(tmp_path, code_writers)
    _code_commit(root)
    git(root, "remote", "add", "gh", "git@github.com:acme/demo.git")
    commands = [
        "git push origin feature",
        "git push gh feature",
        "git push git@github.com:acme/demo.git feature",
        "git push origin nosuchbranch",
        'cd "$X" && git push origin feature',
        "git switch -c new && git push origin new",
    ]
    calls = []
    real = guard_mod._push_code
    monkeypatch.setattr(guard_mod, "_push_code", lambda *a, **k: calls.append(a) or real(*a, **k))
    for command in commands:
        for role in (None, "conductor", "tikcet"):
            d, why = hook(monkeypatch, capsys, root, command, role)
            assert "code path" not in why and "can't tell" not in why, (command, role, why)
    assert calls == []  # never judged: every decision is the rest of the guard's, as today
    # A branch-only ticket session keeps a ticket session's rules.
    _on(root, "claude/build-1")
    assert hook(monkeypatch, capsys, root, "git push origin claude/build-1") == ("allow", "")


# ---------- docs ----------


def test_enforcement_doc_lists_the_push_rule():
    doc = (KIT / "docs/enforcement.md").read_text()
    section = doc[doc.index("**Who writes code**") :]
    for phrase in ("`git push`", "tracking ref", "project.repo", "#390"):
        assert phrase in section, phrase


def test_changelog_note():
    notes = since_0110()
    assert "(#390, part of #338)" in notes and "**A `git push`**" in notes and "test_guard_code_pushes.py" in notes
