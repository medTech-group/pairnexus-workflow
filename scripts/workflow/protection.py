"""Whether the base branch is protected, read back from GitHub's JSON, and
the requests that protect it.

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
`workflow doctor` will call it rather than repeat it. It is also the queue
reader (#245): whether those rulesets require a merge queue (`Report.queue`).

Beside it, the request builder (#66): the requests that create the ruleset and
set the merge settings (`protect`), that add checks to a ruleset
(`require_checks`), and the checks that ran on a commit (`checks_ran`). It
prints them for a session to send, and sends nothing.
"""

from __future__ import annotations

import copy
import fnmatch
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone

# The rules that make a branch protected, with what their absence means.
NEEDED = {
    "deletion": "deletions allowed: no active ruleset on {base} restricts deletions",
    "non_fast_forward": "force pushes allowed: no active ruleset on {base} blocks force pushes",
    "pull_request": "pull requests not required: no active ruleset on {base} requires a pull request",
}
CHECKS_NOTE = "checks not required yet"
# The kinds of what `missing` lists: no rulesets at all; a ruleset that doesn't
# take in the base branch, or can't be told to; one that is turned off, or only
# evaluates; a bypass list, or one that can't be read; and the rules in NEEDED.
KINDS = ("no_rulesets", "not_on_base", "unsure", "not_active", "evaluate", "bypass", "bypass_unread", *NEEDED)
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


def _no_constant(name: str):
    raise ValueError(f"{name} isn't JSON")


def _finite(text: str) -> float:
    """A JSON number as a float; one too large for a float (1e400) isn't taken as Infinity."""
    v = float(text)
    if v in (float("inf"), float("-inf")):
        raise ValueError(f"the number {text[:20]} is too large")
    return v


def loads(text: str):
    """GitHub's JSON as this command reads it: a byte-order mark left out,
    and `NaN`, `Infinity` and numbers too large for a float refused (ValueError)."""
    return json.loads(text.removeprefix("\ufeff"), parse_constant=_no_constant, parse_float=_finite)


def quote(s: str) -> str:
    """Text from the input, as a JSON string: no character of it can start a line.

    json.dumps escapes the control characters; these line breaks it leaves.
    """
    return printable(json.dumps(s, ensure_ascii=False))


def printable(dumped: str) -> str:
    """JSON text with the characters that could start a line, or can't be
    printed, escaped as JSON escapes them."""
    out = dumped.replace("\x85", "\\u0085").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    # A lone surrogate can't be printed; escape it as JSON does.
    return re.sub("[\ud800-\udfff]", lambda m: f"\\u{ord(m.group()):04x}", out)


def branch(name: str) -> str:
    """The base branch as a plain name (`refs/heads/` dropped); raises when it can't be one."""
    name = name.strip(" \t").removeprefix("refs/heads/")
    bad = (
        not name
        or any(c in NOT_IN_A_BRANCH or unicodedata.category(c) in ("Cf", "Cs", "Zl", "Zp") for c in name)
        or name in ("@", "HEAD")
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
    # Active rulesets it can't tell target the base branch, so their required
    # checks aren't in `required_checks` (merge-check won't say "Ready" then).
    unsure: list[str] = field(default_factory=list)
    # What kind each of `missing` is, in its order (`KINDS`), for `workflow
    # doctor` to word each one; and the active rulesets that target the base
    # branch, whose other rules doctor reads. Neither is in --json.
    kinds: list[str] = field(default_factory=list)
    effective: list[dict] = field(default_factory=list)
    # The queue reader (#245): whether a ruleset in force on the base (one of
    # `effective`) requires a merge queue; and each `unsure` ruleset with a
    # merge-queue rule, never counted as a queue. Neither is in --json.
    queue: bool = False
    queue_unsure: list[str] = field(default_factory=list)

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


def _ref(rs: dict) -> dict:
    """The ruleset's ref condition: its `include` and `exclude` lists."""
    return (rs.get("conditions") or {}).get("ref_name") or {}


def _has_merge_queue(rs: dict) -> bool:
    """The ruleset has a merge-queue rule."""
    return any(r["type"] == "merge_queue" for r in rs["rules"])


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
    ref = _ref(rs)
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
        if any(s in p for s in UNREAD_GLOB) or not p.startswith("refs/"):
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


def check(rulesets, base: str, settings=None, base_if_unknown: bool = False) -> Report:
    """The verdict for `base`, from the rulesets (and settings) as GitHub returns them.

    `settings=None` means no settings were given: the merge settings aren't
    reported, and a ruleset on `~DEFAULT_BRANCH` can't be counted. With
    `base_if_unknown`, a default branch the settings don't give is taken to be
    `base`, unless a ruleset excludes `~DEFAULT_BRANCH`: that can only count
    more rulesets as targeting it, never fewer (merge-check's required checks).
    """
    base = branch(base)
    rulesets = _flatten(rulesets)
    names = [_checked_name(rs, i) for i, rs in enumerate(rulesets)]
    merge, default = _settings(settings) if settings is not None else (None, None)
    excluded = any("~DEFAULT_BRANCH" in (_ref(rs).get("exclude") or []) for rs in rulesets)
    # A default branch only taken to be `base` never counts a merge queue on it (#245).
    assumed = default is None and base_if_unknown and not excluded
    if assumed:
        default, settings = base, settings if settings is not None else {}
    if not rulesets:
        return Report(base, False, [f"no rulesets: nothing on GitHub protects {base}"], [], merge, kinds=["no_rulesets"])

    ignored: list[tuple[str, str]] = []
    unsure: list[str] = []
    queue_unsure: list[str] = []
    effective: list[tuple[str, dict]] = []
    for name, rs in zip(names, rulesets):
        off_target = _targets(rs, base, default, settings is not None)
        if off_target and off_target.startswith("doesn't target"):
            ignored.append(("not_on_base", f"{name} {off_target}"))
        elif rs["enforcement"] == "evaluate":
            ignored.append(("evaluate", f"{name} is evaluate only: it reports but doesn't block"))
        elif rs["enforcement"] != "active":
            ignored.append(("not_active", f"{name} is not active (enforcement {quote(rs['enforcement'])})"))
        elif off_target:
            ignored.append(("unsure", f"{name} {off_target}"))
            unsure.append(f"{name} {off_target}")
            if _has_merge_queue(rs):
                queue_unsure.append(f"{name} {off_target}")
        else:
            effective.append((name, rs))

    problems: list[tuple[str, str]] = []
    for name, rs in effective:
        if "bypass_actors" not in rs:
            problems.append(("bypass_unread", f"{name}: its bypass list can't be read (it needs admin access), so nobody can tell who may skip its rules"))
        elif rs["bypass_actors"]:
            n = len(rs["bypass_actors"])
            problems.append(("bypass", f"{name} has a bypass list ({n} {'actor' if n == 1 else 'actors'}): they can skip its rules; empty it"))
    have = {r["type"] for _, rs in effective for r in rs["rules"]}
    problems += [(rule, words.format(base=base)) for rule, words in NEEDED.items() if rule not in have]

    checks: list[str] = []
    for _, rs in effective:
        for r in rs["rules"]:
            if r["type"] == "required_status_checks":
                for c in _checks_of(r):
                    if isinstance(c.get("context"), str) and c["context"] not in checks:
                        checks.append(c["context"])

    protected = not problems
    found = [] if protected else ignored + problems
    queue = False
    for name, rs in effective:
        if not _has_merge_queue(rs):
            continue
        if assumed and not {"~ALL", f"refs/heads/{base}"} & set(_ref(rs).get("include") or []):
            queue_unsure.append(f"{name} targets the default branch, and the pull request doesn't give the repository's (base.repo.default_branch), so it can't tell whether that is {base}")
        else:
            queue = True
    return Report(base, protected, [m for _, m in found], checks, merge, unsure, [k for k, _ in found], [rs for _, rs in effective], queue, queue_unsure)


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


# ---------- the requests: protect, require checks, the checks that ran (#66) ----------
#
# Built from JSON a session hands over, and printed for it to send. Nothing here
# sends a request: the session does, with `gh api` or the GitHub MCP tools, under
# the guard (#17, #33).

KIT = "pairnexus-workflow"
REPO_PART = re.compile(r"[A-Za-z0-9_.-]+")
# What GitHub accepts on an update (PUT repos/<repo>/rulesets/<id>); the rest of
# a ruleset as GET returns it (id, source, node_id, _links, ...) is read-only.
UPDATE_FIELDS = ("name", "target", "enforcement", "bypass_actors", "conditions", "rules")
PULL_REQUEST = {
    "required_approving_review_count": 0,
    "dismiss_stale_reviews_on_push": False,
    "require_code_owner_review": False,
    "require_last_push_approval": False,
    "required_review_thread_resolution": False,
}
# The try-it link's check (#41): never offered for requiring (#18).
NEVER_OFFERED_APPS = ("cloudflare-workers-and-pages",)
# Check-run conclusions GitHub counts as passing a required check.
PASSING = ("success", "neutral", "skipped")
STATUS_RESULT = {"success": "passing", "pending": "pending", "failure": "failing", "error": "failing"}
# What a check name can't hold: line breaks, control characters, lone surrogates.
NOT_IN_A_CHECK = ("Cc", "Cs", "Zl", "Zp")


@dataclass
class Request:
    what: str
    method: str
    path: str
    body: dict

    def as_dict(self) -> dict:
        return {"what": self.what, "method": self.method, "path": self.path, "body": self.body}


@dataclass
class Ran:
    """A check run or a status on the commit."""

    name: str
    result: str
    when: datetime | None
    id: int
    preview: bool = False  # from the try-it link's app (NEVER_OFFERED_APPS)


def _a_check_name(n) -> bool:
    return isinstance(n, str) and bool(n.strip()) and n == n.strip() and not any(unicodedata.category(c) in NOT_IN_A_CHECK for c in n)


def check_names(names) -> list[str]:
    """The check names as given, each once; raises on one that can't be a check name."""
    out: list[str] = []
    for n in names or []:
        if not _a_check_name(n):
            shown = quote(n) if isinstance(n, str) else repr(n)
            raise ProtectionError(
                f"the check name {shown} isn't a check name: it is empty, has spaces at either end, "
                "or holds a line break, a control character or a byte that isn't text"
            )
        if n not in out:
            out.append(n)
    return out


def _repo_name(v) -> str | None:
    """`owner/repo` when v is one, else None."""
    if not isinstance(v, str) or v.count("/") != 1:
        return None
    parts = v.split("/")
    return v if all(REPO_PART.fullmatch(p) and p not in (".", "..") for p in parts) else None


def _checks_rule(names: list[str]) -> dict:
    return {
        "type": "required_status_checks",
        "parameters": {"strict_required_status_checks_policy": True, "required_status_checks": [{"context": n} for n in names]},
    }


def _repo_of(settings) -> tuple[str, str]:
    """(owner/repo, default branch) from the repository's settings."""
    _, default = _settings(settings)  # checks the settings as the read-back does; the merge report isn't needed here
    full = _repo_name(settings.get("full_name"))
    if full is None:
        raise ProtectionError("the repository's settings: full_name isn't owner/repo, so the requests can't name the repository")
    if not default:
        raise ProtectionError("the repository's settings have no default_branch, so it can't tell whether the base branch is the default")
    try:
        return full, branch(default)
    except ProtectionError as e:
        raise ProtectionError(f"the repository's settings: default_branch {quote(default)} isn't a branch name") from e


def protect(base: str, settings, names=()) -> list[Request]:
    """The ruleset to create on the base branch, and the merge settings to change."""
    base = branch(base)
    names = check_names(names)
    repo, default = _repo_of(settings)
    rules = [{"type": "deletion"}, {"type": "non_fast_forward"}, {"type": "pull_request", "parameters": dict(PULL_REQUEST)}]
    if names:
        rules.append(_checks_rule(names))
    ruleset = {
        "name": f"Protect {base} ({KIT})",
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH" if base == default else f"refs/heads/{base}"], "exclude": []}},
        "rules": rules,
    }
    return [
        Request("create the ruleset", "POST", f"repos/{repo}/rulesets", ruleset),
        Request("allow merge commits and auto-merge", "PATCH", f"repos/{repo}", {key: True for key, _, _ in MERGE}),
    ]


def _update(ruleset, verb: str) -> tuple[str, dict]:
    """(the PUT's path, the body GitHub accepts on an update) for the
    repository's own branch ruleset; raises on one the kit can't change.
    `verb` says what the change does, for the messages."""
    if not isinstance(ruleset, dict):
        raise ProtectionError("the ruleset file must be one ruleset (a JSON object), as GET repos/<repo>/rulesets/<id> returns it")
    where = _checked_name(ruleset, 0)
    if not isinstance(ruleset.get("name"), str):
        raise ProtectionError(f"{where} has no name")
    if ruleset["target"] != "branch":
        raise ProtectionError(f"{where} is a {quote(ruleset['target'])} ruleset: only a branch ruleset can {verb}")
    rid = ruleset.get("id")
    if not isinstance(rid, int) or isinstance(rid, bool) or rid <= 0:
        raise ProtectionError(f"{where} has no id, so the request can't name it")
    if ruleset.get("source_type") == "Organization":
        raise ProtectionError(f"{where} is an organisation's ruleset: the kit changes only the repository's own, so change it in the organisation's settings")
    source = _repo_name(ruleset.get("source"))
    if ruleset.get("source_type") != "Repository" or source is None:
        raise ProtectionError(f"{where} has no source repository (source_type Repository, source owner/repo), so the request can't name it")
    return f"repos/{source}/rulesets/{rid}", {k: copy.deepcopy(ruleset[k]) for k in UPDATE_FIELDS if k in ruleset}


def require_checks(ruleset, names) -> Request:
    """The ruleset with the names added to its required checks and "up to date"
    on, or left as it is when the ruleset has a merge-queue rule (#247): the
    queue meets "up to date", which would only send branches back to update.

    Nothing else changes and nothing is removed; only the fields GitHub accepts
    on an update are sent.
    """
    names = check_names(names)
    if not names:
        raise ProtectionError("give the checks to require with --check NAME (one for each)")
    path, body = _update(ruleset, "require checks")
    queued = _has_merge_queue(body)
    rule = next((r for r in body["rules"] if r["type"] == "required_status_checks"), None)
    if rule is None:
        rule = _checks_rule(names)
        rule["parameters"]["strict_required_status_checks_policy"] = not queued
        body["rules"].append(rule)
    else:
        if rule.get("parameters") is None:
            rule["parameters"] = {}
        params = rule["parameters"]
        have = params.get("required_status_checks")
        if have is None:
            have = params["required_status_checks"] = []
        if not isinstance(have, list) or not all(isinstance(c, dict) and isinstance(c.get("context"), str) for c in have):
            raise ProtectionError(f"{_checked_name(ruleset, 0)}: required_status_checks must be a list of objects, each with a context")
        known = {c["context"] for c in have}
        have += [{"context": n} for n in names if n not in known]
        if queued:
            if not isinstance(params.get("strict_required_status_checks_policy"), bool):
                params["strict_required_status_checks_policy"] = False  # GitHub requires the field, a boolean
        else:
            params["strict_required_status_checks_policy"] = True
    return Request("add the checks to the ruleset", "PUT", path, body)


# The merge-queue rule's settings (#243), shown to the owner before the change.
QUEUE_SETTINGS = {
    "merge_method": "MERGE",
    "grouping_strategy": "ALLGREEN",  # every pull request in a group must pass
    "max_entries_to_build": 5,
    "max_entries_to_merge": 5,
    "min_entries_to_merge": 1,
    "min_entries_to_merge_wait_minutes": 0,
}
QUEUE_TIMEOUT = 60  # minutes, with no CI history: GitHub's own default
QUEUE_TIMEOUT_MAX = 360  # GitHub's cap


def queue_timeout(longest: int | None) -> int:
    """The check timeout for the base's longest recent CI run (whole minutes,
    or None): twice it, for room to spare, never below the no-history 60, and
    at most GitHub's 360."""
    return min(QUEUE_TIMEOUT_MAX, max(QUEUE_TIMEOUT, 2 * (longest or 0)))


# How doctor's merge_group check words a workflow or a check that isn't ready (#246).
NOT_READY = {
    "missing": "no merge_group trigger",
    "excluded": "a merge_group filter that leaves out the base branch",
    "cant_check": "can't be checked",
    "other_ci": "from another CI service, which must run on pushes to gh-readonly-queue/<base>",
    "no_run": "no run seen",
    "unknown_workflow": "its workflow can't be found",
}


def _not_ready(items, key: str, fine: str) -> list[str]:
    """Each of doctor's `workflows` (key `path`) or `checks` (key `name`)
    whose state isn't `fine`, quoted with what is wrong."""
    return [f"{quote(x[key])} ({NOT_READY.get(x.get('state'), 'not ready')})"
            for x in (items if isinstance(items, list) else [])
            if isinstance(x, dict) and isinstance(x.get(key), str) and x.get("state") != fine]


def _longest_if_clean(report) -> int | None:
    """The longest recent CI run from `workflow doctor --json`, once its
    `merge_group` verdict is clean; raises when it isn't."""
    if not isinstance(report, dict):
        raise ProtectionError("the doctor file must be what `workflow doctor --json` prints (a JSON object)")
    mq = report.get("merge_queue")
    if not isinstance(mq, dict):
        raise ProtectionError("the doctor file has no merge_queue: run `workflow doctor --json` with checks required on a protected base branch, and give its output")
    mg = mq.get("merge_group")
    if not isinstance(mg, dict):
        raise ProtectionError(
            "doctor made no merge_group check: it makes one only where it suggests a merge queue "
            "(an organisation's repository that can have one, its base branch protected, with checks required)"
        )
    if mg.get("clean") is not True:
        lacking = _not_ready(mg.get("workflows"), "path", "ready") + _not_ready(mg.get("checks"), "name", "actions")
        raise ProtectionError(
            "doctor's merge_group check isn't clean: every required check must come from a workflow that also runs on "
            "merge_group on the base branch before the queue goes on"
            + (f"; not ready: {', '.join(lacking)}" if lacking else "; run `workflow doctor` for what it couldn't check")
        )
    signals = mq.get("signals")
    ci = signals.get("ci_minutes") if isinstance(signals, dict) else None
    longest = ci.get("longest") if isinstance(ci, dict) else None
    if longest is not None and (not isinstance(longest, int) or isinstance(longest, bool) or longest < 0):
        raise ProtectionError("the doctor file: merge_queue.signals.ci_minutes.longest must be whole minutes, or null")
    return longest


def merge_queue(ruleset, report, timeout: int | None = None) -> Request:
    """The ruleset with the merge-queue rule (#247) and "up to date" off,
    its required checks kept; refused unless doctor's `merge_group` verdict
    (`report`, `workflow doctor --json`) is clean. The timeout is the
    owner's when given, else `queue_timeout` of doctor's longest CI run.

    A merge-queue rule already there is replaced (one, where it was);
    nothing else changes. A ruleset that isn't active is refused.
    """
    longest = _longest_if_clean(report)
    if timeout is not None and not 1 <= timeout <= QUEUE_TIMEOUT_MAX:
        raise ProtectionError(f"--timeout {timeout} isn't whole minutes from 1 to {QUEUE_TIMEOUT_MAX}, as GitHub takes it")
    if timeout is not None and longest is not None and timeout <= min(longest, QUEUE_TIMEOUT_MAX - 1):
        raise ProtectionError(
            f"--timeout {timeout} isn't above the base branch's longest recent CI run ({longest} minute{'' if longest == 1 else 's'}): "
            + (f"give {QUEUE_TIMEOUT_MAX}, GitHub's most, though groups may still time out at it" if longest >= QUEUE_TIMEOUT_MAX - 1 else "groups would time out")
        )
    path, body = _update(ruleset, "hold a merge queue")
    if ruleset["enforcement"] != "active":
        raise ProtectionError(f"{_checked_name(ruleset, 0)} isn't active (enforcement {quote(ruleset['enforcement'])}), so its queue would enforce nothing")
    rule = next((r for r in body["rules"] if r["type"] == "required_status_checks"), None)
    params = rule.get("parameters") if rule else None
    have = params.get("required_status_checks") if isinstance(params, dict) else None
    if have is not None and not (isinstance(have, list) and all(isinstance(c, dict) and isinstance(c.get("context"), str) for c in have)):
        raise ProtectionError(f"{_checked_name(ruleset, 0)}: required_status_checks must be a list of objects, each with a context")
    if not have:
        raise ProtectionError(
            f"{_checked_name(ruleset, 0)} requires no checks: the queue goes in the ruleset holding the required checks "
            "(\"Require these checks\" adds them), since a queue with no required checks would merge anything"
        )
    params["strict_required_status_checks_policy"] = False
    queue = {"type": "merge_queue", "parameters": {**QUEUE_SETTINGS, "check_response_timeout_minutes": timeout or queue_timeout(longest)}}
    at = next((n for n, r in enumerate(body["rules"]) if r["type"] == "merge_queue"), len(body["rules"]))
    body["rules"] = [r for r in body["rules"] if r["type"] != "merge_queue"]
    body["rules"].insert(at, queue)
    return Request("add the merge queue to the ruleset, with \"up to date\" off", "PUT", path, body)


def _when(v, what: str) -> datetime | None:
    if v is None:
        return None
    if not isinstance(v, str):
        raise ProtectionError(f"the {what} file: a time must be a string, as GitHub gives it")
    try:
        t = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError as e:
        raise ProtectionError(f"the {what} file: {quote(v)} isn't a time") from e
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _whole(pages: list, key: str, what: str) -> None:
    """Raises when the pages hold fewer items than GitHub's total_count says there are."""
    for p in pages:
        t = p.get("total_count")
        if t is not None and (not isinstance(t, int) or isinstance(t, bool) or t < 0):
            raise ProtectionError(f"the {what} file: total_count must be a number, as GitHub gives it")
    total = max((p["total_count"] for p in pages if p.get("total_count") is not None), default=None)
    have = sum(len(p[key]) for p in pages)
    if total is not None and have < total:
        raise ProtectionError(
            f"the {what} file holds {have} of the commit's {total}: fetch every page "
            "(gh api --paginate --slurp, or per_page=100)"
        )


def _check_runs(data, commit: str | None = None, previews: bool = True) -> list[Ran]:
    """The check runs: one response of GET .../check-runs, or its pages from `--paginate --slurp`.

    With `commit`, a run whose `head_sha` names another commit is left out;
    with `previews=False`, the try-it link's runs are, before they are read."""
    what = "check runs"
    pages = data if isinstance(data, list) else [data]
    if not all(isinstance(p, dict) and isinstance(p.get("check_runs"), list) for p in pages):
        raise ProtectionError(f"the {what} file must hold check_runs, as GET repos/<repo>/commits/<ref>/check-runs returns them")
    _whole(pages, "check_runs", what)
    out: list[Ran] = []
    for r in (r for p in pages for r in p["check_runs"]):
        if not isinstance(r, dict) or not isinstance(r.get("name"), str) or not isinstance(r.get("status"), str):
            raise ProtectionError(f"the {what} file: each check run must be an object with a name and a status")
        app = r.get("app")
        if not isinstance(app, dict) or not isinstance(app.get("slug"), str):
            # Without it, the try-it link's check can't be told apart, and would be offered.
            raise ProtectionError(f"the {what} file: each check run must have its app, with a slug, as GitHub gives it")
        started, completed = _when(r.get("started_at"), what), _when(r.get("completed_at"), what)
        if not previews and app["slug"].casefold() in NEVER_OFFERED_APPS:
            continue
        if commit is not None and isinstance(r.get("head_sha"), str) and r["head_sha"].lower() != commit.lower():
            continue
        if r["status"] != "completed":
            result = "pending"
        elif not isinstance(r.get("conclusion"), str):
            raise ProtectionError(f"the {what} file: the completed check run {quote(r['name'])} has no conclusion")
        else:
            result = "passing" if r["conclusion"] in PASSING else "failing"
        out.append(Ran(r["name"], result, completed or started, _id(r), app["slug"].casefold() in NEVER_OFFERED_APPS))
    return out


def _statuses(data, commit: str | None = None) -> list[Ran]:
    """The statuses: GET .../statuses (or its pages), or the combined GET .../status.

    With `commit`, a combined status whose `sha` names another commit is left out."""
    what = "statuses"
    combined = data if isinstance(data, list) and data and all(isinstance(p, dict) and "statuses" in p for p in data) else None
    if isinstance(data, dict):
        combined = [data]
    if combined is not None:  # the combined status, or its pages
        if not all(isinstance(p.get("statuses"), list) for p in combined):
            raise ProtectionError(f"the {what} file must be a list of statuses, or the combined status with its statuses")
        _whole(combined, "statuses", what)
        items = [s for p in combined if commit is None or not isinstance(p.get("sha"), str) or p["sha"].lower() == commit.lower() for s in p["statuses"]]
    elif isinstance(data, list):
        items = [s for p in data for s in p] if data and all(isinstance(p, list) for p in data) else data
    else:
        raise ProtectionError(f"the {what} file must be a list of statuses, as GET repos/<repo>/commits/<ref>/statuses returns them")
    out: list[Ran] = []
    for s in items:
        if not isinstance(s, dict) or not isinstance(s.get("context"), str) or not isinstance(s.get("state"), str) or s["state"] not in STATUS_RESULT:
            raise ProtectionError(f"the {what} file: each status must be an object with a context and a state (success, pending, failure or error)")
        updated, created = _when(s.get("updated_at"), what), _when(s.get("created_at"), what)
        out.append(Ran(s["context"], STATUS_RESULT[s["state"]], updated or created, _id(s)))
    return out


def _id(item: dict) -> int:
    return item["id"] if isinstance(item.get("id"), int) and not isinstance(item.get("id"), bool) else 0


def _collapse(results: list[Ran]) -> list[Ran]:
    """Each name once, with its latest result: the one that finished (or, not
    finished, started; a status: was updated) last. One with no time counts as
    the oldest; at the same time, the higher id wins."""
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    out: dict[str, Ran] = {}
    for r in results:
        have = out.get(r.name)
        if have is None or (r.when or oldest, r.id) >= (have.when or oldest, have.id):
            out[r.name] = r
    return list(out.values())


def latest(check_runs, statuses=None, commit: str | None = None) -> list[Ran]:
    """Each check that ran on the commit, once, with its latest result
    (passing, failing or pending): a re-run, or a check run and a status of the
    same name, counts once (`_collapse`). The try-it link's check runs are
    kept, marked `preview`. With `commit`, results for another commit are left
    out. `workflow merge-check` reads the checks here."""
    return _collapse(_check_runs(check_runs, commit) + _statuses(statuses if statuses is not None else [], commit))


def checks_ran(check_runs, statuses=None, required=()) -> list[dict]:
    """Each check that ran on the commit, with its latest result (`_collapse`),
    less those required. Check runs from the try-it link's app are never
    offered, nor is a name `--check` would refuse (empty, spaces at either end,
    a control character).
    """
    skip = set(required)
    ran = _collapse(_check_runs(check_runs, previews=False) + _statuses(statuses if statuses is not None else []))
    out = [{"name": r.name, "result": r.result} for r in ran if r.name not in skip and _a_check_name(r.name)]
    return sorted(out, key=lambda c: (c["name"].casefold(), c["name"]))


def requests_text(reqs: list[Request]) -> str:
    lines = ["The requests (not sent: send each with `gh api -X <method> <path> --input <body>` or the GitHub MCP tools):"]
    for i, r in enumerate(reqs, 1):
        lines.append(f"{i}. To {r.what}: {r.method} {r.path}")
        lines.append(printable(json.dumps(r.body, indent=2, ensure_ascii=False)))
    return "\n".join(lines)


def ran_text(checks: list[dict], required: list[str]) -> str:
    if checks:
        lines = ["Checks that ran and aren't required yet:"] + [f"- {quote(c['name'])}: {c['result']}" for c in checks]
    else:
        lines = ["No checks that ran are left to require."]
    if required:
        lines.append("Already required: " + ", ".join(quote(n) for n in required))
    return "\n".join(lines)
