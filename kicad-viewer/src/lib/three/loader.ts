import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import * as THREE from 'three';
import type { Group, Object3D } from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';

export async function loadGlb(url: string): Promise<Group> {
  const loader = new GLTFLoader();
  return new Promise<Group>((resolve, reject) => {
    loader.load(
      url,
      (gltf) => {
        optimizeForRender(gltf.scene);
        resolve(gltf.scene);
      },
      undefined,
      (err) => reject(err instanceof Error ? err : new Error(String(err)))
    );
  });
}

/**
 * Collapse adjacent "static" meshes (board, copper, silk, mask — anything
 * that isn't a refdes-labeled component) into one merged BufferGeometry per
 * material. A rich kicad-cli GLB can come in with thousands of draw calls;
 * without this pass, orbiting drops to ~5fps. Components keep their own
 * meshes so the click-to-refdes regex still lands.
 */
function optimizeForRender(root: Object3D): void {
  const REFDES_RE = /^[A-Z]+\d+/;
  // Collect mergeable meshes grouped by a material signature.
  const buckets = new Map<string, THREE.Mesh[]>();
  const toRemove: THREE.Mesh[] = [];
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh;
    if (!mesh.isMesh) return;
    // Walk up looking for a refdes-named ancestor; leave those alone.
    let cursor: Object3D | null = mesh;
    while (cursor) {
      if (cursor.name && REFDES_RE.test(cursor.name)) return;
      cursor = cursor.parent;
    }
    const mat = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material;
    if (!mat || Array.isArray(mesh.material)) return;
    // Key on material properties so copper/mask/silk stay visually distinct.
    const std = mat as THREE.MeshStandardMaterial;
    const key = [
      mat.type,
      std.color?.getHexString?.() ?? '',
      (std.metalness ?? 0).toFixed(2),
      (std.roughness ?? 0).toFixed(2),
      mat.transparent ? 't' : 'o',
      (mat.opacity ?? 1).toFixed(2)
    ].join('|');
    const bucket = buckets.get(key) ?? [];
    bucket.push(mesh);
    buckets.set(key, bucket);
  });

  for (const [, meshes] of buckets) {
    if (meshes.length < 4) continue; // not worth merging
    const baked: THREE.BufferGeometry[] = [];
    for (const m of meshes) {
      const g = m.geometry.clone();
      m.updateWorldMatrix(true, false);
      g.applyMatrix4(m.matrixWorld);
      // mergeGeometries requires all inputs to share attributes.
      if (!g.getAttribute('position')) { g.dispose(); continue; }
      if (!g.getAttribute('normal')) g.computeVertexNormals();
      // Strip non-essential attributes so every input matches.
      for (const name of Object.keys(g.attributes)) {
        if (name !== 'position' && name !== 'normal' && name !== 'uv') {
          g.deleteAttribute(name);
        }
      }
      baked.push(g);
    }
    if (baked.length === 0) continue;
    let merged: THREE.BufferGeometry | null = null;
    try {
      merged = mergeGeometries(baked, false);
    } catch {
      merged = null;
    }
    for (const g of baked) g.dispose();
    if (!merged) continue;

    const templateMat = Array.isArray(meshes[0]!.material) ? meshes[0]!.material[0] : meshes[0]!.material;
    const mergedMesh = new THREE.Mesh(merged, templateMat ?? new THREE.MeshStandardMaterial());
    mergedMesh.name = `merged:${meshes[0]!.name || 'static'}`;
    root.add(mergedMesh);
    toRemove.push(...meshes);
  }

  for (const m of toRemove) {
    m.removeFromParent();
    m.geometry.dispose();
  }
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
