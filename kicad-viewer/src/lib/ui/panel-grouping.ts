// Classification helpers shared by the left-sidebar panels.

// KiCad conventional refdes-letter → human type label.
// Keep multi-letter prefixes before single-letter fallbacks; `refdesPrefix`
// walks from longest to shortest.
const PREFIX_LABELS: Array<[string, string]> = [
  ['TVS', 'TVS Diodes'],
  ['ANT', 'Antennas'],
  ['BZ', 'Buzzers'],
  ['BT', 'Batteries'],
  ['DS', 'Displays'],
  ['FB', 'Ferrite Beads'],
  ['LS', 'Speakers'],
  ['MH', 'Mounting Holes'],
  ['MK', 'Microphones'],
  ['SW', 'Switches'],
  ['TP', 'Test Points'],
  ['R', 'Resistors'],
  ['C', 'Capacitors'],
  ['L', 'Inductors'],
  ['D', 'Diodes'],
  ['Q', 'Transistors'],
  ['U', 'ICs'],
  ['J', 'Connectors'],
  ['P', 'Connectors'],
  ['K', 'Relays'],
  ['Y', 'Crystals'],
  ['X', 'Crystals'],
  ['F', 'Fuses'],
  ['T', 'Transformers'],
  ['H', 'Hardware']
];

// Order groups appear in the UI. Anything missing falls through to "Other"
// at the end (label sorted).
const GROUP_ORDER = [
  'ICs',
  'Connectors',
  'Transistors',
  'Diodes',
  'TVS Diodes',
  'Crystals',
  'Inductors',
  'Ferrite Beads',
  'Transformers',
  'Relays',
  'Resistors',
  'Capacitors',
  'Fuses',
  'Switches',
  'Test Points',
  'Displays',
  'Speakers',
  'Microphones',
  'Buzzers',
  'Antennas',
  'Batteries',
  'Mounting Holes',
  'Hardware'
];

/**
 * Pull the leading letters off a refdes. "R12" → "R", "TP3" → "TP".
 * Falls back to "?" for empty/numeric-only refdes.
 */
export function refdesPrefix(refdes: string): string {
  const m = refdes.match(/^[A-Za-z]+/);
  return m ? m[0].toUpperCase() : '?';
}

export function refdesTypeLabel(refdes: string): string {
  const pfx = refdesPrefix(refdes);
  for (const [prefix, label] of PREFIX_LABELS) {
    if (pfx === prefix) return label;
  }
  return pfx === '?' ? 'Other' : pfx;
}

/** Sort refdes naturally — R2 before R10. */
export function compareRefdes(a: string, b: string): number {
  const ap = a.match(/^([A-Za-z]+)(\d+)/);
  const bp = b.match(/^([A-Za-z]+)(\d+)/);
  if (ap && bp && ap[1]!.toUpperCase() === bp[1]!.toUpperCase()) {
    return parseInt(ap[2]!, 10) - parseInt(bp[2]!, 10);
  }
  return a.localeCompare(b);
}

/** Stable index for group ordering; unknowns sink to the end. */
export function groupOrderIndex(label: string): number {
  const i = GROUP_ORDER.indexOf(label);
  return i === -1 ? GROUP_ORDER.length + 1 : i;
}

// --- Net classification ---

/**
 * Classify a net name as a power rail vs a regular signal.
 *
 * Power if any of:
 * - Starts with +/- (e.g. +3V3, -12V)
 * - Matches a known rail name (GND/AGND/DGND/PGND/EARTH/VCC/VDD/VSS/VEE/VBUS/VBAT/VIN/VOUT)
 *   either bare or with _SUFFIX
 * - Matches NvM style rails (3V3, 1V8, 12V0, 5V)
 */
export function isPowerRail(name: string): boolean {
  if (!name) return false;
  const n = name.toUpperCase();
  if (n.startsWith('+') || n.startsWith('-')) return true;
  if (/^(GND|AGND|DGND|PGND|SGND|EGND|EARTH|VCC|VDD|VSS|VEE|VBUS|VBAT|VIN|VOUT)(_.*)?$/.test(n)) {
    return true;
  }
  if (/^\d+V\d*(_.*)?$/.test(n)) return true;
  return false;
}
