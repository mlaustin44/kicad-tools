import { unzip } from 'fflate';
import { classifyFiles, type ProjectBlob } from './blob';

export async function loadFromZipBytes(bytes: Uint8Array): Promise<ProjectBlob> {
  const unpacked: Record<string, string | Uint8Array> = await new Promise((resolve, reject) => {
    unzip(bytes, (err, data) => {
      if (err) return reject(err);
      const out: Record<string, string | Uint8Array> = {};
      for (const [k, v] of Object.entries(data)) {
        if (/\.(kicad_[a-z]+|json)$/i.test(k)) {
          out[k] = new TextDecoder().decode(v);
        } else {
          out[k] = v;
        }
      }
      resolve(out);
    });
  });
  return classifyFiles(unpacked);
}

export async function loadFromZipFile(file: File): Promise<ProjectBlob> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  return loadFromZipBytes(bytes);
}
