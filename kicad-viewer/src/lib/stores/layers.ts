import { writable, derived } from 'svelte/store';
import { project } from '$lib/stores/project';

export const layerVisibility = writable<Map<string, boolean>>(new Map());

// Seed visibility map each time project changes
project.subscribe((p) => {
  if (!p) { layerVisibility.set(new Map()); return; }
  const m = new Map<string, boolean>();
  for (const l of p.pcb.layers) {
    const on = ['F.Cu', 'B.Cu', 'In.Cu', 'F.SilkS', 'B.SilkS', 'F.Mask', 'B.Mask', 'Edge.Cuts'].includes(l.type);
    m.set(l.id, on);
  }
  layerVisibility.set(m);
});

export const layers = derived(project, (p) => p?.pcb.layers ?? []);

export function toggleLayer(id: string) {
  layerVisibility.update((m) => {
    const next = new Map(m);
    next.set(id, !next.get(id));
    return next;
  });
}
