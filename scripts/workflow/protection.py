"""Whether the base branch is protected, read back from GitHub's JSON.

`workflow protection` takes the repository's rulesets, each in full (as
`GET repos/<repo>/rulesets/<id>` returns it), and optionally the repository's
settings (`GET repos/<repo>`), and says whether the base branch is protected,
what is missing, whether checks are required, and the merge settings. It reads
only what it is given: it asks GitHub nothing and writes nothing.

The base branch is protected when the active rulesets that target it, taken
together, restrict deletions, block force pushes and require pull requests,
and none of them has a bypass list. Anything it can't tell counts as missing,
so an unknown never reads as protected. `check` is the one place this rule
lives: the "Protect `main`" upgrade, set-up, the conductor's pre-flight and
`workflow doctor` will call it rather than repeat it.
"""

from __future__ import annotations

import fnmatch
import json
import re
import unicodedata
from dataclasses import dataclass, field

# The rules that make a branch protected, with what their absence means.
NEEDED = {
    "deletion": "deletions allowed: no active ruleset on {base} restricts deletions",
    "non_fast_forward": "force pushes allowed: no active ruleset on {base} blocks force pushes",
    "pull_request": "pull requests not required: no active ruleset on {base} requires a pull request",
}
CHECKS_NOTE = "checks not required yet"
# The merge settings: the key in GET repos/<repo>, its name in --json, its words.
MERGE = (
    ("allow_merge_commit", "merge_commits", "merge commits"),
    ("allow_auto_merge", "auto_merge", "auto-merge"),
)
# Glob syntax GitHub (Ruby's File.fnmatch) reads differently from Python's
# fnmatch, so that an exclude could leave out more there than here: `**/`
# (any number of directories), negation, escapes and braces. An exclude holding
# one can't be matched here.
UNREAD_GLOB = ("**", "[^", "[!", "\\", "{", "}")
# What makes a ref condition a pattern rather than a name.
GLOB = set("*?[{\\")
# What a branch name can't hold (git check-ref-format), and what would make
# the report's first line say something else.
NOT_IN_A_BRANCH = set(" ~^:?*[\\") | {chr(c) for c in range(0x20)} | {"\x7f", "\x85", "\u2028", "\u2029"}


def quote(s: str) -> str:
    """Text from the input, as a JSON string: no character of it can start a line.

    json.dumps escapes the control characters; these line breaks it leaves.
    """
    out = json.dumps(s, ensure_ascii=False)
    out = out.replace("\x85", "\\u0085").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    # A lone surrogate can't be printed; escape it as JSON does.
    return re.sub("[\ud800-\udfff]", lambda m: f"\\u{ord(m.group()):04x}", out)


def branch(name: str) -> str:
    """The base branch as a plain name (`refs/heads/` dropped); raises when it can't be one."""
    name = name.strip(" \t").removeprefix("refs/heads/")
    bad = (
        not name
        or any(c in NOT_IN_A_BRANCH or unicodedata.category(c) in ("Cf", "Cs", "Zl", "Zp") for c in name)
        or name == "@"
        or ".." in name
        or "@{" in name
        or "//" in name
        or name.startswith(("-", "/"))
        or name.endswith(("/", ".", ".lock"))
        or any(part.startswith(".") or part.endswith(".lock") for part in name.split("/"))
    )
    if bad:
        raise ProtectionError(f"the base branch {quote(name)} isn't a branch name")
    return name


class ProtectionError(ValueError):
    """The input isn't what GitHub returns: never read as a verdict."""


@dataclass
class Report:
    base_branch: str
    protected: bool
    missing: list[str] = field(default_factory=list)
    required_checks: list[str] = field(default_factory=list)
    merge: dict | None = None  # {"merge_commits": bool | None, "auto_merge": ..., "missing": [...]}

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


def _checks_of(rule: dict) -> list:
    return (rule.get("parameters") or {}).get("required_status_checks") or []


def _checked_name(rs, i: int) -> str:
    """The ruleset as it is named in reports; raises when it isn't a full ruleset.

    The name is quoted as JSON, so a newline in it can't make a line of its own.
    """
    if not isinstance(rs, dict):
        raise ProtectionError(f"item {i + 1} in the rulesets file isn't a ruleset (a JSON object)")
    raw = rs.get("name") if isinstance(rs.get("name"), str) else f"#{rs.get('id', i + 1)}"
    where = "ruleset " + quote(raw)
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
    if not isinstance(rs.get("target"), str):
        raise ProtectionError(f"{where}: target must be a string (branch, tag or push)")
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
            checks = _checks_of(r)
            if not isinstance(checks, list) or not all(isinstance(c, dict) for c in checks):
                raise ProtectionError(f"{where}: required_status_checks must be a list of objects")
    return where


def _targets(rs: dict, base: str, default: str | None, have_settings: bool) -> str | None:
    """Why the ruleset doesn't take in the base branch, or None when it does.

    It counts `~ALL`, `refs/heads/<base>`, and `~DEFAULT_BRANCH` when the
    settings say the base branch is the default branch. An include pattern
    (`refs/heads/ma*`) isn't matched, so it doesn't count. An exclude that
    matches the base branch, a pattern included, takes it out, and one whose
    pattern can't be matched here (or isn't a full ref name) counts as taking
    it out. Excludes are matched ignoring case, so they only ever take out more.
    """
    if rs["target"] != "branch":
        return f"doesn't target {base} (it is a {quote(rs['target'])} ruleset)"
    ref = (rs.get("conditions") or {}).get("ref_name") or {}
    full = f"refs/heads/{base}"

    def names_base(pattern: str) -> bool | None:
        """Whether a ref condition names the base branch; None when it can't tell."""
        if pattern in ("~ALL", full):
            return True
        if pattern == "~DEFAULT_BRANCH":
            return None if default is None else default == base
        return False

    unknown = (
        "the settings file has no default_branch"
        if have_settings
        else "without the repository's settings (--repo)"
    )
    hits = [names_base(p) for p in ref.get("include") or []]
    if True not in hits:
        if None in hits:
            return f"targets the default branch, and {unknown}, so it can't tell whether that is {base}"
        patterns = [p for p in ref.get("include") or [] if any(c in GLOB for c in p)]
        if patterns:
            return f"includes {quote(patterns[0])}, a pattern this command doesn't match, so it can't tell whether it targets {base}"
        if "~DEFAULT_BRANCH" in (ref.get("include") or []):
            return f"doesn't target {base} (it targets the default branch, {quote(default)})"
        return f"doesn't target {base}"
    for p in ref.get("exclude") or []:
        hit = names_base(p)
        if hit is None:
            return f"excludes the default branch, and {unknown}, so it can't tell whether that is {base}"
        if hit:
            return f"doesn't target {base} (it excludes {quote(p)})"
        if any(s in p for s in UNREAD_GLOB) or not (p.startswith("refs/") or p.startswith("~")):
            return f"excludes {quote(p)}, a pattern this command can't match, so it can't tell whether {base} is left out"
        if fnmatch.fnmatchcase(full, p) or fnmatch.fnmatchcase(full.casefold(), p.casefold()):
            return f"doesn't target {base} (it excludes {quote(p)})"
    return None


def _settings(settings) -> tuple[dict, str | None]:
    """The merge settings as reported, and the repository's default branch."""
    if not isinstance(settings, dict):
        raise ProtectionError("the repository's settings must be a JSON object, as GET repos/<repo> returns it")
    merge: dict = {}
    missing: list[str] = []
    for key, name, words in MERGE:
        v = settings.get(key)
        if v is not None and not isinstance(v, bool):
            raise ProtectionError(f"the repository's settings: {key} must be true or false")
        merge[name] = v
        if v is None:
            missing.append(f"{words}: can't be read ({key} isn't in the settings file; it needs admin access)")
        elif not v:
            missing.append(f"{words} not allowed: turn on {key}")
    merge["missing"] = missing
    default = settings.get("default_branch")
    if default is not None and not isinstance(default, str):
        raise ProtectionError("the repository's settings: default_branch must be a string")
    return merge, default


def check(rulesets, base: str, settings=None) -> Report:
    """The verdict for `base`, from the rulesets (and settings) as GitHub returns them.

    `settings=None` means no settings were given: the merge settings aren't
    reported, and a ruleset on `~DEFAULT_BRANCH` can't be counted.
    """
    base = branch(base)
    rulesets = _flatten(rulesets)
    names = [_checked_name(rs, i) for i, rs in enumerate(rulesets)]
    merge, default = _settings(settings) if settings is not None else (None, None)
    if not rulesets:
        return Report(base, False, [f"no rulesets: nothing on GitHub protects {base}"], [], merge)

    ignored: list[str] = []
    effective: list[tuple[str, dict]] = []
    for name, rs in zip(names, rulesets):
        off_target = _targets(rs, base, default, settings is not None)
        if off_target and off_target.startswith("doesn't target"):
            ignored.append(f"{name} {off_target}")
        elif rs["enforcement"] == "evaluate":
            ignored.append(f"{name} is evaluate only: it reports but doesn't block")
        elif rs["enforcement"] != "active":
            ignored.append(f"{name} is not active (enforcement {quote(rs['enforcement'])})")
        elif off_target:
            ignored.append(f"{name} {off_target}")
        else:
            effective.append((name, rs))

    problems: list[str] = []
    for name, rs in effective:
        if "bypass_actors" not in rs:
            problems.append(f"{name}: its bypass list can't be read (it needs admin access), so nobody can tell who may skip its rules")
        elif rs["bypass_actors"]:
            n = len(rs["bypass_actors"])
            problems.append(f"{name} has a bypass list ({n} {'actor' if n == 1 else 'actors'}): they can skip its rules; empty it")
    have = {r["type"] for _, rs in effective for r in rs["rules"]}
    problems += [words.format(base=base) for rule, words in NEEDED.items() if rule not in have]

    checks: list[str] = []
    for _, rs in effective:
        for r in rs["rules"]:
            if r["type"] == "required_status_checks":
                for c in _checks_of(r):
                    if isinstance(c.get("context"), str) and c["context"] not in checks:
                        checks.append(c["context"])

    protected = not problems
    return Report(base, protected, [] if protected else ignored + problems, checks, merge)


def text(rep: Report) -> str:
    lines = [f"{rep.base_branch} is protected." if rep.protected else f"{rep.base_branch} is not protected:"]
    lines += [f"- {m}" for m in rep.missing]
    if rep.required_checks:
        lines.append("Required checks: " + ", ".join(quote(c) for c in rep.required_checks))
    else:
        lines.append(f"Checks not required yet: no active ruleset on {rep.base_branch} requires status checks.")
    if rep.merge is not None:
        state = {True: "allowed", False: "not allowed", None: "unknown"}
        lines.append("Merge settings: " + ", ".join(f"{words} {state[rep.merge[name]]}" for _, name, words in MERGE) + ".")
        lines += [f"- {m}" for m in rep.merge["missing"]]
    return "\n".join(lines)
