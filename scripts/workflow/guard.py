"""The guard: a PreToolUse hook. Defence in depth, never the only boundary.

The real boundaries are GitHub rulesets on the base branch, a credential-free
cloud environment for ticket sessions, and CODEOWNERS on protected paths
(docs/enforcement.md). The guard catches the common ways a session would break
the never-list, so a mistake is stopped early and said plainly.

**Ticket sessions are held to allow-lists** where a deny-list can't keep up:
- `git push` may only update branches matching the profile's `run.ticket_branch`;
- GitHub API writes (`gh api`) may only touch issues, comments, labels and pull
  requests: no refs, contents, merges-by-API, protection or rulesets, and no
  GraphQL mutations;
- `git config` may not set aliases or push settings.

**Every role** is held to a deny-list: pushing to the base branch, force-pushes,
deleting or mirroring branches, `gh pr merge --admin`, and rewriting the base
branch, its protection or rulesets through the API. Ticket sessions and the
conductor are denied; attended sessions are asked.

**Ticket sessions also may not:** run the profile's deploy commands, write
protected paths (Edit/Write, the shell's common writers, GitHub's file tools),
add skip or focus markers to tests, or switch to a branch outside the pattern
when their role comes only from the branch name. A GitHub post (MCP or `gh`)
matching the profile's sensitive patterns is refused in every role.

What it can't see (a script file written then run, a program's own network
calls, obfuscated commands) is why the ruleset and the environment come first.
"""

from __future__ import annotations

import fnmatch
import os
import posixpath
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .profile import Profile

SKIP_MARKERS = [
    r"pytest\.mark\.skip(?:if)?\b",
    r"\bpytest\.skip\(",
    r"\bunittest\.skip",
    r"\bskipTest\(",
    r"\bSkipTest\b",
    r"pytest\.mark\.xfail\([^)]*run\s*=\s*False",
    r"\b(?:it|test|describe|context|suite)\.(?:skip|only|todo)\(",
    r"\bx(?:it|test|describe|context)\(",
    r"\bf(?:it|describe)\(",
    r"\bskip\s*:\s*(?:true|['\"])",
    r"@Disabled\b",
    r"@Ignore\b",
    r"\bt\.Skip(?:Now|f)?\(",
    r"#\[ignore\]",
    r"\bmarkTestSkipped\(",
    r"collection_modifyitems",
]
_SKIP = re.compile("|".join(SKIP_MARKERS))

GITHUB_WRITE_FILES = {"push_files", "create_or_update_file", "delete_file"}
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
_READ_PREFIXES = ("get_", "list_", "search_")


@dataclass
class Decision:
    action: str  # "allow", "deny" or "ask"
    reason: str = ""


ALLOW = Decision("allow")


def _deny(role: str, reason: str) -> Decision:
    if role == "attended":
        return Decision("ask", reason.replace("is never allowed", "is outside the workflow's rules; allow it only if you mean to"))
    return Decision("deny", reason)


# ---------- paths ----------


def _norm(path: str, root: Path, cwd: str = "") -> str:
    """A path relative to the project root, normalised (.., ./, absolute)."""
    p = path.strip().strip("'\"")
    if not p:
        return ""
    if os.path.isabs(p):
        try:
            rel = os.path.relpath(os.path.normpath(p), os.path.normpath(str(root)))
        except ValueError:
            return p
        return p if rel.startswith("..") else ("" if rel == "." else rel.replace(os.sep, "/"))
    joined = posixpath.normpath(posixpath.join(cwd or ".", p.replace("\\", "/")))
    return "" if joined == "." else joined


def matches(rel: str, patterns: list[str]) -> str | None:
    r = rel.casefold()
    for pat in patterns:
        pf = pat.casefold()
        cands = [pf]
        if pf.startswith("**/"):
            cands.append(pf[3:])
        if pf.endswith("/**"):
            cands.append(pf[:-3])
        for c in cands:
            if fnmatch.fnmatchcase(r, c):
                return pat
    return None


def _literal_dir(pat: str) -> str:
    m = re.match(r"^[^*?\[]*", pat)
    head = m.group(0) if m else ""
    return head.rsplit("/", 1)[0] if "/" in head else ""


def contains_protected(rel: str, patterns: list[str]) -> str | None:
    """`rel` is, or is a directory holding, a protected path."""
    hit = matches(rel, patterns)
    if hit:
        return hit
    r = rel.casefold().rstrip("/")
    for pat in patterns:
        head = _literal_dir(pat).casefold()
        if not head:
            continue
        if r == "" or head == r or head.startswith(r + "/"):
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


# ---------- shell parsing ----------

_OPS = {";", "&&", "||", "|", "&", "(", ")", "|&", ";;"}
_KEYWORDS = {"{", "}", "!", "if", "then", "else", "elif", "fi", "do", "done", "while", "until", "case", "esac", "coproc", "time", "select"}
_WRAPPERS: dict[str, set[str]] = {
    "sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U"},
    "env": {"-u", "-C", "-S", "--unset", "--chdir"},
    "nohup": set(),
    "exec": {"-a"},
    "command": set(),
    "builtin": set(),
    "nice": {"-n"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "xargs": {"-I", "-n", "-L", "-P", "-d", "-a", "-E", "-s", "--max-args", "--replace"},
    "watch": {"-n", "-d", "--interval"},
    "stdbuf": {"-i", "-o", "-e"},
    "ionice": {"-c", "-n"},
    "chronic": set(),
}
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1([^\n]*)\n.*?\n[ \t]*\2[ \t]*(?=\n|$)", re.S)


@dataclass
class Seg:
    words: list[str]
    redirects: list[str] = field(default_factory=list)
    cwd: str = ""  # relative to the project root, tracked through `cd`


def _strip_heredocs(command: str) -> str:
    """Drop heredoc bodies (PR text, file contents): they aren't commands."""
    return _HEREDOC.sub(lambda m: "<<" + m.group(2) + m.group(3), command)


def _tokens(command: str) -> list[str]:
    c = command.replace("\\\n", "")
    c = re.sub(r"\$'((?:[^'\\]|\\.)*)'", lambda m: "'" + m.group(1).encode().decode("unicode_escape", "ignore") + "'", c)
    c = c.replace('$"', '"')
    c = c.replace("\n", " ; ").replace("`", " ; ").replace("$(", " ( ")
    lex = shlex.shlex(c, posix=True, punctuation_chars=";&|()<>")
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        return list(lex)
    except ValueError:
        rough = re.sub(r"(&&|\|\||;|\||\(|\)|<|>)", r" \1 ", c.replace('"', " ").replace("'", " "))
        return rough.split()


def _simple(command: str) -> list[tuple[list[str], list[str]]]:
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
        elif re.fullmatch(r"\d*(?:>>?|>\|)|&>>?|>&", t):
            nxt = toks[i + 1] if i + 1 < len(toks) else ""
            if nxt and nxt not in _OPS:
                if not (t == ">&" and (nxt.isdigit() or nxt == "-")):
                    targets.append(nxt)
                i += 1
        elif t in {"<", "<<", "<<<", "<&"}:
            i += 1
        elif t.startswith("<<"):
            pass
        else:
            words.append(t)
        i += 1
    if words or targets:
        out.append((words, targets))
    return out


def _strip_prefix(toks: list[str]) -> list[str]:
    changed = True
    while toks and changed:
        changed = False
        while toks and (toks[0] in _KEYWORDS or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0])):
            toks = toks[1:]
            changed = True
        if toks and toks[0] == "for":
            toks = toks[toks.index("do") + 1 :] if "do" in toks else []
            changed = True
        if toks and Path(toks[0]).name in _WRAPPERS:
            takes = _WRAPPERS[Path(toks[0]).name]
            toks = toks[1:]
            while toks and (toks[0].startswith("-") or re.match(r"^\d+(\.\d+)?[smhd]?$", toks[0]) or "=" in toks[0]):
                t = toks[0]
                toks = toks[1:]
                if t in takes and toks:
                    toks = toks[1:]
            changed = True
    return toks


def _shell_c(toks: list[str]) -> str | None:
    for i, t in enumerate(toks[1:], 1):
        if re.fullmatch(r"-[a-zA-Z]*c[a-zA-Z]*", t) and i + 1 < len(toks):
            return toks[i + 1]
    return None


_INTERP = re.compile(r"^(python\d?(\.\d+)?|node|perl|ruby)$")


def _inline_code(toks: list[str]) -> str:
    return next((toks[i + 1] for i, t in enumerate(toks[:-1]) if t in {"-c", "-e", "-E"}), "")


def segments(command: str, root: Path, depth: int = 0, cwd: str = "") -> list[Seg]:
    """Each simple command, with `cd` tracked, recursing into `sh -c`, `eval`
    and interpreter one-liners that hold git/gh commands."""
    segs: list[Seg] = []
    for words, targets in _simple(_strip_heredocs(command)):
        toks = _strip_prefix(words)
        if toks and toks[0] in ("cd", "pushd") and len(toks) > 1:
            cwd = _norm(toks[1], root, cwd)
            segs.append(Seg(toks, targets, cwd))
            continue
        if not toks and not targets:
            continue
        segs.append(Seg(toks, targets, cwd))
        if not toks or depth >= 3:
            continue
        name = Path(toks[0]).name
        if name in {"sh", "bash", "zsh", "dash", "ksh", "fish"}:
            inner = _shell_c(toks)
            if inner is not None:
                segs += segments(inner, root, depth + 1, cwd)
        elif name == "eval" and len(toks) > 1:
            segs += segments(" ".join(toks[1:]), root, depth + 1, cwd)
        elif _INTERP.match(name):
            for lit in re.findall(r"""['"]([^'"]*\b(?:git|gh)\b[^'"]*)['"]""", _inline_code(toks)):
                segs += segments(lit, root, depth + 1, cwd)
    return segs


def _branch_of(root: Path, cwd: str, explicit_dir: str | None) -> str | None:
    if explicit_dir:
        d = explicit_dir if os.path.isabs(explicit_dir) else str(root / cwd / explicit_dir)
    else:
        d = str(root / cwd) if cwd else str(root)
    try:
        out = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=d, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired, NotADirectoryError):
        return None
    b = out.stdout.strip()
    return b if out.returncode == 0 and b and b != "HEAD" else None


# ---------- git ----------

_GIT_GLOBAL_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}


def _git(toks: list[str]) -> tuple[list[str], list[str], str | None] | None:
    """(global options, subcommand and args, the -C dir) for a git command."""
    if not toks or Path(toks[0]).name != "git":
        return None
    i, glob, cdir = 1, [], None
    while i < len(toks) and toks[i].startswith("-"):
        t = toks[i]
        glob.append(t)
        if t in _GIT_GLOBAL_VALUE and i + 1 < len(toks):
            glob.append(toks[i + 1])
            if t == "-C":
                cdir = toks[i + 1]
            i += 2
        else:
            i += 1
    return glob, toks[i:], cdir


_PUSH_VALUE = {"-o", "--push-option", "--repo", "--receive-pack", "--exec", "--signed"}


def _dst(ref: str) -> str:
    r = ref
    for pre in ("refs/heads/", "heads/"):
        if r.startswith(pre):
            r = r[len(pre) :]
    m = re.match(r"^refs/remotes/[^/]+/(.+)$", r)
    return m.group(1) if m else r


def _push_problem(args: list[str], base: str, branch: str | None, role: str, ticket_pat: str) -> str | None:
    rest = args[1:]
    pos: list[str] = []
    i = 0
    dry = False
    while i < len(rest):
        a = rest[i]
        if a in ("-n", "--dry-run"):
            dry = True
        elif a in {"-f", "--force", "--mirror", "--all", "--delete", "-d", "--prune"} or a.startswith(("--force-with-lease", "--force-if-includes")):
            return f"`git push {a}` is never allowed (force-push, delete, mirror or push-all)"
        elif re.fullmatch(r"-[a-zA-Z]+", a) and "f" in a[1:]:
            return "`git push -f` (force-push) is never allowed"
        elif re.fullmatch(r"-[a-zA-Z]+", a) and "d" in a[1:]:
            return "`git push -d` deletes a branch, which is never allowed"
        elif a in _PUSH_VALUE and i + 1 < len(rest):
            i += 1
        elif not a.startswith("-"):
            pos.append(a)
        i += 1
    if dry:
        return None
    refspecs = pos[1:]
    dsts: list[str] = []
    for r in refspecs:
        if r.startswith("+"):
            return f"`git push {r}` is a force-push (a leading +), which is never allowed"
        if r.startswith(":"):
            return f"`git push {r}` deletes a branch, which is never allowed"
        d = _dst(r.split(":", 1)[1] if ":" in r else r)
        dsts.append(branch or "?" if d in ("HEAD", "@") else d)
    if not refspecs:
        dsts = [branch or "?"]
    for d in dsts:
        if d == base:
            return f"pushing to the base branch `{base}` is never allowed: open a pull request"
    if role == "ticket":
        for d in dsts:
            if d == "?":
                return "can't tell which branch this push updates (a detached HEAD or another directory); push your ticket branch by name"
            if not fnmatch.fnmatchcase(d, ticket_pat):
                return f"a ticket session may only push branches matching `{ticket_pat}`; this pushes `{d}`"
    return None


_PUSH_SETTINGS = re.compile(r"(?i)^(alias\.|remote\.[^=]*\.(push|pushurl|url)\b|push\.|branch\.[^=]*\.(merge|remote|pushremote)\b|url\.)")


def _git_config_problem(glob: list[str], args: list[str], role: str) -> str | None:
    for j, g in enumerate(glob):
        if g == "-c" and j + 1 < len(glob) and _PUSH_SETTINGS.match(glob[j + 1]):
            return f"`git -c {glob[j + 1]}` can redirect a push; set no aliases or push settings"
    if role == "ticket" and args and args[0] == "config":
        keys = [a for a in args[1:] if not a.startswith("-")]
        if keys and _PUSH_SETTINGS.match(keys[0]) and (len(keys) > 1 or "--unset" in args or "--add" in args):
            return f"`git config {keys[0]}` can redirect a push; ticket sessions don't change it"
    return None


def _switch_problem(args: list[str], ticket_pat: str) -> str | None:
    if not args or args[0] not in ("checkout", "switch"):
        return None
    rest = args[1:]
    for k, a in enumerate(rest):
        if a in ("-b", "-B", "-c", "-C", "--orphan") and k + 1 < len(rest):
            tgt = rest[k + 1]
            if not fnmatch.fnmatchcase(tgt, ticket_pat):
                return f"this is a ticket session by its branch name; stay on a `{ticket_pat}` branch (not `{tgt}`)"
    if args[0] == "switch":
        plain = [a for a in rest if not a.startswith("-")]
        if plain and not fnmatch.fnmatchcase(plain[0], ticket_pat):
            return f"this is a ticket session by its branch name; stay on a `{ticket_pat}` branch (not `{plain[0]}`)"
    return None


# ---------- GitHub API ----------

_TICKET_API_WRITES = [
    r"repos/[^/]+/[^/]+/issues",
    r"repos/[^/]+/[^/]+/issues/\d+",
    r"repos/[^/]+/[^/]+/issues/\d+/(comments|labels|labels/[^/]+|assignees)",
    r"repos/[^/]+/[^/]+/issues/comments/\d+",
    r"repos/[^/]+/[^/]+/pulls",
    r"repos/[^/]+/[^/]+/pulls/\d+",
    r"repos/[^/]+/[^/]+/pulls/\d+/(merge|reviews|comments|requested_reviewers|update-branch)",
    r"repos/[^/]+/[^/]+/pulls/\d+/reviews/\d+(/events)?",
    r"repos/[^/]+/[^/]+/pulls/comments/\d+(/replies)?",
    r"repos/[^/]+/[^/]+/actions/runs/\d+/rerun(-failed-jobs)?",
    r"repos/[^/]+/[^/]+/actions/jobs/\d+/rerun",
]
_DANGEROUS_GQL = re.compile(
    r"\b(updateRef|updateRefs|deleteRef|createRef|createCommitOnBranch|mergeBranch|updateBranchProtectionRule|"
    r"deleteBranchProtectionRule|createBranchProtectionRule|updateRepositoryRuleset|deleteRepositoryRuleset|createRepositoryRuleset)\b"
)
_FIELD_FLAGS = ("-f", "-F", "--field", "--raw-field", "--input")


def _api(toks: list[str]) -> tuple[str, str, str] | None:
    """(method, path, the rest as text) for `gh api`, else None."""
    if len(toks) < 2 or Path(toks[0]).name != "gh" or toks[1] != "api":
        return None
    method, path, has_fields = None, None, False
    i = 2
    while i < len(toks):
        t = toks[i]
        m = re.fullmatch(r"(?:-X|--method)(?:=?(.+))?", t)
        if m:
            if m.group(1):
                method = m.group(1)
                i += 1
            else:
                method = toks[i + 1] if i + 1 < len(toks) else ""
                i += 2
            continue
        if t in _FIELD_FLAGS or t.startswith(tuple(f + "=" for f in _FIELD_FLAGS)):
            has_fields = True
            i += 1 if "=" in t else 2
            continue
        if t in ("-H", "--header", "-q", "--jq", "-t", "--template", "--hostname", "--cache", "-p", "--preview"):
            i += 2
            continue
        if not t.startswith("-") and path is None:
            path = t
        i += 1
    method = (method or ("POST" if has_fields else "GET")).upper()
    return method, (path or "").lstrip("/").split("?", 1)[0], " ".join(toks[2:])


def _api_problem(toks: list[str], profile: Profile, role: str) -> str | None:
    base = profile.base_branch
    name = Path(toks[0]).name if toks else ""
    if name == "gh" and len(toks) > 2 and toks[1] == "pr" and toks[2] == "merge" and "--admin" in toks:
        return "`gh pr merge --admin` bypasses the base branch's required checks; it is never allowed"
    if name == "curl" and re.search(r"api\.github\.com|/api/v3/|/api/graphql", " ".join(toks)):
        joined = f" {' '.join(toks)} "
        writes = re.search(r"\s(-X|--request)\s*=?\s*(POST|PUT|PATCH|DELETE)\b", joined, re.I) or re.search(r"\s(-d|--data[\w-]*|-F|--form|-T|--upload-file)[\s=]", joined)
        if writes and role != "attended":
            return "GitHub writes go through `gh api` or the GitHub MCP tools, not curl"
        return None
    a = _api(toks)
    if not a:
        return None
    method, path, rest = a
    if path == "graphql":
        if re.search(r"\bmutation\b", rest):
            if role == "ticket":
                return "ticket sessions don't run GraphQL mutations; use the REST API or the GitHub MCP tools"
            if _DANGEROUS_GQL.search(rest):
                return "this GraphQL mutation rewrites refs, branches, protection or rulesets, which is never allowed"
        return None
    if method == "GET":
        return None
    if re.search(rf"(^|/)git/refs/heads/{re.escape(base)}$", path) or re.search(r"/branches/[^/]+/protection|/rulesets\b", path):
        return f"rewriting the base branch `{base}`, its protection or rulesets through the API is never allowed"
    if re.search(r"/merges$", path) and (re.search(rf"\bbase={re.escape(base)}\b", rest) or "base=" not in rest):
        return f"merging into `{base}` through the merges API is never allowed: use a pull request"
    if re.search(r"/contents/", path) and (re.search(rf"\bbranch={re.escape(base)}\b", rest) or "branch=" not in rest):
        return f"writing files through the contents API to `{base}` (or the default branch) is never allowed: push a branch"
    if role == "ticket" and not any(re.fullmatch(p, path) for p in _TICKET_API_WRITES):
        return f"ticket sessions may only write issues, comments, labels and pull requests through the API; not `{method} {path}`"
    return None


def _gh_post_text(toks: list[str]) -> str | None:
    if len(toks) >= 2 and Path(toks[0]).name == "gh" and toks[1] in {"issue", "pr", "api", "release", "gist"}:
        return " ".join(toks[2:])
    if toks and Path(toks[0]).name == "curl" and re.search(r"api\.github\.com", " ".join(toks)):
        return " ".join(toks[1:])
    return None


# ---------- deploys ----------


def _deploy_problem(seg: Seg, deploy: list[str], root: Path) -> str | None:
    toks = seg.words
    if not toks:
        return None
    name = Path(toks[0]).name
    run_toks = toks
    if name in {"sh", "bash", "zsh", "dash", "source", "."} and len(toks) > 1:
        run_toks = [t for t in toks[1:] if not t.startswith("-")]
    if not run_toks:
        return None
    for d in deploy:
        dt = d.split()
        if not dt:
            continue
        msg = f"`{d}` is a deploy command: only the owner, or the conductor under a release grant, runs it"
        if "/" in dt[0] or re.search(r"\.(sh|py|js|ts|rb)$", dt[0]):
            if _norm(run_toks[0], root, seg.cwd) == _norm(dt[0], root):
                return msg
        else:
            words = [t for t in toks if not t.startswith("-")]
            if words and Path(words[0]).name == dt[0] and words[1 : len(dt)] == dt[1:]:
                return msg
    return None


# ---------- protected paths from the shell ----------

_RM_LIKE = {"rm", "unlink", "rmdir", "shred", "truncate", "touch", "chmod", "chown", "chgrp", "mkdir"}
_DEST_LAST = {"cp", "install", "rsync", "ln", "mv"}


def _opt_values(toks: list[str], names: tuple[str, ...]) -> list[str]:
    out = []
    for k, t in enumerate(toks):
        for n in names:
            if t == n and k + 1 < len(toks):
                out.append(toks[k + 1])
            elif t.startswith(n + "="):
                out.append(t.split("=", 1)[1])
    return out


def _write_targets(seg: Seg) -> tuple[list[str], list[str]]:
    """(paths written, paths deleted or moved away) by one command."""
    toks = seg.words
    writes = list(seg.redirects)
    removes: list[str] = []
    if not toks:
        return writes, removes
    cmd = Path(toks[0]).name
    operands = [t for t in toks[1:] if not t.startswith("-")]
    if cmd in _RM_LIKE:
        if cmd in {"chmod", "chown", "chgrp"} and operands:
            operands = operands[1:]
        writes += operands
        if cmd in {"rm", "rmdir", "unlink", "shred"} or "-R" in toks or "-r" in toks:
            removes += operands
    elif cmd in _DEST_LAST:
        tdir = _opt_values(toks, ("-t", "--target-directory"))
        if tdir:
            writes += tdir
        elif len(operands) > 1:
            writes.append(operands[-1])
        if cmd == "mv":
            removes += operands if tdir else operands[:-1]
    elif cmd == "tee":
        writes += operands
    elif cmd == "dd":
        writes += [t[3:] for t in toks[1:] if t.startswith("of=")]
    elif cmd == "sed" and any(t == "-i" or t.startswith("-i") or t.startswith("--in-place") for t in toks[1:]):
        writes += operands[1:]
    elif cmd == "perl" and any(re.match(r"^-\w*i", t) for t in toks[1:]):
        writes += operands[1:]
    elif cmd == "git":
        g = _git(toks)
        if g:
            _, args, _ = g
            if args[:1] in (["checkout"], ["restore"], ["rm"], ["mv"], ["clean"]):
                rest = [t for t in args[1:] if not t.startswith("-") and t != "--"]
                writes += rest
                if args[0] in ("rm", "mv", "clean"):
                    removes += rest or ["."]
    elif cmd == "tar" and len(toks) > 1 and re.match(r"^-?[a-zA-Z]*x", toks[1]):
        writes += _opt_values(toks, ("-C", "--directory")) or ["."]
    return writes, removes


def _shell_protected(seg: Seg, profile: Profile, root: Path) -> str | None:
    writes, removes = _write_targets(seg)
    for t in writes:
        rel = _norm(t, root, seg.cwd)
        hit = matches(rel, profile.protected_paths) if rel else None
        if hit:
            return f"writing `{t}` touches a protected path ({hit})"
    for t in removes:
        hit = contains_protected(_norm(t, root, seg.cwd), profile.protected_paths)
        if hit:
            return f"removing or moving `{t}` takes a protected path with it ({hit})"
    toks = seg.words
    if toks and _INTERP.match(Path(toks[0]).name):
        for lit in re.findall(r"""['"]([^'"\s]+)['"]""", _inline_code(toks)):
            if matches(_norm(lit, root, seg.cwd), profile.protected_paths):
                return f"this one-liner names the protected path `{lit}`"
    return None


def _shell_skips(seg: Seg, command: str, profile: Profile, root: Path) -> str | None:
    writes, _ = _write_targets(seg)
    for t in writes:
        rel = _norm(t, root, seg.cwd)
        if rel and matches(rel, profile.test_paths) and _SKIP.search(command):
            return f"this writes a skip or focus marker into the test file `{t}`; skipping or disabling a test is never allowed"
    return None


def check_bash(command: str, profile: Profile, role: str, root: Path, current_branch: str | None, role_from_env: bool = True) -> Decision:
    for seg in segments(command, root):
        toks = seg.words
        g = _git(toks)
        if g is not None:
            glob, args, cdir = g
            p = _git_config_problem(glob, args, role)
            if p:
                return _deny(role, p)
            if args and args[0] == "push":
                branch = _branch_of(root, seg.cwd, cdir) if (cdir or seg.cwd) else current_branch
                p = _push_problem(args, profile.base_branch, branch, role, profile.ticket_branch)
                if p:
                    return _deny(role, p)
            if role == "ticket" and not role_from_env:
                p = _switch_problem(args, profile.ticket_branch)
                if p:
                    return Decision("deny", p)
        p = _api_problem(toks, profile, role)
        if p:
            return _deny(role, p)
        text = _gh_post_text(toks)
        if text and profile.sensitive_patterns:
            for pat in profile.sensitive_patterns:
                if re.search(pat, text):
                    return _deny(role, f"this would post text matching the sensitive-data pattern {pat!r}; refer to things by id")
        if role in ("ticket", "attended"):
            p = _deploy_problem(seg, profile.deploy_commands, root)
            if p:
                return _deny(role, p)
        if role == "ticket":
            p = _shell_protected(seg, profile, root)
            if p:
                return Decision("deny", p + "; ticket sessions don't change protected paths (the owner reviews those)")
            if not profile.allow_new_skips:
                p = _shell_skips(seg, command, profile, root)
                if p:
                    return Decision("deny", p)
    return ALLOW


# ---------- file tools ----------


def _added_skips(old: str, new: str) -> int:
    return len(_SKIP.findall(new or "")) - len(_SKIP.findall(old or ""))


def check_write(tool: str, inp: dict, profile: Profile, role: str, root: Path) -> Decision:
    path = inp.get("file_path") or inp.get("notebook_path") or ""
    rel = _norm(path, root) if path else ""
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
        return Decision("deny", f"this adds a skip or focus marker to the test file `{rel}`; skipping or disabling a test is never allowed: fix the test or the code")
    return ALLOW


# ---------- MCP (GitHub) ----------


def check_mcp(tool: str, inp: dict, profile: Profile, role: str, root: Path) -> Decision:
    m = re.match(r"^mcp__(.+?)__(.+)$", tool)
    if not m:
        return ALLOW
    server, name = m.group(1), m.group(2)
    if "github" not in server.lower():
        return ALLOW
    if name in GITHUB_WRITE_FILES:
        branch = (inp.get("branch") or "").strip().removeprefix("refs/heads/")
        if not branch or branch.casefold() == profile.base_branch.casefold():
            return _deny(role, f"`{name}` would write straight to the base branch `{profile.base_branch}`, which is never allowed: work on a branch and open a pull request")
        if role == "ticket":
            if not fnmatch.fnmatchcase(branch, profile.ticket_branch):
                return Decision("deny", f"a ticket session may only write branches matching `{profile.ticket_branch}`")
            paths = [inp.get("path") or ""] + [f.get("path", "") for f in inp.get("files") or [] if isinstance(f, dict)]
            for pth in paths:
                hit = pth and matches(_norm(pth.lstrip("/"), root), profile.protected_paths)
                if hit:
                    return Decision("deny", f"`{pth}` is a protected path ({hit}); ticket sessions don't change it")
    if role == "ticket" and name in {"create_branch", "update_ref", "delete_branch"}:
        ref = (inp.get("branch") or inp.get("ref") or "").strip().removeprefix("refs/heads/")
        if ref and not fnmatch.fnmatchcase(ref, profile.ticket_branch):
            return Decision("deny", f"a ticket session may only create branches matching `{profile.ticket_branch}`")
    if not name.startswith(_READ_PREFIXES) and profile.sensitive_patterns:
        text = "\n".join(_strings(inp))
        for pat in profile.sensitive_patterns:
            if re.search(pat, text):
                return _deny(
                    role,
                    f"this {name} would post text matching the project's sensitive-data pattern {pat!r} "
                    f"({profile.sensitive_description or 'see profile.md'}); remove it and refer to things by id",
                )
    return ALLOW


def decide(event: dict, profile: Profile, role: str, root: Path, current_branch: str | None, role_from_env: bool = True) -> Decision:
    tool = event.get("tool_name") or ""
    inp = event.get("tool_input") or {}
    if tool == "Bash":
        return check_bash(inp.get("command") or "", profile, role, root, current_branch, role_from_env)
    if tool in WRITE_TOOLS:
        return check_write(tool, inp, profile, role, root)
    if tool.startswith("mcp__"):
        return check_mcp(tool, inp, profile, role, root)
    return ALLOW
