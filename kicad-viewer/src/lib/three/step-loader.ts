import * as THREE from 'three';

type OcctModule = Awaited<ReturnType<typeof import('occt-import-js')['default']>>;

// occt-import-js is heavyweight (~8MB wasm). Load lazily on first use and
// cache the module promise so repeated STEP drops reuse the same isolate.
let occtModulePromise: Promise<OcctModule> | null = null;

function loadOcct(): Promise<OcctModule> {
  if (!occtModulePromise) {
    occtModulePromise = (async () => {
      const [factoryModule, wasmUrlModule] = await Promise.all([
        import('occt-import-js'),
        import('occt-import-js/dist/occt-import-js.wasm?url')
      ]);
      const factory = factoryModule.default;
      const wasmUrl = wasmUrlModule.default;
      return factory({
        locateFile: (path) => (path.endsWith('.wasm') ? wasmUrl : path)
      });
    })();
  }
  return occtModulePromise;
}

/**
 * Parse a STEP file's bytes into a THREE.Group with one child Mesh per
 * imported solid. Mesh.name is preserved from the STEP product name so the
 * existing refdes-regex cross-probe logic keeps working.
 */
export async function loadStep(buffer: Uint8Array): Promise<THREE.Group> {
  const occt = await loadOcct();
  const result = occt.ReadStepFile(buffer, null);
  if (!result.success) {
    throw new Error('Failed to parse STEP file');
  }

  const group = new THREE.Group();
  for (const m of result.meshes) {
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
    const index =
      indexArr instanceof Uint32Array ? indexArr : Uint32Array.from(indexArr);
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
    group.add(mesh);
  }

  // KiCad's STEP export is in millimeters with Z-up. three.js / KiCad GLB
  // convention in this project is Y-up. Rotate -90° about X so the board
  // lays flat like the GLB path already expects.
  group.rotation.x = -Math.PI / 2;
  return group;
}
