from tools.knowledge.blueprint_view import (
    build_blueprint_graph,
    display_label,
    dot_quote,
    graph_to_dot,
    html_id,
    kind_caption,
    node_shape,
)
from tools.knowledge.graph import build_graph
from tools.knowledge.models import Node, Verification


def test_kind_caption_and_shape():
    assert kind_caption("definition") == "Definition"
    assert kind_caption("theorem") == "Theorem"
    assert node_shape("definition") == "box"
    assert node_shape("theorem") == "ellipse"
    assert node_shape("example") == "note"


def test_display_label_uses_last_id_component():
    assert display_label("strategic_games.dominant_implies_nash") == "dominant_implies_nash"


def test_html_id_is_stable_and_selector_safe():
    assert html_id("strategic_games.dominant_implies_nash") == "node-strategic_games-2e-dominant_implies_nash"


def test_html_id_distinguishes_different_punctuation():
    assert html_id("topic.a-b") != html_id("topic.a.b")


def test_dot_quote_escapes_quotes_backslashes_and_newlines():
    assert dot_quote('a "quoted" \\ value\nnext') == '"a \\"quoted\\" \\\\ value\\nnext"'


def test_dependency_edges_are_reversed_for_display():
    base = Node(id="t.base", title="Base", kind="definition", status="admitted")
    thm = Node(id="t.thm", title="Theorem", kind="theorem", status="admitted", uses=["t.base"])
    graph, diags = build_graph([base, thm])
    assert diags == []

    view = build_blueprint_graph(graph)

    assert view.edges == [("t.base", "t.thm")]


def test_formalization_status_mapping():
    base = Node(
        id="t.base",
        title="Base",
        kind="definition",
        status="formalized",
        verification=Verification(definition="accepted", proof="not_applicable", alignment="aligned"),
    )
    thm = Node(
        id="t.thm",
        title="Theorem",
        kind="theorem",
        status="proved",
        uses=["t.base"],
        verification=Verification(statement="accepted", proof="accepted", alignment="aligned"),
    )
    graph, diags = build_graph([base, thm])
    assert diags == []

    view = build_blueprint_graph(graph)
    by_id = {node.id: node for node in view.nodes}

    assert by_id["t.base"].border_state == "stated"
    assert by_id["t.base"].fill_state == "defined"
    assert by_id["t.thm"].border_state == "stated"
    assert by_id["t.thm"].fill_state == "fully_proved"


def test_proved_node_with_unproved_ancestor_is_not_fully_proved():
    base = Node(id="t.base", title="Base", kind="theorem", status="admitted")
    thm = Node(id="t.thm", title="Theorem", kind="theorem", status="proved", uses=["t.base"])
    graph, diags = build_graph([base, thm])
    assert diags == []

    view = build_blueprint_graph(graph)
    by_id = {node.id: node for node in view.nodes}

    assert by_id["t.thm"].fill_state == "proved"


def test_staged_node_is_not_ready():
    staged = Node(id="t.future", title="Future", kind="definition", status="staged")
    graph, diags = build_graph([staged])
    assert diags == []

    view = build_blueprint_graph(graph)

    assert view.nodes[0].border_state == "not_ready"
    assert view.nodes[0].fill_state is None


def test_graph_to_dot_is_deterministic_and_uses_reversed_edges():
    base = Node(id="t.base", title="Base", kind="definition", status="admitted")
    thm = Node(id="t.thm", title="Theorem", kind="theorem", status="admitted", uses=["t.base"])
    graph, diags = build_graph([thm, base])
    assert diags == []

    dot = graph_to_dot(build_blueprint_graph(graph))

    assert 'strict digraph "" {' in dot
    assert '"t.base" -> "t.thm"' in dot
    assert 'shape="box"' in dot
    assert 'shape="ellipse"' in dot
