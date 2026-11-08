# kicad-stitch

A standalone KiCad 10 ground-via CLI, with a separate planning engine for future
integration into a larger GUI application. It produces a placement report and SVG
preview, verifies placements with native KiCad refill and DRC, and saves a separate
review board. Apply the review to your original project with an automatic backup,
or choose `--in-place` to validate, back up and apply in one step.

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
# Generate a review. Keep using your original project.
kicad-stitch /path/to/board.kicad_pcb --config stitch.toml --report-dir ./stitch-review

# Inspect stitch-review/preview.svg and stitch-review/board/board.kicad_pcb.
# Close the review board and the original KiCad project, then apply:
kicad-stitch apply ./stitch-review

# Or validate, back up and update the original PCB in one step:
kicad-stitch /path/to/board.kicad_pcb --config stitch.toml --in-place \
  --report-dir ./stitch-applied

# Undo using the backup directory printed by apply / --in-place:
kicad-stitch restore /path/to/.kicad-stitch-backups/TIMESTAMP-ID

# Optional export to another basename instead of the default review board:
kicad-stitch /path/to/board.kicad_pcb \
  --config stitch.toml \
  --report-dir ./stitch-export \
  --output /path/to/board-stitched.kicad_pcb
kicad-stitch apply ./stitch-export
```

**Your original project remains the working project.** The default command saves
a native-validated PCB with matching project/rules under `REPORT_DIR/board/`, using
the original basename. This copy is for review. After applying, reopen the
original `.kicad_pro`; its PCB now contains the stitches. No project switch,
schematic transfer or manual file renaming is needed.

`apply` installs the reviewed vias without replanning or merging into an edited
board. It checks hashes of the source PCB/project/custom rules and the
reviewed files against the native validation record. If anything changed, generate
a new review. Editing or saving the review in KiCad can change its bytes and
invalidate it. KiCad board/project locks also block replacement: save and close
the original before generating a review you intend to apply. Close the review
copy without saving when you finish inspecting it.

Exports using a different basename work with `apply` too. The tool uses the
original project name and source rules in scratch copies, reruns native refill,
DRC and ground-connectivity checks, and verifies that the reviewed via UUIDs,
nets and positions survive. It never drops or relocates vias during apply. New
blocking issues abort the operation before backup/replacement; annular-width
advisories follow the original review's settings. Native refill can update copper
and file serialization under the original context. Checks and the resulting board
are saved under `REPORT_DIR/apply-validation/TIMESTAMP-ID/`, with a report path
in the apply receipt. Source and review hash checks still apply. Existing v0.3.0
reviews have the required metadata and do not need regeneration for this fix.

The runtime for renamed-export validation is detected automatically. Use
`kicad-stitch apply REPORT_DIR --runtime flatpak` or the native `--kicad-python` /
`--kicad-cli` overrides if needed. A matching-basename review already has the right
context and installs the exact validated bytes without another native run.

Before replacing the PCB, the tool stores the original PCB, `.kicad_pro` and optional
`.kicad_dru` in a unique `.kicad-stitch-backups/TIMESTAMP-ID/` subdirectory next to
the source. Its `backup.json` records file hashes and the replacement identity.
Only the original **PCB file** is atomically replaced; project settings,
schematics, libraries, models and other project assets stay in place. The backup
is a board/rules snapshot, not a recursive archive of those unchanged assets.
Reports and backup directories can be excluded from version control.

`restore` checks the snapshot and refuses to overwrite later edits by default.
Use `restore BACKUP_DIR --force` to restore the PCB despite later edits. Every
restore that changes the board first backs up the current PCB/project/rules and
prints a command to undo the restore. Project settings and custom rules remain
unchanged during restore as well. Backup directories are retained until you
remove them. Failed backups or replacement checks leave the source PCB intact.

`--output` is an explicit export option, mutually exclusive with `--in-place`.
Export and report paths must be new. Old reports without saved validation hashes
need regeneration once before apply.

The report directory contains:

- `plan.json`: placed via positions, layers, native UUIDs, rule IDs and reasons,
  settings/spacing assumptions, rejected candidates, unresolved features, source
  hashes, and validation results. `schema_version` is currently `1`.
- `board/`: the saved review PCB and matching project/custom rules, on a successful
  default run. With `--output`, these files are exported to that path instead.
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

Exit codes: `0` native verification passed (possibly with warning advisories);
`2` blocking DRC/connectivity issues remain; `1` input, configuration, runtime or
processing error.

**Only regressions that can break the board block.** A run fails when KiCad
reports a new **error**, or a new electrical/fabrication hazard at any severity
(shorts, clearance, hole/edge clearance, new unconnected items, starved thermals,
drill/width limits, crossing tracks, etc.; see `HAZARD_TYPES` in `backend.py`),
or when an added via fails to reach ground on two layers. Other new **warnings**,
such as `isolated_copper` fragments left by refill, are recorded as advisories
(`advisory_issues`, with KiCad descriptions in the summary) and the run reports
`verified_with_warnings`. Set `block_new_warnings = true` for a strict
no-new-warnings policy. Existing board errors never require cleanup first, and
unresolvable islands are diagnostics, not failures.

**Work is never withheld.** Even when validation fails, the proposed board is
saved in `REPORT_DIR/board/` (or `--output`) next to `final-drc.json`, so the
complaints can be inspected in KiCad. The summary then includes
`failure_reasons`, up to five blocking issues with native descriptions/items, and
an `apply_command` using `kicad-stitch apply --force REPORT_DIR`, which installs
the inspected board anyway (status `applied_unverified`, with the usual backup
and `restore`). Without `--force`, and with `--in-place`, a failed review is
never applied.

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
candidates implicated in blocking issues are removed and the board is
revalidated, up to five evaluations; unattributable blocking issues fail
validation (the proposed board is still saved for inspection).

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
annular issues on generated vias and publishes with `verified_with_warnings`
(annular warnings involving existing items still block).
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

`kicad_stitch.workflow.apply_review(report_path)` and
`restore_backup(backup_path, force=False)` provide the same guarded apply/restore
operations for GUI callers. An optional `backend` argument to `apply_review`
selects the native adapter for a renamed export's revalidation. The library
transaction's `output=None` remains a
read-only validation API; the CLI selects a persistent review path by default.

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
