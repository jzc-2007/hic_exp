from __future__ import annotations

from pathlib import Path
import os
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


AGENTS_YAML = """
agents:
  - slug: main
    display_name: main
    role: supervisor
    enabled: true
    wake_interval_minutes: 120
    responsibilities:
      - coordinate
  - slug: yiyang_lu
    display_name: yiyang lu
    role: infra manager
    enabled: true
    wake_interval_minutes: 180
    responsibilities:
      - manage infra
  - slug: qiao_sun
    display_name: Qiao sun
    role: worker
    enabled: true
    wake_interval_minutes: 180
    responsibilities:
      - work
"""


SETTINGS_YAML = """
web:
  host: 127.0.0.1
  port: 8765
  path_prefix: /hic
  fallback_ports: [18765]
daemon:
  poll_interval_seconds: 1
  max_sleep_minutes: 240
  retry_minutes: 15
  stale_heartbeat_minutes: 5
runner:
  default_next_wake_minutes: 240
  idle_next_wake_minutes: 240
  timeout_seconds: 5
  mock_when_unconfigured: true
  codex_cmd: ""
ops:
  log_tail_lines: 100
  public_url: https://kaiming.me/hic
"""


@pytest.fixture
def sample_root(tmp_path, monkeypatch):
    root = tmp_path / "hic"
    (root / "config").mkdir(parents=True)
    (root / "config" / "agents.yaml").write_text(AGENTS_YAML, encoding="utf-8")
    (root / "config" / "settings.yaml").write_text(SETTINGS_YAML, encoding="utf-8")
    monkeypatch.setenv("HIC_ROOT", str(root))
    monkeypatch.delenv("HIC_CODEX_CMD", raising=False)
    monkeypatch.delenv("HIC_UI_TOKEN", raising=False)
    return root
