<script lang="ts">
  import { selection } from '$lib/stores/selection';
  import { componentsByUuid, sheetsByUuid, netsByName } from '$lib/stores/project';

  function isUrl(s: string): boolean {
    return /^(https?:)?\/\//i.test(s) || s.startsWith('/');
  }
</script>

{#if !$selection}
  <p class="empty">Select a component or net</p>
{:else if $selection.kind === 'component'}
  {@const c = $componentsByUuid.get($selection.uuid)}
  {#if c}
    {@const sheet = $sheetsByUuid.get(c.sheetUuid)}
    <header class="hdr">
      <div class="titles">
        <h3>{c.refdes}</h3>
        {#if c.value}<span class="value">{c.value}</span>{/if}
      </div>
      {#if c.dnp}<span class="dnp-pill">DNP</span>{/if}
    </header>

    <dl>
      {#if c.footprint}<dt>Footprint</dt><dd class="mono">{c.footprint}</dd>{/if}
      {#if c.mpn}<dt>MPN</dt><dd class="mono">{c.mpn}</dd>{/if}
      {#if c.manufacturer}<dt>Mfr</dt><dd>{c.manufacturer}</dd>{/if}
      {#if c.datasheet}
        <dt>Datasheet</dt>
        <dd>
          {#if isUrl(c.datasheet)}
            <a href={c.datasheet} target="_blank" rel="noopener">open ↗</a>
          {:else}
            <span class="mono">{c.datasheet}</span>
          {/if}
        </dd>
      {/if}
      {#each Object.entries(c.properties) as [key, val]}
        <dt>{key}</dt>
        <dd>
          {#if isUrl(val)}<a href={val} target="_blank" rel="noopener">{val}</a>
          {:else}{val}{/if}
        </dd>
      {/each}
      {#if sheet}<dt>Sheet</dt><dd>{sheet.path.join(' / ')}</dd>{/if}
      {#if c.positionMm}
        <dt>Position</dt>
        <dd class="mono">
          {c.positionMm.x.toFixed(2)}, {c.positionMm.y.toFixed(2)} mm
          {#if c.rotationDeg !== undefined && c.rotationDeg !== 0}
            @ {c.rotationDeg}°
          {/if}
          {#if c.side === 'bottom'}<span class="side-pill">bottom</span>{/if}
        </dd>
      {/if}
    </dl>

    {#if c.pins.length}
      <h4>Pins <span class="count">({c.pins.length})</span></h4>
      <div class="table-wrap">
        <table>
          <thead><tr><th class="num">#</th><th>Name</th><th>Net</th></tr></thead>
          <tbody>
            {#each c.pins as p}
              <tr>
                <td class="num">{p.number}</td>
                <td>{p.name}</td>
                <td class="mono">{p.netName ?? '—'}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  {:else}
    <p class="empty">Component not found</p>
  {/if}
{:else if $selection.kind === 'net'}
  {@const n = $netsByName.get($selection.name)}
  <header class="hdr">
    <div class="titles"><h3>{$selection.name}</h3></div>
    <span class="count">{n?.refdesPins.length ?? 0} pins</span>
  </header>
  {#if n}
    <div class="table-wrap">
      <table>
        <thead><tr><th>Refdes</th><th>Pin</th></tr></thead>
        <tbody>
          {#each n.refdesPins as rp}
            <tr><td>{rp.refdes}</td><td class="num">{rp.pin}</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
{:else if $selection.kind === 'sheet'}
  {@const s = $sheetsByUuid.get($selection.uuid)}
  <header class="hdr"><div class="titles"><h3>{s?.name ?? ''}</h3></div></header>
  {#if s}
    <dl>
      <dt>Path</dt><dd>{s.path.join(' / ')}</dd>
      <dt>Components</dt><dd>{s.componentUuids.length}</dd>
    </dl>
  {/if}
{/if}

<style>
  :global(.side.right) { padding: 0.6rem 0.7rem; font-size: 0.75rem; }
  .empty { color: var(--kv-text-dim); font-size: 0.8rem; }

  .hdr {
    display: flex; align-items: flex-start; justify-content: space-between;
    gap: 0.5rem; margin-bottom: 0.6rem;
    padding-bottom: 0.5rem; border-bottom: 1px solid var(--kv-border);
  }
  .titles { display: flex; flex-direction: column; gap: 0.1rem; min-width: 0; }
  .hdr h3 {
    margin: 0; font-size: 0.95rem; font-weight: 700;
    font-family: var(--kv-font-mono); color: var(--kv-text);
    line-height: 1.1;
  }
  .value {
    color: var(--kv-text-dim); font-size: 0.75rem;
    font-family: var(--kv-font-mono); word-break: break-word;
  }
  .count { color: var(--kv-text-dim); font-size: 0.7rem; font-weight: 400; }
  .dnp-pill {
    background: #b83232; color: white;
    padding: 0.08rem 0.4rem; border-radius: 3px;
    font-size: 0.62rem; font-weight: 700; letter-spacing: 0.06em;
    line-height: 1.2; flex-shrink: 0;
  }
  .side-pill {
    background: var(--kv-surface-2); color: var(--kv-text-dim);
    padding: 0 0.3rem; border-radius: 3px; font-size: 0.62rem;
    margin-left: 0.3rem;
  }

  dl {
    display: grid; grid-template-columns: max-content 1fr; gap: 0.2rem 0.6rem;
    margin: 0 0 0.7rem; align-items: baseline;
  }
  dt {
    color: var(--kv-text-dim); font-size: 0.68rem; font-weight: 400;
    letter-spacing: 0.03em; text-transform: uppercase;
    padding-top: 0.05rem;
  }
  dd {
    margin: 0; overflow-wrap: anywhere; color: var(--kv-text);
    font-size: 0.78rem;
  }
  dd a { color: var(--kv-accent); text-decoration: none; }
  dd a:hover { text-decoration: underline; }
  .mono { font-family: var(--kv-font-mono); font-size: 0.72rem; }

  h4 {
    margin: 0.6rem 0 0.3rem; font-size: 0.7rem; font-weight: 600;
    color: var(--kv-text-dim); text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  h4 .count { text-transform: none; letter-spacing: 0; margin-left: 0.25rem; }

  .table-wrap {
    border: 1px solid var(--kv-border); border-radius: 5px; overflow: hidden;
    background: var(--kv-surface);
  }
  /* Specificity bumped (.table-wrap table) so open-props/normalize's thead
     token doesn't force a dark header in light mode. */
  .table-wrap table {
    width: 100%; font-size: 0.72rem; border-collapse: collapse;
    background: var(--kv-surface); color: var(--kv-text);
  }
  .table-wrap thead,
  .table-wrap thead tr,
  .table-wrap thead th {
    background-color: var(--kv-surface-2);
    color: var(--kv-text);
  }
  .table-wrap thead th {
    font-weight: 600; font-size: 0.62rem;
    letter-spacing: 0.07em; text-transform: uppercase;
    padding: 4px 6px; text-align: left;
    border-bottom: 1px solid var(--kv-border);
  }
  .table-wrap tbody td {
    text-align: left; padding: 3px 6px;
    border-bottom: 1px solid var(--kv-border);
    background-color: var(--kv-surface); color: var(--kv-text);
  }
  .table-wrap tbody tr:last-child td { border-bottom: none; }
  .table-wrap tbody tr:hover td { background-color: var(--kv-surface-2); }
  .table-wrap td.num, .table-wrap th.num {
    font-family: var(--kv-font-mono);
    text-align: right; width: 2.2rem;
  }
</style>
