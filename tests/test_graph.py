from pathlib import Path

from tools.knowledge.graph import build_graph, topological_sort
from tools.knowledge.parser import parse_file, scan_directory
from tools.knowledge.models import Node

_TESTS_DIR = Path(__file__).parent
GENERIC_ROOT = _TESTS_DIR / "fixtures" / "generic_knowledge"
NODES_DIR = GENERIC_ROOT / "nodes" / "algebra"
STAGED_DIR = GENERIC_ROOT / "staged" / "algebra"
INVALID_DIR = _TESTS_DIR / "fixtures" / "invalid"


class TestBuildGraph:
    def test_build_from_admitted_nodes(self):
        nodes = scan_directory(NODES_DIR)
        g, diags = build_graph(nodes)
        errors = [d for d in diags if d.level == "error"]
        assert errors == []
        assert len(g.nodes) == 4

    def test_edges(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        assert "algebra.group" in g.edges["algebra.group_homomorphism"]

    def test_reverse_edges(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        assert "algebra.group_homomorphism" in g.reverse_edges["algebra.group"]

    def test_with_staged(self):
        admitted = scan_directory(NODES_DIR)
        staged = scan_directory(STAGED_DIR)
        g, diags = build_graph(admitted + staged)
        assert "algebra.quotient_group" in g.nodes
        errors = [d for d in diags if d.level == "error"]
        assert errors == []


class TestCycleDetection:
    def test_cycle(self):
        a = parse_file(INVALID_DIR / "cycle_a.md")
        b = parse_file(INVALID_DIR / "cycle_b.md")
        _, diags = build_graph([a, b])
        errors = [d for d in diags if d.level == "error"]
        assert any("cycle" in d.message for d in errors)


class TestDuplicateIds:
    def test_duplicate(self):
        node = parse_file(NODES_DIR / "group.md")
        _, diags = build_graph([node, node])
        errors = [d for d in diags if d.level == "error"]
        assert any("duplicate" in d.message for d in errors)


class TestTaskConstraint:
    def test_math_uses_task(self):
        task = Node(id="test.some_task", title="Task", kind="task", status="admitted")
        math = parse_file(INVALID_DIR / "math_uses_task.md")
        _, diags = build_graph([task, math])
        errors = [d for d in diags if d.level == "error"]
        assert any("task" in d.message for d in errors)


class TestProofPlanEdges:
    def test_proof_plan_target_is_tracked_without_polluting_theorem_dependencies(self):
        group = Node(id="algebra.group", title="Group", kind="definition", status="admitted")
        theorem = Node(
            id="algebra.group_identity_unique",
            title="Group Identity Is Unique",
            kind="theorem",
            status="admitted",
            uses=["algebra.group"],
        )
        plan = Node(
            id="algebra.group_identity_unique.plan.via_left_cancel",
            title="Via Left Cancellation",
            kind="proof-plan",
            status="staged",
            target="algebra.group_identity_unique",
            plan_status="candidate",
            uses=["algebra.group"],
        )

        graph, diags = build_graph([group, theorem, plan])

        assert [d for d in diags if d.level == "error"] == []
        assert graph.proof_plan_targets[plan.id] == theorem.id
        assert graph.proof_plans_by_target[theorem.id] == [plan.id]
        assert graph.edges[theorem.id] == ["algebra.group"]
        assert graph.edges[plan.id] == ["algebra.group"]
        assert plan.id not in graph.reverse_edges[theorem.id]

    def test_missing_proof_plan_target_is_diagnostic(self):
        plan = Node(
            id="algebra.group_identity_unique.plan.via_left_cancel",
            title="Via Left Cancellation",
            kind="proof-plan",
            status="staged",
        )

        _, diags = build_graph([plan])

        assert any("proof-plan target" in d.message for d in diags)

    def test_mathematical_node_cannot_use_proof_plan_as_dependency(self):
        theorem = Node(
            id="algebra.group_identity_unique",
            title="Group Identity Is Unique",
            kind="theorem",
            status="admitted",
            uses=["algebra.group_identity_unique.plan.via_left_cancel"],
        )
        plan = Node(
            id="algebra.group_identity_unique.plan.via_left_cancel",
            title="Via Left Cancellation",
            kind="proof-plan",
            status="staged",
            target="algebra.group_identity_unique",
        )

        _, diags = build_graph([theorem, plan])

        errors = [d for d in diags if d.level == "error"]
        assert any("proof-plan" in d.message and "uses" in d.message for d in errors)

    def test_proof_plan_cannot_use_its_target_as_dependency(self):
        theorem = Node(
            id="algebra.group_identity_unique",
            title="Group Identity Is Unique",
            kind="theorem",
            status="admitted",
        )
        plan = Node(
            id="algebra.group_identity_unique.plan.circular",
            title="Circular Plan",
            kind="proof-plan",
            status="staged",
            target="algebra.group_identity_unique",
            uses=["algebra.group_identity_unique"],
        )

        _, diags = build_graph([theorem, plan])

        errors = [d for d in diags if d.level == "error"]
        assert any("proof-plan cannot use its target" in d.message for d in errors)


class TestProvedViaPlanCrossReference:
    def _setup(self, **target_kwargs):
        base = Node(id="t.base", title="Base", kind="definition", status="formalized")
        plan = Node(
            id="t.thm.plan.direct",
            title="Direct Plan",
            kind="proof-plan",
            status="formalized",
            target="t.thm",
            plan_status="selected",
            uses=["t.base"],
        )
        defaults = dict(
            id="t.thm", title="Theorem", kind="theorem", status="proved", uses=[],
        )
        defaults.update(target_kwargs)
        thm = Node(**defaults)
        return [base, plan, thm]

    def test_valid_proved_via_plan_reference(self):
        nodes = self._setup(proved_via_plan="t.thm.plan.direct")
        _, diags = build_graph(nodes)
        assert [d for d in diags if d.level == "error"] == []

    def test_missing_referenced_plan_is_error(self):
        nodes = self._setup(proved_via_plan="t.thm.plan.nonexistent")
        _, diags = build_graph(nodes)
        assert any("references unknown node" in d.message for d in diags)

    def test_reference_to_non_plan_node_is_error(self):
        nodes = self._setup(proved_via_plan="t.base")
        _, diags = build_graph(nodes)
        assert any("must reference a proof-plan node" in d.message for d in diags)

    def test_reference_to_plan_targeting_other_node_is_error(self):
        nodes = self._setup(proved_via_plan="t.thm.plan.direct")
        # Add another theorem and retarget the plan at it instead.
        nodes[1] = Node(
            id="t.thm.plan.direct",
            title="Direct Plan",
            kind="proof-plan",
            status="formalized",
            target="t.other",
            plan_status="selected",
            uses=["t.base"],
        )
        nodes.append(
            Node(id="t.other", title="Other", kind="theorem", status="formalized", uses=[])
        )
        _, diags = build_graph(nodes)
        assert any("whose target is" in d.message for d in diags)


class TestTopologicalSort:
    def test_order(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        order = topological_sort(g)
        idx = {nid: i for i, nid in enumerate(order)}
        assert idx["algebra.group"] < idx["algebra.group_homomorphism"]
        assert idx["algebra.group_homomorphism"] < idx["algebra.group_isomorphism"]
