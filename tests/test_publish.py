import json
import textwrap
from pathlib import Path

import pytest
from tools.knowledge.publish import publish

ROOT = Path(__file__).parent.parent
KNOWLEDGE_ROOT = Path(__file__).parent.parent / "docs" / "knowledge"
GENERIC_KNOWLEDGE_ROOT = Path(__file__).parent / "fixtures" / "generic_knowledge"


def _graph_config_from_page(page: str) -> dict:
    start_marker = '<script id="graph-config" type="application/json">'
    start = page.index(start_marker) + len(start_marker)
    end = page.index("</script>", start)
    return json.loads(page[start:end])


class TestExampleCorpusPublish:
    def test_generates_output(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        site = tmp_path / "site"
        assert (site / "index.html").exists()
        assert (site / "graph.html").exists()
        assert (site / "graph.json").exists()
        assert (site / "style.css").exists()

    def test_topic_directory(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        site = tmp_path / "site"
        assert (site / "strategic_games" / "index.html").exists()

    def test_node_pages(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        site = tmp_path / "site"
        sg_page = site / "strategic_games" / "strategic_games_strategic_game.html"
        assert sg_page.exists()
        content = sg_page.read_text()
        assert "Strategic Game" in content
        assert "StrategicGame" in content

    def test_dependencies_listed(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        site = tmp_path / "site"
        ne_page = site / "strategic_games" / "strategic_games_nash_equilibrium.html"
        content = ne_page.read_text()
        assert "best_response" in content

    def test_reverse_deps_listed(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        site = tmp_path / "site"
        br_page = site / "strategic_games" / "strategic_games_best_response.html"
        content = br_page.read_text()
        assert "nash_equilibrium" in content

    def test_graph_json_valid(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        data = json.loads((tmp_path / "site" / "graph.json").read_text())
        assert len(data["nodes"]) >= 10

    def test_publishes_topic_overview_graph_artifact(self, tmp_path):
        publish(GENERIC_KNOWLEDGE_ROOT, tmp_path / "site")
        overview_path = tmp_path / "site" / "graph_topics.json"

        assert overview_path.exists()
        overview = json.loads(overview_path.read_text())
        assert overview["topics"][0]["id"] == "algebra"
        assert overview["topics"][0]["href"] == "algebra/index.html"
        assert overview["topics"][0]["node_count"] == 5
        assert overview["edges"] == []

    def test_publishes_topic_hierarchy_artifact(self, tmp_path):
        publish(GENERIC_KNOWLEDGE_ROOT, tmp_path / "site")
        hierarchy_path = tmp_path / "site" / "graph_topics_hierarchy.json"

        assert hierarchy_path.exists()
        hierarchy = json.loads(hierarchy_path.read_text())
        assert "roots" in hierarchy
        assert "topics" in hierarchy
        assert len(hierarchy["roots"]) == 1
        assert hierarchy["roots"][0]["id"] == "algebra"
        assert "algebra" in hierarchy["topics"]
        assert hierarchy["topics"]["algebra"]["id"] == "algebra"
        assert hierarchy["topics"]["algebra"]["depth"] == 1
        assert hierarchy["topics"]["algebra"]["children"] == []

    def test_publishes_per_topic_subgraph_artifacts(self, tmp_path):
        publish(GENERIC_KNOWLEDGE_ROOT, tmp_path / "site")
        subgraph_path = tmp_path / "site" / "subgraphs" / "topics" / "algebra.json"

        assert subgraph_path.exists()
        subgraph = json.loads(subgraph_path.read_text())
        assert subgraph["topic"]["id"] == "algebra"
        assert {node["id"] for node in subgraph["nodes"]} >= {
            "algebra.group",
            "algebra.group_identity_unique",
        }
        assert all("body_html" not in node for node in subgraph["nodes"])

    def test_index_lists_all(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        content = (tmp_path / "site" / "index.html").read_text()
        assert "Strategic Game" in content
        assert "Nash Equilibrium" in content

    def test_status_badges(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        content = (tmp_path / "site" / "index.html").read_text()
        assert "status-admitted" in content

    def test_math_rendering_script(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        sg_page = (tmp_path / "site" / "strategic_games" / "strategic_games_strategic_game.html")
        content = sg_page.read_text()
        assert "katex.min.css" in content
        assert "katex.min.js" in content
        assert "auto-render.min.js" in content
        assert "renderMathInElement" in content
        assert "MathJax" not in content

    def test_staged_included(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        content = (tmp_path / "site" / "index.html").read_text()
        assert "mixed_strategy" in content

    def test_generates_leanblueprint_graph_page(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        site = tmp_path / "site"

        assert (site / "dep_graph_document.html").exists()
        assert (site / "graph.html").exists()
        assert (site / "graph.js").exists()

        graph_page = (site / "dep_graph_document.html").read_text()
        assert "Dependency graph" in graph_page
        assert "Legend" in graph_page
        assert "graph_topics.json" in graph_page
        assert "strict digraph" not in graph_page

    def test_graph_page_contains_node_modals(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        site = tmp_path / "site"
        graph_page = (site / "dep_graph_document.html").read_text()
        graph_js = (site / "graph.js").read_text()

        assert "dep-modal-container" in graph_page
        assert 'id="node-detail-modal"' in graph_page
        assert "If every player" not in graph_page
        assert "fetchNodePayload" in graph_js
        assert "nodePayloadCache" in graph_js
        assert "graph-error" in graph_js

    def test_publishes_lazy_node_detail_payloads(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        payload_path = tmp_path / "site" / "node_payloads" / "strategic_games_dominant_implies_nash.json"

        assert payload_path.exists()
        payload = json.loads(payload_path.read_text())
        assert payload["id"] == "strategic_games.dominant_implies_nash"
        assert payload["title"] == "Dominant Strategy Profile is a Nash Equilibrium"
        assert payload["href"] == "strategic_games/strategic_games_dominant_implies_nash.html"
        assert "If every player" in payload["body_html"]
        assert "A weakly dominant strategy weakly dominates every alternative" in payload["proof_html"]
        assert payload["deps"]
        assert payload["lean_refs"]

    def test_graph_page_uses_topic_overview_as_default_graph(self, tmp_path):
        publish(GENERIC_KNOWLEDGE_ROOT, tmp_path / "site")
        graph_page = (tmp_path / "site" / "dep_graph_document.html").read_text()
        graph_js = (tmp_path / "site" / "graph.js").read_text()

        assert 'id="graph-config"' in graph_page
        assert "graph_topics.json" in graph_page
        assert 'id="graph-dot"' not in graph_page
        assert "topicOverviewUrl" in graph_js
        assert "renderTopicOverview" in graph_js

    def test_graph_js_supports_topic_expand_collapse_state(self, tmp_path):
        publish(GENERIC_KNOWLEDGE_ROOT, tmp_path / "site")
        graph_page = (tmp_path / "site" / "dep_graph_document.html").read_text()
        graph_js = (tmp_path / "site" / "graph.js").read_text()

        assert 'id="graph-overview-button"' in graph_page
        assert 'id="graph-parent-button"' in graph_page
        assert 'id="graph-breadcrumbs"' in graph_page
        assert 'id="graph-reset-view-button"' in graph_page
        assert "topicSubgraphBaseUrl" in graph_page
        assert "graphState" in graph_js
        assert "expandedTopic" in graph_js
        assert "currentTopicLayer" in graph_js
        assert "fetchTopicSubgraph" in graph_js
        assert "topicLayerToDot" in graph_js
        assert "renderTopicLayer" in graph_js
        assert "goToParentTopic" in graph_js
        assert "updateGraphBreadcrumbs" in graph_js
        assert "topicSubgraphToDot" in graph_js
        assert "handleTopicActivation" in graph_js
        assert "goToTopicOverview" in graph_js
        assert "updateGraphNavigationControls" in graph_js
        assert "topicCache" in graph_js
        assert "expanded" in graph_js

    def test_topic_subgraph_includes_child_topics_field(self, tmp_path):
        from tools.knowledge.config import GraphDisplayConfig
        from tools.knowledge.export import export_topic_subgraph_json
        from tools.knowledge.graph import build_graph
        from tools.knowledge.models import Node

        parent = Node(id="game_theory.strategic", title="Strategic", kind="concept", status="admitted")
        child1 = Node(id="game_theory.strategic.nash.classic", title="Classic Nash", kind="theorem", status="admitted")
        child2 = Node(id="game_theory.strategic.nash.correlated", title="Correlated Equilibrium", kind="theorem", status="admitted")
        graph, diags = build_graph([parent, child1, child2])
        assert diags == []

        # Force boxed children (no inlining) so child_topics is populated.
        boxed_cfg = GraphDisplayConfig(
            max_visible_nodes=120,
            max_expand_nodes=80,
            proof_plans="selected-only",
            inline_child_max_size=0,
        )
        data = export_topic_subgraph_json(
            graph, "game_theory.strategic", graph_config=boxed_cfg
        )
        assert "child_topics" in data
        assert sorted(data["child_topics"]) == ["game_theory.strategic.nash"]

    def test_topic_subgraph_child_topics_empty_when_no_children(self, tmp_path):
        from tools.knowledge.export import export_topic_subgraph_json
        from tools.knowledge.graph import build_graph
        from tools.knowledge.models import Node

        base = Node(id="algebra.group", title="Group", kind="definition", status="admitted")
        theorem = Node(id="algebra.group_identity_unique", title="Group Identity Is Unique", kind="theorem", status="admitted")
        graph, diags = build_graph([base, theorem])
        assert diags == []

        data = export_topic_subgraph_json(graph, "algebra")
        assert "child_topics" in data
        assert data["child_topics"] == []

    def test_hierarchical_topic_ids_publish_nested_topic_and_node_paths(self, tmp_path):
        knowledge = tmp_path / "knowledge"
        node_dir = knowledge / "nodes" / "game_theory" / "strategic"
        node_dir.mkdir(parents=True)
        (knowledge / "mdblueprint.yml").write_text("site:\n  title: Hierarchy Fixture\n", encoding="utf-8")
        (node_dir / "nash.md").write_text(
            textwrap.dedent(
                """
                ---
                id: game_theory.strategic.nash
                title: Nash Equilibrium
                kind: theorem
                status: admitted
                uses: []
                ---

                # Nash Equilibrium
                """
            ).strip(),
            encoding="utf-8",
        )

        publish(knowledge, tmp_path / "site")
        site = tmp_path / "site"

        assert (site / "game_theory" / "index.html").exists()
        assert (site / "game_theory" / "strategic" / "index.html").exists()
        assert (site / "game_theory" / "strategic" / "game_theory_strategic_nash.html").exists()
        assert (site / "subgraphs" / "topics" / "game_theory.json").exists()
        assert (site / "subgraphs" / "topics" / "game_theory.strategic.json").exists()

        overview = json.loads((site / "graph_topics.json").read_text())
        assert overview["topics"][0]["id"] == "game_theory"
        assert overview["topics"][0]["children"] == ["game_theory.strategic"]

    def test_dot_label_uses_real_newlines_not_double_escaped_sequences(self, tmp_path):
        graph_js = (ROOT / "tools" / "knowledge" / "templates" / "graph.js").read_text()
        assert '${data.topic.title}\\nexpanded' not in graph_js
        assert 'topic.title}\\\\n' not in graph_js

    def test_publish_refuses_to_write_into_source_tree(self, tmp_path):
        from tools.knowledge.publish import publish

        knowledge = tmp_path / "knowledge"
        knowledge.mkdir()
        nodes_dir = knowledge / "nodes" / "algebra"
        nodes_dir.mkdir(parents=True)
        (knowledge / "mdblueprint.yml").write_text("site:\n  title: Test\n", encoding="utf-8")
        (nodes_dir / "group.md").write_text(
            "---\nid: algebra.group\ntitle: Group\nkind: definition\nstatus: admitted\n---\n# Group\n",
            encoding="utf-8",
        )
        inside_output = knowledge / "site"
        with pytest.raises(ValueError, match="inside the knowledge source tree"):
            publish(knowledge, inside_output)

    def test_graph_js_keeps_topic_labels_uncluttered(self):
        graph_js = (ROOT / "tools" / "knowledge" / "templates" / "graph.js").read_text()

        assert "topic.node_count" not in graph_js
        assert "renderCountLabel" not in graph_js
        assert 'label: edge.count' not in graph_js

    def test_graph_page_includes_pan_zoom_reset_controls(self, tmp_path):
        publish(GENERIC_KNOWLEDGE_ROOT, tmp_path / "site")
        graph_page = (tmp_path / "site" / "dep_graph_document.html").read_text()
        graph_js = (tmp_path / "site" / "graph.js").read_text()

        assert 'id="graph-reset-view-button"' in graph_page
        assert "installGraphPanZoom" in graph_js
        assert "resetGraphView" in graph_js
        assert ".zoom()" in graph_js
        assert "graph-pan-zoom-layer" in graph_js

    def test_graph_page_configures_expansion_limits_and_fallback(self, tmp_path):
        config_path = tmp_path / "mdblueprint.yml"
        config_path.write_text(
            textwrap.dedent(
                """
                site:
                  title: Limited Graph Blueprint
                  short_title: Limited
                graph:
                  max_visible_nodes: 3
                  max_expand_nodes: 1
                  proof_plans: hidden
                """
            ).strip(),
            encoding="utf-8",
        )

        publish(GENERIC_KNOWLEDGE_ROOT, tmp_path / "site", config_path=config_path)
        graph_page = (tmp_path / "site" / "dep_graph_document.html").read_text()
        graph_js = (tmp_path / "site" / "graph.js").read_text()
        graph_config = _graph_config_from_page(graph_page)

        assert graph_config["maxVisibleNodes"] == 3
        assert graph_config["maxExpandNodes"] == 1
        assert graph_config["proofPlans"] == "hidden"
        assert 'id="graph-fallback"' in graph_page
        assert "showOversizedTopicFallback" in graph_js
        assert "Keyword pages" in graph_js

    def test_graph_page_includes_proof_plan_visibility_control(self, tmp_path):
        publish(GENERIC_KNOWLEDGE_ROOT, tmp_path / "site")
        graph_page = (tmp_path / "site" / "dep_graph_document.html").read_text()
        graph_js = (tmp_path / "site" / "graph.js").read_text()

        assert 'id="proof-plan-controls"' in graph_page
        assert 'value="hidden"' in graph_page
        assert 'value="selected-only"' in graph_page
        assert 'value="all"' in graph_page
        assert "Hide proof plans" in graph_page
        assert "Show selected plans" in graph_page
        assert "Show all plans" in graph_page
        assert ">Hidden<" not in graph_page
        assert ">Selected<" not in graph_page
        assert ">All<" not in graph_page
        assert "setProofPlanMode" in graph_js
        assert 'node.plan_status === "selected"' in graph_js
        assert "proof_plan_attachments || []).filter" in graph_js
        assert "proof_plan_uses" in graph_js

    def test_graph_modal_contains_node_body(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        payload = json.loads(
            (tmp_path / "site" / "node_payloads" / "strategic_games_dominant_implies_nash.json").read_text()
        )

        assert "If every player" in payload["body_html"]
        assert "weakly dominant strategy" in payload["proof_html"]

    def test_graph_page_uses_graphviz_assets(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        graph_page = (tmp_path / "site" / "dep_graph_document.html").read_text()

        assert "d3-graphviz" in graph_page
        assert 'id="graph-config"' in graph_page
        assert 'id="graph"' in graph_page
        assert 'id="Legend"' in graph_page

    def test_graph_page_has_leanblueprint_legend_entries(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        graph_page = (tmp_path / "site" / "dep_graph_document.html").read_text()

        assert "Boxes" in graph_page
        assert "definitions" in graph_page
        assert "Ellipses" in graph_page
        assert "theorems and lemmas" in graph_page
        assert "Transparent background" in graph_page
        assert "Blue background" in graph_page
        assert "Green background" in graph_page

    def test_node_page_uses_theorem_wrapper(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "strategic_games" / "strategic_games_dominant_implies_nash.html").read_text()

        assert "theorem_thmwrapper" in page
        assert "theorem_thmcaption" in page
        assert "Dominant Strategy Profile is a Nash Equilibrium" in page
        assert "thm_header_hidden_extras" in page

    def test_definition_page_uses_definition_wrapper(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "strategic_games" / "strategic_games_strategic_game.html").read_text()

        assert "definition_thmwrapper" in page
        assert "definition_thmcaption" in page
        assert "Strategic Game" in page

    def test_node_page_has_uses_and_lean_modals(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "strategic_games" / "strategic_games_dominant_implies_nash.html").read_text()

        assert "Uses" in page
        assert "Lean declarations" in page
        assert "StrategicGame.IsNashEquilibrium.of_dominant" in page

    def test_index_links_to_dependency_graph_with_leanblueprint_name(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "index.html").read_text()

        assert "dep_graph_document.html" in page
        assert "Dependency graph" in page

    def test_topic_page_has_blueprint_summary_classes(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "strategic_games" / "index.html").read_text()

        assert "blueprint-node-list" in page
        assert "definition_thmcaption" in page

    def test_sidebar_groups_topics_and_keywords(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "index.html").read_text()

        assert "Topics" in page
        assert "Keywords" in page
        assert 'href="strategic_games/index.html"' in page
        assert 'href="keywords/foundational.html"' in page
        assert 'href="keywords/dominance.html"' in page
        assert 'href="keywords/equilibrium.html"' in page
        assert 'href="keywords/solution-concept.html"' in page

    def test_sidebar_dag_link_before_topics(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "index.html").read_text()
        dag_pos = page.find('dep_graph_document.html')
        topics_pos = page.find('nav-topics')
        assert dag_pos < topics_pos, "DAG link must appear before Topics section"

    def test_sidebar_dag_link_before_topics_on_nested_page(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "strategic_games" / "strategic_games_strategic_game.html").read_text()
        dag_pos = page.find('dep_graph_document.html')
        topics_pos = page.find('nav-topics')
        assert dag_pos < topics_pos, "DAG link must appear before Topics section on nested page"

    def test_sidebar_topic_fold_button_exists(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "index.html").read_text()
        assert 'sidebar-toggle' in page
        assert 'topic-list' in page
        assert 'aria-expanded' in page

    def test_sidebar_keyword_fold_button_exists(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "index.html").read_text()
        assert 'sidebar-toggle-keywords' in page
        assert 'keyword-list' in page

    def test_sidebar_topic_fold_on_topic_page(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "strategic_games" / "index.html").read_text()
        assert 'sidebar-toggle' in page
        assert 'topic-list' in page

    def test_sidebar_topic_fold_on_node_page(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "strategic_games" / "strategic_games_strategic_game.html").read_text()
        assert 'sidebar-toggle' in page
        assert 'topic-list' in page

    def test_no_js_topic_links_remain_accessible(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "index.html").read_text()
        assert 'href="strategic_games/index.html"' in page
        assert 'href="keywords/dominance.html"' in page

    def test_keyword_pages_list_matching_nodes_with_blueprint_summaries(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        site = tmp_path / "site"
        page = (site / "keywords" / "dominance.html").read_text()

        assert "Keyword: dominance" in page
        assert "blueprint-node-list" in page
        assert "Weak Dominance" in page
        assert "Strict Dominance" in page
        assert "Dominant Strategy Profile is a Nash Equilibrium" in page

    def test_theorem_proof_is_collapsed_on_node_page(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "strategic_games" / "strategic_games_dominant_implies_nash.html").read_text()

        assert '<details class="proof-details">' in page
        assert "<summary>Proof</summary>" in page
        assert "If every player" in page
        assert "A weakly dominant strategy weakly dominates every alternative" in page

    def test_definition_without_proof_has_no_empty_proof_disclosure(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "strategic_games" / "strategic_games_strategic_game.html").read_text()

        assert "proof-details" not in page

    def test_graph_modal_proofs_are_collapsed(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        page = json.loads(
            (tmp_path / "site" / "node_payloads" / "strategic_games_dominant_implies_nash.json").read_text()
        )

        assert page["proof_html"]

    def test_graph_dot_uses_titles_as_visible_labels(self, tmp_path):
        publish(GENERIC_KNOWLEDGE_ROOT, tmp_path / "site")
        overview = json.loads((tmp_path / "site" / "graph_topics.json").read_text())

        assert overview["topics"][0]["title"] == "Algebra"
        assert overview["topics"][0]["node_count"] == 5

    def test_graph_js_hides_internal_ids_after_render(self):
        script = (ROOT / "tools" / "knowledge" / "templates" / "graph.js").read_text()

        assert "dataset.graphNodeId" in script
        assert "titleElement.textContent = visibleLabel" in script

    def test_blueprint_views_do_not_show_slug_as_primary_label(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        node_page = (tmp_path / "site" / "strategic_games" / "strategic_games_dominant_implies_nash.html").read_text()
        topic_page = (tmp_path / "site" / "strategic_games" / "index.html").read_text()

        assert "theorem_thmlabel" not in node_page
        assert "node-id" not in node_page
        assert "theorem_thmlabel" not in topic_page

    def test_index_uses_hierarchical_title_outline_not_id_table(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "index.html").read_text()

        assert "blueprint-index-outline" in page
        assert "<table" not in page
        assert "Strategic Games" in page
        assert "Dominant Strategy Profile is a Nash Equilibrium" in page
        assert "strategic_games.dominant_implies_nash" not in page


class TestGenericPublish:
    def test_generic_fixture_generates_site_without_example_corpus_terms(self, tmp_path):
        publish(GENERIC_KNOWLEDGE_ROOT, tmp_path / "site")
        site = tmp_path / "site"

        assert (site / "index.html").exists()
        assert (site / "algebra" / "index.html").exists()
        assert (site / "algebra" / "algebra_group.html").exists()
        assert (site / "keywords" / "algebra.html").exists()
        assert (site / "dep_graph_document.html").exists()

        index = (site / "index.html").read_text()
        assert "Group" in index
        assert "Group Homomorphism" in index
        assert "Group Identity Is Unique" in index
        example_topic = "strategic" + "_games"
        example_label = "Na" + "sh"
        assert example_topic not in index
        assert example_label not in index

    def test_generic_fixture_keeps_theorem_proofs_collapsed(self, tmp_path):
        publish(GENERIC_KNOWLEDGE_ROOT, tmp_path / "site")
        theorem_page = (tmp_path / "site" / "algebra" / "algebra_group_identity_unique.html").read_text()
        graph_topics = json.loads((tmp_path / "site" / "graph_topics.json").read_text())

        assert '<details class="proof-details">' in theorem_page
        assert "<summary>Proof</summary>" in theorem_page
        assert graph_topics["topics"][0]["title"] == "Algebra"

    def test_tex_math_is_preserved_before_katex_on_node_and_graph_pages(self, tmp_path):
        knowledge = tmp_path / "knowledge"
        node_dir = knowledge / "nodes" / "games"
        node_dir.mkdir(parents=True)
        (node_dir / "strategic_game.md").write_text(
            textwrap.dedent(
                r"""
                ---
                id: games.strategic_game
                title: Strategic Game
                kind: definition
                status: admitted
                uses: []
                tags:
                  - games
                ---

                # Strategic Game

                A strategic game is a tuple
                $(I, (S_i)_{i \in I}, (u_i)_{i \in I})$.
                It can also be written as
                \((I, (S_i)_{i \in I}, (u_i)_{i \in I})\).
                """
            ).strip()
        )

        publish(knowledge, tmp_path / "site")
        node_page = (tmp_path / "site" / "games" / "games_strategic_game.html").read_text()
        graph_payload = json.loads(
            (tmp_path / "site" / "node_payloads" / "games_strategic_game.json").read_text()
        )

        assert r"$(I, (S_i)_{i \in I}, (u_i)_{i \in I})$" in node_page
        assert r"\((I, (S_i)_{i \in I}, (u_i)_{i \in I})\)" in node_page
        assert r"$(I, (S_i)_{i \in I}, (u_i)_{i \in I})$" in graph_payload["body_html"]
        assert r"\((I, (S_i)_{i \in I}, (u_i)_{i \in I})\)" in graph_payload["body_html"]
        assert "<em>" not in node_page
        assert "<em>" not in graph_payload["body_html"]


class TestBuildTopicTree:
    """Tests for Issue #81: hierarchical sidebar topic tree."""

    def _tree(self, names):
        from tools.knowledge.publish import _build_topic_tree
        return _build_topic_tree(names)

    def test_flat_topics_become_roots(self):
        tree = self._tree(["algebra", "logic"])
        assert [n["id"] for n in tree] == ["algebra", "logic"]
        assert tree[0]["children"] == []

    def test_nested_topics_become_children(self):
        tree = self._tree(["algebra", "algebra.group", "algebra.ring", "logic"])
        assert len(tree) == 2
        algebra = tree[0]
        assert algebra["id"] == "algebra"
        assert [c["id"] for c in algebra["children"]] == ["algebra.group", "algebra.ring"]
        assert tree[1]["id"] == "logic"

    def test_three_level_hierarchy(self):
        tree = self._tree(["a", "a.b", "a.b.c"])
        assert tree[0]["id"] == "a"
        assert tree[0]["children"][0]["id"] == "a.b"
        assert tree[0]["children"][0]["children"][0]["id"] == "a.b.c"

    def test_label_is_last_segment_titleized(self):
        tree = self._tree(["mechanism_design", "mechanism_design.basic"])
        assert tree[0]["label"] == "Mechanism Design"
        assert tree[0]["children"][0]["label"] == "Basic"

    def test_sidebar_html_contains_nested_structure(self, tmp_path):
        from tools.knowledge.publish import publish

        knowledge = tmp_path / "knowledge"
        nodes_dir = knowledge / "nodes" / "algebra" / "group"
        nodes_dir.mkdir(parents=True)
        (knowledge / "mdblueprint.yml").write_text(
            "site:\n  title: Test\n  base_url: http://localhost\n"
        )
        (nodes_dir / "group.md").write_text(
            "---\nid: algebra.group.definition\ntitle: Group\nkind: definition\n"
            "status: admitted\n---\n\n# Group\n\nA group is a set.\n"
        )
        publish(knowledge, tmp_path / "site")
        sidebar = (tmp_path / "site" / "algebra" / "group" / "index.html").read_text()
        assert "details" in sidebar
        assert "algebra" in sidebar.lower()

    def test_active_topic_details_is_open(self, tmp_path):
        from tools.knowledge.publish import publish

        knowledge = tmp_path / "knowledge"
        nodes_dir = knowledge / "nodes" / "algebra" / "group"
        nodes_dir.mkdir(parents=True)
        other_dir = knowledge / "nodes" / "logic"
        other_dir.mkdir(parents=True)
        (knowledge / "mdblueprint.yml").write_text(
            "site:\n  title: Test\n  base_url: http://localhost\n"
        )
        (nodes_dir / "group.md").write_text(
            "---\nid: algebra.group.def\ntitle: Group\nkind: definition\n"
            "status: admitted\n---\n\n# Group\n\nA group.\n"
        )
        (other_dir / "truth.md").write_text(
            "---\nid: logic.truth\ntitle: Truth\nkind: lemma\n"
            "status: admitted\n---\n\n# Truth\n\nTrue.\n"
        )
        publish(knowledge, tmp_path / "site")
        page = (tmp_path / "site" / "algebra" / "group" / "index.html").read_text()
        assert "details" in page
        assert "open" in page

    def test_sidebar_child_topic_css_removes_nested_bullets(self):
        css = (ROOT / "tools" / "knowledge" / "templates" / "style.css").read_text()

        assert ".topic-children" in css
        assert "list-style: none" in css
        assert ".topic-children li::marker" in css
        assert "display: none" in css


class TestMultiTopicPublish:
    """Tests for Issue #79: multi-topic publisher views."""

    def _make_knowledge(self, tmp_path):
        knowledge = tmp_path / "knowledge"
        nodes_dir = knowledge / "nodes" / "algebra" / "groups"
        monoids_dir = knowledge / "nodes" / "algebra" / "monoids"
        nodes_dir.mkdir(parents=True)
        monoids_dir.mkdir(parents=True)
        (knowledge / "mdblueprint.yml").write_text("site:\n  title: Multi-Topic Test\n")
        # Node that belongs to both algebra.groups and algebra.monoids
        (nodes_dir / "cayley.md").write_text(
            "---\n"
            "id: algebra.groups.cayley\n"
            "title: Cayley's Theorem\n"
            "kind: theorem\n"
            "status: admitted\n"
            "primary_topic: algebra.groups\n"
            "topics:\n"
            "  - algebra.groups\n"
            "  - algebra.monoids\n"
            "---\n\n# Cayley's Theorem\n\nEvery group is isomorphic to a subgroup of a symmetric group.\n"
        )
        # Node only in algebra.monoids
        (monoids_dir / "identity.md").write_text(
            "---\n"
            "id: algebra.monoids.identity\n"
            "title: Monoid Identity\n"
            "kind: definition\n"
            "status: admitted\n"
            "---\n\n# Monoid Identity\n\nA monoid has a unique identity element.\n"
        )
        return knowledge

    def test_multi_topic_node_appears_on_both_topic_pages(self, tmp_path):
        knowledge = self._make_knowledge(tmp_path)
        publish(knowledge, tmp_path / "site")
        groups_page = (tmp_path / "site" / "algebra" / "groups" / "index.html").read_text()
        monoids_page = (tmp_path / "site" / "algebra" / "monoids" / "index.html").read_text()
        assert "Cayley" in groups_page
        assert "Cayley" in monoids_page

    def test_multi_topic_node_has_one_canonical_html_file(self, tmp_path):
        knowledge = self._make_knowledge(tmp_path)
        publish(knowledge, tmp_path / "site")
        # Node page is written once at its ID-derived topic directory
        canonical = tmp_path / "site" / "algebra" / "groups" / "algebra_groups_cayley.html"
        assert canonical.exists()
        # No duplicate in monoids
        duplicate = tmp_path / "site" / "algebra" / "monoids" / "algebra_groups_cayley.html"
        assert not duplicate.exists()

    def test_multi_topic_node_link_from_monoids_page_resolves_to_canonical(self, tmp_path):
        knowledge = self._make_knowledge(tmp_path)
        publish(knowledge, tmp_path / "site")
        monoids_page = (tmp_path / "site" / "algebra" / "monoids" / "index.html").read_text()
        # Link from monoids page must point to the canonical algebra/groups page
        assert "algebra_groups_cayley" in monoids_page

    def test_single_topic_node_not_duplicated_on_ancestor_page(self, tmp_path):
        knowledge = self._make_knowledge(tmp_path)
        publish(knowledge, tmp_path / "site")
        algebra_page = (tmp_path / "site" / "algebra" / "index.html").read_text()
        # Cayley appears once (deduplicated) on the ancestor algebra page
        assert algebra_page.count("Cayley") == 1

    def test_global_unique_node_count_not_inflated(self, tmp_path):
        knowledge = self._make_knowledge(tmp_path)
        publish(knowledge, tmp_path / "site")
        import json
        graph = json.loads((tmp_path / "site" / "graph.json").read_text())
        # 2 unique nodes, not 3 (cayley should not be double-counted)
        assert len(graph["nodes"]) == 2

    def test_node_page_shows_all_topic_memberships_when_multi_topic(self, tmp_path):
        knowledge = self._make_knowledge(tmp_path)
        publish(knowledge, tmp_path / "site")
        page = (tmp_path / "site" / "algebra" / "groups" / "algebra_groups_cayley.html").read_text()
        # "Also in" section with both topics linked
        assert "Also in" in page
        assert "algebra/groups" in page
        assert "algebra/monoids" in page

    def test_node_page_no_also_in_section_when_single_topic(self, tmp_path):
        knowledge = self._make_knowledge(tmp_path)
        publish(knowledge, tmp_path / "site")
        page = (tmp_path / "site" / "algebra" / "monoids" / "algebra_monoids_identity.html").read_text()
        assert "Also in" not in page

    def test_primary_topic_controls_canonical_page_and_payload_links(self, tmp_path):
        knowledge = tmp_path / "knowledge"
        nodes_dir = knowledge / "nodes" / "legacy"
        nodes_dir.mkdir(parents=True)
        (knowledge / "mdblueprint.yml").write_text("site:\n  title: Primary Topic Test\n")
        (nodes_dir / "duality.md").write_text(
            "---\n"
            "id: legacy.duality\n"
            "title: Duality\n"
            "kind: theorem\n"
            "status: admitted\n"
            "primary_topic: linear_programming.duality\n"
            "topics:\n"
            "  - linear_programming.duality\n"
            "---\n\n"
            "# Duality\n",
            encoding="utf-8",
        )
        (nodes_dir / "minimax.md").write_text(
            "---\n"
            "id: legacy.minimax\n"
            "title: Minimax\n"
            "kind: theorem\n"
            "status: admitted\n"
            "primary_topic: game_theory.zero_sum\n"
            "topics:\n"
            "  - game_theory.zero_sum\n"
            "uses:\n"
            "  - legacy.duality\n"
            "---\n\n"
            "# Minimax\n",
            encoding="utf-8",
        )

        publish(knowledge, tmp_path / "site")
        site = tmp_path / "site"

        assert (site / "game_theory" / "zero_sum" / "legacy_minimax.html").exists()
        assert not (site / "legacy" / "legacy_minimax.html").exists()

        zero_sum_page = (site / "game_theory" / "zero_sum" / "index.html").read_text()
        assert "legacy_minimax.html" in zero_sum_page

        payload = json.loads((site / "node_payloads" / "legacy_minimax.json").read_text())
        assert payload["href"] == "game_theory/zero_sum/legacy_minimax.html"
        assert payload["deps"] == [
            {
                "id": "legacy.duality",
                "title": "Duality",
                "href": "linear_programming/duality/legacy_duality.html",
            }
        ]


class TestTopicCatalogPages:
    """Tests for Issue #82: topic catalog content on topic index pages."""

    def _make_knowledge(self, tmp_path):
        knowledge = tmp_path / "knowledge"
        nodes_dir = knowledge / "nodes" / "algebra"
        nodes_dir.mkdir(parents=True)
        (knowledge / "mdblueprint.yml").write_text("site:\n  title: Catalog Test\n")
        (nodes_dir / "group.md").write_text(
            "---\nid: algebra.group\ntitle: Group\nkind: definition\nstatus: admitted\n---\n\n# Group\n\nA group.\n"
        )
        (nodes_dir / "ring.md").write_text(
            "---\nid: algebra.ring\ntitle: Ring\nkind: definition\nstatus: admitted\n---\n\n# Ring\n\nA ring.\n"
        )
        return knowledge

    def test_topic_page_with_catalog_shows_intro_text(self, tmp_path):
        knowledge = self._make_knowledge(tmp_path)
        (knowledge / "nodes" / "algebra" / "topics.md").write_text(
            "This topic covers abstract algebra, including groups and rings.\n"
        )
        publish(knowledge, tmp_path / "site")
        page = (tmp_path / "site" / "algebra" / "index.html").read_text()
        assert "abstract algebra" in page
        assert "groups and rings" in page

    def test_topic_page_without_catalog_shows_node_count(self, tmp_path):
        knowledge = self._make_knowledge(tmp_path)
        publish(knowledge, tmp_path / "site")
        page = (tmp_path / "site" / "algebra" / "index.html").read_text()
        assert "2 nodes" in page

    def test_topic_page_shows_status_counts(self, tmp_path):
        knowledge = self._make_knowledge(tmp_path)
        publish(knowledge, tmp_path / "site")
        page = (tmp_path / "site" / "algebra" / "index.html").read_text()
        assert "admitted" in page

    def test_topic_page_shows_child_topics(self, tmp_path):
        knowledge = tmp_path / "knowledge"
        root_dir = knowledge / "nodes" / "algebra"
        sub_dir = knowledge / "nodes" / "algebra" / "groups"
        sub_dir.mkdir(parents=True)
        (knowledge / "mdblueprint.yml").write_text("site:\n  title: Child Topics Test\n")
        (root_dir / "ring.md").write_text(
            "---\nid: algebra.ring\ntitle: Ring\nkind: definition\nstatus: admitted\n---\n\n# Ring\n"
        )
        (sub_dir / "group.md").write_text(
            "---\nid: algebra.groups.group\ntitle: Group\nkind: definition\nstatus: admitted\n---\n\n# Group\n"
        )
        publish(knowledge, tmp_path / "site")
        page = (tmp_path / "site" / "algebra" / "index.html").read_text()
        assert "Subtopics" in page
        assert "algebra/groups" in page

    def test_topic_page_without_child_topics_shows_no_subtopics_section(self, tmp_path):
        knowledge = self._make_knowledge(tmp_path)
        publish(knowledge, tmp_path / "site")
        page = (tmp_path / "site" / "algebra" / "index.html").read_text()
        assert "Subtopics" not in page

    def test_topic_kind_node_page_lists_child_topics_as_links(self, tmp_path):
        knowledge = tmp_path / "knowledge"
        root_dir = knowledge / "nodes" / "lattice" / "support"
        sub_dir = knowledge / "nodes" / "lattice" / "support" / "distributive"
        sub_dir.mkdir(parents=True)
        (knowledge / "mdblueprint.yml").write_text("site:\n  title: Subtopics Node Test\n")
        (root_dir / "support.md").write_text(
            "---\nid: lattice.support\ntitle: Lattice Support\nkind: topic\n"
            "status: admitted\nprimary_topic: lattice.support\n---\n\n"
            "# Lattice Support\n\nRoadmap node.\n"
        )
        (sub_dir / "join.md").write_text(
            "---\nid: lattice.support.distributive.join\ntitle: Join\nkind: definition\n"
            "status: admitted\n---\n\n# Join\n"
        )
        publish(knowledge, tmp_path / "site")
        node_page = (
            tmp_path / "site" / "lattice" / "support" / "lattice_support.html"
        ).read_text()
        assert "Subtopics" in node_page
        assert 'href="../../lattice/support/distributive/index.html"' in node_page

    def test_non_topic_node_page_has_no_subtopics_section(self, tmp_path):
        knowledge = self._make_knowledge(tmp_path)
        publish(knowledge, tmp_path / "site")
        node_page = (
            tmp_path / "site" / "algebra" / "algebra_group.html"
        ).read_text()
        assert "Subtopics" not in node_page

    def test_malformed_topics_md_frontmatter_stripped(self, tmp_path):
        knowledge = self._make_knowledge(tmp_path)
        (knowledge / "nodes" / "algebra" / "topics.md").write_text(
            "---\ntitle: Algebra Catalog\n---\n\nAlgebra covers structures with operations.\n"
        )
        publish(knowledge, tmp_path / "site")
        page = (tmp_path / "site" / "algebra" / "index.html").read_text()
        assert "Algebra covers structures" in page
        # Frontmatter should not appear verbatim
        assert "title: Algebra Catalog" not in page

    def test_missing_topics_md_does_not_break_publishing(self, tmp_path):
        knowledge = self._make_knowledge(tmp_path)
        # No topics.md — should publish cleanly
        publish(knowledge, tmp_path / "site")
        assert (tmp_path / "site" / "algebra" / "index.html").exists()


NODE_REFS_ROOT = Path(__file__).parent / "fixtures" / "node_refs_knowledge"


class TestNodeReferenceRendering:
    """HTML-level tests for [[node:id]] rendering in published pages."""

    def test_resolved_ref_renders_as_link_in_statement(self, tmp_path):
        publish(NODE_REFS_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "refs_a" / "refs_a_statement_ref.html").read_text()
        assert 'class="node-ref"' in page
        assert 'data-node-id="refs_a.target"' in page
        assert "<a " in page

    def test_resolved_ref_link_is_clickable_not_span(self, tmp_path):
        publish(NODE_REFS_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "refs_a" / "refs_a_statement_ref.html").read_text()
        assert '<a class="node-ref"' in page

    def test_resolved_ref_custom_label(self, tmp_path):
        publish(NODE_REFS_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "refs_a" / "refs_a_statement_ref.html").read_text()
        assert "the target lemma" in page

    def test_resolved_ref_in_proof_section(self, tmp_path):
        publish(NODE_REFS_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "refs_a" / "refs_a_statement_ref.html").read_text()
        proof_start = page.find("proof-details")
        assert proof_start != -1
        proof_section = page[proof_start:]
        assert 'class="node-ref"' in proof_section

    def test_unresolved_ref_renders_as_span(self, tmp_path):
        publish(NODE_REFS_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "refs_a" / "refs_a_unresolved_ref.html").read_text()
        assert 'class="node-ref unresolved"' in page
        assert 'data-node-id="refs_a.does_not_exist"' in page

    def test_nested_topic_href_is_relative_and_correct(self, tmp_path):
        publish(NODE_REFS_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "refs_b" / "sub" / "refs_b_sub_theorem.html").read_text()
        # From refs_b/sub/ to refs_a/refs_a_target.html: go up 2 dirs then into refs_a/
        assert 'href="../../refs_a/refs_a_target.html"' in page

    def test_node_ref_title_is_target_title(self, tmp_path):
        publish(NODE_REFS_ROOT, tmp_path / "site")
        page = (tmp_path / "site" / "refs_a" / "refs_a_statement_ref.html").read_text()
        assert "Target Lemma" in page

    def test_no_raw_shortcode_in_output(self, tmp_path):
        publish(NODE_REFS_ROOT, tmp_path / "site")
        for html_file in (tmp_path / "site").rglob("*.html"):
            content = html_file.read_text()
            assert "[[node:" not in content, f"Raw shortcode found in {html_file}"
