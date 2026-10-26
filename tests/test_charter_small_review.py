"""#259: runs and the small review (#255's seam 3). The charter's `review.small`,
`review.passes` and threshold, the presets' `small`, `charter reuse`, the
limits question's words and the one page, and the ticket session's briefing,
through `workflow charter` and `workflow render`, as
`test_charter_presets.py` and `test_briefing_review.py` drive them."""

import json
import os
import subprocess
import sys

import pytest

from changelog_notes import since_0110
from conftest import KIT

CLI = KIT / "scripts/workflow.py"
TEMPLATE = KIT / "templates/ticket-session-prompt.md"
SLOTS = {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "none", "wake_trigger": "trig_01abc"}


def _cli(tmp_path, *args):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, cwd=tmp_path, env=env)


def _project(tmp_path, run="", explorer="cli"):
    (tmp_path / ".claude/workflow").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "o"\n'
        '[ci]\nrequired_checks = ["CI"]\n'
        f'[ui]\nexplorer = "{explorer}"\n'
        f"[run]\n{run}"
    )
    (tmp_path / "ticket.json").write_text(json.dumps({"number": 7, "title": "Notes list order"}))
    (tmp_path / "slots.json").write_text(json.dumps(SLOTS))


def _file(tmp_path, c, name="c.json"):
    (tmp_path / name).write_text(json.dumps(c))
    return name


def _defaults(tmp_path):
    p = _cli(tmp_path, "charter", "defaults")
    assert p.returncode == 0, p.stderr
    c = json.loads(p.stdout)
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    return c


def _preset(tmp_path, name):
    """A charter written from preset `name`, as the conductor writes one."""
    c = _defaults(tmp_path)
    ps = _limits_q(tmp_path)["presets"][name]
    c["preset"] = name
    c["limits"].update(ps["limits"])
    c["review"] = dict(ps["review"])
    return c


def _limits_q(tmp_path):
    p = _cli(tmp_path, "charter", "questions")
    assert p.returncode == 0, p.stderr
    return next(q for q in json.loads(p.stdout) if q["key"] == "limits")


def _validate(tmp_path, c):
    return _cli(tmp_path, "charter", "validate", _file(tmp_path, c))


def _page(tmp_path, c):
    p = _cli(tmp_path, "charter", "markdown", _file(tmp_path, c))
    assert p.returncode == 0, p.stderr
    return p.stdout


def _line(text, start):
    return next(l for l in text.splitlines() if l.startswith(start))


def _brief(tmp_path, c):
    c["approved"] = {"by": "o", "at": "2026-10-12T11:55:00Z", "source": "chat"}
    _file(tmp_path, c, "charter.json")
    p = _cli(
        tmp_path, "render", "--template", str(TEMPLATE), "--ticket", "ticket.json", "--charter", "charter.json",
        "--slots", "slots.json", "--tracking", "11", "--out", "briefing.md",
    )
    assert p.returncode == 0, p.stderr
    v = _cli(tmp_path, "briefing", "verify", "--file", "briefing.md")
    assert v.returncode == 0 and v.stdout.endswith(" intact\n"), v.stdout
    return (tmp_path / "briefing.md").read_text()


def _merge_check(text):
    return _line(text, "- Right before each of these (merging, arming auto-merge, queueing, saying it's ready)")


# ---------- the presets' small ----------


def test_light_and_normal_turn_the_small_review_on_and_thorough_off(tmp_path):
    _project(tmp_path)
    ps = _limits_q(tmp_path)["presets"]
    assert {n: p["review"]["small"] for n, p in ps.items()} == {"light": True, "normal": True, "thorough": False}


@pytest.mark.parametrize("name", ["light", "normal", "thorough"])
def test_a_charter_from_a_preset_carries_small_explicitly(tmp_path, name):
    _project(tmp_path, f'preset = "{name}"\n')
    c = _defaults(tmp_path)
    assert c["preset"] == name and c["review"]["small"] is (name != "thorough")
    assert _validate(tmp_path, c).returncode == 0


@pytest.mark.parametrize("name", ["light", "normal", "thorough"])
def test_passes_and_the_threshold_are_the_profiles_in_every_preset(tmp_path, name):
    _project(tmp_path, "review_passes = 3\nsmall_max_lines = 80\nsmall_max_files = 5\n")
    p = _limits_q(tmp_path)["presets"][name]
    # The charter carries none of them: a run reads the profile's.
    assert not {"passes", "small_max_lines", "small_max_files"} & set(p["review"])
    assert "at most 3 Correctness passes" in p["words"]
    brief = _brief(tmp_path, _preset(tmp_path, name))
    assert "--review-passes 3 --small-max-lines 80 --small-max-files 5`" in _merge_check(brief)


# ---------- an old charter reads as off ----------


def test_an_old_charter_with_a_review_object_reads_as_off(tmp_path):
    _project(tmp_path)
    c = _defaults(tmp_path)
    c["review"] = {"rounds": 3, "explorer": True}
    assert _validate(tmp_path, c).returncode == 0
    assert _line(_page(tmp_path, c), "- **Small review:**").startswith("- **Small review:** off")
    assert _line(_brief(tmp_path, c), "- **Small review:**").startswith("- **Small review:** off")


@pytest.mark.parametrize("preset", [None, "normal", "light"])
def test_an_old_charter_without_a_review_object_reads_as_off(tmp_path, preset):
    _project(tmp_path)
    c = _defaults(tmp_path)
    del c["review"]
    if preset is None:
        del c["preset"]
    else:
        c["preset"] = preset
    assert _validate(tmp_path, c).returncode == 0
    assert _line(_page(tmp_path, c), "- **Small review:**").startswith("- **Small review:** off")
    assert _line(_brief(tmp_path, c), "- **Small review:**").startswith("- **Small review:** off")


# ---------- a new run from an old charter ----------


@pytest.mark.parametrize("preset, review, want", [
    ("normal", {"rounds": 3, "explorer": True}, True),
    ("light", {"rounds": 1, "explorer": False}, True),
    ("thorough", {"rounds": 3, "explorer": True}, False),
    ("thorough", None, False),
    ("light", None, True),
    (None, None, True),  # a charter from before presets reads as Normal
])
def test_reuse_fills_small_from_the_preset_and_diff_shows_it(tmp_path, preset, review, want):
    _project(tmp_path, "review_rounds = 2\n")
    old = _defaults(tmp_path)
    old.pop("preset")
    old.pop("review")
    if preset:
        old["preset"] = preset
    if review:
        old["review"] = review
    p = _cli(tmp_path, "charter", "reuse", _file(tmp_path, old, "old.json"))
    assert p.returncode == 0, p.stderr
    new = json.loads(p.stdout)
    assert new["review"]["small"] is want
    # What the review was, it stays: only small is new.
    if review:
        assert {k: new["review"][k] for k in review} == review
    else:
        assert new["review"]["rounds"] == {"light": 1, "thorough": 3}.get(preset, 2)
        assert new["review"]["explorer"] is (preset != "light")
    _file(tmp_path, new, "new.json")
    lines = _cli(tmp_path, "charter", "diff", "old.json", "new.json").stdout.splitlines()
    assert any(l.startswith("review: ") and f'"small": {json.dumps(want)}' in l for l in lines), lines


def test_reuse_without_a_profile_says_the_review_is_the_defaults(tmp_path):
    old = json.loads(_cli(tmp_path, "charter", "defaults").stdout)
    del old["review"]
    p = _cli(tmp_path, "charter", "reuse", _file(tmp_path, old))
    assert p.returncode == 0 and "no profile could be read" in p.stderr, p.stderr
    assert json.loads(p.stdout)["review"] == {"rounds": 3, "explorer": False, "small": True}
    # Light's review doesn't depend on the profile: nothing to say.
    old["preset"] = "light"
    p = _cli(tmp_path, "charter", "reuse", _file(tmp_path, old))
    assert p.returncode == 0 and p.stderr == "", p.stderr
    assert json.loads(p.stdout)["review"] == {"rounds": 1, "explorer": False, "small": True}
    del old["preset"]
    # With a review to keep, nothing is taken from the defaults, and nothing is said.
    old["review"] = {"rounds": 2, "explorer": True}
    p = _cli(tmp_path, "charter", "reuse", _file(tmp_path, old))
    assert p.returncode == 0 and p.stderr == "" and json.loads(p.stdout)["review"]["explorer"] is True


def test_reuse_keeps_a_small_the_owner_chose(tmp_path):
    _project(tmp_path)
    old = _defaults(tmp_path)
    old["review"]["small"] = False
    new = json.loads(_cli(tmp_path, "charter", "reuse", _file(tmp_path, old)).stdout)
    assert new["review"]["small"] is False


# ---------- the profile's values, the charter's, and refusals ----------


def test_missing_passes_and_threshold_read_as_the_profiles(tmp_path):
    _project(tmp_path, "review_passes = 4\nsmall_max_lines = 30\nsmall_max_files = 2\n")
    brief = _brief(tmp_path, _defaults(tmp_path))
    assert "--review-rounds 3 --review-passes 4 --small-max-lines 30 --small-max-files 2`" in _merge_check(brief)
    assert "30 lines in 2 files outside tests" in _line(brief, "- **Small review:**")
    assert "at most 4 Correctness passes" in _line(brief, "- **Pass cap:**")


def test_the_charters_passes_and_threshold_win(tmp_path):
    _project(tmp_path, "review_passes = 4\n")
    c = _defaults(tmp_path)
    c["review"].update(passes=0, small_max_lines=1000, small_max_files=50)
    assert _validate(tmp_path, c).returncode == 0
    brief = _brief(tmp_path, c)
    assert "--review-passes 0 --small-max-lines 1000 --small-max-files 50`" in _merge_check(brief)
    assert "1000 lines in 50 files outside tests" in _line(brief, "- **Small review:**")
    assert _line(brief, "- **Pass cap:**").startswith("- **Pass cap:** no Correctness passes after the last review round")


def test_without_a_profile_the_defaults_are_the_profiles_defaults(tmp_path):
    c = json.loads(_cli(tmp_path, "charter", "defaults").stdout)
    assert c["review"]["small"] is True and "passes" not in c["review"]
    q = next(q for q in json.loads(_cli(tmp_path, "charter", "questions").stdout) if q["key"] == "limits")
    assert "at most 2 Correctness passes" in q["presets"]["normal"]["words"]
    assert "60 lines in 4 files" in q["presets"]["normal"]["words"]


@pytest.mark.parametrize("change, needle", [
    ({"small": "yes"}, "review.small must be true or false"),
    ({"small": 1}, "review.small must be true or false"),
    ({"passes": -1}, "review.passes must be a whole number from 0 to 10"),
    ({"passes": 11}, "review.passes must be a whole number from 0 to 10"),
    ({"passes": True}, "review.passes must be a whole number from 0 to 10"),
    ({"passes": "2"}, "review.passes must be a whole number from 0 to 10"),
    ({"small_max_lines": 0}, "review.small_max_lines must be a whole number from 1 to 1000"),
    ({"small_max_lines": 1001}, "review.small_max_lines must be a whole number from 1 to 1000"),
    ({"small_max_files": 0}, "review.small_max_files must be a whole number from 1 to 50"),
    ({"small_max_files": 51}, "review.small_max_files must be a whole number from 1 to 50"),
    ({"small_max_files": 4.0}, "review.small_max_files must be a whole number from 1 to 50"),
])
def test_out_of_range_values_are_refused(tmp_path, change, needle):
    _project(tmp_path)
    c = _defaults(tmp_path)
    c["review"].update(change)
    p = _validate(tmp_path, c)
    assert p.returncode == 1 and needle in p.stderr, p.stderr


@pytest.mark.parametrize("key, value", [("passes", 0), ("passes", 10), ("small_max_lines", 1), ("small_max_lines", 1000),
                                        ("small_max_files", 1), ("small_max_files", 50), ("small", False)])
def test_values_at_the_bounds_are_accepted(tmp_path, key, value):
    _project(tmp_path)
    c = _defaults(tmp_path)
    c["review"][key] = value
    assert _validate(tmp_path, c).returncode == 0


# ---------- the limits question and the one page ----------


def test_the_limits_question_asks_the_small_review_and_the_pass_cap(tmp_path):
    _project(tmp_path)
    q = _limits_q(tmp_path)
    assert "the small review" in q["ask"] and "pass cap" in q["ask"]
    for key in ("review.passes", "review.small_max_lines", "review.small_max_files"):
        assert key in q["note"]
    ps = q["presets"]
    assert "small review on (at most 60 lines in 4 files outside tests); at most 2 Correctness passes;" in ps["light"]["words"]
    assert "small review on (at most 60 lines in 4 files outside tests); at most 2 Correctness passes;" in ps["normal"]["words"]
    assert "small review off; at most 2 Correctness passes;" in ps["thorough"]["words"]


def test_the_one_page_lists_the_small_review_and_the_pass_cap(tmp_path):
    _project(tmp_path, "review_passes = 3\n")
    page = _page(tmp_path, _defaults(tmp_path))
    small = _line(page, "- **Small review:**")
    assert small.startswith("- **Small review:** on:") and "`Review: small`" in small
    assert "within 60 lines in 4 files outside tests (added plus removed)" in small
    assert _line(page, "- **Pass cap:**") == (
        "- **Pass cap:** at most 3 Correctness passes after the last review round, then `needs-human`."
    )
    assert "**Size:** **Normal**." in page


def test_the_one_page_names_a_changed_small_review_and_pass_cap(tmp_path):
    _project(tmp_path)
    c = _defaults(tmp_path)
    c["review"].update(small=False, passes=5, small_max_lines=40)
    page = _page(tmp_path, c)
    assert "**Size:** **Normal**, changed: the small review off, 5 passes, a small threshold of 40 lines in 4 files outside tests." in page
    assert _line(page, "- **Small review:**").startswith("- **Small review:** off")
    # The threshold the owner set is what a run uses, even with the small review off.
    assert "--small-max-lines 40 --small-max-files 4`" in _merge_check(_brief(tmp_path, c))


@pytest.mark.parametrize("preset, review, want", [
    ("normal", {"rounds": 3, "explorer": True}, "**Normal**, changed: the small review off."),
    ("normal", None, "**Normal**, changed: the small review off."),
    ("thorough", {"rounds": 3, "explorer": True, "small": True, "passes": 1}, "**Thorough**, changed: the small review on, 1 pass."),
    ("thorough", {"rounds": 3, "explorer": True}, "**Thorough**."),
])
def test_the_one_page_names_a_small_review_that_differs_from_the_preset(tmp_path, preset, review, want):
    """An old charter's small review reads as off: the size line says so, as the small review's line does."""
    _project(tmp_path)
    c = _defaults(tmp_path)
    c["preset"] = preset
    c["limits"].update(_limits_q(tmp_path)["presets"][preset]["limits"])
    if review is None:
        del c["review"]
    else:
        c["review"] = review
    assert f"- **Size:** {want}" in _page(tmp_path, c)


def test_without_a_profile_normal_still_names_the_small_review(tmp_path):
    c = json.loads(_cli(tmp_path, "charter", "defaults").stdout)
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    c["review"]["small"] = False
    assert "- **Size:** **Normal**, changed: the small review off." in _page(tmp_path, c)


def test_the_small_review_names_the_explorer_only_where_the_run_has_one(tmp_path):
    _project(tmp_path)
    page = _page(tmp_path, _defaults(tmp_path))
    assert "(with the security review and the UI explorer where they apply)" in _line(page, "- **Small review:**")
    for review in ({"rounds": 3, "explorer": False, "small": True}, {"rounds": 1, "explorer": True, "small": True}):
        c = _defaults(tmp_path)
        c["review"] = review
        assert "(with the security review where it applies)" in _line(_page(tmp_path, c), "- **Small review:**")
        assert "with the security review where it applies)" in _line(_brief(tmp_path, c), "- **Small review:**")


def test_the_small_review_names_no_explorer_when_the_profile_has_none(tmp_path):
    """A charter approved before the profile's explorer went to `none` asks for one: no small review promises it."""
    _project(tmp_path, explorer="none")
    c = _defaults(tmp_path)
    c["review"] = {"rounds": 3, "explorer": True, "small": True}
    assert "(with the security review where it applies)" in _line(_page(tmp_path, c), "- **Small review:**")
    brief = _brief(tmp_path, c)
    assert "UI explorer: none." in _line(brief, "- **Review:**")
    assert "with the security review where it applies)" in _line(brief, "- **Small review:**")


def test_the_one_page_says_a_profile_value_written_out_is_no_change(tmp_path):
    _project(tmp_path)
    c = _defaults(tmp_path)
    c["review"].update(passes=2, small_max_lines=60, small_max_files=4)
    assert "**Size:** **Normal**." in _page(tmp_path, c)


# ---------- the briefing ----------


def test_the_briefing_gives_the_small_review_the_threshold_and_the_pass_cap(tmp_path):
    _project(tmp_path)
    brief = _brief(tmp_path, _defaults(tmp_path))
    small = _line(brief, "- **Small review:**")
    assert small.startswith("- **Small review:** on:")
    assert "`Review: small`" in small and "within 60 lines in 4 files outside tests (added plus removed)" in small
    assert "workflow.py review-record --measure --commit <sha> --small-max-lines 60 --small-max-files 4`" in small
    assert "the full panel" in small
    assert _line(brief, "- **Pass cap:**").startswith("- **Pass cap:** at most 2 Correctness passes after the last review round")
    assert _merge_check(brief).count("--review-rounds 3 --review-passes 2 --small-max-lines 60 --small-max-files 4`") == 1


def test_a_one_round_briefing_with_the_small_review_on(tmp_path):
    _project(tmp_path, 'preset = "light"\n')
    c = _defaults(tmp_path)
    assert c["review"] == {"rounds": 1, "explorer": False, "small": True}
    brief = _brief(tmp_path, c)
    assert "at most 1 (the light review)." in _line(brief, "- **Review:**")
    small = _line(brief, "- **Small review:**")
    assert small.startswith("- **Small review:** on:") and "the light review" in small and "the full panel" not in small
    assert "--review-rounds 1 --review-passes 2 --small-max-lines 60 --small-max-files 4`" in _merge_check(brief)


def test_a_briefing_with_the_small_review_off(tmp_path):
    _project(tmp_path, 'preset = "thorough"\n')
    brief = _brief(tmp_path, _defaults(tmp_path))
    small = _line(brief, "- **Small review:**")
    assert small.startswith("- **Small review:** off:") and "`Review: small`" in small
    # merge-check still gets the threshold: a round without Spec is held to it.
    assert "--small-max-lines 60 --small-max-files 4`" in _merge_check(brief)


# ---------- the skills and docs ----------


def test_build_ticket_step_3_names_the_threshold_flags():
    build = (KIT / "skills/build-ticket/SKILL.md").read_text()
    step = build.split("3. **Run `WF merge-check`.**", 1)[1].split("\n   - ", 1)[0]
    assert "--review-rounds <N>" in step and "--review-passes <P>" in step
    assert "--small-max-lines <L> --small-max-files <F>" in step
    assert "the briefing's small threshold" in step


def test_the_conductor_passes_the_charters_values():
    conductor = (KIT / "skills/conductor/SKILL.md").read_text()
    row = next(l for l in conductor.splitlines() if l.startswith("| **PR open, not merged**"))
    assert "--review-passes <P> --small-max-lines <L> --small-max-files <F>" in row
    assert "`review.passes`" in row and "`review.small_max_lines`" in row and "`review.small_max_files`" in row


def test_the_merge_check_skill_no_longer_says_briefings_carry_none():
    skill = (KIT / "skills/merge-check/SKILL.md").read_text()
    assert "while briefings carry" not in skill


def test_docs_charter_names_the_new_keys():
    doc = (KIT / "docs/charter.md").read_text()
    for key in ("`review.small`", "`review.passes`", "`review.small_max_lines`", "`review.small_max_files`"):
        assert key in doc, key
    assert "| `review.small` | on | on | off |" in doc
    schema = doc.split("## 5. The schema", 1)[1]
    assert "a missing `small` reads as off" in schema


def test_changelog_notes_259_without_bumping_version():
    text = (KIT / "CHANGELOG.md").read_text()
    assert "(#259" in since_0110(text)
    released = text.split("\n## ")[2].split()[0].lstrip("v")
    assert (KIT / "VERSION").read_text().strip() == released
