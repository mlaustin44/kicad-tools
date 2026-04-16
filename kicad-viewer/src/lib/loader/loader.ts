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
    const arr = Array.from(input as FileList | File[]);
    // Single zip file in a FileList — unpack it rather than treating it as a raw file.
    if (arr.length === 1 && /\.zip$/i.test(arr[0]!.name)) {
      return loadFromZipFile(arr[0]!);
    }
    return loadFromFileList(input as FileList | File[]);
  }
  if (input instanceof File) {
    return loadFromFileList([input]);
  }
  throw new Error('Unsupported input');
}
