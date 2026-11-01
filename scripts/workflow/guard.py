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
subshells (restored at `)`), `env -C`, `git -C` and `cd -` (OLDPWD); after
`cd ~`, `cd $X`, a bare `cd` or a `cd -` with no previous directory the
directory is unknown, and a relative write is then refused in ticket sessions
when it could be a protected path. Paths outside the project root are never its
protected paths (the global git config is checked on its own). It looks inside
`sh -c`, `eval`, `script -c`, `find -exec`, heredocs fed to a shell, and
interpreter one-liners, and in ticket and conductor sessions finds `git`,
`git-push` or `gh` anywhere among a command's words (behind `setsid`, `doas`,
`time -p` or any other wrapper).

**Ticket sessions are held to allow-lists** where a deny-list can't keep up:
- `git push` (and `send-pack`, `http-push`, `git-push`) may only update the
  session's own branch (`run.ticket_branch`), never tags; a bare push only when
  its upstream has the branch's own name (`$(git branch --show-current)` and
  the like count as the current branch), and `git branch -u` may only set an
  upstream of the branch's own name;
- `gh` may only run the subcommands a ticket needs (pull requests, issues,
  runs, workflow reads, `api`, reads); `gh api` writes may only touch this
  repo's issues, comments, labels and pull requests; never GraphQL (the shell
  can assemble a query in more ways than this can follow; the MCP tools and
  REST cover auto-merge, comments and reads);
- `git config`, `git -c`, `--config-env` and `GIT_CONFIG*`/`GIT_SSH*`/
  `GIT_DIR`-style variables may not set aliases, push, remote, credential or
  command settings (conductor too);
- a command word may not be a variable, a glob, a brace list or hold `$IFS`;
- a merge, or an arm of auto-merge, only of the session's own pull request:
  pinned to the checked-out ticket branch's head (`--match-head-commit`, the
  REST merge's `sha`, `merge_pull_request`'s `expectedHeadSha`), or, for
  `enable_pr_auto_merge` and `ccr/auto_merge`, with the pull request's head
  read back from GitHub (`_pr_head`); adding it to a merge queue through
  `merge-async` is pinned by its `sha` the same way.

**Every role** is held to a deny-list: pushing to the base branch, force-pushes,
deleting or mirroring branches (also by `remote.*.mirror`, `remote.pushDefault`
or `remote.*.skipDefaultUpdate` set with `-c` or `git config`, or
`git remote add --mirror`), `gh pr merge --admin`, a `merge-async` with
`bypass_rules`, any `merge_action` but `merge_queue` or no `sha`, and
rewriting the base branch, its name, the default branch (`gh repo edit
--default-branch`, `gh api` with its body in a file too), its protection or
rulesets through the API; a GraphQL mutation that does so is looked for in the
whole command and the files it reads with `cat`. Ticket sessions and the
conductor are denied; attended sessions are asked, except in solo mode (`project.ruleset = false`): there an
attended session's git push that touches the base branch, or whose destination
can't be told, is refused with `solo_refusal`'s reason (a force-push or
deletion of a named feature branch is still asked), and so is a change to the
base branch through GitHub (`gh pr merge --admin`, the default branch, its name,
ref or protection, a ruleset other than creating one; by `gh api`, `curl`,
GraphQL or the GitHub MCP tools). Ticket sessions and the
conductor also may not write the global git config (~/.gitconfig,
~/.config/git/, $XDG_CONFIG_HOME/git/, the file $GIT_CONFIG_GLOBAL names).

**Ticket sessions also may not:** run the profile's deploy commands (also fed
to a shell on stdin, run by an interpreter or launcher such as `python3`,
`node`, `uv run` or `bash -o pipefail`, through `env -C` or `find -exec`; the
attended are asked), write protected paths (Edit/Write, the shell's writers:
redirects, `cp`/`mv`/`install`/`rsync`/`ln`, `rm`, `sed -i`, `perl -i`,
`awk -i inplace`, `ed`, `ex`/`vim` with a script, `tee`, `dd`, `tar`/`unzip`
extraction, `git apply`/`am`/`patch` (a patch from a heredoc or a `cat` is
read), `git checkout <tree> -- <path>`, `git clean` of a path holding one,
`find` with `-delete` or a writing `-exec` over a tree holding one, through
symlinks, `/proc/self/cwd`, globs and brace lists; an in-place edit of the
files a search of a tree holding one finds is refused, so the files are named;
`.git/config` and `.git/hooks` count as protected), add skip or focus markers
to tests (counted in the writing command's own inserted text, net of what it
removes), use the GitHub MCP tools that trigger workflows, make repositories or
touch secrets, or, when their role comes only from the branch name, switch,
detach or rename away from a branch matching the pattern. A GitHub post (MCP,
`gh`, `curl`) matching the profile's sensitive patterns is refused in every
role: heredocs, body files, its stdin, a piped producer's files and any file
the command reads with `cat` or `<` included.

**Agents' posts carry the marker.** In ticket and conductor sessions, a post
that creates text on GitHub (an issue, pull request, comment or review, or an
edit of one's body: `gh issue|pr create|comment`, an edit, close or reopen with
a body or comment, `gh api` to those endpoints and commit comments with a
`body` field, or with `--input` JSON that carries a `body` or `comment` (or
can't be read), the text-posting GraphQL mutations, and the GitHub MCP tools
that post them) is refused unless the texts it is checked for sensitive data in
hold `<!-- workflow:agent -->`. A GraphQL query from `--input` (a file or
stdin) is read from its JSON's `query`; a mutation that may carry a body counts
only when its arguments (or, through a `$variable`, its variables) name one.
Labels, state changes, `--delete-last` and merges aren't posts. The marker is
looked for in the command's texts as a whole: a seatbelt, not proof per post.
Attended sessions are not asked.

**Who writes code** (#340): under `code_writers = "ticket"` (`profile.code_rule`,
the stricter of the working tree's and the base's profile), only a session with
`WORKFLOW_ROLE=ticket` writes code. Every other session is refused, never asked,
a write the guard places on a code path (`_code_session`, `_shell_code`); a
session that is a ticket session only by its branch or a mistyped role gets an
attended session's rules. It is refused too a `git commit` in the project's
own repository that carries a code path (`_commit_code`, #389): what is
staged, plus what `-a` or a pathspec adds. When the guard can't read what a
commit carries, an attended session is asked and the conductor refused.
So is a `git push` to `project.repo`, from any directory, whose commits not
on a tracking ref of a remote fetching from it carry a code path
(`_push_code`, #390), with the same can't-tell rule. A planning session (not
the conductor) may write and commit code on a `prototype/*` branch, and push
from one to `prototype/*` branches only; their tracking refs don't count as
on the remote (#393).

What it can't see (a script file written then run, a program's own network
calls, variables' values, obfuscation it doesn't recognise) is why the ruleset
and the environment come first.
"""

from __future__ import annotations

import contextlib
import fnmatch
import functools
import glob as _glob
import json
import os
import posixpath
import re
import shlex
import stat
import subprocess
import tarfile
import urllib.parse
import zipfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import fallback, modes
from . import profile as profile_mod
from . import roles as roles_mod
from .posts import AGENT_MARKER
from .profile import Profile, resolve_experience

SKIP_MARKERS = [
    r"pytest\.mark\.skip(?:if)?\b",
    r"\bpytest\.skip\(",
    r"\bunittest\.skip",
    r"\bskipTest\(",
    r"\bSkipTest\b",
    r"pytest\.mark\.xfail\((?:(?!pytest\.mark\.xfail\()[^)])*run\s*=\s*False",  # stops at the next `xfail(`, so it stays linear
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
    sensitive: bool = False  # the input holds sensitive data: never repeat it, nor say to post it by hand
    label: str | None = None  # the session as the refusal names it, when not by its role alone (#340)


ALLOW = Decision("allow")


def _deny(role: str, reason: str, sensitive: bool = False) -> Decision:
    if role == "attended":
        return Decision("ask", reason.replace("is never allowed", "is outside the workflow's rules; allow it only if you mean to"), sensitive)
    return Decision("deny", reason, sensitive)


# ---------- solo mode ----------


@dataclass
class SoloRefusal:
    """Why solo mode refuses an attended session's command. `what` says what the
    guard saw, in a few words. `kind` is "change" (it changes the base branch),
    "unknown" (the guard can't tell which branch it changes, so it counts as the
    base branch) or "setting" (it sets git up so a later push changes it)."""

    what: str
    kind: str = "change"
    hint: str = ""  # for "unknown": what to do instead (by default, push the branch by name)


# Credentials a command may carry: a URL's user:password@, a token variable's value.
_URL_CREDENTIALS = re.compile(r"(?<=://)[^/\s@'\"]+@")
_SECRET_VARS = re.compile(r"(?i)\b(\w*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|CREDENTIALS?)\w*)([ \t]+=[ \t]*|=(?:[ \t]+(?=['\"]))?)(?:'[^']*'|\"[^\"]*\"|\S+)")
_SECRET_HEADERS = re.compile(r"(?i)(authorization:\s*(?:\w+\s+)?|bearer\s+|extraheader=)[^\s\"']+")
_WITHOUT_SENSITIVE = "without the text that matches the project's sensitive-data pattern"
_HAND_MAX = 400  # longer than this, the hand command isn't repeated


def _hand_command(command: str) -> str:
    """The command to run by hand, as code, with credentials masked; or a
    pointer back to it when it's too long to repeat."""
    text = _SECRET_HEADERS.sub(r"\1…", _SECRET_VARS.sub(r"\1\2…", _URL_CREDENTIALS.sub("…@", command.strip())))
    if len(text) > _HAND_MAX:
        return " the command as you gave it (too long to repeat here)."
    code = _code_span(text)
    return code if code.startswith("\n") else " " + code


def _code_span(text: str) -> str:
    """`text` as code, whatever backticks it holds: inline, or a fenced block
    when it runs over more than one line (a heredoc)."""
    text = text.strip()
    longest = max((len(r) for r in re.findall(r"`+", text)), default=0)
    if "\n" in text:
        fence = "`" * max(3, longest + 1)
        return f"\n{fence}\n{text}\n{fence}"
    if not longest:
        return f"`{text}`"
    fence = "`" * (longest + 1)
    return f"{fence} {text} {fence}"


def solo_refusal(base: str, level: str, command: str, refusal: SoloRefusal, sensitive: bool = False) -> str:
    """The reason a solo-mode refusal gives, which Claude relays: why in plain
    words, what `base` is (only for `level` "new"), the command to run by hand
    and what the kit saw (neither when `sensitive`: the input holds text
    matching a sensitive pattern, which either may repeat), and the "Protect" offer. Wording follows `level`; what is refused never does."""
    what = refusal.what
    if refusal.kind == "unknown":
        hint = refusal.hint or "push the branch by name (`git push origin <branch>`)"
        lines = [f"The kit can't tell which branch this would change, so it counts as `{base}`. Without GitHub's protection set up, the kit doesn't allow that: {hint}."]
    elif refusal.kind == "setting":
        lines = [f"This would set git up so that a later push changes `{base}` without a pull request. Without GitHub's protection set up, the kit doesn't allow that."]
    else:
        lines = [f"This would change `{base}` directly. Without GitHub's protection set up, the kit doesn't allow that."]
    if what and not sensitive:
        lines.append(f"What the kit saw: {what}.")
    if level == "new":
        lines.append(f"`{base}` is the branch the project's work comes together on: the version everyone builds on, which should change only through a pull request.")
    name_it = " name the branch and" if refusal.kind == "unknown" and not refusal.hint else ""
    if sensitive:
        lines.append(f"If you really mean it,{name_it} run it yourself in your own terminal, {_WITHOUT_SENSITIVE}.")
    else:
        lines.append(f"If you really mean it,{name_it} run it yourself in your own terminal:{_hand_command(command)}")
    lines.append(
        f'Offer "Protect `{base}`" as a choice, with "Not now": it sets up GitHub\'s protection, so `{base}` changes only through pull requests.'
    )
    return "\n".join(lines)


def _solo_deny(s: SoloRefusal, profile: Profile, root: Path, command: str, sensitive: bool = False) -> Decision:
    level = resolve_experience(root, profile.experience).wording_level
    return Decision("deny", solo_refusal(profile.base_branch, level, command, s, sensitive), sensitive)


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


_PWD = re.compile(r"^(?:\$PWD\b|\$\{PWD(?:%/)?\}|\$\(\s*pwd(?:\s+-[LP])?\s*\)|`\s*pwd(?:\s+-[LP])?\s*`)(?=/|$)")
_PROC_CWD = re.compile(r"^/proc/(?:self|thread-self|\$\$|\$BASHPID|\d+)/cwd(?=/|$)")


_KNOWN_VARS = re.compile(r"\$(?:\{(HOME|XDG_CONFIG_HOME|GIT_CONFIG_GLOBAL)\}|(HOME|XDG_CONFIG_HOME|GIT_CONFIG_GLOBAL)\b)")


def _expand_known(p: str) -> str:
    """`$HOME`, `$XDG_CONFIG_HOME` and `$GIT_CONFIG_GLOBAL` from the environment,
    when set; any other variable is left as it is."""

    def sub(m: re.Match) -> str:
        v = os.environ.get(m.group(1) or m.group(2))
        return v if v else m.group(0)

    return _KNOWN_VARS.sub(sub, p) if "$" in p else p


def _abspath(path: str, cwd: str | None) -> str | None:
    """`path` as an absolute, symlink-resolved path, or None when it depends on
    a directory we can't see."""
    p = _expand_known(path.strip())
    if not p:
        return None
    m = _PWD.match(p)
    if m:
        if cwd is None:
            return None
        p = cwd + p[m.end() :]
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


def _outside(rel: str) -> bool:
    """A path `_rel` left absolute: outside the project root, so never one of
    its protected paths (the global git config is checked on its own)."""
    return rel.startswith("/")


def _holds_root(abspath: str, root: Path) -> bool:
    """`abspath` is the project root or a directory above it."""
    r = os.path.realpath(str(root))
    return r == abspath or r.startswith(abspath.rstrip("/") + "/")


def global_git_config() -> list[tuple[str, bool]]:
    """The global git config's files and directories, as (absolute path, is a
    directory): ~/.gitconfig, ~/.config/git/, $XDG_CONFIG_HOME/git/ and the file
    $GIT_CONFIG_GLOBAL names, from the environment."""
    out: list[tuple[str, bool]] = []
    home = os.environ.get("HOME") or os.path.expanduser("~")
    if home and home != "~":
        out += [(os.path.join(home, ".gitconfig"), False), (os.path.join(home, ".config", "git"), True)]
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        out.append((os.path.join(xdg, "git"), True))
    g = os.environ.get("GIT_CONFIG_GLOBAL")
    if g:
        out.append((os.path.expanduser(g), False))
    return [(os.path.realpath(p), d) for p, d in out]


def global_config_hit(abspath: str, tree: bool = False) -> str | None:
    """`abspath` is (or, written as a tree, holds) the global git config."""
    a = abspath.rstrip("/") or "/"
    for p, is_dir in global_git_config():
        if a == p or (is_dir and a.startswith(p + "/")) or (tree and p.startswith(a.rstrip("/") + "/")):
            return p
    return None


def _global_config_name(rel: str) -> bool:
    """A path relative to a directory we can't see that could be the global git config."""
    r = posixpath.normpath(rel)
    return posixpath.basename(r) == ".gitconfig" or bool(re.search(r"(^|/)(\.config/git(/.*)?|git/config)$", r)) or r in (".config", ".config/git")


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
    """An unquoted shell operator; a quoted word that looks like one is a plain str.
    `glued`: a `(` the lexer met inside a word (`*(e:…:)`, `"x"(…)`, `` `…`(…) ``),
    right after a `)`, or after a word or redirect of the command (`echo
    (src)(e:…:)`, `> (e:…:)`; not an unquoted `{ (…)`, `! (…)`, `time (…)`), or
    zsh's numeric glob before one (`<->(…)`): zsh's glob qualifiers, which
    can run code in the shell itself; bash reads it as an error outside a
    function's name or extglob."""

    glued: bool = False
    hoisted: bool = False  # the `(` or `)` around a substitution's commands put before their command


class Word(str):
    """A word as the lexer read it. `splits`: outside quotes it holds what the
    shell expands into other words, or more of them (a variable or substitution,
    a glob, a brace list, a leading tilde). `expands`: it holds an expansion in
    double quotes (`"$X"`, `"$(…)"`, a backtick), which the shell fills in as
    one word. A word built anywhere else is a plain str, which says nothing
    either way."""

    splits: bool = False
    expands: bool = False
    quoted: bool = False  # any of it quoted or escaped (`"time"`, `\{`): never a reserved word


_UNQUOTED_SPLITS = re.compile(r"[$*?\[]|^~|[=:]~")


def _brace_list(text: str) -> bool:
    """`text` may hold a brace list the shell expands: a `{`, then a `,` or `..`,
    then a `}` (braces inside it included: `{-XPUT,x={}}`). Read in one pass."""
    a = text.find("{")
    if a < 0:
        return False
    b = min((k for k in (text.find(",", a), text.find("..", a)) if k >= 0), default=-1)
    return b >= 0 and text.find("}", b) >= 0


def _unbacktick(body: str, in_dquotes: bool = False) -> str:
    """A backtick substitution's text as the shell then runs it: inside backticks
    `\\$`, `\\\\` and `\\`` lose their backslash first, and `\\"` too
    when the backticks are inside double quotes."""
    return re.sub(r'\\([$`\\"])' if in_dquotes else r"\\([$`\\])", r"\1", body)


@dataclass
class Heredoc:
    body: str
    quoted: bool
    fd: str = ""  # the descriptor it feeds (`3<<EOF`); "" is stdin


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


def _expansions(text: str, hashes: list[int] | None = None, zsh: bool = False) -> list[list]:
    """Command substitutions in text the shell expands (an unquoted heredoc),
    `hashes` and `zsh` as `_lex` takes them."""
    out: list[list] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if text.startswith("$(", i):
            toks, j = _lex(text, i + 2, stop_paren=True, hashes=hashes, zsh=zsh)
            out.append(toks)
            i = j + 1
            continue
        if c == "`":
            j = _backtick_end(text, i)
            out.append(_lex(_unbacktick(text[i + 1 : j]), hashes=hashes, zsh=zsh)[0])
            i = j + 1
            continue
        i += 1
    return out


def _lex(
    s: str, i: int = 0, stop_paren: bool = False, hashes: list[int] | None = None, zsh: bool = False
) -> tuple[list, int]:
    """Tokens of a shell command from s[i]: plain words (str), operators (Op)
    and heredocs (Heredoc). Command substitutions are lexed too and put, as a
    subshell, before the command they appear in; the word keeps their text.
    With stop_paren, stops at the `)` closing a `$(`, returning its index.
    Into `hashes`, a `#` (its index in its own text) read as a comment while
    a `(` glued to a word is open, which zsh reads as its pattern's; with
    `zsh`, such a `#` is read so, as a word's (`segments` reads both)."""
    out: list = []
    cmd_start = 0
    word: list[str] = []
    unquoted: list[str] = []  # the word's text outside quotes ("\0" for an unquoted substitution)
    in_word = False
    quoted = False
    expands = False  # an expansion in double quotes
    close_end = -1  # where the last `)` operator ended (a backslash-newline after it skipped)
    pending: list[tuple[str, bool, Heredoc]] = []
    depth = 0
    globs: list[int] = []  # the depths of the open `(` groups that are part of a word (zsh's, extglob's)
    n = len(s)

    def end_word() -> None:
        nonlocal word, in_word, quoted, unquoted, expands
        if in_word:
            w = Word("".join(word))
            bare = "".join(unquoted)
            w.splits = "\0" in bare or bool(_UNQUOTED_SPLITS.search(bare)) or _brace_list(bare)
            w.expands = expands
            w.quoted = quoted
            out.append(w)
        word, in_word, quoted, unquoted, expands = [], False, False, [], False

    def hoist(inner: list) -> None:
        nonlocal cmd_start
        opens, closes = Op("("), Op(")")
        opens.hoisted = closes.hoisted = True
        block = [opens, *inner, closes]
        out[cmd_start:cmd_start] = block
        cmd_start += len(block)

    def substitution(start: int, inner_from: int) -> int:
        toks, j = _lex(s, inner_from, stop_paren=True, hashes=hashes, zsh=zsh)
        word.append(s[start : j + 1])
        hoist(toks)
        return j + 1

    def backtick(start: int, in_dquotes: bool = False) -> int:
        j = _backtick_end(s, start)
        word.append(s[start : j + 1])
        hoist(_lex(_unbacktick(s[start + 1 : j], in_dquotes), hashes=hashes, zsh=zsh)[0])
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
                bare = line.lstrip("\t") if strip_tabs else line
                if bare == delim:
                    hd.body = s[lines_start:k]
                    k = e + 1 if e < n else n
                    found = True
                    break
                if stop_paren and bare.startswith(delim) and ")" in bare[len(delim):]:
                    # Inside `$( )` bash ends the heredoc at a line starting with
                    # the delimiter and holding a `)` after it: the rest of the
                    # line is code. Any heredoc still pending is read as code too.
                    hd.body = s[lines_start:k]
                    if pending[-1][2] is not hd:
                        pending.clear()
                        return pos + 1
                    k += len(line) - len(bare) + len(delim)
                    found = True
                    break
                if e >= n:
                    break
                k = e + 1
            if not found:  # no terminator: keep the rest as commands, so it's scanned
                pending.clear()
                return pos + 1
            if not hd.quoted:
                for inner in _expansions(hd.body, hashes, zsh):
                    hoist(inner)
        pending.clear()
        return k

    while i < n:
        c = s[i]
        if c == "\\":
            if i + 1 < n and s[i + 1] == "\n":
                if close_end == i:
                    close_end = i + 2
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
                if ch in "$`":
                    expands = True
                if s.startswith("$(", i):
                    i = substitution(i, i + 2)
                    continue
                if ch == "`":
                    i = backtick(i, in_dquotes=True)
                    continue
                if ch == "$" and re.match(r"\$(?:@|\{!|\{[^}]*\[@\])", s[i : i + 256]):
                    unquoted.append("\0")  # "$@", "${A[@]}", "${!p@}": several words, quoted or not
                word.append(ch)
                i += 1
            i += 1
            continue
        if s.startswith("$(", i):
            in_word = True
            unquoted.append("\0")
            i = substitution(i, i + 2)
            continue
        if c == "`":
            in_word = True
            unquoted.append("\0")
            i = backtick(i)
            continue
        if c in "<>" and s.startswith("(", i + 1):  # process substitution
            end_word()
            in_word = True
            i = substitution(i, i + 2)
            continue
        # Inside a `(` group glued to a word, zsh's pattern (`(src|#); git commit …`) holds the `#`, where an
        # array or a bash subshell (`time -p (`) starts a comment: the reading `zsh` asks for, else a comment.
        if c == "#" and not in_word and not (zsh and globs):
            if globs and hashes is not None:
                hashes.append(i)
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
            # A `(` inside a word, right after a `)`, or after a word of the command (zsh: `*(e:…:)`, `(src)(e:…:)`,
            # `echo (…)`), or zsh's numeric glob before one (`<->(…)`).
            glued = (
                c == "(" and (in_word or close_end == i or len(out) > cmd_start and not _leads_subshell(out, cmd_start))
                or c == "<" and bool(re.match(r"<\d*-\d*>\(", s[i : i + 64]))
            )
            fd = ""
            if c in "<>" and in_word and not quoted and word and "".join(word).isdigit():
                fd = "".join(word)
                word, in_word, quoted, unquoted = [], False, False, []
            else:
                end_word()
            if s.startswith("<<", i) and not s.startswith("<<<", i):
                strip_tabs = s.startswith("<<-", i)
                j = i + (3 if strip_tabs else 2)
                while j < n and s[j] in " \t":
                    j += 1
                delim, _q, end = _read_delim(s, j)
                if delim:
                    hd = Heredoc("", _q, fd)
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
            # A glob group's `(`, `|` and `)` are a word's (zsh's), so the command goes on: `echo (a|#) (b|#)`.
            pattern = False
            if op == "(":
                depth += 1
                if glued:  # an array's `A=(…)` too: zsh's reading of its comments only adds commands
                    globs.append(depth)
                    pattern = True
            elif op == ")":
                if globs and globs[-1] == depth:
                    globs.pop()
                    pattern = True
                depth -= 1
            elif op == "|" and globs:
                pattern = True
            tok = Op(fd + op)
            tok.glued = glued
            out.append(tok)
            if op in _SEPARATORS and not pattern:
                cmd_start = len(out)
            i += len(op)
            if op == ")":
                close_end = i
            continue
        word.append(c)
        unquoted.append(c)
        in_word = True
        i += 1
    end_word()
    return out, n


# Words after which a `(` still opens a subshell, as at a command's start: `{ (…); }`, `! (…)`, `time (…)`.
_SUBSHELL_LEADERS = {"{", "!", "if", "then", "else", "elif", "do", "while", "until", "time"}


def _leads_subshell(toks: list, start: int = 0) -> bool:
    """The tokens so far of a simple command are only unquoted words after
    which a `(` opens a subshell: anything else there (another word, a
    quoted `"time"`, `time -p`, whose `-p` zsh runs as the command, a
    redirect, a heredoc) makes zsh read a `(` as part of a word, a pattern
    with glob qualifiers. From toks[start], so nothing is copied."""
    return all(
        type(toks[k]) is Word and not toks[k].quoted and toks[k] in _SUBSHELL_LEADERS for k in range(start, len(toks))
    )


def _tokens(command: str) -> list:
    return _lex(command)[0]


# ---------- simple commands ----------


@dataclass
class _Cmd:
    words: list[str] = field(default_factory=list)
    redirects: list[str] = field(default_factory=list)
    stdin: str | None = None
    heredoc: str | None = None
    inputs: list[str] = field(default_factory=list)  # every `<` file, whatever its descriptor
    stdins: int = 0  # heredocs, here-strings and `<` files given: bash reads only the last
    stdin_unseen: bool = False  # stdin from another descriptor (`<&3`), closed, or not what `stdin`/`heredoc` hold (`3<f`)
    expanded: str = ""  # the text of its unquoted heredocs and here-strings, which the shell expands (a quoted heredoc it never does)


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
            cur.heredoc = (cur.heredoc or "") + t.body  # read by the other checks, whatever its descriptor
            cur.expanded += "" if t.quoted else t.body
            if t.fd in ("", "0"):
                cur.stdins += 1
            else:
                cur.stdin_unseen = True  # `3<<EOF`: so stdin isn't this text
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
                on_stdin = m.group(1) in ("", "0")
                if op == "<&" and on_stdin and nxt != "0":
                    cur.stdin_unseen = True  # stdin from another descriptor, or closed
                elif op in (">&", "<&") and re.fullmatch(r"\d*-?", nxt):
                    pass  # duplicating or closing a descriptor
                elif op == "<&":
                    pass
                elif op == "<":
                    cur.inputs.append(nxt)
                    if on_stdin or cur.stdin is None:  # read by the other checks; fd 0's file comes first
                        cur.stdin = nxt
                    cur.stdins += on_stdin
                    cur.stdin_unseen = cur.stdin_unseen or not on_stdin  # `3<f`: so stdin isn't this file
                elif op == "<<<":
                    cur.heredoc = (cur.heredoc or "") + nxt
                    cur.expanded += nxt
                    cur.stdins += on_stdin
                    cur.stdin_unseen = cur.stdin_unseen or not on_stdin
                else:
                    if op == "<>" and on_stdin:  # opened for reading and writing, on stdin
                        cur.stdin = nxt
                        cur.inputs.append(nxt)
                        cur.stdins += 1
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
    fed: bool = False  # run by xargs: given file names on its stdin
    fed_file: bool = False  # xargs reads them from a file (`-a f`, `< f`), not a pipe
    match_only: bool = False  # run by find -execdir on the match alone (`rm -f {}`), which the find's own check covers
    stdins: int = 0  # how many inputs it was given on stdin (heredocs, here-strings, `<` files)
    stdin_unseen: bool = False  # stdin from another descriptor (`<&3`) or closed
    inputs: list[str] = field(default_factory=list)  # every `<` file, whatever its descriptor
    wrappers: list[str] = field(default_factory=list)  # the wrappers stripped from its words (`time`, `env`, `sudo`, …)
    expanded: str = ""  # the text of its unquoted heredocs and here-strings, which the shell expands


_KEYWORDS = {"{", "}", "!", "if", "then", "else", "elif", "fi", "do", "done", "while", "until", "esac", "coproc"}
_WRAPPERS: dict[str, set[str]] = {
    "sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U", "-T", "--chdir"},
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


def _strip_prefix(toks: list[str], wrappers: list[str] | None = None) -> tuple[list[str], list[str], str | None]:
    """(the command's words, NAME=value assignments, a directory from env -C).
    `wrappers`, when given, gets the name of each wrapper stripped (`xargs`, `sudo`, …)."""
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
            if wrappers is not None:
                wrappers.append(name)
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
                elif name == "sudo" and re.fullmatch(r"-D.+", t):
                    val, t = t[2:], "-D"
                elif name == "env" and re.fullmatch(r"-S.+", t):
                    val, t = t[2:], "-S"
                key = t.split("=", 1)[0]
                if val is not None and ((name == "env" and key in ("-C", "--chdir")) or (name == "sudo" and key in ("-D", "--chdir"))):
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
    hashes: list[int] = []
    segs = _segments_of(_lex(command, hashes=hashes)[0], root, cwd, depth)
    if hashes:  # read as zsh reads it too, each reading from the same directory
        segs += _segments_of(_lex(command, zsh=True)[0], root, cwd, depth)
    return segs


_CHANGES_DIR = ("cd", "pushd", "popd", "chdir")  # the words that move the shell, which the parser follows


def _segments_of(toks: list, root: Path, cwd: str | None, depth: int) -> list[Seg]:
    segs: list[Seg] = []
    saved: list[tuple[str | None, str | None]] = []
    dirs: list[str | None] = []
    oldpwd: str | None = None  # OLDPWD: unknown until a cd here sets it
    prev: Seg | None = None
    piped = False
    case_pattern = False  # between `case … in` / `;;` and the pattern's `)`
    held: list[tuple] = []  # the whole state at each substitution's start, which nothing inside it changes
    for item in _simple(toks):
        if isinstance(item, Op) and item.hoisted:
            if item == "(":
                held.append((cwd, oldpwd, list(saved), list(dirs), case_pattern))
                case_pattern = False  # a pattern's substitution runs as the shell tries the pattern
            elif held:  # its `)`, whatever its own text opened or closed (`` `)` ``, `$(popd)`)
                cwd, oldpwd, saved, dirs, case_pattern = held.pop()
            piped, prev = False, None
            continue
        if isinstance(item, Op):
            if case_pattern and item == ")":
                case_pattern = False
            elif case_pattern and item == "(":
                pass
            elif item == "(":
                saved.append((cwd, oldpwd))
            elif item == ")":
                if saved:
                    cwd, oldpwd = saved.pop()
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
        stripped: list[str] = []
        toks2, assigns, chdir = _strip_prefix(words, stripped)
        if toks2 and toks2[0] == "case":
            case_pattern = True
            continue
        if toks2 and toks2[0] in _CHANGES_DIR:
            if toks2[0] == "popd":
                new = dirs.pop() if dirs else None
            else:
                args = [a for a in toks2[1:] if a not in ("-P", "-L", "-e", "-@", "--")]
                new = oldpwd if args[:1] == ["-"] and toks2[0] != "pushd" else _cd_target(toks2[1:], root, cwd)
                if toks2[0] == "pushd":
                    dirs.append(cwd)
            oldpwd, cwd = cwd, new
            seg = Seg(toks2, item.redirects, cwd, item.stdin, item.heredoc, prev if piped else None, assigns, stdins=item.stdins, stdin_unseen=item.stdin_unseen, inputs=item.inputs, expanded=item.expanded)
            segs.append(seg)
            prev = seg
            continue
        seg_cwd = cwd
        if chdir is not None:
            seg_cwd = _cd_target([chdir], root, cwd)
        if not toks2 and not item.redirects and not assigns and item.stdin is None and item.heredoc is None:
            continue
        seg = Seg(toks2, item.redirects, seg_cwd, item.stdin, item.heredoc, prev if piped else None, assigns, stdins=item.stdins, stdin_unseen=item.stdin_unseen, inputs=item.inputs, wrappers=stripped, expanded=item.expanded)
        if "xargs" in stripped:
            seg.fed = True
            # A list read from a file (`-a f`, `< f`), not the pipe: anywhere in the words, to be safe.
            # xargs's own options: the words before the command, or all of them when env -S split the line
            head = words[: len(words) - len(toks2)] if words[len(words) - len(toks2) :] == toks2 else words
            seg.fed_file = bool(item.stdin or item.heredoc) or any(
                w in ("-a", "--arg-file") or w.startswith("--arg-file=") or re.fullmatch(r"-a.+", w) is not None for w in head
            )
        segs.append(seg)
        prev = seg
        segs += _nested(seg, root, depth)
    return segs


def _reread(text: str, root: Path, cwd: str | None, depth: int, words: list[str] | None = None) -> list[Seg]:
    """The commands in text another shell runs. When the outer shell may have
    expanded it first (a `$`, a backtick or a backslash in it, or one of the
    outer `words` it came from expands: a brace list or glob can open a quote),
    the quoting the lexer sees isn't the one that runs: the words lose their
    marks (`Word`), so what reads them falls back to their text."""
    segs = segments(text, root, cwd, depth + 1)
    if re.search(r"[$`\\]", text) or any(getattr(w, "splits", True) for w in words or []):
        for sg in segs:
            sg.words = [str(w) for w in sg.words]
    return segs


def _nested(seg: Seg, root: Path, depth: int) -> list[Seg]:
    toks = seg.words
    if not toks or depth >= 4:
        return []
    out: list[Seg] = []
    name = Path(toks[0]).name
    if re.search(r"\s", toks[0]):  # a whole command as one word (`watch 'git push'`)
        out += _reread(toks[0], root, seg.cwd, depth, toks[:1])
    if name in _DASH_C:
        inner = _shell_c(toks)
        if inner is not None:
            out += _reread(inner, root, seg.cwd, depth, toks)
    if name in _SHELLS and seg.heredoc and _shell_reads_stdin(toks):
        out += _reread(seg.heredoc, root, seg.cwd, depth)
    if name == "eval" and len(toks) > 1:
        out += _reread(" ".join(toks[1:]), root, seg.cwd, depth, toks[1:])
    if _INTERP.match(name):
        for lit in re.findall(r"""['"]([^'"]*\b(?:git|gh)\b[^'"]*)['"]""", _inline_code(toks)):
            out += _reread(lit, root, seg.cwd, depth)
    if name == "find":
        k = 0
        while k < len(toks):
            if toks[k] in ("-exec", "-execdir", "-ok", "-okdir"):
                j = k + 1
                while j < len(toks) and toks[j] not in (";", "+"):
                    j += 1
                sub, assigns, chdir = _strip_prefix(toks[k + 1 : j])
                if sub:
                    # -execdir runs in each match's own directory, which can't be seen here.
                    where = None if toks[k] in ("-execdir", "-okdir") else seg.cwd
                    s2 = Seg(sub, [], where, assigns=assigns)
                    if where is None and chdir is None and _only_the_match(s2, root):
                        s2.match_only = True
                    out.append(s2)
                    out += _nested(s2, root, depth + 1)
                k = j
            k += 1
    return out


def _git_dir_of(root: Path, cwd: str | None, explicit_dir: str | None) -> str | None:
    if explicit_dir:
        return _abspath(explicit_dir, cwd)
    return cwd


# Solo mode reads the same settings for many segments: while it reads one
# command, each git lookup runs once (`_solo_problem` sets and clears this).
_GIT_MEMO: dict | None = None


def _git_out(d: str | None, *args: str) -> str | None:
    if not d:
        return None
    if _GIT_MEMO is not None:
        key = (d, args)
        if key not in _GIT_MEMO:
            _GIT_MEMO[key] = _git_run(d, *args)
        return _GIT_MEMO[key]
    return _git_run(d, *args)


def _git_run(d: str, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=d, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _branch_of(d: str | None) -> str | None:
    b = _git_out(d, "rev-parse", "--abbrev-ref", "HEAD")
    return b if b and b != "HEAD" else None


def _upstream_branch(d: str | None, branch: str | None = None) -> str | None:
    """The branch name the upstream has on its remote ("claude/build-1"), or None
    when unset: of the checked-out branch, or of `branch`."""
    full = _git_out(d, "rev-parse", "--symbolic-full-name", f"{branch}@{{u}}" if branch else "@{u}")
    if not full:
        return None
    remote = _git_out(d, "config", "--get", f"branch.{branch or _branch_of(d) or ''}.remote") or ""
    m = re.match(r"^refs/remotes/(.+)$", full)
    if m:
        rest = m.group(1)
        if remote and rest.startswith(remote + "/"):
            return rest[len(remote) + 1 :]
        return rest.split("/", 1)[1] if "/" in rest else rest
    return full.removeprefix("refs/heads/")


_PUSH_CMDS = ("push", "send-pack", "http-push")
_PUSH_CONFIG = r"^(remote\..*\.(mirror|push)|remote\.pushdefault|push\.default|branch\..*\.(merge|remote|pushremote))$"
_FALSE = ("false", "no", "off", "0")


def _solo_push_settings(d: str | None, base: str, branch: str | None, remote: str | None) -> SoloRefusal | None:
    """Solo mode, a push without refspecs: whether the push settings on disk send
    it to the base branch (or every branch). Reads the repository's config in
    every scope (`git config --get-regexp`), since a session can write them.
    With no remote named, the remote is the one git picks for a bare push."""
    out = _git_out(d, "config", "--get-regexp", _PUSH_CONFIG)
    if not out:
        return None
    conf: dict[str, list[str]] = {}  # keys lowercased whole: git keeps a remote's or branch's case
    for line in out.splitlines():
        k, _, v = line.partition(" ")
        conf.setdefault(k.lower(), []).append(v.strip())

    def values(key: str) -> list[str]:
        return conf.get(key.lower(), [])

    def last(key: str) -> str:
        return (values(key) or [""])[-1]

    b = branch or ""
    r = remote or last(f"branch.{b}.pushremote") or last("remote.pushdefault") or last(f"branch.{b}.remote") or "origin"
    if any(v.lower() not in _FALSE for v in values(f"remote.{r}.mirror")):
        return SoloRefusal(f"`remote.{r}.mirror` makes every push to `{r}` a mirror of every branch, `{base}` among them")
    for spec in values(f"remote.{r}.push"):
        dst = spec.lstrip("+").split(":", 1)[-1]
        if not dst or _UNSAFE_REF.search(dst) or _dst(dst) in (base, "HEAD"):
            return SoloRefusal(f"`remote.{r}.push` (`{spec}`) sends `git push` with no branch named to `{base}`, or to branches the kit can't tell")
    default = last("push.default").lower()
    if default == "matching":
        return SoloRefusal(f"`push.default` is `matching`, so `git push` with no branch named updates every matching branch, `{base}` among them")
    if default in ("upstream", "tracking") and branch and _dst(last(f"branch.{branch}.merge")) == base:
        return SoloRefusal(f"`push.default` is `{default}` and this branch merges into `{base}`, so `git push` with no branch named updates it")
    return None


# git's own commands: never an alias (git runs the command, not an alias of that name).
_GIT_COMMANDS = {
    "add", "am", "apply", "archive", "bisect", "blame", "branch", "bundle", "cat-file", "checkout", "cherry-pick", "clean",
    "clone", "commit", "config", "describe", "diff", "fetch", "for-each-ref", "format-patch", "fsck", "gc", "grep", "help",
    "init", "log", "ls-files", "ls-remote", "ls-tree", "merge", "merge-base", "mv", "notes", "pull", "push", "rebase",
    "reflog", "remote", "reset", "restore", "rev-list", "rev-parse", "revert", "rm", "send-pack", "http-push", "shortlog",
    "show", "show-ref", "stash", "status", "submodule", "switch", "symbolic-ref", "tag", "update-ref", "var", "version", "worktree",
}  # fmt: skip
_PUSHES = re.compile(r"\b(push|send-pack|http-push)\b")


def _solo_alias(glob: list[str], args: list[str], d: str | None, elsewhere: bool) -> SoloRefusal | None:
    """Solo mode: a git alias that pushes, given with `-c` or set on disk, through
    other aliases too. `elsewhere`: the command takes git config the guard can't
    read (`--config-env`, `-c include.*`, `GIT_CONFIG*`, `HOME`), so any alias might."""
    if not args or args[0] in _GIT_COMMANDS or args[0].startswith("-"):
        return None
    name = args[0]
    if elsewhere:
        return SoloRefusal(f"`git {name}` may be an alias from config the kit can't read", "unknown")
    for _ in range(5):  # an alias of an alias …
        defs = [glob[j + 1].split("=", 1)[1] for j, g in enumerate(glob[:-1]) if g == "-c" and glob[j + 1].lower().startswith(f"alias.{name.lower()}=")]
        if not defs:
            stored = _git_out(d, "config", "--get", f"alias.{name}")
            defs = [stored] if stored else []
        if not defs:
            return None
        v = defs[-1].strip()
        if _PUSHES.search(v) or (v.startswith("!") and "$" in v and "git" in v):
            return SoloRefusal(f"the alias `git {args[0]}` runs a push, or a git command the kit can't read", "unknown")
        nxt = v.split()[0] if v and not v.startswith("!") else ""
        if not nxt or nxt in _GIT_COMMANDS:
            return None
        name = nxt
    return SoloRefusal(f"the alias `git {args[0]}` goes through too many other aliases to read", "unknown")


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
    "progress": False, "recurse-submodules": True, "verify": False, "ipv4": False, "ipv6": False,
    "stdin": False, "remote": True, "helper-status": False,
}  # fmt: skip
_PUSH_LONGS = sorted(set(_PUSH_LONG) | {"no-" + k for k in _PUSH_LONG})
_PUSH_ALWAYS_DENY = {"all", "branches", "mirror", "prune", "delete", "force", "force-with-lease", "force-if-includes"}
_UNSAFE_REF = re.compile(r"[$`*?\[{]|@")
_SOLO_UNSAFE_REF = re.compile(r"[$`*?\[{]")  # `@` alone is HEAD and `@{…}` holds a brace; `user@fix` is a name
# The current branch's name by substitution, which a refspec may use for HEAD.
_CURRENT_CMD = r"\s*git\s+(?:branch\s+--show-current|rev-parse\s+--abbrev-ref\s+HEAD|symbolic-ref\s+--short\s+HEAD)\s*"
_CURRENT_BRANCH = re.compile(rf"\$\({_CURRENT_CMD}\)|`{_CURRENT_CMD}`")


def _unsafe_kind(ref: str) -> str:
    """What makes a destination unreadable, in a few words."""
    if "$" in ref or "`" in ref:
        return "a variable or a command's output"
    if "@" in ref:
        return "`@`, which names a branch the kit can't see"
    if "{" in ref:
        return "a brace list"
    return "a glob"


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


_PUSH_EVERY = {"all", "branches", "mirror"}


def _push_problem(
    args: list[str], base: str, branch: str | None, role: str, ticket_pat: str, upstream=None, solo: bool = False, settings=None
) -> str | SoloRefusal | None:
    """`args` starts with push, send-pack or http-push. `upstream` is called for
    a push without refspecs and returns the upstream's branch name or None;
    in solo mode `settings` is called for one too, with the remote given (or
    None), and returns a `SoloRefusal` when the push settings send it to the base branch.

    In solo mode (`solo`, attended only) what touches the base branch, or might,
    comes back as a `SoloRefusal`; a force-push or deletion is read with its
    destinations, so one of a named feature branch is still only asked."""
    kind = args[0]
    rest = args[1:]
    pos: list[str] = []
    i = 0
    dry = False
    tags = False
    only_pos = False
    # Solo mode: a force or delete, judged by its destinations. An option forces
    # every destination; a refspec's `+` or `:` only its own.
    forced_msg: str | None = None
    force_all = False
    forced_dsts: set[str] = set()
    prune = False  # solo mode: `--prune` deletes what its refspecs' destinations don't hold
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
                    if solo:
                        if "stdin" in bad:
                            return SoloRefusal(f"`{a}` could mean `--stdin`, which reads the branches where the kit can't see them; spell the option out", "unknown")
                        every = [c for c in bad if c in _PUSH_EVERY]
                        if every:
                            return SoloRefusal(f"`{a}` could mean `--{every[0]}`, which pushes every branch; spell the option out")
                        if any(c in _PUSH_ALWAYS_DENY for c in bad):  # a force or delete: judged by its destinations
                            forced_msg, force_all = forced_msg or f"`git {kind} {a}` is ambiguous and could mean --{bad[0]}; spell the option out", True
                        i += 1
                        continue
                    return f"`git {kind} {a}` is ambiguous and could mean --{bad[0]}; spell the option out"
            elif name in _PUSH_ALWAYS_DENY:
                msg = f"`git {kind} --{name}` is never allowed (force-push, delete, mirror or push-all)"
                if not solo:
                    return msg
                if name in _PUSH_EVERY:
                    return SoloRefusal(f"`--{name}` pushes every branch, `{base}` among them")
                if name == "prune":
                    prune = True
                forced_msg, force_all = forced_msg or msg, True
            elif name in ("tags", "follow-tags"):
                tags = True
            elif name == "stdin":
                if solo:
                    return SoloRefusal("`--stdin` reads the branches where the kit can't see them", "unknown")
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
                    msg = f"`git {kind} -f` (force-push) is never allowed"
                    if not solo:
                        return msg
                    forced_msg, force_all = forced_msg or msg, True
                if ch in "dD":
                    msg = f"`git {kind} -{ch}` deletes a branch, which is never allowed"
                    if not solo:
                        return msg
                    forced_msg, force_all = forced_msg or msg, True
                if ch == "n":
                    dry = True
                if ch == "o":
                    if k == len(cluster) - 1:
                        i += 1
                    break
        i += 1
    if dry:
        return forced_msg  # a dry run changes nothing (a forced one is still asked, as before)
    if role == "ticket" and tags:
        return "ticket sessions don't push tags (`--tags`, `--follow-tags`); push your branch by name"
    refspecs = [_CURRENT_BRANCH.sub("HEAD", r) for r in pos[1:]]
    dsts: list[str] = []
    for r in refspecs:
        this_forced = False
        if r.startswith("+"):
            msg = f"`git push {r}` is a force-push (a leading +), which is never allowed"
            if not solo:
                return msg
            forced_msg, this_forced = forced_msg or msg, True
            r = r[1:]
        if r.startswith(":"):
            msg = f"`git push {r}` deletes a branch (or pushes every matching one), which is never allowed"
            if not solo:
                return msg
            if r == ":":
                return SoloRefusal(f"a bare `:` pushes every matching branch, `{base}` among them")
            forced_msg, this_forced = forced_msg or msg, True
        raw_dst = r.rpartition(":")[2]  # git splits a refspec at its last `:`
        if (role != "attended" or solo) and raw_dst not in ("@", "HEAD") and (_SOLO_UNSAFE_REF if solo else _UNSAFE_REF).search(raw_dst):
            if solo:
                return SoloRefusal(f"the branch {_code_span(raw_dst)} is {_unsafe_kind(raw_dst)}", "unknown")
            return f"can't tell which branch `{raw_dst}` is (a variable, `@`, a glob or a brace list); push your branch by name"
        if role == "ticket" and (raw_dst.startswith(("refs/tags/", "tags/")) or r.startswith("refs/tags/")):
            return f"ticket sessions don't push tags (`{r}`); push your branch by name"
        d = _dst(raw_dst)
        dsts.append((branch or "?") if d in ("HEAD", "@") else d)
        if this_forced:
            forced_dsts.add(dsts[-1])
    if not refspecs:
        if kind != "push":
            if solo:
                return SoloRefusal(f"`git {kind}` without refs pushes every matching branch, `{base}` among them")
            return f"`git {kind}` without refs pushes every matching branch; name the branch"
        dsts = [branch or "?"]
        if solo and prune and not tags:  # with --tags it prunes only tags
            return SoloRefusal(f"`--prune` with no branch named can delete every branch the remote has and this one doesn't, `{base}` among them")
        up = upstream() if upstream else None
        if up and up == base:
            if solo:
                if branch and branch != base:
                    return SoloRefusal(f"this branch's upstream is `{base}`, so `git push` with no branch named updates it")
                return SoloRefusal(f"`git push` with no branch named, from `{base}`, updates `{base}`")
            return f"this branch's upstream is the base branch `{base}`, so a bare push would update it; push the branch by name: `git push origin {branch or '<branch>'}`"
        if solo and settings:
            refusal = settings(pos[0] if pos else None)
            if refusal:
                return refusal
        if role == "ticket" and up and branch and up != branch:
            return f"this branch's upstream is `{up}`, not `{branch}`, so a bare push would update another branch; push it by name: `git push origin {branch}`"
    for d in dsts:
        if d == base:
            if solo:
                return SoloRefusal(f"a force-push or deletion of `{base}`" if force_all or d in forced_dsts else f"a push to `{base}`")
            return f"pushing to the base branch `{base}` is never allowed: open a pull request"
    if solo:
        if "?" in dsts:
            return SoloRefusal("a detached HEAD, a directory the kit can't follow, or a switch of branch it can't read", "unknown")
        return forced_msg
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


# Settings that make a push mirror every ref (force-updating and deleting
# branches), skip a remote, or send a bare push elsewhere: checked in every role.
_MIRROR_KEYS = r"remote\..*\.(mirror|skipdefaultupdate)\b|remote\.pushdefault\b"
_MIRROR_SETTINGS = re.compile(rf"(?i)^({_MIRROR_KEYS})")
_PUSH_SETTINGS = re.compile(
    rf"(?i)^(alias\.|remote\.[^=]*\.(push|pushurl|url)\b|{_MIRROR_KEYS}|push\.|branch\.[^=]*\.(merge|remote|pushremote)\b|url\.)"
)
_INJECT_KEYS = re.compile(
    rf"(?i)^(alias\.|remote\..*\.(push|pushurl|url)\b|{_MIRROR_KEYS}|push\.|branch\..*\.(merge|remote|pushremote)\b|url\.|"
    r"core\.(fsmonitor|sshcommand|hookspath|pager|editor|askpass|gitproxy)\b|credential\.|include\.|includeif\.|"
    r"sequence\.editor\b|diff\.external\b|diff\..*\.(command|textconv)\b|merge\..*\.driver\b|filter\.|(diff|merge)tool\..*\.(cmd|path)\b|gpg\.(.*\.)?program\b|gpg\.ssh\.defaultkeycommand\b)"
)
_INJECT_ENV = re.compile(
    r"^(GIT_CONFIG\w*|GIT_SSH\w*|GIT_EXEC_PATH|GIT_DIR|GIT_WORK_TREE|GIT_EDITOR|GIT_SEQUENCE_EDITOR|GIT_EXTERNAL_DIFF|GIT_ASKPASS|GIT_PAGER|EDITOR|VISUAL)\+?="
)
# git subcommands that run a program the guard never sees.
_GIT_RUNS = {"bisect": {"run"}, "submodule": {"foreach"}, "filter-branch": None, "difftool": None, "mergetool": None}
_CONFIG_VALUE_OPTS = {"-f", "--file", "--blob", "--type", "--default", "--comment", "--value", "-t"}
_CONFIG_WRITE_OPTS = {"--unset", "--unset-all", "--add", "--replace-all", "--rename-section", "--remove-section", "--edit", "-e"}


def _env_problem(seg: Seg, role: str) -> str | None:
    if role not in ("ticket", "conductor"):
        return None
    names = list(seg.assigns)
    if seg.words and seg.words[0] in ("export", "declare", "typeset", "local", "readonly"):
        names += [w for w in seg.words[1:] if not w.startswith("-")]
    for a in names:
        if re.fullmatch(r"(GIT_EDITOR|GIT_SEQUENCE_EDITOR|EDITOR|VISUAL)=(true|:|cat|)|GIT_PAGER=(cat|less|more|)|GIT_ASKPASS=(true|)", a):
            continue  # a program that does nothing here: `GIT_EDITOR=true git rebase --continue`, `GIT_PAGER=cat`
        m = _INJECT_ENV.match(a) or re.fullmatch(r"(GIT_CONFIG\w*|GIT_SSH\w*|GIT_EXEC_PATH|GIT_DIR|GIT_WORK_TREE)", a)
        if m:
            name = a.split("=", 1)[0].rstrip("+")
            what = "names a program to run" if name in ("EDITOR", "VISUAL") else "can point git at other config, programs or repositories"
            return f"setting `{name}` {what}; it's not allowed in {role} sessions (a no-op value such as `true` or `cat` is fine)"
        if role == "ticket" and re.match(r"(GH_REPO|GH_HOST|GH_ENTERPRISE_TOKEN|GITHUB_ENTERPRISE_TOKEN|GH_TOKEN|GITHUB_TOKEN|GH_CONFIG_DIR)(\+?=|$)", a):
            return f"setting `{a.split('=', 1)[0].rstrip('+')}` points gh at another repository, host or account; ticket sessions work only in this repository"
    return None


def _git_config_problem(glob: list[str], args: list[str], role: str, solo: bool = False) -> str | SoloRefusal | None:
    """In solo mode (`solo`, attended only) a mirror setting, a push setting on a
    push, or a write of `push.default` or a remote's push refspecs, comes back
    as a `SoloRefusal`."""
    firm = role in ("ticket", "conductor")
    for j, g in enumerate(glob):
        if g == "-c" and j + 1 < len(glob):
            key = glob[j + 1]
            pushes = bool(args) and args[0] in _PUSH_CMDS
            if solo and pushes and re.match(r"(?i)include(if)?\.", key):
                return SoloRefusal(f"`git -c {key}` reads config the kit can't see into the push", "unknown")
            if (_INJECT_KEYS if firm else _PUSH_SETTINGS).match(key):
                if solo and re.match(r"(?i)remote\.pushdefault\b", key):
                    return SoloRefusal(f"`git -c {key}` sends the push to another remote", "unknown")
                if solo and _MIRROR_SETTINGS.match(key):
                    return SoloRefusal(f"`git -c {key}` makes the push mirror every branch or go elsewhere")
                if solo and pushes:
                    return SoloRefusal(f"`git -c {key}` changes where the push goes", "unknown")
                return f"`git -c {key}` can redirect a push or run a program; set no aliases, push, remote, credential or command settings"
        if solo and (g == "--config-env" or g.startswith("--config-env=")) and args[:1] and args[0] in _PUSH_CMDS:
            return SoloRefusal("`git --config-env` sets the push's config from the environment", "unknown")
        if firm and (g == "--config-env" or g.startswith("--config-env=")):
            return "`git --config-env` sets config from the environment, which isn't allowed here"
        if firm and g.startswith("--exec-path="):
            return "`git --exec-path=…` runs git's programs from elsewhere, which isn't allowed here"
    if not args:
        return None
    if args[0] == "remote" and len(args) > 1 and args[1] == "set-url" and role == "ticket":
        return "ticket sessions don't change where a remote points (`git remote set-url`)"
    if args[0] == "remote" and len(args) > 1 and args[1] == "add" and any(a == "--mirror" or a.startswith("--mirror=") for a in args[2:]):
        if solo:
            return SoloRefusal("`git remote add --mirror` makes every push to that remote a mirror of every branch", "setting")
        return "`git remote add --mirror` makes every push to that remote a mirror (force-updating and deleting branches), which is never allowed"
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
        return "`git config --edit` changes the config by hand, which isn't allowed here" if firm else None
    key = positional[0]
    unset = any(t in ("--unset", "--unset-all", "unset") for t in rest)  # takes a setting away: sends no push anywhere new
    if _MIRROR_SETTINGS.match(key) or _MIRROR_SETTINGS.match(key + "."):
        if solo and not unset:
            return SoloRefusal(f"`git config {key}` makes pushes mirror every branch or go elsewhere", "setting")
        return f"`git config {key}` makes pushes mirror every branch (force-updating and deleting them) or go elsewhere, which is never allowed"
    if firm and (_INJECT_KEYS.match(key) or _INJECT_KEYS.match(key + ".")):
        return f"`git config {key}` can redirect a push or run a program; {role} sessions don't change it"
    if solo and not unset:
        value = positional[1].lower() if len(positional) > 1 else ""
        if key.lower() == "push.default" and value not in ("simple", "current", "nothing"):
            what = "every matching branch" if value == "matching" else "the branch it tracks"
            return SoloRefusal(f"`git config push.default {value or '…'}` can make `git push` with no branch named update {what}", "setting")
        if re.fullmatch(r"(?i)remote\..*\.push", key):
            return SoloRefusal(f"`git config {key}` sets where every `git push` to that remote goes when no branch is named", "setting")
        raw = positional[1] if len(positional) > 1 else ""
        if key.lower().startswith("alias.") and (_PUSHES.search(raw) or (raw.startswith("!") and "$" in raw and "git" in raw)):
            return SoloRefusal(f"`git config {key}` makes an alias that pushes", "setting")
    return None


_CREATE_OPTS = ("-b", "-B", "-c", "-C", "--orphan")


def _previous_branch(d: str | None) -> str | None:
    full = _git_out(d, "rev-parse", "--symbolic-full-name", "@{-1}")
    return full.removeprefix("refs/heads/") if full and full.startswith("refs/heads/") else None


def _switch_target(x: str, d: str | None, kind: str) -> tuple[str, str | None]:
    """What `git checkout|switch x` does: ("branch", name), ("detach", None),
    ("unknown", None) or ("none", None) when it isn't a switch (a path)."""
    if x in ("-", "@{-1}"):
        prev = _previous_branch(d)
        return ("branch", prev) if prev else ("unknown", None)
    if x in ("HEAD", "@"):
        return "none", None
    if d is None:
        return ("branch", x) if kind == "switch" else ("none", None)
    if _git_out(d, "rev-parse", "--verify", "-q", f"refs/heads/{x}"):
        return "branch", x
    if kind == "checkout" and _git_out(d, "rev-parse", "--verify", "-q", f"{x}^{{commit}}"):
        return "detach", None
    for remote in (_git_out(d, "remote") or "").split():
        if _git_out(d, "rev-parse", "--verify", "-q", f"refs/remotes/{remote}/{x}"):
            return "branch", x  # git's guess: a new local branch tracking it
    return ("branch", x) if kind == "switch" else ("none", None)


def _switch_problem(args: list[str], ticket_pat: str, d: str | None = None) -> str | None:
    """A ticket session whose role comes from its branch name stays on a ticket
    branch: no switching, detaching or renaming away from one."""
    if not args:
        return None
    stay = f"this is a ticket session by its branch name; stay on a `{ticket_pat}` branch"
    rest = args[1:]
    if args[0] == "branch":
        if any(a in ("-m", "-M", "--move") or re.fullmatch(r"-[a-zA-Z]*[mM][a-zA-Z]*", a) for a in rest):
            plain = [a for a in rest if not a.startswith("-")]
            if plain and not fnmatch.fnmatchcase(plain[-1], ticket_pat):
                return f"{stay} (`git branch -m` renames it to `{plain[-1]}`)"
        return None
    if args[0] not in ("checkout", "switch"):
        return None
    created = False
    for k, a in enumerate(rest):
        tgt = None
        if a in _CREATE_OPTS and k + 1 < len(rest):
            tgt = rest[k + 1]
        elif a.startswith("--orphan="):
            tgt = a.split("=", 1)[1]
        elif re.fullmatch(r"-[bBcC].+", a):
            tgt = a[2:]
        if tgt is not None:
            created = True
            if not fnmatch.fnmatchcase(tgt, ticket_pat):
                return f"{stay} (not `{tgt}`)"
    if any(a == "--detach" or (args[0] == "switch" and a == "-d") for a in rest):
        return f"{stay}: `--detach` leaves it"
    if created:
        return None
    if any(a in ("-t", "--track") or a.startswith("--track=") for a in rest):
        plain = [a for a in rest if not a.startswith("-")]
        if plain:  # a new branch named after the remote one
            remotes = (_git_out(d, "remote") or "origin").split()
            first, _, after = _dst(plain[0]).removeprefix("remotes/").partition("/")
            name = after if after and first in remotes else plain[0]
            return None if fnmatch.fnmatchcase(name, ticket_pat) else f"{stay} (not `{name}`)"
    skip = set(_opt_values(["x", *rest], ("--pathspec-from-file", "--conflict")))
    if "--" in rest:
        k = rest.index("--")
        if rest[k + 1 :]:
            return None  # paths
        rest = rest[:k]
    plain = [a for a in rest if (a == "-" or not a.startswith("-")) and a not in skip]
    if not plain or (args[0] == "checkout" and len(plain) != 1):
        return None
    what, name = _switch_target(plain[0], d, args[0])
    if what == "none":
        return None
    if what == "detach":
        return f"{stay}: `git {args[0]} {plain[0]}` would detach HEAD at a commit (a tag, a remote branch or a revision)"
    if what == "unknown" or not name:
        return f"{stay}: can't tell which branch `git {args[0]} {plain[0]}` switches to"
    if not fnmatch.fnmatchcase(name, ticket_pat):
        return f"{stay} (not `{name}`)"
    return None


def _upstream_problem(args: list[str], d: str | None, branch: str | None) -> str | None:
    """`git branch -u`/`--set-upstream-to` in a ticket session: only to a branch of
    the same name, so a bare push never updates another branch."""
    if args[:1] != ["branch"]:
        return None
    val: str | None = None
    names: list[str] = []
    rest = args[1:]
    i = 0
    while i < len(rest):
        a = rest[i]
        if a in ("-u", "--set-upstream-to"):
            val = rest[i + 1] if i + 1 < len(rest) else ""
            i += 2
            continue
        if a.startswith("--set-upstream-to="):
            val = a.split("=", 1)[1]
        elif re.fullmatch(r"-u.+", a):
            val = a[2:]
        elif not a.startswith("-"):
            names.append(a)
        i += 1
    if val is None:
        return None
    target = names[0] if names else branch
    up = val
    first, _, after = val.partition("/")
    remotes = (_git_out(d, "remote") or "origin").split()
    if after and first in remotes:
        up = after
    up = _dst(up)
    if not target or up != target:
        return (
            f"a ticket branch's upstream must be the branch of its own name (`{target or '?'}`), not `{val}`: "
            "a bare push would update that branch"
        )
    return None


# ---------- GitHub CLI and API ----------

def _repo_name(r: str) -> str:
    """OWNER/REPO from the forms gh takes (`[HOST/]OWNER/REPO`, a URL, `.git`), in lower case."""
    # What gh reads: up to whitespace, a query or a fragment.
    r = re.split(r"[\s?#]", r.strip(), maxsplit=1)[0]
    r = re.sub(r"^(?:https?://|ssh://|git@)", "", r, flags=re.I).rstrip("/")
    r = re.sub(r"\.git$", "", r)
    r = re.sub(r"^github\.com[:/]", "", r, flags=re.I)
    return r.casefold()


# A shell function's or script's parameters, whose values the guard never sees.
_HEREDOC_HINT = "(`-m \"$(cat <<'EOF'` … `EOF` `)\"`)"
_POSITIONAL = re.compile(r"\$(?:[@*#0-9]|\{[!#]?[@*0-9])")

def _literal_heredoc(word: str) -> bool:
    """The word is exactly `$(cat <<'EOF' … EOF)` with a quoted delimiter: the
    shell substitutes the heredoc's text as written, expanding nothing, so a
    `$1` or `-R` in it is only text (the usual way to pass a commit message or
    a PR body)."""
    m = re.match(r"\$\(\s*cat\s+<<(-?)\s*(['\"])([A-Za-z_][\w.-]*)\2[ \t]*\n", word)
    if not m:
        return False
    lines = word[m.end():].split("\n")
    delim = m.group(3)
    for k, line in enumerate(lines):
        bare = line.lstrip("\t") if m.group(1) else line
        # The first line that is the delimiter, or starts with it and `)`, ends
        # the heredoc (bash's rule inside `$( )`); only a bare `)` may follow.
        if bare == delim:
            return "\n".join(lines[k + 1:]).strip() == ")"
        if bare.startswith(delim) and ")" in bare[len(delim):]:
            return bare == delim + ")" and not "\n".join(lines[k + 1:]).strip()
    return False

# `gh` subcommands a ticket session may run (None: any).
_GH_TICKET: dict[str, set[str] | None] = {
    "pr": {"create", "new", "edit", "comment", "view", "checks", "list", "ls", "diff", "ready", "merge", "status", "close"},
    "issue": {"view", "comment", "edit", "list", "ls", "create", "new", "status", "close", "reopen"},
    "run": {"view", "list", "ls", "rerun", "watch", "download", "cancel"},
    "workflow": {"list", "ls", "view"},
    "status": None,
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
    r"pulls/\d+/(merge|merge-async|reviews|comments|requested_reviewers|update-branch|ccr/auto_merge)",
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
    word: str = ""  # the path as written


_STDIN_RE = re.compile(r"-|/dev/stdin|/dev/fd/0|/proc/(?:self|thread-self|\d+|\$\$|\$BASHPID)/fd/0")


class _StdinFile:
    """The spellings of stdin as a file name, after normalising the path."""

    @staticmethod
    def fullmatch(f: str) -> bool:
        if f == "-":
            return True
        n = posixpath.normpath(re.sub(r"/+", "/", f)) if f.startswith("/") else f
        return bool(_STDIN_RE.fullmatch(n))


_STDIN_FILE = _StdinFile


# `gh api`'s options whose value is the next word, whatever it holds (`-X`,
# `--method`, `--input` and the field flags are read on their own).
_API_VALUES = {"-H", "--header", "-q", "--jq", "-t", "--template", "--hostname", "--cache", "-p", "--preview"}


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
        # gh reads `-i` (--include, a boolean) and the short flag after it as one
        # word (`-ifquery=…`, `-iX POST`), and a short flag's value after `=` (`-f=v`).
        bundled = re.fullmatch(r"-i+([fFXHqtp].*)", t)
        if bundled:
            t = "-" + bundled.group(1)
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
            val = t[3:] if t[2] == "=" else t[2:]
            i += 1
        if val is not None:
            fields.append(val)
            if (t.startswith("-F") or t.startswith("--field")) and "=@" in val:
                f = val.split("=@", 1)[1]
                if _STDIN_FILE.fullmatch(f):
                    stdin = True
                else:
                    files.append(f)
            continue
        if t == "--input" or t.startswith("--input="):
            f = t.split("=", 1)[1] if "=" in t else (toks[i + 1] if i + 1 < len(toks) else "")
            i += 1 if "=" in t else 2
            if _STDIN_FILE.fullmatch(f):
                stdin = True
            elif f:
                files.append(f)
            continue
        if t in _API_VALUES:
            i += 2
            continue
        if not t.startswith("-") and path is None:
            path = t
        i += 1
    has_body = bool(fields) or bool(files) or stdin
    method = (method or ("POST" if has_body else "GET")).upper()
    p = re.sub(r"^https?://[^/]+/(api/v3/)?", "", path or "").lstrip("/").split("?", 1)[0].rstrip("/")
    return _ApiCall(method, p, " ".join(toks[start:]), fields, files, stdin, path or "")


def _field_values(call: _ApiCall, name: str) -> list[str]:
    """Every value the call gives the field `name` (gh sends the last)."""
    return [f.split("=", 1)[1] if "=" in f else "" for f in call.fields if f.split("=", 1)[0] == name]


def _field(call: _ApiCall, name: str) -> str | None:
    for f in call.fields:
        if f.split("=", 1)[0] == name:
            return f.split("=", 1)[1] if "=" in f else ""
    return None


def _read_text(path: str, cwd: str | None, limit: int = 1_000_000) -> str | None:
    """A regular file's text (never a device or pipe, which could block)."""
    return _read_sized(path, cwd, limit)[0]


def _read_capped(path: str, cwd: str | None, cap: int) -> tuple[str | None, bool]:
    """A regular file's text, at most `cap` bytes of it, and whether it holds more."""
    text, _, over = _read_sized(path, cwd, cap)
    return text, over


def _read_sized(path: str, cwd: str | None, cap: int) -> tuple[str | None, int, bool]:
    """A regular file's text (at most `cap` bytes), the bytes read, and whether it holds more."""
    if path == os.devnull:  # as written: `/dev/fd/0` can resolve to it here and be something else when it runs
        return "", 0, False
    written = os.path.expanduser(path)
    if not written.startswith("/") and cwd:
        written = cwd + "/" + written
    if posixpath.normpath(re.sub("/+", "/", written)).startswith(("/dev/", "/proc/")):
        return None, 0, False  # a descriptor or device: what it holds when the command runs isn't here
    a = _abspath(path, cwd)
    if not a or not os.path.isfile(a):
        return None, 0, False
    try:
        with open(a, "rb") as fh:
            data = fh.read(max(cap, 0) + 1)
    except OSError:
        return None, 0, False
    return data[:cap].decode("utf-8", "replace"), min(len(data), max(cap, 0)), len(data) > cap


def _gql_plain(text: str) -> str | None:
    """GraphQL text with every string emptied (`""`) and its ignored tokens
    (comments, commas) made spaces, read in one linear pass as GraphQL's lexer
    reads it: a quote in a comment, a `#` in a string, and a backslash before
    three quotes in a block string (an escaped quote) stay where they are.
    None for an unterminated string."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith('"""', i):
            j = i + 3
            while True:
                k = text.find('"""', j)
                if k < 0:
                    return None
                if text[k - 1] == "\\" and k - 1 >= j:  # \""" is an escaped quote
                    j = k + 3
                    continue
                break
            out.append('""')
            i = k + 3
        elif c == '"':
            j = i + 1
            while j < n and text[j] not in '"\n\r':
                j += 2 if text[j] == "\\" else 1
            if j >= n or text[j] != '"':
                return None
            out.append('""')
            i = j + 1
        elif c == "#":
            j = i
            while j < n and text[j] not in "\n\r":
                j += 1
            out.append(" ")
            i = j
        elif c == ",":
            out.append(" ")
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


_GQL_NAME = re.compile(r"[A-Za-z_]\w*")
_GQL_ALIAS = re.compile(r"\s*:\s*([A-Za-z_]\w*)?")


def _mutation_calls(text: str) -> list[tuple[str, str]] | None:
    """(field, its arguments) for each top-level field of each GraphQL mutation
    in text, string values emptied (`body:""`); None if unreadable. The
    selection set after the arguments isn't part of them. GraphQL's ignored
    tokens (comments, commas) are dropped first, and the operation's variable
    definitions, whose default values can hold a body, join every field's
    arguments."""
    t = _gql_plain(text)
    if t is None:
        return None
    out: list[tuple[str, str]] = []
    done = 0  # where the last operation read ended: a `mutation` before it was read with it
    for m in re.finditer(r"\bmutation\b", t):
        if m.start() < done:
            continue
        i, n = m.end(), len(t)
        paren = 0
        while i < n and not (t[i] == "{" and paren == 0):
            paren += {"(": 1, ")": -1}.get(t[i], 0)
            i += 1
        if i >= n:
            return None
        header = t[m.end() : i]
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
            elif depth == 1 and t.startswith("...", i):
                return None  # a fragment on Mutation: its fields can't be read here
            elif depth == 1 and (c.isalpha() or c == "_"):
                mm = _GQL_NAME.match(t, i)
                if not mm:
                    return None  # a name GraphQL doesn't allow
                ident = mm.group(0)
                i = mm.end()
                colon = _GQL_ALIAS.match(t, i)
                if colon:
                    if not colon.group(1):
                        return None
                    ident = colon.group(1)
                    i = colon.end()
                j = i
                while j < n and t[j].isspace():
                    j += 1
                args = ""
                if j < n and t[j] == "(":
                    p, k = 1, j + 1
                    while k < n and p:
                        p += {"(": 1, ")": -1}.get(t[k], 0)
                        k += 1
                    if p:
                        return None
                    args, i = t[j + 1 : k - 1], k
                out.append((ident, f"{args} {header}" if header.strip() else args))
                continue
            i += 1
        done = i
    return out


def _gh_problem(toks: list[str], profile: Profile, role: str, cwd: str | None, raw: str, read=None) -> str | None:
    """Problems with a `gh` command (toks start at the gh word)."""
    group, sub = _gh_group(toks)
    if group == "pr" and sub == "merge" and any(t == "--admin" or t.startswith("--admin=") for t in toks):
        return "`gh pr merge --admin` bypasses the base branch's required checks; it is never allowed"
    if group == "repo" and sub == "edit" and any(t == "--default-branch" or t.startswith("--default-branch=") for t in toks):
        return "changing the repository's default branch (`gh repo edit --default-branch`) is never allowed"
    if role == "ticket":
        for j, t in enumerate(toks):
            if _literal_heredoc(t):  # text the shell never expands: a title, a body
                continue
            r = None
            if t == "--repo" or t.startswith("--repo="):
                r = t.split("=", 1)[1] if "=" in t else toks[j + 1] if j + 1 < len(toks) else ""
            else:
                # `-R x`, `-Rx`, `-R=x`, and bundled after boolean shorts (`-mR x`).
                m = re.fullmatch(r"-[a-zA-Z]*?R(.*)", t, re.S)
                if m:
                    r = m.group(1).removeprefix("=") or (toks[j + 1] if j + 1 < len(toks) else "")
            if r is None:
                # A pull request or issue URL names its own repository, which gh then uses.
                u = re.match(r"(?:https?://)?(?:[^/\s]*@)?(?:[\w-]+\.)*github\.com\.?(?::\d*)?/([^/\s]+/[^/\s]+)/(?:pull|issues)/", t, re.I)
                r = u.group(1) if u else None
            if r is not None and re.search(r"[$`]", r):
                return f"ticket sessions name a repository only literally; `{t}` is filled in by the shell"
            if r is not None and _repo_name(r) != profile.repo.casefold():
                return f"ticket sessions work only in {profile.repo}; `{t}` names another repository (text that starts with one, as a title or body may, goes in a quoted heredoc)"
    if role == "ticket" and group == "auth" and any(t in ("-t", "--show-token") or t.startswith(("--show-token=", "-t=")) or re.fullmatch(r"-[a-zA-Z]*t[a-zA-Z]*", t) for t in toks[2:]):
        return "`gh auth status --show-token` prints the GitHub token; ticket sessions never read it"
    if role == "ticket" and group is not None and not group.startswith("-"):
        allowed = _GH_TICKET.get(group, set())
        if group not in _GH_TICKET or (allowed is not None and sub not in allowed and sub is not None):
            what = f"gh {group}" + (f" {sub}" if sub else "")
            return f"`{what}` isn't something a ticket session runs; ticket sessions use gh only for pull requests, issues, runs, `gh api` and reads"
    return _api_problem(toks, profile, role, cwd, raw, read)


def _api_problem(toks: list[str], profile: Profile, role: str, cwd: str | None = None, raw: str = "", read=None) -> str | None:
    """`read`, when given, returns the text of the files the whole command reads
    with `cat` or `<`, which a query or body may come from by a variable."""
    base = profile.base_branch
    name = Path(toks[0]).name if toks else ""
    # An attended session's curl that reads a config file (`-K`) may name GitHub
    # there, and one whose URL names `merge-async` may have its host filled in.
    queue = role == "attended" and (_curl_configs(toks) or any(_curl_url_queues(t) for t in toks))
    if name == "curl" and (re.search(r"(?:api|uploads)\.github\.com|/api/v3/|/api/graphql", " ".join(toks), re.I) or queue):
        joined = f" {' '.join(toks)} "
        # A short flag may carry its value joined (`-dX`, `-Tq.json`, `-Kcfg`); a
        # config file (`-K`) can hold any of them.
        writes = (
            re.search(r"\s(-[a-zA-Z]*X|--req\w*)[\s=]*(POST|PUT|PATCH|DELETE)\b", joined, re.I)
            or re.search(r"\s(--data[\w-]*|--expand-[\w-]+|--form[\w-]*|--upl[\w-]*|--jso\w*|--conf\w*)[\s=]", joined)
            or re.search(r"\s-[a-zA-Z]*[dFTK]", joined)
        )
        if writes and role != "attended":
            return "GitHub writes go through `gh api` or the GitHub MCP tools, not curl"
        if writes:
            return _curl_queue_problem(toks, joined, cwd)
        return None
    call = _api(toks)
    if not call:
        return None
    path = call.path
    if path == "graphql":
        if role == "ticket":
            # The shell can assemble a query in more ways than any reading of the
            # command can follow (expansions, globs, xargs), and ticket sessions
            # need none: auto-merge, comments and reads have MCP tools and REST.
            return "ticket sessions don't use GitHub's GraphQL API; use the GitHub MCP tools (`enable_pr_auto_merge`, `add_issue_comment`, the read tools) or REST"
        # The whole command and every file it reads: the query may be in a variable.
        text = call.rest + "\n" + raw
        for f in call.files:
            text += "\n" + (_read_text(f, cwd) or "")
        if read is not None:
            text += "\n" + read()
        if _DANGEROUS_GQL.search(text):
            return "this GraphQL mutation rewrites refs, branches, protection or rulesets, which is never allowed"
        return None
    if call.method == "GET":
        return None
    if re.search(rf"(^|/)git/refs/heads/{re.escape(base)}$", path) or re.search(r"/branches/[^/]+/protection|/rulesets\b", path):
        return f"rewriting the base branch `{base}`, its protection or rulesets through the API is never allowed"
    if re.search(rf"(^|/)branches/{re.escape(base)}/rename$", path):
        return f"renaming the base branch `{base}` through the API is never allowed"
    if re.fullmatch(r"repos/[^/]+/[^/]+", path):
        body = call.rest + "".join("\n" + (_read_text(f, cwd) or "") for f in call.files)
        if call.stdin:
            body += "\n" + raw + ("\n" + read() if read is not None else "")
        if _field(call, "default_branch") is not None or re.search(r"default(?:_|\\u005f)branch", body, re.I):
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


# Posts that create text on GitHub, which an agent marks with AGENT_MARKER.
# `gh` subcommands that always post text, and those that do when given a body or comment.
_GH_TEXT_ALWAYS = {("issue", "create"), ("issue", "new"), ("issue", "comment"), ("pr", "create"), ("pr", "new"), ("pr", "comment")}
_GH_TEXT_WITH = {
    ("issue", "edit"): ("-b", "--body", "-F", "--body-file"),
    ("pr", "edit"): ("-b", "--body", "-F", "--body-file"),
    ("pr", "review"): ("-b", "--body", "-F", "--body-file"),
    ("issue", "close"): ("-c", "--comment"),
    ("pr", "close"): ("-c", "--comment"),
    ("issue", "reopen"): ("-c", "--comment"),
    ("pr", "reopen"): ("-c", "--comment"),
}
_GH_COMMENT_BODY = ("-b", "--body", "-F", "--body-file")
# REST endpoints (after repos/<owner>/<repo>/) that always post text, and those that do with a body.
_API_TEXT_ALWAYS = [
    r"issues",
    r"pulls",
    r"issues/\d+/comments",
    r"pulls/\d+/comments",
    r"pulls/(?:\d+/)?comments/\d+/replies",
    r"commits/[0-9a-f]+/comments",
]
_API_TEXT_WITH_BODY = [
    r"issues/\d+",
    r"issues/comments/\d+",
    r"comments/\d+",
    r"pulls/\d+",
    r"pulls/comments/\d+",
    r"pulls/\d+/reviews",
    r"pulls/\d+/reviews/\d+(?:/events)?",
]
_GQL_TEXT_ALWAYS = {"addComment", "createIssue", "createPullRequest", "addPullRequestReviewComment", "addPullRequestReviewThreadReply"}
_GQL_TEXT_WITH_BODY = {"updateIssue", "updateIssueComment", "updatePullRequest", "addPullRequestReview", "submitPullRequestReview", "updatePullRequestReview"}
# GitHub MCP tools that always post text, and those that do when given a body.
_MCP_TEXT_ALWAYS = {
    "add_issue_comment",
    "create_issue",
    "create_pull_request",
    "add_comment_to_pending_review",
    "add_reply_to_pull_request_comment",
    "add_pull_request_review_comment",
    "update_issue_comment",
}
_MCP_TEXT_WITH_BODY = {
    "issue_write",
    "update_issue",
    "update_pull_request",
    "pull_request_review_write",
    "create_pull_request_review",
    "create_and_submit_pull_request_review",
    "submit_pending_pull_request_review",
}
_NO_MARKER = (
    f"agents' posts on GitHub go out under the owner's account, so each carries the marker `{AGENT_MARKER}` "
    f"that tells them from the owner's own words; add `{AGENT_MARKER}` at the end of the body"
)


def _has_opt(toks: list[str], opts: tuple[str, ...]) -> bool:
    longs = tuple(o + "=" for o in opts if o.startswith("--"))
    shorts = tuple(o for o in opts if not o.startswith("--"))
    return any(t in opts or t.startswith(longs) or (t.startswith(shorts) and len(t) > 2 and not t.startswith("--")) for t in toks)


_TEXT_KEYS = ("body", "comment")


def _carries_text(txt: str | None) -> bool:
    """A JSON body (an `--input` file or stdin) that carries text: a `body` or
    `comment` field anywhere in it. One that can't be read counts."""
    if txt is None:
        return True
    try:
        value = json.loads(txt)
    except ValueError:
        return bool(re.search(r'"(?:body|comment)"\s*:', txt))

    def walk(v) -> bool:
        if isinstance(v, dict):
            return any((k in _TEXT_KEYS and isinstance(x, str)) or walk(x) for k, x in v.items())
        if isinstance(v, list):
            return any(walk(x) for x in v)
        return False

    return walk(value)


def _stdin_text(seg: Seg) -> str | None:
    """What the command reads on stdin, when the guard can see it: a heredoc or
    here-string, a `<` file, or a `cat` piping into it. None otherwise."""
    if seg.stdins > 1 or seg.stdin_unseen:
        return None
    if seg.heredoc is not None:
        return seg.heredoc
    if seg.stdin:
        return _read_text(seg.stdin, seg.cwd)
    return _piped_text(seg)


def _graphql_texts(call: _ApiCall, cwd: str | None, stdin_text: str | None) -> tuple[str, str] | None:
    """(the queries, the variables) a `gh api graphql` call sends: `query`
    fields, the `query` and `variables` of `--input` JSON (a file or stdin), a
    query file (`-F query=@q.graphql`), and the other fields. None when an
    input can't be read."""
    queries: list[str] = []
    variables: list[str] = []
    for f in call.fields:
        name, _, val = f.partition("=")
        if name == "query":
            if not val.startswith("@"):
                queries.append(val)
        else:
            variables.append(f)
    sources = [_read_text(f, cwd) for f in call.files] + ([stdin_text] if call.stdin else [])
    for txt in sources:
        if txt is None:
            return None
        try:
            value = json.loads(txt)
        except ValueError:
            value = None
        if isinstance(value, dict) and isinstance(value.get("query"), str):
            queries.append(value["query"])
            variables.append(json.dumps(value.get("variables") or {}))
        else:
            queries.append(txt)
    return "\n".join(queries), "\n".join(variables)


def _creates_text(toks: list[str], cwd: str | None, stdin_text: str | None = None) -> bool:
    """This gh command posts text (an issue, PR, comment or review, or a body) to
    GitHub. `stdin_text` is what it reads on stdin, when that can be seen."""
    if len(toks) < 2 or Path(toks[0]).name != "gh":
        return False
    group, sub = _gh_group(toks)
    if sub == "comment" and group in ("issue", "pr") and _has_opt(toks, ("--delete-last",)) and not _has_opt(toks, _GH_COMMENT_BODY):
        return False
    if (group, sub) in _GH_TEXT_ALWAYS:
        return True
    if (group, sub) in _GH_TEXT_WITH:
        return _has_opt(toks, _GH_TEXT_WITH[(group, sub)])
    if group != "api":
        return False
    call = _api(toks)
    if call is None:
        return False
    if call.path == "graphql":
        texts = _graphql_texts(call, cwd, stdin_text)
        if texts is None:
            return True  # what it sends can't be seen; it counts
        query, variables = texts
        calls = _mutation_calls(query)
        if calls is None:
            return True  # a mutation the guard can't read counts
        for name, args in calls:
            if name in _GQL_TEXT_ALWAYS:
                return True
            # A body in the arguments, or in the variables they take; never in the selection set.
            if name in _GQL_TEXT_WITH_BODY and (re.search(r"\bbody\b", args) or ("$" in args and re.search(r"\bbody\b", variables))):
                return True
        return False
    if call.method not in ("POST", "PATCH", "PUT"):
        return False
    prefix = r"repos/[^/]+/[^/]+/"
    if any(re.fullmatch(prefix + p, call.path, re.I) for p in _API_TEXT_ALWAYS):
        return True
    if not any(re.fullmatch(prefix + p, call.path, re.I) for p in _API_TEXT_WITH_BODY):
        return False
    if _field(call, "body") is not None:
        return True
    if call.stdin and _carries_text(stdin_text):
        return True  # what it sends can't be seen, or carries text
    return any(_carries_text(_read_text(f, cwd)) for f in call.files)


def _mcp_creates_text(name: str, inp: dict) -> bool:
    if name in _MCP_TEXT_ALWAYS:
        return True
    if name == "issue_write" and str(inp.get("method") or "").casefold() == "create":
        return True
    body = inp.get("body")
    return name in _MCP_TEXT_WITH_BODY and isinstance(body, str) and bool(body.strip())


_READERS = {"cat", "tac", "head", "tail"}


def _command_reads(segs: list[Seg]) -> list[str]:
    """The text of every file a command reads with cat (head, tail, tac) or a
    `<` redirect, anywhere in it: `B=$(cat body.md); gh pr comment 1 --body "$B"`."""
    out: list[str] = []
    for s in segs:
        files: list[str] = []
        if s.words and Path(s.words[0]).name in _READERS:
            skip = set(_opt_values(s.words, ("-n", "-c", "--lines", "--bytes")))
            files += [w for w in s.words[1:] if not w.startswith("-") and w not in skip]
        files += s.inputs or ([s.stdin] if s.stdin else [])
        for f in files[:50]:
            txt = _read_text(f, s.cwd)
            if txt:
                out.append(txt)
    return out


# ---------- ticket sessions merge only their own pull request ----------

# A ticket session tells its own pull request from another by its head: a merge
# is pinned to the head commit of the checked-out ticket branch, in the one
# field GitHub checks (`--match-head-commit`, the REST merge's `sha`,
# `merge_pull_request`'s `expectedHeadSha`). Arming auto-merge through
# `enable_pr_auto_merge` or the session route `ccr/auto_merge`, which take no
# pin GitHub is known to check, has the pull request's head read back instead
# (`_pr_head`), whatever pin the call names.
_SHA = re.compile(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}")
_PIN_HOW = (
    "`--match-head-commit <sha>` (`gh pr merge`), `-f sha=<sha>` (the REST merge) or `expectedHeadSha` "
    "(`merge_pull_request`), with `<sha>` from `git rev-parse HEAD` once the branch is pushed"
)
# `gh pr merge`'s options that take a value (pflag takes the next word, even one
# starting with `-`).
_MERGE_VALUES = {"-t", "--subject", "-b", "--body", "-F", "--body-file", "-A", "--author-email", "--match-head-commit", "-R", "--repo"}


def _own_head(root: Path, profile: Profile) -> tuple[str | None, str | None, str | None]:
    """(ticket branch, its head commit, a problem) of the session's checkout."""
    d = str(root)
    branch = _branch_of(d)
    if not branch or not fnmatch.fnmatchcase(branch, profile.ticket_branch):
        where = f"on `{branch}`, not a branch matching" if branch else "detached, not on a branch matching"
        return None, None, (
            f"a ticket session merges, queues or arms auto-merge on only its own pull request, told by its ticket branch's head, and the checkout is {where} "
            f"`{profile.ticket_branch}`: switch back to your ticket branch"
        )
    head = _git_out(d, "rev-parse", "--verify", "-q", "HEAD")
    if not head:
        return branch, None, f"can't read the head of the ticket branch `{branch}`, which tells this session's own pull request"
    return branch, head.lower(), None


def _pin_problem(what: str, pins: list[str], root: Path, profile: Profile, how: str = _PIN_HOW) -> str | None:
    """A ticket session's merge or `merge-async` `pins` (every head commit it
    names) must each be its ticket branch's head. `how` says how to pin it."""
    if not pins:
        return f"a ticket session merges or queues only its own pull request, so this {what} must be pinned to its ticket branch's head: add {how}"
    for pin in pins:
        if not _SHA.fullmatch(pin):
            return f"pin this {what} to the full commit sha that `git rev-parse HEAD` prints, not " + (f"`{pin}`" if pin else "an empty one")
    branch, head, problem = _own_head(root, profile)
    if problem:
        return problem
    for pin in pins:
        if pin.lower() != head:
            return (
                f"`{pin}` isn't the head of this session's ticket branch `{branch}` (`{head}`), so this {what} may be another ticket's "
                f"pull request: a ticket session merges or queues only its own. Push your branch and pin it to `{head}`; if the pull request's "
                "head moved on GitHub (the branch was updated there), `git pull` first and pin to the new head"
            )
    return None


def _pr_head(repo: str, number: int) -> tuple[str, str] | None:
    """(head branch, head sha) of a pull request, read from GitHub with `gh`, or
    None when it can't be read. A head from another repository (a fork) comes
    back as `owner/name:branch`, so it never reads as the session's own; one
    whose repository is gone can't be read."""
    jq = '.head.ref + " " + .head.sha + " " + (.head.repo.full_name // "")'
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{repo}/pulls/{number}", "--jq", jq],
            capture_output=True, text=True, timeout=6, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    parts = out.stdout.split() if out.returncode == 0 else []
    if len(parts) != 3:
        return None
    ref = parts[0] if parts[2].casefold() == repo.casefold() else f"{parts[2]}:{parts[0]}"
    return ref, parts[1]


def _arm_problem(number: object, repo: str, root: Path, profile: Profile) -> str | None:
    """Arming auto-merge: the pull request's head is read back and must be the
    session's ticket branch at its head."""
    branch, head, problem = _own_head(root, profile)
    if problem:
        return problem
    num = "" if number is None or isinstance(number, bool) else str(number)
    if not re.fullmatch(r"[0-9]+", num):
        return "can't tell which pull request this arms auto-merge on; name its number"
    n = int(num)
    got = _pr_head(repo, n)
    if got is None:
        return (
            f"a ticket session arms auto-merge only on its own pull request, and the guard couldn't read pull request #{n}'s head to tell; "
            f"arm it pinned instead (`gh pr merge {n} --auto --merge --match-head-commit <sha>`, with `<sha>` from `git rev-parse HEAD`), "
            "or comment that it's ready and leave it to the conductor"
        )
    ref, sha = got
    if ref != branch:
        return f"pull request #{n} is from `{ref}`, not this session's ticket branch `{branch}`: a ticket session arms auto-merge only on its own pull request"
    if sha.lower() != head:
        return (
            f"pull request #{n}'s head `{sha}` isn't the head of `{branch}` (`{head}`): push your branch first, "
            "or `git pull` if its head moved on GitHub, then arm it again"
        )
    return None


def _merge_words(toks: list[str]) -> tuple[set[str], list[str]]:
    """`gh pr merge`'s flags and its `--match-head-commit` values, read as pflag
    reads them: a text option's value is text, never a flag."""
    flags: set[str] = set()
    pins: list[str] = []
    i = 1
    while i < len(toks):
        t = toks[i]
        i += 1
        name, val = None, None
        if t.startswith("--") and len(t) > 2:
            name, eq, v = t.partition("=")
            flags.add(name if name != "--disable-auto" or not eq else t)  # `--disable-auto=false` is no disarm
            if name in _MERGE_VALUES:
                val = v if eq else (toks[i] if i < len(toks) else "")
                i += 0 if eq else 1
        elif t.startswith("-") and len(t) > 1 and t != "--":
            for k, ch in enumerate(t[1:]):
                flags.add("-" + ch)
                if "-" + ch in _MERGE_VALUES:
                    name, rest = "-" + ch, t[2 + k:]
                    val = rest.removeprefix("=") if rest else (toks[i] if i < len(toks) else "")
                    i += 0 if rest else 1
                    break
        if name == "--match-head-commit":
            pins.append(val or "")
    # gh sends the last value, so an empty one beside a set one unpins it.
    return flags, pins if any(pins) else []


def _unread_merge_word(seg: Seg, toks: list[str]) -> str | None:
    """Why the guard can't read a ticket session's merge or arm as the shell
    runs it: xargs feeds it words, or a word (a heredoc's or text value's too:
    the lexer drops quoting) holds an expansion, a tilde, a glob or a brace list."""
    if seg.fed:
        return "xargs gives it more words"
    for t in toks[1:]:
        if isinstance(t, Word):
            if t.splits:
                return f"the shell may change `{t}`"
        elif re.search(r"[$`~*?\[]", t) or _brace_list(t):
            return f"the shell may change `{t}`"  # a word the lexer didn't read: whatever it holds
    return None


def _gh_merge_problem(seg: Seg, toks: list[str], profile: Profile, root: Path) -> str | None:
    """A ticket session's `gh pr merge` (toks start at the gh word)."""
    flags, pins = _merge_words(toks)
    what = "arm of auto-merge" if "--auto" in flags else "merge"
    unread = _unread_merge_word(seg, toks)  # before the disarm: `--disable-auto $X` may arm
    if unread:
        return (
            f"write this {what} out in full, with no subject or body and the commit pinned as the sha `git rev-parse HEAD` prints: "
            f"{unread}, so the guard can't tell which pull request it merges or what it is pinned to"
        )
    if "--disable-auto" in flags and not flags - {"--disable-auto", "-R", "--repo"}:
        return None  # a disarm, nothing else
    return _pin_problem(what, pins, root, profile)


def _split_api_word(seg: Seg, toks: list[str]) -> str | None:
    """Why a ticket session's `gh api` call may run another call than it reads
    as: xargs feeds it words, or the shell expands a word into others (outside
    quotes: a variable or substitution, a glob, a brace list, a tilde), in
    which a merge path or `-X PUT` can hide. Quoted text is fine; a word the
    lexer didn't read counts if it holds any of these at all."""
    if seg.fed:
        return "xargs gives it more words"
    for t in toks[1:]:
        if isinstance(t, Word):
            if t.splits:
                return f"the shell may split `{t}` into other words"
        elif _literal_heredoc(t) or ((key := re.match(r"[\w.\[\]-]+=", t)) and _literal_heredoc(t[key.end():])):
            continue
        elif re.search(r"[$`*?\[]|(?:^|[=:])~", t) or _brace_list(t):
            return f"the shell may split `{t}` into other words"
    return None


def _rest_merge_problem(seg: Seg, toks: list[str], call: _ApiCall, profile: Profile, root: Path) -> str | None:
    """A ticket session's `gh api` write to a pull request's merge or arm route."""
    m = re.fullmatch(r"repos/([^/]+/[^/]+)/pulls/(\d+)/(merge|ccr/auto_merge)", call.path, re.I)
    # The path word as written: one the shell fills in (`pulls/9?/merge`) reads as another path.
    path_words = [t for t in toks[1:] if re.match(r"(?:https?://[^/\s]+/(?:api/v3/)?)?/?repos/", t)]
    if not m and not any(re.search(r"(?i)pulls/[^/\s]*/(merge(?!-async)|ccr/auto_merge)", t) for t in path_words):
        return None
    what = "arm of auto-merge" if m and m.group(3).lower() != "merge" else "merge"
    unread = _unread_merge_word(seg, toks)
    if unread:
        return f"write this {what} out in full: {unread}, so the guard can't tell which pull request it is for or what it is pinned to"
    if not m:
        return None
    if what == "merge":
        if call.files or call.stdin:
            return "the guard reads a merge's pin only from its `-f sha=<sha>` field: send the merge without an `--input` body or `@file` fields"
        return _pin_problem("merge", _field_values(call, "sha"), root, profile)
    repo = profile.repo if m.group(1) == "{owner}/{repo}" else m.group(1)
    return _arm_problem(m.group(2), repo, root, profile)


def _ticket_merge_problem(seg: Seg, toks: list[str], profile: Profile, root: Path) -> str | None:
    """A ticket session's `gh pr merge` or REST merge/arm (toks start at the gh word)."""
    group, sub = _gh_group(toks)
    if group == "pr" and sub == "merge":
        return _gh_merge_problem(seg, toks, profile, root)
    call = _api(toks)
    if not call:
        return None
    split = _split_api_word(seg, toks)  # a GET or DELETE too: `gh api $X` may be a PUT
    if split:
        return (
            f"write this API call out, quoting what the shell would otherwise expand (text in a quoted heredoc, "
            f"`\"$(cat <<'EOF' … EOF)\"`, or a `-F body=@file` field): {split}, so the guard can't tell which route it calls"
        )
    if call.method not in ("GET", "DELETE"):
        return _rest_merge_problem(seg, toks, call, profile, root)
    return None


# ---------- adding a pull request to a merge queue ----------

# The one route the kit queues a pull request by (#243, #244): REST
# `PUT repos/<repo>/pulls/<n>/merge-async`. Its `merge_action` must be
# `merge_queue`: `default` (also what a missing one means) merges directly when
# no queue is required, and `direct_merge` always does. `bypass_rules` skips the
# ruleset, as `gh pr merge --admin` does, and is refused on any `gh api` write.
# These hold in every role, and the call is pinned by `sha`: to the ticket
# branch's head in a ticket session, to a commit in any other. Its fields are
# read only from `-f`/`-F`, where the guard sees them: a body from a file or
# stdin is refused once it has been searched for `bypass_rules`, to name that
# first. The path is read by its last part, however it is spelled (a host,
# `%`-escapes, `//`, `./`, a start the shell fills in); a path the shell fills
# in counts too when the call names a `merge_action`, or PUTs a bare `sha`. An
# attended session's curl is asked unless its JSON body queues it.
# An expansion the shell (or gh, for `{branch}`) fills in; a path word that
# starts as a path (a URL or `repos/`), so it can't be a flag; and a path whose
# last part after `pulls/<n>/` is filled in or a glob, which may be
# `merge-async` (`pulls/comments/<id>` is another route).
_FILLED = re.compile(r"[$`]|\{branch\}")  # gh fills `{branch}` in from the checkout
_PATH_START = re.compile(r"(?i)(?:[a-z][a-z0-9+.-]*://|/?repos/)")
_LAST_FILLED = re.compile(r"(?i)pulls/(?!comments/)[^/]+/[^/]*(?:[$`*?\[]|\{branch\})[^/]*/?$")
_FILLED_PATH_WHY = (
    "write this API call out: the shell fills in its path `{path}`, which may be `merge-async`, "
    "and `{word}`, which may be a flag of its own"
)
_ASYNC_PIN_HOW = "`-f sha=<sha>`, with `<sha>` from `git rev-parse HEAD` once the branch is pushed"
_BYPASS_NAME = r"bypass(?:_|\\u005f)rules"
_BYPASS_RULES = re.compile(r"(?i)" + _BYPASS_NAME)
_GITHUB_API = re.compile(r"(?i)(?:api|uploads)\.github\.com|/api/v3/")
_BYPASS_WHY = (
    "`bypass_rules` merges past the base branch's ruleset, as `gh pr merge --admin` does: leave it out, and the queue "
    "runs the ruleset's checks before it merges. Sending it is never allowed"
)


def _is_merge_async(word: str) -> bool:
    """The path word names `merge-async`, however it is spelled: by its last
    part, so a start the shell fills in (`repos/$REPO/…`, `${B}merge-async`)
    still reads as the route. No other GitHub route ends in `merge-async`."""
    p = urllib.parse.unquote(word)
    p = re.sub(r"(?i)^[a-z][a-z0-9+.-]*://[^/]*", "", p)
    p = re.split(r"[?#]", p, maxsplit=1)[0]
    last = posixpath.normpath("/" + re.sub("/+", "/", p)).rsplit("/", 1)[-1].casefold()
    return last == "merge-async" or (bool(_FILLED.search(last)) and last.endswith("merge-async"))


def _bypass_key(key: str) -> bool:
    """A field named `bypass_rules`, or a part of it (`bypass_rules[x]`)."""
    return bool(re.fullmatch(r"(?i)" + _BYPASS_NAME + r"(?:\[.*)?", key, re.S))


def _body_has_bypass(text: str) -> bool:
    """A body that names `bypass_rules`: as a JSON key at any depth, its escapes
    read, or anywhere in it when it isn't one JSON document."""
    found = False

    def keys(pairs):
        nonlocal found
        found = found or any(_bypass_key(k) for k, _ in pairs)
        return dict(pairs)

    try:
        json.loads(text, object_pairs_hook=keys)
    except ValueError:
        return bool(_BYPASS_RULES.search(text))
    return found


def _json_keys(text: str) -> set[str]:
    """The keys of the JSON documents in `text`, at any depth; `"name":` spellings
    when it isn't JSON."""
    found: set[str] = set()

    def keys(pairs):
        found.update(k for k, _ in pairs)
        return dict(pairs)

    try:
        json.loads(text, object_pairs_hook=keys)
    except ValueError:
        found.update(re.findall(r'"([A-Za-z_]\w*)"\s*:', text))
    return found


def _input_body(seg: Seg, toks: list[str]) -> tuple[list[str], bool]:
    """(the texts of a `gh api` call's `--input` bodies, each on its own, and
    whether any can't be read): a file named plainly, or stdin from a heredoc,
    a `<` file, a `cat` or a plain `echo`/`printf` piping into it. `@file`
    fields aren't bodies."""
    texts, unread = [], False
    for f in _input_files(toks):
        if _STDIN_FILE.fullmatch(f):
            t = _stdin_text(seg)
            t = _echoed(seg) if t is None else t
        else:
            t = None if _FILLED.search(f) else _read_text(f, seg.cwd)
        unread = unread or t is None
        texts.append(t or "")
    return texts, unread


def _queued_json(text: str | None) -> bool:
    """One JSON object that queues a pull request: `merge_action` `merge_queue`,
    a `sha`, no `bypass_rules`, and no key given twice (the last would win)."""

    def once(pairs):
        names = [k for k, _ in pairs]
        if len(set(names)) != len(names):
            raise ValueError("a key given twice")
        return dict(pairs)

    try:
        obj = json.loads(text or "", object_pairs_hook=once)
    except ValueError:
        return False
    if not isinstance(obj, dict) or any(_bypass_key(k) for k in obj):
        return False
    sha = obj.get("sha")
    return obj.get("merge_action") == "merge_queue" and isinstance(sha, str) and bool(sha.strip())


# curl's options that send a body, and those whose body the guard doesn't read
# (`-G` sends it as the query string instead).
_CURL_BODY = {"-d", "--data", "--data-raw", "--data-binary", "--data-ascii", "--json"}
_CURL_UNREAD = {"--data-urlencode", "-F", "--form", "--form-string", "-T", "--upload-file", "-K", "--config", "-G", "--get", "--url-query"}


def _curl_configs(toks: list[str]) -> list[str]:
    """The config files a curl reads: `-K f`, `-Kf`, `-sK f`, `--config[=]f`."""
    out = []
    for k, t in enumerate(toks):
        nxt = toks[k + 1] if k + 1 < len(toks) else ""
        m = re.fullmatch(r"-[a-zA-Z]*K(.*)", t, re.S)
        if m:
            out.append(m.group(1) or nxt)
        elif t == "--config" or t.startswith("--config="):
            out.append(t.split("=", 1)[1] if "=" in t else nxt)
    return out


def _curl_url_queues(word: str) -> bool:
    """A curl word that is a URL naming `merge-async`, or a GitHub API URL whose
    part after `pulls/<n>/` the shell or curl fills in (`$M`, `{…}`, `[…]`)."""
    if re.search(r'[\s"]', word) or "/" not in word:
        return False  # text, such as a body, not a URL
    u = urllib.parse.unquote(word)
    if _is_merge_async(word):
        return True
    return bool(_GITHUB_API.search(u) and re.search(r"(?i)/pulls/(?!comments/)[^/]+/[^/]*[$`{\[][^/]*$", u))


def _hidden_config(f: str, cwd: str | None) -> bool:
    """A curl config whose text isn't a file the guard can read now: stdin, a
    descriptor or device (any path that resolves under `/dev/` or `/proc/`,
    `/dev/null` as written aside, which is empty), or a name the shell fills in."""
    if f in ("", "-") or _STDIN_FILE.fullmatch(f) or _FILLED.search(f):
        return True
    a = os.path.expanduser(f)
    if not a.startswith("/") and cwd:
        a = cwd + "/" + a
    n = posixpath.normpath(re.sub("/+", "/", a))
    return f != os.devnull and n.startswith(("/dev/", "/proc/"))  # `/dev/null` as written: `/dev/fd/3/../null` is elsewhere


def _curl_queue_problem(toks: list[str], joined: str, cwd: str | None) -> str | None:
    """An attended session's curl PUT that may add a pull request to a merge
    queue (a URL `_curl_url_queues`, or a config file it reads that names
    `merge-async`, or can't be read when the command names no URL) is asked
    unless it sends one JSON body that queues it (`_queued_json`), with no
    query string."""
    configs = _curl_configs(toks)
    named = any(_curl_url_queues(t) for t in toks)
    for f in configs:
        hidden = _hidden_config(f, cwd)
        text = None if hidden else _read_text(f, cwd)
        if text is not None:
            named = named or re.search(r"(?i)merge-async", urllib.parse.unquote(text)) is not None
        elif hidden or not any("://" in t for t in toks):
            named = True  # stdin or a name the shell fills in may hold anything; a plain missing file only fails
    if not named:
        return None
    # GitHub takes `merge-async` only as a PUT: a curl whose every method is a
    # literal other one, with one URL (no `--next`) and no config, is left alone.
    methods = [m.group(1) or (toks[k + 1] if k + 1 < len(toks) else "") for k, t in enumerate(toks) if (m := re.fullmatch(r"(?:-[a-zA-Z]*X|--request=?)(.*)", t, re.S))]
    if any(t in ("-T", "--upload-file") or re.fullmatch(r"-[a-zA-Z]*T.*", t, re.S) for t in toks):
        methods.append("PUT")
    several = any(t in ("--next", "-:") for t in toks)
    if methods and not configs and not several and not any(_FILLED.search(m) or m.upper() == "PUT" for m in methods):
        return None
    bodies: list[str | None] = []
    unread = False
    i = 1
    while i < len(toks):
        t = toks[i]
        i += 1
        name, eq, val = t.partition("=") if t.startswith("--") else (t, "", "")
        if name in _CURL_BODY:
            if not eq:
                val, i = (toks[i] if i < len(toks) else ""), i + 1
        elif re.fullmatch(r"-d.+", t, re.S):
            val = t[2:]
        elif name in _CURL_UNREAD or re.fullmatch(r"-[FTK].+|-[a-zA-Z]*[GK][a-zA-Z]*", t, re.S):
            unread = True
            continue
        else:
            continue
        if val.startswith("@"):
            f = val[1:]
            val = None if f in ("", "-") else _read_text(f, cwd)
        bodies.append(val)
    query = any(_curl_url_queues(t) and "?" in t for t in toks)
    if not unread and not query and len(bodies) == 1 and _queued_json(bodies[0]):
        return None
    return (
        "to add a pull request to the merge queue with curl, send one JSON body the guard can read: `merge_action` "
        "`merge_queue`, a `sha`, and no `bypass_rules`. Or use `gh api -X PUT repos/<repo>/pulls/<n>/merge-async "
        "-f merge_action=merge_queue -f sha=<sha>`"
    )


def _filled_word(toks: list[str], path: str) -> str | None:
    """A `gh api` word the shell fills in that may be a flag of its own: one
    holding an expansion, quoted or not, outside a flag's value, a field's value
    (after a plain `name=`) and the path word `path`. Quoted text such as `"$E"`
    stays one word, but that word can be `--field=bypass_rules=true`."""
    i = toks.index("api") + 1 if "api" in toks else 1
    path_seen = False
    while i < len(toks):
        t = toks[i]
        i += 1
        if t in _FIELD_FLAGS:
            t, i = (toks[i] if i < len(toks) else ""), i + 1
        elif t in _API_VALUES or t in ("-X", "--method", "--input"):
            i += 1
            continue
        elif re.fullmatch(r"--(?:method|header|jq|template|hostname|cache|preview|input)=.*|-[XHqtp].+", t, re.S):
            continue
        elif t.startswith(("--field=", "--raw-field=")):
            t = t.split("=", 1)[1]
        elif re.fullmatch(r"-[fF].+", t, re.S):
            t = t[3:] if t[2] == "=" else t[2:]
        else:
            if t == path and not path_seen:
                path_seen = True
                continue
            if _FILLED.search(t):
                return t
            continue
        if _FILLED.search(t.split("=", 1)[0]) or (_FILLED.search(t) and "=" not in t):
            return t
    return None


def _may_add_flags(seg: Seg, toks: list[str], call: _ApiCall, keys: list[str]) -> bool:
    """Whether the shell or xargs may add flags to this `gh api` call (a
    `-XPUT`, a field): xargs feeds it; a word outside a value holds an
    expansion (`_filled_word`); the path word holds one and doesn't start as a
    path, with another word left to be the path; or an unquoted word splits,
    a path that starts as one only when the call names `merge_action` or `sha`."""
    if seg.fed or _filled_word(toks, call.word) is not None:
        return True
    if _FILLED.search(call.word) and not _PATH_START.match(call.word) and len(_positionals(toks)) > 1:
        return True
    queue_keys = {"merge_action", "sha"} & set(keys)
    return any(isinstance(t, Word) and t.splits and (queue_keys or not _PATH_START.match(t)) for t in toks[1:])


def _positionals(toks: list[str]) -> list[str]:
    """A `gh api` call's words that are neither options nor their values."""
    out: list[str] = []
    i = toks.index("api") + 1 if "api" in toks else 1
    while i < len(toks):
        t = toks[i]
        i += 1
        if t in _FIELD_FLAGS or t in _API_VALUES or t in ("-X", "--method", "--input"):
            i += 1
        elif not t.startswith("-") or t == "-":
            out.append(t)
    return out


def _merge_async_problem(seg: Seg, toks: list[str], profile: Profile, role: str, root: Path) -> str | None:
    """A `gh api` write to `pulls/<n>/merge-async`, in any role (toks start at the gh word)."""
    call = _api(toks)
    if not call or call.method == "GET":
        return None
    keys = [f.split("=", 1)[0] for f in call.fields]
    if any(_bypass_key(k) for k in keys):
        return _BYPASS_WHY
    filled = _FILLED.search(call.word)
    unread_path = seg.fed and not _PATH_START.match(call.word)
    # A path the shell fills in from its start to its last part (`"$URL"`, not
    # `"$PR_URL/merge"`), so it may be any route.
    last_part = call.word.rstrip("/").rsplit("/", 1)[-1]
    whole_filled = (filled and not _PATH_START.match(call.word) and _FILLED.search(last_part)) or unread_path
    # GitHub takes `merge-async` only as a PUT; a literal other method can't
    # become one unless xargs adds words, or a word the shell fills in (outside
    # a value, the path included when it doesn't start as a path) is a flag.
    if call.method in ("POST", "PATCH", "DELETE") and not _may_add_flags(seg, toks, call, keys):
        return None
    route = _is_merge_async(call.word)
    bodies, body_unread = _input_body(seg, toks)
    if (route or filled or unread_path) and any(_body_has_bypass(b) for b in bodies):
        return _BYPASS_WHY
    # The merge's and update-branch's own fields say which route a filled-in
    # last part is.
    other_route = {"merge_method", "expected_head_sha"} & set(keys)
    last_filled = _LAST_FILLED.search(call.word) and not other_route
    # A whole path the shell fills in may be `merge-async` with no
    # `merge_action`: when it PUTs a `sha` and only fields `merge-async` takes,
    # or a body that names `merge_action` or `sha`, or can't be read.
    queue_fields = "sha" in keys and set(keys) <= {"sha", "commit_title", "commit_message"}
    queue_body = body_unread or any(_json_keys(b) & {"merge_action", "sha"} for b in bodies)
    bare_put = whole_filled and (queue_fields or queue_body)
    if not (route or (filled and "merge_action" in keys) or last_filled or unread_path or bare_put):
        if (filled or unread_path) and (word := _filled_word(toks, call.word)) is not None:
            return _FILLED_PATH_WHY.format(path=call.word, word=word)
        return None
    if re.search(r"[?#]", call.word):
        return "write the `merge-async` path without a query string or `#`, and its fields as `-f` or `-F` fields, so the guard reads every one"
    split = _split_api_word(seg, toks)
    if not split and (word := _filled_word(toks, call.word)) is not None:
        split = f"the shell fills in `{word}`, which may be a flag of its own"
    if not split and (last_filled or unread_path):
        split = f"the shell fills in the path `{call.word}`, which may be `merge-async`"
    if split:
        return (
            "write this `merge-async` call out, quoting what the shell fills in (`-f sha=\"$SHA\"`, "
            f"`pulls/\"$N\"/merge-async`) and with its fields as plain `-f name=value` fields: {split}, so the guard can't tell which fields it sends"
        )
    unplain = next((k for k in keys if not re.fullmatch(r"[A-Za-z_]\w*", k)), None)
    if unplain is not None:
        return f"write `merge-async`'s fields out as plain `-f name=value` fields: with `{unplain}`, the guard can't tell which field it sends"
    if call.files or call.stdin:
        return (
            "the guard reads `merge-async`'s fields only from `-f` or `-F`: send `-f merge_action=merge_queue -f sha=<sha>`, "
            "without an `--input` body or `@file` fields"
        )
    actions = _field_values(call, "merge_action")
    if not actions or any(a != "merge_queue" for a in actions):
        return (
            "add a pull request to the merge queue only with `-f merge_action=merge_queue`: `default`, or none, merges it "
            "directly when no queue is required, and `direct_merge` always does"
        )
    pins = _field_values(call, "sha")
    if role == "ticket":
        return _pin_problem("`merge-async` call", pins, root, profile, _ASYNC_PIN_HOW)
    if not pins or not all(_SHA.fullmatch(v) or _FILLED.search(v) for v in pins):
        return (
            "pin this `merge-async` call to the head you checked with `-f sha=<sha>`, the full commit sha "
            "(or one the shell fills in), so GitHub never queues a head nobody checked"
        )
    return None


def _ticket_mcp_merge_problem(name: str, inp: dict, profile: Profile, root: Path) -> str | None:
    if name not in ("merge_pull_request", "enable_pr_auto_merge"):
        return None
    owner, rname = inp.get("owner"), inp.get("repo")
    if (owner or rname) and not (isinstance(owner, str) and isinstance(rname, str) and f"{owner}/{rname}".casefold() == profile.repo.casefold()):
        return f"ticket sessions work only in {profile.repo}; this `{name}` names another repository (give `owner` and `repo` as {profile.repo})"
    if name == "enable_pr_auto_merge":
        return _arm_problem(inp.get("pullNumber"), profile.repo, root, profile)
    # `expectedHeadSha` is the pin the tool sends; a `sha` given as well must match too.
    given = [inp.get("expectedHeadSha")]
    if given[0] not in (None, "") and inp.get("sha") not in (None, ""):
        given.append(inp["sha"])
    pins = [p for p in given if p not in (None, "")]
    if not all(isinstance(p, str) for p in pins):
        return "pin this merge with `expectedHeadSha` given as text: the full commit sha that `git rev-parse HEAD` prints"
    return _pin_problem("merge", pins, root, profile)


# ---------- deploys ----------


# Programs that run a script named among their arguments, with the options
# that take a separate value, and the subcommand word that runs ("uv run").
_SHELL_VALUE_OPTS = {"-o", "+o", "-O", "+O", "--rcfile", "--init-file"}
_LAUNCHERS: dict[str, tuple[str | None, set[str]]] = {
    "python": (None, {"-W", "-X", "--check-hash-based-pycs"}),
    "node": (None, {"-r", "--require", "--import", "--loader", "--experimental-loader", "--env-file", "--conditions", "-C"}),
    "ruby": (None, {"-I", "-r", "-C", "-E", "-F"}),
    "perl": (None, {"-I", "-M", "-m", "-F"}),
    "shell": (None, _SHELL_VALUE_OPTS),
    "uv": ("run", {"--with", "--with-requirements", "--python", "-p", "--project", "--directory", "--group", "--extra", "--env-file", "--index", "--from", "--package"}),
    "npx": (None, {"-p", "--package", "-c", "--call"}),
    "deno": ("run", {"--config", "-c", "--import-map", "--location", "--env-file", "--cert"}),
    "bun": ("run?", {"--cwd", "-r", "--preload", "--config", "-c", "--env-file"}),
}


def _launcher(name: str) -> str | None:
    if re.fullmatch(r"python\d?(\.\d+)?", name):
        return "python"
    if name in ("node", "nodejs"):
        return "node"
    if name in _SHELLS or name in ("source", "."):
        return "shell"
    return name if name in _LAUNCHERS else None


def _launched(toks: list[str]) -> list[str] | None:
    """The words after the interpreters and launchers that run a script
    (`uv run python scripts/deploy.py --stage poc` -> ["scripts/deploy.py",
    "--stage", "poc"]), or None when the command isn't one."""
    words = list(toks)
    stripped = False
    for _ in range(4):
        kind = (_launcher(words[0] if words[0] in (".", "source") else Path(words[0]).name)) if words else None
        if kind is None:
            break
        sub, values = _LAUNCHERS[kind]
        words = words[1:]
        if sub == "run?":
            if words[:1] in (["run"], ["x"]):
                words = words[1:]
        elif sub:
            if words[:1] != [sub]:
                return words if stripped else None  # `uv pip …`, `deno fmt …`: not running a script
            words = words[1:]
        while words and words[0].startswith(("-", "+")) and words[0] not in ("-", "--"):
            w = words.pop(0)
            if w in values and words:
                words.pop(0)
        if words[:1] == ["--"]:
            words = words[1:]
        stripped = True
    return words if stripped else None


def _deploy_problem(seg: Seg, deploy: list[str], root: Path) -> str | None:
    toks = seg.words
    if not toks:
        return None
    name = Path(toks[0]).name
    paths = [d for d in deploy if d.split() and ("/" in d.split()[0] or re.search(r"\.(sh|py|js|ts|rb|mjs|cjs)$", d.split()[0]))]
    deploy_paths = [_norm(d.split()[0], root) for d in paths]
    if name in _SHELLS and _shell_reads_stdin(toks):
        fed = [seg.stdin] if seg.stdin else (seg.piped.words if seg.piped else [])
        for w in fed:
            n = _norm(w, root, seg.piped.cwd if seg.piped and not seg.stdin else seg.cwd)
            if n in deploy_paths:
                d = paths[deploy_paths.index(n)]
                return f"`{d}` is a deploy command (fed to a shell here): only the owner, or the conductor under a release grant, runs it"
    launched = _launched(toks)
    # Run directly, the command word is the script; run by an interpreter, any word may be.
    candidates = [toks[0]] if launched is None else [w for w in launched if not w.startswith("-")]
    for d in deploy:
        dt = d.split()
        if not dt:
            continue
        msg = f"`{d}` is a deploy command: only the owner, or the conductor under a release grant, runs it"
        if d in paths:
            target = _norm(dt[0], root)
            if any(_norm(w, root, seg.cwd) == target for w in candidates):
                return msg
        else:
            for ws in (toks, launched or []):
                words = [t for t in ws if not t.startswith("-")]
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
    # an in-place edit of the files a search finds (`grep -rl x . | xargs sed -i`): (tree searched, its cwd)
    searched: list[tuple[str, str | None]] = field(default_factory=list)
    # a writing find from the project root limited by -name/-iname: (its name globs, case-insensitive)
    # a writing find limited by -name/-iname: (its globs, case-insensitive, its start's own name tested, the start)
    named_from_root: list[tuple[list[str], bool, bool, str]] = field(default_factory=list)


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


def _patch_paths(text: str, stripped: bool = True) -> list[str]:
    """The paths a patch names, each also with its first part dropped
    (`a/`, `b/`, `-p1`) unless `stripped` is False."""
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
    if not stripped:
        return out
    paths: list[str] = []
    for p in out:
        paths.append(p)
        if "/" in p:
            paths.append(p.split("/", 1)[1])  # a/ b/ prefixes, -p1
    return paths


def _piped_text(seg: Seg) -> str | None:
    """What a `cat` (with a heredoc, files or a stdin file) piping into this
    command sends it; None when it isn't one or a file can't be read."""
    return _piped_sized(seg, 1_000_000)[0]


def _piped_sized(seg: Seg, cap: int) -> tuple[str | None, int, bool]:
    """`_piped_text` read up to `cap` bytes in all: (its text, the bytes, whether there is more)."""
    p = seg.piped
    if p is None or not p.words or Path(p.words[0]).name != "cat" or p.stdins > 1 or p.stdin_unseen:
        # Not a `cat` the guard can read; no words is a redirection alone, or a
        # group's (`( cat f ) 2>/dev/null |`), whose output can't be seen.
        return None, 0, False
    ops = [w for w in p.words[1:] if w == "-" or not w.startswith("-")]
    if not ops or ops == ["-"]:
        if p.heredoc is not None:
            size = _size(p.heredoc)
            return p.heredoc, size, size > cap
        return _read_sized(p.stdin, p.cwd, cap) if p.stdin else (None, 0, False)
    texts, left = [], cap
    for f in ops:
        txt, size, over = _read_sized(f, p.cwd, max(left, 0))
        if txt is None or over:
            return None, 0, over
        texts.append(txt)
        left -= size
    return "".join(texts), cap - left, False  # as cat joins them: nothing between


def _patch_texts(cmd: str, args: list[str], seg: Seg) -> tuple[list[str], str | None, list[str]]:
    """git apply/am (args after the subcommand) or patch: (the patch texts, why
    they can't be seen, the file `patch` itself writes). Nothing when it only checks."""
    patched: list[str] = []
    if cmd in ("git", "git-am"):
        if cmd == "git" and any(a in ("--check", "--stat", "--numstat", "--summary") for a in args) and "--apply" not in args:
            return [], None, []
        if cmd == "git-am" and any(a in ("--abort", "--quit", "--skip", "--continue", "--resolved", "-r", "--retry") or a.startswith("--show-current-patch") for a in args):
            return [], None, []
        files = [a for a in args if not a.startswith("-")]
        for v in _opt_values(["x", *args], ("--directory",)):
            files = [f for f in files if f != v]
        texts_from = files
    else:
        if any(a == "--dry-run" for a in args):
            return [], None, []
        inputs = _opt_values(["x", *args], ("-i", "--input"))
        skip = set(inputs) | set(_opt_values(["x", *args], ("-p", "-d", "--directory", "-o", "--output", "-r", "-B", "-z", "-D")))
        positional = [a for a in args if not a.startswith("-") and a not in skip]
        patched = positional[:1]  # the file being patched
        texts_from = inputs or positional[1:2]
    texts: list[str] = []
    left = _PATCH_CAP  # for all the patches together

    def read(f: str) -> tuple[str | None, str | None]:
        """A patch's text, or why it can't be read."""
        nonlocal left
        txt, size, over = _read_sized(f, seg.cwd, left)
        if over:
            return None, f"the patches are over {_PATCH_CAP:,} bytes, more than the guard reads; apply them in smaller parts"
        if txt is None:
            return None, f"can't read the patch `{f}` to see what it changes"
        left -= size
        return txt, None

    for f in texts_from:
        if f == "-":
            texts_from = []
            break
        txt, why = read(f)
        if txt is None:
            return [], why, patched
        texts.append(txt)
    if not texts_from:
        if seg.stdins > 1 or seg.stdin_unseen:
            return [], "this gives the patch more than one input on stdin (heredocs, here-strings or `<` files), or one from another descriptor, which the guard can't follow; give it one", patched
        piped = (None, 0, False)
        if seg.stdin:
            txt, why = read(seg.stdin)
            if txt is None:
                return [], why, patched
            texts.append(txt)
        elif seg.heredoc is not None:
            texts.append(seg.heredoc)
        elif (piped := _piped_sized(seg, left))[2]:
            return [], f"the patches are over {_PATCH_CAP:,} bytes, more than the guard reads; apply them in smaller parts", patched
        elif piped[0] is not None:
            texts.append(piped[0])
        else:
            return [], "this applies a patch from a pipe, where the guard can't see what it changes; apply it from a file or a heredoc", patched
    return texts, None, patched


def _patch_targets(cmd: str, args: list[str], seg: Seg, root: Path, t: _Targets) -> None:
    """git apply / git am (args after the subcommand) or patch (args after `patch`)."""
    texts, unknown, patched = _patch_texts(cmd, args, seg)
    t.files += patched
    if unknown:
        t.unknown = unknown
        return
    base_dir = os.path.realpath(str(root))
    for txt in texts:
        for p in _patch_paths(txt):
            if cmd in ("git", "git-am"):  # paths from the top of the repository
                full = os.path.join(base_dir, p)
                t.files.append(os.path.relpath(full, seg.cwd) if seg.cwd else full)
            else:
                t.files.append(p)


def _git_targets(args: list[str], t: _Targets) -> None:
    sub = args[0] if args else ""
    rest = args[1:]
    if sub == "clean":
        # It removes only untracked files: the protected paths git tracks are
        # safe, so only a path that is or holds one counts, or -x/-X (ignored
        # files, such as .env) from a directory that holds one.
        flags = "".join(a[1:] for a in rest if re.fullmatch(r"-[a-zA-Z]+", a))
        if "n" in flags or "--dry-run" in rest:
            return
        skip = set(_opt_values(["x", *rest], ("-e", "--exclude")))
        paths = [a for a in rest if not a.startswith("-") and a not in skip]
        t.trees += paths or (["."] if set(flags) & {"x", "X"} else [])
        return
    if sub in ("rm", "mv"):
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


def _only_the_match(seg: Seg, root: Path) -> bool:
    """An -execdir command that acts on the match alone: an rm-like or
    touch-like writer, or an in-place editor, whose only target is `{}`. A
    write into the match (`cp x {}`, `tar -C {}`) is not one."""
    toks = seg.words
    name = Path(toks[0]).name if toks else ""
    if any("$(" in w or "`" in w or "<(" in w for w in toks):  # names worked out by the shell, in a directory we can't see
        return False
    if name not in (_RM_LIKE | _TOUCH_LIKE) and not (name in ("sed", "perl", "awk", "gawk") and _inplace_edit(toks) is not None):
        return False
    t = _write_targets(seg, root)
    named = t.files + t.trees + t.links
    return bool(named) and set(named) == {"{}"} and not (t.unknown or t.searched or t.named_from_root)


def _write_targets(seg: Seg, root: Path) -> _Targets:
    """What one command writes, removes, links to, or can't show."""
    t = _write_targets_raw(seg, root)
    if seg.match_only:  # its `{}` is find -execdir's match, which the find's own check covers
        t.files = [x for x in t.files if x != "{}"]
        t.trees = [x for x in t.trees if x != "{}"]
        t.links = [x for x in t.links if x != "{}"]
    return t


def _write_targets_raw(seg: Seg, root: Path) -> _Targets:
    toks = seg.words
    t = _Targets(files=list(seg.redirects))
    if not toks:
        return t
    cmd = Path(toks[0]).name
    operands = [a for a in toks[1:] if not a.startswith("-")]
    if cmd == "git":
        # `git diff|log|show --output=<file>`, `git format-patch -o <dir>`,
        # `git archive -o <file>`, `git bundle create <file>`; under `git -C <dir>`.
        g = _git(toks)
        sub_args = g[1] if g else []
        cdir = (g[2] if g else None) or ""
        files = _opt_values(toks, ("--output",))
        trees = _opt_values(toks, ("--output-directory",))
        if sub_args[:1] in (["format-patch"], ["archive"]):
            for k, a in enumerate(sub_args):
                m = re.fullmatch(r"-[a-zA-Z]*o(.*)", a, re.S)
                if m and not a.startswith("--"):
                    v = m.group(1) or (sub_args[k + 1] if k + 1 < len(sub_args) else "")
                    (trees if sub_args[0] == "format-patch" else files).append(v)
        if sub_args[:2] == ["bundle", "create"] and len(sub_args) > 2:
            files += [a for a in sub_args[2:] if not a.startswith("-")][:1]
        t.files += [os.path.join(cdir, f) if cdir and not os.path.isabs(f) else f for f in files]
        t.trees += [os.path.join(cdir, f) if cdir and not os.path.isabs(f) else f for f in trees]
    if cmd in _RM_LIKE:
        t.files += operands
        t.trees += operands
        _fed_by_xargs(seg, root, t, tree=True)
    elif cmd in _TOUCH_LIKE:
        if cmd in {"chmod", "chown", "chgrp", "chattr", "setfacl"} and operands:
            operands = operands[1:]
        if cmd == "truncate":
            operands = [o for o in operands if o not in _opt_values(toks, ("-s", "--size", "-r", "--reference"))]
        t.files += operands
        if any(a in ("-R", "-r", "--recursive") for a in toks[1:]):
            t.trees += operands
        _fed_by_xargs(seg, root, t, tree=any(a in ("-R", "-r", "--recursive") for a in toks[1:]))
    elif cmd in _DEST_LAST:
        _copy_targets(cmd, toks, seg, root, t)
    elif cmd in ("tee", "sponge"):
        t.files += operands
    elif cmd == "dd":
        t.files += [a[3:] for a in toks[1:] if a.startswith("of=")]
    elif cmd in ("sed", "perl", "awk", "gawk"):
        ed = _inplace_edit(toks)
        if ed is not None:
            _named_files(ed.files, seg, root, t)
    elif cmd in ("ed", "red"):
        skip = set(_opt_values(toks, ("-p",)))
        t.files += [a for a in operands if a not in skip]
    elif cmd in _VIMS:
        ed = _vim_edit(toks, stdin=seg.heredoc is not None or bool(seg.stdin) or seg.piped is not None)
        if ed is not None:
            t.files += ed.files
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
        _find_targets(toks, seg, root, t)
    else:
        g = _git(toks)
        if g:
            _, args, _ = g
            if args[:1] == ["apply"]:
                _patch_targets("git", args[1:], seg, root, t)
            elif args[:1] == ["am"]:
                _patch_targets("git-am", args[1:], seg, root, t)
            else:
                _git_targets(args, t)
    return t


def _find_starts(toks: list[str]) -> list[str]:
    """find's start paths (the trees it searches)."""
    return toks[_find_start_index(toks) : _find_expr_index(toks)]


def _find_start_index(toks: list[str]) -> int:
    """Where find's start paths begin: after its options and a `--`."""
    i = 1
    while i < len(toks) and (toks[i] in ("-H", "-L", "-P") or re.fullmatch(r"-O\d*", toks[i]) or toks[i] == "-D"):
        i += 2 if toks[i] == "-D" else 1
    if i < len(toks) and toks[i] == "--":
        i += 1
    return i


def _find_expr_index(toks: list[str]) -> int:
    """Where find's expression begins, after its start paths."""
    i = _find_start_index(toks)
    while i < len(toks) and not (toks[i].startswith("-") or toks[i] in ("(", "!", ")", ",")):
        i += 1
    return i


def _find_writes(toks: list[str], seg: Seg, root: Path) -> bool:
    """`-delete`, or an `-exec` of a program that writes (a shell or an
    interpreter counts: what it runs can't be seen)."""
    if "-delete" in toks:
        return True
    k = 0
    while k < len(toks):
        if toks[k] in ("-exec", "-execdir", "-ok", "-okdir"):
            j = k + 1
            while j < len(toks) and toks[j] not in (";", "+"):
                j += 1
            sub, _, _ = _strip_prefix(toks[k + 1 : j])
            if sub:
                name = Path(sub[0]).name
                if name in _SHELLS or _INTERP.match(name):
                    return True
                st = _write_targets(Seg(sub, [], seg.cwd), root)
                if st.files or st.trees or st.links or st.unknown:
                    return True
            k = j
        k += 1
    return False


def _find_targets(toks: list[str], seg: Seg, root: Path, t: _Targets) -> None:
    t.files += _opt_values(toks, ("-fprint", "-fprint0", "-fprintf", "-fls"))
    if not _find_writes(toks, seg, root):
        return
    names = _find_names(toks)
    if "-L" in toks[1 : _find_start_index(toks)] or "-follow" in toks:
        # Following links, a write anywhere may reach the project's protected paths.
        t.trees.append(os.path.realpath(str(root)))
        return
    for a in _find_starts(toks) or ["."]:
        p = _abspath(a, seg.cwd)
        if p is not None and names is not None and not _outside(_rel(p, root)) and os.path.isdir(p):
            # A directory in the project, limited by name: what it can match is checked against the files there.
            # find tests -name against the start as written: `.` never matches, a path by its last part
            t.named_from_root.append((*names, posixpath.normpath(a) != ".", p))
            continue
        t.trees.append(a)


_FIND_TESTS = {"-type", "-maxdepth", "-mindepth"}  # each takes one value
_FIND_FLAGS = {"-a", "-and", "-depth", "-xdev", "-mount"}


def _find_names(toks: list[str]) -> tuple[list[str], bool] | None:
    """find's -name/-iname globs when the expression is one this guard can read
    exactly, else None (and the find is a write into its whole tree).

    Read exactly: an optional leading `-name X -prune -o` or `-path X -prune -o`,
    then only -name, -iname, -type, -maxdepth, -mindepth and plain flags, then
    one action at the very end: `-delete`, or `-exec`/`-execdir … ;|+`. Globs
    with `[` or `\\` (whose dialects differ from Python's fnmatch) aren't read."""
    expr = toks[_find_expr_index(toks) :]
    if len(expr) >= 4 and expr[0] in ("-name", "-path") and expr[2] == "-prune" and expr[3] in ("-o", "-or"):
        expr = expr[4:]
    if expr[-1:] == ["-delete"]:
        expr = expr[:-1]
    else:
        k = next((j for j, t in enumerate(expr) if t in ("-exec", "-execdir")), None)
        if k is None or expr[-1:] not in ([";"], ["+"]) or any(t in (";", "+") for t in expr[k + 1 : -1]):
            return None
        expr = expr[:k]
    names, nocase, i = [], False, 0
    while i < len(expr):
        t = expr[i]
        if t in ("-name", "-iname") and i + 1 < len(expr):
            g = expr[i + 1]
            if "[" in g or "\\" in g or (t == "-iname" and not g.isascii()):
                return None  # find's case folding differs from Python's beyond ASCII
            names.append(g)
            nocase = nocase or t == "-iname"
            i += 2
        elif t in _FIND_TESTS and i + 1 < len(expr):
            i += 2
        elif t in _FIND_FLAGS:
            i += 1
        else:
            return None
    return (names, nocase) if names else None


_WALK_LIMIT = 200_000
_TOO_BIG = "the project is too big to check what this find matches by name; search a narrower directory (`find src tests -name …`)"


def _named_hit(
    names: list[str], nocase: bool, root: Path, patterns: list[str], own: bool = True, start: str | None = None
) -> tuple[str | None, str | None]:
    """(the protected path a find from `start` (the root by default) reaches by
    name, or None; why it couldn't be checked, or None). A matched name reaches
    a protected path when it is one, is a directory holding one (`-exec rm -rf
    {} +`) or is a link to one."""
    if not patterns:
        return None, None
    globs = [n.casefold() for n in names] if nocase else names
    real = start or os.path.realpath(str(root))
    name = os.path.basename(real)
    if own and any(fnmatch.fnmatchcase(name.casefold() if nocase else name, g) for g in globs):
        rel = _rel(real, root)  # the start itself matches
        hit = contains_protected(rel, patterns) or _tree_holds(real, root, patterns)
        if hit:
            return hit, None
    protected: list[tuple[str, str]] = []
    matched_dirs: list[str] = []
    seen = 0
    for dirpath, dirnames, filenames in os.walk(real):
        for n, is_dir in [(d, True) for d in dirnames] + [(f, False) for f in filenames]:
            seen += 1
            if seen > _WALK_LIMIT:
                return None, _TOO_BIG
            rel = _rel(os.path.join(dirpath, n), root)
            hit = matches(rel, patterns)
            if hit:
                protected.append((rel, hit))
            name = n.casefold() if nocase else n
            if not any(fnmatch.fnmatchcase(name, g) for g in globs):
                continue
            if hit:
                return hit, None
            path = os.path.join(dirpath, n)
            if os.path.islink(path):  # written through: its target
                target = os.path.realpath(path)
                trel = _rel(target, root)
                if not _outside(trel):
                    hit = contains_protected(trel, patterns) if os.path.isdir(target) else matches(trel, patterns)
                    if hit:
                        return hit, None
            if is_dir:
                hit = contains_protected(rel, patterns)
                if hit:
                    return hit, None
                matched_dirs.append(rel)
    for rel, hit in protected:
        if any(rel.startswith(d + "/") for d in matched_dirs):
            return hit, None
    return None, None


_VIMS = {"vim", "vi", "nvim", "vimdiff", "view", "ex"}
_VIM_EX = re.compile(r"-[AbCdDfFghHlLmMnNRrsvxXyZ]*[eE][AbCdDfFghHlLmMnNRrsxXyZeE]*")  # ex mode, alone or among flags that take no value (`-es`, `-Nes`, `-Xe`); a `v` after it is normal mode again


@dataclass
class _InPlace:
    """An in-place edit: its script text, its files and where they come from."""

    script: str
    files: list[str]


def _sed_args(args: list[str]) -> tuple[bool, list[str], list[str], list[str]]:
    """sed's (in place?, scripts, script files, files)."""
    inplace, scripts, sfiles, files = False, [], [], []
    i = 0
    only = False
    while i < len(args):
        a = args[i]
        nxt = args[i + 1] if i + 1 < len(args) else ""
        if only or a == "-" or not a.startswith("-"):
            files.append(a)
        elif a == "--":
            only = True
        elif a in ("-e", "--expression"):
            scripts.append(nxt)
            i += 1
        elif a.startswith("--expression="):
            scripts.append(a.split("=", 1)[1])
        elif a in ("-f", "--file"):
            sfiles.append(nxt)
            i += 1
        elif a.startswith("--file="):
            sfiles.append(a.split("=", 1)[1])
        elif a.startswith("--in-place"):
            inplace = True
        elif a in ("-l", "--line-length"):
            i += 1
        elif not a.startswith("--"):
            cluster = a[1:]
            for k, ch in enumerate(cluster):
                rest = cluster[k + 1 :]
                if ch == "i":
                    inplace = True
                    if a == "-i" and nxt == "":  # BSD's `-i ''`
                        i += 1
                    break
                if ch in "ef":
                    v = rest or nxt
                    if not rest:
                        i += 1
                    (scripts if ch == "e" else sfiles).append(v)
                    break
                if ch == "l":
                    if not rest:
                        i += 1
                    break
        i += 1
    if not scripts and not sfiles and files:
        scripts.append(files.pop(0))
    return inplace, scripts, sfiles, files


def _perl_args(args: list[str]) -> tuple[bool, list[str], list[str]]:
    """perl's (in place?, code, files)."""
    inplace, code, files = False, [], []
    i = 0
    while i < len(args):
        a = args[i]
        nxt = args[i + 1] if i + 1 < len(args) else ""
        if a == "--":
            files += args[i + 1 :]
            break
        if a == "-" or not a.startswith("-"):
            files.append(a)
        else:
            cluster = a[1:]
            for k, ch in enumerate(cluster):
                rest = cluster[k + 1 :]
                if ch == "i":
                    inplace = True
                    break  # the rest is the backup suffix
                if ch in "eE":
                    code.append(rest or nxt)
                    if not rest:
                        i += 1
                    break
                if ch in "IMmFCdDx0l":
                    if ch in "IM" and not rest:
                        i += 1
                    break
        i += 1
    if not code and files:
        code.append(files.pop(0))  # a script file: its name, not its text
    return inplace, code, files


def _awk_args(args: list[str]) -> tuple[bool, list[str], list[str]]:
    """awk/gawk's (in place?, program, files)."""
    inplace, prog, files = False, [], []
    has_prog_file = False
    i = 0
    while i < len(args):
        a = args[i]
        nxt = args[i + 1] if i + 1 < len(args) else ""
        if a == "--":
            files += args[i + 1 :]
            break
        if a in ("-i", "--include"):
            inplace = inplace or nxt in ("inplace", "inplace.awk")
            i += 1
        elif a.startswith(("-i", "--include=")):
            inplace = inplace or a.split("=", 1)[-1].removeprefix("-i") in ("inplace", "inplace.awk")
        elif a in ("-f", "--file"):
            has_prog_file = True
            i += 1
        elif a in ("-e", "--source"):
            prog.append(nxt)
            i += 1
        elif a in ("-v", "--assign", "-F", "--field-separator"):
            i += 1
        elif a.startswith("-") and a != "-":
            pass
        else:
            files.append(a)
        i += 1
    if not prog and not has_prog_file and files:
        prog.append(files.pop(0))
    files = [f for f in files if not re.match(r"^[A-Za-z_]\w*=", f)]
    return inplace, prog, files


def _inplace_edit(toks: list[str]) -> _InPlace | None:
    """sed -i, perl -i and awk -i inplace: their script and files, else None."""
    cmd = Path(toks[0]).name
    if cmd == "sed":
        inplace, scripts, sfiles, files = _sed_args(toks[1:])
        text = "\n".join(scripts)
    elif cmd == "perl":
        inplace, code, files = _perl_args(toks[1:])
        text = "\n".join(code)
    else:
        inplace, prog, files = _awk_args(toks[1:])
        text = "\n".join(prog)
    return _InPlace(text, files) if inplace else None


def _vim_edit(toks: list[str], stdin: bool = False) -> _InPlace | None:
    """vim/vi/nvim run with a script (-c, --cmd, +cmd, -S, -s, ex mode, or
    `stdin`: commands or keys given on it): what it runs and the files it
    edits; None when it is interactive."""
    values = {"-c", "--cmd", "-S", "-u", "-U", "-i", "-T", "-W", "-w", "-t", "-q", "-r"}
    exmode = Path(toks[0]).name == "ex" or any(_VIM_EX.fullmatch(a) for a in toks[1:])
    script: list[str] = []
    files: list[str] = []
    scripted = exmode or stdin
    i = 1
    while i < len(toks):
        a = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        if a in values or (a == "-s" and not exmode):
            if a in ("-c", "--cmd", "-S", "-s"):
                scripted = True
                script.append(nxt)
            if a == "-s":
                files.append(nxt)  # if ex mode wasn't seen, `-s` is "silent" and this is the file it edits
            i += 2
            continue
        if a.startswith("+"):
            scripted = True
            script.append(a[1:])
        elif a == "--":
            files += toks[i + 1 :]
            break
        elif not a.startswith("-"):
            files.append(a)
        i += 1
    return _InPlace("\n".join(script), files) if scripted else None


_SEARCHERS = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "fd", "fdfind", "find"}


def _glob_dir(pathspec: str, cdir: str | None) -> str:
    """A pathspec's directory: itself, or for a glob (`'src/*.py'`, `'*.yml'`)
    the literal directory before it, which it matches anywhere below."""
    if pathspec.startswith(":"):
        # A magic pathspec (`:/`, `:(top)`, `:(icase)`, `:!`) can reach anything from the repo's top, whatever
        # the cwd: `/`, which holds every project, so what it feeds is never taken as seen.
        return "/"
    m = _GLOB_CHARS.search(pathspec)
    if not m:
        return pathspec
    head = pathspec[: m.start()]
    d = head.rsplit("/", 1)[0] if "/" in head else ""
    return d or cdir or "."


def _search_roots(words: list[str], cwd: str | None) -> list[str] | None:
    """The directories a producer of file names searches (`grep -rl x src`,
    `git ls-files`, `find .`), its cwd when it names none; None when it
    doesn't search."""
    if not words:
        return None
    name = Path(words[0]).name
    g = _git(words)
    if g:
        _, args, cdir = g
        if args[:1] not in (["ls-files"], ["grep"]):
            return None
        rest = args[1:]
        if "--" in rest:
            paths = rest[rest.index("--") + 1 :]
        else:
            plain = [a for a in rest if not a.startswith("-")]
            explicit = any(a in ("-e", "-f") for a in rest)
            paths = plain[1:] if args[0] == "grep" and not explicit else plain
        # A pathspec glob (`'*.yml'`) matches anywhere below: the whole tree.
        return [_glob_dir(p, cdir) for p in paths] or [cdir or "."]
    if name not in _SEARCHERS:
        return None
    if name == "find":
        return _find_starts(words) or ["."]
    args = words[1:]
    recursive = name not in ("grep", "egrep", "fgrep") or any(
        a in ("-r", "-R", "--recursive", "--dereference-recursive") or (re.fullmatch(r"-[a-zA-Z]+", a) and set(a[1:]) & {"r", "R"}) for a in args
    )
    explicit = any(a in ("-e", "-f", "--regexp", "--file") or a.startswith(("--regexp=", "--file=")) for a in args)
    skip = set(_opt_values(["x", *args], ("-e", "-f", "--regexp", "--file", "-m", "--max-count", "-A", "-B", "-C", "-g", "--glob", "-t", "--type", "--include", "--exclude")))
    plain = [a for a in args if not a.startswith("-") and a not in skip]
    paths = plain if explicit and name not in ("fd", "fdfind") else plain[1:]
    if not paths:
        return ["."] if recursive else None
    return paths


def _producer_words(word: str) -> list[str] | None:
    """The command inside a `$(…)` or backtick word."""
    k = word.find("$(")
    if k >= 0:
        toks, _ = _lex(word, k + 2, stop_paren=True)
    elif "`" in word:
        j = word.index("`")
        toks = _lex(word[j + 1 : _backtick_end(word, j)])[0]
    else:
        return None
    for item in _simple(toks):
        if isinstance(item, _Cmd) and item.words:
            return _strip_prefix(item.words)[0]
    return []


_PLAIN_WORD = re.compile(r"""^[^'"\\$`%\s]+$""")


def _fed_by_xargs(seg: Seg, root: Path, t: _Targets, tree: bool) -> None:
    """A writer run by xargs (`echo x | xargs rm`, `xargs -I% rm %`): its targets
    are what the producer names, or unknown when that can't be read exactly."""
    if not seg.fed:
        return
    unknown = "the file names xargs gives this command can't be seen here; name the files"
    if seg.fed_file or seg.piped is None:
        t.unknown = t.unknown or unknown
        return
    words, cwd = seg.piped.words, seg.piped.cwd
    name = Path(words[0]).name if words else ""
    named: list[str] | None = None
    if name == "echo" and not any(w.startswith("-") and "e" in w for w in words[1:2]):
        args = [w for w in words[1:] if not re.fullmatch(r"-[neE]+", w)]
        named = args if all(_PLAIN_WORD.match(w) for w in args) else None
    elif name == "printf" and len(words) >= 2 and words[1] in ("%s\\n", "%s\n", "%s\\0", "%s "):
        named = words[2:] if all(_PLAIN_WORD.match(w) for w in words[2:]) else None
    else:
        roots = _search_roots(words, cwd)
        if roots is not None:
            t.searched += [(r, cwd) for r in roots]
            return
    if named is None:
        t.unknown = t.unknown or unknown
        return
    if cwd != seg.cwd:  # the producer named them from another directory
        t.unknown = t.unknown or unknown
        return
    t.files += named
    if tree:
        t.trees += named


def _named_files(files: list[str], seg: Seg, root: Path, t: _Targets) -> None:
    """The files an in-place edit names, or (fed by xargs or `$(…)`) those its
    producer names, or why they can't be seen when it searches a tree that holds
    a protected path."""
    producers: list[tuple[list[str], str | None]] = []
    for f in files:
        if "$(" in f or "`" in f:
            w = _producer_words(f)
            producers.append((w or [], seg.cwd))
        else:
            t.files.append(f)
    if not files and seg.piped is not None:
        producers.append((seg.piped.words, seg.piped.cwd))
    for words, cwd in producers:
        name = Path(words[0]).name if words else ""
        if name in ("echo", "printf"):
            t.files += [w for w in words[1:] if not w.startswith("-")]
            continue
        if name == "cat":  # a list of files, one a line
            for f in [w for w in words[1:] if not w.startswith("-")]:
                t.files += (_read_text(f, cwd) or "").split()
            continue
        for r in _search_roots(words, cwd) or []:
            t.searched.append((r, cwd))


def _brief(text: str) -> str:
    return text if len(text) <= 80 else text[:79] + "…"


def _brace_overflow(target: str) -> str | None:
    """Why the guard can't place a write target: more brace expanding than
    it does, which main's guard couldn't decide either (it ran out of time)."""
    if _brace_words(target, _BRACE_LIMIT + 1)[1]:
        return f"can't tell which files `{_brief(target)}` names (more brace lists than the guard expands); name them"
    return None


# How much brace expansion the guard does for one word: past it (main's guard ran out of time from about
# 30 lists, and broke at about 1,000), the word is one it can't place.
_BRACE_STEPS_READ = 1_000  # brace lists opened
_BRACE_WORK_READ = 20_000_000  # characters scanned


def _first_brace_list(word: str) -> tuple[tuple[int, int, list[str]] | None, int]:
    """((start, end, parts) of the word's first top-level `{a,b}` list, or
    None; how many characters were scanned to find it)."""
    first = word.find("{")
    if first < 0:
        return None, 0
    depth = 0
    start = 0
    for i in range(first, len(word)):
        c = word[i]
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
                    return (start, i, parts), i + 1
    return None, len(word)


@functools.lru_cache(maxsize=256)
def _brace_words(word: str, limit: int) -> tuple[tuple[str, ...], bool]:
    """(the first `limit` words, in bash's order; whether the word needs more
    expanding than the guard does)."""
    out: list[str] = []
    stack = [iter((word,))]  # each level makes its words only as they are needed
    steps = work = 0
    while stack and len(out) < limit:
        w = next(stack[-1], None)
        if w is None:
            stack.pop()
            continue
        m, scanned = _first_brace_list(w)
        work += scanned
        if m is None:
            out.append(w)
            continue
        steps += 1
        if steps > _BRACE_STEPS_READ or work > _BRACE_WORK_READ:
            return (), True
        stack.append(_brace_choices(w, *m))
    return tuple(out), False


def _brace_choices(word: str, s: int, e: int, parts: list[str]):
    """The words a brace list at `word[s:e + 1]` stands for, one at a time."""
    for p in parts:
        yield word[:s] + p + word[e + 1 :]


def _braces(word: str, limit: int = 64) -> list[str]:
    """Bash brace expansion of `{a,b}` lists (not `{1..3}`): the first
    `limit` words, in bash's order. A word with more lists than the guard
    expands comes back as more than `limit` copies of itself, which a caller
    checking for more reads as too many."""
    words, too_big = _brace_words(word, limit)
    return [word] * (limit + 1) if too_big else list(words)


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


_TREE_WALK_LIMIT = 50_000


def _tree_holds(abspath: str, root: Path, patterns: list[str]) -> str | None:
    """A protected path on disk inside the directory `abspath` (in the project)
    that a pattern matching anywhere (`**/.env`) reaches; the patterns' literal
    directories are `contains_protected`'s. Past the walk's limit, None."""
    loose = [p for p in patterns if not _literal_dir(p)]
    if not loose or not os.path.isdir(abspath):
        return None
    seen = 0
    for dirpath, dirnames, filenames in os.walk(abspath):
        for n in dirnames + filenames:
            seen += 1
            if seen > _TREE_WALK_LIMIT:
                return None
            hit = matches(_rel(os.path.join(dirpath, n), root), loose)
            if hit:
                return hit
    return None


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
        if _outside(rel):  # outside the project: none of its protected paths, unless it holds the project
            if tree and _holds_root(a, root) and patterns:
                return patterns[0]
            continue
        hit = (contains_protected(rel, patterns) or _tree_holds(a, root, patterns)) if tree else matches(rel, patterns)
        if hit:
            return hit
    return None


def _global_config_problem(seg: Seg, t: _Targets) -> str | None:
    """A write to the global git config (~/.gitconfig, ~/.config/git/, the file
    $GIT_CONFIG_GLOBAL names), which can hold aliases, hooks and push settings."""
    named = [(x, False) for x in t.files] + [(x, True) for x in t.trees + t.links]
    for tgt, tree in named:
        over = _brace_overflow(_expand_known(tgt))
        if over:
            return f"{over}, since it may write the global git config, which can hold aliases, hooks and push settings"
        for c in _candidates(_expand_known(tgt), seg.cwd):
            if not c.strip():
                continue
            a = _abspath(c, seg.cwd)
            hit = global_config_hit(a, tree) if a else (_global_config_name(c.strip()) and c)
            if hit:
                return f"writing `{tgt}` changes the global git config ({hit}), which can hold aliases, hooks and push settings; it isn't changed in these sessions"
    toks = seg.words
    if toks and _INTERP.match(Path(toks[0]).name):
        code = _inline_code(toks)
        if _WRITE_CALL.search(code):
            for lit in re.findall(r"""['"]([^'"\n]+)['"]""", code):
                p = lit.strip().lstrip("+<>").strip()
                a = _abspath(p, seg.cwd) if p and not re.search(r"\s", p) else None
                if a and global_config_hit(a):
                    return f"this one-liner writes the global git config `{p}`; it isn't changed in these sessions"
    return None


def _shell_protected(seg: Seg, patterns: list[str], root: Path, t: _Targets | None = None) -> str | None:
    t = t if t is not None else _write_targets(seg, root)
    if t.unknown:
        return t.unknown
    for r, cwd in t.searched:
        a = _abspath(r, cwd)
        rel = _rel(a, root) if a else ""
        if a is None or _holds_root(a, root) or (not _outside(rel) and (contains_protected(rel, patterns) or _tree_holds(a, root, patterns))):
            return (
                f"this changes the files a search of `{r}` finds, which can reach protected paths, so the guard "
                "can't see which files change; name the files, or search a narrower directory that holds no protected path "
                "(to delete what a find matches, use `find … -delete`)"
            )
    unknown_dir = "; the shell's directory can't be followed here (after `cd -`, `cd ~` or `cd $X`), so use a path from the project root"
    for tgt in t.files + t.trees + t.links:
        over = _brace_overflow(tgt)
        if over:
            return over
    for tgt in t.files:
        hit = _protected_hit(tgt, seg, root, patterns, tree=False)
        if hit:
            return f"writing `{tgt}` touches a protected path ({hit})" + (unknown_dir if seg.cwd is None else "")
    for tgt in t.trees:
        hit = _protected_hit(tgt, seg, root, patterns, tree=True)
        if hit:
            return f"writing into, removing or moving `{tgt}` touches a protected path ({hit})" + (unknown_dir if seg.cwd is None else "")
    for names, nocase, own, start in t.named_from_root:
        hit, unchecked = _named_hit(names, nocase, root, patterns, own, start)
        if unchecked:
            return unchecked
        if hit:
            return f"this find from the project root matches a protected path ({hit}) by name; search a narrower directory"
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
                if p and not re.search(r"\s", p):
                    rel = _norm(p, root, seg.cwd)
                    if not _outside(rel) and matches(rel, patterns):
                        return f"this one-liner writes the protected path `{p}`"
    return None


_WRITE_CALL = re.compile(
    r"""\bopen\s*\([^)]*['"](?:[rwxabt]*[wax+][rwxabt+]*|\+?[<>]{1,2}[^'"]*)['"]|\bwrite\w*\s*\(|\.write\b|writeFile|appendFile|"""
    r"""\bunlink|\brmtree\b|\brmdir|\brename|\breplace\s*\(|\bcopy\w*\s*\(|\bmove\s*\(|\bremove\s*\(|\brmSync\b|\bsymlink|\bchmod\b|\btruncate\b|\bmkdir"""
)


# Skip markers in editing scripts. Each tool's script is read by its own
# grammar, so text it writes (sed's `a`/`i`/`c`, a perl string) is never taken
# for an address, and an `s` inside an address is never taken for a command.
# A backslash always starts an escape (`\/` doesn't end a body, as in sed), so
# each character has one reading and nothing backtracks. Where a script can't
# be read, the rest of it counts as added, as written.

_PUT_ESCAPES = {"n": "\n", "t": "\t", "r": "\r"}


def _markers(text: str) -> int:
    """Skip markers in text a command writes, read with sed's and perl's escapes
    (`\\n`, `it\\.only\\(`; `\\s` is a plain `s`)."""
    plain = re.sub(r"\\(.)", lambda m: _PUT_ESCAPES.get(m.group(1), m.group(1)), text or "", flags=re.S)
    return len(_SKIP.findall(plain))


def _found(text: str) -> int:
    """Skip markers a regex finds. A backslash and a letter or digit (`\\s`,
    `\\b`, `\\1`) is a class, an anchor or a backreference, never that letter."""
    plain = re.sub(r"\\(.)", lambda m: "\0" if m.group(1).isascii() and m.group(1).isalnum() else m.group(1), text or "", flags=re.S)
    return len(_SKIP.findall(plain))


@functools.lru_cache(maxsize=256)
def _body(delims: str, newline: bool) -> re.Pattern:
    """A body up to one of `delims`, escapes included; within one line unless `newline`."""
    stop = re.escape(delims) + ("" if newline else "\n")
    return re.compile(r"(?:\\.|[^\\" + stop + "])*", re.S if newline else 0)


def _close(text: str, start: int, d: str, newline: bool = True) -> int | None:
    """Where the body starting at `start` ends at delimiter `d`, else None."""
    end = _body(d, newline).match(text, start).end()
    return end if end < len(text) and text[end] == d else None


_PAIRS = {"{": "}", "(": ")", "[": "]", "<": ">"}


def _close_pair(text: str, start: int, o: str) -> int | None:
    """Where a bracketed body (perl's `m{…}`, `q(…)`) ends, nesting counted."""
    c, depth, pos = _PAIRS[o], 1, start
    while True:
        pos = _body(o + c, True).match(text, pos).end()
        if pos >= len(text) or text[pos] not in (o, c):  # the end, or a lone backslash before it
            return None
        depth += 1 if text[pos] == o else -1
        if depth == 0:
            return pos
        pos += 1


def _script_net(text: str, dialect: str) -> int:
    """Skip markers an editing script adds, net of those it removes: an `s`
    command counts what it puts less what it finds; an address or a regex only
    finds; text it writes is added."""
    text = text or ""
    if dialect == "sed":
        return _sed_net(text)
    if dialect == "ex":
        return _ex_net(text)
    return _code_net(text, perl=dialect != "awk")


# sed: commands start after a newline, `;`, `{` or `}`, each with up to two
# addresses (`/re/`, `\%re%`, a line number, `$`, `first~step`, `+N`).
_SED_GAP = re.compile(r"[\s;{}]*")
_SED_LINE_ADDR = re.compile(r"\d+(?:~\d+)?|\$|[+~]\d+")
_SED_SPACES = re.compile(r"[ \t]*")
_SED_TEXT = re.compile(r"(?:\\.|[^\\\n])*\\?", re.S)  # `a`/`i`/`c` text: one line, continued past an escaped newline
_SED_REST = re.compile(r"[^\n]*")
_SED_LABEL = re.compile(r"[^;\n]*")
_SED_FLAGS = re.compile(r"[gpiImMe0-9]*")
_SED_ADDR_FLAGS = re.compile(r"[IM]*")
_SED_END = re.compile(r"[ \t]*(?:[;\n}#]|$)")
_SED_ARG = re.compile(r"[ \t]*[\d.]*")  # `q`'s exit code, `l`'s line length, `v`'s version
_SED_SIMPLE = "dDgGhHlLnNpPqQxzF=v"


def _sed_net(text: str) -> int:
    net, pos, n = 0, 0, len(text)
    while True:
        pos = at = _SED_GAP.match(text, pos).end()  # `at`: where this command starts
        if pos >= n:
            return net
        for second in (False, True):
            m = _SED_LINE_ADDR.match(text, pos)
            if m:
                pos = m.end()
            elif text[pos : pos + 1] in ("/", "\\"):
                d = "/" if text[pos] == "/" else text[pos + 1 : pos + 2]
                start = pos + (1 if text[pos] == "/" else 2)
                end = _close(text, start, d, newline=False) if d and d not in "\n\\" else None
                if end is None:
                    return net + _markers(text[at:])
                pos = end + 1
                pos = _SED_ADDR_FLAGS.match(text, pos).end()
            elif second:
                return net + _markers(text[at:])  # a `,` with no address after it
            else:
                break
            pos = _SED_SPACES.match(text, pos).end()
            if second or text[pos : pos + 1] != ",":
                break
            pos = _SED_SPACES.match(text, pos + 1).end()
        while text[pos : pos + 1] in ("!", " ", "\t"):
            pos += 1
        c = text[pos : pos + 1]
        if c in ("", "\n", ";", "{", "}"):
            continue
        if c == "#":  # a comment: sed writes nothing of it
            pos = _SED_REST.match(text, pos).end()
        elif c in "aic":
            p = _SED_SPACES.match(text, pos + 1).end()
            if text[p : p + 2] == "\\\n":  # the classic form: the text starts on the next line
                p += 2
            m = _SED_TEXT.match(text, p)
            net += _markers(m.group(0))
            pos = m.end()
        elif c in "sy":
            d = text[pos + 1 : pos + 2]
            e1 = _close(text, pos + 2, d, newline=False) if d and d not in "\n\\" else None
            e2 = _close(text, e1 + 1, d, newline=False) if e1 is not None else None
            if e2 is None:
                return net + _markers(text[at:])
            found, put = text[pos + 2 : e1], text[e1 + 1 : e2]
            net += _markers(put) - (_found(found) if c == "s" else 0)
            pos = _SED_FLAGS.match(text, e2 + 1).end() if c == "s" else e2 + 1
            if c == "s" and text[pos : pos + 1] == "w":  # `w file`: the file name runs to the line's end
                m = _SED_REST.match(text, pos)
                net += _markers(m.group(0))
                pos = m.end()
        elif c in ":btT":
            m = _SED_REST.match(text, pos) if c == ":" else _SED_LABEL.match(text, pos)
            net += _markers(m.group(0))
            pos = m.end()
        elif c in "rRwWe":  # a file name or a command, to the line's end
            m = _SED_REST.match(text, pos)
            net += _markers(m.group(0))
            pos = m.end()
        elif c in _SED_SIMPLE:
            pos = _SED_ARG.match(text, pos + 1).end() if c in "qQlLv" else pos + 1
        else:
            return net + _markers(text[at:])
        if not _SED_END.match(text, pos):  # sed refuses more after a command; so is it read
            return net + _markers(text[at:])


# ed and vim: one command per line (vim's `|` joins more after an `s`), with a
# range of addresses before it. An `s` ends at the end of its line, and its
# closing delimiter may be left out.
_EX_LEAD = re.compile(r"[\s:]*")
_EX_LINE_ADDR = re.compile(r"[.$%]|\d+|'.|\\[/?&]|[+-]\d*")
_EX_OFFSET = re.compile(r"(?:[ \t]*[+-]\d*)*")
_EX_GLOBAL = re.compile(r"(?:g(?:l(?:o(?:b(?:al?)?)?)?)?!?|v(?:g(?:l(?:o(?:b(?:al?)?)?)?)?)?)(?=[^\w\s\"|\\])")
_EX_SUBST = re.compile(r"s(?:u(?:b(?:s(?:t(?:i(?:t(?:u(?:te?)?)?)?)?)?)?)?)?(?=[^\w\s\"|\\])")
_EX_FLAGS = re.compile(r"[&cegiInp#lr]*[ \t]*\d*[ \t]*")
_EX_APPEND = re.compile(r"(?:a(?:ppend)?|i(?:nsert)?|c(?:hange)?)!?\s*$")
# `normal` keys run into the text they insert (`normal Oit.only(`), so there a
# marker is matched without the word boundary before it.
_EX_KEYS = re.compile(r"\b(?:norm(?:al?)?|exe(?:c(?:u(?:te?)?)?)?)\b")
_SKIP_IN_KEYS = re.compile("|".join(p.removeprefix(r"\b") for p in SKIP_MARKERS))


def _ex_net(text: str) -> int:
    net, lines, i = 0, text.split("\n"), 0
    while i < len(lines):
        n, appending = _ex_line(lines[i])
        net += n
        i += 1
        if appending:  # `a`, `i`, `c`: the lines up to a lone `.` are written as they are
            while i < len(lines) and lines[i] != ".":
                net += len(_SKIP.findall(lines[i]))
                i += 1
            i += 1
    return net


def _ex_line(line: str) -> tuple[int, bool]:
    """One line of ed or vim commands: (its net markers, whether it starts appending)."""
    net, pos = 0, 0
    while True:
        pos = _EX_LEAD.match(line, pos).end()
        while True:  # the range: addresses, with or without `,` or `;` between them
            m = _EX_LINE_ADDR.match(line, pos)
            if m:
                pos = m.end()
            elif line[pos : pos + 1] in ("/", "?"):
                end = _close(line, pos + 1, line[pos], newline=False)
                if end is None:
                    return net, False  # a pattern that runs to the line's end only finds
                pos = end + 1
            elif line[pos : pos + 1] not in (",", ";"):
                break
            pos = _EX_OFFSET.match(line, pos).end()
            if line[pos : pos + 1] in (",", ";"):
                pos += 1
        pos = _SED_SPACES.match(line, pos).end()
        m = _EX_GLOBAL.match(line, pos)
        if m:  # `g/re/cmd`: the pattern only finds, the rest is a command
            end = _close(line, m.end() + 1, line[m.end()], newline=False)
            if end is None:
                return net, False
            pos = end + 1
            continue
        m = _EX_SUBST.match(line, pos)
        if m:
            d, p = line[m.end()], m.end() + 1
            e1 = _close(line, p, d, newline=False)
            e2 = _close(line, e1 + 1, d, newline=False) if e1 is not None else None
            found = line[p : len(line) if e1 is None else e1]
            put = "" if e1 is None else line[e1 + 1 : len(line) if e2 is None else e2]
            net += _markers(put) - _found(found)
            pos = len(line) if e1 is None or e2 is None else _EX_FLAGS.match(line, e2 + 1).end()
            if line[pos : pos + 1] == "|":
                pos += 1
                continue
            return net + _markers(line[pos:]), False
        if _EX_APPEND.match(line, pos):
            return net, True
        if _EX_KEYS.search(line, pos):  # `normal` or `execute`, after `silent!`, `bufdo` or not
            return net + len(_SKIP_IN_KEYS.findall(line, pos)), False
        return net + _markers(line[pos:]), False  # anything else: what it holds counts


# perl and awk: a string, a comment or other code is kept and counted; a regex
# (`/re/` where a term is expected, `m…`, `qr…`) only finds; `s///` nets.
_CODE_TOKEN = re.compile(r"""\s+|\\.|&&|\|\||->|[$@%&][\w:#]*|[A-Za-z_]\w*|\d[\w.]*|.""", re.S)
_CODE_EXPECT_TERM = {
    "if", "unless", "while", "until", "and", "or", "not", "xor", "return", "split", "grep", "map", "print",
    "push", "unshift", "join", "when", "eq", "ne", "lt", "gt", "le", "ge", "cmp", "x", "defined", "in",
}
_CODE_REGEX_FLAGS = re.compile(r"[A-Za-z]*")
_QUOTE_LIKE = {"s", "m", "qr", "q", "qq", "qw", "tr", "y"}
_CODE_SIGIL_AFTER = {"my", "our", "local", "state", "keys", "values", "each", "delete", "exists", "scalar", "ref", "defined", "undef"}


def _code_net(text: str, perl: bool = True) -> int:
    net, kept, last, pos, term, n = 0, [], 0, 0, False, len(text)
    prev, before, bare = "", False, False  # the last token, whether a term came before it, whether it was a bareword

    def rest() -> int:  # from where the script can't be read, everything left counts
        return net + _markers(" ".join(kept) + " " + text[last:])

    while pos < n:
        c = text[pos]
        if c in "'\"`":  # a string: kept, and nothing in it is read as code
            end = _close(text, pos + 1, c)
            if end is None:
                return rest()
            pos, term, bare = end + 1, True, False
            continue
        if c == "#":  # a comment: kept
            end = text.find("\n", pos)
            pos = n if end < 0 else end
            continue
        if c == "/" and not term:  # a regex: it only finds
            end = _close(text, pos + 1, "/")
            if end is None:
                return rest()
            kept.append(text[last:pos] + " ")
            pos = last = end + 1
            pos, term, bare = _CODE_REGEX_FLAGS.match(text, pos).end(), True, False  # its flags stay kept
            continue
        if term and not bare and c in "%&*" and not text.startswith("&&", pos):  # after a value, an operator (`$a % s/…/`); after `my`, a sigil
            pos, term, before, prev, bare = pos + 1, False, True, c, False
            continue
        m = _CODE_TOKEN.match(text, pos)
        word = m.group(0)
        at = None  # where a quote-like operator's delimiter is
        # Not a method (`->s`), nor a file test or glob (`-s $f`, `*s`) where `-` or `*` starts a term.
        named = prev == "->" or (prev in ("-", "*") and text[pos - 1] in "-*" and not before and text[pos - 2 : pos - 1] not in ("-", "*"))
        if perl and word in _QUOTE_LIKE and not named:
            # perl allows space before the delimiter (`s /a/b/`) and takes any other
            # character as one (`s,a,b,`); only `=>` makes it a word. What can't be
            # told apart (a hash's `{s}`, a comment before the delimiter) counts as added.
            q = _CODE_SPACE.match(text, m.end()).end()
            d = text[q : q + 1]
            if d == "}" or (q > m.end() and (d == "#" or d.isalnum() or d == "_")):
                return rest()
            if d != "" and not text.startswith("=>", q):
                at = q
        if at is not None and word == "s":
            sub = _perl_s(text, at)
            if sub is None:
                return rest()
            found, put, end = sub
            net += _markers(put) - _found(found)
            kept.append(text[last:pos] + " ")
            pos = last = end
            pos, term, bare = _CODE_REGEX_FLAGS.match(text, pos).end(), True, False
            continue
        if at is not None:
            p, d = at + 1, text[at]
            end = _close_pair(text, p, d) if d in _PAIRS else _close(text, p, d)
            if end is not None and word in ("tr", "y"):  # what it writes is its second part
                end = None if d in _PAIRS else _close(text, end + 1, d)
            if end is None:
                return rest()
            if word in ("m", "qr"):
                kept.append(text[last:pos] + " ")
                last = end + 1
            pos, term, bare = _CODE_REGEX_FLAGS.match(text, end + 1).end(), True, False
            continue
        pos = m.end()
        if not word.isspace():  # after a term a `/` divides; elsewhere it starts a regex
            before, prev = term, word
            term = (word[0].isalnum() or word[0] in "_$@%&)]}\\") and word not in _CODE_EXPECT_TERM and word != "&&"
            bare = word in _CODE_SIGIL_AFTER  # `my %s`: a sigil follows, not an operator
    return rest()


_CODE_SPACE = re.compile(r"\s*")


def _perl_s(text: str, p: int) -> tuple[str, str, int] | None:
    """perl's `s` from its first delimiter at `p`: (what it finds, what it puts,
    where it ends), or None when it can't be read. A bracketed pattern
    (`s{…}`, `s(…)`) is followed by the replacement's own delimiters, as perl
    reads it: `s{a}{b}`, `s{a}/b/`, `s(a) [b]`."""
    d = text[p]
    if d not in _PAIRS:
        e1 = _close(text, p + 1, d)
        e2 = _close(text, e1 + 1, d) if e1 is not None else None
        return None if e2 is None else (text[p + 1 : e1], text[e1 + 1 : e2], e2 + 1)  # type: ignore[index]
    e1 = _close_pair(text, p + 1, d)
    if e1 is None:
        return None
    q = _CODE_SPACE.match(text, e1 + 1).end()
    d2 = text[q : q + 1]
    if d2 == "" or d2.isalnum() or d2 in "_#\\":  # `#` after a space starts a comment: not read
        return None
    e2 = _close_pair(text, q + 1, d2) if d2 in _PAIRS else _close(text, q + 1, d2)
    return None if e2 is None else (text[p + 1 : e1], text[q + 1 : e2], e2 + 1)


def _patch_net(texts: list[str]) -> int:
    """A patch's added lines less its removed ones, read as the file's own text."""
    added = removed = 0
    for txt in texts:
        for line in txt.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added += len(_SKIP.findall(line[1:]))
            elif line.startswith("-") and not line.startswith("---"):
                removed += len(_SKIP.findall(line[1:]))
    return added - removed


_GREPS = {"grep", "egrep", "fgrep", "rg", "ag", "ack"}


# The most script text the guard reads for one command (an in-place edit's
# scripts and `-f` files together), and the most patch text. Over it, a ticket
# session's command is refused rather than read in part.
_SCRIPT_CAP = 1_000_000
_PATCH_CAP = 4_000_000


def _size(text: str) -> int:
    return len(text.encode("utf-8", "replace"))


def _stdin_script(seg: Seg, cap: int) -> tuple[str | None, int, bool]:
    """What a command reads on standard input, up to `cap` bytes: its heredoc,
    its `<` file or a `cat` piped in, as (text, bytes, whether there is more).
    None when the guard can't see it."""
    if seg.stdins > 1 or seg.stdin_unseen:
        return None, 0, False
    if seg.heredoc is not None:
        size = _size(seg.heredoc)
        return seg.heredoc, size, size > cap
    if seg.stdin:
        return _read_sized(seg.stdin, seg.cwd, cap)
    return _piped_sized(seg, cap)


def _added_markers(seg: Seg, root: Path) -> int | str:
    """Skip or focus markers the writing command itself puts in, net of what it
    removes; or why its script can't be read in full. Text another command
    merely searches for (a grep) doesn't count."""
    toks = seg.words
    cmd = Path(toks[0]).name if toks else ""
    too_big = f"a script of over {_SCRIPT_CAP:,} bytes, more than the guard reads; split it into smaller scripts"
    if (seg.stdins > 1 or seg.stdin_unseen) and (cmd in ("sed", "ed", "red") or cmd in _VIMS):
        return "more than one input on stdin (heredocs, here-strings or `<` files), or one from another descriptor, which the guard can't follow; give it one"
    if cmd in ("sed", "perl", "awk", "gawk"):
        ed = _inplace_edit(toks)
        if ed is not None:
            text = ed.script
            left = _SCRIPT_CAP - _size(text)  # bytes, for the scripts and `-f` files together
            if cmd == "sed":
                stdin_read = False
                for f in _sed_args(toks[1:])[2]:
                    if f in ("-", "/dev/stdin") and stdin_read:  # `-` shares one stream, `/dev/stdin` reopens it
                        return "more than one script from standard input; give it once"
                    elif f in ("-", "/dev/stdin"):  # sed reads the script from standard input
                        stdin_read = True
                        txt, size, over = _stdin_script(seg, max(left, 0))
                        if txt is None and not over:
                            return "a script from standard input, which the guard can't see; give it with -e or as a file"
                    else:
                        txt, size, over = _read_sized(f, seg.cwd, max(left, 0))
                        if txt is None and not over:
                            if _abspath(f, seg.cwd) is None:
                                return f"the script `{f}` in a directory the guard can't tell; run it from a known directory"
                            return f"the script `{f}`, which the guard can't read: write it in an earlier command, as a plain file, or give it with -e"
                    if over:
                        return too_big
                    left -= size
                    text += "\n" + (txt or "")
            if left < 0:
                return too_big
            return _script_net(text, {"sed": "sed", "perl": "code"}.get(cmd, "awk"))
    if cmd in ("ed", "red") or cmd in _VIMS:
        given = bool(seg.stdin) or seg.heredoc is not None or seg.piped is not None
        ed = _vim_edit(toks, stdin=given) if cmd in _VIMS else None
        script = ed.script if ed else ""
        # ed and vim's ex mode take stdin as commands; vim otherwise as keys typed.
        exmode = cmd in ("ed", "red", "ex") or any(_VIM_EX.fullmatch(a) for a in toks[1:])
        stdin, size, over = _stdin_script(seg, _SCRIPT_CAP) if given else ("", 0, False)
        if over:
            return too_big
        if stdin is None:
            if seg.stdin:
                return f"commands from `{seg.stdin}`, which the guard can't read"
            return "commands on stdin from another command, which the guard can't see; give them in a heredoc" + ("" if cmd in ("ed", "red") else " or with -c")
        if size + _size(script) > _SCRIPT_CAP:
            return too_big
        if exmode:
            return _script_net(script + "\n" + stdin, "ex")
        # Keys typed: `:` commands among them are read as ex commands too, and the most counts.
        keys = max(len(_SKIP_IN_KEYS.findall(stdin)), len(_SKIP_IN_KEYS.findall(re.sub(r"\\(.)", r"\1", stdin))), _script_net(stdin, "ex"))
        return _script_net(script, "ex") + keys
    if cmd == "patch" or (cmd == "git" and (_git(toks) or ([], [], None))[1][:1] in (["apply"], ["am"])):
        if cmd == "patch":
            texts = _patch_texts("patch", toks[1:], seg)[0]
        else:
            args = _git(toks)[1]  # type: ignore[index]
            texts = _patch_texts("git" if args[0] == "apply" else "git-am", args[1:], seg)[0]
        return _patch_net(texts)
    if cmd in _GREPS:
        return 0  # copies lines that are already there
    text = " ".join(toks[1:]) + "\n" + (seg.heredoc or "")
    p = seg.piped
    if p is not None and not (p.words and Path(p.words[0]).name in _GREPS):
        text += "\n" + " ".join(p.words[1:]) + "\n" + (p.heredoc or "")
    return _markers(text)


def _shell_skips(seg: Seg, profile: Profile, root: Path, t: _Targets | None = None) -> str | None:
    t = t if t is not None else _write_targets(seg, root)
    tests = [tgt for tgt in t.files if (rel := _norm(tgt, root, seg.cwd)) and not _outside(rel) and matches(rel, profile.test_paths)]
    if not tests:
        return None
    added = _added_markers(seg, root)  # once for the command, however many files it edits
    if isinstance(added, str):
        return f"this edits the test file `{tests[0]}` with {added}"
    if added > 0:
        return f"this writes a skip or focus marker into the test file `{tests[0]}`; skipping or disabling a test is never allowed"
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


# Variables that point git at other config or another repository.
_GIT_ENV = re.compile(r"^(GIT_CONFIG\w*|GIT_DIR|GIT_WORK_TREE|GIT_NAMESPACE|GIT_COMMON_DIR|HOME|XDG_CONFIG_HOME)(\+?=|$)")
_DECLARES = ("export", "declare", "typeset", "local", "readonly")


_CREATE_SHORT = re.compile(r"-[a-zA-Z]*?[bBcC](.*)")  # `-B x`, `-Bx`, `-fBx`, `-qB x`
_CREATE_LONG = ("--create", "--force-create", "--orphan")


def _switched_to(args: list[str], d: str | None) -> tuple[bool, str | None]:
    """(whether `git checkout`/`git switch`/`git symbolic-ref HEAD` changes the
    branch, the branch it leaves checked out or None when that can't be told).
    A checkout of files (`--`, a path, more than one name, `HEAD`) changes none."""
    if args[:1] == ["symbolic-ref"]:
        rest = [a for j, a in enumerate(args[1:], 1) if not a.startswith("-") and args[j - 1] != "-m"]
        return (True, _dst(rest[1])) if rest[:1] == ["HEAD"] and len(rest) > 1 else (False, None)
    if not args or args[0] not in ("checkout", "switch") or "--" in args or "-p" in args or "--patch" in args:
        return False, None  # `-p` copies changes in, on the same branch
    names: list[str] = []
    track = False
    i = 1
    while i < len(args):
        a = args[i]
        if a in _CREATE_LONG and i + 1 < len(args):
            return True, args[i + 1]
        m = _CREATE_SHORT.fullmatch(a) if not a.startswith("--") else None
        if m:
            name = m.group(1) or (args[i + 1] if i + 1 < len(args) else "")
            return True, name or None
        if a.startswith(tuple(o + "=" for o in _CREATE_LONG)):
            return True, a.split("=", 1)[1]
        if a in ("--detach", "-d") or (args[0] == "switch" and re.fullmatch(r"-[a-zA-Z]*d[a-zA-Z]*", a)):
            return True, None
        if a in ("-t", "--track") or a.startswith("--track="):
            track = True
        elif a == "-" or not a.startswith("-"):
            names.append(a)
        i += 1
    if not names or (args[0] == "checkout" and len(names) > 1) or names[0] == "HEAD":
        return False, None
    t = names[0]
    if t == "-" or _SOLO_UNSAFE_REF.search(t) or t.startswith("@"):
        return True, None  # the previous branch, or one the kit can't read
    if track:  # `--track origin/main` makes and checks out `main`
        return True, t.split("/", 1)[1] if "/" in t else t
    if args[0] == "checkout" and not _git_out(d, "show-ref", "--verify", f"refs/heads/{t}") and d and os.path.exists(os.path.join(d, t)):
        return False, None  # a path, not a branch
    return True, t


# ---------- solo mode: GitHub-side changes to the base branch ----------

_SOLO_API_HINT = "spell out the call's path, method and body"
# GraphQL mutations that change a branch (refs are named by id, and a branch
# name may come in a variable, so any of them may be the base branch), its
# protection, or a ruleset. Creating a ruleset is left to the ask: it is how a
# project leaves solo mode.
_SOLO_GQL = re.compile(
    r"\b(updateRefs?|deleteRef|renameRef|createCommitOnBranch|mergeBranch|createBranchProtectionRule|"
    r"updateBranchProtectionRule|deleteBranchProtectionRule|updateRepositoryRuleset|deleteRepositoryRuleset)\b"
)
_EXPANDS = re.compile(r"[$`]")
# What makes a curl call one to GitHub's API, or one that may be: its host, or a
# path only GitHub's API has.
_GITHUB_HINT = re.compile(
    r"(?i)(?:api|uploads)\.github\.com|/api/v3\b|/rulesets\b|/protection\b|/git/refs\b|/branches/|/merges\b|/merge-upstream\b|/contents/"
)
_CURL_SHORT_VALUE = set("AbcCdDeEFHKmoPQrtTuUwxXyYz")
_CURL_LONG_VALUE = {
    "request", "data", "data-raw", "data-binary", "data-ascii", "data-urlencode", "json", "form", "form-string",
    "upload-file", "config", "header", "url", "output", "user", "user-agent", "referer", "cookie", "cookie-jar",
    "proxy", "max-time", "write-out", "cert", "key", "cacert", "connect-timeout", "retry", "range", "variable",
    "url-query", "oauth2-bearer", "netrc-file", "output-dir", "trace", "trace-ascii", "trace-config", "resolve",
    "connect-to", "retry-delay", "retry-max-time", "limit-rate", "unix-socket", "abstract-unix-socket", "aws-sigv4",
    "proxy-user", "dns-servers", "interface", "local-port", "max-filesize", "max-redirs", "speed-limit", "speed-time",
    "time-cond", "keepalive-time", "dump-header", "stderr", "capath", "key-type", "cert-type", "pinnedpubkey",
    "ciphers", "proto", "proto-redir", "request-target", "service-name", "socks5", "socks5-hostname", "noproxy",
    "preproxy", "happy-eyeballs-timeout-ms", "expect100-timeout", "login-options", "mail-from", "mail-rcpt",
    "ftp-port", "quote", "delegation", "hostpubmd5", "hostpubsha256", "krb", "pass", "tls-max", "tlsuser",
    "tlspassword", "hsts", "alt-svc", "etag-save", "etag-compare", "ech", "ipfs-gateway", "haproxy-clientip",
}  # fmt: skip
_CURL_LONG_FLAGS = {"get", "head", "globoff", "next", "path-as-is"}
# An abbreviated long option counts as the first of these it may stand for.
_CURL_PRIORITY = ("request", "data", "json", "form", "upload-file", "config", "url", "variable", "get", "head", "next", "globoff")
# gh's own command groups; another first word is an alias or an extension.
_GH_GROUPS = {
    "agent-task", "alias", "api", "attestation", "auth", "browse", "cache", "co", "codespace", "completion", "config",
    "copilot", "extension", "gist", "gpg-key", "help", "issue", "label", "org", "pr", "preview", "project", "release",
    "repo", "ruleset", "run", "search", "secret", "ssh-key", "status", "variable", "version", "workflow",
}  # fmt: skip


def _another_repo(name: str | None, repo: str) -> bool:
    """Whether `name` (OWNER/REPO, as gh or a URL takes it) is literally another
    repository than the project's; one the kit can't read counts as the project's."""
    if not name or not repo or _SOLO_UNSAFE_REF.search(name):
        return False
    return _repo_name(name) != repo.casefold()


def _solo_branch(b: str | None, base: str) -> str | None:
    """"change" when `b` is the base branch (in any case, as the MCP check reads
    it), "unknown" when the kit can't read it (None, empty, or filled in by the shell)."""
    if b is None:
        return "unknown"
    b = urllib.parse.unquote(b).removeprefix("refs/").removeprefix("heads/")
    if b.casefold() == base.casefold():
        return "change"
    return "unknown" if _SOLO_UNSAFE_REF.search(b) or not b else None


def _solo_branches(values: list[str | None], base: str) -> str | None:
    """The worst of `_solo_branch` over every value a field may take."""
    kinds = {_solo_branch(v, base) for v in values}
    return "change" if "change" in kinds else "unknown" if "unknown" in kinds else None


def _json_pairs(text: str) -> list[tuple[str, object]] | None:
    """Every key and value in a JSON text, at any depth and duplicates kept
    (GitHub reads the last); None when it isn't JSON."""
    pairs: list[tuple[str, object]] = []

    def hook(ps):
        pairs.extend(ps)
        return dict(ps)

    try:
        json.loads(text, object_pairs_hook=hook)
    except (ValueError, RecursionError):
        return None
    return pairs


@dataclass
class _Body:
    """What a request sends, as far as the kit can read it: `fields` are the
    name=value pairs (gh's `-f`, a JSON body's keys, every value kept), and
    `unread` says some of it can't be read (a file not there yet, stdin, a name
    the shell fills in), so any field may be in it."""

    fields: list[tuple[str, str | None]]
    unread: bool = False

    def get(self, key: str) -> list[str | None]:
        """Every value `key` may take; [] when it isn't sent."""
        out = [v for k, v in self.fields if k == key]
        return out + [None] if self.unread else out

    def add_text(self, text: str | None) -> None:
        """A body's text: JSON's keys, else the `"key": "value"` pairs it holds."""
        if text is None:
            self.unread = True
            return
        pairs = _json_pairs(text)
        if pairs is None:
            self.fields += [(k, v) for k, v in re.findall(r'"(\w+)"\s*:\s*"([^"\\]*)"', text)]
            if re.search(r"\\u|\\[\"/]", text):  # escapes this reading doesn't decode
                self.unread = True
            return
        self.fields += [(k, v if isinstance(v, str) else None) for k, v in pairs if isinstance(k, str)]


def _api_path(path: str) -> str:
    """A request path as GitHub reads it: decoded, dot segments removed, with
    no host, `api/v3/` prefix or slashes around it."""
    p = re.sub(r"(?i)^[a-z][\w+.-]*://[^/]*", "", path) if "://" in path else path  # any host, one the shell fills in too
    p = urllib.parse.unquote(p.split("?", 1)[0].split("#", 1)[0])
    p = posixpath.normpath("/" + p.lstrip("/")).strip("/")
    p = re.sub(r"(?i)^api/v3/", "", p)
    p = re.sub(r"^repositories/\d+(?=/|$)", "repos/{id}/{id}", p)  # the same repository, by its id
    return "graphql" if re.fullmatch(r"(?i)(?:api/)?graphql", p) else p


# What a repository's issues, pull requests and the like live under: a path the
# shell fills in after one of these never reaches a branch, its protection or a ruleset.
_PLAIN_RESOURCES = r"issues|pulls|labels|milestones|releases|check-runs|check-suites|statuses|commits|comments|deployments|actions|projects|discussions|assignees|collaborators|notifications|hooks|keys|forks|invitations|environments|pages|subscription|stargazers"


def _plain_resource(path: str) -> bool:
    """Whether a path with parts the shell fills in is plainly not one this
    check is about: under a repository's literal issues, pull requests and the
    like, or outside `repos/`, `orgs/` and `repositories/` altogether."""
    if re.search(r"(?:^|/)(?:rulesets|protection|branches|git|refs|merges|merge-upstream|contents)(?:/|$)", path):
        return False  # a refused part after what the shell fills in: `issues/$X/../rulesets/1`
    if re.match(rf"(?:repos/[^/]+/[^/]+|repos/[^/]*[$`][^/]*|repositories/[^/]+)/(?:{_PLAIN_RESOURCES})(?:/|$)", path):
        return True
    first = path.split("/", 1)[0]
    return not _EXPANDS.search(first) and first not in ("repos", "orgs", "repositories") and "rulesets" not in path


def _solo_rest(method: str, path: str, base: str, body: _Body, repo: str = "") -> SoloRefusal | None:
    """Solo mode: a REST call (`path` as `_api_path` gives it) to the project's
    repository `repo` (or its owner's rulesets) that changes the base branch,
    its name or protection, the default branch, or a ruleset (other than
    creating one)."""
    unknown = bool(_EXPANDS.search(method)) or method == "?"
    if method in ("GET", "HEAD"):
        return None
    if not path or (_EXPANDS.search(path) and not _plain_resource(path)):
        return SoloRefusal("a GitHub API call whose path the shell fills in", "unknown", _SOLO_API_HINT)
    m = re.match(r"repos/([^/]+/[^/]+)", path)
    if m and _another_repo(m.group(1), repo):
        return None
    m = re.match(r"orgs/([^/]+)/", path)
    if m and repo and not _SOLO_UNSAFE_REF.search(m.group(1)) and m.group(1).casefold() != repo.split("/")[0].casefold():
        return None
    call = f"`{method} {path}`" if not unknown else f"`{path}`, with a method the kit can't read,"
    if unknown:
        method = "a write"
    m = re.fullmatch(r"(?:repos/[^/]+/[^/]+|orgs/[^/]+)/rulesets(/.*)?", path)
    if m:
        if not m.group(1) and method == "POST":
            return None  # creating a ruleset: asked
        if unknown:
            return SoloRefusal(f"{call} may change or remove a ruleset, which is what protects `{base}`", "unknown", _SOLO_API_HINT)
        return SoloRefusal(f"{call} changes or removes a ruleset, which is what protects `{base}`")
    # A branch's name may hold slashes: the base branch is matched as itself first.
    b = re.escape(base)
    m = re.fullmatch(rf"repos/[^/]+/[^/]+/(?:branches/(?:(?i:{b})|(.+?))/(protection(?:/.*)?|rename)|git/refs/heads/(?:(?i:{b})|(.+)))", path)
    if m:
        named = m.group(1) if m.group(2) else m.group(3)
        kind = "change" if named is None else _solo_branch(named, base)
        if kind:
            what = "name" if m.group(2) == "rename" else "protection" if m.group(2) else "branch"
            return SoloRefusal(f"{call} changes `{base}`'s {what}" if kind == "change" else f"{call} names its branch with something the kit can't read", kind, _SOLO_API_HINT)
        return None
    if re.fullmatch(r"repos/[^/]+/[^/]+/git/refs", path):
        values = body.get("ref")
        kind = _solo_branches(values, base) if values else None
        if kind:
            return SoloRefusal(f"{call} makes a ref the kit reads as `{base}`'s, or can't read", kind, _SOLO_API_HINT)
        return None
    if re.fullmatch(r"repos/[^/]+/[^/]+", path):
        if any(k == "default_branch" for k, _ in body.fields):
            return SoloRefusal(f"{call} changes the default branch, which is `{base}`")
        if body.unread:
            return SoloRefusal(f"{call} sends a body the kit can't read, which may change the default branch", "unknown", _SOLO_API_HINT)
        return None
    for tail, key, what in (("merges", "base", "merges a branch straight into"), ("merge-upstream", "branch", "updates"), ("contents/.+", "branch", "writes a file straight to")):
        if re.fullmatch(rf"repos/[^/]+/[^/]+/{tail}", path):
            values = body.get(key)
            kind = "change" if not values else _solo_branches(values, base)  # none named: the default branch
            if kind:
                return SoloRefusal(f"{call} {what} `{base}`, or a branch the kit can't read", kind, _SOLO_API_HINT)
            return None
    return None


def _solo_graphql(text: str, base: str, literal: bool = False) -> SoloRefusal | None:
    """The refusal for a GraphQL text: by the mutation fields a `literal` query
    calls (so a name in a string is only text), else by any name in it."""
    calls = _mutation_calls(text) if literal else None
    if calls is not None:
        names = [f for f, _ in calls]
        m = next((_SOLO_GQL.fullmatch(n) for n in names if _SOLO_GQL.fullmatch(n)), None)
        if "createRef" not in names:
            text = ""
    else:
        m = _SOLO_GQL.search(text)
    if m:
        return SoloRefusal(f"the GraphQL mutation `{m.group(1)}` changes a branch, its protection or a ruleset, and the kit can't tell it isn't `{base}`'s")
    if re.search(r"\bcreateRef\b", text) and re.search(rf"refs/heads/{re.escape(base)}(?![\w/.-])", text, re.I):
        return SoloRefusal(f"the GraphQL mutation `createRef` makes `refs/heads/{base}`")
    return None


_WHOLE_VAR = re.compile(r"\s*(?:\$\w+|\$\{[^}]*\}|\$\(.*\)|`.*`)\s*", re.S)


def _gql_unread(queries: list[str | None]) -> bool:
    """A query the kit can't read at all: a file not there yet, stdin, or one
    variable or substitution (a query's own `$var`s are GraphQL's)."""
    return any(q is None or _WHOLE_VAR.fullmatch(q) for q in queries)


def _gql_literal(q: str) -> bool:
    """Whether a query's `$`s are all GraphQL variables its operation declares
    (`query($o: String!)`), not the shell's."""
    if "`" in q or re.search(r"\$[({]", q):
        return False
    declared = set(re.findall(r"\$(\w+)\s*:", q))
    return all(n in declared for n in re.findall(r"\$(\w+)", q))


def _writes_file(raw: str, f: str) -> bool:
    """Whether the command writes the file `f`: a redirect or `tee` into it, or
    `cp`/`mv`/`install`/`sed -i` naming it. Read word by word, in linear time."""
    name = f.removeprefix("./")

    def same(w: str) -> bool:
        return w.strip("'\"").removeprefix("./") == name

    if re.search(rf"(?:>|\btee(?:\s+-a)?)[ \t]*['\"]?(?:\./)?{re.escape(name)}(?![\w.-])", raw):
        return True
    for part in re.split(r"[;&|\n()]", raw):
        words = part.split()
        if not words:
            continue
        cmd = Path(words[0]).name
        if cmd in ("cp", "mv", "install") and any(same(w) for w in words[1:]):
            return True
        if cmd == "sed" and any(w.startswith("-i") or w == "--in-place" for w in words[1:]) and any(same(w) for w in words[1:]):
            return True
    return False


def _gql_queries(queries: list[str | None], cwd: str | None, raw: str = "") -> list[str | None]:
    """The queries, a `$(cat FILE)` one read from its file (unread when the
    command also writes the file)."""
    out: list[str | None] = []
    for q in queries:
        m = re.fullmatch(r"\s*\$\(\s*cat\s+([^\s$`;&|<>()]+)\s*\)\s*", q or "")
        f = m.group(1).strip("'\"") if m else ""
        written = bool(f) and _writes_file(raw, f)
        out.append(None if written else _read_text(f, cwd) if m else q)
    return out


def _gql_text(queries: list[str | None], fallback) -> tuple[str, bool]:
    """The GraphQL text to look for mutations in, and whether it is only the
    queries themselves (every one read, none filled in by the shell); else the
    queries with `fallback()` (the whole command and the files it reads)."""
    if queries and all(q is not None and (not _EXPANDS.search(q) or _gql_literal(q)) for q in queries):
        return "\n".join(q for q in queries if q), True
    return "\n".join(q for q in queries if q) + "\n" + fallback(), False


def _solo_gql(queries: list[str | None], fallback, base: str, cwd: str | None = None, strict: bool = True) -> SoloRefusal | None:
    """Solo mode: a GraphQL request's refusal, from its queries (`fallback()`
    when they hold expansions); with `strict`, a query the kit can't read at
    all counts as a mutation that changes the base branch."""
    queries = _gql_queries(queries, cwd, fallback())
    text, literal = _gql_text(queries, fallback)
    r = _solo_graphql(text, base, literal)
    if not r and strict and _gql_unread(queries):
        r = SoloRefusal("a GraphQL request whose query the kit can't read, which may be a mutation that changes a branch or a ruleset", "unknown", _SOLO_API_HINT)
    return r


@dataclass
class _CurlCall:
    method: str  # "?" when a config file, `--next` or `--expand-*` may set it
    urls: list[str]
    body: _Body
    data: list[str | None]  # the data texts, None for one the kit can't read
    unsure: bool  # a config file, `--variable` or `--expand-*`: the URL may be anywhere
    globs: bool  # curl expands `{…}` and `[…]` in the URLs
    hinted: bool = False  # a config file that names GitHub, or can't be read


def _curl_long(name: str) -> str:
    """A long option as curl reads it, abbreviations included."""
    if name in _CURL_LONG_VALUE or name in _CURL_LONG_FLAGS or name.startswith("expand-"):
        return name
    cands = [o for o in (*_CURL_LONG_VALUE, *_CURL_LONG_FLAGS) if o.startswith(name)]
    for o in _CURL_PRIORITY:
        if o in cands:
            return o
    return cands[0] if len(cands) == 1 else name


def _curl_call(toks: list[str], cwd: str | None) -> _CurlCall:
    """A curl command's method, URLs and body, as far as the kit can read them."""
    method = None
    urls: list[str] = []
    data: list[str | None] = []
    upload = get = head = unsure = nxt_seen = hinted = False
    globoff = False

    def _option(flag: str, value: str) -> None:
        nonlocal method, upload, unsure, hinted
        if flag in ("X", "request"):
            method = value
        elif flag in ("d", "F", "json", "form", "form-string") or flag.startswith("data"):
            v = value.split("=", 1)[1] if flag in ("F", "form") and "=" in value else value
            if flag == "data-urlencode" and "@" in v:
                v = "@" + v.split("@", 1)[1]
            if v.startswith("@") and flag not in ("data-raw", "form-string"):
                f = v[1:]
                data.append(None if _STDIN_FILE.fullmatch(f) else _read_text(f, cwd))
            else:
                data.append(v)
        elif flag in ("T", "upload-file"):
            upload = True
        elif flag in ("K", "config", "variable"):
            unsure = True
            if flag != "variable":
                text = None if _STDIN_FILE.fullmatch(value) else _read_text(value, cwd)
                if text is not None and not _GITHUB_HINT.search(text) and not re.search(r"(?im)^\s*-?-?(?:url|request|x)\b", text):
                    unsure = False  # a config the kit has read, with nothing for GitHub in it
                elif text is not None and _GITHUB_HINT.search(text):
                    hinted = True  # it names GitHub (an unread one counts only beside GitHub in the command)
        elif flag == "url":
            urls.append(value)

    i = 1
    while i < len(toks):
        t = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        if t == "--":
            urls += toks[i + 1 :]
            break
        if t.startswith("--") and len(t) > 2:
            raw_name, eq, val = t[2:].partition("=")
            name = _curl_long(raw_name)
            takes = name in _CURL_LONG_VALUE or name.startswith("expand-")
            if name == "get":
                get = True
            elif name == "head":
                head = True
            elif name == "globoff":
                globoff = True
            elif name == "next":
                nxt_seen = True
            elif name.startswith("expand-"):
                unsure = True
                if name == "expand-url":
                    urls.append(val if eq else nxt)
            elif takes:
                _option(name, val if eq else nxt)
            i += 2 if takes and not eq else 1
            continue
        if t.startswith("-") and len(t) > 1:
            used_next = False
            for j, c in enumerate(t[1:], 1):
                if c in _CURL_SHORT_VALUE:
                    value = t[j + 1 :] or nxt
                    used_next = not t[j + 1 :]
                    _option(c, value)
                    break
                if c == "G":
                    get = True
                elif c == "I":
                    head = True
                elif c == "g":
                    globoff = True
                elif c == ":":
                    nxt_seen = True
            i += 2 if used_next else 1
            continue
        urls.append(t)
        i += 1
    if unsure or nxt_seen:
        verb = "?"
    elif method is not None:
        verb = method.upper()
    else:
        verb = "HEAD" if head else "GET" if get else "PUT" if upload else "POST" if data else "GET"
    body = _Body([])
    for d in data:
        body.add_text(d)
    return _CurlCall(verb, urls, body, data, unsure, not globoff and any(re.search(r"[{\[]", u) for u in urls), hinted)


def _curl_github_path(url: str) -> str | None:
    """The API path of a curl URL to GitHub (github.com's API hosts, or a
    server's `/api/v3/` and `/api/graphql`), else None. curl takes a URL
    without a scheme too."""
    m = re.match(r"(?i)(?:[a-z][\w+.-]*://)?(?:[^/@\s]*@)?([^/\s?#]+)(.*)", url)
    if not m:
        return None
    host = m.group(1).split(":", 1)[0].rstrip(".").casefold()
    path = _api_path(m.group(2) or "/")
    if host in ("api.github.com", "uploads.github.com"):
        return path
    local = host in ("localhost", "0.0.0.0", "[::1]") or host.startswith("127.") or host.endswith((".local", ".localhost", ".test"))
    rest = urllib.parse.unquote(m.group(2).lstrip("/"))
    if re.match(r"(?i)api/v3/", rest) or not local and re.match(r"(?i)api/graphql/?(?:[?#]|$)", rest):
        return path  # a GitHub Enterprise server
    if _EXPANDS.search(host) and (path == "graphql" or re.match(r"(?:repos|orgs|repositories)/", path)):
        return path  # a host the shell fills in (`$GITHUB_API_URL`), with GitHub's API paths
    return None


def _solo_curl(toks: list[str], seg: Seg, base: str, repo: str, raw: str, read) -> SoloRefusal | None:
    c = _curl_call(toks, seg.cwd)
    if c.method in ("GET", "HEAD"):
        return None
    hint = _GITHUB_HINT.search(" ".join(c.urls))
    if (c.unsure or seg.fed) and (hint or c.hinted or _GITHUB_HINT.search(raw)):
        return SoloRefusal("a curl call whose URL or method comes from a config file, a curl variable or xargs, and may be GitHub's", "unknown", _SOLO_API_HINT)
    if c.globs and hint:
        return SoloRefusal("a curl URL with `{…}` or `[…]`, which curl expands into other URLs", "unknown", _SOLO_API_HINT)
    for u in c.urls:
        whole = bool(_WHOLE_VAR.fullmatch(u))
        if _EXPANDS.search(u) and (_GITHUB_HINT.search(u) or whole and _GITHUB_HINT.search(raw)) and not ("/" in u.split("://", 1)[-1] and _plain_resource(_api_path(u.split("://", 1)[-1].split("/", 1)[1]))):
            return SoloRefusal(f"the curl URL {_code_span(u)} is filled in by the shell", "unknown", _SOLO_API_HINT)
        path = _curl_github_path(u)
        if path is None:
            continue
        if path == "graphql":
            texts: list[str | None] = []
            for d in c.data:
                pairs = _json_pairs(d) if d is not None else None
                qs = [v for k, v in pairs or [] if k == "query"]
                texts += [v if isinstance(v, str) else None for v in qs] if pairs is not None else [d]
            # Another host's `/api/graphql` may be a GitHub Enterprise server or an
            # app's own: only a mutation the kit sees is refused there.
            r = _solo_gql(texts, lambda: raw + "\n" + read(), base, seg.cwd, strict=bool(re.search(r"(?i)\bapi\.github\.com", u)))
        else:
            r = _solo_rest(c.method, path, base, c.body, repo)
        if r:
            return r
    return None


def _gh_aliases() -> dict[str, str] | None:
    """gh's aliases from its config file (`aliases:` in config.yml), None when
    the file can't be read."""
    d = os.environ.get("GH_CONFIG_DIR") or os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "gh")
    text = _read_text(os.path.join(d, "config.yml"), None)
    if text is None:
        return None
    m = re.search(r"(?m)^aliases:[ \t]*\n((?:[ \t]+.*\n?)*)", text)
    out: dict[str, str] = {}
    for line in (m.group(1) if m else "").splitlines():
        a = re.match(r"\s+([^:\s]+):\s*(.*)$", line)
        if a:
            v = a.group(2).strip()
            out[a.group(1).strip("'\"")] = v[1:-1] if len(v) > 1 and v[0] == v[-1] and v[0] in "'\"" else v
    return out


# `gh pr merge` and `gh repo edit` options whose value is text, never an option.
_GH_TEXT_OPTS = {
    "-b", "--body", "-F", "--body-file", "-t", "--subject", "-A", "--author-email", "--match-head-commit",
    "--description", "-h", "--homepage", "--add-topic", "--remove-topic", "--visibility", "--template",
}  # fmt: skip


def _unread_words(toks: list[str]) -> bool:
    """Whether a `gh pr merge`/`gh repo edit` holds a word the shell fills in that
    may be an option (`--admin`, `--default-branch`): not an option's text value,
    the pull request or repository named first, or a quoted heredoc."""
    sub_at = 2
    positional_seen = False
    for j in range(sub_at + 1, len(toks)):
        t, prev = toks[j], toks[j - 1]
        if toks[1:3] == ["repo", "edit"] and prev == "-d":
            continue  # `gh repo edit -d` is the description (`gh pr merge -d` deletes the branch)
        if not _EXPANDS.search(t) or prev in _GH_TEXT_OPTS or re.match(r"--[\w-]+=", t) and t.split("=", 1)[0] in _GH_TEXT_OPTS:
            positional_seen = positional_seen or not t.startswith("-") and prev not in _GH_TEXT_OPTS
            continue
        if not positional_seen and prev not in ("-R", "--repo"):
            positional_seen = True  # the pull request (`"$PR"`) or repository
            continue
        return True
    return False


def _aliases_set_in(raw: str) -> dict[str, str]:
    """The gh aliases a command sets (`gh alias set NAME EXPANSION`), which a
    later part of it may use."""
    out: dict[str, str] = {}
    for m in re.finditer(r"\bgh\s+alias\s+set\s+((?:'[^']*'|\"[^\"]*\"|[^\s;&|'\"])+)\s+('[^']*'|\"[^\"]*\"|[^\s;&|'\"]+)", raw):
        try:
            name, exp = shlex.split(m.group(1))[0], shlex.split(m.group(2))[0]
        except (ValueError, IndexError):
            continue
        out[name] = exp
    return out


# An alias that may merge with --admin, change the default branch, write through
# the API or run a shell; a read through `api` is not one.
_GH_ALIAS_RISK = re.compile(
    r"--admin\b|--default-branch\b|\bcurl\b|^\s*!|\bapi\b.*(?:\s-X\s*(?!GET\b)\S|--method\b(?!\s*=?\s*GET\b)|\s-[fF]\b|--(?:raw-)?field\b|--input\b|\bgraphql\b)",
    re.I,
)


def _solo_gh(toks: list[str], seg: Seg, profile: Profile, raw: str, read, depth: int = 0) -> SoloRefusal | None:
    base = profile.base_branch
    group, sub = _gh_group(toks)
    if group == "alias" and sub in ("set", "import"):
        words = [t for t in toks[toks.index(sub) + 1 :] if not t.startswith("-")]
        text = " ".join(words[1:]) if sub == "set" else (_read_text(words[0], seg.cwd) if words and words[0] != "-" else None)
        if text is None or _GH_ALIAS_RISK.search(text):
            return SoloRefusal("a gh alias that may merge with `--admin`, change the default branch or call the API", "unknown", "spell the gh command out instead of an alias")
        return None
    if group and group not in _GH_GROUPS and not group.startswith("-"):
        aliases = {**(_gh_aliases() or {}), **_aliases_set_in(raw)}
        exp = aliases.get(group)
        if exp is None:
            return None  # an extension, or a typo: gh says so
        if exp.startswith("!") or depth > 4:
            return SoloRefusal(f"the gh alias `{group}` runs a shell command, or other aliases, the kit doesn't follow", "unknown", _SOLO_API_HINT)
        try:
            words = shlex.split(exp)
        except ValueError:
            return SoloRefusal(f"the gh alias `{group}` can't be read", "unknown", _SOLO_API_HINT)
        at = toks.index(group)
        return _solo_gh([toks[0], *words, *toks[at + 1 :]], seg, profile, raw, read, depth + 1)
    if group in ("pr", "repo") and _another_repo(_gh_repo(toks, group, sub), profile.repo):
        return None
    if (group, sub) in (("pr", "merge"), ("repo", "edit")) and _unread_words(toks):
        return SoloRefusal(f"`gh {group} {sub}` with words the shell fills in, which may be `--admin` or `--default-branch`", "unknown", _SOLO_API_HINT)
    if group == "pr" and sub == "merge" and any(t == "--admin" or t.startswith("--admin=") for t in toks):
        return SoloRefusal(f"`gh pr merge --admin` merges into `{base}` past its required checks")
    if group == "repo" and sub == "edit" and any(t == "--default-branch" or t.startswith("--default-branch=") for t in toks):
        return SoloRefusal(f"`gh repo edit --default-branch` changes the default branch, which is `{base}`")
    call = _api(toks)
    if call is None:
        return None
    path = _api_path(call.path) if call.path else ""
    if seg.fed and call.method != "GET" and not (path and _plain_resource(path)):
        return SoloRefusal("xargs gives this `gh api` call its path or fields, which the kit can't see", "unknown", _SOLO_API_HINT)
    body = _Body([])
    queries: list[str | None] = []
    for f in call.fields:
        k, _, v = f.partition("=")
        if _EXPANDS.search(k):
            body.unread = True
        val: str | None = v
        if v.startswith("@") and f in _raw_fields(toks):
            val = None if _STDIN_FILE.fullmatch(v[1:]) else _read_text(v[1:], seg.cwd)
            val = val.strip() if val is not None and k != "query" else val
        body.fields.append((k, val))
        if k == "query":
            queries.append(val)
    for f in _input_files(toks):
        text = (_stdin_text(seg) or _echoed(seg)) if _STDIN_FILE.fullmatch(f) else _read_text(f, seg.cwd)
        body.add_text(text)
        pairs = _json_pairs(text) if text is not None else None
        queries += [v if isinstance(v, str) else None for k, v in pairs or [] if k == "query"] if text is not None and pairs is not None else [None]
    if path == "graphql":
        return _solo_gql(queries, lambda: call.rest + "\n" + raw + "\n" + read(), base, seg.cwd)
    return _solo_rest(call.method, path, base, body, profile.repo)


def _echoed(seg: Seg) -> str | None:
    """The text a plain `echo` or one-argument `printf` pipes into the command,
    when the shell fills nothing in."""
    w = seg.piped.words if seg.piped is not None else []
    opts = []
    for x in w[1:]:  # echo's leading options, however many
        if not re.fullmatch(r"-[neE]+", x):
            break
        opts.append(x)
    escapes = any("e" in x for x in opts)  # `echo -e` turns `\x5f` into other text
    if seg.stdins or seg.stdin_unseen or seg.stdin or escapes and any("\\" in x for x in w[1:]):
        return None  # the command's own stdin, or escapes the kit doesn't decode
    if not w or Path(w[0]).name not in ("echo", "printf") or any(_EXPANDS.search(x) for x in w[1:]):
        return None
    args = [x for x in w[1:] if not (Path(w[0]).name == "echo" and re.fullmatch(r"-[neE]+", x))]
    if Path(w[0]).name == "printf" and (len(args) != 1 or "%" in args[0] or "\\" in args[0]):
        return None
    return " ".join(args)


def _raw_fields(toks: list[str]) -> set[str]:
    """The `-F`/`--field` values of a `gh api` command (gh reads `@file` in these only)."""
    out: set[str] = set()
    for j, t in enumerate(toks):
        if t in ("-F", "--field") and j + 1 < len(toks):
            out.add(toks[j + 1])
        elif t.startswith("--field="):
            out.add(t.split("=", 1)[1])
        elif re.fullmatch(r"-i*F.+", t):
            v = t[t.index("F") + 1 :]
            out.add(v[1:] if v.startswith("=") else v)
    return out


def _input_files(toks: list[str]) -> list[str]:
    """The files `gh api --input` sends as the body."""
    out = []
    for j, t in enumerate(toks):
        if t == "--input" and j + 1 < len(toks):
            out.append(toks[j + 1])
        elif t.startswith("--input="):
            out.append(t.split("=", 1)[1])
    return out


def _solo_github(seg: Seg, profile: Profile, raw: str, read) -> SoloRefusal | None:
    """Solo mode: a `gh` or `curl` command that changes the base branch through
    GitHub: `gh pr merge --admin`, the default branch, the base branch's name,
    ref or protection, a ruleset, a merge or a file written straight to it.
    What the kit can't read (a path, a method, a body or an alias) counts as
    the base branch."""
    read = read or (lambda: "")
    k = _vcs_index(seg.words, "attended")
    toks = seg.words[k:] if k is not None else seg.words
    name = Path(toks[0]).name if toks else ""
    if name == "curl":
        return _solo_curl(toks, seg, profile.base_branch, profile.repo, raw, read)
    if name == "gh":
        return _solo_gh(toks, seg, profile, raw, read)
    return None


def _gh_repo(toks: list[str], group: str, sub: str | None) -> str | None:
    """The repository a `gh pr`/`gh repo` command names: `-R`/`--repo`, a pull
    request's URL, or `gh repo edit`'s own argument; None when it names none."""
    found = None  # gh takes the last one given
    for j, t in enumerate(toks):
        if t in ("-R", "--repo"):
            found = toks[j + 1] if j + 1 < len(toks) else None
        elif t.startswith(("--repo=", "-R=")) or (t.startswith("-R") and len(t) > 2):
            found = t.split("=", 1)[1] if "=" in t else t[2:]
        elif u := re.match(r"(?i)(?:https?://)?(?:www\.)?github\.com/([^/\s]+/[^/\s]+)/pull/", t):
            found = u.group(1)
    if found is not None:
        return found
    if group == "repo" and sub == "edit":
        # Only right after `edit`: later, a word may be a flag's value.
        nxt = toks[toks.index("edit") + 1 : toks.index("edit") + 2] if "edit" in toks else []
        return nxt[0] if nxt and not nxt[0].startswith("-") else None
    return None


def _solo_curl_ask(seg: Seg, profile: Profile, raw: str, read) -> str | None:
    """Solo mode: a curl command that creates a ruleset, which is asked (as
    `gh api` is), since it's how a project leaves solo mode."""
    if not seg.words or Path(seg.words[0]).name != "curl":
        return None
    c = _curl_call(seg.words, seg.cwd)
    for u in c.urls:
        path = _api_path(u) if _GITHUB_HINT.search(u) else ""
        if (c.method == "POST" and re.fullmatch(r"(?:repos/[^/]+/[^/]+|orgs/[^/]+)/rulesets", path)) or (
            path == "graphql" and re.search(r"\bcreateRepositoryRuleset\b", "\n".join(d or "" for d in c.data) + "\n" + raw)
        ):
            return "creating a ruleset through the API changes what protects the branches; allow it only if you mean to"
    return None


def _mcp_ref(v) -> str:
    return str(v or "").strip().removeprefix("refs/").removeprefix("heads/")


def _solo_mcp(name: str, inp: dict, profile: Profile) -> tuple[SoloRefusal, str] | bool | None:
    """Solo mode: a GitHub MCP call that changes the base branch: the refusal and
    the `gh` command that does the same by hand; True for creating a ruleset
    (asked); None for the rest."""
    base = profile.base_branch
    low = name.lower()
    if low.startswith(_READ_PREFIXES):
        return None
    owner, repo = inp.get("owner"), inp.get("repo")
    r = f"{owner}/{repo}" if isinstance(owner, str) and isinstance(repo, str) and owner and repo else profile.repo
    if _another_repo(r, profile.repo):
        return None
    q = shlex.quote

    def is_base(v) -> bool:
        if v is not None and not isinstance(v, str):
            return True  # not a name the kit can read
        b = _mcp_ref(v)
        return not b or b.casefold() == base.casefold()  # as check_mcp's file writes compare it

    path = str(inp.get("path") or "…").lstrip("/")
    if name in GITHUB_WRITE_FILES and is_base(inp.get("branch")):
        what = f"`{name}` writes files straight to `{base}`" + ("" if _mcp_ref(inp.get("branch")) else " (the default branch, as no branch is named)")
        hand = {
            "create_or_update_file": f"gh api -X PUT {q(f'repos/{r}/contents/{path}')} -f {q('branch=' + base)} -f message=… -f content=…",
            "delete_file": f"gh api -X DELETE {q(f'repos/{r}/contents/{path}')} -f {q('branch=' + base)} -f message=… -f sha=…",
        }.get(name, f"git push origin {q(base)}")
        return SoloRefusal(what), hand
    if "ruleset" in low:
        if low.startswith("create"):
            return True
        rid = inp.get("ruleset_id") or inp.get("id") or "…"
        verb = "DELETE" if low.startswith("delete") else "PUT"
        hand = f"gh api -X {verb} {q(f'repos/{r}/rulesets/{rid}')}" + (" --input ruleset.json" if verb == "PUT" else "")
        return SoloRefusal(f"`{name}` changes or removes a ruleset, which is what protects `{base}`"), hand
    if "protection" in low and is_base(inp.get("branch")):
        verb = "DELETE" if low.startswith("delete") else "PUT"
        hand = f"gh api -X {verb} {q(f'repos/{r}/branches/{base}/protection')}" + (" --input protection.json" if verb == "PUT" else "")
        return SoloRefusal(f"`{name}` changes `{base}`'s protection"), hand
    m = re.fullmatch(r"(create|update|delete|rename)_(?:ref|branch)", low)
    ref = next((inp[k] for k in ("ref", "branch", "name") if inp.get(k) is not None), None)
    # Making a branch needs its name; changing or removing one with no name the kit can read counts as the base.
    if m and (is_base(ref) if m.group(1) != "create" else ref is not None and is_base(ref)):
        hand = {
            "create": f"gh api -X POST {q(f'repos/{r}/git/refs')} -f {q('ref=refs/heads/' + base)} -f sha=…",
            "update": f"gh api -X PATCH {q(f'repos/{r}/git/refs/heads/{base}')} -f {q('sha=' + str(inp.get('sha') or '…'))}" + (" -F force=true" if inp.get("force") else ""),
            "delete": f"gh api -X DELETE {q(f'repos/{r}/git/refs/heads/{base}')}",
            "rename": f"gh api -X POST {q(f'repos/{r}/branches/{base}/rename')} -f {q('new_name=' + str(inp.get('new_name') or '…'))}",
        }[m.group(1)]
        return SoloRefusal(f"`{name}` changes the branch `{base}`" + ("" if isinstance(ref, str) and _mcp_ref(ref) else ", or one the kit can't read")), hand
    if "default_branch" in inp and re.search(r"(?:update|edit)_repo", low):
        return SoloRefusal(f"`{name}` changes the default branch, which is `{base}`"), f"gh repo edit {q(r)} --default-branch {q(str(inp.get('default_branch') or '…'))}"
    return None


def _solo_problem(segs: list[Seg], profile: Profile, start: str, current_branch: str | None, command: str = "", read=None) -> SoloRefusal | None:
    """Solo mode (an attended session, `ruleset = false`): the first thing in the
    command that touches the base branch, or might, through git or GitHub. Every
    segment is read, each git lookup made once. `read` gives the text of the
    files the command reads (a GraphQL query or a body may come from one)."""
    global _GIT_MEMO
    _GIT_MEMO = {}
    try:
        return _solo_scan(segs, profile, start, current_branch, command, read)
    finally:
        _GIT_MEMO = None


def _solo_scan(segs: list[Seg], profile: Profile, start: str, current_branch: str | None, command: str = "", read=None) -> SoloRefusal | None:
    base = profile.base_branch
    switched: dict[str | None, str | None] = {}  # directory -> the branch a switch in this command left checked out
    env_set = False  # git variables set anywhere in the command (exported, or for one command)
    for seg in segs:
        names = list(seg.assigns)
        if seg.words[:1] and seg.words[0] in _DECLARES:
            names += [w for w in seg.words[1:] if not w.startswith("-")]
        if not seg.words or seg.words[0] in _DECLARES:
            env_set = env_set or any(_GIT_ENV.match(a) for a in names)
        if seg.words[:1] == ["alias"] and any(_PUSHES.search(w) for w in seg.words[1:]):
            return SoloRefusal("a shell alias that pushes, which the kit can't follow", "unknown")
        refusal = _solo_github(seg, profile, command, read)
        if refusal:
            return refusal
        g = _git(seg.words)
        if g is None:
            continue
        glob, args, cdir = g
        refusal = _git_config_problem(glob, args, "attended", solo=True)
        if isinstance(refusal, SoloRefusal):
            return refusal
        d = _git_dir_of(Path(start), seg.cwd, cdir)
        repo = _git_out(d, "rev-parse", "--show-toplevel") or d  # a switch holds for the whole repository
        changes, to = _switched_to(args, d)
        if args and args[0] not in _GIT_COMMANDS and not args[0].startswith("-"):
            changes, to = True, None  # an alias, which may switch branches
        if changes and repo:  # an unknown directory: its push is refused as can't-tell anyway
            switched[repo] = to
        env_here = env_set or any(_GIT_ENV.match(a) for a in seg.assigns)
        config_elsewhere = any(o == "--config-env" or o.startswith("--config-env=") for o in glob) or any(
            glob[j] == "-c" and re.match(r"(?i)include(if)?\.", glob[j + 1]) for j in range(len(glob) - 1)
        )
        refusal = _solo_alias(glob, args, d, env_here or config_elsewhere)
        if refusal:
            return refusal
        if not args or args[0] not in _PUSH_CMDS:
            continue
        if seg.fed:
            return SoloRefusal("xargs gives this push its branches, which the kit can't see", "unknown")
        if env_here:
            return SoloRefusal("a `GIT_DIR`, `GIT_WORK_TREE`, `GIT_CONFIG…`, `HOME` or `XDG_CONFIG_HOME` variable points the push at other config or another repository", "unknown")
        if any(o == "--git-dir" or o.startswith(("--git-dir=", "--work-tree")) for o in glob):
            return SoloRefusal("`--git-dir` or `--work-tree` points the push at another repository", "unknown")
        same = cdir is None and seg.cwd == start
        branch = current_branch if same else _branch_of(d)
        after_switch = repo in switched
        if after_switch:
            branch = switched[repo]
        refusal = _push_problem(
            args, base, branch, "attended", profile.ticket_branch,
            upstream=lambda d=d, b=branch if after_switch else None: _upstream_branch(d, b), solo=True,
            settings=lambda remote, d=d, branch=branch: _solo_push_settings(d, base, branch, remote),
        )  # fmt: skip
        if isinstance(refusal, SoloRefusal):
            return refusal
    return None


def _post_texts(s: Seg) -> list[str]:
    """The texts a post may send: its body files, its stdin, a piped producer's files."""
    out: list[str] = []
    files = [(f, s.cwd) for f in _body_files(s.words)]
    files += [(f, s.cwd) for f in (s.inputs or ([s.stdin] if s.stdin else []))]
    if s.piped is not None:  # what its producer reads: `cat body.md | gh pr comment 1 --body-file -`
        files += [(w, s.piped.cwd) for w in s.piped.words[1:] if not w.startswith("-")]
        if s.piped.stdin:
            files.append((s.piped.stdin, s.piped.cwd))
    for f, fcwd in files:
        txt = _read_text(f, fcwd)
        if txt:
            out.append(txt)
    return out


def _bash_holds_sensitive(command: str, profile: Profile, root: Path, cwd: str | os.PathLike | None) -> bool:
    """True when a command, the files it reads, or what any part of it may post
    matches a sensitive pattern: read whole, since an earlier ask stops
    check_bash before it reads the posts."""
    if not profile.sensitive_patterns:
        return False
    segs = segments(command, root, _start_cwd(root, cwd))
    texts = [command, *_command_reads(segs)]
    for seg in segs:
        texts += _post_texts(seg)
    text = "\n".join(texts)
    return any(re.search(pat, text) for pat in profile.sensitive_patterns)


def check_bash(
    command: str,
    profile: Profile,
    role: str,
    root: Path,
    current_branch: str | None,
    role_from_env: bool = True,
    cwd: str | os.PathLike | None = None,
    code: "_Code | None" = None,
) -> Decision:
    start = _start_cwd(root, cwd)
    segs = segments(command, root, start)
    if code is not None:
        if code.planning():  # the prototype exception holds only while nothing may change the branch (#393)
            code = _prototype_rule(code, segs, root, command)
        # Refused wherever it sits in the command: an ask earlier on never hides it.
        p = _shell_code(segs, code, root)
        if p:
            return Decision("deny", p)
        p, unsure = _commit_code(segs, code, root, command)
        if p:
            return Decision("deny", p)
        p, unsure_push = _push_code(segs, code, root, command)
        if p:
            return Decision("deny", p)
        unsure = unsure or unsure_push
        if unsure:
            # The rest of the command first: its refusal stands over this ask, and its ask joins it.
            d = check_bash(command, profile, role, root, current_branch, role_from_env, cwd)
            u = _unsure_code(unsure, role, code)
            if d.action == "deny":
                return d
            if d.action == "ask" and u.action == "ask":
                return Decision("ask", f"{d.reason}\n{u.reason}", d.sensitive)
            return u
    protected = list(profile.protected_paths) + (GIT_INTERNALS if role == "ticket" else [])
    # Solo mode: no ruleset protects the base branch, so what touches it is
    # refused, not asked, wherever it sits in the command (an ask earlier on
    # never hides it). The rest is then checked as in any attended session.
    cache: dict[str, str] = {}

    def read() -> str:
        """The text of every file the command reads with cat or `<`."""
        if "text" not in cache:
            cache["text"] = "\n".join(_command_reads(segs))
        return cache["text"]

    solo = role == "attended" and profile.ruleset is False
    if solo:
        refusal = _solo_problem(segs, profile, start, current_branch, command, read)
        if refusal:
            return _solo_deny(refusal, profile, root, command, _bash_holds_sensitive(command, profile, root, start))
    posts: list[Seg] = []

    for seg in segs:
        p = _word_problem(seg.words, role) or _env_problem(seg, role)
        if p:
            return _deny(role, p)
        k = _vcs_index(seg.words, role)
        toks = seg.words[k:] if k is not None else seg.words
        if role == "ticket" and toks and _is_vcs_word(toks[0]) and any(_POSITIONAL.search(w) and not _literal_heredoc(w) for w in toks[1:]):
            return _deny(role, f"`{Path(toks[0]).name}` with a function's or script's parameters (`$@`, `$1` …) can't be read before it runs; write the command out, and pass text that mentions one in a quoted heredoc " + _HEREDOC_HINT)
        g = _git(toks)
        if g is not None:
            glob, args, cdir = g
            p = _git_config_problem(glob, args, role)
            if p:
                return _deny(role, p)
            d = _git_dir_of(root, seg.cwd, cdir)
            same = cdir is None and seg.cwd == start
            if args and args[0] in ("push", "send-pack", "http-push"):
                if role != "attended" and any(o == "--git-dir" or o.startswith(("--git-dir=", "--work-tree")) for o in glob):
                    return _deny(role, "push from the repository's own directory, not with `--git-dir`/`--work-tree`")
                branch = current_branch if same else _branch_of(d)
                p = _push_problem(args, profile.base_branch, branch, role, profile.ticket_branch, upstream=lambda d=d: _upstream_branch(d))
                if p:
                    return _deny(role, p)
            if role == "ticket" and not role_from_env:
                p = _switch_problem(args, profile.ticket_branch, d)
                if p:
                    return Decision("deny", p)
            runs = _GIT_RUNS.get(args[0]) if args else None
            if role == "ticket" and args and args[0] in _GIT_RUNS and (runs is None or any(a in runs for a in args[1:])):
                return Decision("deny", f"`git {' '.join(args[:2])}` runs a program the guard can't see; run it yourself")
            if role == "ticket" and args[:1] == ["rebase"] and any(
                re.fullmatch(r"--(?:e|ex|exe|exec)(?:=.*)?", a, re.S) or re.match(r"-[a-wyzA-Z]*x", a) for a in args[1:] if not a.startswith("--") or a.startswith("--e")
            ):
                return Decision("deny", "`git rebase --exec` runs commands the guard can't see; run them yourself between steps")
            if role == "ticket" and args[:1] == ["branch"]:  # whatever the role's source
                p = _upstream_problem(args, d, current_branch if same else _branch_of(d))
                if p:
                    return Decision("deny", p)
        if toks and Path(toks[0]).name == "gh":
            p = _merge_async_problem(seg, toks, profile, role, root)
            if p:
                return _deny(role, p)
            p = _gh_problem(toks, profile, role, seg.cwd, command, read)
            if p:
                return _deny(role, p)
            p = _ticket_merge_problem(seg, toks, profile, root) if role == "ticket" else None
            if p:
                return _deny(role, p)
        p = _api_problem(seg.words, profile, role, seg.cwd, command, read) if seg.words and Path(seg.words[0]).name == "curl" else None
        if p:
            return _deny(role, p)
        p = _solo_curl_ask(seg, profile, command, read) if solo else None
        if p:
            return Decision("ask", p)
        if _post_kind(toks):
            posts.append(seg if k is None else replace(seg, words=toks))  # every other field kept, stdin's too
        if role in ("ticket", "attended"):
            p = _deploy_problem(seg, profile.deploy_commands, root)
            if p:
                return _deny(role, p)
        if role in ("ticket", "conductor"):
            t = _write_targets(seg, root)
            p = _global_config_problem(seg, t)
            if p:
                return Decision("deny", p)
            if role == "ticket":
                p = _shell_protected(seg, protected, root, t)
                if p:
                    return Decision("deny", p + "; ticket sessions don't change protected paths (the owner reviews those)")
                if not profile.allow_new_skips:
                    p = _shell_skips(seg, profile, root, t)
                    if p:
                        return Decision("deny", p)
    if not posts:
        return ALLOW

    post_texts = _post_texts

    if profile.sensitive_patterns:
        texts = [command, read()]
        for s in posts:
            texts += post_texts(s)
        text = "\n".join(texts)
        for pat in profile.sensitive_patterns:
            if re.search(pat, text):
                return _deny(role, f"this would post text matching the sensitive-data pattern {pat!r}; refer to things by id", sensitive=True)
    if role in ("ticket", "conductor"):
        for s in posts:
            # In the command's texts as a whole: a seatbelt, not proof that each post carries it.
            if _creates_text(s.words, s.cwd, _stdin_text(s)) and AGENT_MARKER not in "\n".join([command, read(), *post_texts(s)]):
                return Decision("deny", _NO_MARKER)
    return ALLOW


# ---------- file tools ----------


# The most of a test file a Write reads to see which markers it already holds.
_WRITE_READ_CAP = 4_000_000


def _added_skips(old: str, new: str) -> int:
    return len(_SKIP.findall(new or "")) - len(_SKIP.findall(old or ""))


def check_write(
    tool: str, inp: dict, profile: Profile, role: str, root: Path, cwd: str | os.PathLike | None = None, code: "_Code | None" = None
) -> Decision:
    path = inp.get("file_path") or inp.get("notebook_path") or ""
    start = _start_cwd(root, cwd)
    a = _abspath(path, start) if path else None
    rel = _rel(a, root) if a else ""
    if role in ("ticket", "conductor") and a:
        hit = global_config_hit(a)
        if hit:
            return Decision("deny", f"`{path}` is the global git config ({hit}), which can hold aliases, hooks and push settings; it isn't changed in {role} sessions")
    hit = _code_at(a, code, root) if code is not None and a else None
    if hit:
        return Decision("deny", f"{_shown(hit)} is a code path ({hit.pattern}); {code.instead}")
    if _outside(rel):  # outside the project: never one of its protected paths or tests
        return ALLOW
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
        old, over = _read_capped(str(a), None, _WRITE_READ_CAP) if a else (None, False)
        if over:
            return Decision("deny", f"the test file `{rel}` is too large for the guard to read (over {_WRITE_READ_CAP:,} bytes), so it can't check what this replaces; change it with Edit")
        added = _added_skips(old or "", inp.get("content", ""))
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
    if role == "attended" and profile.ruleset is False:
        s = _solo_mcp(name, inp, profile)
        if s is True:
            return Decision("ask", f"`{name}` creates a ruleset, which changes what protects the branches; allow it only if you mean to")
        if s:
            return _solo_deny(s[0], profile, root, s[1], _text_holds_sensitive("\n".join(_strings(inp)), profile))
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
    if role == "ticket":
        p = _ticket_mcp_merge_problem(name, inp, profile, root)
        if p:
            return Decision("deny", p)
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
                    sensitive=True,
                )
    if role in ("ticket", "conductor") and _mcp_creates_text(name, inp):
        body = inp.get("body")
        if not (isinstance(body, str) and AGENT_MARKER in body):
            return Decision("deny", f"this {name} posts text: " + _NO_MARKER)
    return ALLOW


POWERSHELL_REFUSAL = "the guard can't read PowerShell; use Bash"


def check_powershell(inp: dict, profile: Profile, role: str, root: Path, cwd: str | os.PathLike | None = None, code: "_Code | None" = None) -> Decision:
    """The guard can't read PowerShell, and never tries to parse it. Ticket and
    conductor sessions are refused it; an attended session gets the can't-decide
    rule (#53) on its text: a push or a merge is asked (refused in solo mode),
    anything else is left alone. A session that doesn't write code (#340) is
    refused any PowerShell whose text names a code path, even to read it."""
    # The guard can't read PowerShell, so it can't tell the branch stays as it is: no prototype exception (#393).
    hit = _powershell_code(inp, replace(code, no_prototype="PowerShell"), root, cwd) if code is not None else None
    if hit:
        return Decision(
            "deny",
            f"this PowerShell names the code path {_shown(hit)} ({hit.pattern}), and the guard can't read PowerShell "
            f"to tell whether it writes it, so run it through Bash, where the guard can tell; {code.writes_none}",
        )
    if role != "attended":
        return Decision("deny", POWERSHELL_REFUSAL)
    what = fallback.push_or_merge({"tool_name": "PowerShell", "tool_input": inp})
    if not what:
        return ALLOW
    command = inp.get("command") if isinstance(inp.get("command"), str) else ""
    if profile.ruleset is False:
        refusal = SoloRefusal(f"a {what} in PowerShell, which the kit can't read", "unknown", "run it through Bash instead, where the kit can tell")
        return _solo_deny(refusal, profile, root, command, _text_holds_sensitive(command, profile))
    return Decision(
        "ask",
        f"the guard can't read PowerShell, so it can't check this {what} (which branch, which pull request); "
        "allow it only if you mean to, or run it through Bash, which the guard can check",
    )


# ---------- who writes code (#340) ----------
#
# Under `code_writers = "ticket"` (#339's rule, from `profile.code_rule`), only
# a session with `WORKFLOW_ROLE=ticket` writes code. Every other session is
# refused, never asked, a write the guard places on a code path: the file
# tools, the shell's writes it reads as it reads a ticket session's writes to
# protected paths, `git apply` and `git am`, and PowerShell that names one. A
# target it can't place is left alone (a commit or push carrying it is #341's).
# What a code path is: a match of `code_paths`, unless it is protected too,
# under `.workflow/`, or an untracked file git ignores, judged in the checkout
# it belongs to (the project, or one of Claude Code's worktrees of it).


@dataclass
class _Code:
    """A session that writes no code: the code paths, the protected paths
    (which win), and what its refusals say to do instead."""

    paths: list[str]
    protected: list[str]
    instead: str  # what to do instead, after the path
    writes_none: str  # PowerShell's: the session writes no code
    repo: str | None = None  # `project.repo`, whose pushes are judged (#390); None: every push is
    base: str = "main"  # the base branch: a revert of a commit on its remote ref goes through (#392)
    role: str = "attended"  # the role it decides by, for a revert's refusal
    profile: Profile | None = None
    root: Path | None = None
    _ledger: frozenset[str] | None = field(default=None, repr=False)  # read once, when a revert is judged
    # Why this command gets no prototype exception (#393): what in it may change the branch a checkout is on
    # before a write or commit runs, or that it is PowerShell, which the guard can't read.
    no_prototype: str | None = None
    changers: "_Changers | None" = field(default=None, repr=False)  # the command's, built once for its rules
    _heads: dict[tuple[str, tuple[str, ...]], bool] = field(default_factory=dict, repr=False)  # read once per event

    def conductor(self) -> bool:
        return self.role == "conductor"

    def planning(self) -> bool:
        """A planning session's rule: the only one with the prototype exception (#393)."""
        return self.role == "attended"

    def on_prototype(self, top: str, glob: list[str] | tuple[str, ...] = ()) -> bool:
        """Whether the checkout `top` (git run there with `glob`) is on a
        branch named `prototype/*`, as it is now: HEAD names one, and a
        rebase in progress (which finishes on the branch it started on,
        `head-name`, whatever HEAD names meanwhile) started on one, or HEAD
        is detached and it did. Anything it can't read counts as not."""
        key = (top, tuple(glob))
        if key not in self._heads:
            got, err = _git_read(
                top, list(glob), "rev-parse", "--symbolic-full-name", "HEAD",
                "--git-path", "rebase-merge/head-name", "--git-path", "rebase-apply/head-name", sep="\n",
            )  # fmt: skip
            if got is None and "took too long" not in err:  # an unborn branch, which `rev-parse` can't name: read HEAD as a symbolic ref
                head, _ = _git_read(top, list(glob), "symbolic-ref", "-q", "HEAD", sep="\n", ok=(0, 1))
                paths, _ = _git_read(top, list(glob), "rev-parse", "--git-path", "rebase-merge/head-name", "--git-path", "rebase-apply/head-name", sep="\n")
                got = [head[0], *paths] if head and paths else None
            on = False
            if got and len(got) == 3:
                head, ends = got[0], []
                for path in got[1:]:
                    full = os.path.join(top, path)
                    if os.path.lexists(full):
                        text = _read_text(full, None, 4096)
                        ends.append(text.strip() if text is not None else "")  # unreadable: not a prototype's
                ends = [e for e in ends if e != "detached HEAD"]
                on = (head == "HEAD" or _prototype_branch(head)) and (bool(ends) or head != "HEAD")
                on = on and all(_prototype_branch(e) for e in ends)
            self._heads[key] = on
        return self._heads[key]

    def prototype_here(self, top: str, glob: list[str] | tuple[str, ...] = ()) -> bool:
        """Whether this session may write and commit code in the checkout
        `top`: a planning session's, not the conductor's, on a branch named
        `prototype/*` that nothing in the command may change first (#393)."""
        return self.planning() and self.no_prototype is None and self.on_prototype(top, glob)

    def allowed_reverts(self) -> frozenset[str]:
        """The commits the conductor's run's ledger allows it to revert (#392)."""
        if self._ledger is None:
            self._ledger = _ledger_reverts(self.root) if self.root is not None else frozenset()
        return self._ledger


@dataclass
class _Hit:
    path: str  # relative to its checkout's top level
    pattern: str  # the code path it matches
    worktree: str = ""  # the worktree's folder, relative to the project, when not the project itself


def _shown(hit: _Hit) -> str:
    return f"`{hit.path}`" + (f" (in the worktree `{hit.worktree}`)" if hit.worktree else "")


_CODE_TOOLS = WRITE_TOOLS | {"Bash", "Monitor", "PowerShell"}


def _code_session(
    event: dict, profile: Profile, role: str, root: Path, role_from_env: bool, branch: str | None
) -> tuple[str, _Code | None, str | None]:
    """(the role to decide by, the code rule when this session writes no code,
    the session's name in a refusal when not its role's). Under "ticket", a
    session that is a ticket session only by its branch, or by a value of
    `WORKFLOW_ROLE` that isn't a role, gets an attended session's rules."""
    tool = event.get("tool_name") or ""
    if not isinstance(tool, str):
        return role, None, None
    odd = roles_mod.unrecognised()
    firm_ticket = role == "ticket" and role_from_env and odd is None
    # A ticket session only by its branch or a mistyped role gets an attended session's MCP rules too.
    if firm_ticket or not (tool in _CODE_TOOLS or (role == "ticket" and tool.startswith("mcp__"))):
        return role, None, None
    rule = profile_mod.code_rule(root)
    if rule.code_writers != "ticket" or rule.writes_code():
        return role, None, None
    label = None
    if role == "ticket":
        if odd is not None:
            label = f'attended session (WORKFLOW_ROLE={odd!r} isn\'t a role, so under `code_writers = "ticket"` it isn\'t a ticket session)'
        else:
            on = f"`{branch}`, matching `{profile.ticket_branch}`" if branch else f"matching `{profile.ticket_branch}`"
            label = f'attended session (a ticket session only by its branch, {on}: under `code_writers = "ticket"` that isn\'t a ticket session)'
        role = "attended"
    if not rule.code_paths:
        return role, None, label
    code = _Code(
        list(rule.code_paths), list(rule.protected_paths), _instead(role, profile, root), _writes_none(role), rule.repo,
        rule.base_branch, role, profile, root,
    )  # fmt: skip
    return role, code, label


def _writes_none(role: str) -> str:
    if role == "conductor":
        return 'under `code_writers = "ticket"` the conductor writes no code'
    return 'under `code_writers = "ticket"` only ticket sessions (`WORKFLOW_ROLE=ticket`) write code, and this session isn\'t one'


def _instead(role: str, profile: Profile, root: Path) -> str:
    """What a refusal says to do instead, worded as the skills offer it."""
    if role == "conductor":
        charter = _run_state(root).get("charter")
        fixes = charter.get("conductor_fixes") if isinstance(charter, dict) else None  # the charter's, else unread
        if fixes is True:
            way = "file the fix as a `workflow:infra` ticket, for a ticket session, instead"
        elif fixes is False:
            way = "add the fix to `for_owner`, for the report, instead"
        else:
            way = "with the charter's `conductor_fixes` on, file the fix as a `workflow:infra` ticket, for a ticket session; with it off, add it to `for_owner`, for the report"
        return f"{_writes_none(role)}: {way}"
    from . import updates as updates_mod

    if updates_mod.mode(root) == "plugin":  # no unattended runs
        way = "build it in a session on your own computer started with `WORKFLOW_ROLE=ticket` instead"
    elif profile.ticket_environment:
        way = "hand it to a conductor run instead (**Run it unattended**), as a ticket or, for a small change, a quick ticket"
    else:
        way = (
            "hand it to a conductor run instead, once unattended runs are set up (**Set up unattended runs**): "
            "until a ticket environment is named, no session writes code"
        )
    return f"{_writes_none(role)}: {way}. {_ANY_WRITES}"


_ANY_WRITES = "Or, to let every session write code, change `guard.code_writers` in a pull request, for the owner to merge"


def _revert_way(code: _Code, pr: str, entry: bool) -> str:
    """What a refusal of a revert that doesn't go through says to do instead
    (#392): GitHub's own **Revert** button where it can revert the pull
    request (`pr`), else a quick ticket, worded as the skills offer a run.
    The conductor's tells the owner, and marks its ledger `entry` not made."""
    button = f"GitHub's own **Revert** button on pull request #{pr}" if pr else ""
    if code.conductor():
        made = ', and add `"result": "not made: <why>"` to its ledger entry and the same to `for_owner`' if entry else ""
        can = f"use {button} or have it filed as a ticket" if pr else "have it filed as a ticket"
        return f"never resolve a revert that doesn't apply exactly: tell the owner, who can {can}{made}"
    from . import updates as updates_mod

    if code.root is not None and updates_mod.mode(code.root) == "plugin":
        way = "make the revert in a session on your own computer started with `WORKFLOW_ROLE=ticket`"
    elif code.profile is not None and code.profile.ticket_environment:
        way = "have a ticket session make it: file a quick ticket for the revert and hand it to a conductor run (**Run it unattended**)"
    else:
        way = (
            "have a ticket session make it, once unattended runs are set up (**Set up unattended runs**): file a quick ticket that makes the revert, "
            "for a conductor run; until a ticket environment is named, no session writes code"
        )
    if pr:
        way = f"use {button}, which undoes it exactly; where GitHub can't revert it, {way}"
    return f"{code.writes_none}: {way}. {_ANY_WRITES}"


def _run_state(root: Path) -> dict:
    """The state block of the run's local body file (`.workflow/run/body.md`),
    {} when there is none or it can't be read."""
    from . import state as state_mod

    try:
        got = state_mod.get((root / ".workflow/run/body.md").read_text(encoding="utf-8"))
    except Exception:
        return {}
    return got if isinstance(got, dict) else {}


def _ledger_reverts(root: Path) -> frozenset[str]:
    """The commits the run's ledger records the owner as allowing the
    conductor to revert (#392): each entry `{"what": "revert", "revert": "<the
    full sha>", …}`. Entries without a `revert` field don't count; none when
    the body file can't be read."""
    from . import state as state_mod

    ledger = _run_state(root).get("ledger")
    entries = ledger if isinstance(ledger, list) else []
    return frozenset(
        e["revert"] for e in entries if isinstance(e, dict) and str(e.get("what")).strip().lower() == "revert" and state_mod.is_head(e.get("revert"))
    )


def _git_lines(top: str, *args: str, sep: str = "\n", literal: bool = True) -> list[str] | None:
    try:
        p = subprocess.run(["git", *(["--literal-pathspecs"] if literal else []), "-C", top, *args], capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    if p.returncode != 0:
        return None
    return [x for x in p.stdout.decode("utf-8", errors="replace").split(sep) if x]


def _common_dir(top: str) -> str | None:
    out = _git_lines(top, "rev-parse", "--show-toplevel", "--git-common-dir")
    if not out or len(out) != 2 or os.path.realpath(out[0]) != os.path.realpath(top):
        return None
    return os.path.realpath(os.path.join(top, out[1]))


def _checkout_of(abspath: str, root: Path) -> tuple[str, str, str] | None:
    """(the checkout's top level, the path relative to it, the worktree's
    folder or "") for a path in the project or in one of Claude Code's
    worktrees of it (`.claude/worktrees/<name>`); None elsewhere."""
    rel = _rel(abspath, root)
    if _outside(rel):
        return None
    parts = rel.split("/")
    if [x.casefold() for x in parts[:2]] == [".claude", "worktrees"]:
        if len(parts) < 3:
            return None
        top = os.path.join(os.path.realpath(str(root)), *parts[:3])
        mine = _common_dir(top)
        if mine is None or mine != _common_dir(os.path.realpath(str(root))):
            return None  # not a worktree of this project: another clone, left to the push rule
        return top, "/".join(parts[3:]), "/".join(parts[:3])
    return os.path.realpath(str(root)), rel, ""


def _listed_code(rel: str, code: _Code) -> str | None:
    """The code path `rel` matches, by its name alone: protected wins, and
    `.workflow/` is never code."""
    r = rel.casefold().rstrip("/")
    if not r or r == "." or r == ".workflow" or r.startswith(".workflow/") or matches(rel, code.protected):
        return None
    return matches(rel, code.paths)


def _ignored(top: str, rel: str) -> bool:
    """An untracked path git ignores (`check-ignore` never names a tracked one;
    a name it reads as pathspec magic fails it, so counts as not ignored)."""
    try:
        p = subprocess.run(["git", "-C", top, "check-ignore", "-q", "--", rel], capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False
    return p.returncode == 0


def _code_files(top: str, rel: str) -> list[str]:
    """The files git tracks under `rel` in the checkout, and the untracked ones
    it doesn't ignore."""
    spec = rel or "."
    out = _git_lines(top, "ls-files", "-z", "--", spec, sep="\0") or []
    return out + (_git_lines(top, "ls-files", "-z", "-o", "--exclude-standard", "--", spec, sep="\0") or [])


def _code_at(abspath: str | None, code: _Code, root: Path, tree: bool = False) -> _Hit | None:
    """The code path `abspath` is, or (`tree`) one inside it that a write into,
    removal or move of it changes."""
    co = _checkout_of(abspath, root) if abspath else None
    if co is None:
        return None
    top, rel, wt = co
    if wt and not rel:
        return None  # a worktree as a whole is a checkout, not a code path
    m = _listed_code(rel, code)
    hit = None
    if m and not _ignored(top, rel):
        hit = _Hit(rel, m, wt)
    elif tree and (not rel or os.path.isdir(abspath)):
        hit = _first_code(top, rel, code, wt)
    if not hit or not code.prototype_here(top):
        return hit
    return _worktree_code(abspath, code, root) if tree and not wt else None


def _worktree_code(abspath: str, code: _Code, root: Path) -> _Hit | None:
    """A code path in one of Claude Code's worktrees inside `abspath`, a
    folder of a checkout on a `prototype/*` branch: each worktree is judged
    by its own branch (#393)."""
    for w in _claude_worktrees(abspath, root):
        co = _checkout_of(w, root)
        if co is None or code.prototype_here(co[0]):
            continue
        hit = _first_code(co[0], "", code, co[2])
        if hit:
            return hit
    return None


def _first_code(top: str, rel: str, code: _Code, wt: str) -> _Hit | None:
    """The first code path git lists under `rel` in the checkout `top`."""
    for f in _code_files(top, rel):
        m = _listed_code(f, code)
        if m:
            return _Hit(f, m, wt)
    return None


_CHECKS_OUT = {"switch", "checkout", "restore", "merge", "pull", "reset", "stash", "revert", "cherry-pick", "clone", "worktree"}


@dataclass
class _CodeTargets:
    """What one command writes, as the code rule reads it."""

    t: _Targets  # its writes, read as ticket sessions' writes to protected paths are
    patched: list[str] = field(default_factory=list)  # the files `git apply`/`git am` writes, absolute
    cleans: list[tuple[str, list[str]]] = field(default_factory=list)  # `git clean`: (its directory, its pathspecs)


def _from(d: str, paths: list[str]) -> list[str]:
    return [x if os.path.isabs(x) else os.path.join(d, x) for x in paths]


def _code_targets(seg: Seg, root: Path) -> _CodeTargets:
    """What one command writes: git found behind wrappers, as in ticket
    sessions; git commands that check out committed content write nothing
    here; `git clean` removes the untracked files git lists for it."""
    t = _Targets(files=list(seg.redirects))
    out = _CodeTargets(t)
    k = _vcs_index(seg.words, "ticket")
    for s in ([seg] if not k else [seg, replace(seg, words=seg.words[k:], redirects=[])]):
        g = _git(s.words)
        sub = g[1][0] if g and g[1] else None
        if sub in _CHECKS_OUT:
            continue
        if sub in ("clean", "rm", "mv") and g[2]:  # their paths are from `git -C`'s directory; `t` holds the redirects
            s = replace(s, cwd=_git_dir_of(root, s.cwd, g[2]), redirects=[])
        if sub == "clean":
            specs = _clean_trees(g[1][1:])
            if s.cwd and specs:
                out.cleans.append((s.cwd, specs))
            continue
        if sub in ("apply", "am"):
            out.patched += _patched_files(s, g, root)
            continue
        w = _write_targets(s, root)
        if s.cwd != seg.cwd and s.cwd:  # read from `git -C`'s directory: placed from there
            w.files = _from(s.cwd, w.files)
            w.trees = _from(s.cwd, w.trees)
        t.files += [x for x in w.files if x not in t.files]
        t.trees += w.trees
        t.searched += w.searched
        t.named_from_root += w.named_from_root
    return out


def _clean_trees(args: list[str]) -> list[str]:
    """The pathspecs `git clean` removes from, as written: else `.`, its
    directory; none for a dry run or `-X`, which removes only ignored files."""
    flags, paths, i = "", [], 0
    while i < len(args):
        a = args[i]
        if a == "--":
            paths += args[i + 1 :]
            break
        if re.fullmatch(r"-[a-zA-Z]+", a):
            short = a[1:].split("e", 1)  # `-e` takes the rest of the word as its value, else the next word
            flags += short[0]
            i += 2 if len(short) > 1 and not short[1] else 1
            continue
        if a in ("--exclude",):
            i += 2
            continue
        if not a.startswith("-"):
            paths.append(a)
        i += 1
    if "n" in flags or "X" in flags or "--dry-run" in args:
        return []
    return paths or ["."]


def _patched_files(seg: Seg, g: tuple[list[str], list[str], str | None], root: Path) -> list[str]:
    """The files `git apply` or `git am` changes, from the top level of the
    checkout it runs in; none it can place when that is another repository
    or the patch can't be read."""
    _, args, cdir = g
    d = _git_dir_of(root, seg.cwd, cdir)
    texts, unknown, _ = _patch_texts("git" if args[0] == "apply" else "git-am", args[1:], replace(seg, cwd=d) if cdir else seg)
    top = _git_out(d, "rev-parse", "--show-toplevel") if d else None
    if unknown or not top:
        return []
    # A git diff's paths, and `git am`'s, are from the top level. `git apply` places a plain
    # patch's path, its first part dropped, from where it runs, unless it already names that
    # folder, as git does. The paths with their `a/` and `b/` dropped come first, so a refusal
    # names the file git writes.
    here = os.path.relpath(os.path.realpath(d), os.path.realpath(top)).replace(os.sep, "/")
    out: list[str] = []
    for txt in texts:
        if "diff --git " in txt or args[0] == "am" or here == ".":
            out += [os.path.join(top, p) for p in reversed(_patch_paths(txt))]
            continue
        for raw in _patch_paths(txt, stripped=False):
            if "/" in raw:
                rest = raw.split("/", 1)[1]
                out.append(os.path.join(top if rest.startswith(here + "/") else d, rest))
            else:  # a bare name: nothing to strip, so from where it runs
                out.append(os.path.join(d, raw))
            out.append(os.path.join(top, raw))
    return out


def _named_code(names: list[str], nocase: bool, own: bool, start: str, root: Path, code: _Code) -> _Hit | None:
    """A code path a writing `find` limited by name reaches: a file whose
    name matches, or one inside a directory whose name does, the start's
    own name included when find tests it."""
    co = _checkout_of(start, root)
    if co is None:
        return None
    top, rel, wt = co
    fold = (lambda x: x.casefold()) if nocase else (lambda x: x)
    globs = [fold(n) for n in names]
    if own and any(fnmatch.fnmatchcase(fold(posixpath.basename(start.rstrip("/"))), n) for n in globs):
        return _code_at(start, code, root, tree=True)
    skip = len([x for x in rel.split("/") if x])
    for f in _code_files(top, rel):
        parts = f.split("/")[skip:]
        if any(fnmatch.fnmatchcase(fold(x), n) for x in parts for n in globs):
            m = _listed_code(f, code)
            if m and not code.prototype_here(top):
                return _Hit(f, m, wt)
    if code.prototype_here(top) and not wt:  # it reaches into Claude Code's worktrees too, each on its own branch
        for w in _claude_worktrees(start, root):
            hit = _named_code(names, nocase, False, w, root, code)
            if hit:
                return hit
    return None


def _shell_code(segs: list[Seg], code: _Code, root: Path) -> str | None:
    """Why a command writes a code path, or None. Only what the guard places
    counts: a target relative to a directory it can't follow, a patch it
    can't read, an interpreter's own writes, are left alone."""
    for seg in segs:
        ct = _code_targets(seg, root)
        t = ct.t
        for f in ct.patched:
            hit = _code_at(_abspath(f, seg.cwd), code, root)
            if hit:
                return f"this patch writes the code path {_shown(hit)} ({hit.pattern}); {code.instead}"
        for tgt in t.files:
            for c in _candidates(tgt, seg.cwd):
                hit = _code_at(_abspath(c, seg.cwd), code, root) if c.strip() else None
                if hit:
                    return f"writing `{tgt}` writes the code path {_shown(hit)} ({hit.pattern}); {code.instead}"
        top = os.path.realpath(str(root))
        for tgt in t.trees:
            for c in _candidates(tgt, seg.cwd):
                a = _abspath(c, seg.cwd) if c.strip() else None
                if a and a != top and _holds_root(a, root):
                    a = top  # a directory above the project: all of it
                hit = _code_at(a, code, root, tree=True)
                if hit:
                    return f"writing into, removing or moving `{tgt}` changes the code path {_shown(hit)} ({hit.pattern}); {code.instead}"
        for d, specs in ct.cleans:
            co = _checkout_of(os.path.realpath(d), root)
            inside = _git_out(d, "rev-parse", "--show-toplevel") if co else None
            if not inside or os.path.realpath(inside) != co[0]:
                continue  # another repository nested in the project: left alone
            # What git itself lists for these pathspecs: its globs cross folders, `:/` is the top level.
            listed = _git_lines(d, "ls-files", "-z", "-o", "--exclude-standard", "--full-name", "--", *specs, sep="\0", literal=False)
            for f in listed or []:
                m = _listed_code(f, code)
                if m and not code.prototype_here(co[0]):
                    hit = _Hit(f, m, co[2])
                    return f"`git clean` of `{' '.join(specs)}` removes the code path {_shown(hit)} ({hit.pattern}); {code.instead}"
        for r, cwd in t.searched:
            a = _abspath(r, cwd)
            hit = _code_at(top if a and _holds_root(a, root) else a, code, root, tree=True)
            if hit:
                return (
                    f"this changes the files a search of `{r}` finds, which can be code paths ({hit.pattern}), "
                    f"so the guard can't see which files change; name the files. If they are code, {code.instead}"
                )
        for names, nocase, own, start in t.named_from_root:
            hit = _named_code(names, nocase, own, start, root, code)
            if hit:
                return f"this find reaches the code path {_shown(hit)} ({hit.pattern}) by name; {code.instead}"
    return None


# ---------- commits that carry code (#389) ----------
#
# A `git commit` in the project's own repository (the project, or a worktree
# of it) is judged by the files it would carry: what is staged, plus what
# `-a` or a pathspec adds (a pathspec alone commits only what it names, unless
# `-i`). A commit finishing a merge carries only the merge's own changes
# (#391, below), and one finishing a revert is judged by the revert rule
# (#392, below); finishing a cherry-pick, a rebase or `git am` (`--continue`)
# is judged as any commit. A commit in another clone is left to
# the push rule. When the guard can't read what it carries (a git read fails,
# a pathspec the shell expands), an attended session is asked and the
# conductor refused.

# git commit's long options (`git commit --git-completion-helper`): name ->
# takes a separate value. Their `--no-` forms take none. Unique prefixes are
# accepted, as git does.
_COMMIT_LONG: dict[str, bool] = {
    "quiet": False, "verbose": False, "file": True, "author": True, "date": True, "message": True,
    "reedit-message": True, "reuse-message": True, "fixup": True, "squash": True, "reset-author": False,
    "trailer": True, "signoff": False, "template": True, "edit": False, "cleanup": True, "status": False,
    "gpg-sign": False, "all": False, "include": False, "interactive": False, "patch": False, "only": False,
    "no-verify": False, "dry-run": False, "short": False, "branch": False, "ahead-behind": False,
    "porcelain": False, "long": False, "null": False, "amend": False, "no-post-rewrite": False,
    "untracked-files": False, "pathspec-from-file": True, "pathspec-file-nul": False, "allow-empty": False,
    "allow-empty-message": False, "verify": False, "post-rewrite": False,
}  # fmt: skip
_COMMIT_LONGS = sorted(set(_COMMIT_LONG) | {"no-" + k for k in _COMMIT_LONG})
_COMMIT_SHORT_VALUE = "mFcCt"  # the value is the rest of the word, else the next word
_COMMIT_SHORT_OPTIONAL = "Su"  # the value, if any, is the rest of the word
_COMMIT_PICKS = {"interactive", "patch"}  # chooses among the working tree's changes, as `-a` may carry them
_COMMIT_STATUS = {"short", "porcelain", "long"}  # each implies `--dry-run`: nothing is committed
_CONTINUE_COMMITS = ("merge", "cherry-pick", "revert", "rebase", "am")  # `git <sub> --continue` commits what is staged
# Global options that change which repository or how pathspecs read, passed to the guard's reads.
_GIT_REPO_GLOBALS = {"--git-dir", "--work-tree"}
_GIT_PATHSPEC_GLOBALS = {"--literal-pathspecs", "--glob-pathspecs", "--noglob-pathspecs", "--icase-pathspecs"}
# Variables that change which repository, index or work tree git reads: the guard's reads wouldn't match.
_GIT_REPO_ENV = {"GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR"}  # which repository
_GIT_INDEX_ENV = {"GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY"}  # what it reads there
# Variables that change how pathspecs read: their values are passed to the guard's reads.
_GIT_PATHSPEC_ENV = {"GIT_LITERAL_PATHSPECS", "GIT_GLOB_PATHSPECS", "GIT_NOGLOB_PATHSPECS", "GIT_ICASE_PATHSPECS"}
_SPEC_FILE_CAP = 1_000_000  # the most of a pathspec file the guard reads
_SHELL_EXPANDS = re.compile(r"[$`]|^~")
_BRACE_GROUP = re.compile(r"\{[^{}]*\}")  # linear: each try stops at the next brace
_BRACE_LIMIT = 64
_AM_RESOLVED = re.compile(r"-[3kmnqsu]*r[3kmnqsu]*")  # `-r` among `git am`'s flags that take no value
_LITERAL_GLOBALS = {"--literal-pathspecs", "--noglob-pathspecs"}
_LITERAL_ENV = {"GIT_LITERAL_PATHSPECS", "GIT_NOGLOB_PATHSPECS"}


def _brace_sequence(word: str) -> bool:
    """A `{1..3}` in the word, which `_braces` leaves as it is."""
    return any(".." in g for g in _BRACE_GROUP.findall(word))


@dataclass
class _Commit:
    """What a `git commit` would carry, as its arguments say."""

    all: bool = False  # `-a`: the tracked files changed in the working tree too
    include: bool = False  # `-i`: the staged files as well as the pathspec's
    specs: list[str] = field(default_factory=list)
    spec_file: str | None = None  # `--pathspec-from-file`
    spec_nul: bool = False
    dry: bool = False  # `--dry-run`, the last of it and `--no-dry-run`
    status: bool = False  # `--short`, `--porcelain` or `--long`, which imply it, the last of them and their `--no-` forms
    usage: bool = False  # `-h`, `--help`
    null: bool = False  # `-z`, which implies `--porcelain` where no format is given
    amend: bool = False  # `--amend`: the commit replaces HEAD
    messages: list[str] = field(default_factory=list)  # `-m` values, which git joins as paragraphs
    message_from: str = ""  # an option that takes the message from elsewhere (`-F`, `-C`, `-c`, `--fixup`, `--squash`)

    @property
    def dry_run(self) -> bool:
        return self.dry or self.status or self.null or self.usage


def _commit_long(name: str) -> str | None:
    if name in _COMMIT_LONGS:
        return name
    cands = [o for o in _COMMIT_LONGS if o.startswith(name)] if name else []
    return cands[0] if len(cands) == 1 else None


def _commit_args(args: list[str]) -> _Commit:
    c, i = _Commit(), 0
    while i < len(args):
        a = args[i]
        i += 1
        if a == "--":
            c.specs += args[i:]
            break
        if a.startswith("--"):
            name, eq, value = a[2:].partition("=")
            if name in ("help", "help-all"):
                c.usage = True
                continue
            full = _commit_long(name)
            if full is None:
                continue
            if _COMMIT_LONG.get(full) and not eq:
                value = args[i] if i < len(args) else ""
                i += 1
            if full == "message":
                c.messages.append(value)
            elif full in ("file", "reuse-message", "reedit-message", "fixup", "squash"):
                c.message_from = f"--{full}"
            if full == "all" or full in _COMMIT_PICKS:
                c.all = True
            elif full == "include":
                c.include = True
            elif full == "only":
                c.include = False
            elif full == "dry-run" or full == "no-dry-run":
                c.dry = full == "dry-run"
            elif full.removeprefix("no-") in _COMMIT_STATUS:
                c.status = not full.startswith("no-")
            elif full == "null" or full == "no-null":
                c.null = full == "null"
            elif full == "pathspec-from-file":
                c.spec_file = value
            elif full == "pathspec-file-nul":
                c.spec_nul = True
            elif full in ("amend", "no-amend"):
                c.amend = full == "amend"
            continue
        if a.startswith("-") and len(a) > 1:
            for j, ch in enumerate(a[1:], 1):
                if ch in _COMMIT_SHORT_VALUE:
                    value = a[j + 1 :]
                    if j == len(a) - 1:
                        value = args[i] if i < len(args) else ""
                        i += 1
                    if ch == "m":
                        c.messages.append(value)
                    elif ch in "FCc":
                        c.message_from = f"-{ch}"
                    break
                if ch in _COMMIT_SHORT_OPTIONAL:
                    break
                if ch in "ap":
                    c.all = True
                elif ch == "i":
                    c.include = True
                elif ch == "o":
                    c.include = False
                elif ch == "h":  # its usage, and no commit
                    c.usage = True
                elif ch == "z":
                    c.null = True
            continue
        c.specs.append(a)
    return c


# How the guard runs its own git reads: no fsmonitor, hook, signature check or replacement objects run or count, and a root commit's changes are shown.
_GIT_READ = ["git", "--no-replace-objects", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "diff.relative=false", "-c", "log.showSignature=false", "-c", "log.showRoot=true"]
_GIT_READ_SECONDS = 5  # the most one git read may take


def _git_read(
    d: str, glob: list[str], *args: str, sep: str = "\0", env: dict[str, str] | None = None, ok: tuple[int, ...] = (0,), raw: bool = False,
    timeout: float = _GIT_READ_SECONDS, isolated: bool = False,
) -> tuple[list[str] | None, str]:
    """(git's output split on `sep`, else None; what failed, with git's own
    words). `glob` is the command's own options that change the repository
    or how pathspecs read, `env` the variables it sets for them, `ok` the
    exit codes that aren't a failure (`git config --get` exits 1 when it
    finds nothing), `raw` keeps bytes that aren't UTF-8 as they are (for
    names given back to git), `timeout` the most it may take, `isolated`
    that none of the session's own `GIT_*` variables reach git. No
    fsmonitor, hook or signature check runs, a root commit's changes are
    shown, and paths are from the top level."""
    cmd = [*_GIT_READ, *glob, *args]
    shown = "`git " + " ".join(args[:2]) + "`"
    base = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} if isolated else os.environ
    try:
        p = subprocess.run(cmd, cwd=d, capture_output=True, timeout=timeout, env={**base, **env} if env or isolated else None)
    except subprocess.TimeoutExpired:
        return None, f"{shown} took too long in `{d}`"
    except (OSError, ValueError) as e:
        return None, f"{shown} couldn't run in `{d}` ({e})"
    if p.returncode not in ok:
        err = p.stderr.decode("utf-8", errors="replace").strip().splitlines()
        return None, f"{shown} failed in `{d}`" + (f" ({err[0]})" if err else "")
    return [x for x in p.stdout.decode("utf-8", errors="surrogateescape" if raw else "replace").split(sep) if x], ""


def _passed_globals(glob: list[str]) -> list[str]:
    out, i = [], 0
    while i < len(glob):
        o = glob[i]
        name = o.split("=", 1)[0]
        if name in _GIT_REPO_GLOBALS:
            out += [o] if "=" in o else glob[i : i + 2]
            i += 1 if "=" in o else 2
            continue
        if o in _GIT_PATHSPEC_GLOBALS:
            out.append(o)
        if o == "-c" and i + 1 < len(glob) and glob[i + 1].split("=", 1)[0].casefold() == "core.worktree":
            out += glob[i : i + 2]  # where the work tree is; no other setting, so the reads run nothing
        i += 2 if o in _GIT_GLOBAL_VALUE else 1
    return out


def _spec_file(c: _Commit, d: str) -> tuple[list[str] | None, str]:
    """The pathspecs `--pathspec-from-file` reads, or (None, what the guard
    couldn't read): only a regular file, and only so much of it."""
    if c.spec_file == "-":
        return None, "the pathspecs it takes from its stdin (`--pathspec-from-file=-`)"
    if not c.spec_file:
        return None, "its pathspec file, which the shell names (a process substitution, `<(…)`)"
    p = _abspath(c.spec_file, d) or c.spec_file
    try:
        st = os.stat(p)
        if not stat.S_ISREG(st.st_mode) or st.st_size > _SPEC_FILE_CAP:
            return None, f"its pathspec file `{c.spec_file}` (not a file of at most {_SPEC_FILE_CAP:,} bytes)"
        text = Path(p).read_text(encoding="utf-8")
    except (OSError, ValueError) as e:
        return None, f"its pathspec file `{c.spec_file}` ({e.__class__.__name__})"
    lines = [x for x in text.split("\0" if c.spec_nul else "\n") if x.strip()]
    if not c.spec_nul and any(x.startswith('"') for x in lines):
        return None, f"its pathspec file `{c.spec_file}`, whose quoted lines git unquotes"
    return lines, ""


def _carried(d: str, glob: list[str], c: _Commit, env: dict[str, str] | None = None, staged: bool = True) -> tuple[list[str] | None, str]:
    """The files (from the top level) a commit run in `d` would carry, or
    (None, what couldn't be read). Without `staged`, only the working tree's
    changes that `-a` or a pathspec adds: a commit finishing a merge counts
    the merge's own changes in place of what is staged (#391)."""
    specs = c.specs
    diff = ["diff", "--name-only", "-z", "--no-renames"]
    reads = []
    if staged and (not specs or c.include or c.all):
        reads.append([*diff, "--cached"])
    if c.all:
        reads.append(diff)
    if specs:
        reads += [[*diff, "--cached", "--", *specs], [*diff, "--", *specs]] if staged else [[*diff, "--", *specs]]
    out: list[str] = []
    for args in reads:
        got, err = _git_read(d, glob, *args, env=env)
        if got is None:
            return None, err
        out += [x for x in got if x not in out]
    return out, ""


# ---------- a merge's own changes (#391) ----------
#
# A merge commit, and the commit finishing a merge, count only the merge's own
# changes. A merge of two parents is compared with those parents merged again
# (`--diff-merges=remerge`): what git merges cleanly isn't counted, whatever
# lines or renames it spans, while a conflict resolved (taking one parent's
# version included) or a change neither parent has is. Read as a patch, whose
# headers also name a conflict that changed no content (a binary file, a
# rename against a deletion). git skips that for a merge of more parents,
# which is read as `git diff-tree --cc -U0` reads it.

_MERGE_OWN = "the merge's own change (a conflict resolved there, or a change neither parent has)"
_LOG_PLAIN = ["--no-renames", "--no-ext-diff", "--no-textconv", "--no-color", "--ignore-submodules=none"]  # no helper program, as git stores it
_COMMIT_FORMAT = "--format=%x01%x02%h%x03%H"  # shown short; read by its full name, which no ref can shadow
# Every commit but a merge, by its files: `--raw`, so each path follows its `:<modes> …` item and a name never reads as a header.
_FILES = ["--raw", "-z", _COMMIT_FORMAT, "--diff-merges=off", *_LOG_PLAIN]
_REMERGE = [
    "--min-parents=2", "--max-parents=2", _COMMIT_FORMAT, "--diff-merges=remerge", "-p", "-U0",
    "--src-prefix=a/", "--dst-prefix=b/", *_LOG_PLAIN,
]  # fmt: skip
_OCTOPUS = ["--min-parents=3", _COMMIT_FORMAT, "--cc", "-U0", "--inter-hunk-context=0", "--text", "--diff-algorithm=myers", "--no-indent-heuristic", *_LOG_PLAIN]
_REMERGE_CONFIG = ["-c", "merge.renormalize=false"]  # merging again runs no clean filter
_OBJECT_NAME = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_C_ESCAPES = {"a": 7, "b": 8, "t": 9, "n": 10, "v": 11, "f": 12, "r": 13, '"': 34, "\\": 92}
_OCTAL = re.compile(r"[0-3][0-7][0-7]")
_FULL_INDEX = ["-c", "core.splitIndex=false"]  # the guard's copy of the index is written whole, adding no shared index
_UNMERGED_CAP = 1000  # the most unmerged files the guard settles in its copy of the index
_PATCH_LINE_CAP = 1 << 16  # a longer line of a patch that starts no header is passed over, not kept
_DRIVER_RUNS = "git's config names a merge driver (`{}`), which merging the parents again would run"


def _c_unquoted(name: str) -> tuple[str, str]:
    """(the C-quoted name `name` starts with, unquoted; the rest after it),
    as git quotes a path that needs it (octal escapes for bytes)."""
    out, i = bytearray(), 1
    while i < len(name) and name[i] != '"':
        ch = name[i]
        if ch == "\\" and i + 1 < len(name):
            nxt = name[i + 1]
            if nxt in _C_ESCAPES:
                out.append(_C_ESCAPES[nxt])
                i += 2
                continue
            if _OCTAL.fullmatch(name[i + 1 : i + 4]):
                out.append(int(name[i + 1 : i + 4], 8))
                i += 4
                continue
        out += ch.encode("utf-8", errors="surrogateescape")
        i += 1
    return out.decode("utf-8", errors="replace"), name[i + 1 :]


def _patch_path(line: str) -> str | None:
    """The path a patch's file header names: a combined diff's `diff --cc
    <path>`, or `diff --git a/<path> b/<path>` (renames off, so both are one
    path), each C-quoted when the name needs it; else None."""
    if line.startswith("diff --cc "):
        name = line[len("diff --cc ") :]
        return _c_unquoted(name)[0] if name.startswith('"') else name
    if not line.startswith("diff --git "):
        return None
    rest = line[len("diff --git ") :]
    if rest.startswith('"'):
        name = _c_unquoted(rest)[0]
        return name[2:] if name.startswith("a/") else None
    half = (len(rest) - 5) // 2  # `a/<path> b/<path>`
    return rest[2 : 2 + half] if rest.startswith("a/") and half > 0 else None


def _c_quoted(path: str) -> str:
    """`path` in the C quotes git reads in `GIT_ALTERNATE_OBJECT_DIRECTORIES`,
    whose entries a `:` separates."""
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _heads_in_progress(d: str, glob: list[str], name: str = "MERGE_HEAD") -> list[str]:
    """The commits named by the file `name` of an operation in progress in
    `d` (`MERGE_HEAD`, what a merge merges; `REVERT_HEAD`, what a revert
    undoes), else []: none in progress, or a file git couldn't read either."""
    got, _ = _git_read(d, glob, "rev-parse", "--git-path", name, sep="\n")
    if not got or len(got) != 1:
        return []
    try:
        with open(os.path.join(d, got[0]), "rb") as f:
            heads = f.read(64 * 1024).decode("ascii").split()
    except (OSError, ValueError):
        return []
    return heads if heads and all(_OBJECT_NAME.fullmatch(h) for h in heads) else []


def _merge_driver(d: str, glob: list[str]) -> tuple[str, str]:
    """(a merge driver git's config names, `merge.<name>.driver`, in any file
    git reads, the global one included, else ""; what failed). Merging a
    merge's parents again would run it, so the guard doesn't: such a merge is
    one it can't tell about."""
    got, err = _memo_read(d, glob, "config", "--name-only", "--get-regexp", r"^merge\..*\.driver$", sep="\n", ok=(0, 1))
    return (got[0] if got else ""), ("" if got is not None else err)


@contextlib.contextmanager
def _scratch_store(d: str, glob: list[str], index: bool = True):
    """(the environment of a temporary object store that reads the
    repository's objects as alternates, with a copy of its index when
    `index`, else None; what failed). git's own temporary objects (a
    merge's parents merged again) go there, and go with it, so the
    repository is left as it was."""
    import tempfile  # here, not at the top: only a read of a merge needs it, and the hook starts on every tool

    got, err = _memo_read(d, glob, "rev-parse", "--git-path", "index", "--git-path", "objects", sep="\n")
    if not got or len(got) != 2:
        yield None, err or "git named no object store"
        return
    index_path, objects = (os.path.abspath(os.path.join(d, x)) for x in got)
    try:
        tmp = tempfile.TemporaryDirectory(prefix="workflow-guard-")
    except OSError as e:
        yield None, f"it couldn't make a temporary folder ({e.__class__.__name__})"
        return
    with tmp:
        # The session's own alternates, a relative one from the top level as git reads it, since the guard's reads may run elsewhere.
        theirs = os.environ.get("GIT_ALTERNATE_OBJECT_DIRECTORIES") or ""
        if theirs and '"' not in theirs:  # a C-quoted list is passed on as git reads it
            top, _ = _memo_read(d, glob, "rev-parse", "--show-toplevel", sep="\n")
            base = top[0] if top else d
            theirs = ":".join(e if os.path.isabs(e) else os.path.join(base, e) for e in theirs.split(":") if e)
        alternates = [_c_quoted(objects), *([theirs] if theirs else [])]
        env = {
            "GIT_INDEX_FILE": os.path.join(tmp.name, "index"), "GIT_OBJECT_DIRECTORY": os.path.join(tmp.name, "objects"),
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": ":".join(alternates), "GIT_NO_LAZY_FETCH": "1",
        }  # fmt: skip
        try:
            os.mkdir(env["GIT_OBJECT_DIRECTORY"])
            if index and os.path.exists(index_path):
                with open(index_path, "rb") as src, open(env["GIT_INDEX_FILE"], "wb") as dst:
                    dst.write(src.read())
        except OSError as e:
            yield None, f"it couldn't copy the index ({e.__class__.__name__})"
            return
        yield env, ""


def _settle_unmerged(d: str, glob: list[str], env: dict[str, str]) -> str:
    """Settles each unmerged file in the index copy `env` names on one
    version (`HEAD`'s, else the merged commit's; removed with neither), so the
    index can be written as a tree. git commits none of them as they are
    (`-a` takes the working tree's, which count as they are): only the other
    files' changes are read from that tree. Returns what failed, else ""."""
    plain = [g for g in glob if g not in _GIT_PATHSPEC_GLOBALS]  # `:/` is read as git's magic
    # Names kept byte for byte (`raw`), since they are given back to git.
    got, err = _git_read(d, plain, "ls-files", "-u", "-z", "--full-name", "--", ":/", env={**env, "GIT_LITERAL_PATHSPECS": "0"}, raw=True)
    if got is None:
        return err
    stages: dict[str, dict[str, tuple[str, str]]] = {}
    for item in got:
        info, _, path = item.partition("\t")
        mode, sha, stage = (info.split() + ["", "", ""])[:3]
        stages.setdefault(path, {})[stage] = (mode, sha)
    if len(stages) > _UNMERGED_CAP:
        return f"more than {_UNMERGED_CAP:,} unmerged files"
    keep = [f"{v[0]},{v[1]},{path}" for path, by in stages.items() for v in [by.get("2") or by.get("3")] if v]  # from the top level
    gone = [path for path, by in stages.items() if not (by.get("2") or by.get("3"))]
    reads = [[a for k in keep for a in ("--cacheinfo", k)]] if keep else []
    if gone:
        prefix, err = _git_read(d, glob, "rev-parse", "--show-cdup", sep="\n", env=env)
        if prefix is None:
            return err
        reads.append(["--force-remove", "--", *(os.path.join(prefix[0] if prefix else "", g) for g in gone)])  # from `d`
    for args in reads:
        done, err = _git_read(d, [*_FULL_INDEX, *glob], "update-index", *args, sep="\n", env=env)
        if done is None:
            return err
    return ""


def _merge_own_code(d: str, glob: list[str], heads: list[str], code: _Code) -> tuple[_Hit | None, str]:
    """(the first code path among what the merge in progress in `d` would
    change of its own, committed from the index now, else None; what
    couldn't be read). The index is written as a merge commit with `HEAD`
    and `heads` as its parents, into a temporary object store, then read as
    a pushed merge is."""
    if len(heads) == 1:
        driver, err = _merge_driver(d, glob)
        if driver or err:
            return None, err or _DRIVER_RUNS.format(driver)
    with _scratch_store(d, glob) as (env, err):
        if env is None:
            return None, err
        env |= {"GIT_AUTHOR_NAME": "workflow guard", "GIT_AUTHOR_EMAIL": "guard@invalid", "GIT_COMMITTER_NAME": "workflow guard", "GIT_COMMITTER_EMAIL": "guard@invalid"}
        err = _settle_unmerged(d, glob, env)
        if err:
            return None, err
        tree, err = _git_read(d, [*_FULL_INDEX, *glob], "write-tree", sep="\n", env=env)
        if not tree or len(tree) != 1:
            return None, err or "`git write-tree` named no tree"
        parents = [a for h in ["HEAD", *heads] for a in ("-p", h)]
        merge, err = _git_read(d, glob, "commit-tree", "--no-gpg-sign", "-m", "merge", *parents, tree[0], sep="\n", env=env)
        if not merge or len(merge) != 1:
            return None, err or "`git commit-tree` named no commit"
        args = _REMERGE if len(heads) == 1 else _OCTOPUS
        found, err = _sent_code(d, [*glob, *_REMERGE_CONFIG], ["log", "-1", *args, "--end-of-options", merge[0], "--"], code, True, env)
    return (found[1] if found else None), err


# ---------- a revert of a commit on the base (#392) ----------
#
# A commit made by `git revert` names the commit it reverts ("This reverts
# commit <sha>"). When that commit is on the base branch's remote ref
# (`<remote>/<base>` of a remote fetching from `project.repo`) and the
# revert's code paths are as git's own revert of it leaves them (for a merge,
# of its change against its first parent, as `git revert -m 1` makes it), it
# is a revert, not code. git's own revert is that change undone on the
# revert's parent, merged as `git revert` merges (`git merge-tree`, in a
# temporary object store of the guard's own), with no conflict in a code
# path. So a later change a few lines away (or a rename since) doesn't count,
# while a line changed, put back elsewhere or left out, or a conflict
# resolved, does. A revert in progress (`REVERT_HEAD`) is read from the
# index the same way. The conductor reverts only a commit its run's ledger
# records the owner as allowing.


@dataclass
class _Revert:
    """What the revert rule makes of a commit that carries code."""

    kind: str  # "" (it names no commit it reverts), "allowed", "ungranted" (the conductor's, not in its ledger), "unmatched" or "unsure"
    named: str = ""  # the commit it reverts: its full SHA once found, else as the message names it
    why: str = ""  # unmatched: why it doesn't go through, after "but"; unsure: what the guard couldn't read
    pr: str = ""  # the pull request the reverted commit (on the base) merged, which GitHub's own **Revert** button can revert
    path: str = ""  # the code path where it isn't as git's revert leaves it, when it names one
    step: bool = False  # `why` ends with the plain step that fixes it (a revert in progress finished other than as it stands)


_REVERTS = re.compile(r"^This reverts commit ([0-9a-f]{7,64})\b", re.M)  # as `git revert` writes it, `--reference` included
_PR_SUBJECT = re.compile(r"^Merge pull request #(\d+) from |\(#(\d+)\)$")  # GitHub's merge commit, or a squash merge's subject
_REVERSING = re.compile(r"reversing\s+changes made to ([0-9a-f]{7,64})\b")  # `git revert -m <n>` names the parent it reverted against
_REVERT_CAP = 64  # the most reverts one command's pushes read
_REVERT_SECONDS = 8  # the most time one command spends reading reverts
_GIT_FETCH_HINT = "if it merged since this repository last fetched, run `git fetch` and try again"
# What may run beside a commit finishing a revert, which the guard reads as the index is when the command starts: what changes no file.
_SHELL_READS = {*_CHANGES_DIR, "echo", "true", ":", "pwd", "ls", "cat", "head", "tail", "wc", "grep"}  # not `printf -v` or `test -v`, which set or evaluate variables
_EDITOR_ENV = {"GIT_EDITOR", "EDITOR", "VISUAL"}  # set to `true` or `:` beside a finishing commit: no editor runs
_GIT_READS = {
    "status", "diff", "log", "show", "rev-parse", "ls-files", "ls-tree", "describe", "shortlog", "whatchanged", "cat-file",
    "for-each-ref", "rev-list", "merge-base", "blame",
}  # fmt: skip
_GIT_LISTS = {"branch": {"--show-current", "--list", "-l", "-a", "--all", "-r", "--remotes", "-v", "-vv", "--verbose"}, "remote": {"-v", "--verbose"}}  # listing, never writing
_GIT_READ_GLOBALS = {"--no-pager", "-P", "--no-optional-locks", "--literal-pathspecs"}  # global options that run nothing (and `-C <dir>`)


def _revert_head(d: str, glob: list[str]) -> str:
    """The commit a revert in progress in `d` undoes (its `REVERT_HEAD`), else ""."""
    got = _heads_in_progress(d, glob, "REVERT_HEAD")
    return got[0] if len(got) == 1 else ""


def _base_refs(d: str, glob: list[str], code: _Code) -> tuple[list[str] | None, str]:
    """(the base branch's remote refs here, `refs/remotes/<remote>/<base>` of
    each remote fetching from `project.repo` (`origin`'s, without one); what
    failed)."""
    if code.repo:
        listed, err = _memo_read(d, glob, "remote", "-v", sep="\n")
        if listed is None:
            return None, err
        remotes = sorted({line.partition("\t")[0] for line in listed if line.endswith(" (fetch)") and _project_url(line.partition("\t")[2][: -len(" (fetch)")], code.repo)})
    else:
        remotes = ["origin"]
    wanted = [f"refs/remotes/{r}/{code.base}" for r in remotes]
    if not wanted:
        return [], ""
    refs, err = _memo_read(d, glob, "for-each-ref", "--format=%(refname)", *wanted, sep="\n")
    return (None, err) if refs is None else ([r for r in refs if r in wanted], "")


def _on_base(d: str, glob: list[str], sha: str, code: _Code) -> tuple[str, str]:
    """Whether `sha` is on the base branch's remote ref: ("on", the ref
    holding it), ("off", the ref shown, `origin/main`), ("none", "") when
    there is no such ref here, or ("unsure", what failed)."""
    refs, err = _base_refs(d, glob, code)
    if refs is None:
        return "unsure", err
    if not refs:
        return "none", ""
    for ref in refs:
        outside, err = _memo_read(d, glob, "rev-list", "-1", sha, "--not", ref, "--", sep="\n")
        if outside is None:
            return "unsure", err
        if not outside:
            return "on", ref
    return "off", refs[0].removeprefix("refs/remotes/")


def _pr_of(d: str, glob: list[str], sha: str, ref: str) -> str:
    """The pull request whose merge `sha` is, by its subject, else "": a
    merge commit "Merge pull request #<n> from …", or a commit "… (#<n>)" on
    the first-parent line of `ref`, the base, as a squash merge is (a commit
    inside a merged pull request may name an issue so); either on the
    base's first-parent line, where a pull request into it merged."""
    subject, _ = _memo_read(d, glob, "log", "-1", "--format=%s", sha, "--", sep="\n")
    m = _PR_SUBJECT.search(subject[0]) if subject else None
    if not m:
        return ""
    line, _ = _memo_read(d, glob, "rev-list", "--first-parent", ref, "--not", f"{sha}^@", "--", sep="\n")
    return (m.group(1) or m.group(2)) if line and sha in line else ""


def _undone_by_git(d: str, glob: list[str], sha: str, first: str, parent: str, after: str | None, code: _Code, deadline: float) -> tuple[str, str]:
    """How the revert stands against git's own revert of `sha` (against
    `first`, its first parent) made on `parent`, the revert's parent:
    ("same", ""), ("differs", the first code path that isn't the same),
    ("conflict", a code path that conflicts there, or is unmerged in the
    index), ("unmerged", "") for an index with only other files unmerged,
    or ("unsure", what failed). git's revert is merged as `git revert`
    merges it (`git merge-tree`), with git's own text merge only: in an
    empty repository of the guard's own that borrows the project's objects,
    so no config, attribute, merge driver or `merge.default` of the
    project's, the session's or the system's decides a line, and nothing is
    written to the project. The revert is the commit `after`, or with None
    the index. Each read ends by `deadline`."""
    import time

    def left() -> float:
        return max(0.1, min(_GIT_READ_SECONDS, deadline - time.monotonic()))

    found, err = _memo_read(d, glob, "rev-parse", "--verify", "--quiet", "--show-object-format", f"{parent}^{{commit}}", sep="\n")
    if not found or len(found) != 2:
        return "unsure", err or f"`git rev-parse` couldn't name `{parent}`"
    fmt, parent = found
    with _scratch_store(d, glob, index=after is None) as (env, err):
        if env is None:
            return "unsure", err
        if after is None:
            plain = [g for g in glob if g not in _GIT_PATHSPEC_GLOBALS]  # `:/` is read as git's magic
            unmerged, err = _git_read(d, plain, "ls-files", "-u", "-z", "--full-name", "--", ":/", env={**env, "GIT_LITERAL_PATHSPECS": "0"}, raw=True, timeout=left())
            if unmerged is None:
                return "unsure", err
            if unmerged:
                paths = [item.partition("\t")[2] for item in unmerged]
                hit = next((x for x in paths if _listed_code(x, code)), None)
                return ("conflict", hit) if hit else ("unmerged", "")
            tree, err = _git_read(d, [*_FULL_INDEX, *glob], "write-tree", sep="\n", env=env, timeout=left())
            if not tree:
                return "unsure", err or "`git write-tree` named no tree"
            after = tree[0]
        home = os.path.dirname(env["GIT_OBJECT_DIRECTORY"])
        iso = {
            "GIT_DIR": os.path.join(home, "empty.git"), "GIT_OBJECT_DIRECTORY": env["GIT_OBJECT_DIRECTORY"],
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": env["GIT_ALTERNATE_OBJECT_DIRECTORIES"], "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_ATTR_NOSYSTEM": "1", "GIT_NO_LAZY_FETCH": "1", "HOME": home, "XDG_CONFIG_HOME": home,
        }  # fmt: skip
        made, err = _git_read(home, [], "init", "--bare", "-q", "--template=", f"--object-format={fmt}", iso["GIT_DIR"], env={k: v for k, v in iso.items() if k != "GIT_DIR"}, isolated=True, timeout=left())
        if made is None:
            return "unsure", err
        undone, err = _git_read(home, [], "merge-tree", "--write-tree", "-z", "--name-only", "--no-messages", f"--merge-base={sha}", parent, first, env=iso, ok=(0, 1), raw=True, isolated=True, timeout=left())
        if not undone:
            return "unsure", err or "`git merge-tree` named no tree"
        hit = next((x for x in undone[1:] if _listed_code(x, code)), None)
        if hit:
            return "conflict", hit
        differs, err = _git_read(home, [], "diff-tree", "-r", "-z", "--name-only", "--no-renames", "--ignore-submodules=none", undone[0], after, "--", env=iso, raw=True, isolated=True, timeout=left())
        if differs is None:
            return "unsure", err
    hit = next((x for x in differs if _listed_code(x, code)), None)
    return ("differs", hit) if hit else ("same", "")


def _revert_rule(d: str, glob: list[str], named: str, parent: str, after: str | None, code: _Code, deadline: float, mainline: str = "") -> _Revert:
    """What the revert rule makes of a revert of the commit `named`, on
    `parent`: the commit `after`, or with None the index (a revert in
    progress). `mainline` is the parent its message says a merge was
    reverted against ("reversing changes made to <sha>"). Reading it ends by
    `deadline`."""
    import time

    if time.monotonic() > deadline:
        return _Revert("unsure", named, f"it ran out of time ({_REVERT_SECONDS} seconds for the command's reverts)")
    found, err = _memo_read(d, glob, "rev-parse", "--verify", "--quiet", f"{named}^{{commit}}", sep="\n", ok=(0, 1))
    if found is None:
        return _Revert("unsure", named, f"it couldn't read the commit it names ({err})")
    if len(found) != 1 or not found[0].startswith(named):  # a ref of that name isn't the commit
        return _Revert("unmatched", named, f"no commit here is named {named[:12]}: {_GIT_FETCH_HINT}")
    sha = found[0]
    short = sha[:7]
    on, ref = _on_base(d, glob, sha, code)
    if on == "unsure":
        return _Revert("unsure", sha, f"it couldn't read whether {short} is on the base branch ({ref})")
    if on == "none":
        return _Revert("unsure", sha, f"there is no remote ref of the base branch `{code.base}` here to find {short} on: run `git fetch` and try again")
    if on == "off":
        return _Revert("unmatched", sha, f"{short} isn't on `{ref}`, the base branch as last fetched: {_GIT_FETCH_HINT}; if it never merged, there is nothing on the base to revert")
    pr = _pr_of(d, glob, sha, ref)
    parents, err = _memo_read(d, glob, "rev-list", "--parents", "-n1", sha, "--", sep="\n")
    if parents is None:
        return _Revert("unsure", sha, f"it couldn't read the parents of {short} ({err})", pr)
    ids = parents[0].split()[1:] if parents else []
    if not ids:
        shallow, _ = _memo_read(d, glob, "rev-parse", "--is-shallow-repository", sep="\n")
        if shallow == ["true"]:
            return _Revert("unsure", sha, f"{short}'s parent isn't in this shallow clone: run `git fetch --unshallow` and try again", pr)
        return _Revert("unmatched", sha, f"{short} is the first commit, with no change to undo against a parent", pr)
    exact = f"it doesn't exactly undo {short}"
    how, path = _undone_by_git(d, glob, sha, ids[0], parent, after, code, deadline)
    if how == "unmerged":
        return _Revert("unmatched", sha, "files outside the code paths are still unmerged: `git add` them once resolved, then finish it with `git commit --no-edit`, each in a command of its own", step=True)
    if how == "conflict":  # GitHub's **Revert** button would meet the same conflict
        return _Revert("unmatched", sha, f"{exact}: undoing it conflicts in `{_brief(path)}`, and resolving that is writing code", "", path)
    if how == "differs":
        other = mainline and len(ids) > 1 and not ids[0].startswith(mainline)  # its message says it was made against another parent
        hint = f": a merge is reverted against its first parent, as `git revert -m 1 {short}` does" if other else ""
        return _Revert("unmatched", sha, f"{exact}: `{_brief(path)}` isn't as `git revert` of {short} leaves it{hint}", pr, path)
    if how == "unsure":
        return _Revert("unsure", sha, f"it couldn't undo {short} as `git revert` does: {path}", pr)
    if code.conductor() and sha not in code.allowed_reverts():
        return _Revert("ungranted", sha, "", pr)
    return _Revert("allowed", sha, "", pr)


def _commit_revert(d: str, glob: list[str], commit: str, code: _Code) -> _Revert:
    """What the revert rule makes of `commit` (its full name), read once for
    each command: "" when its message names no commit it reverts."""
    import time

    memo = _PUSH_MEMO if _PUSH_MEMO is not None else {}
    key = ("revert", d, tuple(glob), commit)
    if key in memo:
        return memo[key]
    msg, err = _memo_read(d, glob, "log", "-1", "--format=%B", commit, "--", sep="\0")
    m = _REVERTS.search("".join(msg)) if msg is not None else None
    deadline = memo.setdefault("reverts end", time.monotonic() + _REVERT_SECONDS)
    if msg is None:
        v = _Revert("unsure", "", f"it couldn't read the message of commit {commit[:7]} ({err})")
    elif not m:
        v = _Revert("")
    elif memo.setdefault("reverts read", 0) >= _REVERT_CAP:
        v = _Revert("unsure", m.group(1), f"there are more than {_REVERT_CAP} reverts to read")
    else:
        memo["reverts read"] += 1
        parents, err = _memo_read(d, glob, "rev-list", "--parents", "-n1", commit, "--", sep="\n")
        ids = parents[0].split() if parents else []
        if parents is None:
            v = _Revert("unsure", m.group(1), f"it couldn't read the parents of commit {commit[:7]} ({err})")
        elif len(ids) != 2:
            v = _Revert("unmatched", m.group(1), f"a revert has one parent, and commit {commit[:7]} has " + ("none" if len(ids) < 2 else f"{len(ids) - 1}"))
        else:
            to = _REVERSING.search("".join(msg))
            v = _revert_rule(d, glob, m.group(1), ids[1], ids[0], code, deadline, to.group(1) if to else "")
    memo[key] = v
    return v


def _revert_refusal(what: str, hit: _Hit, v: _Revert, code: _Code, to: str = "", abort: bool = False) -> str:
    """A refusal of a revert the rule doesn't let through: `what` is what
    carries the code path ("this commit", "this push sends commit 1a2b3c4,
    which"), `to` where a push goes, `abort` whether a revert is in progress."""
    short = v.named[:7]
    if v.path and v.path != hit.path and _listed_code(v.path, code):
        hit = _Hit(v.path, _listed_code(v.path, code) or "", hit.worktree)
    carries = f"{what} carries the code path {_shown(hit)} ({hit.pattern}){to}"
    if v.kind == "ungranted":
        entry = f'{{"what": "revert", "revert": "{v.named}", "at": …, "grant": "<the owner\'s words and where they were given>"}}'
        if len(v.named) != 40:  # `WF state put` takes a 40-character SHA: a SHA-256 repository's ledger can't name it
            return f"{carries}: it reverts {short} exactly, but the conductor reverts only a commit its ledger names, and the ledger takes 40-character SHAs, not this repository's: tell the owner, who can make this revert"
        return (
            f"{carries}: it reverts {short} exactly, but the conductor reverts only a commit the owner allowed: ask the owner first, on the "
            f"tracking issue or in your chat, and once they allow it record their yes in the run's ledger, `{entry}`, in `.workflow/run/body.md` "
            "(`WF state put`, then the tracking issue's body), then try again"
        )
    cancel = " (or `git revert --abort` cancels the revert)" if abort else ""
    if v.step:
        return f"{carries}: it finishes a revert of {short}, but not as it stands: {v.why}{cancel}"
    entry = code.conductor() and v.named in code.allowed_reverts()
    return f"{carries}: it names itself a revert of {short}, but {v.why}{cancel}. Only a revert that exactly undoes a commit on the base goes through; {_revert_way(code, v.pr, entry)}"


def _expanded_specs(seg: Seg, c: _Commit, literal: bool) -> tuple[list[str], str | None]:
    """(the commit's pathspecs with their brace lists expanded, what the guard
    can't read among them: the file names `xargs` gives it, a word the shell
    expands, or, where git reads pathspecs literally, a glob the shell may)."""
    if seg.fed:
        return [], "the file names `xargs` gives it"
    specs: list[str] = []
    for s in c.specs:
        if "{}" in s:
            return [], "the file names `find -exec` gives it"
        words = _braces(s, _BRACE_LIMIT + 1)
        if _SHELL_EXPANDS.search(s) or len(words) > _BRACE_LIMIT or any(_brace_sequence(w) for w in words):
            return [], f"its pathspec `{s}`, which the shell expands"
        if literal and any(_GLOB_CHARS.search(w) for w in words):
            return [], f"its pathspec `{s}`, a glob the shell may expand where git reads pathspecs literally"
        specs += words
    return specs, None


def _assigned(seg: Seg) -> dict[str, str]:
    """The variables a command's `NAME=value` (or `NAME+=value`) prefixes set."""
    out: dict[str, str] = {}
    for a in seg.assigns:
        name, _, value = a.partition("=")
        out[name.removesuffix("+")] = value
    return out


def _continues(sub: str, a: str) -> bool:
    """Whether `a` finishes a `git <sub>` in progress: `--continue` from
    `--con` on, as git takes it, and for `git am` its `--resolved` and `-r`."""
    if len(a) >= 5 and "--continue".startswith(a):
        return True
    return sub == "am" and (bool(_AM_RESOLVED.fullmatch(a)) or (len(a) >= 5 and "--resolved".startswith(a)))


def _written_before(segs: list[Seg], seg: Seg, name: str, d: str, root: Path) -> bool:
    """Whether the command writes the file `name` (from `d`) before `git
    commit` reads it: an earlier part, or the commit's own redirect, which the
    shell opens first. A target relative to a directory the guard can't
    follow counts when its name is the file's."""
    target = _abspath(name, d)
    for s in segs:
        t = _write_targets(s, root) if s is not seg else _Targets(files=list(s.redirects))
        for f, tree in [(f, False) for f in t.files] + [(f, True) for f in t.trees]:  # `mv` and `cp -r` write trees
            if os.path.isabs(f) or s.cwd is not None:
                a = _abspath(f, s.cwd)
                if a and (a == target or (tree and target and target.startswith(a.rstrip("/") + "/"))):
                    return True
            elif posixpath.basename(f) == posixpath.basename(name):
                return True
        if s is seg:
            return False
    return False


def _commit_git(words: list[str]) -> tuple[list[str], list[str], str | None] | None:
    """`_git`'s reading of a command, found behind wrappers as in ticket
    sessions, with git's dashed `git-commit` read as `git commit` when it is
    the command word (`grep git-commit`, a URL ending in it, only read)."""
    if words and posixpath.basename(words[0]) == "git-commit":
        return [], ["commit", *words[1:]], None
    k = _vcs_index(words, "ticket")
    return _git(words[k:]) if k is not None else None


# The options of `git init`, `git clone` and `git worktree add` that take the next word as their value.
_MAKES_VALUES = {
    "init": {"--template", "--separate-git-dir", "-b", "--initial-branch", "--object-format", "--ref-format"},
    "clone": {"-b", "--branch", "-o", "--origin", "--depth", "-c", "--config", "--reference", "--reference-if-able",
              "--template", "-u", "--upload-pack", "-j", "--jobs", "--separate-git-dir", "--filter", "--shallow-since",
              "--shallow-exclude", "--server-option", "--bundle-uri", "--ref-format", "--revision"},
    "worktree": {"-b", "-B", "--reason"},
}  # fmt: skip


def _made_where(s: Seg) -> tuple[str, str] | None:
    """(what `s` makes, "init", "clone" or "worktree", and where, absolute)
    when it is `git init`, `git clone`, `git worktree add` or `gh repo clone`
    at a place the guard can follow; else None, as for an init whose
    `GIT_DIR` or `--git-dir` puts the repository elsewhere (git reads a
    relative one from the place it makes; a clone ignores both)."""
    if s.cwd is None:
        return None
    git_dir = _assigned(s).get("GIT_DIR")
    gh = bool(s.words[:1]) and posixpath.basename(s.words[0]) == "gh" and s.words[1:3] == ["repo", "clone"]
    bare = False
    if gh:
        kind, rest = "clone", s.words[3:]
    else:
        g = _commit_git(s.words)
        args = g[1] if g else []
        for k, w in enumerate(g[0] if g else []):
            if w.startswith("--git-dir="):
                git_dir = w.partition("=")[2]
            elif w == "--git-dir" and k + 1 < len(g[0]):
                git_dir = g[0][k + 1]
        if args[:1] in (["init"], ["clone"]):
            kind, rest = args[0], args[1:]
        elif args[:2] == ["worktree", "add"]:
            kind, rest = "worktree", args[2:]
        else:
            return None
        s = replace(s, cwd=_git_dir_of(Path("/"), s.cwd, g[2]))
    words, i, values = [], 0, _MAKES_VALUES.get(kind, set()) | ({"--upstream-remote-name"} if gh else set())
    while i < len(rest):
        w = rest[i]
        i += 1
        if w == "--":
            if gh:  # after `gh repo clone`'s `--` come git's own flags
                bare = bare or any(x in ("--bare", "--mirror") for x in rest[i:])
            else:
                words += rest[i:]
            break
        if w.startswith("-"):
            bare = bare or w in ("--bare", "--mirror")
            i += 1 if w in values else 0
            continue
        words.append(w)
    if kind == "init":
        at = words[0] if words else "."
    elif kind == "clone":
        if not words:
            return None
        at = words[1] if len(words) > 1 else _clone_name(words[0], bare)
        if not at:
            return None
    else:
        if not words:
            return None
        at = words[0]
    a = _abspath(at, s.cwd)
    if a and kind == "init" and git_dir is not None and _abspath(git_dir, a) != os.path.join(a, ".git"):
        return None
    return (kind, a) if a else None


def _clone_name(source: str, bare: bool) -> str:
    """The directory `git clone <source>` makes with none named: the source's
    last part, without `/.git`, `.git` or `.bundle` (`.git` added for a bare
    clone)."""
    name = source.rstrip("/").removesuffix("/.git").rstrip("/")
    name = re.split(r"[/:]", name)[-1]
    for suffix in (".git", ".bundle"):
        name = name.removesuffix(suffix)
    return name + ".git" if name and bare else name


def _makes_repository(kind: str, at: str) -> bool:
    """Whether `git init`, `git clone` or `git worktree add` makes a new
    repository or worktree at `at`: an init where none is yet (else it
    reinitialises that one), a clone or worktree into a place that doesn't
    exist yet or is an empty directory (else it fails)."""
    if kind == "init":
        return not os.path.exists(os.path.join(at, ".git"))
    try:
        return not os.path.exists(at) or (os.path.isdir(at) and not os.listdir(at))
    except OSError:  # a folder it can't list: made there unless it holds a repository already
        return not os.path.exists(os.path.join(at, ".git"))


def _nearer_repository(where: str, at: str) -> bool:
    """Whether a folder from `where` up to `at` (not included) already holds a
    `.git`, which git finds first: what is made at `at` is then not where
    the commit goes."""
    p = where
    while p != at and p != os.path.dirname(p):
        if os.path.exists(os.path.join(p, ".git")):
            return True
        p = os.path.dirname(p)
    return False


def _made_by(segs: list[Seg], seg: Seg, where: str) -> str | None:
    """Whether another part of the command makes a repository or worktree
    (`git init`, `git clone`, `gh repo clone`, `git worktree add`) at `where`
    (the commit's directory) or a folder holding it, with no repository
    already nearer, so what git would commit into there isn't on disk yet:
    "earlier" for a part before the commit, else "later" for one after it
    (which may still run first: the commit in the background, a pipeline,
    a loop), else None."""
    later = False
    for s in segs:
        if s is seg:
            later = True
            continue
        m = _made_where(s)
        if m and (where == m[1] or where.startswith(m[1].rstrip("/") + "/")) and _makes_repository(*m) and not _nearer_repository(where, m[1]):
            return "later" if later else "earlier"
    return None


# A `.git` (any case, as a case-insensitive file system finds it) as a word or a path's part, not `.gitignore` or `demo.git`.
# Only the name itself: the word around it is found by hand, so a long word costs no more than its length.
_DOT_GIT = re.compile(r"(?<![\w.])\.git(?![\w.-])", re.IGNORECASE)  # `${x:-.git}` is one
_QUOTING = str.maketrans("", "", "\"'\\")


def _names_dot_git(command: str, segs: list[Seg]) -> str | None:
    """The word of the command that names a `.git`: one it may read, write,
    link, move or remove, which can change where git commits; else None.
    Searched in the command's whole text (a loop's list, a here-string, a
    part that runs first in the background), that text with its quotes and
    backslashes taken out (`.g"it"`), the command's words as the shell
    decodes them (`.g$'i't`, a loop's list among them), and each part's
    words as the guard reads them (`sh -c`'s, `eval`'s)."""
    texts = [command, command.translate(_QUOTING)]
    texts += [t for t in _tokens(command) if isinstance(t, str)]  # every word, a loop's list too, as the shell decodes it
    for s in segs:
        texts += [*s.words, *s.assigns, *s.redirects, *s.inputs, s.stdin or "", s.heredoc or ""]
    for t in texts:
        m = _DOT_GIT.search(t)
        if not m:
            continue
        a, b = m.start(), m.end()
        while a > 0 and not t[a - 1].isspace():
            a -= 1
        while b < len(t) and not t[b].isspace():
            b += 1
        w = t[a:b]
        return w if len(w) <= 80 else w[:79] + "…"
    return None


def _expands(s: Seg, literal: list[str] = ()) -> bool:
    """Whether the shell expands something in a part (a `$` or a backtick in
    its words, its variables' values, its redirects' targets, its unquoted
    heredocs or here-strings, or its `<` files), which can set a variable
    (`$[HOME=1]`) or run a command; or feeds it stdin it can't read. A
    heredoc whose delimiter is quoted (`<<'EOF'`) the shell never expands,
    whatever runs it; nor the `literal` words (a commit's message given as a
    quoted heredoc, `$(cat <<'EOF' … EOF)` in double quotes)."""
    words = [w for w in s.words if not any(w is x for x in literal)]
    texts = [*words, *(a.partition("=")[2] for a in s.assigns), *s.redirects, s.expanded, s.stdin or "", *s.inputs]
    return s.stdin_unseen or any("$" in t or "`" in t for t in texts)


def _reads_only(s: Seg, literal: list[str] = ()) -> bool:
    """Whether a part of the command changes no file, index or ref: a shell
    word that only reads or moves the shell (`cd` to the project's top
    level, as `$(git rev-parse --show-toplevel)` names it, included), or git
    itself (its own command word) running a read (`status`, `diff` without
    `--output`, `branch --show-current`, …) with no global option that runs
    or points at a program (`-c`, `--exec-path`), all with no wrapper (`time
    -o`), variable, expansion (`_expands`) or redirect other than to
    `/dev/null`."""
    if s.fed or not s.words or s.assigns or s.wrappers or any(r != "/dev/null" for r in s.redirects):
        return False
    if s.words[0] in _CHANGES_DIR and all(_TOPLEVEL.match(w) for w in s.words[1:] if "$" in w or "`" in w):
        return not (s.heredoc or s.stdin or s.inputs or s.stdin_unseen)
    if _expands(s, literal):
        return False
    if s.words[0] in _SHELL_READS:
        return True
    if s.words[0] != "git":  # git itself, not a program of that name elsewhere
        return False
    g = _commit_git(s.words)
    if not g or not g[1]:
        return False
    glob, (sub, *rest), i = g[0], g[1], 0
    while i < len(glob):
        if glob[i] == "-C":
            i += 2
            continue
        if glob[i] not in _GIT_READ_GLOBALS:
            return False
        i += 1
    if sub in _GIT_LISTS:
        return all(a in _GIT_LISTS[sub] for a in rest)
    return sub in _GIT_READS and not any(a.startswith("--output") for a in rest)


def _finishing_revert(segs: list[Seg], seg: Seg, d: str, glob: list[str], c: _Commit, env: dict[str, str], reverting: str, code: _Code) -> _Revert:
    """What the revert rule makes of a commit finishing a revert in progress
    in `d`, of the commit `reverting` (#392): read from the index, so only a
    commit of the index as it is, with the message `git revert` wrote (whose
    "This reverts commit" line tells a push it is a revert), in a command
    where nothing else runs but reads (`_reads_only`)."""
    import time

    why = ""
    # A message given as a quoted heredoc in double quotes (`-m "$(cat <<'EOF' … EOF)"`), as Claude Code writes one: its text, as written.
    literal = [w for w in seg.words if isinstance(w, Word) and not w.splits and w in c.messages and _literal_heredoc(w)]
    other = next((s for s in segs if s is not seg and not _reads_only(s, literal)), None)
    # A message given as `$(cat <<-'EOF' …)` reaches git with each line's leading tabs stripped, as the shell strips them.
    told = [("\n".join(x.lstrip("\t") for x in t.split("\n")) if _literal_heredoc(t) and re.match(r"\$\(\s*cat\s+<<-", t) else t) for t in c.messages]
    m = _REVERTS.search("\n\n".join(told))
    line = f'the "This reverts commit {reverting}." line, which tells a push it is a revert'
    raw = _commit_git(seg.words)
    own = [o for o in (raw[0] if raw else []) if o in ("-c", "--config-env", "--exec-path") or o.startswith(("--config-env=", "--exec-path"))]
    for a in seg.assigns:
        name, _, value = a.partition("=")
        name = name.removesuffix("+")
        if name not in _GIT_PATHSPEC_ENV and not (name in _EDITOR_ENV and value in ("true", ":")):
            own.append(name)
    if _expands(seg, literal):
        own.append("a value the shell expands")
    own += [f"`{w}`" for w in seg.wrappers if w != "command"]  # `env -u …`, `sudo`: what it runs under
    if own:  # a setting or variable of its own can run a hook that stages more (`-c core.hooksPath=…`, `HOME=…`, `$[HOME=1]`)
        what = own[0] if own[0].startswith(("a value", "`")) else f"`{_brief(own[0])}`"
        how = f"runs under {what}" if own[0].startswith("`") else f"sets {what} for itself"
        why = f"it {how}, which can change what it commits: finish it with plain `git commit --no-edit`"
    elif other is not None:
        shown = " ".join(other.words) or " ".join(other.assigns) or " ".join(f"> {r}" for r in other.redirects)
        part = f"`{_brief(shown)}`" if shown else "another part"
        why = (
            f"the command also runs {part}, which may change what it commits (only reads, such as `git status`, "
            "may run beside it): finish the revert in a command of its own"
        )
    elif c.amend:
        why = "`--amend` folds it into the commit before it: finish it with `git commit --no-edit` instead"
    elif c.specs and not c.include:
        why = "a pathspec commits only part of it: finish it with `git commit --no-edit`, naming no path"
    elif c.message_from:
        why = f"`{c.message_from}` takes its message from elsewhere, which the guard doesn't read: finish it with `git commit --no-edit`, which keeps {line}"
    elif c.messages and not (m and reverting.startswith(m.group(1))):
        why = f"its message (`-m`) leaves out {line}: finish it with `git commit --no-edit`, or keep that line"
    else:
        wt, err = _carried(d, glob, c, env, staged=False) if c.all or c.specs else ([], "")
        if wt is None:
            return _Revert("unsure", reverting, err)
        wt_code = next((f for f in wt if _listed_code(f, code)), None)
        if wt_code:
            why = f"it would also take the working tree's change to `{_brief(wt_code)}`, which isn't part of it: finish it with `git commit --no-edit` alone, which leaves that change where it is"
            return _Revert("unmatched", reverting, why, step=True, path=wt_code)
    if why:
        return _Revert("unmatched", reverting, why, step=True)
    msg, _ = _git_read(d, glob, "rev-parse", "--git-path", "MERGE_MSG", sep="\n")  # the message `git revert` wrote
    to = None
    if msg and len(msg) == 1:
        try:
            with open(os.path.join(d, msg[0]), encoding="utf-8", errors="replace") as f:
                to = _REVERSING.search(f.read(64 * 1024))
        except OSError:
            pass
    return _revert_rule(d, glob, reverting, "HEAD", None, code, time.monotonic() + _REVERT_SECONDS, to.group(1) if to else "")


def _commit_code(segs: list[Seg], code: _Code, root: Path, command: str) -> tuple[str | None, str | None]:
    """(why a commit in the command carries a code path, why the guard can't
    tell what one carries), each None when it doesn't apply."""
    unsure, project, note = None, None, None
    named = None
    for seg in segs:
        g = _commit_git(seg.words)
        if not g or not g[1]:
            continue
        glob, args, cdir = g
        if args[0] == "commit":
            c = _commit_args(args[1:])
        elif args[0] in _CONTINUE_COMMITS and any(_continues(args[0], a) for a in args[1:]):
            c = _Commit()
        else:
            continue
        d = _git_dir_of(root, seg.cwd, cdir)
        if c.dry_run or not d:
            continue  # a directory the guard can't follow: left to the push rule
        d = os.path.realpath(d)
        cant = f"the guard can't tell what `git {args[0]}` would commit"
        if named is None:
            named = _names_dot_git(command, segs) or ""
        # The notes below leave the commit judged, so a refusal stands; otherwise it is asked, when nothing more telling is.
        if named:
            note = note or f"{cant}: the command names `{named}`, which can change where git commits"
        if not os.path.isdir(d):  # made earlier in the command (a folder, a link, a repository), or never
            unsure = unsure or f"{cant}: it runs in `{d}`, which doesn't exist yet"
            continue
        made = _made_by(segs, seg, d)
        if made == "earlier":
            unsure = unsure or f"{cant}: it runs in `{d}`, where the command makes a repository or worktree first"
            continue
        if made == "later":
            note = note or f"{cant}: it runs in `{d}`, where a later part of the command makes a repository or worktree, which may run first"
        inside = _checkout_of(d, root) is not None
        assigned = _assigned(seg)
        env = sorted(set(assigned) & _GIT_REPO_ENV)
        if env:
            unsure = unsure or f"{cant}: it sets `{env[0]}`, which changes what git reads"
            continue
        glob = _passed_globals(glob)
        where, err = _git_read(d, glob, "rev-parse", "--show-toplevel", "--git-common-dir", sep="\n")
        if where is None or len(where) != 2:
            # Inside the project or not: git commits nothing there unless the command first makes
            # it a repository (a `.git` linked or written, in any spelling), so it is never left alone.
            unsure = unsure or f"{cant}: {err or 'git named no top level'}"
            continue
        if project is None:
            project = _common_dir(os.path.realpath(str(root))) or ""
        if not project:
            if inside:
                unsure = unsure or f"{cant}: it couldn't read the project's own repository"
            continue
        if os.path.realpath(os.path.join(d, where[1])) != project:
            continue  # another repository: another clone, or one nested in the project, left to the push rule
        moved = sorted(set(assigned) & _GIT_INDEX_ENV)
        if moved:
            unsure = unsure or f"{cant}: it sets `{moved[0]}`, which changes what git reads"
            continue
        top = os.path.realpath(where[0])
        wt = "" if top == os.path.realpath(str(root)) else _rel(top, root)
        if code.prototype_here(d, glob):
            continue  # a planning session's commit on a `prototype/*` branch (#393)
        literal = bool(_LITERAL_GLOBALS & set(glob)) or any(assigned.get(v, "0") not in ("", "0", "false") for v in _LITERAL_ENV)
        specs, unread = _expanded_specs(seg, c, literal)
        c = replace(c, specs=specs)
        if not unread and c.spec_file is not None and _written_before(segs, seg, c.spec_file, d, root):
            unread = f"its pathspec file `{c.spec_file}`, which the command writes before it"
        if not unread and c.spec_file is not None:
            more, unread = _spec_file(c, d)
            c = replace(c, specs=c.specs + (more or []), spec_file=None)
        if unread:
            c = replace(c, all=True, include=True, specs=[], spec_file=None)  # every change it could carry
        # A commit finishing a merge (`git commit` while one is in progress, `git merge --continue`) counts the merge's own changes.
        heads = _heads_in_progress(d, glob) if args[0] in ("commit", "merge") else []
        own, own_err = _merge_own_code(d, glob, heads, code) if heads else (None, "")
        finishing = "the commit finishing this merge" if args[0] == "commit" else f"the commit finishing this `git {args[0]}`"
        if own:
            hit = replace(own, worktree=wt)
            return f"{finishing} carries the code path {_shown(hit)} ({hit.pattern}), {_MERGE_OWN}; {code.instead}", None
        pathspec_env = {k: v for k, v in assigned.items() if k in _GIT_PATHSPEC_ENV}
        files, err = _carried(d, glob, c, pathspec_env, staged=not heads)
        if files is None:
            unsure = unsure or f"{cant}: {err}"
            continue
        # A commit finishing a revert (`git commit` while one is in progress, `git revert --continue`) is judged by the revert rule (#392).
        hits = [_Hit(f, m, wt) for f in files for m in [_listed_code(f, code)] if m] if args[0] in ("commit", "revert") and not heads and not unread else []
        reverting = _revert_head(d, glob) if hits else ""
        if reverting:
            v = _finishing_revert(segs, seg, d, glob, c, pathspec_env, reverting, code)
            if v.kind == "allowed":
                continue
            if v.kind == "unsure":
                unsure = unsure or f"{cant}: it couldn't tell whether it exactly undoes {reverting[:7]}: {v.why}"
                continue
            return _revert_refusal("the commit finishing this revert", hits[0], v, code, abort=True), None
        for f in files:
            m = _listed_code(f, code)
            if not m:
                continue
            hit = _Hit(f, m, wt)
            if unread:
                unsure = unsure or f"{cant}: it couldn't read {unread}, and the changes it could carry include the code path {_shown(hit)} ({hit.pattern})"
                break
            what = finishing if heads or args[0] != "commit" else "this commit"
            return f"{what} carries the code path {_shown(hit)} ({hit.pattern}); {code.instead}", None
        if own_err:  # it couldn't read the merge's own changes: asked when what is staged differs from a parent in code
            staged: list[str] | None = []
            for parent in ["HEAD", *heads]:
                got, _ = _git_read(d, glob, "diff", "--name-only", "-z", "--no-renames", "--cached", "--end-of-options", parent, "--", env=pathspec_env)
                staged = None if got is None or staged is None else staged + got
            hit = next((_Hit(f, m, wt) for f in staged or [] for m in [_listed_code(f, code)] if m), None)
            if hit or staged is None:
                shown = f", and what is staged differs from a parent in the code path {_shown(hit)} ({hit.pattern})" if hit else ""
                unsure = unsure or f"{cant}: it couldn't read the merge's own changes ({own_err}){shown}"
    return None, unsure or note


# ---------- a prototype on a `prototype/*` branch (#393) ----------
#
# A planning session (not the conductor) may try an idea in code on a branch
# named `prototype/*`: it may write and commit code paths in a checkout on
# such a branch, and push to `project.repo` from one when every ref git would
# update there is one. The branch is read as it is when the command starts,
# so a command that may change which branch HEAD names first gets no
# exception; each place that finds a code path (`_code_at`, `_named_code`,
# `git clean` in `_shell_code`, `_commit_code`) asks `_Code.prototype_here`
# of the checkout it found it in. Its code can't then reach another branch
# unjudged: the push rule counts as on the remote only the tracking refs git
# fills from a branch that isn't `prototype/*` (`_known_refs`).

_PROTOTYPE = "refs/heads/prototype/"
# git commands that never change which branch HEAD names, though they may move a branch's tip.
_KEEPS_HEAD = {"commit", "merge", "cherry-pick", "revert", "am", "reset", "tag", "notes", "fetch", "config", "remote", *_PUSH_CMDS}
# What finishes a rebase, on the branch it started on (`--quit` leaves HEAD detached).
_REBASE_ENDS = (["--continue"], ["--skip"], ["--abort"])


def _prototype_branch(ref: str) -> bool:
    """`refs/heads/prototype/<name>` (a `*` in a refspec's pattern standing for any name)."""
    return ref.startswith(_PROTOTYPE) and len(ref) > len(_PROTOTYPE)


# A `.git` given as a short option's value, attached (`cp -t.git`, `tar -C.git`), which `_DOT_GIT` reads as part of a word.
_DOT_GIT_OPTION = re.compile(r"(?:^|(?<=[\s=;|&({,]))-[A-Za-z0-9]+\.git(?![\w.-])", re.IGNORECASE)


def _moves_head(changers: "_Changers") -> str | None:
    """What in the command may change which branch a checkout's HEAD names
    (`git switch`, `checkout`, `rebase`, `stash`, `symbolic-ref`, a branch
    renamed, an alias, `gh pr checkout`), else None. The
    parts that may move a ref are the push rule's (`_Changers`); of those,
    only the git commands that move a branch's tip but never which branch
    HEAD names don't count, nor a rebase finished on the branch it started on."""
    for _s, what, label, args in changers.parts:
        if what not in ("refs", "push") or (args is not None and args[0] in _KEEPS_HEAD):
            continue
        if args is not None and args[0] == "rebase" and args[1:] in _REBASE_ENDS:
            continue
        return label
    return None


def _dot_git_named(command: str, segs: list[Seg]) -> str | None:
    """A `.git` the command names (`_names_dot_git`), or one given as a
    short option's value (`cp -t.git`) in any text it reads, else None."""
    named = _names_dot_git(command, segs)
    if named:
        return named
    for t in [command, *(t for s in segs for t in (*s.words, *s.assigns, *s.redirects, *s.inputs, s.stdin or "", s.heredoc or ""))]:
        m = _DOT_GIT_OPTION.search(t)
        if m:
            return m.group(0).strip()
    return None


def _claude_worktrees(abspath: str, root: Path) -> list[str]:
    """Claude Code's worktrees of the project (`.claude/worktrees/<name>`) inside
    `abspath`, a folder of the project: each a checkout with a branch of its own."""
    top = os.path.realpath(str(root))
    wts = os.path.join(top, ".claude", "worktrees")
    if not os.path.isdir(wts) or not (abspath == wts or _holds_root(abspath, root) or wts.startswith(abspath.rstrip("/") + "/")):
        return []
    try:
        return [os.path.join(wts, n) for n in sorted(os.listdir(wts)) if os.path.isdir(os.path.join(wts, n))]
    except OSError:
        return []


def _prototype_rule(code: _Code, segs: list[Seg], root: Path, command: str) -> _Code:
    """A planning session's rule for one command: no prototype exception when
    the command may change the branch first, and then its refusals say why
    when the project or one of Claude Code's worktrees is on a `prototype/*`
    branch. Its `_Changers` are kept for the push rule."""
    changers = _Changers(segs, root)
    code = replace(code, changers=changers)
    moves = _moves_head(changers)
    named = _dot_git_named(command, segs)  # in a commit's message or a file's text too
    unfollowed = _compound_or_cd(segs, command)
    if moves is None and named is None and unfollowed is None:
        return code
    code = replace(code, no_prototype=moves or named or unfollowed)
    top = os.path.realpath(str(root))
    if not any(code.on_prototype(t) for t in [top, *_claude_worktrees(top, root)]):
        return code
    hows = [f"runs `{moves}`: run them in commands of their own"] if moves else []
    if unfollowed:
        hows.append(unfollowed.removeprefix("it "))
    if named:
        hows.append(
            f"names `{named}`, which could: name no `.git` in it (run what names it in a command of its own, "
            "give a commit's message with `-F <file>`, or write a file with the file tools)"
        )
    how = ", and ".join(hows)
    note = (
        f"on a `prototype/*` branch, a planning session's code write or commit goes through only in a command "
        f"that can't change the branch first, and this one {how}. Otherwise, "
    )
    return replace(code, instead=note + code.instead)


def _push_own_part(segs: list[Seg], seg: Seg, glob: list[str], dot_git: str) -> list[str]:
    """What in a push's own part could change which config git reads, where
    it sends the push or what program runs for it, so a planning session's
    push to `prototype/*` branches isn't let through as one: anything but
    plain `git` as its command word (a wrapper, a program before it, a path
    to git), a variable set for it or anywhere in the command that git or
    the shell reads, a global option but `-C` and those that run nothing
    (`--no-pager`), a redirect but to `/dev/null`, a value the shell expands
    but `$(git branch --show-current)`, or a `.git` the command names."""
    own = [f"`{_brief(w)}` before git" for w in seg.words[:1] if w != "git"]
    own += [f"the wrapper `{w}`" for w in seg.wrappers]
    names = list(_assigned(seg))
    var = names[0] if names else _push_env(segs, seg, _PUSH_ENV) or _push_env(segs, seg, _PUSH_ENV_CONFIG) or _push_env(segs, seg, _PUSH_ENV_PROGRAMS)
    own += [f"the variable `{_brief(var)}`"] if var else []
    i = 0
    while i < len(glob):
        if glob[i] == "-C":
            i += 2
            continue
        if glob[i] not in _GIT_READ_GLOBALS:
            own.append(f"`{_brief(glob[i])}`" + (f" `{_brief(glob[i + 1])}`" if glob[i] in ("-c", "--config-env") and i + 1 < len(glob) else ""))
            break
        i += 1
    own += [f"a redirect to `{_brief(r)}`" for r in seg.redirects if r != "/dev/null"]
    current = [w for w in seg.words if ("$" in w or "`" in w) and not re.search(r"[$`]", _CURRENT_BRANCH.sub("", w))]
    if _expands(seg, current):
        own.append("a value the shell expands")
    if dot_git:
        own.append(f"`{dot_git}` named in the command")
    return own


# Shell words that open a compound command, whose header (a loop's variable, a `case` word) no part of the command keeps.
_COMPOUND_WORDS = {"for", "select", "case", "while", "until", "if", "function", "coproc", "repeat", "foreach"}  # zsh's too


def _compound_or_cd(segs: list[Seg], command: str) -> str | None:
    """Why the guard can't follow the command as the shell runs it, for a
    prototype's exception: a compound command (`for HOME in …; do …`, `case
    $[…]`, `if`, `function`), whose header can set a variable or run a program
    no part shows; or a change of directory (`cd`, `pushd`, `popd`), which
    the guard follows only so far (`popd -n`, a logical `..` after a link, a
    `--show-toplevel` from elsewhere). Else None."""
    # A compound word the lexer reads that no part keeps as an argument (`git log --grep for` keeps it) opens a
    # compound command, wherever it stands (`time -p for …`): counted, not placed.
    toks = _tokens(command)
    seen = Counter(t for t in toks if isinstance(t, str) and not isinstance(t, Op) and t in _COMPOUND_WORDS)
    # Kept by the command's own parts, not by text read again within one (`sh -c 'echo for'`, `eval`), which the
    # top-level words never hold.
    tops = [_strip_prefix(list(c.words))[0] for c in _simple(toks) if isinstance(c, _Cmd)]
    kept = Counter(w for words in tops for w in words[1:] if w in _COMPOUND_WORDS)
    opened = next((w for w in seen if seen[w] > kept[w]), None)
    if opened:
        return f"it holds the compound command `{opened}`, whose words the guard doesn't follow"
    moved = next((s.words[0] for s in segs if s.words and s.words[0] in _CHANGES_DIR), None)
    if moved:
        return f"it changes directory with `{moved}`, which the guard follows only so far: run it from that directory, or with `git -C`"
    alone = " (run the write, commit or push in a command of its own)"
    spelled = next((s.words[0] for s in segs if s.words and _spelled_command(s.words[0])), None)
    if spelled:
        return f"it runs a command the shell spells (`{_brief(spelled)}`), which the guard can't follow{alone}"
    # Only the shell's own builtins and assignments change its state (its directory, variables, what later words run);
    # a program it starts can't, and a script's own changes are a script's (unseen, as any).
    changes = next((s.words[0] for s in segs if s.words and s.words[0] in _BUILTINS and not _stateless_builtin(s.words)), None)
    if changes:
        return f"it runs the shell's `{changes}`, which can change what the command's later words do{alone}"
    assigned = next((s.assigns[0].partition("=")[0].removesuffix("+") for s in segs if not s.words and s.assigns), None)
    if assigned:
        return f"it sets `{_brief(assigned)}` for the rest of the command{alone}"
    joined = command.replace("\\\n", "")  # bash joins a backslash-newline before it reads anything
    if _CURRENT_SHELL_SUB.search(joined):
        return f"it runs a command substitution in the shell itself (`${{ …; }}`){alone}, or write the file with the file tools"
    if _ZSH_EVAL.search(joined) or any(isinstance(t, Op) and t.glued for t in toks):
        return (
            f"it may run code in the shell itself (zsh's glob qualifiers such as `*(e:…:)`, a `(` right after a word, "
            f"or `${{(e)…}}`, `${{~…}}`){alone}: give a commit's message with `-F <file>`, or write the file with the file tools"
        )
    if _ASSIGNING_EXPANSION.search(joined):
        return f"it may set a variable in the shell itself (`$((…))`, `$[…]`, `${{X:=…}}`){alone}, or write the file with the file tools"
    return None


# bash's builtins, and those that change nothing in the shell (its directory, variables, options, what words run).
_BUILTINS = {
    # zsh's too, where its precommand modifiers (`noglob cd …`) and option or variable builtins change the shell.
    "noglob", "nocorrect", "-", "setopt", "unsetopt", "emulate", "zmodload", "autoload", "functions", "integer", "float",
    "print", "chdir", "bindkey", "zstyle", "vared", "pushln", "rehash", "unhash", "zle", "zparseopts", "sched",
    "getln", "zformat", "zregexparse", "strftime", "zstat", "sysread", "disable", "unfunction",
    ".", ":", "[", "alias", "bg", "bind", "break", "builtin", "caller", "cd", "command", "compgen", "complete", "compopt",
    "continue", "declare", "dirs", "disown", "echo", "enable", "eval", "exec", "exit", "export", "false", "fc", "fg",
    "getopts", "hash", "help", "history", "jobs", "kill", "let", "local", "logout", "mapfile", "popd", "printf", "pushd",
    "pwd", "read", "readarray", "readonly", "return", "set", "shift", "shopt", "source", "suspend", "test", "times",
    "trap", "true", "type", "typeset", "ulimit", "umask", "unalias", "unset", "wait", "[[",
}  # fmt: skip
# (Not `[[`, whose `-eq X=1` assigns; `printf`, `wait` and `jobs` only without the option that sets or runs.)
_STATELESS_BUILTINS = {":", "echo", "pwd", "true", "false", "type", "help", "times", "dirs"}
# `printf -v VAR`, `wait -p VAR`, `jobs -x CMD`, `test -v 'A[X=1]'` (an arithmetic subscript): stateless without them.
_STATEFUL_OPTION = {"printf": "v", "wait": "p", "jobs": "x", "test": "v", "[": "v"}


def _stateless_builtin(words: list[str]) -> bool:
    """A builtin that changes nothing in the shell as it is given here: one
    of `_STATELESS_BUILTINS`, or one of `_STATEFUL_OPTION`'s without its
    option, written out (no argument the shell may turn into it: `{-x,}`,
    `${X:--x}` or `"${X:--x}"`, a glob)."""
    if words[0] in _STATELESS_BUILTINS:
        return True
    opt = _STATEFUL_OPTION.get(words[0])
    if opt is None:
        return False
    # An argument the shell may turn into others: the lexer's `splits` (unquoted), or `expands` (an expansion in
    # double quotes: `"${X:--x}"`, `"$(echo -x)"`); a word built elsewhere: may.
    return not any(
        w.startswith("-") and opt in w or getattr(w, "splits", True) or getattr(w, "expands", True) for w in words[1:]
    )
# bash 5.3's `${ cmd; }` and `${| cmd; }`, which run in the shell itself (a `cd` there stays).
_CURRENT_SHELL_SUB = re.compile(r"\$\{[\s|]")
# zsh's glob qualifiers that run code (`*(e:…:)`, `*(+fn)`) and parameter flags (`${(e)…}`), in the shell itself.
_ZSH_EVAL = re.compile(r"\$\{[(~]|\$~")  # `${(e)…}`, `${~…}`, `$~X`, live in double quotes too
# Arithmetic and `${X=…}`/`${X:=…}` expansions, which can assign a variable in the shell itself.
_ASSIGNING_EXPANSION = re.compile(r"\$\(\(|\$\[|\(\(|\$\{[^}]*?:?=")


def _spelled_command(word: str) -> bool:
    """A command word the shell turns into another (an expansion, a glob, a
    brace list: `${X:-cd}`, `c[d]`, `{cd,dir}`); `[` and `[[` are commands."""
    if word in ("[", "[["):
        return False
    return "$" in word or "`" in word or bool(_GLOB_CHARS.search(word)) or _brace_list(word)


def _busy_parts(segs: list[Seg], command: str) -> tuple[list[Seg], str | None]:
    """(the parts of the command that do more than read, `_reads_only`; why
    the guard can't follow the command, `_compound_or_cd`). A push to
    `prototype/*` branches is let through only as the one part beside reads,
    in a command it can follow, so nothing in the command can change git's
    config, HEAD, refs or directory, or run a program, before it runs."""
    return [s for s in segs if not _reads_only(s)], _compound_or_cd(segs, command)


def _fetch_dst(dst: str) -> str:
    """Where a fetch refspec's destination (one with no pattern) is stored, as git places it."""
    if dst.startswith("refs/"):
        return dst
    return ("refs/" if dst.startswith(("heads/", "tags/", "remotes/")) else "refs/heads/") + dst


def _any_case(pattern: str) -> str:
    """A ref pattern (`refs/…`) whose letters after `refs/` match in any case,
    as a case-insensitive file system stores loose refs."""
    return "refs/" + "".join(f"[{ch.lower()}{ch.upper()}]" if ch.isascii() and ch.isalpha() else ch for ch in pattern[5:])


def _known_refs(ours: list[str], remotes: list[str], fetch: dict[str, list[str]]) -> list[str]:
    """`git log`'s options naming the tracking refs that count as on the
    remote: those under `refs/remotes/<r>/` of each remote `r` fetching from
    `project.repo` (`ours`), as #390 counts them, less the names that a
    `prototype/*` branch's code can be stored under: `<r>/prototype/…` (git's
    default refspec's), what the `fetch` refspecs of ours store from a
    prototype branch (where a `*` may stand for part of that name, all they
    store), what any refspec of any remote stores from anything but a branch
    (a pull request's `refs/pull/…`, `refs/*`, a short name git may read as a
    tag) or, for a remote not ours, at all, and `<r>/HEAD`, which may point at
    one. A remote nested in one of ours by name (`origin/fork`) that isn't
    ours fetches from elsewhere: its refs are left out. Every name left out
    matches in any case. git splits a refspec at its last `:`."""
    ours = [r for r in ours if not _GLOB_CHARS.search(r) and "\\" not in r]
    out = [f"--exclude=refs/remotes/{o}/*" for o in remotes if o not in ours and o.startswith(tuple(r + "/" for r in ours)) and not _GLOB_CHARS.search(o)]
    left_out = [p for r in ours for p in (f"refs/remotes/{r}/HEAD", f"refs/remotes/{r}/prototype/*")]
    for r in remotes:
        for spec in fetch.get(r) or []:
            src, colon, dst = spec.removeprefix("+").rpartition(":")
            if not colon or not dst or src.startswith("^"):
                continue  # stored under no ref, or a negative refspec, which stores nothing
            branchy = r in ours and src.startswith("refs/heads/")
            if "*" in src:
                if not dst.startswith("refs/") or "*" not in dst:
                    continue  # git stores no pattern's refs there
                before, _, after = dst.partition("*")
                prefix, _, rest = src.partition("*")
                if not branchy or (prefix.startswith(_PROTOTYPE) or (_PROTOTYPE.startswith(prefix) and rest)):
                    left_out.append(before + "*" + after)  # all it stores
                elif _PROTOTYPE.startswith(prefix):  # the `*` stands for `prototype/<name>`, and more
                    left_out.append(before + _PROTOTYPE[len(prefix) :] + "*" + after)
            elif not branchy or _prototype_branch(src):
                left_out.append(_fetch_dst(dst))
    out += [f"--exclude={_any_case(p)}" for p in dict.fromkeys(left_out) if p.startswith("refs/")]
    # `--exclude` holds until the next `--glob`: given again before each.
    return [x for r in ours for x in (*out, f"--glob=refs/remotes/{r}/*")]


# Where a prototype branch's commits are: its local branches, and its tracking refs by git's default refspec.
_PROTOTYPE_REFS = ("refs/heads/prototype", "refs/remotes/*/prototype/**")


# What git's ref names can't hold (`git check-ref-format`), a pattern's one `*` aside.
_NOT_IN_REFS = re.compile(r"[\x00-\x20\x7f:~^?\[\\]|\.\.|@\{|//|\.lock(/|$)|/\.|\.$|/$")


def _prototype_dst(ref: str) -> bool:
    """A refspec's destination that is a `prototype/*` branch, written in full and well formed."""
    return _prototype_branch(ref) and not _NOT_IN_REFS.search(ref) and ref.count("*") <= 1


def _to_prototypes(
    p: _Push, remote: str, cfg: dict[str, list[str]], d: str, glob: list[str], here: bool, code: _Code
) -> tuple[bool, str]:
    """(whether every ref a `git push` updates on its remote is a
    `prototype/*` branch, else why it isn't counted as one), read as git maps
    it, run on a `prototype/*` branch: a refspec's destination, written
    `refs/heads/prototype/<name>`; without one, the ref the source names
    (`HEAD`, a branch, a symbolic ref followed), unless the remote's `push`
    refspecs or `push.default = upstream` could map it elsewhere; with none,
    the remote's `push` refspecs, or `HEAD` where `push.default` sends a bare
    push to its own name (`simple`, `current`). Never with `--follow-tags`
    (or `push.followTags`), `--tags`, `--all`, `--mirror`, or a refspec the
    shell may expand."""
    if p.branches or p.mirror or p.tags or p.delete:
        return False, "it pushes more than named branches"
    if not code.on_prototype(d, glob):
        return False, "it isn't run on a `prototype/*` branch"
    if p.follow_tags or (p.follow_tags is None and (cfg.get("push.followtags") or ["false"])[-1].lower() not in _FALSE):
        return False, "it sends the tags on its commits too (`--follow-tags`, `push.followTags`)"
    # git reads `push.recurseSubmodules` and `submodule.recurse` (true: on-demand) in config order, the last one set
    # winning, and an option over both: counted only when every value it could read means no recursion.
    values = [p.recurse.lower() or "no"] if p.recurse is not None else (cfg.get("push.recursesubmodules") or []) + (cfg.get("submodule.recurse") or [])
    if any(v.lower() not in ("no", "check", *_FALSE) for v in values):
        return False, "git may push submodules too (`--recurse-submodules`, `push.recurseSubmodules`, `submodule.recurse`): push with `--no-recurse-submodules`"
    pushes = cfg.get(f"remote.{remote}.push") if remote else None
    default = (cfg.get("push.default") or [""])[-1].lower()
    mapped = "the remote's `push` refspecs or `push.default = upstream` could send it elsewhere"
    specs, shell = p.refspecs, True
    if not specs:
        mirror = cfg.get(f"remote.{remote}.mirror") if remote else None
        if mirror and mirror[-1].lower() not in _FALSE:
            return False, "its remote mirrors every ref"
        if pushes:
            specs, shell = pushes, False
        elif default in ("", "simple", "current"):
            specs = ["HEAD"]
        else:  # `upstream` sends it to the branch's upstream, `matching` every branch, `nothing` nothing
            return False, f"`push.default = {default}` decides where a bare push goes"
    for r in specs:
        if shell:
            if _CURRENT_BRANCH.search(r):
                if not here:
                    return False, "its branch is the shell's, while git runs elsewhere"
                r = _CURRENT_BRANCH.sub("HEAD", r)
            if r == "tag":
                return False, "it pushes a tag"
            if _shell_spelled(r, globs=True):
                return False, f"the shell may expand `{_brief(r)}`"
        src, colon, dst = r.removeprefix("+").rpartition(":")  # git splits a refspec at its last `:`
        if colon:
            if _prototype_dst(dst):
                continue
            for full in ("refs/heads/" + dst, "refs/" + dst):  # a short one git places by the source's kind, or on a ref the remote has
                if not dst.startswith("refs/") and _prototype_dst(full):
                    return False, f"its destination `{_brief(dst)}` isn't written in full: write it `{_brief(full)}`"
            return False, f"its destination `{_brief(dst)}` isn't a `prototype/*` branch"
        src = dst
        if pushes or default in ("upstream", "tracking"):
            return False, mapped  # git maps a source without a destination through them
        full, _ = _memo_read(d, glob, "rev-parse", "--symbolic-full-name", src, sep="\n") if src and not src.startswith("-") else (None, "")
        if not full or len(full) != 1 or not _prototype_branch(full[0]):
            return False, f"`{_brief(src)}` isn't a `prototype/*` branch here"  # a tag, a symbolic ref elsewhere, a name it can't read
    return True, ""


# ---------- the push rule (#390) ----------
#
# A push to `project.repo` is judged by what git would send: the commits its
# sources reach that are on no tracking ref of a remote fetching from
# `project.repo`, each read as a commit is: a merge by its own changes, as the
# commit rule reads one (#391), and a revert of a commit on the base let
# through (#392). The guard reads them as the repository is when
# the command starts, so another part of the command that may move a branch or
# HEAD, or change where pushes go, makes it a push it can't tell about.


@dataclass
class _Push:
    """What a `git push` (or `send-pack`, `http-push`) names, as git reads it."""

    repo: str | None = None  # the repository: a remote's name or a URL (send-pack's and http-push's always a URL)
    refspecs: list[str] = field(default_factory=list)
    branches: bool = False  # `--all`, `--branches`: every branch
    mirror: bool = False  # `--mirror`: every ref
    tags: bool = False  # `--tags` (`--follow-tags` sends no commit the push doesn't already)
    delete: bool = False  # `-d`, `--delete`: the refspecs name what it deletes
    follow_tags: bool | None = None  # `--follow-tags`, `--no-follow-tags`; None: `push.followTags` decides
    recurse: str | None = None  # `--recurse-submodules=<how>` (`no` for `--no-recurse-submodules`); None: the config decides
    dry: bool = False
    unread: str | None = None  # what the guard can't read among its arguments


def _push_args(args: list[str]) -> _Push:
    kind, rest = args[0], args[1:]
    p, pos, repo_opt, i = _Push(), [], None, 0
    while i < len(rest):
        a = rest[i]
        i += 1
        if a == "--":
            pos += rest[i:]
            break
        if a.startswith("--"):
            name, cands = _expand_long(a)
            if name is None:
                if cands:
                    p.unread = p.unread or f"the option `{_brief(a)}`, which git could read as any of {', '.join('`--' + c + '`' for c in cands)}"
                continue
            if name in ("all", "branches", "no-all", "no-branches"):
                p.branches = not name.startswith("no-")
            elif name in ("mirror", "no-mirror"):
                p.mirror = name == "mirror"
            elif name in ("tags", "no-tags"):
                p.tags = name == "tags"
            elif name in ("delete", "no-delete"):
                p.delete = name == "delete"
            elif name in ("follow-tags", "no-follow-tags"):
                p.follow_tags = name == "follow-tags"
            elif name in ("dry-run", "no-dry-run"):
                p.dry = name == "dry-run"
            elif name == "stdin":
                p.unread = p.unread or "the refs it reads from its stdin (`--stdin`)"
            elif name == "no-recurse-submodules":
                p.recurse = "no"
            elif _PUSH_LONG.get(name) and "=" not in a:
                value = rest[i] if i < len(rest) else ""
                i += 1
                if name == "repo":
                    repo_opt = value
                elif name == "recurse-submodules":
                    p.recurse = value
            elif name == "repo":
                repo_opt = a.partition("=")[2]
            elif name == "recurse-submodules":
                p.recurse = a.partition("=")[2]
            continue
        if a.startswith("-") and a != "-":
            cluster = a[1:]
            for k, ch in enumerate(cluster):
                if ch == "n":
                    p.dry = True
                elif ch == "d":
                    p.delete = True
                elif ch == "o":
                    i += 1 if k == len(cluster) - 1 else 0
                    break
            continue
        pos.append(a)
    p.repo = pos[0] if pos else repo_opt
    p.refspecs = pos[1:]
    if kind != "push" and not p.refspecs:
        p.branches = True  # send-pack and http-push without refs push every matching branch
    return p


def _project_url(url: str, repo: str | None) -> bool:
    """Whether a push URL is `project.repo`'s: each with a trailing `/`,
    then `.git`, then a `/` stripped, in any case, the URL is the repo or
    ends in it with a `/` or `:` just before it. Unlike `_repo_name`, which
    reads a GitHub URL's `OWNER/REPO` exactly, any host or path counts (a
    local clone's, a proxy's). Every URL is, when `repo` isn't known."""
    if not repo:
        return True

    def bare(x: str) -> str:
        x = x.strip().rstrip("/")
        if x.casefold().endswith(".git"):
            x = x[:-4].rstrip("/")
        return x.casefold()

    u, r = bare(url), bare(repo).lstrip("/")
    return bool(r) and (u == r or (u.endswith(r) and u[-len(r) - 1] in "/:"))


def _local_url(url: str) -> bool:
    """A repository on this machine (`.`, a path, `file://`), as opposed to a
    URL with a scheme or scp's `host:path`."""
    u = url.strip()
    if u.casefold().startswith("file:"):
        return True
    return "://" not in u and not re.match(r"[^/]+:", u)


# Git subcommands that change no ref, HEAD or config: another part of the command running one leaves a push's reading as it is.
_KEEPS_REFS = {
    "add", "annotate", "apply", "archive", "blame", "bundle", "cat-file", "check-attr", "check-ignore", "check-mailmap",
    "check-ref-format", "cherry", "clean", "count-objects", "describe", "diff", "diff-files", "diff-index", "diff-tree",
    "for-each-ref", "format-patch", "fsck", "gc", "grep", "hash-object", "help", "log", "ls-files", "ls-remote",
    "ls-tree", "maintenance", "merge-base", "merge-file", "merge-tree", "mv", "name-rev", "pack-refs", "prune",
    "range-diff", "reflog", "repack", "restore", "rev-list", "rev-parse", "rm", "shortlog", "show", "show-branch",
    "show-ref", "status", "stripspace", "var", "verify-commit", "verify-pack", "verify-tag", "version", "whatchanged",
}  # fmt: skip
_BRANCH_WRITES = re.compile(r"-[a-zA-Z]*[fdDmMcCu]|--(f|fo|for|forc|force|d|de|del|dele|delet|delete|m|mo|mov|move|c|co|cop|copy|set-upstream-to|u|un|uns|unset-upstream|edit-description)(=.*)?$", re.S)
# Settings that change where a push goes (`remote.`, `url.`, a branch's remote, includes) or what a bare one sends (`push.default`).
_PUSH_CONFIG_KEYS = re.compile(r"(?i)(remote|url|include|includeif)\.|push\.default(=|$)|branch\..*\.(remote|pushremote)(=|$)", re.S)
# Sections whose removal or renaming can drop such a setting.
_PUSH_CONFIG_SECTIONS = re.compile(r"(?i)(remote|url|include|includeif|push|branch)(\.|$)")
# `git config`'s options that write, and those of `git branch` that only list.
_CONFIG_WRITES = {"--add", "--replace-all", "--unset", "--unset-all", "--rename-section", "--remove-section", "-e", "--edit", "--append"}
_CONFIG_READS = {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "--list", "-l", "--get-color", "--get-colorbool"}
_BRANCH_LISTS = {"-l", "--list", "--contains", "--no-contains", "--merged", "--no-merged", "--points-at"}
# Keys that can send a push given what looks like a URL elsewhere: a rewrite (`url.<base>.pushInsteadOf`), a remote
# of that name (git looks a word up as a remote first, and a remote's name may hold a `:`), or config brought in.
_URL_CONFIG_KEYS = re.compile(r"(?i)(url|remote|include|includeif)(\.|$)")
# `git config`'s long options (git takes a unique prefix of each), and those that take the next word as their value.
_CONFIG_LONGS = [
    "global", "system", "local", "worktree", "file", "blob", "get", "get-all", "get-regexp", "get-urlmatch", "replace-all",
    "add", "unset", "unset-all", "rename-section", "remove-section", "list", "fixed-value", "type", "bool", "int",
    "bool-or-int", "path", "expiry-date", "no-type", "null", "name-only", "includes", "no-includes", "show-origin",
    "show-scope", "get-color", "get-colorbool", "edit", "default", "comment", "value", "all", "regexp", "url", "append",
    "bool-or-str", "show-names", "no-show-names", "no-value", "no-comment", "no-all", "no-regexp", "no-fixed-value",
]  # fmt: skip
_CONFIG_VALUES = {"-f", "--file", "--blob", "--type", "--default", "--comment", "--value", "-t", "--url"}
# Variables that set config as `-c` does, and those that change which repository, refs or config files git reads.
_PUSH_ENV_CONFIG = re.compile(r"GIT_CONFIG_(PARAMETERS|KEY_\w*)")  # read by the settings they name
# (`GIT_CONFIG_PARAMETERS` and `GIT_CONFIG_KEY_<n>` are judged by the keys they set, as `-c` is.)
_PUSH_ENV = re.compile(r"GIT_(DIR|WORK_TREE|COMMON_DIR|INDEX_FILE|OBJECT_DIRECTORY|ALTERNATE_OBJECT_DIRECTORIES|NAMESPACE|CONFIG|CONFIG_GLOBAL|CONFIG_SYSTEM|CONFIG_NOSYSTEM)|HOME|XDG_CONFIG_HOME")
_PUSH_ENV_PROGRAMS = re.compile(r"GIT_EXEC_PATH|GIT_SSH\w*|GIT_PROXY_COMMAND")  # programs git runs for a push (#393)
_PUSH_ENV_REPO = re.compile(r"GIT_(DIR|WORK_TREE|COMMON_DIR|OBJECT_DIRECTORY|ALTERNATE_OBJECT_DIRECTORIES|NAMESPACE)")  # which repository or refs
_GH_MOVES = (["pr", "checkout"], ["pr", "co"], ["repo", "sync"])  # gh commands that move a branch or HEAD


# `git branch`'s and `git tag`'s options that take the next word as their value (not a ref's name).
# (`--column` takes a value only after `=`.)
_REF_LIST_VALUES = {"--format", "--sort", "--contains", "--no-contains", "--merged", "--no-merged", "--points-at", "-m", "-F", "--message", "--file", "-u", "--local-user", "--cleanup", "--set-upstream-to"}


def _ref_args(rest: list[str]) -> tuple[list[str], list[str]]:
    """(`git branch`'s or `git tag`'s options, its other words), options' values in neither."""
    opts, words, i = [], [], 0
    while i < len(rest):
        a = rest[i]
        i += 1
        if a == "--":
            words += rest[i:]
            break
        if a.startswith("-"):
            opts.append(a)
            i += 1 if a in _REF_LIST_VALUES else 0
            continue
        words.append(a)
    return opts, words


def _config_changes(rest: list[str]) -> str | None:
    """What a `git config` command may change that a push reads: "url" (a
    setting that may rewrite a URL a push is given, or one the guard can't
    read), "config" (another push setting), else None."""
    opts, words = _config_args(rest)
    if opts is None:
        return "url"  # an option it can't read: anything
    sub = words[0] if words and words[0] in ("get", "list", "set", "unset", "edit", "rename-section", "remove-section") else None
    if _CONFIG_READS & opts or sub in ("get", "list"):
        return None
    keys = words[1:] if sub else words
    if not (_CONFIG_WRITES & opts) and sub is None and len(keys) == 1:
        return None  # a key alone: a read, whatever scope or format options it takes
    if {"-e", "--edit"} & opts or sub == "edit" or not keys:
        return "url"
    if {"--rename-section", "--remove-section"} & opts or sub in ("rename-section", "remove-section"):
        names = keys[:2] if "--rename-section" in opts or sub == "rename-section" else keys[:1]
        hit = [k for k in names if _PUSH_CONFIG_SECTIONS.match(k) or _key_spelled(k)]
    else:
        hit = [k for k in keys[:1] if _PUSH_CONFIG_KEYS.match(k) or _key_spelled(k)]
    if not hit:
        return None  # another setting (`user.email`): no push reads it
    return "url" if any(_URL_CONFIG_KEYS.match(k) or _key_spelled(k) for k in hit) else "config"


def _other_git(words: list[str]) -> list[str] | None:
    """The subcommand and arguments of a git command in another part of the
    command: found behind wrappers, or git's dashed `git-<sub>` command word."""
    g = _commit_git(words)
    if g:
        return g[1] or None
    name = posixpath.basename(words[0]) if words else ""
    return [name[4:], *words[1:]] if name.startswith("git-") and len(name) > 4 else None


def _config_args(rest: list[str]) -> tuple[set[str] | None, list[str]]:
    """(`git config`'s options, each long one spelled out as git reads a
    unique prefix, or None when one is ambiguous or unknown; its other
    words, options' values left out)."""
    opts: set[str] = set()
    words, i, ok = [], 0, True
    while i < len(rest):
        a = rest[i]
        i += 1
        if a == "--":
            words += rest[i:]
            break
        if a.startswith("--"):
            name, eq, _ = a[2:].partition("=")
            cands = [o for o in _CONFIG_LONGS if o == name] or [o for o in _CONFIG_LONGS if o.startswith(name)] if name else []
            if len(cands) != 1:
                ok = False
                continue
            o = "--" + cands[0]
            opts.add(o)
            i += 1 if o in _CONFIG_VALUES and not eq else 0
            continue
        if a.startswith("-") and len(a) > 1:
            for k, ch in enumerate(a[1:], 1):
                opts.add("-" + ch)
                if "-" + ch in _CONFIG_VALUES:
                    i += 1 if k == len(a) - 1 else 0
                    break
            continue
        words.append(a)
    return (opts if ok else None), words


def _git_changes(args: list[str]) -> str | None:
    """What `git <args>`, run by another part of the command, may change that
    a push reads: "config" (where pushes go, or what a bare push sends),
    "refs" (a branch, a tag or HEAD), "push" (refs, when its repository is
    on this machine: `_other_changes` reads where it goes), else None."""
    if not args:
        return None
    sub, rest = args[0], args[1:]
    opts = [a for a in rest if a.startswith("-")]
    words = [a for a in rest if not a.startswith("-")]
    if sub in _KEEPS_REFS:
        return None
    if sub in _PUSH_CMDS:
        repo = _push_args(args).repo
        return "push" if repo is None or _local_url(repo) else None  # `_pushes_into` reads where it goes
    if sub == "fetch":
        # Moves a local ref when an argument after its repository names a destination (`a:b`, `--refmap=…:…`).
        repo = next((w for w in rest if not w.startswith("-")), None)
        return "refs" if any(":" in a for a in rest if a is not repo) else None
    if sub == "config":
        return _config_changes(rest)
    if sub == "remote":
        # git refuses a remote's name with a `:`, so a remote it adds or renames never looks like a URL.
        return None if not words or words[0] in ("show", "get-url", "update", "prune", "set-head") else "config"
    if sub in ("branch", "tag"):
        opts, words = _ref_args(rest)
    if sub == "branch":
        if set(o.split("=", 1)[0] for o in opts) & _BRANCH_LISTS and not any(_BRANCH_WRITES.match(o) for o in opts):
            return None  # it lists branches
        return "refs" if words or any(_BRANCH_WRITES.match(o) for o in opts) else None
    if sub == "tag":
        listing = {"-l", "--list", "-n", "--contains", "--no-contains", "--merged", "--no-merged", "--points-at"}
        return "refs" if words and not (set(o.split("=", 1)[0] for o in opts) & listing) else None
    if sub == "symbolic-ref":
        return "refs" if len(words) > 1 or any(o in ("-d", "--delete") for o in opts) else None
    if sub in ("stash", "worktree", "notes"):
        return None if words[:1] in (["list"], ["show"]) else "refs"
    return "refs"


# While the push rule runs: its git reads by their arguments, so many pushes in one command read each thing once.
_PUSH_MEMO: dict | None = None
_PUSH_RULE_SECONDS = 15  # the most the push rule spends on one command's pushes


def _memo_read(d: str, glob: list[str], *args: str, **kw) -> tuple[list[str] | None, str]:
    if _PUSH_MEMO is None:
        return _git_read(d, glob, *args, **kw)
    key = (d, tuple(glob), args, tuple(sorted((k, tuple(sorted(v.items())) if isinstance(v, dict) else v) for k, v in kw.items())))
    if key not in _PUSH_MEMO:
        _PUSH_MEMO[key] = _git_read(d, glob, *args, **kw)
    return _PUSH_MEMO[key]


def _git_common(path: str, glob: list[str]) -> str | None:
    """The real path of the git directory `path` (with the command's
    `--git-dir`-style options) belongs to, else None."""
    got, _ = _memo_read(path, glob, "rev-parse", "--git-common-dir", sep="\n") if os.path.isdir(path) else (None, "")
    return os.path.realpath(os.path.join(path, got[0])) if got else None


def _git_dir_abs(path: str, glob: list[str]) -> str | None:
    """The git directory of the worktree `path` is in (each worktree has its own HEAD), else None."""
    got, _ = _memo_read(path, glob, "rev-parse", "--absolute-git-dir", sep="\n")
    return os.path.realpath(got[0]) if got else None


def _default_remote(d: str, glob: list[str]) -> str | None:
    """The remote a push with none named goes to, as git picks it; None
    when the guard can't read it."""
    cfg, _ = _push_config(d, glob)
    head, _ = _memo_read(d, glob, "symbolic-ref", "-q", "HEAD", sep="\n", ok=(0, 1))
    if cfg is None or head is None:
        return None
    branch = head[0].removeprefix("refs/heads/") if head else ""

    def last(key: str) -> str:
        return (cfg.get(key) or [""])[-1]

    return (branch and last(f"branch.{branch}.pushremote")) or last("remote.pushdefault") or (branch and last(f"branch.{branch}.remote")) or "origin"


def _pushes_into(s: Seg, args: list[str], root: Path, common: str | None) -> bool:
    """Whether another part's push may move a ref of the repository whose git
    directory is `common`: its repository (a remote's push URLs read, the
    remote git picks when none is named) is on this machine and is that one,
    or one the guard can't place."""
    g = _commit_git(s.words)
    glob = _passed_globals(g[0]) if g else []
    d = _git_dir_of(root, s.cwd, g[2] if g else None)
    if not d or not os.path.isdir(d):
        return True
    repo = _push_args(args).repo
    if repo is None:
        repo = _default_remote(d, glob)
        if repo is None:
            return True
    names, _ = _memo_read(d, glob, "remote", sep="\n")
    if names is None:
        return True
    urls = [repo]
    if repo in names:
        got, _ = _memo_read(d, glob, "remote", "get-url", "--push", "--all", repo, sep="\n")
        if got is None:
            return True
        urls = got
    for u in urls:
        if not _local_url(u):
            continue  # elsewhere: only its tracking refs move
        path = re.sub(r"(?i)^file://", "", u.strip())
        try:
            target = _git_common(os.path.join(d, os.path.expanduser(path)), [])
        except (ValueError, UnicodeError, OSError):  # a path it can't place (a NUL, a lone surrogate)
            return True
        if target is None or common is None or target == common:
            return True
    return False


def _sets_upstream(args: list[str]) -> bool:
    """`git push -u` (`--set-upstream`, or a prefix of it git takes)."""
    for a in args:
        if a == "--":
            return False
        if a.startswith("--"):
            if _expand_long(a)[0] == "set-upstream":
                return True
        elif a.startswith("-") and a[1:].isalnum() and "u" in a.partition("o")[0]:
            return True
    return False


def _global_config_write(s: Seg, root: Path) -> bool:
    """A part of the command whose shell write the guard places on the global git config."""
    try:
        return bool(_global_config_problem(s, _write_targets(s, root)))
    except Exception:  # a write it can't read: the commit and push rules' own reads still stand
        return False


class _Changers:
    """The parts of one command that may change what a push reads, each
    classified once: "config" (where pushes go), "refs" (a branch, a tag or
    HEAD), "push" (refs, when it pushes into the judged repository)."""

    def __init__(self, segs: list[Seg], root: Path):
        self.root = root
        self.parts: list[tuple[Seg, str, str, list[str] | None]] = []
        for s in segs:
            if not s.words:
                continue
            if posixpath.basename(s.words[0]) == "gh" and s.words[1:3] in _GH_MOVES:
                self.parts.append((s, "refs", "gh " + " ".join(s.words[1:3]), None))
                continue
            args = _other_git(s.words)
            what = _git_changes(args) if args else None
            label = "git " + " ".join(_brief(a) for a in args[:2]) if args else ""
            if what:
                self.parts.append((s, what, label, args))
            if args and args[0] == "push" and _sets_upstream(args[1:]):
                self.parts.append((s, "upstream", label, args))  # `-u` sets a branch's remote, which a push with none named reads
            if _global_config_write(s, root):
                self.parts.append((s, "url", posixpath.basename(s.words[0]), None))
        self.into: dict[tuple, bool] = {}

    def first(self, seg: Seg, kind: str, common: str | None = None) -> str | None:
        """`git <sub>` of the first other part that may change `kind`."""
        for s, what, label, args in self.parts:
            if s is seg:
                continue
            if what == "push" and kind == "refs":
                g = _commit_git(s.words)
                key = (s.cwd, g[2] if g else None, tuple(g[0]) if g else (), _push_args(args).repo, common)
                if key not in self.into:
                    self.into[key] = _pushes_into(s, args, self.root, common)
                what = "refs" if self.into[key] else ""
            if what == kind or (kind == "config" and what == "url"):
                return label
        return None


def _push_env(segs: list[Seg], seg: Seg, pattern: re.Pattern) -> str | None:
    """A variable matching `pattern` set for the push or anywhere in the
    command (exported, declared, or alone)."""
    names = list(_assigned(seg))
    for s in segs:
        if not s.words:
            names += [a.partition("=")[0].removesuffix("+") for a in s.assigns]
        elif s.words[0] in _DECLARES:
            names += [w.partition("=")[0].removesuffix("+") for w in s.words[1:] if not w.startswith("-")]
    return next((n for n in names if pattern.fullmatch(n)), None)


def _shell_spelled(word: str, globs: bool = False, assignment: bool = False) -> bool:
    """A word the shell may turn into others: a variable or a substitution,
    a leading tilde, a brace list or sequence; with `globs`, a glob (not in a
    config key or value, where `*` is ordinary: `http.<url>.*`, `Accept: */*`);
    in an `assignment`'s value, a tilde after `=` or `:` too."""
    if _SHELL_EXPANDS.search(word) or _brace_sequence(word) or len(_braces(word, 2)) > 1:
        return True
    return bool((globs and _GLOB_CHARS.search(word)) or (assignment and re.search(r"[=:]~", word)))


_CONFIG_VAR = re.compile(r"GIT_CONFIG_(PARAMETERS|COUNT|KEY_\w*|VALUE_\w*)")


def _key_spelled(key: str) -> bool:
    """A config key (`-c`'s, `git config`'s, a variable's) the shell may
    turn into another: one `_shell_spelled` reads so, or a glob in its
    section or name, where git allows none (a subsection's `*`, as in
    `http.<url>.*`, is git's own)."""
    k = key.partition("=")[0]
    return _shell_spelled(k) or bool(_GLOB_CHARS.search(k.partition(".")[0]) or _GLOB_CHARS.search(k.rpartition(".")[2]))


def _push_env_config(segs: list[Seg], seg: Seg, keys_re: re.Pattern) -> str | None:
    """A config variable (`GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_KEY_<n>`), set
    by a `NAME=value` the guard reads, for the push or anywhere in the
    command, that sets a key matching `keys_re`, one the shell spells, or a
    value it can't read. One added to (`+=`) or exported bare, or a count or
    value whose keys it doesn't set (inherited), counts whatever its keys."""
    pairs = [a.partition("=") for a in seg.assigns]
    for s in segs:
        if not s.words:
            pairs += [a.partition("=") for a in s.assigns]
        elif s.words[0] in _DECLARES:
            pairs += [w.partition("=") for w in s.words[1:] if not w.startswith("-")]
    pairs = [(n, eq, v) for n, eq, v in pairs if _CONFIG_VAR.fullmatch(n.removesuffix("+"))]
    keys_set = {n.removeprefix("GIT_CONFIG_KEY_") for n, eq, _ in pairs if n.startswith("GIT_CONFIG_KEY_") and eq}
    for n, eq, v in pairs:
        if n.endswith("+") or not eq:
            return n.removesuffix("+")
        if n.startswith("GIT_CONFIG_VALUE_") and n.removeprefix("GIT_CONFIG_VALUE_") not in keys_set:
            return n
        if n == "GIT_CONFIG_COUNT" and not (re.fullmatch(r"[0-9]{1,4}", v) and all(str(k) in keys_set for k in range(int(v)))):
            return n
    for name, _, value in pairs:
        name = name.removesuffix("+")
        if not _PUSH_ENV_CONFIG.fullmatch(name):
            continue
        # Only a key that may send a URL push elsewhere counts here: any other config variable is judged with the push's remote.
        if name == "GIT_CONFIG_PARAMETERS":
            if _shell_spelled(value, assignment=True):
                return name  # git reads it after the shell: anything can come in
            keys = _config_params_keys(value)
            if keys is None:
                return name  # not git's format: it can't be read
        else:
            keys = [value.strip("'\"")]
        if any(_key_spelled(k) or keys_re.match(k.strip()) for k in keys):
            return name
    return None


def _config_params_keys(value: str) -> list[str] | None:
    """The keys `GIT_CONFIG_PARAMETERS` sets, read in one pass as git reads
    it: items `'key'='value'` or the older `'key=value'`, quoted as git
    quotes (a backslash inside quotes is itself; `'\\''` and `'\\!'`
    between quoted parts); None when it can't read it as git would."""
    n, i, keys = len(value), 0, []

    def word() -> str | None:
        nonlocal i
        if i >= n or value[i] != "'":
            return None
        out = []
        i += 1
        while True:
            j = value.find("'", i)
            if j < 0:
                return None
            out.append(value[i:j])
            i = j + 1
            if value[i : i + 1] == "\\" and value[i + 1 : i + 2] in ("'", "!") and value[i + 2 : i + 3] == "'":
                out.append(value[i + 1])
                i += 3
                continue
            return "".join(out)

    while True:
        while i < n and value[i].isspace():
            i += 1
        if i >= n:
            return keys
        w = word()
        if w is None:
            return None
        if value[i : i + 1] == "=":
            i += 1
            if i < n and not value[i].isspace() and word() is None:
                return None  # (`'key'=` alone is git's own spelling of a key set to true)
            keys.append(w)
        else:
            keys.append(w.partition("=")[0])
        if i < n and not value[i].isspace():
            return None


def _push_config(d: str, glob: list[str]) -> tuple[dict[str, list[str]] | None, str]:
    """The settings that say where a push goes and what it sends, by key
    (section and name in lower case, a remote's name as written), else
    (None, what failed)."""
    pattern = r"^(push\.default|remote\.pushdefault|remote\..*\.(url|pushurl|push|mirror|fetch)|push\.followtags|push\.recursesubmodules|submodule\.recurse|branch\..*\.(remote|pushremote))$"
    got, err = _memo_read(d, glob, "config", "-z", "--get-regexp", pattern, ok=(0, 1))
    if got is None:
        return None, err
    out: dict[str, list[str]] = {}
    for item in got:
        key, _, value = item.partition("\n")
        out.setdefault(key, []).append(value)
    return out, ""


def _refspec_sources(specs: list[str], shell: bool, here: bool = True) -> tuple[list[str], set[str], str | None]:
    """(the revisions, the `git log` options naming every ref a pattern could
    match, what the guard can't read) for what refspecs send. `shell`: they
    are a command's words, which the shell may expand; `here`: git runs in
    the shell's own directory, where `$(git branch --show-current)` is HEAD."""
    srcs, pseudo, k = [], set(), 0
    while k < len(specs):
        r = specs[k]
        k += 1
        if shell and _CURRENT_BRANCH.search(r):
            if not here:
                return [], set(), f"the ref `{_brief(r)}`, the shell's branch, while git runs in another directory"
            r = _CURRENT_BRANCH.sub("HEAD", r)
        if r == "tag" and k < len(specs):
            r, k = "refs/tags/" + specs[k], k + 1
        r = r.removeprefix("+")
        if r.startswith("^"):
            return [], set(), f"the negative refspec `{_brief(r)}`, as it doesn't read what that leaves out"
        if r == ":":
            pseudo |= {"--branches", "--tags"}  # every matching branch
            continue
        src = r.rpartition(":")[0] if ":" in r else r  # git splits a refspec at its last `:`
        if not src:
            continue  # a deletion
        words = _braces(src, _BRACE_LIMIT + 1) if shell else [src]
        if shell and (_SHELL_EXPANDS.search(src) or len(words) > _BRACE_LIMIT or any(_brace_sequence(w) for w in words)):
            return [], set(), f"the ref `{_brief(src)}`, which the shell expands"
        for w in words:
            if "*" not in w:
                srcs.append("HEAD" if w == "@" else w)
            elif w.startswith("refs/"):
                pseudo.add(f"--glob={w}")  # every ref the pattern could match
            else:
                return [], set(), f"the pattern `{_brief(w)}`, which isn't a full ref"
    return srcs, pseudo, None


_COMMIT_HEADER = re.compile(r"\x01\x02([0-9a-f]{4,64})\x03([0-9a-f]{40,64})")


def _sent_code(
    d: str, glob: list[str], args: list[str], code: _Code, patch: bool = False, env: dict[str, str] | None = None,
    passes: Callable[[str], bool] | None = None,
) -> tuple[tuple[str, _Hit, str] | None, str]:
    """((the commit, the code path, the commit's full name) of the first code path `git log <args>`
    lists, else None; what failed). Read as git writes it, so a long history
    stops at its first code path, within the time a git read has. With
    `patch`, `git log` writes patches (merges' own changes, #391), whose paths
    are their file headers' rather than `--name-only`'s. `env` adds to git's
    environment. `passes(full name)` says whether a commit carrying a code path
    is let through all the same (a revert, #392); the time it takes adds to
    the read's."""
    # Imported here, not at the top: only a push to `project.repo`, or a commit finishing a merge, needs them, and the hook starts on every tool.
    import queue
    import tempfile
    import threading
    import time

    shown, deadline = "`git log`", time.monotonic() + _GIT_READ_SECONDS
    try:
        err_file = tempfile.TemporaryFile()  # git's messages, read only at the end, so they never fill a pipe
    except OSError as e:
        return None, f"{shown} couldn't run in `{d}`: no temporary file ({e.__class__.__name__})"
    try:
        proc = subprocess.Popen(
            [*_GIT_READ, *glob, *args], cwd=d, stdout=subprocess.PIPE, stderr=err_file, stdin=subprocess.DEVNULL,
            env={**os.environ, **(env or {}), "GIT_NO_LAZY_FETCH": "1"},  # a partial clone fetches nothing for the guard
        )  # fmt: skip
    except (OSError, ValueError) as e:
        err_file.close()
        return None, f"{shown} couldn't run in `{d}` ({e})"
    chunks: "queue.Queue[bytes]" = queue.Queue()

    def pump() -> None:
        try:
            while True:
                b = proc.stdout.read1(1 << 16)
                chunks.put(b)
                if not b:
                    return
        except (OSError, ValueError):
            chunks.put(b"")

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    pending, sha, full, sep, skipping, passed, path_next = bytearray(), "", "", b"\n" if patch else b"\0", False, False, False
    try:
        while True:
            try:
                b = chunks.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                return None, f"{shown} took too long in `{d}`"
            if not b:
                break
            items, start = [], 0
            while (end := b.find(sep, start)) != -1:  # only the new chunk is searched: a long line stays linear
                if not skipping:
                    items.append(bytes(pending) + b[start:end])
                skipping = False
                pending.clear()
                start = end + 1
            if not skipping:
                pending += b[start:]
                if patch and len(pending) > _PATCH_LINE_CAP and not pending.startswith((b"diff --", b"\x01\x02")):
                    pending.clear()  # a patch's content line: never a file header, so not kept
                    skipping = True
            for raw in items:
                if path_next:  # a path, after its `:<modes> …` item: never a header, however it is spelled
                    path_next, item = False, raw.decode("utf-8", errors="replace")
                else:
                    item = raw.decode("utf-8", errors="replace").removeprefix("\n")
                    if not patch and item.startswith(":"):
                        path_next = True
                        continue
                    m = _COMMIT_HEADER.fullmatch(item)
                    if m:
                        sha, full, passed = m.group(1), m.group(2), False
                        continue
                    if patch:
                        item = _patch_path(item) or ""
                if passed:
                    continue  # the rest of a commit let through
                hit = _listed_code(item, code) if item else None
                if hit:
                    if passes is not None:
                        took = time.monotonic()
                        passed = passes(full)
                        deadline += time.monotonic() - took
                        if passed:
                            continue
                    return (sha, _Hit(item, hit), full), ""
        try:
            rc = proc.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            return None, f"{shown} took too long in `{d}`"
        if rc != 0:
            err_file.seek(0)
            err = err_file.read(4096).decode("utf-8", errors="replace").strip().splitlines()
            return None, f"{shown} failed in `{d}`" + (f" ({_brief(err[0])})" if err else "")
        return None, ""
    finally:
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        reader.join(timeout=1)
        if not reader.is_alive():  # else a process git started still holds the pipe: the daemon thread keeps it
            proc.stdout.close()
        err_file.close()


def _push_code(segs: list[Seg], code: _Code, root: Path, command: str) -> tuple[str | None, str | None]:
    """(why a push in the command sends a code path to `project.repo`, why
    the guard can't tell what one sends), each None when it doesn't apply."""
    global _PUSH_MEMO
    _PUSH_MEMO = {}
    try:
        return _judge_pushes(segs, code, root, command)
    finally:
        _PUSH_MEMO = None


def _judge_pushes(segs: list[Seg], code: _Code, root: Path, command: str) -> tuple[str | None, str | None]:
    import time  # here, as `_sent_code`'s: only a command that pushes needs it

    unsure, note, started = None, None, time.monotonic()
    changers: _Changers | None = None
    reads_only: tuple[list[Seg], str | None] | None = None  # `_busy_parts`, read once (#393)
    dot_git: str | None = None  # the `.git` the command names, read once
    for seg in segs:
        g = _commit_git(seg.words)
        if not g or not g[1] or g[1][0] not in _PUSH_CMDS:
            continue
        if time.monotonic() - started > _PUSH_RULE_SECONDS:
            unsure = unsure or "the guard can't tell what the command's pushes would send: there are too many to read in time"
            break
        if changers is None:
            changers = code.changers or _Changers(segs, root)
        glob, args, cdir = g
        kind = args[0]
        p = _push_args(args)
        if p.dry:
            continue
        cant = f"the guard can't tell what `git {kind}` would send"
        named = p.repo
        if named is not None and _shell_spelled(named, globs=True):
            unsure = unsure or f"{cant}: its repository `{_brief(named)}` is one the shell expands"
            continue
        # A setting that may rewrite a URL (`url.<base>.pushInsteadOf`) can send any push anywhere, `project.repo` among them.
        # `-c key=value` and `--config-env key=VAR`, each as its `key=…`.
        cs = [glob[j + 1] for j, o in enumerate(glob[:-1]) if o in ("-c", "--config-env")]
        cs += [o.partition("=")[2] for o in glob if o.startswith("--config-env=")]
        rewrites = [k for k in cs if _URL_CONFIG_KEYS.match(k) or _key_spelled(k)]
        env = _push_env_config(segs, seg, _URL_CONFIG_KEYS)
        other = changers.first(seg, "url")
        if rewrites or env or other:
            what = f"`{env}`" if env else f"`{_brief(rewrites[0].partition('=')[0])}`" if rewrites else ""
            how = f"it sets {what}" if what else f"another part of the command runs `{other}`"
            unsure = unsure or f"{cant}: {how}, which can change where it goes"
            continue
        # A remote's name rarely holds a `:` and never starts a path (`/`, `.`).
        url_given = named is not None and (kind != "push" or ":" in named or named.startswith(("/", ".")))
        elsewhere = url_given and not _project_url(named, code.repo)
        d = _git_dir_of(root, seg.cwd, cdir)
        if not d or "$" in d or "`" in d or not os.path.isdir(d):
            if elsewhere:
                continue  # another repository, by URL: as today
            if not d or "$" in d or "`" in d:
                unsure = unsure or f"{cant}: it runs in a directory the guard can't follow"
            else:
                unsure = unsure or f"{cant}: it runs in `{_brief(d)}`, which " + ("isn't a directory" if os.path.exists(d) else "doesn't exist yet")
            continue
        d = os.path.realpath(d)
        pglob = _passed_globals(glob)
        cfg, err = _push_config(d, pglob)
        listed, err2 = _memo_read(d, pglob, "remote", "-v", sep="\n") if cfg is not None else (None, err)
        if cfg is None or listed is None:
            if elsewhere:
                continue
            unsure = unsure or f"{cant}: {err or err2}"
            continue
        fetch_urls: dict[str, str] = {}  # each remote's URL as git fetches from it (`insteadOf` applied)
        for line in listed:
            name, _, rest = line.partition("\t")
            if rest.endswith(" (fetch)"):
                fetch_urls.setdefault(name, rest[: -len(" (fetch)")])
        remotes = {line.partition("\t")[0] for line in listed}
        remotes |= {k[len("remote.") :].rpartition(".")[0] for k in cfg if k.startswith("remote.") and k.count(".") >= 2}

        def last(key: str) -> str:
            return (cfg.get(key) or [""])[-1]

        if dot_git is None:
            dot_git = _names_dot_git(command, segs) or ""
        is_remote = kind == "push" and named in remotes  # git looks a word up as a remote first
        if elsewhere and not is_remote:
            if dot_git:  # a `.git` written can rewrite the URL (`pushInsteadOf` in its config)
                unsure = unsure or f"{cant}: the command names `{dot_git}`, which can change where it goes"
            continue  # else another repository, by URL: as today
        # A push by a remote's name, or with none named, goes where the config of the repository git reads says:
        # what changes that config, or which repository git reads, makes it one the guard can't tell about.
        # A push given `project.repo`'s URL (not a remote's name) and its refs goes there and sends those whatever the
        # config says: only which repository git reads counts. Without refs, `push.default` says what it sends.
        fixed = url_given and not is_remote and bool(p.refspecs or p.branches or p.mirror or p.tags)
        keys = [k for k in cs if _PUSH_CONFIG_KEYS.match(k)] if not fixed else []
        env = _push_env(segs, seg, _PUSH_ENV if not fixed else _PUSH_ENV_REPO) or (None if fixed else _push_env_config(segs, seg, _PUSH_CONFIG_KEYS))
        other = changers.first(seg, "config") if not fixed else None
        try:
            made = _made_by(segs, seg, d)
        except (ValueError, UnicodeError, OSError):  # a path it can't place: something may be made there
            made = "earlier"
        if keys or env or other or made:
            if keys or env:
                how = f"it sets `-c {_brief(keys[0])}`" if keys else f"the command sets `{env}`"
            elif other:
                how = f"another part of the command runs `{other}`"
            else:
                how = f"it runs in `{_brief(d)}`, where another part of the command makes a repository or worktree"
            unsure = unsure or f"{cant}: {how}, which can change where it goes or what it sends"
            continue
        if named is None and kind == "push":
            moves = changers.first(seg, "refs", _git_common(d, pglob)) or changers.first(seg, "upstream")
            if moves:  # git picks a bare push's remote by the branch checked out when it runs
                unsure = unsure or f"{cant}: another part of the command runs `{moves}`, which can change where it goes and what it sends"
                continue
            named = _default_remote(d, pglob)
            if named is None:
                unsure = unsure or f"{cant}: it couldn't read which remote git picks"
                continue
        is_remote = kind == "push" and named in remotes
        if is_remote:
            urls, err = _memo_read(d, pglob, "remote", "get-url", "--push", "--all", named, sep="\n")
            if urls is None:
                unsure = unsure or f"{cant}: it couldn't read the URL of the remote `{_brief(named)}`: {err}"
                continue
        else:
            common = _git_common(d, pglob)
            named = named or ""  # send-pack and http-push without a repository fail
            legacy = common and named not in ("", ".", "..") and "/" not in named and kind == "push"
            if legacy and any(os.path.isfile(os.path.join(common, sub, named)) for sub in ("remotes", "branches")):
                unsure = unsure or f"{cant}: its remote `{_brief(named)}` is defined in a file under `.git/remotes` or `.git/branches`, which the guard doesn't read"
                continue
            urls = [named]
        if not any(_project_url(u, code.repo) for u in urls):
            if dot_git:  # a `.git` written can change the remote's URL
                unsure = unsure or f"{cant}: the command names `{dot_git}`, which can change where it goes"
            continue  # else another repository: as today
        to = f"`{code.repo}`" if code.repo else f"`{_brief(named)}`"
        cant = f"the guard can't tell what `git {kind}` would send to {to}"
        common = _git_common(d, pglob)
        moves = changers.first(seg, "refs", common)
        if moves:
            unsure = unsure or f"{cant}: another part of the command runs `{moves}`, which can change what it sends"
            continue
        if seg.fed:
            unsure = unsure or f"{cant}: `xargs` gives it its refs"
            continue
        if p.unread:
            unsure = unsure or f"{cant}: it couldn't read {p.unread}"
            continue
        # `$(git branch --show-current)` is the shell's branch: HEAD where git runs in the same repository.
        here = seg.cwd is not None and os.path.isdir(seg.cwd) and _git_dir_abs(seg.cwd, []) == _git_dir_abs(d, pglob)
        # A planning session's push to `prototype/*` branches only (#393), with no setting of its own and nothing
        # else in the command but reads and other pushes, which could change where git maps it or what it sends.
        proto_why = ""  # why a planning session's push named or run on a prototype branch isn't let through as one
        if code.planning():
            if reads_only is None:
                reads_only = _busy_parts(segs, command)
            own = _push_own_part(segs, seg, glob, dot_git)
            if own:
                why = f"it runs with {own[0]}, which could change where git sends it"
            elif reads_only[1]:
                why = reads_only[1]
            elif any(s is not seg for s in reads_only[0]):
                why = "another part of the command does more than read: run the push in a command of its own"
            else:
                ok, why = _to_prototypes(p, named if named in remotes else "", cfg, d, pglob, here, code)
                if ok:
                    continue
            if code.on_prototype(d, pglob) or "prototype/" in " ".join(p.refspecs):
                proto_why = why
        srcs, pseudo, bad = _refspec_sources([] if p.delete else p.refspecs, True, here)
        if p.branches:
            pseudo.add("--branches")
        if p.mirror:
            pseudo.add("--all")
        if p.tags:
            pseudo.add("--tags")
        if kind == "push" and not p.refspecs and not (p.branches or p.mirror or p.tags):
            r = named if named in remotes else ""
            mirror = cfg.get(f"remote.{r}.mirror") if r else None
            if mirror and mirror[-1].lower() not in _FALSE:
                pseudo.add("--all")  # its settings mirror every ref
            elif r and cfg.get(f"remote.{r}.push"):
                more, extra, bad = _refspec_sources(cfg[f"remote.{r}.push"], False)
                srcs, pseudo = srcs + more, pseudo | extra
            elif last("push.default").lower() == "matching":
                pseudo.add("--branches")
            else:
                srcs.append("HEAD")
        if bad:
            unsure = unsure or f"{cant}: it couldn't read {bad}"
            continue
        if not srcs and not pseudo:
            continue  # it sends nothing
        if note is None:
            note = dot_git and f"{cant}: the command names `{dot_git}`, which can change what git reads"
        # On the remote already: what the tracking refs that the fetch refspecs of the remotes fetching from `project.repo`
        # fill from a branch hold, but a `prototype/*` branch's (#393), so its code reaches no other branch unjudged.
        ours = [r for r, url in sorted(fetch_urls.items()) if _project_url(url, code.repo)]
        known = _known_refs(ours, sorted(remotes), {r: cfg.get(f"remote.{r}.fetch") or [] for r in sorted(remotes)})
        # Each commit but a merge by the files it changes, a merge of more parents, then of two, by its own changes (#391).
        memo = _PUSH_MEMO if _PUSH_MEMO is not None else {}
        driver, err = _merge_driver(d, pglob)
        found, a_merge = None, False
        unread: list[str] = []  # reverts it couldn't read, passed over so a code commit beyond them still counts

        def passes(commit: str, _d: str = d, _glob: list[str] = pglob, _unread: list[str] = unread) -> bool:
            v = _commit_revert(_d, _glob, commit, code)
            if v.kind == "unsure":
                _unread.append(f"commit {commit[:7]} exactly undoes " + (v.named[:7] if v.named else "the commit it names") + f": {v.why}")
            return v.kind in ("allowed", "unsure")

        sends = ["--not", *known, "--not", *sorted(pseudo), "--end-of-options", *srcs, "--"]
        # (what it reads, how: `git log`'s options, a patch, in a temporary object store of its own)
        reads = [("files", _FILES, False, False), ("octopus", _OCTOPUS, True, False)] + ([] if driver else [("remerge", _REMERGE, True, True)])
        for read, log_args, patch, scratch in reads:
            if err:
                break
            key = ("log", read, d, tuple(pglob), tuple(known), tuple(sorted(pseudo)), tuple(srcs))
            if key not in memo:  # (found, what failed, the reverts it couldn't read)
                if scratch:  # git merges each again in a temporary object store, the guard's own
                    with _scratch_store(d, pglob, index=False) as (store, e):
                        got = _sent_code(d, [*pglob, *_REMERGE_CONFIG], ["log", *log_args, *sends], code, patch, store) if store else (None, e)
                else:  # a revert of a commit on the base is let through (#392); only the files pass reads commits that aren't merges
                    got = _sent_code(d, pglob, ["log", *log_args, *sends], code, patch, passes=passes if read == "files" else None)
                memo[key] = (*got, tuple(unread))
            found, err, seen = memo[key]
            if read == "files":  # a read from the memo brings back the reverts it couldn't read
                unread[:] = seen
            a_merge = patch  # only merges are read as patches
            if found:
                break
        if driver and not found and not err:  # a merge of two parents it doesn't merge again
            merges, err = _memo_read(d, pglob, "rev-list", "--merges", "--max-parents=2", "-1", *sends, sep="\n")
            if merges:
                err = f"it sends merge commit {merges[0][:7]}, and {_DRIVER_RUNS.format(driver)}"
        if found:
            sha, hit, full = found
            if code.planning() and not proto_why:  # the code of a prototype branch, which doesn't count as on the remote
                held, _ = _memo_read(d, pglob, "for-each-ref", "--count=1", "--sort=-refname", "--format=%(refname)", f"--contains={full}", *_PROTOTYPE_REFS, sep="\n")
                if held and held[0].startswith("refs/remotes/"):
                    proto_why = f"commit {sha} is on `{held[0][13:]}`, a `prototype/*` branch's tracking ref, which doesn't count as on the remote"
                elif held:
                    proto_why = f"commit {sha} is on `{held[0][11:]}`, a `prototype/*` branch, and isn't on the remote yet"
            proto = f"a planning session's prototype code goes to `prototype/*` branches only, pushed from one, and {proto_why}; " if proto_why else ""
            instead = proto + code.instead
            if a_merge:
                return f"this push sends merge commit {sha}, which carries the code path {_shown(hit)} ({hit.pattern}), {_MERGE_OWN}, to {to}; {instead}", None
            v = _commit_revert(d, pglob, full, code)
            if v.kind in ("unmatched", "ungranted"):
                return _revert_refusal(f"this push sends commit {sha}, which", hit, v, code, f", to {to}"), None
            return f"this push sends commit {sha}, which carries the code path {_shown(hit)} ({hit.pattern}), to {to}; {instead}", None
        if not err and unread:
            err = f"it couldn't tell whether {unread[0]}"
        if not err:
            err = _not_commits(d, pglob, srcs, pseudo)
        if err:
            unsure = unsure or f"{cant}: {err}"
    return None, unsure or note or None


def _not_commits(d: str, glob: list[str], srcs: list[str], pseudo: set[str]) -> str:
    """What a push sends that isn't a commit (a tag on a tree or a blob),
    which `git log` passes over, so the guard can't read it; else ""."""
    for src in srcs:
        got, _ = _memo_read(d, glob, "cat-file", "-t", f"{src}^{{commit}}", sep="\n") if not src.startswith("-") else (None, "")
        if got is None:
            return f"`{_brief(src)}` names something that isn't a commit, which it can't read"
    patterns = ["refs/tags"] if "--tags" in pseudo else []
    # for-each-ref's `*` doesn't cross a `/`, a refspec's does: the pattern's literal folder instead.
    patterns += [re.split(r"[*?\[]", g.partition("=")[2], maxsplit=1)[0].rpartition("/")[0] or "refs" for g in pseudo if g.startswith("--glob=")]
    if "--all" in pseudo:
        patterns = ["refs"]
    if patterns:
        got, err = _memo_read(d, glob, "for-each-ref", "--format=%(objecttype) %(*objecttype)", *patterns, sep="\n")
        if got is None:
            return err
        if any(line.split()[-1] != "commit" for line in got if line.strip()):
            return "a tag it sends names something that isn't a commit, which it can't read"
    return ""


def _unsure_code(unsure: str, role: str, code: _Code) -> Decision:
    """The decision on a commit or push whose contents the guard can't read:
    the conductor, which nobody is there to ask, is refused; others are asked."""
    if role == "conductor":
        return Decision(
            "deny", f"{unsure}; {code.writes_none}, and commits or pushes nothing the guard can't read; fix what stops git reading it, then try again"
        )
    return Decision(
        "ask",
        f"{unsure}; {code.writes_none}: allow it only if it carries no code path, or only a revert that exactly undoes a commit "
        "on the base" + (", or only a prototype's code on or to `prototype/*` branches" if code.planning() else ""),
    )


_PS_WORDS = re.compile(r"[^\s;|&(){}<>,=\"'`]+")
_PS_PARAM = re.compile(r"^-\w+:(.+)$")  # `-Path:src/app.py`
_WINDOWS_ABS = re.compile(r"^[A-Za-z]:/")


def _powershell_code(inp: dict, code: _Code, root: Path, cwd: str | os.PathLike | None) -> _Hit | None:
    """A code path PowerShell's text names (`\\` read as `/`, any case)."""
    text = inp.get("command") if isinstance(inp.get("command"), str) else ""
    top = os.path.realpath(str(root)).replace("\\", "/").rstrip("/")
    start = _start_cwd(root, cwd)
    for w in _PS_WORDS.findall(text.replace("\\", "/")):
        m = _PS_PARAM.match(w)
        w = m.group(1) if m else w
        if w.startswith("-") or not ("/" in w or "." in w or _GLOB_CHARS.search(w) or os.path.lexists(os.path.join(start or top, w))):
            continue  # a parameter, or a bare word naming nothing there (`Get-Date`)
        if w.casefold().startswith(top.casefold() + "/"):
            w = top + w[len(top) :]
        elif _WINDOWS_ABS.match(w):
            continue  # another drive's path: never this project's
        # A glob is judged by what it matches there, never by its own text.
        names = [c for c in _candidates(w, start) if c != w] if _GLOB_CHARS.search(w) else [w]
        for c in names:
            a = _abspath(c, start)
            hit = _code_at(a, code, root) if a else None
            if hit:
                return hit
    return None


def _text_holds_sensitive(text: str, profile: Profile) -> bool:
    return any(re.search(pat, text) for pat in profile.sensitive_patterns)


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
    directory (the event's `cwd`, which is used when it isn't given). In an
    attended session, an `ask` becomes a `deny` where nobody is asked (the
    event's `permission_mode`, see `modes`). Under `code_writers = "ticket"`,
    a session that is a ticket session only by its branch or by a mistyped
    `WORKFLOW_ROLE` is decided as an attended one, and a session that doesn't
    write code is refused writing it (#340)."""
    role, code, label = _code_session(event, profile, role, root, role_from_env, current_branch)
    d = _decide(event, profile, role, root, current_branch, role_from_env, cwd, code)
    mode = event.get("permission_mode")
    if d.action == "ask" and role == "attended" and modes.never_asks(mode):
        d = Decision("deny", d.reason + "\n" + _nobody_asked(event, mode, d.sensitive, profile, root, cwd), d.sensitive)
    return replace(d, label=label) if label else d


def _nobody_asked(event: dict, mode, sensitive: bool, profile: Profile, root: Path, cwd: str | os.PathLike | None) -> str:
    """What a refusal adds to the ask's reason in a mode that never asks: the
    kit would have asked, the mode, how to be asked, and how to do it by hand.
    `sensitive`: the ask is about sensitive data. Input matching a sensitive
    pattern is never repeated, whichever check asked (an earlier ask in the
    command can stop the guard before it reads the post)."""
    lines = fallback.mode_lines(mode)  # the same lines as the can't-decide fallback's
    tool = event.get("tool_name") or ""
    inp = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    command = inp.get("command") if tool in fallback.COMMAND_TOOLS else None
    if sensitive:
        # Never repeat sensitive data, nor suggest posting it by hand.
        lines.append("Or remove the text that matches the project's sensitive-data pattern, and try again.")
    else:
        github = isinstance(tool, str) and tool.startswith("mcp__") and "github" in tool.lower()
        runs_command = isinstance(command, str) and command.strip()
        if runs_command and tool == "PowerShell":
            holds = _text_holds_sensitive(command, profile)  # the guard can't read what it reads
        elif runs_command:
            holds = _bash_holds_sensitive(command, profile, root, cwd if cwd is not None else event.get("cwd") or None)
        else:
            holds = _text_holds_sensitive("\n".join(_strings(inp)), profile)
        if holds:
            without = _WITHOUT_SENSITIVE
            if runs_command:
                lines.append(f"Or run it yourself in your own terminal, {without} (the command isn't repeated here, since it or what it posts holds that text).")
            elif github:
                lines.append(f"Or do it yourself on GitHub, {without}.")
            else:
                lines.append(f"Or make the change yourself, by hand, {without}.")
        elif runs_command:
            lines.append(f"Or run it yourself in your own terminal:{_hand_command(command)}")
        elif github:
            lines.append("Or do it yourself on GitHub.")
        else:
            lines.append("Or make the change yourself, by hand.")
    return "\n".join(lines)


def _decide(
    event: dict,
    profile: Profile,
    role: str,
    root: Path,
    current_branch: str | None,
    role_from_env: bool = True,
    cwd: str | os.PathLike | None = None,
    code: "_Code | None" = None,
) -> Decision:
    tool = event.get("tool_name") or ""
    inp = event.get("tool_input") or {}
    if not isinstance(inp, dict):
        inp = {}
    if cwd is None:
        cwd = event.get("cwd") or None
    if tool in ("Bash", "Monitor"):
        # Monitor runs its command as Bash does; a WebSocket watch (`ws`, no command) runs nothing.
        return check_bash(inp.get("command") or "", profile, role, root, current_branch, role_from_env, cwd, code)
    if tool == "PowerShell":
        return check_powershell(inp, profile, role, root, cwd, code)
    if tool in WRITE_TOOLS:
        return check_write(tool, inp, profile, role, root, cwd, code)
    if tool.startswith("mcp__"):
        return check_mcp(tool, inp, profile, role, root)
    return ALLOW
