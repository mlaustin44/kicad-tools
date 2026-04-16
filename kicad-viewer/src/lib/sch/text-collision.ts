/**
 * Best-effort post-render pass that nudges schematic text elements away from
 * symbol bodies they overlap. Runs on the real DOM so text measurement is
 * accurate. Capped at a small number of iterations to avoid layout thrash.
 */

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

function domRectToRect(r: DOMRect): Rect {
  return { x: r.x, y: r.y, w: r.width, h: r.height };
}

function rectsOverlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

function overlapArea(a: Rect, b: Rect): number {
  const ox = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x));
  const oy = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
  return ox * oy;
}

function totalOverlap(textRect: Rect, obstacles: Rect[]): number {
  let sum = 0;
  for (const obs of obstacles) sum += overlapArea(textRect, obs);
  return sum;
}

/**
 * Run collision resolution on all <text> elements inside a schematic SVG.
 * Call from requestAnimationFrame after Svelte commits the {@html svg}.
 */
export function resolveTextOverlaps(svgContainer: HTMLElement): void {
  const svgEl = svgContainer.querySelector('svg');
  if (!svgEl) return;

  // Build per-symbol obstacle sets keyed by refdes so we can skip
  // self-collisions (a component's text naturally sits near its own body).
  interface TaggedRect extends Rect { refdes: string | null }
  const obstacles: TaggedRect[] = [];
  for (const el of svgEl.querySelectorAll(
    '[data-refdes] rect, [data-refdes] polygon, [data-refdes] circle, [data-refdes] polyline'
  )) {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;
    const refdes = el.closest('[data-refdes]')?.getAttribute('data-refdes') ?? null;
    obstacles.push({ ...domRectToRect(r), refdes });
  }

  if (obstacles.length === 0) return;

  // Candidate text elements: component properties and net labels.
  const texts = svgEl.querySelectorAll(
    '[data-refdes] > text, text[data-net], .sch-label text'
  );

  const NUDGE_PX = 3;
  const MAX_ITER = 4;
  const DIRECTIONS: Array<[number, number]> = [
    [0, -1], [0, 1], [-1, 0], [1, 0]
  ];

  for (const textEl of texts) {
    const el = textEl as SVGTextElement;
    let textRect = domRectToRect(el.getBoundingClientRect());
    if (textRect.w === 0 || textRect.h === 0) continue;

    // The text's own parent refdes — skip collisions with this symbol.
    const ownRefdes = el.closest('[data-refdes]')?.getAttribute('data-refdes') ?? null;
    const foreign = obstacles.filter((o) => o.refdes !== ownRefdes || o.refdes === null);
    if (foreign.length === 0) continue;

    let overlap = totalOverlap(textRect, foreign);
    if (overlap === 0) continue;

    let appliedDx = 0;
    let appliedDy = 0;
    for (let iter = 0; iter < MAX_ITER && overlap > 0; iter++) {
      let bestDir: [number, number] = [0, 0];
      let bestOverlap = overlap;
      for (const [dx, dy] of DIRECTIONS) {
        const candidate: Rect = {
          x: textRect.x + dx * NUDGE_PX,
          y: textRect.y + dy * NUDGE_PX,
          w: textRect.w,
          h: textRect.h
        };
        const ov = totalOverlap(candidate, foreign);
        if (ov < bestOverlap) {
          bestOverlap = ov;
          bestDir = [dx, dy];
        }
      }
      if (bestDir[0] === 0 && bestDir[1] === 0) break;
      appliedDx += bestDir[0] * NUDGE_PX;
      appliedDy += bestDir[1] * NUDGE_PX;
      textRect = {
        x: textRect.x + bestDir[0] * NUDGE_PX,
        y: textRect.y + bestDir[1] * NUDGE_PX,
        w: textRect.w,
        h: textRect.h
      };
      overlap = bestOverlap;
    }

    if (appliedDx !== 0 || appliedDy !== 0) {
      const ctm = (svgEl as unknown as SVGSVGElement).getScreenCTM?.();
      const scale = ctm ? ctm.a : 1;
      const svgDx = appliedDx / scale;
      const svgDy = appliedDy / scale;
      const curX = parseFloat(el.getAttribute('x') ?? '0');
      const curY = parseFloat(el.getAttribute('y') ?? '0');
      el.setAttribute('x', String(curX + svgDx));
      el.setAttribute('y', String(curY + svgDy));
    }
  }
}
