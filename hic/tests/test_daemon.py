import json
import threading
import time

from hic import daemon as daemon_module
from hic import db
from hic.codex_runner import RunnerResult
from hic.config import ensure_project_structure, load_agents, load_settings
from hic.daemon import AgentLock, lock_is_active, run_agent_once, start_agent_wake
from hic.message_bus import list_messages, pending_wake_requests, send_message


def test_messages_are_marked_read_when_wake_starts(sample_root, monkeypatch):
    ensure_project_structure(sample_root)
    conn = db.connect(root=sample_root)
    try:
        db.init_db(conn)
        agents = load_agents(sample_root)
        db.upsert_agents(conn, agents)
        msg_id = send_message(conn, "pi", "qiao_sun", "hello", priority=2)
    finally:
        conn.close()

    class FakeRunner:
        def __init__(self, root, settings):
            self.root = root

        def run(self, agent, group_messages, direct_messages, tasks):
            check = db.connect(root=self.root)
            try:
                row = check.execute("SELECT read_by FROM messages WHERE id=?", (msg_id,)).fetchone()
                assert agent.slug in json.loads(row["read_by"])
            finally:
                check.close()
            return RunnerResult(
                "",
                {
                    "status_summary": "ok",
                    "current_task": "done",
                    "next_wake_minutes": 240,
                    "messages_to_send": [],
                    "wake_requests": [],
                    "tasks_to_update": [],
                },
                "mock",
                None,
                None,
            )

    monkeypatch.setattr("hic.daemon.CodexRunner", FakeRunner)
    qiao = next(agent for agent in load_agents(sample_root) if agent.slug == "qiao_sun")
    assert run_agent_once(sample_root, qiao, load_settings(sample_root), reason="test")


def test_new_wake_during_run_stays_pending(sample_root, monkeypatch):
    ensure_project_structure(sample_root)
    conn = db.connect(root=sample_root)
    try:
        db.init_db(conn)
        agents = load_agents(sample_root)
        db.upsert_agents(conn, agents)
        send_message(conn, "pi", "qiao_sun", "first", priority=2)
    finally:
        conn.close()

    class FakeRunner:
        def __init__(self, root, settings):
            self.root = root

        def run(self, agent, group_messages, direct_messages, tasks):
            during = db.connect(root=self.root)
            try:
                send_message(during, "pi", agent.slug, "arrived while running", priority=2)
            finally:
                during.close()
            return RunnerResult(
                "",
                {
                    "status_summary": "ok",
                    "current_task": "done",
                    "next_wake_minutes": 240,
                    "messages_to_send": [],
                    "wake_requests": [],
                    "tasks_to_update": [],
                },
                "mock",
                None,
                None,
            )

    monkeypatch.setattr("hic.daemon.CodexRunner", FakeRunner)
    qiao = next(agent for agent in load_agents(sample_root) if agent.slug == "qiao_sun")
    assert run_agent_once(sample_root, qiao, load_settings(sample_root), reason="test")

    check = db.connect(root=sample_root)
    try:
        pending = pending_wake_requests(check)
        assert len(pending) == 1
        assert pending[0]["reason"] == "direct message 2"
    finally:
        check.close()


def test_claimed_wake_is_cleared_when_run_starts(sample_root, monkeypatch):
    ensure_project_structure(sample_root)
    conn = db.connect(root=sample_root)
    try:
        db.init_db(conn)
        agents = load_agents(sample_root)
        db.upsert_agents(conn, agents)
        send_message(conn, "pi", "qiao_sun", "first", priority=2)
    finally:
        conn.close()

    class FakeRunner:
        def __init__(self, root, settings):
            self.root = root

        def run(self, agent, group_messages, direct_messages, tasks):
            check = db.connect(root=self.root)
            try:
                assert pending_wake_requests(check) == []
            finally:
                check.close()
            return RunnerResult(
                "",
                {
                    "status_summary": "ok",
                    "current_task": "done",
                    "next_wake_minutes": 240,
                    "messages_to_send": [],
                    "wake_requests": [],
                    "tasks_to_update": [],
                },
                "mock",
                None,
                None,
            )

    monkeypatch.setattr("hic.daemon.CodexRunner", FakeRunner)
    qiao = next(agent for agent in load_agents(sample_root) if agent.slug == "qiao_sun")
    assert run_agent_once(sample_root, qiao, load_settings(sample_root), reason="test")


def test_group_replies_are_not_suppressed_without_active_tasks(sample_root, monkeypatch):
    ensure_project_structure(sample_root)
    conn = db.connect(root=sample_root)
    try:
        db.init_db(conn)
        agents = load_agents(sample_root)
        db.upsert_agents(conn, agents)
        send_message(conn, "pi", "group", "@qiao_sun 1+1?", priority=2)
    finally:
        conn.close()

    class FakeRunner:
        def __init__(self, root, settings):
            self.root = root

        def run(self, agent, group_messages, direct_messages, tasks):
            return RunnerResult(
                "",
                {
                    "status_summary": "answered group question",
                    "current_task": "done",
                    "next_wake_minutes": 240,
                    "messages_to_send": [
                        {"recipient": "group", "body": "@pi 1+1=2", "priority": 1},
                    ],
                    "wake_requests": [],
                    "tasks_to_update": [],
                },
                "mock",
                None,
                None,
            )

    monkeypatch.setattr("hic.daemon.CodexRunner", FakeRunner)
    qiao = next(agent for agent in load_agents(sample_root) if agent.slug == "qiao_sun")
    assert run_agent_once(sample_root, qiao, load_settings(sample_root), reason="test")

    check = db.connect(root=sample_root)
    try:
        messages = list_messages(check, channel="group")
        assert messages[-1]["sender"] == "qiao_sun"
        assert messages[-1]["body"] == "@pi 1+1=2"
    finally:
        check.close()


def test_group_origin_pi_replies_are_rerouted_to_group(sample_root, monkeypatch):
    ensure_project_structure(sample_root)
    conn = db.connect(root=sample_root)
    try:
        db.init_db(conn)
        agents = load_agents(sample_root)
        db.upsert_agents(conn, agents)
        send_message(conn, "pi", "group", "@qiao_sun answer in group", priority=2)
    finally:
        conn.close()

    class FakeRunner:
        def __init__(self, root, settings):
            self.root = root

        def run(self, agent, group_messages, direct_messages, tasks):
            return RunnerResult(
                "",
                {
                    "status_summary": "answered group question",
                    "current_task": "done",
                    "next_wake_minutes": 240,
                    "messages_to_send": [
                        {"recipient": "pi", "body": "This should stay in group.", "priority": 1},
                    ],
                    "wake_requests": [],
                    "tasks_to_update": [],
                },
                "mock",
                None,
                None,
            )

    monkeypatch.setattr("hic.daemon.CodexRunner", FakeRunner)
    qiao = next(agent for agent in load_agents(sample_root) if agent.slug == "qiao_sun")
    assert run_agent_once(sample_root, qiao, load_settings(sample_root), reason="test")

    check = db.connect(root=sample_root)
    try:
        group_messages = list_messages(check, channel="group")
        direct_messages = list_messages(check, channel="direct:qiao_sun")
        assert group_messages[-1]["sender"] == "qiao_sun"
        assert group_messages[-1]["recipient"] == "group"
        assert group_messages[-1]["body"] == "This should stay in group."
        assert all(message["sender"] != "qiao_sun" for message in direct_messages)
    finally:
        check.close()


def test_direct_origin_pi_replies_stay_direct(sample_root, monkeypatch):
    ensure_project_structure(sample_root)
    conn = db.connect(root=sample_root)
    try:
        db.init_db(conn)
        agents = load_agents(sample_root)
        db.upsert_agents(conn, agents)
        send_message(conn, "pi", "qiao_sun", "private answer please", priority=2)
    finally:
        conn.close()

    class FakeRunner:
        def __init__(self, root, settings):
            self.root = root

        def run(self, agent, group_messages, direct_messages, tasks):
            return RunnerResult(
                "",
                {
                    "status_summary": "answered direct question",
                    "current_task": "done",
                    "next_wake_minutes": 240,
                    "messages_to_send": [
                        {"recipient": "pi", "body": "Private reply.", "priority": 1},
                    ],
                    "wake_requests": [],
                    "tasks_to_update": [],
                },
                "mock",
                None,
                None,
            )

    monkeypatch.setattr("hic.daemon.CodexRunner", FakeRunner)
    qiao = next(agent for agent in load_agents(sample_root) if agent.slug == "qiao_sun")
    assert run_agent_once(sample_root, qiao, load_settings(sample_root), reason="test")

    check = db.connect(root=sample_root)
    try:
        direct_messages = list_messages(check, channel="direct:qiao_sun")
        assert direct_messages[-1]["sender"] == "qiao_sun"
        assert direct_messages[-1]["recipient"] == "pi"
        assert direct_messages[-1]["body"] == "Private reply."
    finally:
        check.close()


def test_agent_lock_failed_acquire_preserves_existing_lock(sample_root):
    ensure_project_structure(sample_root)
    lock_path = sample_root / "var" / "locks" / "qiao_sun.lock"

    with AgentLock(sample_root, "qiao_sun") as acquired:
        assert acquired
        original = lock_path.read_text(encoding="utf-8")
        with AgentLock(sample_root, "qiao_sun") as acquired_again:
            assert not acquired_again
        assert lock_path.exists()
        assert lock_path.read_text(encoding="utf-8") == original

    assert not lock_path.exists()


def test_dead_pid_lock_is_cleared(sample_root):
    ensure_project_structure(sample_root)
    lock_path = sample_root / "var" / "locks" / "qiao_sun.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("999999999", encoding="ascii")

    assert not lock_is_active(sample_root, "qiao_sun")
    assert not lock_path.exists()


def test_start_agent_wake_returns_without_waiting(sample_root, monkeypatch):
    ensure_project_structure(sample_root)
    conn = db.connect(root=sample_root)
    try:
        db.init_db(conn)
        agents = load_agents(sample_root)
        db.upsert_agents(conn, agents)
    finally:
        conn.close()

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def fake_run_agent_once(root, agent, settings, reason="daemon"):
        try:
            started.set()
            release.wait(timeout=2)
        finally:
            finished.set()
        return True

    monkeypatch.setattr("hic.daemon.run_agent_once", fake_run_agent_once)
    qiao = next(agent for agent in load_agents(sample_root) if agent.slug == "qiao_sun")
    before = time.monotonic()
    assert start_agent_wake(sample_root, qiao, load_settings(sample_root), reason="test")
    elapsed = time.monotonic() - before
    assert elapsed < 0.5
    assert not start_agent_wake(sample_root, qiao, load_settings(sample_root), reason="test")
    assert started.wait(timeout=1)
    release.set()
    assert finished.wait(timeout=1)
    deadline = time.monotonic() + 1
    while qiao.slug in daemon_module.IN_FLIGHT_WAKES and time.monotonic() < deadline:
        time.sleep(0.01)
    assert qiao.slug not in daemon_module.IN_FLIGHT_WAKES
