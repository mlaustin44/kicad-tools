"""STEP 3D model export via `kicad-cli pcb export step`."""
from __future__ import annotations
from pathlib import Path

from .config import Config
from .kicad_cli import run as kicad_run, KicadCliError
from .naming import artifact_path
from .utils import output_dir_for


def export_step(cfg: Config, *, verbose: bool) -> tuple[Path, list[str]]:
    out = artifact_path(cfg, output_dir_for(cfg), "3D", "step")
    # --subst-models: when a footprint only has a VRML 3D model (which STEP,
    # being BREP-based, can't embed), kicad-cli substitutes it rather than
    # erroring. Without this, any board using any VRML-only model fails.
    kicad_run(["pcb", "export", "step", str(cfg.project.pcb_file),
               "-o", str(out), "--force", "--subst-models"],
              verbose=verbose, timeout=600)
    if not out.exists():
        raise KicadCliError(f"kicad-cli pcb export step did not produce {out}")
    return out, []
