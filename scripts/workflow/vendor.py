"""Install the kit into a project as committed files: the vendored mode.

Cloud sessions load a repo's own `.claude/skills`, `.claude/agents` and the hooks
in `.claude/settings.json`, but don't install plugins. So a project used for
unattended runs carries a copy:

    .claude/skills/<kit and mattpocock skills>/
    .claude/agents/<reviewer agents>.md
    .claude/workflow/bin/            the `workflow` CLI the hooks call
    .claude/workflow/{flow.md, docs/, templates/}
    .claude/workflow/lock.json       versions and a hash of every file written
    .claude/settings.json            the kit's hooks, merged with the project's own

`install` refuses a project that also enables the plugin (one mode per
project). Everything is checked before anything is written: a file already
there that isn't the kit's stops the install (unless --adopt), with every such
file listed. `verify` compares the files with the lock. `update` replaces files
the project hasn't changed, keeps the project's edit where the kit didn't change
the file, and writes `<file>.new` beside any both changed, listing them as
conflicts to merge by hand; `resolve <path>` records the hand merge. A file the
kit drops that the project edited is kept, and recorded as orphaned in the lock.

The lock (`files`: the hash of each file as written or resolved; `merged`: for a
resolved file, the kit version merged in; `conflicts`: the kit version each
unresolved conflict offers; `orphaned`: the kit version each kept orphan came
from) gives update a three-way view: the project's file, the kit version it came
from, and the kit's new version.
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


def hook_command(sub: str) -> str:
    """The kit's hook command. It exits 0 when the CLI is missing: python3 on a
    missing file exits 2, which on PreToolUse would block every tool."""
    return f'F="$CLAUDE_PROJECT_DIR/{HOOK_TAG}"; [ -f "$F" ] || exit 0; python3 "$F" hook {sub}'


def _hook(sub: str, matcher: str | None = None, timeout: int = 30) -> dict:
    entry: dict = {"hooks": [{"type": "command", "command": hook_command(sub), "timeout": timeout}]}
    if matcher:
        entry["matcher"] = matcher
    return entry


KIT_HOOKS = {
    "PreToolUse": [_hook("guard", GUARD_MATCHER, 15)],
    "Stop": [_hook("gate", None, 15)],
    "UserPromptSubmit": [_hook("context", None, 10)],
    "SessionStart": [_hook("repair", "startup|resume", 300)],
}


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


def _ensure_ignored(project: Path) -> bool:
    """Add `.workflow/` (the evidence and run scratch) to .gitignore; True when added."""
    f = project / ".gitignore"
    text = f.read_text(encoding="utf-8") if f.exists() else ""
    if any(l.strip() in {".workflow", ".workflow/", "/.workflow", "/.workflow/"} for l in text.splitlines()):
        return False
    if text and not text.endswith("\n"):
        text += "\n"
    f.write_text(text + IGNORE_LINE + "\n", encoding="utf-8")
    return True


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
    if update and lock.get("mattpocock_sha") and mattpocock is None:
        raise VendorError(
            f"the lock records Matt Pocock's skills (at {lock['mattpocock_sha']}); "
            "pass --mattpocock <checkout at SHA> so the update keeps them instead of removing them"
        )
    if not looks_like_kit(kit):
        raise VendorError(f"{kit} doesn't look like the kit (no skills/ and scripts/workflow.py); pass --kit <the kit's checkout>")
    warnings: list[str] = []
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
            kit_base = merged.get(dst, old_files[dst])
            edited = cur != old_files[dst] or dst in merged
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
        if _hash(t) == h and dst not in merged:
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

    # ---- write ----
    for dst in writes:
        target = project / dst
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(files[dst], target)
    for dst in conflicts:
        target = project / dst
        shutil.copyfile(files[dst], target.with_name(target.name + ".new"))
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
    for dst in files:
        if dst in kept or dst in conflicts:
            lock_files[dst] = old_files.get(dst) or orphaned[dst]
            if dst in merged:
                new_merged[dst] = merged[dst]
            if dst in conflicts:
                new_pending[dst] = new_hash[dst]
        else:
            lock_files[dst] = _hash(project / dst)
        orphaned.pop(dst, None)
    version = (kit / "VERSION").read_text().strip() if (kit / "VERSION").exists() else "unknown"
    new_lock = {
        "kit_version": version,
        "kit_sha": _git_sha(kit),
        "mattpocock_sha": mp_sha if mattpocock else None,
        "files": lock_files,
        "merged": new_merged,
        "conflicts": new_pending,
        "orphaned": orphaned,
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
        "symlinks_skipped": symlinks,
        "gitignore_added": ignored,
        "warnings": warnings,
    }


def resolve(project: Path, path: str) -> dict:
    """A hand-merged conflict: record the file as the project's, with the kit
    version merged in, and delete <path>.new, so update stops reporting it."""
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
    kit_version = pending.pop(dst, None) or (_hash(new) if new.exists() else None)
    if kit_version is None:
        raise VendorError(f"{dst} has no conflict to resolve (no {dst}.new and none in the lock)")
    lock["files"][dst] = _hash(target)
    lock.setdefault("merged", {})[dst] = kit_version
    _write_lock(project, lock)
    if new.exists():
        new.unlink()
    return {"resolved": dst}


def verify(project: Path) -> dict:
    lock = read_lock(project)
    if not lock:
        raise VendorError("the kit isn't vendored here (no .claude/workflow/lock.json)")
    missing, changed = [], []
    for dst, h in lock["files"].items():
        t = project / dst
        if not t.exists():
            missing.append(dst)
        elif _hash(t) != h:
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
    return {
        "version": lock.get("kit_version"),
        "missing": missing,
        "changed": changed,
        "conflicts": sorted(lock.get("conflicts") or {}),
        "orphaned": sorted(lock.get("orphaned") or {}),
        "hooks_ok": hooks_ok,
        "plugin_also_enabled": bool(plugin_too),
    }
