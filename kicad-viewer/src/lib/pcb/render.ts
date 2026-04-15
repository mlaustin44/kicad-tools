import type { PcbScene } from './scene';
import type { LayerInfo, GraphicGeom } from '$lib/model/project';

export interface Viewport {
  x: number;
  y: number;
  scale: number;
}

export function drawPcb(
  ctx: CanvasRenderingContext2D,
  scene: PcbScene,
  layers: LayerInfo[],
  visible: Map<string, boolean>,
  viewport: Viewport,
  selectedFootprint?: string | null,
  highlightedNet?: string | null
): void {
  const { width, height } = ctx.canvas;
  ctx.clearRect(0, 0, width, height);

  ctx.save();
  ctx.translate(viewport.x, viewport.y);
  ctx.scale(viewport.scale, viewport.scale);
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

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

  // Selection overlay
  if (selectedFootprint) {
    const fp = scene.footprints.find((f) => f.uuid === selectedFootprint);
    if (fp) {
      ctx.strokeStyle = '#6aa6ff';
      ctx.lineWidth = Math.max(0.1, 2 / viewport.scale);
      ctx.strokeRect(fp.bboxMm.x, fp.bboxMm.y, fp.bboxMm.w, fp.bboxMm.h);
    }
  }

  if (highlightedNet) {
    ctx.strokeStyle = '#ffd54a';
    // Walk all tracks (across layers/buckets) whose netName matches
    for (const [, buckets] of scene.byLayer) {
      for (const t of buckets.tracks) {
        if (t.netName !== highlightedNet) continue;
        ctx.lineWidth = t.widthMm + 0.1;
        ctx.beginPath();
        ctx.moveTo(t.a.x, t.a.y);
        ctx.lineTo(t.b.x, t.b.y);
        ctx.stroke();
      }
      // Vias on the net, too (for through-hole connections)
      for (const v of buckets.vias) {
        if (v.netName !== highlightedNet) continue;
        ctx.beginPath();
        ctx.arc(v.position.x, v.position.y, v.diameterMm / 2 + 0.05, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
  }

  ctx.restore();
}

function drawLayer(ctx: CanvasRenderingContext2D, scene: PcbScene, layer: LayerInfo): void {
  const buckets = scene.byLayer.get(layer.id);
  if (!buckets) return;
  ctx.strokeStyle = layer.defaultColor;
  ctx.fillStyle = layer.defaultColor;

  // Zones (filled polygons, semi-transparent)
  for (const z of buckets.zones) {
    if (z.polygon.length < 2) continue;
    ctx.globalAlpha = 0.5;
    ctx.beginPath();
    const p0 = z.polygon[0]!;
    ctx.moveTo(p0.x, p0.y);
    for (let i = 1; i < z.polygon.length; i++) {
      const pt = z.polygon[i]!;
      ctx.lineTo(pt.x, pt.y);
    }
    ctx.closePath();
    ctx.fill();
    ctx.globalAlpha = 1;
  }

  // Tracks
  for (const t of buckets.tracks) {
    if (t.widthMm <= 0) continue;
    ctx.lineWidth = t.widthMm;
    ctx.beginPath();
    ctx.moveTo(t.a.x, t.a.y);
    ctx.lineTo(t.b.x, t.b.y);
    ctx.stroke();
  }

  // Vias (only on from-layer bucket per scene.ts convention)
  for (const v of buckets.vias) {
    if (v.diameterMm <= 0) continue;
    ctx.beginPath();
    ctx.arc(v.position.x, v.position.y, v.diameterMm / 2, 0, Math.PI * 2);
    ctx.fill();
  }

  // Footprint graphics (silk/fab/courtyard lines, polygons, arcs)
  for (const g of buckets.graphics) {
    const fp = g.from;
    const graphic = fp.graphics[g.idx];
    if (!graphic) continue;
    drawGraphic(ctx, graphic.geom, fp.position, fp.rotationDeg, fp.side);
  }
}

function drawGraphic(
  ctx: CanvasRenderingContext2D,
  s: GraphicGeom,
  at: { x: number; y: number },
  rotDeg: number,
  side: 'top' | 'bottom'
): void {
  ctx.save();
  ctx.translate(at.x, at.y);
  if (side === 'bottom') ctx.scale(-1, 1); // mirror for bottom side
  ctx.rotate((rotDeg * Math.PI) / 180);

  if (s.kind === 'line') {
    ctx.lineWidth = Math.max(0.05, s.widthMm);
    ctx.beginPath();
    ctx.moveTo(s.a.x, s.a.y);
    ctx.lineTo(s.b.x, s.b.y);
    ctx.stroke();
  } else if (s.kind === 'polygon') {
    if (s.points.length > 0) {
      ctx.beginPath();
      const p0 = s.points[0]!;
      ctx.moveTo(p0.x, p0.y);
      for (let i = 1; i < s.points.length; i++) {
        const pt = s.points[i]!;
        ctx.lineTo(pt.x, pt.y);
      }
      ctx.closePath();
      if (s.filled) {
        ctx.fill();
      } else {
        ctx.lineWidth = Math.max(0.05, s.widthMm);
        ctx.stroke();
      }
    }
  } else if (s.kind === 'arc') {
    ctx.lineWidth = Math.max(0.05, s.widthMm);
    ctx.beginPath();
    ctx.arc(
      s.center.x,
      s.center.y,
      s.radiusMm,
      (s.startDeg * Math.PI) / 180,
      (s.endDeg * Math.PI) / 180
    );
    ctx.stroke();
  } else if (s.kind === 'text') {
    // Deferred to Task 28.
  }

  ctx.restore();
}
