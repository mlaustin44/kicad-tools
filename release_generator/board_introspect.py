"""Parse .kicad_pcb S-expression for stackup, dimensions, layer info.

We parse only the fields we need rather than building a full data model.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import sexpdata


@dataclass
class StackupLayer:
    name: str
    type: str
    thickness_mm: float | None
    material: str | None


@dataclass
class BoardInfo:
    stackup: list[StackupLayer]
    enabled_layers: list[str]
    width_mm: float | None
    height_mm: float | None


def _find_first(node, key: str):
    """Return the first child sub-list whose head Symbol equals `key`."""
    for child in node[1:] if isinstance(node, list) else []:
        if isinstance(child, list) and child and isinstance(child[0], sexpdata.Symbol) \
                and child[0].value() == key:
            return child
    return None


def _find_all(node, key: str):
    out = []
    for child in node[1:] if isinstance(node, list) else []:
        if isinstance(child, list) and child and isinstance(child[0], sexpdata.Symbol) \
                and child[0].value() == key:
            out.append(child)
    return out


def _scalar(node, default=None):
    if node is None or len(node) < 2:
        return default
    return node[1]


def parse_board(pcb_path: Path) -> BoardInfo:
    text = pcb_path.read_text(encoding="utf-8")
    tree = sexpdata.loads(text)

    setup = _find_first(tree, "setup")
    stackup_node = _find_first(setup, "stackup") if setup else None
    layers: list[StackupLayer] = []
    if stackup_node:
        for layer in _find_all(stackup_node, "layer"):
            name = layer[1] if len(layer) > 1 else ""
            type_node = _find_first(layer, "type")
            thickness_node = _find_first(layer, "thickness")
            material_node = _find_first(layer, "material")
            layers.append(StackupLayer(
                name=str(name),
                type=str(_scalar(type_node, "")),
                thickness_mm=float(_scalar(thickness_node)) if thickness_node else None,
                material=str(_scalar(material_node)) if material_node else None,
            ))

    layers_def = _find_first(tree, "layers")
    enabled: list[str] = []
    if layers_def:
        for entry in layers_def[1:]:
            if isinstance(entry, list) and len(entry) >= 2:
                enabled.append(str(entry[1]))

    # Board dimensions: walk all gr_line/gr_arc/gr_rect on Edge.Cuts and bound the box.
    edge_xs: list[float] = []
    edge_ys: list[float] = []
    for child in tree[1:]:
        if not isinstance(child, list) or not child:
            continue
        head = child[0]
        if not isinstance(head, sexpdata.Symbol):
            continue
        if head.value() not in ("gr_line", "gr_arc", "gr_rect", "gr_circle"):
            continue
        layer_node = _find_first(child, "layer")
        if not layer_node or _scalar(layer_node) != "Edge.Cuts":
            continue
        for pt_key in ("start", "end", "center", "mid"):
            pt = _find_first(child, pt_key)
            if pt and len(pt) >= 3:
                edge_xs.append(float(pt[1]))
                edge_ys.append(float(pt[2]))

    width = (max(edge_xs) - min(edge_xs)) if edge_xs else None
    height = (max(edge_ys) - min(edge_ys)) if edge_ys else None

    return BoardInfo(stackup=layers, enabled_layers=enabled,
                     width_mm=width, height_mm=height)
