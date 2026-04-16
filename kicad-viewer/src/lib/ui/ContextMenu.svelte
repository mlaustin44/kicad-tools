<script lang="ts">
  interface MenuItem {
    label: string;
    action: () => void;
    disabled?: boolean;
  }
  interface Props {
    open: boolean;
    x: number;
    y: number;
    items: MenuItem[];
    onClose: () => void;
  }
  let { open, x, y, items, onClose }: Props = $props();
</script>

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="scrim" onclick={onClose} oncontextmenu={(e) => { e.preventDefault(); onClose(); }}></div>
  <ul class="menu" style="left: {x}px; top: {y}px;" role="menu">
    {#each items as it (it.label)}
      <li role="none">
        <button
          type="button"
          role="menuitem"
          disabled={it.disabled}
          onclick={() => { if (!it.disabled) { it.action(); onClose(); } }}
        >{it.label}</button>
      </li>
    {/each}
  </ul>
{/if}

<style>
  .scrim { position: fixed; inset: 0; z-index: 40; background: transparent; }
  .menu {
    position: fixed; z-index: 50;
    list-style: none; padding: 4px; margin: 0;
    background: var(--kv-surface);
    border: 1px solid var(--kv-border);
    border-radius: 6px;
    box-shadow: 0 8px 20px rgba(0,0,0,0.3);
    font-size: 0.85rem;
    min-width: 160px;
  }
  .menu li button {
    display: block; width: 100%; text-align: left;
    padding: 4px 10px; border: none; background: transparent;
    color: var(--kv-text); cursor: pointer; border-radius: 4px;
  }
  .menu li button:hover:not(:disabled) { background: var(--kv-surface-2); }
  .menu li button:disabled { color: var(--kv-text-dim); cursor: default; }
</style>
