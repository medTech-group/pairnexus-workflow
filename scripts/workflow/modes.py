"""Claude Code's permission modes, as the guard sees them (#52).

Claude Code sends the session's `permission_mode` with every PreToolUse event.
In some modes a hook's `ask` reaches a person; in others nobody is asked, so
the guard turns its asks into denies there. Any value not listed counts as a
mode that never asks; an absent one (an older Claude Code) as a mode that asks.

Keep it to the standard library and to syntax Python 3.7 reads (a test
checks): the old-Python fallback (`_old_python.py`) shares this list.
"""

# Modes where a hook's `ask` prompts the person.
ASKING_MODES = ("default", "acceptEdits", "auto", "plan")
# Modes where nobody is asked: an `ask` would go through unseen, or not at all.
NEVER_ASK_MODES = ("bypassPermissions", "dontAsk")


def never_asks(mode):
    """True when nobody is asked in `mode` (the event's `permission_mode`, None
    when absent): a mode that never asks, or one the kit doesn't know."""
    if mode is None:
        return False
    return mode not in ASKING_MODES


def known(mode):
    """True for a mode the kit knows."""
    return mode in ASKING_MODES or mode in NEVER_ASK_MODES
