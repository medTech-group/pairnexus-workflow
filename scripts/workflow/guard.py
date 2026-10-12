"""The guard: a PreToolUse hook. Defence in depth, never the only boundary.

The real boundaries are GitHub rulesets on the base branch, a credential-free
cloud environment for ticket sessions, and CODEOWNERS on protected paths
(docs/enforcement.md). The guard catches the common ways a session would break
the never-list, so a mistake is stopped early and said plainly:

- pushing to the base branch, force-pushing, deleting or mirroring branches,
  rewriting the base branch or its protection through the API;
- deploy commands named in the profile;
- writing protected paths (by Edit/Write, by shell, or through GitHub's file tools);
- adding a skip marker to a test file;
- posting sensitive data (the profile's patterns) to issues, comments or PRs.

Ticket sessions are denied. Attended sessions are asked (the person decides).
The conductor is denied pushes to base and force-pushes; deploys and protected
paths are its own to do under the charter, through reviewed PRs.
"""

from __future__ import annotations

import fnmatch
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from .profile import Profile

SKIP_MARKERS = [
    r"@pytest\.mark\.skip(?:if)?\b",
    r"\bpytest\.skip\(",
    r"@unittest\.skip",
    r"\b(?:it|test|describe|context)\.skip\(",
    r"\bx(?:it|test|describe)\(",
    r"\bskip\s*:\s*(?:true|['\"])",
    r"@Disabled\b",
    r"\bt\.Skip(?:Now|f)?\(",
    r"#\[ignore\]",
    r"\bmarkTestSkipped\(",
]
_SKIP = re.compile("|".join(SKIP_MARKERS))

GITHUB_WRITE_FILES = {"push_files", "create_or_update_file", "delete_file"}
GITHUB_POSTS = {
    "issue_write",
    "add_issue_comment",
    "create_pull_request",
    "update_pull_request",
    "add_reply_to_pull_request_comment",
    "pull_request_review_write",
    "add_comment_to_pending_review",
    "update_issue_comment",
    "create_or_update_file",
    "push_files",
}
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


@dataclass
class Decision:
    action: str  # "allow", "deny" or "ask"
    reason: str = ""


ALLOW = Decision("allow")


def _rel(path: str, root: Path) -> str:
    p = Path(path)
    if p.is_absolute():
        try:
            p = p.resolve().relative_to(root.resolve())
        except ValueError:
            return str(p)
    s = str(p).replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return s


def matches(rel: str, patterns: list[str]) -> str | None:
    for pat in patterns:
        cands = [pat]
        if pat.startswith("**/"):
            cands.append(pat[3:])
        if pat.endswith("/**"):
            cands.append(pat[:-3])
        for c in cands:
            if fnmatch.fnmatchcase(rel, c):
                return pat
    return None


def _strings(obj) -> list[str]:
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out += _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            out += _strings(v)
    return out


# ---------- shell ----------

_OPS = {";", "&&", "||", "|", "&", "(", ")", "|&", ";;", "\n"}
_REDIRECT = re.compile(r"^\d*(>>?|>\|)$")


def _tokens(command: str) -> list[str]:
    """Shell tokens with operators split out, quotes respected."""
    lex = shlex.shlex(command.replace("\n", " ; ").replace("`", " ; ").replace("$(", " ( "), posix=True, punctuation_chars=";&|()<>")
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        return list(lex)
    except ValueError:  # unbalanced quotes: fall back to a rough split
        rough = re.sub(r"(&&|\|\||;|\||\(|\))", r" \1 ", command.replace('"', " ").replace("'", " "))
        return rough.split()


def _simple_commands(command: str) -> list[tuple[list[str], list[str]]]:
    """Each simple command as (words, redirect targets)."""
    out: list[tuple[list[str], list[str]]] = []
    words: list[str] = []
    targets: list[str] = []
    toks = _tokens(command)
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in _OPS:
            if words or targets:
                out.append((words, targets))
            words, targets = [], []
        elif t in {">", ">>", ">|"} or _REDIRECT.match(t):
            if i + 1 < len(toks) and toks[i + 1] not in _OPS:
                nxt = toks[i + 1]
                if nxt == "&" or nxt.startswith("&"):
                    i += 1
                else:
                    targets.append(nxt)
                    i += 1
        elif t in {"<", "<<", "<<<"}:
            i += 1  # skip the input source
        else:
            words.append(t)
        i += 1
    if words or targets:
        out.append((words, targets))
    return out


def _strip_prefix(toks: list[str]) -> list[str]:
    while toks and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]):
        toks = toks[1:]  # leading VAR=value
    while toks and toks[0] in {"sudo", "env", "nohup", "time", "exec", "command", "xargs", "timeout", "nice"}:
        toks = toks[1:]
        while toks and (toks[0].startswith("-") or re.match(r"^\d+[smh]?$", toks[0]) or "=" in toks[0]):
            toks = toks[1:]
    return toks


def _segments(command: str, depth: int = 0) -> list[tuple[list[str], list[str]]]:
    """Each simple command (words, redirect targets), recursing into `sh -c "..."` and python one-liners."""
    segs: list[tuple[list[str], list[str]]] = []
    for words, targets in _simple_commands(command):
        toks = _strip_prefix(words)
        if not toks and not targets:
            continue
        segs.append((toks, targets))
        if not toks or depth >= 3:
            continue
        name = Path(toks[0]).name
        if name in {"sh", "bash", "zsh", "dash", "ksh"} and "-c" in toks:
            i = toks.index("-c")
            if i + 1 < len(toks):
                segs += _segments(toks[i + 1], depth + 1)
        elif name.startswith("python") and "-c" in toks:
            i = toks.index("-c")
            if i + 1 < len(toks):
                for lit in re.findall(r"""['"]([^'"]*\b(?:git|gh)\b[^'"]*)['"]""", toks[i + 1]):
                    segs += _segments(lit, depth + 1)
        elif name == "eval" and len(toks) > 1:
            segs += _segments(" ".join(toks[1:]), depth + 1)
    return segs


def _git_args(toks: list[str]) -> list[str] | None:
    if Path(toks[0]).name != "git":
        return None
    i = 1
    while i < len(toks) and toks[i].startswith("-"):
        i += 2 if toks[i] in {"-C", "-c", "--git-dir", "--work-tree", "--namespace"} else 1
    return toks[i:]


def _push_problem(args: list[str], base: str, current: str | None) -> str | None:
    if not args or args[0] != "push":
        return None
    rest = args[1:]
    flags = [a for a in rest if a.startswith("-")]
    pos = [a for a in rest if not a.startswith("-")]
    for f in flags:
        if f in {"-f", "--force", "--mirror", "--all", "--delete", "-d", "--prune"} or f.startswith(
            ("--force-with-lease", "--force-if-includes")
        ):
            return f"`git push {f}` is never allowed (force-push, delete, mirror or push-all)"
        if re.match(r"^-[a-zA-Z]*f", f) and not f.startswith("--"):
            return "`git push -f` (force-push) is never allowed"
    refspecs = pos[1:] if pos else []
    for r in refspecs:
        if r.startswith("+"):
            return f"`git push {r}` is a force-push (a leading +), which is never allowed"
        dst = r.split(":", 1)[1] if ":" in r else r
        dst = dst.removeprefix("refs/heads/")
        if r.startswith(":"):
            return f"`git push {r}` deletes a branch, which is never allowed"
        if dst == base or (dst == "HEAD" and current == base):
            return f"pushing to the base branch `{base}` is never allowed: open a pull request"
    if not refspecs and current == base:
        return f"you are on the base branch `{base}`: pushing it is never allowed; work on a branch and open a pull request"
    return None


def _api_problem(toks: list[str], base: str) -> str | None:
    if Path(toks[0]).name not in {"gh", "curl", "http", "https"}:
        return None
    joined = " ".join(toks)
    if re.search(rf"/git/refs/heads/{re.escape(base)}\b", joined) and re.search(
        r"(-X|--method|--request)\s*(PATCH|POST|PUT|DELETE)", joined, re.I
    ):
        return f"rewriting the base branch `{base}` through the API is never allowed"
    if re.search(r"/branches/[^/\s]+/protection|/rulesets\b", joined) and re.search(
        r"(-X|--method|--request)\s*(PATCH|POST|PUT|DELETE)", joined, re.I
    ):
        return "changing branch protection or rulesets is the owner's alone"
    return None


_WRITERS = {"rm", "mv", "cp", "tee", "truncate", "chmod", "chown", "ln", "install", "dd", "rsync", "unlink", "touch"}


def _shell_writes_protected(seg: list[str], redirects: list[str], protected: list[str], root: Path) -> str | None:
    for tgt in redirects:
        if tgt in {"/dev/null", "/dev/stderr", "/dev/stdout"}:
            continue
        hit = matches(_rel(tgt, root), protected)
        if hit:
            return f"redirecting into `{tgt}` writes a protected path ({hit})"
    if not seg:
        return None
    cmd = Path(seg[0]).name
    targets: list[str] = []
    if cmd in _WRITERS:
        targets = [t for t in seg[1:] if not t.startswith("-")]
    elif cmd == "sed" and any(t == "-i" or t.startswith("-i") or t == "--in-place" for t in seg[1:]):
        targets = [t for t in seg[1:] if not t.startswith("-")][1:]
    elif cmd in {"git"}:
        a = _git_args(seg) or []
        if a[:1] in (["checkout"], ["restore"], ["rm"], ["mv"]):
            targets = [t for t in a[1:] if not t.startswith("-") and t != "--"]
    for t in targets:
        m = matches(_rel(t, root), protected)
        if m:
            return f"`{cmd}` on `{t}` writes a protected path ({m})"
    return None


def _deploy_problem(command: str, deploy: list[str]) -> str | None:
    norm = " ".join(command.split())
    for d in deploy:
        dn = " ".join(d.split())
        if not dn:
            continue
        if re.search(rf"(?:^|[\s;&|(/'\"]){re.escape(dn)}(?:$|[\s;&|)'\"])", norm) or (
            "/" in dn and dn in norm
        ):
            return f"`{d}` is a deploy command: only the owner, or the conductor under a release grant, runs it"
    return None


def check_bash(command: str, profile: Profile, role: str, root: Path, current_branch: str | None) -> Decision:
    base = profile.base_branch
    segs = _segments(command)
    for seg, _redirects in segs:
        if not seg:
            continue
        g = _git_args(seg)
        if g is not None:
            p = _push_problem(g, base, current_branch)
            if p:
                return Decision("deny" if role != "attended" else "ask", p)
        p = _api_problem(seg, base)
        if p:
            return Decision("deny" if role != "attended" else "ask", p)
    if role == "ticket":
        p = _deploy_problem(command, profile.deploy_commands)
        if p:
            return Decision("deny", p)
        for seg, redirects in segs:
            p = _shell_writes_protected(seg, redirects, profile.protected_paths, root)
            if p:
                return Decision("deny", p + "; ticket sessions don't change protected paths (the owner reviews those)")
    elif role == "attended":
        p = _deploy_problem(command, profile.deploy_commands)
        if p:
            return Decision("ask", p)
    return ALLOW


# ---------- file tools ----------


def _added_skips(old: str, new: str) -> int:
    return len(_SKIP.findall(new or "")) - len(_SKIP.findall(old or ""))


def check_write(tool: str, inp: dict, profile: Profile, role: str, root: Path) -> Decision:
    path = inp.get("file_path") or inp.get("notebook_path") or ""
    rel = _rel(path, root) if path else ""
    if role == "ticket" and rel:
        m = matches(rel, profile.protected_paths)
        if m:
            return Decision("deny", f"`{rel}` is a protected path ({m}); ticket sessions don't change it (the owner reviews those)")
    if role != "ticket" or profile.allow_new_skips or not rel or not matches(rel, profile.test_paths):
        return ALLOW
    if tool == "Edit":
        added = _added_skips(inp.get("old_string", ""), inp.get("new_string", ""))
    elif tool == "MultiEdit":
        added = sum(_added_skips(e.get("old_string", ""), e.get("new_string", "")) for e in inp.get("edits") or [])
    elif tool == "Write":
        try:
            old = (root / rel).read_text(encoding="utf-8")
        except OSError:
            old = ""
        added = _added_skips(old, inp.get("content", ""))
    else:
        added = 0
    if added > 0:
        return Decision("deny", f"this adds a skip marker to the test file `{rel}`; skipping or disabling a test is never allowed: fix the test or the code")
    return ALLOW


# ---------- MCP (GitHub) ----------


def check_mcp(tool: str, inp: dict, profile: Profile, role: str, root: Path) -> Decision:
    m = re.match(r"^mcp__([^_].*?)__(.+)$", tool)
    if not m:
        return ALLOW
    server, name = m.group(1), m.group(2)
    if "github" not in server.lower():
        return ALLOW
    if name in GITHUB_WRITE_FILES:
        branch = (inp.get("branch") or "").removeprefix("refs/heads/")
        if branch == profile.base_branch or not branch:
            return Decision(
                "deny" if role != "attended" else "ask",
                f"`{name}` would write straight to the base branch `{profile.base_branch}`; work on a branch and open a pull request",
            )
        if role == "ticket":
            paths = [inp.get("path") or ""] + [f.get("path", "") for f in inp.get("files") or [] if isinstance(f, dict)]
            for pth in paths:
                hit = pth and matches(_rel(pth, root), profile.protected_paths)
                if hit:
                    return Decision("deny", f"`{pth}` is a protected path ({hit}); ticket sessions don't change it")
    if name in GITHUB_POSTS and profile.sensitive_patterns:
        text = "\n".join(_strings(inp))
        for pat in profile.sensitive_patterns:
            if re.search(pat, text):
                return Decision(
                    "deny" if role != "attended" else "ask",
                    f"this {name} would post text matching the project's sensitive-data pattern {pat!r} "
                    f"({profile.sensitive_description or 'see profile.md'}); remove it and refer to things by id",
                )
    return ALLOW


def decide(event: dict, profile: Profile, role: str, root: Path, current_branch: str | None) -> Decision:
    tool = event.get("tool_name") or ""
    inp = event.get("tool_input") or {}
    if tool == "Bash":
        return check_bash(inp.get("command") or "", profile, role, root, current_branch)
    if tool in WRITE_TOOLS:
        return check_write(tool, inp, profile, role, root)
    if tool.startswith("mcp__"):
        return check_mcp(tool, inp, profile, role, root)
    return ALLOW
