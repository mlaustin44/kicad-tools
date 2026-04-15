import { loadFromZipFile } from './zip';
import { loadFromFileList, loadFromDirectoryHandle } from './folder';
import type { ProjectBlob } from './blob';

export async function loadProject(
  input: File | FileList | File[] | FileSystemDirectoryHandle
): Promise<ProjectBlob> {
  if (typeof (input as FileSystemDirectoryHandle).getDirectoryHandle === 'function') {
    return loadFromDirectoryHandle(input as FileSystemDirectoryHandle);
  }
  if (input instanceof File && /\.zip$/i.test(input.name)) {
    return loadFromZipFile(input);
  }
  if (input instanceof FileList || Array.isArray(input)) {
    return loadFromFileList(input as FileList | File[]);
  }
  if (input instanceof File) {
    return loadFromFileList([input]);
  }
  throw new Error('Unsupported input');
}
