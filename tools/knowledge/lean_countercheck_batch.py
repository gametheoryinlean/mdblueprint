"""Batch Lean counterchecks over a predeclared set of node/file pairs.

The batch driver intentionally precomputes the Lean declaration corpus once
and reuses it across all node/file pairs so that the countercheck stage stays
reproducible and reasonably fast.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tools.knowledge.lean_countercheck import (
    build_countercheck_report,
    build_name_corpus,
    safe_countercheck_artifact_stem,
    write_countercheck_report,
)


def _load_pairs(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(raw, list):
        raise SystemExit('pairs file must be a JSON list of mappings')
    pairs: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise SystemExit(f'pair {index} must be a mapping')
        for key in ('node_file', 'lean_file'):
            if key not in item:
                raise SystemExit(f'pair {index} missing {key!r}')
        pairs.append(item)
    return pairs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='mdblueprint-lean-countercheck-batch')
    parser.add_argument('--pairs-file', required=True, type=Path)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--corpus-root', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--reviews-dir', type=Path)
    args = parser.parse_args(argv)

    pairs = _load_pairs(args.pairs_file)
    corpus_names = build_name_corpus(args.corpus_root, source_root=args.source_root)
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    counter_dir = out_dir / 'counterchecks'
    counter_dir.mkdir(parents=True, exist_ok=True)

    reports: list[dict[str, Any]] = []
    used_stems: dict[str, int] = {}
    for pair in pairs:
        report = build_countercheck_report(
            node_file=Path(pair['node_file']),
            lean_file=Path(pair['lean_file']),
            source_root=args.source_root,
            corpus_root=args.corpus_root,
            corpus_names=corpus_names,
        )
        base_stem = safe_countercheck_artifact_stem(
            report.node_id,
            pair['lean_file'],
            module=pair.get('module') if isinstance(pair.get('module'), str) else None,
        )
        stem_count = used_stems.get(base_stem, 0)
        used_stems[base_stem] = stem_count + 1
        stem = base_stem if stem_count == 0 else f"{base_stem}__{stem_count + 1}"
        report_path = counter_dir / f"{stem}.json"
        report_path.write_text(json.dumps(report.raw, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        if args.reviews_dir:
            review_path = write_countercheck_report(report, args.reviews_dir, filename_stem=f"{stem}_lean_countercheck")
        else:
            review_path = None
        reports.append({
            'node_id': report.node_id,
            'node_file': str(pair['node_file']),
            'lean_file': str(pair['lean_file']),
            'countercheck_json': str(report_path),
            'review_path': str(review_path) if review_path else None,
            'missing_declarations': report.missing_declarations,
            'extra_declarations': report.extra_declarations,
            'missing_uses': report.missing_uses,
            'extra_uses': report.extra_uses,
        })

    summary = {
        'pairs': len(pairs),
        'corpus_names': len(corpus_names),
        'nodes_with_missing_decls': sum(bool(r['missing_declarations']) for r in reports),
        'nodes_with_extra_decls': sum(bool(r['extra_declarations']) for r in reports),
        'nodes_with_missing_uses': sum(bool(r['missing_uses']) for r in reports),
        'nodes_with_extra_uses': sum(bool(r['extra_uses']) for r in reports),
        'reports': reports,
    }
    (out_dir / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
