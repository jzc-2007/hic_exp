#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/jzc/zhichengjiang/working/ai_workspace/hic"
if [[ ! -d "$ROOT" ]]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
cd "$ROOT"
PYTHONPATH="$ROOT:${PYTHONPATH:-}" HIC_ROOT="$ROOT" python3 scripts/hicctl.py doctor
