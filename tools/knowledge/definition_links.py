"""Deterministic, opt-in prose navigation; never adds proof dependencies."""
from __future__ import annotations

import hashlib
import posixpath
import re
from collections import Counter
from dataclasses import dataclass
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import yaml

from tools.knowledge.export import home_topic_for_node, leaf_topic_ids_for_node, topic_path, topic_prefixes
from tools.knowledge.models import Node

LinkTarget = tuple[str, str, str]  # node id, relative URL, definition title


def _term_key(term: str) -> str:
    return " ".join(term.split()).casefold()


class _PreservingParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.output: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.output.append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        self.output.append(f"</{tag}>")

    def handle_data(self, data):
        self.output.append(data)

    def handle_entityref(self, name):
        self.output.append(f"&{name};")

    def handle_charref(self, name):
        self.output.append(f"&#{name};")

    def handle_comment(self, data):
        self.output.append(f"<!--{data}-->")

    def handle_decl(self, decl):
        self.output.append(f"<!{decl}>")


class _DefinitionLinker(_PreservingParser):
    SKIP = {"a", "code", "pre", "script", "style", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self, aliases: dict[str, LinkTarget]):
        super().__init__()
        self.aliases = aliases
        alternatives = [
            r"\s+".join(re.escape(part) for part in term.split())
            for term in sorted(aliases, key=lambda t: (-len(t), t))
        ]
        self.pattern = re.compile(
            r"(?<!\w)(?:" + "|".join(alternatives) + r")(?!\w)", re.IGNORECASE,
        )
        self.skipped: Counter[str] = Counter()

    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag, attrs)
        if tag in self.SKIP:
            self.skipped[tag] += 1

    def handle_startendtag(self, tag, attrs):
        self.output.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        super().handle_endtag(tag)
        if self.skipped[tag]:
            self.skipped[tag] -= 1

    def handle_data(self, data):
        def replace(match):
            # IGNORECASE includes a few Unicode case equivalents whose
            # casefold differs; leave those unmatched rather than guessing.
            target = self.aliases.get(_term_key(match.group()))
            if target is None:
                return match.group()
            return (
                f'<a class="node-ref definition-ref" data-node-id="{escape(target[0], quote=True)}" '
                f'href="{escape(target[1], quote=True)}" title="Definition: {escape(target[2], quote=True)}">'
                f'{escape(match.group())}</a>'
            )

        self.output.append(data if any(self.skipped.values()) else self.pattern.sub(replace, data))


def link_definitions(html: str, aliases: dict[str, LinkTarget], math_pattern: re.Pattern) -> str:
    """Link whole prose terms, preserving math, code, headings and existing links."""
    if not aliases:
        return html
    protected: list[str] = []
    token = "MDBLUEPRINTDEFINITIONMASK"
    while token in html:
        token += "X"

    def protect(match):
        protected.append(match.group())
        return f"{token}{len(protected) - 1}END"

    masked = math_pattern.sub(protect, html)
    masked = re.sub(r"\[\[[^\]\n]+\]\]", protect, masked)
    parser = _DefinitionLinker(aliases)
    parser.feed(masked)
    parser.close()
    return re.sub(token + r"(\d+)END", lambda m: protected[int(m.group(1))], "".join(parser.output))


class _PayloadRebaser(_PreservingParser):
    ATTR_RE = re.compile(r'''(?<![\w:-])((?:href|src)\s*=\s*)(?:(["'])(.*?)\2|([^\s>]+))''', re.I)

    def __init__(self, topic: str):
        super().__init__()
        self.topic = topic

    def handle_starttag(self, tag, attrs):
        def replace(match):
            value = unescape(match.group(3) if match.group(2) else match.group(4))
            url = urlsplit(value)
            if url.scheme or url.netloc or not url.path or url.path.startswith("/"):
                return match.group()
            path = posixpath.normpath(posixpath.join(topic_path(self.topic), url.path))
            value = urlunsplit(("", "", path, url.query, url.fragment))
            return match.group(1) + '"' + escape(value, quote=True) + '"'

        self.output.append(self.ATTR_RE.sub(replace, self.get_starttag_text()))


def rebase_payload_links(html: str, topic: str) -> str:
    """Graph details are rooted at the site root, unlike their node pages."""
    parser = _PayloadRebaser(topic)
    parser.feed(html)
    parser.close()
    return "".join(parser.output)


@dataclass(frozen=True)
class ConceptRule:
    node: str
    terms: tuple[str, ...]
    topics: tuple[str, ...] = ()


@dataclass
class DefinitionLinks:
    rules: tuple[ConceptRule, ...]
    nodes: dict[str, Node]
    registry_sha256: str | None = None

    @classmethod
    def load(cls, root: Path, nodes: list[Node]) -> "DefinitionLinks":
        by_id = {n.id: n for n in nodes}
        path = root / "concept-links.yml"
        if not path.exists():
            return cls((), by_id)
        raw = path.read_bytes()
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid concept-links.yml: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("concepts"), list):
            raise ValueError("concept-links.yml must contain a concepts list")
        topics = {topic for n in nodes for leaf in leaf_topic_ids_for_node(n) for topic in topic_prefixes(leaf)}
        rules = []
        for entry in data["concepts"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("node"), str):
                raise ValueError("Each concept entry must name a definition node")
            node = by_id.get(entry["node"])
            if node is None or node.kind != "definition":
                raise ValueError(f"Concept link must target a definition: {entry['node']}")
            terms = entry.get("terms")
            if not isinstance(terms, list) or not terms or any(not isinstance(t, str) or not t.strip() for t in terms):
                raise ValueError(f"Concept terms must be a nonempty list of nonempty alias strings: {node.id}")
            scope = entry.get("topics", [])
            if not isinstance(scope, list) or any(not isinstance(t, str) or t not in topics for t in scope):
                raise ValueError(f"Invalid concept-link topic scope: {scope!r}")
            rules.append(ConceptRule(node.id, tuple(terms), tuple(scope)))
        registry = cls(tuple(rules), by_id, hashlib.sha256(raw).hexdigest())
        # Fail before publishing can replace the previous output directory.
        for topic in sorted(topics):
            registry.aliases_for(topic)
        return registry

    def aliases_for(self, topic: str, current: str | None = None) -> dict[str, LinkTarget]:
        aliases: dict[str, LinkTarget] = {}
        for rule in self.rules:
            if rule.topics and topic not in rule.topics:
                continue
            node = self.nodes[rule.node]
            path = f"{topic_path(home_topic_for_node(node))}/{node.id.replace('.', '_')}.html"
            target = (node.id, posixpath.relpath(path, topic_path(topic)), node.title)
            for term in rule.terms:
                key = _term_key(term)
                if key in aliases and aliases[key] != target:
                    raise ValueError(f"Ambiguous concept alias {term!r} in topic {topic!r}")
                aliases[key] = target
        return {key: target for key, target in aliases.items() if target[0] != current}

    def render(self, html: str, topic: str, math_pattern: re.Pattern, current: str | None = None) -> str:
        return link_definitions(html, self.aliases_for(topic, current), math_pattern)

    def summary(self) -> dict:
        return {"engine": "Python registry matcher; no LLM calls", "registry_sha256": self.registry_sha256,
                "definition_targets": len({r.node for r in self.rules}), "aliases": sum(len(r.terms) for r in self.rules)}
