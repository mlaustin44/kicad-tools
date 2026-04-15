"""Misc helpers: lock-file detection, output directory scaffolding."""
from __future__ import annotations
from pathlib import Path
from .config import Config


class PreflightError(RuntimeError):
    """Raised when preflight checks fail."""


def lock_files_for(target: Path) -> list[Path]:
    """KiCad creates files like `~name.kicad_pcb.lck` next to open files."""
    return [target.parent / f"~{target.name}.lck"]


def check_no_locks(*targets: Path) -> None:
    bad = []
    for t in targets:
        for lck in lock_files_for(t):
            if lck.exists():
                bad.append(str(lck))
    if bad:
        raise PreflightError(
            "the following files appear to be open in KiCad (lock files exist): "
            + ", ".join(bad) + ". Close KiCad and retry."
        )


def output_dir_for(cfg: Config) -> Path:
    return cfg.config_dir / "releases" / cfg.release_dir_name


def scratch_dir_for(cfg: Config) -> Path:
    return output_dir_for(cfg) / ".scratch"


def scaffold_output_dir(cfg: Config) -> Path:
    out = output_dir_for(cfg)
    out.mkdir(parents=True, exist_ok=True)
    (out / "gerbers").mkdir(exist_ok=True)
    scratch_dir_for(cfg).mkdir(exist_ok=True)
    return out
