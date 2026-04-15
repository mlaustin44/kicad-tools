import { writable } from 'svelte/store';

export type LeftSidebarTab = 0 | 1 | 2; // first-tab (Pages/Layers), Nets, Components

const LS_KEY = 'kv.leftsidebar.tab.v1';

function load(): LeftSidebarTab {
  if (typeof localStorage === 'undefined') return 0;
  try {
    const n = parseInt(localStorage.getItem(LS_KEY) ?? '0', 10);
    return n === 0 || n === 1 || n === 2 ? (n as LeftSidebarTab) : 0;
  } catch {
    return 0;
  }
}

export const leftSidebarTab = writable<LeftSidebarTab>(load());

leftSidebarTab.subscribe((t) => {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(LS_KEY, String(t));
  } catch {
    // ignore
  }
});
