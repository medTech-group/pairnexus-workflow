"""Whether a pull request may merge: the merge rule's one implementation.

`workflow merge-check` reads JSON a session hands it (the pull request, its
files, commits, checks, the rulesets, review threads, reviews, comments with
their authors' permissions, the base comparison and the preview) and answers
`ready`, `not_yet` or `owner_review`, with every reason that applies. It reads
only what it is given: it asks GitHub nothing, posts nothing and writes nothing.

Every rule is in `RULES`, each naming the flow §4 item (or #30's condition) it
implements; `tests/test_merge_check.py` fails when flow §4 and `RULES` differ.
Every reason is in `REASONS`, worded for *new to building* and for *developer*;
the decision never depends on the wording. It reuses the kit's readers rather
than repeating them:
- the review records: `reviews.read`;
- the checks on the head commit: `protection.latest` (a name reported twice
  counts by its latest result, the try-it link's check marked);
- the checks the rulesets require: `protection.check`;
- kit and CI files: the guard's own matcher, `guard.matches`.

Anything it can't read is a reason of its own ("couldn't read …"), so malformed
input is never `ready`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import protection, reviews
from .guard import matches
from .posts import CommentsError, _login
from .profile import DEFAULT_PROTECTED

DECISIONS = ("ready", "not_yet", "owner_review")
ACTIONS = ("review", "update_branch", "resolve_conflict", "fix_checks")
INPUTS = {
    "pr": "the pull request",
    "files": "its changed files",
    "commits": "its commits",
    "checks": "the head commit's checks",
    "rulesets": "the repository's rulesets",
    "threads": "its review threads",
    "reviews": "its reviews",
    "comments": "its comments",
    "permissions": "the authors' permissions",
    "compare": "the base comparison",
    "preview": "the preview's status",
    "profile": "the profile",
}
# Permissions whose review records and "changes requested" count (#36).
WRITE = ("admin", "maintain", "write")
_SHA = re.compile(r"[0-9a-f]{40}")
PREVIEWS_DOC = Path(__file__).resolve().parents[2] / "docs/previews.md"


class Unreadable(Exception):
    """An input this rule needs couldn't be read."""

    def __init__(self, name: str, why: str):
        super().__init__(why)
        self.name, self.why = name, why


@dataclass(frozen=True)
class Rule:
    id: str
    implements: str  # "flow §4.<n>", or "#30" for #30's conditions
    judge: Callable


@dataclass(frozen=True)
class Reason:
    rule: str
    action: str | None
    # level -> (message, fix); both formatted with the reason's details.
    wording: dict


@dataclass
class Result:
    decision: str
    pr: int | None
    head: str | None
    level: str
    owner: bool
    reasons: list[dict] = field(default_factory=list)
    notes: list[dict] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    preview: dict | None = None

    def as_dict(self) -> dict:
        return {
            "decision": self.decision,
            "pr": self.pr,
            "head": self.head,
            "experience": self.level,
            "owner": self.owner,
            "reasons": self.reasons,
            "notes": self.notes,
            "checks": self.checks,
            "files": self.files,
            "preview": self.preview,
        }


# ---------- the reasons, worded for both levels ----------

REASONS = {
    "couldnt_read": Reason("", None, {
        "new": ("Not yet: couldn't read {what}: {why}.", "Ask Claude to fetch it again, then ask again."),
        "developer": ("Not yet: couldn't read {what} (--{input}): {why}.", "Pass --{input} as GitHub returns it, then run merge-check again."),
    }),
    "checks_pending": Reason("checks", None, {
        "new": ("Not yet: the checks are still running ({names}).", "Wait a few minutes and ask again."),
        "developer": ("Not yet: required checks pending on {short}: {names}.", "Wait for CI to finish, then run merge-check again."),
    }),
    "checks_failed": Reason("checks", "fix_checks", {
        "new": ("Not yet: some checks failed: {names}.", "Ask Claude to fix it."),
        "developer": ("Not yet: required checks failed on {short}: {names}.", "Fix the failures and push; CI runs again."),
    }),
    "no_checks": Reason("checks", None, {
        "new": ("Not yet: no checks have run on this commit.", "Wait for the checks to start. If this project has no automatic checks (CI), the profile should say `ci.none = true`."),
        "developer": ("Not yet: no checks ran on {short}, and none are required by the rulesets or `ci.required_checks`.", "Wait for CI; for a project without CI, set `ci.none = true` in the profile."),
    }),
    "required_unknown": Reason("checks", None, {
        "new": ("Not yet: couldn't tell which checks this project requires.", "Ask Claude to check the set-up."),
        "developer": ("Not yet: couldn't tell which checks the rulesets require: {why}.", "Give the PR file with base.repo.default_branch, or read the rulesets back with `workflow protection`."),
    }),
    "evidence_missing": Reason("evidence", None, {
        "new": ("Not yet: the tests' results haven't been posted for this commit.", "Ask Claude to run the tests and post their results."),
        "developer": ("Not yet: no `workflow evidence` report read for {short} (the profile says `ci.none`).", "Run `workflow evidence --base-ref origin/{base}` and post the report."),
    }),
    "behind": Reason("up_to_date", "update_branch", {
        "new": ("Not yet: {base} has moved on since this was made.", "Bring it up to date: Claude merges {base} in, and the checks run again."),
        "developer": ("Not yet: the branch is {behind} behind {base}.", "Merge {base} in and push; CI runs again."),
    }),
    "no_review": Reason("review_panel", "review", {
        "new": ("Not yet: nobody has reviewed this change.", "Review it now: Claude runs the review panel."),
        "developer": ("Not yet: no review record from an account with write access on this PR.", "Run the review panel; each round posts its record."),
    }),
    "review_not_clean": Reason("review_panel", "review", {
        "new": ("Not yet: the last review found things to fix.", "Fix them, then review it again."),
        "developer": ("Not yet: review round {round} on {round_short} wasn't clean.", "Fix the findings and run another round."),
    }),
    "review_stale": Reason("review_panel", "review", {
        "new": ("Not yet: the newest changes haven't been reviewed.", "Review it now: a short check of the latest changes."),
        "developer": ("Not yet: the last clean round covers {round_short}, not the head {short}, and no later clean Correctness pass covers the head.", "Run a Correctness pass on the head (review-panel §5)."),
    }),
    "conflict": Reason("conflict", "resolve_conflict", {
        "new": ("Not yet: this change clashes with something already in {base}.", "Ask Claude to resolve the conflict."),
        "developer": ("Not yet: merge conflict with {base}.", "Merge {base} in, resolve the conflicts and push."),
    }),
    "mergeable_unknown": Reason("conflict", None, {
        "new": ("Not yet: GitHub is still checking this change.", "Ask again in a minute."),
        "developer": ("Not yet: GitHub hasn't worked out whether it merges cleanly (mergeable unknown).", "Ask again in a minute."),
    }),
    "unresolved_threads": Reason("people", None, {
        "new": ("Not yet: {who} asked about the code, and it hasn't been resolved.", "Answer each question, then resolve the conversation."),
        "developer": ("Not yet: {count} unresolved review thread(s), from {who}.", "Address and resolve them."),
    }),
    "changes_requested": Reason("people", None, {
        "new": ("Not yet: {who} asked for changes.", "Make the changes, then ask {who} to look again."),
        "developer": ("Not yet: changes requested by {who}, not since approved or re-requested.", "Address them and re-request the review."),
    }),
    "preview_failed": Reason("preview", None, {
        "new": ("Not yet: the try-it link didn't build.", "Ask Claude to find out why."),
        "developer": ("Not yet: the preview build failed for {short}.", "Fix the preview build and push."),
    }),
    "preview_building": Reason("preview", None, {
        "new": ("Not yet: the try-it link is still building.", "Ask again in a few minutes."),
        "developer": ("Not yet: the preview for the head {short} isn't built yet (state {state}, commit {commit}).", "Wait for the preview build, then run merge-check again."),
    }),
}


# ---------- reading the inputs ----------


def _walk(value, name: str, is_item: Callable[[dict], bool], keys: tuple[str, ...]) -> list[dict]:
    """The items in `value`: a list of them, pages of them, or an object
    holding them under one of `keys` (nested, as GraphQL nests them)."""
    out: list[dict] = []

    def go(v, depth: int) -> None:
        if depth > 8:
            raise Unreadable(name, "it is nested deeper than GitHub nests it")
        if isinstance(v, list):
            for x in v:
                go(x, depth + 1)
        elif isinstance(v, dict) and is_item(v):
            out.append(v)
        elif isinstance(v, dict) and any(k in v for k in keys):
            for k in keys:
                if k in v:
                    go(v[k], depth + 1)
                    return
        else:
            raise Unreadable(name, f"it holds a {type(v).__name__} that isn't one of {INPUTS[name]}")

    go(value, 0)
    return out


def _sha(v) -> str | None:
    return v.lower() if isinstance(v, str) and _SHA.fullmatch(v.lower()) else None


@dataclass
class PR:
    number: int | None
    head: str
    base: str
    default_branch: str | None
    mergeable: bool | None
    behind: bool  # GitHub's mergeable_state says behind
    requested: set[str]


def _pr(v, fallback_base: str) -> PR:
    if not isinstance(v, dict):
        raise Unreadable("pr", "it isn't a JSON object, as GET repos/<repo>/pulls/<n> returns one")
    head = v.get("head")
    sha = _sha(head.get("sha") if isinstance(head, dict) else v.get("headRefOid"))
    if sha is None:
        raise Unreadable("pr", "its head commit isn't a full 40-character SHA (head.sha)")
    base = v.get("base")
    ref = base.get("ref") if isinstance(base, dict) else v.get("baseRefName")
    ref = ref if isinstance(ref, str) and ref else fallback_base
    repo = base.get("repo") if isinstance(base, dict) else None
    default = repo.get("default_branch") if isinstance(repo, dict) and isinstance(repo.get("default_branch"), str) else None
    m = v.get("mergeable")
    state = str(v.get("mergeable_state") or v.get("mergeStateStatus") or "").lower()
    if m in (True, "MERGEABLE"):
        mergeable = True
    elif m in (False, "CONFLICTING") or state == "dirty":
        mergeable = False
    elif m in (None, "UNKNOWN"):
        mergeable = None
    else:
        raise Unreadable("pr", "its mergeable is neither true, false nor null")
    requested: set[str] = set()
    for r in v.get("requested_reviewers") or v.get("reviewRequests") or []:
        who = r.get("requestedReviewer", r) if isinstance(r, dict) else r
        login = who.get("login") if isinstance(who, dict) else who
        if isinstance(login, str) and login:
            requested.add(login.casefold())
    number = v.get("number") if isinstance(v.get("number"), int) and not isinstance(v.get("number"), bool) else None
    return PR(number, sha, ref, default, mergeable, state == "behind", requested)


def _permissions(v) -> dict[str, str]:
    """Login (casefolded) -> permission, from a map, GET .../collaborators/<u>/permission
    responses, or the collaborators list."""
    rank = {"admin": 5, "maintain": 4, "write": 3, "triage": 2, "read": 1, "none": 0}
    out: dict[str, str] = {}

    def put(login, perm) -> None:
        if not isinstance(login, str) or not login or perm not in rank:
            raise Unreadable("permissions", "each entry needs a login and a permission (admin, maintain, write, triage, read or none)")
        have = out.get(login.casefold())
        if have is None or rank[perm] > rank[have]:
            out[login.casefold()] = perm

    def one(e: dict) -> None:
        user = e.get("user")
        login = e.get("login") or (user.get("login") if isinstance(user, dict) else None)
        perms = []
        for k in ("role_name", "permission"):
            if isinstance(e.get(k), str) and e[k].lower() in rank:
                perms.append(e[k].lower())
        flags = e.get("permissions")
        if isinstance(flags, dict):
            for flag, perm in (("admin", "admin"), ("maintain", "maintain"), ("push", "write"), ("triage", "triage"), ("pull", "read")):
                if flags.get(flag) is True:
                    perms.append(perm)
        if not perms:
            raise Unreadable("permissions", "an entry has no permission")
        for perm in perms:
            put(login, perm)

    if isinstance(v, dict) and v and all(isinstance(x, str) for x in v.values()) and not ({"login", "user", "permission"} & set(v)):
        for login, perm in v.items():
            put(login, perm.lower())
        return out
    for e in _walk(v, "permissions", lambda d: any(k in d for k in ("permission", "role_name", "permissions")), ("collaborators",)):
        one(e)
    return out


def _counts(login: str | None, perms: dict[str, str]) -> bool:
    return bool(login) and perms.get(login.casefold()) in WRITE


# ---------- the context the rules read ----------


class Context:
    def __init__(self, inputs: dict, profile, profile_error: str | None):
        self.inputs = inputs
        self.profile = profile
        self.profile_error = profile_error
        self.notes: list[dict] = []
        self.checks: list[dict] = []
        self.preview: dict | None = None
        self.kit: list[str] = []
        self._cache: dict = {}

    def raw(self, name: str):
        got = self.inputs.get(name)
        if got is None:
            raise Unreadable(name, f"it wasn't given (--{name})")
        value, error = got
        if error is not None:
            raise Unreadable(name, error)
        return value

    def _once(self, name, fn):
        if name not in self._cache:
            try:
                self._cache[name] = (fn(), None)
            except Unreadable as e:
                self._cache[name] = (None, e)
            except (CommentsError, protection.ProtectionError) as e:
                self._cache[name] = (None, Unreadable(name, str(e)))
            except (TypeError, ValueError, AttributeError, KeyError, RecursionError):
                self._cache[name] = (None, Unreadable(name, f"it isn't in the shape GitHub gives {INPUTS[name]}"))
        value, error = self._cache[name]
        if error is not None:
            raise error
        return value

    @property
    def base_fallback(self) -> str:
        return self.profile.base_branch if self.profile else "main"

    def pr(self) -> PR:
        return self._once("pr", lambda: _pr(self.raw("pr"), self.base_fallback))

    def permissions(self) -> dict[str, str]:
        return self._once("permissions", lambda: _permissions(self.raw("permissions")))

    def commits(self) -> set[str]:
        def read():
            items = _walk(self.raw("commits"), "commits", lambda d: "sha" in d or "oid" in d, ("commits", "nodes"))
            shas = {_sha(c.get("sha") or c.get("oid")) for c in items}
            if None in shas:
                raise Unreadable("commits", "a commit's SHA isn't a full 40-character SHA")
            return shas
        return self._once("commits", read)

    def files(self) -> list[str]:
        def read():
            out: list[str] = []
            for f in _walk(self.raw("files"), "files", lambda d: "filename" in d or "path" in d, ("files", "nodes")):
                for k in ("filename", "path", "previous_filename"):
                    if k in f and (not isinstance(f[k], str) or not f[k]):
                        raise Unreadable("files", f"a file's {k} isn't a path")
                    if isinstance(f.get(k), str) and f[k] not in out:
                        out.append(f[k])
            return out
        return self._once("files", read)

    def need_profile(self) -> None:
        if self.profile_error is not None:
            raise Unreadable("profile", self.profile_error)


def _short(sha: str | None) -> str:
    return f"`{sha[:7]}`" if sha else "the head"


def _names(names) -> str:
    return ", ".join(f"`{n}`" for n in names)


def _who(logins) -> str:
    return ", ".join(f"@{w}" for w in logins) or "someone"


# ---------- the rules ----------


def _checks(ctx: Context, add) -> None:
    """flow §4.1: every required check ran on the head commit and passed; none pending."""
    ctx.need_profile()
    pr = ctx.pr()
    prof = ctx.profile

    def read_checks():
        runs: list = []
        statuses: list = []
        flat: list = []

        def go(v, depth: int) -> None:
            if depth > 4:
                raise Unreadable("checks", "it is nested deeper than GitHub nests it")
            if isinstance(v, list):
                for x in v:
                    go(x, depth + 1)
            elif isinstance(v, dict) and "check_runs" in v:
                runs.append(v)
            elif isinstance(v, dict) and "statuses" in v:
                statuses.append(v)
            elif isinstance(v, dict) and "context" in v:
                flat.append(v)
            else:
                raise Unreadable("checks", "it holds neither check runs (check_runs) nor statuses")

        go(ctx.raw("checks"), 0)
        if flat:
            statuses.append({"statuses": flat})
        return protection.latest(runs, statuses, pr.head)

    ran = ctx._once("checks", read_checks)

    def read_rulesets():
        settings = {"default_branch": pr.default_branch} if pr.default_branch else None
        return protection.check(ctx.raw("rulesets"), pr.base, settings)

    rep = ctx._once("rulesets", read_rulesets)
    if rep.unsure:
        add("required_unknown", why="; ".join(rep.unsure))
    from_rules = list(rep.required_checks)
    from_profile = list(prof.required_checks) if prof else []
    required = from_rules + [c for c in from_profile if c not in from_rules]
    if from_rules and set(from_rules) != set(from_profile) and not (prof and prof.ruleset is False):
        only_rules = [c for c in from_rules if c not in from_profile]
        only_profile = [c for c in from_profile if c not in from_rules]
        parts = []
        if only_rules:
            parts.append(f"only the rulesets require {_names(only_rules)}")
        if only_profile:
            parts.append(f"only the profile's `ci.required_checks` lists {_names(only_profile)}")
        ctx.notes.append({"id": "lists_differ", "message": "The required checks differ: " + "; ".join(parts) + ". Both count; check the set-up."})
    by_name = {r.name: r for r in ran}
    if not required and not rep.unsure:
        required = [r.name for r in ran if not r.preview]
        if not required:
            if not (prof and prof.ci_none):
                add("no_checks")
    pending = [n for n in required if n not in by_name or by_name[n].result == "pending"]
    failed = [n for n in required if n in by_name and by_name[n].result == "failing"]
    for n in required:
        ctx.checks.append({"name": n, "state": by_name[n].result if n in by_name else "missing", "required": True})
    others = sorted((r for r in ran if r.name not in required), key=lambda r: (r.name.casefold(), r.name))
    for r in others:
        ctx.checks.append({"name": r.name, "state": r.result, "required": False})
    if pending:
        add("checks_pending", names=", ".join(f"`{n}`" + (" (not started)" if n not in by_name else "") for n in pending))
    if failed:
        add("checks_failed", names=_names(failed))
    loose = [r.name for r in others if r.result == "failing" and not r.preview]
    if loose:
        ctx.notes.append({"id": "failed_not_required", "message": f"Failed, but not required, so it doesn't block: {_names(loose)}."})


def _evidence(ctx: Context, add) -> None:
    """flow §4.2: the suite's evidence where the profile says `ci.none`. Reading
    the report is #81's; until then `ci.none` is never ready."""
    ctx.need_profile()
    if ctx.profile and ctx.profile.ci_none:
        ctx.pr()
        add("evidence_missing")


def _up_to_date(ctx: Context, add) -> None:
    """flow §4.3: the head isn't behind the base."""
    pr = ctx.pr()

    def read():
        v = ctx.raw("compare")
        if not isinstance(v, dict) or not isinstance(v.get("behind_by"), int) or isinstance(v["behind_by"], bool) or v["behind_by"] < 0:
            raise Unreadable("compare", "it has no behind_by, as GET repos/<repo>/compare/<base>...<head> gives it")
        return v["behind_by"]

    behind = ctx._once("compare", read)
    if behind or pr.behind:
        add("behind", behind=f"{behind} commit{'s' if behind != 1 else ''}" if behind else "behind")


def _panel(ctx: Context, add) -> None:
    """flow §4.4: a clean round on the head, or on an earlier commit of the PR
    with a later clean Correctness pass on the head. Records from accounts
    without write access, or naming a commit outside the PR, are ignored."""
    pr = ctx.pr()
    perms = ctx.permissions()
    shas = ctx.commits() | {pr.head}
    records = ctx._once("comments", lambda: reviews.read(ctx.raw("comments")))
    counted = [r for r in records if _counts(r.author, perms) and r.commit in shas]
    left_out = len(records) - len(counted)
    if left_out:
        ctx.notes.append({"id": "records_ignored", "message": f"{left_out} review record(s) left out: posted by an account without write access, or naming a commit outside this pull request."})
    rounds = [i for i, r in enumerate(counted) if r.kind == "round"]
    if not rounds:
        add("no_review")
        return
    last = counted[rounds[-1]]
    details = {"round": last.round, "round_short": _short(last.commit)}
    if not last.clean:
        add("review_not_clean", **details)
        return
    if last.commit == pr.head:
        return
    passes = [r for r in counted[rounds[-1] + 1:] if r.kind == "pass" and r.commit == pr.head]
    if passes and passes[-1].clean:
        return
    add("review_stale", **details)


def _conflict(ctx: Context, add) -> None:
    """#30: the PR is mergeable."""
    pr = ctx.pr()
    if pr.mergeable is False:
        add("conflict")
    elif pr.mergeable is None:
        add("mergeable_unknown")


def _people(ctx: Context, add) -> None:
    """#30: no unresolved review thread, and no "changes requested" (from an
    account with write access) not followed by that reviewer's approval or a
    new review request. Conversation comments never block."""
    pr = ctx.pr()

    def read_threads():
        items = _walk(
            ctx.raw("threads"), "threads",
            lambda d: any(k in d for k in ("isResolved", "is_resolved", "resolved")),
            ("data", "repository", "pullRequest", "reviewThreads", "review_threads", "threads", "nodes"),
        )
        out = []
        for t in items:
            resolved = next(t[k] for k in ("isResolved", "is_resolved", "resolved") if k in t)
            if not isinstance(resolved, bool):
                raise Unreadable("threads", "a thread's resolved state isn't true or false")
            if not resolved:
                comments = t.get("comments")
                comments = comments.get("nodes") if isinstance(comments, dict) else comments
                first = comments[0] if isinstance(comments, list) and comments and isinstance(comments[0], dict) else {}
                out.append(_login(first) or "someone")
        return out

    def read_reviews():
        items = _walk(ctx.raw("reviews"), "reviews", lambda d: "state" in d, ("reviews", "nodes"))
        for r in items:
            if not isinstance(r.get("state"), str):
                raise Unreadable("reviews", "a review's state isn't text")
        return [(_login(r), r["state"].upper()) for r in items]

    open_threads = ctx._once("threads", read_threads)
    revs = ctx._once("reviews", read_reviews)
    if open_threads:
        add("unresolved_threads", who=_who(dict.fromkeys(open_threads)), count=len(open_threads))
    perms = ctx.permissions()
    standing: dict[str, str] = {}
    for login, state in revs:
        if state in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED") and _counts(login, perms):
            standing[login] = state
    asked = [w for w, s in standing.items() if s == "CHANGES_REQUESTED" and w.casefold() not in pr.requested]
    if asked:
        add("changes_requested", who=_who(asked))


def _preview(ctx: Context, add) -> None:
    """#30: where the project has previews, the head commit's built."""
    pr = ctx.pr()
    if ctx.inputs.get("preview") is None:
        state, url, commit = "none", None, None
    else:
        v = ctx.raw("preview")
        if not isinstance(v, dict) or v.get("state") not in ("built", "building", "failed", "none"):
            raise Unreadable("preview", "its state isn't built, building, failed or none")
        state, url, commit = v["state"], v.get("url"), v.get("commit")
        if url is not None and not isinstance(url, str):
            raise Unreadable("preview", "its url isn't text")
    if state == "none":
        how = " `docs/previews.md` says how to add them." if PREVIEWS_DOC.exists() else ""
        ctx.notes.append({"id": "no_previews", "message": f"There's no try-it link for this project: check the change another way, as the PR's \"How to try it\" says.{how}"})
        return
    for_head = isinstance(commit, str) and len(commit) >= 7 and pr.head.startswith(commit.lower())
    if state == "failed" and (for_head or commit is None):
        add("preview_failed")
    elif state == "built" and for_head and url:
        ctx.preview = {"state": "built", "url": url}
    else:
        add("preview_building", state=state, commit=_short(commit if isinstance(commit, str) else None))


def _kit_files(ctx: Context, add) -> None:
    """#30: a change to the kit's or CI files (the profile's protected paths,
    matched as the guard matches them) is the owner's to merge. It never says
    "Not yet" itself: with everything else holding, the answer is `owner_review`."""
    patterns = list(ctx.profile.protected_paths) if ctx.profile else list(DEFAULT_PROTECTED)
    ctx.kit = [f for f in ctx.files() if matches(f, patterns)]


RULES = (
    Rule("checks", "flow §4.1", _checks),
    Rule("evidence", "flow §4.2", _evidence),
    Rule("up_to_date", "flow §4.3", _up_to_date),
    Rule("review_panel", "flow §4.4", _panel),
    Rule("conflict", "#30", _conflict),
    Rule("people", "#30", _people),
    Rule("preview", "#30", _preview),
    Rule("kit_files", "#30", _kit_files),
)


# ---------- the decision ----------


def _reason(rid: str, rule: Rule, level: str, details: dict) -> dict:
    reason = REASONS[rid]
    wording = {lvl: {"message": m.format(**details), "fix": f.format(**details)} for lvl, (m, f) in reason.wording.items()}
    out = {"id": rid, "rule": rule.id, "implements": rule.implements, **wording[level], "action": reason.action, "wording": wording}
    if rid == "couldnt_read":
        out["input"] = details["input"]
    return out


def evaluate(inputs: dict, profile=None, profile_error: str | None = None, asker: str | None = None, level: str = "new") -> Result:
    """The decision. `inputs` maps each name in INPUTS (but the profile) to
    (value, None) when read, (None, why) when it couldn't be; a name left out
    wasn't given (the preview: none)."""
    ctx = Context(inputs, profile, profile_error)
    reasons: list[dict] = []
    unreadable: set[str] = set()
    for rule in RULES:
        found: list[tuple[str, dict]] = []

        def add(rid: str, **details) -> None:
            found.append((rid, details))

        try:
            rule.judge(ctx, add)
        except Unreadable as e:
            if e.name not in unreadable:
                unreadable.add(e.name)
                found = [("couldnt_read", {"input": e.name, "what": INPUTS[e.name], "why": e.why.rstrip(".")})]
            else:
                found = []
        for rid, details in found:
            try:
                pr = ctx.pr()
                head, base = pr.head, pr.base
            except Unreadable:
                head, base = None, ctx.base_fallback
            reasons.append(_reason(rid, rule, level, {"short": _short(head), "base": base, **details}))

    try:
        pr = ctx.pr()
        number, head = pr.number, pr.head
    except Unreadable:
        number, head = None, None
    owner = False
    if asker:
        who = asker.strip().lstrip("@").casefold()
        if profile and profile.owner:
            owner = who == profile.owner.casefold()
        else:
            try:
                owner = ctx.permissions().get(who) == "admin"
            except Unreadable:
                owner = False
    kit = ctx.kit
    if reasons:
        decision = "not_yet"
        if kit:
            ctx.notes.append({"id": "kit_files", "message": "This change touches the kit's or CI files (" + _names(kit) + "): once everything else holds, it needs the owner's review."})
    elif kit:
        decision = "owner_review"
    else:
        decision = "ready"
    return Result(decision, number, head, level, owner, reasons, ctx.notes, ctx.checks, kit, ctx.preview)


# ---------- text ----------


def text(res: Result) -> str:
    n = f"#{res.pr}" if res.pr is not None else "This pull request"
    if res.decision == "ready":
        lines = [f"Ready: {n} may merge."]
    elif res.decision == "owner_review":
        if res.owner:
            lines = ["Ready once you've read the changes to these files:"]
        else:
            lines = [f"Needs the owner's review: {n} changes the kit's or CI files, which only the owner merges:"]
        lines += [f"- `{f}`" for f in res.files]
    else:
        lines = [f"Not yet: {n} isn't ready to merge."]
        lines += [f"- {r['message']} {r['fix']}" for r in res.reasons]
    if res.preview:
        lines.append(f"Try it first: {res.preview['url']}")
    if res.notes:
        lines.append("Notes:")
        lines += [f"  {x['message']}" for x in res.notes]
    if res.checks:
        lines.append(f"Checks on {_short(res.head)}:")
        lines += [f"  {c['name']}: {c['state']}" + (" (required)" if c["required"] else "") for c in res.checks]
    return "\n".join(lines)
