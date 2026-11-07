# Architecture and GUI integration

The existing release generator is a file-oriented Python CLI and the viewer is a
read-only TypeScript browser app. Stitching needs native KiCad geometry, project
rules and refill/DRC, so it is a separate Python package rather than a browser
editor feature or a dependency of the release pipeline.

```text
CLI now / GUI later
        |
        v
Settings + snapshot -> planner.plan() -> Plan (positions, reasons, diagnostics)
        |                                  |
        +------------ backend.run() -------+
                           |
                  isolated KiCad worker
                  + native kicad-cli DRC
                           |
                  verified separate board
                  + JSON / SVG reports
                           |
                  workflow.apply_review()
                           |
                  original PCB + backup
```

## Boundaries

- `model.py`: validated configuration, `Candidate`, and versioned `Plan` result.
  Plain dataclasses with JSON-serializable fields. No GUI framework.
- `geometry.py`: polygon conversion, bounded sampling and cross-layer union-find.
- `quality.py`: post-validation coverage and island-recovery measurements from
  the actual normally filled final board, independent of planning success.
- `planner.py`: pure deterministic engine operating on a JSON-shaped board
  snapshot. No subprocesses, file writes, editor state or presentation policy.
  `plan(snapshot, settings)` is the primary integration point for a GUI overlay.
- `worker.py`: standard-library-only program run by KiCad's Python; exports
  native outlines/filled ground/obstacles/tracks/bridges and writes through vias.
  It imports `pcbnew`; the host package never does. Native and Flatpak Python
  versions do not need to match.
- `backend.py`: file transaction, project/rule copying, exploratory fill, placement,
  native validation, rejection/revalidation and exclusive output publication.
- `preview.py`: standalone SVG renderer with no role in decision making.
- `workflow.py`: reviewed-file/source hash checks, tool/KiCad locks, board/rules
  snapshots, atomic source-PCB replacement and reversible restoration. No native
  rerun or replanning is needed to install identical validated bytes.
- `cli.py`: argument parsing and report presentation.

Snapshots use millimetres and native layer/net names. Polygon records are
`{"shell": [[x,y], ...], "holes": [[[x,y], ...], ...]}`. Ground polygons are
per layer; obstacle polygons are combined across layers for through-via planning.
The bridge list records plated pad/via positions and their actual layer spans.
The `Plan` JSON includes an integer `schema_version` so a future application can
reject incompatible persisted reports. Worker snapshots currently belong to the
same package version; they are not a separately stabilized file format.

## Native verification and publication

1. Hash source PCB, project and optional custom-rule file.
   Resolve and validate the CLI/Python runtime pair before creating scratch files:
   probe `pcbnew` in candidate interpreters outside the isolated host environment,
   require a matching KiCad major/minor version, and cache the selection. Auto
   mode may switch the entire pair to Flatpak; explicit overrides never do.
2. Copy those files to a scratch baseline with the same basename so KiCad loads
   the correct project rules. Round-trip the scratch board once through KiCad's
   reader/writer to materialize project defaults before copies diverge, then
   refill and save with `kicad-cli pcb drc`.
3. Create an exploratory copy, retain ground islands there, and refill natively.
4. Extract geometry and plan, including an identified reference-ground region.
5. Apply vias to a fresh **baseline** copy with original island-removal policies.
   If publishing, use the requested output basename for native validation too.
6. Refill, DRC and inspect actual ground contact/connectivity.
7. Compare issue identities and multiplicities against the baseline. For changed
   `unconnected_items` representatives, query native connectivity on affected
   nets in both baseline and proposed boards. If every existing connection
   survives and the endpoints were already disconnected on a net with baseline
   unconnected errors, retain the raw report and record the edge as an unchanged
   connectivity issue instead of a regression. Remove
   generated vias implicated by blocking DRC or failed ground contact; remove an
   entire symmetric-return group if either side fails. Repeat up to five native
   evaluations. Record rejected positions and warn of resulting coverage gaps.
8. Fail closed if new issues cannot be attributed or remain after the limit.
   With `allow_annular_width_warnings`, native annular-width warnings referencing
   only generated vias are advisories. Keep them in the raw reports and complete
   `new_issues` list, also classify them as `advisory_issues`, and use
   `verified_with_warnings`. Annular errors and all other issues remain blocking.
9. Recheck source hashes. If requested and verified, exclusively create new
   project/rules and finally the output board. Existing files are never replaced.
   Record the source path, validated basename and SHA-256 hashes of the native
   baseline and validated scratch files, mapped to source and published paths
   respectively. The CLI normally publishes to `REPORT_DIR/board/` using the
   source basename; `output=None` remains available
   for library clients that only need read-only validation.

After the last native evaluation, measure actual contour gaps and per-layer legal
coverage, and intersect original exploratory islands with reference-connected
final copper. Distinguish island recovery from normal island removal. Previews
and the transaction's returned snapshot use the final native fill. The source
exploratory model remains available internally for recovery accounting.

Scratch cleanup is automatic. Publication rolls back files created by the current
transaction if a write fails. Separate files cannot be published as a single
filesystem transaction: the board is written last so its rules are already there.
A GUI should keep native validation off its UI thread and expose progress at these
operation boundaries. Selecting/deselecting proposed vias invalidates previous
native validation and requires a fresh evaluation.

## Applying and restoring a review

The original project stays the working project. A CLI review includes a saved
native-validated board and matching project/rules. `apply_review(report_path)`
requires a verified status, matching source/export hashes, unchanged native
baseline rules and the source basename used during native validation. It never
attempts a merge into a modified board. Old reports lacking this provenance or
exports validated under a different basename require a new default review.

KiCad can normalize project files while saving scratch boards, materializing
implicit defaults. Therefore the review's project/rules hashes must match the
native baseline context; the source is separately checked against its original
raw hashes. The original `.kicad_pro` is never replaced with the normalized copy.

Application serializes with an exclusive per-board tool lock and refuses KiCad
PCB/project lock files. It snapshots the original PCB/project/custom rules in a
unique `.kicad-stitch-backups/` subdirectory, writing a manifest and complete file
contents before replacement. It writes and syncs the new PCB into a temporary file
beside the source, retains its permission bits, then rechecks source hashes and
KiCad locks immediately before an atomic `os.replace`. Source project settings,
custom rules, schematic and other project assets are not replaced.

`restore_backup(path, force=False)` verifies the snapshot and checks that the
current files still match the operation's installed state. Later edits require
explicit `force=True`; a restore first snapshots the current files, so restoration
can itself be undone. Only the PCB is restored; project/rule settings retain their
current values. A manifest written before replacement also permits recovery after
an interrupted operation: the current board is either the original or the intended
replacement. External processes do not honor this tool's lock, so the project
must remain closed throughout replacement. These are local board/rules snapshots,
not recursive archives of all project assets or filesystem-wide transactions.

The native comparison detects regressions rather than requiring a completely
clean starting board. Ordinary DRC issues retain locations and multiplicity.
Unconnected report edges can change representatives without an electrical change;
the additional native comparison uses component membership of stable pre-existing
non-zone UUIDs. It allows merges and rejects splits, missing items and net
reassignments, even when total disconnected-component counts remain equal.
One zone UUID can span multiple islands, so zone UUIDs are not used as vertices
that would incorrectly join their islands. Unknown or zone-only report endpoints
remain blocking. Project-ignored checks remain ignored, with `ignored_checks`
metadata preserved. No raw native report entry is removed or rewritten.

The CLI exposes failure reasons and native blocking descriptions directly, with
the first five issues in its summary and complete details in the plan. Unrelated
baseline errors remain available for normal board cleanup, without blocking the
stitching result solely because native ratsnest representatives changed.

Annular width is deliberately absent from global dimension preflight: the native
engine honors its effective rules and severity. Retained warning advisories do not
alter either source or published project constraints or severities.

## KiCad API lifecycle

[KiCad's deprecation notice](https://dev-docs.kicad.org/en/apis-and-binding/pcbnew/)
marks SWIG deprecated from KiCad 9, with removal planned for KiCad 11. It remains
useful here for standalone **KiCad 10** file access, and is isolated accordingly.
Zone fill always runs through `kicad-cli`, not an in-process SWIG zone filler.

A future GUI can supply an [IPC](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/)
snapshot/transaction adapter, carrying editor selection and undo/commit semantics.
That adapter must reproduce native shape/rule-area extraction and the same refill,
DRC and contact guarantees before claiming equivalent support. This version does
not claim an IPC implementation or KiCad 11 compatibility.

## Known bounds

Only through vias are generated; no blind/microvia stack synthesis, routing of
unreachable islands, creation of missing ground zones, thermal pad drilling,
automatic ground-net merging, capacitor-ground optimization or EM solving.
Signal pairing uses suffix and geometric hints rather than schematic intent.
RF radiators need explicit exclusions. Finger classification is a geometric
heuristic; the continuous coverage calculation uses Euclidean distance and a
0.1 mm geometric tolerance, not an electromagnetic or path-inductance model.
Native candidate rejection does not rerun all placement passes to prove that no
alternative location exists, but final quality is remeasured after rejection.
Later runs can refine remaining signal/contour gaps after native refill changes
the available landing geometry; universal rerun idempotence is not guaranteed.

Grid, perimeter, signal and finger targets use independent pitches. Grid targets
are preferences, not snap constraints: local polygon intersection, spacing-disk
subtraction and nearest/maximum-clearance sites determine placement. Internal
power-zone antipads are permitted by default, while outer zones remain excluded.
Configurable zone policy never overrides rule-area keepouts. Separate metadata
records target displacement, geometric quality and native verification.

The transaction copies the sibling project and custom-rule files. Custom rules
depending on unavailable external resources, differing project basenames or live
unsaved editor state require the caller to provide a self-contained saved project.
Reports document unresolved work instead of silently claiming full coverage.
