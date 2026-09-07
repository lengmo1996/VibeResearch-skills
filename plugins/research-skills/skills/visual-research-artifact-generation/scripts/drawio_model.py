#!/usr/bin/env python3
"""Standard-library model and serializer for editable Draw.io research diagrams."""

from __future__ import annotations

import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


VALID_LAYOUTS = {"horizontal", "vertical", "grid", "manual"}
DEFAULT_NODE_WIDTH = 160.0
DEFAULT_NODE_HEIGHT = 64.0
DEFAULT_CONTAINER_WIDTH = 360.0
DEFAULT_CONTAINER_HEIGHT = 240.0


class SpecError(ValueError):
    """Raised when a normalized diagram specification is invalid."""


def _number(value: Any, field_name: str, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpecError(f"{field_name} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise SpecError(f"{field_name} must be finite")
    return result


def _positive(value: Any, field_name: str, default: float) -> float:
    result = _number(value, field_name, default)
    if result <= 0:
        raise SpecError(f"{field_name} must be positive")
    return result


def _stable_id(prefix: str, parts: list[str], index: int) -> str:
    seed = "\x1f".join(parts + [str(index)])
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _clean_id(value: Any, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise SpecError(f"{field_name} must not be empty")
    if text in {"0", "1"}:
        raise SpecError(f"{field_name} uses a reserved Draw.io ID: {text}")
    return text


@dataclass
class Node:
    id: str
    label: str
    kind: str = "default"
    parent: str | None = None
    container: bool = False
    x: float | None = None
    y: float | None = None
    width: float = DEFAULT_NODE_WIDTH
    height: float = DEFAULT_NODE_HEIGHT
    style: str | None = None


@dataclass
class Edge:
    id: str
    source: str
    target: str
    label: str = ""
    kind: str = "default"
    directed: bool | None = None
    style: str | None = None


@dataclass
class DiagramSpec:
    title: str
    nodes: list[Node]
    edges: list[Edge] = field(default_factory=list)
    layout: str = "horizontal"
    theme: str = "paper-light"
    directed: bool = True
    page_width: float = 1169.0
    page_height: float = 827.0


def load_spec(path: Path) -> DiagramSpec:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SpecError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SpecError("top-level JSON value must be an object")
    return spec_from_mapping(data)


def spec_from_mapping(data: dict[str, Any]) -> DiagramSpec:
    title = str(data.get("title", "Research visual")).strip() or "Research visual"
    layout = str(data.get("layout", "horizontal")).strip().lower()
    if layout not in VALID_LAYOUTS:
        raise SpecError(f"layout must be one of: {', '.join(sorted(VALID_LAYOUTS))}")
    theme = str(data.get("theme", "paper-light")).strip() or "paper-light"
    directed = data.get("directed", True)
    if not isinstance(directed, bool):
        raise SpecError("directed must be true or false")

    page = data.get("page", {})
    if page is None:
        page = {}
    if not isinstance(page, dict):
        raise SpecError("page must be an object")

    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise SpecError("nodes must be a non-empty list")

    nodes: list[Node] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            raise SpecError(f"nodes[{index}] must be an object")
        label = str(raw.get("label", "")).strip()
        node_id = (
            _clean_id(raw["id"], f"nodes[{index}].id")
            if "id" in raw
            else _stable_id("node", [label], index)
        )
        if node_id in seen:
            raise SpecError(f"duplicate node ID: {node_id}")
        seen.add(node_id)
        container = raw.get("container", False)
        if not isinstance(container, bool):
            raise SpecError(f"nodes[{index}].container must be true or false")
        parent = raw.get("parent")
        if parent is not None:
            parent = _clean_id(parent, f"nodes[{index}].parent")
        width_default = DEFAULT_CONTAINER_WIDTH if container else DEFAULT_NODE_WIDTH
        height_default = DEFAULT_CONTAINER_HEIGHT if container else DEFAULT_NODE_HEIGHT
        nodes.append(
            Node(
                id=node_id,
                label=label,
                kind=str(raw.get("kind", "group" if container else "default")).strip()
                or "default",
                parent=parent,
                container=container,
                x=_number(raw.get("x"), f"nodes[{index}].x", 0.0)
                if "x" in raw
                else None,
                y=_number(raw.get("y"), f"nodes[{index}].y", 0.0)
                if "y" in raw
                else None,
                width=_positive(raw.get("width"), f"nodes[{index}].width", width_default),
                height=_positive(raw.get("height"), f"nodes[{index}].height", height_default),
                style=str(raw["style"]).strip() if raw.get("style") else None,
            )
        )

    node_by_id = {node.id: node for node in nodes}
    for node in nodes:
        if node.parent is None:
            continue
        if node.parent not in node_by_id:
            raise SpecError(f"node {node.id} references missing parent {node.parent}")
        if not node_by_id[node.parent].container:
            raise SpecError(f"node {node.id} parent {node.parent} is not a container")
        if node.parent == node.id:
            raise SpecError(f"node {node.id} cannot parent itself")
    for node in nodes:
        chain: set[str] = set()
        cursor = node
        while cursor.parent is not None:
            if cursor.id in chain:
                cycle = " -> ".join(sorted(chain | {cursor.id}))
                raise SpecError(f"container parent cycle detected: {cycle}")
            chain.add(cursor.id)
            cursor = node_by_id[cursor.parent]

    raw_edges = data.get("edges", [])
    if not isinstance(raw_edges, list):
        raise SpecError("edges must be a list")
    edges: list[Edge] = []
    edge_ids: set[str] = set()
    for index, raw in enumerate(raw_edges):
        if not isinstance(raw, dict):
            raise SpecError(f"edges[{index}] must be an object")
        if "source" not in raw or "target" not in raw:
            raise SpecError(f"edges[{index}] requires source and target")
        source = _clean_id(raw["source"], f"edges[{index}].source")
        target = _clean_id(raw["target"], f"edges[{index}].target")
        if source not in node_by_id or target not in node_by_id:
            raise SpecError(f"edge {index} references a missing source or target")
        label = str(raw.get("label", "")).strip()
        edge_id = (
            _clean_id(raw["id"], f"edges[{index}].id")
            if "id" in raw
            else _stable_id("edge", [source, target, label], index)
        )
        if edge_id in edge_ids or edge_id in seen:
            raise SpecError(f"duplicate Draw.io cell ID: {edge_id}")
        edge_ids.add(edge_id)
        edge_directed = raw.get("directed")
        if edge_directed is not None and not isinstance(edge_directed, bool):
            raise SpecError(f"edges[{index}].directed must be true or false")
        edges.append(
            Edge(
                id=edge_id,
                source=source,
                target=target,
                label=label,
                kind=str(raw.get("kind", "default")).strip() or "default",
                directed=edge_directed,
                style=str(raw["style"]).strip() if raw.get("style") else None,
            )
        )

    return DiagramSpec(
        title=title,
        nodes=nodes,
        edges=edges,
        layout=layout,
        theme=theme,
        directed=directed,
        page_width=_positive(page.get("width"), "page.width", 1169.0),
        page_height=_positive(page.get("height"), "page.height", 827.0),
    )


def load_presets(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecError(f"cannot read style presets: {exc}") from exc
    if not isinstance(data, dict) or not data:
        raise SpecError("style presets must be a non-empty object")
    return data


def _rank_nodes(nodes: list[Node], edges: list[Edge]) -> dict[str, int]:
    ids = {node.id for node in nodes}
    incoming = {node_id: 0 for node_id in ids}
    outgoing = {node_id: [] for node_id in ids}
    for edge in edges:
        if edge.source in ids and edge.target in ids and edge.source != edge.target:
            outgoing[edge.source].append(edge.target)
            incoming[edge.target] += 1
    queue = sorted(node_id for node_id, count in incoming.items() if count == 0)
    rank = {node_id: 0 for node_id in queue}
    visited: set[str] = set()
    while queue:
        node_id = queue.pop(0)
        visited.add(node_id)
        for target in sorted(outgoing[node_id]):
            rank[target] = max(rank.get(target, 0), rank[node_id] + 1)
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
                queue.sort()
    fallback = max(rank.values(), default=-1) + 1
    for node_id in sorted(ids - visited):
        rank[node_id] = fallback
    return rank


def apply_layout(spec: DiagramSpec) -> None:
    root_nodes = [node for node in spec.nodes if node.parent is None]
    if spec.layout == "grid":
        columns = max(1, math.ceil(math.sqrt(len(root_nodes))))
        for index, node in enumerate(root_nodes):
            if node.x is None:
                node.x = 60.0 + (index % columns) * 230.0
            if node.y is None:
                node.y = 60.0 + (index // columns) * 150.0
    elif spec.layout in {"horizontal", "vertical"}:
        root_ids = {node.id for node in root_nodes}
        root_edges = [
            edge for edge in spec.edges if edge.source in root_ids and edge.target in root_ids
        ]
        ranks = _rank_nodes(root_nodes, root_edges)
        grouped: dict[int, list[Node]] = {}
        for node in root_nodes:
            grouped.setdefault(ranks[node.id], []).append(node)
        for rank, level in sorted(grouped.items()):
            for order, node in enumerate(sorted(level, key=lambda item: item.id)):
                if spec.layout == "horizontal":
                    if node.x is None:
                        node.x = 60.0 + rank * 260.0
                    if node.y is None:
                        node.y = 60.0 + order * 150.0
                else:
                    if node.x is None:
                        node.x = 60.0 + order * 230.0
                    if node.y is None:
                        node.y = 60.0 + rank * 150.0
    else:
        for index, node in enumerate(root_nodes):
            if node.x is None:
                node.x = 60.0 + (index % 4) * 230.0
            if node.y is None:
                node.y = 60.0 + (index // 4) * 150.0

    children: dict[str, list[Node]] = {}
    for node in spec.nodes:
        if node.parent is not None:
            children.setdefault(node.parent, []).append(node)
    for parent_id, items in children.items():
        columns = max(1, math.ceil(math.sqrt(len(items))))
        for index, node in enumerate(sorted(items, key=lambda item: item.id)):
            if node.x is None:
                node.x = 24.0 + (index % columns) * 170.0
            if node.y is None:
                node.y = 48.0 + (index // columns) * 92.0


def _directed_style(style: str, directed: bool) -> str:
    if directed:
        return style
    style = re.sub(r"endArrow=[^;]*;", "", style)
    style = re.sub(r"endFill=[^;]*;", "", style)
    return style + "endArrow=none;"


def build_tree(spec: DiagramSpec, presets: dict[str, Any]) -> ET.Element:
    if spec.theme not in presets:
        raise SpecError(f"unknown theme {spec.theme!r}; available: {', '.join(sorted(presets))}")
    theme = presets[spec.theme]
    node_styles = theme.get("node_styles", {})
    edge_styles = theme.get("edge_styles", {})
    if "default" not in node_styles or "default" not in edge_styles:
        raise SpecError(f"theme {spec.theme!r} requires default node and edge styles")

    apply_layout(spec)
    mxfile = ET.Element("mxfile", {"host": "app.diagrams.net"})
    diagram_id = _stable_id("diagram", [spec.title], 0)
    diagram = ET.SubElement(mxfile, "diagram", {"id": diagram_id, "name": "Page-1"})
    model = ET.SubElement(
        diagram,
        "mxGraphModel",
        {
            "grid": "1",
            "gridSize": "10",
            "guides": "1",
            "tooltips": "1",
            "connect": "1",
            "arrows": "1",
            "fold": "1",
            "page": "1",
            "pageScale": "1",
            "pageWidth": _format_number(spec.page_width),
            "pageHeight": _format_number(spec.page_height),
            "math": "1",
            "shadow": "0",
        },
    )
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})

    containers = [node for node in spec.nodes if node.container]
    regular = [node for node in spec.nodes if not node.container]
    for node in containers + regular:
        style = node.style or node_styles.get(node.kind, node_styles["default"])
        if node.container and node.style is None:
            style = node_styles.get("group", style)
        cell = ET.SubElement(
            root,
            "mxCell",
            {
                "id": node.id,
                "value": node.label,
                "style": style,
                "vertex": "1",
                "parent": node.parent or "1",
            },
        )
        ET.SubElement(
            cell,
            "mxGeometry",
            {
                "x": _format_number(node.x or 0.0),
                "y": _format_number(node.y or 0.0),
                "width": _format_number(node.width),
                "height": _format_number(node.height),
                "as": "geometry",
            },
        )

    for edge in spec.edges:
        directed = spec.directed if edge.directed is None else edge.directed
        style = edge.style or edge_styles.get(edge.kind, edge_styles["default"])
        style = _directed_style(style, directed)
        cell = ET.SubElement(
            root,
            "mxCell",
            {
                "id": edge.id,
                "value": edge.label,
                "style": style,
                "edge": "1",
                "parent": "1",
                "source": edge.source,
                "target": edge.target,
            },
        )
        ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
    return mxfile


def _format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.3f}".rstrip("0").rstrip(".")


def serialize(tree: ET.Element) -> bytes:
    ET.indent(tree, space="  ")
    return ET.tostring(tree, encoding="utf-8", xml_declaration=True)
