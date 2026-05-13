# Agent Protocol

On every wake, an agent must:

1. Read new group messages.
2. Read new direct messages.
3. Read optional assigned tasks/work orders, if any.
4. Read own STATUS.md, PLAN.md, MEMORY.md, and EXPERIENCE.md.
5. Read shared/TPU_SAFETY_RED_LINES.md before any task that may inspect or
   affect TPU/GPU/cloud jobs, dashboards, queues, data movement, or shared
   cluster state.
6. Do useful work.
7. Append progress to PROGRESS.md.
8. Update STATUS.md.
9. Send messages only when needed. Do not post routine heartbeat or idle
   status updates to group chat; HIC displays those separately on Dashboard
   and Logs.
   Message priority is `1` for `normal` (send only, no wake) or `2` for
   `important` (wake the direct recipient, or mentioned group targets).
10. Routine coordination should happen through group/direct messages. Tasks
   are optional explicit work orders, not the default way to talk to agents.
   Use `current_task` for real current work; if there is no concrete work, say
   the agent is waiting for messages or explicit work.
11. Each agent runs in a persistent Codex session resumed across wakes. Reuse
   prior context instead of redoing one-time initialization, while still
   reading new messages and changed durable files for the current wake.
12. For recurring workflows, simplify and automate: if the same action is done
   repeatedly, add/update a one-click helper script or command and document it.
13. Maintain durable self-evolution memory in structured, compact form:
   - Keep `MEMORY.md` and `EXPERIENCE.md` organized with `##` sections and
     concise bullet points.
   - Keep both files bounded (target <= 8 KB each). Summarize older content
     instead of unbounded growth.
   - Use `python3 scripts/hicctl.py compact-notes` to compact notes when needed.
14. Never stop or restart HIC from inside your own wake. Do not run
   `scripts/stop_all.sh`, `scripts/restart_all.sh`, `scripts/stop_daemon.sh`,
   or kill `hic_daemon`/`hic_web`; that can interrupt your runner before a
   chat reply is sent. If HIC needs a restart, message PI and ask the outer
   operator to do it.
15. Reply in the same channel as the source message:
   - Answer group messages in group chat with `recipient: "group"`.
   - Answer PI direct/private messages with `recipient: "pi"`.
   - Do not move a group thread into direct/private chat unless the human
     explicitly asks for a private reply.
   - Group messages are visible to every agent on their next wake. `@agent`
     and `@all` affect wake targeting only; they do not make the message
     private or hide it from other agents.
16. If blocked or materially uncertain, use `questions_to_ask` instead of
   guessing. Ask at most three concrete PI-facing questions. HIC will send
   them to PI, mark the agent as `needs input`, and resume the same Codex
   session when PI replies with an important message.
17. Request wakeups if needed.
18. Return AGENT_RESULT_JSON.

Agents end each run with:

```json
<AGENT_RESULT_JSON>
{
  "status_summary": "one sentence",
  "current_task": "short description",
  "next_wake_minutes": 240,
  "messages_to_send": [
    {"recipient": "group", "body": "...", "priority": 1}
  ],
  "wake_requests": [
    {"target_agent": "yiyang_lu", "reason": "..."}
  ],
  "tasks_to_update": [
    {"task_id": 1, "status": "in_progress", "note": "..."}
  ],
  "questions_to_ask": [
    {"body": "Which behavior should I implement?", "options": ["A", "B"]}
  ]
}
</AGENT_RESULT_JSON>
```

## main

main maintains shared/TASK_BOARD.md, shared/DECISIONS.md,
shared/INCIDENTS.md, and shared/SYSTEM_DESIGN.md. User complaints about HIC
are improvement requests: record the issue, classify it, plan a fix, assign
or implement it, test it, update docs, and report back.

## yiyang_lu

On first wake, yiyang_lu reads
/home/jzc/zhichengjiang/working/ai_workspace/agent_ops carefully and creates
or updates agents/yiyang_lu/INFRA_MAP.md and agents/yiyang_lu/RUNBOOK.md.
Record commands, task execution protocol, repair steps, and gotchas.

## workers

Workers read shared/ONBOARDING.md, shared/TPU_SAFETY_RED_LINES.md, and the
yiyang_lu runbook if it exists.
If blocked, ask in group chat and tag main or yiyang_lu. Progress reports
should be concise and concrete.

## TPU / Remote Task Safety

`agent_ops/docs/safety_rules.md` is the source of truth. Any agent with a task
that can run experiments or touch TPU/GPU/cloud infrastructure must treat these
as red lines:

- Do not start, resume, kill, delete, deallocate, restart, resize, create, or
  reconfigure TPU/cloud jobs or resources without explicit current-turn user
  confirmation.
- Do not run `tpu_simple.py run/resume/daemon`, start or stop
  `tpu-simple-daemon`, submit TPU dashboard jobs, or dequeue/requeue/clear jobs
  without explicit confirmation.
- Do not run fresh TPU audits (`tou --cache false`, `yizhitou`) or
  mount/repair/cleanup/delete/recreate scripts unless the user asks and the
  side effects are stated.
- Do not launch distributed jobs just to test data existence, repeatedly probe
  missing remote data, hammer cloud APIs, move large cross-region datasets or
  checkpoints, fill shared disks, kill another user's process, clear locks, or
  modify shared gcloud/service-account config.
- Prefer cached/read-only inspections. When unsure, return a proposed command
  plus a risk label instead of running it.

## idle wakes

When there are no active assigned/open tasks after processing messages, request
`next_wake_minutes: 240`. Idle status belongs in `status_summary`,
`STATUS.md`, and `PROGRESS.md`, not in group chat.

## self_evolver

`self_evolver` owns HIC self-improvement work. It may edit
`/home/jzc/zhichengjiang/working/ai_workspace/hic` and should keep logs plus
PROGRESS.md up to date. Like every HIC agent, it uses a persistent Codex
session history across wakes. It must not restart or stop HIC from inside its
own wake; request an outside restart through chat instead.
