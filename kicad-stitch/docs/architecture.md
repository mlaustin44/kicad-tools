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
```

## Boundaries

- `model.py`: validated configuration, `Candidate`, and versioned `Plan` result.
  Plain dataclasses with JSON-serializable fields. No GUI framework.
- `geometry.py`: polygon conversion, bounded sampling and cross-layer union-find.
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
2. Copy those files to a scratch baseline with the same basename so KiCad loads
   the correct project rules. Refill and save with `kicad-cli pcb drc`.
3. Create an exploratory copy, retain ground islands there, and refill natively.
4. Extract geometry and plan, including an identified reference-ground region.
5. Apply vias to a fresh **baseline** copy with original island-removal policies.
   If publishing, use the requested output basename for native validation too.
6. Refill, DRC and inspect actual ground contact/connectivity.
7. Compare issue identities and multiplicities against the baseline. Remove
   generated vias implicated by new DRC or failed ground contact; remove an
   entire symmetric-return group if either side fails. Repeat up to five native
   evaluations. Record rejected positions and warn of resulting coverage gaps.
8. Fail closed if new issues cannot be attributed or remain after the limit.
9. Recheck source hashes. If requested and verified, exclusively create new
   project/rules and finally the output board. Existing files are never replaced.

Scratch cleanup is automatic. Publication rolls back files created by the current
transaction if a write fails. Separate files cannot be published as a single
filesystem transaction: the board is written last so its rules are already there.
A GUI should keep native validation off its UI thread and expose progress at these
operation boundaries. Selecting/deselecting proposed vias invalidates previous
native validation and requires a fresh evaluation.

The current native comparison detects new reported errors and warnings rather
than requiring a completely clean starting board. It also includes unconnected
items and keeps issue locations/multiplicity, so an equal total count cannot hide
a changed violation. Project-ignored checks remain ignored; the report preserves
KiCad's `ignored_checks` metadata for review.

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
RF radiators need explicit exclusions. Finger classification and coverage audits
are sampled geometric heuristics. Native candidate rejection does not rerun all
placement passes to prove that no alternative location exists.

The transaction copies the sibling project and custom-rule files. Custom rules
depending on unavailable external resources, differing project basenames or live
unsaved editor state require the caller to provide a self-contained saved project.
Reports document unresolved work instead of silently claiming full coverage.
