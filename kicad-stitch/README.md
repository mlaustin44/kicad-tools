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

Requires Python 3.11+ and KiCad **10.x**. The Python package installs Shapely 2.1+ for
geometry operations. KiCad supplies the board reader/writer and authoritative
refill/DRC engine. No editor window or scripting plugin is needed.

Supported runtimes:

- Native `kicad-cli` and a Python interpreter that can `import pcbnew`. The tool
  probes interpreters beside the CLI, KiCad's bundled macOS Python, common system
  Python paths, PATH interpreters and the host/base Python. It selects an
  interpreter whose bindings match the CLI's major/minor KiCad version. The uv
  tool environment can remain isolated; it does not need `pcbnew` installed there.
  To override detection, use `--runtime native --kicad-python /usr/bin/python3`
  (typical Linux system installation), or the Python bundled with your KiCad.
- The installed `org.kicad.KiCad` Flatpak: `--runtime flatpak`. KiCad's Python runs
  inside Flatpak; Shapely runs on the host. Flatpak must be able to read the tool
  installation and working directory. Scratch directories are created under the
  working directory because Flatpak has its own `/tmp`.

`--runtime auto` prefers a working native CLI/Python pair and falls back to the
installed KiCad Flatpak if no compatible native pair is available. CLI version
and `pcbnew` import/version are checked before any scratch copy, refill or DRC.
An explicit `--runtime native`, `--kicad-python` or `--kicad-cli` is authoritative:
failures are reported with guidance instead of silently switching installations.
Native executable overrides cannot be combined with `--runtime flatpak`.

If no interpreter can import compatible bindings, install the Python bindings
provided by your KiCad distribution or select a working interpreter explicitly.
`pcbnew` is a native KiCad module, not a dependency to install from PyPI. Reports
record the selected runtime, Python command and CLI command.

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
  It uses the actual final filled copper, including power-plane antipads and
  island removal, rather than the exploratory island-retention fill.
  Hover a via for its reason and coordinates. Colors: orange island repair,
  pink transition return, blue perimeter, red signal fence, yellow finger,
  green grid, white coverage supplement.
  Red crosses mark native-rejected candidates; muted copper and existing vias
  provide clearance context.
- `baseline-drc.json` and `final-drc.json`: complete KiCad reports, including
  pre-existing issues.

Exit codes: `0` native verification passed (possibly with annular-width warning
advisories); `2` blocking DRC/connectivity issues remain
and no board was published; `1` input, configuration, runtime or processing error.
**Verified means no new blocking DRC/connectivity regression and every added via
reaches ground on at least two layers.** Existing unrelated board errors do not
require cleanup before stitching. `verified_with_warnings` also permits native annular-width
warnings on generated vias, recorded in `advisory_issues` and the unmodified DRC
report. Annular-width errors and all other new DRC issues still reject candidates.
Examine diagnostics for incomplete coverage, unrepairable
islands and rejected candidates; verification does not establish EMC performance
or imply that existing DRC errors were fixed.

If verification fails, the CLI includes `failure_reasons`, `blocking_issue_count`,
native descriptions/items for up to five blocking issues, and
`unconnected_via_count`. The complete issue details are in `plan.json` under
`validation.blocking_issue_details`; raw KiCad reports are always preserved.

KiCad can choose a different pair of objects to represent an existing unconnected
net after refill. Such a changed ratsnest edge is not automatically a new fault.
For these cases the tool compares native connected-component membership before
and after: existing connections must all survive, and reported endpoints must
already have been disconnected. Component merges are allowed; splits remain
blocking even if the total error count stays the same. Unknown/zone-only endpoints
are kept blocking when connectivity preservation cannot be proven. Accepted
endpoint changes are recorded in `validation.unchanged_connectivity_issues`.

## Placement passes

1. **Island repair:** temporarily retain disconnected ground copper in a scratch
   fill; build a graph of per-layer copper regions joined by plated pads/existing
   vias; add vias where disconnected regions overlap reference-connected copper.
   GEOS maximum-inscribed-circle searches solve the actual free landing regions
   after spacing exclusions; no fixed sampling grid is required. Iteration
   handles chains of overlaps. Normal island filtering is restored by
   applying the accepted placements to the original board copy and refilling.
2. **Signal return/fence:** detect paired `_P/_N`, `+/-`, `_DP/_DM` suffixes and
   prioritize symmetric return vias beside paired layer transitions. Set
   `pair_fences = true` for continuous fences, or explicitly select RF feed nets
   and component references in `[[signal]]` entries. Tracks, arcs and net-assigned
   custom pad/shape copper are supported, including footprint-based PCB antennas.
3. **Perimeter:** inset the actual board outline, including cutouts; use a separate
   edge pitch and distribute targets by arc length. Search continuously along
   legal contour segments, then within a bounded inward band. Audit and attempt
   to close actual remaining fence gaps.
4. **Finger and grid fill:** identify elongated features removed by a configurable
   morphological opening, prioritize distal tips and require contact with the
   feature when counting existing stitching. Use square or staggered nominal
   grid targets, relocating obstructed targets locally. A continuous polygon
   coverage audit finds off-grid pockets separately on each ground layer.

Every pass avoids existing pads, tracks, vias, holes, protected filled zones,
component courtyards (or native footprint hulls), rule areas, board edges/cutouts,
and explicit exclusions. Through vias clear obstacles on **every copper layer**,
and require full landing copper on at least two layers during planning. Native
DRC evaluates effective netclass and custom constraints afterward. Offending
candidates are removed (except permitted annular-width warnings) and the board is
revalidated, up to five evaluations;
unattributable new violations fail publication.

`zone_policy = "internal_antipads"` allows through-via clearance holes in internal
power pours, while retaining outer-layer zone exclusions. Treating every internal
power fill as immutable would incorrectly prohibit normal ground stitching.
Choose `"avoid"` to preserve all other-net fills, or `"antipads"` to also allow
outer-layer zone antipads. Native refill, DRC and connectivity regression checks
still apply; deliberate keepouts always remain hard exclusions.

DRC acceptance and placement completeness are separate. `validation.placement_quality`
measures the actual final board, including any rejected candidates: edge gaps,
per-layer legal coverage and relocated placements. `validation.island_recovery`
counts regions connected, partially connected, still disconnected or removed by
the normal fill policy. **Removed copper is never counted as recovered ground.**
Unresolved diagnostics include landing size/clearance reasons and coordinates.

## Configuration and electrical assumptions

Start with [example/stitch.toml](example/stitch.toml). All lengths are millimetres
in KiCad board coordinates; net and reference selectors are case-sensitive globs.

### Annular width and fab via sizes

KiCad annular width is radial: `(diameter_mm - drill_mm) / 2`. A 0.5/0.3 mm or
0.6/0.4 mm via has a 0.1 mm radial ring and a 0.2 mm diameter difference. JLC's
[via specification](https://jlcpcb.com/capabilities/pcb-capabilities) describes a
diameter difference, which must not be copied directly into KiCad's radial-width
minimum. The separate PTH annular-ring specification is also not interchangeable
with that via diameter allowance.

Annular width is evaluated by native DRC, including project severity and custom
rules, rather than rejected against the global project minimum during preflight.
By default `allow_annular_width_warnings = true` preserves **warning-severity**
annular issues on generated vias and publishes with `verified_with_warnings`.
The report includes the radial width and diameter difference. The source and
published project rules/severities are not changed. Set this option to `false`
to reject those warnings too. If the project treats annular width as an **error**,
it remains blocking; correct the project's radial minimum to match your chosen
fab process if those via sizes are intended. The tool does not certify fab
acceptance from a warning or infer a vendor profile.

### Spacing and signal selection

Without electrical inputs, automatic interior pitch targets about 100 board-area
cells, bounded to 2–10 mm and legal via spacing. The edge target defaults to half
the interior pitch; signal fencing inherits the edge target, while narrow-feature
pitch is capped at twice `neck_width_mm`. These are separate geometric density
heuristics, with `grid_pitch_mm`, `perimeter_pitch_mm`, `signal_pitch_mm`, and
`finger_pitch_mm` overrides. Legacy `pitch_mm` is the interior target alias.

Maximum significant frequency/rise time optionally apply separate wavelength
bounds: default λ/10 for interior stitching and λ/20 for fences/edges/fingers.
Both divisors and the dielectric assumption are configurable and reported. A
requested pitch below legal spacing is an error. No clock frequency or edge rate
is inferred from board area or a net name.

`search_radius_mm` bounds local target movement (default: half the interior
pitch). Contour passes additionally cap movement to half their own pitch. The
report records each nominal target and its actual displacement, so changing the
pattern does not conceal why vias moved.

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
