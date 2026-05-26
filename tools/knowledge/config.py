"""Project-level configuration for mdblueprint knowledge roots."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from tools.knowledge.latex_check import KNOWN_MACROS
from tools.knowledge.models import SourceLibraryEntry


DEFAULT_CONFIG_NAME = "mdblueprint.yml"
DEFAULT_DISPLAY_DELIMITERS = ((r"$$", r"$$"), (r"\[", r"\]"))
DEFAULT_INLINE_DELIMITERS = ((r"$", r"$"), (r"\(", r"\)"))
DEFAULT_GRAPH_MAX_VISIBLE_NODES = 120
DEFAULT_GRAPH_MAX_EXPAND_NODES = 80
# Matched to the browser-side renderer's maxExpandNodes (see graph.js:39-40)
# so that any subgraph that Python emits as flat can actually render in the
# browser. Mismatch causes pages with 81-100 internal nodes to silently fall
# back to an "oversized topic" text placeholder instead of drawing the DAG.
DEFAULT_GRAPH_MAX_PAGE_TOTAL = 80
DEFAULT_GRAPH_INLINE_CHILD_MAX_SIZE = 8
DEFAULT_GRAPH_PROOF_PLANS = "selected-only"
GRAPH_PROOF_PLAN_POLICIES = {"hidden", "selected-only", "all"}


@dataclass(frozen=True)
class SiteConfig:
    title: str
    short_title: str | None = None


@dataclass(frozen=True)
class MathConfig:
    macros: dict[str, str]
    inline_delimiters: list[tuple[str, str]]
    display_delimiters: list[tuple[str, str]]
    throw_on_error: bool = False


@dataclass(frozen=True)
class LeanRepositoryConfig:
    id: str
    title: str
    local_path: Path
    web_url: str
    source_url_template: str
    revision: str
    # Optional subdirectory of the git repo where `local_path` lives.
    # When set, prepended to the relative path passed to
    # `source_url_template` so users with `local_path: ../../lean` in
    # a repo with `lean/` subdir don't have to hardcode the prefix.
    # Default empty -> nothing prepended (back-compat).
    subdir: str = ""
    # Optional template for the hosted doc-gen4 / mathlib4_docs page
    # corresponding to a declaration. Available placeholders:
    #   {web_url}, {revision}      — repository identification
    #   {module}                   — dotted module name (Foo.Bar.Baz)
    #   {module_html}              — slash form (Foo/Bar/Baz)
    #   {qualified_name}           — full Lean declaration name
    # When set, each resolved declaration in the rendered modal gets
    # a second "doc" link next to the source link. Empty -> no doc
    # link rendered (default).
    doc_url_template: str = ""


@dataclass(frozen=True)
class LeanConfig:
    default_repository: str | None
    repositories: dict[str, LeanRepositoryConfig]


@dataclass(frozen=True)
class GraphDisplayConfig:
    max_visible_nodes: int
    max_expand_nodes: int
    proof_plans: str
    max_page_total: int = DEFAULT_GRAPH_MAX_PAGE_TOTAL
    inline_child_max_size: int = DEFAULT_GRAPH_INLINE_CHILD_MAX_SIZE


@dataclass(frozen=True)
class SourcesConfig:
    library: dict[str, SourceLibraryEntry] = field(default_factory=dict)
    require_source_spans: bool = False


@dataclass(frozen=True)
class LintConfig:
    fuzzy_threshold: float = 0.92
    semantic_candidate_threshold: float = 0.75
    plan_promote_severity: str = "info"
    hierarchy_inversion_severity: str = "warning"
    # Project-level Lean module root → blueprint topic root override.
    # Use when a Lean module belongs (per project organization) to a
    # different blueprint topic than its module name suggests. E.g.
    # {"linear_algebra": "linear_programming"} declares that nodes whose
    # Lean lives in EconCSLib.LinearAlgebra.* should be aligned with
    # blueprint root "linear_programming". Merged on top of the built-in
    # plural/singular table (config wins on conflicts).
    topic_lean_aliases: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TopicConfig:
    id: str
    title: str
    aliases: tuple[str, ...] = field(default_factory=())


@dataclass(frozen=True)
class ProjectConfig:
    site: SiteConfig
    math: MathConfig
    lean: LeanConfig
    graph: GraphDisplayConfig
    topics: tuple[TopicConfig, ...] = field(default_factory=())
    sources: SourcesConfig = field(default_factory=SourcesConfig)
    lint: LintConfig = field(default_factory=LintConfig)


def _titleize_path_name(name: str) -> str:
    cleaned = name.strip().replace("_", " ").replace("-", " ")
    if not cleaned or cleaned.lower() in {"docs", "knowledge"}:
        return "Blueprint"
    return cleaned.title()


def _fallback_config(knowledge_root: Path) -> ProjectConfig:
    return ProjectConfig(
        site=SiteConfig(title=_titleize_path_name(knowledge_root.name)),
        math=_default_math_config(),
        lean=_default_lean_config(),
        graph=_default_graph_config(),
        topics=(),
        lint=LintConfig(),
    )


def _default_math_config() -> MathConfig:
    return MathConfig(
        macros={},
        inline_delimiters=list(DEFAULT_INLINE_DELIMITERS),
        display_delimiters=list(DEFAULT_DISPLAY_DELIMITERS),
        throw_on_error=False,
    )


def _default_lean_config() -> LeanConfig:
    return LeanConfig(default_repository=None, repositories={})


def _default_graph_config() -> GraphDisplayConfig:
    return GraphDisplayConfig(
        max_visible_nodes=DEFAULT_GRAPH_MAX_VISIBLE_NODES,
        max_expand_nodes=DEFAULT_GRAPH_MAX_EXPAND_NODES,
        proof_plans=DEFAULT_GRAPH_PROOF_PLANS,
        max_page_total=DEFAULT_GRAPH_MAX_PAGE_TOTAL,
        inline_child_max_size=DEFAULT_GRAPH_INLINE_CHILD_MAX_SIZE,
    )


def _parse_positive_int(raw: Any, *, path: Path, field: str, default: int) -> int:
    if raw is None:
        return default
    if not isinstance(raw, int) or isinstance(raw, bool) or raw <= 0:
        raise ValueError(f"Project config graph.{field} must be a positive integer: {path}")
    return raw


def _parse_graph_config(raw: Any, *, path: Path) -> GraphDisplayConfig:
    if raw is None:
        return _default_graph_config()
    if not isinstance(raw, dict):
        raise ValueError(f"Project config graph must be a mapping: {path}")

    proof_plans = raw.get("proof_plans", DEFAULT_GRAPH_PROOF_PLANS)
    if not isinstance(proof_plans, str) or proof_plans.strip() not in GRAPH_PROOF_PLAN_POLICIES:
        allowed = ", ".join(sorted(GRAPH_PROOF_PLAN_POLICIES))
        raise ValueError(f"Project config graph.proof_plans must be one of {allowed}: {path}")

    return GraphDisplayConfig(
        max_visible_nodes=_parse_positive_int(
            raw.get("max_visible_nodes"),
            path=path,
            field="max_visible_nodes",
            default=DEFAULT_GRAPH_MAX_VISIBLE_NODES,
        ),
        max_expand_nodes=_parse_positive_int(
            raw.get("max_expand_nodes"),
            path=path,
            field="max_expand_nodes",
            default=DEFAULT_GRAPH_MAX_EXPAND_NODES,
        ),
        proof_plans=proof_plans.strip(),
        max_page_total=_parse_positive_int(
            raw.get("max_page_total"),
            path=path,
            field="max_page_total",
            default=DEFAULT_GRAPH_MAX_PAGE_TOTAL,
        ),
        inline_child_max_size=_parse_positive_int(
            raw.get("inline_child_max_size"),
            path=path,
            field="inline_child_max_size",
            default=DEFAULT_GRAPH_INLINE_CHILD_MAX_SIZE,
        ),
    )


def _parse_delimiters(raw: Any, *, path: Path, field: str, default: tuple[tuple[str, str], ...]) -> list[tuple[str, str]]:
    if raw is None:
        return list(default)
    if not isinstance(raw, list):
        raise ValueError(f"Project config math.delimiters.{field} must be a list: {path}")

    pairs: list[tuple[str, str]] = []
    for item in raw:
        if (
            not isinstance(item, list | tuple)
            or len(item) != 2
            or not all(isinstance(value, str) and value for value in item)
        ):
            raise ValueError(f"Project config math.delimiters.{field} entries must be two non-empty strings: {path}")
        pairs.append((item[0], item[1]))
    return pairs


def _parse_math_config(raw: Any, *, path: Path) -> MathConfig:
    if raw is None:
        return _default_math_config()
    if not isinstance(raw, dict):
        raise ValueError(f"Project config math must be a mapping: {path}")

    macros_raw = raw.get("macros", {})
    if not isinstance(macros_raw, dict):
        raise ValueError(f"Project config math.macros must be a mapping: {path}")
    macros: dict[str, str] = {}
    for name, expansion in macros_raw.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Project config math.macros keys must be non-empty strings: {path}")
        if not isinstance(expansion, str) or not expansion:
            raise ValueError(f"Project config math.macros values must be non-empty strings: {path}")
        macros[name.lstrip("\\").strip()] = expansion

    delimiters_raw = raw.get("delimiters", {})
    if delimiters_raw is None:
        delimiters_raw = {}
    if not isinstance(delimiters_raw, dict):
        raise ValueError(f"Project config math.delimiters must be a mapping: {path}")

    throw_on_error = raw.get("throw_on_error", False)
    if not isinstance(throw_on_error, bool):
        raise ValueError(f"Project config math.throw_on_error must be a boolean: {path}")

    return MathConfig(
        macros=macros,
        inline_delimiters=_parse_delimiters(
            delimiters_raw.get("inline"),
            path=path,
            field="inline",
            default=DEFAULT_INLINE_DELIMITERS,
        ),
        display_delimiters=_parse_delimiters(
            delimiters_raw.get("display"),
            path=path,
            field="display",
            default=DEFAULT_DISPLAY_DELIMITERS,
        ),
        throw_on_error=throw_on_error,
    )


def katex_auto_render_options(math: MathConfig) -> dict[str, Any]:
    delimiters = [
        {"left": left, "right": right, "display": True}
        for left, right in math.display_delimiters
    ] + [
        {"left": left, "right": right, "display": False}
        for left, right in math.inline_delimiters
    ]
    # Lift the backslash out of the f-string expression so this parses on
    # Python 3.11 (PEP 701, which permits backslashes inside f-string
    # expressions, only landed in 3.12). pyproject targets >=3.10.
    _bs = "\\"
    custom_macros = {
        f"\\{name.lstrip(_bs)}": expansion
        for name, expansion in sorted(math.macros.items())
        if name.lstrip(_bs) not in KNOWN_MACROS
    }
    return {
        "delimiters": delimiters,
        "throwOnError": math.throw_on_error,
        "macros": custom_macros,
    }


def _required_str(raw: dict[str, Any], key: str, *, path: Path, prefix: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Project config requires {prefix}.{key}: {path}")
    return value.strip()


def _resolve_local_path(value: str, *, config_path: Path) -> Path:
    local_path = Path(value).expanduser()
    if not local_path.is_absolute():
        local_path = config_path.parent / local_path
    return local_path.resolve()


def _resolve_revision(local_path: Path, revision: str, *, path: Path, prefix: str) -> str:
    if revision != "auto":
        return revision
    try:
        return subprocess.check_output(
            ["git", "-C", str(local_path), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"Project config {prefix}.revision=auto requires a Git repository: {path}") from exc


def _parse_lean_config(raw: Any, *, path: Path) -> LeanConfig:
    if raw is None:
        return _default_lean_config()
    if not isinstance(raw, dict):
        raise ValueError(f"Project config lean must be a mapping: {path}")

    default_repository = raw.get("default_repository")
    if default_repository is not None and (not isinstance(default_repository, str) or not default_repository.strip()):
        raise ValueError(f"Project config lean.default_repository must be a non-empty string: {path}")
    if isinstance(default_repository, str):
        default_repository = default_repository.strip()

    repositories_raw = raw.get("repositories", [])
    if not isinstance(repositories_raw, list):
        raise ValueError(f"Project config lean.repositories must be a list: {path}")

    repositories: dict[str, LeanRepositoryConfig] = {}
    for index, repo_raw in enumerate(repositories_raw):
        prefix = f"lean.repositories[{index}]"
        if not isinstance(repo_raw, dict):
            raise ValueError(f"Project config {prefix} must be a mapping: {path}")

        repo_id = _required_str(repo_raw, "id", path=path, prefix=prefix)
        title = _required_str(repo_raw, "title", path=path, prefix=prefix)
        local_path_raw = _required_str(repo_raw, "local_path", path=path, prefix=prefix)
        web_url = _required_str(repo_raw, "web_url", path=path, prefix=prefix)
        source_url_template = _required_str(repo_raw, "source_url_template", path=path, prefix=prefix)
        revision_raw = _required_str(repo_raw, "revision", path=path, prefix=prefix)
        local_path = _resolve_local_path(local_path_raw, config_path=path)
        subdir_raw = repo_raw.get("subdir", "")
        if subdir_raw is None:
            subdir = ""
        elif isinstance(subdir_raw, str):
            subdir = subdir_raw.strip().strip("/")
        else:
            raise ValueError(f"Project config {prefix}.subdir must be a string: {path}")
        doc_url_template_raw = repo_raw.get("doc_url_template", "")
        if doc_url_template_raw is None:
            doc_url_template = ""
        elif isinstance(doc_url_template_raw, str):
            doc_url_template = doc_url_template_raw.strip()
        else:
            raise ValueError(
                f"Project config {prefix}.doc_url_template must be a string: {path}"
            )

        if not local_path.is_dir():
            raise ValueError(f"Project config {prefix}.local_path does not exist: {local_path}")
        if repo_id in repositories:
            raise ValueError(f"Project config duplicate Lean repository id {repo_id!r}: {path}")

        repositories[repo_id] = LeanRepositoryConfig(
            id=repo_id,
            title=title,
            local_path=local_path,
            web_url=web_url,
            source_url_template=source_url_template,
            revision=_resolve_revision(local_path, revision_raw, path=path, prefix=prefix),
            subdir=subdir,
            doc_url_template=doc_url_template,
        )

    if default_repository is not None and default_repository not in repositories:
        raise ValueError(f"Project config lean.default_repository is not listed in lean.repositories: {default_repository!r}")

    return LeanConfig(default_repository=default_repository, repositories=repositories)


def _parse_topics_config(raw: Any, *, path: Path) -> tuple[TopicConfig, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"Project config topics must be a list: {path}")
    topics: list[TopicConfig] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw):
        prefix = f"topics[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"Project config {prefix} must be a mapping: {path}")
        topic_id = _required_str(item, "id", path=path, prefix=prefix)
        if topic_id in seen_ids:
            raise ValueError(f"Project config duplicate topic id {topic_id!r}: {path}")
        seen_ids.add(topic_id)
        title = _required_str(item, "title", path=path, prefix=prefix)
        aliases_raw = item.get("aliases")
        aliases: tuple[str, ...] = ()
        if aliases_raw is not None:
            if not isinstance(aliases_raw, list):
                raise ValueError(f"Project config {prefix}.aliases must be a list: {path}")
            aliases = tuple(
                str(a).strip() for a in aliases_raw
                if isinstance(a, str) and a.strip()
            )
        topics.append(TopicConfig(id=topic_id, title=title, aliases=aliases))
    return tuple(topics)


def _parse_sources_config(raw: Any, *, path: Path) -> SourcesConfig:
    if raw is None:
        return SourcesConfig()
    if not isinstance(raw, dict):
        raise ValueError(f"Project config sources must be a mapping: {path}")

    library_raw = raw.get("library", [])
    if not isinstance(library_raw, list):
        raise ValueError(f"Project config sources.library must be a list: {path}")

    library: dict[str, SourceLibraryEntry] = {}
    for index, item in enumerate(library_raw):
        prefix = f"sources.library[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"Project config {prefix} must be a mapping: {path}")
        entry_id = _required_str(item, "id", path=path, prefix=prefix)
        if entry_id in library:
            raise ValueError(f"Project config duplicate source library id {entry_id!r}: {path}")
        entry_title = _required_str(item, "title", path=path, prefix=prefix)
        short = item.get("short")
        if short is not None and (not isinstance(short, str) or not short.strip()):
            raise ValueError(f"Project config {prefix}.short must be a non-empty string: {path}")
        authors = item.get("authors")
        if authors is not None and (not isinstance(authors, str) or not authors.strip()):
            raise ValueError(f"Project config {prefix}.authors must be a non-empty string: {path}")
        entry_path = item.get("path")
        if entry_path is not None and (not isinstance(entry_path, str) or not entry_path.strip()):
            raise ValueError(f"Project config {prefix}.path must be a non-empty string: {path}")
        library[entry_id] = SourceLibraryEntry(
            id=entry_id,
            title=entry_title,
            short=short.strip() if short else None,
            authors=authors.strip() if authors else None,
            path=entry_path.strip() if entry_path else None,
        )

    require_source_spans = raw.get("require_source_spans", False)
    if not isinstance(require_source_spans, bool):
        raise ValueError(f"Project config sources.require_source_spans must be a boolean: {path}")
    return SourcesConfig(library=library, require_source_spans=require_source_spans)


def _parse_unit_interval(value: Any, *, path: Path, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(
            f"Project config lint.{field} must be a number between 0 and 1: {path}"
        )
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(
            f"Project config lint.{field} must be between 0 and 1, got {value}: {path}"
        )
    return value


def _parse_lint_config(raw: Any, *, path: Path) -> LintConfig:
    if raw is None:
        return LintConfig()
    if not isinstance(raw, dict):
        raise ValueError(f"Project config lint must be a mapping: {path}")

    fuzzy_threshold = _parse_unit_interval(
        raw.get("fuzzy_threshold", 0.92),
        path=path,
        field="fuzzy_threshold",
    )
    semantic_candidate_threshold = _parse_unit_interval(
        raw.get("semantic_candidate_threshold", 0.75),
        path=path,
        field="semantic_candidate_threshold",
    )
    severity = raw.get("plan_promote_severity", "info")
    if severity not in {"info", "warning"}:
        raise ValueError(
            f"Project config lint.plan_promote_severity must be 'info' or 'warning', "
            f"got {severity!r}: {path}"
        )
    hierarchy_severity = raw.get("hierarchy_inversion_severity", "warning")
    if hierarchy_severity not in {"info", "warning"}:
        raise ValueError(
            f"Project config lint.hierarchy_inversion_severity must be 'info' or 'warning', "
            f"got {hierarchy_severity!r}: {path}"
        )

    aliases_raw = raw.get("topic_lean_aliases", {})
    if aliases_raw is None:
        aliases: dict[str, str] = {}
    elif not isinstance(aliases_raw, dict):
        raise ValueError(
            f"Project config lint.topic_lean_aliases must be a mapping: {path}"
        )
    else:
        aliases = {}
        for key, value in aliases_raw.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError(
                    f"Project config lint.topic_lean_aliases keys and values "
                    f"must be strings: {path}"
                )
            aliases[key] = value

    return LintConfig(
        fuzzy_threshold=fuzzy_threshold,
        semantic_candidate_threshold=semantic_candidate_threshold,
        plan_promote_severity=severity,
        hierarchy_inversion_severity=hierarchy_severity,
        topic_lean_aliases=aliases,
    )


def load_project_config(knowledge_root: Path, config_path: Path | None = None) -> ProjectConfig:
    path = config_path if config_path is not None else knowledge_root / DEFAULT_CONFIG_NAME
    if not path.exists():
        if config_path is not None:
            raise FileNotFoundError(f"Project config not found: {path}")
        return _fallback_config(knowledge_root)

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Project config must be a mapping: {path}")

    site_raw = raw.get("site")
    if not isinstance(site_raw, dict):
        raise ValueError(f"Project config requires a site mapping: {path}")

    title = site_raw.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError(f"Project config requires site.title: {path}")

    short_title = site_raw.get("short_title")
    if short_title is not None:
        if not isinstance(short_title, str) or not short_title.strip():
            raise ValueError(f"Project config site.short_title must be a non-empty string: {path}")
        short_title = short_title.strip()

    return ProjectConfig(
        site=SiteConfig(title=title.strip(), short_title=short_title),
        math=_parse_math_config(raw.get("math"), path=path),
        lean=_parse_lean_config(raw.get("lean"), path=path),
        graph=_parse_graph_config(raw.get("graph"), path=path),
        topics=_parse_topics_config(raw.get("topics"), path=path),
        sources=_parse_sources_config(raw.get("sources"), path=path),
        lint=_parse_lint_config(raw.get("lint"), path=path),
    )
