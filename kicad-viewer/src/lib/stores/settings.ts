import { writable } from 'svelte/store';

export interface Settings {
  inactiveLayerOpacity: number;
}

const DEFAULTS: Settings = { inactiveLayerOpacity: 0.3 };
const STORAGE_KEY = 'kv.settings.v1';

function load(): Settings {
  if (typeof localStorage === 'undefined') return DEFAULTS;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw);
    return { ...DEFAULTS, ...parsed };
  } catch {
    return DEFAULTS;
  }
}

export const settings = writable<Settings>(load());

settings.subscribe((s) => {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    // Storage quota / disabled — silently ignore.
  }
});
