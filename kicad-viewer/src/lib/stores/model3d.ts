import { writable } from 'svelte/store';

// Status of the current 3D-model load pipeline. Kept in a top-level store so
// long STEP parses (tens of seconds for real boards) survive ThreeDView
// unmounts: the load continues in the worker, the store updates when it
// completes, and the viewer can surface a corner notification inviting the
// user back to the 3D tab.

export type Model3dStatus =
  | { kind: 'idle' }
  | { kind: 'loading'; url: string; startedAt: number }
  | { kind: 'ready'; url: string; completedAt: number; acknowledged: boolean }
  | { kind: 'error'; url: string; message: string };

export const model3dStatus = writable<Model3dStatus>({ kind: 'idle' });

export function markLoading(url: string): void {
  model3dStatus.set({ kind: 'loading', url, startedAt: Date.now() });
}
export function markReady(url: string): void {
  model3dStatus.set({
    kind: 'ready',
    url,
    completedAt: Date.now(),
    acknowledged: false
  });
}
export function markError(url: string, message: string): void {
  model3dStatus.set({ kind: 'error', url, message });
}
export function acknowledgeReady(): void {
  model3dStatus.update((s) =>
    s.kind === 'ready' ? { ...s, acknowledged: true } : s
  );
}
