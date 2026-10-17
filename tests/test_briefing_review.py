"""The ticket session's briefing takes its review rounds and UI explorer from
the approved charter (#120), rendered through the CLI as
`tests/test_charter_state_render.py` renders it (#42's seam 2)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from workflow import charter

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"
TEMPLATE = KIT / "templates/ticket-session-prompt.md"
SLOTS = {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "none", "wake_trigger": "trig_01abc"}


def _project(tmp_path, explorer="browser", rounds=4):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        f'[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "owner-login"\n\n'
        f'[run]\nreview_rounds = {rounds}\n\n[ui]\nexplorer = "{explorer}"\n'
    )
    (tmp_path / "ticket.json").write_text(json.dumps({"number": 7, "title": "Readings tab"}))
    (tmp_path / "slots.json").write_text(json.dumps(SLOTS))


def _cli(tmp_path, *args):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, cwd=tmp_path, env=env)


def _brief(tmp_path, c):
    (tmp_path / "charter.json").write_text(json.dumps(c))
    p = _cli(
        tmp_path, "render", "--template", str(TEMPLATE), "--ticket", "ticket.json", "--charter", "charter.json",
        "--slots", "slots.json", "--tracking", "11", "--out", "briefing.md",
    )
    assert p.returncode == 0, p.stderr
    v = _cli(tmp_path, "briefing", "verify", "--file", "briefing.md")
    assert v.returncode == 0 and v.stdout.endswith(" intact\n"), v.stdout
    return (tmp_path / "briefing.md").read_text()


def _charter(**review):
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    c["approved"] = {"by": "owner", "at": "2026-10-12T11:55:00Z", "source": "chat"}
    if review:
        c["review"] = review
    return c


def _review_line(text):
    return next(l for l in text.splitlines() if l.startswith("- **Review:**"))


def test_rounds_and_explorer_come_from_the_charter(tmp_path):
    _project(tmp_path)
    line = _review_line(_brief(tmp_path, _charter(rounds=2, explorer=True)))
    assert "at most 2." in line and "UI explorer: browser" in line


def test_explorer_off_briefs_none(tmp_path):
    _project(tmp_path)
    line = _review_line(_brief(tmp_path, _charter(rounds=5, explorer=False)))
    assert "at most 5." in line and "UI explorer: none" in line and "browser" not in line


def test_older_charter_takes_the_profiles(tmp_path):
    _project(tmp_path)
    c = _charter()
    del c["preset"], c["review"]
    line = _review_line(_brief(tmp_path, c))
    assert "at most 4." in line and "UI explorer: browser" in line


def test_older_charter_without_a_profile_explorer(tmp_path):
    _project(tmp_path, explorer="none", rounds=3)
    c = _charter()
    del c["preset"], c["review"]
    line = _review_line(_brief(tmp_path, c))
    assert "at most 3." in line and "UI explorer: none" in line


def test_preset_without_review_takes_the_presets(tmp_path):
    _project(tmp_path, rounds=2)
    c = _charter()
    c["preset"] = "thorough"
    del c["review"]
    line = _review_line(_brief(tmp_path, c))
    assert "at most 3." in line and "UI explorer: browser" in line


@pytest.mark.parametrize("with_review", [True, False])
def test_light_charter_briefs_one_round(tmp_path, with_review):
    """#121's skills key on "when the briefing's review rounds are 1"."""
    _project(tmp_path)
    c = _charter(rounds=1, explorer=False)
    c["preset"] = "light"
    if not with_review:
        del c["review"]
    line = _review_line(_brief(tmp_path, c))
    assert "at most 1 (the light review)." in line and "UI explorer: none" in line


def test_light_review_runs_no_explorer_even_when_the_charter_says_so(tmp_path):
    """The light review runs no explorer (`review-panel` §6), so one round briefs `none`."""
    _project(tmp_path)
    line = _review_line(_brief(tmp_path, _charter(rounds=1, explorer=True)))
    assert "at most 1 (the light review)." in line and "UI explorer: none" in line


def test_explorer_on_without_a_profile_explorer_briefs_none(tmp_path):
    _project(tmp_path, explorer="none")
    line = _review_line(_brief(tmp_path, _charter(rounds=2, explorer=True)))
    assert "at most 2." in line and "UI explorer: none" in line


def test_the_skills_take_the_briefings_rounds_and_explorer():
    """A ticket session follows these: they must not send it back to the profile."""
    for path in ("skills/review-panel/SKILL.md", "skills/build-ticket/SKILL.md", "docs/flow.md"):
        text = (KIT / path).read_text()
        assert "at most the briefing's review rounds in a ticket session, else the profile's `run.review_rounds`" in text, path
        assert "at most the profile's `run.review_rounds`" not in text, path
    assert "the briefing's UI explorer in a ticket session, else the profile's `ui.explorer`" in (KIT / "skills/review-panel/SKILL.md").read_text()


def test_the_one_page_says_one_round_runs_no_explorer(tmp_path):
    """What the owner approves is what the sessions do: the page and the briefing agree."""
    _project(tmp_path)
    c = _charter(rounds=1, explorer=True)
    (tmp_path / "charter.json").write_text(json.dumps(c))
    p = _cli(tmp_path, "charter", "markdown", "charter.json")
    assert p.returncode == 0, p.stderr
    assert "up to 1 round per ticket; no UI explorer (one round is the light review)." in p.stdout
    c = _charter(rounds=2, explorer=True)
    (tmp_path / "charter.json").write_text(json.dumps(c))
    assert "up to 2 rounds per ticket; UI explorer on." in _cli(tmp_path, "charter", "markdown", "charter.json").stdout


def test_normal_with_one_profile_round_offers_no_explorer(profile):
    from workflow import presets

    profile.review_rounds, profile.explorer = 1, "cli"
    assert presets.words("normal", profile).endswith("up to 1 review round; no UI explorer (one round is the light review)")
    assert presets.words("thorough", profile).endswith("UI explorer on")


def test_changelog_notes_120_without_bumping_version():
    text = (KIT / "CHANGELOG.md").read_text()
    unreleased = text.split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    assert "(#120," in unreleased
    released = text.split("\n## ")[2].split()[0].lstrip("v")
    assert (KIT / "VERSION").read_text().strip() == released
    assert "presets.review_of" in (KIT / "docs/charter.md").read_text().split("## 4.", 1)[1].split("\n## ", 1)[0]


def test_the_one_page_never_offers_an_explorer_the_project_lacks(tmp_path):
    _project(tmp_path, explorer="none")
    (tmp_path / "charter.json").write_text(json.dumps(_charter(rounds=2, explorer=True)))
    p = _cli(tmp_path, "charter", "markdown", "charter.json")
    assert "up to 2 rounds per ticket; no UI explorer (the project has none)." in p.stdout
