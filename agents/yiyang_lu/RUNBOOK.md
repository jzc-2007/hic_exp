# RUNBOOK

Last updated: 2026-05-13 03:33 UTC
Owner: `yiyang_lu`

## Workspace root

```bash
export WS_ROOT=/kmh-nfs-ssd-us-mount/code/zhichengjiang/working/ai_workspace
cd ${WS_ROOT}
```

If prompts mention `/home/jzc/zhichengjiang/working/ai_workspace`, treat that
as a legacy alias and prefer `${WS_ROOT}`.

## 0) Mandatory safety gate

Before any TPU/cloud/job action, read:
- `${WS_ROOT}/agent_ops/docs/safety_rules.md`
- `${WS_ROOT}/hic/shared/TPU_SAFETY_RED_LINES.md`

Without explicit current-turn user confirmation, do **not** run commands that
start/resume/kill/dequeue/requeue/clear jobs, start/stop daemons, run fresh
TPU audits, mutate shared locks/credentials, or move large data.

If unsure: return `proposed command + risk label`, do not execute.

## 1) Wake protocol (teach workers)

For each wake, enforce this order:
1. Read group messages.
2. Read direct messages.
3. Read assigned/open tasks.
4. Read own `STATUS.md`, `PLAN.md`, `MEMORY.md`, `EXPERIENCE.md`.
5. Read shared protocol/safety/task board.
6. Do useful work and update durable files.
7. Append `PROGRESS.md` and refresh `STATUS.md`.
8. Send messages only when concrete answer/blocker/decision is needed.
9. If no active assigned/open tasks, set `next_wake_minutes: 240`.
10. Return one valid `<AGENT_RESULT_JSON>...</AGENT_RESULT_JSON>` object.

Messaging channel rules:
- Reply to group-thread questions in group (`recipient: "group"`).
- Reply to PI direct/private messages in direct (`recipient: "pi"`).
- `@mentions` only target wakeups; group messages remain visible to all agents.
- Do not send routine heartbeat/idle status into group chat.

## 2) Safe daily checks (read-only)

```bash
python3 ${WS_ROOT}/hic/scripts/hicctl.py status
python3 ${WS_ROOT}/hic/scripts/hicctl.py tasks
python3 ${WS_ROOT}/hic/scripts/hicctl.py doctor
python3 ${WS_ROOT}/hic/scripts/hicctl.py logs daemon
python3 ${WS_ROOT}/hic/scripts/hicctl.py logs web
python3 ${WS_ROOT}/hic/scripts/hicctl.py logs agent yiyang_lu

# Runtime sockets and selected HIC port
ss -ltnp | rg ':(8765|18765|18766|18767)'
cat ${WS_ROOT}/hic/var/run/web_port
cat ${WS_ROOT}/hic/var/run/web_url

# TPU scheduler/dashboard snapshots
tmux ls
python ${WS_ROOT}/agent_ops/scripts/tpu_simple.py queue
python ${WS_ROOT}/agent_ops/scripts/tpu_simple.py check
python ${WS_ROOT}/agent_ops/scripts/tpu_simple.py tou --idle-only
tmux capture-pane -t tpu-simple-daemon:0 -p -S -
tmux capture-pane -t tpu-dashboard:0 -p -S -
tail -n 200 ${WS_ROOT}/agent_ops/logs/tpu_simple_daemon.log
tail -n 200 ${WS_ROOT}/agent_ops/logs/tpu_dashboard.log
```

Quick rule: `hicctl status` should show `runner_mode=real` for production side
effects.

## 3) Task execution protocol

### 3.1 Non-TPU tasks
- Use HIC messages/tasks + local code edits/tests.
- Keep durable docs current (`STATUS`, `PROGRESS`, runbook/docs as needed).

### 3.2 TPU-related tasks (only after explicit approval)
Use `agent_ops/scripts/tpu_simple.py` and/or dashboard endpoints.

Typical approved flow:

```bash
python ${WS_ROOT}/agent_ops/scripts/tpu_simple.py set-dir 1 <project_dir>
python ${WS_ROOT}/agent_ops/scripts/tpu_simple.py run type=<tpu_type> dir=1 priority=<n> tag=<tag> <config_args>
python ${WS_ROOT}/agent_ops/scripts/tpu_simple.py queue
python ${WS_ROOT}/agent_ops/scripts/tpu_simple.py check
```

Risk notes:
- `run-direct` is immediate launch and bypasses queued scheduler fairness.
- `resume` is destructive: kills remote Python first.
- `dequeue/requeue/clear` mutate shared scheduler bookkeeping.
- `daemon --allow-fresh-tou` does not run legacy fresh `tou`, but daemon still
  launches/requeues work and is therefore confirmation-required.

## 4) HIC recovery playbooks

### 4.1 Daemon not processing wakes
Symptoms:
- overdue agents, stale heartbeat, or missing `hic_daemon`.

Recovery:

```bash
tmux has-session -t hic_daemon
bash ${WS_ROOT}/hic/scripts/start_daemon.sh
python3 ${WS_ROOT}/hic/scripts/hicctl.py doctor
python3 ${WS_ROOT}/hic/scripts/hicctl.py status
```

### 4.2 Web unavailable or wrong port assumed
Symptoms:
- `/hic` unreachable at expected port.

Recovery:

```bash
tmux has-session -t hic_web
bash ${WS_ROOT}/hic/scripts/stop_web.sh
bash ${WS_ROOT}/hic/scripts/start_web.sh
cat ${WS_ROOT}/hic/var/run/web_port
cat ${WS_ROOT}/hic/var/run/web_url
python3 ${WS_ROOT}/hic/scripts/hicctl.py doctor
```

Notes:
- There is no `restart_web.sh` helper.
- `start_web.sh` selects first free port from configured fallback list.

### 4.3 Agent appears stuck / lock contention
Symptoms:
- repeated daemon log line: `agent <slug> already locked; skipping background start`.

Triage:

```bash
ls -l ${WS_ROOT}/hic/var/locks/<slug>.lock
cat ${WS_ROOT}/hic/var/locks/<slug>.lock
python3 ${WS_ROOT}/hic/scripts/hicctl.py logs agent <slug>
tail -n 200 ${WS_ROOT}/hic/var/daemon.log
```

Behavior:
- daemon auto-cleans stale/dead-pid locks after ~6h staleness threshold.
- avoid manual lock deletion unless explicitly authorized.

### 4.4 Agent output parse failure
Symptoms:
- daemon log contains `result parse warning`.

Triage:

```bash
python3 ${WS_ROOT}/hic/scripts/hicctl.py logs agent <slug>
ls -lt ${WS_ROOT}/hic/agents/<slug>/logs/wake-*.log | head
cat ${WS_ROOT}/hic/agents/<slug>/logs/last-unparsed-output.txt
```

Fix expectation:
- end output with exactly one JSON object inside
  `<AGENT_RESULT_JSON>...</AGENT_RESULT_JSON>`.

## 5) TPU runner/dashboard recovery playbooks

### 5.1 `tpu-simple-daemon` missing

```bash
tmux has-session -t tpu-simple-daemon
tmux new-session -d -s tpu-simple-daemon \
  "cd ${WS_ROOT} && python agent_ops/scripts/tpu_simple.py daemon"
tmux capture-pane -t tpu-simple-daemon:0 -p -S -
```

### 5.2 Queue not draining
Read-only triage:

```bash
python ${WS_ROOT}/agent_ops/scripts/tpu_simple.py queue
python ${WS_ROOT}/agent_ops/scripts/tpu_simple.py tou --idle-only
tail -n 300 ${WS_ROOT}/agent_ops/logs/tpu_simple_daemon.log
```

Common causes:
- no matching READY+idle TPU,
- lock contention in `/kmh-nfs-ssd-us-mount/code/qiao/tpu_lock`,
- mount/process checks failing candidates.

### 5.3 Dashboard unhealthy

```bash
tmux has-session -t tpu-dashboard
tmux capture-pane -t tpu-dashboard:0 -p -S -
tail -n 300 ${WS_ROOT}/agent_ops/logs/tpu_dashboard.log
ls -l ${WS_ROOT}/agent_ops/state/dashboard_password
```

Restart dashboard service:

```bash
tmux kill-session -t tpu-dashboard
tmux new-session -d -s tpu-dashboard \
  "cd ${WS_ROOT} && python agent_ops/scripts/tpu_dashboard.py --host 127.0.0.1 --port 8765"
```

### 5.4 Resume/requeue/clear semantics
- `resume`: remote kill + relaunch (destructive).
- `requeue`: add job payload back to queue (no direct remote action).
- `clear`: archive active job into `job_history` (no direct remote action).
- dashboard `clear-all`: archives every active job; still shared-state mutation.

## 6) Dashboard/API mutation boundaries

Treat these as confirmation-required in shared operations:
- `/api/run` (`START_TPU_JOB`)
- `/api/queue/dequeue` (`DEQUEUE`)
- `/api/queue/retry` (`RETRY_TASK`)
- `/api/queue/update` (`UPDATE_TASK`)
- `/api/job/resume` (`RESUME_JOB`)
- `/api/job/requeue` (`REQUEUE_JOB`)
- `/api/job/clear` (`CLEAR_JOB`)
- `/api/jobs/clear-all` (`CLEAR_ALL_JOBS`)
- `/api/config` (`SAVE_CONFIG`)
- `/api/workdir/{checkout,fetch,pull,push,merge}` (`GIT_*` tokens)

Read-only endpoints that are usually safe:
- `/api/snapshot`
- `/api/billing`
- `/api/configs`
- `GET /api/config`

## 7) tmux and logging gotchas

- HIC sessions: `hic_daemon`, `hic_web`.
- TPU sessions: `tpu-dashboard`, `tpu-simple-daemon`, `tpu-simple`.
- `run`, `run-direct`, `resume`, and daemon-launched work reset remote
  `/tmp/tpu_logs` before launch.
- `tpu_simple.py daemon --allow-fresh-tou` only forces read-only `gcloud` fleet
  refresh but can still launch/requeue jobs in the same loop.
- Do not hand-edit `agent_ops/state/*.json` while daemon/dashboard processes
  are active.
- `tpu_dashboard.log` uses rotation (2MB x 5 backups).

## 8) Messaging behavior gotcha

- If an agent has no active tasks, daemon suppresses outgoing `recipient=group`
  messages (idle anti-spam).
- For required acknowledgement during idle, send direct message fallback.

## 9) Escalation format

When blocked by risk gate, respond with:
- exact command proposal,
- risk label (`safe` / `risky` / `destructive`),
- side effects,
- rollback/containment note.
