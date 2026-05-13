---
name: hic-workflow
description: Use for HIC self-improvement work, dashboard/daemon/runner changes, service restarts, GitHub pushes, or when a HIC agent is blocked and needs PI clarification.
---

# HIC Workflow

## Self-Evolve Workflow

1. Inspect state with `git status --short`, `python3 scripts/hicctl.py doctor`, and focused code reads.
2. Keep changes scoped. Do not touch unrelated dirty files.
3. Preserve PI-facing behavior unless the request explicitly changes it.
4. If you change shared behavior, update tests and `shared/CHANGELOG.md`.
5. Run focused tests first, then all `hic/tests` when the change touches daemon, runner, DB, prompts, or UI state.
6. Restart only from outside an agent wake. If you are running as a HIC agent and a restart is needed, ask PI or the outside operator to use Ops -> Restart HIC after your wake finishes.
7. When committing, stage only intentional files and push to `origin main`.

## Grill Me / Clarification

Ask PI for the smallest useful clarification instead of guessing. Keep the agent's Codex session alive through resume by recording the question in HIC chat and waiting for PI to answer.

## Output Pattern

In the final `AGENT_RESULT_JSON`, include `questions_to_ask`:

```json
{
  "status_summary": "Needs PI input before continuing.",
  "current_task": "Waiting for PI input.",
  "next_wake_minutes": 240,
  "messages_to_send": [],
  "wake_requests": [],
  "tasks_to_update": [],
  "questions_to_ask": [
    {
      "body": "Which behavior should I implement?",
      "options": ["A: keep current routing", "B: make group replies mandatory"]
    }
  ]
}
```

## Question Style

- Ask at most three questions.
- Prefer a concrete default or 2-4 options when possible.
- Include why the answer matters only if it changes risk, cost, or behavior.
- Do not ask when a conservative repo-consistent choice is obvious and safe.

## Guardrails

- Do not run `scripts/stop_all.sh` or `scripts/restart_all.sh` from inside a HIC agent wake.
- Finish the reply first, then let the outside Ops restart apply the new code.
- Do not commit runtime state: logs, SQLite DB, uploads, Codex session ids, pycache, or scratch files.
- If HIC behavior is confusing to PI, prefer making state visible in Dashboard/Chat over adding hidden queues.
