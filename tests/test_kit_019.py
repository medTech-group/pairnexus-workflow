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


# Inputs that made the guard's patterns slow: exponential for the first three
# on 0.1.8 (at 40 escapes they would outlast the hook's timeout), quadratic for
# the last two (a run of escaped slashes, many `xfail(`).
SLOW = (
    "sed -i 's!" + "\\a" * 40 + "' tests/test_x.py",
    "sed -i '/" + "\\." * 40 + "' tests/test_x.py",
    "perl -pi -e 's|" + "\\x" * 40 + "' src/app.spec.ts",
    "sed -i '/" + "\\/" * 30000 + "' tests/test_x.py",
    "sed -i '1i " + "pytest.mark.xfail(" * 30000 + "' tests/test_x.py",
)


def test_editing_scripts_are_read_at_once_whatever_they_hold(profile, tmp_path):
    for cmd in SLOW:
        action, took = _timed(profile, tmp_path, cmd)
        assert took < 2, (cmd[:30], took)
        assert action == "allow", cmd[:30]  # no complete skip marker in them


def test_an_escaped_delimiter_is_read_as_sed_reads_it(profile, tmp_path):
    # `\/` inside an `s` command is an escaped delimiter, not the end: here the
    # marker is in what the command finds, so it's removed, not added.
    assert act(profile, tmp_path, "sed -i 's/x\\/it.only(/y/' src/app.spec.ts") == "allow"
    assert act(profile, tmp_path, "sed -i 's/it\\/a(/it\\/b(/' src/app.spec.ts") == "allow"
    assert act(profile, tmp_path, "sed -i 's/it\\/a(/it.only(/' src/app.spec.ts") == "deny"


def test_a_script_sed_cant_read_counts_its_markers_as_added(profile, tmp_path):
    # From an `s` command that never closes, the guard can't tell what it finds
    # from what it puts, so it nets nothing and drops no address: every marker
    # from there on counts as added.
    for cmd in (
        "sed -i 's/it.only(/it.only(\\/' src/app.spec.ts",
        "sed -i 's/x/@pytest.mark.skip\\/' tests/test_x.py",
        "sed -i 's/x\\/it.only(/' src/app.spec.ts",
        "sed -i 's/x\\/@pytest.mark.skip/' tests/test_x.py",
        # Valid sed: inserts a line holding the marker.
        "sed -i '1i s/\\/pytest.mark.skip/' tests/test_x.py",
        "sed -i '1i s/\\/ s|pytest.skip(|x| /' tests/test_x.py",
    ):
        assert act(profile, tmp_path, cmd) == "deny", cmd
