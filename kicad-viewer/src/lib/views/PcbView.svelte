<script lang="ts">
  import { untrack } from 'svelte';
  import { project } from '$lib/stores/project';
  import { layerVisibility, layers } from '$lib/stores/layers';
  import { selection, selectComponent } from '$lib/stores/selection';
  import { buildPcbScene, type PcbScene } from '$lib/pcb/scene';
  import { drawPcb, type Viewport } from '$lib/pcb/render';
  import { hitPoint } from '$lib/geom/rtree';

  interface Props {
    onCursor?: (p: { x: number; y: number } | null) => void;
    fitRequested?: number;
    panPulse?: { dx: number; dy: number; seq: number };
  }
  let { onCursor, fitRequested = 0, panPulse }: Props = $props();

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
    const sel = $selection?.kind === 'component' ? $selection.uuid : null;
    drawPcb(ctx, scene, $layers, $layerVisibility, viewport, sel, highlightedNet);
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
    if (hits.length) selectComponent({ uuid: hits[0]!, source: 'pcb' });
  }

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
    const fp = scene.footprints.find((f) => f.uuid === s.uuid);
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
  ></canvas>
</div>

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
