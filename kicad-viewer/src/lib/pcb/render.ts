import type { PcbScene } from './scene';
import type { LayerInfo, GraphicGeom, Pad, Point, TrackSeg, FootprintGeom } from '$lib/model/project';

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

  drawGrid(ctx, scene, viewport);

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

  // Drill holes — punch through copper on through-hole pads and vias so they
  // visually read as holes instead of solid copper dots.
  drawDrillHoles(ctx, scene);

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
    const seenPads = new Set<Pad>();
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
      // Pads on the net (dedupe — through-hole pads appear in multiple layer buckets)
      for (const { fp, pad } of buckets.pads) {
        if (pad.netName !== highlightedNet) continue;
        if (seenPads.has(pad)) continue;
        seenPads.add(pad);
        ctx.save();
        ctx.translate(fp.position.x, fp.position.y);
        if (fp.side === 'bottom') ctx.scale(-1, 1);
        ctx.rotate((fp.rotationDeg * Math.PI) / 180);
        ctx.fillStyle = '#ffd54a';
        ctx.globalAlpha = 0.6;
        drawPadShape(ctx, pad);
        ctx.globalAlpha = 1;
        ctx.restore();
      }
    }
  }

  // Labels — only at sufficient zoom
  const REFDES_PX_PER_MM = 1.2;
  const pxPerMm = viewport.scale;

  if (pxPerMm > REFDES_PX_PER_MM) {
    ctx.save();
    ctx.fillStyle = '#c8c8c8';
    const refdesHeightMm = Math.max(0.8, (1.4 / pxPerMm) * 10);
    ctx.font = `${refdesHeightMm}px ui-sans-serif, system-ui, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (const fp of scene.footprints) {
      // Mirror-aware rendering: for bottom-side, text would appear mirrored because
      // the canvas is not flipped globally. We draw refdes in the footprint's natural
      // coordinate frame (top-side convention). Users who care about accurate
      // bottom-side rendering can still toggle the B.Fab layer and read there.
      ctx.fillText(fp.refdes, fp.position.x, fp.position.y);
    }
    ctx.restore();
  }

  drawCopperLabels(ctx, scene, layers, visible, pxPerMm);

  ctx.restore();
}

// ---------- copper labels (net names on tracks, pads, zones; pad numbers) ----------

// Screen-relative label sizing: the numbers are in CSS px, converted to world
// mm via the current zoom.
const TRACK_LABEL_PX = 10;
const PAD_NUM_PX = 11;
const PAD_NET_PX = 9;
const ZONE_LABEL_PX = 14;
// Tracks and pad net labels are only useful when you're zoomed in enough to
// read them without covering everything else. Zone labels stay visible a bit
// earlier because the polygons they sit on are themselves big.
const MIN_ZOOM_FOR_TRACK_LABELS = 6;
const MIN_ZOOM_FOR_PAD_NET = 8;
const MIN_ZOOM_FOR_ZONE_LABELS = 2;
// Minimum world-space separation between two labels for the *same* net.
// Prevents a long bus being labeled at every segment midpoint.
const SAME_NET_MIN_SPACING_MM = 30;

// Axis-aligned bounding box for a rendered label, in world (mm) coordinates.
// We use these to prevent labels from piling up on top of each other in dense
// routing — once a label is placed, any overlapping candidate is skipped.
interface LabelBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

function bboxesOverlap(a: LabelBox, b: LabelBox): boolean {
  return a.x0 < b.x1 && a.x1 > b.x0 && a.y0 < b.y1 && a.y1 > b.y0;
}

function rotatedLabelBox(
  cx: number,
  cy: number,
  widthMm: number,
  heightMm: number,
  angleRad: number
): LabelBox {
  // AABB of the rotated text rectangle. Slightly conservative, which is fine:
  // we're using this as an anti-clutter filter, not a precise layout system.
  const hw = widthMm / 2;
  const hh = heightMm / 2;
  const cos = Math.abs(Math.cos(angleRad));
  const sin = Math.abs(Math.sin(angleRad));
  const halfW = hw * cos + hh * sin;
  const halfH = hw * sin + hh * cos;
  return { x0: cx - halfW, y0: cy - halfH, x1: cx + halfW, y1: cy + halfH };
}

function drawCopperLabels(
  ctx: CanvasRenderingContext2D,
  scene: PcbScene,
  layers: LayerInfo[],
  visible: Map<string, boolean>,
  pxPerMm: number
): void {
  if (pxPerMm < MIN_ZOOM_FOR_ZONE_LABELS) return;

  const copperIds: string[] = [
    'F.Cu',
    ...layers.filter((l) => l.type === 'In.Cu').map((l) => l.id),
    'B.Cu'
  ];
  const seenPads = new Set<Pad>();
  const placed: LabelBox[] = [];

  // Zones first: they cover large areas, and any track/pad label that lands
  // on top of a zone label just becomes unreadable. One label per
  // (layer, net) at the largest polygon's centroid.
  for (const id of copperIds) {
    const l = layers.find((x) => x.id === id);
    if (!l || !visible.get(l.id)) continue;
    const buckets = scene.byLayer.get(l.id);
    if (!buckets) continue;

    const zoneByNet = new Map<string, { polygon: Point[]; area: number }>();
    for (const z of buckets.zones) {
      if (!z.netName || z.polygon.length < 3) continue;
      const area = Math.abs(polygonSignedArea(z.polygon));
      const prev = zoneByNet.get(z.netName);
      if (!prev || area > prev.area) zoneByNet.set(z.netName, { polygon: z.polygon, area });
    }
    for (const [netName, info] of zoneByNet) {
      drawZoneLabel(ctx, info.polygon, netName, pxPerMm, placed);
    }
  }

  // Pads: numbers always (subject to readable size); net names only at higher
  // zoom so they don't clutter far-out views.
  const showPadNets = pxPerMm >= MIN_ZOOM_FOR_PAD_NET;
  for (const id of copperIds) {
    const l = layers.find((x) => x.id === id);
    if (!l || !visible.get(l.id)) continue;
    const buckets = scene.byLayer.get(l.id);
    if (!buckets) continue;
    for (const { fp, pad } of buckets.pads) {
      if (seenPads.has(pad)) continue;
      seenPads.add(pad);
      drawPadLabel(ctx, fp, pad, pxPerMm, showPadNets, placed);
    }
  }

  // Tracks last: skipped entirely at low zoom, collision-filtered at high zoom.
  // Per-net centers lets us enforce a minimum spacing between labels on the
  // same net so a single long trace gets one label, not one per segment.
  if (pxPerMm >= MIN_ZOOM_FOR_TRACK_LABELS) {
    const perNetCenters = new Map<string, Array<{ x: number; y: number }>>();
    for (const id of copperIds) {
      const l = layers.find((x) => x.id === id);
      if (!l || !visible.get(l.id)) continue;
      const buckets = scene.byLayer.get(l.id);
      if (!buckets) continue;
      for (const t of buckets.tracks) {
        if (!t.netName) continue;
        drawTrackLabel(ctx, t, pxPerMm, placed, perNetCenters);
      }
    }
  }
}

function drawTrackLabel(
  ctx: CanvasRenderingContext2D,
  t: TrackSeg,
  pxPerMm: number,
  placed: LabelBox[],
  perNetCenters: Map<string, Array<{ x: number; y: number }>>
): void {
  if (!t.netName) return;
  const dx = t.b.x - t.a.x;
  const dy = t.b.y - t.a.y;
  const lengthMm = Math.hypot(dx, dy);
  if (lengthMm <= 0) return;

  const heightMm = TRACK_LABEL_PX / pxPerMm;
  const approxWidthMm = t.netName.length * heightMm * 0.55;
  // Need the segment to fit the label with a margin on each side; keeps
  // labels off short stubs between vias.
  if (approxWidthMm > lengthMm * 0.85) return;

  const mx = (t.a.x + t.b.x) / 2;
  const my = (t.a.y + t.b.y) / 2;

  // Skip if there's already a same-net label within SAME_NET_MIN_SPACING_MM.
  // One label per long trace is plenty; this trace just repeats it elsewhere.
  const existing = perNetCenters.get(t.netName);
  if (existing) {
    for (const c of existing) {
      if (Math.hypot(c.x - mx, c.y - my) < SAME_NET_MIN_SPACING_MM) return;
    }
  }

  let angle = Math.atan2(dy, dx);
  if (angle > Math.PI / 2) angle -= Math.PI;
  else if (angle < -Math.PI / 2) angle += Math.PI;

  const box = rotatedLabelBox(mx, my, approxWidthMm, heightMm * 1.2, angle);
  if (placed.some((p) => bboxesOverlap(p, box))) return;
  placed.push(box);

  const centers = perNetCenters.get(t.netName) ?? [];
  centers.push({ x: mx, y: my });
  perNetCenters.set(t.netName, centers);

  ctx.save();
  ctx.translate(mx, my);
  ctx.rotate(angle);
  ctx.font = `${heightMm}px ui-sans-serif, system-ui, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = 'rgba(255,255,255,0.95)';
  ctx.strokeStyle = 'rgba(0,0,0,0.55)';
  ctx.lineWidth = heightMm * 0.25;
  ctx.strokeText(t.netName, 0, 0);
  ctx.fillText(t.netName, 0, 0);
  ctx.restore();
}

function drawPadLabel(
  ctx: CanvasRenderingContext2D,
  fp: FootprintGeom,
  pad: Pad,
  pxPerMm: number,
  showNet: boolean,
  placed: LabelBox[]
): void {
  const { sizeMm: sz } = pad;
  if (sz.w <= 0 || sz.h <= 0) return;

  const numH = PAD_NUM_PX / pxPerMm;
  const minDim = Math.min(sz.w, sz.h);
  if (numH > minDim * 1.3) return;

  // Compute the pad's world-frame center for collision bookkeeping.
  const fpCos = Math.cos((fp.rotationDeg * Math.PI) / 180);
  const fpSin = Math.sin((fp.rotationDeg * Math.PI) / 180);
  const mirror = fp.side === 'bottom' ? -1 : 1;
  const localX = pad.positionMm.x * mirror;
  const worldCx = fp.position.x + fpCos * localX - fpSin * pad.positionMm.y;
  const worldCy = fp.position.y + fpSin * localX + fpCos * pad.positionMm.y;

  const worldDeg = fp.side === 'bottom' ? -fp.rotationDeg : fp.rotationDeg;
  const norm = ((worldDeg % 360) + 360) % 360;
  const flip = norm > 90 && norm < 270;

  // Track the number's bbox so tracks can't stomp it. Uses pad extents as a
  // safe upper bound for how much screen real-estate the number occupies.
  placed.push({
    x0: worldCx - sz.w / 2,
    y0: worldCy - sz.h / 2,
    x1: worldCx + sz.w / 2,
    y1: worldCy + sz.h / 2
  });

  ctx.save();
  ctx.translate(fp.position.x, fp.position.y);
  if (fp.side === 'bottom') ctx.scale(-1, 1);
  ctx.rotate((fp.rotationDeg * Math.PI) / 180);
  ctx.translate(pad.positionMm.x, pad.positionMm.y);
  if (flip) ctx.rotate(Math.PI);

  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = 'rgba(255,255,255,0.95)';
  ctx.strokeStyle = 'rgba(0,0,0,0.5)';

  if (showNet && pad.netName) {
    ctx.font = `600 ${numH}px ui-sans-serif, system-ui, sans-serif`;
    ctx.lineWidth = numH * 0.18;
    ctx.strokeText(pad.number, 0, -numH * 0.6);
    ctx.fillText(pad.number, 0, -numH * 0.6);

    const netH = PAD_NET_PX / pxPerMm;
    ctx.font = `${netH}px ui-sans-serif, system-ui, sans-serif`;
    ctx.lineWidth = netH * 0.22;
    ctx.strokeText(pad.netName, 0, netH * 0.7);
    ctx.fillText(pad.netName, 0, netH * 0.7);
  } else {
    ctx.font = `600 ${numH}px ui-sans-serif, system-ui, sans-serif`;
    ctx.lineWidth = numH * 0.18;
    ctx.strokeText(pad.number, 0, 0);
    ctx.fillText(pad.number, 0, 0);
  }

  ctx.restore();
}

function drawZoneLabel(
  ctx: CanvasRenderingContext2D,
  poly: Point[],
  netName: string,
  pxPerMm: number,
  placed: LabelBox[]
): void {
  const c = polygonCentroid(poly);
  if (!c) return;
  const heightMm = ZONE_LABEL_PX / pxPerMm;
  const approxWidthMm = netName.length * heightMm * 0.55;
  const box = rotatedLabelBox(c.x, c.y, approxWidthMm, heightMm * 1.2, 0);
  if (placed.some((p) => bboxesOverlap(p, box))) return;
  placed.push(box);

  ctx.save();
  ctx.font = `${heightMm}px ui-sans-serif, system-ui, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = 'rgba(255,255,255,0.9)';
  ctx.strokeStyle = 'rgba(0,0,0,0.55)';
  ctx.lineWidth = heightMm * 0.22;
  ctx.strokeText(netName, c.x, c.y);
  ctx.fillText(netName, c.x, c.y);
  ctx.restore();
}

function polygonSignedArea(poly: Point[]): number {
  let a = 0;
  for (let i = 0; i < poly.length; i++) {
    const p0 = poly[i]!;
    const p1 = poly[(i + 1) % poly.length]!;
    a += p0.x * p1.y - p1.x * p0.y;
  }
  return a / 2;
}

function polygonCentroid(poly: Point[]): Point | null {
  if (poly.length === 0) return null;
  let cx = 0;
  let cy = 0;
  let area2 = 0;
  for (let i = 0; i < poly.length; i++) {
    const p0 = poly[i]!;
    const p1 = poly[(i + 1) % poly.length]!;
    const cross = p0.x * p1.y - p1.x * p0.y;
    cx += (p0.x + p1.x) * cross;
    cy += (p0.y + p1.y) * cross;
    area2 += cross;
  }
  if (Math.abs(area2) < 1e-9) {
    // Degenerate (collinear) — fall back to vertex average.
    let ax = 0;
    let ay = 0;
    for (const p of poly) {
      ax += p.x;
      ay += p.y;
    }
    return { x: ax / poly.length, y: ay / poly.length };
  }
  const factor = 1 / (3 * area2);
  return { x: cx * factor, y: cy * factor };
}

function drawGrid(ctx: CanvasRenderingContext2D, scene: PcbScene, viewport: Viewport): void {
  const pxPerMm = viewport.scale;
  // Hide grid when too zoomed-out (lines too dense) — at higher zoom it's still useful.
  if (pxPerMm < 0.8) return;

  // Pick grid step based on zoom: finer step at higher zoom
  let stepMm = 1;
  if (pxPerMm < 2) stepMm = 5;
  else if (pxPerMm < 10) stepMm = 1;
  else stepMm = 0.25;

  const bounds = scene.boundsMm;
  // Extend grid a bit beyond board bounds so user sees it near edges.
  const pad = Math.max(bounds.w, bounds.h) * 0.2 || 50;
  const x0 = Math.floor((bounds.x - pad) / stepMm) * stepMm;
  const y0 = Math.floor((bounds.y - pad) / stepMm) * stepMm;
  const x1 = Math.ceil((bounds.x + bounds.w + pad) / stepMm) * stepMm;
  const y1 = Math.ceil((bounds.y + bounds.h + pad) / stepMm) * stepMm;

  ctx.save();
  ctx.strokeStyle = '#2a303a';
  ctx.lineWidth = 0.04;

  ctx.beginPath();
  for (let x = x0; x <= x1; x += stepMm) {
    ctx.moveTo(x, y0);
    ctx.lineTo(x, y1);
  }
  for (let y = y0; y <= y1; y += stepMm) {
    ctx.moveTo(x0, y);
    ctx.lineTo(x1, y);
  }
  ctx.stroke();

  // Major gridlines every 10 steps
  ctx.strokeStyle = '#3a404a';
  ctx.lineWidth = 0.08;
  ctx.beginPath();
  const majorStep = stepMm * 10;
  for (let x = Math.floor(x0 / majorStep) * majorStep; x <= x1; x += majorStep) {
    ctx.moveTo(x, y0);
    ctx.lineTo(x, y1);
  }
  for (let y = Math.floor(y0 / majorStep) * majorStep; y <= y1; y += majorStep) {
    ctx.moveTo(x0, y);
    ctx.lineTo(x1, y);
  }
  ctx.stroke();

  ctx.restore();
}

function drawDrillHoles(ctx: CanvasRenderingContext2D, scene: PcbScene): void {
  // Near-black so the hole reads as "punched through" on dark or light themes.
  ctx.fillStyle = '#0a0d12';
  // Through-hole pads: transform into each footprint's local frame, then punch.
  for (const fp of scene.footprints) {
    if (!fp.pads) continue;
    for (const pad of fp.pads) {
      if (!pad.drillMm || pad.drillMm <= 0) continue;
      ctx.save();
      ctx.translate(fp.position.x, fp.position.y);
      if (fp.side === 'bottom') ctx.scale(-1, 1);
      ctx.rotate((fp.rotationDeg * Math.PI) / 180);
      ctx.beginPath();
      ctx.arc(pad.positionMm.x, pad.positionMm.y, pad.drillMm / 2, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
  }
  // Vias: scene.ts places them on only one layer bucket, so iterate once across
  // buckets to pick them up without double-drawing.
  const seenVia = new Set<object>();
  for (const [, buckets] of scene.byLayer) {
    for (const v of buckets.vias) {
      if (seenVia.has(v)) continue;
      seenVia.add(v);
      if (!v.drillMm || v.drillMm <= 0) continue;
      ctx.beginPath();
      ctx.arc(v.position.x, v.position.y, v.drillMm / 2, 0, Math.PI * 2);
      ctx.fill();
    }
  }
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

  // Pads (before tracks so tracks land on top where they overlap)
  for (const { fp, pad } of buckets.pads) {
    ctx.save();
    ctx.translate(fp.position.x, fp.position.y);
    if (fp.side === 'bottom') ctx.scale(-1, 1);
    ctx.rotate((fp.rotationDeg * Math.PI) / 180);
    drawPadShape(ctx, pad);
    ctx.restore();
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

  // Footprint graphics (silk/fab/courtyard lines, polygons, arcs, text)
  for (const g of buckets.graphics) {
    const fp = g.from;
    const graphic = fp.graphics[g.idx];
    if (!graphic) continue;
    drawGraphic(ctx, graphic.geom, fp.position, fp.rotationDeg, fp.side);
  }

  // Board-level graphics (edge cuts, free drawings) — no per-footprint transform.
  for (const bg of buckets.boardGraphics) {
    drawGraphic(ctx, bg.geom, { x: 0, y: 0 }, 0, 'top');
  }
}

function drawPadShape(ctx: CanvasRenderingContext2D, pad: Pad): void {
  const { positionMm: pos, sizeMm: sz, shape } = pad;
  if (sz.w <= 0 || sz.h <= 0) return;
  ctx.beginPath();
  if (shape === 'circle' || (shape === 'oval' && sz.w === sz.h)) {
    ctx.arc(pos.x, pos.y, sz.w / 2, 0, Math.PI * 2);
  } else if (shape === 'oval') {
    ctx.ellipse(pos.x, pos.y, sz.w / 2, sz.h / 2, 0, 0, Math.PI * 2);
  } else if (shape === 'roundrect') {
    const r = Math.min(0.2, Math.min(sz.w, sz.h) / 4);
    roundRect(ctx, pos.x - sz.w / 2, pos.y - sz.h / 2, sz.w, sz.h, r);
  } else {
    // rect, trapezoid, custom — fall back to rect
    ctx.rect(pos.x - sz.w / 2, pos.y - sz.h / 2, sz.w, sz.h);
  }
  ctx.fill();
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number
): void {
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
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
    ctx.save();
    ctx.translate(s.position.x, s.position.y);
    ctx.rotate((s.rotationDeg * Math.PI) / 180);
    // For bottom-side footprints, the outer transform mirrored the canvas X axis
    // to flip silk/fab geometry. For text we want it to read top-view correctly,
    // so counter-mirror here.
    if (side === 'bottom') ctx.scale(-1, 1);
    const heightPx = Math.max(0.8, s.heightMm);
    ctx.fillStyle = ctx.strokeStyle;
    ctx.font = `${heightPx}px ui-sans-serif, system-ui, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(s.text, 0, 0);
    ctx.restore();
  }

  ctx.restore();
}
