import json
from pathlib import Path

from tools.knowledge.blueprint_view import build_blueprint_graph, graph_to_dot
from tools.knowledge.graph import build_graph
from tools.knowledge.parser import scan_directory
from tools.knowledge.export import (
    export_graph_json,
    export_topic_hierarchy_json,
    export_topic_overview_json,
    export_topic_subgraph_json,
    parent_topic_id,
    topic_depth,
    write_graph_json,
    topic_id_for_node,
    topic_path,
    topic_slug,
)

NODES_DIR = Path(__file__).parent / "fixtures" / "generic_knowledge" / "nodes" / "algebra"


class TestTopicPathHelpers:
    def test_hierarchical_topic_ids_use_all_but_node_slug(self):
        from tools.knowledge.models import Node

        assert topic_id_for_node(Node(id="algebra.group", title="Group", kind="definition", status="admitted")) == "algebra"
        assert topic_id_for_node(Node(
            id="game_theory.strategic.nash",
            title="Nash",
            kind="theorem",
            status="admitted",
        )) == "game_theory.strategic"
        assert topic_id_for_node(Node(
            id="game_theory.strategic.refinements.perfect",
            title="Perfect",
            kind="theorem",
            status="admitted",
        )) == "game_theory.strategic.refinements"

    def test_topic_path_helpers_are_stable(self):
        assert parent_topic_id("game_theory.strategic.refinements") == "game_theory.strategic"
        assert parent_topic_id("game_theory") is None
        assert topic_depth("game_theory.strategic.refinements") == 3
        assert topic_slug("game_theory.strategic.refinements") == "game_theory-strategic-refinements"
        assert topic_path("game_theory.strategic.refinements") == "game_theory/strategic/refinements"


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
        # Edges point from dependency (source) to dependent (target):
        # group_homomorphism uses group, so the edge is group -> group_homomorphism.
        assert ("algebra.group", "algebra.group_homomorphism") in edge_pairs

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

    def test_graph_json_edges_point_from_dependency_to_dependent(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        data = export_graph_json(g)

        assert set(data) == {"nodes", "edges"}
        # group_homomorphism uses group, so the edge is group -> group_homomorphism.
        assert {"from": "algebra.group", "to": "algebra.group_homomorphism"} in data["edges"]

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
        # Attachment edge (target -> plan) must not appear in the uses-edge list.
        assert ("t.thm", "t.thm.plan.direct") not in edge_pairs
        # Plan uses base, so the edge is base -> plan (dependency -> dependent).
        assert ("t.base", "t.thm.plan.direct") in edge_pairs


class TestExportTopicOverviewJson:
    def test_hierarchical_overview_shows_root_topics_not_leaf_subtopics(self):
        from tools.knowledge.models import Node

        zero_sum = Node(
            id="game_theory.zero_sum.minimax",
            title="Minimax",
            kind="theorem",
            status="admitted",
        )
        strategic = Node(
            id="game_theory.strategic.nash",
            title="Nash",
            kind="theorem",
            status="admitted",
            uses=["game_theory.zero_sum.minimax"],
        )
        logic = Node(id="logic.basic.true_intro", title="Truth", kind="lemma", status="proved")
        graph, diags = build_graph([zero_sum, strategic, logic])
        assert diags == []

        data = export_topic_overview_json(graph)

        assert [topic["id"] for topic in data["topics"]] == ["game_theory", "logic"]
        game_theory = data["topics"][0]
        assert game_theory["node_count"] == 2
        assert game_theory["children"] == ["game_theory.strategic", "game_theory.zero_sum"]
        assert game_theory["href"] == "game_theory/index.html"
        assert data["edges"] == []

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

    def test_secondary_topics_tag_does_not_fabricate_cross_topic_edge(self):
        """Regression for #131.

        A node tagged with a secondary topic from a different root for
        navigation purposes (e.g. primary_topic: zero_sum, topics:
        [zero_sum, mixed_strategy]) must not produce a phantom
        zero_sum <-> mixed_strategy overview edge when its only `uses:`
        target is internal to zero_sum.
        """
        from tools.knowledge.models import Node

        prereq = Node(
            id="zero_sum.value_function",
            title="Value Function",
            kind="definition",
            status="admitted",
            primary_topic="zero_sum",
            topics=["zero_sum"],
        )
        consumer = Node(
            id="zero_sum.minimax",
            title="Minimax",
            kind="theorem",
            status="admitted",
            primary_topic="zero_sum",
            # Secondary tag from a different root — discoverability only.
            topics=["zero_sum", "mixed_strategy"],
            uses=["zero_sum.value_function"],
        )
        graph, diags = build_graph([prereq, consumer])
        assert diags == []

        data = export_topic_overview_json(graph)

        # No cross-topic edges should be emitted; both nodes are home-rooted in zero_sum.
        cross_topic_edges = [e for e in data["edges"] if e["from"] != e["to"]]
        assert cross_topic_edges == []

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
    def test_parent_topic_subgraph_contains_immediate_child_topics_and_edges(self):
        from tools.knowledge.models import Node

        base = Node(
            id="game_theory.zero_sum.minimax",
            title="Minimax",
            kind="theorem",
            status="admitted",
        )
        nash = Node(
            id="game_theory.strategic.nash",
            title="Nash",
            kind="theorem",
            status="admitted",
            uses=["game_theory.zero_sum.minimax"],
        )
        perfect = Node(
            id="game_theory.strategic.refinements.perfect",
            title="Perfect Equilibrium",
            kind="theorem",
            status="staged",
            uses=["game_theory.strategic.nash"],
        )
        graph, diags = build_graph([base, nash, perfect])
        assert diags == []

        data = export_topic_subgraph_json(graph, "game_theory")

        assert data["topic"]["id"] == "game_theory"
        assert data["counts"]["descendant_nodes"] == 3
        assert [topic["id"] for topic in data["child_topic_nodes"]] == [
            "game_theory.strategic",
            "game_theory.zero_sum",
        ]
        strategic = data["child_topic_nodes"][0]
        assert strategic["parent"] == "game_theory"
        assert strategic["node_count"] == 2
        assert strategic["children"] == ["game_theory.strategic.refinements"]
        assert data["child_topic_edges"] == [
            {
                "from": "topic:game_theory.zero_sum",
                "to": "topic:game_theory.strategic",
                "kind": "topic_dependency",
                "count": 1,
            }
        ]
        assert data["nodes"] == []

    def test_parent_topic_subgraph_contains_boundary_topics_for_external_edges(self):
        from tools.knowledge.models import Node

        logic = Node(id="logic.order.preorder", title="Preorder", kind="definition", status="admitted")
        base = Node(
            id="algebra.groups.group",
            title="Group",
            kind="definition",
            status="admitted",
            uses=["logic.order.preorder"],
        )
        theorem = Node(
            id="topology.groups.topological_group",
            title="Topological Group",
            kind="definition",
            status="admitted",
            uses=["algebra.groups.group"],
        )
        graph, diags = build_graph([logic, base, theorem])
        assert diags == []

        data = export_topic_subgraph_json(graph, "algebra")

        assert data["child_boundary_topics"] == [
            {
                "id": "logic.order",
                "title": "Logic.Order",
                "href": "logic/order/index.html",
                "role": "dependency",
                "node_count": 1,
            },
            {
                "id": "topology.groups",
                "title": "Topology.Groups",
                "href": "topology/groups/index.html",
                "role": "dependent",
                "node_count": 1,
            },
        ]
        assert data["child_boundary_edges"] == [
            {
                "from": "topic:logic.order",
                "to": "topic:algebra.groups",
                "kind": "boundary_dependency",
                "topic": "logic.order",
                "count": 1,
            },
            {
                "from": "topic:algebra.groups",
                "to": "topic:topology.groups",
                "kind": "boundary_dependent",
                "topic": "topology.groups",
                "count": 1,
            },
        ]

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

    def test_hierarchy_artifact_includes_ancestor_topics_without_direct_nodes(self):
        from tools.knowledge.models import Node

        nodes = [
            Node(id="game_theory.strategic.nash", title="Nash", kind="theorem", status="admitted"),
            Node(id="game_theory.strategic.refinements.perfect", title="Perfect", kind="theorem", status="staged"),
            Node(id="game_theory.zero_sum.minimax", title="Minimax", kind="theorem", status="proved"),
        ]
        graph, diags = build_graph(nodes)
        assert diags == []

        data = export_topic_hierarchy_json(graph)

        assert [topic["id"] for topic in data["roots"]] == ["game_theory"]
        assert data["topics"]["game_theory"]["node_count"] == 3
        assert data["topics"]["game_theory"]["children"] == [
            "game_theory.strategic",
            "game_theory.zero_sum",
        ]
        assert data["topics"]["game_theory.strategic"]["children"] == [
            "game_theory.strategic.refinements"
        ]

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

    def test_boundary_topics_do_not_duplicate_when_node_carries_secondary_same_root_tag(self):
        """Regression for #135.

        A node tagged with `primary_topic: linear_algebra` and
        `topics: [linear_algebra, linear_algebra.alternatives]` must
        contribute exactly one boundary topic (`linear_algebra`) when
        seen from a different-root topic's subgraph view — the
        secondary tag is a discoverability label, not a second
        graph endpoint.
        """
        from tools.knowledge.models import Node

        la = Node(
            id="linear_algebra.theorem_of_alternative",
            title="Theorem of Alternative",
            kind="theorem",
            status="admitted",
            primary_topic="linear_algebra",
            topics=["linear_algebra", "linear_algebra.alternatives"],
        )
        duality = Node(
            id="linear_programming.duality.strong",
            title="Strong Duality",
            kind="theorem",
            status="admitted",
            primary_topic="linear_programming.duality",
            uses=["linear_algebra.theorem_of_alternative"],
        )
        graph, diags = build_graph([la, duality])
        assert diags == []

        data = export_topic_subgraph_json(graph, "linear_programming.duality")
        boundary_ids = [t["id"] for t in data["boundary_topics"]]
        # Exactly one boundary, named by the home topic — not by every
        # `topics:[]` entry.
        assert boundary_ids == ["linear_algebra"]
        # Edge endpoints likewise use the home topic, not the secondary tag.
        boundary_edge_sources = {e["from"] for e in data["boundary_edges"]}
        assert "topic:linear_algebra.alternatives" not in boundary_edge_sources

    def test_child_topic_edges_do_not_duplicate_under_secondary_same_root_tag(self):
        """Regression for #135 (child-topic edge half).

        Inside a parent topic's subgraph, a child node that carries a
        sibling-child `topics:[]` tag must not generate a phantom child-
        topic edge to that sibling.
        """
        from tools.knowledge.models import Node

        # Both nodes live under `algebra` parent topic, in different
        # child topics. The first node carries a secondary tag that
        # also names the second node's child topic — this used to
        # fabricate a self-loop-like edge.
        a = Node(
            id="algebra.groups.identity_unique",
            title="Group Identity Unique",
            kind="theorem",
            status="admitted",
            primary_topic="algebra.groups",
            topics=["algebra.groups", "algebra.monoids"],
            uses=["algebra.groups.group"],
        )
        b = Node(
            id="algebra.groups.group",
            title="Group",
            kind="definition",
            status="admitted",
            primary_topic="algebra.groups",
        )
        graph, diags = build_graph([a, b])
        assert diags == []

        data = export_topic_subgraph_json(graph, "algebra")
        # No phantom edge from `algebra.monoids` to `algebra.groups`
        # induced by the secondary tag on node `a`.
        child_edges = [
            (e["from"], e["to"])
            for e in data["edges"]
            if e["from"].startswith("topic:") and e["to"].startswith("topic:")
        ]
        assert ("topic:algebra.monoids", "topic:algebra.groups") not in child_edges

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
            id="algebra.plan",
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
            "from": "algebra.plan",
            "to": "algebra.group_identity_unique",
            "kind": "has_plan",
            "plan_status": "selected",
        } in data["proof_plan_attachments"]
        assert {
            "from": "algebra.group",
            "to": "algebra.plan",
            "kind": "proof_plan_uses",
        } in data["edges"]
        assert {
            "from": "algebra.group",
            "to": "algebra.plan",
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
            id="algebra.plan_logic",
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
            "to": "algebra.plan_logic",
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
            id="algebra.plan",
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


class TestMultiTopicMembership:
    """Tests for Issue #75: explicit topics list for multi-topic node membership."""

    def _make_node(self, node_id: str, topics: list[str] | None = None):
        from tools.knowledge.models import Node
        return Node(
            id=node_id,
            title=node_id.replace(".", " ").title(),
            kind="theorem",
            status="admitted",
            topics=topics or [],
        )

    def test_leaf_topic_ids_for_node_falls_back_to_id_derived(self):
        from tools.knowledge.models import Node
        from tools.knowledge.export import leaf_topic_ids_for_node, topic_id_for_node
        node = Node(id="algebra.group", title="Group", kind="definition", status="admitted")
        assert leaf_topic_ids_for_node(node) == [topic_id_for_node(node)]

    def test_leaf_topic_ids_for_node_returns_explicit_topics(self):
        from tools.knowledge.models import Node
        from tools.knowledge.export import leaf_topic_ids_for_node
        node = Node(
            id="algebra.group",
            title="Group",
            kind="definition",
            status="admitted",
            topics=["algebra", "linear_programming.duality"],
        )
        assert leaf_topic_ids_for_node(node) == ["algebra", "linear_programming.duality"]

    def test_node_with_explicit_topics_appears_in_both_topic_subgraphs(self):
        from tools.knowledge.graph import build_graph
        from tools.knowledge.export import export_topic_subgraph_json

        shared = self._make_node("zero_sum.minimax", topics=["zero_sum", "linear_programming"])
        other_zero_sum = self._make_node("zero_sum.payoff")
        other_lp = self._make_node("linear_programming.simplex")

        graph, diags = build_graph([shared, other_zero_sum, other_lp])
        assert diags == []

        zs_data = export_topic_subgraph_json(graph, "zero_sum")
        lp_data = export_topic_subgraph_json(graph, "linear_programming")

        zs_ids = {n["id"] for n in zs_data["nodes"]}
        lp_ids = {n["id"] for n in lp_data["nodes"]}

        assert "zero_sum.minimax" in zs_ids
        assert "zero_sum.minimax" in lp_ids
        assert "zero_sum.payoff" in zs_ids
        assert "linear_programming.simplex" in lp_ids

    def test_topic_hierarchy_includes_node_in_all_explicit_topics(self):
        from tools.knowledge.graph import build_graph
        from tools.knowledge.export import export_topic_overview_json

        shared = self._make_node("zero_sum.minimax", topics=["zero_sum", "linear_programming"])
        graph, diags = build_graph([shared])
        assert diags == []

        data = export_topic_overview_json(graph)
        topic_ids = [t["id"] for t in data["topics"]]
        assert "zero_sum" in topic_ids
        assert "linear_programming" in topic_ids

        zs = next(t for t in data["topics"] if t["id"] == "zero_sum")
        lp = next(t for t in data["topics"] if t["id"] == "linear_programming")
        assert zs["node_count"] == 1
        assert lp["node_count"] == 1

    def test_topic_overview_edges_use_home_topic_not_secondary_memberships(self):
        """Updated for #131: overview edges follow each node's single
        canonical (home) topic — derived from ``primary_topic`` when set,
        otherwise from the node id. Secondary entries in ``topics:`` are
        discoverability tags and must not fabricate cross-topic edges.
        """
        from tools.knowledge.graph import build_graph
        from tools.knowledge.export import export_topic_overview_json

        dependency = self._make_node(
            "legacy.duality",
            topics=["linear_programming.duality"],
        )
        dependent = self._make_node(
            "zero_sum.minimax",
            topics=["zero_sum", "game_theory.zero_sum"],
        )
        dependent.uses = ["legacy.duality"]

        graph, diags = build_graph([dependency, dependent])
        assert diags == []

        data = export_topic_overview_json(graph)

        # Edge is derived from the home topics only:
        #   legacy.duality (home root: legacy) -> zero_sum.minimax (home root: zero_sum)
        # No phantom linear_programming / game_theory edges from secondary tags.
        assert data["edges"] == [
            {"from": "legacy", "to": "zero_sum", "count": 1},
        ]

    def test_subgraph_links_and_boundary_topics_use_home_topic(self):
        from tools.knowledge.graph import build_graph
        from tools.knowledge.export import export_topic_subgraph_json
        from tools.knowledge.models import Node

        dependency = Node(
            id="legacy.duality",
            title="Duality",
            kind="theorem",
            status="admitted",
            primary_topic="linear_programming.duality",
            topics=["linear_programming.duality"],
        )
        dependent = Node(
            id="legacy.minimax",
            title="Minimax",
            kind="theorem",
            status="admitted",
            primary_topic="game_theory.zero_sum",
            topics=["game_theory.zero_sum"],
            uses=["legacy.duality"],
        )

        graph, diags = build_graph([dependency, dependent])
        assert diags == []

        data = export_topic_subgraph_json(graph, "game_theory.zero_sum")

        assert data["nodes"] == [
            {
                "id": "legacy.minimax",
                "title": "Minimax",
                "kind": "theorem",
                "status": "admitted",
                "href": "game_theory/zero_sum/legacy_minimax.html",
                "payload": "node_payloads/legacy_minimax.json",
            }
        ]
        assert data["boundary_topics"] == [
            {
                "id": "linear_programming.duality",
                "title": "Linear Programming.Duality",
                "href": "linear_programming/duality/index.html",
                "role": "dependency",
                "node_count": 1,
            }
        ]

    def test_graph_json_includes_topics_field_when_set(self):
        from tools.knowledge.graph import build_graph
        from tools.knowledge.export import export_graph_json

        node = self._make_node("zero_sum.minimax", topics=["zero_sum", "linear_programming"])
        graph, _ = build_graph([node])
        data = export_graph_json(graph)

        entry = next(n for n in data["nodes"] if n["id"] == "zero_sum.minimax")
        assert entry["topics"] == ["zero_sum", "linear_programming"]

    def test_graph_json_omits_topics_field_when_empty(self):
        from tools.knowledge.graph import build_graph
        from tools.knowledge.export import export_graph_json

        node = self._make_node("algebra.group")
        graph, _ = build_graph([node])
        data = export_graph_json(graph)

        entry = next(n for n in data["nodes"] if n["id"] == "algebra.group")
        assert "topics" not in entry

    def test_node_appears_only_once_per_topic_subgraph(self):
        from tools.knowledge.graph import build_graph
        from tools.knowledge.export import export_topic_subgraph_json

        node = self._make_node("zero_sum.minimax", topics=["zero_sum", "linear_programming"])
        graph, _ = build_graph([node])

        zs_data = export_topic_subgraph_json(graph, "zero_sum")
        ids = [n["id"] for n in zs_data["nodes"]]
        assert ids.count("zero_sum.minimax") == 1
