<script lang="ts">
  import { project } from '$lib/stores/project';
  import { selectSheet } from '$lib/stores/selection';
  import type { Sheet } from '$lib/model/project';

  interface Props { activeUuid: string | null; onSelect: (uuid: string) => void; }
  let { activeUuid, onSelect }: Props = $props();

  let tree = $derived.by(() => {
    if (!$project) return [] as Array<{ sheet: Sheet; depth: number }>;
    const roots = $project.sheets.filter((s) => s.parent === null);
    const out: Array<{ sheet: Sheet; depth: number }> = [];
    const walk = (s: Sheet, depth: number) => {
      out.push({ sheet: s, depth });
      for (const c of $project!.sheets.filter((x) => x.parent === s.uuid)) {
        walk(c, depth + 1);
      }
    };
    roots.forEach((r) => walk(r, 0));
    return out;
  });
</script>

<div class="tree">
  <h4>Sheets</h4>
  {#each tree as row}
    <button
      class:active={row.sheet.uuid === activeUuid}
      style="padding-left: {row.depth * 12 + 8}px"
      onclick={() => { onSelect(row.sheet.uuid); selectSheet({ uuid: row.sheet.uuid, source: 'search' }); }}
    >{row.sheet.name}</button>
  {/each}
</div>

<style>
  .tree { font-size: 0.82rem; }
  h4 { font-size: 0.7rem; letter-spacing: 0.08em; color: var(--kv-text-dim); margin: 0.5rem 0.75rem; text-transform: uppercase; }
  button {
    display: block; width: 100%; text-align: left; background: transparent;
    border: none; padding: 4px 8px; color: var(--kv-text);
  }
  button.active { background: var(--kv-surface-2); color: var(--kv-accent); }
  button:hover:not(.active) { background: var(--kv-surface-2); }
</style>
