"""`workflow merge-check`: a clean Correctness pass after the last allowed
review round lifts that round's findings (#170), through the CLI, fed files.

The allowed rounds come from `--review-rounds`, else the profile's
`run.review_rounds` (3 by default). A not-clean round before the last allowed
one still needs another round; no fourth round is ever asked for.
"""

import pytest

from test_merge_check import EARLIER, HEAD, check, comment, ids, inputs, project, rec  # noqa: F401 (project is a fixture)


def rounds_in_profile(project, n):
    path = project / ".claude/workflow/profile.toml"
    path.write_text(path.read_text() + f"\n[run]\nreview_rounds = {n}\n")


def records(*recs):
    return [comment(r, cid=i + 1) for i, r in enumerate(recs)]


def review_reasons(got):
    return [r for r in got["reasons"] if r["rule"] == "review_panel"]


# ---------- the acceptance criteria ----------


def test_last_round_3_of_3_not_clean_and_a_clean_pass_on_the_head_is_ready(project, capsys):
    data = inputs()
    data["comments"] = records(
        rec(rnd=1, commit=EARLIER, clean=False), rec(rnd=2, commit=EARLIER, clean=False),
        rec(rnd=3, commit=EARLIER, clean=False), rec("pass", rnd=3, commit=HEAD),
    )
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]
    assert got["review_rounds"] == 3


def test_last_round_3_of_3_not_clean_with_no_pass_names_the_correctness_pass(project, capsys):
    data = inputs()
    data["comments"] = records(rec(rnd=1, clean=False), rec(rnd=2, clean=False), rec(rnd=3, clean=False))
    got, _ = check(project, capsys, data)
    [r] = review_reasons(got)
    assert r["id"] == "review_not_clean" and r["action"] == "review"
    assert r["next"] == "pass" and r["round"] == 3
    dev, new = r["wording"]["developer"], r["wording"]["new"]
    assert "the last of 3 allowed" in dev["message"]
    assert "Correctness pass on the head" in dev["fix"] and "another round" not in dev["fix"]
    assert "short check of the latest changes" in new["fix"]


def test_a_pass_on_an_earlier_commit_doesnt_lift_the_last_round(project, capsys):
    data = inputs()
    data["comments"] = records(rec(rnd=3, commit=EARLIER, clean=False), rec("pass", rnd=3, commit=EARLIER))
    got, _ = check(project, capsys, data)
    [r] = review_reasons(got)
    assert r["id"] == "review_not_clean" and r["next"] == "pass"


def test_a_pass_before_the_last_round_doesnt_lift_it(project, capsys):
    data = inputs()
    data["comments"] = records(rec("pass", rnd=2, commit=HEAD), rec(rnd=3, clean=False))
    got, _ = check(project, capsys, data)
    assert ids(got) == ["review_not_clean"]


def test_round_2_of_3_not_clean_and_a_clean_pass_still_needs_another_round(project, capsys):
    data = inputs()
    data["comments"] = records(rec(rnd=1, clean=False), rec(rnd=2, commit=EARLIER, clean=False), rec("pass", rnd=2, commit=HEAD))
    got, _ = check(project, capsys, data)
    [r] = review_reasons(got)
    assert r["id"] == "review_not_clean" and r["next"] == "round" and r["round"] == 2
    dev = r["wording"]["developer"]
    assert "round 2 of 3" in dev["message"]
    assert "run another round" in dev["fix"]
    assert "review it again" in r["wording"]["new"]["fix"]


def test_round_1_of_1_the_light_review_not_clean_and_a_clean_pass_is_ready(project, capsys):
    rounds_in_profile(project, 1)
    data = inputs()
    data["comments"] = records(rec(rnd=1, commit=EARLIER, clean=False), rec("pass", rnd=1, commit=HEAD))
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]
    assert got["review_rounds"] == 1


def test_a_not_clean_pass_after_the_last_round_is_pass_not_clean(project, capsys):
    data = inputs()
    data["comments"] = records(rec(rnd=3, commit=EARLIER, clean=False), rec("pass", rnd=3, commit=HEAD, clean=False))
    got, _ = check(project, capsys, data)
    assert ids(got) == ["pass_not_clean"]


def test_the_latest_pass_on_the_head_decides(project, capsys):
    data = inputs()
    data["comments"] = records(rec(rnd=3, commit=EARLIER, clean=False), rec("pass", rnd=3, commit=HEAD), rec("pass", rnd=3, commit=HEAD, clean=False))
    got, _ = check(project, capsys, data)
    assert ids(got) == ["pass_not_clean"]
    data["comments"] = records(rec(rnd=3, commit=EARLIER, clean=False), rec("pass", rnd=3, commit=HEAD, clean=False), rec("pass", rnd=3, commit=HEAD))
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]


def test_a_round_past_the_allowed_rounds_counts_as_the_last(project, capsys):
    # A light review's Correctness-only rounds come on top of its 1 allowed round.
    rounds_in_profile(project, 1)
    data = inputs()
    data["comments"] = records(rec(rnd=1, clean=False), rec(rnd=2, commit=EARLIER, reviewers="correctness", clean=False), rec("pass", rnd=2, commit=HEAD))
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]


def test_pr_177s_records_are_not_review_not_clean(project, capsys):
    """#76's PR #177: round 3 of 3 not clean, a not-clean pass on an earlier
    commit, then a clean pass on the head. The owner had to merge it by hand."""
    shas = ["afe26792ce2219aadd2608fe245f9f8efd30178a", "67cb43d34d5edb063de60e30711cbf50c78931f3",
            "321875192d0adbfcba0f9313e7675814565606a8", "57e9a490a82a02142bded1c38d09870ad0e2bf71",
            "2a3fde04fe37464957e2c565d9dafffd44ae9d14"]
    lines = [
        f"<!-- workflow:review kind=round round=1 commit={shas[0]} reviewers=standards,spec,correctness,explorer result=not-clean -->",
        f"<!-- workflow:review kind=round round=2 commit={shas[1]} reviewers=standards,spec,correctness result=not-clean -->",
        f"<!-- workflow:review kind=round round=3 commit={shas[2]} reviewers=correctness result=not-clean -->",
        f"<!-- workflow:review kind=pass round=3 commit={shas[3]} reviewers=correctness result=not-clean -->",
        f"<!-- workflow:review kind=pass round=3 commit={shas[4]} reviewers=correctness result=clean -->",
    ]
    data = inputs()
    data["pr"]["head"]["sha"] = shas[4]
    data["pr"]["commits"] = len(shas)
    data["commits"] = [{"sha": s} for s in shas]
    data["checks"]["check_runs"][0]["head_sha"] = shas[4]
    data["compare"]["commits"] = [{"sha": s} for s in shas]
    data["compare"]["ahead_by"] = len(shas)
    data["compare"]["url"] = data["compare"]["url"].replace(HEAD, shas[4])
    data["comments"] = [comment(f"Review record.\n\n{line}", cid=i + 1) for i, line in enumerate(lines)]
    got, _ = check(project, capsys, data)
    assert not review_reasons(got), got["reasons"]
    assert got["decision"] == "ready", got["reasons"]


# ---------- where the allowed rounds come from ----------


def test_review_rounds_flag_overrides_the_profile(project, capsys):
    rounds_in_profile(project, 3)
    data = inputs()
    data["comments"] = records(rec(rnd=2, commit=EARLIER, clean=False), rec("pass", rnd=2, commit=HEAD))
    got, _ = check(project, capsys, data)
    assert ids(got) == ["review_not_clean"] and got["review_rounds"] == 3
    got, _ = check(project, capsys, data, "--review-rounds", "2")
    assert got["decision"] == "ready", got["reasons"]
    assert got["review_rounds"] == 2


def test_the_profiles_review_rounds_are_used_without_the_flag(project, capsys):
    rounds_in_profile(project, 2)
    data = inputs()
    data["comments"] = records(rec(rnd=2, commit=EARLIER, clean=False), rec("pass", rnd=2, commit=HEAD))
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]
    assert got["review_rounds"] == 2


def test_without_the_flag_or_the_profiles_value_the_default_is_3(project, capsys):
    data = inputs()
    data["comments"] = records(rec(rnd=2, commit=EARLIER, clean=False), rec("pass", rnd=2, commit=HEAD))
    got, _ = check(project, capsys, data)
    assert got["review_rounds"] == 3
    assert ids(got) == ["review_not_clean"]


def test_an_unreadable_profile_still_says_3(project, capsys):
    (project / ".claude/workflow/profile.toml").write_text("[project\n")
    got, _ = check(project, capsys, inputs())
    assert got["review_rounds"] == 3


@pytest.mark.parametrize("value", ["0", "11", "-1", "three", "2.5", ""])
def test_a_value_outside_1_to_10_is_refused_with_a_plain_message(project, capsys, value):
    with pytest.raises(SystemExit) as e:
        check(project, capsys, inputs(), "--review-rounds", value)
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert "--review-rounds" in err and "a whole number from 1 to 10" in err
    assert "Traceback" not in err


def test_the_text_answer_names_the_correctness_pass(project, capsys):
    data = inputs()
    data["comments"] = records(rec(rnd=3, clean=False))
    out, _ = check(project, capsys, data, as_json=False)
    assert "Correctness pass on the head" in out or "short check of the latest changes" in out


def test_review_reasons_carry_the_counted_rounds_reviewers(project, capsys):
    data = inputs()
    data["comments"] = records(rec(rnd=1, clean=False, reviewers="correctness"))
    got, _ = check(project, capsys, data)
    [r] = review_reasons(got)
    assert r["reviewers"] == ["correctness"] and r["round"] == 1
