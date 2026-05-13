# TPU Safety Red Lines

Source of truth: `/home/jzc/zhichengjiang/working/ai_workspace/agent_ops/docs/safety_rules.md`.
Dashboard-launched Codex agents should also follow
`/home/jzc/zhichengjiang/working/ai_workspace/agent_ops/docs/codex_agent_readme.md`.

Any HIC agent that can inspect or run experiment tasks must know these rules
before touching TPU/GPU/cloud operations.

## Confirmation Required

Ask the user for explicit current-turn confirmation before running anything
that can:

- start, resume, kill, pause, restart, reprioritize, delete, deallocate,
  resize, create, or reconfigure TPU/GPU/cloud jobs or resources;
- consume substantial CPU, GPU, TPU, disk, network, or cloud budget;
- change credentials, permissions, service accounts, SSH keys, or gcloud config;
- delete checkpoints, logs, datasets, experiment outputs, locks, or shared state;
- move large datasets, checkpoints, log trees, WebDataset archives, or GCS
  objects across regions/zones.

## TPU Commands That Need Confirmation

- `tpu run`, `tpu resume`, `tpu rerun`
- `tpu apply`, `tpu applyy`, `tpu reapply`, `tpu reapplyy`, `tpu delete`,
  `tpu restart`
- `tpu mount-disk`, especially with `--force`
- `tpu solve`, `tpu solve-env`, `tpu set-wandb`
- `tpu kill-remote`, `tpu kill-job`, `tpu kill`, `tpu kill-window`
- `tpu clean`, `tpu clear-finished`, `tpu clear-error`, `tpu clear-all`,
  `tpu -czw`, `tpu -czj`
- `tpu add-user`, `tpu del-user`, `tpu init`, `tpu change-ip`
- `tpu lock`, `tpu unlock`, `tpu lock-data`, `tpu unlock-data`, `tpu rm-lock`
- `tpu clean-eu`, `tpu clean-us`, especially with `-f`

## `tpu_simple.py` Commands That Need Confirmation

- `agent_ops/scripts/tpu_simple.py run ...`
- `agent_ops/scripts/tpu_simple.py resume ...`
- `agent_ops/scripts/tpu_simple.py daemon ...`
- starting or stopping `tpu-simple-daemon`
- submitting a job through the TPU dashboard
- `dequeue`, `requeue`, or `clear` when it changes job state

`resume` is destructive: it kills remote Python jobs on all workers of the
selected TPU before launching the resumed job.

## Fresh Audit Red Lines

Do not run these without explicit confirmation:

- `tou --cache false`
- `yizhitou`
- mount, repair, cleanup, delete, or recreate scripts

Fresh TPU audits can delete preempted or repeatedly timing-out TPUs and can
spawn background mount operations. Prefer cached status (`tou`,
`tou --cache true`, queue/status/check pages) and read-only inspections.

## Data And Cost Red Lines

- Do not repeatedly probe missing WebDataset shards, GCS paths, HTTP URLs,
  wandb artifacts, Hugging Face files, or checkpoint paths. Stop after a small
  bounded check, record the exact path/error, and ask.
- Do not launch distributed TPU/GPU jobs just to test whether data exists.
- Do not write loops that hammer `gcloud`, GCS, HTTP dataset endpoints, wandb,
  Hugging Face, or internal APIs.
- Do not fill shared disks with copied datasets, expanded archives, duplicate
  checkpoints, or unbounded logs.
- Do not kill another user's process, clear shared locks, unmount disks, or
  change shared service-account/gcloud configuration.

When unsure, return a proposed command plus a risk label instead of running it.

## Usually Safe Read-Only Checks

- `tpu tldr`, `tpu help <command>`, `tpu list-users`
- `tpu ls <username>`, `tpu get-dir <number> <username>`
- `tpu check <username>`, `tpu check-simp <username>`, `tpu vq [username]`
- `tpu find <tpu_type>`, `tpu describe <tpu>`, `tpu check-status <tpu>`
- `tpu get-settings <username>`, `tpu show-config-alias <username>`
- `tou` or `tou --cache true` when cache exists
- `tmux has-session`, `ps`, `tmux capture-pane`, `tail`, `rg`, and dashboard
  status reads that do not mutate jobs or shared state
