"""#83: the pull request template set-up installs, with "In plain words" at the
top, through `workflow pr-template` (#39's seam 2), and the skills' wording that
uses it, read as the kit-release tests read skills (#39's seam 3)."""

import re
import subprocess
import sys
from pathlib import Path

from conftest import KIT, git
from test_in_plain_words import HEADINGS, _template as _build_ticket_block
from test_vendor_evidence import kit, mattpocock, proj  # noqa: F401  (fixtures)

from workflow import pr_template, vendor
from workflow.guard import matches
from workflow.profile import DEFAULT_PROTECTED

CLI = KIT / "scripts/workflow.py"
TEMPLATE = KIT / "templates/github/pull_request_template.md"


def _run(*args, cli=CLI, cwd=None):
    return subprocess.run([sys.executable, "-B", str(cli), "pr-template", *args], capture_output=True, cwd=cwd)


def _out(p) -> str:
    return p.stdout.decode("utf-8")


def _headings(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines()]
    return [line for line in lines if line == "## In plain words" or re.fullmatch(r"\*\*[^*]+\*\*", line)]


def _section(path: Path, title: str, level: str = "##") -> str:
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"^{level} [^\n]*{re.escape(title)}[^\n]*\n(.*?)(?=^{level} |\Z)", text, re.M | re.S)
    assert m, f"no section {title!r} in {path.name}"
    return m.group(1)


# The template.


def test_the_templates_headings_are_build_tickets():
    # Read from both files, so the two can't drift.
    assert _headings(TEMPLATE.read_text(encoding="utf-8")) == HEADINGS
    assert _headings(_build_ticket_block()) == HEADINGS


def test_an_unedited_pr_shows_only_the_headings():
    text = TEMPLATE.read_text(encoding="utf-8")
    shown = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    assert [line for line in shown.splitlines() if line.strip()] == HEADINGS
    # Each bold heading has its one-line prompt right under it, in an HTML comment.
    lines = text.splitlines()
    for heading in HEADINGS[1:]:
        below = lines[lines.index(heading) + 1]
        assert below.startswith("<!-- ") and below.endswith(" -->"), heading


def test_the_template_uses_everyday_examples():
    low = TEMPLATE.read_text(encoding="utf-8").lower()
    assert "notes" in low
    assert "patient" not in low and "pair-drop" not in low


def test_the_template_is_not_a_protected_path():
    # The owner changes it freely: neither the defaults nor the profile template name it.
    assert matches(".github/pull_request_template.md", DEFAULT_PROTECTED) is None
    assert "pull_request_template" not in (KIT / "templates/profile.toml").read_text(encoding="utf-8")


# `workflow pr-template`.


def test_with_no_existing_template_it_prints_the_kits():
    p = _run()
    assert p.returncode == 0, p.stderr
    assert p.stdout == TEMPLATE.read_bytes()


def test_with_an_existing_template_the_headings_come_first_and_its_content_follows_whole(tmp_path):
    mine = "### Checklist\n\n- [ ] Tests added\n\n<!-- our own note -->\n"
    f = tmp_path / "pull_request_template.md"
    f.write_text(mine, encoding="utf-8")
    p = _run("--existing", str(f))
    assert p.returncode == 0, p.stderr
    out = _out(p)
    kit_part = TEMPLATE.read_text(encoding="utf-8")
    assert out.startswith(kit_part)
    assert out.endswith(mine)
    assert out == kit_part + "\n" + mine
    assert "above" in p.stderr.decode()


def test_an_existing_file_keeps_its_line_endings_and_bytes(tmp_path):
    mine = b"\xef\xbb\xbf## Summary\r\n\r\nWhat this does.\r\n"
    f = tmp_path / "PULL_REQUEST_TEMPLATE.md"
    f.write_bytes(mine)
    p = _run("--existing", str(f))
    assert p.returncode == 0, p.stderr
    # A byte order mark moves to the top; the rest is kept whole.
    assert p.stdout.startswith(b"\xef\xbb\xbf## In plain words\r\n")
    assert p.stdout.endswith(mine[3:])
    # The headings above it follow its line endings.
    head = p.stdout[3 : -len(mine[3:])]
    assert b"\r\n" in head and b"\n" not in head.replace(b"\r\n", b"")


def test_a_file_that_already_starts_with_the_headings_is_printed_unchanged(tmp_path):
    f = tmp_path / "pull_request_template.md"
    first = _run()
    f.write_bytes(first.stdout + b"\n### Our checklist\n")
    p = _run("--existing", str(f))
    assert p.returncode == 0, p.stderr
    assert p.stdout == f.read_bytes()
    assert "already starts with" in p.stderr.decode()


def test_running_it_twice_adds_nothing(tmp_path):
    f = tmp_path / "pull_request_template.md"
    f.write_text("## Summary\n", encoding="utf-8")
    once = _run("--existing", str(f))
    f.write_bytes(once.stdout)
    twice = _run("--existing", str(f))
    assert twice.returncode == 0
    assert twice.stdout == once.stdout
    assert _out(twice).count("## In plain words") == 1


def test_leading_blank_lines_still_count_as_starting_with_the_headings(tmp_path):
    f = tmp_path / "pull_request_template.md"
    f.write_bytes(b"\n\n" + TEMPLATE.read_bytes())
    p = _run("--existing", str(f))
    assert p.stdout == f.read_bytes()


def test_leading_html_comments_still_count_as_starting_with_the_headings(tmp_path):
    f = tmp_path / "pull_request_template.md"
    f.write_bytes(b"<!-- Thanks for\ncontributing -->\n\n" + TEMPLATE.read_bytes())
    p = _run("--existing", str(f))
    assert p.stdout == f.read_bytes()
    assert "already starts with" in p.stderr.decode()


def test_a_heading_further_down_isnt_the_top(tmp_path):
    f = tmp_path / "pull_request_template.md"
    f.write_text("## Summary\n\n## In plain words\n", encoding="utf-8")
    p = _run("--existing", str(f))
    assert _out(p).startswith("## In plain words\n") and _out(p).endswith("## Summary\n\n## In plain words\n")


def test_an_empty_file_gets_the_template(tmp_path):
    f = tmp_path / "pull_request_template.md"
    for empty in (b"", b"  \n\n", b"\xef\xbb\xbf\n"):
        f.write_bytes(empty)
        p = _run("--existing", str(f))
        assert p.returncode == 0
        assert p.stdout == TEMPLATE.read_bytes()
        assert "is empty" in p.stderr.decode()


def test_an_empty_existing_value_is_refused():
    for args in (("--existing", ""), ("--existing=",)):
        p = _run(*args)
        assert p.returncode == 1 and p.stdout == b""
        assert "--existing is empty" in p.stderr.decode()


def test_a_file_that_isnt_utf8_is_refused(tmp_path):
    f = tmp_path / "pull_request_template.md"
    f.write_bytes("## In plain words\n".encode("utf-16"))
    p = _run("--existing", str(f))
    assert p.returncode == 1 and p.stdout == b""
    err = p.stderr.decode()
    assert "isn't UTF-8" in err and "by hand" in err and "Traceback" not in err


def test_a_folder_of_templates_is_left_alone(tmp_path):
    d = tmp_path / ".github/PULL_REQUEST_TEMPLATE"
    d.mkdir(parents=True)
    (d / "feature.md").write_text("## Feature\n", encoding="utf-8")
    p = _run("--existing", str(d))
    assert p.returncode == 3
    assert p.stdout == b""
    err = p.stderr.decode()
    assert "by hand" in err and "query" in err and "is a folder" in err
    assert (d / "feature.md").read_text(encoding="utf-8") == "## Feature\n"


def test_a_missing_file_is_refused_in_words(tmp_path):
    p = _run("--existing", str(tmp_path / "nope.md"))
    assert p.returncode == 1
    assert p.stdout == b""
    assert "Traceback" not in p.stderr.decode() and "nope.md" in p.stderr.decode()


def test_the_kits_own_line_endings_dont_leak_into_the_output(tmp_path):
    # A clone that checked the kit out with CRLF still gives an LF project LF headings.
    k = tmp_path / "kit"
    (k / "templates/github").mkdir(parents=True)
    (k / "templates/github/pull_request_template.md").write_bytes(TEMPLATE.read_bytes().replace(b"\n", b"\r\n"))
    f = tmp_path / "mine.md"
    f.write_bytes(b"## Summary\n")
    assert b"\r" not in pr_template.build(k, f).text
    assert b"\r" not in pr_template.build(k).text


def test_a_missing_kit_template_names_the_kits_file(tmp_path):
    from workflow import cli

    k = tmp_path / "kit"
    k.mkdir()
    old = cli.KIT_ROOT
    cli.KIT_ROOT = k
    try:
        import contextlib
        import io

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            assert cli.main(["pr-template"]) == 1
    finally:
        cli.KIT_ROOT = old
    assert "pull_request_template.md" in err.getvalue() and "None" not in err.getvalue()


def test_it_changes_nothing_in_the_working_tree(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    gh = tmp_path / ".github"
    gh.mkdir()
    (gh / "pull_request_template.md").write_text("## Summary\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init")
    for args in ((), ("--existing", ".github/pull_request_template.md")):
        p = _run(*args, cwd=tmp_path)
        assert p.returncode == 0, p.stderr
        assert git(tmp_path, "status", "--porcelain", "--ignored") == ""
    assert (gh / "pull_request_template.md").read_text(encoding="utf-8") == "## Summary\n"


def test_the_cli_lists_the_command():
    doc = (KIT / "scripts/workflow/cli.py").read_text(encoding="utf-8").split('"""', 2)[1]
    assert "workflow pr-template [--existing FILE]" in doc
    assert "exits 3 for a folder of templates" in doc


# A vendored copy, as the vendor tests read what set-up installs.


def test_a_vendored_copy_carries_the_template_and_prints_it(mattpocock, kit, proj):  # noqa: F811
    vendor.install(kit, proj, mattpocock)
    copy = proj / ".claude/workflow/templates/github/pull_request_template.md"
    assert copy.read_bytes() == TEMPLATE.read_bytes()
    p = _run(cli=proj / ".claude/workflow/bin/workflow.py")
    assert p.returncode == 0, p.stderr
    assert p.stdout == TEMPLATE.read_bytes()


# The skills' wording.

SETUP = KIT / "skills/setup-workflow/SKILL.md"
UPDATE = KIT / "skills/update-workflow/SKILL.md"


def test_setup_writes_the_template_beside_the_issue_templates():
    write = _section(SETUP, "Write, on a branch")
    step = write.split("**11. The pull request template:**", 1)[1].split("\n\n", 1)[0]
    assert "`.github/pull_request_template.md`" in step
    assert "`WF pr-template`" in step
    assert "`WF pr-template --existing <file>`" in step
    assert "`.github/PULL_REQUEST_TEMPLATE/`" in step
    assert "exits 0" in step
    # Never redirected straight over the file it reads: that empties it first.
    assert "`.workflow/pr-template.md`" in step
    assert "never straight over the file it reads" in step
    # A single template beside a folder still gets the headings.
    assert "A single template beside the folder still gets the headings" in step
    # The issue templates' step comes just before it.
    assert write.index("**10. Issue templates:**") < write.index("**11. The pull request template:**")


def test_setup_says_so_in_its_pull_request():
    body = _section(SETUP, "The pull request")
    assert "pull request template" in body
    assert "what was added at the top of the existing one" in body


def test_setups_checklist_names_the_template():
    assert "issue templates, the pull request template" in _section(SETUP, "Checklist")


def test_update_adds_it_to_an_older_project_in_the_update_pr():
    once = UPDATE.read_text(encoding="utf-8").split("**The files set-up copied once,**", 1)[1].split("\n7. ", 1)[0]
    item = next(line for line in once.splitlines() if "pull_request_template.md" in line)
    assert "`WF pr-template`" in item
    assert "--existing" in item
    assert "shown in the PR body" in item
    assert "left as it is" in item
    # Only once: after that the file is the owner's, and later updates don't put the headings back.
    assert "only in the update that brings it in" in item
    assert "later updates leave it as it is, even when the owner has changed the headings" in item


def test_the_readme_lists_it_with_the_issue_templates():
    text = (KIT / "README.md").read_text(encoding="utf-8")
    assert "issue templates, the pull request template" in text
    assert "adds the pull request template once to a project set up before it" in text


def test_install_lists_it_among_what_setup_writes():
    text = (KIT / "docs/install.md").read_text(encoding="utf-8")
    step = next(line for line in text.splitlines() if line.startswith("1. Run the `setup-workflow` skill"))
    assert "the pull request template" in step


def test_the_changelog_notes_it_under_unreleased():
    text = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    unreleased = text.split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    entry = unreleased.split("(#83", 1)[1].split("\n\n**", 1)[0]
    assert "`workflow pr-template`" in entry
    assert "**For projects updating:**" in entry
