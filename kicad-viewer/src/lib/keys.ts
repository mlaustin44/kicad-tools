import { clearSelection } from '$lib/stores/selection';

export function installKeyboardShortcuts(args: {
  setTab: (t: string) => void;
  onSearch: () => void;
  onFit: () => void;
  onPrevSheet: () => void;
  onNextSheet: () => void;
  onFocusLayers: () => void;
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
      case 'f': args.onFit(); break;
      case '[': args.onPrevSheet(); break;
      case ']': args.onNextSheet(); break;
      case 'l': args.onFocusLayers(); break;
    }
  };
  window.addEventListener('keydown', handler);
  return () => window.removeEventListener('keydown', handler);
}
