# PCB Active Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "active layer" concept to the PCB viewer so one copper layer (and its side's silk/mask/paste/fab/courtyard) renders on top while the rest dims to a user-configurable opacity.

**Architecture:** A new `activeLayer` store drives layer z-ordering (computed per-draw from the active layer's side), per-layer dimming (via `globalAlpha` in `drawLayer`), and label gating (refdes follows active side; net/pad labels follow active copper). A small `settings` store persists the dim opacity to `localStorage`. UI changes are surgical: `LayerPanel` rows become clickable (active = highlighted), a Settings button in `Shell` opens a modal with an opacity slider.

**Tech Stack:** SvelteKit 2, Svelte 5 runes, TypeScript, Vitest (jsdom), Canvas 2D.

**Spec:** `docs/superpowers/specs/2026-04-15-pcb-active-layer-design.md`

---

## File Structure

**New files:**
- `src/lib/pcb/layer-side.ts` — `classifyLayer`, `innerCopperSide` pure helpers
- `src/lib/pcb/draw-order.ts` — `computeDrawOrder` pure helper
- `src/lib/stores/settings.ts` — `settings` writable store with localStorage persistence
- `src/lib/ui/SettingsModal.svelte` — modal with opacity slider
- `tests/unit/layer-side.test.ts`
- `tests/unit/draw-order.test.ts`
- `tests/unit/settings-store.test.ts`

**Modified files:**
- `src/lib/stores/layers.ts` — add `activeLayer` writable, re-seed on project change
- `src/lib/pcb/render.ts` — replace hardcoded draw order with `computeDrawOrder`; apply dimming in `drawLayer`; gate labels by active side/copper; extend `drawPcb` signature to accept `activeLayer` and `inactiveOpacity`
- `src/lib/views/PcbView.svelte` — pass `activeLayer` + `settings.inactiveLayerOpacity` into `drawPcb`; redraw on either change
- `src/lib/ui/LayerPanel.svelte` — row click sets active layer; active row highlighted
- `src/lib/ui/Shell.svelte` — add Settings button and mount `SettingsModal`

---

## Task 1: Layer side classification

Pure helpers: every KiCad layer id resolves to `'front' | 'back' | 'board'`. Inner copper (`In{N}.Cu`) routes based on position in the stackup.

**Files:**
- Create: `src/lib/pcb/layer-side.ts`
- Test: `tests/unit/layer-side.test.ts`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/layer-side.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { classifyLayer, innerCopperSide } from '$lib/pcb/layer-side';
import type { LayerInfo } from '$lib/model/project';

function mkLayers(ids: string[]): LayerInfo[] {
  return ids.map((id) => ({
    id,
    name: id,
    type: id.endsWith('.Cu') ? (id === 'F.Cu' || id === 'B.Cu' ? id : 'In.Cu') : 'Other',
    defaultColor: '#888'
  })) as LayerInfo[];
}

describe('classifyLayer', () => {
  const twoLayer = mkLayers(['F.Cu', 'B.Cu', 'F.SilkS', 'B.SilkS', 'Edge.Cuts']);

  it('classifies F.* as front', () => {
    expect(classifyLayer('F.Cu', twoLayer)).toBe('front');
    expect(classifyLayer('F.SilkS', twoLayer)).toBe('front');
    expect(classifyLayer('F.Mask', twoLayer)).toBe('front');
    expect(classifyLayer('F.Paste', twoLayer)).toBe('front');
    expect(classifyLayer('F.Fab', twoLayer)).toBe('front');
    expect(classifyLayer('F.CrtYd', twoLayer)).toBe('front');
    expect(classifyLayer('F.Adhesive', twoLayer)).toBe('front');
  });

  it('classifies B.* as back', () => {
    expect(classifyLayer('B.Cu', twoLayer)).toBe('back');
    expect(classifyLayer('B.SilkS', twoLayer)).toBe('back');
  });

  it('classifies board-wide layers as board', () => {
    expect(classifyLayer('Edge.Cuts', twoLayer)).toBe('board');
    expect(classifyLayer('User.1', twoLayer)).toBe('board');
    expect(classifyLayer('Dwgs.User', twoLayer)).toBe('board');
    expect(classifyLayer('Cmts.User', twoLayer)).toBe('board');
    expect(classifyLayer('Eco1.User', twoLayer)).toBe('board');
    expect(classifyLayer('Eco2.User', twoLayer)).toBe('board');
    expect(classifyLayer('Margin', twoLayer)).toBe('board');
  });

  it('falls back to board for unknown ids', () => {
    expect(classifyLayer('Weird.Custom', twoLayer)).toBe('board');
  });

  it('classifies inner copper by stackup half', () => {
    const four = mkLayers(['F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu']);
    expect(classifyLayer('In1.Cu', four)).toBe('front');
    expect(classifyLayer('In2.Cu', four)).toBe('back');

    const six = mkLayers(['F.Cu', 'In1.Cu', 'In2.Cu', 'In3.Cu', 'In4.Cu', 'B.Cu']);
    expect(classifyLayer('In1.Cu', six)).toBe('front');
    expect(classifyLayer('In2.Cu', six)).toBe('front');
    expect(classifyLayer('In3.Cu', six)).toBe('back');
    expect(classifyLayer('In4.Cu', six)).toBe('back');
  });
});

describe('innerCopperSide', () => {
  it('rounds up when inner count is odd', () => {
    const five = [
      { id: 'F.Cu', type: 'F.Cu' },
      { id: 'In1.Cu', type: 'In.Cu' },
      { id: 'In2.Cu', type: 'In.Cu' },
      { id: 'In3.Cu', type: 'In.Cu' },
      { id: 'B.Cu', type: 'B.Cu' }
    ] as LayerInfo[];
    expect(innerCopperSide('In1.Cu', five)).toBe('front');
    expect(innerCopperSide('In2.Cu', five)).toBe('front');
    expect(innerCopperSide('In3.Cu', five)).toBe('back');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer && npx vitest run tests/unit/layer-side.test.ts`
Expected: FAIL with "Cannot find module '$lib/pcb/layer-side'" (or similar).

- [ ] **Step 3: Implement the module**

Create `src/lib/pcb/layer-side.ts`:

```ts
import type { LayerInfo } from '$lib/model/project';

export type LayerSide = 'front' | 'back' | 'board';

const BOARD_PREFIXES = ['Edge.', 'User.', 'Dwgs.', 'Cmts.', 'Eco1.', 'Eco2.'];
const BOARD_EXACT = new Set(['Margin']);

export function classifyLayer(layerId: string, allLayers: LayerInfo[]): LayerSide {
  if (layerId === 'F.Cu' || layerId.startsWith('F.')) return 'front';
  if (layerId === 'B.Cu' || layerId.startsWith('B.')) return 'back';
  if (BOARD_EXACT.has(layerId)) return 'board';
  for (const p of BOARD_PREFIXES) if (layerId.startsWith(p)) return 'board';
  if (/^In\d+\.Cu$/.test(layerId)) return innerCopperSide(layerId, allLayers);
  return 'board';
}

export function innerCopperSide(layerId: string, allLayers: LayerInfo[]): LayerSide {
  const match = /^In(\d+)\.Cu$/.exec(layerId);
  if (!match) return 'board';
  const n = Number(match[1]);
  const inners = allLayers
    .filter((l) => /^In\d+\.Cu$/.test(l.id))
    .map((l) => Number(/^In(\d+)\.Cu$/.exec(l.id)![1]))
    .sort((a, b) => a - b);
  if (inners.length === 0) return 'front';
  const halfCutoff = Math.ceil(inners.length / 2);
  const idxOneBased = inners.indexOf(n) + 1;
  return idxOneBased <= halfCutoff ? 'front' : 'back';
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer && npx vitest run tests/unit/layer-side.test.ts`
Expected: PASS, all cases green.

- [ ] **Step 5: Commit**

```bash
cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer
git add src/lib/pcb/layer-side.ts tests/unit/layer-side.test.ts
git commit -m "pcb: add layer-side classifier for front/back/board grouping"
```

---

## Task 2: Active layer store

Writable store holding the current active layer id. Seeded to `F.Cu` (or first copper layer) on project load.

**Files:**
- Modify: `src/lib/stores/layers.ts`
- Test: `tests/unit/layer-side.test.ts` (extend) — alternatively a new `tests/unit/active-layer.test.ts`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/active-layer.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { project } from '$lib/stores/project';
import { activeLayer } from '$lib/stores/layers';
import type { Project } from '$lib/model/project';

function fakeProject(layerIds: string[]): Project {
  return {
    name: 'fake',
    sheets: [],
    components: [],
    nets: [],
    pcb: {
      layers: layerIds.map((id) => ({
        id,
        name: id,
        type: id.endsWith('.Cu') && id !== 'F.Cu' && id !== 'B.Cu' ? 'In.Cu' : id,
        defaultColor: '#888'
      })) as any,
      footprints: [],
      tracks: [],
      vias: [],
      zones: [],
      graphics: [],
      boundsMm: { x: 0, y: 0, w: 1, h: 1 }
    }
  } as Project;
}

describe('activeLayer store', () => {
  beforeEach(() => project.set(null));

  it('is F.Cu when project has F.Cu', () => {
    project.set(fakeProject(['F.Cu', 'B.Cu']));
    expect(get(activeLayer)).toBe('F.Cu');
  });

  it('falls back to first copper when no F.Cu', () => {
    project.set(fakeProject(['B.Cu']));
    expect(get(activeLayer)).toBe('B.Cu');
  });

  it('can be set manually', () => {
    project.set(fakeProject(['F.Cu', 'B.Cu']));
    activeLayer.set('B.Cu');
    expect(get(activeLayer)).toBe('B.Cu');
  });

  it('resets to F.Cu on new project load', () => {
    project.set(fakeProject(['F.Cu', 'B.Cu']));
    activeLayer.set('B.Cu');
    project.set(fakeProject(['F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu']));
    expect(get(activeLayer)).toBe('F.Cu');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer && npx vitest run tests/unit/active-layer.test.ts`
Expected: FAIL (activeLayer not exported).

- [ ] **Step 3: Extend the layers store**

Edit `src/lib/stores/layers.ts` to add the `activeLayer` export. Full replacement:

```ts
import { writable, derived } from 'svelte/store';
import { project } from '$lib/stores/project';

export const layerVisibility = writable<Map<string, boolean>>(new Map());
export const activeLayer = writable<string>('F.Cu');

// Seed visibility and active layer each time project changes.
project.subscribe((p) => {
  if (!p) {
    layerVisibility.set(new Map());
    activeLayer.set('F.Cu');
    return;
  }
  const m = new Map<string, boolean>();
  for (const l of p.pcb.layers) {
    const on = ['F.Cu', 'B.Cu', 'In.Cu', 'F.SilkS', 'B.SilkS', 'F.Mask', 'B.Mask', 'Edge.Cuts'].includes(l.type);
    m.set(l.id, on);
  }
  layerVisibility.set(m);

  const hasFCu = p.pcb.layers.some((l) => l.id === 'F.Cu');
  if (hasFCu) {
    activeLayer.set('F.Cu');
  } else {
    const firstCu = p.pcb.layers.find((l) => l.id.endsWith('.Cu'));
    activeLayer.set(firstCu?.id ?? 'F.Cu');
  }
});

export const layers = derived(project, (p) => p?.pcb.layers ?? []);

export function toggleLayer(id: string) {
  layerVisibility.update((m) => {
    const next = new Map(m);
    next.set(id, !next.get(id));
    return next;
  });
}

export function setActiveLayer(id: string) {
  activeLayer.set(id);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer && npx vitest run tests/unit/active-layer.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer
git add src/lib/stores/layers.ts tests/unit/active-layer.test.ts
git commit -m "pcb: add activeLayer store, default F.Cu"
```

---

## Task 3: Settings store

Writable store for viewer settings; persists to `localStorage['kv.settings.v1']`.

**Files:**
- Create: `src/lib/stores/settings.ts`
- Test: `tests/unit/settings-store.test.ts`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/settings-store.test.ts`:

```ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { get } from 'svelte/store';

const STORAGE_KEY = 'kv.settings.v1';

async function loadFreshModule() {
  vi.resetModules();
  return import('$lib/stores/settings');
}

describe('settings store', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('defaults to inactiveLayerOpacity 0.3 when no stored value', async () => {
    const mod = await loadFreshModule();
    expect(get(mod.settings).inactiveLayerOpacity).toBe(0.3);
  });

  it('persists changes to localStorage', async () => {
    const mod = await loadFreshModule();
    mod.settings.update((s) => ({ ...s, inactiveLayerOpacity: 0.5 }));
    const raw = localStorage.getItem(STORAGE_KEY);
    expect(raw).toBeTruthy();
    expect(JSON.parse(raw!).inactiveLayerOpacity).toBe(0.5);
  });

  it('hydrates from localStorage on load', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ inactiveLayerOpacity: 0.7 }));
    const mod = await loadFreshModule();
    expect(get(mod.settings).inactiveLayerOpacity).toBe(0.7);
  });

  it('merges stored partial settings with defaults', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({}));
    const mod = await loadFreshModule();
    expect(get(mod.settings).inactiveLayerOpacity).toBe(0.3);
  });

  it('falls back to defaults on invalid JSON', async () => {
    localStorage.setItem(STORAGE_KEY, '{not-json');
    const mod = await loadFreshModule();
    expect(get(mod.settings).inactiveLayerOpacity).toBe(0.3);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer && npx vitest run tests/unit/settings-store.test.ts`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the store**

Create `src/lib/stores/settings.ts`:

```ts
import { writable } from 'svelte/store';

export interface Settings {
  inactiveLayerOpacity: number;
}

const DEFAULTS: Settings = { inactiveLayerOpacity: 0.3 };
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
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    // Storage quota / disabled — silently ignore.
  }
});
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer && npx vitest run tests/unit/settings-store.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer
git add src/lib/stores/settings.ts tests/unit/settings-store.test.ts
git commit -m "settings: add persistent store with inactiveLayerOpacity"
```

---

## Task 4: Draw order computation

Pure function that takes the full layer list and the active layer id, returns layers in bottom-to-top draw order.

**Files:**
- Create: `src/lib/pcb/draw-order.ts`
- Test: `tests/unit/draw-order.test.ts`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/draw-order.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { computeDrawOrder } from '$lib/pcb/draw-order';
import type { LayerInfo } from '$lib/model/project';

function L(id: string, type: string = id): LayerInfo {
  return { id, name: id, type, defaultColor: '#888' } as LayerInfo;
}

const fourLayer: LayerInfo[] = [
  L('F.Cu'),
  L('In1.Cu', 'In.Cu'),
  L('In2.Cu', 'In.Cu'),
  L('B.Cu'),
  L('F.SilkS'),
  L('B.SilkS'),
  L('F.Mask'),
  L('B.Mask'),
  L('F.Paste'),
  L('B.Paste'),
  L('F.Fab'),
  L('B.Fab'),
  L('F.CrtYd'),
  L('B.CrtYd'),
  L('Edge.Cuts')
];

function idsOf(layers: LayerInfo[]): string[] {
  return layers.map((l) => l.id);
}

describe('computeDrawOrder (F.Cu active)', () => {
  it('puts back-side non-copper first, front-side copper last, edge last of all', () => {
    const order = idsOf(computeDrawOrder(fourLayer, 'F.Cu'));
    // Last layer is always Edge.Cuts
    expect(order[order.length - 1]).toBe('Edge.Cuts');
    // Active copper (F.Cu) appears right before Edge.Cuts (inner coppers and
    // opposite copper come before it).
    const fCuIdx = order.indexOf('F.Cu');
    const edgeIdx = order.indexOf('Edge.Cuts');
    expect(fCuIdx).toBe(edgeIdx - 1);
    // All B.* non-copper come before all F.* non-copper
    const bSilkIdx = order.indexOf('B.SilkS');
    const fSilkIdx = order.indexOf('F.SilkS');
    expect(bSilkIdx).toBeLessThan(fSilkIdx);
    // B.Cu comes before F.Cu
    expect(order.indexOf('B.Cu')).toBeLessThan(fCuIdx);
  });
});

describe('computeDrawOrder (B.Cu active)', () => {
  it('puts front-side non-copper first, back-side copper last', () => {
    const order = idsOf(computeDrawOrder(fourLayer, 'B.Cu'));
    expect(order[order.length - 1]).toBe('Edge.Cuts');
    const bCuIdx = order.indexOf('B.Cu');
    expect(bCuIdx).toBe(order.indexOf('Edge.Cuts') - 1);
    expect(order.indexOf('F.SilkS')).toBeLessThan(order.indexOf('B.SilkS'));
    expect(order.indexOf('F.Cu')).toBeLessThan(bCuIdx);
  });
});

describe('computeDrawOrder (In1.Cu active on 4-layer)', () => {
  it('treats In1 as front side and draws it on top of copper group', () => {
    const order = idsOf(computeDrawOrder(fourLayer, 'In1.Cu'));
    // Active copper is In1.Cu; it sits right before Edge.Cuts.
    expect(order[order.length - 1]).toBe('Edge.Cuts');
    expect(order[order.length - 2]).toBe('In1.Cu');
    // Front-side non-copper comes after back-side non-copper (In1 is front)
    expect(order.indexOf('B.SilkS')).toBeLessThan(order.indexOf('F.SilkS'));
    // F.Cu (same-side copper that is not active) is below the active In1.Cu
    expect(order.indexOf('F.Cu')).toBeLessThan(order.indexOf('In1.Cu'));
    // B.Cu (opposite side copper) is below front-side copper group
    expect(order.indexOf('B.Cu')).toBeLessThan(order.indexOf('F.Cu'));
  });
});

describe('computeDrawOrder (missing layers)', () => {
  it('ignores layers not in the list', () => {
    const twoLayer: LayerInfo[] = [L('F.Cu'), L('B.Cu'), L('Edge.Cuts')];
    const order = idsOf(computeDrawOrder(twoLayer, 'F.Cu'));
    expect(order).toEqual(['B.Cu', 'F.Cu', 'Edge.Cuts']);
  });

  it('is stable when active layer is not in list', () => {
    const twoLayer: LayerInfo[] = [L('F.Cu'), L('B.Cu'), L('Edge.Cuts')];
    // Should not throw; just falls through with F.Cu semantics.
    const order = idsOf(computeDrawOrder(twoLayer, 'In1.Cu'));
    expect(order[order.length - 1]).toBe('Edge.Cuts');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer && npx vitest run tests/unit/draw-order.test.ts`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the module**

Create `src/lib/pcb/draw-order.ts`:

```ts
import type { LayerInfo } from '$lib/model/project';
import { classifyLayer, type LayerSide } from './layer-side';

// Non-copper layer kinds in the order they should stack within a side,
// bottom-to-top. Mask sits below the copper so copper shows through the
// soldermask opening; silk and fab annotations sit above so they read.
const NONCOPPER_ORDER = [
  'Mask',
  'Paste',
  'SilkS',
  'Fab',
  'CrtYd',
  'Adhesive',
  'Adhes'
] as const;

function nonCopperIdsForSide(layers: LayerInfo[], side: 'front' | 'back'): string[] {
  const prefix = side === 'front' ? 'F.' : 'B.';
  const ids: string[] = [];
  for (const kind of NONCOPPER_ORDER) {
    const id = prefix + kind;
    if (layers.some((l) => l.id === id)) ids.push(id);
  }
  return ids;
}

function copperIds(layers: LayerInfo[]): string[] {
  return layers.filter((l) => l.id.endsWith('.Cu')).map((l) => l.id);
}

/**
 * Returns layers in bottom-to-top draw order, given the active layer id.
 *
 * Order:
 *   1. Inactive-side non-copper (mask, paste, silk, fab, crtyd, adhesive)
 *   2. Inactive-side copper (F.Cu or B.Cu — whichever isn't the active side)
 *   3. Active-side non-copper
 *   4. Non-active copper on the active side (for inner-active: the outer copper
 *      on the same side; for outer-active: the inner coppers on that side)
 *   5. Active copper layer
 *   6. Board-wide layers (Edge.Cuts, User.*, etc.) — Edge.Cuts last
 */
export function computeDrawOrder(layers: LayerInfo[], activeLayerId: string): LayerInfo[] {
  const byId = new Map(layers.map((l) => [l.id, l]));
  const activeSide: LayerSide = (() => {
    const s = classifyLayer(activeLayerId, layers);
    return s === 'board' ? 'front' : s; // fallback if active isn't present
  })();
  const inactiveSide: 'front' | 'back' = activeSide === 'front' ? 'back' : 'front';

  const result: string[] = [];
  const push = (id: string) => {
    if (byId.has(id) && !result.includes(id)) result.push(id);
  };

  // 1. Inactive-side non-copper
  for (const id of nonCopperIdsForSide(layers, inactiveSide)) push(id);

  // 2. Inactive-side copper: the outer (F.Cu or B.Cu) plus any inner copper on that side.
  const allCu = copperIds(layers);
  const inactiveOuterCu = inactiveSide === 'front' ? 'F.Cu' : 'B.Cu';
  push(inactiveOuterCu);
  for (const id of allCu) {
    if (id === 'F.Cu' || id === 'B.Cu') continue;
    if (classifyLayer(id, layers) === inactiveSide) push(id);
  }

  // 3. Active-side non-copper
  for (const id of nonCopperIdsForSide(layers, activeSide)) push(id);

  // 4. Non-active copper on the active side (below the focal copper).
  const activeOuterCu = activeSide === 'front' ? 'F.Cu' : 'B.Cu';
  if (activeOuterCu !== activeLayerId) push(activeOuterCu);
  for (const id of allCu) {
    if (id === 'F.Cu' || id === 'B.Cu' || id === activeLayerId) continue;
    if (classifyLayer(id, layers) === activeSide) push(id);
  }

  // 5. Active copper
  push(activeLayerId);

  // 6. Board-wide: everything classified as 'board'. Edge.Cuts always last.
  const boardIds = layers
    .filter((l) => classifyLayer(l.id, layers) === 'board')
    .map((l) => l.id);
  for (const id of boardIds) {
    if (id !== 'Edge.Cuts') push(id);
  }
  push('Edge.Cuts');

  return result.map((id) => byId.get(id)!).filter(Boolean);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer && npx vitest run tests/unit/draw-order.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer
git add src/lib/pcb/draw-order.ts tests/unit/draw-order.test.ts
git commit -m "pcb: add computeDrawOrder for side-based z-stack"
```

---

## Task 5: Wire draw order and dimming into render

Replace the hardcoded back/in/front loops with `computeDrawOrder`. Apply inactive-layer dimming via `globalAlpha` in `drawLayer`.

**Files:**
- Modify: `src/lib/pcb/render.ts` (drawPcb signature; drawLayer alpha)
- Modify: `src/lib/views/PcbView.svelte` (pass activeLayer + opacity)

- [ ] **Step 1: Update drawPcb signature**

In `src/lib/pcb/render.ts`, at the top, add the import:

```ts
import { computeDrawOrder } from './draw-order';
import { classifyLayer } from './layer-side';
```

Change the `drawPcb` signature and body header. Replace:

```ts
export function drawPcb(
  ctx: CanvasRenderingContext2D,
  scene: PcbScene,
  layers: LayerInfo[],
  visible: Map<string, boolean>,
  viewport: Viewport,
  selectedFootprint?: string | null,
  highlightedNet?: string | null
): void {
```

with:

```ts
export function drawPcb(
  ctx: CanvasRenderingContext2D,
  scene: PcbScene,
  layers: LayerInfo[],
  visible: Map<string, boolean>,
  viewport: Viewport,
  activeLayer: string,
  inactiveOpacity: number,
  selectedFootprint?: string | null,
  highlightedNet?: string | null
): void {
```

- [ ] **Step 2: Replace the hardcoded layer loops**

Inside `drawPcb`, find this block (around current lines 30–50):

```ts
// Draw order: back-to-front — back layers first, inner, then front layers on top.
// Edge cuts are drawn on top so the outline always reads.
const backLayerIds = ['B.Cu', 'B.SilkS', 'B.Mask', 'B.Fab', 'B.CrtYd', 'B.Paste'];
const inLayerIds = layers.filter((l) => l.type === 'In.Cu').map((l) => l.id);
const frontLayerIds = ['F.Cu', 'F.SilkS', 'F.Mask', 'F.Fab', 'F.CrtYd', 'F.Paste'];

const drawByIds = (ids: string[]) => {
  for (const id of ids) {
    const l = layers.find((x) => x.id === id);
    if (!l || !visible.get(l.id)) continue;
    drawLayer(ctx, scene, l);
  }
};

drawByIds(backLayerIds);
drawByIds(inLayerIds);
drawByIds(frontLayerIds);

// Edge cuts on top (outline always visible)
const edge = layers.find((l) => l.id === 'Edge.Cuts');
if (edge && visible.get(edge.id)) drawLayer(ctx, scene, edge);
```

Replace with:

```ts
// Bottom-to-top draw order computed from the active layer's side.
const activeSide = classifyLayer(activeLayer, layers);
const ordered = computeDrawOrder(layers, activeLayer);
for (const l of ordered) {
  if (!visible.get(l.id)) continue;
  const side = classifyLayer(l.id, layers);
  const isActive = side === 'board' || side === activeSide;
  drawLayer(ctx, scene, l, isActive ? 1.0 : inactiveOpacity);
}
```

- [ ] **Step 3: Update drawLayer to accept opacity**

Change the `drawLayer` signature:

```ts
function drawLayer(ctx: CanvasRenderingContext2D, scene: PcbScene, layer: LayerInfo): void {
```

to:

```ts
function drawLayer(
  ctx: CanvasRenderingContext2D,
  scene: PcbScene,
  layer: LayerInfo,
  baseOpacity: number = 1.0
): void {
  const prevAlpha = ctx.globalAlpha;
  ctx.globalAlpha = baseOpacity;
```

Find the existing `ctx.globalAlpha = 0.5;` used for zones inside `drawLayer` (current line ~621); replace it and its paired `ctx.globalAlpha = 1;` so zone fills respect the base opacity:

```ts
// Zones (filled polygons, semi-transparent)
for (const z of buckets.zones) {
  if (z.polygon.length < 2) continue;
  ctx.globalAlpha = baseOpacity * 0.5;
  ctx.beginPath();
  const p0 = z.polygon[0]!;
  ctx.moveTo(p0.x, p0.y);
  for (let i = 1; i < z.polygon.length; i++) {
    const pt = z.polygon[i]!;
    ctx.lineTo(pt.x, pt.y);
  }
  ctx.closePath();
  ctx.fill();
  ctx.globalAlpha = baseOpacity;
}
```

At the end of the function, restore the previous alpha:

```ts
  // …existing footprint graphics loop…
  ctx.globalAlpha = prevAlpha;
}
```

- [ ] **Step 4: Wire activeLayer + settings into PcbView**

Edit `src/lib/views/PcbView.svelte`. Near the top, alongside existing store imports, add:

```ts
  import { layerVisibility, layers, activeLayer } from '$lib/stores/layers';
  import { settings } from '$lib/stores/settings';
```

Update the `redraw()` call to include the new params. Replace:

```ts
    drawPcb(ctx, scene, $layers, $layerVisibility, viewport, selFpUuid, highlightedNet);
```

with:

```ts
    drawPcb(
      ctx,
      scene,
      $layers,
      $layerVisibility,
      viewport,
      $activeLayer,
      $settings.inactiveLayerOpacity,
      selFpUuid,
      highlightedNet
    );
```

The existing Svelte effect that redraws on store changes will pick up `activeLayer` and `settings` automatically via auto-subscription.

- [ ] **Step 5: Type-check and run tests**

Run: `cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer && npm run check && npx vitest run`
Expected: No type errors, all existing tests still pass.

- [ ] **Step 6: Manual verification**

Run `npm run dev`, load the `ohm_lamp_v2_usb_r3` project (path: `/home/mlaustin/electronics/ohm_kicad_designs/ohm_lamp_v2_usb_r3/`), switch to PCB tab.
Expected: F.Cu and its side render at full opacity; B.Cu and B-side layers render dimmed at ~30%.

- [ ] **Step 7: Commit**

```bash
cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer
git add src/lib/pcb/render.ts src/lib/views/PcbView.svelte
git commit -m "pcb: apply active-layer z-order and dim inactive layers"
```

---

## Task 6: Gate labels by active side and active copper

Refdes text renders for footprints on the active side only. Net names (tracks, zones), pad numbers, and pad net text render for the active copper layer only.

**Files:**
- Modify: `src/lib/pcb/render.ts`

- [ ] **Step 1: Update the refdes label loop**

In `drawPcb`, find the refdes block (currently around line 110):

```ts
  if (refdesHeightMm * pxPerMm >= 7) {
    ctx.save();
    ctx.fillStyle = '#c8c8c8';
    ctx.font = `${refdesHeightMm}px ui-sans-serif, system-ui, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (const fp of scene.footprints) {
      ctx.fillText(fp.refdes, fp.position.x, fp.position.y);
    }
    ctx.restore();
  }
```

Replace with:

```ts
  if (refdesHeightMm * pxPerMm >= 7) {
    const activeSideForRefdes = activeSide === 'back' ? 'bottom' : 'top';
    ctx.save();
    ctx.fillStyle = '#c8c8c8';
    ctx.font = `${refdesHeightMm}px ui-sans-serif, system-ui, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (const fp of scene.footprints) {
      if (fp.side !== activeSideForRefdes) continue;
      ctx.fillText(fp.refdes, fp.position.x, fp.position.y);
    }
    ctx.restore();
  }
```

(`activeSide` is already computed earlier in `drawPcb` in Task 5.)

- [ ] **Step 2: Restrict drawCopperLabels to the active copper layer**

Update `drawCopperLabels` signature. Change:

```ts
function drawCopperLabels(
  ctx: CanvasRenderingContext2D,
  scene: PcbScene,
  layers: LayerInfo[],
  visible: Map<string, boolean>,
  pxPerMm: number
): void {
  const copperIds: string[] = [
    'F.Cu',
    ...layers.filter((l) => l.type === 'In.Cu').map((l) => l.id),
    'B.Cu'
  ];
```

to:

```ts
function drawCopperLabels(
  ctx: CanvasRenderingContext2D,
  scene: PcbScene,
  layers: LayerInfo[],
  visible: Map<string, boolean>,
  pxPerMm: number,
  activeLayer: string
): void {
  const copperIds: string[] = [activeLayer];
```

(Only the active copper gets labeled — no more iterating all copper layers.)

Update the call site inside `drawPcb`. Change:

```ts
  drawCopperLabels(ctx, scene, layers, visible, pxPerMm);
```

to:

```ts
  drawCopperLabels(ctx, scene, layers, visible, pxPerMm, activeLayer);
```

- [ ] **Step 3: Manual verification**

Run: `cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer && npm run check && npx vitest run`
Expected: Types pass; existing tests pass.

Run `npm run dev` and load the PCB:
- With F.Cu active: all refdes on top side; net names only on F.Cu tracks; bottom-side footprints have no text labels.
- Click B.Cu in layer panel (once Task 7 is done — for now, temporarily change the default to 'B.Cu' or set via the browser console: in DevTools `import('$lib/stores/layers').then(m => m.setActiveLayer('B.Cu'))`).

Since Task 7 adds the UI, a quick sanity check here is to flip the default to `B.Cu` in `src/lib/stores/layers.ts` temporarily (revert before committing) and confirm labels move to the B side. This is optional — the behavior is also testable after Task 7.

- [ ] **Step 4: Commit**

```bash
cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer
git add src/lib/pcb/render.ts
git commit -m "pcb: gate refdes to active side, net labels to active copper"
```

---

## Task 7: Layer panel active selection + highlight

Clicking a row sets active layer; clicking the checkbox still toggles visibility without changing active layer. Active row gets an accent border and tinted background.

**Files:**
- Modify: `src/lib/ui/LayerPanel.svelte`

- [ ] **Step 1: Replace LayerPanel with active-aware version**

Full replacement of `src/lib/ui/LayerPanel.svelte`:

```svelte
<script lang="ts">
  import { layers, layerVisibility, toggleLayer, activeLayer, setActiveLayer } from '$lib/stores/layers';
</script>

<div class="wrap" id="layer-panel">
  <h4>Layers</h4>
  {#each $layers as l (l.id)}
    <div
      class="row"
      class:active={$activeLayer === l.id}
      role="button"
      tabindex="0"
      onclick={() => setActiveLayer(l.id)}
      onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setActiveLayer(l.id); } }}
    >
      <input
        type="checkbox"
        checked={$layerVisibility.get(l.id) ?? false}
        onchange={() => toggleLayer(l.id)}
        onclick={(e) => e.stopPropagation()}
        aria-label={`Toggle ${l.name} visibility`}
      />
      <span class="sw" style="background: {l.defaultColor}"></span>
      <span class="name">{l.name}</span>
    </div>
  {/each}
</div>

<style>
  .wrap { font-size: 0.78rem; }
  h4 {
    font-size: 0.7rem; letter-spacing: 0.08em; color: var(--kv-text-dim);
    margin: 0.5rem 0.75rem; text-transform: uppercase;
  }
  .row {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 3px 10px; cursor: pointer; user-select: none;
    border-left: 3px solid transparent;
  }
  .row:hover { background: var(--kv-surface-2); }
  .row.active {
    background: var(--kv-surface-2);
    border-left-color: var(--kv-accent, #6aa6ff);
  }
  .row.active .name { color: var(--kv-accent, #6aa6ff); font-weight: 600; }
  .sw { width: 10px; height: 10px; border-radius: 2px; border: 1px solid var(--kv-border); }
  .name { flex: 1; }
</style>
```

- [ ] **Step 2: Type-check**

Run: `cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer && npm run check`
Expected: No type errors.

- [ ] **Step 3: Manual verification**

Run `npm run dev`, load project, switch to PCB tab.
Expected:
- F.Cu row is highlighted by default (accent border + bold text).
- Clicking another layer row moves the highlight and re-renders the PCB with that layer active.
- Clicking the checkbox toggles visibility without changing the active layer.

- [ ] **Step 4: Commit**

```bash
cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer
git add src/lib/ui/LayerPanel.svelte
git commit -m "ui: layer panel active-layer selection with highlight"
```

---

## Task 8: Settings modal + toolbar button

Add a Settings button next to Clear in `Shell.svelte`; open a modal with an inactive-layer-opacity slider.

**Files:**
- Create: `src/lib/ui/SettingsModal.svelte`
- Modify: `src/lib/ui/Shell.svelte`

- [ ] **Step 1: Create the modal component**

Create `src/lib/ui/SettingsModal.svelte`:

```svelte
<script lang="ts">
  import { settings } from '$lib/stores/settings';

  interface Props {
    open: boolean;
    onClose: () => void;
  }
  let { open, onClose }: Props = $props();

  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') onClose();
  }

  function onOpacityInput(e: Event) {
    const v = Number((e.target as HTMLInputElement).value);
    settings.update((s) => ({ ...s, inactiveLayerOpacity: v }));
  }
</script>

<svelte:window onkeydown={onKeydown} />

{#if open}
  <div class="backdrop" onclick={onClose} role="presentation">
    <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-label="Settings">
      <header>
        <h3>Settings</h3>
        <button class="close" onclick={onClose} aria-label="Close settings">✕</button>
      </header>

      <section>
        <h4>Display</h4>
        <label class="field">
          <span class="label-text">Inactive layer opacity</span>
          <input
            type="range"
            min="0"
            max="0.8"
            step="0.05"
            value={$settings.inactiveLayerOpacity}
            oninput={onOpacityInput}
          />
          <span class="value">{Math.round($settings.inactiveLayerOpacity * 100)}%</span>
        </label>
      </section>
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed; inset: 0; background: rgba(0, 0, 0, 0.5);
    display: flex; align-items: center; justify-content: center;
    z-index: 100;
  }
  .modal {
    background: var(--kv-surface);
    border: 1px solid var(--kv-border);
    border-radius: 8px;
    min-width: 360px;
    max-width: 480px;
    color: var(--kv-text);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  }
  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0.75rem 1rem; border-bottom: 1px solid var(--kv-border);
  }
  header h3 { margin: 0; font-size: 0.95rem; }
  .close {
    background: transparent; border: none; color: var(--kv-text-dim);
    cursor: pointer; font-size: 1rem; padding: 2px 6px;
  }
  .close:hover { color: var(--kv-text); }
  section { padding: 1rem; }
  section h4 {
    margin: 0 0 0.75rem;
    font-size: 0.7rem; letter-spacing: 0.08em;
    color: var(--kv-text-dim); text-transform: uppercase;
  }
  .field {
    display: grid; grid-template-columns: 1fr 160px auto; gap: 0.75rem;
    align-items: center; font-size: 0.85rem;
  }
  .value { color: var(--kv-text-dim); min-width: 3ch; text-align: right; }
</style>
```

- [ ] **Step 2: Wire the button and modal into Shell**

Edit `src/lib/ui/Shell.svelte`. Full replacement:

```svelte
<script lang="ts">
  import Tabs from './Tabs.svelte';
  import Footer from './Footer.svelte';
  import SettingsModal from './SettingsModal.svelte';
  import { project } from '$lib/stores/project';
  import { theme, toggleTheme } from '$lib/stores/theme';

  interface Props {
    tab: string;
    onTabChange: (v: string) => void;
    onClear?: () => void;
    onHelp?: () => void;
    children: import('svelte').Snippet;
    sidebar?: import('svelte').Snippet;
    inspector?: import('svelte').Snippet;
    cursorMm?: { x: number; y: number } | null;
  }
  let { tab, onTabChange, onClear, onHelp, children, sidebar, inspector, cursorMm }: Props = $props();

  let settingsOpen = $state(false);
</script>

<div class="shell">
  <header class="top">
    <strong>kicad-viewer</strong>
    <span class="project">{$project?.name ?? ''}</span>
    <Tabs value={tab} onChange={onTabChange} />
    <div class="actions">
      {#if onClear}
        <button onclick={onClear} class="iconbtn" aria-label="Clear project">Clear</button>
      {/if}
      <button onclick={() => (settingsOpen = true)} class="iconbtn" aria-label="Settings">Settings</button>
      {#if onHelp}
        <button onclick={onHelp} class="iconbtn" aria-label="Keyboard shortcuts">?</button>
      {/if}
      <button onclick={toggleTheme} class="iconbtn" aria-label="Toggle theme">{$theme === 'dark' ? '☾' : '☀'}</button>
    </div>
  </header>

  <div class="body">
    <aside class="side left">{@render sidebar?.()}</aside>
    <main class="main">{@render children()}</main>
    <aside class="side right">{@render inspector?.()}</aside>
  </div>

  <Footer projectName={$project?.name ?? ''} cursorMm={cursorMm ?? null} />
</div>

<SettingsModal open={settingsOpen} onClose={() => (settingsOpen = false)} />

<style>
  .shell { display: grid; grid-template-rows: auto 1fr auto; min-height: 100dvh; }
  .top {
    display: grid; grid-template-columns: auto auto 1fr auto;
    align-items: center; gap: 1rem;
    padding: 0.4rem 1rem; border-bottom: 1px solid var(--kv-border);
    background: var(--kv-surface);
  }
  .project { color: var(--kv-text-dim); font-size: 0.85rem; }
  .actions { display: flex; gap: 0.4rem; }
  .actions .iconbtn { background: transparent; border: 1px solid var(--kv-border); border-radius: 6px; padding: 4px 8px; color: var(--kv-text); cursor: pointer; }
  .actions .iconbtn:hover { background: var(--kv-surface-2); }
  .body {
    display: grid;
    grid-template-columns: 220px 1fr 280px;
    min-height: 0;
  }
  .side { background: var(--kv-surface); border-right: 1px solid var(--kv-border); overflow: auto; }
  .side.right { border-right: none; border-left: 1px solid var(--kv-border); }
  .main { overflow: hidden; background: var(--kv-render-bg); }
</style>
```

- [ ] **Step 3: Type-check**

Run: `cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer && npm run check`
Expected: No type errors.

- [ ] **Step 4: Manual verification**

Run `npm run dev`:
- Click Settings button → modal opens with opacity slider.
- Drag slider → PCB re-renders in real time; inactive layers dim accordingly.
- Close modal, reload page → slider value persists.
- Press Escape → modal closes.

- [ ] **Step 5: Commit**

```bash
cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer
git add src/lib/ui/SettingsModal.svelte src/lib/ui/Shell.svelte
git commit -m "ui: add settings modal with inactive layer opacity slider"
```

---

## Final Verification

- [ ] **All tests pass**

Run: `cd /home/mlaustin/repos/personal/kicad-tools/kicad-viewer && npx vitest run && npm run check`
Expected: All tests green, no type errors.

- [ ] **End-to-end manual check**

Using the `ohm_lamp_v2_usb_r3` project:
1. Load → PCB tab shows F.Cu active, B-side dimmed, refdes on top side only, net names on F.Cu traces.
2. Click B.Cu in layer panel → z-stack flips, B-side layers render on top at full opacity, refdes moves to bottom-side footprints, net names appear on B.Cu traces.
3. Click In1.Cu (on a multi-layer project) → In1 renders on top of copper group; front-side non-copper stays on top (since In1 is front-side).
4. Open Settings → drag opacity to 0 → inactive layers effectively disappear; drag to 0.8 → barely dimmed.
5. Reload page → previously-set opacity persists; active layer resets to F.Cu (by spec).
6. Toggle a layer visibility checkbox → that layer disappears entirely regardless of active state.
