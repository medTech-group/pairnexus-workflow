"""The guard: a PreToolUse hook. Defence in depth, never the only boundary.

The real boundaries are GitHub rulesets on the base branch, a credential-free
cloud environment for ticket sessions, and CODEOWNERS on protected paths
(docs/enforcement.md). The guard catches a well-meaning session's mistakes and
the obvious tricks, says plainly why, and never blocks ordinary work.

**How it reads a command.** Its own shell lexer: quotes, escapes, `$'…'`,
comments, line continuations, fd redirects (`2>&1` is one redirect), glued
operators (`);`, `&&(`), heredocs (the delimiter read whole, quotes removed;
the body kept as data unless a shell reads it, or its delimiter can't be
read), and `$(…)`, backticks, `<(…)` and `>(…)`, which are parsed as commands
of their own, quoted or not, before the command they sit in. It follows the
shell's directory from the hook event's `cwd` through `cd`, `pushd`, `popd`,
subshells (restored at `)`), `env -C` and `git -C`; after `cd -`, `cd ~`,
`cd $X` or a bare `cd` the directory is unknown, and a relative write is then
refused in ticket sessions when it could be a protected path. It looks inside
`sh -c`, `eval`, `script -c`, `find -exec`, heredocs fed to a shell, and
interpreter one-liners, and in ticket and conductor sessions finds `git`,
`git-push` or `gh` anywhere among a command's words (behind `setsid`, `doas`,
`time -p` or any other wrapper).

**Ticket sessions are held to allow-lists** where a deny-list can't keep up:
- `git push` (and `send-pack`, `http-push`, `git-push`) may only update the
  session's own branch (`run.ticket_branch`), never tags; a bare push only when
  its upstream has the branch's own name;
- `gh` may only run the subcommands a ticket needs (pull requests, issues,
  runs, `api`, reads); `gh api` writes may only touch this repo's issues,
  comments, labels and pull requests; GraphQL mutations only
  `enablePullRequestAutoMerge` and `addComment`;
- `git config`, `git -c`, `--config-env` and `GIT_CONFIG*`/`GIT_SSH*`/
  `GIT_DIR`-style variables may not set aliases, push, remote, credential or
  command settings (conductor too);
- a command word may not be a variable, a glob, a brace list or hold `$IFS`.

**Every role** is held to a deny-list: pushing to the base branch, force-pushes,
deleting or mirroring branches, `gh pr merge --admin`, and rewriting the base
branch, its name, the default branch, its protection or rulesets through the
API. Ticket sessions and the conductor are denied; attended sessions are asked.

**Ticket sessions also may not:** run the profile's deploy commands (also fed
to a shell on stdin, through `env -C` or `find -exec`), write protected paths
(Edit/Write, the shell's writers: redirects, `cp`/`mv`/`install`/`rsync`/`ln`,
`rm`, `sed -i`, `tee`, `dd`, `tar`/`unzip` extraction, `git apply`/`patch`,
`git checkout <tree> -- <path>`, through symlinks, `/proc/self/cwd`, globs and
brace lists; `.git/config` and `.git/hooks` count as protected), add skip or
focus markers to tests, use the GitHub MCP tools that trigger workflows, make
repositories or touch secrets, or switch to a branch outside the pattern when
their role comes only from the branch name. A GitHub post (MCP, `gh`, `curl`)
matching the profile's sensitive patterns is refused in every role, heredocs
and body files included.

What it can't see (a script file written then run, a program's own network
calls, variables' values, obfuscation it doesn't recognise) is why the ruleset
and the environment come first.
"""

from __future__ import annotations

import fnmatch
import glob as _glob
import os
import posixpath
import re
import subprocess
import tarfile
import zipfile
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
# GitHub MCP tools a ticket session never needs: they run workflows, make
# repositories or touch secrets. (`delete_file` also falls under the base-branch rule.)
_TICKET_MCP_DENY = {"actions_run_trigger", "create_repository", "fork_repository", "delete_file"}
_TICKET_MCP_DENY_WORDS = ("secret", "workflow_dispatch", "run_workflow")
# Ticket sessions may not change the repository's own config or hooks either.
GIT_INTERNALS = [".git/config", ".git/hooks/**"]


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

_ENV_EXAMPLES = (".example", ".sample", ".template")
# Claude Code keeps its own worktrees here: they are checkouts, not the kit.
_NEVER_PROTECTED = (".claude/worktrees",)


def matches(rel: str, patterns: list[str]) -> str | None:
    r = rel.casefold()
    if any(r == n or r.startswith(n + "/") for n in _NEVER_PROTECTED):
        return None
    for pat in patterns:
        pf = pat.casefold()
        if pf.endswith(".env.*") and r.endswith(_ENV_EXAMPLES) and posixpath.basename(r).startswith(".env."):
            continue
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
    if r.startswith(".."):
        return None
    for pat in patterns:
        head = _literal_dir(pat).casefold()
        if not head:
            continue
        if r == "" or head == r or head.startswith(r + "/"):
            return pat
    return None


def could_match(rel: str, patterns: list[str]) -> str | None:
    """`rel`, taken relative to some directory we can't see, could be (or hold)
    a protected path: it matches a tail of a pattern."""
    if rel.startswith("..") or rel in ("", "."):
        return patterns[0] if patterns else None
    for pat in patterns:
        comps = pat.split("/")
        for k in range(len(comps)):
            tail = "/".join(comps[k:])
            if matches(rel, [tail]) or contains_protected(rel, [tail]):
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


_PROC_CWD = re.compile(r"^/proc/(?:self|thread-self|\$\$|\$BASHPID|\d+)/cwd(?=/|$)")


def _abspath(path: str, cwd: str | None) -> str | None:
    """`path` as an absolute, symlink-resolved path, or None when it depends on
    a directory we can't see."""
    p = path.strip()
    if not p:
        return None
    if p.startswith("~"):
        p = os.path.expanduser(p)
        if p.startswith("~"):
            return None
    m = _PROC_CWD.match(p)
    if m:
        if cwd is None:
            return None
        p = cwd + p[m.end() :]
    if not os.path.isabs(p):
        if cwd is None:
            return None
        p = os.path.join(cwd, p)
    return os.path.realpath(p)


def _rel(abspath: str, root: Path) -> str:
    """Relative to the project root (posix, "" for the root), else absolute."""
    r = os.path.realpath(str(root))
    rel = os.path.relpath(abspath, r)
    if rel == "." or rel == "":
        return ""
    if rel.startswith(".."):
        return abspath
    return rel.replace(os.sep, "/")


def _norm(path: str, root: Path, cwd: str | None = None) -> str:
    """A path relative to the project root, normalised (.., ./, absolute,
    symlinks). With an unknown directory, a relative path is taken from the root."""
    p = path.strip().strip("'\"")
    if not p:
        return ""
    a = _abspath(p, cwd if cwd is not None else os.path.realpath(str(root)))
    if a is None:
        a = _abspath(p, os.path.realpath(str(root)))
    return _rel(a, root) if a else p


def _start_cwd(root: Path, cwd: str | os.PathLike | None) -> str:
    rr = os.path.realpath(str(root))
    if not cwd:
        return rr
    c = str(cwd)
    return os.path.realpath(c if os.path.isabs(c) else os.path.join(rr, c))


# ---------- the shell lexer ----------


class Op(str):
    """An unquoted shell operator; a quoted word that looks like one is a plain str."""


@dataclass
class Heredoc:
    body: str
    quoted: bool


_OPERATORS = sorted(
    [";;&", ";;", ";&", "&&", "||", "|&", "&>>", "&>", ">>", ">|", ">&", "<<<", "<&", "<>", ";", "&", "|", "(", ")", "<", ">"],
    key=len,
    reverse=True,
)
_SEPARATORS = {";", ";;", ";;&", ";&", "&&", "||", "|", "|&", "&", "(", ")"}
_WORD_END = set(" \t\n;&|()<>")


def _ansi_c(body: str) -> str:
    try:
        return body.encode("latin-1", "backslashreplace").decode("unicode_escape", "ignore")
    except Exception:
        return body


def _backtick_end(s: str, i: int) -> int:
    j = i + 1
    while j < len(s):
        if s[j] == "\\":
            j += 2
            continue
        if s[j] == "`":
            return j
        j += 1
    return len(s)


def _read_delim(s: str, i: int) -> tuple[str, bool, int]:
    """A heredoc delimiter word at s[i]: (word without quotes, quoted?, end)."""
    out: list[str] = []
    quoted = False
    n = len(s)
    while i < n and s[i] not in _WORD_END:
        c = s[i]
        if c == "\\" and i + 1 < n:
            out.append(s[i + 1])
            quoted = True
            i += 2
        elif c in "'\"":
            j = s.find(c, i + 1)
            if j < 0:
                return "", True, i
            out.append(s[i + 1 : j])
            quoted = True
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out), quoted, i


def _expansions(text: str) -> list[list]:
    """Command substitutions in text the shell expands (an unquoted heredoc)."""
    out: list[list] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if text.startswith("$(", i):
            toks, j = _lex(text, i + 2, stop_paren=True)
            out.append(toks)
            i = j + 1
            continue
        if c == "`":
            j = _backtick_end(text, i)
            out.append(_lex(text[i + 1 : j].replace("\\`", "`"))[0])
            i = j + 1
            continue
        i += 1
    return out


def _lex(s: str, i: int = 0, stop_paren: bool = False) -> tuple[list, int]:
    """Tokens of a shell command from s[i]: plain words (str), operators (Op)
    and heredocs (Heredoc). Command substitutions are lexed too and put, as a
    subshell, before the command they appear in; the word keeps their text.
    With stop_paren, stops at the `)` closing a `$(`, returning its index."""
    out: list = []
    cmd_start = 0
    word: list[str] = []
    in_word = False
    quoted = False
    pending: list[tuple[str, bool, Heredoc]] = []
    depth = 0
    n = len(s)

    def end_word() -> None:
        nonlocal word, in_word, quoted
        if in_word:
            out.append("".join(word))
        word, in_word, quoted = [], False, False

    def hoist(inner: list) -> None:
        nonlocal cmd_start
        block = [Op("("), *inner, Op(")")]
        out[cmd_start:cmd_start] = block
        cmd_start += len(block)

    def substitution(start: int, inner_from: int) -> int:
        toks, j = _lex(s, inner_from, stop_paren=True)
        word.append(s[start : j + 1])
        hoist(toks)
        return j + 1

    def backtick(start: int) -> int:
        j = _backtick_end(s, start)
        word.append(s[start : j + 1])
        hoist(_lex(s[start + 1 : j].replace("\\`", "`"))[0])
        return j + 1

    def read_heredocs(pos: int) -> int:
        """Bodies of the pending heredocs, from the line after pos."""
        k = pos + 1
        for delim, strip_tabs, hd in pending:
            lines_start = k
            found = False
            while k <= n:
                e = s.find("\n", k)
                e = n if e < 0 else e
                line = s[k:e]
                if (line.lstrip("\t") if strip_tabs else line) == delim:
                    hd.body = s[lines_start:k]
                    k = e + 1 if e < n else n
                    found = True
                    break
                if e >= n:
                    break
                k = e + 1
            if not found:  # no terminator: keep the rest as commands, so it's scanned
                pending.clear()
                return pos + 1
            if not hd.quoted:
                for inner in _expansions(hd.body):
                    hoist(inner)
        pending.clear()
        return k

    while i < n:
        c = s[i]
        if c == "\\":
            if i + 1 < n and s[i + 1] == "\n":
                i += 2
                continue
            if i + 1 < n:
                word.append(s[i + 1])
                in_word = quoted = True
            i += 2
            continue
        if c == "'":
            j = s.find("'", i + 1)
            j = n if j < 0 else j
            word.append(s[i + 1 : j])
            in_word = quoted = True
            i = j + 1
            continue
        if s.startswith("$'", i):
            j = i + 2
            while j < n and s[j] != "'":
                j += 2 if s[j] == "\\" else 1
            word.append(_ansi_c(s[i + 2 : min(j, n)]))
            in_word = quoted = True
            i = j + 1
            continue
        if c == '"' or s.startswith('$"', i):
            i += 1 if c == '"' else 2
            in_word = quoted = True
            while i < n and s[i] != '"':
                ch = s[i]
                if ch == "\\" and i + 1 < n:
                    nx = s[i + 1]
                    if nx == "\n":
                        i += 2
                    elif nx in '$`"\\':
                        word.append(nx)
                        i += 2
                    else:
                        word.append(ch)
                        i += 1
                    continue
                if s.startswith("$(", i):
                    i = substitution(i, i + 2)
                    continue
                if ch == "`":
                    i = backtick(i)
                    continue
                word.append(ch)
                i += 1
            i += 1
            continue
        if s.startswith("$(", i):
            in_word = True
            i = substitution(i, i + 2)
            continue
        if c == "`":
            in_word = True
            i = backtick(i)
            continue
        if c in "<>" and s.startswith("(", i + 1):  # process substitution
            end_word()
            in_word = True
            i = substitution(i, i + 2)
            continue
        if c == "#" and not in_word:
            j = s.find("\n", i)
            i = n if j < 0 else j
            continue
        if c in " \t":
            end_word()
            i += 1
            continue
        if c == "\n":
            end_word()
            if pending:
                i = read_heredocs(i)
            else:
                i += 1
            out.append(Op(";"))
            cmd_start = len(out)
            continue
        if c in ";&|()<>":
            fd = ""
            if c in "<>" and in_word and not quoted and word and "".join(word).isdigit():
                fd = "".join(word)
                word, in_word, quoted = [], False, False
            else:
                end_word()
            if s.startswith("<<", i) and not s.startswith("<<<", i):
                strip_tabs = s.startswith("<<-", i)
                j = i + (3 if strip_tabs else 2)
                while j < n and s[j] in " \t":
                    j += 1
                delim, _q, end = _read_delim(s, j)
                if delim:
                    hd = Heredoc("", _q)
                    out.append(hd)
                    pending.append((delim, strip_tabs, hd))
                    i = end
                    continue
                out.append(Op(fd + "<<"))  # unreadable: the body stays as commands
                i = j
                continue
            op = next(o for o in _OPERATORS if s.startswith(o, i))
            if op == ")" and stop_paren and depth == 0:
                end_word()
                return out, i
            if op == "(":
                depth += 1
            elif op == ")":
                depth -= 1
            out.append(Op(fd + op))
            if op in _SEPARATORS:
                cmd_start = len(out)
            i += len(op)
            continue
        word.append(c)
        in_word = True
        i += 1
    end_word()
    return out, n


def _tokens(command: str) -> list:
    return _lex(command)[0]


# ---------- simple commands ----------


@dataclass
class _Cmd:
    words: list[str] = field(default_factory=list)
    redirects: list[str] = field(default_factory=list)
    stdin: str | None = None
    heredoc: str | None = None


_REDIR = re.compile(r"(\d*)(>>|>\||&>>|&>|>&|<&|<>|<<<|<<|<|>)")


def _simple(toks: list) -> list:
    """Simple commands (_Cmd) and the separators between them (Op)."""
    items: list = []
    cur = _Cmd()

    def flush() -> None:
        nonlocal cur
        if cur.words or cur.redirects or cur.stdin is not None or cur.heredoc is not None:
            items.append(cur)
        cur = _Cmd()

    i = 0
    while i < len(toks):
        t = toks[i]
        if isinstance(t, Heredoc):
            cur.heredoc = (cur.heredoc or "") + t.body
            i += 1
            continue
        if isinstance(t, Op):
            m = _REDIR.fullmatch(t)
            if m:
                op = m.group(2)
                nxt = toks[i + 1] if i + 1 < len(toks) and not isinstance(toks[i + 1], (Op, Heredoc)) else None
                if op == "<<" or nxt is None:
                    i += 1
                    continue
                if op in (">&", "<&") and re.fullmatch(r"\d*-?", nxt):
                    pass  # duplicating or closing a descriptor
                elif op == "<&":
                    pass
                elif op == "<":
                    cur.stdin = nxt
                elif op == "<<<":
                    cur.heredoc = (cur.heredoc or "") + nxt
                else:
                    cur.redirects.append(nxt)
                i += 2
                continue
            flush()
            items.append(t)
            i += 1
            continue
        cur.words.append(t)
        i += 1
    flush()
    return items


@dataclass
class Seg:
    words: list[str]
    redirects: list[str] = field(default_factory=list)
    cwd: str | None = ""  # absolute; None when the shell's directory is unknown
    stdin: str | None = None  # a file read on stdin
    heredoc: str | None = None  # a heredoc or here-string on stdin
    piped: "Seg | None" = None  # the command piping into this one
    assigns: list[str] = field(default_factory=list)  # NAME=value prefixes, env's too


_KEYWORDS = {"{", "}", "!", "if", "then", "else", "elif", "fi", "do", "done", "while", "until", "esac", "coproc"}
_WRAPPERS: dict[str, set[str]] = {
    "sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U", "-T"},
    "doas": {"-u", "-C"},
    "env": {"-u", "-C", "-S", "--unset", "--chdir", "--split-string"},
    "nohup": set(),
    "setsid": set(),
    "exec": {"-a"},
    "command": set(),
    "builtin": set(),
    "nice": {"-n", "--adjustment"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "xargs": {"-I", "-n", "-L", "-P", "-d", "-a", "-E", "-s", "--max-args", "--replace", "--arg-file", "--delimiter"},
    "watch": {"-n", "-d", "--interval"},
    "stdbuf": {"-i", "-o", "-e"},
    "ionice": {"-c", "-n"},
    "chronic": set(),
    "unbuffer": set(),
    "time": {"-f", "-o", "--format", "--output"},
    "flock": {"-w", "--timeout", "-E", "--conflict-exit-code"},
}
_WRAPPER_POSITIONALS = {"flock": 1}  # flock <lockfile> <command>
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\+?=")
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish", "mksh", "ash", "busybox"}
_DASH_C = _SHELLS | {"script", "su", "runuser", "flock"}
_INTERP = re.compile(r"^(python\d?(\.\d+)?|node|nodejs|perl|ruby|deno|bun|php)$")
# Commands that only print or search their arguments, never run them.
_DATA_ONLY = {"echo", "printf", "grep", "egrep", "fgrep", "rg", "ag", "ack", "man", "which", "type", "whereis", "whatis", "apropos", "info"}


def _strip_prefix(toks: list[str]) -> tuple[list[str], list[str], str | None]:
    """(the command's words, NAME=value assignments, a directory from env -C)."""
    assigns: list[str] = []
    chdir: str | None = None
    changed = True
    while toks and changed:
        changed = False
        while toks and (toks[0] in _KEYWORDS or _ASSIGN.match(toks[0])):
            if _ASSIGN.match(toks[0]):
                assigns.append(toks[0])
            toks = toks[1:]
            changed = True
        if toks and toks[0] == "function":
            toks = toks[2:]
            changed = True
        if toks and toks[0] in ("for", "select"):
            toks = toks[toks.index("do") + 1 :] if "do" in toks else []
            changed = True
        if toks and Path(toks[0]).name in _WRAPPERS:
            name = Path(toks[0]).name
            takes = _WRAPPERS[name]
            toks = toks[1:]
            while toks and (toks[0].startswith("-") or re.match(r"^\d+(\.\d+)?[smhd]?$", toks[0]) or _ASSIGN.match(toks[0])):
                t = toks[0]
                toks = toks[1:]
                if _ASSIGN.match(t):
                    assigns.append(t)
                    continue
                if t == "--":
                    break
                val = None
                if t in takes and toks:
                    val, toks = toks[0], toks[1:]
                elif "=" in t and t.split("=", 1)[0] in takes:
                    val = t.split("=", 1)[1]
                elif name == "env" and re.fullmatch(r"-C.+", t):
                    val, t = t[2:], "-C"
                elif name == "env" and re.fullmatch(r"-S.+", t):
                    val, t = t[2:], "-S"
                key = t.split("=", 1)[0]
                if val is not None and ((name == "env" and key in ("-C", "--chdir")) or (name == "sudo" and key == "-D")):
                    chdir = val if chdir is None or os.path.isabs(val) else posixpath.join(chdir, val)
                if val is not None and name == "env" and key in ("-S", "--split-string"):
                    toks = val.split() + toks
            for _ in range(_WRAPPER_POSITIONALS.get(name, 0)):
                if toks and not toks[0].startswith("-"):
                    toks = toks[1:]
            changed = True
    return toks, assigns, chdir


def _shell_c(toks: list[str]) -> str | None:
    for i, t in enumerate(toks[1:], 1):
        if (re.fullmatch(r"-[a-zA-Z]*c[a-zA-Z]*", t) or t == "--command") and i + 1 < len(toks):
            return toks[i + 1]
    return None


def _shell_reads_stdin(toks: list[str]) -> bool:
    """`bash`, `bash -s …`, `sh -e`: a shell with no script file or -c."""
    if _shell_c(toks) is not None:
        return False
    rest = toks[1:]
    k = 0
    while k < len(rest):
        t = rest[k]
        if t in ("-o", "+o", "-O", "+O", "--rcfile", "--init-file"):
            k += 2
            continue
        if t == "-s" or (re.fullmatch(r"-[a-zA-Z]+", t) and "s" in t):
            return True
        if t.startswith(("-", "+")):
            k += 1
            continue
        return False
    return True


def _inline_code(toks: list[str]) -> str:
    return next((toks[i + 1] for i, t in enumerate(toks[:-1]) if t in {"-c", "-e", "-E", "--eval", "-p", "-r"}), "")


_TOPLEVEL = re.compile(r"^(\$\(git rev-parse --show-toplevel\)|`git rev-parse --show-toplevel`|\$\{?CLAUDE_PROJECT_DIR\}?)/?$")


def _cd_target(args: list[str], root: Path, cwd: str | None) -> str | None:
    args = [a for a in args if a not in ("-P", "-L", "-e", "-@", "--")]
    if not args:
        return None  # $HOME
    a = args[0]
    if _TOPLEVEL.match(a):
        return os.path.realpath(str(root))
    m = re.match(r"^(\$\(git rev-parse --show-toplevel\)|\$\{?CLAUDE_PROJECT_DIR\}?)/(.+)$", a)
    if m:
        return os.path.realpath(os.path.join(str(root), m.group(2)))
    if a == "-" or a.startswith("~") or "$" in a or "`" in a or re.search(r"[*?\[{]", a):
        return None
    return _abspath(a, cwd)


def segments(command: str, root: Path, cwd: str | None = "", depth: int = 0) -> list[Seg]:
    """Each simple command with the shell's directory tracked, recursing into
    `sh -c`, `eval`, shells fed a heredoc, `find -exec`, interpreter one-liners
    that hold git/gh commands, and command words holding a whole command."""
    if cwd == "":
        cwd = os.path.realpath(str(root))
    return _segments_of(_tokens(command), root, cwd, depth)


def _segments_of(toks: list, root: Path, cwd: str | None, depth: int) -> list[Seg]:
    segs: list[Seg] = []
    saved: list[str | None] = []
    dirs: list[str | None] = []
    prev: Seg | None = None
    piped = False
    case_pattern = False  # between `case … in` / `;;` and the pattern's `)`
    for item in _simple(toks):
        if isinstance(item, Op):
            if case_pattern and item == ")":
                case_pattern = False
            elif case_pattern and item == "(":
                pass
            elif item == "(":
                saved.append(cwd)
            elif item == ")":
                if saved:
                    cwd = saved.pop()
            elif item in (";;", ";&", ";;&"):
                case_pattern = True
            piped = item in ("|", "|&")
            if not piped:
                prev = None
            continue
        words = item.words
        if case_pattern:
            if "esac" in words:
                case_pattern = False
            continue
        toks2, assigns, chdir = _strip_prefix(words)
        if toks2 and toks2[0] == "case":
            case_pattern = True
            continue
        if toks2 and toks2[0] in ("cd", "pushd", "popd", "chdir"):
            if toks2[0] == "popd":
                cwd = dirs.pop() if dirs else None
            else:
                if toks2[0] == "pushd":
                    dirs.append(cwd)
                cwd = _cd_target(toks2[1:], root, cwd)
            seg = Seg(toks2, item.redirects, cwd, item.stdin, item.heredoc, prev if piped else None, assigns)
            segs.append(seg)
            prev = seg
            continue
        seg_cwd = cwd
        if chdir is not None:
            seg_cwd = _cd_target([chdir], root, cwd)
        if not toks2 and not item.redirects and not assigns:
            continue
        seg = Seg(toks2, item.redirects, seg_cwd, item.stdin, item.heredoc, prev if piped else None, assigns)
        segs.append(seg)
        prev = seg
        segs += _nested(seg, root, depth)
    return segs


def _nested(seg: Seg, root: Path, depth: int) -> list[Seg]:
    toks = seg.words
    if not toks or depth >= 4:
        return []
    out: list[Seg] = []
    name = Path(toks[0]).name
    if re.search(r"\s", toks[0]):  # a whole command as one word (`watch 'git push'`)
        out += segments(toks[0], root, seg.cwd, depth + 1)
    if name in _DASH_C:
        inner = _shell_c(toks)
        if inner is not None:
            out += segments(inner, root, seg.cwd, depth + 1)
    if name in _SHELLS and seg.heredoc and _shell_reads_stdin(toks):
        out += segments(seg.heredoc, root, seg.cwd, depth + 1)
    if name == "eval" and len(toks) > 1:
        out += segments(" ".join(toks[1:]), root, seg.cwd, depth + 1)
    if _INTERP.match(name):
        for lit in re.findall(r"""['"]([^'"]*\b(?:git|gh)\b[^'"]*)['"]""", _inline_code(toks)):
            out += segments(lit, root, seg.cwd, depth + 1)
    if name == "find":
        k = 0
        while k < len(toks):
            if toks[k] in ("-exec", "-execdir", "-ok", "-okdir"):
                j = k + 1
                while j < len(toks) and toks[j] not in (";", "+"):
                    j += 1
                sub, assigns, chdir = _strip_prefix(toks[k + 1 : j])
                if sub:
                    s2 = Seg(sub, [], seg.cwd, assigns=assigns)
                    out.append(s2)
                    out += _nested(s2, root, depth + 1)
                k = j
            k += 1
    return out


def _git_dir_of(root: Path, cwd: str | None, explicit_dir: str | None) -> str | None:
    if explicit_dir:
        return _abspath(explicit_dir, cwd)
    return cwd


def _git_out(d: str | None, *args: str) -> str | None:
    if not d:
        return None
    try:
        out = subprocess.run(["git", *args], cwd=d, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _branch_of(d: str | None) -> str | None:
    b = _git_out(d, "rev-parse", "--abbrev-ref", "HEAD")
    return b if b and b != "HEAD" else None


def _upstream_branch(d: str | None) -> str | None:
    """The branch name the upstream has on its remote ("claude/build-1"), or None when unset."""
    full = _git_out(d, "rev-parse", "--symbolic-full-name", "@{u}")
    if not full:
        return None
    remote = _git_out(d, "config", "--get", f"branch.{_branch_of(d) or ''}.remote") or ""
    m = re.match(r"^refs/remotes/(.+)$", full)
    if m:
        rest = m.group(1)
        if remote and rest.startswith(remote + "/"):
            return rest[len(remote) + 1 :]
        return rest.split("/", 1)[1] if "/" in rest else rest
    return full.removeprefix("refs/heads/")


# ---------- git ----------

_GIT_GLOBAL_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env", "--super-prefix", "--list-cmds"}
_GIT_DASHED = {"git-push": "push", "git-send-pack": "send-pack", "git-http-push": "http-push", "git-config": "config"}


def _is_vcs_word(t: str) -> bool:
    n = Path(t).name
    return n in ("git", "gh") or n in _GIT_DASHED


def _vcs_index(toks: list[str], role: str) -> int | None:
    """Where the git/gh command starts: the command word, or in ticket and
    conductor sessions any word (behind an unknown wrapper)."""
    if not toks:
        return None
    if _is_vcs_word(toks[0]):
        return 0
    if role in ("ticket", "conductor") and Path(toks[0]).name not in _DATA_ONLY:
        for k, t in enumerate(toks[1:], 1):
            if _is_vcs_word(t):
                return k
    return None


def _git(toks: list[str]) -> tuple[list[str], list[str], str | None] | None:
    """(global options, subcommand and args, the -C dir) for a git command."""
    if not toks:
        return None
    name = Path(toks[0]).name
    if name in _GIT_DASHED:
        return [], [_GIT_DASHED[name], *toks[1:]], None
    if name != "git":
        return None
    i, glob, cdir = 1, [], None
    while i < len(toks) and toks[i].startswith("-"):
        t = toks[i]
        glob.append(t)
        if t in _GIT_GLOBAL_VALUE and i + 1 < len(toks):
            glob.append(toks[i + 1])
            if t == "-C":
                cdir = toks[i + 1] if cdir is None or os.path.isabs(toks[i + 1]) else posixpath.join(cdir, toks[i + 1])
            i += 2
        else:
            i += 1
    return glob, toks[i:], cdir


# git push's long options: name -> takes a separate value. Each also has a
# `--no-` form. Unique prefixes are accepted, as git does.
_PUSH_LONG: dict[str, bool] = {
    "all": False, "branches": False, "mirror": False, "prune": False, "delete": False, "tags": False,
    "follow-tags": False, "dry-run": False, "porcelain": False, "force": False, "force-with-lease": False,
    "force-if-includes": False, "atomic": False, "signed": False, "push-option": True, "receive-pack": True,
    "exec": True, "repo": True, "set-upstream": False, "thin": False, "quiet": False, "verbose": False,
    "progress": False, "recurse-submodules": False, "verify": False, "ipv4": False, "ipv6": False,
    "stdin": False, "remote": True, "helper-status": False,
}  # fmt: skip
_PUSH_LONGS = sorted(set(_PUSH_LONG) | {"no-" + k for k in _PUSH_LONG})
_PUSH_ALWAYS_DENY = {"all", "branches", "mirror", "prune", "delete", "force", "force-with-lease", "force-if-includes"}
_UNSAFE_REF = re.compile(r"[$`*?\[{]|@")


def _expand_long(opt: str) -> tuple[str | None, list[str]]:
    """`--mirr` -> ("mirror", []); an ambiguous prefix -> (None, candidates)."""
    name = opt[2:].split("=", 1)[0]
    if name in _PUSH_LONG or name in _PUSH_LONGS:
        return name, []
    cands = [o for o in _PUSH_LONGS if o.startswith(name)] if name else []
    if len(cands) == 1:
        return cands[0], []
    return None, cands


def _dst(ref: str) -> str:
    r = ref
    for pre in ("refs/heads/", "heads/"):
        if r.startswith(pre):
            r = r[len(pre) :]
    m = re.match(r"^refs/remotes/[^/]+/(.+)$", r)
    return m.group(1) if m else r


def _push_problem(args: list[str], base: str, branch: str | None, role: str, ticket_pat: str, upstream=None) -> str | None:
    """`args` starts with push, send-pack or http-push. `upstream` is called for
    a push without refspecs and returns the upstream's branch name or None."""
    kind = args[0]
    rest = args[1:]
    pos: list[str] = []
    i = 0
    dry = False
    tags = False
    only_pos = False
    while i < len(rest):
        a = rest[i]
        if only_pos or not a.startswith("-") or a == "-":
            pos.append(a)
        elif a == "--":
            only_pos = True
        elif a.startswith("--"):
            name, cands = _expand_long(a)
            if name is None:
                bad = [c for c in cands if c in _PUSH_ALWAYS_DENY or c in ("tags", "follow-tags", "stdin")]
                if bad:
                    return f"`git {kind} {a}` is ambiguous and could mean --{bad[0]}; spell the option out"
            elif name in _PUSH_ALWAYS_DENY:
                return f"`git {kind} --{name}` is never allowed (force-push, delete, mirror or push-all)"
            elif name in ("tags", "follow-tags"):
                tags = True
            elif name == "stdin":
                return f"`git {kind} --stdin` reads its refs where the guard can't see them; name the branch"
            elif name == "dry-run":
                dry = True
            elif name == "no-dry-run":
                dry = False
            elif _PUSH_LONG.get(name) and "=" not in a:
                i += 1  # its value (git still takes the first positional as the remote)
        else:
            cluster = a[1:]
            for k, ch in enumerate(cluster):
                if ch == "f":
                    return f"`git {kind} -f` (force-push) is never allowed"
                if ch in "dD":
                    return f"`git {kind} -{ch}` deletes a branch, which is never allowed"
                if ch == "n":
                    dry = True
                if ch == "o":
                    if k == len(cluster) - 1:
                        i += 1
                    break
        i += 1
    if dry:
        return None
    if role == "ticket" and tags:
        return "ticket sessions don't push tags (`--tags`, `--follow-tags`); push your branch by name"
    refspecs = pos[1:]
    dsts: list[str] = []
    for r in refspecs:
        if r.startswith("+"):
            return f"`git push {r}` is a force-push (a leading +), which is never allowed"
        if r.startswith(":"):
            return f"`git push {r}` deletes a branch (or pushes every matching one), which is never allowed"
        raw_dst = r.split(":", 1)[1] if ":" in r else r
        if role != "attended" and raw_dst not in ("@", "HEAD") and _UNSAFE_REF.search(raw_dst):
            return f"can't tell which branch `{raw_dst}` is (a variable, `@`, a glob or a brace list); push your branch by name"
        if role == "ticket" and (raw_dst.startswith(("refs/tags/", "tags/")) or r.startswith("refs/tags/")):
            return f"ticket sessions don't push tags (`{r}`); push your branch by name"
        d = _dst(raw_dst)
        dsts.append((branch or "?") if d in ("HEAD", "@") else d)
    if not refspecs:
        if kind != "push":
            return f"`git {kind}` without refs pushes every matching branch; name the branch"
        dsts = [branch or "?"]
        up = upstream() if upstream else None
        if up and up == base:
            return f"this branch's upstream is the base branch `{base}`, so a bare push would update it; push the branch by name: `git push origin {branch or '<branch>'}`"
        if role == "ticket" and up and branch and up != branch:
            return f"this branch's upstream is `{up}`, not `{branch}`, so a bare push would update another branch; push it by name: `git push origin {branch}`"
    for d in dsts:
        if d == base:
            return f"pushing to the base branch `{base}` is never allowed: open a pull request"
    if role == "ticket":
        own = branch if branch and fnmatch.fnmatchcase(branch, ticket_pat) else None
        for d in dsts:
            if d == "?":
                return "can't tell which branch this push updates (a detached HEAD or another directory); push your ticket branch by name"
            if own and d != own:
                return f"a ticket session may only push its own branch `{own}`; this pushes `{d}`"
            if not fnmatch.fnmatchcase(d, ticket_pat):
                return f"a ticket session may only push branches matching `{ticket_pat}`; this pushes `{d}`"
    return None


_PUSH_SETTINGS = re.compile(r"(?i)^(alias\.|remote\.[^=]*\.(push|pushurl|url)\b|push\.|branch\.[^=]*\.(merge|remote|pushremote)\b|url\.)")
_INJECT_KEYS = re.compile(
    r"(?i)^(alias\.|remote\..*\.(push|pushurl|url)\b|push\.|branch\..*\.(merge|remote|pushremote)\b|url\.|"
    r"core\.(fsmonitor|sshcommand|hookspath|pager|editor|askpass|gitproxy)\b|credential\.|include\.|includeif\.)"
)
_INJECT_ENV = re.compile(r"^(GIT_CONFIG\w*|GIT_SSH\w*|GIT_EXEC_PATH|GIT_DIR|GIT_WORK_TREE)\+?=")
_CONFIG_VALUE_OPTS = {"-f", "--file", "--blob", "--type", "--default", "--comment", "--value", "-t"}
_CONFIG_WRITE_OPTS = {"--unset", "--unset-all", "--add", "--replace-all", "--rename-section", "--remove-section", "--edit", "-e"}


def _env_problem(seg: Seg, role: str) -> str | None:
    if role not in ("ticket", "conductor"):
        return None
    names = list(seg.assigns)
    if seg.words and seg.words[0] in ("export", "declare", "typeset", "local", "readonly"):
        names += [w for w in seg.words[1:] if not w.startswith("-")]
    for a in names:
        m = _INJECT_ENV.match(a) or re.fullmatch(r"(GIT_CONFIG\w*|GIT_SSH\w*|GIT_EXEC_PATH|GIT_DIR|GIT_WORK_TREE)", a)
        if m:
            return f"setting `{a.split('=', 1)[0]}` can point git at other config, programs or repositories; it's not allowed in {role} sessions"
    return None


def _git_config_problem(glob: list[str], args: list[str], role: str) -> str | None:
    firm = role in ("ticket", "conductor")
    for j, g in enumerate(glob):
        if g == "-c" and j + 1 < len(glob):
            key = glob[j + 1]
            if (_INJECT_KEYS if firm else _PUSH_SETTINGS).match(key):
                return f"`git -c {key}` can redirect a push or run a program; set no aliases, push, remote, credential or command settings"
        if firm and (g == "--config-env" or g.startswith("--config-env=")):
            return "`git --config-env` sets config from the environment, which isn't allowed here"
        if firm and g.startswith("--exec-path="):
            return "`git --exec-path=…` runs git's programs from elsewhere, which isn't allowed here"
    if not firm or not args:
        return None
    if args[0] == "remote" and len(args) > 1 and args[1] == "set-url" and role == "ticket":
        return "ticket sessions don't change where a remote points (`git remote set-url`)"
    if args[0] != "config":
        return None
    rest = args[1:]
    positional: list[str] = []
    write = False
    i = 0
    while i < len(rest):
        t = rest[i]
        if t in _CONFIG_VALUE_OPTS:
            i += 2
            continue
        if t in _CONFIG_WRITE_OPTS:
            write = True
        elif not t.startswith("-"):
            positional.append(t)
        i += 1
    if positional and positional[0] in ("set", "unset", "rename-section", "remove-section", "edit"):
        write = True
        if positional[0] == "edit":
            positional = []
        else:
            positional = positional[1:]
    elif positional and positional[0] in ("get", "list", "get-regexp", "get-urlmatch"):
        positional = []
    elif len(positional) >= 2:
        write = True
    if not write:
        return None
    if not positional:
        return "`git config --edit` changes the config by hand, which isn't allowed here"
    key = positional[0]
    if _INJECT_KEYS.match(key) or _INJECT_KEYS.match(key + "."):
        return f"`git config {key}` can redirect a push or run a program; {role} sessions don't change it"
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


# ---------- GitHub CLI and API ----------

# `gh` subcommands a ticket session may run (None: any).
_GH_TICKET: dict[str, set[str] | None] = {
    "pr": {"create", "new", "edit", "comment", "view", "checks", "list", "ls", "diff", "ready", "merge", "status"},
    "issue": {"view", "comment", "edit", "list", "ls", "create", "new", "status"},
    "run": {"view", "list", "ls", "rerun", "watch"},
    "api": None,
    "repo": {"view"},
    "auth": {"status"},
    "label": {"list", "ls"},
    "search": None,
    "help": None,
    "version": None,
}
_GH_VALUE_FLAGS = {"-R", "--repo", "--hostname"}
_GH_READS = {"view", "list", "ls", "status", "checks", "diff", "download", "watch", None}

_TICKET_API_WRITES = [
    r"issues",
    r"issues/\d+",
    r"issues/\d+/(comments|labels|labels/[^/]+|assignees)",
    r"issues/comments/\d+",
    r"pulls",
    r"pulls/\d+",
    r"pulls/\d+/(merge|reviews|comments|requested_reviewers|update-branch)",
    r"pulls/\d+/reviews/\d+(/events)?",
    r"pulls/comments/\d+(/replies)?",
    r"actions/runs/\d+/rerun(-failed-jobs)?",
    r"actions/jobs/\d+/rerun",
]
_DANGEROUS_GQL = re.compile(
    r"\b(updateRef|updateRefs|deleteRef|createRef|createCommitOnBranch|mergeBranch|updateBranchProtectionRule|"
    r"deleteBranchProtectionRule|createBranchProtectionRule|updateRepositoryRuleset|deleteRepositoryRuleset|createRepositoryRuleset|"
    r"updateRepository|renameRef)\b"
)
_TICKET_GQL_MUTATIONS = {"enablePullRequestAutoMerge", "addComment"}
_FIELD_FLAGS = ("-f", "-F", "--field", "--raw-field")


def _gh_group(toks: list[str]) -> tuple[str | None, str | None]:
    """(group, subcommand) of a gh command: ("pr", "merge")."""
    words: list[str] = []
    i = 1
    while i < len(toks) and len(words) < 2:
        t = toks[i]
        if t in _GH_VALUE_FLAGS:
            i += 2
            continue
        if not t.startswith("-"):
            words.append(t)
        elif t == "--version" and not words:
            return "version", None
        elif t in ("--help", "-h"):
            break
        i += 1
    return (words[0] if words else None), (words[1] if len(words) > 1 else None)


@dataclass
class _ApiCall:
    method: str
    path: str
    rest: str
    fields: list[str]
    files: list[str]  # @file fields and --input
    stdin: bool


def _api(toks: list[str]) -> _ApiCall | None:
    """`gh api`'s method, path, fields and files, else None."""
    if len(toks) < 2 or Path(toks[0]).name != "gh":
        return None
    group, _ = _gh_group(toks)
    if group != "api":
        return None
    start = toks.index("api") + 1
    method, path = None, None
    fields: list[str] = []
    files: list[str] = []
    stdin = False
    i = start
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
        val = None
        if t in _FIELD_FLAGS:
            val = toks[i + 1] if i + 1 < len(toks) else ""
            i += 2
        elif t.startswith(("--field=", "--raw-field=")):
            val = t.split("=", 1)[1]
            i += 1
        elif re.fullmatch(r"-[fF].+", t):
            val = t[2:]
            i += 1
        if val is not None:
            fields.append(val)
            if (t.startswith("-F") or t.startswith("--field")) and "=@" in val:
                f = val.split("=@", 1)[1]
                if f == "-":
                    stdin = True
                else:
                    files.append(f)
            continue
        if t == "--input" or t.startswith("--input="):
            f = t.split("=", 1)[1] if "=" in t else (toks[i + 1] if i + 1 < len(toks) else "")
            i += 1 if "=" in t else 2
            if f == "-":
                stdin = True
            elif f:
                files.append(f)
            continue
        if t in ("-H", "--header", "-q", "--jq", "-t", "--template", "--hostname", "--cache", "-p", "--preview"):
            i += 2
            continue
        if not t.startswith("-") and path is None:
            path = t
        i += 1
    has_body = bool(fields) or bool(files) or stdin
    method = (method or ("POST" if has_body else "GET")).upper()
    p = re.sub(r"^https?://[^/]+/(api/v3/)?", "", path or "").lstrip("/").split("?", 1)[0].rstrip("/")
    return _ApiCall(method, p, " ".join(toks[start:]), fields, files, stdin)


def _field(call: _ApiCall, name: str) -> str | None:
    for f in call.fields:
        if f.split("=", 1)[0] == name:
            return f.split("=", 1)[1] if "=" in f else ""
    return None


def _read_text(path: str, cwd: str | None, limit: int = 1_000_000) -> str | None:
    a = _abspath(path, cwd)
    if not a:
        return None
    try:
        with open(a, "rb") as fh:
            return fh.read(limit).decode("utf-8", "replace")
    except OSError:
        return None


def _mutation_fields(text: str) -> list[str] | None:
    """The top-level fields of each GraphQL mutation in text; None if unreadable."""
    t = re.sub(r'"""(?:.|\n)*?"""|"(?:[^"\\]|\\.)*"', '""', text)
    out: list[str] = []
    for m in re.finditer(r"\bmutation\b", t):
        i, n = m.end(), len(t)
        paren = 0
        while i < n and not (t[i] == "{" and paren == 0):
            paren += {"(": 1, ")": -1}.get(t[i], 0)
            i += 1
        if i >= n:
            return None
        i += 1
        depth = 1
        while i < n and depth > 0:
            c = t[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif c == "(":
                p = 1
                i += 1
                while i < n and p:
                    p += {"(": 1, ")": -1}.get(t[i], 0)
                    i += 1
                continue
            elif depth == 1 and (c.isalpha() or c == "_"):
                mm = re.match(r"[A-Za-z_]\w*", t[i:])
                ident = mm.group(0)
                i += len(ident)
                rest = t[i:].lstrip()
                if rest.startswith(":"):
                    i = n - len(rest) + 1
                    mm = re.match(r"\s*([A-Za-z_]\w*)", t[i:])
                    if not mm:
                        return None
                    ident = mm.group(1)
                    i += mm.end()
                out.append(ident)
                continue
            i += 1
    return out


def _gh_problem(toks: list[str], profile: Profile, role: str, cwd: str | None, raw: str) -> str | None:
    """Problems with a `gh` command (toks start at the gh word)."""
    group, sub = _gh_group(toks)
    if group == "pr" and sub == "merge" and any(t == "--admin" or t.startswith("--admin=") for t in toks):
        return "`gh pr merge --admin` bypasses the base branch's required checks; it is never allowed"
    if role == "ticket" and group is not None and not group.startswith("-"):
        allowed = _GH_TICKET.get(group, set())
        if group not in _GH_TICKET or (allowed is not None and sub not in allowed and sub is not None):
            what = f"gh {group}" + (f" {sub}" if sub else "")
            return f"`{what}` isn't something a ticket session runs; ticket sessions use gh only for pull requests, issues, runs, `gh api` and reads"
    return _api_problem(toks, profile, role, cwd, raw)


def _api_problem(toks: list[str], profile: Profile, role: str, cwd: str | None = None, raw: str = "") -> str | None:
    base = profile.base_branch
    name = Path(toks[0]).name if toks else ""
    if name == "curl" and re.search(r"api\.github\.com|/api/v3/|/api/graphql", " ".join(toks)):
        joined = f" {' '.join(toks)} "
        writes = re.search(r"\s(-X|--request)\s*=?\s*(POST|PUT|PATCH|DELETE)\b", joined, re.I) or re.search(r"\s(-d|--data[\w-]*|-F|--form|-T|--upload-file|--json)[\s=]", joined)
        if writes and role != "attended":
            return "GitHub writes go through `gh api` or the GitHub MCP tools, not curl"
        return None
    call = _api(toks)
    if not call:
        return None
    path = call.path
    if path == "graphql":
        from_file = bool(call.files) or call.stdin
        if role == "ticket":
            if from_file:
                return "a GraphQL call read from a file (`@file`, `--input`) counts as a mutation, which ticket sessions don't run; pass the query inline"
            if re.search(r"\bmutation\b", call.rest):
                names = _mutation_fields(call.rest)
                if names is None or not names or any(n not in _TICKET_GQL_MUTATIONS for n in names):
                    return "ticket sessions run only the `enablePullRequestAutoMerge` and `addComment` GraphQL mutations; use the REST API or the GitHub MCP tools"
            return None
        text = call.rest
        for f in call.files:
            text += "\n" + (_read_text(f, cwd) or "")
        if call.stdin:
            text += "\n" + raw
        if _DANGEROUS_GQL.search(text):
            return "this GraphQL mutation rewrites refs, branches, protection or rulesets, which is never allowed"
        return None
    if call.method == "GET":
        return None
    if re.search(rf"(^|/)git/refs/heads/{re.escape(base)}$", path) or re.search(r"/branches/[^/]+/protection|/rulesets\b", path):
        return f"rewriting the base branch `{base}`, its protection or rulesets through the API is never allowed"
    if re.search(rf"(^|/)branches/{re.escape(base)}/rename$", path):
        return f"renaming the base branch `{base}` through the API is never allowed"
    if re.fullmatch(r"repos/[^/]+/[^/]+", path) and (_field(call, "default_branch") is not None or "default_branch" in call.rest):
        return "changing the repository's default branch through the API is never allowed"
    for key in ("base", "branch"):
        v = _field(call, key)
        if role != "attended" and v is not None and _UNSAFE_REF.search(v):
            return f"can't tell which branch `{key}={v}` is (a variable, `@`, a glob or a brace list); name it"
    if re.search(r"/merges$", path):
        v = _field(call, "base")
        if v is None or v == base:
            return f"merging into `{base}` through the merges API is never allowed: use a pull request"
    if re.search(r"/contents/", path):
        v = _field(call, "branch")
        if v is None or v == base:
            return f"writing files through the contents API to `{base}` (or the default branch) is never allowed: push a branch"
    if role == "ticket":
        repo = re.escape(profile.repo)
        prefix = rf"repos/(?:{repo}|\{{owner\}}/\{{repo\}})/"
        if not re.match(prefix, path, re.I):
            return f"ticket sessions write through the API only to this repository (`{profile.repo}`); not `{call.method} {path}`"
        if not any(re.fullmatch(prefix + p, path, re.I) for p in _TICKET_API_WRITES):
            return f"ticket sessions may only write issues, comments, labels and pull requests through the API; not `{call.method} {path}`"
    return None


def _post_kind(toks: list[str]) -> str | None:
    """'gh' or 'curl' when this command posts to GitHub."""
    if len(toks) >= 2 and Path(toks[0]).name == "gh":
        group, sub = _gh_group(toks)
        if group == "api":
            call = _api(toks)
            return "gh" if call and (call.method != "GET" or call.path == "graphql") else None
        if group in {"issue", "pr", "release", "gist"} and sub not in _GH_READS:
            return "gh"
    if toks and Path(toks[0]).name == "curl" and re.search(r"api\.github\.com|/api/v3/|/api/graphql", " ".join(toks)):
        return "curl"
    return None


def _body_files(toks: list[str]) -> list[str]:
    """Files a gh/curl post reads its text from (`-` is the command's own stdin)."""
    out: list[str] = []
    for k, t in enumerate(toks):
        nxt = toks[k + 1] if k + 1 < len(toks) else ""
        if t in ("--body-file", "--input", "-F", "--field", "--notes-file", "-d", "--data", "--data-binary", "--data-raw", "-T", "--upload-file"):
            if t in ("-F", "--field", "-d", "--data", "--data-binary") and "=@" in nxt:
                out.append(nxt.split("=@", 1)[1])
            elif t in ("-d", "--data", "--data-binary") and nxt.startswith("@"):
                out.append(nxt[1:])
            elif t in ("--body-file", "--input", "--notes-file", "-T", "--upload-file") or (t == "-F" and "=" not in nxt):
                out.append(nxt)
        elif t.startswith(("--body-file=", "--input=", "--notes-file=")):
            out.append(t.split("=", 1)[1])
        elif re.fullmatch(r"-F.+=@.+", t):
            out.append(t.split("=@", 1)[1])
    return [f for f in out if f and f != "-"]


# ---------- deploys ----------


def _deploy_problem(seg: Seg, deploy: list[str], root: Path) -> str | None:
    toks = seg.words
    if not toks:
        return None
    name = Path(toks[0]).name
    run_toks = toks
    if name in _SHELLS | {"source", "."} and len(toks) > 1:
        run_toks = [t for t in toks[1:] if not t.startswith("-")]
    paths = [d for d in deploy if d.split() and ("/" in d.split()[0] or re.search(r"\.(sh|py|js|ts|rb)$", d.split()[0]))]
    deploy_paths = [_norm(d.split()[0], root) for d in paths]
    if name in _SHELLS and _shell_reads_stdin(toks):
        fed = [seg.stdin] if seg.stdin else (seg.piped.words if seg.piped else [])
        for w in fed:
            n = _norm(w, root, seg.piped.cwd if seg.piped and not seg.stdin else seg.cwd)
            if n in deploy_paths:
                d = paths[deploy_paths.index(n)]
                return f"`{d}` is a deploy command (fed to a shell here): only the owner, or the conductor under a release grant, runs it"
    if not run_toks:
        return None
    for d in deploy:
        dt = d.split()
        if not dt:
            continue
        msg = f"`{d}` is a deploy command: only the owner, or the conductor under a release grant, runs it"
        if d in paths:
            if _norm(run_toks[0], root, seg.cwd) == _norm(dt[0], root):
                return msg
        else:
            words = [t for t in toks if not t.startswith("-")]
            if words and Path(words[0]).name == dt[0] and words[1 : len(dt)] == dt[1:]:
                return msg
    return None


# ---------- protected paths from the shell ----------

_RM_LIKE = {"rm", "unlink", "rmdir", "shred"}
_TOUCH_LIKE = {"truncate", "touch", "chmod", "chown", "chgrp", "mkdir", "chattr", "setfacl"}
_DEST_LAST = {"cp", "install", "rsync", "ln", "mv"}
_GLOB_CHARS = re.compile(r"[*?\[]")


@dataclass
class _Targets:
    files: list[str] = field(default_factory=list)  # written: matched against the patterns
    trees: list[str] = field(default_factory=list)  # written into, removed or moved: checked for protected paths inside
    links: list[str] = field(default_factory=list)  # linked to (ln's sources)
    unknown: str | None = None  # what it writes can't be seen (a patch on a pipe)


def _opt_values(toks: list[str], names: tuple[str, ...]) -> list[str]:
    out = []
    for k, t in enumerate(toks):
        for n in names:
            if t == n and k + 1 < len(toks):
                out.append(toks[k + 1])
            elif t.startswith(n + "=") and n.startswith("--"):
                out.append(t.split("=", 1)[1])
            elif not n.startswith("--") and t.startswith(n) and len(t) > len(n):
                out.append(t[len(n) :])
    return out


def _is_dir(path: str, cwd: str | None, root: Path) -> bool:
    if path.endswith("/") or path in (".", ""):
        return True
    a = _abspath(path, cwd)
    return bool(a) and os.path.isdir(a)


def _join(d: str, name: str) -> str:
    return name if d in ("", ".") else d.rstrip("/") + "/" + name


def _copy_targets(cmd: str, toks: list[str], seg: Seg, root: Path, t: _Targets) -> None:
    args = toks[1:]
    recursive = cmd in ("rsync", "mv") or any(
        a in ("-r", "-R", "-a", "--recursive", "--archive") or (re.fullmatch(r"-[a-zA-Z]+", a) and set(a[1:]) & set("rRa")) for a in args
    )
    operands = [a for a in args if not a.startswith("-")]
    tdir = _opt_values(toks, ("-t", "--target-directory")) if cmd != "rsync" else []
    no_tdir = any(a in ("-T", "--no-target-directory") for a in args)
    if cmd == "install" and any(a in ("-d", "--directory") for a in args):
        t.files += operands
        return
    if tdir:
        dest, srcs, dest_is_dir = tdir[0], operands, True
    elif len(operands) > 1:
        dest, srcs = operands[-1], operands[:-1]
        dest_is_dir = not no_tdir and (len(srcs) > 1 or _is_dir(dest, seg.cwd, root))
    elif cmd == "ln" and operands:
        dest, srcs, dest_is_dir = ".", operands, True
    else:
        return
    if cmd == "ln":
        link_dir = dest if dest_is_dir else posixpath.dirname(dest)
        for s in srcs:
            t.links.append(s)
            if not os.path.isabs(s) and link_dir not in ("", "."):
                t.links.append(_join(link_dir, s))
    for s in srcs:
        whole = s.rstrip("/").endswith("/.") or s in (".", "./") or (cmd == "rsync" and s.endswith("/"))
        if dest_is_dir and not whole:
            target = _join(dest, posixpath.basename(s.rstrip("/")) or s)
        else:
            target = dest
        (t.trees if (recursive and cmd != "ln") or _norm(target, root, seg.cwd) == "" else t.files).append(target)
    if cmd == "mv":
        t.trees += srcs


def _tar_targets(toks: list[str], seg: Seg, t: _Targets) -> None:
    args = toks[1:]
    extract = False
    archive: str | None = None
    dirs: list[str] = []
    members: list[str] = []
    strip = 0

    def take(ch: str, v: str) -> None:
        nonlocal archive
        if ch == "f":
            archive = v
        elif ch == "C":
            dirs.append(v)

    i = 0
    while i < len(args):
        a = args[i]
        if i == 0 and re.fullmatch(r"[A-Za-z]+", a):  # old style: `tar xzf a.tgz`
            for ch in a:
                extract = extract or ch == "x"
                if ch in "fCbT":  # each takes the next argument, in order
                    i += 1
                    take(ch, args[i] if i < len(args) else "")
        elif a in ("--extract", "--get"):
            extract = True
        elif a in ("-f", "--file", "-C", "--directory"):
            i += 1
            take("f" if a in ("-f", "--file") else "C", args[i] if i < len(args) else "")
        elif a.startswith(("--file=", "--directory=")):
            take("f" if a.startswith("--file=") else "C", a.split("=", 1)[1])
        elif a.startswith("--strip-components="):
            v = a.split("=", 1)[1]
            strip = int(v) if v.isdigit() else 0
        elif re.fullmatch(r"-[A-Za-z]+", a):  # a cluster: -xzf a.tgz, -Cdir
            letters = a[1:]
            for k, ch in enumerate(letters):
                extract = extract or ch == "x"
                if ch in "fCbT":
                    v = letters[k + 1 :]
                    if not v:
                        i += 1
                        v = args[i] if i < len(args) else ""
                    take(ch, v)
                    break
        elif not a.startswith("-"):
            members.append(a)
        i += 1
    if not extract:
        return
    dest = dirs[-1] if dirs else "."
    names = members or _archive_members(archive, seg.cwd, "tar")
    if names is None:
        t.trees.append(dest)
        return
    for m in names:
        parts = [p for p in m.lstrip("/").split("/") if p not in ("", ".")][strip:]
        if parts:
            t.files.append(_join(dest, "/".join(parts)))


def _archive_members(archive: str | None, cwd: str | None, kind: str) -> list[str] | None:
    if not archive or archive == "-":
        return None
    a = _abspath(archive, cwd)
    if not a or not os.path.isfile(a):
        return None
    try:
        if os.path.getsize(a) > 200_000_000:
            return None
        if kind == "zip":
            with zipfile.ZipFile(a) as z:
                return z.namelist()[:50000]
        out: list[str] = []
        with tarfile.open(a) as tf:
            for m in tf:
                if m.issym() or m.islnk():
                    return None  # a link could point anywhere
                out.append(m.name)
                if len(out) > 50000:
                    return None
        return out
    except Exception:
        return None


def _unzip_targets(toks: list[str], seg: Seg, t: _Targets) -> None:
    args = toks[1:]
    if any(re.fullmatch(r"-[A-Za-z]*[lptvZz][A-Za-z]*", a) for a in args):
        return  # list, test or print: nothing written
    dest = "."
    junk = any(re.fullmatch(r"-[A-Za-z]*j[A-Za-z]*", a) for a in args)
    operands: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-d":
            dest = args[i + 1] if i + 1 < len(args) else "."
            i += 2
            continue
        if re.fullmatch(r"-d.+", a):
            dest = a[2:]
        elif a == "-x":
            break
        elif not a.startswith("-"):
            operands.append(a)
        i += 1
    if not operands:
        return
    names = _archive_members(operands[0], seg.cwd, "zip")
    if names is None:
        t.trees.append(dest)
        return
    for m in names:
        m2 = posixpath.basename(m) if junk else m
        if m2:
            t.files.append(_join(dest, m2.lstrip("/")))


def _patch_paths(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^(?:\+\+\+|---) (\"?)(.+?)\1(?:\t.*)?$", line)
        if m:
            p = m.group(2).strip()
            if p != "/dev/null":
                out.append(p)
            continue
        m = re.match(r"^diff --git (\S+) (\S+)", line)
        if m:
            out += [m.group(1), m.group(2)]
            continue
        m = re.match(r"^(?:rename|copy) (?:from|to) (.+)$", line)
        if m:
            out.append(m.group(1))
    paths: list[str] = []
    for p in out:
        paths.append(p)
        if "/" in p:
            paths.append(p.split("/", 1)[1])  # a/ b/ prefixes, -p1
    return paths


def _patch_targets(cmd: str, args: list[str], seg: Seg, root: Path, t: _Targets) -> None:
    """git apply (args after `apply`) or patch (args after `patch`)."""
    if cmd == "git":
        if any(a in ("--check", "--stat", "--numstat", "--summary") for a in args) and "--apply" not in args:
            return
        files = [a for a in args if not a.startswith("-")]
        for v in _opt_values(["x", *args], ("--directory",)):
            files = [f for f in files if f != v]
        texts_from = files
        base_dir = os.path.realpath(str(root))
    else:
        if any(a == "--dry-run" for a in args):
            return
        inputs = _opt_values(["x", *args], ("-i", "--input"))
        skip = set(inputs) | set(_opt_values(["x", *args], ("-p", "-d", "--directory", "-o", "--output", "-r", "-B", "-z", "-D")))
        positional = [a for a in args if not a.startswith("-") and a not in skip]
        if positional:
            t.files.append(positional[0])  # the file being patched
        texts_from = inputs or positional[1:2]
        base_dir = seg.cwd
    texts: list[str] = []
    for f in texts_from:
        if f == "-":
            texts_from = []
            break
        txt = _read_text(f, seg.cwd)
        if txt is None:
            t.unknown = f"can't read the patch `{f}` to see what it changes"
            return
        texts.append(txt)
    if not texts_from:
        if seg.stdin:
            txt = _read_text(seg.stdin, seg.cwd)
            if txt is None:
                t.unknown = f"can't read the patch `{seg.stdin}` to see what it changes"
                return
            texts.append(txt)
        elif seg.heredoc is not None:
            texts.append(seg.heredoc)
        else:
            t.unknown = "this applies a patch from a pipe, where the guard can't see what it changes; apply it from a file"
            return
    for txt in texts:
        for p in _patch_paths(txt):
            if cmd == "git":  # paths from the top of the repository
                full = os.path.join(base_dir, p)
                t.files.append(os.path.relpath(full, seg.cwd) if seg.cwd else full)
            else:
                t.files.append(p)


def _git_targets(args: list[str], t: _Targets) -> None:
    sub = args[0] if args else ""
    rest = args[1:]
    if sub in ("rm", "mv", "clean"):
        paths = [a for a in rest if not a.startswith("-") and a != "--"]
        t.files += paths
        t.trees += paths or ["."]
        return
    if sub == "checkout":
        skip = set(_opt_values(["x", *rest], ("-b", "-B", "--orphan", "-c", "-C")))
        if "--" in rest:
            k = rest.index("--")
            before = [a for a in rest[:k] if not a.startswith("-") and a not in skip]
            paths = rest[k + 1 :]
            (t.trees if before else t.files).extend(paths)
        else:
            plain = [a for a in rest if not a.startswith("-") and a not in skip]
            if len(plain) >= 2:
                t.trees += plain[1:]
            else:
                t.files += plain
        return
    if sub == "restore":
        source = _opt_values(["x", *rest], ("-s", "--source"))
        paths = [a for a in rest if not a.startswith("-") and a != "--" and a not in source]
        (t.trees if source else t.files).extend(paths)


def _write_targets(seg: Seg, root: Path) -> _Targets:
    """What one command writes, removes, links to, or can't show."""
    toks = seg.words
    t = _Targets(files=list(seg.redirects))
    if not toks:
        return t
    cmd = Path(toks[0]).name
    operands = [a for a in toks[1:] if not a.startswith("-")]
    if cmd in _RM_LIKE:
        t.files += operands
        t.trees += operands
    elif cmd in _TOUCH_LIKE:
        if cmd in {"chmod", "chown", "chgrp", "chattr", "setfacl"} and operands:
            operands = operands[1:]
        if cmd == "truncate":
            operands = [o for o in operands if o not in _opt_values(toks, ("-s", "--size", "-r", "--reference"))]
        t.files += operands
        if any(a in ("-R", "-r", "--recursive") for a in toks[1:]):
            t.trees += operands
    elif cmd in _DEST_LAST:
        _copy_targets(cmd, toks, seg, root, t)
    elif cmd in ("tee", "sponge"):
        t.files += operands
    elif cmd == "dd":
        t.files += [a[3:] for a in toks[1:] if a.startswith("of=")]
    elif cmd == "sed" and any(a == "-i" or (a.startswith("-i") and not a.startswith("--")) or a.startswith("--in-place") or (re.fullmatch(r"-[a-zA-Z]+", a) and "i" in a) for a in toks[1:]):
        t.files += operands[1:]
    elif cmd == "perl" and any(re.match(r"^-\w*i", a) for a in toks[1:]):
        t.files += operands[1:]
    elif cmd == "curl":
        t.files += _opt_values(toks, ("-o", "--output"))
        t.trees += _opt_values(toks, ("--output-dir",))
    elif cmd == "wget":
        t.files += _opt_values(toks, ("-O", "--output-document"))
        t.trees += _opt_values(toks, ("-P", "--directory-prefix"))
    elif cmd == "tar":
        _tar_targets(toks, seg, t)
    elif cmd == "unzip":
        _unzip_targets(toks, seg, t)
    elif cmd == "patch":
        _patch_targets("patch", toks[1:], seg, root, t)
    elif cmd == "find":
        if any(a in ("-delete", "-exec", "-execdir", "-ok", "-okdir") for a in toks):
            for a in toks[1:]:
                if a.startswith("-") or a in ("(", "!"):
                    break
                if a not in (".", "./"):  # under the root: what it matches can't be seen
                    t.files.append(a)
    else:
        g = _git(toks)
        if g:
            _, args, _ = g
            if args[:1] == ["apply"]:
                _patch_targets("git", args[1:], seg, root, t)
            else:
                _git_targets(args, t)
    return t


def _braces(word: str, limit: int = 64) -> list[str]:
    """Bash brace expansion of `{a,b}` lists (not `{1..3}`)."""
    m = None
    depth = 0
    for i, c in enumerate(word):
        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}" and depth:
            depth -= 1
            if depth == 0:
                inner = word[start + 1 : i]
                parts, d, cur = [], 0, ""
                for ch in inner:
                    if ch == "," and d == 0:
                        parts.append(cur)
                        cur = ""
                        continue
                    d += {"{": 1, "}": -1}.get(ch, 0)
                    cur += ch
                parts.append(cur)
                if len(parts) > 1:
                    m = (start, i, parts)
                    break
    if not m:
        return [word]
    s, e, parts = m
    out: list[str] = []
    for p in parts:
        out += _braces(word[:s] + p + word[e + 1 :], limit)
        if len(out) > limit:
            break
    return out[:limit]


def _candidates(target: str, cwd: str | None) -> list[str]:
    """The paths a write target may stand for: its brace list, and what its glob matches now."""
    out: list[str] = []
    for w in _braces(target):
        out.append(w)
        if _GLOB_CHARS.search(w):
            base = cwd or ""
            pat = w if os.path.isabs(w) or not base else os.path.join(base, w)
            try:
                hits = _glob.glob(pat)[:200]
            except Exception:
                hits = []
            out += hits
    return out


def _protected_hit(target: str, seg: Seg, root: Path, patterns: list[str], tree: bool) -> str | None:
    check = contains_protected if tree else matches
    for c in _candidates(target, seg.cwd):
        if not c.strip():
            continue
        a = _abspath(c, seg.cwd)
        if a is None:  # relative to a directory we can't see
            rel = posixpath.normpath(c.strip())
            hit = check(rel, patterns) or could_match(rel, patterns)
            if hit:
                return hit
            continue
        rel = _rel(a, root)
        hit = contains_protected(rel, patterns) if tree else matches(rel, patterns)
        if hit:
            return hit
    return None


def _shell_protected(seg: Seg, patterns: list[str], root: Path) -> str | None:
    t = _write_targets(seg, root)
    if t.unknown:
        return t.unknown
    unknown_dir = "; the shell's directory can't be followed here (after `cd -`, `cd ~` or `cd $X`), so use a path from the project root"
    for tgt in t.files:
        hit = _protected_hit(tgt, seg, root, patterns, tree=False)
        if hit:
            return f"writing `{tgt}` touches a protected path ({hit})" + (unknown_dir if seg.cwd is None else "")
    for tgt in t.trees:
        hit = _protected_hit(tgt, seg, root, patterns, tree=True)
        if hit:
            return f"writing into, removing or moving `{tgt}` touches a protected path ({hit})" + (unknown_dir if seg.cwd is None else "")
    for src in t.links:
        hit = _protected_hit(src, seg, root, patterns, tree=True)
        if hit:
            return f"linking to `{src}` would let a protected path ({hit}) be written through the link"
    toks = seg.words
    if toks and _INTERP.match(Path(toks[0]).name):
        code = _inline_code(toks)
        if _WRITE_CALL.search(code):
            for lit in re.findall(r"""['"]([^'"\n]+)['"]""", code):
                p = lit.strip().lstrip("+<>").strip()
                if p and not re.search(r"\s", p) and matches(_norm(p, root, seg.cwd), patterns):
                    return f"this one-liner writes the protected path `{p}`"
    return None


_WRITE_CALL = re.compile(
    r"""\bopen\s*\([^)]*['"](?:[rwxabt]*[wax+][rwxabt+]*|\+?[<>]{1,2}[^'"]*)['"]|\bwrite\w*\s*\(|\.write\b|writeFile|appendFile|"""
    r"""\bunlink|\brmtree\b|\brmdir|\brename|\breplace\s*\(|\bcopy\w*\s*\(|\bmove\s*\(|\bremove\s*\(|\brmSync\b|\bsymlink|\bchmod\b|\btruncate\b|\bmkdir"""
)


def _shell_skips(seg: Seg, command: str, profile: Profile, root: Path) -> str | None:
    t = _write_targets(seg, root)
    for tgt in t.files:
        rel = _norm(tgt, root, seg.cwd)
        if rel and matches(rel, profile.test_paths) and _SKIP.search(command):
            return f"this writes a skip or focus marker into the test file `{tgt}`; skipping or disabling a test is never allowed"
    return None


def _word_problem(toks: list[str], role: str) -> str | None:
    """A command word that hides what runs (ticket and conductor sessions)."""
    if not toks or role not in ("ticket", "conductor"):
        return None
    w = toks[0]
    if w in ("[", "[[", "]]"):
        return None
    if "$IFS" in w or "${IFS" in w:
        return f"the command word `{w}` hides what runs (`$IFS`); write the command plainly"
    if role == "ticket" and w.startswith("$"):
        return f"the command word `{w}` is a variable or substitution, so the guard can't see what runs; run the command by name"
    if _GLOB_CHARS.search(w) and not w.startswith("$"):
        return f"the command word `{w}` is a glob, so the guard can't see what runs; run the command by name"
    if re.search(r"\{[^{}]*,[^{}]*\}", w):
        return f"the command word `{w}` is a brace list, so the guard can't see what runs; run the command by name"
    return None


def check_bash(
    command: str,
    profile: Profile,
    role: str,
    root: Path,
    current_branch: str | None,
    role_from_env: bool = True,
    cwd: str | os.PathLike | None = None,
) -> Decision:
    start = _start_cwd(root, cwd)
    segs = segments(command, root, start)
    protected = list(profile.protected_paths) + (GIT_INTERNALS if role == "ticket" else [])
    posts: list[Seg] = []
    for seg in segs:
        p = _word_problem(seg.words, role) or _env_problem(seg, role)
        if p:
            return _deny(role, p)
        k = _vcs_index(seg.words, role)
        toks = seg.words[k:] if k is not None else seg.words
        g = _git(toks)
        if g is not None:
            glob, args, cdir = g
            p = _git_config_problem(glob, args, role)
            if p:
                return _deny(role, p)
            if args and args[0] in ("push", "send-pack", "http-push"):
                if role != "attended" and any(o == "--git-dir" or o.startswith(("--git-dir=", "--work-tree")) for o in glob):
                    return _deny(role, "push from the repository's own directory, not with `--git-dir`/`--work-tree`")
                d = _git_dir_of(root, seg.cwd, cdir)
                same = cdir is None and seg.cwd == start
                branch = current_branch if same else _branch_of(d)
                p = _push_problem(args, profile.base_branch, branch, role, profile.ticket_branch, upstream=lambda d=d: _upstream_branch(d))
                if p:
                    return _deny(role, p)
            if role == "ticket" and not role_from_env:
                p = _switch_problem(args, profile.ticket_branch)
                if p:
                    return Decision("deny", p)
        if toks and Path(toks[0]).name == "gh":
            p = _gh_problem(toks, profile, role, seg.cwd, command)
            if p:
                return _deny(role, p)
        p = _api_problem(seg.words, profile, role, seg.cwd, command) if seg.words and Path(seg.words[0]).name == "curl" else None
        if p:
            return _deny(role, p)
        if _post_kind(toks):
            posts.append(seg if k is None else Seg(toks, seg.redirects, seg.cwd))
        if role in ("ticket", "attended"):
            p = _deploy_problem(seg, profile.deploy_commands, root)
            if p:
                return _deny(role, p)
        if role == "ticket":
            p = _shell_protected(seg, protected, root)
            if p:
                return Decision("deny", p + "; ticket sessions don't change protected paths (the owner reviews those)")
            if not profile.allow_new_skips:
                p = _shell_skips(seg, command, profile, root)
                if p:
                    return Decision("deny", p)
    if posts and profile.sensitive_patterns:
        texts = [command]
        for s in posts:
            for f in _body_files(s.words):
                txt = _read_text(f, s.cwd)
                if txt:
                    texts.append(txt)
        text = "\n".join(texts)
        for pat in profile.sensitive_patterns:
            if re.search(pat, text):
                return _deny(role, f"this would post text matching the sensitive-data pattern {pat!r}; refer to things by id")
    return ALLOW


# ---------- file tools ----------


def _added_skips(old: str, new: str) -> int:
    return len(_SKIP.findall(new or "")) - len(_SKIP.findall(old or ""))


def check_write(tool: str, inp: dict, profile: Profile, role: str, root: Path, cwd: str | os.PathLike | None = None) -> Decision:
    path = inp.get("file_path") or inp.get("notebook_path") or ""
    start = _start_cwd(root, cwd)
    a = _abspath(path, start) if path else None
    rel = _rel(a, root) if a else ""
    if role == "ticket" and rel:
        m = matches(rel, list(profile.protected_paths) + GIT_INTERNALS)
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
            old = Path(a).read_text(encoding="utf-8") if a else ""
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
    if role == "ticket" and (name in _TICKET_MCP_DENY or any(w in name.lower() for w in _TICKET_MCP_DENY_WORDS)):
        return Decision("deny", f"`{name}` isn't something a ticket session uses (it runs workflows, makes repositories, deletes files or touches secrets)")
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


def decide(
    event: dict,
    profile: Profile,
    role: str,
    root: Path,
    current_branch: str | None,
    role_from_env: bool = True,
    cwd: str | os.PathLike | None = None,
) -> Decision:
    """The guard's decision on one PreToolUse event. `cwd` is the shell's
    directory (the event's `cwd`, which is used when it isn't given)."""
    tool = event.get("tool_name") or ""
    inp = event.get("tool_input") or {}
    if not isinstance(inp, dict):
        inp = {}
    if cwd is None:
        cwd = event.get("cwd") or None
    if tool == "Bash":
        return check_bash(inp.get("command") or "", profile, role, root, current_branch, role_from_env, cwd)
    if tool in WRITE_TOOLS:
        return check_write(tool, inp, profile, role, root, cwd)
    if tool.startswith("mcp__"):
        return check_mcp(tool, inp, profile, role, root)
    return ALLOW
