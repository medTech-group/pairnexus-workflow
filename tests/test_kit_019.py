"""Kit 0.1.9: the guard's editing-script and skip-marker patterns run in linear time."""

import time

from workflow.guard import decide


def act(profile, root, cmd):
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}}
    return decide(ev, profile, "ticket", root, "claude/build-1", role_from_env=True).action


def edit(profile, root, new, path="tests/test_x.py"):
    ev = {"tool_name": "Edit", "tool_input": {"file_path": path, "old_string": "a", "new_string": new}}
    return decide(ev, profile, "ticket", root, "claude/build-1", role_from_env=True).action


def _timed(fn, *args):
    t = time.monotonic()
    action = fn(*args)
    return action, time.monotonic() - t


# Inputs that make a careless pattern slow. On 0.1.8 the first three were
# exponential (at 40 escapes they would outlast the hook's timeout) and the
# `xfail(` ones quadratic. The run of escaped slashes was quadratic only in an
# early version of this fix; it stays here so it can't come back.
SLOW = (
    "sed -i 's!" + "\\a" * 40 + "' tests/test_x.py",
    "sed -i '/" + "\\." * 40 + "' tests/test_x.py",
    "perl -pi -e 's|" + "\\x" * 40 + "' src/app.spec.ts",
    "sed -i '/" + "\\/" * 30000 + "' tests/test_x.py",
    "sed -i '1i " + "pytest.mark.xfail(" * 30000 + "' tests/test_x.py",
)


def test_editing_scripts_are_read_at_once_whatever_they_hold(profile, tmp_path):
    for cmd in SLOW:
        action, took = _timed(act, profile, tmp_path, cmd)
        assert took < 5, (cmd[:30], took)
        assert action == "allow", cmd[:30]  # no complete skip marker in them


def test_an_edit_full_of_xfail_is_read_at_once(profile, tmp_path):
    action, took = _timed(edit, profile, tmp_path, "@pytest.mark.xfail(" * 30000)
    assert took < 5 and action == "allow", took


def test_an_xfail_that_doesnt_run_is_seen_however_long_its_arguments(profile, tmp_path):
    decorator = '@pytest.mark.xfail(sys.platform == "win32", reason="' + "slow " * 400 + '", strict=True, run=False)'
    assert edit(profile, tmp_path, decorator) == "deny"
    assert act(profile, tmp_path, f"sed -i '1i {decorator}' tests/test_x.py") == "deny"
    assert edit(profile, tmp_path, '@pytest.mark.xfail(reason="flaky", strict=True)') == "allow"


def test_an_escaped_delimiter_is_read_as_sed_reads_it(profile, tmp_path):
    # `\/` inside an `s` command is an escaped delimiter, not the end: here the
    # marker is in what the command finds, so it's removed, not added.
    assert act(profile, tmp_path, "sed -i 's/x\\/it.only(/y/' src/app.spec.ts") == "allow"
    assert act(profile, tmp_path, "sed -i 's/it\\/a(/it\\/b(/' src/app.spec.ts") == "allow"
    assert act(profile, tmp_path, "sed -i 's/it\\/a(/it.only(/' src/app.spec.ts") == "deny"


def test_a_commands_flags_are_not_a_new_command_but_still_count(profile, tmp_path):
    # perl's `s` flag right after the closing delimiter, then a removal.
    assert act(profile, tmp_path, "perl -0777 -pi -e 's/\\n\\n+/\\n/s; s/xit\\(/it(/g' tests/a.spec.js") == "allow"
    assert act(profile, tmp_path, "sed -i 's/a/b/g;s/it.only(/it(/' src/app.spec.ts") == "allow"
    # Letters after a command are still read: these add a marker.
    assert act(profile, tmp_path, "perl -pi -e 's/x/y/SkipTest' tests/test_x.py") == "deny"


def test_a_regex_class_is_not_an_s_command(profile, tmp_path):
    # `\s*` is whitespace in a regex, so these clean up and remove a marker.
    assert act(profile, tmp_path, "sed -i '/^\\s*$/d; s/it\\.only(/it(/' src/app.spec.ts") == "allow"
    assert act(profile, tmp_path, "perl -pi -e 'next if /^\\s*#/; s/xit\\(/it(/g' tests/a.spec.js") == "allow"
    assert act(profile, tmp_path, "sed -i 's/@pytest\\.mark\\.skip\\s*//' tests/test_x.py") == "allow"
    # And a stray `\s` can't make an added marker look like a removal.
    cmd = ("perl -pi -e 's{\\r$}{}; s{^(\\s*)def test_slow}{$1\\@pytest.mark.skip\\n$1def test_slow}; "
           "s{\\s*$}{}; s{\\t*$}{}' tests/test_x.py")
    assert act(profile, tmp_path, cmd) == "deny"


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
        # perl's bracketed form is read as an `s` command delimited by `{`: on
        # its own it never closes, so a removal after it counts as added.
        "perl -pi -e 's{foo}{bar}g; s/xit\\(/it(/g' tests/a.spec.js",
    ):
        assert act(profile, tmp_path, cmd) == "deny", cmd
