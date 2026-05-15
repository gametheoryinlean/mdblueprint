"""Project-level configuration for mdblueprint knowledge roots."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_NAME = "mdblueprint.yml"
DEFAULT_DISPLAY_DELIMITERS = ((r"$$", r"$$"), (r"\[", r"\]"))
DEFAULT_INLINE_DELIMITERS = ((r"$", r"$"), (r"\(", r"\)"))


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
class ProjectConfig:
    site: SiteConfig
    math: MathConfig


def _titleize_path_name(name: str) -> str:
    cleaned = name.strip().replace("_", " ").replace("-", " ")
    if not cleaned or cleaned.lower() in {"docs", "knowledge"}:
        return "Blueprint"
    return cleaned.title()


def _fallback_config(knowledge_root: Path) -> ProjectConfig:
    return ProjectConfig(
        site=SiteConfig(title=_titleize_path_name(knowledge_root.name)),
        math=_default_math_config(),
    )


def _default_math_config() -> MathConfig:
    return MathConfig(
        macros={},
        inline_delimiters=list(DEFAULT_INLINE_DELIMITERS),
        display_delimiters=list(DEFAULT_DISPLAY_DELIMITERS),
        throw_on_error=False,
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
    return {
        "delimiters": delimiters,
        "throwOnError": math.throw_on_error,
        "macros": {
            f"\\{name.lstrip('\\')}": expansion
            for name, expansion in sorted(math.macros.items())
        },
    }


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
    )
