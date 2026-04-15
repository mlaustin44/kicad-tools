<script lang="ts">
  import { untrack } from 'svelte';
  import { project, componentsByRefdes } from '$lib/stores/project';
  import { layerVisibility, layers } from '$lib/stores/layers';
  import { selection, selectComponent, clearSelection } from '$lib/stores/selection';
  import { buildPcbScene, type PcbScene } from '$lib/pcb/scene';
  import { drawPcb, type Viewport } from '$lib/pcb/render';
  import { hitPoint } from '$lib/geom/rtree';
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
    drawPcb(ctx, scene, $layers, $layerVisibility, viewport, selFpUuid, highlightedNet);
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
    if (!scene || !canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = (e.clientX - rect.left - viewport.x) / viewport.scale;
    const my = (e.clientY - rect.top - viewport.y) / viewport.scale;
    const hits = hitPoint(scene.footprintIndex, mx, my);
    // Scene indexes by footprint UUID, but Inspector lookups key by component
    // (symbol) UUID. KiCad keeps these separate, so resolve via refdes.
    const fpUuid = hits[0];
    if (fpUuid) {
      const fp = scene.footprints.find((f) => f.uuid === fpUuid);
      const comp = fp ? $componentsByRefdes.get(fp.refdes) : undefined;
      if (comp) selectComponent({ uuid: comp.uuid, source: 'pcb' });
      else clearSelection();
    } else {
      clearSelection();
    }
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
