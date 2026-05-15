"""Project-level configuration for mdblueprint knowledge roots."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


DEFAULT_CONFIG_NAME = "mdblueprint.yml"


@dataclass(frozen=True)
class SiteConfig:
    title: str
    short_title: str | None = None


@dataclass(frozen=True)
class ProjectConfig:
    site: SiteConfig


def _titleize_path_name(name: str) -> str:
    cleaned = name.strip().replace("_", " ").replace("-", " ")
    if not cleaned or cleaned.lower() in {"docs", "knowledge"}:
        return "Blueprint"
    return cleaned.title()


def _fallback_config(knowledge_root: Path) -> ProjectConfig:
    return ProjectConfig(site=SiteConfig(title=_titleize_path_name(knowledge_root.name)))


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

    return ProjectConfig(site=SiteConfig(title=title.strip(), short_title=short_title))
