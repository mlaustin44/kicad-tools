import { describe, it, expect } from 'vitest';
import { buildSheetSvg } from '$lib/sch/render';
import type { Project, Sheet } from '$lib/model/project';

describe('sch render', () => {
  it('emits an svg string with a viewBox for an empty sheet', () => {
    const sheet: Sheet = {
      uuid: 's', name: 'root', path: ['root'], parent: null,
      componentUuids: [], boundsMm: { x: 0, y: 0, w: 297, h: 210 }
    };
    const project: Project = {
      name: 'x', sheets: [sheet], components: [], nets: [],
      pcb: { boundsMm: { x:0,y:0,w:0,h:0 }, layers: [], stackup: [], footprints: [], tracks: [], vias: [], zones: [], drills: [] },
      source: 'raw'
    };
    const svg = buildSheetSvg(project, sheet);
    expect(svg).toMatch(/<svg/);
    expect(svg).toMatch(/viewBox="0 0 297 210"/);
  });

  it('emits a group per component with data-uuid / data-refdes', () => {
    const sheet: Sheet = {
      uuid: 's', name: 'root', path: ['root'], parent: null,
      componentUuids: ['u1'], boundsMm: { x: 0, y: 0, w: 297, h: 210 }
    };
    const project: Project = {
      name: 'x', sheets: [sheet], nets: [],
      pcb: { boundsMm: { x:0,y:0,w:0,h:0 }, layers: [], stackup: [], footprints: [], tracks: [], vias: [], zones: [], drills: [] },
      source: 'raw',
      components: [{ uuid: 'u1', refdes: 'R1', value: '10k', footprint: 'R', sheetUuid: 's', dnp: false, pins: [] }]
    };
    const svg = buildSheetSvg(project, sheet);
    expect(svg).toContain('data-uuid="u1"');
    expect(svg).toContain('data-refdes="R1"');
    expect(svg).toContain('R1');
  });
});
