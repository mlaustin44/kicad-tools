<script lang="ts">
  import { project, sheetsByUuid } from '$lib/stores/project';
  import { selectComponent, selection } from '$lib/stores/selection';
  import { buildSheetSvg } from '$lib/sch/render';
  import Breadcrumb from '$lib/ui/Breadcrumb.svelte';

  interface Props {
    activeSheetUuid: string | null;
    onNavigateSheet?: (uuid: string) => void;
  }
  let { activeSheetUuid, onNavigateSheet }: Props = $props();

  let activeSheet = $derived($sheetsByUuid.get(activeSheetUuid ?? '') ?? null);

  let viewport = $state({ x: 0, y: 0, scale: 1 });
  let host: HTMLDivElement | undefined = $state();

  function onWheel(e: WheelEvent) {
    e.preventDefault();
    if (!host) return;
    const delta = -e.deltaY * 0.001;
    const factor = Math.exp(delta);
    const rect = host.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    viewport = {
      x: mx - (mx - viewport.x) * factor,
      y: my - (my - viewport.y) * factor,
      scale: viewport.scale * factor
    };
  }

  let dragging = false, lastX = 0, lastY = 0;

  function onDown(e: PointerEvent) {
    if (e.button !== 0) return;
    const t = e.target as Element;
    if (t.closest('[data-refdes]')) return;  // clicks on symbols select, not pan
    dragging = true;
    lastX = e.clientX; lastY = e.clientY;
    host?.setPointerCapture(e.pointerId);
  }

  function onMove(e: PointerEvent) {
    if (!dragging) return;
    viewport = { ...viewport, x: viewport.x + (e.clientX - lastX), y: viewport.y + (e.clientY - lastY) };
    lastX = e.clientX; lastY = e.clientY;
  }

  function onUp() { dragging = false; }

  function onClick(e: MouseEvent) {
    const g = (e.target as Element).closest('[data-refdes]');
    if (!g) return;
    const uuid = g.getAttribute('data-uuid');
    if (uuid) selectComponent({ uuid, source: 'sch' });
  }

  function onDblClick(e: MouseEvent) {
    const sg = (e.target as Element).closest('[data-sheet-uuid]');
    if (!sg) return;
    const uuid = sg.getAttribute('data-sheet-uuid');
    if (uuid) onNavigateSheet?.(uuid);
  }

  let svg = $derived.by(() => {
    if (!$project || !activeSheetUuid) return '';
    const s = $sheetsByUuid.get(activeSheetUuid);
    return s ? buildSheetSvg($project, s) : '';
  });

  let highlightedRefdes = $derived.by(() => {
    if ($selection?.kind !== 'component') return null;
    const c = $project?.components.find((c) => c.uuid === $selection.uuid);
    return c?.refdes ?? null;
  });
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div
  class="stage schematic-stage"
  bind:this={host}
  onwheel={onWheel}
  onpointerdown={onDown}
  onpointermove={onMove}
  onpointerup={onUp}
  onclick={onClick}
  ondblclick={onDblClick}
  role="img"
  aria-label="Schematic view"
>
  <div class="svg" style="transform: translate({viewport.x}px, {viewport.y}px) scale({viewport.scale});">
    {@html svg}
  </div>
  {#if highlightedRefdes}
    {@html `<style>.schematic-stage [data-refdes="${CSS.escape(highlightedRefdes)}"] rect { stroke: var(--kv-accent); stroke-width: 0.8; }</style>`}
  {/if}
  {#if activeSheet}
    <Breadcrumb sheet={activeSheet} />
  {/if}
</div>

<style>
  .stage {
    position: relative; overflow: hidden;
    width: 100%; height: 100%;
    background: var(--kv-render-bg);
    cursor: grab; touch-action: none;
  }
  .svg {
    position: absolute; top: 0; left: 0;
    transform-origin: 0 0;
    width: 800px; height: 600px;
  }
</style>
