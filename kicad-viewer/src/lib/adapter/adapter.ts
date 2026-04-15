import { KicadSch } from '$lib/parser/schematic';
import { KicadPCB } from '$lib/parser/board';
import type { Project, Sheet, Component, Net, PcbData, LayerInfo } from '$lib/model/project';

export interface AdapterInput {
  pro: string;
  pcb: string;
  schematics: Record<string, string>;
  rootSchematic: string;
}

export function toProject(input: AdapterInput): Project {
  const sheets = buildSheets(input.schematics, input.rootSchematic);
  const components = buildComponents(input.schematics, sheets);
  const pcb = buildPcb(input.pcb);
  const nets = buildNets(pcb, components);

  mergePcbPositions(components, pcb);

  return {
    name: deriveName(input.rootSchematic),
    sheets,
    components,
    nets,
    pcb,
    source: 'raw'
  };
}

// — helpers (kept narrow; extend as real fixtures demand) —

function deriveName(path: string): string {
  return path.replace(/\.kicad_sch$/, '').split('/').pop() ?? 'project';
}

function buildSheets(src: Record<string, string>, root: string): Sheet[] {
  const sheets: Sheet[] = [];
  for (const [filename, text] of Object.entries(src)) {
    const sch = new KicadSch(filename, text);
    sheets.push({
      uuid: (sch as { uuid?: string }).uuid ?? filename,
      name: filename.replace(/\.kicad_sch$/, ''),
      path: filename === root ? ['root'] : ['root', filename.replace(/\.kicad_sch$/, '')],
      parent: filename === root ? null : (sheets[0]?.uuid ?? null),
      componentUuids: [],
      boundsMm: { x: 0, y: 0, w: 297, h: 210 } // A4 placeholder; refine via sch
    });
  }
  return sheets;
}

function buildComponents(src: Record<string, string>, sheets: Sheet[]): Component[] {
  const comps: Component[] = [];
  for (const [filename, text] of Object.entries(src)) {
    const sch = new KicadSch(filename, text);
    const sheet =
      sheets.find((s) => s.name === filename.replace(/\.kicad_sch$/, '')) ?? sheets[0];
    if (!sheet) continue;

    const symbolsMap = (sch as { symbols?: Map<string, unknown> | unknown[] }).symbols;
    const symbolIter: Iterable<unknown> = symbolsMap instanceof Map
      ? symbolsMap.values()
      : (Array.isArray(symbolsMap) ? symbolsMap : []);

    for (const symRaw of symbolIter) {
      const sym = symRaw as {
        reference?: string;
        value?: string;
        footprint?: string;
        uuid?: string;
        dnp?: boolean;
        datasheet?: string;
        getProperty?: (name: string) => { value?: string } | undefined;
      };
      const refdes = sym.reference ?? sym.getProperty?.('Reference')?.value ?? '?';
      const value = sym.value ?? sym.getProperty?.('Value')?.value ?? '';
      const fp = sym.footprint ?? sym.getProperty?.('Footprint')?.value ?? '';
      const uuid = sym.uuid ?? `${sheet.uuid}:${refdes}`;
      const component: Component = {
        uuid,
        refdes,
        value,
        footprint: fp,
        sheetUuid: sheet.uuid,
        dnp: sym.dnp ?? false,
        pins: []
      };
      const mpn = sym.getProperty?.('MPN')?.value;
      if (mpn) component.mpn = mpn;
      const mfg = sym.getProperty?.('Manufacturer')?.value;
      if (mfg) component.manufacturer = mfg;
      const datasheet = sym.datasheet ?? sym.getProperty?.('Datasheet')?.value;
      if (datasheet) component.datasheet = datasheet;
      comps.push(component);
      sheet.componentUuids.push(uuid);
    }
  }
  return comps;
}

function buildPcb(pcbText: string): PcbData {
  const pcb = new KicadPCB('pcb', pcbText);
  const rawLayers = (pcb as { layers?: Array<{ canonical_name?: string; name?: string }> }).layers ?? [];
  const layers: LayerInfo[] = rawLayers.map((l) => {
    const name = l.canonical_name ?? l.name ?? '';
    return {
      id: name,
      name,
      type: classifyLayer(name),
      defaultColor: defaultColorFor(name)
    };
  });
  return {
    boundsMm: { x: 0, y: 0, w: 0, h: 0 },
    layers,
    stackup: [],
    footprints: [],
    tracks: [],
    vias: [],
    zones: [],
    drills: []
  };
}

function buildNets(pcb: PcbData, _components: Component[]): Net[] {
  const names = new Set<string>();
  for (const t of pcb.tracks) if (t.netName) names.add(t.netName);
  for (const v of pcb.vias) if (v.netName) names.add(v.netName);
  return [...names].map((name) => ({ name, refdesPins: [] }));
}

function mergePcbPositions(_c: Component[], _p: PcbData): void {
  /* extended in Task 12 */
}

function classifyLayer(name: string): LayerInfo['type'] {
  if (name === 'F.Cu') return 'F.Cu';
  if (name === 'B.Cu') return 'B.Cu';
  if (/^In[0-9]+\.Cu$/.test(name)) return 'In.Cu';
  if (name === 'F.SilkS') return 'F.SilkS';
  if (name === 'B.SilkS') return 'B.SilkS';
  if (name === 'F.Mask') return 'F.Mask';
  if (name === 'B.Mask') return 'B.Mask';
  if (name === 'F.Paste') return 'F.Paste';
  if (name === 'B.Paste') return 'B.Paste';
  if (name === 'F.CrtYd') return 'F.CrtYd';
  if (name === 'B.CrtYd') return 'B.CrtYd';
  if (name === 'F.Fab') return 'F.Fab';
  if (name === 'B.Fab') return 'B.Fab';
  if (name === 'Edge.Cuts') return 'Edge.Cuts';
  if (name === 'Margin') return 'Margin';
  return 'Other';
}

function defaultColorFor(name: string): string {
  const m: Record<string, string> = {
    'F.Cu': '#c83434',
    'B.Cu': '#4d7fc4',
    'F.SilkS': '#e5e5e5',
    'B.SilkS': '#aaaaaa',
    'F.Mask': '#008579',
    'B.Mask': '#008579',
    'F.Paste': '#d0d0d0',
    'B.Paste': '#d0d0d0',
    'F.CrtYd': '#7fb37f',
    'B.CrtYd': '#7fb37f',
    'F.Fab': '#b58d6c',
    'B.Fab': '#afafaf',
    'Edge.Cuts': '#f2eda1'
  };
  return m[name] ?? '#888';
}
