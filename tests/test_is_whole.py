"""`issues.is_whole` is the one shared whole-number check (#773): an `int`,
never a `bool`. `status._whole`, `state._int`, `doctor._number` and the checks
in `merge.py`, `presets.py`, `charter.py` and the kit's other modules call it,
rather than each keeping its own copy.
"""

import inspect
import re
from pathlib import Path

import pytest

from changelog_notes import entry
from workflow import charter, doctor, issues, merge, presets, state, status

KIT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("v, whole", [
    (True, False), (False, False), (3, True), (0, True), (-2, True),
    (3.0, False), ("3", False), (None, False), ([3], False), ({"n": 3}, False),
])
def test_the_tickets_own_cases(v, whole):
    assert issues.is_whole(v) is whole


def test_the_callers_read_as_before():
    # status: a whole number, or missing.
    assert status._whole(None) and status._whole(3)
    assert not status._whole(True) and not status._whole(3.0) and not status._whole("3")
    # state
    assert state._int(3) and not state._int(True) and not state._int(3.0) and not state._int(None)
    # doctor
    assert doctor._number({"number": 7}) == 7
    assert doctor._number({"number": True}) is None
    assert doctor._number({"number": "7"}) is None
    # merge: a whole number that isn't negative.
    assert merge._int(3) == 3 and merge._int(0) == 0
    assert merge._int(-1) is None and merge._int(True) is None and merge._int(3.0) is None
    # presets
    assert presets._whole(3, 1, 5) and not presets._whole(True, 0, 5) and not presets._whole(9, 1, 5)
    assert presets._whole(1, 1, 1) and not presets._whole(1.0, 1, 1)
    # charter
    assert charter._pos_int(3) and not charter._pos_int(True) and not charter._pos_int(0)
    assert charter._is_int_list([1, 2]) and not charter._is_int_list([1, True]) and not charter._is_int_list([0])


def test_presets_rule_and_run_read_whole_numbers_only():
    assert presets._run(type("P", (), {"review_rounds": 4})(), "review_rounds") == 4
    default = presets._run(None, "review_rounds")
    assert presets._run(type("P", (), {"review_rounds": True})(), "review_rounds") == default


_COPY = re.compile(r"isinstance\((\w[\w.\[\]\"']*), int\)\s+and\s+not\s+isinstance\(\1, bool\)"
                   r"|type\([^)]*\)\s+is\s+int\b")


def test_no_copy_of_the_check_is_left():
    own, start = inspect.getsourcelines(issues.is_whole)
    own_lines = range(start, start + len(own))
    left = []
    for path in sorted((KIT / "scripts/workflow").glob("*.py")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _COPY.search(line) and not (path.name == "issues.py" and n in own_lines):
                left.append(f"{path.name}:{n}: {line.strip()}")
    assert left == []


def test_the_architecture_page_lists_it():
    page = (KIT / "docs/architecture/scripts--workflow.md").read_text(encoding="utf-8")
    helpers = page[page.index("## Helpers"):page.index("## Rules")]
    assert "`is_whole`: in `issues.py`" in helpers


def test_the_changelog_note():
    note = entry("#773, found in the review of #770's pull request")
    assert "is_whole" in note
    assert "`VERSION` is unchanged" in note
