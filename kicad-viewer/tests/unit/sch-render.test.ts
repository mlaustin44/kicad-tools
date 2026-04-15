import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { buildSheetSvg } from '$lib/sch/render';
import { toProject } from '$lib/adapter/adapter';
import type { Project, Sheet } from '$lib/model/project';

describe('sch render', () => {
  it('emits an svg string with a viewBox for an empty sheet', () => {
    const sheet: Sheet = {
      uuid: 's', name: 'root', path: ['root'], parent: null,
      componentUuids: [], boundsMm: { x: 0, y: 0, w: 297, h: 210 }
    };
    const project: Project = {
      name: 'x', sheets: [sheet], components: [], nets: [],
      pcb: { boundsMm: { x:0,y:0,w:0,h:0 }, layers: [], stackup: [], footprints: [], tracks: [], vias: [], zones: [], drills: [], boardGraphics: [] },
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
      pcb: { boundsMm: { x:0,y:0,w:0,h:0 }, layers: [], stackup: [], footprints: [], tracks: [], vias: [], zones: [], drills: [], boardGraphics: [] },
      source: 'raw',
      components: [{ uuid: 'u1', refdes: 'R1', value: '10k', footprint: 'R', sheetUuid: 's', dnp: false, pins: [] }]
    };
    const svg = buildSheetSvg(project, sheet);
    expect(svg).toContain('data-uuid="u1"');
    expect(svg).toContain('data-refdes="R1"');
    expect(svg).toContain('R1');
  });

  it('renders real schematic elements from pic_programmer root sheet', () => {
    const fix = (f: string) => readFileSync(join('tests/fixtures', f), 'utf-8');
    const project = toProject({
      pro: fix('pic_programmer.kicad_pro'),
      pcb: fix('pic_programmer.kicad_pcb'),
      schematics: {
        'pic_programmer.kicad_sch': fix('pic_programmer.kicad_sch'),
        'pic_sockets.kicad_sch': fix('pic_sockets.kicad_sch')
      },
      rootSchematic: 'pic_programmer.kicad_sch'
    });
    const root = project.sheets[0]!;
    expect(root.rawSch).toBeTruthy();
    const svg = buildSheetSvg(project, root);

    expect(svg).toMatch(/<svg/);
    // Should contain at least one wire line and at least one symbol group.
    expect(svg).toMatch(/<line /);
    expect(svg).toMatch(/<g data-refdes/);
    // Non-trivial content (the root sheet has many wires and symbols).
    expect(svg.length).toBeGreaterThan(500);
  });
});
