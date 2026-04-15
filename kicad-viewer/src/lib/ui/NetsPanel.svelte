<script lang="ts">
  import { project } from '$lib/stores/project';
  import { selection, selectNet } from '$lib/stores/selection';

  let query = $state('');
  let nets = $derived.by(() => {
    const p = $project;
    if (!p) return [];
    const q = query.trim().toUpperCase();
    const list = q
      ? p.nets.filter((n) => n.name.toUpperCase().includes(q))
      : p.nets.slice();
    return list.slice(0, 200);
  });
</script>

<div class="wrap">
  <h4>Nets</h4>
  <input class="search" placeholder="Filter..." bind:value={query} />
  <div class="list">
    {#each nets as n (n.name)}
      <button
        class:active={$selection?.kind === 'net' && $selection.name === n.name}
        onclick={() => selectNet({ name: n.name, source: 'search' })}
      >{n.name}</button>
    {/each}
  </div>
</div>

<style>
  .wrap { font-size: 0.78rem; display: grid; grid-template-rows: auto auto 1fr; min-height: 0; }
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
    font-family: var(--kv-font-mono);
  }
  button.active { background: var(--kv-surface-2); color: var(--kv-accent); }
  button:hover:not(.active) { background: var(--kv-surface-2); }
</style>
