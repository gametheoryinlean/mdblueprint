from pathlib import Path

import pytest

from tools.knowledge.context import KnowledgeContext

KNOWLEDGE_ROOT = Path(__file__).parent.parent / "docs" / "knowledge"
GENERIC_KNOWLEDGE_ROOT = Path(__file__).parent / "fixtures" / "generic_knowledge"


class TestLoadHappyPath:
    def test_loads_real_knowledge_base(self):
        ctx = KnowledgeContext.load(KNOWLEDGE_ROOT)
        assert len(ctx.all_nodes) >= 10
        assert "strategic_games.nash_equilibrium" in ctx.nodes_by_id
        assert "strategic_games" in ctx.topic_names

    def test_filename_to_node_id_round_trip(self):
        ctx = KnowledgeContext.load(KNOWLEDGE_ROOT)
        node_id = "strategic_games.nash_equilibrium"
        filename = node_id.replace(".", "_")
        assert ctx.filename_to_node_id[filename] == node_id

    def test_jinja_env_is_configured(self):
        ctx = KnowledgeContext.load(KNOWLEDGE_ROOT)
        assert ctx.jinja_env is not None
        assert "topic_path" in ctx.jinja_env.globals
        assert "node_href_from_root" in ctx.jinja_env.globals
        assert "titleize" in ctx.jinja_env.filters

    def test_no_duplicate_in_topic_lists(self):
        ctx = KnowledgeContext.load(KNOWLEDGE_ROOT)
        for topic_id, nodes in ctx.topics.items():
            ids = [n.id for n in nodes]
            assert len(ids) == len(set(ids)), (
                f"duplicate node in topic {topic_id}: {ids}"
            )


class TestBoundaryConditions:
    def test_missing_knowledge_root_uses_fallback(self, tmp_path):
        ctx = KnowledgeContext.load(tmp_path / "nonexistent")
        assert ctx.config is not None
        assert ctx.all_nodes == []

    def test_missing_mdblueprint_yml(self, tmp_path):
        nodes = tmp_path / "nodes"
        nodes.mkdir(parents=True)
        (nodes / "test.md").write_text(
            "---\nid: test.node\ntitle: Test Node\nkind: concept\nstatus: admitted\n---\nTest body"
        )
        ctx = KnowledgeContext.load(tmp_path)
        assert len(ctx.all_nodes) == 1
        assert ctx.config.site.title != ""

    def test_lean_false_gives_empty_indexes(self):
        ctx = KnowledgeContext.load(KNOWLEDGE_ROOT, lean=False)
        assert ctx.lean_indexes == {}

    def test_lean_true_without_repos_gives_empty_indexes(self):
        ctx = KnowledgeContext.load(GENERIC_KNOWLEDGE_ROOT, lean=True)
        assert ctx.lean_indexes == {}

    def test_dev_mode_true(self):
        ctx = KnowledgeContext.load(KNOWLEDGE_ROOT, dev_mode=True)
        assert ctx.dev_mode is True

    def test_two_loads_are_independent(self):
        ctx1 = KnowledgeContext.load(KNOWLEDGE_ROOT)
        ctx2 = KnowledgeContext.load(KNOWLEDGE_ROOT)
        ctx1.topics["new_topic"] = []
        assert "new_topic" not in ctx2.topics

    def test_nodes_by_id_size_matches_unique_ids(self):
        ctx = KnowledgeContext.load(KNOWLEDGE_ROOT)
        unique_ids = {n.id for n in ctx.all_nodes}
        assert len(ctx.nodes_by_id) == len(unique_ids)

    def test_child_topics_map_is_one_level_deep(self):
        ctx = KnowledgeContext.load(KNOWLEDGE_ROOT)
        for parent, children in ctx.child_topics_map.items():
            parent_depth = parent.count(".")
            for child in children:
                assert child.count(".") == parent_depth + 1
