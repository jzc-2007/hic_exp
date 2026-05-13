#!/usr/bin/env bash
set -euo pipefail

ROOT="${HIC_ROOT:-/home/jzc/zhichengjiang/working/ai_workspace/hic}"
if [[ ! -d "$ROOT" ]]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
SESSION="hic_daemon"
MODE="${1:-}"
if [[ "$MODE" == "--dry-run" ]]; then
  echo "would stop tmux session $SESSION"
  exit 0
fi
if [[ "$MODE" != "--force" ]]; then
  active_locks=()
  shopt -s nullglob
  for lock in "$ROOT"/var/locks/*.lock; do
    pid="$(cat "$lock" 2>/dev/null || true)"
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
      active_locks+=("$(basename "$lock" .lock):$pid")
    else
      rm -f "$lock"
    fi
  done
  shopt -u nullglob
  if (( ${#active_locks[@]} )); then
    printf "refusing to stop %s; active agent wake(s): %s\n" "$SESSION" "${active_locks[*]}"
    echo "wait for the wake to finish, or rerun with --force to interrupt it."
    exit 2
  fi
fi
if tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux kill-session -t "$SESSION"
  echo "stopped $SESSION"
else
  echo "$SESSION not running"
fi
