<script lang="ts">
  import { project } from '$lib/stores/project';
  import { selection, selectNet } from '$lib/stores/selection';
  import type { Net } from '$lib/model/project';
  import { isPowerRail } from './panel-grouping';

  let query = $state('');
  let collapsed = $state(new Set<string>());

  function toggle(label: string) {
    const next = new Set(collapsed);
    if (next.has(label)) next.delete(label);
    else next.add(label);
    collapsed = next;
  }

  const groups = $derived.by<Array<{ label: string; items: Net[] }>>(() => {
    const p = $project;
    if (!p) return [];
    const q = query.trim().toUpperCase();
    const filtered = q
      ? p.nets.filter((n) => n.name.toUpperCase().includes(q))
      : p.nets;
    const power: Net[] = [];
    const signal: Net[] = [];
    for (const n of filtered) {
      (isPowerRail(n.name) ? power : signal).push(n);
    }
    power.sort((a, b) => a.name.localeCompare(b.name));
    signal.sort((a, b) => a.name.localeCompare(b.name));
    const out: Array<{ label: string; items: Net[] }> = [];
    if (power.length) out.push({ label: 'Power', items: power });
    if (signal.length) out.push({ label: 'Signals', items: signal });
    return out;
  });
</script>

<div class="wrap">
  <input class="search" placeholder="Filter..." bind:value={query} />
  <div class="list">
    {#each groups as g (g.label)}
      {@const isCollapsed = collapsed.has(g.label)}
      <button
        class="group-hdr"
        onclick={() => toggle(g.label)}
        aria-expanded={!isCollapsed}
      >
        <span class="chev">{isCollapsed ? '▸' : '▾'}</span>
        <span class="group-name">{g.label}</span>
        <span class="count">{g.items.length}</span>
      </button>
      {#if !isCollapsed}
        {#each g.items as n (n.name)}
          <button
            class="item"
            class:active={$selection?.kind === 'net' && $selection.name === n.name}
            onclick={() => selectNet({ name: n.name, source: 'search' })}
          >{n.name}</button>
        {/each}
      {/if}
    {/each}
  </div>
</div>

<style>
  .wrap { font-size: 0.78rem; display: grid; grid-template-rows: auto 1fr; min-height: 0; height: 100%; }
  .search {
    margin: 0.5rem 0.75rem 0.25rem; padding: 4px 6px;
    font-size: 0.78rem; border: 1px solid var(--kv-border); border-radius: 4px;
    background: var(--kv-bg); color: var(--kv-text);
  }
  .list { overflow: auto; min-height: 0; }
  .group-hdr {
    display: flex; align-items: center; gap: 0.35rem;
    width: 100%; text-align: left; background: transparent;
    border: none; padding: 5px 10px;
    color: var(--kv-text-dim);
    font-size: 0.7rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.06em;
    cursor: pointer;
    border-top: 1px solid var(--kv-border);
  }
  .group-hdr:hover { background: var(--kv-surface-2); }
  .chev { font-size: 0.65rem; color: var(--kv-text-dim); width: 0.8rem; display: inline-block; }
  .group-name { flex: 1; }
  .count { color: var(--kv-text-dim); font-weight: 400; font-size: 0.7rem; }
  .item {
    display: block; width: 100%; text-align: left; background: transparent;
    border: none; padding: 3px 10px 3px 24px;
    color: var(--kv-text); font-size: 0.78rem; font-family: var(--kv-font-mono);
    cursor: pointer;
  }
  .item.active { background: var(--kv-surface-2); color: var(--kv-accent); }
  .item:hover:not(.active) { background: var(--kv-surface-2); }
</style>
