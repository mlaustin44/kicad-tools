import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { theme, toggleTheme } from '$lib/stores/theme';

describe('theme store', () => {
  beforeEach(() => {
    localStorage.clear();
    theme.set('light');
  });

  it('defaults to light when no stored preference', () => {
    expect(get(theme)).toBe('light');
  });

  it('toggles dark <-> light', () => {
    theme.set('light');
    toggleTheme();
    expect(get(theme)).toBe('dark');
    toggleTheme();
    expect(get(theme)).toBe('light');
  });

  it('persists to localStorage', () => {
    theme.set('dark');
    expect(localStorage.getItem('kv.theme')).toBe('dark');
  });
});
