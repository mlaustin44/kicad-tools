import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { toProject } from '$lib/adapter/adapter';

const fix = (f: string) => readFileSync(join('tests/fixtures', f), 'utf-8');

describe('adapter.toProject', () => {
  it('parses a trivial project into our model', () => {
    const project = toProject({
      pro: fix('tiny.kicad_pro'),
      pcb: fix('tiny.kicad_pcb'),
      schematics: { 'tiny.kicad_sch': fix('tiny.kicad_sch') },
      rootSchematic: 'tiny.kicad_sch'
    });
    expect(project.sheets.length).toBeGreaterThanOrEqual(1);
    expect(project.pcb.layers.some((l) => l.id === 'F.Cu')).toBe(true);
    expect(project.source).toBe('raw');
  });
});
