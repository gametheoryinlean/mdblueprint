from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.knowledge.publish import publish as publish_knowledge

from .extract_dependencies import main as extract_dependencies_main
from .extract_project import main as extract_project_main
from .extract_theorems import main as extract_theorems_main
from .generate_mdblueprint import main as generate_mdblueprint_main
from .generate_nodes import main as generate_nodes_main
from .lean_runner import build_project


def _is_ignored(path: Path) -> bool:
    parts = set(path.parts)
    return any(part in parts for part in {'.git', '.lake', 'build', 'dist', 'node_modules', '__pycache__'})


def _load_graph(path: Path) -> tuple[dict[str, dict], set[tuple[str, str]]]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    nodes = {n['id']: n for n in payload.get('nodes', [])}
    edges: set[tuple[str, str]] = set()
    for node in payload.get('nodes', []):
        for dep in node.get('uses', []) or []:
            edges.add((node['id'], dep))
    return nodes, edges


def _compare_graphs(generated: Path, ground_truth: Path) -> dict:
    gen_nodes, gen_edges = _load_graph(generated)
    gt_nodes, gt_edges = _load_graph(ground_truth)
    node_ids = set(gen_nodes) & set(gt_nodes)
    return {
        'generated_node_count': len(gen_nodes),
        'ground_truth_node_count': len(gt_nodes),
        'shared_node_count': len(node_ids),
        'generated_edge_count': len(gen_edges),
        'ground_truth_edge_count': len(gt_edges),
        'shared_edge_count': len(gen_edges & gt_edges),
        'generated_only_nodes': sorted(set(gen_nodes) - set(gt_nodes)),
        'ground_truth_only_nodes': sorted(set(gt_nodes) - set(gen_nodes)),
        'generated_only_edges': sorted([f'{a}->{b}' for (a, b) in gen_edges - gt_edges]),
        'ground_truth_only_edges': sorted([f'{a}->{b}' for (a, b) in gt_edges - gen_edges]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='leangen-run-full')
    parser.add_argument('--project-root', required=True, type=Path)
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--ground-truth-graph', type=Path)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--skip-build', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--lean-first', action='store_true')
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()
    source_root = (args.source_root or project_root).resolve()
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and not args.resume:
        raise SystemExit(f'output directory already exists: {output_dir}')
    output_dir.mkdir(parents=True, exist_ok=True)

    lean_files = [
        p for p in sorted(source_root.rglob('*.lean'))
        if not _is_ignored(p.relative_to(source_root))
    ]

    if not args.skip_build and not args.lean_first:
        project_build = build_project(project_root=project_root)
        if project_build.returncode != 0:
            raise SystemExit(project_build.returncode)

    all_theorems_path = output_dir / 'theorems.json'
    all_dependencies_path = output_dir / 'dependencies.json'

    if args.lean_first:
        if not args.resume or not (all_theorems_path.exists() and all_dependencies_path.exists()):
            extract_project_main([
                '--project-root', str(project_root),
                '--source-root', str(source_root),
                '--theorems-output', str(all_theorems_path),
                '--dependencies-output', str(all_dependencies_path),
                '--skip-build',
            ])
        all_theorems = json.loads(all_theorems_path.read_text(encoding='utf-8'))
        all_dependencies = json.loads(all_dependencies_path.read_text(encoding='utf-8'))
    else:
        raw_dir = output_dir / 'raw'
        raw_dir.mkdir(parents=True, exist_ok=True)

        all_theorems: list[dict] = []
        all_dependencies: list[dict] = []
        for idx, lean_file in enumerate(lean_files, start=1):
            stem = lean_file.relative_to(source_root).as_posix().replace('/', '__')
            theorem_path = raw_dir / f'{idx:04d}-{stem}.theorems.json'
            dependency_path = raw_dir / f'{idx:04d}-{stem}.deps.json'
            if not theorem_path.exists() or theorem_path.stat().st_size == 0:
                extract_theorems_main([
                    '--project-root', str(project_root),
                    '--source-root', str(source_root),
                    '--lean-file', str(lean_file),
                    '--output', str(theorem_path),
                    '--skip-build',
                ])
            if theorem_path.exists() and theorem_path.stat().st_size > 0:
                all_theorems.extend(json.loads(theorem_path.read_text(encoding='utf-8')))
                if not dependency_path.exists() or dependency_path.stat().st_size == 0:
                    extract_dependencies_main([
                        '--project-root', str(project_root),
                        '--source-root', str(source_root),
                        '--lean-file', str(lean_file),
                        '--theorems-json', str(theorem_path),
                        '--output', str(dependency_path),
                        '--skip-build',
                    ])
                if dependency_path.exists() and dependency_path.stat().st_size > 0:
                    all_dependencies.extend(json.loads(dependency_path.read_text(encoding='utf-8')))

        all_theorems_path.write_text(json.dumps(all_theorems, indent=2, sort_keys=True) + "\n", encoding='utf-8')
        all_dependencies_path.write_text(json.dumps(all_dependencies, indent=2, sort_keys=True) + "\n", encoding='utf-8')

    staged_dir = output_dir / 'staged'
    generate_nodes_main([
        '--theorems-json', str(all_theorems_path),
        '--dependencies-json', str(all_dependencies_path),
        '--output-dir', str(staged_dir),
    ])

    knowledge_dir = output_dir / 'knowledge'
    generate_mdblueprint_main([
        '--input-dir', str(staged_dir),
        '--output-dir', str(knowledge_dir),
    ])

    site_dir = output_dir / 'site'
    if args.publish or True:
        publish_knowledge(knowledge_dir, site_dir, config_path=knowledge_dir / 'mdblueprint.yml')

    comparison = None
    if args.ground_truth_graph is not None:
        comparison = _compare_graphs(site_dir / 'graph.json', args.ground_truth_graph)
        (output_dir / 'comparison.json').write_text(
            json.dumps(comparison, indent=2, sort_keys=True) + "\n",
            encoding='utf-8',
        )

    summary = {
        'lean_file_count': len(lean_files),
        'theorem_count': len(all_theorems),
        'dependency_count': len(all_dependencies),
        'site_dir': str(site_dir),
        'knowledge_dir': str(knowledge_dir),
        'comparison': comparison,
    }
    (output_dir / 'summary.json').write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding='utf-8',
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
