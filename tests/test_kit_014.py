"""Kit 0.1.4: the planning commands bring the flow into context on their own."""

from workflow import context


def test_planning_commands_bring_the_flow_on_their_own():
    for prompt in [
        "/to-spec",
        "/to-tickets",
        "/wayfinder a patient app for clinic queues",
        "/grill-with-docs Patients export their records as one PDF",
        "/triage",
        "/implement",
        "/implement-spec",
        "/mattpocock-skills:to-spec",
        "  /to-tickets please",
    ]:
        assert context.wants_flow(prompt), prompt


def test_other_commands_and_plain_talk_do_not():
    for prompt in [
        "/grill-me my pitch deck",
        "/prototype",
        "/research how Razorpay refunds work",
        "what does to-spec do?",
        "path/to-spec.md",
    ]:
        assert not context.wants_flow(prompt), prompt


# Every Matt Pocock skill the pinned version copies into a project (the
# vendored set pair-drop has at kit 0.1.3). A new pin that adds or drops one
# fails here until the README's table follows.
MATT_POCOCK_SKILLS = {
    "ask-matt", "code-review", "codebase-design", "diagnosing-bugs", "domain-modeling", "grill-me",
    "grill-with-docs", "grilling", "handoff", "implement", "implement-spec", "improve-codebase-architecture",
    "pr", "prototype", "research", "resolving-merge-conflicts", "retro", "setup-matt-pocock-skills", "tdd",
    "teach", "to-questionnaire", "to-spec", "to-tickets", "triage", "wait-what", "wayfinder", "wizard",
    "writing-for-agents",
}


def _readme():
    from conftest import KIT

    return (KIT / "README.md").read_text()


def test_readme_lists_every_matt_pocock_skill_with_who_starts_it():
    readme = _readme()
    table = readme.split("#### Every Matt Pocock skill in a project", 1)[1].split("\n### ", 1)[0]
    rows = {line.split("`/", 1)[1].split("`", 1)[0] for line in table.splitlines() if line.startswith("| `/")}
    assert rows == MATT_POCOCK_SKILLS
    for line in table.splitlines():
        if line.startswith("| `/"):
            assert "| You type |" in line or "| Claude, when needed |" in line, line


def test_readme_using_it_opens_with_the_guided_start_and_planning_covers_the_path():
    readme = _readme()
    using = readme.index("### Using it")
    assert using < readme.index("#### Start a session and say what you're working on") < readme.index("### Planning new work")
    section = readme.split("### Planning new work", 1)[1].split("### Keeping it up to date", 1)[0]
    for must in ["/grill-with-docs", "/to-spec", "/to-tickets", "/wayfinder", "/next map", "/next spec",
                 "one session", "`spec`", "`Area:`", "owner-task", "workflow:infra", "Don't run it",
                 "A brand-new project", "wayfinder:map", "The gate"]:
        assert must in section, must
