import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { project } from '$lib/stores/project';
import { activeLayer } from '$lib/stores/layers';
import type { Project } from '$lib/model/project';

function fakeProject(layerIds: string[]): Project {
  return {
    name: 'fake',
    source: 'raw',
    sheets: [],
    components: [],
    nets: [],
    pcb: {
      layers: layerIds.map((id) => ({
        id,
        name: id,
        type: id.endsWith('.Cu') && id !== 'F.Cu' && id !== 'B.Cu' ? 'In.Cu' : id,
        defaultColor: '#888'
      })) as unknown as Project['pcb']['layers'],
      footprints: [],
      tracks: [],
      vias: [],
      zones: [],
      graphics: [],
      boundsMm: { x: 0, y: 0, w: 1, h: 1 }
    }
  } as unknown as Project;
}

describe('activeLayer store', () => {
  beforeEach(() => project.set(null));

  it('is F.Cu when project has F.Cu', () => {
    project.set(fakeProject(['F.Cu', 'B.Cu']));
    expect(get(activeLayer)).toBe('F.Cu');
  });

  it('falls back to first copper when no F.Cu', () => {
    project.set(fakeProject(['B.Cu']));
    expect(get(activeLayer)).toBe('B.Cu');
  });

  it('can be set manually', () => {
    project.set(fakeProject(['F.Cu', 'B.Cu']));
    activeLayer.set('B.Cu');
    expect(get(activeLayer)).toBe('B.Cu');
  });

  it('resets to F.Cu on new project load', () => {
    project.set(fakeProject(['F.Cu', 'B.Cu']));
    activeLayer.set('B.Cu');
    project.set(fakeProject(['F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu']));
    expect(get(activeLayer)).toBe('F.Cu');
  });
});
