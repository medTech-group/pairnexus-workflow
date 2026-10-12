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
project). `verify` compares the files with the lock. `update` replaces files
the project hasn't changed and writes `<file>.new` beside any it has, listing
them as conflicts to merge by hand.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

LOCK = Path(".claude/workflow/lock.json")
SETTINGS = Path(".claude/settings.json")
HOOK_TAG = ".claude/workflow/bin/workflow.py"
PLUGIN_KEY = "pairnexus-workflow@pairnexus"
MP_NOTICE = Path(".claude/skills/LICENSE-mattpocock-skills")


class VendorError(RuntimeError):
    pass


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _settings(project: Path) -> dict:
    f = project / SETTINGS
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise VendorError(f"{f} is not valid JSON: {e}") from e


def _hook(event: str, sub: str, matcher: str | None = None, timeout: int = 30) -> dict:
    entry: dict = {
        "hooks": [
            {
                "type": "command",
                "command": f'python3 "$CLAUDE_PROJECT_DIR/{HOOK_TAG}" hook {sub}',
                "timeout": timeout,
            }
        ]
    }
    if matcher:
        entry["matcher"] = matcher
    return entry


KIT_HOOKS = {
    "PreToolUse": [_hook("PreToolUse", "guard", "Bash|Edit|Write|MultiEdit|NotebookEdit|mcp__.*github.*", 15)],
    "Stop": [_hook("Stop", "gate", None, 15)],
    "UserPromptSubmit": [_hook("UserPromptSubmit", "context", None, 10)],
    "SessionStart": [_hook("SessionStart", "repair", "startup|resume", 300)],
}


def merge_hooks(settings: dict) -> dict:
    """The project's settings with the kit's hooks replacing any earlier kit hooks."""
    out = json.loads(json.dumps(settings))
    hooks = out.setdefault("hooks", {})
    for event in list(hooks):
        kept = []
        for entry in hooks[event]:
            cmds = [h.get("command", "") for h in entry.get("hooks", [])]
            if not any(HOOK_TAG in c for c in cmds):
                kept.append(entry)
        hooks[event] = kept
    for event, entries in KIT_HOOKS.items():
        hooks.setdefault(event, []).extend(entries)
    for event in [e for e, v in hooks.items() if not v]:
        del hooks[event]
    return out


def plan(kit: Path, mattpocock: Path | None) -> dict[str, Path]:
    """Destination (relative to the project) -> source file."""
    files: dict[str, Path] = {}

    def add_tree(src: Path, dst: str):
        for f in sorted(src.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts and not f.name.endswith(".pyc"):
                files[f"{dst}/{f.relative_to(src).as_posix()}"] = f

    for skill in sorted((kit / "skills").iterdir()):
        if (skill / "SKILL.md").exists():
            add_tree(skill, f".claude/skills/{skill.name}")
    for agent in sorted((kit / "agents").glob("*.md")):
        files[f".claude/agents/{agent.name}"] = agent
    add_tree(kit / "scripts/workflow", ".claude/workflow/bin/workflow")
    files[".claude/workflow/bin/workflow.py"] = kit / "scripts/workflow.py"
    files[".claude/workflow/flow.md"] = kit / "docs/flow.md"
    for d in sorted((kit / "docs").glob("*.md")):
        if d.name != "flow.md":
            files[f".claude/workflow/docs/{d.name}"] = d
    add_tree(kit / "templates", ".claude/workflow/templates")
    if mattpocock:
        manifest = json.loads((mattpocock / ".claude-plugin/plugin.json").read_text())
        for rel in manifest.get("skills") or []:
            src = (mattpocock / rel).resolve()
            if not (src / "SKILL.md").exists():
                raise VendorError(f"mattpocock skill {rel} has no SKILL.md")
            if (kit / "skills" / src.name).exists():
                continue  # the kit's own skill of that name wins
            add_tree(src, f".claude/skills/{src.name}")
        files[MP_NOTICE.as_posix()] = mattpocock / "LICENSE"
    return files


def _git_sha(path: Path) -> str | None:
    import subprocess

    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else None


def read_lock(project: Path) -> dict | None:
    f = project / LOCK
    return json.loads(f.read_text()) if f.exists() else None


def install(kit: Path, project: Path, mattpocock: Path | None, update: bool = False, adopt: bool = False) -> dict:
    settings = _settings(project)
    if (settings.get("enabledPlugins") or {}).get(PLUGIN_KEY):
        raise VendorError(
            f"{SETTINGS} enables the {PLUGIN_KEY} plugin: pick one mode per project. "
            "Remove the plugin from enabledPlugins to vendor, or don't vendor."
        )
    lock = read_lock(project)
    if lock and not update:
        raise VendorError("the kit is already vendored here; use `workflow vendor update`")
    if update and not lock:
        raise VendorError("nothing to update: the kit isn't vendored here yet")
    old_hashes: dict[str, str] = (lock or {}).get("files", {})
    files = plan(kit, mattpocock)
    written, conflicts, unchanged, adopted = [], [], [], []
    for dst, src in files.items():
        target = project / dst
        new_hash = _hash(src)
        if target.exists():
            cur = _hash(target)
            if cur == new_hash:
                unchanged.append(dst)
                continue
            if dst in old_hashes and cur != old_hashes[dst]:
                # Changed in the project since it was vendored: keep it, offer ours beside it.
                shutil.copyfile(src, target.with_name(target.name + ".new"))
                conflicts.append(dst)
                continue
            if dst not in old_hashes and not adopt:
                raise VendorError(
                    f"{dst} already exists and isn't the kit's: rename the project's own file, or pass --adopt to replace earlier hand-vendored copies"
                )
            if dst not in old_hashes:
                adopted.append(dst)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
        written.append(dst)
    removed = []
    for dst in old_hashes:
        if dst not in files:
            t = project / dst
            if t.exists() and _hash(t) == old_hashes[dst]:
                t.unlink()
                removed.append(dst)
    new_settings = merge_hooks(settings)
    (project / SETTINGS).parent.mkdir(parents=True, exist_ok=True)
    (project / SETTINGS).write_text(json.dumps(new_settings, indent=2) + "\n", encoding="utf-8")
    version = (kit / "VERSION").read_text().strip()
    new_lock = {
        "kit_version": version,
        "kit_sha": _git_sha(kit),
        "mattpocock_sha": _git_sha(mattpocock) if mattpocock else None,
        "files": {d: (old_hashes.get(d) if d in conflicts else _hash(project / d)) for d in files},
    }
    (project / LOCK).parent.mkdir(parents=True, exist_ok=True)
    (project / LOCK).write_text(json.dumps(new_lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"written": written, "adopted": adopted, "unchanged": unchanged, "conflicts": conflicts, "removed": removed, "version": version}


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
    hooks_ok = all(
        any(HOOK_TAG in h.get("command", "") for e in (settings.get("hooks") or {}).get(ev, []) for h in e.get("hooks", []))
        for ev in KIT_HOOKS
    )
    plugin_too = bool((settings.get("enabledPlugins") or {}).get(PLUGIN_KEY))
    return {
        "version": lock.get("kit_version"),
        "missing": missing,
        "changed": changed,
        "hooks_ok": hooks_ok,
        "plugin_also_enabled": plugin_too,
    }
