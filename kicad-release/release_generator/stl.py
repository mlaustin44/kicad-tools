"""STL mesh export via `kicad-cli pcb export stl`."""
from __future__ import annotations
from pathlib import Path

from .config import Config
from .kicad_cli import run as kicad_run, KicadCliError
from .naming import artifact_path
from .utils import output_dir_for


def export_stl(cfg: Config, *, verbose: bool) -> tuple[Path, list[str]]:
    out = artifact_path(cfg, output_dir_for(cfg), "3D", "stl")
    kicad_run(["pcb", "export", "stl", str(cfg.project.pcb_file),
               "-o", str(out), "--force"], verbose=verbose, timeout=600)
    if not out.exists():
        raise KicadCliError(f"kicad-cli pcb export stl did not produce {out}")
    return out, []
