"""#117: every consumer reads the same preview, behind `[previews] on = true`.

The skills' and templates' wording is read as the kit-release tests read
skills (#39's seam 3); `merge-check` runs through the CLI with a preview file,
and the briefing is rendered in-process from a profile with previews on or off.
"""

import pytest
from conftest import KIT
import fake_gh
from test_merge_check import HEAD, EARLIER, check, inputs, note_ids, preview, project  # noqa: F401 (project is a fixture)
from test_merge_check_evidence import REPO, routes, run, with_report
from test_preview import bot, cf_run, row

from changelog_notes import since_0110
from workflow import charter, merge, render
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
    assert new["fix"] == "Ask Claude to find out why: \"When a build fails\" in the kit's `docs/previews.md` gives the fix for each message in the build's log."
    assert "When a build fails" in r["wording"]["developer"]["fix"]


def test_a_failed_previews_fix_names_the_vendored_page_in_a_project(project, capsys, monkeypatch):
    page = project / ".claude/workflow/docs/previews.md"
    page.parent.mkdir(parents=True)
    page.write_text("# Add try-it links to your pull requests\n")
    monkeypatch.setattr(merge, "PREVIEWS_DOC", page)
    data = inputs()
    data["preview"] = preview("failed")
    got, _ = check(project, capsys, data)
    [r] = got["reasons"]
    assert "\"When a build fails\" in `.claude/workflow/docs/previews.md`" in r["wording"]["new"]["fix"]


def test_a_building_preview_says_still_building_and_about_four_minutes(project, capsys):
    data = inputs()
    data["preview"] = preview("building")
    got, _ = check(project, capsys, data)
    [r] = got["reasons"]
    assert r["id"] == "preview_building"
    assert "still building" in r["wording"]["new"]["message"]
    assert "about four minutes" in r["wording"]["new"]["fix"]
    assert "about four minutes" in r["wording"]["developer"]["fix"]


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
    assert "previews are on" in msg.lower() and "can't say whether the link built" in msg
    assert "`workflow preview`" in msg and "`--preview`" in msg
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


def test_with_previews_on_and_no_report_from_cloudflare_the_note_says_so(project, capsys):
    # The reader's `none` with no commit: no bot comment and no check at all.
    _previews_on(project)
    data = inputs()
    data["preview"] = {"state": "none", "url": None, "commit": None}
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready"
    [n] = [n for n in got["notes"] if n["id"] == "no_previews"]
    assert "Cloudflare hasn't reported on this pull request" in n["message"]
    assert "isn't connected" in n["message"] and HEAD[:7] not in n["message"]


def test_with_previews_on_a_none_for_another_commit_is_still_building(project, capsys):
    # A stale answer (another pull request's, or an older head's) never reads as "no link".
    _previews_on(project)
    data = inputs()
    data["preview"] = {"state": "none", "url": None, "commit": EARLIER}
    got, _ = check(project, capsys, data)
    [r] = got["reasons"]
    assert r["id"] == "preview_building" and EARLIER[:7] in r["wording"]["developer"]["message"]


def test_a_preview_file_the_reader_left_empty_is_not_yet(project, capsys):
    # The consumers write `workflow preview`'s answer to a file and always pass
    # it: a reader that failed leaves it empty, and merge-check can't read it.
    _previews_on(project)
    d = project.parent / "in"
    d.mkdir(exist_ok=True)
    (d / "preview.json").write_text("")
    got, _ = check(project, capsys, inputs(), "--preview", str(d / "preview.json"))
    [r] = got["reasons"]
    assert r["id"] == "couldnt_read" and r["input"] == "preview" and "is empty" in r["message"]
    # The fix is the reader's, not GitHub's.
    assert "`workflow preview`" in r["wording"]["developer"]["fix"] and "GitHub" not in r["wording"]["developer"]["fix"]
    assert r["wording"]["new"]["message"] == "Not yet: couldn't read the try-it link."


def test_a_profile_that_cant_be_read_gets_no_pointer_to_add_try_it_links(project, capsys):
    # It may be refused over Access with previews on: the profile's own reason says what to fix.
    (project / ".claude/workflow/profile.toml").write_text("[project\n")
    got, _ = check(project, capsys, inputs())
    assert got["decision"] == "not_yet"
    [n] = [n for n in got["notes"] if n["id"] == "no_previews"]
    assert "previews.md" not in n["message"]


# ---------- merge-check --fetch reads the preview itself with previews on ----------


def _fetch_routes(comments, runs):
    data = with_report(inputs())
    r = routes(data)
    r[f"{REPO}/issues/12/comments"] = fake_gh.pages(data["comments"] + comments)
    r[f"{REPO}/commits/{HEAD}/check-runs"] = fake_gh.pages({"total_count": 1 + len(runs), "check_runs": data["checks"]["check_runs"] + runs})
    return r


def test_fetch_with_previews_on_reads_a_failed_preview_itself(project, capsys, tmp_path, monkeypatch):
    _previews_on(project)
    fake_gh.install(tmp_path, monkeypatch, _fetch_routes([bot(row("❌ Deployment failed", links=""))], [cf_run("failure")]))
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert got["decision"] == "not_yet"
    assert [r["id"] for r in got["reasons"]] == ["preview_failed"]


def test_fetch_with_previews_on_reads_a_built_preview_and_gives_its_link(project, capsys, tmp_path, monkeypatch):
    _previews_on(project)
    fake_gh.install(tmp_path, monkeypatch, _fetch_routes([bot(row())], [cf_run()]))
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert got["decision"] == "ready", got["reasons"]
    assert got["preview"]["state"] == "built" and got["preview"]["url"].startswith("https://")


def test_fetch_with_previews_on_and_an_unreadable_bot_comment_is_not_yet(project, capsys, tmp_path, monkeypatch):
    _previews_on(project)
    broken = bot(row())
    broken["body"] = "| Status | Name |\n| - | - |\n| ✅ | ? |\n"
    fake_gh.install(tmp_path, monkeypatch, _fetch_routes([broken], [cf_run()]))
    got, _ = run(project, capsys, {}, "--fetch", "12")
    [r] = got["reasons"]
    assert r["id"] == "couldnt_read" and r["input"] == "preview" and "try-it link couldn't be read" in r["message"]


def test_fetch_with_previews_off_reads_no_preview(project, capsys, tmp_path, monkeypatch):
    # Cloudflare's failed build is there, but with previews off nothing reads it.
    fake_gh.install(tmp_path, monkeypatch, _fetch_routes([bot(row("❌ Deployment failed", links=""))], [cf_run("failure")]))
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert got["decision"] == "ready" and "no_previews" in note_ids(got)


def test_fetch_keeps_a_preview_file_given(project, capsys, tmp_path, monkeypatch):
    _previews_on(project)
    fake_gh.install(tmp_path, monkeypatch, _fetch_routes([bot(row("❌ Deployment failed", links=""))], [cf_run("failure")]))
    got, _ = run(project, capsys, {"preview": preview("built")}, "--fetch", "12")
    assert got["decision"] == "ready", got["reasons"]


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
    # --fetch reads it itself with previews on, so the answer is the same either way.
    assert "`--fetch` reads the link itself" in gather
    not_yet = _section(_read(MERGE_CHECK), '## 3. "Not yet"', '## 4. "Ready"')
    failed = next(p for p in not_yet.split("\n\n") if p.startswith("**A try-it link that didn't build**"))
    assert "`preview_failed`" in failed and '**"Ask Claude to fix it"**' in failed and "When a build fails" in failed


# ---------- the conductor and build-ticket §6 ----------


def test_the_conductors_merge_row_reads_the_preview_before_merge_check():
    rows = _section(_read(CONDUCTOR), "**4. Each ticket in flight.**", "**Stopping a stuck session safely:**")
    row = next(ln for ln in rows.splitlines() if ln.startswith("| **PR open, not merged**"))
    assert ON in row
    read = "`WF preview --fetch <PR> --json > .workflow/run/preview-<PR>.json`"
    assert read in row and "`--preview .workflow/run/preview-<PR>.json`" in row
    assert "a file per pull request" in row
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
    ready = next(ln for ln in step3.splitlines() if ln.strip().startswith("- `ready`:"))
    assert "`preview.url`" in ready and '"How to try it"' in ready


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
    assert "until the pull request merges" in bullet  # CI can finish before the link is built
    # A fix no push makes (a Cloudflare setting) stops the ticket for the owner.
    assert "Cloudflare setting" in bullet and "`needs-human`" in bullet and "tracking issue" in bullet


# ---------- the briefing ----------


def _briefing(tmp_path):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname="d"\nrepo="a/d"\nowner="o"\n[ci]\nrequired_checks=["CI"]\n', encoding="utf-8"
    )
    c = charter.defaults([])
    c["merge"] = {"mode": "auto-merge", "waived_checks": []}
    slots = {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "none", "wake_trigger": "none"}
    vals = render.values(load(tmp_path), {"number": 7, "title": "Notes list"}, c, slots, 232, None)
    text = render.seal(render.render(_read(TEMPLATE), vals))
    assert render.sealed_intact(text)
    return _section(text, "### Merging", "### Rules")


def test_the_briefing_reads_the_preview_only_with_previews_on(tmp_path):
    # The profile is read each time, so a run that turns previews on mid-way is followed.
    merging = _briefing(tmp_path)
    line = next(ln for ln in merging.splitlines() if ln.startswith("- **The try-it link:**"))
    assert ON in line and "read it each time" in line
    assert "python3 .claude/workflow/bin/workflow.py preview --fetch <PR> --json > .workflow/preview.json" in line
    assert "--preview .workflow/preview.json" in line
    assert "without `gh`, give the reader files, as build-ticket §5 says" in line
    assert "With previews off, pass no `--preview`" in line
    assert merging.index("merge-check --fetch <PR>") < merging.index("- **The try-it link:**")


# ---------- docs and changelog ----------


def test_the_charter_doc_says_runs_pass_the_preview_when_previews_are_on():
    merging = _section(_read(CHARTER_DOC), "**Merges are decided by `workflow merge-check`,**", "**Kill switch.**")
    assert "`workflow preview --fetch <PR> --json`" in merging and "`--preview`" in merging and ON in merging


def test_the_previews_page_says_merge_check_waits_for_the_link():
    expect = _read(PREVIEWS_DOC).split("\n## What to expect\n", 1)[1].split("\n## ", 1)[0]
    line = next(ln for ln in expect.splitlines() if "never a required one" in ln)
    assert "`merge-check` says \"Not yet\"" in line and "still building" in line and "didn't build" in line


@pytest.mark.parametrize("word", ["#117", "workflow preview", "--preview"])
def test_the_changelog_notes_it_under_unreleased(word):
    assert word in since_0110().split("## 0.1.11", 1)[0]
