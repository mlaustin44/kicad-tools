import { describe, it, expect } from 'vitest';
import {
  refdesPrefix,
  refdesTypeLabel,
  compareRefdes,
  isPowerRail
} from '$lib/ui/panel-grouping';

describe('refdesPrefix', () => {
  it('strips numeric suffix', () => {
    expect(refdesPrefix('R12')).toBe('R');
    expect(refdesPrefix('TP3')).toBe('TP');
    expect(refdesPrefix('SW1')).toBe('SW');
  });
  it('uppercases and handles edge cases', () => {
    expect(refdesPrefix('u7')).toBe('U');
    expect(refdesPrefix('')).toBe('?');
    expect(refdesPrefix('42')).toBe('?');
  });
});

describe('refdesTypeLabel', () => {
  it('maps common prefixes', () => {
    expect(refdesTypeLabel('R1')).toBe('Resistors');
    expect(refdesTypeLabel('C100')).toBe('Capacitors');
    expect(refdesTypeLabel('U3')).toBe('ICs');
    expect(refdesTypeLabel('J2')).toBe('Connectors');
    expect(refdesTypeLabel('Q5')).toBe('Transistors');
    expect(refdesTypeLabel('TP7')).toBe('Test Points');
    expect(refdesTypeLabel('FB1')).toBe('Ferrite Beads');
  });
  it('falls back to prefix for unknowns', () => {
    expect(refdesTypeLabel('ZZZ4')).toBe('ZZZ');
  });
});

describe('compareRefdes', () => {
  it('sorts naturally within prefix', () => {
    const arr = ['R10', 'R2', 'R1', 'R20'];
    arr.sort(compareRefdes);
    expect(arr).toEqual(['R1', 'R2', 'R10', 'R20']);
  });
});

describe('isPowerRail', () => {
  it('flags explicit-sign rails', () => {
    expect(isPowerRail('+3V3')).toBe(true);
    expect(isPowerRail('+5V')).toBe(true);
    expect(isPowerRail('-12V')).toBe(true);
  });
  it('flags named rails', () => {
    expect(isPowerRail('GND')).toBe(true);
    expect(isPowerRail('AGND')).toBe(true);
    expect(isPowerRail('VCC')).toBe(true);
    expect(isPowerRail('VDD')).toBe(true);
    expect(isPowerRail('VBUS')).toBe(true);
    expect(isPowerRail('VBUS_RAW')).toBe(true);
  });
  it('flags NvM patterns', () => {
    expect(isPowerRail('3V3')).toBe(true);
    expect(isPowerRail('1V8')).toBe(true);
    expect(isPowerRail('12V0')).toBe(true);
  });
  it('rejects signals', () => {
    expect(isPowerRail('SDA')).toBe(false);
    expect(isPowerRail('USB_DP')).toBe(false);
    expect(isPowerRail('RESET_N')).toBe(false);
    expect(isPowerRail('Net-(U1-Pad3)')).toBe(false);
  });
});
