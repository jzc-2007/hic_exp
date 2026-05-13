from __future__ import annotations

from typing import Any
import json
import re
import sqlite3

from . import db
from .scheduler import iso


def channel_for_recipient(recipient: str) -> str:
    if recipient == "group":
        return "group"
    if recipient == "system":
        return "system"
    if recipient.startswith("direct:"):
        return recipient
    return f"direct:{recipient}"


def normalize_recipient(recipient: str) -> str:
    if recipient.startswith("direct:"):
        return recipient.split(":", 1)[1]
    return recipient


def normalize_priority(priority: int | str | None) -> int:
    try:
        value = int(priority or 1)
    except (TypeError, ValueError):
        value = 1
    return 2 if value >= 2 else 1


def _mention_alias_pattern(alias: str) -> str | None:
    parts = [part for part in re.split(r"[\s_-]+", (alias or "").strip().lower()) if part]
    if not parts:
        return None
    return r"@{}\b".format(r"[\s_-]*".join(re.escape(part) for part in parts))


def mentioned_agent_slugs(conn: sqlite3.Connection, body: str) -> set[str]:
    text = str(body or "")
    if "@" not in text:
        return set()
    lowered = text.lower()
    targets: set[str] = set()
    enabled_agents = db.list_agents(conn, enabled_only=True)
    if re.search(r"@all\b", lowered):
        return {str(row["slug"]) for row in enabled_agents}
    for row in enabled_agents:
        slug = str(row.get("slug") or "").strip()
        if not slug:
            continue
        aliases = {
            slug,
            slug.replace("_", " "),
            slug.replace("-", " "),
            str(row.get("display_name") or ""),
        }
        for alias in aliases:
            pattern = _mention_alias_pattern(alias)
            if not pattern:
                continue
            if re.search(pattern, lowered):
                targets.add(slug)
                break
    return targets


def send_message(
    conn: sqlite3.Connection,
    sender: str,
    recipient: str,
    body: str,
    priority: int = 1,
    wakes_recipient: bool = True,
) -> int:
    recipient = normalize_recipient(recipient.strip())
    priority_value = normalize_priority(priority)
    should_wake = bool(wakes_recipient) and priority_value >= 2
    pi_direct_reply = recipient == "pi" and sender not in ("pi", "group", "system")
    channel = f"direct:{sender}" if pi_direct_reply else channel_for_recipient(recipient)
    cur = conn.execute(
        """
        INSERT INTO messages(created_at, sender, recipient, channel, body, read_by, priority, wakes_recipient)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (iso(), sender, recipient, channel, body, "[]", priority_value, int(should_wake)),
    )
    message_id = int(cur.lastrowid)
    if should_wake:
        wake_targets: set[str] = set()
        mention_targets: set[str] = set()
        if recipient == "group":
            mention_targets = mentioned_agent_slugs(conn, body)
            wake_targets.update(mention_targets)
        elif recipient not in ("system", "pi", sender):
            wake_targets.add(recipient)
        for target in sorted(wake_targets):
            if target in ("system", "pi", sender):
                continue
            if recipient == "group" and target in mention_targets:
                reason = f"group mention message {message_id}"
            else:
                reason = f"group message {message_id}" if recipient == "group" else f"direct message {message_id}"
            create_wake_request(conn, target, sender, reason)
    db.insert_event(
        conn,
        "message_sent",
        sender,
        {
            "message_id": message_id,
            "recipient": recipient,
            "channel": channel,
            "priority": priority_value,
            "wakes_recipient": should_wake,
        },
    )
    conn.commit()
    return message_id


def list_messages(
    conn: sqlite3.Connection,
    channel: str | None = None,
    recipient: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if recipient and not channel:
        channel = channel_for_recipient(recipient)
    if channel:
        rows = conn.execute(
            "SELECT * FROM messages WHERE channel=? ORDER BY id DESC LIMIT ?",
            (channel, int(limit)),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM messages ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    return list(reversed(db.rows_to_dicts(rows)))


def recent_for_agent(conn: sqlite3.Connection, slug: str, limit: int = 40) -> dict[str, list[dict[str, Any]]]:
    return {
        "group": list_messages(conn, channel="group", limit=limit),
        "direct": list_messages(conn, channel=f"direct:{slug}", limit=limit),
    }


def mark_read(conn: sqlite3.Connection, message_id: int, slug: str) -> None:
    row = conn.execute("SELECT read_by FROM messages WHERE id=?", (message_id,)).fetchone()
    if not row:
        return
    try:
        read_by = json.loads(row["read_by"] or "[]")
    except json.JSONDecodeError:
        read_by = []
    if slug not in read_by:
        read_by.append(slug)
        conn.execute("UPDATE messages SET read_by=? WHERE id=?", (json.dumps(read_by), message_id))
        conn.commit()


def mark_channel_read(conn: sqlite3.Connection, channel: str, slug: str) -> None:
    for row in conn.execute("SELECT id FROM messages WHERE channel=?", (channel,)).fetchall():
        mark_read(conn, int(row["id"]), slug)


def create_wake_request(
    conn: sqlite3.Connection,
    target_agent: str,
    requested_by: str,
    reason: str,
    handled: bool = False,
) -> int:
    if not handled:
        existing = conn.execute(
            "SELECT id FROM wake_requests WHERE target_agent=? AND handled=0 ORDER BY id ASC LIMIT 1",
            (target_agent,),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE wake_requests SET created_at=?, requested_by=?, reason=? WHERE id=?",
                (iso(), requested_by, reason, int(existing["id"])),
            )
            conn.commit()
            return int(existing["id"])
    cur = conn.execute(
        """
        INSERT INTO wake_requests(created_at, target_agent, requested_by, reason, handled)
        VALUES (?, ?, ?, ?, ?)
        """,
        (iso(), target_agent, requested_by, reason, int(handled)),
    )
    conn.commit()
    return int(cur.lastrowid)


def pending_wake_requests(conn: sqlite3.Connection, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM wake_requests WHERE handled=0 ORDER BY id ASC LIMIT ?",
        (int(limit),),
    ).fetchall()
    return db.rows_to_dicts(rows)


def mark_wake_requests_handled(conn: sqlite3.Connection, target_agent: str) -> None:
    conn.execute("UPDATE wake_requests SET handled=1 WHERE target_agent=? AND handled=0", (target_agent,))
    conn.commit()


def mark_wake_requests_handled_by_ids(conn: sqlite3.Connection, wake_ids: list[int]) -> None:
    if not wake_ids:
        return
    placeholders = ",".join("?" for _ in wake_ids)
    conn.execute(f"UPDATE wake_requests SET handled=1 WHERE id IN ({placeholders})", tuple(int(item) for item in wake_ids))
    conn.commit()


def append_incident(root, title: str, body: str, task_id: int | None = None) -> None:
    from pathlib import Path

    path = Path(root) / "shared" / "INCIDENTS.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    task_text = f" task_id={task_id}" if task_id else ""
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {iso()} {title}{task_text}\n\n{body.strip()}\n")
