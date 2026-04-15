import type { LayerInfo } from '$lib/model/project';

export type LayerSide = 'front' | 'back' | 'board';

const BOARD_PREFIXES = ['Edge.', 'User.', 'Dwgs.', 'Cmts.', 'Eco1.', 'Eco2.'];
const BOARD_EXACT = new Set(['Margin']);

export function classifyLayer(layerId: string, allLayers: LayerInfo[]): LayerSide {
  if (/^In\d+\.Cu$/.test(layerId)) return innerCopperSide(layerId, allLayers);
  if (layerId === 'F.Cu' || layerId.startsWith('F.')) return 'front';
  if (layerId === 'B.Cu' || layerId.startsWith('B.')) return 'back';
  if (BOARD_EXACT.has(layerId)) return 'board';
  for (const p of BOARD_PREFIXES) if (layerId.startsWith(p)) return 'board';
  return 'board';
}

export function innerCopperSide(layerId: string, allLayers: LayerInfo[]): LayerSide {
  const match = /^In(\d+)\.Cu$/.exec(layerId);
  if (!match) return 'board';
  const n = Number(match[1]);
  const inners = allLayers
    .filter((l) => /^In\d+\.Cu$/.test(l.id))
    .map((l) => Number(/^In(\d+)\.Cu$/.exec(l.id)![1]))
    .sort((a, b) => a - b);
  if (inners.length === 0) return 'front';
  const halfCutoff = Math.ceil(inners.length / 2);
  const idxOneBased = inners.indexOf(n) + 1;
  return idxOneBased <= halfCutoff ? 'front' : 'back';
}
