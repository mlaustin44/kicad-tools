import type { Project, Sheet, TitleBlockInfo } from '$lib/model/project';
import {
  KicadSch,
  Rectangle,
  Polyline,
  Circle,
  Arc,
  Text,
  TextBox,
  type Wire,
  type Junction,
  type NetLabel,
  type GlobalLabel,
  type HierarchicalLabel,
  type SchematicSymbol,
  type SchematicSheet,
  type SchematicSheetPin,
  type NoConnect,
  type LibSymbol,
  type Property,
  type PinDefinition
} from '$lib/parser/schematic';
import type { Effects, Stroke } from '$lib/parser/common';

// --- constants (all mm, matching KiCad defaults) ---
const WIRE_W = 0.1524;          // wire_width — 6 mils
const LIB_W = 0.1524;           // default symbol line width
const NOCONNECT_HALF = 0.635;   // 1/2 of 50 mil X
const JUNCTION_DEFAULT_R = 0.45;
const PIN_NAME_OFFSET = 0.508;
const PIN_NUM_SIZE = 1.27;
const PIN_NAME_SIZE = 1.27;

const PAGE_MARGIN = 10;
const TITLE_W_A3 = 165;
const TITLE_W_A4 = 130;
const TITLE_H = 35;

// ---------- entry ----------

export function buildSheetSvg(project: Project, sheet: Sheet): string {
  const { x, y, w, h } = sheet.boundsMm;
  const parts: string[] = [];

  if (sheet.rawSch) {
    try {
      const sch = new KicadSch(sheet.name, sheet.rawSch);
      // Back-to-front ordering so later layers win on overlap.
      parts.push(...userGraphicsParts(sch));
      parts.push(...sheetSymbolParts(sch));
      parts.push(...symbolParts(sch));
      parts.push(...wireParts(sch));
      parts.push(...junctionParts(sch));
      parts.push(...noConnectParts(sch));
      parts.push(...labelParts(sch));
    } catch {
      parts.push(...fallbackSymbolBoxes(project, sheet));
    }
  } else {
    parts.push(...fallbackSymbolBoxes(project, sheet));
  }

  const frame = pageFrameAndTitleBlock(sheet);

  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${fmt(x)} ${fmt(y)} ${fmt(w)} ${fmt(h)}" ` +
    `preserveAspectRatio="xMidYMid meet" ` +
    `style="color: var(--kv-text); width: 100%; height: 100%">` +
    parts.join('') +
    frame +
    `</svg>`
  );
}

// ---------- page frame + title block ----------

function pageFrameAndTitleBlock(sheet: Sheet): string {
  const { x, y, w, h } = sheet.boundsMm;
  if (w <= 0 || h <= 0) return '';

  const m = PAGE_MARGIN;
  const innerX = x + m;
  const innerY = y + m;
  const innerW = Math.max(0, w - 2 * m);
  const innerH = Math.max(0, h - 2 * m);

  const borders =
    `<g class="sch-page-frame" fill="none" stroke="currentColor" ` +
    `stroke-width="${fmt(0.25)}" opacity="0.55">` +
    `<rect x="${fmt(x + m / 2)}" y="${fmt(y + m / 2)}" ` +
    `width="${fmt(w - m)}" height="${fmt(h - m)}"/>` +
    `<rect x="${fmt(innerX)}" y="${fmt(innerY)}" width="${fmt(innerW)}" height="${fmt(innerH)}"/>` +
    `</g>`;

  const tb = titleBlockSvg(sheet, innerX + innerW, innerY + innerH);
  return borders + tb;
}

// Layout mirrors KiCad's default drawing sheet (common/drawing_sheet/ds_default_data.cpp):
//   anchored bottom-right, ~180mm wide on large paper, stacked rows from TOP of box
//   downward: comments, company, file+sheet, title, size/date/rev, kicad+id.
function titleBlockSvg(sheet: Sheet, rightX: number, bottomY: number): string {
  const info = sheet.titleBlock;
  const paper = sheet.paper ?? 'A4';
  const largePaper = paper === 'A3' || paper === 'A2' || paper === 'A1' || paper === 'A0';
  const boxW = largePaper ? TITLE_W_A3 : TITLE_W_A4;
  const boxH = TITLE_H;
  const x0 = rightX - boxW;
  const y0 = bottomY - boxH;

  const title = info?.title ?? sheet.name ?? '';
  const company = info?.company ?? '';
  const rev = info?.rev ?? '';
  const date = info?.date ?? '';
  const comments = (info?.comments ?? []).filter((c) => c);
  const fileName = sheet.name ? `${sheet.name}.kicad_sch` : '';
  const sheetPath = sheet.path.length <= 1 ? '/' : '/' + sheet.path.slice(1).join('/');
  const paperLabel = paper;

  // Row layout (TOP to BOTTOM of box):
  //   commentsH   — stacked comment lines (2mm each, up to 4)
  //   companyH    — company name
  //   fileSheetH  — "Sheet:" + "File:" stacked
  //   titleH      — TALL, bold title
  //   sizeDateRevH — 3 columns
  //   kicadIdH    — 2 columns
  // The top three rows collapse if their data is empty so the title always has
  // prominence.
  const commentRows = Math.min(comments.length, 4);
  const commentsH = commentRows > 0 ? Math.max(4, commentRows * 2) : 0;
  const companyH = company ? 4 : 0;
  const fileSheetH = 6;
  const sizeDateRevH = 5;
  const kicadIdH = 4;
  const titleH = Math.max(
    6,
    boxH - commentsH - companyH - fileSheetH - sizeDateRevH - kicadIdH
  );

  // Vertical y-offsets (absolute y in sheet frame).
  const yComments = y0;
  const yCompany = yComments + commentsH;
  const yFileSheet = yCompany + companyH;
  const yTitle = yFileSheet + fileSheetH;
  const ySizeDateRev = yTitle + titleH;
  const yKicadId = ySizeDateRev + sizeDateRevH;

  // Column splits for the size/date/rev + kicad/id rows.
  const col1X = x0;
  const col2X = x0 + boxW * 0.4;   // size/kicad  | date
  const col3X = x0 + boxW * 0.72;  // date        | rev/id
  const colEndX = x0 + boxW;

  const parts: string[] = [];
  // Outer border
  parts.push(
    `<rect x="${fmt(x0)}" y="${fmt(y0)}" width="${fmt(boxW)}" height="${fmt(boxH)}" ` +
      `fill="none" stroke="currentColor" stroke-width="${fmt(0.35)}"/>`
  );

  // Horizontal rules between rows (skip zero-height rows).
  const hRule = (y: number): string =>
    `<line x1="${fmt(x0)}" y1="${fmt(y)}" x2="${fmt(colEndX)}" y2="${fmt(y)}" ` +
    `stroke="currentColor" stroke-width="${fmt(0.2)}" opacity="0.7"/>`;
  if (commentsH > 0) parts.push(hRule(yCompany));
  if (companyH > 0) parts.push(hRule(yFileSheet));
  parts.push(hRule(yTitle));
  parts.push(hRule(ySizeDateRev));
  parts.push(hRule(yKicadId));

  // Vertical splits inside size/date/rev and kicad/id rows.
  const vRule = (x: number, ya: number, yb: number): string =>
    `<line x1="${fmt(x)}" y1="${fmt(ya)}" x2="${fmt(x)}" y2="${fmt(yb)}" ` +
    `stroke="currentColor" stroke-width="${fmt(0.2)}" opacity="0.7"/>`;
  parts.push(vRule(col2X, ySizeDateRev, y0 + boxH));
  parts.push(vRule(col3X, ySizeDateRev, y0 + boxH));

  // Padding inside cells.
  const padX = 1.5;
  const labelSize = 1.4;
  const valSize = 2.0;
  const titleSize = largePaper ? 4.2 : 3.4;

  // Comments (oldest at top, newest at bottom of their row).
  for (let i = 0; i < commentRows; i++) {
    const cy = yComments + (i + 0.7) * (commentsH / Math.max(1, commentRows));
    const c = comments[i];
    if (c) parts.push(tbText(x0 + padX, cy, c, { size: labelSize }));
  }

  // Company
  if (company) {
    parts.push(tbText(x0 + padX, yCompany + companyH * 0.72, company, { size: valSize, bold: true }));
  }

  // Sheet + File (two small labeled entries, stacked).
  parts.push(tbLabeled(x0 + padX, yFileSheet + 2.4, 'Sheet:', sheetPath));
  parts.push(tbLabeled(x0 + padX, yFileSheet + 5.0, 'File:', fileName));

  // Title row — "Title:" label tucked top-left, big bold value centered on the row.
  parts.push(tbText(x0 + padX, yTitle + 2, 'Title:', { size: labelSize, dim: true }));
  parts.push(
    tbText(x0 + padX, yTitle + titleH * 0.72, title, { size: titleSize, bold: true })
  );

  // Size / Date / Rev row.
  parts.push(tbLabeled(col1X + padX, ySizeDateRev + 3.2, 'Size:', paperLabel));
  parts.push(tbLabeled(col2X + padX, ySizeDateRev + 3.2, 'Date:', date));
  parts.push(tbLabeled(col3X + padX, ySizeDateRev + 3.2, 'Rev:', rev, { valueBold: true }));

  // KiCad E.D.A. + Id row.
  parts.push(
    tbText(col1X + padX, yKicadId + kicadIdH * 0.7, 'KiCad E.D.A.', { size: labelSize })
  );
  parts.push(tbLabeled(col3X + padX, yKicadId + kicadIdH * 0.7, 'Id:', '1/1'));

  return `<g class="sch-title-block">${parts.join('')}</g>`;
}

// Small text helper.
function tbText(
  x: number, y: number, text: string,
  opts: { size: number; bold?: boolean; dim?: boolean }
): string {
  if (!text) return '';
  const weight = opts.bold ? ' font-weight="700"' : '';
  const op = opts.dim ? ' opacity="0.65"' : '';
  return (
    `<text x="${fmt(x)}" y="${fmt(y)}" font-size="${fmt(opts.size)}" ` +
    `fill="currentColor"${weight}${op}>${escapeText(text)}</text>`
  );
}

// Label + value on the same baseline: tiny italic label, then value beside it.
function tbLabeled(
  x: number, y: number, label: string, value: string,
  opts: { valueBold?: boolean } = {}
): string {
  const labelSvg =
    `<text x="${fmt(x)}" y="${fmt(y)}" font-size="${fmt(1.3)}" ` +
    `fill="currentColor" opacity="0.6" font-style="italic">${escapeText(label)}</text>`;
  const labelWidth = label.length * 0.75; // rough advance for 1.3pt
  if (!value) return labelSvg;
  const weight = opts.valueBold ? ' font-weight="700"' : '';
  return (
    labelSvg +
    `<text x="${fmt(x + labelWidth + 0.8)}" y="${fmt(y)}" font-size="${fmt(1.9)}" ` +
    `fill="currentColor"${weight}>${escapeText(value)}</text>`
  );
}

// ---------- user graphics (top-level) ----------

function userGraphicsParts(sch: KicadSch): string[] {
  const out: string[] = [];
  // Top-level drawings live on sch.drawings (Polyline/Text/Circle/Image) plus
  // images[], and rectangles/arcs are parsed as drawings too in KiCad 7+.
  // Our vendored parser lumps them into drawings[] with mixed types.
  const drawings = (sch as unknown as { drawings?: unknown[] }).drawings ?? [];
  for (const d of drawings) {
    out.push(renderGraphicItem(d));
  }
  // text_box lives separately in some files; KicadSch.drawings includes it if present.
  // Rectangles at top level are not in drawings[] on older vendored parser — check.
  const rects = (sch as unknown as { rectangles?: unknown[] }).rectangles ?? [];
  for (const r of rects) out.push(renderGraphicItem(r));

  return out.filter((s) => s.length > 0);
}

function renderGraphicItem(d: unknown): string {
  if (d instanceof Rectangle) {
    const x = Math.min(d.start.x, d.end.x);
    const y = Math.min(d.start.y, d.end.y);
    const w = Math.abs(d.end.x - d.start.x);
    const h = Math.abs(d.end.y - d.start.y);
    const { stroke, sw, dash } = strokeAttrs(d.stroke, LIB_W);
    const fill = fillAttr(d);
    return (
      `<rect x="${fmt(x)}" y="${fmt(y)}" width="${fmt(w)}" height="${fmt(h)}" ` +
      `fill="${fill}" stroke="${stroke}" stroke-width="${fmt(sw)}"${dash}/>`
    );
  }
  if (d instanceof Polyline) {
    const pts = (d.pts ?? []).map((p) => `${fmt(p.x)},${fmt(p.y)}`).join(' ');
    if (!pts) return '';
    const { stroke, sw, dash } = strokeAttrs(d.stroke, LIB_W);
    const fill = fillAttr(d);
    return (
      `<polyline points="${pts}" fill="${fill}" stroke="${stroke}" ` +
      `stroke-width="${fmt(sw)}"${dash} stroke-linecap="round" stroke-linejoin="round"/>`
    );
  }
  if (d instanceof Circle) {
    const { stroke, sw, dash } = strokeAttrs(d.stroke, LIB_W);
    const fill = fillAttr(d);
    return (
      `<circle cx="${fmt(d.center.x)}" cy="${fmt(d.center.y)}" r="${fmt(d.radius)}" ` +
      `fill="${fill}" stroke="${stroke}" stroke-width="${fmt(sw)}"${dash}/>`
    );
  }
  if (d instanceof Arc) {
    return arcPath(d, 1);
  }
  if (d instanceof Text) {
    return renderTextNode(d, 'text');
  }
  if (d instanceof TextBox) {
    return renderTextBox(d);
  }
  return '';
}

function renderTextBox(tb: TextBox): string {
  const x = tb.at?.position?.x ?? 0;
  const y = tb.at?.position?.y ?? 0;
  const w = tb.size?.x ?? 0;
  const h = tb.size?.y ?? 0;
  const { stroke, sw, dash } = strokeAttrs(tb.stroke, LIB_W);
  const fill = fillAttr(tb);
  const bg = w > 0 && h > 0
    ? `<rect x="${fmt(x)}" y="${fmt(y)}" width="${fmt(w)}" height="${fmt(h)}" ` +
      `fill="${fill}" stroke="${stroke}" stroke-width="${fmt(sw)}"${dash}/>`
    : '';
  const text = tb.text ?? '';
  const tx = x + 0.5;
  const ty = y + (tb.effects?.font?.size?.y ?? 1.27);
  return (
    bg +
    `<text x="${fmt(tx)}" y="${fmt(ty)}" ` +
    `font-size="${fmt(tb.effects?.font?.size?.y ?? 1.27)}" ` +
    `fill="currentColor">${escapeText(text)}</text>`
  );
}

// Render a standalone Text element (at top level, y-down schematic frame, not lib).
function renderTextNode(t: Text, _kind: 'text' | 'libtext'): string {
  const p = t.at?.position;
  if (!p) return '';
  const text = t.shown_text ?? t.text ?? '';
  if (!text) return '';
  const rot = t.at?.rotation ?? 0;
  const { size, weight, anchor, baseline } = effectsAttrs(t.effects);
  const transform = rot
    ? ` transform="rotate(${fmt(-rot)} ${fmt(p.x)} ${fmt(p.y)})"`
    : '';
  return (
    `<text x="${fmt(p.x)}" y="${fmt(p.y)}" font-size="${fmt(size)}" ` +
    `text-anchor="${anchor}" dominant-baseline="${baseline}"${weight}` +
    ` fill="currentColor"${transform}>${escapeText(text)}</text>`
  );
}

// ---------- wires, junctions, no-connects ----------

function wireParts(sch: KicadSch): string[] {
  const out: string[] = [];
  for (const w of sch.wires as Wire[]) {
    const pts = w.pts ?? [];
    for (let i = 0; i + 1 < pts.length; i++) {
      const a = pts[i];
      const b = pts[i + 1];
      if (!a || !b) continue;
      out.push(
        `<line x1="${fmt(a.x)}" y1="${fmt(a.y)}" x2="${fmt(b.x)}" y2="${fmt(b.y)}" ` +
          `stroke="currentColor" stroke-width="${fmt(WIRE_W)}" stroke-linecap="round"/>`
      );
    }
  }
  return out;
}

function junctionParts(sch: KicadSch): string[] {
  const out: string[] = [];
  for (const j of sch.junctions as Junction[]) {
    const p = j.at?.position;
    if (!p) continue;
    const r = j.diameter && j.diameter > 0 ? j.diameter / 2 : JUNCTION_DEFAULT_R;
    out.push(
      `<circle cx="${fmt(p.x)}" cy="${fmt(p.y)}" r="${fmt(r)}" fill="currentColor"/>`
    );
  }
  return out;
}

function noConnectParts(sch: KicadSch): string[] {
  const out: string[] = [];
  const list = (sch as unknown as { no_connects?: NoConnect[] }).no_connects ?? [];
  for (const nc of list) {
    const p = nc.at?.position;
    if (!p) continue;
    const s = NOCONNECT_HALF;
    out.push(
      `<g class="sch-no-connect" stroke="currentColor" stroke-width="${fmt(0.15)}" stroke-linecap="round">` +
      `<line x1="${fmt(p.x - s)}" y1="${fmt(p.y - s)}" x2="${fmt(p.x + s)}" y2="${fmt(p.y + s)}"/>` +
      `<line x1="${fmt(p.x - s)}" y1="${fmt(p.y + s)}" x2="${fmt(p.x + s)}" y2="${fmt(p.y - s)}"/>` +
      `</g>`
    );
  }
  return out;
}

// ---------- labels ----------

function labelParts(sch: KicadSch): string[] {
  const out: string[] = [];
  for (const lbl of (sch.net_labels ?? []) as NetLabel[]) {
    out.push(renderNetLabel(lbl));
  }
  for (const lbl of (sch.global_labels ?? []) as GlobalLabel[]) {
    out.push(renderShapedLabel(lbl, 'global'));
  }
  for (const lbl of (sch.hierarchical_labels ?? []) as HierarchicalLabel[]) {
    out.push(renderShapedLabel(lbl, 'hier'));
  }
  return out.filter((s) => s.length > 0);
}

function renderNetLabel(lbl: NetLabel): string {
  const p = lbl.at?.position;
  if (!p) return '';
  const text = lbl.shown_text ?? lbl.text ?? '';
  if (!text) return '';
  const rot = lbl.at?.rotation ?? 0;
  const { size, weight } = effectsAttrs(lbl.effects);
  const { anchor, transform } = labelOrientation(p.x, p.y, rot);
  // NetLabel anchored just above the wire point.
  return (
    `<text x="${fmt(p.x)}" y="${fmt(p.y - 0.3)}" font-size="${fmt(size)}" ` +
    `text-anchor="${anchor}" data-net="${escapeAttr(text)}" ` +
    `fill="currentColor"${weight}${transform}>${escapeText(text)}</text>`
  );
}

function renderShapedLabel(
  lbl: GlobalLabel | HierarchicalLabel,
  kind: 'global' | 'hier'
): string {
  const p = lbl.at?.position;
  if (!p) return '';
  const text = lbl.shown_text ?? lbl.text ?? '';
  if (!text) return '';
  const rot = ((lbl.at?.rotation ?? 0) % 360 + 360) % 360;
  const size = lbl.effects?.font?.size?.y ?? 1.27;
  const { weight } = effectsAttrs(lbl.effects);
  const shape = (lbl as GlobalLabel).shape ?? 'passive';

  // Estimate text width; glyph aspect for a sans font ~0.6.
  const textW = text.length * size * 0.6;
  const h = size * 1.4;
  const tip = size * 0.55;
  // Build polygon in local frame where text reads left-to-right, origin at the pin.
  // Global labels: rightward arrow shape (pointy end on the wire side).
  // Hierarchical labels: flag shape.
  const padX = size * 0.4;
  const w = textW + padX * 2 + tip;
  const pts: Array<[number, number]> = kind === 'global'
    ? globalLabelPoints(shape, w, h, tip)
    : hierLabelPoints(shape, w, h, tip);
  const poly = pts.map(([x, y]) => `${fmt(x)},${fmt(y)}`).join(' ');

  const { anchor, transform } = labelOrientation(p.x, p.y, rot);
  // For hierarchical sheet pins / hier-labels and global labels, the text sits
  // inside the polygon: offset from the pin side.
  const textOffsetX = tip + padX;
  // Local text position (anchor start, baseline middle → y=0).
  const dy = size * 0.35;

  return (
    `<g class="sch-label ${kind}" data-net="${escapeAttr(text)}" ` +
    `transform="translate(${fmt(p.x)} ${fmt(p.y)})${polyRotate(rot)}">` +
    `<polygon points="${poly}" fill="none" stroke="currentColor" stroke-width="${fmt(0.15)}"/>` +
    `<text x="${fmt(textOffsetX)}" y="${fmt(dy)}" font-size="${fmt(size)}" ` +
    `text-anchor="${anchor === 'end' ? 'start' : 'start'}" ` +
    `fill="currentColor"${weight}${transform === '' ? '' : ''}>${escapeText(text)}</text>` +
    `</g>`
  );
}

function polyRotate(rot: number): string {
  // Flip horizontally for rot=180 so the arrow points the right way, using
  // scale(-1,1) which also needs a text counter-flip handled at the text level.
  switch (rot) {
    case 0: return '';
    case 90: return ' rotate(-90)';
    case 180: return ' scale(-1 1)';
    case 270: return ' rotate(90)';
    default: return ` rotate(${fmt(-rot)})`;
  }
}

function globalLabelPoints(shape: string, w: number, h: number, tip: number): Array<[number, number]> {
  const h2 = h / 2;
  // A rightward arrow: pin at (0,0), tip pokes into the wire on the left.
  // Text sits from tip to w, with pointed left side.
  switch (shape) {
    case 'output':
      // Pointy tail on the right side
      return [
        [0, 0],
        [tip, -h2],
        [w - tip, -h2],
        [w, 0],
        [w - tip, h2],
        [tip, h2]
      ];
    case 'input':
      // Flat pin side, pointy opposite side
      return [
        [0, -h2],
        [w - tip, -h2],
        [w, 0],
        [w - tip, h2],
        [0, h2]
      ];
    case 'bidirectional':
    case 'tri_state':
      return [
        [0, 0],
        [tip, -h2],
        [w - tip, -h2],
        [w, 0],
        [w - tip, h2],
        [tip, h2]
      ];
    case 'passive':
    default:
      return [
        [0, -h2],
        [w, -h2],
        [w, h2],
        [0, h2]
      ];
  }
}

function hierLabelPoints(shape: string, w: number, h: number, tip: number): Array<[number, number]> {
  // Hierarchical labels use rectangular tag with a pointed connector arrow on
  // the pin side; keep it simple and match global shape for this pass.
  return globalLabelPoints(shape, w, h, tip);
}

function labelOrientation(_x: number, _y: number, rot: number): { anchor: 'start' | 'end'; transform: string } {
  const r = ((rot % 360) + 360) % 360;
  // Orientation reflected in the outer group rotate; text just goes left-to-right within.
  return { anchor: r === 180 ? 'end' : 'start', transform: '' };
}

// ---------- symbols (components + power) ----------

function symbolParts(sch: KicadSch): string[] {
  const out: string[] = [];
  for (const sym of sch.symbols.values() as IterableIterator<SchematicSymbol>) {
    if (!sym) continue;
    const refdes = sym.reference || '?';
    const uuid = sym.uuid ?? `${refdes}`;
    const p = sym.at?.position;
    if (!p) continue;
    const rot = sym.at?.rotation ?? 0;
    const mirror = sym.mirror; // 'x' | 'y' | undefined
    const isPower = refdes.startsWith('#');

    let lib: LibSymbol | undefined;
    try { lib = sym.lib_symbol; } catch { lib = undefined; }

    // Graphics + pin lines inside the symbol's mirror/rotation transform.
    const transformedChildren: string[] = [];
    if (lib) {
      const graphicSvg = renderLibSymbol(lib);
      if (graphicSvg) transformedChildren.push(graphicSvg);
    }

    // Hitbox: transparent rect spanning the full lib-symbol bounds so empty
    // areas of stroke-only symbols (caps, ferrite beads) can be clicked, and so
    // the selection highlight has a rect target on every symbol shape.
    if (lib) {
      const bb = libSymbolBounds(lib);
      if (bb) {
        const { minX, minY, maxX, maxY } = bb;
        const pad = 0.4;
        transformedChildren.push(
          `<rect class="sch-hitbox" ` +
          `x="${fmt(minX - pad)}" y="${fmt(minY - pad)}" ` +
          `width="${fmt(maxX - minX + 2 * pad)}" height="${fmt(maxY - minY + 2 * pad)}" ` +
          `fill="none" stroke="none" pointer-events="all"/>`
        );
      }
    }

    // DNP ✗ overlay — two diagonal strokes across the lib-symbol bounding box,
    // drawn in lib coords (the outer matrix handles the y-flip).
    if (sym.dnp && lib) {
      const bb = libSymbolBounds(lib);
      if (bb) {
        const { minX, minY, maxX, maxY } = bb;
        transformedChildren.push(
          `<g stroke="#d03232" stroke-width="${fmt(0.35)}" ` +
          `stroke-linecap="round" opacity="0.9">` +
          `<line x1="${fmt(minX)}" y1="${fmt(minY)}" x2="${fmt(maxX)}" y2="${fmt(maxY)}"/>` +
          `<line x1="${fmt(minX)}" y1="${fmt(maxY)}" x2="${fmt(maxX)}" y2="${fmt(minY)}"/>` +
          `</g>`
        );
      }
    }

    // Outer transform: compute the full 2x2 orientation matrix the way KiCad
    // does (see SCH_PAINTER::orientSymbol / KiCanvas's get_symbol_transform).
    // KiCanvas builds a 3x3 row-vector matrix; the SVG `matrix(a,b,c,d,e,f)`
    // column-vector form accepts those elements directly in the same slots, so
    // we can emit one combined transform instead of juggling rotate/scale
    // composition (which composes differently across row vs column vector
    // conventions and produces the wrong result for mirrored+rotated symbols).
    const outerTransform = ` transform="${symbolOrientMatrix(p, rot, mirror)}"`;

    // Pin text emitted OUTSIDE the mirror/rotation transform so glyphs stay
    // right-side-up regardless of symbol orientation. Each pin's anchor and
    // direction are transformed to the sheet frame first.
    const pinTextSvg = lib ? renderPinsSheetFrame(lib, sym) : '';

    out.push(
      `<g data-refdes="${escapeAttr(refdes)}" data-uuid="${escapeAttr(uuid)}" ` +
      `class="${isPower ? 'sch-power' : 'sch-symbol'}">` +
      `<g${outerTransform}>` + transformedChildren.join('') + `</g>` +
      pinTextSvg +
      `</g>`
    );

    // Properties (reference, value, etc.) are rendered in the SHEET frame,
    // not rotated with the symbol, because property.at is in absolute sheet coords.
    out.push(renderSymbolProperties(sym));
  }
  return out;
}

// Build the SVG `matrix(...)` transform for a symbol instance. Mirrors KiCad's
// own SCH_PAINTER::orientSymbol: start from a base y-flip (lib math frame is
// y-up, sheet frame is y-down) that also encodes the rotation, then apply the
// mirror by negating specific matrix entries.
function symbolOrientMatrix(
  pos: { x: number; y: number },
  rot: number,
  mirror: 'x' | 'y' | undefined
): string {
  const r = ((rot % 360) + 360) % 360;
  // KiCanvas row-vector elements [e0, e1; e3, e4] for each cardinal rotation.
  // With SVG's column-vector matrix(a, b, c, d, e, f) = [a c e; b d f], setting
  // (a,b,c,d) = (e0,e1,e3,e4) gives us the same geometric transform that KiCad
  // applies internally. That correspondence is the key to avoiding the
  // compose-rotate-and-scale pitfall for rotated+mirrored symbols.
  let e0: number, e1: number, e3: number, e4: number;
  if (r === 90) {        e0 = 0;  e1 = -1; e3 = -1; e4 = 0; }
  else if (r === 180) {  e0 = -1; e1 = 0;  e3 = 0;  e4 = 1; }
  else if (r === 270) {  e0 = 0;  e1 = 1;  e3 = 1;  e4 = 0; }
  else {                 e0 = 1;  e1 = 0;  e3 = 0;  e4 = -1; } // default rot=0
  if (mirror === 'y') { e0 = -e0; e3 = -e3; }
  else if (mirror === 'x') { e1 = -e1; e4 = -e4; }
  return `matrix(${fmt(e0)} ${fmt(e1)} ${fmt(e3)} ${fmt(e4)} ${fmt(pos.x)} ${fmt(pos.y)})`;
}

// Orientation 2x2 matrix elements [e0, e1, e3, e4] — the same ones used by
// symbolOrientMatrix to build the SVG transform. Kept separate so pin text
// (rendered outside that transform) can be positioned consistently.
function symbolMatrixElements(sym: SchematicSymbol): [number, number, number, number] {
  const r = (((sym.at?.rotation ?? 0) % 360) + 360) % 360;
  let e0: number, e1: number, e3: number, e4: number;
  if (r === 90) {        e0 = 0;  e1 = -1; e3 = -1; e4 = 0; }
  else if (r === 180) {  e0 = -1; e1 = 0;  e3 = 0;  e4 = 1; }
  else if (r === 270) {  e0 = 0;  e1 = 1;  e3 = 1;  e4 = 0; }
  else {                 e0 = 1;  e1 = 0;  e3 = 0;  e4 = -1; }
  const mirror = sym.mirror;
  if (mirror === 'y') { e0 = -e0; e3 = -e3; }
  else if (mirror === 'x') { e1 = -e1; e4 = -e4; }
  return [e0, e1, e3, e4];
}

// Transform a lib-math (y-up) point to sheet frame (y-down), applying the
// symbol's mirror and rotation via the orientation matrix.
function transformLibPoint(
  lx: number,
  ly: number,
  sym: SchematicSymbol
): { x: number; y: number } {
  const p = sym.at!.position;
  const [e0, e1, e3, e4] = symbolMatrixElements(sym);
  return { x: p.x + e0 * lx + e3 * ly, y: p.y + e1 * lx + e4 * ly };
}

// Transform a pin's outward angle (degrees, lib y-up frame) to sheet frame
// (degrees, y-down). Uses the same matrix so direction stays consistent with
// the transformed symbol position.
function transformLibAngle(pinAngleDeg: number, sym: SchematicSymbol): number {
  const rad = (pinAngleDeg * Math.PI) / 180;
  const dx = Math.cos(rad);
  const dy = Math.sin(rad);
  const [e0, e1, e3, e4] = symbolMatrixElements(sym);
  const worldDx = e0 * dx + e3 * dy;
  const worldDy = e1 * dx + e4 * dy;
  const a = (Math.atan2(worldDy, worldDx) * 180) / Math.PI;
  return ((a % 360) + 360) % 360;
}

function renderPinsSheetFrame(lib: LibSymbol, sym: SchematicSymbol): string {
  const pins: PinDefinition[] = [...lib.pins];
  for (const child of lib.children ?? []) pins.push(...child.pins);
  const hideNames = lib.pin_names?.hide ?? false;
  const hideNumbers = lib.pin_numbers?.hide ?? false;
  const nameOffset = lib.pin_names?.offset ?? PIN_NAME_OFFSET;
  const parts: string[] = [];
  for (const pin of pins) {
    if (pin.hide) continue;
    parts.push(renderPinTextWorld(pin, sym, nameOffset, hideNames, hideNumbers));
  }
  return parts.join('');
}

function renderPinTextWorld(
  pin: PinDefinition,
  sym: SchematicSymbol,
  nameOffset: number,
  hideNames: boolean,
  hideNumbers: boolean
): string {
  const pp = pin.at?.position;
  if (!pp) return '';
  const len = pin.length ?? 2.54;
  const pinAng = pin.at?.rotation ?? 0;
  const anchorWorld = transformLibPoint(pp.x, pp.y, sym);
  const worldAng = transformLibAngle(pinAng, sym);
  const rad = (worldAng * Math.PI) / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  const endX = anchorWorld.x + cos * len;
  const endY = anchorWorld.y + sin * len;

  // Snap world angle to nearest cardinal (KiCad pins are axis-aligned).
  const norm = Math.round(worldAng / 90) * 90 % 360;
  const vertical = norm === 90 || norm === 270;
  const glyphRot = vertical ? 90 : 0;
  // Name extends AWAY from the symbol along the outward direction.
  const nameAnchor: 'start' | 'end' = norm === 180 || norm === 270 ? 'end' : 'start';

  const out: string[] = [];

  if (!hideNames && pin.name?.text && pin.name.text !== '~') {
    const nx = endX + cos * nameOffset;
    const ny = endY + sin * nameOffset;
    const nameSize = pin.name.effects?.font?.size?.y ?? PIN_NAME_SIZE;
    out.push(
      `<g transform="translate(${fmt(nx)} ${fmt(ny)}) rotate(${fmt(glyphRot)})">` +
      `<text x="0" y="0" font-size="${fmt(nameSize)}" text-anchor="${nameAnchor}" ` +
      `dominant-baseline="middle" fill="currentColor">` +
      escapeText(pin.name.text) +
      `</text></g>`
    );
  }

  if (!hideNumbers && pin.number?.text) {
    // Place number above the pin line (perpendicular offset, rotated outward=0
    // sits +Y locally). Midpoint between the pin anchor and its end.
    const mx = (anchorWorld.x + endX) / 2;
    const my = (anchorWorld.y + endY) / 2;
    // Perpendicular offset: rotate outward by -90° (y-down) so the number sits
    // on the "upper" side when the pin is drawn left-to-right.
    const perpX = sin * 0.6;
    const perpY = -cos * 0.6;
    const numSize = pin.number.effects?.font?.size?.y ?? PIN_NUM_SIZE;
    out.push(
      `<g transform="translate(${fmt(mx + perpX)} ${fmt(my + perpY)}) rotate(${fmt(glyphRot)})">` +
      `<text x="0" y="0" font-size="${fmt(numSize * 0.85)}" text-anchor="middle" ` +
      `dominant-baseline="alphabetic" fill="currentColor" opacity="0.85">` +
      escapeText(pin.number.text) +
      `</text></g>`
    );
  }

  return out.join('');
}

function renderSymbolProperties(sym: SchematicSymbol): string {
  const propsMap = sym.properties as Map<string, Property>;
  if (!propsMap) return '';
  // KiCad stores each property's rotation as (symbol_rotation + intended_display_rotation):
  // the symbol's own rotation is baked in. Subtract it back out to recover what the
  // reader should see. Verified against fixtures: FB1 (sym=90, prop=90, displays 0°),
  // Q3 (sym=270, prop=90, displays 180° = horizontal with flipped anchor), R1 (0/0 → 0°).
  const symRot = sym.at?.rotation ?? 0;
  const parts: string[] = [];
  for (const prop of propsMap.values()) {
    const text = prop.shown_text ?? prop.text ?? '';
    if (!text || text === '~') continue;
    if (prop.hide) continue;
    if (prop.effects?.hide) continue;
    const p = prop.at?.position;
    if (!p) continue;
    const propRot = prop.at?.rotation ?? 0;
    const effective = (((propRot - symRot) % 360) + 360) % 360;

    // Never upside-down: 0°/180° render as horizontal text; 90°/270° as vertical.
    // The "flipped" halves (180° and 270°) use opposite text-anchor instead of
    // an inverting rotation.
    const vertical = effective === 90 || effective === 270;
    const flipped = effective === 180 || effective === 270;
    const glyphRot = vertical ? -90 : 0;

    const { size, weight } = effectsAttrs(prop.effects);
    // Honor explicit justify; otherwise pick anchor based on the effective rotation.
    const jh = prop.effects?.justify?.horizontal;
    const jv = prop.effects?.justify?.vertical;
    let anchor: 'start' | 'middle' | 'end';
    if (jh === 'left') anchor = flipped ? 'end' : 'start';
    else if (jh === 'right') anchor = flipped ? 'start' : 'end';
    else if (jh === 'center') anchor = 'middle';
    else anchor = flipped ? 'end' : 'start';
    const baseline =
      jv === 'top' ? 'hanging' : jv === 'bottom' ? 'alphabetic' : 'middle';

    const transform = glyphRot
      ? ` transform="rotate(${fmt(glyphRot)} ${fmt(p.x)} ${fmt(p.y)})"`
      : '';
    const cls = prop.name === 'Reference'
      ? 'sch-refdes'
      : prop.name === 'Value' ? 'sch-value' : 'sch-prop';
    parts.push(
      `<text x="${fmt(p.x)}" y="${fmt(p.y)}" class="${cls}" ` +
      `font-size="${fmt(size)}" text-anchor="${anchor}" ` +
      `dominant-baseline="${baseline}"${weight} fill="currentColor"${transform}>` +
      escapeText(text) +
      `</text>`
    );
  }
  return parts.join('');
}

interface LibBounds { minX: number; minY: number; maxX: number; maxY: number; }
function libSymbolBounds(lib: LibSymbol): LibBounds | null {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const visit = (d: unknown): void => {
    if (d instanceof Rectangle) {
      minX = Math.min(minX, d.start.x, d.end.x);
      maxX = Math.max(maxX, d.start.x, d.end.x);
      minY = Math.min(minY, d.start.y, d.end.y);
      maxY = Math.max(maxY, d.start.y, d.end.y);
    } else if (d instanceof Polyline) {
      for (const p of d.pts ?? []) {
        minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
        minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
      }
    } else if (d instanceof Circle) {
      minX = Math.min(minX, d.center.x - d.radius); maxX = Math.max(maxX, d.center.x + d.radius);
      minY = Math.min(minY, d.center.y - d.radius); maxY = Math.max(maxY, d.center.y + d.radius);
    } else if (d instanceof Arc) {
      for (const p of [d.start, d.mid, d.end]) {
        minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
        minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
      }
    }
  };
  for (const d of lib.drawings) visit(d);
  for (const child of lib.children ?? []) for (const d of child.drawings) visit(d);
  if (!isFinite(minX) || !isFinite(maxX)) return null;
  return { minX, minY, maxX, maxY };
}

function renderLibSymbol(lib: LibSymbol): string {
  // Collect drawings + pins from the symbol and its unit children.
  const drawings: unknown[] = [...lib.drawings];
  const pins: PinDefinition[] = [...lib.pins];
  for (const child of lib.children ?? []) {
    drawings.push(...child.drawings);
    pins.push(...child.pins);
  }

  const parts: string[] = [];
  // No inner y-flip here: the symbol's outer matrix (see symbolOrientMatrix)
  // already folds the lib-math (y-up) to sheet-y-down conversion into the same
  // transform as the KiCad rotation+mirror, matching SCH_PAINTER.
  parts.push(`<g>`);

  for (const d of drawings) {
    if (d instanceof Rectangle) {
      const x = Math.min(d.start.x, d.end.x);
      const y = Math.min(d.start.y, d.end.y);
      const w = Math.abs(d.end.x - d.start.x);
      const h = Math.abs(d.end.y - d.start.y);
      const { stroke, sw, dash } = strokeAttrs(d.stroke, LIB_W);
      const fill = fillAttr(d);
      parts.push(
        `<rect x="${fmt(x)}" y="${fmt(y)}" width="${fmt(w)}" height="${fmt(h)}" ` +
        `fill="${fill}" stroke="${stroke}" stroke-width="${fmt(sw)}"${dash}/>`
      );
    } else if (d instanceof Polyline) {
      const pts = (d.pts ?? []).map((p) => `${fmt(p.x)},${fmt(p.y)}`).join(' ');
      if (pts) {
        const { stroke, sw, dash } = strokeAttrs(d.stroke, LIB_W);
        const fill = fillAttr(d);
        parts.push(
          `<polyline points="${pts}" fill="${fill}" stroke="${stroke}" ` +
          `stroke-width="${fmt(sw)}"${dash} stroke-linejoin="round" stroke-linecap="round"/>`
        );
      }
    } else if (d instanceof Circle) {
      const { stroke, sw, dash } = strokeAttrs(d.stroke, LIB_W);
      const fill = fillAttr(d);
      parts.push(
        `<circle cx="${fmt(d.center.x)}" cy="${fmt(d.center.y)}" r="${fmt(d.radius)}" ` +
        `fill="${fill}" stroke="${stroke}" stroke-width="${fmt(sw)}"${dash}/>`
      );
    } else if (d instanceof Arc) {
      parts.push(arcPath(d, 1));
    } else if (d instanceof Text) {
      // LibText rotation is divided by 10 already by the parser. Render as top-level text.
      parts.push(renderLibText(d));
    }
  }

  for (const pin of pins) {
    if (pin.hide) continue;
    parts.push(renderPin(pin));
  }

  parts.push(`</g>`);
  return parts.join('');
}

function renderLibText(t: Text): string {
  const p = t.at?.position;
  if (!p) return '';
  const text = t.shown_text ?? t.text ?? '';
  if (!text) return '';
  const rot = t.at?.rotation ?? 0;
  const { size, weight, anchor, baseline } = effectsAttrs(t.effects);
  // Lib drawings now sit in a frame that matches SCH_PAINTER's matrix. No
  // counter y-flip is needed here — symbol-level mirror/rotation may still put
  // the glyph upside-down, but that concern is handled when we render pin text
  // separately in renderPinsSheetFrame (which stays outside the mirror).
  const transform = rot
    ? ` transform="translate(${fmt(p.x)} ${fmt(p.y)}) rotate(${fmt(-rot)})"`
    : ` transform="translate(${fmt(p.x)} ${fmt(p.y)})"`;
  return (
    `<g${transform}><text x="0" y="0" font-size="${fmt(size)}" ` +
    `text-anchor="${anchor}" dominant-baseline="${baseline}"${weight} ` +
    `fill="currentColor">${escapeText(text)}</text></g>`
  );
}

// Emits just the pin line in lib-math frame. Pin names and numbers are rendered
// separately in the sheet frame (see renderPinsSheetFrame) so they aren't
// affected by the symbol's mirror/rotation transform.
function renderPin(pin: PinDefinition): string {
  const pp = pin.at?.position;
  if (!pp) return '';
  const len = pin.length ?? 2.54;
  const rad = ((pin.at?.rotation ?? 0) * Math.PI) / 180;
  const x2 = pp.x + Math.cos(rad) * len;
  const y2 = pp.y + Math.sin(rad) * len;
  return (
    `<line x1="${fmt(pp.x)}" y1="${fmt(pp.y)}" x2="${fmt(x2)}" y2="${fmt(y2)}" ` +
    `stroke="currentColor" stroke-width="${fmt(LIB_W)}" stroke-linecap="round"/>`
  );
}

// ---------- hierarchical sheet blocks ----------

function sheetSymbolParts(sch: KicadSch): string[] {
  const out: string[] = [];
  for (const sh of sch.sheets as SchematicSheet[]) {
    const p = sh.at?.position;
    const sz = sh.size;
    if (!p || !sz) continue;
    const name = sh.sheetname ?? sh.get_property_text?.('Sheetname') ?? '';
    const file = sh.sheetfile ?? sh.get_property_text?.('Sheetfile') ?? '';
    const uuid = sh.uuid ?? '';
    const parts: string[] = [];
    parts.push(
      `<rect x="${fmt(p.x)}" y="${fmt(p.y)}" width="${fmt(sz.x)}" height="${fmt(sz.y)}" ` +
      `fill="none" stroke="currentColor" stroke-width="${fmt(0.3)}"/>`
    );
    if (name) {
      parts.push(
        `<text x="${fmt(p.x + 1)}" y="${fmt(p.y - 0.8)}" font-size="${fmt(1.8)}" ` +
        `fill="currentColor" font-weight="700">${escapeText(name)}</text>`
      );
    }
    if (file) {
      parts.push(
        `<text x="${fmt(p.x + 1)}" y="${fmt(p.y + sz.y + 2.2)}" font-size="${fmt(1.2)}" ` +
        `fill="currentColor" opacity="0.7">${escapeText(file)}</text>`
      );
    }
    // Sheet pins on this sheet block.
    for (const pin of (sh.pins ?? []) as SchematicSheetPin[]) {
      parts.push(renderSheetPin(pin));
    }
    out.push(
      `<g data-sheet-uuid="${escapeAttr(uuid)}" data-sheet-name="${escapeAttr(name)}" ` +
      `data-sheet-file="${escapeAttr(file)}">` +
      parts.join('') +
      `</g>`
    );
  }
  return out;
}

function renderSheetPin(pin: SchematicSheetPin): string {
  const p = pin.at?.position;
  if (!p) return '';
  const text = pin.name ?? '';
  const rot = pin.at?.rotation ?? 0;
  const size = pin.effects?.font?.size?.y ?? 1.27;
  const textW = text.length * size * 0.6;
  const h = size * 1.4;
  const tip = size * 0.55;
  const w = textW + size * 0.8 + tip;
  const pts = globalLabelPoints('input', w, h, tip)
    .map(([x, y]) => `${fmt(x)},${fmt(y)}`)
    .join(' ');
  return (
    `<g class="sch-sheet-pin" data-net="${escapeAttr(text)}" ` +
    `transform="translate(${fmt(p.x)} ${fmt(p.y)})${polyRotate(rot)}">` +
    `<polygon points="${pts}" fill="none" stroke="currentColor" stroke-width="${fmt(0.15)}"/>` +
    `<text x="${fmt(tip + size * 0.4)}" y="${fmt(size * 0.35)}" font-size="${fmt(size)}" ` +
    `text-anchor="start" fill="currentColor">${escapeText(text)}</text>` +
    `</g>`
  );
}

// ---------- shared helpers ----------

interface StrokeAttrs { stroke: string; sw: number; dash: string; }

function strokeAttrs(s: Stroke | undefined, defaultW: number): StrokeAttrs {
  const w = s?.width && s.width > 0 ? s.width : defaultW;
  let dash = '';
  switch (s?.type) {
    case 'dash': dash = ` stroke-dasharray="${fmt(w * 8)} ${fmt(w * 4)}"`; break;
    case 'dot': dash = ` stroke-dasharray="${fmt(w * 1.5)} ${fmt(w * 3)}"`; break;
    case 'dash_dot': dash = ` stroke-dasharray="${fmt(w * 8)} ${fmt(w * 4)} ${fmt(w * 1.5)} ${fmt(w * 4)}"`; break;
    case 'dash_dot_dot': dash = ` stroke-dasharray="${fmt(w * 8)} ${fmt(w * 4)} ${fmt(w * 1.5)} ${fmt(w * 4)} ${fmt(w * 1.5)} ${fmt(w * 4)}"`; break;
    default: break;
  }
  return { stroke: 'currentColor', sw: w, dash };
}

function fillAttr(d: unknown): string {
  const fillType = (d as { fill?: { type?: string } }).fill?.type;
  switch (fillType) {
    case 'background':
      return 'var(--kv-surface-2)';
    case 'outline':
      return 'currentColor';
    case 'color':
      return 'var(--kv-surface-2)';
    case 'none':
    default:
      return 'none';
  }
}

interface EffectsAttrs {
  size: number;
  weight: string;
  anchor: 'start' | 'middle' | 'end';
  baseline: string;
}

function effectsAttrs(e: Effects | undefined): EffectsAttrs {
  const size = e?.font?.size?.y ?? 1.27;
  const weight = e?.font?.bold ? ' font-weight="700"' : '';
  // KiCad justify: left/center/right + top/center/bottom; SVG equivalents:
  // left=start, right=end, center=middle; top=hanging, bottom=alphabetic, center=middle.
  const h = e?.justify?.horizontal ?? 'center';
  const v = e?.justify?.vertical ?? 'center';
  const anchor: 'start' | 'middle' | 'end' =
    h === 'left' ? 'start' : h === 'right' ? 'end' : 'middle';
  const baseline =
    v === 'top' ? 'hanging' : v === 'bottom' ? 'alphabetic' : 'middle';
  return { size, weight, anchor, baseline };
}

function arcPath(d: Arc, ySign: 1 | -1): string {
  const { start, mid, end } = d;
  const s = { x: start.x, y: start.y * ySign };
  const m = { x: mid.x, y: mid.y * ySign };
  const e = { x: end.x, y: end.y * ySign };

  // Compute circumscribing circle from three points.
  const ax = m.x - s.x;
  const ay = m.y - s.y;
  const bx = e.x - m.x;
  const by = e.y - m.y;
  const d1 = 2 * (ax * by - ay * bx);

  const { stroke, sw, dash } = strokeAttrs(d.stroke, LIB_W);
  const fill = fillAttr(d);

  if (Math.abs(d1) < 1e-9) {
    // Collinear — draw as line.
    return (
      `<path d="M ${fmt(s.x)} ${fmt(s.y)} L ${fmt(e.x)} ${fmt(e.y)}" ` +
      `fill="${fill}" stroke="${stroke}" stroke-width="${fmt(sw)}"${dash}/>`
    );
  }

  const sumSSq = s.x * s.x + s.y * s.y;
  const sumMSq = m.x * m.x + m.y * m.y;
  const sumESq = e.x * e.x + e.y * e.y;
  const cx = ((sumSSq - sumMSq) * by - (sumMSq - sumESq) * ay) / d1;
  const cy = ((sumMSq - sumSSq) * bx - (sumESq - sumMSq) * ax) / d1;
  const r = Math.hypot(s.x - cx, s.y - cy);

  // Determine sweep direction by sign of d1: positive cross means CCW in math
  // frame. In SVG (y-down), sweep-flag=1 means CCW in *screen* which is CW in
  // math. So:
  const sweep = d1 < 0 ? 1 : 0;

  // Determine large-arc flag: is `mid` on the minor arc from start→end? We
  // compare the angular position of mid vs the linear interpolation between
  // start and end on the circle.
  const a1 = Math.atan2(s.y - cy, s.x - cx);
  const a2 = Math.atan2(e.y - cy, e.x - cx);
  const am = Math.atan2(m.y - cy, m.x - cx);
  // Compute angular arc passing through `am`.
  const totalDelta = angSpan(a1, a2, am);
  const large = Math.abs(totalDelta) > Math.PI ? 1 : 0;

  return (
    `<path d="M ${fmt(s.x)} ${fmt(s.y)} A ${fmt(r)} ${fmt(r)} 0 ${large} ${sweep} ${fmt(e.x)} ${fmt(e.y)}" ` +
    `fill="${fill}" stroke="${stroke}" stroke-width="${fmt(sw)}"${dash}/>`
  );
}

function angSpan(a1: number, a2: number, through: number): number {
  // Signed angular distance from a1 to a2 passing through `through`.
  // Compute both possible deltas and pick the one whose midpoint is on the
  // `through` side.
  const twoPi = Math.PI * 2;
  const ccw = ((a2 - a1) % twoPi + twoPi) % twoPi;          // a1 → a2 CCW
  const cw = ccw - twoPi;                                    // a1 → a2 CW (negative)
  const midCCW = a1 + ccw / 2;
  // Compare distance from `through` to each candidate midpoint (modulo 2π).
  const dCCW = angularDistance(midCCW, through);
  const dCW = angularDistance(a1 + cw / 2, through);
  return dCCW <= dCW ? ccw : cw;
}

function angularDistance(a: number, b: number): number {
  const twoPi = Math.PI * 2;
  let d = Math.abs(a - b) % twoPi;
  if (d > Math.PI) d = twoPi - d;
  return d;
}

function fallbackSymbolBoxes(project: Project, sheet: Sheet): string[] {
  return project.components
    .filter((c) => c.sheetUuid === sheet.uuid)
    .map((c, i) => {
      const cx = (i % 8) * 30 + 20;
      const cy = Math.floor(i / 8) * 20 + 20;
      return (
        `<g data-refdes="${escapeAttr(c.refdes)}" data-uuid="${escapeAttr(c.uuid)}">` +
        `<rect x="${cx}" y="${cy}" width="20" height="10" fill="var(--kv-surface-2)" stroke="currentColor" stroke-width="0.25"/>` +
        `<text x="${cx + 10}" y="${cy + 6}" text-anchor="middle" font-size="4" fill="currentColor">${escapeText(c.refdes)}</text>` +
        `</g>`
      );
    });
}

function fmt(n: number): string {
  if (!isFinite(n)) return '0';
  const r = Math.round(n * 1000) / 1000;
  return r.toString();
}

function escapeAttr(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function escapeText(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Silence unused-var warnings for helpers exported only for types.
export type _InternalTitleBlockInfo = TitleBlockInfo;
