import { describe, it, expect } from 'vitest';
import { classifyLayer, innerCopperSide } from '$lib/pcb/layer-side';
import type { LayerInfo } from '$lib/model/project';

function mkLayers(ids: string[]): LayerInfo[] {
  return ids.map((id) => ({
    id,
    name: id,
    type: id.endsWith('.Cu') ? (id === 'F.Cu' || id === 'B.Cu' ? id : 'In.Cu') : 'Other',
    defaultColor: '#888'
  })) as LayerInfo[];
}

describe('classifyLayer', () => {
  const twoLayer = mkLayers(['F.Cu', 'B.Cu', 'F.SilkS', 'B.SilkS', 'Edge.Cuts']);

  it('classifies F.* as front', () => {
    expect(classifyLayer('F.Cu', twoLayer)).toBe('front');
    expect(classifyLayer('F.SilkS', twoLayer)).toBe('front');
    expect(classifyLayer('F.Mask', twoLayer)).toBe('front');
    expect(classifyLayer('F.Paste', twoLayer)).toBe('front');
    expect(classifyLayer('F.Fab', twoLayer)).toBe('front');
    expect(classifyLayer('F.CrtYd', twoLayer)).toBe('front');
    expect(classifyLayer('F.Adhesive', twoLayer)).toBe('front');
  });

  it('classifies B.* as back', () => {
    expect(classifyLayer('B.Cu', twoLayer)).toBe('back');
    expect(classifyLayer('B.SilkS', twoLayer)).toBe('back');
  });

  it('classifies board-wide layers as board', () => {
    expect(classifyLayer('Edge.Cuts', twoLayer)).toBe('board');
    expect(classifyLayer('User.1', twoLayer)).toBe('board');
    expect(classifyLayer('Dwgs.User', twoLayer)).toBe('board');
    expect(classifyLayer('Cmts.User', twoLayer)).toBe('board');
    expect(classifyLayer('Eco1.User', twoLayer)).toBe('board');
    expect(classifyLayer('Eco2.User', twoLayer)).toBe('board');
    expect(classifyLayer('Margin', twoLayer)).toBe('board');
  });

  it('falls back to board for unknown ids', () => {
    expect(classifyLayer('Weird.Custom', twoLayer)).toBe('board');
  });

  it('classifies inner copper by stackup half', () => {
    const four = mkLayers(['F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu']);
    expect(classifyLayer('In1.Cu', four)).toBe('front');
    expect(classifyLayer('In2.Cu', four)).toBe('back');

    const six = mkLayers(['F.Cu', 'In1.Cu', 'In2.Cu', 'In3.Cu', 'In4.Cu', 'B.Cu']);
    expect(classifyLayer('In1.Cu', six)).toBe('front');
    expect(classifyLayer('In2.Cu', six)).toBe('front');
    expect(classifyLayer('In3.Cu', six)).toBe('back');
    expect(classifyLayer('In4.Cu', six)).toBe('back');
  });
});

describe('innerCopperSide', () => {
  it('rounds up when inner count is odd', () => {
    const five = [
      { id: 'F.Cu', type: 'F.Cu' },
      { id: 'In1.Cu', type: 'In.Cu' },
      { id: 'In2.Cu', type: 'In.Cu' },
      { id: 'In3.Cu', type: 'In.Cu' },
      { id: 'B.Cu', type: 'B.Cu' }
    ] as LayerInfo[];
    expect(innerCopperSide('In1.Cu', five)).toBe('front');
    expect(innerCopperSide('In2.Cu', five)).toBe('front');
    expect(innerCopperSide('In3.Cu', five)).toBe('back');
  });
});
