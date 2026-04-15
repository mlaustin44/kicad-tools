<script lang="ts">
  import { selection } from '$lib/stores/selection';
  import { componentsByUuid, sheetsByUuid, netsByName } from '$lib/stores/project';
</script>

{#if !$selection}
  <p class="empty">Select a component or net</p>
{:else if $selection.kind === 'component'}
  {@const c = $componentsByUuid.get($selection.uuid)}
  {#if c}
    <header class="hdr"><h3>{c.refdes}</h3><span>{c.value}</span></header>
    <dl>
      <dt>Footprint</dt><dd>{c.footprint}</dd>
      {#if c.mpn}<dt>MPN</dt><dd>{c.mpn}</dd>{/if}
      {#if c.manufacturer}<dt>Mfr</dt><dd>{c.manufacturer}</dd>{/if}
      {#if c.datasheet}<dt>Datasheet</dt><dd><a href={c.datasheet} target="_blank" rel="noopener">link</a></dd>{/if}
      <dt>DNP</dt><dd>{c.dnp ? 'yes' : 'no'}</dd>
    </dl>
    {#if c.pins.length}
      <h4>Pins</h4>
      <table>
        <thead><tr><th>#</th><th>Name</th><th>Net</th></tr></thead>
        <tbody>
          {#each c.pins as p}
            <tr><td>{p.number}</td><td>{p.name}</td><td>{p.netName ?? '-'}</td></tr>
          {/each}
        </tbody>
      </table>
    {/if}
  {:else}
    <p class="empty">Component not found</p>
  {/if}
{:else if $selection.kind === 'net'}
  {@const n = $netsByName.get($selection.name)}
  <header class="hdr"><h3>{$selection.name}</h3><span>{n?.refdesPins.length ?? 0} pins</span></header>
  {#if n}
    <ul>
      {#each n.refdesPins as rp}<li>{rp.refdes}.{rp.pin}</li>{/each}
    </ul>
  {/if}
{:else if $selection.kind === 'sheet'}
  {@const s = $sheetsByUuid.get($selection.uuid)}
  <header class="hdr"><h3>{s?.name ?? ''}</h3></header>
  {#if s}<dl><dt>Path</dt><dd>{s.path.join(' / ')}</dd><dt>Components</dt><dd>{s.componentUuids.length}</dd></dl>{/if}
{/if}

<style>
  :global(.side.right) { padding: 0.75rem; font-size: 0.85rem; }
  .empty { color: var(--kv-text-dim); }
  .hdr { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 0.5rem; }
  .hdr h3 { margin: 0; font-size: 1rem; }
  dl { display: grid; grid-template-columns: auto 1fr; gap: 0.25rem 0.75rem; margin: 0 0 0.5rem; }
  dt { color: var(--kv-text-dim); }
  dd { margin: 0; overflow-wrap: anywhere; }
  table { width: 100%; font-size: 0.78rem; border-collapse: collapse; }
  th, td { text-align: left; padding: 2px 4px; border-bottom: 1px solid var(--kv-border); }
</style>
