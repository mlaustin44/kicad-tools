"""Pipeline orchestration. Steps are filled in by later tasks."""
from __future__ import annotations
from dataclasses import dataclass

from .config import load_config, ConfigError

STEP_NAMES = [
    "preflight",
    "schematic",
    "bom",
    "gerbers",
    "render",
    "fab-drawing",
    "assembly-drawing",
]


@dataclass
class StepResult:
    name: str
    artifacts: list[str]
    warnings: list[str]


def run_pipeline(config_path: str, only: list[str] | None, dry_run: bool,
                 keep_scratch: bool, verbose: bool) -> int:
    try:
        cfg = load_config(config_path)
    except ConfigError as e:
        print(f"config error: {e}")
        return 1
    selected = only if only else STEP_NAMES
    unknown = [s for s in selected if s not in STEP_NAMES]
    if unknown:
        print(f"error: unknown step(s): {unknown}. Valid: {STEP_NAMES}")
        return 1
    if dry_run:
        print(f"Project: {cfg.project.name} v{cfg.project.version}")
        print(f"Output: releases/{cfg.release_dir_name}/")
        for name in selected:
            print(f"[dry-run] would execute: {name}")
        return 0
    for name in selected:
        print(f"[stub] {name} not implemented yet")
    return 0
