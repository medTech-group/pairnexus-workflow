"""`workflow graph cites` for an issue, an ADR and a note (#744, spec #682
seam 1): through `cli.main`, on a scratch git repository whose `origin` is a
local bare repository, with GitHub's issues and pull requests from files or
through `tests/fake_gh.py`. Only what the command prints, text and `--json`."""

import json
from pathlib import Path

import pytest

import fake_gh
from conftest import git

from workflow import cli

pytestmark = pytest.mark.usefixtures("_no_user_git_config")

PROFILE = """
[project]
name = "demo"
repo = "acme/demo"
base_branch = "main"
[sensitive]
patterns = ['\\bMRN-\\d{6}\\b']
"""


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _push(root, files=None, msg="x"):
    for rel, text in (files or {}).items():
        _write(root, rel, text)
    git(root, "add", "-A")
    git(root, "commit", "-qm", msg)
    git(root, "push", "-q", "origin", "HEAD:main")


@pytest.fixture
def root(tmp_path):
    """A checkout of `origin`'s main, with the kit's profile, on a work branch."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(work))
    git(work, "config", "user.email", "t@e")
    git(work, "config", "user.name", "t")
    git(work, "checkout", "-q", "-b", "main")
    _push(work, {".claude/workflow/profile.toml": PROFILE, "README.md": "Demo.\n"}, "base")
    git(work, "checkout", "-q", "-b", "work")
    return work


def _issue(n, body="", labels=(), title="A ticket", state="open", assignees=(), **more):
    return {"number": n, "title": title, "state": state, "body": body,
            "labels": [{"name": l} for l in labels], "assignees": [{"login": a} for a in assignees], **more}


def _pr(n, body="", labels=(), title="A change"):
    return {"number": n, "title": title, "state": "open", "body": body, "labels": [{"name": l} for l in labels]}


def _run(monkeypatch, capsys, root, *args, issues=(), prs=()):
    """`workflow graph cites <args>`, with the issues and pull requests as files."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    fi, fp = root.parent / "issues.json", root.parent / "prs.json"
    fi.write_text(json.dumps(list(issues)))
    fp.write_text(json.dumps(list(prs)))
    code = cli.main(["graph", "cites", *args, "--issues", str(fi), "--prs", str(fp)])
    out = capsys.readouterr()
    return code, out.out, out.err


def _json(monkeypatch, capsys, root, *ids, issues=(), prs=()):
    code, out, err = _run(monkeypatch, capsys, root, *ids, "--json", issues=issues, prs=prs)
    assert code == 0, err
    return json.loads(out)


def _one(monkeypatch, capsys, root, id_, issues=(), prs=()):
    got = _json(monkeypatch, capsys, root, id_, issues=issues, prs=prs)
    assert len(got) == 1
    return got[0]


def _passages(got):
    return [(p["file"], p["line"], p["sentence"]) for p in got["passages"]]


# ---------- the citation forms ----------


def test_an_issue_is_found_by_its_number_and_not_by_a_longer_one_or_a_word(root, monkeypatch, capsys):
    _push(root, {"docs/a.md": "Built for #12 first.\n\nNot #123 here.\n\nNor foo#12 or &#12; there.\n",
                 "src/b.py": "x = 1  # see acme/demo#12.\ny = 2  # other/repo#12.\n"})
    got = _one(monkeypatch, capsys, root, "#12")
    assert _passages(got) == [("docs/a.md", 1, "Built for #12 first."), ("src/b.py", 1, "x = 1 # see acme/demo#12.")]


def test_a_link_to_the_issue_or_pull_request_is_not_a_citation_form(root, monkeypatch, capsys):
    """Spec #682's citation forms are `#n`, built in only: a link isn't one."""
    _push(root, {"docs/a.md": "See https://github.com/acme/demo/issues/12 for it.\n\nAnd https://github.com/acme/demo/pull/12.\n"})
    assert _one(monkeypatch, capsys, root, "#12")["passages"] == []


def test_the_commands_own_answer_id_in_prose_cites_its_issue(root, monkeypatch, capsys):
    _push(root, {"docs/a.md": "It replaces `#682:answer:44` now.\n"})
    assert _passages(_one(monkeypatch, capsys, root, "#682")) == [("docs/a.md", 1, "It replaces `#682:answer:44` now.")]


@pytest.mark.parametrize("text", ["As ADR 0001 says.", "As ADR-0001 says.", "As adr 1 says.", "See [it](../adr/0001-clean-review.md).",
                                  "See docs/adr/0001-clean-review.md."])
def test_each_form_of_an_adr_is_found(root, monkeypatch, capsys, text):
    _push(root, {"docs/a.md": text + "\n"})
    assert _passages(_one(monkeypatch, capsys, root, "ADR:0001")) == [("docs/a.md", 1, text)]


def test_an_adr_is_not_found_by_another_number_or_a_longer_word(root, monkeypatch, capsys):
    _push(root, {"docs/a.md": "ADR 0002 and ADR 00011 and madr/0001 and ADR:0001 and xADR-0001.\n"})
    assert _one(monkeypatch, capsys, root, "ADR:0001")["passages"] == []


def test_an_adr_id_is_compared_by_its_number(root, monkeypatch, capsys):
    _push(root, {"docs/a.md": "As ADR 0007 says.\n"})
    got = _one(monkeypatch, capsys, root, "ADR:7")
    assert got["decision"] == "ADR:0007"
    assert len(got["passages"]) == 1


@pytest.mark.parametrize("text", ["See docs/research/salon-booking/note.md.", "See [the note](../research/salon-booking/note.md).",
                                  "The study in `docs/research/salon-booking/` says so.", "As docs/research/salon-booking says."])
def test_a_research_note_is_found_by_its_path(root, monkeypatch, capsys, text):
    _push(root, {"docs/a.md": text + "\n"})
    got = _one(monkeypatch, capsys, root, "docs/research/salon-booking/note.md")
    assert _passages(got) == [("docs/a.md", 1, text)]
    assert got["decision"] == "docs/research/salon-booking/note.md"


def test_a_notes_path_does_not_find_another_note_or_a_file_in_its_folder(root, monkeypatch, capsys):
    _push(root, {"docs/a.md": "See docs/research/salon-booking-2/note.md and docs/research/salon-booking/sources/x.md.\n"})
    assert _one(monkeypatch, capsys, root, "./docs/research/salon-booking/note.md")["passages"] == []


def test_several_ids_in_one_run_each_get_their_own_object_in_the_order_asked(root, monkeypatch, capsys):
    _push(root, {"docs/a.md": "For #12.\n\nAs ADR 0003 says.\n"})
    got = _json(monkeypatch, capsys, root, "ADR:0003", "#12", "#99")
    assert [g["decision"] for g in got] == ["ADR:0003", "#12", "#99"]
    assert [g["counts"]["passages"] for g in got] == [1, 1, 0]


@pytest.mark.parametrize("bad", ["#682:answer:3", "12", "ADR:x", "#0", ""])
def test_an_id_it_cant_read_is_refused(root, monkeypatch, capsys, bad):
    code, out, err = _run(monkeypatch, capsys, root, bad)
    assert code == 2
    assert out == ""
    assert "workflow graph cites:" in err


# ---------- the citing sentence ----------


SENTENCES = """# A heading for #12

Some prose before. The rule for #12 is
wrapped over two lines. After it.

- a list item for #12
- another item
| a | table row for #12 |
| b | c |
He said "about #12." Then more.
It is (as in #12.) Then more.
It is **bold for #12.** Then more.
Is it #12? Then more. Wow #12! Then more.
For e.g. #12 and i.e. this, and ans. 3 too. Then more.
A paragraph for #12

Ends at the blank line.
"""


def test_each_citing_sentence_and_where_it_ends(root, monkeypatch, capsys):
    _push(root, {"docs/a.md": SENTENCES})
    assert _passages(_one(monkeypatch, capsys, root, "#12")) == [
        ("docs/a.md", 1, "A heading for #12"),
        ("docs/a.md", 3, "The rule for #12 is wrapped over two lines."),
        ("docs/a.md", 6, "a list item for #12"),
        ("docs/a.md", 8, "| a | table row for #12 |"),
        ("docs/a.md", 10, 'He said "about #12."'),
        ("docs/a.md", 11, "It is (as in #12.)"),
        ("docs/a.md", 12, "It is **bold for #12.**"),
        ("docs/a.md", 13, "Is it #12?"),
        ("docs/a.md", 13, "Wow #12!"),
        ("docs/a.md", 14, "For e.g. #12 and i.e. this, and ans. 3 too."),
        ("docs/a.md", 15, "A paragraph for #12"),
    ]


def test_a_sentence_over_several_lines_is_given_at_the_citations_line(root, monkeypatch, capsys):
    _push(root, {"docs/a.md": "This sentence starts here and\nruns on until it names #12 at\nlast.\n"})
    assert _passages(_one(monkeypatch, capsys, root, "#12")) == [("docs/a.md", 2, "This sentence starts here and runs on until it names #12 at last.")]


def test_several_citations_in_one_sentence_are_one_passage(root, monkeypatch, capsys):
    _push(root, {"docs/a.md": "Both #12 and\nagain #12 here.\n"})
    assert _passages(_one(monkeypatch, capsys, root, "#12")) == [("docs/a.md", 1, "Both #12 and again #12 here.")]


def test_a_quoted_line_is_read_without_its_quote_marks(root, monkeypatch, capsys):
    _push(root, {"docs/a.md": "> Quoted for #12,\n> over two lines.\n"})
    assert _passages(_one(monkeypatch, capsys, root, "#12")) == [("docs/a.md", 1, "Quoted for #12, over two lines.")]


# ---------- what is left out ----------


def test_the_vendored_kit_is_left_out_by_its_lock(root, monkeypatch, capsys):
    lock = {"files": {".claude/skills/x/SKILL.md": "h"}, "orphaned": {".claude/old.md": "h"},
            "conflicts": {".claude/conflicted.md": "h"}}
    _push(root, {".claude/workflow/lock.json": json.dumps(lock), ".claude/skills/x/SKILL.md": "For #12.\n",
                 ".claude/old.md": "For #12.\n", ".claude/conflicted.md.new": "For #12.\n", ".claude/conflicted.md": "For #12.\n",
                 ".claude/own.md": "For #12.\n"})
    assert [p["file"] for p in _one(monkeypatch, capsys, root, "#12")["passages"]] == [".claude/conflicted.md", ".claude/own.md"]


def test_without_a_lock_nothing_is_left_out_as_vendored(root, monkeypatch, capsys):
    _push(root, {".claude/skills/x/SKILL.md": "For #12.\n"})
    assert [p["file"] for p in _one(monkeypatch, capsys, root, "#12")["passages"]] == [".claude/skills/x/SKILL.md"]


def test_research_notes_saved_copies_and_fingerprint_files_are_left_out(root, monkeypatch, capsys):
    _push(root, {
        "docs/research/salon-booking/note.md": "Status: current\nLast checked: 2026-11-01\nIssue: #5\n\n# Salons\n\nFor #12.\n",
        "docs/research/salon-booking/sources/page.md": "Source: https://example.com/a\nAccessed: 2026-11-01\nThird-party text: theirs.\n\nAbout #12.\n",
        "docs/research/salon-booking/sources/page.fingerprints": "url: https://example.com/#12\n1 " + "a" * 64 + "\n",
        "docs/research/salon-booking/sources/odd": "URL: https://example.com/a #12\n",
        "docs/research/salon-booking/questions.md": "Asked for #12.\n",
        "docs/elsewhere.md": "url: https://example.com/ #12\n",
    })
    assert [p["file"] for p in _one(monkeypatch, capsys, root, "#12")["passages"]] == [
        "docs/elsewhere.md", "docs/research/salon-booking/note.md", "docs/research/salon-booking/questions.md"]


def test_a_colour_in_a_style_file_is_not_an_issue(root, monkeypatch, capsys):
    _push(root, {"web/a.css": "a { color: #123; }\nb { color: #123456; }\nc { color: #12345678; }\n/* see #1234 */\n",
                 "web/b.scss": "$x: #123;\n", "docs/a.md": "Issue #123.\n"})
    assert [(p["file"], p["line"]) for p in _one(monkeypatch, capsys, root, "#123")["passages"]] == [("docs/a.md", 1)]
    assert [(p["file"], p["line"]) for p in _one(monkeypatch, capsys, root, "#1234")["passages"]] == [("web/a.css", 4)]
    assert [(p["file"], p["line"]) for p in _one(monkeypatch, capsys, root, "#12345678")["passages"]] == []


def test_binary_files_are_left_out(root, monkeypatch, capsys):
    (root / "img.bin").write_bytes(b"\x00\x01 #12 \x00")
    _push(root, {"docs/a.md": "For #12.\n"})
    assert [p["file"] for p in _one(monkeypatch, capsys, root, "#12")["passages"]] == ["docs/a.md"]


def test_it_reads_the_base_branch_at_origin_not_the_working_tree(root, monkeypatch, capsys):
    _push(root, {"docs/a.md": "For #12.\n"})
    _write(root, "docs/b.md", "Also #12.\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "not pushed")
    assert [p["file"] for p in _one(monkeypatch, capsys, root, "#12")["passages"]] == ["docs/a.md"]


def test_it_fetches_the_base_branch_first(root, monkeypatch, capsys, tmp_path):
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", "-b", "main", str(tmp_path / "origin.git"), str(other))
    git(other, "config", "user.email", "t@e")
    git(other, "config", "user.name", "t")
    _push(other, {"docs/new.md": "Pushed elsewhere for #12.\n"})
    assert [p["file"] for p in _one(monkeypatch, capsys, root, "#12")["passages"]] == ["docs/new.md"]


# ---------- open issues and open pull requests ----------


def test_open_issues_and_open_pull_requests_citing_it_with_their_sentence(root, monkeypatch, capsys):
    issues = [_issue(20, "Some words.\n\nThis builds on #12 now.\n"), _issue(21, "Nothing here."),
              _issue(22, "Closed one cites #12.", state="closed"),
              _issue(30, "A pull request listed as an issue cites #12.", pull_request={"url": "x"})]
    prs = [_pr(30, "Closes #20. It reads #12 too.")]
    got = _one(monkeypatch, capsys, root, "#12", issues=issues, prs=prs)
    assert [(i["number"], i["sentence"]) for i in got["issues"]] == [(20, "This builds on #12 now."), (30, "It reads #12 too.")]
    assert got["counts"]["issues"] == 2


def test_an_issue_citing_it_in_two_sentences_is_listed_for_each_and_counted_once(root, monkeypatch, capsys):
    got = _one(monkeypatch, capsys, root, "#12", issues=[_issue(20, "First #12.\n\nThen #12 again.")])
    assert [i["sentence"] for i in got["issues"]] == ["First #12.", "Then #12 again."]
    assert got["counts"]["issues"] == 1


REPLACES = """Builds the new reading.

## Replaces

- `#12`
- ADR:0001

## Notes

Read #12 before building, and ADR 0001.
"""


def test_a_citation_inside_its_own_replaces_is_not_listed_and_one_elsewhere_is(root, monkeypatch, capsys):
    issues = [_issue(20, REPLACES), _issue(21, "## Replaces\n\n- #12\n")]
    got = _one(monkeypatch, capsys, root, "#12", issues=issues)
    assert [(i["number"], i["sentence"]) for i in got["issues"]] == [(20, "Read #12 before building, and ADR 0001.")]
    assert [i["number"] for i in _one(monkeypatch, capsys, root, "ADR:0001", issues=issues)["issues"]] == [20]


@pytest.mark.parametrize("body", [
    "Words.\n\n```\n## Replaces\n\n- #12\n```\n",
    "Words.\n\n> ## Replaces\n>\n> - #12\n",
])
def test_a_replaces_heading_in_a_fenced_block_or_a_quote_is_not_the_bodys_own(root, monkeypatch, capsys, body):
    got = _one(monkeypatch, capsys, root, "#12", issues=[_issue(20, body)])
    assert [i["number"] for i in got["issues"]] == [20]


def test_a_replaces_section_ends_at_the_next_heading_of_any_level(root, monkeypatch, capsys):
    body = "### Replaces\n\n- #12\n\n#### Why\n\nSee #12.\n"
    got = _one(monkeypatch, capsys, root, "#12", issues=[_issue(20, body)])
    assert [i["sentence"] for i in got["issues"]] == ["See #12."]


def test_replaces_only_matters_in_an_issues_body_not_in_a_file(root, monkeypatch, capsys):
    _push(root, {"docs/a.md": "## Replaces\n\n- #12\n"})
    assert len(_one(monkeypatch, capsys, root, "#12")["passages"]) == 1


# ---------- kind and claimed ----------


def _kinds(got):
    return {i["number"]: i["kind"] for i in got["issues"]}


def test_each_kind_in_the_specs_order(root, monkeypatch, capsys):
    run_body = "Tracking.\n\n<!-- workflow-state:begin -->\n```json\n" + json.dumps({"by_hand_issue": 28}) + "\n```\n<!-- workflow-state:end -->\n"
    issues = [
        _issue(20, "A ticket for #12."),
        _issue(21, "A spec for #12.", labels=["spec"]),
        _issue(22, "A spec by its title for #12.", title="Spec: things"),
        _issue(23, "A decision for #12.", labels=["wayfinder:research"]),
        _issue(24, "A map for #12.", labels=["wayfinder:map"]),
        _issue(25, "A run for #12.", labels=["workflow:run"]),
        _issue(26, "Closed run.\n\n<!-- workflow-state:begin -->\n```json\n" + json.dumps({"by_hand_issue": 27}) + "\n```\n<!-- workflow-state:end -->\n",
               labels=["workflow:run"], state="closed"),
        _issue(27, "A closed run's by-hand issue for #12."),
        _issue(28, "An open run's by-hand issue for #12."),
        _issue(29, "Its run.\n\n" + run_body.split("\n\n", 1)[1], labels=["workflow:run"]),
        _issue(31, "An owner task for #12.", labels=["owner-task"]),
        _issue(32, "For the human, #12.", labels=["ready-for-human"]),
        _issue(33, "Research for #12.", labels=["research"]),
        _issue(34, "An item for #12.\n<!-- workflow:item path=spec -->"),
        _issue(35, "A parent of sub-issues for #12.", sub_issues_summary={"total": 2}),
        _issue(36, "A spec that is also a decision, #12.", labels=["spec", "wayfinder:task"]),
        _issue(37, "A decision ticket that is also a run, #12.", labels=["wayfinder:prototype", "workflow:run"]),
    ]
    got = _one(monkeypatch, capsys, root, "#12", issues=issues, prs=[_pr(40, "A pull request for #12.", labels=["spec"])])
    assert _kinds(got) == {20: "ticket", 21: "spec", 22: "spec", 23: "decision", 24: "other", 25: "run", 27: "run", 28: "run",
                           31: "other", 32: "other", 33: "other", 34: "other", 35: "other", 36: "spec", 37: "decision", 40: "pull_request"}


def _claimed(got):
    return {i["number"]: i["claimed"] for i in got["issues"]}


def test_claimed_by_the_label_by_a_decision_tickets_assignee_or_an_open_pull_request_closing_it(root, monkeypatch, capsys):
    issues = [
        _issue(20, "Ticket for #12.", labels=["workflow:in-progress"]),
        _issue(21, "Ticket for #12.", assignees=["dev"]),
        _issue(22, "Decision for #12.", labels=["wayfinder:grilling"], assignees=["owner"]),
        _issue(23, "Decision for #12.", labels=["wayfinder:grilling"]),
        _issue(24, "Owner task for #12.", labels=["owner-task"]),
        _issue(25, "Spec for #12.", labels=["spec"]),
        _issue(26, "Ticket for #12."),
    ]
    prs = [_pr(40, "Fixes #24 and closes #25. About #12."), _pr(41, "Closes #40. About #12."),
           _pr(42, "About #12.", labels=["workflow:in-progress"])]
    got = _one(monkeypatch, capsys, root, "#12", issues=issues, prs=prs)
    assert _claimed(got) == {20: True, 21: False, 22: True, 23: False, 24: True, 25: True, 26: False, 40: False, 41: False, 42: True}


def test_a_closed_pull_request_closes_nothing(root, monkeypatch, capsys):
    prs = [_pr(40, "About #12."), {**_pr(41, "Closes #20."), "state": "closed"}]
    got = _one(monkeypatch, capsys, root, "#12", issues=[_issue(20, "Ticket for #12.")], prs=prs)
    assert _claimed(got)[20] is False


# ---------- a run whose state can't be read ----------


def test_a_run_whose_state_cant_be_read_is_named_and_the_command_goes_on(root, monkeypatch, capsys):
    _push(root, {"docs/a.md": "For #12.\n"})
    issues = [
        _issue(25, "Two blocks.\n<!-- workflow-state:begin -->\n<!-- workflow-state:begin -->\n", labels=["workflow:run"]),
        _issue(26, "No state yet.", labels=["workflow:run"], state="closed"),
        _issue(20, "A ticket for #12."),
    ]
    code, out, err = _run(monkeypatch, capsys, root, "#12", issues=issues)
    assert code == 0
    assert "docs/a.md" in out and "#20" in out
    assert "run #25: its state can't be read" in out
    assert "run #26: its state isn't written yet" in out
    assert out.count("by-hand issue isn't told apart") == 2
    code, out, err = _run(monkeypatch, capsys, root, "#12", "--json", issues=issues)
    assert code == 0
    assert len(json.loads(out)[0]["passages"]) == 1
    assert "run #25: its state can't be read" in err and "run #26" in err


# ---------- sensitive sentences ----------


def test_a_sensitive_sentence_is_left_out_keeping_its_place(root, monkeypatch, capsys):
    _push(root, {"docs/a.md": "Patient MRN-123456 needs #12. Plain words for #12.\n"})
    issues = [_issue(20, "Patient MRN-654321 and #12.")]
    got = _one(monkeypatch, capsys, root, "#12", issues=issues)
    assert _passages(got) == [("docs/a.md", 1, "[left out: sensitive]"), ("docs/a.md", 1, "Plain words for #12.")]
    assert got["issues"][0]["sentence"] == "[left out: sensitive]"
    code, out, err = _run(monkeypatch, capsys, root, "#12", issues=issues)
    assert "MRN-" not in out
    assert out.count("[left out: sensitive]") == 2


# ---------- counts and output ----------


def test_counts_first_and_files_counts_distinct_passage_files(root, monkeypatch, capsys):
    _push(root, {"docs/a.md": "One #12.\n\nTwo #12.\n", "docs/b.md": "Three #12.\n"})
    got = _one(monkeypatch, capsys, root, "#12", issues=[_issue(20, "For #12."), _issue(21, "For #12.")])
    assert list(got) == ["decision", "counts", "passages", "issues", "built_by", "changed_by"]
    assert got["counts"] == {"passages": 3, "files": 2, "issues": 2, "built_by": 0, "spec_unsure": 0}
    assert got["passages"][0] == {"file": "docs/a.md", "line": 1, "sentence": "One #12.", "spec_unsure": False}
    assert got["issues"][0] == {"number": 20, "kind": "ticket", "claimed": False, "sentence": "For #12.", "spec_unsure": False}
    assert got["built_by"] == [] and got["changed_by"] == []


def test_the_text_output_gives_counts_first_then_passages_grouped_by_file_then_issues(root, monkeypatch, capsys):
    _push(root, {"docs/b.md": "Three #12.\n", "docs/a.md": "One #12.\n\nTwo #12.\n"})
    code, out, err = _run(monkeypatch, capsys, root, "#12", "ADR:0001",
                          issues=[_issue(20, "For #12.", labels=["workflow:in-progress"])], prs=[_pr(30, "About #12.")])
    assert code == 0
    assert out.splitlines() == [
        "#12: 3 passages in 2 files, 2 open issues",
        "  docs/a.md",
        "    1: One #12.",
        "    3: Two #12.",
        "  docs/b.md",
        "    1: Three #12.",
        "  open issues:",
        "    #20 (ticket, claimed): For #12.",
        "    #30 (pull_request): About #12.",
        "",
        "ADR:0001: 0 passages in 0 files, 0 open issues",
    ]


# ---------- GitHub's inputs ----------


def test_it_needs_the_issues_and_pull_requests(root, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    assert cli.main(["graph", "cites", "#12"]) == 2
    assert "--issues" in capsys.readouterr().err
    f = root.parent / "i.json"
    f.write_text("[]")
    assert cli.main(["graph", "cites", "#12", "--issues", str(f), "--fetch"]) == 2
    assert "not both" in capsys.readouterr().err


def test_issues_given_as_pages_are_read(root, monkeypatch, capsys):
    got = _one(monkeypatch, capsys, root, "#12", issues=[[_issue(20, "For #12.")], [_issue(21, "For #12.")]])
    assert [i["number"] for i in got["issues"]] == [20, 21]


def test_fetch_reads_issues_and_pull_requests_by_page(root, monkeypatch, capsys, tmp_path):
    full = [_issue(100 + i, "Nothing.") for i in range(100)]
    gh = fake_gh.install(tmp_path, monkeypatch, {
        "repos/acme/demo/issues": fake_gh.pages(full, [_issue(20, "For #12.")], numeric_refused=True),
        "repos/acme/demo/pulls": fake_gh.pages([_pr(30, "About #12.")], numeric_refused=True),
    })
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    assert cli.main(["graph", "cites", "#12", "--fetch", "--json"]) == 0
    got = json.loads(capsys.readouterr().out)[0]
    assert [i["number"] for i in got["issues"]] == [20, 30]
    paths = gh.paths()
    assert "repos/acme/demo/issues?state=all&per_page=100&page=2" in paths


def test_fetch_that_fails_says_so(root, monkeypatch, capsys, tmp_path):
    fake_gh.install(tmp_path, monkeypatch, {})
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    assert cli.main(["graph", "cites", "#12", "--fetch"]) == 1
    err = capsys.readouterr().err
    assert "workflow graph cites:" in err and "--issues" in err


def test_without_a_profile_it_says_so(tmp_path, monkeypatch, capsys):
    git(tmp_path, "init", "-q", "-b", "main")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    f = tmp_path / "x.json"
    f.write_text("[]")
    assert cli.main(["graph", "cites", "#12", "--issues", str(f), "--prs", str(f)]) == 1
    assert "profile" in capsys.readouterr().err


def test_without_origin_base_it_says_so(root, monkeypatch, capsys):
    git(root, "remote", "remove", "origin")
    code, out, err = _run(monkeypatch, capsys, root, "#12")
    assert code == 1
    assert "origin/main" in err


# ---------- the shared helpers (the overview's "Reuse, not copies") ----------


def test_it_uses_the_shared_issue_helpers_not_copies_of_them():
    """The pages' flattening is `cli._fetch_items`, an issue's number
    `doctor._number`, open `status._open`, the plural `presets.plural` and the
    repository's comparison `issues._same_repo`: graph.py has no copy of them."""
    import inspect

    from workflow import graph

    src = inspect.getsource(graph)
    for copy in ("def _items(", "def _number(", "def _open(", "def _plural(", "other.casefold() == repo.casefold()"):
        assert copy not in src, copy
    assert "_fetch_items(" in inspect.getsource(cli.cmd_graph)


def test_it_uses_the_shared_constants_not_copies_of_them():
    """The lock's path is `vendor.LOCK`, the run's label `estimate.RUN_LABEL`,
    the owner task's labels `issues.OWNER_TASK_LABELS` and the fence
    `issues._FENCE`: graph.py spells none of them out."""
    import inspect

    from workflow import estimate, graph, issues, vendor

    src = inspect.getsource(graph)
    for copy in ('".claude/workflow/lock.json"', '"workflow:run"', '"owner-task"', '"ready-for-human"', "_FENCE = "):
        assert copy not in src, copy
    assert graph.LOCK == vendor.LOCK.as_posix() and graph.RUN_LABEL == estimate.RUN_LABEL
    assert graph.NOT_TICKET_LABELS == issues.OWNER_TASK_LABELS | {issues.RESEARCH_LABEL}


def test_one_spec_test_shared_by_the_graph_status_and_build_tickets():
    """`issues.is_spec` is the one spec test (the `spec` label or a "Spec:"
    title), listed on its page; the graph's kind, `status` and
    `is_build_ticket` use it, with no copy of the title test."""
    import inspect

    from workflow import graph, issues, status

    assert issues.is_spec({"labels": [{"name": "Spec"}]}) and issues.is_spec({"title": "  spec: booking"})
    assert not issues.is_spec({"title": "A spec for booking", "labels": ["wayfinder:map"]})
    for module in (graph, status):
        assert '"spec:"' not in inspect.getsource(module), module
    assert inspect.getsource(issues).count('startswith("spec:")') == 1
    assert "is_spec(" in inspect.getsource(issues.is_build_ticket) and "is_spec(" in inspect.getsource(graph.kind_of)
    page = (Path(__file__).resolve().parents[1] / "docs/architecture/scripts--workflow.md").read_text()
    assert "Covers: scripts/workflow/issues.py\n" in page and "\n- `is_spec`: in `issues.py`" in page
