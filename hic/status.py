from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import json
import os
import re
import socket
import subprocess
import time

from . import db
from .config import load_agents, load_settings, root_path
from .scheduler import is_overdue, now_utc, parse_iso


def tail_file(path: Path, lines: int = 200, max_bytes: int = 200000) -> str:
    if not path.exists():
        return ""
    size = path.stat().st_size
    with path.open("rb") as fh:
        if size > max_bytes:
            fh.seek(max(0, size - max_bytes))
        data = fh.read()
    text = data.decode("utf-8", errors="replace")
    return "\n".join(text.splitlines()[-lines:])


LOG_RE = re.compile(r"^(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}) (?P<level>[A-Z]+) (?P<body>.*)$")
FLASK_ACCESS_RE = re.compile(
    r'^(?P<host>\S+) - - \[(?P<ts>[^\]]+)\] "(?P<method>\S+) (?P<path>\S+) [^"]*" (?P<status>\d+)'
)
AGENT_RESULT_RE = re.compile(r"<AGENT_RESULT_JSON>\s*(\{.*?\})\s*</AGENT_RESULT_JSON>", re.S)


def parse_log_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = parse_iso(value)
    if parsed:
        return parsed.astimezone(timezone.utc)
    for fmt in ("%Y-%m-%d %H:%M:%S,%f", "%d/%b/%Y %H:%M:%S"):
        try:
            return datetime.strptime(value.split(" +", 1)[0], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def relative_time(value: str | datetime | None) -> str:
    dt = value if isinstance(value, datetime) else parse_log_datetime(str(value or ""))
    if not dt:
        return "-"
    now = now_utc()
    delta = dt - now
    future = delta.total_seconds() > 0
    seconds = abs(int(delta.total_seconds()))
    if seconds < 45:
        text = "just now" if not future else "in a moment"
    elif seconds < 3600:
        minutes = max(1, round(seconds / 60))
        text = f"{minutes}m"
    elif seconds < 86400:
        hours = max(1, round(seconds / 3600))
        text = f"{hours}h"
    else:
        days = max(1, round(seconds / 86400))
        text = f"{days}d"
    if text.startswith(("just", "in a moment")):
        return text
    return f"in {text}" if future else f"{text} ago"


def duration_label(seconds: int | float | None) -> str:
    total = max(0, int(seconds or 0))
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m"
    return f"{total // 3600}h {(total % 3600) // 60}m"


def _card(
    title: str,
    detail: str,
    raw: str,
    *,
    tone: str = "info",
    when: str = "",
    level: str = "",
) -> dict[str, str]:
    return {
        "title": title,
        "detail": detail,
        "raw": raw,
        "tone": tone,
        "when": when,
        "when_label": relative_time(when) if when else "",
        "level": level,
    }


def _system_log_card(line: str) -> dict[str, str]:
    match = LOG_RE.match(line)
    if match:
        when = match.group("ts")
        level = match.group("level")
        body = match.group("body")
        tone = "bad" if level == "ERROR" else "warn" if level == "WARNING" else "ok" if "complete" in body else "info"
        wake = re.search(r"agent (\S+) wake complete mode=(\S+) next=(\S+)", body)
        if wake:
            agent, mode, next_wake = wake.groups()
            return _card(
                f"{agent} completed a wake",
                f"Runner: {mode}. Next wake: {relative_time(next_wake)}.",
                line,
                tone="ok",
                when=when,
                level=level,
            )
        if "HIC daemon starting" in body:
            return _card("Daemon started", body, line, tone="ok", when=when, level=level)
        if "HIC daemon stopping" in body:
            return _card("Daemon stopped", body, line, tone="warn", when=when, level=level)
        if "result parse warning" in body:
            return _card("Agent output needed parser fallback", body, line, tone="warn", when=when, level=level)
        if "wake failed" in body:
            return _card("Agent wake failed", body, line, tone="bad", when=when, level=level)
        return _card(level.title(), body, line, tone=tone, when=when, level=level)

    flask = FLASK_ACCESS_RE.match(line)
    if flask:
        status = int(flask.group("status"))
        method = flask.group("method")
        path = flask.group("path")
        tone = "bad" if status >= 500 else "warn" if status >= 400 else "ok"
        return _card(
            f"{method} {path}",
            f"HTTP {status}",
            line,
            tone=tone,
            when=flask.group("ts"),
            level="HTTP",
        )

    if line.startswith(" * Running on "):
        return _card("Web server listening", line.replace(" * ", ""), line, tone="ok")
    if line.startswith("WARNING:"):
        return _card("Runtime warning", line, line, tone="warn", level="WARNING")
    if line.startswith(" * Serving Flask app"):
        return _card("Web app started", line.replace(" * ", ""), line, tone="ok")
    return _card("Log line", line, line)


def _compact_text(value: str, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _agent_log_cards(content: str) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    structured_events = 0
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("[hic runner started_at="):
            when = stripped[len("[hic runner started_at=") :].rstrip("]")
            cards.append(_card("Wake started", "Codex runner started.", stripped, tone="ok", when=when, level="runner"))
            continue
        if stripped.startswith("[hic runner command="):
            command = stripped[len("[hic runner command=") :].rstrip("]")
            cards.append(_card("Runner command", _compact_text(command, 180), command, tone="info", level="runner"))
            continue
        if not stripped.startswith("{"):
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        structured_events += 1
        event_type = str(event.get("type") or "").lower()
        if event_type == "thread.started":
            thread_id = str(event.get("thread_id") or "").strip()
            cards.append(
                _card(
                    "Session resumed",
                    _compact_text(thread_id, 90) if thread_id else "Persistent session resumed.",
                    json.dumps(event, indent=2, ensure_ascii=False),
                    tone="ok",
                    level="session",
                )
            )
            continue
        if event_type == "turn.started":
            cards.append(_card("Turn started", "Agent turn is running.", json.dumps(event, indent=2, ensure_ascii=False), level="turn"))
            continue
        if event_type == "turn.completed":
            usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
            input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
            total_tokens = int(usage.get("total_tokens") or (input_tokens + output_tokens))
            detail = (
                f"Input {input_tokens:,}, output {output_tokens:,}, total {total_tokens:,} tokens."
                if (input_tokens or output_tokens or total_tokens)
                else "Turn completed."
            )
            cards.append(_card("Token usage", detail, json.dumps(event, indent=2, ensure_ascii=False), tone="ok", level="usage"))
            continue
        if event_type == "turn.failed":
            error = event.get("error")
            cards.append(_card("Turn failed", _compact_text(json.dumps(error, ensure_ascii=False) if error else "Unknown error."), json.dumps(event, indent=2, ensure_ascii=False), tone="bad", level="error"))
            continue
        if event_type != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").lower()
        raw_item = json.dumps(item, indent=2, ensure_ascii=False)
        if item_type == "agent_message":
            text = str(item.get("text") or "").strip()
            if text:
                cards.append(_card("Agent update", _compact_text(text), text, tone="ok", level="message"))
            continue
        if item_type == "command_execution":
            command = _compact_text(str(item.get("command") or ""), 180)
            exit_code = item.get("exit_code")
            status = str(item.get("status") or "")
            tone = "ok" if exit_code in (0, None) else "bad"
            detail = f"{command} | exit {exit_code if exit_code is not None else status or '?'}"
            cards.append(_card("Command finished", detail, raw_item, tone=tone, level="command"))
            continue
        if item_type == "file_change":
            changes = item.get("changes") if isinstance(item.get("changes"), list) else []
            summary = []
            for change in changes[:5]:
                if not isinstance(change, dict):
                    continue
                kind = str(change.get("kind") or "update")
                path = str(change.get("path") or "")
                summary.append(f"{kind} {path}".strip())
            detail = ", ".join(summary) if summary else "File changes applied."
            cards.append(_card("Files updated", _compact_text(detail), raw_item, tone="ok", level="files"))
            continue
        if item_type == "error":
            message = str(item.get("message") or "Codex reported an item-level error.")
            cards.append(_card("Runner item error", _compact_text(message), raw_item, tone="warn", level="error"))

    match = AGENT_RESULT_RE.search(content)
    if match:
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            cards.append(_card("Agent result JSON parse warning", str(exc), match.group(0), tone="warn"))
        else:
            status_summary = str(data.get("status_summary") or "Wake completed.")
            current_task = str(data.get("current_task") or "").strip()
            cards.append(
                _card(
                    "Agent reported a result",
                    status_summary,
                    json.dumps(data, indent=2, ensure_ascii=False),
                    tone="ok",
                    level="result",
                )
            )
            if current_task:
                cards.append(
                    _card(
                        "Current work",
                        _compact_text(current_task),
                        json.dumps(data, indent=2, ensure_ascii=False),
                        tone="info",
                        level="result",
                    )
                )
            cards.append(
                _card(
                    "Final result",
                    status_summary,
                    json.dumps(data, indent=2, ensure_ascii=False),
                    tone="ok",
                    level="result",
                )
            )
    if structured_events == 0 and content.strip():
        cards.append(_card("Agent log captured", "No structured runner events found.", content[:3000], tone="warn"))

    notable = []
    for line in content.splitlines():
        if any(marker in line.lower() for marker in ("error", "failed", "warning", "warn", "traceback")):
            notable.append(line)
    if notable:
        cards.append(_card("Technical warnings", "\n".join(notable[-8:]), "\n".join(notable[-40:]), tone="warn"))
    return cards


def human_log_view(path: Path, target: str, content: str) -> dict[str, Any]:
    if target.startswith("agent:"):
        cards = _agent_log_cards(content)
    else:
        cards = [_system_log_card(line) for line in content.splitlines() if line.strip()]
    cards = cards[-80:]
    problem_count = sum(1 for card in cards if card["tone"] in {"bad", "warn"})
    return {
        "cards": cards,
        "problem_count": problem_count,
        "event_count": len(cards),
        "raw": content,
        "path": str(path),
    }


def tmux_session_exists(name: str) -> bool:
    proc = subprocess.run(
        ["tmux", "has-session", "-t", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode == 0


def agent_lock_active(root: Path | str, slug: str, stale_seconds: int = 6 * 3600) -> bool:
    path = root_path(root) / "var" / "locks" / f"{slug}.lock"
    if not path.exists():
        return False
    try:
        age = time.time() - path.stat().st_mtime
        pid = int(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        return False
    if age > stale_seconds or pid <= 0:
        path.unlink(missing_ok=True)
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        path.unlink(missing_ok=True)
        return False
    except PermissionError:
        return True
    return True


def port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def daemon_alive(conn, settings: dict[str, Any]) -> bool:
    heartbeat = db.get_state(conn, "daemon_heartbeat")
    if not heartbeat:
        return False
    at = parse_iso(heartbeat.get("at") if isinstance(heartbeat, dict) else None)
    if not at:
        return False
    stale_minutes = int(settings.get("daemon", {}).get("stale_heartbeat_minutes") or 5)
    return at + timedelta(minutes=stale_minutes) >= now_utc()


def db_health(root: Path | str | None = None) -> dict[str, Any]:
    root = root_path(root)
    conn = db.connect(root=root)
    try:
        valid, missing = db.schema_valid(conn)
        return {"ok": valid, "missing_tables": missing, "path": str(db.db_path(root))}
    finally:
        conn.close()


def system_snapshot(root: Path | str | None = None) -> dict[str, Any]:
    root = root_path(root)
    settings = load_settings(root)
    web_settings = dict(settings.get("web", {}))
    run_port = root / "var" / "run" / "web_port"
    if run_port.exists():
        try:
            web_settings["port"] = int(run_port.read_text(encoding="utf-8").strip())
        except ValueError:
            pass
    if os.environ.get("HIC_WEB_PORT"):
        web_settings["port"] = int(os.environ["HIC_WEB_PORT"])
    if os.environ.get("HIC_WEB_HOST"):
        web_settings["host"] = os.environ["HIC_WEB_HOST"]
    conn = db.connect(root=root)
    try:
        agents = db.list_agents(conn)
        pending_rows = conn.execute("SELECT target_agent, COUNT(*) AS count FROM wake_requests WHERE handled=0 GROUP BY target_agent").fetchall()
        pending_by_agent = {row["target_agent"]: int(row["count"]) for row in pending_rows}
        stale_minutes = int(settings.get("daemon", {}).get("stale_heartbeat_minutes") or 5)
        current_now = now_utc()
        for agent in agents:
            lock = root / "var" / "locks" / f"{agent['slug']}.lock"
            agent["running"] = agent_lock_active(root, str(agent["slug"]))
            agent["running_for_seconds"] = int(time.time() - lock.stat().st_mtime) if agent["running"] and lock.exists() else 0
            agent["running_for_label"] = duration_label(agent["running_for_seconds"])
            agent["pending_wakes"] = pending_by_agent.get(agent["slug"], 0)
            heartbeat_at = parse_iso(agent.get("heartbeat_at"))
            last_wake_at = parse_iso(agent.get("last_wake_at"))
            freshest = heartbeat_at if heartbeat_at and (not last_wake_at or heartbeat_at >= last_wake_at) else last_wake_at
            recent_awake = bool(freshest and freshest + timedelta(minutes=stale_minutes) >= current_now)
            needs_input = str(agent.get("current_task") or "").strip().lower() == "waiting for pi input."
            if not agent.get("enabled"):
                agent["activity_label"] = "disabled"
                agent["activity_tone"] = "bad"
                agent["activity_detail"] = "agent is disabled"
            elif agent["running"]:
                agent["activity_label"] = f"working {agent['running_for_label']}"
                agent["activity_tone"] = "ok"
                agent["activity_detail"] = "reading messages or doing assigned work"
            elif agent["pending_wakes"]:
                agent["activity_label"] = "wake queued"
                agent["activity_tone"] = "warn"
                agent["activity_detail"] = "waiting for the daemon to start this agent"
            elif needs_input:
                agent["activity_label"] = "needs input"
                agent["activity_tone"] = "warn"
                agent["activity_detail"] = "agent is waiting for PI to answer a question"
            elif recent_awake:
                agent["activity_label"] = "awake recently"
                agent["activity_tone"] = "ok"
                agent["activity_detail"] = f"last activity {relative_time(freshest)}" if freshest else "recent activity"
            else:
                agent["activity_label"] = "sleeping"
                agent["activity_tone"] = "idle"
                agent["activity_detail"] = "no recent wake activity"
        tasks = db.list_tasks(conn, limit=100)
        overdue = [row["slug"] for row in agents if row.get("enabled") and is_overdue(row)]
        return {
            "root": str(root),
            "agents": agents,
            "tasks": tasks,
            "overdue_agents": overdue,
            "daemon_tmux": tmux_session_exists("hic_daemon"),
            "web_tmux": tmux_session_exists("hic_web"),
            "daemon_alive": daemon_alive(conn, settings),
            "runner_mode": "real" if os.environ.get("HIC_CODEX_CMD") or settings.get("runner", {}).get("codex_cmd") else "mock",
            "web": web_settings,
            "db": db_health(root),
        }
    finally:
        conn.close()
