import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { toasts, pushToast, dismissToast } from '$lib/stores/toasts';

describe('toasts', () => {
  beforeEach(() => toasts.set([]));
  it('pushes a toast with monotonic ids', () => {
    pushToast({ kind: 'error', message: 'a' });
    pushToast({ kind: 'info', message: 'b' });
    const list = get(toasts);
    expect(list).toHaveLength(2);
    expect(list[1]!.id).toBeGreaterThan(list[0]!.id);
  });
  it('dismisses by id', () => {
    pushToast({ kind: 'error', message: 'a' });
    const id = get(toasts)[0]!.id;
    dismissToast(id);
    expect(get(toasts)).toHaveLength(0);
  });
});
