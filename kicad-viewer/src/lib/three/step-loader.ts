import * as THREE from 'three';

// Minimal mirror of the occt-import-js output shape so the worker-borne data
// can be consumed without importing the WASM on the main thread.
interface OcctMesh {
  name: string;
  attributes: {
    position: { array: Float32Array | number[] };
    normal?: { array: Float32Array | number[] };
  };
  index: { array: Uint32Array | number[] };
  color?: [number, number, number];
}
interface OcctNode {
  name: string;
  meshes: number[];
  children: OcctNode[];
}
interface OcctReadResult {
  success: boolean;
  meshes: OcctMesh[];
  root?: OcctNode;
}

// Lazy worker — created on first STEP load, kept alive for the session so
// the ~8MB WASM only initializes once.
let worker: Worker | null = null;
let nextReqId = 0;
const pendingReqs = new Map<number, { resolve: (r: OcctReadResult) => void; reject: (e: Error) => void }>();

function ensureWorker(): Worker {
  if (worker) return worker;
  worker = new Worker(new URL('./step-worker.ts', import.meta.url), { type: 'module' });
  worker.onmessage = (ev: MessageEvent<{ id: number; ok: boolean; error?: string; result?: OcctReadResult }>) => {
    const pending = pendingReqs.get(ev.data.id);
    if (!pending) return;
    pendingReqs.delete(ev.data.id);
    if (ev.data.ok && ev.data.result) pending.resolve(ev.data.result);
    else pending.reject(new Error(ev.data.error ?? 'STEP worker failure'));
  };
  worker.onerror = (ev) => {
    for (const [, p] of pendingReqs) p.reject(new Error(ev.message || 'STEP worker error'));
    pendingReqs.clear();
  };
  return worker;
}

function parseInWorker(buffer: ArrayBuffer): Promise<OcctReadResult> {
  const w = ensureWorker();
  const id = ++nextReqId;
  return new Promise<OcctReadResult>((resolve, reject) => {
    pendingReqs.set(id, { resolve, reject });
    // Transfer the buffer — we don't need it on the main thread after this.
    w.postMessage({ id, buffer }, [buffer]);
  });
}

// Per-URL cache. Parsing a 17MB STEP takes tens of seconds even in a worker,
// so tab-switching (which unmounts ThreeDView) must not re-parse. We hold the
// built three.js Group; entries are only evicted when the URL changes (e.g.
// user loaded a different file) so the old geometry can be disposed.
const cache = new Map<string, Promise<THREE.Group>>();

export function evictStep(url: string): void {
  const p = cache.get(url);
  if (!p) return;
  cache.delete(url);
  p.then((group) => {
    group.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (mesh.geometry) mesh.geometry.dispose();
      const mat = mesh.material;
      if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
      else if (mat) mat.dispose();
    });
  }).catch(() => {});
}

/**
 * Parse a STEP file at the given URL into a THREE.Group. The tree is built
 * to mirror the STEP assembly hierarchy so KiCad-exported refdes labels
 * (attached to assembly nodes, not leaf shape meshes) are preserved on the
 * three.js group names — that's what the click-to-refdes regex traverses.
 */
export function loadStep(url: string): Promise<THREE.Group> {
  const cached = cache.get(url);
  if (cached) return cached;
  const p = buildFromUrl(url);
  cache.set(url, p);
  // If parsing fails, drop the cache entry so a retry can happen.
  p.catch(() => cache.delete(url));
  return p;
}

async function buildFromUrl(url: string): Promise<THREE.Group> {
  const response = await fetch(url);
  const buffer = await response.arrayBuffer();
  const result = await parseInWorker(buffer);
  if (!result.success) throw new Error('Failed to parse STEP file');

  const root = new THREE.Group();
  root.name = result.root?.name ?? 'step-root';

  if (result.root) {
    buildNode(result.root, result.meshes, root);
  } else {
    for (const m of result.meshes) root.add(buildMesh(m));
  }

  // KiCad STEP export is Z-up; three.js / the existing GLB pipeline are Y-up.
  root.rotation.x = -Math.PI / 2;
  return root;
}

function buildNode(node: OcctNode, meshes: OcctMesh[], parent: THREE.Object3D): void {
  const group = new THREE.Group();
  group.name = node.name ?? '';
  parent.add(group);
  for (const idx of node.meshes) {
    const m = meshes[idx];
    if (m) group.add(buildMesh(m));
  }
  for (const child of node.children) {
    buildNode(child, meshes, group);
  }
}

function buildMesh(m: OcctMesh): THREE.Mesh {
  const geometry = new THREE.BufferGeometry();
  const positions = m.attributes.position.array;
  geometry.setAttribute(
    'position',
    new THREE.Float32BufferAttribute(
      positions instanceof Float32Array ? positions : Float32Array.from(positions),
      3
    )
  );
  if (m.attributes.normal) {
    const normals = m.attributes.normal.array;
    geometry.setAttribute(
      'normal',
      new THREE.Float32BufferAttribute(
        normals instanceof Float32Array ? normals : Float32Array.from(normals),
        3
      )
    );
  } else {
    geometry.computeVertexNormals();
  }
  const indexArr = m.index.array;
  const index = indexArr instanceof Uint32Array ? indexArr : Uint32Array.from(indexArr);
  geometry.setIndex(new THREE.BufferAttribute(index, 1));

  const color = m.color
    ? new THREE.Color(m.color[0], m.color[1], m.color[2])
    : new THREE.Color(0xb0b0b0);
  const material = new THREE.MeshStandardMaterial({
    color,
    metalness: 0.2,
    roughness: 0.7
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.name = m.name ?? '';
  return mesh;
}
