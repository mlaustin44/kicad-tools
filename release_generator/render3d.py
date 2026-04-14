"""3D render of the PCB to PNG via kicad-cli pcb render."""
from __future__ import annotations
from pathlib import Path
from .config import Config
from .kicad_cli import run as kicad_run, KicadCliError
from .utils import scratch_dir_for


def render_pcb(cfg: Config, *, verbose: bool) -> tuple[list[Path], list[str]]:
    """Returns (list of PNG paths, warnings). Skips entirely if 3D render disabled."""
    if not cfg.assembly_drawing.include_3d_render:
        return [], ["3D render disabled in [assembly_drawing].include_3d_render"]

    out_dir = scratch_dir_for(cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    sides = ["top", "bottom"] if cfg.assembly_drawing.render_view == "both" \
            else [cfg.assembly_drawing.render_view]
    pngs: list[Path] = []
    for side in sides:
        png = out_dir / f"render-3d-{side}.png"
        args = ["pcb", "render", str(cfg.project.pcb_file),
                "-o", str(png),
                "--side", side,
                "--quality", "high",
                "--width", "1600", "--height", "1200",
                "--background", "opaque"]
        kicad_run(args, verbose=verbose, timeout=900)
        if not png.exists():
            raise KicadCliError(f"render did not produce {png}")
        pngs.append(png)
    return pngs, []
