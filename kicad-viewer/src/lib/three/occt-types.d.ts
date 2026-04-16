// Minimal typings for occt-import-js (no official types published).
// Public surface we care about: the default export is an async factory that
// resolves to a module with ReadStepFile(buffer, params).

declare module 'occt-import-js' {
  interface OcctMeshAttribute {
    array: Float32Array | number[];
  }
  interface OcctMeshAttributes {
    position: OcctMeshAttribute;
    normal?: OcctMeshAttribute | undefined;
  }
  interface OcctMesh {
    name: string;
    attributes: OcctMeshAttributes;
    index: { array: Uint32Array | number[] };
    color?: [number, number, number] | undefined;
    brep_faces?: Array<{ first: number; last: number; color?: [number, number, number] | undefined }>;
  }
  interface OcctReadResult {
    success: boolean;
    meshes: OcctMesh[];
    root?: OcctNode | undefined;
  }
  interface OcctNode {
    name: string;
    meshes: number[];
    children: OcctNode[];
  }
  interface OcctModule {
    ReadStepFile(buffer: Uint8Array, params: unknown): OcctReadResult;
  }
  interface OcctFactoryOptions {
    locateFile?: (path: string) => string;
  }
  type OcctFactory = (opts?: OcctFactoryOptions) => Promise<OcctModule>;
  const factory: OcctFactory;
  export default factory;
}

declare module 'occt-import-js/dist/occt-import-js.wasm?url' {
  const url: string;
  export default url;
}
