"""`workflow index reads` and `pages` (#612, spec #611 seam 1): through
`cli.main`, on a scratch git repository. Only what the command prints."""

import json
from pathlib import Path

import pytest
from conftest import git

from workflow import cli

ARCH = "docs/architecture"


def _write(root, rel, text=""):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _commit(root, msg="x"):
    git(root, "add", "-A")
    git(root, "commit", "-qm", msg)


def _repo(tmp_path, files=None):
    """A repository on `main` with one commit, then a branch `work`."""
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@e")
    git(tmp_path, "config", "user.name", "t")
    _write(tmp_path, "README.md", "x\n")
    for rel, text in (files or {}).items():
        _write(tmp_path, rel, text)
    _commit(tmp_path)
    git(tmp_path, "checkout", "-qb", "work")
    return tmp_path


def _run(monkeypatch, capsys, root, *args):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    code = cli.main(["index", *args])
    out = capsys.readouterr()
    return code, out.out, out.err


def _reads(monkeypatch, capsys, root, *args):
    code, out, err = _run(monkeypatch, capsys, root, "reads", "--base", "main", *args)
    return code, out.splitlines(), err


def _page(covers, body="Interface: x\n"):
    return "".join(f"Covers: {c}\n" for c in covers) + "\n" + body


# ---------- reads ----------


def test_no_folder_prints_nothing_and_exits_0(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _write(root, "src/a.py")
    _commit(root)
    code, lines, err = _reads(monkeypatch, capsys, root, "--paths", "src/a.py")
    assert (code, lines) == (0, [])


def test_an_empty_folder_prints_nothing(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    (root / ARCH).mkdir(parents=True)
    _write(root, "src/a.py")
    _commit(root)
    assert _reads(monkeypatch, capsys, root)[:2] == (0, [])


def test_the_overview_first_then_matched_pages_sorted(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {
        f"{ARCH}/README.md": "# Overview\n",
        f"{ARCH}/orders.md": _page(["src/orders/**"]),
        f"{ARCH}/billing.md": _page(["src/billing/**"]),
        f"{ARCH}/users.md": _page(["src/users/**"]),
    })
    _write(root, "src/orders/check.py")
    _write(root, "src/billing/pay.py")
    _commit(root)
    code, lines, _ = _reads(monkeypatch, capsys, root)
    assert code == 0
    assert lines == [f"{ARCH}/README.md", f"{ARCH}/billing.md", f"{ARCH}/orders.md"]


def test_the_overview_only_when_it_exists(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {f"{ARCH}/orders.md": _page(["src/orders/**"])})
    _write(root, "src/orders/check.py")
    _commit(root)
    assert _reads(monkeypatch, capsys, root)[1] == [f"{ARCH}/orders.md"]


def test_no_match_prints_only_the_overview(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {f"{ARCH}/README.md": "x\n", f"{ARCH}/orders.md": _page(["src/orders/**"])})
    _write(root, "lib/other.py")
    _commit(root)
    assert _reads(monkeypatch, capsys, root)[1] == [f"{ARCH}/README.md"]


def test_overlapping_pages_each_once(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {
        f"{ARCH}/src.md": _page(["src/**"]),
        f"{ARCH}/orders.md": _page(["src/orders/**"]),
    })
    _write(root, "src/orders/a.py")
    _write(root, "src/orders/b.py")
    _commit(root)
    assert _reads(monkeypatch, capsys, root)[1] == [f"{ARCH}/orders.md", f"{ARCH}/src.md"]


def test_a_page_with_several_covers_lines_is_matched_by_any(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {f"{ARCH}/shared.md": _page(["src/money.py", "lib/**"])})
    _write(root, "lib/deep/x.py")
    _commit(root)
    code, out, _ = _run(monkeypatch, capsys, root, "reads", "--base", "main", "--json")
    assert json.loads(out) == {
        "documents": [f"{ARCH}/shared.md"],
        "pages": [{"file": f"{ARCH}/shared.md", "matched_by": ["lib/**"]}],
    }


def test_star_crosses_slash(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {f"{ARCH}/py.md": _page(["src/*.py"])})
    _write(root, "src/deep/er/x.py")
    _commit(root)
    assert _reads(monkeypatch, capsys, root)[1] == [f"{ARCH}/py.md"]


def test_paths_are_added_and_need_not_exist(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {
        f"{ARCH}/orders.md": _page(["src/orders/**"]),
        f"{ARCH}/billing.md": _page(["src/billing/**"]),
    })
    _write(root, "src/orders/a.py")
    _commit(root)
    code, lines, _ = _reads(monkeypatch, capsys, root, "--paths", "src/billing/new.py", "./README.md")
    assert code == 0
    assert lines == [f"{ARCH}/billing.md", f"{ARCH}/orders.md"]
    assert not (root / "src/billing/new.py").exists()


def test_paths_alone_on_a_branch_with_no_changes(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {f"{ARCH}/billing.md": _page(["src/billing/**"])})
    assert _reads(monkeypatch, capsys, root)[1] == []
    assert _reads(monkeypatch, capsys, root, "--paths", "src/billing/x.py")[1] == [f"{ARCH}/billing.md"]
    assert _reads(monkeypatch, capsys, root, "--paths", "src/billing/x.py", "--paths", "y")[1] == [f"{ARCH}/billing.md"]


@pytest.mark.parametrize("given", ["./src/billing/x.py", "src//billing/x.py", "ROOT/src/billing/x.py"])
def test_paths_are_made_paths_from_the_root(tmp_path, monkeypatch, capsys, given):
    root = _repo(tmp_path, {f"{ARCH}/billing.md": _page(["src/billing/**"])})
    given = given.replace("ROOT", str(root))
    assert _reads(monkeypatch, capsys, root, "--paths", given)[1] == [f"{ARCH}/billing.md"]


def test_a_change_on_the_base_after_the_merge_base_doesnt_count(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {
        f"{ARCH}/orders.md": _page(["src/orders/**"]),
        f"{ARCH}/billing.md": _page(["src/billing/**"]),
    })
    _write(root, "src/orders/a.py")
    _commit(root)
    git(root, "checkout", "-q", "main")
    _write(root, "src/billing/b.py")
    _commit(root, "on the base")
    git(root, "checkout", "-q", "work")
    assert _reads(monkeypatch, capsys, root)[1] == [f"{ARCH}/orders.md"]


def test_a_moved_file_matches_the_pages_of_its_old_and_new_path(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {
        f"{ARCH}/orders.md": _page(["src/orders/**"]),
        f"{ARCH}/billing.md": _page(["src/billing/**"]),
        "src/orders/money.py": "def money():\n    return 1\n" * 20,
    })
    (root / "src/billing").mkdir()
    git(root, "mv", "src/orders/money.py", "src/billing/money.py")
    _commit(root, "move")
    assert _reads(monkeypatch, capsys, root)[1] == [f"{ARCH}/billing.md", f"{ARCH}/orders.md"]


def test_a_path_holding_comma_space_is_matched_by_one_covers_line(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {f"{ARCH}/odd.md": _page(["src/a, b.py"])})
    _write(root, "src/a, b.py")
    _commit(root)
    assert _reads(monkeypatch, capsys, root)[1] == [f"{ARCH}/odd.md"]


def test_brackets_in_a_path_need_bracketing_in_covers(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {
        f"{ARCH}/plain.md": _page(["app/[id].py"]),
        f"{ARCH}/bracketed.md": _page(["app/[[]id].py"]),
    })
    _write(root, "app/[id].py")
    _commit(root)
    assert _reads(monkeypatch, capsys, root)[1] == [f"{ARCH}/bracketed.md"]


@pytest.mark.parametrize("glob, name", [("src/a[*]b.py", "src/a*b.py"), ("src/a[?]b.py", "src/a?b.py")])
def test_a_star_or_question_mark_in_brackets_matches_only_itself(tmp_path, monkeypatch, capsys, glob, name):
    root = _repo(tmp_path, {f"{ARCH}/lit.md": _page([glob])})
    _write(root, "src/axb.py")
    _commit(root)
    assert _reads(monkeypatch, capsys, root)[1] == []
    assert _reads(monkeypatch, capsys, root, "--paths", name)[1] == [f"{ARCH}/lit.md"]


def test_a_page_with_no_covers_is_printed_in_one_sorted_list(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {
        f"{ARCH}/README.md": "x\n",
        f"{ARCH}/earlier-overview.md": "# What we had\n\nSome rules.\n",
        f"{ARCH}/billing.md": _page(["src/billing/**"]),
        f"{ARCH}/zeta.md": _page(["src/zeta/**"]),
    })
    _write(root, "src/zeta/x.py")
    _commit(root)
    code, out, _ = _run(monkeypatch, capsys, root, "reads", "--base", "main")
    assert out.splitlines() == [f"{ARCH}/README.md", f"{ARCH}/earlier-overview.md", f"{ARCH}/zeta.md"]
    code, out, _ = _run(monkeypatch, capsys, root, "reads", "--base", "main", "--json")
    assert json.loads(out) == {
        "documents": [f"{ARCH}/README.md", f"{ARCH}/earlier-overview.md", f"{ARCH}/zeta.md"],
        "pages": [
            {"file": f"{ARCH}/README.md", "matched_by": []},
            {"file": f"{ARCH}/earlier-overview.md", "matched_by": []},
            {"file": f"{ARCH}/zeta.md", "matched_by": ["src/zeta/**"]},
        ],
    }


def test_a_page_with_no_covers_that_sorts_last_is_printed_last(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {
        f"{ARCH}/README.md": "x\n",
        f"{ARCH}/billing.md": _page(["src/billing/**"]),
        f"{ARCH}/zz-old.md": "# What we had\n",
    })
    _write(root, "src/billing/x.py")
    _commit(root)
    want = [f"{ARCH}/README.md", f"{ARCH}/billing.md", f"{ARCH}/zz-old.md"]
    assert _reads(monkeypatch, capsys, root)[1] == want
    code, out, _ = _run(monkeypatch, capsys, root, "reads", "--base", "main", "--json")
    assert json.loads(out) == {
        "documents": want,
        "pages": [
            {"file": f"{ARCH}/README.md", "matched_by": []},
            {"file": f"{ARCH}/billing.md", "matched_by": ["src/billing/**"]},
            {"file": f"{ARCH}/zz-old.md", "matched_by": []},
        ],
    }


def test_subfolders_and_non_md_files_are_never_pages(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {
        f"{ARCH}/old/orders.md": _page(["src/**"]),
        f"{ARCH}/notes.txt": "Covers: src/**\n",
        f"{ARCH}/diagram.png": "",
    })
    _write(root, "src/a.py")
    _commit(root)
    code, out, _ = _run(monkeypatch, capsys, root, "reads", "--base", "main", "--json")
    assert json.loads(out) == {"documents": [], "pages": []}
    code, out, _ = _run(monkeypatch, capsys, root, "pages", "--json")
    assert json.loads(out) == {"pages": []}


@pytest.mark.parametrize("covers, pages", [("src/**", [{"file": f"{ARCH}/README.md", "matched_by": ["src/**"]}]), ("lib/**", [])])
def test_the_overview_is_printed_first_and_once_and_is_a_page_for_now(tmp_path, monkeypatch, capsys, covers, pages):
    root = _repo(tmp_path, {f"{ARCH}/README.md": f"Covers: {covers}\n", f"{ARCH}/a.md": _page(["src/**"])})
    _write(root, "src/a.py")
    _commit(root)
    assert _reads(monkeypatch, capsys, root)[1] == [f"{ARCH}/README.md", f"{ARCH}/a.md"]
    code, out, _ = _run(monkeypatch, capsys, root, "reads", "--base", "main", "--json")
    assert json.loads(out) == {
        "documents": [f"{ARCH}/README.md", f"{ARCH}/a.md"],
        "pages": pages + [{"file": f"{ARCH}/a.md", "matched_by": ["src/**"]}],
    }
    code, out, _ = _run(monkeypatch, capsys, root, "pages", "--json")
    assert [pg["file"] for pg in json.loads(out)["pages"]] == [f"{ARCH}/README.md", f"{ARCH}/a.md"]


def test_a_missing_base_ref_prints_nothing_says_why_and_fails(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {f"{ARCH}/README.md": "x\n"})
    code, out, err = _run(monkeypatch, capsys, root, "reads", "--base", "no-such-branch")
    assert code != 0
    assert out == ""
    assert "no-such-branch" in err


def test_no_merge_base_prints_nothing_says_why_and_fails(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {f"{ARCH}/README.md": "x\n", f"{ARCH}/any.md": "Covers: **\n"})
    git(root, "checkout", "-q", "--orphan", "other")
    _commit(root, "unrelated")
    code, out, err = _run(monkeypatch, capsys, root, "reads", "--base", "main", "--paths", "x.py")
    assert code != 0
    assert out == ""
    assert "merge base" in err


def test_a_page_that_cant_be_read_is_given_out_as_covering_nothing_yet(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {
        f"{ARCH}/README.md": "x\n",
        f"{ARCH}/billing.md": _page(["src/billing/**"]),
        f"{ARCH}/locked.md": _page(["src/locked/**"]),
    })
    _write(root, "lib/x.py")
    _commit(root)
    locked = root / ARCH / "locked.md"
    real = Path.read_text

    def read_text(self, *a, **k):
        if self == locked:
            raise PermissionError(13, "Permission denied", str(self))
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", read_text)
    code, lines, err = _reads(monkeypatch, capsys, root)
    assert (code, lines) == (0, [f"{ARCH}/README.md", f"{ARCH}/locked.md"])
    assert f"{ARCH}/locked.md" in err and "Permission denied" in err
    code, out, err = _run(monkeypatch, capsys, root, "pages")
    assert code == 0
    assert f"{ARCH}/locked.md\n  (covers nothing yet)" in out
    assert f"{ARCH}/locked.md" in err
    code, out, _ = _run(monkeypatch, capsys, root, "pages", "--json")
    assert [pg["covers"] for pg in json.loads(out)["pages"]] == [[], ["src/billing/**"], []]


def test_reads_changes_nothing(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {f"{ARCH}/README.md": "x\n", f"{ARCH}/a.md": _page(["src/**"])})
    _write(root, "src/a.py")
    _commit(root)
    before = git(root, "status", "--porcelain", "--ignored")
    _reads(monkeypatch, capsys, root, "--paths", "src/new.py")
    _run(monkeypatch, capsys, root, "pages", "--json")
    assert git(root, "status", "--porcelain", "--ignored") == before


# ---------- pages ----------

ORDERS = """Covers: src/orders/**
Covers: src/shared/money.py

Interface: `place(order) -> Receipt`; nothing else is imported from outside.

# Orders

Owns placing and checking orders.

## Helpers

- `check_input`: validates an order's fields, with the shared messages.
- `money`: rounds amounts to cents.

## Rules

- Never call billing directly.
"""


def test_pages_lists_file_covers_interface_and_helpers_sorted(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {
        f"{ARCH}/README.md": "x\n",
        f"{ARCH}/orders.md": ORDERS,
        f"{ARCH}/billing.md": "Covers: src/billing/**\n\n# Billing\n",
    })
    code, out, _ = _run(monkeypatch, capsys, root, "pages", "--json")
    assert code == 0
    assert json.loads(out) == {"pages": [
        {"file": f"{ARCH}/README.md", "covers": [], "interface": None, "helpers": []},
        {"file": f"{ARCH}/billing.md", "covers": ["src/billing/**"], "interface": None, "helpers": []},
        {
            "file": f"{ARCH}/orders.md",
            "covers": ["src/orders/**", "src/shared/money.py"],
            "interface": "`place(order) -> Receipt`; nothing else is imported from outside.",
            "helpers": [
                {"name": "check_input", "what": "validates an order's fields, with the shared messages."},
                {"name": "money", "what": "rounds amounts to cents."},
            ],
        },
    ]}
    code, out, _ = _run(monkeypatch, capsys, root, "pages")
    assert code == 0
    assert out.index(f"{ARCH}/billing.md") < out.index(f"{ARCH}/orders.md")
    billing, orders = out.split(f"{ARCH}/orders.md")
    assert "no interface given" in billing
    assert "Covers: src/billing/**" in billing
    for want in ("Covers: src/orders/**", "Covers: src/shared/money.py", "`place(order) -> Receipt`", "check_input", "validates an order's fields", "money", "rounds amounts to cents."):
        assert want in orders
    assert "no interface given" not in orders
    assert out.startswith(f"{ARCH}/README.md\n  (covers nothing yet)\n")


def test_a_page_with_no_covers_is_listed_covers_nothing_yet(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {f"{ARCH}/earlier-overview.md": "# What we had\n\nInterface: old\n"})
    code, out, _ = _run(monkeypatch, capsys, root, "pages")
    assert code == 0
    assert f"{ARCH}/earlier-overview.md" in out
    assert "covers nothing yet" in out
    code, out, _ = _run(monkeypatch, capsys, root, "pages", "--json")
    assert json.loads(out)["pages"][0]["covers"] == []


def test_covers_lines_count_only_at_the_top(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {f"{ARCH}/late.md": "# Late\n\nCovers: src/**\n"})
    code, out, _ = _run(monkeypatch, capsys, root, "pages", "--json")
    assert json.loads(out)["pages"][0]["covers"] == []


def test_backticks_in_a_line_that_starts_with_three_open_no_fence(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {f"{ARCH}/notes.md": (
        "Covers: src/notes/**\n\n"
        "```save``` is the call to use.\n\n"
        "Interface: `save(note)`\n\n"
        "## Helpers\n\n"
        "- `clean`: trims a note's text.\n\n"
        "```markdown\n## Helpers\n\n- `fake`: inside a fence.\n```\n\n"
        "- `after`: still a helper once the fence closes.\n"
    )})
    code, out, _ = _run(monkeypatch, capsys, root, "pages", "--json")
    page = json.loads(out)["pages"][0]
    assert page["interface"] == "`save(note)`"
    assert page["helpers"] == [
        {"name": "clean", "what": "trims a note's text."},
        {"name": "after", "what": "still a helper once the fence closes."},
    ]


def test_pages_with_no_folder(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    code, out, _ = _run(monkeypatch, capsys, root, "pages", "--json")
    assert (code, json.loads(out)) == (0, {"pages": []})
    code, out, _ = _run(monkeypatch, capsys, root, "pages")
    assert code == 0
