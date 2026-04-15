import type { PcbScene } from './scene';
import type { LayerInfo, GraphicGeom, Pad, Point, TrackSeg, Via, Zone, FootprintGeom } from '$lib/model/project';
import { computeDrawOrder } from './draw-order';
import { classifyLayer } from './layer-side';

export interface Viewport {
  x: number;
  y: number;
  scale: number;
}

export interface SelectedGeom {
  kind: 'track' | 'zone' | 'via';
  idx: number;
}

export function drawPcb(
  ctx: CanvasRenderingContext2D,
  scene: PcbScene,
  layers: LayerInfo[],
  visible: Map<string, boolean>,
  viewport: Viewport,
  activeLayer: string,
  inactiveOpacity: number,
  selectedFootprint?: string | null,
  highlightedNet?: string | null,
  selectedGeom?: SelectedGeom | null,
  projectTracks?: TrackSeg[],
  projectZones?: Zone[],
  projectVias?: Via[]
): void {
  const { width, height } = ctx.canvas;
  ctx.clearRect(0, 0, width, height);

  ctx.save();
  ctx.translate(viewport.x, viewport.y);
  ctx.scale(viewport.scale, viewport.scale);
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  drawGrid(ctx, scene, viewport);

  // Bottom-to-top draw order computed from the active layer's side. Layers on
  // the opposite side of the active copper render first and dimmed.
  const activeSideRaw = classifyLayer(activeLayer, layers);
  const activeSide: 'front' | 'back' = activeSideRaw === 'back' ? 'back' : 'front';
  const ordered = computeDrawOrder(layers, activeLayer);
  for (const l of ordered) {
    if (!visible.get(l.id)) continue;
    const side = classifyLayer(l.id, layers);
    const isActive = side === 'board' || side === activeSide;
    drawLayer(ctx, scene, l, isActive ? 1.0 : inactiveOpacity);
  }

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
    // Fog over everything (already drawn at this point). Then re-paint
    // matching geometry on top in its own layer color plus a bright accent
    // outline so the net pops. The fog rect is sized to the scene bounds with
    // a generous pad so it covers any off-board scribbles.
    const b = scene.boundsMm;
    const pad = Math.max(b.w, b.h) * 2;
    ctx.save();
    ctx.fillStyle = 'rgba(0, 0, 0, 0.72)';
    ctx.fillRect(b.x - pad, b.y - pad, b.w + pad * 2, b.h + pad * 2);
    ctx.restore();

    const seenPads = new Set<Pad>();
    const accent = '#ffd54a';
    const accentLW = Math.max(0.05, 1.5 / viewport.scale);

    for (const l of ordered) {
      if (!visible.get(l.id)) continue;
      const buckets = scene.byLayer.get(l.id);
      if (!buckets) continue;
      ctx.strokeStyle = l.defaultColor;
      ctx.fillStyle = l.defaultColor;

      // Zones on the highlighted net
      for (const z of buckets.zones) {
        if (z.netName !== highlightedNet || z.polygon.length < 3) continue;
        ctx.globalAlpha = 0.6;
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

      // Pads on the net (dedupe across layer buckets)
      for (const { fp, pad: p } of buckets.pads) {
        if (p.netName !== highlightedNet) continue;
        if (seenPads.has(p)) continue;
        seenPads.add(p);
        ctx.save();
        ctx.translate(fp.position.x, fp.position.y);
        if (fp.side === 'bottom') ctx.scale(-1, 1);
        ctx.rotate((fp.rotationDeg * Math.PI) / 180);
        ctx.fillStyle = l.defaultColor;
        drawPadShape(ctx, p);
        ctx.restore();
      }

      // Tracks on the net
      for (const t of buckets.tracks) {
        if (t.netName !== highlightedNet) continue;
        ctx.strokeStyle = l.defaultColor;
        ctx.lineWidth = t.widthMm;
        ctx.beginPath();
        ctx.moveTo(t.a.x, t.a.y);
        ctx.lineTo(t.b.x, t.b.y);
        ctx.stroke();
      }

      // Vias on the net
      for (const v of buckets.vias) {
        if (v.netName !== highlightedNet) continue;
        ctx.fillStyle = l.defaultColor;
        ctx.beginPath();
        ctx.arc(v.position.x, v.position.y, v.diameterMm / 2, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // Accent outline pass — one more lap to draw bright strokes around
    // highlighted tracks/vias/pads so they read at a glance.
    ctx.strokeStyle = accent;
    ctx.lineWidth = accentLW;
    seenPads.clear();
    for (const l of ordered) {
      if (!visible.get(l.id)) continue;
      const buckets = scene.byLayer.get(l.id);
      if (!buckets) continue;
      for (const t of buckets.tracks) {
        if (t.netName !== highlightedNet) continue;
        ctx.beginPath();
        ctx.moveTo(t.a.x, t.a.y);
        ctx.lineTo(t.b.x, t.b.y);
        ctx.stroke();
      }
      for (const v of buckets.vias) {
        if (v.netName !== highlightedNet) continue;
        ctx.beginPath();
        ctx.arc(v.position.x, v.position.y, v.diameterMm / 2 + accentLW, 0, Math.PI * 2);
        ctx.stroke();
      }
    }

    // Drill holes re-cut through the repainted copper.
    drawDrillHoles(ctx, scene);
  }

  // Selection overlay for an individual copper feature (track/zone/via).
  if (selectedGeom) {
    ctx.save();
    ctx.strokeStyle = '#6aa6ff';
    ctx.lineWidth = Math.max(0.08, 2 / viewport.scale);
    if (selectedGeom.kind === 'track' && projectTracks) {
      const t = projectTracks[selectedGeom.idx];
      if (t) {
        ctx.lineWidth = Math.max(t.widthMm + 0.15, 3 / viewport.scale);
        ctx.strokeStyle = '#6aa6ff';
        ctx.beginPath();
        ctx.moveTo(t.a.x, t.a.y);
        ctx.lineTo(t.b.x, t.b.y);
        ctx.stroke();
      }
    } else if (selectedGeom.kind === 'zone' && projectZones) {
      const z = projectZones[selectedGeom.idx];
      if (z && z.polygon.length >= 3) {
        ctx.beginPath();
        const p0 = z.polygon[0]!;
        ctx.moveTo(p0.x, p0.y);
        for (let i = 1; i < z.polygon.length; i++) {
          const pt = z.polygon[i]!;
          ctx.lineTo(pt.x, pt.y);
        }
        ctx.closePath();
        ctx.stroke();
      }
    } else if (selectedGeom.kind === 'via' && projectVias) {
      const v = projectVias[selectedGeom.idx];
      if (v) {
        ctx.beginPath();
        ctx.arc(v.position.x, v.position.y, v.diameterMm / 2 + 0.1, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  // Labels — only at sufficient zoom
  const pxPerMm = viewport.scale;

  // Refdes: target ~12 CSS px on screen through mid zoom, capped at 1.5mm
  // world so it doesn't explode at extreme zoom-in.
  const refdesHeightMm = Math.min(1.5, 12 / pxPerMm);
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

  drawCopperLabels(ctx, scene, layers, visible, pxPerMm, activeLayer);

  ctx.restore();
}

// ---------- copper labels (net names on tracks, pads, zones; pad numbers) ----------

// Label sizing: a hybrid of screen-relative and world-space clamps.
//   heightMm = clamp(TARGET_PX / pxPerMm, MIN_WORLD_MM, MAX_WORLD_MM)
// This keeps labels at roughly a fixed screen size through the mid-zoom range
// (where TARGET_PX / pxPerMm lands inside the clamp window), grows them with
// zoom-in once the world floor kicks in, and hides them at zoom-out once the
// MAX_WORLD clamp pushes the on-screen height below MIN_READABLE_PX.
const MIN_READABLE_PX = 6;
// Track labels default to the trace's own width (so the label naturally grows
// with zoom and reads as "belonging to" that trace). Clamped to a sane range,
// and shrunk proportionally if the label would overflow the segment length.
const TRACK_BASE_MIN_MM = 0.2;
const TRACK_BASE_MAX_MM = 1.2;
// At moderate zoom we also want a minimum screen height so very thin traces
// still get readable labels — clamps the shrunk value back up.
const TRACK_MIN_SCREEN_PX = 8;
// Pads: fraction of the pad's short dimension for sane defaults, with a small
// world-size floor for readability at extreme zoom-in and a tight cap so big
// thermal/connector pads don't get huge text.
const PAD_NUM_FRACTION = 0.28;
const PAD_NET_FRACTION = 0.2;
const PAD_NUM_MIN_WORLD_MM = 0.28;
const PAD_NUM_MAX_WORLD_MM = 0.8;
// Net names get rendered as pad subtitles only when the pad is big enough to
// warrant it — connectors, thermal pads, large SMD. Small IC pins would just
// paint the same name over every pin, which is redundant with track labels.
const PAD_NET_MIN_DIM_MM = 1.8;
const ZONE_LABEL_FRACTION = 0.05; // fraction of zone bbox min dim
const ZONE_LABEL_MIN_MM = 1.2;
const ZONE_LABEL_MAX_MM = 6;
// Via labels: size the label to fit *inside* the via (like KiCad does) so it
// reads as "belonging to" the via rather than drowning its neighborhood. Text
// height is capped at a fraction of diameter so short nets don't look huge;
// otherwise height is driven by the requirement that the label width <=
// ~0.9 × diameter. Labels below VIA_LABEL_MIN_SCREEN_PX are skipped.
const VIA_LABEL_HEIGHT_CAP_FRACTION = 0.45;
const VIA_LABEL_WIDTH_FIT_FRACTION = 0.9;
const VIA_LABEL_MIN_SCREEN_PX = 7;
// Minimum on-screen separation between two labels for the *same* net. Using
// screen space (not world space) means dense labels at high zoom and wide
// spacing at low zoom — proportional to how much board you can actually see.
const SAME_NET_MIN_SPACING_PX = 160;
// Once zoomed in past this, we expect every trace to carry its own label so
// the user can read routing without panning. Above the threshold we skip the
// "label must fit within segment" check and drop the same-net spacing to
// zero; different-net collision still prevents pile-ups.
const FULL_LABELS_ZOOM_PX_PER_MM = 18;

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
  pxPerMm: number,
  activeLayer: string
): void {
  const copperIds: string[] = [activeLayer];
  const seenPads = new Set<Pad>();
  const placed: LabelBox[] = [];

  // Zones first — they cover large areas; anything layered on top becomes
  // unreadable, so let them claim space early.
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

  for (const id of copperIds) {
    const l = layers.find((x) => x.id === id);
    if (!l || !visible.get(l.id)) continue;
    const buckets = scene.byLayer.get(l.id);
    if (!buckets) continue;
    for (const { fp, pad } of buckets.pads) {
      if (seenPads.has(pad)) continue;
      seenPads.add(pad);
      drawPadLabel(ctx, fp, pad, pxPerMm, placed);
    }
  }

  // Vias: label every via regardless of active layer. Vias are drilled holes
  // that connect layers, so their net applies everywhere — matches KiCad's
  // behavior. Walk every bucket since buildPcbScene files each via only under
  // its layerFrom.
  const seenVias = new Set<Via>();
  for (const [, buckets] of scene.byLayer) {
    for (const v of buckets.vias) {
      if (seenVias.has(v)) continue;
      seenVias.add(v);
      if (!v.netName) continue;
      drawViaLabel(ctx, v, pxPerMm, placed);
    }
  }

  // Tracks last. Per-net centers enforces minimum spacing so a single long
  // trace gets one label, not one per segment.
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

  // Feature-relative baseline: label height matches the trace width, so the
  // label is visually tied to its trace and grows with zoom alongside it.
  // Clamp to [MIN, MAX] for sanity.
  let heightMm = Math.min(TRACK_BASE_MAX_MM, Math.max(TRACK_BASE_MIN_MM, t.widthMm));

  // If the label would overflow the segment, shrink the whole label
  // proportionally until it fits — keeps the label linked to its trace
  // instead of bleeding onto neighbors.
  const maxLabelWidthMm = lengthMm * 0.95;
  const baseWidthMm = t.netName.length * heightMm * 0.55;
  if (baseWidthMm > maxLabelWidthMm) {
    heightMm *= maxLabelWidthMm / baseWidthMm;
  }

  // But don't go below a readable screen size. Above the full-labels zoom
  // threshold we also let labels overflow the segment (they'll just extend
  // past the endpoints) so every trace gets named when you're zoomed in.
  const minHeightMm = TRACK_MIN_SCREEN_PX / pxPerMm;
  if (heightMm < minHeightMm) {
    if (pxPerMm >= FULL_LABELS_ZOOM_PX_PER_MM) {
      heightMm = minHeightMm;
    } else {
      return;
    }
  }
  if (heightMm * pxPerMm < MIN_READABLE_PX) return;

  const approxWidthMm = t.netName.length * heightMm * 0.55;

  const mx = (t.a.x + t.b.x) / 2;
  const my = (t.a.y + t.b.y) / 2;

  // Skip if there's already a same-net label within SAME_NET_MIN_SPACING_PX
  // on screen. Above FULL_LABELS_ZOOM_PX_PER_MM we drop this check — when
  // you're zoomed in to read routing, you want every trace's label, not one
  // per-neighborhood.
  if (pxPerMm < FULL_LABELS_ZOOM_PX_PER_MM) {
    const minSpacingMm = SAME_NET_MIN_SPACING_PX / pxPerMm;
    const existing = perNetCenters.get(t.netName);
    if (existing) {
      for (const c of existing) {
        if (Math.hypot(c.x - mx, c.y - my) < minSpacingMm) return;
      }
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

function drawViaLabel(
  ctx: CanvasRenderingContext2D,
  v: Via,
  pxPerMm: number,
  placed: LabelBox[]
): void {
  if (!v.netName || v.diameterMm <= 0) return;

  // Fit the label's width inside the via. Derive height from "width <= 0.9 × D"
  // (characters ≈ 0.55 × h wide), then cap at 45% of the via diameter so short
  // nets like "5V" don't balloon past the via.
  const chars = Math.max(1, v.netName.length);
  const widthFitHeightMm = (v.diameterMm * VIA_LABEL_WIDTH_FIT_FRACTION) / (chars * 0.55);
  const heightMm = Math.min(widthFitHeightMm, v.diameterMm * VIA_LABEL_HEIGHT_CAP_FRACTION);
  if (heightMm * pxPerMm < VIA_LABEL_MIN_SCREEN_PX) return;

  const approxWidthMm = chars * heightMm * 0.55;
  const box = rotatedLabelBox(v.position.x, v.position.y, approxWidthMm, heightMm * 1.2, 0);
  if (placed.some((p) => bboxesOverlap(p, box))) return;
  placed.push(box);

  ctx.save();
  ctx.font = `${heightMm}px ui-sans-serif, system-ui, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = 'rgba(255,255,255,0.95)';
  ctx.strokeStyle = 'rgba(0,0,0,0.7)';
  ctx.lineWidth = Math.max(0.02, heightMm * 0.15);
  ctx.strokeText(v.netName, v.position.x, v.position.y);
  ctx.fillText(v.netName, v.position.x, v.position.y);
  ctx.restore();
}

function drawPadLabel(
  ctx: CanvasRenderingContext2D,
  fp: FootprintGeom,
  pad: Pad,
  pxPerMm: number,
  placed: LabelBox[]
): void {
  const { sizeMm: sz } = pad;
  if (sz.w <= 0 || sz.h <= 0) return;

  // Feature-relative sizing for the pad number, clamped to a readable range.
  // The min floor keeps tiny pads legible at high zoom; the max cap stops
  // giant pads (thermal slugs, big connector holes) from getting huge labels.
  const minDim = Math.min(sz.w, sz.h);
  const numH = Math.min(
    PAD_NUM_MAX_WORLD_MM,
    Math.max(minDim * PAD_NUM_FRACTION, PAD_NUM_MIN_WORLD_MM)
  );
  if (numH * pxPerMm < MIN_READABLE_PX) return;
  const netH = Math.min(
    PAD_NUM_MAX_WORLD_MM * 0.8,
    Math.max(minDim * PAD_NET_FRACTION, PAD_NUM_MIN_WORLD_MM * 0.8)
  );
  // Only annotate pads big enough to carry both lines cleanly. Small IC pins
  // skip the net name — tracks carry that information for them.
  const showNet = pad.netName !== null && pad.netName !== undefined
    && minDim >= PAD_NET_MIN_DIM_MM
    && netH * pxPerMm >= MIN_READABLE_PX
    && pad.netName.length * netH * 0.55 <= Math.max(sz.w, sz.h) * 1.4;

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

  // Reserve just the rendered text footprint (not the whole pad), so a track
  // label running past the pad can sit comfortably next to the pin number.
  // If we also render a net name, extend the reserved height to cover it.
  const numW = pad.number.length * numH * 0.55;
  const totalTextH = showNet && pad.netName
    ? numH + netH + numH * 0.3
    : numH;
  const totalTextW = showNet && pad.netName
    ? Math.max(numW, pad.netName.length * netH * 0.55)
    : numW;
  placed.push({
    x0: worldCx - totalTextW / 2,
    y0: worldCy - totalTextH / 2,
    x1: worldCx + totalTextW / 2,
    y1: worldCy + totalTextH / 2
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

  // Feature-relative: base height on the zone's bbox so bigger zones (ground
  // pours covering most of the board) get bigger labels, smaller copper
  // islands get smaller ones. Clamped to a sane range.
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const p of poly) {
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  const bboxMin = Math.min(maxX - minX, maxY - minY);
  const heightMm = Math.min(
    ZONE_LABEL_MAX_MM,
    Math.max(ZONE_LABEL_MIN_MM, bboxMin * ZONE_LABEL_FRACTION)
  );
  if (heightMm * pxPerMm < MIN_READABLE_PX) return;

  const approxWidthMm = netName.length * heightMm * 0.55;
  // Don't draw a zone label that overflows the zone's bbox — looks like it
  // belongs to something else.
  if (approxWidthMm > (maxX - minX) * 0.95) return;

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

function drawLayer(
  ctx: CanvasRenderingContext2D,
  scene: PcbScene,
  layer: LayerInfo,
  baseOpacity: number = 1.0
): void {
  const buckets = scene.byLayer.get(layer.id);
  if (!buckets) return;
  const prevAlpha = ctx.globalAlpha;
  ctx.globalAlpha = baseOpacity;
  ctx.strokeStyle = layer.defaultColor;
  ctx.fillStyle = layer.defaultColor;

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

  ctx.globalAlpha = prevAlpha;
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
