"""Whether a pull request may merge: the merge rule's one implementation.

`workflow merge-check` reads JSON a session hands it (the pull request, its
files, commits, checks, the rulesets, review threads, reviews, comments with
their authors' permissions, the base comparison and the preview) and answers
`ready`, `not_yet` or `owner_review`, with every reason that applies. It reads
only what it is given (`workflow merge-check --fetch` fetches it first, through
`fetch.merge_inputs`): it asks GitHub nothing, posts nothing and writes nothing.

The run's charter waives named checks (flow §4.1): one counts as passed only
when it failed or was cancelled with one of the profile's `ci.killed_markers`
in its log, and only from an approved charter in a ticket or conductor
session, never an attended one. A waiver used, or `ci.none`, makes the suite's
evidence required (flow §4.2): `workflow evidence`'s report for the head,
read through its own `evidence.read_headline`.

Every rule is in `RULES`, each naming the flow §4 item (or #30's condition) it
implements; `tests/test_merge_check.py` fails when flow §4 and `RULES` differ.
Every reason is in `REASONS`, worded for *new to building* and for *developer*;
the decision never depends on the wording. It reuses the kit's readers rather
than repeating them:
- the review records: `reviews.read`;
- the checks on the head commit: `protection.latest` (a name reported twice
  counts by its latest result, the try-it link's check marked);
- the checks the rulesets require: `protection.check`;
- kit and CI files: the guard's own matcher, `guard.matches`;
- the hashes of the pull request's own changes at its head: `own_changes.of_files`,
  on GitHub's per-file data, as `workflow review-record` hashes them from git.

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

from . import charter as charter_mod
from . import own_changes, protection, reviews, small, state
from .evidence import is_full, read_headline
from .guard import matches
from .posts import CommentsError, _login, _number, comments_from, decode_values
from .profile import DEFAULT_PROTECTED, Suite

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
# How a refused charter's note starts (`waivers`, and the merge queue's refusal).
CHARTER_REFUSED = "The charter wasn't used, so no check is waived: "
PREVIEWS_DOC = Path(__file__).resolve().parents[2] / "docs/previews.md"
DEFAULT_REVIEW_ROUNDS = 3  # the profile's run.review_rounds when it can't be read
REVIEW_ROUNDS = range(1, 11)  # what --review-rounds accepts, as profile.py's run.review_rounds
DEFAULT_REVIEW_PASSES = 2  # the profile's run.review_passes when it can't be read
REVIEW_PASSES = range(0, 11)  # what --review-passes accepts, as profile.py's run.review_passes


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
    # A case of the same reason worded its own way: case -> level -> (message, fix).
    # Unlike couldnt_read_profile's own entry, a case keeps its reason's id and action.
    cases: dict = field(default_factory=dict)


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
    review_rounds: int = DEFAULT_REVIEW_ROUNDS  # the allowed review rounds the review rule used
    review_passes: int = DEFAULT_REVIEW_PASSES  # the pass cap the review rule used
    small_max_lines: int = small.DEFAULT_MAX_LINES  # the small threshold the review rule used (#257)
    small_max_files: int = small.DEFAULT_MAX_FILES
    measured: dict | None = None  # the diff against it, where the small review's condition applies
    queue: bool = False  # a ruleset in force on the base requires a merge queue: "ready" means ready to queue (#245)
    head_hashes: own_changes.Hashes = own_changes.UNKNOWN_HASHES  # the head's own changes, hashed (#261)

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
            "review_rounds": self.review_rounds,
            "review_passes": self.review_passes,
            "small_max_lines": self.small_max_lines,
            "small_max_files": self.small_max_files,
            "small": self.measured,
            "queue": self.queue,
            "head_hashes": {"diff": self.head_hashes.diff, "lines": self.head_hashes.lines},
        }


# ---------- the reasons, worded for both levels ----------

REASONS = {
    "couldnt_read": Reason("", None, {
        "new": ("Not yet: couldn't read {what}.", "Ask Claude to fetch the pull request's details again, then ask again."),
        "developer": ("Not yet: couldn't read {what} (--{input}): {why}.", "Give --{input} as GitHub returns it, every page, then run merge-check again."),
    }, {
        # #117: the preview isn't GitHub's data but #41's reader's answer, and an
        # empty file is how a reader that failed leaves it.
        "preview": {
            "new": ("Not yet: couldn't read the try-it link.", "Ask Claude to read the try-it link again, then ask again. If it still can't, the kit may need updating to read Cloudflare's comment."),
            "developer": ("Not yet: couldn't read the try-it link ({why}).", "Run `workflow preview --fetch {number} --json` (without gh: `workflow preview --comments F --checks F --sha <head> --json`), read what it printed, and give its answer as --preview. If the reader itself can't read Cloudflare's comment or check, the kit needs updating: report it."),
        },
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
        "developer": ("Not yet: no passing `workflow evidence` report for {short} from an account with write access ({why}).", "Run `workflow evidence --base-ref origin/{base}` and post the report."),
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
        "new": ("Not yet: the last review found things to fix.", "Fix them, then run another review round."),
        "developer": ("Not yet: review round {round} of {allowed} on {round_short} wasn't clean.", "Fix the findings and run another round."),
    }, cases={
        # The last allowed round (#170): a clean Correctness pass on the head lifts it.
        "last_round": {
            "new": ("Not yet: the last review found things to fix.", "Fix them, then ask for a short check of the latest changes."),
            "developer": ("Not yet: review round {round} on {round_short} wasn't clean, and no round is left ({allowed} allowed).", "Fix the findings and run a Correctness pass on the head; no further round."),
        },
        # The small review (#257): its round (`small`), and the full-panel round after it
        # (`after_small`), count as the last allowed one, whatever the round limit.
        "small": {
            "new": ("Not yet: the last review found things to fix.", "Fix them, then ask for a short check of the latest changes."),
            "developer": ("Not yet: review round {round} on {round_short} wasn't clean, and no counted round ran Spec (the small review), so it counts as the last round.", "Fix the findings and run a Correctness pass on the head; no further round."),
        },
        "after_small": {
            "new": ("Not yet: the last review found things to fix.", "Fix them, then ask for a short check of the latest changes."),
            "developer": ("Not yet: review round {round} on {round_short} wasn't clean, and as the full-panel round after a small review it counts as the last round.", "Fix the findings and run a Correctness pass on the head; no further round."),
        },
    }),
    "pass_not_clean": Reason("review_panel", "review", {
        "new": ("Not yet: the last check of the newest changes found things to fix.", "Fix them, then ask Claude to check again."),
        "developer": ("Not yet: the Correctness pass on {short} after round {round} wasn't clean.", "Fix the findings and run another pass."),
    }),
    "review_stale": Reason("review_panel", "review", {
        "new": ("Not yet: the newest changes haven't been reviewed.", "Review it now: a short check of the latest changes."),
        "developer": ("Not yet: the last clean round covers {round_short}, not the head {short}, and no later clean Correctness pass covers the head.", "Run a Correctness pass on the head (review-panel §5)."),
    }),
    # The pass cap (#256): in place of the three above when a pass would come next.
    "passes_used_up": Reason("review_panel", "review", {
        "new": ("Not yet: the short checks of the latest changes have reached their limit, so the owner decides what happens next.", "The owner can ask Claude for one more check; until then, this change stays unmerged."),
        "developer": ("Not yet: the pass cap is reached ({cap} allowed after round {round}, {passes}), and the head {short} still needs one: this pull request waits on the owner.", "The owner decides: \"One more pass\" (merge-check skill) runs one past the cap; in a run the ticket stops at needs-human with the open findings in the PR body."),
    }),
    # The small review's condition (#257): in place of every other review reason.
    "past_small_threshold": Reason("review_panel", "review", {
        "new": ("Not yet: this change has grown past what a short review covers ({size}, where a short review covers at most {most}).", "Review it now: Claude runs the full review panel."),
        "developer": ("Not yet: no counted round ran Spec, and the diff is past the small threshold: {size} outside tests, where the threshold is at most {most}.", "Run the full panel (the light review's shape for a 1-round run's pull request), allowed past the round limit; never a Correctness-only round."),
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
        "new": ("Not yet: the try-it link didn't build.", "Ask Claude to find out why: \"When a build fails\" in {page} gives the fix for each message in the build's log."),
        "developer": ("Not yet: the preview build failed for {short}.", "Fix the preview build (\"When a build fails\" in {page} matches its log to a fix) and push."),
    }),
    "preview_building": Reason("preview", None, {
        "new": ("Not yet: the try-it link is still building.", "Ask again in a few minutes: a try-it link can take about four minutes to start building."),
        "developer": ("Not yet: {what}.", "Wait for the preview of the head (Cloudflare's builds can take about four minutes to start), then run merge-check again."),
    }),
}


# ---------- small helpers ----------


def _plural(n: int, one: str, many: str | None = None) -> str:
    """`n` and the noun, singular or plural: "1 thread", "2 threads"."""
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _sha(v) -> str | None:
    """A full SHA, lowercased; None when `v` isn't one."""
    return v.lower() if isinstance(v, str) and _SHA.fullmatch(v.lower()) else None


def _parents(v) -> tuple[str, ...] | None:
    """A commit's parents' SHAs, from REST's `[{sha}]` or GraphQL's
    `{nodes: [{oid}]}`; None when not given, or not in either shape."""
    if isinstance(v, dict):
        v = v.get("nodes")
    if not isinstance(v, list):
        return None
    shas = tuple(_sha(p.get("sha") or p.get("oid")) if isinstance(p, dict) else None for p in v)
    return None if None in shas else shas


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

    def __init__(self, inputs: dict, profile, profile_error: str | None, waivable: frozenset = frozenset(), logs: dict | None = None, review_rounds: int | None = None, review_passes: int | None = None,
                 small_max_lines: int | None = None, small_max_files: int | None = None):
        self.inputs = inputs
        self.profile = profile
        self.profile_error = profile_error
        self.waivable = waivable  # the checks the charter waives, when it may (`waivers`)
        self.logs = logs or {}  # --check-logs: file name -> the log's tail
        # The allowed review rounds: --review-rounds, else the profile's run.review_rounds.
        self.review_rounds = review_rounds or (profile.review_rounds if profile else DEFAULT_REVIEW_ROUNDS)
        # The pass cap: --review-passes, else the profile's run.review_passes (0 is a cap).
        self.review_passes = review_passes if review_passes is not None else (profile.review_passes if profile else DEFAULT_REVIEW_PASSES)
        # The small threshold (#257): the flags, else the profile's run.small_max_lines and run.small_max_files.
        self.small_max_lines = small_max_lines or (profile.small_max_lines if profile else small.DEFAULT_MAX_LINES)
        self.small_max_files = small_max_files or (profile.small_max_files if profile else small.DEFAULT_MAX_FILES)
        self.measured: small.Measure | None = None  # the diff against it, once measured
        self.waived: list[str] = []  # the waivers used
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
        return set(self.parents())

    def parents(self) -> dict[str, tuple[str, ...] | None]:
        """Each commit of the PR, with its parents' SHAs where given (REST's
        `parents: [{sha}]`, GraphQL's `parents: {nodes: [{oid}]}`), else None.
        With a page of commits left out, none are kept: a parent from that
        page would read as outside the pull request."""

        def read():
            items = _walk(self.raw("commits"), "commits", lambda d: "sha" in d or "oid" in d or isinstance(d.get("commit"), dict), GRAPHQL + ("commits", "nodes"))
            # REST's {sha}, gh's {oid}, GraphQL's {commit: {oid}}
            nodes = [c if "sha" in c or "oid" in c else c["commit"] for c in items]
            out = {_sha(c.get("sha") or c.get("oid")): _parents(c.get("parents")) for c in nodes}
            if None in out:
                raise Unreadable("commits", "a commit's SHA isn't a full 40-character SHA")
            self._complete("commits", len(items), required=False)  # a commit left out only leaves out records
            try:
                want = self.pr().counts["commits"]
            except Unreadable:
                want = None
            whole = want is not None and want <= len(items)
            return out if whole else dict.fromkeys(out)

        return self.once("commits", read)

    def base_merge(self, sha: str | None) -> bool:
        """The commit is a merge of the base: a commit of the PR with two or more
        parents, at least one of them outside the PR's commits. Without its
        parents, it isn't."""
        got = self.parents().get(sha)
        return got is not None and len(got) >= 2 and any(p not in self.parents() for p in got)

    def changes(self) -> list[small.Change]:
        """Each file the PR changes: its path, a rename's old path, its status,
        and its additions and deletions as given (#257): `size` checks them,
        only where the small review's condition needs them. Also its blob SHA
        and patch where given (#261), which `head_hashes` reads."""

        def read():
            items = _walk(self.raw("files"), "files", lambda d: "filename" in d or "path" in d, GRAPHQL + ("files", "nodes"))
            out: list[small.Change] = []
            for f in items:
                for k in ("filename", "path", "previous_filename"):
                    if k in f and (not isinstance(f[k], str) or not f[k]):
                        raise Unreadable("files", f"a file's {k} isn't a path")
                if f.get("patch") is not None and not isinstance(f["patch"], str):
                    raise Unreadable("files", "a file's patch isn't text")
                status, sha = f.get("status", f.get("changeType")), f.get("sha")
                out.append(small.Change(
                    f.get("filename") or f["path"], f.get("previous_filename"),
                    status.lower() if isinstance(status, str) else None, f.get("additions"), f.get("deletions"),
                    sha if isinstance(sha, str) else None, f.get("patch"),
                ))
            try:
                want = self.pr().counts["files"]
            except Unreadable:
                want = None
            if want is not None and want > MAX_FILES:
                raise Unreadable("files", f"GitHub lists at most {MAX_FILES} of a pull request's files, and this one changes {want}")
            self._complete("files", len(items))
            return out

        return self.once("files", read)

    def files(self) -> list[str]:
        """Every path the PR changes, a rename's old path too."""
        out: list[str] = []
        for c in self.changes():
            for p in (c.path, c.previous):
                if p and p not in out:
                    out.append(p)
        return out

    def head_hashes(self) -> own_changes.Hashes:
        """The hashes of the PR's own changes at its head, from GitHub's
        per-file data (`own_changes.of_files`): `unknown` when the files can't
        be read, or a file can't be hashed (changes with no patch, or no patch
        and no counts to say it has no changes)."""

        def read():
            try:
                changes = self.changes()
                if any(not c.patch and c.status != "removed" and None in (c.additions, c.deletions) for c in changes):
                    return own_changes.UNKNOWN_HASHES
                return own_changes.of_files(changes)
            except (Unreadable, ValueError):  # CantHash, or text the hash can't encode (a lone surrogate)
                return own_changes.UNKNOWN_HASHES

        return self.once("head_hashes", read)

    def size(self) -> small.Measure:
        """The diff against the small threshold (`small.measure`), counting
        files outside the profile's suites' globs. Unreadable when a counted
        file has no additions and deletions, or a file on a test path has no
        status (it may be a rename from outside tests)."""
        globs = small.suite_globs(self.profile)
        for c in self.changes():
            if c.status is None and c.previous is None and small.is_test(c.path, globs):
                # gh's and GraphQL's lists may name no status: a rename into tests would go uncounted.
                raise Unreadable("files", f"`{c.path}` is on a test path but has no status, so a rename into it from outside tests can't be told: give --files as GitHub's REST list of the pull request's files (GET repos/<repo>/pulls/<n>/files), with each file's status and previous_filename")
        try:
            return small.measure(self.changes(), globs, self.small_max_lines, self.small_max_files)
        except small.NoCounts as e:
            raise Unreadable("files", f"{e}, which the small threshold counts: give --files as GitHub's REST list of the pull request's files (GET repos/<repo>/pulls/<n>/files), with each file's additions and deletions") from None

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

    def queue(self) -> bool:
        """A ruleset in force on the base requires a merge queue (`protection.check`'s
        reader); not when the rulesets can't be read, which is a reason of its own."""
        try:
            return self.rulesets().queue
        except Unreadable:
            return False

    def queue_unsure(self) -> list[str]:
        """The rulesets with a merge-queue rule it can't count either way."""
        try:
            return self.rulesets().queue_unsure
        except Unreadable:
            return []

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

    def comments(self) -> list[dict]:
        """The pull request's comments, oldest first."""

        def read():
            comments = comments_from(self.raw("comments"))
            self._complete("comments", len(comments))
            return _in_time_order(comments, lambda c: _time(c.get("created_at") or c.get("createdAt")), _number)

        return self.once("comments", read)

    def records(self) -> list[reviews.Record]:
        """The round and pass records in the comments (`reviews.read`), oldest
        first. A spec record (#233) names a spec's body, not a commit, so it is
        no review of the pull request's code."""
        return [r for r in reviews.read(self.comments()) if r.kind != "spec"]

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
            named = re.search(r"\.\.\.(?:[^/.:]+:)?([0-9a-fA-F]{40})(?=$|[?#])", url)
            told = [named.group(1).lower()] if named else [last] if last else []
            head_side = re.search(r"\.\.\.([^?#]*)", url)
            if head_side and any(c in unquote(head_side.group(1)) for c in "~^@{"):
                told = ["a revision, not a commit"]  # `<head>~1` and the like name another commit
            base_side = re.search(r"/compare/(.+?)\.\.\.", url)
            if base_side and self.head() is not None and unquote(base_side.group(1)) not in (self.pr().base, f"refs/heads/{self.pr().base}"):
                raise Unreadable("compare", "it compares the head with something other than the base branch: compare <base branch>...<head SHA>")
            if head is not None and (not told or any(s != head for s in told)):
                raise Unreadable("compare", "it doesn't compare the pull request's head: compare <base>...<head SHA>")
            return v["behind_by"]

        return self.once("compare", read)

    def preview_given(self) -> bool:
        """--preview was given (or read by --fetch), readable or not."""
        return self.inputs.get("preview") is not None

    def preview_status(self) -> tuple[str, str | None, str | None]:
        """(state, url, commit); `none` when no preview was given."""

        def read():
            if not self.preview_given():
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
    for n in [n for n in failed if n in ctx.waivable]:
        why = _not_killed(by_name[n].id, ctx.logs, prof)
        if why is None:
            failed.remove(n)
            ctx.waived.append(n)
            next(c for c in ctx.checks if c["name"] == n and c["required"])["state"] = "waived"
        else:
            _note(ctx, "waiver_not_taken", f"{_names([n])} is waived, but {why}: a real failure always blocks.")
    if ctx.waived:
        _note(ctx, "waived", f"Waived, killed rather than failed: {_names(ctx.waived)}. The suite's evidence is required (flow §4.2).")
    if failed:
        add("checks_failed", names=_names(failed))
    loose = [r.name for r in others if r.result == "failing" and not r.preview]
    if loose:
        _note(ctx, "failed_not_required", f"Failed, but not required, so it doesn't block: {_names(loose)}.")


_EXIT_CODE = re.compile(r"\bexit code (\d+)")
# A test that failed, as runners report it while they run, before any count:
# pytest's `path::test FAILED`, `FAILED path::test` (xdist's `[gw0] [ 50%] FAILED
# path::test` too) and its progress line's `F` or `E`, with the file's path or,
# under -q or continued, without (`tests/test_a.py ..F.  [ 40%]`, `..F..  [ 40%]`);
# go's `--- FAIL:` and `FAIL<tab>pkg`; jest's `✕` and `FAIL path` (coloured, ` FAIL  path`). Matched on each line as
# `_log_lines` leaves it.
_TEST_FAILED = re.compile(
    r"::.*? (?:FAILED|ERROR)(?:\s|$)|(?:^|\s)(?:FAILED|ERROR) \S+::|\.py [.sxXFE]*[FE][.sxXFE]*(?:\s|$)"
    r"|^[.sxXFE]*[FE][.sxXFE]*(?:\s+\[\s*\d+(?:%|/\s*\d+)\])?$|^--- FAIL:|^✕ |^FAIL\s+\S"
)
# What starts a line of a check's log before the runner's own text: `gh run
# view --log-failed`'s job and step (tab-separated), Actions' timestamp, colours.
_GH_COLUMNS = re.compile(r"^[^\t\n]*\t[^\t\n]*\t")
_TIMESTAMP = re.compile(r"^\ufeff?(?:\d{4}-\d\d-\d\dT[\d:.]+Z ?)?")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")


def _log_lines(line: str) -> list[str]:
    """A line of a check's log as its runner may have printed it: with gh's job
    and step columns left out, and as it is (a job log the API gives has no
    columns, and a runner's own line may hold tabs, as go's `FAIL<tab>pkg` does)."""
    line = _ANSI.sub("", line)
    return [_TIMESTAMP.sub("", x, count=1).strip() for x in (_GH_COLUMNS.sub("", line, count=1), line)]


def log_names(run_id: int) -> list[str]:
    """The file names a check's log may have in --check-logs: its latest run's
    id on the head (the check run's id, which is its Actions job's id, as
    `gh run view --log-failed --job <id>` takes it), bare or with `.log` or
    `.txt`. By the id, not the name, so a log kept from an earlier run, or
    another commit's, is never read for this one."""
    return [f"{run_id}{ext}" for ext in ("", ".log", ".txt")] if run_id else []


def _not_killed(run_id: int, logs: dict, prof) -> str | None:
    """Why the check's log doesn't show it was killed rather than failed; None
    when it does. Only the first of `log_names` given is read. It must hold one
    of the profile's `ci.killed_markers`, and no sign of a real failure: a
    count the profile's suites read as failed or errored, or an exit code no
    marker names, or a test reported failed as the runner went."""
    markers = [m for m in (prof.killed_markers if prof else []) if m]
    if not markers:
        return "the profile lists no `ci.killed_markers`"
    text = next((logs[k] for k in log_names(run_id) if k in logs), None)
    if text is None:
        return f"no log was given for its run on the head (--check-logs, a file named {run_id or 'by its run id'}.log)"
    if not any(m in text for m in markers):
        return "its log shows none of the profile's `ci.killed_markers`"
    # The profile's suites read their runners' counts; the defaults (pytest's) always count too.
    for suite in [*prof.suites, Suite("", "")]:
        for pattern in (suite.failed, suite.errors):
            try:
                if any(str(x).isdigit() and int(x) > 0 for x in re.findall(pattern, text)):
                    return "its log also shows tests that failed"
            except re.error:
                return "its log can't be read with the profile's suite counts"
    if any(_TEST_FAILED.search(x) for line in text.splitlines() for x in _log_lines(line)):
        return "its log also shows a test that failed"
    named = {code for m in markers for code in _EXIT_CODE.findall(m)}
    if set(_EXIT_CODE.findall(text)) - named:
        return "its log also shows an exit code no killed marker names"
    return None


def _evidence(ctx: Context, add) -> None:
    """flow §4.2: where the profile says `ci.none`, or a waiver was used on this
    head, `workflow evidence`'s report for the head is on the pull request: the
    latest comment, from an account with write access, whose first line is the
    report's headline for the head (a short SHA of 7 or more counts) says
    passed, not on a dirty tree, for the full suite (not only the suites the
    files need). Recommended always, required only there."""
    ctx.read_profile()
    prof = ctx.profile
    if prof and prof.ci_none:
        why = "the profile says `ci.none`"
    elif ctx.waived:
        why = f"{_names(ctx.waived)} was waived"
    else:
        return
    head = ctx.pr().head
    perms = ctx.permissions()
    found, latest = 0, None
    for c in ctx.comments():
        body = (c.get("body") or "").lstrip("\ufeff")
        first = body.split("\n", 1)[0].rstrip("\r") if body else ""
        line = read_headline(first) if body else None
        if line is None:
            continue
        found += 1
        sha, passed, dirty = line
        if head.startswith(sha) and _may_review(_login(c), perms):
            # Here the report is the proof, so only the full suite's counts.
            latest = passed and not dirty and is_full(first)
    if not latest:
        add("evidence_missing", why=why)
        if found:
            _note(ctx, "evidence_ignored", f"Left out {_plural(found, 'evidence report')}: none is the latest passing report for the head from an account with write access (one that says FAILED, names another commit, says \"on a dirty tree\", ran only the suites its files need, or comes from another account doesn't count).")


def _up_to_date(ctx: Context, add) -> None:
    """flow §4.3: the head isn't behind the base, or the merge queue the
    ruleset requires meets it (#245): the queue tests it on the latest base."""
    if ctx.queue():
        return
    behind = ctx.compare()
    if behind or ctx.pr().behind:
        add("behind", by=f" by {_plural(behind, 'commit')}" if behind else "")


def _panel(ctx: Context, add) -> None:
    """flow §4.4: a clean round on the head, or on an earlier commit of the PR
    with a later clean Correctness pass on the head. A round that wasn't clean
    needs another round, unless it is the last allowed one (its number at least
    `ctx.review_rounds`, #170): then a later clean Correctness pass on the head
    lifts its findings, and no further round is asked for. Where a pass is what
    comes next and the counted passes after the last round (on any commit of the
    PR, each record counted) number `ctx.review_passes`, the pass cap (#256)
    gives `passes_used_up` instead: the owner decides. Records from accounts
    without write access, or naming a commit outside the PR, are ignored.

    The small review (#257): when no counted round ran `spec`, the diff must be
    within the small threshold (`ctx.size`). Past it, `past_small_threshold`
    replaces every other review reason and asks for a full-panel round, allowed
    past the round limit. Within it, a round that isn't clean counts as the
    last allowed one, and so does that full-panel round, the first to run
    `spec` after rounds that didn't. Without the files' line counts, it says
    it can't read them, beside the reason today's rule gives.

    The free base merge (#261): when the head is a merge of the base
    (`ctx.base_merge`) and isn't the last counted review's commit, but its own
    changes hash the same with their context (`diff`), that review covers the
    head, with its result, clean or not. A pass doesn't count toward the cap
    when its commit is a merge of the base, the counted review before it was
    clean, its changed lines hash the same as that review's (`lines`), and no
    record on its commit since the last round wasn't clean; nor is the cap
    reached by a pass on the head that wouldn't count. A record without the
    hashes, or with `unknown`, covers only its own commit."""
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
    allowed = ctx.review_rounds
    details = {"round": last.round, "round_short": _short(last.commit), "allowed": allowed, "reviewers": list(last.reviewers)}
    ran_spec = ["spec" in counted[i].reviewers for i in rounds]
    unread = None
    last_allowed = last.round >= allowed or (ran_spec[-1] and len(rounds) > 1 and not any(ran_spec[:-1]))
    if not any(ran_spec):
        try:
            ctx.measured = ctx.size()
        except Unreadable as e:
            unread = e
        if ctx.measured is not None and not ctx.measured.within:
            m = ctx.measured
            size = f"{_plural(m.lines, 'changed line')} in {_plural(m.files, 'file')}"
            most = f"{_plural(m.max_lines, 'line')} in {_plural(m.max_files, 'file')}"
            add("past_small_threshold", next="full_round", size=size, most=most, **details)
            return
        last_allowed = last_allowed or ctx.measured is not None
    latest, hashes = counted[-1], ctx.head_hashes()  # the last counted review, round or pass
    # Only to a merge of the base (answer 4), and never over a review of the head itself since the last round:
    # a record posted late for an older commit doesn't override it.
    carried = (latest.commit != head and ctx.base_merge(head) and _hashed(latest.diff) and latest.diff == hashes.diff
               and not any(r.commit == head for r in counted[rounds[-1]:]))
    if carried:
        _note(ctx, "review_carried", f"The review of {_short(latest.commit)} covers the head {_short(head)}: the pull request's own changes, context included, are the same (its `diff` hash).")

    def on_head(r: reviews.Record) -> bool:
        return r.commit == head or (carried and r is latest)

    def free(i: int, commit: str | None, lines: str | None) -> bool:
        """A pass on `commit` after the counted record `i` doesn't count toward
        the cap (answer 23). One that rechecks open findings always counts: a
        record since the last round on that commit that wasn't clean."""
        prev, since = counted[i], counted[rounds[-1]:i + 1]
        return (ctx.base_merge(commit) and prev.clean and _hashed(lines) and lines == prev.lines
                and all(r.clean for r in since if r.commit == commit))

    after = [(i - 1, r) for i, r in enumerate(counted) if i > rounds[-1] and r.kind == "pass"]
    used = [r for i, r in after if not free(i, r.commit, r.lines)]
    if len(after) > len(used):
        _note(ctx, "free_passes", f"{_plural(len(after) - len(used), 'Correctness pass', 'Correctness passes')} after a merge of the base that left the pull request's changed lines as they were didn't count toward the pass cap.")
    passes = [r for _, r in after if on_head(r)]
    cap = ctx.review_passes

    def needs_pass(rid, **more):
        # A pass the head needs that wouldn't count doesn't meet the cap (answer 23: no false needs-human). It is
        # judged on GitHub's `lines` hash; the pass's record names git's, so where they differ, that pass counts.
        if len(used) >= cap and not free(len(counted) - 1, head, hashes.lines):
            posted = " posted" if len(used) == len(after) else f" counted of {len(after)} posted"
            add("passes_used_up", next="owner", passes=_plural(len(used), "Correctness pass", "Correctness passes") + posted, cap=cap, **details)
        else:
            add(rid, **more, **details)

    if not last.clean:
        if not last_allowed:
            add("review_not_clean", next="round", **details)
        elif not passes:
            needs_pass("review_not_clean", next="pass", case="last_round" if last.round >= allowed else "small" if not any(ran_spec) else "after_small")
        elif not passes[-1].clean:
            needs_pass("pass_not_clean")
    elif passes and not passes[-1].clean:
        needs_pass("pass_not_clean")
    elif not on_head(last) and not passes:
        needs_pass("review_stale")
    if unread is not None:
        raise unread


def _hashed(h: str | None) -> bool:
    """A record's hash that was computed: not missing (before #258), not `unknown`."""
    return h is not None and h != own_changes.UNKNOWN


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


def _previews_doc(sentence_start: bool = True) -> str:
    """Where the reader finds the page on adding try-it links: a vendored
    project's copy by its path from the project's root, else the kit's own
    ("The kit's" to open a sentence, else "the kit's")."""
    workflow = PREVIEWS_DOC.parents[1]
    if workflow.name == "workflow" and workflow.parent.name == ".claude":
        return "`.claude/workflow/docs/previews.md`"
    return f"{'The' if sentence_start else 'the'} kit's `docs/previews.md`"


def _preview(ctx: Context, add) -> None:
    """#30: where the project has previews, the head commit's built."""
    head = ctx.pr().head
    state, url, commit = ctx.preview_status()
    for_head = commit is not None and len(commit) >= 7 and head.startswith(commit.lower())
    on = bool(ctx.profile and ctx.profile.previews.on)
    if state == "none" and on and commit is not None and not for_head:
        # The reader's `none` names the head it read: one for another commit is a stale answer.
        add("preview_building", what=f"the preview is for {_short(commit)}, not the head {_short(head)}")
        return
    if state == "none":
        other_way = "check the change another way, as the PR's \"How to try it\" says."
        if ctx.profile is None:
            return  # a profile that can't be read (its own reason) may well have previews on: no claim either way
        if not on:
            how = f" {_previews_doc()} says how to add try-it links." if PREVIEWS_DOC.exists() else ""
            _note(ctx, "no_previews", f"There's no try-it link for this project: {other_way}{how}")
        elif not ctx.preview_given():
            _note(ctx, "no_previews", "Previews are on for this project, but this check was given no try-it link, so it can't say whether "
                  f"the link built: check again with it (`workflow preview` reads it, given as `--preview`). Until then, {other_way}")
        elif commit is None:
            _note(ctx, "preview_none", "There's no try-it link yet: Cloudflare hasn't reported on this pull request (no comment or check). "
                  f"Its build may not have started, or Cloudflare isn't connected to the repository. Until there is one, {other_way}")
        else:
            _note(ctx, "preview_none", f"There's no try-it link for {_short(head)}: Cloudflare built nothing to try for it. So {other_way}")
        return
    if state == "failed" and (for_head or commit is None):
        add("preview_failed", page=_previews_doc(sentence_start=False))
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


# ---------- the run's waivers ----------


def charter_from(text: str) -> dict:
    """The charter in a file: the charter as JSON, the tracking issue as GitHub
    returns it (its `body`), or the issue's body itself, from whose run state
    (`workflow state get`) it is taken. Raises ValueError saying what's wrong."""
    try:
        values = decode_values(text)
    except CommentsError:
        values = None
    if values and len(values) == 1 and isinstance(values[0], dict):
        v = values[0]
        if "version" in v and "merge" in v:
            return v
        if isinstance(v.get("body"), str):
            text = v["body"]
        else:
            raise ValueError("it is JSON, but neither a charter nor an issue with a body")
    elif values is not None and values:
        raise ValueError("it is JSON, but not a charter")
    try:
        s = state.get(text)
    except state.StateError as e:
        raise ValueError(str(e)) from None
    if not isinstance(s, dict) or not isinstance(s.get("charter"), dict):
        raise ValueError("no charter in it: give the charter's JSON, or the tracking issue's body with its run state")
    return s["charter"]


def waivers(charter_input: tuple | None, role: str | None, profile) -> tuple[frozenset, list[dict]]:
    """The checks the charter waives, and notes. `charter_input` is (text, None)
    or (None, why it couldn't be read); None when none was given. `role` is the
    session's as `WORKFLOW_ROLE` sets it (`roles.env_role`): waivers are taken
    only in a ticket or conductor session, never an attended one, nor where the
    role is only guessed from the branch or unrecognised (the guard reads both
    as ticket, its strictest, which for waivers would be the loosest). Nor from
    a charter that isn't approved by the owner, valid and in `merge.mode` session."""
    if charter_input is None:
        return frozenset(), []
    if role not in ("ticket", "conductor"):
        why = "in an attended session" if role == "attended" else "unless `WORKFLOW_ROLE` says this is a ticket or conductor session"
        return frozenset(), [{"id": "charter_ignored", "message": f"The charter (--charter) is ignored {why}: nobody waives a check by hand."}]
    text, error = charter_input
    problems: list[str] = []
    c = None
    if error is None:
        try:
            c = charter_from(text)
        except ValueError as e:
            error = str(e)
    if error is not None:
        problems = [f"couldn't read it: {error}"]
    elif profile is None or not profile.owner:
        problems = ["the profile names no `project.owner`, so who approved it can't be checked"]
    else:
        problems = charter_mod.validate(c, require_approval=True)
        if not problems:
            problems = charter_mod.against_profile(c, profile)
        if not problems and c["merge"].get("waived_checks") and c["merge"].get("mode") != "session":
            problems = [f"waivers need merge.mode session, and it is {c['merge'].get('mode')}"]
    if problems:
        return frozenset(), [{"id": "charter_refused", "message": CHARTER_REFUSED + _clean("; ".join(problems)) + "."}]
    return frozenset(c["merge"].get("waived_checks") or []), []


# ---------- the decision ----------


def _reason(rid: str, rule: Rule | None, level: str, details: dict, wording_id: str | None = None) -> dict:
    reason = REASONS[wording_id or rid]
    details = {k: _clean(v) if isinstance(v, str) else v for k, v in details.items()}
    worded = reason.cases[details["case"]] if details.get("case") else reason.wording
    wording = {lvl: {"message": m.format(**details), "fix": f.format(**details)} for lvl, (m, f) in worded.items()}
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
    if rule is not None and rule.id == "review_panel" and "round" in details:
        # The counted round, so a caller needn't parse the wording (#122's notes);
        # for review_not_clean, `next` says what lifts it: another round, or a pass.
        out["round"], out["reviewers"] = details["round"], details["reviewers"]
        if "next" in details:
            out["next"] = details["next"]
    return out


def evaluate(
    inputs: dict,
    profile=None,
    profile_error: str | None = None,
    asker: str | None = None,
    level: str = "new",
    charter_input: tuple | None = None,
    logs: dict | None = None,
    role: str | None = None,
    review_rounds: int | None = None,
    review_passes: int | None = None,
    small_max_lines: int | None = None,
    small_max_files: int | None = None,
) -> Result:
    """The decision. `inputs` maps each name in INPUTS to (value, None) when
    read, (None, why) when it couldn't be; a name left out wasn't given (the
    preview: none). `profile_error` says why the profile couldn't be read.
    `charter_input` and `role` (see `waivers`) and `logs` (the checks' logs,
    by file name) are for the run's waivers. `review_rounds` is the allowed
    review rounds (`--review-rounds`); None takes the profile's `run.review_rounds`.
    `review_passes` is the pass cap (`--review-passes`); None takes the profile's
    `run.review_passes`. `small_max_lines` and `small_max_files` are the small
    threshold (`--small-max-lines`, `--small-max-files`); None takes the profile's."""
    waivable, charter_notes = waivers(charter_input, role, profile)
    ctx = Context(inputs, profile, profile_error, waivable, logs, review_rounds, review_passes, small_max_lines, small_max_files)
    ctx.notes += charter_notes
    if waivable and (ctx.queue() or ctx.queue_unsure()):
        # Every merge goes through the queue, and only a direct merge could take a waiver (#241, answer 13);
        # a queue it can't rule out refuses them too.
        ctx.waivable = frozenset()
        why = "with the merge queue on" if ctx.queue() else "where a ruleset may require a merge queue"
        _note(ctx, "charter_refused", CHARTER_REFUSED + f"waivers don't apply {why} (flow §4.1).")
    try:
        pr = ctx.pr()
        number, head, base = pr.number, pr.head, pr.base
    except Unreadable:
        number, head, base = None, None, profile.base_branch if profile else "main"
    common = {"short": _short(head), "base": base, "number": number if number is not None else "<n>"}

    def unreadable(e: Unreadable) -> dict:
        what = "the profile" if e.name == PROFILE else INPUTS[e.name]
        details = {**common, "input": e.name, "what": what, "why": e.why.rstrip("."), **({"case": "preview"} if e.name == "preview" else {})}
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
    queue = ctx.queue()
    if queue:
        _note(ctx, "queue", "The base's ruleset requires a merge queue, which meets flow §4.3 (up to date), so \"ready\" means ready to queue. "
              "These rules are checked when it is queued: a request made after that (changes requested, a new review thread) doesn't stop the merge.")
    elif ctx.queue_unsure():
        _note(ctx, "queue_unsure", "A merge-queue rule in a ruleset this command can't judge isn't counted as a queue: " + "; ".join(ctx.queue_unsure()) + ".")
    kit = ctx.kit
    if reasons:
        decision = "not_yet"
        if kit:
            _note(ctx, "kit_files", "This change touches the kit's or CI files (" + _names(kit) + "): once everything else holds, it needs the owner's review.")
    elif kit:
        decision = "owner_review"
    else:
        decision = "ready"
    return Result(decision, number, head, level, owner, reasons, ctx.notes, ctx.checks, kit, ctx.preview, ctx.review_rounds, ctx.review_passes,
                  ctx.small_max_lines, ctx.small_max_files, ctx.measured.as_dict() if ctx.measured else None, queue, ctx.head_hashes())


# ---------- text ----------


def text(res: Result) -> str:
    """The answer for people: the decision first, then each reason and its fix."""
    n = f"#{res.pr}" if res.pr is not None else "This pull request"
    if res.decision == "ready":
        lines = [f"Ready to queue: {n} may join the merge queue." if res.queue else f"Ready: {n} may merge."]
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
