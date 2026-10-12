"""Telling the owner's words from agents'.

Every comment, issue and pull request an agent posts goes out under the owner's
GitHub account, so the author alone can't tell them apart. Every agent post
(the conductor's and ticket sessions') carries one marker, `AGENT_MARKER`; the
guard refuses an agent's post without it, and `owner_words` keeps the owner's
own comments: theirs, and without the marker.

Comments come in whatever shape the conductor fetched them in (`comments_from`):
- a plain list, as the REST API returns one page;
- a list of pages (`gh api --paginate --slurp`);
- several JSON arrays one after another in one file (`gh api --paginate`
  without `--slurp`), decoded one by one (`decode_values`);
- `{"comments": [...]}` (`gh issue view --json comments`) or a list of such
  comments (the GitHub MCP tools), with `author: {login}`, `createdAt`, `url`
  and node ids as strings ("IC_kw…"): the number is then read from the URL's
  `#issuecomment-<n>`.
"""

from __future__ import annotations

import json
import re

AGENT_MARKER = "<!-- workflow:agent -->"

_COMMENT_URL_ID = re.compile(r"#issuecomment-(\d+)\b")


class CommentsError(ValueError):
    """The comments aren't in a shape `comments_from` knows."""


def is_agent(body: str | None) -> bool:
    """The text carries the agents' marker."""
    return AGENT_MARKER in (body or "")


def decode_values(text: str) -> list:
    """Every JSON value in `text`, one after another (`[…][…]`, or one value).

    Raises CommentsError when the text isn't JSON."""
    dec, out, i = json.JSONDecoder(), [], 0
    text = text or ""
    while True:
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            return out
        try:
            value, i = dec.raw_decode(text, i)
        except json.JSONDecodeError as e:
            raise CommentsError(f"not JSON at line {e.lineno}, column {e.colno}: {e.msg}") from None
        out.append(value)


def _login(comment: dict) -> str:
    for key in ("user", "author"):
        who = comment.get(key)
        if isinstance(who, dict) and who.get("login"):
            return str(who["login"])
        if isinstance(who, str) and who:
            return who
    return ""


def _number(comment: dict) -> int | None:
    """The comment's id as a number: a whole-number `id`, an id of digits, or
    the `#issuecomment-<n>` of its URL (node ids such as "IC_kw…" aren't numbers)."""
    cid = comment.get("id")
    if isinstance(cid, int) and not isinstance(cid, bool):
        return cid
    if isinstance(cid, str) and re.fullmatch(r"[0-9]+", cid.strip()):
        return int(cid.strip())
    for key in ("html_url", "url"):
        m = _COMMENT_URL_ID.search(str(comment.get(key) or ""))
        if m:
            return int(m.group(1))
    return None


def _is_comment(d: dict) -> bool:
    # An issue or PR (`gh issue view --json body,comments,url`) has a body and a
    # URL too; its `comments` list, or its `number`, says it isn't a comment.
    return "body" in d and any(k in d for k in ("id", "url", "html_url")) and not isinstance(d.get("comments"), list) and "number" not in d


def comments_from(value) -> list[dict]:
    """The comment objects in any shape the conductor may have fetched (see the
    module's docstring). Raises CommentsError, saying what it found, for
    anything else."""
    out: list[dict] = []

    def walk(v, where: str) -> None:
        if isinstance(v, list):
            for k, x in enumerate(v):
                walk(x, f"{where}[{k}]")
        elif isinstance(v, dict):
            if _is_comment(v):
                if not isinstance(v["body"], (str, type(None))):
                    raise CommentsError(f"{where}.body is a {type(v['body']).__name__}, not text")
                out.append(v)
            elif isinstance(v.get("comments"), list):
                walk(v["comments"], f"{where}.comments")
            else:
                keys = ", ".join(sorted(map(str, v))[:6]) or "no keys"
                raise CommentsError(f"{where} is an object that isn't a comment or a list of them (its keys: {keys})")
        else:
            raise CommentsError(f"{where} is a {type(v).__name__}, not a comment or a list of them")

    walk(value, "the JSON")
    return out


def load_comments(text: str) -> list[dict]:
    """The comments in a file's text: one JSON value, or several in a row."""
    values = decode_values(text)
    if not values:
        raise CommentsError("the file is empty")
    return comments_from(values[0] if len(values) == 1 else values)


def owner_words(comments, owner: str, since_id: int | None = None) -> list[dict]:
    """The comments `owner` wrote themselves, oldest first: by that login (any
    case), without the marker, and numbered above `since_id` when given.

    `comments` is any shape `comments_from` reads. Each result is
    `{id, created_at, url, body}`: `id` is the comment's number, compared as a
    number; `url` its `html_url` (else its `url`). A comment whose number can't
    be read is an error (CommentsError), never left out silently.
    """
    want = (owner or "").strip().lstrip("@").casefold()
    if not want:
        raise ValueError("give the owner's GitHub login")
    out: dict[int, dict] = {}
    for c in comments_from(comments):
        cid = _number(c)
        if cid is None:
            raise CommentsError(f"a comment has no number: its id is {c.get('id')!r} and its URL has no #issuecomment-<n>")
        if since_id is not None and cid <= since_id:
            continue
        if _login(c).casefold() != want or is_agent(c.get("body")):
            continue
        out[cid] = {
            "id": cid,
            "created_at": c.get("created_at") or c.get("createdAt"),
            "url": c.get("html_url") or c.get("url"),
            "body": c.get("body") or "",
        }
    return [out[k] for k in sorted(out)]
