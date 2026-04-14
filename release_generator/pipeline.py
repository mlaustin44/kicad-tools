"""Pipeline orchestration. Steps are filled in by later tasks."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

# Step name → (description, function). Functions take a Config + run-context kwargs;
# in the scaffold they only print what they would do.
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
    """Returns process exit code."""
    selected = only if only else STEP_NAMES
    unknown = [s for s in selected if s not in STEP_NAMES]
    if unknown:
        print(f"error: unknown step(s): {unknown}. Valid: {STEP_NAMES}")
        return 1
    for name in selected:
        if dry_run:
            print(f"[dry-run] would execute: {name}")
        else:
            print(f"[stub] {name} not implemented yet")
    return 0
