"""The "release gate" check's decision (#88): the `release gate` workflow
(`.github/workflows/release-gate.yml`) runs it on every pull request.

It is fed JSON and text files the workflow reads from the API when it runs,
prints one line, `pass: <reason>` or `fail: <reason>`, and exits 0 on a pass,
1 on a fail. It changes nothing.

- A pull request that doesn't change VERSION passes (it needs only --pr and --files).
- A release pull request passes when the newest gate line for its head commit,
  from an authorised comment, says pass. A gate line is a line of its own,
  `release-gate: pass <sha>` or `release-gate: fail <sha>`, with the full
  40-character SHA. Authorised: the comment carries the agents' marker and its
  author's permission is write, maintain or admin; an author missing from the
  permissions counts as without write access. Comments are read in the order
  they were posted, so a later fail for the same commit wins.
- Or it is an allowed skip: the `release-gate-skipped` label, a "Gate skipped
  because ..." line in the description, and a "Release gate skipped because ..."
  line in the new version's CHANGELOG entry (the release notes). Never twice in
  a row: refused when the base version's entry has that line too.

Its own code, not merge-check's (#80): the check judges the candidate kit, so it
never imports the `scripts/workflow` it's judging. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

MARKER = "<!-- workflow:agent -->"
WRITE = {"write", "maintain", "admin"}
SKIP_LABEL = "release-gate-skipped"
GATE_LINE = re.compile(r"^release-gate: (pass|fail) ([0-9a-f]{40})[ \t]*$", re.M)
PR_SKIP = re.compile(r"^[ \t>*_-]*Gate skipped because[ \t]+\S", re.M)
LOG_SKIP = re.compile(r"^[ \t>*_-]*Release gate skipped because[ \t]+\S", re.M)


class Unreadable(Exception):
    pass


def _json(path: str | None, name: str):
    if path is None:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise Unreadable(f"couldn't read the {name} ({e})") from None


def _text(path: str | None, name: str) -> str | None:
    if path is None:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        raise Unreadable(f"couldn't read the {name} ({e})") from None


def _flat(v) -> list:
    """A list, or `gh api --paginate --slurp`'s list of pages, as one list."""
    if not isinstance(v, list):
        return []
    out = []
    for x in v:
        out.extend(x if isinstance(x, list) else [x])
    return out


def changes_version(files) -> bool:
    return any(isinstance(f, dict) and "VERSION" in (f.get("filename"), f.get("previous_filename"))
               for f in _flat(files))


def entry(changelog: str, version: str) -> str | None:
    """A version's CHANGELOG entry, as release.py reads it for the release notes."""
    m = re.search(rf"^## {re.escape(version)}(?:[ \t][^\n]*)?\n(.*?)(?=^## |\Z)", changelog, re.S | re.M)
    return m.group(1) if m else None


def report(comments, permissions: dict, head: str) -> tuple[bool, str]:
    """(passed, reason) from the authorised gate lines."""
    perms = {str(k).casefold(): str(v).lower() for k, v in permissions.items()}
    rows = [c for c in _flat(comments) if isinstance(c, dict)]
    rows.sort(key=lambda c: (str(c.get("created_at") or ""), c.get("id") or 0))
    lines = []  # (verdict, sha, link), oldest first
    for c in rows:
        body = c.get("body") or ""
        login = str(((c.get("user") or {}).get("login")) or "").casefold()
        if MARKER not in body or perms.get(login) not in WRITE:
            continue
        for verdict, sha in GATE_LINE.findall(body):
            lines.append((verdict, sha, c.get("html_url") or f"comment {c.get('id')}"))
    if not lines:
        return False, "no release gate report yet: run the release gate on this pull request"
    mine = [x for x in lines if x[1] == head]
    if not mine:
        return False, (f"the newest release gate report is for {lines[-1][1]}, not the head commit {head}: "
                       "run the release gate again")
    verdict, _, link = mine[-1]
    if verdict == "pass":
        return True, f"the release gate passed for the head commit {head} ({link})"
    return False, f"the release gate failed for the head commit {head}: {link}"


def skip(pr: dict, changelog: str, head_version: str, base_version: str) -> tuple[bool, str]:
    """(allowed, reason) for skipping the gate."""
    labels = {(lab.get("name") if isinstance(lab, dict) else lab) for lab in pr.get("labels") or []}
    missing = []
    if SKIP_LABEL not in labels:
        missing.append(f"the `{SKIP_LABEL}` label")
    if not PR_SKIP.search(pr.get("body") or ""):
        missing.append('a "Gate skipped because ..." line in the description')
    new = entry(changelog, head_version) if head_version else None
    if new is None:
        missing.append(f'a "Release gate skipped because ..." line in the CHANGELOG (it has no {head_version or "new version"} entry)')
    elif not LOG_SKIP.search(new):
        missing.append(f'a "Release gate skipped because ..." line in the CHANGELOG\'s {head_version} entry')
    if missing:
        return False, "the skip is missing " + ", ".join(missing)
    old = entry(changelog, base_version) if base_version else None
    if old is not None and LOG_SKIP.search(old):
        return False, (f"the skip is refused: the last release skipped the gate ({base_version}'s CHANGELOG entry), "
                       "and it's never skipped twice in a row; run the release gate")
    return True, f"the gate is skipped for {head_version}, with its label and both lines"


def decide(args) -> tuple[bool, str]:
    pr = _json(args.pr, "pull request")
    files = _json(args.files, "changed files")
    if not isinstance(pr, dict):
        raise Unreadable("couldn't read the pull request (--pr)")
    if not isinstance(files, list):
        raise Unreadable("couldn't read the changed files (--files)")
    if not changes_version(files):
        return True, "this pull request doesn't change VERSION"
    head = str((pr.get("head") or {}).get("sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise Unreadable("couldn't read the pull request's head commit")
    need = {"comments": args.comments, "permissions": args.permissions, "changelog": args.changelog,
            "version-head": args.version_head, "version-base": args.version_base}
    absent = [k for k, v in need.items() if v is None]
    if absent:
        raise Unreadable("this pull request changes VERSION, and these weren't given: "
                         + ", ".join(f"--{k}" for k in absent))
    comments = _json(args.comments, "comments")
    permissions = _json(args.permissions, "permissions")
    if not isinstance(permissions, dict):
        raise Unreadable("couldn't read the permissions (a map of login to permission)")
    changelog = _text(args.changelog, "CHANGELOG") or ""
    head_version = (_text(args.version_head, "head's VERSION") or "").strip()
    base_version = (_text(args.version_base, "base's VERSION") or "").strip()
    passed, why = report(comments, permissions, head)
    if passed:
        return True, why
    labels = {(lab.get("name") if isinstance(lab, dict) else lab) for lab in pr.get("labels") or []}
    new = entry(changelog, head_version) if head_version else None
    tried = (SKIP_LABEL in labels or PR_SKIP.search(pr.get("body") or "")
             or (new is not None and LOG_SKIP.search(new)))
    if tried:
        return skip(pr, changelog, head_version, base_version)
    return False, why


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pr", help="the pull request (GET /repos/{o}/{r}/pulls/{n})")
    ap.add_argument("--files", help="its changed files (GET .../pulls/{n}/files; pages allowed)")
    ap.add_argument("--comments", help="its issue comments (GET .../issues/{n}/comments; pages allowed)")
    ap.add_argument("--permissions", help="a map of each comment author's login to their permission")
    ap.add_argument("--changelog", help="CHANGELOG.md at the head")
    ap.add_argument("--version-head", help="VERSION at the head")
    ap.add_argument("--version-base", help="VERSION at the base (an empty file when there is none)")
    args = ap.parse_args(argv)
    try:
        passed, why = decide(args)
    except Unreadable as e:
        passed, why = False, str(e)
    print(("pass: " if passed else "fail: ") + why)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
