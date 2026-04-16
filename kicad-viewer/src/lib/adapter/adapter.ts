import { KicadSch, type SchematicSymbol, type LibSymbol, type PinDefinition } from '$lib/parser/schematic';
import {
  KicadPCB,
  ArcSegment,
  LineSegment,
  Line as ParserLine,
  Arc as ParserArc,
  Poly as ParserPoly,
  Rect as ParserRect,
  Circle as ParserCircle,
  Text as ParserText,
  type Footprint as ParserFootprint,
  type Pad as ParserPad,
  type Zone as ParserZone,
  type Drawing as ParserDrawing
} from '$lib/parser/board';
import { Vec2 } from '$lib/parser/base/math';
import { unescape_string } from '$lib/parser/common';

// KiCad encodes special characters in hierarchical net paths as {slash},
// {backslash}, {space}, etc. Decode once at the adapter boundary so every
// downstream consumer (renderer, search, inspector) sees plain strings.
function cleanNetName(s: string | null | undefined): string | null {
  if (!s) return null;
  return unescape_string(s);
}
import type {
  Project,
  Sheet,
  Component,
  Net,
  Pin,
  PcbData,
  LayerInfo,
  FootprintGeom,
  TrackSeg,
  Pad as ModelPad,
  Graphic,
  GraphicGeom,
  Zone as ModelZone,
  Via as ModelVia,
  PaperSize,
  TitleBlockInfo,
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
  const sheets = buildSheets(parsedSchematics, input.rootSchematic, input.schematics);

  const pcb = new KicadPCB('pcb', input.pcb);
  const pcbData = buildPcb(pcb);

  const components = buildComponents(parsedSchematics, sheets, input.rootSchematic, pcbData);
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

function buildSheets(
  parsed: Map<string, KicadSch>,
  root: string,
  sources: Record<string, string>
): Sheet[] {
  const sheets: Sheet[] = [];
  const rootSch = parsed.get(root);

  const rootUuid = rootSch?.uuid ?? root;
  const rootName = root.replace(/\.kicad_sch$/, '');
  const rootSheet: Sheet = {
    uuid: rootUuid,
    name: rootName,
    path: ['root'],
    parent: null,
    componentUuids: [],
    boundsMm: paperBounds(rootSch)
  };
  const rootText = sources[root];
  if (rootText) rootSheet.rawSch = rootText;
  const rootPaper = paperSize(rootSch);
  if (rootPaper) rootSheet.paper = rootPaper;
  const rootTb = titleBlockInfo(rootSch);
  if (rootTb) rootSheet.titleBlock = rootTb;
  sheets.push(rootSheet);

  // One level of children: any other schematic in the bundle, placed under root.
  for (const [filename, sch] of parsed.entries()) {
    if (filename === root) continue;
    const name = filename.replace(/\.kicad_sch$/, '');
    const childSheet: Sheet = {
      uuid: sch.uuid ?? filename,
      name,
      path: ['root', name],
      parent: rootUuid,
      componentUuids: [],
      boundsMm: paperBounds(sch)
    };
    const childText = sources[filename];
    if (childText) childSheet.rawSch = childText;
    const childPaper = paperSize(sch);
    if (childPaper) childSheet.paper = childPaper;
    const childTb = titleBlockInfo(sch);
    if (childTb) childSheet.titleBlock = childTb;
    sheets.push(childSheet);
  }
  return sheets;
}

function paperSize(sch: KicadSch | undefined): PaperSize | undefined {
  const raw = (sch as unknown as { paper?: { size?: string } } | undefined)?.paper?.size;
  if (!raw) return undefined;
  switch (raw) {
    case 'A0': case 'A1': case 'A2': case 'A3': case 'A4': case 'A5':
    case 'A': case 'B': case 'C': case 'D': case 'E':
      return raw;
    case 'USLetter': return 'USLetter';
    case 'USLegal': return 'USLegal';
    case 'USLedger': return 'USLedger';
    default: return 'Custom';
  }
}

function titleBlockInfo(sch: KicadSch | undefined): TitleBlockInfo | undefined {
  const tb = (sch as unknown as { title_block?: {
    title?: string; date?: string; rev?: string; company?: string;
    comment?: Record<string, string>;
  } } | undefined)?.title_block;
  if (!tb) return undefined;
  const title = tb.title ?? '';
  const date = tb.date ?? '';
  const rev = tb.rev ?? '';
  const company = tb.company ?? '';
  const raw = tb.comment ?? {};
  // KiCad stores comments keyed by number (1..9); keep positional order.
  const comments: string[] = [];
  for (let i = 1; i <= 9; i++) {
    const v = raw[String(i)];
    if (v != null) comments.push(v);
  }
  // Skip empty title blocks.
  if (!title && !date && !rev && !company && comments.every((c) => !c)) return undefined;
  return { title, date, rev, company, comments };
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
  root: string,
  pcb: PcbData
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

  const footprintByRefdes = new Map<string, FootprintGeom>();
  for (const fp of pcb.footprints) footprintByRefdes.set(fp.refdes, fp);

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
        pins: extractPins(s, footprintByRefdes.get(refdes)),
        properties: collectProperties(s)
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

// The Inspector handles these as first-class fields; skip them here so we don't
// duplicate rows. "ki_*" fields are KiCad internal (keywords/filters/etc.).
const RESERVED_PROPERTIES = new Set([
  'Reference', 'Value', 'Footprint', 'Datasheet', 'MPN', 'Manufacturer'
]);

function collectProperties(sym: SchematicSymbol): Record<string, string> {
  const out: Record<string, string> = {};
  const props = sym.properties as unknown as Map<string, { name: string; text: string }>;
  if (!props || typeof props.values !== 'function') return out;
  // Include every property that has a value and isn't surfaced as a first-class
  // field above. We intentionally don't filter on the `hide` flag: that flag
  // controls visibility on the schematic canvas, not metadata availability
  // (Description, LCSC Part, MPN_etc. are often hidden but still meaningful).
  for (const p of props.values()) {
    if (!p || RESERVED_PROPERTIES.has(p.name)) continue;
    if (p.name.startsWith('ki_')) continue;
    const text = (p.text ?? '').trim();
    if (!text || text === '~') continue;
    out[p.name] = text;
  }
  return out;
}

function extractPins(sym: SchematicSymbol, fp: FootprintGeom | undefined): Pin[] {
  let lib: LibSymbol | undefined;
  try {
    lib = sym.lib_symbol;
  } catch {
    return [];
  }
  if (!lib) return [];
  const libPins: PinDefinition[] = [...(lib.pins ?? [])];
  for (const child of lib.children ?? []) libPins.push(...(child.pins ?? []));

  const pins: Pin[] = [];
  for (const p of libPins) {
    const number = p.number?.text ?? '?';
    const name = p.name?.text ?? '';
    const pad = fp?.pads.find((pd) => pd.number === number);
    pins.push({ number, name, netName: cleanNetName(pad?.netName) });
  }
  return pins;
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
  const footprints = pcb.footprints.map((fp) => toFootprintGeom(fp, pcb));
  const tracks = buildTracks(pcb);
  const vias = buildVias(pcb);
  const zones = buildZones(pcb);
  const boardGraphics = buildBoardGraphics(pcb);

  return {
    boundsMm,
    layers,
    stackup: [],
    footprints,
    tracks,
    vias,
    zones,
    drills: [],
    boardGraphics
  };
}

function computeBounds(pcb: KicadPCB): Rect {
  // Walk the board's own Edge.Cuts primitives and read the raw coordinates.
  // We used to rely on pcb.edge_cuts_bbox, but its per-arc bbox depends on the
  // parser's MathArc center-from-three-points which can misbehave; going to
  // the raw `start`/`mid`/`end`/`center` points is CAD-accurate.
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  const include = (x: number, y: number) => {
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  };
  for (const d of pcb.drawings ?? []) {
    const layer = (d as unknown as { layer?: string }).layer;
    if (layer !== 'Edge.Cuts') continue;
    const any = d as unknown as {
      start?: { x: number; y: number };
      mid?: { x: number; y: number };
      end?: { x: number; y: number };
      center?: { x: number; y: number };
      pts?: Array<{ x: number; y: number }>;
    };
    if (any.start) include(any.start.x, any.start.y);
    if (any.mid) include(any.mid.x, any.mid.y);
    if (any.end) include(any.end.x, any.end.y);
    if (any.center) include(any.center.x, any.center.y);
    if (any.pts) for (const p of any.pts) include(p.x, p.y);
  }

  if (isFinite(minX) && isFinite(minY) && maxX > minX && maxY > minY) {
    return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
  }

  // Fallback: union of footprint positions with a small margin.
  if (pcb.footprints.length === 0) {
    return { x: 0, y: 0, w: 0, h: 0 };
  }
  for (const fp of pcb.footprints) {
    const p = fp.at?.position;
    if (!p) continue;
    include(p.x, p.y);
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

function toFootprintGeom(fp: ParserFootprint, pcb: KicadPCB): FootprintGeom {
  const pos: Point = { x: fp.at?.position?.x ?? 0, y: fp.at?.position?.y ?? 0 };
  const rotationDeg = fp.at?.rotation ?? 0;
  const side: 'top' | 'bottom' = fp.layer === 'B.Cu' ? 'bottom' : 'top';
  const bbox = fp.bbox;
  const bboxMm: Rect = bbox
    ? { x: bbox.x, y: bbox.y, w: bbox.w, h: bbox.h }
    : { x: pos.x - 2.5, y: pos.y - 2.5, w: 5, h: 5 };

  return {
    uuid: fp.uuid ?? fp.tstamp ?? `${fp.reference}-${pos.x},${pos.y}`,
    refdes: fp.reference ?? '?',
    position: pos,
    rotationDeg,
    side,
    bboxMm,
    pads: buildPads(fp, pcb),
    graphics: buildFootprintGraphics(fp)
  };
}

function buildPads(fp: ParserFootprint, pcb: KicadPCB): ModelPad[] {
  const pads: ModelPad[] = [];
  for (const p of fp.pads ?? []) {
    pads.push(toModelPad(p, pcb));
  }
  return pads;
}

function toModelPad(pad: ParserPad, pcb: KicadPCB): ModelPad {
  const layerIds = expandPadLayers(pad.layers ?? [], pcb);
  // Pad position is in footprint-local frame.
  const pos: Point = {
    x: pad.at?.position?.x ?? 0,
    y: pad.at?.position?.y ?? 0
  };
  const size = { w: pad.size?.x ?? 0, h: pad.size?.y ?? 0 };
  const out: ModelPad = {
    number: String(pad.number ?? ''),
    shape: String(pad.shape ?? 'rect'),
    layerIds,
    positionMm: pos,
    sizeMm: size,
    netName: cleanNetName(pad.netname)
  };
  // Through-hole pads carry a drill.diameter; only set when truthy to respect
  // exactOptionalPropertyTypes.
  const drillMm = pad.drill?.diameter ?? 0;
  if (drillMm > 0) out.drillMm = drillMm;
  return out;
}

// KiCad pads can use wildcard layer patterns like "F.Cu", "*.Cu" meaning all copper,
// "*.Mask" meaning both masks, etc. Expand wildcards against the board's layer list.
function expandPadLayers(patterns: string[], pcb: KicadPCB): string[] {
  const out = new Set<string>();
  const allIds = pcb.layers.map((l) => l.canonical_name ?? '').filter((s) => s.length > 0);
  for (const p of patterns) {
    if (p.includes('*')) {
      // Convert glob (e.g. "*.Cu", "F.*") to regex.
      const re = new RegExp('^' + p.replace(/\./g, '\\.').replace(/\*/g, '[^.]*') + '$');
      for (const id of allIds) if (re.test(id)) out.add(id);
    } else {
      out.add(p);
    }
  }
  return [...out];
}

function buildFootprintGraphics(fp: ParserFootprint): Graphic[] {
  const out: Graphic[] = [];
  for (const d of fp.drawings ?? []) {
    const g = drawingToGraphic(d);
    if (g) out.push(g);
  }
  return out;
}

function buildBoardGraphics(pcb: KicadPCB): Graphic[] {
  const out: Graphic[] = [];
  for (const d of pcb.drawings ?? []) {
    const g = drawingToGraphic(d);
    if (g) out.push(g);
  }
  return out;
}

type AnyBoardDrawing = ParserDrawing | ParserFootprint['drawings'][number];

function drawingToGraphic(d: AnyBoardDrawing): Graphic | null {
  if (d instanceof ParserLine) {
    const layerId = d.layer ?? '';
    const widthMm = d.width ?? d.stroke?.width ?? 0.15;
    const geom: GraphicGeom = {
      kind: 'line',
      a: { x: d.start.x, y: d.start.y },
      b: { x: d.end.x, y: d.end.y },
      widthMm
    };
    return { layerId, geom };
  }
  if (d instanceof ParserArc) {
    const layerId = d.layer ?? '';
    const widthMm = d.width ?? d.stroke?.width ?? 0.15;
    // Use MathArc from parser to derive center/radius/angles.
    const arc = d.arc;
    const center = arc.center;
    const radiusMm = arc.radius;
    const startDeg = arc.start_angle.degrees;
    const endDeg = arc.end_angle.degrees;
    const geom: GraphicGeom = {
      kind: 'arc',
      center: { x: center.x, y: center.y },
      radiusMm,
      startDeg,
      endDeg,
      widthMm
    };
    return { layerId, geom };
  }
  if (d instanceof ParserPoly) {
    const layerId = d.layer ?? '';
    const widthMm = d.width ?? d.stroke?.width ?? 0.15;
    const points = d.polyline.map((p: Vec2) => ({ x: p.x, y: p.y }));
    const filled = d.fill === 'solid' || d.fill === 'yes' || d.fill === 'true';
    const geom: GraphicGeom = { kind: 'polygon', points, widthMm, filled };
    return { layerId, geom };
  }
  if (d instanceof ParserRect) {
    const layerId = d.layer ?? '';
    const widthMm = d.width ?? d.stroke?.width ?? 0.15;
    const x1 = d.start.x;
    const y1 = d.start.y;
    const x2 = d.end.x;
    const y2 = d.end.y;
    const filled = d.fill === 'solid' || d.fill === 'yes' || d.fill === 'true';
    const geom: GraphicGeom = {
      kind: 'polygon',
      points: [
        { x: x1, y: y1 },
        { x: x2, y: y1 },
        { x: x2, y: y2 },
        { x: x1, y: y2 }
      ],
      widthMm,
      filled
    };
    return { layerId, geom };
  }
  if (d instanceof ParserCircle) {
    const layerId = d.layer ?? '';
    const widthMm = d.width ?? d.stroke?.width ?? 0.15;
    const cx = d.center.x;
    const cy = d.center.y;
    const dx = d.end.x - cx;
    const dy = d.end.y - cy;
    const radiusMm = Math.sqrt(dx * dx + dy * dy);
    const geom: GraphicGeom = {
      kind: 'arc',
      center: { x: cx, y: cy },
      radiusMm,
      startDeg: 0,
      endDeg: 360,
      widthMm
    };
    return { layerId, geom };
  }
  if (d instanceof ParserText) {
    const layerId = d.layer?.name ?? '';
    if (d.hide) return null;
    const heightMm = d.effects?.font?.size?.y ?? 1.0;
    const j = d.effects?.justify;
    const font = d.effects?.font;
    const geom: GraphicGeom = {
      kind: 'text',
      position: { x: d.at?.position?.x ?? 0, y: d.at?.position?.y ?? 0 },
      rotationDeg: d.at?.rotation ?? 0,
      heightMm,
      text: d.shown_text ?? d.text ?? '',
      hAlign: j?.horizontal,
      vAlign: j?.vertical,
      bold: font?.bold,
      italic: font?.italic
    };
    return { layerId, geom };
  }
  return null;
}

function buildZones(pcb: KicadPCB): ModelZone[] {
  const out: ModelZone[] = [];
  const collect = (zone: ParserZone): void => {
    // KiCad 10 stores the net as a name atom; KiCad 9 used a number index.
    const rawNetName =
      zone.net_name ||
      (typeof zone.net === 'string' ? zone.net : null) ||
      (typeof zone.net === 'number' ? pcb.get_netname_by_number(zone.net) : null) ||
      null;
    const netName = cleanNetName(rawNetName);
    // Prefer filled polygons per layer when available — render matches plotted output.
    if (zone.filled_polygons && zone.filled_polygons.length > 0) {
      for (const fp of zone.filled_polygons) {
        const layerId =
          (fp as unknown as { layer?: string }).layer ??
          zone.layer ??
          zone.layers?.[0] ??
          '';
        if (!layerId) continue;
        out.push({
          layerId,
          polygon: fp.polyline.map((p: Vec2) => ({ x: p.x, y: p.y })),
          netName
        });
      }
      return;
    }
    // Fallback: outline polygons (hatched zones before fill).
    const layerIds = zone.layers?.length ? zone.layers : zone.layer ? [zone.layer] : [];
    for (const poly of zone.polygons ?? []) {
      for (const layerId of layerIds) {
        out.push({
          layerId,
          polygon: poly.polyline.map((p: Vec2) => ({ x: p.x, y: p.y })),
          netName
        });
      }
    }
  };
  for (const z of pcb.zones ?? []) collect(z);
  for (const fp of pcb.footprints ?? []) {
    for (const z of fp.zones ?? []) collect(z);
  }
  return out;
}

function buildVias(pcb: KicadPCB): ModelVia[] {
  const out: ModelVia[] = [];
  for (const v of pcb.vias ?? []) {
    const layers = v.layers ?? [];
    const rawVia =
      (typeof v.net === 'string' ? v.net : null) ??
      (typeof v.net === 'number' ? pcb.get_netname_by_number(v.net) ?? null : null);
    const netName = cleanNetName(rawVia);
    out.push({
      position: { x: v.at?.position?.x ?? 0, y: v.at?.position?.y ?? 0 },
      diameterMm: v.size ?? 0.6,
      drillMm: v.drill ?? 0.3,
      layerFrom: layers[0] ?? 'F.Cu',
      layerTo: layers[1] ?? 'B.Cu',
      netName
    });
  }
  return out;
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
        netName: cleanNetName(seg.netname)
      });
    } else if (seg instanceof ArcSegment) {
      // Approximate an arc as start-end chord for now.
      tracks.push({
        layerId: seg.layer,
        a: { x: seg.start.x, y: seg.start.y },
        b: { x: seg.end.x, y: seg.end.y },
        widthMm: seg.width,
        netName: cleanNetName(seg.netname)
      });
    }
  }
  return tracks;
}

function buildNets(pcb: KicadPCB, pcbData: PcbData, components: Component[]): Net[] {
  const byRefdes = new Map<string, Component>();
  for (const c of components) byRefdes.set(c.refdes, c);

  // Map of net name -> list of (refdes, pad number) from footprint pads.
  // Net names are decoded (e.g. "{slash}" → "/") so they match the rest of the
  // project model.
  const netPins = new Map<string, Array<{ refdes: string; pin: string }>>();
  for (const fp of pcb.footprints) {
    for (const pad of fp.pads) {
      const name = cleanNetName(pad.net?.name);
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
    const cleaned = cleanNetName(n.name);
    if (cleaned) names.add(cleaned);
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
