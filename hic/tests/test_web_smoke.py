from io import BytesIO
import json

from hic import db
from hic.message_bus import pending_wake_requests
from hic.webapp import create_app


def test_web_routes_and_forms(sample_root):
    app = create_app(sample_root)
    app.config.update(TESTING=True)
    client = app.test_client()
    assert client.get("/hic/health").status_code == 200
    dashboard = client.get("/hic/")
    assert dashboard.status_code == 200
    assert b'href="https://kaiming.me/"' in dashboard.data
    assert b"TPU Dashboard" in dashboard.data
    assert b"Codex tokens:" in dashboard.data
    assert b"data-countdown-time" in dashboard.data
    assert b">00:00</time>" in dashboard.data
    assert b"/hic/progress/main" in dashboard.data
    group_chat = client.get("/hic/chat?channel=group")
    assert group_chat.status_code == 200
    assert b">important</option>" in group_chat.data
    assert b'<option value="2" selected>important</option>' in group_chat.data
    assert b"3 urgent" not in group_chat.data
    assert b"data-mention-picker" in group_chat.data
    assert b'data-mention="all"' in group_chat.data
    assert b'data-mention="qiao_sun"' in group_chat.data
    resp = client.post("/hic/chat", data={"channel": "group", "body": "smoke", "priority": "1"})
    assert resp.status_code == 302
    resp = client.post(
        "/hic/chat",
        data={
            "channel": "direct:main",
            "body": "",
            "priority": "2",
            "files": (BytesIO(b"hello"), "hello.txt"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    direct_chat = client.get("/hic/chat?channel=direct:main")
    assert b"hello.txt" in direct_chat.data
    assert b"wake queued" in direct_chat.data
    assert b"queued for Main" in direct_chat.data
    assert b"data-countdown-time" in direct_chat.data
    assert b'name="next" value="/hic/chat?channel=direct:main"' in direct_chat.data
    assert b"Wake state" in direct_chat.data
    assert b"Last PI message" in direct_chat.data
    assert b"wake queued; waiting read" in direct_chat.data
    assert b"/hic/progress/main" in direct_chat.data
    tasks_page = client.get("/hic/tasks")
    assert tasks_page.status_code == 200
    assert b"important" in tasks_page.data
    assert b'<option value="2" selected>important</option>' in tasks_page.data
    conn = db.connect(root=sample_root)
    try:
        wakes_before_task = len(pending_wake_requests(conn))
    finally:
        conn.close()
    resp = client.post(
        "/hic/tasks",
        data={"action": "create", "title": "web task", "owner": "main", "priority": "1", "description": ""},
    )
    assert resp.status_code == 302
    conn = db.connect(root=sample_root)
    try:
        assert len(pending_wake_requests(conn)) == wakes_before_task
    finally:
        conn.close()
    resp = client.post(
        "/hic/tasks",
        data={"action": "create", "title": "important web task", "owner": "main", "priority": "2", "description": ""},
    )
    assert resp.status_code == 302
    conn = db.connect(root=sample_root)
    try:
        wakes_after_task = pending_wake_requests(conn)
        assert len(wakes_after_task) == wakes_before_task
        assert any(wake["reason"] == "important task 2" for wake in wakes_after_task)
    finally:
        conn.close()
    assert client.get("/hic/ops").status_code == 200
    resp = client.post(
        "/hic/ops",
        data={"action": "wake", "agent": "main", "next": "/hic/chat?channel=direct:main"},
    )
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/hic/chat?channel=direct:main"
    resp = client.post("/hic/ops", data={"action": "wake", "agent": "main", "next": "https://example.com/"})
    assert resp.status_code == 200
    assert client.get("/hic/guide").status_code == 200
    assert client.get("/hic/docs").status_code == 302
    assert client.get("/hic/logs").status_code == 200
    progress_page = client.get("/hic/progress/main")
    assert progress_page.status_code == 200
    assert b"data-progress-root" in progress_page.data
    assert b"Live Codex" in progress_page.data
    assert b"Raw JSON log" in progress_page.data
    assert b"data-progress-raw-stream" in progress_page.data
    assert b"readable stream" in progress_page.data
    progress_api = client.get("/hic/api/progress/main")
    assert progress_api.status_code == 200
    progress_data = json.loads(progress_api.data)
    assert progress_data["ok"] is True
    assert progress_data["agent"]["slug"] == "main"
    assert "raw" in progress_data
    assert client.get("/hic/settings").status_code == 200
    assert client.get("/hic/self-improve").status_code == 200
    conn = db.connect(root=sample_root)
    try:
        tasks_before_self_improve = conn.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"]
    finally:
        conn.close()
    resp = client.post("/hic/self-improve", data={"body": "GUI improvement smoke"})
    assert resp.status_code == 302
    conn = db.connect(root=sample_root)
    try:
        assert conn.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"] == tasks_before_self_improve
        wakes = pending_wake_requests(conn)
        assert any(wake["target_agent"] in {"self_evolver", "main"} for wake in wakes)
    finally:
        conn.close()
