from hic import db
from hic.codex_runner import CodexRunner, extract_agent_messages, parse_agent_result
from hic.config import ensure_project_structure, load_agents, load_settings
from hic.message_bus import recent_for_agent


def test_mock_codex_runner_updates_parseable_result(sample_root):
    ensure_project_structure(sample_root)
    conn = db.connect(root=sample_root)
    try:
        db.init_db(conn)
        agents = load_agents(sample_root)
        db.upsert_agents(conn, agents)
        db.create_task(conn, "runner task", owner="main")
        main = agents[0]
        recent = recent_for_agent(conn, "main")
        runner = CodexRunner(sample_root, load_settings(sample_root))
        result = runner.run(main, recent["group"], recent["direct"], db.list_tasks(conn))
        assert result.mode == "mock"
        assert result.parsed["next_wake_minutes"] <= 240
        assert result.log_path and result.log_path.exists()
    finally:
        conn.close()


def test_parse_fallback_is_safe():
    parsed, err = parse_agent_result("not json", "main")
    assert err
    assert parsed["next_wake_minutes"] == 240
    assert parsed["messages_to_send"] == []
    assert parsed["questions_to_ask"] == []


def test_extract_agent_messages_from_codex_json_stream():
    raw = (
        '{"type":"turn.started"}\n'
        '{"type":"item.completed","item":{"id":"item_0","type":"agent_message",'
        '"text":"I read the message and started work."}}\n'
    )
    assert extract_agent_messages(raw) == ["I read the message and started work."]


def test_parse_fallback_sends_unstructured_agent_message():
    raw = (
        '{"type":"thread.started","thread_id":"thread-1"}\n'
        '{"type":"item.completed","item":{"id":"item_0","type":"agent_message",'
        '"text":"I saw this and am checking it now."}}\n'
        '{"type":"turn.completed"}\n'
    )
    parsed, err = parse_agent_result(raw, "self_evolver")
    assert err
    assert parsed["messages_to_send"] == [
        {
            "recipient": "pi",
            "body": "I saw this and am checking it now.",
            "priority": 1,
            "wakes_recipient": False,
        }
    ]


def test_parse_uses_last_tagged_result():
    raw = """
<AGENT_RESULT_JSON>
{"status_summary":"example","current_task":"template","next_wake_minutes":1,"messages_to_send":[{"recipient":"group","body":"...","priority":1}],"wake_requests":[{"target_agent":"yiyang_lu","reason":"..."}],"tasks_to_update":[]}
</AGENT_RESULT_JSON>

codex final:
<AGENT_RESULT_JSON>
{"status_summary":"real","current_task":"done","next_wake_minutes":240,"messages_to_send":[],"wake_requests":[],"tasks_to_update":[]}
</AGENT_RESULT_JSON>
"""
    parsed, err = parse_agent_result(raw, "main")
    assert err is None
    assert parsed["status_summary"] == "real"
    assert parsed["wake_requests"] == []


def test_persistent_command_uses_json_and_resume(sample_root):
    ensure_project_structure(sample_root)
    runner = CodexRunner(
        sample_root,
        {
            "runner": {
                "codex_cmd": "codex --ask-for-approval never exec -C /tmp --skip-git-repo-check --sandbox workspace-write -",
                "timeout_seconds": 5,
            }
        },
    )
    cmd = runner._persistent_codex_command("thread-123")
    assert "--json" in cmd
    assert cmd[-3:] == ["resume", "thread-123", "-"]


def test_all_real_agents_use_persistent_sessions(sample_root, monkeypatch):
    ensure_project_structure(sample_root)
    runner = CodexRunner(
        sample_root,
        {
            "runner": {
                "codex_cmd": "codex exec -",
                "timeout_seconds": 5,
            }
        },
    )
    calls = []

    def fake_persistent(agent, prompt, log_path):
        calls.append((agent.slug, prompt, log_path))
        return (
            '<AGENT_RESULT_JSON>{"status_summary":"ok","current_task":"done",'
            '"next_wake_minutes":240,"messages_to_send":[],"wake_requests":[],'
            '"tasks_to_update":[]}</AGENT_RESULT_JSON>'
        )

    monkeypatch.setattr(runner, "_run_persistent_real", fake_persistent)
    main = load_agents(sample_root)[0]
    result = runner.run(main, [], [], [])
    assert result.mode == "real"
    assert result.parse_error is None
    assert calls and calls[0][0] == "main"


def test_agent_prompt_includes_tpu_safety_red_lines(sample_root):
    ensure_project_structure(sample_root)
    agents = load_agents(sample_root)
    runner = CodexRunner(sample_root, load_settings(sample_root))
    prompt = runner.build_prompt(agents[0], [], [], [])
    assert "shared/TPU_SAFETY_RED_LINES.md" in prompt
    assert "AGENTS.md" in prompt
    assert "repo skills" in prompt
    assert "questions_to_ask" in prompt


def test_agent_prompt_explains_channel_reply_routing_and_group_visibility(sample_root):
    ensure_project_structure(sample_root)
    agents = load_agents(sample_root)
    runner = CodexRunner(sample_root, load_settings(sample_root))
    prompt = runner.build_prompt(
        agents[0],
        [{"id": 1, "created_at": "now", "sender": "pi", "recipient": "group", "body": "@main hello"}],
        [{"id": 2, "created_at": "now", "sender": "pi", "recipient": "main", "body": "private"}],
        [],
    )
    assert "GROUP [1]" in prompt
    assert "DIRECT [2]" in prompt
    assert 'messages_to_send[].recipient to "group"' in prompt
    assert 'messages_to_send[].recipient to "pi"' in prompt
    assert "mentions only affect wake targeting, not visibility" in prompt
    assert "persistent Codex session resumed across wakes" in prompt
    assert "Never stop or restart HIC from inside your own wake" in prompt
    assert "hic-workflow" in prompt


def test_yiyang_prompt_does_not_repeat_first_wake_infra_when_runbook_exists(sample_root):
    ensure_project_structure(sample_root)
    agents = load_agents(sample_root)
    yiyang = next(agent for agent in agents if agent.slug == "yiyang_lu")
    adir = sample_root / "agents" / "yiyang_lu"
    adir.mkdir(parents=True, exist_ok=True)
    (adir / "INFRA_MAP.md").write_text("# infra\n", encoding="utf-8")
    (adir / "RUNBOOK.md").write_text("# runbook\n", encoding="utf-8")
    runner = CodexRunner(sample_root, load_settings(sample_root))
    prompt = runner.build_prompt(yiyang, [], [], [])
    assert "SPECIAL FIRST-WAKE INFRA TASK" not in prompt
    assert "Do not re-audit agent_ops" in prompt
