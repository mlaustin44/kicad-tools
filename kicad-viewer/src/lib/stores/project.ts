import { writable, derived } from 'svelte/store';
import type { Project, Component, Net, Sheet } from '$lib/model/project';

export const project = writable<Project | null>(null);

export function setProjectGlbUrl(url: string | null): void {
  project.update((p) => {
    if (!p) return p;
    if (p.glbUrl && p.glbUrl.startsWith('blob:')) URL.revokeObjectURL(p.glbUrl);
    if (url === null) {
      // Return a new object without the glbUrl field to respect exactOptionalPropertyTypes.
      const { glbUrl: _drop, ...rest } = p;
      return rest as typeof p;
    }
    return { ...p, glbUrl: url };
  });
}

export function setProjectRevokingGlb(next: Project | null): void {
  project.update((p) => {
    if (p?.glbUrl && p.glbUrl.startsWith('blob:')) {
      if (!next || next.glbUrl !== p.glbUrl) URL.revokeObjectURL(p.glbUrl);
    }
    return next;
  });
}

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
