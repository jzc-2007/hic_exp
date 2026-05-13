#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/jzc/zhichengjiang/working/ai_workspace/hic"
if [[ ! -d "$ROOT" ]]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
SESSION="hic_daemon"

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "would start tmux session $SESSION for python -m hic.daemon"
  exit 0
fi

cd "$ROOT"
bash scripts/setup.sh >/dev/null
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "$SESSION already running"
  exit 0
fi
tmux new-session -d -s "$SESSION" "cd '$ROOT' && export PYTHONPATH='$ROOT':\${PYTHONPATH:-} HIC_ROOT='$ROOT' && python3 -m hic.daemon"
echo "started $SESSION"
