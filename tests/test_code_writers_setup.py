"""#345 (spec #338): who writes code is asked once and changed by a pull
request. Through the skills' lines, read from their files as the kit-release
tests do: `setup-workflow`'s question, its order and recommendation, the
`code_paths` proposal and its words for a project with no ticket environment;
`update-workflow` asking once for a profile without `code_writers`, a skip
writing nothing; `upgrade-setup`'s "Choose who writes code", ending in a pull
request; `check-setup` offering it on doctor's unanswered note, and its
ticket-session line worded for both answers. Every one of them pushes in a
command of its own (answer 41)."""

import re
import tomllib

import pytest

from changelog_notes import since_0110
from conftest import KIT
from test_doctor import _lines, _prof, _project, _report
from workflow import doctor, vendor
from workflow.profile import parse

SETUP = KIT / "skills/setup-workflow/SKILL.md"
UPDATE = KIT / "skills/update-workflow/SKILL.md"
UPGRADE = KIT / "skills/upgrade-setup/SKILL.md"
CHECK = KIT / "skills/check-setup/SKILL.md"
INSTALL = KIT / "docs/install.md"
NAME = "Choose who writes code"
QUESTION = "Who writes code in this project?"
FIRST, SECOND = "**Only ticket sessions (Recommended)**", "**Any session**"
CHAINED = "never chained with the commit (`git commit … && git push`)"


def _text(path):
    return path.read_text(encoding="utf-8")


def _section(text, title, level="##"):
    """The `<level> ...` section whose heading contains `title`, up to the next
    heading of that level or higher."""
    m = re.search(rf"^{level} [^\n]*{re.escape(title)}[^\n]*\n(.*?)(?=^#{{1,{len(level)}}} |\Z)", text, re.M | re.S)
    assert m, f"no section {title!r}"
    return m.group(1)


def _para(text, opening):
    """The paragraph (or list item) that opens with `opening`."""
    i = text.index(opening)
    return text[i:].split("\n\n", 1)[0]


def _update_step(title):
    m = re.search(rf"^\d+\. \*\*{re.escape(title)}[^\n]*\n?(.*?)(?=^\d+\. \*\*|\Z)", _text(UPDATE), re.M | re.S)
    assert m, f"no step {title!r}"
    return m.group(0)


def _part(title=NAME):
    m = re.search(rf"^# [^\n]*{re.escape(title)}[^\n]*\n(.*?)(?=^# |\Z)", _text(UPGRADE), re.M | re.S)
    assert m, f"no part {title!r}"
    return m.group(1)


def _asks_first_ticket_sessions(text):
    assert QUESTION in text
    assert FIRST in text and SECOND in text
    assert text.index(FIRST) < text.index(SECOND)


# ---------- setup-workflow ----------


def _setup_writers():
    """Set-up's "Who writes code" paragraphs, up to its code paths."""
    text = _text(SETUP)
    return text[text.index("**Who writes code.**"):text.index("**The code paths,**")]


def test_setup_asks_who_writes_code_only_ticket_sessions_first_and_recommended():
    asks = _section(_text(SETUP), "2. Ask")
    row, = [ln for ln in asks.splitlines() if ln.startswith("| Who writes code |")]
    _asks_first_ticket_sessions(row)
    _asks_first_ticket_sessions(_setup_writers())


def test_setup_says_what_only_ticket_sessions_means_without_a_ticket_environment():
    text = _setup_writers()
    assert "While no ticket environment exists" in text
    assert "nothing writes code" in text and '"Set up unattended runs"' in text
    # A new project's first ticket: a session the owner starts in the ticket environment.
    assert "a new project's first ticket is built in a session you start yourself in the ticket environment" in text
    # Plugin mode has no unattended runs: the owner's own ticket session, and the rule's limit.
    assert "In plugin mode" in text and "`WORKFLOW_ROLE=ticket`" in text
    assert "a cloud session has no kit and no guard" in text


def test_setup_proposes_code_paths_from_the_layout_and_asks_when_there_is_no_code_yet():
    paths = _para(_text(SETUP), "**The code paths,**")
    assert "propose `code_paths` from the project's layout" in paths and "for the owner to confirm" in paths
    assert "a path that is both counts as protected, not code" in paths
    assert "For a project with no code yet" in paths
    assert "the source and test folders its stack uses" in paths
    assert "ask which folders will hold code" in paths
    assert "With **Any session**, propose none" in paths


def test_setup_writes_both_keys_as_plain_lines_and_a_skip_writes_nothing():
    write = _section(_text(SETUP), "3. Write")
    item = _para(write, "- **`code_writers` and `code_paths`,**")
    assert "`[guard]`" in item and '`# code_writers = "ticket"`' in item and "`# code_paths = …`" in item
    assert "plain" in item
    assert "When the question was skipped, leave both commented lines as they are" in item
    # A skip is "not answered": doctor and "check the set-up" go on offering it.
    assert "A skipped question writes nothing" in _setup_writers() and f'"{NAME}"' in _setup_writers()
    # profile check's empty-list warning stays only when no folder was named.
    check = _para(write, "- Run `WF profile check`")
    assert "`guard.code_paths` is empty" in check and "only when the owner named no folders" in check


def test_the_lines_set_up_writes_are_read_from_the_template(tmp_path):
    # The template's commented lines, replaced as set-up says, read as the answer.
    template = _text(KIT / "templates/profile.toml")
    assert '\n# code_writers = "ticket"\n' in template and "\n# code_paths = " in template
    for answer in ("ticket", "any"):
        after = template.replace('# code_writers = "ticket"', f'code_writers = "{answer}"', 1)
        after = re.sub(r"^# code_paths = .*$", 'code_paths = ["src/**", "tests/**"]', after, count=1, flags=re.M)
        p = parse(tomllib.loads(after), KIT)
        assert (p.code_writers, p.code_paths) == (answer, ["src/**", "tests/**"])
        # Alone on its line, so it is read from that line when the profile doesn't parse.
        assert re.search(rf'^code_writers = "{answer}"$', after, re.M)
    # Skipped: the template as it is, not answered.
    assert parse(tomllib.loads(template), KIT).code_writers is None


def test_setup_writes_the_answer_last():
    item = _para(_section(_text(SETUP), "3. Write"), "- **`code_writers` and `code_paths`,**")
    assert "Write these two lines last, after every other item of this step 3" in item and "Then run `WF profile check` again" in item


def test_setup_pull_request_words_plugin_mode():
    body = _section(_text(SETUP), "4. The pull request")
    line = _para(body, "- who writes code, as answered")
    assert "in plugin mode instead, that code is written only in a session started on the owner's computer with `WORKFLOW_ROLE=ticket`" in line


def test_setup_pushes_in_a_command_of_its_own():
    write = _section(_text(SETUP), "3. Write")
    assert "push the branch in a command of its own" in write and CHAINED in write


def test_setup_names_the_question_in_its_description():
    head = _text(SETUP).split("---", 2)[1]
    assert "the owner, who writes code)" in head


def test_with_only_ticket_sessions_set_up_unattended_runs_is_what_lets_code_be_written():
    # Vendored, "only ticket sessions": nothing writes code until a ticket environment exists.
    body = _section(_text(SETUP), "4. The pull request")
    runs = _para(body, '  - **"Set up unattended runs"**')
    assert "With only ticket sessions writing code" in runs and "what lets code be written at all" in runs
    after = _section(_text(SETUP), "5. After the merge")
    assert "or answered **Only ticket sessions** in vendored mode" in after
    assert "`set_up_unattended_runs`" in after and 'after "Protect `main`"' in after


def test_setup_pull_request_and_checklist_name_who_writes_code():
    body = _section(_text(SETUP), "4. The pull request")
    assert "who writes code" in body.lower() and f'"{NAME}"' in body
    checklist = _section(_text(SETUP), "Checklist")
    assert "Who writes code asked" in checklist and "`code_paths`" in checklist and "a command of its own" in checklist


# ---------- update-workflow ----------


def test_update_asks_once_for_a_profile_without_code_writers():
    step = _update_step("Who writes code")
    assert "`WF profile check`" in step and '`"code_writers": null`' in step
    assert "ask it a single time" in step
    _asks_first_ticket_sessions(step)
    # Set-up's words for "only ticket sessions", and its code paths.
    assert "set-up's" in step and "`code_paths`" in step
    # In the update's own pull request, before it is made.
    assert "the same pull request" in step
    text = _text(UPDATE)
    assert text.index("**The project's experience default") < text.index("**Who writes code") < text.index("**The PR,**")


def test_update_skip_writes_nothing_as_the_experience_question_does():
    step = _update_step("Who writes code")
    assert "A skipped question or **Not now** writes nothing, as the experience question's does" in step
    assert "each later update asks once while the profile has no `code_writers`" in step
    assert f'"{NAME}"' in step


def test_update_writes_the_answer_last_and_says_it_in_the_pull_request():
    step = _update_step("Who writes code")
    assert "after the update's other files are written" in step
    assert '`code_writers = "ticket"`' in step and '`code_writers = "any"`' in step and "`[guard]`" in step
    pr = _update_step("The PR")
    assert "nothing writes code until one exists" in pr and '"Set up unattended runs" makes one' in pr
    assert "who writes code" in pr and "push the branch in a command of its own" in pr and CHAINED in pr


# ---------- upgrade-setup ----------


def test_upgrade_setup_has_choose_who_writes_code_as_its_sixth_and_last_part():
    text = _text(UPGRADE)
    head = text.split("---", 2)[1]
    assert f'"{NAME}"' in head
    assert f'**"{NAME}"**' in text.split("\n## ", 1)[0]
    assert "The sixth part, last." in text and "shared by all six" in text
    assert text.index("\n# Use a merge queue\n") < text.index(f"\n# {NAME}\n")
    # Doctor names it in its fix; the skill's part is the one it names.
    assert doctor.CHOOSE_WRITERS == NAME


def test_choose_who_writes_code_is_attended_only_and_offered_by_check_setup():
    intro = _part().split("\n## ", 1)[0]
    assert "The sixth path." in intro
    assert "in an attended session" in intro and "`kit.code_writers`" in intro
    assert 'Nor "Choose who writes code".' in _text(UPGRADE)  # the conductor never runs it
    assert "in plugin mode this is where it is asked" in intro
    offered = _section(_text(UPGRADE), "When it's offered")
    assert f'**"{NAME}"**' in offered and "`check-setup`" in offered


def test_choose_who_writes_code_asks_the_same_question_recommending_ticket_sessions():
    q = _section(_part(), "2. The question")
    _asks_first_ticket_sessions(q)
    assert "always first, whatever the answer now" in q
    assert "**Not now**" in q
    # Worded once, in set-up's words, which ship beside it (vendored and plugin).
    assert "no ticket environment" in q and "plugin mode" in q and "in set-up's words" in q
    assert "`.claude/skills/setup-workflow/SKILL.md` (vendored)" in q
    assert "`<this skill's directory>/../setup-workflow/SKILL.md` (plugin)" in q
    assert (KIT / "skills/upgrade-setup/../setup-workflow/SKILL.md").is_file()


def test_the_answers_are_worded_in_one_place():
    # Set-up words the answers; the update and "Choose who writes code" point at them.
    setup = _setup_writers()
    for text in (_update_step("Who writes code"), _section(_part(), "2. The question")):
        assert "in set-up's words" in text
        assert "may write code" not in text  # the answers' words aren't copied
    assert "Any session may write code, as before." in setup


def test_what_a_person_reads_never_says_planning_session_yet():
    # The glossary has no "Planning session" until #275 raises its cap (spec #338).
    for text in (_setup_writers(), _update_step("Who writes code"), _part(), _para(_text(SETUP), "**The code paths,**"),
                 _section(_text(SETUP), "4. The pull request")):
        assert "planning session" not in text.lower()


def test_choose_who_writes_code_ends_in_a_pull_request_the_owner_merges():
    pr = _section(_part(), "4. One pull request")
    assert "`workflow/code-writers`" in pr
    assert "`[guard]`" in pr and '`code_writers = "ticket"`' in pr and '`code_writers = "any"`' in pr
    assert "`code_paths`" in pr and "Change nothing else" in pr
    assert "`WF profile check` passes" in pr
    # The push in a command of its own, as "Pushing" says for every path.
    assert "push the branch in a command of its own (\"Pushing\")" in pr
    assert "open the pull request" in pr.lower()
    assert "never merge it, or enable auto-merge on it, yourself" in pr
    # A loosening counts only once it merges, and in a branch only once the merged
    # base is in it: the stricter of the working tree's answer and the base's counts.
    loosening = _para(pr, "**Loosening waits for the merge.**")
    assert "or removing code paths" in loosening
    # Where it stands, and the default code paths, are the base's: the branch starts there.
    where = _section(_part(), "1. Where it stands")
    assert "`git show origin/<base>:.claude/workflow/profile.toml`" in where
    assert "this session's branch is behind" in where and "not only fetched" in where
    paths = _section(_part(), "3. The code paths")
    assert "with the base's list (step 1) as the default" in paths and "keep the base's list as it is" in paths
    assert "not only fetched" in loosening and "the stricter of the working tree's answer and the base's" in loosening
    assert "once it has the merged base branch in it" in _section(_part(), "5. Where it ends")
    # Nothing to change is judged after the code paths, against the base's profile.
    assert "When the answer and the confirmed code paths are what `origin/<base>`'s profile says already" in pr
    # ...never at the question, before the code paths are confirmed.
    assert "already" not in _section(_part(), "2. The question")


def test_an_open_pull_request_is_found_before_asking():
    # A second answer beside an open one would be lost, or merge into two `code_writers` lines.
    where = _section(_part(), "1. Where it stands")
    assert "an open pull request changing `code_writers` in the profile" in where and "the kit's update among them" in where
    assert "If there is one, ask nothing" in where
    step = _update_step("Who writes code")
    assert "an open pull request changing `code_writers` in the profile" in step and "an earlier kit update's among them" in step
    # Looked for before the question is asked.
    assert step.index("If there is one, ask nothing") < step.index("Otherwise ask it a single time")
    # Its lines go where upgrade-setup puts them, never a second key beside one already there.
    assert "in place of its line there, or of a commented one, or at the end of `[guard]`" in step


def test_set_up_offers_runs_after_the_merge_among_upgrade_setups_moments():
    offered = _section(_text(UPGRADE), "When it's offered")
    assert '"Set up unattended runs" once too, after it, when set-up\'s answer was only ticket sessions in vendored mode' in offered


def test_choose_who_writes_code_proposes_code_paths_as_set_up_does():
    paths = _section(_part(), "3. The code paths")
    assert "as set-up does" in paths and "for the person to confirm" in paths and "The code paths" in paths
    assert "the base's list" in paths


def test_every_upgrade_path_pushes_in_a_command_of_its_own():
    text = _text(UPGRADE)
    pushing = _para(text, "**Pushing.**")
    assert "in a command of its own" in pushing and CHAINED in pushing
    assert text.index("**Pushing.**") < text.index("\n# Protect `main`\n")
    steps = [ln for ln in text.splitlines() if re.match(r"^\d+\. (Push|Commit)", ln)]
    assert len(steps) == 6, steps  # each of the six paths' pull requests
    for ln in steps:
        assert "in a command of its own" in ln and '"Pushing"' in ln, ln


# ---------- check-setup ----------


def _doctor_writers_line(tmp_path, guard="", vendored=True):
    tmp_path.mkdir(exist_ok=True)
    settings = {} if vendored else {"enabledPlugins": {vendor.PLUGIN_KEY: True}}
    root = _project(tmp_path, profile=_prof("ruleset = true\n", guard), vendored=vendored, settings=settings or None)
    return _lines(_report(tmp_path, root))["kit.code_writers"]


def test_check_setup_offers_it_on_doctors_unanswered_note(tmp_path):
    offers = _section(_text(CHECK), "3. The offers")
    para = _para(offers, "**Who writes code.**")
    # Keyed on the line as doctor gives it: its id, its status and its fix.
    assert "`kit.code_writers`" in para and "`note`" in para and f'"{NAME}"' in para
    # Only the unanswered line has no offer: under "ticket" with no ticket environment it offers runs.
    assert "While `guard.code_writers` is unanswered, doctor's `kit.code_writers` line carries no `offer`" in para
    assert f"**{NAME}**" in para and "**Not now**" in para and 'without "(Recommended)"' in para
    assert "upgrade-setup" in para
    assert "plugin mode" in para
    # Doctor's line is that, in both modes: a note, no offer of its own, its fix naming the step.
    for vendored in (True, False):
        ln = _doctor_writers_line(tmp_path / str(vendored), vendored=vendored)
        assert (ln["status"], ln["offer"]) == ("note", None), ln
        assert NAME in ln["fix"], ln


@pytest.mark.parametrize("answer", ["ticket", "any"])
def test_check_setup_does_not_offer_it_once_answered(tmp_path, answer):
    # Doctor's fix names the step only while unanswered, which is what the offer keys on.
    ln = _doctor_writers_line(tmp_path, f'[guard]\ncode_writers = "{answer}"\ncode_paths = ["src/**"]\n')
    # Answered, with a ticket environment named: fine, not a line doctor couldn't read.
    assert ln["status"] == "fine", ln
    assert NAME not in (ln["fix"] or ""), ln


def test_check_setup_ticket_session_line_is_worded_for_both_answers():
    line = _para(_text(CHECK), "**Only in attended sessions.**")
    # Today's reading, with code_writers absent or "any".
    assert "`code_writers` absent or `\"any\"`" in line
    assert "`run.ticket_branch`" in line and "a `WORKFLOW_ROLE` that isn't a role" in line
    # Under "ticket" such a session is a planning session, and may run it.
    assert "`code_writers = \"ticket\"`" in line and "planning session" in line
    assert "pre-flight runs doctor itself" in line


# ---------- docs and changelog ----------


def test_install_names_the_question_and_the_upgrade():
    text = _text(INSTALL)
    every = _section(text, "Every project, whichever mode")
    assert "who writes code" in every and f'"{NAME}"' in every
    assert "once per update while it is unanswered" in every


def test_changelog_notes_it_under_unreleased():
    log = _text(KIT / "CHANGELOG.md")
    # Read as the other notes are, so a release that moves them under its heading still passes.
    assert "#345" in since_0110(log) and NAME in since_0110(log)
    start = log.index("## Unreleased\n")
    end = log.index("\n## ", start + 1)
    # No version bump: VERSION is still the last release's.
    released = log[end + 4:].split("\n", 1)[0].strip()
    assert (KIT / "VERSION").read_text().strip() == released
