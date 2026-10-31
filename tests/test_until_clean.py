"""#402: the pass cap `until-clean`. A run can keep reviewing a ticket until a
Correctness pass is clean, bounded only by the run's end time.

`review.passes = "until-clean"` in the charter, or `run.review_passes =
"until-clean"` in the profile: `charter validate` and `profile check` accept it
and refuse any other string; `merge-check --review-passes until-clean` never
gives `passes_used_up`; `render` and `charter markdown` word it; the limits
question offers it beside the presets; the skills and docs say what it does.
Numbers 0 to 10, and an absent value, behave as before (their own tests:
`test_merge_check_passes.py`, `test_charter_small_review.py`)."""

import re

import pytest

from changelog_notes import since_0110
from test_charter_small_review import _brief, _defaults, _limits_q, _line, _merge_check, _page, _preset, _project, _validate
from test_merge_check import EARLIER, HEAD, check, ids, inputs, project, rec  # noqa: F401 (project is a fixture)
from test_merge_check_passes import KIT, _at_the_cap, _load, passes_in_profile, records, three_commits
from workflow import profile as profile_mod

WORDS = "Correctness passes until one is clean, within the run's end time"


def _read(rel):
    return (KIT / rel).read_text(encoding="utf-8")


def _until_clean_in_profile(project):
    path = project / ".claude/workflow/profile.toml"
    text = re.sub(r"\n\[run\]\nreview_passes = \d+\n", "", path.read_text())
    path.write_text(text + '\n[run]\nreview_passes = "until-clean"\n')


# ---------- merge-check: --review-passes until-clean ----------


def test_until_clean_never_gives_passes_used_up_however_many_passes(project, capsys):
    data = three_commits()
    many = [rec("pass", rnd=3, commit=EARLIER, clean=False)] * 6 + [rec("pass", rnd=3, commit=HEAD, clean=False)] * 6
    data["comments"] = records(rec(rnd=3, commit=EARLIER, clean=False), *many)
    got, _ = check(project, capsys, data, "--review-passes", "until-clean")
    assert ids(got) == ["pass_not_clean"], got["reasons"]
    assert got["decision"] == "not_yet" and got["review_passes"] == "until-clean"


def test_until_clean_where_a_number_would_be_at_the_cap(project, capsys):
    data = _at_the_cap()
    assert "passes_used_up" in ids(check(project, capsys, data)[0])
    got, _ = check(project, capsys, data, "--review-passes", "until-clean")
    assert ids(got) == ["pass_not_clean"]


@pytest.mark.parametrize("comments, want", [
    # A last round that isn't clean, no pass yet: a pass comes next.
    ([rec(rnd=3, commit=HEAD, clean=False)], ("review_not_clean", "pass")),
    # A clean round on an earlier commit, nothing on the head: a pass comes next.
    ([rec(rnd=1, commit=EARLIER)], ("review_stale", None)),
])
def test_until_clean_gives_todays_reason_where_a_pass_comes_next(project, capsys, comments, want):
    data = inputs()
    data["comments"] = records(*comments)
    got, _ = check(project, capsys, data, "--review-passes", "until-clean")
    [r] = [r for r in got["reasons"] if r["rule"] == "review_panel"]
    assert (r["id"], r.get("next")) == want


def test_until_clean_a_clean_pass_on_the_head_is_ready(project, capsys):
    data = three_commits()
    passes = [rec("pass", rnd=3, commit=EARLIER, clean=False)] * 11
    data["comments"] = records(rec(rnd=3, commit=EARLIER, clean=False), *passes, rec("pass", rnd=3, commit=HEAD))
    got, _ = check(project, capsys, data, "--review-passes", "until-clean")
    assert got["decision"] == "ready", got["reasons"]


def test_until_clean_from_the_profile(project, capsys):
    _until_clean_in_profile(project)
    got, _ = check(project, capsys, _at_the_cap())
    assert ids(got) == ["pass_not_clean"] and got["review_passes"] == "until-clean"


def test_a_number_flag_overrides_until_clean_in_the_profile(project, capsys):
    _until_clean_in_profile(project)
    got, _ = check(project, capsys, _at_the_cap(), "--review-passes", "2")
    assert "passes_used_up" in ids(got) and got["review_passes"] == 2


def test_until_clean_flag_overrides_a_number_in_the_profile(project, capsys):
    passes_in_profile(project, 0)
    data = inputs()
    data["comments"] = records(rec(rnd=1, commit=EARLIER))
    assert "passes_used_up" in ids(check(project, capsys, data)[0])
    assert ids(check(project, capsys, data, "--review-passes", "until-clean")[0]) == ["review_stale"]


@pytest.mark.parametrize("value", ["until_clean", "Until-Clean", "until clean", "until-clean ", "unlimited", "-1"])
def test_the_flag_refuses_any_other_string_with_a_plain_message(project, capsys, value):
    with pytest.raises(SystemExit) as e:
        check(project, capsys, inputs(), "--review-passes", value)
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert "--review-passes" in err and "a whole number from 0 to 10, or until-clean" in err
    assert "Traceback" not in err


# ---------- profile.load: run.review_passes = "until-clean" ----------


def test_the_profile_takes_until_clean(tmp_path):
    assert _load(tmp_path, 'review_passes = "until-clean"').review_passes == "until-clean"


@pytest.mark.parametrize("value", ['"until_clean"', '"UNTIL-CLEAN"', '"2"', '""', '"unlimited"'])
def test_the_profile_refuses_any_other_string(tmp_path, value):
    with pytest.raises(profile_mod.ProfileError) as e:
        _load(tmp_path, f"review_passes = {value}")
    msg = str(e.value)
    assert "run.review_passes" in msg and "from 0 to 10" in msg and '"until-clean"' in msg


def test_profile_check_accepts_until_clean_and_refuses_another_string(tmp_path):
    from test_charter_small_review import _cli

    _project(tmp_path, 'review_passes = "until-clean"\n')
    p = _cli(tmp_path, "profile", "check")
    assert p.returncode == 0, p.stdout + p.stderr
    _project(tmp_path, 'review_passes = "forever"\n')
    p = _cli(tmp_path, "profile", "check")
    assert p.returncode != 0 and "run.review_passes" in p.stdout + p.stderr


# ---------- charter validate ----------


def test_charter_validate_accepts_until_clean(tmp_path):
    _project(tmp_path)
    c = _defaults(tmp_path)
    c["review"]["passes"] = "until-clean"
    p = _validate(tmp_path, c)
    assert p.returncode == 0, p.stderr


@pytest.mark.parametrize("value", ["until_clean", "Until-Clean", "until clean", "", "unlimited"])
def test_charter_validate_refuses_any_other_string(tmp_path, value):
    _project(tmp_path)
    c = _defaults(tmp_path)
    c["review"]["passes"] = value
    p = _validate(tmp_path, c)
    assert p.returncode == 1 and 'review.passes must be a whole number from 0 to 10, or "until-clean"' in p.stderr, p.stderr


# ---------- the one page, the limits question and the briefing ----------


def test_the_one_page_words_until_clean(tmp_path):
    _project(tmp_path)
    c = _defaults(tmp_path)
    c["review"]["passes"] = "until-clean"
    line = _line(_page(tmp_path, c), "- **Pass cap:**")
    assert line == (
        f"- **Pass cap:** none: after the last review round, {WORDS}; "
        "a ticket still not clean at the end time is set aside (`needs-human`)."
    )


def test_the_one_page_names_until_clean_as_a_change_from_the_preset(tmp_path):
    _project(tmp_path)
    c = _preset(tmp_path, "normal")
    c["review"]["passes"] = "until-clean"
    assert "**Size:** **Normal**, changed: Correctness passes until one is clean." in _page(tmp_path, c)


def test_the_one_page_with_a_number_reads_as_before(tmp_path):
    _project(tmp_path, "review_passes = 3\n")
    assert _line(_page(tmp_path, _defaults(tmp_path)), "- **Pass cap:**") == (
        "- **Pass cap:** at most 3 Correctness passes after the last review round, then `needs-human`."
    )


def test_until_clean_in_the_profile_reads_into_the_presets_and_the_page(tmp_path):
    _project(tmp_path, 'review_passes = "until-clean"\n')
    q = _limits_q(tmp_path)
    for name in ("light", "normal", "thorough"):
        assert f"; {WORDS};" in q["presets"][name]["words"]
    c = _preset(tmp_path, "normal")
    page = _page(tmp_path, c)
    assert "**Size:** **Normal**." in page
    assert _line(page, "- **Pass cap:**").startswith(f"- **Pass cap:** none: after the last review round, {WORDS}")


def test_the_limits_question_offers_until_clean_beside_the_presets(tmp_path):
    _project(tmp_path, "review_passes = 3\n")
    q = _limits_q(tmp_path)
    assert q["pass_cap"] == [
        {"value": 3, "words": "at most 3 Correctness passes"},
        {"value": "until-clean", "words": WORDS},
    ]
    assert '"until-clean"' in q["note"]
    # The presets' numbers stay as they are.
    for name in ("light", "normal", "thorough"):
        assert "passes" not in q["presets"][name]["review"]
        assert "at most 3 Correctness passes" in q["presets"][name]["words"]


def test_the_limits_question_with_until_clean_in_the_profile_offers_a_number_too(tmp_path):
    _project(tmp_path, 'review_passes = "until-clean"\n')
    assert _limits_q(tmp_path)["pass_cap"] == [
        {"value": "until-clean", "words": WORDS},
        {"value": 2, "words": "at most 2 Correctness passes"},
    ]


def test_the_briefing_words_until_clean(tmp_path):
    _project(tmp_path)
    c = _defaults(tmp_path)
    c["review"]["passes"] = "until-clean"
    brief = _brief(tmp_path, c)
    line = _line(brief, "- **Pass cap:**")
    assert line.startswith(f"- **Pass cap:** none: after the last review round, {WORDS}. Fix each pass's findings")
    assert "at most" not in line
    assert "`merge-check` never says `passes_used_up`" in line
    assert "findings table" in line
    assert "--review-passes until-clean --small-max-lines 60 --small-max-files 4`" in _merge_check(brief)


def test_the_briefing_takes_until_clean_from_the_profile(tmp_path):
    # A charter from a preset leaves review.passes out: the profile's cap then reaches the briefing.
    _project(tmp_path, 'review_passes = "until-clean"\n')
    c = _preset(tmp_path, "normal")
    assert "passes" not in c["review"]
    brief = _brief(tmp_path, c)
    assert _line(brief, "- **Pass cap:**").startswith(f"- **Pass cap:** none: after the last review round, {WORDS}")
    assert "--review-passes until-clean " in _merge_check(brief)


def test_no_free_passes_note_without_a_cap(project, capsys):
    # A pass after a merge of the base that didn't count toward the cap: with no cap, nothing to say about it.
    from test_merge_check import note_ids
    from test_merge_check_carry_over import BASE_TIP, CONTEXT, FORK_POINT, MIDDLE, RESOLVED, REVIEWED, hashed, hashes_of, pr

    reviewed, context = hashes_of(project, capsys, REVIEWED), hashes_of(project, capsys, CONTEXT)
    data = pr(RESOLVED, (EARLIER, [FORK_POINT]), (MIDDLE, [EARLIER, BASE_TIP]), (HEAD, [MIDDLE]))
    data["comments"] = records(hashed(rnd=1, commit=EARLIER, hashes=reviewed), hashed("pass", rnd=1, commit=MIDDLE, hashes=context))
    got, _ = check(project, capsys, data, "--review-passes", "1")
    assert "free_passes" in note_ids(got)
    got, _ = check(project, capsys, data, "--review-passes", "until-clean")
    assert ids(got) == ["review_stale"] and "free_passes" not in note_ids(got)


def test_the_briefing_with_a_number_reads_as_before(tmp_path):
    _project(tmp_path)
    brief = _brief(tmp_path, _defaults(tmp_path))
    assert _line(brief, "- **Pass cap:**") == (
        "- **Pass cap:** at most 2 Correctness passes after the last review round. "
        "When `merge-check` says `passes_used_up`, the cap is reached: stop (below)."
    )


# ---------- the kit's text ----------


def test_the_conductor_skill_says_what_until_clean_does():
    skill = _read("skills/conductor/SKILL.md")
    assert "`until-clean`" in skill
    cap = next(p for p in skill.split("\n\n") if p.startswith("**A ticket at the cap.**"))
    assert "`until-clean`" in cap and "never" in cap.split("`until-clean`", 1)[1]
    stop = skill.split("## Stop the run", 1)[1].split("\n## ", 1)[0]
    assert "`until-clean`" in stop and "set aside at the end time" in stop and "needs-human" in stop
    # The run's cap, from the charter or the profile; the state and the claim label too.
    aside = next(ln for ln in stop.splitlines() if "**Set aside at the end time**" in ln)
    assert "else the profile's `run.review_passes`" in aside and "else the profile's `run.review_passes`" in cap
    assert "mark it `needs-human` in the state" in aside and "remove `workflow:in-progress` and `ready-for-agent`" in aside
    # Once every session is archived, outside the per-session loop, a retry not yet started is set aside too.
    assert "once every session is archived (at once, when none was running at the stop)" in aside
    assert "\n\n   **Set aside at the end time**" in stop  # its own paragraph, not the bullet above's continuation
    # Only the tickets this stop leaves behind, never one set aside or asked about before: a resume takes none twice.
    assert "the state still holds `running` (its session archived by this step) or `queued` (not yet started: a retry, an answered ticket or an adopted leftover), not labelled `needs-human`" in aside
    assert "an open pull request on its ticket branch" in aside
    # The kick-off recommends until-clean for a ticket set aside at an earlier run's end time.
    size = skill.split("**The size, presets first.**", 1)[1].split("\n", 1)[0]
    assert "When a leftover adopted in step 1 is a ticket set aside at an earlier run's end time" in size and "recommend `until-clean`" in size
    assert "`pass_cap`" in skill.split("**The size, presets first.**", 1)[1].split("\n", 1)[0]


@pytest.mark.parametrize("rel", ["docs/flow.md", "skills/build-ticket/SKILL.md", "skills/review-panel/SKILL.md", "docs/charter.md", "docs/profile.md"])
def test_the_skills_and_docs_name_until_clean(rel):
    assert "until-clean" in _read(rel), rel


def test_the_profile_doc_row_names_until_clean():
    row = next(ln for ln in _read("docs/profile.md").splitlines() if ln.startswith("| `review_passes` |"))
    assert '`"until-clean"`' in row


def test_the_charter_doc_validation_names_until_clean():
    assert 'review.passes` 0–10 or `"until-clean"`' in _read("docs/charter.md")


def test_the_changelog_has_the_note():
    unreleased = since_0110(_read("CHANGELOG.md"))
    assert "(#402)" in unreleased and "`until-clean`" in unreleased
