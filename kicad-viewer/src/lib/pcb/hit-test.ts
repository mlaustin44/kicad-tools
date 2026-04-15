import type { Point, TrackSeg, Via, Zone } from '$lib/model/project';

export function pointToSegmentDistMm(px: number, py: number, a: Point, b: Point): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.hypot(px - a.x, py - a.y);
  let t = ((px - a.x) * dx + (py - a.y) * dy) / lenSq;
  t = Math.max(0, Math.min(1, t));
  const cx = a.x + t * dx;
  const cy = a.y + t * dy;
  return Math.hypot(px - cx, py - cy);
}

export function hitTrack(px: number, py: number, t: TrackSeg, slopMm: number = 0): boolean {
  const d = pointToSegmentDistMm(px, py, t.a, t.b);
  return d <= t.widthMm / 2 + slopMm;
}

export function hitVia(px: number, py: number, v: Via, slopMm: number = 0): boolean {
  const d = Math.hypot(px - v.position.x, py - v.position.y);
  return d <= v.diameterMm / 2 + slopMm;
}

export function pointInPolygon(px: number, py: number, poly: Point[]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i]!;
    const b = poly[j]!;
    const intersect =
      a.y > py !== b.y > py &&
      px < ((b.x - a.x) * (py - a.y)) / (b.y - a.y) + a.x;
    if (intersect) inside = !inside;
  }
  return inside;
}

export function hitZone(px: number, py: number, z: Zone): boolean {
  if (z.polygon.length < 3) return false;
  return pointInPolygon(px, py, z.polygon);
}

export function trackLengthMm(t: TrackSeg): number {
  return Math.hypot(t.b.x - t.a.x, t.b.y - t.a.y);
}

export function polygonAreaMm2(poly: Point[]): number {
  if (poly.length < 3) return 0;
  let sum = 0;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    sum += (poly[j]!.x + poly[i]!.x) * (poly[j]!.y - poly[i]!.y);
  }
  return Math.abs(sum / 2);
}
