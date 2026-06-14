"""Dry-run structured graph-refactor operations without writing node files."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from tools.knowledge.config import load_project_config
from tools.knowledge.export import home_topic_for_node, leaf_topic_ids_for_node
from tools.knowledge.graph import KnowledgeGraph, build_graph
from tools.knowledge.models import STAGED_STATUSES, Node
from tools.knowledge.node_refs import check_node_body_refs
from tools.knowledge.parser import scan_directory
from tools.knowledge.validator import Diagnostic, validate_node


OPERATION_KINDS = frozenset({
    "add-node-from-request",
    "add-dependency",
    "remove-dependency",
    "replace-node-body",
    "move-primary-topic",
    "add-topic-membership",
    "remove-topic-membership",
    "mark-lean-topic-divergent",
    "delete-node",
})


def _load_nodes(root: Path, *, include_staged: bool) -> tuple[dict[str, Node], set[str]]:
    nodes: list[Node] = []
    staged_ids: set[str] = set()
    nodes_dir = root / "nodes"
    staged_dir = root / "staged"
    if nodes_dir.exists():
        nodes.extend(scan_directory(nodes_dir))
    if include_staged and staged_dir.exists():
        staged = scan_directory(staged_dir)
        staged_ids = {node.id for node in staged}
        nodes.extend(staged)
    return {node.id: node for node in nodes if node.id}, staged_ids


def _load_plan(plan_path: Path) -> tuple[list[dict[str, Any]], list[Diagnostic]]:
    try:
        raw = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    except OSError as exc:
        return [], [_diag("error", f"cannot read dry-run plan: {exc}", plan_path)]
    except yaml.YAMLError as exc:
        return [], [_diag("error", f"invalid dry-run plan YAML: {exc}", plan_path)]

    if isinstance(raw, list):
        operations = raw
    elif isinstance(raw, dict) and isinstance(raw.get("operations"), list):
        operations = raw["operations"]
    else:
        return [], [_diag("error", "dry-run plan must be a list or a mapping with operations: []", plan_path)]

    diags: list[Diagnostic] = []
    out: list[dict[str, Any]] = []
    for index, operation in enumerate(operations, start=1):
        if not isinstance(operation, dict):
            diags.append(_diag("error", f"operation {index} must be a mapping", plan_path))
            continue
        out.append(dict(operation))
    return out, diags


def _diag(level: str, message: str, path: Path | None = None) -> Diagnostic:
    return Diagnostic(level, "<refactor-dry-run>", message, path, code="REFACTOR_DRY_RUN")


def _diagnostic_key(diag: Diagnostic) -> tuple[str, str, str, str | None, tuple[str, ...]]:
    return (diag.level, diag.node_id, diag.message, diag.code, tuple(diag.related))


def _diagnostic_payload(diag: Diagnostic) -> dict[str, Any]:
    return {
        "level": diag.level,
        "node_id": diag.node_id,
        "message": diag.message,
        "file_path": str(diag.file_path) if diag.file_path else None,
        "code": diag.code,
        "related": list(diag.related),
    }


def _graph_summary(graph: KnowledgeGraph) -> dict[str, int]:
    return {
        "nodes": len(graph.nodes),
        "edges": sum(len(deps) for deps in graph.edges.values()),
    }


def _node_snapshot(node: Node) -> dict[str, Any]:
    return {
        "id": node.id,
        "title": node.title,
        "kind": node.kind,
        "status": node.status,
        "uses": list(node.uses or []),
        "primary_topic": node.primary_topic,
        "home_topic": home_topic_for_node(node),
        "topics": leaf_topic_ids_for_node(node),
        "explicit_topics": list(node.topics or []),
        "topic_lean_alignment": node.topic_lean_alignment,
        "file_path": str(node.file_path) if node.file_path else None,
        "body": node.body,
    }


def _operation_result(
    *,
    index: int,
    operation: dict[str, Any],
    status: str,
    message: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "index": index,
        "op": operation.get("op") or operation.get("kind"),
        "status": status,
        "message": message,
        "operation": operation,
        "before": before,
        "after": after,
    }


def _require_string(operation: dict[str, Any], key: str) -> str | None:
    value = operation.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _resolve_path(raw: str, *, root: Path, plan_path: Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    for candidate in (root / path, plan_path.parent / path, Path(raw)):
        if candidate.exists():
            return candidate
    return root / path


def _read_yaml_mapping(path: Path) -> tuple[dict[str, Any], list[Diagnostic]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {}, [_diag("error", f"cannot read YAML file {path}: {exc}", path)]
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return {}, [_diag("error", f"invalid YAML file {path}: {exc}", path)]
    if not isinstance(raw, dict):
        return {}, [_diag("error", f"YAML file must be a mapping: {path}", path)]
    return raw, []


def _request_node_body(request: dict[str, Any], title: str) -> str:
    body = request.get("proposed_body")
    if isinstance(body, str) and body.strip():
        return body.strip()
    statement = request.get("proposed_statement")
    if isinstance(statement, str) and statement.strip():
        return f"# {title}\n\n{statement.strip()}"
    return f"# {title}"


def _body_from_operation(
    operation: dict[str, Any],
    *,
    root: Path,
    plan_path: Path,
    title: str,
) -> tuple[str | None, list[Diagnostic]]:
    body = operation.get("body")
    if isinstance(body, str) and body.strip():
        return body.strip(), []

    body_path = _require_string(operation, "body_path")
    if body_path is not None:
        path = _resolve_path(body_path, root=root, plan_path=plan_path)
        try:
            return path.read_text(encoding="utf-8").strip(), []
        except OSError as exc:
            return None, [_diag("error", f"cannot read body_path {path}: {exc}", path)]

    request_path = _require_string(operation, "request_path")
    if request_path is not None:
        path = _resolve_path(request_path, root=root, plan_path=plan_path)
        request, diags = _read_yaml_mapping(path)
        if diags:
            return None, diags
        return _request_node_body(request, title), []

    return None, [_diag("error", "replace-node-body requires body, body_path, or request_path", plan_path)]


def _node_from_request(
    request: dict[str, Any],
    *,
    request_path: Path,
    operation: dict[str, Any],
) -> tuple[Node | None, list[Diagnostic]]:
    diags: list[Diagnostic] = []

    def require_request_string(key: str) -> str | None:
        value = request.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        diags.append(_diag("error", f"request file {request_path} missing {key!r}", request_path))
        return None

    node_id = require_request_string("proposed_id")
    title = require_request_string("proposed_title")
    kind = require_request_string("target_kind")
    if node_id is None or title is None or kind is None:
        return None, diags

    raw_uses = request.get("proposed_uses") or []
    if not isinstance(raw_uses, list) or not all(isinstance(item, str) for item in raw_uses):
        diags.append(_diag("error", f"request file {request_path} has invalid proposed_uses", request_path))
        return None, diags

    status = _require_string(operation, "status") or "staged"
    primary_topic = _require_string(operation, "primary_topic")
    topics = operation.get("topics") or []
    if not isinstance(topics, list) or not all(isinstance(item, str) and item.strip() for item in topics):
        diags.append(_diag("error", "add-node-from-request topics must be a list of strings", request_path))
        return None, diags

    return Node(
        id=node_id,
        title=title,
        kind=kind,
        status=status,
        uses=list(raw_uses),
        primary_topic=primary_topic,
        topics=list(topics),
        body=_request_node_body(request, title),
        file_path=request_path,
    ), []


def _replace_node(nodes: dict[str, Node], node: Node) -> None:
    nodes[node.id] = node


def _add_topic_membership(node: Node, topic: str) -> Node:
    current = leaf_topic_ids_for_node(node)
    if topic in current:
        return node
    explicit = list(node.topics or [])
    if not explicit:
        explicit.append(home_topic_for_node(node))
    explicit.append(topic)
    return replace(node, topics=explicit)


def _remove_topic_membership(node: Node, topic: str) -> Node | None:
    if node.topics:
        explicit = [item for item in node.topics if item != topic]
        return replace(node, topics=explicit)
    if topic == home_topic_for_node(node):
        return None
    return node


def _apply_operation(
    nodes: dict[str, Node],
    operation: dict[str, Any],
    *,
    index: int,
    plan_path: Path,
    root: Path,
    staged_ids: set[str],
) -> tuple[dict[str, Any], list[Diagnostic]]:
    op = _require_string(operation, "op") or _require_string(operation, "kind")
    if op not in OPERATION_KINDS:
        return _operation_result(
            index=index,
            operation=operation,
            status="error",
            message=f"unsupported operation {op!r}",
        ), [_diag("error", f"operation {index} has unsupported op {op!r}", plan_path)]

    if op == "add-node-from-request":
        request_path = _require_string(operation, "request_path")
        if request_path is None:
            return _operation_result(
                index=index,
                operation=operation,
                status="error",
                message="missing request_path",
            ), [_diag("error", f"operation {index} missing request_path", plan_path)]
        path = _resolve_path(request_path, root=root, plan_path=plan_path)
        request, request_diags = _read_yaml_mapping(path)
        if request_diags:
            return _operation_result(
                index=index,
                operation=operation,
                status="error",
                message=f"cannot load request file {path}",
            ), request_diags
        node, node_diags = _node_from_request(request, request_path=path, operation=operation)
        if node is None:
            return _operation_result(
                index=index,
                operation=operation,
                status="error",
                message=f"cannot construct node from request file {path}",
            ), node_diags
        if node.id in nodes:
            return _operation_result(
                index=index,
                operation=operation,
                status="error",
                message=f"request proposed_id already exists: {node.id!r}",
                after=_node_snapshot(nodes[node.id]),
            ), [_diag("error", f"operation {index} proposed node already exists: {node.id!r}", path)]
        nodes[node.id] = node
        if node.status in STAGED_STATUSES:
            staged_ids.add(node.id)
        return _operation_result(
            index=index,
            operation=operation,
            status="applied",
            message=f"would add node {node.id!r} from request file {path}",
            before=None,
            after=_node_snapshot(node),
        ), []

    node_id = _require_string(operation, "node_id")
    if node_id is None:
        return _operation_result(
            index=index,
            operation=operation,
            status="error",
            message="missing node_id",
        ), [_diag("error", f"operation {index} missing node_id", plan_path)]
    if node_id not in nodes:
        return _operation_result(
            index=index,
            operation=operation,
            status="error",
            message=f"unknown node_id {node_id!r}",
        ), [_diag("error", f"operation {index} references unknown node_id {node_id!r}", plan_path)]

    node = nodes[node_id]
    before = _node_snapshot(node)

    if op == "delete-node":
        del nodes[node_id]
        return _operation_result(
            index=index,
            operation=operation,
            status="applied",
            message=f"would remove node {node_id!r}",
            before=before,
            after=None,
        ), []

    if op == "replace-node-body":
        body, body_diags = _body_from_operation(
            operation,
            root=root,
            plan_path=plan_path,
            title=node.title,
        )
        if body_diags or body is None:
            return _operation_result(
                index=index,
                operation=operation,
                status="error",
                message="cannot load replacement body",
                before=before,
                after=before,
            ), body_diags
        if node.body == body:
            return _operation_result(
                index=index,
                operation=operation,
                status="noop",
                message=f"{node_id!r} already has the requested body",
                before=before,
                after=before,
            ), []
        updated = replace(node, body=body)
        _replace_node(nodes, updated)
        return _operation_result(
            index=index,
            operation=operation,
            status="applied",
            message=f"would replace body of {node_id!r}",
            before=before,
            after=_node_snapshot(updated),
        ), []

    if op in {"add-dependency", "remove-dependency"}:
        dependency = _require_string(operation, "dependency")
        if dependency is None:
            return _operation_result(
                index=index,
                operation=operation,
                status="error",
                message="missing dependency",
                before=before,
                after=before,
            ), [_diag("error", f"operation {index} missing dependency", plan_path)]
        if op == "add-dependency" and dependency not in nodes:
            return _operation_result(
                index=index,
                operation=operation,
                status="error",
                message=f"unknown dependency {dependency!r}",
                before=before,
                after=before,
            ), [_diag("error", f"operation {index} references unknown dependency {dependency!r}", plan_path)]

        uses = list(node.uses or [])
        if op == "add-dependency":
            if dependency in uses:
                return _operation_result(
                    index=index,
                    operation=operation,
                    status="noop",
                    message=f"{node_id!r} already uses {dependency!r}",
                    before=before,
                    after=before,
                ), []
            updated = replace(node, uses=[*uses, dependency])
            _replace_node(nodes, updated)
            return _operation_result(
                index=index,
                operation=operation,
                status="applied",
                message=f"would add dependency {dependency!r} to {node_id!r}",
                before=before,
                after=_node_snapshot(updated),
            ), []

        if dependency not in uses:
            return _operation_result(
                index=index,
                operation=operation,
                status="noop",
                message=f"{node_id!r} does not use {dependency!r}",
                before=before,
                after=before,
            ), []
        updated = replace(node, uses=[dep for dep in uses if dep != dependency])
        _replace_node(nodes, updated)
        return _operation_result(
            index=index,
            operation=operation,
            status="applied",
            message=f"would remove dependency {dependency!r} from {node_id!r}",
            before=before,
            after=_node_snapshot(updated),
        ), []

    if op == "move-primary-topic":
        topic = _require_string(operation, "topic")
        if topic is None:
            return _operation_result(
                index=index,
                operation=operation,
                status="error",
                message="missing topic",
                before=before,
                after=before,
            ), [_diag("error", f"operation {index} missing topic", plan_path)]
        if node.primary_topic == topic:
            return _operation_result(
                index=index,
                operation=operation,
                status="noop",
                message=f"{node_id!r} already has primary_topic {topic!r}",
                before=before,
                after=before,
            ), []
        updated = replace(node, primary_topic=topic)
        _replace_node(nodes, updated)
        return _operation_result(
            index=index,
            operation=operation,
            status="applied",
            message=f"would set primary_topic of {node_id!r} to {topic!r}",
            before=before,
            after=_node_snapshot(updated),
        ), []

    if op == "add-topic-membership":
        topic = _require_string(operation, "topic")
        if topic is None:
            return _operation_result(
                index=index,
                operation=operation,
                status="error",
                message="missing topic",
                before=before,
                after=before,
            ), [_diag("error", f"operation {index} missing topic", plan_path)]
        updated = _add_topic_membership(node, topic)
        if updated is node:
            return _operation_result(
                index=index,
                operation=operation,
                status="noop",
                message=f"{node_id!r} already belongs to topic {topic!r}",
                before=before,
                after=before,
            ), []
        _replace_node(nodes, updated)
        return _operation_result(
            index=index,
            operation=operation,
            status="applied",
            message=f"would add topic membership {topic!r} to {node_id!r}",
            before=before,
            after=_node_snapshot(updated),
        ), []

    if op == "remove-topic-membership":
        topic = _require_string(operation, "topic")
        if topic is None:
            return _operation_result(
                index=index,
                operation=operation,
                status="error",
                message="missing topic",
                before=before,
                after=before,
            ), [_diag("error", f"operation {index} missing topic", plan_path)]
        updated = _remove_topic_membership(node, topic)
        if updated is None:
            return _operation_result(
                index=index,
                operation=operation,
                status="error",
                message="cannot remove implicit home topic without moving primary_topic",
                before=before,
                after=before,
            ), [_diag(
                "error",
                f"operation {index} cannot remove implicit home topic from {node_id!r}",
                plan_path,
            )]
        if updated is node:
            return _operation_result(
                index=index,
                operation=operation,
                status="noop",
                message=f"{node_id!r} does not explicitly belong to topic {topic!r}",
                before=before,
                after=before,
            ), []
        _replace_node(nodes, updated)
        return _operation_result(
            index=index,
            operation=operation,
            status="applied",
            message=f"would remove topic membership {topic!r} from {node_id!r}",
            before=before,
            after=_node_snapshot(updated),
        ), []

    updated = replace(node, topic_lean_alignment="divergent")
    if updated.topic_lean_alignment == node.topic_lean_alignment:
        return _operation_result(
            index=index,
            operation=operation,
            status="noop",
            message=f"{node_id!r} already has topic_lean_alignment: divergent",
            before=before,
            after=before,
        ), []
    _replace_node(nodes, updated)
    return _operation_result(
        index=index,
        operation=operation,
        status="applied",
        message=f"would mark {node_id!r} as Lean/topic divergent",
        before=before,
        after=_node_snapshot(updated),
    ), []


def _validate_loaded_nodes(
    nodes: dict[str, Node],
    *,
    root: Path,
    staged_ids: set[str],
) -> tuple[KnowledgeGraph, list[Diagnostic]]:
    config = load_project_config(root)
    node_list = list(nodes.values())
    diags: list[Diagnostic] = []
    for node in node_list:
        diags.extend(validate_node(
            node,
            is_staged_dir=node.id in staged_ids,
            project_library=config.sources.library,
            require_source_spans=config.sources.require_source_spans,
        ))
    all_nodes_index = {node.id: node for node in node_list}
    for node in node_list:
        diags.extend(check_node_body_refs(node, all_nodes_index))
    graph, graph_diags = build_graph(node_list)
    diags.extend(graph_diags)
    return graph, diags


def _diagnostic_delta(
    before: list[Diagnostic],
    after: list[Diagnostic],
) -> tuple[list[Diagnostic], list[Diagnostic]]:
    before_keys = {_diagnostic_key(diag) for diag in before}
    after_keys = {_diagnostic_key(diag) for diag in after}
    new = [diag for diag in after if _diagnostic_key(diag) not in before_keys]
    resolved = [diag for diag in before if _diagnostic_key(diag) not in after_keys]
    return new, resolved


def _changed_nodes(
    before_nodes: dict[str, Node],
    after_nodes: dict[str, Node],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    changed: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    added: list[dict[str, Any]] = []
    for node_id in sorted(before_nodes):
        before = _node_snapshot(before_nodes[node_id])
        if node_id not in after_nodes:
            removed.append(before)
            continue
        after = _node_snapshot(after_nodes[node_id])
        if before != after:
            changed.append({"node_id": node_id, "before": before, "after": after})
    for node_id in sorted(set(after_nodes) - set(before_nodes)):
        added.append(_node_snapshot(after_nodes[node_id]))
    return changed, removed, added


def _status_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"applied": 0, "noop": 0, "error": 0}
    for result in results:
        status = result["status"]
        counts[status] = counts.get(status, 0) + 1
    return counts


def build_refactor_dry_run(
    root: Path,
    plan_path: Path,
    *,
    include_staged: bool = False,
) -> dict[str, Any]:
    operations, plan_diags = _load_plan(plan_path)
    before_nodes, staged_ids = _load_nodes(root, include_staged=include_staged)
    before_graph, before_diags = _validate_loaded_nodes(before_nodes, root=root, staged_ids=staged_ids)

    after_nodes = dict(before_nodes)
    operation_results: list[dict[str, Any]] = []
    operation_diags: list[Diagnostic] = list(plan_diags)
    if not plan_diags:
        for index, operation in enumerate(operations, start=1):
            result, diags = _apply_operation(
                after_nodes,
                operation,
                index=index,
                plan_path=plan_path,
                root=root,
                staged_ids=staged_ids,
            )
            operation_results.append(result)
            operation_diags.extend(diags)

    after_graph, after_diags = _validate_loaded_nodes(after_nodes, root=root, staged_ids=staged_ids)
    new_diags, resolved_diags = _diagnostic_delta(before_diags, after_diags)
    changed, removed, added = _changed_nodes(before_nodes, after_nodes)
    operation_errors = [diag for diag in operation_diags if diag.level == "error"]
    new_errors = [diag for diag in new_diags if diag.level == "error"]

    return {
        "kind": "mdblueprint-refactor-dry-run",
        "mode": "admitted+staged" if include_staged else "admitted",
        "knowledge_root": str(root),
        "plan_path": str(plan_path),
        "writes": [],
        "allowed_operations": sorted(OPERATION_KINDS),
        "would_introduce_errors": bool(operation_errors or new_errors),
        "after_has_errors": any(diag.level == "error" for diag in after_diags) or bool(operation_errors),
        "summary": {
            "operation_status_counts": _status_counts(operation_results),
            "added_node_count": len(added),
            "changed_node_count": len(changed),
            "removed_node_count": len(removed),
            "baseline_errors": sum(1 for diag in before_diags if diag.level == "error"),
            "baseline_warnings": sum(1 for diag in before_diags if diag.level == "warning"),
            "new_errors": len(new_errors),
            "new_warnings": sum(1 for diag in new_diags if diag.level == "warning"),
            "resolved_errors": sum(1 for diag in resolved_diags if diag.level == "error"),
            "resolved_warnings": sum(1 for diag in resolved_diags if diag.level == "warning"),
        },
        "graph": {
            "before": _graph_summary(before_graph),
            "after": _graph_summary(after_graph),
        },
        "operations": operation_results,
        "operation_diagnostics": [_diagnostic_payload(diag) for diag in operation_diags],
        "new_diagnostics": [_diagnostic_payload(diag) for diag in new_diags],
        "resolved_diagnostics": [_diagnostic_payload(diag) for diag in resolved_diags],
        "added_nodes": added,
        "changed_nodes": changed,
        "removed_nodes": removed,
    }


def _render_text(result: dict[str, Any]) -> str:
    summary = result["summary"]
    graph = result["graph"]
    counts = summary["operation_status_counts"]
    lines = [
        "mdblueprint refactor dry run",
        f"mode: {result['mode']}",
        f"plan: {result['plan_path']}",
        "writes: none",
        (
            "operations: "
            f"{counts.get('applied', 0)} applied, "
            f"{counts.get('noop', 0)} noop, "
            f"{counts.get('error', 0)} error"
        ),
        (
            "graph: "
            f"{graph['before']['nodes']} nodes/{graph['before']['edges']} edges -> "
            f"{graph['after']['nodes']} nodes/{graph['after']['edges']} edges"
        ),
        (
            "diagnostic delta: "
            f"{summary['new_errors']} new error(s), "
            f"{summary['new_warnings']} new warning(s), "
            f"{summary['resolved_errors']} resolved error(s), "
            f"{summary['resolved_warnings']} resolved warning(s)"
        ),
        f"would_introduce_errors: {str(result['would_introduce_errors']).lower()}",
    ]
    if result["changed_nodes"]:
        lines.append("changed nodes:")
        for item in result["changed_nodes"]:
            lines.append(f"- {item['node_id']}")
    if result["added_nodes"]:
        lines.append("added nodes:")
        for item in result["added_nodes"]:
            lines.append(f"- {item['id']}")
    if result["removed_nodes"]:
        lines.append("removed nodes:")
        for item in result["removed_nodes"]:
            lines.append(f"- {item['id']}")
    for diag in result["operation_diagnostics"] + result["new_diagnostics"]:
        lines.append(str(Diagnostic(
            diag["level"],
            diag["node_id"],
            diag["message"],
            Path(diag["file_path"]) if diag["file_path"] else None,
            code=diag["code"],
            related=tuple(diag["related"]),
        )))
    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run structured mdblueprint graph-refactor operations."
    )
    parser.add_argument("knowledge_root", type=Path)
    parser.add_argument("plan", type=Path, help="YAML file containing operations: []")
    parser.add_argument("--include-staged", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(sys.argv[1:] if argv is None else argv)
    result = build_refactor_dry_run(
        args.knowledge_root,
        args.plan,
        include_staged=args.include_staged,
    )
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(_render_text(result))
    return 1 if result["would_introduce_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
