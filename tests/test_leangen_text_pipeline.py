from __future__ import annotations

import json
from pathlib import Path

from tools.leangen.extract_dependencies import main as extract_dependencies_main
from tools.leangen.extract_theorems import main as extract_theorems_main
from tools.leangen.run_full import main as run_full_main


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def test_text_only_theorem_and_dependency_extraction(tmp_path: Path) -> None:
    source_root = tmp_path / 'EconCSLib'
    foo = _write(
        source_root / 'Alpha.lean',
        '''theorem Alpha.foo : True := by
  trivial
''',
    )
    bar = _write(
        source_root / 'Beta.lean',
        '''import EconCSLib.Alpha

theorem Beta.bar : True := by
  exact Alpha.foo
''',
    )

    theorem_out = tmp_path / 'bar.theorems.json'
    dep_out = tmp_path / 'bar.deps.json'
    extract_theorems_main([
        '--project-root', str(tmp_path / 'project'),
        '--source-root', str(source_root),
        '--lean-file', str(bar),
        '--output', str(theorem_out),
    ])
    extract_dependencies_main([
        '--project-root', str(tmp_path / 'project'),
        '--source-root', str(source_root),
        '--lean-file', str(bar),
        '--theorems-json', str(theorem_out),
        '--output', str(dep_out),
    ])

    theorem_records = json.loads(theorem_out.read_text(encoding='utf-8'))
    deps = json.loads(dep_out.read_text(encoding='utf-8'))

    assert [record['name'] for record in theorem_records] == ['Beta.bar']
    assert theorem_records[0]['dependencies'] == ['Alpha.foo']
    assert deps == [
        {
            'source': 'Beta.bar',
            'target': 'Alpha.foo',
            'kind': 'hard',
            'module': 'EconCSLib.Beta',
        }
    ]


def test_text_only_full_run_creates_artifacts(tmp_path: Path) -> None:
    source_root = tmp_path / 'EconCSLib'
    _write(
        source_root / 'Alpha.lean',
        '''theorem Alpha.foo : True := by
  trivial
''',
    )
    _write(
        source_root / 'Beta.lean',
        '''import EconCSLib.Alpha

theorem Beta.bar : True := by
  exact Alpha.foo
''',
    )

    outdir = tmp_path / 'run'
    run_full_main([
        '--project-root', str(tmp_path / 'project'),
        '--source-root', str(source_root),
        '--output-dir', str(outdir),
        '--skip-build',
    ])

    summary = json.loads((outdir / 'summary.json').read_text(encoding='utf-8'))
    assert summary['lean_file_count'] == 2
    assert summary['theorem_count'] == 2
    assert summary['dependency_count'] == 1
    assert (outdir / 'site' / 'graph.json').exists()
    assert (outdir / 'knowledge' / 'mdblueprint.yml').exists()
