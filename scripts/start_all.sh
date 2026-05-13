#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/jzc/zhichengjiang/working/ai_workspace/hic"
if [[ ! -d "$ROOT" ]]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
cd "$ROOT"
bash scripts/start_daemon.sh "${1:-}"
bash scripts/start_web.sh "${1:-}"
bash scripts/start_daily_update.sh "${1:-}"
if [[ "${1:-}" != "--dry-run" && -f var/run/web_url ]]; then
  echo "open $(cat var/run/web_url)"
fi
