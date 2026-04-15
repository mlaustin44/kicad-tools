import { writable } from 'svelte/store';

export type SelectionSource = 'sch' | 'pcb' | '3d' | 'search';

export type Selection =
  | { kind: 'component'; uuid: string; source: SelectionSource }
  | { kind: 'net'; name: string; source: SelectionSource }
  | { kind: 'sheet'; uuid: string; source: SelectionSource }
  | { kind: 'track'; idx: number; source: SelectionSource }
  | { kind: 'zone'; idx: number; source: SelectionSource }
  | { kind: 'via'; idx: number; source: SelectionSource };

export const selection = writable<Selection | null>(null);

export function selectComponent(args: { uuid: string; source: SelectionSource }) {
  selection.set({ kind: 'component', uuid: args.uuid, source: args.source });
}
export function selectNet(args: { name: string; source: SelectionSource }) {
  selection.set({ kind: 'net', name: args.name, source: args.source });
}
export function selectSheet(args: { uuid: string; source: SelectionSource }) {
  selection.set({ kind: 'sheet', uuid: args.uuid, source: args.source });
}
export function selectTrack(args: { idx: number; source: SelectionSource }) {
  selection.set({ kind: 'track', idx: args.idx, source: args.source });
}
export function selectZone(args: { idx: number; source: SelectionSource }) {
  selection.set({ kind: 'zone', idx: args.idx, source: args.source });
}
export function selectVia(args: { idx: number; source: SelectionSource }) {
  selection.set({ kind: 'via', idx: args.idx, source: args.source });
}
export function clearSelection() {
  selection.set(null);
}
