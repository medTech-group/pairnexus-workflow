"""#49: experience in the guided start (`start`) and in kit updates
(`update-workflow`), part of solo mode (#32). Seam 4: the skills' wording, read
from their files as the kit-release tests do; seam 2: `workflow status` for the
file the guided start's answer lands in."""

import json
import re

from conftest import KIT
from test_solo_mode_profile import _cli
from workflow import context, vendor
from workflow.profile import EXPERIENCE_FILE

START = KIT / "skills/start/SKILL.md"
UPDATE = KIT / "skills/update-workflow/SKILL.md"
SETUP = KIT / "skills/setup-workflow/SKILL.md"


def _text(path):
    return path.read_text(encoding="utf-8")


def _section(path, title, level="##"):
    """The text of the `<level> ...` section whose heading contains `title`, up
    to the next heading of that level or higher."""
    m = re.search(rf"^{level} [^\n]*{re.escape(title)}[^\n]*\n(.*?)(?=^#{{1,{len(level)}}} |\Z)", _text(path), re.M | re.S)
    assert m, f"no section {title!r} in {path.name}"
    return m.group(1)


def _level_section():
    return _section(START, "how much they know")


# The guided start's first question


def test_the_level_question_comes_before_what_are_we_working_on():
    text = _text(START)
    at = text.index("## Before anything: how much they know")
    # Before the first message is read, so before any menu or "What are we working on?".
    assert at < text.index("## 0. Read the first message")
    assert at < text.index('**Then ask: "What are we working on?"**')


def test_the_level_question_is_asked_only_when_the_experience_is_unknown():
    level = _level_section()
    assert "`WF status --json`" in level
    assert '`experience.source` is `"unknown"`' in level
    # One tap, the two levels, as the profile names them.
    assert "*New to building*" in level and "*Developer*" in level
    assert "`AskUserQuestion`" in level
    # It is the very first question: nothing else is asked or done before it.
    assert "the very first question of the session" in level


def test_skipping_the_level_question_counts_as_new():
    level = _level_section()
    assert "**Skipping counts as new.**" in level
    assert "record `new`" in level


def test_a_local_answer_is_written_to_the_file_status_reads():
    level = _level_section()
    assert f"`{EXPERIENCE_FILE.as_posix()}`" in level
    assert "one line, `new` or `developer`" in level
    # Never committed.
    assert "Never stage or commit it" in level


def test_a_cloud_answer_says_once_how_to_keep_it():
    level = _level_section()
    assert "`CLAUDE_CODE_REMOTE` is `true`" in level
    assert "for this session" in level
    assert "**Say once**" in level
    assert "add `WORKFLOW_EXPERIENCE=<level>` to this cloud environment's variables" in level


def test_explain_less_and_explain_more_change_the_level_the_same_way():
    level = _level_section()
    assert '"Explain less"' in level and '"explain more"' in level
    assert '"explain less" to `developer`' in level and '"explain more" to `new`' in level
    assert "recorded the same way" in level
    # An environment value wins over the file: the session keeps the new level,
    # and the person learns how to change it for good.
    assert '`experience.source` is `"environment"`' in level


def test_the_guided_start_tells_claude_when_it_records_a_new_level_section():
    # #35's glossary explanations stop or start again on this line.
    level = _level_section()
    assert "**Tell yourself the new level**" in level
    assert "From now on: <level>" in level
    assert "stop explaining" in level and "glossary" in level


def test_ticket_and_conductor_sessions_are_never_asked():
    level = _level_section()
    assert "**Never in a ticket or conductor session**" in level
    assert "`WORKFLOW_ROLE` set, or a branch named like the profile's `run.ticket_branch`" in level
    assert "they never ask, whatever status says" in level


def test_the_level_question_is_left_to_set_up_when_the_kit_is_not_set_up():
    # Set-up asks the same question: never twice in one session.
    level = _level_section()
    assert "**Nor when the kit isn't set up here**" in level and "`set_up` is false" in level


def test_the_level_is_written_only_where_it_stays_out_of_the_repository():
    level = _level_section()
    assert "`git check-ignore -q .workflow/experience` must succeed" in level
    assert "nothing that isn't a plain file may sit at that path" in level
    assert "don't write it: keep the level in this conversation" in level


def test_explain_less_and_more_bring_the_skill_whenever_they_are_said():
    head = _text(START).split("---", 2)[1]
    assert '"explain less" or "explain more"' in head


def test_the_first_message_nudge_asks_the_level_first():
    assert "no experience level, ask it as the skill says" in context.START
    nudge = context.START.split("ask it as the skill says")[0]
    assert "one clear thing" not in nudge


def test_the_look_around_has_the_solo_mode_line():
    look = _section(START, "1. Look around")
    assert "`Solo mode: yes`" in look
    assert "one of those lines" in look
    # What it means for the person, and the way out.
    assert "nothing on GitHub protects `<base branch>` yet" in look
    assert "Name the profile's base branch" in look
    # It explains; it never nags with the offer at every start (#32, story 26).
    assert "Don't offer \"Protect `main`\" here" in look


def test_the_level_changes_wording_and_never_what_github_reads():
    rules = _section(START, "Rules")
    assert "same for every level" in rules
    assert "plain summary first" in rules
    assert "never what the kit allows" in rules


# The file the answer lands in (seam 2)


def _status(root):
    p = _cli(root, "status", "--json")
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)["experience"]


def test_the_file_start_names_is_the_one_status_reads(tmp_path):
    named = re.findall(r"`(?:git check-ignore -q )?(\.workflow/[\w.-]+)`", _level_section())
    assert named and set(named) == {EXPERIENCE_FILE.as_posix()}
    assert _status(tmp_path)["source"] == "unknown"
    for answer in ("new", "developer"):
        path = tmp_path / named[0]
        path.parent.mkdir(exist_ok=True)
        path.write_text(answer + "\n")
        exp = _status(tmp_path)
        assert (exp["level"], exp["source"]) == (answer, "local file")


def test_the_workflow_directory_stays_untracked():
    assert ".workflow/" in (KIT / ".gitignore").read_text(encoding="utf-8").split()
    # A vendored project gets the same line from `vendor install`.
    assert vendor.IGNORE_LINE == ".workflow/"


# Kit updates


def _update_step(title):
    """Step `title` of update-workflow's numbered list, up to the next step."""
    m = re.search(rf"^\d+\. \*\*{re.escape(title)}[^\n]*\n?(.*?)(?=^\d+\. \*\*|\Z)", _text(UPDATE), re.M | re.S)
    assert m, f"no step {title!r}"
    return m.group(0)


def _update_default():
    return _update_step("The project's experience default")


def test_update_asks_the_project_default_once_when_the_profile_has_none():
    step = _update_default()
    assert "`WF profile check`" in step and '`"experience": null`' in step
    assert "ask once" in step
    assert "*new to building*" in step and "*developer*" in step
    assert "*Leave it unset*" in step
    # Unset, each later update asks once again: said plainly.
    assert "each later update asks once while the profile has no `experience`" in step


def test_update_writes_the_default_into_its_existing_pull_request():
    step = _update_default()
    assert '`experience = "new"`' in step and '`experience = "developer"`' in step
    assert "`[project]`" in step
    assert "the same pull request" in step and "no pull request of its own" in step
    # The PR body says so.
    assert "experience default" in _update_step("The PR")
    # Before the PR is made.
    text = _text(UPDATE)
    assert text.index("**The project's experience default") < text.index("**The PR,**")


def test_update_says_github_posts_are_the_same_for_every_level_section():
    assert "same for every level" in _update_default()


# Set-up now says the guided start asks


def test_setup_says_the_guided_start_asks():
    row = next(l for l in _text(SETUP).splitlines() if l.startswith("| Experience"))
    assert "the guided start asks each person whose level is unknown" in row
