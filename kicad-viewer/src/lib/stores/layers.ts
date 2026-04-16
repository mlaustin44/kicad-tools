import { writable, derived } from 'svelte/store';
import { project } from '$lib/stores/project';

export const layerVisibility = writable<Map<string, boolean>>(new Map());
export const activeLayer = writable<string>('F.Cu');

// Seed visibility and active layer each time project changes.
project.subscribe((p) => {
  if (!p) {
    layerVisibility.set(new Map());
    activeLayer.set('F.Cu');
    return;
  }
  const m = new Map<string, boolean>();
  for (const l of p.pcb.layers) {
    const on = ['F.Cu', 'B.Cu', 'In.Cu', 'F.SilkS', 'B.SilkS', 'F.Mask', 'B.Mask', 'Edge.Cuts'].includes(l.type);
    m.set(l.id, on);
  }
  layerVisibility.set(m);

  const hasFCu = p.pcb.layers.some((l) => l.id === 'F.Cu');
  if (hasFCu) {
    activeLayer.set('F.Cu');
  } else {
    const firstCu = p.pcb.layers.find((l) => l.id.endsWith('.Cu'));
    activeLayer.set(firstCu?.id ?? 'F.Cu');
  }
});

export const layers = derived(project, (p) => p?.pcb.layers ?? []);

export function toggleLayer(id: string) {
  layerVisibility.update((m) => {
    const next = new Map(m);
    next.set(id, !next.get(id));
    return next;
  });
}

export function setActiveLayer(id: string) {
  activeLayer.set(id);
}
