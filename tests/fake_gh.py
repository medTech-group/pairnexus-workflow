"""A fake `gh` on the PATH, for tests of commands that read GitHub through
`gh api` (merge-check's `--fetch`, #81; doctor's, #59). No test calls the real
GitHub API.

    gh = fake_gh.install(tmp_path, monkeypatch, {
        "repos/acme/demo/pulls/12": {...},                     # printed as JSON
        "repos/acme/demo/pulls/12/files": fake_gh.pages([...], [...]),
        "graphql": fake_gh.pages({...}),
        "repos/acme/demo/collaborators/dev/permission": fake_gh.reply(exit=1, stderr="gh: Not Found (HTTP 404)"),
    })
    ... run the command ...
    gh.paths()   # the paths asked for, in order

A route is an `api` call's path without its query string, or "graphql". Its
answer is a JSON value, printed as it is; `pages(...)`, a paginated answer:
with `--paginate --slurp` printed as one list of the pages, with `--paginate`
alone the pages one after another (as an old gh prints them), and without
either only the first page; or `reply(...)`, an exit code and output of its
own. A path with no route answers as GitHub does: `gh: Not Found (HTTP 404)`,
exit 1. `slurp=False` is a gh too old for `--slurp` (it refuses the flag);
`signed_in=False` one that isn't signed in (`auth status` and every `api` call
fail as gh does). Each call's arguments are logged, to read back with
`calls()` or `paths()`.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

TAG = "__fake_gh__"
# `gh api`'s flags that take a value: the path is the first argument after them.
WITH_VALUE = {"-f", "-F", "--field", "--raw-field", "-H", "--header", "-X", "--method", "-q", "--jq", "-t", "--template", "--input", "--hostname", "--cache"}


def pages(*values) -> dict:
    """A paginated answer: each value one page."""
    return {TAG: "pages", "pages": list(values)}


def reply(stdout: str = "", exit: int = 0, stderr: str = "") -> dict:
    """An answer with its own output and exit code."""
    return {TAG: "reply", "stdout": stdout, "exit": exit, "stderr": stderr}


SCRIPT = r'''#!{python}
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TAG = "__fake_gh__"
conf = json.loads((HERE / "fake-gh.json").read_text())
args = sys.argv[1:]
with open(HERE / "calls.jsonl", "a") as log:
    log.write(json.dumps(args) + "\n")


def fail(msg, code=1):
    sys.stderr.write(msg + "\n")
    sys.exit(code)


if args[:2] == ["auth", "status"]:
    if conf["signed_in"]:
        print("github.com\n  Logged in to github.com account fake (keyring)")
        sys.exit(0)
    fail("You are not logged into any GitHub hosts. To log in, run: gh auth login")
if not args or args[0] != "api":
    fail(f"fake gh: only `gh api` and `gh auth status` are faked, not {{args[:1]}}")
if not conf["signed_in"]:
    fail("To get started with GitHub CLI, please run:  gh auth login", 4)
if "--slurp" in args and not conf["slurp"]:
    fail("unknown flag: --slurp")
WITH_VALUE = set(conf["with_value"])
path, i = None, 1
while i < len(args):
    if args[i] in WITH_VALUE:
        i += 2
        continue
    if not args[i].startswith("-"):
        path = args[i]
        break
    i += 1
route = (path or "").split("?", 1)[0]
answer = conf["routes"].get(route)
if answer is None:
    fail("gh: Not Found (HTTP 404)")
if isinstance(answer, dict) and answer.get(TAG) == "reply":
    sys.stdout.write(answer["stdout"])
    sys.stderr.write(answer["stderr"])
    sys.exit(answer["exit"])
if isinstance(answer, dict) and answer.get(TAG) == "pages":
    if "--paginate" not in args:
        print(json.dumps(answer["pages"][0]))
    elif "--slurp" in args:
        print(json.dumps(answer["pages"]))
    else:
        sys.stdout.write("".join(json.dumps(p) for p in answer["pages"]) + "\n")
    sys.exit(0)
print(json.dumps(answer))
'''


class FakeGh:
    def __init__(self, bin_dir: Path):
        self.bin = bin_dir

    def calls(self) -> list[list[str]]:
        """Each call's arguments, in order."""
        log = self.bin / "calls.jsonl"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def paths(self) -> list[str]:
        """The path (or "graphql") each `api` call asked for, in order."""
        out = []
        for args in self.calls():
            if args[:1] != ["api"]:
                continue
            i, path = 1, ""
            while i < len(args):
                if args[i] in WITH_VALUE:
                    i += 2
                    continue
                if not args[i].startswith("-"):
                    path = args[i]
                    break
                i += 1
            out.append(path)
        return out


def install(tmp_path: Path, monkeypatch, routes: dict, slurp: bool = True, signed_in: bool = True) -> FakeGh:
    """Write the fake `gh` into a fresh directory and put it first on PATH."""
    bin_dir = tmp_path / "fake-gh-bin"
    bin_dir.mkdir()
    (bin_dir / "fake-gh.json").write_text(json.dumps({"routes": routes, "slurp": slurp, "signed_in": signed_in, "with_value": sorted(WITH_VALUE)}))
    gh = bin_dir / "gh"
    gh.write_text(SCRIPT.format(python=sys.executable))
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return FakeGh(bin_dir)


def without_gh(tmp_path: Path, monkeypatch, keep: tuple[str, ...] = ("git",)) -> Path:
    """A PATH with no `gh` on it: only links to the `keep` tools."""
    import shutil

    bin_dir = tmp_path / "no-gh-bin"
    bin_dir.mkdir()
    for tool in keep:
        found = shutil.which(tool)
        if found:
            (bin_dir / tool).symlink_to(found)
    monkeypatch.setenv("PATH", str(bin_dir))
    return bin_dir
