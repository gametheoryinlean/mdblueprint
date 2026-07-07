from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

from tools.knowledge.lean_countercheck import build_countercheck_report, extract_decl_records
from tools.knowledge import lean_countercheck_batch


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_extract_decl_records_finds_named_declarations(tmp_path: Path) -> None:
    source_root = tmp_path / "EconCSLib"
    lean_file = _write(
        source_root / "GameTheory" / "StrategicGame" / "Dominance.lean",
        """theorem WeaklyDominates.foo : True := by
  trivial

def IsWeaklyDominant.bar : True := by
  trivial
""",
    )

    records = extract_decl_records(lean_file, source_root)

    assert [record.name for record in records] == ["WeaklyDominates.foo", "IsWeaklyDominant.bar"]
    assert [record.kind for record in records] == ["theorem", "def"]


def test_countercheck_matches_node_and_reports_normalized_uses(tmp_path: Path) -> None:
    source_root = tmp_path / "EconCSLib"
    lean_file = _write(
        source_root / "GameTheory" / "StrategicGame" / "Dominance.lean",
        """import EconCSLib.GameTheory.StrategicGame.BestResponse

/-! test file -/

theorem StrictlyDominates.weakly {G : Nat} : True := by
  exact True.intro

/-- A strictly dominant strategy is weakly dominant. -/
theorem IsStrictlyDominant.isWeaklyDominant {G : Nat} : True := by
  exact True.intro

/-- A weakly dominant strategy is a best response. -/
theorem IsWeaklyDominant.isBestResponse {G : Nat} : True := by
  exact True.intro
""",
    )
    node_file = _write(
        tmp_path / "node.md",
        """---
id: strategic_games.weakly_dominant_strategy
title: Weakly Dominant Strategy
kind: definition
status: admitted
uses:
  - strategic_games.weakly_dominates
lean:
  modules:
    - GameTheoryLib.StrategicGame.Dominance
  declarations:
    - IsWeaklyDominant
---

# Weakly Dominant Strategy
""",
    )
    corpus_root = tmp_path / "corpus"
    _write(
        corpus_root / "GameTheory" / "StrategicGame" / "BestResponse.lean",
        """theorem IsBestResponse.foo : True := by
  trivial
""",
    )

    report = build_countercheck_report(
        node_file=node_file,
        lean_file=lean_file,
        source_root=source_root,
        corpus_root=corpus_root,
    )

    assert "IsWeaklyDominant.isBestResponse" in report.extracted_declarations
    assert "IsWeaklyDominant" in report.node_declarations
    assert report.method_status == {"heuristic": "used"}
    assert report.missing_declarations == ["IsWeaklyDominant"]
    assert report.missing_uses == []
    assert "WeaklyDominates" not in report.extra_uses
    assert report.extra_declarations


def test_batch_countercheck_reuses_precomputed_corpus(tmp_path: Path, monkeypatch) -> None:
    pairs_file = _write(
        tmp_path / "pairs.json",
        json.dumps([
            {
                "node_file": str(tmp_path / "node.md"),
                "lean_file": str(tmp_path / "file.lean"),
            }
        ]),
    )
    out_dir = tmp_path / "out"
    corpus = {"Shared.fact"}
    calls: list[dict[str, object]] = []

    def fake_build_name_corpus(corpus_root: Path, *, source_root: Path | None = None) -> set[str]:
        assert corpus_root == tmp_path / "corpus"
        assert source_root == tmp_path / "src"
        return corpus

    def fake_build_countercheck_report(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            node_id="example.node",
            raw={"node": {"id": "example.node"}},
            missing_declarations=[],
            extra_declarations=[],
            missing_uses=[],
            extra_uses=[],
        )

    monkeypatch.setattr(lean_countercheck_batch, "build_name_corpus", fake_build_name_corpus)
    monkeypatch.setattr(lean_countercheck_batch, "build_countercheck_report", fake_build_countercheck_report)

    assert lean_countercheck_batch.main([
        "--pairs-file", str(pairs_file),
        "--source-root", str(tmp_path / "src"),
        "--corpus-root", str(tmp_path / "corpus"),
        "--output-dir", str(out_dir),
    ]) == 0

    assert calls
    assert calls[0]["corpus_names"] is corpus
    assert (out_dir / "summary.json").exists()
