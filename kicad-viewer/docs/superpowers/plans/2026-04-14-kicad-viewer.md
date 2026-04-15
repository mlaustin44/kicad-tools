# kicad-viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a browser-based KiCad 10 project viewer (schematic + PCB + 3D, with cross-probing) as a static SvelteKit app deployed to Cloudflare Pages.

**Architecture:** SvelteKit with `adapter-static`, client-rendered SPA. Pure TS core modules (model, loader, parser-adapter, selection, layer state) that are TDD'd. Views are Svelte components that subscribe to Svelte stores. Schematic renders via SVG, PCB via Canvas2D, 3D via Three.js. KiCanvas's parser files are vendored (MIT) at a pinned commit; everything above the parser is ours.

**Tech Stack:** SvelteKit 2, Vite, TypeScript strict, Vitest + @testing-library/svelte, Playwright, Three.js, fflate, Open Props for design tokens.

**Reference spec:** `kicad-viewer/docs/superpowers/specs/2026-04-14-kicad-viewer-design.md`.

**Execution environment:** All commands run from `/home/mlaustin/repos/personal/kicad-tools` unless specified. The new app lives in `kicad-viewer/`.

**Commit style:** Follows monorepo convention — one-line messages, no trailers. Commit frequently, one commit per task.

---

## File Structure (committed incrementally across the plan)

```
kicad-viewer/
├── .nvmrc
├── README.md
├── package.json
├── svelte.config.js
├── vite.config.ts
├── tsconfig.json
├── playwright.config.ts
├── vitest.config.ts
├── src/
│   ├── app.html
│   ├── app.css                           # tokens, theme, base
│   ├── routes/
│   │   ├── +layout.svelte                # theme + footer
│   │   ├── +page.svelte                  # landing
│   │   └── viewer/+page.svelte           # viewer SPA entry
│   └── lib/
│       ├── parser/                       # vendored KiCanvas parser (pinned)
│       │   ├── README.md
│       │   ├── tokenizer.ts
│       │   ├── parser.ts
│       │   ├── common.ts
│       │   ├── board.ts
│       │   ├── schematic.ts
│       │   ├── project-settings.ts
│       │   └── index.ts
│       ├── model/
│       │   ├── project.ts                # Project/Sheet/Component/Net/Layer types
│       │   └── ids.ts                    # UUID + refdes helpers
│       ├── loader/
│       │   ├── blob.ts                   # ProjectBlob types + file classification
│       │   ├── zip.ts                    # zip → blob (via fflate)
│       │   ├── folder.ts                 # File[] / folder handle → blob
│       │   └── loader.ts                 # unified entry
│       ├── adapter/
│       │   └── adapter.ts                # vendored parser output → our Project model
│       ├── stores/
│       │   ├── project.ts                # current Project
│       │   ├── selection.ts              # cross-probe selection store
│       │   ├── theme.ts                  # dark/light, persisted
│       │   ├── layers.ts                 # per-layer visibility
│       │   ├── recent.ts                 # IndexedDB recent projects
│       │   └── toasts.ts                 # simple error toast queue
│       ├── geom/
│       │   ├── rtree.ts                  # bounding-box R-tree (via flatbush)
│       │   └── hit.ts                    # hit-testing helpers
│       ├── pcb/
│       │   ├── scene.ts                  # scene builder: Project → PcbScene
│       │   └── render.ts                 # PcbScene → Canvas2D operations
│       ├── sch/
│       │   └── render.ts                 # Project sheet → SVG element tree
│       ├── three/
│       │   ├── loader.ts                 # GLB load via GLTFLoader
│       │   └── picker.ts                 # raycast helpers
│       ├── views/
│       │   ├── SchematicView.svelte
│       │   ├── PcbView.svelte
│       │   └── ThreeDView.svelte
│       ├── ui/
│       │   ├── Shell.svelte              # tabs, sidebar frame, inspector frame, footer
│       │   ├── Tabs.svelte
│       │   ├── DropZone.svelte
│       │   ├── SheetTree.svelte
│       │   ├── LayerPanel.svelte
│       │   ├── Inspector.svelte
│       │   ├── SearchBar.svelte
│       │   ├── SplitPane.svelte
│       │   ├── Toast.svelte
│       │   └── Footer.svelte
│       └── keys.ts                       # keyboard shortcut dispatcher
├── tests/
│   ├── fixtures/                         # small open-source KiCad project + .glb
│   │   ├── pic_programmer.kicad_pro
│   │   ├── pic_programmer.kicad_pcb
│   │   ├── pic_programmer.kicad_sch
│   │   └── pic_programmer.glb
│   ├── unit/                             # vitest — pure TS modules
│   ├── component/                        # vitest + testing-library/svelte
│   ├── e2e/                              # playwright
│   └── smoke-checklist.md
└── static/
    ├── favicon.svg
    └── og.png
```

Every task below names its files explicitly.

---

## Milestone 1 — Scaffold

### Task 1: Initialize SvelteKit + TypeScript + adapter-static

**Files:**
- Create: `kicad-viewer/package.json`
- Create: `kicad-viewer/svelte.config.js`
- Create: `kicad-viewer/vite.config.ts`
- Create: `kicad-viewer/tsconfig.json`
- Create: `kicad-viewer/src/app.html`
- Create: `kicad-viewer/src/routes/+page.svelte`
- Create: `kicad-viewer/.nvmrc`
- Create: `kicad-viewer/README.md`

- [ ] **Step 1: Scaffold the SvelteKit app (non-interactive)**

Run from repo root:

```bash
cd kicad-viewer
npx sv@latest create . --template minimal --types ts --no-add-ons --install npm
```

If the interactive prompt blocks, fall back to manual scaffold: create `package.json` from the template below, then run `npm install`.

`kicad-viewer/package.json`:
```json
{
  "name": "kicad-viewer",
  "private": true,
  "version": "0.0.1",
  "type": "module",
  "scripts": {
    "dev": "vite dev",
    "build": "vite build",
    "preview": "vite preview",
    "check": "svelte-kit sync && svelte-check --tsconfig ./tsconfig.json",
    "test": "vitest run",
    "test:watch": "vitest",
    "e2e": "playwright test"
  },
  "devDependencies": {
    "@sveltejs/adapter-static": "^3.0.0",
    "@sveltejs/kit": "^2.5.0",
    "@sveltejs/vite-plugin-svelte": "^4.0.0",
    "svelte": "^5.0.0",
    "svelte-check": "^4.0.0",
    "typescript": "^5.5.0",
    "vite": "^5.4.0"
  }
}
```

- [ ] **Step 2: Configure adapter-static**

`kicad-viewer/svelte.config.js`:
```js
import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

export default {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      fallback: 'index.html',  // SPA fallback for client-side routing
      precompress: false,
      strict: true
    })
  }
};
```

`kicad-viewer/vite.config.ts`:
```ts
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  server: { port: 5173 }
});
```

`kicad-viewer/tsconfig.json`:
```json
{
  "extends": "./.svelte-kit/tsconfig.json",
  "compilerOptions": {
    "strict": true,
    "noImplicitAny": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true
  }
}
```

- [ ] **Step 3: Make the root route opt out of SSR**

`kicad-viewer/src/routes/+layout.ts`:
```ts
export const prerender = true;
export const ssr = false;  // pure SPA
export const trailingSlash = 'ignore';
```

- [ ] **Step 4: Write a minimal landing stub**

`kicad-viewer/src/routes/+page.svelte`:
```svelte
<h1>kicad-viewer</h1>
<p>scaffold ok</p>
```

- [ ] **Step 5: Pin Node version**

`kicad-viewer/.nvmrc`:
```
20
```

- [ ] **Step 6: Build and verify**

```bash
cd kicad-viewer && npm install && npm run build
```

Expected: build succeeds, output in `kicad-viewer/build/`.

- [ ] **Step 7: Write minimal README**

`kicad-viewer/README.md`:
```markdown
# kicad-viewer

Browser-based KiCad 10 project viewer. Part of the `kicad-tools` monorepo.

## Develop

```
cd kicad-viewer
npm install
npm run dev
```

## Build

```
npm run build
```

Static output lands in `build/`. Deployable to Cloudflare Pages or any static host.
```

- [ ] **Step 8: Commit**

```bash
cd /home/mlaustin/repos/personal/kicad-tools
git add kicad-viewer/
git commit -m "Scaffold kicad-viewer SvelteKit app with adapter-static"
```

---

### Task 2: Install Vitest + testing-library/svelte, add smoke test

**Files:**
- Modify: `kicad-viewer/package.json`
- Create: `kicad-viewer/vitest.config.ts`
- Create: `kicad-viewer/tests/unit/smoke.test.ts`

- [ ] **Step 1: Install dev deps**

```bash
cd kicad-viewer
npm install -D vitest @testing-library/svelte @testing-library/jest-dom jsdom
```

- [ ] **Step 2: Add vitest config**

`kicad-viewer/vitest.config.ts`:
```ts
import { defineConfig } from 'vitest/config';
import { sveltekit } from '@sveltejs/kit/vite';

export default defineConfig({
  plugins: [sveltekit()],
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/unit/**/*.test.ts', 'tests/component/**/*.test.ts']
  }
});
```

- [ ] **Step 3: Write smoke test**

`kicad-viewer/tests/unit/smoke.test.ts`:
```ts
import { describe, it, expect } from 'vitest';

describe('smoke', () => {
  it('runs', () => {
    expect(1 + 1).toBe(2);
  });
});
```

- [ ] **Step 4: Run it**

```bash
cd kicad-viewer && npm test
```

Expected: PASS with 1 test.

- [ ] **Step 5: Commit**

```bash
git add kicad-viewer/
git commit -m "Add Vitest with smoke test"
```

---

### Task 3: Install Playwright, add e2e smoke test

**Files:**
- Modify: `kicad-viewer/package.json`
- Create: `kicad-viewer/playwright.config.ts`
- Create: `kicad-viewer/tests/e2e/smoke.spec.ts`

- [ ] **Step 1: Install**

```bash
cd kicad-viewer
npm install -D @playwright/test
npx playwright install --with-deps chromium
```

- [ ] **Step 2: Add playwright config**

`kicad-viewer/playwright.config.ts`:
```ts
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  webServer: {
    command: 'npm run build && npm run preview -- --port 4173',
    port: 4173,
    reuseExistingServer: !process.env.CI
  },
  use: { baseURL: 'http://localhost:4173' },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }]
});
```

- [ ] **Step 3: Write smoke test**

`kicad-viewer/tests/e2e/smoke.spec.ts`:
```ts
import { test, expect } from '@playwright/test';

test('landing page loads', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('h1')).toContainText('kicad-viewer');
});
```

- [ ] **Step 4: Run it**

```bash
cd kicad-viewer && npm run e2e
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add kicad-viewer/
git commit -m "Add Playwright with landing smoke test"
```

---

## Milestone 2 — Design tokens, theme, landing page

### Task 4: Design tokens and base CSS

**Files:**
- Create: `kicad-viewer/src/app.css`
- Modify: `kicad-viewer/src/routes/+layout.svelte`

- [ ] **Step 1: Install Open Props**

```bash
cd kicad-viewer
npm install open-props
```

- [ ] **Step 2: Write tokens + base CSS**

`kicad-viewer/src/app.css`:
```css
@import 'open-props/style';
@import 'open-props/normalize';

:root {
  color-scheme: light dark;
  --kv-font-sans: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif;
  --kv-font-mono: ui-monospace, 'JetBrains Mono', Menlo, monospace;

  /* semantic tokens — driven by [data-theme] */
  --kv-bg: white;
  --kv-surface: white;
  --kv-surface-2: #f6f6f7;
  --kv-border: #e5e7eb;
  --kv-text: #0b0b0c;
  --kv-text-dim: #5b5f67;
  --kv-accent: #2563eb;
  --kv-render-bg: #111318;
}

[data-theme='dark'] {
  --kv-bg: #0b0d12;
  --kv-surface: #12151c;
  --kv-surface-2: #171b24;
  --kv-border: #242a36;
  --kv-text: #e6e8ec;
  --kv-text-dim: #8a93a6;
  --kv-accent: #6aa6ff;
  --kv-render-bg: #0b0d12;
}

html, body {
  margin: 0; padding: 0; height: 100%;
  background: var(--kv-bg); color: var(--kv-text);
  font-family: var(--kv-font-sans);
}

button { font: inherit; cursor: pointer; }
```

- [ ] **Step 3: Create layout that imports CSS and sets theme attribute**

`kicad-viewer/src/routes/+layout.svelte`:
```svelte
<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { theme } from '$lib/stores/theme';
  let { children } = $props();

  onMount(() => {
    document.body.setAttribute('data-theme', $theme);
  });

  $effect(() => {
    if (typeof document !== 'undefined') {
      document.body.setAttribute('data-theme', $theme);
    }
  });
</script>

{@render children()}
```

Note: `theme` store is created in the next task; this file will initially fail to build. Move to Task 5 immediately.

- [ ] **Step 4: Commit at end of Task 5**

(see Task 5)

---

### Task 5: Theme store (dark/light, persisted)

**Files:**
- Create: `kicad-viewer/src/lib/stores/theme.ts`
- Create: `kicad-viewer/tests/unit/theme.test.ts`

- [ ] **Step 1: Write failing test**

`kicad-viewer/tests/unit/theme.test.ts`:
```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { theme, toggleTheme } from '$lib/stores/theme';

describe('theme store', () => {
  beforeEach(() => {
    localStorage.clear();
    // reset by forcing re-import would require module cache; instead, set directly
    theme.set('light');
  });

  it('defaults to light when no stored preference', () => {
    expect(get(theme)).toBe('light');
  });

  it('toggles dark <-> light', () => {
    theme.set('light');
    toggleTheme();
    expect(get(theme)).toBe('dark');
    toggleTheme();
    expect(get(theme)).toBe('light');
  });

  it('persists to localStorage', () => {
    theme.set('dark');
    expect(localStorage.getItem('kv.theme')).toBe('dark');
  });
});
```

- [ ] **Step 2: Run — fails**

```bash
cd kicad-viewer && npm test tests/unit/theme.test.ts
```

Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

`kicad-viewer/src/lib/stores/theme.ts`:
```ts
import { writable, get } from 'svelte/store';

export type Theme = 'light' | 'dark';

const KEY = 'kv.theme';

function initial(): Theme {
  if (typeof localStorage === 'undefined') return 'light';
  const v = localStorage.getItem(KEY);
  return v === 'dark' ? 'dark' : 'light';
}

export const theme = writable<Theme>(initial());

theme.subscribe((v) => {
  if (typeof localStorage !== 'undefined') localStorage.setItem(KEY, v);
  if (typeof document !== 'undefined') document.body.setAttribute('data-theme', v);
});

export function toggleTheme() {
  theme.set(get(theme) === 'dark' ? 'light' : 'dark');
}
```

- [ ] **Step 4: Run — passes**

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add kicad-viewer/
git commit -m "Add theme store with light/dark toggle and persistence"
```

---

### Task 6: Landing page at `/` (type-led, attribution)

**Files:**
- Modify: `kicad-viewer/src/routes/+page.svelte`
- Modify: `kicad-viewer/tests/e2e/smoke.spec.ts`

- [ ] **Step 1: Implement landing**

`kicad-viewer/src/routes/+page.svelte`:
```svelte
<script lang="ts">
  import { toggleTheme, theme } from '$lib/stores/theme';
</script>

<svelte:head>
  <title>kicad-viewer — by Matthew Austin</title>
  <meta name="description" content="Browser-based KiCad project viewer with schematic, PCB, and 3D views and cross-probing." />
</svelte:head>

<main class="landing">
  <header class="top">
    <span class="eyebrow">KICAD-VIEWER / MATTHEW AUSTIN</span>
    <button class="theme" onclick={toggleTheme} aria-label="Toggle theme">
      {$theme === 'dark' ? '☾' : '☀'}
    </button>
  </header>

  <section class="hero">
    <h1>A browser-based KiCad project viewer.</h1>
    <p>
      Schematic, PCB, and 3D views in one place, with full cross-probing between them.
      Drop a project folder or <code>.zip</code> and it renders — no upload, no install,
      runs entirely in your browser.
    </p>
    <nav class="cta">
      <a class="btn btn-primary" href="/viewer">Open viewer →</a>
      <a class="btn btn-secondary" href="https://github.com/mlaustin44/kicad-tools">GitHub</a>
    </nav>
  </section>

  <footer class="credit">Built by Matthew Austin, 2026</footer>
</main>

<style>
  .landing {
    min-height: 100dvh;
    display: grid;
    grid-template-rows: auto 1fr auto;
    padding: 2rem 4rem;
    max-width: 1100px; margin: 0 auto;
  }
  .top { display: flex; justify-content: space-between; align-items: center; }
  .eyebrow {
    font-size: 0.7rem; letter-spacing: 0.2em; color: var(--kv-text-dim);
  }
  .theme {
    background: transparent; border: 1px solid var(--kv-border);
    border-radius: 8px; padding: 6px 10px; color: var(--kv-text);
  }
  .hero { align-self: center; max-width: 640px; }
  .hero h1 {
    font-size: clamp(1.75rem, 4vw, 2.75rem);
    line-height: 1.1; font-weight: 600; margin: 0 0 1rem;
  }
  .hero p {
    color: var(--kv-text-dim); max-width: 52ch; line-height: 1.55;
    margin: 0 0 1.5rem;
  }
  .cta { display: flex; gap: 0.75rem; }
  .btn {
    padding: 0.6rem 1.1rem; border-radius: 8px;
    font-size: 0.9rem; text-decoration: none;
    border: 1px solid var(--kv-border);
  }
  .btn-primary { background: var(--kv-text); color: var(--kv-bg); border-color: var(--kv-text); }
  .btn-secondary { background: var(--kv-surface); color: var(--kv-text); }
  .credit { font-size: 0.75rem; color: var(--kv-text-dim); padding-top: 2rem; }
</style>
```

- [ ] **Step 2: Update e2e smoke to match new landing**

`kicad-viewer/tests/e2e/smoke.spec.ts`:
```ts
import { test, expect } from '@playwright/test';

test('landing page renders hero and CTA', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('h1')).toContainText('KiCad project viewer');
  await expect(page.locator('a', { hasText: 'Open viewer' })).toHaveAttribute('href', '/viewer');
  await expect(page.locator('.credit')).toContainText('Matthew Austin');
});
```

- [ ] **Step 3: Run**

```bash
cd kicad-viewer && npm run build && npm run e2e
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add kicad-viewer/
git commit -m "Add type-led landing page with attribution and theme toggle"
```

---

## Milestone 3 — Core model, loader, parser adapter

### Task 7: Project model types

**Files:**
- Create: `kicad-viewer/src/lib/model/project.ts`
- Create: `kicad-viewer/src/lib/model/ids.ts`
- Create: `kicad-viewer/tests/unit/ids.test.ts`

- [ ] **Step 1: Write failing test**

`kicad-viewer/tests/unit/ids.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { normalizeRefdes, isUuid } from '$lib/model/ids';

describe('ids', () => {
  it('uppercases and trims refdes', () => {
    expect(normalizeRefdes(' u1 ')).toBe('U1');
    expect(normalizeRefdes('r10')).toBe('R10');
  });

  it('recognises UUID v4', () => {
    expect(isUuid('00000000-0000-4000-8000-000000000000')).toBe(true);
    expect(isUuid('not-a-uuid')).toBe(false);
  });
});
```

- [ ] **Step 2: Run — fails**

Expected: FAIL (module not found).

- [ ] **Step 3: Implement ids**

`kicad-viewer/src/lib/model/ids.ts`:
```ts
export type Uuid = string;
export type Refdes = string;

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(s: string): boolean {
  return UUID_RE.test(s);
}

export function normalizeRefdes(s: string): Refdes {
  return s.trim().toUpperCase();
}
```

- [ ] **Step 4: Implement model types**

`kicad-viewer/src/lib/model/project.ts`:
```ts
import type { Uuid, Refdes } from './ids';

export interface Project {
  name: string;
  sheets: Sheet[];                    // root sheet first; sub-sheets follow (flat list; hierarchy in `parent`)
  components: Component[];            // across all sheets
  nets: Net[];
  pcb: PcbData;
  glbUrl?: string | undefined;        // if supplied in bundle or sidecar
  source: 'raw' | 'bundle';
}

export interface Sheet {
  uuid: Uuid;
  name: string;                       // human, e.g. "power"
  path: string[];                     // hierarchical path, e.g. ["root", "power"]
  parent: Uuid | null;
  componentUuids: Uuid[];
  boundsMm: Rect;
}

export interface Component {
  uuid: Uuid;
  refdes: Refdes;
  value: string;
  footprint: string;
  sheetUuid: Uuid;
  mpn?: string | undefined;
  manufacturer?: string | undefined;
  datasheet?: string | undefined;
  dnp: boolean;
  pins: Pin[];
  positionMm?: Point | undefined;     // on PCB; undefined if schematic-only
  rotationDeg?: number | undefined;
  side?: 'top' | 'bottom' | undefined;
}

export interface Pin { number: string; name: string; netName: string | null; }

export interface Net {
  name: string;
  refdesPins: Array<{ refdes: Refdes; pin: string }>;
}

export interface PcbData {
  boundsMm: Rect;
  layers: LayerInfo[];
  stackup: StackupLayer[];
  footprints: FootprintGeom[];
  tracks: TrackSeg[];
  vias: Via[];
  zones: Zone[];
  drills: Drill[];
}

export interface LayerInfo { id: string; name: string; type: LayerType; defaultColor: string; }
export type LayerType =
  | 'F.Cu' | 'B.Cu' | 'In.Cu'
  | 'F.SilkS' | 'B.SilkS'
  | 'F.Mask' | 'B.Mask'
  | 'F.Paste' | 'B.Paste'
  | 'F.CrtYd' | 'B.CrtYd'
  | 'F.Fab' | 'B.Fab'
  | 'Edge.Cuts' | 'Margin'
  | 'Other';

export interface StackupLayer { name: string; type: string; thicknessMm: number; }
export interface FootprintGeom {
  uuid: Uuid; refdes: Refdes;
  position: Point; rotationDeg: number; side: 'top' | 'bottom';
  bboxMm: Rect;
  pads: Pad[];
  graphics: Graphic[];               // silk/fab lines, text
}
export interface Pad { number: string; shape: string; layerIds: string[]; positionMm: Point; sizeMm: Size; netName: string | null; }
export interface Graphic { layerId: string; geom: GraphicGeom; }
export type GraphicGeom =
  | { kind: 'line'; a: Point; b: Point; widthMm: number }
  | { kind: 'arc'; center: Point; radiusMm: number; startDeg: number; endDeg: number; widthMm: number }
  | { kind: 'polygon'; points: Point[]; widthMm: number; filled: boolean }
  | { kind: 'text'; position: Point; rotationDeg: number; heightMm: number; text: string };
export interface TrackSeg { layerId: string; a: Point; b: Point; widthMm: number; netName: string | null; }
export interface Via { position: Point; diameterMm: number; drillMm: number; layerFrom: string; layerTo: string; netName: string | null; }
export interface Zone { layerId: string; polygon: Point[]; netName: string | null; }
export interface Drill { position: Point; diameterMm: number; plated: boolean; }
export interface Point { x: number; y: number; }
export interface Size { w: number; h: number; }
export interface Rect { x: number; y: number; w: number; h: number; }
```

- [ ] **Step 5: Run — passes**

Expected: 2 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add kicad-viewer/
git commit -m "Add Project model types and id helpers"
```

---

### Task 8: SelectionStore with cross-probe contract

**Files:**
- Create: `kicad-viewer/src/lib/stores/selection.ts`
- Create: `kicad-viewer/tests/unit/selection.test.ts`

- [ ] **Step 1: Write failing test covering the reaction contract**

`kicad-viewer/tests/unit/selection.test.ts`:
```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import {
  selection, selectComponent, selectNet, selectSheet, clearSelection,
  type Selection
} from '$lib/stores/selection';

describe('selection store', () => {
  beforeEach(() => clearSelection());

  it('starts empty', () => {
    expect(get(selection)).toBeNull();
  });

  it('selects a component', () => {
    selectComponent({ uuid: 'u1', source: 'sch' });
    const s = get(selection)!;
    expect(s.kind).toBe('component');
    expect(s.uuid).toBe('u1');
    expect(s.source).toBe('sch');
  });

  it('selecting the same component with a new source updates the source', () => {
    selectComponent({ uuid: 'u1', source: 'sch' });
    selectComponent({ uuid: 'u1', source: 'pcb' });
    expect(get(selection)!.source).toBe('pcb');
  });

  it('clears selection', () => {
    selectComponent({ uuid: 'u1', source: 'sch' });
    clearSelection();
    expect(get(selection)).toBeNull();
  });

  it('net selection has no uuid, has name', () => {
    selectNet({ name: 'VCC', source: 'pcb' });
    const s = get(selection)!;
    expect(s.kind).toBe('net');
    if (s.kind === 'net') expect(s.name).toBe('VCC');
  });

  it('sheet selection carries uuid', () => {
    selectSheet({ uuid: 'sheet-0', source: 'search' });
    expect(get(selection)!.kind).toBe('sheet');
  });
});
```

- [ ] **Step 2: Run — fails**

Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

`kicad-viewer/src/lib/stores/selection.ts`:
```ts
import { writable } from 'svelte/store';

export type SelectionSource = 'sch' | 'pcb' | '3d' | 'search';

export type Selection =
  | { kind: 'component'; uuid: string; source: SelectionSource }
  | { kind: 'net'; name: string; source: SelectionSource }
  | { kind: 'sheet'; uuid: string; source: SelectionSource };

export const selection = writable<Selection | null>(null);

export function selectComponent(args: { uuid: string; source: SelectionSource }) {
  selection.set({ kind: 'component', uuid: args.uuid, source: args.source });
}
export function selectNet(args: { name: string; source: SelectionSource }) {
  selection.set({ kind: 'net', name: args.name, source: args.source });
}
export function selectSheet(args: { uuid: string; source: SelectionSource }) {
  selection.set({ kind: 'sheet', uuid: args.uuid, source: args.source });
}
export function clearSelection() {
  selection.set(null);
}
```

- [ ] **Step 4: Run — passes**

Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add kicad-viewer/
git commit -m "Add selection store for cross-probing"
```

---

### Task 9: Toast store + component

**Files:**
- Create: `kicad-viewer/src/lib/stores/toasts.ts`
- Create: `kicad-viewer/src/lib/ui/Toast.svelte`
- Create: `kicad-viewer/tests/unit/toasts.test.ts`

- [ ] **Step 1: Write test**

`kicad-viewer/tests/unit/toasts.test.ts`:
```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { toasts, pushToast, dismissToast } from '$lib/stores/toasts';

describe('toasts', () => {
  beforeEach(() => toasts.set([]));
  it('pushes a toast with monotonic ids', () => {
    pushToast({ kind: 'error', message: 'a' });
    pushToast({ kind: 'info', message: 'b' });
    const list = get(toasts);
    expect(list).toHaveLength(2);
    expect(list[1]!.id).toBeGreaterThan(list[0]!.id);
  });
  it('dismisses by id', () => {
    pushToast({ kind: 'error', message: 'a' });
    const id = get(toasts)[0]!.id;
    dismissToast(id);
    expect(get(toasts)).toHaveLength(0);
  });
});
```

- [ ] **Step 2: Implement store**

`kicad-viewer/src/lib/stores/toasts.ts`:
```ts
import { writable } from 'svelte/store';

export type Toast = { id: number; kind: 'error' | 'info' | 'success'; message: string; };

export const toasts = writable<Toast[]>([]);

let nextId = 1;
export function pushToast(t: Omit<Toast, 'id'>) {
  toasts.update((l) => [...l, { id: nextId++, ...t }]);
}
export function dismissToast(id: number) {
  toasts.update((l) => l.filter((t) => t.id !== id));
}
```

- [ ] **Step 3: Implement component**

`kicad-viewer/src/lib/ui/Toast.svelte`:
```svelte
<script lang="ts">
  import { toasts, dismissToast } from '$lib/stores/toasts';
</script>

<div class="stack" role="status" aria-live="polite">
  {#each $toasts as t (t.id)}
    <div class="toast {t.kind}" onclick={() => dismissToast(t.id)}>
      {t.message}
    </div>
  {/each}
</div>

<style>
  .stack { position: fixed; right: 1rem; bottom: 1rem; display: grid; gap: 0.5rem; z-index: 100; }
  .toast {
    padding: 0.6rem 0.9rem; border-radius: 8px;
    background: var(--kv-surface-2); border: 1px solid var(--kv-border);
    color: var(--kv-text); font-size: 0.85rem; cursor: pointer; max-width: 340px;
  }
  .toast.error { border-color: #d14b4b; }
</style>
```

- [ ] **Step 4: Run tests**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add kicad-viewer/
git commit -m "Add toast store and Toast component"
```

---

### Task 10: Vendor KiCanvas parser files

**Files:**
- Create: `kicad-viewer/src/lib/parser/*` (copied from KiCanvas)
- Create: `kicad-viewer/src/lib/parser/README.md`

- [ ] **Step 1: Verify the reference clone is at the expected SHA**

```bash
cd /home/mlaustin/repos/personal/kicad-tools/references/kicanvas
git rev-parse HEAD
```

Expected: `2890714705df9378fb09cc89c0776582da21cc96`. If different, note the actual SHA and use it in the README below.

- [ ] **Step 2: Copy parser files**

```bash
SRC=/home/mlaustin/repos/personal/kicad-tools/references/kicanvas/src/kicad
DST=/home/mlaustin/repos/personal/kicad-tools/kicad-viewer/src/lib/parser
cp $SRC/tokenizer.ts $SRC/parser.ts $SRC/common.ts $SRC/board.ts \
   $SRC/schematic.ts $SRC/project-settings.ts $SRC/index.ts $DST/
cp -r $SRC/text $DST/
```

- [ ] **Step 3: Strip imports that reference outside `src/kicad/`**

Inspect each copied file for imports starting with `../` or from `../../` — these reach out to KiCanvas internals (`base/`, `graphics/`, etc.). For each violating import:
- If the import is a utility (e.g., `base/assert`, `base/vec2`), reimplement minimally inline or copy the single dependent file into `parser/` (and repeat the strip).
- If the import is rendering/UI, delete the offending import line and any code that depends on it; most such code sits in methods we don't call from the adapter.

Use `grep -r "from '\\.\\./" kicad-viewer/src/lib/parser/` until it returns empty.

- [ ] **Step 4: Adjust tsconfig if needed**

The vendored files may use `noUncheckedIndexedAccess: false` style indexing. Keep our strict settings; fix issues as compiler errors come up (usually `!` non-null assertions at known safe spots).

Run:
```bash
cd kicad-viewer && npm run check
```

Fix errors until `svelte-check` passes.

- [ ] **Step 5: Write README**

`kicad-viewer/src/lib/parser/README.md`:
````markdown
# Vendored KiCad parser

Files in this directory are copied from [KiCanvas](https://github.com/theacodes/kicanvas)
at commit `2890714705df9378fb09cc89c0776582da21cc96` (2026-04-13). MIT licensed.

## What was copied

- `tokenizer.ts`, `parser.ts`, `common.ts` — s-expression tokenizer and parser
- `board.ts`, `schematic.ts` — typed models of parsed .kicad_pcb / .kicad_sch
- `project-settings.ts` — .kicad_pro parser
- `text/` — stroke font engine (used by board/schematic for text rendering)
- `index.ts` — barrel re-exports

## What was stripped

All imports from `../base/`, `../graphics/`, `../viewers/`, `../kc-ui/` — KiCanvas's
rendering and UI layer. Any methods in the parser classes that relied on these were
either removed or inlined with minimal replacements.

## How we use it

`src/lib/adapter/adapter.ts` imports from this module and converts the parser's output
into our own `Project` type (see `src/lib/model/project.ts`). The rest of the app does
not import from here directly.

## Updating

To re-vendor: update the SHA, re-copy the files, re-strip imports, run
`npm run check` until it's clean. Record the new SHA here.
````

- [ ] **Step 6: Commit**

```bash
git add kicad-viewer/
git commit -m "Vendor KiCanvas parser at 28907147"
```

---

### Task 11: Parser adapter — vendored parser → Project model

**Files:**
- Create: `kicad-viewer/src/lib/adapter/adapter.ts`
- Create: `kicad-viewer/tests/unit/adapter.test.ts`
- Copy: `kicad-viewer/tests/fixtures/tiny.kicad_pcb` (synthetic, see Step 1)
- Copy: `kicad-viewer/tests/fixtures/tiny.kicad_sch` (synthetic)
- Copy: `kicad-viewer/tests/fixtures/tiny.kicad_pro`

- [ ] **Step 1: Commit a tiny synthetic fixture**

Use the smallest existing KiCad 10 project. Simplest path: copy one of KiCad's built-in demo projects if already present on disk. Otherwise, author a minimal project by hand in KiCad and save to `tests/fixtures/tiny.*`.

If no project is available, commit these minimal stubs (they will parse, though fields will be mostly empty):

`kicad-viewer/tests/fixtures/tiny.kicad_pro`:
```json
{
  "meta": { "filename": "tiny.kicad_pro", "version": 1 },
  "board": { "design_settings": {} },
  "schematic": {},
  "pcbnew": {},
  "sheets": [ ["00000000-0000-4000-8000-000000000001", "Root"] ]
}
```

`kicad-viewer/tests/fixtures/tiny.kicad_sch`:
```
(kicad_sch (version 20231120) (generator kicad_viewer_fixture)
  (uuid 00000000-0000-4000-8000-000000000001)
  (paper "A4")
)
```

`kicad-viewer/tests/fixtures/tiny.kicad_pcb`:
```
(kicad_pcb (version 20241229) (generator kicad_viewer_fixture)
  (general (thickness 1.6))
  (paper "A4")
  (layers
    (0 "F.Cu" signal) (31 "B.Cu" signal)
    (36 "B.SilkS" user) (37 "F.SilkS" user)
    (44 "Edge.Cuts" user)
  )
)
```

Swap these out for a real pic_programmer fixture in Task 12.

- [ ] **Step 2: Write failing test**

`kicad-viewer/tests/unit/adapter.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { toProject } from '$lib/adapter/adapter';

const fix = (f: string) => readFileSync(join('tests/fixtures', f), 'utf-8');

describe('adapter.toProject', () => {
  it('parses a trivial project into our model', () => {
    const project = toProject({
      pro: fix('tiny.kicad_pro'),
      pcb: fix('tiny.kicad_pcb'),
      schematics: { 'tiny.kicad_sch': fix('tiny.kicad_sch') },
      rootSchematic: 'tiny.kicad_sch'
    });
    expect(project.sheets.length).toBeGreaterThanOrEqual(1);
    expect(project.pcb.layers.some((l) => l.id === 'F.Cu')).toBe(true);
    expect(project.source).toBe('raw');
  });
});
```

- [ ] **Step 3: Run — fails**

Expected: FAIL (module not found).

- [ ] **Step 4: Implement minimal adapter**

`kicad-viewer/src/lib/adapter/adapter.ts`:
```ts
import { KicadSch } from '$lib/parser/schematic';
import { KicadPCB } from '$lib/parser/board';
import type { Project, Sheet, Component, Net, PcbData, LayerInfo } from '$lib/model/project';

export interface AdapterInput {
  pro: string;
  pcb: string;
  schematics: Record<string, string>;
  rootSchematic: string;
}

export function toProject(input: AdapterInput): Project {
  const sheets = buildSheets(input.schematics, input.rootSchematic);
  const components = buildComponents(input.schematics, sheets);
  const pcb = buildPcb(input.pcb);
  const nets = buildNets(pcb, components);

  mergePcbPositions(components, pcb);

  return {
    name: deriveName(input.rootSchematic),
    sheets, components, nets, pcb,
    source: 'raw'
  };
}

// — helpers (kept narrow; extend as real fixtures demand) —

function deriveName(path: string): string {
  return path.replace(/\.kicad_sch$/, '').split('/').pop() ?? 'project';
}

function buildSheets(src: Record<string, string>, root: string): Sheet[] {
  const sheets: Sheet[] = [];
  // KiCad 10 sheets: parse each .kicad_sch, pick up uuid and sheet symbols,
  // build parent-child links. Minimal impl for tiny fixture: one sheet per file.
  for (const [filename, text] of Object.entries(src)) {
    const sch = new KicadSch(filename, text);
    sheets.push({
      uuid: (sch as any).uuid ?? filename,
      name: filename.replace(/\.kicad_sch$/, ''),
      path: filename === root ? ['root'] : ['root', filename.replace(/\.kicad_sch$/, '')],
      parent: filename === root ? null : (sheets[0]?.uuid ?? null),
      componentUuids: [],
      boundsMm: { x: 0, y: 0, w: 297, h: 210 }  // A4 placeholder; refine via sch
    });
  }
  return sheets;
}

function buildComponents(src: Record<string, string>, sheets: Sheet[]): Component[] {
  const comps: Component[] = [];
  for (const [filename, text] of Object.entries(src)) {
    const sch = new KicadSch(filename, text);
    const sheet = sheets.find((s) => s.name === filename.replace(/\.kicad_sch$/, '')) ?? sheets[0];
    if (!sheet) continue;
    // Iterate sch symbols: KiCanvas's KicadSch exposes `symbols` iterable.
    for (const sym of ((sch as any).symbols ?? []) as any[]) {
      const refdes = sym.reference ?? sym.getProperty?.('Reference')?.value ?? '?';
      const value  = sym.value     ?? sym.getProperty?.('Value')?.value     ?? '';
      const fp     = sym.footprint ?? sym.getProperty?.('Footprint')?.value ?? '';
      comps.push({
        uuid: sym.uuid ?? `${sheet.uuid}:${refdes}`,
        refdes, value, footprint: fp,
        sheetUuid: sheet.uuid,
        dnp: sym.dnp ?? false,
        pins: [],
        mpn: sym.getProperty?.('MPN')?.value,
        manufacturer: sym.getProperty?.('Manufacturer')?.value,
        datasheet: sym.datasheet ?? sym.getProperty?.('Datasheet')?.value
      });
      sheet.componentUuids.push(comps[comps.length - 1]!.uuid);
    }
  }
  return comps;
}

function buildPcb(pcbText: string): PcbData {
  const pcb = new KicadPCB('pcb', pcbText);
  const layers: LayerInfo[] = ((pcb as any).layers ?? []).map((l: any) => ({
    id: l.name, name: l.name,
    type: classifyLayer(l.name),
    defaultColor: defaultColorFor(l.name)
  }));
  return {
    boundsMm: { x: 0, y: 0, w: 0, h: 0 },      // filled by subsequent pass
    layers,
    stackup: [],
    footprints: [],
    tracks: [],
    vias: [],
    zones: [],
    drills: []
  };
}

function buildNets(pcb: PcbData, _components: Component[]): Net[] {
  const names = new Set<string>();
  for (const t of pcb.tracks) if (t.netName) names.add(t.netName);
  for (const v of pcb.vias)   if (v.netName) names.add(v.netName);
  return [...names].map((name) => ({ name, refdesPins: [] }));
}

function mergePcbPositions(_c: Component[], _p: PcbData) { /* extended in Task 14 */ }

function classifyLayer(name: string): LayerInfo['type'] {
  if (name === 'F.Cu') return 'F.Cu';
  if (name === 'B.Cu') return 'B.Cu';
  if (/^In[0-9]+\.Cu$/.test(name)) return 'In.Cu';
  if (name === 'F.SilkS') return 'F.SilkS';
  if (name === 'B.SilkS') return 'B.SilkS';
  if (name === 'F.Mask') return 'F.Mask';
  if (name === 'B.Mask') return 'B.Mask';
  if (name === 'F.Paste') return 'F.Paste';
  if (name === 'B.Paste') return 'B.Paste';
  if (name === 'F.CrtYd') return 'F.CrtYd';
  if (name === 'B.CrtYd') return 'B.CrtYd';
  if (name === 'F.Fab') return 'F.Fab';
  if (name === 'B.Fab') return 'B.Fab';
  if (name === 'Edge.Cuts') return 'Edge.Cuts';
  if (name === 'Margin') return 'Margin';
  return 'Other';
}

function defaultColorFor(name: string): string {
  const m: Record<string, string> = {
    'F.Cu': '#c83434', 'B.Cu': '#4d7fc4',
    'F.SilkS': '#e5e5e5', 'B.SilkS': '#aaaaaa',
    'F.Mask': '#008579', 'B.Mask': '#008579',
    'F.Paste': '#d0d0d0', 'B.Paste': '#d0d0d0',
    'F.CrtYd': '#7fb37f', 'B.CrtYd': '#7fb37f',
    'F.Fab': '#b58d6c', 'B.Fab': '#afafaf',
    'Edge.Cuts': '#f2eda1'
  };
  return m[name] ?? '#888';
}
```

Note: the `as any` casts are deliberate entry points — the vendored parser has its own
class types; we narrow as we need specific fields in later tasks. Do not refactor these
away speculatively.

- [ ] **Step 5: Run — passes**

Expected: the one fixture-based test passes with the minimal layers list.

- [ ] **Step 6: Commit**

```bash
git add kicad-viewer/
git commit -m "Add parser adapter and tiny fixture"
```

---

### Task 12: Replace tiny fixture with real pic_programmer project

**Files:**
- Replace: `kicad-viewer/tests/fixtures/*`
- Add: `kicad-viewer/tests/fixtures/pic_programmer.glb`

- [ ] **Step 1: Locate a real KiCad 10 demo project**

Source options, in order:
1. `/usr/share/kicad/demos/` (Linux KiCad install) — check for `pic_programmer/`.
2. `~/.local/share/kicad/demos/` (user-local).
3. Download from `https://gitlab.com/kicad/code/kicad/-/tree/master/demos/pic_programmer` as fallback.

```bash
cp -r /usr/share/kicad/demos/pic_programmer/* kicad-viewer/tests/fixtures/
# or the fallback path
```

- [ ] **Step 2: Generate a .glb from the project**

```bash
kicad-cli pcb export glb \
  kicad-viewer/tests/fixtures/pic_programmer.kicad_pcb \
  -o kicad-viewer/tests/fixtures/pic_programmer.glb \
  --subst-models --force
```

- [ ] **Step 3: Update `adapter.test.ts` to point at the real project**

Change the fixture filenames in the test to `pic_programmer.*`.

- [ ] **Step 4: Run**

If adapter code chokes on real data, iterate Task 11's helpers to cover the missing
cases — specifically finish `buildComponents` (for hierarchical sub-sheets),
`buildPcb` (populate footprints, tracks, vias, zones, drills from the parser's
iterables), and `mergePcbPositions`.

Keep commits small: one per filled-in helper.

- [ ] **Step 5: Commit (may be multiple commits if helpers are filled in separately)**

```bash
git add kicad-viewer/
git commit -m "Swap fixture to pic_programmer and flesh out adapter helpers"
```

---

### Task 13: Loader — zip, folder, individual files

**Files:**
- Create: `kicad-viewer/src/lib/loader/blob.ts`
- Create: `kicad-viewer/src/lib/loader/zip.ts`
- Create: `kicad-viewer/src/lib/loader/folder.ts`
- Create: `kicad-viewer/src/lib/loader/loader.ts`
- Create: `kicad-viewer/tests/unit/loader.test.ts`

- [ ] **Step 1: Install fflate**

```bash
cd kicad-viewer && npm install fflate
```

- [ ] **Step 2: Write test**

`kicad-viewer/tests/unit/loader.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { zipSync, strToU8 } from 'fflate';
import { loadFromZipBytes } from '$lib/loader/zip';
import { classifyFiles } from '$lib/loader/blob';

describe('loader.blob.classify', () => {
  it('classifies files by extension', () => {
    const blob = classifyFiles({
      'p.kicad_pro': 'x', 'p.kicad_pcb': 'y', 'p.kicad_sch': 'z',
      'p.glb': new Uint8Array([1, 2, 3])
    });
    expect(blob.kicadPro).toBe('p.kicad_pro');
    expect(blob.kicadPcb).toBe('p.kicad_pcb');
    expect(blob.schematics).toContain('p.kicad_sch');
    expect(blob.glb).toBe('p.glb');
  });
});

describe('loader.zip', () => {
  it('extracts a synthetic zip', async () => {
    const zip = zipSync({
      'p.kicad_pro': strToU8('{}'),
      'p.kicad_pcb': strToU8('(kicad_pcb)'),
      'p.kicad_sch': strToU8('(kicad_sch)')
    });
    const blob = await loadFromZipBytes(zip);
    expect(blob.kicadPro).toBe('p.kicad_pro');
    expect(blob.schematics.length).toBe(1);
  });
});
```

- [ ] **Step 3: Implement `blob.ts`**

`kicad-viewer/src/lib/loader/blob.ts`:
```ts
export interface ProjectBlob {
  files: Record<string, string | Uint8Array>;
  kicadPro: string | null;
  kicadPcb: string | null;
  schematics: string[];                // filenames
  glb: string | null;
  manifest: BundleManifest | null;
}

export interface BundleManifest {
  name: string;
  version: string;
  files: { pcb: string; sch: string[]; glb?: string };
  generated_by?: string;
}

export function classifyFiles(files: Record<string, string | Uint8Array>): ProjectBlob {
  let kicadPro: string | null = null;
  let kicadPcb: string | null = null;
  const schematics: string[] = [];
  let glb: string | null = null;
  let manifest: BundleManifest | null = null;

  for (const name of Object.keys(files)) {
    const lower = name.toLowerCase();
    if (lower.endsWith('.kicad_pro'))      kicadPro = name;
    else if (lower.endsWith('.kicad_pcb')) kicadPcb = name;
    else if (lower.endsWith('.kicad_sch')) schematics.push(name);
    else if (lower.endsWith('.glb'))       glb = name;
    else if (lower === 'manifest.json') {
      const text = typeof files[name] === 'string'
        ? (files[name] as string)
        : new TextDecoder().decode(files[name] as Uint8Array);
      manifest = JSON.parse(text);
    }
  }
  return { files, kicadPro, kicadPcb, schematics, glb, manifest };
}

export function rootSchematic(blob: ProjectBlob): string | null {
  // Bundle manifest wins
  if (blob.manifest?.files?.sch?.[0]) return blob.manifest.files.sch[0];
  if (blob.schematics.length === 0) return null;
  // Heuristic: same stem as .kicad_pro if present, else first
  if (blob.kicadPro) {
    const stem = blob.kicadPro.replace(/\.kicad_pro$/i, '');
    const match = blob.schematics.find((s) => s.startsWith(stem + '.'));
    if (match) return match;
  }
  return blob.schematics[0] ?? null;
}
```

- [ ] **Step 4: Implement `zip.ts`**

`kicad-viewer/src/lib/loader/zip.ts`:
```ts
import { unzip } from 'fflate';
import { classifyFiles, type ProjectBlob } from './blob';

export async function loadFromZipBytes(bytes: Uint8Array): Promise<ProjectBlob> {
  const unpacked: Record<string, string | Uint8Array> = await new Promise((resolve, reject) => {
    unzip(bytes, (err, data) => {
      if (err) return reject(err);
      const out: Record<string, string | Uint8Array> = {};
      for (const [k, v] of Object.entries(data)) {
        // v is Uint8Array. Decode text for known text formats; leave binary alone.
        if (/\.(kicad_[a-z]+|json)$/i.test(k)) {
          out[k] = new TextDecoder().decode(v);
        } else {
          out[k] = v;
        }
      }
      resolve(out);
    });
  });
  return classifyFiles(unpacked);
}

export async function loadFromZipFile(file: File): Promise<ProjectBlob> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  return loadFromZipBytes(bytes);
}
```

- [ ] **Step 5: Implement `folder.ts`**

`kicad-viewer/src/lib/loader/folder.ts`:
```ts
import { classifyFiles, type ProjectBlob } from './blob';

export async function loadFromFileList(files: FileList | File[]): Promise<ProjectBlob> {
  const map: Record<string, string | Uint8Array> = {};
  for (const f of Array.from(files)) {
    const isText = /\.(kicad_[a-z]+|json)$/i.test(f.name);
    map[f.name] = isText ? await f.text() : new Uint8Array(await f.arrayBuffer());
  }
  return classifyFiles(map);
}

export async function loadFromDirectoryHandle(handle: FileSystemDirectoryHandle): Promise<ProjectBlob> {
  const map: Record<string, string | Uint8Array> = {};
  await walk(handle, '', map);
  return classifyFiles(map);
}

async function walk(dir: FileSystemDirectoryHandle, prefix: string, into: Record<string, string | Uint8Array>) {
  for await (const [name, entry] of (dir as any).entries()) {
    const full = prefix ? `${prefix}/${name}` : name;
    if (entry.kind === 'file') {
      const f = await entry.getFile();
      const isText = /\.(kicad_[a-z]+|json)$/i.test(f.name);
      into[full] = isText ? await f.text() : new Uint8Array(await f.arrayBuffer());
    } else if (entry.kind === 'directory') {
      await walk(entry, full, into);
    }
  }
}
```

- [ ] **Step 6: Implement unified loader**

`kicad-viewer/src/lib/loader/loader.ts`:
```ts
import { loadFromZipFile } from './zip';
import { loadFromFileList, loadFromDirectoryHandle } from './folder';
import type { ProjectBlob } from './blob';

export async function loadProject(input: File | FileList | File[] | FileSystemDirectoryHandle): Promise<ProjectBlob> {
  if ('getDirectoryHandle' in (input as any)) {
    return loadFromDirectoryHandle(input as FileSystemDirectoryHandle);
  }
  if (input instanceof File && /\.zip$/i.test(input.name)) {
    return loadFromZipFile(input);
  }
  if (input instanceof FileList || Array.isArray(input)) {
    return loadFromFileList(input as FileList | File[]);
  }
  if (input instanceof File) {
    return loadFromFileList([input]);
  }
  throw new Error('Unsupported input');
}
```

- [ ] **Step 7: Run tests**

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add kicad-viewer/
git commit -m "Add project loader (zip, folder, files) with manifest detection"
```

---

### Task 14: Project store and initial viewer route

**Files:**
- Create: `kicad-viewer/src/lib/stores/project.ts`
- Create: `kicad-viewer/src/routes/viewer/+page.svelte`
- Create: `kicad-viewer/src/lib/ui/DropZone.svelte`

- [ ] **Step 1: Implement project store**

`kicad-viewer/src/lib/stores/project.ts`:
```ts
import { writable, derived } from 'svelte/store';
import type { Project, Component, Net, Sheet } from '$lib/model/project';

export const project = writable<Project | null>(null);

export const componentsByUuid = derived(project, (p) => {
  const m = new Map<string, Component>();
  if (p) for (const c of p.components) m.set(c.uuid, c);
  return m;
});

export const componentsByRefdes = derived(project, (p) => {
  const m = new Map<string, Component>();
  if (p) for (const c of p.components) m.set(c.refdes, c);
  return m;
});

export const sheetsByUuid = derived(project, (p) => {
  const m = new Map<string, Sheet>();
  if (p) for (const s of p.sheets) m.set(s.uuid, s);
  return m;
});

export const netsByName = derived(project, (p) => {
  const m = new Map<string, Net>();
  if (p) for (const n of p.nets) m.set(n.name, n);
  return m;
});
```

- [ ] **Step 2: Implement DropZone**

`kicad-viewer/src/lib/ui/DropZone.svelte`:
```svelte
<script lang="ts">
  import { loadProject } from '$lib/loader/loader';
  import { toProject } from '$lib/adapter/adapter';
  import { project } from '$lib/stores/project';
  import { rootSchematic } from '$lib/loader/blob';
  import { pushToast } from '$lib/stores/toasts';

  let dragging = $state(false);

  async function ingest(input: File | FileList | File[] | FileSystemDirectoryHandle) {
    try {
      const blob = await loadProject(input);
      const root = rootSchematic(blob);
      if (!blob.kicadPcb || !root) throw new Error('missing .kicad_pcb or .kicad_sch');
      const schematics: Record<string, string> = {};
      for (const s of blob.schematics) schematics[s] = blob.files[s] as string;
      const pro = blob.kicadPro ? (blob.files[blob.kicadPro] as string) : '{}';
      const pcb = blob.files[blob.kicadPcb] as string;
      const p = toProject({ pro, pcb, schematics, rootSchematic: root });
      if (blob.glb) {
        const u8 = blob.files[blob.glb] as Uint8Array;
        p.glbUrl = URL.createObjectURL(new Blob([u8], { type: 'model/gltf-binary' }));
      }
      if (blob.manifest) p.source = 'bundle';
      project.set(p);
    } catch (e: any) {
      pushToast({ kind: 'error', message: `Couldn't load project: ${e.message ?? e}` });
    }
  }

  async function onDrop(ev: DragEvent) {
    ev.preventDefault(); dragging = false;
    const items = ev.dataTransfer?.items;
    if (items && items.length && items[0]!.webkitGetAsEntry) {
      // collect all File objects shallowly; folders are handled via FS Access handle if picked manually
      const files: File[] = [];
      for (const it of Array.from(items)) {
        const f = it.getAsFile?.();
        if (f) files.push(f);
      }
      if (files.length) await ingest(files);
    } else if (ev.dataTransfer?.files) {
      await ingest(ev.dataTransfer.files);
    }
  }

  async function onPickFiles(ev: Event) {
    const t = ev.target as HTMLInputElement;
    if (t.files) await ingest(t.files);
  }

  async function onPickFolder() {
    if (!(window as any).showDirectoryPicker) {
      pushToast({ kind: 'info', message: 'Folder picker not supported — use the file picker or drop files.' });
      return;
    }
    try {
      const handle = await (window as any).showDirectoryPicker();
      await ingest(handle);
    } catch { /* user cancelled */ }
  }
</script>

<div
  class="drop"
  class:active={dragging}
  ondragover={(e) => { e.preventDefault(); dragging = true; }}
  ondragleave={() => (dragging = false)}
  ondrop={onDrop}
  role="region"
  aria-label="Drop a KiCad project"
>
  <h2>Drop a KiCad project here</h2>
  <p>A folder, a <code>.zip</code>, or individual <code>.kicad_pro</code> / <code>.kicad_pcb</code> / <code>.kicad_sch</code> files.</p>
  <div class="row">
    <label class="btn">Pick files
      <input type="file" multiple hidden onchange={onPickFiles} />
    </label>
    <button class="btn" onclick={onPickFolder}>Pick folder</button>
  </div>
</div>

<style>
  .drop {
    display: grid; place-items: center; text-align: center;
    padding: 3rem; border: 2px dashed var(--kv-border); border-radius: 12px;
    color: var(--kv-text-dim);
  }
  .drop.active { border-color: var(--kv-accent); background: var(--kv-surface-2); }
  .row { display: flex; gap: 0.75rem; margin-top: 0.5rem; }
  .btn {
    padding: 0.5rem 0.9rem; border: 1px solid var(--kv-border);
    border-radius: 8px; background: var(--kv-surface); color: var(--kv-text);
    cursor: pointer;
  }
</style>
```

- [ ] **Step 3: Implement viewer entry**

`kicad-viewer/src/routes/viewer/+page.svelte`:
```svelte
<script lang="ts">
  import DropZone from '$lib/ui/DropZone.svelte';
  import Toast from '$lib/ui/Toast.svelte';
  import { project } from '$lib/stores/project';
</script>

<svelte:head><title>Viewer — kicad-viewer</title></svelte:head>

<main class="viewer">
  {#if $project}
    <p>Loaded: {$project.name} ({$project.components.length} components)</p>
  {:else}
    <DropZone />
  {/if}
</main>
<Toast />

<style>
  .viewer { padding: 2rem; min-height: 100dvh; }
</style>
```

- [ ] **Step 4: Smoke-test in browser**

```bash
cd kicad-viewer && npm run dev
```

Open `http://localhost:5173/viewer`, drop `tests/fixtures/*.kicad_*`, verify the "Loaded:" line shows.

- [ ] **Step 5: Commit**

```bash
git add kicad-viewer/
git commit -m "Add project store, DropZone, minimal viewer route"
```

---

## Milestone 4 — UI shell

### Task 15: Shell component (tabs, sidebar frame, inspector frame, footer)

**Files:**
- Create: `kicad-viewer/src/lib/ui/Shell.svelte`
- Create: `kicad-viewer/src/lib/ui/Tabs.svelte`
- Create: `kicad-viewer/src/lib/ui/Footer.svelte`
- Modify: `kicad-viewer/src/routes/viewer/+page.svelte`

- [ ] **Step 1: Implement `Tabs.svelte`**

`kicad-viewer/src/lib/ui/Tabs.svelte`:
```svelte
<script lang="ts">
  interface Props { value: string; onChange: (v: string) => void; }
  const tabs: Array<{ id: string; label: string }> = [
    { id: 'sch', label: 'Schematic' },
    { id: 'pcb', label: 'PCB' },
    { id: '3d',  label: '3D' },
    { id: 'split', label: 'Split ⇄' }
  ];
  let { value, onChange }: Props = $props();
</script>

<div class="tabs" role="tablist">
  {#each tabs as t}
    <button
      role="tab"
      aria-selected={value === t.id}
      class:active={value === t.id}
      onclick={() => onChange(t.id)}
    >{t.label}</button>
  {/each}
</div>

<style>
  .tabs { display: flex; gap: 0.25rem; }
  button {
    background: transparent; border: none; padding: 0.4rem 0.9rem;
    font-size: 0.85rem; color: var(--kv-text-dim);
    border-radius: 6px; cursor: pointer;
  }
  button.active { background: var(--kv-accent); color: white; }
  button:hover:not(.active) { color: var(--kv-text); background: var(--kv-surface-2); }
</style>
```

- [ ] **Step 2: Implement `Footer.svelte`**

`kicad-viewer/src/lib/ui/Footer.svelte`:
```svelte
<script lang="ts">
  interface Props { projectName?: string; cursorMm?: { x: number; y: number } | null; }
  let { projectName = '', cursorMm = null }: Props = $props();
</script>

<footer>
  <span>{projectName}</span>
  <span>{cursorMm ? `${cursorMm.x.toFixed(3)}, ${cursorMm.y.toFixed(3)} mm` : ''}</span>
  <span class="credit">Built by Matthew Austin, 2026</span>
</footer>

<style>
  footer {
    display: grid; grid-template-columns: 1fr auto auto;
    gap: 1rem; padding: 4px 12px;
    border-top: 1px solid var(--kv-border);
    background: var(--kv-surface);
    font-size: 0.72rem; color: var(--kv-text-dim);
  }
  .credit { font-style: italic; }
</style>
```

- [ ] **Step 3: Implement `Shell.svelte`**

`kicad-viewer/src/lib/ui/Shell.svelte`:
```svelte
<script lang="ts">
  import Tabs from './Tabs.svelte';
  import Footer from './Footer.svelte';
  import { project } from '$lib/stores/project';
  import { theme, toggleTheme } from '$lib/stores/theme';

  interface Props {
    tab: string;
    onTabChange: (v: string) => void;
    children: import('svelte').Snippet;
    sidebar?: import('svelte').Snippet;
    inspector?: import('svelte').Snippet;
    cursorMm?: { x: number; y: number } | null;
  }
  let { tab, onTabChange, children, sidebar, inspector, cursorMm }: Props = $props();
</script>

<div class="shell">
  <header class="top">
    <strong>kicad-viewer</strong>
    <span class="project">{$project?.name ?? ''}</span>
    <Tabs value={tab} onChange={onTabChange} />
    <div class="actions">
      <button onclick={toggleTheme}>{$theme === 'dark' ? '☾' : '☀'}</button>
    </div>
  </header>

  <div class="body">
    <aside class="side left">{@render sidebar?.()}</aside>
    <main class="main">{@render children()}</main>
    <aside class="side right">{@render inspector?.()}</aside>
  </div>

  <Footer projectName={$project?.name} cursorMm={cursorMm} />
</div>

<style>
  .shell { display: grid; grid-template-rows: auto 1fr auto; min-height: 100dvh; }
  .top {
    display: grid; grid-template-columns: auto auto 1fr auto;
    align-items: center; gap: 1rem;
    padding: 0.4rem 1rem; border-bottom: 1px solid var(--kv-border);
    background: var(--kv-surface);
  }
  .project { color: var(--kv-text-dim); font-size: 0.85rem; }
  .actions button { background: transparent; border: 1px solid var(--kv-border); border-radius: 6px; padding: 4px 8px; color: var(--kv-text); }
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

- [ ] **Step 4: Wire viewer route to Shell**

`kicad-viewer/src/routes/viewer/+page.svelte`:
```svelte
<script lang="ts">
  import Shell from '$lib/ui/Shell.svelte';
  import DropZone from '$lib/ui/DropZone.svelte';
  import Toast from '$lib/ui/Toast.svelte';
  import { project } from '$lib/stores/project';

  let tab = $state('sch');
</script>

<svelte:head><title>Viewer — kicad-viewer</title></svelte:head>

{#if $project}
  <Shell {tab} onTabChange={(v) => (tab = v)}>
    {#snippet sidebar()}<div class="panel">sidebar ({tab})</div>{/snippet}
    {#snippet inspector()}<div class="panel">inspector</div>{/snippet}
    <div class="stage">render area ({tab})</div>
  </Shell>
{:else}
  <main class="empty"><DropZone /></main>
{/if}

<Toast />

<style>
  .empty { padding: 3rem; min-height: 100dvh; display: grid; place-items: center; background: var(--kv-bg); }
  .panel, .stage { padding: 1rem; color: var(--kv-text-dim); }
  .stage { color: var(--kv-text); }
</style>
```

- [ ] **Step 5: Smoke-test in browser**

Drop fixture, verify the shell appears with tabs switching.

- [ ] **Step 6: Commit**

```bash
git add kicad-viewer/
git commit -m "Add Shell, Tabs, Footer components"
```

---

### Task 16: Inspector with typed views

**Files:**
- Create: `kicad-viewer/src/lib/ui/Inspector.svelte`
- Modify: `kicad-viewer/src/routes/viewer/+page.svelte`
- Create: `kicad-viewer/tests/component/Inspector.test.ts`

- [ ] **Step 1: Write failing component test**

`kicad-viewer/tests/component/Inspector.test.ts`:
```ts
import { render } from '@testing-library/svelte';
import { describe, it, expect, beforeEach } from 'vitest';
import Inspector from '$lib/ui/Inspector.svelte';
import { selection, selectComponent } from '$lib/stores/selection';
import { project } from '$lib/stores/project';
import type { Project } from '$lib/model/project';

const fake: Project = {
  name: 'x', sheets: [], nets: [], pcb: { boundsMm: { x:0,y:0,w:0,h:0 }, layers: [], stackup: [], footprints: [], tracks: [], vias: [], zones: [], drills: [] },
  source: 'raw',
  components: [{
    uuid: 'u1', refdes: 'R1', value: '10k', footprint: 'R_0603',
    sheetUuid: 's1', dnp: false, pins: [],
    mpn: 'ABC', manufacturer: 'Acme', datasheet: 'https://x'
  }]
};

describe('Inspector', () => {
  beforeEach(() => { project.set(fake); selection.set(null); });

  it('shows empty state when no selection', () => {
    const { getByText } = render(Inspector);
    expect(getByText(/Select/i)).toBeTruthy();
  });

  it('renders component details', () => {
    selectComponent({ uuid: 'u1', source: 'sch' });
    const { getByText } = render(Inspector);
    expect(getByText('R1')).toBeTruthy();
    expect(getByText('10k')).toBeTruthy();
    expect(getByText('Acme')).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run — fails**

- [ ] **Step 3: Implement**

`kicad-viewer/src/lib/ui/Inspector.svelte`:
```svelte
<script lang="ts">
  import { selection } from '$lib/stores/selection';
  import { componentsByUuid, sheetsByUuid, netsByName } from '$lib/stores/project';
</script>

{#if !$selection}
  <p class="empty">Select a component or net</p>
{:else if $selection.kind === 'component'}
  {@const c = $componentsByUuid.get($selection.uuid)}
  {#if c}
    <header class="hdr"><h3>{c.refdes}</h3><span>{c.value}</span></header>
    <dl>
      <dt>Footprint</dt><dd>{c.footprint}</dd>
      {#if c.mpn}<dt>MPN</dt><dd>{c.mpn}</dd>{/if}
      {#if c.manufacturer}<dt>Mfr</dt><dd>{c.manufacturer}</dd>{/if}
      {#if c.datasheet}<dt>Datasheet</dt><dd><a href={c.datasheet} target="_blank" rel="noopener">link</a></dd>{/if}
      <dt>DNP</dt><dd>{c.dnp ? 'yes' : 'no'}</dd>
    </dl>
    {#if c.pins.length}
      <h4>Pins</h4>
      <table>
        <thead><tr><th>#</th><th>Name</th><th>Net</th></tr></thead>
        <tbody>
          {#each c.pins as p}
            <tr><td>{p.number}</td><td>{p.name}</td><td>{p.netName ?? '-'}</td></tr>
          {/each}
        </tbody>
      </table>
    {/if}
  {:else}
    <p class="empty">Component not found</p>
  {/if}
{:else if $selection.kind === 'net'}
  {@const n = $netsByName.get($selection.name)}
  <header class="hdr"><h3>{$selection.name}</h3><span>{n?.refdesPins.length ?? 0} pins</span></header>
  {#if n}
    <ul>
      {#each n.refdesPins as rp}<li>{rp.refdes}.{rp.pin}</li>{/each}
    </ul>
  {/if}
{:else if $selection.kind === 'sheet'}
  {@const s = $sheetsByUuid.get($selection.uuid)}
  <header class="hdr"><h3>{s?.name ?? ''}</h3></header>
  {#if s}<dl><dt>Path</dt><dd>{s.path.join(' / ')}</dd><dt>Components</dt><dd>{s.componentUuids.length}</dd></dl>{/if}
{/if}

<style>
  :global(.side.right) { padding: 0.75rem; font-size: 0.85rem; }
  .empty { color: var(--kv-text-dim); }
  .hdr { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 0.5rem; }
  .hdr h3 { margin: 0; font-size: 1rem; }
  dl { display: grid; grid-template-columns: auto 1fr; gap: 0.25rem 0.75rem; margin: 0 0 0.5rem; }
  dt { color: var(--kv-text-dim); }
  dd { margin: 0; overflow-wrap: anywhere; }
  table { width: 100%; font-size: 0.78rem; border-collapse: collapse; }
  th, td { text-align: left; padding: 2px 4px; border-bottom: 1px solid var(--kv-border); }
</style>
```

- [ ] **Step 4: Wire into viewer route** — replace `{#snippet inspector()}<div class="panel">inspector</div>{/snippet}` with `<Inspector />` rendered inside the snippet.

```svelte
{#snippet inspector()}<Inspector />{/snippet}
```

- [ ] **Step 5: Run tests**

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add kicad-viewer/
git commit -m "Add Inspector with typed views for component/net/sheet selection"
```

---

### Task 17: Keyboard shortcuts

**Files:**
- Create: `kicad-viewer/src/lib/keys.ts`
- Modify: `kicad-viewer/src/routes/viewer/+page.svelte`

- [ ] **Step 1: Implement key dispatcher**

`kicad-viewer/src/lib/keys.ts`:
```ts
import { clearSelection } from '$lib/stores/selection';

export type KeyHandler = (e: KeyboardEvent) => void;

export function installKeyboardShortcuts(args: {
  setTab: (t: string) => void;
  onSearch: () => void;
  onFit: () => void;
  onPrevSheet: () => void;
  onNextSheet: () => void;
  onFocusLayers: () => void;
}): () => void {
  const handler = (e: KeyboardEvent) => {
    const target = e.target as HTMLElement;
    if (['INPUT', 'TEXTAREA'].includes(target.tagName)) return;
    switch (e.key) {
      case '1': args.setTab('sch');   break;
      case '2': args.setTab('pcb');   break;
      case '3': args.setTab('3d');    break;
      case '4': args.setTab('split'); break;
      case '/': e.preventDefault(); args.onSearch(); break;
      case 'Escape': clearSelection(); break;
      case 'f': args.onFit(); break;
      case '[': args.onPrevSheet(); break;
      case ']': args.onNextSheet(); break;
      case 'l': args.onFocusLayers(); break;
    }
  };
  window.addEventListener('keydown', handler);
  return () => window.removeEventListener('keydown', handler);
}
```

- [ ] **Step 2: Wire into viewer page `onMount`**

Add to `src/routes/viewer/+page.svelte` `<script>`:
```ts
  import { onMount } from 'svelte';
  import { installKeyboardShortcuts } from '$lib/keys';

  let searchOpen = $state(false);
  let fitRequested = $state(0);

  onMount(() =>
    installKeyboardShortcuts({
      setTab: (t) => (tab = t),
      onSearch: () => (searchOpen = true),
      onFit: () => fitRequested++,
      onPrevSheet: () => {/* bind in sch view */},
      onNextSheet: () => {/* bind in sch view */},
      onFocusLayers: () => {/* bind in pcb view */}
    })
  );
```

- [ ] **Step 3: Smoke-test in browser: press 1/2/3/4 to switch tabs**

- [ ] **Step 4: Commit**

```bash
git add kicad-viewer/
git commit -m "Add keyboard shortcut dispatcher"
```

---

## Milestone 5 — Schematic view

### Task 18: SchematicView — render a sheet to SVG, pan/zoom

**Files:**
- Create: `kicad-viewer/src/lib/sch/render.ts`
- Create: `kicad-viewer/src/lib/views/SchematicView.svelte`
- Create: `kicad-viewer/tests/unit/sch-render.test.ts`

- [ ] **Step 1: Unit test for the pure render function**

`kicad-viewer/tests/unit/sch-render.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { buildSheetSvg } from '$lib/sch/render';
import type { Project, Sheet } from '$lib/model/project';

describe('sch render', () => {
  it('emits an svg string with a viewBox for an empty sheet', () => {
    const sheet: Sheet = { uuid: 's', name: 'root', path: ['root'], parent: null, componentUuids: [], boundsMm: { x:0,y:0,w:297,h:210 } };
    const project: Project = { name: 'x', sheets: [sheet], components: [], nets: [], pcb: { boundsMm: { x:0,y:0,w:0,h:0 }, layers: [], stackup: [], footprints: [], tracks: [], vias: [], zones: [], drills: [] }, source: 'raw' };
    const svg = buildSheetSvg(project, sheet);
    expect(svg).toMatch(/<svg/);
    expect(svg).toMatch(/viewBox="0 0 297 210"/);
  });
});
```

- [ ] **Step 2: Implement a minimal render that draws wires, symbol boxes, labels**

`kicad-viewer/src/lib/sch/render.ts`:
```ts
import type { Project, Sheet } from '$lib/model/project';

export function buildSheetSvg(project: Project, sheet: Sheet): string {
  const { x, y, w, h } = sheet.boundsMm;
  // Render components placed on this sheet as simple labelled boxes (stage-1).
  // Later iterations populate wires/symbols from the parser.
  const parts = project.components
    .filter((c) => c.sheetUuid === sheet.uuid)
    .map((c, i) => {
      const cx = (i % 8) * 30 + 20, cy = Math.floor(i / 8) * 20 + 20;
      return `<g data-refdes="${c.refdes}" data-uuid="${c.uuid}">
        <rect x="${cx}" y="${cy}" width="20" height="10" fill="var(--kv-surface-2)" stroke="currentColor"/>
        <text x="${cx + 10}" y="${cy + 6}" text-anchor="middle" font-size="4" fill="currentColor">${c.refdes}</text>
      </g>`;
    }).join('');
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${x} ${y} ${w} ${h}" preserveAspectRatio="xMidYMid meet" style="color: var(--kv-text); width: 100%; height: 100%">${parts}</svg>`;
}
```

Note: this is a placeholder renderer — it draws a grid of refdes boxes so cross-probing
can be verified. Real wire/symbol rendering is upgraded in Task 19 using the vendored
parser's `KicadSch` iterables.

- [ ] **Step 3: Implement the Svelte component with pan/zoom**

`kicad-viewer/src/lib/views/SchematicView.svelte`:
```svelte
<script lang="ts">
  import { project, sheetsByUuid } from '$lib/stores/project';
  import { selectComponent, selection } from '$lib/stores/selection';
  import { buildSheetSvg } from '$lib/sch/render';

  let { activeSheetUuid }: { activeSheetUuid: string | null } = $props();

  let viewport = $state({ x: 0, y: 0, scale: 1 });
  let host: HTMLDivElement | undefined;

  function onWheel(e: WheelEvent) {
    e.preventDefault();
    const delta = -e.deltaY * 0.001;
    const factor = Math.exp(delta);
    const rect = host!.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    viewport = {
      x: mx - (mx - viewport.x) * factor,
      y: my - (my - viewport.y) * factor,
      scale: viewport.scale * factor
    };
  }
  let dragging = false, lastX = 0, lastY = 0;
  function onDown(e: PointerEvent) {
    if (e.button !== 0) return;
    const t = e.target as Element;
    if (t.closest('[data-refdes]')) return;  // clicks on symbols should select, not pan
    dragging = true; lastX = e.clientX; lastY = e.clientY;
    (e.target as Element).setPointerCapture(e.pointerId);
  }
  function onMove(e: PointerEvent) {
    if (!dragging) return;
    viewport = { ...viewport, x: viewport.x + (e.clientX - lastX), y: viewport.y + (e.clientY - lastY) };
    lastX = e.clientX; lastY = e.clientY;
  }
  function onUp() { dragging = false; }

  function onClick(e: MouseEvent) {
    const g = (e.target as Element).closest('[data-refdes]');
    if (!g) return;
    const uuid = g.getAttribute('data-uuid');
    if (uuid) selectComponent({ uuid, source: 'sch' });
  }

  let svg = $derived.by(() => {
    if (!$project || !activeSheetUuid) return '';
    const s = $sheetsByUuid.get(activeSheetUuid);
    return s ? buildSheetSvg($project, s) : '';
  });

  let highlightedRefdes = $derived.by(() => {
    if ($selection?.kind !== 'component') return null;
    const c = $project?.components.find((c) => c.uuid === $selection!.uuid);
    return c?.refdes ?? null;
  });
</script>

<div
  class="stage"
  bind:this={host}
  onwheel={onWheel}
  onpointerdown={onDown}
  onpointermove={onMove}
  onpointerup={onUp}
  onclick={onClick}
  role="img"
  aria-label="Schematic view"
>
  <div class="svg" style="transform: translate({viewport.x}px, {viewport.y}px) scale({viewport.scale});">
    {@html svg}
  </div>
  {#if highlightedRefdes}
    <style>[data-refdes="{highlightedRefdes}"] rect { stroke: var(--kv-accent); stroke-width: 0.8; }</style>
  {/if}
</div>

<style>
  .stage { position: relative; overflow: hidden; width: 100%; height: 100%; background: var(--kv-render-bg); cursor: grab; touch-action: none; }
  .svg { position: absolute; top: 0; left: 0; transform-origin: 0 0; width: 800px; height: 600px; }
</style>
```

- [ ] **Step 4: Wire into viewer page**

Replace the placeholder stage in `src/routes/viewer/+page.svelte`:
```svelte
  import SchematicView from '$lib/views/SchematicView.svelte';
  let activeSheet = $derived.by(() => $project?.sheets[0]?.uuid ?? null);
  ...
  {#if tab === 'sch'}
    <SchematicView activeSheetUuid={activeSheet} />
  {:else}
    <div class="stage">render area ({tab})</div>
  {/if}
```

- [ ] **Step 5: Run & smoke-test** — load fixture, click a refdes box, verify inspector shows details.

- [ ] **Step 6: Commit**

```bash
git add kicad-viewer/
git commit -m "Add SchematicView with stage-1 symbol boxes, pan/zoom, click-to-select"
```

---

### Task 19: Upgrade SchematicView to render real wires, symbols, labels

**Files:**
- Modify: `kicad-viewer/src/lib/sch/render.ts`

- [ ] **Step 1: Walk parser output to emit SVG primitives**

Extend `buildSheetSvg` to iterate the vendored `KicadSch`:
- wires: each segment → `<line data-net="NAME" stroke="currentColor" stroke-width="0.15">`
- labels (local/global/hierarchical): `<text>` at label position
- symbols: `<g data-refdes="...">` containing the symbol's body graphic (rectangles, pins as short lines)
- sheet symbols: `<g data-sheet-uuid="..."><rect>` with sheet name text

You will need to parse the sch text in `buildSheetSvg` (via the vendored parser) since
today the function only receives our reduced model. Two choices:
(a) pass the raw sch text into `Project.sheets[i].rawSch?: string` (extend the model + adapter), or
(b) move the render step to take the vendored `KicadSch` directly.

Pick (a) to keep the renderer free of vendor types at the boundary.

- [ ] **Step 2: Extend `Sheet` type and adapter to pass `rawSch`**

In `src/lib/model/project.ts`: add `rawSch?: string;` to `Sheet`.
In `src/lib/adapter/adapter.ts` `buildSheets`: populate `rawSch` with the file text.

- [ ] **Step 3: In `render.ts` parse and emit SVG**

Add at top:
```ts
import { KicadSch } from '$lib/parser/schematic';
```

Then walk: wires, junctions, labels, symbols — emitting minimal SVG. When in doubt,
read `references/kicanvas/src/kicad/schematic.ts` to see what the parser exposes, but
keep our emitted SVG simple (line + text + groups only).

- [ ] **Step 4: Visually verify in browser against KiCad's schematic for pic_programmer**

Accept that v1's visual fidelity is lower than KiCad's — we render skeletons, not full
symbol art. Refine in follow-ups.

- [ ] **Step 5: Commit (possibly in multiple commits as you iterate)**

```bash
git add kicad-viewer/
git commit -m "Upgrade schematic render to draw wires, labels, symbol skeletons"
```

---

### Task 20: Sheet tree + breadcrumb + navigation

**Files:**
- Create: `kicad-viewer/src/lib/ui/SheetTree.svelte`
- Create: `kicad-viewer/src/lib/ui/Breadcrumb.svelte`
- Modify: `kicad-viewer/src/routes/viewer/+page.svelte`

- [ ] **Step 1: Implement `SheetTree.svelte`**

```svelte
<script lang="ts">
  import { project } from '$lib/stores/project';
  import type { Sheet } from '$lib/model/project';

  interface Props { activeUuid: string | null; onSelect: (uuid: string) => void; }
  let { activeUuid, onSelect }: Props = $props();

  let tree = $derived.by(() => {
    if (!$project) return [] as Array<{ sheet: Sheet; depth: number }>;
    const roots = $project.sheets.filter((s) => s.parent === null);
    const out: Array<{ sheet: Sheet; depth: number }> = [];
    const walk = (s: Sheet, depth: number) => {
      out.push({ sheet: s, depth });
      for (const c of $project!.sheets.filter((x) => x.parent === s.uuid)) walk(c, depth + 1);
    };
    roots.forEach((r) => walk(r, 0));
    return out;
  });
</script>

<div class="tree">
  <h4>Sheets</h4>
  {#each tree as row}
    <button
      class:active={row.sheet.uuid === activeUuid}
      style="padding-left: {row.depth * 12 + 8}px"
      onclick={() => onSelect(row.sheet.uuid)}
    >{row.sheet.name}</button>
  {/each}
</div>

<style>
  .tree { font-size: 0.82rem; }
  h4 { font-size: 0.7rem; letter-spacing: 0.08em; color: var(--kv-text-dim); margin: 0.5rem 0.75rem; text-transform: uppercase; }
  button { display: block; width: 100%; text-align: left; background: transparent; border: none; padding: 4px 8px; color: var(--kv-text); }
  button.active { background: var(--kv-surface-2); color: var(--kv-accent); }
  button:hover:not(.active) { background: var(--kv-surface-2); }
</style>
```

- [ ] **Step 2: Implement `Breadcrumb.svelte`**

```svelte
<script lang="ts">
  import type { Sheet } from '$lib/model/project';
  interface Props { sheet: Sheet; onSelect: (uuid: string) => void; }
  let { sheet, onSelect }: Props = $props();
</script>

<nav class="crumb">
  {#each sheet.path as p, i}
    <span>{p}</span>
    {#if i < sheet.path.length - 1}<span class="sep">›</span>{/if}
  {/each}
</nav>

<style>
  .crumb { position: absolute; top: 8px; left: 10px; background: var(--kv-surface); border: 1px solid var(--kv-border); border-radius: 6px; padding: 2px 8px; font-size: 0.75rem; display: flex; gap: 0.25rem; }
  .sep { color: var(--kv-text-dim); }
</style>
```

- [ ] **Step 3: Wire sheet tree into shell sidebar when tab = sch**

In viewer route:
```svelte
  let activeSheet = $state<string | null>(null);
  $effect(() => {
    if (!activeSheet && $project) activeSheet = $project.sheets[0]?.uuid ?? null;
  });
  ...
  {#snippet sidebar()}
    {#if tab === 'sch'}
      <SheetTree activeUuid={activeSheet} onSelect={(u) => (activeSheet = u)} />
    {:else}
      <div class="panel">({tab} sidebar)</div>
    {/if}
  {/snippet}
```

- [ ] **Step 4: Double-click sheet symbol to dive in**

In `SchematicView.svelte` click handler:
```ts
  const sheetGroup = (e.target as Element).closest('[data-sheet-uuid]');
  if (sheetGroup && e.detail === 2) {  // double-click
    const uuid = sheetGroup.getAttribute('data-sheet-uuid');
    if (uuid) dispatchNavigate(uuid);
  }
```

Expose `onNavigateSheet` as a component prop; handle in the viewer route to update `activeSheet`.

- [ ] **Step 5: Wire `[` / `]` shortcuts** via the `onPrevSheet`/`onNextSheet` handlers left in Task 17.

- [ ] **Step 6: Commit**

```bash
git add kicad-viewer/
git commit -m "Add SheetTree, breadcrumb, hierarchy navigation"
```

---

### Task 21: Search bar for refdes/net

**Files:**
- Create: `kicad-viewer/src/lib/ui/SearchBar.svelte`
- Modify: `kicad-viewer/src/routes/viewer/+page.svelte`

- [ ] **Step 1: Implement SearchBar**

```svelte
<script lang="ts">
  import { componentsByRefdes, netsByName } from '$lib/stores/project';
  import { selectComponent, selectNet } from '$lib/stores/selection';

  interface Props { open: boolean; onClose: () => void; }
  let { open, onClose }: Props = $props();

  let query = $state('');
  let results = $derived.by(() => {
    if (!query.trim()) return [];
    const q = query.toUpperCase();
    const comp = [...$componentsByRefdes.values()]
      .filter((c) => c.refdes.includes(q) || c.value.toUpperCase().includes(q)).slice(0, 8);
    const nets = [...$netsByName.values()]
      .filter((n) => n.name.toUpperCase().includes(q)).slice(0, 8);
    return [...comp.map((c) => ({ k: 'c' as const, c })), ...nets.map((n) => ({ k: 'n' as const, n }))];
  });

  function pick(r: typeof results extends ReadonlyArray<infer T> ? T : never) {
    if (r.k === 'c') selectComponent({ uuid: r.c.uuid, source: 'search' });
    else selectNet({ name: r.n.name, source: 'search' });
    onClose(); query = '';
  }
</script>

{#if open}
  <div class="overlay" onclick={onClose} role="button" tabindex="-1">
    <div class="box" onclick={(e) => e.stopPropagation()}>
      <input
        placeholder="Search refdes or net..."
        bind:value={query}
        autofocus
        onkeydown={(e) => { if (e.key === 'Escape') onClose(); }}
      />
      <ul>
        {#each results as r}
          <li onclick={() => pick(r)}>
            {#if r.k === 'c'}<strong>{r.c.refdes}</strong> {r.c.value}{:else}<em>{r.n.name}</em>{/if}
          </li>
        {/each}
      </ul>
    </div>
  </div>
{/if}

<style>
  .overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: grid; place-items: start center; padding-top: 15vh; z-index: 50; }
  .box { width: 520px; background: var(--kv-surface); border: 1px solid var(--kv-border); border-radius: 10px; padding: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.3); }
  input { width: 100%; padding: 8px 10px; font-size: 1rem; border: 1px solid var(--kv-border); border-radius: 6px; background: var(--kv-bg); color: var(--kv-text); }
  ul { list-style: none; padding: 0; margin: 8px 0 0; max-height: 280px; overflow: auto; }
  li { padding: 6px 8px; border-radius: 4px; cursor: pointer; }
  li:hover { background: var(--kv-surface-2); }
</style>
```

- [ ] **Step 2: Wire into viewer route**

```svelte
  import SearchBar from '$lib/ui/SearchBar.svelte';
  ...
  <SearchBar open={searchOpen} onClose={() => (searchOpen = false)} />
```

Pressing `/` toggles `searchOpen` via the existing keyboard handler.

- [ ] **Step 3: Smoke-test** — `/` → type "R1" → click result → schematic scrolls to component (via selection + next task's nav integration).

- [ ] **Step 4: Commit**

```bash
git add kicad-viewer/
git commit -m "Add search bar for refdes/net"
```

---

### Task 22: Schematic reaction to external selection (cross-probe in)

**Files:**
- Modify: `kicad-viewer/src/lib/views/SchematicView.svelte`
- Create: `kicad-viewer/tests/component/SchematicView-xprobe.test.ts`

- [ ] **Step 1: Subscribe to `selection` and pan/scroll active sheet to the highlighted symbol when source ≠ 'sch'**

Add in `SchematicView.svelte` `<script>`:
```ts
  import { selection } from '$lib/stores/selection';
  import { componentsByUuid } from '$lib/stores/project';

  $effect(() => {
    const s = $selection;
    if (!s || s.source === 'sch' || s.kind !== 'component') return;
    const c = $componentsByUuid.get(s.uuid);
    if (!c || c.sheetUuid !== activeSheetUuid) {
      // viewer-level navigation will switch sheet; once active, this effect re-fires
      return;
    }
    // find element, compute center, set viewport to centre it
    const el = host?.querySelector(`[data-uuid="${s.uuid}"]`);
    if (!el) return;
    const bbox = (el as SVGGraphicsElement).getBoundingClientRect();
    const stageBox = host!.getBoundingClientRect();
    const dx = stageBox.width / 2 - (bbox.left + bbox.width / 2 - stageBox.left);
    const dy = stageBox.height / 2 - (bbox.top + bbox.height / 2 - stageBox.top);
    viewport = { ...viewport, x: viewport.x + dx, y: viewport.y + dy };
  });
```

- [ ] **Step 2: Test with a mock**

`kicad-viewer/tests/component/SchematicView-xprobe.test.ts`:
```ts
import { render } from '@testing-library/svelte';
import { describe, it, expect, beforeEach } from 'vitest';
import SchematicView from '$lib/views/SchematicView.svelte';
import { project } from '$lib/stores/project';
import { selection, selectComponent } from '$lib/stores/selection';

const p = {
  name: 'x', source: 'raw' as const, nets: [], pcb: { boundsMm: { x:0,y:0,w:0,h:0 }, layers: [], stackup: [], footprints: [], tracks: [], vias: [], zones: [], drills: [] },
  sheets: [{ uuid: 's0', name: 'root', path: ['root'], parent: null, componentUuids: ['u1'], boundsMm: { x:0,y:0,w:100,h:100 } }],
  components: [{ uuid: 'u1', refdes: 'R1', value: '10k', footprint: 'R', sheetUuid: 's0', dnp: false, pins: [] }]
};

describe('SchematicView cross-probe', () => {
  beforeEach(() => { project.set(p as any); selection.set(null); });

  it('highlights the selected component', async () => {
    const { container } = render(SchematicView, { activeSheetUuid: 's0' });
    selectComponent({ uuid: 'u1', source: 'pcb' });
    // rough assertion: our highlight <style> block exists
    await new Promise((r) => setTimeout(r, 10));
    expect(container.innerHTML).toContain('data-refdes="R1"');
  });
});
```

- [ ] **Step 3: Run**

Expected: PASS (assertion is soft; stronger checks added later).

- [ ] **Step 4: Commit**

```bash
git add kicad-viewer/
git commit -m "Schematic view reacts to external selection"
```

---

## Milestone 6 — PCB view

### Task 23: R-tree geometry helper

**Files:**
- Create: `kicad-viewer/src/lib/geom/rtree.ts`
- Create: `kicad-viewer/tests/unit/rtree.test.ts`

- [ ] **Step 1: Install `flatbush`**

```bash
cd kicad-viewer && npm install flatbush
```

- [ ] **Step 2: Write test**

`kicad-viewer/tests/unit/rtree.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { buildRtree, hitPoint } from '$lib/geom/rtree';

describe('rtree', () => {
  it('finds items containing a point', () => {
    const idx = buildRtree([
      { id: 'A', bbox: { x: 0, y: 0, w: 10, h: 10 } },
      { id: 'B', bbox: { x: 20, y: 20, w: 5, h: 5 } }
    ]);
    expect(hitPoint(idx, 5, 5)).toContain('A');
    expect(hitPoint(idx, 25, 25)).toContain('B');
    expect(hitPoint(idx, 50, 50)).toHaveLength(0);
  });
});
```

- [ ] **Step 3: Implement**

`kicad-viewer/src/lib/geom/rtree.ts`:
```ts
import Flatbush from 'flatbush';

export interface BboxItem { id: string; bbox: { x: number; y: number; w: number; h: number }; }

export interface RtreeIndex {
  fb: Flatbush;
  ids: string[];
}

export function buildRtree(items: BboxItem[]): RtreeIndex {
  if (items.length === 0) {
    const fb = new Flatbush(1);
    fb.add(0, 0, 0, 0);
    fb.finish();
    return { fb, ids: [] };
  }
  const fb = new Flatbush(items.length);
  for (const it of items) fb.add(it.bbox.x, it.bbox.y, it.bbox.x + it.bbox.w, it.bbox.y + it.bbox.h);
  fb.finish();
  return { fb, ids: items.map((i) => i.id) };
}

export function hitPoint(idx: RtreeIndex, x: number, y: number): string[] {
  if (idx.ids.length === 0) return [];
  const hits = idx.fb.search(x, y, x, y);
  return hits.map((i) => idx.ids[i]!);
}
```

- [ ] **Step 4: Run — passes**

- [ ] **Step 5: Commit**

```bash
git add kicad-viewer/
git commit -m "Add flatbush-based R-tree for hit-testing"
```

---

### Task 24: PCB scene builder (pure data)

**Files:**
- Create: `kicad-viewer/src/lib/pcb/scene.ts`
- Create: `kicad-viewer/tests/unit/pcb-scene.test.ts`

- [ ] **Step 1: Write test**

`kicad-viewer/tests/unit/pcb-scene.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { buildPcbScene } from '$lib/pcb/scene';
import type { Project } from '$lib/model/project';

const baseProject = (): Project => ({
  name: 'x', sheets: [], components: [], nets: [], source: 'raw',
  pcb: {
    boundsMm: { x: 0, y: 0, w: 50, h: 50 },
    layers: [
      { id: 'F.Cu', name: 'F.Cu', type: 'F.Cu', defaultColor: '#c83434' },
      { id: 'Edge.Cuts', name: 'Edge.Cuts', type: 'Edge.Cuts', defaultColor: '#f2eda1' }
    ],
    stackup: [],
    footprints: [{
      uuid: 'u1', refdes: 'R1', position: { x: 10, y: 10 }, rotationDeg: 0, side: 'top',
      bboxMm: { x: 8, y: 9, w: 4, h: 2 }, pads: [], graphics: []
    }],
    tracks: [{ layerId: 'F.Cu', a: { x:0, y:0 }, b: { x:5, y:0 }, widthMm: 0.25, netName: 'VCC' }],
    vias: [], zones: [], drills: []
  }
});

describe('pcb scene', () => {
  it('splits primitives by layer id', () => {
    const scene = buildPcbScene(baseProject());
    expect(scene.byLayer.get('F.Cu')?.tracks.length).toBe(1);
    expect(scene.footprintIndex.ids).toContain('u1');
  });
});
```

- [ ] **Step 2: Implement**

`kicad-viewer/src/lib/pcb/scene.ts`:
```ts
import type { Project, FootprintGeom, TrackSeg, Via, Zone } from '$lib/model/project';
import { buildRtree, type RtreeIndex } from '$lib/geom/rtree';

export interface PcbScene {
  boundsMm: Project['pcb']['boundsMm'];
  byLayer: Map<string, LayerBuckets>;
  footprintIndex: RtreeIndex;
  footprints: FootprintGeom[];
}

export interface LayerBuckets {
  tracks: TrackSeg[]; vias: Via[]; zones: Zone[]; graphics: { from: FootprintGeom; idx: number }[];
}

export function buildPcbScene(project: Project): PcbScene {
  const byLayer = new Map<string, LayerBuckets>();
  const ensure = (id: string) => {
    const b = byLayer.get(id); if (b) return b;
    const n: LayerBuckets = { tracks: [], vias: [], zones: [], graphics: [] };
    byLayer.set(id, n); return n;
  };

  for (const t of project.pcb.tracks)        ensure(t.layerId).tracks.push(t);
  for (const v of project.pcb.vias)          ensure(v.layerFrom).vias.push(v);  // indexed from-layer
  for (const z of project.pcb.zones)         ensure(z.layerId).zones.push(z);
  for (const f of project.pcb.footprints)    f.graphics.forEach((g, i) => ensure(g.layerId).graphics.push({ from: f, idx: i }));

  const footprintIndex = buildRtree(
    project.pcb.footprints.map((f) => ({ id: f.uuid, bbox: f.bboxMm }))
  );
  return { boundsMm: project.pcb.boundsMm, byLayer, footprintIndex, footprints: project.pcb.footprints };
}
```

- [ ] **Step 3: Run — passes**

- [ ] **Step 4: Commit**

```bash
git add kicad-viewer/
git commit -m "Add PCB scene builder with layer bucketing and footprint R-tree"
```

---

### Task 25: Layers store + LayerPanel

**Files:**
- Create: `kicad-viewer/src/lib/stores/layers.ts`
- Create: `kicad-viewer/src/lib/ui/LayerPanel.svelte`

- [ ] **Step 1: Implement store**

`kicad-viewer/src/lib/stores/layers.ts`:
```ts
import { writable, derived } from 'svelte/store';
import { project } from '$lib/stores/project';

export const layerVisibility = writable<Map<string, boolean>>(new Map());

// Seed visibility map each time project changes
project.subscribe((p) => {
  if (!p) { layerVisibility.set(new Map()); return; }
  const m = new Map<string, boolean>();
  for (const l of p.pcb.layers) {
    // Default: show copper, silk, mask, edge-cuts; hide paste/courtyard/fab
    const on = ['F.Cu','B.Cu','In.Cu','F.SilkS','B.SilkS','F.Mask','B.Mask','Edge.Cuts'].includes(l.type);
    m.set(l.id, on);
  }
  layerVisibility.set(m);
});

export const layers = derived(project, (p) => p?.pcb.layers ?? []);

export function toggleLayer(id: string) {
  layerVisibility.update((m) => { m.set(id, !m.get(id)); return new Map(m); });
}
```

- [ ] **Step 2: Implement panel**

`kicad-viewer/src/lib/ui/LayerPanel.svelte`:
```svelte
<script lang="ts">
  import { layers, layerVisibility, toggleLayer } from '$lib/stores/layers';
</script>

<div class="wrap">
  <h4>Layers</h4>
  {#each $layers as l}
    <label>
      <input type="checkbox" checked={$layerVisibility.get(l.id) ?? false} onchange={() => toggleLayer(l.id)} />
      <span class="sw" style="background: {l.defaultColor}"></span>
      <span>{l.name}</span>
    </label>
  {/each}
</div>

<style>
  .wrap { font-size: 0.78rem; }
  h4 { font-size: 0.7rem; letter-spacing: 0.08em; color: var(--kv-text-dim); margin: 0.5rem 0.75rem; text-transform: uppercase; }
  label { display: flex; align-items: center; gap: 0.5rem; padding: 3px 10px; cursor: pointer; user-select: none; }
  label:hover { background: var(--kv-surface-2); }
  .sw { width: 10px; height: 10px; border-radius: 2px; border: 1px solid var(--kv-border); }
</style>
```

- [ ] **Step 3: Wire into shell sidebar when tab = pcb**

In viewer route, extend the `sidebar` snippet:
```svelte
  {:else if tab === 'pcb'}
    <LayerPanel />
```

- [ ] **Step 4: Commit**

```bash
git add kicad-viewer/
git commit -m "Add layer visibility store and LayerPanel"
```

---

### Task 26: PCB renderer (Canvas2D)

**Files:**
- Create: `kicad-viewer/src/lib/pcb/render.ts`
- Create: `kicad-viewer/src/lib/views/PcbView.svelte`

- [ ] **Step 1: Implement pure renderer against a canvas context**

`kicad-viewer/src/lib/pcb/render.ts`:
```ts
import type { PcbScene } from './scene';
import type { LayerInfo } from '$lib/model/project';

export interface Viewport { x: number; y: number; scale: number; }

export function drawPcb(
  ctx: CanvasRenderingContext2D,
  scene: PcbScene,
  layers: LayerInfo[],
  visible: Map<string, boolean>,
  viewport: Viewport,
  selectedFootprint?: string | null
) {
  const { width, height } = ctx.canvas;
  ctx.clearRect(0, 0, width, height);
  ctx.save();
  ctx.translate(viewport.x, viewport.y);
  ctx.scale(viewport.scale, viewport.scale);

  // Edge-cuts first as reference outline
  const edge = layers.find((l) => l.id === 'Edge.Cuts');
  if (edge && visible.get(edge.id)) drawLayerStroke(ctx, scene, edge);

  // Back-to-front order: B.* → In.Cu → F.*. Keep simple for v1.
  const orderIds = ['B.Cu','B.SilkS','B.Mask','B.Fab','B.CrtYd','B.Paste','In.Cu','F.Cu','F.SilkS','F.Mask','F.Fab','F.CrtYd','F.Paste'];
  for (const id of orderIds) {
    const l = layers.find((x) => x.id === id);
    if (!l || !visible.get(l.id)) continue;
    drawLayerStroke(ctx, scene, l);
  }

  // Footprint bounding boxes (debug) + selection overlay
  for (const fp of scene.footprints) {
    if (fp.uuid === selectedFootprint) {
      ctx.strokeStyle = '#6aa6ff'; ctx.lineWidth = 0.15;
      ctx.strokeRect(fp.bboxMm.x, fp.bboxMm.y, fp.bboxMm.w, fp.bboxMm.h);
    }
  }

  ctx.restore();
}

function drawLayerStroke(ctx: CanvasRenderingContext2D, scene: PcbScene, layer: LayerInfo) {
  const buckets = scene.byLayer.get(layer.id);
  if (!buckets) return;
  ctx.strokeStyle = layer.defaultColor; ctx.fillStyle = layer.defaultColor;
  for (const t of buckets.tracks) {
    ctx.lineWidth = t.widthMm;
    ctx.beginPath(); ctx.moveTo(t.a.x, t.a.y); ctx.lineTo(t.b.x, t.b.y); ctx.stroke();
  }
  for (const z of buckets.zones) {
    if (!z.polygon.length) continue;
    ctx.beginPath();
    ctx.moveTo(z.polygon[0]!.x, z.polygon[0]!.y);
    for (let i = 1; i < z.polygon.length; i++) ctx.lineTo(z.polygon[i]!.x, z.polygon[i]!.y);
    ctx.closePath(); ctx.fill();
  }
  for (const v of buckets.vias) {
    ctx.beginPath(); ctx.arc(v.position.x, v.position.y, v.diameterMm / 2, 0, Math.PI * 2); ctx.fill();
  }
  for (const g of buckets.graphics) {
    drawGraphic(ctx, g.from.graphics[g.idx]!, g.from.position, g.from.rotationDeg);
  }
}

function drawGraphic(ctx: CanvasRenderingContext2D, g: import('$lib/model/project').Graphic, at: { x:number;y:number }, rotDeg: number) {
  ctx.save();
  ctx.translate(at.x, at.y);
  ctx.rotate(rotDeg * Math.PI / 180);
  const s = g.geom;
  if (s.kind === 'line') {
    ctx.lineWidth = s.widthMm;
    ctx.beginPath(); ctx.moveTo(s.a.x, s.a.y); ctx.lineTo(s.b.x, s.b.y); ctx.stroke();
  } else if (s.kind === 'polygon') {
    ctx.beginPath();
    s.points.forEach((p, i) => i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y));
    ctx.closePath();
    if (s.filled) ctx.fill(); else ctx.stroke();
  } else if (s.kind === 'arc') {
    ctx.lineWidth = s.widthMm;
    ctx.beginPath();
    ctx.arc(s.center.x, s.center.y, s.radiusMm, s.startDeg * Math.PI/180, s.endDeg * Math.PI/180);
    ctx.stroke();
  }
  ctx.restore();
}
```

- [ ] **Step 2: Implement the Svelte view**

`kicad-viewer/src/lib/views/PcbView.svelte`:
```svelte
<script lang="ts">
  import { project } from '$lib/stores/project';
  import { layerVisibility, layers } from '$lib/stores/layers';
  import { selection, selectComponent } from '$lib/stores/selection';
  import { buildPcbScene } from '$lib/pcb/scene';
  import { drawPcb, type Viewport } from '$lib/pcb/render';
  import { hitPoint } from '$lib/geom/rtree';

  let host: HTMLDivElement | undefined;
  let canvas: HTMLCanvasElement | undefined;
  let viewport = $state<Viewport>({ x: 40, y: 40, scale: 4 });
  let cursorMm = $state<{ x: number; y: number } | null>(null);

  let scene = $derived.by(() => ($project ? buildPcbScene($project) : null));

  $effect(() => {
    if (!canvas || !scene) return;
    const dpr = window.devicePixelRatio;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    const ctx = canvas.getContext('2d')!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const sel = $selection?.kind === 'component' ? $selection.uuid : null;
    drawPcb(ctx, scene, $layers, $layerVisibility, viewport, sel);
  });

  function onWheel(e: WheelEvent) {
    e.preventDefault();
    const factor = Math.exp(-e.deltaY * 0.001);
    const rect = canvas!.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    viewport = {
      x: mx - (mx - viewport.x) * factor,
      y: my - (my - viewport.y) * factor,
      scale: viewport.scale * factor
    };
  }
  let drag = false, lx = 0, ly = 0;
  function onDown(e: PointerEvent) { if (e.button !== 0) return; drag = true; lx = e.clientX; ly = e.clientY; canvas!.setPointerCapture(e.pointerId); }
  function onMove(e: PointerEvent) {
    const rect = canvas!.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    cursorMm = { x: (mx - viewport.x) / viewport.scale, y: (my - viewport.y) / viewport.scale };
    if (drag) {
      viewport = { ...viewport, x: viewport.x + (e.clientX - lx), y: viewport.y + (e.clientY - ly) };
      lx = e.clientX; ly = e.clientY;
    }
  }
  function onUp() { drag = false; }
  function onClick(e: MouseEvent) {
    if (!scene) return;
    const rect = canvas!.getBoundingClientRect();
    const mx = (e.clientX - rect.left - viewport.x) / viewport.scale;
    const my = (e.clientY - rect.top  - viewport.y) / viewport.scale;
    const hits = hitPoint(scene.footprintIndex, mx, my);
    if (hits.length) selectComponent({ uuid: hits[0]!, source: 'pcb' });
  }
  function fit() {
    if (!scene || !canvas) return;
    const rect = canvas.getBoundingClientRect();
    const b = scene.boundsMm;
    if (b.w === 0 || b.h === 0) return;
    const s = Math.min(rect.width / b.w, rect.height / b.h) * 0.9;
    viewport = { x: rect.width / 2 - (b.x + b.w / 2) * s, y: rect.height / 2 - (b.y + b.h / 2) * s, scale: s };
  }

  // expose cursorMm and fit via callback prop so the viewer route can wire them
  interface Props { onCursor?: (p: { x:number; y:number } | null) => void; fitRequested?: number; }
  let { onCursor, fitRequested = 0 }: Props = $props();
  $effect(() => onCursor?.(cursorMm));
  $effect(() => { if (fitRequested > 0) fit(); });
</script>

<div class="stage" bind:this={host}>
  <canvas
    bind:this={canvas}
    onwheel={onWheel}
    onpointerdown={onDown}
    onpointermove={onMove}
    onpointerup={onUp}
    onclick={onClick}
  ></canvas>
</div>

<style>
  .stage { position: relative; width: 100%; height: 100%; background: var(--kv-render-bg); overflow: hidden; }
  canvas { position: absolute; inset: 0; width: 100%; height: 100%; touch-action: none; display: block; cursor: grab; }
</style>
```

- [ ] **Step 3: Wire into viewer**

```svelte
  {:else if tab === 'pcb'}
    <PcbView onCursor={(c) => (cursorMm = c)} {fitRequested} />
```

and pass `cursorMm` down to the `Shell` via its existing prop.

- [ ] **Step 4: Smoke-test** — layer toggles, pan/zoom, click footprint, inspector updates.

- [ ] **Step 5: Commit**

```bash
git add kicad-viewer/
git commit -m "Add Canvas2D PcbView with layer toggles and click selection"
```

---

### Task 27: PCB cross-probe reaction + net highlighting

**Files:**
- Modify: `kicad-viewer/src/lib/views/PcbView.svelte`

- [ ] **Step 1: On external selection (source ≠ 'pcb'), pan/zoom canvas to center on target footprint**

Add in `$effect` for `$selection`:
```ts
  $effect(() => {
    const s = $selection;
    if (!s || s.source === 'pcb' || s.kind !== 'component' || !scene || !canvas) return;
    const fp = scene.footprints.find((f) => f.uuid === s.uuid);
    if (!fp) return;
    const rect = canvas.getBoundingClientRect();
    const cx = fp.position.x, cy = fp.position.y;
    viewport = { ...viewport, x: rect.width / 2 - cx * viewport.scale, y: rect.height / 2 - cy * viewport.scale };
  });
```

- [ ] **Step 2: Net highlighting on hover and on selection**

Extend `drawPcb`:
```ts
export function drawPcb(
  ctx: CanvasRenderingContext2D,
  scene: PcbScene,
  layers: LayerInfo[],
  visible: Map<string, boolean>,
  viewport: Viewport,
  selectedFootprint?: string | null,
  highlightedNet?: string | null
) {
  /* ... existing body ... */

  // Draw highlighted net on top
  if (highlightedNet) {
    ctx.save();
    ctx.translate(viewport.x, viewport.y); ctx.scale(viewport.scale, viewport.scale);
    ctx.strokeStyle = '#ffd54a';
    for (const [, buckets] of scene.byLayer) {
      for (const t of buckets.tracks) {
        if (t.netName !== highlightedNet) continue;
        ctx.lineWidth = t.widthMm + 0.1;
        ctx.beginPath(); ctx.moveTo(t.a.x, t.a.y); ctx.lineTo(t.b.x, t.b.y); ctx.stroke();
      }
    }
    ctx.restore();
  }
}
```

- [ ] **Step 3: Wire hover-to-highlight in `PcbView` via `onpointermove` resolving pointer-under-track**

Add per-track R-tree for cheap nearest-track lookup; or, simpler for v1: resolve only on click/selection — hover-highlight only when the selection is a net.

Pragmatic v1: skip pointer hover; net-highlight is driven solely by `selection.kind === 'net'`.

```ts
  let highlightedNet = $derived.by(() =>
    $selection?.kind === 'net' ? $selection.name : null
  );
```

Pass into `drawPcb` call.

- [ ] **Step 4: Commit**

```bash
git add kicad-viewer/
git commit -m "PCB view reacts to external selection and highlights selected net"
```

---

### Task 28: Net/refdes labels at zoom thresholds

**Files:**
- Modify: `kicad-viewer/src/lib/pcb/render.ts`

- [ ] **Step 1: Add a pass that draws labels when viewport.scale exceeds thresholds**

Add after the layer-stroke loop, inside the transformed space:
```ts
  // Refdes labels: always above REFDES_THRESHOLD (px/mm)
  const REFDES_THRESHOLD = 1.2;
  const NET_THRESHOLD = 2.5;
  const pxPerMm = viewport.scale;
  if (pxPerMm > REFDES_THRESHOLD) {
    ctx.save();
    ctx.fillStyle = '#c8c8c8';
    ctx.font = `${1.2 / pxPerMm * 10}px ui-sans-serif`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    for (const fp of scene.footprints) {
      ctx.fillText(fp.refdes, fp.position.x, fp.position.y);
    }
    ctx.restore();
  }
  if (pxPerMm > NET_THRESHOLD) {
    ctx.save();
    ctx.fillStyle = '#80e080';
    ctx.font = `${0.8 / pxPerMm * 10}px ui-sans-serif`;
    for (const [, buckets] of scene.byLayer) {
      for (const t of buckets.tracks) {
        if (!t.netName) continue;
        const mx = (t.a.x + t.b.x) / 2, my = (t.a.y + t.b.y) / 2;
        ctx.fillText(t.netName, mx, my - 0.2);
      }
    }
    ctx.restore();
  }
```

Render-time: acceptable on medium boards; if it chokes, gate behind viewport culling later.

- [ ] **Step 2: Commit**

```bash
git add kicad-viewer/
git commit -m "Draw refdes and net labels above zoom thresholds"
```

---

## Milestone 7 — 3D view

### Task 29: ThreeDView with GLB loader and orbit controls

**Files:**
- Create: `kicad-viewer/src/lib/three/loader.ts`
- Create: `kicad-viewer/src/lib/views/ThreeDView.svelte`

- [ ] **Step 1: Install three**

```bash
cd kicad-viewer && npm install three
npm install -D @types/three
```

- [ ] **Step 2: Implement loader helper**

`kicad-viewer/src/lib/three/loader.ts`:
```ts
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { Group } from 'three';

export async function loadGlb(url: string): Promise<Group> {
  const loader = new GLTFLoader();
  return new Promise((resolve, reject) => {
    loader.load(url, (gltf) => resolve(gltf.scene), undefined, reject);
  });
}

/** Build refdes → Object3D map from named nodes. KiCad 10 names each footprint group. */
export function indexByRefdes(root: Group): Map<string, import('three').Object3D> {
  const m = new Map<string, import('three').Object3D>();
  root.traverse((obj) => {
    if (obj.name && /^[A-Z]+[0-9]+/.test(obj.name)) m.set(obj.name.split(/\s|:/)[0]!, obj);
  });
  return m;
}
```

- [ ] **Step 3: Implement view**

`kicad-viewer/src/lib/views/ThreeDView.svelte`:
```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import * as THREE from 'three';
  import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
  import { project } from '$lib/stores/project';
  import { selection, selectComponent } from '$lib/stores/selection';
  import { loadGlb, indexByRefdes } from '$lib/three/loader';

  let host: HTMLDivElement | undefined;
  let canvas: HTMLCanvasElement | undefined;
  let refdesToMesh = new Map<string, THREE.Object3D>();
  let renderer: THREE.WebGLRenderer | null = null;
  let camera: THREE.PerspectiveCamera | null = null;
  let scene: THREE.Scene | null = null;
  let controls: OrbitControls | null = null;
  let raycaster = new THREE.Raycaster();

  onMount(() => {
    if (!canvas) return;
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0b0d12);
    camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
    camera.position.set(100, 80, 100);
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    controls = new OrbitControls(camera, canvas);
    scene.add(new THREE.AmbientLight(0xffffff, 0.5));
    const dir = new THREE.DirectionalLight(0xffffff, 1.0); dir.position.set(100, 200, 100);
    scene.add(dir);

    const ro = new ResizeObserver(() => resize());
    ro.observe(host!);

    let raf = 0;
    const tick = () => {
      controls!.update();
      renderer!.render(scene!, camera!);
      raf = requestAnimationFrame(tick);
    };
    resize();
    tick();
    return () => { cancelAnimationFrame(raf); ro.disconnect(); renderer?.dispose(); };
  });

  function resize() {
    if (!host || !renderer || !camera) return;
    const r = host.getBoundingClientRect();
    renderer.setSize(r.width, r.height, false);
    camera.aspect = r.width / r.height;
    camera.updateProjectionMatrix();
  }

  let currentGlbUrl: string | null = null;
  $effect(() => {
    if (!scene || !$project) return;
    if (currentGlbUrl === $project.glbUrl) return;
    currentGlbUrl = $project.glbUrl ?? null;
    // clear previous
    scene.children.filter((c) => c.userData.glb).forEach((c) => scene!.remove(c));
    if (!$project.glbUrl) return;
    loadGlb($project.glbUrl).then((group) => {
      group.userData.glb = true;
      scene!.add(group);
      refdesToMesh = indexByRefdes(group);
    }).catch(() => { /* toast via caller */ });
  });

  function onClick(ev: MouseEvent) {
    if (!camera || !canvas || !scene) return;
    const rect = canvas.getBoundingClientRect();
    const x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
    const y = -(((ev.clientY - rect.top) / rect.height) * 2 - 1);
    raycaster.setFromCamera(new THREE.Vector2(x, y), camera);
    const picks = raycaster.intersectObjects(scene.children, true);
    for (const p of picks) {
      let o: THREE.Object3D | null = p.object;
      while (o) {
        const r = o.name?.split(/\s|:/)[0];
        if (r && refdesToMesh.has(r)) {
          const c = $project!.components.find((c) => c.refdes === r);
          if (c) { selectComponent({ uuid: c.uuid, source: '3d' }); return; }
        }
        o = o.parent;
      }
    }
  }

  // external selection → pan camera
  $effect(() => {
    const s = $selection;
    if (!s || s.kind !== 'component' || s.source === '3d' || !camera || !controls) return;
    const c = $project?.components.find((c) => c.uuid === s.uuid);
    if (!c) return;
    const mesh = refdesToMesh.get(c.refdes);
    if (!mesh) return;
    const target = new THREE.Vector3();
    mesh.getWorldPosition(target);
    controls.target.copy(target);
    // leave camera position alone; OrbitControls recenters
  });
</script>

<div class="stage" bind:this={host}>
  {#if !$project?.glbUrl}
    <div class="empty">
      <p>No 3D asset loaded.</p>
      <p class="dim">Drop a <code>.glb</code> here or include one in your bundle.</p>
    </div>
  {:else}
    <canvas bind:this={canvas} onclick={onClick}></canvas>
  {/if}
</div>

<style>
  .stage { position: relative; width: 100%; height: 100%; background: var(--kv-render-bg); }
  canvas { width: 100%; height: 100%; display: block; }
  .empty { position: absolute; inset: 0; display: grid; place-items: center; text-align: center; color: var(--kv-text); }
  .dim { color: var(--kv-text-dim); font-size: 0.85rem; }
</style>
```

- [ ] **Step 4: Wire into viewer**

```svelte
  {:else if tab === '3d'}
    <ThreeDView />
```

- [ ] **Step 5: Smoke-test** — load bundle fixture with .glb; orbit with mouse; click a component; inspector updates; click in schematic; 3D camera recenters.

- [ ] **Step 6: Commit**

```bash
git add kicad-viewer/
git commit -m "Add 3D view with GLB loader, orbit controls, cross-probe hooks"
```

---

### Task 30: 3D empty-state drop zone for sidecar .glb

**Files:**
- Modify: `kicad-viewer/src/lib/views/ThreeDView.svelte`

- [ ] **Step 1: Accept drag-drop of a .glb onto the empty state**

Add to the `{#if !$project?.glbUrl}` branch:
```svelte
    <div class="empty"
      ondragover={(e) => { e.preventDefault(); }}
      ondrop={(e) => {
        e.preventDefault();
        const f = e.dataTransfer?.files?.[0];
        if (!f || !/\.glb$/i.test(f.name)) return;
        const url = URL.createObjectURL(f);
        project.update((p) => p ? { ...p, glbUrl: url } : p);
      }}
    >
```

Plus an `<input type="file" accept=".glb">` fallback.

- [ ] **Step 2: Commit**

```bash
git add kicad-viewer/
git commit -m "Accept sidecar .glb drop for 3D view"
```

---

## Milestone 8 — Split view, persistence, deploy

### Task 31: SplitPane component + split tab

**Files:**
- Create: `kicad-viewer/src/lib/ui/SplitPane.svelte`
- Modify: `kicad-viewer/src/routes/viewer/+page.svelte`

- [ ] **Step 1: Implement resizable split**

`kicad-viewer/src/lib/ui/SplitPane.svelte`:
```svelte
<script lang="ts">
  interface Props { left: import('svelte').Snippet; right: import('svelte').Snippet; initial?: number; }
  let { left, right, initial = 0.5 }: Props = $props();
  let ratio = $state(initial);
  let host: HTMLDivElement | undefined;
  let dragging = false;
  function onDown() { dragging = true; }
  function onMove(e: PointerEvent) {
    if (!dragging || !host) return;
    const r = host.getBoundingClientRect();
    ratio = Math.max(0.1, Math.min(0.9, (e.clientX - r.left) / r.width));
  }
  function onUp() { dragging = false; }
</script>

<svelte:window onpointermove={onMove} onpointerup={onUp} />

<div class="split" bind:this={host}>
  <div class="pane" style="flex: {ratio};">{@render left()}</div>
  <div class="gutter" onpointerdown={onDown}></div>
  <div class="pane" style="flex: {1 - ratio};">{@render right()}</div>
</div>

<style>
  .split { display: flex; height: 100%; }
  .pane { min-width: 0; }
  .gutter { width: 6px; background: var(--kv-border); cursor: col-resize; }
</style>
```

- [ ] **Step 2: Add per-pane view picker + split wiring in viewer route**

```svelte
  let leftPane = $state<'sch' | 'pcb' | '3d'>('sch');
  let rightPane = $state<'sch' | 'pcb' | '3d'>('pcb');

  {:else if tab === 'split'}
    <SplitPane>
      {#snippet left()}
        <div class="pane-with-picker">
          <select bind:value={leftPane}><option value="sch">Schematic</option><option value="pcb">PCB</option><option value="3d">3D</option></select>
          {#if leftPane === 'sch'}<SchematicView activeSheetUuid={activeSheet} />{:else if leftPane === 'pcb'}<PcbView />{:else}<ThreeDView />{/if}
        </div>
      {/snippet}
      {#snippet right()}
        <div class="pane-with-picker">
          <select bind:value={rightPane}><option value="sch">Schematic</option><option value="pcb">PCB</option><option value="3d">3D</option></select>
          {#if rightPane === 'sch'}<SchematicView activeSheetUuid={activeSheet} />{:else if rightPane === 'pcb'}<PcbView />{:else}<ThreeDView />{/if}
        </div>
      {/snippet}
    </SplitPane>
```

Add CSS:
```svelte
  <style>
    .pane-with-picker { height: 100%; display: grid; grid-template-rows: auto 1fr; }
    .pane-with-picker select {
      padding: 4px 8px; border: none; border-bottom: 1px solid var(--kv-border);
      background: var(--kv-surface-2); color: var(--kv-text); font-size: 0.75rem;
    }
  </style>
```

- [ ] **Step 3: Smoke-test split view: pick sch+pcb, click in left, right centers on same refdes**

- [ ] **Step 4: Commit**

```bash
git add kicad-viewer/
git commit -m "Add split-pane view with per-pane picker and resizable divider"
```

---

### Task 32: Recent-projects store + persistence

**Files:**
- Create: `kicad-viewer/src/lib/stores/recent.ts`
- Modify: `kicad-viewer/src/lib/ui/DropZone.svelte`
- Modify: `kicad-viewer/src/routes/viewer/+page.svelte`

- [ ] **Step 1: Implement IndexedDB-backed store**

`kicad-viewer/src/lib/stores/recent.ts`:
```ts
// tiny IDB wrapper; no lib needed

const DB = 'kv-recent'; const STORE = 'projects';

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') return reject(new Error('no idb'));
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: 'id' });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function saveRecent(files: Record<string, string | Uint8Array>): Promise<void> {
  try {
    const db = await open();
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).put({ id: 'last', files, savedAt: Date.now() });
    await new Promise((r) => (tx.oncomplete = r));
  } catch { /* private mode or quota: ignore */ }
}

export async function loadRecent(): Promise<Record<string, string | Uint8Array> | null> {
  try {
    const db = await open();
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly');
      const req = tx.objectStore(STORE).get('last');
      req.onsuccess = () => resolve(req.result?.files ?? null);
      req.onerror = () => reject(req.error);
    });
  } catch { return null; }
}

export async function clearRecent(): Promise<void> {
  try {
    const db = await open();
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).delete('last');
    await new Promise((r) => (tx.oncomplete = r));
  } catch { /* ignore */ }
}
```

- [ ] **Step 2: In `DropZone.svelte` ingest, save to IDB after parse success**

```ts
  import { saveRecent } from '$lib/stores/recent';
  ...
      project.set(p);
      await saveRecent(blob.files);
```

- [ ] **Step 3: In viewer route, hydrate from IDB on mount if project is null**

```ts
  import { loadRecent, clearRecent } from '$lib/stores/recent';
  import { classifyFiles, rootSchematic } from '$lib/loader/blob';
  import { toProject } from '$lib/adapter/adapter';
  onMount(async () => {
    if ($project) return;
    const files = await loadRecent();
    if (!files) return;
    const blob = classifyFiles(files);
    const root = rootSchematic(blob);
    if (!blob.kicadPcb || !root) return;
    const scs: Record<string, string> = {};
    for (const s of blob.schematics) scs[s] = blob.files[s] as string;
    const p = toProject({
      pro: blob.kicadPro ? (blob.files[blob.kicadPro] as string) : '{}',
      pcb: blob.files[blob.kicadPcb] as string,
      schematics: scs,
      rootSchematic: root
    });
    if (blob.glb) {
      const u8 = blob.files[blob.glb] as Uint8Array;
      p.glbUrl = URL.createObjectURL(new Blob([u8], { type: 'model/gltf-binary' }));
    }
    project.set(p);
  });
```

- [ ] **Step 4: Add "Clear" button to shell top bar that clears IDB and resets store**

```svelte
  <button onclick={() => { clearRecent(); project.set(null); }}>Clear</button>
```

- [ ] **Step 5: Smoke-test: load, reload page, still there; clear, reloads to drop-zone**

- [ ] **Step 6: Commit**

```bash
git add kicad-viewer/
git commit -m "Persist last project to IndexedDB and auto-reopen"
```

---

### Task 33: Smoke checklist + fixtures README

**Files:**
- Create: `kicad-viewer/tests/smoke-checklist.md`
- Create: `kicad-viewer/tests/fixtures/README.md`

- [ ] **Step 1: Write smoke checklist**

`kicad-viewer/tests/smoke-checklist.md`:
```markdown
# Smoke checklist

Run before each deploy. ~5 minutes.

1. `npm run dev`, open http://localhost:5173
2. Landing loads, attribution visible, theme toggle works
3. Click "Open viewer" → `/viewer` shows drop zone
4. Drop `tests/fixtures/pic_programmer.kicad_pcb` + siblings → shell appears
5. Schematic tab
   - SheetTree lists sheets
   - Click a symbol → Inspector shows refdes, value, footprint
   - Press `/`, search "R1", pick → schematic centres on R1
6. PCB tab
   - Layers panel lists all layers
   - Toggle F.Silkscreen off / on → render updates
   - Click a footprint → Inspector matches
   - Select same in Schematic tab → PCB recenters on it
7. 3D tab
   - GLB loads (pic_programmer.glb)
   - Orbit with mouse
   - Click a component → Inspector; click in Schematic → camera recenters
8. Split tab
   - Picker shows sch/pcb/3d choices
   - Choose sch on left, pcb on right → both render
   - Drag divider → split resizes
   - Click in left → right reacts
9. Reload page → last project re-opens
10. Click "Clear" → drop zone returns
```

- [ ] **Step 2: Fixtures README**

`kicad-viewer/tests/fixtures/README.md`:
```markdown
# Fixtures

A small open-source KiCad 10 project used as the sole test fixture.

- `pic_programmer.*` — from KiCad's demos (MIT / CC).
- `pic_programmer.glb` — generated via `kicad-cli pcb export glb --subst-models --force`.

To regenerate the .glb:

    kicad-cli pcb export glb pic_programmer.kicad_pcb -o pic_programmer.glb --subst-models --force
```

- [ ] **Step 3: Commit**

```bash
git add kicad-viewer/
git commit -m "Add smoke checklist and fixtures README"
```

---

### Task 34: Cross-probing e2e test

**Files:**
- Create: `kicad-viewer/tests/e2e/cross-probe.spec.ts`

- [ ] **Step 1: Write e2e covering sch→pcb click**

```ts
import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

test('sch click cross-probes to pcb', async ({ page }) => {
  await page.goto('/viewer');

  const files = ['pic_programmer.kicad_pro', 'pic_programmer.kicad_pcb', 'pic_programmer.kicad_sch'];
  const input = page.locator('input[type=file]');
  await input.setInputFiles(files.map((f) => join('tests/fixtures', f)));

  await expect(page.locator('h1, header strong')).toContainText('kicad-viewer');
  await expect(page.locator('[aria-selected="true"]', { hasText: 'Schematic' })).toBeVisible();

  // Click a symbol group (first)
  const first = page.locator('[data-refdes]').first();
  await first.click();
  const refdes = await first.getAttribute('data-refdes');
  expect(refdes).toBeTruthy();

  // Switch to PCB and confirm inspector still shows the refdes
  await page.locator('button', { hasText: 'PCB' }).click();
  await expect(page.locator('.hdr h3')).toContainText(refdes!);
});
```

- [ ] **Step 2: Run**

```bash
cd kicad-viewer && npm run e2e
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add kicad-viewer/
git commit -m "Add e2e cross-probe smoke"
```

---

### Task 35: Cloudflare Pages deployment

**Files:**
- Create: `kicad-viewer/DEPLOY.md`
- Modify: `kicad-viewer/README.md`

- [ ] **Step 1: Write deploy doc**

`kicad-viewer/DEPLOY.md`:
```markdown
# Deploying kicad-viewer to Cloudflare Pages

## One-time setup

1. In the Cloudflare dashboard, create a Pages project linked to
   `github.com/mlaustin44/kicad-tools`.
2. Build settings:
   - Root directory: `kicad-viewer`
   - Build command: `npm ci && npm run build`
   - Output directory: `build`
   - Node version: `20` (set `NODE_VERSION=20` in env, or rely on `.nvmrc`)
3. Production branch: `main`. Preview branches: all others.

## Per-deploy

Just push to the branch. CF picks it up; production URL updates on `main`,
preview URL posted on each PR.

## Custom domain (optional)

Add a CNAME pointing to the Pages project once you have one.

## Local preview (matching production)

```
cd kicad-viewer
npm run build
npm run preview
```
```

- [ ] **Step 2: Link from README**

Append to `kicad-viewer/README.md`:
```markdown

## Deploying

See `DEPLOY.md`.
```

- [ ] **Step 3: Commit**

```bash
git add kicad-viewer/
git commit -m "Add Cloudflare Pages deploy doc"
```

---

## Self-review

Spec-to-plan coverage:

| Spec requirement | Task(s) |
|---|---|
| Landing `/` with attribution | 6 |
| Viewer `/viewer` SPA route | 14, 15 |
| Drop zip/folder/files | 13, 14 |
| Manifest bundle detection | 13 |
| Schematic tab — hierarchy, click details | 18, 19, 20 |
| Schematic — pan/zoom, search | 18, 21 |
| PCB tab — layer toggles, click, hover | 25, 26, 27 |
| PCB — net/pour labels at zoom | 28 |
| 3D tab — GLB, orbit, click | 29 |
| 3D — empty state drop zone | 30 |
| Split tab — per-pane picker | 31 |
| Cross-probing contract | 8, 22, 27, 29 |
| Persistence (IndexedDB) | 32 |
| Footer attribution | 15 |
| KiCad UUID identity | 7, 8 |
| Keyboard shortcuts | 17 |
| Theming (dark/light) | 4, 5 |
| Error toasts | 9, 14 |
| Bundle format | 13 |
| Testing (unit/component/e2e/smoke) | 2, 3, 5, 7, 8, 9, 11, 13, 16, 22, 23, 24, 33, 34 |
| Deployment | 35 |

All spec requirements are mapped. 3D cross-probing is implemented in Task 29; if the
GLB mesh-naming assumption fails, Task 29 ships as the static view described in the
spec's "Open technical risks" section and the reaction-table rows for 3D become no-ops.
