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

Every input is read before any rule runs (`Context.read_all`), so each one it
can't read is a reason of its own ("couldn't read …"), never `ready`. A list
GitHub says is longer than the file (a page left out) is one it can't read:
the pull request's own counts, GraphQL's `totalCount` and `pageInfo` say so.
"""

from __future__ import annotations

import re
from urllib.parse import unquote
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import protection, reviews
from .guard import matches
from .posts import CommentsError, _login, comments_from
from .profile import DEFAULT_PROTECTED

# The inputs, each given by its own flag (`--<name>`), and what each is called.
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
}
PROFILE = "profile"  # read from the project, not given by a flag
# How GraphQL nests a pull request's lists.
GRAPHQL = ("data", "repository", "pullRequest")
# Where the pull request says how long each list is (REST, then gh's --json).
COUNT_KEYS = {"files": "changed_files", "comments": "comments", "commits": "commits"}
GH_COUNT_KEYS = {"files": "changedFiles", "comments": "comments", "commits": "commits"}
# Permissions whose review records and "changes requested" count (#36).
WRITE = ("admin", "maintain", "write")
RANK = {"admin": 5, "maintain": 4, "write": 3, "triage": 2, "read": 1, "none": 0}
# GitHub lists at most this many of a pull request's files, and of its commits.
MAX_FILES = 3000
MAX_COMMITS = 250
PARTIAL = "it holds only part of the list: fetch every page (gh api --paginate --slurp; with GraphQL, until pageInfo.hasNextPage is false)"
_SHA = re.compile(r"[0-9a-f]{40}")
_STATUS_URL_SHA = re.compile(r"/statuses/([0-9a-fA-F]{40})\b")
PREVIEWS_DOC = Path(__file__).resolve().parents[2] / "docs/previews.md"


class Unreadable(Exception):
    """An input couldn't be read: `name` is the input, `why` says what was wrong."""

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
    rule: str  # the Rule's id; "" for couldn't-read, which belongs to an input
    action: str | None  # review, update_branch, resolve_conflict, fix_checks
    # level -> (message, fix); both formatted with the reason's details.
    wording: dict


@dataclass
class Result:
    decision: str  # ready, not_yet or owner_review
    pr: int | None
    head: str | None
    level: str
    owner: bool  # the asker counts as the owner
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
        "new": ("Not yet: couldn't read {what}.", "Ask Claude to fetch the pull request's details again, then ask again."),
        "developer": ("Not yet: couldn't read {what} (--{input}): {why}.", "Give --{input} as GitHub returns it, every page, then run merge-check again."),
    }),
    # The profile isn't fetched: its own wording, still the id `couldnt_read`.
    "couldnt_read_profile": Reason("", None, {
        "new": ("Not yet: couldn't read this project's settings (the profile).", "Ask Claude to repair `.claude/workflow/profile.toml`."),
        "developer": ("Not yet: couldn't read the profile: {why}.", "Fix `.claude/workflow/profile.toml`; `workflow profile check` says what's wrong."),
    }),
    "checks_pending": Reason("checks", None, {
        "new": ("Not yet: the checks are still running: {names}.", "Wait a few minutes and ask again. If a check never starts, ask Claude to check the set-up."),
        "developer": ("Not yet: required checks pending on {short}: {names}.", "Wait for CI. A check that never starts may have been renamed: compare the rulesets and `ci.required_checks` with the jobs CI runs."),
    }),
    "checks_failed": Reason("checks", "fix_checks", {
        "new": ("Not yet: some checks failed: {names}.", "Ask Claude to fix it."),
        "developer": ("Not yet: required checks failed on {short}: {names}.", "Fix the failures and push; CI runs again."),
    }),
    "no_checks": Reason("checks", None, {
        "new": ("Not yet: no checks have run on this commit.", "Wait for the checks to start. If this project has no automatic checks (CI), the profile should say `ci.none = true`."),
        "developer": ("Not yet: no checks ran on {short}, and neither the rulesets nor `ci.required_checks` require any.", "Wait for CI; for a project without CI, set `ci.none = true` in the profile."),
    }),
    "required_unknown": Reason("checks", None, {
        "new": ("Not yet: couldn't tell which checks this project requires.", "Ask Claude to fetch the pull request again with its base branch's repository, or to check the set-up."),
        "developer": ("Not yet: couldn't tell which checks the rulesets require: {why}.", "Give --pr with base.repo.default_branch (GET repos/<repo>/pulls/<n>), or read the rulesets back with `workflow protection`."),
    }),
    "evidence_missing": Reason("evidence", None, {
        "new": ("Not yet: the tests' results haven't been posted for this commit.", "Ask Claude to run the tests and post their results."),
        "developer": ("Not yet: no `workflow evidence` report read for {short} (the profile says `ci.none`).", "Run `workflow evidence --base-ref origin/{base}` and post the report."),
    }),
    "behind": Reason("up_to_date", "update_branch", {
        "new": ("Not yet: {base} has moved on since this was made.", "Bring it up to date: Claude merges {base} in, and the checks run again."),
        "developer": ("Not yet: the branch is behind {base}{by}.", "Merge {base} in and push; CI runs again."),
    }),
    "no_review": Reason("review_panel", "review", {
        "new": ("Not yet: nobody has reviewed this change.", "Review it now: Claude runs the review panel."),
        "developer": ("Not yet: no review record from an account with write access on this PR.", "Run the review panel; each round posts its record."),
    }),
    "review_not_clean": Reason("review_panel", "review", {
        "new": ("Not yet: the last review found things to fix.", "Fix them, then review it again."),
        "developer": ("Not yet: review round {round} on {round_short} wasn't clean.", "Fix the findings and run another round."),
    }),
    "pass_not_clean": Reason("review_panel", "review", {
        "new": ("Not yet: the last check of the newest changes found things to fix.", "Fix them, then ask Claude to check again."),
        "developer": ("Not yet: the Correctness pass on {short} after round {round} wasn't clean.", "Fix the findings and run another pass."),
    }),
    "review_stale": Reason("review_panel", "review", {
        "new": ("Not yet: the newest changes haven't been reviewed.", "Review it now: a short check of the latest changes."),
        "developer": ("Not yet: the last clean round covers {round_short}, not the head {short}, and no later clean Correctness pass covers the head.", "Run a Correctness pass on the head (review-panel §5)."),
    }),
    "conflict": Reason("mergeable", "resolve_conflict", {
        "new": ("Not yet: this change clashes with something already in {base}.", "Ask Claude to resolve the conflict."),
        "developer": ("Not yet: merge conflict with {base}.", "Merge {base} in, resolve the conflicts and push."),
    }),
    "mergeable_unknown": Reason("mergeable", None, {
        "new": ("Not yet: GitHub is still checking this change.", "Ask again in a minute."),
        "developer": ("Not yet: GitHub hasn't worked out whether it merges cleanly (mergeable unknown).", "Ask again in a minute."),
    }),
    "draft": Reason("mergeable", None, {
        "new": ("Not yet: this change is still marked as a draft.", "Mark it ready for review once it's done, or ask Claude to."),
        "developer": ("Not yet: the pull request is a draft.", "Mark it ready for review (`gh pr ready {number}`)."),
    }),
    "closed": Reason("mergeable", None, {
        "new": ("Not open: this pull request is closed or has already merged.", "Nothing to merge. If it should still go in and hasn't merged, reopen it."),
        "developer": ("Not open: the pull request's state is {state}.", "If it should still go in and hasn't merged, reopen it."),
    }),
    "unresolved_threads": Reason("people", None, {
        "new": ("Not yet: {who} asked about the code, and it hasn't been resolved.", "Answer each question, then resolve the conversation."),
        "developer": ("Not yet: {threads} from {who}.", "Address and resolve each one."),
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
        "developer": ("Not yet: {what}.", "Wait for the preview of the head, then run merge-check again."),
    }),
}


# ---------- small helpers ----------


def _plural(n: int, one: str, many: str | None = None) -> str:
    """`n` and the noun, singular or plural: "1 thread", "2 threads"."""
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _sha(v) -> str | None:
    """A full SHA, lowercased; None when `v` isn't one."""
    return v.lower() if isinstance(v, str) and _SHA.fullmatch(v.lower()) else None


def _int(v) -> int | None:
    """A whole number GitHub gives (not a bool), else None."""
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def _time(v) -> datetime | None:
    """A GitHub timestamp, or None when it isn't one."""
    if not isinstance(v, str):
        return None
    try:
        t = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _in_time_order(items: list, when: Callable, number: Callable) -> list:
    """`items` oldest first by `when(item)`, then by `number(item)` (GitHub's
    ids grow with time), when every item has a time; otherwise as given
    (GitHub's order). Items alike in both keep their order."""
    times = [when(x) for x in items]
    if any(t is None for t in times):
        return items
    keyed = [(t, _int(number(x)) or 0, i, x) for i, (t, x) in enumerate(zip(times, items))]
    return [x for *_, x in sorted(keyed, key=lambda k: k[:3])]


def _short(sha: str | None) -> str:
    """A SHA as people read it: its first seven characters, in backticks."""
    return f"`{sha[:7]}`" if sha else "the head"


def _clean(text: str) -> str:
    """Text from the input as a message shows it: a line break or control
    character escaped, so it can't make a line of its own."""
    return "".join(c if unicodedata.category(c) not in ("Cc", "Cf", "Cs", "Zl", "Zp") else f"\\u{ord(c):04x}" for c in str(text))


def _names(names) -> str:
    """Check or file names for a message: each in backticks."""
    return ", ".join(f"`{_clean(n)}`" for n in names)


def _who(logins) -> str:
    """Logins for a message (`@dev`); a missing one is "someone"."""
    return ", ".join(f"@{_clean(w)}" if w else "someone" for w in logins) or "someone"


def _walk(value, name: str, is_item: Callable[[dict], bool], keys: tuple[str, ...] = (), counted: bool = False) -> list[dict]:
    """The items in `value`: a list of them, pages of them, or an object
    holding them under one of `keys` (nested, as GraphQL nests them).

    Raises Unreadable for anything else, and for a GraphQL list fetched only in
    part: its pages (`gh api graphql --paginate --slurp`) taken together hold
    fewer nodes than `totalCount`, or the last says `pageInfo.hasNextPage`, or
    the first `hasPreviousPage`. With `counted`, a list that doesn't say how
    long it is (no `totalCount` or `pageInfo`) can't be read either."""
    out: list[dict] = []
    pages: list[tuple[bool, bool, int | None, int]] = []  # (has previous, has next, total, nodes)

    def flag(page, key) -> bool:
        v = page.get(key, False) if isinstance(page, dict) else False
        if not isinstance(v, bool):
            raise Unreadable(name, f"its pageInfo.{key} isn't true or false")
        return v

    def go(v, depth: int) -> None:
        if depth > 8:
            raise Unreadable(name, "it is nested deeper than GitHub nests it")
        if isinstance(v, list):
            for x in v:
                go(x, depth + 1)
        elif isinstance(v, dict) and any(isinstance(v.get(k), (list, dict)) for k in keys):
            # A container first: a pull request object (`gh pr view --json`) holds its lists.
            k = next(k for k in keys if isinstance(v.get(k), (list, dict)))
            if "pageInfo" in v or "totalCount" in v:
                total = v.get("totalCount")
                if total is not None and _int(total) is None:
                    raise Unreadable(name, "its totalCount isn't a whole number")
                page = v.get("pageInfo")
                pages.append((flag(page, "hasPreviousPage"), flag(page, "hasNextPage"), total, len(v[k]) if isinstance(v[k], list) else 0))
            go(v[k], depth + 1)
        elif isinstance(v, dict) and is_item(v):
            out.append(v)
        else:
            what = "an empty object" if v == {} else "something"
            raise Unreadable(name, f"it holds {what} that isn't {INPUTS[name]}, as GitHub gives them")

    go(value, 0)
    if counted and not pages:
        raise Unreadable(name, "it doesn't say how many there are, so a page left out can't be told: give GraphQL's connection with totalCount and pageInfo")
    if pages:
        total = max((t for *_, t, _ in pages if t is not None), default=None)
        if pages[0][0] or pages[-1][1] or (total is not None and sum(n for *_, n in pages) < total):
            raise Unreadable(name, PARTIAL)
    return out


# ---------- the pull request and the permissions ----------


@dataclass
class PR:
    number: int | None
    head: str
    base: str
    default_branch: str | None
    mergeable: bool | None
    behind: bool  # GitHub's mergeable_state says behind
    draft: bool
    state: str  # open, closed or merged
    requested: set[str]  # logins asked to review again, casefolded
    counts: dict  # what GitHub says the lists hold: files, comments, commits


def _one(v):
    """One object as `--paginate --slurp` gives it too: a list of one page."""
    return v[0] if isinstance(v, list) and len(v) == 1 and isinstance(v[0], dict) else v


def _pr(v) -> PR:
    """The pull request, from GET repos/<repo>/pulls/<n> or `gh pr view --json`."""
    v = _one(v)
    if not isinstance(v, dict):
        raise Unreadable("pr", "it isn't a JSON object, as GET repos/<repo>/pulls/<n> returns one")
    head = v.get("head")
    sha = _sha(head.get("sha") if isinstance(head, dict) else v.get("headRefOid"))
    if sha is None:
        raise Unreadable("pr", "its head commit isn't a full 40-character SHA (head.sha)")
    base = v.get("base")
    ref = base.get("ref") if isinstance(base, dict) else v.get("baseRefName")
    if not isinstance(ref, str) or not ref.strip():
        raise Unreadable("pr", "it names no base branch (base.ref)")
    repo = base.get("repo") if isinstance(base, dict) else None
    default = repo.get("default_branch") if isinstance(repo, dict) and isinstance(repo.get("default_branch"), str) else None
    m = v.get("mergeable")
    state = v.get("mergeable_state", v.get("mergeStateStatus"))
    if state is not None and not isinstance(state, str):
        raise Unreadable("pr", "its mergeable_state isn't text")
    state = (state or "").lower()
    if m is True or m == "MERGEABLE":
        mergeable = True
    elif m is False or m == "CONFLICTING":
        mergeable = False
    elif m is None or m == "UNKNOWN":
        mergeable = None
    else:
        raise Unreadable("pr", "its mergeable is neither true, false nor null")
    if state == "dirty":
        mergeable = False
    draft = v.get("draft", v.get("isDraft", False))
    if not isinstance(draft, bool):
        raise Unreadable("pr", "its draft isn't true or false")
    pr_state = v.get("state", "open")
    if not isinstance(pr_state, str) or pr_state.lower() not in ("open", "closed", "merged"):
        raise Unreadable("pr", "its state isn't open, closed or merged")
    if v.get("merged") not in (None, True, False):
        raise Unreadable("pr", "its merged isn't true or false")
    pr_state = "merged" if v.get("merged") is True or v.get("merged_at") or pr_state.lower() == "merged" else pr_state.lower()
    requested: set[str] = set()
    asked = v.get("requested_reviewers", v.get("reviewRequests", []))
    if isinstance(asked, dict) and isinstance(asked.get("nodes"), list):
        asked = asked["nodes"]
    if not isinstance(asked, list):
        raise Unreadable("pr", "its requested_reviewers isn't a list")
    for r in asked:
        if not isinstance(r, dict):
            raise Unreadable("pr", "a requested reviewer isn't an object with a login")
        who = r.get("requestedReviewer", r)
        login = who.get("login") if isinstance(who, dict) else None
        if isinstance(login, str) and login:
            requested.add(login.casefold())  # a team (no login) asks nobody in particular
    # gh's --json gives the comments themselves, all of them.
    comments = v.get("comments")
    counts = {
        "files": _int(v.get("changed_files", v.get("changedFiles"))),
        "comments": len(comments) if isinstance(comments, list) else _int(comments),
        "commits": _int(v.get("commits")),
    }
    return PR(_int(v.get("number")), sha, ref.strip(), default, mergeable, state == "behind", draft or state == "draft", pr_state, requested, counts)


def _permissions(v) -> dict[str, str]:
    """Login (casefolded) -> permission, from a map, GET .../collaborators/<u>/permission
    responses, or the collaborators list (each login's highest counts)."""
    out: dict[str, str] = {}

    def put(login, perm) -> None:
        if not isinstance(login, str) or not login or perm not in RANK:
            raise Unreadable("permissions", "each entry needs a login and a permission (admin, maintain, write, triage, read or none)")
        have = out.get(login.casefold())
        if have is None or RANK[perm] > RANK[have]:
            out[login.casefold()] = perm

    def one(e: dict) -> None:
        user = e.get("user")
        login = e.get("login") or (user.get("login") if isinstance(user, dict) else None)
        perms = [e[k].lower() for k in ("role_name", "permission") if isinstance(e.get(k), str) and e[k].lower() in RANK]
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


# ---------- the context: every input, read once ----------


class Context:
    """The inputs as the rules read them. Each reader raises Unreadable (the
    same one each time) for an input it can't read."""

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
        """The input's JSON as given."""
        got = self.inputs.get(name)
        if got is None:
            raise Unreadable(name, "it wasn't given")
        value, error = got
        if error is not None:
            raise Unreadable(name, error)
        return value

    def once(self, name: str, fn):
        """`fn()`'s value, worked out once; any failure is the input's Unreadable."""
        if name not in self._cache:
            try:
                self._cache[name] = (fn(), None)
            except Unreadable as e:
                self._cache[name] = (None, e)
            except (CommentsError, protection.ProtectionError) as e:
                self._cache[name] = (None, Unreadable(name, str(e)))
            except (TypeError, ValueError, AttributeError, KeyError, IndexError, RecursionError):
                self._cache[name] = (None, Unreadable(name, f"it isn't in the shape GitHub gives {INPUTS.get(name, name)}"))
        value, error = self._cache[name]
        if error is not None:
            raise error
        return value

    def read_all(self) -> list[Unreadable]:
        """Every input that can't be read, in order, each once."""
        out: list[Unreadable] = []
        for read in (self.read_profile, self.pr, self.files, self.commits, self.checks_ran, self.rulesets,
                     self.open_threads, self.reviews, self.records, self.permissions, self.compare, self.preview_status):
            try:
                read()
            except Unreadable as e:
                if all(e.name != o.name for o in out):
                    out.append(e)
        return out

    def read_profile(self) -> None:
        if self.profile_error is not None:
            raise Unreadable(PROFILE, self.profile_error)

    def pr(self) -> PR:
        return self.once("pr", lambda: _pr(self.raw("pr")))

    def head(self) -> str | None:
        """The head commit, or None when the pull request can't be read (its
        own reason): an input is then still read, to say whether it can be."""
        try:
            return self.pr().head
        except Unreadable:
            return None

    def _complete(self, name: str, have: int, required: bool = True) -> None:
        """Raises when the pull request says the list holds more than `have`,
        or (`required`) doesn't say how many it holds: a page left out would
        then go unseen."""
        try:
            want = self.pr().counts[name]
        except Unreadable:
            return
        if want is None and required:
            raise Unreadable(name, f"--pr doesn't say how many there are, so a page left out can't be told: give --pr from GET repos/<repo>/pulls/<n> ({COUNT_KEYS[name]}), or add {GH_COUNT_KEYS[name]} to `gh pr view --json`")
        if want is not None and have < min(want, MAX_COMMITS if name == "commits" else want):
            raise Unreadable(name, PARTIAL)

    def permissions(self) -> dict[str, str]:
        return self.once("permissions", lambda: _permissions(self.raw("permissions")))

    def commits(self) -> set[str]:
        def read():
            items = _walk(self.raw("commits"), "commits", lambda d: "sha" in d or "oid" in d or isinstance(d.get("commit"), dict), GRAPHQL + ("commits", "nodes"))
            # REST's {sha}, gh's {oid}, GraphQL's {commit: {oid}}
            shas = {_sha(c.get("sha") or c.get("oid") or c["commit"].get("oid")) for c in items}
            if None in shas:
                raise Unreadable("commits", "a commit's SHA isn't a full 40-character SHA")
            self._complete("commits", len(items), required=False)  # a commit left out only leaves out records
            return shas

        return self.once("commits", read)

    def files(self) -> list[str]:
        """Every path the PR changes, a rename's old path too."""

        def read():
            items = _walk(self.raw("files"), "files", lambda d: "filename" in d or "path" in d, GRAPHQL + ("files", "nodes"))
            out: list[str] = []
            for f in items:
                for k in ("filename", "path", "previous_filename"):
                    if k in f and (not isinstance(f[k], str) or not f[k]):
                        raise Unreadable("files", f"a file's {k} isn't a path")
                    if isinstance(f.get(k), str) and f[k] not in out:
                        out.append(f[k])
            try:
                want = self.pr().counts["files"]
            except Unreadable:
                want = None
            if want is not None and want > MAX_FILES:
                raise Unreadable("files", f"GitHub lists at most {MAX_FILES} of a pull request's files, and this one changes {want}")
            self._complete("files", len(items))
            return out

        return self.once("files", read)

    def checks_ran(self) -> list:
        """The latest result of each check on the head commit (`protection.latest`)."""

        def read():
            head = self.head()
            runs, statuses, flat = [], [], []
            unknown = "names no commit, so it can't be told to be the head's: keep each check run's head_sha, the combined status's sha, a status's url"
            for v in _walk(self.raw("checks"), "checks", lambda d: any(k in d for k in ("check_runs", "statuses", "context"))):
                if "check_runs" in v:
                    if isinstance(v["check_runs"], list) and any(isinstance(r, dict) and not isinstance(r.get("head_sha"), str) for r in v["check_runs"]):
                        raise Unreadable("checks", "a check run " + unknown)
                    runs.append(v)
                elif "statuses" in v:
                    if not isinstance(v.get("sha"), str):
                        raise Unreadable("checks", "a combined status " + unknown)
                    statuses.append(v)
                else:
                    m = _STATUS_URL_SHA.search(str(v.get("url") or ""))  # a plain status names its commit only in its URL
                    if m is None:
                        raise Unreadable("checks", "a status " + unknown)
                    if head is None or m.group(1).lower() == head:
                        flat.append(v)
            if flat:
                statuses.append({"statuses": flat})
            return protection.latest(runs, statuses, head)

        return self.once("checks", read)

    def rulesets(self) -> protection.Report:
        """The rulesets on the base branch, read as `workflow protection` reads them."""

        def read():
            rulesets = self.raw("rulesets")
            try:
                pr = self.pr()
            except Unreadable:  # still read, to say whether they can be
                protection.check(rulesets, self.profile.base_branch if self.profile else "main")
                raise
            settings = {"default_branch": pr.default_branch} if pr.default_branch else None
            # Without the repository's default branch, the profile's base counts as it.
            assume = bool(self.profile) and pr.base == self.profile.base_branch
            return protection.check(rulesets, pr.base, settings, base_if_unknown=assume)

        return self.once("rulesets", read)

    def open_threads(self) -> list[str | None]:
        """Who opened each unresolved review thread (None when it can't be told)."""

        def read():
            items = _walk(
                self.raw("threads"),
                "threads",
                lambda d: any(k in d for k in ("isResolved", "is_resolved", "resolved")),
                GRAPHQL + ("reviewThreads", "review_threads", "threads", "nodes"),
                counted=True,  # threads come only from GraphQL, 100 to a page
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
                    out.append(_login(first) or None)
            return out

        return self.once("threads", read)

    def reviews(self) -> list[tuple[str, str]]:
        """(login, state) for each review, oldest first."""

        def read():
            items = _walk(self.raw("reviews"), "reviews", lambda d: "state" in d and any(k in d for k in ("user", "author", "submitted_at", "submittedAt")), GRAPHQL + ("reviews", "nodes"))
            for r in items:
                if not isinstance(r.get("state"), str):
                    raise Unreadable("reviews", "a review's state isn't text")
            items = [r for r in items if r["state"].upper() != "PENDING"]  # a draft review nobody else sees
            items = _in_time_order(items, lambda r: _time(r.get("submitted_at") or r.get("submittedAt")), lambda r: r.get("id"))
            return [(_login(r), r["state"].upper()) for r in items]

        return self.once("reviews", read)

    def records(self) -> list[reviews.Record]:
        """The review records in the comments (`reviews.read`), oldest first."""

        def read():
            comments = comments_from(self.raw("comments"))
            self._complete("comments", len(comments))
            return _in_time_order(reviews.read(comments), lambda r: _time(r.created_at), lambda r: r.comment_id)

        return self.once("comments", read)

    def compare(self) -> int:
        """How many commits the head is behind the base."""

        def read():
            v = _one(self.raw("compare"))
            head = self.head()
            if not isinstance(v, dict) or _int(v.get("behind_by")) is None:
                raise Unreadable("compare", "it has no behind_by, as GET repos/<repo>/compare/<base>...<head> gives it")
            commits = v.get("commits")
            # The list stops at 250 commits: its last is the head only when it holds them all.
            whole = isinstance(commits, list) and commits and len(commits) == _int(v.get("ahead_by")) and isinstance(commits[-1], dict)
            last = _sha(commits[-1].get("sha")) if whole else None
            url = str(v.get("url") or v.get("html_url") or "")
            # A fork's head is `owner:<sha>`. The url names the head exactly; the
            # list's last commit is by date, so it is used only when the url names none.
            named = re.search(r"\.\.\.(?:[^/.:]+:)?([0-9a-fA-F]{40})\b", url)
            told = [named.group(1).lower()] if named else [last] if last else []
            base_side = re.search(r"/compare/(.+?)\.\.\.", url)
            if base_side and self.head() is not None and unquote(base_side.group(1)) not in (self.pr().base, f"refs/heads/{self.pr().base}"):
                raise Unreadable("compare", "it compares the head with something other than the base branch: compare <base branch>...<head SHA>")
            if head is not None and (not told or any(s != head for s in told)):
                raise Unreadable("compare", "it doesn't compare the pull request's head: compare <base>...<head SHA>")
            return v["behind_by"]

        return self.once("compare", read)

    def preview_status(self) -> tuple[str, str | None, str | None]:
        """(state, url, commit); `none` when no preview was given."""

        def read():
            if self.inputs.get("preview") is None:
                return "none", None, None
            v = self.raw("preview")
            if not isinstance(v, dict) or v.get("state") not in ("built", "building", "failed", "none"):
                raise Unreadable("preview", "its state isn't built, building, failed or none")
            url, commit = v.get("url"), v.get("commit")
            if url is not None and not (isinstance(url, str) and url.startswith(("https://", "http://")) and url.isprintable() and " " not in url):
                raise Unreadable("preview", "its url isn't a web address (https://…)")
            if commit is not None and not (isinstance(commit, str) and re.fullmatch(r"[0-9a-fA-F]{7,40}", commit)):
                raise Unreadable("preview", "its commit isn't a SHA (at least 7 hex characters)")
            if v["state"] == "built" and not url:
                raise Unreadable("preview", "it is built but gives no url")
            return v["state"], url, commit

        return self.once("preview", read)


def _may_review(login: str | None, perms: dict[str, str]) -> bool:
    """The account has write, maintain or admin permission."""
    return bool(login) and perms.get(login.casefold()) in WRITE


def _note(ctx: Context, nid: str, message: str) -> None:
    ctx.notes.append({"id": nid, "message": message})


# ---------- the rules ----------


def _checks(ctx: Context, add) -> None:
    """flow §4.1: every required check ran on the head commit and passed; none pending."""
    ctx.read_profile()
    prof = ctx.profile
    ran = ctx.checks_ran()
    rep = ctx.rulesets()
    if rep.unsure:
        add("required_unknown", why="; ".join(rep.unsure))
    from_rules = list(rep.required_checks)
    from_profile = list(prof.required_checks) if prof else []
    required = from_rules + [c for c in from_profile if c not in from_rules]
    # In solo mode (`project.ruleset = false`) nothing on GitHub requires checks, by design.
    if set(from_rules) != set(from_profile) and not (prof and prof.ruleset is False):
        only_rules = [c for c in from_rules if c not in from_profile]
        only_profile = [c for c in from_profile if c not in from_rules]
        parts = []
        if only_rules:
            parts.append(f"only the rulesets require {_names(only_rules)}")
        if only_profile:
            parts.append(f"only the profile's `ci.required_checks` lists {_names(only_profile)}")
        _note(ctx, "lists_differ", "The required checks differ: " + "; ".join(parts) + ". Both count; check the set-up.")
    by_name = {r.name: r for r in ran}
    if not required and not rep.unsure:
        required = [r.name for r in ran if not r.preview]
        if not required and not (prof and prof.ci_none):
            add("no_checks")
    for n in required:
        ctx.checks.append({"name": n, "state": by_name[n].result if n in by_name else "missing", "required": True})
    others = sorted((r for r in ran if r.name not in required), key=lambda r: (r.name.casefold(), r.name))
    for r in others:
        ctx.checks.append({"name": r.name, "state": r.result, "required": False})
    running = [n for n in required if n in by_name and by_name[n].result == "pending"]
    missing = [n for n in required if n not in by_name]
    if running or missing:
        parts = ([_names(running)] if running else []) + ([f"not started yet: {_names(missing)}"] if missing else [])
        add("checks_pending", names="; ".join(parts))
    failed = [n for n in required if n in by_name and by_name[n].result == "failing"]
    if failed:
        add("checks_failed", names=_names(failed))
    loose = [r.name for r in others if r.result == "failing" and not r.preview]
    if loose:
        _note(ctx, "failed_not_required", f"Failed, but not required, so it doesn't block: {_names(loose)}.")


def _evidence(ctx: Context, add) -> None:
    """flow §4.2: the suite's evidence where the profile says `ci.none`. Reading
    the report is #81's; until then `ci.none` is never ready."""
    ctx.read_profile()
    if ctx.profile and ctx.profile.ci_none:
        add("evidence_missing")


def _up_to_date(ctx: Context, add) -> None:
    """flow §4.3: the head isn't behind the base."""
    behind = ctx.compare()
    if behind or ctx.pr().behind:
        add("behind", by=f" by {_plural(behind, 'commit')}" if behind else "")


def _panel(ctx: Context, add) -> None:
    """flow §4.4: a clean round on the head, or on an earlier commit of the PR
    with a later clean Correctness pass on the head. Records from accounts
    without write access, or naming a commit outside the PR, are ignored."""
    head = ctx.pr().head
    perms = ctx.permissions()
    shas = ctx.commits() | {head}
    records = ctx.records()
    counted = [r for r in records if _may_review(r.author, perms) and r.commit in shas]
    if len(records) > len(counted):
        left_out = _plural(len(records) - len(counted), "review record")
        _note(ctx, "records_ignored", f"Left out {left_out}: posted by an account without write access, or naming a commit outside this pull request.")
    rounds = [i for i, r in enumerate(counted) if r.kind == "round"]
    if not rounds:
        add("no_review")
        return
    last = counted[rounds[-1]]
    details = {"round": last.round, "round_short": _short(last.commit)}
    if not last.clean:
        add("review_not_clean", **details)
        return
    passes = [r for r in counted[rounds[-1] + 1:] if r.kind == "pass" and r.commit == head]
    if passes and not passes[-1].clean:
        add("pass_not_clean", **details)
    elif last.commit != head and not passes:
        add("review_stale", **details)


def _mergeable(ctx: Context, add) -> None:
    """#30: GitHub can merge it: open, not a draft, and no conflict."""
    pr = ctx.pr()
    if pr.state != "open":
        add("closed", state=pr.state)
    if pr.draft:
        add("draft")
    if pr.mergeable is False:
        add("conflict")
    elif pr.mergeable is None:
        add("mergeable_unknown")


def _people(ctx: Context, add) -> None:
    """#30: no unresolved review thread, and no "changes requested" (from an
    account with write access) not followed by that reviewer's approval or a
    new review request. Conversation comments never block."""
    open_threads = ctx.open_threads()
    if open_threads:
        add("unresolved_threads", who=_who(dict.fromkeys(open_threads)), threads=_plural(len(open_threads), "unresolved review thread"))
    pr = ctx.pr()
    revs = ctx.reviews()
    perms = ctx.permissions()
    standing: dict[str, tuple[str, str]] = {}
    for login, state in revs:
        if state in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED") and _may_review(login, perms):
            standing[login.casefold()] = (login, state)
    asked = [login for key, (login, state) in standing.items() if state == "CHANGES_REQUESTED" and key not in pr.requested]
    if asked:
        add("changes_requested", who=_who(asked))


def _preview(ctx: Context, add) -> None:
    """#30: where the project has previews, the head commit's built."""
    head = ctx.pr().head
    state, url, commit = ctx.preview_status()
    if state == "none":
        how = " `docs/previews.md` says how to add them." if PREVIEWS_DOC.exists() else ""
        _note(ctx, "no_previews", f"There's no try-it link for this project: check the change another way, as the PR's \"How to try it\" says.{how}")
        return
    for_head = commit is not None and len(commit) >= 7 and head.startswith(commit.lower())
    if state == "failed" and (for_head or commit is None):
        add("preview_failed")
    elif state == "built" and for_head:
        ctx.preview = {"state": "built", "url": url}
    elif state == "building" and (for_head or commit is None):
        add("preview_building", what=f"the preview for {_short(head)} is still building")
    else:
        add("preview_building", what=f"the preview is for {_short(commit)}, not the head {_short(head)}" if commit else "the preview names no commit")


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
    Rule("mergeable", "#30", _mergeable),
    Rule("people", "#30", _people),
    Rule("preview", "#30", _preview),
    Rule("kit_files", "#30", _kit_files),
)


# ---------- the decision ----------


def _reason(rid: str, rule: Rule | None, level: str, details: dict, wording_id: str | None = None) -> dict:
    reason = REASONS[wording_id or rid]
    details = {k: _clean(v) if isinstance(v, str) else v for k, v in details.items()}
    wording = {lvl: {"message": m.format(**details), "fix": f.format(**details)} for lvl, (m, f) in reason.wording.items()}
    out = {
        "id": rid,
        "rule": rule.id if rule else None,
        "implements": rule.implements if rule else None,
        **wording[level],
        "action": reason.action,
        "wording": wording,
    }
    if rid == "couldnt_read":
        out["input"] = details["input"]
    return out


def evaluate(inputs: dict, profile=None, profile_error: str | None = None, asker: str | None = None, level: str = "new") -> Result:
    """The decision. `inputs` maps each name in INPUTS to (value, None) when
    read, (None, why) when it couldn't be; a name left out wasn't given (the
    preview: none). `profile_error` says why the profile couldn't be read."""
    ctx = Context(inputs, profile, profile_error)
    try:
        pr = ctx.pr()
        number, head, base = pr.number, pr.head, pr.base
    except Unreadable:
        number, head, base = None, None, profile.base_branch if profile else "main"
    common = {"short": _short(head), "base": base, "number": number if number is not None else "<n>"}

    def unreadable(e: Unreadable) -> dict:
        what = "the profile" if e.name == PROFILE else INPUTS[e.name]
        details = {**common, "input": e.name, "what": what, "why": e.why.rstrip(".")}
        return _reason("couldnt_read", None, level, details, "couldnt_read_profile" if e.name == PROFILE else None)

    failed = ctx.read_all()
    reasons = [unreadable(e) for e in failed]
    for rule in RULES:
        found: list[tuple[str, dict]] = []
        try:
            rule.judge(ctx, lambda rid, **details: found.append((rid, details)))
        except Unreadable as e:  # already a reason of its own; what the rule found before it stays
            if all(e.name != f.name for f in failed):
                failed.append(e)
                reasons.append(unreadable(e))
        reasons += [_reason(rid, rule, level, {**common, **details}) for rid, details in found]

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
            _note(ctx, "kit_files", "This change touches the kit's or CI files (" + _names(kit) + "): once everything else holds, it needs the owner's review.")
    elif kit:
        decision = "owner_review"
    else:
        decision = "ready"
    return Result(decision, number, head, level, owner, reasons, ctx.notes, ctx.checks, kit, ctx.preview)


# ---------- text ----------


def text(res: Result) -> str:
    """The answer for people: the decision first, then each reason and its fix."""
    n = f"#{res.pr}" if res.pr is not None else "This pull request"
    if res.decision == "ready":
        lines = [f"Ready: {n} may merge."]
    elif res.decision == "owner_review":
        if res.owner:
            lines = ["Ready once you've read the changes to these files:"]
        else:
            lines = [f"Needs the owner's review: {n} changes the kit's or CI files, which only the owner merges:"]
        lines += [f"- `{_clean(f)}`" for f in res.files]
    else:
        lines = [f"Not yet: {n} isn't ready to merge."]
        for r in res.reasons:
            message = r["message"].removeprefix("Not yet: ")
            lines.append(f"- {message[:1].upper()}{message[1:]} {r['fix']}")
    if res.preview and res.decision != "not_yet":
        lines.append(f"Try it first: {_clean(res.preview['url'])}")
    if res.notes:
        lines.append("Notes:")
        lines += [f"  {x['message']}" for x in res.notes]
    if res.checks:
        lines.append(f"Checks on {_short(res.head)}:")
        lines += [f"  {_clean(c['name'])}: {c['state']}" + (" (required)" if c["required"] else "") for c in res.checks]
    # Text from the input can't start a line of its own or fail to print.
    return protection.printable("\n".join(lines))
