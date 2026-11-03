"""#428 (spec #412, "The bar"): `run.bar_areas` names the areas whose tickets
need a `## Bar`; `profile check` refuses a name that isn't an area and shows
the setting, and `workflow ready` notes a ready ticket in such an area whose
body has no `## Bar` heading, leaving it ready."""

import json
import tomllib
from pathlib import Path

import pytest

from workflow import cli
from workflow.issues import BAR_NOTE, has_bar, readiness
from workflow.profile import ProfileError, check, parse

KIT = Path(__file__).resolve().parents[1]

AREAS = '[areas]\nguard = ["scripts/workflow/guard.py"]\nconductor = ["skills/conductor/**"]\nprofile = ["scripts/workflow/profile.py"]\n'
BAR = "## Bar\n\n- Must handle: x.\n- Fail closed: y.\n- Accepted limits: none.\n"


def issue(n, body="", labels=("ready-for-agent",)):
    return {"number": n, "state": "open", "labels": [{"name": l} for l in labels], "body": body, "title": f"t{n}"}


def _toml(run=""):
    return f'[project]\nname = "demo"\nrepo = "acme/demo"\n{AREAS}[run]\n{run}\n'


def _write(root, run=""):
    (root / ".claude/workflow").mkdir(parents=True, exist_ok=True)
    (root / ".claude/workflow/profile.toml").write_text(_toml(run))


def _parse(run=""):
    return parse(tomllib.loads(_toml(run)), Path("."))


# ---------- the profile ----------


@pytest.mark.parametrize("run", ["", "bar_areas = []"])
def test_absent_or_empty_means_none(run):
    assert _parse(run).bar_areas == []


def test_reads_the_listed_areas():
    assert _parse('bar_areas = ["guard", "conductor"]').bar_areas == ["guard", "conductor"]


def test_a_name_differing_only_in_case_is_the_area():
    assert _parse('bar_areas = ["Guard"]').bar_areas == ["Guard"]


@pytest.mark.parametrize(
    "run, said",
    [
        ('bar_areas = ["guard", "gaurd"]', "gaurd"),
        ('bar_areas = ["billing"]', "billing"),
        ('bar_areas = [""]', "''"),
    ],
)
def test_refuses_a_name_that_isnt_an_area(run, said):
    with pytest.raises(ProfileError) as e:
        _parse(run)
    msg = str(e.value)
    assert "run.bar_areas" in msg and said in msg and "isn't one of the profile's areas" in msg
    assert "(conductor, guard, profile)" in msg  # names the areas there are


def test_a_long_name_is_cut_short_in_the_message():
    with pytest.raises(ProfileError) as e:
        _parse(f'bar_areas = ["{"x" * 3000}"]')
    assert len(str(e.value)) < 300


def test_refuses_any_name_when_there_are_no_areas():
    with pytest.raises(ProfileError) as e:
        parse(tomllib.loads('[project]\nname = "d"\nrepo = "a/d"\n[run]\nbar_areas = ["guard"]\n'), Path("."))
    assert "run.bar_areas" in str(e.value) and "isn't one of the profile's areas (it has none)" in str(e.value)


@pytest.mark.parametrize("name", ["web app", "ui/ux", "-lead", "trail.", "_drafts", "a+b"])
def test_warns_of_a_name_no_ticket_could_give(tmp_path, name):
    data = tomllib.loads(_toml(f"bar_areas = [{json.dumps(name)}, \"guard\"]"))
    data["areas"][name] = []  # an area by that name exists: the setting stands
    prof = parse(data, tmp_path)
    assert prof.bar_areas == [name, "guard"]
    (w,) = [x for x in check(prof) if x.startswith("run.bar_areas")]
    assert "no ticket's Area: line can give" in w and "never noted" in w


def test_no_warning_for_names_a_ticket_can_give(tmp_path):
    data = tomllib.loads(_toml('bar_areas = ["guard", "merge-check", "v2.0"]'))
    data["areas"]["merge-check"] = data["areas"]["v2.0"] = []
    assert not [x for x in check(parse(data, tmp_path)) if x.startswith("run.bar_areas")]


@pytest.mark.parametrize("run", ['bar_areas = "guard"', "bar_areas = [1]", "bar_areas = true"])
def test_refuses_anything_but_a_list_of_names(run):
    with pytest.raises(ProfileError) as e:
        _parse(run)
    assert "run.bar_areas" in str(e.value) and "a list of area names" in str(e.value)


def test_profile_check_shows_the_setting(tmp_path, monkeypatch, capsys):
    _write(tmp_path, 'bar_areas = ["guard", "conductor"]')
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert cli.main(["profile", "check"]) == 0
    assert json.loads(capsys.readouterr().out)["bar_areas"] == ["guard", "conductor"]


def test_profile_check_shows_none_as_an_empty_list(tmp_path, monkeypatch, capsys):
    _write(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert cli.main(["profile", "check"]) == 0
    assert json.loads(capsys.readouterr().out)["bar_areas"] == []


def test_profile_check_refuses_a_name_that_isnt_an_area(tmp_path, monkeypatch, capsys):
    _write(tmp_path, 'bar_areas = ["gaurd"]')
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert cli.main(["profile", "check"]) == 1
    assert "run.bar_areas" in capsys.readouterr().err


# ---------- the heading ----------


@pytest.mark.parametrize(
    "body",
    [
        BAR,
        "## What to build\n\nx\n\n## Bar\n\n- y\n",
        "### Bar\n- y\n",
        "## bar:\n- y\n",
        "  ## Bar  \n- y\n",
        "## Bar ##\n- y\n",
        "## **Bar**\n- y\n",
        "## _Bar:_\n- y\n",
        "Bar\n---\n- y\n",  # underlined, as GitHub shows a heading
        "x\n\nBar\n===\n- y\n",
        "## Bar\r\n- y\r\n",
        "<!-- guidance -->\n## Bar\n- y\n",  # a comment before it, closed
        "```x`y\n## Bar\n",  # a backtick in a backtick fence's info string: not a fence
        "<details>\n\n## Bar\n\n</details>\n",  # an HTML block ends at a blank line
        "<!-- a\nb -->\n## Bar\n",  # a comment ends at its line with -->
        "x\n\n```\na\n```\n\n## Bar\n",
        "- x\n  ## Bar\n",  # a heading in a list item
        "```\nx\n``` \t\n## Bar\n",  # a closer may have spaces and tabs after it
        "x\n \t\nBar\n---\n",
    ],
)
def test_has_bar(body):
    assert has_bar(body)


@pytest.mark.parametrize(
    "body",
    [
        None,
        "",
        "Area: guard\n\nNo bar here.\n",
        "The bar is high.\n",
        "## Barriers\n- y\n",
        "## Bar codes\n- y\n",
        "**Bar**\n- y\n",
        "```markdown\n## Bar\n- y\n```\n",  # an example in fenced code isn't the ticket's bar
        "~~~\n## Bar\n~~~\n",
        "> ## Bar\n> - y\n",  # quoted from elsewhere
        "    ## Bar\n",  # indented code
        "#Bar\n",  # not a heading in GitHub's Markdown
        "\t## Bar\n",  # tab-indented: code
        "<!--\n## Bar\n- Must handle: TODO\n-->\n",  # hidden by GitHub
        "<!-- a placeholder\n## Bar\n",  # an unclosed comment hides the rest
        "- ```md\n  ## Bar\n  ```\n",  # fenced code in a list item
        "```\n~~~\n## Bar\n```\n",  # a fence closes only with its own character
        "````\n```\n## Bar\n````\n",  # and at least as long
        "```\n```js\n## Bar\n```\n",  # and with nothing after it
        "x\nBar\n---\n",  # a paragraph's last line underlined: the heading is "x Bar"
        "Bar\n- y\n",
        "## Bar (must handle, fail closed, accepted limits)\n",
        # Round 2: a `<!--` in code can't hide a fence's opener.
        "The marker opens with `<!--`.\n\n```md\n<!-- workflow:agent -->\n## Bar\n- x\n```\n",
        "<!-- workflow:agent -->## Bar\n",  # text after a comment, on its line, is HTML
        "<!-- c --> ## Bar\n",
        "<!-- a\nb\n--> ## Bar\n",
        "<details>\n<summary>Bar</summary>\n## Bar\n</details>\n",  # an HTML block runs to a blank line
        "<div>\n## Bar\n</div>\n",
        "<pre>\n\n## Bar\n</pre>\n",  # and <pre> to its closing tag
        "<!-- never closed\n\n## Bar\n",
        # Fences GitHub may pair differently stop the reading.
        "    ```\nx\n```\n## Bar\n",
        "- ```\n  run x\n- next\n```\n## Bar\n```\n",
        "1. ```\n   ## Bar\n   ```\n",
        "   ```\n## Bar\n```\n",
        "1. x\n\n   ```\n   a\n  ```\n## Bar\n```\n",
        "> ```\n## Bar\n",
        # Lines inside a fence that don't close it.
        "```md\n- ```\n## Bar\n```\n",
        "```\n    ```\n## Bar\n```\n",
        "```\n\t```\n## Bar\n```\n",
        # An underline at column 0 can't underline a list item's paragraph.
        "- Must handle: x\n\n  Bar\n---\n",
        "x\n\nBar",  # the last line: no underline, no error
        # Only \n, \r and \r\n end a line in Markdown.
        "x\x0b## Bar\n",
        "x\u2028## Bar\n",
        "x\x85## Bar\n",
        # Round 3: HTML in a list item or a quote stops the reading.
        "- <!--\n  ## Bar\n  -->\n",
        "- <details><summary>Notes</summary>\n  ## Bar\n  </details>\n",
        "* <pre>\n\n  ## Bar\n  </pre>\n",
        "1) <!--\n   ## Bar\n   -->\n",
        "> <div>\n## Bar\n",
        # Only spaces and tabs are blank or trailing in Markdown, not U+00A0.
        "```\nx\n```\u00a0\n## Bar\n```\n",
        "<div>\n\u00a0\n## Bar\n</div>\n",
        "x\n\u00a0\nBar\n---\n",
        "Bar\n---\u00a0\n",
        "x\n\u3000\nBar\n---\n",
    ],
)
def test_has_no_bar(body):
    assert not has_bar(body)


@pytest.mark.parametrize("body", ["## Bar" + " " * 65000 + "x", "\n\nBar" + " \t" * 32000 + "x", "**Bar**" + " " * 65000])
def test_a_long_line_is_quick(body):
    import time

    t = time.monotonic()
    has_bar(body)
    assert time.monotonic() - t < 1


def test_a_heading_after_a_closed_fence_counts():
    assert has_bar("```\nexample\n```\n\n## Bar\n- y\n")


def test_an_unclosed_fence_hides_what_follows():
    assert not has_bar("```\nexample\n\n## Bar\n- y\n")


# ---------- workflow ready ----------


def _notes(issues, bar_areas, areas=("guard", "conductor", "profile")):
    return {v.number: v for v in readiness(issues, [], areas=list(areas), bar_areas=bar_areas)}


def test_notes_a_ticket_in_a_bar_area_with_no_bar_and_leaves_it_ready():
    v = _notes([issue(1, "Area: guard\n"), issue(2, "Area: guard\n\n" + BAR)], ["guard"])
    assert v[1].ready and v[1].reasons == []
    assert v[1].notes == [BAR_NOTE.format(area="guard")]
    assert v[2].ready and v[2].notes == []


def test_the_note_says_what_is_missing():
    (note,) = _notes([issue(1, "Area: guard\n")], ["guard"])[1].notes
    assert "## Bar" in note and "guard" in note and "run.bar_areas" in note
    assert "(must handle" not in note  # nothing a writer might copy into the heading


def test_only_the_listed_areas():
    v = _notes([issue(1, "Area: profile\n"), issue(2, "Area: conductor\n"), issue(3)], ["guard", "conductor"])
    assert v[1].notes == [] and v[3].notes == []
    assert v[2].notes == [BAR_NOTE.format(area="conductor")]


@pytest.mark.parametrize("bar_areas", [None, []])
def test_no_bar_areas_no_note(bar_areas):
    assert _notes([issue(1, "Area: guard\n")], bar_areas)[1].notes == []


def test_areas_compare_without_case():
    v = _notes([issue(1, "Area: Guard\n"), issue(2, "Area: guard\n")], ["GUARD"])
    assert v[1].notes == [BAR_NOTE.format(area="guard")] and v[2].notes == [BAR_NOTE.format(area="guard")]


def test_a_fenced_example_bar_is_still_noted():
    v = _notes([issue(1, "Area: guard\n\n```\n## Bar\n```\n")], ["guard"])
    assert v[1].notes == [BAR_NOTE.format(area="guard")]


def test_a_ticket_not_ready_is_noted_too():
    # As the protected-path note: the note is about the ticket, whatever else holds it.
    v = _notes([issue(1, "Area: guard\n\n## Blocked by\n\n#9\n"), issue(9, labels=())], ["guard"])
    assert not v[1].ready and v[1].notes == [BAR_NOTE.format(area="guard")]


def test_beside_the_other_notes():
    body = "Area: guard\n\nChange `.github/workflows/ci.yml` to add a job.\n"
    v = {x.number: x for x in readiness([issue(1, body)], [], areas=["guard"], protected=[".github/workflows/**"], bar_areas=["guard"])}
    assert v[1].ready
    assert any(n.startswith("names protected path") for n in v[1].notes)
    assert BAR_NOTE.format(area="guard") in v[1].notes


# ---------- the CLI ----------


@pytest.fixture
def ready_files(tmp_path, monkeypatch):
    _write(tmp_path, 'bar_areas = ["guard"]')
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    issues = [issue(1, "Area: guard\n"), issue(2, "Area: guard\n\n" + BAR), issue(3, "Area: profile\n")]
    (tmp_path / "issues.json").write_text(json.dumps(issues))
    (tmp_path / "prs.json").write_text("[]")
    return ["ready", "--issues", str(tmp_path / "issues.json"), "--prs", str(tmp_path / "prs.json")]


def test_ready_cli_json(ready_files, capsys):
    assert cli.main([*ready_files, "--json", "--slots", "5"]) == 0
    out = json.loads(capsys.readouterr().out)
    notes = {v["number"]: v["notes"] for v in out["ready"]}
    assert notes == {1: [BAR_NOTE.format(area="guard")], 2: [], 3: []}
    assert out["not_ready"] == []


def test_ready_cli_text(ready_files, capsys):
    assert cli.main([*ready_files, "--only", "1"]) == 0
    out = capsys.readouterr().out
    assert "READY #1 [guard]" in out and f"note: {BAR_NOTE.format(area='guard')}" in out


# ---------- the template and the docs ----------


def test_template_names_the_setting_and_still_parses():
    text = (KIT / "templates/profile.toml").read_text(encoding="utf-8")
    assert "bar_areas" in text
    run = text[text.index("\n[run]") :]
    assert "bar_areas" in run.split("\n[", 2)[1]  # under [run]
    assert parse(tomllib.loads(text), Path(".")).bar_areas == []


def test_template_example_is_one_of_its_areas():
    text = (KIT / "templates/profile.toml").read_text(encoding="utf-8")
    example = text.split("bar_areas = []", 1)[1].split("e.g. ", 1)[1].split("\n", 1)[0]
    areas = text.split("\n[areas]", 1)[1].split("\n[", 1)[0]
    for name in json.loads(example):
        assert f"# {name} = [" in areas


def test_docs_name_the_setting():
    text = (KIT / "docs/profile.md").read_text(encoding="utf-8")
    run = text[text.index("## `[run]`") :]
    row = next(l for l in run.splitlines() if l.startswith("| `bar_areas`"))
    assert "## Bar" in row and "workflow ready" in row and "[areas]" in row


def test_next_lists_the_note():
    text = (KIT / "skills/next/SKILL.md").read_text(encoding="utf-8")
    notes = text.split("A READY ticket may carry notes", 1)[1].split("\n\n", 1)[0]
    shown = BAR_NOTE.format(area="<area>").split(":", 1)[0]
    assert f'"{shown}: …"' in notes and "run.bar_areas" in notes
    line = next(l for l in notes.splitlines() if shown in l)
    assert "before building" not in line  # a note never changes whether a ticket is ready
