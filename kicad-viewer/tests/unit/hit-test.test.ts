import { describe, it, expect } from 'vitest';
import {
  pointToSegmentDistMm,
  pointInPolygon,
  hitTrack,
  hitVia,
  hitZone,
  trackLengthMm,
  polygonAreaMm2
} from '$lib/pcb/hit-test';
import type { TrackSeg, Via, Zone } from '$lib/model/project';

describe('pointToSegmentDistMm', () => {
  it('returns 0 on the segment', () => {
    expect(pointToSegmentDistMm(5, 0, { x: 0, y: 0 }, { x: 10, y: 0 })).toBe(0);
  });
  it('handles perpendicular distance', () => {
    expect(pointToSegmentDistMm(5, 3, { x: 0, y: 0 }, { x: 10, y: 0 })).toBe(3);
  });
  it('handles distance past endpoint', () => {
    expect(pointToSegmentDistMm(12, 0, { x: 0, y: 0 }, { x: 10, y: 0 })).toBe(2);
  });
  it('handles zero-length segment', () => {
    expect(pointToSegmentDistMm(3, 4, { x: 0, y: 0 }, { x: 0, y: 0 })).toBe(5);
  });
});

describe('hitTrack', () => {
  const t: TrackSeg = {
    layerId: 'F.Cu',
    a: { x: 0, y: 0 },
    b: { x: 10, y: 0 },
    widthMm: 0.5,
    netName: 'X'
  };
  it('hits within half-width', () => {
    expect(hitTrack(5, 0.2, t)).toBe(true);
  });
  it('misses outside half-width', () => {
    expect(hitTrack(5, 0.5, t)).toBe(false);
  });
  it('hits with slop', () => {
    expect(hitTrack(5, 0.4, t, 0.2)).toBe(true);
  });
});

describe('hitVia', () => {
  const v: Via = {
    position: { x: 10, y: 10 },
    diameterMm: 1,
    drillMm: 0.4,
    layerFrom: 'F.Cu',
    layerTo: 'B.Cu',
    netName: 'X'
  };
  it('hits inside radius', () => {
    expect(hitVia(10.3, 10, v)).toBe(true);
  });
  it('misses outside radius', () => {
    expect(hitVia(11, 10, v)).toBe(false);
  });
});

describe('pointInPolygon + hitZone', () => {
  const square = [
    { x: 0, y: 0 },
    { x: 10, y: 0 },
    { x: 10, y: 10 },
    { x: 0, y: 10 }
  ];
  it('hits interior', () => {
    expect(pointInPolygon(5, 5, square)).toBe(true);
  });
  it('misses exterior', () => {
    expect(pointInPolygon(-1, 5, square)).toBe(false);
  });
  it('hitZone wraps polygon', () => {
    const z: Zone = { layerId: 'F.Cu', polygon: square, netName: 'GND' };
    expect(hitZone(5, 5, z)).toBe(true);
    expect(hitZone(-1, 5, z)).toBe(false);
  });
  it('hitZone rejects degenerate polygons', () => {
    const z: Zone = { layerId: 'F.Cu', polygon: [{ x: 0, y: 0 }, { x: 1, y: 1 }], netName: 'GND' };
    expect(hitZone(0.5, 0.5, z)).toBe(false);
  });
});

describe('metrics', () => {
  it('trackLengthMm', () => {
    const t: TrackSeg = {
      layerId: 'F.Cu',
      a: { x: 0, y: 0 },
      b: { x: 3, y: 4 },
      widthMm: 0.2,
      netName: 'X'
    };
    expect(trackLengthMm(t)).toBe(5);
  });
  it('polygonAreaMm2 for unit square', () => {
    const square = [
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 1, y: 1 },
      { x: 0, y: 1 }
    ];
    expect(polygonAreaMm2(square)).toBe(1);
  });
});
