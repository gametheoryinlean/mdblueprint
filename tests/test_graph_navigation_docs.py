from pathlib import Path


ROOT = Path(__file__).parent.parent


def test_readme_documents_topic_first_graph_artifacts():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "topic-first" in readme
    assert "graph_topics.json" in readme
    assert "subgraphs/topics/<topic>.json" in readme
    assert "node_payloads/<node>.json" in readme
    assert "graph.json` remains the full machine graph" in readme


def test_publisher_docs_define_topic_edges_and_subgraphs():
    docs = (ROOT / "docs" / "publisher-and-dag.md").read_text(encoding="utf-8")

    assert "A topic overview edge is displayed from a dependency topic to a dependent topic" in docs
    assert "boundary topic node" in docs
    assert "`dependency -> dependent`" in docs
    assert "Proof-plan route dependencies are omitted from the topic overview" in docs
    assert "`graph.json` remains the full machine graph" in docs
    assert "lazy node detail payload" in docs


def test_docs_define_real_library_gate_contract():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "publisher-and-dag.md").read_text(encoding="utf-8")
    combined = readme + "\n" + docs

    assert "tools.knowledge.econcslib_gate" in combined
    assert "--render-mode smoke" in combined
    assert "current mdblueprint checkout" in combined
    assert "exact source commit" in combined
    assert "graph_topics.json" in combined
    assert "subgraphs/topics/*.json" in combined
    assert "blocking external-data issue" in combined


def test_reference_docs_include_domain_specific_topic_example():
    docs = (ROOT / "docs" / "reference-repos.md").read_text(encoding="utf-8")

    assert "strategic_games" in docs
    assert "Nash equilibrium" in docs
    assert "game-theory example is illustrative only" in docs
