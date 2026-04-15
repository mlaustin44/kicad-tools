# PCB Active Layer Design

**Status:** Draft → Approved (conversation 2026-04-15)
**Scope:** Introduce an "active layer" concept to the PCB viewer so the user can focus rendering on one copper layer and its associated side, with the rest of the board dimmed and pushed behind.

## Goal

Match the familiar KiCad PCB editor behavior where one copper layer is "on top" and all other layers are visually de-emphasized. This makes probing, net-tracing, and layer-specific review much easier than the current flat, back-to-front stack.

## User-Visible Behavior

1. **Active layer selection.** The left-side Layers panel gains a single-select "active" state. Clicking a layer row makes it active (highlighted accent border/fill). The existing visibility eyeball/checkbox is independent — it toggles whether the layer is drawn at all.
2. **Default active layer.** On load, `F.Cu` is active.
3. **Z-stack reorders.** When the active layer is a copper layer, all sibling layers on the same side (silk, mask, paste, fab, courtyard, adhesive) move up with it, on top of the opposite side's equivalents. Board-wide layers (`Edge.Cuts`, `User.*`, `Dwgs.*`, `Cmts.*`, `Eco*`, `Margin`) stay drawn last, above everything else.
4. **Dimming.** Inactive layers (neither the active copper nor anything on its side) render at reduced opacity (default 0.3). A hidden layer (visibility off) stays hidden — dimming only applies to visible-but-inactive layers.
5. **Labels.** Refdes and silkscreen text render at full opacity for the full active side. Net names and pad numbers render only for the active copper layer; inactive-side pads keep their shapes but drop their text.
6. **Inner copper.** When an inner copper layer is active, it sits at the top of the copper stack. Its "side" (used to pick which silk/mask to promote with it) is inferred from proximity to F.Cu vs B.Cu in the stackup: the half closer to F.Cu counts as front, the other half as back. On a 4-layer board this makes `In1.Cu → front`, `In2.Cu → back`.
7. **Settings modal.** A new Settings button next to the existing Clear button opens a modal with:
   - "Inactive layer opacity" slider, range 0.0–0.8, step 0.05, default 0.3.
   Settings persist to `localStorage` under a single key (`kv.settings.v1`) so future options can share the store.

## Out of Scope (explicitly deferred)

- Click-through / hit-testing restricted to the active side. Selection still works across all layers — flagged for a future pass.
- Keyboard shortcuts for cycling active layer (PageUp/PageDown style). Nice-to-have, not now.
- Independent active layers per side (KiCad has this for pad-swap workflows). Not needed here.
- 3D view integration. Active layer is a 2D-view concept only.

## Architecture

### State

New store `activeLayer` (writable string, default `'F.Cu'`) in `src/lib/stores/layers.ts`. Re-seeded to `'F.Cu'` on project load; if the project has no `F.Cu` (unlikely but possible for flex/single-side boards) fall back to the first copper layer.

New store `settings` (writable object) in `src/lib/stores/settings.ts`:

```ts
interface Settings {
  inactiveLayerOpacity: number; // 0–0.8
}
const DEFAULTS: Settings = { inactiveLayerOpacity: 0.3 };
```

Hydrates from `localStorage['kv.settings.v1']` on module load, writes back on every change (with try/catch around JSON parse and storage write).

### Side classification

Pure function in a new file `src/lib/pcb/layer-side.ts`:

```ts
export type LayerSide = 'front' | 'back' | 'board';

export function classifyLayer(layerId: string, allLayers: LayerInfo[]): LayerSide;
```

Rules:
- Prefix `F.` → `'front'`.
- Prefix `B.` → `'back'`.
- `In{N}.Cu` → determined by `innerCopperSide(layerId, allLayers)` (see below).
- `Edge.Cuts`, `User.*`, `Dwgs.*`, `Cmts.*`, `Eco1.*`, `Eco2.*`, `Margin` → `'board'`.
- Anything else unmatched → `'board'` (safe default; `Edge.Cuts`-like behavior).

`innerCopperSide(layerId, allLayers)` extracts the numeric index N from `In{N}.Cu`, counts total inner copper layers in the project, and returns `'front'` if N is in the first half (rounded up), otherwise `'back'`. This gives `In1 → front`, `In2 → back` on a 4-layer board (2 inner layers), and e.g. `In1,In2 → front`, `In3,In4 → back` on a 6-layer.

### Draw order

Replace the current hard-coded `backLayerIds / inLayerIds / frontLayerIds` sequence in `src/lib/pcb/render.ts` with a computed order based on the active layer's side.

New function in `src/lib/pcb/render.ts`:

```ts
function computeDrawOrder(layers: LayerInfo[], activeLayer: string): LayerInfo[];
```

Output order (each group filtered to layers actually present in the project; all visible+hidden layers included — `drawPcb` still skips hidden ones at draw time):

1. **Inactive-side non-copper**: mask, paste, silk, fab, courtyard, adhesive of the opposite side.
2. **Inactive-side copper** (F.Cu or B.Cu, whichever isn't the active side).
3. **Active-side non-copper** (mask, paste, silk, fab, courtyard, adhesive).
4. **Non-active copper layers** on the active side (for inner-active case: the non-active outer; for outer-active case: inner copper). This keeps less-relevant copper below the focal copper.
5. **Active copper layer**.
6. **Board-wide layers**: `Edge.Cuts` last so the outline always reads.

Within a side the non-copper sub-order is chosen so silk reads on top of mask/paste but below fab annotations and courtyards: `mask → paste → silk → fab → courtyard → adhesive`.

For the outer-active case (F.Cu or B.Cu active), "non-active copper on active side" is just the inner coppers. For the inner-active case, the active copper goes to the top of the copper group and the outer copper on the same side stays below it.

### Dimming

`drawPcb` passes `activeLayer` into `drawLayer`. `drawLayer` sets `ctx.globalAlpha` at the start and restores it at the end:

```ts
const side = classifyLayer(layer.id, allLayers);
const activeSide = classifyLayer(activeLayer, allLayers);
const isActive = side === 'board' || side === activeSide;
ctx.globalAlpha = isActive ? 1.0 : settings.inactiveLayerOpacity;
```

`'board'` layers always render at full opacity (Edge.Cuts etc. are universal). The opacity value is read from the settings store at draw time (or passed in via `drawPcb` signature).

### Labels

`drawCopperLabels` currently iterates all copper layers. Update it to:

- **Refdes / silk text**: draw for every footprint whose reference layer (silk) is on the active side. Footprint has `layer: 'F.Cu' | 'B.Cu'` — use that to pick the side.
- **Net names on tracks/zones, pad numbers, pad net labels**: draw only for geometry on the active copper layer.

No text is drawn for inactive-side footprints or inactive-copper pads/tracks (they still render as geometry under the dimming alpha).

### UI: Layer panel

Update `src/lib/ui/LayerPanel.svelte`:

- Each row becomes clickable (not just the checkbox). Clicking the row sets `activeLayer`. The checkbox click does not propagate.
- Active row gets a visible highlight: left accent border (3px, `var(--kv-accent)`) plus a subtle background tint.
- Keep the existing color swatch and label.
- The default visibility seed stays as-is.

### UI: Settings modal

New component `src/lib/ui/SettingsModal.svelte`. A "Settings" button is added to the toolbar next to the existing Clear button (find the Clear button in `PcbView.svelte` or wherever it lives). Clicking it opens a modal:

- Backdrop closes on click / Escape key.
- Single section "Display" with:
  - Label "Inactive layer opacity"
  - Range input, 0.0–0.8 step 0.05, two-way bound to the settings store
  - Numeric readout next to the slider (e.g., `30%`)

Modal uses the existing design tokens (`--kv-surface`, `--kv-border`, etc.) — no new visual vocabulary.

### Settings store persistence

`src/lib/stores/settings.ts`:

```ts
const STORAGE_KEY = 'kv.settings.v1';

function load(): Settings {
  if (typeof localStorage === 'undefined') return DEFAULTS;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw);
    return { ...DEFAULTS, ...parsed };
  } catch {
    return DEFAULTS;
  }
}

export const settings = writable<Settings>(load());
settings.subscribe((s) => {
  if (typeof localStorage === 'undefined') return;
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(s)); } catch {}
});
```

## Testing

Unit:
- `classifyLayer` covers every KiCad-standard prefix (F, B, In*, Edge, User, Dwgs, Cmts, Eco, Margin).
- `innerCopperSide` gives expected front/back split for 2-, 4-, 6-, 8-layer projects.
- `computeDrawOrder` produces the expected ID sequence for: `F.Cu` active, `B.Cu` active, `In1.Cu` active on a 4-layer project.

Visual / manual:
- Loading the `ohm_lamp_v2_usb_r3` project shows F.Cu active by default, B.* layers dimmed.
- Clicking B.Cu in the layer list flips the stack — B silk/mask/etc. are now on top and visible, F side is dimmed.
- Inactive-side footprint refdes text disappears; active-side text stays.
- Net names only render on the active copper.
- Settings modal opens, slider updates dimming in real time, value persists across reload.

## Rollout

Single branch, single PR. No migration concerns (new state, new storage key). Default behavior matches user expectation (F.Cu active, 0.3 dim) so no opt-in needed.
