"""#193: the test helpers that make the slowest tests faster. A compiled copy
of the kit's package (`copy_kit_package`) runs a copied file's own source once
a test changes it, and `at_once` gives every call's result in order."""

import subprocess
import sys
import threading

import pytest

from conftest import KIT, at_once, copy_kit_package


def _run(top, code):
    return subprocess.run([sys.executable, "-B", "-c", f"import sys; sys.path.insert(0, {str(top)!r}); {code}"],
                          capture_output=True, text=True)


def test_a_compiled_copy_has_bytecode_for_every_module(tmp_path):
    copy_kit_package(tmp_path / "workflow")
    sources = sorted(p.relative_to(KIT / "scripts").as_posix() for p in (KIT / "scripts/workflow").rglob("*.py"))
    copied = sorted(p.relative_to(tmp_path).as_posix() for p in (tmp_path / "workflow").rglob("*.py"))
    assert copied == sources
    for name in copied:
        f = tmp_path / name
        assert list((f.parent / "__pycache__").glob(f"{f.stem}.*.pyc")), name


def test_a_changed_file_in_a_compiled_copy_runs_its_own_source(tmp_path):
    copy_kit_package(tmp_path / "workflow")
    init = tmp_path / "workflow/__init__.py"
    init.write_text(init.read_text() + '\nCHANGED = "yes"\n')
    p = _run(tmp_path, "import workflow; print(workflow.CHANGED)")
    assert (p.returncode, p.stdout) == (0, "yes\n"), p.stderr


def test_an_uncompiled_copy_has_no_bytecode(tmp_path):
    copy_kit_package(tmp_path / "workflow", compiled=False)
    assert (tmp_path / "workflow/cli.py").is_file()
    assert not list(tmp_path.rglob("__pycache__"))


def test_at_once_gives_each_result_in_order_from_calls_made_together():
    both = threading.Barrier(2, timeout=10)  # passes only when two calls run at the same time

    def waits_then(k):
        both.wait()
        return k

    assert at_once([lambda: waits_then(1), lambda: waits_then(2)]) == [1, 2]
    assert at_once(lambda k=k: k * k for k in range(20)) == [k * k for k in range(20)]


def test_at_once_raises_what_a_call_raised():
    def bad():
        raise ValueError("call 2")

    with pytest.raises(ValueError, match="call 2"):
        at_once([lambda: 1, bad, lambda: 3])
