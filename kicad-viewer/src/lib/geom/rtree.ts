import Flatbush from 'flatbush';

export interface BboxItem { id: string; bbox: { x: number; y: number; w: number; h: number }; }

export interface RtreeIndex {
  fb: Flatbush;
  ids: string[];
}

export function buildRtree(items: BboxItem[]): RtreeIndex {
  if (items.length === 0) {
    const fb = new Flatbush(1);
    fb.add(0, 0, 0, 0);
    fb.finish();
    return { fb, ids: [] };
  }
  const fb = new Flatbush(items.length);
  for (const it of items) {
    fb.add(it.bbox.x, it.bbox.y, it.bbox.x + it.bbox.w, it.bbox.y + it.bbox.h);
  }
  fb.finish();
  return { fb, ids: items.map((i) => i.id) };
}

export function hitPoint(idx: RtreeIndex, x: number, y: number): string[] {
  if (idx.ids.length === 0) return [];
  const hits = idx.fb.search(x, y, x, y);
  return hits.map((i) => idx.ids[i]!);
}
