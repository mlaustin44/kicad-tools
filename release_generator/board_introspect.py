"""Parse .kicad_pcb S-expression for stackup, dimensions, layer info.

We parse only the fields we need rather than building a full data model.
Design rules (min track, clearance, etc.) live in the sibling .kicad_pro
JSON, which we load opportunistically.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
import sexpdata


@dataclass
class StackupLayer:
    name: str
    type: str
    thickness_mm: float | None
    material: str | None
    color: str | None = None
    epsilon_r: float | None = None
    loss_tangent: float | None = None


@dataclass
class BoardInfo:
    stackup: list[StackupLayer]
    enabled_layers: list[str]
    width_mm: float | None
    height_mm: float | None
    copper_layer_count: int = 0
    board_thickness_mm: float | None = None
    min_trace_width_mm: float | None = None
    min_clearance_mm: float | None = None
    min_hole_size_mm: float | None = None
    min_annular_ring_mm: float | None = None
    copper_finish: str | None = None
    impedance_controlled: bool = False
    edge_plating: bool = False
    castellated_pads: bool = False
    edge_connector: str | None = None


def _sym_value(node):
    """Return the string value of a Symbol/str node, or '' otherwise."""
    if isinstance(node, sexpdata.Symbol):
        return node.value()
    if isinstance(node, str):
        return node
    return ""


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


def _as_bool(val) -> bool:
    """Interpret KiCad yes/no (Symbol or str) as a boolean."""
    s = _sym_value(val) if isinstance(val, sexpdata.Symbol) else str(val or "")
    return s.lower() in ("yes", "true")


def _walk_drills(tree) -> list[float]:
    """Walk the tree collecting every (drill N) value in mm.

    Handles both `(drill 0.8)` and `(drill oval 0.6 0.8)` forms.
    """
    drills: list[float] = []

    def visit(node):
        if not isinstance(node, list) or not node:
            return
        head = node[0]
        if isinstance(head, sexpdata.Symbol) and head.value() == "drill":
            for val in node[1:]:
                if isinstance(val, (int, float)):
                    drills.append(float(val))
        for child in node[1:]:
            if isinstance(child, list):
                visit(child)

    visit(tree)
    return drills


def _load_design_rules(pcb_path: Path) -> dict:
    """Return the `board.design_settings.rules` dict from the .kicad_pro
    JSON sibling of the .kicad_pcb, or {} if unavailable.
    """
    pro_path = pcb_path.with_suffix(".kicad_pro")
    if not pro_path.exists():
        return {}
    try:
        data = json.loads(pro_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    board = data.get("board") or {}
    ds = board.get("design_settings") or {}
    rules = ds.get("rules")
    return rules if isinstance(rules, dict) else {}


def parse_board(pcb_path: Path) -> BoardInfo:
    text = pcb_path.read_text(encoding="utf-8")
    tree = sexpdata.loads(text)

    setup = _find_first(tree, "setup")
    stackup_node = _find_first(setup, "stackup") if setup else None
    layers: list[StackupLayer] = []
    copper_finish: str | None = None
    edge_plating = False
    castellated = False
    edge_connector: str | None = None
    if stackup_node:
        for layer in _find_all(stackup_node, "layer"):
            name = layer[1] if len(layer) > 1 else ""
            type_node = _find_first(layer, "type")
            thickness_node = _find_first(layer, "thickness")
            material_node = _find_first(layer, "material")
            color_node = _find_first(layer, "color")
            epsilon_node = _find_first(layer, "epsilon_r")
            loss_node = _find_first(layer, "loss_tangent")
            layers.append(StackupLayer(
                name=str(name),
                type=str(_scalar(type_node, "")),
                thickness_mm=float(_scalar(thickness_node)) if thickness_node else None,
                material=str(_scalar(material_node)) if material_node else None,
                color=str(_scalar(color_node)) if color_node else None,
                epsilon_r=float(_scalar(epsilon_node)) if epsilon_node else None,
                loss_tangent=float(_scalar(loss_node)) if loss_node else None,
            ))
        cf = _find_first(stackup_node, "copper_finish")
        if cf is not None:
            copper_finish = str(_scalar(cf)) or None
        ep = _find_first(stackup_node, "edge_plating")
        if ep is not None:
            edge_plating = _as_bool(_scalar(ep))
        cp = _find_first(stackup_node, "castellated_pads")
        if cp is not None:
            castellated = _as_bool(_scalar(cp))
        ec = _find_first(stackup_node, "edge_connector")
        if ec is not None:
            edge_connector = str(_scalar(ec)) or None

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

    # Derived/characteristic fields.
    copper_count = sum(1 for l in layers if l.type == "copper")
    thicknesses = [l.thickness_mm for l in layers if l.thickness_mm is not None]
    board_thickness = sum(thicknesses) if thicknesses else None
    impedance = any(
        l.epsilon_r is not None or l.loss_tangent is not None for l in layers
    )

    # Design rules from .kicad_pro (best-effort).
    rules = _load_design_rules(pcb_path)

    def _rule(key: str) -> float | None:
        v = rules.get(key)
        if isinstance(v, (int, float)):
            return float(v)
        return None

    min_trace = _rule("min_track_width")
    min_clr = _rule("min_clearance")
    min_hole = _rule("min_through_hole_diameter")
    min_annular = _rule("min_via_annular_width")

    # Fall back to scanning pad drills for the smallest finished hole diameter.
    if min_hole is None:
        drills = _walk_drills(tree)
        if drills:
            min_hole = min(drills)

    return BoardInfo(
        stackup=layers,
        enabled_layers=enabled,
        width_mm=width,
        height_mm=height,
        copper_layer_count=copper_count,
        board_thickness_mm=board_thickness,
        min_trace_width_mm=min_trace,
        min_clearance_mm=min_clr,
        min_hole_size_mm=min_hole,
        min_annular_ring_mm=min_annular,
        copper_finish=copper_finish,
        impedance_controlled=impedance,
        edge_plating=edge_plating,
        castellated_pads=castellated,
        edge_connector=edge_connector,
    )
