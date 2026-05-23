from pathlib import Path

import pytest

from tools.knowledge.promote_via_plan import (
    _canonical_plan,
    _rewrite_frontmatter,
    promote,
)


def _write_kb(root: Path, files: dict[str, str]) -> None:
    for relpath, content in files.items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _kb_config(root: Path) -> None:
    (root / "mdblueprint.yml").write_text("site:\n  title: Test\n", encoding="utf-8")


def _base_definition(node_id: str) -> str:
    return (
        f"---\nid: {node_id}\ntitle: Base\nkind: definition\nstatus: formalized\n"
        f"uses: []\nlean:\n  modules: [Lib.Mod]\n  declarations: [Lib.def_x]\n"
        f"---\n\n# Base\n"
    )


def _theorem(node_id: str, status: str = "formalized", uses: list[str] | None = None) -> str:
    uses_yaml = "[]" if not uses else "\n  - " + "\n  - ".join(uses)
    if uses:
        uses_line = "uses:\n  - " + "\n  - ".join(uses)
    else:
        uses_line = "uses: []"
    return (
        f"---\nid: {node_id}\ntitle: Theorem\nkind: theorem\nstatus: {status}\n"
        f"{uses_line}\nlean:\n  modules: [Lib.Mod]\n  declarations: [Lib.thm_x]\n"
        f"---\n\n# Theorem\n"
    )


def _plan(
    plan_id: str, target: str, *, plan_status: str = "selected",
    status: str = "formalized", uses: list[str] | None = None,
) -> str:
    if uses:
        uses_line = "uses:\n  - " + "\n  - ".join(uses)
    else:
        uses_line = "uses: []"
    return (
        f"---\nid: {plan_id}\ntitle: Plan\nkind: proof-plan\nstatus: {status}\n"
        f"target: {target}\nplan_status: {plan_status}\n{uses_line}\n"
        f"lean:\n  modules: [Lib.Mod]\n  declarations: [Lib.plan_x]\n"
        f"---\n\n# Plan\n"
    )


class TestRewriteFrontmatter:
    def test_inserts_marker_after_status_line(self):
        original = (
            "---\nid: t.thm\ntitle: Theorem\nkind: theorem\nstatus: formalized\nuses: []\n---\n\n# Body\n"
        )
        rewritten = _rewrite_frontmatter(original, plan_id="t.thm.plan.direct")
        assert "status: proved\n" in rewritten
        assert "proved_via_plan: t.thm.plan.direct\n" in rewritten
        # Marker must come right after status.
        lines = rewritten.split("\n")
        status_index = next(i for i, line in enumerate(lines) if line.startswith("status:"))
        assert lines[status_index + 1] == "proved_via_plan: t.thm.plan.direct"
        # Body untouched.
        assert "# Body" in rewritten

    def test_replaces_existing_marker(self):
        original = (
            "---\nid: t.thm\ntitle: Theorem\nkind: theorem\nstatus: proved\n"
            "proved_via_plan: t.old_plan\nuses: []\n---\n\n# Body\n"
        )
        rewritten = _rewrite_frontmatter(original, plan_id="t.new_plan")
        assert "proved_via_plan: t.new_plan" in rewritten
        assert "proved_via_plan: t.old_plan" not in rewritten

    def test_raises_when_no_frontmatter(self):
        with pytest.raises(ValueError):
            _rewrite_frontmatter("# Just a body\n", plan_id="p")


class TestCanonicalPlan:
    def test_prefers_selected_over_candidate(self, tmp_path):
        from tools.knowledge.graph import build_graph
        from tools.knowledge.models import Node

        base = Node(id="t.base", title="B", kind="definition", status="formalized")
        candidate = Node(
            id="t.thm.plan.alpha", title="A", kind="proof-plan",
            status="formalized", target="t.thm", plan_status="candidate", uses=["t.base"],
        )
        selected = Node(
            id="t.thm.plan.beta", title="B", kind="proof-plan",
            status="formalized", target="t.thm", plan_status="selected", uses=["t.base"],
        )
        thm = Node(id="t.thm", title="T", kind="theorem", status="formalized", uses=[])
        g, _ = build_graph([base, candidate, selected, thm])
        assert _canonical_plan("t.thm", g) == "t.thm.plan.beta"

    def test_returns_none_when_no_plan_qualifies(self, tmp_path):
        from tools.knowledge.graph import build_graph
        from tools.knowledge.models import Node

        base = Node(id="t.base", title="B", kind="definition", status="formalized")
        unfinished = Node(
            id="t.thm.plan.draft", title="D", kind="proof-plan",
            status="staged", target="t.thm", plan_status="candidate", uses=["t.base"],
        )
        thm = Node(id="t.thm", title="T", kind="theorem", status="formalized", uses=[])
        g, _ = build_graph([base, unfinished, thm])
        assert _canonical_plan("t.thm", g) is None


class TestPromoteCommand:
    def test_promotes_qualifying_theorem(self, tmp_path, capsys):
        kb = tmp_path / "kb"
        nodes_dir = kb / "nodes" / "topic"
        _write_kb(nodes_dir, {
            "base.md": _base_definition("topic.base"),
            "thm.md": _theorem("topic.thm", uses=[]),
            "plan.md": _plan("topic.thm.plan.direct", "topic.thm", uses=["topic.base"]),
        })
        _kb_config(kb)

        exit_code = promote(kb, dry_run=False)
        assert exit_code == 0

        rewritten = (nodes_dir / "thm.md").read_text(encoding="utf-8")
        assert "status: proved" in rewritten
        assert "proved_via_plan: topic.thm.plan.direct" in rewritten

    def test_dry_run_does_not_modify_files(self, tmp_path):
        kb = tmp_path / "kb"
        nodes_dir = kb / "nodes" / "topic"
        _write_kb(nodes_dir, {
            "base.md": _base_definition("topic.base"),
            "thm.md": _theorem("topic.thm"),
            "plan.md": _plan("topic.thm.plan.direct", "topic.thm", uses=["topic.base"]),
        })
        _kb_config(kb)

        before = (nodes_dir / "thm.md").read_text(encoding="utf-8")
        exit_code = promote(kb, dry_run=True)
        after = (nodes_dir / "thm.md").read_text(encoding="utf-8")
        assert exit_code == 0
        assert before == after

    def test_idempotent_on_already_promoted_files(self, tmp_path):
        kb = tmp_path / "kb"
        nodes_dir = kb / "nodes" / "topic"
        _write_kb(nodes_dir, {
            "base.md": _base_definition("topic.base"),
            "thm.md": _theorem("topic.thm"),
            "plan.md": _plan("topic.thm.plan.direct", "topic.thm", uses=["topic.base"]),
        })
        _kb_config(kb)

        promote(kb, dry_run=False)
        mtime_after_first = (nodes_dir / "thm.md").stat().st_mtime
        content_after_first = (nodes_dir / "thm.md").read_text(encoding="utf-8")

        promote(kb, dry_run=False)
        content_after_second = (nodes_dir / "thm.md").read_text(encoding="utf-8")
        # Idempotent: status is now 'proved' so the theorem is no longer a candidate
        # and the file content should match exactly.
        assert content_after_first == content_after_second

    def test_skips_theorem_with_unfinished_plan(self, tmp_path):
        kb = tmp_path / "kb"
        nodes_dir = kb / "nodes" / "topic"
        _write_kb(nodes_dir, {
            "base.md": _base_definition("topic.base"),
            "thm.md": _theorem("topic.thm"),
            "plan.md": _plan(
                "topic.thm.plan.draft", "topic.thm",
                status="staged", plan_status="candidate", uses=["topic.base"],
            ),
        })
        # staged plan must live in staged/ directory per directory-status rules.
        # Move plan to staged.
        (nodes_dir / "plan.md").unlink()
        staged_dir = kb / "staged" / "topic"
        _write_kb(staged_dir, {
            "plan.md": _plan(
                "topic.thm.plan.draft", "topic.thm",
                status="staged", plan_status="candidate", uses=["topic.base"],
            ),
        })
        _kb_config(kb)

        before = (nodes_dir / "thm.md").read_text(encoding="utf-8")
        exit_code = promote(kb, dry_run=False)
        after = (nodes_dir / "thm.md").read_text(encoding="utf-8")
        assert exit_code == 0
        assert before == after

    def test_refuses_when_knowledge_base_has_errors(self, tmp_path, capsys):
        kb = tmp_path / "kb"
        nodes_dir = kb / "nodes" / "topic"
        _write_kb(nodes_dir, {
            # Theorem references a missing dependency: build_graph errors.
            "thm.md": _theorem("topic.thm", uses=["topic.missing"]),
        })
        _kb_config(kb)

        exit_code = promote(kb, dry_run=False)
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "Refusing to promote" in captured.err
