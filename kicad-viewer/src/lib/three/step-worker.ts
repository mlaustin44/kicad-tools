/// <reference lib="webworker" />
// Parses STEP files off the main thread. occt-import-js is ~8MB of WASM and
// a 17MB populated-board STEP takes tens of seconds to tessellate — running
// it in-page would (and did) lock up the whole app.

import occtimportjs from 'occt-import-js';
import wasmUrl from 'occt-import-js/dist/occt-import-js.wasm?url';

type OcctModule = Awaited<ReturnType<typeof occtimportjs>>;

let occtPromise: Promise<OcctModule> | null = null;

interface ParseRequest {
  id: number;
  buffer: ArrayBuffer;
}
interface ParseResponse {
  id: number;
  ok: boolean;
  error?: string;
  result?: unknown;
}

self.onmessage = async (ev: MessageEvent<ParseRequest>) => {
  const { id, buffer } = ev.data;
  try {
    if (!occtPromise) {
      occtPromise = occtimportjs({
        locateFile: (path: string) => (path.endsWith('.wasm') ? wasmUrl : path)
      });
    }
    const occt = await occtPromise;
    const result = occt.ReadStepFile(new Uint8Array(buffer), null);
    const response: ParseResponse = { id, ok: true, result };
    (self as unknown as Worker).postMessage(response);
  } catch (e) {
    const response: ParseResponse = { id, ok: false, error: e instanceof Error ? e.message : String(e) };
    (self as unknown as Worker).postMessage(response);
  }
};
