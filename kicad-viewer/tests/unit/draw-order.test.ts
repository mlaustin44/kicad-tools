import { describe, it, expect } from 'vitest';
import { computeDrawOrder } from '$lib/pcb/draw-order';
import type { LayerInfo } from '$lib/model/project';

function L(id: string, type: string = id): LayerInfo {
  return { id, name: id, type, defaultColor: '#888' } as LayerInfo;
}

const fourLayer: LayerInfo[] = [
  L('F.Cu'),
  L('In1.Cu', 'In.Cu'),
  L('In2.Cu', 'In.Cu'),
  L('B.Cu'),
  L('F.SilkS'),
  L('B.SilkS'),
  L('F.Mask'),
  L('B.Mask'),
  L('F.Paste'),
  L('B.Paste'),
  L('F.Fab'),
  L('B.Fab'),
  L('F.CrtYd'),
  L('B.CrtYd'),
  L('Edge.Cuts')
];

function idsOf(layers: LayerInfo[]): string[] {
  return layers.map((l) => l.id);
}

describe('computeDrawOrder (F.Cu active)', () => {
  it('puts back-side non-copper first, front-side copper last, edge last of all', () => {
    const order = idsOf(computeDrawOrder(fourLayer, 'F.Cu'));
    expect(order[order.length - 1]).toBe('Edge.Cuts');
    const fCuIdx = order.indexOf('F.Cu');
    const edgeIdx = order.indexOf('Edge.Cuts');
    expect(fCuIdx).toBe(edgeIdx - 1);
    const bSilkIdx = order.indexOf('B.SilkS');
    const fSilkIdx = order.indexOf('F.SilkS');
    expect(bSilkIdx).toBeLessThan(fSilkIdx);
    expect(order.indexOf('B.Cu')).toBeLessThan(fCuIdx);
  });
});

describe('computeDrawOrder (B.Cu active)', () => {
  it('puts front-side non-copper first, back-side copper last', () => {
    const order = idsOf(computeDrawOrder(fourLayer, 'B.Cu'));
    expect(order[order.length - 1]).toBe('Edge.Cuts');
    const bCuIdx = order.indexOf('B.Cu');
    expect(bCuIdx).toBe(order.indexOf('Edge.Cuts') - 1);
    expect(order.indexOf('F.SilkS')).toBeLessThan(order.indexOf('B.SilkS'));
    expect(order.indexOf('F.Cu')).toBeLessThan(bCuIdx);
  });
});

describe('computeDrawOrder (In1.Cu active on 4-layer)', () => {
  it('treats In1 as front side and draws it on top of copper group', () => {
    const order = idsOf(computeDrawOrder(fourLayer, 'In1.Cu'));
    expect(order[order.length - 1]).toBe('Edge.Cuts');
    expect(order[order.length - 2]).toBe('In1.Cu');
    expect(order.indexOf('B.SilkS')).toBeLessThan(order.indexOf('F.SilkS'));
    expect(order.indexOf('F.Cu')).toBeLessThan(order.indexOf('In1.Cu'));
    expect(order.indexOf('B.Cu')).toBeLessThan(order.indexOf('F.Cu'));
  });
});

describe('computeDrawOrder (missing layers)', () => {
  it('ignores layers not in the list', () => {
    const twoLayer: LayerInfo[] = [L('F.Cu'), L('B.Cu'), L('Edge.Cuts')];
    const order = idsOf(computeDrawOrder(twoLayer, 'F.Cu'));
    expect(order).toEqual(['B.Cu', 'F.Cu', 'Edge.Cuts']);
  });

  it('is stable when active layer is not in list', () => {
    const twoLayer: LayerInfo[] = [L('F.Cu'), L('B.Cu'), L('Edge.Cuts')];
    const order = idsOf(computeDrawOrder(twoLayer, 'In1.Cu'));
    expect(order[order.length - 1]).toBe('Edge.Cuts');
  });
});
