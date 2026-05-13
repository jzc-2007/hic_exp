from hic import db
from hic.config import ensure_project_structure, load_agents


def test_db_initialization(sample_root):
    ensure_project_structure(sample_root)
    conn = db.connect(root=sample_root)
    try:
        db.init_db(conn)
        db.upsert_agents(conn, load_agents(sample_root))
        valid, missing = db.schema_valid(conn)
        assert valid, missing
        agents = db.list_agents(conn)
        assert len(agents) == 3
        task_id = db.create_task(conn, "test task", owner="main")
        db.update_task(conn, task_id, status="done", note="finished")
        assert db.list_tasks(conn, status="done")[0]["id"] == task_id
        msg_id = conn.execute(
            "INSERT INTO messages(created_at, sender, recipient, channel, body, read_by, priority, wakes_recipient) VALUES ('now', 'pi', 'main', 'direct:main', 'body', '[]', 1, 0)"
        ).lastrowid
        attachment_id = db.add_attachment(conn, msg_id, "note.txt", "var/uploads/note.txt", "text/plain", 4)
        assert db.get_attachment(conn, attachment_id)["filename"] == "note.txt"
        assert db.list_attachments(conn, [msg_id])[msg_id][0]["size"] == 4
        normalized_task_id = db.create_task(conn, "legacy high priority", owner="main", priority=3)
        assert db.list_tasks(conn, limit=10)[0]["id"] == normalized_task_id
        assert db.list_tasks(conn, limit=10)[0]["priority"] == 2
    finally:
        conn.close()
