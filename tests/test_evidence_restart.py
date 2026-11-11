"""#673: a background evidence run its head outran starts again on the
checkout's head, with the same options, whether or not the pull request has
merged since; after the merge, against the base it merged onto (the merge
commit's first parent), never the base branch's latest.

The repository below plays it out: the pull request adds a test and merges onto
a base with 3; another pull request then adds 2 more to the base branch."""

from pathlib import Path

from conftest import git
from test_evidence_after_the_merge import _step
from test_evidence_review import _evidence, _repo
from test_evidence_tree import _section_6_step_2

from workflow import evidence

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/build-ticket/SKILL.md"


def _merged(tmp_path):
    """(the checkout, the merge commit): the checkout on the pull request's
    head, `origin/main` the base branch's latest, past the merge."""
    root = _repo(tmp_path, {f"tests/test_{n}.txt": "pass" for n in range(3)})  # 3 passing tests on main
    git(root, "checkout", "-qb", "pr")
    (root / "tests/test_3.txt").write_text("pass")
    git(root, "add", ".")
    git(root, "commit", "-qm", "the pull request adds a test")
    git(root, "checkout", "-q", "main")
    git(root, "merge", "-q", "--no-ff", "-m", "Merge pull request", "pr")
    merge = git(root, "rev-parse", "HEAD").strip()
    for n in (4, 5):  # another pull request, merged after it
        (root / f"tests/test_{n}.txt").write_text("pass")
    git(root, "add", ".")
    git(root, "commit", "-qm", "another pull request adds two tests")
    git(root, "update-ref", "refs/remotes/origin/main", "main")
    git(root, "checkout", "-q", "pr")
    return root, merge


def test_after_the_merge_the_base_branchs_latest_counts_tests_this_head_never_had(tmp_path, monkeypatch, capsys):
    # Round 2 of #670: the restart's `--base-ref origin/<base>` after the merge.
    root, _ = _merged(tmp_path)
    assert _evidence(monkeypatch, root, "--base-ref", "origin/main") == 1
    assert "Fewer tests than the base branch" in capsys.readouterr().out


def test_after_the_merge_the_restart_compares_with_the_merge_commits_first_parent(tmp_path, monkeypatch, capsys):
    root, merge = _merged(tmp_path)
    parent = git(root, "rev-parse", f"{merge}^1").strip()
    head = git(root, "rev-parse", "HEAD").strip()
    assert _evidence(monkeypatch, root, "--base-ref", f"{merge}^1") == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == evidence.headline(head, True)
    assert f"Base branch (`{merge}^1` at `{parent[:12]}`): 3 passed; this commit: 4." in out


def _restart() -> str:
    step = _section_6_step_2(SKILL.read_text())
    return step.split("**When it stops because your head moved", 1)[1].split("\n   - ", 1)[0]


def test_build_ticket_starts_a_run_its_head_outran_again_merged_or_not():
    rule = _restart()
    # Both kinds of stop, in one sentence: "HEAD moved", and a run the session
    # stopped before changing its checkout, which counts as one ("While it runs").
    assert '("HEAD moved", a run you stopped before changing your checkout among them)' in rule
    assert "start it again on your checkout's head" in rule
    assert "as a tracked background task" in rule
    assert "whether or not the pull request has merged since" in rule
    # The same options: `--all` where step 2 ran it with `--all`.
    assert "with the same options" in rule and "`--all`" in rule


def test_build_ticket_restarts_a_run_you_stopped_only_once_your_change_is_made():
    rule = _restart()
    # A run that stopped by itself starts again at once ...
    assert "one that stopped by itself at once" in rule
    # ... but one you stopped ("While it runs": stop it first, then make the
    # change) waits for the change, or it runs beside it on the old head.
    assert (
        "one you stopped once your change is made (an edit or a merge of the base committed and pushed, "
        "a pull done), on the new head, never between the stop and the change"
    ) in rule
    assert "start it again at once" not in rule


def test_build_ticket_restarts_after_the_merge_against_the_base_it_merged_onto():
    rule = _restart()
    assert "until it has merged, `--base-ref origin/<base>`" in rule
    assert "the base it merged onto, the merge commit's first parent" in rule
    assert "`--base-ref <merge>^1`" in rule and "`merge_commit_sha`" in rule
    # Why not the base branch's latest: it holds this pull request, and any merged since.
    assert "holds this pull request and any merged after it" in rule


def test_a_stop_the_restart_covers_is_no_reason_for_no_report():
    stay = _step(5).split("**Then stay**", 1)[1]
    assert "(it stopped, or couldn't run)" not in stay
    assert "other than by your head moving, which step 2 starts again" in stay
