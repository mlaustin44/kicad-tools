"""Artifact file-naming helpers.

All per-release artifacts follow the pattern:
    <file_name>_<version>_<SUFFIX>.<ext>

Exceptions live in known subfolders with native filenames:
    gerbers/*  (gerber and drill files)
    kicad/*    (core KiCad project files)
"""
from __future__ import annotations
from pathlib import Path
from .config import Config


def prefix(cfg: Config) -> str:
    """`<file_name>_<version>` — the repeated prefix on every artifact name."""
    return f"{cfg.project.file_name}_{cfg.project.version}"


def artifact_path(cfg: Config, out_dir: Path, suffix: str, ext: str) -> Path:
    """Return <out_dir>/<file_name>_<version>_<SUFFIX>.<ext>."""
    name = f"{prefix(cfg)}_{suffix}.{ext.lstrip('.')}"
    return out_dir / name
