import type { Project, Sheet } from '$lib/model/project';
import {
  KicadSch,
  type Wire,
  type Junction,
  type NetLabel,
  type GlobalLabel,
  type HierarchicalLabel,
  type SchematicSymbol,
  type SchematicSheet,
  Rectangle,
  Polyline,
  Circle,
  Arc,
  type LibSymbol,
  type PinDefinition
} from '$lib/parser/schematic';

export function buildSheetSvg(project: Project, sheet: Sheet): string {
  const { x, y, w, h } = sheet.boundsMm;
  const parts: string[] = [];

  if (sheet.rawSch) {
    try {
      const sch = new KicadSch(sheet.name, sheet.rawSch);
      parts.push(...wireParts(sch));
      parts.push(...junctionParts(sch));
      parts.push(...labelParts(sch));
      parts.push(...sheetSymbolParts(sch));
      parts.push(...symbolParts(sch));
    } catch {
      parts.push(...fallbackSymbolBoxes(project, sheet));
    }
  } else {
    parts.push(...fallbackSymbolBoxes(project, sheet));
  }

  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${x} ${y} ${w} ${h}" ` +
    `preserveAspectRatio="xMidYMid meet" style="color: var(--kv-text); width: 100%; height: 100%">` +
    parts.join('') +
    `</svg>`
  );
}

// --- helpers ---

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
          `stroke="currentColor" stroke-width="0.15" stroke-linecap="round"/>`
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
    const r = j.diameter && j.diameter > 0 ? j.diameter / 2 : 0.45;
    out.push(
      `<circle cx="${fmt(p.x)}" cy="${fmt(p.y)}" r="${fmt(r)}" fill="currentColor"/>`
    );
  }
  return out;
}

function labelParts(sch: KicadSch): string[] {
  const out: string[] = [];
  const allLabels: Array<NetLabel | GlobalLabel | HierarchicalLabel> = [
    ...(sch.net_labels ?? []),
    ...(sch.global_labels ?? []),
    ...(sch.hierarchical_labels ?? [])
  ];
  for (const lbl of allLabels) {
    const p = lbl.at?.position;
    if (!p) continue;
    const text = lbl.text ?? '';
    if (!text) continue;
    const rot = lbl.at?.rotation ?? 0;
    // KiCad label rotation is counter-clockwise in the schematic; SVG y is inverted
    // vs KiCad's on-screen coordinates but both use the same mm layout, so we keep
    // rotation as-is and accept the minor orientation mismatch.
    const transform = rot ? ` transform="rotate(${-rot} ${fmt(p.x)} ${fmt(p.y)})"` : '';
    out.push(
      `<text x="${fmt(p.x)}" y="${fmt(p.y)}" font-size="1.27" ` +
        `fill="currentColor"${transform}>${escapeText(text)}</text>`
    );
  }
  return out;
}

function sheetSymbolParts(sch: KicadSch): string[] {
  const out: string[] = [];
  for (const sh of sch.sheets as SchematicSheet[]) {
    const p = sh.at?.position;
    const sz = sh.size;
    if (!p || !sz) continue;
    const name = sh.sheetname ?? sh.get_property_text?.('Sheetname') ?? '';
    const file = sh.sheetfile ?? sh.get_property_text?.('Sheetfile') ?? '';
    const uuid = sh.uuid ?? '';
    out.push(
      `<g data-sheet-uuid="${escapeAttr(uuid)}" data-sheet-name="${escapeAttr(name)}" ` +
        `data-sheet-file="${escapeAttr(file)}">` +
        `<rect x="${fmt(p.x)}" y="${fmt(p.y)}" width="${fmt(sz.x)}" height="${fmt(sz.y)}" ` +
        `fill="var(--kv-surface-2)" fill-opacity="0.35" stroke="currentColor" stroke-width="0.3"/>` +
        `<text x="${fmt(p.x + 1)}" y="${fmt(p.y - 0.5)}" font-size="1.8" fill="currentColor">` +
        escapeText(name) +
        `</text>` +
        (file
          ? `<text x="${fmt(p.x + 1)}" y="${fmt(p.y + sz.y + 2.2)}" ` +
            `font-size="1.2" fill="currentColor" opacity="0.7">${escapeText(file)}</text>`
          : '') +
        `</g>`
    );
  }
  return out;
}

function symbolParts(sch: KicadSch): string[] {
  const out: string[] = [];
  for (const sym of sch.symbols.values() as IterableIterator<SchematicSymbol>) {
    if (!sym) continue;
    const refdes = sym.reference || '?';
    if (refdes.startsWith('#')) continue; // power symbols
    const uuid = sym.uuid ?? `${refdes}`;
    const p = sym.at?.position;
    if (!p) continue;
    const rot = sym.at?.rotation ?? 0;

    const inner: string[] = [];
    let hasGraphics = false;

    // Try to render the library symbol's graphics.
    let lib: LibSymbol | undefined;
    try {
      lib = sym.lib_symbol;
    } catch {
      lib = undefined;
    }
    if (lib) {
      const graphicSvg = renderLibSymbol(lib);
      if (graphicSvg) {
        inner.push(graphicSvg);
        hasGraphics = true;
      }
    }

    if (!hasGraphics) {
      // Fallback: 10x6mm box centered on position with refdes+value inside.
      inner.push(
        `<rect x="-5" y="-3" width="10" height="6" fill="var(--kv-surface-2)" ` +
          `stroke="currentColor" stroke-width="0.2"/>`
      );
    }

    // Always draw refdes + value labels near the symbol origin.
    const value = sym.value || '';
    inner.push(
      `<g transform="rotate(${-rot})">` +
        `<text x="0" y="-4" text-anchor="middle" font-size="1.4" fill="currentColor">` +
        escapeText(refdes) +
        `</text>` +
        (value
          ? `<text x="0" y="5.5" text-anchor="middle" font-size="1.2" fill="currentColor" opacity="0.75">${escapeText(value)}</text>`
          : '') +
        `</g>`
    );

    out.push(
      `<g data-refdes="${escapeAttr(refdes)}" data-uuid="${escapeAttr(uuid)}" ` +
        `transform="translate(${fmt(p.x)} ${fmt(p.y)}) rotate(${fmt(-rot)})">` +
        inner.join('') +
        `</g>`
    );
  }
  return out;
}

function renderLibSymbol(lib: LibSymbol): string {
  const parts: string[] = [];
  // Combine drawings from lib and all unit children (KiCad splits multi-unit
  // symbol graphics across child LibSymbols keyed by unit number).
  const drawings = [...lib.drawings];
  const pins = [...lib.pins];
  for (const child of lib.children ?? []) {
    drawings.push(...child.drawings);
    pins.push(...child.pins);
  }

  for (const d of drawings) {
    if (d instanceof Rectangle) {
      const x = Math.min(d.start.x, d.end.x);
      const y = Math.min(d.start.y, d.end.y);
      const w = Math.abs(d.end.x - d.start.x);
      const h = Math.abs(d.end.y - d.start.y);
      parts.push(
        `<rect x="${fmt(x)}" y="${fmt(-y - h)}" width="${fmt(w)}" height="${fmt(h)}" ` +
          `fill="var(--kv-surface-2)" fill-opacity="0.25" stroke="currentColor" stroke-width="0.15"/>`
      );
    } else if (d instanceof Polyline) {
      const pts = (d.pts ?? [])
        .map((pt) => `${fmt(pt.x)},${fmt(-pt.y)}`)
        .join(' ');
      if (pts) {
        parts.push(
          `<polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="0.15"/>`
        );
      }
    } else if (d instanceof Circle) {
      parts.push(
        `<circle cx="${fmt(d.center.x)}" cy="${fmt(-d.center.y)}" r="${fmt(d.radius)}" ` +
          `fill="none" stroke="currentColor" stroke-width="0.15"/>`
      );
    } else if (d instanceof Arc) {
      // Approximate with a straight chord from start to end; good enough for a skeleton.
      parts.push(
        `<line x1="${fmt(d.start.x)}" y1="${fmt(-d.start.y)}" x2="${fmt(d.end.x)}" y2="${fmt(-d.end.y)}" ` +
          `stroke="currentColor" stroke-width="0.15"/>`
      );
    }
  }

  for (const pin of pins as PinDefinition[]) {
    if (pin.hide) continue;
    const pp = pin.at?.position;
    if (!pp) continue;
    const len = pin.length ?? 2.54;
    const rot = pin.at?.rotation ?? 0;
    const rad = (rot * Math.PI) / 180;
    const dx = Math.cos(rad) * len;
    const dy = Math.sin(rad) * len;
    // Flip Y for SVG.
    const x1 = pp.x;
    const y1 = -pp.y;
    const x2 = pp.x + dx;
    const y2 = -(pp.y + dy);
    parts.push(
      `<line x1="${fmt(x1)}" y1="${fmt(y1)}" x2="${fmt(x2)}" y2="${fmt(y2)}" ` +
        `stroke="currentColor" stroke-width="0.15"/>`
    );
  }

  return parts.join('');
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
  // Keep numbers readable and deterministic. KiCad uses up to 4 decimal places in files.
  if (!isFinite(n)) return '0';
  const r = Math.round(n * 1000) / 1000;
  return Number.isInteger(r) ? r.toString() : r.toString();
}

function escapeAttr(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function escapeText(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
