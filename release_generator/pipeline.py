"""Pipeline orchestration."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from .assembly_drawing import compose_assembly_drawing
from .bom import generate_bom
from .config import load_config, ConfigError, Config
from .fab_drawing import compose_fab_drawing
from .gerbers import export_gerbers
from .kicad_cli import check_version, KicadCliError
from .render3d import render_pcb
from .schematic import export_schematic_pdf
from .utils import check_no_locks, scaffold_output_dir, output_dir_for, PreflightError

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
    artifacts: list[Path]
    warnings: list[str]


def step_preflight(cfg: Config, *, verbose: bool) -> StepResult:
    check_version()
    check_no_locks(cfg.project.pcb_file, cfg.project.schematic_file)
    out = scaffold_output_dir(cfg)
    return StepResult(name="preflight", artifacts=[out], warnings=[])


def step_schematic(cfg: Config, *, verbose: bool) -> StepResult:
    pdf, warnings = export_schematic_pdf(cfg, verbose=verbose)
    return StepResult(name="schematic", artifacts=[pdf], warnings=warnings)


def step_gerbers(cfg: Config, *, verbose: bool) -> StepResult:
    artifacts, warnings = export_gerbers(cfg, verbose=verbose)
    return StepResult(name="gerbers", artifacts=artifacts, warnings=warnings)


def step_bom(cfg: Config, *, verbose: bool) -> StepResult:
    bom_csv, warnings = generate_bom(cfg, verbose=verbose)
    return StepResult(name="bom", artifacts=[bom_csv], warnings=warnings)


def step_render(cfg: Config, *, verbose: bool) -> StepResult:
    pngs, warnings = render_pcb(cfg, verbose=verbose)
    return StepResult(name="render", artifacts=pngs, warnings=warnings)


def step_fab_drawing(cfg: Config, *, verbose: bool) -> StepResult:
    pdf, warnings = compose_fab_drawing(cfg, verbose=verbose)
    return StepResult(name="fab-drawing", artifacts=[pdf], warnings=warnings)


def step_assembly_drawing(cfg: Config, *, verbose: bool) -> StepResult:
    pdf, warnings = compose_assembly_drawing(cfg, verbose=verbose)
    return StepResult(name="assembly-drawing", artifacts=[pdf],
                      warnings=warnings)


def _stub(name: str):
    def fn(cfg: Config, *, verbose: bool) -> StepResult:
        print(f"[stub] {name} not implemented yet")
        return StepResult(name=name, artifacts=[], warnings=[])
    return fn


STEPS = {
    "preflight": step_preflight,
    "schematic": step_schematic,
    "bom": step_bom,
    "gerbers": step_gerbers,
    "render": step_render,
    "fab-drawing": step_fab_drawing,
    "assembly-drawing": step_assembly_drawing,
}


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

    # preflight is always implicit unless explicitly excluded by --only
    if "preflight" not in selected:
        selected = ["preflight"] + selected

    if dry_run:
        print(f"Project: {cfg.project.name} v{cfg.project.version}")
        print(f"Output: {output_dir_for(cfg)}")
        for name in selected:
            print(f"[dry-run] would execute: {name}")
        return 0

    results: list[StepResult] = []
    for name in selected:
        try:
            r = STEPS[name](cfg, verbose=verbose)
            results.append(r)
        except (KicadCliError, PreflightError) as e:
            print(f"[{name}] failed: {e}")
            return 2 if name == "preflight" else 3

    print("\n--- Summary ---")
    for r in results:
        print(f"  {r.name}: {len(r.artifacts)} artifact(s), {len(r.warnings)} warning(s)")
        for w in r.warnings:
            print(f"    warn: {w}")
    return 0
