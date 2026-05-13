#!/usr/bin/env bash
set -euo pipefail

SESSION="hic_daily_update"
if [[ "${1:-}" == "--dry-run" ]]; then
  echo "would stop tmux session $SESSION"
  exit 0
fi
if tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux kill-session -t "$SESSION"
  echo "stopped $SESSION"
else
  echo "$SESSION not running"
fi

