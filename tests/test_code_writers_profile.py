"""#339 (spec #338): the profile says who writes code (`guard.code_writers`,
`guard.code_paths`), and which profile counts: the working tree's and the base
branch's as last fetched, the stricter. Through `workflow profile check` and
`workflow status --json` (`cli.main`), and `profile.code_rule`, the one helper
the guard, the hooks, doctor and status call."""

import json
import tomllib

import pytest

from changelog_notes import since_0110
from conftest import KIT, git
from workflow import cli
from workflow import profile as profile_mod

HEAD = '[project]\nname = "demo"\nrepo = "acme/demo"\n'
PROFILE = ".claude/workflow/profile.toml"


def _guard(*lines):
    return HEAD + "[guard]\n" + "".join(line + "\n" for line in lines)


def _env(monkeypatch, root, role=None):
    monkeypatch.chdir(root)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "off")
    for k in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "WORKFLOW_ROLE"):
        monkeypatch.delenv(k, raising=False)
    if role is not None:
        monkeypatch.setenv("WORKFLOW_ROLE", role)


def _write(root, text):
    path = root / PROFILE
    if text is None:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _checkout(tmp_path, base=None, tree=None, branch="main", base_ref="main", files=()):
    """A checkout whose `origin/<base_ref>` (as last fetched) holds the
    profile `base`, on `branch`, with `tree` as its working tree's profile
    (None: deleted). `files` are tracked files of its own."""
    root = tmp_path / "proj"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    for f in files:
        (root / f).parent.mkdir(parents=True, exist_ok=True)
        (root / f).write_text("x\n")
    if base is not None:
        _write(root, base)
    git(root, "add", "-A")
    git(root, "commit", "-q", "--allow-empty", "-m", "base")
    if base is not None:
        git(root, "update-ref", f"refs/remotes/origin/{base_ref}", "HEAD")
    if branch != "main":
        git(root, "checkout", "-q", "-b", branch)
    _write(root, tree)
    return root


def _check(monkeypatch, capsys, root):
    _env(monkeypatch, root)
    code = cli.main(["profile", "check"])
    out = capsys.readouterr()
    return code, out.out, out.err


def _refused(monkeypatch, capsys, root):
    """`profile check`'s error for a profile it refuses."""
    _env(monkeypatch, root)
    assert cli.main(["profile", "check"]) == 1
    return capsys.readouterr().err


def _status(monkeypatch, capsys, root, role=None):
    _env(monkeypatch, root, role)
    assert cli.main(["status", "--json"]) == 0
    return json.loads(capsys.readouterr().out)


# profile check: both keys read


@pytest.mark.parametrize("line, want", [('code_writers = "ticket"', "ticket"), ('code_writers = "any"', "any"), ("", None)])
def test_profile_check_reads_code_writers(tmp_path, monkeypatch, capsys, line, want):
    root = _checkout(tmp_path, tree=_guard(line, 'code_paths = ["src/**"]'))
    code, out, err = _check(monkeypatch, capsys, root)
    assert code == 0, err
    got = json.loads(out)
    assert got["code_writers"] == want and got["code_paths"] == ["src/**"]


def test_code_paths_absent_is_an_empty_list(tmp_path, monkeypatch, capsys):
    root = _checkout(tmp_path, tree=_guard('code_writers = "any"'))
    code, out, err = _check(monkeypatch, capsys, root)
    assert code == 0, err
    assert json.loads(out)["code_paths"] == []


@pytest.mark.parametrize(
    "line", ['code_writers = "Ticket"', 'code_writers = "tickets"', 'code_writers = ""', "code_writers = true", "code_writers = []", "code_writers = 1"]
)
def test_profile_check_refuses_any_other_code_writers(tmp_path, monkeypatch, capsys, line):
    err = _refused(monkeypatch, capsys, _checkout(tmp_path, tree=_guard(line)))
    assert "guard.code_writers" in err and '"ticket"' in err and '"any"' in err


@pytest.mark.parametrize("line", ['code_paths = "src/**"', "code_paths = [1]", "code_paths = true", 'code_paths = [""]', "code_paths = {}"])
def test_profile_check_refuses_a_code_paths_that_isnt_a_list_of_globs(tmp_path, monkeypatch, capsys, line):
    assert "guard.code_paths" in _refused(monkeypatch, capsys, _checkout(tmp_path, tree=_guard(line)))


def test_a_long_bad_code_writers_is_cut_short(tmp_path, monkeypatch, capsys):
    err = _refused(monkeypatch, capsys, _checkout(tmp_path, tree=_guard(f'code_writers = "{"x" * 5000}"')))
    assert "guard.code_writers" in err and len(err) < 400


# profile check: the three warnings


def _warnings(monkeypatch, capsys, root):
    code, out, err = _check(monkeypatch, capsys, root)
    assert code == 0, err
    return json.loads(out)["warnings"]


def test_warns_when_only_ticket_sessions_write_code_and_no_path_is_code(tmp_path, monkeypatch, capsys):
    root = _checkout(tmp_path, tree=_guard('code_writers = "ticket"'))
    assert [w for w in _warnings(monkeypatch, capsys, root) if "guard.code_paths is empty" in w]


@pytest.mark.parametrize("lines", [('code_writers = "any"',), ("",), ('code_writers = "ticket"', 'code_paths = ["src/**"]')])
def test_no_empty_list_warning_otherwise(tmp_path, monkeypatch, capsys, lines):
    root = _checkout(tmp_path, tree=_guard(*lines))
    assert not [w for w in _warnings(monkeypatch, capsys, root) if "code_paths is empty" in w]


def _overlap(warnings):
    return [w for w in warnings if "protected" in w and "code_paths" in w and "both" in w]


def test_warns_of_tracked_files_both_code_and_protected_outside_the_kits_folder(tmp_path, monkeypatch, capsys):
    files = ("src/app.py", "src/deploy/run.py", ".claude/workflow/bin/workflow.py", "docs/x.md")
    tree = _guard('code_writers = "ticket"', 'code_paths = ["src/**", "**/*.py"]',
                  'protected_paths = [".claude/**", ".github/workflows/**", "src/deploy/**"]')
    root = _checkout(tmp_path, tree=tree, files=files)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "tree")
    overlap = _overlap(_warnings(monkeypatch, capsys, root))
    assert len(overlap) == 1, overlap
    assert "src/deploy/run.py" in overlap[0]
    assert ".claude/" not in overlap[0] and "src/app.py" not in overlap[0]


def test_no_overlap_warning_when_only_the_kits_folder_overlaps(tmp_path, monkeypatch, capsys):
    tree = _guard('code_writers = "ticket"', 'code_paths = ["**/*.py"]')
    root = _checkout(tmp_path, tree=tree, files=(".claude/workflow/bin/workflow.py", "app.py"))
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "tree")
    assert not _overlap(_warnings(monkeypatch, capsys, root))


def test_an_untracked_file_isnt_listed_as_overlapping(tmp_path, monkeypatch, capsys):
    tree = _guard('code_paths = ["src/**"]', 'protected_paths = [".claude/**", ".github/workflows/**", "src/**"]')
    root = _checkout(tmp_path, tree=tree)
    (root / "src").mkdir()
    (root / "src/new.py").write_text("x\n")
    assert not _overlap(_warnings(monkeypatch, capsys, root))


def test_many_overlapping_files_are_listed_in_short(tmp_path, monkeypatch, capsys):
    files = tuple(f"src/f{i:02}.py" for i in range(30))
    tree = _guard('code_paths = ["src/**"]', 'protected_paths = [".claude/**", ".github/workflows/**", "src/**"]')
    root = _checkout(tmp_path, tree=tree, files=files)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "tree")
    (w,) = _overlap(_warnings(monkeypatch, capsys, root))
    assert "src/f00.py" in w and "src/f29.py" not in w and "30" in w


@pytest.mark.parametrize(
    "text",
    [
        _guard("code_writers = 'ticket'"),
        _guard('"code_writers" = "ticket"'),
        'guard.code_writers = "ticket"\n' + HEAD,
        'guard = { code_writers = "ticket" }\n' + HEAD,
    ],
    ids=["single quotes", "quoted key", "dotted key", "inline table"],
)
def test_warns_when_code_writers_isnt_a_plain_line(tmp_path, monkeypatch, capsys, text):
    root = _checkout(tmp_path, tree=text)
    spelling = [w for w in _warnings(monkeypatch, capsys, root) if "plain line" in w]
    assert len(spelling) == 1 and 'code_writers = "ticket"' in spelling[0]


@pytest.mark.parametrize("line", ['code_writers = "ticket"', 'code_writers="any"', '  code_writers  =  "ticket"   # only ticket sessions'])
def test_a_plain_line_has_no_spelling_warning(tmp_path, monkeypatch, capsys, line):
    root = _checkout(tmp_path, tree=_guard(line, 'code_paths = ["src/**"]'))
    assert not [w for w in _warnings(monkeypatch, capsys, root) if "plain line" in w]


# status --json: code_writers and writes_code, per kind of session

SESSIONS = [
    # (WORKFLOW_ROLE, branch, writes code under "ticket")
    (None, "main", False),  # attended
    ("conductor", "main", False),
    ("ticket", "claude/build-1", True),
    (" Ticket ", "claude/build-1", True),
    ("ticket", "main", True),
    (None, "claude/build-1", False),  # a ticket session only by its branch
    ("tikcet", "claude/build-1", False),  # a mistyped WORKFLOW_ROLE
]


@pytest.mark.parametrize("role, branch, writes", SESSIONS)
@pytest.mark.parametrize("answer", ["ticket", "any", None])
def test_status_says_who_writes_code(tmp_path, monkeypatch, capsys, role, branch, writes, answer):
    lines = [f'code_writers = "{answer}"' if answer else "", 'code_paths = ["src/**"]']
    root = _checkout(tmp_path, tree=_guard(*lines), branch=branch)
    st = _status(monkeypatch, capsys, root, role)
    assert st["code_writers"] == answer
    assert st["writes_code"] is (writes if answer == "ticket" else True)


def test_status_without_a_profile_is_as_today(tmp_path, monkeypatch, capsys):
    st = _status(monkeypatch, capsys, _checkout(tmp_path))
    assert st["code_writers"] is None and st["writes_code"] is True


# Which profile counts: the base branch's as last fetched, the stricter

TICKET = _guard('code_writers = "ticket"', 'code_paths = ["src/**"]')


@pytest.mark.parametrize(
    "tree",
    [
        _guard('code_writers = "any"', 'code_paths = ["src/**"]'),
        _guard('code_paths = ["src/**"]'),
        _guard('code_writers = "nope"'),
        HEAD + "[guard\n",
        HEAD + "[guard]\nunknown_key = 1\n",
        None,
    ],
    ids=["loosened", "unanswered", "invalid value", "toml broken", "unknown key", "deleted"],
)
def test_the_base_branchs_ticket_wins_over_the_working_tree(tmp_path, monkeypatch, capsys, tree):
    root = _checkout(tmp_path, base=TICKET, tree=tree)
    st = _status(monkeypatch, capsys, root)
    assert st["code_writers"] == "ticket" and st["writes_code"] is False
    assert _status(monkeypatch, capsys, root, "ticket")["writes_code"] is True


def test_the_working_trees_ticket_applies_at_once(tmp_path, monkeypatch, capsys):
    root = _checkout(tmp_path, base=_guard('code_writers = "any"'), tree=TICKET)
    assert _status(monkeypatch, capsys, root)["code_writers"] == "ticket"


def test_any_on_either_side_without_ticket_is_any(tmp_path, monkeypatch, capsys):
    root = _checkout(tmp_path, base=_guard('code_writers = "any"'), tree=_guard(""))
    assert _status(monkeypatch, capsys, root)["code_writers"] == "any"


def test_the_code_path_lists_are_joined(tmp_path, monkeypatch):
    root = _checkout(tmp_path, base=_guard('code_writers = "ticket"', 'code_paths = ["src/**", "lib/**"]'),
                     tree=_guard('code_paths = ["app/**", "src/**"]'))
    _env(monkeypatch, root)
    rule = profile_mod.code_rule(root)
    assert rule.code_writers == "ticket"
    assert rule.code_paths == ["app/**", "src/**", "lib/**"]


def test_the_base_is_read_from_the_working_trees_base_branch(tmp_path, monkeypatch, capsys):
    tree = HEAD.replace('repo = "acme/demo"\n', 'repo = "acme/demo"\nbase_branch = "trunk"\n') + "[guard]\n"
    root = _checkout(tmp_path, base=TICKET, tree=tree, base_ref="trunk")
    assert _status(monkeypatch, capsys, root)["code_writers"] == "ticket"


def test_origin_head_is_the_second_choice(tmp_path, monkeypatch, capsys):
    root = _checkout(tmp_path, base=TICKET, tree=None, base_ref="trunk")
    git(root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
    assert _status(monkeypatch, capsys, root)["code_writers"] == "ticket"


def test_only_what_was_last_fetched_counts(tmp_path, monkeypatch, capsys):
    """The base's profile is read from origin/<base>, never from a local
    branch of that name, which the session itself could change."""
    root = _checkout(tmp_path, tree=_guard('code_writers = "any"'))
    _write(root, TICKET)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "local main only")
    _write(root, _guard('code_writers = "any"'))
    assert _status(monkeypatch, capsys, root)["code_writers"] == "any"


def test_a_base_profile_with_a_key_this_kit_doesnt_know_still_counts(tmp_path, monkeypatch, capsys):
    base = _guard('code_writers = "ticket"', 'code_paths = ["src/**"]', 'protected_paths = [".claude/**", "infra/**"]',
                  "a_later_releases_key = true") + "[a_later_table]\nx = 1\n"
    root = _checkout(tmp_path, base=base, tree=None)
    st = _status(monkeypatch, capsys, root)
    assert st["code_writers"] == "ticket" and st["writes_code"] is False
    rule = profile_mod.code_rule(root)
    assert rule.code_paths == ["src/**"]
    assert rule.protected_paths == [".claude/**", "infra/**"] and rule.repo == "acme/demo" and rule.base_branch == "main"


def test_a_base_profile_whose_toml_doesnt_parse_counts_by_its_plain_line(tmp_path, monkeypatch, capsys):
    base = _guard('code_writers = "ticket"', 'code_paths = ["src/**"') + "[broken\n"
    root = _checkout(tmp_path, base=base, tree=_guard('code_writers = "any"'))
    assert _status(monkeypatch, capsys, root)["code_writers"] == "ticket"


def test_the_working_trees_profile_counts_whole_when_valid(tmp_path, monkeypatch):
    root = _checkout(tmp_path, base=_guard('protected_paths = ["base/**"]'), tree=_guard('protected_paths = [".claude/**", "tree/**"]'))
    _env(monkeypatch, root)
    rule = profile_mod.code_rule(root)
    assert rule.protected_paths == [".claude/**", "tree/**"] and rule.profile is not None and rule.profile.name == "demo"


def test_with_neither_profile_readable_nothing_changes(tmp_path, monkeypatch, capsys):
    st = _status(monkeypatch, capsys, _checkout(tmp_path, tree=HEAD + "[guard\n"))
    assert st["code_writers"] is None and st["writes_code"] is True


def test_outside_a_git_checkout_the_working_tree_alone_counts(tmp_path, monkeypatch):
    root = tmp_path / "plain"
    root.mkdir()
    _write(root, TICKET)
    _env(monkeypatch, root)
    rule = profile_mod.code_rule(root)
    assert rule.code_writers == "ticket" and rule.code_paths == ["src/**"]


# Docs, template and changelog


def _row(text, key):
    return next(line for line in text.splitlines() if line.startswith(f"| `{key}` |"))


def test_docs_profile_names_both_keys():
    doc = (KIT / "docs/profile.md").read_text()
    writers, paths = _row(doc, "code_writers"), _row(doc, "code_paths")
    assert '`"ticket"`' in writers and '`"any"`' in writers and "plain" in writers
    assert "protected" in paths and ".workflow/" in paths and "`[]`" in paths


def test_docs_profile_words_the_branch_fallback_for_both_answers():
    doc = (KIT / "docs/profile.md").read_text()
    for row in (_row(doc, "ticket_branch"), _row(doc, "WORKFLOW_ROLE")):
        assert 'code_writers = "ticket"' in row and "planning session" in row


def test_the_template_has_both_keys_commented_with_code_writers_absent():
    lines = (KIT / "templates/profile.toml").read_text().splitlines()
    assert '# code_writers = "ticket"' in lines
    assert any(line.startswith("# code_paths = [") for line in lines)
    assert not [line for line in lines if line.lstrip().startswith(("code_writers", "code_paths"))]
    at = next(i for i, line in enumerate(lines) if line.startswith("ticket_branch"))
    note = "\n".join(lines[at - 3 : at + 1])
    assert "code_writers" in note and '"ticket"' in note and "planning session" in note


def test_the_template_still_parses_without_the_keys(tmp_path):
    prof = profile_mod.parse(tomllib.loads((KIT / "templates/profile.toml").read_text()), tmp_path)
    assert prof.code_writers is None and prof.code_paths == []


def test_changelog_note():
    notes = since_0110()
    assert "`code_writers`" in notes and "`code_paths`" in notes and "#339" in notes


# Round 1's findings


@pytest.mark.parametrize(
    "tree",
    [
        HEAD + "[sensitive]\npatterns = ['a{4294967295}']\n",  # re.compile raises OverflowError, not re.error
        HEAD + "[ui]\nnotes = " + "[" * 1200 + "]" * 1200 + "\n",  # tomllib's recursion
    ],
    ids=["regex overflow", "deep nesting"],
)
def test_code_rule_never_raises_and_the_bases_ticket_still_counts(tmp_path, monkeypatch, tree):
    root = _checkout(tmp_path, base=TICKET, tree=tree)
    _env(monkeypatch, root)
    rule = profile_mod.code_rule(root)
    assert rule.code_writers == "ticket" and rule.code_paths == ["src/**"]
    (tmp_path / "b").mkdir()
    root2 = _checkout(tmp_path / "b", base=tree, tree=TICKET)
    assert profile_mod.code_rule(root2).code_writers == "ticket"


def test_a_pipe_at_the_profiles_path_is_never_read(tmp_path):
    import os
    import subprocess
    import sys

    root = _checkout(tmp_path, base=TICKET, tree=None)
    os.mkfifo(root / PROFILE)
    env = {k: v for k, v in os.environ.items() if k not in ("WORKFLOW_ROLE", "WORKFLOW_EXPERIENCE")}
    env.update(CLAUDE_PROJECT_DIR=str(root), WORKFLOW_UPDATE_CHECK="off")
    p = subprocess.run([sys.executable, "-B", str(KIT / "scripts/workflow.py"), "status", "--json"], cwd=root, env=env,
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["code_writers"] == "ticket"


@pytest.mark.parametrize("base_branch", ["main~1", "main@{1}", "-main", "main:x"])
def test_a_base_branch_that_isnt_a_branch_name_reads_no_base_by_that_name(tmp_path, monkeypatch, base_branch):
    """A session's own copy can't point the base read at an older commit."""
    root = _checkout(tmp_path, base=_guard('code_writers = "any"'), tree=None)
    _write(root, TICKET)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "ticket")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    tree = HEAD.replace('repo = "acme/demo"\n', f'repo = "acme/demo"\nbase_branch = "{base_branch}"\n') + "[guard]\n"
    _write(root, tree)
    _env(monkeypatch, root)
    assert profile_mod.code_rule(root).code_writers is None


def test_the_plain_line_counts_only_for_a_base_whose_toml_doesnt_parse(tmp_path, monkeypatch):
    base = HEAD + '[ui]\nnotes = """\ncode_writers = "ticket"\n"""\n'
    root = _checkout(tmp_path, base=base, tree=None)
    _env(monkeypatch, root)
    assert profile_mod.code_rule(root).code_writers is None


def test_in_a_base_that_doesnt_parse_any_plain_ticket_line_wins(tmp_path, monkeypatch):
    base = HEAD + '[ui]\nnotes = """\ncode_writers = "any"\n"""\n[guard\ncode_writers = "ticket"\n'
    root = _checkout(tmp_path, base=base, tree=None)
    _env(monkeypatch, root)
    assert profile_mod.code_rule(root).code_writers == "ticket"


def test_no_spelling_warning_when_the_plain_line_is_there_beside_another(tmp_path, monkeypatch, capsys):
    tree = HEAD + '[ui]\nnotes = """\ncode_writers = "any"\n"""\n[guard]\ncode_writers = "ticket"\ncode_paths = ["src/**"]\n'
    root = _checkout(tmp_path, tree=tree)
    assert not [w for w in _warnings(monkeypatch, capsys, root) if "plain line" in w]


def test_one_overlapping_file_is_worded_as_one(tmp_path, monkeypatch, capsys):
    tree = _guard('code_paths = ["lib/**"]', 'protected_paths = [".claude/**", ".github/workflows/**", "lib/x.py"]')
    root = _checkout(tmp_path, tree=tree, files=("lib/x.py",))
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "tree")
    (w,) = _overlap(_warnings(monkeypatch, capsys, root))
    assert "1 tracked file, which counts as protected" in w


def test_the_empty_list_warning_says_only_what_is_true(tmp_path, monkeypatch, capsys):
    root = _checkout(tmp_path, tree=_guard('code_writers = "ticket"'))
    (w,) = [w for w in _warnings(monkeypatch, capsys, root) if "code_paths is empty" in w]
    assert "refuses nothing" not in w


def test_uncommenting_the_templates_key_leaves_a_valid_profile(tmp_path):
    tpl = (KIT / "templates/profile.toml").read_text()
    on = tpl.replace('# code_writers = "ticket"', 'code_writers = "ticket"').replace("# code_paths = [", "code_paths = [")
    prof = profile_mod.parse(tomllib.loads(on), tmp_path)
    assert prof.code_writers == "ticket" and prof.code_paths


# Round 2's findings


def test_the_conductor_follows_a_planning_sessions_rules_and_isnt_called_one():
    """Spec #338: every session other than a ticket session and the conductor
    is a planning session; the conductor follows a planning session's rules."""
    doc = (KIT / "docs/profile.md").read_text()
    tpl = (KIT / "templates/profile.toml").read_text()
    row = _row(doc, "code_writers")
    assert "the conductor included, is a planning session" not in row
    assert "the conductor follows a planning session's rules" in row
    at = tpl.index('# code_writers = "ticket"')
    assert "the conductor follows a planning session's rules" in " ".join(
        line.lstrip("# ").strip() for line in tpl[:at].splitlines()[-6:]
    )
