import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { toProject } from '$lib/adapter/adapter';

const fix = (f: string) => readFileSync(join('tests/fixtures', f), 'utf-8');

describe('adapter.toProject (pic_programmer)', () => {
  const project = toProject({
    pro: fix('pic_programmer.kicad_pro'),
    pcb: fix('pic_programmer.kicad_pcb'),
    schematics: {
      'pic_programmer.kicad_sch': fix('pic_programmer.kicad_sch'),
      'pic_sockets.kicad_sch': fix('pic_sockets.kicad_sch')
    },
    rootSchematic: 'pic_programmer.kicad_sch'
  });

  it('has sheets', () => {
    expect(project.sheets.length).toBeGreaterThanOrEqual(1);
  });

  it('has components with real refdes', () => {
    expect(project.components.length).toBeGreaterThan(10);
    const refdes = project.components.map((c) => c.refdes);
    // pic_programmer has at least these classes of parts
    expect(refdes.some((r) => r.startsWith('R'))).toBe(true);
    expect(refdes.some((r) => r.startsWith('C'))).toBe(true);
    expect(refdes.some((r) => r.startsWith('U'))).toBe(true);
  });

  it('has PCB layers including F.Cu and Edge.Cuts', () => {
    expect(project.pcb.layers.some((l) => l.id === 'F.Cu')).toBe(true);
    expect(project.pcb.layers.some((l) => l.id === 'Edge.Cuts')).toBe(true);
  });

  it('has footprints with positions matching components', () => {
    expect(project.pcb.footprints.length).toBeGreaterThan(0);
    const fpRefs = project.pcb.footprints.map((f) => f.refdes);
    const compRefs = project.components.map((c) => c.refdes);
    const overlap = fpRefs.filter((r) => compRefs.includes(r));
    expect(overlap.length).toBeGreaterThan(0);
  });

  it('has tracks with layer ids and widths', () => {
    expect(project.pcb.tracks.length).toBeGreaterThan(0);
    for (const t of project.pcb.tracks.slice(0, 5)) {
      expect(t.layerId).toBeTruthy();
      expect(t.widthMm).toBeGreaterThan(0);
    }
  });

  it('tracks and pads have net names populated (KiCad 10 format)', () => {
    const tracksWithNet = project.pcb.tracks.filter((t) => t.netName);
    const allPads = project.pcb.footprints.flatMap((f) => f.pads);
    const padsWithNet = allPads.filter((p) => p.netName);
    // pic_programmer fixture has hundreds of net-bearing tracks and pads.
    expect(tracksWithNet.length).toBeGreaterThan(100);
    expect(padsWithNet.length).toBeGreaterThan(100);
  });

  it('has bounds with non-zero size', () => {
    expect(project.pcb.boundsMm.w).toBeGreaterThan(0);
    expect(project.pcb.boundsMm.h).toBeGreaterThan(0);
  });
});
