// Minimal IndexedDB wrapper for persisting the last loaded project's raw files.
// Falls back silently if IDB is unavailable (private mode, quota denied).

const DB_NAME = 'kv-recent';
const STORE = 'projects';
const VERSION = 1;

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') return reject(new Error('no idb'));
    const req = indexedDB.open(DB_NAME, VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'id' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('idb open failed'));
  });
}

export interface RecentRecord {
  id: 'last';
  files: Record<string, string | Uint8Array>;
  savedAt: number;
}

export async function saveRecent(files: Record<string, string | Uint8Array>): Promise<void> {
  try {
    const db = await open();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).put({ id: 'last', files, savedAt: Date.now() } satisfies RecentRecord);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error ?? new Error('idb write failed'));
      tx.onabort = () => reject(tx.error ?? new Error('idb write aborted'));
    });
    db.close();
  } catch {
    // Private-mode / quota exceeded / feature disabled — silently ignore persistence.
  }
}

export async function loadRecent(): Promise<Record<string, string | Uint8Array> | null> {
  try {
    const db = await open();
    const result = await new Promise<RecentRecord | undefined>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly');
      const req = tx.objectStore(STORE).get('last');
      req.onsuccess = () => resolve(req.result as RecentRecord | undefined);
      req.onerror = () => reject(req.error ?? new Error('idb read failed'));
    });
    db.close();
    return result?.files ?? null;
  } catch {
    return null;
  }
}

export async function clearRecent(): Promise<void> {
  try {
    const db = await open();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).delete('last');
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error ?? new Error('idb delete failed'));
    });
    db.close();
  } catch {
    // ignore
  }
}
