"""#75: explanations stop, restart, and run during set-up, part of the quickstart
and the glossary (#35). Seam 1's way: the skills' wording, read from their
files as the kit-release tests read what ships, beside #74's hook text."""

import re

import pytest

from conftest import KIT
from workflow import context

START = KIT / "skills/start/SKILL.md"
SETUP = KIT / "skills/setup-workflow/SKILL.md"


def _text(path):
    return path.read_text(encoding="utf-8")


def _flat(text):
    """Lower-cased, with line breaks and runs of spaces as one space."""
    return re.sub(r"\s+", " ", text).lower()


def _level_change():
    """The guided start's "Tell yourself the new level" paragraph."""
    m = re.search(r"^\*\*Tell yourself the new level\*\*.*?(?=\n\n)", _text(START), re.M | re.S)
    assert m, "no 'Tell yourself the new level' paragraph in start"
    return m.group(0)


def _setup_explaining():
    """Set-up's paragraph on explaining the glossary's words."""
    m = re.search(r"^\*\*Explaining the glossary's words\.\*\*.*?(?=\n\n)", _text(SETUP), re.M | re.S)
    assert m, "no 'Explaining the glossary's words.' paragraph in setup-workflow"
    return m.group(0)


# The guided start: a level that changes mid-session


def test_developer_and_explain_less_stop_the_explanations_for_the_session():
    para = _level_change()
    assert '"explain less"' in para
    assert "the first question's answer" in para
    assert "stop explaining the glossary's words for the rest of the session" in para


def test_explain_more_reads_the_glossary_again_in_both_install_modes():
    para = _level_change()
    # words used while explaining nothing are explained at their next use
    assert "A word you used while explaining nothing hasn't been explained yet." in para
    assert 'After "explain more", read the glossary again' in para
    assert "`.claude/workflow/docs/glossary.md` vendored" in para
    assert "`docs/glossary.md` beside `skills/` in the plugin" in para
    assert "from then on" in para


# Set-up: before the kit is in the project


def test_setup_follows_the_rule_from_the_glossary_in_its_clone_after_new_to_building():
    para = _setup_explaining()
    assert "*new to building*" in para
    assert "`$KIT/docs/glossary.md`" in para and "clone of the kit" in para
    assert "for the rest of set-up" in para


def test_setup_explains_nothing_after_a_developer_answer():
    assert "A *developer* answer gets none" in _setup_explaining()


def test_setup_treats_a_skipped_question_as_new_to_building():
    assert "or a skipped question (worded as *new to building*)" in _setup_explaining()


def test_setup_asks_the_experience_question_first_on_its_own():
    """So the other questions' words come after the answer is known."""
    assert "Ask the experience question first, on its own" in _setup_explaining()


def test_setup_explains_after_the_question_is_asked_not_before():
    """It sits under "Ask", after the questions' table, since the rule starts with the answer."""
    text = _text(SETUP)
    ask = text.index("## 2. Ask")
    assert ask < text.index("**Explaining the glossary's words.**") < text.index("## 3. Write, on a branch")


def test_setup_keeps_explanations_out_of_its_pull_request():
    para = _setup_explaining()
    assert "the set-up pull request's body included, and the files and commit messages it carries" in para


# The same rule everywhere, never on GitHub included (both skills, and the hook)

KEY_PHRASES = [
    "in the glossary's wording",
    "the first time you use",
    "never again in this session",
    "never explain them in what you write on github (pull request descriptions, comments, reports)",
]


@pytest.mark.parametrize(
    "where",
    [
        pytest.param(_level_change, id="start"),
        pytest.param(_setup_explaining, id="setup-workflow"),
        pytest.param(lambda: context.GLOSSARY_RULE, id="hook"),
    ],
)
@pytest.mark.parametrize("phrase", KEY_PHRASES)
def test_the_rules_key_phrases_are_the_same_in_all_three(where, phrase):
    assert phrase in _flat(where())
