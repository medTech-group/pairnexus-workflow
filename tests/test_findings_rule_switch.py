"""#382: runs review under the rule for build reviewers (spec #412, "Runs").

A run started on the new kit uses the rule throughout; a run keeps the rule it
started with, with no question asked. The charter carries it as `rule: 2`
(written by `charter defaults` and `charter reuse`; absent means today's rule),
and a run's charter can't change it. Seams: the rendered briefing and the one
page (prior art: `tests/test_briefing_review.py`), with the charter's own
checks beside them.

- The briefing names the rule in a "Findings:" line; a briefing without it
  means today's rule (its "Pass cap:" line, as before).
- Under rule 2 the briefing and the one page drop the pass cap: the run's end
  time is its only limit on a ticket's reviews, and nothing stops for the owner
  because a review isn't clean.
"""

import json

import pytest

from changelog_notes import since_0110
from test_charter_small_review import KIT, TEMPLATE, _cli, _defaults, _file, _limits_q, _line, _merge_check, _page, _preset, _project, _validate
from workflow import charter as charter_mod
from workflow import presets as presets_mod

FINDINGS = "- **Findings:**"
PASS_CAP = "- **Pass cap:**"


def _read(rel):
    return (KIT / rel).read_text(encoding="utf-8")


def _render(tmp_path, c, template=TEMPLATE):
    c["approved"] = {"by": "o", "at": "2026-10-12T11:55:00Z", "source": "chat"}
    _file(tmp_path, c, "charter.json")
    return _cli(
        tmp_path, "render", "--template", str(template), "--ticket", "ticket.json", "--charter", "charter.json",
        "--slots", "slots.json", "--tracking", "11", "--out", "briefing.md",
    )


def _brief(tmp_path, c):
    p = _render(tmp_path, c)
    assert p.returncode == 0, p.stderr
    v = _cli(tmp_path, "briefing", "verify", "--file", "briefing.md")
    assert v.returncode == 0 and v.stdout.endswith(" intact\n"), v.stdout
    return (tmp_path / "briefing.md").read_text()


def _old(c):
    """The charter as a run started before the rule wrote it: no `rule`."""
    c.pop("rule", None)
    return c


def _lines(text, start):
    return [l for l in text.splitlines() if l.startswith(start)]


# ---------- the charter ----------


def test_a_new_charter_is_under_the_rule(tmp_path):
    _project(tmp_path)
    assert _defaults(tmp_path, rule=True)["rule"] == 2
    assert charter_mod.defaults()["rule"] == 2


def test_a_charter_from_a_preset_keeps_the_rule(tmp_path):
    # Choosing a preset sets `preset`, `limits` and `review`: the rule is outside them.
    _project(tmp_path)
    for name in ("light", "normal", "thorough"):
        assert _preset(tmp_path, name, rule=True)["rule"] == 2


def test_the_next_run_uses_the_rule(tmp_path):
    # A run started before the rule, reused for the next run: the next run uses the new one,
    # and the old pass cap goes, since there is none under the rule.
    _project(tmp_path)
    old = _old(_defaults(tmp_path, rule=True))
    old["review"]["passes"] = 3
    new = charter_mod.reuse(old)
    assert new["rule"] == 2 and "passes" not in new["review"]
    assert "rule: null -> 2" in charter_mod.diff(old, new)
    assert not charter_mod.validate({**new, "limits": {**new["limits"], "ends_at": "2099-10-13T03:30:00Z"}})


def test_reuse_keeps_a_until_clean_charter_valid(tmp_path):
    old = _old(charter_mod.defaults())
    old["review"]["passes"] = "until-clean"
    new = charter_mod.reuse(old)
    assert "passes" not in new["review"]
    assert not charter_mod.validate({**new, "limits": {**new["limits"], "ends_at": "2099-10-13T03:30:00Z"}})


def test_validate_accepts_the_rule_and_its_absence(tmp_path):
    _project(tmp_path)
    assert _validate(tmp_path, _defaults(tmp_path, rule=True)).returncode == 0
    assert _validate(tmp_path, _old(_defaults(tmp_path, rule=True))).returncode == 0


@pytest.mark.parametrize("value", [1, 3, "2", True, None, 2.0])
def test_validate_refuses_any_other_rule(tmp_path, value):
    _project(tmp_path)
    c = _defaults(tmp_path, rule=True)
    c["rule"] = value
    p = _validate(tmp_path, c)
    assert p.returncode == 1 and "rule must be 2" in p.stderr


@pytest.mark.parametrize("passes", [0, 2, "until-clean", 99, None])
def test_validate_refuses_a_pass_cap_under_the_rule(tmp_path, passes):
    # There is none to give: a pass cap the run would never apply is refused, not ignored.
    _project(tmp_path)
    c = _defaults(tmp_path, rule=True)
    c["review"]["passes"] = passes
    p = _validate(tmp_path, c)
    assert p.returncode == 1 and "review.passes" in p.stderr and "no pass cap" in p.stderr
    assert "must be a whole number" not in p.stderr  # one answer: no value is right
    if passes not in (99, None):
        assert _validate(tmp_path, _old(c)).returncode == 0  # today's rule keeps its pass cap


def test_the_review_under_the_rule_has_no_pass_cap(tmp_path):
    # Whatever the profile says: the charter's review is what the briefing, the page and merge-check take.
    _project(tmp_path, "review_passes = 3\n")
    from workflow.profile import load

    prof = load(tmp_path)
    assert presets_mod.review_of(_defaults(tmp_path, rule=True), prof)["passes"] == presets_mod.UNTIL_CLEAN
    assert presets_mod.review_of(_old(_defaults(tmp_path, rule=True)), prof)["passes"] == 3


def test_the_limits_question_offers_no_pass_cap_under_the_rule(tmp_path):
    _project(tmp_path, "review_passes = 3\n")
    q = _limits_q(tmp_path)
    assert "pass_cap" not in q
    assert "pass cap" not in q["ask"] and "review.passes" not in q["note"]
    for name in ("light", "normal", "thorough"):
        words = q["presets"][name]["words"]
        assert "at most 3 Correctness passes" not in words and presets_mod.UNTIL_CLEAN_WORDS in words, words


def test_a_run_keeps_the_rule_it_started_with(tmp_path):
    # Neither way: a run started before the rule never takes it mid-run, and a run under it never drops it.
    new, old = charter_mod.defaults(), _old(charter_mod.defaults())
    assert charter_mod.changed_rule(old, new) and charter_mod.changed_rule(new, old)
    assert charter_mod.changed_rule(old, old) is None and charter_mod.changed_rule(new, new) is None
    assert charter_mod.changed_rule(None, new) is None  # a run's first charter starts it
    # Clearing a run's charter is refused under either rule, so a later charter can't bring the other one.
    assert charter_mod.changed_rule(new, None) and charter_mod.changed_rule(old, None)


def _state(tmp_path, c):
    """A running run's tracking issue body. One started before the rule was written by an earlier
    kit's `state init`, which this kit's refuses (below), so it is built directly."""
    from workflow import state as state_mod

    c["approved"] = {"by": "o", "at": "2026-10-12T11:55:00Z", "source": "chat"}
    s = state_mod.empty(c)
    s["run_id"], s["comments_read_through"] = "r1", 0
    (tmp_path / "body.md").write_text(state_mod.put("The run.", s))


@pytest.mark.parametrize("rule", [True, False])
def test_a_run_started_on_this_kit_is_under_the_rule(tmp_path, rule):
    _project(tmp_path)
    c = _defaults(tmp_path, rule=True)
    if not rule:
        _old(c)
    c["approved"] = {"by": "o", "at": "2026-10-12T11:55:00Z", "source": "chat"}
    _file(tmp_path, c, "charter.json")
    p = _cli(tmp_path, "state", "init", "--charter", "charter.json", "--run-id", "r1", "--read-through", "0")
    if rule:
        assert p.returncode == 0, p.stderr
        assert json.loads(p.stdout)["charter"]["rule"] == 2
    else:
        assert p.returncode == 1 and "needs `rule: 2`" in p.stderr, p.stderr


@pytest.mark.parametrize("started", ["old", "new"])
def test_a_state_write_that_changes_the_rule_is_refused(tmp_path, started):
    from workflow import state as state_mod

    _project(tmp_path)
    c = _defaults(tmp_path, rule=True)
    if started == "old":
        _old(c)
    _state(tmp_path, c)
    before = (tmp_path / "body.md").read_text()

    def put(charter):
        s = state_mod.get(before)
        s["charter"] = charter
        (tmp_path / "state.json").write_text(json.dumps(s))
        return _cli(tmp_path, "state", "put", "--body", "body.md", "--state", "state.json", "--out", "body.md")

    other = json.loads(json.dumps(c))
    if started == "old":
        other["rule"] = 2
    else:
        _old(other)
    p = put(other)
    assert p.returncode != 0 and "keeps the rule it started with" in p.stderr, p.stderr + p.stdout
    assert (tmp_path / "body.md").read_text() == before
    # `state patch` refuses it too: a charter patch that sets the other rule, or takes it out.
    (tmp_path / "patch.json").write_text(json.dumps({"charter": {"rule": 2} if started == "old" else {"rule": None}}))
    p = _cli(tmp_path, "state", "patch", "--body", "body.md", "--patch", "patch.json", "--out", "body.md")
    assert p.returncode != 0 and "keeps the rule it started with" in p.stderr, p.stderr + p.stdout
    assert (tmp_path / "body.md").read_text() == before
    # Nor can the charter be cleared, so that a later `put` could bring the other rule.
    p = put(None)
    assert p.returncode != 0 and "nor the charter be cleared" in p.stderr, p.stderr + p.stdout
    assert (tmp_path / "body.md").read_text() == before
    # Any other charter change still goes through.
    same = json.loads(json.dumps(c))
    same["limits"]["check_in_minutes"] = 30
    p = put(same)
    assert p.returncode == 0, p.stderr
    assert state_mod.get((tmp_path / "body.md").read_text())["charter"]["limits"]["check_in_minutes"] == 30


# ---------- the rendered briefing ----------


def test_the_briefing_names_the_rule_in_a_findings_line(tmp_path):
    _project(tmp_path, "review_passes = 3\n")
    brief = _brief(tmp_path, _defaults(tmp_path, rule=True))
    [line] = _lines(brief, FINDINGS)
    assert line.startswith("- **Findings:** rule 2, the rule for build reviewers")
    assert "`review-panel` §10" in line and "`build-ticket` §3" in line
    # Plain words for what has no ticket number in another project: the briefing names none.
    assert "#412" not in line


def test_under_the_rule_the_briefing_drops_the_pass_cap(tmp_path):
    _project(tmp_path, "review_passes = 3\n")
    brief = _brief(tmp_path, _defaults(tmp_path, rule=True))
    assert not _lines(brief, PASS_CAP)
    line = _line(brief, FINDINGS)
    assert "no pass cap" in line and "the run's end time is the only limit on this ticket's reviews" in line
    assert "carries the ticket on to the next run" in line and "set aside" not in line
    # The bar goes to every reviewer; a ticket held for the owner isn't carried on.
    assert "each reviewer gets the ticket's `## Bar`, when it has one, as the line their hunt stops at" in line
    assert "unless it is held for the owner (a security or safety problem in code already on the base branch, or a protected path)" in line
    assert "--review-passes until-clean " in _merge_check(brief)
    # No owner stop for a review that isn't clean: `passes_used_up` never comes, so nothing waits on it.
    assert "Correctness passes after" not in brief and "passes_used_up" not in brief.replace(
        "`merge-check` never says `passes_used_up`", ""
    )
    stopping = _line(brief, "- **Stopping:**")
    # No pass cap to stop at; a stop `build-ticket` names (a security problem in code on the base branch) still applies.
    assert stopping == "- **Stopping:** if CI is still red after three fix attempts, or the ticket can't be built as written:"


def test_a_briefing_without_the_rule_reads_as_before(tmp_path):
    # A run started before the rule keeps today's rule throughout: no "Findings:" line, its pass cap and its stop.
    _project(tmp_path, "review_passes = 3\n")
    brief = _brief(tmp_path, _old(_defaults(tmp_path, rule=True)))
    assert not _lines(brief, FINDINGS) and "Findings:" not in brief
    assert _line(brief, PASS_CAP) == (
        "- **Pass cap:** at most 3 Correctness passes after the last review round. "
        "When `merge-check` says `passes_used_up`, the cap is reached: stop (below)."
    )
    assert "--review-passes 3 " in _merge_check(brief)
    assert _line(brief, "- **Stopping:**") == (
        "- **Stopping:** if CI is still red after three fix attempts, the review reached its pass cap "
        "(`merge-check` says `passes_used_up`: put the open findings in the PR body), or the ticket can't be built as written:"
    )


def test_a_template_without_the_line_is_refused_under_the_rule(tmp_path):
    # An older template has no slot for the "Findings:" line: its session would review under today's rule.
    _project(tmp_path)
    old = tmp_path / "old-template.md"
    old.write_text(TEMPLATE.read_text().replace("{{review.limit}}", "- **Pass cap:** {{review.pass_cap}}"))
    p = _render(tmp_path, _defaults(tmp_path, rule=True), old)
    assert p.returncode != 0 and "{{review.limit}}" in p.stderr
    p = _render(tmp_path, _old(_defaults(tmp_path, rule=True)), old)
    assert p.returncode == 0, p.stderr
    assert "Findings:" not in (tmp_path / "briefing.md").read_text()
    # Before #402 the line was "{{review.passes_words}} after the last review round": refused too.
    old.write_text(TEMPLATE.read_text().replace("{{review.limit}}", "- {{review.passes_words}} after the last review round."))
    p = _render(tmp_path, _defaults(tmp_path, rule=True), old)
    assert p.returncode != 0 and "{{review.limit}}" in p.stderr


def test_any_template_without_the_line_is_refused_under_the_rule(profile):
    # A project's own template, or an older kit's with no pass cap line at all: its session would
    # review under today's rule. Its other holes are named first.
    from workflow import render

    c = charter_mod.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    slots = {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "Build it.", "wake_trigger": "t"}
    vals = render.values(profile, {"number": 1}, c, slots, 1, None)
    with pytest.raises(render.RenderError, match=r"no \{\{review\.limit\}\} line"):
        render.render("{{briefing}}", vals)
    with pytest.raises(render.RenderError, match="no value for: nope"):
        render.render("{{briefing}} {{nope}}", vals)
    assert render.render("{{review.limit}}", vals).startswith("- **Findings:** rule 2")
    assert render.render("{{briefing}}", render.values(profile, {"number": 1}, _old(c), slots, 1, None)) == "Build it."


def test_the_template_has_the_line_once():
    assert TEMPLATE.read_text().count("{{review.limit}}") == 1
    assert "{{review.pass_cap}}" not in TEMPLATE.read_text()


HAND_OFF = "https://github.com/acme/demo/pull/41#issuecomment-6600212381"


def test_the_hand_off_line_reads_the_same_under_either_rule(tmp_path):
    # Under the rule, `build-ticket` §3 says how its findings are fixed; the line names no second way.
    _project(tmp_path)
    (tmp_path / "slots.json").write_text(json.dumps({**json.loads((tmp_path / "slots.json").read_text()), "hand_off": HAND_OFF}))
    ruled = _line(_brief(tmp_path, _defaults(tmp_path, rule=True)), "**Hand-off:**")
    assert ruled == _line(_brief(tmp_path, _old(_defaults(tmp_path, rule=True))), "**Hand-off:**")
    assert "fix its open blocking findings first, then run the next review" in ruled


# ---------- the one page ----------


def test_under_the_rule_the_one_page_names_it_and_drops_the_pass_cap(tmp_path):
    _project(tmp_path, "review_passes = 3\n")
    page = _page(tmp_path, _defaults(tmp_path, rule=True))
    assert not _lines(page, PASS_CAP)
    [line] = _lines(page, FINDINGS)
    assert line.startswith("- **Findings:** the rule for build reviewers")
    assert "no pass cap" in line and "the run's end time is the only limit on a ticket's reviews" in line
    assert "carried on to the next run" in line and "#412" not in line
    # The pass cap isn't named a change from the preset either.
    assert "**Size:** **Normal**." in page


def test_a_one_page_without_the_rule_reads_as_before(tmp_path):
    _project(tmp_path, "review_passes = 3\n")
    page = _page(tmp_path, _old(_defaults(tmp_path, rule=True)))
    assert not _lines(page, FINDINGS)
    assert _line(page, PASS_CAP) == "- **Pass cap:** at most 3 Correctness passes after the last review round, then `needs-human`."


# ---------- the kit's text ----------


def test_the_conductor_keeps_a_runs_rule_with_no_question():
    skill = _read("skills/conductor/SKILL.md")
    para = next(p for p in skill.split("\n") if "**The rule for build reviewers.**" in p)
    assert "`rule`" in para and "no question" in para and "started with" in para
    assert "never" in para and "mid-run" in para
    # The size question offers no pass cap under the rule.
    size = skill.split("**The size, presets first.**", 1)[1].split("\n", 1)[0]
    assert "no `pass_cap`" in size and "the rule for build reviewers (above)" in size


def test_the_limits_question_names_no_ticket():
    # Its words reach other projects' conductors, which have no such ticket.
    q = next(q for q in charter_mod.questions() if q["key"] == "limits")
    assert "#" not in q["ask"] + q["note"]


def test_the_rule_is_switched_on_by_the_templates_line_only():
    which = next(ln for ln in _read("skills/build-ticket/SKILL.md").splitlines() if ln.startswith("- **Which rule.**"))
    assert 'only when its briefing has a "Findings:" line naming rule 2' in which and "`- **Findings:** rule 2, …`" in which
    assert "the notes the conductor writes for the ticket don't count" in which


def test_every_merge_check_a_run_runs_has_no_pass_cap_under_the_rule():
    conductor = _read("skills/conductor/SKILL.md")
    row = next(ln for ln in conductor.splitlines() if ln.startswith("| **PR open, not merged** (any mode) |"))
    assert "`--review-passes until-clean` under the charter's `rule: 2`" in row
    cap = next(p for p in conductor.split("\n\n") if p.startswith("**A ticket at the cap.**"))
    assert "recommend `until-clean`" not in cap and "never finds it there" in cap
    step = next(ln for ln in _read("skills/build-ticket/SKILL.md").splitlines() if ln.startswith("3. **Run `WF merge-check`.**"))
    assert "`<P>` the briefing's pass cap (`until-clean` with its \"Findings:\" line" in step


def test_the_end_time_step_reads_the_rule_from_the_charter():
    stop = _read("skills/conductor/SKILL.md").split("## Stop the run", 1)[1].split("\n## ", 1)[0]
    aside = next(ln for ln in stop.splitlines() if "**Set aside at the end time**" in ln)
    assert "the charter's `rule: 2`" in aside


def test_the_charter_doc_names_the_rule():
    doc = _read("docs/charter.md")
    assert '"rule":    2' in doc.split("## 5. The schema", 1)[1]
    assert "`rule` 2 when given" in doc


def test_the_changelog_has_the_note():
    # Read from "## Unreleased" down, so a release that moves the note under its version keeps it found.
    note = since_0110(_read("CHANGELOG.md")).split("**Runs review under the rule for build reviewers** (#382", 1)[1].split("\n\n**", 1)[0]
    assert "`rule: 2`" in note and '"Findings:" line' in note
    released = _read("CHANGELOG.md").split("\n## ")[2].split()[0].lstrip("v")
    assert (KIT / "VERSION").read_text().strip() == released  # untouched: a release bumps it
