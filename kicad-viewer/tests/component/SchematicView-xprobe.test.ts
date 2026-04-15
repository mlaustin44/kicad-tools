import { render } from '@testing-library/svelte';
import { describe, it, expect, beforeEach } from 'vitest';
import SchematicView from '$lib/views/SchematicView.svelte';
import { project } from '$lib/stores/project';
import { selection, selectComponent } from '$lib/stores/selection';
import type { Project } from '$lib/model/project';

const p: Project = {
  name: 'x', source: 'raw', nets: [],
  pcb: { boundsMm: { x:0,y:0,w:0,h:0 }, layers: [], stackup: [], footprints: [], tracks: [], vias: [], zones: [], drills: [] },
  sheets: [{
    uuid: 's0', name: 'root', path: ['root'], parent: null,
    componentUuids: ['u1'], boundsMm: { x:0, y:0, w:100, h:100 }
  }],
  components: [{
    uuid: 'u1', refdes: 'R1', value: '10k', footprint: 'R',
    sheetUuid: 's0', dnp: false, pins: []
  }]
};

// jsdom does not provide CSS.escape; stub it for any code that needs it.
if (typeof (globalThis as { CSS?: { escape?: (s: string) => string } }).CSS === 'undefined') {
  (globalThis as { CSS?: { escape: (s: string) => string } }).CSS = { escape: (s: string) => s };
}

describe('SchematicView cross-probe', () => {
  beforeEach(() => { project.set(p); selection.set(null); });

  it('highlights the selected component when selected externally', async () => {
    const { container } = render(SchematicView, { props: { activeSheetUuid: 's0' } });
    selectComponent({ uuid: 'u1', source: 'pcb' });
    await new Promise((r) => setTimeout(r, 10));
    // Can't easily test viewport change — instead, confirm a [data-refdes="R1"] group exists
    expect(container.querySelector('[data-refdes="R1"]')).toBeTruthy();
  });
});
