"""Telling the owner's words from agents'.

Every comment, issue and pull request an agent posts goes out under the owner's
GitHub account, so the author alone can't tell them apart. Every agent post
(the conductor's and ticket sessions') carries one marker, `AGENT_MARKER`; the
guard refuses an agent's post without it, and `owner_words` keeps the owner's
own comments: theirs, and without the marker.
"""

from __future__ import annotations

AGENT_MARKER = "<!-- workflow:agent -->"


def is_agent(body: str | None) -> bool:
    """The text carries the agents' marker."""
    return AGENT_MARKER in (body or "")


def _login(comment: dict) -> str:
    user = comment.get("user")
    if isinstance(user, dict):
        return str(user.get("login") or "")
    return str(user or comment.get("author") or "")


def owner_words(comments: list, owner: str, since_id: int | None = None) -> list[dict]:
    """The comments `owner` wrote themselves, oldest first: by that login (any
    case), without the marker, and with an id above `since_id` when given.

    Each is `{id, created_at, url, body}`; `url` is the comment's `html_url`
    (else its `url`). A comment that isn't an object, or has no whole-number
    id, is left out.
    """
    want = (owner or "").strip().lstrip("@").casefold()
    if not want:
        raise ValueError("give the owner's GitHub login")
    out: list[dict] = []
    for c in comments or []:
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        if not isinstance(cid, int) or isinstance(cid, bool):
            continue
        if since_id is not None and cid <= since_id:
            continue
        if _login(c).casefold() != want or is_agent(c.get("body")):
            continue
        out.append(
            {
                "id": cid,
                "created_at": c.get("created_at"),
                "url": c.get("html_url") or c.get("url"),
                "body": c.get("body") or "",
            }
        )
    return sorted(out, key=lambda x: x["id"])
