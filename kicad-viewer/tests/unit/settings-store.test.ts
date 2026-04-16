import { describe, it, expect, beforeEach, vi } from 'vitest';
import { get } from 'svelte/store';

const STORAGE_KEY = 'kv.settings.v1';

async function loadFreshModule() {
  vi.resetModules();
  return import('$lib/stores/settings');
}

describe('settings store', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('defaults to inactiveLayerOpacity 0.3 when no stored value', async () => {
    const mod = await loadFreshModule();
    expect(get(mod.settings).inactiveLayerOpacity).toBe(0.3);
  });

  it('persists changes to localStorage', async () => {
    const mod = await loadFreshModule();
    mod.settings.update((s) => ({ ...s, inactiveLayerOpacity: 0.5 }));
    const raw = localStorage.getItem(STORAGE_KEY);
    expect(raw).toBeTruthy();
    expect(JSON.parse(raw!).inactiveLayerOpacity).toBe(0.5);
  });

  it('hydrates from localStorage on load', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ inactiveLayerOpacity: 0.7 }));
    const mod = await loadFreshModule();
    expect(get(mod.settings).inactiveLayerOpacity).toBe(0.7);
  });

  it('merges stored partial settings with defaults', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({}));
    const mod = await loadFreshModule();
    expect(get(mod.settings).inactiveLayerOpacity).toBe(0.3);
  });

  it('falls back to defaults on invalid JSON', async () => {
    localStorage.setItem(STORAGE_KEY, '{not-json');
    const mod = await loadFreshModule();
    expect(get(mod.settings).inactiveLayerOpacity).toBe(0.3);
  });
});
