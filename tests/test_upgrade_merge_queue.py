"""#247: the "Use a merge queue" upgrade. Seam 6 of #243, the kit's text:
`upgrade-setup`'s fifth path (its two steps in order, workflows first, the
settings shown first, never mid-run), "Require these checks" leaving "up to
date" alone with the queue, the CI template's `merge_group`, the docs and the
changelog; and doctor's `require_checks` fix saying the same (seam 1)."""

import re

from changelog_notes import since_0110
from conftest import KIT
from test_doctor import RULESET, _prof, _project, _report
from test_doctor_github import CHECKS, _rule
from test_doctor_require_checks import _github, _given, _run, _runs

SKILL = KIT / "skills/upgrade-setup/SKILL.md"
NAME = "Use a merge queue"


def _text(path=SKILL):
    return path.read_text(encoding="utf-8")


def _part(title):
    m = re.search(rf"^# [^\n]*{re.escape(title)}[^\n]*\n(.*?)(?=^# |\Z)", _text(), re.M | re.S)
    assert m, f"no part {title!r}"
    return m.group(1)


def _sec(part, title):
    m = re.search(rf"^## [^\n]*{re.escape(title)}[^\n]*\n(.*?)(?=^## |\Z)", part, re.M | re.S)
    assert m, f"no section {title!r}"
    return m.group(1)


# ---------- the path and its offer ----------


def test_the_fifth_path_is_named_with_its_offer():
    text = _text()
    head = text.split("---", 2)[1]
    assert f'"{NAME}"' in head
    assert f'**"{NAME}"**' in text.split("\n## ", 1)[0]
    assert "The fifth part, last." in text and "shared by all five" in text
    assert text.index("\n# Add try-it links\n") < text.index(f"\n# {NAME}\n")
    assert "The fifth path (offer `use_merge_queue`)." in _part(NAME)
    offers = re.search(r"^## When it's offered\n(.*?)(?=^#{1,2} )", text, re.M | re.S).group(1)
    entry = offers[offers.index("**`use_merge_queue`**"):].split("\n- **`", 1)[0]
    assert "only through `workflow doctor`'s `use_merge_queue` offer" in entry and "or when the person asks" in entry
    assert "Never while a run is in progress" in entry


def test_its_two_steps_come_in_order_workflows_first():
    part = _part(NAME)
    intro = part.split("\n## ", 1)[0]
    assert "always in this order, workflows first" in intro
    assert intro.index("**The workflows' pull request:**") < intro.index("**The ruleset change,**")
    assert "once doctor's `merge_group` check is clean on the base branch" in intro
    assert part.index("## Step 1: the workflows' pull request") < part.index("## Step 2: the ruleset change")
    # The ruleset waits for a clean check on the base, read after a fetch.
    where = _sec(part, "Where it stands")
    assert "`git fetch origin <base>`" in where and "`merge_group.clean` is `true`:** the workflows are ready: step 2" in where
    one = _sec(part, "Step 1")
    assert "`merge_group:` beside `pull_request:`" in one
    assert "the owner reviews and merges it" in one and "Never merge it, or enable auto-merge on it, yourself" in one
    assert "go on to step 2 only when `merge_group.clean` is `true`" in one
    # Another CI service, and path-filtered CI: the merge group's base_sha..head_sha.
    assert "`gh-readonly-queue/<base>`" in one
    assert "`base_sha..head_sha`" in one


def test_it_is_never_offered_mid_run_or_outside_an_attended_session():
    part = _part(NAME)
    intro = part.split("\n## ", 1)[0]
    assert "**Only in an attended session, and never while a run is in progress.**" in intro
    assert "`merge_queue.signals.run_in_progress` is `true`, or `null`" in intro
    assert "A ticket session never runs it" in intro and "neither does the conductor" in intro
    assert 'It never runs "Add try-it links" or "Use a merge queue" either.' in _text()


def test_the_settings_are_shown_first_and_chosen_there():
    two = _sec(_part(NAME), "Step 2")
    shown = two.index("**The settings, shown first,**")
    for words in ("`MERGE`", "`ALLGREEN`", "at least 60 minutes (60 with no history) and at most GitHub's 360",
                  "at most 5 entries built and 5 merged at once", "a minimum of 1 entry, and no wait",
                  "\"Require branches to be up to date\" turned off", "`ci.required_checks` unchanged",
                  "**Use these settings** (recommended)", "**Change the timeout**", "**Not now**"):
        assert words in two[shown:], words
    # The settings come before anything is sent or clicked.
    assert shown < two.index("**The update with `gh`,**") < two.index("**The clicks,**")
    assert "made as \"Protect `main`\" makes its change" in two


def test_the_update_uses_the_writer_with_doctors_verdict_and_reads_back():
    two = _sec(_part(NAME), "Step 2")
    order = [
        "`gh api repos/<repo>/rulesets/<id> > .workflow/ruleset.json`",
        "`WF protection --merge-queue .workflow/ruleset.json --doctor .workflow/doctor.json --json",
        "`--timeout <minutes>`",
        "`gh api -X PUT repos/<repo>/rulesets/<id> --input .workflow/queue-request.json`",
        "**The read-back,**",
    ]
    at = [two.index(s) for s in order]
    assert at == sorted(at), order
    assert "Exit 2 is a refusal: nothing was sent, and the clicks would do what it refused, so give none" in two
    assert "a merge_group check that isn't clean, back to step 1; a timeout, back to the settings screen" in two
    assert "**Require merge queue**" in two and "untick **Require branches to be up to date before merging**" in two
    assert "`merge_queue.queue` is `true`" in two


def test_require_these_checks_leaves_up_to_date_alone_with_the_queue():
    part = _part("Require these checks")
    assert '"Require branches to be up to date" on (left as it is when that ruleset has a merge queue, which meets it)' in part
    clicks = _sec(part, "The clicks for the checks")
    assert "unless **Require merge queue** is ticked on that ruleset: then leave \"up to date\" as it is, and give no click for it" in clicks
    back = _sec(part, "Read the checks back")
    assert "the read-back never asks for \"up to date\" there" in back
    local = _sec(part, "The update with `gh`")
    assert "(left as it is when the ruleset has the merge-queue rule)" in local


def test_check_setup_hands_the_offer_to_this_path():
    offers = (KIT / "skills/check-setup/SKILL.md").read_text(encoding="utf-8")
    assert f'Load `upgrade-setup` for "{NAME}" (its offer `use_merge_queue`), from its start' in offers


# ---------- the CI template, the docs, the changelog ----------


def test_the_ci_template_runs_for_the_merge_queue():
    text = (KIT / "templates/github/workflow-kit.yml").read_text()
    on = text.split("\non:\n", 1)[1].split("\n\n", 1)[0]
    assert "\n  pull_request:\n  merge_group:\n" in "\n" + on + "\n"


def test_protection_doc_covers_the_queue_and_require_checks_with_it():
    doc = (KIT / "docs/protection.md").read_text()
    queue = doc.split("### The merge queue", 1)[1]
    assert "workflow protection --merge-queue ruleset.json --doctor doctor.json" in queue
    for words in ("public repository owned by an organization", "GitHub Enterprise Cloud", "\"up to date\" is turned off",
                  "`merge_queue.merge_group.clean`", "360", "`base_sha..head_sha`"):
        assert words in queue, words
    require = doc.split("### Require checks", 1)[1].split("\n### ", 1)[0]
    assert "left as it is when the ruleset has a `merge_queue` rule" in require


def test_the_changelog_notes_it_under_unreleased():
    notes = since_0110()
    unreleased = notes.split("\n## ", 1)[0]
    assert "(#247, part of #243)" in unreleased
    for words in ("--merge-queue", "Use a merge queue", "merge_group", "Merge queue"):
        assert words in unreleased, words
    assert "tests/test_protection_queue.py" in unreleased


# ---------- doctor's require_checks fix with the queue ----------

DEVELOPER = _prof('experience = "developer"\nruleset = true\n', CHECKS)
QUEUE_RULE = {"type": "merge_queue", "parameters": {"merge_method": "MERGE", "grouping_strategy": "ALLGREEN", "check_response_timeout_minutes": 60}}


def _queued():
    import copy

    rs = copy.deepcopy(RULESET)
    rs["rules"].append(QUEUE_RULE)
    _rule(rs, "required_status_checks")["parameters"]["strict_required_status_checks_policy"] = False
    return rs


def test_doctors_require_checks_fix_leaves_up_to_date_alone_with_the_queue(tmp_path):
    ran = [_runs(_run("tests"), _run("lint", n=2))]
    q = _github(_report(tmp_path / "q", _project(tmp_path / "q", profile=DEVELOPER), *_given(tmp_path / "q", ran, rulesets=[_queued()])))
    plain = _github(_report(tmp_path / "p", _project(tmp_path / "p", profile=DEVELOPER), *_given(tmp_path / "p", ran)))
    line, before = q["github.required_checks"], plain["github.required_checks"]
    assert line["offer"] == before["offer"] == "require_checks", (line, before)
    assert '"up to date" left as it is (the merge queue meets it)' in line["fix"] and '"up to date" on' not in line["fix"], line
    assert '"up to date" on' in before["fix"], before


def test_doctors_fix_follows_the_ruleset_holding_the_checks(tmp_path):
    # The queue in a ruleset of its own: "Require these checks" adds to the
    # one holding the checks, which turns "up to date" on, and the fix says so.
    import copy

    alone = copy.deepcopy(RULESET)
    alone.update(id=202, name="Queue only", rules=[QUEUE_RULE])
    ran = [_runs(_run("tests"), _run("lint", n=2))]
    r = _report(tmp_path, _project(tmp_path, profile=DEVELOPER), *_given(tmp_path, ran, rulesets=[RULESET, alone]))
    assert '"up to date" on' in _github(r)["github.required_checks"]["fix"]


# ---------- the round-1 review's fixes ----------


def test_the_description_fits_claude_codes_limit():
    head = _text().split("---", 2)[1]
    description = re.search(r"^description: (.*)$", head, re.M).group(1)
    assert len(description) <= 1024


def test_step_one_opens_nothing_when_nothing_is_the_kits_to_change():
    one = _sec(_part(NAME), "Step 1")
    assert "**Nothing for the kit to change:** when no workflow is `missing` or `excluded`, open no pull request" in one
    assert "the queue can't go on while they are required" in one
    assert "a workflow GitHub runs itself (a `dynamic/` path" in one and "has no file" in one
    # A push refused for want of the workflow scope: the change by hand.
    assert "without the `workflow` scope" in one and "give the owner each change to make by hand" in one
    assert '"The queue waits for <what is left>' in _sec(_part(NAME), "Where the queue ends")


def test_step_two_knows_which_way_before_the_settings_and_shows_the_minutes():
    two = _sec(_part(NAME), "Step 2")
    assert two.index("**Which way:**") < two.index("**The settings, shown first,**")
    assert "with the timeout as a number of minutes" in two
    assert "above the longest recent CI run and at most 360, or 360 itself when CI runs that long: the writer refuses one below" in two
    assert "groups may time out even at 360" in two


def test_require_these_checks_beside_the_queue_needs_merge_group_on_the_new_checks():
    screen = _sec(_part("Require these checks"), "The checks screen")
    assert "**Beside a merge queue**" in screen
    assert "must also come from a workflow that runs on `merge_group`" in screen
    assert "After the read-back, run doctor again" in screen
    assert "one without `merge_group:` beside `pull_request:` gets **Not now** recommended" in screen
    assert "before the check is required" in screen
    assert '(never "up to date" beside a merge queue)' in _part("Require these checks")


def test_enforcement_scopes_up_to_date_to_no_queue():
    doc = (KIT / "docs/enforcement.md").read_text()
    assert "unless the ruleset has a merge queue, which meets it" in doc
    assert "If the owner leaves it off with no merge queue on the base branch, the conductor's pre-flight raises it as a safety gap" in doc
    assert "`strict_required_status_checks_policy` true, or false beside a `merge_queue` rule, which meets it" in doc


def test_a_run_in_progress_stops_before_the_plan_question():
    where = _sec(_part(NAME), "Where it stands")
    assert where.index("**A run in progress**") < where.index("**`available` is `check_plan`:**")


def test_doctors_fix_follows_the_kits_own_ruleset_with_the_queue_and_no_checks_yet(tmp_path):
    # The queue in the kit's own ruleset, the checks in another: "Require these
    # checks" adds to the kit's own, beside its queue, so "up to date" stays off.
    import copy

    own = copy.deepcopy(RULESET)
    own.update(id=303, name="Protect main (pairnexus-workflow)", rules=[r for r in own["rules"] if r["type"] != "required_status_checks"] + [QUEUE_RULE])
    ran = [_runs(_run("tests"), _run("lint", n=2))]
    r = _report(tmp_path, _project(tmp_path, profile=DEVELOPER), *_given(tmp_path, ran, rulesets=[RULESET, own]))
    assert "left as it is (the merge queue meets it)" in _github(r)["github.required_checks"]["fix"]


def test_doctors_fix_with_several_rulesets_follows_the_one_holding_queue_and_checks(tmp_path):
    import copy

    both = _queued()
    both.update(id=404, name="Main rules")
    other = copy.deepcopy(RULESET)
    other.update(id=405, name="Other rules")
    ran = [_runs(_run("tests"), _run("lint", n=2))]
    r = _report(tmp_path, _project(tmp_path, profile=DEVELOPER), *_given(tmp_path, ran, rulesets=[other, both]))
    assert "left as it is (the merge queue meets it)" in _github(r)["github.required_checks"]["fix"]


def test_enforcement_says_merge_check_is_ready_to_queue_with_the_queue():
    doc = (KIT / "docs/enforcement.md").read_text()
    assert "unless a merge queue meets it: then `ready` means ready to queue" in doc
