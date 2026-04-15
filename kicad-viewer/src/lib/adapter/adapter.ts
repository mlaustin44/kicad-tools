import { KicadSch, type SchematicSymbol } from '$lib/parser/schematic';
import {
  KicadPCB,
  ArcSegment,
  LineSegment,
  type Footprint as ParserFootprint
} from '$lib/parser/board';
import type {
  Project,
  Sheet,
  Component,
  Net,
  PcbData,
  LayerInfo,
  FootprintGeom,
  TrackSeg,
  Point,
  Rect
} from '$lib/model/project';

export interface AdapterInput {
  pro: string;
  pcb: string;
  schematics: Record<string, string>;
  rootSchematic: string;
}

export function toProject(input: AdapterInput): Project {
  const parsedSchematics = parseSchematics(input.schematics);
  const sheets = buildSheets(parsedSchematics, input.rootSchematic);
  const components = buildComponents(parsedSchematics, sheets, input.rootSchematic);

  const pcb = new KicadPCB('pcb', input.pcb);
  const pcbData = buildPcb(pcb);
  const nets = buildNets(pcb, pcbData, components);

  mergePcbPositions(components, pcbData);

  return {
    name: deriveName(input.rootSchematic),
    sheets,
    components,
    nets,
    pcb: pcbData,
    source: 'raw'
  };
}

// — helpers —

function deriveName(path: string): string {
  return path.replace(/\.kicad_sch$/, '').split('/').pop() ?? 'project';
}

function parseSchematics(src: Record<string, string>): Map<string, KicadSch> {
  const out = new Map<string, KicadSch>();
  for (const [filename, text] of Object.entries(src)) {
    out.set(filename, new KicadSch(filename, text));
  }
  return out;
}

function buildSheets(parsed: Map<string, KicadSch>, root: string): Sheet[] {
  const sheets: Sheet[] = [];
  const rootSch = parsed.get(root);

  const rootUuid = rootSch?.uuid ?? root;
  const rootName = root.replace(/\.kicad_sch$/, '');
  sheets.push({
    uuid: rootUuid,
    name: rootName,
    path: ['root'],
    parent: null,
    componentUuids: [],
    boundsMm: paperBounds(rootSch)
  });

  // One level of children: any other schematic in the bundle, placed under root.
  for (const [filename, sch] of parsed.entries()) {
    if (filename === root) continue;
    const name = filename.replace(/\.kicad_sch$/, '');
    sheets.push({
      uuid: sch.uuid ?? filename,
      name,
      path: ['root', name],
      parent: rootUuid,
      componentUuids: [],
      boundsMm: paperBounds(sch)
    });
  }
  return sheets;
}

function paperBounds(sch: KicadSch | undefined): Rect {
  // Default to A4 if paper missing; KiCad paper sizes are in mm.
  if (!sch) return { x: 0, y: 0, w: 297, h: 210 };
  const paper = (sch as unknown as { paper?: { width?: number; height?: number } }).paper;
  const w = paper?.width ?? 297;
  const h = paper?.height ?? 210;
  return { x: 0, y: 0, w, h };
}

function buildComponents(
  parsed: Map<string, KicadSch>,
  sheets: Sheet[],
  root: string
): Component[] {
  const comps: Component[] = [];
  const sheetByFilename = new Map<string, Sheet>();
  for (const [filename] of parsed) {
    const name = filename.replace(/\.kicad_sch$/, '');
    const sheet =
      filename === root
        ? sheets.find((s) => s.path.length === 1)
        : sheets.find((s) => s.name === name);
    if (sheet) sheetByFilename.set(filename, sheet);
  }

  for (const [filename, sch] of parsed) {
    const sheet = sheetByFilename.get(filename);
    if (!sheet) continue;

    for (const sym of sch.symbols.values()) {
      const s = sym as SchematicSymbol;
      const refdes = s.reference || '?';
      // Skip power symbols and unreferenced entries (starts with '#').
      if (refdes.startsWith('#')) continue;

      const uuid = s.uuid || `${sheet.uuid}:${refdes}`;
      const component: Component = {
        uuid,
        refdes,
        value: s.value || '',
        footprint: s.footprint || '',
        sheetUuid: sheet.uuid,
        dnp: s.dnp ?? false,
        pins: []
      };

      const mpn = s.get_property_text?.('MPN');
      if (mpn) component.mpn = mpn;
      const mfg = s.get_property_text?.('Manufacturer');
      if (mfg) component.manufacturer = mfg;
      const datasheet = s.get_property_text?.('Datasheet');
      if (datasheet && datasheet !== '~') component.datasheet = datasheet;

      comps.push(component);
      sheet.componentUuids.push(uuid);
    }
  }
  return comps;
}

function buildPcb(pcb: KicadPCB): PcbData {
  const layers: LayerInfo[] = pcb.layers.map((l) => {
    const id = l.canonical_name ?? '';
    return {
      id,
      name: l.user_name ?? id,
      type: classifyLayer(id),
      defaultColor: defaultColorFor(id)
    };
  });

  const boundsMm = computeBounds(pcb);
  const footprints = pcb.footprints.map(toFootprintGeom);
  const tracks = buildTracks(pcb);

  return {
    boundsMm,
    layers,
    stackup: [],
    footprints,
    tracks,
    vias: [],
    zones: [],
    drills: []
  };
}

function computeBounds(pcb: KicadPCB): Rect {
  const bbox = pcb.edge_cuts_bbox;
  if (bbox && bbox.w > 0 && bbox.h > 0) {
    return { x: bbox.x, y: bbox.y, w: bbox.w, h: bbox.h };
  }
  // Fallback: union of footprint positions with a small margin.
  if (pcb.footprints.length === 0) {
    return { x: 0, y: 0, w: 0, h: 0 };
  }
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const fp of pcb.footprints) {
    const p = fp.at?.position;
    if (!p) continue;
    if (p.x < minX) minX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.x > maxX) maxX = p.x;
    if (p.y > maxY) maxY = p.y;
  }
  if (!isFinite(minX)) return { x: 0, y: 0, w: 0, h: 0 };
  const margin = 5;
  return {
    x: minX - margin,
    y: minY - margin,
    w: maxX - minX + 2 * margin,
    h: maxY - minY + 2 * margin
  };
}

function toFootprintGeom(fp: ParserFootprint): FootprintGeom {
  const pos: Point = { x: fp.at?.position?.x ?? 0, y: fp.at?.position?.y ?? 0 };
  const side: 'top' | 'bottom' = fp.layer === 'B.Cu' ? 'bottom' : 'top';
  const bbox = fp.bbox;
  const bboxMm: Rect = bbox
    ? { x: bbox.x, y: bbox.y, w: bbox.w, h: bbox.h }
    : { x: pos.x - 2.5, y: pos.y - 2.5, w: 5, h: 5 };

  return {
    uuid: fp.uuid ?? fp.tstamp ?? `${fp.reference}-${pos.x},${pos.y}`,
    refdes: fp.reference ?? '?',
    position: pos,
    rotationDeg: fp.at?.rotation ?? 0,
    side,
    bboxMm,
    pads: [],
    graphics: []
  };
}

function buildTracks(pcb: KicadPCB): TrackSeg[] {
  const tracks: TrackSeg[] = [];
  for (const seg of pcb.segments) {
    if (seg instanceof LineSegment) {
      tracks.push({
        layerId: seg.layer,
        a: { x: seg.start.x, y: seg.start.y },
        b: { x: seg.end.x, y: seg.end.y },
        widthMm: seg.width,
        netName: seg.netname ?? null
      });
    } else if (seg instanceof ArcSegment) {
      // Approximate an arc as start-end chord for now.
      tracks.push({
        layerId: seg.layer,
        a: { x: seg.start.x, y: seg.start.y },
        b: { x: seg.end.x, y: seg.end.y },
        widthMm: seg.width,
        netName: seg.netname ?? null
      });
    }
  }
  return tracks;
}

function buildNets(pcb: KicadPCB, pcbData: PcbData, components: Component[]): Net[] {
  const byRefdes = new Map<string, Component>();
  for (const c of components) byRefdes.set(c.refdes, c);

  // Map of net name -> list of (refdes, pad number) from footprint pads.
  const netPins = new Map<string, Array<{ refdes: string; pin: string }>>();
  for (const fp of pcb.footprints) {
    for (const pad of fp.pads) {
      const name = pad.net?.name;
      if (!name) continue;
      if (!byRefdes.has(fp.reference)) continue;
      const arr = netPins.get(name) ?? [];
      arr.push({ refdes: fp.reference, pin: pad.number });
      netPins.set(name, arr);
    }
  }

  // Prefer the parser's net list (covers nets with no pads too); otherwise
  // derive from tracks/vias.
  const names = new Set<string>();
  for (const n of pcb.nets) {
    if (n.name) names.add(n.name);
  }
  if (names.size === 0) {
    for (const t of pcbData.tracks) if (t.netName) names.add(t.netName);
    for (const v of pcbData.vias) if (v.netName) names.add(v.netName);
  }

  const nets: Net[] = [];
  for (const name of names) {
    // Skip the special "no-net" entry KiCad emits as an empty string.
    if (!name) continue;
    nets.push({ name, refdesPins: netPins.get(name) ?? [] });
  }
  return nets;
}

function mergePcbPositions(components: Component[], pcb: PcbData): void {
  const byRef = new Map<string, FootprintGeom>();
  for (const fp of pcb.footprints) byRef.set(fp.refdes, fp);

  for (const c of components) {
    const fp = byRef.get(c.refdes);
    if (!fp) continue;
    c.positionMm = { x: fp.position.x, y: fp.position.y };
    c.rotationDeg = fp.rotationDeg;
    c.side = fp.side;
  }
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
