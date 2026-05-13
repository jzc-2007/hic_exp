from datetime import timedelta

from hic.scheduler import clamp_minutes, is_due, iso, next_wake_from_minutes, now_utc, parse_iso


def test_scheduler_max_four_hour_clamp():
    start = now_utc()
    next_wake = parse_iso(next_wake_from_minutes(999, now=start, max_minutes=240))
    assert next_wake <= start + timedelta(minutes=240, seconds=1)
    assert clamp_minutes(999, max_minutes=240) == 240
    assert is_due(iso(start - timedelta(seconds=1)), now=start)
