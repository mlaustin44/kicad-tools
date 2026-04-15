<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import * as THREE from 'three';
  import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
  import { project, setProjectGlbUrl } from '$lib/stores/project';
  import { selection, selectComponent } from '$lib/stores/selection';
  import { theme } from '$lib/stores/theme';
  import { loadGlb, indexByRefdes } from '$lib/three/loader';
  import { pushToast } from '$lib/stores/toasts';

  let host: HTMLDivElement | undefined = $state();
  let canvas: HTMLCanvasElement | undefined = $state();

  let refdesToMesh: Map<string, THREE.Object3D> = new Map();
  let currentGlbUrl: string | null = null;
  let currentGlbGroup: THREE.Group | null = null;

  let scene: THREE.Scene | null = null;
  let camera: THREE.PerspectiveCamera | null = null;
  let renderer: THREE.WebGLRenderer | null = null;
  let controls: OrbitControls | null = null;
  const raycaster = new THREE.Raycaster();

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

  // Load / swap GLB when the project's glbUrl changes
  $effect(() => {
    if (!scene) return;
    const url = $project?.glbUrl ?? null;
    if (url === currentGlbUrl) return;
    currentGlbUrl = url;

    // Remove previous
    if (currentGlbGroup) {
      scene.remove(currentGlbGroup);
      currentGlbGroup.traverse((o) => {
        const mesh = o as THREE.Mesh;
        if (mesh.geometry) mesh.geometry.dispose();
      });
      currentGlbGroup = null;
      refdesToMesh = new Map();
    }

    if (!url) return;

    loadGlb(url).then((group) => {
      if (currentGlbUrl !== url) return;  // superseded by another project change
      if (!scene) return;
      group.userData['isGlbBoard'] = true;
      scene.add(group);
      currentGlbGroup = group;
      refdesToMesh = indexByRefdes(group);

      // Auto-frame: center camera on bounding box
      const box = new THREE.Box3().setFromObject(group);
      if (!box.isEmpty() && camera && controls) {
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        controls.target.copy(center);
        const maxDim = Math.max(size.x, size.y, size.z);
        const dist = maxDim * 2;
        camera.position.copy(center).add(new THREE.Vector3(dist, dist, dist));
        camera.lookAt(center);
        controls.update();
      }
    }).catch((e: unknown) => {
      const msg = e instanceof Error ? e.message : String(e);
      pushToast({ kind: 'error', message: `Couldn't load 3D model: ${msg}` });
    });
  });

  // Raycast -> selection on click
  function onClick(ev: MouseEvent): void {
    if (!camera || !canvas || !scene || !currentGlbGroup) return;
    const rect = canvas.getBoundingClientRect();
    const x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
    const y = -(((ev.clientY - rect.top) / rect.height) * 2 - 1);
    raycaster.setFromCamera(new THREE.Vector2(x, y), camera);
    const picks = raycaster.intersectObject(currentGlbGroup, true);
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
  }

  async function ingestGlbFile(f: File): Promise<void> {
    if (!/\.glb$/i.test(f.name)) {
      pushToast({ kind: 'error', message: '3D: expected a .glb file' });
      return;
    }
    const url = URL.createObjectURL(f);
    setProjectGlbUrl(url);
  }

  function onGlbDrop(ev: DragEvent): void {
    ev.preventDefault();
    const f = ev.dataTransfer?.files?.[0];
    if (f) void ingestGlbFile(f);
  }

  function onGlbPick(ev: Event): void {
    const t = ev.target as HTMLInputElement;
    const f = t.files?.[0];
    if (f) void ingestGlbFile(f);
  }

  // External selection -> camera pan to mesh
  $effect(() => {
    const s = $selection;
    if (!s || s.kind !== 'component' || s.source === '3d') return;
    if (!camera || !controls) return;
    const comp = $project?.components.find((c) => c.uuid === s.uuid);
    if (!comp) return;
    const mesh = refdesToMesh.get(comp.refdes);
    if (!mesh) return;
    const target = new THREE.Vector3();
    mesh.getWorldPosition(target);
    untrack(() => {
      controls!.target.copy(target);
      // Keep the existing camera direction; OrbitControls will redraw.
    });
  });
</script>

<div class="stage" bind:this={host}>
  <canvas bind:this={canvas} onclick={onClick} class:hidden={!$project?.glbUrl}></canvas>
  {#if $project && !$project.glbUrl}
    <div class="empty"
      ondragover={(e) => { e.preventDefault(); }}
      ondrop={onGlbDrop}
      role="region"
      aria-label="Drop a .glb file"
    >
      <p>No 3D asset loaded.</p>
      <p class="dim">Drop a <code>.glb</code> here or include one in your bundle.</p>
      <label class="btn">Pick .glb
        <input type="file" accept=".glb,.gltf" hidden onchange={onGlbPick} />
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
  .dim { color: var(--kv-text-dim); font-size: 0.85rem; }
  .btn {
    display: inline-block; margin-top: 0.75rem;
    padding: 0.5rem 0.9rem; border: 1px solid var(--kv-border);
    border-radius: 8px; background: var(--kv-surface); color: var(--kv-text);
    cursor: pointer; font-size: 0.85rem;
  }
</style>
