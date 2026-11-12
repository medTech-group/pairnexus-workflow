"""`issues.is_whole` is the one shared whole-number check (#773): an `int`,
never a `bool`. `status._whole`, `state._int`, `doctor._number` and the checks
in `merge.py`, `presets.py`, `charter.py` and the kit's other modules call it,
rather than each keeping its own copy.
"""

import ast
import inspect
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


def _is_check(node, kind: str) -> bool:
    """`isinstance(<anything>, int)` or `isinstance(<anything>, bool)`, with
    `not` before it or not."""
    while isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        node = node.operand
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "isinstance"
            and len(node.args) == 2 and isinstance(node.args[1], ast.Name) and node.args[1].id == kind)


def _checks_in(node) -> list:
    """The isinstance calls joined by `and`/`or` in a condition, `not`s and
    nested conditions included."""
    while isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        node = node.operand
    if isinstance(node, ast.BoolOp):
        return [c for v in node.values for c in _checks_in(v)]
    return [node]


def _copies(source: str) -> list[int]:
    """The lines of each copy of the whole-number check in a module's source:
    an `int` check and a `bool` check in one condition, in either order and
    either sense (`isinstance(x, int) and not isinstance(x, bool)`, `not
    isinstance(x, int) or isinstance(x, bool)`), whatever the value's
    spelling, and `type(x) is int`, `is not int`, `== int` or `!= int`."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.BoolOp):
            parts = _checks_in(node)
            if any(_is_check(c, "int") for c in parts) and any(_is_check(c, "bool") for c in parts):
                lines.append(node.lineno)
        elif isinstance(node, ast.Compare):
            sides = [node.left, *node.comparators]
            typed = any(isinstance(s, ast.Call) and isinstance(s.func, ast.Name) and s.func.id == "type" for s in sides)
            if typed and any(isinstance(s, ast.Name) and s.id == "int" for s in sides) \
                    and all(isinstance(op, (ast.Is, ast.IsNot, ast.Eq, ast.NotEq)) for op in node.ops):
                lines.append(node.lineno)
    return sorted(set(lines))


@pytest.mark.parametrize("line", [
    "ok = isinstance(n, int) and not isinstance(n, bool)",
    "ok = isinstance(i.get('number'), int) and not isinstance(i['number'], bool)",
    "ok = not isinstance(x, int) or isinstance(x, bool) or x < 0",
    "ok = isinstance(x, bool) or not isinstance(x, int)",
    "ok = all(isinstance(p, dict) and isinstance(p.get('n'), int) and not isinstance(p.get('n'), bool) for p in ps)",
    "ok = x is not None and (not isinstance(x, int) or isinstance(x, bool) or x < 0)",
    "ok = type(p.get('number')) is int",
    "ok = type(v) is not int or not 1 <= v <= 9",
    "ok = type(c.get('rule')) == int",
    "ok = (isinstance(x, int)\n      and not isinstance(x, bool))",
])
def test_the_scan_finds_each_form_of_a_copy(line):
    assert _copies(line) == [1]


@pytest.mark.parametrize("line", [
    "ok = issues_mod.is_whole(x) and x > 0",
    "ok = isinstance(x, (int, float)) and not isinstance(x, bool)",
    "ok = isinstance(x, int) and y > 0",
    "ok = isinstance(x, bool) and x",
    "ok = type(x) is str",
])
def test_the_scan_leaves_other_checks(line):
    assert _copies(line) == []


def test_no_copy_of_the_check_is_left():
    own, start = inspect.getsourcelines(issues.is_whole)
    own_lines = range(start, start + len(own))
    left = []
    for path in sorted((KIT / "scripts").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for n in _copies(text):
            if not (path.name == "issues.py" and n in own_lines):
                left.append(f"{path.relative_to(KIT)}:{n}: {text.splitlines()[n - 1].strip()}")
    assert left == []


def test_the_architecture_page_lists_it():
    page = (KIT / "docs/architecture/scripts--workflow.md").read_text(encoding="utf-8")
    helpers = page[page.index("## Helpers"):page.index("## Rules")]
    assert "`is_whole`: in `issues.py`" in helpers


def test_the_changelog_note():
    note = entry("#773, found in the review of #770's pull request")
    assert "is_whole" in note
    assert "`VERSION` is unchanged" in note
