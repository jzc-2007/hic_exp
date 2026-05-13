from __future__ import annotations

from pathlib import Path
import argparse
import logging
import os
import signal
import sys
import threading
import time
import traceback

from . import db
from .codex_runner import CodexRunner, append_progress
from .config import AgentConfig, ensure_project_structure, load_agents, load_settings, write_status_file
from .message_bus import (
    mark_read,
    mark_wake_requests_handled_by_ids,
    pending_wake_requests,
    send_message,
)
from .scheduler import is_due, iso, next_wake_from_minutes, now_utc, parse_iso, unique_ordered


STOP = False
IN_FLIGHT_WAKES: set[str] = set()
IN_FLIGHT_WAKES_LOCK = threading.Lock()


def configure_logging(root: Path) -> None:
    log_path = root / "var" / "daemon.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler(sys.stdout)],
    )


def handle_signal(signum, frame) -> None:  # noqa: ARG001
    global STOP
    STOP = True


class AgentLock:
    def __init__(self, root: Path, slug: str, stale_seconds: int = 6 * 3600):
        self.path = root / "var" / "locks" / f"{slug}.lock"
        self.stale_seconds = stale_seconds
        self.fd: int | None = None

    def __enter__(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            age = time.time() - self.path.stat().st_mtime
            if age > self.stale_seconds or not lock_owner_alive(self.path):
                self.path.unlink(missing_ok=True)
        try:
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self.fd, str(os.getpid()).encode("ascii"))
            return True
        except FileExistsError:
            return False

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        if self.fd is not None:
            os.close(self.fd)
            self.path.unlink(missing_ok=True)


def lock_is_active(root: Path, slug: str, stale_seconds: int = 6 * 3600) -> bool:
    path = root / "var" / "locks" / f"{slug}.lock"
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    if age > stale_seconds or not lock_owner_alive(path):
        path.unlink(missing_ok=True)
        return False
    return True


def lock_owner_alive(path: Path) -> bool:
    try:
        pid = int(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def sync_state(root: Path) -> tuple[list[AgentConfig], dict]:
    ensure_project_structure(root)
    settings = load_settings(root)
    agents = load_agents(root)
    conn = db.connect(root=root)
    try:
        db.init_db(conn)
        db.upsert_agents(conn, agents)
    finally:
        conn.close()
    return agents, settings


def choose_due_agents(root: Path, configured_agents: list[AgentConfig], conn) -> list[str]:
    agent_by_slug = {agent.slug: agent for agent in configured_agents if agent.enabled}
    requested = [row["target_agent"] for row in pending_wake_requests(conn)]
    rows = db.list_agents(conn, enabled_only=True)
    due = [row["slug"] for row in rows if is_due(row.get("next_wake_at"))]
    return [slug for slug in unique_ordered(requested + due) if slug in agent_by_slug]


def latest_pi_message(messages: list[dict]) -> tuple[object, dict] | None:
    latest = None
    for msg in messages:
        if str(msg.get("sender") or "") != "pi":
            continue
        created_at = parse_iso(str(msg.get("created_at") or ""))
        if not created_at:
            continue
        if latest is None or created_at > latest[0]:
            latest = (created_at, msg)
    return latest


def route_agent_reply_recipient(recipient: str, group_messages: list[dict], direct_messages: list[dict]) -> str:
    normalized = str(recipient or "group").strip() or "group"
    if normalized not in {"pi", "direct:pi"}:
        return normalized
    latest_group = latest_pi_message(group_messages)
    latest_direct = latest_pi_message(direct_messages)
    if latest_group and (not latest_direct or latest_group[0] >= latest_direct[0]):
        return "group"
    return normalized


def run_agent_once(root: Path, agent: AgentConfig, settings: dict, reason: str = "scheduled") -> bool:
    with AgentLock(root, agent.slug) as acquired:
        if not acquired:
            logging.info("agent %s already locked; skipping", agent.slug)
            return False
        conn = db.connect(root=root)
        try:
            db.set_agent_heartbeat(conn, agent.slug)
            wake_ids_to_handle = [
                int(row["id"]) for row in pending_wake_requests(conn) if row.get("target_agent") == agent.slug
            ]
            mark_wake_requests_handled_by_ids(conn, wake_ids_to_handle)
            recent = __import__("hic.message_bus", fromlist=["recent_for_agent"]).recent_for_agent(conn, agent.slug)
            for msg in recent["group"] + recent["direct"]:
                if msg.get("id"):
                    mark_read(conn, int(msg["id"]), agent.slug)
            tasks = db.list_tasks(conn, owner=agent.slug, limit=100)
            mainish = db.list_tasks(conn, owner="main", limit=100) if agent.slug == "main" else []
            open_tasks = db.list_tasks(conn, status="open", limit=100)
            task_map = {task["id"]: task for task in tasks + mainish + open_tasks}
            active_tasks = [task for task in task_map.values() if task.get("status") != "done"]
            runner = CodexRunner(root, settings)
            result = runner.run(agent, recent["group"], recent["direct"], list(task_map.values()))
            parsed = result.parsed
            max_minutes = int(settings.get("daemon", {}).get("max_sleep_minutes") or 240)
            default_minutes = int(settings.get("runner", {}).get("default_next_wake_minutes") or 240)
            idle_minutes = int(settings.get("runner", {}).get("idle_next_wake_minutes") or 240)
            requested_next = parsed.get("next_wake_minutes")
            if not active_tasks:
                try:
                    if requested_next is None or int(requested_next) < idle_minutes:
                        requested_next = idle_minutes
                except (TypeError, ValueError):
                    requested_next = idle_minutes
            last_wake = iso(now_utc())
            next_wake = next_wake_from_minutes(
                requested_next,
                default_minutes=default_minutes,
                max_minutes=max_minutes,
            )
            status_summary = str(parsed.get("status_summary") or "Wake complete.")
            current_task = str(parsed.get("current_task") or "Reviewing messages and deciding whether work is needed.")
            db.update_agent_status(
                conn,
                agent.slug,
                status_summary,
                current_task,
                last_wake,
                next_wake,
                heartbeat_at=last_wake,
            )
            write_status_file(
                agent.slug,
                current_task,
                status_summary,
                last_wake_at=last_wake,
                next_wake_at=next_wake,
                root=root,
            )
            append_progress(root, agent.slug, status_summary, result.mode, result.log_path)
            db.insert_event(
                conn,
                "agent_status",
                agent.slug,
                {
                    "status_summary": status_summary,
                    "current_task": current_task,
                    "active_tasks": len(active_tasks),
                    "next_wake_at": next_wake,
                },
            )
            for msg in parsed.get("messages_to_send") or []:
                if not isinstance(msg, dict):
                    continue
                body = str(msg.get("body") or "").strip()
                requested_recipient = str(msg.get("recipient") or "group").strip()
                recipient = route_agent_reply_recipient(requested_recipient, recent["group"], recent["direct"])
                if body:
                    if recipient != requested_recipient:
                        db.insert_event(
                            conn,
                            "agent_reply_rerouted",
                            agent.slug,
                            {
                                "from": requested_recipient,
                                "to": recipient,
                                "reason": "latest PI prompt was in group chat",
                                "body": body[:500],
                            },
                        )
                    send_message(
                        conn,
                        sender=agent.slug,
                        recipient=recipient,
                        body=body,
                        priority=int(msg.get("priority") or 1),
                        wakes_recipient=bool(msg.get("wakes_recipient", True)),
                    )
            for wake in parsed.get("wake_requests") or []:
                if not isinstance(wake, dict):
                    continue
                target = str(wake.get("target_agent") or "").strip()
                if target:
                    from .message_bus import create_wake_request

                    create_wake_request(conn, target, agent.slug, str(wake.get("reason") or "agent requested wake"))
            for update in parsed.get("tasks_to_update") or []:
                if not isinstance(update, dict) or not update.get("task_id"):
                    continue
                try:
                    db.update_task(
                        conn,
                        int(update["task_id"]),
                        status=update.get("status"),
                        owner=update.get("owner"),
                        note=update.get("note"),
                    )
                except Exception as exc:
                    logging.warning("task update failed for agent %s: %s", agent.slug, exc)
            mark_wake_requests_handled_by_ids(conn, wake_ids_to_handle)
            db.insert_event(
                conn,
                "agent_wake",
                agent.slug,
                {
                    "reason": reason,
                    "mode": result.mode,
                    "parse_error": result.parse_error,
                    "next_wake_at": next_wake,
                    "log_path": str(result.log_path) if result.log_path else None,
                },
            )
            if result.parse_error:
                logging.warning("agent %s result parse warning: %s", agent.slug, result.parse_error)
            logging.info("agent %s wake complete mode=%s next=%s", agent.slug, result.mode, next_wake)
            return True
        except Exception:
            logging.error("agent %s wake failed:\n%s", agent.slug, traceback.format_exc())
            retry = next_wake_from_minutes(settings.get("daemon", {}).get("retry_minutes") or 15)
            try:
                db.update_agent_status(
                    conn,
                    agent.slug,
                    "Wake failed; retry scheduled.",
                    "Recovering from wake failure.",
                    iso(),
                    retry,
                    heartbeat_at=iso(),
                )
                db.insert_event(conn, "agent_wake_failed", agent.slug, {"traceback": traceback.format_exc()[-4000:]})
            except Exception:
                logging.error("failed to record agent failure for %s", agent.slug)
            return False
        finally:
            conn.close()


def start_agent_wake(root: Path, agent: AgentConfig, settings: dict, reason: str = "daemon") -> bool:
    with IN_FLIGHT_WAKES_LOCK:
        if agent.slug in IN_FLIGHT_WAKES or lock_is_active(root, agent.slug):
            logging.info("agent %s already locked; skipping background start", agent.slug)
            return False
        IN_FLIGHT_WAKES.add(agent.slug)

    def worker() -> None:
        try:
            run_agent_once(root, agent, settings, reason=reason)
        finally:
            with IN_FLIGHT_WAKES_LOCK:
                IN_FLIGHT_WAKES.discard(agent.slug)

    thread = threading.Thread(target=worker, name=f"hic-agent-{agent.slug}", daemon=True)
    thread.start()
    logging.info("agent %s wake started in background", agent.slug)
    return True


def daemon_loop(root: Path, once: bool = False, only_agent: str | None = None, interval_override: int | None = None) -> None:
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    logging.info("HIC daemon starting root=%s once=%s only_agent=%s", root, once, only_agent)
    while not STOP:
        agents, settings = sync_state(root)
        agent_by_slug = {agent.slug: agent for agent in agents if agent.enabled}
        conn = db.connect(root=root)
        try:
            db.set_state(conn, "daemon_heartbeat", {"at": iso(), "pid": os.getpid()})
            due = [only_agent] if only_agent else choose_due_agents(root, agents, conn)
        finally:
            conn.close()
        for slug in due:
            agent = agent_by_slug.get(slug)
            if agent:
                reason = "manual" if only_agent else "daemon"
                if once or only_agent:
                    run_agent_once(root, agent, settings, reason=reason)
                else:
                    start_agent_wake(root, agent, settings, reason=reason)
        if once:
            break
        sleep_seconds = int(interval_override or settings.get("daemon", {}).get("poll_interval_seconds") or 30)
        for _ in range(max(1, sleep_seconds)):
            if STOP:
                break
            time.sleep(1)
    logging.info("HIC daemon stopping")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run HIC daemon")
    parser.add_argument(
        "--root",
        default=os.environ.get("HIC_ROOT", "/home/jzc/zhichengjiang/working/ai_workspace/hic"),
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--agent")
    parser.add_argument("--interval", type=int)
    args = parser.parse_args(argv)
    root = Path(args.root).absolute()
    configure_logging(root)
    daemon_loop(root, once=args.once, only_agent=args.agent, interval_override=args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
