#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/jzc/zhichengjiang/working/ai_workspace/hic"
if [[ ! -d "$ROOT" ]]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
cd "$ROOT"

SESSION="hic_daily_update"
if [[ "${1:-}" == "--dry-run" ]]; then
  echo "would start tmux session $SESSION for daily git status updates"
  exit 0
fi
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "$SESSION already running"
  exit 0
fi

mkdir -p var
tmux new-session -d -s "$SESSION" "cd '$ROOT' && while true; do PYTHONPATH='$ROOT':\${PYTHONPATH:-} HIC_ROOT='$ROOT' python3 scripts/daily_status_update.py --push >> var/daily_update.log 2>&1 || true; sleep 86400; done"
echo "started $SESSION"

