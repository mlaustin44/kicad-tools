"""Compose the assembly drawing: title block + front view + back view + notes."""
from __future__ import annotations
from pathlib import Path

from .config import Config
from .fab_drawing import (
    _build_notes_list,
    _build_text_vars,
    _load_svg_inner,
    _wrap_in_region,
)
from .kicad_cli import run as kicad_run
from .svg_template import SvgTemplate
from .svg_to_pdf import convert as svg_to_pdf
from .utils import output_dir_for, scratch_dir_for


def compose_assembly_drawing(cfg: Config, *, verbose: bool) -> tuple[Path, list[str]]:
    """Assemble the assembly drawing PDF. Returns (pdf_path, warnings)."""
    out = output_dir_for(cfg)
    scratch = scratch_dir_for(cfg)
    template_path = cfg.assembly_drawing.template or cfg.titleblock.template
    warnings: list[str] = []

    # 1. Export front-side SVG (F.Fab + F.Courtyard + Edge.Cuts by default).
    front_svg = scratch / "assembly-front.svg"
    kicad_run(["pcb", "export", "svg", str(cfg.project.pcb_file),
               "-o", str(front_svg),
               "--layers", ",".join(cfg.assembly_drawing.layers_front),
               "--page-size-mode", "2",
               "--mode-single",
               "--exclude-drawing-sheet"], verbose=verbose)

    # 2. Export back-side SVG (mirrored).
    back_svg = scratch / "assembly-back.svg"
    kicad_run(["pcb", "export", "svg", str(cfg.project.pcb_file),
               "-o", str(back_svg),
               "--layers", ",".join(cfg.assembly_drawing.layers_back),
               "--page-size-mode", "2",
               "--mode-single",
               "--exclude-drawing-sheet",
               "--mirror"], verbose=verbose)

    # 3. Load template, run text substitution.
    tpl = SvgTemplate(template_path.read_bytes())
    tpl.substitute_text(_build_text_vars(cfg, cfg.assembly_drawing.title))

    # 4. Find regions.
    region_ids = ["front-view", "back-view", "assembly-notes"]
    regions = tpl.find_regions(region_ids)
    for needed in region_ids:
        if needed not in regions:
            warnings.append(
                f"template missing region id='{needed}', skipping content")

    # 5. Place front view.
    if "front-view" in regions:
        g, w, h = _load_svg_inner(front_svg)
        tpl.replace_region("front-view",
                           _wrap_in_region(g, regions["front-view"], w, h))

    # 6. Place back view.
    if "back-view" in regions:
        g, w, h = _load_svg_inner(back_svg)
        tpl.replace_region("back-view",
                           _wrap_in_region(g, regions["back-view"], w, h))

    # 7. Place assembly notes.
    if "assembly-notes" in regions and cfg.assembly_drawing.notes:
        content = _build_notes_list(cfg.assembly_drawing.notes)
        notes_h = max(1, len(cfg.assembly_drawing.notes)) * 4
        tpl.replace_region("assembly-notes",
                           _wrap_in_region(content, regions["assembly-notes"],
                                           60, notes_h))

    # 8. Write SVG, convert to PDF.
    final_svg = scratch / "assembly-drawing.svg"
    final_svg.write_bytes(tpl.serialize())
    final_pdf = out / "assembly-drawing.pdf"
    svg_to_pdf(final_svg, final_pdf)

    return final_pdf, warnings
