import { describe, it, expect } from 'vitest';
import { normalizeRefdes, isUuid } from '$lib/model/ids';

describe('ids', () => {
  it('uppercases and trims refdes', () => {
    expect(normalizeRefdes(' u1 ')).toBe('U1');
    expect(normalizeRefdes('r10')).toBe('R10');
  });

  it('recognises UUID v4', () => {
    expect(isUuid('00000000-0000-4000-8000-000000000000')).toBe(true);
    expect(isUuid('not-a-uuid')).toBe(false);
  });
});
