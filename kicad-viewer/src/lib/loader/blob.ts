export interface ProjectBlob {
  files: Record<string, string | Uint8Array>;
  kicadPro: string | null;
  kicadPcb: string | null;
  schematics: string[];
  glb: string | null;
  manifest: BundleManifest | null;
}

export interface BundleManifest {
  name: string;
  version: string;
  files: { pcb: string; sch: string[]; glb?: string };
  generated_by?: string;
}

export function classifyFiles(files: Record<string, string | Uint8Array>): ProjectBlob {
  let kicadPro: string | null = null;
  let kicadPcb: string | null = null;
  const schematics: string[] = [];
  let glb: string | null = null;
  let manifest: BundleManifest | null = null;

  for (const name of Object.keys(files)) {
    const lower = name.toLowerCase();
    if (lower.endsWith('.kicad_pro')) kicadPro = name;
    else if (lower.endsWith('.kicad_pcb')) kicadPcb = name;
    else if (lower.endsWith('.kicad_sch')) schematics.push(name);
    else if (lower.endsWith('.glb')) glb = name;
    else if (lower === 'manifest.json') {
      const raw = files[name];
      const text = typeof raw === 'string' ? raw : new TextDecoder().decode(raw);
      manifest = JSON.parse(text);
    }
  }
  return { files, kicadPro, kicadPcb, schematics, glb, manifest };
}

export function rootSchematic(blob: ProjectBlob): string | null {
  if (blob.manifest?.files?.sch?.[0]) return blob.manifest.files.sch[0];
  if (blob.schematics.length === 0) return null;
  if (blob.kicadPro) {
    const stem = blob.kicadPro.replace(/\.kicad_pro$/i, '');
    const match = blob.schematics.find((s) => s.startsWith(stem + '.'));
    if (match) return match;
  }
  return blob.schematics[0] ?? null;
}
