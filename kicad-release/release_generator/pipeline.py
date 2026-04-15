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
from .project_dump import dump_project
from .render3d import render_pcb
from .schematic import export_schematic_pdf
from .step import export_step
from .stl import export_stl
from .utils import check_no_locks, scaffold_output_dir, output_dir_for, PreflightError

STEP_NAMES = [
    "preflight",
    "schematic",
    "bom",
    "gerbers",
    "render",
    "fab-drawing",
    "assembly-drawing",
    "step",
    "stl",
    "kicad-dump",
]


@dataclass
class StepResult:
    name: str
    artifacts: list[Path]
    warnings: list[str]


def _skipped(name: str, reason: str) -> StepResult:
    return StepResult(name=name, artifacts=[], warnings=[f"skipped: {reason}"])


def step_preflight(cfg: Config, *, verbose: bool) -> StepResult:
    check_version()
    check_no_locks(cfg.project.pcb_file, cfg.project.schematic_file)
    out = scaffold_output_dir(cfg)
    return StepResult(name="preflight", artifacts=[out], warnings=[])


def step_schematic(cfg: Config, *, verbose: bool) -> StepResult:
    if not cfg.schematic.enabled:
        return _skipped("schematic", "[schematic].enabled = false")
    pdf, warnings = export_schematic_pdf(cfg, verbose=verbose)
    return StepResult(name="schematic", artifacts=[pdf], warnings=warnings)


def step_gerbers(cfg: Config, *, verbose: bool) -> StepResult:
    if not cfg.gerbers.enabled:
        return _skipped("gerbers", "[gerbers].enabled = false")
    artifacts, warnings = export_gerbers(cfg, verbose=verbose)
    return StepResult(name="gerbers", artifacts=artifacts, warnings=warnings)


def step_bom(cfg: Config, *, verbose: bool) -> StepResult:
    if not cfg.bom.enabled:
        return _skipped("bom", "[bom].enabled = false")
    bom_csv, warnings = generate_bom(cfg, verbose=verbose)
    return StepResult(name="bom", artifacts=[bom_csv], warnings=warnings)


def step_render(cfg: Config, *, verbose: bool) -> StepResult:
    pngs, warnings = render_pcb(cfg, verbose=verbose)
    return StepResult(name="render", artifacts=pngs, warnings=warnings)


def step_fab_drawing(cfg: Config, *, verbose: bool) -> StepResult:
    if not cfg.fab_drawing.enabled:
        return _skipped("fab-drawing", "[fab_drawing].enabled = false")
    pdf, warnings = compose_fab_drawing(cfg, verbose=verbose)
    return StepResult(name="fab-drawing", artifacts=[pdf], warnings=warnings)


def step_assembly_drawing(cfg: Config, *, verbose: bool) -> StepResult:
    if not cfg.assembly_drawing.enabled:
        return _skipped("assembly-drawing", "[assembly_drawing].enabled = false")
    pdf, warnings = compose_assembly_drawing(cfg, verbose=verbose)
    return StepResult(name="assembly-drawing", artifacts=[pdf],
                      warnings=warnings)


def step_step(cfg: Config, *, verbose: bool) -> StepResult:
    if not cfg.step.enabled:
        return _skipped("step", "[step].enabled = false")
    path, warnings = export_step(cfg, verbose=verbose)
    return StepResult(name="step", artifacts=[path], warnings=warnings)


def step_stl(cfg: Config, *, verbose: bool) -> StepResult:
    if not cfg.stl.enabled:
        return _skipped("stl", "[stl].enabled = false")
    path, warnings = export_stl(cfg, verbose=verbose)
    return StepResult(name="stl", artifacts=[path], warnings=warnings)


def step_kicad_dump(cfg: Config, *, verbose: bool) -> StepResult:
    if not cfg.kicad_project_dump.enabled:
        return _skipped("kicad-dump", "[kicad_project_dump].enabled = false")
    paths, warnings = dump_project(cfg, verbose=verbose)
    return StepResult(name="kicad-dump", artifacts=paths, warnings=warnings)


STEPS = {
    "preflight": step_preflight,
    "schematic": step_schematic,
    "bom": step_bom,
    "gerbers": step_gerbers,
    "render": step_render,
    "fab-drawing": step_fab_drawing,
    "assembly-drawing": step_assembly_drawing,
    "step": step_step,
    "stl": step_stl,
    "kicad-dump": step_kicad_dump,
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

    if "preflight" not in selected:
        selected = ["preflight"] + selected

    import sys
    import time

    if dry_run:
        print(f"Project: {cfg.project.name} v{cfg.project.version}")
        print(f"Output: {output_dir_for(cfg)}")
        for name in selected:
            print(f"[dry-run] would execute: {name}")
        return 0

    print(f"Project: {cfg.project.name} v{cfg.project.version}")
    print(f"Output:  {output_dir_for(cfg)}\n")

    results: list[StepResult] = []
    for name in selected:
        print(f"[{name}] …", end="", flush=True)
        t0 = time.monotonic()
        try:
            r = STEPS[name](cfg, verbose=verbose)
        except (KicadCliError, PreflightError) as e:
            print(f" failed ({time.monotonic() - t0:.1f}s)")
            print(f"  {e}", file=sys.stderr)
            return 2 if name == "preflight" else 3
        elapsed = time.monotonic() - t0
        status = "skipped" if any(w.startswith("skipped:") for w in r.warnings) \
                 else f"{len(r.artifacts)} artifact(s)"
        print(f" {status} ({elapsed:.1f}s)")
        for w in r.warnings:
            if not w.startswith("skipped:"):
                print(f"  warn: {w}")
        results.append(r)

    print("\n--- Summary ---")
    for r in results:
        print(f"  {r.name}: {len(r.artifacts)} artifact(s), {len(r.warnings)} warning(s)")
    return 0
