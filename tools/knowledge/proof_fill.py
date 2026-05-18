"""Proof-fill orchestrator.

Implements the bounded generator/verifier loop described in
docs/agent-contracts.md §7 and skills/mdblueprint-proof-fill/SKILL.md.

The orchestrator:
  1. Builds a bounded context bundle (target node + allowed dependencies).
  2. Calls a generator (CodexRunner) for a candidate proof.
  3. Validates generator output strictly before passing to the verifier.
  4. Calls a fresh verifier with no hidden generator context.
  5. On `accepted`: writes back the proof block (unless dry_run).
  6. On `gap`: passes repair_hint to the generator for up to max_rounds.
  7. On `critical` or exhausted rounds: writes a failure report; node untouched.

Usage (dry-run, claude CLI runner):
    uv run python -m tools.knowledge.proof_fill \\
        --node-id algebra.group_identity_unique \\
        --knowledge-root docs/knowledge --dry-run
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import yaml
from jinja2 import Environment, FileSystemLoader

from tools.knowledge.models import Node
from tools.knowledge.parser import scan_directory

TEMPLATE_DIR = Path(__file__).parent / "templates"

# ── types ──────────────────────────────────────────────────────────────────────

# A runner is any callable: prompt string → raw LLM text response.
CodexRunner = Callable[[str], str]


@dataclasses.dataclass
class GeneratorResult:
    decision: str           # "filled" | "cannot_fill"
    proof: str
    reason: str
    used_node_ids: list[str]


@dataclasses.dataclass
class VerifierResult:
    verdict: str            # "accepted" | "gap" | "critical"
    verification_report: str
    gaps: list[str]
    critical_errors: list[str]
    repair_hint: str


@dataclasses.dataclass
class ProofFillReport:
    node_id: str
    outcome: str            # "accepted" | "cannot_fill" | "gap" | "critical" | "invalid_output"
    proof: str | None
    reason: str
    rounds: int
    repair_hints: list[str]
    timestamp: str = dataclasses.field(
        default_factory=lambda: datetime.datetime.utcnow().isoformat()
    )


# ── context bundle ─────────────────────────────────────────────────────────────

def build_context_bundle(node: Node, all_nodes: dict[str, Node]) -> dict[str, Any]:
    """Build the bounded context bundle for generator and verifier prompts."""
    deps = []
    for dep_id in node.uses:
        dep = all_nodes.get(dep_id)
        if dep is not None:
            deps.append({"id": dep.id, "title": dep.title, "body": dep.body})
    return {
        "target_frontmatter": _frontmatter_text(node),
        "target_body": node.body,
        "dependencies": deps,
        "source_hint": None,
    }


def _frontmatter_text(node: Node) -> str:
    d: dict[str, Any] = {
        "id": node.id,
        "title": node.title,
        "kind": node.kind,
        "status": node.status,
        "uses": node.uses,
    }
    return yaml.dump(d, default_flow_style=False, allow_unicode=True).rstrip()


# ── JSON decoders ──────────────────────────────────────────────────────────────

_PLACEHOLDER_RE = re.compile(
    r"\.\.\.|TODO|FIXME|PLACEHOLDER|\[insert\]|\[fill\]", re.IGNORECASE
)


def decode_generator_output(raw: str) -> GeneratorResult:
    """Parse and validate generator JSON. Raises ValueError on any violation."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Generator output is not valid JSON: {exc}") from exc

    for field in ("decision", "proof", "reason", "used_node_ids"):
        if field not in data:
            raise ValueError(f"Generator output missing required field: {field!r}")

    decision = data["decision"]
    if decision not in ("filled", "cannot_fill"):
        raise ValueError(
            f"Generator decision must be 'filled' or 'cannot_fill', got {decision!r}"
        )

    proof = data["proof"]
    if not isinstance(proof, str):
        raise ValueError("Generator 'proof' field must be a string")

    if decision == "filled":
        if not proof.strip():
            raise ValueError("Generator returned 'filled' but proof text is empty")
        if _PLACEHOLDER_RE.search(proof):
            raise ValueError(
                "Generator proof contains placeholders or operational notes"
            )

    used_node_ids = data["used_node_ids"]
    if not isinstance(used_node_ids, list):
        raise ValueError("Generator 'used_node_ids' must be a list")

    return GeneratorResult(
        decision=decision,
        proof=proof,
        reason=str(data.get("reason", "")),
        used_node_ids=used_node_ids,
    )


def decode_verifier_output(raw: str) -> VerifierResult:
    """Parse and validate verifier JSON. Raises ValueError on any violation."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Verifier output is not valid JSON: {exc}") from exc

    for field in ("verdict", "verification_report", "gaps", "critical_errors", "repair_hint"):
        if field not in data:
            raise ValueError(f"Verifier output missing required field: {field!r}")

    verdict = data["verdict"]
    if verdict not in ("accepted", "gap", "critical"):
        raise ValueError(
            f"Verifier verdict must be 'accepted', 'gap', or 'critical', got {verdict!r}"
        )

    gaps = data["gaps"]
    critical_errors = data["critical_errors"]
    if not isinstance(gaps, list):
        raise ValueError("Verifier 'gaps' must be a list")
    if not isinstance(critical_errors, list):
        raise ValueError("Verifier 'critical_errors' must be a list")

    if verdict == "accepted" and (gaps or critical_errors):
        raise ValueError(
            "Verifier returned 'accepted' but has non-empty gaps or critical_errors"
        )
    if verdict == "gap" and not gaps:
        raise ValueError("Verifier returned 'gap' but 'gaps' list is empty")
    if verdict == "critical" and not critical_errors:
        raise ValueError("Verifier returned 'critical' but 'critical_errors' list is empty")

    return VerifierResult(
        verdict=verdict,
        verification_report=str(data.get("verification_report", "")),
        gaps=gaps,
        critical_errors=critical_errors,
        repair_hint=str(data.get("repair_hint", "")),
    )


# ── output validation ─────────────────────────────────────────────────────────

def validate_generator_result(result: GeneratorResult, node: Node) -> str | None:
    """Return an error string if the result violates local-only restrictions, else None."""
    allowed_ids = set(node.uses) | {node.id}
    for cited_id in result.used_node_ids:
        if cited_id not in allowed_ids:
            return (
                f"Generator cited node id {cited_id!r} which is not in the "
                f"allowed set {sorted(allowed_ids)}"
            )
    return None


# ── writeback ─────────────────────────────────────────────────────────────────

def insert_proof_into_node(node_path: Path, proof_text: str) -> None:
    """Insert a *Proof.* block into the node body. No-op if proof block already present."""
    text = node_path.read_text(encoding="utf-8")
    if "*Proof.*" in text or "**Proof.**" in text:
        return
    proof_block = f"\n\n*Proof.* {proof_text.strip()}\n"
    node_path.write_text(text.rstrip("\n") + proof_block, encoding="utf-8")


def set_verification_proof_accepted(node_path: Path) -> None:
    """Add or update verification.proof: accepted in the node frontmatter."""
    text = node_path.read_text(encoding="utf-8")
    if re.search(r"verification:\s*\n\s+proof:\s+accepted", text):
        return
    if re.search(r"^verification:", text, re.MULTILINE):
        text = re.sub(
            r"(^verification:\s*\n)",
            r"\1  proof: accepted\n",
            text,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        text = re.sub(
            r"(\n---\n)",
            r"\nverification:\n  proof: accepted\n---\n",
            text,
            count=1,
        )
    node_path.write_text(text, encoding="utf-8")


# ── orchestrator ──────────────────────────────────────────────────────────────

def run_proof_fill(
    node: Node,
    all_nodes: dict[str, Node],
    generator: CodexRunner,
    verifier: CodexRunner,
    *,
    max_rounds: int = 2,
    dry_run: bool = False,
    template_dir: Path | None = None,
    source_hint: str | None = None,
) -> ProofFillReport:
    """Run the proof-fill workflow for a single node.

    Returns a ProofFillReport. Does not modify the node file unless
    dry_run is False and the verifier returns 'accepted'.
    """
    tdir = template_dir if template_dir is not None else TEMPLATE_DIR
    env = Environment(loader=FileSystemLoader(str(tdir)))
    gen_tmpl = env.get_template("proof_fill_generate.md")
    ver_tmpl = env.get_template("proof_fill_verify.md")

    bundle = build_context_bundle(node, all_nodes)
    bundle["source_hint"] = source_hint
    repair_hints: list[str] = []
    repair_hint = ""

    for round_num in range(max_rounds):
        gen_prompt = gen_tmpl.render(**bundle, repair_hint=repair_hint)
        gen_raw = generator(gen_prompt)

        try:
            gen_result = decode_generator_output(gen_raw)
        except ValueError as exc:
            return ProofFillReport(
                node_id=node.id,
                outcome="invalid_output",
                proof=None,
                reason=f"Generator validation failed (round {round_num + 1}): {exc}",
                rounds=round_num + 1,
                repair_hints=repair_hints,
            )

        if gen_result.decision == "cannot_fill":
            return ProofFillReport(
                node_id=node.id,
                outcome="cannot_fill",
                proof=None,
                reason=gen_result.reason,
                rounds=round_num + 1,
                repair_hints=repair_hints,
            )

        violation = validate_generator_result(gen_result, node)
        if violation:
            return ProofFillReport(
                node_id=node.id,
                outcome="invalid_output",
                proof=None,
                reason=f"Generator violated local-only restriction (round {round_num + 1}): {violation}",
                rounds=round_num + 1,
                repair_hints=repair_hints,
            )

        # Verifier receives no generator context — only the bundle + candidate proof
        ver_prompt = ver_tmpl.render(**bundle, candidate_proof=gen_result.proof)
        ver_raw = verifier(ver_prompt)

        try:
            ver_result = decode_verifier_output(ver_raw)
        except ValueError as exc:
            return ProofFillReport(
                node_id=node.id,
                outcome="invalid_output",
                proof=None,
                reason=f"Verifier validation failed (round {round_num + 1}): {exc}",
                rounds=round_num + 1,
                repair_hints=repair_hints,
            )

        if ver_result.verdict == "accepted":
            if not dry_run and node.file_path is not None:
                insert_proof_into_node(node.file_path, gen_result.proof)
                set_verification_proof_accepted(node.file_path)
            return ProofFillReport(
                node_id=node.id,
                outcome="accepted",
                proof=gen_result.proof,
                reason=ver_result.verification_report,
                rounds=round_num + 1,
                repair_hints=repair_hints,
            )

        if ver_result.verdict == "critical":
            return ProofFillReport(
                node_id=node.id,
                outcome="critical",
                proof=None,
                reason="; ".join(ver_result.critical_errors),
                rounds=round_num + 1,
                repair_hints=repair_hints,
            )

        # verdict == "gap" — carry repair hint into next round
        repair_hint = ver_result.repair_hint
        if repair_hint:
            repair_hints.append(repair_hint)

    return ProofFillReport(
        node_id=node.id,
        outcome="gap",
        proof=None,
        reason=f"Max repair rounds ({max_rounds}) reached without acceptance",
        rounds=max_rounds,
        repair_hints=repair_hints,
    )


# ── failure report ─────────────────────────────────────────────────────────────

def write_failure_report(report: ProofFillReport, reviews_dir: Path) -> Path:
    """Write a structured failure report under reviews_dir. Returns the report path."""
    reviews_dir.mkdir(parents=True, exist_ok=True)
    slug = report.node_id.replace(".", "_")
    ts = re.sub(r"[:\-T]", "_", report.timestamp)[:15]
    path = reviews_dir / f"{slug}_proof_fill_{ts}.md"
    lines = [
        "---",
        "agent: proof-fill",
        "target:",
        f"  node_id: {report.node_id}",
        f"decision: {report.outcome}",
        f'created_at: "{report.timestamp}"',
        "---",
        "",
        f"# Proof-Fill Report: {report.node_id}",
        "",
        f"**Outcome:** {report.outcome}  ",
        f"**Rounds:** {report.rounds}",
        "",
        "## Reason",
        "",
        report.reason,
        "",
    ]
    if report.repair_hints:
        lines += ["## Repair Hints", ""]
        for i, hint in enumerate(report.repair_hints, 1):
            lines += [f"### Round {i}", "", hint, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ── CLI runner ────────────────────────────────────────────────────────────────

def _make_claude_cli_runner(model: str = "claude-sonnet-4-6") -> CodexRunner:
    """Return a runner that calls the claude CLI subprocess."""
    def _run(prompt: str) -> str:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", model, "--output-format", "text"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    return _run


# ── CLI entry point ───────────────────────────────────────────────────────────

def _load_all_nodes(knowledge_root: Path) -> dict[str, Node]:
    nodes: dict[str, Node] = {}
    for subdir in ("nodes", "staged"):
        d = knowledge_root / subdir
        if d.exists():
            for node in scan_directory(d):
                nodes[node.id] = node
    return nodes


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Fill a small proof gap in a knowledge node.")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--node-id", help="Node id to fill proof for")
    group.add_argument("--node-path", type=Path, help="Path to the node Markdown file")
    ap.add_argument(
        "--knowledge-root", type=Path, default=Path("docs/knowledge"),
        help="Knowledge root directory (default: docs/knowledge)",
    )
    ap.add_argument("--max-rounds", type=int, default=2, help="Max repair rounds (default: 2)")
    ap.add_argument("--dry-run", action="store_true", help="Do not write back to node file")
    ap.add_argument(
        "--reviews-dir", type=Path,
        help="Directory for failure reports (default: <knowledge-root>/reviews)",
    )
    ap.add_argument("--model", default="claude-sonnet-4-6", help="Claude model to use")
    args = ap.parse_args(argv)

    knowledge_root: Path = args.knowledge_root
    reviews_dir: Path = args.reviews_dir or (knowledge_root / "reviews")

    all_nodes = _load_all_nodes(knowledge_root)

    if args.node_id:
        node = all_nodes.get(args.node_id)
        if node is None:
            print(f"Error: node {args.node_id!r} not found in {knowledge_root}", file=sys.stderr)
            sys.exit(1)
    else:
        from tools.knowledge.parser import parse_file
        node = parse_file(args.node_path)
        if node.id not in all_nodes:
            all_nodes[node.id] = node

    runner = _make_claude_cli_runner(model=args.model)
    report = run_proof_fill(
        node,
        all_nodes,
        generator=runner,
        verifier=runner,
        max_rounds=args.max_rounds,
        dry_run=args.dry_run,
    )

    if report.outcome == "accepted":
        action = "dry-run, no write" if args.dry_run else "written to node"
        print(f"Proof accepted (round {report.rounds}, {action})")
        snippet = (report.proof or "")[:80]
        if len(report.proof or "") > 80:
            snippet += "..."
        print(f"  {snippet}")
    else:
        report_path = write_failure_report(report, reviews_dir)
        print(f"Proof fill failed: {report.outcome} (round {report.rounds})", file=sys.stderr)
        print(f"  {report.reason}", file=sys.stderr)
        print(f"  Report: {report_path}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
