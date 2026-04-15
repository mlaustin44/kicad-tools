import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { Group, Object3D } from 'three';

export async function loadGlb(url: string): Promise<Group> {
  const loader = new GLTFLoader();
  return new Promise((resolve, reject) => {
    loader.load(
      url,
      (gltf) => resolve(gltf.scene),
      undefined,
      (err) => reject(err instanceof Error ? err : new Error(String(err)))
    );
  });
}

/** Build refdes -> Object3D map from named nodes.
 *  KiCad 10's GLB export tends to name each footprint group with the refdes
 *  somewhere in the string (often at the start, sometimes as "U1:value" or similar).
 *  We match refdes via a pragmatic regex and take the first mesh with a matching
 *  refdes token. If the export doesn't name by refdes, this map will be empty and
 *  cross-probe-to-3D becomes a no-op.
 */
export function indexByRefdes(root: Group): Map<string, Object3D> {
  const m = new Map<string, Object3D>();
  root.traverse((obj) => {
    if (!obj.name) return;
    // Extract a refdes token at the start (e.g., "R1", "U23", "C100").
    const match = obj.name.match(/^([A-Z]+\d+)/);
    if (!match) return;
    const refdes = match[1];
    if (!refdes) return;
    // First-writer-wins: if the same refdes appears on multiple nodes, take the outermost.
    if (!m.has(refdes)) m.set(refdes, obj);
  });
  return m;
}
