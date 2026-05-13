from pathlib import Path
import os
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def run_cli(sample_root, *args):
    env = os.environ.copy()
    env["HIC_ROOT"] = str(sample_root)
    env["PYTHONPATH"] = f"{ROOT}:{env.get('PYTHONPATH', '')}"
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "hicctl.py"), "--root", str(sample_root), *args],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def test_cli_status_send_wake_tasks(sample_root):
    assert run_cli(sample_root, "status").returncode == 0
    sent = run_cli(sample_root, "send", "--to", "group", "--body", "cli smoke")
    assert sent.returncode == 0
    assert "sent message" in sent.stdout
    assert run_cli(sample_root, "wake", "all").returncode == 0
    added = run_cli(sample_root, "task-add", "--title", "cli task", "--owner", "main")
    assert added.returncode == 0
    assert "created task" in added.stdout
    assert run_cli(sample_root, "tasks").returncode == 0
    compact = run_cli(sample_root, "compact-notes", "--dry-run")
    assert compact.returncode == 0
    assert "dry-run only; no files written." in compact.stdout


def test_start_stop_scripts_dry_run():
    start = subprocess.run(
        ["bash", "scripts/start_all.sh", "--dry-run"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    stop = subprocess.run(
        ["bash", "scripts/stop_all.sh", "--dry-run"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert start.returncode == 0
    assert stop.returncode == 0
    assert "would start" in start.stdout
    assert "would stop" in stop.stdout


def test_stop_daemon_refuses_active_agent_lock(tmp_path):
    root = tmp_path / "hic-root"
    lock_dir = root / "var" / "locks"
    lock_dir.mkdir(parents=True)
    (lock_dir / "qiao_sun.lock").write_text(str(os.getpid()), encoding="ascii")
    env = os.environ.copy()
    env["HIC_ROOT"] = str(root)
    stop = subprocess.run(
        ["bash", str(ROOT / "scripts" / "stop_daemon.sh")],
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert stop.returncode == 2
    assert "active agent wake" in stop.stdout
    assert "qiao_sun" in stop.stdout
