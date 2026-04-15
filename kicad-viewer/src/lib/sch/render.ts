import type { Project, Sheet } from '$lib/model/project';

export function buildSheetSvg(project: Project, sheet: Sheet): string {
  const { x, y, w, h } = sheet.boundsMm;
  const parts = project.components
    .filter((c) => c.sheetUuid === sheet.uuid)
    .map((c, i) => {
      const cx = (i % 8) * 30 + 20;
      const cy = Math.floor(i / 8) * 20 + 20;
      return `<g data-refdes="${escapeAttr(c.refdes)}" data-uuid="${escapeAttr(c.uuid)}">` +
        `<rect x="${cx}" y="${cy}" width="20" height="10" fill="var(--kv-surface-2)" stroke="currentColor" stroke-width="0.25"/>` +
        `<text x="${cx + 10}" y="${cy + 6}" text-anchor="middle" font-size="4" fill="currentColor">${escapeText(c.refdes)}</text>` +
        `</g>`;
    }).join('');
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${x} ${y} ${w} ${h}" preserveAspectRatio="xMidYMid meet" style="color: var(--kv-text); width: 100%; height: 100%">${parts}</svg>`;
}

function escapeAttr(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function escapeText(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
