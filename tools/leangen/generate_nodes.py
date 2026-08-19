from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import write_json


def slugify(name: str) -> str:
    slug = name.replace(".", "-").replace("_", "-").replace("/", "-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def build_node_markdown(theorem: dict, deps: list[dict]) -> str:
    uses = [edge["target"] for edge in deps if edge["source"] == theorem["name"]]
    lines = [
        "---",
        f'id: {slugify(theorem["name"])}',
        f'title: {theorem["name"]}',
        f'kind: {theorem["kind"]}',
        "status: staged",
        "lean:",
        f'  module: {theorem["module"]}',
        "  declarations:",
        f'    - {theorem["name"]}',
        "uses:",
    ]
    for dep in uses:
        lines.append(f"  - {dep}")
    lines.extend(
        [
            "---",
            "",
            f"# {theorem['name']}",
            "",
            "## Lean type",
            "",
            "```lean",
            theorem["type"],
            "```",
            "",
            "## Dependencies",
            "",
        ]
    )
    if uses:
        for dep in uses:
            lines.append(f"- {dep}")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="leangen-generate-nodes")
    parser.add_argument("--theorems-json", required=True, type=Path)
    parser.add_argument("--dependencies-json", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    theorems = json.loads(args.theorems_json.read_text(encoding="utf-8"))
    deps = json.loads(args.dependencies_json.read_text(encoding="utf-8"))
    nodes_dir = args.output_dir / "nodes"
    nodes_dir.mkdir(parents=True, exist_ok=True)

    manifests = []
    for theorem in theorems:
        node_slug = slugify(theorem["name"])
        node_path = nodes_dir / f"{node_slug}.md"
        node_path.write_text(build_node_markdown(theorem, deps), encoding="utf-8")
        manifests.append(
            {
                "name": theorem["name"],
                "path": str(node_path),
                "module": theorem["module"],
                "kind": theorem["kind"],
            }
        )

    write_json(args.output_dir / "leangen-node-manifest.json", manifests)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

