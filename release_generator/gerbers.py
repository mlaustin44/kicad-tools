"""Gerbers, drill files, drill report, and pick-and-place export."""
from __future__ import annotations
from pathlib import Path
from .config import Config
from .kicad_cli import run as kicad_run
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

    # Drill files (Excellon) + drill map (PDF) + drill report
    drill_args = ["pcb", "export", "drill", pcb, "-o", str(gerber_dir) + "/",
                  "--generate-map", "--map-format", "pdf",
                  "--generate-report"]
    kicad_run(drill_args, verbose=verbose)

    # Pick-and-place
    pos_csv = out / "pick-and-place.csv"
    pos_args = ["pcb", "export", "pos", pcb, "-o", str(pos_csv),
                "--format", "csv", "--units", "mm"]
    kicad_run(pos_args, verbose=verbose)

    artifacts = sorted(gerber_dir.glob("*"))
    if pos_csv.exists():
        artifacts.append(pos_csv)
    return artifacts, []
