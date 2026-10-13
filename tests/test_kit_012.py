"""Kit 0.1.2: the owner's set-up guide, and the docs that point to it."""

from pathlib import Path

KIT = Path(__file__).resolve().parents[1]


def test_readme_starts_with_the_step_by_step_set_up():
    readme = (KIT / "README.md").read_text()
    start = readme.index("## Getting started")
    assert start < readme.index("## What's in it")
    steps = [
        "### Before your first repository (once)",
        "### Step 1. Ask Claude to set the repository up",
        "### Step 2. Merge the pull request",
        "### Step 3. Protect the base branch with a ruleset",
        "### Step 4. Check the merge settings",
        "### Step 5. Create the two Claude environments",
        "### Step 6. Check it",
        "### Using it",
        "### Keeping it up to date",
    ]
    at = [readme.index(s) for s in steps]
    assert at == sorted(at) and at[0] > start
    for phrase in (
        "skills/setup-workflow/SKILL.md",
        "skills/update-workflow/SKILL.md",
        "Settings → Rules → Rulesets",
        "Enforcement status:** **Active",
        "Require branches to be up to date before merging",
        "Require review from Code Owners: leave it unticked",
        "Allow auto-merge",
        "Allow merge commits",
        "Bypass list:** **leave it empty",
        "WORKFLOW_ROLE=ticket",
        "WORKFLOW_ROLE=conductor",
        "Why the names must match",
        "workflow:stop",
    ):
        assert phrase in readme, phrase


def test_environments_are_per_repo_and_named_exactly():
    text = (KIT / "docs/enforcement.md").read_text()
    assert "once per account |" not in text
    assert "The owner, per repo" in text
    assert "The names must match exactly" in text
    assert "- **Bypass list:** empty." in text and "Require linear history" in text


def test_the_conductor_never_starts_tickets_without_the_named_environment():
    text = (KIT / "skills/conductor/SKILL.md").read_text()
    assert "None of that name is a blocking problem" in text
    assert "Never start ticket sessions in another environment" in text


def test_setup_puts_every_click_in_the_pr_body():
    text = (KIT / "skills/setup-workflow/SKILL.md").read_text()
    assert "The owner should be able to do every step from the PR body alone" in text
    plan = text.index("**The organisation's GitHub plan,**")
    assert plan < text.index("**The base branch's ruleset,**")


def test_flow_names_the_projects_glossary_not_context_md():
    assert "`CONTEXT.md`" not in (KIT / "docs/flow.md").read_text()


def test_the_ci_template_reads_only():
    text = (KIT / "templates/github/workflow-kit.yml").read_text()
    assert "permissions:\n  contents: read" in text
    assert "persist-credentials: false" in text
