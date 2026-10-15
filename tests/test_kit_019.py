"""Kit 0.1.9: the guard reads editing scripts in linear time."""

import time

from workflow.guard import decide


def act(profile, root, cmd):
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}}
    return decide(ev, profile, "ticket", root, "claude/build-1", role_from_env=True).action


def _timed(profile, root, cmd):
    t = time.monotonic()
    action = act(profile, root, cmd)
    return action, time.monotonic() - t


# Inputs that made the `s` command and address patterns backtrack exponentially:
# a delimiter, then many escapes and no closing delimiter. At 24 escapes the old
# patterns took seconds; at 40 they would outlast the hook's timeout.
SLOW = (
    "sed -i 's!" + "\\a" * 40 + "' tests/test_x.py",
    "sed -i '/" + "\\." * 40 + "' tests/test_x.py",
    "perl -pi -e 's|" + "\\x" * 40 + "' src/app.spec.ts",
)


def test_editing_scripts_with_many_escapes_are_read_at_once(profile, tmp_path):
    for cmd in SLOW:
        action, took = _timed(profile, tmp_path, cmd)
        assert took < 1, (cmd[:30], took)
        assert action == "allow", cmd[:30]  # no skip marker in them


def test_an_escaped_delimiter_is_read_as_sed_reads_it(profile, tmp_path):
    # `\/` inside an `s` command is an escaped delimiter, not the end.
    assert act(profile, tmp_path, "sed -i 's/it\\/a(/it\\/b(/' src/app.spec.ts") == "allow"
    assert act(profile, tmp_path, "sed -i 's/it\\/a(/it.only(/' src/app.spec.ts") == "deny"
    assert act(profile, tmp_path, "sed -i 's/it.only\\/x(/it\\/x(/' src/app.spec.ts") == "allow"
    assert act(profile, tmp_path, "sed -i '/it.only\\/x(/d' src/app.spec.ts") == "allow"


def test_a_script_that_never_closes_counts_its_markers_as_added(profile, tmp_path):
    # Unterminated, so sed would refuse it; the guard can't tell what it finds
    # from what it puts, and counts the markers as added rather than netting
    # one against the other.
    assert act(profile, tmp_path, "sed -i 's/it.only(/it.only(\\/' src/app.spec.ts") == "deny"
    assert act(profile, tmp_path, "sed -i 's/x/@pytest.mark.skip\\/' tests/test_x.py") == "deny"
