# INFRA_MAP

Last updated: 2026-05-13 03:33 UTC
Owner: `yiyang_lu` (infra manager)

## Workspace root resolution

Canonical workspace root on this host:
- `/kmh-nfs-ssd-us-mount/code/zhichengjiang/working/ai_workspace`

Use this in commands:

```bash
export WS_ROOT=/kmh-nfs-ssd-us-mount/code/zhichengjiang/working/ai_workspace
```

Legacy prompts may use `/home/jzc/zhichengjiang/working/ai_workspace`; on this
host that path may not be mounted, so prefer `${WS_ROOT}`.

## Scope and source of truth

Operational docs and runner scripts:
- `${WS_ROOT}/agent_ops`

HIC multi-agent orchestration:
- `${WS_ROOT}/hic`

TPU safety source of truth:
- `${WS_ROOT}/agent_ops/docs/safety_rules.md`
- mirrored guide: `${WS_ROOT}/hic/shared/TPU_SAFETY_RED_LINES.md`

HIC operational truth:
- `${WS_ROOT}/hic/var/hic.sqlite3`
- `tasks` table is canonical for task state.

## Directory map

### `agent_ops/`
- `README.md`: entrypoint + write-back expectations.
- `docs/`: stable procedures (`safety_rules`, workflows, recovery, dashboard,
  `tpu_simple`, monitoring, `tou` behavior).
- `scripts/tpu_simple.py`: queue + launcher + resume + daemon.
- `scripts/tpu_dashboard.py`: local web control plane over `tpu_simple` state.
- `state/`: local runner/dashboard state (`state.json`, `tpus.json`,
  `tpu_fleet_cache.json`, `codex_agents.json`, `dashboard_password`).
- `logs/`: `tpu_simple_daemon.log`, `tpu_dashboard.log`, learning log.

### `hic/`
- `config/agents.yaml`: agent responsibilities and wake intervals.
- `config/settings.yaml`: daemon/web/runner settings.
- `scripts/hicctl.py`: fallback CLI (`status/send/wake/tasks/logs/doctor/test`).
- `scripts/start_daemon.sh`, `stop_daemon.sh`, `restart_daemon.sh`.
- `scripts/start_web.sh`, `stop_web.sh`.
- `scripts/start_all.sh`, `stop_all.sh`, `restart_all.sh`.
- `shared/`: protocol, TPU red lines, task board.
- `agents/<slug>/`: durable agent memory + wake logs.
- `var/`: DB, daemon/web logs, locks, runtime web port/url.

## Runtime topology

### HIC services
- Daemon tmux session: `hic_daemon`
  - command: `python3 -m hic.daemon`
  - scheduler poll interval from settings: `1s`.
- Web tmux session: `hic_web`
  - command: `python3 -m hic.webapp --host 127.0.0.1 --port <selected_port>`
  - default/fallback ports from settings: `8765`, `18765`, `18766`, `18767`.

### TPU services
- Dashboard tmux session: `tpu-dashboard`
  - command: `python agent_ops/scripts/tpu_dashboard.py --host 127.0.0.1 --port 8765`
- Scheduler tmux session: `tpu-simple-daemon`
  - command: `python agent_ops/scripts/tpu_simple.py daemon`
- Job tmux session: `tpu-simple`
  - one window per local tracked job.

## Verified live baseline (2026-05-13 02:51 UTC)

- `hicctl status`: all agents enabled, none overdue, `runner_mode=real`.
- HIC daemon and web tmux sessions exist (`hic_daemon`, `hic_web`).
- HIC web runtime URL file:
  - `${WS_ROOT}/hic/var/run/web_port` -> `18765`
  - `${WS_ROOT}/hic/var/run/web_url` -> `http://127.0.0.1:18765/hic`
- Listening ports:
  - `127.0.0.1:18765` (`hic_web`)
  - `127.0.0.1:8765` (`tpu-dashboard`)
- `tpu-simple-daemon` running; queue currently empty.
- `tmux ls` includes: `tpu-dashboard`, `tpu-simple-daemon`, `tpu-simple`,
  and a long-running `yizhitou` session (treat as risky to touch).

## Verified command surface

### `tpu_simple.py` subcommands
- `set-cur`, `set-dir`, `ls`, `set-tpu`, `list-tpus`, `status`
- `run`, `run-direct`, `resume`
- `check`, `monitor`
- `queue`, `dequeue`, `clear`, `requeue`
- `daemon`, `tou`

### `hicctl.py` subcommands
- `status`, `send`, `wake`, `tasks`
- `task-add`, `task-done`
- `logs`, `doctor`, `test`

## Control plane flow

### HIC wake flow
1. `hic.daemon` picks due/wake-requested agents.
2. It composes prompt from group/direct messages, tasks, durable files, shared
   protocol/red-lines/task-board.
3. Agent returns `<AGENT_RESULT_JSON>{...}</AGENT_RESULT_JSON>`.
4. Daemon applies status update, optional outbound messages, wake requests,
   task updates, and progress append.
5. Idle-guard behavior: if the sender has no active tasks, outbound
   `recipient=group` messages are suppressed by daemon.

### TPU simple flow
1. `run` creates a payload from workdir + constraints + config args.
2. Scheduler uses cached fleet snapshot (`state/tpu_fleet_cache.json`) and
   read-only `gcloud tpu-vm list` refresh logic.
3. If idle TPU matches, launch to tmux window; else enqueue.
4. `daemon` polls queue, requeues resumable failures/preemptions, and launches
   eligible queued jobs.
5. `resume` kills remote Python, resets remote `/tmp/tpu_logs`, then relaunches.

`daemon --allow-fresh-tou` still does **not** call legacy `tou --cache false`;
it only bypasses local fleet cache staleness and refreshes read-only `gcloud`
fleet listings before scheduling.

## Locks and scheduling guards

- HIC per-agent lock: `${WS_ROOT}/hic/var/locks/<slug>.lock`
  - stale threshold in daemon: `6h`; dead-PID locks are auto-cleaned.
- TPU state write lock: `${WS_ROOT}/agent_ops/state/.state.lock`
- Shared TPU reservation lock dir: `/kmh-nfs-ssd-us-mount/code/qiao/tpu_lock`
  - active window considered recent for ~30 minutes by `tpu_simple.py`.

## First triage bundle (safe)

```bash
python3 ${WS_ROOT}/hic/scripts/hicctl.py status
python3 ${WS_ROOT}/hic/scripts/hicctl.py doctor
tmux ls
ss -ltnp | rg ':(8765|18765|18766|18767)'
cat ${WS_ROOT}/hic/var/run/web_url
python ${WS_ROOT}/agent_ops/scripts/tpu_simple.py queue
tmux capture-pane -t tpu-simple-daemon:0 -p -S -
```

## Critical gotchas

- `tou --cache false` and `yizhitou` are not read-only and can trigger TPU
  deletion/mount actions; explicit user confirmation required.
- `tpu_simple.py resume` is destructive (kills remote Python on all workers of
  target TPU).
- `tpu_simple.py run-direct` bypasses queue fairness and shared lock/process
  safety checks used by queued scheduling; treat as high-risk launch path.
- `tpu_simple.py dequeue`, `requeue`, `clear` mutate shared scheduler state
  even when no remote TPU action occurs.
- `tpu_simple.py daemon --allow-fresh-tou` is not a fresh `tou` audit, but
  remains mutation-capable because daemon scheduling can launch/requeue jobs.
- Dashboard mutation endpoints are state-changing even with UI confirmations:
  `/api/run`, `/api/queue/{dequeue,retry,update}`,
  `/api/job/{resume,requeue,clear}`, `/api/jobs/clear-all`,
  `/api/workdir/*`, `/api/config`.
- Do not hand-edit `agent_ops/state/*.json` while `tpu-simple-daemon` or
  `tpu-dashboard` is active; stop service first if emergency repair is needed.
- `start_web.sh` chooses first available configured port and writes runtime port
  to `hic/var/run/web_port`; do not assume `8765`.
- There is no `hic/scripts/restart_web.sh`; use stop/start web or `restart_all.sh`.
- HIC daemon suppresses idle `recipient=group` messages; for must-ack pings
  while idle, send direct message fallback.
- Group messages are visible to every agent on wake; `@mentions` affect wake
  targeting only and are not private routing.
- Scripts contain legacy `/home/jzc/...` defaults but runtime root should be
  resolved via `${WS_ROOT}` and `hic/var/run/*` files.
