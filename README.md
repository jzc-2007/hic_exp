# HIC

HIC is a persistent, GUI-first multi-Codex orchestration system.

Project root:

```bash
/home/jzc/zhichengjiang/working/ai_workspace/hic
```

## Start

```bash
cd /home/jzc/zhichengjiang/working/ai_workspace/hic
bash scripts/setup.sh
bash scripts/start_all.sh
```

Then open the URL printed by `start_all.sh`. On this machine, port `8765` is
already used by the existing TPU dashboard, so HIC safely started at:

```bash
http://127.0.0.1:18765/hic
```

If `8765` is free, HIC defaults to:

```bash
http://127.0.0.1:8765/hic
```

The current effective URL is also stored in:

```bash
var/run/web_url
```

## Stop And Restart

```bash
bash scripts/stop_all.sh
bash scripts/restart_all.sh
```

HIC runs in tmux sessions:

- `hic_daemon`
- `hic_web`
- `hic_daily_update`

## GUI

The web UI supports:

- Cyberpunk-themed dashboard with agent status, current tasks, wake buttons,
  relative last-wake labels, and live `hh:mm` next-wake countdowns.
- Group chat and direct chats with every configured agent.
- Optional task/work-order creation for explicit longer work. Routine
  coordination should happen through group/direct messages.
- Safe Ops actions: wake agent, wake all, doctor, tests, restart daemon,
  reload config, DB health, and logs.
- Logs for daemon, web, and each agent.
- Settings page for roster visibility, enable/disable, and adding agents.
- Guide page at `/hic/guide` with operator usage documentation.
- Self-improvement page that records an incident, sends it to `self_evolver`,
  and wakes it.

Operator guide file: `shared/USAGE.md`.

## CLI Fallback

```bash
python3 scripts/hicctl.py status
python3 scripts/hicctl.py send --to group --body "hello"
python3 scripts/hicctl.py send --to main --body "please check"
python3 scripts/hicctl.py wake main
python3 scripts/hicctl.py wake all
python3 scripts/hicctl.py tasks
python3 scripts/hicctl.py task-add --title "..." --owner yiyang_lu --description "..."
python3 scripts/hicctl.py task-done 1
python3 scripts/hicctl.py logs daemon
python3 scripts/hicctl.py logs agent yiyang_lu
python3 scripts/hicctl.py doctor
python3 scripts/hicctl.py test
python3 scripts/hicctl.py compact-notes
```

The CLI is meant for fallback and emergency debugging. The GUI is the main
control surface.

`compact-notes` is the one-click self-evolution helper for keeping each
agent's `MEMORY.md` and `EXPERIENCE.md` concise and structured.

## Git Mirror And Daily Status

This checkout is mirrored to:

```bash
git@github-hic-exp:jzc-2007/hic_exp.git
```

`scripts/daily_status_update.py` writes one deterministic UTC-daily snapshot to
`shared/DAILY_STATUS.md`, commits only that file, and pushes to `origin/main`. The
`hic_daily_update` tmux session runs that script once every 24 hours. Runtime
state such as SQLite files, logs, uploads, Codex session ids, and pycache files
is ignored by git.

## Runner Mode

HIC is currently configured for the real Codex runner. Every agent uses its own
persistent Codex session stored in `agents/<slug>/CODEX_SESSION_ID`; after the
first wake, HIC calls Codex through resume so the agent does not repeat one-time
initialization on every wake. The command receives the agent prompt on stdin and
should return the required
`<AGENT_RESULT_JSON>...</AGENT_RESULT_JSON>` block.

Current command:

```bash
/home/sqa/.npm-global/bin/codex --ask-for-approval never exec -C /home/jzc/zhichengjiang/working/ai_workspace --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox -m gpt-5.3-codex -
```

If this command is removed from `config/settings.yaml`, HIC falls back to mock
mode so the GUI and scheduler remain usable.

## Security

For standalone exposure beyond localhost, set a UI token:

```bash
export HIC_UI_TOKEN="set-a-long-random-value"
bash scripts/restart_all.sh
```

For the current public entry at `kaiming.me/hic`, the existing dashboard
password protects the route before it reaches HIC. HIC does not expose
arbitrary shell execution in the UI; admin actions are allowlisted.

## kaiming.me/hic

As of 2026-05-12, `kaiming.me` keeps routing all non-legacy traffic to the
latest TPU dashboard at `http://localhost:8765`. The dashboard has the existing
password protection and now includes an `HIC` toolbar link.

The dashboard reverse-proxies `/hic` to the local HIC web service on
`127.0.0.1:18765` or the port stored in `var/run/web_port`, so the public entry
point is:

```bash
https://kaiming.me/hic
```

Do not add a separate Cloudflare `/hic.*` ingress unless `HIC_UI_TOKEN` or an
equivalent HIC-specific access layer is configured.

## Tests

```bash
bash scripts/doctor.sh
bash scripts/run_tests.sh
```

The test report lives at `shared/TEST_REPORT.md`.

## Fresh Deploy Without Existing History

To deploy a similar HIC instance elsewhere without carrying current agents'
runtime history (messages, wake logs, sessions):

1. Copy this repository to the new machine/path.
2. Keep or edit `config/agents.yaml` for the roster you want.
3. Remove runtime state in the copied repo before first start:
   - delete `var/hic.sqlite3` (message/task/event DB)
   - delete `var/uploads/*`, `var/run/*`, and old `var/*.log` files
   - delete `agents/*/logs/*` and `agents/*/CODEX_SESSION_ID`
4. Run:
   - `bash scripts/setup.sh`
   - `bash scripts/start_all.sh`

This keeps code/config but starts with a clean runtime history and fresh Codex
sessions per agent.
