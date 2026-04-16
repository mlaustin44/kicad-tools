import { describe, it, expect } from 'vitest';
import { zipSync, strToU8 } from 'fflate';
import { loadFromZipBytes } from '$lib/loader/zip';
import { classifyFiles } from '$lib/loader/blob';

describe('loader.blob.classify', () => {
  it('classifies files by extension', () => {
    const blob = classifyFiles({
      'p.kicad_pro': 'x',
      'p.kicad_pcb': 'y',
      'p.kicad_sch': 'z',
      'p.glb': new Uint8Array([1, 2, 3])
    });
    expect(blob.kicadPro).toBe('p.kicad_pro');
    expect(blob.kicadPcb).toBe('p.kicad_pcb');
    expect(blob.schematics).toContain('p.kicad_sch');
    expect(blob.glb).toBe('p.glb');
  });

  it('detects a manifest.json and parses it', () => {
    const manifestText = JSON.stringify({
      name: 'X',
      version: '1.0',
      files: { pcb: 'x.kicad_pcb', sch: ['x.kicad_sch'] }
    });
    const blob = classifyFiles({
      'manifest.json': manifestText,
      'x.kicad_pcb': 'y',
      'x.kicad_sch': 'z'
    });
    expect(blob.manifest?.name).toBe('X');
    expect(blob.manifest?.files.pcb).toBe('x.kicad_pcb');
  });
});

describe('loader.zip', () => {
  it('extracts a synthetic zip', async () => {
    // Wrap with `new Uint8Array(...)` so the values are instances of the test
    // realm's Uint8Array; fflate's `zipSync` does `val instanceof u8` (where
    // `u8 = Uint8Array` inside the fflate module), and under vitest + jsdom
    // those realms differ — without the wrap, names get coerced to directories.
    const zip = zipSync({
      'p.kicad_pro': new Uint8Array(strToU8('{}')),
      'p.kicad_pcb': new Uint8Array(strToU8('(kicad_pcb)')),
      'p.kicad_sch': new Uint8Array(strToU8('(kicad_sch)'))
    });
    const blob = await loadFromZipBytes(zip);
    expect(blob.kicadPro).toBe('p.kicad_pro');
    expect(blob.schematics.length).toBe(1);
  });
});
