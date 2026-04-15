import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import { computeComponentFrame } from '$lib/three/camera-framing';

describe('computeComponentFrame', () => {
  it('target is the bbox center', () => {
    const min = new THREE.Vector3(10, 0, 20);
    const max = new THREE.Vector3(20, 2, 30);
    const f = computeComponentFrame(min, max, 45, 'top');
    expect(f.target.x).toBeCloseTo(15);
    expect(f.target.y).toBeCloseTo(1);
    expect(f.target.z).toBeCloseTo(25);
  });

  it('top-side camera ends up above the part (y > target.y)', () => {
    const min = new THREE.Vector3(-5, 0, -5);
    const max = new THREE.Vector3(5, 1, 5);
    const f = computeComponentFrame(min, max, 45, 'top');
    expect(f.position.y).toBeGreaterThan(f.target.y);
  });

  it('bottom-side camera ends up below the part (y < target.y)', () => {
    const min = new THREE.Vector3(-5, 0, -5);
    const max = new THREE.Vector3(5, 1, 5);
    const f = computeComponentFrame(min, max, 45, 'bottom');
    expect(f.position.y).toBeLessThan(f.target.y);
  });

  it('tiny parts get a minimum padding so we do not over-zoom', () => {
    const tinyMin = new THREE.Vector3(-0.5, 0, -0.5);
    const tinyMax = new THREE.Vector3(0.5, 0.1, 0.5);
    const big = new THREE.Vector3(-7.5, 0, -7.5);
    const bigMax = new THREE.Vector3(7.5, 1, 7.5);
    const tinyF = computeComponentFrame(tinyMin, tinyMax, 45, 'top');
    const bigF = computeComponentFrame(big, bigMax, 45, 'top');
    const tinyDist = tinyF.position.distanceTo(tinyF.target);
    const bigDist = bigF.position.distanceTo(bigF.target);
    // 1mm cube should be capped to the 15mm-min-context distance,
    // essentially matching the 15mm cube.
    expect(tinyDist).toBeCloseTo(bigDist, 1);
  });

  it('bigger components sit further from the camera', () => {
    const small = computeComponentFrame(
      new THREE.Vector3(-7.5, 0, -7.5),
      new THREE.Vector3(7.5, 1, 7.5),
      45,
      'top'
    );
    const huge = computeComponentFrame(
      new THREE.Vector3(-50, 0, -50),
      new THREE.Vector3(50, 1, 50),
      45,
      'top'
    );
    expect(huge.position.distanceTo(huge.target)).toBeGreaterThan(
      small.position.distanceTo(small.target)
    );
  });
});
