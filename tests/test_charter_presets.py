"""#119: a run's size in one choice (#42). Seam 1, the charter through the CLI:
the presets in `questions` and `defaults`, their numbers with the profile's,
`markdown` saying what changed, `reuse` and `diff`, validation and the check
against the profile, and older charters reading as Normal. Seam 4, the profile:
`run.preset` through `profile check`."""

import json
import os
import subprocess
import sys

import pytest

from workflow import charter, presets

from conftest import KIT

CLI = KIT / "scripts/workflow.py"
# What review_of adds for a charter without them (#259): the small review off, the profile's pass cap and threshold.
OFF = {"small": False, "passes": 2, "small_max_lines": 60, "small_max_files": 4}


def _cli(*args, env=None):
    e = {**os.environ, **(env or {})}
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, env=e)


def _profile(tmp_path, run="", explorer="none"):
    text = (
        '[project]\nname="d"\nrepo="a/d"\nowner="o"\n'
        '[ci]\nrequired_checks=["CI"]\n'
        f'[ui]\nexplorer="{explorer}"\n'
        f"[run]\n{run}"
    )
    (tmp_path / ".claude/workflow").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(text)
    return {"CLAUDE_PROJECT_DIR": str(tmp_path)}


def _defaults(env, *args):
    p = _cli("charter", "defaults", *args, env=env)
    assert p.returncode == 0, p.stderr
    c = json.loads(p.stdout)
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    return c


def _file(tmp_path, c, name="c.json"):
    f = tmp_path / name
    f.write_text(json.dumps(c))
    return str(f)


def _limits_q(env):
    p = _cli("charter", "questions", env=env)
    assert p.returncode == 0, p.stderr
    return next(q for q in json.loads(p.stdout) if q["key"] == "limits")


def _validate(tmp_path, env, c):
    return _cli("charter", "validate", _file(tmp_path, c), env=env)


# ---------- questions and defaults offer the presets first ----------


@pytest.mark.parametrize("line, want", [("", "normal"), ('preset = "light"\n', "light"), ('preset = "thorough"\n', "thorough")])
def test_questions_offer_the_presets_first_with_the_profiles_recommended(tmp_path, line, want):
    q = _limits_q(_profile(tmp_path, line))
    assert q["options"][0] == want and sorted(q["options"]) == ["light", "normal", "thorough"]
    assert q["recommended"] == want
    assert set(q["presets"]) == {"light", "normal", "thorough"}
    for name, p in q["presets"].items():
        assert set(p) == {"label", "limits", "review", "words"}
        assert set(p["limits"]) == {"max_parallel", "max_sessions", "max_retries"}
        assert set(p["review"]) == {"rounds", "explorer", "small"}
    assert "Light, Normal or Thorough" in q["ask"]
    # The end time is still asked: no preset gives one.
    assert "ends_at" in q["ask"] and "ends_at" not in q["presets"][want]["limits"]


@pytest.mark.parametrize("name", ["light", "normal", "thorough"])
def test_defaults_start_from_the_profiles_preset(tmp_path, name):
    env = _profile(tmp_path, f'preset = "{name}"\ncheck_in_minutes = 15\n')
    c = _defaults(env)
    want = _limits_q(env)["presets"][name]
    assert c["preset"] == name
    assert {k: c["limits"][k] for k in want["limits"]} == want["limits"]
    assert c["review"] == want["review"]
    # Not part of a preset: the check-in interval stays the profile's, the end time the owner's.
    assert c["limits"]["check_in_minutes"] == 15
    assert _cli("charter", "defaults", env=env).stdout.count('"ends_at": null') == 1
    assert _validate(tmp_path, env, c).returncode == 0


def test_defaults_keep_solo_modes_merge_rule(tmp_path):
    # #50's rule stands beside the presets: no auto-merge in solo mode, whatever the preset.
    env = _profile(tmp_path, 'preset = "thorough"\n')
    prof = tmp_path / ".claude/workflow/profile.toml"
    prof.write_text(prof.read_text().replace('owner="o"\n', 'owner="o"\nruleset=false\n'))
    c = _defaults(env)
    assert c["preset"] == "thorough" and c["merge"]["mode"] == "session"
    q = next(q for q in json.loads(_cli("charter", "questions", env=env).stdout) if q["key"] == "merge")
    assert "auto-merge" not in q["options"]


# ---------- each preset's numbers, with the profile's ----------


def test_each_presets_numbers_from_a_default_profile(tmp_path):
    ps = _limits_q(_profile(tmp_path, explorer="browser"))["presets"]
    assert ps["light"]["limits"] == {"max_parallel": 1, "max_sessions": 10, "max_retries": 0}
    assert ps["light"]["review"] == {"rounds": 1, "explorer": False, "small": True}
    assert ps["normal"]["limits"] == {"max_parallel": 2, "max_sessions": 40, "max_retries": 1}
    assert ps["normal"]["review"] == {"rounds": 3, "explorer": True, "small": True}
    assert ps["thorough"]["limits"] == {"max_parallel": 3, "max_sessions": 60, "max_retries": 1}
    assert ps["thorough"]["review"] == {"rounds": 3, "explorer": True, "small": False}


def test_normal_comes_from_the_profile(tmp_path):
    env = _profile(tmp_path, "max_parallel = 4\nmax_retries = 2\nreview_rounds = 2\n", explorer="cli")
    ps = _limits_q(env)["presets"]
    assert ps["normal"]["limits"] == {"max_parallel": 4, "max_sessions": 40, "max_retries": 2}
    assert ps["normal"]["review"] == {"rounds": 2, "explorer": True, "small": True}
    # Light and Thorough are fixed, apart from Thorough's rounds and both explorers.
    assert ps["light"]["limits"] == {"max_parallel": 1, "max_sessions": 10, "max_retries": 0}
    assert ps["thorough"]["limits"] == {"max_parallel": 3, "max_sessions": 60, "max_retries": 1}
    assert ps["thorough"]["review"]["rounds"] == 3


@pytest.mark.parametrize("rounds, want", [(1, 3), (3, 3), (5, 5), (10, 10)])
def test_thorough_has_at_least_3_rounds_and_keeps_more(tmp_path, rounds, want):
    ps = _limits_q(_profile(tmp_path, f"review_rounds = {rounds}\n"))["presets"]
    assert ps["thorough"]["review"]["rounds"] == want


def test_no_explorer_when_the_profile_has_none(tmp_path):
    ps = _limits_q(_profile(tmp_path, explorer="none"))["presets"]
    assert all(p["review"]["explorer"] is False for p in ps.values())
    assert "no UI explorer (the project has none)" in ps["thorough"]["words"]


def test_presets_without_a_profile():
    # Normal is the profile's defaults then, and nothing claims an explorer.
    assert presets.numbers("normal") == {
        "limits": {"max_parallel": 2, "max_sessions": 40, "max_retries": 1},
        "review": {"rounds": 3, "explorer": False, "small": True},
    }
    assert charter.defaults()["preset"] == "normal"


# ---------- one changed number keeps the preset ----------


def test_one_changed_number_keeps_the_preset_and_markdown_says_so(tmp_path):
    env = _profile(tmp_path, explorer="browser")
    c = _defaults(env)
    p = _cli("charter", "markdown", _file(tmp_path, c), env=env)
    assert p.returncode == 0, p.stderr
    assert "**Size:** **Normal**." in p.stdout and "changed" not in p.stdout
    assert "up to 3 rounds" in p.stdout and "UI explorer on" in p.stdout
    c["limits"]["max_parallel"] = 3
    assert _validate(tmp_path, env, c).returncode == 0
    p = _cli("charter", "markdown", _file(tmp_path, c), env=env)
    assert c["preset"] == "normal"
    assert "**Size:** **Normal**, changed: 3 sessions at once." in p.stdout


def test_markdown_names_every_change(tmp_path):
    env = _profile(tmp_path, explorer="browser")
    c = _defaults(env)
    c["preset"] = "light"
    c["limits"].update(max_parallel=1, max_sessions=12, max_retries=1)
    c["review"] = {"rounds": 2, "explorer": True}
    md = _cli("charter", "markdown", _file(tmp_path, c), env=env).stdout
    assert "**Size:** **Light**, changed: 12 sessions in all, 1 retry per ticket, 2 review rounds, the UI explorer on, the small review off." in md


def test_markdown_says_the_project_has_no_explorer(tmp_path):
    env = _profile(tmp_path, 'preset = "thorough"\n', explorer="none")
    md = _cli("charter", "markdown", _file(tmp_path, _defaults(env)), env=env).stdout
    assert "**Size:** **Thorough**." in md
    assert "no UI explorer (the project has none)" in md


def test_splice_renders_the_preset_too(tmp_path):
    env = _profile(tmp_path, 'preset = "light"\n')
    body = tmp_path / "b.md"
    body.write_text(f"# Run\n\n{charter.SECTION_BEGIN}\n{charter.SECTION_END}\n")
    p = _cli("charter", "splice", "--body", str(body), "--charter", _file(tmp_path, _defaults(env)), env=env)
    assert p.returncode == 0, p.stderr
    assert "**Size:** **Light**." in p.stdout


# ---------- reuse and diff ----------


def test_reuse_keeps_preset_and_review(tmp_path):
    env = _profile(tmp_path, 'preset = "thorough"\n', explorer="api")
    c = _defaults(env)
    c["review"]["rounds"] = 4
    p = _cli("charter", "reuse", _file(tmp_path, c), env=env)
    assert p.returncode == 0, p.stderr
    new = json.loads(p.stdout)
    assert new["preset"] == "thorough" and new["review"] == {"rounds": 4, "explorer": True, "small": False}


def test_diff_shows_changes_to_preset_and_review(tmp_path):
    env = _profile(tmp_path)
    old = _defaults(env)
    new = json.loads(json.dumps(old))
    new["preset"] = "light"
    new["review"]["rounds"] = 1
    lines = _cli("charter", "diff", _file(tmp_path, old, "o.json"), _file(tmp_path, new, "n.json"), env=env).stdout.splitlines()
    assert 'preset: "normal" -> "light"' in lines
    assert any(x.startswith("review: ") and '"rounds": 3' in x and '"rounds": 1' in x for x in lines)
    # An older charter against a new one shows both as added.
    older = {k: v for k, v in old.items() if k not in ("preset", "review")}
    lines = _cli("charter", "diff", _file(tmp_path, older, "o.json"), _file(tmp_path, old, "n.json"), env=env).stdout
    assert 'preset: null -> "normal"' in lines and "review: null ->" in lines


# ---------- refused ----------


@pytest.mark.parametrize(
    "change, needle",
    [
        ({"preset": "heavy"}, "preset must be one of"),
        ({"preset": "Normal"}, "preset must be one of"),
        ({"preset": ["light"]}, "preset must be one of"),
        ({"review": {"rounds": 3, "explorer": False, "depth": 2}}, "review: unknown key 'depth'"),
        ({"review": {"rounds": 0, "explorer": False}}, "review.rounds must be a whole number from 1 to 10"),
        ({"review": {"rounds": 11, "explorer": False}}, "review.rounds must be a whole number from 1 to 10"),
        ({"review": {"rounds": True, "explorer": False}}, "review.rounds must be a whole number from 1 to 10"),
        ({"review": {"rounds": 3, "explorer": "yes"}}, "review.explorer must be true or false"),
        ({"review": {"rounds": 3}}, "review.explorer must be true or false"),
        ({"review": "light"}, "review must be an object"),
    ],
)
def test_validate_refuses(tmp_path, change, needle):
    env = _profile(tmp_path)
    c = _defaults(env)
    c.update(change)
    p = _validate(tmp_path, env, c)
    assert p.returncode == 1 and needle in p.stderr, p.stderr


def test_the_explorer_on_without_one_in_the_profile_is_refused(tmp_path):
    env = _profile(tmp_path, explorer="none")
    c = _defaults(env)
    c["review"]["explorer"] = True
    p = _validate(tmp_path, env, c)
    assert p.returncode == 1 and "review.explorer" in p.stderr and "ui.explorer" in p.stderr
    # With one, it's fine.
    env = _profile(tmp_path, explorer="browser")
    assert _validate(tmp_path, env, c).returncode == 0


def test_state_init_refuses_the_explorer_without_one(tmp_path):
    env = _profile(tmp_path, explorer="none")
    c = _defaults(env)
    c["review"]["explorer"] = True
    c["approved"] = {"by": "o", "at": "2026-10-11T10:00:00Z", "source": "go"}
    p = _cli("state", "init", "--charter", _file(tmp_path, c), "--run-id", "r1", env=env)
    assert p.returncode == 1 and "review.explorer" in p.stderr


# ---------- older charters ----------


def _older(env):
    c = _defaults(env)
    del c["preset"], c["review"]
    return c


def test_a_charter_without_preset_or_review_stays_valid(tmp_path):
    env = _profile(tmp_path, 'preset = "light"\nreview_rounds = 2\n', explorer="browser")
    c = _older(env)
    assert _validate(tmp_path, env, c).returncode == 0
    c["approved"] = {"by": "o", "at": "2026-10-11T10:00:00Z", "source": "go"}
    p = _cli("state", "init", "--charter", _file(tmp_path, c), "--run-id", "r1", env=env)
    assert p.returncode == 0, p.stderr
    body = tmp_path / "b.md"
    body.write_text("# Run\n")
    st = tmp_path / "s.json"
    st.write_text(p.stdout)
    p = _cli("state", "put", "--body", str(body), "--state", str(st), env=env)
    assert p.returncode == 0, p.stderr


def test_a_charter_without_preset_or_review_reads_as_normal(tmp_path):
    # Whatever the profile's run.preset: it only recommends an answer.
    env = _profile(tmp_path, 'preset = "light"\nreview_rounds = 2\n', explorer="browser")
    c = _older(env)
    md = _cli("charter", "markdown", _file(tmp_path, c), env=env).stdout
    assert "**Size:** Normal (no preset in the charter)." in md
    assert "up to 2 rounds" in md and "UI explorer on" in md
    assert "changed" not in md
    # The review a run takes from it: the profile's rounds and explorer, as before.
    from workflow import profile as profile_mod

    prof = profile_mod.load(tmp_path)
    assert presets.review_of(c, prof) == {"rounds": 2, "explorer": True, **OFF}


def test_review_of_takes_the_charters_review(tmp_path):
    from workflow import profile as profile_mod

    env = _profile(tmp_path, explorer="browser")
    prof = profile_mod.load(tmp_path)
    c = _defaults(env)
    c["review"] = {"rounds": 1, "explorer": False}
    assert presets.review_of(c, prof) == {"rounds": 1, "explorer": False, **OFF}


# ---------- run.preset in the profile ----------


@pytest.mark.parametrize("line, want", [('preset = "light"\n', "light"), ('preset = "normal"\n', "normal"), ('preset = "thorough"\n', "thorough"), ("", "normal")])
def test_profile_check_accepts_each_preset_and_absent(tmp_path, line, want):
    env = _profile(tmp_path, line)
    p = _cli("profile", "check", env=env)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["preset"] == want


@pytest.mark.parametrize("line", ['preset = "heavy"\n', 'preset = "Light"\n', 'preset = ""\n', "preset = 1\n", "preset = true\n", 'preset = ["light"]\n'])
def test_profile_check_refuses_any_other_preset(tmp_path, line):
    env = _profile(tmp_path, line)
    p = _cli("profile", "check", env=env)
    assert p.returncode == 1
    assert "run.preset" in p.stderr and "light, normal or thorough" in p.stderr


def test_the_starter_profile_and_docs_name_run_preset():
    assert 'preset = "normal"' in (KIT / "templates/profile.toml").read_text()
    doc = (KIT / "docs/profile.md").read_text()
    assert "| `preset` |" in doc
    cdoc = (KIT / "docs/charter.md").read_text()
    for words in ("Light", "Normal", "Thorough", "`preset`", "`review`", "`review.rounds`", "`review.explorer`"):
        assert words in cdoc


def test_a_running_runs_charter_from_before_presets_keeps_working(tmp_path):
    # The shape of a charter approved before this change (as #130's run state holds it).
    env = _profile(tmp_path)
    c = {
        "version": 1,
        "scope": {"tickets": "all-ready", "exclude": [88], "follow_unblocked": True},
        "limits": {"ends_at": "2099-10-18T23:59:00Z", "max_parallel": 2, "max_sessions": 40, "max_retries": 1, "check_in_minutes": 10},
        "merge": {"mode": "auto-merge", "waived_checks": []},
        "release": {"when": "never", "steps": [], "smoke_test": True},
        "outward": {"allowed": []},
        "conductor_fixes": True,
        "open_decisions": "decide-and-record",
        "stop_run_on": [],
        "notify": {"failures": "issue", "final_report": "push"},
        "accepted_gaps": [],
        "approved": {"by": "o", "at": "2026-10-16T13:44:16Z", "source": "chat 2026-10-16T13:44:16Z: Go"},
        "amendments": [],
        "plan": [43, 44],
    }
    assert _cli("charter", "validate", _file(tmp_path, c), "--approved", env=env).returncode == 0
    st = tmp_path / "s.json"
    st.write_text(json.dumps({"version": 1, "charter": c, "tickets": {}}))
    body = tmp_path / "b.md"
    body.write_text("# Run\n")
    p = _cli("state", "put", "--body", str(body), "--state", str(st), env=env)
    assert p.returncode == 0, p.stderr


def test_a_preset_without_review_reviews_as_its_preset(tmp_path):
    # The page and the run never read a Light charter as Normal's review.
    from workflow import profile as profile_mod

    env = _profile(tmp_path, explorer="browser")
    c = _defaults(env)
    c["preset"] = "light"
    c["limits"].update(max_parallel=1, max_sessions=10, max_retries=0)
    del c["review"]
    assert _validate(tmp_path, env, c).returncode == 0
    md = _cli("charter", "markdown", _file(tmp_path, c), env=env).stdout
    # Without a review, the small review reads as off (#259): a change from Light's.
    assert "**Size:** **Light**, changed: the small review off." in md and "up to 1 round per ticket; UI explorer off." in md
    assert presets.review_of(c, profile_mod.load(tmp_path)) == {"rounds": 1, "explorer": False, **OFF}


def test_a_review_without_a_preset_shows_the_charters_review(tmp_path):
    env = _profile(tmp_path, explorer="browser")
    c = _older(env)
    c["review"] = {"rounds": 2, "explorer": False}
    md = _cli("charter", "markdown", _file(tmp_path, c), env=env).stdout
    assert "**Size:** Normal (no preset in the charter)." in md and "up to 2 rounds per ticket; UI explorer off." in md


def test_light_says_no_retries_in_plain_words(tmp_path):
    env = _profile(tmp_path, 'preset = "light"\n')
    md = _cli("charter", "markdown", _file(tmp_path, _defaults(env)), env=env).stdout
    assert "0 retries per ticket, then `needs-human`" in md and "0 retry " not in md


def test_markdown_and_splice_still_render_with_a_broken_profile(tmp_path):
    env = _profile(tmp_path)
    c = _defaults(env)
    (tmp_path / ".claude/workflow/profile.toml").write_text('[project]\nname="d"\nrepo="a/d"\n[run]\npreset="huge"\n')
    p = _cli("charter", "markdown", _file(tmp_path, c), env=env)
    assert p.returncode == 0, p.stderr
    assert "**Size:** **Normal**" in p.stdout
    body = tmp_path / "b.md"
    body.write_text(f"{charter.SECTION_BEGIN}\n{charter.SECTION_END}\n")
    p = _cli("charter", "splice", "--body", str(body), "--charter", _file(tmp_path, c), env=env)
    assert p.returncode == 0, p.stderr


def test_without_a_profile_normal_claims_no_changes(tmp_path):
    # Normal's numbers are the profile's: with none to compare, nothing is called changed.
    env = _profile(tmp_path, "max_parallel = 4\n")
    c = _defaults(env)
    p = _cli("charter", "markdown", _file(tmp_path, c), env={"CLAUDE_PROJECT_DIR": str(tmp_path / "none")})
    assert p.returncode == 0, p.stderr
    assert "**Size:** **Normal**." in p.stdout


def test_the_limits_questions_default_is_normals():
    q = next(q for q in charter.QUESTIONS if q["key"] == "limits")
    want = presets.numbers("normal")["limits"]
    assert {k: q["default"][k] for k in want} == want


def test_without_a_profile_thorough_claims_no_changed_rounds(tmp_path):
    env = _profile(tmp_path, 'preset = "thorough"\nreview_rounds = 5\n')
    c = _defaults(env)
    assert c["review"]["rounds"] == 5
    p = _cli("charter", "markdown", _file(tmp_path, c), env={"CLAUDE_PROJECT_DIR": str(tmp_path / "none")})
    assert p.returncode == 0, p.stderr
    assert "**Size:** **Thorough**." in p.stdout
    c["limits"]["max_parallel"] = 4
    p = _cli("charter", "markdown", _file(tmp_path, c), env={"CLAUDE_PROJECT_DIR": str(tmp_path / "none")})
    assert p.returncode == 0, p.stderr
    assert "**Size:** **Thorough**, changed: 4 sessions at once." in p.stdout
    # Fewer than 3 is a change whatever the profile says.
    c["limits"]["max_parallel"] = 3
    c["review"]["rounds"] = 2
    p = _cli("charter", "markdown", _file(tmp_path, c), env={"CLAUDE_PROJECT_DIR": str(tmp_path / "none")})
    assert p.returncode == 0, p.stderr
    assert "**Size:** **Thorough**, changed: 2 review rounds." in p.stdout


@pytest.mark.parametrize("broken", [b'[ui]\nexplorer = ["browser"]\n', b'[ui]\nnotes = "\xff"\n'])
def test_markdown_renders_with_a_profile_that_fails_to_load_oddly(tmp_path, broken):
    env = _profile(tmp_path)
    c = _defaults(env)
    (tmp_path / ".claude/workflow/profile.toml").write_bytes(b'[project]\nname="d"\nrepo="a/d"\n' + broken)
    p = _cli("charter", "markdown", _file(tmp_path, c), env=env)
    assert p.returncode == 0, p.stderr
    assert "**Size:** **Normal**" in p.stdout


def test_review_error_says_what_absent_means(tmp_path):
    env = _profile(tmp_path)
    c = _defaults(env)
    c["review"] = []
    p = _validate(tmp_path, env, c)
    assert "or absent (its preset's review; with no preset, the profile's)" in p.stderr


def test_profile_check_refuses_an_explorer_that_isnt_a_name(tmp_path):
    env = _profile(tmp_path)
    (tmp_path / ".claude/workflow/profile.toml").write_text('[project]\nname="d"\nrepo="a/d"\n[ui]\nexplorer = ["browser"]\n')
    p = _cli("profile", "check", env=env)
    assert p.returncode == 1 and "ui.explorer must be one of" in p.stderr and "Traceback" not in p.stderr


def test_without_a_profile_lights_explorer_on_is_still_a_change(tmp_path):
    env = _profile(tmp_path, 'preset = "light"\n', explorer="browser")
    c = _defaults(env)
    c["review"]["explorer"] = True
    p = _cli("charter", "markdown", _file(tmp_path, c), env={"CLAUDE_PROJECT_DIR": str(tmp_path / "none")})
    assert p.returncode == 0, p.stderr
    assert "**Size:** **Light**, changed: the UI explorer on." in p.stdout
