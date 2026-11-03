"""#426 (spec #412, "Records and clean"): `workflow merge-check` judges `rule=2`
review records, which `workflow review-record --findings` writes (#370).

- A `rule=2` review is clean only when it reports no finding marked blocks; a
  finding kept after a contest is re-entered as blocks, so it is never clean
  either. A blocking finding fixed in the same review still makes it not
  clean: the next review checks the fix.
- A finding marked note, or a ticket to fix it, never makes a review unclean.
- There is no pass cap for `rule=2` records: never `passes_used_up`, whatever
  `--review-passes` or the profile's `run.review_passes` says. The round limit
  still chooses the review's shape, as today.
- Records without `rule=2` are judged as today (their own tests:
  `test_merge_check_passes.py`, `test_until_clean.py`); on a pull request with
  both, the latest counted record's rule decides.
"""

import json

import pytest

from changelog_notes import since_0110
from test_merge_check import EARLIER, HEAD, check, comment, ids, inputs, note_ids, project, rec  # noqa: F401 (project is a fixture)
from test_merge_check_passes import KIT, MIDDLE, passes_in_profile, records, review_reasons, three_commits
from workflow import findings, reviews

BLOCKS = {"mark": "blocks", "mechanism": "the requeue order", "reproducer": "a PR dropped twice is requeued once"}
KEPT = {**BLOCKS, "contested": True}
TICKET = {"mark": "ticket", "mechanism": "label sync", "issue": 415}
NOTE = {"mark": "note", "mechanism": "wording"}
SECURITY_NOTE = {"mark": "note", "mechanism": "token scope", "security": "change", "area": "sign-in"}


def new(found=(), kind="round", rnd=1, commit=HEAD, outcomes=(), split=False, reviewers=None, hashes=(None, None)):
    """A `rule=2` record, as `workflow review-record --findings` writes it."""
    f = findings.load(json.dumps({"findings": list(found), "outcomes": list(outcomes), "split": split}))
    who = reviewers or ("correctness" if kind == "pass" else "standards,spec,correctness")
    return reviews.record(kind=kind, round=rnd, commit=commit, reviewers=who, clean=None, findings=f, diff=hashes[0], lines=hashes[1])


def with_records(*recs, data=None):
    data = data or three_commits()
    data["comments"] = records(*recs)
    return data


def review_ids(got):
    return [(r["id"], r.get("next")) for r in review_reasons(got)]


# ---------- clean, worked out from the marks ----------


def test_the_records_are_read_as_rule_2():
    [r] = reviews.read([comment(new([BLOCKS]))])
    assert r.rule == reviews.RULE and not r.found.clean


@pytest.mark.parametrize("found", [
    [],
    [NOTE],
    [TICKET],
    [NOTE, TICKET, SECURITY_NOTE],
], ids=["no-findings", "a-note", "a-ticket", "notes-and-tickets"])
def test_a_round_with_no_blocking_finding_is_clean_and_ready(project, capsys, found):
    got, _ = check(project, capsys, with_records(new(found)))
    assert got["decision"] == "ready", got["reasons"]


KEPT_RULING = [{"outcome": "contested", "finding": 1, "ruling": "kept"}]


@pytest.mark.parametrize("found, outcomes", [
    ([BLOCKS], []),
    ([NOTE, BLOCKS, TICKET], []),
    ([KEPT], KEPT_RULING),
], ids=["blocks", "blocks-among-others", "kept-contest"])
def test_a_blocking_or_kept_finding_makes_the_round_not_clean(project, capsys, found, outcomes):
    got, _ = check(project, capsys, with_records(new(found, rnd=2, outcomes=outcomes)))
    assert review_ids(got) == [("review_not_clean", "round")]


def test_a_blocking_finding_fixed_in_the_same_review_still_makes_it_not_clean(project, capsys):
    # Round 1 on EARLIER found it; its fix is the head. The next review checks the fix.
    got, _ = check(project, capsys, with_records(new([BLOCKS], commit=EARLIER)))
    assert review_ids(got) == [("review_not_clean", "round")]


def test_a_pass_with_a_blocking_finding_isnt_clean_and_one_with_notes_is(project, capsys):
    blocked = with_records(new([BLOCKS], rnd=3, commit=EARLIER), new([BLOCKS], kind="pass", rnd=3))
    assert review_ids(check(project, capsys, blocked, "--review-rounds", "3")[0]) == [("pass_not_clean", None)]
    noted = with_records(new([BLOCKS], rnd=3, commit=EARLIER), new([NOTE, TICKET], kind="pass", rnd=3))
    assert check(project, capsys, noted, "--review-rounds", "3")[0]["decision"] == "ready"


def test_a_kept_contest_on_a_pass_isnt_clean(project, capsys):
    data = with_records(
        new([BLOCKS], rnd=3, commit=EARLIER),
        new([KEPT], kind="pass", rnd=3, outcomes=KEPT_RULING),
    )
    assert review_ids(check(project, capsys, data, "--review-rounds", "3")[0]) == [("pass_not_clean", None)]


def test_an_overturned_contest_leaves_the_review_clean(project, capsys):
    # The contest was overturned, so the finding isn't re-entered: it counts for nothing.
    data = with_records(
        new([BLOCKS], rnd=3, commit=EARLIER),
        new([NOTE], kind="pass", rnd=3, outcomes=[{"outcome": "contested", "finding": 1, "ruling": "overturned"}]),
    )
    assert check(project, capsys, data, "--review-rounds", "3")[0]["decision"] == "ready"


# ---------- the round limit still applies ----------


def test_the_round_limit_still_chooses_a_round_or_a_pass(project, capsys):
    below = with_records(new([BLOCKS], rnd=2, commit=EARLIER))
    assert review_ids(check(project, capsys, below, "--review-rounds", "3")[0]) == [("review_not_clean", "round")]
    last = with_records(new([BLOCKS], rnd=3, commit=EARLIER))
    assert review_ids(check(project, capsys, last, "--review-rounds", "3")[0]) == [("review_not_clean", "pass")]


# ---------- no pass cap ----------


@pytest.mark.parametrize("cap", ["0", "1", "2", "10"])
def test_no_passes_used_up_whatever_the_flag_says(project, capsys, cap):
    many = [new([BLOCKS], kind="pass", rnd=3, commit=MIDDLE)] * 11 + [new([BLOCKS], kind="pass", rnd=3)]
    data = with_records(new([BLOCKS], rnd=3, commit=EARLIER), *many)
    got, _ = check(project, capsys, data, "--review-rounds", "3", "--review-passes", cap)
    assert review_ids(got) == [("pass_not_clean", None)]
    assert got["review_passes"] == "until-clean"


@pytest.mark.parametrize("cap", [0, 2])
def test_no_passes_used_up_whatever_the_profile_says(project, capsys, cap):
    passes_in_profile(project, cap)
    passes = [new([BLOCKS], kind="pass", rnd=3, commit=MIDDLE)] * 3
    got, _ = check(project, capsys, with_records(new([BLOCKS], rnd=3, commit=EARLIER), *passes), "--review-rounds", "3")
    # The passes were on an earlier commit: the head still needs one, and it is asked for.
    assert review_ids(got) == [("review_not_clean", "pass")]
    assert got["review_passes"] == "until-clean"


@pytest.mark.parametrize("recs, want", [
    # A last round that isn't clean, no pass yet: a pass comes next, at any cap.
    (lambda: [new([BLOCKS], rnd=3)], ("review_not_clean", "pass")),
    # A clean round on an earlier commit, nothing on the head: a pass comes next.
    (lambda: [new([], rnd=1, commit=EARLIER)], ("review_stale", None)),
], ids=["last-round", "stale"])
def test_with_a_cap_of_0_todays_reason_where_a_pass_comes_next(project, capsys, recs, want):
    got, _ = check(project, capsys, with_records(*recs()), "--review-rounds", "3", "--review-passes", "0")
    assert review_ids(got) == [want]


def test_a_clean_pass_on_the_head_after_many_is_ready(project, capsys):
    many = [new([BLOCKS], kind="pass", rnd=3, commit=MIDDLE)] * 6
    data = with_records(new([BLOCKS], rnd=3, commit=EARLIER), *many, new([NOTE], kind="pass", rnd=3))
    got, _ = check(project, capsys, data, "--review-rounds", "3", "--review-passes", "2")
    assert got["decision"] == "ready", got["reasons"]


def _free_pass(project, capsys, rule2):
    """A clean round, then a pass on a merge of the base that left the changed
    lines as they were (it doesn't count toward a cap), and the head after it."""
    from test_merge_check_carry_over import BASE_TIP, CONTEXT, FORK_POINT, MIDDLE as MERGE, RESOLVED, REVIEWED, hashed, hashes_of, pr

    reviewed, context = hashes_of(project, capsys, REVIEWED), hashes_of(project, capsys, CONTEXT)
    data = pr(RESOLVED, (EARLIER, [FORK_POINT]), (MERGE, [EARLIER, BASE_TIP]), (HEAD, [MERGE]))
    if rule2:
        data["comments"] = records(new([], rnd=1, commit=EARLIER, hashes=reviewed), new([NOTE], kind="pass", rnd=1, commit=MERGE, hashes=context))
    else:
        data["comments"] = records(hashed(rnd=1, commit=EARLIER, hashes=reviewed), hashed("pass", rnd=1, commit=MERGE, hashes=context))
    return check(project, capsys, data, "--review-passes", "1")[0]


def test_no_free_passes_note_without_a_cap(project, capsys):
    # The note about passes that didn't count toward the cap means nothing without one.
    old = _free_pass(project, capsys, rule2=False)
    assert "free_passes" in note_ids(old) and old["review_passes"] == 1
    got = _free_pass(project, capsys, rule2=True)
    assert review_ids(got) == [("review_stale", None)]
    assert "free_passes" not in note_ids(got) and got["review_passes"] == "until-clean"


def test_a_rule_2_review_carries_over_a_merge_of_the_base(project, capsys):
    # A merge of the base that left the pull request's own changes as they were: the review covers the head.
    from test_merge_check_carry_over import REVIEWED, hashes_of, merged_in

    reviewed = hashes_of(project, capsys, REVIEWED)
    for found, want in (([NOTE], "ready"), ([BLOCKS], "not_yet")):
        data = merged_in(REVIEWED)
        data["comments"] = records(new(found, rnd=1, commit=EARLIER, hashes=reviewed))
        got, _ = check(project, capsys, data)
        assert got["decision"] == want and "review_carried" in note_ids(got), got
    assert review_ids(got) == [("review_not_clean", "round")]


# ---------- both rules on one pull request: the latest counted record decides ----------


def test_old_records_alone_are_judged_as_today(project, capsys):
    data = with_records(rec(rnd=3, commit=EARLIER, clean=False), rec("pass", rnd=3, commit=MIDDLE, clean=False), rec("pass", rnd=3, commit=HEAD, clean=False))
    got, _ = check(project, capsys, data, "--review-rounds", "3", "--review-passes", "2")
    assert review_ids(got) == [("passes_used_up", "owner")]
    assert got["review_passes"] == 2


def test_old_records_then_a_new_one_no_cap(project, capsys):
    data = with_records(
        rec(rnd=3, commit=EARLIER, clean=False), rec("pass", rnd=3, commit=MIDDLE, clean=False), rec("pass", rnd=3, commit=MIDDLE, clean=False),
        new([BLOCKS], kind="pass", rnd=3),
    )
    got, _ = check(project, capsys, data, "--review-rounds", "3", "--review-passes", "2")
    assert review_ids(got) == [("pass_not_clean", None)]
    assert got["review_passes"] == "until-clean"


def test_new_records_then_an_old_one_the_cap_again(project, capsys):
    data = with_records(
        new([BLOCKS], rnd=3, commit=EARLIER), new([BLOCKS], kind="pass", rnd=3, commit=MIDDLE),
        rec("pass", rnd=3, commit=HEAD, clean=False),
    )
    got, _ = check(project, capsys, data, "--review-rounds", "3", "--review-passes", "2")
    assert review_ids(got) == [("passes_used_up", "owner")]
    assert got["review_passes"] == 2


def test_a_late_old_record_for_an_older_commit_doesnt_decide(project, capsys):
    # Posted last, but for MIDDLE, before the head's own pass: the new rule still decides.
    data = with_records(
        new([BLOCKS], rnd=3, commit=EARLIER), *[new([BLOCKS], kind="pass", rnd=3, commit=MIDDLE)] * 2, new([BLOCKS], kind="pass", rnd=3),
        rec("pass", rnd=3, commit=MIDDLE, clean=False),
    )
    got, _ = check(project, capsys, data, "--review-rounds", "3", "--review-passes", "2")
    assert review_ids(got) == [("pass_not_clean", None)]
    assert got["review_passes"] == "until-clean"


def test_a_late_new_record_for_an_older_commit_doesnt_decide(project, capsys):
    data = with_records(
        rec(rnd=3, commit=EARLIER, clean=False), rec("pass", rnd=3, commit=MIDDLE, clean=False), rec("pass", rnd=3, commit=HEAD, clean=False),
        new([BLOCKS], kind="pass", rnd=3, commit=MIDDLE),
    )
    got, _ = check(project, capsys, data, "--review-rounds", "3", "--review-passes", "2")
    assert review_ids(got) == [("passes_used_up", "owner")]
    assert got["review_passes"] == 2


def test_on_one_commit_the_last_posted_decides(project, capsys):
    old_last = with_records(new([BLOCKS], rnd=3, commit=EARLIER), *[new([BLOCKS], kind="pass", rnd=3)] * 2, rec("pass", rnd=3, commit=HEAD, clean=False))
    assert review_ids(check(project, capsys, old_last, "--review-rounds", "3", "--review-passes", "2")[0]) == [("passes_used_up", "owner")]
    new_last = with_records(new([BLOCKS], rnd=3, commit=EARLIER), *[rec("pass", rnd=3, commit=HEAD, clean=False)] * 2, new([BLOCKS], kind="pass", rnd=3))
    assert review_ids(check(project, capsys, new_last, "--review-rounds", "3", "--review-passes", "2")[0]) == [("pass_not_clean", None)]


def _past_250(*recs):
    """A pull request of 251 commits: GitHub lists the 250 oldest, so its head isn't listed."""
    data = inputs()
    shas = [f"{n:040x}" for n in range(1, 251)]
    data["pr"]["commits"] = 251
    data["commits"] = [{"sha": s} for s in shas]
    data["compare"]["commits"] = [{"sha": s} for s in shas] + [{"sha": HEAD}]
    data["compare"]["ahead_by"] = 251
    last = shas[-1]
    data["comments"] = records(*(r(last) for r in recs))
    return data


def test_a_head_past_the_listed_commits_is_the_newest(project, capsys):
    # The head isn't in GitHub's list: its record is still the latest, by the PR's history.
    new_last = _past_250(lambda last: rec(rnd=3, commit=last, clean=False), *[lambda last: rec("pass", rnd=3, commit=last, clean=False)] * 2,
                         lambda last: new([BLOCKS], kind="pass", rnd=3))
    got, _ = check(project, capsys, new_last, "--review-rounds", "3", "--review-passes", "2")
    assert review_ids(got) == [("pass_not_clean", None)] and got["review_passes"] == "until-clean"
    old_last = _past_250(lambda last: new([BLOCKS], rnd=3, commit=last), *[lambda last: new([BLOCKS], kind="pass", rnd=3, commit=last)] * 2,
                         lambda last: rec("pass", rnd=3, commit=HEAD, clean=False))
    got, _ = check(project, capsys, old_last, "--review-rounds", "3", "--review-passes", "2")
    assert review_ids(got) == [("passes_used_up", "owner")] and got["review_passes"] == 2


@pytest.mark.parametrize("order", [(HEAD, EARLIER, MIDDLE), (EARLIER, HEAD, MIDDLE)], ids=["head-first", "head-second"])
def test_a_head_listed_before_an_older_commit_is_still_the_newest(project, capsys, order):
    # GitHub lists commits by date, so a head can come before an older commit: a late record for that one doesn't decide.
    data = with_records(rec(rnd=3, commit=EARLIER, clean=False), new([BLOCKS], kind="pass", rnd=3), rec("pass", rnd=3, commit=MIDDLE, clean=False))
    data["commits"] = [{"sha": s} for s in order]
    got, _ = check(project, capsys, data, "--review-rounds", "3", "--review-passes", "1")
    assert review_ids(got) == [("pass_not_clean", None)] and got["review_passes"] == "until-clean"


def test_an_old_record_from_an_account_without_write_access_doesnt_decide(project, capsys):
    # Only counted records decide: a stranger's old-rule record posted last changes nothing.
    data = with_records(new([BLOCKS], rnd=3, commit=EARLIER), *[new([BLOCKS], kind="pass", rnd=3, commit=MIDDLE)] * 3)
    data["comments"].append(comment(rec("pass", rnd=3, commit=HEAD, clean=False), author="stranger", cid=99))
    got, _ = check(project, capsys, data, "--review-rounds", "3", "--review-passes", "2")
    assert review_ids(got) == [("review_not_clean", "pass")]
    assert got["review_passes"] == "until-clean"


def test_a_new_round_after_an_old_round_judges_by_its_marks(project, capsys):
    data = with_records(rec(rnd=1, commit=EARLIER, clean=False), new([NOTE], rnd=2))
    assert check(project, capsys, data, "--review-rounds", "3")[0]["decision"] == "ready"


# ---------- docs ----------


def test_the_changelog_notes_it():
    notes = since_0110()
    assert "(#426, part of spec #412)" in notes


def test_the_merge_check_skill_says_rule_2_has_no_cap():
    text = (KIT / "skills/merge-check/SKILL.md").read_text(encoding="utf-8")
    assert "rule=2" in text and "never says `passes_used_up`" in text
    [field] = [line for line in text.splitlines() if line.startswith("- `review_passes`:")]
    assert "`rule=2`" in field and "#426" in field


def test_the_flags_help_says_rule_2_has_no_cap(capsys):
    from workflow import cli

    with pytest.raises(SystemExit):
        cli.main(["merge-check", "--help"])
    help_text = " ".join(capsys.readouterr().out.split())
    assert "a run passes the briefing's; no pass cap applies when the latest counted review record is a rule=2 one" in help_text


def test_the_merge_rule_says_how_rule_2_is_judged():
    text = (KIT / "docs/flow.md").read_text(encoding="utf-8")
    assert "`rule=2`" in text and "latest counted record's rule decides" in text
