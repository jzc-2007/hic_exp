from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import os
import re

import yaml


REQUESTED_PROJECT_ROOT = Path("/home/jzc/zhichengjiang/working/ai_workspace/hic")
PROJECT_ROOT = Path(
    os.environ.get(
        "HIC_ROOT",
        str(REQUESTED_PROJECT_ROOT if REQUESTED_PROJECT_ROOT.exists() else Path(__file__).parents[1]),
    )
).absolute()


@dataclass(frozen=True)
class AgentConfig:
    slug: str
    display_name: str
    role: str
    enabled: bool = True
    wake_interval_minutes: int = 240
    responsibilities: list[str] = field(default_factory=list)


DEFAULT_SETTINGS: dict[str, Any] = {
    "web": {
        "host": "127.0.0.1",
        "port": 8765,
        "path_prefix": "/hic",
        "fallback_ports": [18765, 18766, 18767],
    },
    "daemon": {
        "poll_interval_seconds": 30,
        "max_sleep_minutes": 240,
        "retry_minutes": 15,
        "stale_heartbeat_minutes": 5,
    },
    "runner": {
        "default_next_wake_minutes": 240,
        "idle_next_wake_minutes": 240,
        "timeout_seconds": 1800,
        "mock_when_unconfigured": True,
        "codex_cmd": "",
    },
    "ops": {
        "log_tail_lines": 300,
        "public_url": "https://kaiming.me/hic",
        "tpu_dashboard_url": "https://kaiming.me/",
    },
}


DEFAULT_AGENT_DOCS = {
    "README.md": "# {display_name}\n\nRole: {role}\n",
    "MEMORY.md": "# MEMORY\n\nStable long-term lessons go here.\n",
    "STATUS.md": (
        "# STATUS\n\n"
        "- current_task: Awaiting assignment.\n"
        "- status_summary: Initialized.\n"
        "- blockers: None.\n"
        "- last_wake_at:\n"
        "- next_wake_at:\n"
    ),
    "PLAN.md": "# PLAN\n\n- Read messages, tasks, memory, and protocol on each wake.\n",
    "PROGRESS.md": "# PROGRESS\n\nAppend-only progress log.\n",
    "EXPERIENCE.md": "# EXPERIENCE\n\nCommands, gotchas, and practical lessons go here.\n",
}


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9_ -]+", "", value)
    value = re.sub(r"[\s-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        raise ValueError("slug cannot be empty")
    return value


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def root_path(root: Path | str | None = None) -> Path:
    return Path(root or PROJECT_ROOT).absolute()


def load_yaml(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or default
    return data


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=False)


def load_agents(root: Path | str | None = None) -> list[AgentConfig]:
    root = root_path(root)
    path = root / "config" / "agents.yaml"
    data = load_yaml(path, {"agents": []})
    rows = data.get("agents", []) if isinstance(data, dict) else []
    agents: list[AgentConfig] = []
    seen: set[str] = set()
    for row in rows:
        slug = slugify(str(row["slug"]))
        if slug in seen:
            raise ValueError(f"duplicate agent slug: {slug}")
        seen.add(slug)
        responsibilities = row.get("responsibilities") or []
        if isinstance(responsibilities, str):
            responsibilities = [responsibilities]
        agents.append(
            AgentConfig(
                slug=slug,
                display_name=str(row.get("display_name") or slug),
                role=str(row.get("role") or "agent"),
                enabled=bool(row.get("enabled", True)),
                wake_interval_minutes=int(row.get("wake_interval_minutes") or 240),
                responsibilities=[str(item) for item in responsibilities],
            )
        )
    if not agents:
        raise ValueError(f"no agents configured in {path}")
    return agents


def agents_to_yaml_rows(agents: list[AgentConfig]) -> list[dict[str, Any]]:
    return [
        {
            "slug": agent.slug,
            "display_name": agent.display_name,
            "role": agent.role,
            "enabled": bool(agent.enabled),
            "wake_interval_minutes": int(agent.wake_interval_minutes),
            "responsibilities": list(agent.responsibilities),
        }
        for agent in agents
    ]


def save_agents(agents: list[AgentConfig], root: Path | str | None = None) -> None:
    root = root_path(root)
    write_yaml(root / "config" / "agents.yaml", {"agents": agents_to_yaml_rows(agents)})


def load_settings(root: Path | str | None = None) -> dict[str, Any]:
    root = root_path(root)
    data = load_yaml(root / "config" / "settings.yaml", {})
    if not isinstance(data, dict):
        data = {}
    return deep_merge(DEFAULT_SETTINGS, data)


def update_agent_enabled(slug: str, enabled: bool, root: Path | str | None = None) -> AgentConfig:
    root = root_path(root)
    agents = load_agents(root)
    updated: list[AgentConfig] = []
    found: AgentConfig | None = None
    for agent in agents:
        if agent.slug == slug:
            found = AgentConfig(
                slug=agent.slug,
                display_name=agent.display_name,
                role=agent.role,
                enabled=enabled,
                wake_interval_minutes=agent.wake_interval_minutes,
                responsibilities=agent.responsibilities,
            )
            updated.append(found)
        else:
            updated.append(agent)
    if found is None:
        raise KeyError(slug)
    save_agents(updated, root)
    return found


def add_agent(
    slug: str,
    display_name: str,
    role: str,
    responsibilities: list[str] | None = None,
    root: Path | str | None = None,
) -> AgentConfig:
    root = root_path(root)
    slug = slugify(slug)
    agents = load_agents(root)
    if any(agent.slug == slug for agent in agents):
        raise ValueError(f"agent already exists: {slug}")
    agent = AgentConfig(
        slug=slug,
        display_name=display_name or slug,
        role=role or "agent",
        enabled=True,
        wake_interval_minutes=240,
        responsibilities=responsibilities or [],
    )
    save_agents(agents + [agent], root)
    ensure_agent_dir(agent, root)
    return agent


def write_text_if_missing(path: Path, body: str) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def ensure_agent_dir(agent: AgentConfig, root: Path | str | None = None) -> None:
    root = root_path(root)
    agent_dir = root / "agents" / agent.slug
    for subdir in ("inbox", "outbox", "scratch", "logs"):
        (agent_dir / subdir).mkdir(parents=True, exist_ok=True)
    for name, template in DEFAULT_AGENT_DOCS.items():
        write_text_if_missing(
            agent_dir / name,
            template.format(display_name=agent.display_name, role=agent.role),
        )
    if agent.slug == "yiyang_lu":
        write_text_if_missing(agent_dir / "INFRA_MAP.md", "# INFRA_MAP\n\nPending first infra wake.\n")
        write_text_if_missing(agent_dir / "RUNBOOK.md", "# RUNBOOK\n\nPending first infra wake.\n")


def ensure_shared_docs(root: Path | str | None = None) -> None:
    root = root_path(root)
    defaults = {
        "ONBOARDING.md": "# HIC Onboarding\n\nRead shared/PROTOCOL.md and your own agent files.\n",
        "PROTOCOL.md": "# Agent Protocol\n\nRead messages, tasks, memory, do useful work, and return AGENT_RESULT_JSON.\n",
        "TPU_SAFETY_RED_LINES.md": (
            "# TPU Safety Red Lines\n\n"
            "Read agent_ops/docs/safety_rules.md before TPU/GPU/cloud work. "
            "Ask the user before starting/resuming/killing jobs, running fresh "
            "TPU audits, moving large data, or mutating shared cluster state.\n"
        ),
        "SYSTEM_DESIGN.md": "# HIC System Design\n\nSQLite, daemon, web UI, and per-agent directories.\n",
        "TASK_BOARD.md": "# Task Board\n\nDatabase table `tasks` is the source of truth.\n",
        "CHANGELOG.md": "# Changelog\n",
        "DECISIONS.md": "# Decisions\n",
        "INCIDENTS.md": "# Incidents And Improvements\n",
        "VISUAL_FIRST.md": "# Visual First\n\nThe web UI is the primary control surface.\n",
        "TESTING.md": "# Testing\n\nRun `bash scripts/run_tests.sh`.\n",
    }
    for name, body in defaults.items():
        write_text_if_missing(root / "shared" / name, body)


def ensure_project_structure(root: Path | str | None = None) -> None:
    root = root_path(root)
    for rel in (
        "config",
        "scripts",
        "hic/tests",
        "web/static",
        "web/templates",
        "shared",
        "var/locks",
        "var/run",
        "var/snapshots",
        "var/uploads",
        "agents",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)
    ensure_shared_docs(root)
    for agent in load_agents(root):
        ensure_agent_dir(agent, root)


def agent_dir(slug: str, root: Path | str | None = None) -> Path:
    return root_path(root) / "agents" / slug


def read_file(path: Path, limit: int = 20000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > limit:
        return text[-limit:]
    return text


def append_file(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(body)


def write_status_file(
    slug: str,
    current_task: str,
    status_summary: str,
    blockers: str = "None.",
    last_wake_at: str | None = None,
    next_wake_at: str | None = None,
    root: Path | str | None = None,
) -> None:
    path = agent_dir(slug, root) / "STATUS.md"
    body = (
        "# STATUS\n\n"
        f"- current_task: {current_task or ''}\n"
        f"- status_summary: {status_summary or ''}\n"
        f"- blockers: {blockers or 'None.'}\n"
        f"- last_wake_at: {last_wake_at or ''}\n"
        f"- next_wake_at: {next_wake_at or ''}\n"
    )
    path.write_text(body, encoding="utf-8")
