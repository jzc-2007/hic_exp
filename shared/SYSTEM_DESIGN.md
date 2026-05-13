# HIC System Design

HIC has four first-milestone parts:

- SQLite persistence in var/hic.sqlite3.
- A daemon hosted in tmux as hic_daemon.
- A Flask web UI hosted in tmux as hic_web under /hic.
- Per-agent working directories with durable Markdown memory.

The daemon loads config/agents.yaml, initializes directories and the database,
handles wake requests, starts due agents in parallel background workers, clamps
every next wake to four hours or less, and records events. Per-agent locks
prevent two simultaneous wakes for the same agent while allowing different
agents to run at the same time. The Codex runner is configurable through
HIC_CODEX_CMD. Without that setting, mock mode keeps the UI and scheduler usable.

The web UI exposes only allowlisted operations: wake agents, run doctor, run
tests, restart daemon, reload config, inspect logs, manage known agent fields,
create tasks, and send messages.

UI presentation normalizes human names from slugs, renders chat and last-wake
times as relative labels, renders next-wake time as a live `hh:mm` countdown,
and shows whether each agent is sleeping, queued to wake, recently awake, or working while
preserving source UTC timestamps in element metadata.
