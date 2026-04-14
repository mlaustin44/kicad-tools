"""Schematic PDF export with title block variable injection."""
from __future__ import annotations
from pathlib import Path
from .config import Config
from .kicad_cli import run as kicad_run
from .utils import output_dir_for


def schematic_vars(cfg: Config) -> dict[str, str]:
    """Build the variable map injected into the schematic title block."""
    base = {
        "TITLE": cfg.project.name,
        "REV": cfg.project.version,
        "DATE": cfg.project.date,
        "COMPANY": cfg.titleblock.company,
    }
    base.update(cfg.schematic.extra_vars)
    return base


def export_schematic_pdf(cfg: Config, *, verbose: bool) -> tuple[Path, list[str]]:
    out_pdf = output_dir_for(cfg) / "schematic.pdf"
    args = ["sch", "export", "pdf", str(cfg.project.schematic_file),
            "-o", str(out_pdf)]
    for k, v in schematic_vars(cfg).items():
        args += ["--define-var", f"{k}={v}"]
    kicad_run(args, verbose=verbose)
    warnings: list[str] = []
    if not out_pdf.exists():
        raise RuntimeError(f"expected output {out_pdf} not produced")
    return out_pdf, warnings
