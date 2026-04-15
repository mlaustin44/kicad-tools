<script lang="ts">
  interface Props { value: string; onChange: (v: string) => void; }
  const tabs: Array<{ id: string; label: string }> = [
    { id: 'sch', label: 'Schematic' },
    { id: 'pcb', label: 'PCB' },
    { id: '3d',  label: '3D' },
    { id: 'split', label: 'Split ⇄' }
  ];
  let { value, onChange }: Props = $props();
</script>

<div class="tabs" role="tablist">
  {#each tabs as t}
    <button
      role="tab"
      aria-selected={value === t.id}
      class:active={value === t.id}
      onclick={() => onChange(t.id)}
    >{t.label}</button>
  {/each}
</div>

<style>
  .tabs { display: flex; gap: 0.25rem; }
  button {
    background: transparent; border: none; padding: 0.4rem 0.9rem;
    font-size: 0.85rem; color: var(--kv-text-dim);
    border-radius: 6px; cursor: pointer;
  }
  button.active { background: var(--kv-accent); color: white; }
  button:hover:not(.active) { color: var(--kv-text); background: var(--kv-surface-2); }
</style>
