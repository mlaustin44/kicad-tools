# Smoke checklist

Run before each deploy. Takes ~5 minutes.

## Setup

```
cd kicad-viewer
npm run dev
```

Open http://localhost:5173

## Steps

1. **Landing** — `/` loads. Hero headline visible, theme toggle (☀/☾) switches.
   Footer "Built by Matthew Austin, 2026" is visible on the viewer, not landing
   (landing has its own credit).
2. **Open viewer** — click "Open viewer →" → goes to `/viewer`, shows drop zone.
3. **Load project** — drop `tests/fixtures/pic_programmer.kicad_pcb`, `.kicad_sch`,
   `.kicad_pro`, `pic_sockets.kicad_sch`, and `.glb` (or use "Pick files" multi-select).
   Viewer shell appears.
4. **Schematic tab**
   - Sheets tree lists `pic_programmer` and `pic_sockets`.
   - Click any sheet symbol (double-click to dive) — navigates.
   - Click a component — Inspector shows refdes, value, footprint.
   - Press `/`, type "R1", pick — view recenters on R1.
   - Press `[` / `]` — navigates between sheets.
5. **PCB tab**
   - Layers panel lists all layers with color swatches.
   - Toggle F.Silkscreen off/on — render updates.
   - Click a footprint — Inspector matches.
   - Drag pans, wheel zooms, `f` fits.
6. **Cross-probe** — select R1 in Schematic → PCB centres on it. Select it in
   PCB → Schematic navigates to the right sheet and centres on R1.
7. **3D tab**
   - Drop-in .glb renders; orbit with mouse.
   - Click a component in 3D → Inspector shows details.
   - Click in Schematic → 3D camera recenters (best-effort; depends on KiCad's
     GLB naming — acceptable if no-op).
8. **Split tab**
   - Picker shows sch/pcb/3d for each pane.
   - Choose sch left, pcb right — both render.
   - Drag divider — split resizes.
   - Click in left pane → right reacts.
9. **Persistence**
   - Reload the page → last project re-opens automatically.
   - Click "Clear" in the top bar → drop zone returns.
10. **Themes** — toggle dark/light — chrome and render surfaces update.
