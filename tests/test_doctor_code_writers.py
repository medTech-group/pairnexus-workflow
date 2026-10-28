"""#344 (spec #338): doctor's `kit.code_writers` line says where the choice of
who writes code stands. Through `workflow doctor --json`, as test_doctor.py
runs it: a note while `guard.code_writers` is unanswered, and one under
`"ticket"` while no ticket environment is named (worded for plugin mode,
which has no unattended runs, too); no note under `"any"`, or under
`"ticket"` with a ticket environment named."""

import shutil

import pytest

from changelog_notes import since_0110
from conftest import git
from test_doctor import RUN, _bin, _lines, _prof, _project, _report
from workflow import vendor

# The tests' repositories never see the developer's own git configuration.
pytestmark = pytest.mark.usefixtures("_no_user_git_config")

NEW = {"WORKFLOW_EXPERIENCE": "new"}
DEV = {"WORKFLOW_EXPERIENCE": "developer"}
PLUGIN = {"enabledPlugins": {vendor.PLUGIN_KEY: True}}
NO_TICKET_ENV = RUN.replace('ticket_environment = "t"\n', "")
# A profile with a key this kit doesn't know (a later release's, or a typo).
LATER = '[project]\nname = "demo"\nnot_a_key = 1\n'


def _guard(writers):
    return '[guard]\ncode_writers = "%s"\ncode_paths = ["src/**"]\n' % writers


def _profile(writers=None, run=RUN):
    """A profile answering `code_writers` with `writers` (None: unanswered),
    with `run` as its [run] table."""
    return _prof("ruleset = true\n", _guard(writers) if writers else "").replace(RUN, run)


def _both(tmp_path, root, **kw):
    """The line in each wording: (new, developer)."""
    return tuple(_lines(_report(tmp_path / w, root, env=env, **kw))["kit.code_writers"] for w, env in (("new", NEW), ("dev", DEV)))


@pytest.mark.parametrize("vendored", [True, False], ids=["vendored", "plugin"])
def test_unanswered_is_a_note_whose_fix_is_choose_who_writes_code(tmp_path, vendored):
    root = _project(tmp_path, profile=_profile(), vendored=vendored, settings=None if vendored else PLUGIN)
    for ln in _both(tmp_path, root):
        assert ln["status"] == "note", ln
        assert "Choose who writes code" in ln["fix"], ln
        assert ln["group"] == "The kit"


def test_ticket_without_a_ticket_environment_is_a_note_that_nothing_writes_code(tmp_path):
    root = _project(tmp_path, profile=_profile("ticket", NO_TICKET_ENV))
    new, dev = _both(tmp_path, root)
    for ln in (new, dev):
        assert ln["status"] == "note", ln
        assert ln["offer"] == "set_up_unattended_runs", ln
        assert "Set up unattended runs" in ln["fix"] and "by hand" in ln["fix"], ln
    assert "nothing writes code until" in new["message"].lower(), new
    assert "nothing writes code until" in dev["message"].lower() and "run.ticket_environment" in dev["message"], dev
    assert new["message"] != dev["message"]


def test_ticket_without_a_ticket_environment_in_plugin_mode_names_the_owners_own_ticket_session(tmp_path):
    root = _project(tmp_path, profile=_profile("ticket", NO_TICKET_ENV), vendored=False, settings=PLUGIN)
    new, dev = _both(tmp_path, root)
    for ln in (new, dev):
        assert ln["status"] == "note", ln
        assert ln["offer"] is None, ln
        both = ln["message"] + " " + ln["fix"]
        assert "WORKFLOW_ROLE=ticket" in both, ln
        assert "Set up unattended runs" not in both, ln
        # The rule holds only where the plugin is installed: a cloud session has no kit and no guard.
        assert "cloud session" in ln["message"] and "plugin" in ln["message"], ln
    assert "your computer" in new["message"], new
    assert new["message"] != dev["message"]


@pytest.mark.parametrize("writers, run", [("any", RUN), ("any", NO_TICKET_ENV), ("ticket", RUN)],
                         ids=["any", "any-no-ticket-environment", "ticket-with-a-ticket-environment"])
@pytest.mark.parametrize("vendored", [True, False], ids=["vendored", "plugin"])
def test_no_note_under_any_or_under_ticket_with_a_ticket_environment(tmp_path, writers, run, vendored):
    root = _project(tmp_path, profile=_profile(writers, run), vendored=vendored, settings=None if vendored else PLUGIN)
    new, dev = _both(tmp_path, root)
    for ln in (new, dev):
        assert (ln["status"], ln["fix"], ln["offer"]) == ("fine", "", None), ln
    assert new["message"] != dev["message"]


def test_in_plugin_mode_a_ticket_environment_named_is_never_where_the_rule_holds(tmp_path):
    """A cloud session has no kit and no guard: the line says so, and never
    that ticket sessions run in the cloud environment the profile names."""
    root = _project(tmp_path, profile=_profile("ticket", RUN), vendored=False, settings=PLUGIN)
    for ln in _both(tmp_path, root):
        assert ln["status"] == "fine", ln
        assert "WORKFLOW_ROLE=ticket" in ln["message"] and "no kit and no guard" in ln["message"], ln
        assert "`t`" not in ln["message"], ln


@pytest.mark.parametrize("profile, fix", [(None, "set the kit up"), (LATER, "correct the kit's profile")],
                         ids=["no-profile", "invalid-profile"])
def test_without_a_readable_profile_it_cant_check(tmp_path, profile, fix):
    root = _project(tmp_path, profile=profile)
    new, dev = _both(tmp_path, root)
    assert (new["status"], dev["status"]) == ("cant_check", "cant_check"), (new, dev)
    assert fix in new["fix"], new
    assert "kit.profile" in dev["fix"], dev


def _with_base(tmp_path, root, tree, ref="main"):
    """Make `root` a checkout whose `origin/<ref>`, as last fetched, holds its
    profile as it is now, then write `tree` (None: deleted; True: kept) as
    its working tree's; the PATH doctor runs with, with git on it."""
    git(root, "init", "-q", "-b", "main")
    git(root, "add", ".claude/workflow/profile.toml")
    git(root, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "profile")
    git(root, "update-ref", f"refs/remotes/origin/{ref}", "HEAD")
    path = root / ".claude/workflow/profile.toml"
    if tree is None:
        path.unlink()
    elif tree is not True:
        path.write_text(tree)
    bin_dir = _bin(tmp_path)
    (bin_dir / "git").symlink_to(shutil.which("git"))
    return bin_dir


@pytest.mark.parametrize("tree", [_profile(None, NO_TICKET_ENV), _profile("any", NO_TICKET_ENV)], ids=["unanswered", "any"])
def test_the_base_branchs_ticket_counts_over_a_working_tree_that_says_less(tmp_path, tree):
    """Who writes code is the profile that counts (`profile.code_rule`): the
    base's `"ticket"`, as last fetched, beats a working tree that doesn't
    answer or says `"any"`, and the line says where it comes from."""
    root = _project(tmp_path, profile=_profile("ticket", NO_TICKET_ENV))
    new, dev = _both(tmp_path, root, path=_with_base(tmp_path, root, tree))
    for ln in (new, dev):
        assert (ln["status"], ln["offer"]) == ("note", "set_up_unattended_runs"), ln
        assert "Choose who writes code" not in ln["fix"], ln
    assert "`main` branch's profile says so" in new["message"], new
    assert "from origin/main" in dev["message"], dev


@pytest.mark.parametrize("vendored", [True, False], ids=["vendored", "plugin"])
def test_the_base_is_named_beside_who_writes_code_never_beside_the_working_trees_environment(tmp_path, vendored):
    """The working tree says `"any"` and names the ticket environment; the
    base says `"ticket"`: the base is named for who writes code alone."""
    root = _project(tmp_path, profile=_profile("ticket", NO_TICKET_ENV), vendored=vendored, settings=None if vendored else PLUGIN)
    new, dev = _both(tmp_path, root, path=_with_base(tmp_path, root, _profile("any", RUN)))
    for ln in (new, dev):
        assert ln["status"] == "fine", ln
    assert new["message"].startswith("Only ticket sessions write code") and "branch's profile says so" in new["message"], new
    assert "from origin/main" in dev["message"], dev
    if vendored:
        said, env = new["message"].index("branch's profile says so"), new["message"].index("`t`")
        assert said < env and "Their cloud environment is `t`." in new["message"], new


def test_the_base_read_from_origin_head_is_the_base_branch(tmp_path):
    """No `origin/main`: the base's profile is read from `origin/HEAD`, and the
    line names that, never `main`."""
    root = _project(tmp_path, profile=_profile("ticket", NO_TICKET_ENV))
    new, dev = _both(tmp_path, root, path=_with_base(tmp_path, root, _profile(None, NO_TICKET_ENV), ref="HEAD"))
    assert "The base branch's profile says so" in new["message"] and "`main`" not in new["message"], new
    assert "from origin/HEAD" in dev["message"], dev


@pytest.mark.parametrize("tree", [True, None, LATER], ids=["ticket", "missing", "invalid"])
def test_it_names_no_base_unless_a_working_tree_profile_says_less(tmp_path, tree):
    """A working tree that says `"ticket"` itself, or has no readable profile
    to count over (the profile line says so), names no base."""
    root = _project(tmp_path, profile=_profile("ticket", NO_TICKET_ENV))
    new, dev = _both(tmp_path, root, path=_with_base(tmp_path, root, tree))
    for ln in (new, dev):
        assert (ln["status"], ln["offer"]) == ("note", "set_up_unattended_runs"), ln
        assert "branch's profile" not in ln["message"] and "origin/main" not in ln["message"], ln


@pytest.mark.parametrize("writers", ["ticket", "any"])
def test_a_base_this_kit_cant_read_whole_still_says_its_answer(tmp_path, writers):
    """No working tree's profile, and a base with a key this kit doesn't
    know (a later release's): its `"ticket"` counts while its ticket
    environment can't be read; its `"any"` needs no ticket environment."""
    root = _project(tmp_path, profile=LATER + _guard(writers))
    new, dev = _both(tmp_path, root, path=_with_base(tmp_path, root, None))
    if writers == "any":
        assert (new["status"], dev["status"]) == ("fine", "fine"), (new, dev)
        return
    assert (new["status"], dev["status"]) == ("cant_check", "cant_check"), (new, dev)
    assert new["message"].startswith("Only ticket sessions write code") and "can't be told" in new["message"], new
    assert 'guard.code_writers = "ticket" (origin/main)' in dev["message"], dev


def test_the_changelog_has_a_note():
    notes = since_0110()
    assert "#344" in notes and "kit.code_writers" in notes
