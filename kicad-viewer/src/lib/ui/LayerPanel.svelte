<script lang="ts">
  import { layers, layerVisibility, toggleLayer } from '$lib/stores/layers';
</script>

<div class="wrap">
  <h4>Layers</h4>
  {#each $layers as l (l.id)}
    <label>
      <input
        type="checkbox"
        checked={$layerVisibility.get(l.id) ?? false}
        onchange={() => toggleLayer(l.id)}
      />
      <span class="sw" style="background: {l.defaultColor}"></span>
      <span>{l.name}</span>
    </label>
  {/each}
</div>

<style>
  .wrap { font-size: 0.78rem; }
  h4 {
    font-size: 0.7rem; letter-spacing: 0.08em; color: var(--kv-text-dim);
    margin: 0.5rem 0.75rem; text-transform: uppercase;
  }
  label {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 3px 10px; cursor: pointer; user-select: none;
  }
  label:hover { background: var(--kv-surface-2); }
  .sw { width: 10px; height: 10px; border-radius: 2px; border: 1px solid var(--kv-border); }
</style>
