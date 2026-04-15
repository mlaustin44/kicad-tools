"""Copy the core KiCad project files into the release under ``kicad/``.

Included (native filenames):
  - <name>.kicad_pro
  - <name>.kicad_pcb
  - all *.kicad_sch (covers hierarchical sheets)
  - <name>.kicad_dru  (if present)
"""
from __future__ import annotations
import shutil
from pathlib import Path

from .config import Config
from .utils import output_dir_for


def dump_project(cfg: Config, *, verbose: bool) -> tuple[list[Path], list[str]]:
    src_dir = cfg.project.pcb_file.parent
    stem = cfg.project.pcb_file.stem
    dest_dir = output_dir_for(cfg) / "kicad"
    dest_dir.mkdir(parents=True, exist_ok=True)

    to_copy: list[Path] = []
    candidates = [
        src_dir / f"{stem}.kicad_pro",
        src_dir / f"{stem}.kicad_pcb",
        src_dir / f"{stem}.kicad_dru",
    ]
    for p in candidates:
        if p.exists():
            to_copy.append(p)
    # All schematic sheets (root + hierarchical) live in src_dir.
    to_copy.extend(sorted(src_dir.glob("*.kicad_sch")))

    warnings: list[str] = []
    copied: list[Path] = []
    for src in to_copy:
        dest = dest_dir / src.name
        shutil.copy2(src, dest)
        copied.append(dest)
    if not any(p.suffix == ".kicad_pro" for p in copied):
        warnings.append(f"no .kicad_pro found next to {cfg.project.pcb_file}")
    return copied, warnings
