from pathlib import Path


ROOT = Path(__file__).parent.parent


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_root_agent_docs_cover_project_operations_and_sync_contract():
    readme = _read("README.md")
    agents = _read("AGENTS.md")
    claude = _read("CLAUDE.md")
    combined = "\n".join([readme, agents, claude])

    required = [
        "Markdown-first blueprint system",
        "Repository Structure",
        "Development Commands",
        "GitHub Sync Contract",
        "EconCSLib Relationship",
        "uv run --extra dev python -m pytest -q",
        "uv run --extra browser python -m tools.knowledge.econcslib_gate",
        "git pull --ff-only origin main",
        "git push origin main",
        "AGENTS.md",
    ]

    missing = [phrase for phrase in required if phrase not in combined]
    assert missing == []


def test_agent_docs_tell_parallel_agents_how_to_avoid_conflicts():
    agents = _read("AGENTS.md")

    assert "Use one branch or worktree per agent task" in agents
    assert "Do not rewrite another agent's files" in agents
    assert "Do not hand-edit generated graph or site artifacts" in agents
    assert "Treat GitHub issues as the coordination queue" in agents
