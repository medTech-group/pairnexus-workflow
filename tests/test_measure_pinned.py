"""`review-record --measure` counts with the same pinned `git diff` as the
hashes (#298, from #258): the configuration and a working tree's attributes
never change its counts, so both sides of the small threshold count the same
diff. In temporary repositories isolated from the user's git configuration,
whose `origin` is a local bare repository.
"""

import re

import pytest

from workflow import own_changes
from test_review_record_hashes import _no_user_git_config  # noqa: F401 (an autouse fixture)
from test_small_review import checkout, git, measure  # noqa: F401 (checkout is a fixture)

COUNTS = "11 lines in 4 files outside tests: within the small threshold"


def counts(capsys):
    code, out, err = measure(capsys)
    assert code == 0, err
    return out


def test_the_counts_are_unchanged_with_no_configuration(checkout, capsys):
    assert counts(capsys).startswith(COUNTS)


def test_a_rename_limit_of_one_doesnt_change_them(checkout, capsys):
    # One removed path against four added ones: past a limit of 1, git would
    # show the rename as a removal and an addition.
    git(checkout, "config", "diff.renameLimit", "1")
    assert counts(capsys).startswith(COUNTS)


@pytest.mark.parametrize("key, value", [("diff.renames", "false"), ("diff.algorithm", "patience"),
                                        ("core.bigFileThreshold", "10"), ("diff.external", "false")])
def test_other_diff_settings_dont_change_them(checkout, capsys, key, value):
    git(checkout, "config", key, value)
    assert counts(capsys).startswith(COUNTS)


def test_a_working_tree_gitattributes_doesnt_change_them(checkout, capsys):
    (checkout / ".gitattributes").write_text("*.py -diff\n*.md -diff\n")
    got = counts(capsys)
    # Before git 2.40, git ignores GIT_ATTR_SOURCE and reads the working tree's (the changelog says so).
    if tuple(int(n) for n in re.findall(r"\d+", git(checkout, "version"))[:2]) >= (2, 40):
        assert got.startswith(COUNTS)


def test_an_attributes_file_in_the_configuration_doesnt_change_them(checkout, capsys):
    attrs = checkout.parent / "attributes"
    attrs.write_text("*.py -diff\n")
    git(checkout, "config", "core.attributesFile", str(attrs))
    assert counts(capsys).startswith(COUNTS)


def test_the_commits_own_attributes_count(checkout, capsys):
    # As GitHub reads them: a file the commit marks `-diff` is binary, 0 lines.
    (checkout / ".gitattributes").write_text("src/new.py -diff\n")
    git(checkout, "add", ".gitattributes")
    git(checkout, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "attributes")
    assert counts(capsys).startswith("7 lines in 5 files outside tests")


def test_a_submodule_counts_whatever_the_configuration(checkout, capsys, tmp_path):
    lib = tmp_path / "lib"
    git(tmp_path, "init", "-q", "-b", "main", str(lib))
    for n in ("1", "2"):
        (lib / "x.txt").write_text(n + "\n")
        git(lib, "add", ".")
        git(lib, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", n)
    old = git(lib, "rev-parse", "HEAD~1")
    git(checkout, "checkout", "-q", "main")
    git(checkout, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(lib), "libs/lib")
    git(checkout / "libs/lib", "checkout", "-q", old)
    git(checkout, "add", ".")
    git(checkout, "commit", "-qm", "the submodule")
    git(checkout, "push", "-q", "origin", "main")
    git(checkout, "checkout", "-q", "-b", "bump")
    git(checkout / "libs/lib", "checkout", "-q", "main")
    git(checkout, "add", "libs/lib")
    git(checkout, "commit", "-qm", "bump")
    before = counts(capsys)
    assert before.startswith("2 lines in 1 file outside tests")
    for key, value in [("diff.ignoreSubmodules", "all"), ("submodule.libs/lib.ignore", "all")]:
        git(checkout, "config", key, value)
        assert counts(capsys) == before, key
        git(checkout, "config", "--unset", key)


def test_a_replaced_object_doesnt_change_them_or_the_hashes(checkout, capsys):
    # GitHub never reads `git replace`'s refs: both sides diff the objects as committed.
    commit = git(checkout, "rev-parse", "HEAD")
    hashes = own_changes.of_files(own_changes.local_files(checkout, commit, "refs/remotes/origin/main"))
    (checkout.parent / "other.py").write_text("only = 1\n")
    other = git(checkout, "hash-object", "-w", str(checkout.parent / "other.py"))
    git(checkout, "replace", git(checkout, "rev-parse", f"{commit}:src/new.py"), other)
    assert counts(capsys).startswith(COUNTS)
    assert own_changes.of_files(own_changes.local_files(checkout, commit, "refs/remotes/origin/main")) == hashes
