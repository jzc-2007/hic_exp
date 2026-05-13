#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import os
import sys

ROOT = Path(os.environ.get("HIC_ROOT", "/home/jzc/zhichengjiang/working/ai_workspace/hic")).absolute()
sys.path.insert(0, str(ROOT))

from hic import db  # noqa: E402
from hic.config import add_agent, load_agents, root_path  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Add a HIC agent")
    parser.add_argument("slug")
    parser.add_argument("--display-name", default="")
    parser.add_argument("--role", default="agent")
    parser.add_argument("--responsibility", action="append", default=[])
    parser.add_argument("--root", default=os.environ.get("HIC_ROOT", str(ROOT)))
    args = parser.parse_args(argv)
    root = root_path(args.root)
    agent = add_agent(args.slug, args.display_name or args.slug, args.role, args.responsibility, root)
    conn = db.connect(root=root)
    try:
        db.init_db(conn)
        db.upsert_agents(conn, load_agents(root))
    finally:
        conn.close()
    print(f"added {agent.slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
