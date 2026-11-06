# kicad-stitch

A standalone KiCad 10 ground-via CLI, with a separate planning engine for future
integration into a larger GUI application. It produces a placement report and SVG
preview, verifies placements with native KiCad refill and DRC, and optionally saves
a separate stitched board and project.

## Install

```sh
cd kicad-stitch
uv tool install .
```

Requires Python 3.11+ and KiCad **10.x**. The Python package installs Shapely for
geometry operations. KiCad supplies the board reader/writer and authoritative
refill/DRC engine. No editor window or scripting plugin is needed.

Supported runtimes:

- Native `kicad-cli` and a Python interpreter that can `import pcbnew`. Use
  `--runtime native --kicad-python /usr/bin/python3` when your package environment
  does not include the system KiCad bindings.
- The installed `org.kicad.KiCad` Flatpak: `--runtime flatpak`. KiCad's Python runs
  inside Flatpak; Shapely runs on the host. Flatpak must be able to read the tool
  installation and working directory. Scratch directories are created under the
  working directory because Flatpak has its own `/tmp`.

`--runtime auto` selects native when `kicad-cli` is on PATH, otherwise Flatpak.
KiCad 11 is deliberately unsupported by this adapter: SWIG removal requires an
IPC adapter. See [architecture](docs/architecture.md).

## Use

The board must have a valid, closed Edge.Cuts outline, a ground net and copper
zones, and a sibling `.kicad_pro`. A sibling `.kicad_dru` is preserved and used.

```sh
# Preview and validate. Source board/project stay unchanged.
kicad-stitch /path/to/board.kicad_pcb --report-dir ./stitch-review

# Place and publish a separate board, project and custom rules after verification.
kicad-stitch /path/to/board.kicad_pcb \
  --config stitch.toml \
  --report-dir ./stitch-applied \
  --output /path/to/board-stitched.kicad_pcb
```

Output paths must be new. Existing boards, projects and reports are never
overwritten. Without `--output`, even a successful run publishes only the report.
Both modes do the same native validation.

The report directory contains:

- `plan.json`: placed via positions, layers, native UUIDs, rule IDs and reasons,
  settings/spacing assumptions, rejected candidates, unresolved features, source
  hashes, and validation results. `schema_version` is currently `1`.
- `preview.svg`: board, overlapping ground copper, components, and colored vias.
  Hover a via for its reason and coordinates. Colors: orange island repair,
  pink transition return, blue perimeter, red signal fence, yellow finger,
  green grid, white coverage supplement.
  Red crosses mark native-rejected candidates; muted copper and existing vias
  provide clearance context.
- `baseline-drc.json` and `final-drc.json`: complete KiCad reports, including
  pre-existing issues.

Exit codes: `0` native verification passed; `2` new DRC/connectivity issues remain
and no board was published; `1` input, configuration, runtime or processing error.
**Verified means no new reported DRC issues and every added via reaches ground on
at least two layers.** Examine diagnostics for incomplete coverage, unrepairable
islands and rejected candidates; verification does not establish EMC performance
or imply that existing DRC errors were fixed.

## Placement passes

1. **Island repair:** temporarily retain disconnected ground copper in a scratch
   fill; build a graph of per-layer copper regions joined by plated pads/existing
   vias; add vias where disconnected regions overlap reference-connected copper.
   Iteration handles chains of overlaps. Normal island filtering is restored by
   applying the accepted placements to the original board copy and refilling.
2. **Signal return/fence:** detect paired `_P/_N`, `+/-`, `_DP/_DM` suffixes and
   prioritize symmetric return vias beside paired layer transitions. Set
   `pair_fences = true` for continuous fences, or explicitly select RF feed nets
   and component references in `[[signal]]` entries. Tracks, arcs and net-assigned
   custom pad/shape copper are supported, including footprint-based PCB antennas.
3. **Perimeter:** inset the actual board outline, including cutouts; distribute
   targets by arc length and search nearby perimeter stations around obstacles.
4. **Finger and grid fill:** identify elongated features removed by a configurable
   morphological opening, stitch legal portions, and fill a board-origin grid.
   A half-pitch coverage audit supplements sparse areas per contacted layer.

Every pass avoids existing pads, tracks, vias, holes, non-ground filled zones,
component courtyards (or native footprint hulls), rule areas, board edges/cutouts,
and explicit exclusions. Through vias clear obstacles on **every copper layer**,
and require full landing copper on at least two layers during planning. Native
DRC evaluates effective netclass and custom constraints afterward. Offending
candidates are removed and the board is revalidated, up to five evaluations;
unattributable new violations fail publication.

## Configuration and electrical assumptions

Start with [example/stitch.toml](example/stitch.toml). All lengths are millimetres
in KiCad board coordinates; net and reference selectors are case-sensitive globs.

Without electrical inputs, automatic pitch targets about 100 board-area cells,
bounded to 2–10 mm and legal via spacing. This is a density heuristic. Optional
maximum significant frequency and rise time tighten that pitch using a
configurable guided-wavelength heuristic; every assumption is recorded.
Explicit `pitch_mm` overrides geometric density but remains subject to the
electrical limit. A requested pitch smaller than legal spacing is an error.

Supply the antenna manufacturer's exclusions before selecting an RF feed for
fencing. Selecting an antenna net is permission to fence its selected routing;
the tool cannot infer the radiator's allowed ground geometry from its net name.
Reference selectors include all non-ground pad nets of the selected components.
Continuous differential fences also need a reviewed offset appropriate to the
line impedance. Board geometry alone cannot determine that offset.
For a differential pair with unconventional names, explicitly select its two nets
and set `differential = true` in that signal entry. Unrelated selected RF nets are
handled individually at transitions.

The reference ground defaults to the largest existing connected copper component.
Use `anchors_mm` at an existing plated ground connection to make this explicit.
Each run treats exactly one named net; it never joins distinct AGND/DGND/chassis
net names or crosses net ties automatically.

Read [placement rules and sources](docs/rules.md) for the research, evidence
levels, books/standards identified, implemented formulas and limitations.

## Library interface and GUI integration

```python
from kicad_stitch.model import Settings
from kicad_stitch.planner import plan

# snapshot is the JSON-shaped board model returned by the KiCad adapter.
result = plan(snapshot, Settings(max_frequency_hz=2.4e9))
overlay = result.to_dict()
```

`plan()` is deterministic and has no file/process/UI dependencies. The file
transaction API is `kicad_stitch.backend.run(board_path, settings, backend,
output=optional_path)`. GUI clients can render/filter the result or replace the
KiCad adapter. A modified proposal must go through native validation before save;
`plan()` alone provides geometry checks only.

## Tests

```sh
uv sync --extra dev
uv run pytest -q

# Native KiCad fixture generation, island recovery, custom-rule rejection,
# source preservation and rerun idempotency (requires KiCad 10).
KICAD_STITCH_INTEGRATION=1 uv run pytest -q

# Optional read-only test of a real project; no output board is published.
KICAD_STITCH_INTEGRATION=1 KICAD_STITCH_TEST_BOARD=/path/to/board.kicad_pcb \
  uv run pytest -q
```
