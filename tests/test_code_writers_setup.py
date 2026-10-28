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

from conftest import KIT
from test_doctor import _lines, _prof, _project, _report
from workflow import doctor
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


def test_setup_pushes_in_a_command_of_its_own():
    write = _section(_text(SETUP), "3. Write")
    assert "push the branch in a command of its own" in write and CHAINED in write


def test_setup_pull_request_and_checklist_name_who_writes_code():
    body = _section(_text(SETUP), "4. The pull request")
    assert "who writes code" in body.lower() and f'"{NAME}"' in body
    checklist = _section(_text(SETUP), "Checklist")
    assert "Who writes code asked" in checklist and "`code_paths`" in checklist and "a command of its own" in checklist


# ---------- update-workflow ----------


def test_update_asks_once_for_a_profile_without_code_writers():
    step = _update_step("Who writes code")
    assert "`WF profile check`" in step and '`"code_writers": null`' in step
    assert "ask once" in step
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
    assert "once the update's other files are written" in step
    assert '`code_writers = "ticket"`' in step and '`code_writers = "any"`' in step and "`[guard]`" in step
    pr = _update_step("The PR")
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
    assert "the conductor never runs it" in intro
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
    assert "in a command of its own" in pr and CHAINED in pr
    assert "open the pull request" in pr.lower() and '("Pushing")' in pr
    assert "never merge it, or enable auto-merge on it, yourself" in pr
    # A loosening counts only once it merges: the base's "ticket" wins until then.
    assert "**Loosening waits for the merge.**" in pr


def test_choose_who_writes_code_proposes_code_paths_as_set_up_does():
    paths = _section(_part(), "3. The code paths")
    assert "as set-up does" in paths and "for the person to confirm" in paths and "The code paths" in paths
    assert "the profile's own list" in paths


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


def _doctor_writers_line(tmp_path, guard=""):
    root = _project(tmp_path, profile=_prof("ruleset = true\n", guard))
    return _lines(_report(tmp_path, root))["kit.code_writers"]


def test_check_setup_offers_it_on_doctors_unanswered_note(tmp_path):
    offers = _section(_text(CHECK), "3. The offers")
    para = _para(offers, "**Who writes code.**")
    # Keyed on the line as doctor gives it: its id, its status and its fix.
    assert "`kit.code_writers`" in para and "`note`" in para and f'"{NAME}"' in para
    assert f"**{NAME}**" in para and "**Not now**" in para
    assert "upgrade-setup" in para
    assert "plugin mode" in para
    # Doctor's line is that: a note, no offer of its own, its fix naming the step.
    ln = _doctor_writers_line(tmp_path)
    assert (ln["status"], ln["offer"]) == ("note", None), ln
    assert NAME in ln["fix"], ln


@pytest.mark.parametrize("answer", ["ticket", "any"])
def test_check_setup_does_not_offer_it_once_answered(tmp_path, answer):
    # Doctor's fix names the step only while unanswered, which is what the offer keys on.
    ln = _doctor_writers_line(tmp_path, f'[guard]\ncode_writers = "{answer}"\ncode_paths = ["src/**"]\n')
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


def test_changelog_notes_it_under_unreleased():
    log = _text(KIT / "CHANGELOG.md")
    start = log.index("## Unreleased\n")
    end = log.index("\n## ", start + 1)
    assert "#345" in log[start:end] and NAME in log[start:end]
    # No version bump: VERSION is still the last release's.
    released = log[end + 4:].split("\n", 1)[0].strip()
    assert (KIT / "VERSION").read_text().strip() == released
