# KiCad Release Automation Tool — Design Spec

**Date:** 2026-04-14
**Status:** Approved for implementation
**Project location:** `release_generator/` package within `kicad-tools` repo

## Purpose

A Python CLI tool that generates a complete, versioned production release package from a KiCad 10 project. Given a project directory and a TOML config, the tool produces a release folder containing:

- Schematic PDF (with title block fields populated)
- Fabrication drawing PDF (composite: title block, board outline, drill table, stackup, fab notes, optional 3D render)
- Assembly drawing PDF (composite: title block, front view, back view, assembly notes)
- Gerbers, drill files, drill report
- Pick-and-place CSV
- BOM CSV (grouped, with custom columns)

The tool replaces the user's current ad-hoc/KiBot-based workflow with a single repeatable command.

## Test Fixture

Primary development and validation target is the user's real project:
`/home/mlaustin/electronics/kicad_designs/example_pcb/`

This is a 4-layer board with multi-page schematic, real BOM, and standard FR4 stackup — exercises the full feature set.

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scope | Single tool covering all artifacts | User wants one cohesive deliverable; testing performed throughout to catch issues incrementally |
| Rendering backend | SVG-based composition (not DXF) | SVG→PDF via CairoSVG/Inkscape is dramatically more reliable than DXF→PDF (LibreOffice/Inkscape DXF importers are lossy). `kicad-cli pcb export svg` is native, lossless. SVG manipulation is plain XML. |
| Schematic title block update | Inject `--define-var` at PDF export time | Schematic file isn't modified per release (no git churn, no risk of corruption when KiCad is open). Requires one-time setup of `${REV}`/`${TITLE}`/`${DATE}` variables in the schematic's title block. |
| BOM source | `kicad-cli sch export bom` then post-process CSV | Uses KiCad's own hierarchical sheet flattening and field handling. Post-processing reshapes columns/grouping per config. Avoids re-implementing schematic parsing. |
| Template authoring contract | Named `<rect id="…">` regions for content placement; `{{PLACEHOLDER}}` strings for text | Template authored visually in Inkscape. Tool finds named rectangles by id, reads bounding box, replaces with rendered content. Start simple; iterate if it proves limiting. |
| Testing posture | Manual first; integration tests for kicad-cli wrappers; unit tests only for obvious candidates (config validation, placeholder substitution, BOM CSV reshape); promote to automated test if any area needs >1 fix cycle | This is closer to a script/utility than a full application; avoid over-testing, but capture real bugs as regression tests |

## Architecture

```
kicad-tools/
├── pyproject.toml
├── README.md
├── release_generator/
│   ├── __init__.py
│   ├── __main__.py           # CLI entry point (argparse), routes to pipeline
│   ├── config.py             # TOML load + validation
│   ├── pipeline.py           # orchestrates steps based on --only/--all
│   ├── kicad_cli.py          # subprocess wrapper around kicad-cli (timeout, stderr capture, version check)
│   ├── schematic.py          # PDF export with --define-var for title block fields
│   ├── gerbers.py            # gerber + drill + pos passthrough exports
│   ├── bom.py                # kicad-cli sch export bom + post-process to config columns/grouping
│   ├── board_introspect.py   # parse .kicad_pcb for stackup, dimensions, layer count, drill data
│   ├── render3d.py           # kicad-cli pcb render → PNG
│   ├── svg_template.py       # load SVG, find {{placeholders}} and id="region" rects, substitute
│   ├── fab_drawing.py        # compose fab drawing
│   ├── assembly_drawing.py   # compose assembly drawing
│   ├── svg_to_pdf.py         # CairoSVG primary; Inkscape CLI fallback
│   └── utils.py              # paths, lock-file detection, output dir scaffolding
├── templates/                # ships with example title block templates
│   └── titleblock_a4.svg
├── docs/
│   └── superpowers/specs/
│       └── 2026-04-14-kicad-release-tool-design.md  (this file)
└── tests/
    ├── fixtures/
    ├── unit/
    └── integration/
```

### Module responsibilities

- **`board_introspect.py`** — single owner of `.kicad_pcb` S-expression parsing. Returns structured data (stackup layers, board width × height, enabled copper layers, drill report) consumed by `gerbers.py`, `fab_drawing.py`, and `render3d.py`.
- **`kicad_cli.py`** — every subprocess call to `kicad-cli` goes through this module. Centralizes timeout handling, stderr capture, version checking (KiCad 10+ required), and consistent error reporting.
- **`svg_template.py`** — shared by fab and assembly drawing modules. Handles two distinct substitution mechanisms: text placeholder strings (`{{REV}}`) and region rectangles (`<rect id="board-view"…>`).
- **`svg_to_pdf.py`** — CairoSVG is primary backend (deterministic, dependency-free Python). Inkscape CLI is fallback if CairoSVG fails on a particular template.

## Pipeline

CLI loads config, scaffolds output directory, runs steps. `--only <step>` runs a single step; default runs all. Steps:

```
1. config.load(release.toml)
   └─→ validated Config object, output dir releases/{version}/

2. preflight checks (utils)
   ├─ kicad-cli version ≥ 10
   ├─ no .lck files for pcb/sch
   ├─ template SVG exists, parses, has expected placeholders
   └─ output dir created

3. board_introspect.parse(pcb_file)         [in-memory only, feeds steps 6 + 7]
   ├─→ stackup
   ├─→ dimensions, layer count
   ├─→ enabled layers
   └─→ drill report

4. schematic.export_pdf()
   └─ kicad-cli sch export pdf --define-var REV=… --define-var TITLE=… --define-var DATE=…
   └─→ releases/{ver}/schematic.pdf

5. bom.generate()
   ├─ kicad-cli sch export bom (raw CSV)
   └─ post-process: group_by, columns, ref designator concatenation
   └─→ releases/{ver}/bom.csv

6. gerbers.export()
   ├─ kicad-cli pcb export gerbers
   ├─ kicad-cli pcb export drill
   └─ kicad-cli pcb export pos --format csv
   └─→ releases/{ver}/gerbers/*.gbr, *.drl, drill-report.txt
       releases/{ver}/pick-and-place.csv

7. render3d.export()                        [only if fab.include_3d_render = true]
   └─ kicad-cli pcb render --side {top,bottom} --quality high → PNG
   └─→ scratch dir, consumed by step 8

8. fab_drawing.compose()
   ├─ kicad-cli pcb export svg --layers Edge.Cuts
   ├─ load template, run svg_template substitution
   ├─ replace id="board-view"/"drill-table"/"stackup-table"/"fab-notes"/"render-3d" regions
   └─ svg_to_pdf.convert()
   └─→ releases/{ver}/fab-drawing.pdf

9. assembly_drawing.compose()
   ├─ kicad-cli pcb export svg --layers F.Fab,F.Courtyard,Edge.Cuts (front)
   ├─ kicad-cli pcb export svg --layers B.Fab,B.Courtyard,Edge.Cuts (back)
   ├─ load template, substitute, fill id="front-view"/"back-view"/"assembly-notes"
   └─ svg_to_pdf.convert()
   └─→ releases/{ver}/assembly-drawing.pdf

10. summary report (stdout) — list artifacts, sizes, any warnings
```

### Error handling

- Fail-fast on preflight (locked files, missing kicad-cli, malformed template).
- Per-step errors abort the pipeline; report which step failed and which artifacts were produced before the failure.
- `--only` mode lets you re-run a single step without redoing everything.
- Scratch files (3D PNGs, intermediate SVGs) live in `releases/{ver}/.scratch/` and are cleaned at end unless `--keep-scratch` is passed.

## SVG Template Contract

The template author creates an SVG (in Inkscape) with two kinds of dynamic content.

### Text placeholders

Plain `{{NAME}}` strings inside `<text>` or `<tspan>` elements get string-replaced.

| Placeholder | Source |
|-------------|--------|
| `{{TITLE}}` | Per-drawing config (`fab_drawing.title`, `assembly_drawing.title`) |
| `{{DATE}}` | `[project].date` (or today if `"auto"`) |
| `{{REV}}` | `[project].version` |
| `{{DRAWN_BY}}` | `[titleblock].drawn_by` |
| `{{COMPANY}}` | `[titleblock].company` |
| `{{CONFIDENTIALITY}}` | `[titleblock].confidentiality` |
| `{{PAGE}}` | `"Page 1 of 1"` |
| `{{FILENAME}}` | Source PCB filename (basename) |
| `{{REV_1}}`, `{{EC_1}}`, `{{DESC_1}}`, `{{REV_2}}`… | From `[[revisions]]` array (1 = newest) |

Missing placeholder in template → tool warns, leaves literal text. Unknown placeholder in template → ignored.

### Region rectangles

A `<rect>` with a recognized `id` attribute defines where rendered content goes. The tool reads the rect's `x`, `y`, `width`, `height`, removes the rect, and renders content scaled (preserving aspect) to fit.

| ID | Drawing | Content |
|------|---------|---------|
| `board-view` | fab | Edge.Cuts SVG, scaled to fit, centered |
| `drill-table` | fab | Generated table: hole size, count, plated/non-plated, symbol |
| `stackup-table` | fab | Generated table: layer name, type, thickness, material |
| `fab-notes` | fab | Numbered list from `fab_drawing.notes` |
| `render-3d` | fab | PNG from kicad-cli render, embedded as `<image>`, aspect-preserved |
| `front-view` | assembly | F.Fab + F.Courtyard + Edge.Cuts SVG, scaled to fit |
| `back-view` | assembly | B.Fab + B.Courtyard + Edge.Cuts SVG, scaled to fit |
| `assembly-notes` | assembly | Numbered list from `assembly_drawing.notes` |

Missing region in template (e.g., `id="render-3d"` absent but `include_3d_render = true`) → tool warns and skips that content.

### Authoring workflow

1. Set page size (A4 etc.).
2. Draw title block: borders, logos, static labels, revision table grid — normal Inkscape objects.
3. Type `{{REV}}` etc. into text elements at desired position/style.
4. For dynamic regions, draw a rectangle, open Object Properties (Ctrl+Shift+O), set its ID. Stroke/fill don't matter — they get removed.
5. Optionally Path > Object to Path on all text to eliminate font dependency.
6. Save as plain SVG.

The tool ships an example `templates/titleblock_a4.svg` as a starting point. The user (working with Claude) will author the project-specific template during the implementation phase.

## Config File (`release.toml`)

```toml
[project]
name = "Example PCB"
version = "3.2"
date = "2026-04-14"             # or "auto"
pcb_file = "example_pcb.kicad_pcb"
schematic_file = "example_pcb.kicad_sch"

[titleblock]
template = "templates/titleblock_a4.svg"   # default; overridable per drawing
company = "Acme Corp"
drawn_by = "M Austin"
logo_file = "templates/logo.svg"        # optional
confidentiality = "PROPRIETARY AND CONFIDENTIAL"

[[revisions]]                               # newest first
rev = "A"
ec = "N/A"
description = "ADD LOCATING FEATURE SLOTS"

[schematic]
# Variables injected at PDF export. Defaults: TITLE=project.name, REV=project.version,
# DATE=project.date, COMPANY=titleblock.company. Override with extra_vars if needed:
# extra_vars = { CUSTOM = "value" }

[fab_drawing]
title = "Fab Drawing"
page_size = "A4"
notes = [ "FABRICATE IN ACCORDANCE WITH IPC-6013 …", … ]
include_3d_render = true
render_view = "top"                         # "top", "bottom", or "both"
# template = "templates/fab_a4.svg"         # optional override

[assembly_drawing]
title = "Assembly Drawing"
page_size = "A4"
notes = [ … ]
layers_front = ["F.Fab", "F.Courtyard", "Edge.Cuts"]
layers_back = ["B.Fab", "B.Courtyard", "Edge.Cuts"]

[bom]
group_by = ["value", "footprint"]
columns = ["reference", "value", "footprint", "quantity", "mpn", "manufacturer"]

[gerbers]
layers = "auto"
subtract_soldermask = false
```

### Validation rules

- All file paths resolve relative to the directory containing `release.toml`.
- `pcb_file`, `schematic_file`, `template`, optional `logo_file` must exist.
- `version` must be a non-empty string; sanitized for use as a directory name (path separators removed).
- `date = "auto"` resolved to `datetime.date.today().isoformat()`.
- `[[revisions]]` must have ≥ 1 entry.
- `render_view` must be `"top"`, `"bottom"`, or `"both"`. When `"both"`, the `render-3d` region is split horizontally and contains both views side-by-side, each scaled to fit its half.
- `gerbers.layers` is `"auto"` or a list of layer name strings.
- `bom.columns` may reference symbol fields that don't exist in the schematic (e.g., `mpn`, `manufacturer`). Missing fields render as empty cells; tool emits one warning per missing field at the start of BOM generation.

## CLI Surface

```bash
kicad-release --config release.toml                        # full pipeline
kicad-release --config release.toml --only fab-drawing     # one step (repeatable)
kicad-release --config release.toml --only assembly-drawing
kicad-release --config release.toml --only schematic
kicad-release --config release.toml --only gerbers
kicad-release --config release.toml --only bom
kicad-release --config release.toml --only render
kicad-release --config release.toml --dry-run              # show steps + outputs, run nothing
kicad-release --config release.toml --keep-scratch         # don't clean intermediate files
kicad-release --config release.toml --verbose              # full kicad-cli output streamed
```

Exit codes: `0` success, `1` config error, `2` preflight failure, `3` step failure.

## Implementation Phases (with validation gates)

Each phase ends with a manual smoke test against the real `example_pcb` project.

| Phase | Deliverable | Validation gate |
|-------|-------------|-----------------|
| 0 | Project scaffold: `pyproject.toml`, package structure, CLI skeleton, `--dry-run` works | `kicad-release --dry-run` lists steps |
| 1 | Config loader + validation + preflight | Tool refuses bad configs with clear errors; accepts a real `release.toml` |
| 2 | `board_introspect.py` — stackup, dimensions, layer list | Print extracted data, compare to KiCad UI |
| 3 | Gerbers + drill + pos passthrough | Artifacts present in `releases/3.2/gerbers/`, open one in a gerber viewer |
| 4 | Schematic PDF with `--define-var` | Requires user to update schematic title block to use `${REV}` etc. once. Open output PDF, verify fields populated |
| 5 | BOM via kicad-cli + post-processing | Open CSV, verify grouping/columns match config |
| 6 | 3D render | PNG looks right |
| 7 | SVG template engine (text + region substitution) | Unit test: substitution edge cases. Manual: substitute on hand-built test SVG |
| 8 | Title block template authoring (Inkscape walkthrough) → ship `templates/titleblock_a4.svg` | Used by phases 9 and 10 |
| 9 | `fab_drawing.py` composition + `svg_to_pdf.py` (CairoSVG) | Open PDF; if layout is fiddly → add integration test with reference check |
| 10 | `assembly_drawing.py` composition | Open PDF |
| 11 | End-to-end: full `kicad-release --config release.toml` | Every artifact present and correct |
| 12 | README + example template + sample `release.toml` | A stranger could pick up the repo and figure it out |

## Dependencies

| Package | Purpose |
|---------|---------|
| Python 3.11+ | `tomllib` in stdlib, modern type hints |
| `cairosvg` | SVG → PDF rendering (primary) |
| `lxml` | SVG (XML) parsing and manipulation |
| `Pillow` | PNG handling for 3D render embedding |
| `pytest` | Test runner |
| `kicad-cli` (system) | KiCad 10+ — verified at preflight |
| Inkscape (system, optional) | SVG → PDF fallback. Used only if CairoSVG fails on a particular template; tool runs without it as long as CairoSVG succeeds. |

## Out of Scope (explicitly)

- Editing `.kicad_sch` or `.kicad_pcb` files in place (schematic title block uses variable injection instead).
- Multi-page fab/assembly drawings (single page each).
- Visual regression test framework (only added if specific outputs prove flaky).
- Direct schematic S-expression parsing for BOM (we post-process kicad-cli's output instead).
- DXF intermediate format (replaced by SVG).
- KiCad versions older than 10 (preflight rejects).
