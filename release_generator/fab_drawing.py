"""Compose the fab drawing: title block + board view + drill map + stackup +
notes."""
from __future__ import annotations
import base64
import datetime
import re
from pathlib import Path

from lxml import etree

from .board_introspect import BoardInfo, parse_board
from .config import Config
from .kicad_cli import run as kicad_run
from .svg_template import Region, SVG_NS, SvgTemplate
from .svg_to_pdf import convert as svg_to_pdf
from .utils import output_dir_for, scratch_dir_for

NSMAP = {"svg": SVG_NS}
XLINK_NS = "http://www.w3.org/1999/xlink"

_LEADING_NUMBER_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)")


def _parse_length(attr: str | None, default: float = 100.0) -> float:
    """Parse an SVG length attribute (e.g. '297mm', '100', '50%') to a float.

    Returns the leading numeric portion. Units are ignored; viewBox is the
    preferred source of truth for dimensions.
    """
    if not attr:
        return default
    m = _LEADING_NUMBER_RE.match(attr)
    if not m:
        return default
    try:
        return float(m.group(1))
    except ValueError:
        return default


def _build_text_vars(cfg: Config, drawing_title: str,
                     page: str = "Page 1 of 1") -> dict[str, str]:
    vars_ = {
        "TITLE": drawing_title,
        "DATE": (cfg.project.date
                 if cfg.project.date != "auto"
                 else datetime.date.today().isoformat()),
        "REV": cfg.project.version,
        "DRAWN_BY": cfg.titleblock.drawn_by,
        "COMPANY": cfg.titleblock.company,
        "CONFIDENTIALITY": cfg.titleblock.confidentiality,
        "PAGE": page,
        "FILENAME": cfg.project.pcb_file.name,
    }
    for i, rev in enumerate(cfg.revisions, start=1):
        vars_[f"REV_{i}"] = rev.rev
        vars_[f"EC_{i}"] = rev.ec
        vars_[f"DESC_{i}"] = rev.description
    return vars_


def _wrap_in_region(content: etree._Element, region: Region,
                    content_width: float, content_height: float) -> etree._Element:
    """Wrap content element in a <g> that translates+scales it to fit region.

    Aspect-preserving fit. Content is centered in the region.
    """
    if content_width <= 0 or content_height <= 0:
        scale = 1.0
    else:
        scale = min(region.width / content_width, region.height / content_height)
    rendered_w = content_width * scale
    rendered_h = content_height * scale
    tx = region.x + (region.width - rendered_w) / 2
    ty = region.y + (region.height - rendered_h) / 2
    g = etree.Element(f"{{{SVG_NS}}}g")
    g.set("transform", f"translate({tx} {ty}) scale({scale})")
    g.append(content)
    return g


def _load_svg_inner(svg_path: Path) -> tuple[etree._Element, float, float]:
    """Load an SVG and return (wrapper_group, width, height) for embedding.

    Moves children of the root <svg> into a new <g> so the fragment can be
    embedded inside another SVG document. Dimensions come from viewBox when
    present (preferred), otherwise from width/height attributes with unit
    suffixes stripped.
    """
    tree = etree.parse(str(svg_path))
    root = tree.getroot()
    vb = root.get("viewBox")
    if vb:
        parts = vb.replace(",", " ").split()
        if len(parts) >= 4:
            width = float(parts[2])
            height = float(parts[3])
        else:
            width = _parse_length(root.get("width"))
            height = _parse_length(root.get("height"))
    else:
        width = _parse_length(root.get("width"))
        height = _parse_length(root.get("height"))
    g = etree.Element(f"{{{SVG_NS}}}g")
    for child in root:
        g.append(child)
    return g, width, height


def _build_stackup_table(board: BoardInfo) -> etree._Element:
    """Build a vertically stacked text table of the stackup layers."""
    g = etree.Element(f"{{{SVG_NS}}}g")
    line_height = 3.5
    header = etree.SubElement(g, f"{{{SVG_NS}}}text",
                              attrib={"x": "0", "y": "0",
                                      "font-size": "3",
                                      "font-weight": "bold",
                                      "font-family": "monospace"})
    header.text = f"{'NAME':18s} {'TYPE':18s} {'TH(mm)':>8s} {'MAT':10s}"
    for i, layer in enumerate(board.stackup, start=1):
        t = etree.SubElement(g, f"{{{SVG_NS}}}text",
                             attrib={"x": "0",
                                     "y": str(i * line_height),
                                     "font-size": "3",
                                     "font-family": "monospace"})
        thickness = (f"{layer.thickness_mm:.3f}"
                     if layer.thickness_mm is not None else "-")
        material = layer.material or "-"
        t.text = (f"{layer.name[:18]:18s} {layer.type[:18]:18s} "
                  f"{thickness:>8s} {material[:10]:10s}")
    return g


def _build_notes_list(notes: list[str]) -> etree._Element:
    """Build a numbered list of notes as text elements."""
    g = etree.Element(f"{{{SVG_NS}}}g")
    for i, note in enumerate(notes, start=1):
        t = etree.SubElement(g, f"{{{SVG_NS}}}text",
                             attrib={"x": "0",
                                     "y": str(i * 4),
                                     "font-size": "2.5",
                                     "font-family": "sans-serif"})
        t.text = f"{i}. {note}"
    return g


def _build_image_element(png_path: Path, width: float, height: float) -> etree._Element:
    """Build an <image> referencing a PNG, sized to (width, height) in its own units.

    The PNG is embedded as a base64 data URI so the SVG is self-contained and
    renders correctly through cairosvg (which does not follow external `file://`
    or bare-path references). The caller wraps the element in a transform that
    positions it within the page.
    """
    data = png_path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    img = etree.Element(f"{{{SVG_NS}}}image",
                        attrib={"x": "0", "y": "0",
                                "width": str(width),
                                "height": str(height),
                                "preserveAspectRatio": "xMidYMid meet"})
    img.set(f"{{{XLINK_NS}}}href", f"data:image/png;base64,{b64}")
    return img


def compose_fab_drawing(cfg: Config, *, verbose: bool) -> tuple[Path, list[str]]:
    """Assemble the fab drawing PDF. Returns (pdf_path, warnings)."""
    out = output_dir_for(cfg)
    scratch = scratch_dir_for(cfg)
    template_path = cfg.fab_drawing.template or cfg.titleblock.template
    warnings: list[str] = []

    # 1. Export Edge.Cuts SVG of the board (board-area-only, no frame).
    board_svg = scratch / "board-edge.svg"
    kicad_run(["pcb", "export", "svg", str(cfg.project.pcb_file),
               "-o", str(board_svg),
               "--layers", "Edge.Cuts",
               "--page-size-mode", "2",
               "--mode-single",
               "--exclude-drawing-sheet"], verbose=verbose)

    # 2. Generate drill map SVG via kicad-cli.
    drill_dir = scratch / "drill_map"
    drill_dir.mkdir(parents=True, exist_ok=True)
    kicad_run(["pcb", "export", "drill", str(cfg.project.pcb_file),
               "-o", str(drill_dir) + "/",
               "--generate-map", "--map-format", "svg"], verbose=verbose)
    drill_map_svg = drill_dir / f"{cfg.project.pcb_file.stem}-drl_map.svg"

    # 3. Parse board for stackup.
    board = parse_board(cfg.project.pcb_file)

    # 4. Load template, run text substitution.
    tpl = SvgTemplate(template_path.read_bytes())
    tpl.substitute_text(_build_text_vars(cfg, cfg.fab_drawing.title))

    # 5. Find regions.
    region_ids = ["board-view", "drill-map", "stackup-table", "fab-notes"]
    regions = tpl.find_regions(region_ids)
    for needed in region_ids:
        if needed not in regions:
            warnings.append(
                f"template missing region id='{needed}', skipping content")

    # 6. Place board view.
    if "board-view" in regions:
        g, bw, bh = _load_svg_inner(board_svg)
        tpl.replace_region("board-view",
                           _wrap_in_region(g, regions["board-view"], bw, bh))

    # 7. Place drill map (KiCad-generated SVG with board outline + table).
    if "drill-map" in regions:
        if drill_map_svg.exists():
            g, dw, dh = _load_svg_inner(drill_map_svg)
            tpl.replace_region("drill-map",
                               _wrap_in_region(g, regions["drill-map"],
                                               dw, dh))
        else:
            warnings.append(
                f"drill map SVG not found at {drill_map_svg}; skipping")

    # 8. Place stackup table.
    if "stackup-table" in regions:
        content = _build_stackup_table(board)
        rows_h = max(1, len(board.stackup) + 1) * 4
        tpl.replace_region("stackup-table",
                           _wrap_in_region(content, regions["stackup-table"],
                                           60, rows_h))

    # 9. Place fab notes.
    if "fab-notes" in regions and cfg.fab_drawing.notes:
        content = _build_notes_list(cfg.fab_drawing.notes)
        notes_h = max(1, len(cfg.fab_drawing.notes)) * 4
        tpl.replace_region("fab-notes",
                           _wrap_in_region(content, regions["fab-notes"],
                                           80, notes_h))

    # 10. Write SVG, convert to PDF.
    final_svg = scratch / "fab-drawing.svg"
    final_svg.write_bytes(tpl.serialize())
    final_pdf = out / "fab-drawing.pdf"
    svg_to_pdf(final_svg, final_pdf)

    return final_pdf, warnings
