"""Compose the assembly drawing: title block + front view + back view + 3D render
+ notes."""
from __future__ import annotations
from pathlib import Path

from .config import Config
from .fab_drawing import (
    _build_image_element,
    _build_notes_list,
    _build_text_vars,
    _load_svg_inner,
    _wrap_in_region,
)
from .kicad_cli import run as kicad_run
from .render3d import render_pcb
from .svg_template import Region, SVG_NS, SvgTemplate
from .svg_to_pdf import convert as svg_to_pdf
from .utils import output_dir_for, scratch_dir_for

# Render resolution (px) — keep in sync with render3d.render_pcb args.
RENDER_PX_W = 1600
RENDER_PX_H = 1200


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

    # 3. Render 3D PNG(s) if enabled.
    pngs: list[Path] = []
    if cfg.assembly_drawing.include_3d_render:
        pngs, w = render_pcb(cfg, verbose=verbose)
        warnings.extend(w)

    # 4. Load template, run text substitution.
    tpl = SvgTemplate(template_path.read_bytes())
    tpl.substitute_text(_build_text_vars(cfg, cfg.assembly_drawing.title))

    # 5. Find regions.
    region_ids = ["front-view", "back-view", "render-3d", "assembly-notes"]
    regions = tpl.find_regions(region_ids)
    for needed in region_ids:
        if needed not in regions:
            warnings.append(
                f"template missing region id='{needed}', skipping content")

    # 6. Place front view.
    if "front-view" in regions:
        g, w, h = _load_svg_inner(front_svg)
        tpl.replace_region("front-view",
                           _wrap_in_region(g, regions["front-view"], w, h))

    # 7. Place back view.
    if "back-view" in regions:
        g, w, h = _load_svg_inner(back_svg)
        tpl.replace_region("back-view",
                           _wrap_in_region(g, regions["back-view"], w, h))

    # 8. Place 3D render(s) — only if enabled in config.
    if "render-3d" in regions:
        if not cfg.assembly_drawing.include_3d_render:
            warnings.append(
                "render-3d region present but "
                "[assembly_drawing].include_3d_render is disabled; skipping")
        elif not pngs:
            warnings.append("render-3d region present but no PNGs produced; skipping")
        elif len(pngs) == 2:
            # "both" mode: split the region horizontally for top + bottom.
            r = regions["render-3d"]
            half_w = r.width / 2
            for idx, png in enumerate(pngs):
                sub_region = Region(id=f"render-half-{idx}",
                                    x=r.x + idx * half_w, y=r.y,
                                    width=half_w, height=r.height)
                img = _build_image_element(png, RENDER_PX_W, RENDER_PX_H)
                wrapper = _wrap_in_region(img, sub_region,
                                          RENDER_PX_W, RENDER_PX_H)
                tpl.tree.append(wrapper)
            # Remove the original region rect so it doesn't linger.
            for rect in tpl.tree.iter(f"{{{SVG_NS}}}rect"):
                if rect.get("id") == "render-3d":
                    rect.getparent().remove(rect)
                    break
        else:
            img = _build_image_element(pngs[0], RENDER_PX_W, RENDER_PX_H)
            tpl.replace_region("render-3d",
                               _wrap_in_region(img, regions["render-3d"],
                                               RENDER_PX_W, RENDER_PX_H))

    # 9. Place assembly notes.
    if "assembly-notes" in regions and cfg.assembly_drawing.notes:
        content = _build_notes_list(cfg.assembly_drawing.notes)
        notes_h = max(1, len(cfg.assembly_drawing.notes)) * 4
        tpl.replace_region("assembly-notes",
                           _wrap_in_region(content, regions["assembly-notes"],
                                           60, notes_h))

    # 10. Write SVG, convert to PDF.
    final_svg = scratch / "assembly-drawing.svg"
    final_svg.write_bytes(tpl.serialize())
    final_pdf = out / "assembly-drawing.pdf"
    svg_to_pdf(final_svg, final_pdf)

    return final_pdf, warnings
