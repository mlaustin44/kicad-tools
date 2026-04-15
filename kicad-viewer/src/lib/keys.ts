import { clearSelection } from '$lib/stores/selection';

export function installKeyboardShortcuts(args: {
  setTab: (t: string) => void;
  onSearch: () => void;
  onFit: () => void;
  onPan: (dx: number, dy: number) => void;
  onPrevSheet: () => void;
  onNextSheet: () => void;
  onFocusLayers: () => void;
  onPreset: (preset: 'top' | 'bottom' | 'iso') => void;
  onHelp: () => void;
}): () => void {
  const handler = (e: KeyboardEvent) => {
    const target = e.target as HTMLElement;
    if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return;
    switch (e.key) {
      case '1': args.setTab('sch');   break;
      case '2': args.setTab('pcb');   break;
      case '3': args.setTab('3d');    break;
      case '4': args.setTab('split'); break;
      case '/': e.preventDefault(); args.onSearch(); break;
      case 'Escape': clearSelection(); break;
      case 'f':
      case 'Home':
        args.onFit();
        break;
      case 'ArrowLeft':  e.preventDefault(); args.onPan(40, 0); break;
      case 'ArrowRight': e.preventDefault(); args.onPan(-40, 0); break;
      case 'ArrowUp':    e.preventDefault(); args.onPan(0, 40); break;
      case 'ArrowDown':  e.preventDefault(); args.onPan(0, -40); break;
      case '[': args.onPrevSheet(); break;
      case ']': args.onNextSheet(); break;
      case 'l': args.onFocusLayers(); break;
      case 't': args.onPreset('top'); break;
      case 'b': args.onPreset('bottom'); break;
      case 'i': args.onPreset('iso'); break;
      case '?':
      case 'h':
        e.preventDefault();
        args.onHelp();
        break;
    }
  };
  window.addEventListener('keydown', handler);
  return () => window.removeEventListener('keydown', handler);
}
