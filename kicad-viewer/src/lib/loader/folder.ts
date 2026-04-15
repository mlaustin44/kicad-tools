import { classifyFiles, type ProjectBlob } from './blob';

export async function loadFromFileList(files: FileList | File[]): Promise<ProjectBlob> {
  const map: Record<string, string | Uint8Array> = {};
  for (const f of Array.from(files)) {
    const isText = /\.(kicad_[a-z]+|json)$/i.test(f.name);
    map[f.name] = isText ? await f.text() : new Uint8Array(await f.arrayBuffer());
  }
  return classifyFiles(map);
}

export async function loadFromDirectoryHandle(handle: FileSystemDirectoryHandle): Promise<ProjectBlob> {
  const map: Record<string, string | Uint8Array> = {};
  await walk(handle, '', map);
  return classifyFiles(map);
}

async function walk(
  dir: FileSystemDirectoryHandle,
  prefix: string,
  into: Record<string, string | Uint8Array>
) {
  const entries = (
    dir as unknown as { entries(): AsyncIterable<[string, FileSystemHandle]> }
  ).entries();
  for await (const [name, entry] of entries) {
    const full = prefix ? `${prefix}/${name}` : name;
    if (entry.kind === 'file') {
      const f = await (entry as FileSystemFileHandle).getFile();
      const isText = /\.(kicad_[a-z]+|json)$/i.test(f.name);
      into[full] = isText ? await f.text() : new Uint8Array(await f.arrayBuffer());
    } else if (entry.kind === 'directory') {
      await walk(entry as FileSystemDirectoryHandle, full, into);
    }
  }
}
