import json
from pathlib import Path

from tools.knowledge.blueprint_view import build_blueprint_graph, graph_to_dot
from tools.knowledge.graph import build_graph
from tools.knowledge.parser import scan_directory
from tools.knowledge.export import (
    export_graph_json,
    export_topic_overview_json,
    export_topic_subgraph_json,
    write_graph_json,
)

NODES_DIR = Path(__file__).parent / "fixtures" / "generic_knowledge" / "nodes" / "algebra"


class TestExportGraphJson:
    def test_structure(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        data = export_graph_json(g)
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 4

    def test_node_fields(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        data = export_graph_json(g)
        group = next(n for n in data["nodes"] if n["id"] == "algebra.group")
        assert group["title"] == "Group"
        assert group["kind"] == "definition"
        assert group["status"] == "admitted"

    def test_edges(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        data = export_graph_json(g)
        edge_pairs = {(e["from"], e["to"]) for e in data["edges"]}
        assert ("algebra.group_homomorphism", "algebra.group") in edge_pairs

    def test_deterministic(self):
        nodes = scan_directory(NODES_DIR)
        g1, _ = build_graph(nodes)
        g2, _ = build_graph(nodes)
        d1 = json.dumps(export_graph_json(g1), sort_keys=True)
        d2 = json.dumps(export_graph_json(g2), sort_keys=True)
        assert d1 == d2

    def test_write_file(self, tmp_path):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        out = tmp_path / "graph.json"
        write_graph_json(g, out)
        assert out.exists()
        data = json.loads(out.read_text())
        assert len(data["nodes"]) == 4

    def test_lean_declarations(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        data = export_graph_json(g)
        group = next(n for n in data["nodes"] if n["id"] == "algebra.group")
        assert "Algebra.Group" in group["lean_declarations"]

    def test_reverse_deps(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        data = export_graph_json(g)
        group = next(n for n in data["nodes"] if n["id"] == "algebra.group")
        assert "algebra.group_homomorphism" in group.get("used_by", [])

    def test_blueprint_dot_uses_dependency_to_dependent_direction(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        view = build_blueprint_graph(g)
        dot = graph_to_dot(view)

        assert '"algebra.group" -> "algebra.group_homomorphism"' in dot

    def test_blueprint_dot_uses_leanblueprint_shapes(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        view = build_blueprint_graph(g)
        dot = graph_to_dot(view)

        assert 'shape="box"' in dot
        assert 'shape="ellipse"' in dot

    def test_existing_graph_json_shape_is_unchanged(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        data = export_graph_json(g)

        assert set(data) == {"nodes", "edges"}
        assert {"from": "algebra.group_homomorphism", "to": "algebra.group"} in data["edges"]

    def test_proof_plan_metadata_exports_without_attachment_edge_polluting_uses(self):
        from tools.knowledge.models import Node

        base = Node(id="t.base", title="Base", kind="definition", status="admitted")
        thm = Node(id="t.thm", title="Theorem", kind="theorem", status="admitted", uses=["t.base"])
        plan = Node(
            id="t.thm.plan.direct",
            title="Direct Plan",
            kind="proof-plan",
            status="staged",
            target="t.thm",
            plan_status="selected",
            uses=["t.base"],
        )
        graph, diags = build_graph([base, thm, plan])
        assert diags == []

        data = export_graph_json(graph)
        plan_entry = next(node for node in data["nodes"] if node["id"] == plan.id)
        edge_pairs = {(edge["from"], edge["to"]) for edge in data["edges"]}

        assert plan_entry["target"] == "t.thm"
        assert plan_entry["plan_status"] == "selected"
        assert ("t.thm", "t.thm.plan.direct") not in edge_pairs
        assert ("t.thm.plan.direct", "t.base") in edge_pairs


class TestExportTopicOverviewJson:
    def test_topics_include_counts_and_cross_topic_dependency_edges(self):
        from tools.knowledge.models import Node

        algebra_group = Node(id="algebra.group", title="Group", kind="definition", status="admitted")
        algebra_theorem = Node(
            id="algebra.group_identity_unique",
            title="Group Identity Is Unique",
            kind="theorem",
            status="proved",
            uses=["algebra.group", "logic.exists_unique"],
        )
        logic_theorem = Node(
            id="logic.exists_unique",
            title="Exists Unique",
            kind="theorem",
            status="formalized",
        )
        graph, diags = build_graph([algebra_group, algebra_theorem, logic_theorem])
        assert diags == []

        data = export_topic_overview_json(graph)

        assert [topic["id"] for topic in data["topics"]] == ["algebra", "logic"]
        algebra = data["topics"][0]
        assert algebra["title"] == "Algebra"
        assert algebra["href"] == "algebra/index.html"
        assert algebra["node_count"] == 2
        assert algebra["kind_counts"] == {"definition": 1, "theorem": 1}
        assert algebra["status_counts"] == {"admitted": 1, "proved": 1}
        assert data["edges"] == [
            {
                "from": "logic",
                "to": "algebra",
                "count": 1,
            }
        ]

    def test_same_topic_edges_do_not_become_topic_self_edges(self):
        from tools.knowledge.models import Node

        base = Node(id="algebra.group", title="Group", kind="definition", status="admitted")
        theorem = Node(
            id="algebra.group_identity_unique",
            title="Group Identity Is Unique",
            kind="theorem",
            status="admitted",
            uses=["algebra.group"],
        )
        graph, diags = build_graph([base, theorem])
        assert diags == []

        data = export_topic_overview_json(graph)

        assert [topic["id"] for topic in data["topics"]] == ["algebra"]
        assert data["edges"] == []

    def test_proof_plan_route_edges_do_not_create_topic_overview_edges(self):
        from tools.knowledge.models import Node

        approachability = Node(
            id="approachability.blackwell",
            title="Blackwell Approachability",
            kind="theorem",
            status="admitted",
        )
        minimax = Node(
            id="zerosum.minimax",
            title="Minimax",
            kind="theorem",
            status="admitted",
        )
        plan = Node(
            id="zerosum.minimax_from_approachability",
            title="Proof From Approachability",
            kind="proof-plan",
            status="staged",
            target="zerosum.minimax",
            plan_status="candidate",
            uses=["approachability.blackwell"],
        )
        graph, diags = build_graph([approachability, minimax, plan])
        assert diags == []

        data = export_topic_overview_json(graph)

        assert data["edges"] == []


class TestExportTopicSubgraphJson:
    def test_topic_subgraph_contains_internal_nodes_and_edges(self):
        from tools.knowledge.models import Node

        base = Node(id="algebra.group", title="Group", kind="definition", status="admitted")
        theorem = Node(
            id="algebra.group_identity_unique",
            title="Group Identity Is Unique",
            kind="theorem",
            status="admitted",
            uses=["algebra.group"],
        )
        graph, diags = build_graph([base, theorem])
        assert diags == []

        data = export_topic_subgraph_json(graph, "algebra")

        assert data["topic"]["id"] == "algebra"
        assert [node["id"] for node in data["nodes"]] == [
            "algebra.group",
            "algebra.group_identity_unique",
        ]
        assert data["edges"] == [
            {
                "from": "algebra.group",
                "to": "algebra.group_identity_unique",
                "kind": "uses",
            }
        ]
        assert data["boundary_topics"] == []
        assert data["boundary_edges"] == []

    def test_topic_subgraph_contains_dependency_and_dependent_boundary_topics(self):
        from tools.knowledge.models import Node

        algebra = Node(
            id="algebra.group",
            title="Group",
            kind="definition",
            status="admitted",
            uses=["logic.exists_unique"],
        )
        logic = Node(id="logic.exists_unique", title="Exists Unique", kind="theorem", status="admitted")
        topology = Node(
            id="topology.topological_group",
            title="Topological Group",
            kind="definition",
            status="admitted",
            uses=["algebra.group"],
        )
        graph, diags = build_graph([algebra, logic, topology])
        assert diags == []

        data = export_topic_subgraph_json(graph, "algebra")

        assert data["boundary_topics"] == [
            {
                "id": "logic",
                "title": "Logic",
                "href": "logic/index.html",
                "role": "dependency",
                "node_count": 1,
            },
            {
                "id": "topology",
                "title": "Topology",
                "href": "topology/index.html",
                "role": "dependent",
                "node_count": 1,
            },
        ]
        assert data["boundary_edges"] == [
            {
                "from": "topic:logic",
                "to": "algebra.group",
                "kind": "boundary_dependency",
                "topic": "logic",
                "count": 1,
            },
            {
                "from": "algebra.group",
                "to": "topic:topology",
                "kind": "boundary_dependent",
                "topic": "topology",
                "count": 1,
            },
        ]

    def test_topic_subgraph_keeps_proof_plan_attachments_separate_from_uses_edges(self):
        from tools.knowledge.models import Node

        base = Node(id="algebra.group", title="Group", kind="definition", status="admitted")
        theorem = Node(
            id="algebra.group_identity_unique",
            title="Group Identity Is Unique",
            kind="theorem",
            status="admitted",
            uses=["algebra.group"],
        )
        plan = Node(
            id="algebra.group_identity_unique.plan.direct",
            title="Direct Plan",
            kind="proof-plan",
            status="staged",
            target="algebra.group_identity_unique",
            plan_status="selected",
            uses=["algebra.group"],
        )
        graph, diags = build_graph([base, theorem, plan])
        assert diags == []

        data = export_topic_subgraph_json(graph, "algebra")

        assert {
            "from": "algebra.group_identity_unique",
            "to": "algebra.group_identity_unique.plan.direct",
            "kind": "has_plan",
            "plan_status": "selected",
        } in data["proof_plan_attachments"]
        assert {
            "from": "algebra.group",
            "to": "algebra.group_identity_unique.plan.direct",
            "kind": "proof_plan_uses",
        } in data["edges"]
        assert {
            "from": "algebra.group",
            "to": "algebra.group_identity_unique.plan.direct",
            "kind": "uses",
        } not in data["edges"]

    def test_topic_subgraph_marks_external_proof_plan_route_edges(self):
        from tools.knowledge.models import Node

        logic = Node(id="logic.exists_unique", title="Exists Unique", kind="theorem", status="admitted")
        theorem = Node(
            id="algebra.group_identity_unique",
            title="Group Identity Is Unique",
            kind="theorem",
            status="admitted",
        )
        plan = Node(
            id="algebra.group_identity_unique.plan.logic",
            title="Logic Plan",
            kind="proof-plan",
            status="staged",
            target="algebra.group_identity_unique",
            plan_status="candidate",
            uses=["logic.exists_unique"],
        )
        graph, diags = build_graph([logic, theorem, plan])
        assert diags == []

        data = export_topic_subgraph_json(graph, "algebra")

        assert {
            "from": "topic:logic",
            "to": "algebra.group_identity_unique.plan.logic",
            "kind": "boundary_proof_plan_dependency",
            "topic": "logic",
            "count": 1,
        } in data["boundary_edges"]

    def test_topic_subgraph_counts_support_large_topic_fallback(self):
        from tools.knowledge.models import Node

        base = Node(
            id="algebra.group",
            title="Group",
            kind="definition",
            status="admitted",
            tags=["algebra", "foundational"],
        )
        theorem = Node(
            id="algebra.group_identity_unique",
            title="Group Identity Is Unique",
            kind="theorem",
            status="admitted",
            uses=["algebra.group"],
            tags=["algebra", "theorem"],
        )
        plan = Node(
            id="algebra.group_identity_unique.plan.direct",
            title="Direct Plan",
            kind="proof-plan",
            status="staged",
            target="algebra.group_identity_unique",
            plan_status="selected",
            uses=["algebra.group"],
            tags=["plan"],
        )
        graph, diags = build_graph([base, theorem, plan])
        assert diags == []

        data = export_topic_subgraph_json(graph, "algebra")

        assert data["counts"]["internal_nodes"] == 3
        assert data["counts"]["non_proof_plan_nodes"] == 2
        assert data["counts"]["proof_plan_nodes"] == 1
        assert data["counts"]["selected_proof_plan_nodes"] == 1
        assert data["counts"]["visible_nodes_without_proof_plans"] == 3
        assert data["keywords"] == [
            {"id": "algebra", "title": "algebra", "href": "keywords/algebra.html", "count": 2},
            {"id": "foundational", "title": "foundational", "href": "keywords/foundational.html", "count": 1},
            {"id": "plan", "title": "plan", "href": "keywords/plan.html", "count": 1},
            {"id": "theorem", "title": "theorem", "href": "keywords/theorem.html", "count": 1},
        ]
