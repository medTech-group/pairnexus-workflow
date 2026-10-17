"""`workflow merge-check`: a clean Correctness pass after the last allowed
review round lifts that round's findings (#170), through the CLI, fed files.

The allowed rounds come from `--review-rounds`, else the profile's
`run.review_rounds` (3 by default). A not-clean round before the last allowed
one still needs another round; no fourth round is ever asked for.
"""

import json
import re
from pathlib import Path

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
    assert "wasn't clean, and no round is left (3 allowed)" in dev["message"]
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
    assert r["wording"]["new"]["fix"] == "Fix them, then run another review round."


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


@pytest.mark.parametrize("value", ["0", "11", "-1", "three", "2.5", "", " 3", "+3", "٣", "１", "²", "9" * 5000])
def test_a_value_outside_1_to_10_is_refused_with_a_plain_message(project, capsys, value):
    with pytest.raises(SystemExit) as e:
        check(project, capsys, inputs(), "--review-rounds", value)
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert "--review-rounds" in err and "a whole number from 1 to 10" in err
    assert "Traceback" not in err
    [line] = [ln for ln in err.splitlines() if "--review-rounds:" in ln]
    assert len(line) < 300  # a long value is cut


def test_the_text_answer_names_the_correctness_pass_at_both_levels(project, capsys, monkeypatch):
    data = inputs()
    data["comments"] = records(rec(rnd=3, clean=False))
    out, _ = check(project, capsys, data, as_json=False)
    assert "no round is left (3 allowed). Fix the findings and run a Correctness pass on the head; no further round." in out
    monkeypatch.setenv("WORKFLOW_EXPERIENCE", "new")
    out, _ = check(project, capsys, data, as_json=False)
    assert "The last review found things to fix. Fix them, then ask for a short check of the latest changes." in out


def test_the_flag_can_allow_more_rounds_than_the_profile(project, capsys):
    rounds_in_profile(project, 1)
    data = inputs()
    data["comments"] = records(rec(rnd=1, commit=EARLIER, clean=False), rec("pass", rnd=1, commit=HEAD))
    got, _ = check(project, capsys, data, "--review-rounds", "3")
    [r] = review_reasons(got)
    assert r["id"] == "review_not_clean" and r["next"] == "round"


def test_a_pass_from_an_account_without_write_access_doesnt_lift_the_last_round(project, capsys):
    data = inputs()
    data["comments"] = [comment(rec(rnd=3, commit=EARLIER, clean=False), cid=1), comment(rec("pass", rnd=3, commit=HEAD), author="stranger", cid=2)]
    got, _ = check(project, capsys, data)
    [r] = review_reasons(got)
    assert r["id"] == "review_not_clean" and r["next"] == "pass"
    assert "records_ignored" in [n["id"] for n in got["notes"]]


def test_every_case_is_worded_at_both_levels():
    from workflow import merge

    for rid, reason in merge.REASONS.items():
        for case, wording in reason.cases.items():
            assert set(wording) == set(reason.wording), (rid, case)
            for level, (message, fix) in wording.items():
                assert message.startswith("Not yet: ") and fix, (rid, case, level)
            assert wording["new"] != wording["developer"], (rid, case)


def test_review_reasons_carry_the_counted_rounds_reviewers(project, capsys):
    data = inputs()
    data["comments"] = records(rec(rnd=1, clean=False, reviewers="correctness"))
    got, _ = check(project, capsys, data)
    [r] = review_reasons(got)
    assert r["reviewers"] == ["correctness"] and r["round"] == 1


# ---------- the skills, docs and briefing pass the rounds ----------

KIT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (KIT / rel).read_text(encoding="utf-8")


def test_build_ticket_and_the_conductor_pass_the_review_rounds():
    build = _read("skills/build-ticket/SKILL.md")
    assert "--charter .workflow/tracking.md --review-rounds <N>`, with `<N>` the briefing's review rounds" in build
    assert "its `next` says what follows: `round` is another round, `pass` is a Correctness pass on the head, since that was the last allowed round" in build
    conductor = _read("skills/conductor/SKILL.md")
    assert "--charter .workflow/run/tracking.md --review-rounds <N>`, with `<N>` the charter's review rounds as the briefings give them (its `review.rounds`, else its preset's, else the profile's `run.review_rounds`)" in conductor
    assert "--review-rounds <the charter's review rounds>" in _read("docs/charter.md")


def test_the_merge_check_skill_runs_a_pass_for_next_pass():
    skill = _read("skills/merge-check/SKILL.md")
    assert "When its `next` is `pass` (that round was the last allowed one, by the answer's `review_rounds`), fix the findings, then a Correctness pass on the head (§5) instead" in skill
    assert "The reason's `round` and `reviewers` give that round directly." in skill
    assert "- `review_rounds`: how many review rounds it allowed" in skill
    fork = skill.split("**A branch Claude can't push to**", 1)[1].split("\n\n", 1)[0]
    assert "Once the author has pushed fixes, also offer it for `review_not_clean` whose `next` is `pass`, and for `pass_not_clean`" in fork
    assert "so a person needs no `--review-rounds`" in skill
    assert "for one whose body says \"Light review:\" (build-ticket's line), `--review-rounds 1`" in skill


def test_the_flow_says_the_last_round_is_lifted_by_a_clean_pass():
    flow = _read("docs/flow.md")
    item = next(ln for ln in flow.splitlines() if ln.startswith("4. **The reviews are clean**"))
    assert "unless it was the last allowed one (§3 step 3): then a clean Correctness pass on the head lifts its findings, and no further round is added" in item


def test_the_briefing_passes_its_review_rounds():
    from workflow import presets, render
    from workflow.profile import parse

    import conftest

    prof = parse(json.loads(json.dumps(conftest.BASE_PROFILE)), KIT)
    template = _read("templates/ticket-session-prompt.md")
    assert "--review-rounds {{review.rounds}}" in template
    for n in (1, 4):
        charter = {"review": {"rounds": n, "explorer": "none"}}
        v = render.values(prof, {"number": 7, "title": "t"}, charter, {}, 9, None)
        assert v["review.rounds"] == str(n)
        assert presets.review_of(charter, prof)["rounds"] == n
    # A charter with only a preset: the briefing gives its preset's rounds.
    light = {"preset": "light"}
    assert render.values(prof, {"number": 7, "title": "t"}, light, {}, 9, None)["review.rounds"] == str(presets.review_of(light, prof)["rounds"]) == "1"


def test_the_changelog_has_the_note():
    unreleased = _read("CHANGELOG.md").split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    assert "(#170" in unreleased and "--review-rounds N" in unreleased


def test_the_rendered_briefings_merge_check_names_the_rounds(tmp_path):
    from test_run_merges_on_merge_check import _render

    merging = _render(tmp_path, "auto-merge", [])
    assert re.search(r"merge-check --fetch <PR> --json --charter \.workflow/tracking\.md --review-rounds \d+`", merging), merging
