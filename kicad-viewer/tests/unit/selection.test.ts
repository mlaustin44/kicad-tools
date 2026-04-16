import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import {
  selection, selectComponent, selectNet, selectSheet, clearSelection,
  type Selection
} from '$lib/stores/selection';

describe('selection store', () => {
  beforeEach(() => clearSelection());

  it('starts empty', () => {
    expect(get(selection)).toBeNull();
  });

  it('selects a component', () => {
    selectComponent({ uuid: 'u1', source: 'sch' });
    const s = get(selection)!;
    expect(s.kind).toBe('component');
    if (s.kind === 'component') expect(s.uuid).toBe('u1');
    expect(s.source).toBe('sch');
  });

  it('selecting the same component with a new source updates the source', () => {
    selectComponent({ uuid: 'u1', source: 'sch' });
    selectComponent({ uuid: 'u1', source: 'pcb' });
    expect(get(selection)!.source).toBe('pcb');
  });

  it('clears selection', () => {
    selectComponent({ uuid: 'u1', source: 'sch' });
    clearSelection();
    expect(get(selection)).toBeNull();
  });

  it('net selection has no uuid, has name', () => {
    selectNet({ name: 'VCC', source: 'pcb' });
    const s = get(selection)!;
    expect(s.kind).toBe('net');
    if (s.kind === 'net') expect(s.name).toBe('VCC');
  });

  it('sheet selection carries uuid', () => {
    selectSheet({ uuid: 'sheet-0', source: 'search' });
    expect(get(selection)!.kind).toBe('sheet');
  });
});
