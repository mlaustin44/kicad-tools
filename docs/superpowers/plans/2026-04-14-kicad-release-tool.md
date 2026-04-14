# KiCad Release Automation Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI tool (`kicad-release`) that generates a complete versioned production release package (schematic PDF, fab/assembly drawings, gerbers, drill, BOM, pick-and-place) from a KiCad 10 project given a TOML config.

**Architecture:** Single Python package (`release_generator`) with one module per pipeline step. Each step shells out to `kicad-cli` for KiCad-native operations and uses Python (lxml + CairoSVG) for SVG template composition. Pipeline is orchestrated by `pipeline.py` driven from an argparse CLI.

**Tech Stack:** Python 3.11+, `tomllib` (stdlib), `lxml`, `cairosvg`, `Pillow`, `pytest`, `kicad-cli` (system), Inkscape (system, optional fallback).

**Spec:** `docs/superpowers/specs/2026-04-14-kicad-release-tool-design.md`

**Test fixture:** `<test-project-path>` — referenced via `KICAD_TEST_PROJECT` env var, integration tests skip cleanly if unset.

**Testing posture:** Unit tests only for obvious candidates (config validation, SVG placeholder substitution, BOM CSV reshape). Everything else manual smoke testing first; promote to integration test if any area needs >1 fix cycle.

---

## File Structure

```
release_generator/
├── __init__.py             # Package metadata; __version__
├── __main__.py             # CLI entry point; argparse; dispatches to pipeline
├── config.py               # TOML load + validation (dataclasses, no pydantic)
├── pipeline.py             # Orchestrates ordered steps; --only filtering
├── kicad_cli.py            # Subprocess wrapper; version check; error handling
├── utils.py                # Path helpers; lock-file detection; output dir scaffolding
├── board_introspect.py     # Parse .kicad_pcb S-expression for stackup/dimensions/layers
├── schematic.py            # kicad-cli sch export pdf with --define-var
├── gerbers.py              # gerbers + drill + pick-and-place exports
├── bom.py                  # kicad-cli sch export bom + post-process to config columns/grouping
├── render3d.py             # kicad-cli pcb render → PNG
├── svg_template.py         # Load SVG, substitute {{placeholders}} and id="region" rects
├── svg_to_pdf.py           # CairoSVG primary; Inkscape CLI fallback
├── fab_drawing.py          # Compose fab drawing
└── assembly_drawing.py     # Compose assembly drawing

tests/
├── conftest.py             # KICAD_TEST_PROJECT env var → fixture path; skip-if-unset marker
├── unit/
│   ├── test_config.py
│   ├── test_svg_template.py
│   └── test_bom.py
└── integration/
    ├── test_kicad_cli.py
    ├── test_board_introspect.py
    ├── test_gerbers.py
    ├── test_schematic.py
    ├── test_bom_integration.py
    ├── test_render3d.py
    ├── test_fab_drawing.py
    ├── test_assembly_drawing.py
    └── test_pipeline_e2e.py

templates/
└── titleblock_a4.svg       # Example SVG title block, authored in Inkscape

pyproject.toml              # Build config; entry point: kicad-release = release_generator.__main__:main
README.md                   # Usage + Inkscape template authoring guide

example/
├── release.toml            # Sample config matching the spec
└── README.md               # How to use the example
```

---

## Task 1: Project Scaffold + CLI Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `release_generator/__init__.py`
- Create: `release_generator/__main__.py`
- Create: `release_generator/pipeline.py` (skeleton only — empty step functions)
- Create: `tests/conftest.py`
- Create: `.gitignore`

- [ ] **Step 1: Create `.gitignore`**

```
__pycache__/
*.pyc
*.egg-info/
.pytest_cache/
.venv/
build/
dist/
releases/
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "kicad-release"
version = "0.1.0"
description = "Generate production release packages from KiCad projects"
requires-python = ">=3.11"
dependencies = [
    "lxml>=5.0",
    "cairosvg>=2.7",
    "Pillow>=10.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
kicad-release = "release_generator.__main__:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["release_generator*"]
```

- [ ] **Step 3: Create `release_generator/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Create `release_generator/pipeline.py` (skeleton)**

```python
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
```

- [ ] **Step 5: Create `release_generator/__main__.py`**

```python
"""CLI entry point."""
from __future__ import annotations
import argparse
import sys
from . import __version__
from .pipeline import run_pipeline, STEP_NAMES


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kicad-release",
        description="Generate a production release package from a KiCad project.",
    )
    p.add_argument("--config", required=True, help="Path to release.toml")
    p.add_argument("--only", action="append", default=None, metavar="STEP",
                   help=f"Run a single step (repeatable). Valid: {', '.join(STEP_NAMES)}")
    p.add_argument("--dry-run", action="store_true",
                   help="Print steps and outputs without executing")
    p.add_argument("--keep-scratch", action="store_true",
                   help="Keep intermediate files in releases/{ver}/.scratch/")
    p.add_argument("--verbose", action="store_true",
                   help="Stream full kicad-cli output")
    p.add_argument("--version", action="version", version=f"kicad-release {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_pipeline(
        config_path=args.config,
        only=args.only,
        dry_run=args.dry_run,
        keep_scratch=args.keep_scratch,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Create `tests/conftest.py`**

```python
"""Shared pytest fixtures and markers."""
from __future__ import annotations
import os
import pytest
from pathlib import Path

KICAD_TEST_PROJECT_ENV = "KICAD_TEST_PROJECT"


@pytest.fixture
def kicad_project() -> Path:
    """Path to a real KiCad project for integration tests."""
    raw = os.environ.get(KICAD_TEST_PROJECT_ENV)
    if not raw:
        pytest.skip(
            f"integration tests require a real KiCad project; "
            f"set the {KICAD_TEST_PROJECT_ENV} env var to a project directory"
        )
    path = Path(raw)
    if not path.exists():
        pytest.skip(f"KICAD_TEST_PROJECT path does not exist: {path}")
    return path
```

- [ ] **Step 7: Install package in editable mode and verify CLI**

Run:
```bash
cd /home/mlaustin/repos/personal/kicad-tools
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/kicad-release --version
.venv/bin/kicad-release --config nonexistent.toml --dry-run
```

Expected:
- Version line: `kicad-release 0.1.0`
- Dry-run output lists all 7 steps prefixed with `[dry-run] would execute:`

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml release_generator/ tests/conftest.py .gitignore
git commit -m "Scaffold kicad-release package and CLI skeleton"
```

---

## Task 2: Config Loader + Validation

**Files:**
- Create: `release_generator/config.py`
- Create: `tests/unit/test_config.py`
- Create: `tests/unit/__init__.py` (empty)

- [ ] **Step 1: Write failing unit tests in `tests/unit/test_config.py`**

```python
"""Unit tests for config loading and validation."""
from __future__ import annotations
import datetime
import textwrap
import pytest
from pathlib import Path
from release_generator.config import load_config, ConfigError


def write_minimal_config(tmp_path: Path, **overrides) -> Path:
    """Write a minimal valid config plus dummy referenced files."""
    (tmp_path / "board.kicad_pcb").touch()
    (tmp_path / "board.kicad_sch").touch()
    (tmp_path / "tb.svg").write_text("<svg/>")
    body = textwrap.dedent(f"""
        [project]
        name = "Test"
        version = "{overrides.get('version', '1.0')}"
        date = "{overrides.get('date', '2026-04-14')}"
        pcb_file = "board.kicad_pcb"
        schematic_file = "board.kicad_sch"

        [titleblock]
        template = "tb.svg"
        company = "ACME"
        drawn_by = "M Test"
        confidentiality = "PROPRIETARY"

        [[revisions]]
        rev = "01"
        ec = "N/A"
        description = "Initial"

        [fab_drawing]
        title = "Fab Drawing"
        page_size = "A4"
        notes = ["Note 1"]
        include_3d_render = true
        render_view = "{overrides.get('render_view', 'top')}"

        [assembly_drawing]
        title = "Assembly Drawing"
        page_size = "A4"
        notes = ["Note 1"]
        layers_front = ["F.Fab", "Edge.Cuts"]
        layers_back = ["B.Fab", "Edge.Cuts"]

        [bom]
        group_by = ["value"]
        columns = ["reference", "value", "quantity"]

        [gerbers]
        layers = "auto"
        subtract_soldermask = false
    """).strip()
    cfg = tmp_path / "release.toml"
    cfg.write_text(body)
    return cfg


def test_loads_minimal_valid_config(tmp_path):
    cfg_path = write_minimal_config(tmp_path)
    cfg = load_config(cfg_path)
    assert cfg.project.name == "Test"
    assert cfg.project.version == "1.0"
    assert cfg.project.pcb_file.name == "board.kicad_pcb"
    assert cfg.titleblock.company == "ACME"
    assert len(cfg.revisions) == 1
    assert cfg.gerbers.layers == "auto"


def test_resolves_paths_relative_to_config(tmp_path):
    cfg_path = write_minimal_config(tmp_path)
    cfg = load_config(cfg_path)
    assert cfg.project.pcb_file.is_absolute()
    assert cfg.project.pcb_file == (tmp_path / "board.kicad_pcb").resolve()


def test_date_auto_resolves_to_today(tmp_path):
    cfg_path = write_minimal_config(tmp_path, date="auto")
    cfg = load_config(cfg_path)
    assert cfg.project.date == datetime.date.today().isoformat()


def test_rejects_missing_pcb_file(tmp_path):
    cfg_path = write_minimal_config(tmp_path)
    (tmp_path / "board.kicad_pcb").unlink()
    with pytest.raises(ConfigError, match="pcb_file"):
        load_config(cfg_path)


def test_rejects_empty_version(tmp_path):
    cfg_path = write_minimal_config(tmp_path, version="")
    with pytest.raises(ConfigError, match="version"):
        load_config(cfg_path)


def test_rejects_invalid_render_view(tmp_path):
    cfg_path = write_minimal_config(tmp_path, render_view="sideways")
    with pytest.raises(ConfigError, match="render_view"):
        load_config(cfg_path)


def test_rejects_zero_revisions(tmp_path):
    cfg_path = write_minimal_config(tmp_path)
    text = cfg_path.read_text()
    text = text.replace('[[revisions]]\nrev = "01"\nec = "N/A"\ndescription = "Initial"', '')
    cfg_path.write_text(text)
    with pytest.raises(ConfigError, match="revisions"):
        load_config(cfg_path)


def test_sanitizes_version_for_directory(tmp_path):
    cfg_path = write_minimal_config(tmp_path, version="3.2/../evil")
    cfg = load_config(cfg_path)
    assert "/" not in cfg.release_dir_name
    assert ".." not in cfg.release_dir_name


def test_gerbers_layers_explicit_list(tmp_path):
    cfg_path = write_minimal_config(tmp_path)
    text = cfg_path.read_text().replace('layers = "auto"', 'layers = ["F.Cu", "B.Cu"]')
    cfg_path.write_text(text)
    cfg = load_config(cfg_path)
    assert cfg.gerbers.layers == ["F.Cu", "B.Cu"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
.venv/bin/pytest tests/unit/test_config.py -v
```

Expected: all FAIL with `ModuleNotFoundError: No module named 'release_generator.config'`

- [ ] **Step 3: Implement `release_generator/config.py`**

```python
"""TOML config loader and validator."""
from __future__ import annotations
import datetime
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union


class ConfigError(ValueError):
    """Raised on any config validation failure."""


@dataclass
class ProjectConfig:
    name: str
    version: str
    date: str
    pcb_file: Path
    schematic_file: Path


@dataclass
class TitleblockConfig:
    template: Path
    company: str
    drawn_by: str
    confidentiality: str
    logo_file: Path | None = None


@dataclass
class RevisionEntry:
    rev: str
    ec: str
    description: str


@dataclass
class SchematicConfig:
    extra_vars: dict[str, str] = field(default_factory=dict)


@dataclass
class FabDrawingConfig:
    title: str
    page_size: str
    notes: list[str]
    include_3d_render: bool
    render_view: str
    template: Path | None = None


@dataclass
class AssemblyDrawingConfig:
    title: str
    page_size: str
    notes: list[str]
    layers_front: list[str]
    layers_back: list[str]
    template: Path | None = None


@dataclass
class BomConfig:
    group_by: list[str]
    columns: list[str]


@dataclass
class GerbersConfig:
    layers: Union[str, list[str]]  # "auto" or explicit list
    subtract_soldermask: bool


@dataclass
class Config:
    project: ProjectConfig
    titleblock: TitleblockConfig
    revisions: list[RevisionEntry]
    schematic: SchematicConfig
    fab_drawing: FabDrawingConfig
    assembly_drawing: AssemblyDrawingConfig
    bom: BomConfig
    gerbers: GerbersConfig
    config_dir: Path

    @property
    def release_dir_name(self) -> str:
        """Sanitized version string safe for use as a directory name."""
        return re.sub(r"[^A-Za-z0-9._-]", "_", self.project.version)


def _require(d: dict, section: str, key: str):
    if key not in d:
        raise ConfigError(f"[{section}] missing required key '{key}'")
    return d[key]


def _resolve_path(base: Path, rel: str, must_exist: bool, label: str) -> Path:
    p = (base / rel).resolve()
    if must_exist and not p.exists():
        raise ConfigError(f"{label} not found: {p}")
    return p


def load_config(config_path: str | Path) -> Config:
    config_path = Path(config_path).resolve()
    if not config_path.exists():
        raise ConfigError(f"config file not found: {config_path}")
    with open(config_path, "rb") as f:
        raw = tomllib.load(f)
    base = config_path.parent

    # [project]
    proj_raw = _require(raw, "root", "project")
    version = str(_require(proj_raw, "project", "version"))
    if not version.strip():
        raise ConfigError("[project] version must be non-empty")
    date = str(_require(proj_raw, "project", "date"))
    if date == "auto":
        date = datetime.date.today().isoformat()
    project = ProjectConfig(
        name=str(_require(proj_raw, "project", "name")),
        version=version,
        date=date,
        pcb_file=_resolve_path(base, _require(proj_raw, "project", "pcb_file"),
                               must_exist=True, label="[project] pcb_file"),
        schematic_file=_resolve_path(base, _require(proj_raw, "project", "schematic_file"),
                                     must_exist=True, label="[project] schematic_file"),
    )

    # [titleblock]
    tb_raw = _require(raw, "root", "titleblock")
    titleblock = TitleblockConfig(
        template=_resolve_path(base, _require(tb_raw, "titleblock", "template"),
                               must_exist=True, label="[titleblock] template"),
        company=str(_require(tb_raw, "titleblock", "company")),
        drawn_by=str(_require(tb_raw, "titleblock", "drawn_by")),
        confidentiality=str(_require(tb_raw, "titleblock", "confidentiality")),
        logo_file=(_resolve_path(base, tb_raw["logo_file"], must_exist=True,
                                 label="[titleblock] logo_file")
                   if "logo_file" in tb_raw else None),
    )

    # [[revisions]]
    revs_raw = raw.get("revisions", [])
    if not revs_raw:
        raise ConfigError("at least one [[revisions]] entry is required")
    revisions = [RevisionEntry(rev=str(r["rev"]), ec=str(r["ec"]),
                               description=str(r["description"]))
                 for r in revs_raw]

    # [schematic] (optional)
    sch_raw = raw.get("schematic", {})
    schematic = SchematicConfig(
        extra_vars={str(k): str(v) for k, v in sch_raw.get("extra_vars", {}).items()},
    )

    # [fab_drawing]
    fab_raw = _require(raw, "root", "fab_drawing")
    render_view = str(fab_raw.get("render_view", "top"))
    if render_view not in ("top", "bottom", "both"):
        raise ConfigError(f"[fab_drawing] render_view must be one of "
                          f"top/bottom/both, got '{render_view}'")
    fab = FabDrawingConfig(
        title=str(_require(fab_raw, "fab_drawing", "title")),
        page_size=str(_require(fab_raw, "fab_drawing", "page_size")),
        notes=[str(n) for n in fab_raw.get("notes", [])],
        include_3d_render=bool(fab_raw.get("include_3d_render", False)),
        render_view=render_view,
        template=(_resolve_path(base, fab_raw["template"], must_exist=True,
                                label="[fab_drawing] template")
                  if "template" in fab_raw else None),
    )

    # [assembly_drawing]
    asm_raw = _require(raw, "root", "assembly_drawing")
    asm = AssemblyDrawingConfig(
        title=str(_require(asm_raw, "assembly_drawing", "title")),
        page_size=str(_require(asm_raw, "assembly_drawing", "page_size")),
        notes=[str(n) for n in asm_raw.get("notes", [])],
        layers_front=[str(l) for l in asm_raw.get("layers_front", [])],
        layers_back=[str(l) for l in asm_raw.get("layers_back", [])],
        template=(_resolve_path(base, asm_raw["template"], must_exist=True,
                                label="[assembly_drawing] template")
                  if "template" in asm_raw else None),
    )

    # [bom]
    bom_raw = _require(raw, "root", "bom")
    bom = BomConfig(
        group_by=[str(g) for g in bom_raw.get("group_by", [])],
        columns=[str(c) for c in bom_raw.get("columns", [])],
    )

    # [gerbers]
    gb_raw = _require(raw, "root", "gerbers")
    gb_layers = gb_raw.get("layers", "auto")
    if not (gb_layers == "auto" or
            (isinstance(gb_layers, list) and all(isinstance(x, str) for x in gb_layers))):
        raise ConfigError("[gerbers] layers must be \"auto\" or a list of strings")
    gerbers = GerbersConfig(
        layers=gb_layers,
        subtract_soldermask=bool(gb_raw.get("subtract_soldermask", False)),
    )

    return Config(
        project=project, titleblock=titleblock, revisions=revisions,
        schematic=schematic, fab_drawing=fab, assembly_drawing=asm,
        bom=bom, gerbers=gerbers, config_dir=base,
    )
```

- [ ] **Step 4: Run unit tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_config.py -v`
Expected: all PASS.

- [ ] **Step 5: Wire config loading into pipeline.py**

Update `release_generator/pipeline.py` — replace the existing `run_pipeline` body so that it loads the config and prints a summary on dry-run:

```python
from .config import load_config, ConfigError

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
```

- [ ] **Step 6: Manual smoke test against real project**

Create `example/release.toml` matching the spec exactly, with paths relative to the example dir, then:
```bash
.venv/bin/kicad-release --config example/release.toml --dry-run
```
Expected: project name, version, output dir, then all 7 steps listed.

Note: example/release.toml will reference the test fixture board files. Use absolute paths or symlink the fixture files into example/. For now, easier path: put the example release.toml in the test fixture directory directly during this manual check.

- [ ] **Step 7: Commit**

```bash
git add release_generator/config.py release_generator/pipeline.py tests/unit/
git commit -m "Add TOML config loader with validation"
```

---

## Task 3: kicad-cli Wrapper + Preflight

**Files:**
- Create: `release_generator/kicad_cli.py`
- Create: `release_generator/utils.py`
- Modify: `release_generator/pipeline.py` — wire preflight step
- Create: `tests/integration/__init__.py` (empty)
- Create: `tests/integration/test_kicad_cli.py`

- [ ] **Step 1: Create `release_generator/kicad_cli.py`**

```python
"""Wrapper around `kicad-cli` subprocess invocations."""
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path

MIN_VERSION = (10, 0, 0)


class KicadCliError(RuntimeError):
    """Raised when kicad-cli fails or is missing/too old."""


def find_kicad_cli() -> str:
    path = shutil.which("kicad-cli")
    if not path:
        raise KicadCliError("kicad-cli not found on PATH")
    return path


def get_version() -> tuple[int, int, int]:
    out = subprocess.run([find_kicad_cli(), "version"],
                         capture_output=True, text=True, timeout=10)
    if out.returncode != 0:
        raise KicadCliError(f"`kicad-cli version` failed: {out.stderr.strip()}")
    line = out.stdout.strip().splitlines()[0].strip()
    parts = line.split(".")
    if len(parts) < 3:
        raise KicadCliError(f"unparseable kicad-cli version: '{line}'")
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2].split("-")[0]))
    except ValueError:
        raise KicadCliError(f"unparseable kicad-cli version: '{line}'")


def check_version() -> None:
    v = get_version()
    if v < MIN_VERSION:
        raise KicadCliError(f"kicad-cli {'.'.join(map(str, v))} is too old; "
                            f"requires {'.'.join(map(str, MIN_VERSION))}+")


def run(args: list[str], *, cwd: Path | None = None, verbose: bool = False,
        timeout: int = 600) -> subprocess.CompletedProcess:
    """Invoke `kicad-cli` with the given args. Raises KicadCliError on failure."""
    cmd = [find_kicad_cli()] + args
    if verbose:
        print(f"$ {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=cwd, capture_output=not verbose, text=True,
                         timeout=timeout)
    if res.returncode != 0:
        stderr = res.stderr if not verbose else "(streamed above)"
        raise KicadCliError(
            f"kicad-cli {' '.join(args[:2])} failed (exit {res.returncode}): {stderr}"
        )
    return res
```

- [ ] **Step 2: Create `release_generator/utils.py`**

```python
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
```

- [ ] **Step 3: Wire preflight + output scaffolding into pipeline.py**

Replace `pipeline.py` with the full version that runs preflight and scaffolds output:

```python
"""Pipeline orchestration."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from .config import load_config, ConfigError, Config
from .kicad_cli import check_version, KicadCliError
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


def _stub(name: str):
    def fn(cfg: Config, *, verbose: bool) -> StepResult:
        print(f"[stub] {name} not implemented yet")
        return StepResult(name=name, artifacts=[], warnings=[])
    return fn


STEPS = {
    "preflight": step_preflight,
    "schematic": _stub("schematic"),
    "bom": _stub("bom"),
    "gerbers": _stub("gerbers"),
    "render": _stub("render"),
    "fab-drawing": _stub("fab-drawing"),
    "assembly-drawing": _stub("assembly-drawing"),
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
```

- [ ] **Step 4: Write integration test in `tests/integration/test_kicad_cli.py`**

```python
"""Integration tests for kicad-cli wrapper."""
from __future__ import annotations
import pytest
from release_generator.kicad_cli import (
    find_kicad_cli, get_version, check_version, run, KicadCliError, MIN_VERSION
)


def test_finds_kicad_cli():
    path = find_kicad_cli()
    assert path.endswith("kicad-cli")


def test_version_is_at_least_minimum():
    v = get_version()
    assert v >= MIN_VERSION
    check_version()  # should not raise


def test_run_succeeds_with_version():
    res = run(["version"], verbose=False, timeout=10)
    assert res.returncode == 0
    assert res.stdout.strip()


def test_run_raises_on_bogus_subcommand():
    with pytest.raises(KicadCliError):
        run(["nonexistent-subcommand"], verbose=False, timeout=10)
```

- [ ] **Step 5: Run integration test**

Run: `.venv/bin/pytest tests/integration/test_kicad_cli.py -v`
Expected: all PASS (assumes `kicad-cli` 10+ is on PATH).

- [ ] **Step 6: Manual smoke test against real project**

Create a temporary `release.toml` next to the test board (or use an existing example), then:
```bash
.venv/bin/kicad-release --config /path/to/release.toml
```
Expected:
- Preflight runs (no error if KiCad isn't open with the board)
- Other steps print their stub messages
- Summary shows preflight produced 1 artifact (the output directory)
- `releases/3.2/` and `releases/3.2/gerbers/` and `releases/3.2/.scratch/` all exist

Test failure case: open the board in KiCad GUI, re-run; expect exit code 2 with helpful "lock files exist" message.

- [ ] **Step 7: Commit**

```bash
git add release_generator/kicad_cli.py release_generator/utils.py release_generator/pipeline.py tests/integration/
git commit -m "Add kicad-cli wrapper, preflight, and output scaffolding"
```

---

## Task 4: Schematic PDF Export

**Files:**
- Create: `release_generator/schematic.py`
- Modify: `release_generator/pipeline.py` — wire `step_schematic`
- Create: `tests/integration/test_schematic.py`

- [ ] **Step 1: Implement `release_generator/schematic.py`**

```python
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
```

- [ ] **Step 2: Wire into pipeline.py**

In `pipeline.py`, replace the schematic stub:

```python
from .schematic import export_schematic_pdf

def step_schematic(cfg: Config, *, verbose: bool) -> StepResult:
    pdf, warnings = export_schematic_pdf(cfg, verbose=verbose)
    return StepResult(name="schematic", artifacts=[pdf], warnings=warnings)

# Update STEPS:
STEPS["schematic"] = step_schematic
```

- [ ] **Step 3: Write integration test in `tests/integration/test_schematic.py`**

```python
"""Integration test for schematic PDF export."""
from __future__ import annotations
import shutil
from pathlib import Path
from release_generator.config import load_config
from release_generator.schematic import export_schematic_pdf
from release_generator.utils import scaffold_output_dir


def _write_test_config(workdir: Path, kicad_project: Path) -> Path:
    """Copy the test project files alongside a release.toml in workdir."""
    sch = next(kicad_project.glob("*.kicad_sch"))
    pcb = next(kicad_project.glob("*.kicad_pcb"))
    shutil.copy(sch, workdir / sch.name)
    shutil.copy(pcb, workdir / pcb.name)
    (workdir / "tb.svg").write_text("<svg/>")
    (workdir / "release.toml").write_text(f"""
[project]
name = "Test"
version = "T1"
date = "auto"
pcb_file = "{pcb.name}"
schematic_file = "{sch.name}"

[titleblock]
template = "tb.svg"
company = "ACME"
drawn_by = "M Test"
confidentiality = "PROPRIETARY"

[[revisions]]
rev = "01"
ec = "N/A"
description = "Initial"

[fab_drawing]
title = "Fab Drawing"
page_size = "A4"
notes = []
include_3d_render = false
render_view = "top"

[assembly_drawing]
title = "Assembly Drawing"
page_size = "A4"
notes = []
layers_front = ["F.Fab", "Edge.Cuts"]
layers_back = ["B.Fab", "Edge.Cuts"]

[bom]
group_by = ["value"]
columns = ["reference", "value", "quantity"]

[gerbers]
layers = "auto"
subtract_soldermask = false
""")
    return workdir / "release.toml"


def test_schematic_pdf_is_produced(kicad_project, tmp_path):
    cfg_path = _write_test_config(tmp_path, kicad_project)
    cfg = load_config(cfg_path)
    scaffold_output_dir(cfg)
    pdf, warnings = export_schematic_pdf(cfg, verbose=False)
    assert pdf.exists()
    assert pdf.stat().st_size > 1000  # nontrivial PDF
```

- [ ] **Step 4: Run integration test**

Run: `.venv/bin/pytest tests/integration/test_schematic.py -v`
Expected: PASS, with `releases/T1/schematic.pdf` produced.

- [ ] **Step 5: Manual smoke test against real project**

```bash
.venv/bin/kicad-release --config /path/to/release.toml --only schematic
```

Open `releases/{ver}/schematic.pdf`. Verify:
- Multi-page schematic exported as single PDF
- Title block fields show config-driven values *if* the schematic title block uses `${TITLE}`, `${REV}`, `${DATE}`, `${COMPANY}` variables.
- If the title block currently uses literal text, fields will show the literal text — this is expected; user must do the one-time schematic edit (open KiCad → File → Schematic Setup → Project Variables, or edit the title block fields in eeschema).

Document this requirement in the commit message and (later) README.

- [ ] **Step 6: Commit**

```bash
git add release_generator/schematic.py release_generator/pipeline.py tests/integration/test_schematic.py
git commit -m "Add schematic PDF export with variable injection"
```

---

## Task 5: Gerbers + Drill + Pick-and-Place Export

**Files:**
- Create: `release_generator/gerbers.py`
- Modify: `release_generator/pipeline.py`
- Create: `tests/integration/test_gerbers.py`

- [ ] **Step 1: Implement `release_generator/gerbers.py`**

```python
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
                  "--generate-job-file"]
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
```

- [ ] **Step 2: Wire into pipeline.py**

Replace the gerbers stub in `pipeline.py`:

```python
from .gerbers import export_gerbers

def step_gerbers(cfg: Config, *, verbose: bool) -> StepResult:
    artifacts, warnings = export_gerbers(cfg, verbose=verbose)
    return StepResult(name="gerbers", artifacts=artifacts, warnings=warnings)

STEPS["gerbers"] = step_gerbers
```

- [ ] **Step 3: Write integration test in `tests/integration/test_gerbers.py`**

```python
"""Integration test for gerbers export."""
from __future__ import annotations
import pytest
from pathlib import Path
from release_generator.config import load_config
from release_generator.gerbers import export_gerbers
from release_generator.utils import scaffold_output_dir, output_dir_for
# Reuse helper from schematic test
from .test_schematic import _write_test_config


def test_gerbers_produces_expected_files(kicad_project, tmp_path):
    cfg_path = _write_test_config(tmp_path, kicad_project)
    cfg = load_config(cfg_path)
    scaffold_output_dir(cfg)
    artifacts, _ = export_gerbers(cfg, verbose=False)
    out = output_dir_for(cfg)
    gerber_dir = out / "gerbers"
    # Must have at least one .gbr (a copper layer) and at least one .drl
    gbr_files = list(gerber_dir.glob("*.gbr"))
    drl_files = list(gerber_dir.glob("*.drl"))
    assert gbr_files, f"no .gbr files in {gerber_dir}"
    assert drl_files, f"no .drl files in {gerber_dir}"
    # Pick-and-place CSV exists and has a header row
    pos = out / "pick-and-place.csv"
    assert pos.exists()
    assert pos.read_text().count("\n") >= 1
```

- [ ] **Step 4: Run integration test**

Run: `.venv/bin/pytest tests/integration/test_gerbers.py -v`
Expected: PASS.

- [ ] **Step 5: Manual smoke test**

```bash
.venv/bin/kicad-release --config /path/to/release.toml --only gerbers --verbose
```

Open one `.gbr` in a gerber viewer (e.g., gerbv) — verify it shows the correct layer for the test board.

- [ ] **Step 6: Commit**

```bash
git add release_generator/gerbers.py release_generator/pipeline.py tests/integration/test_gerbers.py
git commit -m "Add gerbers, drill, and pick-and-place export"
```

---

## Task 6: Board Introspection (Stackup, Dimensions, Layers)

**Files:**
- Create: `release_generator/board_introspect.py`
- Create: `tests/integration/test_board_introspect.py`

- [ ] **Step 1: Add `sexpdata` dependency**

Edit `pyproject.toml`, add `"sexpdata>=1.0"` to `dependencies`, then re-install:
```bash
.venv/bin/pip install -e ".[dev]"
```

- [ ] **Step 2: Implement `release_generator/board_introspect.py`**

```python
"""Parse .kicad_pcb S-expression for stackup, dimensions, layer info.

We parse only the fields we need rather than building a full data model.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import sexpdata


@dataclass
class StackupLayer:
    name: str
    type: str
    thickness_mm: float | None
    material: str | None


@dataclass
class BoardInfo:
    stackup: list[StackupLayer]
    enabled_layers: list[str]
    width_mm: float | None
    height_mm: float | None


def _find_first(node, key: str):
    """Return the first child sub-list whose head Symbol equals `key`."""
    for child in node[1:] if isinstance(node, list) else []:
        if isinstance(child, list) and child and isinstance(child[0], sexpdata.Symbol) \
                and child[0].value() == key:
            return child
    return None


def _find_all(node, key: str):
    out = []
    for child in node[1:] if isinstance(node, list) else []:
        if isinstance(child, list) and child and isinstance(child[0], sexpdata.Symbol) \
                and child[0].value() == key:
            out.append(child)
    return out


def _scalar(node, default=None):
    if node is None or len(node) < 2:
        return default
    return node[1]


def parse_board(pcb_path: Path) -> BoardInfo:
    text = pcb_path.read_text(encoding="utf-8")
    tree = sexpdata.loads(text)

    setup = _find_first(tree, "setup")
    stackup_node = _find_first(setup, "stackup") if setup else None
    layers: list[StackupLayer] = []
    if stackup_node:
        for layer in _find_all(stackup_node, "layer"):
            name = layer[1] if len(layer) > 1 else ""
            type_node = _find_first(layer, "type")
            thickness_node = _find_first(layer, "thickness")
            material_node = _find_first(layer, "material")
            layers.append(StackupLayer(
                name=str(name),
                type=str(_scalar(type_node, "")),
                thickness_mm=float(_scalar(thickness_node)) if thickness_node else None,
                material=str(_scalar(material_node)) if material_node else None,
            ))

    layers_def = _find_first(tree, "layers")
    enabled: list[str] = []
    if layers_def:
        for entry in layers_def[1:]:
            if isinstance(entry, list) and len(entry) >= 2:
                enabled.append(str(entry[1]))

    # Board dimensions: walk all gr_line/gr_arc/gr_rect on Edge.Cuts and bound the box.
    edge_xs: list[float] = []
    edge_ys: list[float] = []
    for child in tree[1:]:
        if not isinstance(child, list) or not child:
            continue
        head = child[0]
        if not isinstance(head, sexpdata.Symbol):
            continue
        if head.value() not in ("gr_line", "gr_arc", "gr_rect", "gr_circle"):
            continue
        layer_node = _find_first(child, "layer")
        if not layer_node or _scalar(layer_node) != "Edge.Cuts":
            continue
        for pt_key in ("start", "end", "center", "mid"):
            pt = _find_first(child, pt_key)
            if pt and len(pt) >= 3:
                edge_xs.append(float(pt[1]))
                edge_ys.append(float(pt[2]))

    width = (max(edge_xs) - min(edge_xs)) if edge_xs else None
    height = (max(edge_ys) - min(edge_ys)) if edge_ys else None

    return BoardInfo(stackup=layers, enabled_layers=enabled,
                     width_mm=width, height_mm=height)
```

- [ ] **Step 3: Write integration test in `tests/integration/test_board_introspect.py`**

```python
"""Integration test for board introspection."""
from __future__ import annotations
from release_generator.board_introspect import parse_board


def test_parses_real_board(kicad_project):
    pcb = next(kicad_project.glob("*.kicad_pcb"))
    info = parse_board(pcb)

    # Should have a non-trivial stackup (≥ 4 layers for a 2-layer board, more for 4-layer)
    assert len(info.stackup) >= 4
    # Should detect copper layers
    cu = [l for l in info.stackup if l.type == "copper"]
    assert len(cu) >= 2
    # All enabled layers should be strings
    assert info.enabled_layers
    assert all(isinstance(n, str) for n in info.enabled_layers)
    # Board dimensions should be plausible (PCBs are between 1mm and 1m)
    assert info.width_mm is not None and 1.0 < info.width_mm < 1000.0
    assert info.height_mm is not None and 1.0 < info.height_mm < 1000.0
```

- [ ] **Step 4: Run test**

Run: `.venv/bin/pytest tests/integration/test_board_introspect.py -v`
Expected: PASS.

- [ ] **Step 5: Manual eyeball — print extracted data and compare to KiCad UI**

```bash
.venv/bin/python -c "
from pathlib import Path
from release_generator.board_introspect import parse_board
info = parse_board(Path('<test-project-path>/example.kicad_pcb'))
print(f'Dimensions: {info.width_mm:.2f} x {info.height_mm:.2f} mm')
print(f'Enabled layers ({len(info.enabled_layers)}): {info.enabled_layers}')
print(f'Stackup ({len(info.stackup)} layers):')
for l in info.stackup:
    print(f'  {l.name:18s} type={l.type:18s} thickness={l.thickness_mm} material={l.material}')
"
```

Open the board in KiCad → Board Setup → Physical Stackup. Compare layer names, types, thicknesses, materials. Open Board Setup → Board Editor Layers for the enabled layer list. Use Edit → Measure to confirm board dimensions. All values should match.

- [ ] **Step 6: Commit**

```bash
git add release_generator/board_introspect.py tests/integration/test_board_introspect.py pyproject.toml
git commit -m "Add board introspection (stackup, layers, dimensions)"
```

---

## Task 7: BOM Generation

**Files:**
- Create: `release_generator/bom.py`
- Modify: `release_generator/pipeline.py`
- Create: `tests/unit/test_bom.py`
- Create: `tests/integration/test_bom_integration.py`

- [ ] **Step 1: Write failing unit tests in `tests/unit/test_bom.py`**

```python
"""Unit tests for BOM CSV reshaping."""
from __future__ import annotations
import csv
import io
import pytest
from release_generator.bom import reshape_bom


def _csv_str(rows: list[dict]) -> str:
    buf = io.StringIO()
    if not rows:
        return ""
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def test_groups_by_value_and_concatenates_refs():
    raw = _csv_str([
        {"Reference": "R1", "Value": "10k", "Footprint": "0402"},
        {"Reference": "R2", "Value": "10k", "Footprint": "0402"},
        {"Reference": "R3", "Value": "1k", "Footprint": "0402"},
    ])
    out = reshape_bom(raw, group_by=["Value", "Footprint"],
                     columns=["reference", "value", "footprint", "quantity"])
    rows = list(csv.DictReader(io.StringIO(out)))
    assert len(rows) == 2
    by_val = {r["value"]: r for r in rows}
    assert by_val["10k"]["reference"] == "R1, R2"
    assert by_val["10k"]["quantity"] == "2"
    assert by_val["1k"]["reference"] == "R3"
    assert by_val["1k"]["quantity"] == "1"


def test_missing_field_emits_empty_cells_and_warning(capsys):
    raw = _csv_str([{"Reference": "R1", "Value": "10k"}])
    out = reshape_bom(raw, group_by=["Value"],
                     columns=["reference", "value", "mpn", "manufacturer"])
    rows = list(csv.DictReader(io.StringIO(out)))
    assert rows[0]["mpn"] == ""
    assert rows[0]["manufacturer"] == ""
    captured = capsys.readouterr().out
    assert "mpn" in captured.lower() or "missing" in captured.lower()


def test_sorts_references_naturally():
    raw = _csv_str([
        {"Reference": "R10", "Value": "10k"},
        {"Reference": "R2", "Value": "10k"},
        {"Reference": "R1", "Value": "10k"},
    ])
    out = reshape_bom(raw, group_by=["Value"],
                     columns=["reference", "value", "quantity"])
    rows = list(csv.DictReader(io.StringIO(out)))
    assert rows[0]["reference"] == "R1, R2, R10"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_bom.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `release_generator/bom.py`**

```python
"""BOM generation: kicad-cli sch export bom + post-process to config columns/grouping.

The kicad-cli output uses CamelCase column names (Reference, Value, Footprint, Datasheet,
plus user fields). Our config uses lowercase-with-underscores. We map between them
case-insensitively.
"""
from __future__ import annotations
import csv
import io
import re
from pathlib import Path
from .config import Config
from .kicad_cli import run as kicad_run
from .utils import output_dir_for


_NUM_RE = re.compile(r"(\d+)")


def _natural_key(s: str):
    """Sort 'R1' < 'R2' < 'R10' instead of 'R1' < 'R10' < 'R2'."""
    parts = _NUM_RE.split(s)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def _normalize(s: str) -> str:
    return s.lower().replace(" ", "_")


def _resolve_column(column: str, available_keys: list[str]) -> str | None:
    """Find the case-insensitive matching column in the kicad-cli output."""
    target = _normalize(column)
    for k in available_keys:
        if _normalize(k) == target:
            return k
    return None


def reshape_bom(raw_csv: str, group_by: list[str], columns: list[str]) -> str:
    """Group raw kicad-cli BOM CSV by `group_by`, output columns specified by `columns`.

    Returns the reshaped CSV as a string. Prints a warning to stdout for each
    requested column not found in the source.
    """
    reader = csv.DictReader(io.StringIO(raw_csv))
    rows = list(reader)
    fieldnames = reader.fieldnames or []

    # Resolve group_by columns (must exist or grouping fails)
    grp_keys = []
    for g in group_by:
        actual = _resolve_column(g, fieldnames)
        if actual is None:
            raise ValueError(f"group_by column '{g}' not found in BOM. "
                             f"Available: {fieldnames}")
        grp_keys.append(actual)

    # Reference column (always required for output if requested)
    ref_key = _resolve_column("reference", fieldnames)

    # Group rows
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        key = tuple(row.get(k, "") for k in grp_keys)
        groups.setdefault(key, []).append(row)

    # Warn once per missing column
    missing = []
    column_resolutions: list[tuple[str, str | None]] = []
    for col in columns:
        if col.lower() == "quantity":
            column_resolutions.append((col, None))  # synthesized
            continue
        actual = _resolve_column(col, fieldnames)
        column_resolutions.append((col, actual))
        if actual is None:
            missing.append(col)
    if missing:
        print(f"warning: BOM columns not found in source, will be empty: {missing}")

    # Build output rows
    out_rows: list[dict] = []
    for _, members in groups.items():
        # Concatenate refs naturally sorted
        if ref_key:
            refs = sorted([m.get(ref_key, "") for m in members if m.get(ref_key)],
                          key=_natural_key)
            ref_str = ", ".join(refs)
        else:
            ref_str = ""
        first = members[0]
        out_row: dict = {}
        for col, actual in column_resolutions:
            if col.lower() == "reference":
                out_row[col] = ref_str
            elif col.lower() == "quantity":
                out_row[col] = str(len(members))
            elif actual:
                out_row[col] = first.get(actual, "")
            else:
                out_row[col] = ""
        out_rows.append(out_row)

    # Sort output by first ref for stability
    out_rows.sort(key=lambda r: _natural_key(r.get("reference", "").split(",")[0]))

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    writer.writerows(out_rows)
    return buf.getvalue()


def generate_bom(cfg: Config, *, verbose: bool) -> tuple[Path, list[str]]:
    """Run kicad-cli sch export bom, then reshape per config."""
    out_dir = output_dir_for(cfg)
    raw_csv_path = out_dir / ".scratch" / "bom_raw.csv"
    raw_csv_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["sch", "export", "bom", str(cfg.project.schematic_file),
            "-o", str(raw_csv_path)]
    kicad_run(args, verbose=verbose)
    raw = raw_csv_path.read_text(encoding="utf-8")
    reshaped = reshape_bom(raw, group_by=cfg.bom.group_by, columns=cfg.bom.columns)
    final_path = out_dir / "bom.csv"
    final_path.write_text(reshaped, encoding="utf-8")
    return final_path, []
```

- [ ] **Step 4: Run unit tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_bom.py -v`
Expected: all PASS.

- [ ] **Step 5: Wire into pipeline.py**

```python
from .bom import generate_bom

def step_bom(cfg: Config, *, verbose: bool) -> StepResult:
    bom_csv, warnings = generate_bom(cfg, verbose=verbose)
    return StepResult(name="bom", artifacts=[bom_csv], warnings=warnings)

STEPS["bom"] = step_bom
```

- [ ] **Step 6: Write integration test in `tests/integration/test_bom_integration.py`**

```python
"""Integration test for BOM generation."""
from __future__ import annotations
import csv
import io
from release_generator.config import load_config
from release_generator.bom import generate_bom
from release_generator.utils import scaffold_output_dir
from .test_schematic import _write_test_config


def test_bom_against_real_project(kicad_project, tmp_path):
    cfg_path = _write_test_config(tmp_path, kicad_project)
    cfg = load_config(cfg_path)
    scaffold_output_dir(cfg)
    bom, _ = generate_bom(cfg, verbose=False)
    assert bom.exists()
    rows = list(csv.DictReader(io.StringIO(bom.read_text())))
    assert rows, "expected at least one BOM row"
    assert "reference" in rows[0]
    assert "value" in rows[0]
    assert "quantity" in rows[0]
```

- [ ] **Step 7: Run integration test**

Run: `.venv/bin/pytest tests/integration/test_bom_integration.py -v`
Expected: PASS.

- [ ] **Step 8: Manual smoke test**

```bash
.venv/bin/kicad-release --config /path/to/release.toml --only bom --verbose
```

Open `releases/{ver}/bom.csv`. Verify:
- Components grouped as expected (same value+footprint collapsed into one row)
- Reference designators correctly concatenated and sorted
- Quantity column is correct
- Missing-field warning printed for `mpn`/`manufacturer` if those fields aren't on your symbols

- [ ] **Step 9: Commit**

```bash
git add release_generator/bom.py release_generator/pipeline.py tests/unit/test_bom.py tests/integration/test_bom_integration.py
git commit -m "Add BOM generation with grouping and column reshape"
```

---

## Task 8: 3D Render

**Files:**
- Create: `release_generator/render3d.py`
- Modify: `release_generator/pipeline.py`
- Create: `tests/integration/test_render3d.py`

- [ ] **Step 1: Implement `release_generator/render3d.py`**

```python
"""3D render of the PCB to PNG via kicad-cli pcb render."""
from __future__ import annotations
from pathlib import Path
from .config import Config
from .kicad_cli import run as kicad_run
from .utils import scratch_dir_for


def render_pcb(cfg: Config, *, verbose: bool) -> tuple[list[Path], list[str]]:
    """Returns (list of PNG paths, warnings). Skips entirely if 3D render disabled."""
    if not cfg.fab_drawing.include_3d_render:
        return [], ["3D render disabled in [fab_drawing].include_3d_render"]

    out_dir = scratch_dir_for(cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    sides = ["top", "bottom"] if cfg.fab_drawing.render_view == "both" \
            else [cfg.fab_drawing.render_view]
    pngs: list[Path] = []
    for side in sides:
        png = out_dir / f"render-3d-{side}.png"
        args = ["pcb", "render", str(cfg.project.pcb_file),
                "-o", str(png),
                "--side", side,
                "--quality", "high",
                "--width", "1600", "--height", "1200",
                "--background", "opaque"]
        kicad_run(args, verbose=verbose, timeout=900)
        if not png.exists():
            raise RuntimeError(f"render did not produce {png}")
        pngs.append(png)
    return pngs, []
```

- [ ] **Step 2: Wire into pipeline.py**

```python
from .render3d import render_pcb

def step_render(cfg: Config, *, verbose: bool) -> StepResult:
    pngs, warnings = render_pcb(cfg, verbose=verbose)
    return StepResult(name="render", artifacts=pngs, warnings=warnings)

STEPS["render"] = step_render
```

- [ ] **Step 3: Write integration test in `tests/integration/test_render3d.py`**

```python
"""Integration test for 3D render."""
from __future__ import annotations
from release_generator.config import load_config
from release_generator.render3d import render_pcb
from release_generator.utils import scaffold_output_dir
from .test_schematic import _write_test_config


def test_render_top_only(kicad_project, tmp_path):
    cfg_path = _write_test_config(tmp_path, kicad_project)
    # _write_test_config sets include_3d_render=false by default; we need to enable it.
    # Modify the toml to enable rendering before loading.
    text = cfg_path.read_text().replace(
        "include_3d_render = false", "include_3d_render = true"
    )
    cfg_path.write_text(text)
    cfg = load_config(cfg_path)
    scaffold_output_dir(cfg)
    pngs, warnings = render_pcb(cfg, verbose=False)
    assert len(pngs) == 1
    assert pngs[0].exists()
    assert pngs[0].stat().st_size > 10_000  # nontrivial PNG
```

- [ ] **Step 4: Run integration test**

Run: `.venv/bin/pytest tests/integration/test_render3d.py -v`
Expected: PASS. Note: render is slow (10s–60s); be patient.

- [ ] **Step 5: Manual smoke test**

```bash
.venv/bin/kicad-release --config /path/to/release.toml --only render --verbose
```

Open the PNG in `releases/{ver}/.scratch/render-3d-top.png`. Verify:
- Board is recognizable
- Components visible
- Image is reasonably high quality

- [ ] **Step 6: Commit**

```bash
git add release_generator/render3d.py release_generator/pipeline.py tests/integration/test_render3d.py
git commit -m "Add 3D render via kicad-cli pcb render"
```

---

## Task 9: SVG Template Engine

**Files:**
- Create: `release_generator/svg_template.py`
- Create: `tests/unit/test_svg_template.py`

- [ ] **Step 1: Write failing unit tests in `tests/unit/test_svg_template.py`**

```python
"""Unit tests for SVG template substitution."""
from __future__ import annotations
import pytest
from lxml import etree
from release_generator.svg_template import (
    SvgTemplate, Region, substitute_text_placeholders, find_regions
)


SVG_NS = "http://www.w3.org/2000/svg"
NSMAP = {"svg": SVG_NS}


def _svg_with(body: str) -> bytes:
    return f'<?xml version="1.0"?><svg xmlns="{SVG_NS}" width="100" height="100">{body}</svg>'.encode()


def test_substitute_simple_placeholder():
    src = _svg_with('<text>{{REV}}</text>')
    out = substitute_text_placeholders(src, {"REV": "3.2"})
    root = etree.fromstring(out)
    text_el = root.find("svg:text", NSMAP)
    assert text_el.text == "3.2"


def test_substitute_in_tspan():
    src = _svg_with('<text><tspan>Rev: {{REV}}</tspan></text>')
    out = substitute_text_placeholders(src, {"REV": "3.2"})
    root = etree.fromstring(out)
    tspan = root.find("svg:text/svg:tspan", NSMAP)
    assert tspan.text == "Rev: 3.2"


def test_missing_placeholder_left_alone_with_warning(capsys):
    src = _svg_with('<text>{{UNKNOWN}}</text>')
    out = substitute_text_placeholders(src, {"REV": "3.2"})
    root = etree.fromstring(out)
    text_el = root.find("svg:text", NSMAP)
    assert text_el.text == "{{UNKNOWN}}"
    captured = capsys.readouterr().out
    assert "UNKNOWN" in captured


def test_find_named_region_rect():
    src = _svg_with(
        '<rect id="board-view" x="10" y="20" width="40" height="30"/>'
        '<rect id="other" x="0" y="0" width="5" height="5"/>'
    )
    regions = find_regions(src, ids=["board-view", "drill-table"])
    assert "board-view" in regions
    assert "drill-table" not in regions
    r = regions["board-view"]
    assert (r.x, r.y, r.width, r.height) == (10.0, 20.0, 40.0, 30.0)


def test_region_rect_removed_when_replaced():
    src = _svg_with('<rect id="board-view" x="0" y="0" width="50" height="50"/>')
    tpl = SvgTemplate(src)
    tpl.replace_region("board-view",
                       etree.Element(f"{{{SVG_NS}}}g", id="content"))
    out = tpl.serialize()
    root = etree.fromstring(out)
    assert root.find('svg:rect[@id="board-view"]', NSMAP) is None
    assert root.find('svg:g[@id="content"]', NSMAP) is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_svg_template.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `release_generator/svg_template.py`**

```python
"""SVG template loading and substitution.

Two mechanisms:
- Text placeholders: {{NAME}} strings inside <text>/<tspan> elements get replaced.
- Region rectangles: <rect id="NAME" x="..." y="..." width="..." height="..."/>
  defines a content area; the tool removes the rect and inserts rendered content.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from lxml import etree

SVG_NS = "http://www.w3.org/2000/svg"
NSMAP = {"svg": SVG_NS}
PLACEHOLDER_RE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


@dataclass
class Region:
    id: str
    x: float
    y: float
    width: float
    height: float


def _walk_text_elements(root):
    """Yield every <text> and <tspan> element and direct text children."""
    for tag in ("text", "tspan"):
        for el in root.iter(f"{{{SVG_NS}}}{tag}"):
            yield el


def substitute_text_placeholders(svg_bytes: bytes, vars_: dict[str, str]) -> bytes:
    """Replace {{NAME}} strings in text/tspan element text content."""
    root = etree.fromstring(svg_bytes)
    found: set[str] = set()
    for el in _walk_text_elements(root):
        if el.text:
            def repl(m):
                key = m.group(1)
                found.add(key)
                if key in vars_:
                    return vars_[key]
                return m.group(0)  # leave alone
            new_text = PLACEHOLDER_RE.sub(repl, el.text)
            el.text = new_text
        # also scan tail text? probably not — placeholders should live inside elements.
    unknown = found - set(vars_.keys())
    for u in sorted(unknown):
        print(f"warning: SVG template references unknown placeholder {{{{{u}}}}}, "
              f"left as literal text")
    return etree.tostring(root, xml_declaration=True, encoding="utf-8")


def find_regions(svg_bytes: bytes, ids: list[str]) -> dict[str, Region]:
    """Return {id: Region} for any <rect id="..."> in the template matching ids."""
    root = etree.fromstring(svg_bytes)
    out: dict[str, Region] = {}
    for rect in root.iter(f"{{{SVG_NS}}}rect"):
        rid = rect.get("id")
        if rid and rid in ids:
            out[rid] = Region(
                id=rid,
                x=float(rect.get("x", "0")),
                y=float(rect.get("y", "0")),
                width=float(rect.get("width", "0")),
                height=float(rect.get("height", "0")),
            )
    return out


class SvgTemplate:
    """Mutable in-memory SVG template for composition."""

    def __init__(self, svg_bytes: bytes):
        self.tree = etree.fromstring(svg_bytes)

    def substitute_text(self, vars_: dict[str, str]) -> None:
        new_bytes = substitute_text_placeholders(
            etree.tostring(self.tree, xml_declaration=True, encoding="utf-8"), vars_
        )
        self.tree = etree.fromstring(new_bytes)

    def find_regions(self, ids: list[str]) -> dict[str, Region]:
        return find_regions(
            etree.tostring(self.tree, xml_declaration=True, encoding="utf-8"), ids
        )

    def replace_region(self, region_id: str, content_element) -> None:
        """Remove the rect with the given id, append the content element in its place.

        The content element's positioning is the caller's responsibility — typically
        the caller wraps content in a <g transform="translate(x,y) scale(...)"> sized
        to the region's bounding box.
        """
        for rect in self.tree.iter(f"{{{SVG_NS}}}rect"):
            if rect.get("id") == region_id:
                parent = rect.getparent()
                idx = list(parent).index(rect)
                parent.remove(rect)
                parent.insert(idx, content_element)
                return
        # Region not found — caller should have warned before calling

    def serialize(self) -> bytes:
        return etree.tostring(self.tree, xml_declaration=True, encoding="utf-8",
                              pretty_print=False)
```

- [ ] **Step 4: Run unit tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_svg_template.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add release_generator/svg_template.py tests/unit/test_svg_template.py
git commit -m "Add SVG template engine with text and region substitution"
```

---

## Task 10: SVG → PDF Converter

**Files:**
- Create: `release_generator/svg_to_pdf.py`
- Create: `tests/integration/test_svg_to_pdf.py`

- [ ] **Step 1: Implement `release_generator/svg_to_pdf.py`**

```python
"""SVG → PDF conversion. CairoSVG primary; Inkscape CLI fallback."""
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path

import cairosvg


class SvgToPdfError(RuntimeError):
    pass


def convert(svg_path: Path, pdf_path: Path) -> None:
    """Convert SVG file to PDF. Raises SvgToPdfError if both backends fail."""
    try:
        cairosvg.svg2pdf(url=str(svg_path), write_to=str(pdf_path))
        return
    except Exception as e:
        cairo_err = e

    inkscape = shutil.which("inkscape")
    if inkscape:
        res = subprocess.run(
            [inkscape, str(svg_path), "--export-type=pdf",
             f"--export-filename={pdf_path}"],
            capture_output=True, text=True, timeout=120,
        )
        if res.returncode == 0 and pdf_path.exists():
            return
        raise SvgToPdfError(
            f"CairoSVG failed: {cairo_err}; Inkscape fallback failed: {res.stderr}"
        )
    raise SvgToPdfError(
        f"CairoSVG failed and Inkscape not found on PATH: {cairo_err}"
    )
```

- [ ] **Step 2: Write integration test in `tests/integration/test_svg_to_pdf.py`**

```python
"""Integration test for SVG → PDF conversion."""
from __future__ import annotations
from release_generator.svg_to_pdf import convert


def test_simple_svg_round_trips_to_pdf(tmp_path):
    svg = tmp_path / "input.svg"
    svg.write_text("""<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <rect x="10" y="10" width="80" height="80" fill="blue"/>
  <text x="50" y="50" text-anchor="middle">Hello</text>
</svg>""")
    pdf = tmp_path / "out.pdf"
    convert(svg, pdf)
    assert pdf.exists()
    assert pdf.read_bytes()[:4] == b"%PDF"
```

- [ ] **Step 3: Run test**

Run: `.venv/bin/pytest tests/integration/test_svg_to_pdf.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add release_generator/svg_to_pdf.py tests/integration/test_svg_to_pdf.py
git commit -m "Add SVG to PDF conversion (CairoSVG with Inkscape fallback)"
```

---

## Task 11: Title Block Template (Inkscape Walkthrough)

**Files:**
- Create: `templates/titleblock_a4.svg`
- Create: `templates/README.md`

This task is interactive — Claude walks the user through Inkscape, then both verify the result. Steps below are a checklist for the conversation, not autonomous code generation.

- [ ] **Step 1: Walk the user through Inkscape title block authoring**

Open Inkscape, create a new A4 landscape document. Walk through:

1. **Page setup**: File → Document Properties → set to A4, landscape orientation. Units: mm.
2. **Title block frame**: Draw the outer border rectangle and inner title block boxes using the Rectangle tool. Use 0.25 mm stroke, no fill.
3. **Static labels**: Use the Text tool to add labels like "DRAWN BY:", "DATE:", "REV:", "COMPANY:", "CONFIDENTIALITY:", "TITLE:".
4. **Dynamic text**: Add `{{TITLE}}`, `{{DRAWN_BY}}`, `{{DATE}}`, `{{REV}}`, `{{COMPANY}}`, `{{CONFIDENTIALITY}}`, `{{PAGE}}`, `{{FILENAME}}` text elements at desired positions.
5. **Revision table**: Draw a small table grid in the title block. Add `{{REV_1}}`, `{{EC_1}}`, `{{DESC_1}}` text elements for the newest revision row. Add `{{REV_2}}` etc. for additional rows if you want more than one row of revision history visible.
6. **Region rectangles for fab content**: Draw five rectangles in the main drawing area, label them via Object Properties (Ctrl+Shift+O):
   - `id="board-view"` — large area for board outline (e.g., upper-left, ~60% of page)
   - `id="drill-table"` — table for drill report (e.g., upper-right corner)
   - `id="stackup-table"` — table for stackup (e.g., right side, middle)
   - `id="fab-notes"` — vertical strip for fab notes (e.g., right side, lower)
   - `id="render-3d"` — area for 3D render PNG (e.g., lower-left)
   Set fill to "none" or a faint color so they're visible while authoring; the tool removes them anyway.
7. **Convert text to paths** (optional but recommended): Edit → Select All → Path → Object to Path. This eliminates font dependency.
8. **Save as plain SVG**: File → Save As → set type to "Plain SVG (*.svg)" (not Inkscape SVG).

- [ ] **Step 2: Save the file**

Save to `templates/titleblock_a4.svg` in the repo.

- [ ] **Step 3: Verify the template parses and contains expected placeholders**

Run:
```bash
.venv/bin/python -c "
from release_generator.svg_template import find_regions, PLACEHOLDER_RE
import re
text = open('templates/titleblock_a4.svg').read()
placeholders = sorted(set(PLACEHOLDER_RE.findall(text)))
print(f'Placeholders found: {placeholders}')
regions = find_regions(text.encode(), ['board-view', 'drill-table', 'stackup-table',
                                        'fab-notes', 'render-3d',
                                        'front-view', 'back-view', 'assembly-notes'])
print(f'Regions found: {sorted(regions.keys())}')
for r in regions.values():
    print(f'  {r.id}: x={r.x:.1f} y={r.y:.1f} w={r.width:.1f} h={r.height:.1f}')
"
```

Expected: all expected placeholders and at least the fab regions are present.

- [ ] **Step 4: Write `templates/README.md` documenting the contract**

```markdown
# Title Block Templates

Each `*.svg` here is an SVG title block template authored in Inkscape. The
release tool substitutes `{{PLACEHOLDER}}` strings and replaces named
`<rect id="...">` rectangles with rendered content.

See `docs/superpowers/specs/2026-04-14-kicad-release-tool-design.md` section
"SVG Template Contract" for the full list of placeholders and regions.

To create a new template:

1. Open Inkscape, set document to your target page size.
2. Draw your title block (borders, labels, logo).
3. Add `{{REV}}`, `{{DATE}}` etc. text elements where dynamic text goes.
4. Draw rectangles where dynamic content goes; set their `id` via Object Properties
   (Ctrl+Shift+O) to one of the recognized region names.
5. Optionally Path > Object to Path on all text to eliminate font dependency.
6. Save as Plain SVG.
```

- [ ] **Step 5: Commit**

```bash
git add templates/
git commit -m "Add A4 title block template and authoring guide"
```

---

## Task 12: Fab Drawing Composition

**Files:**
- Create: `release_generator/fab_drawing.py`
- Modify: `release_generator/pipeline.py`
- Create: `tests/integration/test_fab_drawing.py`

- [ ] **Step 1: Implement `release_generator/fab_drawing.py`**

```python
"""Compose the fab drawing: title block + board view + drill table + stackup +
notes + optional 3D render."""
from __future__ import annotations
import datetime
import shutil
from pathlib import Path
from lxml import etree
from .config import Config
from .kicad_cli import run as kicad_run
from .svg_template import SvgTemplate, Region, SVG_NS
from .svg_to_pdf import convert as svg_to_pdf
from .board_introspect import parse_board, BoardInfo
from .render3d import render_pcb
from .utils import output_dir_for, scratch_dir_for

NSMAP = {"svg": SVG_NS}


def _build_text_vars(cfg: Config, drawing_title: str, page: str = "Page 1 of 1") -> dict[str, str]:
    vars_ = {
        "TITLE": drawing_title,
        "DATE": cfg.project.date if cfg.project.date != "auto"
                else datetime.date.today().isoformat(),
        "REV": cfg.project.version,
        "DRAWN_BY": cfg.titleblock.drawn_by,
        "COMPANY": cfg.titleblock.company,
        "CONFIDENTIALITY": cfg.titleblock.confidentiality,
        "PAGE": page,
        "FILENAME": cfg.project.pcb_file.name,
    }
    for i, rev in enumerate(cfg.revisions, start=1):
        vars_[f"REV_{i}"] = rev.rev
        vars_[f"EC_{i}"] = rev.ec
        vars_[f"DESC_{i}"] = rev.description
    return vars_


def _wrap_in_region(content: etree._Element, region: Region,
                    content_width: float, content_height: float) -> etree._Element:
    """Wrap content element in a <g> that translates+scales it to fit region.

    Aspect-preserving fit. Content is centered in the region.
    """
    if content_width <= 0 or content_height <= 0:
        scale = 1.0
    else:
        scale = min(region.width / content_width, region.height / content_height)
    rendered_w = content_width * scale
    rendered_h = content_height * scale
    tx = region.x + (region.width - rendered_w) / 2
    ty = region.y + (region.height - rendered_h) / 2
    g = etree.Element(f"{{{SVG_NS}}}g")
    g.set("transform", f"translate({tx} {ty}) scale({scale})")
    g.append(content)
    return g


def _load_svg_inner(svg_path: Path) -> tuple[etree._Element, float, float]:
    """Load an SVG and return (root_element, width, height) for embedding.

    Returns the root <svg> element renamed to <g> so it can be embedded inside
    another SVG document, plus its viewBox width and height.
    """
    tree = etree.parse(str(svg_path))
    root = tree.getroot()
    # Determine intrinsic dimensions
    vb = root.get("viewBox")
    if vb:
        parts = vb.split()
        width = float(parts[2])
        height = float(parts[3])
    else:
        width = float(root.get("width", "100").rstrip("mmptcin %"))
        height = float(root.get("height", "100").rstrip("mmptcin %"))
    # Convert root <svg> into <g> by creating a new element and moving children
    g = etree.Element(f"{{{SVG_NS}}}g")
    for child in root:
        g.append(child)
    return g, width, height


def _build_drill_table(board: BoardInfo) -> etree._Element:
    """Build a simple drill-info <g> as text. (Placeholder data — drill report
    parsing is added in the future if richer info is needed.)"""
    g = etree.Element(f"{{{SVG_NS}}}g")
    text = etree.SubElement(g, f"{{{SVG_NS}}}text",
                            attrib={"font-size": "3", "font-family": "monospace"})
    text.text = "DRILL TABLE — see drill-report.txt"
    return g


def _build_stackup_table(board: BoardInfo) -> etree._Element:
    """Build a vertically stacked text table of the stackup layers."""
    g = etree.Element(f"{{{SVG_NS}}}g")
    line_height = 3.5
    header = etree.SubElement(g, f"{{{SVG_NS}}}text",
                              attrib={"x": "0", "y": "0",
                                      "font-size": "3", "font-weight": "bold",
                                      "font-family": "monospace"})
    header.text = f"{'NAME':18s} {'TYPE':18s} {'TH(mm)':>8s} {'MAT':10s}"
    for i, layer in enumerate(board.stackup, start=1):
        t = etree.SubElement(g, f"{{{SVG_NS}}}text",
                             attrib={"x": "0", "y": str(i * line_height),
                                     "font-size": "3", "font-family": "monospace"})
        thickness = f"{layer.thickness_mm:.3f}" if layer.thickness_mm is not None else "—"
        material = layer.material or "—"
        t.text = f"{layer.name[:18]:18s} {layer.type[:18]:18s} {thickness:>8s} {material[:10]:10s}"
    return g


def _build_notes_list(notes: list[str]) -> etree._Element:
    """Build a numbered list of notes as text elements."""
    g = etree.Element(f"{{{SVG_NS}}}g")
    for i, note in enumerate(notes, start=1):
        t = etree.SubElement(g, f"{{{SVG_NS}}}text",
                             attrib={"x": "0", "y": str(i * 4),
                                     "font-size": "2.5", "font-family": "sans-serif"})
        t.text = f"{i}. {note}"
    return g


def _build_image_element(png_path: Path, width: float, height: float) -> etree._Element:
    """Build an <image> referencing a PNG, sized to (width, height)."""
    img = etree.Element(f"{{{SVG_NS}}}image",
                        attrib={"x": "0", "y": "0",
                                "width": str(width), "height": str(height),
                                "preserveAspectRatio": "xMidYMid meet"})
    img.set("{http://www.w3.org/1999/xlink}href", str(png_path))
    return img


def compose_fab_drawing(cfg: Config, *, verbose: bool) -> tuple[Path, list[str]]:
    out = output_dir_for(cfg)
    scratch = scratch_dir_for(cfg)
    template_path = cfg.fab_drawing.template or cfg.titleblock.template
    warnings: list[str] = []

    # 1. Export Edge.Cuts SVG of the board
    board_svg = scratch / "board-edge.svg"
    kicad_run(["pcb", "export", "svg", str(cfg.project.pcb_file),
               "-o", str(board_svg), "--layers", "Edge.Cuts",
               "--page-size-mode", "2"], verbose=verbose)

    # 2. Render 3D PNG(s) if enabled
    pngs: list[Path] = []
    if cfg.fab_drawing.include_3d_render:
        pngs, w = render_pcb(cfg, verbose=verbose)
        warnings.extend(w)

    # 3. Parse board for stackup
    board = parse_board(cfg.project.pcb_file)

    # 4. Load template, run text substitution
    tpl = SvgTemplate(template_path.read_bytes())
    tpl.substitute_text(_build_text_vars(cfg, cfg.fab_drawing.title))

    # 5. Find regions
    region_ids = ["board-view", "drill-table", "stackup-table", "fab-notes", "render-3d"]
    regions = tpl.find_regions(region_ids)
    for needed in region_ids:
        if needed not in regions:
            warnings.append(f"template missing region id='{needed}', skipping content")

    # 6. Place board view
    if "board-view" in regions:
        g, w, h = _load_svg_inner(board_svg)
        tpl.replace_region("board-view", _wrap_in_region(g, regions["board-view"], w, h))

    # 7. Place drill table
    if "drill-table" in regions:
        content = _build_drill_table(board)
        tpl.replace_region("drill-table",
                           _wrap_in_region(content, regions["drill-table"], 80, 30))

    # 8. Place stackup table
    if "stackup-table" in regions:
        content = _build_stackup_table(board)
        rows_h = (len(board.stackup) + 1) * 4
        tpl.replace_region("stackup-table",
                           _wrap_in_region(content, regions["stackup-table"], 60, rows_h))

    # 9. Place fab notes
    if "fab-notes" in regions:
        content = _build_notes_list(cfg.fab_drawing.notes)
        notes_h = len(cfg.fab_drawing.notes) * 4
        tpl.replace_region("fab-notes",
                           _wrap_in_region(content, regions["fab-notes"], 80, notes_h))

    # 10. Place 3D render
    if "render-3d" in regions and pngs:
        # If "both", split region horizontally
        if len(pngs) == 2:
            r = regions["render-3d"]
            half_w = r.width / 2
            for idx, png in enumerate(pngs):
                sub_region = Region(id=f"render-half-{idx}",
                                    x=r.x + idx * half_w, y=r.y,
                                    width=half_w, height=r.height)
                img = _build_image_element(png, 1600, 1200)
                wrapper = _wrap_in_region(img, sub_region, 1600, 1200)
                # Append as new child of root; we don't have a region rect to remove
                tpl.tree.append(wrapper)
            # Remove the original region rect
            for rect in tpl.tree.iter(f"{{{SVG_NS}}}rect"):
                if rect.get("id") == "render-3d":
                    rect.getparent().remove(rect)
                    break
        else:
            img = _build_image_element(pngs[0], 1600, 1200)
            tpl.replace_region("render-3d",
                               _wrap_in_region(img, regions["render-3d"], 1600, 1200))

    # 11. Write SVG, convert to PDF
    final_svg = scratch / "fab-drawing.svg"
    final_svg.write_bytes(tpl.serialize())
    final_pdf = out / "fab-drawing.pdf"
    svg_to_pdf(final_svg, final_pdf)

    return final_pdf, warnings
```

- [ ] **Step 2: Wire into pipeline.py**

```python
from .fab_drawing import compose_fab_drawing

def step_fab_drawing(cfg: Config, *, verbose: bool) -> StepResult:
    pdf, warnings = compose_fab_drawing(cfg, verbose=verbose)
    return StepResult(name="fab-drawing", artifacts=[pdf], warnings=warnings)

STEPS["fab-drawing"] = step_fab_drawing
```

- [ ] **Step 3: Write integration test in `tests/integration/test_fab_drawing.py`**

```python
"""Integration test for fab drawing composition."""
from __future__ import annotations
from pathlib import Path
import shutil
from release_generator.config import load_config
from release_generator.fab_drawing import compose_fab_drawing
from release_generator.utils import scaffold_output_dir
from .test_schematic import _write_test_config

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "templates" / "titleblock_a4.svg"


def test_fab_drawing_pdf_is_produced(kicad_project, tmp_path):
    cfg_path = _write_test_config(tmp_path, kicad_project)
    # Replace the dummy tb.svg with the real template
    shutil.copy(TEMPLATE, tmp_path / "tb.svg")
    # Disable 3D render to keep test fast
    text = cfg_path.read_text()
    text = text.replace("include_3d_render = true", "include_3d_render = false")
    cfg_path.write_text(text)
    cfg = load_config(cfg_path)
    scaffold_output_dir(cfg)
    pdf, warnings = compose_fab_drawing(cfg, verbose=False)
    assert pdf.exists()
    assert pdf.read_bytes()[:4] == b"%PDF"
    # Print warnings for visibility
    for w in warnings:
        print(f"warning: {w}")
```

- [ ] **Step 4: Run integration test**

Run: `.venv/bin/pytest tests/integration/test_fab_drawing.py -v -s`
Expected: PASS.

- [ ] **Step 5: Manual smoke test with 3D render enabled**

```bash
.venv/bin/kicad-release --config /path/to/release.toml --only fab-drawing --verbose --keep-scratch
```

Open `releases/{ver}/fab-drawing.pdf`. Verify:
- Title block fields are populated
- Board outline visible in board-view region
- Stackup table shows actual layer data
- Fab notes are numbered and legible
- 3D render is embedded if enabled
- Nothing overlaps catastrophically (if it does, adjust template region positions)

If any region is empty or content overlaps, this is the area where iteration is expected. Adjust the template SVG's region rect positions and re-run.

- [ ] **Step 6: Commit**

```bash
git add release_generator/fab_drawing.py release_generator/pipeline.py tests/integration/test_fab_drawing.py
git commit -m "Add fab drawing composition with stackup, notes, and 3D render"
```

---

## Task 13: Assembly Drawing Composition

**Files:**
- Create: `release_generator/assembly_drawing.py`
- Modify: `release_generator/pipeline.py`
- Create: `tests/integration/test_assembly_drawing.py`

- [ ] **Step 1: Implement `release_generator/assembly_drawing.py`**

```python
"""Compose the assembly drawing: title block + front view + back view + notes."""
from __future__ import annotations
from pathlib import Path
from lxml import etree
from .config import Config
from .kicad_cli import run as kicad_run
from .svg_template import SvgTemplate, SVG_NS
from .svg_to_pdf import convert as svg_to_pdf
from .utils import output_dir_for, scratch_dir_for
from .fab_drawing import (
    _build_text_vars, _wrap_in_region, _load_svg_inner, _build_notes_list,
)


def compose_assembly_drawing(cfg: Config, *, verbose: bool) -> tuple[Path, list[str]]:
    out = output_dir_for(cfg)
    scratch = scratch_dir_for(cfg)
    template_path = cfg.assembly_drawing.template or cfg.titleblock.template
    warnings: list[str] = []

    # 1. Export front and back SVGs
    front_svg = scratch / "assembly-front.svg"
    back_svg = scratch / "assembly-back.svg"
    kicad_run(["pcb", "export", "svg", str(cfg.project.pcb_file),
               "-o", str(front_svg),
               "--layers", ",".join(cfg.assembly_drawing.layers_front),
               "--page-size-mode", "2"], verbose=verbose)
    kicad_run(["pcb", "export", "svg", str(cfg.project.pcb_file),
               "-o", str(back_svg),
               "--layers", ",".join(cfg.assembly_drawing.layers_back),
               "--page-size-mode", "2", "--mirror"], verbose=verbose)

    # 2. Load template, substitute text
    tpl = SvgTemplate(template_path.read_bytes())
    tpl.substitute_text(_build_text_vars(cfg, cfg.assembly_drawing.title))

    # 3. Find regions
    region_ids = ["front-view", "back-view", "assembly-notes"]
    regions = tpl.find_regions(region_ids)
    for needed in region_ids:
        if needed not in regions:
            warnings.append(f"template missing region id='{needed}', skipping content")

    # 4. Place front view
    if "front-view" in regions:
        g, w, h = _load_svg_inner(front_svg)
        tpl.replace_region("front-view", _wrap_in_region(g, regions["front-view"], w, h))

    # 5. Place back view
    if "back-view" in regions:
        g, w, h = _load_svg_inner(back_svg)
        tpl.replace_region("back-view", _wrap_in_region(g, regions["back-view"], w, h))

    # 6. Place notes
    if "assembly-notes" in regions:
        content = _build_notes_list(cfg.assembly_drawing.notes)
        notes_h = len(cfg.assembly_drawing.notes) * 4
        tpl.replace_region("assembly-notes",
                           _wrap_in_region(content, regions["assembly-notes"], 80, notes_h))

    # 7. Write SVG, convert to PDF
    final_svg = scratch / "assembly-drawing.svg"
    final_svg.write_bytes(tpl.serialize())
    final_pdf = out / "assembly-drawing.pdf"
    svg_to_pdf(final_svg, final_pdf)
    return final_pdf, warnings
```

- [ ] **Step 2: Wire into pipeline.py**

```python
from .assembly_drawing import compose_assembly_drawing

def step_assembly_drawing(cfg: Config, *, verbose: bool) -> StepResult:
    pdf, warnings = compose_assembly_drawing(cfg, verbose=verbose)
    return StepResult(name="assembly-drawing", artifacts=[pdf], warnings=warnings)

STEPS["assembly-drawing"] = step_assembly_drawing
```

- [ ] **Step 3: Write integration test in `tests/integration/test_assembly_drawing.py`**

```python
"""Integration test for assembly drawing composition."""
from __future__ import annotations
from pathlib import Path
import shutil
from release_generator.config import load_config
from release_generator.assembly_drawing import compose_assembly_drawing
from release_generator.utils import scaffold_output_dir
from .test_schematic import _write_test_config

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "templates" / "titleblock_a4.svg"


def test_assembly_drawing_pdf_is_produced(kicad_project, tmp_path):
    cfg_path = _write_test_config(tmp_path, kicad_project)
    shutil.copy(TEMPLATE, tmp_path / "tb.svg")
    cfg = load_config(cfg_path)
    scaffold_output_dir(cfg)
    pdf, warnings = compose_assembly_drawing(cfg, verbose=False)
    assert pdf.exists()
    assert pdf.read_bytes()[:4] == b"%PDF"
    for w in warnings:
        print(f"warning: {w}")
```

- [ ] **Step 4: Run integration test**

Run: `.venv/bin/pytest tests/integration/test_assembly_drawing.py -v -s`
Expected: PASS.

- [ ] **Step 5: Manual smoke test**

```bash
.venv/bin/kicad-release --config /path/to/release.toml --only assembly-drawing --verbose --keep-scratch
```

Open `releases/{ver}/assembly-drawing.pdf`. Verify:
- Title block correct
- Front view shows F.Fab + Edge.Cuts
- Back view shows B.Fab + Edge.Cuts (mirrored so it reads as if looking at the bottom)
- Notes are numbered and legible

- [ ] **Step 6: Commit**

```bash
git add release_generator/assembly_drawing.py release_generator/pipeline.py tests/integration/test_assembly_drawing.py
git commit -m "Add assembly drawing composition with front and back views"
```

---

## Task 14: End-to-End Pipeline Test + Example Config

**Files:**
- Create: `tests/integration/test_pipeline_e2e.py`
- Create: `example/release.toml`
- Create: `example/README.md`

- [ ] **Step 1: Write E2E integration test in `tests/integration/test_pipeline_e2e.py`**

```python
"""End-to-end pipeline test against the real KiCad project."""
from __future__ import annotations
from pathlib import Path
import shutil
from release_generator.__main__ import main
from .test_schematic import _write_test_config

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "templates" / "titleblock_a4.svg"


def test_full_pipeline_against_real_project(kicad_project, tmp_path, capsys):
    cfg_path = _write_test_config(tmp_path, kicad_project)
    shutil.copy(TEMPLATE, tmp_path / "tb.svg")
    # Disable 3D render to keep this test snappy
    text = cfg_path.read_text().replace("include_3d_render = true",
                                         "include_3d_render = false")
    cfg_path.write_text(text)

    rc = main(["--config", str(cfg_path)])
    assert rc == 0

    out = tmp_path / "releases" / "T1"
    assert (out / "schematic.pdf").exists()
    assert (out / "bom.csv").exists()
    assert (out / "pick-and-place.csv").exists()
    assert (out / "fab-drawing.pdf").exists()
    assert (out / "assembly-drawing.pdf").exists()
    assert any((out / "gerbers").glob("*.gbr"))
    assert any((out / "gerbers").glob("*.drl"))

    captured = capsys.readouterr().out
    assert "Summary" in captured
```

- [ ] **Step 2: Run E2E test**

Run: `.venv/bin/pytest tests/integration/test_pipeline_e2e.py -v -s`
Expected: PASS.

- [ ] **Step 3: Create `example/release.toml`**

Copy the spec's example config exactly into `example/release.toml` (with paths adjusted as needed for the example to be self-contained — e.g., reference `templates/titleblock_a4.svg` from the repo root, or have the example `pcb_file`/`schematic_file` paths point at the test fixture project).

```toml
[project]
name = "Example PCB"
version = "1.0"
date = "auto"
pcb_file = "./example.kicad_pcb"
schematic_file = "./example.kicad_sch"

[titleblock]
template = "../templates/titleblock_a4.svg"
company = "<company>"
drawn_by = "Your Name"
confidentiality = "PROPRIETARY AND CONFIDENTIAL"

[[revisions]]
rev = "A"
ec = "N/A"
description = "ADD LOCATING FEATURE SLOTS"

[[revisions]]
rev = "02"
ec = "N/A"
description = "INCREASE CS TRACE WIDTH, CHANGE TEMP SENSE, UPDATED PINOUT"

[[revisions]]
rev = "01"
ec = "N/A"
description = "INITIAL RELEASE"

[fab_drawing]
title = "Fab Drawing"
page_size = "A4"
notes = [
    "FABRICATE IN ACCORDANCE WITH IPC-6013, CLASS 2. CERTIFICATION REQUIRED.",
    "INSPECT IN ACCORDANCE WITH IPC-A-600. CERTIFICATION REQUIRED.",
    "THIS PCB SHALL BE RoHS COMPLIANT.",
    "ROUTING TOLERANCE: +/- 20%",
    "MIN TRACE / MIN SPACE: 3 MIL / 3 MIL",
    "SURFACE FINISH: ELECTROLESS NICKEL IMMERSION GOLD (ENIG)",
    "SILKSCREEN WHITE, NONCONDUCTIVE EPOXY INK, BOTH SIDES",
    "SILKSCREEN NOT TO COVER ANY PORTION OF EXPOSED COPPER.",
    "A CERTIFICATE OF CONFORMANCE SHALL BE PROVIDED WITH EACH PCB.",
]
include_3d_render = true
render_view = "top"

[assembly_drawing]
title = "Assembly Drawing"
page_size = "A4"
notes = [
    "This board is to be assembled and soldered in accordance with IPC-A-610 (current revision), Class 2 specification. CERTIFICATION REQUIRED",
    "Warning: This board contains electrostatic sensitive devices. All personnel handling this board must be electrically grounded.",
    "PCB Assembly shall be lead free, in compliance with the RoHS Directive (current revision). CERTIFICATION REQUIRED",
    "Pin 1 of integrated circuits (ICs) is indicated with a dot or circle in the silkscreen. Cathodes are designated with a dot, bar, or K designation on the silkscreen and/or assembly drawing",
]
layers_front = ["F.Fab", "F.Courtyard", "Edge.Cuts"]
layers_back = ["B.Fab", "B.Courtyard", "Edge.Cuts"]

[bom]
group_by = ["value", "footprint"]
columns = ["reference", "value", "footprint", "quantity", "mpn", "manufacturer"]

[gerbers]
layers = "auto"
subtract_soldermask = false
```

- [ ] **Step 4: Create `example/README.md`**

```markdown
# Example Release Configuration

`release.toml` here is a generic sample config; customize it for your project.

To run:

```bash
kicad-release --config example/release.toml
```

Output goes to `example/releases/3.2/`.

For the schematic title block to populate correctly, the schematic must use
KiCad text variables (`${TITLE}`, `${REV}`, `${DATE}`, `${COMPANY}`) in the
title block fields. See the project README for one-time setup.
```

- [ ] **Step 5: Run full pipeline against real project, manually**

```bash
.venv/bin/kicad-release --config example/release.toml --verbose
```

Verify all artifacts in `example/releases/3.2/`:
- `schematic.pdf` — title block populated
- `bom.csv` — grouped, has expected components
- `pick-and-place.csv` — has component positions
- `gerbers/*.gbr` — open in gerber viewer
- `gerbers/*.drl` — drill data present
- `fab-drawing.pdf` — title block + board view + drill table + stackup + notes + 3D render
- `assembly-drawing.pdf` — title block + front view + back view + notes
- Console summary lists all artifacts and any warnings

- [ ] **Step 6: Commit**

```bash
git add example/ tests/integration/test_pipeline_e2e.py
git commit -m "Add example config and end-to-end pipeline test"
```

---

## Task 15: README + Wrap-Up

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# kicad-tools

Tools for KiCad PCB design workflows.

## kicad-release

A CLI tool that generates a complete versioned production release package from
a KiCad 10 project: schematic PDF, fab/assembly drawings, gerbers, drill,
pick-and-place, BOM.

### Install

```bash
git clone <repo> && cd kicad-tools
python -m venv .venv
.venv/bin/pip install -e .
```

Requires:
- Python 3.11+
- KiCad 10+ (`kicad-cli` on PATH)
- Optionally: Inkscape (used as a fallback if CairoSVG fails on a particular SVG)

### Usage

```bash
# Full release
kicad-release --config release.toml

# Single step
kicad-release --config release.toml --only fab-drawing

# Dry run (list steps without executing)
kicad-release --config release.toml --dry-run

# Keep intermediate scratch files (useful for debugging fab/assembly layout)
kicad-release --config release.toml --keep-scratch

# Verbose (stream kicad-cli output)
kicad-release --config release.toml --verbose
```

See `example/release.toml` for a full annotated config.

### One-time setup: schematic title block

For the schematic PDF's title block fields to be populated by the tool, the
schematic must use KiCad text variables in the title block. In KiCad:

1. Open the schematic in eeschema.
2. File → Schematic Setup → Project → Text Variables.
3. Either declare nothing (the tool injects `TITLE`, `REV`, `DATE`, `COMPANY`
   at export time via `--define-var`), and use `${TITLE}` etc. in the title
   block fields directly.

The .kicad_sch file is **never modified** by this tool — variables are injected
at export time only.

### Title block templates

Title blocks are SVG files authored in Inkscape. See `templates/README.md`
for the authoring contract.

### Spec and design

See `docs/superpowers/specs/2026-04-14-kicad-release-tool-design.md`.
```

- [ ] **Step 2: Final full-stack verification**

Run all tests:
```bash
.venv/bin/pytest tests/ -v
```

Expected: all unit tests pass; integration tests pass when `kicad-cli` is available and the test fixture project exists.

Run the tool end-to-end one final time:
```bash
.venv/bin/kicad-release --config example/release.toml
```

Open every output artifact and confirm correctness. If anything is wrong, that's the input to the next iteration cycle (likely template tweaks).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Add README"
```

---

## Implementation Notes

- **Schematic variables:** Phase 4 requires the user to update their schematic title block fields to use `${TITLE}`, `${REV}`, `${DATE}`, `${COMPANY}` text variables. This is a one-time per-project setup. We document it in the README and remind during the schematic phase.
- **Template iteration:** The fab and assembly drawings are visually opinionated. Expect to iterate on the template SVG (region positions, sizes) after first end-to-end run. The `--keep-scratch` flag is the debugging aid here — open `releases/{ver}/.scratch/fab-drawing.svg` in Inkscape to see exactly what the tool produced before PDF conversion.
- **Drill table content:** The current `_build_drill_table` is a placeholder pointing at the drill report. If a richer table (hole size, count, plated/non-plated) is needed later, parse the drill report from `kicad-cli pcb export drill --generate-map` output. Out of scope for v1.
- **Layer name mismatches:** `kicad-cli` accepts both internal layer names (`F.Cu`) and friendlier names (`F_Cu`). Stick with internal names in the config (`F.Fab`, `Edge.Cuts`) — that's what's documented in KiCad's own docs.
- **Lock file behavior:** Both `~name.kicad_pcb.lck` and `~name.kicad_pcb.lck` (autosave variant) appear in real projects. The check looks for `~{filename}.lck` next to each file; that pattern matches both.
