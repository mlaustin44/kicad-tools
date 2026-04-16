import * as THREE from 'three';

export interface FrameResult {
  /** Where the camera should sit. */
  position: THREE.Vector3;
  /** Where the camera should look (OrbitControls target). */
  target: THREE.Vector3;
}

/**
 * Compute a camera pose that frames a world-space AABB for a component.
 *
 * Sizing: padded to at least MIN_FRAME_MM so a 0402 doesn't turn into
 * a 100× zoom. Distance derived from the perspective FOV + largest padded
 * dimension, then a breathing-room factor.
 *
 * Direction: a 3/4 iso-ish angle that flips below the board for bottom-side
 * parts so they're actually visible.
 */
export function computeComponentFrame(
  bboxMin: THREE.Vector3,
  bboxMax: THREE.Vector3,
  fovDegrees: number,
  side: 'top' | 'bottom'
): FrameResult {
  const MIN_FRAME_MM = 15;
  const BREATHING_FACTOR = 1.2;

  const center = new THREE.Vector3().addVectors(bboxMin, bboxMax).multiplyScalar(0.5);
  const size = new THREE.Vector3().subVectors(bboxMax, bboxMin);
  const maxDim = Math.max(size.x, size.y, size.z);
  const padded = Math.max(maxDim, MIN_FRAME_MM);

  const fovRad = (fovDegrees * Math.PI) / 180;
  const halfPadded = padded / 2;
  const dist = (halfPadded / Math.tan(fovRad / 2)) * BREATHING_FACTOR * 2;

  const up = side === 'bottom' ? -1 : 1;
  const dir = new THREE.Vector3(0.4, up * 1.0, 0.5).normalize();
  const position = center.clone().add(dir.multiplyScalar(dist));

  return { position, target: center };
}
