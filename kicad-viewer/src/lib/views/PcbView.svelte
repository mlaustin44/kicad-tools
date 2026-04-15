<script lang="ts">
  import { untrack } from 'svelte';
  import { project, componentsByRefdes } from '$lib/stores/project';
  import { layerVisibility, layers, activeLayer } from '$lib/stores/layers';
  import { settings } from '$lib/stores/settings';
  import {
    selection,
    selectComponent,
    selectTrack,
    selectZone,
    selectVia,
    clearSelection
  } from '$lib/stores/selection';
  import { buildPcbScene, type PcbScene } from '$lib/pcb/scene';
  import { drawPcb, type Viewport } from '$lib/pcb/render';
  import { hitPoint } from '$lib/geom/rtree';
  import { hitTrack, hitVia, hitZone, polygonAreaMm2 } from '$lib/pcb/hit-test';
  import { classifyLayer } from '$lib/pcb/layer-side';
  import ContextMenu from '$lib/ui/ContextMenu.svelte';

  interface Props {
    onCursor?: (p: { x: number; y: number } | null) => void;
    fitRequested?: number;
    panPulse?: { dx: number; dy: number; seq: number };
    zoomPulse?: { factor: number; seq: number };
  }
  let { onCursor, fitRequested = 0, panPulse, zoomPulse }: Props = $props();

  let host = $state<HTMLDivElement | undefined>(undefined);
  let canvas = $state<HTMLCanvasElement | undefined>(undefined);
  let viewport = $state<Viewport>({ x: 40, y: 40, scale: 4 });
  let cursorMm = $state<{ x: number; y: number } | null>(null);

  const scene = $derived.by<PcbScene | null>(() => ($project ? buildPcbScene($project) : null));

  let highlightedNet = $derived.by<string | null>(() => {
    if ($selection?.kind === 'net') return $selection.name;
    return null;
  });

  function redraw() {
    if (!canvas || !scene) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    // Translate component UUID to footprint UUID (they differ in KiCad).
    let selFpUuid: string | null = null;
    if ($selection?.kind === 'component') {
      const comp = $project?.components.find((c) => c.uuid === $selection.uuid);
      const fp = comp ? scene.footprints.find((f) => f.refdes === comp.refdes) : undefined;
      selFpUuid = fp?.uuid ?? null;
    }
    const selGeom =
      $selection?.kind === 'track' || $selection?.kind === 'zone' || $selection?.kind === 'via'
        ? { kind: $selection.kind, idx: $selection.idx }
        : null;
    drawPcb(
      ctx,
      scene,
      $layers,
      $layerVisibility,
      viewport,
      $activeLayer,
      $settings.inactiveLayerOpacity,
      selFpUuid,
      highlightedNet,
      selGeom,
      $project?.pcb.tracks,
      $project?.pcb.zones,
      $project?.pcb.vias
    );
  }

  function resizeCanvas() {
    if (!canvas || !host) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = host.getBoundingClientRect();
    const nextW = Math.max(1, Math.floor(rect.width * dpr));
    const nextH = Math.max(1, Math.floor(rect.height * dpr));
    if (canvas.width !== nextW) canvas.width = nextW;
    if (canvas.height !== nextH) canvas.height = nextH;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = rect.height + 'px';
    const ctx = canvas.getContext('2d');
    if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  // Redraw whenever scene / layers / visibility / viewport / selection change
  $effect(() => {
    if (!canvas || !scene) return;
    resizeCanvas();
    redraw();
  });

  $effect(() => {
    if (!host) return;
    const ro = new ResizeObserver(() => {
      resizeCanvas();
      redraw();
    });
    ro.observe(host);
    return () => ro.disconnect();
  });

  function onWheel(e: WheelEvent) {
    e.preventDefault();
    if (!canvas) return;
    const factor = Math.exp(-e.deltaY * 0.001);
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    viewport = {
      x: mx - (mx - viewport.x) * factor,
      y: my - (my - viewport.y) * factor,
      scale: viewport.scale * factor
    };
  }

  let drag = $state(false);
  let lx = 0, ly = 0;
  function onDown(e: PointerEvent) {
    if (e.button === 1) {
      e.preventDefault();
    } else if (e.button !== 0) {
      return;
    }
    drag = true;
    lx = e.clientX;
    ly = e.clientY;
    canvas?.setPointerCapture(e.pointerId);
  }
  function onMove(e: PointerEvent) {
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    cursorMm = {
      x: (mx - viewport.x) / viewport.scale,
      y: (my - viewport.y) / viewport.scale
    };
    if (drag) {
      viewport = {
        x: viewport.x + (e.clientX - lx),
        y: viewport.y + (e.clientY - ly),
        scale: viewport.scale
      };
      lx = e.clientX;
      ly = e.clientY;
    }
  }
  function onUp() {
    drag = false;
  }
  function onLeave() {
    cursorMm = null;
  }

  function onClick(e: MouseEvent) {
    if (!scene || !canvas || !$project) return;
    const rect = canvas.getBoundingClientRect();
    const mx = (e.clientX - rect.left - viewport.x) / viewport.scale;
    const my = (e.clientY - rect.top - viewport.y) / viewport.scale;
    const slopMm = 2 / viewport.scale;

    // Determine the active side from the active layer so we can prefer things
    // the user is actually looking at over stuff on the dimmed opposite side.
    const rawSide = classifyLayer($activeLayer, $layers);
    const activeSide: 'front' | 'back' = rawSide === 'back' ? 'back' : 'front';
    const activeFpSide: 'top' | 'bottom' = activeSide === 'back' ? 'bottom' : 'top';

    const fpHits = hitPoint(scene.footprintIndex, mx, my);
    const fpsHit = fpHits
      .map((uuid) => scene.footprints.find((f) => f.uuid === uuid))
      .filter((f): f is NonNullable<typeof f> => Boolean(f));

    const selectFootprint = (fp: NonNullable<typeof fpsHit[number]>) => {
      const comp = $componentsByRefdes.get(fp.refdes);
      if (comp) selectComponent({ uuid: comp.uuid, source: 'pcb' });
      else clearSelection();
    };

    // 1. Active-side footprint — the user clicked on a component they're viewing.
    const activeFp = fpsHit.find((f) => f.side === activeFpSide);
    if (activeFp) {
      selectFootprint(activeFp);
      return;
    }

    // 2. Active-copper via.
    const vias = $project.pcb.vias;
    for (let i = 0; i < vias.length; i++) {
      const v = vias[i]!;
      if (!hitVia(mx, my, v)) continue;
      if (v.layerFrom === $activeLayer || v.layerTo === $activeLayer) {
        selectVia({ idx: i, source: 'pcb' });
        return;
      }
    }

    // 3. Active-copper track.
    const tracks = $project.pcb.tracks;
    let bestTrack = -1;
    let bestTrackDist = Infinity;
    for (let i = 0; i < tracks.length; i++) {
      const t = tracks[i]!;
      if (t.layerId !== $activeLayer) continue;
      if (!$layerVisibility.get(t.layerId)) continue;
      if (!hitTrack(mx, my, t, slopMm)) continue;
      if (t.widthMm < bestTrackDist) {
        bestTrack = i;
        bestTrackDist = t.widthMm;
      }
    }
    if (bestTrack >= 0) {
      selectTrack({ idx: bestTrack, source: 'pcb' });
      return;
    }

    // 4. Active-copper zone (prefer smallest-area so nested pours work).
    const zones = $project.pcb.zones;
    let bestZone = -1;
    let bestZoneArea = Infinity;
    for (let i = 0; i < zones.length; i++) {
      const z = zones[i]!;
      if (z.layerId !== $activeLayer) continue;
      if (!$layerVisibility.get(z.layerId)) continue;
      if (!hitZone(mx, my, z)) continue;
      const area = polygonAreaMm2(z.polygon);
      if (area < bestZoneArea) {
        bestZone = i;
        bestZoneArea = area;
      }
    }
    if (bestZone >= 0) {
      selectZone({ idx: bestZone, source: 'pcb' });
      return;
    }

    // 5. Fall back to opposite-side footprint (so bottom components are still
    // pickable when F.Cu is active and there's nothing else there).
    const otherFp = fpsHit.find((f) => f.side !== activeFpSide);
    if (otherFp) {
      selectFootprint(otherFp);
      return;
    }

    // 6. Any visible via regardless of active layer.
    for (let i = 0; i < vias.length; i++) {
      if (hitVia(mx, my, vias[i]!)) {
        selectVia({ idx: i, source: 'pcb' });
        return;
      }
    }

    // 7. Any visible track.
    bestTrack = -1;
    bestTrackDist = Infinity;
    for (let i = 0; i < tracks.length; i++) {
      const t = tracks[i]!;
      if (!$layerVisibility.get(t.layerId)) continue;
      if (!hitTrack(mx, my, t, slopMm)) continue;
      if (t.widthMm < bestTrackDist) {
        bestTrack = i;
        bestTrackDist = t.widthMm;
      }
    }
    if (bestTrack >= 0) {
      selectTrack({ idx: bestTrack, source: 'pcb' });
      return;
    }

    // 8. Any visible zone.
    bestZone = -1;
    bestZoneArea = Infinity;
    for (let i = 0; i < zones.length; i++) {
      const z = zones[i]!;
      if (!$layerVisibility.get(z.layerId)) continue;
      if (!hitZone(mx, my, z)) continue;
      const area = polygonAreaMm2(z.polygon);
      if (area < bestZoneArea) {
        bestZone = i;
        bestZoneArea = area;
      }
    }
    if (bestZone >= 0) {
      selectZone({ idx: bestZone, source: 'pcb' });
      return;
    }

    clearSelection();
  }

  let ctxMenu = $state<{ open: boolean; x: number; y: number; refdes: string | null }>({
    open: false, x: 0, y: 0, refdes: null
  });

  function onContextMenu(e: MouseEvent) {
    e.preventDefault();
    if (!canvas || !scene) {
      ctxMenu = { open: true, x: e.clientX, y: e.clientY, refdes: null };
      return;
    }
    const rect = canvas.getBoundingClientRect();
    const mx = (e.clientX - rect.left - viewport.x) / viewport.scale;
    const my = (e.clientY - rect.top - viewport.y) / viewport.scale;
    const hits = hitPoint(scene.footprintIndex, mx, my);
    const hit = hits[0];
    const fp = hit ? scene.footprints.find((f) => f.uuid === hit) : undefined;
    ctxMenu = {
      open: true,
      x: e.clientX,
      y: e.clientY,
      refdes: fp?.refdes ?? null
    };
  }

  let menuItems = $derived.by(() => {
    const items: Array<{ label: string; action: () => void }> = [
      { label: 'Fit view', action: () => fit() },
      { label: 'Clear selection', action: () => clearSelection() }
    ];
    if (ctxMenu.refdes) {
      const r = ctxMenu.refdes;
      items.push({
        label: `Copy refdes (${r})`,
        action: () => { navigator.clipboard?.writeText(r).catch(() => {}); }
      });
    }
    return items;
  });

  function fit() {
    if (!scene || !canvas) return;
    const rect = canvas.getBoundingClientRect();
    const b = scene.boundsMm;
    if (b.w <= 0 || b.h <= 0 || rect.width <= 0 || rect.height <= 0) return;
    const s = Math.min(rect.width / b.w, rect.height / b.h) * 0.9;
    viewport = {
      x: rect.width / 2 - (b.x + b.w / 2) * s,
      y: rect.height / 2 - (b.y + b.h / 2) * s,
      scale: s
    };
  }

  // External cursor prop callback
  $effect(() => {
    onCursor?.(cursorMm);
  });

  // fitRequested: tracked by parent via incrementing counter
  $effect(() => {
    if (fitRequested > 0) fit();
  });

  let lastPanSeq = 0;
  $effect(() => {
    if (!panPulse || panPulse.seq === lastPanSeq) return;
    lastPanSeq = panPulse.seq;
    viewport = { x: viewport.x + panPulse.dx, y: viewport.y + panPulse.dy, scale: viewport.scale };
  });

  let lastZoomSeq = 0;
  $effect(() => {
    if (!zoomPulse || zoomPulse.seq === lastZoomSeq || !canvas) return;
    lastZoomSeq = zoomPulse.seq;
    const rect = canvas.getBoundingClientRect();
    const mx = rect.width / 2;
    const my = rect.height / 2;
    const factor = zoomPulse.factor;
    viewport = {
      x: mx - (mx - viewport.x) * factor,
      y: my - (my - viewport.y) * factor,
      scale: viewport.scale * factor
    };
  });

  // When a new project arrives, auto-fit once.
  $effect(() => {
    if (scene) {
      queueMicrotask(fit);
    }
  });

  // External component selection (from Schematic, search, etc.) — recenter PCB on it.
  $effect(() => {
    const s = $selection;
    if (!s || s.kind !== 'component' || s.source === 'pcb') return;
    if (!scene || !canvas) return;
    // s.uuid is a component (symbol) UUID; resolve to footprint via refdes.
    const comp = $project?.components.find((c) => c.uuid === s.uuid);
    if (!comp) return;
    const fp = scene.footprints.find((f) => f.refdes === comp.refdes);
    if (!fp) return;
    const rect = canvas.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    const current = untrack(() => viewport);
    const cx = fp.position.x;
    const cy = fp.position.y;
    const nextX = rect.width / 2 - cx * current.scale;
    const nextY = rect.height / 2 - cy * current.scale;
    if (Math.abs(nextX - current.x) < 0.5 && Math.abs(nextY - current.y) < 0.5) return;
    viewport = { x: nextX, y: nextY, scale: current.scale };
  });
</script>

<div class="stage" bind:this={host}>
  <canvas
    bind:this={canvas}
    class:dragging={drag}
    onwheel={onWheel}
    onpointerdown={onDown}
    onpointermove={onMove}
    onpointerup={onUp}
    onpointerleave={onLeave}
    onauxclick={(e) => { if (e.button === 1) e.preventDefault(); }}
    onclick={onClick}
    oncontextmenu={onContextMenu}
  ></canvas>
</div>

<ContextMenu
  open={ctxMenu.open}
  x={ctxMenu.x}
  y={ctxMenu.y}
  items={menuItems}
  onClose={() => (ctxMenu = { ...ctxMenu, open: false })}
/>

<style>
  .stage {
    position: relative;
    width: 100%;
    height: 100%;
    background: var(--kv-render-bg);
    overflow: hidden;
  }
  canvas {
    position: absolute;
    inset: 0;
    touch-action: none;
    display: block;
    cursor: grab;
  }
  canvas.dragging { cursor: grabbing; }
</style>
