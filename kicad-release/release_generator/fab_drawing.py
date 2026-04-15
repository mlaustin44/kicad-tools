"""Compose the fab drawing: title block + board characteristics + drill map +
stackup + notes.

Typography conventions (ISO 3098 / ANSI Y14.2M inspired) are centralized in
the FONT_STACK / FONT_STACK_MONO / BODY_SIZE / HEADING_SIZE constants so the
fab and assembly drawings share a single visual language.
"""
from __future__ import annotations
import base64
import re
import shutil
import subprocess
from pathlib import Path

from lxml import etree

from .board_introspect import BoardInfo, parse_board
from .config import Config
from .kicad_cli import run as kicad_run
from .naming import artifact_path
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
        "DATE": cfg.project.date,
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
                    content_width: float, content_height: float,
                    *, padding: float = 0.0,
                    vertical_anchor: str = "center") -> etree._Element:
    """Wrap content element in a <g> that translates+scales it to fit region.

    Aspect-preserving fit. Content is horizontally centered in the region.
    ``padding`` is an inset fraction (0.0–1.0) applied on all sides; e.g.
    padding=0.05 makes the content fill 90% of the region (5% margin each side).

    ``vertical_anchor`` controls vertical placement:
      - "center" (default): content vertically centered in the region
      - "top": content biased to the top with ``padding * region.height`` inset
      - "bottom": content biased to the bottom with ``padding * region.height`` inset
    """
    if content_width <= 0 or content_height <= 0:
        scale = 1.0
    else:
        scale = min(region.width / content_width, region.height / content_height)
        if padding:
            scale *= max(0.0, 1.0 - 2.0 * padding)
    rendered_w = content_width * scale
    rendered_h = content_height * scale
    tx = region.x + (region.width - rendered_w) / 2
    if vertical_anchor == "top":
        ty = region.y + padding * region.height
    elif vertical_anchor == "bottom":
        ty = region.y + region.height - rendered_h - padding * region.height
    else:
        ty = region.y + (region.height - rendered_h) / 2
    g = etree.Element(f"{{{SVG_NS}}}g")
    g.set("transform", f"translate({tx} {ty}) scale({scale})")
    g.append(content)
    return g


def _crop_svg_to_drawing(src: Path, dst: Path) -> bool:
    """Crop an SVG so its viewBox matches the drawing content (not the page).

    Uses Inkscape's ``--export-area-drawing`` which computes the bounding box
    of visible elements and rewrites the viewBox accordingly. This is what we
    need for KiCad's drill-map export, which otherwise ships the drill data
    inside a full A4 page frame with lots of empty space.

    Returns True on success. On any failure (no Inkscape, non-zero exit,
    missing output) returns False and leaves ``dst`` unwritten so the caller
    can fall back to the uncropped source.
    """
    inkscape = shutil.which("inkscape")
    if not inkscape:
        return False
    try:
        res = subprocess.run(
            [inkscape, "--export-type=svg", "--export-plain-svg",
             "--export-area-drawing", "-o", str(dst), str(src)],
            capture_output=True, timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    if res.returncode != 0:
        return False
    return dst.exists() and dst.stat().st_size > 0


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
    # Top frame.
    _line(0, header_y_top, total_w, header_y_top, w=0.2)
    # Thick underline below the header row — separates header from body.
    _line(0, body_top, total_w, body_top, w=0.3)

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
    # Hairline row dividers between each data row (skip the last — that's
    # the table's bottom border).
    for i in range(1, len(board.stackup)):
        y = body_top + i * row_h
        _line(0, y, total_w, y, w=0.1)
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

NOTES_TITLE_SIZE = 2.5      # Bold header above the numbered notes.
NOTES_TITLE_GAP = 0.5       # mm — vertical gap between header baseline and note #1.


def _build_notes_list(notes: list[str], region: Region, *,
                      title: str | None = None) -> etree._Element:
    """Render numbered notes inside ``region`` at true mm sizes, wrapping to width.

    Returns a <g> already translated to region.x/region.y; no further scaling
    should be applied. Long notes wrap at the region width; hanging-indent
    keeps wrapped lines aligned past the number prefix.
    """
    NUMBER_COL_W = 4.5      # mm — x offset where note text starts
    SIDE_PAD = 1.0          # mm — inner padding (left/right) inside region
    TOP_PAD = 1.0           # mm — inner top padding
    CHAR_W = BODY_SIZE * 0.65  # DejaVu Sans Mono advance (conservative)
    row_h = BODY_SIZE * 1.7
    text_x = NUMBER_COL_W

    content_w = max(0.0, region.width - 2 * SIDE_PAD)
    wrap_w = max(10.0, content_w - NUMBER_COL_W)
    max_chars = max(10, int(wrap_w / CHAR_W))

    import textwrap
    wrapped = [
        textwrap.wrap(note, width=max_chars,
                      break_long_words=False, break_on_hyphens=False) or [""]
        for note in notes
    ]

    g = etree.Element(f"{{{SVG_NS}}}g")
    g.set("transform", f"translate({region.x + SIDE_PAD} {region.y + TOP_PAD})")

    y = 0.0
    if title:
        y = NOTES_TITLE_SIZE
        _text(g, 0, y, title,
              size=NOTES_TITLE_SIZE, weight="bold", family=FONT_STACK,
              letter_spacing="0.04em")
        y += NOTES_TITLE_GAP

    for i, lines in enumerate(wrapped, start=1):
        y += row_h
        _text(g, 0, y, f"{i}.",
              size=BODY_SIZE, weight="bold", family=FONT_STACK_MONO)
        for j, line in enumerate(lines):
            _text(g, text_x, y + j * row_h, line,
                  size=BODY_SIZE, weight="normal", family=FONT_STACK_MONO)
        y += (len(lines) - 1) * row_h
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
    template_path = cfg.fab_drawing.template
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
    # KiCad emits the map inside a full A4 page frame; crop to drawing bounds
    # via Inkscape so the content fills the region instead of being stranded
    # in a corner.
    if "drill-map" in regions:
        if drill_map_svg.exists():
            cropped = drill_dir / f"{cfg.project.pcb_file.stem}-drl_map.cropped.svg"
            src = cropped if _crop_svg_to_drawing(drill_map_svg, cropped) \
                else drill_map_svg
            if src is drill_map_svg:
                warnings.append(
                    "Inkscape crop failed for drill map; using uncropped SVG "
                    "(content may render small)")
            g, dw, dh = _load_svg_inner(src)
            tpl.replace_region("drill-map",
                               _wrap_in_region(g, regions["drill-map"],
                                               dw, dh, padding=0.025))
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

    # 8. Place fab notes. Rendered at true mm sizes inside the region.
    if "fab-notes" in regions and cfg.fab_drawing.notes:
        content = _build_notes_list(cfg.fab_drawing.notes,
                                    regions["fab-notes"],
                                    title="FABRICATION NOTES")
        tpl.replace_region("fab-notes", content)

    # 9. Write SVG, convert to PDF.
    final_svg = scratch / "fab-drawing.svg"
    final_svg.write_bytes(tpl.serialize())
    final_pdf = artifact_path(cfg, out, "FABRICATION_DRAWING", "pdf")
    svg_to_pdf(final_svg, final_pdf)

    return final_pdf, warnings
