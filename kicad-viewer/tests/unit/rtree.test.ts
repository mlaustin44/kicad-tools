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

  it('returns empty array for empty index', () => {
    const idx = buildRtree([]);
    expect(hitPoint(idx, 0, 0)).toHaveLength(0);
  });
});
