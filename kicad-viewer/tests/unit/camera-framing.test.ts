import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import { computeComponentFrame } from '$lib/three/camera-framing';

// sceneMaxDim simulates a 100-unit board for mm-scale or 0.1 for meter-scale.
const SCENE_MM = 100;
const SCENE_M = 0.1;

describe('computeComponentFrame', () => {
  it('target is the bbox center', () => {
    const min = new THREE.Vector3(10, 0, 20);
    const max = new THREE.Vector3(20, 2, 30);
    const f = computeComponentFrame(min, max, 45, 'top', SCENE_MM);
    expect(f.target.x).toBeCloseTo(15);
    expect(f.target.y).toBeCloseTo(1);
    expect(f.target.z).toBeCloseTo(25);
  });

  it('top-side camera ends up above the part (y > target.y)', () => {
    const min = new THREE.Vector3(-5, 0, -5);
    const max = new THREE.Vector3(5, 1, 5);
    const f = computeComponentFrame(min, max, 45, 'top', SCENE_MM);
    expect(f.position.y).toBeGreaterThan(f.target.y);
  });

  it('bottom-side camera ends up below the part (y < target.y)', () => {
    const min = new THREE.Vector3(-5, 0, -5);
    const max = new THREE.Vector3(5, 1, 5);
    const f = computeComponentFrame(min, max, 45, 'bottom', SCENE_MM);
    expect(f.position.y).toBeLessThan(f.target.y);
  });

  it('tiny parts get minimum padding so we do not over-zoom', () => {
    const tinyF = computeComponentFrame(
      new THREE.Vector3(-0.5, 0, -0.5),
      new THREE.Vector3(0.5, 0.1, 0.5),
      45, 'top', SCENE_MM
    );
    // min-context = 100 * 0.12 = 12 units. Tiny part (1 unit) is padded to 12.
    const bigF = computeComponentFrame(
      new THREE.Vector3(-6, 0, -6),
      new THREE.Vector3(6, 1, 6),
      45, 'top', SCENE_MM
    );
    // The 12-unit component should produce a similar distance to the padded tiny.
    expect(tinyF.position.distanceTo(tinyF.target)).toBeCloseTo(
      bigF.position.distanceTo(bigF.target), 0
    );
  });

  it('bigger components sit further from the camera', () => {
    const small = computeComponentFrame(
      new THREE.Vector3(-7.5, 0, -7.5),
      new THREE.Vector3(7.5, 1, 7.5),
      45, 'top', SCENE_MM
    );
    const huge = computeComponentFrame(
      new THREE.Vector3(-50, 0, -50),
      new THREE.Vector3(50, 1, 50),
      45, 'top', SCENE_MM
    );
    expect(huge.position.distanceTo(huge.target)).toBeGreaterThan(
      small.position.distanceTo(small.target)
    );
  });

  it('scales correctly for meter-unit models (GLB)', () => {
    // 10mm IC on a 100mm board, but in meters
    const f = computeComponentFrame(
      new THREE.Vector3(-0.005, 0, -0.005),
      new THREE.Vector3(0.005, 0.001, 0.005),
      45, 'top', SCENE_M
    );
    const dist = f.position.distanceTo(f.target);
    // Camera should be within a reasonable fraction of the scene — not 36m away.
    expect(dist).toBeLessThan(SCENE_M * 2);
    expect(dist).toBeGreaterThan(SCENE_M * 0.01);
  });
});
