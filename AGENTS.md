# AGENTS.md

## HIC Operating Rules

- HIC lives at `/home/jzc/zhichengjiang/working/ai_workspace/hic`.
- Prefer the repo's existing helpers and tests before inventing new machinery.
- Use group/direct chat for routine coordination. Use tasks only for explicit long-running work orders.
- Reply in the same channel as the source message: group questions go to `group`, PI direct messages go to `pi`.
- If you are missing information that affects correctness, use `questions_to_ask` in `AGENT_RESULT_JSON` instead of guessing.
- Do not send routine heartbeat or idle messages. Put idle state in `status_summary`, `current_task`, `STATUS.md`, and `PROGRESS.md`.

## Safety

- Never stop or restart HIC from inside your own wake. Do not run `scripts/stop_all.sh`, `scripts/restart_all.sh`, `scripts/stop_daemon.sh`, or kill `hic_daemon`/`hic_web`. If a restart is needed, ask PI or the outside operator to use Ops -> Restart HIC after your wake has finished.
- Before any work that may affect TPU/GPU/cloud jobs, queues, dashboards, data movement, or shared cluster state, read `shared/TPU_SAFETY_RED_LINES.md` and use the `tpu-safety` skill.
- Do not start, resume, kill, delete, restart, resize, reconfigure, dequeue, requeue, or submit TPU/cloud work without explicit current-turn user authorization.

## Self-Improvement

- For HIC code changes or PI clarification loops, use the `hic-workflow` skill.
- Run focused tests for the files touched; broaden tests when changing shared behavior.
- Keep durable notes compact. Use `python3 scripts/hicctl.py compact-notes` when agent memory grows.
- Do not stage unrelated user changes. In this workspace, `.gitignore` and scratch files may be dirty for unrelated reasons.

## Output Contract

HIC runner prompts require a final `<AGENT_RESULT_JSON>...</AGENT_RESULT_JSON>` object. Include:

- `status_summary`
- `current_task`
- `next_wake_minutes`
- `messages_to_send`
- `wake_requests`
- `tasks_to_update`
- optional `questions_to_ask` when blocked or underspecified
