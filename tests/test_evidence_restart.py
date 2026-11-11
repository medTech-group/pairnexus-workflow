"""#673: a background evidence run its head outran starts again on the
checkout's head, with the same options, whether or not the pull request has
merged since; after the merge, against the base it merged onto (the merge
commit's first parent), never the base branch's latest.

The repository below plays it out: the pull request adds a test and merges onto
a base with 3; another pull request then adds 2 more to the base branch. A
second one has the merge queue merge a head behind its base: the merge commit's
first parent holds a pull request merged ahead of it, so the restart compares
with where that parent and the head meet (`git merge-base`)."""

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
    # A head level with its base: where they meet is the first parent itself.
    assert git(root, "merge-base", "HEAD", f"{merge}^1").strip() == parent
    assert _evidence(monkeypatch, root, "--base-ref", f"{merge}^1") == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == evidence.headline(head, True)
    assert f"Base branch (`{merge}^1` at `{parent[:12]}`): 3 passed; this commit: 4." in out


def _merged_behind(tmp_path):
    """(the checkout, the merge commit): the pull request adds 2 tests to a base
    with 3; one ahead of it in the queue adds 3 and merges first; the queue then
    merges this head, never updated, onto that base."""
    root = _repo(tmp_path, {f"tests/test_{n}.txt": "pass" for n in range(3)})
    git(root, "checkout", "-qb", "pr")
    for n in (3, 4):
        (root / f"tests/test_{n}.txt").write_text("pass")
    git(root, "add", ".")
    git(root, "commit", "-qm", "the pull request adds two tests")
    git(root, "checkout", "-q", "main")
    for n in (5, 6, 7):  # the pull request ahead of it in the queue
        (root / f"tests/test_{n}.txt").write_text("pass")
    git(root, "add", ".")
    git(root, "commit", "-qm", "the pull request ahead of it adds three tests")
    git(root, "merge", "-q", "--no-ff", "-m", "Merge pull request", "pr")
    merge = git(root, "rev-parse", "HEAD").strip()
    git(root, "update-ref", "refs/remotes/origin/main", "main")
    git(root, "checkout", "-q", "pr")
    return root, merge


def test_a_head_merged_behind_its_base_never_had_the_first_parents_tests(tmp_path, monkeypatch, capsys):
    # Round 1 of #726: `--base-ref <merge>^1` counts the tests of a pull request
    # merged ahead of this one in the queue.
    root, merge = _merged_behind(tmp_path)
    assert _evidence(monkeypatch, root, "--base-ref", f"{merge}^1") == 1
    assert "Fewer tests than the base branch" in capsys.readouterr().out


def test_a_head_merged_behind_its_base_compares_with_where_it_left_the_base(tmp_path, monkeypatch, capsys):
    root, merge = _merged_behind(tmp_path)
    fork = git(root, "merge-base", "HEAD", f"{merge}^1").strip()
    assert fork != git(root, "rev-parse", f"{merge}^1").strip()
    assert _evidence(monkeypatch, root, "--base-ref", fork) == 0
    assert f"Base branch (`{fork}` at `{fork[:12]}`): 3 passed; this commit: 5." in capsys.readouterr().out


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


def test_build_ticket_reposts_the_evidence_to_come_line_for_the_new_head():
    rule = _restart()
    assert "When your latest note on the tracking issue says the evidence for the old head is to come (step 5)" in rule
    assert 'post the line again there for the new one: "Evidence for `<sha>` to come on #<PR>"' in rule


def test_build_ticket_restarts_after_the_merge_against_the_base_it_merged_onto():
    rule = _restart()
    assert "until it has merged, `--base-ref origin/<base>`" in rule
    assert "the base it merged onto, as far as your head had it" in rule
    assert "`--base-ref $(git merge-base HEAD <merge>^1)`" in rule and "`merge_commit_sha`" in rule
    assert "`--base-ref <merge>^1`" not in rule
    # The merge commit's first parent when the head was level with it; where
    # the head left the base when the queue merged it behind (step 3).
    assert "the merge commit's first parent when your head was level with it" in rule
    assert "where your head left the base when the merge queue merged it behind (step 3)" in rule
    # Why neither the base branch's latest nor a first parent alone: they hold
    # pull requests merged after or ahead of this one.
    assert "holds this pull request and any merged after it" in rule
    assert "`<merge>^1` any merged ahead of it in the queue" in rule


def test_a_stop_the_restart_covers_is_no_reason_for_no_report():
    stay = _step(5).split("**Then stay**", 1)[1]
    assert "(it stopped, or couldn't run)" not in stay
    assert "other than by your head moving, which step 2 starts again" in stay
