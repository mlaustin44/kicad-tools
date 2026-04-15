<script lang="ts">
  import { layers, layerVisibility, toggleLayer, activeLayer, setActiveLayer } from '$lib/stores/layers';
</script>

<div class="wrap" id="layer-panel">
  <h4>Layers</h4>
  {#each $layers as l (l.id)}
    <div
      class="row"
      class:active={$activeLayer === l.id}
      data-layer-id={l.id}
      role="button"
      tabindex="0"
      onclick={() => setActiveLayer(l.id)}
      onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setActiveLayer(l.id); } }}
    >
      <input
        type="checkbox"
        checked={$layerVisibility.get(l.id) ?? false}
        onchange={() => toggleLayer(l.id)}
        onclick={(e) => e.stopPropagation()}
        aria-label={`Toggle ${l.name} visibility`}
      />
      <span class="sw" style="background: {l.defaultColor}"></span>
      <span class="name">{l.name}</span>
    </div>
  {/each}
</div>

<style>
  .wrap { font-size: 0.78rem; }
  h4 {
    font-size: 0.7rem; letter-spacing: 0.08em; color: var(--kv-text-dim);
    margin: 0.5rem 0.75rem; text-transform: uppercase;
  }
  .row {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 3px 10px; cursor: pointer; user-select: none;
    border-left: 3px solid transparent;
  }
  .row:hover { background: var(--kv-surface-2); }
  .row.active {
    background: var(--kv-surface-2);
    border-left-color: var(--kv-accent, #6aa6ff);
  }
  .row.active .name { color: var(--kv-accent, #6aa6ff); font-weight: 600; }
  .sw { width: 10px; height: 10px; border-radius: 2px; border: 1px solid var(--kv-border); }
  .name { flex: 1; }
</style>
