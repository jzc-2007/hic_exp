#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/jzc/zhichengjiang/working/ai_workspace/hic"
if [[ ! -d "$ROOT" ]]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
cd "$ROOT"

python3 - <<'PY'
import importlib
import subprocess
import sys

needed = {"flask": "Flask", "yaml": "PyYAML", "pytest": "pytest"}
missing = []
for module, package in needed.items():
    try:
        importlib.import_module(module)
    except Exception:
        missing.append(package)
if missing:
    print("Installing missing Python packages:", ", ".join(missing))
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", *missing])
PY

PYTHONPATH="$ROOT:${PYTHONPATH:-}" HIC_ROOT="$ROOT" python3 - <<'PY'
from pathlib import Path
from hic import db
from hic.config import ensure_project_structure, load_agents, root_path

root = root_path()
ensure_project_structure(root)
conn = db.connect(root=root)
try:
    db.init_db(conn)
    db.upsert_agents(conn, load_agents(root))
finally:
    conn.close()
for path in ["var/daemon.log", "var/web.log"]:
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch(exist_ok=True)
print(f"HIC setup complete: {root}")
PY
