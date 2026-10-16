"""#106: `workflow adopt` makes a copy of the starter the person's own, on a
temporary checkout shaped like the starter (#40's seam 2), as `vendor`'s tests
use temporary checkouts. The starter's real files are checked by hand (#40)."""

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from conftest import KIT, git

from workflow import adopt, updates

CLI = KIT / "scripts/workflow.py"

PROFILE = """\
# The project's workflow profile.

[project]
name = "pairnexus-starter-web"
repo = "medTech-group/pairnexus-starter-web" # GitHub owner/repo of the issue tracker
base_branch = "main"
owner = "old-owner"                # optional: the owner's GitHub login, without the @
rules = ["CLAUDE.md"]
ruleset = false
experience = "new"

[commands]
setup = "npm ci"
setup_check = "test -d node_modules"
typecheck = "npx tsc --noEmit"
test_file = "npx vitest run {file}"

[[commands.suite]]
name = "unit"
run = "npx vitest run {files}"
files = "test/**/*.test.ts"
group = 8

[ui]
explorer = "browser"
"""

CODEOWNERS = """\
# The owner reviews the kit's files and the workflows.
* @old-owner
/.claude/ @old-owner
/.github/workflows/ @Old-Owner @medTech-group/maintainers
/docs/ @old-owner-bot
"""

WRANGLER = """\
#:schema node_modules/wrangler/config-schema.json
name = "pairnexus-starter-web"   # the Worker's name: unique per Cloudflare account
main = "src/worker/index.ts"
compatibility_date = "2026-09-01"

[assets]
directory = "./dist/client"

[[d1_databases]]
binding = "DB"
database_name = "notes"
migrations_dir = "migrations"

[previews]
name = "keep-me"
"""

PACKAGE = """{
  "name": "pairnexus-starter-web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "test": "vitest run"
  },
  "devDependencies": {
    "name": "not-this-one",
    "vitest": "^3.2.0"
  }
}
"""

README = """\
<!-- the starter's README -->
# pairnexus-starter-web

A notes app: type a note, save it, see it listed.

```md
# not this one
```
"""

OTHER = {
    "CLAUDE.md": "# pairnexus-starter-web\n\nRules for medTech-group/pairnexus-starter-web.\n",
    "src/worker/index.ts": 'export default { name: "pairnexus-starter-web" };\n',
    "migrations/0001_notes.sql": "CREATE TABLE notes (id INTEGER PRIMARY KEY, text TEXT);\n",
    ".claude/workflow/profile.md": "# old-owner's notes\n",
    ".github/workflows/ci.yml": "name: ci\n",
}


def _starter(root: Path, crlf: bool = False) -> Path:
    files = {
        ".claude/workflow/profile.toml": PROFILE,
        ".github/CODEOWNERS": CODEOWNERS,
        "wrangler.toml": WRANGLER,
        "package.json": PACKAGE,
        "README.md": README,
        **OTHER,
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))
    git(root, "init", "-q", "-b", "main")
    return root


def _snapshot(root: Path) -> dict[str, bytes]:
    """Every file outside .git, byte for byte."""
    files = (p for p in sorted(root.rglob("*")) if p.is_file())
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in files if p.relative_to(root).parts[0] != ".git"}


def _cli(root: Path, *args):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root)}
    return subprocess.run([sys.executable, "-B", str(CLI), *args], capture_output=True, text=True, cwd=root, env=env)


def _run(root: Path, owner="ada", repo="ada/my-notes", name="My Notes!"):
    return _cli(root, "adopt", f"--owner={owner}", f"--repo={repo}", f"--name={name}")


@pytest.fixture
def copy(tmp_path):
    return _starter(tmp_path / "copy")


# The rewrite.


def test_adopt_rewrites_the_names_and_nothing_else(copy):
    before = _snapshot(copy)
    p = _run(copy)
    assert p.returncode == 0, p.stderr
    after = _snapshot(copy)

    names = {".claude/workflow/profile.toml", ".github/CODEOWNERS", "wrangler.toml", "package.json", "README.md"}
    assert set(after) == set(before)
    for rel in set(before) - names:
        assert after[rel] == before[rel], rel
    for rel in names:
        assert after[rel] != before[rel], rel

    prof = tomllib.loads(after[".claude/workflow/profile.toml"].decode())
    assert prof["project"]["owner"] == "ada"
    assert prof["project"]["name"] == "My Notes!"
    assert prof["project"]["repo"] == "ada/my-notes"
    assert tomllib.loads(after["wrangler.toml"].decode())["name"] == "my-notes"
    assert json.loads(after["package.json"])["name"] == "my-notes"
    assert after["README.md"].decode().splitlines()[1] == "# My Notes!"

    for line in ("Changed .claude/workflow/profile.toml: project.owner, project.name, project.repo",
                 "Changed .github/CODEOWNERS: @old-owner → @ada",
                 "Changed wrangler.toml: name = my-notes",
                 "Changed package.json: name = my-notes",
                 "Changed README.md: title = My Notes!"):
        assert line in p.stdout.splitlines()


def test_comments_order_and_formatting_are_kept(copy):
    assert _run(copy).returncode == 0
    prof = (copy / ".claude/workflow/profile.toml").read_text()
    assert prof == (PROFILE
                    .replace('name = "pairnexus-starter-web"', 'name = "My Notes!"')
                    .replace('repo = "medTech-group/pairnexus-starter-web"', 'repo = "ada/my-notes"')
                    .replace('owner = "old-owner"', 'owner = "ada"'))
    assert (copy / ".github/CODEOWNERS").read_text() == """\
# The owner reviews the kit's files and the workflows.
* @ada
/.claude/ @ada
/.github/workflows/ @ada @medTech-group/maintainers
/docs/ @old-owner-bot
"""
    # Only the top-level name: [previews] keeps its own.
    assert (copy / "wrangler.toml").read_text() == WRANGLER.replace(
        'name = "pairnexus-starter-web"   #', 'name = "my-notes"   #')
    assert (copy / "package.json").read_text() == PACKAGE.replace('"name": "pairnexus-starter-web"', '"name": "my-notes"')
    assert (copy / "README.md").read_text() == README.replace("# pairnexus-starter-web\n", "# My Notes!\n")


def test_line_endings_are_kept(tmp_path):
    copy = _starter(tmp_path / "copy", crlf=True)
    assert _run(copy).returncode == 0
    for rel in (".claude/workflow/profile.toml", ".github/CODEOWNERS", "wrangler.toml", "package.json", "README.md"):
        data = (copy / rel).read_bytes()
        assert b"\n" not in data.replace(b"\r\n", b""), rel


def test_a_second_run_changes_nothing_and_says_so(copy):
    assert _run(copy).returncode == 0
    once = _snapshot(copy)
    p = _run(copy)
    assert p.returncode == 0, p.stderr
    assert _snapshot(copy) == once
    assert "Already yours: nothing to change." in p.stdout
    assert "Changed" not in p.stdout


def test_the_rewritten_profile_passes_profile_check(copy):
    assert _run(copy).returncode == 0
    p = _cli(copy, "profile", "check")
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert out["ok"] and out["repo"] == "ada/my-notes"


def test_an_owner_the_profile_left_out_is_added_under_repo(tmp_path):
    copy = _starter(tmp_path / "copy")
    path = copy / ".claude/workflow/profile.toml"
    path.write_text(PROFILE.replace('owner = "old-owner"                # optional: the owner\'s GitHub login, without the @\n', ""))
    p = _run(copy)
    assert p.returncode == 0, p.stderr
    lines = path.read_text().splitlines()
    assert lines[lines.index('repo = "ada/my-notes" # GitHub owner/repo of the issue tracker') + 1] == 'owner = "ada"'
    # With no old owner, CODEOWNERS has nothing to replace.
    assert (copy / ".github/CODEOWNERS").read_text() == CODEOWNERS
    assert "Skipped .github/CODEOWNERS: the profile named no owner to replace" in p.stdout


# Missing files and refusals.


def test_a_missing_file_is_skipped_with_a_note_never_created(copy):
    (copy / "wrangler.toml").unlink()
    (copy / ".github/CODEOWNERS").unlink()
    p = _run(copy)
    assert p.returncode == 0, p.stderr
    assert not (copy / "wrangler.toml").exists()
    assert not any((copy / c).exists() for c in adopt.CODEOWNERS_PATHS)
    assert "Skipped wrangler.toml: not there" in p.stdout
    assert "Skipped CODEOWNERS: not there" in p.stdout
    assert json.loads((copy / "package.json").read_text())["name"] == "my-notes"


def test_a_top_level_value_that_reads_name_isnt_taken_for_the_key(copy):
    (copy / "package.json").write_text('{\n  "description": "name",\n  "keywords": ["name"],\n  "name": "pairnexus-starter-web"\n}\n')
    assert _run(copy).returncode == 0
    assert (copy / "package.json").read_text() == '{\n  "description": "name",\n  "keywords": ["name"],\n  "name": "my-notes"\n}\n'


def test_codeowners_at_the_root_is_found(copy):
    (copy / ".github/CODEOWNERS").rename(copy / "CODEOWNERS")
    assert _run(copy).returncode == 0
    assert "* @ada" in (copy / "CODEOWNERS").read_text()


@pytest.mark.parametrize("repo", ["ada", "ada/notes/more", "/notes", "ada/", "ada notes/x", "https://github.com/ada/notes", ""])
def test_a_bad_repo_is_refused_and_nothing_changes(copy, repo):
    before = _snapshot(copy)
    p = _run(copy, repo=repo)
    assert p.returncode == 1
    assert "--repo must be owner/name" in p.stderr
    assert _snapshot(copy) == before


@pytest.mark.parametrize("name", ["!!!", "  ", "—", "two\nlines"])
def test_a_name_that_makes_an_empty_worker_name_is_refused(copy, name):
    before = _snapshot(copy)
    p = _run(copy, name=name)
    assert p.returncode == 1
    assert "--name" in p.stderr
    assert _snapshot(copy) == before


def test_a_bad_owner_is_refused(copy):
    before = _snapshot(copy)
    p = _run(copy, owner="ada lovelace")
    assert p.returncode == 1 and "--owner" in p.stderr
    assert _snapshot(copy) == before


def test_an_owner_given_with_its_at_is_taken(copy):
    assert _run(copy, owner="@ada").returncode == 0
    assert tomllib.loads((copy / ".claude/workflow/profile.toml").read_text())["project"]["owner"] == "ada"


def test_no_profile_is_refused(copy):
    (copy / ".claude/workflow/profile.toml").unlink()
    before = _snapshot(copy)
    p = _run(copy)
    assert p.returncode == 1 and "no profile" in p.stderr
    assert _snapshot(copy) == before


def test_a_line_it_cant_rewrite_is_refused_and_nothing_changes(copy):
    (copy / "wrangler.toml").write_text(WRANGLER.replace('name = "pairnexus-starter-web"', 'name = """pairnexus-starter-web"""'))
    before = _snapshot(copy)
    p = _run(copy)
    assert p.returncode == 1 and "wrangler.toml" not in p.stdout
    assert _snapshot(copy) == before


def test_a_name_with_quotes_stays_valid_toml_and_json(copy):
    assert _run(copy, name='Ada\'s "Notes" \\ App').returncode == 0
    assert tomllib.loads((copy / ".claude/workflow/profile.toml").read_text())["project"]["name"] == 'Ada\'s "Notes" \\ App'
    assert tomllib.loads((copy / "wrangler.toml").read_text())["name"] == "ada-s-notes-app"
    assert json.loads((copy / "package.json").read_text())["name"] == "ada-s-notes-app"


def test_dashed():
    assert adopt.dashed("My Notes!") == "my-notes"
    assert adopt.dashed("  Notes_2026  app ") == "notes-2026-app"
    assert adopt.dashed("!!!") == ""
    assert len(adopt.dashed("a" * 100)) == adopt.WORKER_NAME_MAX
    assert not adopt.dashed("a" * 62 + " b").endswith("-")


# The starter's home.


def test_version_starter_prints_the_constant_with_no_network(tmp_path):
    assert updates.STARTER_REPO == "medTech-group/pairnexus-starter-web"
    env = {k: v for k, v in os.environ.items() if k != "WORKFLOW_UPDATE_CHECK"}
    # A proxy that can't be reached: any network call would fail or hang.
    env.update(HTTPS_PROXY="http://127.0.0.1:9", HTTP_PROXY="http://127.0.0.1:9", PATH="", CLAUDE_PROJECT_DIR=str(tmp_path))
    p = subprocess.run([sys.executable, "-B", str(CLI), "version", "--starter"], capture_output=True, text=True, cwd=tmp_path, env=env, timeout=20)
    assert p.returncode == 0, p.stderr
    assert p.stdout == "medTech-group/pairnexus-starter-web\n"


def test_version_starter_reads_nothing_else(monkeypatch, capsys):
    from workflow import cli

    monkeypatch.setattr(updates, "check", lambda *a, **k: pytest.fail("asked for the latest release"))
    assert cli.main(["version", "--starter"]) == 0
    assert capsys.readouterr().out == updates.STARTER_REPO + "\n"


# Review round 1's cases.


def test_a_failed_write_leaves_the_profile_so_a_rerun_finishes(copy, monkeypatch):
    real = adopt._write

    def failing(path, data):
        if path.name == "CODEOWNERS":
            raise OSError(28, "No space left on device")
        real(path, data)

    monkeypatch.setattr(adopt, "_write", failing)
    with pytest.raises(adopt.AdoptError, match="couldn't write .github/CODEOWNERS: No space left on device"):
        adopt.adopt(copy, "ada", "ada/my-notes", "My Notes!")
    assert (copy / ".claude/workflow/profile.toml").read_text() == PROFILE
    monkeypatch.setattr(adopt, "_write", real)
    adopt.adopt(copy, "ada", "ada/my-notes", "My Notes!")
    assert "* @ada" in (copy / ".github/CODEOWNERS").read_text()
    assert not [p for p in copy.rglob(".*.*") if p.is_file() and p.name.startswith((".CODEOWNERS.", ".profile.toml."))]


def test_a_write_error_is_refused_in_words(copy, monkeypatch):
    monkeypatch.setattr(adopt.os, "replace", lambda *a: (_ for _ in ()).throw(PermissionError(13, "Permission denied")))
    from workflow import cli

    monkeypatch.chdir(copy)
    assert cli.main(["adopt", "--owner", "ada", "--repo", "ada/my-notes", "--name", "x", "--project", str(copy)]) == 1


def test_an_email_owner_isnt_rewritten(copy):
    (copy / ".github/CODEOWNERS").write_text("* @old-owner ops@old-owner.example\n")
    assert _run(copy).returncode == 0
    assert (copy / ".github/CODEOWNERS").read_text() == "* @ada ops@old-owner.example\n"


def test_codeowners_without_the_old_owner_gets_a_note(copy):
    (copy / ".github/CODEOWNERS").write_text("* @medTech-group/maintainers\n")
    p = _run(copy)
    assert p.returncode == 0
    assert "Left .github/CODEOWNERS as it is: it doesn't name @old-owner" in p.stdout


def test_an_owner_goes_in_under_a_last_line_without_a_newline(copy):
    path = copy / ".claude/workflow/profile.toml"
    path.write_text('[project]\nname = "x"\nrepo = "a/b"')
    assert _run(copy).returncode == 0
    assert path.read_text() == '[project]\nname = "My Notes!"\nrepo = "ada/my-notes"\nowner = "ada"'


def test_a_value_already_right_in_other_quotes_is_left(copy):
    path = copy / ".claude/workflow/profile.toml"
    text = PROFILE.replace('name = "pairnexus-starter-web"', "name = 'My Notes!'").replace('repo = "medTech-group/pairnexus-starter-web"', "repo = 'ada/my-notes'")
    path.write_text(text)
    assert _run(copy).returncode == 0
    assert path.read_text() == text.replace('owner = "old-owner"', 'owner = "ada"')


def test_a_bom_is_kept_and_the_title_after_it_found(copy):
    (copy / "README.md").write_bytes(b"\xef\xbb\xbf# old\n\n# second\n")
    (copy / "package.json").write_bytes(b'\xef\xbb\xbf{"name": "old"}\n')
    assert _run(copy).returncode == 0
    assert (copy / "README.md").read_bytes() == b"\xef\xbb\xbf# My Notes!\n\n# second\n"
    assert (copy / "package.json").read_bytes() == b'\xef\xbb\xbf{"name": "my-notes"}\n'


def test_decoys_before_the_real_names_are_left(copy):
    (copy / "README.md").write_text("<!--\n# in a comment\n-->\n```\n# in a fence\n```\n# old\n")
    (copy / "package.json").write_text('{"repository": {"name": "decoy"}, "name": "old"}\n')
    (copy / "wrangler.toml").write_text('[previews]\nname = "keep-me"\n')
    p = _run(copy)
    assert p.returncode == 0
    assert (copy / "README.md").read_text() == "<!--\n# in a comment\n-->\n```\n# in a fence\n```\n# My Notes!\n"
    assert (copy / "package.json").read_text() == '{"repository": {"name": "decoy"}, "name": "my-notes"}\n'
    assert (copy / "wrangler.toml").read_text() == '[previews]\nname = "keep-me"\n'
    assert "Skipped wrangler.toml: no top-level name" in p.stdout


@pytest.mark.parametrize("repo", ["ada/..", "ada/.", "-ada/x", "ada-/x", "ada--x/y"])
def test_repos_github_refuses_are_refused(copy, repo):
    assert _run(copy, repo=repo).returncode == 1


def test_a_name_with_no_ascii_says_so(copy):
    p = _run(copy, name="笔记")
    assert p.returncode == 1 and "no ASCII letters or digits" in p.stderr


# Review round 1: the explorer's cases.


def test_an_empty_project_is_refused(copy):
    before = _snapshot(copy)
    p = _cli(copy, "adopt", "--owner=ada", "--repo=ada/x", "--name=x", "--project=")
    assert p.returncode == 1 and "--project is empty" in p.stderr
    assert _snapshot(copy) == before


def test_a_rerun_after_a_failed_write_says_nothing_about_codeowners(copy, monkeypatch):
    real = adopt._write
    monkeypatch.setattr(adopt, "_write", lambda path, data: (_ for _ in ()).throw(OSError(28, "full")) if path.name == "package.json" else real(path, data))
    with pytest.raises(adopt.AdoptError):
        adopt.adopt(copy, "ada", "ada/my-notes", "My Notes!")
    monkeypatch.setattr(adopt, "_write", real)
    r = adopt.adopt(copy, "ada", "ada/my-notes", "My Notes!")
    assert not any("CODEOWNERS" in n for n in r.notes)
    assert [path for path, _ in r.changed] == [".claude/workflow/profile.toml", "package.json", "README.md"]


def test_a_symlinked_file_is_refused_and_nothing_changes(copy):
    (copy / "package.json").rename(copy / "real-package.json")
    (copy / "package.json").symlink_to("real-package.json")
    before = _snapshot(copy)
    p = _run(copy)
    assert p.returncode == 1 and "package.json is a symbolic link" in p.stderr
    assert _snapshot(copy) == before and (copy / "package.json").is_symlink()


def test_accents_are_folded():
    assert adopt.dashed("Café Notes") == "cafe-notes"
    assert adopt.dashed("Ünïcödé") == "unicode"


@pytest.mark.parametrize("name, says", [("   ", "--name is empty"), ("a\tb", "no tabs or control characters")])
def test_blank_and_control_names_say_why(copy, name, says):
    p = _run(copy, name=name)
    assert p.returncode == 1 and says in p.stderr


@pytest.mark.parametrize("owner", ["-ada", "ada-", "a--b", "@@ada", "a" * 40])
def test_owners_github_refuses_are_refused(copy, owner):
    assert _run(copy, owner=owner).returncode == 1


def test_a_repo_name_over_100_characters_is_refused(copy):
    assert _run(copy, repo="ada/" + "n" * 101).returncode == 1
    assert _run(copy, repo="ada/" + "n" * 100).returncode == 0


def test_a_triple_quoted_name_is_refused_in_words(copy):
    (copy / "wrangler.toml").write_text('name = """old"""\n')
    p = _run(copy)
    assert p.returncode == 1 and "can't rewrite line by line" in p.stderr
