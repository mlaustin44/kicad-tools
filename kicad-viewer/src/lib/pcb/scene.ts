import type { Project, FootprintGeom, TrackSeg, Via, Zone, Graphic, Pad } from '$lib/model/project';
import { buildRtree, type RtreeIndex } from '$lib/geom/rtree';

export interface PcbScene {
  boundsMm: Project['pcb']['boundsMm'];
  byLayer: Map<string, LayerBuckets>;
  footprintIndex: RtreeIndex;
  footprints: FootprintGeom[];
}

export interface LayerBuckets {
  tracks: TrackSeg[];
  vias: Via[];
  zones: Zone[];
  graphics: { from: FootprintGeom; idx: number }[];
  boardGraphics: Graphic[];
  pads: Array<{ fp: FootprintGeom; pad: Pad }>;
}

export function buildPcbScene(project: Project): PcbScene {
  const byLayer = new Map<string, LayerBuckets>();
  const ensure = (id: string) => {
    const b = byLayer.get(id);
    if (b) return b;
    const n: LayerBuckets = {
      tracks: [],
      vias: [],
      zones: [],
      graphics: [],
      boardGraphics: [],
      pads: []
    };
    byLayer.set(id, n);
    return n;
  };

  for (const t of project.pcb.tracks)     ensure(t.layerId).tracks.push(t);
  for (const v of project.pcb.vias)       ensure(v.layerFrom).vias.push(v);
  for (const z of project.pcb.zones)      ensure(z.layerId).zones.push(z);
  for (const f of project.pcb.footprints) {
    f.graphics.forEach((g, i) => ensure(g.layerId).graphics.push({ from: f, idx: i }));
    for (const pad of f.pads) {
      for (const layerId of pad.layerIds) {
        ensure(layerId).pads.push({ fp: f, pad });
      }
    }
  }
  for (const bg of project.pcb.boardGraphics ?? []) {
    ensure(bg.layerId).boardGraphics.push(bg);
  }

  const footprintIndex = buildRtree(
    project.pcb.footprints.map((f) => ({ id: f.uuid, bbox: f.bboxMm }))
  );

  return {
    boundsMm: project.pcb.boundsMm,
    byLayer,
    footprintIndex,
    footprints: project.pcb.footprints
  };
}
