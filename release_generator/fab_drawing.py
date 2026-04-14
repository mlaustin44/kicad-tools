"""Compose the fab drawing: title block + board characteristics + drill map +
stackup + notes.

Typography conventions (ISO 3098 / ANSI Y14.2M inspired) are centralized in
the FONT_STACK / FONT_STACK_MONO / BODY_SIZE / HEADING_SIZE constants so the
fab and assembly drawings share a single visual language.
"""
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

# --- Typography -------------------------------------------------------------
# Fallback stack ordered for technical-drawing aesthetic: DejaVu Sans renders
# cleanly at small sizes through CairoSVG (its strokes don't ghost), Liberation
# Sans and Arial cover other platforms, and generic sans-serif is the floor.
FONT_STACK = "DejaVu Sans, Liberation Sans, Arial, sans-serif"
FONT_STACK_MONO = "DejaVu Sans Mono, Liberation Mono, Courier New, monospace"

TITLE_SIZE = 3.0      # Section titles (BOARD CHARACTERISTICS, BOARD STACKUP).
HEADING_SIZE = 2.3    # Table header rows.
BODY_SIZE = 2.0       # Normal body text / table cells.
NOTE_SIZE = 2.2       # Numbered fab notes.
LABEL_COL_WIDTH = 48.0  # mm, for key:value layouts.

MM_PER_MIL = 0.0254


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


def _text(parent, x: float, y: float, content: str, *,
          size: float = BODY_SIZE,
          weight: str = "normal",
          anchor: str = "start",
          family: str = FONT_STACK,
          letter_spacing: str | None = None) -> etree._Element:
    """Create an SVG <text> under `parent` with our house typography defaults.

    Always sets an explicit fill='black' so CairoSVG doesn't inherit a stroke
    and render the text as outlines.
    """
    attrib = {
        "x": f"{x:g}",
        "y": f"{y:g}",
        "font-family": family,
        "font-size": f"{size:g}",
        "fill": "black",
        "text-anchor": anchor,
    }
    if weight != "normal":
        attrib["font-weight"] = weight
    if letter_spacing:
        attrib["letter-spacing"] = letter_spacing
    el = etree.SubElement(parent, f"{{{SVG_NS}}}text", attrib=attrib)
    el.text = content
    return el


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


# --- Board characteristics --------------------------------------------------

def _fmt_mm_mil(mm: float | None) -> str:
    """Format a dimension as 'N mil / M.MMM mm'. Returns 'Not specified' if None."""
    if mm is None:
        return "Not specified"
    mil = mm / MM_PER_MIL
    return f"{mil:.1f} mil / {mm:.3f} mm"


def _fmt_mm(mm: float | None, decimals: int = 3) -> str:
    if mm is None:
        return "Not specified"
    return f"{mm:.{decimals}f} mm"


def _fmt_yesno(val: bool) -> str:
    return "Yes" if val else "No"


def _build_board_characteristics(board: BoardInfo) -> tuple[etree._Element, float, float]:
    """Return (group, natural_width_mm, natural_height_mm).

    Two-column 'Label: Value' layout. Label column is bold, value column is
    regular weight. Title at top in bold.
    """
    g = etree.Element(f"{{{SVG_NS}}}g")

    title = "BOARD CHARACTERISTICS"
    _text(g, 0, TITLE_SIZE, title,
          size=TITLE_SIZE, weight="bold", letter_spacing="0.04em")

    rows: list[tuple[str, str]] = [
        ("Copper Layer Count:", str(board.copper_layer_count)
         if board.copper_layer_count else "Not specified"),
        ("Board Thickness:", _fmt_mm(board.board_thickness_mm)),
        ("Min Trace Width:", _fmt_mm_mil(board.min_trace_width_mm)),
        ("Min Clearance:", _fmt_mm_mil(board.min_clearance_mm)),
        ("Min Hole Size:", _fmt_mm(board.min_hole_size_mm)),
        ("Min Annular Ring:", _fmt_mm(board.min_annular_ring_mm)),
        ("Copper Finish:", board.copper_finish or "Not specified"),
        ("Impedance Control:", _fmt_yesno(board.impedance_controlled)),
        ("Edge Plating:", _fmt_yesno(board.edge_plating)),
        ("Castellated Pads:", _fmt_yesno(board.castellated_pads)),
        ("Edge Connector:", board.edge_connector or "None"),
    ]

    # Layout: title baseline at y=TITLE_SIZE. First row 2mm below that.
    row_h = BODY_SIZE * 1.5
    top = TITLE_SIZE + 2.0
    label_x = 0.0
    value_x = LABEL_COL_WIDTH
    value_max = 72.0  # mm — widest observed value column text, for natural width
    for i, (label, value) in enumerate(rows):
        y = top + (i + 1) * row_h
        _text(g, label_x, y, label,
              size=BODY_SIZE, weight="bold", family=FONT_STACK)
        _text(g, value_x, y, value,
              size=BODY_SIZE, weight="normal", family=FONT_STACK_MONO)

    natural_w = value_x + value_max
    natural_h = top + (len(rows) + 1) * row_h
    return g, natural_w, natural_h


# --- Stackup table ----------------------------------------------------------

_STACKUP_COLS = [
    ("Layer", 26.0, "start"),
    ("Type", 26.0, "start"),
    ("Material", 16.0, "start"),
    ("Thickness", 16.0, "end"),
    ("Color", 12.0, "start"),
    ("Er", 8.0, "end"),
    ("Tan D", 10.0, "end"),
]


def _build_stackup_table(board: BoardInfo) -> tuple[etree._Element, float, float]:
    """Build a properly tabular stackup with header + one row per layer.

    Header row bold. Body in monospaced font for number alignment. Row
    separators are 0.1mm hairlines; overall frame is 0.2mm.
    Returns (group, natural_width_mm, natural_height_mm).
    """
    g = etree.Element(f"{{{SVG_NS}}}g")

    # Column x-positions: accumulate widths from left edge.
    x_left = [0.0]
    for _, w, _ in _STACKUP_COLS:
        x_left.append(x_left[-1] + w)
    total_w = x_left[-1]

    row_h = BODY_SIZE * 1.55
    title_h = TITLE_SIZE + 2.0

    # Title.
    _text(g, 0, TITLE_SIZE, "BOARD STACKUP",
          size=TITLE_SIZE, weight="bold", letter_spacing="0.04em")

    # Header row background line.
    header_y_top = title_h
    _text_baseline = header_y_top + row_h * 0.72  # vertically centered-ish
    for i, (name, w, anchor) in enumerate(_STACKUP_COLS):
        if anchor == "end":
            tx = x_left[i] + w - 1.0
        elif anchor == "middle":
            tx = x_left[i] + w / 2
        else:
            tx = x_left[i] + 1.0
        _text(g, tx, _text_baseline, name,
              size=HEADING_SIZE, weight="bold", anchor=anchor,
              family=FONT_STACK)

    # Horizontal lines under header and at bottom; vertical column separators.
    def _line(x1, y1, x2, y2, w=0.15):
        etree.SubElement(g, f"{{{SVG_NS}}}line", attrib={
            "x1": f"{x1:g}", "y1": f"{y1:g}",
            "x2": f"{x2:g}", "y2": f"{y2:g}",
            "stroke": "black", "stroke-width": f"{w:g}",
        })

    body_top = header_y_top + row_h
    _line(0, header_y_top, total_w, header_y_top, w=0.2)
    _line(0, body_top, total_w, body_top, w=0.2)

    for i, layer in enumerate(board.stackup):
        baseline = body_top + (i + 1) * row_h - row_h * 0.28
        thickness = (f"{layer.thickness_mm:.3f}"
                     if layer.thickness_mm is not None else "\u2014")
        material = layer.material or "\u2014"
        color = layer.color or "\u2014"
        er = (f"{layer.epsilon_r:.2f}" if layer.epsilon_r is not None else "")
        tan = (f"{layer.loss_tangent:.3f}"
               if layer.loss_tangent is not None else "")
        values = [layer.name, layer.type, material, thickness, color, er, tan]
        for col_i, (_, w, anchor) in enumerate(_STACKUP_COLS):
            if anchor == "end":
                tx = x_left[col_i] + w - 1.0
            elif anchor == "middle":
                tx = x_left[col_i] + w / 2
            else:
                tx = x_left[col_i] + 1.0
            _text(g, tx, baseline, values[col_i],
                  size=BODY_SIZE, weight="normal", anchor=anchor,
                  family=FONT_STACK_MONO)

    body_bottom = body_top + len(board.stackup) * row_h
    _line(0, body_bottom, total_w, body_bottom, w=0.2)

    # Frame + column dividers.
    _line(0, header_y_top, 0, body_bottom, w=0.2)
    _line(total_w, header_y_top, total_w, body_bottom, w=0.2)
    for i in range(1, len(_STACKUP_COLS)):
        _line(x_left[i], header_y_top, x_left[i], body_bottom, w=0.1)

    natural_w = total_w
    natural_h = body_bottom + 1.0
    return g, natural_w, natural_h


# --- Notes ------------------------------------------------------------------

def _build_notes_list(notes: list[str]) -> etree._Element:
    """Build a numbered list of notes as text elements."""
    g = etree.Element(f"{{{SVG_NS}}}g")
    row_h = NOTE_SIZE * 1.7
    for i, note in enumerate(notes, start=1):
        y = (i + 0.5) * row_h
        _text(g, 0, y, f"{i}.",
              size=NOTE_SIZE, weight="bold")
        _text(g, 4.5, y, note,
              size=NOTE_SIZE, weight="normal")
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

    # 1. Generate drill map SVG via kicad-cli.
    drill_dir = scratch / "drill_map"
    drill_dir.mkdir(parents=True, exist_ok=True)
    kicad_run(["pcb", "export", "drill", str(cfg.project.pcb_file),
               "-o", str(drill_dir) + "/",
               "--generate-map", "--map-format", "svg"], verbose=verbose)
    drill_map_svg = drill_dir / f"{cfg.project.pcb_file.stem}-drl_map.svg"

    # 2. Parse board for stackup + characteristics.
    board = parse_board(cfg.project.pcb_file)

    # 3. Load template, run text substitution.
    tpl = SvgTemplate(template_path.read_bytes())
    tpl.substitute_text(_build_text_vars(cfg, cfg.fab_drawing.title))

    # 4. Find regions.
    region_ids = ["board-characteristics", "drill-map", "stackup-table",
                  "fab-notes"]
    regions = tpl.find_regions(region_ids)
    for needed in region_ids:
        if needed not in regions:
            warnings.append(
                f"template missing region id='{needed}', skipping content")

    # 5. Place drill map (KiCad-generated SVG with board outline + table).
    if "drill-map" in regions:
        if drill_map_svg.exists():
            g, dw, dh = _load_svg_inner(drill_map_svg)
            tpl.replace_region("drill-map",
                               _wrap_in_region(g, regions["drill-map"],
                                               dw, dh))
        else:
            warnings.append(
                f"drill map SVG not found at {drill_map_svg}; skipping")

    # 6. Place board characteristics.
    if "board-characteristics" in regions:
        content, nw, nh = _build_board_characteristics(board)
        tpl.replace_region(
            "board-characteristics",
            _wrap_in_region(content, regions["board-characteristics"], nw, nh),
        )

    # 7. Place stackup table.
    if "stackup-table" in regions:
        content, nw, nh = _build_stackup_table(board)
        tpl.replace_region("stackup-table",
                           _wrap_in_region(content, regions["stackup-table"],
                                           nw, nh))

    # 8. Place fab notes.
    if "fab-notes" in regions and cfg.fab_drawing.notes:
        content = _build_notes_list(cfg.fab_drawing.notes)
        notes_h = max(1, len(cfg.fab_drawing.notes)) * NOTE_SIZE * 1.7 + NOTE_SIZE
        tpl.replace_region("fab-notes",
                           _wrap_in_region(content, regions["fab-notes"],
                                           90, notes_h))

    # 9. Write SVG, convert to PDF.
    final_svg = scratch / "fab-drawing.svg"
    final_svg.write_bytes(tpl.serialize())
    final_pdf = out / "fab-drawing.pdf"
    svg_to_pdf(final_svg, final_pdf)

    return final_pdf, warnings
