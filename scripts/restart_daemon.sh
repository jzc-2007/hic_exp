#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/jzc/zhichengjiang/working/ai_workspace/hic"
if [[ ! -d "$ROOT" ]]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
cd "$ROOT"
bash scripts/stop_daemon.sh "${1:-}"
if [[ "${1:-}" == "--dry-run" ]]; then
  bash scripts/start_daemon.sh --dry-run
else
  bash scripts/start_daemon.sh
fi
