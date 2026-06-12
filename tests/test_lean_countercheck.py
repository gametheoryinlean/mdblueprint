from __future__ import annotations

from pathlib import Path

from tools.knowledge.lean_countercheck import build_countercheck_report, extract_decl_records


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_extract_decl_records_finds_named_declarations(tmp_path: Path) -> None:
    source_root = tmp_path / "EconCSLib"
    lean_file = _write(
        source_root / "GameTheory" / "StrategicGame" / "Dominance.lean",
        """theorem WeaklyDominates.foo : True := by\n  trivial\n\ndef IsWeaklyDominant.bar : True := by\n  trivial\n""",
    )

    records = extract_decl_records(lean_file, source_root)

    assert [record.name for record in records] == ["WeaklyDominates.foo", "IsWeaklyDominant.bar"]
    assert [record.kind for record in records] == ["theorem", "def"]


def test_countercheck_matches_node_and_reports_lsp_probe(tmp_path: Path) -> None:
    source_root = tmp_path / "EconCSLib"
    lean_file = _write(
        source_root / "GameTheory" / "StrategicGame" / "Dominance.lean",
        """import EconCSLib.GameTheory.StrategicGame.BestResponse\n\n/-! test file -/\n\ntheorem StrictlyDominates.weakly {G : Nat} : True := by\n  exact True.intro\n\n/-- A strictly dominant strategy is weakly dominant. -/\ntheorem IsStrictlyDominant.isWeaklyDominant {G : Nat} : True := by\n  exact True.intro\n\n/-- T2: A weakly dominant strategy is a best response. -/\ntheorem IsWeaklyDominant.isBestResponse {G : Nat} : True := by\n  exact True.intro\n""",
    )
    node_file = _write(
        tmp_path / "node.md",
        """---\nid: strategic_games.weakly_dominant_strategy\ntitle: Weakly Dominant Strategy\nkind: definition\nstatus: admitted\nuses:\n  - strategic_games.weakly_dominates\nlean:\n  modules:\n    - GameTheoryLib.StrategicGame.Dominance\n  declarations:\n    - IsWeaklyDominant\n---\n\n# Weakly Dominant Strategy\n""",
    )
    corpus_root = tmp_path / "corpus"
    _write(
        corpus_root / "GameTheory" / "StrategicGame" / "BestResponse.lean",
        """theorem IsBestResponse.foo : True := by\n  trivial\n""",
    )

    report = build_countercheck_report(
        node_file=node_file,
        lean_file=lean_file,
        source_root=source_root,
        corpus_root=corpus_root,
        compare_with_lsp=False,
    )

    assert "IsWeaklyDominant.isBestResponse" in report.extracted_declarations
    assert "IsWeaklyDominant" in report.node_declarations
    assert report.method_status == {"heuristic": "used"}
    assert report.missing_declarations == ["IsWeaklyDominant"]
    assert report.missing_uses == []
    assert "WeaklyDominates" not in report.extra_uses
    assert report.extra_declarations
