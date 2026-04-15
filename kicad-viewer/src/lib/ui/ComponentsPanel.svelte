<script lang="ts">
  import { project } from '$lib/stores/project';
  import { selection, selectComponent } from '$lib/stores/selection';

  let query = $state('');
  let comps = $derived.by(() => {
    const p = $project;
    if (!p) return [];
    const q = query.trim().toUpperCase();
    const list = q
      ? p.components.filter((c) => c.refdes.toUpperCase().includes(q) || c.value.toUpperCase().includes(q))
      : p.components.slice();
    return list.slice(0, 200);
  });
</script>

<div class="wrap">
  <h4>Components</h4>
  <input class="search" placeholder="Filter..." bind:value={query} />
  <div class="list">
    {#each comps as c (c.uuid)}
      <button
        class:active={$selection?.kind === 'component' && $selection.uuid === c.uuid}
        onclick={() => selectComponent({ uuid: c.uuid, source: 'search' })}
      ><strong>{c.refdes}</strong> <span class="dim">{c.value}</span></button>
    {/each}
  </div>
</div>

<style>
  .wrap { font-size: 0.78rem; display: grid; grid-template-rows: auto auto 1fr; min-height: 0; height: 100%; }
  h4 { font-size: 0.7rem; letter-spacing: 0.08em; color: var(--kv-text-dim);
       margin: 0.5rem 0.75rem; text-transform: uppercase; }
  .search {
    margin: 0 0.75rem 0.25rem; padding: 4px 6px;
    font-size: 0.78rem; border: 1px solid var(--kv-border); border-radius: 4px;
    background: var(--kv-bg); color: var(--kv-text);
  }
  .list { overflow: auto; min-height: 0; }
  button {
    display: block; width: 100%; text-align: left; background: transparent;
    border: none; padding: 3px 10px; color: var(--kv-text); font-size: 0.78rem;
  }
  button.active { background: var(--kv-surface-2); color: var(--kv-accent); }
  button:hover:not(.active) { background: var(--kv-surface-2); }
  .dim { color: var(--kv-text-dim); }
</style>
