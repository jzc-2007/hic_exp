from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable
import json


UTC = timezone.utc


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime | None = None) -> str:
    dt = dt or now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(microsecond=0).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def clamp_minutes(value: int | float | str | None, default_minutes: int = 240, max_minutes: int = 240) -> int:
    try:
        minutes = int(value) if value is not None else int(default_minutes)
    except (TypeError, ValueError):
        minutes = int(default_minutes)
    if minutes < 1:
        minutes = 1
    return min(minutes, int(max_minutes))


def next_wake_from_minutes(
    minutes: int | float | str | None,
    now: datetime | None = None,
    default_minutes: int = 240,
    max_minutes: int = 240,
) -> str:
    base = now or now_utc()
    clamped = clamp_minutes(minutes, default_minutes, max_minutes)
    return iso(base + timedelta(minutes=clamped))


def is_due(next_wake_at: str | None, now: datetime | None = None) -> bool:
    parsed = parse_iso(next_wake_at)
    if parsed is None:
        return True
    return parsed <= (now or now_utc())


def is_overdue(row: dict, now: datetime | None = None, max_minutes: int = 240) -> bool:
    current = now or now_utc()
    next_wake_at = parse_iso(row.get("next_wake_at"))
    if next_wake_at is not None and next_wake_at < current:
        return True
    last_wake_at = parse_iso(row.get("last_wake_at"))
    if last_wake_at is None:
        return True
    return last_wake_at + timedelta(minutes=max_minutes) < current


def unique_ordered(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def json_dumps(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)
