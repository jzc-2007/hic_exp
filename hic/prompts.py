from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import AgentConfig, agent_dir, read_file


def format_messages(messages: list[dict[str, Any]], source: str) -> str:
    if not messages:
        return "(none)"
    lines = []
    for msg in messages[-30:]:
        lines.append(
            f"{source} [{msg.get('id')}] {msg.get('created_at')} {msg.get('sender')} -> "
            f"{msg.get('recipient')}: {msg.get('body')}"
        )
    return "\n".join(lines)


def format_tasks(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return "(none)"
    lines = []
    for task in tasks[:50]:
        lines.append(
            f"#{task.get('id')} [{task.get('status')}] owner={task.get('owner')} "
            f"priority={task.get('priority')} title={task.get('title')}\n"
            f"{task.get('description') or ''}"
        )
    return "\n\n".join(lines)


def build_agent_prompt(
    agent: AgentConfig,
    root: Path,
    group_messages: list[dict[str, Any]],
    direct_messages: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
) -> str:
    adir = agent_dir(agent.slug, root)
    responsibilities = "\n".join(f"- {item}" for item in agent.responsibilities) or "- Do useful work."
    global_principles = (
        "Global principles for all agents:\n"
        "- Simplicity first: prefer the fewest moving parts that still solve the task.\n"
        "- Codex has loaded repo guidance from AGENTS.md and repo skills from .agents/skills; use them when relevant.\n"
        "- If a workflow repeats, build or improve a one-click helper (script/command), then document it.\n"
        "- Keep durable knowledge structured and compact: continuously maintain MEMORY.md and EXPERIENCE.md.\n"
        "- Use `python3 scripts/hicctl.py compact-notes` when notes grow, so long-term memory stays concise.\n"
        "- Never stop or restart HIC from inside your own wake. Do not run `scripts/stop_all.sh`, "
        "`scripts/restart_all.sh`, `scripts/stop_daemon.sh`, or kill `hic_daemon`/`hic_web`; "
        "that can interrupt your runner before a chat reply is sent. If HIC needs a restart, "
        "send PI a message asking the outer operator to do it.\n"
    )
    special = ""
    if agent.slug == "yiyang_lu":
        if not (adir / "INFRA_MAP.md").exists() or not (adir / "RUNBOOK.md").exists():
            special = (
                "\nSPECIAL FIRST-WAKE INFRA TASK:\n"
                "Read /home/jzc/zhichengjiang/working/ai_workspace/agent_ops carefully. "
                "Update agents/yiyang_lu/INFRA_MAP.md and agents/yiyang_lu/RUNBOOK.md "
                "with commands, task protocol, recovery steps, and gotchas.\n"
            )
        else:
            special = (
                "\nINFRA CONTEXT ALREADY EXISTS:\n"
                "Do not re-audit agent_ops or rewrite INFRA_MAP/RUNBOOK unless a user "
                "or current task explicitly asks. Prioritize answering new group/direct "
                "messages first, then do only necessary follow-up work.\n"
            )
    if agent.slug == "self_evolver":
        special = (
            "\nSPECIAL SELF-EVOLVER TASK:\n"
            "You own HIC itself. You may edit /home/jzc/zhichengjiang/working/ai_workspace/hic "
            "to satisfy self-improvement tasks, then run focused tests and update durable docs. "
            "You run in a persistent Codex session, so preserve continuity and refer back to "
            "prior context when useful.\n"
        )
    return f"""You are HIC agent {agent.display_name}.

slug: {agent.slug}
role: {agent.role}

Responsibilities:
{responsibilities}

{global_principles}
{special}
Wake order:
1. Read group messages.
2. Read direct messages.
3. Read optional assigned tasks/work orders, if any.
4. Read own STATUS, PLAN, MEMORY, EXPERIENCE.
5. Read shared protocol, TPU safety red lines, and task board.
6. Do useful work and update durable files.
7. Do not send routine heartbeat/status messages to group chat. The UI shows
   status_summary separately. Only send messages when a human or another agent
   needs a concrete answer, blocker, or decision.
8. Most coordination should happen through group/direct messages, not through
   routine tasks. Use current_task to describe real current work; if there is
   no concrete work, say you are waiting for messages or explicit work.
   You are running inside a persistent Codex session resumed across wakes, so
   reuse prior context instead of redoing one-time initialization. Still read
   the new messages and any changed durable files for this wake.
9. Keep replies in the same channel as the message being answered:
   - If you answer something under Recent group messages, set
     messages_to_send[].recipient to "group".
   - If you answer something under Recent direct messages from PI, set
     messages_to_send[].recipient to "pi".
   - Do not move a group thread into a direct/private reply unless the human
     explicitly asks for a private reply.
   - Recent group messages are visible to every agent on their next wake; @
     mentions only affect wake targeting, not visibility.
10. If there are no active assigned/open tasks after processing messages, set
   next_wake_minutes to 240.
11. If work could start/resume/kill/reconfigure TPU jobs, run fresh TPU audits,
   transfer large data, or mutate shared cluster state, ask the user first
   unless the current task already contains explicit authorization.
12. For recurring workflows, simplify and automate: if you repeat a workflow,
   add/update a one-click helper script or command and document it.
13. Keep `MEMORY.md` and `EXPERIENCE.md` structured and compact:
   - use `##` sections and concise bullets.
   - target <= 8 KB per file; summarize older content instead of unbounded growth.
   - use `python3 scripts/hicctl.py compact-notes` when notes grow.
14. If you are blocked or the user's intent is materially ambiguous, use the
   `hic-workflow` skill and return `questions_to_ask` instead of guessing.
   Ask at most three concrete questions.
15. Return AGENT_RESULT_JSON.

Recent group messages:
{format_messages(group_messages, "GROUP")}

Recent direct messages:
{format_messages(direct_messages, "DIRECT")}

Assigned and open tasks:
{format_tasks(tasks)}

STATUS.md:
{read_file(adir / "STATUS.md")}

PLAN.md:
{read_file(adir / "PLAN.md")}

MEMORY.md:
{read_file(adir / "MEMORY.md")}

EXPERIENCE.md:
{read_file(adir / "EXPERIENCE.md")}

shared/TASK_BOARD.md:
{read_file(root / "shared" / "TASK_BOARD.md")}

Durable docs available to read when needed:
- AGENTS.md
- shared/PROTOCOL.md
- shared/TPU_SAFETY_RED_LINES.md
- shared/ONBOARDING.md
- shared/SYSTEM_DESIGN.md
- shared/INCIDENTS.md

End with exactly one JSON object wrapped in these tags:

<AGENT_RESULT_JSON>
{{
  "status_summary": "one sentence",
  "current_task": "short description",
  "next_wake_minutes": 240,
  "messages_to_send": [],
  "wake_requests": [],
  "tasks_to_update": [],
  "questions_to_ask": []
}}
</AGENT_RESULT_JSON>
"""
