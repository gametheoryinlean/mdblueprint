import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools.knowledge.admit import admit_node

KNOWLEDGE_ROOT = Path("docs/knowledge")


def _setup_test_knowledge(tmp_path):
    """Copy the real knowledge base into a temp dir for testing."""
    kb = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_ROOT, kb)
    return kb


class TestAdmitValid:
    def test_admit_staged_node(self, tmp_path):
        kb = _setup_test_knowledge(tmp_path)
        staged = kb / "staged" / "mixed_strategy.md"
        assert staged.exists()

        # Create a fake review
        reviews_dir = kb / "reviews"
        reviews_dir.mkdir(exist_ok=True)
        review = reviews_dir / "mixed_strategy_review.md"
        review.write_text(
            "---\nagent: statement-verifier\ntarget:\n  node_id: strategic_games.mixed_strategy\n"
            "decision: accepted\n---\nAccepted.\n"
        )

        # Need generality for definition kind
        text = staged.read_text()
        text = text.replace(
            "tags:",
            "generality:\n  reviewed: true\n  prompt: test\n  verdict: ok\ntags:",
        )
        staged.write_text(text)

        result = admit_node(staged, kb)
        assert result.success
        assert result.target_path is not None
        assert result.target_path.exists()
        assert not staged.exists()

        admitted_text = result.target_path.read_text()
        assert "status: admitted" in admitted_text

    def test_admit_without_reviews_flag(self, tmp_path):
        kb = _setup_test_knowledge(tmp_path)
        staged = kb / "staged" / "mixed_strategy.md"

        text = staged.read_text()
        text = text.replace(
            "tags:",
            "generality:\n  reviewed: true\n  prompt: test\n  verdict: ok\ntags:",
        )
        staged.write_text(text)

        result = admit_node(staged, kb, require_reviews=False)
        assert result.success


class TestAdmitBlocked:
    def test_missing_generality_gate(self, tmp_path):
        kb = _setup_test_knowledge(tmp_path)
        staged = kb / "staged" / "mixed_strategy.md"
        result = admit_node(staged, kb, require_reviews=False)
        assert not result.success
        msgs = [d.message for d in result.diagnostics]
        assert any("generality" in m for m in msgs)

    def test_missing_reviews(self, tmp_path):
        kb = _setup_test_knowledge(tmp_path)
        staged = kb / "staged" / "mixed_strategy.md"

        text = staged.read_text()
        text = text.replace(
            "tags:",
            "generality:\n  reviewed: true\n  prompt: test\n  verdict: ok\ntags:",
        )
        staged.write_text(text)

        result = admit_node(staged, kb, require_reviews=True)
        assert not result.success
        msgs = [d.message for d in result.diagnostics]
        assert any("review" in m for m in msgs)

    def test_cycle_detection(self, tmp_path):
        kb = _setup_test_knowledge(tmp_path)
        staged = kb / "staged"

        # Create a staged node that would create a cycle
        cycle_node = staged / "cycle_test.md"
        cycle_node.write_text(
            "---\nid: strategic_games.strategic_game\ntitle: Cycle\nkind: definition\n"
            "status: staged\nuses:\n  - strategic_games.nash_equilibrium\n"
            "generality:\n  reviewed: true\n  prompt: test\n  verdict: ok\n---\n\n# Cycle\n"
        )
        result = admit_node(cycle_node, kb, require_reviews=False)
        assert not result.success
        msgs = " ".join(d.message for d in result.diagnostics)
        assert "duplicate" in msgs or "cycle" in msgs


class TestAdmitPlacement:
    def test_correct_topic_directory(self, tmp_path):
        kb = _setup_test_knowledge(tmp_path)
        staged = kb / "staged" / "mixed_strategy.md"

        text = staged.read_text()
        text = text.replace(
            "tags:",
            "generality:\n  reviewed: true\n  prompt: test\n  verdict: ok\ntags:",
        )
        staged.write_text(text)

        result = admit_node(staged, kb, require_reviews=False)
        assert result.success
        assert "strategic_games" in str(result.target_path)


class TestAdmitCLI:
    def test_cli_no_args_shows_usage(self):
        result = subprocess.run(
            [sys.executable, "-m", "tools.knowledge.admit"],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        assert "Usage" in result.stdout

    def test_cli_successful_admission(self, tmp_path):
        kb = _setup_test_knowledge(tmp_path)
        staged = kb / "staged" / "mixed_strategy.md"

        text = staged.read_text()
        text = text.replace(
            "tags:",
            "generality:\n  reviewed: true\n  prompt: test\n  verdict: ok\ntags:",
        )
        staged.write_text(text)

        reviews_dir = kb / "reviews"
        reviews_dir.mkdir(exist_ok=True)
        (reviews_dir / "review.md").write_text(
            "---\nagent: statement-verifier\ntarget:\n  node_id: strategic_games.mixed_strategy\n"
            "decision: accepted\n---\nOK.\n"
        )

        result = subprocess.run(
            [sys.executable, "-m", "tools.knowledge.admit", str(staged), str(kb)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Admitted" in result.stdout

    def test_cli_blocked_admission(self, tmp_path):
        kb = _setup_test_knowledge(tmp_path)
        staged = kb / "staged" / "mixed_strategy.md"

        result = subprocess.run(
            [sys.executable, "-m", "tools.knowledge.admit", str(staged), str(kb)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        assert "blocked" in result.stdout.lower()
