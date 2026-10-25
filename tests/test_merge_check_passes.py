"""`workflow merge-check`: the pass cap (#256, #255's seams 1, 4 and 5).

At most `run.review_passes` Correctness passes (default 2) after the last
counted round, from `--review-passes`, else the profile. Every counted pass
record after that round counts, on any commit of the pull request, repeated
ones on one commit included. Where a pass is what comes next and the cap is
reached, `passes_used_up` replaces `review_not_clean` (next: pass),
`pass_not_clean` and `review_stale`, and the pull request waits on the owner.
"""

import re
from pathlib import Path

import pytest

from test_merge_check import EARLIER, HEAD, check, comment, ids, inputs, project, rec  # noqa: F401 (project is a fixture)
from changelog_notes import since_0110
from workflow import profile as profile_mod

MIDDLE = "c" * 40  # a commit of the PR between EARLIER and HEAD
KIT = Path(__file__).resolve().parents[1]


def passes_in_profile(project, n):
    """Set `run.review_passes` to `n`, adding the `[run]` table the first time."""
    path = project / ".claude/workflow/profile.toml"
    text = re.sub(r"\n\[run\]\nreview_passes = \d+\n", "", path.read_text())
    path.write_text(text + f"\n[run]\nreview_passes = {n}\n")


def three_commits():
    data = inputs()
    shas = [EARLIER, MIDDLE, HEAD]
    data["pr"]["commits"] = len(shas)
    data["commits"] = [{"sha": s} for s in shas]
    data["compare"]["commits"] = [{"sha": s} for s in shas]
    data["compare"]["ahead_by"] = len(shas)
    return data


def records(*recs):
    return [comment(r, cid=i + 1) for i, r in enumerate(recs)]


def review_reasons(got):
    return [r for r in got["reasons"] if r["rule"] == "review_panel"]


def used_up(got):
    [r] = review_reasons(got)
    assert r["id"] == "passes_used_up", got["reasons"]
    return r


# ---------- passes up to the cap give today's reasons; at the cap, passes_used_up ----------


def test_up_to_the_cap_the_reasons_are_todays_then_passes_used_up(project, capsys):
    data = three_commits()
    data["comments"] = records(rec(rnd=3, commit=EARLIER, clean=False), rec("pass", rnd=3, commit=MIDDLE, clean=False))
    got, _ = check(project, capsys, data)
    [r] = review_reasons(got)
    assert r["id"] == "review_not_clean" and r["next"] == "pass"  # 1 of 2 used
    data["comments"] = records(rec(rnd=3, commit=EARLIER, clean=False), rec("pass", rnd=3, commit=HEAD, clean=False))
    got, _ = check(project, capsys, data)
    assert ids(got) == ["pass_not_clean"]  # 1 of 2 used
    data["comments"] = records(
        rec(rnd=3, commit=EARLIER, clean=False), rec("pass", rnd=3, commit=MIDDLE, clean=False), rec("pass", rnd=3, commit=HEAD, clean=False),
    )
    got, _ = check(project, capsys, data)
    r = used_up(got)
    assert r["action"] == "review" and r["next"] == "owner" and r["implements"] == "flow §4.4"
    assert got["decision"] == "not_yet" and got["review_passes"] == 2


def test_a_stale_head_at_the_cap_is_passes_used_up(project, capsys):
    data = three_commits()
    data["comments"] = records(rec(rnd=1, commit=EARLIER), rec("pass", rnd=1, commit=MIDDLE))
    got, _ = check(project, capsys, data)
    assert ids(got) == ["review_stale"]
    data["comments"] = records(rec(rnd=1, commit=EARLIER), rec("pass", rnd=1, commit=MIDDLE), rec("pass", rnd=1, commit=MIDDLE))
    used_up(check(project, capsys, data)[0])


def test_a_clean_last_round_then_passes_not_clean_reach_the_cap(project, capsys):
    data = inputs()
    data["comments"] = records(rec(rnd=1, commit=EARLIER), rec("pass", rnd=1, commit=HEAD, clean=False))
    got, _ = check(project, capsys, data)
    assert ids(got) == ["pass_not_clean"]
    got, _ = check(project, capsys, data, "--review-passes", "1")
    used_up(got)
    assert got["review_passes"] == 1


def test_the_cap_comes_from_the_profile(project, capsys):
    passes_in_profile(project, 3)
    data = three_commits()
    data["comments"] = records(
        rec(rnd=3, commit=EARLIER, clean=False), rec("pass", rnd=3, commit=MIDDLE, clean=False), rec("pass", rnd=3, commit=HEAD, clean=False),
    )
    got, _ = check(project, capsys, data)
    assert ids(got) == ["pass_not_clean"] and got["review_passes"] == 3
    passes_in_profile(project, 1)
    got, _ = check(project, capsys, data)
    used_up(got)
    assert got["review_passes"] == 1


def test_the_flag_overrides_the_profile(project, capsys):
    passes_in_profile(project, 1)
    data = inputs()
    data["comments"] = records(rec(rnd=1, commit=EARLIER), rec("pass", rnd=1, commit=HEAD, clean=False))
    used_up(check(project, capsys, data)[0])
    got, _ = check(project, capsys, data, "--review-passes", "4")
    assert ids(got) == ["pass_not_clean"] and got["review_passes"] == 4


def test_without_the_flag_or_the_profiles_value_the_cap_is_2(project, capsys):
    got, _ = check(project, capsys, inputs())
    assert got["review_passes"] == 2


def test_an_unreadable_profile_still_says_2(project, capsys):
    (project / ".claude/workflow/profile.toml").write_text("[project\n")
    got, _ = check(project, capsys, inputs())
    assert got["review_passes"] == 2


def _at_the_cap():
    data = three_commits()
    data["comments"] = records(
        rec(rnd=3, commit=EARLIER, clean=False), rec("pass", rnd=3, commit=MIDDLE, clean=False), rec("pass", rnd=3, commit=HEAD, clean=False),
    )
    return data


def test_the_cap_still_comes_back_beside_an_input_that_cant_be_read(project, capsys):
    # The conductor's step 2 relies on this (#281): an unreadable try-it link doesn't hide the cap.
    data = _at_the_cap()
    data["preview"] = {}
    got, _ = check(project, capsys, data, raw={"preview": "{not json"})
    assert [r.get("input") for r in got["reasons"] if r["id"] == "couldnt_read"] == ["preview"]
    used_up(got)


def test_with_the_profile_unreadable_the_cap_is_the_default_and_says_so(project, capsys):
    # The cap then isn't the project's own, so the conductor doesn't take it as the cap (#281).
    passes_in_profile(project, 4)
    data = _at_the_cap()
    assert ids(check(project, capsys, data)[0]) == ["pass_not_clean"]  # 2 of the project's 4
    (project / ".claude/workflow/profile.toml").write_text("[project\n")
    got, _ = check(project, capsys, data)
    assert [r.get("input") for r in got["reasons"] if r["id"] == "couldnt_read"] == ["profile"]
    used_up(got)


# ---------- --review-passes 0 ----------


def test_zero_passes_a_commit_after_a_clean_last_round_stops_at_once(project, capsys):
    data = inputs()
    data["comments"] = records(rec(rnd=1, commit=EARLIER))
    used_up(check(project, capsys, data, "--review-passes", "0")[0])


def test_zero_passes_a_last_round_that_isnt_clean_stops_at_once(project, capsys):
    data = inputs()
    data["comments"] = records(rec(rnd=3, commit=HEAD, clean=False))
    used_up(check(project, capsys, data, "--review-passes", "0")[0])


def test_zero_passes_from_the_profile(project, capsys):
    passes_in_profile(project, 0)
    data = inputs()
    data["comments"] = records(rec(rnd=1, commit=EARLIER))
    got, _ = check(project, capsys, data)
    used_up(got)
    assert got["review_passes"] == 0


def test_zero_passes_a_clean_round_on_the_head_is_ready(project, capsys):
    got, _ = check(project, capsys, inputs(), "--review-passes", "0")
    assert got["decision"] == "ready", got["reasons"]


def test_one_more_pass_past_the_cap_that_is_clean_on_the_head_is_ready(project, capsys):
    # The person chose "One more pass": a clean one on the head lifts it.
    data = three_commits()
    data["comments"] = records(
        rec(rnd=3, commit=EARLIER, clean=False), rec("pass", rnd=3, commit=MIDDLE, clean=False),
        rec("pass", rnd=3, commit=MIDDLE, clean=False), rec("pass", rnd=3, commit=HEAD),
    )
    got, _ = check(project, capsys, data)
    assert got["decision"] == "ready", got["reasons"]
    data["comments"] = records(rec(rnd=1, commit=EARLIER), rec("pass", rnd=1, commit=HEAD))
    got, _ = check(project, capsys, data, "--review-passes", "0")
    assert got["decision"] == "ready", got["reasons"]


# ---------- what counts ----------


def test_two_passes_not_clean_on_one_commit_count_twice(project, capsys):
    data = inputs()
    data["comments"] = records(rec(rnd=1, commit=EARLIER), rec("pass", rnd=1, commit=HEAD, clean=False), rec("pass", rnd=1, commit=HEAD, clean=False))
    used_up(check(project, capsys, data)[0])


def test_passes_on_earlier_commits_of_the_pr_count(project, capsys):
    data = three_commits()
    data["comments"] = records(rec(rnd=1, commit=EARLIER), rec("pass", rnd=1, commit=EARLIER, clean=False), rec("pass", rnd=1, commit=MIDDLE, clean=False))
    used_up(check(project, capsys, data)[0])


def test_passes_before_the_last_round_dont_count(project, capsys):
    data = three_commits()
    data["comments"] = records(
        rec(rnd=1, commit=EARLIER, clean=False), rec("pass", rnd=1, commit=EARLIER, clean=False), rec("pass", rnd=1, commit=EARLIER, clean=False),
        rec(rnd=2, commit=MIDDLE),
    )
    got, _ = check(project, capsys, data)
    assert ids(got) == ["review_stale"]


def test_passes_not_counted_dont_reach_the_cap(project, capsys):
    data = inputs()
    data["comments"] = [
        comment(rec(rnd=1, commit=EARLIER), cid=1),
        comment(rec("pass", rnd=1, commit=EARLIER, clean=False), author="stranger", cid=2),
        comment(rec("pass", rnd=1, commit="d" * 40, clean=False), cid=3),  # outside the PR
    ]
    got, _ = check(project, capsys, data)
    assert ids(got) == ["review_stale"]


# ---------- a round below the limit ----------


def test_a_round_below_the_limit_not_clean_still_asks_for_a_round_whatever_the_passes(project, capsys):
    data = inputs()
    data["comments"] = records(rec(rnd=1, commit=EARLIER, clean=False), *[rec("pass", rnd=1, commit=HEAD, clean=False)] * 3)
    for extra in ((), ("--review-passes", "0")):
        got, _ = check(project, capsys, data, *extra)
        [r] = review_reasons(got)
        assert r["id"] == "review_not_clean" and r["next"] == "round", extra


# ---------- the wording ----------


def test_passes_used_up_is_worded_at_both_levels(project, capsys):
    data = inputs()
    data["comments"] = records(rec(rnd=3, commit=EARLIER, clean=False), rec("pass", rnd=3, commit=HEAD, clean=False), rec("pass", rnd=3, commit=HEAD, clean=False))
    r = used_up(check(project, capsys, data)[0])
    dev, new = r["wording"]["developer"], r["wording"]["new"]
    assert dev["message"].startswith("Not yet: ") and new["message"].startswith("Not yet: ")
    assert "the pass cap is reached (2 allowed after round 3, 2 Correctness passes posted)" in dev["message"]
    assert "waits on the owner" in dev["message"]
    assert "the owner decides" in new["message"] and "stays unmerged" in new["fix"]
    assert "One more pass" in dev["fix"] and "needs-human" in dev["fix"]
    assert r["round"] == 3 and r["reviewers"] == ["standards", "spec", "correctness"]


def test_the_text_answer_says_the_cap_is_reached(project, capsys, monkeypatch):
    data = inputs()
    data["comments"] = records(rec(rnd=1, commit=EARLIER))
    out, _ = check(project, capsys, data, "--review-passes", "0", as_json=False)
    assert "The pass cap is reached (0 allowed after round 1, 0 Correctness passes posted)" in out and "waits on the owner" in out
    monkeypatch.setenv("WORKFLOW_EXPERIENCE", "new")
    out, _ = check(project, capsys, data, "--review-passes", "0", as_json=False)
    assert "The short checks of the latest changes have reached their limit, so the owner decides what happens next." in out


# ---------- --review-passes refuses values outside 0 to 10 ----------


@pytest.mark.parametrize("value", ["0", "10"])
def test_the_flag_takes_0_to_10(project, capsys, value):
    got, _ = check(project, capsys, inputs(), "--review-passes", value)
    assert got["review_passes"] == int(value)


@pytest.mark.parametrize("value", ["11", "-1", "two", "2.5", "", " 2", "+2", "٢", "9" * 5000])
def test_a_value_outside_0_to_10_is_refused_with_a_plain_message(project, capsys, value):
    with pytest.raises(SystemExit) as e:
        check(project, capsys, inputs(), "--review-passes", value)
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert "--review-passes" in err and "a whole number from 0 to 10" in err
    assert "Traceback" not in err
    [line] = [ln for ln in err.splitlines() if "--review-passes:" in ln]
    assert len(line) < 300


# ---------- profile.load: run.review_passes (seam 4) ----------


def _load(tmp_path, run=""):
    root = tmp_path / "p"
    (root / ".claude/workflow").mkdir(parents=True)
    (root / ".claude/workflow/profile.toml").write_text('[project]\nname = "demo"\nrepo = "acme/demo"\n' + (f"\n[run]\n{run}\n" if run else ""))
    return profile_mod.load(root)


def test_the_profile_default_is_2(tmp_path):
    assert _load(tmp_path).review_passes == 2


@pytest.mark.parametrize("n", [0, 2, 10])
def test_the_profile_takes_0_to_10(tmp_path, n):
    assert _load(tmp_path, f"review_passes = {n}").review_passes == n


@pytest.mark.parametrize("value", ["-1", "11", '"two"', "2.5", "true"])
def test_the_profile_refuses_values_outside_0_to_10(tmp_path, value):
    with pytest.raises(profile_mod.ProfileError) as e:
        _load(tmp_path, f"review_passes = {value}")
    assert "run.review_passes" in str(e.value) and "from 0 to 10" in str(e.value)


def test_the_template_and_the_profile_doc_name_it():
    assert "\nreview_passes = 2" in (KIT / "templates/profile.toml").read_text()
    row = next(ln for ln in (KIT / "docs/profile.md").read_text().splitlines() if ln.startswith("| `review_passes` |"))
    assert "(0–10)" in row and "`2`" in row


# ---------- the kit's text (seam 5) ----------


def _read(rel):
    return (KIT / rel).read_text(encoding="utf-8")


def test_the_merge_check_skill_offers_one_more_pass_and_names_the_flag():
    skill = _read("skills/merge-check/SKILL.md")
    assert "`passes_used_up`" in skill and "One more pass" in skill
    assert "--review-passes" in skill
    assert "- `review_passes`: how many Correctness passes it allowed" in skill


def test_build_ticket_takes_it_as_needs_human_and_passes_the_flag():
    build = _read("skills/build-ticket/SKILL.md")
    assert "`passes_used_up`" in build and "needs-human" in build.split("`passes_used_up`", 1)[1].split("\n", 1)[0]
    assert "--review-passes <P>" in build
    assert "the briefing's pass cap, else the profile's `run.review_passes`" in build


def test_the_conductor_takes_it_as_needs_human():
    conductor = _read("skills/conductor/SKILL.md")
    line = next(ln for ln in conductor.splitlines() if ln.startswith("| **`not_yet` with `passes_used_up`**"))
    assert "needs-human" in line
    # It leaves the labelling to the session, and claims no findings that may not exist.
    # Stopping is the session's: the conductor never settles a session that still runs.
    assert "Don't label or archive it yourself while its session runs" in line
    # Once labelled, a ticket at the cap takes step 2's steps (the "One more pass" note, the `for_owner`
    # line) on every path, the session's own stop at the cap included (#281).
    assert "for a ticket at the cap (step 2's \"A ticket at the cap\") take its steps instead of that row's question to the owner and its `for_owner` line" in line
    # Asking the owner, or a retry, would only start a session that stops at the cap again.
    assert "never requeues a ticket at the cap (step 2's \"A ticket at the cap\")" in line
    # "A ticket at the cap" is said once (#281): the merge rule's merge-check, flags and all (without
    # `--review-rounds`, a Light run's capped ticket reads as `next: round`), and the steps for it.
    at_cap = conductor.split("**A ticket at the cap.**", 1)[1].split("\n\n", 1)[0]
    assert "`WF merge-check` on its pull request, run as the \"PR open, not merged\" row runs it (with `--charter` and `--review-rounds <N>`), says `passes_used_up`" in at_cap
    # `merge-check` keeps judging the review when an input can't be read, so the cap wins over a
    # "couldn't read" reason (an unreadable try-it link, say), but not over one for the profile,
    # which holds the cap itself.
    assert "with no \"couldn't read\" reason for the profile, which holds the cap itself" in at_cap
    # Only an open pull request can be at the cap: a new PR starts with no passes counted.
    assert "A ticket with no open pull request (none, or one closed without merging) is never at the cap." in at_cap
    # With the profile unreadable the cap can't be told, so it isn't taken as the cap: the ticket keeps
    # waiting, and an answer requeues it as usual. Nothing is held, so no answer can be dropped.
    assert "With a \"couldn't read\" reason for the profile, whether it is at the cap can't be told, so it isn't at the cap: it still counts as waiting, and an answer requeues it as usual." in at_cap
    assert "waits for a check-in that reads the profile" not in conductor
    # The steps, each taken once, whichever path comes to them first.
    assert "take these steps, each only where it isn't done already:" in at_cap
    assert "leave its labels as they are (`needs-human` stays, with no `ready-for-agent` or `workflow:in-progress`)" in at_cap
    assert "clear its `asked_at`, so the run doesn't wait on it" in at_cap
    assert "replace its `for_owner` line with the pass-cap row's (\"#n reached its pass cap (#PR): see its review records and PR body\")" in at_cap
    assert "say on the ticket that \"One more pass\" runs in an attended session (the `merge-check` skill)" in at_cap
    # Named on the tracking issue at once, never left owed to a later check-in.
    assert "name the change on the tracking issue: in this check-in's comment, or, for an answer in chat between check-ins, in a comment of its own at once" in at_cap
    # Every path uses that one definition.
    waiting = conductor.split("- **Waiting on the owner** (not done):", 1)[1].split("\n- **Done**", 1)[0]
    assert "Before counting a `needs-human` ticket with `asked_at` as waiting, check whether it is at the cap (\"A ticket at the cap\", below)" in waiting
    # The definition isn't restated, so it can't be read the other way.
    assert "one that is takes its steps and no longer counts, since no answer lets a run build it; any other still counts." in waiting
    asking = conductor.split("**Asking about a `needs-human` ticket.**", 1)[1].split("\n\n", 1)[0]
    # Never asked about, and its steps taken, whichever way its session stopped.
    assert "A ticket at the cap (below) is never asked about, whatever stopped its session: no answer lets a run build it, so take the steps for a ticket at the cap instead." in asking
    answers = conductor.split("**When the owner answers**", 1)[1].split("\n3. ", 1)[0]
    assert "Except for a ticket at the cap (above): a new session would only stop at the pass cap again, so don't requeue it, and take the steps for a ticket at the cap instead." in answers
    # Each rule is said once: the definition and the `for_owner` line aren't restated elsewhere in step 2.
    step2 = conductor.split("**2. Stop or wind down?**", 1)[1].split("**3. The owner's words.**", 1)[0]
    assert step2.count("says `passes_used_up`") == 1
    assert step2.count("#n reached its pass cap (#PR): see its review records and PR body") == 1
    # Step 9 names the cap as an end of waiting on a question.
    assert "or its pull request reaches the pass cap" in conductor.split("- Never block on a question:", 1)[1].split("\n", 1)[0]
    assert "is the stuck row's, except that instead of a retry you label the ticket `needs-human`" in line


def test_the_ticket_session_prompts_stopping_list_names_the_cap():
    template = _read("templates/ticket-session-prompt.md")
    stopping = template.split("**Stopping:**", 1)[1].split("\n- **", 1)[0]
    assert "pass cap" in stopping and "`passes_used_up`" in stopping


def test_review_panel_5_stops_passes_at_the_cap():
    panel = _read("skills/review-panel/SKILL.md")
    assert "the briefing's pass cap in a ticket session, else the profile's `run.review_passes`" in panel


def test_the_flow_names_the_cap_in_3_4_and_5():
    flow = _read("docs/flow.md")
    s3 = flow.split("## 3. Building", 1)[1].split("\n## ", 1)[0]
    assert "pass cap" in s3 and "`run.review_passes`" in s3
    item4 = next(ln for ln in flow.splitlines() if ln.startswith("4. **The reviews are clean**"))
    assert "pass cap" in item4
    s5 = flow.split("## 5. Unattended runs", 1)[1]
    stops = next(ln for ln in s5.splitlines() if "it labels the ticket `needs-human`" in ln)
    assert "pass cap" in stops


def test_the_changelog_has_the_note():
    unreleased = since_0110(_read("CHANGELOG.md"))
    assert "(#256" in unreleased and "--review-passes N" in unreleased and "`passes_used_up`" in unreleased


def test_the_wording_holds_past_the_cap(project, capsys):
    # After "One more pass" that wasn't clean, the passes number more than the cap.
    data = inputs()
    data["comments"] = records(rec(rnd=1, commit=EARLIER), *[rec("pass", rnd=1, commit=HEAD, clean=False)] * 3)
    r = used_up(check(project, capsys, data)[0])
    assert "the pass cap is reached (2 allowed after round 1, 3 Correctness passes posted)" in r["wording"]["developer"]["message"]
