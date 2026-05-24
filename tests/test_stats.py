"""Tests for tools.knowledge.stats (mdblueprint-stats CLI)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.knowledge.graph import build_graph
from tools.knowledge.parser import scan_directory
from tools.knowledge.stats import (
    _dag_longest_path,
    _load_nodes,
    _orphan_count,
    _top_by_in_degree,
    _top_by_out_degree,
    compute_stats,
    main,
    render_json,
    render_text,
)


# ── Fixture helpers ───────────────────────────────────────────────────────────


def _write_node(
    directory: Path,
    filename: str,
    *,
    node_id: str,
    kind: str = "definition",
    status: str = "admitted",
    uses: list[str] | None = None,
    primary_topic: str | None = None,
    verification: dict | None = None,
) -> None:
    """Write a minimal valid node file."""
    lines = [
        "---",
        f"id: {node_id}",
        f"title: {node_id.split('.')[-1].replace('_', ' ').title()}",
        f"kind: {kind}",
        f"status: {status}",
    ]
    if uses:
        lines.append("uses:")
        for dep in uses:
            lines.append(f"  - {dep}")
    if primary_topic is not None:
        lines.append(f"primary_topic: {primary_topic}")
    if verification is not None:
        lines.append("verification:")
        for k, v in verification.items():
            lines.append(f"  {k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {node_id}")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text("\n".join(lines))


def _make_minimal_kb(tmp_path: Path) -> Path:
    """Minimal 1-node knowledge base (admitted only, no staged)."""
    root = tmp_path / "kb"
    (root / "nodes").mkdir(parents=True)
    (root / "staged").mkdir(parents=True)
    (root / "mdblueprint.yml").write_text("site:\n  title: Stats Test\n")
    _write_node(root / "nodes", "a.md", node_id="test.a")
    return root


def _make_chain_kb(tmp_path: Path) -> Path:
    """Three-node chain: A ← B ← C (depth=2)."""
    root = tmp_path / "chain"
    (root / "nodes").mkdir(parents=True)
    (root / "staged").mkdir(parents=True)
    (root / "mdblueprint.yml").write_text("site:\n  title: Chain Test\n")
    _write_node(root / "nodes", "a.md", node_id="t.a")
    _write_node(root / "nodes", "b.md", node_id="t.b", uses=["t.a"])
    _write_node(root / "nodes", "c.md", node_id="t.c", uses=["t.b"])
    return root


def _make_kind_kb(tmp_path: Path) -> Path:
    """2 definitions + 1 theorem."""
    root = tmp_path / "kinds"
    (root / "nodes").mkdir(parents=True)
    (root / "staged").mkdir(parents=True)
    (root / "mdblueprint.yml").write_text("site:\n  title: Kind Test\n")
    _write_node(root / "nodes", "d1.md", node_id="k.d1", kind="definition")
    _write_node(root / "nodes", "d2.md", node_id="k.d2", kind="definition", uses=["k.d1"])
    _write_node(root / "nodes", "th1.md", node_id="k.th1", kind="theorem", uses=["k.d1", "k.d2"])
    return root


def _make_staged_kb(tmp_path: Path) -> Path:
    """1 admitted node + 1 staged node."""
    root = tmp_path / "staged_kb"
    (root / "nodes").mkdir(parents=True)
    (root / "staged").mkdir(parents=True)
    (root / "mdblueprint.yml").write_text("site:\n  title: Staged Test\n")
    _write_node(root / "nodes", "a.md", node_id="s.a", status="admitted")
    _write_node(root / "staged", "b.md", node_id="s.b", status="staged", uses=["s.a"])
    return root


# ── Smoke tests ───────────────────────────────────────────────────────────────


class TestSmoke:
    def test_single_node_no_crash(self, tmp_path):
        root = _make_minimal_kb(tmp_path)
        nodes = _load_nodes(root, include_staged=True)
        graph, _ = build_graph(nodes)
        stats = compute_stats(nodes, graph, top_n=10)
        assert stats["totals"]["nodes"] == 1
        assert stats["dag"]["depth"] == 0
        assert stats["dag"]["orphans"] == 1

    def test_main_exits_zero(self, tmp_path):
        root = _make_minimal_kb(tmp_path)
        exit_code = main([str(root)])
        assert exit_code == 0

    def test_empty_kb_no_crash(self, tmp_path):
        root = tmp_path / "empty_kb"
        (root / "nodes").mkdir(parents=True)
        (root / "staged").mkdir(parents=True)
        (root / "mdblueprint.yml").write_text("site:\n  title: Empty\n")
        nodes = _load_nodes(root, include_staged=True)
        graph, _ = build_graph(nodes)
        stats = compute_stats(nodes, graph, top_n=10)
        assert stats["totals"]["nodes"] == 0
        assert stats["dag"]["depth"] == 0
        assert stats["dag"]["orphans"] == 0


# ── Kind histogram ────────────────────────────────────────────────────────────


class TestKindHistogram:
    def test_correct_counts(self, tmp_path):
        root = _make_kind_kb(tmp_path)
        nodes = _load_nodes(root, include_staged=True)
        graph, _ = build_graph(nodes)
        stats = compute_stats(nodes, graph)
        assert stats["kinds"]["definition"] == 2
        assert stats["kinds"]["theorem"] == 1
        assert "example" not in stats["kinds"]

    def test_totals_match_kind_sum(self, tmp_path):
        root = _make_kind_kb(tmp_path)
        nodes = _load_nodes(root, include_staged=True)
        graph, _ = build_graph(nodes)
        stats = compute_stats(nodes, graph)
        assert sum(stats["kinds"].values()) == stats["totals"]["nodes"]


# ── Hot-spot lists ────────────────────────────────────────────────────────────


class TestHotSpots:
    def test_in_degree_sorted_desc(self, tmp_path):
        """t.a is used by t.b and t.c; it should appear first."""
        root = _make_kind_kb(tmp_path)
        nodes = _load_nodes(root, include_staged=True)
        graph, _ = build_graph(nodes)
        stats = compute_stats(nodes, graph, top_n=10)
        hot_in = stats["hot_spots_in_degree"]
        # k.d1 is used by k.d2 and k.th1 → in-degree 2
        assert hot_in[0]["node_id"] == "k.d1"
        assert hot_in[0]["count"] == 2

    def test_out_degree_sorted_desc(self, tmp_path):
        root = _make_kind_kb(tmp_path)
        nodes = _load_nodes(root, include_staged=True)
        graph, _ = build_graph(nodes)
        stats = compute_stats(nodes, graph, top_n=10)
        hot_out = stats["hot_spots_out_degree"]
        # k.th1 uses k.d1 and k.d2 → out-degree 2
        assert hot_out[0]["node_id"] == "k.th1"
        assert hot_out[0]["count"] == 2

    def test_top_respects_limit(self, tmp_path):
        root = _make_kind_kb(tmp_path)
        nodes = _load_nodes(root, include_staged=True)
        graph, _ = build_graph(nodes)
        stats = compute_stats(nodes, graph, top_n=1)
        assert len(stats["hot_spots_in_degree"]) == 1
        assert len(stats["hot_spots_out_degree"]) == 1

    def test_top_zero_empty_lists(self, tmp_path):
        root = _make_kind_kb(tmp_path)
        nodes = _load_nodes(root, include_staged=True)
        graph, _ = build_graph(nodes)
        stats = compute_stats(nodes, graph, top_n=0)
        assert stats["hot_spots_in_degree"] == []
        assert stats["hot_spots_out_degree"] == []

    def test_stable_sort_on_ties(self, tmp_path):
        """Tied nodes must be sorted alphabetically for deterministic output."""
        root = tmp_path / "tied_kb"
        (root / "nodes").mkdir(parents=True)
        (root / "staged").mkdir(parents=True)
        (root / "mdblueprint.yml").write_text("site:\n  title: Tie Test\n")
        # a and b are both used by exactly 1 node each
        _write_node(root / "nodes", "a.md", node_id="z.a")
        _write_node(root / "nodes", "b.md", node_id="z.b")
        _write_node(root / "nodes", "x.md", node_id="z.x", uses=["z.a"])
        _write_node(root / "nodes", "y.md", node_id="z.y", uses=["z.b"])
        nodes = _load_nodes(root, include_staged=True)
        graph, _ = build_graph(nodes)
        stats = compute_stats(nodes, graph, top_n=10)
        # z.a and z.b are tied at in-degree 1; alphabetical tie-break
        in_ids = [e["node_id"] for e in stats["hot_spots_in_degree"] if e["count"] == 1]
        assert in_ids == sorted(in_ids)


# ── DAG depth ─────────────────────────────────────────────────────────────────


class TestDagDepth:
    def test_chain_abc_depth_is_2(self, tmp_path):
        root = _make_chain_kb(tmp_path)
        nodes = _load_nodes(root, include_staged=True)
        graph, _ = build_graph(nodes)
        assert _dag_longest_path(graph) == 2

    def test_single_node_depth_zero(self, tmp_path):
        root = _make_minimal_kb(tmp_path)
        nodes = _load_nodes(root, include_staged=True)
        graph, _ = build_graph(nodes)
        assert _dag_longest_path(graph) == 0

    def test_empty_graph_depth_zero(self):
        from tools.knowledge.graph import KnowledgeGraph
        assert _dag_longest_path(KnowledgeGraph()) == 0

    def test_parallel_chains(self, tmp_path):
        """Two parallel chains A→B and C→D: depth should be 1."""
        root = tmp_path / "parallel"
        (root / "nodes").mkdir(parents=True)
        (root / "staged").mkdir(parents=True)
        (root / "mdblueprint.yml").write_text("site:\n  title: Parallel\n")
        _write_node(root / "nodes", "a.md", node_id="p.a")
        _write_node(root / "nodes", "b.md", node_id="p.b", uses=["p.a"])
        _write_node(root / "nodes", "c.md", node_id="p.c")
        _write_node(root / "nodes", "d.md", node_id="p.d", uses=["p.c"])
        nodes = _load_nodes(root, include_staged=True)
        graph, _ = build_graph(nodes)
        assert _dag_longest_path(graph) == 1


# ── JSON output ───────────────────────────────────────────────────────────────


class TestJsonOutput:
    def test_valid_json_parses(self, tmp_path):
        root = _make_chain_kb(tmp_path)
        nodes = _load_nodes(root, include_staged=True)
        graph, _ = build_graph(nodes)
        stats = compute_stats(nodes, graph)
        raw = render_json(stats)
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_all_section_keys_present(self, tmp_path):
        root = _make_chain_kb(tmp_path)
        nodes = _load_nodes(root, include_staged=True)
        graph, _ = build_graph(nodes)
        stats = compute_stats(nodes, graph)
        raw = render_json(stats)
        parsed = json.loads(raw)
        expected_keys = {
            "totals",
            "kinds",
            "topics",
            "verification",
            "hot_spots_in_degree",
            "hot_spots_out_degree",
            "dag",
        }
        assert expected_keys <= set(parsed.keys())

    def test_numbers_are_numbers_not_strings(self, tmp_path):
        root = _make_kind_kb(tmp_path)
        nodes = _load_nodes(root, include_staged=True)
        graph, _ = build_graph(nodes)
        stats = compute_stats(nodes, graph)
        raw = render_json(stats)
        parsed = json.loads(raw)
        assert isinstance(parsed["totals"]["nodes"], int)
        assert isinstance(parsed["dag"]["depth"], int)
        assert isinstance(parsed["dag"]["orphans"], int)

    def test_main_json_flag(self, tmp_path, capsys):
        root = _make_chain_kb(tmp_path)
        exit_code = main([str(root), "--json"])
        assert exit_code == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert "totals" in parsed


# ── Staged flag ───────────────────────────────────────────────────────────────


class TestStagedFlag:
    def test_include_staged_true_counts_both(self, tmp_path):
        root = _make_staged_kb(tmp_path)
        nodes = _load_nodes(root, include_staged=True)
        graph, _ = build_graph(nodes)
        stats = compute_stats(nodes, graph)
        assert stats["totals"]["nodes"] == 2
        assert stats["totals"]["staged"] == 1

    def test_include_staged_false_excludes_staged(self, tmp_path):
        root = _make_staged_kb(tmp_path)
        nodes = _load_nodes(root, include_staged=False)
        graph, _ = build_graph(nodes)
        stats = compute_stats(nodes, graph)
        assert stats["totals"]["nodes"] == 1
        assert stats["totals"]["staged"] == 0

    def test_main_no_include_staged_flag(self, tmp_path):
        root = _make_staged_kb(tmp_path)
        nodes = _load_nodes(root, include_staged=False)
        graph, _ = build_graph(nodes)
        stats = compute_stats(nodes, graph)
        # hot spots should only contain admitted node s.a
        # s.b is excluded so s.a has no in-edges from the loaded set
        all_ids = {e["node_id"] for e in stats["hot_spots_in_degree"]}
        all_ids |= {e["node_id"] for e in stats["hot_spots_out_degree"]}
        assert "s.b" not in all_ids

    def test_main_cli_no_include_staged(self, tmp_path):
        root = _make_staged_kb(tmp_path)
        exit_code = main([str(root), "--no-include-staged", "--json"])
        assert exit_code == 0
