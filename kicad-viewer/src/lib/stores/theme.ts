import { writable, get } from 'svelte/store';

export type Theme = 'light' | 'dark';

const KEY = 'kv.theme';

function initial(): Theme {
  if (typeof localStorage === 'undefined') return 'light';
  const v = localStorage.getItem(KEY);
  return v === 'dark' ? 'dark' : 'light';
}

export const theme = writable<Theme>(initial());

theme.subscribe((v) => {
  if (typeof localStorage !== 'undefined') localStorage.setItem(KEY, v);
  if (typeof document !== 'undefined') document.body.setAttribute('data-theme', v);
});

export function toggleTheme() {
  theme.set(get(theme) === 'dark' ? 'light' : 'dark');
}
