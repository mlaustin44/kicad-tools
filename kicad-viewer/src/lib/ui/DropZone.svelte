<script lang="ts">
  import { loadProject } from '$lib/loader/loader';
  import { toProject } from '$lib/adapter/adapter';
  import { setProjectRevokingGlb } from '$lib/stores/project';
  import { rootSchematic } from '$lib/loader/blob';
  import { pushToast } from '$lib/stores/toasts';
  import { saveRecent } from '$lib/stores/recent';

  let dragging = $state(false);

  async function ingest(input: File | FileList | File[] | FileSystemDirectoryHandle) {
    try {
      const blob = await loadProject(input);
      const root = rootSchematic(blob);
      if (!blob.kicadPcb || !root) throw new Error('missing .kicad_pcb or .kicad_sch');
      const schematics: Record<string, string> = {};
      for (const s of blob.schematics) schematics[s] = blob.files[s] as string;
      const pro = blob.kicadPro ? (blob.files[blob.kicadPro] as string) : '{}';
      const pcb = blob.files[blob.kicadPcb] as string;
      const p = toProject({ pro, pcb, schematics, rootSchematic: root });
      if (blob.step) {
        // Prefer STEP when both are present — tessellated client-side from CAD-grade geometry.
        const u8 = blob.files[blob.step] as Uint8Array;
        p.stepUrl = URL.createObjectURL(new Blob([u8 as BlobPart], { type: 'model/step' }));
      } else if (blob.glb) {
        const u8 = blob.files[blob.glb] as Uint8Array;
        p.glbUrl = URL.createObjectURL(new Blob([u8 as BlobPart], { type: 'model/gltf-binary' }));
      }
      if (blob.manifest) p.source = 'bundle';
      setProjectRevokingGlb(p);
      await saveRecent(blob.files);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      pushToast({ kind: 'error', message: `Couldn't load project: ${msg}` });
    }
  }

  async function onDrop(ev: DragEvent) {
    ev.preventDefault();
    dragging = false;
    const files = ev.dataTransfer?.files;
    if (files && files.length) await ingest(files);
  }

  async function onPickFiles(ev: Event) {
    const t = ev.target as HTMLInputElement;
    if (t.files) await ingest(t.files);
  }

  async function onPickFolder() {
    const sdp = (window as unknown as { showDirectoryPicker?: () => Promise<FileSystemDirectoryHandle> }).showDirectoryPicker;
    if (!sdp) {
      pushToast({ kind: 'info', message: 'Folder picker not supported — use the file picker or drop files.' });
      return;
    }
    try {
      const handle = await sdp();
      await ingest(handle);
    } catch {
      /* user cancelled */
    }
  }
</script>

<div
  class="drop"
  class:active={dragging}
  ondragover={(e) => { e.preventDefault(); dragging = true; }}
  ondragleave={() => (dragging = false)}
  ondrop={onDrop}
  role="region"
  aria-label="Drop a KiCad project"
>
  <h2>kicad-viewer</h2>
  <p>Web-based KiCad viewer with Schematic, PCB layout, and 3D viewer. Cross-probe components between views.</p>
  <p>Drop a project folder, <code>.zip</code>, or individual files (<code>.kicad_pro</code>, <code>.kicad_sch</code>, and <code>.kicad_pcb</code>) to get started! Upload a <a href="https://docs.kicad.org/10.0/en/cli/cli.html#pcb_export_glb" target="_blank" rel="noopener"><code>.glb</code></a> file to view and cross-probe in 3D.</p>
  <p class="privacy">Your data lives only in your browser — nothing is saved or uploaded, and the project is fully open-source on <a href="https://github.com/mlaustin44/kicad-tools" target="_blank" rel="noopener">my GitHub</a>.</p>
  <div class="row">
    <label class="btn">Pick files
      <input type="file" multiple hidden onchange={onPickFiles} />
    </label>
    <button class="btn" onclick={onPickFolder}>Pick folder</button>
  </div>
</div>

<style>
  .drop {
    display: grid; place-items: center; text-align: center;
    padding: 3rem; border: 2px dashed var(--kv-border); border-radius: 12px;
    color: var(--kv-text-dim);
  }
  .drop.active { border-color: var(--kv-accent); background: var(--kv-surface-2); }
  .drop a { color: var(--kv-accent); text-decoration: none; }
  .drop a:hover { text-decoration: underline; }
  .privacy { font-size: 0.8rem; opacity: 0.7; margin-top: 0.5rem; }
  .row { display: flex; gap: 0.75rem; margin-top: 0.5rem; }
  .btn {
    padding: 0.5rem 0.9rem; border: 1px solid var(--kv-border);
    border-radius: 8px; background: var(--kv-surface); color: var(--kv-text);
    cursor: pointer;
  }
</style>
