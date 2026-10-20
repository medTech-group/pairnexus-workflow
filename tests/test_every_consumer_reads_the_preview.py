"""#117: every consumer reads the same preview, behind `[previews] on = true`.

The skills' and templates' wording is read as the kit-release tests read
skills (#39's seam 3); `merge-check` runs through the CLI with a preview file,
and the briefing is rendered in-process from a profile with previews on or off.
"""

import pytest
from conftest import KIT
from test_merge_check import HEAD, EARLIER, check, inputs, note_ids, preview, project  # noqa: F401 (project is a fixture)

from changelog_notes import since_0110
from workflow import charter, render
from workflow.profile import load

MERGE_CHECK = KIT / "skills/merge-check/SKILL.md"
CONDUCTOR = KIT / "skills/conductor/SKILL.md"
BUILD_TICKET = KIT / "skills/build-ticket/SKILL.md"
TEMPLATE = KIT / "templates/ticket-session-prompt.md"
CHARTER_DOC = KIT / "docs/charter.md"
PREVIEWS_DOC = KIT / "docs/previews.md"

ON = "`[previews] on = true`"


def _read(p):
    return p.read_text(encoding="utf-8")


def _section(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i + len(start))]


def _previews_on(project):
    with (project / ".claude/workflow/profile.toml").open("a") as f:
        f.write("\n[previews]\non = true\naccess = true\n")


# ---------- merge-check through the CLI ----------


def test_a_failed_preview_says_the_link_didnt_build_with_the_page_as_its_fix(project, capsys):
    data = inputs()
    data["preview"] = preview("failed")
    got, _ = check(project, capsys, data)
    assert got["decision"] == "not_yet"
    [r] = got["reasons"]
    new = r["wording"]["new"]
    assert new["message"] == "Not yet: the try-it link didn't build."
    assert "When a build fails" in new["fix"] and "docs/previews.md" in new["fix"]
    assert "When a build fails" in r["wording"]["developer"]["fix"]


def test_a_building_preview_says_still_building_and_about_four_minutes(project, capsys):
    data = inputs()
    data["preview"] = preview("building")
    got, _ = check(project, capsys, data)
    [r] = got["reasons"]
    assert r["id"] == "preview_building"
    assert "still building" in r["wording"]["new"]["message"]
    assert "about four minutes" in r["wording"]["new"]["fix"]
    assert "about four minutes" in r["wording"]["developer"]["fix"]


def test_a_built_preview_gives_the_link(project, capsys):
    data = inputs()
    data["preview"] = preview("built")
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready"
    assert got["preview"]["url"] == "https://pr-12.demo.pages.dev"


def test_with_previews_off_none_never_blocks_and_names_the_page(project, capsys):
    got, _ = check(project, capsys, inputs())
    assert got["decision"] == "ready"
    [n] = [n for n in got["notes"] if n["id"] == "no_previews"]
    assert "no try-it link for this project" in n["message"]
    assert "docs/previews.md" in n["message"]


def test_with_previews_on_and_no_preview_given_the_note_says_none_was_read(project, capsys):
    _previews_on(project)
    got, _ = check(project, capsys, inputs())
    assert got["decision"] == "ready"
    [n] = [n for n in got["notes"] if n["id"] == "no_previews"]
    msg = n["message"]
    assert "no try-it link for this project" not in msg  # previews are on: there is one to read
    assert "previews are on" in msg.lower() and "`workflow preview`" in msg and "`--preview`" in msg
    assert "previews.md" not in msg


def test_with_previews_on_and_a_none_preview_the_note_says_cloudflare_built_nothing(project, capsys):
    _previews_on(project)
    data = inputs()
    data["preview"] = {"state": "none", "url": None, "commit": HEAD}
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready" and "no_previews" in note_ids(got)
    [n] = [n for n in got["notes"] if n["id"] == "no_previews"]
    assert "Cloudflare" in n["message"] and HEAD[:7] in n["message"]
    assert "previews.md" not in n["message"]


def test_a_preview_file_the_reader_left_empty_is_not_yet(project, capsys):
    # The consumers write `workflow preview`'s answer to a file and always pass
    # it: a reader that failed leaves it empty, and merge-check can't read it.
    _previews_on(project)
    data = inputs()
    data["preview"] = {}
    got, _ = check(project, capsys, data, raw={"preview": "\n"})
    assert got["decision"] == "not_yet"
    assert any("preview" in r["message"] for r in got["reasons"])


def test_a_preview_for_an_older_commit_is_still_building(project, capsys):
    data = inputs()
    data["preview"] = preview("built", EARLIER)
    got, _ = check(project, capsys, data)
    [r] = got["reasons"]
    assert r["id"] == "preview_building"


# ---------- the merge-check skill ----------


def test_the_merge_check_skill_reads_the_preview_only_with_previews_on():
    gather = _section(_read(MERGE_CHECK), "## 1. Gather the inputs", "## 2. Read the answer")
    assert ON in gather
    assert "WF preview --fetch 12 --json > <dir>/preview.json" in gather
    assert "--preview <dir>/preview.json" in gather
    # Without gh: the reader from files, the PR's issue comments and its head's check runs alone.
    assert "WF preview --comments F --checks F --sha <head> --json" in gather
    # Off: no reader and no --preview; `none`'s note never blocks and names the page.
    assert "pass no `--preview`" in gather
    assert "never blocks" in gather and "`docs/previews.md`" in gather
    # A reader that can't read leaves the file empty: merge-check says so, never "ready".
    assert "empty" in gather
    row = next(ln for ln in gather.splitlines() if ln.startswith("| `--preview`"))
    assert ON in row


# ---------- the conductor and build-ticket §6 ----------


def test_the_conductors_merge_row_reads_the_preview_before_merge_check():
    rows = _section(_read(CONDUCTOR), "**4. Each ticket in flight.**", "**Stopping a stuck session safely:**")
    row = next(ln for ln in rows.splitlines() if ln.startswith("| **PR open, not merged**"))
    assert ON in row
    read = "`WF preview --fetch <PR> --json > .workflow/run/preview.json`"
    assert read in row and "`--preview .workflow/run/preview.json`" in row
    assert row.index(read) < row.index("WF merge-check --fetch <PR> --json --charter")
    assert "pass no `--preview`" in row


def test_build_ticket_section_6_reads_the_preview_before_merge_check():
    six = _section(_read(BUILD_TICKET), "## 6. Post the evidence and merge", "## 7. End each turn")
    step3 = _section(six, "3. **Run `WF merge-check`.**", "4. **Merge** on `ready`.")
    assert ON in step3
    assert "`WF preview --fetch <PR> --json > .workflow/preview.json`" in step3
    assert "`--preview .workflow/preview.json`" in step3
    assert "pass no `--preview`" in step3
    # A failed preview is one to fix, a building one to wait for.
    assert "`preview_failed`" in step3 and "`preview_building`" in step3


# ---------- build-ticket's "How to try it" ----------


def test_the_pr_opens_saying_where_the_link_will_appear_with_previews_on():
    four = _section(_read(BUILD_TICKET), "## 4. Open the pull request", "## 5. Get it green")
    how = four.split("- `**How to try it**`:", 1)[1].split("\n- `**What could go wrong**`:", 1)[0]
    assert ON in how
    assert "where the link will appear" in how
    assert "The kit doesn't read preview links yet" not in how


def test_the_wait_for_ci_step_fills_in_the_link_once_built_and_says_a_failure_plainly():
    five = _section(_read(BUILD_TICKET), "## 5. Get it green", "## 6. Post the evidence and merge")
    bullet = next(p for p in five.split("\n- ") if p.startswith("**The try-it link"))
    assert ON in bullet
    assert "WF preview --fetch <PR> --json" in bullet
    assert "`built`" in bullet and "\"How to try it\"" in bullet and "two or three things to try" in bullet
    assert "`failed`" in bullet and "didn't build" in bullet
    assert "When a build fails" in bullet  # the fix, from the page's table


# ---------- the briefing ----------


def _briefing(tmp_path, previews):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    extra = "[previews]\non = true\n" if previews else ""
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname="d"\nrepo="a/d"\nowner="o"\n[ci]\nrequired_checks=["CI"]\n' + extra, encoding="utf-8"
    )
    c = charter.defaults([])
    c["merge"] = {"mode": "auto-merge", "waived_checks": []}
    slots = {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "none", "wake_trigger": "none"}
    vals = render.values(load(tmp_path), {"number": 7, "title": "Notes list"}, c, slots, 232, None)
    text = render.seal(render.render(_read(TEMPLATE), vals))
    assert render.sealed_intact(text)
    return _section(text, "### Merging", "### Rules")


def test_the_briefing_reads_the_preview_with_previews_on(tmp_path):
    merging = _briefing(tmp_path, True)
    assert "python3 .claude/workflow/bin/workflow.py preview --fetch <PR> --json > .workflow/preview.json" in merging
    assert "--preview .workflow/preview.json" in merging


def test_the_briefing_passes_no_preview_with_previews_off(tmp_path):
    merging = _briefing(tmp_path, False)
    assert "preview --fetch" not in merging
    assert "pass no `--preview`" in merging


# ---------- docs and changelog ----------


def test_the_charter_doc_says_runs_pass_the_preview_when_previews_are_on():
    merging = _section(_read(CHARTER_DOC), "**Merges are decided by `workflow merge-check`,**", "**Kill switch.**")
    assert "`workflow preview --fetch <PR> --json`" in merging and "`--preview`" in merging and ON in merging


def test_the_previews_page_says_the_merge_helper_waits_for_the_link():
    expect = _read(PREVIEWS_DOC).split("\n## What to expect\n", 1)[1].split("\n## ", 1)[0]
    line = next(ln for ln in expect.splitlines() if "never a required one" in ln)
    assert "Not yet" in line and "still building" in line and "didn't build" in line


@pytest.mark.parametrize("word", ["#117", "workflow preview", "--preview"])
def test_the_changelog_notes_it_under_unreleased(word):
    assert word in since_0110().split("## 0.1.11", 1)[0]
