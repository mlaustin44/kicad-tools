export type Uuid = string;
export type Refdes = string;

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(s: string): boolean {
  return UUID_RE.test(s);
}

export function normalizeRefdes(s: string): Refdes {
  return s.trim().toUpperCase();
}
