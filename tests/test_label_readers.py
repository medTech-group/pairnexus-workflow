"""#778: `workflow doctor` and the conductor's estimate read an issue's labels
through `issues.labels_of` (#772), the one shared reader, rather than each
keeping its own copy; the empty name is settled so the readers agree.
"""

import inspect
from pathlib import Path

import pytest

from changelog_notes import entry
from workflow import doctor, estimate, issues, state

KIT = Path(__file__).resolve().parents[1]


def test_doctors_reader_is_the_shared_one():
    assert doctor._label_names is issues.labels_of


def test_estimate_keeps_no_label_reading_of_its_own():
    source = inspect.getsource(estimate)
    assert not hasattr(estimate, "_labels")
    assert '.get("labels")' not in source and ".get('labels')" not in source
    assert "issues_mod.labels_of" in source


@pytest.mark.parametrize(
    "labels, want",
    [([""], set()), ([{"name": ""}], set()), (["", {"name": ""}], set()), (["", "x"], {"x"}), ([{"name": ""}, {"name": "X"}], {"x"})],
)
def test_an_empty_name_reads_as_no_label_in_every_reader(labels, want):
    assert issues.labels_of({"labels": labels}) == want
    assert doctor._label_names({"labels": labels}) == want


def _past_run(n, labels):
    """A closed tracking issue as the GitHub API returns it, with one merged ticket."""
    ticket = {"status": "merged", "attempts": 1, "area": "x",
              "started_at": "2026-10-16T10:00:00Z", "merged_at": "2026-10-16T11:00:00Z"}
    s = {"version": 1, "run_id": f"run-{n}", "status": "stopped", "charter": None, "tickets": {"1": ticket},
         "ledger": [], "overrides": [], "for_owner": [], "kickoff_tickets": []}
    body = state.put(f"# Run: run-{n}\n\n## Now\n\nDone.\n\n<!-- workflow:agent -->", s)
    return {"number": n, "state": "closed", "closed_at": "2026-10-17T00:00:00Z", "labels": labels, "body": body}


@pytest.mark.parametrize(
    "labels",
    [["Workflow:Run"], [{"name": "WORKFLOW:RUN"}], [{"name": 5}, 7, "", {"name": ""}, "workflow:run"]],
    ids=["text, other case", "object, other case", "beside labels read past"],
)
def test_the_estimate_reads_the_run_label_as_github_matches_it(labels):
    runs, notes = estimate.past_runs([_past_run(140, labels)])
    assert len(runs) == 1, notes


@pytest.mark.parametrize("labels", [[""], [{"name": ""}], ["workflow:runs"], [{"name": ["workflow:run"]}], 5])
def test_the_estimate_skips_an_issue_without_the_run_label(labels):
    runs, _ = estimate.past_runs([_past_run(140, labels)])
    assert runs == []


def test_estimate_and_doctor_read_the_same_runs():
    """`doctor._read_runs` and `estimate.past_runs` keep an issue as a run on
    the same labels: the run label, in any case, among labels read past."""
    for labels in (["Workflow:Run"], ["", "workflow:run"], [""], [{"name": ""}], ["x"]):
        in_doctor = estimate.RUN_LABEL in doctor._label_names({"labels": labels})
        in_estimate = bool(estimate.past_runs([_past_run(140, labels)])[0])
        assert in_doctor == in_estimate, labels


def test_the_architecture_page_names_the_readers_that_use_it():
    page = (KIT / "docs/architecture/scripts--workflow.md").read_text(encoding="utf-8")
    helper = next(l for l in page.splitlines() if l.startswith("- `labels_of`:"))
    assert "`workflow doctor`" in helper and "`doctor._label_names`" in helper
    assert "estimate" in helper and "#778" in helper
    assert "empty name" in helper


def test_the_changelog_note():
    note = entry("#778, found in the review of #772's pull request")
    assert "`issues.labels_of`" in note
    assert "`VERSION` is unchanged" in note
    assert "tests/test_label_readers.py" in note
