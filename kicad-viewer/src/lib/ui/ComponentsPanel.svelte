<script lang="ts">
  import { project } from '$lib/stores/project';
  import { selection, selectComponent } from '$lib/stores/selection';
  import type { Component } from '$lib/model/project';
  import {
    refdesTypeLabel,
    compareRefdes,
    groupOrderIndex
  } from './panel-grouping';

  let query = $state('');
  let collapsed = $state(new Set<string>());

  function toggle(label: string) {
    const next = new Set(collapsed);
    if (next.has(label)) next.delete(label);
    else next.add(label);
    collapsed = next;
  }

  const groups = $derived.by<Array<{ label: string; items: Component[] }>>(() => {
    const p = $project;
    if (!p) return [];
    const q = query.trim().toUpperCase();
    const filtered = q
      ? p.components.filter(
          (c) => c.refdes.toUpperCase().includes(q) || c.value.toUpperCase().includes(q)
        )
      : p.components;
    const by = new Map<string, Component[]>();
    for (const c of filtered) {
      const label = refdesTypeLabel(c.refdes);
      const arr = by.get(label) ?? [];
      arr.push(c);
      by.set(label, arr);
    }
    const out: Array<{ label: string; items: Component[] }> = [];
    for (const [label, items] of by) {
      items.sort((a, b) => compareRefdes(a.refdes, b.refdes));
      out.push({ label, items });
    }
    out.sort((a, b) => {
      const ai = groupOrderIndex(a.label);
      const bi = groupOrderIndex(b.label);
      if (ai !== bi) return ai - bi;
      return a.label.localeCompare(b.label);
    });
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
        {#each g.items as c (c.uuid)}
          <button
            class="item"
            class:active={$selection?.kind === 'component' && $selection.uuid === c.uuid}
            onclick={() => selectComponent({ uuid: c.uuid, source: 'search' })}
          >
            <strong class="refdes">{c.refdes}</strong>
            <span class="value">{c.value}</span>
          </button>
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
    display: grid; grid-template-columns: auto 1fr;
    gap: 0.5rem; align-items: baseline;
    width: 100%; text-align: left; background: transparent;
    border: none; padding: 3px 10px 3px 24px;
    color: var(--kv-text); font-size: 0.78rem;
    cursor: pointer;
  }
  .item.active { background: var(--kv-surface-2); color: var(--kv-accent); }
  .item:hover:not(.active) { background: var(--kv-surface-2); }
  .refdes { font-family: var(--kv-font-mono); min-width: 2.5rem; }
  .value { color: var(--kv-text-dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
