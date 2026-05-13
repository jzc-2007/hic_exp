#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import importlib
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

ROOT_DEFAULT = Path(os.environ.get("HIC_ROOT", "/home/jzc/zhichengjiang/working/ai_workspace/hic")).absolute()
sys.path.insert(0, str(ROOT_DEFAULT))

from hic import db  # noqa: E402
from hic.config import ensure_project_structure, load_agents, load_settings, root_path  # noqa: E402
from hic.message_bus import create_wake_request, send_message  # noqa: E402
from hic.scheduler import is_overdue, parse_iso  # noqa: E402
from hic.status import daemon_alive, tail_file, tmux_session_exists  # noqa: E402


def bootstrap(root: Path):
    ensure_project_structure(root)
    agents = load_agents(root)
    conn = db.connect(root=root)
    db.init_db(conn)
    db.upsert_agents(conn, agents)
    return conn, agents


def print_table(rows: list[list[str]], headers: list[str]) -> None:
    widths = [len(h) for h in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(str(value)))
    fmt = "  ".join("{:<" + str(width) + "}" for width in widths)
    print(fmt.format(*headers))
    print(fmt.format(*["-" * width for width in widths]))
    for row in rows:
        print(fmt.format(*row))


def _default_note_sections(filename: str) -> list[str]:
    if filename == "MEMORY.md":
        return ["## PRINCIPLES", "## WORKING_PATTERNS", "## PITFALLS"]
    if filename == "EXPERIENCE.md":
        return ["## COMMANDS", "## GOTCHAS", "## CHECKLISTS"]
    stem = Path(filename).stem.upper()
    return [f"## {stem}_NOTES"]


def _normalize_note_title(text: str, filename: str) -> str:
    lines = text.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped:
            if stripped.startswith("# "):
                return stripped
            break
    return f"# {Path(filename).stem.upper()}"


def _parse_note_sections(text: str, filename: str) -> tuple[str, list[str], dict[str, list[str]]]:
    defaults = _default_note_sections(filename)
    title = _normalize_note_title(text, filename)
    order: list[str] = []
    sections: dict[str, list[str]] = {}
    current = defaults[0]
    sections[current] = []
    order.append(current)

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("# ") or stripped.startswith("<!--"):
            continue
        if stripped.startswith("## "):
            current = stripped
            if current not in sections:
                sections[current] = []
                order.append(current)
            continue
        if current not in sections:
            sections[current] = []
            order.append(current)
        bullet = re.sub(r"^[*-]\s*", "", stripped).strip()
        if bullet:
            sections[current].append(bullet)

    for sec in defaults:
        if sec not in sections:
            sections[sec] = []
            order.append(sec)
    return title, order, sections


def _render_note(title: str, order: list[str], sections: dict[str, list[str]]) -> str:
    parts: list[str] = [title, ""]
    for sec in order:
        parts.append(sec)
        entries = sections.get(sec) or []
        if entries:
            parts.extend(f"- {entry}" for entry in entries)
        else:
            parts.append("- (none)")
        parts.append("")
    parts.append("> Managed by `python3 scripts/hicctl.py compact-notes`.")
    parts.append("")
    return "\n".join(parts)


def _compact_note_content(text: str, filename: str, max_items: int, max_bytes: int) -> str:
    title, order, sections = _parse_note_sections(text, filename)
    trimmed = {sec: (entries[-max_items:] if max_items > 0 else list(entries)) for sec, entries in sections.items()}
    rendered = _render_note(title, order, trimmed)
    while len(rendered.encode("utf-8")) > max_bytes:
        non_empty = [sec for sec in order if trimmed.get(sec)]
        if not non_empty:
            break
        target = max(non_empty, key=lambda sec: len(trimmed.get(sec, [])))
        trimmed[target] = trimmed[target][1:]
        rendered = _render_note(title, order, trimmed)
    return rendered


def _compact_note_file(path: Path, max_items: int, max_bytes: int, dry_run: bool) -> tuple[bool, int, int]:
    before = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    after = _compact_note_content(before, path.name, max_items=max_items, max_bytes=max_bytes)
    changed = after != before
    if changed and not dry_run:
        path.write_text(after, encoding="utf-8")
    return changed, len(before.encode("utf-8")), len(after.encode("utf-8"))


def cmd_status(args) -> int:
    root = root_path(args.root)
    conn, _ = bootstrap(root)
    try:
        rows = []
        for agent in db.list_agents(conn):
            rows.append(
                [
                    agent["slug"],
                    "yes" if agent["enabled"] else "no",
                    "yes" if is_overdue(agent) and agent["enabled"] else "no",
                    agent.get("last_wake_at") or "-",
                    agent.get("next_wake_at") or "-",
                    (agent.get("current_task") or "-")[:50],
                    (agent.get("status_summary") or "-")[:60],
                ]
            )
        print_table(rows, ["agent", "enabled", "overdue", "last_wake", "next_wake", "task", "summary"])
        print(f"daemon_tmux={tmux_session_exists('hic_daemon')} web_tmux={tmux_session_exists('hic_web')}")
        print(f"runner_mode={'real' if os.environ.get('HIC_CODEX_CMD') or load_settings(root).get('runner', {}).get('codex_cmd') else 'mock'}")
    finally:
        conn.close()
    return 0


def cmd_send(args) -> int:
    root = root_path(args.root)
    conn, _ = bootstrap(root)
    try:
        msg_id = send_message(conn, "pi", args.to, args.body, priority=args.priority, wakes_recipient=True)
        print(f"sent message #{msg_id} to {args.to}")
    finally:
        conn.close()
    return 0


def cmd_wake(args) -> int:
    root = root_path(args.root)
    conn, agents = bootstrap(root)
    try:
        targets = [agent.slug for agent in agents if agent.enabled] if args.agent == "all" else [args.agent]
        for target in targets:
            create_wake_request(conn, target, "pi", "manual wake from hicctl")
            print(f"wake requested: {target}")
    finally:
        conn.close()
    return 0


def cmd_tasks(args) -> int:
    root = root_path(args.root)
    conn, _ = bootstrap(root)
    try:
        rows = [
            [
                str(task["id"]),
                task["status"],
                task["owner"],
                str(task["priority"]),
                task["title"][:80],
            ]
            for task in db.list_tasks(conn, owner=args.owner, status=args.status, limit=500)
        ]
        print_table(rows, ["id", "status", "owner", "prio", "title"])
    finally:
        conn.close()
    return 0


def cmd_task_add(args) -> int:
    root = root_path(args.root)
    conn, _ = bootstrap(root)
    try:
        task_id = db.create_task(
            conn,
            args.title,
            description=args.description or "",
            owner=args.owner,
            priority=args.priority,
        )
        if args.priority >= 2:
            create_wake_request(conn, args.owner, "pi", f"important task {task_id} from hicctl")
            print(f"created task #{task_id} (important); wake requested for {args.owner}")
        else:
            print(f"created task #{task_id} (normal); no wake requested")
    finally:
        conn.close()
    return 0


def cmd_task_done(args) -> int:
    root = root_path(args.root)
    conn, _ = bootstrap(root)
    try:
        db.update_task(conn, int(args.id), status="done", note="Marked done via hicctl.")
        print(f"task #{args.id} marked done")
    finally:
        conn.close()
    return 0


def cmd_logs(args) -> int:
    root = root_path(args.root)
    if args.kind == "daemon":
        path = root / "var" / "daemon.log"
    elif args.kind == "web":
        path = root / "var" / "web.log"
    else:
        path = root / "agents" / args.agent / "logs"
        candidates = sorted(path.glob("*.log"), key=lambda p: p.stat().st_mtime if p.exists() else 0)
        path = candidates[-1] if candidates else path / "missing.log"
    print(tail_file(path, lines=args.lines))
    return 0


def check_import(name: str) -> tuple[bool, str]:
    try:
        importlib.import_module(name)
        return True, "ok"
    except Exception as exc:
        return False, exc.__class__.__name__


def read_effective_port(root: Path, settings: dict) -> int:
    run_port = root / "var" / "run" / "web_port"
    if run_port.exists():
        try:
            return int(run_port.read_text(encoding="utf-8").strip())
        except ValueError:
            pass
    return int(os.environ.get("HIC_WEB_PORT") or settings.get("web", {}).get("port", 8765))


def cmd_doctor(args) -> int:
    root = root_path(args.root)
    critical_failures = 0
    print(f"HIC doctor root={root}")
    print(f"cwd={Path.cwd()}")
    print(f"python={sys.version.split()[0]}")
    for mod in ("flask", "yaml", "pytest"):
        ok, detail = check_import(mod)
        print(f"package {mod}: {detail}")
        if not ok:
            critical_failures += 1
    print(f"tmux={shutil.which('tmux') or 'missing'}")
    print(f"codex={shutil.which('codex') or 'missing'}")
    try:
        conn, agents = bootstrap(root)
        print(f"config/agents.yaml: ok ({len(agents)} agents)")
    except Exception as exc:
        print(f"config/agents.yaml: FAIL {exc}")
        return 1
    try:
        valid, missing = db.schema_valid(conn)
        print(f"db exists={db.db_path(root).exists()} schema={'ok' if valid else 'missing ' + ','.join(missing)}")
        if not valid:
            critical_failures += 1
        for agent in agents:
            adir = root / "agents" / agent.slug
            required = ["STATUS.md", "PLAN.md", "MEMORY.md", "PROGRESS.md", "EXPERIENCE.md"]
            missing_files = [name for name in required if not (adir / name).exists()]
            print(f"agent_dir {agent.slug}: {'ok' if not missing_files else 'missing ' + ','.join(missing_files)}")
            if missing_files:
                critical_failures += 1
        settings = load_settings(root)
        print(f"tmux hic_daemon={tmux_session_exists('hic_daemon')} hic_web={tmux_session_exists('hic_web')}")
        print(f"daemon_heartbeat={'alive' if daemon_alive(conn, settings) else 'not alive or not started'}")
        rows = db.list_agents(conn)
        overdue = [row["slug"] for row in rows if row["enabled"] and is_overdue(row)]
        print(f"overdue_agents={','.join(overdue) if overdue else 'none'}")
        if os.environ.get("HIC_CODEX_CMD") or settings.get("runner", {}).get("codex_cmd"):
            print("HIC_CODEX_CMD: configured")
        else:
            print("HIC_CODEX_CMD: not configured; mock runner active")
        if os.environ.get("HIC_UI_TOKEN"):
            print("HIC_UI_TOKEN: configured")
        else:
            print("HIC_UI_TOKEN: not configured; ok when kaiming.me dashboard auth protects /hic")
        host = os.environ.get("HIC_WEB_HOST") or settings.get("web", {}).get("host", "127.0.0.1")
        port = read_effective_port(root, settings)
        url = f"http://{host}:{port}/hic/health"
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                print(f"/hic/health: {resp.status} {url}")
        except urllib.error.HTTPError as exc:
            print(f"/hic/health: HTTP {exc.code} {url}")
        except Exception as exc:
            print(f"/hic/health: not reachable ({exc.__class__.__name__}) {url}")
        print(f"path_prefix=/hic public_url={settings.get('ops', {}).get('public_url')}")
    finally:
        conn.close()
    return 0 if critical_failures == 0 else 1


def cmd_test(args) -> int:
    root = root_path(args.root)
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{root}:{env.get('PYTHONPATH', '')}"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "hic/tests"],
        cwd=root,
        env=env,
        text=True,
        check=False,
    )
    return int(proc.returncode)


def cmd_compact_notes(args) -> int:
    root = root_path(args.root)
    agents = load_agents(root)
    target_slugs = {args.agent} if args.agent else {agent.slug for agent in agents}
    rows: list[list[str]] = []
    changed_total = 0
    for slug in sorted(target_slugs):
        adir = root / "agents" / slug
        if not adir.exists():
            rows.append([slug, "-", "missing", "agent dir not found"])
            continue
        for name in ("MEMORY.md", "EXPERIENCE.md"):
            path = adir / name
            if not path.exists():
                rows.append([slug, name, "missing", "file not found"])
                continue
            changed, before_bytes, after_bytes = _compact_note_file(
                path, max_items=args.max_items, max_bytes=args.max_bytes, dry_run=args.dry_run
            )
            if changed:
                changed_total += 1
            status = "updated" if changed and not args.dry_run else "would_update" if changed else "ok"
            rows.append([slug, name, status, f"{before_bytes}B -> {after_bytes}B"])
    print_table(rows, ["agent", "file", "status", "size"])
    if args.dry_run:
        print("dry-run only; no files written.")
    elif changed_total == 0:
        print("no note files needed compaction.")
    else:
        print(f"compacted {changed_total} note files.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HIC fallback CLI")
    parser.add_argument("--root", default=os.environ.get("HIC_ROOT", str(ROOT_DEFAULT)))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status").set_defaults(func=cmd_status)
    p = sub.add_parser("send")
    p.add_argument("--to", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--priority", type=int, choices=[1, 2], default=1)
    p.set_defaults(func=cmd_send)
    p = sub.add_parser("wake")
    p.add_argument("agent")
    p.set_defaults(func=cmd_wake)
    p = sub.add_parser("tasks")
    p.add_argument("--owner")
    p.add_argument("--status")
    p.set_defaults(func=cmd_tasks)
    p = sub.add_parser("task-add")
    p.add_argument("--title", required=True)
    p.add_argument("--owner", default="main")
    p.add_argument("--description", default="")
    p.add_argument("--priority", type=int, choices=[1, 2], default=1)
    p.set_defaults(func=cmd_task_add)
    p = sub.add_parser("task-done")
    p.add_argument("id")
    p.set_defaults(func=cmd_task_done)
    p = sub.add_parser("logs")
    p.add_argument("kind", choices=["daemon", "web", "agent"])
    p.add_argument("agent", nargs="?", default="")
    p.add_argument("--lines", type=int, default=200)
    p.set_defaults(func=cmd_logs)
    sub.add_parser("doctor").set_defaults(func=cmd_doctor)
    sub.add_parser("test").set_defaults(func=cmd_test)
    p = sub.add_parser("compact-notes")
    p.add_argument("--agent", default="")
    p.add_argument("--max-items", type=int, default=24)
    p.add_argument("--max-bytes", type=int, default=8192)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_compact_notes)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
