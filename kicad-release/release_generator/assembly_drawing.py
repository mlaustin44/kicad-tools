"""Compose the assembly drawing: title block + front view + back view + 3D render
+ notes."""
from __future__ import annotations
from pathlib import Path

from lxml import etree

from .board_introspect import parse_references
from .config import Config
from .fab_drawing import (
    _build_image_element,
    _build_notes_list,
    _build_text_vars,
    _load_svg_inner,
    _wrap_in_region,
)
from .kicad_cli import run as kicad_run
from .naming import artifact_path
from .render3d import render_pcb
from .svg_template import Region, SVG_NS, SvgTemplate
from .svg_to_pdf import convert as svg_to_pdf
from .utils import output_dir_for, scratch_dir_for


# KiCad's default color theme, used to identify layers in exported SVG.
_SILK_STROKE = "#F2EDA1"
_SILK_REPLACEMENT = "#808080"   # medium grey for silkscreen
_BLACK = "#000000"


def _recolor_for_white_sheet(svg_path: Path) -> None:
    """Recolor a KiCad SVG for printing on a white page.

    Silkscreen is mapped to medium grey; every other layer (fab, courtyard,
    edge-cuts) is mapped to black. The dark-mode theme colors KiCad uses
    wash out on a white sheet.
    """
    import re
    stroke_re = re.compile(r"stroke\s*:\s*(#[0-9A-Fa-f]{6})")
    fill_re = re.compile(r"fill\s*:\s*(#[0-9A-Fa-f]{6})")
    tree = etree.parse(str(svg_path))

    def replace(match: "re.Match[str]") -> str:
        color = match.group(1).upper()
        prop = match.group(0).split(":", 1)[0].strip()
        if color == _SILK_STROKE.upper():
            return f"{prop}:{_SILK_REPLACEMENT}"
        return f"{prop}:{_BLACK}"

    for el in tree.iter():
        style = el.get("style")
        if not style:
            continue
        new = stroke_re.sub(replace, style)
        new = fill_re.sub(replace, new)
        if new != style:
            el.set("style", new)
    tree.write(str(svg_path))


def _text_items(tree) -> list[tuple[object, str]]:
    """Enumerate text-bearing elements in a KiCad-exported SVG as
    (element_to_remove, content) pairs.

    KiCad emits two forms:
      - `<text>…</text>` for small text (the content is the element's text).
      - `<g class="stroked-text"><desc>STRING</desc><path…/>…</g>` when text is
        rendered as stroked paths; we key on the `<desc>` child.
    """
    desc_tag = f"{{{SVG_NS}}}desc"
    items: list[tuple[object, str]] = []
    for t in tree.iter(f"{{{SVG_NS}}}text"):
        c = "".join(t.itertext()).strip()
        if c:
            items.append((t, c))
    for g in tree.iter(f"{{{SVG_NS}}}g"):
        if "stroked-text" not in (g.get("class") or ""):
            continue
        desc = g.find(desc_tag)
        if desc is not None and (desc.text or "").strip():
            items.append((g, desc.text.strip()))
    return items


def _collect_text(svg_path: Path) -> set[str]:
    """Return the set of distinct text strings appearing in a KiCad SVG."""
    tree = etree.parse(str(svg_path))
    return {content for _, content in _text_items(tree)}


def _remove_texts(svg_path: Path, to_remove: set[str]) -> int:
    """Remove text-bearing elements whose content is in ``to_remove``.

    Handles both `<text>` elements and `<g class="stroked-text">` groups.
    """
    if not to_remove:
        return 0
    tree = etree.parse(str(svg_path))
    removed = 0
    for el, content in _text_items(tree):
        if content in to_remove:
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
                removed += 1
    tree.write(str(svg_path))
    return removed

# Render resolution (px) — keep in sync with render3d.render_pcb args.
RENDER_PX_W = 1600
RENDER_PX_H = 1200


def compose_assembly_drawing(cfg: Config, *, verbose: bool) -> tuple[Path, list[str]]:
    """Assemble the assembly drawing PDF. Returns (pdf_path, warnings)."""
    out = output_dir_for(cfg)
    scratch = scratch_dir_for(cfg)
    template_path = cfg.assembly_drawing.template
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

    # Strip fab-layer value text (MPNs, "TestPoint", etc.) from the combined
    # views. Method: do a fab-only export per side, collect its text, remove
    # the non-refdes subset from the combined SVGs. Silkscreen and other
    # layers are untouched.
    refs = parse_references(cfg.project.pcb_file)
    for combined, fab_layer, mirror in (
        (front_svg, "F.Fab", False),
        (back_svg, "B.Fab", True),
    ):
        fab_only = scratch / f"{fab_layer.replace('.', '_')}-only.svg"
        args = ["pcb", "export", "svg", str(cfg.project.pcb_file),
                "-o", str(fab_only),
                "--layers", fab_layer,
                "--page-size-mode", "2",
                "--mode-single",
                "--exclude-drawing-sheet"]
        if mirror:
            args.append("--mirror")
        kicad_run(args, verbose=verbose)
        discard = _collect_text(fab_only) - refs
        _remove_texts(combined, discard)
        _recolor_for_white_sheet(combined)

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

    # 6. Place front view. Labels (e.g. "FRONT"/"BACK") are authored as text
    # elements in the template SVG itself.
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

    # 9. Place assembly notes. Rendered at true mm sizes inside the region.
    if "assembly-notes" in regions and cfg.assembly_drawing.notes:
        content = _build_notes_list(cfg.assembly_drawing.notes,
                                    regions["assembly-notes"],
                                    title="ASSEMBLY NOTES")
        tpl.replace_region("assembly-notes", content)

    # 10. Write SVG, convert to PDF.
    final_svg = scratch / "assembly-drawing.svg"
    final_svg.write_bytes(tpl.serialize())
    final_pdf = artifact_path(cfg, out, "ASSEMBLY_DRAWING", "pdf")
    svg_to_pdf(final_svg, final_pdf)

    return final_pdf, warnings
