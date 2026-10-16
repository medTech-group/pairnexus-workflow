"""Whether the base branch is protected, read back from GitHub's JSON.

`workflow protection` takes the repository's rulesets, each in full (as
`GET repos/<repo>/rulesets/<id>` returns it), and optionally the repository's
settings (`GET repos/<repo>`), and says whether the base branch is protected,
what is missing, whether checks are required, and the merge settings. It reads
only what it is given: it asks GitHub nothing and writes nothing.

The base branch is protected when the active rulesets that target it, taken
together, restrict deletions, block force pushes and require pull requests,
and none of them has a bypass list. Anything it can't tell counts as missing,
so an unknown never reads as protected. The "Protect `main`" read-back,
set-up's `ruleset` answer, the conductor's pre-flight and `workflow doctor`
all use `check`, so the rule sits in one place.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field

# The rules that make a branch protected, with what their absence means.
NEEDED = {
    "deletion": "deletions allowed: no active ruleset on {base} restricts deletions",
    "non_fast_forward": "force pushes allowed: no active ruleset on {base} blocks force pushes",
    "pull_request": "pull requests not required: no active ruleset on {base} requires a pull request",
}
CHECKS_NOTE = "checks not required yet"
MERGE = {
    "allow_merge_commit": ("merge_commits", "merge commits"),
    "allow_auto_merge": ("auto_merge", "auto-merge"),
}


class ProtectionError(ValueError):
    """The input isn't what GitHub returns: never read as a verdict."""


@dataclass
class Report:
    base_branch: str
    protected: bool
    missing: list[str] = field(default_factory=list)
    required_checks: list[str] = field(default_factory=list)
    merge: dict | None = None

    def as_dict(self) -> dict:
        return {
            "base_branch": self.base_branch,
            "protected": self.protected,
            "missing": list(self.missing),
            "checks": {"required": list(self.required_checks), "note": None if self.required_checks else CHECKS_NOTE},
            "merge": self.merge,
        }


def _flatten(data) -> list:
    """A list of rulesets; pages from `gh api --paginate --slurp` are joined."""
    if not isinstance(data, list):
        raise ProtectionError("the rulesets file must be a JSON list of rulesets, as GitHub returns them")
    if data and all(isinstance(x, list) for x in data):
        return [r for page in data for r in page]
    return data


def _strs(v, where: str) -> list[str]:
    if v is None:
        return []
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise ProtectionError(f"{where} must be a list of strings")
    return v


def _validate(rs, i: int) -> str:
    """The ruleset's name for messages; raises when it isn't a full ruleset."""
    if not isinstance(rs, dict):
        raise ProtectionError(f"ruleset {i + 1} isn't a JSON object")
    name = rs.get("name") if isinstance(rs.get("name"), str) else f"#{rs.get('id', i + 1)}"
    where = f'ruleset "{name}"'
    if "rules" not in rs:
        raise ProtectionError(
            f"{where} isn't in full (it has no rules): the rulesets list gives only summaries, "
            "so fetch each one with GET repos/<repo>/rulesets/<id>"
        )
    rules = rs["rules"]
    if not isinstance(rules, list) or not all(isinstance(r, dict) and isinstance(r.get("type"), str) for r in rules):
        raise ProtectionError(f"{where}: rules must be a list of objects, each with a type")
    if not isinstance(rs.get("enforcement"), str):
        raise ProtectionError(f"{where}: enforcement must be a string (active, evaluate or disabled)")
    if "target" in rs and not isinstance(rs["target"], str):
        raise ProtectionError(f"{where}: target must be a string")
    if "bypass_actors" in rs and not isinstance(rs["bypass_actors"], list):
        raise ProtectionError(f"{where}: bypass_actors must be a list")
    cond = rs.get("conditions")
    if cond is not None:
        if not isinstance(cond, dict):
            raise ProtectionError(f"{where}: conditions must be an object")
        ref = cond.get("ref_name")
        if ref is not None:
            if not isinstance(ref, dict):
                raise ProtectionError(f"{where}: conditions.ref_name must be an object")
            _strs(ref.get("include"), f"{where}: conditions.ref_name.include")
            _strs(ref.get("exclude"), f"{where}: conditions.ref_name.exclude")
    for r in rules:
        if r.get("parameters") is not None and not isinstance(r["parameters"], dict):
            raise ProtectionError(f"{where}: a rule's parameters must be an object")
        if r["type"] == "required_status_checks":
            checks = (r.get("parameters") or {}).get("required_status_checks", [])
            if not isinstance(checks, list) or not all(isinstance(c, dict) for c in checks):
                raise ProtectionError(f"{where}: required_status_checks must be a list of objects")
    return name


def _targets(rs: dict, base: str, is_default: bool) -> bool:
    """Whether the ruleset's ref conditions take in the base branch.

    It counts `~ALL`, `refs/heads/<base>`, and `~DEFAULT_BRANCH` when the base
    branch is the default branch. An include pattern (`refs/heads/ma*`) isn't
    matched, so it doesn't count; an exclude that matches the base branch, a
    pattern included, takes it out.
    """
    if rs.get("target", "branch") != "branch":
        return False
    ref = (rs.get("conditions") or {}).get("ref_name") or {}
    full = f"refs/heads/{base}"

    def names(pattern: str, globs: bool) -> bool:
        if pattern == "~ALL" or pattern == full:
            return True
        if pattern == "~DEFAULT_BRANCH":
            return is_default
        return globs and fnmatch.fnmatchcase(full, pattern)

    if not any(names(p, globs=False) for p in ref.get("include") or []):
        return False
    return not any(names(p, globs=True) for p in ref.get("exclude") or [])


def _merge(settings, base: str) -> tuple[dict, bool]:
    """The merge settings, and whether the base branch is the default branch."""
    if not isinstance(settings, dict):
        raise ProtectionError("the repository's settings must be a JSON object, as GET repos/<repo> returns it")
    out: dict = {"missing": []}
    for key, (name, words) in MERGE.items():
        v = settings.get(key)
        if v is not None and not isinstance(v, bool):
            raise ProtectionError(f"the repository's settings: {key} must be true or false")
        out[name] = v
        if v is None:
            out["missing"].append(f"{words}: can't be read ({key} isn't in the settings file; it needs admin access)")
        elif not v:
            out["missing"].append(f"{words} not allowed: turn on {key}")
    default = settings.get("default_branch")
    if default is not None and not isinstance(default, str):
        raise ProtectionError("the repository's settings: default_branch must be a string")
    return {"merge_commits": out["merge_commits"], "auto_merge": out["auto_merge"], "missing": out["missing"]}, default in (None, base)


def check(rulesets, base: str, settings=None) -> Report:
    """The verdict for `base`, from the rulesets (and settings) as GitHub returns them."""
    rulesets = _flatten(rulesets)
    names = [_validate(rs, i) for i, rs in enumerate(rulesets)]
    merge, is_default = _merge(settings, base) if settings is not None else (None, True)
    if not rulesets:
        return Report(base, False, [f"no rulesets: nothing on GitHub protects {base}"], [], merge)

    ignored: list[str] = []
    effective: list[tuple[str, dict]] = []
    for name, rs in zip(names, rulesets):
        if not _targets(rs, base, is_default):
            ignored.append(f'ruleset "{name}" doesn\'t target {base}')
        elif rs["enforcement"] == "evaluate":
            ignored.append(f'ruleset "{name}" is evaluate only: it reports but doesn\'t block')
        elif rs["enforcement"] != "active":
            ignored.append(f'ruleset "{name}" is not active ({rs["enforcement"]})')
        else:
            effective.append((name, rs))

    problems: list[str] = []
    for name, rs in effective:
        if "bypass_actors" not in rs:
            problems.append(f'ruleset "{name}": its bypass list can\'t be read (it needs admin access), so it may let someone skip its rules')
        elif rs["bypass_actors"]:
            n = len(rs["bypass_actors"])
            problems.append(f'ruleset "{name}" has a bypass list ({n} {"actor" if n == 1 else "actors"}): they can skip its rules; empty it')
    have = {r["type"] for _, rs in effective for r in rs["rules"]}
    problems += [words.format(base=base) for rule, words in NEEDED.items() if rule not in have]

    checks: list[str] = []
    for _, rs in effective:
        for r in rs["rules"]:
            if r["type"] == "required_status_checks":
                for c in (r.get("parameters") or {}).get("required_status_checks", []):
                    if isinstance(c.get("context"), str) and c["context"] not in checks:
                        checks.append(c["context"])

    protected = not problems
    return Report(base, protected, [] if protected else ignored + problems, checks, merge)


def text(rep: Report) -> str:
    lines = [f"{rep.base_branch} is protected." if rep.protected else f"{rep.base_branch} is not protected:"]
    lines += [f"- {m}" for m in rep.missing]
    if rep.required_checks:
        lines.append("Required checks: " + ", ".join(rep.required_checks))
    else:
        lines.append(f"Checks not required yet: no active ruleset on {rep.base_branch} requires status checks.")
    if rep.merge is not None:
        if not rep.merge["missing"]:
            lines.append("Merge settings: merge commits allowed, auto-merge allowed.")
        else:
            good = [words + " allowed" for key, (name, words) in MERGE.items() if rep.merge[name]]
            lines.append("Merge settings:" + (" " + ", ".join(good) + "; missing:" if good else ""))
            lines += [f"- {m}" for m in rep.merge["missing"]]
    return "\n".join(lines)
