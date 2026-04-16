import { writable } from 'svelte/store';

export type Toast = { id: number; kind: 'error' | 'info' | 'success'; message: string; };

export const toasts = writable<Toast[]>([]);

let nextId = 1;
export function pushToast(t: Omit<Toast, 'id'>) {
  toasts.update((l) => [...l, { id: nextId++, ...t }]);
}
export function dismissToast(id: number) {
  toasts.update((l) => l.filter((t) => t.id !== id));
}
