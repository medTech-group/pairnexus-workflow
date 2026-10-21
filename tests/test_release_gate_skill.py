"""#89: the `release-gate` skill (#36). Seam 2: what a vendored copy and the plugin
contain. Seam 3: the skill's wording, read from its file as the kit-release tests
read skills. And the line the skill writes is the line the check reads: its
example reports, with a commit filled in, go through #88's script."""

from __future__ import annotations

import json
import re

from conftest import KIT

from workflow import vendor
from changelog_notes import since_0110
from test_release_gate import HEAD, _comment, _run

SKILL = KIT / ".claude/skills/release-gate/SKILL.md"
SCRIPT = KIT / ".github/scripts/release_gate.py"
SHA = HEAD  # the head commit of test_release_gate's release pull request

# The checks, in their order. Later tickets insert theirs (#91 after the first,
# #92 after the last) without rewording these.
CHECKS = ["The update with CI green", "The guard's refusal", "The ruleset's refusal"]


def _text():
    return SKILL.read_text(encoding="utf-8")


def _flat(s):
    return re.sub(r"\s+", " ", s)


def _section(title):
    m = re.search(rf"^## [^\n]*{re.escape(title)}[^\n]*\n(.*?)(?=^## |\Z)", _text(), re.M | re.S)
    assert m, f"no section {title!r}"
    return m.group(1)


def _examples():
    """The report section's example reports, in order: the pass, then the fail."""
    return re.findall(r"^```markdown\n(.*?)^```", _section("The gate report"), re.M | re.S)


# ---------- what ships (seam 2) ----------

def test_the_skill_is_the_kit_repositorys_own_and_never_ships():
    assert SKILL.is_file()
    assert not (KIT / "skills/release-gate").exists()
    assert not any("release-gate" in dst for dst in vendor.plan(KIT, None))


def test_the_plugin_takes_only_skills():
    """The plugin's skills are `skills/`: its manifest names no other skill directory."""
    for name in ("plugin.json", "marketplace.json"):
        text = (KIT / ".claude-plugin" / name).read_text()
        assert "release-gate" not in text and ".claude/skills" not in text
    assert "skills" not in json.loads((KIT / ".claude-plugin/plugin.json").read_text())


def test_its_description_loads_it_on_the_ask():
    front = _text().split("---", 2)[1]
    assert "name: release-gate" in front
    assert "run the release gate on PR #N" in front
    assert "disable-model-invocation" not in front


# ---------- the skill's wording (seam 3) ----------

def test_the_candidate_is_the_prs_exact_commit_outside_the_working_tree():
    s = _flat(_section("The candidate"))
    assert "exact commit" in s and "full 40-character SHA" in s and "`VERSION` at it" in s
    assert "outside this session's working tree" in s and "checkout --detach" in s


def test_a_sandbox_branch_with_its_pull_request():
    s = _flat(_section("The sandbox branch"))
    assert "pairnexus-workflow-sandbox" in _text()
    assert '`access: "push"`' in s and "release-gate/$VERSION origin/main" in s
    assert "open the sandbox pull request" in s and "names the candidate commit" in s
    assert "links the release pull request" in s


def test_the_update_goes_through_the_candidates_update_workflow():
    s = _flat(_section("The sandbox branch"))
    assert "`$CAND/skills/update-workflow/SKILL.md`" in s
    assert "`vendor update --kit` pointing at the candidate's checkout" in s
    assert 'vendor update --kit "$CAND"' in s
    assert "pinned SHA" in s and "marketplace.json" in s


def test_every_update_workflow_command_runs_on_the_sandbox():
    """Without them, `profile check` and the rest find the session's checkout, the kit's own."""
    s = _flat(_section("The sandbox branch"))
    assert 'Every one of its commands runs on the sandbox' in s
    assert 'CLAUDE_PROJECT_DIR="$SANDBOX"' in s and 'vendor verify --project "$SANDBOX"' in s
    assert "with `KIT` as `$CAND`" in s
    assert "every file it names (`CLAUDE.md`, `.github/…`, the profile) is the one under `$SANDBOX`" in s


def test_a_renamed_version_file_counts_as_a_release_pr():
    assert ".previous_filename // empty" in _section("The candidate")


def test_a_run_on_a_newer_commit_starts_afresh_and_posts_a_new_report():
    s = _flat(_section("The sandbox branch"))
    assert "A run on a newer commit starts afresh" in s
    assert "Close every open sandbox pull request whose branch starts with `release-gate/`" in s
    assert "issues/<earlier PR>/comments" in s and "pulls/<earlier PR> -f state=closed" in s
    # Deleted whenever it exists, or a closed pull request's branch refuses the new push.
    assert "whenever `release-gate/$VERSION` exists on the sandbox" in s and "git/refs/heads/release-gate/$VERSION" in s
    assert "A run on a newer commit posts a new report**; the old ones stay" in _section("The gate report")


def test_the_checks_run_in_order_as_one_numbered_list():
    """The numbered list is consecutive, and CI, the guard's refusal and the ruleset's
    refusal come in that order, wherever later tickets add theirs."""
    s = _section("The checks, in order")
    items = re.findall(r"^(\d+)\. \*\*([^*]+?)\.\*\*", s, re.M)
    assert [int(n) for n, _ in items] == list(range(1, len(items) + 1))
    names = [name for _, name in items]
    assert [n for n in names if n in CHECKS] == CHECKS


def test_each_check_says_what_passes_and_its_evidence():
    s = _flat(_section("The checks, in order"))
    assert "`ci.required_checks`" in s and "the CI run's link" in s
    assert "`create_session`" in s and "`run.ticket_environment`" in s and "`list_environments`" in s
    assert "release-gate/$VERSION" in s and "push it to main" in s
    assert "`main` is unchanged" in s and "before and after" in s and "transcript's link" in s
    assert "throwaway clone outside any checkout with the kit's hooks" in s
    assert "repository rule violation" in s and "the push's output" in s


def test_it_refuses_a_fork_a_strange_version_and_a_pr_not_changing_version():
    s = _flat(_section("The candidate"))
    assert ".head.repo.full_name" in s and "isn't `$KIT_REPO` (a fork)" in s
    assert "`VERSION` isn't three numbers" in s and "doesn't change `VERSION`" in s


def test_the_ruleset_push_never_leaves_the_throwaway_clone():
    """No `cd`: a shell that falls back to the session's checkout would commit there and push
    the kit's own `main`, whose ruleset would refuse it as a false pass."""
    s = _section("The checks, in order")
    block = s[s.index("**The ruleset's refusal.**"):]
    block = re.search(r"```bash\n(.*?)```", block, re.S).group(1)
    assert "cd " not in block
    commands = [line for line in block.splitlines() if line.strip().startswith("git ")]
    assert commands and all('git -C "$T/clone"' in c for c in commands)
    assert "push https://github.com/<sandbox> HEAD:main" in block


def test_the_guards_refusal_is_for_the_base_branch_and_leaves_the_head_alone():
    s = _flat(_section("The checks, in order"))
    assert "pushing to the base branch `main` is never allowed" in s and "doesn't count" in s
    assert "is still at `<head>`" in s


def test_ci_is_judged_only_once_checks_have_run():
    s = _flat(_section("The checks, in order"))
    assert "at least one check has run" in s and "`success`, `neutral` or `skipped`" in s


def test_a_failed_check_stops_the_gate_and_closes_the_sandbox_pr():
    s = _flat(_section("The checks, in order"))
    assert "A failed check stops the gate" in s and "close the sandbox pull request" in s
    assert "issues/<sandbox PR>/comments" in s and "pulls/<sandbox PR> -f state=closed" in s
    assert "A failure in this section" in _section("The sandbox branch") and "failure of the first check" in _section("The sandbox branch")
    r = _flat(_section("The gate report"))
    assert "After a fail, it is closed" in r and "After a pass, the sandbox pull request stays open" in r


def test_the_report_has_its_table_version_marker_and_line_last():
    r = _flat(_section("The gate report"))
    assert "(check | result | evidence)" in r and "the Claude Code version" in r
    assert "`<!-- workflow:agent -->`" in r and "machine-readable line" in r
    assert "ordinary pull request comment" in r and "never a review comment" in r
    assert "read the pull request's head again" in r
    assert "`claude --version`" in _section("The candidate")
    for ex in _examples():
        rows = re.findall(r"^\| (The [^|]+?) \|", ex, re.M)
        assert [x for x in rows if x in CHECKS] == CHECKS
        assert "Claude Code version: " in ex and "<!-- workflow:agent -->" in ex
        assert re.search(r"release-gate: (pass|fail) <full sha>\n\Z", ex)


# ---------- finishing the gate (#90) ----------

# Its steps, in their order (#90's acceptance criteria).
FINISH = [
    "The release exists",
    "The sandbox pull request",
    "The update from the tag",
    "Files unchanged apart from the lock's source and version",
    "The description names the release",
    "CI green",
    "A merge commit",
]


def _finish_steps():
    """The finishing section's numbered steps, in order: (number, name, its text up to the next step)."""
    s = _section("Finishing the gate")
    parts = re.split(r"^(\d+)\. \*\*([^*]+?)\.\*\*", s, flags=re.M)
    return [(int(n), name, _flat(body)) for n, name, body in zip(parts[1::3], parts[2::3], parts[3::3])]


def _finish_step(name):
    return {n: body for _, n, body in _finish_steps()}[name]


def test_finishing_is_asked_for_by_name():
    front = _text().split("---", 2)[1]
    assert "finish the release gate" in front
    assert "once the release has published" in _flat(_section("Finishing the gate"))


def test_finishing_runs_its_steps_in_order():
    steps = _finish_steps()
    assert [n for n, _, _ in steps] == list(range(1, len(steps) + 1))
    assert [name for _, name, _ in steps] == FINISH


def test_finishing_stops_without_a_release():
    body = _finish_step("The release exists")
    assert "releases/tags/v$VERSION" in body and "not merely a tag" in body
    assert "hasn't published yet and stop" in body
    assert "`VERSION` isn't three numbers" in body
    assert "merge_commit_sha" in body and "has no release: stop" in body  # asked for the release pull request #N
    assert "Given neither, ask the owner which version" in _flat(_section("Finishing the gate"))


def test_a_closed_or_missing_sandbox_pr_stops_it():
    body = _finish_step("The sandbox pull request")
    assert "state=all&head=medTech-group:release-gate/$VERSION" in body
    assert body.index('`access: "push"`') < body.index("pulls?state=all")  # the sandbox reachable first
    assert "there's none" in body and "closed and merged" in body and "closed and not merged" in body
    assert "a later version's gate run did" in body and "Stop, saying why" in body
    assert "Finish a version before running the gate for the next one" in _flat(_section("Finishing the gate"))


def test_the_update_comes_from_the_release_tag_as_the_candidate_was_applied():
    body = _finish_step("The update from the tag")
    assert 'checkout --detach "v$VERSION"' in body and "outside the working tree" in body
    assert 'vendor update --kit "$REL" --project "$SANDBOX"' in body and "--strict-pin" in body
    assert 'CLAUDE_PROJECT_DIR="$SANDBOX"' in body
    assert "pinned SHA" in body and "$REL/.claude-plugin/marketplace.json" in body


def test_any_other_changed_file_stops_it_loudly_naming_the_files():
    body = _finish_step("Files unchanged apart from the lock's source and version")
    assert "`kit_sha`" in body and "`kit_version`" in body
    assert 'git -C "$SANDBOX" status --porcelain' in body and "del(.kit_sha, .kit_version)" in body
    assert "stop loudly" in body and "name every file that differs" in body
    assert "Push nothing, leave the sandbox pull request open" in body
    assert "never touch the sandbox's `main`" in body


def test_the_description_names_the_release_and_keeps_its_lists():
    description = _finish_step("The description names the release")
    assert "holds release `v$VERSION`" in description and "pulls/<sandbox PR> -f title=" in description
    assert "keeps the earlier description's `kept` files and conflicts" in description


def test_ci_is_judged_as_the_gates_first_check():
    ci = _finish_step("CI green")
    assert "section 3's first check" in ci and "leave the sandbox pull request open" in ci


def test_the_merge_is_a_merge_commit_pinned_to_the_head():
    assert "merge_method=merge -f sha=<head>" in _finish_step("A merge commit")


def test_the_merge_is_pinned_to_the_pushed_commit_once_the_pr_shows_it():
    """The PATCH's answer can still carry the old head: CI would read as green at once and
    the pinned merge would be refused."""
    description = _finish_step("The description names the release")
    assert 'git -C "$SANDBOX" rev-parse HEAD` prints `<head>`, the pushed commit' in description
    assert "`<head>` is then step 2's current head" in description
    assert "read the pull request's head until it is `<head>`" in description
    assert "Skip both when step 4's first command listed nothing" in description
    assert "after 10 minutes, stop" in description


def test_matt_pococks_skills_follow_the_branchs_lock():
    """A sandbox that declined them must not get them, or step 4 stops on a release that's fine."""
    body = _finish_step("The update from the tag")
    assert "follow the branch's lock" in body and "records a `mattpocock_sha`" in body
    assert "without `--mattpocock <checkout> --strict-pin`" in body
    assert "candidate commit the gate tried" in body
    assert "an earlier finish pushed and then stopped" in body  # a re-run reads the candidate elsewhere
    assert "someone pushed to the branch since step 2: stop" in body


def test_finishing_never_touches_main_but_by_the_merge_nor_spike():
    s = _flat(_section("Finishing the gate"))
    assert "touches the sandbox's `main` only through that pull request's merge" in s
    assert "A stop never merges and never touches the sandbox's `main`" in s
    assert "never touches `docs/spike.md`" in s and "changes only when a row's status does" in s


def test_the_gate_report_points_to_finishing():
    assert "when the gate is finished (section 5)" in _flat(_section("The gate report"))


def test_contributing_ends_the_release_section_with_finishing():
    c = _flat((KIT / "CONTRIBUTING.md").read_text())
    assert "finish the release gate" in c
    # The release section's last paragraph, after running, skipping and changing the check.
    gate = c[c.index("**Running the gate.**"):c.index("**The kit's home.**")]
    last = gate[gate.index("**Finishing the gate"):]
    assert "**Skipping the gate" not in last and "A change to the check's own workflow" not in last
    assert "after the release publishes" in last and "sandbox pull request" in last


# ---------- the line the skill writes is the line the check reads ----------

def _check(tmp_path, report):
    """#88's script on a release pull request whose one comment is `report`, by an admin."""
    return _run(tmp_path, comments=[_comment(report)])


def test_the_example_pass_reads_as_a_pass_for_its_commit(tmp_path):
    passed, _ = _examples()
    code, out = _check(tmp_path, passed.replace("<full sha>", SHA))
    assert code == 0 and out.startswith("pass: ") and SHA in out, out


def test_the_example_pass_for_another_commit_counts_for_nothing(tmp_path):
    passed, _ = _examples()
    code, out = _check(tmp_path, passed.replace("<full sha>", "b" * 40))
    assert code == 1 and out.startswith("fail: "), out


def test_the_example_fail_reads_as_a_fail(tmp_path):
    _, failed = _examples()
    code, out = _check(tmp_path, failed.replace("<full sha>", SHA))
    assert code == 1 and out.startswith("fail: ") and "failed for the head commit" in out, out


# ---------- docs ----------

def test_contributing_says_how_to_run_the_gate_and_that_claude_skills_never_ships():
    c = _flat((KIT / "CONTRIBUTING.md").read_text())
    assert "run the release gate on PR #N" in c and "about 30 minutes" in c
    assert "ticket environment" in c and "#89 says how" not in c
    assert "own `.claude/skills/` is for maintainers and never ships" in c
    assert "kit-only `release-gate` skill" in (KIT / "CLAUDE.md").read_text()


def test_spike_says_the_gate_re_proves_rows_4_and_5():
    s = _flat((KIT / "docs/spike.md").read_text())
    assert "re-proves rows 4 (the push) and 5 at every release" in s
    assert "Update it whenever one of these is checked again" not in s
    assert "changes only when a row's status does" in s


def test_the_changelog_note_and_no_version_bump():
    text = (KIT / "CHANGELOG.md").read_text()
    assert "(#89," in since_0110(text) and "`release-gate`" in since_0110(text)
    assert "(#90," in since_0110(text) and "finish the release gate" in since_0110(text)
    latest_release = text.split("\n## ")[2].split()[0].lstrip("v")  # the heading after "## Unreleased"
    assert (KIT / "VERSION").read_text().strip() == latest_release
