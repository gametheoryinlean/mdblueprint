"""In-memory snapshot of the parsed knowledge base.

Used by the static publisher and the local dev server. The class is a frozen
view: rebuild by calling `KnowledgeContext.load(...)` again — do not mutate.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment

from tools.knowledge.blueprint_view import build_blueprint_graph
from tools.knowledge.config import ProjectConfig, load_project_config
from tools.knowledge.export import (
    home_topic_for_node,
    leaf_topic_ids_for_node,
    topic_prefixes,
)
from tools.knowledge.graph import KnowledgeGraph, build_graph
from tools.knowledge.lean_index import LeanIndex
from tools.knowledge.models import Node
from tools.knowledge.parser import scan_directory


@dataclass
class KnowledgeContext:
    knowledge_root: Path
    config: ProjectConfig
    all_nodes: list[Node]
    nodes_by_id: dict[str, Node]
    filename_to_node_id: dict[str, str]
    graph: KnowledgeGraph
    blueprint_nodes: dict
    topics: dict[str, list[Node]]
    topic_names: list[str]
    topic_tree: list[dict]
    child_topics_map: dict[str, list[str]]
    keywords: dict[str, list[Node]]
    keyword_names: list[str]
    lean_indexes: dict[str, LeanIndex]
    jinja_env: Environment
    dev_mode: bool = False

    @classmethod
    def load(
        cls,
        knowledge_root: Path,
        *,
        lean: bool = False,
        dev_mode: bool = False,
        config_path: Path | None = None,
    ) -> "KnowledgeContext":
        from tools.knowledge.renderer import (
            _build_topic_tree,
            _index_configured_lean_repositories,
            build_jinja_env,
        )

        config = load_project_config(knowledge_root, config_path)

        all_nodes: list[Node] = []
        for subdir in ("nodes", "staged"):
            d = knowledge_root / subdir
            if d.exists():
                all_nodes.extend(scan_directory(d))

        nodes_by_id = {n.id: n for n in all_nodes}
        filename_to_node_id = {n.id.replace(".", "_"): n.id for n in all_nodes}

        lean_indexes = (
            _index_configured_lean_repositories(all_nodes, config.lean)
            if lean
            else {}
        )

        g, _ = build_graph(all_nodes)
        blueprint_graph = build_blueprint_graph(g)
        blueprint_nodes = {view.id: view for view in blueprint_graph.nodes}

        seen_per_topic: dict[str, set[str]] = defaultdict(set)
        topics: dict[str, list[Node]] = defaultdict(list)
        for node in all_nodes:
            for leaf in leaf_topic_ids_for_node(node):
                for t in topic_prefixes(leaf):
                    if node.id not in seen_per_topic[t]:
                        seen_per_topic[t].add(node.id)
                        topics[t].append(node)

        topic_names = sorted(topics.keys())

        child_topics_map: dict[str, list[str]] = {}
        for t in topic_names:
            depth = len(t.split("."))
            child_topics_map[t] = [
                other
                for other in topic_names
                if other.startswith(t + ".") and len(other.split(".")) == depth + 1
            ]

        keywords: dict[str, list[Node]] = defaultdict(list)
        for node in all_nodes:
            for tag in node.tags:
                keywords[tag].append(node)

        return cls(
            knowledge_root=knowledge_root,
            config=config,
            all_nodes=all_nodes,
            nodes_by_id=nodes_by_id,
            filename_to_node_id=filename_to_node_id,
            graph=g,
            blueprint_nodes=blueprint_nodes,
            topics=dict(topics),
            topic_names=topic_names,
            topic_tree=_build_topic_tree(topic_names),
            child_topics_map=child_topics_map,
            keywords=dict(keywords),
            keyword_names=sorted(keywords.keys()),
            lean_indexes=lean_indexes,
            jinja_env=build_jinja_env(config),
            dev_mode=dev_mode,
        )
