# HIC Test Report

Date: 2026-05-13

## Commands Run

```bash
bash scripts/setup.sh
bash scripts/doctor.sh
bash scripts/run_tests.sh
python3 scripts/hicctl.py status
python3 scripts/hicctl.py send --to group --body "smoke test: report status"
python3 scripts/hicctl.py wake all
python3 scripts/hicctl.py status
bash scripts/start_all.sh
curl -sS -i http://127.0.0.1:18765/hic/health
curl -sS -o /tmp/hic_dashboard.html -w '%{http_code}\n' http://127.0.0.1:18765/hic/
curl -sS -o /tmp/hic_chat.html -w '%{http_code}\n' 'http://127.0.0.1:18765/hic/chat?channel=group'
curl -sS -o /tmp/hic_logs.html -w '%{http_code}\n' http://127.0.0.1:18765/hic/logs
curl -sS -o /tmp/hic_exact.html -w '%{http_code}\n' http://127.0.0.1:18765/hic
bash scripts/doctor.sh
```

## Results

- setup: pass
- doctor before start: pass with expected warnings that HIC daemon/web were not started yet
- pytest suite: pass, 13 passed
- CLI status: pass
- CLI send: pass, message persisted
- CLI wake all: pass, wake requests persisted
- daemon start: pass, tmux session `hic_daemon`
- web start: pass, tmux session `hic_web`
- `/hic/health`: pass, HTTP 200 on `127.0.0.1:18765`
- dashboard/chat/logs routes: pass, HTTP 200
- exact `/hic` route: pass, HTTP 200
- doctor after start: pass, daemon heartbeat alive, no overdue agents
- final pytest rerun after chat upload/progress/self-evolver update: pass, 13 passed

## Runner Mode

Real runner is active through `config/settings.yaml`:

```bash
/home/sqa/.npm-global/bin/codex --ask-for-approval never exec -C /home/jzc/zhichengjiang/working/ai_workspace --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox -m gpt-5.3-codex -
```

## Current URL

```bash
http://127.0.0.1:18765/hic
```

HIC defaults to `127.0.0.1:8765`, but that port is already occupied by the
existing TPU dashboard. The start script selected fallback port `18765` and
stored it in `var/run/web_url`.

## Current Notes

- The current web server uses Flask's built-in development server. It is fine
  because public access goes through the existing kaiming.me dashboard password
  gate.
- `HIC_UI_TOKEN` is optional for the current deployment because `/hic` inherits
  the dashboard auth. Set it before adding any direct HIC-only public route.

## Startup Instructions

```bash
cd /home/jzc/zhichengjiang/working/ai_workspace/hic
bash scripts/setup.sh
bash scripts/start_all.sh
```

Open `https://kaiming.me/hic` through the existing dashboard password gate, or
use the local URL printed by `start_all.sh`:

```bash
cat var/run/web_url
```

## Next Recommended Improvements

- Add richer per-agent run pages that show STATUS, PLAN, PROGRESS, and the
  last parsed result side by side.
- Add background snapshots into `var/snapshots/` for daily summaries.
