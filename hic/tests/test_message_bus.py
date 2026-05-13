from hic import db
from hic.config import ensure_project_structure, load_agents
from hic.message_bus import list_messages, pending_wake_requests, send_message


def test_normal_messages_do_not_wake(sample_root):
    ensure_project_structure(sample_root)
    conn = db.connect(root=sample_root)
    try:
        db.init_db(conn)
        db.upsert_agents(conn, load_agents(sample_root))
        send_message(conn, "pi", "group", "hello group", priority=1)
        send_message(conn, "pi", "qiao_sun", "hello qiao", priority=1)
        group = list_messages(conn, channel="group")
        direct = list_messages(conn, channel="direct:qiao_sun")
        wakes = pending_wake_requests(conn)
        assert group[-1]["body"] == "hello group"
        assert direct[-1]["recipient"] == "qiao_sun"
        assert wakes == []
    finally:
        conn.close()


def test_important_direct_wakes_target(sample_root):
    ensure_project_structure(sample_root)
    conn = db.connect(root=sample_root)
    try:
        db.init_db(conn)
        db.upsert_agents(conn, load_agents(sample_root))
        send_message(conn, "pi", "qiao_sun", "important direct", priority=2)
        direct_targets = [wake["target_agent"] for wake in pending_wake_requests(conn)]
        assert direct_targets == ["qiao_sun"]
    finally:
        conn.close()


def test_wake_requests_are_coalesced_per_agent(sample_root):
    ensure_project_structure(sample_root)
    conn = db.connect(root=sample_root)
    try:
        db.init_db(conn)
        db.upsert_agents(conn, load_agents(sample_root))
        send_message(conn, "pi", "qiao_sun", "important direct 1", priority=2)
        send_message(conn, "pi", "qiao_sun", "important direct 2", priority=2)
        wakes = pending_wake_requests(conn)
        assert len(wakes) == 1
        assert wakes[0]["target_agent"] == "qiao_sun"
        assert wakes[0]["reason"] == "direct message 2"
    finally:
        conn.close()


def test_important_group_without_mentions_does_not_wake(sample_root):
    ensure_project_structure(sample_root)
    conn = db.connect(root=sample_root)
    try:
        db.init_db(conn)
        db.upsert_agents(conn, load_agents(sample_root))
        send_message(conn, "pi", "group", "important group", priority=2)
        assert pending_wake_requests(conn) == []
    finally:
        conn.close()


def test_agent_reply_to_pi_stays_in_agent_direct_chat(sample_root):
    ensure_project_structure(sample_root)
    conn = db.connect(root=sample_root)
    try:
        db.init_db(conn)
        db.upsert_agents(conn, load_agents(sample_root))
        msg_id = send_message(conn, "main", "pi", "done", priority=1)
        message = list_messages(conn, channel="direct:main")[0]
        assert message["id"] == msg_id
        assert message["recipient"] == "pi"
        assert pending_wake_requests(conn) == []
    finally:
        conn.close()


def test_group_mention_wakes_target_agent_by_slug(sample_root):
    ensure_project_structure(sample_root)
    conn = db.connect(root=sample_root)
    try:
        db.init_db(conn)
        db.upsert_agents(conn, load_agents(sample_root))
        send_message(conn, "pi", "group", "@qiao_sun check this", priority=2)
        wake_targets = {wake["target_agent"] for wake in pending_wake_requests(conn)}
        assert wake_targets == {"qiao_sun"}
    finally:
        conn.close()


def test_group_mention_wakes_target_agent_by_display_name(sample_root):
    ensure_project_structure(sample_root)
    conn = db.connect(root=sample_root)
    try:
        db.init_db(conn)
        db.upsert_agents(conn, load_agents(sample_root))
        send_message(conn, "pi", "group", "ping @Qiao sun please", priority=2)
        wake_targets = {wake["target_agent"] for wake in pending_wake_requests(conn)}
        assert wake_targets == {"qiao_sun"}
    finally:
        conn.close()


def test_normal_group_mention_does_not_wake(sample_root):
    ensure_project_structure(sample_root)
    conn = db.connect(root=sample_root)
    try:
        db.init_db(conn)
        db.upsert_agents(conn, load_agents(sample_root))
        send_message(conn, "pi", "group", "@main normal check", priority=1)
        assert pending_wake_requests(conn) == []
    finally:
        conn.close()


def test_group_all_mention_wakes_all_enabled_agents(sample_root):
    ensure_project_structure(sample_root)
    conn = db.connect(root=sample_root)
    try:
        db.init_db(conn)
        agents = load_agents(sample_root)
        db.upsert_agents(conn, agents)
        send_message(conn, "pi", "group", "@all please look", priority=2)
        wake_targets = {wake["target_agent"] for wake in pending_wake_requests(conn)}
        assert wake_targets == {agent.slug for agent in agents}
    finally:
        conn.close()


def test_direct_message_mentions_do_not_fanout(sample_root):
    ensure_project_structure(sample_root)
    conn = db.connect(root=sample_root)
    try:
        db.init_db(conn)
        db.upsert_agents(conn, load_agents(sample_root))
        send_message(conn, "pi", "qiao_sun", "cc @hanhong_zhao", priority=2)
        wake_targets = [wake["target_agent"] for wake in pending_wake_requests(conn)]
        assert wake_targets == ["qiao_sun"]
    finally:
        conn.close()
