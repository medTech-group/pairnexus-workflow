"""Install the kit into a project as committed files: the vendored mode.

Cloud sessions load a repo's own `.claude/skills`, `.claude/agents` and the hooks
in `.claude/settings.json`, but don't install plugins. So a project used for
unattended runs carries a copy:

    .claude/skills/<kit and mattpocock skills>/
    .claude/agents/<reviewer agents>.md
    .claude/workflow/bin/            the `workflow` CLI the hooks call
    .claude/workflow/{flow.md, docs/, templates/, LICENSE}
    .claude/workflow/lock.json       versions and a hash of every file written
    .claude/settings.json            the kit's hooks, merged with the project's own

`install` refuses a project that also enables the plugin (one mode per
project). Everything is checked before anything is written: a file already
there that isn't the kit's stops the install (unless --adopt), with every such
file listed. `verify` compares the files with the lock. `update` replaces files
the project hasn't changed, keeps the project's edit where the kit didn't change
the file, and writes `<file>.new` beside any both changed, listing them as
conflicts to merge by hand; `resolve <path>` records the hand merge, and
`resolve --keep <path>` a deliberate local edit with no conflict (still a
conflict when the kit later changes that file). A file the kit drops that the
project edited is kept, and recorded as orphaned in the lock. `verify` fails on
missing files, missing hooks and unresolved conflicts (and, with --strict, on
changed files and Matt Pocock's skills left out without --no-mattpocock).

The lock (`files`: the hash of each file as written or resolved; `merged`: for a
resolved file, the kit version merged in; `conflicts`: the kit version each
unresolved conflict offers; `orphaned`: the kit version each kept orphan came
from; `kept`: the hash of each deliberate local edit) gives update a three-way
view: the project's file, the kit version it came from (`merged`, else
`files`), and the kit's new version. A file is edited when it differs from the
kit version it came from, so a conflict resolved by taking the kit's version
unchanged updates cleanly next time.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

LOCK = Path(".claude/workflow/lock.json")
SETTINGS = Path(".claude/settings.json")
SETTINGS_LOCAL = Path(".claude/settings.local.json")
HOOK_TAG = ".claude/workflow/bin/workflow.py"
PLUGIN_KEY = "pairnexus-workflow@pairnexus"
MP_PLUGIN = "mattpocock-skills"
MP_NOTICE = Path(".claude/skills/LICENSE-mattpocock-skills")
GUARD_MATCHER = "Bash|Edit|Write|MultiEdit|NotebookEdit|mcp__.*[Gg]it[Hh]ub.*"
SKIP_DOCS = {"flow.md", "proposal.md", "spike.md"}
IGNORE_LINE = ".workflow/"
IGNORE_LINES = {
    ".workflow/": {".workflow", ".workflow/", "/.workflow", "/.workflow/"},
    "__pycache__/": {"__pycache__", "__pycache__/", "/__pycache__/", "**/__pycache__", "**/__pycache__/", "*.pyc", "*.py[cod]"},
}
MP_MISSING = (
    "the Matt Pocock skills (tdd, code-review, to-spec, …) aren't vendored; build-ticket and review-panel need them. "
    "Pass --mattpocock <a checkout of mattpocock/skills>, or --no-mattpocock to go without them deliberately"
)
# Directories the kit owns as a whole: files there it doesn't ship are left from an earlier copy.
OWNED_DIRS = (".claude/workflow/bin/workflow", ".claude/workflow/docs", ".claude/workflow/templates")


class VendorError(RuntimeError):
    pass


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _settings(project: Path, rel: Path = SETTINGS) -> dict:
    f = project / rel
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise VendorError(f"{f} is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise VendorError(f"{f} must hold a JSON object")
    return data


MISSING_KIT_REASON = (
    f"the workflow kit is missing from this checkout ({HOOK_TAG}); restore it with: git checkout -- .claude/workflow"
)
# What the guard still allows with the kit missing: exactly these Bash commands.
RESTORE_COMMANDS = ("git checkout -- .claude/workflow", "git restore .claude/workflow")


NO_PYTHON_REASON = (
    "python3 could not run the workflow kit (it is missing or failing, or the kit failed: an invalid profile, "
    "a broken checkout), so nothing can be checked; check python3 --version (3.11 or newer is needed) and "
    "python3 .claude/workflow/bin/workflow.py profile check, then start a new session"
)
# Both go into single-quoted sh strings.
assert "'" not in NO_PYTHON_REASON + MISSING_KIT_REASON

# WORKFLOW_ROLE, trimmed and lower-cased as roles.env_role reads it.
_ROLE = (
    """R=$(printf '%s' "${WORKFLOW_ROLE:-}" | tr '[:upper:]' '[:lower:]' """
    """| sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'); """
)
# With WORKFLOW_ROLE unset and the kit set up: the project directory's branch
# matching the profile's run.ticket_branch (its first `ticket_branch = "…"`
# line, as _old_python reads it) means a ticket session. Without Python the
# event's cwd can't be read, so a worktree's own branch isn't seen.
_BRANCH = (
    'P="$CLAUDE_PROJECT_DIR/.claude/workflow/profile.toml"; '
    'if [ -z "$R" ] && [ -f "$P" ]; then '
    'B=$(git -C "$CLAUDE_PROJECT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null); '
    """T=$(sed -n 's/^[[:space:]]*ticket_branch[[:space:]]*=[[:space:]]*["'"'"']\\([^"'"'"']*\\)["'"'"'].*/\\1/p' "$P" | head -n 1); """
    'case "$B" in HEAD|"") ;; ${T:-claude/build-*}) R=ticket;; esac; fi; '
)


PLUGIN_CLI = "${CLAUDE_PLUGIN_ROOT}/scripts/workflow.py"
# The plugin has no profile check to point to: it says only what python3 needs.
PLUGIN_NO_PYTHON_REASON = (
    "python3 could not run the workflow kit (it is missing or failing, or the kit failed), so nothing can be checked and a push "
    "or a merge is asked first (refused in solo mode or where nobody is asked); check python3 --version (3.11 or newer is needed), then start a new session"
)
BROKEN_KIT_REASON = (
    "The workflow kit is broken (python3 could not run it, and its fallback.sh is missing), so the guard cannot check "
    "anything and asks about every tool. Restore the kit (a vendored project: git checkout -- .claude/workflow; the "
    "plugin: reinstall it) and check python3 --version (3.11 or newer), then start a new session."
)
assert "'" not in PLUGIN_NO_PYTHON_REASON + BROKEN_KIT_REASON


def hook_command(sub: str, plugin: bool = False) -> str:
    """The kit's hook command, run by Claude Code with sh: a vendored
    project's (the CLI under $CLAUDE_PROJECT_DIR), or with `plugin` the
    plugin's (the CLI under ${CLAUDE_PLUGIN_ROOT}). The CLI's directory holds
    the kit's package, `fallback.sh` included, in both.

    With the CLI there and `python3` on the PATH: `python3 -B` runs it (-B: no
    __pycache__ in the checkout); on a Python older than 3.11 the entry point
    hands the hook to `_old_python`, which fails closed too (#22).
    With the CLI missing (a session deleted it, a bad checkout):
    - the guard fails closed when WORKFLOW_ROLE is set to anything but
      `attended` (ticket, conductor, or an unrecognised value, which the CLI
      treats as ticket): it prints a deny decision, except for exactly
      `git checkout -- .claude/workflow` or `git restore .claude/workflow`, so
      the session can put the kit back. The event comes on stdin (hook commands
      get no $CLAUDE_TOOL_INPUT), so python3 reads it; without python3, every
      tool is denied and the owner restores the kit by hand;
    - with WORKFLOW_ROLE unset or `attended`, and for every other hook, it
      exits 0 silently (python3 on a missing file exits 2, which on PreToolUse
      would block every tool, unexplained).
    With the CLI there but `python3` missing or failing (a stub, a shim with no
    version, a broken checkout: a non-zero exit, which Claude Code reads as a
    non-blocking error, so the tool would run), the guard denies every tool to
    a ticket or conductor session (WORKFLOW_ROLE, or with it unset a branch
    matching the profile's run.ticket_branch), and an attended session gets
    the can't-decide fallback without Python (`fallback.sh`, #56): a push or a
    merge is asked, or refused in solo mode and where nobody is asked. An
    attended session's guard always exits 0. SessionStart says so to everyone
    (#22). The CLI itself exits 0 whenever it has decided, so a non-zero exit
    means it couldn't.

    The plugin is for attended work only: without a working python3 its guard
    never refuses every tool, and runs the fallback whatever WORKFLOW_ROLE
    says (an old python3 still reads the role, as the CLI does)."""
    cli = PLUGIN_CLI if plugin else f"$CLAUDE_PROJECT_DIR/{HOOK_TAG}"
    if sub not in ("guard", "repair"):
        return (
            f'F="{cli}"; '
            f'if [ -f "$F" ] && command -v python3 >/dev/null 2>&1; then exec python3 -B "$F" hook {sub}; fi; exit 0'
        )
    if sub == "repair":
        reason = PLUGIN_NO_PYTHON_REASON if plugin else NO_PYTHON_REASON
        told = json.dumps({"systemMessage": f"Workflow kit: {reason}."}, separators=(",", ":"))
        return (
            f'F="{cli}"; '
            f'if [ -f "$F" ] && command -v python3 >/dev/null 2>&1; then python3 -B "$F" hook repair && exit 0; fi; '
            f"if [ -f \"$F\" ]; then printf '%s\\n' '{told}'; fi; exit 0"
        )
    # The event is read once, so the fallback still has it after python3 failed.
    run = (
        f'F="{cli}"; E=$(cat); '
        'if [ -f "$F" ] && command -v python3 >/dev/null 2>&1; then '
        """O=$(printf '%s\\n' "$E" | python3 -B "$F" hook guard) && { [ -z "$O" ] || printf '%s\\n' "$O"; exit 0; }; fi; """
    )
    # With fallback.sh missing too (a partial copy of the kit), every tool is asked.
    broken = json.dumps(
        {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": BROKEN_KIT_REASON}},
        separators=(",", ":"),
    )
    fallback = (
        """if [ -f "$F" ] && [ -f "${F%.py}/fallback.sh" ]; then printf '%s\\n' "$E" | sh "${F%.py}/fallback.sh"; """
        f"""elif [ -f "$F" ]; then printf '%s\\n' '{broken}'; fi; exit 0"""
    )
    if plugin:
        return run + fallback

    def deny(reason: str) -> str:
        return json.dumps(
            {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}},
            separators=(",", ":"),
        )

    restore = (
        "import json,sys;e=json.load(sys.stdin);i=e.get('tool_input') or {};"
        "c=i.get('command') if e.get('tool_name')=='Bash' and isinstance(i,dict) else None;"
        f"sys.exit(0 if isinstance(c,str) and ' '.join(c.split()) in {RESTORE_COMMANDS!r} else 1)"
    ).replace("'", '"')
    return (
        run
        + _ROLE
        + 'if [ -f "$F" ]; then ' + _BRANCH + 'fi; '
        + 'if [ -z "$R" ] || [ "$R" = attended ]; then ' + fallback + '; fi; '
        + f"if [ -f \"$F\" ]; then printf '%s\\n' '{deny('Refused: ' + NO_PYTHON_REASON + '.')}'; exit 0; fi; "
        + f"""if command -v python3 >/dev/null 2>&1 && printf '%s\\n' "$E" | python3 -c '{restore}' 2>/dev/null; then exit 0; fi; """
        + f"printf '%s\\n' '{deny(MISSING_KIT_REASON)}'"
    )


def _hook(sub: str, matcher: str | None = None, timeout: int = 30, plugin: bool = False) -> dict:
    entry: dict = {"hooks": [{"type": "command", "command": hook_command(sub, plugin), "timeout": timeout}]}
    if matcher:
        entry["matcher"] = matcher
    return entry


def _kit_hooks(plugin: bool = False) -> dict:
    return {
        "PreToolUse": [_hook("guard", GUARD_MATCHER, 15, plugin)],
        "Stop": [_hook("gate", None, 15, plugin)],
        "UserPromptSubmit": [_hook("context", None, 10, plugin)],
        "SessionStart": [_hook("repair", "startup|resume", 600, plugin)],
    }


KIT_HOOKS = _kit_hooks()


def plugin_hooks() -> dict:
    """The plugin's hooks file (`hooks/hooks.json`): the same hooks as a
    vendored project's settings, rooted at the plugin's directory (#56). A
    test checks the file against this; to write it again, run
    `python3 -c "import json,sys; sys.path.insert(0, 'scripts'); from workflow import vendor; print(json.dumps(vendor.plugin_hooks(), indent=2))" > hooks/hooks.json`."""
    return {"hooks": _kit_hooks(plugin=True)}


def _is_kit_hook(h: dict) -> bool:
    return HOOK_TAG in str(h.get("command", ""))


def _check_hooks(settings: dict) -> None:
    if not isinstance(settings, dict):
        raise VendorError(f"{SETTINGS} must hold a JSON object")
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        raise VendorError(f'{SETTINGS}: "hooks" must be an object of event -> list of entries')
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            raise VendorError(f"{SETTINGS}: hooks.{event} must be a list of entries")
        for i, e in enumerate(entries):
            if not isinstance(e, dict) or not isinstance(e.get("hooks"), list):
                raise VendorError(f'{SETTINGS}: hooks.{event}[{i}] must be an object with a "hooks" list')
            for j, h in enumerate(e["hooks"]):
                if not isinstance(h, dict):
                    raise VendorError(f"{SETTINGS}: hooks.{event}[{i}].hooks[{j}] must be an object")


def merge_hooks(settings: dict) -> dict:
    """The project's settings with the kit's hooks replacing any earlier kit hooks.
    Only the kit's commands are taken out of an entry; an entry is dropped only
    when that leaves it empty."""
    _check_hooks(settings)
    out = json.loads(json.dumps(settings))
    hooks = out.setdefault("hooks", {})
    for event in list(hooks):
        kept = []
        for entry in hooks[event]:
            mine = [h for h in entry["hooks"] if not _is_kit_hook(h)]
            if len(mine) == len(entry["hooks"]):
                kept.append(entry)
            elif mine:
                kept.append({**entry, "hooks": mine})
        hooks[event] = kept
    for event, entries in KIT_HOOKS.items():
        hooks.setdefault(event, []).extend(json.loads(json.dumps(entries)))
    for event in [e for e, v in hooks.items() if not v]:
        del hooks[event]
    return out


def _walk(src: Path, symlinks: list[str] | None):
    """Regular files under src, sorted; symlinks are skipped and noted, never followed."""
    for d, dirs, names in os.walk(src, followlinks=False):
        here = Path(d)
        for name in sorted(dirs):
            if (here / name).is_symlink() and symlinks is not None:
                symlinks.append(str(here / name))
        dirs[:] = sorted(x for x in dirs if x != "__pycache__" and not (here / x).is_symlink())
        for name in sorted(names):
            f = here / name
            if f.is_symlink():
                if symlinks is not None:
                    symlinks.append(str(f))
                continue
            if name.endswith(".pyc") or not f.is_file():
                continue
            yield f


def looks_like_kit(kit: Path) -> bool:
    return (kit / "skills").is_dir() and (kit / "scripts/workflow.py").is_file()


def plan(kit: Path, mattpocock: Path | None, symlinks: list[str] | None = None) -> dict[str, Path]:
    """Destination (relative to the project) -> source file."""
    if not looks_like_kit(kit):
        raise VendorError(f"{kit} doesn't look like the kit (no skills/ and scripts/workflow.py); pass --kit <the kit's checkout>")
    files: dict[str, Path] = {}

    def add_tree(src: Path, dst: str):
        for f in sorted(_walk(src, symlinks)):
            files[f"{dst}/{f.relative_to(src).as_posix()}"] = f

    for skill in sorted((kit / "skills").iterdir()):
        if skill.is_symlink():
            if symlinks is not None:
                symlinks.append(str(skill))
            continue
        if (skill / "SKILL.md").exists():
            add_tree(skill, f".claude/skills/{skill.name}")
    for agent in sorted((kit / "agents").glob("*.md")):
        files[f".claude/agents/{agent.name}"] = agent
    add_tree(kit / "scripts/workflow", ".claude/workflow/bin/workflow")
    files[".claude/workflow/bin/workflow.py"] = kit / "scripts/workflow.py"
    files[".claude/workflow/flow.md"] = kit / "docs/flow.md"
    for d in sorted((kit / "docs").glob("*.md")):
        if d.name not in SKIP_DOCS:
            files[f".claude/workflow/docs/{d.name}"] = d
    add_tree(kit / "templates", ".claude/workflow/templates")
    if (kit / "LICENSE").is_file():
        files[".claude/workflow/LICENSE"] = kit / "LICENSE"  # MIT: the notice travels with the copy
    if mattpocock:
        root = mattpocock.resolve()
        mf = mattpocock / ".claude-plugin/plugin.json"
        try:
            manifest = json.loads(mf.read_text())
        except (OSError, json.JSONDecodeError) as e:
            raise VendorError(f"{mf} can't be read ({e}); pass --mattpocock <a checkout of mattpocock/skills>") from e
        for rel in manifest.get("skills") or []:
            src = (mattpocock / rel).resolve()
            if not src.is_relative_to(root):
                raise VendorError(f"mattpocock skill {rel!r} resolves to {src}, outside the checkout {root}")
            if not (src / "SKILL.md").exists():
                raise VendorError(f"mattpocock skill {rel} has no SKILL.md")
            if (kit / "skills" / src.name).exists():
                continue  # the kit's own skill of that name wins
            add_tree(src, f".claude/skills/{src.name}")
        files[MP_NOTICE.as_posix()] = mattpocock / "LICENSE"
    return files


def _git_sha(path: Path) -> str | None:
    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else None


def pinned_mattpocock_sha(kit: Path) -> str | None:
    """The SHA the kit's marketplace pins the mattpocock-skills plugin at."""
    f = kit / ".claude-plugin/marketplace.json"
    try:
        data = json.loads(f.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    for p in data.get("plugins") or []:
        if isinstance(p, dict) and p.get("name") == MP_PLUGIN and isinstance(p.get("source"), dict):
            return p["source"].get("sha")
    return None


def read_lock(project: Path) -> dict | None:
    f = project / LOCK
    if not f.exists():
        return None
    try:
        lock = json.loads(f.read_text())
    except json.JSONDecodeError as e:
        raise VendorError(f"{f} is not valid JSON: {e}") from e
    if not isinstance(lock, dict) or not isinstance(lock.get("files"), dict):
        raise VendorError(f"{f} has no files map; restore it from git")
    return lock


def _write_lock(project: Path, lock: dict) -> None:
    (project / LOCK).parent.mkdir(parents=True, exist_ok=True)
    (project / LOCK).write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _ensure_ignored(project: Path) -> list[str]:
    """Add `.workflow/` (the evidence and run scratch) and `__pycache__/` (the hooks
    run `python3 -B`, but other scripts may not) to .gitignore; the lines added."""
    f = project / ".gitignore"
    text = f.read_text(encoding="utf-8") if f.exists() else ""
    have = {l.strip() for l in text.splitlines()}
    add = [line for line, forms in IGNORE_LINES.items() if not have & forms]
    if not add:
        return []
    if text and not text.endswith("\n"):
        text += "\n"
    f.write_text(text + "".join(l + "\n" for l in add), encoding="utf-8")
    return add


def _other_prompt_hooks(project: Path) -> list[str]:
    """The commands of UserPromptSubmit hooks that aren't the kit's."""
    out = []
    for rel in (SETTINGS, SETTINGS_LOCAL):
        hooks = _settings(project, rel).get("hooks")
        entries = hooks.get("UserPromptSubmit") if isinstance(hooks, dict) else None
        for e in entries if isinstance(entries, list) else []:
            for h in (e.get("hooks") if isinstance(e, dict) else None) or []:
                if isinstance(h, dict) and not _is_kit_hook(h):
                    out.append(f"{h.get('command') or h.get('type') or '?'} (in {rel})")
    return out


def _stale(project: Path, files: dict[str, Path], known: set[str]) -> list[str]:
    """Files in directories the kit owns (each of its skills, and the CLI, docs and
    templates) that it doesn't ship and the lock doesn't know: left from an
    earlier copy. Reported, never deleted."""
    dirs = set(OWNED_DIRS)
    for dst in files:
        parts = dst.split("/")
        if len(parts) > 3 and parts[:2] == [".claude", "skills"]:
            dirs.add("/".join(parts[:3]))
    out = []
    for d in sorted(dirs):
        root = project / d
        if not root.is_dir():
            continue
        for f in _walk(root, None):
            rel = f.relative_to(project).as_posix()
            if rel not in files and rel not in known and not rel.endswith(".new"):
                out.append(rel)
    return sorted(out)


def _clash_message(clashes: list[str]) -> list[str]:
    by_skill: dict[str, list[str]] = {}
    other: list[str] = []
    for dst in clashes:
        parts = dst.split("/")
        if len(parts) > 3 and parts[:2] == [".claude", "skills"]:
            by_skill.setdefault(parts[2], []).append(dst)
        else:
            other.append(dst)
    out = []
    for name, paths in by_skill.items():
        out.append(
            f"a skill of the same name already exists in .claude/skills/{name}/: rename the project's skill "
            f"directory, or pass --adopt to replace it ({', '.join(paths)})"
        )
    for dst in other:
        out.append(f"{dst} already exists and isn't the kit's: rename or move the project's file, or pass --adopt to replace it")
    return out


def install(
    kit: Path,
    project: Path,
    mattpocock: Path | None,
    update: bool = False,
    adopt: bool = False,
    strict_pin: bool = False,
    no_mattpocock: bool = False,
) -> dict:
    for rel in (SETTINGS, SETTINGS_LOCAL):
        if (_settings(project, rel).get("enabledPlugins") or {}).get(PLUGIN_KEY):
            raise VendorError(
                f"{rel} enables the {PLUGIN_KEY} plugin: pick one mode per project. "
                "Remove the plugin from enabledPlugins to vendor, or don't vendor."
            )
    settings = _settings(project)
    lock = read_lock(project)
    if lock and not update:
        raise VendorError("the kit is already vendored here; use `workflow vendor update`")
    if update and not lock:
        raise VendorError("nothing to update: the kit isn't vendored here yet")
    lock = lock or {}
    if mattpocock is not None and no_mattpocock:
        raise VendorError("give --mattpocock or --no-mattpocock, not both")
    if update and lock.get("mattpocock_sha") and mattpocock is None and not no_mattpocock:
        raise VendorError(
            f"the lock records Matt Pocock's skills (at {lock['mattpocock_sha']}); "
            "pass --mattpocock <checkout at SHA> so the update keeps them instead of removing them"
        )
    if not looks_like_kit(kit):
        raise VendorError(f"{kit} doesn't look like the kit (no skills/ and scripts/workflow.py); pass --kit <the kit's checkout>")
    warnings: list[str] = []
    if mattpocock:
        mp_state = "vendored"
    elif no_mattpocock or (update and lock.get("mattpocock_skills") == "declined"):
        mp_state = "declined"
    else:
        mp_state = "not_vendored"
        warnings.append(MP_MISSING)
    for cmd in _other_prompt_hooks(project):
        warnings.append(
            f"the project's settings already have a UserPromptSubmit hook, {cmd}: if it also puts the flow in "
            "context, sessions get it twice; remove it once the kit's context hook replaces it"
        )
    mp_sha = None
    if mattpocock:
        mp_sha = _git_sha(mattpocock)
        pinned = pinned_mattpocock_sha(kit)
        if pinned and mp_sha != pinned:
            warnings.append(
                f"the mattpocock checkout is at {mp_sha or 'an unknown commit (not a git checkout)'}, "
                f"but the kit pins {pinned} (.claude-plugin/marketplace.json)"
            )
    if strict_pin and warnings:
        raise VendorError(warnings[0] + "; check out the pinned SHA, or drop --strict-pin")

    # ---- plan everything; write nothing until it all checks out ----
    new_settings = merge_hooks(settings)
    symlinks: list[str] = []
    files = plan(kit, mattpocock, symlinks)
    old_files: dict[str, str] = dict(lock.get("files", {}))
    merged: dict[str, str] = dict(lock.get("merged", {}))
    pending: dict[str, str] = dict(lock.get("conflicts", {}))
    orphaned: dict[str, str] = dict(lock.get("orphaned", {}))
    keeps: dict[str, str] = dict(lock.get("kept", {}))
    missing = [f"{dst} (from {src})" for dst, src in files.items() if not src.is_file()]
    if missing:
        raise VendorError("the kit is missing files it should ship: " + "; ".join(missing))

    writes: list[str] = []  # to copy over
    conflicts: list[str] = []
    unchanged: list[str] = []
    kept: list[str] = []  # the project's edit, which the kit didn't change
    adopted: list[str] = []
    clashes: list[str] = []
    new_hash: dict[str, str] = {}
    for dst, src in files.items():
        target = project / dst
        h = new_hash[dst] = _hash(src)
        if not target.exists():
            writes.append(dst)
            continue
        cur = _hash(target)
        if cur == h:
            unchanged.append(dst)
            continue
        if dst in old_files:
            # The kit version the file came from: what a resolve merged in, else as written.
            kit_base = merged.get(dst, old_files[dst])
            edited = cur != kit_base
        elif dst in orphaned:
            kit_base, edited = orphaned[dst], cur != orphaned[dst]
        else:
            if adopt:
                adopted.append(dst)
                writes.append(dst)
            else:
                clashes.append(dst)
            continue
        if not edited:
            writes.append(dst)
        elif h == kit_base:
            kept.append(dst)
        else:
            conflicts.append(dst)
    if clashes:
        raise VendorError(
            "nothing was written: these are already in the project and aren't the kit's:\n- "
            + "\n- ".join(_clash_message(clashes))
        )

    removed: list[str] = []
    orphans: list[str] = []
    for dst, h in old_files.items():
        if dst in files:
            continue
        t = project / dst
        if not t.exists():
            continue
        if _hash(t) == merged.get(dst, h):
            removed.append(dst)
        else:
            orphans.append(dst)
    for dst, h in list(orphaned.items()):
        if dst in files:
            continue
        t = project / dst
        if not t.exists():
            del orphaned[dst]
        elif _hash(t) == h:
            removed.append(dst)

    stale = _stale(project, files, set(old_files) | set(orphaned)) if adopt else []

    # ---- write ----
    for dst in writes:
        target = project / dst
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(files[dst], target)
    for dst in conflicts:
        target = project / dst
        shutil.copyfile(files[dst], target.with_name(target.name + ".new"))
    # A <file>.new left from an earlier update whose file has no conflict now.
    for dst in set(files) | set(old_files) | set(orphaned) | set(pending):
        if dst in conflicts or dst + ".new" in files:
            continue
        stale_new = (project / dst).with_name(Path(dst).name + ".new")
        if stale_new.is_file() and not stale_new.is_symlink():
            stale_new.unlink()
    for dst in removed:
        (project / dst).unlink()
        orphaned.pop(dst, None)
    for dst in orphans:
        orphaned[dst] = merged.get(dst, old_files[dst])
    (project / SETTINGS).parent.mkdir(parents=True, exist_ok=True)
    (project / SETTINGS).write_text(json.dumps(new_settings, indent=2) + "\n", encoding="utf-8")
    ignored = _ensure_ignored(project)

    lock_files: dict[str, str] = {}
    new_merged: dict[str, str] = {}
    new_pending: dict[str, str] = {}
    new_keeps: dict[str, str] = {}
    # A deliberate edit to a file the kit dropped stays recorded while the file
    # is unchanged, so it is still kept if the kit adds the file back unchanged.
    for dst in orphaned:
        if dst not in files and dst in keeps and (project / dst).exists() and _hash(project / dst) == keeps[dst]:
            new_keeps[dst] = keeps[dst]
    for dst in files:
        if dst in kept or dst in conflicts:
            lock_files[dst] = old_files.get(dst) or orphaned[dst]
            if dst in merged:
                new_merged[dst] = merged[dst]
            if dst in conflicts:
                new_pending[dst] = new_hash[dst]
            elif dst in keeps and _hash(project / dst) == keeps[dst]:
                new_keeps[dst] = keeps[dst]  # still the deliberate edit, and the kit didn't change it
        else:
            lock_files[dst] = _hash(project / dst)
        orphaned.pop(dst, None)
    version = (kit / "VERSION").read_text().strip() if (kit / "VERSION").exists() else "unknown"
    new_lock = {
        "kit_version": version,
        "kit_sha": _git_sha(kit),
        "mattpocock_sha": mp_sha if mattpocock else None,
        "mattpocock_skills": mp_state,
        "files": lock_files,
        "merged": new_merged,
        "conflicts": new_pending,
        "orphaned": orphaned,
        "kept": new_keeps,
    }
    _write_lock(project, new_lock)
    return {
        "version": version,
        "written": [d for d in writes if d not in adopted],
        "adopted": adopted,
        "unchanged": unchanged,
        "kept": kept,
        "conflicts": conflicts,
        "removed": removed,
        "orphaned": orphans,
        "stale": stale,
        "symlinks_skipped": symlinks,
        "gitignore_added": ignored,
        "warnings": warnings,
    }


def resolve(project: Path, path: str, keep: bool = False) -> dict:
    """A hand-merged conflict: record the file as the project's, with the kit
    version merged in, and delete <path>.new, so update stops reporting it.

    With keep: a deliberate local edit to a vendored file with no conflict,
    recorded as `kept` so `verify --strict` passes for it. Update leaves it while
    the kit doesn't change the file, and reports a conflict when it does."""
    lock = read_lock(project)
    if not lock:
        raise VendorError("the kit isn't vendored here (no .claude/workflow/lock.json)")
    p = Path(path)
    if p.is_absolute():
        try:
            p = p.resolve().relative_to(project.resolve())
        except ValueError:
            raise VendorError(f"{path} isn't inside the project {project}") from None
    dst = p.as_posix().removesuffix(".new")
    target = project / dst
    new = target.with_name(target.name + ".new")
    pending = lock.setdefault("conflicts", {})
    if dst not in lock["files"]:
        raise VendorError(f"{dst} isn't one of the kit's files in the lock")
    if not target.exists():
        raise VendorError(f"{dst} doesn't exist; restore it, or run `vendor update` again")
    if keep:
        if dst in pending or new.exists():
            raise VendorError(f"{dst} has a conflict: merge {dst}.new into it and run `vendor resolve {dst}`")
        cur = _hash(target)
        if cur == lock["files"][dst]:
            raise VendorError(f"{dst} is as the lock records it: there is no local edit to keep")
        lock.setdefault("kept", {})[dst] = cur
        _write_lock(project, lock)
        return {"kept": dst}
    kit_version = pending.pop(dst, None) or (_hash(new) if new.exists() else None)
    if kit_version is None:
        raise VendorError(
            f"{dst} has no conflict to resolve (no {dst}.new and none in the lock); "
            f"to keep a local edit, `vendor resolve --keep {dst}`"
        )
    lock["files"][dst] = _hash(target)
    lock.setdefault("merged", {})[dst] = kit_version
    (lock.get("kept") or {}).pop(dst, None)
    _write_lock(project, lock)
    if new.exists():
        new.unlink()
    return {"resolved": dst}


def verify(project: Path) -> dict:
    lock = read_lock(project)
    if not lock:
        raise VendorError("the kit isn't vendored here (no .claude/workflow/lock.json)")
    missing, changed, kept = [], [], []
    keeps = lock.get("kept") or {}
    for dst, h in lock["files"].items():
        t = project / dst
        if not t.exists():
            missing.append(dst)
            continue
        cur = _hash(t)
        if cur == h:
            continue
        if keeps.get(dst) == cur:
            kept.append(dst)
        else:
            changed.append(dst)
    settings = _settings(project)
    hooks = settings.get("hooks") if isinstance(settings.get("hooks"), dict) else {}
    hooks_ok = all(
        any(
            _is_kit_hook(h)
            for e in (hooks.get(ev) or [])
            if isinstance(e, dict)
            for h in (e.get("hooks") or [])
            if isinstance(h, dict)
        )
        for ev in KIT_HOOKS
    )
    plugin_too = any(
        (_settings(project, rel).get("enabledPlugins") or {}).get(PLUGIN_KEY) for rel in (SETTINGS, SETTINGS_LOCAL)
    )
    mp = lock.get("mattpocock_skills") or ("vendored" if lock.get("mattpocock_sha") else "not_vendored")
    return {
        "version": lock.get("kit_version"),
        "missing": missing,
        "changed": changed,
        "kept": kept,
        "mattpocock": mp,
        "conflicts": sorted(lock.get("conflicts") or {}),
        "orphaned": sorted(lock.get("orphaned") or {}),
        "hooks_ok": hooks_ok,
        "plugin_also_enabled": bool(plugin_too),
    }
