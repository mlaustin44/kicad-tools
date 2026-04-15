import { writable, derived } from 'svelte/store';
import type { Project, Component, Net, Sheet } from '$lib/model/project';

export const project = writable<Project | null>(null);

export const componentsByUuid = derived(project, (p) => {
  const m = new Map<string, Component>();
  if (p) for (const c of p.components) m.set(c.uuid, c);
  return m;
});

export const componentsByRefdes = derived(project, (p) => {
  const m = new Map<string, Component>();
  if (p) for (const c of p.components) m.set(c.refdes, c);
  return m;
});

export const sheetsByUuid = derived(project, (p) => {
  const m = new Map<string, Sheet>();
  if (p) for (const s of p.sheets) m.set(s.uuid, s);
  return m;
});

export const netsByName = derived(project, (p) => {
  const m = new Map<string, Net>();
  if (p) for (const n of p.nets) m.set(n.name, n);
  return m;
});
