import type { Uuid, Refdes } from './ids';

export interface Project {
  name: string;
  sheets: Sheet[];                    // root sheet first; sub-sheets follow (flat list; hierarchy in `parent`)
  components: Component[];            // across all sheets
  nets: Net[];
  pcb: PcbData;
  glbUrl?: string | undefined;        // if supplied in bundle or sidecar
  stepUrl?: string | undefined;       // KiCad STEP export (tessellated client-side via occt-import-js)
  source: 'raw' | 'bundle';
}

export interface Sheet {
  uuid: Uuid;
  name: string;                       // human, e.g. "power"
  path: string[];                     // hierarchical path, e.g. ["root", "power"]
  parent: Uuid | null;
  componentUuids: Uuid[];
  boundsMm: Rect;
  rawSch?: string | undefined;        // original S-expression source for deferred render parsing
  paper?: PaperSize | undefined;      // paper size enum (A4/A3/USLetter/etc.) if declared in .kicad_sch
  titleBlock?: TitleBlockInfo | undefined;
}

export type PaperSize =
  | 'A0' | 'A1' | 'A2' | 'A3' | 'A4' | 'A5'
  | 'A' | 'B' | 'C' | 'D' | 'E'
  | 'USLetter' | 'USLegal' | 'USLedger'
  | 'Custom';

export interface TitleBlockInfo {
  title: string;
  date: string;
  rev: string;
  company: string;
  comments: string[];                 // comments 1..9, trimmed to last non-empty
}

export interface Component {
  uuid: Uuid;
  refdes: Refdes;
  value: string;
  footprint: string;
  sheetUuid: Uuid;
  mpn?: string | undefined;
  manufacturer?: string | undefined;
  datasheet?: string | undefined;
  dnp: boolean;
  pins: Pin[];
  /** All non-empty, non-hidden KiCad properties except Reference/Value/Footprint/Datasheet
   *  which are surfaced as first-class fields. Keyed by property name; insertion order
   *  matches the KiCad symbol declaration order. */
  properties: Record<string, string>;
  positionMm?: Point | undefined;     // on PCB; undefined if schematic-only
  rotationDeg?: number | undefined;
  side?: 'top' | 'bottom' | undefined;
}

export interface Pin { number: string; name: string; netName: string | null; }

export interface Net {
  name: string;
  refdesPins: Array<{ refdes: Refdes; pin: string }>;
}

export interface PcbData {
  boundsMm: Rect;
  layers: LayerInfo[];
  stackup: StackupLayer[];
  footprints: FootprintGeom[];
  tracks: TrackSeg[];
  vias: Via[];
  zones: Zone[];
  drills: Drill[];
  boardGraphics: Graphic[];          // board-level lines/arcs/polys/text (edge cuts, free drawings)
}

export interface LayerInfo { id: string; name: string; type: LayerType; defaultColor: string; }
export type LayerType =
  | 'F.Cu' | 'B.Cu' | 'In.Cu'
  | 'F.SilkS' | 'B.SilkS'
  | 'F.Mask' | 'B.Mask'
  | 'F.Paste' | 'B.Paste'
  | 'F.CrtYd' | 'B.CrtYd'
  | 'F.Fab' | 'B.Fab'
  | 'Edge.Cuts' | 'Margin'
  | 'Other';

export interface StackupLayer { name: string; type: string; thicknessMm: number; }
export interface FootprintGeom {
  uuid: Uuid; refdes: Refdes;
  position: Point; rotationDeg: number; side: 'top' | 'bottom';
  bboxMm: Rect;
  pads: Pad[];
  graphics: Graphic[];               // silk/fab lines, text
}
export interface Pad {
  number: string;
  shape: string;
  layerIds: string[];
  positionMm: Point;
  sizeMm: Size;
  drillMm?: number | undefined;      // set for through-hole pads
  netName: string | null;
}
export interface Graphic { layerId: string; geom: GraphicGeom; }
export type GraphicGeom =
  | { kind: 'line'; a: Point; b: Point; widthMm: number }
  | { kind: 'arc'; center: Point; radiusMm: number; startDeg: number; endDeg: number; widthMm: number }
  | { kind: 'polygon'; points: Point[]; widthMm: number; filled: boolean }
  | {
      kind: 'text';
      position: Point;
      rotationDeg: number;
      heightMm: number;
      text: string;
      hAlign?: 'left' | 'center' | 'right';
      vAlign?: 'top' | 'center' | 'bottom';
      bold?: boolean;
      italic?: boolean;
    };
export interface TrackSeg { layerId: string; a: Point; b: Point; widthMm: number; netName: string | null; }
export interface Via { position: Point; diameterMm: number; drillMm: number; layerFrom: string; layerTo: string; netName: string | null; }
export interface Zone { layerId: string; polygon: Point[]; netName: string | null; }
export interface Drill { position: Point; diameterMm: number; plated: boolean; }
export interface Point { x: number; y: number; }
export interface Size { w: number; h: number; }
export interface Rect { x: number; y: number; w: number; h: number; }
