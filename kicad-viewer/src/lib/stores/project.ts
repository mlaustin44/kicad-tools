import { writable, derived } from 'svelte/store';
import type { Project, Component, Net, Sheet } from '$lib/model/project';

export const project = writable<Project | null>(null);

// Setting either GLB or STEP replaces the other — only one 3D asset is
// displayed at a time, and we revoke any replaced blob: URL so memory for
// large STEP/GLB files is actually freed.
function revokeIfBlob(url: string | undefined): void {
  if (url && url.startsWith('blob:')) URL.revokeObjectURL(url);
}

export function setProjectGlbUrl(url: string | null): void {
  project.update((p) => {
    if (!p) return p;
    revokeIfBlob(p.glbUrl);
    revokeIfBlob(p.stepUrl);
    const { glbUrl: _g, stepUrl: _s, ...rest } = p;
    if (url === null) return rest as typeof p;
    return { ...rest, glbUrl: url } as typeof p;
  });
}

export function setProjectStepUrl(url: string | null): void {
  project.update((p) => {
    if (!p) return p;
    revokeIfBlob(p.glbUrl);
    revokeIfBlob(p.stepUrl);
    const { glbUrl: _g, stepUrl: _s, ...rest } = p;
    if (url === null) return rest as typeof p;
    return { ...rest, stepUrl: url } as typeof p;
  });
}

export function setProjectRevokingGlb(next: Project | null): void {
  project.update((p) => {
    if (p?.glbUrl && p.glbUrl.startsWith('blob:')) {
      if (!next || next.glbUrl !== p.glbUrl) URL.revokeObjectURL(p.glbUrl);
    }
    if (p?.stepUrl && p.stepUrl.startsWith('blob:')) {
      if (!next || next.stepUrl !== p.stepUrl) URL.revokeObjectURL(p.stepUrl);
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
