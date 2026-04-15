import { describe, it, expect } from 'vitest';
import { buildPcbScene } from '$lib/pcb/scene';
import type { Project } from '$lib/model/project';

const baseProject = (): Project => ({
  name: 'x', sheets: [], components: [], nets: [], source: 'raw',
  pcb: {
    boundsMm: { x: 0, y: 0, w: 50, h: 50 },
    layers: [
      { id: 'F.Cu', name: 'F.Cu', type: 'F.Cu', defaultColor: '#c83434' },
      { id: 'Edge.Cuts', name: 'Edge.Cuts', type: 'Edge.Cuts', defaultColor: '#f2eda1' }
    ],
    stackup: [],
    footprints: [{
      uuid: 'u1', refdes: 'R1', position: { x: 10, y: 10 }, rotationDeg: 0, side: 'top',
      bboxMm: { x: 8, y: 9, w: 4, h: 2 }, pads: [], graphics: []
    }],
    tracks: [{ layerId: 'F.Cu', a: { x:0, y:0 }, b: { x:5, y:0 }, widthMm: 0.25, netName: 'VCC' }],
    vias: [], zones: [], drills: []
  }
});

describe('pcb scene', () => {
  it('splits primitives by layer id', () => {
    const scene = buildPcbScene(baseProject());
    expect(scene.byLayer.get('F.Cu')?.tracks.length).toBe(1);
    expect(scene.footprintIndex.ids).toContain('u1');
  });
});
