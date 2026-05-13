from pathlib import Path

from hic.status import human_log_view


def test_human_log_view_summarizes_daemon_line():
    content = "2026-05-12 23:49:00,007 INFO agent main wake complete mode=real next=2026-05-13T01:14:19+00:00"
    view = human_log_view(Path("daemon.log"), "daemon", content)
    assert view["event_count"] == 1
    assert view["cards"][0]["title"] == "main completed a wake"
    assert view["cards"][0]["tone"] == "ok"


def test_human_log_view_summarizes_agent_json():
    content = """
<AGENT_RESULT_JSON>
{"status_summary":"ok","current_task":"checking messages","next_wake_minutes":120,"messages_to_send":[],"wake_requests":[],"tasks_to_update":[]}
</AGENT_RESULT_JSON>
"""
    view = human_log_view(Path("wake.log"), "agent:main", content)
    titles = [card["title"] for card in view["cards"]]
    assert "Agent reported a result" in titles
    assert "Current work" in titles
