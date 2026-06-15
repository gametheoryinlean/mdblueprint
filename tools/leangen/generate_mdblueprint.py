from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import write_json


def topic_for_node(node: dict) -> str:
    module = node.get("module", "")
    if not module:
        return "generated"
    return module.split(".")[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="leangen-generate-mdblueprint")
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--site-title", default="Lean-derived Blueprint")
    parser.add_argument("--short-title", default="Lean Blueprint")
    args = parser.parse_args(argv)

    manifest_path = args.input_dir / "leangen-node-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    output_nodes = args.output_dir / "nodes"
    output_nodes.mkdir(parents=True, exist_ok=True)
    for node in manifest:
        src = Path(node["path"])
        dst = output_nodes / src.name
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    topics = []
    seen = set()
    for node in manifest:
        topic = topic_for_node(node)
        if topic in seen:
            continue
        seen.add(topic)
        topics.append({"id": topic, "title": topic.replace("_", " ").title(), "aliases": [topic]})

    mdblueprint = {
        "site": {"title": args.site_title, "short_title": args.short_title},
        "topics": topics,
    }
    write_json(args.output_dir / "mdblueprint.json", mdblueprint)
    (args.output_dir / "mdblueprint.yml").write_text(
        "site:\n"
        f"  title: {args.site_title}\n"
        f"  short_title: {args.short_title}\n"
        "topics:\n"
        + "".join(
            [
                f"  - id: {topic['id']}\n"
                f"    title: {topic['title']}\n"
                f"    aliases:\n"
                + "".join(f"      - {alias}\n" for alias in topic["aliases"])
                for topic in topics
            ]
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

