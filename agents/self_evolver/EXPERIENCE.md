# EXPERIENCE

Commands, gotchas, and practical lessons for evolving HIC go here.

- In this environment, `pytest` may resolve to a different interpreter than
  HIC runtime deps. Prefer `python3 -m pytest` with `PYTHONPATH="$ROOT"` and
  `HIC_ROOT="$ROOT"` for focused verification.
