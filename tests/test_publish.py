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
        assert 'id="graph-reset-view-button"' in graph_page
        assert "topicSubgraphBaseUrl" in graph_page
        assert "graphState" in graph_js
        assert "expandedTopic" in graph_js
        assert "fetchTopicSubgraph" in graph_js
        assert "topicSubgraphToDot" in graph_js
        assert "handleTopicActivation" in graph_js
        assert "goToTopicOverview" in graph_js
        assert "updateGraphNavigationControls" in graph_js
        assert "topicCache" in graph_js
        assert "expanded" in graph_js

    def test_topic_subgraph_includes_child_topics_field(self, tmp_path):
        from tools.knowledge.export import export_topic_subgraph_json
        from tools.knowledge.graph import build_graph
        from tools.knowledge.models import Node

        parent = Node(id="game_theory.strategic", title="Strategic", kind="concept", status="admitted")
        child1 = Node(id="game_theory.strategic.nash.classic", title="Classic Nash", kind="theorem", status="admitted")
        child2 = Node(id="game_theory.strategic.nash.correlated", title="Correlated Equilibrium", kind="theorem", status="admitted")
        graph, diags = build_graph([parent, child1, child2])
        assert diags == []

        data = export_topic_subgraph_json(graph, "game_theory.strategic")
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
        assert "Blue border" in graph_page
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
