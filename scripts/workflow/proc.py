"""Running a command so that nothing it started outlives the wait.

The one runner for the kit's own short commands (doctor's checks, status's
`git` calls, the profile's `git` reads): the command runs in a session of its
own, and its whole process group is killed whenever the caller stops waiting
(a timeout, a Ctrl-C), so a child it started is never left running (#684,
#689). A Ctrl-C still reaches the caller as `KeyboardInterrupt`, for its own
quiet stop.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from typing import NamedTuple


class Done(NamedTuple):
    """How a command ended: `started` False when it couldn't be started,
    `timed_out` when it was killed at the timeout; otherwise its exit code
    and what it printed (`err` only when asked for)."""

    started: bool
    timed_out: bool = False
    code: int | None = None
    out: bytes = b""
    err: bytes = b""


def run(argv: list[str], *, cwd=None, env: dict | None = None, timeout: float, stderr: bool = False) -> Done:
    """Run `argv` with no shell and no input, for at most `timeout` seconds."""
    # A Ctrl-C while Popen starts the command is held until `p` is set: raised
    # inside Popen, it would leave the command running with nothing to kill it
    # (#684). Only the main thread's handler raises KeyboardInterrupt.
    held: list[int] = []
    previous = signal.getsignal(signal.SIGINT)
    hold = callable(previous) and threading.current_thread() is threading.main_thread()
    if hold:
        signal.signal(signal.SIGINT, lambda *_: held.append(1))
    try:
        p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE if stderr else subprocess.DEVNULL, start_new_session=True)
    except BaseException as e:
        if hold:
            signal.signal(signal.SIGINT, previous)
        if held:
            raise KeyboardInterrupt from None
        if isinstance(e, (OSError, ValueError)):
            return Done(False)
        raise
    timed_out, out, err = False, b"", b""
    try:
        if hold:
            signal.signal(signal.SIGINT, previous)
        if held:
            raise KeyboardInterrupt
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        if p.returncode is None:  # still running: a timeout, or the caller interrupted
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                p.kill()
            try:
                p.communicate(timeout=1)  # a detached grandchild may hold the pipe: don't wait on it
            except subprocess.TimeoutExpired:
                pass
            for f in (p.stdout, p.stderr):
                if f:
                    f.close()
    if timed_out:
        return Done(True, timed_out=True)
    return Done(True, code=p.returncode, out=out or b"", err=err or b"")


def output(argv: list[str], *, cwd=None, timeout: float) -> str | None:
    """What `argv` printed, read as UTF-8 with any other bytes replaced, when
    it ran and exited 0; else None (it couldn't start, timed out or failed)."""
    done = run(argv, cwd=cwd, timeout=timeout)
    return done.out.decode("utf-8", errors="replace") if done.started and done.code == 0 else None
