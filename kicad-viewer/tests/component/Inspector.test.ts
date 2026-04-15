import { render } from '@testing-library/svelte';
import { describe, it, expect, beforeEach } from 'vitest';
import Inspector from '$lib/ui/Inspector.svelte';
import { selection, selectComponent } from '$lib/stores/selection';
import { project } from '$lib/stores/project';
import type { Project } from '$lib/model/project';

const fake: Project = {
  name: 'x', sheets: [], nets: [],
  pcb: { boundsMm: { x:0,y:0,w:0,h:0 }, layers: [], stackup: [], footprints: [], tracks: [], vias: [], zones: [], drills: [], boardGraphics: [] },
  source: 'raw',
  components: [{
    uuid: 'u1', refdes: 'R1', value: '10k', footprint: 'R_0603',
    sheetUuid: 's1', dnp: false, pins: [],
    mpn: 'ABC', manufacturer: 'Acme', datasheet: 'https://x'
  }]
};

describe('Inspector', () => {
  beforeEach(() => { project.set(fake); selection.set(null); });

  it('shows empty state when no selection', () => {
    const { getByText } = render(Inspector);
    expect(getByText(/Select/i)).toBeTruthy();
  });

  it('renders component details', () => {
    selectComponent({ uuid: 'u1', source: 'sch' });
    const { getByText } = render(Inspector);
    expect(getByText('R1')).toBeTruthy();
    expect(getByText('10k')).toBeTruthy();
    expect(getByText('Acme')).toBeTruthy();
  });
});
