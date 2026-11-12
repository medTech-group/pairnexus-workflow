"""`issues.labels_of` reads past a label of the wrong type (#772), so
`workflow status` reads labels through the one shared reader, and
`status.as_read` keeps no label filter of its own.
"""

from pathlib import Path

import pytest

from changelog_notes import entry
from workflow import issues, status

KIT = Path(__file__).resolve().parents[1]


def test_the_tickets_own_cases():
    assert issues.labels_of({"labels": [{"name": 5}, 7, "x", {"name": "Y"}]}) == {"x", "y"}
    assert issues.labels_of({"labels": 5}) == set()


@pytest.mark.parametrize(
    "labels",
    [None, 5, "spec", {"name": "spec"}, True, 1.5],
    ids=["null", "number", "text", "object", "bool", "float"],
)
def test_labels_that_arent_a_list_read_as_none(labels):
    assert issues.labels_of({"labels": labels}) == set()


def test_a_label_of_the_wrong_type_is_read_past_and_the_others_kept():
    labels = [{"name": 5}, 7, None, ["x"], True, {"name": None}, {}, "", {"name": ""}, "Spec", {"name": "Ready-For-Agent"}]
    assert issues.labels_of({"labels": labels}) == {"spec", "ready-for-agent"}


def test_no_labels_field_reads_as_none():
    assert issues.labels_of({}) == set()


def test_it_reads_as_doctors_reader_does():
    from workflow import doctor

    for labels in ([{"name": 5}, 7, "x", {"name": "Y"}], 5, None, "ab", {"name": "z"}, [None, ["q"], {"name": "Q"}]):
        assert issues.labels_of({"labels": labels}) == doctor._label_names({"labels": labels}), labels


@pytest.mark.parametrize(
    "labels",
    [[{"name": 5}, 7, None, ["x"], "workflow:in-progress", {"name": "spec"}], 5, {"name": "owner-task"}, "spec"],
    ids=["list", "number", "object", "text"],
)
def test_as_read_keeps_no_label_filter_of_its_own(labels):
    item = {"number": 1, "title": "Add notes", "state": "open", "labels": labels}
    assert status.as_read(item)["labels"] == labels


def test_the_architecture_page_says_which_reader_reads_labels():
    page = (KIT / "docs/architecture/scripts--workflow.md").read_text(encoding="utf-8")
    lines = page.splitlines()
    as_read = next(l for l in lines if l.startswith("- `as_read`:"))
    assert "`labels` and each label" not in as_read
    assert "`issues.labels_of`" in as_read
    helper = next(l for l in lines if l.startswith("- `labels_of`:"))
    assert "in `issues.py`" in helper
    assert "`workflow status`" in helper


def test_the_changelog_note():
    note = entry("#772, found in the review of #770's pull request")
    assert "`issues.labels_of`" in note
    assert "`VERSION` is unchanged" in note
    assert "tests/test_labels_of.py" in note
