import re
from pathlib import Path


ROOT = Path(__file__).parent.parent
DOMAIN_PATTERN = re.compile(
    r"game ?theory|gametheory|strategic_games|StrategicGame|GameTheoryLib|"
    r"Nash|dominance|payoff|player",
    re.IGNORECASE,
)
AUDITED_PATHS = [
    ROOT / "README.md",
    ROOT / "docs" / "node-format.md",
    ROOT / "docs" / "architecture.md",
    ROOT / "docs" / "agent-contracts.md",
    ROOT / "docs" / "skills.md",
    ROOT / "docs" / "publisher-and-dag.md",
    ROOT / "docs" / "superpowers" / "plans" / "2026-05-14-leanblueprint-style-publisher.md",
    ROOT / "tools",
    ROOT / "skills",
]
ALLOWLISTED_PARTS = {
    ("docs", "knowledge"),
    ("tests", "fixtures"),
}


def _is_allowlisted(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    parts = relative.parts
    return any(parts[:len(prefix)] == prefix for prefix in ALLOWLISTED_PARTS)


def _audited_files() -> list[Path]:
    files: list[Path] = []
    for path in AUDITED_PATHS:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(path.rglob("*"))
    return sorted(
        path
        for path in files
        if path.is_file()
        and not _is_allowlisted(path)
        and "__pycache__" not in path.parts
    )


def test_generic_docs_skills_and_tools_do_not_use_domain_fixture_terms():
    matches: list[str] = []
    for path in _audited_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if DOMAIN_PATTERN.search(line):
                matches.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")

    assert matches == []
