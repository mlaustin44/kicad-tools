<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import * as THREE from 'three';
  import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
  import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
  import { project, setProjectGlbUrl, setProjectStepUrl } from '$lib/stores/project';
  import { selection, selectComponent, clearSelection } from '$lib/stores/selection';
  import { theme } from '$lib/stores/theme';
  import { loadGlb, evictGlb, indexByRefdes } from '$lib/three/loader';
  import { loadStep, evictStep } from '$lib/three/step-loader';
  import { indexByPosition } from '$lib/three/position-index';
  import { computeComponentFrame } from '$lib/three/camera-framing';
  import { pushToast } from '$lib/stores/toasts';
  import { model3dStatus, markLoading, markReady, markError } from '$lib/stores/model3d';
  import { mergeRecentFile } from '$lib/stores/recent';

  type PresetView = 'top' | 'bottom' | 'iso';

  interface Props {
    fitRequested?: number;
    presetRequested?: PresetView | null;
  }
  let { fitRequested = 0, presetRequested = null }: Props = $props();

  let host: HTMLDivElement | undefined = $state();
  let canvas: HTMLCanvasElement | undefined = $state();

  let refdesToMesh: Map<string, THREE.Object3D> = new Map();
  // Reverse lookup for click hits: the raycast returns a leaf mesh, we walk
  // up parents until one appears here. Works uniformly for name-indexed GLB
  // and position-indexed STEP.
  let objToRefdes: WeakMap<THREE.Object3D, string> = new WeakMap();
  // Tracks whichever model is currently on screen (GLB or STEP). Keeping it
  // uniform lets cross-probe / click-hit / framing stay format-agnostic.
  let currentModelUrl: string | null = null;
  let currentModelKind: 'glb' | 'step' | null = null;
  let currentModelGroup: THREE.Group | null = null;

  // Ticks once per second while status.kind === 'loading' so the elapsed
  // time display can refresh. Separate from status so re-rendering doesn't
  // stomp on the shared store.
  let nowTick = $state(Date.now());
  $effect(() => {
    if ($model3dStatus.kind !== 'loading') return;
    const id = setInterval(() => (nowTick = Date.now()), 500);
    return () => clearInterval(id);
  });
  const elapsedSec = $derived.by(() => {
    if ($model3dStatus.kind !== 'loading') return 0;
    return Math.max(0, (nowTick - $model3dStatus.startedAt) / 1000);
  });

  let scene: THREE.Scene | null = null;
  let camera: THREE.PerspectiveCamera | null = null;
  let renderer: THREE.WebGLRenderer | null = null;
  let controls: OrbitControls | null = null;
  const raycaster = new THREE.Raycaster();

  function goToPreset(preset: PresetView): void {
    if (!currentModelGroup || !camera || !controls) return;
    const box = new THREE.Box3().setFromObject(currentModelGroup);
    if (box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    const dist = maxDim * 1.8;

    controls.target.copy(center);
    let offset: THREE.Vector3;
    if (preset === 'top')         offset = new THREE.Vector3(0, dist, 0);
    else if (preset === 'bottom') offset = new THREE.Vector3(0, -dist, 0);
    else                          offset = new THREE.Vector3(dist, dist, dist);

    camera.position.copy(center).add(offset);
    camera.lookAt(center);
    controls.update();
  }

  function adjustCameraClipping(box: THREE.Box3): void {
    if (!camera || box.isEmpty()) return;
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z) || 1;
    // Tight near/far bracket gives the depth buffer usable precision, which
    // is critical for KiCad GLBs where silkscreen sits ~15µm above the mask.
    // We still leave headroom so orbiting far out doesn't clip the board.
    camera.near = Math.max(0.001, maxDim * 0.0005);
    camera.far = Math.max(100, maxDim * 50);
    camera.updateProjectionMatrix();
  }

  function frameWhole(): void {
    if (!currentModelGroup || !camera || !controls) return;
    const box = new THREE.Box3().setFromObject(currentModelGroup);
    if (box.isEmpty()) return;
    adjustCameraClipping(box);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    controls.target.copy(center);
    const maxDim = Math.max(size.x, size.y, size.z);
    const dist = maxDim * 2;
    camera.position.copy(center).add(new THREE.Vector3(dist, dist, dist));
    camera.lookAt(center);
    controls.update();
  }

  function readRenderBgColor(): number {
    if (typeof getComputedStyle === 'undefined') return 0x0b0d12;
    const v = getComputedStyle(document.body).getPropertyValue('--kv-render-bg').trim();
    if (v.startsWith('#') && v.length === 7) return parseInt(v.slice(1), 16);
    return 0x0b0d12;
  }

  onMount(() => {
    if (!canvas || !host) return;

    scene = new THREE.Scene();
    scene.background = new THREE.Color(readRenderBgColor());

    camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
    camera.position.set(100, 80, 100);

    // logarithmicDepthBuffer kills the z-fighting that manifests as "melty"
    // silkscreen/mask when the GLB stacks many near-coplanar layers; pixel
    // ratio is capped because a KiCad GLB can have thousands of meshes and
    // the fill cost on a 2x retina surface destroys the frame rate.
    renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      logarithmicDepthBuffer: true,
      powerPreference: 'high-performance'
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.toneMapping = THREE.NoToneMapping;

    controls = new OrbitControls(camera, canvas);
    controls.enableDamping = true;

    // PBR lighting: without an environment map, metallic materials render as
    // flat grey because they have nothing to reflect. RoomEnvironment gives
    // us a cheap baked indoor-studio reflection so copper actually looks like
    // copper and the mask/silk pick up shape from ambient reflection.
    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

    // Environment map handles ambient/diffuse. Keep direct lights minimal —
    // just enough for specular highlights and a subtle fill.
    const key = new THREE.DirectionalLight(0xffffff, 0.6);
    key.position.set(100, 200, 100);
    scene.add(key);

    const ro = new ResizeObserver(() => resize());
    ro.observe(host);

    let raf = 0;
    const tick = (): void => {
      if (!renderer || !scene || !camera || !controls) return;
      controls.update();
      renderer.render(scene, camera);
      raf = requestAnimationFrame(tick);
    };
    resize();
    tick();

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer?.dispose();
      renderer = null;
      scene = null;
      camera = null;
      controls?.dispose();
      controls = null;
    };
  });

  function resize(): void {
    if (!host || !renderer || !camera) return;
    const r = host.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return;
    renderer.setSize(r.width, r.height, false);
    camera.aspect = r.width / r.height;
    camera.updateProjectionMatrix();
  }

  // Re-theme the 3D scene background when the theme token changes.
  $effect(() => {
    $theme;
    if (scene) scene.background = new THREE.Color(readRenderBgColor());
  });

  function disposeGlbGroup(group: THREE.Group): void {
    group.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (mesh.geometry) mesh.geometry.dispose();
      const mat = mesh.material;
      if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
      else if (mat) mat.dispose();
    });
  }

  // Load / swap 3D model when the project's stepUrl or glbUrl changes. STEP
  // takes precedence when both are present (higher-fidelity CAD geometry).
  //
  // Disposal is asymmetric: GLB groups are fresh each load so we can dispose
  // inline. STEP groups are cached by URL in step-loader.ts so tab switches
  // don't re-parse — we only evict (and dispose) when the URL actually
  // changes (user dropped a different file).
  $effect(() => {
    if (!scene) return;
    const stepUrl = $project?.stepUrl ?? null;
    const glbUrl = $project?.glbUrl ?? null;
    const kind: 'step' | 'glb' | null = stepUrl ? 'step' : glbUrl ? 'glb' : null;
    const url = stepUrl ?? glbUrl ?? null;

    if (url === currentModelUrl) return;

    // Swap out the previous model.
    if (currentModelGroup) {
      scene.remove(currentModelGroup);
      if (currentModelKind === 'glb' && currentModelUrl) {
        evictGlb(currentModelUrl);
      } else if (currentModelKind === 'step' && currentModelUrl) {
        evictStep(currentModelUrl);
      }
      currentModelGroup = null;
      refdesToMesh = new Map();
    }
    currentModelUrl = url;
    currentModelKind = kind;

    if (!url || !kind) return;

    markLoading(url);
    const loadPromise = kind === 'step' ? loadStep(url) : loadGlb(url);

    loadPromise
      .then((group) => {
        // Update status regardless of whether the view is still mounted —
        // the viewer page uses this to show a corner notification when the
        // user navigated away during a long STEP parse.
        markReady(url);
        if (currentModelUrl !== url) return; // superseded
        if (!scene) return;
        scene.add(group);
        currentModelGroup = group;

        // STEP: KiCad's export doesn't encode refdes on the product names
        // occt-import-js exposes (they sit on NEXT_ASSEMBLY_USAGE_OCCURRENCE
        // instead), so match to footprints by position. GLB from kicad-cli
        // does encode refdes in mesh names — keep the regex path for that.
        const footprints = $project?.pcb.footprints ?? [];
        refdesToMesh = kind === 'step'
          ? indexByPosition(group, footprints)
          : indexByRefdes(group);
        const rev = new WeakMap<THREE.Object3D, string>();
        for (const [r, o] of refdesToMesh) rev.set(o, r);
        objToRefdes = rev;

        if (refdesToMesh.size === 0) {
          pushToast({
            kind: 'info',
            message: '3D model loaded, but no components were matched to refdes — picking disabled.'
          });
        }
        // Debug: expose camera/controls for Playwright diagnostics.
        const _camera = camera;
        const _controls = controls;
        const _refdesToMesh = refdesToMesh;
        const _currentModelGroup = currentModelGroup;
        // Debug hook for Playwright: exposes a stable surface for asserting
        // that refdes matching worked and computing screen-space coordinates
        // of a specific refdes so tests can dispatch real clicks.
        (globalThis as unknown as { __kv3d?: unknown }).__kv3d = {
          refdesCount: refdesToMesh.size,
          refdesList: Array.from(refdesToMesh.keys()),
          getCameraState(): unknown {
            if (!_camera || !_controls) return null;
            return {
              pos: [_camera.position.x, _camera.position.y, _camera.position.z],
              target: [_controls.target.x, _controls.target.y, _controls.target.z],
              near: _camera.near,
              far: _camera.far,
              fov: _camera.fov
            };
          },
          screenPosFor(refdes: string): { x: number; y: number } | null {
            const obj = refdesToMesh.get(refdes);
            if (!obj || !camera || !canvas) return null;
            const box = new THREE.Box3().setFromObject(obj);
            if (box.isEmpty()) return null;
            const c = box.getCenter(new THREE.Vector3());
            const p = c.clone().project(camera);
            const rect = canvas.getBoundingClientRect();
            return {
              x: rect.left + ((p.x + 1) / 2) * rect.width,
              y: rect.top + ((1 - (p.y + 1) / 2)) * rect.height
            };
          }
        };
        frameWhole();
      })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : String(e);
        markError(url, msg);
        pushToast({ kind: 'error', message: `Couldn't load 3D model: ${msg}` });
      });
  });

  // Raycast -> selection on click
  function onClick(ev: MouseEvent): void {
    if (!camera || !canvas || !scene || !currentModelGroup) return;
    const rect = canvas.getBoundingClientRect();
    const x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
    const y = -(((ev.clientY - rect.top) / rect.height) * 2 - 1);
    raycaster.setFromCamera(new THREE.Vector2(x, y), camera);
    const picks = raycaster.intersectObject(currentModelGroup, true);
    for (const p of picks) {
      let o: THREE.Object3D | null = p.object;
      while (o) {
        const refdes = objToRefdes.get(o);
        if (refdes) {
          const comp = $project?.components.find((c) => c.refdes === refdes);
          if (comp) {
            selectComponent({ uuid: comp.uuid, source: '3d' });
            return;
          }
        }
        o = o.parent;
      }
    }
    // No hit on any component mesh — treat as a click on empty space.
    clearSelection();
  }

  async function ingestModelFile(f: File): Promise<void> {
    const lower = f.name.toLowerCase();
    const isGlb = /\.glb$/i.test(lower);
    const isStep = /\.(step|stp)$/i.test(lower);
    if (!isGlb && !isStep) {
      pushToast({ kind: 'error', message: '3D: expected a .glb, .step, or .stp file' });
      return;
    }
    const bytes = new Uint8Array(await f.arrayBuffer());
    const url = URL.createObjectURL(new Blob([bytes]));
    if (isStep) setProjectStepUrl(url);
    else setProjectGlbUrl(url);
    // Persist so the 3D file survives page reloads alongside the PCB/SCH.
    void mergeRecentFile(f.name, bytes);
  }

  function onModelDrop(ev: DragEvent): void {
    ev.preventDefault();
    const f = ev.dataTransfer?.files?.[0];
    if (f) void ingestModelFile(f);
  }

  function onModelPick(ev: Event): void {
    const t = ev.target as HTMLInputElement;
    const f = t.files?.[0];
    if (f) void ingestModelFile(f);
  }

  // Fit on external request.
  $effect(() => {
    if (fitRequested > 0) frameWhole();
  });

  // Preset on external request.
  $effect(() => {
    if (presetRequested) goToPreset(presetRequested);
  });

  // Tracks per-mesh material swaps so clearHighlight restores the original
  // shared material and disposes the cloned tinted copy. GLTFLoader shares
  // material instances across meshes — mutating them in-place would light up
  // every capacitor when you click one.
  const highlightedMeshes = new Map<THREE.Mesh, THREE.Material | THREE.Material[]>();
  const HIGHLIGHT_COLOR = new THREE.Color(0x4a90e2);

  function clearHighlight(): void {
    for (const [mesh, origMat] of highlightedMeshes) {
      const cloned = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      for (const c of cloned) c.dispose();
      mesh.material = origMat;
    }
    highlightedMeshes.clear();
  }

  function tintMaterial(m: THREE.Material): THREE.Material {
    const clone = m.clone();
    const std = clone as THREE.MeshStandardMaterial;
    if (std.emissive) {
      std.emissive.copy(HIGHLIGHT_COLOR);
      std.emissiveIntensity = 0.6;
    }
    return clone;
  }

  function applyHighlight(obj: THREE.Object3D): void {
    obj.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh) return;
      highlightedMeshes.set(mesh, mesh.material);
      mesh.material = Array.isArray(mesh.material)
        ? mesh.material.map(tintMaterial)
        : tintMaterial(mesh.material);
    });
  }

  // External selection -> camera zoom+rotate to frame the selected component
  // AND emissive-highlight its mesh so the user can see what's selected.
  // For 3d-source selections we still highlight (visual feedback) but skip
  // camera motion (the user is already looking at what they clicked).
  $effect(() => {
    const s = $selection;
    clearHighlight();
    if (!s || s.kind !== 'component') return;
    if (!camera || !controls || !currentModelGroup) return;
    const comp = $project?.components.find((c) => c.uuid === s.uuid);
    if (!comp) return;
    const mesh = refdesToMesh.get(comp.refdes);
    if (!mesh) return;

    applyHighlight(mesh);

    if (s.source === '3d') return; // already looking at it

    // World-space bbox of the selected mesh for the framing pass.
    const box = new THREE.Box3().setFromObject(mesh);
    if (box.isEmpty()) return;
    const side: 'top' | 'bottom' = comp.side === 'bottom' ? 'bottom' : 'top';
    untrack(() => {
      if (!controls || !camera || !currentModelGroup) return;
      const sceneBox = new THREE.Box3().setFromObject(currentModelGroup);
      const sceneSize = sceneBox.getSize(new THREE.Vector3());
      const sceneMaxDim = Math.max(sceneSize.x, sceneSize.y, sceneSize.z) || 1;
      const frame = computeComponentFrame(box.min, box.max, camera.fov, side, sceneMaxDim);
      controls.target.copy(frame.target);
      camera.position.copy(frame.position);
      adjustCameraClipping(sceneBox);
      controls.update();
    });
  });

  let hasModel = $derived(Boolean($project?.glbUrl || $project?.stepUrl));
</script>

<div class="stage" bind:this={host}>
  <canvas bind:this={canvas} onclick={onClick} class:hidden={!hasModel}></canvas>
  {#if hasModel}
    <div class="presets" aria-label="View presets">
      <button type="button" onclick={() => goToPreset('top')}>Top</button>
      <button type="button" onclick={() => goToPreset('bottom')}>Bottom</button>
      <button type="button" onclick={() => goToPreset('iso')}>Iso</button>
    </div>
  {/if}
  {#if $model3dStatus.kind === 'loading'}
    <div class="loading" role="status" aria-live="polite">
      <div class="loading-title">Parsing 3D model…</div>
      <div class="progress" aria-label="Parsing in progress">
        <div class="progress-bar"></div>
      </div>
      <div class="loading-sub">{elapsedSec.toFixed(1)}s elapsed · large STEP files can take 30-60s</div>
    </div>
  {/if}
  {#if $project && !hasModel}
    <div class="empty"
      ondragover={(e) => { e.preventDefault(); }}
      ondrop={onModelDrop}
      role="region"
      aria-label="Drop a 3D model file"
    >
      <p>No 3D asset loaded.</p>
      <p class="dim">
        Drop a <code>.glb</code> (recommended — includes silkscreen, copper, mask; loads instantly)
        or a <code>.step</code>/<code>.stp</code> (solid bodies only; parses client-side in ~30–60s for large boards).
      </p>
      <p class="dim subtle">Generate a rich GLB with:</p>
      <code class="cmd">kicad-cli pcb export glb --include-tracks --include-pads --include-zones --include-silkscreen --include-soldermask --fuse-shapes</code>
      <label class="btn">Pick 3D file
        <input type="file" accept=".glb,.gltf,.step,.stp" hidden onchange={onModelPick} />
      </label>
    </div>
  {/if}
</div>

<style>
  .stage {
    position: relative; width: 100%; height: 100%;
    background: var(--kv-render-bg);
  }
  canvas {
    width: 100%; height: 100%; display: block;
  }
  canvas.hidden { visibility: hidden; }
  .empty {
    position: absolute; inset: 0;
    display: grid; place-items: center; text-align: center;
    color: var(--kv-text);
  }
  .loading {
    position: absolute; inset: 0;
    display: grid; place-items: center; grid-auto-rows: min-content;
    align-content: center; gap: 0.7rem;
    color: var(--kv-text); background: rgba(0, 0, 0, 0.55);
    font-size: 0.9rem;
    pointer-events: none;
  }
  .loading-title { font-weight: 600; }
  .loading-sub { color: var(--kv-text-dim); font-size: 0.75rem; }
  .progress {
    width: 280px; height: 6px; border-radius: 3px;
    background: var(--kv-surface); overflow: hidden;
    border: 1px solid var(--kv-border);
  }
  .progress-bar {
    width: 35%; height: 100%;
    background: linear-gradient(90deg,
      transparent 0%,
      var(--kv-accent, #6aa6ff) 25%,
      var(--kv-accent, #6aa6ff) 75%,
      transparent 100%);
    animation: shimmer 1.3s ease-in-out infinite;
  }
  @keyframes shimmer {
    from { transform: translateX(-100%); }
    to   { transform: translateX(340%); }
  }
  .subtle { font-size: 0.7rem; opacity: 0.7; margin-top: 0.3rem; }
  .cmd {
    display: block; margin-top: 0.4rem;
    padding: 0.4rem 0.7rem; border-radius: 6px;
    background: var(--kv-surface); color: var(--kv-text-dim);
    font-size: 0.65rem; white-space: nowrap;
    max-width: min(90vw, 560px); overflow-x: auto;
  }
  .dim { color: var(--kv-text-dim); font-size: 0.85rem; }
  .btn {
    display: inline-block; margin-top: 0.75rem;
    padding: 0.5rem 0.9rem; border: 1px solid var(--kv-border);
    border-radius: 8px; background: var(--kv-surface); color: var(--kv-text);
    cursor: pointer; font-size: 0.85rem;
  }
  .presets {
    position: absolute; top: 10px; right: 10px;
    display: flex; gap: 4px;
    background: rgba(0, 0, 0, 0.4);
    border: 1px solid var(--kv-border);
    border-radius: 6px;
    padding: 2px;
  }
  .presets button {
    background: transparent; border: none;
    padding: 4px 10px; font-size: 0.75rem;
    color: #fff; cursor: pointer;
    border-radius: 4px;
  }
  .presets button:hover { background: var(--kv-surface-2); }
</style>
