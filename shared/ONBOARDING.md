# HIC Onboarding

HIC is a persistent, GUI-first multi-agent workspace. The SQLite database is
the source of truth for roster, messages, tasks, wake requests, and events.
Each agent also has durable local files under agents/<slug>/ for resume.

Start by reading:

- shared/PROTOCOL.md
- shared/TPU_SAFETY_RED_LINES.md
- shared/TASK_BOARD.md
- your own STATUS.md, PLAN.md, MEMORY.md, EXPERIENCE.md
- relevant direct and group messages

If a task touches `agent_ops`, TPU/GPU jobs, dashboards, queues, remote
experiments, GCS/data movement, or shared cluster state, read
`/home/jzc/zhichengjiang/working/ai_workspace/agent_ops/docs/safety_rules.md`
before acting. Prefer read-only/cached inspection first, and ask the user before
any command that starts/resumes/kills jobs, runs fresh TPU audits, mutates
shared state, or consumes meaningful cloud resources.

Never assume terminal-only control. Prefer updates that show up in the GUI:
messages, task changes, status summaries, progress files, and logs.
