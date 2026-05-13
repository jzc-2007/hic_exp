from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse
import json
import os
import re
import secrets
import subprocess
import uuid

from flask import (
    abort,
    Flask,
    Response,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.utils import secure_filename

from . import db
from .config import (
    AgentConfig,
    add_agent,
    ensure_project_structure,
    load_agents,
    load_settings,
    read_file,
    root_path,
    update_agent_enabled,
)
from .message_bus import append_incident, create_wake_request, list_messages, send_message
from .scheduler import is_overdue, iso, now_utc, parse_iso
from .status import agent_lock_active, daemon_alive, db_health, human_log_view, system_snapshot, tail_file


def classify_issue(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ("gui", "ui", "不好用", "界面")):
        return "UX issue"
    if any(word in lower for word in ("agent", "wake", "没醒", "sleep", "醒")):
        return "agent behavior issue"
    if any(word in lower for word in ("daemon", "tmux", "log", "infra", "runner")):
        return "infra issue"
    if any(word in lower for word in ("add", "new", "加", "feature")):
        return "feature"
    return "bug"


def safe_run(root: Path, args: list[str], timeout: int = 180) -> dict[str, Any]:
    proc = subprocess.run(
        args,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    output = proc.stdout or ""
    (root / "var" / "run").mkdir(parents=True, exist_ok=True)
    (root / "var" / "run" / "last_ops_output.txt").write_text(output[-20000:], encoding="utf-8")
    return {"returncode": proc.returncode, "output": output[-20000:], "command": " ".join(args)}


def safe_return_url(value: str | None) -> str:
    target = str(value or "").strip()
    if not target or target.startswith("//"):
        return ""
    if target == "/hic" or target.startswith("/hic/") or target.startswith("/hic?"):
        return target
    return ""


def human_name(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "-"
    special = {"pi": "PI", "group": "Group", "all": "All", "jqdai": "jqdai"}
    mapped = special.get(raw.lower())
    if mapped:
        return mapped
    words = [part for part in re.split(r"[\s_-]+", raw) if part]
    if not words:
        return raw

    def normalize(word: str) -> str:
        if word.isupper() and len(word) <= 4:
            return word
        return word[:1].upper() + word[1:].lower()

    return " ".join(normalize(word) for word in words)


def relative_time(value: Any) -> str:
    parsed = parse_iso(str(value or ""))
    if not parsed:
        return "-"
    delta_seconds = int((parsed - now_utc()).total_seconds())
    absolute = abs(delta_seconds)
    if absolute < 5:
        return "just now"
    if absolute < 60:
        amount, suffix = absolute, "s"
    elif absolute < 3600:
        amount, suffix = absolute // 60, "m"
    elif absolute < 86400:
        amount, suffix = absolute // 3600, "h"
    else:
        amount, suffix = absolute // 86400, "d"
    if delta_seconds < 0:
        return f"{amount}{suffix} ago"
    return f"in {amount}{suffix}"


def countdown_time(value: Any) -> str:
    parsed = parse_iso(str(value or ""))
    if not parsed:
        return "-"
    delta_seconds = int((parsed - now_utc()).total_seconds())
    if delta_seconds <= 0:
        return "00:00"
    total_minutes = (delta_seconds + 59) // 60
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours:02d}:{minutes:02d}"


def _extract_usage_from_wake_log(path: Path) -> dict[str, int] | None:
    content = tail_file(path, lines=900, max_bytes=350000)
    for line in reversed(content.splitlines()):
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        usage = payload.get("usage") if isinstance(payload, dict) else None
        if not isinstance(usage, dict):
            continue
        input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or 0)
        if total_tokens <= 0:
            total_tokens = input_tokens + output_tokens
        if input_tokens or output_tokens or total_tokens:
            return {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            }
    return None


def codex_usage_summary(root: Path) -> dict[str, Any]:
    input_sum = 0
    output_sum = 0
    total_sum = 0
    usage_agents = 0
    latest_mtime = 0.0
    for agent in load_agents(root):
        logs_dir = root / "agents" / agent.slug / "logs"
        if not logs_dir.exists():
            continue
        wake_logs = list(logs_dir.glob("wake-*.log"))
        if not wake_logs:
            continue
        latest_log = max(wake_logs, key=lambda item: item.stat().st_mtime)
        usage = _extract_usage_from_wake_log(latest_log)
        if not usage:
            continue
        usage_agents += 1
        input_sum += int(usage["input_tokens"])
        output_sum += int(usage["output_tokens"])
        total_sum += int(usage["total_tokens"])
        latest_mtime = max(latest_mtime, latest_log.stat().st_mtime)
    if usage_agents == 0:
        return {
            "available": False,
            "label": "Codex tokens: -",
            "title": "No recent token usage found in agent wake logs.",
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "agents": 0,
        }
    latest_iso = datetime.fromtimestamp(latest_mtime, tz=timezone.utc).isoformat() if latest_mtime else ""
    return {
        "available": True,
        "label": f"Codex tokens: {input_sum:,}/{output_sum:,}",
        "title": (
            f"Input: {input_sum:,}, Output: {output_sum:,}, Total: {total_sum:,}. "
            f"Summed from latest usage event of {usage_agents} agent log(s)"
            + (f", latest at {latest_iso}" if latest_iso else "")
        ),
        "input_tokens": input_sum,
        "output_tokens": output_sum,
        "total_tokens": total_sum,
        "agents": usage_agents,
    }


def decorate_messages(conn, messages: list[dict[str, Any]], root: Path | None = None) -> list[dict[str, Any]]:
    message_ids = [int(msg["id"]) for msg in messages if msg.get("id")]
    attachments = db.list_attachments(conn, message_ids)
    root = Path(root) if root else None
    display_by_slug = {
        str(agent["slug"]): human_name(str(agent.get("display_name") or agent["slug"])) for agent in db.list_agents(conn)
    }

    def display_label(value: Any) -> str:
        raw = str(value or "")
        return display_by_slug.get(raw, human_name(raw))

    for msg in messages:
        msg_id = int(msg["id"])
        msg["attachments"] = attachments.get(msg_id, [])
        msg["sender_display"] = display_label(msg.get("sender"))
        msg["recipient_display"] = display_label(msg.get("recipient"))
        try:
            read_by = json.loads(msg.get("read_by") or "[]")
        except json.JSONDecodeError:
            read_by = []
        msg["read_by_list"] = read_by
        msg["read_by_display"] = [display_label(slug) for slug in read_by]
        wakes = db.wake_requests_for_message(conn, msg_id)
        pending = [wake for wake in wakes if not wake.get("handled")]
        if wakes:
            pending_targets = [str(wake.get("target_agent") or "") for wake in pending]
            wake_targets = [str(wake.get("target_agent") or "") for wake in wakes]
            running_targets = [
                target
                for target in wake_targets
                if root and target and agent_lock_active(root, target)
            ]
            pending_target_display = [display_label(target) for target in pending_targets]
            running_target_display = [display_label(target) for target in running_targets]
            if running_targets:
                label = "working"
            elif pending:
                label = "wake queued"
            else:
                label = "wake complete"
            msg["wake_progress"] = {
                "total": len(wakes),
                "pending": len(pending),
                "running": len(running_targets),
                "pending_targets": pending_targets,
                "pending_target_display": pending_target_display,
                "running_targets": running_targets,
                "running_target_display": running_target_display,
                "label": label,
            }
        else:
            msg["wake_progress"] = {
                "total": 0,
                "pending": 0,
                "running": 0,
                "pending_targets": [],
                "pending_target_display": [],
                "running_targets": [],
                "running_target_display": [],
                "label": "sent",
            }
    return messages


def latest_pi_delivery_state(
    messages: list[dict[str, Any]],
    target_agent: str,
    activity_label: str = "",
) -> dict[str, Any] | None:
    for msg in reversed(messages):
        if str(msg.get("sender") or "") != "pi":
            continue
        if str(msg.get("recipient") or "") != target_agent:
            continue
        read_by = [str(item) for item in msg.get("read_by_list") or []]
        progress = msg.get("wake_progress", {})
        pending_targets = [str(item) for item in progress.get("pending_targets") or []]
        running_targets = [str(item) for item in progress.get("running_targets") or []]
        awake_like = activity_label.startswith(("awake", "working"))
        if target_agent in running_targets:
            label, tone = "received; agent working", "warn"
        elif target_agent in read_by and awake_like:
            label, tone = "received; agent awake", "ok"
        elif target_agent in read_by:
            label, tone = "received; agent now idle", "warn"
        elif target_agent in pending_targets:
            label, tone = "wake queued; waiting read", "warn"
        else:
            label, tone = "sent; not read yet", "bad"
        return {
            "message_id": int(msg.get("id") or 0),
            "label": label,
            "tone": tone,
            "when_label": relative_time(msg.get("created_at")),
            "created_at": msg.get("created_at"),
        }
    return None


def save_uploads(root: Path, conn, message_id: int, files: list[Any]) -> list[dict[str, Any]]:
    saved: list[dict[str, Any]] = []
    upload_dir = root / "var" / "uploads" / iso()[:10]
    upload_dir.mkdir(parents=True, exist_ok=True)
    for item in files:
        if not item or not getattr(item, "filename", ""):
            continue
        filename = secure_filename(item.filename) or "upload"
        stored = upload_dir / f"{uuid.uuid4().hex}-{filename}"
        item.save(stored)
        size = stored.stat().st_size
        rel_path = str(stored.relative_to(root))
        attachment_id = db.add_attachment(
            conn,
            message_id,
            filename,
            rel_path,
            content_type=getattr(item, "mimetype", "") or "",
            size=size,
        )
        saved.append(
            {
                "id": attachment_id,
                "filename": filename,
                "path": str(stored),
                "content_type": getattr(item, "mimetype", "") or "",
                "size": size,
            }
        )
    return saved


def latest_agent_log_path(root: Path, slug: str) -> Path:
    logs_dir = root / "agents" / slug / "logs"
    candidates = sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime if p.exists() else 0)
    return candidates[-1] if candidates else logs_dir / "missing.log"


def agent_progress_payload(root: Path, slug: str, lines: int = 400) -> dict[str, Any] | None:
    agent = next((item for item in load_agents(root) if item.slug == slug), None)
    if not agent:
        return None
    log_path = latest_agent_log_path(root, slug)
    content = tail_file(log_path, lines=lines, max_bytes=500000)
    log_view = human_log_view(log_path, f"agent:{slug}", content)
    running = agent_lock_active(root, slug)
    session_path = root / "agents" / slug / "CODEX_SESSION_ID"
    modified_at = ""
    size = 0
    if log_path.exists():
        stat = log_path.stat()
        modified_at = iso(datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc))
        size = int(stat.st_size)
    session_id = session_path.read_text(encoding="utf-8").strip() if session_path.exists() else ""
    return {
        "ok": True,
        "agent": {"slug": agent.slug, "display_name": human_name(agent.display_name or agent.slug)},
        "running": running,
        "running_label": "working" if running else "not running",
        "session": session_id or "",
        "session_label": "resume ready" if session_id else "new session on next wake",
        "path": str(log_path),
        "exists": log_path.exists(),
        "modified_at": modified_at,
        "size": size,
        "lines": int(lines),
        "cards": log_view["cards"],
        "problem_count": log_view["problem_count"],
        "event_count": log_view["event_count"],
        "raw": content,
    }


def create_app(root: Path | str | None = None) -> Flask:
    root = root_path(root)
    ensure_project_structure(root)
    conn = db.connect(root=root)
    try:
        db.init_db(conn)
        db.upsert_agents(conn, load_agents(root))
    finally:
        conn.close()

    source_root = Path(__file__).parents[1]
    template_root = root / "web" / "templates"
    static_root = root / "web" / "static"
    if not (template_root / "dashboard.html").exists():
        template_root = source_root / "web" / "templates"
    if not (static_root / "hic.css").exists():
        static_root = source_root / "web" / "static"

    app = Flask(
        __name__,
        template_folder=str(template_root),
        static_folder=str(static_root),
        static_url_path="/hic/static",
    )
    app.secret_key = os.environ.get("HIC_FLASK_SECRET", "hic-local-dev-secret")
    app.config["HIC_ROOT"] = str(root)

    def ui_token() -> str:
        return os.environ.get("HIC_UI_TOKEN", "")

    def authed() -> bool:
        token = ui_token()
        if not token:
            return True
        supplied = (
            request.cookies.get("hic_token")
            or request.headers.get("X-HIC-Token")
            or request.args.get("token")
            or request.form.get("token")
            or ""
        )
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            supplied = auth.split(" ", 1)[1]
        return bool(supplied) and secrets.compare_digest(supplied, token)

    @app.before_request
    def require_auth():
        token = ui_token()
        if not token:
            return None
        if request.path in ("/hic/health", "/hic/login") or request.path.startswith("/hic/static/"):
            return None
        if authed():
            return None
        if request.headers.get("Accept", "").startswith("application/json"):
            return jsonify({"ok": False, "error": "auth required"}), 401
        return redirect(url_for("login", next=request.path))

    @app.context_processor
    def inject_globals():
        settings = load_settings(root)
        return {
            "settings": settings,
            "path_prefix": settings.get("web", {}).get("path_prefix", "/hic"),
            "auth_enabled": bool(ui_token()),
            "current_return_url": request.full_path.rstrip("?"),
            "codex_usage": codex_usage_summary(root),
        }

    @app.template_filter("short")
    def short(value: str | None, length: int = 70) -> str:
        text = str(value or "")
        return text if len(text) <= length else text[: length - 1] + "..."

    @app.template_filter("human_name")
    def human_name_filter(value: Any) -> str:
        return human_name(value)

    @app.template_filter("relative_time")
    def relative_time_filter(value: Any) -> str:
        return relative_time(value)

    @app.template_filter("countdown_time")
    def countdown_time_filter(value: Any) -> str:
        return countdown_time(value)

    @app.template_filter("overdue")
    def overdue_filter(row: dict[str, Any]) -> bool:
        return is_overdue(row)

    @app.template_filter("relative")
    def relative_filter(value: str | None) -> str:
        return relative_time(value)

    @app.route("/")
    def root_redirect():
        return redirect(url_for("dashboard"))

    @app.route("/hic/login", methods=["GET", "POST"])
    def login():
        if not ui_token():
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            supplied = request.form.get("token") or ""
            if secrets.compare_digest(supplied, ui_token()):
                resp = make_response(redirect(request.args.get("next") or url_for("dashboard")))
                resp.set_cookie("hic_token", supplied, httponly=True, samesite="Lax")
                return resp
            flash("Invalid token", "error")
        return render_template("login.html")

    @app.route("/hic/logout", methods=["POST"])
    def logout():
        resp = make_response(redirect(url_for("login")))
        resp.delete_cookie("hic_token")
        return resp

    @app.route("/hic/health")
    def health():
        conn = db.connect(root=root)
        try:
            settings = load_settings(root)
            return jsonify(
                {
                    "ok": True,
                    "root": str(root),
                    "daemon_alive": daemon_alive(conn, settings),
                    "path_prefix": "/hic",
                    "db": db_health(root),
                }
            )
        finally:
            conn.close()

    @app.route("/hic")
    @app.route("/hic/")
    def dashboard():
        snap = system_snapshot(root)
        return render_template("dashboard.html", snapshot=snap)

    @app.route("/hic/docs")
    def docs():
        return redirect(url_for("guide"))

    @app.route("/hic/attachments/<int:attachment_id>")
    def attachment(attachment_id: int):
        conn = db.connect(root=root)
        try:
            row = db.get_attachment(conn, attachment_id)
        finally:
            conn.close()
        if not row:
            abort(404)
        path = (root / str(row["stored_path"])).resolve()
        uploads = (root / "var" / "uploads").resolve()
        if uploads not in path.parents or not path.exists():
            abort(404)
        return send_file(
            path,
            as_attachment=True,
            download_name=str(row["filename"] or path.name),
            mimetype=str(row.get("content_type") or "application/octet-stream"),
        )

    @app.route("/hic/chat", methods=["GET", "POST"])
    def chat():
        agents = load_agents(root)
        selected = request.values.get("channel") or "group"
        if request.method == "POST":
            selected = request.form.get("channel") or selected
            body = (request.form.get("body") or "").strip()
            priority = int(request.form.get("priority") or 2)
            files = [item for item in request.files.getlist("files") if item and item.filename]
            if body or files:
                recipient = selected.split(":", 1)[1] if selected.startswith("direct:") else selected
                conn = db.connect(root=root)
                try:
                    send_body = body or "Uploaded file(s)."
                    msg_id = send_message(conn, "pi", recipient, send_body, priority=priority, wakes_recipient=True)
                    saved = save_uploads(root, conn, msg_id, files)
                    if saved:
                        lines = ["", "Attachments:"]
                        for item in saved:
                            lines.append(
                                f"- {item['filename']}: {item['path']} ({item['content_type'] or 'file'}, {item['size']} bytes)"
                            )
                        send_body = send_body.rstrip() + "\n" + "\n".join(lines)
                        db.update_message_body(conn, msg_id, send_body)
                    flash(f"Message #{msg_id} sent.", "ok")
                finally:
                    conn.close()
            if body or files:
                return redirect(url_for("chat", channel=selected, sent=msg_id))
            return redirect(url_for("chat", channel=selected))
        conn = db.connect(root=root)
        try:
            messages = decorate_messages(conn, list_messages(conn, channel=selected, limit=150), root=root)
            selected_agent = selected.split(":", 1)[1] if selected.startswith("direct:") else None
            agent_row = db.get_agent(conn, selected_agent) if selected_agent else None
            snap = system_snapshot(root)
            agent_runtime = next((row for row in snap["agents"] if row["slug"] == selected_agent), None) if selected_agent else None
            latest_pi_delivery = (
                latest_pi_delivery_state(
                    messages,
                    selected_agent,
                    str((agent_runtime or {}).get("activity_label") or ""),
                )
                if selected_agent
                else None
            )
            try:
                sent_message_id = int(request.args.get("sent") or 0)
            except ValueError:
                sent_message_id = 0
        finally:
            conn.close()
        if selected == "group":
            selected_label = "Group"
        elif selected.startswith("direct:"):
            selected_label = f"Direct: {human_name(selected.split(':', 1)[1])}"
        else:
            selected_label = human_name(selected)
        return render_template(
            "chat.html",
            agents=agents,
            selected=selected,
            selected_label=selected_label,
            messages=messages,
            selected_agent=agent_row,
            agent_runtime=agent_runtime,
            latest_pi_delivery=latest_pi_delivery,
            snapshot=snap,
            sent_message_id=sent_message_id,
        )

    @app.route("/hic/tasks", methods=["GET", "POST"])
    def tasks():
        agents = load_agents(root)
        conn = db.connect(root=root)
        try:
            if request.method == "POST":
                action = request.form.get("action")
                if action == "create":
                    title = (request.form.get("title") or "").strip()
                    if title:
                        priority = int(request.form.get("priority") or 2)
                        task_id = db.create_task(
                            conn,
                            title=title,
                            description=request.form.get("description") or "",
                            owner=request.form.get("owner") or "main",
                            priority=priority,
                        )
                        if priority >= 2:
                            create_wake_request(conn, request.form.get("owner") or "main", "pi", f"important task {task_id}")
                        suffix = " and wake queued" if priority >= 2 else ""
                        flash(f"Task #{task_id} created{suffix}", "ok")
                elif action == "update":
                    task_id = int(request.form["task_id"])
                    db.update_task(
                        conn,
                        task_id,
                        status=request.form.get("status") or None,
                        owner=request.form.get("owner") or None,
                        note=request.form.get("note") or None,
                    )
                    flash(f"Task #{task_id} updated", "ok")
                return redirect(url_for("tasks"))
            owner = request.args.get("owner") or None
            status = request.args.get("status") or None
            task_rows = db.list_tasks(conn, owner=owner, status=status, limit=500)
        finally:
            conn.close()
        return render_template("tasks.html", tasks=task_rows, agents=agents)

    @app.route("/hic/ops", methods=["GET", "POST"])
    def ops():
        result = None
        agents = load_agents(root)
        conn = db.connect(root=root)
        try:
            if request.method == "POST":
                action = request.form.get("action")
                return_to = safe_return_url(request.form.get("next"))
                if action == "wake":
                    target = request.form.get("agent") or "main"
                    create_wake_request(conn, target, "pi", "manual wake from UI")
                    result = {"output": f"Wake request created for {target}", "returncode": 0}
                elif action == "wake_all":
                    for agent in agents:
                        if agent.enabled:
                            create_wake_request(conn, agent.slug, "pi", "manual wake all from UI")
                    result = {"output": "Wake requests created for all enabled agents", "returncode": 0}
                elif action == "doctor":
                    result = safe_run(root, ["bash", "scripts/doctor.sh"], timeout=180)
                elif action == "tests":
                    result = safe_run(root, ["bash", "scripts/run_tests.sh"], timeout=600)
                elif action == "restart_daemon":
                    result = safe_run(root, ["bash", "scripts/restart_daemon.sh"], timeout=60)
                elif action == "reload_config":
                    db.upsert_agents(conn, load_agents(root))
                    result = {"output": "Config reloaded into database", "returncode": 0}
                elif action == "db_health":
                    result = {"output": str(db_health(root)), "returncode": 0}
                else:
                    result = {"output": "Unknown allowlisted action", "returncode": 1}
                db.insert_event(conn, "ui_ops_action", "pi", {"action": action, "returncode": result["returncode"]})
                if return_to and action in {"wake", "wake_all"}:
                    flash(result["output"], "ok" if result["returncode"] == 0 else "error")
                    return redirect(return_to)
            snap = system_snapshot(root)
            recent_daemon = tail_file(root / "var" / "daemon.log", lines=80)
            recent_web = tail_file(root / "var" / "web.log", lines=80)
        finally:
            conn.close()
        return render_template(
            "ops.html",
            agents=agents,
            snapshot=snap,
            result=result,
            recent_daemon=recent_daemon,
            recent_web=recent_web,
        )

    @app.route("/hic/logs")
    def logs():
        agents = load_agents(root)
        target = request.args.get("target") or "daemon"
        lines = int(request.args.get("lines") or load_settings(root).get("ops", {}).get("log_tail_lines") or 300)
        if target == "daemon":
            path = root / "var" / "daemon.log"
        elif target == "web":
            path = root / "var" / "web.log"
        elif target.startswith("agent:"):
            slug = target.split(":", 1)[1]
            logs_dir = root / "agents" / slug / "logs"
            candidates = sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime if p.exists() else 0)
            path = candidates[-1] if candidates else logs_dir / "missing.log"
        else:
            path = root / "var" / "daemon.log"
        content = tail_file(path, lines=lines)
        log_view = human_log_view(path, target, content)
        return render_template(
            "logs.html",
            agents=agents,
            target=target,
            path=path,
            content=content,
            log_view=log_view,
            lines=lines,
        )

    @app.route("/hic/progress/<slug>")
    def agent_progress(slug: str):
        agents = load_agents(root)
        payload = agent_progress_payload(root, slug)
        if not payload:
            abort(404)
        return render_template("agent_progress.html", agents=agents, progress=payload)

    @app.route("/hic/api/progress/<slug>")
    def api_agent_progress(slug: str):
        try:
            lines = int(request.args.get("lines") or 400)
        except ValueError:
            lines = 400
        lines = max(80, min(lines, 1200))
        payload = agent_progress_payload(root, slug, lines=lines)
        if not payload:
            return jsonify({"ok": False, "error": "agent not found"}), 404
        return jsonify(payload)

    @app.route("/hic/settings", methods=["GET", "POST"])
    def settings_page():
        result = None
        if request.method == "POST":
            action = request.form.get("action")
            try:
                if action == "toggle":
                    slug = request.form["slug"]
                    enabled = request.form.get("enabled") == "1"
                    update_agent_enabled(slug, enabled, root)
                    conn = db.connect(root=root)
                    try:
                        db.set_agent_enabled(conn, slug, enabled)
                    finally:
                        conn.close()
                    result = f"{slug} {'enabled' if enabled else 'disabled'}"
                elif action == "add":
                    responsibilities = [
                        line.strip()
                        for line in (request.form.get("responsibilities") or "").splitlines()
                        if line.strip()
                    ]
                    agent = add_agent(
                        request.form.get("slug") or "",
                        request.form.get("display_name") or "",
                        request.form.get("role") or "agent",
                        responsibilities,
                        root,
                    )
                    conn = db.connect(root=root)
                    try:
                        db.upsert_agents(conn, load_agents(root))
                    finally:
                        conn.close()
                    result = f"Added agent {agent.slug}"
            except Exception as exc:
                result = f"Error: {exc}"
        agents = load_agents(root)
        agents_yaml = read_file(root / "config" / "agents.yaml", limit=50000)
        onboarding = read_file(root / "shared" / "ONBOARDING.md", limit=20000)
        return render_template(
            "settings.html",
            agents=agents,
            agents_yaml=agents_yaml,
            onboarding=onboarding,
            result=result,
        )

    @app.route("/hic/self-improve", methods=["GET", "POST"])
    def self_improve():
        conn = db.connect(root=root)
        try:
            if request.method == "POST":
                body = (request.form.get("body") or "").strip()
                if body:
                    issue_type = classify_issue(body)
                    title = f"{issue_type}: {body[:80]}"
                    owner = "self_evolver" if db.get_agent(conn, "self_evolver") else "main"
                    append_incident(root, title, body)
                    send_message(
                        conn,
                        "pi",
                        owner,
                        f"System improvement request ({issue_type}):\n{body}",
                        priority=2,
                        wakes_recipient=True,
                    )
                    flash(f"Improvement request sent to {human_name(owner)}.", "ok")
                    return redirect(url_for("self_improve"))
            incidents = read_file(root / "shared" / "INCIDENTS.md", limit=30000)
        finally:
            conn.close()
        return render_template("self_improve.html", incidents=incidents)

    @app.route("/hic/guide")
    def guide():
        usage_doc = read_file(root / "shared" / "USAGE.md", limit=80000)
        return render_template("guide.html", usage_doc=usage_doc)

    @app.route("/hic/api/status")
    def api_status():
        return jsonify(system_snapshot(root))

    @app.route("/hic/api/messages")
    def api_messages():
        channel = request.args.get("channel") or "group"
        conn = db.connect(root=root)
        try:
            return jsonify({"messages": list_messages(conn, channel=channel, limit=100)})
        finally:
            conn.close()

    @app.route("/hic/raw/agents.yaml")
    def raw_agents_yaml():
        return Response(read_file(root / "config" / "agents.yaml", limit=100000), mimetype="text/plain")

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run HIC web app")
    parser.add_argument(
        "--root",
        default=os.environ.get("HIC_ROOT", "/home/jzc/zhichengjiang/working/ai_workspace/hic"),
    )
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)
    root = Path(args.root).absolute()
    settings = load_settings(root)
    host = args.host or os.environ.get("HIC_WEB_HOST") or settings.get("web", {}).get("host", "127.0.0.1")
    port = int(args.port or os.environ.get("HIC_WEB_PORT") or settings.get("web", {}).get("port", 8765))
    app = create_app(root)
    app.run(host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
