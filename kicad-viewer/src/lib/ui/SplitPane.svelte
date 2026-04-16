<script lang="ts">
  import type { Snippet } from 'svelte';
  import { untrack } from 'svelte';
  interface Props { left: Snippet; right: Snippet; initial?: number; }
  let { left, right, initial = 0.5 }: Props = $props();

  let ratio = $state(untrack(() => initial));
  let host: HTMLDivElement | undefined = $state();
  let dragging = $state(false);

  function onDown(): void { dragging = true; }
  function onMove(e: PointerEvent): void {
    if (!dragging || !host) return;
    const r = host.getBoundingClientRect();
    const raw = (e.clientX - r.left) / r.width;
    ratio = Math.max(0.1, Math.min(0.9, raw));
  }
  function onUp(): void { dragging = false; }
  function onKey(e: KeyboardEvent): void {
    const step = e.shiftKey ? 0.1 : 0.05;
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      ratio = Math.max(0.1, ratio - step);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      ratio = Math.min(0.9, ratio + step);
    }
  }
</script>

<svelte:window onpointermove={onMove} onpointerup={onUp} />

<div class="split" bind:this={host}>
  <div class="pane" style="flex: {ratio};">{@render left()}</div>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="gutter"
    role="separator"
    tabindex="0"
    aria-label="Resize panes"
    aria-valuenow={Math.round(ratio * 100)}
    aria-valuemin="10"
    aria-valuemax="90"
    aria-orientation="vertical"
    onpointerdown={onDown}
    onkeydown={onKey}
  ></div>
  <div class="pane" style="flex: {1 - ratio};">{@render right()}</div>
</div>

<style>
  .split { display: flex; height: 100%; width: 100%; }
  .pane { min-width: 0; min-height: 0; overflow: hidden; }
  .gutter {
    width: 6px;
    background: var(--kv-border);
    cursor: col-resize;
    border: none;
    padding: 0;
    touch-action: none;
  }
  .gutter:hover { background: var(--kv-accent); }
</style>
