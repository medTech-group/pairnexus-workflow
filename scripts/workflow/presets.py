"""A run's size in one choice: Light, Normal or Thorough (#42, decided in #31).

Each preset bundles the levers the kit controls: the charter's
`limits.max_parallel`, `limits.max_sessions` and `limits.max_retries`, and its
`review.rounds` and `review.explorer`. The end time and the check-in interval
aren't part of a preset. This is the one place the presets' numbers live: the
charter's questions, defaults, validation and one page read them, and so does
the estimate.

`profile` is a loaded profile (`profile.load`), or None for the profile's
defaults. Normal is the profile's own numbers; "has an explorer" means the
profile's `ui.explorer` isn't `none`, and with none, `review.explorer` is
always off.
"""

from __future__ import annotations

from typing import Any

PRESETS = ("light", "normal", "thorough")
DEFAULT = "normal"
LABELS = {"light": "Light", "normal": "Normal", "thorough": "Thorough"}

# The profile's [run] defaults, for Normal without a profile.
_PROFILE_DEFAULTS = {"max_parallel": 2, "max_retries": 1, "review_rounds": 3}

NO_EXPLORER = "no UI explorer (the project has none)"


def _run(profile: Any, key: str) -> int:
    v = getattr(profile, key, None)
    return v if isinstance(v, int) and not isinstance(v, bool) else _PROFILE_DEFAULTS[key]


def has_explorer(profile: Any) -> bool:
    """The profile has a UI explorer: its `ui.explorer` isn't `none`."""
    return getattr(profile, "explorer", "none") not in (None, "", "none")


def numbers(name: str, profile: Any = None) -> dict:
    """A preset's numbers with the profile's: `{"limits": {max_parallel,
    max_sessions, max_retries}, "review": {rounds, explorer}}`."""
    if name not in PRESETS:
        raise ValueError(f"unknown preset {name!r}; one of {', '.join(PRESETS)}")
    rounds = _run(profile, "review_rounds")
    explorer = has_explorer(profile)
    if name == "light":
        limits, review = (1, 10, 0), (1, False)
    elif name == "normal":
        limits, review = (_run(profile, "max_parallel"), 40, _run(profile, "max_retries")), (rounds, explorer)
    else:
        limits, review = (3, 60, 1), (max(3, rounds), explorer)
    return {
        "limits": dict(zip(("max_parallel", "max_sessions", "max_retries"), limits)),
        "review": {"rounds": review[0], "explorer": review[1]},
    }


def _n(v: int, one: str, many: str) -> str:
    return f"{v} {one if v == 1 else many}"


def _explorer_words(on: bool, profile: Any) -> str:
    if on:
        return "UI explorer on"
    return NO_EXPLORER if profile is not None and not has_explorer(profile) else "UI explorer off"


def words(name: str, profile: Any = None) -> str:
    """A preset's numbers in words, for the question's choices."""
    p = numbers(name, profile)
    lim, rev = p["limits"], p["review"]
    return (
        f"{lim['max_parallel']} at once, {lim['max_sessions']} sessions in all, "
        f"{_n(lim['max_retries'], 'retry', 'retries')} per ticket; "
        f"up to {_n(rev['rounds'], 'review round', 'review rounds')}; {_explorer_words(rev['explorer'], profile)}"
    )


def table(profile: Any = None) -> dict:
    """Every preset, as the limits question offers them."""
    return {name: {"label": LABELS[name], **numbers(name, profile), "words": words(name, profile)} for name in PRESETS}


def recommended(profile: Any = None) -> str:
    """The profile's `run.preset`, Normal when absent."""
    v = getattr(profile, "preset", None)
    return v if v in PRESETS else DEFAULT


def preset_of(c: dict) -> str:
    """The charter's preset; Normal for one written before presets."""
    v = c.get("preset") if isinstance(c, dict) else None
    return v if v in PRESETS else DEFAULT


def review_of(c: dict, profile: Any = None) -> dict:
    """The review a run takes from its charter, `{rounds, explorer}`: the
    charter's `review`, or, for a charter written before presets, the
    profile's rounds and explorer, as before."""
    r = c.get("review") if isinstance(c, dict) else None
    if isinstance(r, dict) and "rounds" in r and "explorer" in r:
        return {"rounds": r["rounds"], "explorer": r["explorer"]}
    return {"rounds": _run(profile, "review_rounds"), "explorer": has_explorer(profile)}


def changes(c: dict, profile: Any = None) -> list[str]:
    """What the charter changed from its preset's numbers, in words ("3
    sessions at once"); empty when it matches, or has no preset."""
    if not isinstance(c, dict) or c.get("preset") not in PRESETS:
        return []
    want = numbers(c["preset"], profile)
    lim = c.get("limits") if isinstance(c.get("limits"), dict) else {}
    out = []
    for key, one, many in (
        ("max_parallel", "session at once", "sessions at once"),
        ("max_sessions", "session in all", "sessions in all"),
        ("max_retries", "retry per ticket", "retries per ticket"),
    ):
        if key in lim and lim[key] != want["limits"][key]:
            out.append(_n(lim[key], one, many))
    rev = c.get("review")
    if isinstance(rev, dict):
        if "rounds" in rev and rev["rounds"] != want["review"]["rounds"]:
            out.append(_n(rev["rounds"], "review round", "review rounds"))
        if "explorer" in rev and rev["explorer"] != want["review"]["explorer"]:
            out.append(f"the UI explorer {'on' if rev['explorer'] else 'off'}")
    return out


def explorer_words(c: dict, profile: Any = None) -> str:
    """The review's explorer for the one page: on, off, or the project has none."""
    return _explorer_words(bool(review_of(c, profile)["explorer"]), profile)
