# EXPERIENCE

- Assume `WS_ROOT=/kmh-nfs-ssd-us-mount/code/zhichengjiang/working/ai_workspace` (see `RUNBOOK.md`).
- Safe first triage bundle:
  - `python3 ${WS_ROOT}/hic/scripts/hicctl.py status`
  - `tmux ls`
  - `ss -ltnp | rg ':(8765|18765|18766|18767)'`
  - `python ${WS_ROOT}/agent_ops/scripts/tpu_simple.py queue`
- If HIC web seems down, verify selected runtime port from `hic/var/run/web_url` before restarting.
- There is no `hic/scripts/restart_web.sh`; use `stop_web.sh` then `start_web.sh`, then re-check `hic/var/run/web_url`.
- If agent wake appears stuck, inspect `hic/var/locks/<slug>.lock` and latest `agents/<slug>/logs/wake-*.log` before intervention.
- `resume` in `tpu_simple.py` is destructive (kills remote python). Treat as confirmation-required even for “debug” usage.
- `dequeue` / `requeue` / `clear` in `tpu_simple.py` mutate shared queue/job bookkeeping; require explicit confirmation in task-running contexts.
- `run-direct` in `tpu_simple.py` launches immediately and bypasses queued scheduler fairness/lock checks; treat as high-risk.
- `tou --cache false` is operationally risky; prefer cached/read-only status checks first.
- When idle (no active tasks), outbound group messages are suppressed by daemon; use direct-message fallback for must-ack pings.
