from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json
import os
import re
import selectors
import shlex
import subprocess
import time

from .config import AgentConfig, agent_dir, append_file, load_settings, read_file
from .prompts import build_agent_prompt
from .scheduler import iso


RESULT_RE = re.compile(r"<AGENT_RESULT_JSON>\s*(\{.*?\})\s*</AGENT_RESULT_JSON>", re.S)


@dataclass
class RunnerResult:
    raw_output: str
    parsed: dict[str, Any]
    mode: str
    parse_error: str | None = None
    log_path: Path | None = None


def extract_agent_messages(raw_output: str, limit: int = 4000) -> list[str]:
    messages: list[str] = []
    for line in raw_output.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if str(event.get("type") or "").lower() != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").lower() != "agent_message":
            continue
        text = str(item.get("text") or "").strip()
        if text:
            messages.append(text)

    if not messages and "[hic assistant text]" in raw_output:
        text = raw_output.split("[hic assistant text]", 1)[1].strip()
        if text:
            messages.append(text)

    clipped: list[str] = []
    for text in messages[-3:]:
        if len(text) > limit:
            text = text[: limit - 3].rstrip() + "..."
        clipped.append(text)
    return clipped


def default_result(
    agent_slug: str,
    reason: str = "fallback",
    assistant_messages: list[str] | None = None,
) -> dict[str, Any]:
    messages_to_send = [
        {
            "recipient": "pi",
            "body": message,
            "priority": 1,
            "wakes_recipient": False,
        }
        for message in assistant_messages or []
        if message.strip()
    ]
    return {
        "status_summary": f"{agent_slug} completed a {reason} wake.",
        "current_task": "Reviewing messages and deciding whether work is needed.",
        "next_wake_minutes": 240,
        "messages_to_send": messages_to_send,
        "wake_requests": [],
        "tasks_to_update": [],
        "questions_to_ask": [],
    }


def parse_agent_result(raw_output: str, agent_slug: str) -> tuple[dict[str, Any], str | None]:
    assistant_messages = extract_agent_messages(raw_output)
    matches = list(RESULT_RE.finditer(raw_output))
    candidate = matches[-1].group(1) if matches else ""
    if not candidate:
        start = raw_output.find("{")
        end = raw_output.rfind("}")
        if start >= 0 and end > start:
            candidate = raw_output[start : end + 1]
    if not candidate:
        return default_result(agent_slug, "unparsed", assistant_messages), "missing AGENT_RESULT_JSON"
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        return default_result(agent_slug, "parse-error", assistant_messages), str(exc)
    if not isinstance(data, dict):
        return default_result(agent_slug, "invalid", assistant_messages), "result JSON is not an object"
    data.setdefault("status_summary", f"{agent_slug} woke successfully.")
    data.setdefault("current_task", "Reviewing messages and deciding whether work is needed.")
    data.setdefault("next_wake_minutes", 240)
    data.setdefault("messages_to_send", [])
    data.setdefault("wake_requests", [])
    data.setdefault("tasks_to_update", [])
    data.setdefault("questions_to_ask", [])
    return data, None


@dataclass
class CodexRunner:
    root: Path
    settings: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()
        if not self.settings:
            self.settings = load_settings(self.root)

    def configured_command(self) -> str:
        return os.environ.get("HIC_CODEX_CMD") or str(self.settings.get("runner", {}).get("codex_cmd") or "")

    def is_mock_mode(self) -> bool:
        return not bool(self.configured_command())

    def build_prompt(
        self,
        agent: AgentConfig,
        group_messages: list[dict[str, Any]],
        direct_messages: list[dict[str, Any]],
        tasks: list[dict[str, Any]],
    ) -> str:
        return build_agent_prompt(agent, self.root, group_messages, direct_messages, tasks)

    def run(
        self,
        agent: AgentConfig,
        group_messages: list[dict[str, Any]],
        direct_messages: list[dict[str, Any]],
        tasks: list[dict[str, Any]],
    ) -> RunnerResult:
        prompt = self.build_prompt(agent, group_messages, direct_messages, tasks)
        adir = agent_dir(agent.slug, self.root)
        log_path = adir / "logs" / f"wake-{iso().replace(':', '').replace('+', 'Z')}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if self.is_mock_mode():
            raw = self._mock_output(agent, group_messages, direct_messages, tasks, prompt)
            log_path.write_text(raw, encoding="utf-8")
            parsed, parse_error = parse_agent_result(raw, agent.slug)
            return RunnerResult(raw, parsed, "mock", parse_error, log_path)
        raw = self._run_real(agent, prompt, log_path)
        parsed, parse_error = parse_agent_result(raw, agent.slug)
        if parse_error:
            raw_path = adir / "logs" / "last-unparsed-output.txt"
            raw_path.write_text(raw, encoding="utf-8")
        return RunnerResult(raw, parsed, "real", parse_error, log_path)

    def _run_real(self, agent: AgentConfig, prompt: str, log_path: Path) -> str:
        return self._run_persistent_real(agent, prompt, log_path)

    def _run_command_streaming(
        self,
        cmd: list[str],
        prompt: str,
        cwd: Path,
        timeout: int,
        log_path: Path,
        agent_slug: str,
    ) -> str:
        raw_parts: list[str] = []
        log_path.write_text(
            f"[hic runner started_at={iso()}]\n[hic runner command={shlex.join(cmd)}]\n\n",
            encoding="utf-8",
        )
        try:
            proc = subprocess.Popen(
                cmd,
                text=True,
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
            )
            if proc.stdin is not None:
                proc.stdin.write(prompt)
                proc.stdin.close()
            deadline = time.monotonic() + max(1, int(timeout))
            if proc.stdout is not None:
                selector = selectors.DefaultSelector()
                selector.register(proc.stdout, selectors.EVENT_READ)
                while True:
                    if time.monotonic() > deadline:
                        proc.kill()
                        marker = "\n[hic runner timeout]\n"
                        raw_parts.append(marker)
                        append_file(log_path, marker)
                        break
                    if proc.poll() is not None:
                        remainder = proc.stdout.read() or ""
                        if remainder:
                            raw_parts.append(remainder)
                            append_file(log_path, remainder)
                        break
                    for key, _ in selector.select(timeout=0.5):
                        line = key.fileobj.readline()
                        if not line:
                            continue
                        raw_parts.append(line)
                        append_file(log_path, line)
                selector.close()
            returncode = proc.wait(timeout=5)
            raw = "".join(raw_parts)
            marker = f"\n\n[hic runner exit_code={returncode}]\n"
            raw += marker
            append_file(log_path, marker)
        except Exception as exc:
            raw = f"Runner failed: {exc}\n"
            raw += json.dumps(default_result(agent_slug, "runner-failure"))
            log_path.write_text(raw, encoding="utf-8")
        return raw

    def _persistent_codex_command(self, session_id: str) -> list[str]:
        cmd = shlex.split(self.configured_command())
        if "exec" in cmd and "--json" not in cmd:
            cmd.insert(cmd.index("exec") + 1, "--json")
        if cmd and cmd[-1] == "-":
            cmd = cmd[:-1]
        if session_id:
            cmd.extend(["resume", session_id, "-"])
        else:
            cmd.append("-")
        return cmd

    def _run_persistent_real(self, agent: AgentConfig, prompt: str, log_path: Path) -> str:
        timeout = int(self.settings.get("runner", {}).get("timeout_seconds") or 1800)
        adir = agent_dir(agent.slug, self.root)
        session_path = adir / "CODEX_SESSION_ID"
        session_id = session_path.read_text(encoding="utf-8").strip() if session_path.exists() else ""
        cmd = self._persistent_codex_command(session_id)
        try:
            raw = self._run_command_streaming(cmd, prompt, adir, timeout, log_path, agent.slug)
            assistant_chunks: list[str] = []
            for line in raw.splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event_type = str(event.get("type") or "").lower()
                if event_type == "thread.started":
                    thread_id = str(event.get("thread_id") or "").strip()
                    if thread_id:
                        session_id = thread_id
                elif event_type == "item.completed":
                    item = event.get("item")
                    if isinstance(item, dict) and str(item.get("type") or "").lower() == "agent_message":
                        text = str(item.get("text") or "").strip()
                        if text:
                            assistant_chunks.append(text)
            if session_id:
                session_path.write_text(session_id + "\n", encoding="utf-8")
            if assistant_chunks:
                assistant_text = "\n\n[hic assistant text]\n" + "\n\n".join(assistant_chunks)
                raw += assistant_text
                append_file(log_path, assistant_text)
            raw += f"\n\n[hic persistent_session_id={session_id or 'new'}]\n"
            append_file(log_path, f"\n\n[hic persistent_session_id={session_id or 'new'}]\n")
        except Exception as exc:
            raw = f"Runner failed: {exc}\n"
            raw += json.dumps(default_result(agent.slug, "runner-failure"))
            log_path.write_text(raw, encoding="utf-8")
        return raw

    def _mock_output(
        self,
        agent: AgentConfig,
        group_messages: list[dict[str, Any]],
        direct_messages: list[dict[str, Any]],
        tasks: list[dict[str, Any]],
        prompt: str,
    ) -> str:
        adir = agent_dir(agent.slug, self.root)
        if agent.slug == "yiyang_lu":
            self._mock_update_infra_docs(adir)
        if agent.slug == "main":
            self._mock_main_housekeeping(tasks)
        open_task = next((task for task in tasks if task.get("status") != "done"), None)
        current_task = open_task["title"] if open_task else "Waiting for messages or concrete work."
        status = f"{agent.display_name} reviewed messages and tasks with the fallback runner."
        messages = []
        updates = []
        if open_task:
            updates.append(
                {
                    "task_id": int(open_task["id"]),
                    "status": "in_progress",
                    "note": f"{agent.slug} reviewed this task during a fallback wake.",
                }
            )
        result = {
            "status_summary": status,
            "current_task": current_task,
            "next_wake_minutes": agent.wake_interval_minutes or 240,
            "messages_to_send": messages,
            "wake_requests": [],
            "tasks_to_update": updates,
            "questions_to_ask": [],
        }
        return (
            f"FALLBACK HIC RUN for {agent.slug}\n\n"
            f"Prompt characters: {len(prompt)}\n"
            f"Read STATUS bytes: {len(read_file(adir / 'STATUS.md'))}\n\n"
            "<AGENT_RESULT_JSON>\n"
            f"{json.dumps(result, indent=2, ensure_ascii=True)}\n"
            "</AGENT_RESULT_JSON>\n"
        )

    def _mock_update_infra_docs(self, adir: Path) -> None:
        agent_ops = Path("/home/jzc/zhichengjiang/working/ai_workspace/agent_ops")
        docs = [
            "README.md",
            "docs/safety_rules.md",
            "docs/experiment_workflows.md",
            "docs/tpu_dashboard.md",
            "docs/monitoring_and_logs.md",
        ]
        existing = [rel for rel in docs if (agent_ops / rel).exists()]
        infra_body = (
            "# INFRA_MAP\n\n"
            f"Last mock refresh: {iso()}\n\n"
            "Known operation source: /home/jzc/zhichengjiang/working/ai_workspace/agent_ops\n\n"
            "Key docs inspected or available:\n"
            + "\n".join(f"- {rel}" for rel in existing)
            + "\n\nCurrent visible services include tmux-hosted TPU dashboard and simple daemon.\n"
        )
        runbook_body = (
            "# RUNBOOK\n\n"
            f"Last mock refresh: {iso()}\n\n"
            "Before changing infra, read agent_ops/README.md, docs/safety_rules.md, "
            "docs/conventions.md, and docs/write_back_protocol.md.\n\n"
            "Useful read-only checks:\n"
            "- tmux ls\n"
            "- ss -ltnp\n"
            "- tail -n 200 agent_ops/logs/tpu_simple_daemon.log\n"
            "- tail -n 200 agent_ops/logs/tpu_dashboard.log\n"
        )
        (adir / "INFRA_MAP.md").write_text(infra_body, encoding="utf-8")
        (adir / "RUNBOOK.md").write_text(runbook_body, encoding="utf-8")

    def _mock_main_housekeeping(self, tasks: list[dict[str, Any]]) -> None:
        board = self.root / "shared" / "TASK_BOARD.md"
        open_tasks = [task for task in tasks if task.get("status") != "done"]
        lines = ["# Task Board\n", "The database table `tasks` is the source of truth.\n", "## Open\n"]
        if open_tasks:
            for task in open_tasks[:50]:
                lines.append(f"- #{task['id']} [{task['status']}] {task['title']} (owner: {task['owner']})")
        else:
            lines.append("- No open tasks.")
        lines.append("\n## Done\n")
        done = [task for task in tasks if task.get("status") == "done"]
        if done:
            for task in done[:50]:
                lines.append(f"- #{task['id']} {task['title']}")
        else:
            lines.append("- No done tasks recorded in the current task slice.")
        board.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_progress(root: Path, slug: str, summary: str, mode: str, log_path: Path | None = None) -> None:
    line = f"\n- {iso()} [{mode}] {summary}"
    if log_path:
        line += f" log={log_path}"
    line += "\n"
    append_file(agent_dir(slug, root) / "PROGRESS.md", line)
