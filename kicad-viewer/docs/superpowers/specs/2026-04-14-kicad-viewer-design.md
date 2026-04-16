# kicad-viewer — Design Spec

**Date:** 2026-04-14
**Author:** Matthew Austin
**Status:** v1 design, approved

## Goal

A browser-based KiCad 10 project viewer. A visitor drops a project (raw files
or a release-tool bundle) and immediately sees the schematic (with full
sheet hierarchy), the PCB (layer-aware, with net labels), and a 3D render,
with bidirectional cross-probing across all three views. Pure static Jamstack
app on Cloudflare Pages, zero backend in v1.

This is also a portfolio piece: the landing page carries attribution, the
design favours craft (hand-written CSS, minimal dependencies, small bundles)
over default-framework conventions.

## Scope

### In v1

- Landing page at `/` — type-led minimal design, prominent "by Matthew Austin"
  attribution, GitHub link, "Open viewer" CTA.
- Viewer app at `/viewer`:
  - **Load:** drop zip, folder (File System Access API where supported; file
    picker fallback), or individual files. Auto-detects a release bundle via
    `manifest.json` at archive root; otherwise parses raw project files.
  - **Schematic tab:** multi-sheet hierarchy with sheet tree, breadcrumb,
    double-click-to-dive into sheet symbols. Click component → inspector
    (refdes, value, footprint, MPN, manufacturer, datasheet link, DNP flag,
    pins table). Pan, zoom, search by refdes or net.
  - **PCB tab:** layer toggles for all standard KiCad layers (copper, silk,
    mask, paste, courtyard, fab, edge cuts, drill, vias) with KiCad-default
    colours. Net and pour labels at zoom. Click footprint → inspector.
    Hover-highlight nets. Pan, zoom, fit.
  - **3D tab:** loads sidecar `.glb` via Three.js. Orbit, pan, zoom. Click
    mesh → inspector. Camera animates to selection driven from elsewhere.
    Empty state with drop zone if no GLB available.
  - **Split tab:** two panes, each with its own inline view picker (any of
    sch / pcb / 3d / another sheet). Resizable divider. Shared left sidebar
    and right inspector follow the focused pane.
  - **Cross-probing:** one shared selection store drives all views. See
    the contract table below.
  - **Persistence:** last loaded project cached in IndexedDB, auto-reopens on
    return visit, with "clear / load new" affordance.
  - **Footer:** "Built by Matthew Austin, 2026", project path, cursor coords
    (PCB only).
- Deployment: Cloudflare Pages with GitHub integration. Pushes to `main`
  trigger production deploys; PRs get preview URLs.

### Out of scope (deferred)

- v2-D — upload & shareable URLs (requires Cloudflare R2 + Pages Functions).
- DRC/ERC visualization, BOM table view, any editing. This is a read-only
  viewer.
- In-browser STEP parsing (occt-import-js). GLB only.
- Embed mode (iframe or web component) for use in external docs.
- Mobile-responsive polish. Desktop is the v1 target; mobile works but is
  not optimized.
- `[viewer]` artifact emitter in the `kicad-release` Python tool. v1 ships
  with the bundle format documented; release-tool integration is a small
  follow-up.
- 3D cross-probing is a stretch goal within v1. If KiCad 10's `pcb export glb`
  output turns out not to have per-footprint named nodes, 3D ships as a
  static view and cross-probing becomes a v2 feature; the viewer does not
  block on this.

## Stack

- **SvelteKit** with `adapter-static` for client-rendered SPA output. No SSR
  (the viewer is client-only: WebGL, large file parsing, IndexedDB).
- **Vite** + **TypeScript** (strict mode).
- **Cloudflare Pages** for hosting; GitHub integration for CI/CD.
- **Dependencies** (all MIT/permissive):
  - `three` — 3D rendering (GLTFLoader from `three/examples/jsm`).
  - `fflate` — zip extraction.
  - `pako` — gzip decompression for bundle payloads.
  - Vendored parser module: selected files from KiCanvas's `src/kicad/`
    directory, pinned to a specific upstream commit SHA, stripped of all UI
    and rendering code. Re-exposed through a narrow TypeScript API in
    `src/lib/parser/` so we don't leak upstream internals.
- **No state management library.** Svelte stores are sufficient.
- **No CSS framework.** Plain CSS with custom properties, Open Props for the
  design-token baseline. Hand-written chrome is part of the craft signal.

## Architecture

```
[File drop / URL / IndexedDB]
         │
         ▼
  ┌──────────────────┐
  │  ProjectLoader    │  zip/folder/files → ProjectBlob (filemap + manifest)
  └──────────────────┘
         │
         ▼
  ┌──────────────────┐
  │  KiCadParser      │  .kicad_sch/.kicad_pcb → Project (TS model)
  └──────────────────┘
         │
         ▼
  ┌──────────────────┐        ┌────────────────────┐
  │  ProjectStore     │◄──────│  SelectionStore     │
  │  (Svelte writable)│       │  (Svelte writable)  │
  └──────────────────┘        └────────────────────┘
     │       │      │                ▲   ▲   ▲
     ▼       ▼      ▼                │   │   │
  SchView  PcbView  3DView ──────────┘   │   │
     ▲       ▲      ▲                    │   │
     └───────┴──────┴────────────────────┘   │
                emit selection ─────────────┘
```

- **ProjectLoader** normalizes every input source (zip, folder, individual
  files) into a `ProjectBlob` — a typed filemap plus a detected manifest if
  present. Unknown files are tolerated; known files (`.kicad_pro`,
  `.kicad_sch`, `.kicad_pcb`, `.glb`, `manifest.json`) are indexed.
- **KiCadParser** walks the blob and produces a `Project` object: sheets[],
  components[], nets[], layers[], stackup, bounds. Pure function; no I/O. All
  parsed data lives in memory.
- **ProjectStore** is a Svelte writable holding the current `Project`, plus
  derived stores (e.g., `componentsByRefdes`, `netsByName`).
- **SelectionStore** is the cross-probing backbone. Single writable holding
  `Selection = { kind: 'component'|'net'|'sheet', id: string,
  source: 'sch'|'pcb'|'3d'|'search' }`. Every view subscribes and reacts.
  The `source` field is used to prevent feedback loops: the originating view
  does not re-navigate itself.
- **Views** (`SchematicView`, `PcbView`, `ThreeDView`) are plain Svelte
  components. Each receives the `Project` and the `SelectionStore` as inputs,
  renders to its own canvas/SVG, owns local viewport state (pan, zoom,
  camera). Selection is global; viewport is local.

### Rendering choices

- **Schematic — SVG.** Schematics are line art + text at a fixed logical
  size. SVG gives free DOM-level hit-testing and scales without quality loss.
  `<g data-refdes="U1">` per component; `data-net="VCC"` on wire polylines.
- **PCB — Canvas2D.** Chosen on UX parity with InteractiveHtmlBom (the
  reference UX). Hit-testing via a bounding-box R-tree built once per project
  load. WebGL2 is an optimization path we can take later if profiling
  demands it; v1 API is renderer-agnostic.
- **3D — Three.js.** GLB loaded via GLTFLoader; perspective camera (default)
  + ortho toggle; OrbitControls; raycaster for picks.

## Views

### Schematic

- Full-sheet SVG render with wires, labels, symbols, pins, text.
- Pan: drag / two-finger. Zoom: wheel (cursor-anchored). Buttons: fit, 1:1.
- Hierarchy: sheet symbols rendered as labelled blocks; double-click dives
  in. Breadcrumb overlay in the top-left of the canvas shows the current
  path. `[` / `]` navigate to previous/next sheet.
- Search (opens with `/`): type refdes or net → instant jump + highlight.

### PCB

- Layer draw order (back to front): board outline, substrate tint, plane
  fills, copper zones, tracks, vias, pads, silk, mask, paste, fab,
  courtyard, component reference text, selection overlay.
- Layer colours match KiCad defaults in dark theme and invert appropriately
  in light theme.
- Net labels render above ~2 px/mm zoom; refdes labels render above a lower
  threshold.
- Pours are filled polygons at low detail. Tracks respect real widths.
- Hit-testing via R-tree on footprint bounding boxes; fall-back to
  per-pixel net resolution for click-on-track.
- Controls: drag pan, wheel zoom, `f` for fit.

### 3D

- GLB loaded into scene. Default perspective camera with orbit controls.
- Per-footprint named nodes in the GLB (KiCad 10 output convention) →
  `refdesToMesh` map built at load.
- Click mesh: raycast → selection event (source `3d`).
- External selection (source `sch` or `pcb`): camera animates to centre on
  the target mesh; mesh gets an emissive highlight material.
- Sliders: board opacity, toggle group visibility (board, silk, components).

## Cross-probing contract

Reactions by selection source and consuming view, for `kind: 'component'`:

| Source   | Sch reacts                    | PCB reacts                   | 3D reacts                     |
|----------|-------------------------------|------------------------------|-------------------------------|
| `sch`    | highlight (is source)         | recenter on footprint        | recenter camera on mesh       |
| `pcb`    | navigate to sheet, highlight  | highlight (is source)        | recenter camera on mesh       |
| `3d`     | navigate to sheet, highlight  | recenter on footprint        | highlight (is source)         |
| `search` | navigate, highlight           | recenter                     | recenter                      |

Other selection kinds:

- `kind: 'net'` — PCB highlights all track segments on the net; schematic
  highlights wires/labels with that net; 3D skips (no net semantics).
- `kind: 'sheet'` — schematic navigates to the sheet; PCB and 3D ignore.

3D reactions are disabled when 3D cross-probing is descoped (see "Open
technical risks"): the 3D column above becomes a no-op, but the rest of
the table still holds.

Identity: KiCad UUIDs are canonical. Refdes is the human-facing lookup but
maps to UUID internally. Net name is the canonical net identity.

## UI shell

- **Top bar:** logo + project title + tabs (`Schematic | PCB | 3D | Split ⇄`)
  + actions (Load project, Clear).
- **Left sidebar** (persistent, context-aware):
  - Schematic tab: Sheets tree + Components list (filterable).
  - PCB tab: Layers list with visibility toggles + colour swatches + Nets
    list (filterable).
  - 3D tab: Components list + visibility toggles for board, silk, model
    group.
  - Split tab: controls for the currently-focused pane.
- **Right inspector** (persistent): empty state until selection. Renders a
  typed detail view for Component / Net / Sheet selections.
- **Status bar (bottom):** project path, cursor coords (PCB only), "Built by
  Matthew Austin, 2026" right-aligned.
- **Routes:**
  - `/` — landing page, static, minimal JS (theme toggle only).
  - `/viewer` — SPA entry, lazy-loads heavy dependencies after first paint.
  - `/viewer?demo=<name>` — reserved for future bundled demo projects.

### Keyboard shortcuts

`1` / `2` / `3` / `4` — tabs. `/` — search. `esc` — clear selection. `f` —
fit view. `[` / `]` — previous / next schematic sheet. `l` — focus layers
panel.

### Theming

- Dark is the default for render surfaces; light is the default for chrome
  (top bar, sidebars, inspector). One toggle flips both via
  `data-theme="dark"|"light"` on `<body>`.
- Layer palette follows KiCad defaults in dark theme and is inverted in
  light theme.

## Bundle format

```
project.zip
├── manifest.json        # {name, version, files:{pcb, sch[], glb?}, generated_by}
├── project.kicad_pro
├── project.kicad_pcb
├── project.kicad_sch    # root + sub-sheets as siblings
├── power.kicad_sch
└── project.glb          # optional
```

- Presence of `manifest.json` at the archive root triggers bundle mode and
  gives the loader direct pointers.
- Without `manifest.json`, the loader falls back to heuristics: find the
  `.kicad_pro`, read its referenced files, load siblings.

## Repo layout

```
kicad-tools/
├── kicad-release/            # existing Python tool
├── kicad-viewer/             # new — SvelteKit app
│   ├── src/
│   │   ├── routes/
│   │   │   ├── +layout.svelte
│   │   │   ├── +page.svelte            # landing
│   │   │   └── viewer/
│   │   │       └── +page.svelte        # viewer SPA entry
│   │   ├── lib/
│   │   │   ├── parser/                 # vendored KiCanvas parsers
│   │   │   │   ├── README.md           # pinned SHA, notes on what was stripped
│   │   │   │   └── …
│   │   │   ├── model/                  # Project/Sheet/Component/Net TS types
│   │   │   ├── loader/                 # ProjectLoader
│   │   │   ├── stores/                 # project, selection, theme, recent
│   │   │   ├── views/
│   │   │   │   ├── SchematicView.svelte
│   │   │   │   ├── PcbView.svelte
│   │   │   │   └── ThreeDView.svelte
│   │   │   ├── ui/
│   │   │   │   ├── Shell.svelte
│   │   │   │   ├── SheetTree.svelte
│   │   │   │   ├── LayerPanel.svelte
│   │   │   │   ├── Inspector.svelte
│   │   │   │   └── SplitPane.svelte
│   │   │   └── demo/                   # reserved
│   │   ├── app.css
│   │   └── app.html
│   ├── static/
│   ├── tests/
│   │   ├── fixtures/                   # small public KiCad project + .glb
│   │   ├── unit/
│   │   └── e2e/
│   ├── svelte.config.js
│   ├── vite.config.ts
│   ├── package.json
│   ├── tsconfig.json
│   └── README.md
└── README.md
```

## Testing

- **Unit (Vitest):** parser adapters against small fixture files,
  selection-store reactions (each row of the cross-probing table maps to
  one test), bundle-manifest detection, layer toggle state machine, sheet
  hierarchy tree building.
- **Component (Vitest + `@testing-library/svelte`):** `Inspector` rendering
  per selection kind, `SheetTree` click-to-navigate events, `LayerPanel`
  toggle updates.
- **E2E (Playwright, headed in CI):** two scenarios — drop fixture project,
  verify tabs render and sch→pcb cross-probe works; drop bundle with
  .glb, verify 3D renders and 3d→sch cross-probe works. Record canvas
  screenshots for rough regression.
- **Fixtures:** one small open-source KiCad 10 project (candidate: the
  `pic_programmer` that ships with KiCad demos) plus a .glb generated by
  `kicad-cli pcb export glb`. No proprietary content.
- **Smoke checklist** (`tests/smoke-checklist.md`): "open fixture project in
  each tab, click five things" — run before each deploy.

## Error handling

- Unrecognized or corrupt input → loader throws a named error; UI shows a
  toast with a useful reason. Never silently degrade to a blank viewer.
- Schematic/PCB mismatch (UUID or refdes present in one but not the other)
  → render both; cross-probing a one-sided element shows a subtle "only in
  schematic" / "only in PCB" badge in the inspector.
- Huge boards exceeding render budget → no special handling in v1. Log
  parse/render timing to the console in dev.
- Missing `.glb` → 3D tab shows an empty state with a drop zone for a
  sidecar file.
- KiCad format drift (KiCad 11+): parser throws `UnsupportedFormatError`;
  UI surfaces a version-skew message with a link to the repo.
- IndexedDB unavailable (private-mode browsers, quota exceeded) →
  persistence silently disabled; everything else works.

## Deployment

- Cloudflare Pages project connected to the GitHub repo.
- Build command: `cd kicad-viewer && npm ci && npm run build`.
- Output directory: `kicad-viewer/build`.
- Node version pinned in `.nvmrc`.
- `main` → production. PRs → preview URLs.
- No env vars in v1 (pure client). v2-D would introduce an `R2_BUCKET`
  binding for project sharing.

## Open technical risks

- **KiCad 10 GLB mesh naming.** The 3D cross-probing design assumes
  per-footprint named nodes in the GLB output of `kicad-cli pcb export glb`.
  Verified in the first implementation task. If wrong, either:
  (a) we add a small post-process step that uses the `.kicad_pcb` component
  poses to split the GLB by footprint, or (b) 3D ships as a static view
  without cross-probing. Per scope, (b) is acceptable — 3D cross-probing is
  a stretch goal, not a blocker.
- **Canvas2D performance on very large boards.** Accepted risk. If
  profiling shows unacceptable frame times, we swap the renderer behind the
  same `PcbView` contract (WebGL2 via `regl` or `ogl` as a drop-in).
- **Parser vendoring drift.** KiCanvas is single-maintainer. We pin a
  specific commit SHA and keep the vendored surface small (parsers only, no
  UI). Upstream changes don't reach us automatically; we re-vendor
  deliberately.

## Commit style

Follows the monorepo convention: ≤ 2-line messages, no attribution trailer.
Small, thematic commits per implementation task.
