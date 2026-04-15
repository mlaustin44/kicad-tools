"""Gerbers, drill files, drill report, pick-and-place, and the top-level
DRILL convenience copy."""
from __future__ import annotations
import shutil
from pathlib import Path

from .config import Config
from .kicad_cli import run as kicad_run
from .naming import artifact_path
from .utils import output_dir_for


def export_gerbers(cfg: Config, *, verbose: bool) -> tuple[list[Path], list[str]]:
    out = output_dir_for(cfg)
    gerber_dir = out / "gerbers"
    gerber_dir.mkdir(exist_ok=True)
    pcb = str(cfg.project.pcb_file)

    # Gerbers
    gerber_args = ["pcb", "export", "gerbers", pcb, "-o", str(gerber_dir) + "/"]
    if isinstance(cfg.gerbers.layers, list):
        gerber_args += ["--layers", ",".join(cfg.gerbers.layers)]
    if cfg.gerbers.subtract_soldermask:
        gerber_args += ["--subtract-soldermask"]
    kicad_run(gerber_args, verbose=verbose)

    # Drill files + map + report, written alongside the gerbers.
    drill_args = ["pcb", "export", "drill", pcb, "-o", str(gerber_dir) + "/",
                  "--generate-map", "--map-format", "pdf",
                  "--generate-report"]
    kicad_run(drill_args, verbose=verbose)

    # Pick-and-place at the top level, with the naming pattern.
    pos_csv = artifact_path(cfg, out, "PICK_AND_PLACE", "csv")
    pos_args = ["pcb", "export", "pos", pcb, "-o", str(pos_csv),
                "--format", "csv", "--units", "mm"]
    kicad_run(pos_args, verbose=verbose)

    warnings: list[str] = []
    # Convenience DRILL copy at the release root. Grab any *.drl; if multiple
    # (separate PTH/NPTH) we prefer the one without 'NPTH' in the filename.
    drills = sorted(gerber_dir.glob("*.drl"))
    pth = [p for p in drills if "NPTH" not in p.name.upper()]
    pick = pth[0] if pth else (drills[0] if drills else None)
    if pick is not None:
        dest = artifact_path(cfg, out, "DRILL", "drl")
        shutil.copy2(pick, dest)
    else:
        warnings.append("no .drl file produced; skipping top-level DRILL copy")

    artifacts = sorted(gerber_dir.glob("*"))
    if pos_csv.exists():
        artifacts.append(pos_csv)
    return artifacts, warnings
