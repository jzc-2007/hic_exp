---
name: tpu-safety
description: Use before inspecting or changing TPU, GPU, cloud, agent_ops, task queues, dashboards, jobs, data movement, checkpoints, shared disks, or remote experiment state.
---

# TPU Safety

## Required Checks

1. Read `shared/TPU_SAFETY_RED_LINES.md`.
2. If working in `agent_ops`, also read `/home/jzc/zhichengjiang/working/ai_workspace/agent_ops/docs/safety_rules.md`.
3. Prefer cached and read-only inspection.
4. If an action could mutate shared state, ask PI before running it.

## Never Without Explicit Current-Turn Authorization

- Start, resume, kill, delete, deallocate, restart, resize, create, or reconfigure TPU/cloud jobs or resources.
- Run `tpu_simple.py run/resume/daemon`.
- Start or stop `tpu-simple-daemon`.
- Submit TPU dashboard jobs, dequeue, requeue, or clear jobs.
- Run fresh TPU audits such as `tou --cache false` or `yizhitou`.
- Move large cross-region datasets or checkpoints.
- Clear shared locks, unmount disks, or modify shared gcloud/service-account config.

## If Unsure

Return a concise proposed command plus a risk label in chat, or use `questions_to_ask` to ask PI for the missing decision.
