import type { LayerInfo } from '$lib/model/project';
import { classifyLayer, type LayerSide } from './layer-side';

const NONCOPPER_ORDER = [
  'Mask',
  'Paste',
  'SilkS',
  'Fab',
  'CrtYd',
  'Adhesive',
  'Adhes'
] as const;

function nonCopperIdsForSide(layers: LayerInfo[], side: 'front' | 'back'): string[] {
  const prefix = side === 'front' ? 'F.' : 'B.';
  const ids: string[] = [];
  for (const kind of NONCOPPER_ORDER) {
    const id = prefix + kind;
    if (layers.some((l) => l.id === id)) ids.push(id);
  }
  return ids;
}

function copperIds(layers: LayerInfo[]): string[] {
  return layers.filter((l) => l.id.endsWith('.Cu')).map((l) => l.id);
}

export function computeDrawOrder(layers: LayerInfo[], activeLayerId: string): LayerInfo[] {
  const byId = new Map(layers.map((l) => [l.id, l]));
  const activeSide: 'front' | 'back' = (() => {
    const s: LayerSide = classifyLayer(activeLayerId, layers);
    return s === 'back' ? 'back' : 'front';
  })();
  const inactiveSide: 'front' | 'back' = activeSide === 'front' ? 'back' : 'front';

  const result: string[] = [];
  const push = (id: string) => {
    if (byId.has(id) && !result.includes(id)) result.push(id);
  };

  // 1. Inactive-side non-copper
  for (const id of nonCopperIdsForSide(layers, inactiveSide)) push(id);

  // 2. Inactive-side copper: outer + any inner copper on that side.
  const allCu = copperIds(layers);
  const inactiveOuterCu = inactiveSide === 'front' ? 'F.Cu' : 'B.Cu';
  push(inactiveOuterCu);
  for (const id of allCu) {
    if (id === 'F.Cu' || id === 'B.Cu') continue;
    if (classifyLayer(id, layers) === inactiveSide) push(id);
  }

  // 3. Active-side non-copper
  for (const id of nonCopperIdsForSide(layers, activeSide)) push(id);

  // 4. Non-active copper on the active side (below the focal copper).
  const activeOuterCu = activeSide === 'front' ? 'F.Cu' : 'B.Cu';
  if (activeOuterCu !== activeLayerId) push(activeOuterCu);
  for (const id of allCu) {
    if (id === 'F.Cu' || id === 'B.Cu' || id === activeLayerId) continue;
    if (classifyLayer(id, layers) === activeSide) push(id);
  }

  // 5. Active copper
  push(activeLayerId);

  // 6. Board-wide: everything classified as 'board'. Edge.Cuts always last.
  const boardIds = layers
    .filter((l) => classifyLayer(l.id, layers) === 'board')
    .map((l) => l.id);
  for (const id of boardIds) {
    if (id !== 'Edge.Cuts') push(id);
  }
  push('Edge.Cuts');

  return result.map((id) => byId.get(id)!).filter(Boolean);
}
