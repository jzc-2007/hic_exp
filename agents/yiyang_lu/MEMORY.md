# MEMORY

- `agent_ops` is the operational source of truth for experiment infra.
- TPU task-running red lines are defined in `agent_ops/docs/safety_rules.md` and mirrored in `shared/TPU_SAFETY_RED_LINES.md`.
- HIC source of truth is `hic/var/hic.sqlite3`; markdown files are durable working memory, not scheduling truth.
- HIC web port may move to fallback ports; always check `hic/var/run/web_port` and `hic/var/run/web_url`.
- `tpu_simple.py` scheduler/dashboard use internal cached fleet snapshot (`agent_ops/state/tpu_fleet_cache.json`), not fresh destructive `tou --cache false`.
- Canonical workspace root on this host is `/kmh-nfs-ssd-us-mount/code/zhichengjiang/working/ai_workspace`; `/home/jzc/...` paths may appear in prompts but are not always mounted.
- HIC daemon suppresses outbound `recipient=group` messages when sender has no active tasks; use direct-message fallback for idle-period acknowledgements.
- `tpu_simple.py` queue/job mutation commands (`dequeue`, `requeue`, `clear`) do not touch remote TPU directly but still mutate shared scheduler state; treat as confirmation-required in shared operations.
- `tpu_simple.py run-direct` bypasses queued scheduler fairness and should be treated as high-risk launch behavior.
- `hic/scripts/restart_web.sh` does not exist; web recovery is `stop_web.sh` + `start_web.sh`.
- Dashboard API mutations include `/api/jobs/clear-all` and `/api/queue/update`; treat these as confirmation-required shared-state writes.
