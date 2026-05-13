#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/jzc/zhichengjiang/working/ai_workspace/hic"
if [[ ! -d "$ROOT" ]]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
SESSION="hic_web"

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "would start tmux session $SESSION for python -m hic.webapp"
  exit 0
fi

cd "$ROOT"
bash scripts/setup.sh >/dev/null
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "$SESSION already running"
  exit 0
fi

PORT="$(PYTHONPATH="$ROOT:${PYTHONPATH:-}" HIC_ROOT="$ROOT" python3 - <<'PY'
import os
import socket
from hic.config import load_settings, root_path

root = root_path()
settings = load_settings(root)
host = os.environ.get("HIC_WEB_HOST") or settings["web"].get("host", "127.0.0.1")
ports = []
if os.environ.get("HIC_WEB_PORT"):
    ports.append(int(os.environ["HIC_WEB_PORT"]))
else:
    ports.append(int(settings["web"].get("port", 8765)))
    ports.extend(int(p) for p in settings["web"].get("fallback_ports", []))
for port in ports:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.25)
    try:
        sock.bind((host, port))
        sock.close()
        print(port)
        break
    except OSError:
        sock.close()
else:
    raise SystemExit("no configured web port is available")
PY
)"

mkdir -p var/run
printf "%s\n" "$PORT" > var/run/web_port
printf "http://127.0.0.1:%s/hic\n" "$PORT" > var/run/web_url
tmux new-session -d -s "$SESSION" "cd '$ROOT' && export PYTHONPATH='$ROOT':\${PYTHONPATH:-} HIC_ROOT='$ROOT' HIC_WEB_PORT='$PORT' && python3 -m hic.webapp --host 127.0.0.1 --port '$PORT' >> var/web.log 2>&1"
echo "started $SESSION at http://127.0.0.1:$PORT/hic"
