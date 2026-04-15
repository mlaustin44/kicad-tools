<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import * as THREE from 'three';
  import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
  import { project, setProjectGlbUrl, setProjectStepUrl } from '$lib/stores/project';
  import { selection, selectComponent, clearSelection } from '$lib/stores/selection';
  import { theme } from '$lib/stores/theme';
  import { loadGlb, indexByRefdes } from '$lib/three/loader';
  import { loadStep } from '$lib/three/step-loader';
  import { computeComponentFrame } from '$lib/three/camera-framing';
  import { pushToast } from '$lib/stores/toasts';

  type PresetView = 'top' | 'bottom' | 'iso';

  interface Props {
    fitRequested?: number;
    presetRequested?: PresetView | null;
  }
  let { fitRequested = 0, presetRequested = null }: Props = $props();

  let host: HTMLDivElement | undefined = $state();
  let canvas: HTMLCanvasElement | undefined = $state();

  let refdesToMesh: Map<string, THREE.Object3D> = new Map();
  // Tracks whichever model is currently on screen (GLB or STEP). Keeping it
  // uniform lets cross-probe / click-hit / framing stay format-agnostic.
  let currentModelUrl: string | null = null;
  let currentModelGroup: THREE.Group | null = null;
  let loading = $state(false);

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

  function frameWhole(): void {
    if (!currentModelGroup || !camera || !controls) return;
    const box = new THREE.Box3().setFromObject(currentModelGroup);
    if (box.isEmpty()) return;
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

    renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);

    controls = new OrbitControls(camera, canvas);
    controls.enableDamping = true;

    scene.add(new THREE.AmbientLight(0xffffff, 0.5));
    const dir = new THREE.DirectionalLight(0xffffff, 1.0);
    dir.position.set(100, 200, 100);
    scene.add(dir);

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

  function disposeCurrentModel(): void {
    if (!currentModelGroup || !scene) return;
    scene.remove(currentModelGroup);
    currentModelGroup.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (mesh.geometry) mesh.geometry.dispose();
      const mat = mesh.material;
      if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
      else if (mat) mat.dispose();
    });
    currentModelGroup = null;
    refdesToMesh = new Map();
  }

  // Load / swap 3D model when the project's stepUrl or glbUrl changes. STEP
  // takes precedence when both are present (higher-fidelity CAD geometry).
  $effect(() => {
    if (!scene) return;
    const stepUrl = $project?.stepUrl ?? null;
    const glbUrl = $project?.glbUrl ?? null;
    const kind: 'step' | 'glb' | null = stepUrl ? 'step' : glbUrl ? 'glb' : null;
    const url = stepUrl ?? glbUrl ?? null;

    if (url === currentModelUrl) return;
    currentModelUrl = url;
    disposeCurrentModel();

    if (!url || !kind) return;

    loading = true;
    const loadPromise = kind === 'step'
      ? fetch(url).then((r) => r.arrayBuffer()).then((b) => loadStep(new Uint8Array(b)))
      : loadGlb(url);

    loadPromise
      .then((group) => {
        if (currentModelUrl !== url) return; // superseded
        if (!scene) return;
        scene.add(group);
        currentModelGroup = group;
        refdesToMesh = indexByRefdes(group);
        frameWhole();
      })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : String(e);
        pushToast({ kind: 'error', message: `Couldn't load 3D model: ${msg}` });
      })
      .finally(() => { loading = false; });
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
        const match = o.name?.match(/^([A-Z]+\d+)/);
        if (match) {
          const refdes = match[1];
          if (refdes) {
            const comp = $project?.components.find((c) => c.refdes === refdes);
            if (comp) {
              selectComponent({ uuid: comp.uuid, source: '3d' });
              return;
            }
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
    const url = URL.createObjectURL(f);
    if (isStep) setProjectStepUrl(url);
    else setProjectGlbUrl(url);
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

  // External selection -> camera zoom+rotate to frame the selected component
  // (using its footprint side so bottom-side parts aren't hidden behind the
  // board). Tiny parts are padded to a minimum context so we don't end up
  // nose-against-silkscreen.
  $effect(() => {
    const s = $selection;
    if (!s || s.kind !== 'component' || s.source === '3d') return;
    if (!camera || !controls || !currentModelGroup) return;
    const comp = $project?.components.find((c) => c.uuid === s.uuid);
    if (!comp) return;
    const mesh = refdesToMesh.get(comp.refdes);
    if (!mesh) return;

    // World-space bbox of the selected mesh.
    const box = new THREE.Box3().setFromObject(mesh);
    if (box.isEmpty()) return;

    // Default to top if we don't know the side (best-effort).
    const side: 'top' | 'bottom' = comp.side === 'bottom' ? 'bottom' : 'top';

    untrack(() => {
      if (!controls || !camera) return;
      const frame = computeComponentFrame(box.min, box.max, camera.fov, side);
      controls.target.copy(frame.target);
      camera.position.copy(frame.position);
      camera.lookAt(frame.target);
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
  {#if loading}
    <div class="loading">Loading 3D model…</div>
  {/if}
  {#if $project && !hasModel}
    <div class="empty"
      ondragover={(e) => { e.preventDefault(); }}
      ondrop={onModelDrop}
      role="region"
      aria-label="Drop a 3D model file"
    >
      <p>No 3D asset loaded.</p>
      <p class="dim">Drop a <code>.step</code>, <code>.stp</code>, or <code>.glb</code> here, or include one with your project bundle.</p>
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
    display: grid; place-items: center;
    color: var(--kv-text); background: rgba(0, 0, 0, 0.4);
    font-size: 0.85rem;
    pointer-events: none;
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
    color: var(--kv-text); cursor: pointer;
    border-radius: 4px;
  }
  .presets button:hover { background: var(--kv-surface-2); }
</style>
