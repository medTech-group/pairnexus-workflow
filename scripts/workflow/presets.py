"""A run's size in one choice: Light, Normal or Thorough (#42, decided in #31).

Each preset bundles the levers the kit controls: the charter's
`limits.max_parallel`, `limits.max_sessions` and `limits.max_retries`, and its
`review.rounds`, `review.explorer` and `review.small` (#259). The end time and
the check-in interval aren't part of a preset, nor are the pass cap and the
small threshold (`review.passes`, `review.small_max_lines` and
`review.small_max_files`): those are the profile's in every preset. This is
the one place the presets' numbers live: the charter's questions, defaults,
validation and one page read them.

`profile` is a loaded profile (`profile.load`), or None for the profile's
defaults. Normal is the profile's own numbers; "has an explorer" means the
profile's `ui.explorer` isn't `none`, and with none, `review.explorer` is
always off.
"""

from __future__ import annotations

import dataclasses
from typing import Any

PRESETS = ("light", "normal", "thorough")
DEFAULT = "normal"
LABELS = {"light": "Light", "normal": "Normal", "thorough": "Thorough"}

NO_EXPLORER = "no UI explorer (the project has none)"
LIGHT_NO_EXPLORER = "no UI explorer (one round is the light review)"


def _run(profile: Any, key: str) -> int:
    """The profile's [run] number, or its default without a profile."""
    v = getattr(profile, key, None)
    if isinstance(v, int) and not isinstance(v, bool):
        return v
    from .profile import Profile  # here, not at the top: profile.py imports this module

    return next(f.default for f in dataclasses.fields(Profile) if f.name == key)


def has_explorer(profile: Any) -> bool:
    """The profile has a UI explorer: its `ui.explorer` isn't `none`."""
    return getattr(profile, "explorer", "none") not in (None, "", "none")


def numbers(name: str, profile: Any = None) -> dict:
    """A preset's numbers with the profile's: `{"limits": {max_parallel,
    max_sessions, max_retries}, "review": {rounds, explorer, small}}`. The
    small review is on in Light and Normal, off in Thorough."""
    if name not in PRESETS:
        raise ValueError(f"unknown preset {name!r}; one of {', '.join(PRESETS)}")
    rounds, explorer = _run(profile, "review_rounds"), has_explorer(profile)
    return {
        "light": {
            "limits": {"max_parallel": 1, "max_sessions": 10, "max_retries": 0},
            "review": {"rounds": 1, "explorer": False, "small": True},
        },
        "normal": {
            "limits": {"max_parallel": _run(profile, "max_parallel"), "max_sessions": 40, "max_retries": _run(profile, "max_retries")},
            "review": {"rounds": rounds, "explorer": explorer, "small": True},
        },
        "thorough": {
            "limits": {"max_parallel": 3, "max_sessions": 60, "max_retries": 1},
            "review": {"rounds": max(3, rounds), "explorer": explorer, "small": False},
        },
    }[name]


def plural(v: int, one: str, many: str) -> str:
    """ "1 retry", "0 retries"."""
    return f"{v} {one if v == 1 else many}"


def runs_explorer(review: dict) -> bool:
    """A review `{rounds, explorer}` runs the UI explorer: it asks for one, and
    isn't a single round, which is the light review (`review-panel` §6)."""
    return review.get("explorer") is True and review.get("rounds") != 1


def _explorer_phrase(review: dict, profile: Any) -> str:
    if profile is not None and not has_explorer(profile):
        return NO_EXPLORER
    if runs_explorer(review):
        return "UI explorer on"
    if review.get("explorer") is True:
        return LIGHT_NO_EXPLORER
    return "UI explorer off"


def threshold_words(review: dict) -> str:
    """ "60 lines in 4 files": the small threshold of a review (`review_of`)."""
    return f"{plural(review['small_max_lines'], 'line', 'lines')} in {plural(review['small_max_files'], 'file', 'files')}"


def passes_words(review: dict) -> str:
    """ "at most 2 Correctness passes", or "no Correctness passes" for 0: the
    pass cap of a review (`review_of`)."""
    if review["passes"] == 0:
        return "no Correctness passes"
    return f"at most {plural(review['passes'], 'Correctness pass', 'Correctness passes')}"


def past_small(review: dict) -> str:
    """What a ticket marked small gets past the threshold: the full panel, or
    in a 1-round run the light review."""
    return "the light review" if review["rounds"] == 1 else "the full panel"


def small_reviewers(review: dict, profile: Any = None) -> str:
    """Who the small review runs beside Correctness: the security review where
    it applies, and the UI explorer only when the run has one (and the
    profile, when given, has one)."""
    if runs_explorer(review) and (profile is None or has_explorer(profile)):
        return "with the security review and the UI explorer where they apply"
    return "with the security review where it applies"


def words(name: str, profile: Any = None) -> str:
    """A preset's numbers in words, for the question's choices."""
    p = numbers(name, profile)
    lim, rev = p["limits"], review_of({"preset": name, "review": p["review"]}, profile)
    small = f"small review on (at most {threshold_words(rev)} outside tests)" if rev["small"] else "small review off"
    return (
        f"{plural(lim['max_parallel'], 'session', 'sessions')} at once, {lim['max_sessions']} in all, "
        f"{plural(lim['max_retries'], 'retry', 'retries')} per ticket; {small}; {passes_words(rev)}; "
        f"up to {plural(rev['rounds'], 'review round', 'review rounds')}; {_explorer_phrase(rev, profile)}"
    )


def table(profile: Any = None) -> dict:
    """Every preset, as the limits question offers them."""
    return {name: {"label": LABELS[name], **numbers(name, profile), "words": words(name, profile)} for name in PRESETS}


def recommended(profile: Any = None) -> str:
    """The profile's `run.preset`, Normal when absent."""
    v = getattr(profile, "preset", None)
    return v if v in PRESETS else DEFAULT


# The charter's review keys that are the profile's when absent: (charter key, profile key, low, high).
PROFILE_REVIEW = (
    ("passes", "review_passes", 0, 10),
    ("small_max_lines", "small_max_lines", 1, 1000),
    ("small_max_files", "small_max_files", 1, 50),
)


def _whole(v: Any, lo: int, hi: int) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def review_of(c: dict, profile: Any = None) -> dict:
    """The review a run takes from its charter, `{rounds, explorer, small,
    passes, small_max_lines, small_max_files}`. Rounds and explorer: the
    charter's `review`; without one, its preset's; and for a charter written
    before presets, the profile's, as before. `small`: the charter's, and off
    when it has none, so a charter approved before the small review behaves as
    approved. The pass cap and the small threshold: the charter's, else the
    profile's `run.review_passes`, `run.small_max_lines` and `run.small_max_files`."""
    r = c.get("review") if isinstance(c, dict) else None
    r = r if isinstance(r, dict) else {}
    if "rounds" in r and "explorer" in r:
        out = {"rounds": r["rounds"], "explorer": r["explorer"]}
    elif isinstance(c, dict) and c.get("preset") in PRESETS:
        rv = numbers(c["preset"], profile)["review"]
        out = {"rounds": rv["rounds"], "explorer": rv["explorer"]}
    else:
        out = {"rounds": _run(profile, "review_rounds"), "explorer": has_explorer(profile)}
    out["small"] = r.get("small") is True
    for key, run_key, lo, hi in PROFILE_REVIEW:
        out[key] = r[key] if _whole(r.get(key), lo, hi) else _run(profile, run_key)
    return out


def changes(c: dict, profile: Any = None) -> list[str]:
    """What the charter changed from its preset's numbers, in words ("3
    sessions at once"); empty when it matches, or has no preset. Without a
    profile, only what doesn't depend on it: for Normal only the small
    review, not Thorough's rounds of 3 or more, and Light's explorer only."""
    if not isinstance(c, dict) or c.get("preset") not in PRESETS:
        return []
    want = numbers(c["preset"], profile)
    # Every preset's small is fixed; a charter without one (written before it) reads as off.
    small = review_of(c, profile)["small"]
    small_change = [f"the small review {'on' if small else 'off'}"] if small != want["review"]["small"] else []
    if profile is None and c["preset"] == "normal":
        return small_change
    lim = c.get("limits") if isinstance(c.get("limits"), dict) else {}
    out = []
    for key, one, many in (
        ("max_parallel", "session at once", "sessions at once"),
        ("max_sessions", "session in all", "sessions in all"),
        ("max_retries", "retry per ticket", "retries per ticket"),
    ):
        if key in lim and lim[key] != want["limits"][key]:
            out.append(plural(lim[key], one, many))
    rev = c.get("review")
    if isinstance(rev, dict):
        # Thorough's rounds are the profile's when more than 3: fewer is a change whatever the profile.
        known = profile is not None or c["preset"] != "thorough" or rev.get("rounds", 3) < 3
        if known and "rounds" in rev and rev["rounds"] != want["review"]["rounds"]:
            out.append(plural(rev["rounds"], "review round", "review rounds"))
        # Light's explorer is always off; the others' follow the profile.
        if (profile is not None or c["preset"] == "light") and "explorer" in rev and rev["explorer"] != want["review"]["explorer"]:
            out.append(f"the UI explorer {'on' if rev['explorer'] else 'off'}")
    out += small_change
    # The pass cap and the threshold are the profile's in every preset: a change only against a profile.
    if isinstance(rev, dict) and profile is not None:
        got, usual = review_of(c, profile), review_of({"preset": c["preset"]}, profile)
        if got["passes"] != usual["passes"]:
            out.append(plural(got["passes"], "pass", "passes"))
        if (got["small_max_lines"], got["small_max_files"]) != (usual["small_max_lines"], usual["small_max_files"]):
            out.append(f"a small threshold of {threshold_words(got)} outside tests")
    return out


def explorer_words(c: dict, profile: Any = None) -> str:
    """The review's explorer for the one page: on, off, off for the light
    review, or the project has none."""
    return _explorer_phrase(review_of(c, profile), profile)
