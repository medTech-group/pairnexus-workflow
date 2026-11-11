"""One shared helper decides whether a text matches the profile's
`[sensitive].patterns` (#756): `profile.holds_sensitive`, with
`profile.sensitive_match` naming the first pattern that matches. The guard
and `workflow graph` both call it, rather than each keeping its own
`re.search` loop over the patterns."""

import re
from pathlib import Path

from workflow import graph, guard
from workflow import profile as profile_mod
from workflow.profile import Profile

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts" / "workflow"
MRN = r"\bMRN-\d{6}\b"
NAME = r"(?i)\bpatient name:"


def test_a_text_matching_a_pattern_holds_sensitive_data():
    assert profile_mod.holds_sensitive("seen for MRN-123456 today", [MRN])
    assert profile_mod.holds_sensitive("Patient Name: Ada", [MRN, NAME])


def test_a_text_matching_no_pattern_does_not():
    assert not profile_mod.holds_sensitive("seen for MRN-12345 today", [MRN])
    assert not profile_mod.holds_sensitive("plain words for #12", [MRN, NAME])


def test_no_patterns_means_nothing_is_sensitive():
    assert not profile_mod.holds_sensitive("MRN-123456", [])
    assert profile_mod.sensitive_match("MRN-123456", []) is None


def test_the_match_names_the_first_pattern_that_matches():
    assert profile_mod.sensitive_match("Patient name: Ada, MRN-123456", [MRN, NAME]) == MRN
    assert profile_mod.sensitive_match("Patient name: Ada", [MRN, NAME]) == NAME
    assert profile_mod.sensitive_match("nothing here", [MRN, NAME]) is None


def test_a_match_on_a_later_line_counts():
    # `re.search`, not `re.match`: anywhere in the text, any line.
    assert profile_mod.holds_sensitive("first line\nsecond MRN-654321", [MRN])


def test_the_guard_asks_the_shared_helper(monkeypatch):
    seen = []

    def fake(text, patterns):
        seen.append((text, list(patterns)))
        return True

    monkeypatch.setattr(profile_mod, "holds_sensitive", fake)
    prof = Profile(root=Path("."), name="demo", repo="acme/demo", sensitive_patterns=[MRN])
    assert guard._text_holds_sensitive("some text", prof) is True
    assert seen == [("some text", [MRN])]


def test_graph_asks_the_shared_helper(monkeypatch):
    seen = []

    def fake(text, patterns):
        seen.append((text, list(patterns)))
        return text == "hide me"

    monkeypatch.setattr(profile_mod, "holds_sensitive", fake)
    assert graph._shown("hide me", [MRN]) == graph.SENSITIVE
    assert graph._shown("show me", [MRN]) == "show me"
    assert seen == [("hide me", [MRN]), ("show me", [MRN])]


def test_neither_keeps_its_own_search_loop_over_the_patterns():
    # A `re.search` inside a loop or generator over the sensitive patterns:
    # `for pat in profile.sensitive_patterns: if re.search(pat, ...)`, or
    # `any(re.search(p, s) for p in sensitive)`.
    loop = re.compile(r"re\.search\(\s*(\w+)\s*,[^\n]*\n?[^\n]*\bfor\s+\1\s+in\b|\bfor\s+(\w+)\s+in\s+[\w.]*sensitive[\w.]*:\s*\n\s*if\s+re\.search\(\s*\2\b")
    for name in ("guard.py", "graph.py"):
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        assert not loop.search(text), name
        assert not re.search(r"re\.search\([^)\n]*\)\s+for\s+\w+\s+in\s+[\w.]*sensitive", text), name


def test_the_helper_is_listed_on_its_architecture_page():
    page = (SCRIPTS.parent.parent / "docs" / "architecture" / "scripts--workflow.md").read_text(encoding="utf-8")
    assert "Covers: scripts/workflow/profile.py" in page
    helpers = page.split("\n## Helpers\n", 1)[1].split("\n## ", 1)[0]
    assert re.search(r"^- `holds_sensitive`: in `profile\.py`", helpers, re.M)
