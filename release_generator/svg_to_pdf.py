"""SVG → PDF conversion. CairoSVG primary; Inkscape CLI fallback."""
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path

import cairosvg


class SvgToPdfError(RuntimeError):
    pass


def convert(svg_path: Path, pdf_path: Path) -> None:
    """Convert SVG file to PDF. Raises SvgToPdfError if both backends fail."""
    try:
        cairosvg.svg2pdf(url=str(svg_path), write_to=str(pdf_path))
        return
    except Exception as e:
        cairo_err = e

    inkscape = shutil.which("inkscape")
    if inkscape:
        res = subprocess.run(
            [inkscape, str(svg_path), "--export-type=pdf",
             f"--export-filename={pdf_path}"],
            capture_output=True, text=True, timeout=120,
        )
        if res.returncode == 0 and pdf_path.exists():
            return
        raise SvgToPdfError(
            f"CairoSVG failed: {cairo_err}; Inkscape fallback failed: {res.stderr}"
        )
    raise SvgToPdfError(
        f"CairoSVG failed and Inkscape not found on PATH: {cairo_err}"
    )
