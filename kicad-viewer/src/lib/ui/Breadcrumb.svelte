<script lang="ts">
  import type { Sheet } from '$lib/model/project';
  interface Props { sheet: Sheet; }
  let { sheet }: Props = $props();
</script>

<nav class="crumb">
  {#each sheet.path as p, i}
    <span>{p}</span>
    {#if i < sheet.path.length - 1}<span class="sep">›</span>{/if}
  {/each}
</nav>

<style>
  .crumb {
    position: absolute; top: 8px; left: 10px;
    background: var(--kv-surface); border: 1px solid var(--kv-border);
    border-radius: 6px; padding: 2px 8px; font-size: 0.75rem;
    display: flex; gap: 0.25rem;
  }
  .sep { color: var(--kv-text-dim); }
</style>
