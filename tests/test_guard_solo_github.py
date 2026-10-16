"""Solo mode (#46): with `ruleset = false`, an attended session's GitHub-side
changes to the base branch are refused (deny, never ask), worded by experience:
`gh pr merge --admin`, the default branch, the base branch's name and
protection, rulesets, and the GitHub MCP tools' writes. Creating a ruleset is
still asked: it is how a project leaves solo mode.

Every command here is data passed to `decide` or the hook; none is run.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from workflow.guard import decide
from workflow.profile import load

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"
MAIN_LINE = "`main` is the branch the project's work comes together on"
REFUSED_LINE = "Without GitHub's protection set up, the kit doesn't allow that"
OFFER = 'Offer "Protect `main`" as a choice, with "Not now"'
API = "https://api.github.com/repos/acme/demo"


def bash(cmd, cwd=None):
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}}
    if cwd is not None:
        ev["cwd"] = str(cwd)
    return ev


def mcp(name, inp):
    return {"tool_name": f"mcp__github__{name}", "tool_input": inp}


def _toml(ruleset):
    line = "" if ruleset is None else f"ruleset = {'true' if ruleset else 'false'}\n"
    return f"""
[project]
name = "demo"
repo = "acme/demo"
base_branch = "main"
{line}
[guard]
deploy_commands = ["scripts/deploy.sh"]
"""


def on_disk(root: Path, ruleset):
    (root / ".claude/workflow").mkdir(parents=True, exist_ok=True)
    (root / ".claude/workflow/profile.toml").write_text(_toml(ruleset))
    return load(root)


@pytest.fixture(autouse=True)
def _session_env(monkeypatch):
    monkeypatch.delenv("WORKFLOW_EXPERIENCE", raising=False)
    monkeypatch.delenv("WORKFLOW_ROLE", raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def solo(tmp_path):
    return on_disk(tmp_path, False)


def act(profile, event, role="attended", branch="feature"):
    if isinstance(event, str):
        event = bash(event)
    return decide(event, profile, role, profile.root, branch)


# ---------- refused through the shell ----------

GQL = "gh api graphql -f query='mutation {{ {m}(input: {{id: X}}) {{ clientMutationId }} }}'"

REFUSED_BASH = [
    # gh pr merge --admin
    "gh pr merge 12 --admin",
    "gh pr merge --merge --admin 12",
    "gh pr merge 12 --admin=true",
    # the default branch and the base branch's name
    "gh repo edit --default-branch trunk",
    "gh repo edit acme/demo --default-branch=trunk",
    "gh api -X PATCH repos/acme/demo -f default_branch=trunk",
    "gh api -X POST repos/acme/demo/branches/main/rename -f new_name=trunk",
    # protection writes
    "gh api -X PUT repos/acme/demo/branches/main/protection --input p.json",
    "gh api -X DELETE repos/acme/demo/branches/main/protection",
    "gh api -X DELETE repos/{owner}/{repo}/branches/main/protection/enforce_admins",
    "gh api --method POST repos/acme/demo/branches/main/protection/required_status_checks/contexts -f contexts[]=x",
    # rulesets: PUT, PATCH, DELETE
    "gh api -X PUT repos/acme/demo/rulesets/42 --input r.json",
    "gh api -X PATCH repos/acme/demo/rulesets/42 -f enforcement=disabled",
    "gh api -X DELETE repos/acme/demo/rulesets/42",
    "gh api --method=DELETE /repos/{owner}/{repo}/rulesets/42",
    "gh api -X DELETE orgs/acme/rulesets/7",
    # the base branch's ref, merges and contents
    "gh api -X PATCH repos/acme/demo/git/refs/heads/main -f sha=abc -F force=true",
    "gh api -X DELETE repos/acme/demo/git/refs/heads/main",
    "gh api repos/acme/demo/merges -f base=main -f head=feature",
    "gh api -X PUT repos/acme/demo/contents/README.md -f message=m -f content=eA==",
    "gh api -X PUT repos/acme/demo/contents/README.md -f message=m -f content=eA== -f branch=main",
    # curl
    f"curl -X PUT {API}/rulesets/42 -d @r.json",
    f"curl -X PATCH {API}/rulesets/42 -d '{{}}'",
    f"curl -sX DELETE {API}/rulesets/42",
    f"curl --request DELETE {API}/rulesets/42",
    f"curl --request=DELETE {API}/rulesets/42",
    f"curl -XDELETE {API}/rulesets/42",
    f"curl -X DELETE -H 'Authorization: token abc' {API}/branches/main/protection",
    f"curl -X PUT {API}/branches/main/protection -d @p.json",
    f"curl -T p.json {API}/branches/main/protection",
    f"curl -X PATCH {API} -d '{{\"default_branch\": \"trunk\"}}'",
    f"curl -X POST {API}/branches/main/rename -d '{{\"new_name\": \"trunk\"}}'",
    f"curl -X DELETE {API}/git/refs/heads/main",
    "curl -X DELETE https://ghe.example.com/api/v3/repos/acme/demo/rulesets/42",
    # GraphQL
    GQL.format(m="deleteRepositoryRuleset"),
    GQL.format(m="updateRepositoryRuleset"),
    GQL.format(m="deleteBranchProtectionRule"),
    GQL.format(m="updateBranchProtectionRule"),
    GQL.format(m="createBranchProtectionRule"),
    GQL.format(m="updateRef"),
    GQL.format(m="deleteRef"),
    GQL.format(m="mergeBranch"),
    "curl -X POST https://api.github.com/graphql -d '{\"query\": \"mutation { deleteRepositoryRuleset(input: {id: X}) { clientMutationId } }\"}'",
    # wrapped, or after something else
    "echo hi; gh pr merge 12 --admin",
    "sh -c 'gh api -X DELETE repos/acme/demo/rulesets/42'",
]


@pytest.mark.parametrize("cmd", REFUSED_BASH)
def test_refused_in_solo_mode(cmd, solo):
    d = act(solo, cmd)
    assert d.action == "deny", cmd
    assert REFUSED_LINE in d.reason, cmd


def test_graphql_from_a_file_it_reads(solo):
    (solo.root / "q.graphql").write_text("mutation { deleteRepositoryRuleset(input: {id: X}) { clientMutationId } }\n")
    (solo.root / "q.json").write_text(json.dumps({"query": "mutation { updateRepositoryRuleset(input: {id: X}) { clientMutationId } }"}))
    for cmd in (
        "gh api graphql -F query=@q.graphql",
        'Q=$(cat q.graphql); gh api graphql -f query="$Q"',
        "curl -X POST https://api.github.com/graphql -d @q.json",
        "curl https://api.github.com/graphql --data-binary @q.json",
    ):
        assert act(solo, bash(cmd, solo.root)).action == "deny", cmd


def test_contents_and_merges_name_the_base_in_a_body_file(solo):
    (solo.root / "c.json").write_text(json.dumps({"message": "m", "content": "eA==", "branch": "main"}))
    (solo.root / "f.json").write_text(json.dumps({"message": "m", "content": "eA==", "branch": "feature"}))
    assert act(solo, bash(f"curl -X PUT {API}/contents/a.md -d @c.json", solo.root)).action == "deny"
    assert act(solo, bash(f"curl -X PUT {API}/contents/a.md -d @f.json", solo.root)).action == "allow"


@pytest.mark.parametrize(
    "cmd",
    [
        'gh api -X PUT "repos/acme/demo/branches/$B/protection" --input p.json',
        'gh api -X "$M" repos/acme/demo/rulesets/42',
        f'curl -X "$M" {API}/rulesets/42',
        f"curl -K opts.cfg {API}/rulesets/42",
        f'curl -X PATCH "{API}/git/refs/heads/$B" -d @r.json',
    ],
)
def test_cant_tell_counts_as_the_base_branch(cmd, solo):
    d = act(solo, cmd)
    assert d.action == "deny", cmd
    assert "can't tell" in d.reason, cmd


# ---------- still asked: creating a ruleset ----------

ASKED = [
    "gh api -X POST repos/acme/demo/rulesets --input r.json",
    "gh api repos/acme/demo/rulesets --input r.json",
    "gh api --method POST /repos/{owner}/{repo}/rulesets -f name=protect-main",
    f"curl -X POST {API}/rulesets -d @r.json",
    f"curl {API}/rulesets -d @r.json",
    f"curl --json @r.json {API}/rulesets",
    GQL.format(m="createRepositoryRuleset"),
]


@pytest.mark.parametrize("cmd", ASKED)
def test_creating_a_ruleset_is_asked(cmd, solo):
    d = act(solo, cmd)
    assert d.action == "ask", cmd
    assert REFUSED_LINE not in d.reason


# ---------- not about the base branch: as before ----------

UNCHANGED = {
    "gh pr merge 12 --merge": "allow",
    "gh pr merge 12 --auto --merge": "allow",
    "gh repo edit --enable-auto-merge": "allow",
    "gh api -X PATCH repos/acme/demo -f allow_auto_merge=true": "allow",
    f"curl -X PATCH {API} -d '{{\"allow_auto_merge\": true}}'": "allow",
    "gh api repos/acme/demo/rulesets": "allow",
    "gh api repos/acme/demo/branches/main/protection": "allow",
    f"curl {API}/rulesets": "allow",
    f"curl -H 'Accept: application/json' {API}/branches/main/protection": "allow",
    "gh api -X DELETE repos/acme/demo/git/refs/heads/feature": "allow",
    "gh api -X PUT repos/acme/demo/contents/a.md -f message=m -f content=eA== -f branch=feature": "allow",
    f"curl -X DELETE {API}/git/refs/heads/feature": "allow",
    "gh api -X PUT repos/acme/demo/branches/feature/protection --input p.json": "ask",
    "gh api graphql -f query='mutation { addComment(input: {subjectId: X, body: hi}) { clientMutationId } }'": "allow",
    "gh api graphql -f query='mutation { updateRepository(input: {repositoryId: X, hasWikiEnabled: false}) { clientMutationId } }'": "ask",
}


@pytest.mark.parametrize("cmd,expected", list(UNCHANGED.items()))
def test_not_about_the_base_branch_unchanged_in_solo_mode(cmd, expected, solo):
    assert act(solo, cmd).action == expected, cmd


# Today's attended decisions, with `ruleset = true` or no setting.
TODAY_ATTENDED = {
    **{c: "ask" for c in REFUSED_BASH if not c.startswith("curl ")},
    **{c: "allow" for c in REFUSED_BASH if c.startswith("curl ")},
    **{c: "ask" for c in ASKED if not c.startswith("curl ")},
    **{c: "allow" for c in ASKED if c.startswith("curl ")},
    **UNCHANGED,
}


@pytest.mark.parametrize("cmd,expected", list(TODAY_ATTENDED.items()))
def test_ruleset_true_and_unset_give_todays_decisions(cmd, expected, tmp_path):
    protected = on_disk(tmp_path / "a", True)
    unset = on_disk(tmp_path / "b", None)
    a, b = act(protected, cmd), act(unset, cmd)
    assert (a.action, a.reason) == (b.action, b.reason), cmd
    assert a.action == expected, cmd
    assert REFUSED_LINE not in a.reason


@pytest.mark.parametrize("role", ["ticket", "conductor"])
@pytest.mark.parametrize("cmd", list(TODAY_ATTENDED))
def test_ticket_and_conductor_unchanged_in_solo_mode(role, cmd, tmp_path):
    solo = on_disk(tmp_path / "solo", False)
    unset = on_disk(tmp_path / "unset", None)
    a = act(solo, cmd, role=role, branch="claude/build-1")
    b = act(unset, cmd, role=role, branch="claude/build-1")
    assert (a.action, a.reason) == (b.action, b.reason), cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "gh api -X PUT repos/other/thing/branches/main/protection --input p.json",
        "gh api -X DELETE repos/other/thing/rulesets/42",
        "gh api -X DELETE orgs/other/rulesets/7",
        "gh pr merge 3 --admin -R other/thing",
        "gh pr merge https://github.com/other/thing/pull/3 --admin",
        "gh repo edit other/thing --default-branch trunk",
        "curl -X DELETE https://api.github.com/repos/other/thing/rulesets/42",
    ],
)
def test_another_repository_is_not_refused(cmd, solo, tmp_path):
    unset = on_disk(tmp_path / "unset", None)
    a, b = act(solo, cmd), act(unset, cmd)
    assert (a.action, a.reason) == (b.action, b.reason), cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "gh pr merge 3 --admin -R acme/demo",
        "gh pr merge 3 --admin --repo=ACME/Demo",
        'gh pr merge 3 --admin -R "$R"',
        "gh repo edit acme/demo --default-branch trunk",
        "gh api -X DELETE repos/ACME/demo/rulesets/42",
        "gh api -X DELETE orgs/acme/rulesets/7",
        "gh api -X DELETE repos/acme/demo/git/refs/heads/Main",
        f"env curl -X DELETE {API}/rulesets/42",
        f"sudo curl -X DELETE {API}/rulesets/42",
    ],
)
def test_the_project_named_any_way_is_refused(cmd, solo):
    assert act(solo, cmd).action == "deny", cmd


@pytest.mark.parametrize("cmd", [f"env curl -X POST {API}/rulesets -d @r.json", f"timeout 5 curl {API}/rulesets -d @r.json"])
def test_a_wrapped_curl_ruleset_create_is_asked(cmd, solo):
    assert act(solo, cmd).action == "ask", cmd


def test_mcp_on_another_repository_is_not_refused(solo, tmp_path):
    unset = on_disk(tmp_path / "unset", None)
    for name, inp in [
        ("create_or_update_file", {"owner": "other", "repo": "thing", "path": "a", "branch": "main", "content": "x", "message": "m"}),
        ("update_ref", {"owner": "other", "repo": "thing", "ref": "heads/main", "sha": "abc"}),
    ]:
        a, b = act(solo, mcp(name, inp)), act(unset, mcp(name, inp))
        assert (a.action, a.reason) == (b.action, b.reason), name
    assert act(solo, mcp("update_ref", {"owner": "ACME", "repo": "demo", "ref": "heads/main", "sha": "abc"})).action == "deny"


# ---------- review round 1: what gh and curl really send ----------

SENT = [
    # every URL curl is given
    f"curl -X DELETE https://api.github.com/zen {API}/rulesets/42",
    f"curl https://api.github.com/zen --next -X DELETE {API}/rulesets/42",
    f"curl -X DELETE --url https://api.github.com/zen --url {API}/rulesets/42",
    # repeated fields: any value counts
    "gh api -X PUT repos/acme/demo/contents/a.md -f message=m -f content=eA== -f branch=feature -f branch=main",
    f"curl -X PUT {API}/contents/a.md -d '{{\"message\":\"m\",\"content\":\"eA==\",\"branch\":\"feature\",\"branch\":\"main\"}}'",
    # dot segments, globs, encodings
    f"curl -X DELETE {API}/x/../rulesets/42",
    f'curl -X DELETE "{API}/{{rulesets/42,zen}}"',
    f'curl -X PUT "{API}/branches/main/protectio[n-n]" -d @p.json',
    f"curl -X DELETE {API}/%72ulesets/42",
    "gh api -X DELETE repos/acme/demo/x/../rulesets/42",
    # abbreviations, curl variables, config files
    f"curl --req DELETE {API}/rulesets/42",
    f"curl --reque=DELETE {API}/rulesets/42",
    f"curl --variable U={API}/rulesets/42 -X DELETE --expand-url '{{{{U}}}}'",
    "curl -K missing.cfg https://api.github.com/zen",
    # paths the shell fills in, and xargs
    'P=repos/acme/demo/rulesets/42; gh api -X DELETE "$P"',
    'gh api -X DELETE "repos/acme/demo/branches/main/$W"',
    f'curl -X DELETE "$U/rulesets/42"',
    "echo repos/acme/demo/rulesets/42 | xargs gh api -X DELETE",
    f"echo {API}/rulesets/42 | xargs curl -X DELETE",
    # bodies the kit can't read
    "printf x > b.json; gh api -X PATCH repos/acme/demo --input b.json",
    'gh api -X PATCH repos/acme/demo -f "default_$X=trunk"',
    # gh aliases
    "gh alias set m 'pr merge --admin' && gh m 12",
    "gh alias set d 'api -X DELETE repos/acme/demo/rulesets/42'",
    # merge-upstream, GHE GraphQL
    "gh api repos/acme/demo/merge-upstream -f branch=main",
    f"curl -X POST {API}/merge-upstream -d '{{\"branch\":\"main\"}}'",
    "gh api https://ghe.example.com/api/graphql -f query='mutation { deleteRepositoryRuleset(input: {id: X}) { clientMutationId } }'",
]


@pytest.mark.parametrize("cmd", SENT)
def test_what_is_really_sent_is_read(cmd, solo):
    assert act(solo, bash(cmd, solo.root)).action == "deny", cmd


def test_bodies_and_files_as_gh_and_curl_send_them(solo):
    root = solo.root
    (root / "c.json").write_text(json.dumps({"message": "m", "content": "eA==", "branch": "main"}))
    (root / "b.txt").write_text("main\n")
    (root / "q.json").write_text('{"query":"mutation{delete\\u0052epositoryRuleset(input:{id:\\"X\\"}){clientMutationId}}"}')
    (root / "d.json").write_text('{"default\\u005fbranch":"trunk"}')
    (root / "gh.cfg").write_text(f"url = {API}/rulesets/42\nrequest = DELETE\n")
    (root / "plain.cfg").write_text("silent\n")
    for cmd in (
        "gh api -X PUT repos/acme/demo/contents/a.md -f branch=feature --input c.json",
        "gh api repos/acme/demo/merges -f head=feature -F base=@b.txt",
        "gh api -X PUT repos/acme/demo/contents/a.md -f message=m -f content=eA== -F branch=@b.txt",
        """echo '{"branch":"feature"}'; curl -X PUT """ + API + "/contents/a.md -d @c.json",
        "gh api graphql --input q.json",
        "curl -X POST https://api.github.com/graphql -d @q.json",
        f"curl -X PATCH {API} -d @d.json",
        "curl -K gh.cfg https://api.github.com/zen",
        "curl -K gh.cfg",
    ):
        assert act(solo, bash(cmd, root)).action == "deny", cmd
    assert act(solo, bash("curl -K plain.cfg https://example.com/x -d a=b", root)).action == "allow"


def test_gh_alias_from_its_config(solo, monkeypatch, tmp_path):
    d = tmp_path / "ghcfg"
    d.mkdir()
    (d / "config.yml").write_text("aliases:\n    m: pr merge --admin\n    s: '!gh pr merge --admin'\n    v: pr view\ngit_protocol: https\n")
    monkeypatch.setenv("GH_CONFIG_DIR", str(d))
    assert act(solo, "gh m 12").action == "deny"
    assert act(solo, "gh s 12").action == "deny"
    assert act(solo, "gh v 12").action == "allow"
    assert act(solo, "gh some-extension run").action == "allow"


@pytest.mark.parametrize(
    "cmd",
    [
        "cat docs/notes.md; gh api graphql -f query='{ viewer { login } }'",
        "gh api graphql -f query='query { repository(owner: \"acme\", name: \"demo\") { name } }' # mergeBranch",
        "gh alias set v 'pr view'",
        f"curl -X POST https://example.com/hook -d @r.json",
        'curl -X POST "$WEBHOOK" -d @r.json',
        "gh api -X PUT repos/acme/demo/branches/release/main/protection --input p.json",
    ],
)
def test_round_1_not_refused(cmd, solo):
    (solo.root / "docs").mkdir(exist_ok=True)
    (solo.root / "docs/notes.md").write_text("updateRef and deleteRef are refused\n")
    assert act(solo, bash(cmd, solo.root)).action != "deny", cmd


def test_a_base_branch_with_a_slash(tmp_path):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(_toml(False).replace('"main"', '"release/main"'))
    prof = load(tmp_path)
    for cmd in (
        "gh api -X PUT repos/acme/demo/branches/release/main/protection --input p.json",
        "gh api -X DELETE repos/acme/demo/git/refs/heads/release/main",
        "gh api -X POST repos/acme/demo/branches/release%2Fmain/rename -f new_name=x",
    ):
        assert act(prof, cmd).action == "deny", cmd
    assert act(prof, "gh api -X PUT repos/acme/demo/branches/main/protection --input p.json").action == "ask"


@pytest.mark.parametrize(
    "name,inp",
    [
        ("delete_branch", {"owner": "acme", "repo": "demo", "name": "main"}),
        ("delete_branch", {"owner": "acme", "repo": "demo"}),
        ("update_ref", {"owner": "acme", "repo": "demo", "sha": "abc"}),
        ("push_files", {"owner": "acme", "repo": "demo", "branch": ["main"], "files": [], "message": "m"}),
    ],
)
def test_mcp_without_a_readable_ref(name, inp, solo):
    assert act(solo, mcp(name, inp)).action == "deny", (name, inp)


# ---------- review round 1: the explorer ----------


@pytest.mark.parametrize(
    "cmd",
    [
        "A=--admin; gh pr merge 1 $A",
        "gh pr merge 1 --admin -R someone/other -R acme/demo",
        "curl -L -X DELETE api.github.com/repos/acme/demo/rulesets/1",
        "curl -X DELETE api.github.com/repos/acme/demo/rulesets/1",
        "U=https://api.github.com/repos/acme/demo/rulesets/1; curl -X DELETE $U",
        'gh api graphql -f query="$Q"',
        "gh api graphql -F query=@missing.graphql",
        "curl -X POST https://api.github.com/graphql -d @missing.json",
    ],
)
def test_explorer_round_1_refused(cmd, solo):
    assert act(solo, bash(cmd, solo.root)).action == "deny", cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "curl -X DELETE https://example.com/repos/acme/demo/rulesets/1",
        "curl -X DELETE http://localhost:3000/repos/acme/demo/rulesets/1",
        "gh api graphql -f query='query($o: String!) { repositoryOwner(login: $o) { login } }' -f o=acme",
        "gh pr merge 1 --admin -R acme/demo -R someone/other",
    ],
)
def test_explorer_round_1_not_refused(cmd, solo):
    assert act(solo, bash(cmd, solo.root)).action != "deny", cmd


def test_mcp_hand_command_is_quoted(solo):
    inp = {"owner": "acme", "repo": "demo", "path": "a b/$(whoami).txt", "branch": "main", "content": "x", "message": "m"}
    r = act(solo, mcp("create_or_update_file", inp)).reason
    assert "'repos/acme/demo/contents/a b/$(whoami).txt'" in r


def test_mcp_new_repository_with_a_default_branch_is_not_refused(solo):
    assert act(solo, mcp("create_repository", {"name": "new", "default_branch": "main"})).action == "allow"


def test_an_earlier_ask_never_hides_a_later_refusal(solo):
    cmd = "gh api -X PUT repos/acme/demo/branches/feature/protection --input p.json; gh api -X DELETE repos/acme/demo/rulesets/42"
    assert act(solo, cmd).action == "deny"
    cmd = f"curl -X POST {API}/rulesets -d @r.json && gh pr merge 3 --admin"
    assert act(solo, cmd).action == "deny"


# ---------- the GitHub MCP tools ----------

REFUSED_MCP = [
    ("create_or_update_file", {"owner": "acme", "repo": "demo", "path": "README.md", "branch": "main", "content": "x", "message": "m"}),
    ("create_or_update_file", {"owner": "acme", "repo": "demo", "path": "README.md", "content": "x", "message": "m"}),
    ("push_files", {"owner": "acme", "repo": "demo", "branch": "main", "files": [{"path": "a", "content": "x"}], "message": "m"}),
    ("push_files", {"owner": "acme", "repo": "demo", "branch": "refs/heads/main", "files": [], "message": "m"}),
    ("delete_file", {"owner": "acme", "repo": "demo", "branch": "main", "path": "a", "message": "m"}),
    ("update_ref", {"owner": "acme", "repo": "demo", "ref": "heads/main", "sha": "abc", "force": True}),
    ("update_ref", {"owner": "acme", "repo": "demo", "ref": "refs/heads/main", "sha": "abc"}),
    ("delete_branch", {"owner": "acme", "repo": "demo", "branch": "main"}),
    ("delete_ref", {"owner": "acme", "repo": "demo", "ref": "heads/main"}),
    ("create_branch", {"owner": "acme", "repo": "demo", "branch": "main", "from_branch": "feature"}),
    ("rename_branch", {"owner": "acme", "repo": "demo", "branch": "main", "new_name": "trunk"}),
    ("update_branch_protection", {"owner": "acme", "repo": "demo", "branch": "main"}),
    ("delete_branch_protection", {"owner": "acme", "repo": "demo", "branch": "main"}),
    ("update_ruleset", {"owner": "acme", "repo": "demo", "ruleset_id": 42}),
    ("delete_repository_ruleset", {"owner": "acme", "repo": "demo", "ruleset_id": 42}),
    ("update_repository", {"owner": "acme", "repo": "demo", "default_branch": "trunk"}),
]


@pytest.mark.parametrize("name,inp", REFUSED_MCP)
def test_mcp_writes_to_the_base_branch_refused(name, inp, solo):
    d = act(solo, mcp(name, inp))
    assert d.action == "deny", name
    assert REFUSED_LINE in d.reason and OFFER in d.reason, name
    assert "run it yourself in your own terminal:" in d.reason, name


ASKED_MCP = [("create_ruleset", {"owner": "acme", "repo": "demo", "name": "protect-main"}), ("create_repository_ruleset", {"owner": "acme", "repo": "demo"})]

UNCHANGED_MCP = [
    ("create_or_update_file", {"owner": "acme", "repo": "demo", "path": "a", "branch": "feature", "content": "x", "message": "m"}),
    ("push_files", {"owner": "acme", "repo": "demo", "branch": "feature", "files": [], "message": "m"}),
    ("update_ref", {"owner": "acme", "repo": "demo", "ref": "heads/feature", "sha": "abc"}),
    ("delete_branch", {"owner": "acme", "repo": "demo", "branch": "feature"}),
    ("create_branch", {"owner": "acme", "repo": "demo", "branch": "feature", "from_branch": "main"}),
    ("update_branch_protection", {"owner": "acme", "repo": "demo", "branch": "feature"}),
    ("merge_pull_request", {"owner": "acme", "repo": "demo", "pullNumber": 3, "merge_method": "merge"}),
    ("update_repository", {"owner": "acme", "repo": "demo", "allow_auto_merge": True}),
    ("get_branch_protection", {"owner": "acme", "repo": "demo", "branch": "main"}),
    ("list_rulesets", {"owner": "acme", "repo": "demo"}),
    ("get_file_contents", {"owner": "acme", "repo": "demo", "path": "a", "ref": "refs/heads/main"}),
]


@pytest.mark.parametrize("name,inp", ASKED_MCP)
def test_mcp_creating_a_ruleset_is_asked(name, inp, solo):
    d = act(solo, mcp(name, inp))
    assert d.action == "ask", name
    assert REFUSED_LINE not in d.reason


@pytest.mark.parametrize("name,inp", UNCHANGED_MCP)
def test_mcp_not_about_the_base_branch_unchanged(name, inp, solo, tmp_path):
    unset = on_disk(tmp_path / "unset", None)
    a, b = act(solo, mcp(name, inp)), act(unset, mcp(name, inp))
    assert (a.action, a.reason) == (b.action, b.reason), name


@pytest.mark.parametrize("name,inp", REFUSED_MCP + ASKED_MCP + UNCHANGED_MCP)
def test_mcp_outside_solo_mode_and_other_roles_unchanged(name, inp, tmp_path):
    protected = on_disk(tmp_path / "a", True)
    unset = on_disk(tmp_path / "b", None)
    solo = on_disk(tmp_path / "c", False)
    a, b = act(protected, mcp(name, inp)), act(unset, mcp(name, inp))
    assert (a.action, a.reason) == (b.action, b.reason), name
    assert a.action != "deny" and REFUSED_LINE not in a.reason, name
    for role in ("ticket", "conductor"):
        x = act(solo, mcp(name, inp), role=role, branch="claude/build-1")
        y = act(unset, mcp(name, inp), role=role, branch="claude/build-1")
        assert (x.action, x.reason) == (y.action, y.reason), (role, name)


def test_mcp_file_writes_on_the_base_were_asked_before(tmp_path):
    unset = on_disk(tmp_path, None)
    for name, inp in REFUSED_MCP[:5]:
        assert act(unset, mcp(name, inp)).action == "ask", name


def test_mcp_hand_command_names_the_api_call(solo, monkeypatch):
    monkeypatch.setenv("WORKFLOW_EXPERIENCE", "developer")
    r = act(solo, mcp("update_ref", {"owner": "acme", "repo": "demo", "ref": "heads/main", "sha": "abc"})).reason
    assert "`gh api -X PATCH repos/acme/demo/git/refs/heads/main" in r
    r = act(solo, mcp("delete_file", {"branch": "main", "path": "a.md", "message": "m"})).reason
    assert "`gh api -X DELETE repos/acme/demo/contents/a.md" in r


# ---------- the reason's wording ----------


@pytest.mark.parametrize("event", [bash("gh pr merge 12 --admin"), bash(f"curl -X DELETE {API}/rulesets/42"), mcp("delete_branch", {"branch": "main"})])
def test_wording_by_experience(event, solo, monkeypatch):
    monkeypatch.setenv("WORKFLOW_EXPERIENCE", "new")
    new = act(solo, event)
    monkeypatch.setenv("WORKFLOW_EXPERIENCE", "developer")
    dev = act(solo, event)
    assert new.action == dev.action == "deny"
    assert MAIN_LINE in new.reason and MAIN_LINE not in dev.reason
    for r in (new.reason, dev.reason):
        assert "run it yourself in your own terminal:" in r and OFFER in r


def test_reason_repeats_the_command_with_its_token_masked(solo):
    r = act(solo, f"curl -X DELETE -H 'Authorization: token abc123' {API}/rulesets/42").reason
    assert "abc123" not in r and f"{API}/rulesets/42" in r


def test_reason_says_what_was_seen(solo):
    assert "--admin" in act(solo, "gh pr merge 12 --admin").reason
    assert "ruleset" in act(solo, "gh api -X DELETE repos/acme/demo/rulesets/42").reason
    assert "default branch" in act(solo, "gh repo edit --default-branch trunk").reason


# ---------- end to end through the hook CLI ----------


def run_hook(event, cwd, env_extra):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(cwd), **env_extra}
    for k in ("WORKFLOW_ROLE", "WORKFLOW_EXPERIENCE"):
        if k not in env_extra:
            env.pop(k, None)
    p = subprocess.run([sys.executable, str(CLI), "hook", "guard"], input=json.dumps(event), capture_output=True, text=True, cwd=cwd, env=env)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)["hookSpecificOutput"] if p.stdout.strip() else None


@pytest.fixture
def solo_repo(repo):
    (repo / ".claude/workflow/profile.toml").write_text(_toml(False))
    return repo


@pytest.mark.parametrize(
    "event",
    [
        bash("gh pr merge 12 --admin"),
        bash("gh api -X DELETE repos/acme/demo/rulesets/42"),
        bash(f"curl -X PUT {API}/branches/main/protection -d @p.json"),
        mcp("push_files", {"owner": "acme", "repo": "demo", "branch": "main", "files": [], "message": "m"}),
    ],
)
def test_hook_denies_in_solo_mode(event, solo_repo):
    out = run_hook({**event, "cwd": str(solo_repo)}, solo_repo, {"WORKFLOW_ROLE": "attended"})
    assert out["permissionDecision"] == "deny"
    assert out["permissionDecisionReason"].startswith("[workflow guard, attended session] ")
    assert "Protect `main`" in out["permissionDecisionReason"]


def test_hook_asks_for_a_ruleset_create_and_outside_solo_mode(solo_repo):
    out = run_hook(bash(f"curl -X POST {API}/rulesets -d @r.json", solo_repo), solo_repo, {"WORKFLOW_ROLE": "attended"})
    assert out["permissionDecision"] == "ask"
    (solo_repo / ".claude/workflow/profile.toml").write_text(_toml(True))
    out = run_hook(bash("gh pr merge 12 --admin", solo_repo), solo_repo, {"WORKFLOW_ROLE": "attended"})
    assert out["permissionDecision"] == "ask"
