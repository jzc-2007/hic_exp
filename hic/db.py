from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import json
import sqlite3

from .config import AgentConfig, root_path
from .scheduler import iso


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS agents (
  slug TEXT PRIMARY KEY,
  display_name TEXT,
  role TEXT,
  enabled INTEGER,
  created_at TEXT,
  last_wake_at TEXT,
  next_wake_at TEXT,
  status_summary TEXT,
  current_task TEXT,
  heartbeat_at TEXT
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT,
  sender TEXT,
  recipient TEXT,
  channel TEXT,
  body TEXT,
  read_by TEXT,
  priority INTEGER,
  wakes_recipient INTEGER
);
CREATE TABLE IF NOT EXISTS attachments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT,
  message_id INTEGER,
  filename TEXT,
  stored_path TEXT,
  content_type TEXT,
  size INTEGER,
  FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT,
  updated_at TEXT,
  title TEXT,
  description TEXT,
  owner TEXT,
  status TEXT,
  priority INTEGER,
  parent_task_id INTEGER
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT,
  type TEXT,
  actor TEXT,
  payload TEXT
);
CREATE TABLE IF NOT EXISTS wake_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT,
  target_agent TEXT,
  requested_by TEXT,
  reason TEXT,
  handled INTEGER
);
CREATE TABLE IF NOT EXISTS system_state (
  key TEXT PRIMARY KEY,
  value TEXT,
  updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_channel_created ON messages(channel, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_recipient_created ON messages(recipient, created_at);
CREATE INDEX IF NOT EXISTS idx_attachments_message ON attachments(message_id);
CREATE INDEX IF NOT EXISTS idx_tasks_owner_status ON tasks(owner, status);
CREATE INDEX IF NOT EXISTS idx_wake_requests_handled ON wake_requests(handled, target_agent);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
"""


REQUIRED_TABLES = {"agents", "messages", "attachments", "tasks", "events", "wake_requests"}


def db_path(root: Path | str | None = None) -> Path:
    return root_path(root) / "var" / "hic.sqlite3"


def connect(path: Path | str | None = None, root: Path | str | None = None) -> sqlite3.Connection:
    if path is None:
        path = db_path(root)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def initialize(root: Path | str | None = None, agents: list[AgentConfig] | None = None) -> None:
    conn = connect(root=root)
    try:
        init_db(conn)
        if agents:
            upsert_agents(conn, agents)
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def schema_valid(conn: sqlite3.Connection) -> tuple[bool, list[str]]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    found = {row["name"] for row in rows}
    missing = sorted(REQUIRED_TABLES - found)
    return not missing, missing


def upsert_agents(conn: sqlite3.Connection, agents: list[AgentConfig]) -> None:
    now = iso()
    for agent in agents:
        existing = conn.execute("SELECT slug FROM agents WHERE slug=?", (agent.slug,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE agents
                SET display_name=?, role=?, enabled=?
                WHERE slug=?
                """,
                (agent.display_name, agent.role, int(agent.enabled), agent.slug),
            )
        else:
            conn.execute(
                """
                INSERT INTO agents (
                  slug, display_name, role, enabled, created_at, last_wake_at,
                  next_wake_at, status_summary, current_task, heartbeat_at
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, NULL)
                """,
                (
                    agent.slug,
                    agent.display_name,
                    agent.role,
                    int(agent.enabled),
                    now,
                    now,
                    "Initialized.",
                    "Awaiting first wake.",
                ),
            )
    conn.commit()


def list_agents(conn: sqlite3.Connection, enabled_only: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM agents"
    params: tuple[Any, ...] = ()
    if enabled_only:
        sql += " WHERE enabled=1"
    sql += " ORDER BY CASE slug WHEN 'main' THEN 0 WHEN 'self_evolver' THEN 1 ELSE 2 END, slug"
    return rows_to_dicts(conn.execute(sql, params).fetchall())


def get_agent(conn: sqlite3.Connection, slug: str) -> dict[str, Any] | None:
    return row_to_dict(conn.execute("SELECT * FROM agents WHERE slug=?", (slug,)).fetchone())


def update_agent_status(
    conn: sqlite3.Connection,
    slug: str,
    status_summary: str,
    current_task: str,
    last_wake_at: str,
    next_wake_at: str,
    heartbeat_at: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE agents
        SET status_summary=?, current_task=?, last_wake_at=?, next_wake_at=?,
            heartbeat_at=COALESCE(?, heartbeat_at)
        WHERE slug=?
        """,
        (status_summary, current_task, last_wake_at, next_wake_at, heartbeat_at, slug),
    )
    conn.commit()


def set_agent_heartbeat(conn: sqlite3.Connection, slug: str, when: str | None = None) -> None:
    conn.execute("UPDATE agents SET heartbeat_at=? WHERE slug=?", (when or iso(), slug))
    conn.commit()


def set_agent_enabled(conn: sqlite3.Connection, slug: str, enabled: bool) -> None:
    conn.execute("UPDATE agents SET enabled=? WHERE slug=?", (int(enabled), slug))
    conn.commit()


def insert_event(conn: sqlite3.Connection, type_: str, actor: str, payload: dict[str, Any] | str | None = None) -> int:
    if isinstance(payload, str):
        encoded = payload
    else:
        encoded = json.dumps(payload or {}, ensure_ascii=True, sort_keys=True)
    cur = conn.execute(
        "INSERT INTO events(created_at, type, actor, payload) VALUES (?, ?, ?, ?)",
        (iso(), type_, actor, encoded),
    )
    conn.commit()
    return int(cur.lastrowid)


def add_attachment(
    conn: sqlite3.Connection,
    message_id: int,
    filename: str,
    stored_path: str,
    content_type: str = "",
    size: int = 0,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO attachments(created_at, message_id, filename, stored_path, content_type, size)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (iso(), int(message_id), filename, stored_path, content_type, int(size)),
    )
    conn.commit()
    return int(cur.lastrowid)


def update_message_body(conn: sqlite3.Connection, message_id: int, body: str) -> None:
    conn.execute("UPDATE messages SET body=? WHERE id=?", (body, int(message_id)))
    conn.commit()


def get_attachment(conn: sqlite3.Connection, attachment_id: int) -> dict[str, Any] | None:
    return row_to_dict(conn.execute("SELECT * FROM attachments WHERE id=?", (int(attachment_id),)).fetchone())


def list_attachments(conn: sqlite3.Connection, message_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    if not message_ids:
        return {}
    placeholders = ",".join("?" for _ in message_ids)
    rows = conn.execute(
        f"SELECT * FROM attachments WHERE message_id IN ({placeholders}) ORDER BY id",
        tuple(int(mid) for mid in message_ids),
    ).fetchall()
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows_to_dicts(rows):
        grouped.setdefault(int(row["message_id"]), []).append(row)
    return grouped


def wake_requests_for_message(conn: sqlite3.Connection, message_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM wake_requests WHERE reason LIKE ? ORDER BY id",
        (f"%message {int(message_id)}%",),
    ).fetchall()
    return rows_to_dicts(rows)


def set_state(conn: sqlite3.Connection, key: str, value: Any) -> None:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True)
    conn.execute(
        """
        INSERT INTO system_state(key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (key, encoded, iso()),
    )
    conn.commit()


def get_state(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute("SELECT value FROM system_state WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except json.JSONDecodeError:
        return default


def create_task(
    conn: sqlite3.Connection,
    title: str,
    description: str = "",
    owner: str = "main",
    status: str = "open",
    priority: int = 1,
    parent_task_id: int | None = None,
) -> int:
    now = iso()
    try:
        priority_value = 2 if int(priority) >= 2 else 1
    except (TypeError, ValueError):
        priority_value = 1
    cur = conn.execute(
        """
        INSERT INTO tasks(created_at, updated_at, title, description, owner, status, priority, parent_task_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (now, now, title, description, owner, status, priority_value, parent_task_id),
    )
    conn.commit()
    return int(cur.lastrowid)


def update_task(
    conn: sqlite3.Connection,
    task_id: int,
    status: str | None = None,
    owner: str | None = None,
    note: str | None = None,
) -> None:
    row = conn.execute("SELECT description FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise KeyError(task_id)
    description = row["description"] or ""
    if note:
        description = f"{description}\n\n[{iso()}] {note}".strip()
    if status is None and owner is None and not note:
        return
    conn.execute(
        """
        UPDATE tasks
        SET status=COALESCE(?, status), owner=COALESCE(?, owner), description=?, updated_at=?
        WHERE id=?
        """,
        (status, owner, description, iso(), task_id),
    )
    conn.commit()


def list_tasks(
    conn: sqlite3.Connection,
    owner: str | None = None,
    status: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM tasks WHERE 1=1"
    params: list[Any] = []
    if owner:
        sql += " AND owner=?"
        params.append(owner)
    if status:
        sql += " AND status=?"
        params.append(status)
    sql += " ORDER BY CASE status WHEN 'done' THEN 1 ELSE 0 END, priority DESC, updated_at DESC LIMIT ?"
    params.append(limit)
    return rows_to_dicts(conn.execute(sql, tuple(params)).fetchall())
