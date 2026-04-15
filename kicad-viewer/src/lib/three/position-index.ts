import * as THREE from 'three';

export interface FootprintLike {
  refdes: string;
  position: { x: number; y: number };
}

/**
 * Match STEP meshes to refdes by spatial proximity. Needed because KiCad's
 * STEP export puts the refdes on `NEXT_ASSEMBLY_USAGE_OCCURRENCE` entries
 * (the assembly-link name) while occt-import-js exposes the underlying
 * `PRODUCT_DEFINITION` name instead — typically a generic "design". We can't
 * tell products apart by name, so we calibrate against the PCB footprint
 * positions we already have and match by position.
 *
 * Tries both z-sign orientations (KiCad's y-down vs. our three.js coords can
 * differ in handedness depending on how the group is set up) and keeps the
 * mapping that produces more matches.
 */
export function indexByPosition(
  group: THREE.Group,
  footprints: FootprintLike[]
): Map<string, THREE.Object3D> {
  if (footprints.length === 0) return new Map();

  // Collect candidate nodes with their world-bbox centers. We consider both
  // Groups (the assembly containers — usually what we want) and individual
  // Meshes (the fallback when a component is a single face with no wrapper).
  type Candidate = { obj: THREE.Object3D; wx: number; wz: number; vol: number };
  const groupCandidates: Candidate[] = [];
  const meshCandidates: Candidate[] = [];

  const COMPONENT_MAX_MM = 80; // any bigger than this is the whole-board body
  const COMPONENT_MIN_MM = 0.05;

  group.updateWorldMatrix(true, true);
  group.traverse((obj) => {
    if (obj === group) return;
    const box = new THREE.Box3().setFromObject(obj);
    if (box.isEmpty()) return;
    const size = box.getSize(new THREE.Vector3());
    const maxD = Math.max(size.x, size.y, size.z);
    if (maxD > COMPONENT_MAX_MM || maxD < COMPONENT_MIN_MM) return;
    const center = box.getCenter(new THREE.Vector3());
    const vol = Math.max(size.x, 0.01) * Math.max(size.y, 0.01) * Math.max(size.z, 0.01);
    const cand: Candidate = { obj, wx: center.x, wz: center.z, vol };
    if ((obj as THREE.Mesh).isMesh) meshCandidates.push(cand);
    else groupCandidates.push(cand);
  });

  const TOL_MM = 5;
  const TOL_SQ = TOL_MM * TOL_MM;

  function match(cands: Candidate[], zSign: 1 | -1): Map<string, THREE.Object3D> {
    const map = new Map<string, THREE.Object3D>();
    for (const fp of footprints) {
      let best: Candidate | null = null;
      let bestVol = Infinity;
      for (const c of cands) {
        const dx = c.wx - fp.position.x;
        const dy = zSign * c.wz - fp.position.y;
        if (dx * dx + dy * dy > TOL_SQ) continue;
        if (c.vol < bestVol) {
          bestVol = c.vol;
          best = c;
        }
      }
      if (best) map.set(fp.refdes, best.obj);
    }
    return map;
  }

  // Prefer groups if they yield any matches; otherwise fall back to meshes.
  // For each candidate pool try both sign conventions and keep the fatter map.
  let best = new Map<string, THREE.Object3D>();
  for (const pool of [groupCandidates, meshCandidates]) {
    for (const zSign of [1, -1] as const) {
      const m = match(pool, zSign);
      if (m.size > best.size) best = m;
    }
    if (best.size > 0) break;
  }
  return best;
}
