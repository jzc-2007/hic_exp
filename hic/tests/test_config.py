from hic.config import add_agent, ensure_project_structure, load_agents


def test_agent_roster_load_and_dirs(sample_root):
    ensure_project_structure(sample_root)
    agents = load_agents(sample_root)
    assert [agent.slug for agent in agents] == ["main", "yiyang_lu", "qiao_sun"]
    for agent in agents:
        assert (sample_root / "agents" / agent.slug / "STATUS.md").exists()
        assert (sample_root / "agents" / agent.slug / "PROGRESS.md").exists()
    assert (sample_root / "agents" / "yiyang_lu" / "RUNBOOK.md").exists()


def test_add_agent_updates_config(sample_root):
    ensure_project_structure(sample_root)
    agent = add_agent("new codex", "New Codex", "worker", ["test"], sample_root)
    assert agent.slug == "new_codex"
    assert "new_codex" in [row.slug for row in load_agents(sample_root)]
    assert (sample_root / "agents" / "new_codex" / "MEMORY.md").exists()
