from __future__ import annotations

from pathlib import Path
from typing import Any
import mimetypes
import re
import shutil
import uuid

from . import db
from .scheduler import iso


MAX_AGENT_ATTACHMENTS = 10
MAX_AGENT_ATTACHMENT_BYTES = 50 * 1024 * 1024


def _safe_filename(value: str) -> str:
    name = Path(value or "artifact").name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return cleaned or "artifact"


def _attachment_path_from_item(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return str(item.get("path") or item.get("file") or item.get("filename") or "")
    return ""


def _resolve_agent_artifact(root: Path, agent_slug: str, raw_path: str) -> Path:
    source = Path(raw_path).expanduser()
    if not source.is_absolute():
        source = root / source
    resolved = source.resolve()
    allowed = (root / "agents" / agent_slug / "outbox").resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError as exc:
        raise ValueError(f"{raw_path} is outside agents/{agent_slug}/outbox") from exc
    if not resolved.exists():
        raise FileNotFoundError(f"{raw_path} does not exist")
    if not resolved.is_file():
        raise ValueError(f"{raw_path} is not a regular file")
    size = resolved.stat().st_size
    if size > MAX_AGENT_ATTACHMENT_BYTES:
        raise ValueError(f"{raw_path} is too large ({size} bytes)")
    return resolved


def attach_agent_artifacts(
    root: Path,
    conn,
    message_id: int,
    agent_slug: str,
    raw_items: list[Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    saved: list[dict[str, Any]] = []
    errors: list[str] = []
    upload_dir = root / "var" / "uploads" / "agent-artifacts" / iso()[:10]
    upload_dir.mkdir(parents=True, exist_ok=True)
    for item in raw_items[:MAX_AGENT_ATTACHMENTS]:
        raw_path = _attachment_path_from_item(item).strip()
        if not raw_path:
            continue
        try:
            source = _resolve_agent_artifact(root, agent_slug, raw_path)
            filename = _safe_filename(source.name)
            stored = upload_dir / f"{uuid.uuid4().hex}-{filename}"
            shutil.copy2(source, stored)
            size = stored.stat().st_size
            content_type = mimetypes.guess_type(filename)[0] or ""
            rel_path = str(stored.relative_to(root))
            attachment_id = db.add_attachment(
                conn,
                message_id,
                filename,
                rel_path,
                content_type=content_type,
                size=size,
            )
            saved.append(
                {
                    "id": attachment_id,
                    "filename": filename,
                    "source": str(source),
                    "path": str(stored),
                    "content_type": content_type,
                    "size": size,
                }
            )
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    if len(raw_items) > MAX_AGENT_ATTACHMENTS:
        errors.append(f"Only the first {MAX_AGENT_ATTACHMENTS} attachments were processed.")
    return saved, errors


def append_attachment_report(body: str, saved: list[dict[str, Any]], errors: list[str]) -> str:
    lines: list[str] = []
    if saved:
        lines.extend(["", "Attachments:"])
        for item in saved:
            lines.append(f"- {item['filename']} ({item['size']} bytes)")
    if errors:
        lines.extend(["", "Attachment errors:"])
        lines.extend(f"- {error}" for error in errors)
    if not lines:
        return body
    return body.rstrip() + "\n" + "\n".join(lines)
