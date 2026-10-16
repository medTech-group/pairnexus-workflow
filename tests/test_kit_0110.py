"""Kit 0.1.10: older gaps in how the guard counts skip markers in ticket sessions,
and a time budget so a slow guard fails closed."""

import json
import time

import pytest

from workflow import cli, guard
from workflow.guard import decide


def act(profile, root, cmd):
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}}
    return decide(ev, profile, "ticket", root, "claude/build-1", role_from_env=True).action


def write(profile, root, path, content):
    ev = {"tool_name": "Write", "tool_input": {"file_path": str(root / path), "content": content}}
    return decide(ev, profile, "ticket", root, "claude/build-1", role_from_env=True)


# 1. Text that sed's `a`, `i` and `c` write is added, whatever it holds.


def test_inserted_text_with_slashes_counts_as_added(profile, tmp_path):
    for cmd in (
        "sed -i '5i\\    x = \"/\"; pytest.skip(\"/\")' tests/test_x.py",
        "sed -i '1a /x/; pytest.skip(\"/\")' tests/test_x.py",
        "sed -i '/def test_a/c\\\n/ @pytest.mark.skip /' tests/test_x.py",
        "sed -i '$a\\\nx = 1\\\n/; it.only(\"a\", f) /' src/app.spec.ts",
        # An `s` command inside the text is text too, not a removal.
        "sed -i '1i pytest.skip(1) s/pytest.skip(/x/' tests/test_x.py",
    ):
        assert act(profile, tmp_path, cmd) == "deny", cmd


def test_an_address_still_only_finds(profile, tmp_path):
    for cmd in (
        "sed -i '/it\\.only(/d' src/app.spec.ts",
        "sed -i '1,/xit(/d' tests/a.spec.js",
        "sed -i '/a/,/xit(/d' tests/a.spec.js",
        "sed -i '5{/xit(/d}' tests/a.spec.js",
        "sed -i '/keep/!{/xit(/d}' tests/a.spec.js",
        "sed -i '0,/it\\.only(/s//it(/' src/app.spec.ts",
        "sed -i '\\%pytest.mark.skip%d' tests/test_x.py",
        "sed -i -e '/@pytest.mark.skip/d' -e '$a\\' -e 'x = 1' tests/test_x.py",
    ):
        assert act(profile, tmp_path, cmd) == "allow", cmd
    assert act(profile, tmp_path, "sed -i '0,/it(/s//it.only(/' src/app.spec.ts") == "deny"


# 2. An `s` inside an address isn't an `s` command.


def test_an_s_inside_an_address_starts_no_command(profile, tmp_path):
    assert act(profile, tmp_path, "sed -i '/x.s/d; s/it(/xit(/' tests/a.spec.js") == "deny"
    assert act(profile, tmp_path, "sed -i '/a s/d; s/it(/it.only(/' src/app.spec.ts") == "deny"
    assert act(profile, tmp_path, "sed -i '/x.s/d; s/xit(/it(/' tests/a.spec.js") == "allow"


# 3. vim's and ed's `s` ends at the end of its line.


def test_a_vim_s_command_ends_at_its_line(profile, tmp_path):
    cmd = "vim -es -c '%s/a/b' -c '1s/^/@pytest.mark.skip\\r/' -c wq tests/test_x.py"
    assert act(profile, tmp_path, cmd) == "deny"
    assert act(profile, tmp_path, "ex -s -c '%s/x/y' -c '1s/^/it.only(/' -c wq src/app.spec.ts") == "deny"
    assert act(profile, tmp_path, "ed -s tests/test_x.py <<'EOF'\n,s/a/b\n1s/^/pytest.skip(1)/\nw\nq\nEOF") == "deny"
    # Removals and cleanups are still read as such.
    assert act(profile, tmp_path, "vim -es -c '%s/it\\.only(/it(/g' -c wq src/app.spec.ts") == "allow"
    assert act(profile, tmp_path, "vim -es -c 'g/xit(/d' -c wq tests/a.spec.js") == "allow"
    assert act(profile, tmp_path, "ex -s -c '%s/xit(/it(/|wq' tests/a.spec.js") == "allow"
    assert act(profile, tmp_path, "vim -es -c 'g/x/s//pytest.skip(1)/' -c wq tests/test_x.py") == "deny"


def test_vim_normal_keys_run_into_the_text_they_insert(profile, tmp_path):
    assert act(profile, tmp_path, "vim -es -c 'normal ggOpytest.skip(1)' -c wq tests/test_x.py") == "deny"
    assert act(profile, tmp_path, "vim -es -c 'g/x/norm Oit.only(' -c wq src/app.spec.ts") == "deny"
    assert act(profile, tmp_path, "vim -es -c 'exe \"normal Axit(\"' -c wq tests/a.spec.js") == "deny"
    assert act(profile, tmp_path, "vim -es -c '%$normal Opytest.skip(1)' -c wq tests/test_x.py") == "deny"
    assert act(profile, tmp_path, "vim -es -c 'silent! bufdo norm Oit.only(' -c wq src/app.spec.ts") == "deny"
    assert act(profile, tmp_path, "vim -es -c 'normal ggdd' -c wq tests/a.spec.js") == "allow"


def test_ed_appended_text_counts_as_added(profile, tmp_path):
    assert act(profile, tmp_path, "ed -s tests/test_x.py <<'EOF'\n1a\n@pytest.mark.skip\n.\nw\nq\nEOF") == "deny"


# 4. A patch's lines are the file's text, read literally.


def _patch(root, removed, added, path="tests/a.spec.js"):
    (root / "fix.patch").write_text(
        f"--- a/{path}\n+++ b/{path}\n@@ -1,1 +1,1 @@\n-{removed}\n+{added}\n"
    )
    return act_in(root, "git apply fix.patch")


def act_in(root, cmd):
    from conftest import BASE_PROFILE
    from workflow.profile import parse

    profile = parse(json.loads(json.dumps(BASE_PROFILE)), root)
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(root)}
    return decide(ev, profile, "ticket", root, "claude/build-1", role_from_env=True).action


def test_patch_lines_are_read_without_unescaping(tmp_path):
    # The removed line holds `it\.only\(`, not the marker, so the added one isn't netted away.
    assert _patch(tmp_path, "expect(src).toMatch(/it\\.only\\(/)", 'it.only("a", f)') == "deny"
    assert _patch(tmp_path, 'it.only("a", f)', 'it("a", f)') == "allow"
    assert _patch(tmp_path, "x", "expect(src).toMatch(/it\\.only\\(/)") == "allow"


# 5. What an `s` command finds is a regex: `\s` there is whitespace, not `s`.


def test_a_regex_escape_in_what_is_found_is_no_letter(profile, tmp_path):
    assert act(profile, tmp_path, "sed -i 's/it\\.\\skip(/x/; s/it(/it.only(/' src/app.spec.ts") == "deny"
    assert act(profile, tmp_path, "perl -pi -e 's/it\\.\\skip\\(/x/; s/it\\(/it.only(/' tests/a.spec.js") == "deny"
    # What a command puts is still read as sed writes it.
    assert act(profile, tmp_path, "sed -i 's/it(/it.\\skip(/' src/app.spec.ts") == "deny"
    assert act(profile, tmp_path, "sed -i 's/@pytest\\.mark\\.skip\\s*//' tests/test_x.py") == "allow"


# perl and awk: a string is what the code writes, a regex only finds.


def test_perl_strings_are_text_and_regexes_only_find(profile, tmp_path):
    assert act(profile, tmp_path, "perl -pi -e '$_ .= \"/ pytest.skip(1) /\" if $. == 1' tests/test_x.py") == "deny"
    assert act(profile, tmp_path, "perl -pi -e '$_ = \"pytest.skip(1)\" . $_ if $. == 1; $x = \"s/pytest.skip(/y/\"' tests/test_x.py") == "deny"
    assert act(profile, tmp_path, "perl -pi -e 'print q{; /pytest.skip(1)/} if $. == 1' tests/test_x.py") == "deny"
    assert act(profile, tmp_path, "perl -ni -e 'print unless /it\\.only\\(/' src/app.spec.ts") == "allow"
    assert act(profile, tmp_path, "perl -pi -e 's/xit\\(/it(/ if m{xit\\(}' tests/a.spec.js") == "allow"
    assert act(profile, tmp_path, "awk -i inplace '{ gsub(/it\\.only\\(/, \"it(\") } 1' src/app.spec.ts") == "allow"
    assert act(profile, tmp_path, "awk -i inplace '{ gsub(/it\\(/, \"it.only(\") } 1' src/app.spec.ts") == "deny"


# 6. A big `-f` script is read once per command, and over the cap it is refused.


def test_a_big_sed_script_is_read_once_for_many_files(profile, tmp_path):
    (tmp_path / "big.sed").write_text("s/a/b/\n" * 140_000)
    files = " ".join(f"tests/test_{i}.py" for i in range(30))
    t = time.monotonic()
    assert act(profile, tmp_path, f"sed -i -f big.sed {files}") == "allow"
    assert time.monotonic() - t < 5


def test_sed_scripts_over_the_cap_are_refused(profile, tmp_path):
    (tmp_path / "a.sed").write_text("s/a/b/\n" * 100_000)
    (tmp_path / "b.sed").write_text("s/a/b/\n" * 100_000)
    assert act(profile, tmp_path, "sed -i -f a.sed -f b.sed tests/test_x.py") == "deny"
    # A marker past the first megabyte of one script is seen, not cut off.
    (tmp_path / "c.sed").write_text("s/a/b/\n" * 150_000 + "1i @pytest.mark.skip\n")
    assert act(profile, tmp_path, "sed -i -f c.sed tests/test_x.py") == "deny"
    assert act(profile, tmp_path, "sed -i -f a.sed tests/test_x.py") == "allow"


def test_a_patch_over_the_cap_is_refused(tmp_path):
    big = "".join(f"+x = {i}\n" for i in range(200_000))
    (tmp_path / "big.patch").write_text(f"--- a/tests/a.spec.js\n+++ b/tests/a.spec.js\n@@ -0,0 +1,200000 @@\n{big}+it.only('a', f)\n")
    assert act_in(tmp_path, "git apply big.patch") == "deny"


# 7. A Write reads at most a capped amount of the file it replaces.


def test_a_write_over_a_huge_test_file_is_refused(profile, tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "_WRITE_READ_CAP", 1000)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_big.py").write_text("x = 1\n" * 1000)
    d = write(profile, tmp_path, "tests/test_big.py", "x = 2\n")
    assert d.action == "deny" and "too large" in d.reason
    (tmp_path / "tests/test_small.py").write_text("@pytest.mark.skip\n")
    assert write(profile, tmp_path, "tests/test_small.py", "@pytest.mark.skip\nx = 1\n").action == "allow"
    assert write(profile, tmp_path, "tests/test_small.py", "@pytest.mark.skip\npytest.skip(1)\n").action == "deny"


# 8. A guard that runs past its budget is refused in ticket and conductor sessions.


@pytest.mark.parametrize("role", ["ticket", "conductor"])
def test_a_slow_guard_fails_closed(repo, monkeypatch, capsys, role):
    def slow(*a, **k):
        time.sleep(5)
        return guard.ALLOW

    monkeypatch.setattr(cli, "GUARD_BUDGET", 0.2)
    monkeypatch.setattr(cli.guard_mod, "decide", slow)
    monkeypatch.setenv("WORKFLOW_ROLE", role)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    monkeypatch.chdir(repo)
    t = time.monotonic()
    assert cli._hook_guard({"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": str(repo)}) == 0
    assert time.monotonic() - t < 3
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "time" in out["permissionDecisionReason"]


def test_a_quick_guard_is_untouched_by_the_budget(repo, monkeypatch, capsys):
    monkeypatch.setenv("WORKFLOW_ROLE", "ticket")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    monkeypatch.chdir(repo)
    assert cli._hook_guard({"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": str(repo)}) == 0
    assert capsys.readouterr().out == ""
    import signal

    if hasattr(signal, "setitimer"):
        assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)  # no alarm left behind
